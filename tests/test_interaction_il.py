from copy import deepcopy
import pytest
from fdisbull.interaction_il import ILInvalid, change_role, execute_il, validate_il


def program():
    return {'format': 'fdisbull-il-1', 'role': 'udl',
            'variables': {'$money': {'type': 'u8', 'initial': 255}, '$signed': {'type': 'i8', 'initial': 127}, '$opened': {'type': 'bool', 'initial': False}},
            'resources': {'msg': {'kind': 'text', 'text': 'Hello'}, 'pic': {'kind': 'graphic', 'uri': 'image.bin'}},
            'evidence': {'src': {'sha256': 'a' * 64, 'range': [1, 4]}},
            'body': [{'id': 'a', 'op': 'add', 'var': '$money', 'value': 1, 'evidence': ['src']},
                     {'id': 'b', 'op': 'add', 'var': '$signed', 'value': 1},
                     {'id': 'c', 'op': 'if', 'condition': {'op': 'eq', 'left': {'var': '$money'}, 'right': 0},
                      'then': [{'id': 'd', 'op': 'set', 'var': '$opened', 'value': True}, {'id': 'e', 'op': 'text', 'resource': 'msg', 'evidence': ['src']}], 'else': []}]}


def test_role_is_only_metadata_and_arithmetic():
    p = program(); other = change_role(p, 'uil')
    assert p['role'] == 'udl' and other['role'] == 'uil'
    a = execute_il(p); b = execute_il(other)
    assert a == b and a['complete']
    assert a['state'] == {'$money': 0, '$signed': -128, '$opened': True}
    assert a['events'][0]['evidence'] == ['src'] and a['evidence'] == p['evidence']


def test_bool_arithmetic_refused_and_bad_state_is_atomic():
    p = program(); p['body'][0]['var'] = '$opened'
    with pytest.raises(ILInvalid): validate_il(p)
    p = program(); state = {'$money': 256, '$signed': 0, '$opened': False}
    result = execute_il(p, state)
    assert result['status'] == 'refused' and result['state'] == state and result['events'] == []


def test_host_preflight_in_unselected_branch_and_pending():
    p = program(); graphic = {'id': 'g', 'op': 'load_graphic', 'resource': 'pic', 'x': 0, 'y': 1}
    p['body'][2]['else'] = [graphic]
    assert execute_il(p)['status'] == 'refused'
    p['body'][2]['then'].append(graphic); p['body'][2]['else'] = []
    result = execute_il(p, capabilities=['graphics'])
    assert result['status'] == 'pending_host' and not result['complete']
    assert result['state']['$money'] == 255 and result['proposed_state']['$money'] == 0
    assert result['events'][-1]['block_id'] == 'g'


def test_budget_and_evidence_refuse_without_effects():
    p = program(); result = execute_il(p, max_steps=1)
    assert result['status'] == 'refused' and result['events'] == [] and result['state']['$money'] == 255
    p['body'][0]['evidence'] = ['missing']
    with pytest.raises(ILInvalid): validate_il(p)
    p = program(); p['body'] = [{'id': str(i), 'op': 'text', 'resource': 'msg'} for i in range(1025)]
    assert execute_il(p)['status'] == 'refused'


def test_unsigned_ge_gate_accepts_equal_and_rejects_shortfall():
    p = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
         'variables': {'$treasury': {'type': 'u16', 'initial': 160},
                       '$price': {'type': 'u16', 'initial': 160}},
         'body': [{'id': 'gate', 'op': 'require',
                   'condition': {'op': 'ge', 'left': {'var': '$treasury'},
                                 'right': {'var': '$price'}}}]}
    assert execute_il(p)['status'] == 'complete'
    p['variables']['$treasury']['initial'] = 159
    assert execute_il(p)['status'] == 'refused'
    p['variables']['$price'] = {'type': 'i16', 'initial': 0}
    with pytest.raises(ILInvalid):
        validate_il(p)
