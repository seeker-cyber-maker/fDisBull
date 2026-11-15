"""Static tests only: no compiler, guest, or native execution is implied."""
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

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


def test_oracle_and_boat_fixture_load_without_site_packages(tmp_path):
    source = Path(__file__).parents[1]
    script = textwrap.dedent('''
        import importlib.util
        import json
        import struct
        import sys
        from hashlib import sha256
        from pathlib import Path

        source = Path(sys.argv[1])
        sys.path.insert(0, str(source / 'src'))
        oracle_path = source / 'tests/offline_windows_oracles.py'
        spec = importlib.util.spec_from_file_location('actual_offline_oracle', oracle_path)
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)

        data = bytearray(0x300)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 0x40)
        data[0x40:0x42] = b'NE'
        def word(offset, value):
            struct.pack_into('<H', data, 0x40 + offset, value)
        word(14, 2); word(20, 0); word(22, 1); word(24, 0x80); word(26, 2)
        word(28, 2); word(34, 0x40); word(50, 0); data[0x40 + 54] = 2
        struct.pack_into('<4H', data, 0x80, 0x100, 0x80, 0, 0x80)
        struct.pack_into('<4H', data, 0x88, 0x200, 0x80, 1, 0x80)
        data[0x110:0x110 + len(oracle.CHECKPOINT)] = oracle.CHECKPOINT
        data[0x220:0x220 + len(oracle.STATE)] = oracle.STATE
        payload = bytes(data)
        profile = oracle.win16_profile(payload)
        assert profile['entry'] == 'ne:1:0x0'
        assert profile['checkpoint'] == 'ne:1:0x10'
        assert profile['counter'] == 'ne:2:0x25'
        assert profile['source_sha256'] == sha256((source / 'tests/offline_win16_oracle.c').read_bytes()).hexdigest()
        assert profile['executable_sha256'] == sha256(payload).hexdigest()
        invalid = bytearray(payload); invalid[0x40:0x42] = b'XX'
        try:
            oracle.win16_profile(bytes(invalid))
        except ValueError:
            pass
        else:
            raise AssertionError('wrong NE signature was accepted')

        fixture_dir = Path(sys.argv[2]); fixture_dir.mkdir()
        executable = fixture_dir / 'ORACLE.EXE'; executable.write_bytes(payload)
        boat_path = source / 'scripts/ci/boat-linux.py'
        boat_spec = importlib.util.spec_from_file_location('actual_boat_linux', boat_path)
        boat = importlib.util.module_from_spec(boat_spec)
        boat_spec.loader.exec_module(boat)
        authored = boat.authored_fixture(source, executable)
        assert authored['size'] == len(payload)
        assert authored['source_sha256'] == profile['source_sha256']
        assert not {'lief', 'capstone', 'iced_x86'}.intersection(sys.modules)
        print(json.dumps({'profile': profile, 'authored_fixture': authored}, sort_keys=True))
    ''')
    result = subprocess.run(
        [sys.executable, '-I', '-S', '-c', script, str(source), str(tmp_path / 'fixture')],
        cwd=tmp_path, text=True, capture_output=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
