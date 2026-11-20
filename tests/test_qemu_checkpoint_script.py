"""Modern DOS checkpoint scripts with real storage and QMP/GDB framing.

Native DOS ownership/CPU observation and the QEMU process are authored seams.
The public DOS methods, archive/hash/control validation, full-load guard,
snapshot protocol, owner swap/epochs, script routes and FDB are production.
Actual DOS/VMState behavior belongs to the separately admitted native cases.
"""
from copy import deepcopy
from functools import wraps
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from fdisbull import qemu_dos_checkpoint as checkpoint
from fdisbull.cli import respond, public_addresses
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull.qemu_machine import MachineContext
from test_qemu_checkpoint_tracking import qcow_bytes
from test_qemu_operation_deadlines import Clock, Wire, client, packet
from support.qemu_image_fixture import attach_image


def route(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=list(steps))


class CheckpointWire(Wire):
    def __init__(self, clock, protocol, vm):
        super().__init__(clock, protocol)
        self.vm = vm

    def sendall(self, data):
        if data == b'+':
            return super().sendall(data)
        if self.protocol == 'gdb':
            command = data[1:-3]
            if command.startswith((b'Z', b'z', b'm')):
                self.requests.append(command)
                self.budgets.append(self.timeout)
                result = self.vm.word.to_bytes(2, 'little').hex().encode() if command.startswith(b'm') else b'OK'
                self.buffer.extend(packet(result))
                self.pending_delay = self.latency
                return
            return super().sendall(data)
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        self.requests.append(command)
        self.budgets.append(self.timeout)
        if command == 'query-status':
            result = dict(running=False, status='paused')
        elif command == checkpoint.COMMAND:
            result = {'iobase': 0x2f8, 'index': 1, 'tx-idle': True, 'rx-empty': True,
                      'tx-fifo-bytes': 0, 'rx-fifo-bytes': 0, 'tsr-retry': 0}
        elif command in ('snapshot-save', 'snapshot-load'):
            self.vm.job = dict(id=args['job-id'], type=command, status='concluded')
            if command == 'snapshot-save':
                self.vm.checkpoint_disk.write_bytes(qcow_bytes() + json.dumps(
                    dict(word=self.vm.word, pc=self.vm.pc)).encode())
            else:
                state = json.loads(self.vm.checkpoint_disk.read_bytes()[104:])
                self.vm.word, self.vm.pc = state['word'], state['pc']
            result = {}
        elif command == 'query-jobs':
            result = [self.vm.job]
        elif command == 'job-dismiss':
            result = {}
        else:
            pytest.fail('Unexpected checkpoint QMP command: ' + command)
        self.buffer.extend(json.dumps({'return': result, 'id': request['id']}).encode() + b'\n')
        self.pending_delay = self.latency


