"""Regression coverage for the bounded Civ city UIL/UDC slice."""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from examples.civ.civ_city_uil import _primitive_program, build_city_udc, city_scene
from fdisbull.il_scenes import ILSceneBackend
from fdisbull.interaction_il import execute_il


def test_city_scene_exposes_source_mapped_tabs_and_transitions():
    backend = ILSceneBackend(city_scene())
    initial = backend.observe()
    assert initial["complete"] is True
    assert initial["context"]["id"] == "city"
    visible = {item["id"] for item in initial["objects"]}
    assert {"food-storage", "production-storage", "city-radius", "tab-map"} <= visible
    token = initial["context"]["token"]

    changed = backend.act(
        {"verb": "select", "target": "tab-map", "item": None, "context_token": token}
    )
    assert changed == {"status": "success", "complete": True, "message": "Map"}
    mapped = backend.observe()
    mapped_ids = {item["id"] for item in mapped["objects"]}
    assert "map-panel" in mapped_ids
    assert "food-storage" not in mapped_ids

    restored = backend.act(
        {
            "verb": "select",
            "target": "tab-resources",
            "item": None,
            "context_token": mapped["context"]["token"],
        }
    )
    assert restored["status"] == "success"
    assert "food-storage" in {item["id"] for item in backend.observe()["objects"]}


def test_city_shield_step_preserves_sanitize_and_disorder_boundary():
    program = _primitive_program()
    normal = execute_il(
        program,
        state={
            "$shield_box": 5,
            "$shield_delta": 3,
            "$disorder": False,
            "$sanitized": True,
        },
    )
    assert normal["status"] == "complete"
    assert normal["state"]["$shield_box"] == 8

    disorder = execute_il(
        program,
        state={
            "$shield_box": 5,
            "$shield_delta": 3,
            "$disorder": True,
            "$sanitized": True,
        },
    )
    assert disorder["status"] == "complete"
    assert disorder["state"]["$shield_box"] == 5

    unsanitized = execute_il(
        program,
        state={
            "$shield_box": 5,
            "$shield_delta": 3,
            "$disorder": False,
            "$sanitized": False,
        },
    )
    assert unsanitized["status"] == "refused"
    assert unsanitized["state"]["$shield_box"] == 5
    assert unsanitized["events"] == []


def test_city_udc_rejects_non_pinned_source_before_output(tmp_path):
    source = tmp_path / "CIV_UNP.EXE"
    source.write_bytes(b"not the pinned Civ root")
    destination = tmp_path / "out"
    with pytest.raises(ValueError, match="pinned unpacked root"):
        build_city_udc(source, destination)
    assert not destination.exists()


NATIVE = sys.platform == "darwin" and platform.machine() == "arm64"
PINNED_ROOT = Path(os.environ.get("FDISBULL_CIV_UNPACKED", "build/civ-analysis/CIV_UNP.EXE"))


