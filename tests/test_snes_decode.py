import pytest

from fdisbull.snes_decode import decode_one, lorom_offset


@pytest.mark.parametrize('m8,x8', [(False, False), (False, True),
                                   (True, False), (True, True)])
@pytest.mark.parametrize('opcode,register', [
    (0x09, 'm'), (0x29, 'm'), (0x49, 'm'), (0x69, 'm'),
    (0x89, 'm'), (0xA9, 'm'), (0xC9, 'm'), (0xE9, 'm'),
    (0xA0, 'x'), (0xA2, 'x'), (0xC0, 'x'), (0xE0, 'x'),
])
def test_immediate_widths_are_independent(opcode, register, m8, x8):
    result = decode_one(bytes((opcode, 0x34, 0x12, 0xEA)), 0x008000,
                        m8=m8, x8=x8)
    short = m8 if register == 'm' else x8
    assert result['size'] == (2 if short else 3)
    assert result['operands'] == ('#0x34' if short else '#0x1234')


@pytest.mark.parametrize('m8,x8', [(False, False), (False, True),
                                   (True, False), (True, True)])
def test_65816_only_and_status_instructions(m8, x8):
    for code, mnemonic, size in ((b'\x22\x34\x12\x56', 'jsl', 4),
                                  (b'\xc2\x20', 'rep', 2),
                                  (b'\xe2\x20', 'sep', 2)):
        result = decode_one(code, 0x008000, m8=m8, x8=x8)
        assert (result['mnemonic'], result['size']) == (mnemonic, size)


def test_width_must_be_supplied_again_after_status_change():
    assert decode_one(b'\xc2\x20', 0x8000, m8=True, x8=True)['mnemonic'] == 'rep'
    assert decode_one(b'\xa9\x34\x12', 0x8002, m8=False, x8=True)['size'] == 3
    with pytest.raises(ValueError):
        decode_one(b'\xa9\x34\x12', 0x8002, m8=0, x8=True)
    with pytest.raises(ValueError):
        decode_one(b'\xa9', 0x8002, m8=False, x8=True)
    with pytest.raises(ValueError):
        decode_one(b'\x22\x34\x12\x56', 0x00FFFE, m8=True, x8=True)


def test_short_width_fallback_only_selects_between_independent_immediates():
    import capstone as cs

    decoders = [cs.Cs(cs.CS_ARCH_MOS65XX, mode) for mode in
                (cs.CS_MODE_MOS65XX_65816_LONG_M,
                 cs.CS_MODE_MOS65XX_65816_LONG_X)]
    differences = set()
    for opcode in range(256):
        rows = [[(i.mnemonic, i.op_str, i.size) for i in decoder.disasm(
            bytes((opcode, 0x34, 0x12, 0x56)), 0x8000, count=1)]
                for decoder in decoders]
        if rows[0] != rows[1]:
            differences.add(opcode)
    assert differences == {0x09, 0x29, 0x49, 0x69, 0x89, 0xA9, 0xC9, 0xE9,
                           0xA0, 0xA2, 0xC0, 0xE0}


def test_lorom_upper_low_banks_and_bounds():
    assert lorom_offset(0x008000, 0x100000) == 0
    assert lorom_offset(0x01FFFF, 0x100000, copier_header=512) == 0x10200 - 1
    for addr in (0x007FFF, 0x7E8000, 0x7F8000, 0x808000, 0x208000):
        with pytest.raises(ValueError):
            lorom_offset(addr, 0x100000)
