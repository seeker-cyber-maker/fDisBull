"""Owned AGI scene acceptance with independently authored actor expectations.

Native cases require an explicit FDISBULL_QEMU_AGI executable; an absent value
skips visibly and an invalid configured path fails. Inputs are authored raw
bytecode. These checks do not use a production decoder or scene consumer to
derive expected positions, instruction locations, gaps, or failure receipts.
"""
from copy import deepcopy
from functools import partial
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from fdisbull_core.agi_scene import SceneInputError


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native" / "qemu-agi"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_harness = _load("qemu_agi_scene_native_harness", NATIVE / "harness.py")
_scene = _load("qemu_agi_scene_adapter", NATIVE / "scene_harness.py")
QemuAGI = partial(_harness.QemuAGI,
                 evidence_dir=os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE"))
AGISceneHarness = _scene.AGISceneHarness
PROFILE = "agi-2917-scalar-position-pilot-1"
# Literal independent input: positions at PCs 0/4/8/12/16, then return at 20.
# PC 8 repeats the unchanged actor-zero position and emits no scene change.
POSITIONS = bytes.fromhex("25000a1425011e2825000a142500323c2501465000")
OUT_AND_BACK = bytes.fromhex("25000a142500000000")


@pytest.fixture(scope="module")
def native_binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("native scene acceptance requires explicit FDISBULL_QEMU_AGI")
    path = Path(configured).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI must name an executable candidate binary")
    return path


def assert_positions(view, expected):
    assert view["schema"] == "fdisbull-agi-scene-view-1"
    assert len(view["actors"]) == 16
    actual = [{key: actor[key] for key in ("id", "x", "y", "prev_x", "prev_y")}
              for actor in view["actors"]]
    wanted = []
    for index in range(16):
        x, y = expected.get(index, (0, 0))
        wanted.append({"id": index, "x": x, "y": y, "prev_x": x, "prev_y": y})
    assert actual == wanted


def assert_changes(update, expected):
    assert update["status"] == ("applied" if expected else "unchanged")
    assert update["needs_resync"] is False and update["reason"] is None
    assert [(item["actor"], item["after"]["x"], item["after"]["y"], item["pc"])
            for item in update["changes"]] == expected
    for item in update["changes"]:
        assert item["kind"] == "position" and item["opcode"] == 37
        assert item["bytes"] == [37, item["actor"], item["after"]["x"], item["after"]["y"]]
        assert item["next_pc"] == item["pc"] + 4


def assert_source(view, code, session):
    assert view["source"] == {
        "sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
        "logic_id": 0, "profile": PROFILE,
    }
    assert view["session_id"] == session


@pytest.mark.parametrize("mask", [2, 3])
def test_native_scene_and_both_project_only_committed_positions(native_binary, mask):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        assert scene.attachment["update"] == {
            "status": "attached", "needs_resync": False,
            "reason": "initial_attachment", "changes": [],
        }
        assert_positions(scene.view(), {})
        assert all(actor["witness"] is None for actor in scene.view()["actors"])
        scene.configure(mask=mask, capacity=64, step_budget=2)
        first = scene.run()
        assert_changes(first["update"], [(0, 10, 20, 0), (1, 30, 40, 4)])
        assert_positions(first["view"], {0: (10, 20), 1: (30, 40)})
        second = scene.run()
        assert_changes(second["update"], [(0, 50, 60, 12)])
        assert_positions(second["view"], {0: (50, 60), 1: (30, 40)})
        third = scene.run()
        assert_changes(third["update"], [(1, 70, 80, 16)])
        assert_positions(third["view"], {0: (50, 60), 1: (70, 80)})
        assert_source(third["view"], POSITIONS, scene.session_id)
        assert third["view"]["guest"]["status"] == "return"
        assert third["view"]["checkpoint"]["retired"] == 6
        assert third["view"]["actors"][0]["witness"]["pc"] == 12
        assert third["view"]["actors"][1]["witness"]["pc"] == 16
        assert third["view"]["coverage"]["history_complete_since_attach"] is True
        assert third["view"]["coverage"]["gap_count"] == 0
        assert third["view"]["coverage"]["scene_enabled"] is True
        state, records = vm.state(), vm.events()["events"]
        assert state["observation"]["count"] == (4 if mask == 2 else 10)
        assert [r["pc"] for r in records if r["kind"] == "position"] == [0, 4, 12, 16]
        assert_changes(scene.capture()["update"], [])
        third["view"]["actors"][0]["witness"]["after"]["x"] = 255
        assert scene.view()["actors"][0]["witness"]["after"]["x"] == 50


@pytest.mark.parametrize("mask", [2, 3])
@pytest.mark.parametrize("capacity", [0, 64])
def test_native_attach_after_work_anchors_snapshot_without_replaying_history(
        native_binary, mask, capacity):
    with QemuAGI(native_binary, POSITIONS) as vm:
        vm.configure(mask=mask, capacity=capacity, step_budget=1)
        state = vm.run()
        scene = AGISceneHarness(vm)
        assert scene.attachment["update"]["changes"] == []
        assert_positions(scene.view(), {0: (10, 20)})
        assert all(actor["witness"] is None for actor in scene.view()["actors"])
        assert scene.view()["checkpoint"]["eligible"] == state["observation"]["eligible"]
        assert scene.view()["coverage"]["history_complete_since_attach"] is True
        assert_changes(scene.capture()["update"], [])
        result = scene.run()
        assert_positions(result["view"], {0: (10, 20), 1: (30, 40)})
        if capacity:
            assert_changes(result["update"], [(1, 30, 40, 4)])
            assert result["view"]["actors"][0]["witness"] is None
            assert result["view"]["coverage"]["history_complete_since_attach"] is True
        else:
            assert result["update"]["status"] == "resynced"
            assert result["update"]["reason"] == "scene_records_lost"
            assert result["view"]["coverage"]["history_complete_since_attach"] is False


def test_native_each_attachment_has_its_own_uuid_without_owning_vm(native_binary):
    with QemuAGI(native_binary, POSITIONS) as vm:
        process = vm.process
        first, second = AGISceneHarness(vm), AGISceneHarness(vm)
        assert first.session_id != second.session_id
        assert uuid.UUID(first.session_id).version == uuid.UUID(second.session_id).version == 4
        assert first.vm is second.vm is vm
        assert_source(first.view(), POSITIONS, first.session_id)
        assert_source(second.view(), POSITIONS, second.session_id)
        first.configure(mask=2, capacity=16, step_budget=1)
        first.run()
        assert vm.process is process and process.poll() is None
        assert_positions(second.capture()["view"], {0: (10, 20)})
    assert process.poll() is not None


@pytest.mark.parametrize("mask", [2, 3])
@pytest.mark.parametrize("capacity", [0, 1])
def test_native_overflow_resynchronizes_current_scene_and_keeps_gap_visible(
        native_binary, mask, capacity):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=mask, capacity=capacity, step_budget=2)
        result = scene.run()
        assert result["update"] == {
            "status": "resynced", "needs_resync": False,
            "reason": "scene_records_lost", "changes": [],
        }
        assert_positions(result["view"], {0: (10, 20), 1: (30, 40)})
        assert result["view"]["coverage"]["gap_count"] == 1
        assert result["view"]["coverage"]["history_complete_since_attach"] is False
        assert result["view"]["coverage"]["last_gap"]["reason"] == "scene_records_lost"
        assert all(actor["witness"] is None for actor in result["view"]["actors"])
        assert_changes(scene.capture()["update"], [])
        assert scene.view()["coverage"]["gap_count"] == 1