@pytest.fixture
def process_checkpoint(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock)
    binary = tmp_path / 'CHECK.COM'
    binary.write_bytes(bytes.fromhex('90ebfd'))
    owners = []

    class Machine:
        def __init__(self, *, _checkpoint_image=None, timeout_ms=None, **kwargs):
            self.lock = threading.RLock()
            self.closed, self.operation_deadline = False, None
            self.word, self.pc = 0x1111, 0x101
            self.process = SimpleNamespace(poll=lambda: 0 if self.closed else None)
            self.checkpoint_disk = tmp_path / ('owner-%d.qcow2' % len(owners))
            self.checkpoint_disk.write_bytes(Path(_checkpoint_image).read_bytes() if _checkpoint_image else qcow_bytes())
            self.checkpoint_virtual_size = 1474560
            self.machine_configuration = dict(cpus=1, memory_mib=16,
                clock_profile={'profile': 'standard'}, audio_profile={'profile': 'off'},
                retrace_profile={'profile': 'standard'})
            self.inputs, self.qmp_commands = {}, {checkpoint.COMMAND}
            self.qmp, _ = client('qmp', clock)
            self.gdb, _ = client('gdb', clock)
            self.qwire, self.gwire = CheckpointWire(clock, 'qmp', self), CheckpointWire(clock, 'gdb', self)
            self.qmp.socket, self.gdb.socket = self.qwire, self.gwire
            self.gdb.packet_size = 4096
            self.close_observer = None
            self.timeout_ms = timeout_ms
            attach_image(self)
            owners.append(self)

        def debugger(self):
            return self.gdb

        def serial(self, deadline):
            return SimpleNamespace(operation_deadline=deadline)

        def close(self):
            if self.closed:
                return
            self.closed = True
            if self.close_observer is not None:
                self.close_observer()
            self.qmp.close()
            self.gdb.close()

    monkeypatch.setattr('fdisbull.qemu_machine.QemuMachine', Machine)
    origin = dict(nonce='aa', process_disk={'sha256': '1'*64})
    decoded = (b'\xaa', b'ready', b'', b'vectors', b'helper',
               dict(helper_segment=0x100, exit_wait_ip=0x20))
    monkeypatch.setattr(checkpoint, '_origin', lambda session: deepcopy(origin))
    monkeypatch.setattr(checkpoint, '_decode_origin', lambda session, value: deepcopy(decoded))

    def serial(session, vm=None, channel=None):
        return (vm or session.vm).qmp.call(checkpoint.COMMAND)

    def observe(session, process, provenance, *, vm=None, memory=None, **kwargs):
        vm = vm or session.vm
        word = vm.debugger().request('m2000,2').decode()
        observed = dict(word=word)
        if memory is not None and observed != memory:
            raise ValueError('Authored native process RAM differs from checkpoint')
        cpu = dict(registers={'eip': hex(vm.pc)}, instruction_pointer=hex(vm.pc),
                   linear_pc=hex(vm.pc), cpu_mode='real', address_state={'code_bits': 16})
        return cpu, observed, deepcopy(decoded)

    monkeypatch.setattr(checkpoint, '_serial_idle', serial)
    monkeypatch.setattr(checkpoint, '_verify_process', observe)
    with Project.create(tmp_path / 'checkpoint.fdb', binary, image='com') as project:
        session = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
        vm = Machine()
        MachineContext.__init__(session, vm)
        session.project, session.rpc, session.run_id = project, vm, 'checkpoint-script-run'
        session.version = project.version()
        session.metadata = dict(backend='qemu-dos', source_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                                version_sha256=session.version['sha256'], process_disk=deepcopy(origin['process_disk']))
        session._checkpoint_source = binary
        session._checkpoint_launch = dict(checkpoint_tool='authored-img', audio_profile='off', retrace_profile='standard')
        session.guest_profile = dict(profile='authored-dos', schema=1, machine={},
            profile_sha256='2'*64, boot_image={'size': 1474560, 'sha256': '3'*64})
        session.closed, session.state = False, 'stopped'
        session._deadline, session._checkpoint_epoch, session._epoch_number = None, 0, 1
        session._runtime_epoch = session.run_id + ':process:1'
        session._process = dict(state='active', capture_epoch=session._runtime_epoch,
            source_mapping=dict(live=True, live_ranges=[]), allocation=dict(start=0x2000, end=0x3000),
            drivers=dict(headers=[dict(address=0x4000)]))
        session._staging, session._published = None, False
        session._channel, session._serial_buffer = vm.serial(None), bytearray()
        session._ready = decoded[-1]
        session.capabilities.update(save_states=True, rewind=True, frame_timeline=False,
                                    frame_key_ownership=False)
        session._history_bind()
        vm.context, vm.close_observer = session, session._on_machine_closed
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (session.run_id, session.version['id'], 'authored', None, 'stopped', json.dumps(session.metadata)))
        try:
            yield SimpleNamespace(session=session, project=project, owners=owners, vm=vm,
                                  clock=clock, binary=binary, directory=tmp_path, machine=Machine)
        finally:
            session.close()


