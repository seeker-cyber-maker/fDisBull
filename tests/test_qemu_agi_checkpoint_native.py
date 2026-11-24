"""Cold cross-session checkpoints for the authored native AGI pilot."""
from __future__ import annotations

import ctypes
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from fdisbull.cli import respond
from fdisbull import cli
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.qemu_agi_checkpoint import ERROR_FORMAT
from test_qemu_agi_public_native import CALLEE_CODE, CODE, RUNTIME_CODE, _project, _runtime_package


def _canonical_continuation(debug):
    """Capture stack return and the caller's subsequent root return."""
    rows = []
    for expected_logic, expected_pc in ((7, 2), (7, 3)):
        result = debug.step()
        position = debug.registers()["logical_position"]
        observed = debug.scene_observe()
        rows.append({"outcome": result["outcome"], "retired": result["retired"],
                     "position": position, "guest": observed["state"]["guest"],
                     "source": observed["state"]["source"],
                     "projection": observed["projection"]})
        if len(rows) == 1:
            assert result["outcome"] == "step"
            assert position["logic_id"] == expected_logic and position["pc"] == expected_pc
        else:
            assert result["outcome"] == "return"
            assert position["logic_id"] == expected_logic and position["pc"] == expected_pc
    return rows


def _child(control_path):
    control = json.loads(Path(control_path).read_text())
    with Project(control["database"]) as project:
        offline = project.debug_state_info(control["artifact"])
        assert offline["sha256"] == control["artifact_sha256"]
        with project.debugger(control["executable"], backend="qemu-agi",
                              agi_runtime_package=control["package"]) as debug:
            assert debug.capabilities["save_states"] is True
            restored = debug.load_state(control["artifact"])
            assert restored["sha256"] == control["artifact_sha256"]
            registers = debug.registers()
            expected_location = {"logic_id": 8, "pc": 7,
                                 "source_sha256": hashlib.sha256(CALLEE_CODE).hexdigest()}
            assert offline["logical_position"] == expected_location
            assert restored["logical_position"] == expected_location
            assert registers["logical_position"] == expected_location
            observation = debug.scene_observe()
            assert observation["state"] == control["saved"]["state"]
            assert observation["events"] == control["saved"]["events"]
            assert observation["projection"] == control["saved"]["projection"]
            assert len(observation["projection"]["visual"]) == 160 * 168 * 2
            assert len(observation["projection"]["priority"]) == 160 * 168 * 2
            continuation = _canonical_continuation(debug)
            assert continuation == control["continuation"]
    print(json.dumps({"passed": True, "continuation_steps": len(continuation)}))


def _checkpoint_executable():
    value = os.environ.get("FDISBULL_QEMU_AGI_CHECKPOINT")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI_CHECKPOINT to the checkpoint-capable native candidate")
    executable = Path(value).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_CHECKPOINT must name an executable native candidate")
    return executable


def _stopped_checkpoint_executable():
    value = os.environ.get("FDISBULL_QEMU_AGI_CHECKPOINT_STOPS")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI_CHECKPOINT_STOPS to a candidate with stopped-state checkpoint support")
    executable = Path(value).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_CHECKPOINT_STOPS must name an executable native candidate")
    return executable


def _corrupt_pending_ticket(checkpoint, pending_storage_hex):
    """Change only the pending effect ticket inside the bounded native runtime section."""
    class NativeHeader(ctypes.Structure):
        _fields_ = [
            ("magic", ctypes.c_char * 8), ("source", ctypes.c_char * 65),
            ("version", ctypes.c_uint32), ("endian", ctypes.c_uint32),
            ("env_size", ctypes.c_uint32), ("event_size", ctypes.c_uint32),
            ("count", ctypes.c_uint32), ("runtime_size", ctypes.c_uint32),
        ]

    header_size = ctypes.sizeof(NativeHeader)
    if len(checkpoint) < header_size:
        raise AssertionError("native AGI checkpoint is shorter than its header")
    header = NativeHeader.from_buffer_copy(checkpoint[:header_size])
    assert header.magic == b"FDBAGIC1" and header.version == 1 and header.endian == 0x01020304
    runtime_start = header_size + header.env_size + header.event_size * header.count
    runtime_end = runtime_start + header.runtime_size
    assert header.runtime_size > 0 and runtime_end == len(checkpoint)

    pending = bytes.fromhex(pending_storage_hex)
    assert len(pending) >= ctypes.sizeof(ctypes.c_uint64)
    section = checkpoint[runtime_start:runtime_end]
    offset = section.find(pending)
    assert offset >= 0 and section.find(pending, offset + 1) == -1, "pending native state must occur exactly once"
    # AgiRuntimePending begins with the uint64_t request ID.
    changed = bytearray(checkpoint)
    changed[runtime_start + offset] ^= 1
    assert changed[runtime_start + offset:runtime_start + offset + len(pending)] != pending
    return bytes(changed)


