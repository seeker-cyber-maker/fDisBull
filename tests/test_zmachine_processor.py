"""Processor source qualification and variable-reference contracts.

All fixtures are authored here. Processor control-flow acceptance has its own
independent byte vectors in test_zmachine_processor_acceptance.py.
"""
from pathlib import Path

import pytest

from fdisbull.processor import Location, decode_instruction
from fdisbull.zmachine import MAX_STORY_FILE, decode_v3, inspect_story, inspect_story_bytes
from fdisbull.zmachine_processor import ZMachineV3Processor


def image(code=b'\xba'):
    data = bytearray(1024)
    data[0] = 3
    for at, value in ((2, 9), (4, 900), (6, 900), (8, 810), (10, 544),
                      (12, 64), (14, 800), (24, 606), (26, 512)):
        data[at:at + 2] = value.to_bytes(2, 'big')
    data[18:24] = b'261029'
    data[810:814] = bytes((0, 4, 0, 0))
    data[900:900 + len(code)] = code
    data[28:30] = (sum(data[64:]) & 65535).to_bytes(2, 'big')
    return bytes(data)


def decoded(code):
    processor = ZMachineV3Processor(image(bytes.fromhex(code)))
    result = decode_instruction(processor, processor.program,
                                Location(processor.info.address_space, 900))
    return processor, result


def test_byte_inspection_preserves_path_inspection_metadata(tmp_path):
    source = image() + b'private padding'
    path = tmp_path / 'unrelated.extension'
    path.write_bytes(source)
    assert inspect_story_bytes(source) == inspect_story(path)


@pytest.mark.parametrize('source', [bytearray(image()), memoryview(image()), None, 'not bytes'])
def test_processor_requires_immutable_source_bytes(source):
    with pytest.raises(ValueError, match='immutable'):
        ZMachineV3Processor(source)


@pytest.mark.parametrize('change', [
    lambda b: b.__setitem__(0, 5),
    lambda b: b.__setitem__(slice(26, 28), b'\xff\xff'),
    lambda b: b.__setitem__(900, 0),
])
def test_constructor_qualifies_structure_and_checksum(change):
    data = bytearray(image())
    change(data)
    with pytest.raises(ValueError):
        ZMachineV3Processor(bytes(data))


def test_bounded_file_loader_reads_once_and_survives_path_replacement(tmp_path, monkeypatch):
    path = tmp_path / 'story.dat'
    raw = image()
    path.write_bytes(raw)
    original = Path.open
    reads = []

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, length):
            reads.append(length)
            return self.stream.read(length)

    def open_source(selected, *args, **kwargs):
        assert selected == path
        return Reader(original(selected, *args, **kwargs))

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', open_source)
        processor = ZMachineV3Processor.from_file(path)
    assert reads == [MAX_STORY_FILE + 1]
    path.write_bytes(b'replaced by another source')
    result = decode_instruction(processor, processor.program,
                                Location(processor.info.address_space, 900))
    assert result.facts['op'] == 'quit'
    assert processor.program == raw


def test_program_and_metadata_are_not_mutable_through_public_properties():
    processor = ZMachineV3Processor(image())
    metadata = processor.story_info
    metadata['initial_pc'] = 42
    metadata['globals'] = 42
    assert processor.story_info['initial_pc'] == 900
    assert processor.story_info['globals'] == 64
    with pytest.raises(AttributeError):
        processor.program = b'new source'
    with pytest.raises(AttributeError):
        processor.story_info = metadata


def test_raw_decoder_facts_remain_exactly_available():
    processor, result = decoded('a2 86 00 c1')  # get_child global_0x86 -> sp ?rtrue
    raw = decode_v3(processor.program, 900)
    assert {key: result.facts[key] for key in raw} == raw
    assert result.facts['mnemonic'] == 'get_child'
    assert result.facts['size'] == 4
    assert result.facts['store_variable'] == {
        'number': 0, 'kind': 'stack', 'name': 'sp', 'stack_write': 'push'
    }
    reference = result.facts['operand_details'][0]['read_variable']
    assert (reference['number'], reference['kind'], reference['address']) == (0x86, 'global', 300)
    assert result.facts['operand_evaluation'] == 'left_to_right'


def test_stack_value_reads_and_result_writes_are_distinct():
    _, result = decoded('75 00 00 00')  # sub sp sp -> sp
    assert result.facts['op'] == 'sub'
    assert [operand['stack_read'] for operand in result.facts['operand_details']] == ['pop', 'pop']
    assert result.facts['store_variable']['stack_write'] == 'push'
    assert result.facts['op_str'] == 'pop(sp), pop(sp), -> sp'


def test_immediate_indirect_stack_reference_is_in_place_not_a_pop():
    _, result = decoded('95 00')  # inc (sp)
    operand = result.facts['operand_details'][0]
    assert operand['role'] == 'variable_number'
    assert operand['referenced_variable']['kind'] == 'stack'
    assert operand['stack_reference'] == 'in_place'
    assert 'read_variable' not in operand
    assert operand['text'] == 'variable(sp)'


def test_variable_indirect_reference_requires_operand_value_before_target_selection():
    _, result = decoded('a5 00')  # inc variable-number supplied by popping sp
    operand = result.facts['operand_details'][0]
    assert operand['read_variable']['kind'] == 'stack'
    assert operand['stack_read'] == 'pop'
    assert operand['referenced_variable'] is None
    assert operand['reference_resolution'] == 'runtime_operand_value'
    assert operand['text'] == 'variable(pop(sp))'


def test_local_reference_does_not_assert_current_frame_has_that_local():
    _, result = decoded('ab 01')  # ret local1
    reference = result.facts['operand_details'][0]['read_variable']
    assert reference['number'] == 1
    assert reference['index'] == 0
    assert reference['exists_in_current_frame'] is None


def test_immediate_indirect_variable_number_cannot_exceed_byte_range():
    with pytest.raises(ValueError, match='variable number'):
        decoded('85 01 00')  # inc variable 256


def test_header_offsets_are_not_decoded_and_padding_is_excluded():
    processor = ZMachineV3Processor(image() + b'\xba')
    with pytest.raises(ValueError, match='header'):
        decode_instruction(processor, processor.program, Location(processor.info.address_space, 63))
    assert decode_instruction(processor, processor.program,
                              Location(processor.info.address_space, 1024)) is None


def test_terminal_instruction_at_last_declared_byte_has_no_fabricated_fallthrough():
    raw = bytearray(image())
    raw[-1] = 0xBA
    raw[28:30] = (sum(raw[64:]) & 65535).to_bytes(2, 'big')
    processor = ZMachineV3Processor(bytes(raw))
    result = decode_instruction(processor, processor.program,
                                Location(processor.info.address_space, 1023))
    assert result.facts['op'] == 'quit'
    assert result.successors == ()
