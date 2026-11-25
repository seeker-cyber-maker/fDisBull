"""Host contract tests for the persistent QEMU DOS fetch trace facade."""
from copy import deepcopy
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_fetch_trace import QemuFetchTraceMixin


class FakeProcess:
    def poll(self):
        return None


class FakeQMP:
    def __init__(self):
        self.epoch = 40
        self.trace = None
        self.calls = []
        self.fail_start = False
        self.drop_count = 0
        self.sequence_gap = False
        self.trace_version = 1

    def call(self, method, arguments=None):
        arguments = dict(arguments or {})
        self.calls.append((method, deepcopy(arguments)))
        if method == "x-fdisbull-trace-start":
            if self.fail_start:
                self.trace = dict(active=True, count=arguments["instruction-count"], events=[])
                raise TimeoutError("lost start response")
            self.epoch += 1
            self.trace = dict(active=True, count=arguments["instruction-count"], events=[])
            result = dict(epoch=self.epoch, **{"instruction-count": self.trace["count"],
                "capacity": self.trace["count"], "active": True, "next-sequence": 1})
            if self.trace_version == 2:
                result["trace-version"] = 2
            return result
        if self.trace is None or arguments.get("epoch") != self.epoch:
            raise DebuggerError("wrong fake trace epoch")
        if method in ("x-fdisbull-trace-read", "x-fdisbull-trace-stop"):
            after = arguments["after-sequence"]
            limit = arguments["max-events"]
            events = [deepcopy(event) for event in self.trace["events"]
                      if event["sequence"] > after][:limit]
            if method == "x-fdisbull-trace-stop":
                self.trace["active"] = False
            oldest = self.trace["events"][0]["sequence"] if self.trace["events"] else 1
            next_sequence = len(self.trace["events"]) + 1
            if self.sequence_gap and events:
                events[0]["sequence"] += 1
            result = {"epoch": self.epoch, "active": self.trace["active"],
                "stopped-reason": "count" if not self.trace["active"] else None,
                "instruction-count": self.trace["count"], "captured-count": len(self.trace["events"]),
                "oldest-sequence": oldest, "next-sequence": next_sequence,
                "dropped-count": self.drop_count, "events": events}
            if self.trace_version == 2:
                result["trace-version"] = 2
            return result
        raise AssertionError(method)

    def dispatch(self, count):
        for _ in range(count):
            sequence = len(self.trace["events"]) + 1
            if sequence > self.trace["count"]:
                self.trace["active"] = False
                break
            pc = 0x1000 + (sequence - 1)
            origin = "tcg-dispatch" if sequence % 2 else "breakpoint-pre-dispatch"
            event = {"sequence": sequence, "vcpu": 0, "pc": pc,
                     "reason": "before-execution", "origin": origin}
            if self.trace_version == 2:
                available = origin == "tcg-dispatch"
                event.update({
                    "code-bytes": "40" if available else "",
                    "code-byte-count": 1 if available else 0,
                    "code-bytes-valid": available,
                    "code-bytes-unavailable-reason": "" if available else
                        "breakpoint-pre-dispatch-no-translation",
                    "code-bytes-source": "translated-tb" if available else "none",
                    "code-bits": 16,
                    "cs-selector": 0x1000,
                    "cs-base": 0x10000,
                    "x86-context-valid": True,
                })
            self.trace["events"].append(event)
            if sequence == self.trace["count"]:
                self.trace["active"] = False


class Session(QemuFetchTraceMixin):
    _trace_start = QemuFetchTraceMixin._trace_start.__wrapped__
    _trace_read = QemuFetchTraceMixin._trace_read.__wrapped__
    _trace_stop = QemuFetchTraceMixin._trace_stop.__wrapped__

    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock(), qmp=FakeQMP(),
            process=FakeProcess(), qmp_commands={"x-fdisbull-trace-start"}, close_count=0)
        self.vm.close = lambda: setattr(self.vm, "close_count", self.vm.close_count + 1)
        self.session_id = "session-A"
        self.closed = False
        self._runtime_epoch = "run-A:process:1"
        self.machine_state = "stopped"
        self._process = {"state": "active", "capture_epoch": self._runtime_epoch,
            "source_mapping": {"live": True}}

    def status(self):
        return {"state": self.machine_state}

    def call(self, method, params=None):
        if method in ("trace.start", "trace.read", "trace.stop"):
            return self._trace_rpc(method, params)
        raise AssertionError(method)


