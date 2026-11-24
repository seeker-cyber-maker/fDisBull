"""Full owned-VM recovery without restoring a DOS executable's source authority.

This archive is deliberately separate from process checkpoints. Its DOS helper
is a completion-channel observer, not proof of the child's allocation lifetime.
Only explicitly native machine controls can cross this recovery boundary.
"""
from __future__ import annotations
from .qemu_ram import high_ram_end, low_ram_end

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid
import zipfile

from .dosbox_rpc import DebuggerError
from .qemu_cpu_undo_guard import full_load

FORMAT = 'fdisbull-qemu-owned-machine-qcow2-v1'
KIND = 'machine-state'
MAX_STATE = 128 * 1024 * 1024
MAX_SIDECAR = 64 * 1024 * 1024


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _archive(machine, bundle):
    raw = _json(bundle)
    if len(raw) > MAX_SIDECAR:
        raise ValueError('Owned machine sidecar exceeds its byte budget')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('machine.qcow2', machine)
        archive.writestr('owned-machine.json', raw)
    return output.getvalue()


def _unarchive(data):
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_STATE:
        raise ValueError('Owned machine checkpoint exceeds its byte budget')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if (len(members) != 2 or {m.filename for m in members} != {'machine.qcow2', 'owned-machine.json'}
                or any(m.compress_type != zipfile.ZIP_STORED or m.flag_bits & 1 for m in members)):
            raise ValueError('Invalid owned machine checkpoint components')
        if (archive.getinfo('owned-machine.json').file_size > MAX_SIDECAR
                or archive.getinfo('machine.qcow2').file_size > MAX_STATE):
            raise ValueError('Owned machine checkpoint component exceeds its byte budget')
        machine = archive.read('machine.qcow2')
        bundle = json.loads(archive.read('owned-machine.json'))
    if not isinstance(bundle, dict) or bundle.get('format') != FORMAT:
        raise ValueError('Unknown owned machine checkpoint format')
    return machine, bundle


def _remaining(deadline):
    milliseconds = int((deadline - time.monotonic()) * 1000)
    if milliseconds < 1:
        raise TimeoutError('Owned machine checkpoint deadline expired')
    return min(600000, milliseconds)


@contextmanager
def _operation(session, timeout_ms):
    from .operation_budget import request_deadline
    owner = session.vm
    deadline = request_deadline(session, timeout_ms)
    bounds = [deadline, getattr(session, '_deadline', None), owner.operation_deadline]
    channels = [owner, *[c for c in (owner.qmp, owner.gdb) if c is not None]]
    previous = [(channel, getattr(channel, 'operation_deadline', None)) for channel in channels]
    deadline = min(bound for bound in bounds + [v for _, v in previous] if bound is not None)
    if not owner.lock.acquire(timeout=min(10, max(0, deadline - time.monotonic()))):
        raise TimeoutError('Owned machine checkpoint lock timed out')
    previous_session = getattr(session, '_deadline', None)
    try:
        _remaining(deadline)
        if session.vm is not owner:
            raise ValueError('Machine owner changed before owned checkpoint admission')
        session._set_deadline(deadline)
        yield owner, deadline
    except BaseException as error:
        # Admission reads can lose their transport before the snapshot's own
        # cleanup scope begins. A plain policy refusal keeps intact ownership.
        if any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
               for channel in (owner.qmp, owner.gdb)):
            _close_uncertain(session, error)
        raise
    finally:
        primary = sys.exception()
        cleanup = []
        try:
            session._set_deadline(previous_session)
        except BaseException as error:
            cleanup.append(error)
        try:
            for channel, value in previous:
                try:
                    channel.operation_deadline = value
                except BaseException as error:
                    cleanup.append(error)
            if owner.gdb is not None and not any(owner.gdb is c for c, _ in previous):
                owner.gdb.operation_deadline = previous[0][1]
        except BaseException as error:
            cleanup.append(error)
        finally:
            owner.lock.release()
        if cleanup:
            if primary is not None:
                primary.checkpoint_budget_cleanup_errors = [type(e).__name__ for e in cleanup]
            else:
                _close_uncertain(session, cleanup[0])
                raise cleanup[0]


def _close_uncertain(session, error, new=None):
    """Retain the first failure even if retirement or native cleanup also fails."""
    if new is not None:
        new._fdisbull_control_quarantine = 'failed owned machine restore'
        try:
            new.close()
        except BaseException as cleanup:
            error.new_machine_cleanup_error = type(cleanup).__name__
    session.vm._fdisbull_control_quarantine = 'uncertain owned machine checkpoint'
    try:
        session.close()
    except BaseException as cleanup:
        error.machine_cleanup_error = type(cleanup).__name__


