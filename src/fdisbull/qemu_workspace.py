"""Checkpoint-bound DOS D: workspace generations for the QEMU process backend.

The workspace is observed only from a supplied, standalone QCOW2 checkpoint.
This module never reads a running disk image.  A successful generation record
therefore describes the exact D: bytes in one full VM checkpoint, not a live
view of guest writes made afterward.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .dos_file_layers import WorkspaceStore
from .qemu_dos_history import _history_operation

FORMAT = 'fdisbull-qemu-workspace-1'
RECORD_KIND = 'qemu-workspace-checkpoint'
MAX_DISK_BYTES = 64 * 1024 * 1024
MAX_QCOW_BYTES = 128 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _dos_path(value, *, allow_c=False):
    if not isinstance(value, str) or not value:
        raise ValueError('Workspace path must be a DOS relative path')
    value = value.replace('/', '\\')
    if len(value) >= 3 and value[1:3] == ':\\':
        if value[0].upper() not in (('C', 'D') if allow_c else ('D',)):
            raise ValueError('Workspace path must be relative to D:')
        value = value[3:]
    value = value.upper()
    if (not value or value.startswith('\\') or ':' in value
            or any(part in ('', '.', '..') for part in value.split('\\'))):
        raise ValueError('Workspace path must be relative to D:')
    return value


def _store_session(project, version):
    """Build the read-only subset WorkspaceStore needs for offline checks."""
    class Reader:
        def __init__(self):
            self.project = project
            self.version = {'id': version}
            self.run_id = ''

        def _artifact(self, *args, **kwargs):
            raise RuntimeError('Offline workspace validation cannot publish artifacts')
    return Reader()


def _runtime_component(session):
    supplied = getattr(session, '_workspace_runtime_component', None)
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise ValueError('Workspace runtime component identity must be an object')
        return deepcopy(supplied)
    vm = session.vm
    inputs = deepcopy(getattr(vm, 'inputs', {}))
    machine = deepcopy(getattr(vm, 'machine_configuration', {}))
    # Paths are useful evidence but may differ across compatible installations.
    # The executable/input hashes and QEMU version are the runtime identity.
    compact_inputs = {}
    for name, value in sorted(inputs.items()):
        if isinstance(value, dict):
            compact_inputs[name] = {k: deepcopy(v) for k, v in value.items()
                                    if k in ('sha256', 'version')}
        else:
            compact_inputs[name] = value
    profile = deepcopy(getattr(session, 'guest_profile', None))
    return dict(qemu_inputs=compact_inputs, machine=machine,
                guest_profile_sha256=(profile.get('profile_sha256') if isinstance(profile, dict) else None),
                source_sha256=getattr(session, 'metadata', {}).get('source_sha256'),
                version_sha256=getattr(session, 'metadata', {}).get('version_sha256'))


def _layout_json(layout):
    from .dos_workspace_fat import volume_layout
    if not isinstance(layout, dict):
        raise ValueError('Workspace disk layout must be an object')
    # Accept the full composite receipt or the result of volume_layout().
    partitions = layout.get('partitions', layout)
    if not isinstance(partitions, dict) or not {'C', 'D'} <= set(partitions):
        raise ValueError('Workspace layout must contain C: and D: partitions')
    result = {}
    for name in ('C', 'D'):
        item = partitions[name]
        if not isinstance(item, dict):
            raise ValueError('Workspace partition receipt is malformed')
        required = ('index', 'status', 'type', 'start_lba', 'sectors', 'offset', 'size')
        if any(type(item.get(key)) is not int for key in required):
            raise ValueError('Workspace partition extent is malformed')
        if item['offset'] != item['start_lba'] * 512 or item['size'] != item['sectors'] * 512:
            raise ValueError('Workspace partition sector and byte extents disagree')
        result[name] = {key: item[key] for key in required}
    if result['C']['offset'] + result['C']['size'] > result['D']['offset']:
        raise ValueError('Workspace partitions overlap or are out of order')
    if result['D']['offset'] + result['D']['size'] > MAX_DISK_BYTES:
        raise ValueError('Composite DOS disk exceeds the 64 MiB workspace limit')
    return result


def _inventory_entries(parsed):
    if not isinstance(parsed, dict):
        raise ValueError('FAT workspace parser returned an invalid inventory')
    entries = []
    for dos_path, item in sorted(parsed.items()):
        if not isinstance(item, dict) or item.get('type') not in ('file', 'directory'):
            raise ValueError('FAT workspace entry is malformed')
        if not isinstance(dos_path, str) or not dos_path or dos_path.startswith('\\'):
            raise ValueError('FAT workspace path is malformed')
        entries.append(dict(path=dos_path.replace('\\', '/'), dos_path=dos_path,
                            type=item['type'], attributes=item['attributes'],
                            dos_date=item['dos_date'], dos_time=item['dos_time'],
                            **({'data': item['data']} if item['type'] == 'file' else {})))
    return entries


def _generation_receipt(store, generation):
    row, data = store._row(generation, 'workspace-generation')
    manifest = store._manifest(generation)
    return dict(artifact=generation, sha256=row['sha256'], manifest=manifest)


def _make_state(session, *, base, generation, layout, source_dospath, mode,
                runtime_descriptor=None, source_sha256=None):
    if mode not in ('checkpointed', 'live'):
        raise ValueError('Workspace mode must be checkpointed or live')
    if not isinstance(source_dospath, str) or not source_dospath or len(source_dospath) > 260:
        raise ValueError('Original source DOS path is required and bounded')
    layout = _layout_json(layout)
    store = WorkspaceStore(session)
    base_ref = _generation_receipt(store, base)
    current_ref = _generation_receipt(store, generation)
    root = current_ref['manifest'].get('base') or generation
    if root != base:
        raise ValueError('Workspace generation does not descend from its declared base')
    runtime_component = _runtime_component(session)
    _json(runtime_component)
    runtime_descriptor = deepcopy(runtime_descriptor)
    _json(runtime_descriptor)
    source_sha256 = source_sha256 or getattr(session, 'metadata', {}).get('source_sha256')
    if not _digest(source_sha256):
        raise ValueError('Workspace source hash is missing or malformed')
    return dict(format=FORMAT, base_generation=base_ref, generation=current_ref,
                layout=layout, source_dospath=source_dospath,
                source_sha256=source_sha256, version=session.version['id'],
                version_sha256=session.metadata.get('version_sha256'), mode=mode,
                runtime_descriptor=runtime_descriptor,
                runtime_component=runtime_component,
                runtime_component_sha256=_sha(_json(runtime_component)),
                state_scope='The complete private QCOW2 disk is checkpointed; guest handles and caches are preserved only by the accompanying full VM checkpoint.')


def init_state(session, capture, runtime, layout, source_dospath, mode,
               generation=None):
    """Initialize the session's immutable base generation after binding.

    ``capture`` may be the mapping returned by ``dos_workspace_fat.parse_volume``
    or an explicit inventory with an ``entries`` mapping/list.  It is an
    observed base inventory; this call does not claim guest-created provenance.
    """
    if getattr(session, 'closed', True):
        raise ValueError('Cannot initialize a workspace on a closed session')
    if not isinstance(capture, dict):
        raise ValueError('Workspace initial capture must be an inventory')
    raw_entries = capture.get('entries', capture)
    if isinstance(raw_entries, dict):
        parsed = raw_entries
        entries = _inventory_entries(parsed)
    elif isinstance(raw_entries, list):
        entries = deepcopy(raw_entries)
    else:
        raise ValueError('Workspace initial inventory has no entries')
    store = WorkspaceStore(session)
    if generation is None:
        source_root = capture.get('root') if isinstance(capture, dict) else None
        source_identity = capture.get('root_identity') if isinstance(capture, dict) else None
        result = store.seal(entries, mode=mode, reason='initial-disk-capture',
                            source_root=source_root, source_identity=source_identity)
        generation = result['artifact']
    generation_ref = _generation_receipt(store, generation)
    base_generation = generation_ref['manifest'].get('base') or generation
    state = _make_state(session, base=base_generation, generation=generation,
                        layout=layout, source_dospath=source_dospath, mode=mode,
                        runtime_descriptor=runtime,
                        source_sha256=session.metadata.get('source_sha256'))
    session._dos_workspace = state
    return _status(state)


def _status(state, *, active=True):
    if not isinstance(state, dict) or state.get('format') != FORMAT:
        raise ValueError('DOS workspace has not been initialized')
    generation = state['generation']
    return dict(format=FORMAT, active=bool(active), mode=state['mode'],
                source_dospath=state['source_dospath'], source_sha256=state['source_sha256'],
                base_generation=deepcopy(state['base_generation']),
                generation=deepcopy(generation), layout=deepcopy(state['layout']),
                runtime_component_sha256=state['runtime_component_sha256'],
                state_scope=state['state_scope'], live_guest_visibility=False,
                new_file_provenance='requires an explicit witnessed create operation')


def _deadline(session):
    value = getattr(session, '_rpc_deadline', None)
    if value is None:
        value = getattr(session, '_deadline', None)
    return value or (time.monotonic() + 60.0)


def _convert_qcow_to_raw(session, qcow_bytes):
    if not isinstance(qcow_bytes, bytes) or not qcow_bytes or len(qcow_bytes) > MAX_QCOW_BYTES:
        raise ValueError('Workspace checkpoint QCOW2 bytes exceed their bound')
    vm = session.vm
    virtual_size = getattr(vm, 'checkpoint_virtual_size', None)
    if type(virtual_size) is not int or not 1 <= virtual_size <= MAX_DISK_BYTES:
        raise ValueError('Workspace checkpoint virtual disk must be at most 64 MiB')
    tool = getattr(vm, 'inputs', {}).get('checkpoint_tool', {}).get('path')
    if not isinstance(tool, str) or not os.path.isabs(tool) or not os.access(tool, os.X_OK):
        raise ValueError('Workspace checkpoint requires the admitted qemu-img executable')
    from .qemu_checkpoint import validate_qcow_header
    validate_qcow_header(qcow_bytes[:104], virtual_size)
    parent = Path(vm.checkpoint_disk).resolve().parent
    if not parent.is_dir():
        raise ValueError('Workspace checkpoint temporary parent is unavailable')
    deadline = _deadline(session)
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError('Workspace checkpoint conversion deadline expired')
        return max(0.001, value)
    with tempfile.TemporaryDirectory(prefix='fdb-workspace-', dir=parent) as directory:
        source = Path(directory) / 'checkpoint.qcow2'
        target = Path(directory) / 'disk.raw'
        source.write_bytes(qcow_bytes)
        info = subprocess.run([tool, 'info', '-f', 'qcow2', '--output=json', str(source)],
                              check=True, timeout=remaining(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        try:
            details = json.loads(info.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError('Workspace QCOW2 metadata is malformed') from error
        if (details.get('format') != 'qcow2' or details.get('virtual-size') != virtual_size
                or details.get('backing-filename') or details.get('full-backing-filename')):
            raise ValueError('Workspace checkpoint must be a standalone matching QCOW2 disk')
        subprocess.run([tool, 'convert', '-f', 'qcow2', '-O', 'raw', str(source), str(target)],
                       check=True, timeout=remaining(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE)
        if target.stat().st_size != virtual_size or target.stat().st_size > MAX_DISK_BYTES:
            raise ValueError('Workspace raw conversion returned an unexpected disk size')
        raw = target.read_bytes()
    return raw


def _publish_record(session, payload):
    encoded = _json(payload)
    digest = _sha(encoded)
    receipt = session._artifact('qemu-workspace-checkpoint.json', RECORD_KIND, encoded,
                                dict(format=FORMAT, record_sha256=digest,
                                     generation=payload['generation']['artifact']))
    if (not isinstance(receipt, dict) or receipt.get('sha256') != digest
            or receipt.get('size') != len(encoded)):
        raise ValueError('Workspace checkpoint record receipt differs')
    return dict(**deepcopy(payload), artifact=receipt['artifact'], record_sha256=digest)


def checkpoint_workspace(session, qcow_bytes):
    """Seal one immutable semantic generation from supplied snapshot bytes."""
    state = deepcopy(getattr(session, '_dos_workspace', None))
    if not isinstance(state, dict) or state.get('format') != FORMAT:
        raise ValueError('DOS workspace base generation is not initialized')
    if state.get('version') != session.version['id']:
        raise ValueError('DOS workspace belongs to another source version')
    runtime = _runtime_component(session)
    if _sha(_json(runtime)) != state.get('runtime_component_sha256'):
        raise ValueError('DOS workspace runtime component identity changed')
    raw = _convert_qcow_to_raw(session, qcow_bytes)
    from .dos_workspace_fat import parse_volume, volume_layout
    layout = _layout_json(volume_layout(raw))
    if layout != state['layout']:
        raise ValueError('Checkpoint disk layout differs from the admitted workspace')
    d = layout['D']
    workspace_bytes = raw[d['offset']:d['offset'] + d['size']]
    parsed = parse_volume(workspace_bytes)
    entries = _inventory_entries(parsed)
    store = WorkspaceStore(session)
    parent = state['generation']['artifact']
    # FAT stores only the DOS 8.3 alias. Preserve the host spelling admitted
    # for an unchanged path so an ordinary checkpoint does not manufacture a
    # rename (or change the file's keep/export provenance).
    previous = store.load(parent)['entries']
    host_paths = {(item['dos_path'].casefold(), item['type']): item['path']
                  for item in previous}
    for item in entries:
        original_path = host_paths.get((item['dos_path'].casefold(), item['type']))
        if original_path is not None:
            item['path'] = original_path
    child = store.seal(entries, parent=parent, reason='checkpointed-qcow2-capture')
    child_ref = _generation_receipt(store, child['artifact'])
    base = state['base_generation']['artifact']
    payload = dict(format=FORMAT, version=session.version['id'],
        source_sha256=state['source_sha256'], version_sha256=session.metadata.get('version_sha256'),
        source_dospath=state['source_dospath'], mode=state['mode'],
        state_scope=state['state_scope'], runtime_descriptor=deepcopy(state['runtime_descriptor']),
        runtime_component=runtime,
        runtime_component_sha256=_sha(_json(runtime)), layout=layout,
        qcow_sha256=_sha(qcow_bytes), qcow_size=len(qcow_bytes),
        raw_sha256=_sha(raw), raw_size=len(raw),
        workspace_volume_sha256=_sha(workspace_bytes),
        base_generation=_generation_receipt(store, base), generation=child_ref,
        capture='read from supplied standalone QCOW2 checkpoint bytes; no live image access')
    published = _publish_record(session, payload)
    # Advance only after all file chunks, manifest, and record are durable.
    state['generation'] = child_ref
    state['last_record'] = deepcopy(published)
    session._dos_workspace = state
    return published


def _record_payload(record):
    if not isinstance(record, dict) or record.get('format') != FORMAT:
        raise ValueError('Invalid QEMU workspace checkpoint record')
    payload = {key: deepcopy(value) for key, value in record.items()
               if key not in ('artifact', 'record_sha256', 'entries')}
    if not isinstance(record.get('artifact'), str) or not _digest(record.get('record_sha256')):
        raise ValueError('Workspace record artifact receipt is missing')
    if _sha(_json(payload)) != record['record_sha256']:
        raise ValueError('Workspace record payload hash differs')
    return payload


def validate_workspace(project, record, version):
    """Validate a workspace record and its complete immutable chunk lineage."""
    payload = _record_payload(record)
    row = project.db.execute(
        'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
        (record['artifact'],)).fetchone()
    if (row is None or row['kind'] != RECORD_KIND or row['version'] != version
            or _sha(bytes(row['data'])) != row['sha256']
            or bytes(row['data']) != _json(payload)):
        raise ValueError('Workspace record artifact is missing, cross-version, or corrupt')
    metadata = json.loads(row['metadata'])
    if (metadata.get('format') != FORMAT or metadata.get('record_sha256') != record['record_sha256']
            or metadata.get('generation') != payload['generation']['artifact']):
        raise ValueError('Workspace record metadata differs')
    if (payload.get('version') != version or not _digest(payload.get('source_sha256'))
            or not _digest(payload.get('version_sha256'))
            or payload.get('mode') not in ('live', 'checkpointed')
            or not isinstance(payload.get('state_scope'), str)
            or type(payload.get('qcow_size')) is not int or not 1 <= payload['qcow_size'] <= MAX_QCOW_BYTES
            or type(payload.get('raw_size')) is not int or not 1 <= payload['raw_size'] <= MAX_DISK_BYTES
            or not isinstance(payload.get('runtime_descriptor'), (dict, list, str, int, bool, type(None)))
            or not _digest(payload.get('runtime_component_sha256'))
            or _sha(_json(payload.get('runtime_component'))) != payload.get('runtime_component_sha256')
            or not _digest(payload.get('qcow_sha256')) or not _digest(payload.get('raw_sha256'))
            or not _digest(payload.get('workspace_volume_sha256'))):
        raise ValueError('Workspace record identity is malformed')
    layout = _layout_json(payload.get('layout'))
    if layout != payload['layout']:
        raise ValueError('Workspace record layout is not canonical')
    reader = _store_session(project, version)
    store = WorkspaceStore(reader)
    for key in ('base_generation', 'generation'):
        ref = payload.get(key)
        if not isinstance(ref, dict) or set(ref) != {'artifact', 'sha256', 'manifest'}:
            raise ValueError('Workspace generation reference is malformed')
        if not _digest(ref.get('sha256')):
            raise ValueError('Workspace generation hash is malformed')
        actual = _generation_receipt(store, ref['artifact'])
        if actual['sha256'] != ref['sha256'] or actual['manifest'] != ref['manifest']:
            raise ValueError('Workspace generation reference differs from durable store')
    base = payload['base_generation']['artifact']
    generation = payload['generation']['artifact']
    if (payload['generation']['manifest'].get('base') != base
            or payload['generation']['manifest'].get('parent') is None):
        raise ValueError('Workspace checkpoint generation is not a child of its base lineage')
    if any(ref['manifest'].get('mode') != payload['mode']
           for ref in (payload['base_generation'], payload['generation'])):
        raise ValueError('Workspace generation mode differs from its checkpoint record')
    source_dospath = _dos_path(payload.get('source_dospath'), allow_c=True)
    if source_dospath not in payload['base_generation']['manifest'].get('original_dos_paths', []):
        raise ValueError('Workspace source DOS path is not in its original inventory')
    loaded = store.load(generation)
    entries = loaded['entries']
    if len(_json([{k: item[k] for k in item if k != 'data'} for item in entries])) > 16 * 1024 * 1024:
        raise ValueError('Workspace inventory exceeds its metadata bound')
    return dict(**deepcopy(payload), artifact=record['artifact'], record_sha256=record['record_sha256'],
                entries=entries)


def validate_workspace_image(record, raw_disk):
    """Bind an offline validated record to the D: bytes in its saved QCOW2."""
    payload = _record_payload(record)
    if not isinstance(raw_disk, bytes) or len(raw_disk) != payload.get('raw_size'):
        raise ValueError('Workspace checkpoint raw disk size differs')
    if _sha(raw_disk) != payload.get('raw_sha256'):
        raise ValueError('Workspace checkpoint raw disk hash differs')
    from .dos_workspace_fat import parse_volume, volume_layout
    layout = _layout_json(volume_layout(raw_disk))
    if layout != payload.get('layout'):
        raise ValueError('Workspace raw disk layout differs')
    d = layout['D']
    volume = raw_disk[d['offset']:d['offset'] + d['size']]
    if _sha(volume) != payload.get('workspace_volume_sha256'):
        raise ValueError('Workspace FAT volume hash differs')
    actual = parse_volume(volume)
    expected_entries = record.get('entries')
    if expected_entries is None:
        raise ValueError('Workspace record must be validated against its durable generation first')
    expected = {item['dos_path']: item for item in expected_entries}
    if set(actual) != set(expected):
        raise ValueError('Workspace FAT inventory paths differ from its generation')
    for path, item in actual.items():
        prior = expected[path]
        for key in ('type', 'attributes', 'dos_date', 'dos_time'):
            if item[key] != prior[key]:
                raise ValueError('Workspace FAT metadata differs from its generation')
        if item['type'] == 'file' and item['data'] != prior['data']:
            raise ValueError('Workspace FAT file bytes differ from its generation')
    return dict(valid=True, raw_sha256=_sha(raw_disk), workspace_volume_sha256=_sha(volume),
                generation=payload['generation']['artifact'])


def verify_workspace_checkpoint(session, machine_bytes, record):
    """Validate sidecar refs and prove D: matches before a VM is replaced."""
    validated = validate_workspace(session.project, record, session.version['id'])
    raw = _convert_qcow_to_raw(session, machine_bytes)
    image = validate_workspace_image(validated, raw)
    return dict(record=validated, image=image)


def restore_workspace(session, record):
    """Adopt workspace state after the caller's full native VM restore passed."""
    payload = validate_workspace(session.project, record, session.version['id'])
    runtime = _runtime_component(session)
    if _sha(_json(runtime)) != payload['runtime_component_sha256']:
        raise ValueError('Restored workspace runtime identity differs')
    current = getattr(session, '_dos_workspace', None)
    if not isinstance(current, dict) or current.get('format') != FORMAT:
        # A fresh session can adopt the lineage after full process-checkpoint
        # verification; the original checkpoint already binds its source.
        current = dict(format=FORMAT)
    session._dos_workspace = dict(format=FORMAT, version=payload['version'],
        source_sha256=payload['source_sha256'], source_dospath=payload['source_dospath'],
        version_sha256=payload['version_sha256'], mode=payload['mode'],
        runtime_descriptor=deepcopy(payload['runtime_descriptor']),
        state_scope=payload['state_scope'], runtime_component=deepcopy(payload['runtime_component']),
        runtime_component_sha256=payload['runtime_component_sha256'], layout=deepcopy(payload['layout']),
        base_generation=deepcopy(payload['base_generation']),
        generation=deepcopy(payload['generation']), last_record=deepcopy(record))
    return _status(session._dos_workspace)


