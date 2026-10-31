"""Authored source programs for the bounded AGI reference, not game data."""
from copy import deepcopy

import pytest

from fdisbull.agi_slice import AGISliceError, run_slice


def payload(code):
    return len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])


def state():
    value = {'variables': [0] * 256, 'flags': [False] * 256,
             'ego': {'x': 80, 'y': 90}, 'words': [42],
             'player_control': True, 'host': {'marker': ['untouched']}}
    value['flags'][2] = True
    return value


def run(code, before=None, **options):
    return run_slice(payload(code), state() if before is None else before,
                     entry=2, stop=2 + len(code), **options)


def condition(tokens, body):
    return b'\xff' + tokens + b'\xff' + len(body).to_bytes(2, 'little') + body


def said(*groups):
    return bytes([14, len(groups)]) + b''.join(group.to_bytes(2, 'little') for group in groups)


def test_arithmetic_flags_and_positions_preserve_order_and_input_state():
    code = bytes.fromhex('0303ff0503030703040c160d1627003c3d073c0726003c3d')
    before = state()
    original = deepcopy(before)
    result = run(code, before)
    assert result['status'] == 'complete' and result['pc'] == 2 + len(code)
    assert result['state']['variables'][3] == 254
    assert result['state']['variables'][60:62] == [73, 90]
    assert result['state']['ego'] == {'x': 73, 'y': 90}
    assert result['state']['flags'][22] is False
    assert result['effects'] == [
        {'operation': 'assignn', 'operands': [3, 255]},
        {'operation': 'addn', 'operands': [3, 3]},
        {'operation': 'subn', 'operands': [3, 4]},
        {'operation': 'set', 'operands': [22]},
        {'operation': 'reset', 'operands': [22]},
        {'operation': 'get.posn', 'operands': [0, 60, 61]},
        {'operation': 'subn', 'operands': [60, 7]},
        {'operation': 'position.v', 'operands': [0, 60, 61]},
    ]
    assert before == original
    result['state']['host']['marker'].append('caller mutation')
    assert before == original


def test_actor_engine_requests_preserve_loop_before_view_and_implicit_writes():
    code = bytes.fromhex('24004d002900092f0000031f024c001f23004900162b00012900004e00')
    before = state()
    before['variables'][6] = 7
    before['flags'][22] = True
    result = run(code, before)
    assert [item['operation'] for item in result['effects']] == [
        'erase', 'stop.motion', 'set.view', 'set.cel', 'assignn',
        'cycle.time', 'draw', 'end.of.loop', 'set.loop', 'set.view', 'start.motion']
    assert result['effects'][8:10] == [
        {'operation': 'set.loop', 'operands': [0, 1]},
        {'operation': 'set.view', 'operands': [0, 0]}]
    assert result['state']['variables'][6] == 0
    assert result['state']['flags'][22] is False
    assert result['state']['player_control'] is True
    assert result['state']['ego'] == before['ego']
    stopped = run(bytes.fromhex('4d00'), before)
    assert stopped['state']['player_control'] is False
    assert stopped['state']['variables'][6] == 0
    # Actor view/cel/scheduler behavior is requested, not invented in state.
    assert set(result['state']) == set(before)


def test_get_position_alias_uses_source_write_order_and_byte_arithmetic():
    before = state()
    before['ego'] = {'x': 250, 'y': 251}
    result = run(bytes.fromhex('27003c3c053c0726003c3c'), before)
    assert result['state']['variables'][60] == 2
    assert result['state']['ego'] == {'x': 2, 'y': 2}


