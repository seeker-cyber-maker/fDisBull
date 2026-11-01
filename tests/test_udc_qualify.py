"""Independent typed IL examples qualify only the declared model projection."""
from copy import deepcopy

import pytest

import fdisbull.udc_qualify as qualification
from fdisbull.interaction_il import execute_il
from fdisbull.udc_qualify import qualify_uil


def program(types, body, resources=None):
    index = 0
    def identify(items):
        nonlocal index
        result = []
        for block in items:
            index += 1; item = dict(block, id='block_' + str(index))
            if item['op'] == 'if':item.update(then=identify(item['then']), **{'else': identify(item['else'])})
            result.append(item)
        return result
    return dict(format='fdisbull-il-1', role='uil', variables={n: dict(type=t, initial=False if t == 'bool' else 0) for n, t in types.items()}, resources=resources or {}, body=identify(body))


def contract(prog, inputs, outputs, domain=None):
    return dict(format='fdisbull-block-contract-1', name='authored.contract', inputs=inputs, outputs=outputs, behavior=dict(kind='uil', program=prog), domain=domain or {})


def set_(var, value):return dict(op='set', var=var, value=value)
def add(var, value):return dict(op='add', var=var, value=value)
def sub(var, value):return dict(op='subtract', var=var, value=value)
def ref(name):return {'var': name}
def eq(left, right):return dict(op='eq', left=left, right=right)
def req(condition):return dict(op='require', condition=condition)
def branch(condition, yes, no):return {'op': 'if', 'condition': condition, 'then': yes, 'else': no}


def sum_pair():
    types = {'$left': 'u16', '$right': 'u16', '$result': 'u16'}
    left = program(types, [set_('$result', ref('$left')), add('$result', ref('$right'))])
    right = program(types, [set_('$result', ref('$right')), add('$result', ref('$left')), add('$result', 0), sub('$result', 0)])
    return contract(left, {'left': 'u16', 'right': 'u16'}, {'result': 'u16'}), dict(backend='uil', program=right)


def test_commuted_sum_and_neutral_operations_have_a_model_proof():
    pytest.importorskip('z3')
    c, implementation = sum_pair()
    result = qualify_uil(c, implementation)
    assert result['status'] == 'equivalent_under_contract'
    assert result['method'] == 'bounded-scalar-z3' and result['reference_completion_possible'] is True
    assert result['programs']['reference_sha256'] != result['programs']['implementation_sha256']
    assert 'native-source' in result['proof_scope']


def test_wrong_carry_like_increment_returns_replayable_counterexample():
    pytest.importorskip('z3')
    c, implementation = sum_pair()
    implementation['program']['body'][-1]['value'] = 1
    result = qualify_uil(c, implementation)
    assert result['status'] == 'counterexample'
    assert set(result['inputs']) == {'left', 'right'}
    assert result['reference']['complete'] and result['implementation']['complete']
    assert result['reference']['outputs'] != result['implementation']['outputs']


def test_signed_modulo_model_matches_independent_exhaustive_i8_execution():
    pytest.importorskip('z3')
    types = {'$x': 'i8', '$result': 'i8'}
    left = program(types, [set_('$result', ref('$x')), add('$result', 1)])
    right = program(types, [set_('$result', ref('$x')), add('$result', 2), sub('$result', 1)])
    c = contract(left, {'x': 'i8'}, {'result': 'i8'})
    assert qualify_uil(c, dict(backend='uil', program=right))['status'] == 'equivalent_under_contract'
    for x in range(-128, 128):
        expected = (x + 1 + 128) % 256 - 128
        for p in (left, right):
            observed = execute_il(p, state={'$x': x, '$result': 0})
            assert observed['complete'] and observed['state']['$result'] == expected


def test_set_range_refusal_and_input_domain_are_observable():
    pytest.importorskip('z3')
    types = {'$x': 'i16', '$result': 'u8'}
    left = program(types, [set_('$result', ref('$x'))])
    right = program(types, [add('$result', ref('$x'))])
    c = contract(left, {'x': 'i16'}, {'result': 'u8'})
    result = qualify_uil(c, dict(backend='uil', program=right))
    assert result['status'] == 'counterexample'
    assert not result['reference']['complete'] and result['reference']['atomic_refusal']
    assert result['implementation']['complete']
    c['domain'] = {'x': {'min': 0, 'max': 255}}
    assert qualify_uil(c, dict(backend='uil', program=right))['status'] == 'equivalent_under_contract'


def test_require_failure_rolls_back_earlier_assignments_and_both_refusals_match():
    pytest.importorskip('z3')
    types = {'$x': 'u8', '$result': 'u8'}
    predicate = eq(ref('$x'), 0)
    left = program(types, [set_('$result', ref('$x')), req(predicate)])
    right = program(types, [req(predicate), set_('$result', ref('$x'))])
    c = contract(left, {'x': 'u8'}, {'result': 'u8'})
    assert qualify_uil(c, dict(backend='uil', program=right))['status'] == 'equivalent_under_contract'
    for p in (left, right):
        state = {'$x': 7, '$result': 0}
        observed = execute_il(p, state=state)
        assert observed['status'] == 'refused' and observed['state'] == state


def test_all_refuse_proof_is_explicitly_refusal_only():
    pytest.importorskip('z3')
    types = {'$x': 'u8', '$result': 'u8'}
    impossible = eq(0, 1)
    left = program(types, [set_('$result', ref('$x')), req(impossible)])
    right = program(types, [req(impossible), add('$result', 1)])
    result = qualify_uil(contract(left, {'x': 'u8'}, {'result': 'u8'}), dict(backend='uil', program=right))
    assert result['status'] == 'equivalent_under_contract'
    assert result['reference_completion_possible'] is False and result['proof_scope'].startswith('refusal-only')


