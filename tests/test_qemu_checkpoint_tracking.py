"""Public raw checkpoint composition with authored lifecycle tracking.

The native transport and snapshot job are boundaries here; the Project,
tracker, mapping journal, checkpoint artifact and public save/load are real.
"""
from copy import deepcopy
import struct
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.debugger import _attach_runtime_tracking, _tracking_callback
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_machine import MachineContext, MachineDebugSession
from test_runtime_mapping_snapshots import capture
from test_runtime_tracking import Provider, Session, setup
from test_runtime_tracking_physical import _certificate


def qcow_bytes():
    data = bytearray(104)
    struct.pack_into('>IIQIIQI', data, 0, 0x514649fb, 3, 0, 0, 16, 1474560, 0)
    struct.pack_into('>I', data, 100, 104)
    return bytes(data)


class Remote:
    def __init__(self, machine):
        self.machine = machine
        self.socket = object()
        self.operation_deadline = None
        self.requests = []
        self.fail = None

    def request(self, command, **kwargs):
        self.requests.append(command)
        op, kind, rest = command[0], int(command[1]), command[3:]
        address, length = (int(value, 16) for value in rest.split(','))
        key = (kind, address, length)
        if op == 'z':
            self.machine.points.discard(key)
        else:
            self.machine.points.add(key)
        if self.fail == op:
            raise DebuggerError('authored lost ' + op + ' acknowledgement')
        return b'OK'


class Machine:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.points = set()
        self.gdb = Remote(self)
        self.qmp = SimpleNamespace(socket=object(), operation_deadline=None,
            call=lambda *args, **kwargs: dict(running=False, status='paused'))
        self.closed = False
        self.operation_deadline = None
        self.close_observer = None
        self.process = SimpleNamespace(poll=lambda: 0 if self.closed else None)
        self.checkpoint_disk = path
        path.write_bytes(qcow_bytes())
        self.checkpoint_virtual_size = 1474560
        self.machine_configuration = dict(cpus=1, memory_mib=16,
            clock_profile=dict(profile='standard'))
        self.inputs = dict(authored='immutable input')
        self.qmp_commands = frozenset()
        self.cpu = dict(registers=dict(rip='0x123ff0'), instruction_pointer='0x123ff0',
            linear_pc='0x123ff0', cpu_mode='protected', address_state=dict(code_bits=32))

    def debugger(self):
        return self.gdb

    def close(self):
        self.closed = True


class TrackedMachine(MachineDebugSession):
    def __init__(self, project, path):
        Session.__init__(self, project, owned=False)
        self.vm = Machine(path)
        self.vm.context = self
        self.rpc = self.vm
        self.next_bp = 1
        self.closed = False
        self._checkpoint_launch = dict(checkpoint_tool='authored-qemu-img')
        self._checkpoint_epoch = 0
        self.guest_profile = None
        self.metadata.update(version_sha256=self.version['sha256'])
        self._automatic_internal_pending = None

    _artifact = Session._artifact
    def memory_snapshot(self, address, *, length, task_id, name):
        pages = [dict(linear='0x123000', physical=hex(self.physical), entries=[]),
                 dict(linear='0x124000', physical=hex(self.physical+0x3000), entries=[])]
        identifier = capture(self.project, self.memory, start=address, task=task_id,
                             pages=pages, epoch=self._runtime_epoch)
        self.snapshots.append(identifier)
        return dict(artifact=identifier)

    def registers(self):
        return deepcopy(self.vm.cpu)

    def close(self):
        _tracking_callback(self, 'close', 'authored checkpoint cleanup')
        self.vm.close()
        self.closed = True


@pytest.fixture
def tracked(setup, tmp_path, monkeypatch):
    project, _, match = setup
    session = TrackedMachine(project, tmp_path / 'owned.qcow2')
    provider = Provider()
    provider.session = session
    provider.qualify_physical = lambda identifier, native: _certificate(project, identifier, native)
    monkeypatch.setattr('fdisbull.runtime_desqview.discover', lambda _: provider)
    _attach_runtime_tracking(session)
    tracker = session._automatic_runtime_tracker
    assert tracker.status()['state'] == 'qualified-stopped-bindings'
    jobs = []

    def snapshot(machine, operation, **kwargs):
        assert not machine.points, 'observer controls leaked into checkpoint'
        jobs.append((operation, machine))
        return dict(status='concluded')

    monkeypatch.setattr('fdisbull.qemu_checkpoint.snapshot_job', snapshot)
    return SimpleNamespace(project=project, session=session, provider=provider,
                           tracker=tracker, jobs=jobs, directory=tmp_path)


