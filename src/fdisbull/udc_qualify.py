"""Pure shared-IL contract qualification; no native/source fidelity claim.

Exact definitions retain ordered event plans. Different definitions are admitted
only by the scalar atomic IL model implemented here, over the typed input domain.
"""
from __future__ import annotations

import hashlib
import json
import time

from .interaction_il import execute_il, validate_il


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):return hashlib.sha256(_encoded(value)).hexdigest()


def _load_z3():
    try:import z3
    except ImportError:return None
    return z3


class _ModelBudget(Exception):
    pass


def _semantic(program):
    # Only metadata fields are removed. A resource actually named "evidence"
    # or "id" must retain its data and participate in this identity check.
    def body(items):
        result = []
        for item in items:
            cleaned = {k: v for k, v in item.items() if k not in ('id', 'evidence')}
            if item['op'] == 'if':cleaned.update(then=body(item['then']), **{'else': body(item['else'])})
            result.append(cleaned)
        return result
    return dict(format=program['format'], variables=program['variables'], resources=program['resources'], body=body(program['body']))


def _ports(descriptor, contract):
    program = descriptor.get('program'); validate_il(program)
    maps = {}
    for side in ('inputs', 'outputs'):
        mapping = descriptor.get(side, {name: '$' + name for name in contract[side]})
        if type(mapping) is not dict or set(mapping) != set(contract[side]):raise ValueError('UIL port bindings must match contract ports exactly')
        for port, var in mapping.items():
            if not isinstance(var, str) or var not in program['variables'] or program['variables'][var]['type'] != contract[side][port]:raise ValueError('UIL port type/binding mismatch')
        if side == 'inputs' and len(set(mapping.values())) != len(mapping):raise ValueError('UIL input bindings must identify distinct variables')
        maps[side] = mapping
    return program, maps


def _pure(body):
    for block in body:
        if block['op'] not in ('set', 'add', 'subtract', 'if', 'require'):return False
        if block['op'] == 'if' and not (_pure(block['then']) and _pure(block['else'])):return False
    return True


def _range(z3, value, typ):
    if typ == 'bool':return z3.BoolVal(True)
    bits = int(typ[1:])
    low, high = (0, (1 << bits) - 1) if typ[0] == 'u' else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)
    return z3.And(value >= low, value <= high)


