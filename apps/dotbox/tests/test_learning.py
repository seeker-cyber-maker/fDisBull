"""Persistent play-first planning metadata; no guest or ownership operations."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import dotbox
from dotbox.learning import LearningStore


SOURCE = "a" * 64


def test_reopening_the_same_focus_keeps_its_deadline_and_probe_count(tmp_path):
    path = tmp_path / "private" / "learning.sqlite"
    clock = [100.0]
    with LearningStore(path, SOURCE, clock=lambda: clock[0], clock_id="boot-one") as store:
        first = store.focus(context="frame-one", scene="gate", goal="enter town",
                            question="Which control opens the gate?", next_interaction="speak to guard")
        assert store.admit(first["focus_id"])["admitted"]
    clock[0] = 110.0
    with LearningStore(path, SOURCE, clock=lambda: clock[0], clock_id="boot-one") as store:
        again = store.focus(context="frame-one", scene="gate", goal="enter town",
                            question="Try the visible handle", next_interaction="speak to guard",
                            budget_seconds=90, max_probes=8)
        assert again["focus_id"] == first["focus_id"]
        assert again["deadline_monotonic"] == 115.0
        assert again["probes_admitted"] == 1
        assert again["max_probes"] == 2
        assert again["remaining_seconds"] == 5.0


def focus(store, **changes):
    return store.focus(**({"context": "frame-one", "scene": "gate", "goal": "enter town",
                          "question": "How does this gate open?", "next_interaction": "speak to guard"} | changes))


@pytest.fixture
def learning(tmp_path):
    clock = [100.0]
    with LearningStore(tmp_path / "private" / "learning.sqlite", SOURCE,
                       clock=lambda: clock[0], clock_id="boot-one") as store:
        yield store, clock


def test_deadline_denies_the_first_probe_after_time_spent_thinking(learning):
    store, clock = learning
    first = focus(store)
    clock[0] = 115.0
    denied = store.admit(first["focus_id"])
    assert denied["admitted"] is False
    assert denied["budget_state"] == "deadline"
    assert denied["elapsed_seconds"] == 15.0
    assert denied["probes_admitted"] == 0
    assert denied["recommendation"] == "report_block"
    again = focus(store, budget_seconds=180, max_probes=16)
    assert again["deadline_monotonic"] == 115.0
    assert again["max_probes"] == 2
    assert not again["can_admit_probe"]


def test_probe_admissions_are_atomic_across_connections(learning):
    store, _ = learning
    first = focus(store)

    def admit(_):
        with LearningStore(store.path, SOURCE, clock=lambda: 101.0, clock_id="boot-one") as other:
            return other.admit(first["focus_id"])["admitted"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        accepted = list(executor.map(admit, range(4)))
    assert sum(accepted) == 2
    assert store.status()["probes_admitted"] == 2


@pytest.mark.parametrize("operation", ["admit", "record"])
def test_mutations_require_an_explicit_focus_id(learning, operation):
    store, _ = learning
    first = focus(store)
    for missing in (None, "", False):
        with pytest.raises(ValueError, match="focus_id"):
            if operation == "admit":
                store.admit(missing)
            else:
                store.record(missing, "candidate", "private/reference", "b" * 64)
    status = store.status()
    assert status["focus_id"] == first["focus_id"]
    assert status["probes_admitted"] == 0 and status["recent_results"] == []


def test_applicable_fallback_recommends_play_even_without_a_named_scene(learning):
    store, clock = learning
    first = focus(store, scene="unknown", fallback="Use the visible menu's known arrow/Enter controls")
    assert first["recommendation"] == "use_fallback"
    assert first["probes_admitted"] == 0
    clock[0] = 130.0
    status = store.status()
    assert status["recommendation"] == "use_fallback"
    assert not status["can_admit_probe"]
    assert status["scope"] == "planning_metadata_only"


def test_changed_context_requires_explicit_retirement_and_preserves_history(learning):
    store, clock = learning
    first = focus(store)
    with pytest.raises(ValueError, match="retire_reason"):
        focus(store, context="frame-two", scene="courtyard")
    assert store.status()["focus_id"] == first["focus_id"]
    with pytest.raises(ValueError, match="fresh context"):
        focus(store, scene="courtyard", retire_reason="changed room")
    clock[0] = 104.0
    second = focus(store, context="frame-two", scene="courtyard", retire_reason="Observed entry into courtyard")
    assert second["focus_id"] != first["focus_id"]
    assert second["deadline_monotonic"] == 119.0
    retired = store.status(first["focus_id"])
    assert retired["state"] == "retired" and retired["retire_reason"] == "Observed entry into courtyard"
    assert store.admit(first["focus_id"])["admitted"] is False
    with pytest.raises(ValueError, match="Retired"):
        focus(store, retire_reason="attempted reuse of an old context")
    assert store.status()["focus_id"] == second["focus_id"]


def test_clock_change_requires_reobservation_and_cannot_renew_the_same_focus(learning):
    store, _ = learning
    first = focus(store, fallback="known control")
    with LearningStore(store.path, SOURCE, clock=lambda: 1.0, clock_id="boot-two") as reopened:
        stale = focus(reopened, fallback="known control", budget_seconds=180)
        assert stale["focus_id"] == first["focus_id"]
        assert stale["recommendation"] == "reobserve"
        assert stale["elapsed_seconds"] is None and stale["remaining_seconds"] is None
        assert not reopened.admit(first["focus_id"])["admitted"]
        fresh = focus(reopened, context="new-boot-observation", retire_reason="Reobserved after reboot")
        assert fresh["started_monotonic"] == 1.0
        assert fresh["deadline_monotonic"] == 16.0


def test_clock_regression_cannot_be_repaired_by_relabeling_context(learning):
    store, clock = learning
    first = focus(store)
    clock[0] = 109.0
    assert store.admit(first["focus_id"])["admitted"]
    clock[0] = 108.0
    assert store.status()["budget_state"] == "clock_regressed"
    assert not store.admit(first["focus_id"])["admitted"]
    with pytest.raises(ValueError, match="Clock regressed"):
        focus(store, context="frame-two", retire_reason="changed context")
    assert store.status()["focus_id"] == first["focus_id"]


@pytest.mark.parametrize("checkpoint", ["status", "focus", "denied_admission"])
def test_expired_time_observation_cannot_be_undone_by_clock_regression(learning, checkpoint):
    store, clock = learning
    first = focus(store)
    clock[0] = 120.0
    if checkpoint == "status":
        assert store.status()["budget_state"] == "deadline"
    elif checkpoint == "focus":
        assert focus(store)["budget_state"] == "deadline"
    else:
        assert not store.admit(first["focus_id"])["admitted"]
    clock[0] = 110.0
    denied = store.admit(first["focus_id"])
    assert not denied["admitted"]
    assert denied["budget_state"] == "clock_regressed"
    assert denied["probes_admitted"] == 0


def test_evidence_is_immutable_idempotent_and_does_not_certify_a_candidate(learning):
    store, clock = learning
    first = focus(store)
    candidate = store.record(first["focus_id"], "candidate", "private-evidence/frame-1", "b" * 64,
                             "The handle may open the gate")
    clock[0] = 117.0
    duplicate = store.record(first["focus_id"], "candidate", "private-evidence/frame-1", "b" * 64,
                             "The handle may open the gate")
    assert duplicate == candidate
    observed = store.record(first["focus_id"], "observed", "private-evidence/frame-2", "c" * 64,
                            "Caller observed an open gate after one input")
    assert observed["record_id"] != candidate["record_id"]
    assert observed["elapsed_seconds"] == 17.0
    status = store.status()
    assert {r["result_status"] for r in status["recent_results"]} == {"candidate", "observed"}
    assert all(r["claim"] == "caller_reported" for r in status["recent_results"])
    assert status["recommendation"] == "report_block"
    assert status["probes_admitted"] == 0
    assert not status["can_admit_probe"]
    with pytest.raises(ValueError):
        store.record(first["focus_id"], "certified", "reference", "c" * 64)
    with pytest.raises(ValueError):
        store.record(first["focus_id"], "observed", "reference", "not-a-digest")
    assert len(store.status()["recent_results"]) == 2


def test_wrong_source_binding_preserves_the_existing_file(learning):
    store, _ = learning
    focus(store)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="binding"):
        LearningStore(store.path, "b" * 64, clock_id="boot-one")
    assert store.path.read_bytes() == before


def test_record_idempotency_survives_focus_question_changes(learning):
    store, _ = learning
    first = focus(store, question="Does Enter confirm?")
    original = store.record(first["focus_id"], "observed", "private/enter-result", "d" * 64,
                            "Enter confirmed the menu choice")
    focus(store, question="Does Escape close?")
    repeated = store.record(first["focus_id"], "observed", "private/enter-result", "d" * 64,
                            "Enter confirmed the menu choice")
    assert repeated == original
    assert repeated["focus_question_at_recording"] == "Does Enter confirm?"
    assert "question" not in repeated  # Recording context is not an assertion about the probe question.
    assert len(store.status()["recent_results"]) == 1


def test_nonlearning_database_is_rejected_without_mutation(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "other.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE user_work(value TEXT)")
        db.execute("INSERT INTO user_work VALUES ('preserve me')")
    path.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not a DotBox learning store"):
        LearningStore(path, SOURCE, clock_id="boot-one")
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["public_parent", "public_file", "symlink"])
def test_private_storage_requirements_preserve_foreign_files(tmp_path, kind):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755 if kind == "public_parent" else 0o700)
    path = directory / "learning.sqlite"
    target = tmp_path / "original"
    target.write_bytes(b"private original")
    if kind == "public_file":
        path.write_bytes(b"public file")
        path.chmod(0o644)
    elif kind == "symlink":
        path.symlink_to(target)
    with pytest.raises(ValueError, match="private"):
        LearningStore(path, SOURCE, clock_id="boot-one")
    assert target.read_bytes() == b"private original"
    if kind == "public_parent":
        assert not path.exists()


@pytest.mark.parametrize("budget,probes", [(0, 2), (-1, 2), (float("nan"), 2),
                                         (float("inf"), 2), (181, 2), (15, 0), (15, True)])
def test_invalid_budgets_never_start_a_focus(learning, budget, probes):
    store, _ = learning
    with pytest.raises(ValueError, match="Budget"):
        focus(store, budget_seconds=budget, max_probes=probes)
    assert store.status()["focus_id"] is None


def test_cli_keeps_budget_across_separate_processes(tmp_path):
    package_root = str(Path(dotbox.__file__).resolve().parent.parent)
    bootstrap = f"import runpy,sys;sys.path.insert(0,{package_root!r});runpy.run_module('dotbox.learning',run_name='__main__')"
    prefix = [sys.executable, "-I", "-c", bootstrap]
    common = ["--store", str(tmp_path / "private" / "learning.sqlite"), "--source-sha256", SOURCE]

    def run(command, *arguments):
        return subprocess.run(prefix + [command] + common + list(arguments), capture_output=True, text=True, timeout=3)

    missing = run("status")
    assert missing.returncode == 1
    assert not (tmp_path / "private").exists()
    started = run("focus", "--context", "visible-frame", "--scene", "gate", "--goal", "enter",
                  "--question", "how to open?", "--next", "enter courtyard")
    assert started.returncode == 0, started.stderr
    first = json.loads(started.stdout)["result"]
    for expected in (0, 0, 1):
        admitted = run("admit", "--focus-id", first["focus_id"])
        assert admitted.returncode == expected, admitted.stderr
        assert json.loads(admitted.stdout)["ok"] is (expected == 0)
    status = run("status")
    assert status.returncode == 0, status.stderr
    final = json.loads(status.stdout)["result"]
    assert final["focus_id"] == first["focus_id"]
    assert final["deadline_monotonic"] == first["deadline_monotonic"]
    assert final["probes_admitted"] == 2
    assert final["elapsed_seconds"] >= 0
