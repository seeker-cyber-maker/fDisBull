import pytest
from fdisbull.action_continuations import ActionContinuation


def test_one_input_four_transitions_and_qualified_arrival_are_separate_from_effect():
    events, inputs, advances = [], [], []
    action = ActionContinuation('acknowledge notice', event=events.append)
    action.send_once(lambda: inputs.append('thumb') or {'accepted': True, 'delivery': 'queued'})
    frames = iter([{'destinations': [], 'interruptions': []}] * 4 +
                  [{'destinations': ['park'], 'interruptions': []}])
    result = action.wait(lambda: next(frames), advances.append)
    assert inputs == ['thumb'] and advances == [500] * 4
    assert result['arrival'] == 'qualified' and result['effect'] == 'unknown'
    assert action.confirm_effect()['effect'] == 'applied-confirmed'
    assert all(e['following_input'] == 'not_sent' for e in events if e['stage'] == 'observation')
    with pytest.raises(ValueError, match='already been attempted'):
        action.send_once(lambda: inputs.append('duplicate'))
    assert inputs == ['thumb']


def test_exception_after_dispatch_keeps_input_uncertain_and_blocks_replay():
    action = ActionContinuation('purchase')
    def lost(): raise EOFError('lost input reply')
    with pytest.raises(EOFError): action.send_once(lost)
    assert action.record['input'] == 'attempted' and action.record['effect'] == 'unknown'
    with pytest.raises(ValueError): action.send_once(lost)


def test_observation_budget_is_not_renewed_on_another_wait():
    action = ActionContinuation('travel', max_slices=2)
    advances = []
    observe = lambda: {'destinations': [], 'interruptions': ['known-notice']}
    assert action.wait(observe, advances.append)['arrival'] == 'unqualified'
    assert action.wait(observe, advances.append)['arrival'] == 'unqualified'
    assert advances == [500, 500]
    with pytest.raises(ValueError): action.confirm_effect()


def test_ambiguous_destination_stops_without_advancing_or_input():
    action = ActionContinuation('travel')
    result = action.wait(lambda: {'destinations': ['street', 'park'], 'interruptions': []},
                         lambda ms: pytest.fail('ambiguous observations must not advance'))
    assert result['arrival'] == 'ambiguous'
