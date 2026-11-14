"""Build the Civ city-screen debugger scene from captured frames.

The scene is an overlay for the DOSBox debugger: it recognises the city screen
from native pixels and turns the recovered tab and CHANGE controls into checked
actions. Geometry and outcome pixels come from frames captured by the debugger
itself, so a new element is added by saving a child revision with the frame that
showed it as evidence.

Usage:
    python examples/civ/civ_city_overlay.py PROJECT REFERENCE \
        --chooser CH1 --chooser CH2 [--parent REVISION] [--scene NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CATALOG = Path(__file__).with_name("civ_city_scene.json")

# Stable pixels of the 320x200 city screen shared by the INFO, HAPPY and MAP
# views (measured on the 474.03 runtime capture).
MATCH_SAMPLES = [
    {"x": 250, "y": 111, "rgb": [121, 142, 255]},
    {"x": 100, "y": 55, "rgb": [117, 117, 239]},
    {"x": 300, "y": 10, "rgb": [117, 117, 239]},
]
CITY_CONTEXT = {
    "state": "city screen for Rome, 4000 BC (474.03 runtime)",
    "triggers": [
        "city founded and the production note dismissed",
        "c on the map with the city under the cursor",
    ],
}


def _pixels(samples, min_matches=None):
    payload = {"samples": samples, "tolerance": 0}
    if min_matches is not None:
        payload["min_matches"] = min_matches
    return {"pixels": payload}


def _object(name, area, point, key, outcome, description, evidence):
    return {
        "name": name,
        "context": {"state": description, "triggers": ["city screen is showing"]},
        "area": {"rect": area},
        "point": point,
        "visible": {"constant": True},
        "ready": {"constant": True},
        "enabled": {"constant": True},
        "action": {"kind": "press", "key": key},
        "outcome": outcome,
        "outcome_phase": "interface",
        "guest_ms": 4000,
        "timeout_ms": 5000,
        "evidence": list(evidence),
    }


def catalog_ids(path=None):
    """Object ids of the Z scene; the debugger overlay names the same controls."""
    data = json.loads(Path(path or CATALOG).read_text())
    return {obj["id"] for obj in data["objects"]}


def scene_definition(reference, chooser_frames, city_frame=None, scene_ids=None):
    """Return the validated-shape scene definition for the city screen."""
    if not chooser_frames:
        raise ValueError("at least one production-chooser frame is required")
    city_frame = city_frame or reference
    document = {
        "format": "fdisbull-scene-1",
        "width": 320,
        "height": 200,
        "mode_id": 5,
        "reference": reference,
        "context": CITY_CONTEXT,
        "match": _pixels(MATCH_SAMPLES),
        "exclusive_group": "main",
        "objects": [
            _object(
                "tab-happiness",
                [128, 106, 160, 118],
                [140, 111],
                "h",
                _pixels([{"x": 105, "y": 134, "rgb": [255, 255, 150]}]),
                "HAPPY tab; recovered key h sets view mode 1",
                [reference],
            ),
            _object(
                "tab-map",
                [160, 106, 192, 118],
                [172, 111],
                "m",
                _pixels([{"x": 200, "y": 150, "rgb": [0, 0, 0]}]),
                "MAP tab; recovered key m sets view mode 2",
                [reference],
            ),
            _object(
                "production-change",
                [230, 106, 270, 118],
                [250, 111],
                "c",
                # The chooser popup border is fixed at x=81 while its list grows
                # with available items, so two of three border pixels suffice.
                _pixels(
                    [
                        {"x": 81, "y": 10, "rgb": [235, 235, 235]},
                        {"x": 81, "y": 11, "rgb": [235, 235, 235]},
                        {"x": 81, "y": 12, "rgb": [235, 235, 235]},
                    ],
                    min_matches=2,
                ),
                "CHANGE opens the production chooser; measured on the live city screen",
                [city_frame, *chooser_frames],
            ),
            _object(
                "tab-city-view",
                [192, 106, 224, 118],
                [204, 111],
                "v",
                _pixels([{"x": 160, "y": 100, "rgb": [109, 158, 97]}]),
                "VIEW tab; recovered key v enters the int 3F city-view overlay",
                [reference],
            ),
            # Escape leaves the city screen for the map view. `not match` alone
            # is satisfied by the blank frame drawn during the transition
            # (observed in run c778c405), so the map panel's cyan resource bar
            # must also be drawn.
            _object(
                "exit",
                [280, 190, 320, 199],
                [288, 193],
                "escape",
                {
                    "all": [
                        {"not": _pixels(MATCH_SAMPLES)},
                        _pixels(
                            [
                                {"x": 5, "y": 62, "rgb": [12, 227, 235]},
                                {"x": 30, "y": 66, "rgb": [12, 227, 235]},
                                {"x": 60, "y": 62, "rgb": [12, 227, 235]},
                            ],
                            min_matches=2,
                        ),
                    ]
                },
                "EXIT control; escape returns to the map view",
                [reference],
            ),
        ],
    }
    if scene_ids is not None:
        known = set(scene_ids)
        unknown = [
            obj["name"] for obj in document["objects"] if obj["name"] not in known
        ]
        if unknown:
            raise ValueError(
                f"overlay objects missing from the Z scene catalog: {unknown}"
            )
    return document


def build(
    project_path,
    reference,
    chooser_frames,
    *,
    city_frame=None,
    parent=None,
    scene="civ-city-screen",
    author="agent",
):
    from fdisbull.project import Project

    with Project(project_path) as project:
        definition = scene_definition(
            reference, chooser_frames, city_frame, catalog_ids()
        )
        saved = project.debug_save_scene(
            scene, definition, parent=parent, author=author
        )
        overlay = project.debug_scene_overlay(
            saved["id"], name="civ-city-overlay.png", labels="numbers"
        )
        return {
            "revision": saved["id"],
            "parent": saved["parent"],
            "objects": [o["name"] for o in saved["definition"]["objects"]],
            "overlay": overlay["artifact"],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("reference")
    parser.add_argument("--chooser", action="append", default=[], required=True)
    parser.add_argument("--city-frame")
    parser.add_argument("--parent")
    parser.add_argument("--scene", default="civ-city-screen")
    parser.add_argument("--author", default="agent")
    args = parser.parse_args(argv)
    result = build(
        args.project,
        args.reference,
        args.chooser,
        city_frame=args.city_frame,
        parent=args.parent,
        scene=args.scene,
        author=args.author,
    )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