@pytest.mark.parametrize('save,load', [('save-state','load-anchor-stone'), ('save-anchor-stone','load-state')])
def test_real_saved_script_replaces_owner_and_retains_canonical_state(process_checkpoint, save, load):
    o = process_checkpoint
    script = route(dict(op=save, max_bytes=None, **{'as':'saved'}),
                   dict(op=load, artifact='$saved.artifact', **{'as':'restored'}),
                   dict(op='assert', value='$restored.source_binding_restored', equals=True))
    stored = o.project.debug_save_script('checkpoint-route.json', script)
    result = o.session.script(script_id=stored['script_id'], timeout_ms=1000)
    assert result['ok'], result
    assert len(o.owners) == 2 and o.vm.closed and not o.session.vm.closed
    assert o.session.vm.lock is o.vm.lock
    assert o.session._runtime_epoch != 'checkpoint-script-run:process:1'
    assert result['steps'][0]['result']['metadata']['format'] == checkpoint.FORMAT
    assert result['steps'][0]['result']['name'] == ('dos-process-checkpoint.qcow2' if save == 'save-state' else 'anchor-stone.qcow2')
    assert result['steps'][1]['result']['capture_epoch'] == o.session._runtime_epoch
    artifact = result['artifact']
    saved_report = json.loads(o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()[0])
    assert saved_report == {key:value for key,value in result.items() if key != 'artifact'}
    with Project(o.project.path) as cold:
        assert json.loads(cold.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()[0]) == saved_report
    assert o.session._deadline is None and getattr(o.session,'_rpc_deadline',None) is None
    assert all(owner.operation_deadline is None and owner.qmp.operation_deadline is None
               and owner.gdb.operation_deadline is None for owner in o.owners)


def test_last_save_cannot_succeed_after_real_artifact_publication_expired(process_checkpoint, monkeypatch):
    o = process_checkpoint
    publish = o.session._artifact
    def late(name, kind, data, metadata):
        result = publish(name, kind, data, metadata)
        if kind == 'state':
            o.clock.advance(.2)
        return result
    monkeypatch.setattr(o.session, '_artifact', late)
    with pytest.raises(TimeoutError) as caught:
        execute_script(o.session, route(dict(op='save-state')), timeout_ms=100)
    result = caught.value.script_result
    assert result['ok'] is False and result['steps'][0]['error']['type'] == 'TimeoutError'
    assert result['steps'][0]['result']['kind'] == 'state'
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 1
    assert o.session.closed and len(o.owners) == 1


@pytest.mark.parametrize('protocol', ['qmp','gdb'])
def test_save_inherits_deadline_at_real_transport_boundary(process_checkpoint, protocol):
    o = process_checkpoint
    wire = o.vm.qwire if protocol == 'qmp' else o.vm.gwire
    wire.latency = .06
    with pytest.raises(TimeoutError) as caught:
        execute_script(o.session, route(dict(op='save-anchor-stone')), timeout_ms=50)
    result = caught.value.script_result
    assert result['ok'] is False and result['steps'][0]['error']['type'] == 'TimeoutError'
    assert o.clock.now <= 100.051
    assert max(wire.budgets) <= .050001
    assert 'snapshot-save' not in o.vm.qwire.requests
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 0


def test_report_publication_failure_keeps_completed_checkpoint_without_replay(process_checkpoint, monkeypatch):
    o = process_checkpoint
    publish = o.session._artifact
    primary = OSError('authored result store outage')
    def fail_report(name, kind, data, metadata):
        if kind == 'script-result':
            raise primary
        return publish(name, kind, data, metadata)
    monkeypatch.setattr(o.session, '_artifact', fail_report)
    with pytest.raises(OSError) as caught:
        o.session.script(route(dict(op='save-state')), timeout_ms=1000)
    assert caught.value is primary
    report = caught.value.script_result
    assert report['completed_steps'] == 1 and len(report['steps']) == 1
    assert report['steps'][0]['result']['kind'] == 'state'
    assert o.vm.qwire.requests.count('snapshot-save') == 1
    assert len(o.owners) == 1


