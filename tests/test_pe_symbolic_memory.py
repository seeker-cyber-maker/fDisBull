"""Symbolic byte aliases remain bounded and cannot hide invalid earlier accesses."""
import pytest

pytest.importorskip('z3')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_region_equivalence import compare_pe_regions
from fdisbull.wine_arch import register_names
from test_pe_region_equivalence import _pair


def _contract(length=16, *, observation='ordered', rdi=(0x3000, 0x3004), rsi=None):
    ranges = {'rdi': {'min': hex(rdi[0]), 'max': hex(rdi[1])}}
    if rsi is not None:
        ranges['rsi'] = {'min': hex(rsi[0]), 'max': hex(rsi[1])}
    return {'entry_register_ranges': ranges,
            'memory_ranges': [{'address': '0x3000', 'length': length}],
            'memory_model': 'private_ordinary_ram', 'memory_observation': observation}


def test_symbolic_store_then_load_through_a_temporary_preserves_alias_behavior():
    # Both pointer ranges include exact and partial aliases; no pointer is fixed.
    (a, am), (b, bm) = _pair('488907488b1e', '488907488b0e4889cb',
        general={'rdi': 0x3000, 'rsi': 0x3000, 'rax': 0x8877665544332211, 'rcx': 99},
        memory=bytes(16))
    contract = {**_contract(rsi=(0x3000, 0x3004)), 'live_registers': ['rbx']}
    report = compare_pe_regions(a, b, contract=contract, same_source=True,
                               baseline_memory=am, layer_memory=bm)
    assert report['status'] == 'equivalent_under_contract'
    assert report['contraction']['contract']['entry_register_ranges']['rdi'] == {
        'min': '0x3000', 'max': '0x3004'}


def test_scaled_index_and_guarded_memory_loaded_pointer_are_symbolic():
    # MOV RAX,[RDI+RSI*8], with a two-element symbolic array index.
    (a, am), (b, bm) = _pair('488b04f7', '488b0cf74889c8',
        general={'rdi': 0x3000, 'rsi': 1}, memory=bytes(range(16)))
    contract = {**_contract(rdi=(0x3000, 0x3000), rsi=(0, 1)), 'live_registers': ['rax']}
    assert compare_pe_regions(a, b, contract=contract, same_source=True,
        baseline_memory=am, layer_memory=bm)['status'] == 'equivalent_under_contract'
    # Load a pointer from RAM, then both lower and upper guards constrain the dereference.
    raw = '488b374881fe00300000720c4881fe083000007703488b0690'
    ram = (0x3008).to_bytes(8, 'little') + bytes(range(8))
    (a, am), (b, bm) = _pair(raw, raw, general={'rdi': 0x3000}, memory=ram)
    contract = _contract(rdi=(0x3000, 0x3000))
    assert compare_pe_regions(a, b, contract=contract, same_source=True,
        baseline_memory=am, layer_memory=bm)['status'] == 'equivalent_under_contract'
    raw = '488b37488b0690'  # The same observed pointer, without the protective guards.
    (a, am), (b, bm) = _pair(raw, raw, general={'rdi': 0x3000}, memory=ram)
    result = compare_pe_regions(a, b, contract=contract, same_source=True,
        baseline_memory=am, layer_memory=bm)
    assert result['status'] == 'unknown'
    assert result['safety_counterexample']['event_index'] == 1


def test_reversed_symbolic_partial_stores_have_a_replayable_alias_counterexample():
    old, new = '48890748891e', '48891e488907'
    (a, am), (b, bm) = _pair(old, new,
        general={'rdi': 0x3000, 'rsi': 0x3004, 'rax': 0, 'rbx': 0}, memory=bytes(16))
    assert am['exit'] == bm['exit']
    contract = _contract(observation='final', rsi=(0x3000, 0x3004))
    report = compare_pe_regions(a, b, contract=contract, same_source=True,
                               baseline_memory=am, layer_memory=bm)
    assert report['status'] == 'different'
    witness = report['counterexample']
    inputs = {n: int(value, 16) for n, value in witness['entry_general'].items()}
    ram = bytes(int(witness['entry_memory'][hex(0x3000 + i)], 16) for i in range(16))
    (_, old_memory), (_, new_memory) = _pair(old, new, general=inputs,
        flags=int(witness['entry_flags'], 16), memory=ram)
    assert old_memory['exit'] != new_memory['exit']


def test_reordered_disjoint_symbolic_stores_preserve_final_bytes_but_not_order():
    old, new = '48890748891e', '48891e488907'
    (a, am), (b, bm) = _pair(old, new,
        general={'rdi': 0x3000, 'rsi': 0x3010, 'rax': 1, 'rbx': 2}, memory=bytes(32))
    contract = _contract(32, rdi=(0x3000, 0x3003), rsi=(0x3010, 0x3013))
    kwargs = {'same_source': True, 'baseline_memory': am, 'layer_memory': bm}
    assert compare_pe_regions(a, b, contract=contract, **kwargs)['status'] == 'different'
    contract['memory_observation'] = 'final'
    assert compare_pe_regions(a, b, contract=contract, **kwargs)['status'] == 'equivalent_under_contract'


