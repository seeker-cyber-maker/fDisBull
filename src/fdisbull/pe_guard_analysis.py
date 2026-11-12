"""Trace-bound guard comparison, finite witnesses and backward dependency slices.

The admitted prefix is full-width MOV/CMP, NOP and direct JMP/Jcc. Slices
describe register/flag dependencies along captured paths, not all program paths.
"""
from copy import deepcopy
import hashlib
import itertools
import json

import capstone
from capstone import x86_const
from iced_x86 import Decoder

from .behavior_diff import compare_trace_topology
from .pe_guard_model import ARITHMETIC_MASK, FLAG_BITS, READS, cmp_flags, condition_name, decision
from .pe_path_transfer import _qualified_trace, _state
from .uil_catalog import from_asm_instruction


def _value(expression, state):
    return state['general'][expression['register']] if 'register' in expression else expression['constant']


def _flags(predicate, state):
    source = predicate['flags']
    if source['kind'] == 'entry_flags':
        return state['flags']
    return cmp_flags(_value(source['left'], state), _value(source['right'], state), source['bits'])


def _evaluate(predicate, state):
    return decision(predicate['condition'], _flags(predicate, state))


def _inputs(predicate):
    if predicate['condition'] == 'always':
        return set(), set()
    source = predicate['flags']
    if source['kind'] == 'entry_flags':
        return set(), set(READS[predicate['condition']])
    return {e['register'] for e in (source['left'], source['right']) if 'register' in e}, set()


def _receipt(trace):
    return {'version': trace['version'],
            'source_sha256': trace['mapping']['source_sha256'],
            'version_sha256': trace['mapping']['version_sha256'],
            'trace_sha256': hashlib.sha256(json.dumps(trace, sort_keys=True, separators=(',', ':'),
                                                     allow_nan=False).encode()).hexdigest()}


