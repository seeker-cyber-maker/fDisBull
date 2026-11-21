"""Authored observation-budget checks; no native guest is launched."""
from copy import deepcopy

import pytest

from dotbox.bounded_wait import bounded_wait


class NativeModel:
    """A deterministic 50-fps clock with independent call and parent deadlines."""

    def __init__(self, *, deadline=60000, call_limit=15000):
        self.now = 0
        self.deadline = deadline
        self.call_limit = call_limit
        self.calls = []
        self.receipts = []

    def step(self, *, max_frames, max_guest_ms):
        self.calls.append({"max_frames": max_frames, "max_guest_ms": max_guest_ms})
        elapsed = min(max_guest_ms, max_frames * 20)
        if elapsed > self.call_limit:
            raise TimeoutError("native operation deadline")
        if self.now + elapsed > self.deadline:
            raise TimeoutError("original parent deadline")
        before = self.now
        self.now += elapsed
        frames = elapsed // 20
        cause = "frame_limit" if frames == max_frames else "guest_time_limit"
        result = receipt(max_frames, max_guest_ms, frames, elapsed, cause)
        result.update(session_id="authored", state_revision=len(self.calls),
                      arbitrary_evidence={"ticks": [before, self.now]})
        self.receipts.append(result)
        return result


def receipt(max_frames, max_guest_ms, frames, elapsed, cause="guest_time_limit"):
    return {"boundary": "bounded_execution_then_safe_fetch",
            "bounded": {"max_frames": max_frames, "max_guest_ms": max_guest_ms,
                        "frames_completed": frames, "guest_elapsed_ms": elapsed,
                        "stop_cause": cause}}


def test_slices_avoid_long_single_operation_without_enlarging_observation():
    # The native operation cap and total observation budget are independent.
    # At this supported model speed a single 25-second request exceeds the
    # 15-second operation cap, although the enclosing 30-second budget fits.
    unsliced = NativeModel(deadline=30000)
    with pytest.raises(TimeoutError, match="native operation deadline"):
        unsliced.step(max_frames=1900, max_guest_ms=25000)
    model = NativeModel(deadline=30000)
    result = bounded_wait(model.step, max_frames=1900, max_guest_ms=25000)
    assert model.calls == [{"max_frames": f, "max_guest_ms": 5000}
                           for f in [1900, 1650, 1400, 1150, 900]]
    assert result["schema"] == "dotbox-bounded-wait-1"
    assert result["limits"] == {"max_frames": 1900, "max_guest_ms": 25000,
                                "slice_guest_ms": 5000}
    assert result["totals"] == {"frames_completed": 1250, "guest_elapsed_ms": 25000}
    assert result["stop_cause"] == "guest_time_limit"
    assert model.deadline == 30000
    assert [s["request"] for s in result["steps"]] == model.calls
    assert [s["receipt"] for s in result["steps"]] == model.receipts
    assert "bounded" not in result and "frame_id" not in result


def test_original_frame_ceiling_ends_entire_observation():
    model = NativeModel()
    result = bounded_wait(model.step, max_frames=600, max_guest_ms=25000)
    assert model.calls == [{"max_frames": 600, "max_guest_ms": 5000},
                           {"max_frames": 350, "max_guest_ms": 5000},
                           {"max_frames": 100, "max_guest_ms": 5000}]
    assert result["totals"] == {"frames_completed": 600, "guest_elapsed_ms": 12000}
    assert result["stop_cause"] == "frame_limit"
    assert len(result["steps"]) == 3


@pytest.mark.parametrize("budget,slice_size,expected", [
    (1, 5000, [1]), (4999, 5000, [4999]), (5001, 5000, [5000, 1]),
    (2501, 1000, [1000, 1000, 501]), (30000, 5000, [5000] * 6),
])
def test_short_and_final_slices_keep_exact_guest_ceiling(budget, slice_size, expected):
    model = NativeModel()
    result = bounded_wait(model.step, max_frames=10000, max_guest_ms=budget,
                          slice_guest_ms=slice_size)
    assert [c["max_guest_ms"] for c in model.calls] == expected
    assert result["totals"]["guest_elapsed_ms"] == budget
    assert result["stop_cause"] == "guest_time_limit"


def test_guest_progress_without_completed_frame_is_valid():
    model = NativeModel()
    result = bounded_wait(model.step, max_frames=7, max_guest_ms=1)
    assert result["totals"] == {"frames_completed": 0, "guest_elapsed_ms": 1}


def test_frame_progress_without_guest_tick_is_valid_and_stops():
    calls = []

    def step(**args):
        calls.append(args)
        return receipt(1, 5000, 1, 0, "frame_limit")

    result = bounded_wait(step, max_frames=1, max_guest_ms=15000)
    assert len(calls) == 1
    assert result["totals"] == {"frames_completed": 1, "guest_elapsed_ms": 0}
    assert result["stop_cause"] == "frame_limit"


