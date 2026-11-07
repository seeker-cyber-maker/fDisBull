"""Boundary, ownership and failure contracts for live execution predicates."""
from copy import deepcopy
import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.execution_trace import ExecutionTraceSessionMixin


class Session(ExecutionTraceSessionMixin):
    """A stopped RPC peer; stepping is the only operation which changes its PC."""

    def __init__(self):
        self.closed = False
        self.run_id = "owned-run"
        self.version = {"id": 1, "sha256": "2" * 64}
        self.metadata = {"backend": "dosbox", "source_sha256": "1" * 64,
                         "version_sha256": "2" * 64,
                         "runtime_load_segment": 0x2000, "static_load_segment": 0x1000}
        self.project = SimpleNamespace(
            regions=lambda version: [SimpleNamespace(name="loaded_image", start=0x10100,
                                                     data=b"\xb8\x07\x00\x40\x90\xeb\xfe")])
        self.delta = 0x10000
        self.runtime_load = 0x2000
        self.dos = {"load_segment": 0x1000}
        self.rpc = SimpleNamespace(capabilities={"trace": {"cpu": True}, "input": {"absolute_mouse": True, "keyboard": "ibm_pc_controller_us_ascii_v1"}})
        self.pc = 0x100
        self.eax = 0
        self.revision = 1
        self.breakpoints = []
        self.calls = []
        self.artifacts = []
        self.journal = []
        self.inputs = []
        self.native_kind = "pause"
        self.initial_kind = "startup"
        self.trace_active = False
        self.trace_events = []
        self.interval_entry_shift = False
        self.omit_changed_register = False
        self.fail_step = None
        self.fail_capture = False
        self.running = False
        self._layers = []
        self._runtime_epoch = "epoch-1"

    def project_address(self, address):
        value = int(address["segment"], 16) * 16 + int(address["offset"], 16)
        return hex(value - self.delta) if 0x20100 <= value < 0x20107 else None

    def _runtime_state(self):
        return {}

    def layers(self):
        return {"active": self._layers}

    def registers(self):
        return self.call("state.get_registers")

    def click(self, x, y, **options):
        self.inputs.append({"x": x, "y": y, **options})
        return {"queued": True, "state_revision": self.revision}

    def keyboard_press(self, key, **options):
        self.inputs.append({"key": key, **options})
        return {"queued": True}

    def _event(self, operation, evidence):
        self.journal.append((operation, deepcopy(evidence)))

    def _artifact(self, name, kind, data, metadata):
        result = {"artifact": "trace-" + str(len(self.artifacts) + 1), "kind": kind,
                  "sha256": hashlib.sha256(data).hexdigest(), "metadata": metadata}
        self.artifacts.append((result, json.loads(data)))
        return result

    def close(self):
        self.closed = True

    def fetch(self):
        registers = self.call('state.get_registers')
        address = dict(space='segmented', segment='0x2000', offset=hex(self.pc))
        raw = self.call('memory.read', {'address': {'offset': hex(0x20000 + self.pc)}, 'length': 15})
        return dict(sequence=1, address=address, cpu_mode='real', code_bits=16,
                    execution_bytes=base64.b64decode(raw['data_base64']).hex(),
                    register_changes={**registers['general'], **registers['segments'],
                                      'flags': registers['flags'], 'instruction_pointer': hex(self.pc)})

    def call(self, method, params=None):
        self.calls.append((method, deepcopy(params)))
        if method == "session.status":
            return {"state": "running" if self.running else "stopped", "state_revision": self.revision,
                    "last_stop": {"kind": self.native_kind if self.pc != 0x100 else self.initial_kind}}
        if method == "breakpoints.list":
            return {"breakpoints": deepcopy(self.breakpoints)}
        if method == "state.get_registers":
            return {"cpu_mode": "real", "code_bits": 16, "stack_bits": 16,
                    "address_context": {"cpu_mode": "real", "paging_enabled": False,
                                        "a20_enabled": False, "cr0": "0x10", "cr3": "0x0", "cr4": "0x0",
                                        "code_bits": 16, "stack_bits": 16},
                    "general": {key: hex(self.eax if key == "eax" else 0) for key in
                                ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp")},
                    "segments": {key: "0x2000" for key in ("cs", "ds", "es", "ss", "fs", "gs")},
                    "instruction_pointer": hex(self.pc), "flags": "0x202", "state_revision": self.revision}
        if method == "memory.read":
            if self.fail_capture:
                raise OSError("capture unavailable")
            address = int(params["address"]["offset"], 16)
            data = b"\xb8\x07\x00\x40\x90\xeb\xfe".ljust(32, b"\x90")
            raw = data[address - 0x20100:address - 0x20100 + params["length"]]
            return {"data_base64": base64.b64encode(raw).decode(),
                    "sha256": hashlib.sha256(raw).hexdigest(), "overlay_valid": True}
        if method == 'trace.read':
            return dict(active=self.trace_active, events=deepcopy(self.trace_events[:params['limit']]), next_cursor=None)
        if method == 'trace.start':
            self.trace_active = True
            self.trace_events = []
            return {'active': True}
        if method == 'trace.stop':
            self.trace_active = False
            return {'active': False}
        if method == "execution.continue":
            if self.fail_step:
                self.running = True
                raise self.fail_step
            before = self.fetch()
            if self.interval_entry_shift:
                before['address']['offset'] = hex(self.pc + 1)
            if self.pc == 0x100:
                self.eax = 7
                self.pc = 0x103
            elif self.pc == 0x103:
                self.eax = 8
                self.pc = 0x104
            elif self.pc == 0x104:
                self.pc = 0x105
            self.revision += 1
            after = self.fetch()
            after['sequence'] = 2
            if self.omit_changed_register:
                del after['register_changes']['eax']
            self.trace_events = [before, after]
            self.trace_active = False
            return {'operation_id': 'interval-owned'}
        if method == "execution.pause":
            self.running = False
            return {"operation_id": "pause-owned"}
        if method == "execution.wait":
            return {"running": False, "state": "stopped", "stop_reason": {"kind": self.native_kind}}
        raise AssertionError(method)


def steps(session):
    return [params for method, params in session.calls if method == "execution.continue"]


def test_initial_match_does_not_step_or_queue_action():
    session = Session()
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 0},
                                 action={"op": "click", "x": 10, "y": 20})
    assert result["matched"] and result["exact_stop"] and result["steps"] == 0
    assert not steps(session) and not session.inputs
    assert result["action"]["dispatch"] == "skipped_initial_match"


