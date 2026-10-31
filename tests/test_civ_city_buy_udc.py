"""Coverage for the bounded Civ city BUY commit module."""

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
    return execute_il(program, state)["state"]


def test_buy_commit_doubles_cost_and_debits_treasury():
    state = _run({"$shield_box": 5, "$treasury": 100, "$remaining": 10})
    assert state["$shield_box"] == 15
    assert state["$treasury"] == 80
    assert state["$gold_cost"] == 20


def test_buy_commit_wraps_at_16_bits():
    state = _run({"$shield_box": 0, "$treasury": 5, "$remaining": 10})
    assert state["$treasury"] == 65521
    assert state["$shield_box"] == 10


def test_buy_commit_credits_when_stock_exceeds_cost():
    state = _run({"$shield_box": 2, "$treasury": 20, "$remaining": -3})
    assert state["$shield_box"] == -1
    assert state["$treasury"] == 26


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
    by_case = {
        row["case"]: row["observed"]["frame"]["state"] for row in receipt["cases"]
    }
    assert by_case["default"] == {"$shield_box": 15, "$treasury": 80, "$remaining": 10}
    assert by_case["wrap-treasury"] == {
        "$shield_box": 10,
        "$treasury": 65521,
        "$remaining": 10,
    }
    assert by_case["negative-remaining"] == {
        "$shield_box": -1,
        "$treasury": 26,
        "$remaining": -3,
    }


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
