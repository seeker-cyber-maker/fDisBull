"""Segmented decoding and conservative DOS register facts, without execution."""
import pytest

from fdisbull.dos_decoder import decode_dos


def decoded(hex_bytes, *, ip=0x100, cs=0x1000, state=None):
    return decode_dos(bytes.fromhex(hex_bytes), (cs << 4) + ip, cs, state)


def test_near_branch_offsets_wrap_inside_the_original_cs():
    ins = decoded('eb00', ip=0xfffe, cs=0x2345)
    assert ins['ip'] == 0xfffe and ins['cs'] == 0x2345
    assert ins['target'] == ins['next_address'] == 0x23450
    assert ins['target_cs'] == 0x2345 and not ins['far']
    assert decoded('e8fdff', ip=0x100)['target'] == 0x10100
    assert decoded('90', ip=0xffff)['next_address'] == 0x10000


def test_far_call_uses_relocated_selector_and_preserves_caller_edge_state():
    state = {'dx': 0x4020, 'ds': 0x4020, 'sp': 0x80}
    ins = decoded('9afd53ff38', state=state)
    assert ins['flow'] == 'call' and ins['far']
    assert ins['target_cs'] == 0x38ff
    assert ins['target'] == 0x3e3ed
    assert ins['references'] == [{'operand_index': 0, 'role': 'code', 'target': 0x3e3ed, 'width': 4}]
    assert ins['next_registers'] == state
    assert state == {'dx': 0x4020, 'ds': 0x4020, 'sp': 0x80}


def test_out_of_range_far32_offsets_remain_unresolved():
    ins = decoded('66ea785634120010')
    assert ins['flow'] == 'jump' and ins['far']
    assert ins['target'] is None and ins['target_cs'] is None
    assert ins['unresolved'] and not ins['references']


def test_ds_cs_override_and_bp_default_ss_are_distinct():
    state = {'ds': 0x4020, 'ss': 0x5000, 'bp': 0xfffe}
    assert decoded('a13412', state=state)['data_refs'] == [0x41434]
    assert decoded('2ea13412', state=state)['data_refs'] == [0x11234]
    # BP+4 wraps the effective offset to 2, then SS supplies the segment.
    assert decoded('8b4604', state=state)['data_refs'] == [0x50002]
    assert decoded('268b4604', state={**state, 'es': 0x3000})['data_refs'] == [0x30002]


def test_unknown_index_or_segment_does_not_create_a_flat_reference():
    unknown_index = decoded('8b00', state={'ds': 0x4020, 'bx': 0x10})  # [bx+si]
    assert unknown_index['data_refs'] == [] and unknown_index['unresolved']
    unknown_ds = decoded('a13412')
    assert unknown_ds['data_refs'] == [] and any('segment ds' in x for x in unknown_ds['unresolved'])
    unknown_eax = decoded('678b00', state={'ds': 0x4020, 'ax': 4})
    assert unknown_eax['data_refs'] == [] and unknown_eax['unresolved']


def test_actual_relocated_dinopark_startup_retains_dx_across_version_interrupt():
    # First 0x16 bytes of the original entry, after the known DOS relocation.
    code = bytes.fromhex('ba20402e89169102b430cd218b2e02008b1e2c008eda')
    address = 0x10000
    state = {}
    observed = []
    while code:
        ins = decode_dos(code, address, 0x1000, state)
        observed.append(ins)
        state, address = ins['next_registers'], ins['next_address']
        code = code[ins['size']:]
    assert observed[1]['data_refs'] == [0x10291]
    assert observed[2]['next_registers']['ah'] == 0x30
    assert observed[3]['next_registers']['dx'] == 0x4020
    assert state['ds'] == 0x4020
    assert 'ax' not in state and 'bx' not in state and 'cx' not in state


def test_simple_transfers_wrap_and_partial_unknown_writes_invalidate_aliases():
    assert decoded('b83412')['next_registers']['ax'] == 0x1234
    assert decoded('8eda', state={'dx': 0x4020})['next_registers']['ds'] == 0x4020
    assert decoded('31c0', state={'ax': 42})['next_registers']['ax'] == 0
    assert decoded('83c001', state={'ax': 0xffff})['next_registers']['ax'] == 0
    assert decoded('83e801', state={'ax': 0})['next_registers']['ax'] == 0xffff
    assert decoded('83c0ff', state={'ax': 2})['next_registers']['ax'] == 1
    after = decoded('8ae3', state={'ax': 0x1234, 'dx': 7})['next_registers']  # mov ah,bl
    assert 'ax' not in after and 'ah' not in after and after['dx'] == 7
    after32 = decoded('668b07', state={'ax': 0x1234, 'ds': 0x4020})['next_registers']
    assert 'ax' not in after32


def test_lea_computes_an_offset_without_requiring_a_known_data_segment():
    ins = decoded('8d4704', state={'bx': 0xfffe})
    assert ins['next_registers']['ax'] == 2
    assert not ins['data_refs']


