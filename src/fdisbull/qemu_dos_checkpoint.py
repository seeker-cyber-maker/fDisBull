"""Portable private DOS process snapshots and their host control state."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import select
import tempfile
import time
import zipfile

from .dosbox_rpc import DebuggerError
from .qemu_checkpoint import snapshot_job, validate_qcow_header
from .qemu_checkpoint_controls import capture_controls, restore_controls

FORMAT = 'fdisbull-qemu-dos-process-qcow2-v2'
COMMAND = 'x-fdisbull-dos-checkpoint-status'
MAX_STATE = 128 * 1024 * 1024
MAX_SIDECAR = 64 * 1024 * 1024
_CURRENT_TASK = object()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _source(session):
    with session._checkpoint_source.open('rb') as stream:
        data = stream.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or _sha(data) != session.metadata['source_sha256']:
        raise ValueError('Process checkpoint source identity changed')
    return data


def _compatibility(session):
    inputs = session.vm.inputs
    machine = deepcopy(session.vm.machine_configuration)
    # Native admissions are observations of one live owner. The immutable
    # launch profiles and hashed executable/firmware identify compatibility.
    for key in tuple(machine):
        if key.startswith('native_') and key.endswith('_admission'):
            del machine[key]
    profile = session.guest_profile
    return dict(
        inputs={key: {field: value[field] for field in ('sha256', 'version') if field in value}
                for key, value in inputs.items() if key != 'boot_image'},
        machine=machine,
        guest_profile=dict(profile=profile['profile'], schema=profile['schema'],
            machine=profile['machine'], profile_sha256=profile['profile_sha256'],
            boot_image={key: profile['boot_image'][key] for key in ('size', 'sha256')}),
        disk_size=session.vm.checkpoint_virtual_size)


def _preflight(session):
    from .qemu_input import require_released_machine_input
    from .qemu_instrumented_checkpoint import preflight
    if (session.closed or session.vm.checkpoint_disk is None
            or session._checkpoint_launch['checkpoint_tool'] is None):
        raise ValueError('DOS process checkpoints are not enabled')
    if session.project.db.in_transaction:
        raise ValueError('Checkpoint requires a project outside a caller-owned transaction')
    if COMMAND not in session.vm.qmp_commands:
        raise ValueError('Mid-program checkpoints require the native DOS checkpoint extension')
    session._stopped()
    require_released_machine_input(session.vm)
    preflight(session)


def _serial_idle(session, vm=None, channel=None):
    vm = session.vm if vm is None else vm
    channel = session._channel if channel is None else channel
    if session._serial_buffer:
        raise ValueError('Process checkpoint requires a drained helper channel')
    reader = getattr(channel, 'reader', channel)
    result = vm.qmp.call(COMMAND)
    required = dict(iobase=0x2f8, index=1, **{'tx-idle': True, 'rx-empty': True})
    if (not isinstance(result, dict)
            or any(type(result.get(key)) is not type(value) or result[key] != value
                   for key, value in required.items())
            or result.get('tx-fifo-bytes') != 0 or result.get('rx-fifo-bytes') != 0
            or result.get('tsr-retry') != 0):
        raise ValueError('Process checkpoint requires an idle native COM2 UART')
    if select.select([reader], [], [], 0)[0]:
        raise ValueError('Process checkpoint requires a drained helper channel')
    return result


def _read(vm, address, length):
    remote = vm.debugger()
    parts = []
    for offset in range(0, length, 65536):
        parts.append(remote.memory(address + offset, min(65536, length - offset), space='virtual'))
    return b''.join(parts)


def _origin(session):
    from .dos_launch import guest_name
    return dict(
        nonce=session._nonce.hex(), ready=session._ready_bytes.hex(),
        command_tail=session._tail.hex(),
        target=session.guest_profile['machine']['boot_drive'] + '\\' +
               guest_name(session.project.meta['filename'], session.metadata['source_sha256'],
                          session.project.meta['format']),
        helper_sha256=_sha(session._helper), vectors_before=session._vectors_before.hex(),
        process_disk=deepcopy(session.metadata['process_disk']))


def _decode_origin(session, origin):
    from .dos_process_helper import build_loader, parse_report
    try:
        nonce = bytes.fromhex(origin['nonce'])
        ready_bytes = bytes.fromhex(origin['ready'])
        tail = bytes.fromhex(origin['command_tail'])
        vectors = bytes.fromhex(origin['vectors_before'])
        helper = build_loader(origin['target'], tail, nonce)
        ready = parse_report(ready_bytes, nonce)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Invalid checkpoint DOS helper identity') from error
    if (len(vectors) != 1024 or ready['type'] != 'ready'
            or _sha(helper) != origin['helper_sha256'] or tail != session._tail):
        raise ValueError('Checkpoint DOS helper or command tail differs')
    expected_target = _origin(session)['target']
    if origin['target'] != expected_target:
        raise ValueError('Checkpoint DOS target differs from the selected source')
    return nonce, ready_bytes, tail, vectors, helper, ready


def _verify_process(session, process, origin, vm=None, memory=None, task_binding=_CURRENT_TASK,
                    private_views=_CURRENT_TASK):
    from .qemu_dos_process import observe_mcbs, relocated_source
    vm = session.vm if vm is None else vm
    task_binding = getattr(session, '_dos_task_binding', None) if task_binding is _CURRENT_TASK else task_binding
    private_views = getattr(session,'_dos_task_views',{}) if private_views is _CURRENT_TASK else private_views
    if task_binding is not None:
        from .qemu_dos_tasks import observe_task
        if task_binding.get('process_nonce') != origin.get('nonce'):
            raise ValueError('Task binding differs from the checkpoint DOS helper lifetime')
        task = observe_task(session, task_binding, vm=vm)
        if task['matches_binding'] is not True:
            raise ValueError('Selected native DOS task differs from the bound task lifetime')
    nonce, raw, tail, vectors, helper, ready = _decode_origin(session, origin)
    context = session if vm is session.vm else vm.context
    registers = context.registers()
    state = registers['address_state']
    if (registers['cpu_mode'] not in ('real', 'protected', 'v86')
            or state.get('register_context_match') is not True or state.get('machine_vcpus') != 1):
        raise ValueError('DOS process checkpoints require one observed supported CPU context')
    if registers['cpu_mode'] == 'real' and state.get('paging') is not False:
        raise ValueError('Real-mode DOS process checkpoints require unpaged execution')
    if (process.get('state') != 'active' or process.get('machine_closed')
            or process['psp_segment'] != ready['child_psp']
            or process['parent_psp_segment'] != ready['helper_psp']):
        raise ValueError('Checkpoint does not identify an active owned DOS process')
    space = None
    private_read = None
    if private_views and task_binding is not None:
        from .qemu_dos_task_views import private_reader, _observe
        row = private_views.get(task_binding['task_id'])
        if row is None or row['retired']:
            raise ValueError('Selected process lacks a live private task view')
        if vm is session.vm and getattr(session,'_dos_task_monitor',None):
            _observe(session,row)
        private_read = private_reader(vm,task_binding,row['generation'])
    if registers['cpu_mode'] != 'real':
        from .qemu_dos_address_space import DosAddressSpace
        space = DosAddressSpace(vm, registers, task_binding=task_binding,private_read=private_read)
    read = ((lambda address, length: _read(vm, address, length)) if private_read is None else private_read) if space is None else space.read
    blocks = observe_mcbs(read, ready['first_mcb_segment'])
    allocation = process['allocation']
    current = next((block for block in blocks if block['mcb_segment'] == allocation['mcb_segment']), None)
    if current != allocation or current['owner_psp'] != process['psp_segment']:
        raise ValueError('DOS process allocation ownership changed')
    helper_block = next((block for block in blocks if block['segment'] == ready['helper_psp']
                         and block['owner_psp'] == ready['helper_psp']), None)
    if helper_block is None:
        raise ValueError('DOS helper no longer owns its allocation')
    psp = read(process['psp_segment'] * 16, 256)
    if (psp[:2] != b'\xcd\x20' or int.from_bytes(psp[0x16:0x18], 'little') != ready['helper_psp']
            or psp[0x80:0x82 + len(tail)] != bytes([len(tail)]) + tail + b'\r'):
        raise ValueError('DOS process PSP, parent or command tail changed')
    original, mapping = relocated_source(_source(session), session.dos, session.project.meta['format'], ready)
    recorded = process['source_mapping']
    if (any(recorded.get(key) != value for key, value in mapping.items())
            or recorded.get('source_sha256') != session.metadata['source_sha256']
            or recorded.get('expected_module_sha256') != _sha(original)
            or not recorded.get('live')):
        raise ValueError('Checkpoint source mapping differs from its DOS relocation identity')
    start = mapping['runtime_base']
    if not allocation['start'] <= start < start + len(original) <= allocation['end']:
        raise ValueError('Checkpoint source extent is outside its allocation')
    if space is not None:
        pc = registers.get('linear_pc')
        if pc is None or not start <= int(pc, 16) < start + len(original):
            raise ValueError('Protected DOS ownership requires the selected CPU inside its source module')
    expected_ranges = [dict(runtime_address=start, project_address=mapping['static_base'], length=len(original))]
    if recorded.get('live_ranges') != expected_ranges:
        raise ValueError('Checkpoint source lifetime ranges differ')
    if read(ready['helper_segment'] * 16 + ready['report_offset'], len(raw)) != raw:
        raise ValueError('Checkpoint helper READY identity changed')
    from .dos_process_helper import loader_code_ranges
    for first, last in loader_code_ranges():
        address = ready['helper_segment'] * 16 + 0x100 + first
        if read(address, last - first) != helper[first:last]:
            raise ValueError('Checkpoint helper executable code changed')
    for key in ('ready_wait_ip', 'exit_wait_ip'):
        offset = ready[key]
        if read(ready['helper_segment'] * 16 + offset, 4) != helper[offset-0x100:offset-0x100+4]:
            raise ValueError('Checkpoint helper park code changed')
    observed = dict(module_sha256=_sha(read(start, len(original))),
                    helper_sha256=_sha(read(ready['helper_segment'] * 16 + 0x100, len(helper))),
                    vectors_sha256=_sha(read(0, 1024)))
    if space is not None:
        observed['address_space'] = space.evidence()
    if memory is not None and observed != memory:
        raise ValueError('Restored process RAM differs from the captured state')
    return registers, observed, (nonce, raw, tail, vectors, helper, ready)


def _archive(machine, bundle):
    raw = _json(bundle)
    if len(raw) > MAX_SIDECAR:
        raise ValueError('Process checkpoint sidecar exceeds its byte budget')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('machine.qcow2', machine)
        archive.writestr('process.json', raw)
    return output.getvalue()


def _unarchive(data):
    if len(data) > MAX_STATE:
        raise ValueError('Process checkpoint exceeds its byte budget')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        items = archive.infolist()
        if (len(items) != 2 or {item.filename for item in items} != {'machine.qcow2', 'process.json'}
                or any(item.compress_type != zipfile.ZIP_STORED for item in items)):
            raise ValueError('Invalid private DOS checkpoint components')
        if archive.getinfo('process.json').file_size > MAX_SIDECAR:
            raise ValueError('Process checkpoint sidecar exceeds its byte budget')
        machine = archive.read('machine.qcow2')
        bundle = json.loads(archive.read('process.json'))
    if not isinstance(bundle, dict) or bundle.get('format') != FORMAT:
        raise ValueError('Unknown DOS process checkpoint format')
    return machine, bundle


def save_process_state(session, name, max_bytes):
    from .external_files import _file_name
    from .qemu_instrumented_checkpoint import capture, verify_saved
    from .qemu_dos_tasks import capture_task_checkpoint
    from .qemu_dos_task_views import capture_task_views
    from .qemu_dos_scheduler import capture_scheduler
    import uuid
    _file_name(name)
    if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= MAX_STATE):
        raise ValueError('Checkpoint byte budget must be 1..134217728')
    limit = max_bytes or MAX_STATE
    _preflight(session)
    serial = _serial_idle(session)
    origin = _origin(session)
    registers, memory, _ = _verify_process(session, session._process, origin)
    controls = capture_controls(session)
    task_checkpoint = capture_task_checkpoint(session)
    task_views = capture_task_views(session)
    scheduler = capture_scheduler(session)
    instrumentation, export_token = capture(session)
    tag = 'fdb-' + uuid.uuid4().hex
    bundle = dict(format=FORMAT, tag=tag, source_sha256=session.metadata['source_sha256'],
        version_sha256=session.metadata['version_sha256'], version=session.version['id'],
        runtime=_compatibility(session), runtime_origin=deepcopy(session.vm.inputs),
        process=deepcopy(session._process), origin=origin, registers=registers,
        memory=memory, controls=controls, serial=serial, instrumentation=instrumentation,
        native_task=task_checkpoint, task_binding=deepcopy(getattr(session, '_dos_task_binding', None)),
        task_views=task_views,native_scheduler=scheduler)
    try:
        snapshot_job(session.vm, 'save', tag=tag, vmstate='disk0', devices=['disk0'],
                     instrumented=instrumentation is not None, export_token=export_token)
        if _serial_idle(session) != serial:
            raise DebuggerError('Native COM2 state changed while saving the checkpoint')
        verify_saved(session, instrumentation)
        if capture_task_checkpoint(session) != task_checkpoint:
            raise DebuggerError('Native task context changed while saving checkpoint')
        if capture_task_views(session) != task_views:
            raise DebuggerError('Native private task views changed while saving checkpoint')
        if capture_scheduler(session) != scheduler:
            raise DebuggerError('Native scheduler CPU/frame state changed while saving checkpoint')
        with session.vm.checkpoint_disk.open('rb') as stream:
            machine = stream.read(limit + 1)
        if len(machine) > limit:
            raise ValueError('Checkpoint exceeds its byte budget')
        validate_qcow_header(machine[:104], session.vm.checkpoint_virtual_size)
        data = _archive(machine, bundle)
        if len(data) > limit:
            raise ValueError('Checkpoint exceeds its byte budget')
        metadata = dict(format=FORMAT, source_sha256=bundle['source_sha256'],
            version_sha256=bundle['version_sha256'], origin_run=session.run_id,
            sidecar_sha256=_sha(_json(bundle)), checkpoint_scope='stopped DOS process with private disk and debugger controls',
            host_files_restored=False)
        if instrumentation is not None:
            metadata['instrumentation'] = dict(sha256=instrumentation['sha256'],
                clock_profile='virtual', audio_profile=session._checkpoint_launch['audio_profile'],
                retrace_profile=session._checkpoint_launch['retrace_profile'])
        return session._artifact(name, 'state', data, metadata)
    except BaseException:
        session.close()
        raise


def load_process_state(session, artifact, timeout_ms):
    from .operation_budget import request_deadline
    from .qemu_machine import MachineContext, QemuMachine
    from .qemu_instrumented_checkpoint import validate, restore
    from .qemu_dos_tasks import read_task_context, restore_task_checkpoint, task_key
    from .qemu_dos_task_views import validate_task_views, prime_task_views, verify_task_views, restore_task_views
    from .qemu_dos_scheduler import validate_scheduler,prime_scheduler,verify_scheduler,restore_scheduler

    deadline = request_deadline(session, timeout_ms)

    def remaining():
        value = int((deadline - time.monotonic()) * 1000)
        if value <= 0:
            raise TimeoutError('DOS process restore deadline expired')
        return min(value, 600000)

    owner = session.vm
    wait = min(10, max(0, deadline - time.monotonic()))
    if not owner.lock.acquire(timeout=wait):
        raise TimeoutError('DOS process restore lock timed out')
    previous_session_deadline = session._deadline
    previous_vm_deadline = owner.operation_deadline
    previous_channels = [(channel, channel.operation_deadline) for channel in
                         (owner.qmp, owner.gdb) if channel is not None]
    bounds = [deadline, previous_session_deadline, previous_vm_deadline,
              *[bound for _, bound in previous_channels]]
    deadline = min(bound for bound in bounds if bound is not None)
    session._set_deadline(deadline)
    try:
        remaining()
        if session.vm is not owner:
            raise ValueError('Machine owner changed before process restore')
        _preflight(session)
        _serial_idle(session)
        row = session.project.db.execute(
            'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
            (artifact,)).fetchone()
        if row is None or row['kind'] != 'state' or row['version'] != session.version['id']:
            raise ValueError('Process checkpoint must belong to the selected project version')
        data = bytes(row['data'])
        metadata = json.loads(row['metadata'])
        if (_sha(data) != row['sha256'] or metadata.get('format') != FORMAT
                or metadata.get('source_sha256') != session.metadata['source_sha256']
                or metadata.get('version_sha256') != session.metadata['version_sha256']):
            raise ValueError('Process checkpoint source, version or data identity differs')
        remaining()
        machine, bundle = _unarchive(data)
        remaining()
        expected = dict(format=FORMAT, source_sha256=session.metadata['source_sha256'],
                        version_sha256=session.metadata['version_sha256'], version=session.version['id'],
                        runtime=_compatibility(session))
        if (metadata.get('sidecar_sha256') != _sha(_json(bundle))
                or any(bundle.get(key) != value for key, value in expected.items())):
            raise ValueError('Process checkpoint sidecar or runtime identity differs')
        _source(session)
        decoded = _decode_origin(session, bundle['origin'])
        task_binding = bundle.get('task_binding')
        if task_binding is not None:
            task_key(task_binding)
            if task_binding.get('process_nonce') != bundle['origin']['nonce']:
                raise ValueError('Checkpoint task binding differs from its process helper lifetime')
        native_task = bundle.get('native_task')
        if task_binding is not None and native_task is None:
            raise ValueError('Task-bound checkpoint lacks a native task observation')
        task_views = bundle.get('task_views')
        validate_task_views(session, task_views, bundle['origin']['nonce'])
        if task_views is not None and (task_binding is None or not any(
                task_key(row['binding']) == task_key(task_binding) for row in task_views['views'])):
            raise ValueError('Private checkpoint lacks its selected task binding')
        scheduler = bundle.get('native_scheduler')
        validate_scheduler(session,scheduler,bundle['origin']['nonce'],task_views,bundle['process'])
        if ((scheduler is not None) != (bundle['controls'].get('format') == 'fdisbull-qemu-controls-task-4')):
            raise ValueError('Native scheduler checkpoint requires its version-4 control fence')
        instrumentation = bundle.get('instrumentation')
        validate(session.vm, instrumentation)
        validate_qcow_header(machine[:104], session.vm.checkpoint_virtual_size)
        remaining()
        new = None
        try:
            with tempfile.TemporaryDirectory(prefix='fdisbull-process-checkpoint-') as directory:
                image = Path(directory) / 'state.qcow2'
                image.write_bytes(machine)
                new = QemuMachine(**dict(session._checkpoint_launch, timeout_ms=remaining()),
                                  _checkpoint_image=image)
            new.operation_deadline = deadline
            new.qmp.operation_deadline = deadline
            channel = new.serial(deadline)
            # Register the native scalar VMState on this fresh owner before
            # the incoming snapshot is parsed. No guest instruction executes.
            if native_task is not None:
                if read_task_context(new) is None:
                    raise ValueError('Fresh QEMU lacks the checkpoint task-context extension')
            prime_task_views(new, task_views)
            prime_scheduler(new,scheduler,task_views)
            snapshot_job(new, 'load', tag=bundle['tag'], vmstate='disk0', devices=['disk0'],
                         timeout_ms=remaining(), instrumented=instrumentation is not None)
            restored_instrumentation = restore(new, instrumentation)
            restored_task = restore_task_checkpoint(new, native_task, task_binding)
            restored_views = verify_task_views(new, task_views)
            restored_scheduler = verify_scheduler(new,scheduler)
            actual, _, _ = _verify_process(session, bundle['process'], bundle['origin'],
                vm=new, memory=bundle['memory'], task_binding=task_binding,
                private_views={} if task_views is None else {row['binding']['task_id']:row for row in task_views['views']})
            for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
                if actual.get(field) != bundle['registers'].get(field):
                    from .qemu_dos_scheduler import _differences
                    changed = _differences(bundle['registers'].get(field),actual.get(field),field)
                    error = DebuggerError('Restored process CPU differs: '+', '.join(changed))
                    error.expected_cpu = bundle['registers']
                    error.actual_cpu = actual
                    raise error
            if _serial_idle(session, vm=new, channel=channel) != bundle['serial']:
                raise DebuggerError('Restored native COM2 state differs from the checkpoint')
            # QEMU retains the fresh owner's prelaunch runstate after a cold
            # load. The verified CPU/RAM/serial state is already stopped; a
            # later save must not require an intervening guest continuation.
            new._checkpoint_restored_stopped = True
            remaining()
            # The session's one lock remains stable for queued callers.
            new.lock = owner.lock
            owner.close_observer = None
            owner.close()
            session.vm = session.rpc = new
            new.context = session
            new.close_observer = session._on_machine_closed
            session._channel = channel
            session._serial_buffer = bytearray()
            (session._nonce, session._ready_bytes, session._tail, session._vectors_before,
             session._helper, session._ready) = decoded
            session.breakpoints = {}
            session.next_bp = 1
            session._reset_native_layers()
            session._qemu_hooks = {}
            session._qemu_hook_pending = None
            session._qemu_hook_pending_task = None
            session._dos_task_binding = deepcopy(task_binding)
            session.metadata['dos_task_binding'] = deepcopy(task_binding)
            session._process = deepcopy(bundle['process'])
            session._advance_epoch()
            session._set_deadline(deadline)
            private_layer_ids = restore_task_views(session, task_views, restored_views)
            restore_scheduler(session,scheduler,restored_scheduler)
            session._return_breakpoint = MachineContext.breakpoint(
                session, session._ready['helper_segment'] * 16 + session._ready['exit_wait_ip'])['breakpoint_id']
            restored_controls = restore_controls(session, bundle['controls'],
                bundle['process']['capture_epoch'], private_layer_ids=private_layer_ids)
            session._checkpoint_entry_clean = False
            session._checkpoint_epoch += 1
            session.metadata['process_disk'] = deepcopy(bundle['origin']['process_disk'])
            session.metadata['checkpoint_restore'] = dict(
                artifact=artifact, sha256=row['sha256'], origin_run=row['run'],
                runtime_origin=bundle['runtime_origin'], launch_template_inputs=deepcopy(new.inputs))
            session._persist_process()
            result = dict(artifact=artifact, sha256=row['sha256'],
                          checkpoint_epoch=session._checkpoint_epoch, origin_run=row['run'],
                          capture_epoch=session._runtime_epoch, source_binding_restored=True,
                          host_files_restored=False, process=deepcopy(session._process),
                          controls=restored_controls)
            if restored_instrumentation is not None:
                result['instrumentation'] = restored_instrumentation
            if restored_task is not None:
                result['native_task'] = restored_task
                result['task_identity'] = deepcopy(task_binding)
            if restored_views is not None:
                result['task_views'] = dict(layers=private_layer_ids,
                    tasks=list(session._dos_task_views), native=restored_views)
            if restored_scheduler is not None:
                result['scheduler'] = restored_scheduler
            session._event('load-state', result)
            remaining()
            session._set_deadline(previous_session_deadline)
            return result
        except BaseException:
            if new is not None:
                new.close()
            session.close()
            raise
    except BaseException:
        channels = (owner.qmp, owner.gdb)
        if any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
               for channel in channels):
            session.close()
        raise
    finally:
        owner.operation_deadline = previous_vm_deadline
        for channel, bound in previous_channels:
            channel.operation_deadline = bound
        if session.vm is owner:
            session._deadline = previous_session_deadline
            current = owner.gdb
            if current is not None and not any(current is channel for channel, _ in previous_channels):
                current.operation_deadline = previous_vm_deadline
        owner.lock.release()