def _filter_controls(controls):
    if not isinstance(controls, dict) or controls.get('format') != 'fdisbull-qemu-controls-1':
        raise ValueError('Owned machine recovery cannot restore task controls')
    definitions, hooks, points = (controls.get(k) for k in ('definitions', 'hooks', 'breakpoints'))
    if not isinstance(definitions, dict) or not isinstance(hooks, list) or not isinstance(points, list):
        raise ValueError('Invalid owned machine controls')
    for definition in definitions.values():
        binding = definition.get('native_binding') if isinstance(definition, dict) else None
        if (not isinstance(binding, dict) or binding.get('space') not in ('physical', 'linear')
                or 'task_identity' in binding or binding.get('scope') == 'task-private'
                or binding.get('run') != controls.get('run') or binding.get('epoch') != controls.get('epoch')):
            raise ValueError('Owned machine recovery requires explicit native machine layers')
    for hook in hooks:
        if (not isinstance(hook, dict) or hook.get('space') != 'linear'
                or hook.get('task_identity') is not None or hook.get('task_id') is not None
                or hook.get('cs') is not None):
            raise ValueError('Owned machine recovery requires linear machine hooks')
        actions = hook.get('actions')
        if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
            raise ValueError('Invalid owned machine hook actions')
        for action in actions:
            if not isinstance(action, dict) or action.get('op') not in ('layers', 'registers'):
                raise ValueError('Owned machine hook action depends on source or task authority')
            if action['op'] == 'layers' and (set(action) != {'op', 'layers'}
                    or not isinstance(action['layers'], list)
                    or len(action['layers']) > 64
                    or any(not isinstance(layer, str) for layer in action['layers'])
                    or len(set(action['layers'])) != len(action['layers'])
                    or any(layer not in definitions for layer in action['layers'])):
                raise ValueError('Owned machine hook references an unavailable native layer')
    if any(not isinstance(point, dict) or point.get('owner', 'user') != 'user' for point in points):
        raise ValueError('Owned machine recovery cannot serialize automatic observer controls')
    return controls


def _preflight(session):
    from .qemu_dos_checkpoint import _preflight as process_preflight
    if not getattr(session, '_process', None):
        raise ValueError('Owned machine recovery requires a DOS-launched session')
    if any(getattr(session, key, None) is not None for key in
           ('_dos_task_binding', '_dos_task_monitor', '_dos_scheduler', '_dos_save_witness')):
        raise ValueError('Owned machine recovery cannot carry DOS task or provenance owners')
    if getattr(session, '_dos_task_views', None):
        raise ValueError('Owned machine recovery cannot carry task-private views')
    tracker = getattr(session, '_automatic_runtime_tracker', None)
    if (getattr(session, '_automatic_internal_pending', None) is not None
            or tracker is not None and (getattr(tracker, 'internal_breakpoints', None)
                                       or getattr(tracker, 'provider', None) is not None)):
        raise ValueError('Resolve automatic source observers before owned machine recovery')
    # Policy inspection does not capture RAM or conflict with partial-undo
    # recovery. Inactive layers referenced by a hook are included as well.
    hooks = deepcopy(list(getattr(session, '_qemu_hooks', {}).values()))
    ids = set(getattr(session, '_layer_active', ()))
    for hook in hooks:
        for action in hook.get('actions', ()):
            if action.get('op') == 'layers':
                ids.update(action.get('layers', ()))
    _filter_controls(dict(format='fdisbull-qemu-controls-1', run=session.run_id,
        epoch=session._layer_epoch(), definitions={i: session.project.debug_layer_info(i) for i in ids},
        hooks=hooks, breakpoints=[point for key, point in session.breakpoints.items()
                                 if key != session._return_breakpoint]))
    process_preflight(session)


def _native_idle(vm):
    """Check available native observers; task registries use owned-API scope."""
    from .qemu_dos_provenance import query
    witness = query(vm)
    if witness is not None and witness['active']:
        raise ValueError('Owned machine recovery cannot carry a native save observer')
    command = 'x-fdisbull-task-scheduler-observe'
    scheduler = 'unavailable'
    if command in vm.qmp_commands:
        try:
            vm.qmp.call(command)
        except DebuggerError as error:
            prefix = 'QMP ' + command + ': '
            try:
                payload = json.loads(str(error)[len(prefix):]) if str(error).startswith(prefix) else None
            except ValueError:
                payload = None
            if payload != {'class': 'GenericError',
                           'desc': 'FDISBULL_TASK_PRECONDITION: scheduler is not initialized'}:
                raise
            scheduler = 'uninitialized'
        else:
            raise ValueError('Owned machine recovery cannot carry a prepared native scheduler')
    return dict(save_observer='inactive' if witness is not None else 'unavailable',
                scheduler=scheduler,
                task_registry_scope='owned host API registries; not an adversarial guest absence proof')


def _disk_identity(vm):
    """Prove the complete attached writable device set is the owned disk0."""
    blocks = vm.qmp.call('query-block')
    if not isinstance(blocks, list) or any(not isinstance(b, dict) for b in blocks):
        raise ValueError('Malformed native block device inventory')
    inserted = [b['inserted'] for b in blocks if 'inserted' in b]
    if (len(inserted) != 1 or not isinstance(inserted[0], dict)
            or inserted[0].get('node-name') != 'disk0' or inserted[0].get('drv') != 'qcow2'
            or inserted[0].get('ro') is not False):
        raise ValueError('Owned machine recovery requires exactly one writable disk0')
    nodes = vm.qmp.call('query-named-block-nodes')
    if (not isinstance(nodes, list) or len(nodes) != 2
            or any(not isinstance(n, dict) for n in nodes)
            or {n.get('node-name') for n in nodes} != {'disk0', 'fdbfile'}):
        raise ValueError('Owned machine recovery requires a standalone two-node disk0 graph')
    disk = next(n for n in nodes if n['node-name'] == 'disk0')
    file = next(n for n in nodes if n['node-name'] == 'fdbfile')
    image = disk.get('image', {})
    if (disk.get('drv') != 'qcow2' or file.get('drv') != 'file'
            or disk.get('ro') is not False or file.get('ro') is not False
            or image.get('virtual-size') != vm.checkpoint_virtual_size
            or image.get('format') != 'qcow2'
            or any(image.get(k) for k in ('backing-filename', 'full-backing-filename'))
            or Path(file.get('file', '')).resolve() != vm.checkpoint_disk.resolve()):
        raise ValueError('Owned machine disk graph or image identity differs')
    return dict(node='disk0', file_node='fdbfile', format='qcow2',
                virtual_size=vm.checkpoint_virtual_size, attached_writable_devices=1,
                standalone=True)


