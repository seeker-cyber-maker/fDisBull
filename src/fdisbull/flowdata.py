"""Architecture-independent, bounded forward propagation of normalized IR.

This is an abstract interpreter over instruction facts, not an input-code
executor. Joins discard conflicting values. Stack storage is symbolic and a
caller-provided memory reader is an immutable-snapshot oracle, never execution.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import json

_OPS = {'add', 'sub', 'mul', 'shl', 'and'}
_INVERSE = {'eq': 'ne', 'ne': 'eq', 'lt_u': 'ge_u', 'le_u': 'gt_u',
            'gt_u': 'le_u', 'ge_u': 'lt_u', 'lt_s': 'ge_s', 'le_s': 'gt_s',
            'gt_s': 'le_s', 'ge_s': 'lt_s'}


def _const(value):
    return {'op': 'const', 'value': int(value)}


def _identity(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _unknown(expr):
    return not isinstance(expr, dict) or expr.get('op') == 'unknown'


def _number(expr, state, depth=0):
    if depth > 32 or not isinstance(expr, dict):
        return None
    if expr.get('op') == 'const':
        return expr.get('value')
    if expr.get('op') == 'stack' and expr.get('base') == 'entry_sp':
        initial = state.get('initial_stack_pointer')
        if isinstance(initial, int) and not isinstance(initial, bool):
            return initial + expr.get('offset', 0)
        if isinstance(initial, dict) and initial.get('op') == 'const':
            return initial['value'] + expr.get('offset', 0)
    if expr.get('op') in _OPS and len(expr.get('args', [])) == 2:
        a, b = (_number(v, state, depth+1) for v in expr['args'])
        if a is not None and b is not None:
            value = _simplify(expr['op'], _const(a), _const(b))
            return value.get('value') if value.get('op') == 'const' else None
    return None


def _memory_key(address, width):
    if not isinstance(width, int) or not 0 < width <= 4096 or not isinstance(address, dict):
        return None
    if address.get('op') == 'stack':
        return f"{address.get('base', 'entry_sp')}:{address.get('offset', 0):+d}:{width}"
    if address.get('op') == 'const':
        return f"absolute:{address['value']:+d}:{width}"
    return None


def _reader_allowed(address, width, state):
    if state.get('memory_tainted'):
        return False
    for write in state.get('memory_writes', []):
        prior = write['address']
        # Stack objects and the caller's static mapped-memory oracle are distinct
        # abstract spaces unless an initial concrete SP establishes an alias.
        start = _number(prior, state)
        if start is None and prior.get('op') == 'stack':
            continue
        if start is None or not isinstance(write.get('width'), int):
            return False
        if start < address + width and address < start + write['width']:
            return False
    return True


# Shared by indirect recovery so snapshot-read policy has one authority.
memory_read_allowed = _reader_allowed


def _canonical_history(state, writes):
    """Canonical finite may-write set; taint is an absorbing top element."""
    if state.get('memory_tainted'):
        state['memory_writes'] = []
        return
    unique = {_identity(write): write for write in writes}
    if len(unique) > 128:
        state['memory_tainted'] = True
        state['memory_writes'] = []
    else:
        state['memory_writes'] = [unique[key] for key in sorted(unique)]


def _simplify(op, left, right):
    if left.get('op') == right.get('op') == 'const':
        a, b = left['value'], right['value']
        if op == 'shl' and not 0 <= b <= 127:
            return {'op': 'unknown', 'reason': 'unbounded shift'}
        value = {'add': lambda: a+b, 'sub': lambda: a-b, 'mul': lambda: a*b,
                 'shl': lambda: a << b, 'and': lambda: a & b}[op]()
        if value.bit_length() > 256:
            return {'op': 'unknown', 'reason': 'expression integer budget'}
        return _const(value)
    if op in ('add', 'sub') and left.get('op') == 'stack' and right.get('op') == 'const':
        return dict(left, offset=left.get('offset', 0) + right['value'] * (1 if op == 'add' else -1))
    if op == 'add' and right.get('op') == 'stack' and left.get('op') == 'const':
        return dict(right, offset=right.get('offset', 0) + left['value'])
    if op == 'sub' and left.get('op') == right.get('op') == 'stack' and left.get('base') == right.get('base'):
        return _const(left.get('offset', 0)-right.get('offset', 0))
    if right == _const(0) and op in ('add', 'sub', 'shl'):
        return left
    if left == _const(0) and op == 'add':
        return right
    if op == 'mul' and (left == _const(0) or right == _const(0)):
        return _const(0)
    if op == 'mul' and right == _const(1):
        return left
    return {'op': op, 'args': [left, right]}


def evaluate_expression(expr, state, read_memory=None):
    """Substitute known values, preserving unresolved register/load expressions.

    Frozen ``symbol`` fields distinguish old unknown values from a later value
    of the same register. ``read_memory(address, width)`` may return exact bytes
    or an integer from the caller's immutable snapshot. Without it loads remain
    symbolic, except for values already established in abstract stack storage.
    """
    registers = state.get('registers', state) if isinstance(state, dict) else {}

    def visit(value, active, depth):
        if depth > 32 or not isinstance(value, dict):
            return {'op': 'unknown', 'reason': 'malformed/deep expression'}
        op = value.get('op')
        if op in ('const', 'unknown', 'stack'):
            return deepcopy(value)
        if op == 'reg':
            name = value.get('name')
            if value.get('symbol') is not None:
                return deepcopy(value)
            if name in registers and name not in active:
                return visit(registers[name], active | {name}, depth+1)
            return dict(value, symbol=state.get('symbols', {}).get(name, f'entry:{name}'))
        if op in _OPS:
            args = value.get('args', [])
            if len(args) != 2:
                return {'op': 'unknown', 'reason': 'binary expression requires two arguments'}
            return _simplify(op, visit(args[0], active, depth+1), visit(args[1], active, depth+1))
        if op == 'load':
            address = visit(value.get('address'), active, depth+1)
            width = value.get('width')
            logical = visit(value['stack_address'], active, depth+1) if value.get('stack_address') is not None else address
            key = _memory_key(logical, width)
            stored = state.get('memory', {}).get(key)
            if stored is not None:
                resolved = visit(stored, active, depth+1)
            else:
                resolved = None
                number = _number(address, state)
                if read_memory is not None and number is not None and isinstance(width, int) and 0 < width <= 64 and number >= 0 and _reader_allowed(number, width, state):
                    try:
                        data = read_memory(number, width)
                    except (ValueError, IndexError, KeyError, OSError):
                        data = None
                    if isinstance(data, (bytes, bytearray)) and len(data) == width:
                        resolved = _const(int.from_bytes(data, 'little', signed=bool(value.get('signed'))))
                    elif isinstance(data, int) and not isinstance(data, bool):
                        number = data & ((1 << (width*8))-1)
                        if value.get('signed') and number & (1 << (width*8-1)):
                            number -= 1 << (width*8)
                        resolved = _const(number)
            if resolved is not None:
                if value.get('signed') and resolved.get('op') == 'const' and isinstance(width, int):
                    number = resolved['value'] & ((1 << (width*8))-1)
                    return _const(number-(1 << (width*8)) if number & (1 << (width*8-1)) else number)
                return resolved
            return dict(value, address=address, **({'stack_address': logical} if value.get('stack_address') is not None else {}))
        return {'op': 'unknown', 'reason': f'unsupported expression operation {op}'}

    return visit(expr, set(), 0)


evaluate = evaluate_expression


def _state(initial, stack_register):
    initial = deepcopy(initial or {})
    state = initial if 'registers' in initial else {'registers': initial}
    state.setdefault('memory', {})
    state.setdefault('bounds', {})
    state.setdefault('guards', [])
    state.setdefault('symbols', {})
    state.setdefault('comparison', None)
    state.setdefault('memory_writes', [])
    state.setdefault('memory_tainted', False)
    _canonical_history(state, state['memory_writes'])
    for name, value in list(state['registers'].items()):
        if isinstance(value, int) and not isinstance(value, bool):
            state['registers'][name] = _const(value)
        elif not isinstance(value, dict) or value.get('op') == 'unknown':
            del state['registers'][name]
    if stack_register:
        original = state['registers'].get(stack_register)
        symbol = {'op': 'stack', 'base': 'entry_sp', 'offset': 0}
        state['initial_stack_pointer'] = original['value'] if original and original.get('op') == 'const' else original
        state['stack_origin'] = {'register': stack_register, 'expression': symbol, 'initial': original}
        state['registers'][stack_register] = symbol
    return state


def _join(states, node, widened):
    if not states:
        return None
    result = deepcopy(states[0])
    _canonical_history(result, result.get('memory_writes', []))
    for other in states[1:]:
        result['memory_tainted'] = result.get('memory_tainted', False) or other.get('memory_tainted', False)
        _canonical_history(result, result.get('memory_writes', []) + other.get('memory_writes', []))
        for field in ('registers', 'memory'):
            result[field] = {key: value for key, value in result[field].items() if other[field].get(key) == value}
        if result.get('comparison') != other.get('comparison'):
            result['comparison'] = None
        common = {_identity(g) for g in other.get('guards', [])}
        result['guards'] = [g for g in result.get('guards', []) if _identity(g) in common]
        bounds = {}
        for name, bound in result['bounds'].items():
            b = other['bounds'].get(name)
            if b and all(b.get(k) == bound.get(k) for k in ('bits', 'signed', 'symbol', 'projection', 'projected')):
                evidence = {_identity(g) for g in b.get('evidence', [])}
                bounds[name] = dict(bound, min=min(bound['min'], b['min']), max=max(bound['max'], b['max']),
                                    evidence=[g for g in bound.get('evidence', []) if _identity(g) in evidence])
        result['bounds'] = bounds
    names = set().union(*(set(s.get('symbols', {})) | set(s['registers']) for s in states))
    result['symbols'] = {}
    for name in names:
        values = {s.get('symbols', {}).get(name, f'entry:{name}') for s in states}
        result['symbols'][name] = next(iter(values)) if len(values) == 1 else f'join:{node}:{name}'
    for name in widened:
        result['bounds'].pop(name, None)
    return result


def _store(state, address, width, value, physical=None):
    key = _memory_key(address, width)
    if key is None:
        state['memory'].clear()
        state['memory_tainted'] = True
        state['memory_writes'] = []
        return
    write = dict(address=physical if physical is not None else address, width=width)
    _canonical_history(state, state.get('memory_writes', []) + [write])
    # Remove every potentially overlapping prior slot. Unknown relative/absolute
    # aliasing is conservative when an entry stack address is unavailable.
    for old in list(state['memory']):
        base, offset, old_width = old.rsplit(':', 2)
        offset, old_width = int(offset), int(old_width)
        if address.get('op') == 'stack' and base == address.get('base'):
            overlaps = offset < address['offset']+width and address['offset'] < offset+old_width
        elif address.get('op') == 'const' and base == 'absolute':
            overlaps = offset < address['value']+width and address['value'] < offset+old_width
        else:
            overlaps = True
        if overlaps:
            del state['memory'][old]
    if value is not None and not _unknown(value) and len(state['memory']) < 128:
        if value.get('op') == 'const':
            value = _const(value['value'] & ((1 << (width*8))-1))
        state['memory'][key] = value


def _transfer(before, semantic, node, read_memory):
    after = deepcopy(before)
    if semantic.get('memory_reset'):
        after['memory'].clear()
        after['memory_writes'] = []
        after['memory_tainted'] = True
    clobbers = set(semantic.get('clobbers', []))
    assignments = semantic.get('assignments', [])
    for name in clobbers | {a['register'] for a in assignments}:
        after['registers'].pop(name, None)
        after['bounds'].pop(name, None)
        after['symbols'][name] = f'write:{node}:{name}'
        after['guards'] = [g for g in after['guards'] if g.get('register') != name]
    if semantic.get('flags_clobbered') or semantic.get('clobbers_flags'):
        after['comparison'] = None
    for memory in semantic.get('memory', []):
        if memory.get('access') in ('write', 'read_write', 'conditional_write', 'unknown') or memory.get('may_write'):
            repeat = memory.get('repeat')
            if repeat:
                count = repeat.get('count')
                if count is None and repeat.get('count_register'):
                    count = _number(evaluate_expression({'op': 'reg', 'name': repeat['count_register']}, before), before)
                if count == 0:
                    continue
                # A repeated element descriptor is not a proof that only its
                # first slot is touched. Bulk value/range transfer is unsupported.
                after['memory'].clear()
                after['memory_tainted'] = True
                after['memory_writes'] = []
                continue
            address = evaluate_expression(memory.get('stack_address', memory.get('address')), before)
            physical = evaluate_expression(memory.get('address'), before)
            value = evaluate_expression(memory['value'], before, read_memory) if memory.get('value') is not None else None
            # A conditional store cannot establish one definite new value.
            if memory.get('access') == 'conditional_write':
                value = None
            _store(after, address, memory.get('width'), value, physical)
    for assignment in assignments:
        value = evaluate_expression(assignment.get('value'), before, read_memory)
        bits = assignment.get('bits')
        if value.get('op') == 'const' and isinstance(bits, int) and 0 < bits <= 128:
            value = _const(value['value'] & ((1 << bits)-1))
        if not _unknown(value):
            after['registers'][assignment['register']] = value
    comparison = semantic.get('comparison')
    if comparison:
        after['comparison'] = dict(comparison,
            left=evaluate_expression(comparison['left'], before, read_memory),
            right=evaluate_expression(comparison['right'], before, read_memory), source=node)
    # Explicit SP assignments take precedence over the optional delta summary.
    sp = semantic.get('stack_pointer')
    if sp and sp not in {a['register'] for a in assignments}:
        delta = semantic.get('stack_delta')
        if isinstance(delta, int) and not isinstance(delta, bool) and sp in before['registers']:
            after['registers'][sp] = _simplify('add', before['registers'][sp], _const(delta))
        elif sp in clobbers:
            after['registers'].pop(sp, None)
    return after


def _guard(state, semantic, edge, source):
    condition = semantic.get('branch_condition')
    if not condition:
        return deepcopy(state), None
    taken = edge.get('taken')
    if taken is None:
        kind = edge.get('kind', '')
        taken = False if kind in ('fallthrough', 'not_taken', 'false') else True if kind in ('conditional', 'jump', 'branch', 'taken', 'true') else None
    if taken is None:
        return deepcopy(state), None
    comparison = state.get('comparison') if condition.get('source') == 'comparison' else condition
    if not comparison or comparison.get('left') is None or comparison.get('right') is None:
        return deepcopy(state), None
    left = evaluate_expression(comparison['left'], state)
    right = evaluate_expression(comparison['right'], state)
    predicate = condition.get('predicate')
    if predicate not in _INVERSE:
        return deepcopy(state), None
    predicate = predicate if taken else _INVERSE[predicate]
    bits = comparison.get('bits') or condition.get('bits') or 64
    if not isinstance(bits, int) or not 0 < bits <= 128:
        return deepcopy(state), None
    signed = predicate.endswith('_s')
    mask = (1 << bits)-1

    def number(v):
        n = v['value'] & mask
        return n-(1 << bits) if signed and n & (1 << (bits-1)) else n

    if left.get('op') == right.get('op') == 'const':
        a, b = number(left), number(right)
        feasible = {'eq': a == b, 'ne': a != b, 'lt': a < b, 'le': a <= b,
                    'gt': a > b, 'ge': a >= b}[predicate.split('_')[0]]
        return (deepcopy(state) if feasible else None), dict(source=source, predicate=predicate, taken=taken, feasible=feasible)
    if left.get('op') == 'const' and right.get('op') == 'reg':
        left, right = right, left
        predicate = {'lt_u':'gt_u', 'le_u':'ge_u', 'gt_u':'lt_u', 'ge_u':'le_u',
                     'lt_s':'gt_s', 'le_s':'ge_s', 'gt_s':'lt_s', 'ge_s':'le_s', 'eq':'eq', 'ne':'ne'}[predicate]
    projection = None
    if left.get('op') == 'and' and len(left.get('args', [])) == 2:
        a, b = left['args']
        if a.get('op') == 'reg' and b == _const(mask):
            projection, left = left, a
        elif b.get('op') == 'reg' and a == _const(mask):
            projection, left = left, b
    if left.get('op') != 'reg' or right.get('op') != 'const':
        return deepcopy(state), None
    name, symbol, bound = left['name'], left.get('symbol'), number(right)
    low, high = (-(1 << (bits-1)), (1 << (bits-1))-1) if signed else (0, mask)
    relation = predicate.split('_')[0]
    if relation == 'eq':
        low = high = bound
    elif relation == 'lt':
        high = min(high, bound-1)
    elif relation == 'le':
        high = min(high, bound)
    elif relation == 'gt':
        low = max(low, bound+1)
    elif relation == 'ge':
        low = max(low, bound)
    else:
        return deepcopy(state), None  # An interval cannot represent a hole.
    old = state['bounds'].get(name)
    if old and old.get('symbol') == symbol and old.get('bits') == bits and old.get('signed') == signed and old.get('projection') == projection:
        low, high = max(low, old['min']), min(high, old['max'])
    evidence = dict(source=source, predicate=predicate, taken=taken, register=name,
                    symbol=symbol, min=low, max=high, bits=bits, signed=signed,
                    projection=projection, projected=projection is not None)
    if low > high:
        return None, dict(evidence, feasible=False)
    result = deepcopy(state)
    guards = list(old.get('evidence', [])) if old and old.get('symbol') == symbol else []
    if evidence not in guards:
        guards.append(evidence)
    result['bounds'][name] = dict(min=low, max=high, bits=bits, signed=signed, symbol=symbol,
                                projection=projection, projected=projection is not None, evidence=guards)
    if evidence not in result['guards']:
        result['guards'].append(evidence)
    return result, evidence


def _call_effects(state, semantic, edge, abi, source):
    if semantic.get('flow') not in ('call', 'indirect_call'):
        return state
    # A call edge enters the callee before its effects. A continuation edge
    # represents an assumed completed call and applies the supplied ABI.
    if edge.get('kind') in ('call', 'indirect_call', 'callee'):
        return state
    state = deepcopy(state)
    if isinstance(semantic.get('call_abi'), dict):
        abi = semantic['call_abi']
    sp = semantic.get('stack_pointer')
    clobbers = abi.get('caller_clobbers', abi.get('clobbers')) if abi is not None else None
    if clobbers is None:
        clobbers = [name for name in state['registers'] if name != sp]
    for name in clobbers:
        state['registers'].pop(name, None)
        state['bounds'].pop(name, None)
        state['symbols'][name] = f'call:{source}:{name}'
    state['comparison'] = None
    state['guards'] = [g for g in state['guards'] if g.get('register') not in clobbers]
    if not abi or not abi.get('preserve_stack', False):
        state['memory'].clear()
    if not abi or not abi.get('memory_readonly', False):
        state['memory_tainted'] = True
        state['memory_writes'] = []
    adjustment = (abi or {}).get('stack_delta')
    explicit_adjustment = isinstance(adjustment, int) and not isinstance(adjustment, bool)
    if adjustment is None:
        adjustment = semantic.get('call_return_size', semantic.get('return_address_size'))
    if adjustment is None:
        adjustment = (abi or {}).get('return_width')
    cleanup = (abi or {}).get('callee_cleanup')
    known_cleanup = isinstance(cleanup, int) and not isinstance(cleanup, bool) and cleanup >= 0
    if sp and sp in state['registers']:
        if explicit_adjustment:
            state['registers'][sp] = _simplify('add', state['registers'][sp], _const(adjustment))
        elif known_cleanup and isinstance(adjustment, int) and not isinstance(adjustment, bool):
            state['registers'][sp] = _simplify('add', state['registers'][sp], _const(adjustment + cleanup))
        else:
            state['registers'].pop(sp, None)
    return state


def analyze_flow(nodes, edges, entry_id, semantics_by_id, initial=None, read_memory=None,
                 abi=None, max_steps=100000):
    """Compute a conservative fixed point over normalized instruction semantics.

    Nodes may be ids, ``{'id': ...}`` records, or a mapping keyed by id. Edges
    require ``source``/``target`` and may include ``kind`` and ``taken``. Unknown
    or unsupported effects stay symbolic or kill facts; a budget stop is never
    reported stable. Branch evidence is intersected at joins, so a guard from
    only one incoming path cannot justify a later jump-table bound.
    """
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 1000000:
        raise ValueError('max_steps must be an integer in 1..1000000')
    if abi is not None and not isinstance(abi, dict):
        raise ValueError('abi must be a dictionary')
    ids = list(nodes) if isinstance(nodes, dict) else [n['id'] if isinstance(n, dict) else n for n in nodes]
    if len(ids) != len(set(ids)) or entry_id not in ids or len(ids) > 250000:
        raise ValueError('nodes must have unique ids, contain entry_id, and fit the node budget')
    ids_set = set(ids)
    outgoing = {node: [] for node in ids}
    normalized = []
    unresolved = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or 'source' not in edge or 'target' not in edge:
            raise ValueError('edges require source and target')
        if edge['source'] not in ids_set or edge['target'] not in ids_set:
            unresolved.append(dict(kind='external_edge', source=edge['source'], target=edge['target']))
            continue
        normalized.append(dict(edge, _index=index))
        outgoing[edge['source']].append(normalized[-1])
    if len(normalized) > 1000000:
        raise ValueError('edge budget exceeded')
    entry = _state(initial, semantics_by_id.get(entry_id, {}).get('stack_pointer'))
    contributions = {node: {} for node in ids}
    contributions[entry_id][-1] = entry
    in_states, out_states, edge_states = {entry_id: entry}, {}, {}
    queue, queued = deque([entry_id]), {entry_id}
    changes, widened, steps = {node: 0 for node in ids}, {node: set() for node in ids}, 0
    while queue and steps < max_steps:
        node = queue.popleft()
        queued.remove(node)
        steps += 1
        before = in_states.get(node)
        if before is None:
            continue
        semantic = semantics_by_id.get(node)
        if semantic is None:
            unresolved.append(dict(kind='missing_semantics', source=node))
            continue
        after = _transfer(before, semantic, node, read_memory)
        out_states[node] = (_call_effects(after, semantic, {'kind': 'fallthrough'}, abi, node)
                            if semantic.get('flow') in ('call', 'indirect_call') and
                            not any(e.get('kind') in ('call', 'indirect_call', 'callee') for e in outgoing[node])
                            else after)
        for edge in outgoing[node]:
            propagated, evidence = _guard(after, semantic, edge, node)
            if propagated is not None:
                propagated = _call_effects(propagated, semantic, edge, abi, node)
            index, target = edge['_index'], edge['target']
            edge_states[index] = dict(source=node, target=target, kind=edge.get('kind'), taken=edge.get('taken'),
                                      feasible=propagated is not None, state=deepcopy(propagated), guard=evidence)
            if propagated is None:
                contributions[target].pop(index, None)
            else:
                contributions[target][index] = propagated
            joined = _join(list(contributions[target].values()), target, widened[target])
            old = in_states.get(target)
            if joined != old:
                changes[target] += 1
                if changes[target] > 8 and old and joined:
                    varying = {name for name in old['bounds'] if old['bounds'].get(name) != joined['bounds'].get(name)}
                    widened[target].update(varying)
                    for name in widened[target]:
                        joined['bounds'].pop(name, None)
                if joined is None:
                    in_states.pop(target, None)
                else:
                    in_states[target] = joined
                if target not in queued:
                    queue.append(target)
                    queued.add(target)
    budget = bool(queue)
    if budget:
        unresolved.append(dict(kind='budget_exhausted', pending=len(queue)))
    if read_memory is not None:
        unresolved.append(dict(kind='immutable_memory_assumption', detail='Memory reader supplies immutable snapshot bytes; runtime mutation is outside this model.'))
        unresolved.append(dict(kind='symbolic_stack_assumption', detail='Symbolic stack objects are separate from mapped snapshot data unless an initial concrete stack pointer establishes an address alias.'))
    cleanup = (abi or {}).get('callee_cleanup')
    if not (type((abi or {}).get('stack_delta')) is int or type(cleanup) is int and cleanup >= 0):
        for node in out_states:
            if semantics_by_id.get(node, {}).get('flow') in ('call', 'indirect_call'):
                unresolved.append(dict(kind='unknown_call_stack_cleanup', source=node,
                                       detail='A returned call has no established callee stack-cleanup contract.'))
    # De-duplicate diagnostics from loop reprocessing.
    diagnostics = {_identity(item): item for item in unresolved}
    return dict(in_states=in_states, out_states=out_states, edge_states=[edge_states[k] for k in sorted(edge_states)],
                steps=steps, stable=not budget, budget_exhausted=budget, unresolved=list(diagnostics.values()),
                entry_id=entry_id, reached_nodes=len(in_states), widened={node: sorted(names) for node, names in widened.items() if names})
