"""No-VM witnesses for original-source facts at public machine boundaries."""
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull import qemu_machine as q
from fdisbull.qemu_layers import LAYER_COMMANDS, QemuLayerSessionMixin
from test_runtime_tracking import setup
from test_runtime_tracking_containment import contained


class Tracker:
    def __init__(self):
        self.events = []
        self.current = True
        self.closed = False

    def before_execution(self, reason):
        self.events.append(('invalidate', reason))
        self.current = False

    def after_stop(self, reason):
        self.events.append(('observe', reason))

    def close(self, reason):
        self.events.append(('close', reason))
        self.current = False
        self.closed = True

    def status(self):
        return dict(current_bindings=int(self.current), closed=self.closed)


class Remote:
    socket = object()

    def __init__(self):
        self.calls = []
        self.ram = {0x200: 0x90}

    def execute(self, command, timeout_ms):
        self.calls.append(command)
        return b'S02', False

    def memory(self, address, length, *, space):
        return bytes(self.ram[address + index] for index in range(length))

    def close(self):
        self.socket = None


class Peer:
    socket = object()

    def __init__(self, remote):
        self.remote = remote
        self.running = False
        self.generation = 0
        self.at_write = None

    def call(self, method, args=None):
        if method == 'query-status':
            return dict(running=self.running, status='running' if self.running else 'paused')
        if method == 'stop':
            self.running = False
            return {}
        if method == 'x-fdisbull-layer-observe':
            return dict(generation=self.generation, **{'execution-bytes': 0})
        if method == 'x-fdisbull-layer-configure':
            assert self.at_write is not None
            self.at_write()
            for chunk in args['ram']:
                for offset, value in enumerate(bytes.fromhex(chunk['after'])):
                    self.remote.ram[chunk['address'] + offset] = value
            self.generation += 1
            return dict(generation=self.generation,
                        **{'ram-bytes': sum(len(bytes.fromhex(chunk['after'])) for chunk in args['ram']),
                           'execution-bytes': 0})
        raise AssertionError(method)

    def close(self):
        self.socket = None


class Context(QemuLayerSessionMixin, q.MachineContext):
    def __init__(self):
        self.remote = Remote()
        peer = Peer(self.remote)
        vm = SimpleNamespace(lock=threading.RLock(), gdb=self.remote, qmp=peer,
                             debugger=lambda: self.remote, close=lambda: None,
                             machine_stopped=True, qmp_commands=LAYER_COMMANDS,
                             machine_configuration=dict(cpus=1))
        super().__init__(vm)
        self._automatic_runtime_tracker = Tracker()
        self.journal = []

    def registers(self):
        return dict(linear_pc='0x20100', cpu_mode='real',
                    registers=dict(cs='0x2000', eip='0x100'))

    def _event(self, operation, value):
        self.journal.append((operation, value))


def test_pause_refreshes_mapping_after_asynchronous_execution():
    session = Context()
    session.vm.qmp.running = True
    session._automatic_runtime_tracker.current = False
    result = session.pause()
    assert result['state'] == 'stopped'
    assert session._automatic_runtime_tracker.events == [('observe', 'machine-pause')]


def test_one_public_run_records_one_native_execution_event():
    session = Context()
    session.project = object()
    result = session.run(timeout_ms=100)
    assert session.remote.calls == ['c']
    assert result['outcome'] == 'stopped'
    assert [name for name, _ in session.journal] == ['machine-run']


def test_layer_write_retires_current_original_mapping_before_native_mutation():
    session = Context()
    session.run_id = 'authored-run'
    session.version = dict(id=1)
    definition = dict(version=1, kind='ram',
                      patches=[dict(address=0x200, expected_hex='90', data_hex='cc')],
                      native_binding=dict(run='authored-run', epoch='authored-run', spans=[(0x200, 1)]))
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False),
                                      debug_layer_info=lambda identifier: definition)
    session.vm.qmp.at_write = lambda: _require_invalidated(session)
    result = session.layers(active=['authored-layer'])
    assert session.remote.ram[0x200] == 0xcc
    assert result['ram_bytes'] == 1
    assert session._automatic_runtime_tracker.events == [
        ('invalidate', 'machine-layer-write'), ('observe', 'machine-layer-transition')]


def _require_invalidated(session):
    assert not session._automatic_runtime_tracker.current
    assert session.remote.ram[0x200] == 0x90


def test_raw_owner_close_retires_tracker_without_explicit_session_close(tmp_path, monkeypatch):
    """Transport failures close the native owner directly, bypassing session.close."""
    from fdisbull.project import Project
    from fdisbull import debugger

    original_owner = q.QemuMachine
    owner = original_owner.__new__(original_owner)
    owner.lock = threading.RLock()
    owner.gdb = Remote()
    owner.qmp = Peer(owner.gdb)
    owner.process = owner.temporary = None
    owner._channels = []
    owner.close_observer = None
    owner.inputs = {}
    owner.qmp_commands = frozenset()
    owner.machine_configuration = dict(cpus=1)
    monkeypatch.setattr(q, 'QemuMachine', lambda *args, **options: owner)
    tracker = Tracker()
    monkeypatch.setattr(debugger, '_attach_runtime_tracking',
                        lambda session: setattr(session, '_automatic_runtime_tracker', tracker))
    image = tmp_path / 'authored.img'
    image.write_bytes(bytes(510) + b'\x55\xaa')
    with Project.create(tmp_path / 'machine.fdb', image, arch='x86', bits=16) as project:
        session = q.MachineDebugSession(project, '/not-executed', boot_image=image)
        try:
            owner.close()
            assert tracker.closed and not tracker.current
        finally:
            session.close()


