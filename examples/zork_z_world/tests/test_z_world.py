from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE))

import build_zork_world as builder
import zlang

SAMPLE = """
(z-world "sample"
  (source "https://example.invalid/zil" "abc" "MIT")
  (entry A)
  (directions NORTH SOUTH EAST WEST)
  (room A
    (flags RLANDBIT)
    (NORTH (to B))
    (EAST (blocked))
    (SOUTH (to C (if WON-FLAG) (else (blocked)))))
  (room B
    (SOUTH (to A)))
  (room C
    (EAST (per ROUTINE)))
  (object BOX
    (in A)
    (flags CONTBIT))
)
"""


def test_roundtrip_and_graph():
    world = zlang.parse_z(SAMPLE)
    assert zlang.validate(world) == []
    graph = zlang.build_graph(world)
    assert graph["stats"] == {
        "rooms": 3,
        "objects": 1,
        "exits": 5,
        "kinds": {
            "passage": 2,
            "conditional": 1,
            "blocked": 1,
            "routine": 1,
            "unknown": 0,
        },
        "reachable": 3,
        "unreachable": 0,
        "one_way": 1,
    }
    canonical = zlang.world_to_z(world)
    assert zlang.world_to_z(zlang.parse_z(canonical)) == canonical
    text = zlang.render_text(world, graph)
    assert "A" in text
    assert "SOUTH -> C if WON-FLAG else blocked" in text


def test_validation_errors_and_warnings():
    world = zlang.parse_z(SAMPLE.replace("(to B)", "(to NOPE)"))
    problems = zlang.validate(world)
    assert any(p["code"] == "unknown-target" for p in problems)

    world = zlang.parse_z(SAMPLE.replace("(EAST (blocked))", "(NORTH (to C))"))
    problems = zlang.validate(world)
    assert any(p["code"] == "duplicate-direction" for p in problems)
    world = zlang.parse_z(
        SAMPLE.replace("(object BOX", "(room D (south (to A)))\n  (object BOX")
    )
    problems = zlang.validate(world)
    assert any(
        p["code"] == "unreachable-room" and p["subject"] == "D" for p in problems
    )


def test_zil_inline_comment_does_not_break_flags(tmp_path: Path):
    (tmp_path / "1dungeon.zil").write_text(
        "<DIRECTIONS NORTH>\n"
        '<ROOM A (IN ROOMS) (FLAGS RLANDBIT ;"CANT-HAVE-ONBIT")\n'
        "      (NORTH TO B)>\n"
        "<ROOM B (IN ROOMS)>\n"
        "<OBJECT X (IN A)>\n",
        encoding="utf-8",
    )
    world = builder.lift(tmp_path, entry="A")
    assert world.rooms["A"].flags == ("RLANDBIT",)
    assert world.rooms["A"].exit("NORTH").target == "B"
    assert world.objects["X"].location == "A"


def test_real_zil_source():
    root = Path(
        os.environ.get(
            "ZORK1_ZIL_ROOT", "/Volumes/CODEX/Codex_Projects/zork1-open-source"
        )
    )
    if not (root / "1dungeon.zil").exists():
        pytest.skip("MIT Zork I ZIL source is not present")
    if (root / ".git").exists():
        head = builder._git_head(root)
        if not head.startswith("97b7b3d68c075dd9af7da499c3e9690ada3471fd"):
            pytest.skip(f"unexpected ZIL source commit {head}")
    world = builder.lift(root, entry="WEST-OF-HOUSE")
    graph = zlang.build_graph(world)
    assert graph["stats"]["rooms"] == 110
    assert graph["stats"]["objects"] == 140
    assert graph["stats"]["exits"] == 352
    assert graph["stats"]["kinds"] == {
        "passage": 277,
        "conditional": 31,
        "blocked": 37,
        "routine": 7,
        "unknown": 0,
    }
    assert graph["stats"]["reachable"] == 105
    assert {p["subject"] for p in zlang.validate(world)} == {
        "RIVER-1",
        "RIVER-2",
        "RIVER-3",
        "RIVER-4",
        "RIVER-5",
    }
    west = world.rooms["WEST-OF-HOUSE"]
    assert west.exit("NORTH").target == "NORTH-OF-HOUSE"
    assert west.exit("EAST").kind == "blocked"
    assert west.exit("SW").condition == ("WON-FLAG",)
    assert world.objects["MAILBOX"].location == "WEST-OF-HOUSE"
    for room in world.rooms.values():
        for exit_ in room.exits:
            if exit_.target:
                assert exit_.target in world.rooms


def test_svg_renderer():
    if not (shutil.which("fdp") or shutil.which("dot")):
        pytest.skip("Graphviz is not installed")
    world = zlang.parse_z(SAMPLE)
    svg = zlang.render_svg(world, zlang.build_graph(world))
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    assert "A" in svg
