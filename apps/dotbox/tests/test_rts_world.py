"""Synthetic RTS observations: identity, disclosure, bounds and real scenes."""

from copy import deepcopy
import json

import pytest

from dotbox import rts_world, scenes
from dotbox.scene_state import SceneStore


def entity(identity="scout", **changes):
    return {"id": identity, "kind": "unit", "label": "Scout", "identity_scope": "observation",
            "incarnation_id": None, "observation_id": "observation-7", "visibility": "visible",
            "audience": "player", "owner_faction": "blue", "controller_faction": None,
            "relation_to_player": "self", "commandable": None, "position": [8, 9],
            "evidence_ref": "authored/entity/7", **changes}


def packet():
    return {"format": "dotbox-rts-world-1", "source_sha256": "a" * 64, "edition": "authored-1",
            "observation_id": "observation-7", "state_context": {"provider_id": "provider", "session_id": "session",
                "branch_id": "branch", "revision": 7, "context_token": "context-7"}, "player_faction": "blue",
            "map": {"space": "tile", "bounds": [0, 0, 64, 64]},
            "camera": {"world_bounds": [0, 0, 15, 10], "screen_bounds": [0, 40, 240, 200],
                       "frame_size": [320, 200], "frame_id": 70, "mode_id": 1, "evidence_ref": "authored/frame/7"},
            "phase": {"name": "gameplay", "input_ready": None, "evidence_ref": "authored/phase/7"},
            "entities": [entity()],
            "selection": {"entity_ids": ["scout"], "pending_action": None, "evidence_ref": "authored/selection/7"},
            "groups": [{"id": "patrol", "kind": "logical", "label": "Patrol", "entity_ids": ["scout"],
                        "observation_id": "observation-7", "audience": "player", "evidence_ref": "authored/group/7"}],
            "events": [{"id": "briefing", "kind": "mission", "text": "Reach the marked area.", "blocking": False,
                        "audience": "player", "observation_id": "observation-7", "evidence_ref": "authored/event/7"}],
            "evidence_ref": "authored/world/7"}


def advance(world):
    result = deepcopy(world)
    result["observation_id"] = "observation-8"
    result["state_context"].update(revision=8, context_token="context-8")
    for name in ("entities", "events", "groups"):
        for record in result[name]:
            record["observation_id"] = result["observation_id"]
    return result


def assign(world, path, value):
    target = world
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def test_validation_copy_and_digest_are_independent_and_ordered():
    original = packet()
    clean = deepcopy(original)
    checked = rts_world.validate_world(original)
    assert checked == original and checked is not original
    checked["entities"][0]["label"] = "Changed returned copy"
    assert original == clean
    reordered = dict(reversed(list(original.items())))
    assert rts_world.world_digest(original) == rts_world.world_digest(reordered)
    assert rts_world.world_digest(checked) != rts_world.world_digest(original)


@pytest.mark.parametrize("path", [(), ("state_context",), ("map",), ("camera",), ("phase",),
                                   ("selection",), ("entities", 0), ("groups", 0), ("events", 0)])
def test_every_record_is_closed(path):
    world = packet()
    target = world
    for key in path:
        target = target[key]
    target["unrecognized"] = True
    with pytest.raises(ValueError):
        rts_world.validate_world(world)


@pytest.mark.parametrize("path,value", [
    (("format",), "other"), (("source_sha256",), "A" * 64), (("edition",), " "),
    (("state_context", "revision"), True), (("state_context", "revision"), -1),
    (("state_context", "revision"), 2**63), (("phase", "input_ready"), 1),
    (("entities", 0, "commandable"), 0), (("events", 0, "blocking"), "unknown"),
    (("entities", 0, "visibility"), "last_seen"), (("entities", 0, "audience"), "everyone"),
    (("entities", 0, "relation_to_player"), "friendly"), (("entities", 0, "identity_scope"), "persistent"),
    (("entities", 0, "position"), [True, 2]), (("entities", 0, "position"), [64, 1]),
    (("entities", 0, "position"), [1.5, 2]), (("map", "bounds"), [0, 0, 0, 10]),
    (("camera", "world_bounds"), [0, 0, 65, 10]), (("camera", "screen_bounds"), [0, 40, 240, 201]),
    (("camera", "frame_size"), [0, 200]), (("camera", "mode_id"), False),
    (("entities", 0, "label"), "\ud800"), (("groups", 0, "kind"), "native_selection"),
    (("selection", "entity_ids"), ["missing"]), (("groups", 0, "entity_ids"), ["scout", "scout"]),
    (("entities", 0, "incarnation_id"), "invented-lifetime"),
    (("entities", 0, "identity_scope"), "incarnation"),
])
def test_invalid_types_geometry_and_references_refuse(path, value):
    world = packet()
    assign(world, path, value)
    with pytest.raises(ValueError):
        rts_world.validate_world(world)


