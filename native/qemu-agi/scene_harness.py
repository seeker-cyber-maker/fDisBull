#!/usr/bin/env python3
"""Stopped scene projection for a caller-owned experimental AGI QEMU session.

AGISceneHarness never launches, closes, or takes ownership of its VM. The parent
``with QemuAGI(...)`` remains the process owner. This adapter brackets native
records with stopped snapshots, delegates all data validation to the shared
consumer, and immediately resynchronizes from that same snapshot after a gap.

The optional CLI explicitly owns one QemuAGI child and runs only the small
homegrown program below. It requires an explicit binary and a new output file.
Install the matching fdisbull-core package before using the standalone CLI.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid

from fdisbull_core.agi_scene import AGISceneConsumer, SceneInputError


class SceneOperationError(RuntimeError):
    """An operation failed after consuming a successful checkpoint receipt.

    ``operation`` is configure, restart, clear_events or run. ``stage`` is
    control (native setter group), run (native execution), or capture (the
    following stopped capture). ``receipts`` is detached: controls retain a
    full ``pending_capture``; a prepared run retains its ``preparation`` result.
    The original exception is ``__cause__``. Nothing is retried or rolled back.
    """

    def __init__(self, operation, stage, receipts):
        self.operation = operation
        self.stage = stage
        self.receipts = deepcopy(receipts)
        super().__init__(
            f"AGI scene {operation} failed during {stage}; "
            "successful checkpoint receipts are available in .receipts"
        )


# Five position instructions (one deliberately repeated), followed by return.
# Raw code-relative PCs: 0, 4, 8, 12, 16, 20. No game resource is embedded.
DEMO_CODE = bytes.fromhex("25000a1425011e2825000a142500323c2501465000")
DEMO_INSTRUCTIONS = 6


class AGISceneHarness:
    """Project scene state without changing native interpretation or lifecycle.

    ``attachment`` is the initial snapshot receipt, with update status
    ``attached``. Every result contains ``update`` and the detached ``view``.
    Control methods additionally return ``pending_update`` so observations
    captured before a control change are not silently discarded. A budgeted
    ``run`` preserves that control result as ``preparation``. If a subsequent
    operation fails, SceneOperationError retains these successful receipts and
    the original cause. A failed initial capture is propagated unchanged.
    """

    def __init__(self, vm):
        self.vm = vm
        self._session_id = str(uuid.uuid4())
        self._consumer = None
        self.attachment = self.capture()

    @property
    def session_id(self):
        """Identity of this attachment, never inferred from code bytes or PCs."""
        return self._session_id

    def view(self):
        """Return the shared consumer's detached current scene view."""
        return self._consumer.view()

    def capture(self):
        """Read one stable stopped checkpoint; never retry a changing capture."""
        before = self.vm.state()
        events = self.vm.events()
        state = self.vm.state()
        if before != state:
            raise SceneInputError("Stopped AGI checkpoint changed during capture")

        if self._consumer is None:
            consumer = AGISceneConsumer.from_snapshot(state, session_id=self.session_id)
            # Validate the envelope and seed retained history without replaying
            # pre-attachment records or manufacturing their missing history.
            initial = consumer.consume(events, state, session_id=self.session_id)
            if initial["needs_resync"]:
                raise SceneInputError("Initial AGI snapshot and records do not form a checkpoint")
            self._consumer = consumer
            update = {"status": "attached", "needs_resync": False,
                      "reason": "initial_attachment", "changes": []}
        else:
            update = self._consumer.consume(events, state, session_id=self.session_id)
            if update["needs_resync"]:
                update = self._consumer.resync(
                    state, reason=update["reason"], session_id=self.session_id,
                )
        return {"update": update, "view": self.view()}

    def _control(self, name, operation):
        # If this first capture fails, nothing was consumed successfully and
        # the original capture error must remain visible without wrapping.
        pending = self.capture()
        stage = "control"
        try:
            operation()
            stage = "capture"
            result = self.capture()
        except Exception as error:
            raise SceneOperationError(
                name, stage, {"pending_capture": pending},
            ) from error
        result["pending_update"] = pending["update"]
        return result

    def configure(self, *, mask=None, capacity=None, step_budget=None):
        """Capture pending work before controls and checkpoint their completion."""
        return self._control("configure", lambda: self.vm.configure(
            mask=mask, capacity=capacity, step_budget=step_budget,
        ))

    def restart(self):
        """Explicitly restart the caller-owned VM and capture the new epoch."""
        return self._control("restart", self.vm.restart)

    def clear_events(self):
        """Explicitly clear native observations and capture the new epoch."""
        return self._control("clear_events", self.vm.clear_events)

    def run(self, *, step_budget=None):
        """Run to the native bounded stop, then capture; no implicit reset."""
        preparation = None
        if step_budget is not None:
            preparation = self.configure(step_budget=step_budget)
        stage = "run"
        try:
            self.vm.run()
            stage = "capture"
            result = self.capture()
        except Exception as error:
            if preparation is None:
                raise
            raise SceneOperationError(
                "run", stage, {"preparation": preparation},
            ) from error
        if preparation is not None:
            result["preparation"] = preparation
        return result