def test_register_predicate_stops_before_next_increment_and_keeps_one_trace():
    session = Session()
    result = session.trace_until({"kind": "register", "register": "ax", "equals": 7})
    assert result["matched"] and result["exact_stop"] and result["steps"] == 1
    assert session.pc == 0x103 and session.eax == 7
    assert len(steps(session)) == 1 and len(session.artifacts) == 1
    artifact, document = session.artifacts[0]
    assert result["trace_artifact"] == artifact["artifact"]
    assert len(document["events"]) == 2 and document["window"]["closed"]
    assert document["events"][-1]["observation"]["instruction_completed"] is False


def test_armed_execution_breakpoint_precedes_matching_predicate_without_consumption():
    session = Session()
    point = {"breakpoint_id": "foreign-once", "kind": "execution", "enabled": True, "once": True,
             "address": {"space": "segmented", "segment": "0x2000", "offset": "0x103"}}
    session.breakpoints.append(point)
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 7})
    assert result["outcome"] == "foreign_stop" and not result["matched"]
    assert result["steps"] == 1 and session.eax == 7
    assert session.breakpoints == [point]
    assert not any(method == "breakpoints.delete" for method, _ in session.calls)


@pytest.mark.parametrize("fault", ["watch", "layer", "predicate", "region", "action"])
def test_invalid_or_unqualified_controls_refuse_before_input_and_execution(fault):
    session = Session()
    options = {"action": {"op": "click", "x": 10, "y": 20}}
    predicate = {"kind": "register", "register": "eax", "equals": 7}
    if fault == "watch":
        session.breakpoints = [{"kind": "memory_change", "enabled": True, "breakpoint_id": "watch"}]
    elif fault == "layer":
        session._layers = ["active-execution-layer"]
    elif fault == "predicate":
        predicate["invented"] = True
    elif fault == "region":
        options["regions"] = [{"id": "bad", "space": "project", "start": 4, "end": 3}]
    else:
        options["action"] = {"op": "run", "guest_ms": 10}
    with pytest.raises(ValueError):
        session.trace_until(predicate, **options)
    assert not steps(session) and not session.inputs


def test_budget_is_explicit_and_does_not_claim_a_match():
    session = Session()
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 99}, max_steps=2)
    assert result["outcome"] == "step_budget" and not result["matched"]
    assert not result["exact_stop"] and result["steps"] == 2
    assert len(steps(session)) == 2 and session.pc == 0x104
    assert session.artifacts[0][1]["window"]["closed"]


def test_native_nonstep_stop_has_precedence_over_predicate():
    session = Session()
    session.native_kind = "watchpoint"
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 7})
    assert result["outcome"] == "foreign_stop" and not result["matched"]
    assert len(steps(session)) == 1
    assert not session.artifacts[0][1]["window"]["closed"]