@pytest.mark.parametrize("collection", ["entities", "groups", "events"])
def test_duplicate_or_stale_current_records_refuse(collection):
    world = packet()
    world[collection].append(deepcopy(world[collection][0]))
    with pytest.raises(ValueError):
        rts_world.validate_world(world)
    world = packet()
    world[collection][0]["observation_id"] = "older"
    with pytest.raises(ValueError, match="current observation"):
        rts_world.validate_world(world)


def test_explicit_incarnation_ids_are_unique_and_not_display_names():
    world = packet()
    world["entities"] = [entity("one", identity_scope="incarnation", incarnation_id="allocation-1"),
                         entity("two", identity_scope="incarnation", incarnation_id="allocation-1")]
    world["selection"]["entity_ids"] = []
    world["groups"] = []
    with pytest.raises(ValueError, match="unique explicit"):
        rts_world.validate_world(world)
    world["entities"][1]["incarnation_id"] = "allocation-2"
    scene = rts_world.project_scene(world)
    facts = [f for f in scene["facts"] if f["predicate"] == "relation_to_player"]
    assert len({f["subject"] for f in facts}) == 2


def test_visibility_is_a_provider_assertion_not_an_inferred_camera_test():
    world = packet()
    world["entities"][0]["position"] = [20, 20]
    assert rts_world.validate_world(world)["entities"][0]["position"] == [20, 20]
    assert "(20, 20)" in scenes.project_scene(rts_world.project_scene(world))["narration"]
    world["entities"][0]["position"] = None
    assert "unknown position" in scenes.project_scene(rts_world.project_scene(world))["narration"]


def test_public_projection_allows_visible_enemies_and_allies_without_control_grants():
    world = packet()
    world["entities"] += [entity("enemy", label="Enemy vehicle", owner_faction="red", relation_to_player="enemy", commandable=False),
                           entity("ally", label="Ally vehicle", owner_faction="green", relation_to_player="ally"),
                           entity("hidden", label="HIDDEN_SECRET", visibility="hidden"),
                           entity("offscreen", label="OFFSCREEN_SECRET", visibility="known_offscreen"),
                           entity("private", label="INTERNAL_SECRET", audience="internal")]
    world["groups"].append({**deepcopy(world["groups"][0]), "id": "secret-group", "label": "GROUP_SECRET",
                             "entity_ids": ["scout", "hidden"]})
    world["events"].append({**deepcopy(world["events"][0]), "id": "secret-event", "text": "EVENT_SECRET", "audience": "internal"})
    original = deepcopy(world)
    scene = rts_world.project_scene(world)
    view = scenes.project_scene(scene, detail="detailed")
    assert all(secret not in json.dumps(view) for secret in ("HIDDEN_SECRET", "OFFSCREEN_SECRET", "INTERNAL_SECRET", "GROUP_SECRET", "EVENT_SECRET"))
    assert "Enemy vehicle" in view["narration"] and "Ally vehicle" in view["narration"]
    assert scene["choices"] == [] and world == original
    assert [f["value"] for f in scene["facts"] if f["predicate"] == "commandable"] == [None, False, None]


def test_complete_digest_carries_internal_event_changes_into_scene_identity():
    world = packet()
    world["events"][0]["audience"] = "internal"
    first = rts_world.project_scene(world)
    changed = deepcopy(world)
    changed["events"][0]["text"] = "A different private event"
    second = rts_world.project_scene(changed)
    assert scenes.project_scene(first)["narration"] == scenes.project_scene(second)["narration"]
    assert scenes._digest(first) != scenes._digest(second)
    with pytest.raises(ValueError, match="Stale"):
        scenes.select_choice(second, "move", scenes._digest(first), first["observation_id"])


