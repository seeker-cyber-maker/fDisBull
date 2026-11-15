"""Owned machine archives have no DOS process/source restoration authority."""
import io
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import threading
import time
from types import SimpleNamespace
import zipfile

import pytest

from fdisbull import qemu_dos_checkpoint as process_checkpoint
from fdisbull import qemu_owned_checkpoint as owned
from fdisbull.project import Project
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull import dos_process_helper
from fdisbull.dosbox_rpc import DebuggerError


def test_owned_archive_is_not_a_process_checkpoint():
    bundle = {'format': owned.FORMAT, 'machine_state_restored': False}
    payload = owned._archive(b'authored-native-state', bundle)
    assert owned._unarchive(payload) == (b'authored-native-state', bundle)
    assert owned.KIND == 'machine-state'
    assert owned.FORMAT not in process_checkpoint.PROCESS_FORMATS
    with pytest.raises(ValueError, match='components'):
        process_checkpoint._unarchive(payload)


@pytest.mark.parametrize('names', [
    ['machine.qcow2', 'owned-machine.json', 'extra'],
    ['machine.qcow2', 'owned-machine.json', 'owned-machine.json'],
    ['machine.qcow2', 'process.json'],
])
def test_owned_archive_rejects_extra_duplicate_or_foreign_members(names):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name in names:
            archive.writestr(name, b'{}')
    with pytest.raises(ValueError, match='components'):
        owned._unarchive(stream.getvalue())


def qcow():
    data = bytearray(104)
    struct.pack_into('>IIQIIQI', data, 0, 0x514649fb, 3, 0, 0, 16, 1474560, 0)
    struct.pack_into('>I', data, 100, 104)
    return bytes(data)


class Native:
    """Only QMP/GDB/snapshot boundaries are substituted in this host route."""
    def __init__(self, path, memory=None, cpu=None):
        self.lock = threading.RLock()
        self.checkpoint_disk = path
        path.write_bytes(qcow())
        self.checkpoint_virtual_size = 1474560
        self.memory = bytearray(2 << 20) if memory is None else bytearray(memory)
        self.cpu = deepcopy(cpu) if cpu is not None else dict(registers=dict(
            rip='0x110010', rsp='0x120100', ss='0x18', cs='0x10', eflags='0x202'),
            instruction_pointer='0x110010', linear_pc='0x110010', cpu_mode='protected',
            address_state=dict(cpu_mode='protected', code_bits=32, stack_bits=32, paging=False,
                a20=True, machine_vcpus=1, register_context_match=True,
                control=dict(CR0='0x11', CR3='0x0', CR4='0x0', EFER='0x0'),
                segments=dict(ss=dict(base='0x0'))))
        self.inputs = dict(qemu=dict(sha256='1'*64), boot_image=dict(sha256='2'*64))
        self.machine_configuration = dict(cpus=1, memory_mib=2,
            clock_profile=dict(profile='standard'))
        self.closed = False; self.operation_deadline = None; self.close_observer = None
        self.process = SimpleNamespace(poll=lambda: 0 if self.closed else None)
        self.qmp_commands = frozenset({process_checkpoint.COMMAND})
        self.calls = []; self.points = set(); self.gdb = self
        self.qmp = SimpleNamespace(call=self.call, operation_deadline=None)

    def debugger(self):
        return self.gdb

    def memory_read(self, address, length, **kwargs):
        return bytes(self.memory[address:address+length])

    def request(self, command, **kwargs):
        self.calls.append(command)
        self.points.add(command)
        return b'OK'

    def call(self, command, arguments=None, **kwargs):
        self.calls.append(command)
        if command == 'query-status':
            return dict(running=False, status='paused')
        if command == 'query-block':
            return [dict(inserted=dict(node_name_unused=True,
                **{'node-name':'disk0', 'drv':'qcow2', 'ro':False}))]
        if command == 'query-named-block-nodes':
            return [dict(**{'node-name':'disk0', 'drv':'qcow2', 'ro':False,
                'image':{'format':'qcow2', 'virtual-size':1474560}}),
                dict(**{'node-name':'fdbfile', 'drv':'file', 'ro':False,
                        'file':str(self.checkpoint_disk)})]
        if command == 'x-fdisbull-layer-observe':
            return {'generation':0, 'execution-bytes':0, 'fault':None}
        raise AssertionError('Unexpected native request: ' + command)

    def close(self):
        self.closed = True


