"""A changed path can have the same admitted register transfer."""
from copy import deepcopy

import pytest

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_path_transfer import compare_pe_register_paths
from fdisbull.wine_arch import register_names


def _event(address, code, rax, *, rbx=7, rcx=9, flags=0x202, thread=17):
    general = {name: '0x0' for name in register_names(64) - {'rip', 'rflags'}}
    general.update(rax=hex(rax), rbx=hex(rbx), rcx=hex(rcx))
    return {'address': hex(address), 'project_address': hex(address), 'bytes': code,
            'registers': {'rip': hex(address), 'rflags': hex(flags),
                          'general': general, 'thread': thread}}


def _trace(events, *, source='a' * 64, version='b' * 64, bits=64):
    normalize_trace('wine-qemu', events, version=1)
    return {'mapping': {'backend': 'wine-qemu', 'bits': bits,
                        'source_sha256': source, 'version_sha256': version},
            'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}


def test_two_mov_encodings_have_one_admitted_register_transfer():
    baseline = _trace([_event(0x100, '4889d8', 0), _event(0x103, '90', 7)])
    layer = _trace([_event(0x100, '488bc3', 0), _event(0x103, '90', 7)])
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['status'] == 'compared'
    assert result['topology']['code_difference'] is True
    assert result['register_transfer'] == 'equal'
    assert result['baseline']['transfer']['rax'] == 'rbx'
    assert result['sampled_entry_state_equal'] is True
    assert result['sampled_exit_state_equal'] is True
    assert result['path_guards'] == 'uncompared'
    assert result['semantic_equivalence'] is None


def test_pe32_full_width_mov_encodings_share_a_transfer():
    general = {name: '0x0' for name in register_names(32) - {'eip', 'eflags'}}
    general['ebx'] = '0x7'

    def event(address, code, eax):
        return {'address': hex(address), 'project_address': hex(address), 'bytes': code,
                'registers': {'eip': hex(address), 'eflags': '0x202', 'thread': 17,
                              'general': {**general, 'eax': hex(eax)}}}

    baseline = _trace([event(0x401000, '89d8', 0), event(0x401002, '90', 7)], bits=32)
    layer = _trace([event(0x401000, '8bc3', 0), event(0x401002, '90', 7)], bits=32)
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['status'] == 'compared'
    assert result['register_transfer'] == 'equal'
    assert result['baseline']['transfer']['eax'] == 'ebx'


def test_dead_detour_write_is_removed_only_after_common_overwrite():
    baseline = _trace([_event(0x100, '7503', 0),
                       _event(0x105, '4889d8', 0),
                       _event(0x108, '90', 7)])
    layer = _trace([_event(0x100, 'eb00', 0),
                    _event(0x102, '4889c8', 0),
                    _event(0x105, '4889d8', 9),
                    _event(0x108, '90', 7)])
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['status'] == 'compared'
    assert result['topology']['control_flow_difference'] is True
    assert result['register_transfer'] == 'equal'
    assert result['layer']['dead_write_events'] == [1]
    assert result['baseline']['dead_write_events'] == []
    assert result['layer']['branch_events'] == [{'event_index': 0, 'conditional': False}]
    assert result['baseline']['branch_events'] == [{'event_index': 0, 'conditional': True}]
    assert result['semantic_equivalence'] is None  # The branch guards differ.


def test_distinct_live_register_transfer_is_reported():
    baseline = _trace([_event(0x100, '4889d8', 0), _event(0x103, '90', 7)])
    layer = _trace([_event(0x100, '4889c8', 0), _event(0x103, '90', 9)])
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['register_transfer'] == 'different'
    assert result['baseline']['transfer']['rax'] == 'rbx'
    assert result['layer']['transfer']['rax'] == 'rcx'


def test_equal_transfer_does_not_hide_different_entry_values():
    baseline = _trace([_event(0x100, '4889d8', 0, rbx=7),
                       _event(0x103, '90', 7, rbx=7)])
    layer = _trace([_event(0x100, '4889d8', 0, rbx=8),
                    _event(0x103, '90', 8, rbx=8)])
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['register_transfer'] == 'equal'
    assert result['sampled_entry_state_equal'] is False
    assert result['sampled_exit_state_equal'] is False
    assert result['semantic_equivalence'] is None


def test_memory_operand_and_undeclared_state_change_remain_unknown():
    baseline = _trace([_event(0x100, '4889d8', 0), _event(0x103, '90', 7)])
    memory = _trace([_event(0x100, '488b03', 0), _event(0x103, '90', 7)])
    assert compare_pe_register_paths(baseline, memory, same_source=True)['status'] == 'unknown'
    drift = deepcopy(baseline)
    drift['events'][1]['registers']['general']['rcx'] = '0xa'
    assert compare_pe_register_paths(baseline, drift, same_source=True)['status'] == 'unknown'
    broken_next = deepcopy(baseline)
    broken_next['events'][1]['address'] = '0x104'
    broken_next['events'][1]['project_address'] = '0x104'
    broken_next['events'][1]['identity']['runtime_address'] = '0x104'
    broken_next['events'][1]['identity']['project_address'] = '0x104'
    broken_next['events'][1]['registers']['rip'] = '0x104'
    assert compare_pe_register_paths(baseline, broken_next, same_source=True)['status'] == 'unknown'


def test_write_read_by_later_mov_is_live():
    events = [_event(0x100, '4889c8', 0), _event(0x103, '4889c2', 9),
              _event(0x106, '4889d8', 9), _event(0x109, '90', 7)]
    events[2]['registers']['general']['rdx'] = '0x9'
    events[3]['registers']['general']['rdx'] = '0x9'
    trace = _trace(events)
    result = compare_pe_register_paths(trace, trace, same_source=True)
    assert result['status'] == 'compared'
    assert result['baseline']['dead_write_events'] == []
    assert result['baseline']['transfer']['rdx'] == 'rcx'


def test_source_identity_and_path_correspondence_are_required():
    baseline = _trace([_event(0x100, '4889d8', 0), _event(0x103, '90', 7)])
    other = _trace([_event(0x100, '4889d8', 0), _event(0x103, '90', 7)], source='c' * 64)
    with pytest.raises(ValueError, match='matching byte identities'):
        compare_pe_register_paths(baseline, other, same_source=True)
    assert compare_pe_register_paths(baseline, other)['status'] == 'unknown'
    other['events'][0]['observation']['instruction_completed'] = None
    assert compare_pe_register_paths(baseline, other)['status'] == 'unknown'


def test_dead_detour_transfer_matches_independent_unicorn_execution():
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const

    def run(code):
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        cpu.mem_map(0x1000, 0x1000)
        cpu.mem_write(0x1000, bytes.fromhex(code))
        for register, value in ((x86_const.UC_X86_REG_RAX, 0),
                                (x86_const.UC_X86_REG_RBX, 7),
                                (x86_const.UC_X86_REG_RCX, 9),
                                (x86_const.UC_X86_REG_EFLAGS, 0x202)):
            cpu.reg_write(register, value)
        events = []

        def before(guest, address, size, _):
            events.append(_event(address, bytes(guest.mem_read(address, size)).hex(),
                                 guest.reg_read(x86_const.UC_X86_REG_RAX),
                                 rbx=guest.reg_read(x86_const.UC_X86_REG_RBX),
                                 rcx=guest.reg_read(x86_const.UC_X86_REG_RCX),
                                 flags=guest.reg_read(x86_const.UC_X86_REG_EFLAGS)))

        cpu.hook_add(unicorn.UC_HOOK_CODE, before)
        cpu.emu_start(0x1000, 0x1009, count=4)
        return _trace(events)

    baseline = run('75039090904889d890')
    layer = run('eb004889c84889d890')
    assert [event['address'] for event in baseline['events']] == ['0x1000', '0x1005', '0x1008']
    assert [event['address'] for event in layer['events']] == ['0x1000', '0x1002', '0x1005', '0x1008']
    result = compare_pe_register_paths(baseline, layer, same_source=True)
    assert result['register_transfer'] == 'equal'
    assert result['layer']['dead_write_events'] == [1]
