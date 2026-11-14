"""A finite path cover recovers a returning leaf's branch and RAM behavior."""
from copy import deepcopy

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.wine_arch import register_names


STACK, OUT, RETURN = 0x8008, 0x3000, 0x1100


def _code(key, wide=False):
    # uint64 F(uint64 x, uint64 *out): x<=10 => *out=x+key, return x+key;
    # otherwise return UINT64_MAX without touching out. RBX is spilled/restored.
    constant = (b'\x48\xb8' + key.to_bytes(8, 'little') if wide else
                b'\xb8' + key.to_bytes(4, 'little') + b'\x90' * 5)
    return (bytes.fromhex('4883ec1048895c24084889cb4883f90a7712') + constant +
            bytes.fromhex('4801c8488902eb0748c7c0ffffffff488b5c24084883c410c3'))


def _contract():
    return {'entry_registers': {'rsp': hex(STACK), 'rdx': hex(OUT)},
            'memory_model': 'private_ordinary_ram',
            'memory_ranges': [{'address': hex(OUT), 'length': 8},
                              {'address': hex(STACK - 8), 'length': 16}],
            'entry_memory': [{'address': hex(STACK), 'hex': RETURN.to_bytes(8, 'little').hex()}]}


def _path(key, x, wide=False, *, code=None):
    import unicorn
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for address in (0x1000, OUT, 0x7000, 0x8000):
        cpu.mem_map(address, 4096)
    cpu.mem_write(0x1000, _code(key, wide) if code is None else code)
    cpu.mem_write(RETURN, b'\x90')
    cpu.mem_write(STACK, RETURN.to_bytes(8, 'little'))
    cpu.mem_write(STACK - 8, bytes.fromhex('1122334455667788'))
    cpu.mem_write(OUT, bytes.fromhex('8877665544332211'))
    initial = {'rax': 0xfedcba9876543210, 'rbx': 0xaabbccddeeff0011,
               'rcx': x, 'rdx': OUT, 'rsp': STACK}
    for name, value in initial.items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), value)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    def memory():
        return [{'address': r['address'], 'hex': bytes(cpu.mem_read(int(r['address'], 16), r['length'])).hex()}
                for r in _contract()['memory_ranges']]
    entry = memory()
    events = []
    def before(guest, address, size, _):
        events.append({'address': hex(address), 'project_address': hex(address),
                       'bytes': bytes(guest.mem_read(address, size)).hex(),
                       'registers': {'rip': hex(address),
                         'rflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)), 'thread': 17,
                         'general': {n: hex(guest.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                     for n in register_names(64) - {'rip', 'rflags'}}}})
    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(0x1000, RETURN + 1, count=64)
    normalize_trace('wine-qemu', events, version=1)
    return {'trace': {'mapping': {'backend': 'wine-qemu', 'bits': 64,
                      'capture_provider': 'independent-unicorn',
                      'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64},
                     'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'complete': True, 'events': events},
            'memory': {'entry': entry, 'exit': memory()}}


def _family(key, wide=False):
    return [_path(key, 3, wide), _path(key, 11, wide)]


def test_whole_leaf_recovers_both_paths_and_real_changed_memory():
    from fdisbull.pe_function_recovery import compare_pe_functions
    result = compare_pe_functions(_family(1), _family(2), contract=_contract())
    assert result['status'] == 'different', result
    assert all(v['status'] == 'complete' for v in result['coverage'].values())
    witness = result['counterexample']
    assert 'rax' in witness['differing_live_registers']
    assert witness['differing_memory_bytes']
    assert int(witness['entry_general']['rcx'], 16) <= 10
    assert result['baseline_recovery']['call_frame']['stack_pointer_delta'] == 8
    assert result['baseline_recovery']['call_frame']['return_target'] == hex(RETURN)


def test_wider_encoding_reduces_complete_function_and_expands_exact_paths():
    from fdisbull.pe_function_recovery import compare_pe_functions, expand_pe_function_contraction
    a, b = _family(2), _family(2, True)
    frozen = deepcopy((a, b))
    result = compare_pe_functions(a, b, contract=_contract())
    assert result['status'] == 'equivalent_under_contract', result
    assert result['baseline_recovery']['termination_bound_instructions'] == 17
    assert result['layer_recovery']['termination_bound_instructions'] == 12
    effects = result['baseline_recovery']['cases']
    assert sorted(len(c['ordered_accesses']) for c in effects) == [3, 4]
    assert expand_pe_function_contraction(result['contraction'], a, b) == {'baseline': a, 'layer': b}
    assert (a, b) == frozen


def test_missing_branch_leaves_an_uncovered_input_witness():
    from fdisbull.pe_function_recovery import compare_pe_functions
    result = compare_pe_functions(_family(2)[:1], _family(2), contract=_contract())
    assert result['status'] == 'incomplete_path_coverage', result
    assert int(result['coverage']['baseline']['counterexample']['entry_general']['rcx'], 16) > 10
    assert result['contraction'] is None


def test_return_word_must_be_an_explicit_call_frame_assumption():
    from fdisbull.pe_function_recovery import compare_pe_functions
    contract = _contract()
    contract.pop('entry_memory')
    result = compare_pe_functions(_family(2), _family(2), contract=contract)
    assert result['status'] == 'unknown', result
    assert 'return word' in result['reason']


def test_different_epochs_cannot_be_mixed_into_one_function():
    from fdisbull.pe_function_recovery import compare_pe_functions
    mixed = [_path(1, 3), _path(2, 3)]
    result = compare_pe_functions(mixed, _family(2), contract=_contract())
    assert result['status'] == 'unknown' and 'inconsistent code' in result['reason']


def test_wrong_post_return_stack_and_code_alias_stay_unknown():
    from fdisbull.pe_function_recovery import compare_pe_functions
    a = _family(2)
    a[0]['trace']['events'][-1]['registers']['general']['rsp'] = hex(STACK + 16)
    result = compare_pe_functions(a, _family(2), contract=_contract())
    assert result['status'] == 'unknown' and 'contradict' in result['reason']
    contract = _contract()
    contract['memory_ranges'].append({'address': '0x1000', 'length': 8})
    result = compare_pe_functions(_family(2), _family(2), contract=contract)
    assert result['status'] == 'unknown' and 'overlaps captured code' in result['reason']


def test_changed_guard_compares_cross_branch_intersections():
    from fdisbull.pe_function_recovery import compare_pe_functions
    changed = _code(2).replace(bytes.fromhex('4883f90a'), bytes.fromhex('4883f90b'))
    layer = [_path(2, 3, code=changed), _path(2, 12, code=changed)]
    result = compare_pe_functions(_family(2), layer, contract=_contract())
    assert result['status'] == 'different', result
    witness = result['counterexample']
    assert witness['baseline_path'] == 1 and witness['layer_path'] == 0
    assert int(witness['entry_general']['rcx'], 16) == 11
    assert witness['memory_access_counts'] == {'baseline': 3, 'layer': 4}


def test_recovery_matches_independent_known_source_specification():
    from fdisbull.pe_function_recovery import compare_pe_functions
    from test_smc_function_wine import _verify_source_spec
    result = compare_pe_functions(_family(2), _family(2, True), contract=_contract())
    for name in ('baseline_recovery', 'layer_recovery'):
        assert _verify_source_spec(result[name], 2, _contract())['status'] == 'proved_under_entry_contract'