class NativeRemote:
    def __init__(self, machine):
        self.vm = machine
        self.operation_deadline = None

    def memory(self, address, length, **kwargs):
        return self.vm.memory_read(address, length, **kwargs)

    def request(self, command, **kwargs):
        return self.vm.request(command, **kwargs)


class Session(QemuDOSProcessSession):
    def __init__(self, project, path):
        self.project = project; self.version = project.version(); self.run_id = 'owned-host-run'
        self.vm = Native(path); self.vm.gdb = NativeRemote(self.vm); self.vm.context = self
        self.rpc = self.vm; self.closed = False; self._deadline = None
        self.metadata = dict(source_sha256=project.meta['source_sha256'],
                             version_sha256=self.version['sha256'], process_disk={})
        self.guest_profile = dict(profile='authored', schema=1, machine=dict(boot_drive='A:'),
                                 profile_sha256='3'*64, boot_image=dict(size=1474560, sha256='2'*64))
        self._checkpoint_launch = dict(executable='authored-qemu', checkpoint_tool='authored-qemu-img',
                                      audio_profile='off', retrace_profile='standard')
        self._checkpoint_source = project.path.parent / 'TARGET.COM'
        self._checkpoint_epoch = 0; self._epoch_number = 1
        self._runtime_epoch = self.run_id + ':process:1'
        self._dos_task_binding = None; self._dos_task_views = {}; self._dos_scheduler = None
        self._automatic_runtime_tracker = None; self._automatic_internal_pending = None
        self._nonce = bytes(range(16)); self._tail = b''; self._vectors_before = bytes(1024)
        self._helper = dos_process_helper.build_loader('A:\\TARGET.COM', b'', self._nonce)
        report = bytearray(self._helper[4:100]); report[5] = 1
        for field, value in dict(helper_segment=0x2000, helper_psp=0x2000, child_psp=0x3000,
                                  stack_sp=2, raw_stack_sp=0).items():
            struct.pack_into('<H', report, dos_process_helper.REPORT_FIELDS[field], value)
        self._ready_bytes = bytes(report)
        self._ready = dos_process_helper.parse_report(self._ready_bytes, self._nonce)
        self.vm.memory[0x20100:0x20100+len(self._helper)] = self._helper
        self.vm.memory[0x20104:0x20164] = report
        self._process = dict(state='active', capture_epoch=self._runtime_epoch,
            psp_segment=0x3000, parent_psp_segment=0x2000,
            allocation=dict(paragraphs=500), source_mapping=dict(live=True, live_ranges=[{'historical':1}]))
        self._return_breakpoint = 'machine-bp-0'
        self.breakpoints = {self._return_breakpoint:dict(address=0x20000+self._ready['exit_wait_ip'],
            kind=1, length=1, access='x', owner='user')}
        self.next_bp = 1; self.capabilities = dict(code_layers=False)
        self._reset_native_layers(); self._qemu_hooks = {}; self._qemu_hook_pending = None
        self._qemu_hook_pending_task = None; self._dos_workspace_enabled = False
        self._serial_buffer = bytearray(); self._channel = object()
        self.thawed = 0
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (self.run_id, self.version['id'], 'authored', None, 'stopped', '{}'))

    def registers(self):
        return deepcopy(self.vm.cpu)

    def _cpu_delta_full_restore_complete(self):
        self.thawed += 1

    def close(self):
        self.vm.close(); self.closed = True


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    source = tmp_path / 'TARGET.COM'; source.write_bytes(b'\x90\xeb\xfd')
    project = Project.create(tmp_path / 'owned.fdb', source, image='com')
    session = Session(project, tmp_path / 'native.qcow2')
    snapshots = []; spawned = []
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._serial_idle',
                        lambda *args, **kwargs: dict(idle=True))
    # Native context/instrumentation are separately verified implementations;
    # these doubles model their absent standard-profile native boundary here.
    monkeypatch.setattr('fdisbull.qemu_dos_tasks.capture_task_checkpoint', lambda _: None)
    monkeypatch.setattr('fdisbull.qemu_dos_tasks.restore_task_checkpoint', lambda *args: None)
    monkeypatch.setattr('fdisbull.qemu_machine.MachineContext.registers',
                        lambda self: deepcopy(self.vm.cpu))

    def snapshot(vm, operation, **kwargs):
        snapshots.append((operation, vm))
        if operation == 'save':
            saved_memory[:] = vm.memory
            saved_cpu.clear(); saved_cpu.update(deepcopy(vm.cpu))
        else:
            vm.memory[:] = saved_memory
            vm.cpu = deepcopy(saved_cpu)
        return dict(status='concluded')

    saved_memory = bytearray(); saved_cpu = {}
    monkeypatch.setattr('fdisbull.qemu_checkpoint.snapshot_job', snapshot)

    def fresh(**kwargs):
        native = Native(tmp_path / ('fresh-'+str(len(spawned))+'.qcow2'))
        native.gdb = NativeRemote(native)
        native.serial = lambda _: object()
        spawned.append(native)
        return native
    monkeypatch.setattr('fdisbull.qemu_machine.QemuMachine', fresh)
    yield SimpleNamespace(session=session, project=project, snapshots=snapshots,
                          spawned=spawned, saved_memory=saved_memory, saved_cpu=saved_cpu)
    project.__exit__(None, None, None)


