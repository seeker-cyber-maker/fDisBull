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

    def call(self, method, arguments=None):
        arguments = dict(arguments or {})
        self.calls.append((method, deepcopy(arguments)))
        if method == "x-fdisbull-trace-start":
            if self.fail_start:
                self.trace = dict(active=True, count=arguments["instruction-count"], events=[])
                raise TimeoutError("lost start response")
            self.epoch += 1
            self.trace = dict(active=True, count=arguments["instruction-count"], events=[])
            return dict(epoch=self.epoch, **{"instruction-count": self.trace["count"],
                "capacity": self.trace["count"], "active": True, "next-sequence": 1})
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
            return {"epoch": self.epoch, "active": self.trace["active"],
                "stopped-reason": "count" if not self.trace["active"] else None,
                "instruction-count": self.trace["count"], "captured-count": len(self.trace["events"]),
                "oldest-sequence": oldest, "next-sequence": next_sequence,
                "dropped-count": self.drop_count, "events": events}
        raise AssertionError(method)

    def dispatch(self, count):
        for _ in range(count):
            sequence = len(self.trace["events"]) + 1
            if sequence > self.trace["count"]:
                self.trace["active"] = False
                break
            pc = 0x1000 + (sequence - 1)
            self.trace["events"].append({"sequence": sequence, "vcpu": 0,
                "pc": pc, "reason": "before-execution",
                "origin": "tcg-dispatch" if sequence % 2 else "breakpoint-pre-dispatch"})
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
