"""Authored peers test Dune batch failure policy, not game/runtime qualification."""
from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import struct

import pytest


SPEC = importlib.util.spec_from_file_location(
    "dune_probe_batch", Path(__file__).resolve().parents[1] / "scripts/experiments/dune_probe_batch.py")
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


def registers(offset=0x1111):
    return {"cpu_mode": "real", "code_bits": 16, "stack_bits": 16,
            "address_context": {"paging_enabled": False},
            "segments": {"cs": hex(batch.CS), "ds": hex(batch.DS)},
            "instruction_pointer": hex(offset), "general": {}}


def hit(identifier="bp-owned", offset=0x1111):
    return {"session_id": "test-session", "state_revision": 4, "completed": False,
            "stop_reason": {"kind": "breakpoint", "breakpoint_id": identifier,
                            "address": {"space": "segmented", "segment": hex(batch.CS), "offset": hex(offset)}},
            "registers": registers(offset)}


def runner_for(call):
    # Bypass executable/file admission only: these tests exercise RPC/stop policy.
    runner = batch._Runner.__new__(batch._Runner)
    runner.call = call
    runner.source = bytes(batch.SOURCE_SIZE)
    runner.session_id = "test-session"
    runner.owned = {"bp-owned"}
    probe = {"id": "bp-owned", "labels": ["test"], "segment": batch.CS,
             "offset": 0x1111, "active": True}
    runner.probes = {"bp-owned": probe}
    runner.by_address = {(batch.CS, 0x1111): probe}
    runner.uncertain = False
    runner.stopped = True
    runner.deadline = None
    return runner


def opening_menu():
    data = bytearray(65536)
    for offset, value in ((0x2840, 0x2824), (0x2824, 0x2598), (0x2598, 0x00FF),
                          (0x259A, 0x008E), (0x259C, 0x1BBF), (0x259E, 0x006E),
                          (0x25A0, 0x9DDC)):
        struct.pack_into("<H", data, offset, value)
    data[0xFED5] = 0xFF
    rows = [{"bounds": bounds, "flag_bytes": (0x80, 0), "value": 27, "callback": callback}
            for bounds, callback in (((92, 159, 228, 167), 0xCE85), ((92, 167, 228, 175), 0xCE80))]
    return data, rows


def test_opening_menu_binds_handlers_flags_and_click_geometry():
    data, rows = opening_menu()
    observed = batch._opening_menu(data, rows)
    assert [entry["handler"] for entry in observed["entries"]] == [0x1BBF, 0x9DDC]
    assert observed["special_row"] == 0xFF and observed["skip"] == 0


@pytest.mark.parametrize("alter", [
    lambda data, rows: struct.pack_into("<H", data, 0x259C, 0x2222),
    lambda data, rows: data.__setitem__(0xFED4, 1),
    lambda data, rows: rows[0].update(flag_bytes=(0, 0)),
    lambda data, rows: rows[1].update(bounds=(92, 175, 228, 183)),
])
def test_other_menu_or_inactive_geometry_is_refused(alter):
    data, rows = opening_menu()
    alter(data, rows)
    with pytest.raises(batch.BatchAborted):
        batch._opening_menu(data, rows)


@pytest.mark.parametrize("change", [
    lambda r: r["stop_reason"].update(kind="pause"),
    lambda r: r["stop_reason"].update(breakpoint_id="foreign"),
    lambda r: r["stop_reason"]["address"].update(offset="0x2222"),
    lambda r: r["registers"].update(instruction_pointer="0x2222"),
    lambda r: r.update(completed=True),
])
def test_stop_requires_kind_owned_id_address_and_register_pc(change):
    runner = runner_for(None)
    result = hit()
    change(result)
    with pytest.raises(batch.UnexpectedStop):
        runner.accept_stop(result, {"state": "stopped"})
    assert runner.probes["bp-owned"]["active"] is True


def test_consumed_one_shot_cannot_be_accepted_again():
    runner = runner_for(None)
    assert runner.accept_stop(hit(), {})["active"] is False
    with pytest.raises(batch.UnexpectedStop, match="active owned"):
        runner.accept_stop(hit(), {})


def test_frame_rejects_stale_status_before_attributing_a_hit():
    calls = []

    def peer(method, params, timeout_ms):
        calls.append(method)
        if method == "frame.step":
            return hit()
        return {"session_id": "test-session", "state_revision": 5,
                "state": "stopped", "last_stop": hit()["stop_reason"]}

    runner = runner_for(peer)
    with pytest.raises(batch.UnexpectedStop, match="Fresh status"):
        runner.frame()
    assert calls == ["frame.step", "session.status"]
    assert runner.probes["bp-owned"]["active"] is True


