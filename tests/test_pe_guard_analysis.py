"""Native CPU observations independently qualify guard models and witnesses."""
from copy import deepcopy
import itertools
import random

import pytest

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_guard_analysis import compare_pe_patch_guards, compare_pe_patch_paths
from fdisbull.pe_guard_model import ARITHMETIC_MASK, FLAG_BITS, cmp_flags, condition_name, decision
from fdisbull.pe_path_transfer import compare_pe_register_paths
from fdisbull.wine_arch import register_names


def capture(code, *, bits=64, general=None, flags=0x202):
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64 if bits == 64 else unicorn.UC_MODE_32)
    cpu.mem_map(0x1000, 4096)
    raw = bytes.fromhex(code)
    cpu.mem_write(0x1000, raw)
    names = register_names(bits) - ({'rip', 'rflags'} if bits == 64 else {'eip', 'eflags'})
    for name, value in (general or {}).items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), value)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, flags)
    events = []

    def before(guest, address, size, _):
        ip, flag = ('rip', 'rflags') if bits == 64 else ('eip', 'eflags')
        context = {'general': {name: hex(guest.reg_read(getattr(reg, 'UC_X86_REG_' + name.upper())))
                               for name in names}, ip: hex(address),
                   flag: hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)), 'thread': 17}
        events.append({'address': hex(address), 'project_address': hex(address),
                       'execution_bytes': bytes(guest.mem_read(address, size)).hex(),
                       'bytes': bytes(guest.mem_read(address, size)).hex(), 'registers': context})

    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(0x1000, 0x1000 + len(raw), count=64)
    normalize_trace('wine-qemu', events, version=1)
    return {'mapping': {'backend': 'wine-qemu', 'bits': bits, 'source_sha256': 'a' * 64,
                        'version_sha256': 'b' * 64},
            'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}


def test_cmp_boundary_witness_slice_and_independent_native_replay():
    # MOV RAX,RCX; CMP RAX,RBX; JA/JAE +1; NOP; NOP.
    old, new = '4889c84839d877019090', '4889c84839d873019090'
    baseline = capture(old, general={'rcx': 2, 'rbx': 3})
    layer = capture(new, general={'rcx': 2, 'rbx': 3})
    result = compare_pe_patch_paths(baseline, layer, same_source=True)
    guards = result['guards']
    assert guards['baseline']['status'] == 'complete'
    assert guards['baseline']['guards'][0]['slice']['event_indices'] == [0, 1]
    assert guards['baseline']['guards'][0]['slice']['entry_registers'] == ['rbx', 'rcx']
    pair, = guards['guard_pairs']
    witness = pair['difference_search']['witness']
    assert witness['baseline_taken'] is False and witness['layer_taken'] is True
    assert witness['entry_general']['rcx'] == witness['entry_general']['rbx']
    inputs = {n: int(v, 16) for n, v in witness['entry_general'].items()}
    replay_a = capture(old, general=inputs, flags=int(witness['entry_flags'], 16))
    replay_b = capture(new, general=inputs, flags=int(witness['entry_flags'], 16))
    assert replay_a['events'][3]['address'] == witness['baseline_successor'] == '0x1008'
    assert replay_b['events'][3]['address'] == witness['layer_successor'] == '0x1009'
    assert result['semantic_equivalence'] is None
    assert result['register_paths']['status'] == 'unknown'  # CMP isn't a register-transfer model.


@pytest.mark.parametrize('bits,prefix,dest', [(32, '', 'eax'), (64, '48', 'rax')])
def test_immediate_compare_and_flags_match_cpu_at_boundaries(bits, prefix, dest):
    values = [0, 1, 7, 8, (1 << (bits - 1)) - 1, 1 << (bits - 1), (1 << bits) - 1]
    for left in values:
        trace = capture(prefix + '83f8ff9090', bits=bits, general={dest: left})  # CMP reg,-1
        after = trace['events'][1]['registers']
        actual = int(after['eflags' if bits == 32 else 'rflags'], 16) & ARITHMETIC_MASK
        assert cmp_flags(left, (1 << bits) - 1, bits) == actual
    trace = capture(prefix + '83f80777019090', bits=bits, general={dest: 2})
    layer = capture(prefix + '83f80773019090', bits=bits, general={dest: 2})
    pair, = compare_pe_patch_guards(trace, layer, same_source=True)['guard_pairs']
    assert int(pair['difference_search']['witness']['entry_general'][dest], 16) == 7


@pytest.mark.parametrize('bits', [32, 64])
def test_all_jcc_predicates_match_cpu_for_all_relevant_flag_combinations(bits):
    from iced_x86 import Decoder
    names = ('cf', 'pf', 'zf', 'sf', 'of')
    for opcode, values in itertools.product(range(0x70, 0x80), itertools.product((0, 1), repeat=5)):
        flags = 0x202 | sum(value << FLAG_BITS[name] for name, value in zip(names, values, strict=True))
        raw = bytes((opcode, 1))
        trace = capture(raw.hex() + '9090', flags=flags, bits=bits)
        taken = trace['events'][1]['address'] == '0x1003'
        assert decision(condition_name(Decoder(bits, raw, ip=0x1000).decode()), flags) == taken


def test_prior_guards_must_allow_one_shared_entry_state():
    baseline = capture('74019077019090', flags=0x203)  # JE not taken; JA not taken.
    layer = capture('75019073019090', flags=0x243)     # JNE not taken; JAE not taken.
    report = compare_pe_patch_guards(baseline, layer, same_source=True)
    assert len(report['guard_pairs']) == 2
    second = report['guard_pairs'][1]
    assert second['difference_search']['status'] == 'no_witness_in_candidates'
    assert second['difference_search']['witness'] is None
    assert report['baseline']['guards'][1]['slice']['control_event_indices'] == [0]


def test_unsupported_dependencies_tampered_flags_and_wrong_taken_edge_stop_slicing():
    baseline = capture('4889c84839d877019090', general={'rcx': 2, 'rbx': 3})
    bad = deepcopy(baseline)
    bad['events'][0]['execution_bytes'] = '488b01'  # Memory load.
    report = compare_pe_patch_guards(bad, baseline, same_source=True)
    assert report['baseline']['status'] == 'partial' and not report['guard_pairs']
    assert report['baseline']['frontier']['event_index'] == 0
    bad = deepcopy(baseline)
    bad['events'][2]['registers']['rflags'] = '0x202'
    report = compare_pe_patch_guards(bad, baseline, same_source=True)
    assert report['baseline']['frontier']['event_index'] == 1
    # Native trace is JNE taken. Flipping ZF makes its recorded successor impossible.
    branch = capture('75019090', flags=0x202)
    branch['events'][0]['registers']['rflags'] = '0x242'
    assert compare_pe_register_paths(branch, branch, same_source=True)['status'] == 'unknown'


def test_search_budget_source_binding_and_coverage_are_explicit():
    baseline = capture('4883f80777019090', general={'rax': 2})
    layer = capture('4883f80773019090', general={'rax': 2})
    result = compare_pe_patch_guards(baseline, layer, same_source=True, max_candidates=1)
    assert result['candidates_checked'] == 1
    assert result['guard_pairs'][0]['difference_search']['status'] == 'budget_exhausted'
    assert result['semantic_equivalence'] is None
    changed = deepcopy(layer)
    changed['mapping']['source_sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='byte identities'):
        compare_pe_patch_guards(baseline, changed, same_source=True)
    result = compare_pe_patch_guards(baseline, changed)
    assert result['status'] == 'unknown'
    assert result['sources']['layer']['trace_sha256'] != result['sources']['baseline']['trace_sha256']


def test_slice_follows_latest_definition_and_retains_control_dependencies():
    # MOV RAX,RCX; MOV RAX,RDX; CMP RAX,RBX; JA +1; NOP; NOP.
    trace = capture('4889c84889d04839d877019090', general={'rcx': 99, 'rdx': 2, 'rbx': 3})
    result = compare_pe_patch_guards(trace, trace, same_source=True)
    guard, = result['baseline']['guards']
    assert guard['slice']['event_indices'] == [1, 2]
    assert guard['slice']['entry_registers'] == ['rbx', 'rdx']
    assert result['guard_pairs'][0]['difference_search']['status'] == 'same_expression'


def test_predicate_witness_does_not_claim_distinct_control_effect():
    baseline, layer = capture('770090'), capture('730090')  # Target equals fallthrough.
    result = compare_pe_patch_guards(baseline, layer, same_source=True)
    witness = result['guard_pairs'][0]['difference_search']['witness']
    assert witness['baseline_successor'] == witness['layer_successor'] == '0x1002'
    assert 'Predicate decision difference' in witness['scope']
    assert result['semantic_equivalence'] is None


def test_unaligned_entry_and_removed_guard_are_not_silently_paired():
    baseline = capture('909077019090')
    layer = capture('909073019090')
    # Different initial site, despite a later aligned branch.
    baseline['events'][0]['project_address'] = '0x2000'
    baseline['events'][0]['identity']['project_address'] = '0x2000'
    result = compare_pe_patch_guards(baseline, layer, same_source=True)
    assert result['common_entry_established'] is False
    assert not result['guard_pairs']
    assert result['unpaired_guard_events']['baseline'] == [2]
    baseline = capture('77019090')
    layer = capture('90909090')
    result = compare_pe_patch_guards(baseline, layer, same_source=True)
    assert not result['guard_pairs']
    assert result['unpaired_guard_events']['baseline'] == [0]


@pytest.mark.parametrize('bits,prefix,a,b', [(32, '', 'eax', 'ebx'), (64, '48', 'rax', 'rbx')])
def test_cmp_register_flags_match_cpu_for_signed_unsigned_edges_and_random_pairs(bits, prefix, a, b):
    rng = random.Random(7301)
    sign, maximum = 1 << (bits - 1), (1 << bits) - 1
    pairs = [(0, 1), (sign, 1), (sign - 1, maximum), (maximum, maximum), (0, maximum)]
    pairs += [(rng.getrandbits(bits), rng.getrandbits(bits)) for _ in range(40)]
    for left, right in pairs:
        trace = capture(prefix + '39d890', bits=bits, general={a: left, b: right})
        flags = trace['events'][1]['registers']['eflags' if bits == 32 else 'rflags']
        assert int(flags, 16) & ARITHMETIC_MASK == cmp_flags(left, right, bits)


def test_separate_sources_use_evidenced_site_map_and_partial_prefix_stays_partial():
    baseline = capture('4883f80777019090', general={'rax': 2})
    layer = capture('4883f80773019090', general={'rax': 2})
    layer['mapping']['source_sha256'] = 'c' * 64
    correspondence = [{'baseline': {'source_version': 1, 'context': 'flat',
                                    'project_address': event['project_address']},
                       'layer': {'source_version': 1, 'context': 'flat',
                                 'project_address': event['project_address']},
                       'evidence': 'authored fixture sites'} for event in baseline['events']]
    result = compare_pe_patch_guards(baseline, layer, correspondence=correspondence)
    assert result['guard_pairs'][0]['difference_search']['status'] == 'found'
    baseline, layer = capture('7701909090'), capture('7701909090')
    layer['events'][1]['execution_bytes'] = 'cc'
    result = compare_pe_patch_guards(baseline, layer, same_source=True)
    assert len(result['guard_pairs']) == 1 and result['status'] == 'partial'
