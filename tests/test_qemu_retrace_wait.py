"""Bounded retrace-edge composition at the production QMP/GDB boundary.

This deterministic peer tests host admission, ownership, stop preservation and
absolute-window classification. Authored native guests test the actual model.
"""
from copy import deepcopy

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_retrace import validate_retrace_wait_parameters
from test_qemu_retrace import initialized, retrace
from test_qemu_clock_budget import owned


@pytest.fixture
def waiting(retrace):
    state = initialized(retrace)
    state.context.capabilities['retrace_wait'] = True
    state.overshoot_ns = 64
    state.native_reply = b'T02thread:1;'
    state.timed_out = False
    state.after_execution = lambda: None

    def execute(command, timeout_ms):
        state.executions.append((command, timeout_ms, state.remote.operation_deadline))
        state.clock.now += state.execution_latency
        native = state.wire.receipt
        end = (native['budget-start-ns'] + 128 if state.early
               else native['budget-deadline-ns'] + state.overshoot_ns)
        native.update({'budget-state': 'stopped', 'budget-stopped-ns': end,
                       'virtual-ns': end})
        if not state.early:
            native['budget-fired-ns'] = end
        state.wire.counter += 1
        state.after_execution()
        return state.native_reply, state.timed_out

    state.remote.execute = execute
    return state


def test_enter_wait_runs_once_to_the_absolute_window(waiting):
    state = waiting
    result = state.context.retrace_wait(edge='enter', timeout_ms=250)
    assert result['format'] == 'fdisbull-retrace-wait-1'
    assert result['outcome'] == 'synchronized' and result['synchronized'] is True
    assert result['target_ns'] == 2_536_000
    assert result['window_end_ns'] == 2_884_700
    assert result['after']['observed_ns'] == 2_536_064
    assert result['execution']['clock_budget']['deadline_ns'] == result['target_ns']
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert [command for command, _, _ in state.executions] == ['c']
    commands = [name for name, _ in state.wire.calls]
    assert commands.count('x-fdisbull-query-retrace') == 2
    assert commands.count('x-fdisbull-arm-clock-budget') == 1
    assert commands.count('x-fdisbull-cancel-clock-budget') == 1
    assert [name for name, _ in state.journal].count('machine-retrace-wait') == 1
    assert result['completed_renderer_update'] is None
    assert result['completed_guest_frame'] is None and result['guest_frame_id'] is None
    assert not state.vm.closed


@pytest.mark.parametrize('edge,now,target,end', [
    ('enter', 1000, 2_536_000, 2_884_700),
    ('enter', 2_535_999, 2_536_000, 2_884_700),
    ('enter', 2_536_000, 5_706_000, 6_054_700),
    ('enter', 2_536_001, 5_706_000, 6_054_700),
    ('exit', 1000, 2_884_700, 5_706_000),
    ('exit', 2_884_699, 2_884_700, 5_706_000),
    ('exit', 2_884_700, 6_054_700, 8_876_000),
    ('exit', 2_884_701, 6_054_700, 8_876_000),
])
def test_strictly_next_occurrence_includes_neither_current_edge_nor_zero_budget(
        waiting, edge, now, target, end):
    state = waiting
    state.wire.receipt['virtual-ns'] = now
    result = state.context.retrace_wait(edge=edge)
    assert result['target_ns'] == target and result['window_end_ns'] == end
    assert result['execution']['clock_budget']['requested_delta_ns'] == target - now > 0
    assert result['after']['phase']['vertical-retrace'] is (edge == 'enter')
    assert result['synchronized'] is True
    assert len(state.executions) == 1


@pytest.mark.parametrize('edge,width', [('enter', 348_700), ('exit', 2_821_300)])
@pytest.mark.parametrize('position,outcome', [('last', 'synchronized'), ('end', 'missed-edge'),
                                             ('next-period', 'missed-edge')])