@pytest.mark.parametrize("mask", [0, 1])
def test_native_disabled_out_and_back_requires_resync_even_when_positions_match(native_binary, mask):
    with QemuAGI(native_binary, OUT_AND_BACK) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=mask, capacity=16, step_budget=8)
        before = scene.view()
        result = scene.run()
        assert_positions(before, {})
        assert_positions(result["view"], {})
        assert result["view"]["actors"] == before["actors"]
        assert result["update"]["status"] == "resynced"
        assert result["update"]["reason"] == "observation_disabled"
        assert result["view"]["coverage"]["history_complete_since_attach"] is False
        assert result["view"]["coverage"]["gap_count"] == 1
        assert vm.state()["guest"]["retired"] == 3
        assert vm.state()["observation"]["count"] == (3 if mask else 0)


@pytest.mark.parametrize("operation", ["clear_events", "restart"])
def test_native_epoch_changes_resync_promptly_and_discard_old_witnesses(native_binary, operation):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=64, step_budget=2)
        first = scene.run()
        assert first["view"]["actors"][0]["witness"] is not None
        result = getattr(scene, operation)()
        assert_changes(result["pending_update"], [])
        assert result["update"]["status"] == "resynced"
        assert result["update"]["reason"] == "epoch_changed"
        assert result["view"]["checkpoint"]["epoch"] == first["view"]["checkpoint"]["epoch"] + 1
        assert all(actor["witness"] is None for actor in result["view"]["actors"])
        expected = {} if operation == "restart" else {0: (10, 20), 1: (30, 40)}
        assert_positions(result["view"], expected)
        assert result["view"]["coverage"]["gap_count"] == 1
        following = scene.run()
        assert following["view"]["coverage"]["gap_count"] == 1
        assert following["view"]["coverage"]["history_complete_since_attach"] is False
        expected_changes = [(0, 10, 20, 0), (1, 30, 40, 4)] if operation == "restart" else [(0, 50, 60, 12)]
        assert_changes(following["update"], expected_changes)


