"""Address/source atlas checks for the pinned Civ DOS 474.05 build."""

from __future__ import annotations

import os
from pathlib import Path

import capstone
import pytest

from examples.civ import civ_exe_atlas

CIVD_BUILD = Path(
    os.environ.get(
        "FDISBULL_CIVD_BUILD",
        "/Volumes/CODEX/Codex_Projects/Civd-intake/verified-builds/47405",
    )
)
ROOT = Path(os.environ.get("FDISBULL_CIV_UNPACKED", "build/civ-analysis/CIV_UNP.EXE"))
PINNED = "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"


@pytest.fixture(scope="module")
def atlas():
    if not (CIVD_BUILD / "CIV.MAP").exists() or not ROOT.exists():
        pytest.skip("pinned civd build inputs are not present")
    if civ_exe_atlas.sha256(ROOT.read_bytes()) != PINNED:
        pytest.skip("present root is not the pinned Civ identity")
    return civ_exe_atlas.build_atlas(
        map_path=CIVD_BUILD / "CIV.MAP",
        cod_dir=CIVD_BUILD,
        root_path=ROOT,
        packed_path=CIVD_BUILD / "CIV.EXE",
    )


@pytest.fixture(scope="module")
def functions(atlas):
    return {item["name"]: item for item in atlas["functions"]}


def test_atlas_counts_and_identity(atlas):
    counts = atlas["counts"]
    assert counts["segments"] == 97
    assert counts["root_code_segments"] == 22
    assert counts["overlays"] == 23
    assert counts["publics"] == 1188
    assert counts["c_functions"] == 430
    assert counts["c_sources"] == 42
    assert counts["calls"] == 5951
    assert counts["internal_calls"] + counts["external_calls"] == counts["calls"]
    assert counts["unresolved_calls"] == 0
    assert counts["anchors_total"] == 21
    assert counts["anchors_resolved"] == 21
    assert atlas["edition"]["unpacked_sha256"] == PINNED


def test_every_c_entry_and_call_is_checked(atlas):
    counts = atlas["counts"]
    assert counts["entries_verified"] == 411
    assert counts["entry_opcodes_verified"] == 430
    assert counts["map_entry_matches"] == 428
    assert counts["call_opcodes_verified"] == 5951
    assert counts["call_targets_verified"] == 5951
    assert atlas["verification"]["overlay_size_matches"] == 23
    assert atlas["verification"]["overlay_size_total"] == 23


def test_city_and_overlay_functions_keep_their_own_address_space(functions):
    city = functions["_city_process"]
    assert city["segment"] == "F0D12"
    assert city["overlay"] is None
    assert city["start"] == 0xD165
    assert city["end"] == 0xD165 + 26856
    assert city["source"] == "CITYMGT.C"
    assert city["line"] == 127

    # All overlays load at the same linear base.  The same-address trap is the
    # reason an overlay number must accompany every lookup.
    city_view = functions["_city_scene"]
    assert city_view["overlay"] == 19
    assert city_view["segment"] == "O19_TEXT"
    assert city_view["start"] == 0x23740
    city_create = functions["_city_create"]
    assert city_create["overlay"] == 20
    assert city_create["start"] == 0x23740
    assert city_view["source"] == "CITYVIEW.C"
    assert city_create["source"] == "CITY.C"

    quiz = functions["_quiz_event"]
    assert quiz["overlay"] == 16
    assert quiz["entry_opcode_verified"] is True


def test_civ64_anchors_resolve_to_the_intended_overlay(functions, atlas):
    anchors = {item["dos_address"]: item for item in atlas["anchors"]}
    assert anchors["R:0D12:0045"]["function"] == "_city_process"
    assert anchors["O19:0000"]["function"] == "_city_scene"
    assert anchors["O19:0000"]["function_source"] == "CITYVIEW.C"
    assert anchors["O19:167B"]["function"] == "_invasion_scene"
    assert anchors["O20:0540"]["function"] == "_city_disaster"
    assert anchors["O20:047C"]["function"] == "_city_create"
    assert anchors["O22:0EAF"]["function"] == "_city_founded"
    assert anchors["R:0403:35CE"]["function"] == "_ai_turn"
    assert anchors["R:0ADE:0093"]["function"] == "_civ_economy"
    assert anchors["R:0ADE:0093"]["inside_function"] is True
    assert all(
        item["resolution"] == "civd-source-function" for item in atlas["anchors"]
    )


def test_calls_use_int3f_only_across_overlays(functions):
    unit_goal = functions["_unit_goal"]
    internal = [call for call in unit_goal["calls"] if call["target"] == "_path_search"]
    assert internal
    assert all(call["opcode"] == 0xE8 for call in internal)
    assert all(call["target_function"] == "_path_search" for call in internal)

    main = functions["_main"]
    overlay_call = next(
        call for call in main["calls"] if call["target"] == "_setup_main"
    )
    assert overlay_call["opcode"] == 0xCD
    assert overlay_call["decoded_target_overlay"] == 1
    assert overlay_call["decoded_target_linear"] == 0x23740
    assert overlay_call["target_verified"] is True


def test_path_subsystem_is_one_contiguous_segment(functions):
    expected = {
        "_unit_goal": (0x1E31E, 1496, 29),
        "_path_coarse": (0x1E8F6, 1094, 123),
        "_path_select": (0x1ED3C, 497, 224),
        "_path_search": (0x1EF2D, 1279, 290),
        "_path_probe": (0x1F42C, 127, 404),
        "_wrap_x": (0x1F4AB, 36, 422),
    }
    for name, (start, size, line) in expected.items():
        function = functions[name]
        assert function["source"] == "PATH.C"
        assert function["segment"] == "F1E31"
        assert function["overlay"] is None
        assert function["start"] == start
        assert function["size"] == size
        assert function["line"] == line
        assert function["entry_opcode_verified"] is True
    assert functions["_unit_goal"]["end"] == functions["_path_coarse"]["start"]
    assert functions["_wrap_x"]["end"] == 0x1F4CF


def test_unit_record_arithmetic_is_in_the_binary(functions):
    root = ROOT.read_bytes()
    header = civ_exe_atlas._root_header(root)
    unit_goal = functions["_unit_goal"]
    base = header["header_size"] + unit_goal["start"]
    code = root[base : base + 80]
    assert b"\xa1\xee\xd7" in code  # mov ax, [DGROUP:D7EE] (civnow)
    assert b"\xb8\x00\x06" in code  # mov ax, 600h (1536 = 8*128*12)
    assert b"\xb8\x0c\x00" in code  # mov ax, 0Ch (unit stride)
    # goto_x / goto_y are [si-7E26h] / [si-7E25h], i.e. DGROUP:81DA/81DB.
    assert b"\x8a\x84\xda\x81" in code
    assert b"\x8a\x84\xdb\x81" in code


def test_wrap_x_binary_matches_the_source_rule():
    root = ROOT.read_bytes()
    header = civ_exe_atlas._root_header(root)
    start = 0x1F4AB
    code = root[header["header_size"] + start : header["header_size"] + 0x1F4CF]
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    instructions = list(decoder.disasm(code, start))
    text = [(item.mnemonic, item.op_str) for item in instructions]
    assert text[:4] == [
        ("push", "bp"),
        ("mov", "bp, sp"),
        ("cmp", "word ptr [bp + 6], 0"),
        ("jge", "0x1f4bc"),
    ]
    assert ("add", "ax, 0x50") in text
    assert ("cmp", "word ptr [bp + 6], 0x50") in text
    assert ("sub", "ax, 0x50") in text
    assert text[-2:] == [("pop", "bp"), ("retf", "")]
