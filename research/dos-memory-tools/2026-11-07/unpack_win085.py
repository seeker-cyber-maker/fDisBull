"""Reconstruct the supplied Win32 Game Wizard0.85 installer without running it.

This target-specific research reader pins the inspected installer hash. It
parses the proven CreateInstall framing and calls the separately authored,
bounded bitstream decoder. Payload files remain caller-owned private inputs;
the output JSON records hashes/ranges rather than original bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

from createinstall_decoder import decode
from intake_versions import executable_header, identity


EXPECTED_SHA256 = "60c5ffc4c4bb78282a1257a87ddb9ce824889578039a30247d7ef404bac9aaac"
EXPECTED_SIZE = 94830
DLL_START = 0x2000
DLL_READ_SIZE = 0x8214
CONFIG_START = DLL_START + DLL_READ_SIZE
CONFIG_HEADER_SIZE = 0x4F


def local_name(raw: str) -> str:
    # The first file is declared using the installer's quoted path variable.
    # Interpret only this observed prefix; never evaluate installer commands.
    if raw.startswith('"%installpath%\\') and raw.endswith('"'):
        raw = raw[len('"%installpath%\\'):-1]
    name = PurePosixPath(raw.replace("\\", "/"))
    if name.is_absolute() or len(name.parts) != 1 or name.name in (".", ".."):
        raise ValueError("Unexpected member path")
    if ":" in raw or any(ord(c) < 32 for c in raw):
        raise ValueError("Unsafe member path")
    return name.name


def read_installer(source: Path) -> bytes:
    """Take one bounded immutable snapshot of the caller's original."""
    with source.open("rb") as stream:
        data = stream.read(EXPECTED_SIZE + 1)
    if len(data) != EXPECTED_SIZE or hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise ValueError("This reader requires the exact inspected0.85 installer")
    return data