def _stop_package(directory, code, messages=()):
    path = _runtime_package(directory / "runtime-package.json")
    package = json.loads(path.read_text())
    package["logics"] = [{"id": package["entry_logic"], "code": code.hex(),
                          "sha256": hashlib.sha256(code).hexdigest(), "messages": list(messages)}]
    path.write_text(json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def _runtime_snapshot(debug):
    return {"state": debug.state(), "events": debug.events(),
            "scene": debug.scene_observe(), "registers": debug.registers()}


def _runtime_command(debug, command):
    debug.vm.qmp.call("qom-set", {
        "path": debug.cpu_path,
        "property": "agi-runtime-command",
        "value": json.dumps(command, sort_keys=True, separators=(",", ":")),
    })


def test_checkpoint_restores_callee_stack_and_scene_after_original_owner_closes(tmp_path):
    executable = _checkpoint_executable()
    project, database, _source = _project(tmp_path, RUNTIME_CODE)
    package = _runtime_package(tmp_path / "runtime-package.json")
    control_path = tmp_path / "checkpoint-control.json"
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            assert debug.capabilities["save_states"] is True
            for _ in range(4):  # call LOGIC 8, assignn, load.pic, draw.pic
                assert debug.step()["outcome"] == "step"
            regs = debug.registers()
            assert regs["logical_position"] == {
                "logic_id": 8, "pc": 7,
                "source_sha256": hashlib.sha256(CALLEE_CODE).hexdigest(),
            }
            saved_observation = debug.scene_observe()
            assert saved_observation["state"]["guest"]["logic"] == 8
            assert saved_observation["projection"] is not None
            assert len(saved_observation["projection"]["visual"]) == 160 * 168 * 2
            assert len(saved_observation["projection"]["priority"]) == 160 * 168 * 2
            saved = debug.save_state("agi-cross-session.fdbstate", max_bytes=16 * 1024 * 1024)
            continuation = _canonical_continuation(debug)
            owner = debug.vm.process
        assert owner.poll() is not None, "original native QEMU owner must close before reopening"

    control = {"database": str(database), "package": str(package),
               "executable": str(executable), "artifact": saved["artifact"],
               "artifact_sha256": saved["sha256"], "saved": saved_observation,
               "continuation": continuation}
    control_path.write_text(json.dumps(control, sort_keys=True))
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                "--checkpoint-child", str(control_path)],
                               cwd=str(Path(__file__).resolve().parents[1]),
                               env=environment, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr[-3000:]
    assert json.loads(completed.stdout)["passed"] is True


