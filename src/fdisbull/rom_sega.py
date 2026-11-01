"""Bounded, header-based Sega cartridge identification.

References: Sega Genesis Software Manual (cartridge information), Sega 32X
Hardware Manual section 5.1, and devkitSMS ihx2sms header handling. Header
fields are claims made by the image, not a CPU address map or code discovery.
"""

_MAX_SIZE = 64 * 1024 * 1024
_SMS_SIZES = {0xA: 8192, 0xB: 16384, 0xC: 32768, 0xD: 49152,
              0xE: 65536, 0xF: 131072, 0: 262144, 1: 524288, 2: 1048576}
_SMS_REGIONS = {3: "Master System Japan", 4: "Master System export",
                5: "Game Gear Japan", 6: "Game Gear export", 7: "Game Gear international"}


def _text(data):
    return data.decode("ascii", errors="replace").strip(" \x00")


def _u32(data, offset):
    return int.from_bytes(data[offset:offset + 4], "big")


def _base(fmt, platform, arch, bits, endian, offset):
    return {"format": fmt, "family": "console ROM", "platform": platform,
            "arch": arch, "bits": bits, "endian": endian,
            "header_offset": offset, "valid": True, "detection": "magic",
            "metadata": {}, "regions": [], "warnings": []}


def _validate_input(data):
    if not isinstance(data, bytes):
        raise TypeError("ROM data must be bytes")
    if len(data) > _MAX_SIZE:
        raise ValueError("ROM data exceeds 64 MiB")


def parse_genesis(data: bytes) -> dict | None:
    """Identify raw headers. Validity is structural; checksums are advisory."""
    _validate_input(data)
    if data[0x100:0x104] != b"SEGA":
        # Recognize only well-defined signatures; do not silently normalize bytes.
        variant = None
        if data[0x100:0x104] == b"ESAG":
            variant = "byte-swapped"
        elif (len(data) >= 0x284 and data[8:10] == b"\xaa\xbb"
              and data[0x280:0x284] in (b"EAGN", b"EAMG")):
            variant = "SMD interleaved"
        if not variant:
            return None
        result = _base("sega-genesis", "Sega Genesis / Mega Drive", "m68000", 16, "big", None)
        result["valid"] = False
        result["detection"] = "heuristic"
        result["metadata"]["recognized_variant"] = variant
        result["warnings"].append(f"{variant} image recognized but parsing is unsupported; original bytes were not transformed")
        return result
    result = _base("sega-genesis", "Sega Genesis / Mega Drive", "m68000", 16, "big", 0x100)
    result["metadata"]["signature"] = "SEGA"
    if len(data) < 0x200:
        result["valid"] = False
        result["warnings"].append("Truncated Genesis header")
        return result
    md = result["metadata"]
    md.update({"console": _text(data[0x100:0x110]),
               "copyright": _text(data[0x110:0x120]),
               "domestic_title": _text(data[0x120:0x150]),
               "overseas_title": _text(data[0x150:0x180]),
               "product": _text(data[0x180:0x18e]),
               "region": _text(data[0x1f0:0x200]),
               "rom_start": _u32(data, 0x1a0), "rom_end": _u32(data, 0x1a4),
               "ram_start": _u32(data, 0x1a8), "ram_end": _u32(data, 0x1ac),
               "initial_stack_pointer": _u32(data, 0), "reset_vector": _u32(data, 4)})
    is_32x = "32X" in md["console"].upper() or data[0x3c0:0x3cf] == b"MARS CHECK MODE"
    if is_32x:
        result["platform"] = "Sega 32X"
        md["variant"] = "32X"
        result["warnings"].append("32X identified from header; SH-2 analysis and bank mapping are not provided")
    result["regions"] = [{"name": "cartridge header", "kind": "header", "file_offset": 0x100, "file_size": 0x100}]
    stored = int.from_bytes(data[0x18e:0x190], "big")
    # A file-wide sum is only comparable when the declared range starts at zero
    # and is fully present; never silently checksum a truncated or padded image.
    end = md["rom_end"] + 1
    if md["rom_start"] != 0 or md["rom_end"] < md["rom_start"] or end < 0x200 or end > len(data):
        result["valid"] = False
        result["warnings"].append("Declared ROM extent is invalid or incomplete")
    reset = md["reset_vector"]
    stack = md["initial_stack_pointer"]
    md["vector_plausibility"] = {"reset_in_declared_rom": md["rom_start"] <= reset <= md["rom_end"] and reset >= 0x200 and reset % 2 == 0,
                                 "stack_nonzero_even": stack != 0 and stack % 2 == 0}
    if not all(md["vector_plausibility"].values()):
        result["warnings"].append("Initial vectors are not conventionally plausible; execution has not been established")
    checksum = {"stored": stored, "computed": None, "matches": None,
                "range_start": 0x200, "range_end_exclusive": end}
    if md["rom_start"] == 0 and 0x200 <= end <= len(data) and end % 2 == 0:
        checksum["computed"] = (sum(data[0x200:end:2]) * 256 + sum(data[0x201:end:2])) & 0xffff
        checksum["matches"] = checksum["computed"] == stored
        if not checksum["matches"]:
            result["warnings"].append("Genesis checksum mismatch over the declared ROM range")
    else:
        result["warnings"].append("Genesis checksum not computed: declared ROM range is unavailable or unsuitable")
    if md["rom_end"] < md["rom_start"] or md["ram_end"] < md["ram_start"]:
        result["warnings"].append("A declared address range is inverted")
    md["checksum"] = checksum
    return result


