import pytest

from fdisbull.rom_nes import parse_nes


def image(prg=1, chr=1, flags6=0, flags7=0, extra=None, payload=b""):
    header = bytearray(b"NES\x1a" + bytes(12))
    header[4:8] = bytes((prg, chr, flags6, flags7))
    if extra:
        for index, value in extra.items():
            header[index] = value
    return bytes(header) + payload


def test_unmatched_and_truncated():
    assert parse_nes(b"other") is None
    short = parse_nes(b"NES\x1a")
    assert not short["valid"] and short["warnings"]
    truncated = parse_nes(image(payload=b"x" * 10))
    assert not truncated["valid"]
    assert truncated["regions"][1]["file_size"] == 10
    assert any("CHR-ROM" in w for w in truncated["warnings"])


def test_ines_trainer_and_original_offsets():
    data = image(flags6=0x34, flags7=0x20, payload=bytes(512 + 16384 + 8192) + b"tail")
    parsed = parse_nes(data)
    assert parsed["valid"] and parsed["metadata"]["mapper"] == 0x23
    assert [(r["kind"], r["file_offset"], r["file_size"]) for r in parsed["regions"]] == [
        ("header", 0, 16), ("trainer", 16, 512), ("prg_rom", 528, 16384),
        ("chr_rom", 16912, 8192), ("trailing_data", 25104, 4)]


def test_nes2_linear_and_ram_and_misc():
    data = image(prg=1, chr=1, flags6=0x10, flags7=0x28,
                 extra={8: 0x31, 10: 0x76, 11: 0x09, 14: 1},
                 payload=bytes(16384 + 8192) + b"misc")
    parsed = parse_nes(data)
    m = parsed["metadata"]
    assert parsed["valid"] and parsed["format"] == "NES 2.0"
    assert (m["mapper"], m["submapper"]) == (0x121, 3)
    assert (m["prg_ram_size"], m["prg_nvram_size"], m["chr_ram_size"], m["chr_nvram_size"]) == (4096, 8192, 32768, 0)
    assert parsed["regions"][-1]["kind"] == "misc_rom"


def test_nes2_exponent_multiplier_and_truncation():
    # 2^13 * 3 bytes, and 2^10 * 5 bytes.
    parsed = parse_nes(image(prg=(13 << 2) | 1, chr=(10 << 2) | 2,
                             flags7=8, extra={9: 0xff}, payload=bytes(24576 + 5120)))
    assert parsed["valid"]
    assert (parsed["metadata"]["prg_rom_size"], parsed["metadata"]["chr_rom_size"]) == (24576, 5120)
    huge = parse_nes(image(prg=255, chr=0, flags7=8, extra={9: 15}))
    assert not huge["valid"] and huge["metadata"]["prg_rom_size"] == 7 * 2**63


def test_polluted_header_does_not_claim_mapper():
    parsed = parse_nes(image(prg=0, chr=0, flags6=0x10, flags7=0x40, extra={12: 1}))
    assert parsed["valid"] and parsed["metadata"]["mapper"] is None
    assert parsed["metadata"]["mapper_low_nibble"] == 1
    assert parsed["warnings"]


def test_input_size_limit():
    with pytest.raises(ValueError, match="64 MiB"):
        parse_nes(b"NES\x1a" + bytes(64 * 1024 * 1024))
    with pytest.raises(ValueError, match="64 MiB"):
        parse_nes(bytes(64 * 1024 * 1024 + 1))
    for invalid in (None, "NES", bytearray(b"NES\x1a")):
        with pytest.raises(ValueError, match="bytes"):
            parse_nes(invalid)


def test_nes2_noncanonical_and_uncertain_extents():
    # 16 KiB is representable in linear PRG units, but encoded as 2^14.
    parsed = parse_nes(image(prg=14 << 2, chr=0, flags7=8,
                             extra={9: 15}, payload=bytes(16384)))
    assert parsed["valid"]
    assert any("Noncanonical PRG-ROM" in w for w in parsed["warnings"])
    truncated = parse_nes(image(prg=1, chr=0, flags7=8))
    assert not truncated["valid"] and truncated["format"] == "NES 2.0"
    assert any("polluted header" in w for w in truncated["warnings"])
    assert parse_nes(image(prg=0, chr=0, flags7=8))["valid"]
