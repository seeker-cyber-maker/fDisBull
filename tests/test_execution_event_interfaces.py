"""Public event workflows keep ownership, preflight and partial evidence intact."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from fdisbull.cli import METHODS, invoke, main, respond
from fdisbull.debug_script import execute_script
from fdisbull.debug_semantics import contract, normalize_trace
from fdisbull.debugger import DebugWorkspace
from fdisbull.execution_trace import ExecutionTraceError, validate_trace_until
from fdisbull.project import Project


PREDICATE = {"kind": "register", "register": "ax", "equals": 7}


class RouteSession:
    """An interface peer; native boundary behavior is covered by runner tests."""

    def __init__(self, path):
        self.project = SimpleNamespace(path=Path(path).resolve())
        self.run_id = "owned-route"
        self.metadata = {"backend": "dosbox"}
        self.rpc = SimpleNamespace(capabilities={})
        self.closed = False
        self.calls = []
        self.artifacts = []
        self.failure = None
        self.result = {"outcome": "predicate", "matched": True,
                       "complete": True, "exact_stop": True,
                       "trace_artifact": "retained-trace", "steps": 1,
                       "current_stop": {"address": {"space": "segmented",
                                                     "segment": "0x2000", "offset": "0x103"}},
                       "action": {"dispatch": "not_requested"}}

    def click(self, x, y, *, button="left", hold_ms=80, mode_id=None, frame_id=None):
        self.calls.append(("click", {"x": x, "y": y}))
        return {"queued": True}

    def status(self):
        self.calls.append(("status", {}))
        return {"state": "stopped"}

    def keyboard_press(self, key, *, modifiers=None, hold_ms=40, gap_ms=40):
        self.calls.append(("keyboard.press", {"key": key}))
        return {"queued": True}

    def trace_until(self, until, *, regions=None, max_steps=1000, timeout_ms=10000,
                    name="trace-until.json", action=None, label="trial"):
        options = dict(until=until, regions=regions, max_steps=max_steps,
                       timeout_ms=timeout_ms, name=name, action=action, label=label)
        validate_trace_until(**options)
        self.calls.append(("trace-until", deepcopy(options)))
        if self.failure is not None:
            raise self.failure
        return deepcopy(self.result)

    def _artifact(self, name, kind, data, metadata):
        artifact = {"artifact": "route-artifact-" + str(len(self.artifacts)),
                    "sha256": hashlib.sha256(data).hexdigest(), "kind": kind}
        self.artifacts.append((artifact, json.loads(data)))
        return artifact

    def close(self):
        self.closed = True


def route(*steps):
    return {"format": "fdisbull-script-1", "steps": list(steps)}


def live_request(session, **options):
    return {"id": "trace-request", "method": "debug-trace-until", "params": {
        "project": str(session.project.path), "run": session.run_id,
        "until": deepcopy(PREDICATE), **options}}


def test_live_json_preserves_typed_request_and_requires_workspace_ownership(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    regions = [{"id": "handler", "space": "project", "start": "0x10100", "end": "0x10110"}]
    request = live_request(session, max_steps=9, timeout_ms=321, regions=regions,
                           action={"op": "keyboard.press", "key": "enter"}, label="button A")
    original = deepcopy(request)
    reply = respond(request, debugger=workspace)
    assert reply["ok"] and reply["id"] == "trace-request"
    assert reply["result"]["trace_artifact"] == "retained-trace"
    assert request == original
    operation, supplied = session.calls[0]
    assert operation == "trace-until" and supplied["until"] == PREDICATE
    assert supplied["regions"] == regions and supplied["max_steps"] == 9
    assert supplied["timeout_ms"] == 321 and supplied["label"] == "button A"
    assert supplied["action"] == {"op": "keyboard.press", "key": "enter"}
    assert not session.closed


@pytest.mark.parametrize("fault", ["missing-run", "different-project", "pending-run", "no-workspace"])
def test_live_ownership_refusals_happen_before_trace_dispatch(tmp_path, fault):
    session = RouteSession(tmp_path / "owned.fdb")
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    request = live_request(session)
    if fault == "missing-run":
        request["params"]["run"] = "historical-run"
    elif fault == "different-project":
        request["params"]["project"] = str(tmp_path / "another.fdb")
    elif fault == "pending-run":
        workspace.async_runs["active-operation"] = {
            "run": session.run_id, "done": threading.Event()}
    else:
        workspace = None
    reply = respond(request, debugger=workspace)
    assert not reply["ok"] and reply["error"]["type"] == "ValueError"
    assert session.calls == [] and not session.closed


def test_live_json_retains_partial_result_when_trace_persistence_fails(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    retained = deepcopy(session.result)
    retained["persistence_error"] = {"type": "OSError", "message": "journal unavailable"}
    session.failure = ExecutionTraceError(retained, OSError("journal unavailable"))
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    reply = respond(live_request(session), debugger=workspace)
    assert not reply["ok"]
    assert reply["error"]["result"] == retained
    assert len(session.calls) == 1 and not session.closed


@pytest.mark.parametrize("change", [
    {"until": {"kind": "register", "register": "ax", "equals": "$earlier.value"}},
    {"until": {"kind": "invented"}},
    {"max_steps": 10000},
    {"timeout_ms": 0},
    {"regions": [{"id": "bad", "space": "project", "start": 9, "end": 8}]},
    {"action": {"op": "run", "guest_ms": 1}},
    {"action": {"op": "keyboard.press", "key": "ENTER"}},
    {"name": "../outside.json"},
    {"name": "$earlier.name"},
    {"label": "$earlier.label"},
    {"regions": [{"id": "$earlier.id", "space": "project", "start": 1, "end": 2}]},
    {"regions": [{"id": "region", "name": "$earlier.name", "space": "project", "start": 1, "end": 2}]},
])
def test_malformed_later_trace_is_rejected_before_earlier_input(tmp_path, change):
    session = RouteSession(tmp_path / "owned.fdb")
    trace = {"op": "trace-until", "until": deepcopy(PREDICATE), **change}
    script = route({"op": "click", "x": 1, "y": 2, "as": "earlier"}, trace)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, script)
    assert session.calls == [] and session.artifacts == []
    assert not session.closed


def test_trace_script_backend_refusal_precedes_earlier_input(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    session.metadata["backend"] = "wine-qemu"
    script = route({"op": "click", "x": 1, "y": 2},
                   {"op": "trace-until", "until": PREDICATE})
    with pytest.raises(ValueError, match="DOSBox"):
        execute_script(session, script)
    assert session.calls == [] and session.artifacts == []


@pytest.mark.parametrize("outcome,flags", [
    ("step_budget", (False, False, False)),
    ("foreign_stop", (False, False, False)),
    ("timeout", (False, False, False)),
    ("predicate", (False, True, True)),
    ("predicate", (True, False, True)),
    ("predicate", (True, True, False)),
])
def test_unmet_trace_contract_stops_script_and_preserves_receipt(tmp_path, outcome, flags):
    session = RouteSession(tmp_path / "owned.fdb")
    session.result.update(outcome=outcome, complete=flags[0], matched=flags[1], exact_stop=flags[2])
    bindings = {}
    callbacks = []
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE, "as": "found"},
        {"op": "click", "x": 2, "y": 3}),
        _bindings_out=bindings, _after_step=lambda *args: callbacks.append(args))
    assert not report["ok"] and report["completed_steps"] == 0
    assert report["requested_steps"] == 2 and len(report["steps"]) == 1
    assert report["error"]["op"] == "trace-until"
    assert report["steps"][0]["result"] == session.result
    assert [name for name, _ in session.calls] == ["trace-until"]
    assert not bindings and not callbacks and not session.closed


def test_successful_trace_script_preserves_alias_and_limits_nested_deadline(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    bindings = {}
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE, "timeout_ms": 10000, "as": "found"},
        {"op": "assert", "value": "$found.trace_artifact", "equals": "retained-trace"},
        {"op": "status"}), timeout_ms=1000, _bindings_out=bindings)
    assert report["ok"] and report["completed_steps"] == 3
    assert 1 <= session.calls[0][1]["timeout_ms"] <= 1000
    assert [name for name, _ in session.calls] == ["trace-until", "status"]
    assert bindings["found"]["trace_artifact"] == "retained-trace"
    assert [artifact[0]["kind"] for artifact in session.artifacts] == ["script", "script-result"]


@pytest.mark.parametrize("dispatch", ["queued", "uncertain"])
@pytest.mark.parametrize("action", [{"op": "keyboard.press", "key": "enter"},
                                    {"op": "click", "x": 2, "y": 3}])
def test_failed_trace_with_possible_queued_input_closes_owned_guest(tmp_path, dispatch, action):
    session = RouteSession(tmp_path / "owned.fdb")
    session.result.update(outcome="timeout", complete=False, matched=False, exact_stop=False,
                          action={"dispatch": dispatch})
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE, "action": action},
        {"op": "click", "x": 2, "y": 3}))
    assert not report["ok"] and session.closed
    assert report["input_cleanup"]["closed"]
    assert report["steps"][0]["result"]["action"]["dispatch"] == dispatch
    assert [name for name, _ in session.calls] == ["trace-until"]


@pytest.mark.parametrize("outcome", ["foreign_stop", "step_budget"])
@pytest.mark.parametrize("action", [{"op": "keyboard.press", "key": "enter"},
                                    {"op": "click", "x": 2, "y": 3}])
def test_failed_trace_without_dispatched_input_preserves_stopped_guest(tmp_path, outcome, action):
    session = RouteSession(tmp_path / "owned.fdb")
    session.result.update(outcome=outcome, complete=False, matched=False, exact_stop=False,
                          action={"dispatch": "not_dispatched"})
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE, "action": action},
        {"op": "click", "x": 2, "y": 3}))
    assert not report["ok"] and not session.closed
    assert report["input_cleanup"] is None
    assert [name for name, _ in session.calls] == ["trace-until"]


def test_skipped_trace_input_does_not_erase_earlier_script_input_ownership(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    session.result.update(outcome="foreign_stop", complete=False, matched=False, exact_stop=False,
                          action={"dispatch": "not_dispatched"})
    report = execute_script(session, route(
        {"op": "keyboard.press", "key": "enter"},
        {"op": "trace-until", "until": PREDICATE,
         "action": {"op": "keyboard.press", "key": "enter"}},
        {"op": "status"}))
    assert not report["ok"] and session.closed and report["completed_steps"] == 1
    assert report["input_cleanup"]["closed"]
    assert [name for name, _ in session.calls] == ["keyboard.press", "trace-until"]


def test_trace_script_keeps_result_on_evidence_persistence_exception(tmp_path):
    session = RouteSession(tmp_path / "owned.fdb")
    session.failure = ExecutionTraceError(deepcopy(session.result), OSError("trace journal unavailable"))
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE}, {"op": "status"}))
    assert not report["ok"] and report["steps"][0]["result"] == session.result
    assert [name for name, _ in session.calls] == ["trace-until"]
    assert not session.closed


@pytest.mark.parametrize("dispatch", ["not_requested", "not_dispatched", "skipped_initial_match"])
def test_trace_persistence_error_with_proven_no_input_preserves_stopped_guest(tmp_path, dispatch):
    session = RouteSession(tmp_path / "owned.fdb")
    session.result["action"] = {"dispatch": dispatch}
    session.failure = ExecutionTraceError(deepcopy(session.result), OSError("trace journal unavailable"))
    report = execute_script(session, route(
        {"op": "trace-until", "until": PREDICATE,
         "action": {"op": "keyboard.press", "key": "enter"}},
        {"op": "status"}))
    assert not report["ok"] and not session.closed
    assert report["input_cleanup"] is None
    assert report["steps"][0]["result"]["action"]["dispatch"] == dispatch
    assert report["steps"][0]["result"]["current_stop"] == session.result["current_stop"]
    assert [name for name, _ in session.calls] == ["trace-until"]


def _save_authored_trace(project, run, values):
    version = project.version()
    mapping = {"source_sha256": project.meta["source_sha256"], "version_sha256": version["sha256"],
               "static_load_segment": 0x1000, "runtime_load_segment": 0x800, "backend": "dosbox"}
    events = []
    for index, value in enumerate(values):
        offset = 0x100 + index
        events.append({"sequence": index + 1,
                       "address": {"space": "segmented", "segment": "0x800", "offset": hex(offset)},
                       "cpu_mode": "real", "code_bits": 16, "stack_bits": 16,
                       "execution_bytes": "90", "project_address": hex(0x10000 + offset),
                       "register_changes": {"eax": hex(value), "cs": "0x800", "instruction_pointer": hex(offset)}})
    normalize_trace("dosbox", events, version=version["id"], delta=-0x8000, budget_reached=True)
    document = {"run": {"run": run}, "version": version["id"], "mapping": mapping,
                "events": events, "observation_contract": contract("dosbox"),
                "requested_count": len(events), "complete": True}
    with project.transaction(True):
        project.db.execute("INSERT INTO debug_runs VALUES (?,?,?,?,?,?)",
                           (run, version["id"], "authored", None, "stopped", json.dumps(mapping)))
        return project._debug_artifact(run, "authored-trace.json", "trace", json.dumps(document).encode(),
                                       {"event_count": len(events), "complete": True})["artifact"]


def test_cli_narrows_register_values_and_queries_history_after_project_reopen(tmp_path, capsys):
    binary = tmp_path / "authored.com"
    binary.write_bytes(b"\x90" * 16 + b"\xeb\xfe")
    path = tmp_path / "events.fdb"
    with Project.create(path, binary, image="com") as project:
        a = _save_authored_trace(project, "action-a", [1, 3])
        b = _save_authored_trace(project, "action-b", [2, 3])

    def command(*args):
        assert main(list(args)) == 0
        reply = json.loads(capsys.readouterr().out)
        assert reply["ok"]
        return reply["result"]

    predicate = json.dumps({"kind": "register", "register": "ax", "ge": 1})
    started = command("event-search-start", str(path), a, "--feature", "register-value",
                      "--register", "AX", "--predicate", predicate, "--label", "button A")
    refined = command("event-search-refine", str(path), started["artifact"], b,
                      "--mode", "exclude", "--label", "button B")
    page = command("event-search-results", str(path), refined["artifact"], "--offset", "0", "--limit", "1")
    assert refined["artifact"] != started["artifact"]
    assert len(page["rows"]) == 1 and page["rows"][0]["register"] == "ax"
    assert page["rows"][0]["value"] == 1
    assert int(str(page["rows"][0]["site"]["address"]), 0) == 0x10100
    historical = command("event-trace-query", str(path), a, "--predicate", predicate,
                         "--offset", "1", "--limit", "1")
    assert historical["matched_count"] == 2 and historical["rows"][0]["index"] == 1
    assert historical["complete"] and historical["unknown_count"] == 0
    original = command("event-search-results", str(path), started["artifact"])
    assert len(original["rows"]) == 2


def test_discovery_exposes_distinct_live_and_offline_scope_without_qualification():
    expected = {"debug-trace-until", "event-search-start", "event-search-refine",
                "event-search-results", "event-trace-query"}
    assert expected <= METHODS.keys()
    methods = respond({"method": "help"})
    assert methods["ok"] and expected <= methods["result"]["methods"].keys()
    capabilities = invoke("capabilities", {})
    item = next(row for row in capabilities["capabilities"] if row["id"] == "debug.execution-search")
    assert item["implementation"] == "partial" and item["runtime_validation"] == "not_run"
    assert "Live DOS16" in item["scope"] and "offline" in item["scope"]
    reference = "references/execution-event-search.md"
    text = invoke("agent-skill", {"reference": reference})["files"][reference]
    assert "trace_until" in text and "event_search_start" in text