def test_far_indirect_descriptor_preserves_offset_selector_distinction():
    far_call = decoded('ff1e3412', state={'ds': 0x4020})
    assert far_call['flow'] == 'indirect_call' and far_call['far']
    assert far_call['target'] is None and far_call['target_cs'] is None
    assert far_call['indirect'] == {'pointer_address': 0x41434, 'offset_size': 2, 'far': True, 'kind': 'call'}
    near_call = decoded('ff163412', state={'ds': 0x4020})
    assert near_call['indirect']['far'] is False
    assert near_call['indirect']['offset_size'] == 2
    assert near_call['references'][0]['width'] == 2
    far_jump = decoded('ff2e3412', state={'ds': 0x4020})
    assert far_jump['indirect']['kind'] == 'jump'


def test_lds_les_require_caller_memory_and_invalidate_old_target_values():
    state = {'ds': 0x4020, 'es': 0x2000, 'bx': 0x1234}
    ins = decoded('c41e3412', state=state)
    assert ins['load_far'] == {'linear': 0x41434, 'width': 4, 'register': 'bx', 'segment_register': 'es', 'offset_size': 2}
    assert 'es' not in ins['next_registers'] and 'bx' not in ins['next_registers']
    assert ins['next_registers']['ds'] == 0x4020
    assert ins['unresolved']


def test_push_pop_expose_explicit_effects_without_inventing_stack_memory():
    push = decoded('0e', cs=0x2345, state={'sp': 2})
    assert push['push_value'] == 0x2345 and push['next_registers']['sp'] == 0
    pop = decoded('1f', state={'ds': 0x4020, 'sp': 0xfffe})
    assert pop['pop_register'] == 'ds'
    assert 'ds' not in pop['next_registers'] and pop['next_registers']['sp'] == 0


def test_unknown_interrupt_policy_is_explicit_and_dos_termination_stops():
    state = {'ax': 0x0900, 'dx': 0x1234, 'ds': 0x4020, 'es': 0x2000, 'ss': 0x5000}
    ins = decoded('cd21', state=state)
    assert ins['next_registers'] == {'ds': 0x4020, 'es': 0x2000, 'ss': 0x5000}
    assert any('assumption' in note for note in ins['unresolved'])
    assert decoded('cd21', state={'ah': 0x4c})['flow'] == 'stop'
    assert decoded('cd20')['flow'] == 'stop'


def test_segment_boundary_and_invalid_bytes_are_not_decoded_flat():
    assert decoded('e90000', ip=0xffff) is None
    assert decoded('0f', ip=0x100) is None
    with pytest.raises(ValueError, match='outside'):
        decode_dos(b'\x90', 0x20000, 0x1000)
    with pytest.raises(ValueError, match='CS'):
        decode_dos(b'\x90', 0, 0x10000)
    assert decoded('cb')['far'] and decoded('cb')['flow'] == 'return'


def test_pop_sp_and_32bit_stack_values_do_not_create_false_16bit_constants():
    pop = decoded('5c', state={'sp': 0x100})
    assert pop['pop_register'] == 'sp' and 'sp' not in pop['next_registers']
    push32 = decoded('666878563412', state={'sp': 0x100})
    assert push32['push_value'] is None and push32['push_width'] == 4
    assert push32['next_registers']['sp'] == 0xfc
    assert push32['unresolved']


@pytest.mark.parametrize('code', ['bc0002', '83c402', '8ed0', '8946fe', '666878563412', '6658', '5c', '17', '8f4600'])
def test_unmodeled_stack_changes_explicitly_invalidate_abstract_stack(code):
    ins = decoded(code, state={'sp': 0x100, 'ss': 0x5000, 'bp': 0x100, 'ax': 0x1234})
    assert ins['stack_reset'] is True
    assert any('abstract stack' in note for note in ins['unresolved'])


def test_modeled_word_stack_operations_preserve_push_pop_transfer():
    push = decoded('0e', cs=0x2345, state={'sp': 0x100, 'ss': 0x5000})
    pop = decoded('1f', state={'sp': 0x100, 'ss': 0x5000})
    unknown_push = decoded('ff36a000', state={'sp': 0x100, 'ss': 0x5000, 'ds': 0x4020})
    assert push['stack_reset'] is False and push['push_value'] == 0x2345
    assert push['next_registers']['sp'] == 0xFE
    assert pop['stack_reset'] is False and pop['pop_register'] == 'ds'
    assert pop['next_registers']['sp'] == 0x102
    assert unknown_push['stack_reset'] is False and unknown_push['push_value'] is None


def test_stack_alias_writes_reset_but_known_disjoint_data_write_does_not():
    alias = decoded('a30001', state={'ds': 0x5000, 'ss': 0x5000, 'sp': 0x100})
    data = decoded('a30001', state={'ds': 0x4000, 'ss': 0x5000, 'sp': 0x100})
    unknown = decoded('8907', state={'ss': 0x5000, 'sp': 0x100})
    assert alias['stack_reset'] is True
    assert data['stack_reset'] is False
    assert unknown['stack_reset'] is True


@pytest.mark.parametrize('code,adjustment', [
    ('e80100', -2), ('66e801000000', -4), ('9a00000010', -4), ('669a000000000010', -8)])
def test_native_call_stack_adjustment_preserves_operand_size(code, adjustment):
    ins = decoded(code, state={'sp': 32})
    assert ins['flow'] == 'call'
    assert ins['call_stack_adjust'] == adjustment
    assert ins['next_registers']['sp'] == 32  # caller policy remains outside decoder
