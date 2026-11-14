"""Bounded PE-entry recovery with explicit, observable imported-call contracts.

This proves the authored module under declared API/loader boundary contracts.
It does not prove Windows, Wine, the loader or an imported implementation.
"""
from copy import deepcopy
import time

from capstone import x86_const as X

from .behavior_diff import _site
from .pe_function_recovery import _code_document, _code_image
from .pe_path_transfer import _qualified_trace, _state
from .pe_region_equivalence import _contract, _digest, _execute, _snapshots


_APIS = {'SetLastError', 'GetLastError', 'ExitProcess'}
_VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
SCOPE = ('Bounded single-threaded PE entry through ExitProcess under explicit observed '
         'post-loader initialization and imported-call contracts; imported implementation, '
         'loader, TLS/CLR, library-private memory, other threads, devices and timing are not proved')


def _rows(cells):
    rows = []
    for address, byte in sorted(cells.items()):
        if rows and int(rows[-1]['address'], 16) + len(rows[-1]['hex']) // 2 == address:
            rows[-1]['hex'] += f'{byte:02x}'
        else:
            rows.append({'address': hex(address), 'hex': f'{byte:02x}'})
    return rows


def _module_contract(contract, initialization):
    if not isinstance(contract, dict):
        raise ValueError('A module contract is required')
    machine = {k: v for k, v in contract.items() if k != 'external_stack_ranges'}
    normalized, addresses, names = _contract(machine, 64)
    if normalized['memory_observation'] != 'ordered' or 'rsp' not in normalized['entry_registers']:
        raise ValueError('Modules require ordered memory and an explicit entry RSP')
    if (not isinstance(initialization, dict) or set(initialization) != {
            'stage', 'source_sha256', 'entry_address', 'image_base', 'memory',
            'tls_callbacks', 'clr', 'imports'}
            or initialization['stage'] != 'pe-entry-after-loader'
            or initialization['tls_callbacks'] != [] or initialization['clr'] is not False):
        raise ValueError('Exact post-loader PE initialization with absent TLS/CLR is required')
    for key in ('entry_address', 'image_base'):
        if (not isinstance(initialization[key], str) or not initialization[key].startswith('0x')
                or not 0 <= int(initialization[key], 16) < 1 << 64):
            raise ValueError('Initialization requires PE64 addresses')
    if int(initialization['entry_address'], 16) < int(initialization['image_base'], 16):
        raise ValueError('PE entry precedes its declared loaded image base')
    loaded = _code_image(initialization['memory'])
    if not set(loaded) <= set(addresses):
        raise ValueError('Initialized PE data and IAT must be in declared RAM')
    fixed = {int(row['address'], 16) + k: byte for row in normalized['entry_memory']
             for k, byte in enumerate(bytes.fromhex(row['hex']))}
    if any(a in fixed and fixed[a] != b for a, b in loaded.items()):
        raise ValueError('Initialization contradicts explicit entry RAM')
    machine['entry_memory'] = _rows(fixed | loaded)
    normalized, addresses, names = _contract(machine, 64)
    stack_rows = contract.get('external_stack_ranges')
    if not isinstance(stack_rows, list) or not 1 <= len(stack_rows) <= 32:
        raise ValueError('Explicit external stack scratch ranges are required')
    scratch = set()
    for row in stack_rows:
        if (not isinstance(row, dict) or set(row) != {'address', 'length'}
                or not isinstance(row['address'], str) or not row['address'].startswith('0x')
                or type(row['length']) is not int or not 1 <= row['length'] <= 256):
            raise ValueError('External stack scratch ranges require bounded address/length rows')
        start = int(row['address'], 16)
        cells = set(range(start, start + row['length']))
        if not cells <= set(addresses) or cells & scratch or cells & set(loaded):
            raise ValueError('External stack scratch must be disjoint declared uninitialized RAM')
        scratch |= cells
    imports = initialization['imports']
    if not isinstance(imports, list) or not 1 <= len(imports) <= 8:
        raise ValueError('An exact bounded import table is required')
    bound = {}
    iat_cells = set()
    for row in imports:
        if (not isinstance(row, dict) or set(row) != {'name', 'iat_address', 'target'}
                or row['name'] not in _APIS or row['name'] in bound):
            raise ValueError('Only unique SetLastError/GetLastError/ExitProcess imports are modeled')
        address, target = int(row['iat_address'], 16), int(row['target'], 16)
        if not 0 <= address <= (1 << 64) - 8 or not 0 <= target < 1 << 64:
            raise ValueError('Malformed import addresses')
        if any(address + k not in loaded for k in range(8)):
            raise ValueError('Every resolved IAT word must have initialized byte evidence')
        if iat_cells & set(range(address, address + 8)):
            raise ValueError('Declared import IAT words overlap')
        iat_cells.update(range(address, address + 8))
        if int.from_bytes(bytes(loaded[address + k] for k in range(8)), 'little') != target:
            raise ValueError('Resolved IAT bytes contradict the declared import target')
        bound[row['name']] = {'iat_address': address, 'target': target}
    if 'ExitProcess' not in bound:
        raise ValueError('A module requires its explicit ExitProcess import')
    return normalized, addresses, names, sorted(scratch), bound


