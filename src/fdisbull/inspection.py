"""Bounded static container metadata and file-backed strings; never executes code."""
from __future__ import annotations

import re
import struct

import lief

MAX_INPUT = 64 * 1024 * 1024
MAX_ITEMS = 10000
MAX_STRING_TEXT = 1024 * 1024


def _input(data: bytes) -> bytes:
    if not isinstance(data, bytes):
        raise ValueError("binary inspection requires bytes")
    if len(data) > MAX_INPUT:
        raise ValueError("binary inspection input exceeds 64 MiB")
    return data


def identify_header(data: bytes) -> dict:
    """Identify headers by magic and validate the structural header extents.

    ``valid`` means the recognized header fits, not that the file can execute.
    Unsupported containers can be identified without being loaded.
    """
    data = _input(data)
    h = {"format": "unknown", "family": "raw", "valid": False, "bits": None,
         "arch": None, "endian": None, "header_offset": 0,
         "source": "header bytes", "warnings": []}

    def need(end: int, message: str) -> bool:
        if end > len(data):
            h["warnings"].append(message)
            return False
        return True

    if data.startswith(b"MZ"):
        h.update(format="DOS MZ", family="DOS", bits=16, arch="x86", endian="little")
        if not need(28, "truncated DOS MZ header"):
            return h
        header_size = int.from_bytes(data[8:10], "little") * 16
        h["valid"] = header_size >= 28 and need(header_size, "DOS header paragraphs exceed file")
        if header_size < 28:
            h["warnings"].append("invalid DOS header paragraph count")
        # PE recognition does not depend on a DOS stub being executable: some
        # valid minimal PE images leave DOS-only paragraph fields zero.
        if len(data) < 64:
            return h
        offset = int.from_bytes(data[60:64], "little")
        if not offset:
            return h
        h["header_offset"] = offset
        if offset < 64:
            h["valid"] = False
            h["warnings"].append("secondary header offset overlaps DOS header")
            return h
        if not need(offset + 2, "truncated secondary executable header"):
            h["valid"] = False
            return h
        signature = data[offset:offset + 4]
        if signature[:2] in (b"NE", b"LE", b"LX"):
            kind = signature[:2].decode("ascii")
            h.update(format=kind, family="DOS", bits=16 if kind == "NE" else 32)
            h["valid"] = need(offset + (64 if kind == "NE" else 196), f"truncated {kind} header")
            return h
        if signature != b"PE\0\0":
            h["warnings"].append("unrecognized secondary header; DOS MZ identification retained")
            return h
        h.update(format="PE", family="PE", valid=False, bits=None)
        if not need(offset + 24, "truncated PE COFF header"):
            return h
        machine, sections = struct.unpack_from("<HH", data, offset + 4)
        optional_size = struct.unpack_from("<H", data, offset + 20)[0]
        optional = offset + 24
        h["arch"] = {0x14C: "x86", 0x8664: "x86", 0xAA64: "arm64"}.get(machine, f"machine:{machine:#x}")
        if optional_size < 2:
            h["warnings"].append("PE optional header has no complete magic")
            return h
        if not need(optional + optional_size, "truncated PE optional header"):
            return h
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic not in (0x10B, 0x20B):
            h["warnings"].append("unsupported PE optional-header magic")
            return h
        h.update(format="PE32+" if magic == 0x20B else "PE32", bits=64 if magic == 0x20B else 32)
        minimum = 112 if magic == 0x20B else 96
        if optional_size < minimum:
            h["warnings"].append("PE optional header is smaller than its format minimum")
            return h
        imagebase = struct.unpack_from("<Q" if magic == 0x20B else "<I", data, optional + (24 if magic == 0x20B else 28))[0]
        h["imagebase"] = imagebase
        h["entrypoint"] = imagebase + struct.unpack_from("<I", data, optional + 16)[0]
        h["section_count"] = sections
        if sections > 4096:
            h["warnings"].append("PE section count exceeds inspection limit")
            return h
        h["valid"] = need(optional + optional_size + sections * 40, "truncated PE section table")
        return h
    if data.startswith(b"\x7fELF"):
        h.update(format="ELF", family="ELF")
        if not need(16, "truncated ELF identification"):
            return h
        cls, endian = data[4], data[5]
        if cls not in (1, 2) or endian not in (1, 2) or data[6] != 1:
            h["warnings"].append("invalid ELF class, endianness or version")
            return h
        h.update(bits=32 if cls == 1 else 64, endian="little" if endian == 1 else "big")
        prefix = "<" if endian == 1 else ">"
        minimum = 52 if cls == 1 else 64
        if not need(minimum, "truncated ELF file header"):
            return h
        machine = struct.unpack_from(prefix + "H", data, 18)[0]
        h["arch"] = {3: "x86", 62: "x86", 183: "arm64", 40: "arm"}.get(machine, f"machine:{machine}")
        h["entrypoint"] = struct.unpack_from(prefix + ("I" if cls == 1 else "Q"), data, 24)[0]
        if cls == 1:
            phoff, shoff = struct.unpack_from(prefix + "II", data, 28)
            ehsize, phsize, phnum, shsize, shnum = struct.unpack_from(prefix + "HHHHH", data, 40)
        else:
            phoff, shoff = struct.unpack_from(prefix + "QQ", data, 32)
            ehsize, phsize, phnum, shsize, shnum = struct.unpack_from(prefix + "HHHHH", data, 52)
        if ehsize < minimum or (phnum and phsize < (32 if cls == 1 else 56)) or (shnum and shsize < (40 if cls == 1 else 64)):
            h["warnings"].append("invalid ELF header/table entry sizes")
            return h
        h["valid"] = (need(ehsize, "truncated ELF declared header") and
                      need(phoff + phsize * phnum, "truncated ELF program-header table") and
                      need(shoff + shsize * shnum, "truncated ELF section-header table"))
        if phnum == 0xFFFF:
            h["valid"] = False
            h["warnings"].append("extended ELF program-header counts are not supported")
        return h
    magic = data[:4]
    thin = {b"\xce\xfa\xed\xfe": (32, "little"), b"\xcf\xfa\xed\xfe": (64, "little"),
            b"\xfe\xed\xfa\xce": (32, "big"), b"\xfe\xed\xfa\xcf": (64, "big")}
    fat = {b"\xca\xfe\xba\xbe": (32, "big"), b"\xbe\xba\xfe\xca": (32, "little"),
           b"\xca\xfe\xba\xbf": (64, "big"), b"\xbf\xba\xfe\xca": (64, "little")}
    if magic in thin:
        bits, endian = thin[magic]
        h.update(format="Mach-O", family="Mach-O", bits=bits, endian=endian)
        size = 32 if bits == 64 else 28
        if not need(size, "truncated Mach-O header"):
            return h
        prefix = "<" if endian == "little" else ">"
        cpu, _, _, count, command_size = struct.unpack_from(prefix + "IIIII", data, 4)
        h["arch"] = {7: "x86", 0x1000007: "x86", 0x100000C: "arm64", 12: "arm"}.get(cpu, f"cpu:{cpu:#x}")
        if count > 4096 or not need(size + command_size, "truncated Mach-O load commands"):
            h["warnings"].append("Mach-O load-command limits exceeded") if count > 4096 else None
            return h
        position = size
        for _ in range(count):
            if position + 8 > size + command_size:
                h["warnings"].append("truncated Mach-O command header")
                return h
            length = struct.unpack_from(prefix + "I", data, position + 4)[0]
            if length < 8 or position + length > size + command_size:
                h["warnings"].append("invalid Mach-O command extent")
                return h
            position += length
        h["valid"] = True
        return h
    if magic in fat:
        bits, endian = fat[magic]
        h.update(format="Mach-O fat", family="Mach-O", endian=endian)
        if not need(8, "truncated fat Mach-O header"):
            return h
        prefix = "<" if endian == "little" else ">"
        count = struct.unpack_from(prefix + "I", data, 4)[0]
        stride = 32 if bits == 64 else 20
        if not 1 <= count <= 128:
            h["warnings"].append("fat Mach-O slice count is invalid or exceeds 128")
            return h
        h["slice_count"] = count
        if not need(8 + stride * count, "truncated fat Mach-O slice table"):
            return h
        for index in range(count):
            position = 8 + index * stride + 8
            offset, size = struct.unpack_from(prefix + ("QQ" if bits == 64 else "II"), data, position)
            if not need(offset + size, "fat Mach-O slice exceeds file"):
                return h
        h["valid"] = True
    return h


