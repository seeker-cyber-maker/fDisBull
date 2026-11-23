"""Two bounded continuations for a positioned, observed CuteMouse click."""
from copy import deepcopy

from .dosbox_rpc import DebuggerError
from .qemu_clock import clock_timer_stop_is_ordinary, validate_clock_budget
from .qemu_int33_mouse_control import _stopped_target, validate_int33_input
from .qemu_save_stop import safe_stop_enabled


_FORMAT = 'fdisbull-qemu-int33-observed-click-1'
_BUTTON_MASKS = {'left': 1, 'right': 2}
_DEFAULT_BUDGET_NS = 50_000_000


def validate_int33_click(x, y, *, stream, frame_id, button='left',
                         press_budget_ns=_DEFAULT_BUDGET_NS,
                         release_budget_ns=_DEFAULT_BUDGET_NS, timeout_ms=3000):
    validate_int33_input(x, y, stream=stream, frame_id=frame_id, button=button,
                         timeout_ms=timeout_ms)
    validate_clock_budget(press_budget_ns, timeout_ms)
    validate_clock_budget(release_budget_ns, timeout_ms)


def _click_owner(cursor):
    raster = cursor['raster']
    return (cursor['run'], cursor['runtime_epoch'], cursor['checkpoint_epoch'],
            cursor['driver'], cursor['authority']['owner_lifetime'],
            raster['stream'], raster['epoch'], raster['configuration_generation'])


def _owned_lease(vm, token):
    """Read the captured VM's host ledger without dispatch or a new owner."""
    state = getattr(vm, '_physical_input', None)
    if state is None or not state['valid']:
        return None, 'delivery_unknown'
    lease = state['leases'].get(token)
    if lease is None:
        return None, None
    if lease['make'] == 'python_pending':
        return deepcopy(lease), 'cancel_unsent_input'
    if lease['release'] == 'python_pending':
        return deepcopy(lease), 'resolve_pending_release'
    return deepcopy(lease), 'release_owned_button'


def _accepted(execution, queued):
    delivery = execution.get('input_delivery') or {}
    return (delivery.get('delivery') == 'qmp_accepted'
            and delivery.get('edge_count') == 1
            and delivery.get('sequences') == [queued['sequence']]
            and delivery.get('pending_edges') == 0)


def _observed_edge(before, after, phase, button, target):
    expected = deepcopy(before['button_edges'])
    edge = expected[phase][button]
    edge.update(count=edge['count'] + 1, last_position=target)
    return after['button_edges'] == expected


def _run_phase(owner, vm, result, phase, queued, before, budget_ns, timeout_ms):
    section = result[phase] = dict(queued=queued, execution=None, observed=None,
                                   observed_edge_at_target=None)
    result['stage'] = phase
    execution = section['execution'] = owner._clock_advance_with_hooks(
        budget_ns, timeout_ms=timeout_ms)
    if owner.vm is not vm:
        raise DebuggerError('INT33 click owner changed after execution')
    if (not clock_timer_stop_is_ordinary(execution) or execution.get('hook_hits')
            or execution.get('layer_conflict') or execution.get('save_boundary_conflict')):
        return 'competing_stop'
    budget = execution['clock_budget']
    if (budget['epoch'] != before['clock']['epoch']
            or budget['start_ns'] != before['clock']['virtual_ns']):
        return 'execution_clock_changed'
    if not _accepted(execution, queued):
        return 'dispatch_unconfirmed'
    try:
        after = section['observed'] = owner.observe_int33_mouse(timeout_ms=timeout_ms)
    except ValueError as error:
        if getattr(error, 'observation_refusal', False) is not True:
            raise
        result['observation_refusal'] = dict(code=error.code, message=str(error))
        return 'observation_refused'
    if (_click_owner(after) != _click_owner(before)
            or after['raster']['frame_id'] < before['raster']['frame_id']
            or after['clock']['epoch'] != budget['epoch']
            or after['clock']['virtual_ns'] != budget['stopped_ns']):
        return 'observation_owner_changed'
    button, target = result['button'], result['target']
    section['observed_edge_at_target'] = _observed_edge(before, after, phase, button, target)
    if not section['observed_edge_at_target']:
        return 'driver_edge_unconfirmed'
    expected_buttons = _BUTTON_MASKS[button] if phase == 'press' else 0
    if after['buttons'] != expected_buttons:
        return 'driver_button_state_changed'
    if phase == 'press' and after['position'] != target:
        return 'cursor_left_target'
    return None


def mouse_click_int33(self, x, y, *, stream, frame_id, button='left',
                      press_budget_ns=_DEFAULT_BUDGET_NS,
                      release_budget_ns=_DEFAULT_BUDGET_NS, timeout_ms=3000):
    """Execute a press and release at a qualified, already-landed cursor.

    The budgets bound observation windows. The guest handler determines when
    each edge is consumed. A partial result preserves competing stops and any
    outstanding input lease for explicit recovery.
    """
    if safe_stop_enabled(self):
        raise ValueError('Observed INT33 click requires the automatic DOS save-stop owner to be inactive')
    vm = self.vm
    before, target = _stopped_target(self, x, y, stream, frame_id, timeout_ms)
    if before['position'] != target:
        raise ValueError('INT33 click requires an observed landing before pressing')
    if any(before['button_edges'][phase][button]['count'] == 0xffff
           for phase in ('press', 'release')):
        raise ValueError('INT33 click requires room in the driver edge counters')
    result = dict(format=_FORMAT, stage='press', complete=False, button=button,
                  source_target=[x, y], target=target, before=before,
                  press=None, release=None, lease=None, lease_state=None, next_action=None,
                  effect='unconfirmed',
                  scope='Stopped CuteMouse edge records and explicit virtual-time budgets')
    token = None

    def finish(outcome):
        result['outcome'] = outcome
        if token is not None:
            result['lease_state'], result['next_action'] = _owned_lease(vm, token)
        return result

    try:
        press = self.mouse_button_down(button)
        token = result['lease'] = press['lease']
        outcome = _run_phase(self, vm, result, 'press', press, before,
                             press_budget_ns, timeout_ms)
        if outcome is not None:
            if result['press']['observed_edge_at_target']:
                result['effect'] = 'press_observed'
            return finish(outcome)

        result['effect'] = 'press_observed'
        result['stage'] = 'release'
        release = self.mouse_button_up(token)
        outcome = _run_phase(self, vm, result, 'release', release,
                             result['press']['observed'], release_budget_ns, timeout_ms)
        if outcome is not None:
            if result['release']['observed_edge_at_target']:
                result['effect'] = 'press_and_release_observed'
            return finish(outcome)

        result.update(stage='complete', complete=True, effect='press_and_release_observed')
        return finish('completed')
    except BaseException as error:
        result['failure'] = type(error).__name__
        error.int33_click = finish('failed')
        raise