def test_existing_canonical_checkpoint_uses_real_loader_and_owner_swap(process_checkpoint):
    o = process_checkpoint
    saved = o.session.save_state()
    o.vm.word, o.vm.pc = 0x2222, 0x105
    restored = o.session.load_state(saved['artifact'])
    assert restored['source_binding_restored'] is True
    assert o.session.vm.word == 0x1111 and o.session.vm.pc == 0x101
    assert len(o.owners) == 2 and o.vm.closed


def test_process_save_parent_budget_reaches_real_qmp_before_script_admission(process_checkpoint):
    o = process_checkpoint
    o.session._rpc_deadline = o.clock.now + .05
    o.vm.qwire.latency = .06
    with pytest.raises(TimeoutError):
        o.session.save_state()
    assert o.clock.now <= 100.051
    assert o.vm.qwire.requests == ['query-status']


@pytest.mark.parametrize('bad', [
    dict(op='save-state', name='../escape'), dict(op='save-anchor-stone', name='$x.name'),
    dict(op='save-state', max_bytes=True), dict(op='save-state', max_bytes=0),
    dict(op='save-state', max_bytes=1.5), dict(op='save-state', max_bytes=128*1024**2+1),
    dict(op='save-anchor-stone', max_bytes='$x.bytes'),
    dict(op='load-state', artifact='x', timeout_ms=True), dict(op='load-state', artifact='x', timeout_ms=None),
    dict(op='load-state', artifact='x', timeout_ms=0), dict(op='load-state', artifact='x', timeout_ms=600001),
    dict(op='load-state', artifact='x', timeout_ms='$x.timeout'),
    dict(op='load-anchor-stone', artifact='x', timeout_ms=1),
    dict(op='load-anchor-stone', artifact=False), dict(op='load-state', artifact=''),
])
def test_bad_literal_refuses_whole_route_before_earlier_save(process_checkpoint, bad):
    o = process_checkpoint
    with pytest.raises((ValueError,TypeError)):
        o.session.script(route(dict(op='save-state'), bad))
    assert not o.vm.qwire.requests and not o.vm.gwire.requests
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('family', ['fdisbull-qemu-dos-entry-qcow2-v1','fdisbull-qemu-raw-qcow2-v1',
    'fdisbull-qemu-owned-machine-qcow2-v1','fdisbull-qemu-dos-le-checkpoint-1'])
@pytest.mark.parametrize('reference', [False, True])
def test_wrong_family_never_reaches_fallback_or_an_earlier_save(process_checkpoint, monkeypatch, family, reference):
    o = process_checkpoint
    metadata = dict(format=family, source_sha256=o.session.metadata['source_sha256'],
                    version_sha256=o.session.metadata['version_sha256'])
    saved = o.session._artifact('other.qcow2', 'state', b'authored other family', metadata)
    monkeypatch.setattr(o.session, '_load_entry_state_v1', lambda *a,**kw: pytest.fail('Entry fallback reached'))
    if reference:
        result = execute_script(o.session, route(dict(op='load-anchor-stone',artifact='$x.artifact'),
            dict(op='save-state')), bindings={'x':saved})
        assert not result['ok'] and result['completed_steps'] == 0 and len(result['steps']) == 1
    else:
        with pytest.raises(ValueError,match='format/source/version'):
            o.session.script(route(dict(op='save-state'),dict(op='load-state',artifact=saved['artifact'])))
    assert not o.vm.qwire.requests and len(o.owners) == 1 and not o.session.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 1


