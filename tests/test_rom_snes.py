import pytest

from fdisbull.rom_snes import parse_snes


def rom(offset=0x7fc0, mode=0x20, copier=0, size=0x10000):
    data = bytearray(max(size + copier, offset + copier + 64))
    pos = offset + copier
    data[pos:pos + 21] = b'SYNTHETIC TEST GAME  '
    data[pos + 21:pos + 28] = bytes([mode, 0, 6, 0, 1, 0, 0])
    data[pos + 28:pos + 32] = bytes.fromhex('cbed3412')
    data[pos + 60:pos + 62] = bytes.fromhex('0080')
    return data


def test_layouts_and_copier_offsets():
    for offset, mode, name, copier in [(0x7fc0, 0x20, 'LoROM', 0),
                                       (0xffc0, 0x31, 'HiROM', 512),
                                       (0x40ffc0, 0x25, 'ExHiROM', 0)]:
        result = parse_snes(bytes(rom(offset, mode, copier)))
        assert result['valid']
        assert result['header_offset'] == offset + copier
        assert result['metadata']['layout'] == name
        assert result['metadata']['checksum_verified'] is False
        assert result['metadata']['reset_vector'] == 0x8000
        assert result['regions'][-1]['file_offset'] == copier


def test_unmatched_and_invalid():
    assert parse_snes(bytes(0x10000)) is None
    with pytest.raises(ValueError):
        parse_snes(bytes(64 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        parse_snes(bytearray())
    data = rom()
    data[0x7ffc:0x7ffe] = b'\x00\x20'
    assert not parse_snes(bytes(data))['valid']
    assert not parse_snes(bytes(rom()[:0x7fe0]))['valid']
    data = rom()
    data[0x7fd7] = 10
    result = parse_snes(bytes(data))
    assert result['valid'] and any("rounded ROM capacity" in w for w in result['warnings'])


def test_non_power_of_two_rom_capacity():
    data = rom(size=1536 * 1024)
    data[0x7fd7] = 11
    result = parse_snes(bytes(data))
    assert result["valid"]
    assert result["metadata"]["observed_rom_size"] == 1536 * 1024
    assert result["metadata"]["declared_rom_capacity"] == 2 * 1024 * 1024
    assert any("truncation" in warning for warning in result["warnings"])


def test_ambiguous_candidates_are_not_resolved():
    data = rom()
    second = rom(0xffc0, 0x21, size=0x20000)
    data.extend(bytes(len(second) - len(data)))
    data[0xffc0:0x10000] = second[0xffc0:0x10000]
    result = parse_snes(bytes(data))
    assert not result['valid']
    assert result['header_offset'] is None
    assert len(result['metadata']['candidates']) == 2
    assert result['regions'] == []
