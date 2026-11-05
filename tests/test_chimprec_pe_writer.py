"""Acceptance for the bounded captured-PE import reconstruction writer."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from fdisbull.chimprec_pe import rebuild_pe_file
from fdisbull.chimprec_pe_image import map_pe_file, parse_pe
from fdisbull.chimprec_pe_imports import _checksum, parse_imports
from fdisbull.chimprec_pe_writer import rebuild_pe_image


def make_pe(bits: int, section_names=(".text", "UPX1")):
    """Return source file-layout bytes and a mapped capture with distinct cells."""
    image_base = 0x400000 if bits == 32 else 0x140000000
    pe = 0x80
    optional_size = 0xE0 if bits == 32 else 0xF0
    section_table = pe + 24 + optional_size
    headers = 0x200
    section_alignment = 0x1000
    file_alignment = 0x200
    section_count = len(section_names)
    size_image = 0x1000 * (section_count + 2)
    source = bytearray(headers + section_count * file_alignment)
    capture = bytearray(size_image)
    source[:2] = b"MZ"
    struct.pack_into("<I", source, 0x3C, pe)
    source[pe : pe + 4] = b"PE\0\0"
    machine = 0x14C if bits == 32 else 0x8664
    struct.pack_into(
        "<HHIIIHH",
        source,
        pe + 4,
        machine,
        section_count,
        0,
        0,
        0,
        optional_size,
        0x0102,
    )
    optional = pe + 24
    struct.pack_into("<H", source, optional, 0x10B if bits == 32 else 0x20B)
    struct.pack_into("<I", source, optional + 16, 0x1000)
    if bits == 32:
        struct.pack_into("<I", source, optional + 28, image_base)
        count_offset = 92
    else:
        struct.pack_into("<Q", source, optional + 24, image_base)
        count_offset = 108
    struct.pack_into("<II", source, optional + 32, section_alignment, file_alignment)
    struct.pack_into("<II", source, optional + 56, size_image, headers)
    struct.pack_into("<H", source, optional + 68, 3)
    struct.pack_into("<H", source, optional + 70, 0x140)
    struct.pack_into("<I", source, optional + count_offset, 16)
    raw = headers
    for index, name in enumerate(section_names):
        offset = section_table + index * 40
        rva = 0x1000 * (index + 1)
        characteristics = 0x60000020
        source[offset : offset + 8] = name.encode("ascii").ljust(8, b"\0")
        struct.pack_into(
            "<IIIIIIHHI",
            source,
            offset + 8,
            0x1000,
            rva,
            file_alignment,
            raw,
            0,
            0,
            0,
            0,
            characteristics,
        )
        source[raw : raw + file_alignment] = bytes([0xA0 + index]) * file_alignment
        capture[rva : rva + 0x1000] = bytes([0xB0 + index]) * 0x1000
        raw += file_alignment
    return bytes(source), bytes(capture), image_base


def plan_for(bits: int, image_base: int) -> dict:
    width = bits // 8
    return {
        "format": "chimprec-import-plan-1",
        "bits": bits,
        "pointer_width": width,
        "descriptors": [
            {
                "module": "kernel32.dll",
                "entries": [
                    {
                        "address": image_base + 0x1100,
                        "name": "ExitProcess",
                        "ordinal": None,
                    },
                    {
                        "address": image_base + 0x1100 + width,
                        "name": None,
                        "ordinal": 17,
                    },
                ],
            }
        ],
    }


@pytest.mark.parametrize("bits", [32, 64])
def test_writer_rebuilds_import_directory_oep_and_iat(bits):
    source, capture, image_base = make_pe(bits)
    width = bits // 8
    slot = 0x1100
    capture = bytearray(capture)
    capture[slot : slot + width] = (0x76001000).to_bytes(width, "little")
    capture[slot + width : slot + 2 * width] = (0x76001000 + 0x100).to_bytes(
        width, "little"
    )
    rebuilt, receipt = rebuild_pe_image(
        source,
        bytes(capture),
        plan_for(bits, image_base),
        entry_rva=0x1010,
    )
    layout = parse_pe(rebuilt)
    assert receipt["format"] == "fdisbull-chimprec-pe-rebuild-1"
    assert receipt["import_count"] == 2
    assert receipt["oep"] == image_base + 0x1010
    assert layout["entry_rva"] == 0x1010
    assert layout["sections"][-1]["name"] == ".reimp"
    assert layout["directories"][1]["rva"] == layout["sections"][-1]["rva"]
    assert layout["directories"][12]["size"] == 2 * width
    mapped_rebuilt, mapped_layout = map_pe_file(rebuilt)
    imports = parse_imports(mapped_rebuilt, mapped_layout)["entries"]
    assert [(item["name"], item["ordinal"]) for item in imports] == [
        ("ExitProcess", None),
        (None, 17),
    ]
    checksum_offset = layout["optional_offset"] + 64
    assert struct.unpack_from("<I", rebuilt, checksum_offset)[0] == _checksum(
        rebuilt, checksum_offset
    )
    # The source section bytes are not used as the captured image body.
    assert rebuilt[layout["sections"][0]["raw_offset"]] == 0xB0


def test_file_api_writes_receipt_and_refuses_overwrite(tmp_path: Path):
    source, capture, image_base = make_pe(32)
    plan = plan_for(32, image_base)
    source_path = tmp_path / "wrapper.exe"
    capture_path = tmp_path / "mapped.bin"
    plan_path = tmp_path / "plan.json"
    source_path.write_bytes(source)
    capture_path.write_bytes(capture)
    plan_path.write_text(json.dumps(plan))
    output = tmp_path / "out.exe"
    result = rebuild_pe_file(
        source_path, capture_path, plan_path, output, entry_rva=0x1010
    )
    assert output.is_file()
    assert output.with_suffix(".exe.chimprec.json").is_file()
    assert result["import_count"] == 2
    with pytest.raises(FileExistsError):
        rebuild_pe_file(source_path, capture_path, plan_path, output, entry_rva=0x1010)


def test_writer_rejects_invalid_or_incomplete_plans():
    source, capture, image_base = make_pe(32)
    with pytest.raises(ValueError, match="import plan"):
        rebuild_pe_image(source, capture, {"format": "wrong"}, entry_rva=0x1010)
    bad = plan_for(32, image_base)
    bad["descriptors"][0]["entries"][0]["name"] = None
    bad["descriptors"][0]["entries"][0]["ordinal"] = None
    with pytest.raises(ValueError, match="exactly one"):
        rebuild_pe_image(source, capture, bad, entry_rva=0x1010)
    with pytest.raises(ValueError, match="entry RVA"):
        rebuild_pe_image(source, capture, plan_for(32, image_base), entry_rva=-1)