def test_public_core_capture_is_distinct_and_offline_inspect_is_passive(runtime):
    s = runtime.session
    # The stronger source verification must never be used to admit this mode.
    s._process['allocation']['paragraphs'] = 2
    saved = owned.save_owned_machine_state(s)
    report = owned.inspect_owned_machine_state(runtime.project, saved['artifact'])
    assert report['kind'] == 'machine-state'
    assert report['source_binding_restored'] is False
    assert report['workspace_present'] is False
    assert [op for op, _ in runtime.snapshots] == ['save']
    assert not runtime.spawned
    assert not s.closed


def test_changed_ram_cpu_cold_owner_restore_retires_source_and_attests(runtime):
    s = runtime.session; old = s.vm; old_epoch = s._runtime_epoch
    s.vm.memory[0x110020:0x110024] = b'ABCD'
    saved = owned.save_owned_machine_state(s)
    s.vm.memory[0x110020:0x110024] = b'WXYZ'
    s.vm.cpu['registers']['eflags'] = '0x203'
    result = owned.load_owned_machine_state(s, saved['artifact'])
    assert bytes(s.vm.memory[0x110020:0x110024]) == b'ABCD'
    assert s.vm.cpu['registers']['eflags'] == '0x202'
    assert old.closed and s.vm is not old
    assert s._runtime_epoch != old_epoch
    assert result['machine_state_restored'] is True and result['source_binding_restored'] is False
    assert s._process['source_mapping']['live'] is False
    assert s._process['source_mapping']['live_ranges'] == []
    assert s._owned_machine_restored is True and s._checkpoint_entry_clean is False
    assert s.thawed == 1
    assert s._return_breakpoint in s.breakpoints
    assert runtime.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='load-machine-state'").fetchone()[0] == 1


@pytest.mark.parametrize('attribute,value', [
    ('_dos_task_binding', {'task_id':'old'}), ('_dos_task_monitor', {'old':1}),
    ('_dos_scheduler', {'enabled':False}), ('_dos_save_witness', {'owner':'old'}),
    ('_dos_task_views', {'old':{}}), ('_automatic_internal_pending', {'pc':1}),
])
def test_unsupported_owned_composition_refuses_before_snapshot(runtime, attribute, value):
    setattr(runtime.session, attribute, value)
    with pytest.raises(ValueError):
        owned.save_owned_machine_state(runtime.session)
    assert not runtime.snapshots and not runtime.spawned
    assert not runtime.session.closed


def test_bad_disk_graph_refuses_before_native_save(runtime, monkeypatch):
    original = runtime.session.vm.call
    def call(command, *args, **kwargs):
        if command == 'query-block':
            return [dict(inserted={'node-name':'disk0','drv':'qcow2','ro':False}),
                    dict(inserted={'node-name':'unowned','drv':'raw','ro':False})]
        return original(command, *args, **kwargs)
    runtime.session.vm.qmp.call = call
    with pytest.raises(ValueError, match='exactly one writable'):
        owned.save_owned_machine_state(runtime.session)
    assert not runtime.snapshots


def test_publication_failure_preserves_primary_and_closes(runtime, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('authored artifact failure')
    monkeypatch.setattr(runtime.session, '_artifact', fail)
    with pytest.raises(OSError, match='authored artifact failure'):
        owned.save_owned_machine_state(runtime.session)
    assert runtime.session.closed


def test_corrupt_artifact_refuses_before_fresh_spawn(runtime):
    saved = owned.save_owned_machine_state(runtime.session)
    runtime.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',
                              (b'corrupt', saved['artifact']))
    runtime.project.db.commit()
    with pytest.raises(ValueError, match='hash differs'):
        owned.load_owned_machine_state(runtime.session, saved['artifact'])
    assert not runtime.spawned and not runtime.session.closed


