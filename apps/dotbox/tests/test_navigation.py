"""Authored geometry and stale-proposal cases; no commercial game or live input."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def room(width=12, height=6):
    return {
        "format": "fdisbull-spatial-map-1",
        "source": {"sha256": "d" * 64, "context": "authored-study-map",
                   "room": "study", "resource": "authored:no-game-resource"},
        "space": {"name": "authored-grid", "width": width, "height": height, "unit": "cell"},
        "actor": {"width": 1, "height": 1, "anchor": [0, 0]},
        "known": {"rect": [0, 0, width, height]},
        "safe": {"rect": [0, 0, width, height]},
        "layers": [],
        "evidence": {"authored": {"kind": "authored-test-fixture", "game_bytes": False}},
    }


def packet():
    return json.loads((ROOT / "examples/scene_window_closed.json").read_text())


def plan(document, start, goal, **kwargs):
    from dotbox.navigation import plan_movement

    return plan_movement(document, start, goal, scene_packet=packet(), **kwargs)


def check(proposal, document, **kwargs):
    from dotbox.navigation import check_movement_plan

    return check_movement_plan(proposal, document, packet(), **kwargs)


def layer(identity, kind, rectangle, **extra):
    return {"id": identity, "kind": kind, "area": {"rect": rectangle}, **extra}


def reseal(proposal):
    """A content hash is not authentication: a modified plan must still be checked."""
    content = {key: value for key, value in proposal.items() if key != "plan_sha256"}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    proposal["plan_sha256"] = hashlib.sha256(encoded).hexdigest()


def test_long_straight_route_is_one_leg_without_execution():
    document = room()
    result = plan(document, [1, 2], [10, 2])
    assert result["status"] == "found"
    assert result["distance"] == 9 and result["turns"] == 0
    assert result["path"] == [[x, 2] for x in range(1, 11)]
    assert result["legs"] == [{"start": [1, 2], "end": [10, 2], "direction": "right", "steps": 9}]
    assert result["execution"] == "not_performed"
    assert result["live_applicability"] == "unverified"
    assert result["source"]["context"] == "authored-study-map"
    assert result["observation_id"] == "window-frame-1"
    checked = check(result, document)
    assert checked["valid"] is True and checked["route_available"] is True
    assert checked["execution"] == "not_performed"


def test_shortest_route_prefers_three_turns_over_upstream_five():
    document = room(8, 8)
    blocked = [[0, 3], [0, 6], [1, 2], [1, 7], [2, 4], [3, 4], [4, 0],
               [4, 3], [4, 5], [4, 7], [6, 6], [7, 1], [7, 3]]
    document["layers"] = [layer(str(i), "obstacle", [x, y, x + 1, y + 1])
                          for i, (x, y) in enumerate(blocked)]
    result = plan(document, [0, 0], [7, 7])
    assert result["status"] == "found"
    # Independent authored counterexample: upstream BFS took 14 steps / 5 turns.
    assert (result["distance"], result["turns"], len(result["legs"])) == (14, 3, 4)
    assert {tuple(point) for point in result["path"]}.isdisjoint(map(tuple, blocked))
    assert result == plan(document, [0, 0], [7, 7])
    assert sum(leg["steps"] for leg in result["legs"]) == 14


def test_heading_is_preserved_and_no_diagonal_shortcut_is_generated():
    result = plan(room(), [1, 1], [9, 4])
    assert result["distance"] == 11 and result["turns"] == 1
    assert len(result["legs"]) == 2
    for before, after in zip(result["path"], result["path"][1:]):
        assert abs(before[0] - after[0]) + abs(before[1] - after[1]) == 1
    for leg in result["legs"]:
        assert (leg["start"][0] == leg["end"][0]) != (leg["start"][1] == leg["end"][1])


def test_open_agi_sized_grid_fits_default_heading_expansion_budget():
    result = plan(room(160, 168), [0, 0], [159, 167])
    assert result["status"] == "found"
    assert (result["distance"], result["turns"], len(result["legs"])) == (326, 1, 2)
    assert result["visited"] <= 10000


def test_small_maps_match_independent_simple_path_enumeration():
    # Exhaustive simple-path enumeration is independent of A* priorities and
    # heading-state bookkeeping. Positive travel costs need no repeated cells.
    optional = [(x, y) for y in range(3) for x in range(3) if (x, y) not in ((0, 0), (2, 2))]
    for mask in range(1 << len(optional)):
        blocked = {point for bit, point in enumerate(optional) if mask & (1 << bit)}
        possible, pending = [], [[(0, 0)]]
        while pending:
            path = pending.pop()
            if path[-1] == (2, 2):
                headings = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
                possible.append((len(path) - 1, sum(a != b for a, b in zip(headings, headings[1:]))))
                continue
            x, y = path[-1]
            for point in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                if 0 <= point[0] < 3 and 0 <= point[1] < 3 and point not in blocked and point not in path:
                    pending.append([*path, point])
        document = room(3, 3)
        document["layers"] = [{"id": "walls", "kind": "obstacle", "area": {
            "row_runs": [[y, x, x + 1] for x, y in sorted(blocked, key=lambda point: (point[1], point[0]))]}}]
        result = plan(document, [0, 0], [2, 2])
        if possible:
            assert result["status"] == "found"
            assert (result["distance"], result["turns"]) == min(possible)
        else:
            assert result["status"] == "no_route"


def test_actor_footprint_cannot_fit_a_point_sized_gap():
    document = room(7, 5)
    document["layers"] = [layer("top-wall", "obstacle", [3, 0, 4, 2]),
                          layer("bottom-wall", "obstacle", [3, 3, 4, 5])]
    assert plan(document, [1, 2], [5, 2])["status"] == "found"
    document["actor"] = {"width": 2, "height": 2, "anchor": [0, 0]}
    assert plan(document, [1, 2], [5, 2])["status"] == "no_route"
    assert plan(document, [6, 2], [6, 2])["status"] == "endpoint_not_clear"


def test_unknown_ground_stays_unknown_and_cannot_be_routed_through():
    from dotbox.spatial_map import spatial_check

    document = room(5, 3)
    document["known"] = {"subtract": [document["known"], {"rect": [2, 0, 3, 3]}]}
    document["safe"] = deepcopy(document["known"])
    assert spatial_check(document, [2, 1])["classification"] == "unknown"
    assert plan(document, [0, 1], [4, 1])["status"] == "no_route"
    assert plan(document, [2, 1], [2, 1])["status"] == "endpoint_not_clear"


@pytest.mark.parametrize("kind", ["obstacle", "hazard"])
def test_conditional_layers_require_observed_false_to_be_clear(kind):
    document = room(5, 3)
    document["layers"] = [layer("conditional", kind, [2, 0, 3, 3], when="active")]
    for conditions in (None, {}, {"active": None}, {"active": True}):
        assert plan(document, [0, 1], [4, 1], conditions=conditions)["status"] == "no_route"
    result = plan(document, [0, 1], [4, 1], conditions={"active": False})
    assert result["status"] == "found"
    with pytest.raises(ValueError, match="Stale"):
        check(result, document, conditions={"active": None})
    assert plan(document, [0, 1], [4, 1]) == plan(document, [0, 1], [4, 1], conditions={"active": None})


@pytest.mark.parametrize("conditions", [None, {"exit_active": False}, {"exit_active": True}])
def test_all_portals_are_boundaries_even_when_condition_is_false(conditions):
    document = room(5, 3)
    document["layers"] = [layer("exit", "portal", [2, 0, 3, 3], when="exit_active")]
    assert plan(document, [0, 1], [4, 1], conditions=conditions)["status"] == "no_route"
    assert plan(document, [2, 1], [2, 1], conditions=conditions)["status"] == "endpoint_not_clear"
    document["actor"]["width"] = 2
    assert plan(document, [1, 1], [1, 1], conditions=conditions)["status"] == "endpoint_not_clear"


def test_partial_portal_is_avoided_and_goal_stops_before_it():
    document = room(7, 5)
    document["layers"] = [layer("unselected-exit", "portal", [3, 2, 4, 3])]
    result = plan(document, [1, 2], [5, 2])
    assert result["status"] == "found" and result["distance"] == 6
    assert [3, 2] not in result["path"]
    assert plan(document, [1, 2], [2, 2])["distance"] == 1


@pytest.mark.parametrize("field,value", [
    ("revision", 2), ("revision", 0), ("branch_id", "rewound-branch"),
    ("provider_id", "different-provider"), ("session_id", "new-session"),
    ("context_token", "different-token"),
])
def test_state_changes_invalidate_old_route_even_with_identical_room(field, value):
    from dotbox.navigation import check_movement_plan

    document = room()
    result = plan(document, [1, 1], [9, 1])
    changed = packet()
    changed["state_context"][field] = value
    with pytest.raises(ValueError, match="Stale"):
        check_movement_plan(result, document, changed)


@pytest.mark.parametrize("field,value", [
    ("observation_id", "new-observation"), ("edition", "new-edition"),
    ("title", "Same room with a new observation"), ("selection_sha256", "e" * 64),
])
def test_scene_document_changes_invalidate_route(field, value):
    from dotbox.navigation import check_movement_plan

    document = room()
    result = plan(document, [1, 1], [9, 1])
    changed = packet()
    changed[field] = value
    with pytest.raises(ValueError, match="Stale"):
        check_movement_plan(result, document, changed)


def test_map_revision_and_all_condition_changes_invalidate_route():
    document = room()
    document["layers"] = [layer("hazard", "hazard", [0, 0, 1, 1], when="active")]
    result = plan(document, [1, 1], [9, 1], conditions={"active": False})
    changed = deepcopy(document)
    changed["evidence"]["authored"]["revision"] = 2
    with pytest.raises(ValueError, match="Stale"):
        check(result, changed, conditions={"active": False})
    with pytest.raises(ValueError, match="Stale"):
        check(result, document, conditions={"active": True})


@pytest.mark.parametrize("field,value", [("sha256", "e" * 64), ("room", "other-room")])
def test_source_and_room_must_agree_with_scene(field, value):
    document = room()
    document["source"][field] = value
    with pytest.raises(ValueError, match="source|room"):
        plan(document, [1, 1], [9, 1])


def test_state_context_is_required_and_bindings_are_independent_copies():
    from dotbox.navigation import plan_movement

    document, scene, conditions = room(), packet(), {"active": False}
    document["layers"] = [layer("hazard", "hazard", [0, 0, 1, 1], when="active")]
    result = plan_movement(document, [1, 1], [9, 1], scene_packet=scene, conditions=conditions)
    before = deepcopy(result)
    scene["state_context"]["revision"] += 1
    document["source"]["context"] = "changed"
    conditions["active"] = True
    assert result == before
    del scene["state_context"]
    with pytest.raises(ValueError, match="state_context"):
        plan_movement(document, [1, 1], [9, 1], scene_packet=scene)


@pytest.mark.parametrize("field,value", [
    ("path", [[1, 1], [9, 1]]), ("legs", []), ("distance", 1), ("turns", 2),
    ("visited", 0), ("execution", "performed"), ("extra", "ignored?"),
])
def test_edited_proposals_are_rejected_even_with_recomputed_hash(field, value):
    document = room()
    result = plan(document, [1, 1], [9, 1])
    result[field] = value
    reseal(result)
    with pytest.raises(ValueError, match="canonical|Invalid"):
        check(result, document)


def test_other_valid_but_noncanonical_route_is_rejected():
    document = room()
    result = plan(document, [1, 1], [3, 3])
    # Reflect the chosen equal-cost route around its diagonal. Both are clear.
    result["path"] = [[y, x] for x, y in result["path"]]
    directions = {"up": "left", "left": "up", "right": "down", "down": "right"}
    for leg in result["legs"]:
        leg["start"] = leg["start"][::-1]
        leg["end"] = leg["end"][::-1]
        leg["direction"] = directions[leg["direction"]]
    reseal(result)
    with pytest.raises(ValueError, match="canonical"):
        check(result, document)


def test_budget_exhaustion_is_not_no_route_and_zero_length_still_checks_geometry():
    document = room(5, 3)
    result = plan(document, [0, 1], [4, 1], maxnodes=1)
    assert result["status"] == "budget_exhausted" and result["visited"] == 1
    assert result["path"] == [] and result["legs"] == []
    assert result["distance"] is None and result["turns"] is None
    assert check(result, document)["route_available"] is False
    same = plan(document, [0, 1], [0, 1], maxnodes=1)
    assert same["status"] == "found" and same["distance"] == same["turns"] == 0
    assert same["legs"] == []
    document["layers"] = [layer("wall", "obstacle", [2, 0, 3, 3])]
    assert plan(document, [0, 1], [4, 1])["status"] == "no_route"


@pytest.mark.parametrize("start,goal,maxnodes", [
    ([True, 1], [9, 1], 100), ([1.0, 1], [9, 1], 100),
    ([1, 1], [12, 1], 100), ([1, 1], [9, 1], True),
    ([1, 1], [9, 1], 0), ([1, 1], [9, 1], 100001),
])
def test_numeric_input_bounds_are_strict(start, goal, maxnodes):
    with pytest.raises(ValueError):
        plan(room(), start, goal, maxnodes=maxnodes)


@pytest.mark.parametrize("conditions", [{"active": 1}, {"active": "false"}, {"active": float("nan")}, []])
def test_condition_values_are_boolean_or_explicitly_unknown(conditions):
    with pytest.raises(ValueError):
        plan(room(), [1, 1], [9, 1], conditions=conditions)


def test_condition_budget_includes_missing_declared_keys():
    document = room()
    document["layers"] = [layer("hazard", "hazard", [0, 0, 1, 1], when="missing")]
    with pytest.raises(ValueError, match="128"):
        plan(document, [1, 1], [9, 1], conditions={str(i): False for i in range(128)})


@pytest.mark.parametrize("mutation", ["boolean-width", "duplicate-layer", "safe-outside-known", "deep-geometry", "nonfinite-evidence"])
def test_malformed_geometry_fails_closed(mutation):
    document = room()
    if mutation == "boolean-width":
        document["space"]["width"] = True
    elif mutation == "duplicate-layer":
        document["layers"] = [layer("same", "obstacle", [0, 0, 1, 1])] * 2
    elif mutation == "safe-outside-known":
        document["known"] = {"rect": [0, 0, 1, 1]}
    elif mutation == "deep-geometry":
        for _ in range(10):
            document["known"] = {"union": [document["known"], {"rect": [0, 0, 1, 1]}]}
    else:
        document["evidence"]["authored"]["bad"] = float("inf")
    with pytest.raises(ValueError):
        plan(document, [1, 1], [9, 1])


def test_optional_existing_coordinate_domains_contract_remains_supported():
    document = room()
    document["coordinate_domains"] = {
        "format": "fdisbull-coordinate-domains-1", "space": {"name": "authored-grid", "unit": "cell"},
        "bounds": {"world": None, "room": [0, 0, 12, 6], "collision": None, "viewport": None},
        "objects": [], "expectations": [], "alerts": True, "provenance": {"kind": "authored"},
    }
    assert plan(document, [1, 1], [9, 1])["status"] == "found"
    document["coordinate_domains"]["bounds"]["room"] = [0, 0, 13, 6]
    with pytest.raises(ValueError, match="bounds"):
        plan(document, [1, 1], [9, 1])


def test_cli_round_trip_reads_regular_json_and_does_not_modify_inputs(tmp_path, capsys, monkeypatch):
    from dotbox import cli

    def forbidden(*args, **kwargs):
        pytest.fail("Offline navigation constructed a live Client")

    monkeypatch.setattr(cli, "Client", forbidden)
    files = {"map.json": room(), "scene.json": packet(), "conditions.json": {}}
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value))
    before = {name: (tmp_path / name).read_bytes() for name in files}
    args = ["--scene", str(tmp_path / "scene.json"), "--conditions", str(tmp_path / "conditions.json")]
    assert cli.main(["route", "plan", str(tmp_path / "map.json"), *args, "--start", "1", "1", "--goal", "9", "1"]) == 0
    output = capsys.readouterr().out
    (tmp_path / "plan.json").write_text(output)
    assert cli.main(["route", "check", str(tmp_path / "plan.json"), "--map", str(tmp_path / "map.json"), *args]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["valid"] is True
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content
    assert (tmp_path / "plan.json").read_text() == output


@pytest.mark.parametrize("bad", ['{"active":false,"active":true}', '{"active":NaN}', '{"active":1}'])
def test_cli_rejects_duplicate_and_nonfinite_json(tmp_path, capsys, bad):
    from dotbox.navigation import main

    (tmp_path / "map.json").write_text(json.dumps(room()))
    (tmp_path / "conditions.json").write_text(bad)
    args = ["plan", str(tmp_path / "map.json"), "--scene", str(ROOT / "examples/scene_window_closed.json"),
            "--conditions", str(tmp_path / "conditions.json"), "--start", "1", "1", "--goal", "9", "1"]
    assert main(args) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_cli_refuses_special_and_oversized_sources(tmp_path, capsys):
    from dotbox.navigation import MAX_MAP_FILE_BYTES, main

    args = ["--scene", str(ROOT / "examples/scene_window_closed.json"), "--start", "1", "1", "--goal", "9", "1"]
    assert main(["plan", str(tmp_path), *args]) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False
    oversized = tmp_path / "large.json"
    oversized.write_bytes(b" " * (MAX_MAP_FILE_BYTES + 1))
    assert main(["plan", str(oversized), *args]) == 1
    assert "budget" in json.loads(capsys.readouterr().err)["error"]


def test_authored_example_and_installed_self_check():
    from dotbox.navigation import self_check

    document = json.loads((ROOT / "examples/navigation_room.json").read_text())
    assert document["source"]["context"] == "authored-study-map"
    assert plan(document, [1, 3], [10, 3])["status"] == "found"
    assert self_check()["ok"] is True