def test_success_window_is_exclusive_and_rejects_a_later_matching_cycle(waiting, edge, width, position, outcome):
    state = waiting
    state.overshoot_ns = {'last': width - 1, 'end': width, 'next-period': 3_170_000}[position]
    result = state.context.retrace_wait(edge=edge)
    assert result['outcome'] == outcome
    assert result['synchronized'] is (outcome == 'synchronized')
    assert result['execution']['clock_budget']['deadline_reached'] is True
    if position == 'next-period':
        assert result['after']['phase']['vertical-retrace'] is (edge == 'enter')
        assert result['after']['observed_ns'] > result['window_end_ns']
    assert len(state.executions) == 1


@pytest.mark.parametrize('edge,vstart,vend,target,end', [
    ('enter', 0, 10, 3_170_000, 3_518_700),
    ('exit', 89, 99, 3_170_000, 5_991_300),
])
def test_real_transition_at_period_wrap_is_supported(waiting, edge, vstart, vend, target, end):
    state = waiting
    state.wire.retrace['raw']['cr10'] = vstart
    state.wire.retrace['timing'].update(vstart=vstart, vend=vend)
    result = state.context.retrace_wait(edge=edge)
    assert result['synchronized'] is True
    assert result['target_ns'] == target and result['window_end_ns'] == end
    assert result['after']['phase']['vertical-retrace'] is (edge == 'enter')


@pytest.mark.parametrize('edge', ['enter', 'exit'])
def test_whole_period_retrace_has_no_transition_even_with_valid_phase(waiting, edge):
    state = waiting
    state.wire.retrace['raw'].update(cr06=0, cr10=0, cr11=0)
    state.wire.retrace['timing'].update(**{'total-chars': 200, 'vstart': 0, 'vend': 1})
    result = state.context.retrace_wait(edge=edge)
    assert result['outcome'] == 'unsupported' and result['unsupported_reason'] == 'no-transition'
    assert result['before']['phase_supported'] is True
    assert result['before']['phase']['vertical-retrace'] is True
    assert result['synchronized'] is False
    assert result['target_ns'] is result['window_end_ns'] is result['after'] is result['execution'] is None
    assert not state.executions
    commands = [name for name, _ in state.wire.calls]
    assert commands.count('x-fdisbull-query-retrace') == 1
    assert 'x-fdisbull-arm-clock-budget' not in commands
    assert [name for name, _ in state.journal].count('machine-retrace-wait') == 1


@pytest.mark.parametrize('reason', ['uninitialized', 'vbe-enabled', 'invalid-timing'])
def test_unsupported_phase_is_structured_and_passive(waiting, reason):
    state = waiting
    native = state.wire.retrace
    native.update({'phase-supported': False, 'unsupported-reason': reason})
    if reason == 'uninitialized':
        native['timing'] = {key: 0 for key in native['timing']}
    elif reason == 'vbe-enabled':
        native['raw']['vbe-enable'] = 1
    else:
        native['raw']['cr04'] = 255
        native['timing'].update(hstart=255, hend=265)
    result = state.context.retrace_wait()
    assert result['outcome'] == 'unsupported' and result['unsupported_reason'] == reason
    assert result['synchronized'] is False
    assert result['target_ns'] is result['window_end_ns'] is result['after'] is result['execution'] is None
    assert len(state.wire.calls) == 7 and not state.executions
    assert [name for name, _ in state.journal].count('machine-retrace-wait') == 1