def test_source_mismatch_and_tampered_checkpoint_leave_current_owner_intact(tmp_path):
    value = os.environ.get("FDISBULL_QEMU_AGI_CHECKPOINT")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI_CHECKPOINT to the checkpoint-capable native candidate")
    executable = Path(value).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_CHECKPOINT must name an executable native candidate")
    project, _database, _source = _project(tmp_path, RUNTIME_CODE)
    package = _runtime_package(tmp_path / "runtime-package.json")
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            saved = debug.save_state("guard.fdbstate", max_bytes=16 * 1024 * 1024)
            artifact = saved["artifact"]
            owner = debug.vm
            original = debug.scene_observe()
            source_row = project.db.execute(
                "SELECT source_bytes FROM binary_info WHERE version=?", (debug.version["id"],)
            ).fetchone()
            source_bytes = bytes(source_row[0])

            # A changed retained LOGIC binding must be rejected before replacing the live owner.
            with project.transaction(True):
                project.db.execute("UPDATE binary_info SET source_bytes=? WHERE version=?",
                                   (bytes((source_bytes[0] ^ 1,)) + source_bytes[1:], debug.version["id"]))
            with pytest.raises(ValueError):
                debug.load_state(artifact)
            with project.transaction(True):
                project.db.execute("UPDATE binary_info SET source_bytes=? WHERE version=?",
                                   (source_bytes, debug.version["id"]))
            assert debug.vm is owner and owner.process.poll() is None
            assert debug.scene_observe() == original

            altered_package = json.loads(package.read_text())
            picture = bytes((1,))
            altered_package["pictures"][0].update(
                data=picture.hex(), sha256=hashlib.sha256(picture).hexdigest())
            other_path = tmp_path / "different-runtime-package.json"
            other_path.write_text(json.dumps(altered_package, sort_keys=True,
                                             separators=(",", ":")) + "\n")
            with project.debugger(str(executable), backend="qemu-agi",
                                  agi_runtime_package=str(other_path)) as other:
                other_owner = other.vm
                with pytest.raises(ValueError, match="identity or payload differs"):
                    other.load_state(artifact)
                assert other.vm is other_owner and other_owner.process.poll() is None
                assert debug.vm is owner and owner.process.poll() is None

            # A forged saved scene digest must fail at staged native readback without adoption.
            metadata_row = project.db.execute(
                "SELECT metadata FROM debug_artifacts WHERE id=?", (artifact,)
            ).fetchone()
            metadata_text = metadata_row[0]
            changed_metadata = json.loads(metadata_text)
            changed_metadata["observation"]["scene_sha256"] = "0" * 64
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET metadata=? WHERE id=?",
                                   (json.dumps(changed_metadata, sort_keys=True), artifact))
            with pytest.raises(DebuggerError, match="readback differs"):
                debug.load_state(artifact)
            assert debug.vm is owner and owner.process.poll() is None
            assert debug.scene_observe() == original
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET metadata=? WHERE id=?",
                                   (metadata_text, artifact))

            # Corrupt one stored payload byte while retaining its recorded digest.
            row = project.db.execute("SELECT data FROM debug_artifacts WHERE id=?", (artifact,)).fetchone()
            data = bytes(row[0])
            changed = bytes((data[0] ^ 1,)) + data[1:]
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET data=? WHERE id=?", (changed, artifact))
            with pytest.raises(ValueError, match="payload hash differs"):
                debug.load_state(artifact)
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?",
                                   (changed, hashlib.sha256(changed).hexdigest(), artifact))
            with pytest.raises((ValueError, DebuggerError)):
                debug.load_state(artifact)
            assert debug.vm is owner and owner.process.poll() is None
            assert debug.scene_observe() == original
            assert debug.step()["outcome"] == "step"
            assert debug.vm is owner and owner.process.poll() is None
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?",
                                   (data, hashlib.sha256(data).hexdigest(), artifact))


def test_raw_logic_checkpoint_restores_into_reopened_project_session(tmp_path):
    executable = _checkpoint_executable()
    project, _database, _source = _project(tmp_path, CODE)
    with project:
        with project.debugger(str(executable), backend="qemu-agi") as debug:
            assert debug.step()["outcome"] == "step"
            saved = debug.save_state("raw-agi-checkpoint.bin", max_bytes=16 * 1024 * 1024)
            original_owner = debug.vm.process
        assert original_owner.poll() is not None
        with project.debugger(str(executable), backend="qemu-agi") as reopened:
            restored = reopened.load_state(saved["artifact"])
            assert restored["verified"] is True
            expected_location = {
                "logic_id": 0, "pc": 4, "source_sha256": hashlib.sha256(CODE).hexdigest(),
            }
            assert project.debug_state_info(saved["artifact"])["logical_position"] == expected_location
            assert restored["logical_position"] == expected_location
            assert reopened.registers()["logical_position"] == {
                **expected_location,
            }
            assert original_owner.poll() is not None