def test_public_trace_methods_keep_paged_before_execution_events():
    session = Session()
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 4})
    session.vm.qmp.dispatch(4)
    first = session.call("trace.read", {"cursor": started["cursor"], "limit": 2})
    assert first["active"] is False
    assert [event["sequence"] for event in first["events"]] == [1, 2]
    assert first["next_cursor"] == first["cursor"]
    page = session.call("trace.read", {"cursor": first["next_cursor"], "limit": 2})
    assert [event["sequence"] for event in page["events"]] == [3, 4]
    assert page["next_cursor"] is None
    event = page["events"][-1]
    assert event["native"]["reason"] == "before-execution"
    assert event["native"]["origin"] == "breakpoint-pre-dispatch"
    assert event["address"] == {"space": "virtual", "offset": "0x1003"}
    assert event["observation"]["registers_stage"] == "before-instruction"
    assert event["observation"]["instruction_completed"] is None
    assert "instruction" not in event and "execution_bytes" not in event
    origins = {item["native"]["origin"] for item in first["events"] + page["events"]}
    assert origins == {"tcg-dispatch", "breakpoint-pre-dispatch"}
    stopped = session.call("trace.stop")
    assert stopped["active"] is False and stopped["event_count"] == 4
    assert stopped["events"] == []


@pytest.mark.parametrize("params", [
    {"detail": "invented", "instruction_count": 2},
    {"detail": "normal", "instruction_count": True},
    {"detail": "normal", "instruction_count": 10001},
    {"detail": "normal", "instruction_count": 2, "extra": 1},
])
def test_start_validates_detail_and_bounded_count_before_native_dispatch(params):
    session = Session()
    with pytest.raises((ValueError, TypeError)):
        session.call("trace.start", params)
    assert not session.vm.qmp.calls


def test_duplicate_start_refuses_and_old_cursor_cannot_alias_new_capture():
    session = Session()
    started = session.call("trace.start", {"detail": "short", "instruction_count": 3})
    with pytest.raises(DebuggerError, match="already active"):
        session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    session.vm.qmp.dispatch(3)
    session.call("trace.stop")
    newer = session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    assert newer["trace_id"] != started["trace_id"]
    with pytest.raises(DebuggerError, match="another capture epoch"):
        session.call("trace.read", {"cursor": started["cursor"], "limit": 1})


def test_source_epoch_change_blocks_read_but_allows_bounded_machine_owned_stop():
    session = Session()
    session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    session.vm.qmp.dispatch(1)
    session._runtime_epoch = "run-A:process:2"
    session._process["capture_epoch"] = session._runtime_epoch
    with pytest.raises(DebuggerError, match="owner or source epoch changed"):
        session.call("trace.read", {"cursor": None, "limit": 2})
    stopped = session.call("trace.stop")
    assert stopped["active"] is False
    assert stopped["event_count"] == 1


@pytest.mark.parametrize("fault,message", [
    ("drop_count", "dropped"),
    ("sequence_gap", "omitted"),
])
def test_native_loss_or_gapped_dispatch_fails_closed(fault, message):
    session = Session()
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    session.vm.qmp.dispatch(2)
    setattr(session.vm.qmp, fault, 1 if fault == "drop_count" else True)
    with pytest.raises(DebuggerError, match=message):
        session.call("trace.read", {"cursor": started["cursor"], "limit": 3})


def test_start_response_loss_is_retained_as_uncertain_and_not_retried():
    session = Session()
    session.vm.qmp.fail_start = True
    with pytest.raises(TimeoutError):
        session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    assert session.vm.close_count == 1
    with pytest.raises(DebuggerError, match="active or uncertain"):
        session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    assert [method for method, _ in session.vm.qmp.calls].count("x-fdisbull-trace-start") == 1


def test_trace_cursor_is_strict_and_stopped_read_retains_cached_events():
    session = Session()
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 2})
    session.vm.qmp.dispatch(2)
    session.call("trace.stop")
    with pytest.raises(ValueError, match="opaque"):
        session.call("trace.read", {"cursor": "trace-1", "limit": 1})
    page = session.call("trace.read", {"cursor": started["cursor"], "limit": 2})
    assert [event["sequence"] for event in page["events"]] == [1, 2]


def test_v1_producer_keeps_new_context_unknown_for_backward_compatibility():
    session = Session()
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 1})
    assert started["trace_version"] == 1
    session.vm.qmp.dispatch(1)
    page = session.call("trace.read", {"cursor": started["cursor"], "limit": 1})
    assert page["trace_version"] == 1
    assert "fetch_context" not in page["events"][0]
    assert "code-bytes-valid" not in page["events"][0]["native"]


