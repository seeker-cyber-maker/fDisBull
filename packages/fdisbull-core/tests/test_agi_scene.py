"""Independent stopped-scene contracts using authored snapshots and bytecode.

Expected actor positions and instruction effects are literal fixture facts.
The tests use only the public consumer API; no VM, decoder, or implementation
helper supplies the expected projection.
"""
from copy import deepcopy
import hashlib

import pytest

from fdisbull_core.agi_scene import AGISceneConsumer, SceneInputError


SESSION = "authored-scene-attachment"
PROFILE = "agi-2917-scalar-position-pilot-1"
CODE = bytes.fromhex("25000a1425011e2825000a142500323c2501465000")
SOURCE = {"sha256": hashlib.sha256(CODE).hexdigest(), "size": len(CODE),
          "logic_id": 0, "profile": PROFILE}
# Five position instructions, including one unchanged position, then return.
PCS = (0, 4, 8, 12, 16, 20, 21)
ACTOR_POSITIONS = (
    ((0, 0), (0, 0)),
    ((10, 20), (0, 0)),
    ((10, 20), (30, 40)),
    ((10, 20), (30, 40)),
    ((50, 60), (30, 40)),
    ((50, 60), (70, 80)),
    ((50, 60), (70, 80)),
)
CHANGES = {
    1: (0, (0, 0), (10, 20)),
    2: (1, (0, 0), (30, 40)),
    4: (0, (10, 20), (50, 60)),
    5: (1, (30, 40), (70, 80)),
}


def position(x=0, y=0):
    return {"x": x, "y": y, "prev_x": x, "prev_y": y}


def actors_at(retired):
    pairs = ACTOR_POSITIONS[retired]
    return [{"id": index, **position(*(pairs[index] if index < 2 else (0, 0)))}
            for index in range(16)]


def journal(retired, mask=2, generation=3):
    records = []
    for ordinal in range(1, retired + 1):
        pc, next_pc = PCS[ordinal - 1], PCS[ordinal]
        common = {"retired": ordinal, "pc": pc, "next_pc": next_pc,
                  "opcode": CODE[pc], "bytes": list(CODE[pc:next_pc]),
                  "control_generation": generation}
        if mask & 1:
            records.append({"kind": "retire", **common})
        if mask & 2 and ordinal in CHANGES:
            actor, before, after = CHANGES[ordinal]
            records.append({"kind": "position", **common, "actor": actor,
                            "before": position(*before), "after": position(*after)})
    for seq, record in enumerate(records, 1):
        record["seq"] = seq
    return records


def checkpoint(retired=0, *, mask=2, generation=3, epoch=1, capacity=64,
               invocation=None, records=None, scene_dropped=0, disasm_dropped=0):
    """Build one full readout from explicit authored effects and accounting."""
    records = deepcopy(journal(retired, mask, generation) if records is None else records)
    stored_scene = sum(record["kind"] == "position" for record in records)
    stored_disasm = sum(record["kind"] == "retire" for record in records)
    state = {
        "schema": "fdisbull-agi-native-state-1", "source": deepcopy(SOURCE),
        "guest": {"pc": PCS[retired], "status": "ready" if not retired else
                  "return" if retired == 6 else "budget", "fault": None,
                  "retired": retired, "variables": [0] * 256, "flags": [0] * 256,
                  "actors": actors_at(retired)},
        "run": {"invocation": retired if invocation is None else invocation,
                "retired": retired, "elapsed_ns": 0},
        "observation": {
            "mask": mask, "capacity": capacity, "count": len(records),
            "eligible": len(records) + scene_dropped + disasm_dropped,
            "dropped": scene_dropped + disasm_dropped,
            "control_generation": generation, "epoch": epoch,
            "per_channel": {
                "scene": {"stored": stored_scene, "eligible": stored_scene + scene_dropped,
                          "dropped": scene_dropped},
                "disasm": {"stored": stored_disasm, "eligible": stored_disasm + disasm_dropped,
                           "dropped": disasm_dropped},
            },
        },
    }
    events = {"schema": "fdisbull-agi-native-events-1",
              "source": deepcopy(SOURCE), "epoch": epoch, "events": records}
    return state, events


