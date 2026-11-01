"""SH-2 profile controls for the pinned Capstone decoding defect."""
from fdisbull.rom_asm_capstone import decode


def native_rows(data):
    import capstone
    engine = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    return [item for offset in range(0, len(data), 2)
            for item in engine.disasm(data[offset:offset + 2], offset, count=1)]


def test_rtv_n_all_registers_are_rejected_and_native_facts_retained():
    words = b''.join((0x007b | (n << 8)).to_bytes(2, 'big') for n in range(16))
    result = decode(words, 0x1000, 16, scan_all_words=True)
    assert result['instructions'] == []
    assert [item['native_fact']['bytes'] for item in result['diagnostics']] == [bytes(item.bytes).hex() for item in native_rows(words)]
    assert all(item['native_fact']['mnemonic'] == 'rtv/n' for item in result['diagnostics'])


def test_profile_guard_keeps_valid_neighbors_and_stops_linear():
    result = decode(bytes.fromhex('0009 027b 000b'), 0, 3, scan_all_words=True)
    assert [row['mnemonic'] for row in result['instructions']] == ['nop', 'rts']
    assert [r['native_fact']['bytes'] for r in result['diagnostics']] == [
        bytes(item.bytes).hex() for item in native_rows(bytes.fromhex('027b'))]
    linear = decode(bytes.fromhex('0009 027b 000b'), 0, 3)
    assert [row['mnemonic'] for row in linear['instructions']] == ['nop']
    assert linear['diagnostics'] == result['diagnostics']


def test_other_exclusive_profile_families_and_sh2_controls():
    # Independent examples cover register, system, memory and branch forms;
    # the source-table fix additionally has an exhaustive differential check.
    raw = bytes.fromhex('0039 004a 005b 0068 006b 00ab 4042 404b 4080 408b 40a9 40e5 40f0 0009 000b 001b 002b')
    result = decode(raw, 0, len(raw) // 2, scan_all_words=True)
    assert [row['bytes'] for row in result['instructions']] == ['0009', '000b', '001b', '002b']
    assert [row['native_fact']['bytes'] for row in result['diagnostics']] == [
        bytes(item.bytes).hex() for item in native_rows(raw[:-8])]
