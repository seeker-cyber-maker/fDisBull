"""Compose one observation budget from short, already-fenced native steps.

This module grants no native access. The caller supplies the fenced callback and
owns capabilities, ownership, receipt provenance, and the original host deadline.
It does not send input, restore state, renew deadlines, clean up, or retry.
"""
from collections.abc import Callable
from copy import deepcopy
from typing import Any


def _ceiling(value: int, name: str, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 1..{maximum}")


def bounded_wait(
    step: Callable[..., dict[str, Any]],
    *,
    max_frames: int,
    max_guest_ms: int,
    slice_guest_ms: int = 5000,
) -> dict[str, Any]:
    """Wait within the original frame/time ceilings using short native calls.

    ``step`` is called only with ``max_frames`` and ``max_guest_ms`` keyword
    arguments. Each request uses the remaining aggregate frame allowance and at
    most ``slice_guest_ms`` guest milliseconds. A frame ceiling ends the entire
    observation, even when guest time remains. If both ceilings are reached,
    the aggregate reports ``frame_limit`` and preserves the native stop cause
    in its raw receipt.

    The result is an explicit aggregate, never a replacement native receipt.
    Raw receipts are deep-copied before a later callback can reuse their data.
    Accounting checks here supplement the caller's native fencing; they cannot
    establish session identity, ownership, clock continuity, or valid rendering.

    Callback exceptions propagate unchanged and no further call is made. A
    malformed receipt raises ``ValueError`` without another call. Earlier
    steps may already have advanced the guest: neither failure is permission
    to replay the observation. The caller's native journal must retain partial
    evidence when an exception prevents returning the aggregate.

    Short guest slices reduce individual native-operation duration; they do
    not guarantee any host speed or change the caller's original host deadline.
    """
    if not callable(step):
        raise TypeError("step must be an already-fenced callable")
    _ceiling(max_frames, "max_frames", 10000)
    _ceiling(max_guest_ms, "max_guest_ms", 30000)
    _ceiling(slice_guest_ms, "slice_guest_ms", 5000)
    frames_total = guest_total = 0
    steps = []
    while frames_total < max_frames and guest_total < max_guest_ms:
        request = {"max_frames": max_frames - frames_total,
                   "max_guest_ms": min(slice_guest_ms, max_guest_ms - guest_total)}
        returned = step(**request)
        if not isinstance(returned, dict):
            raise ValueError("Bounded step receipt must be an object")
        receipt = deepcopy(returned)
        bounded = receipt.get("bounded")
        if not isinstance(bounded, dict):
            raise ValueError("Bounded step receipt lacks accounting")
        fields = ("max_frames", "max_guest_ms", "frames_completed", "guest_elapsed_ms")
        if any(type(bounded.get(name)) is not int for name in fields):
            raise ValueError("Bounded step counters must be integers")
        if any(bounded[name] != request[name] for name in request):
            raise ValueError("Bounded step receipt changed the requested ceiling")
        frames, elapsed = bounded["frames_completed"], bounded["guest_elapsed_ms"]
        if not (0 <= frames <= request["max_frames"]
                and 0 <= elapsed <= request["max_guest_ms"]):
            raise ValueError("Bounded step exceeded its frame or guest-time ceiling")
        if frames == elapsed == 0:
            raise ValueError("Bounded step made no frame or guest-time progress")
        cause = bounded.get("stop_cause")
        if cause not in ("frame_limit", "guest_time_limit"):
            raise ValueError("Bounded step has an unknown stop cause")
        if ((cause == "frame_limit" and frames != request["max_frames"])
                or (cause == "guest_time_limit" and elapsed != request["max_guest_ms"])):
            raise ValueError("Bounded step stop cause disagrees with its accounting")
        steps.append({"request": request, "receipt": receipt})
        frames_total += frames
        guest_total += elapsed
    return {"schema": "dotbox-bounded-wait-1",
            "limits": {"max_frames": max_frames, "max_guest_ms": max_guest_ms,
                       "slice_guest_ms": slice_guest_ms},
            "steps": steps,
            "totals": {"frames_completed": frames_total, "guest_elapsed_ms": guest_total},
            "stop_cause": "frame_limit" if frames_total == max_frames else "guest_time_limit"}