def _family(paths, initialization):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
        raise ValueError('Module recovery requires 1..8 complete paths')
    common, code = None, None
    for path in paths:
        if (not isinstance(path, dict) or set(path) - {
                'trace', 'memory', 'code', 'code_versions', 'external_calls', 'terminal'}
                or not {'trace', 'memory', 'code', 'external_calls', 'terminal'} <= set(path)):
            raise ValueError('Module paths need exact trace, RAM, code, external calls and terminal evidence')
        trace = path['trace']
        if _qualified_trace(trace, allow_external_boundary=True) != 64 or trace.get('complete') is not True or len(trace['events']) > 257:
            raise ValueError('A module requires complete PE64 paths of at most 256 modeled instructions')
        entry, _, _ = _code_document(path['code'])
        identity = (trace['mapping']['source_sha256'], trace['mapping']['version_sha256'],
                    _site(trace['events'][0]), trace['events'][0]['address'])
        if (identity[0] != initialization['source_sha256']
                or int(identity[3], 16) != int(initialization['entry_address'], 16)):
            raise ValueError('Module trace does not begin at its source-bound PE entry')
        if common is not None and (common != identity or code != entry):
            raise ValueError('A module family requires one source, PE entry and entry code image')
        common, code = identity, entry
        for event in trace['events'][:-1]:
            raw = bytes.fromhex(event.get('execution_bytes', event.get('bytes', '')))
            address = int(event['address'], 16)
            if not 1 <= len(raw) <= 15 or any(address + k not in entry for k in range(len(raw))):
                raise ValueError('A module-owned instruction fetch escapes the declared image')
        if not isinstance(path['external_calls'], list) or not 1 <= len(path['external_calls']) <= 32:
            raise ValueError('Module paths require 1..32 observed external calls')
        if (not isinstance(path['terminal'], dict) or set(path['terminal']) != {'name', 'exit_code', 'process_exited'}
                or path['terminal']['name'] != 'ExitProcess' or path['terminal']['process_exited'] is not True
                or not isinstance(path['terminal']['exit_code'], str)
                or not 0 <= int(path['terminal']['exit_code'], 16) <= 0xffffffff):
            raise ValueError('An actual ExitProcess terminal receipt is required')
    return common, code