def _helper(session, origin, vm=None):
    from .qemu_dos_checkpoint import _decode_origin
    vm = session.vm if vm is None else vm
    decoded = _decode_origin(session, origin)
    _, raw, _, _, expected, ready = decoded
    remote = vm.debugger()
    def read(offset, length):
        address = ready['helper_segment'] * 16 + offset
        if not 0 <= address < address + length <= 0xa0000:
            raise ValueError('Owned helper must reside in conventional RAM')
        return remote.memory(address, length, space='physical')
    if read(ready['report_offset'], len(raw)) != raw:
        raise ValueError('Owned machine helper READY identity changed')
    from .dos_process_helper import loader_code_ranges
    if hasattr(session, '_helper_module'):
        loader_code_ranges = session._helper_module().loader_code_ranges
    code = []
    for first, last in loader_code_ranges():
        observed = read(first + 0x100, last - first)
        if observed != expected[first:last]:
            raise ValueError('Owned machine helper executable code changed')
        code.append(dict(offset=first + 0x100, length=last-first, sha256=_sha(observed)))
    return dict(ready_sha256=_sha(raw), code=code,
                parent_psp=ready['helper_psp'], child_psp=ready['child_psp']), decoded


def _ram(vm, registers):
    """Observe two architectural RAM pages without claiming source ownership."""
    from .dos_memory import translate_386_page
    from .qemu_le_translation import translate_linear, require_executable_walks
    from .qemu_dos_source_admission import _integer
    state = registers['address_state']
    if state.get('machine_vcpus') != 1 or state.get('register_context_match') is not True:
        raise ValueError('Owned machine RAM fences require one observed CPU')
    stack_bits = state.get('stack_bits')
    segment = state.get('segments', {}).get('ss', {})
    values = registers['registers']
    if stack_bits not in (16, 32) or 'base' not in segment:
        raise ValueError('Owned machine RAM fences require a supported observed stack')
    sp = values.get('rsp', values.get('esp'))
    if sp is None or registers.get('linear_pc') is None:
        raise ValueError('Owned machine RAM fence addresses are unavailable')
    stack = int(segment['base'], 0) + (int(sp, 0) & ((1 << stack_bits) - 1))
    pages = sorted({int(registers['linear_pc'], 0) & ~4095, stack & ~4095})
    remote = vm.debugger()
    ram_end = low_ram_end(vm.machine_configuration)
    high_end = high_ram_end(vm.machine_configuration)
    def read(address, length):
        if not (0 <= address < address + length <= 0xa0000
                or 0x100000 <= address < address + length <= ram_end
                or high_end is not None and 0x100000000 <= address < address + length <= high_end):
            raise ValueError('Owned machine RAM fence is outside conventional or extended RAM')
        data = remote.memory(address, length, space='physical')
        if not isinstance(data, bytes) or len(data) != length:
            raise DebuggerError('Incomplete owned machine RAM fence')
        return data
    result = []
    for page in pages:
        translation = translate_386_page(page, state, read)
        if translation.get('status') != 'mapped':
            if registers.get('cpu_mode') != 'protected' or state.get('a20') is not True:
                raise ValueError('Owned machine RAM page translation is unsupported')
            try:
                context = {key.lower(): _integer(state['control'][key]) for key in ('CR0', 'CR3', 'CR4', 'EFER')}
            except (KeyError, TypeError, ValueError):
                raise ValueError('Owned machine RAM paging controls are unavailable') from None
            from .qemu_runtime_capture import _qemu_input_hashes
            from .qemu_paged_le_capture import _pse36
            image_hash = _qemu_input_hashes(getattr(vm, 'inputs', {})).get('qemu_image')
            physical, walks = translate_linear(context, page, 4096, read,
                qemu_image_sha256=image_hash, high_ram_end=high_end,
                pse36=_pse36(vm.machine_configuration, image_hash))
            if page == int(registers['linear_pc'], 0) & ~4095:
                require_executable_walks(walks, 4096)
            backing = walks[0]['physical']
            translation = dict(status='mapped', physical_address=hex(backing),
                               page_size=walks[0]['page_size'], walk=walks[0],
                               scope='stopped table walk and byte comparison; active backing identity is not proven')
        else:
            backing = int(translation['physical_address'], 0)
            physical = read(backing, 4096)
        if remote.memory(page, 4096, space='virtual') != physical:
            raise ValueError('Owned machine physical and virtual RAM fences differ')
        result.append(dict(linear=page, physical=backing, length=4096,
                           hex=physical.hex(), sha256=_sha(physical), translation=translation))
    return result


def _cpu_equal(actual, expected):
    for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
        if actual.get(field) != expected.get(field):
            raise DebuggerError('Owned machine CPU differs: ' + field)


