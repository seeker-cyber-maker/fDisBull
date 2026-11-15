"""Cooperative host/virtual clock mapping with a deterministic native peer.

These tests exercise the real QMP envelope and existing native-clock owner.
They do not establish emulator timing; separate native witnesses do that.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_clock_sync import validate_clock_sync_options
from test_qemu_clock_budget import owned


@pytest.fixture
def synced(owned, monkeypatch):
    o = owned
    monkeypatch.setattr('time.monotonic_ns', lambda: round(o.clock.now * 1_000_000_000))
    o.events, o.waits = [], []
    o.context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    o.context.run_id = 'clock-sync-owned-run'
    o.context._event = lambda name, value: o.events.append((name, deepcopy(value)))

    def sleep(seconds):
        o.waits.append(seconds)
        o.clock.now += seconds

    monkeypatch.setattr('time.sleep', sleep)
    return o


def test_clock_sync_accounts_for_host_work_without_rebasing(synced):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .025
    first = o.context.clock_sync_step()
    assert first['target_ns'] == start['anchors']['virtual_ns'] + 25_000_000
    assert first['action'] == 'advance'
    assert first['execution']['clock_budget']['requested_delta_ns'] == 25_000_000
    assert first['anchors'] == start['anchors']
    assert len(o.executions) == 1
    o.clock.now += .015
    second = o.context.clock_sync_step()
    assert second['target_ns'] == start['anchors']['virtual_ns'] + 40_000_000
    assert second['execution']['clock_budget']['requested_delta_ns'] == 14_999_936
    assert second['anchors'] == start['anchors']
    assert len(o.executions) == 2


def test_start_is_passive_and_samples_host_after_native(synced):
    o = synced
    o.wire.latency = .001
    result = o.context.clock_sync_start()
    assert result['format'] == 'fdisbull-clock-sync-1'
    assert result['state'] == 'active' and result['outcome'] == 'started'
    assert result['rate'] == dict(virtual_ns=1, host_ns=1)
    assert result['config'] == dict(tolerance_ns=1_000_000,
                                   max_lag_ns=250_000_000, max_wait_ns=250_000_000)
    assert result['anchors'] == dict(virtual_ns=1000, host_ns=100_003_000_000)
    assert result['host_before_ns'] >= result['before']['host_monotonic_ns']
    assert result['after'] == result['before']
    assert result['drift_before_ns'] == result['drift_after_ns'] == 0
    assert result['within_tolerance'] is True
    assert result['execution'] is None and result['action'] == 'none'
    assert [name for name, _ in o.events] == ['machine-clock-sync-start']
    assert [name for name, _ in o.wire.calls] == [
        'query-status', 'query-replay', 'x-fdisbull-query-clock']
    assert not o.executions and not o.waits


def test_native_work_is_reported_as_residual_drift_without_chasing(synced):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=100)
    o.clock.now += .025
    o.execution_latency = .010
    result = o.context.clock_sync_step()
    assert result['target_ns'] == 25_001_000
    assert result['after']['virtual_ns'] == 25_001_064
    assert result['drift_after_ns'] == -9_999_936
    assert result['within_tolerance'] is False
    assert result['state'] == 'active' and result['outcome'] == 'advanced'
    assert result['anchors'] == start['anchors'] and len(o.executions) == 1


@pytest.mark.parametrize('drift', [-1_000_000, 0, 1_000_000])
def test_tolerance_includes_both_endpoints_without_execution_or_wait(synced, drift):
    o = synced
    o.context.clock_sync_start()
    if drift < 0:
        o.clock.now += -drift / 1_000_000_000
    else:
        o.wire.receipt['virtual-ns'] += drift
    result = o.context.clock_sync_step()
    assert result['outcome'] == 'within-tolerance'
    assert result['drift_before_ns'] == result['drift_after_ns'] == drift
    assert result['within_tolerance'] is True
    assert not o.executions and not o.waits


def test_ahead_step_waits_only_on_host_and_measures_actual_oversleep(synced, monkeypatch):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=0)
    o.wire.receipt['virtual-ns'] += 20_000_000

    def oversleep(seconds):
        o.waits.append(seconds)
        o.clock.now += seconds + .003

    monkeypatch.setattr('time.sleep', oversleep)
    result = o.context.clock_sync_step()
    assert result['action'] == 'wait' and result['outcome'] == 'waited'
    assert result['requested_wait_ns'] == 20_000_000
    assert result['actual_wait_ns'] == 23_000_000
    assert result['wait_deadline_host_ns'] == start['anchors']['host_ns'] + 20_000_000
    assert result['before']['virtual_ns'] == result['after']['virtual_ns']
    assert result['before']['counter'] == result['after']['counter']
    assert result['target_ns'] == start['anchors']['virtual_ns']
    assert result['drift_after_ns'] == -3_000_000 and result['within_tolerance'] is False
    assert o.waits == [.02] and not o.executions


def test_short_host_wait_reports_remaining_drift_without_retry(synced, monkeypatch):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.wire.receipt['virtual-ns'] += 20_000_000

    def short_sleep(seconds):
        o.waits.append(seconds)
        o.clock.now += seconds / 2

    monkeypatch.setattr('time.sleep', short_sleep)
    result = o.context.clock_sync_step()
    assert result['actual_wait_ns'] == result['drift_after_ns'] == 10_000_000
    assert result['within_tolerance'] is False
    assert o.waits == [.02] and not o.executions


def test_after_wait_host_sample_cannot_regress_behind_measured_wait_end(
        synced, monkeypatch, request):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=0)
    anchor = start['anchors']['host_ns']
    o.wire.receipt['virtual-ns'] += 20_000_000
    # Native-before stamp, host-before, wait start, measured wait end,
    # native-after stamp, host-after. The last two are newer than before,
    # but older than the already observed end of the host-only wait.
    samples = iter([anchor, anchor, anchor, anchor + 20_000_000,
                    anchor + 10_000_000, anchor + 10_000_000])
    monkeypatch.setattr('time.monotonic_ns', lambda: next(samples))
    error = None
    try:
        result = o.context.clock_sync_step()
    except DebuggerError as caught:
        error, result = caught, caught.result
    # Retain the actual accepted/refused receipt in both baseline and fixed
    # JUnit records, including the contradictory timestamps and original wait.
    request.node.user_properties.append(('host_wait_frontier_receipt',
                                        json.dumps(result, sort_keys=True)))
    assert error is not None, 'Accepted a host sample earlier than the measured wait end'
    assert 'regressed' in str(error)
    assert result['state'] == o.vm._clock_sync['state'] == 'invalidated'
    assert result['host_before_ns'] == anchor
    assert result['host_after_ns'] == anchor + 10_000_000
    assert result['actual_wait_ns'] == 20_000_000
    assert result['after']['virtual_ns'] == result['before']['virtual_ns']
    assert o.vm._clock_sync['last_host_ns'] == anchor + 20_000_000
    assert result['execution'] is None and not o.executions
    assert o.waits == [.02] and not o.vm.closed


@pytest.mark.parametrize('ahead', [False, True])
def test_excess_drift_latches_without_correction_or_rebase(synced, ahead):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=0, max_lag_ns=10_000_000,
                                      max_wait_ns=10_000_000)
    if ahead:
        o.wire.receipt['virtual-ns'] += 10_000_001
    else:
        o.clock.now += .010000001
    result = o.context.clock_sync_step()
    assert result['state'] == 'desynchronized'
    assert result['outcome'] == ('wait-limit' if ahead else 'lag-limit')
    assert result['anchors'] == start['anchors'] and result['action'] == 'none'
    assert not o.executions and not o.waits
    o.wire.calls.clear()
    with pytest.raises(ValueError, match='active mapping'):
        o.context.clock_sync_step()
    with pytest.raises(ValueError, match='Stop the existing'):
        o.context.clock_sync_start()
    assert o.wire.calls == []
    observed = o.context.clock_sync_observe()
    assert observed['state'] == 'desynchronized' and observed['token'] == start['token']
    assert observed['anchors'] == start['anchors']


def test_observe_and_stop_are_passive_and_fresh_start_is_explicit(synced):
    o = synced
    start = o.context.clock_sync_start()
    o.clock.now += .005
    observed = o.context.clock_sync_observe()
    assert observed['drift_after_ns'] == -5_000_000
    assert observed['anchors'] == start['anchors']
    first = o.context.clock_sync_stop()
    o.clock.now += .005
    second = o.context.clock_sync_stop()
    assert first['state'] == second['state'] == 'stopped'
    assert first['token'] == second['token'] == start['token']
    assert o.context.clock_sync_observe()['state'] == 'stopped'
    with pytest.raises(ValueError, match='active mapping'):
        o.context.clock_sync_step()
    restarted = o.context.clock_sync_start()
    assert restarted['token'] != start['token']
    assert restarted['anchors']['virtual_ns'] == start['anchors']['virtual_ns']
    assert restarted['anchors']['host_ns'] == start['anchors']['host_ns'] + 10_000_000
    assert not o.executions and not o.waits


def test_empty_mapping_observe_step_refuse_and_stop_is_idle(synced):
    o = synced
    with pytest.raises(ValueError, match='Start a host'):
        o.context.clock_sync_observe()
    with pytest.raises(ValueError, match='active mapping'):
        o.context.clock_sync_step()
    result = o.context.clock_sync_stop()
    assert result['state'] == result['outcome'] == 'idle'
    assert result['token'] is result['anchors'] is result['execution'] is None
    assert not o.wire.calls and not o.executions and not o.waits


def test_active_start_cannot_implicitly_rebase(synced):
    o = synced
    start = o.context.clock_sync_start()
    o.clock.now += .01
    o.wire.calls.clear()
    with pytest.raises(ValueError, match='Stop the existing'):
        o.context.clock_sync_start()
    assert o.wire.calls == []
    assert o.context.clock_sync_observe()['anchors'] == start['anchors']


@pytest.mark.parametrize('key,bad', [
    ('tolerance_ns', True), ('tolerance_ns', -1), ('tolerance_ns', 60_000_000_001),
    ('max_lag_ns', False), ('max_lag_ns', 0), ('max_lag_ns', 60_000_000_001),
    ('max_wait_ns', True), ('max_wait_ns', 0), ('max_wait_ns', 60_000_000_001),
    ('timeout_ms', True), ('timeout_ms', 0), ('timeout_ms', 600001),
    ('tolerance_ns', 0.0), ('max_lag_ns', '12'), ('max_wait_ns', None),
])
def test_literal_options_are_strict_and_pure(key, bad):
    with pytest.raises(ValueError, match=key):
        validate_clock_sync_options(**{key: bad})


def test_option_limits_are_inclusive_without_invented_relational_constraints():
    assert validate_clock_sync_options(tolerance_ns=0, max_lag_ns=1, max_wait_ns=1,
                                      timeout_ms=1)['tolerance_ns'] == 0
    assert validate_clock_sync_options(tolerance_ns=60_000_000_000,
                                      max_lag_ns=60_000_000_000,
                                      max_wait_ns=60_000_000_000,
                                      timeout_ms=600000)['timeout_ms'] == 600000


def test_invalid_timeout_refuses_before_clock_or_mapping_changes(synced):
    o = synced
    start = o.context.clock_sync_start()
    o.wire.calls.clear()
    for method in ('clock_sync_start', 'clock_sync_observe', 'clock_sync_step', 'clock_sync_stop'):
        with pytest.raises(ValueError, match='timeout_ms'):
            getattr(o.context, method)(timeout_ms=True)
    assert o.wire.calls == []
    assert o.vm._clock_sync['state'] == 'active' and o.vm._clock_sync['anchors'] == start['anchors']


@pytest.mark.parametrize('method', ['clock_sync_observe', 'clock_sync_step', 'clock_sync_stop'])
def test_caller_transaction_refusal_does_not_mutate_the_mapping(synced, method):
    o = synced
    o.context.clock_sync_start()
    o.context.project.db.in_transaction = True
    o.wire.calls.clear()
    with pytest.raises(ValueError, match='transaction'):
        getattr(o.context, method)()
    assert not o.wire.calls and not o.executions
    assert o.vm._clock_sync['state'] == 'active'


def test_standard_profile_refuses_before_native_io(synced):
    o = synced
    o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard', 1)
    with pytest.raises(ValueError, match='virtual clock profile'):
        o.context.clock_sync_start()
    assert not o.wire.calls and not o.vm.closed


def test_profile_loss_of_owned_mapping_is_terminal(synced):
    o = synced
    o.context.clock_sync_start()
    o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard', 1)
    with pytest.raises(DebuggerError, match='profile'):
        o.context.clock_sync_observe()
    assert o.vm._clock_sync['state'] == 'invalidated' and o.vm.closed


def test_early_breakpoint_latches_and_retains_original_stop(synced):
    o = synced
    start = o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    o.early = True
    o.context.breakpoints['early'] = dict(address=0x7c00, access='x', kind=1, length=1)
    result = o.context.clock_sync_step()
    assert result['state'] == result['outcome'] == 'interrupted'
    assert result['execution']['outcome'] == 'breakpoint'
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['execution']['session']['stop_reason']['breakpoint_ids'] == ['early']
    assert result['execution']['clock_budget']['deadline_reached'] is False
    assert result['anchors'] == start['anchors'] and not o.vm.closed
    with pytest.raises(ValueError, match='active mapping'):
        o.context.clock_sync_step()
    assert len(o.executions) == 1


@pytest.mark.parametrize('outcome', ['watchpoint', 'guest_exit', 'guest_tsr', 'exception', 'timeout'])
def test_fired_timer_never_overrides_other_native_classification(synced, outcome):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    execute = o.context._execute

    def classified(*args, **kwargs):
        result = execute(*args, **kwargs)
        result['outcome'] = outcome
        result['classification_witness'] = outcome
        return result

    o.context._execute = classified
    result = o.context.clock_sync_step()
    assert result['execution']['clock_budget']['deadline_reached'] is True
    assert result['execution']['classification_witness'] == outcome
    assert result['state'] == 'interrupted' and len(o.executions) == 1


def test_ordinary_timer_with_active_dos_descriptor_remains_qualified(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    execute = o.context._execute

    def classified(*args, **kwargs):
        result = execute(*args, **kwargs)
        result['process'] = dict(state='active', machine_closed=False)
        return result

    o.context._execute = classified
    result = o.context.clock_sync_step()
    assert result['state'] == 'active' and result['outcome'] == 'advanced'
    assert result['execution']['process'] == dict(state='active', machine_closed=False)


def test_after_sample_must_join_exact_native_stopped_time(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    advance = o.context.clock_advance

    def changed(*args, **kwargs):
        result = advance(*args, **kwargs)
        o.wire.receipt['virtual-ns'] += 128
        return result

    o.context.clock_advance = changed
    with pytest.raises(DebuggerError, match='stopped') as caught:
        o.context.clock_sync_step()
    result = caught.value.result
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert result['after']['virtual_ns'] == result['execution']['clock_budget']['stopped_ns'] + 128
    assert result['state'] == 'invalidated' and o.vm.closed
    assert len(o.executions) == 1


def test_ahead_wait_is_bounded_by_same_operation_deadline(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.wire.receipt['virtual-ns'] += 100_000_000
    with pytest.raises(TimeoutError) as caught:
        o.context.clock_sync_step(timeout_ms=25)
    result = caught.value.result
    assert result['action'] == 'wait' and result['requested_wait_ns'] == 100_000_000
    assert result['actual_wait_ns'] == 25_000_000
    assert result['state'] == 'interrupted' and o.vm._clock_sync['state'] == 'interrupted'
    assert o.waits == pytest.approx([.025]) and not o.executions
    assert not o.vm.closed
    assert o.vm.operation_deadline is o.qmp.operation_deadline is o.remote.operation_deadline is None


def test_nested_incoming_deadlines_shrink_and_restore_independently(synced):
    o = synced
    o.context.clock_sync_start()
    o.context._rpc_deadline = 100.150
    o.context._deadline = 100.125
    o.vm.operation_deadline = 100.200
    o.qmp.operation_deadline = 100.100
    o.remote.operation_deadline = 100.175
    o.wire.latency = .01
    o.wire.budgets.clear()
    result = o.context.clock_sync_observe(timeout_ms=1000)
    assert result['drift_after_ns'] == -30_000_000
    assert o.wire.budgets == pytest.approx([.100, .090, .080])
    assert o.context._rpc_deadline == 100.150 and o.context._deadline == 100.125
    assert o.vm.operation_deadline == 100.200
    assert o.qmp.operation_deadline == 100.100 and o.remote.operation_deadline == 100.175


def test_late_journal_retains_observation_and_latches_interruption(synced):
    o = synced
    event = o.context._event

    def late(name, value):
        event(name, value)
        o.clock.now += .051

    o.context._event = late
    with pytest.raises(TimeoutError) as caught:
        o.context.clock_sync_start(timeout_ms=50)
    assert caught.value.result['format'] == 'fdisbull-clock-sync-1'
    assert caught.value.result['anchors']['virtual_ns'] == 1000
    assert caught.value.result['state'] == o.vm._clock_sync['state'] == 'interrupted'
    assert len(o.events) == 1 and o.events[0][1]['state'] == 'active'
    assert not o.vm.closed and not o.executions


def test_late_outer_wrapper_check_cannot_leave_active_mapping(synced, monkeypatch):
    o = synced
    event = o.context._event
    after_journal = []

    def journal(name, value):
        event(name, value)
        after_journal.append(0)

    def monotonic():
        if after_journal:
            after_journal[0] += 1
            # First read is the module's final check. The next is the outer
            # wrapper's check, where the original request has now expired.
            if after_journal[0] == 2:
                o.clock.now += .051
        return o.clock.now

    o.context._event = journal
    monkeypatch.setattr('time.monotonic', monotonic)
    with pytest.raises(TimeoutError) as caught:
        o.context.clock_sync_start(timeout_ms=50)
    assert caught.value.result['format'] == 'fdisbull-clock-sync-1'
    assert o.vm._clock_sync['state'] == 'interrupted'
    assert caught.value.result['state'] == 'interrupted'


def test_failed_journal_retains_complete_native_execution(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    event = o.context._event

    def failed(name, value):
        if name == 'machine-clock-sync-step':
            raise OSError('sync journal refused')
        event(name, value)

    o.context._event = failed
    with pytest.raises(OSError, match='journal refused') as caught:
        o.context.clock_sync_step()
    result = caught.value.result
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert result['execution']['clock_budget']['deadline_reached'] is True
    assert result['after']['virtual_ns'] == result['execution']['clock_budget']['stopped_ns']
    assert result['state'] == 'interrupted' and len(o.executions) == 1
    assert not o.vm.closed


def test_uncertain_clock_cleanup_keeps_stop_in_nested_error_evidence(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01
    o.wire.change_final = lambda value: dict(value, **{'budget-token': 'not-owned'})
    with pytest.raises(DebuggerError) as caught:
        o.context.clock_sync_step()
    result = caught.value.result
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert result['before']['virtual_ns'] == 1000 and result['target_ns'] == 10_001_000
    assert result['state'] == 'invalidated' and o.vm.closed
    assert len(o.executions) == 1


def test_failed_post_stop_register_read_keeps_original_native_reply(synced):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .01

    def failed():
        raise OSError('register read failed after stop')

    o.context.registers = failed
    with pytest.raises(OSError, match='register read') as caught:
        o.context.clock_sync_step()
    execution = caught.value.result['execution']
    assert execution['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert execution['session']['stop_reason']['classification_complete'] is False
    assert len(o.executions) == 1 and o.vm.closed


def test_native_epoch_loss_invalidates_mapping_and_closes_owner(synced):
    o = synced
    o.context.clock_sync_start()
    o.wire.receipt['epoch'] = 2
    with pytest.raises(DebuggerError, match='epoch') as caught:
        o.context.clock_sync_observe()
    assert caught.value.result['state'] == 'invalidated'
    assert o.vm.closed and not o.executions


def test_host_regression_invalidates_mapping_without_execution(synced):
    o = synced
    o.context.clock_sync_start()
    o.clock.now -= .001
    with pytest.raises(DebuggerError, match='regressed') as caught:
        o.context.clock_sync_observe()
    assert caught.value.result['state'] == 'invalidated' and not o.executions


def test_virtual_target_overflow_is_rejected_without_execution(synced):
    o = synced
    o.wire.receipt['virtual-ns'] = (1 << 63) - 6
    o.context.clock_sync_start(tolerance_ns=0)
    o.clock.now += .000000010
    with pytest.raises(DebuggerError, match='overflowed') as caught:
        o.context.clock_sync_step()
    assert caught.value.result['state'] == 'invalidated' and not o.executions


def test_host_wait_target_overflow_is_rejected_without_wait(synced, monkeypatch):
    o = synced
    monkeypatch.setattr('time.monotonic_ns', lambda: (1 << 63) - 6)
    o.context.clock_sync_start(tolerance_ns=0)
    o.wire.receipt['virtual-ns'] += 10
    with pytest.raises(DebuggerError, match='overflowed') as caught:
        o.context.clock_sync_step()
    assert caught.value.result['state'] == 'invalidated' and not o.waits


def test_unexpected_native_progress_during_host_wait_closes_owner(synced, monkeypatch):
    o = synced
    o.context.clock_sync_start(tolerance_ns=0)
    o.wire.receipt['virtual-ns'] += 20_000_000

    def changed(seconds):
        o.clock.now += seconds
        o.wire.receipt['virtual-ns'] += 128

    monkeypatch.setattr('time.sleep', changed)
    with pytest.raises(DebuggerError, match='advanced during') as caught:
        o.context.clock_sync_step()
    assert caught.value.result['state'] == 'invalidated' and o.vm.closed
    assert not o.executions


def test_returned_receipt_cannot_rewrite_owned_anchors_or_configuration(synced):
    o = synced
    result = o.context.clock_sync_start()
    anchors = deepcopy(result['anchors'])
    result['anchors']['virtual_ns'] = 99
    result['config']['max_lag_ns'] = 99
    result['before']['clock_profile']['shift'] = 8
    observed = o.context.clock_sync_observe()
    assert observed['anchors'] == anchors
    assert observed['config']['max_lag_ns'] == 250_000_000
    assert observed['before']['clock_profile']['shift'] == 7
