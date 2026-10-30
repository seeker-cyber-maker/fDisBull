"""Bounded iNES and NES 2.0 container parsing, not emulation.

Format references: https://www.nesdev.org/wiki/INES and
https://www.nesdev.org/wiki/NES_2.0 . File regions are not CPU mappings.
"""

_MAX_SIZE = 64 * 1024 * 1024
_MAGIC = b"NES\x1a"


def _rom_size(low: int, high: int, unit: int) -> int:
    if high == 15:
        return (1 << (low >> 2)) * (2 * (low & 3) + 1)
    return (low | (high << 8)) * unit


def _ram_size(shift: int) -> int:
    return 64 << shift if shift else 0


def parse_nes(data: bytes) -> dict | None:
    """Describe an iNES/NES 2.0 file using only its header and file offsets."""
    if not isinstance(data, bytes):
        raise ValueError("NES input must be bytes")
    if len(data) > _MAX_SIZE:
        raise ValueError("NES input exceeds the 64 MiB parsing limit")
    if not data.startswith(_MAGIC):
        return None
    result = {
        "format": "iNES", "family": "console ROM", "platform": "NES",
        "arch": "mos6502", "bits": 8, "endian": "little",
        "header_offset": 0, "valid": False, "detection": "NES magic",
        "metadata": {}, "regions": [], "warnings": [],
    }
    warnings = result["warnings"]
    if len(data) < 16:
        warnings.append("Truncated 16-byte NES header")
        return result

    h = data[:16]
    nes2 = h[7] & 0x0c == 0x08
    polluted = not nes2 and (any(h[12:16]) or h[7] & 0x0c != 0)
    mapper_low = h[6] >> 4
    mapper_high = h[7] & 0xf0
    meta = result["metadata"]
    result["format"] = "NES 2.0" if nes2 else "iNES"
    result["detection"] = "NES magic and NES 2.0 marker" if nes2 else "NES magic and iNES header"
    if polluted:
        warnings.append("Legacy header may be polluted; upper mapper bits are uncertain")
        mapper = None
    else:
        mapper = mapper_low | mapper_high | (((h[8] & 0x0f) << 8) if nes2 else 0)
    meta.update({
        "mapper": mapper, "mapper_low_nibble": mapper_low,
        "mapper_high_nibble_raw": mapper_high >> 4,
        "submapper": h[8] >> 4 if nes2 else None,
        "trainer_present": bool(h[6] & 4), "battery": bool(h[6] & 2),
        "four_screen": bool(h[6] & 8), "mirroring_bit": h[6] & 1,
        "console_type_raw": h[7] & 3 if not polluted else None,
        "legacy_header_polluted": polluted,
    })
    if nes2:
        prg = _rom_size(h[4], h[9] & 15, 16384)
        chr_size = _rom_size(h[5], h[9] >> 4, 8192)
        for label, high, size, unit in (("PRG-ROM", h[9] & 15, prg, 16384),
                                        ("CHR-ROM", h[9] >> 4, chr_size, 8192)):
            if high == 15 and size % unit == 0 and size // unit <= 0xeff:
                warnings.append(f"Noncanonical {label} exponent encoding: linear encoding can represent this size")
        meta.update({
            "prg_ram_size": _ram_size(h[10] & 15),
            "prg_nvram_size": _ram_size(h[10] >> 4),
            "chr_ram_size": _ram_size(h[11] & 15),
            "chr_nvram_size": _ram_size(h[11] >> 4),
            "misc_rom_count": h[14] & 3,
            "timing_mode_raw": h[12] & 3,
        })
    else:
        prg, chr_size = h[4] * 16384, h[5] * 8192
        # Legacy RAM fields are ambiguous; retain bytes without inferring hardware.
        meta.update({"prg_ram_size_raw": h[8] if not polluted else None,
                     "misc_rom_count": None})
    meta.update({"prg_rom_size": prg, "chr_rom_size": chr_size})
    result["regions"].append({"name": "Header", "kind": "header", "file_offset": 0, "file_size": 16})
    offset = 16
    complete = True
    for name, kind, size in (("Trainer", "trainer", 512 if h[6] & 4 else 0),
                             ("PRG-ROM", "prg_rom", prg),
                             ("CHR-ROM", "chr_rom", chr_size)):
        if not size:
            continue
        available = max(0, min(size, len(data) - offset))
        if available:
            result["regions"].append({"name": name, "kind": kind, "file_offset": offset,
                                      "file_size": available})
        if available != size:
            warnings.append(f"Truncated {name}: expected {size} bytes, found {available}")
            complete = False
        offset += size
    if nes2 and not complete:
        warnings.append("NES 2.0 marker retained; declared extents may indicate truncation or a polluted header")
    if offset < len(data):
        count = len(data) - offset
        kind = "misc_rom" if nes2 and meta["misc_rom_count"] else "trailing_data"
        result["regions"].append({"name": "Miscellaneous ROM data" if kind == "misc_rom" else "Trailing data",
                                  "kind": kind, "file_offset": offset, "file_size": count})
        if kind == "trailing_data":
            warnings.append("Unclassified trailing data follows declared ROM regions")
    elif nes2 and meta["misc_rom_count"] and complete:
        warnings.append("Miscellaneous ROMs are declared but no trailing data is present")
        complete = False
    result["valid"] = complete
    return result