def test_raw_cold_restore_retires_old_tracker_and_observes_fresh_epoch(tmp_path, monkeypatch):
    """Host restore orchestration only; no claim about native qcow compatibility."""
    from copy import deepcopy
    from fdisbull.project import Project
    from fdisbull import qemu_checkpoint, runtime_tracking

    original_owner = q.QemuMachine
    owners = []

    def owner_factory(*args, **options):
        owner = original_owner.__new__(original_owner)
        owner.lock = threading.RLock()
        owner.gdb = Remote()
        owner.qmp = Peer(owner.gdb)
        owner.process = owner.temporary = None
        owner._channels = []
        owner.close_observer = None
        owner.inputs = {}
        owner.qmp_commands = frozenset()
        owner.machine_configuration = dict(cpus=1, clock_profile=dict(profile='standard'))
        owner.checkpoint_disk = tmp_path / 'authored.qcow2'
        owner.operation_deadline = None
        owners.append(owner)
        return owner

    trackers = []

    def tracker_factory(session):
        tracker = Tracker()
        trackers.append(tracker)
        return tracker

    registers = dict(registers=dict(eip='0x100'), instruction_pointer='0x100',
                     cpu_mode='real', address_state=dict(code_bits=16))
    jobs = []
    monkeypatch.setattr(q, 'QemuMachine', owner_factory)
    monkeypatch.setattr(q.MachineContext, 'registers', lambda self: deepcopy(registers))
    monkeypatch.setattr(runtime_tracking, 'AutomaticRuntimeTracker', tracker_factory)
    monkeypatch.setattr(qemu_checkpoint, 'snapshot_job',
                        lambda owner, operation, **options: jobs.append((owner, operation)))
    image = tmp_path / 'authored.img'
    image.write_bytes(bytes(510) + b'\x55\xaa')
    with Project.create(tmp_path / 'restore.fdb', image, arch='x86', bits=16) as project:
        session = q.MachineDebugSession(project, '/not-executed', boot_image=image,
                                       checkpoint_tool='/not-executed')
        try:
            metadata = dict(format='fdisbull-qemu-raw-qcow2-v1', tag='authored-tag',
                            source_sha256=session.metadata['source_sha256'],
                            version_sha256=session.metadata['version_sha256'],
                            backend=session.backend_id, runtime_inputs=owners[0].inputs,
                            machine_configuration=owners[0].machine_configuration,
                            guest_profile=None, registers=registers)
            artifact = session._artifact('authored-state.qcow2', 'state', b'authored host-only state', metadata)
            old_tracker = trackers[0]
            result = session.load_state(artifact['artifact'])
            assert len(owners) == 2 and jobs == [(owners[1], 'load')]
            assert session.vm is owners[1] and session._runtime_epoch
            assert old_tracker.closed and not old_tracker.current
            assert len(trackers) == 2 and session._automatic_runtime_tracker is trackers[1]
            assert not trackers[1].closed
            assert trackers[1].events == [('observe', 'session-start')]
            assert result['checkpoint_epoch'] == 1 and result['source_binding_restored'] is False
        finally:
            session.close()


def test_unclassified_arrived_stop_retires_continuity_without_replay(contained):
    """A native stop receipt survives even when its register observation fails."""
    project, session, _, _, tracker = contained
    old_task = tracker.status()['sources'][0]['task']
    session._automatic_runtime_tracker = tracker
    session._automatic_internal_pending = dict(pc='authored-prior-pending')
    error = ValueError('authored register observation failure')
    receipt = dict(context='machine', outcome='stopped', registers=None,
                   session=dict(stop_reason=dict(native_reply='T05', classification_complete=False)))
    error.result = receipt
    dispatched = []

    def stopped_but_unclassified(command, timeout_ms):
        dispatched.append(command)
        raise error

    session._execute_once = stopped_but_unclassified
    reasons = []
    before = tracker.before_execution

    def remember_reason(reason):
        reasons.append(reason)
        return before(reason)

    tracker.before_execution = remember_reason
    with pytest.raises(ValueError) as caught:
        q.MachineContext._native_execute(session, None, 'c', time.monotonic() + 1)
    assert caught.value is error and caught.value.result is receipt
    assert dispatched == ['c']
    assert 'machine-restore-unobserved-stop' in reasons
    assert session._automatic_internal_pending is None
    assert project._mapping_task(old_task)['ended'] is not None
    assert project.runtime_mappings(old_task)['bindings'] == []
    assert tracker.provider is None and not tracker.internal_breakpoints
    assert not tracker.generations and not tracker.observed_creations
    tracker.after_stop('fresh source stop after the failed classification')
    assert tracker.status()['sources'][0]['task'] != old_task
