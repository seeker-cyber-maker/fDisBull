import pytest

from fdisbull.iso9660 import inspect_iso


def both(value, width):
    return value.to_bytes(width, 'little') + value.to_bytes(width, 'big')


def record(name, extent, size, directory=False):
    length = 33 + len(name) + (len(name) % 2 == 0)
    rec = bytearray(length)
    rec[0] = length
    rec[2:10] = both(extent, 4)
    rec[10:18] = both(size, 4)
    rec[25] = 2 if directory else 0
    rec[28:32] = both(1, 2)
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def image():
    blocks = [bytearray(2048) for _ in range(30)]
    for i, typ in ((16, 0), (17, 1), (18, 255)):
        blocks[i][:7] = bytes([typ]) + b'CD001\x01'
    pvd = blocks[17]
    pvd[40:72] = b'TEST'.ljust(32, b' ')
    pvd[80:88] = both(30, 4)
    pvd[120:124] = both(1, 2)
    pvd[124:128] = both(1, 2)
    pvd[128:132] = both(2048, 2)
    root = record(b'\0', 20, 2048, True)
    pvd[156:190] = root
    directory = root + record(b'\1', 20, 2048, True) + record(b'DIR', 21, 2048, True) + record(b'ONE.BIN;1', 25, 2500)
    blocks[20][:len(directory)] = directory
    nested = record(b'\0', 21, 2048, True) + record(b'\1', 20, 2048, True) + record(b'TWO.TXT;1', 29, 10)
    blocks[21][:len(nested)] = nested
    return blocks


def inspect(blocks, **kwargs):
    return inspect_iso(lambda lba: bytes(blocks[lba]), len(blocks), **kwargs)


def test_primary_after_boot_and_nested_tree():
    result = inspect(image())
    assert result['valid'] is True and result['complete'] is True
    assert [d['type'] for d in result['descriptors']] == [0, 1, 255]
    assert result['volume_id'] == 'TEST'
    assert [(e['path'], e['kind'], e['available']) for e in result['entries']] == [
        ('/DIR', 'directory', True), ('/ONE.BIN;1', 'file', True), ('/DIR/TWO.TXT;1', 'file', True)]


def test_truncated_volume_reports_each_file_availability():
    blocks = image()[:27]
    result = inspect(blocks)
    assert result['complete'] is True and result['valid'] is True
    assert result['volume_extent_fits'] is False
    assert [e['available'] for e in result['entries']] == [True, True, False]


def test_missing_directory_is_incomplete():
    blocks = image()[:21]
    result = inspect(blocks)
    assert result['valid'] is None and not result['complete']
    assert 'available' in result['warnings'][-1]


def test_both_endian_mismatch_rejected():
    blocks = image()
    blocks[17][84] ^= 1
    result = inspect(blocks)
    assert result['valid'] is False and 'endian' in result['warnings'][-1]


def test_directory_cycle_rejected():
    blocks = image()
    cycle = record(b'LOP', 20, 2048, True)
    blocks[20][68:68 + len(cycle)] = cycle
    result = inspect(blocks)
    assert result['valid'] is False and 'cycle' in result['warnings'][-1]


@pytest.mark.parametrize('kwargs', [{'max_entries': 0}, {'max_depth': 0}, {'max_directory_bytes': 100}])
def test_budgets_are_incomplete(kwargs):
    result = inspect(image(), **kwargs)
    assert result['valid'] is None and not result['complete']
    assert 'budget' in result['warnings'][-1]


def test_cross_sector_record_rejected():
    blocks = image()
    blocks[20][0] = 255
    blocks[20][32] = 1
    # A record beyond the current directory boundary is always rejected.
    blocks[17][166:174] = both(100, 4)
    result = inspect(blocks)
    assert result['valid'] is False


def test_unsafe_name_and_multiextent_rejected():
    blocks = image()
    blocks[20][101:104] = b'../'
    assert inspect(blocks)['valid'] is False
    blocks = image()
    blocks[20][68 + 25] |= 0x80
    assert inspect(blocks)['valid'] is False


def test_descriptor_scope_and_unknown_type():
    blocks = image()
    blocks[16][0] = 2
    result = inspect(blocks)
    assert result['complete'] and 'primary' in result['validation_scope']
    assert any('ignored' in warning for warning in result['warnings'])
    assert result['availability_scope'] == 'extent in supplied track range'
    assert result['content_verified'] is False
    blocks[16][0] = 42
    assert inspect(blocks)['valid'] is False


def test_system_use_is_explicitly_uninterpreted():
    blocks = image()
    # Add a two-byte system-use field to the final directory record.
    directory = (record(b'\0', 20, 2048, True) + record(b'\1', 20, 2048, True)
                 + record(b'DIR', 21, 2048, True))
    entry = bytearray(record(b'ONE.BIN;1', 25, 2500))
    entry[0] += 2
    blocks[20][:] = bytes(2048)
    blocks[20][:len(directory + entry) + 2] = directory + entry + b'XY'
    assert 'system-use bytes are uninterpreted' in inspect(blocks)['warnings']


def test_reserved_and_overlapping_extents_rejected():
    blocks = image()
    blocks[20][70:78] = both(17, 4)
    assert inspect(blocks)['valid'] is False
    blocks = image()
    # File ONE starts inside root directory.
    offset = 68 + len(record(b'DIR', 21, 2048, True))
    blocks[20][offset + 2:offset + 10] = both(20, 4)
    result = inspect(blocks)
    assert result['valid'] is False and 'overlap' in result['warnings'][-1]


@pytest.mark.parametrize('kwargs', [{'max_entries': 100001}, {'max_depth': 129},
                                     {'max_directory_bytes': 64 * 1024 * 1024 + 1}])
def test_limit_hard_caps(kwargs):
    with pytest.raises(ValueError, match='hard maximum'):
        inspect(image(), **kwargs)
