"""Explicit tracker/LE attachment through real DOS controls and FDB storage.

QMP/GDB, provider discovery and unavailable source enrichment are authored
boundaries. These tests do not establish native DESQview/LE co-operation.
"""
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_machine import _tracking
from fdisbull.runtime_source_matching import SourceMatchError
from fdisbull.runtime_tracking import AutomaticRuntimeTracker
from test_qemu_dos_source_admission import owned
from test_qemu_dos_le_trace import active_le
from test_runtime_tracking import Provider


@pytest.fixture
def coupled(active_le, monkeypatch):
    o, s = active_le, active_le.session

    class CoveredProvider(Provider):
        checks = 0

        def validate_coverage(self):
            self.checks += 1
            return super().validate_coverage()

    provider = CoveredProvider()
    controls = []
    request = o.peer.request

    def native_control(command, **options):
        if command in (f'Z1,{provider.hook_address:x},1', f'z1,{provider.hook_address:x},1'):
            controls.append(command)
            return b'OK'
        return request(command, **options)

    o.peer.request = native_control
    monkeypatch.setattr('fdisbull.runtime_desqview.discover',
                        lambda _: None if provider.fingerprint_failure else provider)
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', lambda _: [])
    tracker = AutomaticRuntimeTracker(s)
    s._automatic_runtime_tracker = tracker
    _tracking(s, 'after_stop', 'authored explicit provider attachment')
    assert tracker.provider is provider and len(tracker.internal_breakpoints) == 1
    assert len(controls) == 1 and controls[0].startswith('Z1,')
    assert s.dos_source_binding()['live']

    def ambiguous(_):
        raise SourceMatchError('authored coupled source ambiguity')

    monkeypatch.setattr('fdisbull.runtime_source_matching.discover', ambiguous)
    o.tracker, o.provider, o.tracking_controls = tracker, provider, controls
    return o


def test_source_ambiguity_preserves_provider_and_independently_qualified_le_stop(coupled):
    o, s = coupled, coupled.session
    before = s.dos_source_binding()
    points = set(o.tracker.internal_breakpoints)
    checks = o.provider.checks
    result = s.step(timeout_ms=1000)
    after = s.dos_source_binding()
    tracked = o.tracker.status()

    assert result['outcome'] == 'step'
    assert result['session']['stop_reason']['native_reply'] == 'T05'
    assert len(o.intervals) == 1 and not o.closed
    assert after['live'] and after['binding_id'] == before['binding_id']
    assert after['capture_epoch'] == before['capture_epoch']
    assert after['continuity'].endswith('not OS/task/allocation lifetime')
    assert o.tracker.provider is o.provider and o.tracker.internal_breakpoints == points
    assert o.provider.checks >= checks + 3
    assert tracked['state'] == 'source-unavailable' and not tracked['fenced']
    assert tracked['sources'] == [] and tracked['current_bindings'] == 0
    assert tracked['errors']['count'] == 1
    assert tracked['errors']['last']['lifetime_action'] == 'preserved-native-provider'


def journal_failure(o):
    error = OSError('authored coupled error journal failure')
    original = o.tracker._record

    def record(kind, document):
        if kind == 'observation-error':
            raise error
        return original(kind, document)

    o.tracker._record = record
    return error


def assert_arrived_stop_fenced(o, error):
    s, tracker = o.session, o.tracker
    assert error.result['outcome'] == 'step'
    assert error.result['session']['stop_reason']['native_reply'] == 'T05'
    assert len(o.intervals) == 1
    assert s.vm._fdisbull_control_quarantine == 'failed native stop publication'
    assert tracker.fenced
    assert tracker.status()['errors']['unrecorded']['recording_error']['type'] == 'OSError'
    assert s.dos_source_binding()['state'] == 'retired'
    assert not s.dos_source_binding()['live']
    assert_future_controls_refused(o)


def assert_future_controls_refused(o):
    s = o.session
    counts = (len(o.intervals), len(o.peer.reads), len(o.peer.qmp_calls), len(o.tracking_controls))
    with pytest.raises(DebuggerError, match='quarantined'):
        s.step(timeout_ms=1000)
    with pytest.raises(DebuggerError, match='quarantined'):
        s.run(timeout_ms=1000)
    assert counts == (len(o.intervals), len(o.peer.reads), len(o.peer.qmp_calls), len(o.tracking_controls))


def test_tracker_error_journal_failure_keeps_arrived_result_and_retires_le(coupled):
    o = coupled
    failure = journal_failure(o)
    with pytest.raises(OSError, match='coupled error journal') as caught:
        o.session.step(timeout_ms=1000)
    assert caught.value is failure
    assert o.closed
    assert_arrived_stop_fenced(o, caught.value)


def test_disposal_failures_remain_secondary_to_original_tracker_error_and_stop(coupled):
    o = coupled
    failure = journal_failure(o)

    def failed_close():
        o.closed.append(True)
        raise RuntimeError('authored coupled disposal failure')

    o.session.vm.close = failed_close
    with pytest.raises(OSError, match='coupled error journal') as caught:
        o.session.step(timeout_ms=1000)
    assert caught.value is failure
    assert caught.value.machine_cleanup_error == 'RuntimeError'
    assert caught.value.dos_process_cleanup_error == 'RuntimeError'
    assert len(o.closed) == 2  # Both existing disposal attempts remain inspectable.
    assert_arrived_stop_fenced(o, caught.value)