def test_json_checkpoint_methods_save_and_restore_into_a_fresh_run(tmp_path):
    executable = _checkpoint_executable()
    project, database, _source = _project(tmp_path, RUNTIME_CODE)
    with project:
        pass
    package = _runtime_package(tmp_path / "runtime-package.json")
    workspace = DebugWorkspace()
    policy = OutputPolicy(65536, tmp_path / "json-output")

    def invoke(method, **params):
        request = {"method": method, "params": {"project": str(database), **params}}
        with output_policy_context(policy):
            reply = respond(request, debugger=workspace)
        assert reply["ok"], reply
        return reply["result"]

    def materialize(result, name):
        if result.get("format") != "fdisbull-output-ref-1":
            return result
        path = tmp_path / f"{name}.json"
        with output_policy_context(policy):
            exported = respond({"method": "output-export", "params": {
                "artifact": result["artifact"]["id"], "output": str(path)}}, debugger=workspace)
        assert exported["ok"], exported
        payload = json.loads(path.read_text())
        return payload.get("result", payload)

    try:
        first = invoke("debug-launch", executable=str(executable), backend="qemu-agi",
                       agi_runtime_package=str(package))
        first_run = first["run"]
        for _ in range(4):
            assert invoke("debug-step", run=first_run)["outcome"] == "step"
        saved = materialize(invoke("debug-save-state", run=first_run,
                                   name="json-agi-checkpoint.bin", max_bytes=16 * 1024 * 1024), "saved")
        first_session = workspace.sessions[first_run]
        original_owner = first_session.vm
        assert invoke("debug-stop", run=first_run)["process_reaped"] is True

        second = invoke("debug-launch", executable=str(executable), backend="qemu-agi",
                        agi_runtime_package=str(package))
        second_run = second["run"]
        fresh_session = workspace.sessions[second_run]
        fresh_owner = fresh_session.vm
        loaded = materialize(invoke("debug-load-state", run=second_run,
                                    artifact=saved["artifact"]), "loaded")
        assert loaded["verified"] is True
        expected_location = {
            "logic_id": 8, "pc": 7,
            "source_sha256": hashlib.sha256(CALLEE_CODE).hexdigest(),
        }
        assert loaded["logical_position"] == expected_location
        assert fresh_session.registers()["logical_position"] == {
            **expected_location,
        }
        assert fresh_session.scene_observe()["state"]["guest"]["logic"] == 8
        assert original_owner.process.poll() is not None
        assert fresh_owner.process.poll() is not None
        assert fresh_session.vm is not fresh_owner
        assert fresh_session.vm.process.poll() is None
        assert fresh_session.run_id == second_run
        invoke("debug-stop", run=second_run)
    finally:
        workspace.close()


def test_frozen_candidate_without_checkpoint_support_remains_usable(tmp_path):
    value = os.environ.get("FDISBULL_QEMU_AGI_LEGACY")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI_LEGACY to the frozen pre-checkpoint native candidate")
    executable = Path(value).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_LEGACY must name an executable native candidate")
    project, _database, _source = _project(tmp_path, CODE)
    with project:
        with project.debugger(str(executable), backend="qemu-agi") as debug:
            assert debug.capabilities["save_states"] is False
            owner = debug.vm
            with pytest.raises(ValueError, match="checkpoint interface is unavailable"):
                debug.save_state("unsupported.bin")
            assert debug.vm is owner and owner.process.poll() is None
            assert debug.step()["outcome"] == "step"


