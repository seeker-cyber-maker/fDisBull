"""Regional proofs retain liveness, guards, byte aliases and expandable evidence."""
from copy import deepcopy
import random

import pytest

pytest.importorskip('z3')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_guard_analysis import compare_pe_patch_paths
from fdisbull.pe_region_equivalence import compare_pe_regions, expand_pe_contraction
from fdisbull.wine_arch import register_names


@pytest.mark.parametrize('bits,prefix,a,b', [(32, '', 'eax', 'ebx'), (64, '48', 'rax', 'rbx')])
@pytest.mark.parametrize('opcode,logical', [('01d8', False), ('29d8', False), ('31d8', True),
                                           ('21d8', True), ('09d8', True), ('39d8', False)])
def test_arithmetic_model_agrees_with_independent_cpu_samples(bits, prefix, a, b, opcode, logical):
    rng = random.Random(8812)
    pairs = [(0, 1), ((1 << bits) - 1, 1), (1 << (bits - 1), 1),
             ((1 << (bits - 1)) - 1, (1 << bits) - 1)]
    pairs += [(rng.getrandbits(bits), rng.getrandbits(bits)) for _ in range(12)]
    for left, right in pairs:
        (trace, _), _ = _pair(prefix + opcode, prefix + opcode, bits=bits, general={a: left, b: right})
        result = compare_pe_regions(trace, trace,
            contract={'live_flags': 0xffffffef if logical else 0xffffffff}, same_source=True)
        assert result['status'] == 'equivalent_under_contract'


def test_rip_relative_loads_and_immediate_store_widths():
    (a, am), (b, bm) = _pair('488b05f91f0000', '488b0df91f00004889c8',
                              memory=bytes.fromhex('8877665544332211'))
    contract = {'live_registers': ['rax'], 'memory_model': 'private_ordinary_ram',
                'memory_ranges': [{'address': '0x3000', 'length': 8}]}
    assert compare_pe_regions(a, b, contract=contract, same_source=True,
        baseline_memory=am, layer_memory=bm)['status'] == 'equivalent_under_contract'
    for bits, pointer, code in ((64, 'rdi', '48c707ffffffff'), (64, 'rdi', 'c60780'),
                               (64, 'rdi', 'c70744332211'), (32, 'edi', 'c60780'),
                               (32, 'edi', 'c70744332211')):
        (trace, evidence), _ = _pair(code, code, bits=bits, general={pointer: 0x3000}, memory=bytes(8))
        contract['entry_registers'] = {pointer: '0x3000'}
        contract.pop('live_registers', None)
        assert compare_pe_regions(trace, trace, contract=contract, same_source=True,
            baseline_memory=evidence, layer_memory=evidence)['status'] == 'equivalent_under_contract'