def test_uncertain_step_timeout_pauses_owned_guest_without_replaying():
    session = Session()
    session.fail_step = TimeoutError("native reply lost")
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 7})
    assert result["outcome"] == "timeout" and not result["matched"]
    assert result["attempted_steps"] == 1 and len(steps(session)) == 1
    assert not session.running and not session.artifacts[0][1]["window"]["closed"]
    assert any(method == "execution.pause" for method, _ in session.calls)


def test_queued_input_is_retained_without_claiming_game_consumption():
    session = Session()
    result = session.trace_until({"kind": "register", "register": "eax", "equals": 7},
                                 action={"op": "click", "x": 10, "y": 20}, label="button-A")
    assert result["action"]["dispatch"] == "queued"
    assert result["action"]["game_consumption_proven"] is False
    assert len(session.inputs) == 1 and result["label"] == "button-A"


@pytest.mark.parametrize('reason', ['exception', 'breakpoint', 'guest_exit', 'unknown-stop'])
def test_initial_foreign_stop_cannot_be_overridden_or_stepped(reason):
    session = Session()
    session.initial_kind = reason
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 0},
                                 action={'op': 'click', 'x': 10, 'y': 20})
    assert not result['matched'] and not steps(session) and not session.inputs
    assert result['foreign_stop']['kind'] == reason
    assert not session.artifacts[0][1]['window']['closed']


def test_zero_step_budget_does_not_queue_unconsumable_action():
    session = Session()
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7},
        max_steps=0, action={'op': 'click', 'x': 10, 'y': 20})
    assert result['outcome'] == 'step_budget' and not session.inputs and not steps(session)


def test_cancellation_stops_owned_guest_retains_partial_evidence_and_reraises():
    session = Session()
    session.fail_step = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as caught:
        session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7})
    result = caught.value.result
    assert result['outcome'] == 'cancelled' and not result['matched']
    assert result['attempted_steps'] == 1 and not session.running
    assert result['cleanup']['stopped'] and len(steps(session)) == 1
    assert not session.artifacts[0][1]['window']['closed']


def test_unexpected_first_fetch_does_not_claim_exact_match_or_closed_window():
    session = Session()
    session.interval_entry_shift = True
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7})
    assert result['outcome'] == 'unqualified_interval'
    assert not result['matched'] and not result['exact_stop'] and not result['complete']
    assert result['steps'] == 0 and result['attempted_steps'] == 1
    assert session.pc == 0x103 and result['current_stop']['address']['offset'] == '0x103'
    assert not session.artifacts[0][1]['window']['closed']


def test_active_native_trace_is_preserved_before_input_or_execution():
    session = Session()
    session.trace_active = True
    with pytest.raises(ValueError, match='active native trace'):
        session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7},
                            action={'op': 'click', 'x': 10, 'y': 20})
    assert session.trace_active and not steps(session) and not session.inputs


def test_artifact_reserve_stops_before_an_interval_without_losing_evidence(monkeypatch):
    import fdisbull.execution_trace as module
    monkeypatch.setattr(module, 'MAX_TRACE_BYTES', 270000)
    session = Session()
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7},
                                action={'op': 'click', 'x': 10, 'y': 20})
    assert result['outcome'] == 'artifact_budget' and not result['matched']
    assert not steps(session) and not session.inputs
    assert not session.artifacts[0][1]['window']['closed']


def test_cleanup_failures_retain_evidence_and_original_capture_epoch():
    session = Session()
    session.fail_step = TimeoutError('continuation uncertain')
    original_call = session.call

    def call(method, params=None):
        if method == 'trace.stop':
            raise OSError('collector cleanup unavailable')
        return original_call(method, params)

    def close():
        session.closed = True
        session._runtime_epoch = 'after-close'
        raise OSError('close journal unavailable')

    session.call, session.close = call, close
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7})
    assert result['outcome'] == 'timeout' and result['trace_artifact']
    assert result['trace_cleanup_error']['closed']
    assert result['trace_cleanup_error']['close_error']['message'] == 'close journal unavailable'
    assert session.artifacts[0][1]['capture_epoch'] == 'epoch-1'


def test_initial_foreign_stop_with_zero_budget_never_sets_artifact_complete():
    session = Session()
    session.initial_kind = 'exception'
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 0}, max_steps=0)
    assert result['outcome'] == 'foreign_stop' and not result['complete']
    artifact, document = session.artifacts[0]
    assert not artifact['metadata']['complete'] and not document['complete']
    assert not document['window']['closed']


def test_missing_register_delta_cannot_qualify_the_final_stop_phase():
    session = Session()
    session.omit_changed_register = True
    result = session.trace_until({'kind': 'register', 'register': 'eax', 'equals': 7})
    assert session.eax == 7 and result['outcome'] == 'unqualified_interval'
    assert not result['matched'] and not result['exact_stop']
