from fdisbull.rom_sega import parse_genesis, parse_sms


def genesis():
    data = bytearray(0x210)
    data[:8] = bytes.fromhex('00ff000000000200')
    data[0x100:0x110] = b'SEGA GENESIS    '
    data[0x120:0x125] = b'TITLE'
    data[0x180:0x18e] = b'GM TEST-00    '
    data[0x1a4:0x1a8] = (0x20f).to_bytes(4, 'big')
    data[0x1a8:0x1ac] = (0xff0000).to_bytes(4, 'big')
    data[0x1ac:0x1b0] = (0xffffff).to_bytes(4, 'big')
    data[0x1f0:0x1f3] = b'JUE'
    data[0x200:0x204] = bytes.fromhex('12345678')
    data[0x18e:0x190] = (0x68ac).to_bytes(2, 'big')
    return data


def test_genesis_fields_and_bounded_checksum():
    data = genesis()
    result = parse_genesis(bytes(data))
    assert result['valid'] and result['detection'] == 'magic'
    assert result['metadata']['domestic_title'] == 'TITLE'
    assert result['metadata']['reset_vector'] == 0x200
    assert result['metadata']['checksum']['matches'] is True
    assert result['regions'][0]['file_offset'] == 0x100
    data[-1] = 1
    assert parse_genesis(bytes(data))['metadata']['checksum']['matches'] is False
    data[0x1a4:0x1a8] = (0x1000).to_bytes(4, 'big')
    assert parse_genesis(bytes(data))['metadata']['checksum']['matches'] is None


def test_32x_and_unsupported_formats():
    data = genesis() + bytearray(0x200)
    data[0x3c0:0x3cf] = b'MARS CHECK MODE'
    result = parse_genesis(bytes(data))
    assert result['platform'] == 'Sega 32X'
    assert any('SH-2' in warning for warning in result['warnings'])
    swapped = bytearray(0x104)
    swapped[0x100:0x104] = b'ESAG'
    assert not parse_genesis(bytes(swapped))['valid']
    assert not parse_genesis(b'\0' * 0x100 + b'SEGA')['valid']
    assert parse_genesis(b'other') is None


def test_sms_locations_and_product():
    for off in (0x1ff0, 0x3ff0, 0x7ff0):
        data = bytearray(off + 16)
        data[off:off + 8] = b'TMR SEGA'
        data[off + 10:off + 16] = bytes.fromhex('e2162670004c')
        result = parse_sms(bytes(data))
        assert result['header_offset'] == off
        assert result['metadata']['product_code'] == 7026
        assert result['metadata']['checksum_stored'] == 0x16e2
        assert result['platform'] == 'Sega Master System'
        assert result['regions'][0]['file_size'] == 16
    data[-1] = 0x7c
    assert parse_sms(bytes(data))['platform'] == 'Sega Game Gear'


def test_sms_unknown_and_truncated():
    data = bytearray(0x8000)
    data[0x7ff0:0x7ff8] = b'TMR SEGA'
    data[0x7ffc] = 0xfa
    assert parse_sms(bytes(data))['metadata']['product_code'] is None
    assert not parse_sms(bytes(data[:0x7ff8]))['valid']
    assert parse_sms(b'other') is None


def test_genesis_invalid_extent_vectors_and_smd():
    data = genesis()
    data[0x1a4:0x1a8] = (0x1000).to_bytes(4, 'big')
    assert not parse_genesis(bytes(data))['valid']
    data[0x1a0:0x1a4] = (0x2000).to_bytes(4, 'big')
    assert not parse_genesis(bytes(data))['valid']
    data = genesis()
    data[:8] = bytes(8)
    result = parse_genesis(bytes(data))
    assert not result['metadata']['vector_plausibility']['stack_nonzero_even']
    assert not result['metadata']['vector_plausibility']['reset_in_declared_rom']
    smd = bytearray(0x284)
    smd[8:10] = b'\xaa\xbb'
    smd[0x280:0x284] = b'EAGN'
    result = parse_genesis(bytes(smd))
    assert not result['valid'] and result['detection'] == 'heuristic'
    assert 'unsupported' in result['warnings'][0]


def test_sms_invalid_fields_and_extent():
    data = bytearray(0x8000)
    data[0x7ff0:0x7ff8] = b'TMR SEGA'
    data[0x7fff] = 0x4c
    assert parse_sms(bytes(data))['valid']
    data[0x7ffe] = 0xa0
    assert not parse_sms(bytes(data))['valid']
    assert parse_sms(bytes(data))['metadata']['product_code'] is None
    data[0x7ffe] = 0
    for value in (0x8c, 0x43, 0x40):
        data[0x7fff] = value
        assert not parse_sms(bytes(data))['valid']


def test_input_type_and_size_bounds():
    import pytest

    for parser in (parse_genesis, parse_sms):
        with pytest.raises(TypeError):
            parser(bytearray())
        with pytest.raises(ValueError):
            parser(bytes(64 * 1024 * 1024 + 1))