def test_cold_cpu_disagreement_closes_both_without_thaw(runtime, monkeypatch):
    saved = owned.save_owned_machine_state(runtime.session)
    old = runtime.session.vm
    def wrong(self):
        values = deepcopy(self.vm.cpu); values['registers']['eflags'] = '0x203'
        return values
    monkeypatch.setattr('fdisbull.qemu_machine.MachineContext.registers', wrong)
    with pytest.raises(DebuggerError, match='CPU differs'):
        owned.load_owned_machine_state(runtime.session, saved['artifact'])
    assert old.closed and runtime.spawned[0].closed
    assert runtime.session.thawed == 0


def test_budget_cleanup_failure_preserves_primary_and_releases_lock(runtime, monkeypatch):
    session = runtime.session
    original = session._set_deadline
    def deadline(value):
        if value is None:
            raise OSError('authored deadline cleanup failure')
        original(value)
    monkeypatch.setattr(session, '_set_deadline', deadline)
    session._dos_task_binding = {'unsupported':True}
    with pytest.raises(ValueError, match='task or provenance') as caught:
        owned.save_owned_machine_state(session)
    assert caught.value.checkpoint_budget_cleanup_errors == ['OSError']
    acquired = []
    def lock_probe():
        ok = session.vm.lock.acquire(timeout=.1); acquired.append(ok)
        if ok: session.vm.lock.release()
    thread = threading.Thread(target=lock_probe); thread.start(); thread.join()
    assert acquired == [True]


def test_native_layer_selection_hook_rebinds_without_source_authority(runtime):
    session = runtime.session
    session.capabilities['code_layers'] = True
    layer = session.layer_patch('physical-native', '0x110020', expected_hex='00', data_hex='01',
                                space='physical', activate=False)
    hook = session.hook('0x110040', space='linear', once=False, max_hits=3,
                        actions=[{'op':'layers', 'layers':[layer['layer']]}])
    saved = owned.save_owned_machine_state(session)
    result = owned.load_owned_machine_state(session, saved['artifact'])
    rebound = result['controls']['layers'][layer['layer']]
    assert rebound != layer['layer']
    definition = runtime.project.debug_layer_info(rebound)
    assert definition['native_binding']['epoch'] == session._runtime_epoch
    assert definition['native_binding']['space'] == 'physical'
    restored = list(session._qemu_hooks.values())
    assert len(restored) == 1 and restored[0]['hook'] == hook['hook']
    assert restored[0]['actions'] == [{'op':'layers', 'layers':[rebound]}]
    assert restored[0]['space'] == 'linear' and restored[0]['hits'] == 0


@pytest.mark.parametrize('change', ['source_hook', 'redirect', 'source_layer'])
def test_source_dependent_controls_refuse_without_native_io(runtime, change):
    session = runtime.session
    session.capabilities['code_layers'] = True
    session.hook('0x110040', space='linear', once=False, max_hits=3,
                 actions=[{'op':'registers', 'registers':{'rax':{'expected':0, 'value':0}}}])
    hook = next(iter(session._qemu_hooks.values()))
    if change == 'source_hook':
        hook['space'] = 'source'
    elif change == 'redirect':
        hook['actions'] = [{'op':'redirect', 'address':'0x10000'}]
    else:
        layer = runtime.project.debug_layer('source-control', kind='ram', patches=[dict(
            address=hex(runtime.project.regions(session.version['id'])[0].start),
            expected_hex='90', data_hex='90')])
        hook['actions'] = [{'op':'layers', 'layers':[layer['layer']]}]
    before = list(session.vm.calls)
    with pytest.raises(ValueError, match='machine|source'):
        owned.save_owned_machine_state(session)
    assert session.vm.calls == before and not runtime.snapshots


def rewrite(runtime, saved, change):
    row = runtime.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',
                                   (saved['artifact'],)).fetchone()
    machine, bundle = owned._unarchive(bytes(row['data']))
    change(bundle)
    data = owned._archive(machine, bundle); metadata = json.loads(row['metadata'])
    metadata['sidecar_sha256'] = owned._sha(owned._json(bundle))
    with runtime.project.transaction(True):
        runtime.project.db.execute('UPDATE debug_artifacts SET data=?,sha256=?,metadata=? WHERE id=?',
            (data, owned._sha(data), json.dumps(metadata), saved['artifact']))


