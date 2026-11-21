"""Authored bounded protocol peers; actual native execution has separate tests."""
from copy import deepcopy
import hashlib

import pytest

from test_dune_progress import Peer, progress, reader, registers


CAPABILITIES = {"execution": {"bounded_frame_step": {
    "schema": "dotbox-bounded-frame-step-1", "max_frames": 10000,
    "max_guest_ms": 30000,
}}}


class BoundedPeer(Peer):
    """Execute the authored peer until an event, frame count or guest deadline."""

    def __init__(self, source):
        super().__init__(source)
        self.budget_after_dispatch = False
        self.delay_probe_frames = 0
        self.corrupt = None

    def __call__(self, method, params, timeout_ms):
        if method in ("breakpoints.create", "breakpoints.delete"):
            reply = super().__call__(method, params, timeout_ms)
            self.revision += 1  # Native probe mutations advance the revision.
            reply["state_revision"] = self.revision
            return reply
        if method != "frame.step" or "max_frames" not in params:
            return super().__call__(method, params, timeout_ms)
        before, frames, reply = self.ticks, 0, None
        limit, guest_limit = params["max_frames"], params["max_guest_ms"]
        while frames < limit:
            remaining = guest_limit - ((self.ticks - before) % (1 << 32))
            if (self.budget_after_dispatch and self.ip == progress.DISPATCH
                    or remaining < 14 and (not self.entries or self.scenario == "no_hit")):
                self.calls.append((method, deepcopy(params)))
                self.ticks = (self.ticks + remaining) % (1 << 32)
                self.revision += 1
                self.stop = {"kind": "budget"}
                reply = {"session_id": "test-session", "state_revision": self.revision,
                         "completed": False, "stop_reason": self.stop,
                         "registers": registers(self.ip), "guest_ticks": self.ticks}
                cause = "guest_time_limit"
                break
            delayed = self.entries if self.delay_probe_frames else None
            if delayed is not None:
                self.entries = {}
                self.delay_probe_frames -= 1
            reply = super().__call__(method, params, timeout_ms)
            if delayed is not None:
                self.entries = delayed
            self.ticks %= 1 << 32
            reply["guest_ticks"] = self.ticks
            if not reply["completed"]:
                cause = "breakpoint"
                break
            frames += 1
            if frames == limit:
                cause = "frame_limit"
        reply.update(frame_available=True, frame_id=self.frame_id)
        reply["bounded"] = {"max_frames": limit, "max_guest_ms": guest_limit,
                            "frames_completed": frames, "guest_tick_bits": 32,
                            "guest_ticks_before": before, "guest_ticks_after": self.ticks,
                            "guest_elapsed_ms": (self.ticks - before) % (1 << 32),
                            "stop_cause": cause}
        if self.corrupt:
            self.corrupt(reply)
        return reply