@pytest.mark.parametrize('fault',['missing','source','version_hash','selected_version','kind','workspace'])
@pytest.mark.parametrize('reference',[False,True])
def test_modern_artifact_identity_refuses_before_native_or_earlier_save(process_checkpoint,fault,reference):
    o=process_checkpoint
    metadata=dict(format=checkpoint.FORMAT,source_sha256=o.session.metadata['source_sha256'],
                  version_sha256=o.session.metadata['version_sha256'])
    run=o.session.run_id
    kind='state'
    if fault=='source':metadata['source_sha256']='0'*64
    elif fault=='version_hash':metadata['version_sha256']='0'*64
    elif fault=='workspace':metadata['format']=checkpoint.WORKSPACE_FORMAT
    elif fault=='kind':kind='machine-state'
    elif fault=='selected_version':
        version=o.project.patch(o.project.regions(1)[0].start,'91')['version']
        run='another-version-run'
        with o.project.transaction(True):
            o.project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (run,version,'authored',None,'stopped','{}'))
    artifact=(o.project._debug_artifact(run,'candidate.qcow2',kind,b'authored candidate',metadata)['artifact']
              if fault!='missing' else 'missing-artifact')
    before=o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    if reference:
        result=execute_script(o.session,route(dict(op='load-state',artifact='$saved.artifact'),dict(op='save-state')),
                              bindings={'saved':{'artifact':artifact}})
        assert not result['ok'] and len(result['steps'])==1
    else:
        with pytest.raises(ValueError):
            o.session.script(route(dict(op='save-state'),dict(op='load-anchor-stone',artifact=artifact)))
        assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==before
    assert not o.vm.qwire.requests and not o.vm.gwire.requests
    assert len(o.owners)==1 and not o.session.closed


@pytest.mark.parametrize('value', [True,None,12,[],{},''])
def test_resolved_artifact_type_refuses_before_checkpoint_dispatch(process_checkpoint, value):
    o = process_checkpoint
    result = execute_script(o.session,route(dict(op='load-state',artifact='$saved.value'),dict(op='save-state')),
                            bindings={'saved':{'value':value}})
    assert not result['ok'] and result['completed_steps'] == 0
    assert not o.vm.qwire.requests and len(o.owners) == 1


@pytest.mark.parametrize('missing', ['extension','capability','tool','disk'])
def test_missing_full_profile_refuses_before_effects(process_checkpoint, missing):
    o = process_checkpoint
    if missing == 'extension':o.vm.qmp_commands=set()
    elif missing == 'capability':o.session.capabilities['save_states']=False
    elif missing == 'tool':o.session._checkpoint_launch['checkpoint_tool']=None
    else:o.vm.checkpoint_disk=None
    with pytest.raises(ValueError,match='full DOS process checkpoints'):
        o.session.script(route(dict(op='save-anchor-stone')))
    assert not o.vm.qwire.requests
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_caller_transaction_and_raw_backend_are_not_new_checkpoint_profiles(process_checkpoint):
    o = process_checkpoint
    with o.project.transaction(True):
        with pytest.raises(ValueError,match='caller transaction'):
            o.session.script(route(dict(op='save-state')))
    with pytest.raises(ValueError,match='Unsupported operation'):
        validate_script(dict(route(dict(op='save-anchor-stone')),backend='qemu-machine'))
    assert not o.vm.qwire.requests


class AdmissionLock:
    def __init__(self, clock, *, accept=False, on_acquire=None):
        self.clock, self.accept, self.on_acquire = clock, accept, on_acquire
        self.waits, self.releases = [], 0
    def acquire(self, *, timeout):
        self.waits.append(timeout)
        if self.on_acquire:self.on_acquire()
        else:self.clock.advance(timeout)
        return self.accept
    def release(self):self.releases += 1


