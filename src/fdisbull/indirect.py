"""Architecture-independent, read-only indirect-transfer recovery from native IR.

No memory is scanned looking for pointers. An indexed load is expanded only
over a finite state or an interval justified by a guard retained by the flow
solver. Results remain candidates until the caller validates native decoding.
"""
from __future__ import annotations

import re
import string

_BINARY = {'add', 'sub', 'mul', 'shl', 'and'}


class _Invalid(Exception):
    def __init__(self, reason, **detail):
        self.reason, self.detail = reason, detail
        super().__init__(reason)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate(expr, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if depth > 48 or count[0] > 1024 or not isinstance(expr, dict):
        raise _Invalid('malformed_or_excessive_expression')
    op = expr.get('op')
    if not isinstance(op, str):
        raise _Invalid('malformed_expression_operation')
    if op == 'const':
        if not _integer(expr.get('value')) or expr['value'].bit_length() > 128:
            raise _Invalid('invalid_constant')
    elif op == 'reg':
        if not isinstance(expr.get('name'), str) or not expr['name'] or len(expr['name']) > 256:
            raise _Invalid('invalid_register')
        if expr.get('symbol') is not None and not isinstance(expr['symbol'], str):
            raise _Invalid('invalid_register_symbol')
    elif op == 'load':
        if not _integer(expr.get('width')) or expr['width'] not in (1, 2, 4, 8):
            raise _Invalid('invalid_load_width')
        if not isinstance(expr.get('signed', False), bool):
            raise _Invalid('invalid_load_signedness')
        _validate(expr.get('address'), depth + 1, count)
    elif op in _BINARY:
        if not isinstance(expr.get('args'), (list, tuple)) or len(expr['args']) != 2:
            raise _Invalid('invalid_binary_expression')
        for arg in expr['args']:
            _validate(arg, depth + 1, count)
    elif op != 'unknown':
        raise _Invalid('unsupported_expression', operation=op)


def _variables(expr):
    if expr['op'] == 'reg':
        return {(expr['name'], expr.get('symbol'))}
    if expr['op'] == 'load':
        return _variables(expr['address'])
    if expr['op'] in _BINARY:
        return set().union(*(_variables(arg) for arg in expr['args']))
    return set()


def _load_variables(expr):
    if expr['op'] == 'load':
        return _variables(expr['address'])
    if expr['op'] in _BINARY:
        return set().union(*(_load_variables(arg) for arg in expr['args']))
    return set()


def _has_load(expr):
    return expr['op'] == 'load' or (expr['op'] in _BINARY and any(_has_load(arg) for arg in expr['args']))


def _same_symbol(name, symbol, record, register=None):
    other = record.get('symbol')
    if symbol is not None or other is not None:
        return symbol is not None and symbol == other
    return name == (register if register is not None else record.get('register'))


def _covered_by_projection(expression, variable, projection, covered=False):
    covered = covered or expression == projection
    if expression['op'] == 'reg':
        return (expression['name'], expression.get('symbol')) != variable or covered
    children = [expression['address']] if expression['op'] == 'load' else expression.get('args', [])
    return all(_covered_by_projection(child, variable, projection, covered) for child in children)


def _domain(variable, state, expression):
    name, symbol = variable
    bounds, guards = state.get('bounds', {}), state.get('guards', [])
    if not isinstance(bounds, dict) or not isinstance(guards, list):
        raise _Invalid('malformed_index_bounds', register=name)
    matches = [(register, bound) for register, bound in bounds.items() if isinstance(bound, dict)
               and _same_symbol(name, symbol, bound, register)]
    for register, bound in matches:
        if bound.get('projected'):
            projection = bound.get('projection')
            if not isinstance(projection, dict) or not _covered_by_projection(expression, variable, projection):
                continue
        low, high, bits, signed = (bound.get(key) for key in ('min', 'max', 'bits', 'signed'))
        if not all(_integer(value) for value in (low, high, bits)) or not 1 <= bits <= 64 or not isinstance(signed, bool):
            raise _Invalid('malformed_index_bounds', register=name)
        minimum, maximum = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
        if low > high or low < minimum or high > maximum:
            raise _Invalid('malformed_index_bounds', register=name)
        dominating = [guard for guard in guards if isinstance(guard, dict) and guard.get('source')
                      and guard.get('predicate') and guard.get('dominates', True)
                      and _same_symbol(name, symbol, guard)]
        if dominating:
            return range(low, high + 1), dict(kind='dominating_guard_interval', register=register,
                    symbol=symbol, min=low, max=high, bits=bits, signed=signed, guards=dominating,
                    evidence=bound.get('evidence', []), projected=bound.get('projected', False),
                    projection=bound.get('projection'))
    raise _Invalid('unbounded_or_nondominating_index', register=name, symbol=symbol)


def _evaluate(expr, bindings, read_memory, cache, loads):
    op = expr['op']
    if op == 'const':
        return expr['value']
    if op == 'reg':
        identity = (expr['name'], expr.get('symbol'))
        if identity not in bindings:
            raise _Invalid('unknown_register_value', register=expr['name'])
        return bindings[identity]
    if op == 'unknown':
        raise _Invalid('unknown_target_expression', explanation=expr.get('reason'))
    if op == 'load':
        address = _evaluate(expr['address'], bindings, read_memory, cache, loads)
        width = expr['width']
        if not 0 <= address < 1 << 64 or address + width > 1 << 64:
            raise _Invalid('entry_address_outside_supported_range', address=address, width=width)
        identity = (address, width)
        if identity not in cache:
            try:
                data = read_memory(address, width)
            except (ValueError, OverflowError, OSError) as exc:
                raise _Invalid('entry_read_failed', address=address, width=width, error=str(exc)) from exc
            if data is None:
                raise _Invalid('unmapped_table_entry', address=address, width=width)
            if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) != width:
                raise _Invalid('truncated_or_invalid_table_entry', address=address, width=width,
                               available=len(data) if isinstance(data, (bytes, bytearray, memoryview)) else None)
            cache[identity] = bytes(data)
        value = int.from_bytes(cache[identity], 'little', signed=expr.get('signed', False))
        record = dict(address=address, width=width, signed=expr.get('signed', False), value=value)
        if record not in loads:
            loads.append(record)
        return value
    left, right = (_evaluate(arg, bindings, read_memory, cache, loads) for arg in expr['args'])
    if op == 'add':
        result = left + right
    elif op == 'sub':
        result = left - right
    elif op == 'mul':
        result = left * right
    elif op == 'and':
        result = left & right
    else:
        if not 0 <= right <= 63:
            raise _Invalid('invalid_shift_count', count=right)
        result = left << right
    if result.bit_length() > 128:
        raise _Invalid('excessive_arithmetic_value')
    return result


