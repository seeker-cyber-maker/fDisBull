"""KINT6 processor boundaries, snapshots, and honest control-flow facts.

These are authored vectors, never Sherlock bytes. Independent assembler-wide
acceptance vectors are tested separately in test_kint6_vectors.py.
"""
import pytest

from fdisbull.kint6_processor import KINT6Processor
from fdisbull.processor import Location, decode_instruction


def image(code=bytes.fromhex('14020000')):
    """Build a minimal authored envelope with a fixed event entry at 0x200."""
    raw = bytearray(512)
    raw[:8] = bytes.fromhex('efcdab8967452301')
    raw[0xD0:0xD6] = b'KINT6\0'
    raw[0xE0:0xE8] = (512 + len(code)).to_bytes(8, 'little')
    raw[0xE8:0xF0] = (64).to_bytes(8, 'little')
    raw[0xF0:0xF8] = (4096).to_bytes(8, 'little')
    raw[0xF8:0x100] = (4096).to_bytes(8, 'little')
    return bytes(raw) + code


def decoded(hex_bytes):
    processor = KINT6Processor(image(bytes.fromhex(hex_bytes)))
    result = decode_instruction(processor, processor.program,
                                Location(processor.info.address_space, 512))
    return processor, result


def test_qword_raw_operand_and_instruction_span_are_retained():
    processor, result = decoded('767e0000887766554433221114020000')
    assert result.facts['mnemonic'] == 'mov'
    assert result.facts['width_bits'] == 64
    assert result.facts['size'] == 12
    assert result.facts['bytes'] == '767e00008877665544332211'
    assert result.facts['operands'][0]['number'] == 3
    assert result.facts['operands'][1]['encoded_value'] == 0x1122334455667788
    assert result.facts['operands'][1]['encoded_bits'] == 64
    assert result.facts['file_offset'] == result.facts['guest_offset'] == 512
    assert result.facts['runtime_execution'] is False
    assert result.successors[0].target == Location(processor.info.address_space, 524)


def test_byte_constant_preserves_full_encoded_dword_and_effective_width():
    _, result = decoded('96780000efbeadde')
    constant = result.facts['operands'][1]
    assert constant['encoded_value'] == 0xDEADBEEF
    assert constant['encoded_bits'] == 32
    assert constant['value'] == 0xEF
    assert constant['signed_value'] == -17
    assert constant['width_bits'] == 8


def test_small_signed_constant_does_not_lose_the_original_nibble():
    _, result = decoded('3e7e0c00')
    constant = result.facts['operands'][1]
    assert constant['encoded_value'] == 12
    assert constant['encoded_bits'] == 4
    assert constant['signed_value'] == -4
    assert constant['value'] == (1 << 64) - 4


def test_tlj_frame_displacement_and_packed_target_are_different_quantities():
    processor, result = decoded('d8100200fcffffff940200009402000014020000')
    assert result.facts['mnemonic'] == 'tljne'
    assert result.facts['operands'][0]['base'] == 'frame'
    assert result.facts['operands'][0]['displacement'] == -4
    assert result.facts['operands'][0]['encoded_displacement'] == 0xFFFFFFFC
    assert result.facts['target'] == 0x210
    assert [(edge.kind, edge.target.offset) for edge in result.successors] == [
        ('branch', 0x210), ('fallthrough', 0x208),
    ]
    assert all(edge.target.space == processor.info.address_space for edge in result.successors)


def test_call_target_is_a_byte_offset_and_returns_are_only_assumed():
    _, result = decoded('540018000c0200001402000054020000')
    assert result.facts['mnemonic'] == 'jsrfr'
    assert result.facts['operands'][0]['value'] == 24
    assert result.facts['target'] == 0x20C
    assert [(edge.kind, edge.target.offset) for edge in result.successors] == [
        ('call', 0x20C), ('fallthrough', 0x208),
    ]
    assert 'if callee returns' in result.successors[1].evidence


@pytest.mark.parametrize('target', [0x1FC, 0x203, 0xFFFF_FFFC])
def test_invalid_call_target_is_preserved_as_an_unresolved_edge(target):
    code = bytes.fromhex('54000000') + target.to_bytes(4, 'little') + bytes.fromhex('14020000')
    processor = KINT6Processor(image(code))
    result = processor.decode(processor.program, Location(processor.info.address_space, 512))
    assert result.facts['target'] == target
    assert result.successors[0].kind == 'call'
    assert result.successors[0].target is None
    assert f'{target:#x}' in result.successors[0].evidence
    assert result.successors[1].target.offset == 0x208


def test_indirect_jump_dereferences_memory_and_never_invents_initial_register_state():
    raw = bytearray(image(bytes.fromhex('8c10000014020000')))
    raw[24:32] = (0x204).to_bytes(8, 'little')  # Initial $2 is not live state.
    processor = KINT6Processor(bytes(raw))
    result = processor.decode(processor.program, Location(processor.info.address_space, 512))
    assert result.facts['flow'] == 'indirect_jump'
    operand = result.facts['operands'][0]
    assert operand['kind'] == 'memory'
    assert operand['register'] == 2
    assert operand['displacement'] == 16
    assert len(result.successors) == 1
    assert result.successors[0].target is None
    assert 'register and memory' in result.successors[0].evidence