def test_bool_and_not_and_bit_test_conditions_are_modeled():
    pytest.importorskip('z3')
    types = {'$x': 'u8', '$flag': 'bool', '$result': 'u8'}
    bit = dict(op='bit_test', value=ref('$x'), bit=1)
    yes = eq(ref('$flag'), True)
    left = program(types, [branch(dict(op='and', conditions=[bit, dict(op='not', condition=eq(ref('$flag'), False))]), [set_('$result', 1)], [set_('$result', 0)])])
    right = program(types, [branch(yes, [branch(bit, [set_('$result', 1)], [set_('$result', 0)])], [set_('$result', 0)])])
    result = qualify_uil(contract(left, {'x': 'u8', 'flag': 'bool'}, {'result': 'u8'}), dict(backend='uil', program=right))
    assert result['status'] == 'equivalent_under_contract'


def test_negative_signed_bit_test_preserves_shared_il_sign_extension():
    pytest.importorskip('z3')
    types = {'$x': 'i8', '$result': 'bool'}
    make = lambda bit: program(types, [branch(dict(op='bit_test', value=ref('$x'), bit=bit), [set_('$result', True)], [set_('$result', False)])])
    result = qualify_uil(contract(make(63), {'x': 'i8'}, {'result': 'bool'}), dict(backend='uil', program=make(7)))
    assert result['status'] == 'equivalent_under_contract'


def test_different_variable_names_use_exact_typed_port_maps():
    pytest.importorskip('z3')
    left = program({'$x': 'u16', '$result': 'u16'}, [set_('$result', ref('$x')), add('$result', 1)])
    right = program({'$arg': 'u16', '$out': 'u16'}, [set_('$out', ref('$arg')), add('$out', 1), add('$out', 0)])
    c = contract(left, {'x': 'u16'}, {'result': 'u16'})
    implementation = dict(backend='uil', program=right, inputs={'x': '$arg'}, outputs={'result': '$out'})
    assert qualify_uil(c, implementation)['status'] == 'equivalent_under_contract'
    implementation['outputs']['result'] = '$missing'
    with pytest.raises(ValueError, match='binding'):qualify_uil(c, implementation)


def test_shared_definition_can_ignore_only_metadata_and_preserves_event_data():
    left = program({}, [dict(op='text', resource='evidence')], {'evidence': {'kind': 'text', 'text': 'visible content'}})
    right = deepcopy(left); right['role'] = 'udl'; right['body'][0]['id'] = 'renamed'
    right['evidence'] = {'note': {'description': 'authored annotation'}}; right['body'][0]['evidence'] = ['note']
    c = contract(left, {}, {})
    result = qualify_uil(c, dict(backend='uil', program=right))
    assert result['status'] == 'equivalent_under_contract' and result['method'] == 'shared-definition'
    assert 'ordered event plans' in result['proof_scope']
    right['resources']['evidence']['text'] = 'different visible content'
    assert qualify_uil(c, dict(backend='uil', program=right))['status'] == 'unknown'


def test_different_event_order_is_not_discarded_by_scalar_proof():
    resources = {n: {'kind': 'text', 'text': n} for n in ('first', 'second')}
    left = program({}, [dict(op='text', resource='first'), dict(op='text', resource='second')], resources)
    right = program({}, [dict(op='text', resource='second'), dict(op='text', resource='first')], resources)
    result = qualify_uil(contract(left, {}, {}), dict(backend='uil', program=right))
    assert result['status'] == 'unknown' and 'eventful' in result['reason']


def test_extra_effect_claims_are_not_silently_proved_from_scalar_outputs():
    c, implementation = sum_pair()
    c['effects'] = {'ordered_writes': 'observable external state'}
    result = qualify_uil(c, implementation)
    assert result['status'] == 'unknown' and 'effects' in result['reason']


def test_qualification_receipt_is_detached_from_later_author_edits():
    c, implementation = sum_pair()
    result = qualify_uil(c, implementation)
    c['inputs']['left'] = 'u8'
    assert result['interfaces']['inputs']['left'] == 'u16'


def test_solver_unavailable_and_unknown_timeout_do_not_admit_programs(monkeypatch):
    c, implementation = sum_pair()
    monkeypatch.setattr(qualification, '_load_z3', lambda: None)
    assert qualify_uil(c, implementation)['status'] == 'unknown'
    z3 = pytest.importorskip('z3')
    class UnknownSolver:
        def __init__(self):self.real = z3.Solver()
        def __getattr__(self, name):return getattr(self.real, name)
        def check(self):return z3.unknown
        def reason_unknown(self):return 'timeout'
    class Provider:
        Solver = UnknownSolver
        def __getattr__(self, name):return getattr(z3, name)
    monkeypatch.setattr(qualification, '_load_z3', lambda: Provider())
    result = qualify_uil(c, implementation)
    assert result['status'] == 'unknown' and 'timeout' in result['reason']


def test_expired_total_budget_and_contradictory_domains_fail_closed(monkeypatch):
    pytest.importorskip('z3')
    c, implementation = sum_pair()
    c['domain'] = {'left': {'min': 2, 'max': 1}}
    with pytest.raises(ValueError, match='bound'):qualify_uil(c, implementation)
    c['domain'] = {}
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(qualification.time, 'monotonic', lambda: next(ticks))
    result = qualify_uil(c, implementation, timeout_ms=1)
    assert result['status'] == 'unknown' and 'timeout' in result['reason']


@pytest.mark.parametrize('timeout', [0, -1, True, 60001])
def test_timeout_argument_is_bounded(timeout):
    c, implementation = sum_pair()
    with pytest.raises(ValueError):qualify_uil(c, implementation, timeout_ms=timeout)