def _context(template, bindings, read_memory, cache, loads):
    if template is None or isinstance(template, str):
        if template is not None and len(template) > 256:
            raise _Invalid('invalid_target_context')
        return template
    if not isinstance(template, dict) or not isinstance(template.get('template'), str) or len(template['template']) > 256 or not isinstance(template.get('values'), dict):
        raise _Invalid('invalid_target_context')
    values = {}
    for name, expression in template['values'].items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
            raise _Invalid('invalid_target_context')
        _validate(expression)
        values[name] = _evaluate(expression, bindings, read_memory, cache, loads)
    try:
        for _, field, specification, conversion in string.Formatter().parse(template['template']):
            if field is not None and (field not in values or conversion or not re.fullmatch(r'(?:0?[1-9][0-9]?)?[dxX]?', specification)):
                raise _Invalid('invalid_target_context')
        result = template['template'].format(**values)
    except (KeyError, ValueError) as exc:
        raise _Invalid('invalid_target_context') from exc
    if len(result) > 256:
        raise _Invalid('invalid_target_context')
    return result


def _slot(loads):
    if not loads:
        return None, None
    ordered = sorted({(load['address'], load['width']) for load in loads})
    end = ordered[0][0]
    for address, width in ordered:
        if address != end:
            return ordered[0][0], None
        end = address + width
    return ordered[0][0], end - ordered[0][0]


