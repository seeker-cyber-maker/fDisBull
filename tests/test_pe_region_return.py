"""Bounded near returns consume declared stack RAM and preserve caller state."""
from copy import deepcopy
import time

import pytest

z3 = pytest.importorskip('z3')

from fdisbull.debug_semantics import normalize_trace, PE_TRACE_SEMANTICS
from fdisbull.pe_region_equivalence import (
    _contract, _execute, _snapshots, compare_pe_regions, expand_pe_contraction)
from fdisbull.wine_arch import register_names


STACK_START, STACK_SIZE, STACK_POINTER, CALLER = 0x3060, 40, 0x3080, 0x1800


def _capture(code, *, bits=64, stack_data=None):
    """Record real Unicorn steps through RET to a stopped caller boundary."""
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86,
                     unicorn.UC_MODE_64 if bits == 64 else unicorn.UC_MODE_32)
    cpu.mem_map(0x1000, 4096)
    cpu.mem_write(0x1000, bytes.fromhex(code))
    cpu.mem_write(CALLER, b'\x90')
    cpu.mem_map(0x3000, 4096)
    memory = bytearray(bytes(STACK_SIZE) if stack_data is None else stack_data)
    width = bits // 8
    offset = STACK_POINTER - STACK_START
    memory[offset:offset + width] = CALLER.to_bytes(width, 'little')
    cpu.mem_write(STACK_START, bytes(memory))
    ip, flags, stack = ('rip', 'rflags', 'rsp') if bits == 64 else ('eip', 'eflags', 'esp')
    names = register_names(bits) - {ip, flags}
    cpu.reg_write(getattr(reg, 'UC_X86_REG_' + stack.upper()), STACK_POINTER)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x8d7)
    cpu.reg_write(reg.UC_X86_REG_EBX, 0x76543210)
    events = []

    def before(guest, address, size, _):
        raw = bytes(guest.mem_read(address, size)).hex()
        events.append({'address': hex(address), 'project_address': hex(address),
            'bytes': raw, 'execution_bytes': raw,
            'registers': {ip: hex(address), flags: hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                'thread': 71, 'general': {name: hex(guest.reg_read(getattr(
                    reg, 'UC_X86_REG_' + name.upper()))) for name in names}}})
        if address == CALLER:
            guest.emu_stop()

    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(0x1000, 0x2000, count=32)
    assert events[-1]['address'] == hex(CALLER)
    normalize_trace('wine-qemu', events, version=1)
    events[-1]['observation'].update(instruction_completed=False,
                                    evidence='Caller boundary captured before execution')
    trace = {'mapping': {'backend': 'wine-qemu', 'bits': bits,
                         'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64,
                         'capture_provider': 'unicorn'},
             'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}
    evidence = {'entry': [{'address': hex(STACK_START), 'hex': bytes(memory).hex()}],
                'exit': [{'address': hex(STACK_START),
                          'hex': bytes(cpu.mem_read(STACK_START, STACK_SIZE)).hex()}]}
    contract = {'entry_registers': {stack: hex(STACK_POINTER)},
                'memory_model': 'private_ordinary_ram',
                'memory_ranges': [{'address': hex(STACK_START), 'length': STACK_SIZE}]}
    return trace, evidence, contract


def _compare(trace, evidence, contract, *, layer=None, layer_memory=None):
    return compare_pe_regions(trace, trace if layer is None else layer,
        contract=contract, same_source=True, baseline_memory=evidence,
        layer_memory=evidence if layer_memory is None else layer_memory)


@pytest.mark.parametrize('bits', [32, 64])
def test_ret_reads_pointer_width_stack_bytes_and_advances_stack(bits):
    trace, evidence, contract = _capture('c3', bits=bits)
    stack = 'rsp' if bits == 64 else 'esp'
    assert int(trace['events'][-1]['registers']['general'][stack], 16) == STACK_POINTER + bits // 8
    assert trace['events'][0]['registers']['general'] | {stack: hex(STACK_POINTER + bits // 8)} == trace['events'][-1]['registers']['general']
    assert trace['events'][0]['registers']['rflags' if bits == 64 else 'eflags'] == trace['events'][-1]['registers']['rflags' if bits == 64 else 'eflags']
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'equivalent_under_contract', result
    reads = result['contraction']['reduced_effects']['ordered_accesses']
    assert len(reads) == 1 and reads[0]['kind'] == 'read' and reads[0]['width'] == bits // 8
    # The return slot remains symbolic by default, conditioned on this caller.
    assert 'entry_ram_' in result['contraction']['reduced_effects']['path_domain']
    expanded = expand_pe_contraction(result['contraction'], trace, trace,
                                    baseline_memory=evidence, layer_memory=evidence)
    assert expanded['baseline'] == trace and expanded['baseline_memory'] == evidence


def test_frame_spill_reload_and_ret_keep_ordered_stack_effects():
    trace, evidence, contract = _capture('4883ec2048891c2448c7c300000000488b1c244883c420c3')
    assert trace['events'][0]['registers']['general']['rbx'] == trace['events'][-1]['registers']['general']['rbx']
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'equivalent_under_contract', result
    accesses = result['contraction']['reduced_effects']['ordered_accesses']
    assert [(a['kind'], a['width']) for a in accesses] == [('write', 8), ('read', 8), ('read', 8)]
    # The frame's saved bytes are retained as memory effects, even after return.
    assert evidence['exit'] != evidence['entry']
    normalized, addresses, names = _contract(contract, 64)
    initial = {n: z3.BitVec('entry_' + n, 64) for n in names}
    memory = {a: z3.BitVec(f'entry_ram_{a:x}', 8) for a in addresses}
    modeled = _execute(z3, trace, 64, initial, z3.BitVec('entry_flags', 32), memory,
                       normalized, _snapshots(evidence, addresses), 'test', time.monotonic() + 5)
    assert len(modeled['returns']) == 1
    returned = modeled['returns'][0]
    assert returned['event_index'] == len(trace['events']) - 2 and returned['width'] == 8
    assert z3.simplify(returned['stack_address']).as_long() == STACK_POINTER
    assert z3.is_bv(returned['target']) and returned['target'].size() == 64


def test_entry_memory_fixes_only_declared_bytes_not_the_whole_sample():
    left, evidence, contract = _capture('488b4424f8c3')  # Load caller data before the return slot.
    right, right_memory, _ = _capture('48c7c000000000c3')
    contract.update(memory_observation='final', entry_memory=[{
        'address': hex(STACK_POINTER), 'hex': CALLER.to_bytes(8, 'little').hex()}])
    assert left['events'][-1]['registers']['general']['rax'] == right['events'][-1]['registers']['general']['rax'] == '0x0'
    original = deepcopy((left, right, evidence, right_memory, contract))
    result = _compare(left, evidence, contract, layer=right, layer_memory=right_memory)
    assert result['status'] == 'different', result
    assert 'rax' in result['counterexample']['differing_live_registers']
    for offset, byte in enumerate(CALLER.to_bytes(8, 'little')):
        assert int(result['counterexample']['entry_memory'][hex(STACK_POINTER + offset)], 16) == byte
    # Pinning the separate data word now justifies the equality.
    contract['entry_memory'].append({'address': hex(STACK_POINTER - 8), 'hex': '00' * 8})
    assert _compare(left, evidence, contract, layer=right,
                    layer_memory=right_memory)['status'] == 'equivalent_under_contract'
    assert (left, right, evidence, right_memory) == original[:4]


@pytest.mark.parametrize('corruption', ['successor', 'stack_pointer', 'entry_slot', 'exit_memory'])
def test_ret_rejects_contradictory_successor_stack_or_ram_evidence(corruption):
    trace, evidence, contract = _capture('c3')
    if corruption == 'successor':
        event = trace['events'][-1]
        event['address'] = event['project_address'] = event['registers']['rip'] = hex(CALLER + 1)
        event['identity']['runtime_address'] = event['identity']['project_address'] = hex(CALLER + 1)
    elif corruption == 'stack_pointer':
        trace['events'][-1]['registers']['general']['rsp'] = hex(STACK_POINTER + 16)
    else:
        stage = 'entry' if corruption == 'entry_slot' else 'exit'
        raw = bytearray.fromhex(evidence[stage][0]['hex'])
        raw[STACK_POINTER - STACK_START] ^= 1
        evidence[stage][0]['hex'] = raw.hex()
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'unknown', result
    assert result.get('contraction') is None


def test_entry_memory_assumption_must_agree_with_captured_entry():
    trace, evidence, contract = _capture('c3')
    contract['entry_memory'] = [{'address': hex(STACK_POINTER), 'hex': 'ff'}]
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'unknown', result
    assert 'fixed-memory assumptions' in result['reason']


@pytest.mark.parametrize('entry', [
    [{'address': '0x5000', 'hex': '00'}],
    [{'address': '0x3080', 'hex': '0000'}, {'address': '0x3081', 'hex': '00'}],
    [{'address': '0x3080', 'hex': ''}],
    [{'address': '0x3080', 'hex': 'gg'}],
    [{'address': 0x3080, 'hex': '00'}],
])
def test_entry_memory_requires_bounded_nonoverlapping_declared_bytes(entry):
    trace, evidence, contract = _capture('c3')
    contract['entry_memory'] = entry
    with pytest.raises(ValueError):
        _compare(trace, evidence, contract)


def test_symbolic_stack_still_requires_safety_before_the_return_guard():
    trace, evidence, contract = _capture('c3')
    contract['entry_registers'] = {}
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'unknown', result
    assert 'escape declared RAM' in result['reason']
    assert result.get('safety_counterexample')


@pytest.mark.parametrize('code', ['c20800', 'cb', 'ca0800'])
def test_ret_immediate_and_far_returns_are_not_admitted(code):
    if code == 'c20800':
        trace, evidence, contract = _capture(code)
    else:
        # Tamper a real near-return trace to ensure unsupported far-return bytes
        # cannot inherit its completed near-return meaning.
        trace, evidence, contract = _capture('c3')
        trace['events'][0]['bytes'] = trace['events'][0]['execution_bytes'] = code
    result = _compare(trace, evidence, contract)
    assert result['status'] == 'unknown', result
    assert result.get('contraction') is None