@pytest.mark.parametrize('gate', ['timeline','machine'])
@pytest.mark.parametrize('accepted', [False,True])
def test_gate_wait_consumes_deadline_before_native_or_route_publication(process_checkpoint, gate, accepted):
    o = process_checkpoint
    lock = AdmissionLock(o.clock, accept=accepted)
    if gate == 'timeline':o.session._timeline_lock=lock
    else:o.vm.lock=lock
    with pytest.raises(TimeoutError):
        if gate == 'timeline':o.session.script(route(dict(op='save-state')),timeout_ms=50)
        else:
            o.session._rpc_deadline=100.05
            o.session.save_state()
    assert lock.waits == pytest.approx([.05]) and lock.releases == int(accepted)
    assert not o.vm.qwire.requests
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    if gate == 'timeline':assert not hasattr(o.session,'_rpc_deadline')


def test_save_rechecks_original_owner_after_lock_wait(process_checkpoint):
    o = process_checkpoint
    replacement = o.machine()
    lock = AdmissionLock(o.clock, accept=True, on_acquire=lambda:setattr(o.session,'vm',replacement))
    o.vm.lock=lock
    o.session._rpc_deadline=101.
    with pytest.raises(ValueError,match='owner changed'):
        o.session.save_state()
    assert lock.releases == 1 and not o.vm.closed and not replacement.closed
    assert not o.vm.qwire.requests and not replacement.qwire.requests
    assert replacement.operation_deadline is None
    o.session.vm=o.vm


def test_tighter_native_bounds_survive_saved_roundtrip_and_new_owner(process_checkpoint):
    o = process_checkpoint
    o.session._deadline=100.9
    o.vm.operation_deadline=100.8
    o.vm.qmp.operation_deadline=100.7
    o.vm.gdb.operation_deadline=100.6
    result=o.session.script(route(dict(op='save-state',**{'as':'saved'}),
        dict(op='load-state',artifact='$saved.artifact',timeout_ms=600000)),timeout_ms=1000)
    assert result['ok'] and len(o.owners)==2
    assert max(o.vm.qwire.budgets+o.vm.gwire.budgets)<=.600001
    assert o.session._deadline==100.9 and o.vm.operation_deadline==100.8
    assert o.vm.qmp.operation_deadline==100.7 and o.vm.gdb.operation_deadline==100.6
    # The genuine loader's restored owner must also leave the completed script's bounds.
    assert o.session.vm.operation_deadline==100.8
    assert o.session.vm.qmp.operation_deadline==100.7 and o.session.vm.gdb.operation_deadline==100.6
    assert o.session._channel.operation_deadline is None


@pytest.mark.parametrize('operation',['save-state','load-anchor-stone'])
@pytest.mark.parametrize('close_fails',[False,True])
def test_receipt_expiring_between_method_return_and_step_completion_is_failed(process_checkpoint,monkeypatch,operation,close_fails):
    o=process_checkpoint
    if operation.startswith('load-'):
        artifact=o.session.save_state()['artifact']
        step=dict(op=operation,artifact=artifact)
        method='load_anchor_stone'
    else:
        step=dict(op=operation);method='save_state'
    original=getattr(o.session,method)
    @wraps(original)
    def boundary(*args,**kwargs):
        result=original(*args,**kwargs)
        o.clock.advance(.2)
        return result
    monkeypatch.setattr(o.session,method,boundary)
    close=o.session.close
    if close_fails:
        def failed_close():
            close();raise OSError('authored late-result cleanup failure')
        monkeypatch.setattr(o.session,'close',failed_close)
    try:
        with pytest.raises(TimeoutError,match='step returned') as caught:
            o.session.script(route(step),timeout_ms=100)
    finally:monkeypatch.setattr(o.session,'close',close)
    error=caught.value
    assert error.script_result['completed_steps']==0 and error.script_result['ok'] is False
    step=error.script_result['steps'][0]
    assert step['result'] is error.result and not step['ok']
    assert o.vm.qwire.requests.count('snapshot-save')==1
    assert o.session.closed and all(vm.closed for vm in o.owners)
    assert o.session.vm._fdisbull_control_quarantine=='late checkpoint script result'
    if close_fails:assert error.machine_cleanup_error=='OSError'
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='script-result'").fetchone()[0]==0