def _seal_workspace(session, name='qemu-workspace-checkpoint.qcow2'):
    """Seal under the caller's existing machine lock, deadline and history scope."""
    result = session.save_state(name, max_bytes=128 * 1024 * 1024)
    artifact = result.get('artifact') if isinstance(result, dict) else None
    if not isinstance(artifact, str):
        raise ValueError('Workspace seal did not receive a full checkpoint artifact')
    row = session.project.db.execute('SELECT data,sha256,metadata FROM debug_artifacts WHERE id=?',
                                    (artifact,)).fetchone()
    if row is None or row['sha256'] != _sha(bytes(row['data'])):
        session.close()
        raise ValueError('Workspace checkpoint artifact readback differs')
    from .qemu_dos_checkpoint import _unarchive, checkpoint_format
    if json.loads(row['metadata']).get('format') != checkpoint_format(session):
        raise ValueError('Workspace sealing requires a full native DOS checkpoint')
    _machine, bundle = _unarchive(bytes(row['data']))
    record = bundle.get('workspace')
    if not isinstance(record, dict):
        raise ValueError('Full checkpoint did not publish a workspace generation')
    return dict(checkpoint=artifact, workspace=deepcopy(record), status=restore_workspace(session, record))


class QemuDOSWorkspaceMixin:
    """Read sealed D: generations; capture them only at full-QEMU checkpoint."""

    def _workspace_store(self):
        state = getattr(self, '_dos_workspace', None)
        if not isinstance(state, dict) or state.get('format') != FORMAT:
            raise ValueError('DOS workspace is not initialized')
        return WorkspaceStore(self)

    def _workspace_generation(self, store, generation):
        if generation is None:
            generation = self._dos_workspace['generation']['artifact']
        if not isinstance(generation, str) or not generation:
            raise ValueError('Workspace generation ID must be a nonempty string')
        loaded = store.load(generation)
        if (loaded['manifest']['base'] or generation) != self._dos_workspace['base_generation']['artifact']:
            raise ValueError('Workspace generation belongs to a different base')
        return generation

    @_history_operation
    def workspace_status(self, *, timeout_ms=60000):
        return _status(getattr(self, '_dos_workspace', None), active=not self.closed)

    @_history_operation
    def workspace_files(self, generation=None, *, view='effective', timeout_ms=60000):
        store = self._workspace_store()
        state = self._dos_workspace
        generation = self._workspace_generation(store, generation)
        if view not in ('effective', 'base', 'diff'):
            raise ValueError("workspace view must be 'effective', 'base', or 'diff'")
        inventory = store.inspect(generation, base=state['base_generation']['artifact'])
        if view == 'diff':
            return dict(format=FORMAT, generation=generation, view=view,
                        entries=deepcopy(inventory['difference']))
        return dict(format=FORMAT, generation=generation, view=view,
                    entries=deepcopy(inventory['base_entries'] if view == 'base'
                                     else inventory['effective']))

    @_history_operation
    def workspace_read(self, path, generation=None, *, timeout_ms=60000):
        if not isinstance(path, str) or not path:
            raise ValueError('Workspace read requires a DOS relative path')
        dos_path = _dos_path(path)
        store = self._workspace_store()
        generation = self._workspace_generation(store, generation)
        loaded = store.load(generation)
        found = next((item for item in loaded['entries']
                      if item['dos_path'].casefold() == dos_path.casefold()), None)
        if found is None or found['type'] != 'file':
            raise ValueError('Workspace file is absent from the selected sealed generation')
        data = found['data']
        return dict(format=FORMAT, generation=generation, dos_path=found['dos_path'],
                    size=len(data), sha256=_sha(data), data=data)

    @_history_operation
    def workspace_seal(self, name='qemu-workspace-checkpoint.qcow2', *, timeout_ms=60000):
        """Save one complete VM checkpoint; its QCOW2 snapshot creates the generation."""
        return _seal_workspace(self, name)

    @_history_operation
    def workspace_save_output(self, path, new_destination, *, closed_and_flushed=False,
                              timeout_ms=60000):
        """Capture and export an explicitly attested closed/flushed guest output."""
        from .qemu_workspace_output import save_output
        return save_output(self, path, new_destination, closed_and_flushed=closed_and_flushed)

    @_history_operation
    def workspace_export(self, path, new_destination, generation=None, *, timeout_ms=60000):
        store = self._workspace_store()
        generation = self._workspace_generation(store, generation)
        # Export is exclusive and byte-verified by WorkspaceStore. Unlike keep,
        # it does not imply that an observed raw FAT pathname was guest-created.
        export = getattr(store, 'export_file', None)
        if export is None:
            raise ValueError('Workspace store does not support explicit file export')
        return export(generation, _dos_path(path), new_destination)

    @_history_operation
    def workspace_keep(self, path, new_destination, generation=None, *, timeout_ms=60000):
        """Export an explicitly created staged file, without claiming guest creation."""
        store = self._workspace_store()
        generation = self._workspace_generation(store, generation)
        return store.keep(generation, _dos_path(path), new_destination)

    @_history_operation
    def workspace_edit(self, generation, operation, *, path=None, data=None,
                       offset=None, size=None, destination=None,
                       expected_sha256=None, timeout_ms=60000):
        """Create a staged immutable child generation without changing the VM."""
        schemas = {
            'create': {'path', 'data'}, 'import': {'path', 'data'},
            'write': {'path', 'data', 'expected_sha256'},
            'write-range': {'path', 'data', 'offset', 'expected_sha256'},
            'resize': {'path', 'size', 'expected_sha256'},
            'rename': {'path', 'destination'}, 'delete': {'path'},
            'refresh': set(),
        }
        if not isinstance(generation, str) or not generation:
            raise ValueError('Workspace edit requires an explicit generation ID')
        if not isinstance(operation, str) or operation not in schemas:
            raise ValueError('Unknown workspace edit operation')
        supplied = {key for key, value in dict(path=path, data=data, offset=offset,
                    size=size, destination=destination, expected_sha256=expected_sha256).items()
                    if value is not None}
        if supplied != schemas[operation]:
            raise ValueError('Workspace edit arguments do not match the operation')
        if data is not None and not isinstance(data, bytes):
            raise ValueError('Workspace edit data must be bytes')
        if expected_sha256 is not None and not _digest(expected_sha256):
            raise ValueError('Workspace edit expected SHA-256 is malformed')
        path = _dos_path(path) if path is not None else None
        destination = _dos_path(destination) if destination is not None else None
        store = self._workspace_store()
        generation = self._workspace_generation(store, generation)
        self._history_remaining_ms()
        if operation == 'create':
            result = store.create_file(generation, path, data)
        elif operation == 'import':
            result = store.import_file(generation, path, data)
        elif operation == 'write':
            result = store.write_file(generation, path, data, expected_sha256=expected_sha256)
        elif operation == 'write-range':
            result = store.write_range(generation, path, offset, data, expected_sha256=expected_sha256)
        elif operation == 'resize':
            result = store.resize_file(generation, path, size, expected_sha256=expected_sha256)
        elif operation == 'rename':
            result = store.rename_file(generation, path, destination)
        elif operation == 'delete':
            result = store.delete_file(generation, path)
        else:
            result = store.refresh(generation,
                source_dospath=_dos_path(self._dos_workspace['source_dospath'], allow_c=True),
                expected_source_sha256=self._dos_workspace['source_sha256'])
        receipt = _generation_receipt(store, result['artifact'])
        if receipt['sha256'] != result['sha256']:
            raise ValueError('Staged workspace generation readback differs')
        response = dict(format=FORMAT, operation=operation, parent_generation=generation,
                    generation=receipt, active=False,
                    activation='not active until launch or restore',
                    guest_create_provenance=False)
        if operation == 'refresh':
            response.update(activation='cold launch only; running guest unchanged',
                            capture_consistency=result['capture_consistency'])
        return response