def consume(consumer, state, events, session=SESSION):
    return consumer.consume(events, state, session_id=session)


def attach(state=None):
    return AGISceneConsumer.from_snapshot(
        checkpoint()[0] if state is None else state, session_id=SESSION,
    )


def assert_actors(view, retired):
    assert [{key: actor[key] for key in ("id", "x", "y", "prev_x", "prev_y")}
            for actor in view["actors"]] == actors_at(retired)


def assert_gap(consumer, state, events, reason):
    before = consumer.view()
    result = consume(consumer, state, events)
    assert result == {"status": "resync_required", "needs_resync": True,
                      "reason": reason, "changes": []}
    assert consumer.view() == before
    return result


def fault_after_first_position(state, events):
    """Use a distinct authored program: position followed by unsupported opcode9."""
    code = bytes.fromhex("25000a1409")
    source = {**SOURCE, "sha256": hashlib.sha256(code).hexdigest(), "size": len(code)}
    state["source"] = source
    events["source"] = deepcopy(source)
    state["guest"]["status"] = "fault"
    state["guest"]["fault"] = {"code": 1, "name": "unsupported_opcode", "pc": 4,
                                "opcode": 9}
    return source


def test_attach_adopts_current_snapshot_and_uses_eligible_high_water_mark():
    state, events = checkpoint(2, records=[], capacity=0, scene_dropped=2)
    consumer = attach(state)
    view = consumer.view()
    assert_actors(view, 2)
    assert view["checkpoint"]["eligible"] == 2
    assert view["coverage"]["history_complete_since_attach"] is True
    assert view["coverage"]["history_start"] == view["checkpoint"]
    assert all(actor["witness"] is None for actor in view["actors"])
    assert consume(consumer, state, events)["status"] == "unchanged"
    # Grow stopped storage, then observe a new sequence beyond the lost prefix.
    controlled, controlled_events = checkpoint(2, records=[], capacity=4, generation=4,
                                               scene_dropped=2)
    assert consume(consumer, controlled, controlled_events)["status"] == "unchanged"
    new = journal(4, generation=4)[-1]
    new["seq"] = 3
    current, current_events = checkpoint(4, records=[new], capacity=4, generation=4,
                                         scene_dropped=2)
    update = consume(consumer, current, current_events)
    assert [record["seq"] for record in update["changes"]] == [3]
    assert_actors(consumer.view(), 4)
    assert consumer.view()["actors"][1]["witness"] is None


@pytest.mark.parametrize("mask", [2, 3], ids=["scene", "both"])
def test_applies_only_new_position_records_across_overlapping_readouts(mask):
    consumer = attach(checkpoint(mask=mask)[0])
    for retired, pcs in ((1, [0]), (2, [4]), (5, [12, 16])):
        state, events = checkpoint(retired, mask=mask)
        update = consume(consumer, state, events)
        assert update["status"] == "applied" and update["needs_resync"] is False
        assert update["reason"] is None
        assert [record["pc"] for record in update["changes"]] == pcs
        assert all(record["kind"] == "position" for record in update["changes"])
        assert_actors(consumer.view(), retired)
        assert consume(consumer, state, events) == {
            "status": "unchanged", "needs_resync": False, "reason": None, "changes": [],
        }
    view = consumer.view()
    assert view["schema"] == "fdisbull-agi-scene-view-1"
    assert view["session_id"] == SESSION and view["source"] == SOURCE
    assert view["actors"][0]["witness"]["pc"] == 12
    assert view["actors"][1]["witness"]["pc"] == 16
    assert view["coverage"]["history_complete_since_attach"] is True
    assert view["coverage"]["gap_count"] == 0