@pytest.mark.parametrize("code,status,outcome", [
    (bytes((101, 1)), "pending", "pending"),
    (bytes((254, 0xff, 0x7f)), "fault", "fault"),
    (bytes((134, 1, 0)), "quit", "quit"),
])
def test_runtime_stops_restore_cold_and_remain_stable_across_step_run_and_resave(tmp_path, monkeypatch,
                                                                                  code, status, outcome):
    executable = _stopped_checkpoint_executable()
    project, _database, _source = _project(tmp_path, code)
    package = _stop_package(tmp_path, code, ["Native timed checkpoint window"])
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as original:
            assert original.capabilities["save_states"] is True
            if status == "pending":
                _runtime_command(original, {"action": "seed", "variables": {"21": 2}})
            assert original.step()["outcome"] == outcome
            if status == "pending":
                after_print = original.state()["guest"]
                assert after_print["window_open"] == 1
                assert after_print["window_ticks_remaining"] == 20
                _runtime_command(original, {"action": "clock", "ticks": 7})
            stopped = _runtime_snapshot(original)
            assert stopped["state"]["guest"]["status"] == status
            if status == "pending":
                assert stopped["state"]["guest"].get("pending_effect") is not None
                assert stopped["state"]["guest"]["window_ticks_remaining"] == 13
                assert stopped["state"]["guest"]["clock_ticks"] == 7
                clock_event = stopped["events"]["events"][-1]
                assert clock_event["channel"] == "scene" and clock_event["opcode"] == 256
                assert clock_event["size"] == 0 and clock_event["bytes"] == []
            elif status == "fault":
                assert stopped["state"]["guest"].get("fault") is not None
            first_run = original.run_id
            initial_artifacts = project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (first_run,)
            ).fetchone()[0]
            first_save = original.save_state(f"{status}-first.bin", max_bytes=16 * 1024 * 1024)
            first_observation = project.debug_state_info(first_save["artifact"])["metadata"]["observation"]
            assert first_observation["runtime_stop"] == {
                "status": status,
                "pending_effect": stopped["state"]["guest"].get("pending_effect"),
                "fault": stopped["state"]["guest"].get("fault"),
            }
            assert project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (first_run,)
            ).fetchone()[0] == initial_artifacts + 1
            first_owner = original.vm.process
        assert first_owner.poll() is not None, "original native owner must close before cold restore"

        def unexpected_native_execute(*_args, **_kwargs):
            raise AssertionError("terminal AGI stop attempted to issue a native execution packet")
        monkeypatch.setattr(GDBRemote, "execute", unexpected_native_execute)

        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as restored:
            assert restored.run_id != first_run
            cold = restored.load_state(first_save["artifact"])
            assert cold["verified"] is True
            restored_snapshot = _runtime_snapshot(restored)
            assert restored_snapshot == stopped
            if status == "pending":
                assert restored_snapshot["state"]["guest"]["window_ticks_remaining"] == 13
                assert restored_snapshot["events"]["events"][-1] == clock_event
            restored_owner = restored.vm
            for operation in (restored.step, restored.run):
                result = operation()
                assert result["outcome"] == outcome
                assert result["retired"] == 0
                assert result["registers"] == stopped["registers"]
                assert restored.state() == stopped["state"]
                assert restored.events() == stopped["events"]
                assert restored.scene_observe() == stopped["scene"]
                assert restored.vm is restored_owner and restored_owner.process.poll() is None

            second_save = restored.save_state(f"{status}-resaved.bin", max_bytes=16 * 1024 * 1024)
            assert second_save["sha256"] == first_save["sha256"]
            assert second_save["artifact"] != first_save["artifact"]
            second_observation = project.debug_state_info(second_save["artifact"])["metadata"]["observation"]
            assert second_observation["runtime_stop"] == first_observation["runtime_stop"]
            assert project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (restored.run_id,)
            ).fetchone()[0] == 1
            second_run = restored.run_id
            second_owner = restored.vm.process
        assert second_owner.poll() is not None

        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as resaved:
            assert resaved.run_id != second_run
            again = resaved.load_state(second_save["artifact"])
            assert again["verified"] is True
            assert _runtime_snapshot(resaved) == stopped
            for operation in (resaved.step, resaved.run):
                result = operation()
                assert result["outcome"] == outcome
                assert result["retired"] == 0
                assert resaved.state() == stopped["state"]
                assert resaved.events() == stopped["events"]
                assert resaved.scene_observe() == stopped["scene"]


def test_corrupt_pending_ticket_is_rejected_by_native_setter_without_replacing_owner(tmp_path):
    executable = _stopped_checkpoint_executable()
    code = bytes((29, 0))  # show.pri.screen: a pending ACK with no operands
    project, _database, _source = _project(tmp_path, code)
    package = _stop_package(tmp_path, code)
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            assert debug.capabilities["save_states_runtime_stops"] is True
            assert debug.step()["outcome"] == "pending"
            before = {
                "state": debug.state(), "events": debug.events(),
                "scene": debug.scene_observe(), "registers": debug.registers(),
            }
            pending_storage_hex = before["state"]["guest"]["pending_storage_hex"]
            saved = debug.save_state("pending-ticket.fdbstate", max_bytes=16 * 1024 * 1024)
            row = project.db.execute(
                "SELECT data FROM debug_artifacts WHERE id=?", (saved["artifact"],)
            ).fetchone()
            original_data = bytes(row[0])
            corrupted_data = _corrupt_pending_ticket(original_data, pending_storage_hex)
            with project.transaction(True):
                project.db.execute("UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?",
                                   (corrupted_data, hashlib.sha256(corrupted_data).hexdigest(),
                                    saved["artifact"]))

            owner = debug.vm
            artifacts_before = project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (debug.run_id,)
            ).fetchone()[0]
            with pytest.raises(DebuggerError) as refused:
                debug.load_state(saved["artifact"])
            assert "invalid or unsupported runtime checkpoint" in str(refused.value)
            assert debug.vm is owner and owner.process.poll() is None
            assert {"state": debug.state(), "events": debug.events(),
                    "scene": debug.scene_observe(), "registers": debug.registers()} == before
            assert project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (debug.run_id,)
            ).fetchone()[0] == artifacts_before


