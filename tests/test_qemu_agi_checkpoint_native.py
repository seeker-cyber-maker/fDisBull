"""Cold cross-session checkpoints for the authored native AGI pilot."""
from __future__ import annotations

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
    (bytes((29, 0)), "pending", "pending"),
    (bytes((254, 0xff, 0x7f)), "fault", "fault"),
    (bytes((134, 1, 0)), "quit", "quit"),
])
def test_runtime_pending_fault_and_quit_refuse_checkpoint_without_mutation(tmp_path, code, status,
                                                                             outcome):
    executable = _checkpoint_executable()
    project, _database, _source = _project(tmp_path, code)
    package = _runtime_package(tmp_path / "runtime-package.json")
    package_value = json.loads(package.read_text())
    logic = {"id": 7, "code": code.hex(), "sha256": hashlib.sha256(code).hexdigest(), "messages": []}
    package_value["entry_logic"] = 7
    package_value["logics"] = [logic]
    package.write_text(json.dumps(package_value, sort_keys=True, separators=(",", ":")) + "\n")
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as debug:
            assert debug.step()["outcome"] == outcome
            before = debug.scene_observe()
            assert before["state"]["guest"]["status"] == status
            owner = debug.vm
            artifact_count = project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (debug.run_id,)
            ).fetchone()[0]
            with pytest.raises(DebuggerError):
                debug.save_state(f"{status}.bin")
            after = debug.scene_observe()
            assert after == before
            assert debug.vm is owner and owner.process.poll() is None
            assert project.db.execute(
                "SELECT COUNT(*) FROM debug_artifacts WHERE run=?", (debug.run_id,)
            ).fetchone()[0] == artifact_count == 0


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

if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--checkpoint-child":
    _child(sys.argv[2])
