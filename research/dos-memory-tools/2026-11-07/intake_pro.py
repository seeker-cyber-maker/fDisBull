"""Bounded private intake of the supplied Game Wizard Pro distribution containers.

Original archives are read only. Extracted files remain in the chosen private
output directory; the JSON manifest contains identities and extraction metadata.
This script does not execute any program or infer publisher authenticity.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

INPUTS = {
    "donor30": "gw30.zip",
    "english30": "Game Wizard 32 Pro.ver.3.0.English.zip",
    "english30a": "Game Wizard 32 Pro.ver.3.0a.English.rar",
    "ima30a": "GameWizard32Pro30AIMA.zip",
    "dfi30a": "GameWizard32Pro30Adfi.zip",
}
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_MEMBERS = 4096


def identity(data: bytes) -> dict:
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def member_path(name: str) -> PurePosixPath:
    # DOS archives sometimes use a backslash; normalize it before validation.
    value = name.replace("\\", "/")
    p = PurePosixPath(value)
    if (not value or "\0" in value or value.startswith("/") or ":" in value
            or ".." in p.parts or not p.parts):
        raise ValueError("unsafe archive member path: " + repr(name))
    return p


def zip_members(path: Path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > MAX_MEMBERS:
            raise ValueError("member budget exceeded")
        for entry in archive.infolist():
            p = member_path(entry.filename)
            mode = entry.external_attr >> 16
            if entry.is_dir():
                yield p, None, {"kind": "directory"}
                continue
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("archive member is not a regular file: " + entry.filename)
            if entry.flag_bits & 1:
                raise ValueError("encrypted member unsupported")
            if not 0 <= entry.file_size <= MAX_FILE:
                raise ValueError("member size budget exceeded")
            data = archive.read(entry)  # zipfile validates the stored CRC32.
            if len(data) != entry.file_size:
                raise ValueError("member length mismatch")
            yield p, data, {"kind": "file", "crc32": f"{entry.CRC:08x}",
                            "zip_crc32_validated": True,
                            "archive_time": list(entry.date_time)}


def rar_members(path: Path):
    name = ctypes.util.find_library("archive")
    if not name:
        raise RuntimeError("system libarchive unavailable")
    lib = ctypes.CDLL(name)
    declarations = {
        "archive_read_new": ([], ctypes.c_void_p),
        "archive_read_support_filter_all": ([ctypes.c_void_p], ctypes.c_int),
        "archive_read_support_format_all": ([ctypes.c_void_p], ctypes.c_int),
        "archive_read_open_filename": ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
        "archive_read_next_header": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
        "archive_entry_pathname": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_entry_filetype": ([ctypes.c_void_p], ctypes.c_uint),
        "archive_entry_size": ([ctypes.c_void_p], ctypes.c_int64),
        "archive_entry_symlink": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_entry_hardlink": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_read_data": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t], ctypes.c_ssize_t),
        "archive_read_data_skip": ([ctypes.c_void_p], ctypes.c_int),
        "archive_error_string": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_read_free": ([ctypes.c_void_p], ctypes.c_int),
    }
    for method, (args, result) in declarations.items():
        fn = getattr(lib, method)
        fn.argtypes, fn.restype = args, result
    handle = lib.archive_read_new()
    if not handle:
        raise RuntimeError("libarchive allocation failed")

    def check(status):
        if status < 0:
            error = lib.archive_error_string(handle)
            raise ValueError(error.decode("utf-8", "replace") if error else "libarchive read error")

    try:
        check(lib.archive_read_support_filter_all(handle))
        check(lib.archive_read_support_format_all(handle))
        check(lib.archive_read_open_filename(handle, bytes(path), 65536))
        count = 0
        while True:
            entry = ctypes.c_void_p()
            status = lib.archive_read_next_header(handle, ctypes.byref(entry))
            if status == 1:
                break
            check(status)
            count += 1
            if count > MAX_MEMBERS:
                raise ValueError("member budget exceeded")
            raw_name = lib.archive_entry_pathname(entry)
            if not raw_name:
                raise ValueError("member name missing")
            p = member_path(raw_name.decode("utf-8", "strict"))
            if lib.archive_entry_symlink(entry) or lib.archive_entry_hardlink(entry):
                raise ValueError("archive links unsupported")
            kind = lib.archive_entry_filetype(entry)
            if kind == stat.S_IFDIR:
                check(lib.archive_read_data_skip(handle))
                yield p, None, {"kind": "directory"}
                continue
            if kind != stat.S_IFREG:
                raise ValueError("archive member is not a regular file")
            declared = lib.archive_entry_size(entry)
            if not 0 <= declared <= MAX_FILE:
                raise ValueError("member size budget exceeded")
            buffer = ctypes.create_string_buffer(65536)
            pieces, size = [], 0
            while True:
                got = lib.archive_read_data(handle, buffer, len(buffer))
                check(got)
                if not got:
                    break
                size += got
                if size > MAX_FILE or size > declared:
                    raise ValueError("member exceeds declared length/budget")
                pieces.append(buffer.raw[:got])
            data = b"".join(pieces)
            if len(data) != declared:
                raise ValueError("member length mismatch")
            yield p, data, {"kind": "file", "reader": name,
                            "declared_length_validated": True,
                            "archive_reader_completed_without_error": True}
    finally:
        lib.archive_read_free(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "gamewizard-pro-container-intake-1", "archives": [],
              "limits": {"max_file": MAX_FILE, "max_total_per_archive": MAX_TOTAL,
                         "max_members": MAX_MEMBERS},
              "claim": "Exact identities and bounded extraction only; no authenticity or program execution claim"}
    for label, filename in INPUTS.items():
        original = args.source / filename
        row = {"label": label, "name": filename, **identity(original.read_bytes()), "members": []}
        out = args.output / label
        out.mkdir()
        total, seen = 0, set()
        reader = rar_members if original.suffix.lower() == ".rar" else zip_members
        for p, data, metadata in reader(original):
            key = p.as_posix().casefold()
            if key in seen:
                raise ValueError("ambiguous duplicate archive member: " + p.as_posix())
            seen.add(key)
            target = out.joinpath(*p.parts)
            if data is None:
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError("aggregate extraction budget exceeded")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            row["members"].append({"path": p.as_posix(), **identity(data), **metadata})
        row["total_file_bytes"] = total
        row["member_count"] = len(row["members"])
        report["archives"].append(row)
        print(json.dumps({"label": label, "files": row["member_count"], "uncompressed_bytes": total}), flush=True)
    (args.output / "archive_inventory.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
