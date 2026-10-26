"""Observation waits must preserve evidence and stop boundaries."""
from types import SimpleNamespace

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debug_wait import wait_until


class Target:
    """Deterministic guest-clock model for failure paths; native coverage is separate."""
    def __init__(self, values=(0, 1), stop='guest_time'):
        self.values = values
        self.index = 0
        self.stop = stop
        self.events = []
        self.runs = []
        self.rpc = SimpleNamespace(capabilities={'timing': {'fast_forward': True}})
        self.run_id = 'model'

    def memory(self, address, length):
        return dict(hex=self.values[min(self.index, len(self.values)-1)].to_bytes(length, 'little').hex(),
                    project_address=address)

    def registers(self):
        return {'general': {'eax': hex(self.index)}}

    def status(self):
        return {'video': {'frame_counter': self.index}}

    def run(self, **params):
        self.runs.append(params)
        self.index += 1
        return dict(outcome=self.stop, guest_elapsed_ms=params['guest_ms'],
                    hook_hits=[{'hook': 'test'}] if self.stop == 'hook' else [])

    def screenshot(self, name):
        return {'artifact': 'diagnostic', 'name': name}

    def _event(self, op, result):
        self.events.append((op, result))

    def _artifact(self, *args):
        return {'artifact': 'saved'}

    def wait(self, *args, **params):
        return wait_until(self, *args, **params)


OBS = {'counter': {'kind': 'memory', 'address': '0x10000', 'length': 2}}
UNTIL = {'observation': 'counter', 'equals': '0100'}


def test_true_initially_does_not_execute_guest():
    target = Target((1,))
    result = wait_until(target, OBS, UNTIL, guest_ms=100)
    assert result['complete'] and result['matched']
    assert not target.runs and result['guest_elapsed_ms'] == 0


def test_measured_progress_and_saved_script_wait_binding():
    target = Target((0, 0, 1))
    script = {'format': 'fdisbull-script-1', 'steps': [
        dict(op='wait', observations=OBS, until=UNTIL, guest_ms=100, slice_ms=10, **{'as': 'ready'}),
        dict(op='assert', value='$ready.matched', equals=True)]}
    result = execute_script(target, script)
    assert result['ok'], result
    wait = result['steps'][0]['result']
    assert wait['guest_elapsed_ms'] == 20 and len(wait['polls']) == 3
    assert all(run['stop_on_hook'] for run in target.runs)


def test_false_is_bounded_and_script_does_not_continue():
    target = Target((0,))
    result = execute_script(target, {'format': 'fdisbull-script-1', 'steps': [
        dict(op='wait', observations=OBS, until=UNTIL, guest_ms=20, slice_ms=10),
        dict(op='registers')]})
    assert not result['ok'] and len(result['steps']) == 1
    wait = result['steps'][0]['result']
    assert wait['outcome'] == 'guest_budget' and not wait['complete']
    assert wait['last_observation'] == {'counter': '0000'}
    assert wait['diagnostic_frame']['artifact'] == 'diagnostic'


@pytest.mark.parametrize('stop', ['breakpoint', 'watchpoint', 'hook', 'exited', 'error', 'timeout'])
def test_stops_win_over_matching_post_stop_bytes(stop):
    target = Target((0, 1), stop=stop)
    result = wait_until(target, OBS, UNTIL, guest_ms=100)
    assert result['outcome'] == stop and not result['complete']
    assert len(target.runs) == 1 and result['stop']['outcome'] == stop


def test_register_mask_memory_mask_and_frame_counter_require_explicit_observations():
    target = Target((0x8000, 0x8001))
    observations = {**OBS, 'ax': {'kind': 'register', 'path': 'general.eax'},
                    'frame': {'kind': 'status', 'path': 'video.frame_counter'}}
    until = {'all': [dict(observation='counter', equals='0100', mask='ff00'),
                      dict(observation='ax', ge=1), dict(observation='frame', greater_than_initial=True)]}
    result = wait_until(target, observations, until, guest_ms=100)
    assert result['complete'] and len(target.runs) == 1


def test_missing_required_capture_never_succeeds_even_in_any_predicate():
    target = Target((1,))
    obs = {**OBS, 'missing': {'kind': 'status', 'path': 'video.no_such_field'}}
    result = wait_until(target, obs, {'any': [UNTIL]}, guest_ms=100)
    assert not result['complete'] and result['outcome'] == 'incomplete'
    assert result['last_observation'] == {'counter': '0100'}
    assert not target.runs


def test_short_memory_capture_and_failed_diagnostic_remain_incomplete():
    target = Target()
    target.memory = lambda **params: {'hex': '01'}
    def broken(name):
        raise RuntimeError('No frame')
    target.screenshot = broken
    result = wait_until(target, OBS, UNTIL, guest_ms=100)
    assert not result['complete'] and result['error'] and result['capture_error']


def test_bad_later_predicate_rejected_before_any_operation():
    target = Target()
    script = {'format': 'fdisbull-script-1', 'steps': [dict(op='registers'),
        dict(op='wait', observations=OBS, until=dict(observation='missing', equals='0100'), guest_ms=10)]}
    with pytest.raises(ValueError, match='unknown observation'):
        execute_script(target, script)
    assert not target.events


@pytest.mark.parametrize('extra', [dict(guest_ms=True), dict(slice_ms=0), dict(max_polls=0),
    dict(until=dict(observation='counter', equals='01')), dict(until=dict(observation='counter', equals='0100', mask='ff'))])
def test_preflight_rejects_invalid_budgets_and_comparisons(extra):
    params = dict(observations=OBS, until=UNTIL, guest_ms=100)
    params.update(extra)
    with pytest.raises(ValueError):
        validate_script({'format': 'fdisbull-script-1', 'steps': [dict(op='wait', **params)]})


def test_poll_limit_and_unavailable_clock():
    target = Target((0,))
    result = wait_until(target, OBS, UNTIL, guest_ms=100, max_polls=1)
    assert result['outcome'] == 'poll_budget' and not target.runs
    target.rpc.capabilities = {}
    with pytest.raises(ValueError, match='guest time'):
        wait_until(target, OBS, UNTIL, guest_ms=100)


def test_wall_budget_is_not_reported_as_guest_budget(monkeypatch):
    import fdisbull.debug_wait as module
    clock = [0.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    target = Target((0,))
    run = target.run
    def advance(**params):
        clock[0] += 0.1
        return run(**params)
    target.run = advance
    result = wait_until(target, OBS, UNTIL, guest_ms=10000, slice_ms=10, timeout_ms=100)
    assert result['outcome'] == 'timeout' and result['guest_elapsed_ms'] == 10


def test_guest_exception_is_recorded_and_no_more_runs():
    target = Target((0,))
    def broken(**params):
        raise RuntimeError('guest error')
    target.run = broken
    result = wait_until(target, OBS, UNTIL, guest_ms=100)
    assert result['outcome'] == 'incomplete' and result['error']['message'] == 'guest error'


def test_slice_overshoot_cannot_prove_match_within_guest_budget():
    target=Target((0,1))
    original=target.run
    def overshoot(**params):
        result=original(**params);result['guest_elapsed_ms']=101
        return result
    target.run=overshoot
    result=wait_until(target,OBS,UNTIL,guest_ms=100)
    assert not result['matched'] and result['outcome']=='guest_budget'
    assert result['last_observation']['counter']=='0100'
    assert result['guest_budget_overshoot_ms']==1
