"""Persistent, full-checkpoint history for owned QEMU DOS processes.

This module deliberately records complete process checkpoints.  It does not
implement inverse CPU/RAM deltas or deterministic replay.  Each history
revision is an immutable artifact containing the DAG index; each node points
to a full ``qemu_dos_checkpoint`` state artifact.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import inspect
import json
import time
import uuid

from .operation_budget import request_deadline

FORMAT = 'fdisbull-qemu-dos-history-v1'
MANIFEST_KIND = 'rewind-history'
MAX_NODES = 128
MAX_HISTORY_BYTES = 1024 * 1024 * 1024
MAX_STATE = 128 * 1024 * 1024

# These observations do not change the selected guest or debugger controls.
# Every other operation invalidates the live edge before it can be dispatched.
_READ_ONLY = frozenset({
    'rewind_status', 'status', 'registers', 'memory', 'memory_snapshot',
    'memory_translation', 'dos_process_info', 'dos_task_observe',
    'dos_task_context', 'dos_task_scheduler_observe', 'dos_task_memory',
    'dos_task_layers', 'code',
    'hooks', 'layer_stack', 'clock_observe', 'audio_observe',
    'display_observe', 'retrace_observe', 'input_state',
})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _hex_digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in '0123456789abcdef' for char in value))


def _positive_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be an integer in {minimum}..{maximum}')
    return value


def _history_operation(function):
    """Hold one lock/deadline across every nested checkpoint and step RPC."""
    @wraps(function)
    def invoke(self, *args, **kwargs):
        bound_args = inspect.signature(function).bind(self, *args, **kwargs)
        bound_args.apply_defaults()
        timeout_ms = bound_args.arguments.get('timeout_ms', 60000)
        deadline = request_deadline(self, timeout_ms)
        vm = self.vm
        limits = [deadline, getattr(self, '_deadline', None),
                  getattr(vm, 'operation_deadline', None),
                  *(getattr(channel, 'operation_deadline', None)
                    for channel in (getattr(vm, 'qmp', None), getattr(vm, 'gdb', None))
                    if channel is not None)]
        deadline = min(value for value in limits if value is not None)
        wait = min(10.0, deadline - time.monotonic())
        if wait <= 0 or not vm.lock.acquire(timeout=wait):
            raise TimeoutError('QEMU history operation could not acquire the machine before its deadline')
        saved = dict(
            session_deadline=getattr(self, '_deadline', None),
            rpc_deadline=getattr(self, '_rpc_deadline', None),
            vm_deadline=getattr(vm, 'operation_deadline', None),
            channels={name: (getattr(vm, name), getattr(getattr(vm, name), 'operation_deadline', None))
                      for name in ('qmp', 'gdb') if getattr(vm, name, None) is not None},
            serial_deadline=getattr(getattr(self, '_channel', None), 'operation_deadline', None),
            busy=getattr(self, '_history_busy', False),
        )
        try:
            legacy_guard = getattr(vm, 'operation_guard', None)
            if legacy_guard is not None:
                legacy_guard(function.__name__)
            self._history_busy = True
            detail_guard = getattr(vm, 'history_operation_guard', None)
            if detail_guard is not None:
                detail_guard(function.__name__, args, kwargs)
            self._rpc_deadline = deadline
            self._deadline = deadline
            vm.operation_deadline = deadline
            for channel_name, (channel, _) in saved['channels'].items():
                channel.operation_deadline = deadline
            result = function(self, *args, **kwargs)
            if time.monotonic() >= deadline:
                error = TimeoutError('QEMU history operation exceeded its outer deadline')
                error.result = result
                if function.__name__ in ('rewind_start', 'rewind_record', 'rewind'):
                    try:
                        self.close()
                    except Exception:
                        pass
                raise error
            return result
        finally:
            self._history_busy = saved['busy']
            self._rpc_deadline = saved['rpc_deadline']
            self._deadline = saved['session_deadline']
            vm.operation_deadline = saved['vm_deadline']
            for channel_name, (channel, old) in saved['channels'].items():
                channel.operation_deadline = old
            new_vm = getattr(self, 'vm', None)
            if new_vm is not None and new_vm is not vm:
                new_vm.operation_deadline = saved['vm_deadline']
                for name in ('qmp', 'gdb'):
                    channel = getattr(new_vm, name, None)
                    if channel is not None:
                        old = saved['channels'].get(name)
                        channel.operation_deadline = old[1] if old is not None else None
                serial_channel = getattr(self, '_channel', None)
                if serial_channel is not None and hasattr(serial_channel, 'operation_deadline'):
                    serial_channel.operation_deadline = saved['serial_deadline']
            vm.lock.release()
    return invoke


class QemuDOSHistoryMixin:
    """Checkpoint-backed rewind DAG for a source-bound QEMU DOS process.

    Required session attributes are ``project``, ``run_id``, ``version``,
    ``metadata``, ``vm``, ``_process``, ``save_state``, ``load_state``,
    ``registers`` and ``step``. The integration calls :meth:`_history_bind`
    after session creation and after a verified full-checkpoint VM replacement.
    """

    _history_busy = False

    def _history_bind(self):
        """Install the detail-only guard without replacing native task guards."""
        vm = self.vm
        previous = getattr(vm, 'history_operation_guard', None)
        if getattr(previous, '_qemu_dos_history_owner', None) is self:
            return

        def chained(name, args=(), kwargs=None):
            if previous is not None:
                previous(name, args, kwargs or {})
            self._history_before_operation(name, args, kwargs)

        chained._qemu_dos_history_owner = self
        vm.history_operation_guard = chained

    def _history_before_operation(self, name, args=(), kwargs=None):
        """Invalidate the live edge before an unrecorded external mutation."""
        kwargs = kwargs or {}
        readonly = name in _READ_ONLY
        if name in ('layers', 'dos_task_layers'):
            active = kwargs.get('active', args[0] if args else None)
            readonly = active is None
        if getattr(self, '_history_busy', False) or readonly:
            return
        live = getattr(self, '_qemu_history_live', None)
        if live is None or not live.get('valid'):
            return
        live['valid'] = False
        live['invalid_reason'] = 'unrecorded operation: ' + str(name)
        live['cursor'] = None

    def _history_supported(self):
        from .qemu_dos_checkpoint import COMMAND
        if (getattr(self, 'closed', True) or self.metadata.get('backend') != 'qemu-dos'
                or COMMAND not in getattr(self.vm, 'qmp_commands', set())
                or self.vm.checkpoint_disk is None
                or self._checkpoint_launch.get('checkpoint_tool') is None):
            raise ValueError('QEMU process history requires the native full DOS checkpoint extension')
        if self.project.db.in_transaction:
            raise ValueError('History operations require a project outside a caller-owned transaction')

    def _history_identity(self):
        from .qemu_dos_checkpoint import _compatibility
        from .dos_process_helper import _NONCE_FILE_OFFSET
        profile = self.guest_profile
        helper = bytearray(self._helper)
        nonce = getattr(self, '_nonce', None)
        if nonce is not None:
            if (not isinstance(nonce, bytes) or len(nonce) != 16
                    or helper[_NONCE_FILE_OFFSET:_NONCE_FILE_OFFSET + 16] != nonce):
                raise ValueError('History loader helper does not match its process nonce')
            # The nonce fences one live owner. Only this authored field is
            # neutralized for cross-session compatibility; target, tail and
            # every instruction byte remain part of the helper identity.
            helper[_NONCE_FILE_OFFSET:_NONCE_FILE_OFFSET + 16] = bytes(16)
        return dict(
            schema=1,
            source_sha256=self.metadata['source_sha256'],
            version=self.version['id'],
            version_sha256=self.metadata['version_sha256'],
            runtime=_compatibility(self),
            target=dict(filename=self.project.meta['filename'], format=self.project.meta['format'],
                        command_tail_sha256=_sha(self._tail),
                        helper_sha256=_sha(bytes(helper))),
            guest_schema=profile['schema'],
            guest_profile_sha256=profile['profile_sha256'],
        )

    def _history_admission(self):
        """Reject known checkpoint/controller conflicts before any intent."""
        from .qemu_dos_checkpoint import _preflight, _serial_idle
        _preflight(self)
        _serial_idle(self)

    def _history_base_response(self):
        return dict(format=FORMAT, active=not getattr(self, 'closed', True),
                    implementation='immutable full native DOS process checkpoints; no deterministic replay',
                    checkpoint_scope='source-bound DOS process, private QCOW2 and debugger/native controls',
                    host_files_restored=False,
                    storage_budget_scope='cumulative state artifact payloads; bounded by the project 256 MiB runtime-artifact cap',
                    private_disk_budget_scope='live private QCOW2 file growth is measured separately and is not quota-managed',
                    live_private_disk_bytes=self._history_disk_bytes())

    def _history_disk_bytes(self):
        path = getattr(getattr(self, 'vm', None), 'checkpoint_disk', None)
        try:
            return path.stat().st_size if path is not None else None
        except OSError:
            return None

    def _history_live_fingerprint(self):
        nonce = getattr(self, '_nonce', b'')
        if isinstance(nonce, str):
            nonce = nonce.encode('utf-8')
        return dict(epoch=getattr(self, '_runtime_epoch', None),
                    process_nonce_sha256=_sha(bytes(nonce)))

    def _history_row(self, artifact):
        if not isinstance(artifact, str) or not artifact:
            raise ValueError('History must identify an immutable manifest artifact')
        row = self.project.db.execute(
            'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
            (artifact,)).fetchone()
        if row is None or row['kind'] != MANIFEST_KIND or row['version'] != self.version['id']:
            raise ValueError('History manifest must belong to this project version')
        data = bytes(row['data'])
        if _sha(data) != row['sha256']:
            raise ValueError('History manifest artifact hash mismatch')
        try:
            manifest = json.loads(data)
        except (TypeError, ValueError) as error:
            raise ValueError('History manifest is invalid JSON') from error
        self._validate_manifest(manifest)
        if row['metadata']:
            metadata = json.loads(row['metadata'])
            if (metadata.get('format') != FORMAT or metadata.get('history_id') != manifest['id']
                    or metadata.get('manifest_sha256') != row['sha256']):
                raise ValueError('History manifest metadata does not match its content')
        if manifest['identity'] != self._history_identity():
            raise ValueError('History source, version, runtime or target identity differs')
        manifest['_artifact_id'] = artifact
        return manifest, row

    def _history_latest(self, history):
        manifest, row = self._history_row(history)
        history_id = manifest['id']
        rows = self.project.db.execute(
            'SELECT id,metadata FROM debug_artifacts WHERE kind=?', (MANIFEST_KIND,)).fetchall()
        candidates = [(int(json.loads(item['metadata']).get('revision', -1)), item['id'])
                      for item in rows
                      if json.loads(item['metadata']).get('history_id') == history_id]
        if not candidates:
            raise ValueError('History has no persisted manifest revisions')
        _, latest_id = max(candidates)
        return self._history_row(latest_id)

    @staticmethod
    def _validate_manifest(manifest):
        if (not isinstance(manifest, dict) or manifest.get('format') != FORMAT
                or not isinstance(manifest.get('id'), str)
                or not isinstance(manifest.get('identity'), dict)
                or not isinstance(manifest.get('nodes'), list)
                or len(manifest['nodes']) > MAX_NODES
                or type(manifest.get('max_steps')) is not int
                or not 1 <= manifest['max_steps'] <= MAX_NODES
                or type(manifest.get('max_bytes')) is not int
                or not 1 <= manifest['max_bytes'] <= MAX_HISTORY_BYTES
                or not isinstance(manifest.get('pending'), (dict, type(None)))):
            raise ValueError('History manifest has an unsupported or invalid schema')
        seen = set()
        state_bytes = 0
        for node in manifest['nodes']:
            if (not isinstance(node, dict) or not isinstance(node.get('id'), str)
                    or node['id'] in seen or node.get('parent') not in seen | {None}
                    or not isinstance(node.get('checkpoint'), dict)
                    or not isinstance(node.get('edge'), dict)):
                raise ValueError('History contains an invalid DAG node')
            cp = node['checkpoint']
            if (not isinstance(cp.get('artifact'), str) or not _hex_digest(cp.get('sha256'))
                    or type(cp.get('size')) is not int or cp['size'] < 1):
                raise ValueError('History node checkpoint reference is invalid')
            state_bytes += cp['size']
            seen.add(node['id'])
        if len(seen) > manifest['max_steps'] or state_bytes > manifest['max_bytes']:
            raise ValueError('History exceeds its recorded cumulative budget')
        if manifest.get('cursor') is not None and manifest['cursor'] not in seen:
            raise ValueError('History cursor does not identify a node')
        if manifest.get('head') is not None and manifest['head'] not in seen:
            raise ValueError('History head does not identify a node')

    def _history_publish(self, manifest, *, reason):
        self._validate_manifest(manifest)
        data = _json(manifest)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('History manifest exceeds its artifact limit')
        digest = _sha(data)
        with self.project.transaction(True):
            rows = self.project.db.execute(
                'SELECT id,metadata FROM debug_artifacts WHERE kind=?', (MANIFEST_KIND,)).fetchall()
            candidates = [(int(json.loads(item['metadata']).get('revision', -1)), item['id'])
                          for item in rows
                          if json.loads(item['metadata']).get('history_id') == manifest['id']]
            expected_parent = manifest.get('parent_manifest')
            if candidates:
                current_revision, current_id = max(candidates)
                if current_id != expected_parent or manifest['revision'] != current_revision + 1:
                    raise ValueError('History DAG changed concurrently; no new operation was dispatched')
            elif expected_parent is not None or manifest['revision'] != 1:
                raise ValueError('History manifest parent is missing; refusing to fork from stale state')
            artifact = self.project._debug_artifact(self.run_id,
                f"rewind-{manifest['id'][:12]}-{manifest['revision']:06d}.json",
                MANIFEST_KIND, data, dict(format=FORMAT, history_id=manifest['id'],
                    revision=manifest['revision'], manifest_sha256=digest,
                    host_files_restored=False))
        manifest['_artifact_id'] = artifact['artifact']
        fingerprint = self._history_live_fingerprint()
        self._qemu_history_live = dict(history=manifest['_artifact_id'], history_id=manifest['id'],
            cursor=manifest.get('cursor'), valid=manifest.get('live_cursor_valid', False),
            invalid_reason=manifest.get('invalid_reason'), fingerprint=fingerprint)
        return artifact

    def _history_new_revision(self, manifest, *, pending=None, **updates):
        new = deepcopy(manifest)
        new.pop('_artifact_id', None)
        new['revision'] += 1
        new['parent_manifest'] = manifest.get('_artifact_id')
        new['pending'] = deepcopy(pending)
        new.update(deepcopy(updates))
        self._validate_manifest(new)
        artifact = self._history_publish(new, reason='revision')
        return new, artifact

    def _history_checkpoint(self, *, remaining_bytes, node_name):
        limit = min(MAX_STATE, max(1, remaining_bytes))
        disk_before = self._history_disk_bytes()
        result = self.save_state(node_name, max_bytes=limit)
        disk_after = self._history_disk_bytes()
        if (not isinstance(result, dict) or not isinstance(result.get('artifact'), str)
                or not _hex_digest(result.get('sha256')) or type(result.get('size')) is not int
                or not 1 <= result['size'] <= limit):
            raise ValueError('Process checkpoint did not return a valid bounded artifact receipt')
        row = self.project.db.execute('SELECT kind,sha256,metadata FROM debug_artifacts WHERE id=?',
                                      (result['artifact'],)).fetchone()
        if row is None or row['kind'] != 'state' or row['sha256'] != result['sha256']:
            raise ValueError('Checkpoint artifact readback differs from its returned receipt')
        meta = json.loads(row['metadata'])
        from .qemu_dos_checkpoint import FORMAT as PROCESS_FORMAT
        if meta.get('format') != PROCESS_FORMAT or meta.get('host_files_restored') is not False:
            raise ValueError('History requires the complete native process checkpoint format')
        return dict(artifact=result['artifact'], sha256=result['sha256'], size=result['size'],
                    live_disk_bytes_before=disk_before, live_disk_bytes_after=disk_after,
                    live_disk_bytes_growth=(None if disk_before is None or disk_after is None
                                            else max(0, disk_after - disk_before)))

    def _history_capacity(self, manifest, parent, count):
        """Conservatively reserve enough for at least another comparable state."""
        used = sum(row['checkpoint']['size'] for row in manifest['nodes'])
        remaining_history = manifest['max_bytes'] - used
        live_disk = self._history_disk_bytes() or 0
        minimum = max(4096, min(MAX_STATE, max(parent['checkpoint']['size'], live_disk)))
        project_used = self.project.db.execute(
            'SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0]
        remaining_project = 256 * 1024 * 1024 - int(project_used)
        needed = minimum * count
        if remaining_history < needed:
            raise ValueError('History byte budget cannot reserve the next full checkpoint before execution')
        if remaining_project < needed:
            raise ValueError('Project artifact budget cannot reserve the next full checkpoint before execution')
        return used

    def _history_resolve_known_stop(self, stop, reason, *, records=(), requested_count=None):
        live = getattr(self, '_qemu_history_live', None)
        manifest, _ = self._history_row(live['history'])
        manifest['pending'] = None
        manifest['cursor'] = None
        manifest['live_cursor_valid'] = False
        manifest['invalid_reason'] = reason
        manifest['last_stop'] = deepcopy(stop)
        new, artifact = self._history_new_revision(manifest)
        result = self._history_summary(new, artifact['artifact'])
        result.update(requested_count=requested_count, recorded_count=len(records),
                      records=deepcopy(list(records)), stop=deepcopy(stop))
        return result

    @staticmethod
    def _node(manifest, node_id):
        return next((node for node in manifest['nodes'] if node['id'] == node_id), None)

    @staticmethod
    def _ancestors(manifest, node_id):
        by_id = {row['id']: row for row in manifest['nodes']}
        out = []
        while node_id is not None:
            node = by_id.get(node_id)
            if node is None:
                raise ValueError('History lineage contains a missing parent')
            out.append(node)
            node_id = node['parent']
        return out

    def _history_state_artifact(self, checkpoint):
        row = self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                                      (checkpoint['artifact'],)).fetchone()
        if (row is None or row['kind'] != 'state' or row['version'] != self.version['id']
                or row['sha256'] != checkpoint['sha256'] or len(row['data']) != checkpoint['size']
                or _sha(bytes(row['data'])) != checkpoint['sha256']):
            raise ValueError('History checkpoint artifact is missing or corrupt')
        meta = json.loads(row['metadata'])
        from .qemu_dos_checkpoint import FORMAT as PROCESS_FORMAT
        if (meta.get('format') != PROCESS_FORMAT or meta.get('host_files_restored') is not False
                or meta.get('source_sha256') != self.metadata['source_sha256']
                or meta.get('version_sha256') != self.metadata['version_sha256']):
            raise ValueError('History node is not a full native DOS process checkpoint')
        return row

    def _history_summary(self, manifest, artifact=None):
        cursor = manifest.get('cursor')
        total_bytes = sum(node['checkpoint']['size'] for node in manifest['nodes'])
        result = self._history_base_response()
        result.update(history=artifact or manifest.get('_artifact_id'), history_id=manifest['id'],
            revision=manifest['revision'], parent_manifest=manifest.get('parent_manifest'),
            valid=bool(manifest.get('live_cursor_valid')),
            invalid_reason=manifest.get('invalid_reason'), cursor=cursor,
            head=manifest.get('head'), retained_nodes=len(manifest['nodes']),
            captures_used=len(manifest['nodes']), state_bytes_used=total_bytes,
            max_steps=manifest['max_steps'], max_bytes=manifest['max_bytes'],
            pending=deepcopy(manifest.get('pending')),
            node_ids=[node['id'] for node in manifest['nodes']],
            nodes=[dict(id=node['id'], parent=node['parent'], edge=deepcopy(node['edge']),
                        checkpoint=deepcopy(node['checkpoint'])) for node in manifest['nodes']])
        result['captures_used'] = result['retained_nodes']
        result['node'] = result['cursor']
        result['history_artifact'] = result['history']
        return result

    @contextmanager
    def _history_internal(self):
        old = getattr(self, '_history_busy', False)
        self._history_busy = True
        try:
            yield
        finally:
            self._history_busy = old

    @_history_operation
    def rewind_start(self, max_steps=16, max_bytes=536870912, *, history=None, timeout_ms=60000):
        _positive_int(max_steps, 'max_steps', 1, MAX_NODES)
        _positive_int(max_bytes, 'max_bytes', 1, MAX_HISTORY_BYTES)
        self._history_supported()
        self._stopped()
        identity = self._history_identity()
        if history is not None:
            manifest, row = self._history_latest(history)
            same_live = (getattr(self, '_qemu_history_live', None) or {}).get('history_id') == manifest['id']
            live = getattr(self, '_qemu_history_live', None) if same_live else None
            valid = bool(live and live.get('valid')
                and live.get('history') == manifest.get('_artifact_id')
                and live.get('fingerprint') == self._history_live_fingerprint())
            self._qemu_history_live = dict(history=manifest.get('_artifact_id') or history,
                history_id=manifest['id'], cursor=live.get('cursor') if valid else None,
                valid=valid, invalid_reason=None if valid
                else 'attached history is not bound to the current live machine',
                fingerprint=live.get('fingerprint') if live else None)
            summary = self._history_summary(manifest, manifest.get('_artifact_id') or history)
            summary['cursor'] = self._qemu_history_live['cursor']
            summary['node'] = summary['cursor']
            summary['valid'] = self._qemu_history_live['valid']
            summary['invalid_reason'] = self._qemu_history_live['invalid_reason']
            return summary
        if self._process.get('state') != 'active' or self._process.get('machine_closed'):
            raise ValueError('History requires a live owned DOS process')
        self._history_admission()
        project_used = int(self.project.db.execute(
            'SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if 256 * 1024 * 1024 - project_used < min(MAX_STATE, max_bytes):
            raise ValueError('Project artifact budget cannot reserve a full root checkpoint')
        history_id = uuid.uuid4().hex
        manifest = dict(format=FORMAT, id=history_id, revision=0, parent_manifest=None,
            identity=identity, max_steps=max_steps, max_bytes=max_bytes, nodes=[],
            head=None, cursor=None, live_cursor_valid=False, invalid_reason=None,
            pending=dict(kind='root-capture', started=time.time_ns()))
        # Publish intent before requesting a state capture. If completion or
        # receipt persistence is uncertain, this node is never silently retried.
        manifest, first = self._history_new_revision(manifest, pending=manifest['pending'])
        try:
            with self._history_internal():
                checkpoint = self._history_checkpoint(remaining_bytes=max_bytes,
                    node_name=f'history-{history_id[:8]}-root.qcow2')
                node_id = uuid.uuid4().hex
                node = dict(id=node_id, parent=None, checkpoint=checkpoint,
                    edge=dict(kind='root', completed_instruction=False),
                    registers=self.registers(), created=time.time_ns())
                manifest['nodes'].append(node)
                manifest['head'] = manifest['cursor'] = node_id
                manifest['live_cursor_valid'] = True
                manifest['pending'] = None
                manifest['invalid_reason'] = None
                new, artifact = self._history_new_revision(manifest)
                return self._history_summary(new, artifact['artifact'])
        except BaseException:
            self.close()
            raise

    @_history_operation
    def rewind_status(self, *, history=None):
        result = self._history_base_response()
        live = getattr(self, '_qemu_history_live', None)
        selected = history or (live.get('history') if live else None)
        if selected is None:
            result.update(history=None, history_id=None, revision=0, valid=False,
                          cursor=None, head=None, retained_nodes=0, captures_used=0,
                          state_bytes_used=0, invalid_reason='not_started')
            return result
        manifest, row = self._history_latest(selected)
        live = getattr(self, '_qemu_history_live', None)
        summary = self._history_summary(manifest, manifest.get('_artifact_id') or selected)
        if live and live.get('history_id') == manifest['id']:
            valid = bool(live.get('valid') and not self.closed
                and live.get('history') == manifest.get('_artifact_id')
                and live.get('fingerprint') == self._history_live_fingerprint())
            summary.update(cursor=live.get('cursor') if valid else None,
                node=live.get('cursor') if valid else None, valid=valid,
                invalid_reason=(None if valid else live.get('invalid_reason')
                    or 'live owner, epoch or history revision changed'))
        else:
            summary.update(cursor=None, node=None, valid=False,
                invalid_reason='history is not bound to this live machine')
        return summary

    @_history_operation
    def rewind_record(self, count=1, timeout_ms=60000, *, advance='step'):
        _positive_int(count, 'count', 1, MAX_NODES)
        if advance not in ('step', 'capture'):
            raise ValueError("advance must be 'step' or 'capture'")
        if advance == 'capture' and count != 1:
            raise ValueError('Explicit checkpoint capture records one stopped boundary')
        self._history_supported()
        live = getattr(self, '_qemu_history_live', None)
        if not live:
            raise ValueError('Start or attach to a history before recording')
        manifest, _ = self._history_latest(live['history'])
        if live.get('history') != manifest.get('_artifact_id'):
            raise ValueError('History revision changed in another session; attach to its latest manifest first')
        fingerprint = self._history_live_fingerprint()
        prior_fingerprint = live.get('fingerprint')
        if (prior_fingerprint and prior_fingerprint.get('process_nonce_sha256')
                != fingerprint.get('process_nonce_sha256')):
            raise ValueError('History belongs to a different DOS process nonce')
        live_valid = bool(live.get('valid') and live.get('cursor') == manifest.get('cursor')
                          and prior_fingerprint == fingerprint)
        if not manifest.get('cursor') or (advance == 'step' and not live_valid):
            raise ValueError('History has no valid live cursor; explicitly restore a node or start a new history')
        if manifest.get('pending') is not None:
            raise ValueError('History has an unresolved operation; do not replay it')
        cursor = manifest['cursor']
        parent = self._node(manifest, cursor)
        if parent is None:
            raise ValueError('History cursor node is missing')
        if len(manifest['nodes']) + count > manifest['max_steps']:
            raise ValueError('History capture budget exhausted; earlier nodes remain available')
        used = self._history_capacity(manifest, parent, count)
        self._stopped()
        if advance == 'step' and (getattr(self, '_qemu_hook_pending', None) is not None
                                  or getattr(self, '_qemu_hook_pending_task', None) is not None):
            raise ValueError('A pending hook must be resolved before history stepping')
        self._history_admission()
        records = []
        with self._history_internal():
            for _ in range(count):
                if advance == 'step':
                    self._history_pending(manifest, parent['id'], 'step')
                    try:
                        step_result = self.step(timeout_ms=self._history_remaining_ms())
                    except BaseException:
                        self.close()
                        raise
                    outcome = step_result.get('outcome') if isinstance(step_result, dict) else None
                    if not isinstance(step_result, dict) or not isinstance(outcome, str):
                        # An execution outcome outside the checkpoint contract is
                        # retained only as unresolved evidence; never replay it.
                        self.close()
                        raise ValueError('History step returned no inspectable native stop receipt')
                    if outcome != 'step' and (outcome in ('exited', 'guest_exit', 'guest_tsr')
                            or self.closed or self.vm is None or self.vm.process.poll() is not None
                            or self._process.get('state') in ('exited', 'session_closed', 'observation_failed')):
                        try:
                            return self._history_resolve_known_stop(step_result,
                                'guest reached a non-checkpointable terminal stop',
                                records=records, requested_count=count)
                        except BaseException:
                            self.close()
                            raise
                    edge = dict(kind='step' if outcome == 'step' else 'stopped',
                                outcome=outcome, completed_instruction=None,
                                stop=deepcopy(step_result))
                    if outcome != 'step':
                        try:
                            self._history_pending(manifest, parent['id'], 'stopped-checkpoint',
                                                  receipt=step_result)
                        except BaseException:
                            self.close()
                            raise
                else:
                    step_result = None
                    edge = dict(kind='capture', completed_instruction=None,
                                label='unobserved interval; no instruction-completion claim')
                    self._history_pending(manifest, parent['id'], 'capture')
                try:
                    remaining = manifest['max_bytes'] - used
                    checkpoint = self._history_checkpoint(remaining_bytes=remaining,
                        node_name=f"history-{manifest['id'][:8]}-{len(manifest['nodes']) + 1:04d}.qcow2")
                    used += checkpoint['size']
                    node_id = uuid.uuid4().hex
                    node = dict(id=node_id, parent=parent['id'], checkpoint=checkpoint,
                        edge=edge, registers=self.registers(), created=time.time_ns())
                    manifest['nodes'].append(node)
                    manifest['head'] = manifest['cursor'] = node_id
                    manifest['live_cursor_valid'] = True
                    manifest['invalid_reason'] = None
                    manifest['pending'] = None
                    manifest, artifact = self._history_new_revision(manifest)
                except BaseException:
                    self.close()
                    raise
                records.append(dict(node=node_id, parent=parent['id'], checkpoint=checkpoint,
                                    edge=edge, history=artifact['artifact']))
                parent = node
                if edge['kind'] != 'step':
                    break
        return dict(self._history_summary(manifest), requested_count=count,
                    recorded_count=len(records), records=records)

    def _history_remaining_ms(self):
        deadline = getattr(self, '_rpc_deadline', None)
        if deadline is None:
            return 60000
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('QEMU history outer deadline expired')
        return min(60000, remaining)

    def _history_pending(self, manifest, node, kind, *, receipt=None):
        intent = dict(kind=kind, parent=node, started=time.time_ns())
        if receipt is not None:
            intent['receipt'] = deepcopy(receipt)
        pending, artifact = self._history_new_revision(manifest, pending=intent)
        manifest.clear()
        manifest.update(pending)
        self._qemu_history_live = dict(history=artifact['artifact'], history_id=manifest['id'],
            cursor=manifest.get('cursor'), valid=manifest.get('live_cursor_valid', False),
            invalid_reason=manifest.get('invalid_reason'),
            fingerprint=self._history_live_fingerprint())

    @_history_operation
    def rewind(self, count=1, *, history=None, node=None, timeout_ms=60000):
        _positive_int(count, 'count', 1, MAX_NODES)
        self._history_supported()
        live = getattr(self, '_qemu_history_live', None)
        selected = history or (live.get('history') if live else None)
        if selected is None:
            raise ValueError('Select a stored history manifest before restoring')
        manifest, _ = self._history_latest(selected)
        if manifest.get('pending') is not None:
            raise ValueError('History has an unresolved operation and cannot be restored')
        if node is not None:
            if not isinstance(node, str):
                raise ValueError('node must be a history node ID')
            target = self._node(manifest, node)
            if target is None:
                raise ValueError('Selected history node is not present in this manifest')
        else:
            same_live = live is not None and live.get('history_id') == manifest['id']
            if history is not None and (not same_live or not live.get('valid')):
                cursor = manifest.get('head')
            else:
                if (not same_live or not live.get('valid') or not live.get('cursor')
                        or live.get('cursor') != manifest.get('cursor')
                        or live.get('fingerprint') != self._history_live_fingerprint()):
                    raise ValueError('History live cursor is invalid; supply an explicit node')
                cursor = live['cursor']
            ancestors = self._ancestors(manifest, cursor)
            if count >= len(ancestors):
                raise ValueError('Rewind count exceeds the available parent lineage')
            target = ancestors[count]
        self._history_state_artifact(target['checkpoint'])
        self._stopped()
        self._history_admission()
        self._history_pending(manifest, target['id'], 'restore')
        pending_manifest, pending_row = self._history_row(self._qemu_history_live['history'])
        try:
            with self._history_internal():
                restored = self.load_state(target['checkpoint']['artifact'],
                                           timeout_ms=self._history_remaining_ms())
                if self.closed or not isinstance(restored, dict) or restored.get('source_binding_restored') is not True:
                    raise ValueError('Restored checkpoint did not verify process source ownership')
                current = self.registers()
                expected = target.get('registers')
                if not isinstance(expected, dict) or any(current.get(key) != expected.get(key)
                        for key in ('registers', 'general', 'segments', 'instruction_pointer',
                                    'linear_pc', 'flags', 'cpu_mode', 'address_state')):
                    raise ValueError('Restored CPU readback differs from the selected history node')
                pending_manifest['cursor'] = target['id']
                pending_manifest['live_cursor_valid'] = True
                pending_manifest['invalid_reason'] = None
                pending_manifest['pending'] = None
                new, artifact = self._history_new_revision(pending_manifest)
                return dict(self._history_summary(new, artifact['artifact']),
                    rewound_count=count, target_node=target['id'],
                    target_checkpoint=deepcopy(target['checkpoint']), restore=restored)
        except BaseException:
            # Load implementations close the owner on partial restoration. A
            # later failure is also uncertain, so never retry or replay it.
            self.close()
            raise
