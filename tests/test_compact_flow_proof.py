"""Bounded symbolic check of one authored graph, not a game-wide proof."""
from copy import deepcopy
import pytest

z3 = pytest.importorskip('z3')
from test_agi_control import loaded, lift


def symbolic_paths(document, initial):
    """Interpret only the admitted forms and enumerate this acyclic graph."""
    graphs = document['continuations']
    paths = []
    def value(v, state):
        if isinstance(v, dict) and set(v) == {'var'}:
            return state[v['var']]
        if type(v) is bool:
            return z3.BoolVal(v)
        if type(v) is int and 0 <= v <= 255:
            return z3.BitVecVal(v, 8)
        raise AssertionError('unsupported value')
    def condition(c, state):
        if c['op'] == 'eq' and set(c) == {'op', 'left', 'right'}:
            return value(c['left'], state) == value(c['right'], state)
        if c['op'] == 'lt' and set(c) == {'op', 'left', 'right'}:
            return z3.ULT(value(c['left'], state), value(c['right'], state))
        if c['op'] == 'not' and set(c) == {'op', 'condition'}:
            return z3.Not(condition(c['condition'], state))
        if c['op'] == 'and' and set(c) == {'op', 'conditions'}:
            return z3.And(*(condition(x, state) for x in c['conditions']))
        raise AssertionError('unsupported condition')
    def blocks(items, state, guard):
        pending = [(state, guard)]
        for block in items:
            output = []
            for current, path in pending:
                op = block['op']
                if op == 'set':
                    updated = dict(current)
                    updated[block['var']] = value(block['value'], current)
                    output.append((updated, path))
                elif op == 'require':
                    output.append((current, z3.And(path, condition(block['condition'], current))))
                elif op == 'if':
                    test = condition(block['condition'], current)
                    output.extend(blocks(block['then'], dict(current), z3.And(path, test)))
                    output.extend(blocks(block['else'], dict(current), z3.And(path, z3.Not(test))))
                else:
                    raise AssertionError('unsupported body operation')
            pending = output
        return pending
    def visit(name, stack, state, guard, visited):
        key = (name, tuple(stack))
        assert key not in visited and len(visited) < 64, 'model must be bounded and acyclic'
        visited = visited | {key}
        node = graphs[name]
        for next_state, next_guard in blocks(node['body'], state, guard):
            transfer = node['transfer']; op = transfer['op']
            if op == 'goto':
                visit(transfer['target'], stack, next_state, next_guard, visited)
            elif op == 'if':
                test = condition(transfer['condition'], next_state)
                visit(transfer['then'], stack, dict(next_state), z3.And(next_guard, test), visited)
                visit(transfer['else'], stack, dict(next_state), z3.And(next_guard, z3.Not(test)), visited)
            elif op == 'call':
                visit(transfer['target'], stack + [transfer['resume']], next_state, next_guard, visited)
            elif op == 'return' and stack:
                assert stack[-1] is not None
                visit(stack[-1], stack[:-1], next_state, next_guard, visited)
            elif op in ('return', 'stop'):
                paths.append((next_guard, next_state))
            else:
                raise AssertionError('unsupported transfer')

    visit(document['entry'], [], initial, z3.BoolVal(True), set())
    return paths


def test_authored_shared_callee_matches_symbolic_contract_and_detects_mutation(tmp_path):
    caller = bytes.fromhex('1601040302160104040200')
    callee = bytes.fromhex('ff0701ff040003020a0003021400')
    program = loaded(tmp_path, {0: caller, 1: callee}, callee_entries={1: 0})
    defaults = {'$agi_f1': False, '$agi_v2': 0, '$agi_v3': 0, '$agi_v4': 0}
    graph = lift(program, defaults, control_flow='compact')['uil']
    initial = {name: z3.Bool(name) if type(v) is bool else z3.BitVec(name, 8)
               for name, v in defaults.items()}
    expected = z3.If(initial['$agi_f1'], z3.BitVecVal(10, 8), z3.BitVecVal(20, 8))

    def mismatch(doc):
        paths = symbolic_paths(doc, initial)
        coverage = z3.Solver(); coverage.set(timeout=5000)
        coverage.add(z3.Not(z3.Or(*(guard for guard, _ in paths))))
        assert coverage.check() == z3.unsat, 'no initial state may disappear from the proof'
        solver = z3.Solver(); solver.set(timeout=5000)
        solver.add(z3.Or(*(z3.And(guard, z3.Or(state['$agi_f1'] != initial['$agi_f1'],
                      *(state[n] != expected for n in ('$agi_v2', '$agi_v3', '$agi_v4'))))
                      for guard, state in paths)))
        return solver.check()

    assert mismatch(graph) == z3.unsat
    mutant = deepcopy(graph)
    copy = next(block for c in mutant['continuations'].values() for block in c['body']
                if block['op'] == 'set' and block['var'] == '$agi_v3')
    copy['value'] = 0
    assert mismatch(mutant) == z3.sat
