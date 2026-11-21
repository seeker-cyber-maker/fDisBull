"""Real sparse readers with an authored protocol peer, not live-game qualification."""
import hashlib

import pytest

from test_dune_progress import progress
from test_dune_progress_native import BoundedPeer, CAPABILITIES
from test_dune_ui_reader import BASE, authored_ram, put_label, reader


@pytest.fixture
def sparse_controller(tmp_path, monkeypatch):
    source = b"\x90" * progress.SOURCE_SIZE
    monkeypatch.setattr(progress, "SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    game = tmp_path / "game"
    game.mkdir()
    executable = game / "authored.exe"
    executable.write_bytes(source)

    peer = BoundedPeer(source)
    peer.ram = authored_ram(conversation=True)
    # The authored UI and code witnesses occupy separate memory regions.
    # Only hook bytes are needed; no real executable or capture is imported.
    for offset in (progress.DISPATCH, progress.INPUT_LOOP, *progress.ROW_CALLBACKS):
        start = progress.CS * 16 + offset
        peer.ram[start:start + 5] = source[progress.HEADER + offset:progress.HEADER + offset + 5]
    controller = progress.ProgressController(
        peer, reader.describe, tmp_path / "evidence",
        session_id="test-session", source_path=executable,
        wait_strategy="native", capabilities=CAPABILITIES,
        read_strategy="sparse", sparse_reader=reader.describe_sparse,
        structure_reader=reader.read_structure_sparse,
    )
    ready = controller.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    assert ready["after"]["memory_mode"] == "sparse"
    return peer, controller, ready["after"]


def test_sparse_action_reaches_fresh_input_boundary_with_real_reader(sparse_controller):
    peer, controller, observation = sparse_controller
    result = controller.perform(observation["scene_token"], label="Authored alpha", max_frames=5)

    assert result["outcome"] == "context_changed", result.get("error")
    assert result["after"]["memory_mode"] == "sparse"
    assert result["after"]["scene"] == reader.describe(peer.ram)
    assert result["readiness"] == {
        "matched_control_dispatch": True, "input_loop_observed": True,
        "input_retired": True, "stable_control_frames": 2,
        "fresh_frame_since_dispatch": True, "fresh_frame_after_input_loop": True,
    }
    assert peer.ip == progress.INPUT_LOOP and not peer.entries
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    assert result["continuation_allowed"] and not controller.blocked


def test_changed_external_label_dependency_declines_before_click(sparse_controller):
    peer, controller, observation = sparse_controller
    # This loaded text pool lies outside DS. Checking only a DS hash cannot
    # establish the unchanged label that the user selected.
    put_label(peer.ram, 1, b"Authored changed route")
    calls_before = len(peer.calls)
    result = controller.perform(observation["scene_token"], label="Authored alpha", max_frames=5)

    assert result["outcome"] == "declined"
    assert "Parsed Dune dependencies changed" in result["error"]["message"]
    assert result["input_attempted"] is False and result["input_sent"] is False
    assert not any(method in ("input.mouse.click", "frame.step")
                   for method, _ in peer.calls[calls_before:])
    assert peer.ip == progress.INPUT_LOOP and not peer.entries


def test_revision_change_during_sparse_admission_prevents_input(sparse_controller):
    peer, controller, observation = sparse_controller
    original = controller.call_adapter
    changed = False

    def change_revision(method, params, timeout_ms):
        nonlocal changed
        reply = original(method, params, timeout_ms)
        if method == "memory.read" and not changed:
            peer.revision += 1
            changed = True
        return reply

    controller.call_adapter = change_revision
    calls_before = len(peer.calls)
    result = controller.perform(observation["scene_token"], label="Authored alpha", max_frames=5)

    assert changed and result["outcome"] == "unexpected_stop"
    assert "Sparse admission changed while reading dependencies" in result["error"]["message"]
    assert result["input_attempted"] is False and result["input_sent"] is False
    assert not any(method in ("input.mouse.click", "frame.step")
                   for method, _ in peer.calls[calls_before:])
    assert not result["continuation_allowed"] and controller.ready_token is None


def test_sparse_dispatch_label_rebind_preserves_pre_call_stop_without_resume(sparse_controller):
    peer, controller, observation = sparse_controller
    original = controller.call_adapter
    calls_at_rebind = None

    def rebind_label(method, params, timeout_ms):
        nonlocal calls_at_rebind
        reply = original(method, params, timeout_ms)
        if (method == "frame.step" and reply.get("stop_reason", {}).get("kind") == "breakpoint"
                and reply.get("registers", {}).get("instruction_pointer") == hex(progress.DISPATCH)):
            put_label(peer.ram, 1, b"Authored changed route")
            calls_at_rebind = len(peer.calls)
        return reply

    controller.call_adapter = rebind_label
    result = controller.perform(observation["scene_token"], label="Authored alpha", max_frames=5)

    assert calls_at_rebind is not None and result["outcome"] == "unexpected_stop"
    assert "Selected route rebound before its callback" in result["error"]["message"]
    assert result["input_sent"] is True and result["after"] is None
    assert peer.ip == progress.DISPATCH and controller.blocked
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    assert not any(method == "frame.step" for method, _ in peer.calls[calls_at_rebind:])
    assert not result["continuation_allowed"] and not peer.entries

    # Neither ordinary observation waiting nor explicit partial reconciliation
    # may execute the rejected callback that is still at the preserved PC.
    calls_before_wait = len(peer.calls)
    for reconcile_partial in (False, True):
        with pytest.raises(progress.ProgressError, match="preserved stop"):
            controller.await_ready(max_frames=5, reconcile_partial=reconcile_partial)
        assert len(peer.calls) == calls_before_wait


def test_unparsed_prefetch_change_does_not_invalidate_sparse_action(sparse_controller):
    peer, controller, observation = sparse_controller
    address = BASE + 0x4000
    before = observation["memory_capture"]
    assert any(item["address"] <= address < item["address"] + item["length"]
               for item in before["reads"]["ranges"])
    assert not any(item["address"] <= address < item["address"] + item["length"]
                   for item in before["dependencies"])
    peer.ram[address] ^= 1

    result = controller.perform(observation["scene_token"], label="Authored alpha", max_frames=5)
    assert result["outcome"] == "context_changed", result.get("error")
    admitted = result["admission_capture"]["memory_capture"]
    assert admitted["sha256"] != before["sha256"]
    assert admitted["dependency_sha256"] == before["dependency_sha256"]
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    assert peer.ip == progress.INPUT_LOOP and result["continuation_allowed"]
