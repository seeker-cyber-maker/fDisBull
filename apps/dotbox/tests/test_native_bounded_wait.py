"""Real native execution bounds on authored DOS fixtures, never commercial games."""
import json
import os
from pathlib import Path

import pytest

from dotbox.native_session import NativeSession


def _session(tmp_path, code):
    executable = os.environ.get("DOTBOX_DOSBOX_EXECUTABLE")
    if not executable:
        pytest.skip("DOTBOX_DOSBOX_EXECUTABLE required for native bounded-wait acceptance")
    program = tmp_path / "BOUND.COM"
    program.write_bytes(code)
    return NativeSession(executable, tmp_path, program, window=False)


def _stopped(session, result):
    status = session.call("session.status")
    assert status["state"] == "stopped"
    assert status["state_revision"] == result["state_revision"]
    assert status["last_stop"] == result["stop_reason"]
    return status


def _save_result(tmp_path, name, value):
    (tmp_path / (name + ".json")).write_text(json.dumps(value, indent=2) + "\n")


def test_native_bounded_frames_and_legacy_single_frame(tmp_path):
    # Set VGA then stay in an ordinary instruction loop.
    session = _session(tmp_path, bytes.fromhex("b81300cd10ebfe"))
    try:
        cap = session.rpc.capabilities["execution"]["bounded_frame_step"]
        assert cap == {"schema": "dotbox-bounded-frame-step-1", "max_frames": 10000,
                       "max_guest_ms": 30000}
        first = session.call("frame.step")
        _stopped(session, first)
        assert first["completed"] is True and "bounded" not in first
        result = session.call("frame.step", {"max_frames": 4, "max_guest_ms": 1000})
        _stopped(session, result)
        assert result["completed"] is True
        assert result["bounded"]["stop_cause"] == "frame_limit"
        assert result["bounded"]["frames_completed"] == 4
        assert 0 < result["bounded"]["guest_elapsed_ms"] < 1000
        assert result["frame_id"] == first["frame_id"] + 4
        assert result["frame_available"] is True
        legacy = session.call("frame.step")
        _stopped(session, legacy)
        assert legacy["completed"] is True and "bounded" not in legacy
        assert legacy["frame_id"] == result["frame_id"] + 1
        _save_result(tmp_path, "frames", {"first": first, "bounded": result, "legacy": legacy})
    finally:
        session.close()
    assert session.rpc.process.poll() == 0


def test_native_guest_limit_returns_stopped_without_waiting_for_frame(tmp_path):
    session = _session(tmp_path, b"\x90" * 60000 + b"\xeb\xfe")
    try:
        result = session.call("frame.step", {"max_frames": 1000, "max_guest_ms": 1})
        _stopped(session, result)
        assert result["completed"] is False
        assert result["stop_reason"]["kind"] == "budget"
        assert result["bounded"]["stop_cause"] == "guest_time_limit"
        assert result["bounded"]["frames_completed"] == 0
        assert result["bounded"]["guest_elapsed_ms"] == 1
        assert result["bounded"]["guest_tick_bits"] in (32, 64)
        _save_result(tmp_path, "guest-limit", result)
    finally:
        session.close()
    assert session.rpc.process.poll() == 0


def test_native_breakpoint_wins_at_same_guest_budget_boundary(tmp_path):
    # A straight-line authored program lets the first run discover the precise
    # instruction at the native 1 ms boundary. Rewind machine memory, arm
    # that address, and repeat the identical bound. There is no earlier visit
    # to that instruction at which the breakpoint could satisfy this test.
    session = _session(tmp_path, b"\x90" * 60000 + b"\xeb\xfe")
    try:
        checkpoint = tmp_path / "collision.sav"
        saved = session.call("state.save", {"path": str(checkpoint)})
        assert saved["completed"] is True and saved["frame_keys"] == []
        reference = session.call("frame.step", {"max_frames": 1000, "max_guest_ms": 1})
        _stopped(session, reference)
        assert reference["bounded"]["stop_cause"] == "guest_time_limit"
        address = {"space": "segmented", "segment": reference["registers"]["segments"]["cs"],
                   "offset": reference["registers"]["instruction_pointer"]}
        assert 0x100 < int(address["offset"], 16) < 60100
        restored = session.call("state.load", {"path": str(checkpoint), "frame_keys": [],
                                              "expected_generation": 0})
        assert restored["completed"] is True
        breakpoint = session.call("breakpoints.create", {"kind": "execution", "once": True,
                                                         "address": address})
        collision = session.call("frame.step", {"max_frames": 1000, "max_guest_ms": 1})
        _stopped(session, collision)
        assert collision["bounded"]["guest_elapsed_ms"] == reference["bounded"]["guest_elapsed_ms"]
        assert collision["bounded"]["frames_completed"] == reference["bounded"]["frames_completed"]
        assert collision["registers"]["segments"]["cs"] == address["segment"]
        assert collision["registers"]["instruction_pointer"] == address["offset"]
        assert collision["stop_reason"]["kind"] == "breakpoint"
        assert collision["stop_reason"]["breakpoint_id"] == breakpoint["breakpoint_id"]
        assert collision["bounded"]["stop_cause"] == "breakpoint"
        assert collision["completed"] is False
        _save_result(tmp_path, "collision", {"reference": reference, "collision": collision})
    finally:
        session.close()
    assert session.rpc.process.poll() == 0



