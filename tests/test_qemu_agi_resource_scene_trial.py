"""Authored resources and native checks for the private resource packet seam."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native/qemu-agi"))
from scene_harness import SceneOperationError

_SPEC = importlib.util.spec_from_file_location(
    "resource_scene_trial_tests", ROOT / "native/qemu-agi/resource_scene_trial.py")
trial = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(trial)


@pytest.fixture
def authored(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    code = bytes((25, 0, 41, 1, 0, 37, 1, 7, 9, 35, 1, 0))
    logic = len(code).to_bytes(2, "little") + code + b"\0\x03\0"
    picture = b"\xff"
    view = bytes((0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 2, 15,
                  0x11, 0x21, 0, 0x31, 0))
    volume = bytearray()
    for directory, payload in (("LOGDIR", logic), ("PICDIR", picture), ("VIEWDIR", view)):
        (game / directory).write_bytes(len(volume).to_bytes(3, "big"))
        volume.extend(b"\x12\x34\0" + len(payload).to_bytes(2, "little") + payload)
    (game / "SNDDIR").write_bytes(b"")
    (game / "VOL.0").write_bytes(volume)
    case = {"id": "authored", "logic": 0, "picture": 0, "actor": 1,
            "picture_offset": 2, "view_offset": 4, "position_offset": 7,
            "draw_offset": 11, "loop": 0, "cel": 0, "edit_position": [13, 17]}
    return game, case, logic, picture, view


@pytest.fixture
def binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI")
    return Path(configured).expanduser().resolve()


def test_source_boundaries_and_explicit_designer_assets(authored):
    game, case, logic, picture, view = authored
    value = trial.prepare_case(game, case)
    assert value["code"] == bytes((37, 1, 7, 9, 0))
    assert value["logic"]["sha256"] == hashlib.sha256(logic).hexdigest()
    assert value["picture"]["sha256"] == hashlib.sha256(picture).hexdigest()
    assert value["view"]["sha256"] == hashlib.sha256(view).hexdigest()
    assert value["sites"]["position"]["payload_offset"] == 7
    assert value["sites"]["position"]["code_pc"] == 5
    assert value["picture_variable"] == 0
    assert value["assets"] == {"background.idx": bytes([15]) * 26880,
                                "priority.idx": bytes([4]) * 26880,
                                "cel.idx": bytes((1, 2, 3, 15))}
    assert value["cel"]["width"] == value["cel"]["height"] == 2
    assert value["cel"]["transparent_color"] == 15


@pytest.mark.parametrize("field,value", [
    ("actor", True), ("actor", 16), ("logic", -1), ("picture", 256),
    ("loop", False), ("cel", "0"), ("position_offset", 8),
    ("position_offset", 4), ("view_offset", 2), ("draw_offset", 4),
    ("picture_offset", 4), ("id", "../escape"),
    ("edit_position", [1]), ("edit_position", [False, 2]),
])
def test_invalid_case_refuses_before_execution(authored, field, value):
    game, case, *_ = authored
    with pytest.raises(ValueError):
        trial.prepare_case(game, {**case, field: value})


def test_optional_expectations_admit_only_matching_source_facts(authored):
    game, case, *_ = authored
    value = trial.prepare_case(game, {**case, "view": 0, "original_position": [7, 9]})
    assert value["view"]["number"] == 0
    assert value["code"] == bytes((37, 1, 7, 9, 0))


@pytest.mark.parametrize("field,value", [
    ("view", 1), ("view", True), ("view", -1),
    ("original_position", [9, 7]), ("original_position", [7]),
    ("original_position", [7, False]), ("original_position", [7, 256]),
    ("unexpected", "ignored?"),
])
def test_mismatched_or_misspelled_expectations_are_rejected(authored, field, value):
    game, case, *_ = authored
    with pytest.raises(ValueError):
        trial.prepare_case(game, {**case, field: value})


def test_existing_output_is_preserved(authored, tmp_path):
    game, case, *_ = authored
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep"
    marker.write_bytes(b"unchanged")
    with pytest.raises(FileExistsError):
        trial.collect(tmp_path / "missing", game, output, case)
    assert list(output.iterdir()) == [marker]
    assert marker.read_bytes() == b"unchanged"


def test_native_packet_preserves_identity_mapping_and_design_limits(authored, binary, tmp_path):
    game, case, logic, *_ = authored
    originals = {p.name: p.read_bytes() for p in game.iterdir()}
    output = tmp_path / "native"
    report = trial.collect(binary, game, output, case)
    assert report["status"] == "completed"
    packet = json.loads((output / "helper/packet.json").read_text())
    assert packet["qualification"] == "source_bound_design_preview_with_native_position_fragments"
    assert packet["logic"]["sha256"] == hashlib.sha256(logic).hexdigest()
    assert packet["fragment_mapping"] == {
        "copied_fragment_span": [0, 4], "source_payload_base": 7,
        "source_code_base": 5, "authored_return_pc": 4,
        "native_logic_id": 0, "actual_logic": 0, "containing_logic_executed": False}
    assert packet["design"]["current_game_visibility"] is None
    assert packet["design"]["picture"]["selection_basis"] == "explicit_designer_binding_not_runtime_observation"
    assert packet["design"]["cel"]["selection_basis"] == "explicit_designer_loop_and_cel"
    assert packet["render_contract"]["kind"] == "diagnostic_unoccluded_layer"
    assert packet["render_contract"]["priority_compositing"] is False
    assert len(packet["unknowns"]) >= 6
    assert packet["source_edit_proposal"]["write_performed"] is False
    assert packet["source_edit_proposal"]["full_logic_replay_qualified"] is False
    assert packet["source_edit_proposal"]["replacement_bytes"] == [37, 1, 13, 17]
    sessions = set()
    for name, coordinates in (("original", (7, 9)), ("edited", (13, 17))):
        run = report["runs"][name]
        assert packet["fragments"][name] == {
            "captured_scene": run["capture"], "observations": run["events"]}
        state = run["final_state"]
        assert state["guest"]["status"] == "return" and state["guest"]["retired"] == 2
        assert state["run"]["invocation"] == 1
        assert state["source"]["sha256"] == hashlib.sha256(bytes((37, 1, *coordinates, 0))).hexdigest()
        for actor in state["guest"]["actors"]:
            expected = coordinates if actor["id"] == 1 else (0, 0)
            assert (actor["x"], actor["y"]) == expected
        assert state["observation"]["dropped"] == 0
        assert state["observation"]["per_channel"]["disasm"]["stored"] == 2
        assert state["observation"]["per_channel"]["scene"]["stored"] == 1
        sessions.add(run["capture"]["view"]["session_id"])
    assert len(sessions) == 2
    for name, expected in (("background.idx", bytes([15]) * 26880),
                           ("priority.idx", bytes([4]) * 26880),
                           ("cel.idx", bytes((1, 2, 3, 15)))):
        assert (output / "helper" / name).read_bytes() == expected
        assert packet["assets"][name] == {"file": name, "bytes": len(expected),
                                           "sha256": hashlib.sha256(expected).hexdigest()}
    assert {p.name: p.read_bytes() for p in game.iterdir()} == originals


def test_failed_configuration_keeps_attachment_and_structured_receipts(authored, binary, tmp_path, monkeypatch):
    game, case, *_ = authored
    def fail_configure(self, **kwargs):
        pending = self.capture()
        raise SceneOperationError("configure", "control", {"pending_capture": pending}) from ValueError("injected setter failure")
    monkeypatch.setattr(trial.AGISceneHarness, "configure", fail_configure)
    output = tmp_path / "config-failed"
    with pytest.raises(SceneOperationError):
        trial.collect(binary, game, output, case)
    report = json.loads((output / "collection.json").read_text())
    assert report["status"] == "failed"
    run = report["runs"]["original"]
    assert run["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert run["attachment"]["view"]["guest"] == {"status": "ready", "pc": 0, "fault": None}
    assert run["attachment"]["view"]["checkpoint"]["retired"] == 0
    assert report["failure"]["operation"] == "configure"
    assert report["failure"]["operation_stage"] == "control"
    assert report["failure"]["stage"] == "original_fragment"
    assert report["failure"]["receipts"]["pending_capture"]["view"]["guest"] == {"status": "ready", "pc": 0, "fault": None}
    assert report["failure"]["receipts"]["pending_capture"]["view"]["checkpoint"]["retired"] == 0
    assert report["failure"]["cause"] == {"type": "ValueError", "message": "injected setter failure"}
    assert not (output / "helper").exists()


def test_unchanged_zero_position_refuses_unwitnessed_edit(authored, binary, tmp_path):
    game, case, *_ = authored
    volume = bytearray((game / "VOL.0").read_bytes())
    # Five-byte volume header, then payload offset 7 and two operand bytes.
    volume[14:16] = b"\0\0"
    (game / "VOL.0").write_bytes(volume)
    output = tmp_path / "no-change"
    with pytest.raises(ValueError, match="no captured position witness"):
        trial.collect(binary, game, output, case)
    report = json.loads((output / "collection.json").read_text())
    assert report["status"] == "failed" and report["failure"]["stage"] == "edit_plan"
    assert set(report["runs"]) == {"original"}
    state = report["runs"]["original"]["final_state"]
    assert state["guest"]["status"] == "return" and state["guest"]["retired"] == 2
    assert state["observation"]["per_channel"]["scene"]["stored"] == 0
    assert not (output / "helper").exists()


def test_late_export_failure_keeps_both_native_captures(authored, binary, tmp_path, monkeypatch):
    game, case, *_ = authored
    write_bytes = Path.write_bytes
    def fail_guide(self, data):
        if self.name == "PROTOCOL.md":
            raise OSError("injected packet export failure")
        return write_bytes(self, data)
    monkeypatch.setattr(Path, "write_bytes", fail_guide)
    output = tmp_path / "export-failed"
    with pytest.raises(OSError, match="injected packet"):
        trial.collect(binary, game, output, case)
    report = json.loads((output / "collection.json").read_text())
    assert report["status"] == "failed" and report["failure"]["stage"] == "packet_write"
    assert set(report["runs"]) == {"original", "edited"}
    assert all(run["final_state"]["guest"]["status"] == "return" for run in report["runs"].values())
