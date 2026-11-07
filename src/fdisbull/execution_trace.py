"""Bounded predicates at owned, stopped DOS instruction boundaries.

Two-fetch trace intervals use native Continue without the ordinary ``run``
hook dispatcher. This preserves DOSBox callback dispatch, unlike its low-level
step operation. Both endpoint observations are checked. An interrupt before
the first fetch leaves an incomplete interval, never an exact-match claim.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import time

from .debug_timeline import timeline_locked
from .external_files import _file_name
from .operation_budget import rpc_budget, run_cleanup_scope


MAX_STEPS = 9999  # Include the initial boundary in the 10,000-event budget.
MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_BOUNDARY_BYTES = 8192


class ExecutionTraceError(ValueError):
    """Retain the observed result when its final artifact/journal cannot be saved."""

    def __init__(self, result, error):
        self.result = result
        super().__init__("Execution trace result requires inspection: " + str(error))


def _bounded(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in {low}..{high}")
    return value


def _number(value, label, high=0xffffffff):
    if isinstance(value, str):
        try:
            value = int(value, 16 if value.lower().startswith("0x") else 10)
        except ValueError:
            raise ValueError("Invalid " + label) from None
    return _bounded(value, label, 0, high)


def _label(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or any(ord(char) < 32 for char in value)):
        raise ValueError("label must contain 1..128 printable characters")
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_action(action):
    """Validate only the existing queued-input methods, before any dispatch."""
    if action is None:
        return None
    if not isinstance(action, dict):
        raise ValueError("trace-until action must be a queued input descriptor")
    result = deepcopy(action)
    operation = result.get("op")
    if operation == "click":
        allowed = {"op", "x", "y", "button", "hold_ms", "mode_id", "frame_id"}
        if set(result) - allowed or not {"x", "y"} <= set(result):
            raise ValueError("click requires x and y, with existing mouse options")
        _bounded(result["x"], "x", 0, 4095)
        _bounded(result["y"], "y", 0, 4095)
        _bounded(result.get("hold_ms", 80), "hold_ms", 1, 1000)
        if result.get("button", "left") not in ("left", "right", "middle"):
            raise ValueError("Invalid mouse button")
        for field in ("mode_id", "frame_id"):
            if field in result:
                _bounded(result[field], field, 0, (1 << 53) - 1)
    elif operation == "keyboard.press":
        from .keyboard_input import validate_keyboard
        if set(result) - {"op", "key", "modifiers", "hold_ms", "gap_ms"} or "key" not in result:
            raise ValueError("keyboard.press requires a physical key and existing key options")
        validate_keyboard(**{key: value for key, value in result.items() if key != "op"})
    else:
        raise ValueError("trace-until action supports click or keyboard.press")
    return result


def validate_trace_until(until, *, regions=None, max_steps=1000, timeout_ms=10000,
                         name="trace-until.json", action=None, label="trial"):
    from .execution_events import validate_predicate, validate_regions
    predicate = validate_predicate(until)
    normalized_regions = None if regions is None else validate_regions(regions)
    _bounded(max_steps, "max_steps", 0, MAX_STEPS)
    _bounded(timeout_ms, "timeout_ms", 1, 600000)
    _file_name(name)
    _label(label)
    return predicate, normalized_regions, validate_action(action)


def _needs_region(predicate):
    if predicate.get("kind") == "region-change":
        return True
    return any(_needs_region(child) for key in ("all", "any")
               for child in predicate.get(key, []))


def _native_controls(session):
    """Read controls without consuming a once breakpoint or running a hook."""
    reply = session.call("breakpoints.list")
    items = reply.get("breakpoints")
    if not isinstance(items, list) or len(items) > 4096:
        raise ValueError("A bounded native breakpoint inventory is required")
    controls = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid native breakpoint inventory")
        if item.get("enabled") is False:
            continue
        if item.get("kind") != "execution":
            raise ValueError("trace-until cannot qualify stepping with armed data/watchpoints")
        address = item.get("address")
        if not isinstance(address, dict) or address.get("space") not in ("segmented", "linear"):
            raise ValueError("Unqualified execution-breakpoint address")
        location = _number(address.get("offset"), "breakpoint offset")
        segment = None
        if address["space"] == "segmented":
            segment = _number(address.get("segment"), "breakpoint segment", 0xffff)
        identifier = item.get("breakpoint_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Native breakpoint identifier is missing")
        controls.append(dict(id=identifier, space=address["space"], offset=location,
                             segment=segment, once=item.get("once")))
    return controls


def _at_breakpoint(controls, event):
    pc = event["pc"]
    found = []
    for point in controls:
        matches = (pc.get("linear") == point["offset"] if point["space"] == "linear"
                   else pc.get("segment") == point["segment"] and pc["offset"] == point["offset"])
        if matches:
            found.append(point["id"])
    return found


def _trace_idle(session):
    from .dosbox_rpc import DebuggerError
    try:
        state = session.call('trace.read', {'cursor': None, 'limit': 1})
    except DebuggerError as error:
        if str(error) != 'No CPU trace has been started (COMMAND_REJECTED)':
            raise
    else:
        if state.get('active') is not False:
            raise ValueError('trace-until cannot replace another active native trace')


def _same_boundary(sample, observed, *, ignore_flags=False):
    """Compare native fetch evidence with the stopped register/code snapshot."""
    try:
        if sample['cpu_mode'] != observed['cpu_mode'] or sample['code_bits'] != observed['code_bits']:
            return False
        for field in ('segment', 'offset'):
            if _number(sample['address'][field], field) != _number(observed['address'][field], field):
                return False
        code = bytes.fromhex(sample['execution_bytes'])
        if not code or not bytes.fromhex(observed['execution_bytes']).startswith(code[:15]):
            return False
        changes = sample.get('register_changes', {})
        ignored = {'flags'} if ignore_flags else set()
        if set(observed['register_changes']) - set(changes) - ignored:
            return False
        for name, value in changes.items():
            if name not in ignored and name in observed['register_changes'] and _number(value, name) != _number(observed['register_changes'][name], name):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _advance_boundary(session, ownership):
    """One callback-safe native interval, retaining both fetched endpoints."""
    ownership['trace'] = True  # An uncertain start must also be cleaned up.
    session.call('trace.start', {'detail': 'normal', 'instruction_count': 2})
    operation = session.call('execution.continue')
    if not operation.get('operation_id'):
        raise ValueError('Native continuation lacks an operation identity')
    while True:
        remaining = int((session._rpc_deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Native boundary interval exceeded the shared deadline')
        stopped = session.call('execution.wait', {'operation_id': operation['operation_id'],
                                                 'timeout_ms': min(50, remaining)})
        if stopped.get('running') is not True:
            break
    status = session.call('session.status')
    if status.get('state') not in ('stopped', 'exited'):
        raise RuntimeError('Native interval returned without a stopped CPU')
    page = session.call('trace.read', {'cursor': None, 'limit': 3})
    samples = page.get('events')
    if not isinstance(samples, list) or len(samples) > 2 or page.get('next_cursor'):
        raise ValueError('Native boundary interval exceeded its two-fetch trace budget')
    session.call('trace.stop')
    ownership['trace'] = False
    return dict(stop=stopped, status=status, events=samples)


def _observe(session, index):
    """Read code and registers from one unchanged, unpaged real-mode stop."""
    status = session.call("session.status")
    if status.get("state") != "stopped":
        raise ValueError("trace-until requires an owned stopped DOS CPU")
    registers = session.call("state.get_registers")
    context = registers.get("address_context")
    if (registers.get("cpu_mode") != "real" or registers.get("code_bits") != 16
            or not isinstance(context, dict) or context.get("cpu_mode") != "real"
            or context.get("paging_enabled") is not False):
        raise ValueError("Live trace-until currently requires observed unpaged real-mode DOS")
    if registers.get("state_revision") != status.get("state_revision"):
        raise ValueError("Register observation differs from the stopped revision")
    segment = _number(registers.get("segments", {}).get("cs"), "CS", 0xffff)
    offset = _number(registers.get("instruction_pointer"), "real-mode IP", 0xffff)
    linear = segment * 16 + offset
    length = min(15, 0x10000 - offset)
    reply = session.call("memory.read", {
        "address": {"space": "linear", "offset": f"0x{linear:08X}"},
        "length": length, "view": "execute"})
    raw = base64.b64decode(reply.get("data_base64", ""), validate=True)
    if (len(raw) != length or hashlib.sha256(raw).hexdigest() != reply.get("sha256")
            or reply.get("overlay_valid") is False):
        raise ValueError("Stopped instruction bytes failed their length/hash/view check")
    after = session.call("session.status")
    if after != status:
        raise ValueError("Native stop changed during the instruction observation")
    address = dict(space="segmented", segment=hex(segment), offset=hex(offset))
    source = session.project_address(address)
    relative_segment = segment - session.runtime_load + session.dos["load_segment"]
    values = {**registers.get("general", {}), **registers.get("segments", {}),
              "instruction_pointer": registers["instruction_pointer"], "flags": registers.get("flags")}
    event = dict(sequence=index + 1, address=address, cpu_mode="real", code_bits=16,
                 stack_bits=registers.get("stack_bits"), execution_bytes=raw.hex(),
                 register_changes=values, project_address=source, active_layers=[],
                 identity=dict(source_version=session.version["id"], runtime_address=address,
                               project_address=source,
                               context=f"real:{relative_segment:04x}" if 0 <= relative_segment <= 0xffff else None),
                 observation=dict(registers_stage="before-instruction", instruction_completed=False, flags_materialized=True,
                                  evidence="stopped boundary snapshot; no retirement claim"),
                 native_stop=deepcopy(status), address_context=deepcopy(context))
    if len(_encoded(event)) > MAX_BOUNDARY_BYTES:
        raise ValueError('Stopped boundary exceeds its 8 KiB observation budget')
    return event, dict(status=status, registers=registers, address=address)


def _document(session, events, *, window=None):
    from .debug_semantics import contract
    backend = session.metadata.get("backend", "dosbox")
    semantics = contract(backend)
    semantics["trace_completion"] = "stopped instruction boundaries; architectural retirement unqualified"
    return dict(run={"run": session.run_id}, version=session.version["id"],
                mapping=deepcopy(session.metadata), events=events,
                observation_contract=semantics, requested_count=len(events), complete=False,
                **({"window": window} if window is not None else {}))


def _compiled_boundary(session, raw, regions):
    from .execution_events import normalize_trace
    # Each boundary carries a full native register observation, so this local
    # compilation has no hidden dependency on sparse changes from an earlier call.
    value = deepcopy(raw)
    value["sequence"] = 1
    compiled = normalize_trace(_document(session, [value]), regions=regions)
    event = compiled["events"][0]
    event["index"] = raw["sequence"] - 1
    event["sequence"] = raw["sequence"]
    event["contiguous"] = raw["sequence"] > 1
    return event


def _cleanup_pause(session, result):
    """After an uncertain request, obtain a bounded stopped receipt or close."""
    old_grace = getattr(session, "_rpc_cleanup_grace_ms", None)
    session._rpc_cleanup_grace_ms = 3000
    try:
        with run_cleanup_scope(session):
            status = session.call("session.status")
            if status.get("state") != "stopped":
                pause = session.call("execution.pause")
                if pause.get("operation_id"):
                    session.call("execution.wait", {"operation_id": pause["operation_id"], "timeout_ms": 2000})
                status = session.call("session.status")
            if status.get("state") != "stopped":
                raise RuntimeError("Owned CPU could not be confirmed stopped")
            result["cleanup"] = {"stopped": True, "status": status}
    except Exception as error:
        result["cleanup"] = {"stopped": False, "error": str(error), "closed": False}
        try:
            session.close()
        except Exception as close_error:
            result["cleanup"]["close_error"] = str(close_error)
        result["cleanup"]["closed"] = bool(session.closed)
    finally:
        session._rpc_cleanup_grace_ms = old_grace


class ExecutionTraceSessionMixin:
    """Exact live predicate matching for the qualified DOSBox boundary adapter."""

    @timeline_locked
    @rpc_budget
    def trace_until(self, until, *, regions=None, max_steps=1000, timeout_ms=10000,
                    name="trace-until.json", action=None, label="trial"):
        from .execution_events import evaluate_predicate, validate_regions
        until, regions, action = validate_trace_until(
            until, regions=regions, max_steps=max_steps, timeout_ms=timeout_ms,
            name=name, action=action, label=label)
        backend = getattr(self, "backend_name", None) or self.metadata.get("backend", "dosbox")
        if self.closed or backend not in ("dosbox", "dosbox-qemu"):
            raise ValueError("Live trace-until requires an owned DOSBox session")
        if not self.rpc.capabilities.get("trace", {}).get("cpu"):
            raise ValueError("Backend lacks the required CPU observation contract")
        if self.layers().get("active"):
            raise ValueError("Live trace-until does not qualify active execution byte layers")
        if action is not None:
            inputs = self.rpc.capabilities.get("input", {})
            if action["op"] == "click" and inputs.get("absolute_mouse") is not True:
                raise ValueError("Backend lacks queued absolute mouse input")
            if action["op"] == "keyboard.press" and inputs.get("keyboard") != "ibm_pc_controller_us_ascii_v1":
                raise ValueError("Backend lacks the qualified queued keyboard contract")
        if regions is None:
            regions = validate_regions([
                dict(id=f"project:{index}:{region.start:x}:{region.start + len(region.data):x}",
                     name=region.name, space="project", start=region.start, end=region.start + len(region.data))
                for index, region in enumerate(self.project.regions(self.version["id"])) if region.data])
        controls = _native_controls(self)
        _trace_idle(self)
        first, current_stop = _observe(self, 0)
        current = _compiled_boundary(self, first, regions)
        if _needs_region(until) and current.get("region") is None:
            raise ValueError("region-change requires an initial declared region")
        # Reserve the complete mapping and bounded result/input metadata before
        # execution. Leave room for one maximum-size next boundary; saturation
        # returns a retained partial window instead of losing the whole trace.
        header_bytes = len(_encoded(_document(self, []))) + len(_encoded(regions)) + len(_encoded(until)) + 256 * 1024
        event_bytes = len(_encoded(first)) + 1
        if header_bytes + event_bytes > MAX_TRACE_BYTES:
            raise ValueError('Trace mapping leaves no room in the 16 MiB artifact budget')
        # Complete every preflight and initial read before an optional input.
        self._runtime_state()
        capture_epoch = self._runtime_epoch
        result = dict(format="fdisbull-trace-until-1", run=self.run_id,
                      version=self.version["id"], label=label, until=until,
                      matched=False, exact_stop=False, complete=False,
                      outcome="incomplete", max_steps=max_steps, steps=0, attempted_steps=0,
                      budget_unit="verified next-fetch intervals; retirement not inferred",
                      timeout_ms=timeout_ms, matched_event=None, current_stop=current_stop,
                      action=dict(requested=action, dispatch="not_requested" if action is None else "not_dispatched",
                                  game_consumption_proven=False), error=None)
        events = [first]
        initial = deepcopy(current)
        previous = None
        started = time.monotonic()
        interrupted = None
        ownership = {'trace': False}
        try:
            while True:
                if time.monotonic() >= self._rpc_deadline:
                    result["outcome"] = "timeout"
                    break
                native = current_stop["status"].get("last_stop", {})
                if native.get("kind") not in ("startup", "pause", "step"):
                    result.update(outcome="exited" if native.get("kind") in ("guest_exit", "guest_tsr", "exited", "exit") else "foreign_stop",
                                  foreign_stop=deepcopy(native))
                    break
                # Checking armed controls here preserves the user's boundary and
                # once flag without invoking or deleting a host-side hook.
                points = _at_breakpoint(controls, current)
                if points:
                    result.update(outcome="foreign_stop", foreign_stop={
                        "kind": "armed_execution_breakpoint_boundary", "breakpoint_ids": points})
                    break
                evaluation = evaluate_predicate(until, current, initial=initial, previous=previous)
                result["evaluation"] = evaluation
                if evaluation["matched"] is True:
                    result.update(matched=True, exact_stop=True, complete=True,
                                  outcome="predicate", matched_event=deepcopy(current))
                    if action is not None and result["action"]["dispatch"] == "not_dispatched":
                        result["action"]["dispatch"] = "skipped_initial_match"
                    break
                if result["attempted_steps"] >= max_steps:
                    result["outcome"] = "step_budget"
                    break
                if header_bytes + event_bytes + MAX_BOUNDARY_BYTES > MAX_TRACE_BYTES:
                    result["outcome"] = "artifact_budget"
                    break
                if action is not None and result["action"]["dispatch"] == "not_dispatched":
                    result["action"]["dispatch"] = "dispatching"
                    self._event("trace-until-input-attempt", dict(label=label, requested=action))
                    params = {key: value for key, value in action.items() if key != "op"}
                    method = self.click if action["op"] == "click" else self.keyboard_press
                    receipt = method(**params)
                    result["action"].update(dispatch="queued", receipt=deepcopy(receipt))
                    # Queuing input is not an execution permission. Re-observe
                    # the boundary before the first step and preserve its phase.
                    fresh, current_stop = _observe(self, 0)
                    if fresh["address"] != first["address"]:
                        raise ValueError("Queued input unexpectedly changed the instruction pointer")
                    events[0] = fresh
                    event_bytes = len(_encoded(fresh)) + 1
                    current = _compiled_boundary(self, fresh, regions)
                    result["current_stop"] = current_stop
                    continue
                result["attempted_steps"] += 1
                interval = _advance_boundary(self, ownership)
                stop = interval['stop'].get("stop_reason", {})
                status = interval['status']
                reason = status.get("last_stop", {})
                result["native_interval"] = deepcopy(interval)
                if status.get('state') == 'exited' or stop.get("kind") != "pause" or reason.get("kind") != "pause":
                    native = stop if stop.get("kind") != "pause" else reason
                    result.update(outcome="exited" if status.get('state') == 'exited' or native.get("kind") in ("guest_exit", "guest_tsr", "exited", "exit") else "foreign_stop",
                                  foreign_stop=deepcopy(native), current_stop={"status": status})
                    break
                raw, current_stop = _observe(self, len(events))
                result['current_stop'] = current_stop
                samples = interval['events']
                last = deepcopy(samples[-1]) if len(samples) == 2 else {}
                if len(samples) == 2:
                    last['register_changes'] = {**samples[0].get('register_changes', {}),
                                                **samples[1].get('register_changes', {})}
                if (len(samples) != 2 or not _same_boundary(samples[0], events[-1])
                        # Native fetch deltas retain lazy FLAGS until the
                        # stopped register RPC materializes them. Compare all
                        # other registers; predicates use that fresh full read.
                        or not _same_boundary(last, raw, ignore_flags=True)):
                    result.update(outcome='unqualified_interval', error={
                        'type': 'BoundaryMismatch',
                        'message': 'Native fetch endpoints differ from the stopped boundaries; an interrupt or context change may have intervened'})
                    break
                result["steps"] += 1
                # Earlier records were observed before the step. Their
                # architectural completion remains unknown, even after a reply.
                events[-1]["observation"]["instruction_completed"] = None
                previous = current
                current = _compiled_boundary(self, raw, regions)
                events.append(raw)
                event_bytes += len(_encoded(raw)) + 1
                result["current_stop"] = current_stop
        except BaseException as error:
            if not isinstance(error, Exception):
                interrupted = error
            result.update(outcome="cancelled" if interrupted is not None else "timeout" if isinstance(error, TimeoutError) else "error",
                          matched=False, exact_stop=False, complete=False,
                          error={"type": type(error).__name__, "message": str(error)})
            if result["action"]["dispatch"] == "dispatching":
                result["action"]["dispatch"] = "uncertain"
            _cleanup_pause(self, result)
        if ownership['trace']:
            try:
                old_grace = getattr(self, '_rpc_cleanup_grace_ms', None)
                self._rpc_cleanup_grace_ms = 3000
                try:
                    with run_cleanup_scope(self):
                        self.call('trace.stop')
                finally:
                    self._rpc_cleanup_grace_ms = old_grace
            except BaseException as error:
                result['trace_cleanup_error'] = {'type': type(error).__name__, 'message': str(error)}
                try:
                    self.close()
                except BaseException as close_error:
                    result['trace_cleanup_error']['close_error'] = {
                        'type': type(close_error).__name__, 'message': str(close_error)}
                result['trace_cleanup_error']['closed'] = bool(self.closed)
        result["host_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        closed_window = result["outcome"] in ("predicate", "step_budget")
        document = _document(self, events, window=dict(closed=closed_window, reason=result["outcome"],
                             scope="these observed boundaries only; action completion is not inferred"))
        document.update(requested_count=max_steps + 1, complete=closed_window and len(events) == max_steps + 1,
                        capture_kind="stopped-boundary-predicate", label=label, action=deepcopy(result["action"]),
                        capture_epoch=capture_epoch, regions=regions,
                        collector=dict(max_steps=max_steps, attempted_steps=result["attempted_steps"],
                                       steps=result["steps"], until=until, outcome=result["outcome"],
                                       matched=result["matched"], exact_stop=result["exact_stop"],
                                       current_stop=result["current_stop"], error=result["error"]))
        if result['outcome'] == 'unqualified_interval':
            document['collector']['unqualified_interval'] = deepcopy(result['native_interval'])
        try:
            raw = _encoded(document)
            if len(raw) > MAX_TRACE_BYTES:
                raise ValueError("Aggregate execution trace exceeds the 16 MiB artifact budget")
            artifact = self._artifact(name, "trace", raw,
                                      dict(event_count=len(events), complete=document["complete"],
                                           window=document["window"], label=label, capture_kind=document["capture_kind"]))
            result.update(trace_artifact=artifact["artifact"], trace=artifact, observation_count=len(events))
            self._event("trace-until", result)
        except Exception as error:
            result["persistence_error"] = {"type": type(error).__name__, "message": str(error)}
            if interrupted is not None:
                interrupted.result = result
                raise interrupted from error
            raise ExecutionTraceError(result, error) from error
        if interrupted is not None:
            interrupted.result = result
            raise interrupted
        return result