def test_v1_checkpoint_candidate_still_refuses_pending_capture_without_owner_loss(tmp_path):
    value = os.environ.get("FDISBULL_QEMU_AGI_CHECKPOINT_V1")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI_CHECKPOINT_V1 to the v1-only native candidate")
    executable = Path(value).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_CHECKPOINT_V1 must name an executable native candidate")
    code = bytes((29, 0))
    project, _database, _source = _project(tmp_path, code)
    package = _stop_package(tmp_path, code)
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            assert debug.capabilities["save_states"] is True
            assert debug.capabilities["save_states_runtime_stops"] is False
            assert debug.step()["outcome"] == "pending"
            before = {"state": debug.state(), "events": debug.events(),
                      "scene": debug.scene_observe(), "registers": debug.registers()}
            owner = debug.vm
            with pytest.raises(DebuggerError):
                debug.save_state("v1-pending-refusal.fdbstate")
            assert debug.vm is owner and owner.process.poll() is None
            assert {"state": debug.state(), "events": debug.events(),
                    "scene": debug.scene_observe(), "registers": debug.registers()} == before


@pytest.mark.parametrize("body,reply,answer", [
    (bytes((101, 1)), "ack", {"accepted": True}),
    (bytes((115, 0, 1, 0, 0, 10)), "text", {"accepted": True, "text": "ok"}),
    (bytes((118, 1, 3)), "number", {"accepted": True, "number": 42}),
    (bytes((134, 0)), "choice", {"accepted": True}),
    (bytes((156, 2, 157, 3, 5, 158, 161)), "menu", {"accepted": True, "number": 5}),
    (bytes((126,)), "restore", {"accepted": False}),
])
def test_restored_pending_ticket_completes_exactly_once(tmp_path, body, reply, answer, monkeypatch):
    executable = _stopped_checkpoint_executable()
    code = bytes((29,)) + body + bytes((0,))
    project, _, _ = _project(tmp_path, code)
    package = _stop_package(tmp_path, code, ["Hello", "Menu", "Item"])
    with project:
        with project.debugger(str(executable), backend="qemu-agi", agi_runtime_package=str(package)) as original:
            assert original.capabilities["save_states_runtime_stops"] is True
            _runtime_command(original, {"action": "seed", "flags": {"14": 1}})
            assert original.step()["outcome"] == "pending"
            assert original.state()["guest"]["pending_effect"]["id"] == 1
            first_ticket = original.state()["guest"]["pending_effect"]["id"]
            original.reply_host(first_ticket, accepted=False)
            for _ in range(8):
                outcome = original.step()["outcome"]
                if outcome == "pending":
                    break
                assert outcome == "step"
            else:
                pytest.fail("Expected a second pending request")
            before = original.state()
            pending = before["guest"]["pending_effect"]
            assert pending["id"] == 2 and pending["reply"] == reply
            saved = original.save_state(f"{reply}.bin")
            assert saved["metadata"]["observation"]["runtime_stop"]["pending_effect"] == pending
            owner = original.vm.process
        assert owner.poll() is not None

        with project.debugger(str(executable), backend="qemu-agi", agi_runtime_package=str(package)) as restored:
            assert restored.load_state(saved["artifact"])["verified"] is True
            assert restored.state() == before
            # The restored owner is the only authority allowed to answer this
            # durable request.  Use the public host-reply API; the private QMP
            # runtime command remains a fixture-seeding mechanism only.
            ticket = pending["id"]
            with pytest.raises((TypeError, ValueError, DebuggerError)):
                restored.reply_host(ticket, accepted="yes")
            assert restored.state() == before
            with pytest.raises((ValueError, DebuggerError)):
                restored.reply_host(first_ticket, accepted=True)
            assert restored.state() == before
            if reply == "menu":
                owner = restored.vm
                with pytest.raises(ValueError):
                    restored.reply_host(ticket, accepted=True, number=4)
                assert restored.vm is owner and owner.process.poll() is None
                assert restored.state() == before
            owner = restored.vm
            gdb_calls = []
            with monkeypatch.context() as blocker:
                blocker.setattr(owner.gdb, "execute", lambda *args, **kwargs: gdb_calls.append(args))
                reply_result = restored.reply_host(ticket, **answer)
                assert reply_result["verified"] is True
                with pytest.raises((ValueError, DebuggerError)):
                    restored.reply_host(ticket, **answer)
                assert gdb_calls == []
            assert reply_result["format"] == "fdisbull-qemu-agi-host-reply-1"
            assert reply_result["ticket"] == ticket
            assert reply_result["before"] == {
                "status": before["guest"]["status"],
                "pending_effect": pending,
                "retired": before["guest"]["retired"],
                "logic": before["guest"]["logic"],
                "pc": before["guest"]["pc"],
            }
            assert reply_result["after"] == {
                "status": "quit" if reply == "choice" else "ready",
                "pending_effect": None,
                "retired": before["guest"]["retired"] + 1,
                "logic": before["guest"]["logic"],
                "pc": pending["next_pc"],
            }
            assert reply_result["accepted"] is answer["accepted"]
            assert reply_result["verified"] is True
            completed = restored.state()
            assert completed["guest"]["pending_effect"] is None
            assert completed["guest"]["retired"] == before["guest"]["retired"] + 1
            assert completed["guest"]["status"] == ("quit" if reply == "choice" else "ready")
            # A saved checkpoint is an independent branch: replaying its
            # pending ticket is valid after rewind, even though the prior
            # branch already consumed that ticket once.
            prior_owner = restored.vm.process
            assert restored.load_state(saved["artifact"])["verified"] is True
            assert prior_owner.poll() is not None
            assert restored.state() == before
            branch_reply = restored.reply_host(ticket, **answer)
            assert branch_reply["after"] == reply_result["after"]
            assert restored.state() == completed
            if reply == "choice":
                quit_saved = restored.save_state("confirmed-quit.bin")
                previous_owner = restored.vm.process
                assert restored.load_state(quit_saved["artifact"])["verified"] is True
                assert previous_owner.poll() is not None
                assert restored.state() == completed
                for operation in (restored.step, restored.run):
                    result = operation()
                    assert result["outcome"] == "quit" and result["retired"] == 0
                    assert restored.state() == completed


