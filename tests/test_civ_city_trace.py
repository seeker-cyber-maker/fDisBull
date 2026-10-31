"""Static caller and field trace for the Civ DOS city routine."""

import struct
import os

import pytest

from examples.civ import civ_city_trace as trace

PINNED = "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"
REAL_ROOT = os.environ.get("FDISBULL_CIV_UNPACKED", "build/civ-analysis/CIV_UNP.EXE")


def _synthetic_root(*, with_relocation=True, high_call=False, overlay=b""):
    """Minimal MZ with the city prologue, reset block and one far call."""
    header = bytearray(48)
    struct.pack_into(
        "<14H",
        header,
        0,
        0x5A4D,
        (48 + 0x20000) % 512,
        (48 + 0x20000 + 511) // 512,
        (2 if high_call else 1) if with_relocation else 0,
        3,
        0,
        0xFFFF,
        0,
        0x100,
        0,
        0,
        0,
        0x1C,
        0,
    )
    module = bytearray(0x20000)
    module[0xD165 : 0xD165 + 3] = b"\x55\x8b\xec"
    module[0xE000:0xE005] = b"\x9a\x45\x00\x12\x0d"
    if with_relocation:
        # Relocation entry: offset of the segment word inside the module.
        struct.pack_into("<HH", header, 0x1C, 0xE003, 0)
        if high_call:
            struct.pack_into("<HH", header, 0x20, 0x2003, 0x1000)
    if high_call:
        module[0x12000:0x12005] = b"\x9a\x45\x00\x12\x0d"
    reset = bytes.fromhex(
        "81bffa70e7037e03e91200b81c00f76e068bd8"
        "83bffa70007c03e90e00b81c00f76e068bd8"
        "c787fa700000"
    )
    module[0xD244 : 0xD244 + len(reset)] = reset
    return bytes(header) + bytes(module) + overlay


def test_mz_header_excludes_header_from_module_and_preserves_overlay_boundary():
    h = trace._header(_synthetic_root(overlay=b"overlay-tail"))
    assert h["module"] == 0x20000
    assert h["overlays"] == 12


def test_segmented_relocation_keeps_the_high_resident_caller():
    result = trace.callers(_synthetic_root(high_call=True))
    assert {s["linear"] for s in result["sites"]} == {0xE000, 0x12000}


def test_reset_rule_rejects_unsigned_branch_substitution():
    root = bytearray(_synthetic_root())
    root[48 + 0xD24A] = 0x76  # JBE differs from signed JLE.
    assert trace.shield_reset(bytes(root))["matches_rule"] is False


def test_synthetic_trace_decodes_call_reset_and_field_model():
    result = trace.analyze(_synthetic_root())
    assert result["entry"]["linear"] == 0xD165
    assert result["entry"]["prologue_hex"].startswith("558bec")
    assert result["shield_reset"]["matches_rule"] is True
    assert result["callers"]["in_root_module"] == 1
    site = result["callers"]["sites"][0]
    assert site["linear"] == 0xE000
    assert site["segment_offset"] == "0D12:0045"
    assert site["segment_word_relocated"] is True


def test_synthetic_unrelocated_match_is_coincidental_not_a_caller():
    result = trace.analyze(_synthetic_root(with_relocation=False))
    assert result["callers"]["in_root_module"] == 0
    assert result["callers"]["coincidental_byte_matches"] == 1


def test_real_root_entry_reset_and_root_callers():
    from pathlib import Path

    root_path = Path(REAL_ROOT)
    if not root_path.exists():
        pytest.skip("pinned unpacked Civ root is not present")
    root = root_path.read_bytes()
    if trace.identity(root)["sha256"] != PINNED:
        pytest.skip("present root is not the pinned Civ identity")
    result = trace.analyze(root)
    assert result["entry"]["file_offset"] == 63733
    assert result["entry"]["prologue_hex"].startswith(
        "558bec81ec0c015756b81c00f76e068bd880bff270ff"
    )
    assert result["shield_reset"]["matches_rule"] is True
    sites = {s["linear"]: s for s in result["callers"]["sites"] if s["in_root_module"]}
    assert sorted(sites) == [0xAE31, 0xAE73, 0xB1E3, 0xB21F, 0x14B27]
    assert sites[0xAE31]["caller_function"] == 0xADE6
    assert sites[0xAE73]["caller_function"] == 0xADE6
    assert sites[0xB1E3]["caller_function"] == 0xB1CA
    assert sites[0xB21F]["caller_function"] == 0xB201
    assert sites[0x14B27]["caller_function"] == 0x14590
    assert [sites[a]["mode_word"] for a in sorted(sites)] == [0, 1, 1, -1, 1]
    assert trace._header(root)["module"] == 203584
    assert trace._header(root)["overlays"] == 127079
    # The mode-0 site passes a zero long argument; the display site sets ax=1.
    assert sites[0xAE31]["register_arguments"][:2] == ["ax", "ax"]
    assert any(
        i["mnemonic"] == "mov" and i["operands"] == "ax, 1"
        for i in sites[0xAE73]["preceding"]
    )
    fields = result["fields"]
    assert fields["status"]["offset"] == 0x06 and fields["status"]["references"] >= 50
    assert (
        fields["shield_box"]["offset"] == 0x0E
        and fields["shield_box"]["references"] >= 20
    )
