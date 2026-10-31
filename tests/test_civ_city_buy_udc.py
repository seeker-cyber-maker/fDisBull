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


def test_buy_completes_production_and_debits_price():
    result = _run({"$shield_box": 7, "$treasury": 200, "$item_cost": 4, "$price": 160})
    assert result["status"] == "complete"
    assert result["state"]["$shield_box"] == 40
    assert result["state"]["$treasury"] == 40


def test_buy_refuses_when_treasury_is_short():
    result = _run({"$shield_box": 3, "$treasury": 100, "$item_cost": 4, "$price": 160})
    assert result["status"] == "refused"
    assert result["state"]["$treasury"] == 100
    assert result["state"]["$shield_box"] == 3


def test_buy_accepts_exact_treasury():
    result = _run({"$shield_box": 3, "$treasury": 160, "$item_cost": 4, "$price": 160})
    assert result["status"] == "complete"
    assert result["state"]["$treasury"] == 0
    assert result["state"]["$shield_box"] == 40


def test_tenfold_item_cost_wraps_at_16_bits():
    result = _run({"$shield_box": 0, "$treasury": 50, "$item_cost": 4000, "$price": 10})
    assert result["state"]["$shield_box"] == -25536
    assert result["state"]["$treasury"] == 40


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
        "$treasury": 40,
        "$item_cost": 4,
        "$price": 160,
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
