"""Public API witnesses for the explicitly selected raw QEMU-AGI target.

The program bytes below are authored from the AGI 2.917 action layout:
position.to(actor 0, x=42, y=73), then root return.  This is not a game or
original-runtime parity claim.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from fdisbull.qemu_agi_scene import observe as observe_scene


CODE = bytes((37, 0, 42, 73, 0))
RUNTIME_CODE = bytes((22, 8, 0))
CALLEE_CODE = bytes((3, 5, 1, 24, 5, 25, 5, 0))
PICTURE = bytes.fromhex("f005f208f60a140c14ff")
PROFILE = "agi-2917-scalar-position-pilot-1"


class _SyntheticSceneSession:
    def __init__(self, state, events, projection=None):
        self.vm = object()
        self.identity = {"source_sha256": state["source"]["sha256"],
                         "source_size": state["source"].get("size"),
                         "runtime_package_sha256": state["source"].get("sha256")
                         if state["source"]["profile"] == "agi-2917-runtime-1" else None}
        self._state_value = state
        self._events_value = events
        self._projection = projection

    @contextmanager
    def _budget(self, _vm, _deadline):
        yield

    def _stopped(self):
        pass

    def _state(self):
        return deepcopy(self._state_value)

    def _events(self):
        return deepcopy(self._events_value)

    def _json_property(self, _name):
        return deepcopy(self._projection)


def _synthetic_native_state(*, runtime=False):
    digest = "a" * 64
    profile = "agi-2917-runtime-1" if runtime else PROFILE
    schema = "fdisbull-agi-runtime-state-1" if runtime else "fdisbull-agi-native-state-1"
    source = {"sha256": digest, "profile": profile}
    if runtime:
        source.update(logic_id=8, logic_sha256="b" * 64)
    else:
        source.update(logic_id=0, size=5)
    observation = {"epoch": 4, "mask": 2, "capacity": 0, "count": 0,
                   "eligible": 0, "dropped": 0,
                   "per_channel": {name: {"eligible": 0, "stored": 0, "dropped": 0}
                                   for name in ("disasm", "scene")}}
    guest = {"actors": [{} for _ in range(256 if runtime else 16)]}
    if runtime:
        guest.update(scene_revision=1, presentation_revision=1, picture_shown=1)
    state = {"schema": schema, "source": source, "guest": guest, "observation": observation}
    events = {"schema": "fdisbull-agi-runtime-events-1" if runtime else "fdisbull-agi-native-events-1",
              "source": deepcopy(source), "epoch": 4, "events": []}
    if runtime:
        events["observation"] = deepcopy(observation)
    projection = None
    if runtime:
        projection = {"schema": "fdisbull-agi-runtime-scene-1", "source": deepcopy(source),
                      "width": 160, "height": 168, "revision": 1, "presentation": 1,
                      "picture_shown": 1, "visual": "00" * (160 * 168),
                      "priority": "00" * (160 * 168)}
    return state, events, projection


def _native_executable():
    value = os.environ.get("FDISBULL_QEMU_AGI")
    if not value:
        pytest.skip("Set FDISBULL_QEMU_AGI to run public native AGI API witnesses")
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI must name an executable native candidate")
    return path


def _project(path: Path, code=CODE):
    source = path / "logic.raw"
    source.write_bytes(code)
    database = path / "logic.fdb"
    project = Project.create(database, source, arch="agi", base=0, entry=0)
    return project, database, source


def test_synthetic_scene_observation_validation_is_read_only_and_fails_closed():
    state, events, projection = _synthetic_native_state()
    session = _SyntheticSceneSession(state, events, projection)
    result = observe_scene(session)
    assert result["projection"] is None
    assert result["state"] == state and result["events"] == events
    assert observe_scene(session) == result

    runtime_state, runtime_events, runtime_projection = _synthetic_native_state(runtime=True)
    runtime_session = _SyntheticSceneSession(runtime_state, runtime_events, runtime_projection)
    runtime_result = observe_scene(runtime_session)
    assert runtime_result["projection"] == runtime_projection
    runtime_events.pop("epoch")
    broken = _SyntheticSceneSession(runtime_state, runtime_events, runtime_projection)
    with pytest.raises(ValueError, match="inconsistent|Invalid|observation"):
        observe_scene(broken)

    invalid_projection = deepcopy(runtime_projection)
    invalid_projection["visual"] = "0" * (160 * 168 * 2 - 2)
    with pytest.raises(ValueError, match="projection|plane"):
        observe_scene(_SyntheticSceneSession(runtime_state, runtime_events | {"epoch": 4},
                                             invalid_projection))


def _scene_row(observation, *, opcode, before, after):
    events = observation["events"]
    assert events["schema"] == "fdisbull-agi-native-events-1"
    rows = [row for row in events["events"] if row.get("opcode") == opcode]
    assert len(rows) == 1, events
    row = rows[0]
    assert row["actor"] == 0
    assert row["before"]["x"] == before[0] and row["before"]["y"] == before[1]
    assert row["after"]["x"] == after[0] and row["after"]["y"] == after[1]
    return row


def test_python_session_reads_and_executes_authored_scene_change(tmp_path):
    executable = _native_executable()
    project, _, source = _project(tmp_path)
    with project:
        with project.debugger(str(executable), backend="qemu-agi") as session:
            initial = session.scene_observe()
            assert initial["schema"] == "fdisbull-qemu-agi-scene-observation-1"
            assert initial["state"]["source"]["sha256"] == hashlib.sha256(CODE).hexdigest()
            assert initial["state"]["source"]["profile"] == PROFILE
            assert initial["state"]["guest"]["actors"][0]["x"] == 0
            assert initial["state"]["guest"]["actors"][0]["y"] == 0

            # Repeated stopped reads must not consume observations or advance PC.
            again = session.scene_observe()
            assert again == initial
            regs_before = session.registers()
            regs_repeat = session.registers()
            assert regs_repeat == regs_before

            stepped = session.step()
            assert stepped["outcome"] == "step"
            observed = session.scene_observe()
            event = _scene_row(observed, opcode=37, before=(0, 0), after=(42, 73))
            assert observed["state"]["guest"]["actors"][0]["x"] == 42
            assert observed["state"]["guest"]["actors"][0]["y"] == 73
            assert event["pc"] == 0
            assert source.read_bytes() == CODE


def test_json_debug_surface_launches_steps_observes_and_cleans_up(tmp_path):
    executable = _native_executable()
    _, database, source = _project(tmp_path)
    workspace = DebugWorkspace()

    def invoke(method, **params):
        reply = respond({"method": method, "params": {"project": str(database), **params}},
                        debugger=workspace)
        assert reply["ok"], reply
        return reply["result"]

    try:
        launched = invoke("debug-launch", executable=str(executable), backend="qemu-agi")
        run = launched["run"]
        first = invoke("debug-agi-scene-observe", run=run)
        assert first["schema"] == "fdisbull-qemu-agi-scene-observation-1"
        assert first["state"]["source"]["sha256"] == hashlib.sha256(CODE).hexdigest()
        assert invoke("debug-agi-scene-observe", run=run) == first
        assert invoke("debug-registers", run=run) == invoke("debug-registers", run=run)
        stepped = invoke("debug-step", run=run)
        assert stepped["outcome"] == "step"
        after = invoke("debug-agi-scene-observe", run=run)
        _scene_row(after, opcode=37, before=(0, 0), after=(42, 73))
        assert after["state"]["guest"]["actors"][0]["x"] == 42
        assert source.read_bytes() == CODE
        stopped = invoke("debug-stop", run=run)
        assert stopped["process_reaped"] is True
    finally:
        workspace.close()


def test_qemu_agi_dispatch_refuses_non_profile_options_before_spawn(tmp_path):
    project, _, _ = _project(tmp_path)
    with project:
        with pytest.raises(ValueError, match="raw LOGIC profile"):
            project.debugger("/does/not/need/to/exist", backend="qemu-agi", window=True)


def test_qemu_agi_source_admission_rejects_patch_before_executable_lookup(tmp_path):
    project, _, _ = _project(tmp_path)
    with project:
        patched = project.patch(0, "00", label="test-only altered LOGIC")
        version = patched.get("id", patched.get("version"))
        with pytest.raises(ValueError, match="original unpatched raw LOGIC"):
            project.debugger("/does/not/need/to/exist", backend="qemu-agi", version=version)


def test_qemu_agi_capability_is_explicitly_experimental_and_not_selected():
    reply = respond({"method": "capabilities", "params": {}})
    assert reply["ok"], reply
    result = reply["result"]
    row = next(item for item in result["capabilities"] if item["id"] == "debug.qemu-agi")
    assert row["maturity"] == "experimental"
    assert row["availability"] == "not_checked"
    assert row["runtime_validation"] == "not_run"
    assert result["dependencies"]["qemu-system-agi"]["status"] == "not_selected"


def _runtime_package(path: Path):
    """Entry LOGIC 7 calls LOGIC 8 to draw an authored 160x168 picture."""
    def logic(ident, code):
        return {"id": ident, "code": code.hex(), "sha256": hashlib.sha256(code).hexdigest(),
                "messages": []}

    package = {
        "schema": "fdisbull-agi-runtime-package-1",
        "profile": "agi-2917-runtime-1",
        "entry_logic": 7,
        "logics": [logic(7, RUNTIME_CODE), logic(8, CALLEE_CODE)],
        "views": [], "pictures": [{"id": 1, "data": PICTURE.hex(),
                                      "sha256": hashlib.sha256(PICTURE).hexdigest()}],
        "sounds": [], "words": [], "objects": [],
    }
    path.write_text(json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def test_runtime_package_keeps_project_logic_identity_and_scene_observation(tmp_path):
    executable = _native_executable()
    project, _, source = _project(tmp_path, RUNTIME_CODE)
    package = _runtime_package(tmp_path / "runtime-package.json")
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as session:
            assert session.identity["source_sha256"] == hashlib.sha256(RUNTIME_CODE).hexdigest()
            assert session.identity["runtime_package_sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
            assert session.capabilities["registers"] is True
            assert session.capabilities["step"] is True
            assert session.capabilities["memory"] is False
            initial = session.scene_observe()
            assert initial["state"]["source"]["logic_id"] == 7
            assert initial["state"]["source"]["logic_sha256"] == hashlib.sha256(RUNTIME_CODE).hexdigest()
            assert initial["state"]["guest"]["logic"] == 7
            assert initial["state"]["guest"]["pc"] == 0
            initial_regs = session.registers()
            assert initial_regs["linear_pc"] is None
            assert initial_regs["logical_position"] == {
                "logic_id": 7, "pc": 0, "source_sha256": hashlib.sha256(RUNTIME_CODE).hexdigest()
            }
            assert session.scene_observe() == initial
            stepped = session.step()
            assert stepped["outcome"] == "step"
            in_callee = session.registers()
            assert in_callee["logical_position"]["logic_id"] == 8
            assert in_callee["logical_position"]["pc"] == 0
            assert in_callee["logical_position"]["source_sha256"] == hashlib.sha256(CALLEE_CODE).hexdigest()
            assert session.step()["outcome"] == "step"  # assignn(v5, 1)
            assert session.step()["outcome"] == "step"  # load.pic(v5)
            assert session.step()["outcome"] == "step"  # draw.pic(v5)
            observed = session.scene_observe()
            assert observed["state"]["source"]["logic_id"] == 8
            assert observed["state"]["source"]["logic_sha256"] == hashlib.sha256(CALLEE_CODE).hexdigest()
            assert observed["state"]["guest"]["logic"] == 8
            assert observed["events"]["schema"] == "fdisbull-agi-runtime-events-1"
            assert observed["events"]["source"] == observed["state"]["source"]
            projection = observed["projection"]
            assert projection["schema"] == "fdisbull-agi-runtime-scene-1"
            assert projection["source"] == observed["state"]["source"]
            assert (projection["width"], projection["height"]) == (160, 168)
            assert len(projection["visual"]) == len(projection["priority"]) == 160 * 168 * 2
            for x in (10, 11, 12):
                offset = (20 * 160 + x) * 2
                assert projection["visual"][offset:offset + 2] == "05"
                assert projection["priority"][offset:offset + 2] == "08"
            assert source.read_bytes() == RUNTIME_CODE


def test_json_runtime_launch_preserves_logical_location_and_scene_source(tmp_path):
    executable = _native_executable()
    _, database, source = _project(tmp_path, RUNTIME_CODE)
    package = _runtime_package(tmp_path / "runtime-package.json")
    workspace = DebugWorkspace()
    policy = OutputPolicy(65536, tmp_path / "json-output")

    def invoke(method, **params):
        request_params = dict(params)
        if method not in ("output-export",):
            request_params["project"] = str(database)
        with output_policy_context(policy):
            reply = respond({"method": method, "params": request_params}, debugger=workspace)
        assert reply["ok"], reply
        return reply["result"]

    def materialize(value, name):
        if value.get("format") != "fdisbull-output-ref-1":
            return value
        destination = tmp_path / f"{name}.json"
        invoke("output-export", artifact=value["artifact"]["id"], output=str(destination))
        exported = json.loads(destination.read_text())
        return exported["result"] if isinstance(exported, dict) and "result" in exported else exported

    try:
        launched = invoke("debug-launch", executable=str(executable), backend="qemu-agi",
                          agi_runtime_package=str(package))
        run = launched["run"]
        before_reply = invoke("debug-agi-scene-observe", run=run)
        assert before_reply["format"] == "fdisbull-output-ref-1"
        before = materialize(before_reply, "before")
        assert before["state"]["source"]["logic_id"] == 7
        assert before["state"]["guest"]["pc"] == 0
        repeat = materialize(invoke("debug-agi-scene-observe", run=run), "repeat")
        assert repeat == before
        stepped = invoke("debug-step", run=run)
        assert stepped["outcome"] == "step"
        registers = invoke("debug-registers", run=run)
        assert registers["logical_position"]["logic_id"] == 8
        assert registers["logical_position"]["pc"] == 0
        assert registers["logical_position"]["source_sha256"] == hashlib.sha256(CALLEE_CODE).hexdigest()
        assert registers["linear_pc"] is None
        assert invoke("debug-step", run=run)["outcome"] == "step"  # assignn(v5, 1)
        assert invoke("debug-step", run=run)["outcome"] == "step"  # load.pic(v5)
        assert invoke("debug-step", run=run)["outcome"] == "step"  # draw.pic(v5)
        after = materialize(invoke("debug-agi-scene-observe", run=run), "after")
        assert after["state"]["source"]["logic_id"] == 8
        assert after["state"]["source"]["logic_sha256"] == hashlib.sha256(CALLEE_CODE).hexdigest()
        assert after["events"]["source"] == after["state"]["source"]
        projection = after["projection"]
        assert projection["schema"] == "fdisbull-agi-runtime-scene-1"
        assert projection["source"] == after["state"]["source"]
        assert (projection["width"], projection["height"]) == (160, 168)
        assert len(projection["visual"]) == len(projection["priority"]) == 160 * 168 * 2
        for x in (10, 11, 12):
            offset = (20 * 160 + x) * 2
            assert projection["visual"][offset:offset + 2] == "05"
            assert projection["priority"][offset:offset + 2] == "08"
        assert source.read_bytes() == RUNTIME_CODE
        assert invoke("debug-stop", run=run)["process_reaped"] is True
    finally:
        workspace.close()


@pytest.mark.parametrize("code,expected", [(bytes((0,)), "return"), (bytes((255,)), "fault")])
def test_terminal_or_fault_step_is_stable_and_does_not_replay(tmp_path, code, expected):
    executable = _native_executable()
    project, _, _ = _project(tmp_path, code)
    with project:
        with project.debugger(str(executable), backend="qemu-agi") as session:
            first = session.step()
            assert first["outcome"] == expected
            assert first["retired"] == (1 if expected == "return" else 0)
            registers = session.registers()
            again = session.step()
            assert again["outcome"] == expected
            assert again["retired"] == 0
            assert session.registers() == registers


def test_runtime_pending_request_does_not_retire_or_replay(tmp_path):
    executable = _native_executable()
    pending_code = bytes((29, 0))  # Native show.pri.screen host request.
    project, _, _ = _project(tmp_path, pending_code)
    package = _runtime_package(tmp_path / "runtime-package.json")
    value = json.loads(package.read_text())
    value["entry_logic"] = 7
    value["logics"] = [{"id": 7, "code": pending_code.hex(),
                        "sha256": hashlib.sha256(pending_code).hexdigest(), "messages": []}]
    package.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    with project:
        with project.debugger(str(executable), backend="qemu-agi",
                              agi_runtime_package=str(package)) as session:
            before = session.registers()
            first = session.step()
            assert first["outcome"] == "pending"
            assert first["retired"] == 0
            stopped = session.state()["guest"]
            assert stopped["status"] == "pending"
            again = session.step()
            assert again["outcome"] == "pending"
            assert again["retired"] == 0
            assert session.registers() == before
            assert session.state()["guest"] == stopped


def test_runtime_package_entry_identity_mismatch_is_rejected_and_unregistered(tmp_path):
    executable = _native_executable()
    project, _, _ = _project(tmp_path, RUNTIME_CODE)
    package = _runtime_package(tmp_path / "runtime-package.json")
    value = json.loads(package.read_text())
    mismatch = bytes((0,))
    value["logics"][0].update(code=mismatch.hex(), sha256=hashlib.sha256(mismatch).hexdigest())
    package.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    with project:
        with pytest.raises(DebuggerError, match="source identity"):
            project.debugger(str(executable), backend="qemu-agi", agi_runtime_package=str(package))
        assert project.db.execute("SELECT COUNT(*) FROM debug_runs").fetchone()[0] == 0
