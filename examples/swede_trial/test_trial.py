"""Coordinator checks; not part of a fresh worker's reading packet."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixture
import trial


def oracle(name, args):
    if name == "normalize":
        return [max(0, min(args[0], 3))]
    if name == "award":
        return [[0, 2, 4, 7][args[0]]]
    if name == "apply":
        score = min(args[0] + args[1], 10)
        return [score, score == 10]
    count = max(0, min(args[0], 3))
    points = [0, 2, 4, 7][count]
    if name == "pair":
        return [count, points]
    return [count, points] + oracle("apply", (args[1], points))


@pytest.mark.parametrize("name", ["normalize", "award", "apply", "pair", "turn"])
def test_reference_matches_independent_oracle(name):
    for args in fixture.cases(name):
        assert fixture.evaluate(name, args) == oracle(name, args)


GOOD = '''#include "abi.h"
uint16_t normalize(int16_t raw) { return raw < 0 ? 0u : raw > 3 ? 3u : (uint16_t)raw; }
uint16_t award(uint16_t count) { return (uint16_t)(count * 2u + (count == 3u)); }
ApplyResult apply(uint16_t score, uint16_t points) {
    unsigned total = (unsigned)score + points;
    uint16_t next = (uint16_t)(total > 10u ? 10u : total);
    ApplyResult r = {next, next == 10u}; return r;
}
TurnResult turn(int16_t raw, uint16_t score) {
    uint16_t count = normalize(raw); uint16_t points = award(count);
    ApplyResult r = apply(score, points);
    TurnResult t = {count, points, r.next_score, r.won}; return t;
}
'''


def write_candidate(work, text=GOOD):
    work.mkdir(exist_ok=True)
    (work / "turn.c").write_text(text, encoding="utf-8")
    return trial.state_dir(work)


def test_compiler_comparison_registration_roundtrip_and_stale_source(tmp_path):
    state = write_candidate(tmp_path)
    before = trial.lookup("triple", state)
    assert all(row["next_action"] == "assess-bind-existing" for row in before["blocks"].values())
    packet = trial.task("triple", state)
    assert packet["absence_established"] is False
    checked = trial.check("triple", tmp_path, state)
    assert checked["status"] == "passed", checked
    assert checked["unique_native_cases"] == 296
    assert checked["native_result_rows"] == 592
    assert checked["composition_substitution_cases"] == 187
    registered = trial.register("triple", tmp_path, state)
    assert len(registered["receipts"]) == 3
    after = trial.lookup("triple", state)
    assert all(row["next_action"] == "review-evidence" for row in after["blocks"].values())
    assert all(row["execution_authorized"] is False for row in after["blocks"].values())
    with (tmp_path / "turn.c").open("a") as stream:
        stream.write("\n/* source changed */\n")
    with pytest.raises(ValueError, match="stale qualification"):
        trial.register("triple", tmp_path, state)


@pytest.mark.parametrize("old,new,contract", [
    ("raw < 0 ? 0u", "raw < 0 ? 3u", "normalize"),
    ("count * 2u + (count == 3u)", "count * 2u", "award"),
    ("next == 10u", "next > 10u", "apply"),
    ("apply(score, points)", "apply(score, count)", "turn"),
])
def test_exhaustive_check_rejects_wrong_block_and_wrong_connection(tmp_path, old, new, contract):
    state = write_candidate(tmp_path, GOOD.replace(old, new))
    checked = trial.check("triple", tmp_path, state)
    assert checked["status"] == "failed", checked
    assert checked["failure"]["kind"] == "behavior-mismatch"
    assert checked["failure"]["contract"] == contract
    with pytest.raises(ValueError, match="qualification missing"):
        trial.register("triple", tmp_path, state)


def test_checker_rejects_missing_result_row():
    assert trial.compare_rows([("normalize", (-1,), [0])], "")["kind"] == "row-count"


@pytest.mark.parametrize("mode,native_cases,substitution_cases", [("singles", 109, 748), ("pair", 38, 187)])
def test_other_modes_compile_check_register(tmp_path, mode, native_cases, substitution_cases):
    lines = GOOD.splitlines(keepends=True)
    if mode == "singles":
        (tmp_path / "normalize.c").write_text(lines[0] + lines[1])
        (tmp_path / "award.c").write_text(lines[0] + lines[2])
        (tmp_path / "apply.c").write_text(lines[0] + "".join(lines[3:8]))
    else:
        pair = """PairResult pair(int16_t raw) {
    uint16_t count = normalize(raw);
    PairResult r = {count, award(count)}; return r;
}
"""
        (tmp_path / "pair.c").write_text("".join(lines[:3]) + pair)
    state = trial.state_dir(tmp_path)
    trial.task(mode, state)
    result = trial.check(mode, tmp_path, state)
    assert result["status"] == "passed", result
    assert result["unique_native_cases"] == native_cases
    assert result["composition_substitution_cases"] == substitution_cases
    trial.register(mode, tmp_path, state)
    assert all(row["next_action"] == "review-evidence" for row in trial.lookup(mode, state)["blocks"].values())


@pytest.mark.parametrize("mode", ["singles", "pair", "triple"])
def test_collected_agent_sources_against_contracts(tmp_path, mode):
    for filename in fixture.MODES[mode]["files"]:
        (tmp_path / filename).write_bytes((HERE / "candidates" / mode / filename).read_bytes())
    result = trial.check(mode, tmp_path, trial.state_dir(tmp_path))
    assert result["status"] == "passed", result