def test_attach_skips_existing_records_but_retains_new_source_witness():
    initial, old = checkpoint(2)
    consumer = attach(initial)
    assert consume(consumer, initial, old)["changes"] == []
    assert all(actor["witness"] is None for actor in consumer.view()["actors"])
    state, events = checkpoint(4)
    update = consume(consumer, state, events)
    assert [record["pc"] for record in update["changes"]] == [12]
    witness = consumer.view()["actors"][0]["witness"]
    assert witness == events["events"][-1]
    assert witness["bytes"] == [37, 0, 50, 60]
    assert consumer.view()["actors"][1]["witness"] is None


def test_before_state_mismatch_rejects_entire_batch_transactionally():
    consumer = attach()
    state, events = checkpoint(2)
    events["events"][1]["before"] = position(99, 99)
    assert_gap(consumer, state, events, "before_state_mismatch")
    assert_actors(consumer.view(), 0)


def test_final_actor_mismatch_does_not_publish_a_partially_verified_view():
    consumer = attach()
    state, events = checkpoint(2)
    state["guest"]["actors"][1].update(position(99, 99))
    assert_gap(consumer, state, events, "actor_state_mismatch")
    assert_actors(consumer.view(), 0)


def test_malformed_later_event_does_not_apply_valid_prefix():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(2)
    events["events"][1]["bytes"][2] = 256
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    assert consumer.view() == before
    valid_state, valid_events = checkpoint(2)
    assert len(consume(consumer, valid_state, valid_events)["changes"]) == 2


def test_conflicting_duplicate_is_not_silently_discarded():
    consumer = attach()
    state, events = checkpoint(1)
    consume(consumer, state, events)
    before = consumer.view()
    later, journal_with_conflict = checkpoint(2)
    # An otherwise valid unknown JSON field is also part of the raw record.
    journal_with_conflict["events"][0]["annotation"] = "changed retained prefix"
    with pytest.raises(SceneInputError, match="prefix"):
        consume(consumer, later, journal_with_conflict)
    assert consumer.view() == before


def test_direct_position_witness_must_match_its_literal_coordinates():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    events["events"][0]["after"] = position(30, 40)
    state["guest"]["actors"][0].update(position(30, 40))
    assert events["events"][0]["bytes"] == [37, 0, 10, 20]
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    assert consumer.view() == before


def test_new_event_cannot_predate_the_checkpoint_control_generation():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    events["events"][0]["control_generation"] = 2
    assert state["observation"]["control_generation"] == 3
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    assert consumer.view() == before


@pytest.mark.parametrize("mask,capacity", [(2, 0), (3, 1)],
                         ids=["zero-capacity", "both-retirement-only"])
def test_lost_scene_is_reported_even_if_its_retirement_was_retained(mask, capacity):
    consumer = attach(checkpoint(mask=mask, capacity=capacity)[0])
    retained = [] if capacity == 0 else [journal(1, 3)[0]]
    state, events = checkpoint(1, mask=mask, capacity=capacity,
                               records=retained, scene_dropped=1)
    assert_gap(consumer, state, events, "scene_records_lost")


def test_disasm_loss_alone_does_not_break_scene_continuity():
    consumer = attach(checkpoint(mask=3, capacity=9)[0])
    retained = journal(6, 3)[:-1]  # All four changes fit; only return's record is lost.
    state, events = checkpoint(6, mask=3, capacity=9, records=retained, disasm_dropped=1)
    update = consume(consumer, state, events)
    assert [record["pc"] for record in update["changes"]] == [0, 4, 12, 16]
    assert_actors(consumer.view(), 6)
    assert consumer.view()["checkpoint"]["eligible"] == 10
    assert consumer.view()["coverage"]["history_complete_since_attach"] is True