def test_consistent_outer_archive_with_invalid_ram_fence_refuses_before_spawn(runtime):
    saved = owned.save_owned_machine_state(runtime.session)
    rewrite(runtime, saved, lambda bundle: bundle['ram'][0].update(hex='ff'*4096))
    with pytest.raises(ValueError, match='RAM fence'):
        owned.load_owned_machine_state(runtime.session, saved['artifact'])
    assert not runtime.spawned and not runtime.session.closed


def test_load_publication_failure_closes_fresh_owner_and_never_thaws(runtime, monkeypatch):
    session = runtime.session; saved = owned.save_owned_machine_state(session)
    original = session._event
    def fail(operation, value):
        if operation == 'load-machine-state':
            raise OSError('authored restore publication failure')
        return original(operation, value)
    monkeypatch.setattr(session, '_event', fail)
    with pytest.raises(OSError, match='authored restore publication failure'):
        owned.load_owned_machine_state(session, saved['artifact'])
    assert session.closed and runtime.spawned[0].closed and session.thawed == 0


def test_expired_inherited_budget_does_not_dispatch(runtime):
    session = runtime.session; session._deadline = time.monotonic()-1
    with pytest.raises(TimeoutError, match='deadline expired'):
        owned.save_owned_machine_state(session)
    assert not runtime.snapshots and not session.vm.calls and not session.closed


@pytest.mark.parametrize('change', ['source_sha256', 'version', 'version_sha256', 'maps'])
def test_rehashed_invalid_control_identity_or_maps_refuse_before_spawn(runtime, change):
    session = runtime.session; saved = owned.save_owned_machine_state(session)
    def alter(bundle):
        controls = bundle['controls']
        if change == 'maps':
            controls['maps']['exec'] = [[0x110000, 0]]
            controls['maps']['exec_base'] = [[0x110000, 0]]
            controls['observed'] = [[0x110000, 0]]
        else:
            controls[change] = 'not-this-source-or-version'
    rewrite(runtime, saved, alter)
    with pytest.raises(ValueError, match='controls differ|maps differ'):
        owned.load_owned_machine_state(session, saved['artifact'])
    assert not runtime.spawned and not session.closed and session.thawed == 0


@pytest.mark.parametrize('change', ['missing_cs', 'address', 'too_many_actions', 'task_field', 'duplicate_site'])
def test_rehashed_invalid_hook_refuses_before_spawn(runtime, change):
    session = runtime.session
    session.hook('0x110040', space='linear', once=False, max_hits=3,
        actions=[{'op':'registers', 'registers':{'rax':{'expected':0, 'value':0}}}])
    saved = owned.save_owned_machine_state(session)
    def alter(bundle):
        controls = bundle['controls']; hook = controls['hooks'][0]
        if change == 'missing_cs': hook.pop('cs')
        elif change == 'address': hook['address'] = '0x110041'
        elif change == 'too_many_actions': hook['actions'] *= 17
        elif change == 'task_field': controls['task_identity'] = None
        else:
            duplicate = deepcopy(hook); duplicate['hook'] = 'another-id'
            controls['hooks'].append(duplicate)
    rewrite(runtime, saved, alter)
    with pytest.raises(ValueError, match='hook|task identity|duplicate native'):
        owned.load_owned_machine_state(session, saved['artifact'])
    assert not runtime.spawned and not session.closed


@pytest.mark.parametrize('value', ['bad', {}, {'mode':'not-a-mode'}])
def test_malformed_native_context_refuses_before_spawn_and_owner_loss(runtime, value):
    session = runtime.session; saved = owned.save_owned_machine_state(session)
    rewrite(runtime, saved, lambda bundle: bundle.update(native_task=value))
    with pytest.raises(ValueError, match='architectural context'):
        owned.load_owned_machine_state(session, saved['artifact'])
    assert not runtime.spawned and not session.closed and session.thawed == 0


@pytest.mark.parametrize('operation', ['save', 'load'])
def test_admission_transport_loss_quarantines_without_masking_primary(runtime, monkeypatch, operation):
    session = runtime.session
    saved = owned.save_owned_machine_state(session) if operation == 'load' else None
    session.vm.qmp.socket = object()
    def lost(*args, **kwargs):
        session.vm.qmp.socket = None
        raise OSError('authored admission transport loss')
    monkeypatch.setattr(session.vm.qmp, 'call', lost)
    with pytest.raises(OSError, match='authored admission transport loss'):
        if operation == 'save': owned.save_owned_machine_state(session)
        else: owned.load_owned_machine_state(session, saved['artifact'])
    assert session.closed and session.vm._fdisbull_control_quarantine
    assert not runtime.spawned and session.thawed == 0