def return_breakpoint(o):
    s = o.session
    return_address = o.peer.cpu['cs_base'] + o.peer.cpu['ip'] + 2
    request = o.peer.request

    def return_control(command, **options):
        if command == f'Z1,{return_address:x},1':
            o.tracking_controls.append(command)
            return b'OK'
        return request(command, **options)

    o.peer.request = return_control
    identifier = s.breakpoint(return_address)['breakpoint_id']
    s._return_breakpoint = identifier
    return identifier


def test_invalid_parent_return_preserves_context_error_and_stop_when_disposal_fails(coupled):
    o, s = coupled, coupled.session
    identifier = return_breakpoint(o)
    s._ready = dict(helper_segment=s._process['parent_psp_segment'], exit_wait_ip=0)

    def failed_close():
        o.closed.append(True)
        raise RuntimeError('authored parent-return disposal failure')

    s.vm.close = failed_close
    with pytest.raises(DebuggerError, match='helper callback context') as caught:
        s.step(timeout_ms=1000)
    assert caught.value.result['outcome'] == 'breakpoint'
    assert caught.value.result['session']['stop_reason']['native_reply'] == 'T05'
    assert caught.value.result['breakpoints'] == [identifier]
    assert caught.value.dos_process_cleanup_error == 'RuntimeError'
    assert len(o.intervals) == 1 and len(o.closed) == 1
    assert getattr(s.vm, '_fdisbull_control_quarantine', None)
    assert s.dos_source_binding()['state'] == 'retired'
    assert not s.dos_source_binding()['live']
    assert_future_controls_refused(o)


def test_scheduler_return_refusal_keeps_arrived_stop_when_disposal_fails(coupled):
    o, s = coupled, coupled.session
    identifier = return_breakpoint(o)
    s._dos_scheduler = dict(enabled=True)

    def failed_close():
        o.closed.append(True)
        raise RuntimeError('authored scheduler-return disposal failure')

    s.vm.close = failed_close
    with pytest.raises(DebuggerError, match='Disable the native scheduler') as caught:
        s.step(timeout_ms=1000)
    assert caught.value.result['outcome'] == 'breakpoint'
    assert caught.value.result['session']['stop_reason']['native_reply'] == 'T05'
    assert caught.value.result['breakpoints'] == [identifier]
    assert caught.value.dos_process_cleanup_error == 'RuntimeError'
    assert len(o.intervals) == 1 and len(o.closed) == 1
    assert getattr(s.vm, '_fdisbull_control_quarantine', None)
    assert s.dos_source_binding()['state'] == 'retired'
    assert not s.dos_source_binding()['live']
    assert_future_controls_refused(o)


@pytest.mark.parametrize('reply', [b'W00', b'X09'])
def test_native_exit_cleanup_failure_retains_arrived_exit_and_quarantines(coupled, reply):
    o, s = coupled, coupled.session
    failures = []

    def native_exit(command, timeout_ms, **options):
        assert command == 's' and 0 < timeout_ms <= 1000
        o.intervals.append((command, timeout_ms))
        return reply, False

    def failed_close():
        o.closed.append(True)
        error = RuntimeError('authored exited-guest disposal failure')
        failures.append(error)
        raise error

    o.peer.execute, s.vm.close = native_exit, failed_close
    with pytest.raises(RuntimeError, match='exited-guest disposal failure') as caught:
        s.step(timeout_ms=1000)
    assert caught.value is failures[0]
    assert getattr(caught.value, 'result', None) is not None
    assert caught.value.result['outcome'] == 'exited'
    assert caught.value.result['session']['stop_reason']['native_reply'] == reply.decode('ascii')
    assert caught.value.dos_process_cleanup_error == 'RuntimeError'
    assert len(o.intervals) == 1 and len(o.closed) == 2
    assert getattr(s.vm, '_fdisbull_control_quarantine', None)
    assert s.dos_source_binding()['state'] == 'retired'
    assert not s.dos_source_binding()['live']
    assert_future_controls_refused(o)


def test_failed_provider_coverage_retires_tracker_continuity_without_rebinding_le(coupled):
    o, s = coupled, coupled.session
    before = s.dos_source_binding()
    points = set(o.tracker.internal_breakpoints)
    o.provider.fingerprint_failure = True
    result = s.step(timeout_ms=1000)
    after = s.dos_source_binding()
    tracked = o.tracker.status()

    assert result['outcome'] == 'step'
    assert len(o.intervals) == 1 and not o.closed
    assert after['live'] and after['binding_id'] == before['binding_id']
    assert after['capture_epoch'] == before['capture_epoch']
    assert o.tracker.provider is None and not o.tracker.internal_breakpoints
    assert not points.intersection(s.breakpoints)
    assert len(o.tracking_controls) == 2 and o.tracking_controls[-1].startswith('z1,')
    assert not tracked['fenced'] and not tracked['process_episodes']
    assert tracked['sources'] == [] and tracked['current_bindings'] == 0
    assert tracked['errors']['count'] == 2
    assert tracked['errors']['recent'][0]['lifetime_action'] == 'retire-continuity'
    assert tracked['errors']['last']['lifetime_action'] == 'retire-source-only'
    assert tracked['lifetime_qualification'] == 'one-stop-only'