@pytest.mark.parametrize("collection,maximum", [("entities", 1024), ("events", 64), ("groups", 32)])
def test_record_caps_refuse_oversized_lists(collection, maximum):
    world = packet()
    template = world[collection][0]
    world[collection] = [{**deepcopy(template), "id": f"item_{i}"} for i in range(maximum + 1)]
    with pytest.raises(ValueError, match="limit"):
        rts_world.validate_world(world)


def test_large_world_projects_within_real_fact_budget_and_prioritizes_selection():
    world = packet()
    world["entities"] = [entity(f"unit_{i}") for i in range(1024)]
    world["selection"]["entity_ids"] = ["unit_1023"]
    world["groups"] = [{**deepcopy(world["groups"][0]), "id": f"group_{i}", "entity_ids": ["unit_1023"]} for i in range(32)]
    world["events"] = [{**deepcopy(world["events"][0]), "id": f"event_{i}"} for i in range(64)]
    world["entities"][-1]["label"] = "SELECTED_UNIT"
    scene = rts_world.project_scene(world)
    assert len(scene["facts"]) <= 32 and len(scenes._encode(scene).encode()) <= scenes.MAX_DOCUMENT_BYTES
    assert next(f for f in scene["facts"] if f["id"] == "entity_0")["text"].startswith("SELECTED_UNIT")
    assert any(f["value"] > 0 for f in scene["facts"] if f["predicate"].startswith("omitted_"))


def test_valid_long_text_world_sheds_rows_into_a_useful_bounded_scene():
    world = packet()
    observation = "o" * 2048
    world["observation_id"] = observation
    world["evidence_ref"] = "e" * 2048
    world["state_context"]["context_token"] = "c" * 2048
    for name in ("phase", "camera", "selection"):
        world[name]["evidence_ref"] = "e" * 2048
    world["entities"] = [entity(f"unit_{i}", label="n" * 256, observation_id=observation,
                                 evidence_ref="e" * 2048) for i in range(8)]
    world["selection"]["entity_ids"] = ["unit_7"]
    world["groups"] = []
    world["events"] = [{**deepcopy(world["events"][0]), "id": f"event_{i}", "text": "t" * 2048,
                        "observation_id": observation, "evidence_ref": "e" * 2048} for i in range(8)]
    assert rts_world.validate_world(world) == world
    scene = rts_world.project_scene(world)
    assert scenes.validate_scene(scene) == scene
    assert len(scenes._encode(scene).encode()) <= scenes.MAX_DOCUMENT_BYTES
    assert any(f["id"] == "phase" for f in scene["facts"])
    assert any(f.get("entity_id") for f in scene["facts"])
    assert "omitted" in next(f for f in scene["facts"] if f["id"] == "freshness").get("detail", "")
    assert rts_world.validate_world(world)["events"][0]["text"] == "t" * 2048


def test_json_byte_limit_and_nonfinite_values_refuse_without_mutation():
    world = packet()
    world["entities"] = [entity(f"unit_{i}", evidence_ref="e" * 2048) for i in range(1024)]
    with pytest.raises(ValueError, match="one MiB"):
        rts_world.validate_world(world)
    world = packet()
    world["entities"][0]["position"][0] = float("nan")
    with pytest.raises(ValueError, match="finite JSON"):
        rts_world.validate_world(world)


def test_non_ascii_event_rows_are_shed_but_binding_metadata_is_never_truncated():
    world = packet()
    world["events"] = [{**deepcopy(world["events"][0]), "id": f"event_{i}", "text": "\U0001f680" * 2048}
                        for i in range(8)]
    scene = rts_world.project_scene(world)
    assert len(scenes._encode(scene).encode()) <= scenes.MAX_DOCUMENT_BYTES
    assert scene["state_context"] == world["state_context"]
    assert scene["observation_id"] == world["observation_id"]
    assert len([f for f in scene["facts"] if f["id"].startswith("event_")]) < 8
    for fact in scene["facts"]:
        if fact["id"].startswith("event_"):
            assert fact["text"] == "\U0001f680" * 2048
    world["observation_id"] = "\U0001f680" * 2048
    world["evidence_ref"] = "\U0001f680" * 2048
    world["state_context"]["context_token"] = "\U0001f680" * 2048
    for collection in ("entities", "groups", "events"):
        for record in world[collection]:
            record["observation_id"] = world["observation_id"]
            record["evidence_ref"] = world["evidence_ref"]
    assert rts_world.validate_world(world) == world
    with pytest.raises(ValueError, match="48 KiB"):
        rts_world.project_scene(world)