def _strings(data: bytes, mappings: list[tuple[int, int, int]], warnings: list[str]) -> list[dict]:
    found = []
    text_budget = MAX_STRING_TEXT
    for pattern, encoding in [(rb"[\x20-\x7e]{4,}", "ascii"), (rb"(?:[\x20-\x7e]\x00){4,}", "utf-16le")]:
        for match in re.finditer(pattern, data):
            if len(found) >= MAX_ITEMS or text_budget <= 0:
                warnings.append("string extraction capped at 10000 entries or 1 MiB text")
                return sorted(found, key=lambda item: (item["file_offset"], item["encoding"]))
            raw = match.group()
            unit = 2 if encoding == "utf-16le" else 1
            limit = min(4096, text_budget) * unit
            text = raw[:limit].decode(encoding)
            address = next((va + match.start() - offset for offset, length, va in mappings
                            if offset <= match.start() and match.end() <= offset + length), None)
            found.append({"text": text, "encoding": encoding, "file_offset": match.start(),
                          "size": len(raw), "address": address, "truncated": len(raw) > limit})
            text_budget -= len(text)
    return sorted(found, key=lambda item: (item["file_offset"], item["encoding"]))


def inspect_binary(data: bytes) -> dict:
    """Inspect metadata and ASCII/ASCII-range UTF-16LE strings from file bytes.

    Unresolved addresses are None. Returned addresses are preferred static VAs,
    never file offsets mislabeled as VAs or guessed runtime bindings.
    """
    data = _input(data)
    header = identify_header(data)
    result = {"header": header, "sections": [], "imports": [], "exports": [],
              "strings": [], "warnings": list(header["warnings"])}
    warnings = result["warnings"]
    mappings = []
    if not header["valid"] or header["format"] not in ("PE32", "PE32+", "ELF", "Mach-O"):
        warnings.append("structural metadata unavailable for this header; no address mapping inferred")
        result["strings"] = _strings(data, mappings, warnings)
        return result
    try:
        binary = lief.parse(data)
        if binary is None:
            raise ValueError("LIEF rejected the executable")
        if isinstance(binary, lief.PE.Binary):
            base = int(binary.optional_header.imagebase)
            header_size = min(len(data), int(binary.optional_header.sizeof_headers))
            mappings.append((0, header_size, base))
            for section in binary.sections:
                flags = section.characteristics
                permissions = "".join(letter if flags & mask else "-" for letter, mask in [("r", 0x40000000), ("w", 0x80000000), ("x", 0x20000000)])
                record = {"name": section.name, "virtual_address": base + int(section.virtual_address),
                          "virtual_size": int(section.virtual_size), "file_offset": int(section.pointerto_raw_data),
                          "file_size": int(section.sizeof_raw_data), "permissions": permissions}
                result["sections"].append(record)
                length = min(record["file_size"], max(0, len(data) - record["file_offset"]))
                mappings.append((record["file_offset"], length, record["virtual_address"]))
            for library in binary.imports:
                for entry in library.entries:
                    result["imports"].append({"module": library.name, "name": None if entry.is_ordinal else entry.name,
                        "ordinal": int(entry.ordinal) if entry.is_ordinal else None,
                        "address": base + int(entry.iat_address), "kind": "iat", "hint": None if entry.is_ordinal else int(entry.hint)})
                    if len(result["imports"]) >= MAX_ITEMS:
                        break
                if len(result["imports"]) >= MAX_ITEMS:
                    warnings.append("import list capped at 10000 entries")
                    break
            if binary.has_exports:
                for entry in binary.get_export().entries:
                    result["exports"].append({"name": entry.name or None,
                        "address": None if entry.is_forwarded else base + int(entry.address),
                        "ordinal": int(entry.ordinal), "forwarder": str(entry.forward_information) if entry.is_forwarded else None})
                    if len(result["exports"]) >= MAX_ITEMS:
                        warnings.append("export list capped at 10000 entries")
                        break
            warnings.append("PE imports describe normal IAT entries; delay-load imports are not enumerated")
        elif isinstance(binary, lief.ELF.Binary):
            for section in binary.sections:
                flags = int(section.flags)
                result["sections"].append({"name": section.name, "virtual_address": int(section.virtual_address),
                    "virtual_size": int(section.size), "file_offset": int(section.offset),
                    "file_size": 0 if section.type == lief.ELF.Section.TYPE.NOBITS else int(section.size),
                    "permissions": ("r" if flags & 2 else "-") + ("w" if flags & 1 else "-") + ("x" if flags & 4 else "-")})
            for segment in binary.segments:
                if segment.type == lief.ELF.Segment.TYPE.LOAD:
                    mappings.append((int(segment.file_offset), min(int(segment.physical_size), max(0, len(data) - int(segment.file_offset))), int(segment.virtual_address)))
            for symbol in binary.dynamic_symbols:
                if symbol.imported:
                    result["imports"].append({"module": None, "name": symbol.name or None, "ordinal": None, "address": None, "kind": "dynamic_symbol"})
                if symbol.exported:
                    result["exports"].append({"name": symbol.name or None, "address": int(symbol.value), "ordinal": None, "forwarder": None})
                if len(result["imports"]) + len(result["exports"]) >= MAX_ITEMS:
                    warnings.append("dynamic symbol lists capped at 10000 entries")
                    break
            warnings.append("ELF import slots and symbol-to-library bindings are unresolved; imports have address null")
        elif isinstance(binary, lief.MachO.Binary):
            for segment in binary.segments:
                if int(segment.file_size):
                    mappings.append((int(segment.file_offset), min(int(segment.file_size), max(0, len(data) - int(segment.file_offset))), int(segment.virtual_address)))
            for section in binary.sections:
                result["sections"].append({"name": section.name, "virtual_address": int(section.virtual_address),
                    "virtual_size": int(section.size), "file_offset": int(section.offset),
                    "file_size": 0 if str(section.type).endswith("ZEROFILL") else int(section.size),
                    "permissions": "unknown"})
            for symbol in binary.imported_symbols:
                result["imports"].append({"module": None, "name": symbol.name or None, "ordinal": None,
                                          "address": None, "kind": "imported_symbol"})
                if len(result["imports"]) >= MAX_ITEMS:
                    warnings.append("import list capped at 10000 entries")
                    break
            for symbol in binary.exported_symbols:
                result["exports"].append({"name": symbol.name or None, "address": int(symbol.value), "ordinal": None, "forwarder": None})
                if len(result["exports"]) >= MAX_ITEMS:
                    warnings.append("export list capped at 10000 entries")
                    break
            warnings.append("Mach-O import binding locations, library attribution and section permissions are unresolved")
        else:
            warnings.append("LIEF returned an unsupported metadata type")
    except Exception as exc:
        warnings.append(f"partial metadata: {type(exc).__name__}: {exc}")
    if len(result["sections"]) > MAX_ITEMS:
        result["sections"] = result["sections"][:MAX_ITEMS]
        warnings.append("section list capped at 10000 entries")
    result["strings"] = _strings(data, mappings, warnings)
    return result