@pytest.mark.parametrize('change', ['new-timing', 'aba', 'vbe'])
def test_timing_changes_invalidate_the_original_occurrence_without_retry(waiting, change):
    state = waiting

    def mutate():
        native = state.wire.retrace
        native['timing-generation'] += 2 if change == 'aba' else 1
        if change == 'new-timing':
            native['raw']['cr10'] = 81
            native['timing'].update(vstart=81, vend=91)
        elif change == 'vbe':
            native['raw']['vbe-enable'] = 1
            native.update({'phase-supported': False, 'unsupported-reason': 'vbe-enabled'})

    state.after_execution = mutate
    result = state.context.retrace_wait()
    assert result['outcome'] == 'timing-changed' and result['synchronized'] is False
    assert result['target_ns'] == 2_536_000
    assert result['execution']['clock_budget']['deadline_reached'] is True
    if change == 'aba':
        assert result['before']['raw'] == result['after']['raw']
        assert result['before']['timing'] == result['after']['timing']
        assert result['after']['timing_generation'] == result['before']['timing_generation'] + 2
    assert len(state.executions) == 1 and not state.vm.closed


@pytest.mark.parametrize('reply,early,timed_out,breakpoint,outcome', [
    (b'T05thread:1;', True, False, True, 'breakpoint'),
    (b'T05thread:1;', False, False, True, 'breakpoint'),
    (b'T05thread:1;', False, False, False, 'stopped'),
    (b'T02thread:1;watch:7c00;', False, False, False, 'watchpoint'),
    (b'T0bthread:1;', False, False, False, 'exception'),
    (b'T02thread:1;', False, True, False, 'timeout'),
])
def test_early_or_coincident_native_cause_is_never_replaced_by_timer_success(
        waiting, reply, early, timed_out, breakpoint, outcome):
    state = waiting
    state.native_reply, state.early, state.timed_out = reply, early, timed_out
    if breakpoint:
        state.context.breakpoints[7] = dict(address=0x7c00, access='x', kind=1, length=1)
    result = state.context.retrace_wait()
    assert result['outcome'] == 'interrupted' and result['synchronized'] is False
    execution = result['execution']
    assert execution['outcome'] == outcome and execution['timed_out'] is timed_out
    assert execution['session']['stop_reason']['native_reply'] == reply.decode()
    assert execution['clock_budget']['deadline_reached'] is (not early)
    assert len(state.executions) == 1 and not state.vm.closed


def test_active_dos_process_metadata_does_not_hide_an_ordinary_timer_stop(waiting):
    state = waiting
    execute = state.context._execute

    def process_execute(*args, **kwargs):
        result = execute(*args, **kwargs)
        result['process'] = dict(state='active', psp_segment=0x1200, termination=None)
        return result

    state.context._execute = process_execute
    result = state.context.retrace_wait()
    assert result['synchronized'] is True
    assert result['execution']['process']['state'] == 'active'
    assert len(state.executions) == 1


def test_dos_return_classification_remains_complete_and_unsynchronized(waiting):
    state = waiting
    execute = state.context._execute

    def process_execute(*args, **kwargs):
        result = execute(*args, **kwargs)
        result['native_machine_stop'] = deepcopy(result['session']['stop_reason'])
        result.update(outcome='guest_exit', process=dict(state='exited', termination={'code': 0}))
        result['session']['stop_reason'] = dict(kind='guest_exit', guest_exit={'code': 0})
        result['stop'].update(trigger='guest_exit', context='dos-process', guest_exit={'code': 0})
        return result

    state.context._execute = process_execute
    result = state.context.retrace_wait()
    assert result['outcome'] == 'interrupted' and result['synchronized'] is False
    assert result['execution']['outcome'] == 'guest_exit'
    assert result['execution']['native_machine_stop']['native_reply'] == 'T02thread:1;'
    assert result['execution']['session']['stop_reason']['guest_exit'] == {'code': 0}
    assert len(state.executions) == 1