def _validate_controls(project, controls, version, machine):
    from .qemu_checkpoint_controls import _unpack, _derive
    _filter_controls(controls)
    if ('task_identity' in controls or controls.get('pending_task') is not None
            or any('task_identity' in item for item in controls['hooks'])):
        raise ValueError('Owned machine controls contain an unbound task identity')
    selected = project.version(version)
    if (controls.get('source_sha256') != project.meta['source_sha256']
            or controls.get('version') != version
            or controls.get('version_sha256') != selected['sha256']):
        raise ValueError('Owned machine controls differ from source provenance or version')
    definitions = controls['definitions']
    active = controls.get('active')
    if (not isinstance(active, list) or len(active) > 64 or len(set(active)) != len(active)
            or any(i not in definitions for i in active) or len(definitions) > 256
            or any(project.debug_layer_info(i) != definition or definition['version'] != version
                   for i, definition in definitions.items())):
        raise ValueError('Owned machine layer definitions differ from their project identities')
    maps = controls.get('maps')
    if not isinstance(maps, dict) or set(maps) != {'ram_base', 'ram_applied', 'exec_base', 'exec'}:
        raise ValueError('Invalid owned machine control maps')
    decoded = {name: _unpack(rows) for name, rows in maps.items()}
    observed = _unpack(controls.get('observed'))
    if (decoded['ram_base'].keys() != decoded['ram_applied'].keys()
            or decoded['exec_base'].keys() != decoded['exec'].keys()
            or observed.keys() != decoded['ram_applied'].keys() | decoded['exec'].keys()):
        raise ValueError('Owned machine control byte extents differ')
    def extent(address, length):
        end = address + length
        if not (0 <= address < end <= 0xa0000
                or 0x100000 <= address < end <= low_ram_end(machine)):
            raise ValueError('Owned machine control extent is outside supported RAM')
    bounds = SimpleNamespace(_layer_ram_extent=extent, _dos_task_binding=None)
    for identifier in definitions:
        _derive(bounds, [identifier], definitions, controls['run'], controls['epoch'])
    expected, ram, execute = _derive(bounds, active, definitions, controls['run'], controls['epoch'])
    if (decoded['ram_applied'] != ram or decoded['exec'] != execute
            or decoded['ram_base'] != {a: expected[a] for a in ram}
            or decoded['exec_base'] != {a: ram.get(a, expected[a]) for a in execute}
            or any(observed[a] != byte for a, byte in decoded['exec_base'].items())):
        raise ValueError('Owned machine layer maps differ from their definitions')
    hooks, points = controls['hooks'], controls['breakpoints']
    if len(hooks) + len(points) > 256:
        raise ValueError('Owned machine control point budget exceeded')
    identifiers = [point.get('id') for point in points]
    hook_ids = [hook.get('hook') for hook in hooks]
    if (any(not isinstance(i, str) for i in identifiers + hook_ids)
            or len(set(identifiers)) != len(identifiers) or len(set(hook_ids)) != len(hook_ids)
            or controls.get('pending_hook') not in (None, *hook_ids)):
        raise ValueError('Invalid owned machine control identifiers')
    for point in points + hooks:
        address = point.get('runtime_address') if 'hook' in point else point.get('address')
        if (type(address) is not int or not 0 <= address <= 0xffffffff
                or point.get('access') not in ('x', 'r', 'w', 'rw')
                or type(point.get('length')) is not int or not 1 <= point['length'] <= 65536
                or point['access'] == 'x' and point['length'] != 1):
            raise ValueError('Invalid owned machine breakpoint extent')
    for hook in hooks:
        if (any(key not in hook for key in ('address', 'cs', 'space', 'runtime_address', 'access',
                                           'length', 'once', 'max_hits', 'hits', 'actions', 'epoch', 'hook'))
                or hook['cs'] is not None
                or type(hook['address']) is not int and not isinstance(hook['address'], str)
                or hook.get('epoch') != controls.get('epoch') or type(hook.get('once')) is not bool
                or type(hook.get('hits')) is not int or type(hook.get('max_hits')) is not int
                or not 0 <= hook['hits'] < hook['max_hits'] <= 1000):
            raise ValueError('Invalid owned machine hook lifetime')
        address = int(hook['address'], 0) if isinstance(hook['address'], str) else hook['address']
        if address != hook['runtime_address']:
            raise ValueError('Owned machine hook address differs from its native linear site')
        for action in hook['actions']:
            if action['op'] == 'registers':
                edits = action.get('registers')
                if set(action) != {'op', 'registers'} or not isinstance(edits, dict) or not edits:
                    raise ValueError('Invalid owned machine register hook action')
                for name, change in edits.items():
                    if (not isinstance(name, str) or name.lower() in ('cs', 'eip', 'rip', 'ip')
                            or not isinstance(change, dict) or set(change) != {'expected', 'value'}):
                        raise ValueError('Invalid owned machine guarded register action')
                    for value in change.values():
                        if type(value) is not int and not isinstance(value, str):
                            raise ValueError('Invalid owned machine register value')
                        if (int(value, 0) if isinstance(value, str) else value) < 0:
                            raise ValueError('Invalid owned machine register value')
    sites = [(p.get('runtime_address', p.get('address')), p['access'], p['length']) for p in points + hooks]
    if len(sites) != len(set(sites)):
        raise ValueError('Owned machine controls contain duplicate native sites')