def test_frame_ceiling_wins_tie_but_retains_native_cause():
    def step(**args):
        return receipt(2, 5000, 2, 5000, "guest_time_limit")

    result = bounded_wait(step, max_frames=2, max_guest_ms=5000)
    assert result["stop_cause"] == "frame_limit"
    assert result["steps"][0]["receipt"]["bounded"]["stop_cause"] == "guest_time_limit"


def test_original_parent_deadline_is_not_renewed_by_slicing():
    model = NativeModel(deadline=11000)
    with pytest.raises(TimeoutError, match="original parent deadline"):
        bounded_wait(model.step, max_frames=1900, max_guest_ms=25000)
    assert model.deadline == 11000
    assert model.now == 10000
    assert len(model.calls) == 3
    assert len(model.receipts) == 2


def test_callback_exception_after_success_propagates_same_object_without_retry():
    failure = RuntimeError("uncertain native stop")
    calls = []

    def step(**args):
        calls.append(args)
        if len(calls) == 2:
            raise failure
        return receipt(args["max_frames"], args["max_guest_ms"], 5, args["max_guest_ms"])

    with pytest.raises(RuntimeError) as caught:
        bounded_wait(step, max_frames=100, max_guest_ms=15000)
    assert caught.value is failure
    assert len(calls) == 2


def test_recorded_raw_receipts_are_not_mutated_by_later_callback_reuse():
    shared = {}

    def step(**args):
        shared.clear()
        shared.update(receipt(args["max_frames"], args["max_guest_ms"], 2, args["max_guest_ms"]))
        return shared

    result = bounded_wait(step, max_frames=100, max_guest_ms=7000)
    assert result["steps"][0]["receipt"]["bounded"]["max_guest_ms"] == 5000
    assert result["steps"][1]["receipt"]["bounded"]["max_guest_ms"] == 2000
    shared["bounded"]["max_guest_ms"] = 999
    assert result["steps"][1]["receipt"]["bounded"]["max_guest_ms"] == 2000


@pytest.mark.parametrize("field,value", [
    ("max_frames", True), ("max_frames", 0), ("max_frames", 10001),
    ("max_guest_ms", None), ("max_guest_ms", 0), ("max_guest_ms", 30001),
    ("slice_guest_ms", False), ("slice_guest_ms", 1.5), ("slice_guest_ms", 0),
    ("slice_guest_ms", 5001),
])
def test_invalid_budgets_are_refused_before_callback(field, value):
    calls = []
    limits = dict(max_frames=100, max_guest_ms=5000, slice_guest_ms=5000)
    limits[field] = value
    with pytest.raises(ValueError):
        bounded_wait(lambda **args: calls.append(args), **limits)
    assert calls == []


def test_noncallable_step_is_refused():
    with pytest.raises(TypeError):
        bounded_wait(None, max_frames=1, max_guest_ms=1)


@pytest.mark.parametrize("path,value", [
    ((), None), (("bounded",), None), (("bounded",), []),
    (("bounded", "stop_cause"), "breakpoint"),
    (("bounded", "stop_cause"), None),
    (("bounded", "max_frames"), 101),
    (("bounded", "max_guest_ms"), 5001),
    (("bounded", "frames_completed"), True),
    (("bounded", "frames_completed"), -1),
    (("bounded", "frames_completed"), 101),
    (("bounded", "guest_elapsed_ms"), 5001),
    (("bounded", "guest_elapsed_ms"), "5000"),
    (("bounded", "guest_elapsed_ms"), -1),
    (("bounded", "guest_elapsed_ms"), 1),
    (("bounded", "stop_cause"), "frame_limit"),
])
def test_malformed_or_unknown_receipt_stops_without_another_callback(path, value):
    returned = receipt(100, 5000, 20, 5000)
    if not path:
        returned = value
    else:
        target = returned
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    calls = []

    def step(**args):
        calls.append(args)
        return deepcopy(returned)

    with pytest.raises(ValueError):
        bounded_wait(step, max_frames=100, max_guest_ms=15000)
    assert len(calls) == 1


def test_zero_progress_receipt_refuses_without_loop():
    calls = []

    def step(**args):
        calls.append(args)
        return receipt(args["max_frames"], args["max_guest_ms"], 0, 0)

    with pytest.raises(ValueError, match="progress"):
        bounded_wait(step, max_frames=100, max_guest_ms=15000)
    assert len(calls) == 1


def test_second_receipt_cannot_reuse_original_frame_budget():
    calls = []

    def step(**args):
        calls.append(args)
        return receipt(100, args["max_guest_ms"], 20, args["max_guest_ms"])

    with pytest.raises(ValueError, match="ceiling"):
        bounded_wait(step, max_frames=100, max_guest_ms=15000)
    assert calls == [{"max_frames": 100, "max_guest_ms": 5000},
                     {"max_frames": 80, "max_guest_ms": 5000}]