@pytest.mark.parametrize("operation", ["configure", "clear_events", "restart"])
def test_native_controls_return_pending_changes_before_modifying_checkpoint(native_binary, operation):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.run()
        result = scene.configure(capacity=32) if operation == "configure" else getattr(scene, operation)()
        assert_changes(result["pending_update"], [(0, 10, 20, 0)])
        assert_positions(result["view"], {} if operation == "restart" else {0: (10, 20)})
        if operation == "configure":
            assert_changes(result["update"], [])
            assert result["view"]["coverage"]["history_complete_since_attach"] is True
        else:
            assert result["update"]["status"] == "resynced"
            assert result["update"]["reason"] == "epoch_changed"


def test_native_optional_run_budget_preserves_preparation_and_prior_changes(native_binary):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.run()
        generation = vm.state()["observation"]["control_generation"]
        result = scene.run(step_budget=1)
        assert_changes(result["preparation"]["pending_update"], [(0, 10, 20, 0)])
        assert_changes(result["preparation"]["update"], [])
        assert_positions(result["preparation"]["view"], {0: (10, 20)})
        assert_changes(result["update"], [(1, 30, 40, 4)])
        assert_positions(result["view"], {0: (10, 20), 1: (30, 40)})
        assert result["view"]["checkpoint"]["control_generation"] == generation + 1
        assert result["view"]["coverage"]["history_complete_since_attach"] is True


def test_native_uncheckpointed_control_generation_across_work_requires_resync(native_binary):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.configure(mask=2)
        vm.run()
        result = scene.capture()
        assert result["update"]["status"] == "resynced"
        assert result["update"]["reason"] == "control_changed_during_execution"
        assert_positions(result["view"], {0: (10, 20)})
        assert result["view"]["coverage"]["history_complete_since_attach"] is False
        assert_changes(scene.capture()["update"], [])
        assert scene.view()["coverage"]["gap_count"] == 1


@pytest.mark.parametrize("terminal", [0, 9])
def test_native_budget_resume_terminal_and_sticky_stops_preserve_projection(native_binary, terminal):
    code = bytes([37, 0, 10, 20, terminal])
    with QemuAGI(native_binary, code) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        first = scene.run()
        assert_changes(first["update"], [(0, 10, 20, 0)])
        assert first["view"]["guest"]["status"] == "budget"
        second = scene.run()
        assert_changes(second["update"], [])
        assert_positions(second["view"], {0: (10, 20)})
        assert second["view"]["guest"]["status"] == ("return" if terminal == 0 else "fault")
        if terminal:
            assert second["view"]["guest"]["fault"]["opcode"] == terminal
            assert second["view"]["guest"]["fault"]["pc"] == 4
        else:
            assert second["view"]["guest"]["fault"] is None
        third = scene.run()
        assert_changes(third["update"], [])
        assert third["view"]["actors"] == second["view"]["actors"]
        assert third["view"]["guest"] == second["view"]["guest"]
        assert third["view"]["checkpoint"]["retired"] == second["view"]["checkpoint"]["retired"]
        assert third["view"]["checkpoint"]["invocation"] > second["view"]["checkpoint"]["invocation"]
        assert third["view"]["coverage"]["history_complete_since_attach"] is True
        assert vm.state()["run"]["retired"] == 0


