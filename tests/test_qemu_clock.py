"""Machine instruction observations never stand in for elapsed guest time."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import (MachineClockMixin, machine_clock_arguments,
                                 machine_clock_configuration)
from test_qemu_owned_checkpoint import (runtime as owned_checkpoint_runtime,
                                        rewrite as rewrite_owned_archive)


class ClockPeer:
    def __init__(self, values=(), *, running=False):
        self.values = iter(values)
        self.running = running
        self.calls = []

    def call(self, command):
        self.calls.append(command)
        if command == 'query-status':
            return dict(running=self.running, status='running' if self.running else 'paused')
        assert command == 'query-replay'
        return next(self.values)


class ClockContext(MachineClockMixin):
    context_id = 'machine'
    run_id = 19
    project = None

    def __init__(self, profile='instruction', values=(), *, running=False):
        self.peer = ClockPeer(values, running=running)
        self.vm = SimpleNamespace(
            qmp=self.peer, machine_stopped=not running,
            machine_configuration={'cpus': 1,
                                   'clock_profile': machine_clock_configuration(profile, 1)},
            closed=False)
        def close():
            self.vm.closed = True
            self.vm.qmp = None
        self.vm.close = close
        self.events = []

    def _event(self, operation, result):
        self.events.append((operation, deepcopy(result)))


def test_explicit_instruction_profile_selects_single_tcg_without_recording():
    profile = machine_clock_configuration('instruction', 1)
    assert profile['profile'] == 'instruction'
    assert profile['shift'] == 7 and profile['sleep'] is False and profile['align'] is False
    assert profile['read_source'] == 'query-replay.icount'
    assert machine_clock_arguments('instruction') == [
        '-accel', 'tcg,thread=single', '-icount', 'shift=7,align=off,sleep=off']
    assert machine_clock_arguments('standard') == ['-accel', 'tcg,thread=multi']
    assert machine_clock_configuration('standard', 2)['read_source'] is None


def test_virtual_profile_pins_vm_backed_rtc_without_fixing_the_initial_calendar():
    assert machine_clock_configuration('virtual', 1)['rtc'] == {
        'base': 'utc', 'clock': 'vm', 'driftfix': 'none'}
    assert machine_clock_arguments('virtual') == [
        '-accel', 'tcg,thread=single', '-icount', 'shift=7,align=off,sleep=off',
        '-rtc', 'base=utc,clock=vm,driftfix=none']
    # These profiles retain their pre-existing RTC defaults and launch identity.
    for profile in ('standard', 'instruction'):
        assert 'rtc' not in machine_clock_configuration(profile, 1)
        assert '-rtc' not in machine_clock_arguments(profile)


def test_legacy_virtual_descriptor_is_closed_before_any_native_observation():
    context = ClockContext('virtual')
    context.vm.machine_configuration['clock_profile'].pop('rtc', None)
    def unexpected(command):
        context.peer.calls.append(command)
        pytest.fail('Legacy RTC descriptor reached native observation: ' + command)
    context.vm.qmp = SimpleNamespace(call=unexpected)
    with pytest.raises(DebuggerError, match='clock profile'):
        context.clock_observe()
    assert context.vm.closed and context.peer.calls == [] and context.events == []


@pytest.mark.parametrize('rtc', [None, {},
    {'base': 'localtime', 'clock': 'vm', 'driftfix': 'none'},
    {'base': 'utc', 'clock': 'host', 'driftfix': 'none'},
    {'base': 'utc', 'clock': 'rt', 'driftfix': 'none'},
    {'base': 'utc', 'clock': 'vm', 'driftfix': 'slew'},
    {'base': 'utc', 'clock': 'vm', 'driftfix': 'none', 'unrecorded': True},
])
def test_forged_virtual_rtc_policy_is_closed_before_any_native_observation(rtc):
    context = ClockContext('virtual')
    context.vm.machine_configuration['clock_profile']['rtc'] = rtc
    with pytest.raises(DebuggerError, match='clock profile'):
        context.clock_observe()
    assert context.vm.closed and context.peer.calls == [] and context.events == []


@pytest.mark.parametrize('rtc', [None,
    {'base': 'utc', 'clock': 'host', 'driftfix': 'none'},
    {'base': 'utc', 'clock': 'vm', 'driftfix': 'slew'},
])
def test_owned_archive_rtc_policy_differs_before_spawn_or_owner_retirement(
        owned_checkpoint_runtime, monkeypatch, rtc):
    from fdisbull import qemu_owned_checkpoint as owned
    from fdisbull.qemu_instrumented_checkpoint import FORMAT

    runtime = owned_checkpoint_runtime
    session = runtime.session
    saved = owned.save_owned_machine_state(session)
    profile = machine_clock_configuration('virtual', 1)

    def alter(bundle):
        recorded = deepcopy(profile)
        if rtc is None:
            recorded.pop('rtc', None)
        else:
            recorded['rtc'] = rtc
        bundle['runtime']['machine']['clock_profile'] = recorded
        # This host test models the native instrumentation boundary. It uses
        # the real archive/hash reader and runtime comparison, and must refuse
        # before native import or a replacement QEMU can be requested.
        state = json.dumps({'format': FORMAT, 'source-epoch': 1, 'virtual-ns': 0,
                            'clock': {}, 'audio': {}, 'display': {}, 'retrace': {}})
        bundle['instrumentation'] = dict(state=state,
            sha256=hashlib.sha256(state.encode()).hexdigest(), icount=0)

    rewrite_owned_archive(runtime, saved, alter)
    session.vm.machine_configuration['clock_profile'] = profile
    monkeypatch.setattr('fdisbull.qemu_instrumented_checkpoint.preflight', lambda _: None)
    owner, epoch, cpu = session.vm, session._runtime_epoch, session.registers()
    snapshots = list(runtime.snapshots)
    with pytest.raises(ValueError, match='runtime identity differs'):
        owned.load_owned_machine_state(session, saved['artifact'])
    assert runtime.spawned == [] and runtime.snapshots == snapshots
    assert session.vm is owner and not session.closed and not owner.closed
    assert session._runtime_epoch == epoch and session.registers() == cpu
    assert session.thawed == 0


@pytest.mark.parametrize('profile,cpus', [('instruction', 2), ('standard', 0),
                                         ('standard', True), ('unknown', 1)])
def test_invalid_clock_profiles_cannot_be_admitted(profile, cpus):
    with pytest.raises(ValueError):
        machine_clock_configuration(profile, cpus)


def test_standard_profile_reports_clock_unsupported_without_reading_zero_icount():
    context = ClockContext('standard')
    value = context.clock_observe()
    assert value['counter']['state'] == 'unsupported'
    assert value['counter']['value'] is None
    assert value['virtual_ns'] is None and value['guest_ms'] is None
    assert value['host_monotonic_ns'] > 0
    assert context.peer.calls == ['query-status']
    assert not context.vm.closed


def test_stopped_observations_keep_counter_units_epoch_sequence_and_native_evidence():
    context = ClockContext(values=[dict(mode='none', icount=n) for n in [4, 4, 900]])
    context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    observations = [context.clock_observe() for _ in range(3)]
    assert [value['sequence'] for value in observations] == [1, 2, 3]
    assert len({value['epoch'] for value in observations}) == 1
    assert [value['counter']['value'] for value in observations] == [4, 4, 900]
    for value in observations:
        assert value['counter']['state'] == 'observed'
        assert value['counter']['unit'] == 'instructions'
        assert value['counter']['source'] == 'query-replay.icount'
        assert value['counter']['native']['mode'] == 'none'
        assert value['virtual_ns'] is None and value['guest_ms'] is None
        assert value['run'] == 19 and value['context'] == 'machine'
        assert value['session']['state'] == 'stopped'
        assert value['native_state']['running'] is False
    assert context.events == [('machine-clock-observe', value) for value in observations]


def test_new_machine_has_distinct_epoch_and_counter_baseline():
    first = ClockContext(values=[dict(mode='none', icount=500)])
    second = ClockContext(values=[dict(mode='none', icount=1)])
    left, right = first.clock_observe(), second.clock_observe()
    assert left['epoch'] != right['epoch']
    assert left['sequence'] == right['sequence'] == 1
    assert right['counter']['value'] == 1


def test_counter_regression_closes_owned_machine_and_is_not_reported_as_elapsed_time():
    context = ClockContext(values=[dict(mode='none', icount=10), dict(mode='none', icount=9)])
    context.clock_observe()
    with pytest.raises(DebuggerError, match='regressed'):
        context.clock_observe()
    assert context.vm.closed


@pytest.mark.parametrize('native', [None, {}, dict(mode='none'),
                                   dict(mode='none', icount=True),
                                   dict(mode='none', icount=-1),
                                   dict(mode='none', icount=1 << 64),
                                   dict(mode='none', icount='12'),
                                   dict(mode='play', icount=12),
                                   dict(mode='record', icount=12)])
def test_malformed_or_replayed_counter_closes_machine(native):
    context = ClockContext(values=[native])
    with pytest.raises(DebuggerError, match='instruction counter'):
        context.clock_observe()
    assert context.vm.closed and context.events == []


def test_running_machine_is_rejected_without_silently_stopping_or_querying_counter():
    context = ClockContext(running=True)
    with pytest.raises(ValueError, match='Pause'):
        context.clock_observe()
    assert context.peer.calls == ['query-status'] and not context.vm.closed


def test_caller_transaction_is_rejected_before_native_observation():
    context = ClockContext()
    context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=True))
    with pytest.raises(ValueError, match='caller-owned transaction'):
        context.clock_observe()
    assert context.peer.calls == [] and context.events == []


def test_clock_descriptor_does_not_allow_late_counter_profile_activation():
    context = ClockContext('standard')
    context.clock_observe()
    context.vm.machine_configuration['clock_profile'] = machine_clock_configuration('instruction', 1)
    with pytest.raises(DebuggerError, match='clock profile'):
        context.clock_observe()
    assert context.vm.closed