def _read_artifact(project, artifact, version=None):
    """Validate durable archive/provenance without consulting a live VM."""
    from .qemu_checkpoint import validate_qcow_header
    if not isinstance(artifact, str) or not artifact:
        raise ValueError('Owned machine artifact ID must be nonempty')
    row = project.db.execute(
        'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
        (artifact,)).fetchone()
    if row is None or row['kind'] != KIND or version is not None and row['version'] != version:
        raise ValueError('Owned machine state must belong to the selected project version')
    data = bytes(row['data']); metadata = json.loads(row['metadata'])
    if _sha(data) != row['sha256']:
        raise ValueError('Stored owned machine checkpoint hash differs')
    machine, bundle = _unarchive(data)
    selected = project.version(row['version'])
    expected = dict(format=FORMAT, source_sha256=project.meta['source_sha256'],
                    version_sha256=selected['sha256'], source_binding_restored=False)
    if (any(bundle.get(k) != v or metadata.get(k) != v for k, v in expected.items())
            or bundle.get('source_binding_restored') is not False
            or metadata.get('source_binding_restored') is not False
            or metadata.get('host_files_restored') is not False
            or not isinstance(metadata.get('checkpoint_scope'), str)
            or bundle.get('version') != row['version']
            or metadata.get('sidecar_sha256') != _sha(_json(bundle))
            or bundle.get('machine_sha256') != _sha(machine)):
        raise ValueError('Owned machine archive or provenance identity differs')
    required = {'tag': str, 'runtime': dict, 'runtime_origin': dict, 'process_provenance': dict,
                'origin': dict, 'registers': dict, 'ram': list, 'helper': dict, 'serial': dict,
                'disk': dict, 'controls': dict, 'parent_return_observer': bool, 'native_idle': dict}
    if any(type(bundle.get(key)) is not typ for key, typ in required.items()):
        raise ValueError('Malformed owned machine checkpoint sidecar')
    if ('instrumentation' not in bundle or 'native_task' not in bundle
            or not isinstance(bundle['process_provenance'].get('source_mapping'), dict)
            or not isinstance(bundle['process_provenance'].get('capture_epoch'), str)
            or not isinstance(bundle['runtime'].get('machine'), dict)):
        raise ValueError('Malformed owned machine native state declarations')
    if (not 1 <= len(bundle['tag']) <= 100 or any(c not in
            'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in bundle['tag'])
            or bundle['controls'].get('epoch') != bundle['process_provenance'].get('capture_epoch')):
        raise ValueError('Owned machine tag or control origin differs')
    memory_mib = bundle['runtime']['machine'].get('memory_mib')
    if type(memory_mib) is not int or not 1 <= memory_mib <= 4096:
        raise ValueError('Invalid owned machine RAM size')
    _validate_controls(project, bundle['controls'], selected['id'], bundle['runtime']['machine'])
    cpu = bundle['registers']; state = cpu.get('address_state')
    if (cpu.get('cpu_mode') not in ('real', 'protected', 'v86') or not isinstance(state, dict)
            or state.get('machine_vcpus') != 1 or state.get('register_context_match') is not True
            or state.get('stack_bits') not in (16, 32) or not isinstance(cpu.get('registers'), dict)):
        raise ValueError('Unsupported saved owned machine CPU')
    if not 1 <= len(bundle['ram']) <= 2:
        raise ValueError('Invalid owned machine RAM fence count')
    machine_config = bundle['runtime']['machine']
    ram_end = low_ram_end(machine_config)
    high_end = high_ram_end(machine_config)
    for fence in bundle['ram']:
        if (not isinstance(fence, dict) or type(fence.get('linear')) is not int
                or type(fence.get('physical')) is not int or fence.get('length') != 4096
                or not 0 <= fence['linear'] <= 0xfffff000 or fence['linear'] & 4095
                or fence['physical'] & 4095
                or not (0 <= fence['physical'] < fence['physical'] + 4096 <= 0xa0000
                        or 0x100000 <= fence['physical'] < fence['physical'] + 4096 <= ram_end
                        or high_end is not None and 0x100000000 <= fence['physical']
                        < fence['physical'] + 4096 <= high_end)
                or not isinstance(fence.get('hex'), str) or len(fence['hex']) != 8192
                or _sha(bytes.fromhex(fence['hex'])) != fence.get('sha256')
                or not isinstance(fence.get('translation'), dict)):
            raise ValueError('Invalid owned machine RAM fence')
    from .qemu_instrumented_checkpoint import _decode
    instrumentation = bundle['instrumentation']
    virtual = bundle['runtime']['machine'].get('clock_profile', {}).get('profile') == 'virtual'
    if virtual != (instrumentation is not None):
        raise ValueError('Owned machine instrumentation profile differs')
    if instrumentation is not None:
        _decode(instrumentation)
    native_task = bundle['native_task']
    if native_task is not None:
        from .qemu_dos_tasks import COMMAND, read_task_context, validate_register_context
        if not isinstance(native_task, dict) or any(k in native_task for k in ('anchor-address', 'anchor-hex')):
            raise ValueError('Invalid unbound owned machine architectural context')
        # Reuse the native receipt validator on supplied data, without I/O.
        replay = SimpleNamespace(qmp_commands={COMMAND},
                                 qmp=SimpleNamespace(call=lambda *args: native_task))
        try:
            validate_register_context(read_task_context(replay), cpu)
        except (ValueError, DebuggerError) as error:
            raise ValueError('Invalid owned machine architectural context') from error
    origin = bundle['origin']
    from . import dos_workspace_helper, dos_process_helper
    helper_api = dos_workspace_helper if 'workspace' in bundle else dos_process_helper
    try:
        nonce, ready, tail = (bytes.fromhex(origin[k]) for k in ('nonce', 'ready', 'command_tail'))
        helper = helper_api.build_loader(origin['target'], tail, nonce)
        report = helper_api.parse_report(ready, nonce)
        if (_sha(helper) != origin['helper_sha256'] or len(bytes.fromhex(origin['vectors_before'])) != 1024
                or 'process_disk' not in origin or report['type'] != 'ready'
                or bundle['process_provenance'].get('psp_segment') != report['child_psp']
                or bundle['process_provenance'].get('parent_psp_segment') != report['helper_psp']):
            raise ValueError('Owned machine helper origin differs')
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Invalid owned machine helper provenance') from error
    if (type(bundle['disk'].get('virtual_size')) is not int
            or bundle['disk'] != dict(node='disk0', file_node='fdbfile', format='qcow2',
                virtual_size=bundle['disk']['virtual_size'], attached_writable_devices=1, standalone=True)):
        raise ValueError('Invalid owned machine disk declaration')
    validate_qcow_header(machine[:104], bundle['disk']['virtual_size'])
    if 'workspace' in bundle:
        from .qemu_workspace import validate_workspace
        validate_workspace(project, bundle['workspace'], selected['id'])
        if bundle['workspace'].get('qcow_sha256') != _sha(machine):
            raise ValueError('Owned machine workspace image hash differs')
    return row, metadata, machine, bundle


def inspect_owned_machine_state(project, artifact):
    """Read and validate an owned archive without a VM or source authority."""
    row, metadata, machine, bundle = _read_artifact(project, artifact)
    return dict(artifact=artifact, kind=KIND, format=FORMAT, sha256=row['sha256'], size=len(row['data']),
        version=row['version'], source_sha256=bundle['source_sha256'],
        version_sha256=bundle['version_sha256'], source_binding_restored=False,
        checkpoint_scope=metadata['checkpoint_scope'], machine_sha256=_sha(machine),
        controls=dict(layers=len(bundle['controls']['active']), hooks=len(bundle['controls']['hooks']),
                      breakpoints=len(bundle['controls']['breakpoints'])),
        workspace_present='workspace' in bundle, instrumentation_present=bundle.get('instrumentation') is not None,
        metadata=deepcopy(metadata),
        components=[dict(name='machine.qcow2', size=len(machine)),
                    dict(name='owned-machine.json', size=len(_json(bundle)))],
        host_files_restored=False)


def _capture(session, name, max_bytes, deadline):
    from .external_files import _file_name
    from .qemu_checkpoint import snapshot_job, validate_qcow_header
    from .qemu_checkpoint_controls import capture_controls
    from .qemu_dos_checkpoint import _serial_idle, _origin, _compatibility, _source
    from .qemu_dos_tasks import capture_task_checkpoint
    from .qemu_instrumented_checkpoint import capture, verify_saved
    _file_name(name)
    if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= MAX_STATE):
        raise ValueError('Owned machine byte budget must be 1..134217728')
    limit = max_bytes or MAX_STATE
    _preflight(session)
    _source(session)  # Original-file provenance only; never module RAM ownership.
    disk = _disk_identity(session.vm)
    native_idle = _native_idle(session.vm)
    serial = _serial_idle(session)
    origin = _origin(session)
    helper, _ = _helper(session, origin)
    reserved = session._return_breakpoint
    ready = session._ready
    expected = dict(address=ready['helper_segment'] * 16 + ready['exit_wait_ip'],
                    kind=1, length=1, access='x', owner='user')
    if reserved is not None and session.breakpoints.get(reserved) != expected:
        raise ValueError('Owned machine parent-return observer identity differs')
    controls = _filter_controls(capture_controls(session))
    registers = session.registers()
    ram = _ram(session.vm, registers)
    native_task = capture_task_checkpoint(session)
    instrumentation, token = capture(session)
    _remaining(deadline)
    tag = 'fdb-owned-' + uuid.uuid4().hex
    bundle = dict(format=FORMAT, tag=tag, source_sha256=session.metadata['source_sha256'],
        version=session.version['id'], version_sha256=session.metadata['version_sha256'],
        runtime=_compatibility(session), runtime_origin=deepcopy(session.vm.inputs),
        process_provenance=deepcopy(session._process), origin=origin, registers=registers,
        ram=ram, helper=helper, serial=serial, disk=disk, native_idle=native_idle, controls=controls,
        native_task=native_task, instrumentation=instrumentation,
        source_binding_restored=False, parent_return_observer=reserved is not None)
    try:
        snapshot_job(session.vm, 'save', tag=tag, vmstate='disk0', devices=['disk0'],
                     timeout_ms=_remaining(deadline), instrumented=instrumentation is not None,
                     export_token=token)
        _cpu_equal(session.registers(), registers)
        if (_ram(session.vm, registers) != ram or _helper(session, origin)[0] != helper
                or _serial_idle(session) != serial or _disk_identity(session.vm) != disk
                or _native_idle(session.vm) != native_idle
                or capture_controls(session) != controls or capture_task_checkpoint(session) != native_task):
            raise DebuggerError('Owned machine state changed during checkpoint capture')
        verify_saved(session, instrumentation)
        with session.vm.checkpoint_disk.open('rb') as stream:
            machine = stream.read(limit + 1)
        if len(machine) > limit:
            raise ValueError('Owned machine checkpoint exceeds its byte budget')
        validate_qcow_header(machine[:104], session.vm.checkpoint_virtual_size)
        bundle['machine_sha256'] = _sha(machine)
        if getattr(session, '_dos_workspace_enabled', False):
            from .qemu_workspace import checkpoint_workspace
            bundle['workspace'] = checkpoint_workspace(session, machine)
        data = _archive(machine, bundle)
        if len(data) > limit:
            raise ValueError('Owned machine archive exceeds its byte budget')
        _remaining(deadline)
        metadata = dict(format=FORMAT, source_sha256=bundle['source_sha256'],
            version_sha256=bundle['version_sha256'], origin_run=session.run_id,
            sidecar_sha256=_sha(_json(bundle)), source_binding_restored=False,
            checkpoint_scope='owned native machine and private disk; no DOS/LE source ownership',
            host_files_restored=False)
        return dict(name=name, kind=KIND, data=data, metadata=metadata,
                    sha256=_sha(data), size=len(data))
    except BaseException as error:
        _close_uncertain(session, error)
        raise