def test_disabled_scene_is_a_gap_after_work_even_with_current_snapshot():
    consumer = attach(checkpoint(mask=0)[0])
    state, events = checkpoint(2, mask=0)
    update = assert_gap(consumer, state, events, "observation_disabled")
    recovered = consumer.resync(state, reason=update["reason"], session_id=SESSION)
    assert recovered["status"] == "resynced" and recovered["changes"] == []
    assert_actors(consumer.view(), 2)
    assert consumer.view()["coverage"]["history_complete_since_attach"] is False
    assert all(actor["witness"] is None for actor in consumer.view()["actors"])


def test_disabled_scene_without_work_is_an_idempotent_snapshot_view():
    state, events = checkpoint(mask=0)
    consumer = attach(state)
    before = consumer.view()
    for _ in range(2):
        assert consume(consumer, state, events)["status"] == "unchanged"
    assert consumer.view() == before
    assert before["coverage"]["history_complete_since_attach"] is True
    assert before["coverage"]["scene_enabled"] is False


def test_reenabled_scene_and_matching_coordinates_do_not_prove_continuity():
    code = bytes.fromhex("25000a142500000000")
    source = {**SOURCE, "size": len(code), "sha256": hashlib.sha256(code).hexdigest()}
    initial, _ = checkpoint()
    initial["source"] = deepcopy(source)
    consumer = attach(initial)
    state, events = checkpoint(2, generation=5, records=[])
    state["source"] = deepcopy(source)
    events["source"] = deepcopy(source)
    state["guest"]["actors"] = actors_at(0)
    assert state["guest"]["pc"] == 8  # Both positions completed, return is next.
    assert state["guest"]["actors"] == initial["guest"]["actors"]
    assert_gap(consumer, state, events, "control_changed_during_execution")


def test_stopped_control_change_can_be_checkpointed_before_further_work():
    consumer = attach(checkpoint(mask=0)[0])
    controlled, records = checkpoint(mask=2, generation=4)
    assert consume(consumer, controlled, records)["status"] == "unchanged"
    current, current_records = checkpoint(1, mask=2, generation=4)
    assert consume(consumer, current, current_records)["status"] == "applied"
    assert_actors(consumer.view(), 1)
    assert consumer.view()["coverage"]["history_complete_since_attach"] is True


@pytest.mark.parametrize("operation", ["clear", "restart"])
def test_epoch_change_requires_explicit_resync_and_clears_provenance(operation):
    consumer = attach()
    state, events = checkpoint(2)
    consume(consumer, state, events)
    assert consumer.view()["actors"][0]["witness"] is not None
    retired = 2 if operation == "clear" else 0
    changed, records = checkpoint(retired, records=[], epoch=2, generation=4, invocation=3)
    assert_gap(consumer, changed, records, "epoch_changed")
    result = consumer.resync(changed, reason="epoch_changed", session_id=SESSION)
    assert result == {"status": "resynced", "needs_resync": False,
                      "reason": "epoch_changed", "changes": []}
    view = consumer.view()
    assert_actors(view, retired)
    assert view["checkpoint"]["epoch"] == 2
    assert all(actor["witness"] is None for actor in view["actors"])
    assert view["coverage"]["gap_count"] == 1
    assert view["coverage"]["history_complete_since_attach"] is False


def test_resync_recovers_state_but_does_not_restore_missing_history():
    consumer = attach(checkpoint(capacity=1)[0])
    first = journal(1)[0]
    state, events = checkpoint(2, records=[first], capacity=1, scene_dropped=1)
    assert_gap(consumer, state, events, "scene_records_lost")
    consumer.resync(state, reason="scene_records_lost", session_id=SESSION)
    assert_actors(consumer.view(), 2)
    gap = consumer.view()["coverage"]["last_gap"]
    assert gap["reason"] == "scene_records_lost"
    assert gap["from"]["retired"] == 0 and gap["to"]["retired"] == 2
    controlled, controlled_events = checkpoint(2, records=[first], capacity=4,
                                               generation=4, scene_dropped=1)
    assert consume(consumer, controlled, controlled_events)["status"] == "unchanged"
    new = journal(4, generation=4)[-1]
    new["seq"] = 3
    current, current_events = checkpoint(4, records=[first, new], capacity=4,
                                         generation=4, scene_dropped=1)
    update = consume(consumer, current, current_events)
    assert [record["pc"] for record in update["changes"]] == [12]
    view = consumer.view()
    assert_actors(view, 4)
    assert view["coverage"]["history_complete_since_attach"] is False
    assert view["coverage"]["gap_count"] == 1
    assert view["coverage"]["last_gap"] == gap
    assert view["actors"][0]["witness"]["pc"] == 12
    assert view["actors"][1]["witness"] is None


