"""Conservative, file-offset-only identification of conventional SNES ROM headers.

Header layout: https://snes.nesdev.org/wiki/ROM_header
No checksum over the ROM or CPU-to-file address mapping is inferred here.
"""

_MAX_SIZE = 64 * 1024 * 1024
# Extended LoROM uses the conventional low header with an enlarged image;
# no distinct mapping can be established from that header alone.
_LAYOUTS = ((0x7FC0, "LoROM", (0x20, 0x30, 0x22, 0x32, 0x23, 0x33)),
            (0xFFC0, "HiROM", (0x21, 0x31)),
            (0x40FFC0, "ExHiROM", (0x25, 0x35)))


def _candidate(data, copier, offset, layout, modes):
    pos = copier + offset
    if pos + 32 > len(data):
        return None
    h = data[pos:pos + 32]
    title = h[:21]
    # Multiple independent signals are necessary: an appropriate map byte,
    # a plausible title, and a nontrivial complementary checksum pair.
    complement = int.from_bytes(h[28:30], "little")
    checksum = int.from_bytes(h[30:32], "little")
    if (h[21] not in modes or not title.strip(b" \x00") or
            sum(32 <= b <= 126 for b in title) < 16 or
            checksum in (0, 0xFFFF) or (checksum ^ complement) != 0xFFFF):
        return None
    vector = int.from_bytes(data[pos + 0x3C:pos + 0x3E], "little") if pos + 0x3E <= len(data) else None
    return {"header_offset": pos, "copier_header_size": copier, "layout": layout,
            "title": title.decode("ascii", errors="replace").rstrip(" \x00"),
            "map_mode": h[21], "chipset": h[22], "rom_size_code": h[23],
            "ram_size_code": h[24], "region": h[25], "version": h[27],
            "checksum_complement": complement, "checksum": checksum,
            "reset_vector": vector}


def parse_snes(data: bytes) -> dict | None:
    """Identify plausible headers; a match is heuristic, never a mapping proof."""
    if not isinstance(data, bytes):
        raise ValueError("SNES input must be bytes")
    if len(data) > _MAX_SIZE:
        raise ValueError("SNES input exceeds the 64 MiB parsing limit")
    candidates = []
    for copier in (0, 512):
        for offset, layout, modes in _LAYOUTS:
            c = _candidate(data, copier, offset, layout, modes)
            if c is not None:
                candidates.append(c)
    if not candidates:
        return None
    warnings = ["ROM checksum was not verified; only the header checksum/complement pair was checked."]
    valid = True
    if len(candidates) != 1:
        warnings.append("Multiple plausible headers; layout and copier header are ambiguous.")
        valid = False
    c = candidates[0]
    if c["reset_vector"] is None:
        warnings.append("Truncated header: reset vector is unavailable.")
        valid = False
    elif c["reset_vector"] < 0x8000:
        warnings.append("Reset vector points below the conventional ROM window.")
        valid = False
    for key, label in (("rom_size_code", "ROM"), ("ram_size_code", "RAM")):
        code = c[key]
        if code > 16:
            warnings.append(f"Unreasonable declared {label} size code: {code}.")
            valid = False
    rom_size = (1024 << c["rom_size_code"]) if c["rom_size_code"] <= 16 else None
    ram_size = (0 if c["ram_size_code"] == 0 else 1024 << c["ram_size_code"]) if c["ram_size_code"] <= 16 else None
    observed_size = len(data) - c["copier_header_size"]
    if rom_size is not None and observed_size < rom_size:
        warnings.append("File is smaller than the declared rounded ROM capacity; this may be a non-power-of-two image or truncation.")
    metadata = dict(c, declared_rom_size=rom_size, declared_rom_capacity=rom_size,
                    observed_rom_size=observed_size, declared_ram_size=ram_size,
                    checksum_verified=False, candidates=candidates)
    regions = []
    if len(candidates) == 1:
        if c["copier_header_size"]:
            regions.append({"name": "Copier header", "kind": "copier_header", "file_offset": 0, "file_size": 512})
        regions.append({"name": "ROM data", "kind": "rom", "file_offset": c["copier_header_size"],
                        "file_size": len(data) - c["copier_header_size"]})
    return {"format": "SNES ROM", "family": "console ROM", "platform": "SNES",
            "arch": "w65c816", "bits": 16, "endian": "little",
            "header_offset": c["header_offset"] if len(candidates) == 1 else None,
            "valid": valid, "detection": "heuristic", "metadata": metadata,
            "regions": regions, "warnings": warnings}