def test_native_halted_cpu_attributes_pending_breakpoint_at_frame_limit(tmp_path):
    # CLI; HLT prevents any further instruction fetch before the renderer event.
    # The native frame boundary must still attribute the newly armed address.
    # No restoration or assumed post-restore renderer phase is involved.
    session = _session(tmp_path, bytes.fromhex("faf490ebfe"))
    try:
        halted = session.call("frame.step", {"max_frames": 100, "max_guest_ms": 1})
        _stopped(session, halted)
        assert halted["bounded"]["stop_cause"] == "guest_time_limit"
        assert int(halted["registers"]["instruction_pointer"], 16) == 0x102
        address = {"space": "segmented", "segment": halted["registers"]["segments"]["cs"],
                   "offset": "0x00000102"}
        breakpoint = session.call("breakpoints.create", {"kind": "execution", "once": True,
                                                         "address": address})
        result = session.call("frame.step", {"max_frames": 1, "max_guest_ms": 1000})
        _stopped(session, result)
        assert result["bounded"]["frames_completed"] == 1
        assert result["bounded"]["guest_elapsed_ms"] > 0
        assert result["bounded"]["stop_cause"] == "breakpoint"
        assert result["stop_reason"]["kind"] == "breakpoint"
        assert result["stop_reason"]["breakpoint_id"] == breakpoint["breakpoint_id"]
        assert int(result["registers"]["instruction_pointer"], 16) == 0x102
        assert result["completed"] is False
        _save_result(tmp_path, "halted-frame-breakpoint", {"halted": halted, "frame": result})
    finally:
        session.close()
    assert session.rpc.process.poll() == 0


def test_native_foreign_breakpoint_preempts_multiframe_wait(tmp_path):
    session = _session(tmp_path, bytes.fromhex("909090ebfe"))
    try:
        registers = session.call("state.get_registers")
        breakpoint = session.call("breakpoints.create", {"kind": "execution", "once": True,
            "address": {"space": "segmented", "segment": registers["segments"]["cs"],
                        "offset": "0x00000102"}})
        result = session.call("frame.step", {"max_frames": 1000, "max_guest_ms": 1000})
        _stopped(session, result)
        assert result["stop_reason"]["kind"] == "breakpoint"
        assert result["stop_reason"]["breakpoint_id"] == breakpoint["breakpoint_id"]
        assert result["bounded"]["stop_cause"] == "breakpoint"
        assert result["bounded"]["frames_completed"] == 0
        assert int(result["registers"]["instruction_pointer"], 16) == 0x102
        _save_result(tmp_path, "foreign-stop", result)
    finally:
        session.close()
    assert session.rpc.process.poll() == 0


def test_native_invalid_bounds_do_not_run_guest(tmp_path):
    session = _session(tmp_path, bytes.fromhex("909090ebfe"))
    try:
        before = session.call("session.status")
        registers = session.call("state.get_registers")
        for bounds in ({"max_frames": 4}, {"max_guest_ms": 1},
                       {"max_frames": 0, "max_guest_ms": 1},
                       {"max_frames": 1, "max_guest_ms": 0},
                       {"max_frames": 10001, "max_guest_ms": 1},
                       {"max_frames": 1, "max_guest_ms": 30001},
                       {"max_frames": True, "max_guest_ms": 1}):
            with pytest.raises(ValueError, match="Bounded frame.step requires"):
                session.call("frame.step", bounds)
            after = session.call("session.status")
            assert after["state"] == "stopped" and after["state_revision"] == before["state_revision"]
            assert session.call("state.get_registers") == registers
    finally:
        session.close()
    assert session.rpc.process.poll() == 0