@pytest.mark.parametrize("status", ["budget", "fault", "external"])
def test_committed_position_survives_a_nonreturn_stop(status):
    initial, _ = checkpoint()
    state, events = checkpoint(1)
    state["guest"]["status"] = status
    if status == "fault":
        initial["source"] = deepcopy(fault_after_first_position(state, events))
    consumer = attach(initial)
    assert consume(consumer, state, events)["status"] == "applied"
    assert_actors(consumer.view(), 1)
    assert consumer.view()["guest"]["status"] == status
    assert consumer.view()["guest"]["fault"] == state["guest"]["fault"]
    assert consumer.view()["actors"][0]["witness"]["pc"] == 0


@pytest.mark.parametrize("status", ["return", "fault"])
def test_sticky_terminal_continue_does_not_duplicate_positions(status):
    retired = 6 if status == "return" else 1
    initial, _ = checkpoint()
    state, events = checkpoint(retired)
    if status == "fault":
        initial["source"] = deepcopy(fault_after_first_position(state, events))
    consumer = attach(initial)
    consume(consumer, state, events)
    before = consumer.view()
    continued = deepcopy(state)
    continued["run"]["invocation"] += 1
    continued["run"]["retired"] = 0
    assert consume(consumer, continued, events)["changes"] == []
    view = consumer.view()
    assert view["actors"] == before["actors"]
    assert view["guest"] == before["guest"]
    assert view["checkpoint"]["retired"] == retired
    assert view["checkpoint"]["invocation"] == before["checkpoint"]["invocation"] + 1
    assert view["coverage"]["history_complete_since_attach"] is True


@pytest.mark.parametrize("field,value", [
    ("sha256", "a5" * 32), ("size", 16), ("logic_id", 1),
    ("profile", "different-engine-profile"),
])
def test_source_tuple_mismatch_is_an_error_without_implicit_rebind(field, value):
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    state["source"][field] = value
    events["source"][field] = value
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    with pytest.raises(SceneInputError):
        consumer.resync(state, reason="replacement", session_id=SESSION)
    assert consumer.view() == before


def test_event_and_state_source_disagreement_is_rejected():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    events["source"]["sha256"] = "a5" * 32
    with pytest.raises(SceneInputError, match="source"):
        consume(consumer, state, events)
    assert consumer.view() == before


def test_event_epoch_must_match_the_accompanying_stopped_state():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    events["epoch"] = 0
    with pytest.raises(SceneInputError, match="epoch"):
        consume(consumer, state, events)
    assert consumer.view() == before


def test_identical_source_in_a_different_session_requires_a_new_consumer():
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(1)
    with pytest.raises(SceneInputError, match="session"):
        consume(consumer, state, events, session="another-attachment")
    with pytest.raises(SceneInputError, match="session"):
        consumer.resync(state, reason="new process", session_id="another-attachment")
    assert consumer.view() == before
    replacement = AGISceneConsumer.from_snapshot(state, session_id="another-attachment")
    assert_actors(replacement.view(), 1)
    assert replacement.view()["session_id"] == "another-attachment"


@pytest.mark.parametrize("session_id", ["", None, 123])
def test_invalid_session_identity_is_refused(session_id):
    state, _ = checkpoint()
    with pytest.raises(SceneInputError, match="session"):
        AGISceneConsumer.from_snapshot(state, session_id=session_id)


