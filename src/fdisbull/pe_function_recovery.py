"""Finite-path recovery of returning PE64 code under an explicit call frame.

The instruction, guard and byte-memory semantics are the regional model's.
Coverage and every feasible cross-path intersection are proved separately.
Stable leaves remain the default. Direct internal calls and synchronous code
stores require an explicit opt-in and a complete immutable code-image timeline.
"""
from copy import deepcopy
import time

from .behavior_diff import _site
from .pe_path_transfer import _qualified_trace
from .pe_region_equivalence import _contract, _digest, _execute, _snapshots


SCOPE = ('Whole returning PE64 leaf for the supplied stable code epochs and explicit '
         'call-frame/private-RAM contract; concurrent code changes, calls, traps, '
         'devices, timing and external effects remain outside the model')
CALL_SMC_SCOPE = ('Whole returning single-threaded PE64 function with bounded direct internal calls '
                  'and synchronous instruction stores under the explicit call-frame/private-RAM/code-image '
                  'contract; concurrent mutation, indirect or external calls, traps, devices, timing '
                  'and external effects remain outside the model')


def _code_image(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError('A code image requires 1..32 exact byte ranges')
    cells = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'address', 'hex'}
                or not isinstance(row['address'], str) or not row['address'].startswith('0x')
                or not isinstance(row['hex'], str) or not 2 <= len(row['hex']) <= 1024
                or len(row['hex']) % 2):
            raise ValueError('Code images require bounded exact address/hex rows')
        address, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
        if address < 0 or address + len(raw) > 1 << 64:
            raise ValueError('Code image exceeds the PE64 address space')
        for offset, byte in enumerate(raw):
            if address + offset in cells:
                raise ValueError('Code image ranges overlap')
            cells[address + offset] = byte
    if len(cells) > 512:
        raise ValueError('Code images exceed 512 bytes')
    return cells


def _code_document(document):
    if not isinstance(document, dict) or set(document) != {'entry', 'exit', 'versions'}:
        raise ValueError('Dynamic recovery requires exact entry/exit code and every code version')
    entry, exit_code = _code_image(document['entry']), _code_image(document['exit'])
    if set(entry) != set(exit_code):
        raise ValueError('Entry and exit code images must cover the same addresses')
    versions = document['versions']
    if not isinstance(versions, list) or not 1 <= len(versions) <= 257:
        raise ValueError('Code versions require the initial image and every writing instruction')
    timeline = []
    for row in versions:
        if (not isinstance(row, dict) or set(row) != {'after_event', 'image'}
                or type(row['after_event']) is not int or not 0 <= row['after_event'] <= 256):
            raise ValueError('Code version rows require an exact completed-event count and image')
        image = _code_image(row['image'])
        if set(image) != set(entry) or (timeline and row['after_event'] <= timeline[-1]['after_event']):
            raise ValueError('Code versions require increasing event counts and the complete image')
        timeline.append({'after_event': row['after_event'], 'bytes': {hex(a): b for a, b in sorted(image.items())}})
    if timeline[0]['after_event'] != 0 or timeline[0]['bytes'] != {hex(a): b for a, b in sorted(entry.items())}:
        raise ValueError('The first code version must preserve the exact entry image')
    if timeline[-1]['bytes'] != {hex(a): b for a, b in sorted(exit_code.items())}:
        raise ValueError('The last code version must preserve the exact exit image')
    return entry, exit_code, timeline


def _family(paths, *, dynamic=False):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
        raise ValueError('A function family requires 1..8 bounded paths')
    entry, exit_site, runtime_entry, runtime_exit, source = None, None, None, None, None
    code = {}
    for path in paths:
        allowed = {'trace', 'memory', 'code', 'code_versions'} if dynamic else {'trace', 'memory'}
        required = {'trace', 'memory', 'code'} if dynamic else allowed
        if not isinstance(path, dict) or set(path) - allowed or not required <= set(path):
            raise ValueError('Function paths require exact trace and entry/exit memory evidence')
        trace = path['trace']
        entry_code = _code_document(path['code'])[0] if dynamic else None
        if dynamic:
            if code and entry_code != code:
                raise ValueError('A dynamic function family requires one common entry code image')
            code = entry_code
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
                if dynamic:
                    if address + offset not in code:
                        raise ValueError('Instruction fetch outside the complete code image')
                    continue
                if address + offset in code and code[address + offset] != byte:
                    raise ValueError('A function family contains inconsistent code epochs')
                code[address + offset] = byte
    return entry, exit_site, runtime_entry, runtime_exit, source, code


