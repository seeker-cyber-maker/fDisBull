"""Public primitive behavior with an authored synchronous provider boundary."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading

import pytest

from dotbox.rts_actions import ActionRefused, ActionUncertain, RtsController, prepare_action, check_action, request_digest


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture
def world():
    return json.loads((Path(__file__).parents[1] / "examples/rts_world.json").read_text())


def later(world):
    value = deepcopy(world)
    value["state_context"]["revision"] += 1
    revision = value["state_context"]["revision"]
    value["observation_id"] = f"example-{revision}"
    value["state_context"]["context_token"] = f"authored-context-{revision}"
    value["camera"]["frame_id"] += 1
    for collection in ("entities", "groups", "events"):
        for item in value[collection]:
            item["observation_id"] = value["observation_id"]
    return value


class Provider:
    """Test boundary: explicit observations/outcomes, no simulated game mechanics."""

    def __init__(self, world):
        self.world = deepcopy(world)
        self.executed = []
        self.admissions = []
        self.observations = 0
        self.control = "owner-generation-1"
        self.binding = "b" * 64
        self.supported = True
        self.ready = True
        self.after = None
        self.failure = None
        self.milestones = {"action_sent": True, "accepted": None, "complete": False, "effects": "unknown"}

    def observe(self):
        self.observations += 1
        return deepcopy(self.world)

    def admit(self, request):
        self.admissions.append(deepcopy(request))
        if not self.supported:
            return None
        return {"format": "dotbox-rts-admission-1", "request_sha256": digest(request),
                "binding_id": "authored:" + request["primitive"], "binding_sha256": self.binding,
                "control_token": self.control, "enabled": True, "ready": self.ready,
                "evidence_ref": "authored/admission"}

    def execute(self, request, *, expected_admission):
        assert expected_admission["control_token"] == self.control
        assert request["world_sha256"] == digest(self.world)
        self.executed.append(deepcopy(request))
        if self.failure is not None:
            raise self.failure
        result = {"format": "dotbox-rts-receipt-1", "request_sha256": digest(request),
                  **self.milestones, "evidence_ref": "authored/outcome", "observation": deepcopy(self.after)}
        if self.after is not None:
            self.world = deepcopy(self.after)
        return result


def test_actions_compose_independently_without_hidden_continuation(world):
    provider = Provider(world)
    controller = RtsController(provider)
    # Camera change does not select an actor or change its command.
    provider.after = later(world)
    provider.after["camera"]["world_bounds"] = [1, 0, 16, 10]
    plan = controller.prepare(world, "pan_view", {"position": [12, 5]})
    first = controller.execute(plan)
    assert [item["primitive"] for item in provider.executed] == ["pan_view"]
    assert first["receipt"]["observation"]["selection"] == world["selection"]
    current = controller.observe()
    provider.after = later(current)
    provider.after["selection"]["entity_ids"] = ["tank"]
    controller.execute(controller.prepare(current, "select_entity", {"entity_id": "tank"}))
    current = controller.observe()
    provider.after = later(current)
    provider.after["selection"]["pending_action"] = "move"
    controller.execute(controller.prepare(current, "choose_action", {"action_id": "move"}))
    assert [item["primitive"] for item in provider.executed] == ["pan_view", "select_entity", "choose_action"]
    assert all("target" not in item["arguments"] for item in provider.executed)
    current = controller.observe()
    provider.after = later(current)
    provider.after["selection"]["pending_action"] = None
    provider.milestones.update(accepted=True, complete=False, effects="applied-confirmed")
    result = controller.execute(controller.prepare(current, "select_target", {"target": {"position": [12, 8]}}))
    assert result["receipt"]["accepted"] is True
    assert result["receipt"]["complete"] is False
    assert result["receipt"]["observation"]["entities"][1]["position"] == [9, 9]
    assert len(provider.executed) == 4  # No input-free wait or next order was sent implicitly.


def test_context_click_retains_unknown_semantics_and_is_not_move(world):
    provider = Provider(world)
    controller = RtsController(provider)
    result = controller.execute(controller.prepare(world, "context_click", {"target": {"entity_id": "worm"}}))
    assert provider.executed[0]["primitive"] == "context_click"
    assert result["receipt"]["accepted"] is None and result["receipt"]["effects"] == "unknown"
    assert world["selection"]["pending_action"] is None


def test_logical_groups_never_dispatch_or_imply_native_multiselect(world):
    provider = Provider(world)
    controller = RtsController(provider)
    args = {"group_id": "watch", "entity_ids": ["scout", "ally", "worm"], "mode": "logical"}
    plan = controller.prepare(world, "select_group", args)
    args["entity_ids"].clear()
    result = controller.execute(plan)
    assert result["execution"] == "not_performed" and result["scope"] == "planner"
    assert result["logical_selection"]["entity_ids"] == ["scout", "ally", "worm"]
    assert result["native_selection"]["entity_ids"] == ["scout"]
    assert provider.executed == [] and provider.admissions == []
    changed = later(world)
    group = controller.logical_selection(changed)
    assert group["status"] == "stale" and group["unresolved_entity_ids"] == ["worm"]
    assert group["entity_ids"] == ["scout", "ally"]


def test_reused_slot_and_restore_cannot_retarget_logical_members(world):
    provider = Provider(world)
    controller = RtsController(provider)
    controller.execute(controller.prepare(world, "select_group", {"group_id": "patrol", "entity_ids": ["scout"], "mode": "logical"}))
    reused = later(world)
    reused["entities"][0]["incarnation_id"] = "new-unit-in-same-slot"
    assert controller.logical_selection(reused)["status"] == "stale"
    restored = deepcopy(world)
    restored["state_context"]["branch_id"] = "restored"
    assert controller.logical_selection(restored)["status"] == "stale"
    older = deepcopy(world)
    older["state_context"]["revision"] -= 1
    assert controller.logical_selection(older)["status"] == "stale"
    conflicting = deepcopy(world)
    conflicting["entities"][0]["position"] = [7, 9]
    assert controller.logical_selection(conflicting)["status"] == "stale"


@pytest.mark.parametrize("mutation", [
    lambda w: w["camera"].update(frame_id=71),
    lambda w: w["state_context"].update(branch_id="restored"),
    lambda w: w["state_context"].update(session_id="new-session"),
    lambda w: w["state_context"].update(revision=8),
    lambda w: w["entities"][0].update(position=[7, 9]),
    lambda w: w["entities"][0].update(incarnation_id="new-life"),
    lambda w: w["entities"][0].update(controller_faction="red", commandable=False),
    lambda w: w["selection"].update(entity_ids=["tank"]),
    lambda w: w["events"][0].update(blocking=True),
    lambda w: w["phase"].update(name="story"),
])
def test_freshness_refuses_before_dispatch_even_with_same_pixels(world, mutation):
    provider = Provider(world)
    controller = RtsController(provider)
    plan = controller.prepare(world, "select_entity", {"entity_id": "scout"})
    provider.world = later(provider.world)
    mutation(provider.world)
    with pytest.raises((ActionRefused, ActionUncertain)):
        controller.execute(plan)
    assert provider.executed == []
    with pytest.raises((ActionRefused, ActionUncertain)):
        controller.execute(plan)


@pytest.mark.parametrize("field,value", [("control", "owner-generation-2"), ("binding", "c" * 64), ("ready", False), ("supported", False)])
def test_current_route_and_ownership_admission_is_independent_of_world(world, field, value):
    provider = Provider(world)
    controller = RtsController(provider)
    plan = controller.prepare(world, "pan_view", {"position": [10, 5]})
    setattr(provider, field, value)
    with pytest.raises(ActionRefused):
        controller.execute(plan)
    assert provider.executed == []


def test_no_native_group_binding_means_no_fallback_clicks_or_drag(world):
    provider = Provider(world)
    provider.supported = False
    controller = RtsController(provider)
    with pytest.raises(ActionRefused, match="no qualified binding"):
        controller.prepare(world, "select_group", {"group_id": "patrol", "entity_ids": ["scout", "tank"], "mode": "native"})
    assert provider.executed == []


@pytest.mark.parametrize("identity", ["worm", "ally"])
def test_npc_and_alliance_do_not_grant_player_commands(world, identity):
    world["selection"]["entity_ids"] = [identity]
    with pytest.raises(ActionRefused, match="commandability"):
        prepare_action(world, "choose_action", {"action_id": "move"})
    assert prepare_action(world, "select_entity", {"entity_id": identity})["execution"] == "not_performed"


def test_hidden_entity_and_unknown_readiness_cannot_be_targeted(world):
    world["entities"][2].update(visibility="hidden", audience="internal")
    with pytest.raises(ActionRefused, match="visible"):
        prepare_action(world, "context_click", {"target": {"entity_id": "worm"}})
    world["phase"]["input_ready"] = None
    with pytest.raises(ActionRefused, match="readiness"):
        prepare_action(world, "pan_view", {"position": [10, 5]})


def test_scripted_interruption_requires_explicit_response(world):
    world["phase"]["name"] = "story"
    world["events"][0].update(kind="story", blocking=True, text="An ally asks for help.")
    with pytest.raises(ActionRefused):
        prepare_action(world, "choose_action", {"action_id": "move"})
    provider = Provider(world)
    controller = RtsController(provider)
    controller.execute(controller.prepare(world, "respond_to_event", {"event_id": "objective", "response_id": "continue"}))
    assert [item["primitive"] for item in provider.executed] == ["respond_to_event"]


def test_drag_is_one_bounded_primitive_not_exposed_down_move_up_sequence(world):
    args = {"surface": "minimap", "start": [294, 160], "end": [280, 168], "button": "left",
            "max_guest_ms": 800, "max_frames": 80, "timeout_ms": 15000}
    provider = Provider(world)
    controller = RtsController(provider)
    controller.execute(controller.prepare(world, "drag_pointer", args))
    assert len(provider.executed) == 1 and provider.executed[0]["arguments"] == args
    args["max_frames"] = True
    with pytest.raises(ValueError):
        prepare_action(world, "drag_pointer", args)


def test_applied_then_lost_response_consumes_token_and_latches_uncertainty(world):
    provider = Provider(world)
    provider.failure = TimeoutError("Reply lost after provider accepted input")
    controller = RtsController(provider)
    plan = controller.prepare(world, "select_entity", {"entity_id": "tank"})
    with pytest.raises(ActionUncertain):
        controller.execute(plan)
    assert len(provider.executed) == 1 and controller.uncertain
    counts = (len(provider.admissions), provider.observations)
    for operation in (lambda: controller.execute(plan), lambda: controller.prepare(world, "pan_view", {"position": [10, 5]}), controller.observe):
        with pytest.raises(ActionUncertain):
            operation()
    assert (len(provider.admissions), provider.observations) == counts
    assert len(provider.executed) == 1  # No retry or cleanup input.


def test_known_acceptance_survives_invalid_after_observation(world):
    provider = Provider(world)
    provider.milestones.update(accepted=True, effects="applied-confirmed")
    provider.after = {"invalid": True}
    controller = RtsController(provider)
    with pytest.raises(ActionUncertain) as error:
        controller.execute(controller.prepare(world, "choose_action", {"action_id": "move"}))
    assert error.value.receipt["accepted"] is True
    assert controller.last_receipt["action_sent"] is True


def test_mutation_replay_foreign_and_serialized_requests_never_dispatch(world):
    provider = Provider(world)
    controller = RtsController(provider)
    offline = prepare_action(world, "pan_view", {"position": [10, 5]})
    assert check_action(offline, world) == offline
    with pytest.raises(ActionRefused):
        controller.execute(offline)
    foreign = RtsController(provider).prepare(world, "pan_view", {"position": [10, 5]})
    with pytest.raises(ActionRefused):
        controller.execute(foreign)
    plan = controller.prepare(world, "pan_view", {"position": [10, 5]})
    plan["request"]["arguments"]["position"] = [11, 5]
    with pytest.raises(ActionRefused, match="modified"):
        controller.execute(plan)
    assert provider.executed == []


def test_controller_refuses_other_threads_before_any_provider_call(world):
    provider = Provider(world)
    controller = RtsController(provider)
    errors = []
    def attempt():
        try:
            controller.prepare(world, "pan_view", {"position": [10, 5]})
        except ActionRefused as error:
            errors.append(str(error))
    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join()
    assert errors and provider.admissions == [] and provider.executed == []


def test_provider_cannot_reenter_controller_while_an_action_is_in_flight(world):
    provider = Provider(world)
    controller = RtsController(provider)
    original = provider.execute
    errors = []
    def reentrant(request, *, expected_admission):
        try:
            controller.prepare(world, "choose_action", {"action_id": "move"})
        except ActionRefused as error:
            errors.append(str(error))
        return original(request, expected_admission=expected_admission)
    provider.execute = reentrant
    controller.execute(controller.prepare(world, "select_entity", {"entity_id": "tank"}))
    assert errors and "reenter" in errors[0] and len(provider.executed) == 1
    assert len(provider.admissions) == 2


def test_provider_digest_is_stable_for_non_ascii_arguments(world):
    request = prepare_action(world, "choose_action", {"action_id": "déplacer"})
    assert request_digest(request) == digest(request)


@pytest.mark.parametrize("change", [
    lambda w: w["entities"][0].update(position=[7, 9]),
    lambda w: w["state_context"].update(revision=6),
])
def test_incoherent_provider_observation_head_latches_before_input(world, change):
    provider = Provider(world)
    controller = RtsController(provider)
    controller.observe()
    change(provider.world)
    with pytest.raises(ActionUncertain):
        controller.observe()
    assert controller.uncertain and provider.executed == []
    before = len(provider.admissions)
    with pytest.raises(ActionUncertain):
        controller.prepare(provider.world, "pan_view", {"position": [10, 5]})
    assert len(provider.admissions) == before


def test_deeply_malformed_after_receipt_preserves_acceptance_and_blocks_followup(world):
    provider = Provider(world)
    provider.milestones.update(accepted=True, effects="applied-confirmed")
    controller = RtsController(provider)
    nested = []
    for _ in range(700):
        nested = [nested]
    # Return the malformed object directly: copying it inside the test provider
    # would test an execution exception rather than receipt validation.
    def returned(request, *, expected_admission):
        provider.executed.append(deepcopy(request))
        return {"format": "dotbox-rts-receipt-1", "request_sha256": digest(request),
                **provider.milestones, "evidence_ref": "authored/deep-after", "observation": {"invalid": nested}}
    provider.execute = returned
    with pytest.raises(ActionUncertain) as error:
        controller.execute(controller.prepare(world, "choose_action", {"action_id": "move"}))
    assert error.value.receipt["accepted"] is True and controller.uncertain
    before = len(provider.admissions)
    with pytest.raises(ActionUncertain):
        controller.prepare(world, "choose_action", {"action_id": "move"})
    assert len(provider.admissions) == before and len(provider.executed) == 1


def test_complete_request_byte_bound_is_enforced_before_provider_admission(world):
    world["observation_id"] = "界" * 2048
    world["state_context"]["context_token"] = "界" * 2048
    for collection in ("entities", "groups", "events"):
        for item in world[collection]:
            item["observation_id"] = world["observation_id"]
    provider = Provider(world)
    controller = RtsController(provider)
    with pytest.raises(ValueError, match="request exceeds"):
        controller.prepare(world, "pan_view", {"position": [10, 5]})
    assert provider.admissions == [] and provider.executed == []


def test_group_readout_cannot_resurrect_member_superseded_in_known_head(world):
    provider = Provider(world)
    controller = RtsController(provider)
    controller.execute(controller.prepare(world, "select_group", {"group_id": "patrol", "entity_ids": ["scout"], "mode": "logical"}))
    stale = later(world)
    provider.world = later(stale)
    provider.world["entities"][0]["incarnation_id"] = "scout-life-2"
    controller.observe()
    reported = controller.logical_selection(stale)
    assert reported["status"] == "stale" and reported["entity_ids"] == []
    assert reported["unresolved_entity_ids"] == ["scout"]