def test_incarnation_changes_report_affiliation_without_inventing_control_or_events():
    before = packet()
    before["entities"][0].update(identity_scope="incarnation", incarnation_id="allocation-17")
    after = advance(before)
    after["entities"][0].update(owner_faction="red", controller_faction="green", relation_to_player="ally")
    report = rts_world.diff_world(before, after)
    changes = report["entity_changes"][0]["fields"]
    assert set(changes) == {"owner_faction", "controller_faction", "relation_to_player"}
    assert report["newly_observed"] == report["no_longer_observed"] == []
    assert report["events"]["newly_reported"] == report["events"]["changed"] == []
    assert after["entities"][0]["commandable"] is None
    assert rts_world.project_scene(after)["choices"] == []


def test_matching_provider_incarnation_survives_reference_rename():
    before = packet()
    before["entities"][0].update(identity_scope="incarnation", incarnation_id="allocation-17")
    after = advance(before)
    after["entities"][0]["id"] = "renamed"
    after["selection"]["entity_ids"] = ["renamed"]
    after["groups"][0]["entity_ids"] = ["renamed"]
    report = rts_world.diff_world(before, after)
    assert report["entity_changes"][0]["fields"]["id"] == {"before": "scout", "after": "renamed"}
    a, b = (next(f["entity_id"] for f in rts_world.project_scene(p)["facts"] if "entity_id" in f) for p in (before, after))
    assert a == b


def test_observation_refs_and_reused_incarnations_never_claim_continuity():
    before = packet()
    after = advance(before)
    after["entities"][0]["position"] = [9, 9]
    report = rts_world.diff_world(before, after)
    assert report["entity_changes"] == []
    assert report["newly_observed"][0]["id"] == report["no_longer_observed"][0]["id"] == "scout"
    assert report["omissions_are_not_destruction"] is True
    before["entities"][0].update(identity_scope="incarnation", incarnation_id="old-allocation")
    after["entities"][0].update(identity_scope="incarnation", incarnation_id="new-allocation")
    assert rts_world.diff_world(before, after)["entity_changes"] == []


@pytest.mark.parametrize("path,value", [(("source_sha256",), "b"*64), (("edition",), "different"),
    (("state_context", "provider_id"), "other"), (("state_context", "session_id"), "other"),
    (("state_context", "branch_id"), "restored"), (("state_context", "revision"), 6)])
def test_diffs_refuse_incompatible_or_stale_observations(path, value):
    before, after = packet(), advance(packet())
    assign(after, path, value)
    with pytest.raises(ValueError):
        rts_world.diff_world(before, after)


def test_same_revision_is_idempotent_only_for_identical_snapshot():
    before = packet()
    assert rts_world.diff_world(before, before)["entity_changes"] == []
    after = deepcopy(before)
    after["events"][0]["blocking"] = True
    with pytest.raises(ValueError, match="conflicting"):
        rts_world.diff_world(before, after)


def test_events_and_logical_groups_remain_observed_reports_and_do_not_select():
    before = packet()
    after = advance(before)
    after["events"][0].update(blocking=True, text="A mission message awaits a response.")
    after["groups"][0]["entity_ids"] = []
    report = rts_world.diff_world(before, after)
    assert report["events"]["changed"][0]["fields"]["blocking"]["after"] is True
    assert report["groups"]["changed"][0]["fields"]["entity_ids"]["after"] == []
    assert before["selection"] == after["selection"]
    assert "selection" not in report["context_changes"]


def test_real_scene_store_tracks_current_and_historical_identity_after_reopen(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "scenes.sqlite"
    before, after = packet(), advance(packet())
    first, second = (rts_world.project_scene(p) for p in (before, after))
    with SceneStore(path, create=True) as store:
        store.record(first)
        store.record(second)
        records = [f for f in store.memory()["facts"] if f["predicate"] == "relation_to_player"]
        assert len(records) == 2 and sum(f["current_in_snapshot"] for f in records) == 1
        with pytest.raises(ValueError, match="Stale"):
            store.record(first)
        abandoned = advance(after)
        abandoned["state_context"].update(branch_id="restored", revision=9)
        with pytest.raises(ValueError, match="branch binding"):
            store.record(rts_world.project_scene(abandoned))
    with SceneStore(path) as reopened:
        assert reopened.current() == second
        assert reopened.present()["choices"] == []
