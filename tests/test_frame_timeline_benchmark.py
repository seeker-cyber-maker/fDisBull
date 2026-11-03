"""Offline checks for the authored benchmark protocol; no emulator is launched."""
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/benchmark_frame_timeline.py"
spec = importlib.util.spec_from_file_location("frame_timeline_benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_authored_fixture_branch_targets_and_control_writes():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    code = benchmark.FIXTURE_CODE
    instructions = list(Cs(CS_ARCH_X86, CS_MODE_16).disasm(code, 0x100))
    assert sum(instruction.size for instruction in instructions) == len(code)
    branches = {instruction.address: instruction.op_str for instruction in instructions
                if instruction.mnemonic in {"je", "jmp"}}
    assert branches == {0x112: "0x123", 0x129: "0x10e"}
    # These three writes independently bind the machine code to the declared
    # counter, additive BIOS-key checksum, and last-key oracle.
    assert [(instruction.mnemonic, instruction.op_str) for instruction in instructions[12:15]] == [
        ("inc", "word ptr [0x204]"), ("add", "word ptr [0x206], ax"),
        ("mov", "word ptr [0x208], ax")]
    assert benchmark.authored_com()[0x100:0x104] == b"FTL1"
    assert len(benchmark.authored_com()) == 512


def test_default_input_plan_is_balanced_and_independent_oracle_matches_bios_words():
    plan = benchmark.frame_plan(24)
    assert [item["frame"] for item in plan] == [0, 2, 6, 8, 12, 14]
    held = set()
    presses = []
    for item in plan:
        for edge in item["edges"]:
            if edge["pressed"]:
                assert edge["key"] not in held
                held.add(edge["key"])
                presses.append(edge["key"])
            else:
                held.remove(edge["key"])
    assert not held and presses == ["a", "b", "c"]
    assert benchmark.expected_controls(0) == {"count": 0, "sum": 0, "last": 0}
    # Keyboard scan codes 1e,30,2e and ASCII 61,62,63 independently give this sum.
    assert benchmark.expected_controls(24) == {"count": 3, "sum": 0x7d26, "last": 0x2e63}
    data = benchmark.expected_module(benchmark.expected_controls(24))
    assert struct.unpack_from("<3H", data, 0x104) == (3, 0x7d26, 0x2e63)


def test_capture_accounting_refuses_to_call_evicted_bytes_cumulative():
    status = {"captures_used": 2, "state_bytes_used": 10, "image_bytes_used": 4,
              "input_bytes_used": 3, "bytes_used": 17,
              "state_payload_bytes": 8, "image_payload_bytes": 2,
              "points": [{"state_bytes": 10, "image_bytes": 4,
                          "checkpoint_size": 8, "image_size": 2}]}
    with pytest.raises(ValueError, match="evicted points"):
        benchmark.timeline_accounting(status)
    status["captures_used"] = 1
    result = benchmark.timeline_accounting(status)
    assert result["ring_retained_bytes"] == 17
    assert result["cumulative_state_bytes_including_metadata"] == 10
    assert result["cumulative_state_bytes"] == 8


def test_meter_separates_verification_and_restores_rpc_after_failure():
    def dispatch(method, params=None):
        if method == "state.load":
            raise ValueError("authored failure")
        return {"ok": True}
    session = SimpleNamespace(rpc=SimpleNamespace(call=dispatch))
    result = {}
    with pytest.raises(ValueError, match="authored failure"):
        with benchmark.Meter(session, result) as meter:
            meter.call("capture", "save_anchor_stone", session.rpc.call, "state.save")
            meter.call("verification", "observe", session.rpc.call, "memory.read")
            meter.call("restore", "load_anchor_stone", session.rpc.call, "state.load")
    assert session.rpc.call is dispatch
    assert result["measurements"]["verification"]["backend_rpc_dispatches"] == 1
    assert result["native_component_timings"]["capture_rpc_dispatches"] == 1
    assert result["native_component_timings"]["restore_rpc_dispatches"] == 1
    assert result["native_component_timings"]["recording_caller_api_calls"] == 1


def test_unrecorded_baseline_metrics_exclude_capture_and_verification():
    class Project:
        def __init__(self):
            self.artifacts = []

        def debug_artifacts(self):
            return {"artifacts": self.artifacts}

    class Session:
        def __init__(self, project):
            self.project = project
            self.dos = {"load_segment": 0x1000}
            self.rpc = SimpleNamespace(call=lambda *args, **kwargs: {})
            self.words = []
            self.memory_reads = 0

        def registers(self):
            self.rpc.call("state.get_registers")
            return {"cpu_mode": "real", "general": {}, "segments": {},
                    "instruction_pointer": "0x10e", "flags": "0x202"}

        def memory(self, address, *, length):
            self.rpc.call("memory.read")
            self.memory_reads += 1
            assert address == "1000:0100" and length == 512
            data = bytearray(benchmark.authored_com())
            struct.pack_into("<3H", data, 0x104, len(self.words), sum(self.words) & 0xffff,
                             self.words[-1] if self.words else 0)
            return {"hex": bytes(data).hex()}

        def load_anchor_stone(self, artifact):
            assert artifact == "common-seed"
            self.rpc.call("state.load")
            self.words = []

        def frame_inputs(self, edges):
            self.rpc.call("input.keyboard.frame_edges")
            for edge in edges:
                if edge["pressed"]:
                    self.words.append({"a": 0x1e61, "b": 0x3062, "c": 0x2e63}[edge["key"]])

        def advance_frames(self, *, frames, timeout_ms):
            assert frames == 1
            self.rpc.call("frame.step")
            return {"completed_frames": 1, "frames": [{}]}

        def screenshot(self, name, *, hooks):
            assert hooks is False
            self.rpc.call("video.screenshot")
            self.project.artifacts.append({"id": "verification-png", "size": 123, "kind": "screenshot"})
            return {"artifact": "verification-png", "sha256": "authored-png", "size": 123}

        def save_anchor_stone(self, *args, **kwargs):
            raise AssertionError("Unrecorded baseline must never save a state")

    project = Project()
    session = Session(project)
    initial = benchmark.observe(session)
    session.memory_reads = 0
    result = {}
    benchmark.run_unrecorded_baseline(project, session, "common-seed", initial, 1,
                                     24, benchmark.frame_plan(24), 1000, lambda: None, result)
    assert result["status"] == "passed"
    assert result["history_state_captures"] == result["retained_history_points"] == 0
    assert session.memory_reads == 3  # Seed, aligned S0, final; no per-frame reads.
    assert result["retry_loop_cost"]["forward_caller_api_calls"] == 30  # 24 frames + 6 edges.
    assert result["retry_loop_cost"]["caller_api_calls"] == 32  # Also seed load + alignment.
    components = result["native_component_timings"]
    assert components["advance_rpc_dispatches"] == 24
    assert components["capture_rpc_dispatches"] == components["restore_rpc_dispatches"] == 0
    assert result["storage_after_forward_work"]["new_artifacts"] == 0
    assert result["verification_image_bytes"] == 123