@pytest.mark.parametrize("method,receipt", [
    ("debug-save-state", {"format": ERROR_FORMAT, "artifact": {"artifact": "saved-id"},
                          "do_not_replay": True, "disposition": "publication completed"}),
    ("debug-load-state", {"format": ERROR_FORMAT, "restore": {"artifact": "saved-id"},
                          "do_not_replay": True, "owner_adopted": False,
                          "owner_closed": False, "disposition": "restore failed"}),
])
def test_cli_returns_typed_agi_checkpoint_failure_receipt(monkeypatch, method, receipt):
    error = RuntimeError("checkpoint operation failed with a durable receipt")
    error.result = receipt

    def fail(_method, _params, _debugger):
        raise error

    monkeypatch.setattr(cli, "invoke", fail)
    reply = respond({"id": 19, "method": method, "params": {"run": "synthetic-run"}})
    assert reply["ok"] is False
    assert reply["id"] == 19
    assert reply["error"]["type"] == "RuntimeError"
    assert reply["error"]["result"] == receipt


def test_json_reply_uses_the_restored_run_and_consumes_one_ticket(tmp_path):
    executable = _stopped_checkpoint_executable()
    code = bytes((118, 1, 3, 0))  # get.num(message 1, v3), return
    project, database, _ = _project(tmp_path, code)
    with project:
        package = _stop_package(tmp_path, code, ["Choose a number"])
    workspace = DebugWorkspace()
    policy = OutputPolicy(1024 * 1024, tmp_path / "json-output")

    def call(method, **params):
        with output_policy_context(policy):
            return respond({"id": 23, "method": method, "params": params},
                           default_project=str(database), debugger=workspace)

    def invoke(method, **params):
        response = call(method, **params)
        assert response["ok"], response
        return response["result"]

    launch = dict(executable=str(executable), backend="qemu-agi", agi_runtime_package=str(package))
    try:
        first = invoke("debug-launch", **launch)["run"]
        assert invoke("debug-step", run=first)["outcome"] == "pending"
        saved = invoke("debug-save-state", run=first, name="number.bin")
        assert invoke("debug-stop", run=first)["process_reaped"]
        second = invoke("debug-launch", **launch)["run"]
        assert second != first
        stop = invoke("debug-load-state", run=second, artifact=saved["artifact"])["observation"]["runtime_stop"]
        answer = dict(run=second, ticket=stop["pending_effect"]["id"], accepted=True, number=42)
        receipt = invoke("debug-agi-reply", **answer)
        assert receipt["verified"] and receipt["after"]["retired"] == receipt["before"]["retired"] + 1
        assert receipt["after"]["pc"] == 3
        duplicate = call("debug-agi-reply", **answer)
        assert duplicate["id"] == 23 and not duplicate["ok"]
        assert workspace.sessions[second].state()["guest"]["variables"][3] == 42
    finally:
        workspace.close()