def parse_sms(data: bytes) -> dict | None:
    """Identify Sega 8-bit headers, leaving mapper and execution state unknown."""
    _validate_input(data)
    offsets = [off for off in (0x7ff0, 0x3ff0, 0x1ff0)
               if data[off:off + 8] == b"TMR SEGA"]
    if not offsets:
        return None
    off = offsets[0]
    result = _base("sega-sms", "Sega Master System / Game Gear", "z80", 8, "little", off)
    result["metadata"] = {"signature": "TMR SEGA", "candidate_offsets": offsets}
    if len(offsets) > 1:
        result["warnings"].append("Multiple Sega headers found; highest standard offset selected")
    if len(data) < off + 16:
        result["valid"] = False
        result["warnings"].append("Truncated Sega 8-bit header")
        return result
    header = data[off:off + 16]
    region, size = header[15] >> 4, header[15] & 15
    if region in (3, 4):
        result["platform"] = "Sega Master System"
    elif region in (5, 6, 7):
        result["platform"] = "Sega Game Gear"
    digits = (header[13] >> 4, header[13] & 15, header[12] >> 4, header[12] & 15)
    product = (header[14] >> 4) * 10000 + sum(d * 10 ** (3 - i) for i, d in enumerate(digits)) if all(d < 10 for d in digits) and header[14] >> 4 < 10 else None
    result["metadata"].update({"region_code": region, "region": _SMS_REGIONS.get(region),
                          "size_code": size, "declared_size": _SMS_SIZES.get(size),
                          "product_code": product, "product_raw": header[12:15].hex(),
                          "version": header[14] & 15,
                          "checksum_stored": int.from_bytes(header[10:12], "little")})
    result["regions"] = [{"name": "cartridge header", "kind": "header", "file_offset": off, "file_size": 16}]
    if product is None:
        result["valid"] = False
        result["warnings"].append("Product code contains non-BCD digits")
    if region not in _SMS_REGIONS:
        result["valid"] = False
        result["warnings"].append("Unknown region code; platform is ambiguous")
    if size not in _SMS_SIZES:
        result["valid"] = False
        result["warnings"].append("Unknown size/checksum-range code")
    elif _SMS_SIZES[size] > len(data):
        result["valid"] = False
        result["warnings"].append("Declared size exceeds available file bytes")
    result["warnings"].append("SMS/GG checksum and mapper behavior have not been validated")
    return result