def test_native_changing_capture_bracket_raises_without_mutating_projection(native_binary, monkeypatch):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        before, events, calls = scene.view(), vm.events, 0

        def advance_during_capture():
            nonlocal calls
            calls += 1
            vm.run()
            return events()

        with monkeypatch.context() as changed:
            changed.setattr(vm, "events", advance_during_capture)
            with pytest.raises(SceneInputError, match="changed during capture"):
                scene.capture()
        assert calls == 1
        assert scene.view() == before
        assert vm.state()["guest"]["retired"] == 1
        assert_changes(scene.capture()["update"], [(0, 10, 20, 0)])


def test_native_wrong_source_records_raise_instead_of_resynchronizing(native_binary, monkeypatch):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        before = scene.view()
        vm.run()
        records = vm.events()
        records["source"]["sha256"] = "f" * 64
        with monkeypatch.context() as changed:
            changed.setattr(vm, "events", lambda: deepcopy(records))
            with pytest.raises(SceneInputError, match="source"):
                scene.capture()
        assert scene.view() == before
        assert_changes(scene.capture()["update"], [(0, 10, 20, 0)])


@pytest.mark.parametrize("option,value", [
    ("--mask", "4"), ("--capacity", "-1"), ("--capacity", "65537"),
    ("--step-budget", "0"), ("--step-budget", "4097"),
    ("--timeout", "nan"), ("--timeout", "inf"), ("--timeout", "0.01"), ("--timeout", "31"),
])
def test_scene_demo_rejects_unbounded_controls_before_creating_output(tmp_path, option, value):
    output = tmp_path / "not-created.json"
    with pytest.raises(SystemExit) as failure:
        _scene.main(["--binary", str(tmp_path / "absent"), "--output", str(output), option, value])
    assert failure.value.code == 2 and not output.exists()