def test_modal_output_pauses_after_each_print_and_resumes_at_next_instruction():
    code = bytes.fromhex('0c18650105030365020d18')
    before = state()
    first = run(code, before)
    assert first['status'] == 'awaiting_ack' and first['pc'] == 6
    assert first['state']['flags'][24] is True
    assert first['state']['variables'][3] == 0
    assert first['effects'] == [
        {'operation': 'set', 'operands': [24]},
        {'operation': 'print', 'operands': [1]}]
    second = run_slice(payload(code), first['state'], entry=first['pc'], stop=2 + len(code))
    assert second['status'] == 'awaiting_ack' and second['pc'] == 11
    assert second['state']['variables'][3] == 3
    assert second['state']['flags'][24] is True
    third = run_slice(payload(code), second['state'], entry=second['pc'], stop=2 + len(code))
    assert third['status'] == 'complete'
    assert third['state']['flags'][24] is False
    assert before == state()


@pytest.mark.parametrize('field', ['output_mode', 'auto_close'])
def test_unqualified_print_mode_is_refused(field):
    before = state()
    if field == 'output_mode':
        before['flags'][15] = True
    else:
        before['variables'][21] = 1
    original = deepcopy(before)
    with pytest.raises(AGISliceError, match='blocking print'):
        run(bytes.fromhex('0c186501'), before)
    assert before == original


def test_and_short_circuit_does_not_consume_a_skipped_said():
    code = condition(bytes([7, 10]) + said(42), bytes([12, 11]))
    result = run(code)
    assert not result['state']['flags'][4]
    assert not result['state']['flags'][11]
    assert result['effects'] == []
    assert result['executed_offsets'] == [2]


def test_or_short_circuit_skips_said_then_later_said_claims_input_once():
    before = state()
    before['flags'][10] = True
    tokens = bytes([252, 7, 10]) + said(42) + bytes([252]) + said(42)
    code = condition(tokens, bytes([12, 11]))
    result = run(code, before)
    assert result['state']['flags'][4] is True
    assert result['state']['flags'][11] is True
    assert result['effects'] == [{'operation': 'set', 'operands': [11]}]


def test_said_consumption_survives_later_false_or_negation():
    for tokens in (said(42) + bytes([7, 10]), bytes([253]) + said(42)):
        result = run(condition(tokens, bytes([12, 11])))
        assert result['state']['flags'][4] is True
        assert result['state']['flags'][11] is False
        assert result['effects'] == []


def test_successful_or_said_does_not_evaluate_remaining_said_or_reclaim_input():
    tokens = bytes([252]) + said(42, 99) + said(42) + bytes([252])
    code = condition(tokens, bytes([12, 11])) + condition(said(42), bytes([12, 12]))
    result = run(code)
    assert result['state']['flags'][4] is True
    assert result['state']['flags'][11] is True
    assert result['state']['flags'][12] is False


@pytest.mark.parametrize('words,ready,accepted,matched', [
    ([42], True, False, True), ([42, 99], True, False, False),
    ([], True, False, False), ([42], False, False, False),
    ([42], True, True, False), ([99], True, False, False),
])
def test_said_matches_exact_groups_and_parser_admission(words, ready, accepted, matched):
    before = state()
    before['words'] = words
    before['flags'][2], before['flags'][4] = ready, accepted
    result = run(condition(said(42), bytes([12, 11])), before)
    assert result['state']['flags'][11] is matched
    assert result['state']['flags'][4] is (accepted or matched)


@pytest.mark.parametrize('x,y,inside', [
    (18, 80, True), (67, 107, True), (40, 90, True),
    (17, 80, False), (68, 107, False), (18, 79, False), (67, 108, False),
])
def test_posn_uses_inclusive_left_baseline_geometry(x, y, inside):
    before = state()
    before['ego'] = {'x': x, 'y': y}
    result = run(condition(bytes([11, 0, 18, 80, 67, 107]), bytes([12, 11])), before)
    assert result['state']['flags'][11] is inside


def test_numeric_conditions_use_unsigned_bytes_and_exact_equality():
    before = state()
    before['variables'][40:42] = [255, 1]
    tokens = bytes.fromhex('0128ff022828032902042928052801062829')
    result = run(condition(tokens, bytes([12, 11])), before)
    assert result['state']['flags'][11] is True