def test_valid_sample_does_not_hide_an_out_of_bounds_alternative_pointer():
    (a, am), (b, bm) = _pair('488907', '488907',
        general={'rdi': 0x3000, 'rax': 1}, memory=bytes(16))
    report = compare_pe_regions(a, b, contract=_contract(rdi=(0x3000, 0x3009)), same_source=True,
                               baseline_memory=am, layer_memory=bm, timeout_ms=5000)
    assert report['status'] == 'unknown'
    assert report.get('contraction') is None
    assert 'escape declared RAM' in report['reason']
    witness = report['safety_counterexample']
    assert int(witness['address'], 16) + witness['width'] > 0x3010
    assert int(witness['entry_general']['rdi'], 16) == int(witness['address'], 16)


def test_later_guard_cannot_filter_an_earlier_unsafe_store_from_the_proof():
    # Store first, then select only pointers <=0x3008. The store was already unsafe.
    raw = '4889074881ff0830000077019090'
    (a, am), (b, bm) = _pair(raw, raw,
        general={'rdi': 0x3000, 'rax': 1}, memory=bytes(16))
    report = compare_pe_regions(a, b, contract=_contract(rdi=(0x3000, 0x3010)), same_source=True,
                               baseline_memory=am, layer_memory=bm, timeout_ms=5000)
    assert report['status'] == 'unknown'
    assert report.get('contraction') is None
    assert 'escape declared RAM' in report['reason']
    witness = report['safety_counterexample']
    pointer = int(witness['entry_general']['rdi'], 16)
    assert pointer > 0x3008  # The later JA would have filtered this witness out.
    assert int(witness['address'], 16) == pointer
    assert pointer + witness['width'] > 0x3010
    assert witness['event_index'] == 0


def test_prior_guard_can_establish_safe_symbolic_memory_bounds():
    # The captured path selects RDI<=0x3008 before the 8-byte store.
    raw = '4881ff08300000770348890790'
    (a, am), (b, bm) = _pair(raw, raw,
        general={'rdi': 0x3000, 'rax': 1}, memory=bytes(16))
    report = compare_pe_regions(a, b, contract=_contract(rdi=(0x3000, 0x3010)), same_source=True,
                               baseline_memory=am, layer_memory=bm)
    assert report['status'] == 'equivalent_under_contract'


def test_observed_pointer_must_satisfy_declared_symbolic_range():
    (a, am), (b, bm) = _pair('488907', '488907',
        general={'rdi': 0x3000, 'rax': 1}, memory=bytes(16))
    report = compare_pe_regions(a, b, contract=_contract(rdi=(0x3001, 0x3004)), same_source=True,
                               baseline_memory=am, layer_memory=bm)
    assert report['status'] == 'unknown'


def test_symbolic_alias_expression_budget_prevents_unbounded_expansion():
    raw = '488907' * 17
    (a, am), (b, bm) = _pair(raw, raw,
        general={'rdi': 0x3000, 'rax': 1}, memory=bytes(256))
    report = compare_pe_regions(a, b, contract=_contract(256, rdi=(0x3000, 0x3001)), same_source=True,
                               baseline_memory=am, layer_memory=bm)
    assert report['status'] == 'unknown'
    assert any(word in report['reason'].lower() for word in ('budget', 'deadline'))


def _high_pe32_trace():
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
    cpu.mem_map(0x1000, 4096)
    cpu.mem_map(0, 4096)
    cpu.mem_map(0xfffff000, 4096)
    cpu.mem_write(0x1000, bytes.fromhex('890790'))  # MOV [EDI],EAX; exit NOP.
    cpu.reg_write(reg.UC_X86_REG_EDI, 0xfffffff8)
    cpu.reg_write(reg.UC_X86_REG_EAX, 0x11223344)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    events = []

    def before(guest, address, size, _):
        raw = bytes(guest.mem_read(address, size)).hex()
        events.append({'address': hex(address), 'project_address': hex(address), 'bytes': raw,
                       'execution_bytes': raw, 'registers': {
                           'eip': hex(address), 'eflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                           'thread': 17, 'general': {name: hex(guest.reg_read(getattr(
                               reg, 'UC_X86_REG_' + name.upper()))) for name in
                               register_names(32) - {'eip', 'eflags'}}}})

    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(0x1000, 0x1003, count=2)
    normalize_trace('wine-qemu', events, version=1)
    trace = {'mapping': {'backend': 'wine-qemu', 'bits': 32, 'source_sha256': 'a' * 64,
                         'version_sha256': 'b' * 64},
             'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}
    memory = {'entry': [{'address': '0x0', 'hex': '00' * 8},
                        {'address': '0xfffffff8', 'hex': '00' * 8}],
              'exit': [{'address': '0x0', 'hex': bytes(cpu.mem_read(0, 8)).hex()},
                       {'address': '0xfffffff8', 'hex': bytes(cpu.mem_read(0xfffffff8, 8)).hex()}]}
    return trace, memory


def test_memory_span_cannot_wrap_between_separately_declared_high_and_low_bytes():
    trace, evidence = _high_pe32_trace()
    contract = {'entry_register_ranges': {'edi': {'min': '0xfffffff8', 'max': '0xffffffff'}},
                'memory_ranges': [{'address': '0x0', 'length': 8},
                                  {'address': '0xfffffff8', 'length': 8}],
                'memory_model': 'private_ordinary_ram'}
    report = compare_pe_regions(trace, trace, contract=contract, same_source=True,
                               baseline_memory=evidence, layer_memory=evidence, timeout_ms=5000)
    assert report['status'] == 'unknown'
    assert report.get('contraction') is None
    assert 'escape declared RAM' in report['reason']
    witness = report['safety_counterexample']
    assert int(witness['address'], 16) + witness['width'] > 1 << 32
