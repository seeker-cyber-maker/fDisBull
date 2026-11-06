"""Independent KASM acceptance vectors, using only authored instruction bytes.

The neighboring JSON records its external oracle and the two cases where that
assembler disagrees with its interpreter. Expected fields do not come from the
decoder under test. We deliberately do not treat an assembler as infallible.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from fdisbull.kint6_processor import KINT6Processor
from fdisbull.processor import Location, decode_instruction


VECTORS = json.loads(Path(__file__).with_name('kint6_vectors.json').read_text())


def _image(payload: bytes, offset: int = 0x200) -> bytes:
    image = bytearray(offset + len(payload))
    image[:8] = bytes.fromhex('efcdab8967452301')
    image[0xD0:0xD6] = b'KINT6\0'
    image[0xE0:0xE8] = len(image).to_bytes(8, 'little')
    image[offset:] = payload
    return bytes(image)


@pytest.fixture(scope='module')
def assembled_image():
    # A fresh synthetic header avoids importing upstream or original-game data.
    image = bytearray(_image(bytes(VECTORS['image_size'] - 0x200)))
    for vector in VECTORS['vectors']:
        encoded = bytes.fromhex(vector['bytes'])
        image[vector['offset']:vector['offset'] + len(encoded)] = encoded
    for discrepancy in VECTORS['assembler_discrepancies']:
        encoded = bytes.fromhex(discrepancy['assembler_bytes'])
        image[discrepancy['offset']:discrepancy['offset'] + len(encoded)] = encoded
    tail = VECTORS['tail']
    image[tail['offset']:] = bytes.fromhex(tail['bytes'])
    return bytes(image)


@pytest.fixture(scope='module')
def assembled_processor(assembled_image):
    return KINT6Processor(assembled_image)


def _decode(processor, offset):
    return decode_instruction(
        processor, processor.program, Location(processor.info.address_space, offset)
    )


def test_authored_source_provenance_matches_recorded_digest():
    assert sha256(VECTORS['assembly_source'].encode()).hexdigest() == (
        VECTORS['provenance']['authored_assembly_sha256']
    )


def _assert_vector(processor, vector):
    decoded = _decode(processor, vector['offset'])
    assert decoded is not None
    for key in ('size', 'bytes', 'mnemonic', 'width_bits', 'target'):
        assert decoded.facts[key] == vector[key], (vector['assembly'], key)
    operands = decoded.facts['operands']
    assert len(operands) == len(vector['operands'])
    for actual, expected in zip(operands, vector['operands']):
        for key, value in expected.items():
            assert actual[key] == value, (vector['assembly'], key, actual, expected)
    return decoded


@pytest.mark.parametrize('vector', VECTORS['vectors'], ids=lambda value: value['id'])
def test_authored_kasm_vector(assembled_processor, vector):
    _assert_vector(assembled_processor, vector)


@pytest.mark.parametrize('vector', VECTORS['runtime_vectors'], ids=lambda value: value['id'])
def test_source_checked_qword_vector(vector):
    processor = KINT6Processor(_image(bytes.fromhex(vector['bytes'])))
    _assert_vector(processor, vector)


@pytest.mark.parametrize('case', VECTORS['assembler_discrepancies'], ids=lambda value: value['id'])
def test_assembler_discrepancy_does_not_shorten_instruction(assembled_processor, case):
    decoded = _decode(assembled_processor, case['offset'])
    assert decoded is not None
    assert decoded.facts['size'] == case['interpreter_span']
    assert decoded.facts['size'] > case['assembler_span']
    assert decoded.facts['bytes'].startswith(case['assembler_bytes'])


def test_all_vector_truncations_are_bounded(assembled_image):
    for vector in VECTORS['vectors']:
        for available in range(1, vector['size']):
            truncated = bytearray(assembled_image[:vector['offset'] + available])
            truncated[0xE0:0xE8] = len(truncated).to_bytes(8, 'little')
            with pytest.raises(ValueError, match='[Tt]runcated'):
                processor = KINT6Processor(bytes(truncated))
                _decode(processor, vector['offset'])


def test_control_flow_remains_candidate_or_unresolved(assembled_processor):
    by_id = {vector['id']: _decode(assembled_processor, vector['offset'])
             for vector in VECTORS['vectors']}
    for name in ('call_direct', 'jump_direct', 'branch_ljeq', 'branch_tljne_reg'):
        assert by_id[name] is not None
        assert any(edge.target is not None for edge in by_id[name].successors)
    for name, kind in (('call_indirect', 'call'), ('jump_indirect', 'branch'),
                       ('frame_end', 'return'), ('no_operand_pause', 'suspend'),
                       ('no_operand_smod', 'suspend'), ('no_operand_emod', 'modal_resume')):
        decoded = by_id[name]
        assert decoded is not None
        assert any(edge.kind == kind and edge.target is None for edge in decoded.successors)
    for name in ('no_operand_pause', 'no_operand_smod', 'no_operand_emod',
                 'frame_end', 'jump_indirect'):
        assert all(edge.kind != 'fallthrough' for edge in by_id[name].successors)
    assert by_id['no_operand_term'].successors == ()


def test_targets_outside_initialized_instructions_are_unresolved():
    # Direct JSRFR uses an uncompressed byte address after its opcode.
    for target in (0, 0x1FC, 0x201, 0x400, 0xFFFFFFFF):
        processor = KINT6Processor(_image(bytes.fromhex('54001800') + target.to_bytes(4, 'little')))
        decoded = _decode(processor, 0x200)
        assert decoded is not None and decoded.facts['target'] == target
        assert decoded.successors[0].kind == 'call'
        assert decoded.successors[0].target is None


def test_opcode_space_probe_never_reads_past_captured_bytes():
    # Exercise every low-ten-bit dispatch tag with three independent high-bit
    # patterns. Reserved encodings may reject; accepted encodings must be bounded.
    for high in (0, 0xFFFFFC00, 0x00047C00):
        for low in range(1024):
            payload = (high | low).to_bytes(4, 'little') + bytes.fromhex('efcdab896745230101020304')
            processor = KINT6Processor(_image(payload))
            try:
                decoded = _decode(processor, 0x200)
            except ValueError:
                continue
            assert decoded is not None
            size = decoded.facts['size']
            assert size in (4, 8, 12, 16)
            assert decoded.facts['bytes'] == payload[:size].hex()
            assert all(edge.target is None or 0x200 <= edge.target.offset <= len(processor.program) - 4
                       for edge in decoded.successors)