def capture_owned_machine_state(session, name='owned-machine.qcow2', max_bytes=None):
    with _operation(session, 30000) as (_, deadline):
        return _capture(session, name, max_bytes, deadline)


def save_owned_machine_state(session, name='owned-machine.qcow2', max_bytes=None):
    with _operation(session, 30000) as (_, deadline):
        captured = _capture(session, name, max_bytes, deadline)
        try:
            saved = session._artifact(captured['name'], captured['kind'], captured['data'], captured['metadata'])
            _remaining(deadline)
            return saved
        except BaseException as error:
            _close_uncertain(session, error)
            raise


@full_load
def load_owned_machine_state(session, artifact, timeout_ms=60000, rebind_protected_source=False):
    return _load_owned_machine_state(session, artifact, timeout_ms,
                                    rebind_protected_source=rebind_protected_source)


def _load_owned_machine_state(session, artifact, timeout_ms=60000, rebind_protected_source=False,
                              *, _le_checkpoint=None):
    """Trusted full-loader body; its caller must own a full_load scope."""
    if not getattr(session, '_qemu_cpu_delta_full_load_depth', 0):
        raise ValueError('Owned machine loader requires a trusted full-load scope')
    if _le_checkpoint is not None and (not rebind_protected_source
            or not isinstance(_le_checkpoint, dict)
            or _le_checkpoint.get('machine', {}).get('artifact') != artifact):
        raise ValueError('LE source checkpoint and native machine reference differ')
    if type(rebind_protected_source) is not bool:
        raise ValueError('rebind_protected_source must be a literal Boolean')
    from .qemu_checkpoint import snapshot_job, validate_qcow_header
    from .qemu_checkpoint_controls import restore_controls
    from .qemu_dos_checkpoint import _compatibility, _decode_origin, _serial_idle, _source
    from .qemu_dos_tasks import read_task_context, restore_task_checkpoint
    from .qemu_instrumented_checkpoint import validate, restore
    from .qemu_machine import QemuMachine, MachineContext, _tracking, _machine_operation_guard
    from .qemu_cpu_undo_guard import attest_machine_restore
    with _operation(session, timeout_ms) as (owner, deadline):
        _machine_operation_guard(owner, 'load_machine_state', (artifact,), {'timeout_ms': timeout_ms})
        _preflight(session)
        _serial_idle(session)
        row, metadata, machine, bundle = _read_artifact(session.project, artifact, session.version['id'])
        from .qemu_image import ProducerMismatch, require_record, verify
        require_record(bundle.get('runtime', {}).get('inputs'))
        expected = dict(format=FORMAT, source_sha256=session.metadata['source_sha256'],
            version_sha256=session.metadata['version_sha256'], version=session.version['id'],
            runtime=_compatibility(session), source_binding_restored=False)
        if any(bundle.get(k) != v for k, v in expected.items()):
            raise ValueError('Owned machine archive, provenance or runtime identity differs')
        _native_idle(owner)
        _source(session)
        decoded = _decode_origin(session, bundle['origin'])
        validate(session.vm, bundle['instrumentation'])
        validate_qcow_header(machine[:104], session.vm.checkpoint_virtual_size)
        if getattr(session, '_dos_workspace_enabled', False) != ('workspace' in bundle):
            raise ValueError('Owned machine workspace presence differs')
        if 'workspace' in bundle:
            from .qemu_workspace import verify_workspace_checkpoint
            verify_workspace_checkpoint(session, machine, bundle['workspace'])
        if rebind_protected_source:
            # This is a new stopped-source admission, not an archived handle
            # or a restoration of the launch-time DOS allocation authority.
            from .qemu_dos_source_admission import _context, _source as le_source
            from .le import load_runtime_le_carrier
            if bundle['controls']['active']:
                raise ValueError('Protected source rebind requires an unlayered saved machine view')
            _context(bundle['registers'])
            raw, _ = le_source(session, session.metadata['source_sha256'])
            load_runtime_le_carrier(raw)
        _remaining(deadline)
        new = None
        try:
            # Old stopped state remains owned until fresh native state is verified.
            with tempfile.TemporaryDirectory(prefix='fdisbull-owned-checkpoint-') as directory:
                image = Path(directory) / 'state.qcow2'; image.write_bytes(machine)
                new = QemuMachine(**dict(session._checkpoint_launch, timeout_ms=_remaining(deadline)),
                                  _checkpoint_image=image)
            new.operation_deadline = deadline
            new.qmp.operation_deadline = deadline
            if new.gdb is not None:
                new.gdb.operation_deadline = deadline
            channel = new.serial(deadline)
            fresh = SimpleNamespace(vm=new, guest_profile=session.guest_profile,
                _workspace_launch_identity=getattr(session, '_workspace_launch_identity', None))
            if _compatibility(fresh) != bundle['runtime']:
                raise ProducerMismatch('Fresh owned machine runtime identity differs')
            verify(new,deadline)
            if _disk_identity(new) != bundle['disk']:
                raise DebuggerError('Fresh owned machine disk graph differs')
            if bundle['native_task'] is not None and read_task_context(new) is None:
                raise ValueError('Fresh machine lacks native architectural context support')
            # The save witness has an always-on VMState record, even when idle.
            _native_idle(new)
            snapshot_job(new, 'load', tag=bundle['tag'], vmstate='disk0', devices=['disk0'],
                         timeout_ms=_remaining(deadline), instrumented=bundle['instrumentation'] is not None)
            instrumentation = restore(new, bundle['instrumentation'])
            native_task = restore_task_checkpoint(new, bundle['native_task'], None)
            actual = MachineContext(new).registers()
            _cpu_equal(actual, bundle['registers'])
            if (_ram(new, actual) != bundle['ram'] or _helper(session, bundle['origin'], new)[0] != bundle['helper']
                    or _serial_idle(session, vm=new, channel=channel) != bundle['serial']
                    or _disk_identity(new) != bundle['disk']
                    or _native_idle(new) != bundle['native_idle']):
                raise DebuggerError('Restored owned machine RAM, helper, disk or UART differs')
            _remaining(deadline)
            new._checkpoint_restored_stopped = True
            new.lock = owner.lock
            _tracking(session, 'close', 'owned-machine-checkpoint-restore')
            owner.close_observer = None
            owner.close()
            session.vm = session.rpc = new
            new.context = session
            new.close_observer = session._on_machine_closed
            session._channel = channel
            session._serial_buffer = bytearray()
            (session._nonce, session._ready_bytes, session._tail, session._vectors_before,
             session._helper, session._ready) = decoded
            session.breakpoints = {}; session.next_bp = 1
            session._return_breakpoint = None
            session._reset_native_layers()
            session._qemu_hooks = {}; session._qemu_hook_pending = None; session._qemu_hook_pending_task = None
            session._automatic_runtime_tracker = None
            session._automatic_internal_pending = None
            session._process = deepcopy(bundle['process_provenance'])
            session._process.pop('machine_closed', None)
            session._advance_epoch()
            session._process['source_mapping'].update(live=False, live_ranges=[],
                status='unqualified-after-owned-machine-restore', current_bytes='not source-qualified')
            session._owned_machine_restored = True
            session._checkpoint_entry_clean = False
            session._checkpoint_epoch += 1
            session._set_deadline(deadline)
            bind_history = getattr(session, '_history_bind', None)
            if bind_history is not None:
                bind_history()
            le_history = getattr(session, '_qemu_le_history_provider', None)
            if le_history is not None:
                le_history._history_bind()
            if bundle['parent_return_observer']:
                session._return_breakpoint = MachineContext.breakpoint(session,
                    session._ready['helper_segment'] * 16 + session._ready['exit_wait_ip'])['breakpoint_id']
            controls = restore_controls(session, bundle['controls'], bundle['controls']['epoch'])
            if 'workspace' in bundle:
                from .qemu_workspace import restore_workspace
                restore_workspace(session, bundle['workspace'])
            session.metadata['process_disk'] = deepcopy(bundle['origin']['process_disk'])
            session.metadata['owned_machine_restore'] = dict(artifact=artifact, sha256=row['sha256'],
                origin_run=row['run'], source_binding_restored=False, runtime_origin=bundle['runtime_origin'])
            session._persist_process()
            protected_binding = None
            if rebind_protected_source:
                protected_binding = session.dos_source_bind(
                    expected_source_sha256=session.metadata['source_sha256'],
                    timeout_ms=_remaining(deadline))
            result = dict(artifact=artifact, sha256=row['sha256'], machine_state_restored=True,
                source_binding_restored=False, host_files_restored=False, origin_run=row['run'],
                protected_source_rebound=rebind_protected_source,
                capture_epoch=session._runtime_epoch, checkpoint_epoch=session._checkpoint_epoch,
                registers=actual, controls=controls, process=deepcopy(session._process),
                instrumentation=instrumentation, native_architectural_context=native_task,
                workspace_restored='workspace' in bundle,
                framebuffer='native state restored; recapture for a new stored image')
            if protected_binding is not None:
                result.update(protected_source_binding=protected_binding,
                    source_revalidation_scope='fresh stopped LE admission; not restored MZ authority or allocation lifetime')
            if _le_checkpoint is not None:
                from .qemu_dos_le_checkpoint import complete_le_restore
                result.update(complete_le_restore(session, _le_checkpoint, protected_binding))
            with session.project.transaction(True):
                session._event('load-machine-state', result)
                if _le_checkpoint is not None:
                    session._event('load-le-source-state', result)
                _remaining(deadline)
            _remaining(deadline)
            attest_machine_restore(session, result)
            return result
        except BaseException as error:
            if isinstance(error,ProducerMismatch):
                if new is not None:
                    try:new.close()
                    except BaseException as cleanup:error.new_machine_cleanup_error=type(cleanup).__name__
            else:_close_uncertain(session, error, new)
            raise
