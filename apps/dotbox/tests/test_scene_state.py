"""Provider observation persistence, sparse memory and snapshot-bound selection."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3
import stat

import pytest

from dotbox.scene_state import SceneStore


def fact(subject="window", predicate="open", value=False, *, observation_id="observation-1", audience="player"):
    return {"id": subject + "." + predicate, "subject": subject, "predicate": predicate,
            "value": value, "text": f"Reported {subject} {predicate}: {value}.", "audience": audience,
            "observation_id": observation_id, "evidence_ref": "private/observation"}


def packet(revision=1, *, facts=None, **changes):
    observation = f"observation-{revision}"
    return {"format": "dotbox-scene-1", "source_sha256": "a" * 64, "edition": "authored example",
            "scene_id": "lobby", "observation_id": observation, "title": "Lobby",
            "facts": [fact(observation_id=observation)] if facts is None else facts,
            "choices": [{"id": "open_window", "label": "Open the window", "requires": [],
                         "observation_id": observation, "available": True,
                         "route": {"kind": "ordinary", "reference": "observed open route"}}],
            "guide_sources": [], "guide_claims": [],
            "state_context": {"provider_id": "authored-provider", "session_id": "session-one",
                              "branch_id": "branch-one", "revision": revision, "context_token": f"token-{revision}"},
            **changes}


def outcome(effects="partial", *, complete=False):
    return {"id": "open-attempt", "action_sent": True, "complete": complete, "effects": effects,
            "phase": "state", "evidence_ref": "private/action-receipt"}


@pytest.fixture
def store(tmp_path):
    with SceneStore(tmp_path / "private" / "scene.sqlite", create=True) as value:
        yield value


def test_latest_packet_and_last_reports_survive_reopening(store):
    first = packet()
    receipt = store.record(first)
    assert receipt["status"] == "recorded" and receipt["scope"] == "persisted_snapshot_only"
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    with SceneStore(store.path) as reopened:
        assert reopened.current() == first
        memory = reopened.memory()
        assert memory["head"]["revision"] == 1
        assert memory["facts"][0]["observed_observation_id"] == "observation-1"
        assert memory["facts"][0]["current_in_snapshot"] is True
        assert memory["scope"] == "internal_only"
        assert memory["latest_outcome"] is None


def test_sparse_reports_preserve_history_without_inventing_current_flags(store):
    store.record(packet(facts=[fact(), fact("door", "locked", True, audience="internal")]))
    store.record(packet(2, facts=[fact("window", "open", None, observation_id="observation-2")]))
    memory = {item["subject"]: item for item in store.memory()["facts"]}
    assert memory["window"]["value"] is None
    assert memory["window"]["current_in_snapshot"] is True
    assert memory["door"]["value"] is True
    assert memory["door"]["current_in_snapshot"] is False
    assert memory["door"]["observed_revision"] == 1
    assert all(item["subject"] != "door" for item in store.present()["facts"])
    assert store.current()["facts"][0]["value"] is None


@pytest.mark.parametrize("effects,complete", [("partial", False), ("unknown", False), ("applied-confirmed", True)])
def test_effect_receipts_do_not_apply_predicted_flags_or_inventory(store, effects, complete):
    store.record(packet())
    receipt = outcome(effects, complete=complete)
    store.record(packet(2, facts=[], outcome=receipt))
    memory = store.memory()
    assert memory["latest_outcome"]["outcome"] == receipt
    assert memory["latest_outcome"]["current_in_snapshot"] is True
    assert len(memory["facts"]) == 1
    assert memory["facts"][0]["value"] is False
    assert memory["facts"][0]["current_in_snapshot"] is False
    assert store.present()["facts"] == []
    store.record(packet(3, facts=[]))
    retained = store.memory()["latest_outcome"]
    assert retained["outcome"] == receipt
    assert retained["observed_revision"] == 2
    assert retained["current_in_snapshot"] is False


def test_new_offscreen_flag_invalidates_old_selection_in_same_room(store):
    first = packet(facts=[fact(), fact("far_door", "locked", True, audience="internal")])
    store.record(first)
    old_view = store.present()
    fresh = packet(2, facts=[fact(observation_id="observation-2"),
                            fact("far_door", "locked", False, observation_id="observation-2", audience="internal")])
    store.record(fresh)
    assert store.current()["scene_id"] == first["scene_id"]
    with pytest.raises(ValueError, match="Stale"):
        store.choose("open_window", old_view["scene_sha256"], old_view["observation_id"])
    new_view = store.present()
    intent = store.choose("open_window", new_view["scene_sha256"], new_view["observation_id"])
    assert intent["execution"] == "not_performed" and intent["live_applicability"] == "unverified"
    assert intent["scope"] == "persisted_snapshot_only"
    assert all(item["subject"] != "far_door" for item in new_view["facts"])


def test_confirmed_open_observation_replaces_fact_and_removes_reported_unavailable_choice(store):
    store.record(packet())
    assert store.present()["suggested_choice_ids"] == ["open_window"]
    opened = packet(2, facts=[fact(value=True, observation_id="observation-2")])
    opened["choices"][0]["available"] = False
    store.record(opened)
    assert store.memory()["facts"][0]["value"] is True
    assert store.present()["suggested_choice_ids"] == []
    view = store.present()
    with pytest.raises(ValueError, match="not currently offered"):
        store.choose("open_window", view["scene_sha256"], view["observation_id"])


def test_equal_revision_identical_packet_is_idempotent(store):
    first = packet(outcome=outcome())
    receipt = store.record(first)
    before = store.path.read_bytes()
    same = json.loads(json.dumps(first, sort_keys=True))
    repeated = store.record(same)
    assert repeated == {**receipt, "status": "unchanged"}
    assert store.path.read_bytes() == before
    assert len(store.memory()["facts"]) == 1


@pytest.mark.parametrize("change", ["older", "same-revision-conflict"])
def test_late_or_conflicting_observations_cannot_replace_head(store, change):
    current = packet(4)
    store.record(current)
    incoming = packet(3) if change == "older" else {**current, "title": "Different report"}
    with pytest.raises(ValueError, match="Stale|Conflicting"):
        store.record(incoming)
    assert store.current() == current
    assert store.memory()["head"]["revision"] == 4


@pytest.mark.parametrize("field", ["source_sha256", "edition", "selection_sha256", "provider_id", "session_id", "branch_id"])
def test_source_session_and_branch_bindings_cannot_change(store, field):
    first = packet(selection_sha256="b" * 64)
    store.record(first)
    changed = packet(2, selection_sha256="b" * 64)
    if field in changed["state_context"]:
        changed["state_context"][field] = "another-identity"
    else:
        changed[field] = "c" * 64 if field.endswith("sha256") else "another edition"
    with pytest.raises(ValueError, match="binding differs"):
        store.record(changed)
    assert store.current() == first


def test_missing_optional_selection_cannot_weaken_first_binding(store):
    store.record(packet(selection_sha256="b" * 64))
    with pytest.raises(ValueError, match="binding differs"):
        store.record(packet(2))


def test_restore_branch_has_separate_observation_memory(store):
    store.record(packet())
    restored = packet(0, facts=[])
    restored["state_context"]["branch_id"] = "restored-branch"
    with pytest.raises(ValueError, match="new store"):
        store.record(restored)
    with SceneStore(store.path.parent / "restored.sqlite", create=True) as other:
        other.record(restored)
        assert other.current() == restored
        assert other.memory()["facts"] == []
    assert store.current() == packet()


def test_old_facts_carried_in_a_new_packet_are_not_reaffirmed(store):
    old = fact()
    store.record(packet(facts=[old]))
    store.record(packet(2, facts=[old]))
    remembered = store.memory()["facts"][0]
    assert remembered["observed_revision"] == 1
    assert remembered["current_in_snapshot"] is False
    assert store.present()["facts"] == []


def test_same_local_subject_in_different_scenes_keeps_distinct_history(store):
    store.record(packet(scene_id="hall", facts=[fact("door", "locked", True)]))
    store.record(packet(2, scene_id="kitchen", facts=[fact("door", "locked", False,
                                                          observation_id="observation-2")]))
    remembered = {item["observed_scene_id"]: item for item in store.memory(subject="door")["facts"]}
    assert set(remembered) == {"hall", "kitchen"}
    assert remembered["hall"]["value"] is True
    assert remembered["hall"]["observed_revision"] == 1
    assert remembered["hall"]["current_in_snapshot"] is False
    assert remembered["kitchen"]["value"] is False
    assert remembered["kitchen"]["current_in_snapshot"] is True
    assert all(item["identity_scope"] == "scene" for item in remembered.values())
    store.record(packet(3, scene_id="hall", facts=[fact("door", "locked", None,
                                                       observation_id="observation-3")]))
    again = {item["observed_scene_id"]: item for item in store.memory(subject="door")["facts"]}
    assert len(again) == 2
    assert again["hall"]["value"] is None and again["hall"]["current_in_snapshot"]
    assert again["kitchen"]["value"] is False and not again["kitchen"]["current_in_snapshot"]


def test_provider_entity_identity_updates_across_scenes_and_subject_aliases(store):
    first = {**fact("gate", "locked", True, audience="internal"), "entity_id": "world/north-gate"}
    store.record(packet(scene_id="hall", facts=[first]))
    later = {**fact("north gate", "locked", False, observation_id="observation-2", audience="internal"),
             "id": "gate.unlocked-report", "entity_id": "world/north-gate"}
    store.record(packet(2, scene_id="switch_room", facts=[later]))
    reports = store.memory()["facts"]
    assert len(reports) == 1
    assert reports[0]["entity_id"] == "world/north-gate"
    assert reports[0]["identity_scope"] == "entity"
    assert reports[0]["subject"] == "north gate" and reports[0]["value"] is False
    assert reports[0]["observed_revision"] == 2 and reports[0]["observed_scene_id"] == "switch_room"
    assert reports[0]["current_in_snapshot"] is True
    assert store.memory(subject="gate")["facts"] == []
    assert store.memory(subject="north gate")["facts"] == reports
    assert store.present()["facts"] == []
    store.record(packet(3, scene_id="courtyard", facts=[]))
    historical = store.memory()["facts"][0]
    assert historical["observed_revision"] == 2
    assert historical["current_in_snapshot"] is False


def test_fact_identity_uses_structural_keys_without_delimiter_collisions(store):
    store.record(packet(scene_id="hall:door", facts=[fact("latch", "locked", True)]))
    store.record(packet(2, scene_id="hall", facts=[fact("door:latch", "locked", False,
                                                       observation_id="observation-2")]))
    a = {**fact("first", "open", True, observation_id="observation-3"), "entity_id": "door:locked"}
    b = {**fact("second", "locked:open", False, observation_id="observation-3"), "entity_id": "door"}
    store.record(packet(3, facts=[a, b]))
    records = store.memory()["facts"]
    assert len(records) == 4
    assert len([item for item in records if item["identity_scope"] == "scene"]) == 2
    assert len([item for item in records if item["identity_scope"] == "entity"]) == 2
    assert all(not item["current_in_snapshot"] for item in records if item["identity_scope"] == "scene")
    assert {tuple(json.loads(row[0])) for row in store.db.execute("SELECT identity FROM scene_facts")} == {
        ("scene", "hall:door", "latch", "locked"), ("scene", "hall", "door:latch", "locked"),
        ("entity", "door:locked", "open"), ("entity", "door", "locked:open")}


def test_current_and_memory_are_independent_copies(store):
    original = packet(outcome=outcome())
    expected = deepcopy(original)
    store.record(original)
    original["facts"][0]["value"] = True
    original["outcome"]["effects"] = "unknown"
    retrieved = store.current()
    retrieved["state_context"]["revision"] = 99
    retrieved["facts"].clear()
    memory = store.memory()
    memory["facts"][0]["value"] = True
    memory["latest_outcome"]["outcome"]["effects"] = "unknown"
    assert store.current() == expected
    assert store.memory()["facts"][0]["value"] is False
    assert store.memory()["latest_outcome"]["outcome"]["effects"] == "partial"


def test_passive_look_and_present_leave_snapshot_and_database_unchanged(store):
    first = packet(outcome=outcome())
    store.record(first)
    before = store.path.read_bytes()
    view = store.present()
    looked = store.look()
    assert looked["narration"] == view["narration"]
    assert looked["scope"] == "persisted_snapshot_only"
    assert store.current() == first
    assert store.path.read_bytes() == before
    assert "private/action-receipt" not in json.dumps(view)
    assert "private/action-receipt" not in json.dumps(looked)


def test_competing_deliveries_keep_the_newest_provider_revision(store):
    store.record(packet())

    def deliver(revision):
        with SceneStore(store.path) as other:
            try:
                return other.record(packet(revision))["status"]
            except ValueError as error:
                assert "Stale" in str(error)
                return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(deliver, (2, 3)))
    assert results[1] == "recorded"
    assert store.current()["state_context"]["revision"] == 3


def test_memory_filter_and_limit_are_bounded(store):
    store.record(packet(facts=[fact("door", "locked", True), fact("door", "open", False), fact()]))
    limited = store.memory(limit=2)
    assert len(limited["facts"]) == 2 and limited["has_more"]
    door = store.memory(subject="door", limit=2)
    assert len(door["facts"]) == 2 and not door["has_more"]
    assert {item["predicate"] for item in door["facts"]} == {"locked", "open"}
    assert store.memory(subject="unseen")["facts"] == []
    for limit in (False, 0, 257, 1.5):
        with pytest.raises(ValueError, match="limit"):
            store.memory(limit=limit)


def test_no_observation_and_missing_state_context_are_explicit(store):
    with pytest.raises(ValueError, match="no recorded observation"):
        store.current()
    legacy = packet()
    del legacy["state_context"]
    with pytest.raises(ValueError, match="require state_context"):
        store.record(legacy)
    assert store.db.execute("SELECT COUNT(*) FROM scene_head").fetchone()[0] == 0


def test_missing_store_is_not_created_by_default(tmp_path):
    path = tmp_path / "missing" / "scene.sqlite"
    with pytest.raises(ValueError, match="does not exist"):
        SceneStore(path)
    assert not path.parent.exists()


def test_foreign_database_is_rejected_without_mutation(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "other.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE user_work(value TEXT)")
        db.execute("INSERT INTO user_work VALUES ('preserve this')")
    path.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not a DotBox scene store"):
        SceneStore(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["public_parent", "public_file", "symlink", "dangling_symlink", "parent_symlink"])
def test_private_storage_guards_preserve_foreign_files(tmp_path, kind):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755 if kind == "public_parent" else 0o700)
    path = directory / "scene.sqlite"
    original = tmp_path / "original"
    original.write_bytes(b"preserve original")
    if kind == "public_file":
        path.write_bytes(b"public file")
        path.chmod(0o644)
    elif kind == "symlink":
        path.symlink_to(original)
    elif kind == "dangling_symlink":
        path.symlink_to(tmp_path / "absent")
    elif kind == "parent_symlink":
        link = tmp_path / "linked"
        link.symlink_to(directory, target_is_directory=True)
        path = link / "scene.sqlite"
    with pytest.raises(ValueError, match="private"):
        SceneStore(path, create=True)
    assert original.read_bytes() == b"preserve original"
    if kind in ("public_parent", "parent_symlink"):
        assert not path.exists()
