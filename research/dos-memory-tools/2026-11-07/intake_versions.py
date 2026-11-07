"""Read-only intake of supplied Game Wizard distributions.

Original archives are never modified. ZIP members are materialized only in a
new output directory after path, link, encryption, and byte-budget checks.
Reading each ZIP member verifies its stored CRC32 through Python's zipfile.
Nested ZIPs are inventoried separately, preserving their container identities.
No input executable is launched. Output JSON contains identities, not payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import zipfile


ARCHIVES = {
    "pro240": "Game Wizard Pro.ver.2.40.English.zip",
    "share240": "Game Wizard shareware.ver.2.40.English.zip",
    "share260": "Game Wizard shareware.ver.2.60.English.zip",
    "win085": "Game Wizard for Windows.ver.0.85.English.zip",
}
MEMBER_LIMIT = 16 * 1024 * 1024
ARCHIVE_LIMIT = 64 * 1024 * 1024
MAX_MEMBERS = 4096


def identity(data: bytes) -> dict:
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def executable_header(data: bytes) -> dict:
    if not data.startswith((b"MZ", b"ZM")) or len(data) < 28:
        return {"format": "not_MZ"}
    fields = struct.unpack_from("<14H", data)
    result = {
        "format": "MZ",
        "mz_header_bytes": fields[4] * 16,
        "mz_relocations": fields[3],
        "mz_ip": fields[10],
        "mz_cs": fields[11],
        "mz_ss": fields[7],
        "mz_sp": fields[8],
        "mz_declared_file_size": ((fields[2] - 1) * 512 + (fields[1] or 512)) if fields[2] else 0,
    }
    # A 32-byte DOS header does not contain e_lfanew; bytes at0x3c are then
    # ordinary load-image data and must not be presented as a header pointer.
    if result["mz_header_bytes"] >= 64 and len(data) >= 64:
        secondary = struct.unpack_from("<I", data, 0x3C)[0]
        result["secondary_header_offset"] = secondary
        if secondary <= len(data) - 2 and data[secondary:secondary + 2] in (b"NE", b"LE", b"LX"):
            result["format"] = data[secondary:secondary + 2].decode("ascii")
        elif secondary <= len(data) - 24 and data[secondary:secondary + 4] == b"PE\0\0":
            machine, nsections, timestamp, _, _, optional_size, characteristics = struct.unpack_from("<HHIIIHH", data, secondary + 4)
            result.update(format="PE", pe_machine=hex(machine), pe_sections=nsections,
                          pe_timestamp=timestamp, pe_characteristics=hex(characteristics))
            optional = secondary + 24
            if optional_size >= 70 and optional + optional_size <= len(data):
                result.update(pe_optional_magic=hex(struct.unpack_from("<H", data, optional)[0]),
                              pe_entry_rva=hex(struct.unpack_from("<I", data, optional + 16)[0]),
                              pe_subsystem=struct.unpack_from("<H", data, optional + 68)[0])
            sections = []
            table = optional + optional_size
            if table + nsections * 40 <= len(data):
                for i in range(nsections):
                    pos = table + i * 40
                    name = data[pos:pos + 8].split(b"\0", 1)[0].decode("ascii", "replace")
                    vsize, rva, raw_size, raw_ptr = struct.unpack_from("<IIII", data, pos + 8)
                    sections.append({"name": name, "virtual_size": vsize, "rva": rva,
                                     "raw_size": raw_size, "raw_offset": raw_ptr,
                                     "raw_extent_within_file": raw_ptr + raw_size <= len(data)})
            result["pe_section_table"] = sections
    return result


def extract_zip(path: Path, destination: Path, label: str, depth: int = 0) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    report = {"label": label, "archive_name": path.name, **identity(path.read_bytes()),
              "members": [], "nested_archives": []}
    seen = set()
    total = 0
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > MAX_MEMBERS:
            raise ValueError("Archive member budget exceeded")
        for entry in archive.infolist():
            name = entry.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or any(p in ("", ".", "..") or ":" in p for p in parts):
                raise ValueError("Unsafe member path: " + repr(entry.filename))
            if any(ord(c) < 32 for c in name):
                raise ValueError("Control character in member name")
            normalized = "/".join(parts)
            if normalized.casefold() in seen:
                raise ValueError("Ambiguous case-insensitive member: " + normalized)
            seen.add(normalized.casefold())
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("Unsupported ZIP special member")
            if entry.flag_bits & 1:
                raise ValueError("Encrypted ZIP member")
            target = destination.joinpath(*parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not 0 <= entry.file_size <= MEMBER_LIMIT:
                raise ValueError("Member byte budget exceeded")
            total += entry.file_size
            if total > ARCHIVE_LIMIT:
                raise ValueError("Archive byte budget exceeded")
            data = archive.read(entry)
            if len(data) != entry.file_size:
                raise ValueError("Incorrect expanded length")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
            record = {"name": normalized, **identity(data), "zip_crc32": f"{entry.CRC:08x}",
                      "zip_timestamp": list(entry.date_time), "crc32_verified": True,
                      "executable": executable_header(data)}
            report["members"].append(record)
            if normalized.lower().endswith(".zip"):
                if depth >= 2:
                    raise ValueError("Nested archive depth exceeded")
                report["nested_archives"].append(extract_zip(target, destination / (target.stem + "_contents"),
                                                            label + "/" + normalized, depth + 1))
    report["expanded_member_bytes"] = total
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives_directory", type=Path)
    parser.add_argument("new_output_directory", type=Path)
    args = parser.parse_args()
    args.new_output_directory.mkdir(parents=True, exist_ok=False)
    result = {"schema": "gw-older-windows-intake-1", "scope": "Static read-only archive/header inspection; no original program execution",
              "limits": {"member_bytes": MEMBER_LIMIT, "archive_bytes": ARCHIVE_LIMIT, "nested_depth": 2},
              "archives": []}
    for label, name in ARCHIVES.items():
        result["archives"].append(extract_zip(args.archives_directory / name, args.new_output_directory / label, label))
    output = args.new_output_directory / "intake.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