def inspect_installer(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """Parse the entire pinned container without creating files or executing it.

    The second return value holds private payload bytes in memory. It is never
    part of the JSON report. A witness derives its coverage from this complete
    parse instead of trusting a caller-supplied list of streams.
    """
    if len(data) != EXPECTED_SIZE or hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise ValueError("This reader requires the exact inspected0.85 installer")
    payloads = {}
    dll = decode(data[DLL_START:CONFIG_START], output_limit=0x10F00)
    padding = data[DLL_START + dll.consumed_bytes:CONFIG_START]
    if padding != b"0" * 93:
        raise ValueError("Unexpected installer DLL padding")
    dll_header = executable_header(dll.data)
    if dll_header["format"] != "PE" or not (int(dll_header["pe_characteristics"], 16) & 0x2000):
        raise ValueError("Decoded installer engine is not a PE DLL")
    payloads["instcrin.dll"] = dll.data
    declared_file_length, declared_expanded, settings_size = struct.unpack_from("<III", data, CONFIG_START)
    if declared_file_length != len(data):
        raise ValueError("Installer file-length mismatch")
    records_start = CONFIG_START + CONFIG_HEADER_SIZE + settings_size
    if records_start >= len(data):
        raise ValueError("Settings extent out of bounds")
    streams = [{"name": "instcrin.dll", "compressed_start": DLL_START,
                "compressed_bytes": dll.consumed_bytes, "compressed_bits": dll.consumed_bits,
                "decoded_size": len(dll.data), "sha256": identity(dll.data)["sha256"],
                "executable": dll_header, "role": "installer engine, separate from installed member total"}]
    pos = records_start
    stack = []
    seen = {"instcrin.dll"}
    records = []
    total = 0
    ended = False
    while pos < len(data):
        if len(records) >= 32 or pos + 17 > len(data):
            raise ValueError("Record budget or header extent exceeded")
        start = pos
        kind, attributes, timestamp, flag, name_size = struct.unpack_from("<HIQBH", data, pos)
        pos += 17
        record = {"header_offset": start, "kind": kind, "attributes": attributes,
                  "filetime": timestamp, "flag": flag, "declared_name_bytes": name_size}
        if kind == 4:
            if stack or (attributes, timestamp, flag, name_size) != (0, 0, 0, 0):
                raise ValueError("Unexpected end-of-archive record")
            record["action"] = "end_archive"
            records.append(record)
            ended = True
            break
        if kind == 3:
            if not stack:
                raise ValueError("End-directory without an open directory")
            folder = stack.pop()
            if (attributes, timestamp, flag, name_size) != folder[1:]:
                raise ValueError("End-directory identity mismatch")
            record.update(action="end_directory", directory=folder[0])
            records.append(record)
            continue
        if kind not in (1, 2) or pos + name_size > len(data):
            raise ValueError("Unsupported record or name extent")
        raw_name = data[pos:pos + name_size].decode("cp1252")
        pos += name_size
        name = local_name(raw_name)
        record["declared_name"] = raw_name
        if kind == 2:
            if not attributes & 0x10:
                raise ValueError("Directory flag missing")
            stack.append((name, attributes, timestamp, flag, name_size))
            record.update(action="directory", directory=name)
            records.append(record)
            continue
        if attributes & 0x10 or pos + 4 > len(data):
            raise ValueError("Invalid file record")
        declared_length = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if declared_length > 1024 * 1024:
            raise ValueError("Decoded member budget exceeded")
        decoded = decode(data[pos:], output_limit=declared_length)
        if len(decoded.data) != declared_length:
            raise ValueError("Decoded member-length mismatch")
        relative = PurePosixPath(*(item[0] for item in stack), name)
        key = relative.as_posix().casefold()
        if key in seen:
            raise ValueError("Duplicate output name")
        seen.add(key)
        payloads[relative.as_posix()] = decoded.data
        header = executable_header(decoded.data)
        record.update(action="file", path=relative.as_posix(), decoded_size=declared_length,
                      compressed_start=pos, compressed_bytes=decoded.consumed_bytes,
                      compressed_bits=decoded.consumed_bits, **identity(decoded.data), executable=header)
        streams.append({"name": relative.as_posix(), "compressed_start": pos,
                        "compressed_bytes": decoded.consumed_bytes, "compressed_bits": decoded.consumed_bits,
                        "decoded_size": declared_length, "sha256": identity(decoded.data)["sha256"],
                        "executable": header, "role": "installed payload"})
        pos += decoded.consumed_bytes
        total += declared_length
        records.append(record)
    if not ended or pos != len(data) or total != declared_expanded or len(streams) != 9:
        raise ValueError("Container endpoint or total decoded-length mismatch")
    report = {"schema": "gw-win085-static-createinstall-payload-1", "source": identity(data),
              "scope": "Hash-pinned static reconstruction; no installer or payload executed on host",
              "installer_engine_extent": [DLL_START, CONFIG_START],
              "installer_engine_padding_bytes": len(padding),
              "config_header_extent": [CONFIG_START, CONFIG_START + CONFIG_HEADER_SIZE],
              "config_strings_extent": [CONFIG_START + CONFIG_HEADER_SIZE, records_start],
              "records_start": records_start, "records": records, "streams": streams,
              "final_offset": pos, "file_length": len(data), "remaining_bytes": len(data) - pos,
              "decoded_member_bytes": total, "declared_uncompressed": declared_expanded,
              "all_declared_lengths_and_eos_boundaries_verified": True,
              "stored_payload_crc_available": False}
    return report, payloads


def unpack(source: Path, output: Path) -> dict:
    report, payloads = inspect_installer(read_installer(source))
    output.mkdir(parents=True, exist_ok=False)
    raw_dir = output / "files"
    raw_dir.mkdir()
    for name, data in payloads.items():
        target = raw_dir.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    (output / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("new_output_directory", type=Path)
    args = parser.parse_args()
    report = unpack(args.installer, args.new_output_directory)
    print(json.dumps({"output": str(args.new_output_directory), "installed_files": len(report["streams"]) - 1,
                      "decoded_member_bytes": report["decoded_member_bytes"], "remaining_bytes": report["remaining_bytes"]}))


if __name__ == "__main__":
    main()
