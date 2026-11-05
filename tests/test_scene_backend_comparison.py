"""The comparison gate must reject attractive but unequal live-run evidence."""

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from fdisbull.scene_backend_comparison import (
    CARROT_TASK, SOURCE_AGI_SHA256, TASK, FORMAT, compare, compare_carrot,
)


def _run(backend):
    digest = "a" * 64
    frame_source = ("last_completed_guest_frame" if backend == "dosbox-x"
                    else "last_committed_scummvm_display")
    start_frame = {"sha256": "c" * 64, "width": 320, "height": 200,
                   "frame_id": 4, "source": frame_source}
    end_frame = {"sha256": "d" * 64, "width": 320, "height": 200,
                 "frame_id": 8, "source": frame_source}
    if backend == "scummvm-agi":
        start_frame["commit_revision"] = 2
        end_frame["commit_revision"] = 4
    return {
        "format": FORMAT, "task": TASK, "backend": backend,
        "status": "complete", "policy": "physical", "interventions": [],
        "source": {"agi_sha256": SOURCE_AGI_SHA256, "manifest_sha256": digest},
        "runtime": {"binary_sha256": "b" * 64, "version": "test-native-build"},
        "boundaries": {
            "start": {"state": {"room": 1, "score": 0},
                      "frame": start_frame},
            "end": {"state": {"room": 16, "score": 0},
                    "frame": end_frame},
        },
        "timing_ms": {"startup": 10.0, "route": 20.0, "observation": 2.0,
                      "teardown": 3.0, "inclusive": 34.0},
    }


def test_matched_live_receipts_produce_only_a_partial_scene():
    report, scene = compare(_run("dosbox-x"), _run("scummvm-agi"))
    assert report["matched_fields"] == ["room", "score"]
    assert "whole-engine" in report["claim_ceiling"]
    assert scene["partial"] is True
    assert report["scene"]["end"] == "room-16"


def test_scummvm_frame_identity_is_opaque_and_commit_revision_is_ordered():
    scummvm = _run("scummvm-agi")
    scummvm["boundaries"]["end"]["frame"]["frame_id"] = 1
    report, _ = compare(_run("dosbox-x"), scummvm)
    assert report["scene"]["end"] == "room-16"


@pytest.mark.parametrize("change", [
    lambda r: r["source"].update(manifest_sha256="f" * 64),
    lambda r: r["boundaries"]["end"]["state"].update(score=1),
    lambda r: r["boundaries"]["end"]["frame"].update(commit_revision=2),
    lambda r: r.update(interventions=["memory write"]),
    lambda r: r.update(status="budget_exhausted"),
])
def test_mismatched_or_incomplete_runs_cannot_qualify(change):
    dos = _run("dosbox-x")
    scummvm = deepcopy(_run("scummvm-agi"))
    change(scummvm)
    with pytest.raises(ValueError):
        compare(dos, scummvm)


def _carrot_run(backend):
    run = _run(backend)
    run["task"] = CARROT_TASK
    run["inputs"] = [{"kind": "press", "value": "up", "delivery": "queued"}] * 7
    run["runtime"]["python_sources"] = {"provider.py": "e" * 64}
    run["runtime"]["python_manifest_sha256"] = sha256(json.dumps(
        run["runtime"]["python_sources"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    run["route_control_calls"] = {"guest_runs": 10, "state_reads": 5,
                                  "memory_reads": 20 if backend == "dosbox-x" else 0,
                                  "engine_state_reads": 5 if backend == "scummvm-agi" else 0,
                                  "keyboard_state_reads": 10 if backend == "dosbox-x" else 0,
                                  "keyboard_submissions": 7, "screenshots": 3}
    run["timing_ms"] = {"startup": 10.0, "route": 20.0, "observation": 2.0,
                        "teardown": 3.0, "inclusive": 34.0}
    source = run["boundaries"]
    source.pop("end")
    states = {
        "start": {"room": 1, "score": 0, "carrot_flag_77": False,
                  "ego_y": 100, "direction": 0},
        "arrival": {"room": 16, "score": 0, "carrot_flag_77": False,
                    "ego_y": 140, "direction": 0},
        "carrot": {"room": 16, "score": 2, "carrot_flag_77": True,
                   "ego_y": 140, "direction": 0},
        "repeat": {"room": 16, "score": 2, "carrot_flag_77": True,
                   "ego_y": 140, "direction": 0},
    }
    for index, phase in enumerate(states):
        state = states[phase]
        if backend == "dosbox-x":
            state["message_window"] = False
        else:
            state["at_modal"] = False
            state["modal_revision"] = [0, 0, 2, 4][index]
        frame = {"sha256": "c" * 64, "width": 320, "height": 200,
                 "frame_id": 10 + index,
                 "source": ("last_completed_guest_frame" if backend == "dosbox-x"
                            else "last_committed_scummvm_display")}
        if backend == "scummvm-agi":
            frame["commit_revision"] = 10 + index
        source[phase] = {"state": state, "frame": frame}
    run["commands"] = []
    for index, phase in enumerate(("carrot", "repeat")):
        witness = {"state": deepcopy(source[phase]["state"])}
        if backend == "dosbox-x":
            witness.update(opened=True, dismissed=True)
        else:
            witness.update(opened_revision=1 + 2 * index, closed_revision=2 + 2 * index)
        run["commands"].append({"command": "get carrot",
                                "result": "taken" if index == 0 else "refused-no-state-change",
                                "witness": witness})
    return run


def test_carrot_pair_replays_effect_and_repeat_guard_in_partial_z_scene():
    report, scene, replay = compare_carrot(_carrot_run("dosbox-x"), _carrot_run("scummvm-agi"))
    assert report["matched_fields"] == ["room", "score", "carrot_flag_77",
                                         "message open and close", "repeat state unchanged"]
    assert scene["partial"] is True
    assert replay["actions"][-1]["status"] == "rejected"
    assert replay["final"]["state"] == {"$room": 16, "$score": 2, "$f77_carrot": True}


@pytest.mark.parametrize("change", [
    lambda r: r["boundaries"]["carrot"]["state"].update(carrot_flag_77=False),
    lambda r: r["boundaries"]["repeat"]["state"].update(score=4),
    lambda r: r["boundaries"]["repeat"]["state"].update(modal_revision=2),
    lambda r: r["commands"][1].update(result="taken"),
    lambda r: r.update(status="incomplete"),
])
def test_carrot_comparison_rejects_missing_effect_or_refusal(change):
    scummvm = _carrot_run("scummvm-agi")
    change(scummvm)
    with pytest.raises(ValueError):
        compare_carrot(_carrot_run("dosbox-x"), scummvm)
