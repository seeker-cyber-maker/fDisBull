"""Build the reduced, indexed UIL record for the Civ world map.

The original play screen keeps an 80x50 terrain-colour projection in page 2.
This builder decodes the page-2 image saved beside a game (``CIVILn.MAP``),
extracts the terrain/unit/improvement layers, and emits a
``fdisbull-uil-record-1`` record whose slots are addressed by zero-based index.

Slots 0..49 are the 50 map row strings. That makes the manual operation
``print_text(23, 0, 23)`` print row 23 without a name lookup. The arrays after
the rows preserve the per-tile source layers for a future renderer or Z view.
The record is a reduced projection, not the original VGA screen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from examples.civ.civ_media import (
    HEIGHT,
    TERRAIN_BY_COLOUR,
    TERRAIN_NAMES,
    WIDTH,
    decode_pic,
    extract_world_map,
    sha256,
)
from fdisbull.uil_record import execute_record, validate_record


def _row_slot(row: int, text: str) -> dict:
    return {
        "name": f"$map_row_{row}",
        "type": "string",
        "initial": text,
        "max_bytes": WIDTH,
    }


def build_record(pixels: bytes, *, source_sha256: str | None = None) -> dict:
    """Build the indexed record from one decoded 320x200 page-2 image."""
    world = extract_world_map(pixels)
    slots = [_row_slot(row, text) for row, text in enumerate(world["rows"])]
    slots.extend(
        [
            {
                "name": "$terrain",
                "type": "array",
                "element": "i8",
                "length": WIDTH * HEIGHT,
                "initial": world["terrain"],
            },
            {
                "name": "$terrain_colour",
                "type": "array",
                "element": "u8",
                "length": WIDTH * HEIGHT,
                "initial": world["terrain_colour"],
            },
            {
                "name": "$unit_owner",
                "type": "array",
                "element": "u8",
                "length": WIDTH * HEIGHT,
                "initial": world["owner"],
            },
            {
                "name": "$unit_present",
                "type": "array",
                "element": "bool",
                "length": WIDTH * HEIGHT,
                "initial": world["unit"],
            },
            {
                "name": "$improvements",
                "type": "array",
                "element": "u16",
                "length": WIDTH * HEIGHT,
                "initial": world["improvements"],
            },
            {
                "name": "$known",
                "type": "array",
                "element": "u16",
                "length": WIDTH * HEIGHT,
                "initial": world["known"],
            },
            {
                "name": "$minimap",
                "type": "array",
                "element": "u8",
                "length": WIDTH * HEIGHT,
                "initial": world["minimap"],
            },
            {"name": "$view_x", "type": "u8", "initial": 0},
            {"name": "$view_y", "type": "u8", "initial": 0},
            {"name": "$selected_x", "type": "u8", "initial": 0},
            {"name": "$selected_y", "type": "u8", "initial": 0},
        ]
    )
    body = [
        {
            "id": f"print-row-{row}",
            "op": "print_text",
            "slot": row,
            "x": 0,
            "y": row,
            "font": 1,
        }
        for row in range(HEIGHT)
    ]
    record = {
        "format": "fdisbull-uil-record-1",
        "role": "uil",
        "slots": slots,
        "body": body,
        "evidence": {
            "page2": {
                "sha256": source_sha256 or sha256(pixels),
                "note": "320x200 page-2 image saved as CIVILn.MAP",
            },
            "terrain_table": {
                "values": list(TERRAIN_BY_COLOUR),
                "note": "Civd MAP.C:385 terrain_map; Civ64 SCENES-PLAY 1.1",
            },
            "terrain_names": {"values": list(TERRAIN_NAMES)},
        },
    }
    validate_record(record)
    return record


def build_from_map_file(path: str | Path) -> tuple[dict, dict]:
    data = Path(path).read_bytes()
    image = decode_pic(data)
    if image["width"] != 320 or image["height"] != 200:
        raise ValueError("world map image must be 320x200")
    world = extract_world_map(image["pixels"])
    record = build_record(image["pixels"], source_sha256=image["sha256"])
    summary = {
        "source": str(path),
        "source_sha256": image["sha256"],
        "pixel_sha256": image["pixel_sha256"],
        "width": world["width"],
        "height": world["height"],
        "terrain_sha256": hashlib.sha256(
            bytes(value & 0xFF for value in world["terrain"])
        ).hexdigest(),
        "units": sum(world["unit"]),
        "improved": sum(1 for value in world["improvements"] if value),
        "known": sum(1 for value in world["known"] if value),
        "minimap_sha256": hashlib.sha256(bytes(world["minimap"])).hexdigest(),
        "rows_sha256": hashlib.sha256(
            "\n".join(world["rows"]).encode("utf-8")
        ).hexdigest(),
    }
    return record, summary


def render_rows(record: dict) -> str:
    """Run only the print_text body and return the emitted rows in order."""
    outcome = execute_record(record)
    if not outcome["complete"]:
        raise ValueError(outcome.get("error", "record execution refused"))
    return "\n".join(
        event["text"] for event in outcome["events"] if event["op"] == "print_text"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, help="CIVILn.MAP page-2 image")
    parser.add_argument("--out", required=True, help="record JSON output")
    parser.add_argument("--summary", help="summary JSON output")
    parser.add_argument("--text", help="optional reduced text output")
    args = parser.parse_args(argv)
    record, summary = build_from_map_file(args.map)
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        Path(args.summary).write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    if args.text:
        Path(args.text).write_text(render_rows(record) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