def _combinations(domains, count):
    """Enumerate a capped Cartesian prefix without materializing large ranges."""
    for ordinal in range(count):
        values = []
        for domain in reversed(domains):
            ordinal, digit = divmod(ordinal, domain.stop - domain.start)
            values.append(domain.start + digit)
        yield tuple(reversed(values))


def recover_indirect(snapshot, semantics_by_id, flow_result, read_memory, is_executable, *, max_entries=256):
    """Propose indirect targets without decoding, queuing work or writing facts.

    Callbacks use canonical physical addresses. ``read_memory(a, width)`` must
    return exactly width bytes or None; ``is_executable(a)`` checks the mapped
    execution policy. Every candidate still requires caller-owned native decoder
    validation. max_entries is a global budget for table-entry evaluations.
    Normalized IR currently defines little-endian loads; container names and
    instruction mnemonics are never inspected here.
    """
    from .flowdata import evaluate_expression, memory_read_allowed
    if not _integer(max_entries) or not 1 <= max_entries <= 65536:
        raise ValueError('max_entries must be an integer in 1..65536')
    if not callable(read_memory) or not callable(is_executable):
        raise ValueError('read_memory and is_executable must be callable')
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('nodes'), list) or not isinstance(semantics_by_id, dict) or not isinstance(flow_result, dict):
        raise ValueError('snapshot, semantics_by_id and flow_result must contain normalized graph data')
    states = flow_result.get('in_states', {})
    if not isinstance(states, dict):
        raise ValueError('flow_result.in_states must be a mapping')
    candidates, rejections, proposals = [], [], []
    examined = reads = targets = skipped = 0
    flow_incomplete = bool(flow_result.get('budget_exhausted')) or flow_result.get('stable') is False
    graph_incomplete = bool(snapshot.get('budget_exhausted'))
    partial = flow_incomplete or graph_incomplete
    for node in snapshot['nodes']:
        if not isinstance(node, dict) or node.get('flow') not in ('indirect_call', 'indirect_jump'):
            continue
        source = node.get('id')
        semantics = semantics_by_id.get(source, {})
        state = states.get(source)
        identity = dict(source=source, source_address=node.get('address'), source_context=node.get('context'), flow=node['flow'])
        if flow_incomplete or graph_incomplete:
            proposals.append(dict(identity, reason='incomplete_dataflow' if flow_incomplete else 'incomplete_cfg_budget'))
            continue
        if not isinstance(state, dict):
            proposals.append(dict(identity, reason='no_reachable_incoming_state'))
            continue
        if any(not isinstance(state.get(field, {}), dict) for field in ('registers', 'memory', 'bounds')) or not isinstance(state.get('guards', []), list):
            proposals.append(dict(identity, reason='malformed_incoming_state'))
            continue
        if not isinstance(semantics, dict) or semantics.get('indirect_target') is None:
            proposals.append(dict(identity, reason='no_normalized_indirect_target'))
            continue

        def snapshot_reader(address, width):
            # The solver owns memory-alias conservatism. Its unresolved loads
            # must not regain an old file value merely because recovery later
            # instantiates a bounded index.
            if not memory_read_allowed(address, width, state):
                raise _Invalid('snapshot_memory_may_be_modified', address=address, width=width)
            return read_memory(address, width)
        try:
            expression = semantics['indirect_target']
            _validate(expression)
            expression = evaluate_expression(expression, state)
            _validate(expression)
            variables = sorted(_variables(expression), key=lambda item: (item[0], item[1] or ''))
            if set(variables) - _load_variables(expression):
                raise _Invalid('unknown_nonindex_target_value')
            domains, bounds = [], []
            for variable in variables:
                domain, evidence = _domain(variable, state, expression)
                domains.append(domain)
                bounds.append(evidence)
            template = semantics.get('target_context')
            if isinstance(template, dict) and isinstance(template.get('values'), dict):
                template = dict(template, values={key: evaluate_expression(value, state) for key, value in template['values'].items()})
            constraints = semantics.get('target_constraints', [])
            if not isinstance(constraints, list) or len(constraints) > 32:
                raise _Invalid('malformed_target_constraints')
            normalized_constraints = []
            for constraint in constraints:
                if not isinstance(constraint, dict) or not all(_integer(constraint.get(key)) for key in ('min', 'max')) or constraint['min'] > constraint['max']:
                    raise _Invalid('malformed_target_constraints')
                _validate(constraint.get('expression'))
                checked = evaluate_expression(constraint['expression'], state)
                _validate(checked)
                normalized_constraints.append(dict(expression=checked, min=constraint['min'], max=constraint['max']))
        except _Invalid as exc:
            proposals.append(dict(identity, reason=exc.reason, **exc.detail))
            continue
        cardinality = 1
        for domain in domains:
            cardinality *= domain.stop - domain.start
        table = _has_load(expression) or any(_has_load(item['expression']) for item in normalized_constraints)
        count = min(cardinality, max_entries - examined) if table else cardinality
        if count < cardinality:
            partial = True
            skipped += cardinality - count
        for values in _combinations(domains, count):
            if table:
                examined += 1
            targets += 1
            bindings = dict(zip(variables, values))
            index = [dict(register=name, symbol=symbol, value=bindings[(name, symbol)]) for name, symbol in variables]
            cache, loads = {}, []
            try:
                target = _evaluate(expression, bindings, snapshot_reader, cache, loads)
                target_context = _context(template, bindings, snapshot_reader, cache, loads)
                checked_constraints = []
                for constraint in normalized_constraints:
                    value = _evaluate(constraint['expression'], bindings, snapshot_reader, cache, loads)
                    if not constraint['min'] <= value <= constraint['max']:
                        raise _Invalid('target_constraint_failed', value=value, minimum=constraint['min'], maximum=constraint['max'])
                    checked_constraints.append(dict(constraint, value=value))
                if not 0 <= target < 1 << 64:
                    raise _Invalid('out_of_range_target', target=target)
                if not is_executable(target):
                    raise _Invalid('target_not_executable', target=target)
                slot, width = _slot(loads)
                candidates.append(dict(identity, target=target, target_address=f'0x{target:x}', target_context=target_context,
                    table_slot=slot, entry_width=width, index=index, bound_evidence=bounds or [dict(kind='finite_constant_state' if not loads else 'fixed_slot')],
                    loads=loads, expression=expression, target_constraints=checked_constraints, status='candidate', requires_decoder_validation=True,
                    evidence='normalized indirect target evaluated under reachable incoming state and bounded index evidence',
                    assumptions=['Static snapshot memory values; runtime writes are not modeled.',
                                 'Caller must validate native target decoding and context before admission.']))
            except _Invalid as exc:
                rejections.append(dict(identity, index=index, reason=exc.reason, **exc.detail))
            finally:
                reads += len(cache)
    return dict(candidates=candidates, rejections=rejections, proposals=proposals,
                budget=dict(max_entries=max_entries, entries_examined=examined, memory_reads=reads,
                            targets_examined=targets, skipped_entries=skipped, partial=partial,
                            flow_incomplete=flow_incomplete, graph_incomplete=graph_incomplete, scope='all_transfers'),
                note='Candidates are static evidence, not proven runtime targets. No unbounded memory scan or database mutation was performed.')
