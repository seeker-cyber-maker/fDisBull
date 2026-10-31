"""Coverage for the bounded Civ city BUY guard and commit module."""

import platform
import shutil
import sys
from pathlib import Path

import pytest

from examples.civ.civ_city_buy_udc import build_buy_udc, buy_program
from fdisbull.interaction_il import execute_il

NATIVE = sys.platform == "darwin" and platform.machine() == "arm64"
PINNED_ROOT = Path("build/civ-analysis/CIV_UNP.EXE")


def _run(initial):
    program = buy_program(initial)
    state = {name: value["initial"] for name, value in program["variables"].items()}
    return execute_il(program, state)


def test_buy_completes_production_and_debits_the_computed_price():
    result = _run({"$shield_box": 0, "$treasury": 1000, "$item_cost": 4})
    assert result["status"] == "complete"
    state = result["state"]
    assert (
        state["$base"] == 40 and state["$square"] == 1600 and state["$quotient"] == 80
    )
    assert state["$price"] == 320
    assert state["$shield_box"] == 40 and state["$treasury"] == 680


def test_partial_shield_box_lowers_the_price():
    result = _run({"$shield_box": 10, "$treasury": 1000, "$item_cost": 4})
    assert result["state"]["$price"] == 105
    assert result["state"]["$shield_box"] == 40
    assert result["state"]["$treasury"] == 895


def test_unit_build_ids_past_21_double_the_price():
    result = _run(
        {"$shield_box": 0, "$treasury": 2000, "$item_cost": 4, "$build_id": -22}
    )
    assert result["state"]["$price"] == 640
    assert result["state"]["$treasury"] == 1360


def test_square_wraps_at_16_bits_like_the_source():
    result = _run({"$shield_box": 0, "$treasury": 5000, "$item_cost": 30})
    assert result["state"]["$square"] == 24464
    assert result["state"]["$price"] == 3646
    assert result["state"]["$treasury"] == 1354


def test_buy_refuses_when_treasury_is_short():
    result = _run({"$shield_box": 0, "$treasury": 100, "$item_cost": 4})
    assert result["status"] == "refused"
    assert result["state"]["$treasury"] == 100
    assert result["state"]["$shield_box"] == 0


def test_buy_program_refuses_unknown_state():
    with pytest.raises(ValueError, match="unknown Civ buy variable"):
        buy_program({"$gold": 1})


@pytest.mark.skipif(
    not (NATIVE and shutil.which("clang")),
    reason="native arm64 Mach-O execution requires macOS arm64 and clang",
)
def test_buy_udc_builds_and_matches_interpreter_natively(tmp_path):
    if not PINNED_ROOT.exists():
        pytest.skip("pinned unpacked Civ root is not present")
    from examples.civ.civ_city_udc_diff import sweep_buy

    receipt = sweep_buy(PINNED_ROOT, tmp_path / "buy", target="macos-arm64")
    assert receipt["verdict"] == "match", [
        (row["case"], row["expected"], row["observed"])
        for row in receipt["cases"]
        if not row["match"]
    ]
    by_case = {row["case"]: row for row in receipt["cases"]}
    assert by_case["default"]["observed"]["frame"]["state"] == {
        "$shield_box": 40,
        "$treasury": 680,
        "$item_cost": 4,
        "$build_id": 0,
    }
    refused = by_case["insufficient"]["observed"]
    assert refused["returncode"] != 0 and refused["frame"] is None


@pytest.mark.skipif(
    not (NATIVE and shutil.which("clang")),
    reason="native arm64 Mach-O execution requires macOS arm64 and clang",
)
def test_buy_udc_requires_the_pinned_root(tmp_path):
    if not PINNED_ROOT.exists():
        pytest.skip("pinned unpacked Civ root is not present")
    forged = tmp_path / "forged.bin"
    forged.write_bytes(b"\xc3" * 64)
    with pytest.raises(ValueError, match="pinned unpacked root"):
        build_buy_udc(
            forged,
            tmp_path / "out",
            project_path=tmp_path / "x.fdb",
            target="macos-arm64",
        )
