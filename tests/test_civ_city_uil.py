"""Regression coverage for the bounded Civ city UIL/UDC slice."""

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
