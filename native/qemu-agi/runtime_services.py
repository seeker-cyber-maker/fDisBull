"""Explicit host services for native pending AGI requests.

Only native-emitted request records are dispatched here. There is no bytecode
framing, opcode execution, parser, renderer or invented device implementation.
Text output is implemented as a bounded readable ledger. Input, menu selection,
restart/quit, pause and save-slot selection require caller decisions. Remaining
device requests stay visibly unsupported, unless explicitly cancelled.

Save slots contain opaque native snapshots in memory, bound to the exact
resource package and executable. They are not original-interpreter save files
and are never silently written to disk.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys


def _runtime_module():
    path = Path(__file__).resolve().with_name("runtime_harness.py")
    for name in ("runtime_harness", "_fdisbull_agi_runtime_harness"):
        module = sys.modules.get(name)
        if module is not None and Path(getattr(module, "__file__", "")).resolve() == path:
            return module
    name = "_fdisbull_agi_runtime_harness"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


_runtime = _runtime_module()
HarnessError = _runtime.HarnessError
SAVE_SCHEMA = "fdisbull-agi-runtime-memory-save-1"
LEDGER_SCHEMA = "fdisbull-agi-runtime-output-ledger-1"
_TEXT_OUTPUTS = {101: "print", 102: "print.v", 135: "memory", 141: "version",
                 144: "log", 151: "print.at", 152: "print.at.v"}


class RuntimeServices:
    """Bounded host output and explicit decisions for one existing QMP owner.

    handle() auto-records only the text operations listed above. For other
    supported requests use handle(choice={...}) with an explicit accepted
    Boolean and text, number or slot when required. accepted=False means
    cancellation, never successful emulation of an unavailable device.

    An unsupported outcome leaves the native PC, pending ID and state intact.
    The caller can inspect its ticket and choose another device implementation.
    """

    def __init__(self, vm, *, max_outputs=4096, max_slots=256,
                 max_saved_bytes=64 * 1024**2):
        for value, limit, name in ((max_outputs, 65536, "max_outputs"),
                                   (max_slots, 256, "max_slots"),
                                   (max_saved_bytes, 256 * 1024**2, "max_saved_bytes")):
            if type(value) is not int or not 1 <= value <= limit:
                raise ValueError(f"{name} must be an integer in 1..{limit}")
        self.vm = vm
        self.max_outputs, self.max_slots = max_outputs, max_slots
        self.max_saved_bytes = max_saved_bytes
        self._ledger, self._slots = [], {}
        self._output_attempts = set()

    @property
    def ledger(self):
        return {"schema": LEDGER_SCHEMA, "package_sha256": self.vm.package_sha256,
                "binary_sha256": self.vm.binary_sha256, "entries": deepcopy(self._ledger)}

    @property
    def slots(self):
        """Independent copies, suitable for explicit transfer to a matching owner."""
        return deepcopy(self._slots)

    @staticmethod
    def _slot_name(name):
        if type(name) is not str or not 1 <= len(name) <= 128 or "\0" in name:
            raise ValueError("slot must be an explicit non-NUL name of 1..128 characters")
        return name

    def _validate_save(self, saved):
        if type(saved) is not dict or set(saved) != {
            "schema", "package_sha256", "binary_sha256", "sha256", "snapshot"
        } or saved["schema"] != SAVE_SCHEMA \
                or saved["package_sha256"] != self.vm.package_sha256 \
                or saved["binary_sha256"] != self.vm.binary_sha256:
            raise HarnessError("Save slot schema, resource package or executable differs")
        snapshot = saved["snapshot"]
        if type(snapshot) is not bytes or not 1 <= len(snapshot) <= _runtime.MAX_SNAPSHOT_BYTES \
                or saved["sha256"] != sha256(snapshot).hexdigest():
            raise HarnessError("Save slot snapshot bytes differ from their bound identity")
        return deepcopy(saved)

    def _slot_capacity(self, name, saved):
        if name not in self._slots and len(self._slots) >= self.max_slots:
            raise HarnessError("Memory save-slot capacity exhausted")
        size = sum(len(value["snapshot"]) for key, value in self._slots.items() if key != name)
        if size + len(saved["snapshot"]) > self.max_saved_bytes:
            raise HarnessError("Memory save-byte capacity exhausted")

    def install_slot(self, name, saved):
        """Import an explicitly supplied same-package, same-executable memory save."""
        name = self._slot_name(name)
        value = self._validate_save(saved)
        self._slot_capacity(name, value)
        self._slots[name] = value

    def _finish(self, ticket, kind, action, details=None):
        if len(self._ledger) >= self.max_outputs:
            raise HarnessError("Host output-ledger capacity exhausted")
        entry = {"sequence": len(self._ledger) + 1, "kind": kind, "status": "recorded",
                 "request": deepcopy(ticket)}
        if details:
            entry.update(deepcopy(details))
        self._ledger.append(entry)
        try:
            state = action()
        except ValueError:
            entry["status"] = "rejected_locally"
            raise
        except BaseException:
            entry["status"] = "completion_failed_or_unknown"
            raise
        entry["status"] = "completed"
        return {"status": kind, "request": deepcopy(ticket), "state": state,
                "ledger_sequence": entry["sequence"]}

    @staticmethod
    def _choice(choice, extra=()):
        if type(choice) is not dict or set(choice) != {"accepted", *extra} \
                or type(choice.get("accepted")) is not bool:
            raise ValueError("choice requires explicit accepted Boolean and exactly "
                             + ", ".join(extra or ("no extra fields",)))

    def handle(self, *, choice=None):
        """Handle one stopped request; never run the guest or choose missing input."""
        ticket = self.vm.pending()
        if ticket is None:
            if choice is not None:
                raise HarnessError("No native request is pending for this choice")
            return {"status": "idle", "request": None}
        effect = ticket["effect"]
        opcode, reply = effect["opcode"], effect["reply"]
        if choice is not None and type(choice) is not dict:
            raise ValueError("choice must be an explicit dictionary")
        if choice is not None and choice.get("accepted") is False:
            self._choice(choice)
            return self._finish(ticket, "cancelled",
                                lambda: self.vm.complete(ticket, accepted=False))
        if opcode in _TEXT_OUTPUTS and reply == "ack":
            if choice is not None:
                self._choice(choice)
            key = (ticket["context"], effect["id"])
            if key in self._output_attempts:
                raise HarnessError("Output completion was already attempted; inspect state before resolving")
            # Recording the complete exposed text implements this host service.
            # QOM projects the native CP437 text losslessly into Unicode.
            # Even when completion is uncertain the output stays in the ledger.
            if len(self._ledger) >= self.max_outputs:
                raise HarnessError("Host output-ledger capacity exhausted")
            self._output_attempts.add(key)
            return self._finish(
                ticket, "output", lambda: self.vm.complete(ticket, accepted=True),
                {"operation": _TEXT_OUTPUTS[opcode], "text": effect["text"]},
            )
        if opcode == 125 and reply == "ack":
            if choice is None:
                return self._waiting(ticket, "slot")
            self._choice(choice, ("slot",))
            name = self._slot_name(choice["slot"])
            snapshot = self.vm.snapshot()
            saved = self._validate_save({
                "schema": SAVE_SCHEMA, "package_sha256": self.vm.package_sha256,
                "binary_sha256": self.vm.binary_sha256, "snapshot": snapshot,
                "sha256": sha256(snapshot).hexdigest(),
            })
            self._slot_capacity(name, saved)

            def save():
                state = self.vm.complete(ticket, accepted=True)
                self._slots[name] = saved
                return state

            return self._finish(ticket, "saved", save,
                                {"slot": name, "snapshot_sha256": saved["sha256"],
                                 "snapshot_size": len(snapshot)})
        if opcode == 126 and reply == "restore":
            if choice is None:
                return self._waiting(ticket, "slot")
            self._choice(choice, ("slot",))
            name = self._slot_name(choice["slot"])
            if name not in self._slots:
                raise HarnessError("Requested memory save slot does not exist")
            saved = self._validate_save(self._slots[name])
            return self._finish(
                ticket, "restored", lambda: self.vm.restore(ticket, saved["snapshot"]),
                {"slot": name, "snapshot_sha256": saved["sha256"]},
            )
        if reply in ("text", "number", "menu", "choice") or (opcode == 136 and reply == "ack"):
            field = "text" if reply == "text" else "number" if reply in ("number", "menu") else None
            if choice is None:
                return self._waiting(ticket, field)
            self._choice(choice, () if field is None else (field,))
            values = {} if field is None else {field: choice[field]}
            return self._finish(
                ticket, "completed", lambda: self.vm.complete(ticket, accepted=True, **values),
                {"reply": deepcopy(choice)},
            )
        if choice is not None:
            self._choice(choice)
        return {"status": "unsupported", "request": deepcopy(ticket),
                "reason": "No implemented host device service for this native request"}

    @staticmethod
    def _waiting(ticket, field):
        required = ["accepted"] + ([] if field is None else [field])
        return {"status": "choice_required", "request": deepcopy(ticket),
                "required": required}