def test_public_save_suspends_only_observer_controls_and_preserves_episode(tracked):
    o = tracked
    session = o.session
    old_status = o.tracker.status()
    old_points = deepcopy(session.breakpoints)
    remote = session.vm.gdb
    remote.requests.clear()
    saved = session.save_state()
    assert [operation for operation, _ in o.jobs] == ['save']
    assert remote.requests == ['z1,5000,1', 'Z1,5000,1']
    assert session.breakpoints == old_points
    assert session.vm.points == {(1, 0x5000, 1)}
    assert o.tracker.status() == old_status
    assert saved['metadata']['source_binding_restored'] is False
    assert saved['metadata']['runtime_tracking_controls_serialized'] is False
    assert not session.closed


@pytest.mark.parametrize('change', ['user', 'alias', 'hook', 'owner', 'kind',
    'address', 'missing', 'foreign_tracker', 'foreign_provider', 'closed', 'fenced',
    'busy', 'pending', 'layers', 'input'])
def test_checkpoint_refuses_unowned_or_pending_controls_without_native_mutation(tracked, change):
    o = tracked
    s = o.session
    identifier = next(iter(s.breakpoints))
    if change in ('user', 'alias'):
        s.breakpoint(0x5000 if change == 'alias' else 0x9000)
    elif change == 'hook':
        s._qemu_hooks = {identifier: dict(hook='authored-hook')}
    elif change in ('owner', 'kind', 'address'):
        s.breakpoints[identifier][change] = dict(owner='user', kind=2, address=0x5001)[change]
    elif change == 'missing':
        del s.breakpoints[identifier]
    elif change == 'foreign_tracker':
        o.tracker.session = object()
    elif change == 'foreign_provider':
        o.provider.session = object()
    elif change in ('closed', 'fenced', 'busy'):
        setattr(o.tracker, change, True)
    elif change == 'pending':
        s._automatic_internal_pending = dict(ids=[identifier], pc='0x5000',
            registers=dict(rip='0x5000'), result=dict(already_recorded=True))
    elif change == 'layers':
        s._layer_active = ['authored-layer']
    else:
        s.vm._physical_input = dict(pending=[1], leases={}, valid=True)
    points = deepcopy(s.breakpoints)
    pending = deepcopy(s._automatic_internal_pending)
    s.vm.gdb.requests.clear()
    with pytest.raises(ValueError):
        s.save_state()
    assert s.vm.gdb.requests == [] and o.jobs == []
    assert s.breakpoints == points and s._automatic_internal_pending == pending
    assert not s.closed


@pytest.mark.parametrize('stage', ['z', 'Z'])
def test_uncertain_control_ack_closes_owner_without_publishing_state(tracked, stage):
    o = tracked
    o.session.vm.gdb.fail = stage
    with pytest.raises(DebuggerError, match='authored lost'):
        o.session.save_state()
    assert o.session.closed and o.session.vm.closed
    assert getattr(o.session.vm, '_fdisbull_control_quarantine', None)
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 0
    assert len(o.jobs) == (stage == 'Z')


def install_cold_transport(o, monkeypatch):
    created = []

    def launch(**kwargs):
        incoming = kwargs['_checkpoint_image'].read_bytes()
        machine = Machine(o.directory / ('cold-'+str(len(created))+'.qcow2'))
        machine.checkpoint_disk.write_bytes(incoming)
        created.append(machine)
        return machine

    monkeypatch.setattr('fdisbull.qemu_machine.QemuMachine', launch)
    monkeypatch.setattr(MachineContext, 'registers', lambda self: deepcopy(self.vm.cpu))
    return created