def make_native(tmp_path, monkeypatch, *, capabilities=CAPABILITIES):
    source = b"\x90" * progress.SOURCE_SIZE
    monkeypatch.setattr(progress, "SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    game = tmp_path / "game"
    game.mkdir()
    path = game / "authored.exe"
    path.write_bytes(source)
    peer = BoundedPeer(source)
    ctl = progress.ProgressController(peer, reader, tmp_path / "evidence",
                                     session_id="test-session", source_path=path,
                                     wait_strategy="native", capabilities=capabilities)
    return peer, ctl


def test_native_wait_requires_explicit_compatible_capability(tmp_path, monkeypatch):
    with pytest.raises(progress.ProgressError, match="capability"):
        make_native(tmp_path, monkeypatch, capabilities={})


def test_batched_frames_are_charged_even_when_wait_ends_at_owned_probe(tmp_path, monkeypatch):
    peer, ctl = make_native(tmp_path, monkeypatch)
    peer.delay_probe_frames = 4
    ready = ctl.await_ready(max_frames=10)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    assert ready["native_waits"][0]["stop_cause"] == "breakpoint"
    assert ready["native_waits"][0]["frames_completed"] == 4
    assert ready["frames_completed"] == 6
    assert ready["bounded_guest_elapsed_ms"] == 84
    assert not peer.click and not peer.entries


@pytest.mark.parametrize("transient_segment", [None, "cs", "ds"])
def test_valid_own_guest_budget_can_be_reconciled_without_replaying_input(tmp_path, monkeypatch, transient_segment):
    peer, ctl = make_native(tmp_path, monkeypatch)
    if transient_segment:
        def transient_mapping(method, params, timeout_ms):
            reply = peer(method, params, timeout_ms)
            if method == "state.get_registers" and peer.stop["kind"] == "budget":
                reply["segments"][transient_segment] = "0xA000"  # Overlay/renderer before the input loop.
            return reply
        ctl.call_adapter = transient_mapping
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary"
    peer.budget_after_dispatch = True
    action = ctl.perform(ready["after"]["scene_token"], label="CONTINUE", max_guest_ms=1)
    assert action["outcome"] == "timeout", action.get("error")
    assert action["readiness"]["matched_control_dispatch"]
    assert action["continuation_allowed"] and ctl.blocked
    assert action["bounded_guest_elapsed_ms"] == 1
    peer.budget_after_dispatch = False
    reconciled = ctl.await_ready(max_frames=5, reconcile_partial=True)
    assert reconciled["outcome"] == "input_boundary", reconciled.get("error")
    assert reconciled["partial_reconciled"] and not ctl.blocked
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1


@pytest.mark.parametrize("foreign_revision", [False, True])
def test_unowned_or_changed_budget_stop_cannot_be_resumed(tmp_path, monkeypatch, foreign_revision):
    peer, ctl = make_native(tmp_path, monkeypatch)
    if foreign_revision:
        peer.scenario = "no_hit"
        own = ctl.await_ready(max_guest_ms=1)
        assert own["outcome"] == "timeout"
        peer.revision += 1
    peer.stop = {"kind": "budget"}
    peer.calls.clear()
    refused = ctl.await_ready()
    assert refused["outcome"] == "unexpected_stop"
    assert not refused["continuation_allowed"]
    assert [method for method, _ in peer.calls] == ["session.status"]


@pytest.mark.parametrize("corruption", ["frames", "clock", "cause", "running"])
def test_inconsistent_native_result_stays_stopped_without_retry(tmp_path, monkeypatch, corruption):
    peer, ctl = make_native(tmp_path, monkeypatch)
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary"
    def corrupt(reply):
        if corruption == "frames": reply["bounded"]["frames_completed"] = 10001
        elif corruption == "clock": reply["bounded"]["guest_ticks_before"] += 1
        elif corruption == "cause": reply["bounded"]["stop_cause"] = "frame_limit"
        else: reply["state_revision"] += 1
    peer.corrupt = corrupt
    result = ctl.perform(ready["after"]["scene_token"], label="CONTINUE")
    assert result["outcome"] == "unexpected_stop"
    assert not result["continuation_allowed"]
    assert sum(method == "input.mouse.click" for method, _ in peer.calls) == 1


@pytest.mark.parametrize("scenario, ending", [("foreign", "unexpected_stop"), ("uncertain", "uncertain_dispatch")])
def test_native_wait_preserves_foreign_or_uncertain_execution(tmp_path, monkeypatch, scenario, ending):
    peer, ctl = make_native(tmp_path, monkeypatch)
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary"
    peer.scenario = scenario
    result = ctl.perform(ready["after"]["scene_token"], label="CONTINUE")
    assert result["outcome"] == ending
    assert not result["continuation_allowed"]
    if scenario == "uncertain":
        assert peer.calls[-1][0] == "frame.step"
    else:
        assert set(peer.entries) == {"foreign"}


def test_native_clock_wrap_is_accounted_in_wait_budget(tmp_path, monkeypatch):
    peer, ctl = make_native(tmp_path, monkeypatch)
    peer.ticks = (1 << 32) - 20
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    assert ready["bounded_guest_elapsed_ms"] == 28
    assert ready["guest_elapsed_ms"] == 28


@pytest.mark.parametrize("change", ["extra_revision", "different_stop"])
def test_cleanup_does_not_adopt_an_unrelated_change_as_owned_budget(tmp_path, monkeypatch, change):
    peer, ctl = make_native(tmp_path, monkeypatch)
    ready = ctl.await_ready(max_frames=5)
    assert ready["outcome"] == "input_boundary"
    def external_change(method, params, timeout_ms):
        reply = peer(method, params, timeout_ms)
        if method == "breakpoints.delete":
            if change == "extra_revision":
                peer.revision += 1
                reply["state_revision"] = peer.revision
            else:
                peer.stop = {"kind": "pause"}
        return reply
    ctl.call_adapter = external_change
    peer.budget_after_dispatch = True
    action = ctl.perform(ready["after"]["scene_token"], label="CONTINUE", max_guest_ms=1)
    assert action["outcome"] == "cleanup_failed"
    assert not action["continuation_allowed"]
    calls = len(peer.calls)
    with pytest.raises(progress.ProgressError, match="preserved stop"):
        ctl.await_ready(reconcile_partial=True)
    assert len(peer.calls) == calls