@pytest.mark.skipif(
    not (NATIVE and shutil.which("clang")),
    reason="native arm64 Mach-O execution requires macOS arm64 and clang",
)
def test_city_udc_macos_target_builds_and_runs_natively(tmp_path):
    if not PINNED_ROOT.exists():
        pytest.skip("pinned unpacked Civ root is not present")
    receipt = build_city_udc(
        PINNED_ROOT,
        tmp_path / "out",
        project_path=tmp_path / "city.fdb",
        target="macos-arm64",
    )
    assert receipt["native_build"]["profile"] == "macos-arm64-c-plan-libsystem-1"
    assert receipt["native_build"]["target"]["arch"] == "arm64"
    assert (
        receipt["native_build"]["native_build_qualification"]["native_execution"]
        is False
    )
    done = subprocess.run(
        [str(tmp_path / "out/program")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    frame = json.loads(done.stdout.strip().splitlines()[-1])
    assert frame["format"] == "fdisbull-macos-observation-1"
    assert frame["status"] == 0
    assert frame["state"]["$shield_box"] == 3


@pytest.mark.skipif(
    not (NATIVE and shutil.which("clang")),
    reason="native arm64 Mach-O execution requires macOS arm64 and clang",
)
def test_city_udc_matches_interpreter_across_boundaries(tmp_path):
    if not PINNED_ROOT.exists():
        pytest.skip("pinned unpacked Civ root is not present")
    from examples.civ.civ_city_udc_diff import sweep

    receipt = sweep(PINNED_ROOT, tmp_path / "sweep", target="macos-arm64")
    assert receipt["verdict"] == "match", [
        (row["case"], row["expected"], row["observed"])
        for row in receipt["cases"]
        if not row["match"]
    ]
    by_case = {row["case"]: row for row in receipt["cases"]}
    assert by_case["wrap-high"]["observed"]["frame"]["state"]["$shield_box"] == -32768
    assert by_case["wrap-low"]["observed"]["frame"]["state"]["$shield_box"] == 32767
    assert by_case["disorder-preserves-stock"]["observed"]["frame"]["state"]["$shield_box"] == 7
    refused = by_case["unsanitized-refusal"]["observed"]
    assert refused["returncode"] != 0 and refused["frame"] is None


def _act(backend, verb, target):
    observation = backend.observe()
    return backend.act(
        {
            "verb": verb,
            "target": target,
            "item": None,
            "context_token": observation["context"]["token"],
        }
    )


def test_city_production_chooser_commits_recovered_codes():
    backend = ILSceneBackend(city_scene())
    assert _act(backend, "activate", "production-change")["status"] == "success"
    chooser = backend.observe()
    assert chooser["context"]["id"] == "production-chooser"
    assert {item["id"] for item in chooser["objects"]} == {"build-settlers", "build-militia"}
    assert _act(backend, "build", "build-militia")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city"
    assert backend.state["$production"] == 1
    assert _act(backend, "activate", "production-change")["status"] == "success"
    assert _act(backend, "build", "build-settlers")["status"] == "success"
    assert backend.state["$production"] == 0


def test_city_auto_build_toggles_and_unit_cursor_clamps():
    definition = city_scene()
    backend = ILSceneBackend(definition)
    assert _act(backend, "activate", "production-auto")["status"] == "success"
    assert backend.state["$auto_build"] is True
    assert _act(backend, "activate", "production-auto")["status"] == "success"
    assert backend.state["$auto_build"] is False

    state = {name: decl["initial"] for name, decl in backend.variables.items()}
    state["$unit_count"] = 2
    units = ILSceneBackend(definition, state=state)
    assert _act(units, "open", "unit-panel")["status"] == "success"
    assert units.observe()["context"]["id"] == "unit-list"
    assert (units.state["$unit_cursor"], units.state["$unit_last"]) == (0, 1)
    assert _act(units, "next", "unit-cursor-next")["status"] == "success"
    assert units.state["$unit_cursor"] == 1
    assert _act(units, "next", "unit-cursor-next")["status"] == "success"
    assert units.state["$unit_cursor"] == 1
    assert _act(units, "previous", "unit-cursor-previous")["status"] == "success"
    assert units.state["$unit_cursor"] == 0
    assert _act(units, "select", "unit-cursor-select")["status"] == "success"
    assert units.observe()["context"]["id"] == "city"
    assert units.state["$city_cursor"] == 0


def test_city_unit_cursor_refuses_selection_without_units():
    backend = ILSceneBackend(city_scene())
    assert _act(backend, "open", "unit-panel")["status"] == "success"
    assert (backend.state["$unit_cursor"], backend.state["$unit_last"]) == (0, 0)
    assert _act(backend, "select", "unit-cursor-select")["status"] == "rejected"
    assert _act(backend, "exit", "unit-cursor-exit")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city"


def test_city_scene_serves_the_z_player_without_a_debugger():
    import shlex

    root = Path(__file__).resolve().parents[1]
    scene = root / "examples/civ/civ_city_scene.json"
    env = dict(os.environ, PYTHONPATH=str(root / "src") + ":" + str(root / "player"))
    backend = shlex.join([sys.executable, "-m", "fdisbull.il_scenes", str(scene)])
    result = subprocess.run(
        [sys.executable, "-m", "fdisbull_player", "--backend-command", backend],
        input="activate change\nbuild militia\nopen units\nlook\nnext next\nselect select\nquit\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Success: What shall we build in Rome?" in result.stdout
    assert "Success: Militia (10 turns)" in result.stdout
    assert "Visible: Next unit" in result.stdout
    assert "Rejected: Action refused." in result.stdout