@pytest.mark.parametrize('field', ['run', 'host-epoch', 'device', 'native-epoch', 'same-generation-timing'])
def test_identity_or_generation_coherence_loss_closes_owner_and_retains_execution(waiting, field):
    state = waiting

    def mutate():
        if field == 'run':
            state.context.run_id = 'different-run'
        elif field == 'host-epoch':
            state.vm._clock_observation_state['epoch'] = 'different-epoch'
        elif field == 'device':
            state.wire.retrace['device'] = '/machine/unattached/replacement[0]'
        elif field == 'native-epoch':
            state.wire.receipt['epoch'] = 2
        else:
            state.wire.retrace['raw']['cr10'] = 81
            state.wire.retrace['timing'].update(vstart=81, vend=91)

    state.after_execution = mutate
    with pytest.raises(DebuggerError) as failure:
        state.context.retrace_wait()
    result = failure.value.result
    assert result['format'] == 'fdisbull-retrace-wait-1'
    assert result['outcome'] == 'error' and result['synchronized'] is False
    assert result['before']['run'] == 'owned-retrace-run'
    assert result['target_ns'] == 2_536_000
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert state.vm.closed and len(state.executions) == 1


def test_virtual_time_change_after_budget_stop_does_not_count_as_owned_edge(waiting):
    state = waiting
    advance = state.context.clock_advance

    def changed(*args, **kwargs):
        result = advance(*args, **kwargs)
        state.wire.receipt['virtual-ns'] += 128
        return result

    state.context.clock_advance = changed
    with pytest.raises(DebuggerError, match='owned clock') as failure:
        state.context.retrace_wait()
    result = failure.value.result
    assert result['after']['observed_ns'] == result['execution']['clock_budget']['stopped_ns'] + 128
    assert result['outcome'] == 'error' and state.vm.closed
    assert len(state.executions) == 1


@pytest.mark.parametrize('edge,now,known_target', [
    ('enter', (1 << 63) - 2, None),
    ('exit', 9_223_372_036_853_484_699, 9_223_372_036_853_484_700),
])
def test_target_and_entire_verification_window_must_fit_native_nanoseconds(waiting, edge, now, known_target):
    state = waiting
    state.wire.receipt['virtual-ns'] = now
    with pytest.raises(ValueError, match='overflow') as failure:
        state.context.retrace_wait(edge=edge)
    result = failure.value.result
    assert result['before']['observed_ns'] == now
    assert result['target_ns'] == known_target and result['window_end_ns'] is None
    assert result['execution'] is result['after'] is None
    assert not state.executions and not state.vm.closed


@pytest.mark.parametrize('parameters', [
    dict(edge=True), dict(edge=None), dict(edge='vblank'), dict(edge=[]),
    dict(timeout_ms=True), dict(timeout_ms=0), dict(timeout_ms=600001),
    dict(timeout_ms=1.5), dict(timeout_ms='1000'), dict(timeout_ms=None),
])
def test_invalid_literal_parameters_fail_before_any_native_operation(waiting, parameters):
    state = waiting
    with pytest.raises(ValueError):
        validate_retrace_wait_parameters(**parameters)
    with pytest.raises(ValueError):
        state.context.retrace_wait(**parameters)
    assert not state.wire.calls and not state.executions and not state.journal
    assert not state.vm.closed


def test_caller_transaction_is_refused_before_observation(waiting):
    state = waiting
    state.context.project.db.in_transaction = True
    with pytest.raises(ValueError, match='transaction'):
        state.context.retrace_wait()
    assert not state.wire.calls and not state.executions and not state.journal


def test_nested_operations_preserve_the_tightest_incoming_absolute_deadline(waiting):
    state = waiting
    state.context._deadline = 100.25
    state.vm.operation_deadline = 100.2
    state.qmp.operation_deadline = 100.1
    state.remote.operation_deadline = 100.15
    state.wire.latency = 0.002
    result = state.context.retrace_wait(timeout_ms=1000)
    assert result['synchronized'] is True
    assert state.executions[0][2] == 100.1
    assert 0 < min(state.wire.budgets) <= max(state.wire.budgets) <= 0.1 + 1e-9
    assert state.context._deadline == 100.25
    assert state.vm.operation_deadline == 100.2
    assert state.qmp.operation_deadline == 100.1
    assert state.remote.operation_deadline == 100.15


