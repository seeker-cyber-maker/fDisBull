#!/usr/bin/env python3
"""Collect private execution-bound pose packets from contiguous AGI fragments.

The authored load prologue and reset entry state are explicit. A stopped native
binding is not evidence of whole-room reachability, drawing or presentation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture
from fdisbull.agi_resources import V2Resources
from fdisbull_core.agi_view import decode_view_cel, describe_view
from binding_catalog import PROFILE, decode_catalog, encode_catalog
from harness import HarnessError
from resource_scene_trial import PALETTE, _identity, _resource, _uint, _write_json
from scene_harness import _bounded_timeout


def prepare_case(game_dir, spec):
    """Validate exact contiguous source and build an explicitly seeded catalog.

    The final original instruction is an expected unsupported boundary. No
    branch is relocated, instruction skipped or authored source address invented.
    All scene pose choices come from native state after execution, not this spec.
    """
    fields = {"id", "logic", "picture", "payload_span", "views", "actors",
              "horizon", "stop_opcode"}
    if type(spec) is not dict or set(spec) != fields:
        raise ValueError("Case specification requires exactly the documented fields")
    if type(spec["id"]) is not str or not re.fullmatch(r"[a-z0-9_-]{1,40}", spec["id"]):
        raise ValueError("Invalid case id")
    for name in ("logic", "picture", "stop_opcode"):
        _uint(spec[name], name)
    _uint(spec["horizon"], "horizon", 167)
    for field, limit in (("views", 255), ("actors", 15)):
        values = spec[field]
        if type(values) is not list or not 1 <= len(values) <= 8:
            raise ValueError(f"{field} must contain 1..8 identifiers")
        for value in values:
            _uint(value, field, limit)
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {field} identifier")
    span = spec["payload_span"]
    if type(span) is not list or len(span) != 2:
        raise ValueError("payload_span requires two instruction boundaries")
    start, end = (_uint(value, "payload boundary", 65535, 2) for value in span)
    if not 0 < end - start <= 256:
        raise ValueError("Copied fragment must contain 1..256 bytes")

    resources = V2Resources(game_dir)
    logic = _resource(resources, "logic", spec["logic"])
    payload = logic["payload"]
    layout = logic_layout(payload)
    boundaries = layout["instructions"] + [layout["code_end"]]
    if start not in boundaries[:-1] or end not in boundaries:
        raise ValueError("Fragment endpoints are not LOGIC instruction boundaries")
    sites = []
    prelude = bytes(value for number in sorted(spec["views"]) for value in (30, number))
    for offset, following in zip(boundaries, boundaries[1:]):
        if start <= offset < end:
            opcode = payload[offset]
            if opcode in (0, 254, 255):
                raise ValueError("This fragment collector admits straight-line actions only")
            sites.append({"payload_offset": offset, "code_pc": offset - 2,
                          "fragment_pc": len(prelude) + offset - start,
                          "bytes": list(payload[offset:following]), "opcode": opcode})
    if not 2 <= len(sites) <= 64 or sites[-1]["opcode"] != spec["stop_opcode"]:
        raise ValueError("Expected final unsupported boundary differs from source")
    views = {number: _resource(resources, "view", number) for number in sorted(spec["views"])}
    catalog = encode_catalog({number: row["payload"] for number, row in views.items()},
                             horizon=spec["horizon"])
    metadata = {number: describe_view(row["payload"]) for number, row in views.items()}
    cel_count = sum(row["cel_references"] for row in metadata.values())
    pixel_count = sum(cel["width"] * cel["height"] for row in metadata.values()
                      for loop in row["loops"] for cel in loop["cels"])
    if cel_count > 128 or pixel_count > 4 * 1024 * 1024:
        raise ValueError("Private trial asset budget exceeded")
    picture = _resource(resources, "picture", spec["picture"])
    decoded_picture = decode_picture(picture["payload"])
    assets = {"background.idx": decoded_picture["visual"],
              "priority.idx": decoded_picture["priority"]}
    cels = []
    for number, metadata_row in metadata.items():
        for loop in metadata_row["loops"]:
            for cel in loop["cels"]:
                decoded = decode_view_cel(views[number]["payload"], loop=loop["loop"], cel=cel["cel"])
                filename = f"view-{number:03d}-loop-{loop['loop']:03d}-cel-{cel['cel']:03d}.idx"
                assets[filename] = decoded.pop("pixels")
                cels.append({"view": number, "asset": filename, **decoded})
    copied = payload[start:end]
    code = prelude + copied + b"\0"
    return {"spec": deepcopy(spec), "source_manifest": resources.manifest(),
            "logic": _identity(logic), "picture": _identity(picture),
            "views": {number: _identity(row) for number, row in views.items()},
            "catalog": catalog, "code": code, "sites": sites, "cels": cels,
            "assets": assets, "prelude": prelude,
            "mapping": {"copied_fragment_span": [len(prelude), len(prelude) + len(copied)],
                        "source_payload_span": list(span),
                        "source_code_span": [start - 2, end - 2],
                        "copied_span_sha256": sha256(copied).hexdigest(),
                        "authored_load_prologue_span": [0, len(prelude)],
                        "authored_return_pc": len(code) - 1,
                        "authored_original_source_address": None,
                        "containing_logic_executed": False}}


def validate_binding(state, *, code, catalog):
    """Validate a stopped authoritative binding snapshot against exact inputs.

    This is a capture validator, not a delta-history reconstruction API. The
    old position consumer deliberately does not accept this richer profile.
    """
    metadata = decode_catalog(catalog)
    expected_source = {"sha256": sha256(code).hexdigest(), "size": len(code),
                       "logic_id": 0, "profile": PROFILE,
                       "catalog_sha256": metadata["sha256"]}
    if type(state) is not dict or state.get("schema") != "fdisbull-agi-binding-state-1" \
            or state.get("source") != expected_source:
        raise HarnessError("Binding snapshot source/profile/catalog identity differs")
    expected_catalog = {"sha256": metadata["sha256"], "size": len(catalog),
                        "view_count": len(metadata["views"]), "horizon": metadata["horizon"],
                        "loop_count": sum(len(v["loops"]) for v in metadata["views"].values()),
                        "cel_count": sum(len(loop) for v in metadata["views"].values()
                                         for loop in v["loops"])}
    if state.get("catalog") != expected_catalog:
        raise HarnessError("Binding catalog summary differs")
    guest = state.get("guest")
    if type(guest) is not dict or guest.get("horizon") != metadata["horizon"] \
            or guest.get("status") not in ("ready", "budget", "return", "fault", "external"):
        raise HarnessError("Binding snapshot is not a stopped guest")
    for name, maximum in (("variables", 255), ("flags", 1)):
        values = guest.get(name)
        if type(values) is not list or len(values) != 256 \
                or any(type(value) is not int or not 0 <= value <= maximum for value in values):
            raise HarnessError("Binding snapshot contains invalid scalar state")
    loaded = guest.get("loaded_views")
    if type(loaded) is not list or any(type(number) is not int or number not in metadata["views"]
                                     for number in loaded) or loaded != sorted(set(loaded)):
        raise HarnessError("Invalid loaded VIEW membership")
    actors = guest.get("actors")
    if type(actors) is not list or len(actors) != 16:
        raise HarnessError("Binding snapshot requires all 16 actors")
    integers = {"id", "x", "y", "prev_x", "prev_y", "view", "loop", "cel", "width", "height", "direction"}
    flags = {"view_bound", "animated", "update", "cycling", "ignore_horizon", "update_pos", "view_replaced"}
    for index, actor in enumerate(actors):
        if type(actor) is not dict or set(actor) != integers | flags | {"motion", "cycle"}:
            raise HarnessError("Unknown or incomplete actor state")
        if any(type(actor[name]) is not int or not 0 <= actor[name] <= 255 for name in integers) \
                or actor["id"] != index or any(type(actor[name]) is not bool for name in flags) \
                or actor["motion"] != "normal" or actor["cycle"] != "normal" or actor["direction"] != 0:
            raise HarnessError("Invalid binding actor state")
        if actor["view_bound"]:
            if actor["view"] not in loaded:
                raise HarnessError("Bound actor references an unloaded VIEW")
            loops = metadata["views"][actor["view"]]["loops"]
            if actor["loop"] >= len(loops) or actor["cel"] >= len(loops[actor["loop"]]):
                raise HarnessError("Bound actor selects an absent pose")
            geometry = loops[actor["loop"]][actor["cel"]]
            if (actor["width"], actor["height"]) != (geometry["width"], geometry["height"]):
                raise HarnessError("Actor dimensions differ from bound catalog pose")
        elif any(actor[name] != 0 for name in ("view", "loop", "cel", "width", "height")):
            raise HarnessError("Unbound actor contains resource geometry")
    return deepcopy(state)


def validate_journal(initial, state, events, *, code, sites, prelude):
    """Require a complete, source-bound journal for this single-run collector.

    Check every retired source site and replay all atomic actor/load changes
    from the initial snapshot. This validates observation continuity without
    substituting a Python AGI interpreter for the native execution.
    """
    observation = state["observation"]
    rows = events.get("events") if type(events) is dict else None
    if type(rows) is not list or events.get("schema") != "fdisbull-agi-binding-events-1" \
            or events.get("source") != state["source"] \
            or events.get("epoch") != observation["epoch"] or observation["mask"] != 3 \
            or observation["dropped"] != 0 or observation["count"] != len(rows) \
            or observation["eligible"] != len(rows):
        raise HarnessError("Trial requires a complete matching observation journal")
    expected = [{"fragment_pc": pc, "bytes": list(prelude[pc:pc + 2]), "opcode": 30}
                for pc in range(0, len(prelude), 2)] + sites[:-1]
    actors = deepcopy(initial["guest"]["actors"])
    loaded = set(initial["guest"]["loaded_views"])
    retired, scene_count, previous_kind = 0, 0, None
    current = None
    for sequence, event in enumerate(rows, 1):
        if type(event) is not dict or event.get("seq") != sequence \
                or event.get("control_generation") != observation["control_generation"]:
            raise HarnessError("Observation sequence/control generation has a gap")
        kind = event.get("kind")
        if kind == "retire":
            if retired >= len(expected):
                raise HarnessError("Unexpected retired source instruction")
            current = expected[retired]
            retired += 1
        elif kind not in ("actor", "view_load") or previous_kind != "retire":
            raise HarnessError("SCENE must follow its matching retired instruction")
        if current is None or event.get("retired") != retired \
                or event.get("pc") != current["fragment_pc"] \
                or event.get("opcode") != current["opcode"] \
                or event.get("bytes") != current["bytes"] \
                or event.get("next_pc") != current["fragment_pc"] + len(current["bytes"]) \
                or list(code[event["pc"]:event["next_pc"]]) != current["bytes"]:
            raise HarnessError("Journal instruction identity/retirement differs from source")
        if kind == "actor":
            number = event.get("actor")
            if type(number) is not int or not 0 <= number < 16 \
                    or current["opcode"] not in (33, 37, 38, 41, 42, 43, 44, 47, 48) \
                    or current["bytes"][1] != number:
                raise HarnessError("Invalid actor SCENE source")
            before = {key: value for key, value in actors[number].items() if key != "id"}
            after = event.get("after")
            if event.get("before") != before or type(after) is not dict \
                    or set(after) != set(before) or before == after:
                raise HarnessError("Actor transition is missing, incomplete or disconnected")
            actors[number] = {"id": number, **deepcopy(after)}
            scene_count += 1
        elif kind == "view_load":
            view = event.get("view")
            if type(view) is not int or not 0 <= view <= 255 or view in loaded \
                    or event.get("before") is not False or event.get("after") is not True \
                    or current["opcode"] not in (30, 31) \
                    or current["opcode"] == 30 and current["bytes"][1] != view:
                raise HarnessError("Invalid VIEW load transition")
            loaded.add(view)
            scene_count += 1
        previous_kind = kind
    if retired != len(expected) or retired != state["guest"]["retired"] \
            or actors != state["guest"]["actors"] or sorted(loaded) != state["guest"]["loaded_views"]:
        raise HarnessError("Journal does not reconstruct the complete final binding state")
    channels = observation["per_channel"]
    for name, count in (("disasm", retired), ("scene", scene_count)):
        if channels.get(name) != {"eligible": count, "stored": count, "dropped": 0}:
            raise HarnessError("Observation channel accounting differs from journal")
    return {"retired_sites": retired, "scene_transitions": scene_count,
            "journal_records": len(rows), "all_actors_and_loaded_views_match": True}


def collect(binary, game_dir, output, spec, *, timeout=10.0):
    """Run one owned native fragment once and publish a private helper packet."""
    from visual_binding_harness import QemuAGIViewBinding

    timeout = _bounded_timeout(timeout)
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures = output / "native-failures"
    failures.mkdir()
    report = {"schema": "agi-binding-scene-collection-1", "status": "running",
              "parameters": {"maximum_children": 1, "resumes": 1, "step_budget": 80,
                             "timeout_seconds": timeout, "maximum_asset_bytes": 4 * 1024 * 1024}}
    stage = "prepare"
    try:
        prepared = prepare_case(game_dir, spec)
        code, catalog = prepared["code"], prepared["catalog"]
        report["source_manifest"] = prepared["source_manifest"]
        stage = "native_capture"
        with QemuAGIViewBinding(binary, code, catalog, timeout=timeout, evidence_dir=failures) as vm:
            report["binary_sha256"] = vm.binary_sha256
            report["initial_state"] = validate_binding(vm.state(), code=code, catalog=catalog)
            vm.configure(mask=3, capacity=256, step_budget=80)
            state = vm.run()
            events = vm.events()
            if state != vm.state() or events != vm.events():
                raise HarnessError("Stopped binding capture changed")
            report["final_state"] = validate_binding(state, code=code, catalog=catalog)
            report["events"] = events
        boundary = prepared["sites"][-1]
        guest = state["guest"]
        expected_retired = len(spec["views"]) + len(prepared["sites"]) - 1
        if guest["status"] != "fault" or guest["retired"] != expected_retired \
                or guest["pc"] != boundary["fragment_pc"] \
                or guest["fault"] != {"code": 1, "name": "unsupported_opcode",
                                      "pc": boundary["fragment_pc"], "opcode": spec["stop_opcode"]}:
            raise HarnessError("Native execution did not reach the exact expected unsupported boundary")
        report["journal_validation"] = validate_journal(
            report["initial_state"], state, events, code=code,
            sites=prepared["sites"], prelude=prepared["prelude"])
        if any(not guest["actors"][number]["view_bound"] for number in spec["actors"]):
            raise HarnessError("A selected actor did not acquire a native VIEW binding")
        after = V2Resources(game_dir).manifest()
        if after != prepared["source_manifest"]:
            raise HarnessError("Game inputs changed during collection")
        stage = "packet_write"
        helper = output / "helper"
        helper.mkdir()
        asset_rows = {}
        for name, data in prepared["assets"].items():
            (helper / name).write_bytes(data)
            asset_rows[name] = {"file": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
        (helper / "catalog.bin").write_bytes(catalog)
        documents = {}
        for name, source_name in (("README.md", "VIEW_BINDING_PACKET.md"),
                                  ("VIEW_BINDING_PROFILE.md", "VIEW_BINDING_PROFILE.md")):
            data = Path(__file__).with_name(source_name).read_bytes()
            if len(data) > 65536:
                raise ValueError("Packet contract document exceeds 64 KiB")
            data.decode("utf-8")
            (helper / name).write_bytes(data)
            documents[name] = {"file": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
        packet = {"schema": "fdisbull-agi-binding-scene-packet-1", "id": spec["id"],
                  "qualification": "native_pose_binding_in_explicit_reset_fragment",
                  "source_manifest": prepared["source_manifest"], "logic": prepared["logic"],
                  "views": prepared["views"], "fragment_mapping": prepared["mapping"],
                  "sites": prepared["sites"], "selected_actors": spec["actors"],
                  "catalog": {"file": "catalog.bin", **decode_catalog(catalog)},
                  "entry": {"kind": "authored_reset_with_executed_load_prologue",
                            "horizon": spec["horizon"], "original_room_checkpoint": False,
                            "load_prologue_bytes": list(prepared["prelude"]),
                            "authored_return_bytes": [0],
                            "initial_snapshot": report["initial_state"]},
                  "native": {"binary_sha256": report["binary_sha256"],
                             "snapshot": state, "observations": events},
                  "stop_boundary": {**boundary, "retired": False, "committed": False},
                  "picture": {"resource": prepared["picture"],
                              "selection_basis": "explicit_preview_background_not_native_picture_state"},
                  "cel_assets": prepared["cels"], "assets": asset_rows, "documents": documents,
                  "render_contract": {"kind": "diagnostic_unoccluded_layer", "width": 160, "height": 168,
                                      "axes": "x_right_y_down", "anchor": "lower_left_baseline",
                                      "top_row": "y-height+1", "clip": "canvas_bounds",
                                      "palette_rgb": PALETTE, "priority_compositing": False,
                                      "draw_order": spec["actors"]},
                  "unknowns": ["Original room entry/path and inherited actor state are not qualified.",
                               "View/loop/cel are native results only within the explicit reset and catalog model.",
                               "Picture choice is an external preview input; no picture command executed.",
                               "No draw, renderer, priority occlusion or picture presentation is qualified.",
                               "Animation flags do not imply that a motion/cycle tick advanced.",
                               "The stopped unsupported instruction did not retire or commit."]}
        _write_json(helper / "packet.json", packet)
        report.update(status="completed", packet="helper/packet.json", inputs_unchanged=True,
                      expected_retired=expected_retired, stop_boundary=packet["stop_boundary"])
    except BaseException as error:
        report.update(status="failed", stage=stage, error={"type": type(error).__name__, "message": str(error)})
        _write_json(output / "report.json", report)
        raise
    _write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--case-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    path = Path(args.case_json)
    if path.stat().st_size > 8192:
        parser.error("case-json exceeds 8192 bytes")
    report = collect(args.binary, args.game_dir, args.output, json.loads(path.read_text()), timeout=args.timeout)
    print(json.dumps({"status": report["status"], "packet": report["packet"]}))


if __name__ == "__main__":
    main()