@pytest.mark.parametrize("damage", ["old_snapshot", "generation", "invocation"])
def test_stale_same_epoch_input_does_not_rewind_projection(damage):
    consumer = attach()
    state, events = checkpoint(2)
    consume(consumer, state, events)
    before = consumer.view()
    if damage == "old_snapshot":
        state, events = checkpoint(1)
    elif damage == "generation":
        state["observation"]["control_generation"] = 2
    else:
        state["run"]["invocation"] = 1
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    with pytest.raises(SceneInputError):
        consumer.resync(state, reason="stale", session_id=SESSION)
    assert consumer.view() == before


@pytest.mark.parametrize("damage", [
    "running", "status_container", "actor_count", "duplicate_actor",
    "coordinate_bool", "coordinate_range", "total_count", "channel_total",
    "negative_counter",
])
def test_malformed_stopped_snapshot_is_refused(damage):
    state, events = checkpoint()
    if damage == "running":
        state["guest"]["status"] = "running"
    elif damage == "status_container":
        state["guest"]["status"] = []
    elif damage == "actor_count":
        state["guest"]["actors"].pop()
    elif damage == "duplicate_actor":
        state["guest"]["actors"][1]["id"] = 0
    elif damage == "coordinate_bool":
        state["guest"]["actors"][0]["x"] = True
    elif damage == "coordinate_range":
        state["guest"]["actors"][0]["y"] = 256
    elif damage == "total_count":
        state["observation"]["count"] = 1
    elif damage == "channel_total":
        state["observation"]["per_channel"]["scene"]["eligible"] = 1
    else:
        state["observation"]["eligible"] = -1
    with pytest.raises(SceneInputError):
        attach(state)
    consumer = attach()
    before = consumer.view()
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    assert consumer.view() == before


@pytest.mark.parametrize("damage", [
    "missing_record", "duplicate_sequence", "unknown_kind", "kind_container",
    "bool_sequence", "actor_range", "missing_before_field", "byte_range",
    "future_generation",
])
def test_malformed_complete_event_envelope_is_refused_transactionally(damage):
    consumer = attach()
    before = consumer.view()
    state, events = checkpoint(2)
    if damage == "missing_record":
        events["events"].pop()
    elif damage == "duplicate_sequence":
        events["events"][1]["seq"] = 1
    elif damage == "unknown_kind":
        events["events"][1]["kind"] = "unsupported"
    elif damage == "kind_container":
        events["events"][1]["kind"] = []
    elif damage == "bool_sequence":
        events["events"][1]["seq"] = True
    elif damage == "actor_range":
        events["events"][1]["actor"] = 16
    elif damage == "missing_before_field":
        del events["events"][1]["before"]["x"]
    elif damage == "byte_range":
        events["events"][1]["bytes"][2] = 256
    else:
        events["events"][1]["control_generation"] = 4
    with pytest.raises(SceneInputError):
        consume(consumer, state, events)
    assert consumer.view() == before


def test_inputs_updates_views_and_witnesses_are_detached():
    initial, _ = checkpoint()
    consumer = attach(initial)
    initial["guest"]["actors"][0]["x"] = 200
    assert_actors(consumer.view(), 0)
    state, events = checkpoint(2)
    update = consume(consumer, state, events)
    view = consumer.view()
    expected = deepcopy(view)
    state["guest"]["actors"][1]["x"] = 201
    events["events"][0]["after"]["x"] = 202
    update["changes"][0]["before"]["x"] = 203
    view["actors"][0]["witness"]["bytes"][0] = 0
    view["source"]["sha256"] = "ff" * 32
    view["coverage"]["history_start"]["retired"] = 999
    assert consumer.view() == expected
    assert_actors(consumer.view(), 2)
    assert consumer.view()["actors"][0]["witness"]["bytes"] == [37, 0, 10, 20]
