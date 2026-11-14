"""Static tests only: no compiler, guest, or native execution is implied."""
import struct

import pytest

from offline_windows_oracles import CHECKPOINT, STATE, win16_profile, win16_recipe


def sample_ne():
    data = bytearray(0x300)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 0x40)
    data[0x40:0x42] = b'NE'
    def word(offset, value):
        struct.pack_into('<H', data, 0x40 + offset, value)
    word(14, 2)  # automatic data segment
    word(20, 0); word(22, 1)  # entry IP, CS
    word(24, 0x80); word(26, 2)  # SP, SS
    word(28, 2); word(34, 0x40); word(50, 0)
    data[0x40 + 54] = 2
    struct.pack_into('<4H', data, 0x80, 0x100, 0x80, 0, 0x80)
    struct.pack_into('<4H', data, 0x88, 0x200, 0x80, 1, 0x80)
    data[0x110:0x110 + len(CHECKPOINT)] = CHECKPOINT
    data[0x220:0x220 + len(STATE)] = STATE
    return bytes(data)


def test_profile_binds_markers_to_logical_segments_and_source_hash():
    profile = win16_profile(sample_ne())
    assert profile['entry'] == 'ne:1:0x0'
    assert profile['checkpoint'] == 'ne:1:0x10'
    assert profile['counter'] == 'ne:2:0x25'
    assert len(profile['executable_sha256']) == len(profile['source_sha256']) == 64
    assert 'unverified' in profile['scope']


def test_profile_refuses_missing_duplicate_and_wrong_segment_markers():
    base = sample_ne()
    for index, marker in [(0x110, CHECKPOINT), (0x220, STATE)]:
        missing = bytearray(base); missing[index] ^= 1
        with pytest.raises(ValueError, match='marker'):
            win16_profile(bytes(missing))
        duplicate = bytearray(base); duplicate[0x280:0x280 + len(marker)] = marker
        with pytest.raises(ValueError, match='marker'):
            win16_profile(bytes(duplicate))
    misplaced = bytearray(base)
    misplaced[0x110:0x110 + len(CHECKPOINT)] = bytes(len(CHECKPOINT))
    misplaced[0x240:0x240 + len(CHECKPOINT)] = CHECKPOINT
    with pytest.raises(ValueError, match='marker'):
        win16_profile(bytes(misplaced))


def test_recipe_only_describes_explicit_compilation():
    recipe = win16_recipe()
    assert [row[0] for row in recipe] == ['wcc', 'wlink']
    assert 'ORACLE.C' in recipe[0] and 'ORACLE.EXE' in recipe[1]
