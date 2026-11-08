"""Bounded models of emitted IL; not proof of an original AGI runtime."""
from copy import deepcopy

import pytest

from fdisbull.interaction_il import validate_il
from test_agi_control import loaded, lift


def symbolic_program(z3, program):
    validate_il(program)
    initial={name:z3.Bool(name) if decl['type']=='bool' else z3.Int(name)
             for name,decl in program['variables'].items()}
    domain=[z3.And(initial[name]>=0,initial[name]<=255)
            for name,decl in program['variables'].items() if decl['type']=='u8']
    assert all(decl['type'] in ('u8','bool') for decl in program['variables'].values())
    def value(item,state):
        if isinstance(item,dict):return state[item['var']]
        return z3.BoolVal(item) if type(item) is bool else z3.IntVal(item)
    def condition(item,state):
        op=item['op']
        if op=='eq':return value(item['left'],state)==value(item['right'],state)
        if op=='lt':return value(item['left'],state)<value(item['right'],state)
        if op=='not':return z3.Not(condition(item['condition'],state))
        if op=='and':return z3.And(*(condition(c,state) for c in item['conditions']))
        raise AssertionError('condition outside admitted proof model')
    def run(body,state):
        state=dict(state)
        for node in body:
            if node['op']=='set':state[node['var']]=value(node['value'],state)
            elif node['op']=='if':
                yes,no=run(node['then'],state),run(node['else'],state)
                predicate=condition(node['condition'],state)
                state={name:z3.If(predicate,yes[name],no[name]) for name in state}
            elif node['op']=='require':
                # Compiler's trace markers are tautologies; arbitrary guards
                # require a precondition model rather than being ignored.
                assert z3.is_true(z3.simplify(condition(node['condition'],state)))
            else:raise AssertionError('operation outside admitted proof model')
        return state
    return initial,run(program['body'],initial),domain


def test_call_return_model_equivalence_and_mutation_counterexample(tmp_path):
    z3=pytest.importorskip('z3')
    caller=bytes.fromhex('160104030200')  # call1; v3=v2; return
    callee=bytes.fromhex('ff0701ff040003020a0003021400')
    program=lift(loaded(tmp_path,{0:caller,1:callee},callee_entries={1:0}),
                 {'$agi_f1':False,'$agi_v2':0,'$agi_v3':0})['uil']
    initial,actual,domain=symbolic_program(z3,program)
    # Independent source contract: both callee returns resume the copy in caller.
    expected=z3.If(initial['$agi_f1'],10,20)
    solver=z3.Solver();solver.set(timeout=2000)
    solver.add(*domain,z3.Or(actual['$agi_v2']!=expected,actual['$agi_v3']!=expected,
                            actual['$agi_f1']!=initial['$agi_f1']))
    assert solver.check()==z3.unsat
    broken=deepcopy(program)
    def remove_copy(body):
        for node in list(body):
            if node.get('op')=='set' and node.get('var')=='$agi_v3':body.remove(node)
            elif node['op']=='if':remove_copy(node['then']);remove_copy(node['else'])
    remove_copy(broken['body'])
    before,after,constraints=symbolic_program(z3,broken)
    solver=z3.Solver();solver.set(timeout=2000)
    solver.add(*constraints,after['$agi_v3']!=z3.If(before['$agi_f1'],10,20))
    assert solver.check()==z3.sat
