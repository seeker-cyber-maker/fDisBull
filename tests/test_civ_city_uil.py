"""Regression coverage for the bounded Civ city UIL/UDC slice."""

import json
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
    assert disorder["state"]["$shield_box"] == 0

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
PINNED_ROOT = Path("build/civ-analysis/CIV_UNP.EXE")


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