def test_expiration_during_initial_observation_never_arms_or_continues(waiting):
    state = waiting
    state.wire.latency = 0.003
    with pytest.raises(TimeoutError) as failure:
        state.context.retrace_wait(timeout_ms=10)
    assert failure.value.result['format'] == 'fdisbull-retrace-wait-1'
    assert failure.value.result['execution'] is None
    assert not state.executions and state.vm.closed
    assert 'x-fdisbull-arm-clock-budget' not in [name for name, _ in state.wire.calls]


def test_expiration_after_native_stop_retains_stop_even_without_cancel_receipt(waiting):
    state = waiting
    state.execution_latency = 0.3
    with pytest.raises(TimeoutError) as failure:
        state.context.retrace_wait(timeout_ms=250)
    result = failure.value.result
    assert result['before']['observed_ns'] == 1000 and result['target_ns'] == 2_536_000
    assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert 'clock_budget' not in result['execution']
    assert result['after'] is None and state.vm.closed
    assert len(state.executions) == 1


@pytest.mark.parametrize('failing_event,observation_number', [
    ('machine-retrace-observe', 1), ('machine-retrace-observe', 2),
    ('machine-run', None), ('machine-clock-advance', None), ('machine-retrace-wait', None),
])
def test_journal_failures_retain_every_completed_child_receipt(waiting, failing_event, observation_number):
    state = waiting
    event = state.context._event
    observations = 0
    attempts = []

    def fail(name, value):
        nonlocal observations
        attempts.append(name)
        if name == 'machine-retrace-observe':
            observations += 1
        if name == failing_event and (observation_number is None or observations == observation_number):
            raise OSError('Journal write failed')
        return event(name, value)

    state.context._event = fail
    with pytest.raises(OSError, match='Journal') as failure:
        state.context.retrace_wait()
    result = failure.value.result
    assert result['format'] == 'fdisbull-retrace-wait-1' and result['outcome'] == 'error'
    assert result['before']['format'] == 'fdisbull-retrace-observation-1'
    if observation_number == 1:
        assert result['target_ns'] is result['execution'] is result['after'] is None
        assert not state.executions
    else:
        assert result['execution']['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert len(state.executions) == 1
        if failing_event != 'machine-run':
            assert result['execution']['clock_budget']['deadline_reached'] is True
        if observation_number == 2 or failing_event == 'machine-retrace-wait':
            assert result['after']['format'] == 'fdisbull-retrace-observation-1'
    assert attempts.count('machine-retrace-wait') <= 1


def test_deadline_expires_during_final_journal_without_repeating_execution_or_write(waiting):
    state = waiting
    event = state.context._event

    def slow(name, value):
        event(name, value)
        if name == 'machine-retrace-wait':
            state.clock.now += 0.3

    state.context._event = slow
    with pytest.raises(TimeoutError) as failure:
        state.context.retrace_wait(timeout_ms=250)
    result = failure.value.result
    assert result['outcome'] == 'error' and result['failure_stage'] == 'journal'
    assert result['after']['observed_ns'] == result['execution']['clock_budget']['stopped_ns']
    assert len(state.executions) == 1
    assert [name for name, _ in state.journal].count('machine-retrace-wait') == 1


def test_returned_nested_receipt_is_owned_independently_of_native_cache_and_journal(waiting):
    state = waiting
    result = state.context.retrace_wait()
    result['before']['raw']['cr10'] = 1
    result['after']['timing']['vstart'] = 1
    result['execution']['clock_budget']['native']['budget-token'] = 'changed'
    saved = next(value for name, value in state.journal if name == 'machine-retrace-wait')
    assert saved['before']['raw']['cr10'] == 80
    assert saved['after']['timing']['vstart'] == 80
    assert saved['execution']['clock_budget']['native']['budget-token'] != 'changed'
    assert state.vm._retrace_last['timing']['vstart'] == 80
