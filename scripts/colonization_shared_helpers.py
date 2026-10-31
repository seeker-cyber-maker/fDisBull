"""Authored shared Colonization helper definitions in existing fdisbull-il-1.
Physical addresses and source selectors belong in separate UDL bindings.
"""
from copy import deepcopy
from pathlib import Path
import json


def v(name): return {'var': '$' + name}
def decl(t='i16', initial=0): return {'type': t, 'initial': initial}
def bit(name, n): return {'op': 'bit_test', 'value': v(name), 'bit': n}
def neg(c): return {'op': 'not', 'condition': c}
def both(*conds): return {'op': 'and', 'conditions': list(conds)}
def either(a, b): return neg(both(neg(a), neg(b)))
def eq(a, b): return {'op': 'eq', 'left': a, 'right': b}
def stmt(ident, op, name, value): return {'id': ident, 'op': op, 'var': '$' + name, 'value': value}
def choose(ident, condition, yes, no=()):
    return {'id': ident, 'op': 'if', 'condition': condition, 'then': list(yes), 'else': list(no)}


def signed_less(left, right, difference):
    # difference is wrap_i16(left - right), computed before this condition.
    ls, rs = bit(left, 15), bit(right, 15)
    same = either(both(ls, rs), both(neg(ls), neg(rs)))
    return either(both(ls, neg(rs)), both(same, bit(difference, 15)))


def balance_uil():
    variables = {x: decl() for x in (
        '$supply', '$demand', '$available', '$consumed', '$shortage', '$unmet',
        '$supply_minus_demand', '$available_total', '$total_minus_demand')}
    body = [
        stmt('consume', 'set', 'consumed', v('demand')),
        stmt('clear_shortage', 'set', 'shortage', 0),
        stmt('clear_unmet', 'set', 'unmet', 0),
        stmt('start_supply_comparison', 'set', 'supply_minus_demand', v('supply')),
        stmt('supply_comparison', 'subtract', 'supply_minus_demand', v('demand')),
        choose('demand_exceeds_supply', signed_less('supply', 'demand', 'supply_minus_demand'), [
            stmt('shortage_start', 'set', 'shortage', v('demand')),
            stmt('shortage_subtract', 'subtract', 'shortage', v('supply'))]),
        stmt('availability_start', 'set', 'available_total', v('supply')),
        stmt('availability_wrap', 'add', 'available_total', v('available')),
        stmt('start_total_comparison', 'set', 'total_minus_demand', v('available_total')),
        stmt('total_comparison', 'subtract', 'total_minus_demand', v('demand')),
        choose('demand_exceeds_total', signed_less('available_total', 'demand', 'total_minus_demand'), [
            stmt('unmet_start', 'set', 'unmet', v('demand')),
            stmt('unmet_subtract', 'subtract', 'unmet', v('available_total'))])]
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables, 'resources': {}, 'body': body}


def net_uil():
    variables = {x: decl() for x in (
        '$produced', '$consumed', '$mapped_adjustment', '$net', '$reported_adjustment')}
    variables.update({
        '$has_mapped_adjustment': decl('bool', False),
        '$has_report_target': decl('bool', False),
        '$report_written': decl('bool', False)})
    body = [
        stmt('no_report_yet', 'set', 'report_written', False),
        stmt('net_start', 'set', 'net', v('produced')),
        stmt('subtract_consumption', 'subtract', 'net', v('consumed')),
        choose('has_mapped_adjustment', eq(v('has_mapped_adjustment'), True), [
            stmt('subtract_adjustment', 'subtract', 'net', v('mapped_adjustment')),
            choose('has_optional_report_target', eq(v('has_report_target'), True), [
                stmt('write_optional_report', 'set', 'reported_adjustment', v('mapped_adjustment')),
                stmt('mark_report', 'set', 'report_written', True)])])]
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables, 'resources': {}, 'body': body}


def initial_state(document, **inputs):
    state = {k: value['initial'] for k, value in document['variables'].items()}
    for key, value in inputs.items():
        if '$' + key not in state:
            raise ValueError('undeclared input: ' + key)
        state['$' + key] = value
    return state


def write_documents(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, doc in [('input_balance', balance_uil()), ('net_production', net_uil())]:
        (directory / f'{name}.uil.json').write_text(json.dumps(doc, indent=2) + '\n')
        udl = deepcopy(doc)
        udl['role'] = 'udl'
        (directory / f'{name}.udl.json').write_text(json.dumps(udl, indent=2) + '\n')
    # Role documents do not execute native bytes by themselves: bindings/executor are explicit.


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory for authored definitions')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output directory already exists')
    write_documents(args.output)