def test_public_cold_restore_retires_old_epoch_and_requalifies_fresh_snapshots(tracked, monkeypatch):
    from fdisbull.project import Project

    o = tracked
    s = o.session
    old = o.tracker.status()['sources'][0]
    old_bindings = o.project.runtime_mappings(old['task'])['bindings']
    old_epoch = s._runtime_epoch
    old_snapshot = old['physical_qualification']['snapshots'][0]
    old_vm = s.vm
    saved = s.save_state()
    created = install_cold_transport(o, monkeypatch)
    old_vm.gdb.requests.clear()
    result = s.load_state(saved['artifact'])
    assert result['source_binding_restored'] is False and result['checkpoint_epoch'] == 1
    assert old_vm.closed and s.vm is created[0] and not s.closed
    assert old_vm.gdb.requests == ['z1,5000,1']
    assert [kind for kind, _ in o.jobs] == ['save', 'load']
    assert s._runtime_epoch != old_epoch and s._automatic_internal_pending is None
    assert o.tracker.closed and o.project._mapping_task(old['task'])['ended'] is not None
    assert not o.project.runtime_mappings(old['task'])['bindings']
    fresh = s._automatic_runtime_tracker.status()['sources'][0]
    assert fresh['task'] != old['task']
    assert fresh['identity']['process_episode']['incarnation'] != old['identity']['process_episode']['incarnation']
    assert fresh['physical_qualification']['qualified'] is True
    assert not set(fresh['physical_qualification']['snapshots']).intersection(old['physical_qualification']['snapshots'])
    assert s.vm.points == {(1, 0x5000, 1)}
    bindings = o.project.runtime_mappings(fresh['task'])['bindings']
    assert all(b['physical_qualification']['snapshot'] != old_snapshot for b in bindings)
    assert not {b['id'] for b in bindings}.intersection(b['id'] for b in old_bindings)
    with pytest.raises(ValueError):
        o.project.runtime_map_snapshot(fresh['task'], old_snapshot, 'region:0', 0, 16)
    with Project(o.project.path) as cold:
        assert cold.runtime_mappings(fresh['task'])['bindings'] == bindings
        assert not cold.runtime_mappings(old['task'])['bindings']
        assert len(cold.runtime_tasks()['tasks']) == 2


@pytest.mark.parametrize('change', ['user', 'pending'])
def test_restore_refuses_before_new_owner_or_control_mutation(tracked, monkeypatch, change):
    o = tracked
    saved = o.session.save_state()
    created = install_cold_transport(o, monkeypatch)
    if change == 'user':
        o.session.breakpoint(0x9000)
    else:
        o.session._automatic_internal_pending = dict(already_recorded=True)
    o.session.vm.gdb.requests.clear()
    with pytest.raises(ValueError):
        o.session.load_state(saved['artifact'])
    assert created == [] and o.session.vm.gdb.requests == []
    assert not o.session.closed and not o.tracker.closed


def test_checkpoint_budget_covers_provider_snapshot_repair_and_restores_bounds(tracked, monkeypatch):
    o = tracked
    s = o.session
    parent = time.monotonic()+10
    s._rpc_deadline = parent
    s.vm.operation_deadline = parent+1
    s.vm.qmp.operation_deadline = parent+2
    s.vm.gdb.operation_deadline = parent+3
    previous = [s.vm.operation_deadline, s.vm.qmp.operation_deadline, s.vm.gdb.operation_deadline]
    checks = []

    def coverage():
        bound = s.vm.operation_deadline
        assert bound <= parent
        assert s.vm.qmp.operation_deadline == s.vm.gdb.operation_deadline == bound
        checks.append(bound)

    monkeypatch.setattr(o.provider, 'validate_coverage', coverage)
    s.save_state()
    assert len(checks) == 1
    assert [s.vm.operation_deadline, s.vm.qmp.operation_deadline, s.vm.gdb.operation_deadline] == previous
    assert s._rpc_deadline == parent


def test_expired_parent_refuses_before_provider_or_controls(tracked, monkeypatch):
    o = tracked
    o.session._rpc_deadline = time.monotonic()-1
    monkeypatch.setattr(o.provider, 'validate_coverage', lambda: pytest.fail('late provider I/O'))
    o.session.vm.gdb.requests.clear()
    with pytest.raises(TimeoutError):
        o.session.save_state()
    assert not o.jobs and not o.session.vm.gdb.requests and not o.session.closed


def test_close_failure_does_not_replace_lost_control_ack(tracked, monkeypatch):
    o = tracked
    o.session.vm.gdb.fail = 'z'

    def close():
        o.session.vm.close()
        raise RuntimeError('authored secondary cleanup')

    monkeypatch.setattr(o.session, 'close', close)
    with pytest.raises(DebuggerError, match='authored lost z') as caught:
        o.session.save_state()
    assert caught.value.machine_cleanup_error == 'RuntimeError'
    assert o.session.vm.closed