def compare_pe_modules(baseline, layer, *, contract, initialization, timeout_ms=10000):
    """Recover complete bounded PE-entry paths under explicit external contracts."""
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    base = {'format': 'fdisbull-pe-module-recovery-1', 'status': 'unknown', 'scope': SCOPE,
            'semantic_equivalence': None, 'contraction': None, 'coverage': {}, 'counterexample': None}
    try:
        normalized, addresses, names, scratch, imports = _module_contract(contract, initialization)
        families = [_family(paths, initialization) for paths in (baseline, layer)]
        if families[0][0] != families[1][0] or set(families[0][1]) != set(families[1][1]):
            raise ValueError('Compared modules require common source, entry and code addresses')
        if any(a in families[0][1] for a in addresses):
            raise ValueError('Module code and ordinary RAM overlap')
        if any(row['target'] in families[0][1] for row in imports.values()):
            raise ValueError('Declared imported API targets must be outside the authored code image')
        snapshots = [[_snapshots(p['memory'], addresses) for p in paths] for paths in (baseline, layer)]
        import z3 as z
    except (ValueError, TypeError, KeyError, ImportError) as error:
        return base | {'reason': str(error)}
    deadline = time.monotonic() + timeout_ms / 1000
    initial = {name: z.BitVec('entry_' + name, 64) for name in names}
    flags = z.BitVec('entry_flags', 32)
    memory = {a: z.BitVec(f'entry_ram_{a:x}', 8) for a in addresses}
    assumptions = [initial[n] == int(v, 16) for n, v in normalized['entry_registers'].items()]
    substitutions = [(initial[n], z.BitVecVal(int(v, 16), 64)) for n, v in normalized['entry_registers'].items()]
    for n, bounds in normalized['entry_register_ranges'].items():
        assumptions += [z.UGE(initial[n], int(bounds['min'], 16)), z.ULE(initial[n], int(bounds['max'], 16))]
    for row in normalized['entry_memory']:
        start = int(row['address'], 16)
        for k, byte in enumerate(bytes.fromhex(row['hex'])):
            assumptions.append(memory[start + k] == byte)
            substitutions.append((memory[start + k], z.BitVecVal(byte, 8)))
    assumptions.append((flags & 2) == 2)
    solver = z.Solver()
    def query(claim):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise ValueError('Module proof deadline exhausted')
        solver.set(timeout=remaining)
        solver.push()
        solver.add(*assumptions, claim)
        result = solver.check()
        model = solver.model() if result == z.sat else None
        reason = solver.reason_unknown() if result == z.unknown else None
        solver.pop()
        if result == z.unknown:
            raise ValueError('Module solver unknown: ' + str(reason))
        return result, model
    def inputs(model):
        val = lambda v: hex(model.eval(v, model_completion=True).as_long())
        return {'entry_general': {n: val(v) for n, v in initial.items()}, 'entry_flags': val(flags),
                'entry_memory': {hex(a): val(v) for a, v in memory.items()}}
    try:
        if query(z.BoolVal(True))[0] != z.sat:
            raise ValueError('Infeasible module entry contract')
        modeled = []
        for side, paths, samples in zip(('baseline', 'layer'), (baseline, layer), snapshots, strict=True):
            group = []
            for path_index, (path, sample) in enumerate(zip(paths, samples, strict=True)):
                code_entry, code_exit, timeline = _code_document(path['code'])
                calls = path['external_calls']
                by_index = {}
                for ordinal, call in enumerate(calls):
                    if (not isinstance(call, dict) or set(call) != {'event_index', 'name', 'iat_address', 'target',
                            'entry_registers', 'return_registers', 'memory', 'code'}
                            or type(call['event_index']) is not int or call['event_index'] in by_index
                            or call['name'] not in imports
                            or (ordinal and call['event_index'] <= calls[ordinal - 1]['event_index'])):
                        raise ValueError('External calls require exact increasing import-bound boundary records')
                    by_index[call['event_index']] = (ordinal, call)
                effects, used, symbols = [], [], {}
                state = {'last_error': z.BitVec('entry_last_error', 32), 'set': False, 'exit_code': None}
                def handler(index, event, following, ctx):
                    if index not in by_index:
                        raise ValueError('Unknown external call has no admitted contract')
                    ordinal, call = by_index[index]
                    used.append(index)
                    binding = imports[call['name']]
                    if (ctx['raw'][:2] != b'\xff\x15' or len(ctx['raw']) != 6
                            or len(ctx['instruction'].operands) != 1
                            or ctx['instruction'].operands[0].type != X.X86_OP_MEM
                            or ctx['instruction'].reg_name(ctx['instruction'].operands[0].mem.base) != 'rip'
                            or int(call['iat_address'], 16) != binding['iat_address']
                            or int(call['target'], 16) != binding['target']):
                        raise ValueError('External call must use its exact RIP-relative resolved IAT binding')
                    pointer, width = ctx['location'](ctx['instruction'].operands[0])
                    target = ctx['read_memory'](pointer, width)
                    ctx['obligations'].append({'kind': 'resolved_import', 'event_index': index,
                        'prefix': z.And(*ctx['domains']),
                        'valid': z.And(pointer == binding['iat_address'], target == binding['target'])})
                    regs = ctx['registers']
                    caller_stack = regs['rsp']
                    stack_address, _ = ctx['memory_location'](caller_stack - 8, 8)
                    sampled_stack = ctx['observed'](caller_stack)
                    if sampled_stack % 16 or any(sampled_stack + k not in scratch for k in range(32)):
                        raise ValueError('External calls require aligned RSP and 32 bytes of declared caller shadow store')
                    if any(ctx['observed'](stack_address) + k in scratch for k in range(8)):
                        raise ValueError('External scratch ranges overlap the architectural return word')
                    ctx['obligations'].append({'kind': 'external_call_frame', 'event_index': index,
                        'prefix': z.And(*ctx['domains']), 'valid': z.And((caller_stack & 15) == 0,
                            z.And(*[z.Or(*[caller_stack + k == a for a in scratch]) for k in range(32)]),
                            z.And(*[stack_address + k != a for k in range(8) for a in scratch]))})
                    ctx['write_memory'](stack_address, 8, z.BitVecVal(ctx['sequential'], 64))
                    entry = {'address': hex(binding['target']), 'registers': call['entry_registers']}
                    entry_regs, entry_flags, entry_thread = _state(entry, 64)
                    before_regs, _, before_thread = _state(event, 64)
                    if (entry_thread != before_thread or entry_flags != ctx['observed'](ctx['flags'])
                            or any(entry_regs[n] != (ctx['observed'](stack_address) if n == 'rsp'
                                  else ctx['observed'](regs[n])) for n in names)
                            or int(call['entry_registers']['rip'], 16) != binding['target']):
                        raise ValueError('Imported API entry registers contradict the architectural CALL')
                    api_memory = _snapshots({'entry': call['memory']['entry'],
                        'exit': call['memory']['entry'] if call['memory']['exit'] is None else call['memory']['exit']}, addresses)
                    if any(ctx['observed'](ctx['memory'][a]) != byte for a, byte in api_memory[0].items()):
                        raise ValueError('Imported API entry RAM contradicts the CALL frame')
                    if _code_image(call['code']['entry']) != {a: ctx['observed'](ctx['memory'][a]) for a in code_entry}:
                        raise ValueError('Imported API entry code image contradicts the current epoch')
                    arg = z.Extract(31, 0, regs['rcx']) if call['name'] != 'GetLastError' else None
                    effect = {'event_index': index, 'name': call['name'], 'iat_address': hex(binding['iat_address']),
                        'target': hex(binding['target']), 'argument': arg, 'return': None,
                        'memory_havoc': [], 'opaque_symbols': []}
                    effects.append(effect)
                    if call['name'] == 'ExitProcess':
                        if (ctx['call_stack'] or call['return_registers'] is not None
                                or call['memory']['exit'] is not None or call['code']['exit'] is not None
                                or following['registers'] != call['entry_registers']
                                or int(following['address'], 16) != binding['target']
                                or ctx['observed'](arg) != int(path['terminal']['exit_code'], 16)):
                            raise ValueError('ExitProcess requires matching nonreturning native exit evidence')
                        state['exit_code'] = arg
                        regs['rsp'] = stack_address
                        return {'flags': ctx['flags'], 'terminated': True}
                    if call['return_registers'] is None or following['registers'] != call['return_registers']:
                        raise ValueError('Returning API requires its exact caller-resume context')
                    if int(following['address'], 16) != ctx['sequential']:
                        raise ValueError('Returning API does not resume at the CALL fallthrough')
                    if _code_image(call['code']['exit']) != {a: ctx['observed'](ctx['memory'][a]) for a in code_entry}:
                        raise ValueError('An imported API changed the module code image')
                    if call['name'] == 'SetLastError':
                        state['last_error'], state['set'] = arg, True
                    elif not state['set']:
                        raise ValueError('This bounded contract requires SetLastError before GetLastError')
                    after_regs, after_flags, after_thread = _state(following, 64)
                    if after_thread != before_thread:
                        raise ValueError('An imported API changes the selected thread')
                    def fresh(label, bits, actual):
                        symbol = z.BitVec(f'external_{ordinal}_{label}', bits)
                        symbols[str(symbol)] = bits
                        effect['opaque_symbols'].append(str(symbol))
                        ctx['sample_substitutions'].append((symbol, z.BitVecVal(actual, bits)))
                        return symbol
                    for name in sorted(_VOLATILE):
                        regs[name] = fresh(name, 64, after_regs[name])
                    if call['name'] == 'GetLastError':
                        regs['rax'] = z.Concat(z.Extract(63, 32, regs['rax']), state['last_error'])
                        effect['return'] = state['last_error']
                    api_flags = fresh('flags', 32, after_flags) | 2
                    for a in scratch:
                        ctx['memory'][a] = fresh(f'ram_{a:x}', 8, api_memory[1][a])
                        effect['memory_havoc'].append(a)
                    if any(ctx['observed'](ctx['memory'][a]) != byte for a, byte in api_memory[1].items()):
                        raise ValueError('Imported API changed RAM outside declared stack scratch')
                    return {'flags': api_flags, 'terminated': False}
                item = _execute(z, path['trace'], 64, initial, flags,
                    memory | {a: z.BitVecVal(b, 8) for a, b in code_entry.items()}, normalized,
                    (sample[0] | code_entry, sample[1] | code_exit), side + str(path_index), deadline,
                    execution_code=code_entry, external_handler=handler)
                if not item['terminated'] or state['exit_code'] is None or used != list(by_index):
                    raise ValueError('Module path does not discharge every API boundary and terminate')
                generated = [{'after_event': 0 if row['after_event_index'] is None else row['after_event_index'] + 1,
                              'bytes': row['bytes']} for row in item['code_versions']]
                if generated != timeline:
                    raise ValueError('Module code version timeline omits or contradicts a writing instruction')
                for obligation in item['proof_obligations'] + item['safety']:
                    result, model = query(z.And(obligation['prefix'], z.Not(obligation['valid'])))
                    if result != z.unsat:
                        return base | {'reason': 'Module execution obligation is not proved: ' + obligation.get('kind', 'memory_safety'),
                            'execution_counterexample': inputs(model) | {'side': side, 'path': path_index,
                                'event_index': obligation['event_index']}}
                if query(item['domain'])[0] != z.sat:
                    raise ValueError('A module path is infeasible')
                item.update(external_effects=effects, external_symbols=symbols,
                            last_error=state['last_error'], exit_code=state['exit_code'])
                group.append(item)
            modeled.append(group)
            result, model = query(z.Not(z.Or(*[p['domain'] for p in group])))
            base['coverage'][side] = {'status': 'complete' if result == z.unsat else 'incomplete',
                'paths': len(group), 'counterexample': inputs(model) if model is not None else None}
            if result == z.sat:
                return base | {'status': 'incomplete_path_coverage', 'reason': 'Module paths do not cover the admitted entry state'}
        budget = {'remaining': 120000}
        def expression(value):
            text = z.simplify(z.substitute(value, *substitutions)).sexpr()
            if len(text) > 8192 or len(text) > budget['remaining']:
                raise ValueError('Module recovery presentation budget exhausted')
            budget['remaining'] -= len(text)
            return text
        def recover(group, paths):
            return {'termination_bound_instructions': max(len(p['trace']['events']) - 1 for p in paths),
                'cases': [{'guard': expression(p['domain']),
                    'registers': {n: expression(p['registers'][n]) for n in normalized['live_registers']},
                    'flags': expression(p['flags'] & normalized['live_flags']),
                    'memory_bytes': {hex(a): expression(p['memory'][a]) for a in addresses},
                    'code_bytes': {hex(a): expression(p['memory'][a]) for a in sorted(families[0][1])},
                    'ordered_accesses': [{'kind': k, 'address': expression(a), 'width': w, 'value': expression(v)}
                                         for k, a, w, v in p['accesses']],
                    'external_effects': [{**{k: v for k, v in e.items() if k not in ('argument', 'return')},
                        'argument': expression(e['argument']) if e['argument'] is not None else None,
                        'return': expression(e['return']) if e['return'] is not None else None} for e in p['external_effects']],
                    'external_symbols': p['external_symbols'], 'last_error': expression(p['last_error']),
                    'exit_code': expression(p['exit_code']), 'code_versions': p['code_versions'],
                    'internal_calls': [{'event_index': c['event_index'], 'target': hex(c['target']),
                        'return_address': hex(c['return_address']), 'depth': c['depth']} for c in p['calls']],
                    'instruction_fetches_checked': p['fetch_checks'],
                    'execution_obligations_checked': len(p['proof_obligations'])} for p in group]}
        base.update(contract=normalized | {'external_stack_ranges': deepcopy(contract['external_stack_ranges'])},
            initialization=deepcopy(initialization), baseline_recovery=recover(modeled[0], baseline),
            layer_recovery=recover(modeled[1], layer),
            external_contracts={'names': sorted(imports),
                'volatile_registers': sorted(_VOLATILE), 'flags': 'opaque architectural bit1-fixed choice',
                'scratch_memory': 'opaque unordered overwrite of each declared external stack byte',
                'GetLastError': 'Only low32 return bits defined; upper32 remain opaque',
                'other_memory': 'Declared no-pointer API contract, checked on native boundary snapshots; library-private effects unknown',
                'coupling': 'Corresponding API ordinal shares opaque environmental choices; not a proof of imported implementation'})
        pairs = 0
        for i, a in enumerate(modeled[0]):
            for j, b in enumerate(modeled[1]):
                domain = z.And(a['domain'], b['domain'])
                if query(domain)[0] == z.unsat:
                    continue
                pairs += 1
                differences = [a['registers'][n] != b['registers'][n] for n in normalized['live_registers']]
                differences += [(a['flags'] & normalized['live_flags']) != (b['flags'] & normalized['live_flags']),
                                a['last_error'] != b['last_error'], a['exit_code'] != b['exit_code']]
                differences += [a['memory'][p] != b['memory'][p] for p in [*addresses, *families[0][1]]]
                if len(a['accesses']) != len(b['accesses']) or len(a['external_effects']) != len(b['external_effects']):
                    differences.append(z.BoolVal(True))
                for x, y in zip(a['accesses'], b['accesses']):
                    differences.append(z.BoolVal(True) if x[0] != y[0] or x[2] != y[2]
                                       else z.Or(x[1] != y[1], x[3] != y[3]))
                for x, y in zip(a['external_effects'], b['external_effects']):
                    if x['name'] != y['name'] or x['target'] != y['target'] or x['iat_address'] != y['iat_address']:
                        differences.append(z.BoolVal(True))
                    for key in ('argument', 'return'):
                        if (x[key] is None) != (y[key] is None):
                            differences.append(z.BoolVal(True))
                        elif x[key] is not None:
                            differences.append(x[key] != y[key])
                result, model = query(z.And(domain, z.Or(*differences)))
                if result == z.sat:
                    value = lambda v: hex(model.eval(v, model_completion=True).as_long())
                    return base | {'status': 'different', 'feasible_path_pairs_checked': pairs,
                        'counterexample': inputs(model) | {'baseline_path': i, 'layer_path': j,
                            'external_choices': {name: value(z.BitVec(name, bits))
                                for name, bits in (a['external_symbols'] | b['external_symbols']).items()},
                            'exit_code': {'baseline': value(a['exit_code']), 'layer': value(b['exit_code'])},
                            'last_error': {'baseline': value(a['last_error']), 'layer': value(b['last_error'])},
                            'differing_live_registers': {n: {'baseline': value(a['registers'][n]),
                                'layer': value(b['registers'][n])} for n in normalized['live_registers']
                                if value(a['registers'][n]) != value(b['registers'][n])},
                            'masked_flags': {'baseline': value(a['flags'] & normalized['live_flags']),
                                'layer': value(b['flags'] & normalized['live_flags'])},
                            'differing_memory_bytes': {hex(p): {'baseline': value(a['memory'][p]), 'layer': value(b['memory'][p])}
                                for p in addresses if value(a['memory'][p]) != value(b['memory'][p])},
                            'differing_code_bytes': {hex(p): {'baseline': value(a['memory'][p]), 'layer': value(b['memory'][p])}
                                for p in families[0][1] if value(a['memory'][p]) != value(b['memory'][p])},
                            'external_effect_counts': {'baseline': len(a['external_effects']), 'layer': len(b['external_effects'])},
                            'validation': 'Contract-scoped symbolic module witness; independent replay required'}}
        contraction = {'format': 'fdisbull-pe-module-contraction-1', 'scope': SCOPE,
            'sources': {'baseline': _digest(baseline), 'layer': _digest(layer)},
            'contract': base['contract'], 'initialization': initialization, 'coverage': base['coverage'],
            'baseline_recovery': base['baseline_recovery'], 'layer_recovery': base['layer_recovery'],
            'external_contracts': base['external_contracts'], 'feasible_path_pairs_checked': pairs}
        contraction['sha256'] = _digest(contraction)
        return base | {'status': 'equivalent_under_contract', 'contraction': contraction,
                       'feasible_path_pairs_checked': pairs}
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return base | {'reason': str(error)}


def expand_pe_module_contraction(contraction, baseline, layer):
    if (not isinstance(contraction, dict) or contraction.get('format') != 'fdisbull-pe-module-contraction-1'
            or contraction.get('sha256') != _digest({k: v for k, v in contraction.items() if k != 'sha256'})
            or contraction.get('sources') != {'baseline': _digest(baseline), 'layer': _digest(layer)}):
        raise ValueError('Module contraction requires its exact original boundary and version evidence')
    return {'baseline': deepcopy(baseline), 'layer': deepcopy(layer)}
