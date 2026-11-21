"""Authored context fences for input-free recovery from an owned native budget."""
import pytest

from test_dune_progress import progress
from test_dune_progress_native import make_native


@pytest.fixture
def owned_budget_partial(tmp_path, monkeypatch):
    peer, controller = make_native(tmp_path, monkeypatch)
    ready = controller.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    peer.budget_after_dispatch = True
    action = controller.perform(ready["after"]["scene_token"], label="CONTINUE", max_guest_ms=1)
    assert action["outcome"] == "timeout", action.get("error")
    assert action["readiness"]["matched_control_dispatch"]
    assert action["continuation_allowed"] and controller.blocked
    assert action["cleanup"]["status"] == "clean" and not peer.entries
    peer.budget_after_dispatch = False
    return peer, controller


@pytest.mark.parametrize("invalid_context", ["protected", "code32", "paging"])
def test_owned_budget_mapping_exception_does_not_relax_cpu_mode(owned_budget_partial, invalid_context):
    peer, controller = owned_budget_partial
    original = controller.call_adapter

    def changed_context(method, params, timeout_ms):
        reply = original(method, params, timeout_ms)
        if method == "state.get_registers" and peer.stop["kind"] == "budget":
            reply["segments"]["cs"] = "0x26D4"  # Authored temporary overlay context.
            if invalid_context == "protected":
                reply["cpu_mode"] = "protected"
            elif invalid_context == "code32":
                reply["code_bits"] = 32
            else:
                reply["address_context"]["paging_enabled"] = True
        return reply

    controller.call_adapter = changed_context
    calls_before = len(peer.calls)
    result = controller.await_ready(max_frames=5, reconcile_partial=True)

    assert result["outcome"] == "observation_error"
    assert "qualified real-mode Dune code/data mapping changed" in result["error"]["message"]
    assert result["after"] is None and result["partial_reconciled"] is False
    assert controller.ready_token is None and controller.blocked
    assert not any(method in ("frame.step", "input.mouse.click")
                   for method, _ in peer.calls[calls_before:])
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1


def test_owned_budget_resume_requires_full_mapping_at_returned_input_loop(owned_budget_partial):
    peer, controller = owned_budget_partial
    original = controller.call_adapter

    def wrong_return_mapping(method, params, timeout_ms):
        reply = original(method, params, timeout_ms)
        if method == "state.get_registers" and peer.stop["kind"] == "budget":
            reply["segments"]["cs"] = "0x26D4"
        elif (method == "frame.step" and reply.get("stop_reason", {}).get("kind") == "breakpoint"
                and reply.get("registers", {}).get("instruction_pointer") == hex(progress.INPUT_LOOP)):
            reply["registers"]["segments"]["ds"] = "0xA000"
        return reply

    controller.call_adapter = wrong_return_mapping
    calls_before = len(peer.calls)
    result = controller.await_ready(max_frames=5, reconcile_partial=True)

    assert result["outcome"] == "observation_error"
    assert "qualified real-mode Dune code/data mapping changed" in result["error"]["message"]
    assert result["after"] is None and result["partial_reconciled"] is False
    assert controller.ready_token is None and controller.blocked
    assert peer.ip == progress.INPUT_LOOP
    assert sum(method == "frame.step" for method, _ in peer.calls[calls_before:]) == 1
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1
    # A reached address with the wrong data mapping must not authorize another
    # action or hide the original incomplete action behind a refreshed token.
    calls_before_action = len(peer.calls)
    with pytest.raises(progress.ProgressError, match="partial/uncertain"):
        controller.perform("unqualified-token", label="CONTINUE")
    assert len(peer.calls) == calls_before_action