def test_public_restore_reply_uses_bound_guest_snapshot_without_resuming(tmp_path):
    executable = _stopped_checkpoint_executable()
    code = bytes((3, 5, 1, 126, 0))  # assignn(v5, 1), restore.game, return
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    project, _, _ = _project(target_dir, code)
    target_package = _stop_package(target_dir, code)
    decoy_dir = tmp_path / "decoy"
    decoy_dir.mkdir()
    decoy_code = bytes((3, 5, 2, 126, 0))
    decoy_project, _, _ = _project(decoy_dir, decoy_code)
    decoy_package = _stop_package(decoy_dir, decoy_code)
    with project, decoy_project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(target_package)) as debug:
            assert debug.capabilities["agi_host_replies"] is True
            assert debug.step()["outcome"] == "step"
            saved_guest = debug.state()["guest"]
            assert saved_guest["pc"] == 3
            target_snapshot = debug.vm.qmp.call("qom-get", {
                "path": debug.cpu_path, "property": "agi-runtime-snapshot-hex"})
            assert isinstance(target_snapshot, str) and target_snapshot
            assert debug.step()["outcome"] == "pending"
            before = debug.state()
            pending = before["guest"]["pending_effect"]
            assert pending["reply"] == "restore"
            ticket = pending["id"]
            owner = debug.vm

            with decoy_project.debugger(str(executable), backend="qemu-agi",
                                        agi_runtime_package=str(decoy_package)) as decoy:
                decoy_snapshot = decoy.vm.qmp.call("qom-get", {
                    "path": decoy.cpu_path, "property": "agi-runtime-snapshot-hex"})
            assert isinstance(decoy_snapshot, str) and decoy_snapshot != target_snapshot
            with pytest.raises(DebuggerError) as rejected:
                debug.reply_host(ticket, accepted=True, snapshot_hex=decoy_snapshot)
            assert rejected.value.result["disposition"] == "native rejection"
            assert rejected.value.result["do_not_replay"] is False
            assert debug.vm is owner and owner.process.poll() is None
            assert debug.state() == before

            receipt = debug.reply_host(ticket, accepted=True, snapshot_hex=target_snapshot)
            restored = debug.state()["guest"]
            assert receipt["reply_type"] == "restore" and receipt["verified"] is True
            assert receipt["snapshot"]["size"] > 0
            assert restored["status"] in ("ready", "return")
            assert restored["pending_effect"] is None
            assert restored["pc"] == saved_guest["pc"]
            assert restored["logic"] == saved_guest["logic"]
            assert restored["retired"] == saved_guest["retired"]
            assert restored["flags"][12] == 1
            assert receipt["after"]["restored_flag"] == 1
            assert debug.vm is owner and owner.process.poll() is None
            with pytest.raises((ValueError, DebuggerError)):
                debug.reply_host(ticket, accepted=True, snapshot_hex=target_snapshot)
            assert debug.state()["guest"] == restored


def test_host_reply_lost_ack_is_not_replayed_and_records_uncertainty(tmp_path):
    executable = _stopped_checkpoint_executable()
    code = bytes((101, 1, 0))  # print, then return
    project, _, _ = _project(tmp_path, code)
    package = _stop_package(tmp_path, code, ["Press a key"])
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            assert debug.step()["outcome"] == "pending"
            pending = debug.state()["guest"]["pending_effect"]
            ticket = pending["id"]
            owner = debug.vm
            original_call = owner.qmp.call
            setters = []
            committed = []

            def commit_then_drop_ack(command, *args, **kwargs):
                if (command == "qom-set" and args and
                        args[0].get("property") == "agi-runtime-command"):
                    setters.append(args[0]["value"])
                    original_call(command, *args, **kwargs)
                    committed.append(debug._state()["guest"])
                    raise TimeoutError("injected lost host-reply acknowledgement")
                return original_call(command, *args, **kwargs)

            owner.qmp.call = commit_then_drop_ack
            with pytest.raises(TimeoutError) as uncertain:
                debug.reply_host(ticket, accepted=True)
            assert len(setters) == 1
            assert committed and committed[0]["pending_effect"] is None
            assert uncertain.value.result["do_not_replay"] is True
            assert uncertain.value.result["owner_closed"] is True
            assert owner.process.poll() is not None
            history = project.db.execute(
                "SELECT operation,evidence FROM debug_events WHERE run=? ORDER BY sequence",
                (debug.run_id,),
            ).fetchall()
            evidence = [(operation, json.loads(payload)) for operation, payload in history]
            assert any(operation == "agi-host-reply-uncertain" and
                       record.get("do_not_replay") is True
                       for operation, record in evidence)
            assert not any(operation == "agi-host-reply" for operation, _ in evidence)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--checkpoint-child":
    _child(sys.argv[2])