class FailurePeer:
    def __init__(self, *, uncertain=False):
        self.calls = []
        self.entries = {}
        self.revision = 1
        self.stop = {"kind": "pause"}
        self.uncertain = uncertain

    def __call__(self, method, params, timeout_ms):
        self.calls.append((method, deepcopy(params)))
        result = {"session_id": "test-session", "state_revision": self.revision}
        if method == "session.status":
            return {**result, "state": "stopped", "last_stop": self.stop}
        if method == "breakpoints.list":
            return {**result, "breakpoints": list(self.entries.values())}
        if method == "breakpoints.create":
            entry = {"breakpoint_id": "bp-owned", "kind": "execution", "once": True,
                     "enabled": True, "address": params["address"]}
            self.entries["bp-owned"] = entry
            return {**result, **entry}
        if method == "breakpoints.delete":
            del self.entries[params["breakpoint_id"]]
            return {**result, "breakpoint_id": params["breakpoint_id"], "deleted": True}
        if method == "input.keyboard.state":
            return {**result, "keyboard": {"pending_events": 0, "owned_keys": 0,
                                            "queued_guest_ms": 0, "frame_keys": []}}
        if method == "input.mouse.state":
            return {**result, "mouse": {"buttons": 0, "owned_buttons": 0,
                                         "pending_release_buttons": 0, "release_pending": False}}
        if method == "input.mouse.click":
            return {**result, "accepted": True, "delivery": "queued"}
        if method == "execution.timing":
            return {**result, "guest_ticks": 100}
        if method == "memory.read":
            return {**result, "data_base64": base64.b64encode(bytes(params["length"])).decode()}
        if method == "state.load":
            return {**result, "completed": True, "frame_keys": []}
        if method == "frame.step":
            if self.uncertain:
                raise TimeoutError("Acknowledgement lost after dispatch")
            response = hit("bp-foreign")
            self.revision = response["state_revision"]
            self.stop = response["stop_reason"]
            self.entries["bp-foreign"] = {"breakpoint_id": "bp-foreign"}
            return response
        raise AssertionError("Unexpected peer request: " + method)


@pytest.mark.parametrize("uncertain", [False, True])
def test_batch_aborts_without_next_restore_and_cleans_only_when_certain(tmp_path, monkeypatch, uncertain):
    peer = FailurePeer(uncertain=uncertain)
    runner = runner_for(peer)
    runner.root, runner.game = tmp_path / "evidence", tmp_path / "game"
    runner.root.mkdir()
    runner.game.mkdir()
    runner.owned.clear()
    runner.probes.clear()
    runner.by_address.clear()
    baseline = {"schema": "dune-probe-baseline-1", "source_sha256": batch.SOURCE_SHA256,
                "checkpoint": {"file": "throne-baseline.sav"},
                "saved": {"session_id": "test-session"}, "bindings": []}
    (runner.root / "baseline.json").write_text(json.dumps(baseline))

    def restore(_baseline):
        runner.rpc("state.load", {"path": "authored-state"})
        return {"settle": {"frame_id": 1, "mode_id": 1}}

    runner.restore = restore
    runner.bindings = lambda: []
    monkeypatch.setattr(batch, "_Runner", lambda *args: runner)
    monkeypatch.setattr(batch, "ANCHORS", (("test", 0x1111, 3),))
    monkeypatch.setattr(batch, "TRIALS", (("first", (1, 2)), ("must_not_run", (3, 4))))
    with pytest.raises(batch.BatchAborted) as raised:
        batch.run_batch(peer, runner.root, runner.game, profile="dispatch")
    methods = [method for method, _ in peer.calls]
    assert methods.count("state.load") == 1
    assert methods.count("input.mouse.click") == 1
    assert methods.count("frame.step") == 1
    report = json.loads(Path(raised.value.report_path).read_text())
    assert report["completed"] is False
    assert report["error"]["uncertain_dispatch"] is uncertain
    assert len(report["trials"]) == 1
    if uncertain:
        assert methods[-1] == "frame.step"  # No status, cleanup, input, or replay.
        assert "bp-owned" in peer.entries
    else:
        deleted = [params["breakpoint_id"] for method, params in peer.calls if method == "breakpoints.delete"]
        assert deleted == ["bp-owned"]
        assert set(peer.entries) == {"bp-foreign"}
        assert report["error"]["evidence"]["result"]["stop_reason"]["breakpoint_id"] == "bp-foreign"