def test_indirect_call_preserves_register_and_candidate_return_continuation():
    _, result = decoded('5433080014020000')
    assert result.facts['flow'] == 'indirect_call'
    assert result.facts['operands'][0]['value'] == 8
    assert result.facts['operands'][1]['number'] == 3
    assert result.successors[0].kind == 'call'
    assert result.successors[0].target is None
    assert result.successors[1].target.offset == 0x204


@pytest.mark.parametrize(('code', 'mnemonic', 'flow'), [
    ('94000000', 'pause', 'suspend'),
    ('14030000', 'smod', 'suspend'),
    ('94030000', 'emod', 'modal_resume'),
])
def test_event_and_modal_control_never_claim_ordinary_fallthrough(code, mnemonic, flow):
    _, result = decoded(code + '14020000')
    assert result.facts['mnemonic'] == mnemonic
    assert result.facts['flow'] == flow
    assert len(result.successors) == 1
    assert result.successors[0].kind == flow
    assert result.successors[0].target is None


def test_term_has_no_following_edge_and_efr_has_only_runtime_return():
    _, term = decoded('1402000094020000')
    assert term.facts['flow'] == 'stop'
    assert term.successors == ()
    _, efr = decoded('5412000094020000')
    assert efr.facts['register_count'] == 4
    assert efr.facts['saved_registers'] == [10, 11, 12, 13]
    assert [(edge.kind, edge.target) for edge in efr.successors] == [('return', None)]


def test_host_service_reports_unknown_effects_and_only_a_candidate_continuation():
    _, result = decoded('1401000014020000')
    assert result.facts['host_effects'] == 'unresolved_runtime_service'
    assert result.successors[0].kind == 'fallthrough'
    assert 'assuming normal completion' in result.successors[0].evidence


def test_running_off_initialized_code_is_explicitly_unresolved():
    _, result = decoded('94020000')
    assert result.facts['mnemonic'] == 'nop'
    assert len(result.successors) == 1
    assert result.successors[0].target is None
    assert 'initialized' in result.successors[0].evidence


@pytest.mark.parametrize('cut', [4, 5, 8, 11])
def test_truncated_qword_extension_never_borrows_runtime_zero_memory(cut):
    body = bytes.fromhex('767e00008877665544332211')[:cut]
    processor = KINT6Processor(image(body))
    with pytest.raises(ValueError, match='Truncated'):
        processor.decode(processor.program, Location(processor.info.address_space, 512))


@pytest.mark.parametrize(('code', 'message'), [
    ('04000000', 'Unknown or reserved'),
    ('1f000000', 'Unknown or reserved'),
    ('1cc00000', 'reserved KINT6 binary'),
    ('d41c0000', 'reserved KINT6 unary'),
    ('d4480000', 'reserved KINT6 unary'),
    ('1c880000', 'floating-point'),
    ('d4000000', 'floating-point'),
    ('14040000', 'control-opcode extension'),
    ('543d0000', 'saved-register count'),
    ('54420000', 'return extension'),
    ('54040000', 'call extension'),
    ('0000000010000000', 'register number'),
])
def test_unknown_or_malformed_encodings_fail_instead_of_becoming_nops(code, message):
    processor = KINT6Processor(image(bytes.fromhex(code)))
    with pytest.raises(ValueError, match=message):
        processor.decode(processor.program, Location(processor.info.address_space, 512))


def test_byte_identity_and_address_space_are_bound_to_one_source():
    first = KINT6Processor(image())
    second = KINT6Processor(image(bytes.fromhex('94020000')))
    assert first.info.address_space != second.info.address_space
    equal_copy = memoryview(first.program).tobytes()
    assert equal_copy == first.program and equal_copy is not first.program
    location = Location(first.info.address_space, 512)
    with pytest.raises(ValueError, match='captured immutable'):
        first.decode(equal_copy, location)
    with pytest.raises(ValueError, match='address space'):
        first.decode(first.program, Location(second.info.address_space, 512))


def test_header_unaligned_and_runtime_only_locations_are_not_decoded():
    processor = KINT6Processor(image())
    with pytest.raises(ValueError, match='header'):
        processor.decode(processor.program, Location(processor.info.address_space, 0))
    with pytest.raises(ValueError, match='aligned'):
        processor.decode(processor.program, Location(processor.info.address_space, 513))
    assert processor.decode(processor.program, Location(processor.info.address_space, 516)) is None
    assert processor.decode(processor.program, Location(processor.info.address_space, 4096)) is None


def test_header_pc_is_not_used_as_event_entry():
    raw = bytearray(image())
    raw[0x88:0x90] = (0x1234).to_bytes(8, 'little')
    processor = KINT6Processor(bytes(raw))
    assert processor.image_info['entry_offset'] == 512


def test_metadata_mutation_cannot_rewrite_source_or_decode_bounds():
    processor = KINT6Processor(image())
    info = processor.image_info
    info['entry_offset'] = 0
    info['sections'][0]['size_bytes'] = 1 << 40
    info['qualification']['runtime_execution'] = True
    assert processor.image_info['entry_offset'] == 512
    assert processor.image_info['sections'][0]['size_bytes'] == len(processor.program)
    assert processor.image_info['qualification']['runtime_execution'] is False


def test_file_replacement_does_not_change_captured_program(tmp_path):
    path = tmp_path / 'program.ke'
    original = image()
    path.write_bytes(original)
    processor = KINT6Processor.from_file(path)
    path.write_bytes(image(bytes.fromhex('94020000')))
    result = processor.decode(processor.program, Location(processor.info.address_space, 512))
    assert processor.program == original
    assert result.facts['mnemonic'] == 'term'