def test_v2_projects_translation_bytes_and_explicit_breakpoint_unavailability():
    session = Session()
    session.vm.qmp.trace_version = 2
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 2})
    session.vm.qmp.dispatch(2)
    page = session.call("trace.read", {"cursor": started["cursor"], "limit": 2})
    assert started["trace_version"] == page["trace_version"] == 2
    tcg, breakpoint = page["events"]
    assert tcg["native"]["code-bytes"] == "40"
    assert tcg["fetch_context"]["translated_bytes"] == {
        "valid": True, "hex": "40", "count": 1,
        "source": "translated-tb", "unavailable_reason": None}
    assert tcg["fetch_context"]["x86"] == {
        "valid": True, "code_bits": 16, "cs_selector": 0x1000, "cs_base": 0x10000}
    assert breakpoint["fetch_context"]["translated_bytes"] == {
        "valid": False, "hex": None, "count": 0, "source": "none",
        "unavailable_reason": "breakpoint-pre-dispatch-no-translation"}
    assert breakpoint["fetch_context"]["x86"]["valid"] is True
    assert "cpu_mode" not in breakpoint
    assert all(event["observation"]["instruction_completed"] is None for event in page["events"])


@pytest.mark.parametrize("mutation", [
    lambda event: event.update({"code-byte-count": 2}),
    lambda event: event.update({"code-bytes-source": "none"}),
    lambda event: event.update({"code-bits": 17}),
    lambda event: event.update({"x86-context-valid": False}),
])
def test_v2_malformed_context_is_rejected_without_inference(mutation):
    session = Session()
    session.vm.qmp.trace_version = 2
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 1})
    session.vm.qmp.dispatch(1)
    mutation(session.vm.qmp.trace["events"][0])
    with pytest.raises(DebuggerError):
        session.call("trace.read", {"cursor": started["cursor"], "limit": 1})


def test_stop_disables_capture_and_drains_unread_tail_across_native_pages():
    session = Session()
    session.call("trace.start", {"detail": "normal", "instruction_count": 5000})
    session.vm.qmp.dispatch(5000)
    stopped = session.call("trace.stop")
    assert stopped["active"] is False and stopped["event_count"] == 5000
    assert len(stopped["events"]) == 5000
    assert stopped["events"][0]["sequence"] == 1
    assert stopped["events"][-1]["sequence"] == 5000
    assert [method for method, _ in session.vm.qmp.calls][-2:] == [
        "x-fdisbull-trace-stop", "x-fdisbull-trace-read"]


def test_stop_while_guest_runs_preserves_capture_for_later_cleanup():
    session = Session()
    session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    session.vm.qmp.dispatch(1)
    session.machine_state = "running"
    calls_before = len(session.vm.qmp.calls)
    with pytest.raises(ValueError, match="requires a stopped DOS process"):
        session.call("trace.stop")
    assert len(session.vm.qmp.calls) == calls_before
    assert session.vm.close_count == 0
    assert session._qemu_fetch_trace["state"] == "active"
    session.machine_state = "stopped"
    result = session.call("trace.stop")
    assert result["active"] is False
    assert result["event_count"] == 1
    assert session.vm.close_count == 0


def test_producer_epoch_change_rejects_old_trace_before_native_read():
    session = Session()
    session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    session.vm.qmp.dispatch(1)
    session.vm.qmp.epoch += 1
    before = len(session.vm.qmp.calls)
    with pytest.raises(DebuggerError, match="wrong fake trace epoch"):
        session.call("trace.read", {"cursor": None, "limit": 2})
    assert len(session.vm.qmp.calls) == before + 1


def test_machine_replacement_invalidates_old_cursor_and_allows_fresh_capture(monkeypatch):
    from fdisbull import qemu_session_revision
    from fdisbull.qemu_dos_process import QemuDOSProcessSession

    session = Session()
    session.run_id = "run-A"
    started = session.call("trace.start", {"detail": "normal", "instruction_count": 3})
    old_vm = session.vm
    replacement = SimpleNamespace(lock=threading.RLock(), qmp=FakeQMP(),
        process=FakeProcess(), qmp_commands={"x-fdisbull-trace-start"}, close_count=0)
    replacement.close = lambda: setattr(replacement, "close_count", replacement.close_count + 1)
    session.vm = replacement
    session._le_source_retire = lambda _reason: None
    monkeypatch.setattr(qemu_session_revision, "session_revision",
                        lambda _vm: SimpleNamespace(effect=lambda: None))

    QemuDOSProcessSession._advance_epoch(session)

    assert session._qemu_fetch_trace["state"] == "invalidated"
    assert session._qemu_fetch_trace["invalidation_reason"] == "machine-replaced"
    old_calls = len(old_vm.qmp.calls)
    with pytest.raises(DebuggerError, match="invalidated by machine replacement"):
        session.call("trace.read", {"cursor": started["cursor"], "limit": 1})
    assert len(old_vm.qmp.calls) == old_calls

    fresh = session.call("trace.start", {"detail": "normal", "instruction_count": 2})
    assert fresh["trace_id"] != started["trace_id"]
    assert fresh["epoch"] == 41
    assert [method for method, _ in old_vm.qmp.calls].count("x-fdisbull-trace-start") == 1
    assert [method for method, _ in replacement.qmp.calls].count("x-fdisbull-trace-start") == 1
