"""Finite-path recovery of a returning PE64 leaf under an explicit call frame.

The instruction, guard and byte-memory semantics are the regional model's.
Coverage and every feasible cross-path intersection are proved separately.
"""
from copy import deepcopy
import time

from .behavior_diff import _site
from .pe_path_transfer import _qualified_trace
from .pe_region_equivalence import _contract, _digest, _execute, _snapshots


SCOPE = ('Whole returning PE64 leaf for the supplied stable code epochs and explicit '
         'call-frame/private-RAM contract; concurrent code changes, calls, traps, '
         'devices, timing and external effects remain outside the model')


def _family(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
        raise ValueError('A function family requires 1..8 bounded paths')
    entry, exit_site, runtime_entry, runtime_exit, source = None, None, None, None, None
    code = {}
    for path in paths:
        if not isinstance(path, dict) or set(path) != {'trace', 'memory'}:
            raise ValueError('Function paths require exact trace and entry/exit memory evidence')
        trace = path['trace']
        if _qualified_trace(trace) != 64 or trace.get('complete') is not True or len(trace['events']) > 257:
            raise ValueError('A function requires complete PE64 paths of at most 256 instructions')
        first, last = trace['events'][0], trace['events'][-1]
        identity = tuple(trace['mapping'][k] for k in ('source_sha256', 'version_sha256'))
        if entry is None:
            entry, exit_site = _site(first), _site(last)
            runtime_entry, runtime_exit = first['address'], last['address']
            source = identity
        if (entry != _site(first) or exit_site != _site(last) or source != identity
                or runtime_entry != first['address'] or runtime_exit != last['address']):
            raise ValueError('Function paths require common source, entry and caller boundary')
        for event in trace['events']:
            raw = bytes.fromhex(event.get('execution_bytes', event.get('bytes', '')))
            if not 1 <= len(raw) <= 15:
                raise ValueError('Function paths need exact bounded instruction bytes')
            address = int(event['address'], 16)
            for offset, byte in enumerate(raw):
                if address + offset in code and code[address + offset] != byte:
                    raise ValueError('A function family contains inconsistent code epochs')
                code[address + offset] = byte
    return entry, exit_site, runtime_entry, runtime_exit, source, code


def compare_pe_functions(baseline, layer, *, contract, timeout_ms=5000):
    """Recover/compare both entire finite path families, without guessing paths."""
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    base = {'format': 'fdisbull-pe-function-recovery-1', 'status': 'unknown',
            'scope': SCOPE, 'semantic_equivalence': None, 'contraction': None,
            'counterexample': None, 'coverage': {}}
    try:
        normalized, addresses, names = _contract(contract, 64)
        families = [_family(p) for p in (baseline, layer)]
        if families[0][:5] != families[1][:5]:
            raise ValueError('Compared functions require common source, entry and caller boundary')
        if any(address in family[5] for address in addresses for family in families):
            raise ValueError('Declared memory overlaps captured code')
        if normalized['memory_observation'] != 'ordered':
            raise ValueError('Whole-function recovery requires ordered memory observation')
        if 'rsp' not in normalized['entry_registers']:
            raise ValueError('Whole-function recovery requires an explicit fixed entry RSP')
        snapshots = [[_snapshots(p['memory'], addresses) for p in paths] for paths in (baseline, layer)]
    except (ValueError, TypeError, KeyError) as error:
        return base | {'reason': str(error)}
    try:
        import z3 as z
    except ImportError:
        return base | {'reason': 'Optional z3 proof dependency is unavailable'}
    deadline = time.monotonic() + timeout_ms / 1000
    initial = {n: z.BitVec('entry_' + n, 64) for n in names}
    flags = z.BitVec('entry_flags', 32)
    memory = {a: z.BitVec(f'entry_ram_{a:x}', 8) for a in addresses}
    assumptions = [initial[n] == int(v, 16) for n, v in normalized['entry_registers'].items()]
    substitutions = [(initial[n], z.BitVecVal(int(v, 16), 64)) for n, v in normalized['entry_registers'].items()]
    for n, bounds in normalized['entry_register_ranges'].items():
        assumptions += [z.UGE(initial[n], int(bounds['min'], 16)), z.ULE(initial[n], int(bounds['max'], 16))]
    for row in normalized['entry_memory']:
        address = int(row['address'], 16)
        for offset, byte in enumerate(bytes.fromhex(row['hex'])):
            assumptions.append(memory[address + offset] == byte)
            substitutions.append((memory[address + offset], z.BitVecVal(byte, 8)))
    assumptions.append((flags & 2) == 2)
    solver = z.Solver()

    def query(claim):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise ValueError('Whole-function proof deadline exhausted')
        solver.set(timeout=remaining)
        solver.push()
        solver.add(*assumptions, claim)
        outcome = solver.check()
        model = solver.model() if outcome == z.sat else None
        reason = solver.reason_unknown() if outcome == z.unknown else None
        solver.pop()
        if outcome == z.unknown:
            raise ValueError('Whole-function solver unknown: ' + str(reason))
        return outcome, model

    def inputs(model):
        value = lambda expression: hex(model.eval(expression, model_completion=True).as_long())
        return {'entry_general': {n: value(v) for n, v in initial.items()},
                'entry_flags': value(flags), 'entry_memory': {hex(a): value(v) for a, v in memory.items()}}

    try:
        if query(z.BoolVal(True))[0] != z.sat:
            raise ValueError('Infeasible whole-function entry contract')
        stack = int(normalized['entry_registers']['rsp'], 16)
        target = int(families[0][3], 16)
        if stack + 8 > 1 << 64 or any(stack + k not in memory for k in range(8)):
            raise ValueError('Declared RAM must include the complete entry return word')
        return_word = z.Concat(*[memory[stack + k] for k in reversed(range(8))])
        if query(return_word != target)[0] != z.unsat:
            raise ValueError('The entry return word must explicitly establish the observed caller boundary')
        modeled = []
        for side, paths, sampled in zip(('baseline', 'layer'), (baseline, layer), snapshots, strict=True):
            group = []
            for index, (path, sample) in enumerate(zip(paths, sampled, strict=True)):
                item = _execute(z, path['trace'], 64, initial, flags, memory,
                                normalized, sample, side + str(index), deadline)
                returns = item['returns']
                if (len(returns) != 1 or returns[0]['width'] != 8
                        or returns[0]['event_index'] != len(path['trace']['events']) - 2):
                    raise ValueError('Each function path must end with exactly one completed near RET')
                for access in item['safety']:
                    outcome, model = query(z.And(access['prefix'], z.Not(access['valid'])))
                    if outcome == z.sat:
                        return base | {'reason': 'Function memory access may escape declared RAM',
                                       'safety_counterexample': inputs(model) | {'side': side, 'path': index}}
                if query(item['domain'])[0] != z.sat:
                    raise ValueError('A supplied function path is infeasible under its entry contract')
                obligation = z.Or(returns[0]['stack_address'] != initial['rsp'],
                                  item['registers']['rsp'] != initial['rsp'] + 8)
                if query(z.And(item['domain'], obligation))[0] != z.unsat:
                    raise ValueError('RET does not restore the declared caller stack frame')
                group.append(item)
            modeled.append(group)
            outcome, model = query(z.Not(z.Or(*[p['domain'] for p in group])))
            base['coverage'][side] = {'status': 'complete' if outcome == z.unsat else 'incomplete',
                'paths': len(group), 'counterexample': inputs(model) if model is not None else None}
            if outcome == z.sat:
                return base | {'status': 'incomplete_path_coverage',
                               'reason': 'Supplied paths do not cover the admitted function inputs'}

        presentation = {'remaining': 65536}
        def expression(value):
            text = z.simplify(z.substitute(value, *substitutions)).sexpr()
            if len(text) > 4096 or len(text) > presentation['remaining']:
                raise ValueError('Whole-function effect presentation budget exhausted')
            presentation['remaining'] -= len(text)
            return text

        def recover(group, paths):
            return {'call_frame': {'entry_stack': hex(stack), 'return_target': hex(target),
                                  'stack_pointer_delta': 8},
                    'termination_bound_instructions': max(len(p['trace']['events']) - 1 for p in paths),
                    'cases': [{'guard': expression(p['domain']),
                               'registers': {n: expression(p['registers'][n]) for n in normalized['live_registers']},
                               'flags': expression(p['flags'] & normalized['live_flags']),
                               'memory_bytes': {hex(a): expression(p['memory'][a]) for a in addresses},
                               'ordered_accesses': [{'kind': kind, 'address': expression(address), 'width': width,
                                                     'value': expression(value)} for kind, address, width, value in p['accesses']]}
                              for p in group]}
        base.update(contract=normalized, solver={'name': 'z3', 'version': z.get_version_string(), 'timeout_ms_total': timeout_ms},
                    baseline_recovery=recover(modeled[0], baseline), layer_recovery=recover(modeled[1], layer))
        pairs = 0
        for i, a in enumerate(modeled[0]):
            for j, b in enumerate(modeled[1]):
                domain = z.And(a['domain'], b['domain'])
                if query(domain)[0] == z.unsat:
                    continue
                pairs += 1
                differences = [a['registers'][n] != b['registers'][n] for n in normalized['live_registers']]
                differences += [(a['flags'] & normalized['live_flags']) != (b['flags'] & normalized['live_flags'])]
                differences += [a['memory'][address] != b['memory'][address] for address in addresses]
                if len(a['accesses']) != len(b['accesses']):
                    differences.append(z.BoolVal(True))
                for x, y in zip(a['accesses'], b['accesses']):
                    differences.append(z.BoolVal(True) if x[0] != y[0] or x[2] != y[2]
                                       else z.Or(x[1] != y[1], x[3] != y[3]))
                outcome, model = query(z.And(domain, z.Or(*differences)))
                if outcome == z.sat:
                    value = lambda v: hex(model.eval(v, model_completion=True).as_long())
                    witness = inputs(model) | {'baseline_path': i, 'layer_path': j,
                        'differing_live_registers': {n: {'baseline': value(a['registers'][n]), 'layer': value(b['registers'][n])}
                            for n in normalized['live_registers'] if value(a['registers'][n]) != value(b['registers'][n])},
                        'differing_memory_bytes': {hex(address): {'baseline': value(a['memory'][address]),
                            'layer': value(b['memory'][address])} for address in addresses
                            if value(a['memory'][address]) != value(b['memory'][address])},
                        'masked_flags': {'baseline': value(a['flags'] & normalized['live_flags']),
                                         'layer': value(b['flags'] & normalized['live_flags'])},
                        'memory_access_counts': {'baseline': len(a['accesses']), 'layer': len(b['accesses'])},
                        'validation': 'Symbolic whole-function witness; independent CPU replay required'}
                    return base | {'status': 'different', 'counterexample': witness, 'feasible_path_pairs_checked': pairs}
        contraction = {'format': 'fdisbull-pe-function-contraction-1', 'contract': normalized,
            'sources': {'baseline': _digest(baseline), 'layer': _digest(layer)},
            'coverage': base['coverage'], 'baseline_recovery': base['baseline_recovery'],
            'layer_recovery': base['layer_recovery'], 'feasible_path_pairs_checked': pairs,
            'scope': SCOPE, 'proof': 'Complete feasible path cover and unsatisfiable effect difference on every intersection'}
        contraction['sha256'] = _digest(contraction)
        return base | {'status': 'equivalent_under_contract', 'contraction': contraction,
                       'feasible_path_pairs_checked': pairs}
    except (ValueError, TypeError, KeyError) as error:
        return base | {'reason': str(error)}


def expand_pe_function_contraction(contraction, baseline, layer):
    """Re-expand exact path and memory evidence; digests are not proof signatures."""
    if (not isinstance(contraction, dict) or contraction.get('format') != 'fdisbull-pe-function-contraction-1'
            or contraction.get('sha256') != _digest({k: v for k, v in contraction.items() if k != 'sha256'})
            or contraction.get('sources') != {'baseline': _digest(baseline), 'layer': _digest(layer)}):
        raise ValueError('Function contraction requires its exact original path/memory evidence')
    return {'baseline': deepcopy(baseline), 'layer': deepcopy(layer)}
