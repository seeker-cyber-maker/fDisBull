"""Qualification evidence is input-bound; only authored one-byte LOGIC is used."""

from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest


NATIVE = Path(__file__).resolve().parents[1] / "native/qemu-agi"
sys.path.insert(0, str(NATIVE))
import qualify_runtime_resources as qualification
from runtime_pack import build_package, dump_package


def authored_manifest(tmp_path, *, wrong_pixel=False):
    package = dump_package(build_package(logics=[{"id": 0, "code": b"\0", "messages": []}]))
    (tmp_path / "package.json").write_bytes(package)
    visual = bytearray([15] * (160 * 168))
    if wrong_pixel:
        visual[160 + 2] = 1
    (tmp_path / "visual.idx").write_bytes(visual)
    value = {
        "schema": qualification.SCHEMA,
        "cases": [{
            "name": "authored-return", "scope": "One authored return; blank native scene.",
            "package": {"path": "package.json", "sha256": sha256(package).hexdigest()},
            "seed": {}, "step_budget": 10,
            "expected_fields": [
                {"path": ["guest", "status"], "value": "return"},
                {"path": ["guest", "pc"], "value": 1},
                {"path": ["guest", "retired"], "value": 1},
            ],
            "expected_planes": {"visual": {"path": "visual.idx", "sha256": sha256(visual).hexdigest()}},
        }],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(value))
    return path, value


def test_changed_package_is_rejected_before_native_launch(tmp_path, monkeypatch):
    path, _ = authored_manifest(tmp_path)
    (tmp_path / "package.json").write_bytes((tmp_path / "package.json").read_bytes() + b"\n")
    def forbidden(*args, **kwargs):
        pytest.fail("Changed source must not reach native execution")
    monkeypatch.setattr(qualification, "QemuAGIRuntime", forbidden)
    with pytest.raises(ValueError, match="hash mismatch"):
        qualification.qualify(path, tmp_path / "absent-binary", "0" * 64, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_plane_shape_and_case_collision_are_rejected(tmp_path):
    path, value = authored_manifest(tmp_path)
    (tmp_path / "visual.idx").write_bytes(b"\x0f")
    value["cases"][0]["expected_planes"]["visual"]["sha256"] = sha256(b"\x0f").hexdigest()
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="160x168"):
        qualification.prepare(path)
    value["cases"][0]["expected_planes"] = {}
    value["cases"].append(value["cases"][0].copy())
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="unique"):
        qualification.prepare(path)


@pytest.fixture
def binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("Set FDISBULL_QEMU_AGI to qualify a native executable")
    path = Path(configured).resolve()
    assert path.is_file() and os.access(path, os.X_OK)
    digest = sha256(path.read_bytes()).hexdigest()
    expected = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256")
    if expected:
        assert digest == expected
    yield path, digest
    assert sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("wrong_pixel", [False, True])
def test_native_qualification_detects_an_independent_wrong_pixel(binary, tmp_path, wrong_pixel):
    path, _ = authored_manifest(tmp_path, wrong_pixel=wrong_pixel)
    oracle = (tmp_path / "visual.idx").read_bytes()
    executable, digest = binary
    receipt = qualification.qualify(path, executable, digest, tmp_path / "output")
    assert receipt["native_children"] == 5 and receipt["binary_unchanged"]
    assert receipt["passed"] is not wrong_pixel
    assert (tmp_path / "visual.idx").read_bytes() == oracle
    for run in receipt["cases"][0]["runs"]:
        assert run["checks"]["full_guest_equal_across_observation"]
        assert run["checks"]["inspection_did_not_mutate_guest"]
        assert run["planes"]["visual"]["mismatches"] == int(wrong_pixel)
        if wrong_pixel:
            assert run["planes"]["visual"]["first_mismatches"] == [
                {"x": 2, "y": 1, "actual": 15, "expected": 1},
            ]