def _extract(trace, bits):
    events = trace['events']
    registers, _, _ = _state(events[0], bits)
    symbols = {name: {'register': name} for name in registers}
    producers = {name: set() for name in registers}
    flag_source, flag_producers = {'kind': 'entry_flags'}, set()
    guards = []
    decoder = capstone.Cs(capstone.CS_ARCH_X86,
                          capstone.CS_MODE_64 if bits == 64 else capstone.CS_MODE_32)
    decoder.detail = True
    for index, event in enumerate(events[:-1]):
        following = events[index + 1]
        try:
            if event['observation'].get('instruction_completed') is not True:
                raise ValueError('Instruction completion is unverified')
            before, flags, thread = _state(event, bits)
            after, next_flags, next_thread = _state(following, bits)
            if thread is None or thread != next_thread:
                raise ValueError('Selected thread changes')
            raw_hex = event.get('execution_bytes', event.get('bytes'))
            if not isinstance(raw_hex, str) or not 2 <= len(raw_hex) <= 30 or len(raw_hex) % 2:
                raise ValueError('Missing exact instruction bytes')
            raw = bytes.fromhex(raw_hex)
            address, next_address = int(event['address'], 16), int(following['address'], 16)
            ins = Decoder(bits, raw, ip=address).decode()
            if ins.is_invalid or ins.len != len(raw):
                raise ValueError('Instruction bytes are not exact')
            sequential = (address + len(raw)) % (1 << bits)
            if ins.is_jcc_short_or_near or ins.is_jmp_short_or_near:
                condition = condition_name(ins)
                predicate = {'condition': condition, 'flags': deepcopy(flag_source)}
                taken = decision(condition, flags)
                expected = ins.near_branch_target if taken else sequential
                if next_address != expected or before != after or flags != next_flags:
                    raise ValueError('Branch decision or preserved state contradicts the trace')
                names, flag_names = _inputs(predicate)
                dependencies = sorted(flag_producers) if condition != 'always' else []
                guards.append({'event_index': index, 'project_address': event['project_address'],
                               'predicate': predicate, 'modeled_taken': taken,
                               'semantic_id': 'pe-guard:' + hashlib.sha256(json.dumps(
                                   predicate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                               'decision_basis': 'Captured FLAGS and x86 predicate; next PC checked',
                               'target': hex(ins.near_branch_target), 'fallthrough': hex(sequential),
                               'prior_path': [g['modeled_taken'] for g in guards],
                               'slice': {'event_indices': dependencies,
                                         'entry_registers': sorted(names), 'entry_flags': sorted(flag_names),
                                         'control_event_indices': [g['event_index'] for g in guards],
                                         'scope': 'Captured prefix data dependencies and prior control decisions'}})
                continue
            if next_address != sequential:
                raise ValueError('Nonsequential successor outside direct branch profile')
            if raw == b'\x90':
                if before != after or flags != next_flags:
                    raise ValueError('NOP changes state')
                continue
            decoded = list(decoder.disasm(raw, address))
            if len(decoded) != 1 or decoded[0].size != len(raw):
                raise ValueError('Native decode does not cover one instruction')
            native = decoded[0]
            if native.mnemonic == 'mov':
                model = from_asm_instruction(raw, bits=bits, flags='explicit')
                dest, src = model['source']['outputs'][0], model['source']['inputs'][0]
                if dest not in symbols or src not in symbols:
                    raise ValueError('Partial register MOV is unsupported')
                if (after != {**before, dest: before[src]} or flags != next_flags):
                    raise ValueError('MOV state contradicts the model')
                symbols[dest] = deepcopy(symbols[src])
                producers[dest] = producers[src] | {index}
            elif native.mnemonic == 'cmp':
                operands = native.operands
                if len(operands) != 2 or any(native.prefix):
                    raise ValueError('CMP prefix or operands are unsupported')
                expressions, dependencies, values = [], set(), []
                for operand in operands:
                    if operand.type == x86_const.X86_OP_REG:
                        name = native.reg_name(operand.reg)
                        if name not in symbols or operand.size * 8 != bits:
                            raise ValueError('Partial register CMP is unsupported')
                        expressions.append(deepcopy(symbols[name]))
                        dependencies |= producers[name]
                        values.append(before[name])
                    elif operand.type == x86_const.X86_OP_IMM:
                        value = operand.imm % (1 << bits)
                        expressions.append({'constant': value})
                        values.append(value)
                    else:
                        raise ValueError('Memory CMP dependency is unresolved')
                expected = (flags & ~ARITHMETIC_MASK) | cmp_flags(*values, bits)
                if before != after or next_flags != expected:
                    raise ValueError('CMP state contradicts the model')
                flag_source = {'kind': 'cmp', 'bits': bits,
                               'left': expressions[0], 'right': expressions[1]}
                flag_producers = dependencies | {index}
            else:
                raise ValueError('Instruction is outside the MOV/CMP/NOP/direct branch prefix')
        except (KeyError, TypeError, ValueError) as error:
            return {'status': 'partial', 'guards': guards,
                    'frontier': {'event_index': index, 'reason': str(error)}}
    return {'status': 'complete', 'guards': guards, 'frontier': None}


def _witness(left, right, left_guards, right_guards, baseline, bits, budget):
    predicates = [g['predicate'] for g in left_guards + right_guards] + [left['predicate'], right['predicate']]
    names, flags_read, candidates = set(), set(), {0, 1, (1 << bits) - 1, 1 << (bits - 1)}
    for predicate in predicates:
        regs, flags = _inputs(predicate)
        names |= regs
        flags_read |= flags
        source = predicate['flags']
        if source['kind'] == 'cmp':
            for expr in (source['left'], source['right']):
                if 'constant' in expr:
                    candidates.update((expr['constant'] + offset) % (1 << bits) for offset in (-1, 0, 1))
    initial, initial_flags, _ = _state(baseline['events'][0], bits)
    candidates.update(initial[name] for name in names)
    names, flag_names = sorted(names), sorted(flags_read)
    count = 0
    for values in itertools.product(sorted(candidates), repeat=len(names)):
        for flag_values in itertools.product((False, True), repeat=len(flag_names)):
            if count >= budget:
                return {'status': 'budget_exhausted', 'candidates_checked': count, 'witness': None}
            count += 1
            state = {'general': {**initial, **dict(zip(names, values, strict=True))}, 'flags': initial_flags}
            for name, value in zip(flag_names, flag_values, strict=True):
                state['flags'] = (state['flags'] & ~(1 << FLAG_BITS[name])) | (int(value) << FLAG_BITS[name])
            if any(_evaluate(g['predicate'], state) != g['modeled_taken'] for g in left_guards + right_guards):
                continue
            a, b = _evaluate(left['predicate'], state), _evaluate(right['predicate'], state)
            if a != b:
                return {'status': 'found', 'candidates_checked': count,
                        'witness': {'entry_general': {n: hex(v) for n, v in sorted(state['general'].items())},
                                    'entry_flags': hex(state['flags']), 'baseline_taken': a, 'layer_taken': b,
                                    'baseline_successor': left['target'] if a else left['fallthrough'],
                                    'layer_successor': right['target'] if b else right['fallthrough'],
                                    'scope': 'Predicate decision difference; successor correspondence and external effects unverified',
                                    'validation': 'Evaluated in both admitted prefix models; native replay pending'}}
    return {'status': 'no_witness_in_candidates', 'candidates_checked': count, 'witness': None}


def compare_pe_patch_guards(baseline, layer, *, same_source=False, correspondence=None,
                            max_candidates=4096):
    """Compare aligned branch predicates and search bounded common-entry witnesses.

    A found witness proves a decision difference in the admitted prefix models.
    Exhausting candidates proves no equivalence. Whole-program effects stay unknown.
    """
    if type(max_candidates) is not int or not 1 <= max_candidates <= 65536:
        raise ValueError('max_candidates must be 1..65536')
    bits, other_bits = _qualified_trace(baseline), _qualified_trace(layer)
    if bits != other_bits:
        raise ValueError('Guard comparison requires matching PE widths')
    if same_source and any(baseline['mapping'][key] != layer['mapping'][key]
                           for key in ('source_sha256', 'version_sha256')):
        raise ValueError('Same-source guard comparison requires matching byte identities')
    topology = compare_trace_topology(baseline, layer, same_source=same_source, correspondence=correspondence)
    left, right = _extract(baseline, bits), _extract(layer, bits)
    pairs = []
    remaining = max_candidates
    segments = topology['segments']
    common_entry = bool(segments and segments[0]['kind'] == 'common'
                        and segments[0]['baseline'][0] == segments[0]['layer'][0] == 0)
    if topology['alignment'] == 'evidenced' and not topology['segments_truncated'] and common_entry:
        left_sites = {g['event_index']: (i, g) for i, g in enumerate(left['guards'])}
        right_sites = {g['event_index']: (i, g) for i, g in enumerate(right['guards'])}
        for segment in topology['segments']:
            if segment['kind'] != 'common':
                continue
            for a, b in zip(range(*segment['baseline']), range(*segment['layer']), strict=True):
                if a not in left_sites or b not in right_sites:
                    continue
                i, x = left_sites[a]
                j, y = right_sites[b]
                equal = x['predicate'] == y['predicate']
                search = ({'status': 'same_expression', 'candidates_checked': 0, 'witness': None} if equal else
                          _witness(x, y, left['guards'][:i], right['guards'][:j], baseline, bits, remaining))
                remaining -= search['candidates_checked']
                pairs.append({'baseline_event_index': a, 'layer_event_index': b,
                              'guard_relation': 'same_expression' if equal else 'different_expression',
                              'difference_search': search,
                              'successor_correspondence': 'uncompared'})
    paired_left = {pair['baseline_event_index'] for pair in pairs}
    paired_right = {pair['layer_event_index'] for pair in pairs}
    unpaired = any(g['event_index'] not in paired_left for g in left['guards']) or any(
        g['event_index'] not in paired_right for g in right['guards'])
    return {'format': 'fdisbull-pe-guard-analysis-1',
            'status': ('partial' if unpaired or left['status'] == 'partial' or right['status'] == 'partial'
                       else 'compared') if pairs else 'unknown',
            'common_entry_established': common_entry,
            'unpaired_guard_events': {
                'baseline': [g['event_index'] for g in left['guards'] if g['event_index'] not in paired_left],
                'layer': [g['event_index'] for g in right['guards'] if g['event_index'] not in paired_right]},
            'sources': {'baseline': _receipt(baseline), 'layer': _receipt(layer)},
            'baseline': left, 'layer': right, 'guard_pairs': pairs, 'topology': topology,
            'candidates_checked': max_candidates - remaining,
            'semantic_equivalence': None,
            'scope': 'Aligned guard decisions, captured-prefix slices and bounded model witnesses; external inputs/effects unknown'}


def compare_pe_patch_paths(baseline, layer, *, same_source=False, correspondence=None,
                           max_candidates=4096):
    """Combine existing path transfer and new guard evidence without an equivalence verdict."""
    from .pe_path_transfer import compare_pe_register_paths
    return {'format': 'fdisbull-pe-patch-paths-1',
            'guards': compare_pe_patch_guards(baseline, layer, same_source=same_source,
                                             correspondence=correspondence, max_candidates=max_candidates),
            'register_paths': compare_pe_register_paths(baseline, layer, same_source=same_source,
                                                       correspondence=correspondence),
            'semantic_equivalence': None}
