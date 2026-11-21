"""Authored map-route contracts; no game bytes or live-runtime qualification."""
import importlib.util
from copy import deepcopy
from pathlib import Path
import struct
import sys

import pytest

from dune_map_fixtures import (
    BASE, MAP_CALLBACK, MAP_DISPATCH, ORIGIN, SITE_ACCEPT, TARGET, TARGET_XY,
    VECTOR, VECTOR_WORDS, execution_calls, input_calls, make_controller, progress, put_word,
)
from test_dune_ui_reader import put_label


def load_map_module():
    path = Path(__file__).resolve().parents[1] / "scripts/experiments/dune_map.py"
    assert path.is_file(), "The edition-bound map selector API has not been implemented"
    sys.modules["dune_progress"] = progress
    spec = importlib.util.spec_from_file_location("dune_map", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_map_selector_public_api_is_available():
    module = load_map_module()
    assert callable(module.MapSelector)
    assert callable(module.MapSelector.prepare)
    assert callable(module.MapSelector.select)


@pytest.fixture
def make_case(tmp_path, monkeypatch):
    module = load_map_module()
    count = 0

    def make(**kwargs):
        nonlocal count
        folder = tmp_path / str(count)
        folder.mkdir()
        count += 1
        peer, controller, observation = make_controller(folder, monkeypatch, **kwargs)
        return peer, controller, observation, module.MapSelector(controller)

    return make


@pytest.fixture
def case(make_case):
    return make_case()


def prepared(case):
    peer, controller, observation, selector = case
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "prepared", result.get("error")
    assert isinstance(result["selection_token"], str) and result["selection_token"]
    assert result["input_attempted"] is False and result["input_sent"] is False
    assert not input_calls(peer) and not execution_calls(peer)
    assert not peer.entries
    return result["selection_token"]


def assert_no_automatic_resume(peer, controller):
    before = len(peer.calls)
    for reconcile in (False, True):
        with pytest.raises(progress.ProgressError):
            controller.await_ready(max_frames=5, reconcile_partial=reconcile)
        assert len(peer.calls) == before


def change_binding(peer, change):
    ram = peer.ram
    if change == "vector_pointer":
        put_word(ram, 0x2A5C, VECTOR - 14)
    elif change == "callback":
        put_word(ram, VECTOR + 2, MAP_CALLBACK + 1)
    elif change == "other_vector_word":
        put_word(ram, VECTOR + 4, 0x1234)
    elif change == "gate":
        ram[BASE + 0x11D6] = 5
    elif change == "viewport":
        put_word(ram, 0x423F, 82)
    elif change == "mode":
        ram[BASE + 0x4247] = 2
    elif change == "current_site":
        put_word(ram, 0x114E, TARGET)
    elif change == "pending_action":
        put_word(ram, 0x4235, 1)
    elif change == "menu":
        put_word(ram, 0x2824, 0x2598)
    elif change == "moved_point":
        put_word(ram, 0xA10F, TARGET_XY[0] + 1)
    elif change == "missing_point":
        put_word(ram, 0xA10D, 0)
    elif change == "ineligible_point":
        ram[BASE + TARGET + 8] = 0xFF
    elif change == "duplicate_target":
        struct.pack_into("<3H", ram, BASE + 0xA113, TARGET, 130, 0x0150)
    elif change == "tied_point":
        struct.pack_into("<3H", ram, BASE + 0xA107, ORIGIN, TARGET_XY[0], 0x0100 | TARGET_XY[1])
    elif change == "rectangle_overlap":
        struct.pack_into("<4H", ram, BASE + 0x2186, 119, 79, 121, 80)
    elif change == "parsed_label":
        put_label(ram, 2, b"Authored changed destination", offset=0x0440)
    else:
        raise AssertionError(change)


BINDING_CHANGES = (
    "vector_pointer", "callback", "other_vector_word", "gate", "viewport",
    "mode", "current_site", "pending_action", "menu", "moved_point",
    "missing_point", "ineligible_point", "duplicate_target", "tied_point",
    "rectangle_overlap", "parsed_label",
)


@pytest.mark.parametrize("read_strategy", ["full", "sparse"])
def test_one_map_click_proves_destination_then_independent_readiness_without_arrival(make_case, read_strategy):
    peer, controller, observation, selector = case = make_case(read_strategy=read_strategy)
    token = prepared(case)
    result = selector.select(token)

    assert result["outcome"] in ("input_boundary", "context_changed"), result.get("error")
    assert result["destination_accepted"] is True and result["input_ready"] is True
    assert result["arrival"] == "unknown" and result["story_commit"] == "unknown"
    assert result["acceptance"]["target_record"] == TARGET
    assert result["acceptance"]["selected_record"] == TARGET
    assert result["acceptance"]["register_record"] == TARGET
    assert result["readiness"]["matched_map_dispatch"] is True
    assert result["readiness"]["input_loop_observed"] is True
    assert result["readiness"]["input_retired"] is True
    assert result["readiness"]["stable_control_frames"] >= 2
    assert result["readiness"]["fresh_frame_since_dispatch"] is True
    assert result["readiness"]["fresh_frame_after_input_loop"] is True
    assert result["after"]["scene"]["site_witness"]["current_record_114e"] == ORIGIN
    assert result["after"]["scene"]["site_witness"]["selected_record_4258"] == TARGET
    assert peer.probes_seen == [MAP_DISPATCH, SITE_ACCEPT, progress.INPUT_LOOP, progress.INPUT_LOOP]
    assert len(input_calls(peer)) == 1 and not peer.entries and not controller.blocked
    assert input_calls(peer)[0]["x"] == TARGET_XY[0] and input_calls(peer)[0]["y"] == TARGET_XY[1]
    assert controller.ready_token == result["after"]["scene_token"] != observation["scene_token"]
    assert Path(result["report_path"]).is_file()


def test_constructor_requires_explicit_native_wait_without_any_rpc(tmp_path, monkeypatch):
    peer, controller, _ = make_controller(tmp_path, monkeypatch, wait_strategy="frame")
    with pytest.raises(progress.ProgressError, match="native|bounded"):
        load_map_module().MapSelector(controller)
    assert not peer.calls


@pytest.mark.parametrize("change", ["token", "revision", "descriptive_only", "stop"])
def test_preparation_requires_current_ready_token(case, change):
    peer, controller, observation, selector = case
    token = observation["scene_token"]
    if change == "token":
        token = "obsolete-scene-token"
    elif change == "revision":
        peer.revision += 1
    elif change == "descriptive_only":
        token = controller.observe()["scene_token"]
    else:
        peer.stop = {"kind": "budget"}
    peer.calls.clear()
    result = selector.prepare(token, site_record=TARGET)
    assert result["outcome"] == "declined"
    assert not result.get("selection_token")
    assert not input_calls(peer) and not execution_calls(peer) and not peer.entries


@pytest.mark.parametrize("site_record", [ORIGIN, 0, 0xFFF1, 0x0101, True])
def test_preparation_refuses_current_missing_or_nonrecord_target(case, site_record):
    peer, _, observation, selector = case
    result = selector.prepare(observation["scene_token"], site_record=site_record)
    assert result["outcome"] == "declined"
    assert not input_calls(peer) and not execution_calls(peer) and not peer.entries


@pytest.mark.parametrize("change", BINDING_CHANGES)
def test_changed_prepared_binding_declines_before_input_and_consumes_token(case, change):
    peer, controller, _, selector = case
    token = prepared(case)
    change_binding(peer, change)
    result = selector.select(token)
    assert result["outcome"] == "declined", result.get("error")
    assert result["destination_accepted"] is False and result["input_attempted"] is False
    assert not input_calls(peer) and not execution_calls(peer) and not peer.entries
    before = len(peer.calls)
    replay = selector.select(token)
    assert replay["outcome"] == "declined" and len(peer.calls) == before


@pytest.mark.parametrize("change", ["revision", "observe", "new_preparation", "unknown_token"])
def test_stale_map_tokens_never_replay_a_click(case, change):
    peer, controller, observation, selector = case
    token = prepared(case)
    if change == "revision":
        peer.revision += 1
    elif change == "observe":
        controller.observe()
    elif change == "new_preparation":
        newer = selector.prepare(observation["scene_token"], site_record=TARGET)
        assert newer["outcome"] == "prepared" and newer["selection_token"] != token
    else:
        token = "not-a-selection-token"
    before = len(peer.calls)
    result = selector.select(token)
    assert result["outcome"] == "declined"
    assert not input_calls(peer) and not execution_calls(peer)
    if change in ("new_preparation", "unknown_token"):
        assert len(peer.calls) == before


def test_successful_selection_token_is_one_use_even_after_new_ready_boundary(case):
    peer, _, _, selector = case
    token = prepared(case)
    result = selector.select(token)
    assert result["input_ready"] is True
    before = len(peer.calls)
    replay = selector.select(token)
    assert replay["outcome"] == "declined" and len(peer.calls) == before
    assert len(input_calls(peer)) == 1


@pytest.mark.parametrize("change", ("si", "dx", "bx", *BINDING_CHANGES))
def test_dispatch_revalidates_registers_and_binding_before_executing_callback(case, change):
    peer, controller, _, selector = case
    token = prepared(case)
    if change == "si":
        peer.dispatch_si = VECTOR + 2
    elif change == "dx":
        peer.dispatch_xy = (TARGET_XY[0] + 1, TARGET_XY[1])
    elif change == "bx":
        peer.dispatch_xy = (TARGET_XY[0], TARGET_XY[1] + 1)
    else:
        peer.on_boundary = lambda p, offset: change_binding(p, change) if offset == MAP_DISPATCH else None
    result = selector.select(token)
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert result["destination_accepted"] is False and result["input_ready"] is False
    assert peer.ip == MAP_DISPATCH and not peer.acceptance_observed
    assert len(input_calls(peer)) == 1 and not result["continuation_allowed"]
    assert not any(method == "frame.step" for method, _ in peer.calls[peer.event_call_indices[MAP_DISPATCH] + 1:])
    assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("wrong", ["di", "selected_record"])
def test_acceptance_requires_both_returned_di_and_selected_record(case, wrong):
    peer, controller, _, selector = case
    token = prepared(case)
    if wrong == "di":
        peer.accept_di = ORIGIN
    else:
        peer.accept_selected = ORIGIN
    result = selector.select(token)
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert result["destination_accepted"] is False and result["input_ready"] is False
    assert peer.ip == SITE_ACCEPT and len(input_calls(peer)) == 1
    assert_no_automatic_resume(peer, controller)


def test_normal_hover_selection_and_cursor_changes_are_not_route_rebinding(case):
    peer, _, _, selector = case
    token = prepared(case)

    def hover(p, offset):
        if offset == MAP_DISPATCH:
            for address, value in ((0x4258, TARGET), (0x2A6E, 7), (0x4237, 0x1234)):
                put_word(p.ram, address, value)

    peer.on_boundary = hover
    result = selector.select(token)
    assert result["input_ready"] and result["destination_accepted"], result.get("error")
    assert len(input_calls(peer)) == 1


def test_unused_prefetched_byte_does_not_replace_parsed_binding_identity(case):
    peer, _, observation, selector = case
    token = prepared(case)
    address = BASE + 0x4000
    capture = observation["memory_capture"]
    assert any(r["address"] <= address < r["address"] + r["length"] for r in capture["reads"]["ranges"])
    assert not any(r["address"] <= address < r["address"] + r["length"] for r in capture["dependencies"])
    peer.ram[address] ^= 0x42
    result = selector.select(token)
    assert result["input_ready"] and result["destination_accepted"], result.get("error")
    assert len(input_calls(peer)) == 1


@pytest.mark.parametrize("boundary", [MAP_DISPATCH, SITE_ACCEPT, progress.INPUT_LOOP])
def test_foreign_breakpoint_at_expected_pc_is_preserved_and_never_resumed(case, boundary):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.foreign_at = boundary
    result = selector.select(token)
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert not result["input_ready"] and not result["continuation_allowed"]
    assert result["destination_accepted"] is (boundary == progress.INPUT_LOOP)
    assert set(peer.entries) == {"foreign"} and len(input_calls(peer)) == 1
    assert_no_automatic_resume(peer, controller)


def test_rectangle_dispatch_cannot_be_mistaken_for_map_callback(case):
    peer, controller, _, selector = case
    token = prepared(case)

    def intercept(p, method, params, result):
        if method == "input.mouse.click":
            p.events[0]["offset"] = progress.DISPATCH

    peer.after_call = intercept
    result = selector.select(token)
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert peer.ip == progress.DISPATCH and not result["destination_accepted"]
    assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("boundary", [MAP_DISPATCH, SITE_ACCEPT])
def test_known_timeout_before_destination_acceptance_cannot_generic_resume(case, boundary):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.block_at = boundary
    result = selector.select(token, max_guest_ms=20)
    assert result["outcome"] == "timeout", result.get("error")
    assert not result["destination_accepted"] and not result["input_ready"]
    assert not result["continuation_allowed"] and controller.blocked
    assert len(input_calls(peer)) == 1 and not peer.entries
    assert_no_automatic_resume(peer, controller)


def test_known_timeout_after_acceptance_allows_only_input_free_reconciliation(case):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.block_at = progress.INPUT_LOOP
    result = selector.select(token, max_guest_ms=20)
    assert result["outcome"] == "timeout", result.get("error")
    assert result["destination_accepted"] and not result["input_ready"]
    assert result["arrival"] == "unknown" and result["continuation_allowed"] and controller.blocked
    assert peer.stop["kind"] == "budget" and not peer.entries
    peer.block_at = None
    reconciled = controller.await_ready(max_frames=6, reconcile_partial=True)
    assert reconciled["outcome"] == "input_boundary", reconciled.get("error")
    assert reconciled["partial_reconciled"] and not controller.blocked
    assert len(input_calls(peer)) == 1
    before = len(peer.calls)
    assert selector.select(token)["outcome"] == "declined"
    assert len(peer.calls) == before


@pytest.mark.parametrize("fault", ["click", MAP_DISPATCH, SITE_ACCEPT, progress.INPUT_LOOP])
def test_uncertain_input_or_execution_forbids_every_subsequent_native_rpc(case, fault):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.uncertain_at = fault
    result = selector.select(token)
    assert result["outcome"] == "uncertain_dispatch", result.get("error")
    assert not result["continuation_allowed"] and not result["input_ready"]
    assert result["destination_accepted"] is (fault == progress.INPUT_LOOP)
    assert len(input_calls(peer)) == 1
    assert peer.calls[-1][0] == ("input.mouse.click" if fault == "click" else "frame.step")
    assert result["cleanup"]["status"] == "preserved_without_native_calls"
    before = len(peer.calls)
    assert selector.select(token)["outcome"] == "declined"
    assert len(peer.calls) == before
    assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("kind,limit,accepted", [("frames", 3, False), ("guest", 20, False),
                                                ("guest", 35, True), ("stops", 1, False),
                                                ("stops", 2, True), ("stops", 3, True)])
def test_all_phases_share_one_aggregate_execution_budget(case, kind, limit, accepted):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.event_delays = {MAP_DISPATCH: 1, SITE_ACCEPT: 1, progress.INPUT_LOOP: 1}
    if kind == "frames":
        peer.event_delays[SITE_ACCEPT] = 3
    bounds = {"max_frames": 20, "max_guest_ms": 500, "max_stops": 12}
    bounds[{"frames": "max_frames", "guest": "max_guest_ms", "stops": "max_stops"}[kind]] = limit
    result = selector.select(token, **bounds)
    assert result["outcome"] == "timeout", result.get("error")
    assert result["destination_accepted"] is accepted and not result["input_ready"]
    frames, ticks = 0, 0
    for reply in peer.execution_receipts:
        budget = reply["bounded"]
        assert budget["max_frames"] <= bounds["max_frames"] - frames
        assert budget["max_guest_ms"] <= bounds["max_guest_ms"] - ticks
        frames += budget["frames_completed"]
        ticks += budget["guest_elapsed_ms"]
    assert result["frames_completed"] == frames <= bounds["max_frames"]
    assert result["bounded_guest_elapsed_ms"] == ticks <= bounds["max_guest_ms"]
    assert len(peer.probes_seen) <= bounds["max_stops"]
    assert len(input_calls(peer)) == 1
    if not accepted:
        assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("change", ["vector_pointer", "callback", "gate", "mode", "pending_action",
                                    "menu", "missing_point", "ineligible_point", "duplicate_target",
                                    "tied_point", "rectangle_overlap"])
def test_preparation_rejects_inapplicable_route_even_with_fresh_input_boundary(make_case, change):
    peer, _, observation, selector = make_case(mutate_before_ready=lambda p: change_binding(p, change))
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "declined", result.get("error")
    assert not input_calls(peer) and not execution_calls(peer) and not peer.entries


@pytest.mark.parametrize("slot", [0, 2, 3, 4, 5, 6])
def test_initial_unknown_vector_slots_decline_before_click_or_execution(make_case, slot):
    def unknown_slot(peer):
        put_word(peer.ram, VECTOR + 2 * slot, VECTOR_WORDS[slot] ^ 1)

    peer, _, observation, selector = make_case(mutate_before_ready=unknown_slot)
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "declined", result.get("error")
    assert not result.get("selection_token")
    assert not input_calls(peer) and not execution_calls(peer) and not peer.entries


@pytest.mark.parametrize("xy,allowed", [((81, 80), True), ((120, 45), True),
                                        ((241, 80), False), ((120, 134), False)])
def test_viewport_lower_edges_are_included_and_upper_edges_excluded(make_case, xy, allowed):
    def move_target(peer):
        struct.pack_into("<3H", peer.ram, BASE + 0xA10D, TARGET, xy[0], 0x0100 | xy[1])

    peer, _, observation, selector = make_case(mutate_before_ready=move_target)
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert (result["outcome"] == "prepared") is allowed, result.get("error")
    assert not input_calls(peer) and not execution_calls(peer)


@pytest.mark.parametrize("rectangle,overlaps", [((120, 79, 121, 81), False),
                                                ((119, 80, 121, 81), False),
                                                ((119, 79, 120, 81), False),
                                                ((119, 79, 121, 80), True)])
def test_rectangle_overlap_uses_original_asymmetric_edges(make_case, rectangle, overlaps):
    def rectangle_at_point(peer):
        struct.pack_into("<4H", peer.ram, BASE + 0x2186, *rectangle)

    peer, _, observation, selector = make_case(mutate_before_ready=rectangle_at_point)
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert (result["outcome"] == "declined") is overlaps, result.get("error")
    assert not input_calls(peer) and not execution_calls(peer)


def test_wrong_mode_point_pointer_is_bounded_before_its_type_is_dereferenced(make_case):
    def hidden_bad_pointer(peer):
        struct.pack_into("<3H", peer.ram, BASE + 0xA113, 0xFFFC, 130, 0x0250)

    peer, _, observation, selector = make_case(mutate_before_ready=hidden_bad_pointer)
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "declined", result.get("error")
    assert not input_calls(peer) and not execution_calls(peer)


def test_hidden_wrong_mode_type_is_bound_even_when_reader_does_not_render_it(make_case):
    hidden_record = 0x0138

    def hidden_point(peer):
        struct.pack_into("<3H", peer.ram, BASE + 0xA113, hidden_record, 130, 0x0250)
        peer.ram[BASE + hidden_record:BASE + hidden_record + 2] = bytes((1, 2))

    case = make_case(mutate_before_ready=hidden_point)
    peer, _, observation, selector = case
    assert all(p["site_record"] != hidden_record for p in observation["scene"]["site_witness"]["rendered_map_points"])
    token = prepared(case)
    peer.ram[BASE + hidden_record + 8] = 0xFF
    result = selector.select(token)
    assert result["outcome"] == "declined", result.get("error")
    assert not input_calls(peer) and not execution_calls(peer)


def test_token_from_another_selector_has_no_native_effect(case):
    peer, controller, _, selector = case
    token = prepared(case)
    other = load_map_module().MapSelector(controller)
    before = len(peer.calls)
    result = other.select(token)
    assert result["outcome"] == "declined" and len(peer.calls) == before
    assert not input_calls(peer)


def test_existing_unowned_probe_is_not_deleted_or_admitted_before_click(case):
    peer, controller, _, selector = case
    token = prepared(case)
    peer.entries["foreign"] = {"breakpoint_id": "foreign", "kind": "execution", "once": False,
                               "address": {"space": "segmented", "segment": "0x0824", "offset": "0xD2FE"}}
    result = selector.select(token)
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert set(peer.entries) == {"foreign"}
    assert not input_calls(peer) and not execution_calls(peer)
    assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("field,value", [("max_frames", 0), ("max_frames", 601),
                                        ("max_stops", 0), ("max_stops", 33),
                                        ("max_guest_ms", 0), ("max_guest_ms", 30001),
                                        ("hold_ms", 0), ("stable_frames", 1),
                                        ("host_budget_ms", 0)])
def test_invalid_bounds_have_no_input_or_execution_effect(case, field, value):
    peer, _, _, selector = case
    token = prepared(case)
    before = len(peer.calls)
    with pytest.raises(ValueError):
        selector.select(token, **{field: value})
    assert len(peer.calls) == before and not input_calls(peer) and not execution_calls(peer)


def test_host_admission_expiration_after_dispatch_preserves_unaccepted_route(case, monkeypatch):
    peer, controller, _, selector = case
    token = prepared(case)
    clock = [10.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock[0])

    def elapsed_at_dispatch(p, offset):
        if offset == MAP_DISPATCH:
            clock[0] += 0.020

    peer.on_boundary = elapsed_at_dispatch
    result = selector.select(token, host_budget_ms=10)
    assert result["outcome"] == "timeout", result.get("error")
    assert not result["destination_accepted"] and not result["continuation_allowed"]
    assert len(input_calls(peer)) == 1
    assert_no_automatic_resume(peer, controller)


def test_uncertain_preparation_reads_issue_no_token_or_followup_rpc(case):
    peer, controller, observation, selector = case
    original = controller.call_adapter

    def lost_read(method, params, timeout_ms):
        if method == "memory.read":
            peer.calls.append((method, params))
            raise TimeoutError("Authored preparation read lost its response")
        return original(method, params, timeout_ms)

    controller.call_adapter = lost_read
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "uncertain_dispatch"
    assert not result.get("selection_token") and peer.calls[-1][0] == "memory.read"
    assert not input_calls(peer) and not execution_calls(peer)
    assert_no_automatic_resume(peer, controller)


def test_declining_during_another_operation_preserves_its_owned_observer_without_rpc(case):
    peer, controller, _, selector = case
    token = prepared(case)
    controller._arm(0x1234)  # A distinct operation now owns this observer.
    entries, owned = deepcopy(peer.entries), deepcopy(controller.owned)
    before = len(peer.calls)
    result = selector.select(token)
    assert result["outcome"] == "declined"
    assert len(peer.calls) == before and peer.entries == entries and controller.owned == owned
    assert not input_calls(peer) and not execution_calls(peer)


@pytest.mark.parametrize("change", ["extra_revision", "missing_revision", "stale_receipt_revision", "changed_stop"])
def test_click_acknowledgement_must_match_its_expected_revision_and_stopped_context(case, change):
    peer, controller, _, selector = case
    token = prepared(case)

    def change_after_click(p, method, params, reply):
        if method == "input.mouse.click":
            if change == "extra_revision":
                p.revision += 1
            elif change == "missing_revision":
                del reply["state_revision"]
            elif change == "stale_receipt_revision":
                reply["state_revision"] -= 1
            else:
                p.stop = {"kind": "pause"}

    peer.after_call = change_after_click
    result = selector.select(token)
    assert not result["destination_accepted"] and not result["input_ready"]
    assert not result["continuation_allowed"] and len(input_calls(peer)) == 1
    assert not execution_calls(peer)
    assert_no_automatic_resume(peer, controller)


def test_mutating_returned_preparation_cannot_change_the_private_selected_target(case):
    peer, _, observation, selector = case
    result = selector.prepare(observation["scene_token"], site_record=TARGET)
    assert result["outcome"] == "prepared"
    token = result["selection_token"]
    result["target"]["screen_xy"][:] = [1, 1]
    result["target"]["site_record"] = ORIGIN
    selected = selector.select(token)
    assert selected["destination_accepted"] and selected["input_ready"], selected.get("error")
    assert (input_calls(peer)[0]["x"], input_calls(peer)[0]["y"]) == TARGET_XY
    assert selected["acceptance"]["target_record"] == TARGET


@pytest.mark.parametrize("phase", ["admission", "dispatch"])
def test_changed_hit_test_body_is_detected_beyond_five_byte_hook(phase, case):
    peer, controller, _, selector = case
    token = prepared(case)

    def changed_body(p, offset=MAP_DISPATCH):
        if offset == MAP_DISPATCH:
            p.ram[progress.CS * 16 + 0x6C30] ^= 1

    if phase == "admission":
        changed_body(peer)
    else:
        peer.on_boundary = changed_body
    result = selector.select(token)
    assert not result["destination_accepted"] and not result["input_ready"]
    if phase == "admission":
        assert not input_calls(peer) and not execution_calls(peer)
    else:
        assert len(input_calls(peer)) == 1 and len(execution_calls(peer)) == 1
        assert_no_automatic_resume(peer, controller)


@pytest.mark.parametrize("expiry", ["after_status", "after_create"])
def test_accepted_target_timeout_after_readiness_arm_retains_exact_stop_for_reconciliation(case, monkeypatch, expiry):
    peer, controller, _, selector = case
    token = prepared(case)
    clock = [10.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock[0])

    def expire_after_arm(p, method, params, reply):
        after_status = expiry == "after_status" and method == "session.status"
        after_create = (expiry == "after_create" and method == "breakpoints.create"
                        and int(params["address"]["offset"], 16) == progress.INPUT_LOOP)
        if ((after_status or after_create) and p.ip == SITE_ACCEPT
                and any(int(entry["address"]["offset"], 16) == progress.INPUT_LOOP
                        for entry in p.entries.values())):
            clock[0] += 0.020
            p.after_call = None

    peer.after_call = expire_after_arm
    result = selector.select(token, host_budget_ms=10)
    assert result["outcome"] == "timeout", result.get("error")
    assert result["destination_accepted"] and not result["input_ready"]
    assert controller.blocked and not peer.entries
    if expiry == "after_status":
        assert result["continuation_allowed"]  # The exact transition was verified.
    if result["continuation_allowed"]:
        reconciled = controller.await_ready(max_frames=6, reconcile_partial=True)
        assert reconciled["outcome"] == "input_boundary", reconciled.get("error")
        assert reconciled["partial_reconciled"] and not controller.blocked
    else:
        # If the creation acknowledgement cannot be fenced, preserving the
        # stop is valid; promising recovery that the controller rejects is not.
        assert_no_automatic_resume(peer, controller)
    assert len(input_calls(peer)) == 1
