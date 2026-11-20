"""Exact initial-match invariants for a wait that revalidates a pending press."""
from copy import deepcopy

import pytest


def initial_match_preserves_arm(debug, operation):
    before = debug.clock_observe()
    inputs = deepcopy(debug.input_state())
    owned = deepcopy(debug._input_storage())
    process = deepcopy(debug._process)
    assert owned['schedule']['bound'] and owned['schedule']['applied_count'] == 0
    assert inputs['schedule']['state'] == 'armed'
    assert inputs['schedule']['native']['press']['dispatched-count'] == 0
    peer, execute = debug.vm.gdb, debug.vm.gdb.execute
    def forbidden(*args, **kwargs):
        pytest.fail('An initial scene match attempted native execution')
    peer.execute = forbidden
    try:
        result = operation()
    finally:
        peer.execute = execute
    after = debug.clock_observe()
    stable_clock = lambda value: (value['epoch'], value['virtual_ns'], value['counter'])
    assert stable_clock(after) == stable_clock(before)
    current = debug.input_state()
    normalized = deepcopy(current)
    owned_after = deepcopy(debug._input_storage())
    # Revalidation refreshes these two observation fields only. Preserve every
    # other public/owned field, including token, native receipt, queue and cursor.
    for field in ('host_monotonic_ns', 'sequence'):
        old, new = inputs['schedule']['clock'][field], current['schedule']['clock'][field]
        assert type(old) is int and type(new) is int, field
        assert 0 <= old <= new, field
        if field == 'sequence':
            assert new > old, field
        normalized['schedule']['clock'][field] = old
        owned_after['schedule_receipt']['clock'][field] = old
    assert normalized == inputs
    assert owned_after == owned
    assert debug._process == process
    wait = result['wait']
    assert result['status'] == 'matched' and result['complete'] and result['capture_context_verified']
    assert wait['input_plan']['observed_input'] == current['schedule']
    assert not wait['input_plan']['first_slice_attempted']
    assert len(wait['polls']) == 1 and not wait['runs'] and wait['guest_elapsed_ns'] == 0
    clock = result['observation_context']['clock']
    assert stable_clock(clock['before']) == stable_clock(clock['after']) == stable_clock(before)
    assert 'frame' not in result
    return result