def _capture(code, *, general=None, flags=0x202, bits=64, memory=b''):
    """Capture real CPU pre-states and data snapshots, not model predictions."""
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86,
                     unicorn.UC_MODE_64 if bits == 64 else unicorn.UC_MODE_32)
    cpu.mem_map(0x1000, 4096)
    cpu.mem_write(0x1000, code)
    cpu.mem_map(0x3000, 4096)
    if memory:
        cpu.mem_write(0x3000, memory)
    for name, value in (general or {}).items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), value)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, flags)
    ip, flag = ('rip', 'rflags') if bits == 64 else ('eip', 'eflags')
    names = register_names(bits) - {ip, flag}
    events = []

    def before(guest, address, size, _):
        raw = bytes(guest.mem_read(address, size)).hex()
        events.append({'address': hex(address), 'project_address': hex(address),
                       'bytes': raw, 'execution_bytes': raw,
                       'registers': {ip: hex(address),
                                     flag: hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                                     'thread': 17,
                                     'general': {name: hex(guest.reg_read(getattr(
                                         reg, 'UC_X86_REG_' + name.upper()))) for name in names}}})

    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(0x1000, 0x1000 + len(code), count=64)
    normalize_trace('wine-qemu', events, version=1)
    trace = {'mapping': {'backend': 'wine-qemu', 'bits': bits,
                         'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64},
             'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}
    snapshots = {'entry': [{'address': '0x3000', 'hex': memory.hex()}],
                 'exit': [{'address': '0x3000',
                           'hex': bytes(cpu.mem_read(0x3000, len(memory))).hex()}]} if memory else None
    return trace, snapshots


def _pair(left, right, **kwargs):
    left, right = bytes.fromhex(left), bytes.fromhex(right)
    # Different internal regions retain one common final pre-instruction boundary.
    length = max(len(left), len(right)) + 1
    a = _capture(left.ljust(length, b'\x90'), **kwargs)
    b = _capture(right.ljust(length, b'\x90'), **kwargs)
    assert a[0]['events'][0]['address'] == b[0]['events'][0]['address'] == '0x1000'
    assert a[0]['events'][-1]['address'] == b[0]['events'][-1]['address']
    return a, b


def _ram_contract(length, *, observation='ordered'):
    return {'entry_registers': {'rdi': '0x3000'},
            'memory_ranges': [{'address': '0x3000', 'length': length}],
            'memory_model': 'private_ordinary_ram', 'memory_observation': observation}


def test_region_with_extra_copy_contracts_only_when_clobbered_register_is_dead():
    (baseline, _), (layer, _) = _pair('4889d8', '4889d94889c8',
                                     general={'rax': 0, 'rbx': 7, 'rcx': 99})
    live_result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert live_result['status'] == 'different'
    assert live_result.get('contraction') is None
    result = compare_pe_regions(baseline, layer,
                                contract={'live_registers': ['rax']}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'
    assert result['contraction']
    assert result['contraction']['reduced_effects']['registers']['rax'] == {
        'type': 'u64', 'expression': 'entry_rbx'}
    expanded = expand_pe_contraction(result['contraction'], baseline, layer)
    assert expanded['baseline'] == baseline and expanded['layer'] == layer
    assert expanded['baseline'] is not baseline
    # The operation node's expandable boundary data must not alias the original trace.
    original = deepcopy(baseline)
    result['contraction']['regions']['baseline']['entry']['project_address'] = '0xbad'
    assert baseline == original


def test_algebraically_cancelled_arithmetic_preserves_live_data_but_not_flags():
    (baseline, _), (layer, _) = _pair('4801d84829d8', '90',
                                     general={'rax': 0xFFFFFFFFFFFFFFFF, 'rbx': 7})
    result = compare_pe_regions(baseline, layer, contract={'live_flags': 0}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'
    result = compare_pe_regions(baseline, layer, contract={'live_flags': 0x40}, same_source=True)
    assert result['status'] == 'different'
    assert result.get('counterexample')
    witness = result['counterexample']
    replay_a, replay_b = _pair('4801d84829d8', '90',
        general={n: int(v, 16) for n, v in witness['entry_general'].items()},
        flags=int(witness['entry_flags'], 16))
    a_flags = int(replay_a[0]['events'][-1]['registers']['rflags'], 16)
    b_flags = int(replay_b[0]['events'][-1]['registers']['rflags'], 16)
    assert a_flags & 0x40 != b_flags & 0x40


def test_equal_zeroing_result_requires_live_flag_contract():
    (baseline, _), (layer, _) = _pair('48c7c000000000', '4831c0', general={'rax': 9})
    assert compare_pe_regions(baseline, layer, contract={'live_flags': 0},
                              same_source=True)['status'] == 'equivalent_under_contract'
    assert compare_pe_regions(baseline, layer, contract={'live_flags': 0x40},
                              same_source=True)['status'] == 'different'
    # XOR's architecturally undefined AF cannot become a claimed equality.
    assert compare_pe_regions(baseline, layer, contract={'live_flags': 0x10},
                              same_source=True)['status'] == 'unknown'


def test_equal_captured_path_domains_can_have_different_guard_encodings():
    # CMP operands reversed, JE keeps the same equality predicate. FLAGS are dead.
    (baseline, _), (layer, _) = _pair('4839d8740190', '4839c3740190',
                                     general={'rax': 1, 'rbx': 2})
    result = compare_pe_regions(baseline, layer, contract={'live_flags': 0}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'


def test_changed_guard_domain_blocks_contraction_even_with_no_live_data():
    # Both observed paths fall through, but they require incompatible entry domains.
    raw_a = bytes.fromhex('4883f80074019090')
    raw_b = bytes.fromhex('4883f80075019090')
    baseline, _ = _capture(raw_a, general={'rax': 1})
    layer, _ = _capture(raw_b, general={'rax': 0})
    result = compare_pe_regions(baseline, layer,
                                contract={'live_registers': [], 'live_flags': 0}, same_source=True)
    assert result['status'] == 'different'
    assert result.get('counterexample')
    assert result.get('contraction') is None


def test_equal_final_ram_does_not_erase_an_extra_ordered_write():
    # The first store is overwritten; it still exists in the default ordered contract.
    (baseline, a_memory), (layer, b_memory) = _pair('48890748891f', '48891f',
        general={'rdi': 0x3000, 'rax': 1, 'rbx': 2}, memory=bytes(8))
    kwargs = {'same_source': True, 'baseline_memory': a_memory, 'layer_memory': b_memory}
    assert a_memory['exit'] == b_memory['exit']
    result = compare_pe_regions(baseline, layer, contract=_ram_contract(8), **kwargs)
    assert result['status'] == 'different'
    result = compare_pe_regions(baseline, layer,
                                contract=_ram_contract(8, observation='final'), **kwargs)
    assert result['status'] == 'equivalent_under_contract'
    expanded = expand_pe_contraction(result['contraction'], baseline, layer,
                                     baseline_memory=a_memory, layer_memory=b_memory)
    assert expanded['baseline'] == baseline
    changed_memory = deepcopy(a_memory)
    changed_memory['entry'][0]['hex'] = '01' + '00' * 7
    with pytest.raises(ValueError):
        expand_pe_contraction(result['contraction'], baseline, layer,
                              baseline_memory=changed_memory, layer_memory=b_memory)


def test_overlapping_store_aliases_are_compared_byte_by_byte():
    # The concrete samples are equal, while symbolic bytes differ under store reversal.
    (baseline, a_memory), (layer, b_memory) = _pair('48890748895f01', '48895f01488907',
        general={'rdi': 0x3000, 'rax': 0, 'rbx': 0}, memory=bytes(9))
    assert a_memory['exit'] == b_memory['exit']
    result = compare_pe_regions(baseline, layer,
        contract=_ram_contract(9, observation='final'), same_source=True,
        baseline_memory=a_memory, layer_memory=b_memory)
    assert result['status'] == 'different'
    assert result.get('counterexample')
    witness = result['counterexample']
    initial = bytes(int(witness['entry_memory'][hex(0x3000 + offset)], 16) for offset in range(9))
    replay_a, replay_b = _pair('48890748895f01', '48895f01488907',
        general={n: int(v, 16) for n, v in witness['entry_general'].items()},
        flags=int(witness['entry_flags'], 16), memory=initial)
    assert replay_a[1]['exit'] != replay_b[1]['exit']


def test_memory_read_through_temporary_has_same_live_output_and_accesses():
    # MOV RAX,[RDI] versus MOV RCX,[RDI]; MOV RAX,RCX.
    (baseline, a_memory), (layer, b_memory) = _pair('488b07', '488b0f4889c8',
        general={'rdi': 0x3000, 'rcx': 99}, memory=bytes.fromhex('8877665544332211'))
    contract = {**_ram_contract(8), 'live_registers': ['rax']}
    result = compare_pe_regions(baseline, layer, contract=contract, same_source=True,
                                baseline_memory=a_memory, layer_memory=b_memory)
    assert result['status'] == 'equivalent_under_contract'


def test_observed_pointer_is_not_silently_promoted_to_fixed_memory_assumption():
    (baseline, a_memory), (layer, b_memory) = _pair('488b07', '488b07',
        general={'rdi': 0x3000}, memory=bytes(8))
    contract = _ram_contract(8)
    contract.pop('entry_registers')
    result = compare_pe_regions(baseline, layer, contract=contract, same_source=True,
                                baseline_memory=a_memory, layer_memory=b_memory)
    assert result['status'] == 'unknown'
    result = compare_pe_regions(baseline, layer, contract=_ram_contract(8), same_source=True)
    assert result['status'] == 'unknown'


def test_memory_bounds_and_snapshot_contradictions_prevent_contraction():
    (baseline, a_memory), (layer, b_memory) = _pair('488b07', '488b07',
        general={'rdi': 0x3001}, memory=bytes(8))
    contract = {**_ram_contract(8), 'entry_registers': {'rdi': '0x3001'}}
    result = compare_pe_regions(baseline, layer, contract=contract, same_source=True,
                                baseline_memory=a_memory, layer_memory=b_memory)
    assert result['status'] == 'unknown'
    (baseline, a_memory), (layer, b_memory) = _pair('488b07', '488b07',
        general={'rdi': 0x3000}, memory=bytes(8))
    corrupted = deepcopy(a_memory)
    corrupted['entry'][0]['hex'] = 'ff' * 8
    result = compare_pe_regions(baseline, layer, contract=_ram_contract(8), same_source=True,
                                baseline_memory=corrupted, layer_memory=b_memory)
    assert result['status'] == 'unknown'
    contradicted = {**_ram_contract(8), 'entry_registers': {'rdi': '0x3001'}}
    result = compare_pe_regions(baseline, layer, contract=contradicted, same_source=True,
                                baseline_memory=a_memory, layer_memory=b_memory)
    assert result['status'] == 'unknown'


def test_ordinary_ram_contract_cannot_treat_executed_code_as_private_data():
    raw = bytes.fromhex('488b07909090909090')
    trace, _ = _capture(raw, general={'rdi': 0x1000})
    memory = {'entry': [{'address': '0x1000', 'hex': raw[:8].hex()}],
              'exit': [{'address': '0x1000', 'hex': raw[:8].hex()}]}
    contract = {'entry_registers': {'rdi': '0x1000'},
                'memory_ranges': [{'address': '0x1000', 'length': 8}],
                'memory_model': 'private_ordinary_ram'}
    result = compare_pe_regions(trace, trace, contract=contract, same_source=True,
                                baseline_memory=memory, layer_memory=memory)
    assert result['status'] == 'unknown'


def test_contraction_expansion_rejects_changed_trace_and_changed_contract():
    (baseline, _), (layer, _) = _pair('4889d8', '488bc3', general={'rbx': 7})
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'
    changed = deepcopy(layer)
    changed['events'][0]['execution_bytes'] = '4889c8'
    with pytest.raises(ValueError):
        expand_pe_contraction(result['contraction'], baseline, changed)
    altered = deepcopy(result['contraction'])
    altered['contract']['live_flags'] = 0
    with pytest.raises(ValueError):
        expand_pe_contraction(altered, baseline, layer)


def test_pe32_full_width_register_regions_are_qualified_independently():
    (baseline, _), (layer, _) = _pair('89d8', '89d989c8', bits=32,
                                     general={'ebx': 7, 'ecx': 99})
    result = compare_pe_regions(baseline, layer,
                                contract={'live_registers': ['eax']}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'


def test_ignored_legacy_prefix_is_outside_regional_profile():
    (baseline, _), (layer, _) = _pair('664889d8', '4889d8', general={'rbx': 7})
    assert compare_pe_regions(baseline, layer, contract={}, same_source=True)['status'] == 'unknown'


def test_combined_patch_analysis_returns_explicit_regional_contract_result():
    (baseline, _), (layer, _) = _pair('4889d8', '4889d94889c8',
                                     general={'rbx': 7, 'rcx': 99})
    report = compare_pe_patch_paths(baseline, layer, same_source=True,
                                    region_contract={'live_registers': ['rax']})
    assert report['regional']['status'] == 'equivalent_under_contract'
    assert report['regional']['contraction']['contract']['live_registers'] == ['rax']
    assert report['semantic_equivalence'] is None


def test_boundary_only_correspondence_accepts_separate_source_regions_with_unmatched_interiors():
    (baseline, _), (layer, _) = _pair('4889d8', '4889d94889c8',
                                     general={'rbx': 7, 'rcx': 99})
    layer['mapping']['source_sha256'], layer['mapping']['version_sha256'] = 'c' * 64, 'd' * 64
    correspondence = [{
        'baseline': {key: baseline['events'][index]['identity'][key]
                     for key in ('source_version', 'context', 'project_address')},
        'layer': {key: layer['events'][index]['identity'][key]
                  for key in ('source_version', 'context', 'project_address')},
        'evidence': 'reviewed homegrown common entry/exit boundaries',
    } for index in (0, -1)]
    assert len(baseline['events']) != len(layer['events'])
    result = compare_pe_regions(baseline, layer, contract={'live_registers': ['rax']},
                                correspondence=correspondence)
    assert result['status'] == 'equivalent_under_contract'
    assert result['contraction']['sources']['baseline']['source_sha256'] != result['contraction']['sources']['layer']['source_sha256']
    without_entry = compare_pe_regions(baseline, layer, contract={'live_registers': ['rax']},
                                       correspondence=correspondence[1:])
    assert without_entry['status'] == 'unknown'


def test_optional_solver_absence_prevents_contraction(monkeypatch):
    import builtins
    (baseline, _), (layer, _) = _pair('4889d8', '488bc3', general={'rbx': 7})
    original = builtins.__import__

    def without_z3(name, *args, **kwargs):
        if name == 'z3':
            raise ImportError('proof dependency intentionally unavailable')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', without_z3)
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'unknown'
    assert result.get('contraction') is None


def test_solver_unknown_never_becomes_equivalence(monkeypatch):
    import z3
    (baseline, _), (layer, _) = _pair('4889d8', '488bc3', general={'rbx': 7})
    real_solver = z3.Solver

    class UnknownSolver:
        def __init__(self):
            self.real = real_solver()

        def __getattr__(self, name):
            return getattr(self.real, name)

        def check(self):
            return z3.unknown

        def reason_unknown(self):
            return 'deterministic test unknown'

    monkeypatch.setattr(z3, 'Solver', UnknownSolver)
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'unknown'
    assert result.get('contraction') is None


def test_later_cmp_kills_undefined_logical_flags_before_live_exit():
    (baseline, _), (layer, _) = _pair('48c7c0000000004839d8', '4831c04839d8',
                                     general={'rax': 9, 'rbx': 7})
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'equivalent_under_contract'