def test_ambiguous_conditional_zero_is_refused_in_this_reference_profile():
    with pytest.raises(AGISliceError, match='conditional zero'):
        run(condition(b'\x00', bytes([12, 11])))


def test_high_bit_conditional_offset_is_refused_instead_of_becoming_backward_flow():
    # The layout tool interprets the displacement as signed. The pinned engine
    # uses an unsigned IF displacement, so this narrow executor cannot endorse
    # the layout's apparent backward loop as reference execution.
    with pytest.raises(AGISliceError, match='conditional displacement'):
        run(bytes.fromhex('ff070afffaff'), max_steps=1)


def test_goto_changes_flow_without_becoming_a_source_action_effect():
    code = bytes.fromhex('fe0300030309030304')
    result = run(code)
    assert result['state']['variables'][3] == 4
    assert result['executed_offsets'] == [2, 8]
    assert result['effects'] == [{'operation': 'assignn', 'operands': [3, 4]}]


def test_instruction_budget_refuses_without_changing_input():
    before = state()
    original = deepcopy(before)
    with pytest.raises(AGISliceError, match='budget'):
        run(bytes.fromhex('050301fefaff'), before, max_steps=5)
    assert before == original


@pytest.mark.parametrize('code,reason', [
    (bytes([130, 1, 4, 30]), 'action'),
    (condition(bytes([13]), bytes([12, 11])), 'predicate'),
    (bytes([35, 1]), 'ego'),
    (condition(bytes([11, 1, 0, 0, 50, 50]), bytes([12, 11])), 'ego'),
    (condition(bytes([252, 252, 7, 10]), bytes([12, 11])), 'OR'),
    (condition(said(1), bytes([12, 11])), 'wildcard'),
    (condition(said(9999), bytes([12, 11])), 'wildcard'),
])
def test_unsupported_execution_is_explicit(code, reason):
    with pytest.raises(AGISliceError, match=reason):
        run(code)


@pytest.mark.parametrize('change', [
    lambda s: s['variables'].__setitem__(0, True),
    lambda s: s['variables'].__setitem__(0, 256),
    lambda s: s['variables'].pop(),
    lambda s: s['flags'].__setitem__(0, 1),
    lambda s: s['flags'].pop(),
    lambda s: s['ego'].__setitem__('x', -1),
    lambda s: s['ego'].__setitem__('y', True),
    lambda s: s['words'].append(65536),
    lambda s: s['words'].append(False),
    lambda s: s.__setitem__('player_control', 1),
    lambda s: s.__setitem__('extra', 1),
    lambda s: s.__setitem__('host', []),
])
def test_invalid_concrete_state_is_rejected(change):
    before = state()
    change(before)
    with pytest.raises(AGISliceError):
        run(b'\x00', before)


@pytest.mark.parametrize('options', [
    {'entry': True}, {'entry': 3}, {'stop': 4}, {'stop': 99},
    {'max_steps': True}, {'max_steps': 0}, {'max_steps': 200001},
])
def test_invalid_boundaries_and_budgets_are_rejected(options):
    code = bytes.fromhex('03030100')
    with pytest.raises(AGISliceError):
        run_slice(payload(code), state(), **{'entry': 2, 'stop': 6, **options})


def test_branch_cannot_jump_past_selected_stop():
    code = bytes.fromhex('fe030003030100')
    with pytest.raises(AGISliceError, match='stop'):
        run_slice(payload(code), state(), entry=2, stop=5)


def test_return_ends_invocation_and_stop_entry_is_empty_completion():
    result = run(bytes.fromhex('00030309'))
    assert result['status'] == 'complete' and result['pc'] == 3
    assert result['state']['variables'][3] == 0
    assert result['effects'] == [{'operation': 'return', 'operands': []}]
    source = payload(b'\x00')
    empty = run_slice(source, state(), entry=3, stop=3)
    assert empty['status'] == 'complete' and empty['executed_offsets'] == []
