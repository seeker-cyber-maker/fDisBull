"""Static CHIP-8 facts agree with the pilot classifier and explicit flow cases."""
import sys
from pathlib import Path
import pytest
from fdisbull.chip8 import PROFILE, decode


def test_classification_matches_classic_pilot_for_every_word():
    pilot = Path(__file__).resolve().parents[1] / 'examples' / 'chip8_pilot'
    sys.path.insert(0, str(pilot))
    try:
        from chip8lab.decoder import decode_table
        families = set()
        for word in range(65536):
            expected = decode_table(word, 'chip8')
            actual = decode(word.to_bytes(2, 'big'), 0x200)
            if expected.tier == 'classic':
                assert actual is not None and actual['mnemonic'] == expected.family.lower()
                families.add(expected.family)
            else:
                assert actual is None
        assert len(families) == 34
    finally:
        sys.path.remove(str(pilot))


@pytest.mark.parametrize('raw,flow,target', [
    ('1234', 'jump', 0x234), ('2234', 'call', 0x234),
    ('00ee', 'return', None), ('b234', 'indirect_jump', None),
    ('3101', 'conditional', 0x204), ('e19e', 'conditional', 0x204),
    ('6001', 'next', None), ('a345', 'next', None),
])
def test_explicit_flow(raw, flow, target):
    fact = decode(bytes.fromhex(raw), 0x200)
    assert fact['flow'] == flow and fact['target'] == target
    assert fact['size'] == 2 and fact['bytes'] == raw
    assert fact['data_refs'] == []


def test_bounds_and_unsupported_words():
    assert PROFILE == 'chip8-classic-pilot-default-v1'
    for address in (-1, 0x201, 0xfff, 0x1000, True):
        assert decode(bytes.fromhex('6001'), address) is None
    assert decode(b'\x60', 0x200) is None
    for raw in ('0123', '00ff', 'f000', '5121', '8128'):
        assert decode(bytes.fromhex(raw), 0x200) is None
    assert decode(bytes.fromhex('3100'), 0xffe)['target'] is None
    assert decode(bytes.fromhex('1fff'), 0x200)['target'] == 0xfff
