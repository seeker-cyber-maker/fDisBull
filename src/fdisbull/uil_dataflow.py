"""Recoverable scalar value numbering for physical copy elimination.

This is a lowering plan, not a rewrite of UIL. Every original charged statement
retains its position. Immutable value IDs let a native emitter omit register
copies without confusing a later overwrite of the source slot with that copy.
Control/array/effect boundaries deliberately keep the ordinary lowering.
"""
from copy import deepcopy

from .common_uil import digest, validate_function


def scalar_value_plan(function):
    """Return an owned straight-line plan, or None for a different shape.

    All final slots are retained, including flag slots. Aliasing is between
    immutable values; no storage alias or pointer authority is introduced.
    Entry frames and imported frames therefore have the same logical state.
    """
    validate_function(function)
    admitted = {'bool', 'resource'} | {s + str(w) for s in 'ui' for w in (8, 16, 32, 64)}
    if any(d['type'] not in admitted for d in function['variables'] + function['constants']):
        return None
    flat = []

    def flatten(nodes, path=()):
        for i, node in enumerate(nodes):
            at = [*path, i]
            if node['op'] == 'group':
                if not flatten(node['body'], (*at, 'body')):
                    return False
            elif node['op'] in ('set', 'require', 'return'):
                flat.append((at, node))
                if len(flat) > 4096:
                    return False
            else:
                return False
        return True

    if not flatten(function['body']):
        return None
    values = list(range(len(function['variables'])))
    initial = list(values)
    value_types = deepcopy(function['variables'])
    next_value = len(values)
    body, eliminated = [], []

    def expression(value):
        if set(value) == {'var'}:
            return {'ssa': values[value['var']]}
        if set(value) == {'const'}:
            return deepcopy(value)
        return {'op': value['op'], 'type': value['type'],
                'args': [expression(v) for v in value['args']]}

    for path, node in flat:
        op = node['op']
        item = {'op': op, 'path': path, 'charge': 1}
        if op == 'set':
            dst = node['dst']
            if set(node['value']) == {'var'}:
                src = node['value']['var']
                values[dst] = values[src]
                item.update(op='alias', dst=dst, source=src, value=values[dst])
                eliminated.append({'path': deepcopy(path), 'dst': dst, 'source': src,
                                   'value': values[dst], 'charge_retained': 1})
            else:
                expr = expression(node['value'])
                values[dst] = next_value
                item.update(op='define', dst=dst, value=next_value, expression=expr)
                value_types.append(deepcopy(function['variables'][dst]))
                next_value += 1
        elif op == 'require':
            item['condition'] = expression(node['condition'])
        body.append(item)
        if op == 'return':
            break
    return {'format': 'fdisbull-uil-scalar-value-plan-1',
            'function_sha256': digest(function), 'initial_values': initial,
            'body': body, 'final_values': values, 'value_count': next_value,
            'value_types': value_types,
            'eliminated_copies': eliminated,
            'accounting': 'one charge retained for every reached non-group UIL statement',
            'observation': 'all logical slots retained; no flags, memory or budget behavior discarded'}
