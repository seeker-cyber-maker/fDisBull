"""Source-independent v3 examples for recognition and instruction facts."""
import hashlib
import pytest
from fdisbull.zmachine import decode_v3, decode_ztext, inspect_story


def image():
    data = bytearray(1024)
    data[0] = 3
    def word(at, value): data[at:at+2] = value.to_bytes(2, 'big')
    for at, value in ((2, 7), (4, 900), (6, 900), (8, 810), (10, 544), (12, 64), (14, 800), (24, 606), (26, 512)):
        word(at, value)
    data[18:24] = b'870915'
    data[810:814] = bytes([0, 4, 0, 0])
    word(28, sum(data[64:]) & 65535)
    return data


def test_content_not_extension_and_trailing_bytes(tmp_path):
    raw = image() + b'extra'
    story = tmp_path / 'arbitrary.bin'; story.write_bytes(raw)
    info = inspect_story(story)
    assert (info['release'], info['serial_text'], info['declared_bytes'], info['trailing_bytes']) == (7, '870915', 1024, 5)
    assert info['sha256'] == hashlib.sha256(raw).hexdigest()

@pytest.mark.parametrize('modify', [
    lambda b: b.__setitem__(0, 5),
    lambda b: b.__setitem__(slice(26, 28), b'\xff\xff'),
    lambda b: b.__setitem__(slice(14, 16), b'\x00\x40'),
    lambda b: b.__setitem__(slice(6, 8), b'\xff\xff'),
    lambda b: b.__setitem__(slice(24, 26), b'\xff\xff'),
    lambda b: b.__setitem__(slice(8, 10), b'\xff\xff'),
    lambda b: b.__setitem__(810, 255),
    lambda b: b.__setitem__(900, 1),
])
def test_invalid_header_or_checksum_rejected(tmp_path, modify):
    raw = image(); modify(raw); story = tmp_path / 'game.z3'; story.write_bytes(raw)
    with pytest.raises(ValueError): inspect_story(story)


def test_add_stores_result_in_variable():
    result = decode_v3(bytes([0x14, 2, 3, 0x10]), 0)
    assert result['op'] == 'add' and result['operands'] == [{'kind':'small','value':2}, {'kind':'small','value':3}]
    assert result['store'] == 16 and result['end'] == 4


def test_short_and_signed_long_branches():
    short = decode_v3(bytes([0x90, 0, 0xc4]), 0)
    assert short['op'] == 'jz' and short['branch'] == {'when': True, 'offset': 4, 'return': None, 'target': 5}
    long = decode_v3(bytes([0x90, 1, 0xbf, 0xfe]), 0)
    assert long['branch'] == {'when': True, 'offset': -2, 'return': None, 'target': 0}
    ret = decode_v3(bytes([0x90, 1, 0xc1]), 0)
    assert ret['branch']['return'] is True and ret['branch']['target'] is None


def test_instruction_truncation_and_inline_text():
    for data in (b'\x14\x02\x03', b'\x90\x00\x80', b'\xb2\x00'):
        with pytest.raises(ValueError, match='Truncated'): decode_v3(data, 0)
    result = decode_v3(b'\xb2\x98\xe8', 0)
    assert result['op'] == 'print' and result['text_offset'] == 1 and result['end'] == 3


def words(*groups):
    out = bytearray()
    for i, (a, b, c) in enumerate(groups):
        value = (a << 10) | (b << 5) | c
        if i == len(groups) - 1: value |= 0x8000
        out.extend(value.to_bytes(2, 'big'))
    return bytes(out)


def test_ztext_alphabet_escape_and_abbreviation():
    # 'A', then ZSCII 33 ('!'), then 'b'.
    encoded = words((4, 6, 5), (6, 1, 1), (7, 5, 5))
    assert decode_ztext(encoded, 0)[0] == 'A!b'
    data = bytearray(100)
    data[24:26] = (40).to_bytes(2, 'big')
    data[40:42] = (30).to_bytes(2, 'big')
    data[60:62] = words((6, 7, 8))
    data[80:82] = words((1, 0, 9))
    assert decode_ztext(bytes(data), 80)[0] == 'abcd'


def test_ztext_truncation_and_cyclic_abbreviation():
    with pytest.raises(ValueError, match='Truncated'): decode_ztext(b'\x00', 0)
    data = bytearray(100); data[24:26] = (40).to_bytes(2, 'big'); data[40:42] = (30).to_bytes(2, 'big'); data[60:62] = words((1, 0, 5))
    with pytest.raises(ValueError, match='cyclic'): decode_ztext(bytes(data), 60)