def test_expiry_during_snapshot_does_not_renew_repair_budget(tracked, monkeypatch):
    import fdisbull.qemu_machine as module

    o = tracked
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    o.session._rpc_deadline = 105.0

    def snapshot(machine, operation, **kwargs):
        assert not machine.points and kwargs['timeout_ms'] <= 5000
        clock[0] = 106.0

    monkeypatch.setattr('fdisbull.qemu_checkpoint.snapshot_job', snapshot)
    o.session.vm.gdb.requests.clear()
    with pytest.raises(TimeoutError, match='deadline'):
        o.session.save_state()
    assert o.session.vm.gdb.requests == ['z1,5000,1']
    assert o.session.closed and o.session.vm.closed
    assert getattr(o.session.vm, '_fdisbull_control_quarantine', None)
    assert o.session.vm.operation_deadline is None


def test_restore_keeps_tighter_old_transport_bound_through_retirement(tracked, monkeypatch):
    o = tracked
    s = o.session
    saved = s.save_state()
    created = install_cold_transport(o, monkeypatch)
    old = s.vm
    parent = time.monotonic()+5
    old.gdb.operation_deadline = parent
    previous_close = o.tracker.close
    retired = []

    def close(reason):
        assert s.vm is old
        assert old.operation_deadline == old.qmp.operation_deadline == old.gdb.operation_deadline
        assert old.operation_deadline <= parent
        assert created[0].operation_deadline <= parent
        retired.append(reason)
        previous_close(reason)

    monkeypatch.setattr(o.tracker, 'close', close)
    s.load_state(saved['artifact'], timeout_ms=60000)
    assert retired == ['machine-checkpoint-restore']
    assert old.operation_deadline is None and old.qmp.operation_deadline is None
    assert old.gdb.operation_deadline == parent


def test_late_artifact_publication_retains_evidence_but_never_returns_success(tracked, monkeypatch):
    import fdisbull.qemu_machine as module

    o = tracked
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    o.session._rpc_deadline = 105.0
    original = o.session._artifact

    def publish(*args):
        result = original(*args)
        clock[0] = 106.0
        return result

    monkeypatch.setattr(o.session, '_artifact', publish)
    with pytest.raises(TimeoutError, match='deadline'):
        o.session.save_state()
    assert o.session.closed and o.session.vm.closed
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 1


@pytest.mark.parametrize('change', ['epoch', 'registry', 'process'])
def test_snapshot_cannot_change_control_ownership_before_repair(tracked, monkeypatch, change):
    o = tracked

    def snapshot(machine, operation, **kwargs):
        if change == 'epoch':
            o.session._runtime_epoch = 'foreign-epoch'
        elif change == 'registry':
            next(iter(o.session.breakpoints.values()))['owner'] = 'user'
        else:
            machine.process = SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr('fdisbull.qemu_checkpoint.snapshot_job', snapshot)
    o.session.vm.gdb.requests.clear()
    with pytest.raises(DebuggerError, match='ownership changed'):
        o.session.save_state()
    assert o.session.vm.gdb.requests == ['z1,5000,1']
    assert o.session.closed and o.session.vm.closed
    assert getattr(o.session.vm, '_fdisbull_control_quarantine', None)


@pytest.mark.parametrize('operation', ['save', 'load'])
def test_failed_native_coverage_retires_authority_before_checkpoint_controls(tracked, operation):
    o = tracked
    s = o.session
    task = o.tracker.status()['sources'][0]['task']
    saved = s.save_state() if operation == 'load' else None
    jobs = len(o.jobs)
    o.provider.fingerprint_failure = True
    s.vm.gdb.requests.clear()
    with pytest.raises(ValueError, match='authored manager fingerprint changed'):
        if operation == 'save':
            s.save_state()
        else:
            s.load_state(saved['artifact'])
    assert s.closed and s.vm.closed and o.tracker.closed
    assert getattr(s.vm, '_fdisbull_control_quarantine', None)
    assert o.tracker.status()['current_bindings'] == 0
    assert not o.project.runtime_mappings(task)['bindings']
    assert o.project._mapping_task(task)['ended'] is not None
    assert len(o.jobs) == jobs and s.vm.gdb.requests == []


def test_coverage_failure_preserves_primary_when_retirement_cleanup_also_fails(tracked, monkeypatch):
    o = tracked
    original = o.session.close

    def close():
        original()
        raise RuntimeError('authored retirement cleanup failure')

    monkeypatch.setattr(o.session, 'close', close)
    o.provider.fingerprint_failure = True
    with pytest.raises(ValueError, match='authored manager fingerprint changed') as caught:
        o.session.save_state()
    assert caught.value.machine_cleanup_error == 'RuntimeError'
    assert o.session.vm.closed and o.tracker.closed