def _symbolic(z3, program, ports, inputs, deadline):
    variables = program['variables']
    state = {name: z3.BoolVal(item['initial']) if item['type'] == 'bool' else z3.IntVal(item['initial']) for name, item in variables.items()}
    for port, variable in ports['inputs'].items():state[variable] = inputs[port]

    def value(item, work):
        if isinstance(item, dict):return work[item['var']]
        return z3.BoolVal(item) if type(item) is bool else z3.IntVal(item)

    def condition(item, work):
        op = item['op']
        if op == 'eq':return value(item['left'], work) == value(item['right'], work)
        if op == 'bit_test':return (value(item['value'], work) / (1 << item['bit'])) % 2 == 1
        if op == 'not':return z3.Not(condition(item['condition'], work))
        return z3.And(*(condition(child, work) for child in item['conditions']))

    def run(body, work, complete):
        for block in body:
            if time.monotonic() >= deadline:raise _ModelBudget('model construction exceeded timeout budget')
            op = block['op']
            if op == 'require':complete = z3.And(complete, condition(block['condition'], work))
            elif op == 'if':
                choose = condition(block['condition'], work)
                left, a = run(block['then'], dict(work), z3.And(complete, choose))
                right, b = run(block['else'], dict(work), z3.And(complete, z3.Not(choose)))
                for name in work:
                    if left[name] is not work[name] or right[name] is not work[name]:work[name] = z3.If(choose, left[name], right[name])
                complete = z3.Or(a, b)
            else:
                name = block['var']; typ = variables[name]['type']; operand = value(block['value'], work)
                if op == 'set':
                    complete = z3.And(complete, _range(z3, operand, typ)); work[name] = operand
                else:
                    width = 1 << int(typ[1:])
                    result = (work[name] + (operand if op == 'add' else -operand)) % width
                    work[name] = z3.If(result >= width // 2, result - width, result) if typ[0] == 'i' else result
        return work, complete

    work, complete = run(program['body'], state, z3.BoolVal(True))
    return complete, {port: work[variable] for port, variable in ports['outputs'].items()}


def _concrete(program, ports, inputs):
    state = {name: declaration['initial'] for name, declaration in program['variables'].items()}
    for port, variable in ports['inputs'].items():state[variable] = inputs[port]
    result = execute_il(program, state=state, max_steps=4096)
    return dict(complete=result['status'] == 'complete', status=result['status'],
                outputs={port: result['state'][variable] for port, variable in ports['outputs'].items()} if result['status'] == 'complete' else None,
                atomic_refusal=result['state'] == state if result['status'] == 'refused' else None)


def _check(solver, deadline):
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:return None, 'timeout budget exhausted'
    solver.set(timeout=remaining)
    result = solver.check()
    return result, solver.reason_unknown() if str(result) == 'unknown' else None


def qualify_uil(contract, implementation, timeout_ms=2000):
    """Compare completion and declared outputs, including atomic refusal.

    The result qualifies supplied IL models only. It does not prove source
    recovery, native compiler correctness, ABI/effect fidelity, or whole games.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:raise ValueError('timeout_ms must be 1..60000')
    deadline = time.monotonic() + timeout_ms / 1000
    from .udc_layers import validate_contract
    contract = validate_contract(contract)
    if contract['behavior']['kind'] != 'uil':raise ValueError('UIL qualification requires a shared-IL behavior contract')
    if type(implementation) is not dict or implementation.get('backend') != 'uil' or set(implementation) - {'backend', 'program', 'inputs', 'outputs', 'return', 'notification_binding'}:raise ValueError('qualification requires an explicit UIL implementation descriptor')
    left, left_ports = _ports(contract['behavior'], contract)
    right, right_ports = _ports(implementation, contract)
    # Detach the accepted JSON inputs so the receipt's digest/interface cannot
    # change when a caller later edits its authored document.
    implementation = json.loads(_encoded(implementation))
    right, right_ports = _ports(implementation, contract)
    receipt = dict(format='fdisbull-uil-qualification-1', status='unknown', timeout_ms=timeout_ms,
        programs=dict(reference_sha256=_sha(left), implementation_sha256=_sha(right)),
        interfaces=dict(inputs=contract['inputs'], outputs=contract['outputs'], reference=left_ports, implementation=right_ports),
        domain=contract.get('domain', {}), reference_completion_possible=None,
        contract_sha256=_sha(contract),
        proof_scope='shared-IL completion and declared output projection; atomic refusal; no native-source or whole-program claim')
    exact = _semantic(left) == _semantic(right) and left_ports == right_ports
    if exact:
        return dict(receipt, status='equivalent_under_contract', method='shared-definition',
                    proof_scope='same shared-IL definition and interface, including ordered event plans; successful execution and native realization remain unqualified')
    if not (_pure(left['body']) and _pure(right['body'])):
        return dict(receipt, reason='different eventful/unsupported IL programs are outside the scalar qualification profile')
    if contract.get('effects'):
        return dict(receipt, reason='additional declared contract effects are outside the scalar output-projection profile')
    z3 = _load_z3()
    if z3 is None:return dict(receipt, reason='Z3 solver is unavailable')
    solver = z3.Solver()
    inputs = {name: z3.Bool('input_' + name) if typ == 'bool' else z3.Int('input_' + name) for name, typ in contract['inputs'].items()}
    for name, typ in contract['inputs'].items():solver.add(_range(z3, inputs[name], typ))
    for name, bound in contract.get('domain', {}).items():
        if contract['inputs'][name] == 'bool':
            if bound['min'] == bound['max']:solver.add(inputs[name] == z3.BoolVal(bound['min']))
        else:solver.add(inputs[name] >= bound['min'], inputs[name] <= bound['max'])
    checked, reason = _check(solver, deadline)
    if checked is None or checked == z3.unknown:return dict(receipt, reason='domain check unknown: ' + str(reason))
    if checked == z3.unsat:return dict(receipt, reason='admitted input domain is empty')
    try:
        left_complete, left_outputs = _symbolic(z3, left, left_ports, inputs, deadline)
        right_complete, right_outputs = _symbolic(z3, right, right_ports, inputs, deadline)
    except _ModelBudget as exc:return dict(receipt, reason=str(exc))
    solver.push(); solver.add(left_complete)
    checked, reason = _check(solver, deadline)
    solver.pop()
    if checked is None or checked == z3.unknown:return dict(receipt, reason='completion check unknown: ' + str(reason))
    receipt['reference_completion_possible'] = checked == z3.sat
    mismatch = z3.Or(*(left_outputs[name] != right_outputs[name] for name in contract['outputs']))
    solver.add(z3.Or(left_complete != right_complete, z3.And(left_complete, right_complete, mismatch)))
    checked, reason = _check(solver, deadline)
    receipt.update(method='bounded-scalar-z3', solver='Z3 ' + z3.get_version_string())
    if checked is None or checked == z3.unknown:return dict(receipt, reason='equivalence check unknown: ' + str(reason))
    if checked == z3.unsat:
        if not receipt['reference_completion_possible']:receipt['proof_scope'] = 'refusal-only: both supplied models atomically refuse every input in the nonempty admitted domain; no working computation established'
        return dict(receipt, status='equivalent_under_contract')
    model = solver.model()
    values = {name: z3.is_true(model.eval(symbol, model_completion=True)) if contract['inputs'][name] == 'bool' else model.eval(symbol, model_completion=True).as_long() for name, symbol in inputs.items()}
    observed_left, observed_right = _concrete(left, left_ports, values), _concrete(right, right_ports, values)
    if observed_left['complete'] == observed_right['complete'] and (not observed_left['complete'] or observed_left['outputs'] == observed_right['outputs']):
        return dict(receipt, reason='symbolic counterexample did not reproduce in the shared-IL interpreter', inputs=values)
    return dict(receipt, status='counterexample', inputs=values, reference=observed_left, implementation=observed_right)
