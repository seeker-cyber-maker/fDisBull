"""Authored protocol peers; these tests do not qualify a game or native runtime."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import struct

import pytest


SPEC = importlib.util.spec_from_file_location(
    "dune_progress", Path(__file__).resolve().parents[1] / "scripts/experiments/dune_progress.py")
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


def registers(ip=0xD532, record=0x21E8):
    return {"cpu_mode": "real", "code_bits": 16, "stack_bits": 16,
            "address_context": {"paging_enabled": False},
            "segments": {"cs": hex(progress.CS), "ds": hex(progress.DS)},
            "instruction_pointer": hex(ip), "general": {"edi": hex(record)}}


def reader(ram, ds):
    base = ds * 16
    selector = ram[base + 0x4315]
    handler = struct.unpack_from("<H", ram, base + 0x260C)[0]
    metadata = struct.unpack_from("<H", ram, base + 0x260A)[0]
    values = struct.unpack_from("<4H2B2H", ram, base + 0x2186 + 7 * 14)
    control = {"record_offset": 0x21E8, "bounds": list(values[:4]), "flags": list(values[4:6]),
               "value": values[6], "callback": values[7], "active": bool(values[4] & 0x80)}
    row = {"row": 0, "record_offset": 0x21E8, "handler": handler, "metadata": metadata,
           "active_rectangle": control["active"], "disabled_by_metadata": bool(metadata & 0x4000),
           "bounds": control["bounds"], "callback": control["callback"],
           "label": {"ascii": "CONTINUE", "ascii_only": True}}
    return {"menu_admission_sha256": f"{selector}:{handler}", "location_key": {"word_0004": 1},
            "subject_selector_431b": 0, "menu": {"menu_offset": 0x2608, "rows": [row]},
            "controls": [control], "conversation_witness": {"dialogue_selector_4315": selector},
            "text_buffer_candidate": {"freshness": "candidate only"}}


class Peer:
    def __init__(self, source, *, scenario="success"):
        self.ram = bytearray(progress.RAM_BYTES)
        self.ram[progress.CS * 16:progress.CS * 16 + len(source) - progress.HEADER] = source[progress.HEADER:]
        base = progress.DS * 16
        for offset, value in ((0x2184, 8), (0x2840, 0x2824), (0x2824, 0x2608),
                              (0x2608, 0x00FF), (0x260A, 1), (0x260C, 0x1000)):
            struct.pack_into("<H", self.ram, base + offset, value)
        self.ram[base + 0xFED8] = 1
        self.ram[base + 0xFED5] = 255
        struct.pack_into("<4H2B2H", self.ram, base + 0x21E8, 92, 159, 228, 167, 128, 0, 27, 0xCE85)
        self.scenario = scenario
        self.calls = []
        self.entries = {}
        self.next_id = 1
        self.revision = 1
        self.stop = {"kind": "frame"}
        self.frame_id = 10
        self.ticks = 1000
        self.click = False
        self.frames = 0
        self.probes_seen = []
        self.ip = 0xD532
        self.callback_pending = False

    def __call__(self, method, params, timeout_ms):
        self.calls.append((method, deepcopy(params)))
        common = {"session_id": "test-session", "state_revision": self.revision}
        if method == "session.status":
            return {**common, "state": "stopped", "last_stop": self.stop}
        if method == "state.get_registers":
            return {**common, **registers(self.ip)}
        if method == "memory.read":
            offset = int(params["address"]["offset"], 16)
            return {**common, "data_base64": base64.b64encode(self.ram[offset:offset + params["length"]]).decode()}
        if method == "input.keyboard.state":
            return {**common, "keyboard": {"pending_events": 0, "owned_keys": 0, "queued_guest_ms": 0, "frame_keys": []}}
        if method == "input.mouse.state":
            held = self.click and (self.frames < 2 or self.scenario == "held")
            return {**common, "mouse": {"buttons": int(held), "owned_buttons": int(held),
                                        "pending_release_buttons": int(held), "release_pending": held}}
        if method == "execution.timing":
            return {**common, "guest_ticks": self.ticks, "fast_forward": False}
        if method == "video.screenshot":
            return {**common, "data_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nauthored-fixture").decode(),
                    "frame_id": self.frame_id, "mode_id": 1, "width": 320, "height": 200, "captured_ticks": self.ticks}
        if method == "breakpoints.list":
            return {**common, "breakpoints": list(self.entries.values())}
        if method == "breakpoints.create":
            identifier = f"bp-{self.next_id}"
            self.next_id += 1
            entry = {"breakpoint_id": identifier, "kind": "execution", "once": True, "address": params["address"]}
            self.entries[identifier] = entry
            return {**common, **entry}
        if method == "breakpoints.delete":
            del self.entries[params["breakpoint_id"]]
            return {**common, "deleted": True, "breakpoint_id": params["breakpoint_id"]}
        if method == "input.mouse.click":
            self.click = True
            self.frames = 0
            return {**common, "accepted": True, "delivery": "queued"}
        if method == "frame.step":
            if self.scenario == "uncertain":
                raise TimeoutError("Lost acknowledgement after execution dispatch")
            self.revision += 1
            common["state_revision"] = self.revision
            if self.callback_pending:
                self.ram[progress.DS * 16 + 0x4315] += 1
                self.callback_pending = False
            if self.scenario == "foreign":
                self.stop = {"kind": "breakpoint", "breakpoint_id": "foreign", "address": {"space": "segmented", "segment": "0x0824", "offset": "0x1234"}}
                self.entries["foreign"] = {"breakpoint_id": "foreign"}
                return {**common, "completed": False, "stop_reason": self.stop, "registers": registers(0x1234)}
            if self.entries and self.scenario != "no_hit":
                identifier, entry = next(iter(self.entries.items()))
                del self.entries[identifier]
                ip = int(entry["address"]["offset"], 16)
                self.ip = ip
                self.probes_seen.append(ip)
                if ip == progress.DISPATCH:
                    self.callback_pending = True
                self.stop = {"kind": "breakpoint", "breakpoint_id": identifier, "address": entry["address"]}
                return {**common, "completed": False, "stop_reason": self.stop,
                        "registers": registers(ip, 0x21F6 if self.scenario == "wrong_control" else 0x21E8), "guest_ticks": self.ticks}
            self.frames += 1
            self.frame_id += 1
            self.ticks += 14
            self.ip = 0xD532
            self.stop = {"kind": "frame"}
            return {**common, "completed": True, "stop_reason": self.stop, "frame_id": self.frame_id,
                    "mode_id": 1, "registers": registers(), "guest_ticks": self.ticks}
        raise AssertionError("Unexpected native request: " + method)


def setup(tmp_path, monkeypatch, scenario="success"):
    # Authored source bytes qualify only this test peer, never a real executable.
    source = bytes([0x90]) * progress.SOURCE_SIZE
    monkeypatch.setattr(progress, "SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    game = tmp_path / "game"
    game.mkdir()
    path = game / "authored.exe"
    path.write_bytes(source)
    peer = Peer(source)
    ctl = progress.ProgressController(peer, reader, tmp_path / "evidence", session_id="test-session", source_path=path)
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    peer.scenario = scenario
    peer.probes_seen.clear()
    return peer, ctl, ready["after"]


def test_single_click_waits_for_dispatch_release_stability_and_post_action_loop(tmp_path, monkeypatch):
    peer, ctl, observation = setup(tmp_path, monkeypatch)
    result = ctl.perform(observation["scene_token"], label="CONTINUE")
    assert result["outcome"] == "context_changed", result.get("error")
    assert result["story_commit"] == "unknown"
    assert result["readiness"] == {"matched_control_dispatch": True, "input_loop_observed": True,
                                    "input_retired": True, "stable_control_frames": 2,
                                    "fresh_frame_since_dispatch": True, "fresh_frame_after_input_loop": True}
    assert peer.probes_seen == [progress.DISPATCH, progress.INPUT_LOOP, progress.INPUT_LOOP]
    assert result["frames_completed"] == 3  # first frame still has a pending release
    assert result["metrics"]["rpc_by_method"]["input.mouse.click"] == 1
    assert result["metrics"]["model_calls_by_controller"] == 0
    assert result["after"]["scene_token"] != observation["scene_token"]
    assert not peer.entries and not ctl.blocked
    assert Path(result["report_path"]).is_file()


@pytest.mark.parametrize("change", ["token", "revision", "data", "inactive", "label"])
def test_stale_or_inapplicable_selection_sends_no_input(tmp_path, monkeypatch, change):
    peer, ctl, observation = setup(tmp_path, monkeypatch)
    token, label = observation["scene_token"], "CONTINUE"
    if change == "token": token = "old-token"
    if change == "revision": peer.revision += 1
    if change == "data": peer.ram[progress.DS * 16 + 0x4315] += 1
    if change == "inactive": ctl.latest["scene"]["controls"][0]["active"] = False
    if change == "label": label = "NOT A CURRENT LABEL"
    result = ctl.perform(token, label=label)
    assert result["outcome"] == "declined"
    assert not result["input_sent"] and not peer.click
    assert not peer.entries


@pytest.mark.parametrize("scenario, ending", [("foreign", "unexpected_stop"), ("wrong_control", "unexpected_stop"),
                                             ("no_hit", "timeout"), ("held", "timeout"), ("uncertain", "uncertain_dispatch")])
def test_partial_attempt_is_not_replayed_and_preserves_unknown_stops(tmp_path, monkeypatch, scenario, ending):
    peer, ctl, observation = setup(tmp_path, monkeypatch, scenario)
    result = ctl.perform(observation["scene_token"], control_record=0x21E8, max_frames=5)
    assert result["outcome"] == ending, result.get("error")
    assert ctl.blocked and result["story_commit"] == "unknown" and result["after"] is None
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    before_retry = len(peer.calls)
    with pytest.raises(progress.ProgressError, match="reconciled"):
        ctl.perform(observation["scene_token"], label="CONTINUE")
    assert len(peer.calls) == before_retry
    if scenario == "uncertain":
        assert peer.calls[-1][0] == "frame.step"  # no status or cleanup after uncertain dispatch
        assert result["cleanup"]["status"] == "preserved_without_native_calls"
    elif scenario == "foreign":
        assert set(peer.entries) == {"foreign"}
        assert result["error"]["evidence"]["reply"]["stop_reason"]["breakpoint_id"] == "foreign"
    else:
        assert not peer.entries


def test_code_mapping_change_declines_before_input(tmp_path, monkeypatch):
    peer, ctl, observation = setup(tmp_path, monkeypatch)
    peer.ram[progress.CS * 16 + progress.INPUT_LOOP] ^= 1
    result = ctl.perform(observation["scene_token"], label="CONTINUE")
    assert result["outcome"] == "declined" and not peer.click
    assert "hook bytes" in result["error"]["message"]


def test_descriptive_observation_does_not_authorize_a_click(tmp_path, monkeypatch):
    peer, ctl, _ = setup(tmp_path, monkeypatch)
    observation = ctl.observe()
    result = ctl.perform(observation["scene_token"], label="CONTINUE")
    assert result["outcome"] == "declined" and not peer.click
    assert "await_ready" in result["error"]["message"]


def test_input_free_wait_can_explicitly_reconcile_a_known_partial(tmp_path, monkeypatch):
    peer, ctl, observation = setup(tmp_path, monkeypatch, "held")
    attempt = ctl.perform(observation["scene_token"], label="CONTINUE", max_frames=5)
    assert attempt["outcome"] == "timeout" and ctl.blocked
    peer.scenario = "success"
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary" and ctl.blocked
    assert ready["partial_reconciled"] is False and ready["input_attempted"] is False
    reconciled = ctl.await_ready(max_frames=5, reconcile_partial=True)
    assert reconciled["outcome"] == "input_boundary" and not ctl.blocked
    assert reconciled["partial_reconciled"] is True
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1


def test_wait_cannot_bypass_a_timed_out_unvalidated_dispatch(tmp_path, monkeypatch):
    peer, ctl, observation = setup(tmp_path, monkeypatch, "no_hit")
    attempt = ctl.perform(observation["scene_token"], label="CONTINUE", max_frames=5)
    assert attempt["outcome"] == "timeout" and attempt["continuation_allowed"] is False
    prior_calls = len(peer.calls)
    with pytest.raises(progress.ProgressError, match="preserved stop"):
        ctl.await_ready(reconcile_partial=True)
    assert len(peer.calls) == prior_calls


def test_retained_menu_during_flight_waits_without_sending_input(tmp_path, monkeypatch):
    peer, ctl, _ = setup(tmp_path, monkeypatch)
    peer.scenario = "no_hit"
    result = ctl.await_ready(max_frames=5)
    assert result["outcome"] == "timeout" and result["after"] is None
    assert not peer.click and not peer.entries and ctl.ready_token is None


def test_hover_highlight_alone_is_not_a_route_rebind(tmp_path, monkeypatch):
    peer, ctl, observation = setup(tmp_path, monkeypatch)
    original = ctl.call_adapter

    def hover(method, params, timeout_ms):
        result = original(method, params, timeout_ms)
        if method == "frame.step" and result.get("registers", {}).get("instruction_pointer") == hex(progress.DISPATCH):
            struct.pack_into("<H", peer.ram, progress.DS * 16 + 0x260A, 0x8001)
        return result

    ctl.call_adapter = hover
    result = ctl.perform(observation["scene_token"], label="CONTINUE")
    assert result["outcome"] == "context_changed", result.get("error")
    assert result["readiness"]["matched_control_dispatch"] is True


def test_changed_row_binding_at_dispatch_preserves_stop_before_callback(tmp_path, monkeypatch):
    class RebindingPeer(Peer):
        def __call__(self, method, params, timeout_ms):
            reply = super().__call__(method, params, timeout_ms)
            if (method == "frame.step" and reply.get("stop_reason", {}).get("kind") == "breakpoint"
                    and int(reply["registers"]["instruction_pointer"], 16) == progress.DISPATCH):
                # A scheduled update reuses the same rectangle/CE85 row callback
                # for a different command before the pre-call breakpoint.
                struct.pack_into("<H", self.ram, progress.DS * 16 + 0x260C, 0x2222)
                self.rebind_call = len(self.calls) - 1
            return reply

    monkeypatch.setitem(globals(), "Peer", RebindingPeer)
    peer, ctl, observation = setup(tmp_path, monkeypatch)
    result = ctl.perform(observation["scene_token"], label="CONTINUE")
    assert result["outcome"] == "unexpected_stop", result.get("error")
    assert result["input_sent"] is True and result["after"] is None
    assert result["selected"]["row"]["handler"] == 0x1000
    assert ctl.blocked and peer.ip == progress.DISPATCH
    assert not any(method == "frame.step" for method, _ in peer.calls[peer.rebind_call + 1:])
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    assert not peer.entries
    # At this preserved PC, another input-free frame still executes the
    # rejected callback. Neither ordinary waiting nor timeout reconciliation
    # may turn that deliberately rejected route into an authorized effect.
    calls_before_wait = len(peer.calls)
    for reconcile_partial in (False, True):
        with pytest.raises(progress.ProgressError):
            ctl.await_ready(max_frames=5, reconcile_partial=reconcile_partial)
        assert len(peer.calls) == calls_before_wait


def talk_setup(tmp_path, monkeypatch, *, cycle=False, changed_subject=False):
    peer, ctl, _ = setup(tmp_path, monkeypatch)

    def talk_reader(ram, ds):
        result = reader(ram, ds)
        selector = result["conversation_witness"]["dialogue_selector_4315"]
        result["menu"]["rows"][0]["label"]["ascii"] = progress.TALK_LABEL
        result["dialogue_witness_sha256"] = str(selector % 2 if cycle else selector)
        result["text_buffer_candidate"]["ascii_projection"] = f"Authored line {selector}"
        if changed_subject and selector:
            result["subject_selector_431b"] = 1
        return result

    ctl.reader = talk_reader
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary"
    return peer, ctl, ready["after"]


def test_conversation_macro_preserves_exact_label_and_stops_on_dialogue_cycle(tmp_path, monkeypatch):
    peer, ctl, observation = talk_setup(tmp_path, monkeypatch, cycle=True)
    result = progress.continue_conversation(ctl, observation["scene_token"], max_actions=6)
    assert result["outcome"] == "dialogue_repeated"
    assert len(result["steps"]) == 2
    assert result["exact_label"] == '" TALK TO ME "'
    assert [step["text_buffer_candidate"]["ascii_projection"] for step in result["steps"]] == ["Authored line 1", "Authored line 2"]
    assert result["metrics"]["rpc_by_method"]["input.mouse.click"] == 2
    assert result["metrics"]["model_calls_by_controller"] == 0
    assert result["story_commit"] == "unknown" and not ctl.blocked


def test_conversation_macro_does_not_continue_into_a_different_subject(tmp_path, monkeypatch):
    peer, ctl, observation = talk_setup(tmp_path, monkeypatch, changed_subject=True)
    result = progress.continue_conversation(ctl, observation["scene_token"], max_actions=6)
    assert result["outcome"] == "conversation_context_changed"
    assert len(result["steps"]) == 1
    assert result["after"]["scene"]["subject_selector_431b"] == 1


def test_conversation_macro_has_aggregate_action_and_frame_limits(tmp_path, monkeypatch):
    peer, ctl, observation = talk_setup(tmp_path, monkeypatch)
    result = progress.continue_conversation(ctl, observation["scene_token"], max_actions=2)
    assert result["outcome"] == "action_limit" and len(result["steps"]) == 2
    next_result = progress.continue_conversation(ctl, result["after"]["scene_token"], max_frames=1)
    assert next_result["outcome"] == "action_incomplete"
    assert next_result["frames_completed"] == 1 and len(next_result["steps"]) == 1
    assert ctl.blocked