@pytest.mark.parametrize('corrupt',[False,True])
def test_script_full_loader_preserves_selected_freeze_until_verified(process_checkpoint, corrupt):
    o=process_checkpoint
    saved=o.session.save_state()
    o.session._qemu_cpu_delta_history=dict(id='selected',valid=True,frozen=True)
    if corrupt:
        with o.project.transaction(True):
            o.project.db.execute('UPDATE debug_artifacts SET sha256=? WHERE id=?',('0'*64,saved['artifact']))
    result=o.session.script(route(dict(op='load-anchor-stone',artifact=saved['artifact'])))
    assert result['ok'] is (not corrupt)
    assert o.session._qemu_cpu_delta_history['frozen'] is corrupt
    assert len(o.owners)==(1 if corrupt else 2)
    assert getattr(o.session,'_qemu_cpu_delta_full_load_depth',0)==0


def test_late_load_event_keeps_verified_receipt_and_stops_before_next_action(process_checkpoint,monkeypatch):
    o=process_checkpoint
    saved=o.session.save_state()
    event=o.session._event
    def late(operation,value):
        event(operation,value)
        if operation=='load-state':o.clock.advance(.2)
    monkeypatch.setattr(o.session,'_event',late)
    with pytest.raises(TimeoutError) as caught:
        o.session.script(route(dict(op='load-state',artifact=saved['artifact']),dict(op='save-state')),timeout_ms=100)
    error=caught.value
    assert error.result['source_binding_restored'] is True
    assert error.script_result['steps'][0]['result'] is error.result
    assert len(error.script_result['steps'])==1 and len(o.owners)==2
    assert all(vm.closed for vm in o.owners)
    assert o.vm.qwire.requests.count('snapshot-save')==1


@pytest.mark.parametrize('change',['lock','epoch'])
def test_post_load_owner_change_retains_actual_receipt_without_closing_unrelated_owner(process_checkpoint,monkeypatch,change):
    o=process_checkpoint
    saved=o.session.save_state()
    original=o.session.load_anchor_stone
    observed=[]
    @wraps(original)
    def moved(*args,**kwargs):
        result=original(*args,**kwargs)
        observed.append(result)
        restored=o.session.vm
        unrelated=o.machine()
        if change=='epoch':
            unrelated.lock=restored.lock
            o.session._advance_epoch()
        restored.close_observer=None
        restored.close()
        o.session.vm=o.session.rpc=unrelated
        return result
    monkeypatch.setattr(o.session,'load_anchor_stone',moved)
    report=o.session.script(route(dict(op='load-anchor-stone',artifact=saved['artifact']),dict(op='save-state')))
    assert not report['ok'] and len(report['steps'])==1
    assert report['steps'][0]['error']['type']=='ValueError'
    assert report['steps'][0]['result'] is observed[0]
    assert observed[0]['source_binding_restored'] is True
    assert len(o.owners)==3 and not o.owners[-1].closed
    assert not o.owners[-1].qwire.requests


def test_late_report_keeps_real_committed_report_and_does_not_repeat_save(process_checkpoint,monkeypatch):
    o=process_checkpoint
    publish=o.session._artifact
    def late(name,kind,data,metadata):
        result=publish(name,kind,data,metadata)
        if kind=='script-result':o.clock.advance(.2)
        return result
    monkeypatch.setattr(o.session,'_artifact',late)
    with pytest.raises(TimeoutError) as caught:
        o.session.script(route(dict(op='save-anchor-stone')),timeout_ms=100)
    result=caught.value.script_result
    assert result['completed_steps']==1 and result['ok'] is True
    stored=json.loads(o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(result['artifact'],)).fetchone()[0])
    assert stored=={k:v for k,v in result.items() if k!='artifact'}
    assert o.vm.qwire.requests.count('snapshot-save')==1


def json_request(o, script):
    return dict(method='debug-script',params=dict(project=str(o.project.path),run=o.session.run_id,
                context='machine',script=script,timeout_ms=1000))