def _bounded_int(text, minimum, maximum):
    try:
        value = int(text)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("Expected a decimal integer") from error
    if not minimum <= value <= maximum:
        raise argparse.ArgumentTypeError(f"Expected an integer in {minimum}..{maximum}")
    return value


def _bounded_timeout(text):
    try:
        value = float(text)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("Expected a finite timeout") from error
    if not math.isfinite(value) or not 0.1 <= value <= 30:
        raise argparse.ArgumentTypeError("Timeout must be finite and in 0.1..30 seconds")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Explicit qemu-system-agi executable")
    parser.add_argument("--output", required=True, help="New JSON receipt path; never overwritten")
    parser.add_argument("--mask", type=int, choices=(0, 1, 2, 3), default=2)
    parser.add_argument("--capacity", type=lambda value: _bounded_int(value, 0, 65536), default=64)
    parser.add_argument("--step-budget", type=lambda value: _bounded_int(value, 1, 4096), default=2)
    parser.add_argument("--timeout", type=_bounded_timeout, default=10.0)
    args = parser.parse_args(argv)

    output = Path(args.output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Scene demonstration requires a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "fdisbull-agi-scene-demo-1",
        "status": "running",
        "scope": "Authored scalar/position pilot; no complete AGI game or parity claim",
        "parameters": {"mask": args.mask, "capacity": args.capacity,
                       "step_budget": args.step_budget, "timeout": args.timeout,
                       "maximum_resumes": DEMO_INSTRUCTIONS},
        "program": {"hex": DEMO_CODE.hex(), "size": len(DEMO_CODE),
                    "sha256": hashlib.sha256(DEMO_CODE).hexdigest()},
        "captures": [],
    }
    # Reserve the caller's new file before starting a child. Failed attempts
    # retain a truthful bounded receipt and cannot overwrite earlier evidence.
    with output.open("x", encoding="utf-8") as stream:
        try:
            from harness import HarnessError, QemuAGI

            with QemuAGI(args.binary, DEMO_CODE, timeout=args.timeout) as vm:
                report["binary"] = {"path": str(vm.binary), "sha256": vm.binary_sha256}
                scene = AGISceneHarness(vm)
                report["session_id"] = scene.session_id
                report["attachment"] = scene.attachment
                report["configuration"] = scene.configure(
                    mask=args.mask, capacity=args.capacity, step_budget=args.step_budget,
                )
                for _ in range(DEMO_INSTRUCTIONS):
                    report["captures"].append(scene.run())
                    state = vm.state()
                    if state["guest"]["status"] in ("return", "fault"):
                        break
                else:
                    raise HarnessError("Authored scene demonstration exceeded its resume bound")
                report["final_state"] = state
                if state["guest"]["status"] != "return":
                    raise HarnessError("Authored scene demonstration did not return normally")
                report["status"] = "completed"
        except BaseException as error:
            report["status"] = "failed"
            report["failure"] = {"type": type(error).__name__, "message": str(error)}
            if isinstance(error, SceneOperationError):
                report["failure"].update({
                    "operation": error.operation, "stage": error.stage,
                    "receipts": error.receipts,
                })
                if error.__cause__ is not None:
                    report["failure"]["cause"] = {
                        "type": type(error.__cause__).__name__,
                        "message": str(error.__cause__),
                    }
            raise
        finally:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