def compare_pe_functions(baseline, layer, *, contract, timeout_ms=5000, execution_mode='stable_leaf'):
    """Recover both finite path covers, including opt-in internal calls/code stores.

    In dynamic mode code bytes, fetches and LIFO call frames are obligations
    proved under preceding guards, never assumptions that can narrow coverage.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    if execution_mode not in ('stable_leaf', 'single_threaded_calls_smc'):
        raise ValueError('Unknown function execution mode')
    dynamic = execution_mode == 'single_threaded_calls_smc'
    base = {'format': 'fdisbull-pe-function-recovery-1', 'status': 'unknown',
            'scope': CALL_SMC_SCOPE if dynamic else SCOPE, 'execution_mode': execution_mode,
            'semantic_equivalence': None, 'contraction': None,
            'counterexample': None, 'coverage': {}}
    try:
        normalized, addresses, names = _contract(contract, 64)
        families = [_family(p, dynamic=dynamic) for p in (baseline, layer)]
        if families[0][:5] != families[1][:5]:
            raise ValueError('Compared functions require common source, entry and caller boundary')
        if any(address in family[5] for address in addresses for family in families):
            raise ValueError('Declared memory overlaps captured code')
        if dynamic and set(families[0][5]) != set(families[1][5]):
            raise ValueError('Compared dynamic functions require the same code image addresses')
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
                code_entry, code_exit, timeline = _code_document(path['code']) if dynamic else ({}, {}, [])
                path_memory = memory | {a: z.BitVecVal(byte, 8) for a, byte in code_entry.items()}
                path_sample = (sample[0] | code_entry, sample[1] | code_exit)
                item = _execute(z, path['trace'], 64, initial, flags, path_memory,
                                normalized, path_sample, side + str(index), deadline,
                                execution_code=code_entry if dynamic else None)
                returns = item['returns']
                if (len(returns) != (len(item['calls']) + 1 if dynamic else 1)
                        or returns[-1]['width'] != 8
                        or returns[-1]['event_index'] != len(path['trace']['events']) - 2):
                    raise ValueError('Each function path must finish with a balanced completed near RET')
                if dynamic:
                    generated = [{'after_event': 0 if row['after_event_index'] is None else row['after_event_index'] + 1,
                                  'bytes': row['bytes']} for row in item['code_versions']]
                    if timeline != generated:
                        raise ValueError('Code version evidence omits or contradicts a modeled writing instruction')
                    for obligation in item['proof_obligations']:
                        outcome, model = query(z.And(obligation['prefix'], z.Not(obligation['valid'])))
                        if outcome != z.unsat:
                            return base | {'reason': 'Dynamic execution obligation is not proved: ' + obligation['kind'],
                                'execution_counterexample': inputs(model) | {'side': side, 'path': index,
                                    'event_index': obligation['event_index'], 'kind': obligation['kind']}}
                for access in item['safety']:
                    outcome, model = query(z.And(access['prefix'], z.Not(access['valid'])))
                    if outcome == z.sat:
                        return base | {'reason': 'Function memory access may escape declared RAM',
                                       'safety_counterexample': inputs(model) | {'side': side, 'path': index}}
                if query(item['domain'])[0] != z.sat:
                    raise ValueError('A supplied function path is infeasible under its entry contract')
                obligation = z.Or(returns[-1]['stack_address'] != initial['rsp'],
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
                                                     'value': expression(value)} for kind, address, width, value in p['accesses']],
                               **({'code_bytes': {hex(a): expression(p['memory'][a]) for a in sorted(families[0][5])},
                                   'internal_calls': [{'event_index': c['event_index'], 'target': hex(c['target']),
                                      'return_address': hex(c['return_address']), 'stack_address': expression(c['stack_address']),
                                      'depth': c['depth']} for c in p['calls']],
                                   'return_events': [{'event_index': r['event_index'], 'target': expression(r['target']),
                                      'stack_address': expression(r['stack_address']), 'width': r['width'],
                                      'remaining_call_depth': r['call_depth']} for r in p['returns']],
                                   'code_writes': [{'event_index': w['event_index'], 'address': expression(w['address']),
                                      'width': w['width'], 'value': expression(w['value'])} for w in p['code_writes']],
                                   'code_versions': p['code_versions'], 'instruction_fetches_checked': p['fetch_checks'],
                                   'execution_obligations_checked': len(p['proof_obligations'])} if dynamic else {})}
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
                if dynamic:
                    differences += [a['memory'][address] != b['memory'][address] for address in families[0][5]]
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
                        **({'differing_code_bytes': {hex(address): {'baseline': value(a['memory'][address]),
                                'layer': value(b['memory'][address])} for address in families[0][5]
                                if value(a['memory'][address]) != value(b['memory'][address])}} if dynamic else {}),
                        'masked_flags': {'baseline': value(a['flags'] & normalized['live_flags']),
                                         'layer': value(b['flags'] & normalized['live_flags'])},
                        'memory_access_counts': {'baseline': len(a['accesses']), 'layer': len(b['accesses'])},
                        'validation': 'Symbolic whole-function witness; independent CPU replay required'}
                    return base | {'status': 'different', 'counterexample': witness, 'feasible_path_pairs_checked': pairs}
        contraction = {'format': 'fdisbull-pe-function-contraction-1', 'contract': normalized,
            'sources': {'baseline': _digest(baseline), 'layer': _digest(layer)},
            'coverage': base['coverage'], 'baseline_recovery': base['baseline_recovery'],
            'layer_recovery': base['layer_recovery'], 'feasible_path_pairs_checked': pairs,
            'scope': base['scope'], 'execution_mode': execution_mode,
            'proof': 'Complete feasible path cover and unsatisfiable effect difference on every intersection'}
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