def test_scene_demo_refuses_to_overwrite_existing_evidence(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("previous evidence\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="new output path"):
        _scene.main(["--binary", str(tmp_path / "absent"), "--output", str(output)])
    assert output.read_text(encoding="utf-8") == "previous evidence\n"


def test_scene_demo_invalid_binary_fails_with_receipt_without_launching(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(NATIVE))
    output = tmp_path / "failed.json"
    with pytest.raises(ValueError, match="explicit executable"):
        _scene.main(["--binary", str(tmp_path / "absent"), "--output", str(output)])
    report = json.loads(output.read_text())
    assert report["status"] == "failed" and report["captures"] == []
    assert report["failure"]["type"] == "ValueError"


def test_native_scene_cli_finishes_bounded_authored_program_with_overflow(native_binary, tmp_path):
    output = tmp_path / "scene.json"
    env = dict(os.environ)
    core = str(ROOT / "packages" / "fdisbull-core" / "src")
    env["PYTHONPATH"] = core + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, str(NATIVE / "scene_harness.py"), "--binary", str(native_binary),
         "--output", str(output), "--mask", "3", "--capacity", "0", "--step-budget", "1"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert report["schema"] == "fdisbull-agi-scene-demo-1" and report["status"] == "completed"
    assert report["program"]["hex"] == POSITIONS.hex()
    assert len(report["captures"]) == report["parameters"]["maximum_resumes"] == 6
    assert report["attachment"]["update"]["status"] == "attached"
    assert report["final_state"]["guest"]["status"] == "return"
    assert report["final_state"]["guest"]["retired"] == 6
    assert report["final_state"]["observation"]["dropped"] == 10
    final = report["captures"][-1]
    assert_positions(final["view"], {0: (50, 60), 1: (70, 80)})
    assert final["view"]["coverage"]["history_complete_since_attach"] is False


def test_native_failed_control_exposes_consumed_pending_receipt(native_binary):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.run()
        generation = vm.state()["observation"]["control_generation"]
        with pytest.raises(_scene.SceneOperationError) as failure:
            scene.configure(capacity=-1)
        error = failure.value
        assert error.operation == "configure" and error.stage == "control"
        assert isinstance(error.__cause__, ValueError)
        pending = error.receipts["pending_capture"]
        assert_changes(pending["update"], [(0, 10, 20, 0)])
        assert_positions(pending["view"], {0: (10, 20)})
        assert_changes(scene.capture()["update"], [])
        assert vm.state()["observation"]["control_generation"] == generation
        assert vm.state()["guest"]["retired"] == 1
        pending["update"]["changes"][0]["after"]["x"] = 255
        pending["view"]["actors"][0]["x"] = 255
        assert_positions(scene.view(), {0: (10, 20)})
        assert scene.view()["actors"][0]["witness"]["after"]["x"] == 10


def test_native_post_control_capture_error_keeps_pending_receipt(native_binary, monkeypatch):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.run()
        events = vm.events
        calls = 0
        original = _harness.HarnessError("post-control record query failed")

        def fail_second_read():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise original
            return events()

        with monkeypatch.context() as changed:
            changed.setattr(vm, "events", fail_second_read)
            with pytest.raises(_scene.SceneOperationError) as failure:
                scene.configure(capacity=32)
        error = failure.value
        assert error.operation == "configure" and error.stage == "capture"
        assert error.__cause__ is original
        assert_changes(error.receipts["pending_capture"]["update"], [(0, 10, 20, 0)])
        assert calls == 2  # No retry of the failing capture.
        assert vm.state()["observation"]["capacity"] == 32  # No control rollback.
        assert vm.state()["guest"]["retired"] == 1
        assert_changes(scene.capture()["update"], [])
        assert scene.view()["coverage"]["history_complete_since_attach"] is True


def test_native_failed_initial_control_capture_keeps_original_error_and_delta(native_binary, monkeypatch):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        before = scene.view()
        vm.run()
        generation = vm.state()["observation"]["control_generation"]
        records = vm.events()
        records["source"]["sha256"] = "f" * 64
        with monkeypatch.context() as changed:
            changed.setattr(vm, "events", lambda: deepcopy(records))
            with pytest.raises(SceneInputError, match="source"):
                scene.configure(capacity=32)
        assert scene.view() == before
        assert vm.state()["observation"]["capacity"] == 16
        assert vm.state()["observation"]["control_generation"] == generation
        assert_changes(scene.capture()["update"], [(0, 10, 20, 0)])


@pytest.mark.parametrize("stage", ["run", "capture"])
def test_native_budgeted_run_error_retains_successful_preparation(native_binary, monkeypatch, stage):
    with QemuAGI(native_binary, POSITIONS) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=16, step_budget=1)
        vm.run()
        events = vm.events
        calls = 0
        original = _harness.HarnessError(f"prepared {stage} failed")

        def fail_run():
            raise original

        def fail_post_run_read():
            nonlocal calls
            calls += 1
            if calls == 3:  # Two successful configure captures precede run.
                raise original
            return events()

        with monkeypatch.context() as changed:
            if stage == "run":
                changed.setattr(vm, "run", fail_run)
            else:
                changed.setattr(vm, "events", fail_post_run_read)
            with pytest.raises(_scene.SceneOperationError) as failure:
                scene.run(step_budget=1)
        error = failure.value
        assert error.operation == "run" and error.stage == stage
        assert error.__cause__ is original
        preparation = error.receipts["preparation"]
        assert_changes(preparation["pending_update"], [(0, 10, 20, 0)])
        assert_changes(preparation["update"], [])
        assert_positions(preparation["view"], {0: (10, 20)})
        if stage == "capture":
            assert calls == 3
            assert vm.state()["guest"]["retired"] == 2
            assert_changes(scene.capture()["update"], [(1, 30, 40, 4)])
        else:
            assert vm.state()["guest"]["retired"] == 1
            assert_changes(scene.capture()["update"], [])
        preparation["pending_update"]["changes"][0]["after"]["x"] = 255
        assert scene.view()["actors"][0]["witness"]["after"]["x"] == 10