def test_json_roundtrip_projects_all_addresses_without_altering_canonical_store(process_checkpoint,monkeypatch):
    o=process_checkpoint
    workspace=DebugWorkspace();workspace.sessions[o.session.run_id]=o.session
    captured=[];original=o.session.script
    @wraps(original)
    def once(*args,**kwargs):
        value=original(*args,**kwargs);captured.append(value);return value
    monkeypatch.setattr(o.session,'script',once)
    try:
        reply=respond(json_request(o,route(dict(op='save-anchor-stone',**{'as':'saved'}),
            dict(op='load-state',artifact='$saved.artifact'))),debugger=workspace)
    finally:workspace.sessions.clear()
    assert reply['ok'] and len(captured)==1
    assert reply['result']==public_addresses(captured[0])
    canonical=captured[0]['steps'][1]['result']['process']
    public=reply['result']['steps'][1]['result']['process']
    assert canonical['allocation']['start']==0x2000 and public['allocation']['start']=='0x2000'
    assert canonical['allocation']['end']==0x3000 and public['allocation']['end']=='0x3000'
    assert canonical['drivers']['headers'][0]['address']==0x4000 and public['drivers']['headers'][0]['address']=='0x4000'
    saved=json.loads(o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(captured[0]['artifact'],)).fetchone()[0])
    assert saved=={k:v for k,v in captured[0].items() if k!='artifact'}


def test_json_failure_exports_primary_native_result_and_prefix_without_reexecution(process_checkpoint,monkeypatch):
    from fdisbull.output_limits import OutputPolicy, output_policy_context
    o=process_checkpoint
    primary=RuntimeError('authored native save acknowledgement loss')
    primary.result=dict(native='snapshot-save',address=0x4321,prefix='x'*5000)
    send=o.vm.qwire.sendall
    def lost(data):
        send(data)
        if json.loads(data)['execute']=='snapshot-save':raise primary
    monkeypatch.setattr(o.vm.qwire,'sendall',lost)
    publish=o.session._artifact
    def publication(name,kind,data,metadata):
        if kind=='script-result':raise OSError('authored report store failure')
        return publish(name,kind,data,metadata)
    monkeypatch.setattr(o.session,'_artifact',publication)
    close=o.session.close
    def close_failure():
        close();raise OSError('authored secondary close failure')
    monkeypatch.setattr(o.session,'close',close_failure)
    workspace=DebugWorkspace();workspace.sessions[o.session.run_id]=o.session
    policy=OutputPolicy(4096,artifact_dir=o.directory/'outputs')
    try:
        with output_policy_context(policy):
            reply=respond(json_request(o,route(dict(op='save-state'),dict(op='save-anchor-stone'))),debugger=workspace)
            assert not reply['ok'] and reply['error']['type']=='RuntimeError'
            marker=reply['output'];assert marker['retry_safe'] is False
            output=o.directory/'native-failure.json'
            before=list(o.vm.qwire.requests)
            exported=respond(dict(method='output-export',params=dict(artifact=marker['artifact']['id'],output=str(output))))
            assert exported['ok'] and o.vm.qwire.requests==before
            raw=output.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==marker['artifact']['sha256']
            error=json.loads(raw)['error']
            assert error['result']==primary.result and error['result']['address']==0x4321
            assert error['script_result']==primary.script_result
            assert len(error['script_result']['steps'])==1
            assert error['script_result']['steps'][0]['result']==primary.result
            assert error['script_publication_error']['type']=='OSError'
            assert error['machine_cleanup_error']=='OSError'
            assert error['script_result']['steps'][0]['checkpoint_cleanup']['machine_cleanup_error']=='OSError'
        assert primary.machine_cleanup_error=='OSError' and o.vm.closed
        assert o.vm.qwire.requests.count('snapshot-save')==1
    finally:
        workspace.sessions.clear();monkeypatch.setattr(o.session,'close',close)
