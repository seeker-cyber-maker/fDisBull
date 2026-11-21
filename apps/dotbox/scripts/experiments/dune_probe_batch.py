"""Fixed, private Dune dispatch experiment; not a DotBox live rewind API.

The caller owns an isolated guest already stopped at the observed throne-room
baseline and supplies call(method, params, timeout_ms=...). This module does not
launch a guest, import fDisBull, select actions with a model, or roll disk back.
Use a fresh private output directory for prepare(), then run_batch(). Original
game files, checkpoints, screenshots and raw memory must stay outside Git.

Every row restores the same memory checkpoint and runs one settling frame before
arming probes and queuing one ordinary left click. Probes stop BEFORE execution.
``dispatch`` stops at a resolved row destination, a non-row control destination,
or the empty row's observed fallback; it does not execute those destination
bodies. ``full`` continues after owned one-shot hits for 120 completed frames.
The idle dispatch row observes 30 frames. Input is not reissued after a hit;
the next restore retires pending input. Unexpected stops abort the entire batch.

Host budgets are cooperative admission checks between RPCs, not hard transport
timeouts. A single admitted call can outlast that allowance. Any RPC exception
leaves dispatch uncertain: save the report and make NO further native calls.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import time


SOURCE_SHA256 = "32439602abe95e0ff778653ad58052bfed56a73e103b92f079455daa2ee886e7"
SOURCE_SIZE = 74757
CS, DS, HEADER = 0x0824, 0x16F3, 0x200
RAM_BYTES = 0xA0000
ANCHORS = (
    ("control_callback", 0xD326, 3), ("row_resolved", 0xCE8A, 9),
    ("row_jump", 0xCE93, 2), ("generic_si_plus_2", 0xD2FE, 3),
    ("generic_si_plus_6", 0xD33D, 3), ("generic_action", 0xD2C1, 3),
)
TRIALS = (
    ("idle", None), ("see_dune_map", (160, 163)), ("duke_leto", (160, 171)),
    ("empty_row", (160, 179)), ("north", (274, 167)), ("east", (289, 177)),
    ("south", (274, 186)), ("center", (274, 177)),
    ("see_dune_map_repeat", (160, 163)),
)
ROW_CALLBACKS = frozenset((0xCE71, 0xCE76, 0xCE7B, 0xCE80, 0xCE85))
CANARY_BEFORE = b"Authored Dune probe canary: before checkpoint\n"
CANARY_AFTER = b"Authored Dune probe canary: newer disk version; preserve after restore\n"


class BatchAborted(RuntimeError):
    """The private report retains the incomplete trial and original stop."""


class UnexpectedStop(BatchAborted):
    def __init__(self, message, *, result=None, status=None):
        super().__init__(message)
        self.evidence = {"result": result, "status": status}


class HostBudgetExpired(BatchAborted):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _new_file(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(data)


def _json(path, value, *, new=False):
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if new:
        _new_file(path, data)
    else:
        # Only the report created by this invocation is replaced.
        temporary = path.with_suffix(".json.new")
        _new_file(temporary, data)
        os.replace(temporary, path)


def _paths(root, game):
    root, game = Path(root).expanduser().resolve(), Path(game).expanduser().resolve(strict=True)
    repository = Path(__file__).resolve().parents[2]
    if not game.is_dir() or root.is_relative_to(game) or root.is_relative_to(repository):
        raise ValueError("Evidence must be outside the game mount and repository")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root, game


def _files(game):
    return {str(p.relative_to(game)): {"size": p.stat().st_size, "sha256": _sha(p.read_bytes())}
            for p in sorted(game.rglob("*")) if p.is_file()}


def _file_diff(before, after):
    return {name: {"before": before.get(name), "after": after.get(name)}
            for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)}


def _register_key(registers):
    return {k: v for k, v in registers.items() if k not in ("session_id", "state_revision")}


def _real_mode(registers, *, baseline=False):
    context = registers.get("address_context", {})
    if (registers.get("cpu_mode") != "real" or registers.get("code_bits") != 16
            or registers.get("stack_bits") != 16 or context.get("paging_enabled") is not False):
        raise BatchAborted("The qualified real-mode, 16-bit, unpaged context changed")
    if baseline and (int(registers["segments"]["cs"], 16) != CS
                     or int(registers["segments"]["ds"], 16) != DS):
        raise BatchAborted("The qualified Dune code/data segments changed")


def _address(value):
    if not isinstance(value, dict) or value.get("space") != "segmented":
        raise ValueError("Expected a segmented execution address")
    return int(value["segment"], 16), int(value["offset"], 16)


def _opening_menu(data, table):
    """Bind the fixed trial names/coordinates to the observed opening menu."""
    def word(offset):
        if not 0 <= offset <= len(data) - 2:
            raise BatchAborted("Menu pointer leaves the captured data segment")
        return struct.unpack_from("<H", data, offset)[0]

    if len(data) != 65536:
        raise BatchAborted("Opening-menu guard needs a complete data segment")
    pointer = word(0x2840)
    menu = word(pointer)
    if not 0 <= menu <= len(data) - 10:
        raise BatchAborted("Menu entries leave the captured data segment")
    skip = struct.unpack_from("<b", data, menu + 1)[0]
    entries = [(word(menu + 2 + index * 4), word(menu + 4 + index * 4)) for index in range(2)]
    if ((pointer, menu, data[menu], skip, data[0xFED4], data[0xFED5])
            != (0x2824, 0x2598, 0xFF, 0, 0, 0xFF)
            or entries != [(0x008E, 0x1BBF), (0x006E, 0x9DDC)]):
        raise BatchAborted("The fixed trial names require the qualified opening menu")
    rows = []
    for bounds, callback in (((92, 159, 228, 167), 0xCE85), ((92, 167, 228, 175), 0xCE80)):
        matches = [record for record in table if tuple(record["bounds"]) == bounds]
        if (len(matches) != 1 or tuple(matches[0]["flag_bytes"]) != (0x80, 0)
                or matches[0]["value"] != 27 or matches[0]["callback"] != callback):
            raise BatchAborted("Active opening command geometry differs from the fixed click recipe")
        rows.append(matches[0])
    return {"pointer": pointer, "menu": menu, "skip": skip,
            "mode": data[0xFED4], "special_row": data[0xFED5],
            "entries": [{"offset": menu + 2 + index * 4, "metadata": meta, "handler": handler}
                        for index, (meta, handler) in enumerate(entries)], "active_rows": rows}


class _Runner:
    def __init__(self, call, root, game):
        self.call = call
        self.root, self.game = _paths(root, game)
        self.source = (self.game / "DUNEPRG.EXE").read_bytes()
        if len(self.source) != SOURCE_SIZE or _sha(self.source) != SOURCE_SHA256:
            raise BatchAborted("DUNEPRG.EXE does not match the qualified executable")
        self.session_id = None
        self.owned = set()
        self.probes = {}
        self.by_address = {}
        self.uncertain = False
        self.stopped = False
        self.deadline = None

    def rpc(self, method, params=None, *, timeout_ms=15000):
        if self.uncertain:
            raise BatchAborted("No native calls are allowed after uncertain dispatch")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise HostBudgetExpired("Cooperative host admission budget expired")
        try:
            result = self.call(method, params or {}, timeout_ms=timeout_ms)
        except BaseException:
            self.uncertain = True
            raise
        if not isinstance(result, dict) or not isinstance(result.get("session_id"), str):
            self.uncertain = True
            raise BatchAborted("Native response did not identify the owned session")
        if self.session_id is None:
            self.session_id = result["session_id"]
        elif result["session_id"] != self.session_id:
            self.uncertain = True
            raise BatchAborted("Native response changed session identity")
        return result

    def status(self, reply=None):
        status = self.rpc("session.status")
        self.stopped = status.get("state") == "stopped"
        if not self.stopped:
            raise UnexpectedStop("Guest is not confirmed stopped", result=reply, status=status)
        if reply is not None and (status.get("state_revision") != reply.get("state_revision")
                                 or ("stop_reason" in reply and status.get("last_stop") != reply["stop_reason"])):
            raise UnexpectedStop("Fresh status does not match the observed boundary", result=reply, status=status)
        return status

    def neutral(self):
        keyboard = self.rpc("input.keyboard.state")
        mouse = self.rpc("input.mouse.state")
        k, m = keyboard["keyboard"], mouse["mouse"]
        if (any(k[name] != 0 for name in ("pending_events", "owned_keys", "queued_guest_ms"))
                or k["frame_keys"] or any(m[name] != 0 for name in
                    ("buttons", "owned_buttons", "pending_release_buttons")) or m["release_pending"]):
            raise BatchAborted("Admission requires neutral keyboard and mouse input")
        return keyboard, mouse

    def memory(self, address, length):
        blocks = []
        for offset in range(0, length, 65536):
            size = min(65536, length - offset)
            response = self.rpc("memory.read", {"address": {"space": "linear", "offset": f"0x{address + offset:08X}"},
                                                 "length": size})
            block = base64.b64decode(response["data_base64"], validate=True)
            if len(block) != size:
                raise BatchAborted("Native memory response has the wrong length")
            blocks.append(block)
        return b"".join(blocks)

    def code(self, segment, offset, length):
        if segment != CS or not 0 < offset <= 0x10000 - length or HEADER + offset + length > len(self.source):
            raise BatchAborted("Destination is outside the qualified original near-code mapping")
        live = self.memory(segment * 16 + offset, length)
        if live != self.source[HEADER + offset:HEADER + offset + length]:
            raise BatchAborted("Loaded instruction bytes differ from the qualified file mapping")
        return _sha(live)

    def bindings(self):
        return [{"label": label, "segment": CS, "offset": offset, "length": length,
                 "bytes_sha256": self.code(CS, offset, length)} for label, offset, length in ANCHORS]

    def screenshot(self, name):
        response = self.rpc("video.screenshot")
        data = base64.b64decode(response.get("data_base64") or response["png_base64"], validate=True)
        _new_file(self.root / name, data)
        return {**{k: v for k, v in response.items() if not k.endswith("base64")},
                "file": name, "bytes": len(data), "sha256": _sha(data)}

    def no_foreign_probes(self):
        entries = self.rpc("breakpoints.list")["breakpoints"]
        if any(item["breakpoint_id"] not in self.owned for item in entries):
            raise BatchAborted("Foreign breakpoint definitions prevent batch admission")
        return entries

    def arm(self, label, segment, offset):
        key = (segment, offset)
        if key in self.by_address:
            probe = self.by_address[key]
            if label not in probe["labels"]:
                probe["labels"].append(label)
            return  # A consumed one-shot is never implicitly rearmed.
        identity = self.code(segment, offset, 3)
        reply = self.rpc("breakpoints.create", {"kind": "execution", "once": True,
                         "address": {"space": "segmented", "segment": f"0x{segment:04X}",
                                     "offset": f"0x{offset:08X}"}})
        identifier = reply.get("breakpoint_id")
        if not isinstance(identifier, str) or not identifier:
            self.uncertain = True
            raise BatchAborted("Created probe has no usable identity")
        self.owned.add(identifier)
        if reply.get("kind") != "execution" or reply.get("once") is not True or _address(reply["address"]) != key:
            raise BatchAborted("Native probe receipt differs from requested definition")
        probe = {"id": identifier, "labels": [label], "segment": segment, "offset": offset,
                 "active": True, "bytes_sha256": identity}
        self.probes[identifier] = probe
        self.by_address[key] = probe

    def accept_stop(self, result, status):
        reason = result.get("stop_reason", {})
        probe = self.probes.get(reason.get("breakpoint_id"))
        try:
            address = _address(reason.get("address"))
            registers = result["registers"]
            pc = (int(registers["segments"]["cs"], 16), int(registers["instruction_pointer"], 16))
        except (KeyError, TypeError, ValueError):
            raise UnexpectedStop("Stop lacks a qualified address/register snapshot", result=result, status=status)
        if (result.get("completed") is not False or reason.get("kind") != "breakpoint"
                or probe is None or not probe["active"] or probe["id"] not in self.owned
                or address != (probe["segment"], probe["offset"]) or pc != address):
            raise UnexpectedStop("Stop is not an active owned one-shot hit", result=result, status=status)
        _real_mode(registers)
        probe["active"] = False
        return probe

    def cleanup(self):
        if self.uncertain or not self.stopped:
            return {"status": "preserved_without_native_calls", "owned_ids": sorted(self.owned)}
        saved_deadline, self.deadline = self.deadline, None
        removed = []
        try:
            for item in self.rpc("breakpoints.list")["breakpoints"]:
                identifier = item["breakpoint_id"]
                if identifier in self.owned:
                    reply = self.rpc("breakpoints.delete", {"breakpoint_id": identifier})
                    if reply.get("deleted") is not True or reply.get("breakpoint_id") != identifier:
                        raise BatchAborted("Owned probe cleanup was not acknowledged")
                    removed.append(identifier)
            remaining = self.rpc("breakpoints.list")["breakpoints"]
            if any(item["breakpoint_id"] in self.owned for item in remaining):
                raise BatchAborted("Owned probes remain after cleanup")
            self.owned.clear()
            self.probes.clear()
            self.by_address.clear()
            return {"status": "clean", "deleted": removed,
                    "foreign_preserved": [item["breakpoint_id"] for item in remaining]}
        finally:
            self.deadline = saved_deadline

    def frame(self):
        result = self.rpc("frame.step")
        status = self.status(result)
        if result.get("completed") is True:
            if result.get("stop_reason", {}).get("kind") != "frame":
                raise UnexpectedStop("Completed frame has another stop reason", result=result, status=status)
            return result, None
        return result, self.accept_stop(result, status)

    def restore(self, baseline):
        self.status()
        self.no_foreign_probes()
        if self.owned:
            raise BatchAborted("Owned probes must be cleaned before restore")
        checkpoint = self.root / baseline["checkpoint"]["file"]
        if _sha(checkpoint.read_bytes()) != baseline["checkpoint"]["sha256"]:
            raise BatchAborted("Checkpoint identity changed")
        prior_files = _files(self.game)
        started = time.monotonic()
        reply = self.rpc("state.load", {"path": str(checkpoint), "frame_keys": []}, timeout_ms=30000)
        self.status(reply)
        if reply.get("completed") is not True or reply.get("frame_keys") != []:
            raise BatchAborted("Memory restore was not acknowledged with neutral frame keys")
        self.no_foreign_probes()
        registers = self.rpc("state.get_registers")
        _real_mode(registers, baseline=True)
        ram = self.memory(0, RAM_BYTES)
        timing = self.rpc("execution.timing")
        record = {"reply": reply, "host_ms": (time.monotonic() - started) * 1000,
                  "registers_equal": _register_key(registers) == _register_key(baseline["registers"]),
                  "ram_sha256": _sha(ram), "ram_equal": _sha(ram) == baseline["ram_sha256"],
                  "guest_ticks_equal": timing["guest_ticks"] == baseline["timing"]["guest_ticks"],
                  "files_changed_by_restore": _file_diff(prior_files, _files(self.game)),
                  "canary_preserved": (self.game / baseline["canary"]).read_bytes() == CANARY_AFTER}
        if (not all(record[k] for k in ("registers_equal", "ram_equal", "guest_ticks_equal", "canary_preserved"))
                or record["files_changed_by_restore"]):
            error = BatchAborted("Restore equality or disk-preservation check failed")
            error.evidence = record
            raise error
        self.neutral()
        record["settle"], probe = self.frame()
        if probe is not None:
            raise UnexpectedStop("A probe interrupted the uninstrumented settling frame", result=record["settle"])
        self.neutral()
        record["settled_ram_sha256"] = _sha(self.memory(0, RAM_BYTES))
        return record


def prepare(call, root, game):
    """Qualify this loaded edition and save one neutral private memory baseline.

    This adapter targets the legacy 0.34.1 native state protocol. A caller using
    a generation-fenced backend must provide a session-bound adapter that adds
    its current expected_generation; this script does not grant input ownership.
    """
    runner = _Runner(call, root, game)
    root, game = runner.root, runner.game
    if (root / "baseline.json").exists() or (root / "throne-baseline.sav").exists():
        raise ValueError("Prepare requires a fresh evidence directory")
    runner.status()
    runner.no_foreign_probes()
    registers = runner.rpc("state.get_registers")
    _real_mode(registers, baseline=True)
    keyboard, mouse = runner.neutral()
    bindings = runner.bindings()
    data = runner.memory(DS * 16, 65536)
    count = struct.unpack_from("<H", data, 0x2184)[0]
    if not 1 <= count <= 64:
        raise BatchAborted("Control-table count is outside the observed bounded layout")
    table = []
    for index in range(count):
        offset = 0x2186 + index * 14
        values = struct.unpack_from("<4H2B2H", data, offset)
        table.append({"record_offset": offset, "bounds": values[:4], "flag_bytes": values[4:6],
                      "value": values[6], "callback": values[7]})
    menu_identity = _opening_menu(data, table)
    canary = "DB" + _sha(str(root).encode())[:6].upper() + ".TXT"
    _new_file(game / canary, CANARY_BEFORE)
    checkpoint = root / "throne-baseline.sav"
    saved = runner.rpc("state.save", {"path": str(checkpoint)}, timeout_ms=30000)
    runner.status(saved)
    if saved.get("completed") is not True or saved.get("frame_keys") != []:
        raise BatchAborted("Checkpoint was not acknowledged with neutral frame keys")
    ram = runner.memory(0, RAM_BYTES)
    baseline = {"schema": "dune-probe-baseline-1", "created_unix": time.time(),
                "source_sha256": SOURCE_SHA256, "saved": saved,
                "checkpoint": {"file": checkpoint.name, "sha256": _sha(checkpoint.read_bytes())},
                "registers": runner.rpc("state.get_registers"), "timing": runner.rpc("execution.timing"),
                "keyboard": keyboard, "mouse": mouse, "ram_sha256": _sha(ram),
                "ds_sha256": _sha(data), "canary": canary, "files_at_save": _files(game),
                "bindings": bindings, "control_table": table, "menu_identity": menu_identity,
                "screenshot": runner.screenshot("throne-baseline.png")}
    _new_file(root / "baseline-conventional-ram.bin", ram)
    _new_file(root / "baseline-ds.bin", data)
    _json(root / "baseline.json", baseline, new=True)
    (game / canary).write_bytes(CANARY_AFTER)
    return baseline


def _capture_hit(runner, probe, result, trial):
    registers = result["registers"]
    labels = list(probe["labels"])
    hit = {"sequence": len(trial["hits"]), "label": labels[0], "aliases": labels[1:],
           "breakpoint_id": probe["id"], "cs": probe["segment"], "ip": probe["offset"],
           "completed_frames_before": trial["frames_completed"], "guest_ticks": result.get("guest_ticks"),
           "stop_reason": result["stop_reason"], "registers": registers, "timing": "before_instruction"}
    trial["hits"].append(hit)
    general = {key: int(value, 16) for key, value in registers["general"].items()}
    if "control_callback" in labels:
        ds, di = int(registers["segments"]["ds"], 16), general["edi"] & 0xFFFF
        if ds != DS or not 0x2186 <= di < 0x2186 + 64 * 14 or (di - 0x2186) % 14:
            raise BatchAborted("Observed control pointer is outside the qualified table")
        values = struct.unpack("<4H2B2H", runner.memory(ds * 16 + di, 14))
        hit["control"] = {"record_offset": di, "bounds": values[:4], "flag_bytes": values[4:6],
                          "value": values[6], "callback": values[7]}
        trial["control_is_row"] = values[7] in ROW_CALLBACKS
        runner.arm("control_destination", CS, values[7])
    if "row_resolved" in labels or "row_jump" in labels:
        hit.update(row=general["ecx"] & 0xFFFF, menu_metadata=general["eax"] & 0xFFFF,
                   handler=general["ebx"] & 0xFFFF, menu_entry=general["esi"] & 0xFFFF)
    if "row_jump" in labels and hit["handler"]:
        runner.arm("row_destination", CS, hit["handler"])
    return labels


def run_batch(call, root, game, *, profile="full"):
    """Run all fixed rows without per-trial model decisions; return private report.

    On any unexpected stop or RPC error, raise BatchAborted with report_path.
    An acknowledged unexpected stop permits deletion of owned probe definitions
    only. An uncertain RPC permits no subsequent native calls, including cleanup.
    """
    if profile not in ("full", "dispatch"):
        raise ValueError("profile must be full or dispatch")
    runner = _Runner(call, root, game)
    root, game = runner.root, runner.game
    baseline = json.loads((root / "baseline.json").read_text())
    if (baseline.get("schema") != "dune-probe-baseline-1" or baseline.get("source_sha256") != SOURCE_SHA256
            or baseline.get("checkpoint", {}).get("file") != "throne-baseline.sav"):
        raise BatchAborted("The baseline is not this adapter's qualified checkpoint")
    report_path = root / ("batch-" + profile + "-result.json")
    report = {"schema": "dune-probe-batch-1", "profile": profile, "completed": False,
              "started_unix": time.time(), "recipe": {"settling_frames": 1,
                  "observation_frames": 120, "dispatch_idle_frames": 30, "max_probe_stops": 24,
                  "trial_cooperative_host_seconds": 12, "rpc_timeout_ms": 15000,
                  "state_rpc_timeout_ms": 30000, "disk_rollback": False, "mouse_hold_ms": 80,
                  "stop_timing": "before_instruction", "input_reissued_after_hit": False,
                  "dynamic_rules": ["control_callback: observe DS:DI+12 near callback",
                                    "row_jump: observe BX near destination"],
                  "continuation": "owned one-shot hits only; dispatch stops before destination body",
                  "timeout_note": "Frame exhaustion is an observation timeout; RPC exceptions abort with uncertain dispatch."},
              "trials": []}
    _json(report_path, report, new=True)
    started = time.monotonic()
    try:
        runner.status()
        if runner.session_id != baseline["saved"]["session_id"]:
            raise BatchAborted("Checkpoint belongs to a different native session")
        runner.no_foreign_probes()
        runner.neutral()
        for epoch, (name, point) in enumerate(TRIALS, 1):
            trial_start = time.monotonic()
            runner.deadline = trial_start + 12
            trial = {"name": name, "point": point, "restore_epoch": epoch,
                     "hits": [], "frames_completed": 0, "step_calls": 0}
            report["trials"].append(trial)
            trial["restore"] = runner.restore(baseline)
            before_files = _files(game)
            before_ticks = runner.rpc("execution.timing")["guest_ticks"]
            if runner.bindings() != baseline["bindings"]:
                raise BatchAborted("Loaded anchor identity changed")
            for label, offset, _ in ANCHORS:
                runner.arm(label, CS, offset)
            settle = trial["restore"]["settle"]
            trial["input"] = None if point is None else runner.rpc("input.mouse.click", {
                "x": point[0], "y": point[1], "button": "left", "hold_ms": 80,
                "mode_id": settle["mode_id"], "frame_id": settle["frame_id"]})
            if point is not None:
                if trial["input"].get("accepted") is not True or trial["input"].get("delivery") != "queued":
                    raise BatchAborted("The ordinary mouse click was not acknowledged as queued")
                runner.status(trial["input"])
            limit = 30 if profile == "dispatch" and point is None else 120
            trial["frame_budget"] = limit
            while trial["frames_completed"] < limit:
                if len(trial["hits"]) >= 24:
                    trial["end"] = "probe_stop_budget"
                    break
                result, probe = runner.frame()
                trial["step_calls"] += 1
                if probe is None:
                    trial["frames_completed"] += 1
                    continue
                labels = _capture_hit(runner, probe, result, trial)
                if profile == "dispatch":
                    if "row_destination" in labels:
                        trial["end"] = "row_destination_observed"
                        break
                    if "control_destination" in labels and trial.get("control_is_row") is False:
                        trial["end"] = "control_destination_observed"
                        break
                    if name == "empty_row" and "generic_si_plus_2" in labels:
                        trial["end"] = "input_fallback_observed"
                        break
            else:
                trial["end"] = "observation_window_complete" if trial["hits"] else "no_hit_timeout"
            trial["guest_elapsed_ms"] = runner.rpc("execution.timing")["guest_ticks"] - before_ticks
            trial["screenshot"] = runner.screenshot(name + "-" + profile + ".png")
            trial["after_registers"] = runner.rpc("state.get_registers")
            trial["after_ram_sha256"] = _sha(runner.memory(0, RAM_BYTES))
            trial["keyboard_after"] = runner.rpc("input.keyboard.state")
            trial["mouse_after"] = runner.rpc("input.mouse.state")
            trial["disk_changes_during_trial"] = _file_diff(before_files, _files(game))
            trial["host_ms"] = (time.monotonic() - trial_start) * 1000
            runner.deadline = None
            trial["cleanup"] = runner.cleanup()
            _json(report_path, report)
        runner.deadline = time.monotonic() + 12
        report["final_restore"] = runner.restore(baseline)
        report["final_screenshot"] = runner.screenshot("batch-" + profile + "-restored.png")
        report["completed"] = True
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error),
                           "evidence": getattr(error, "evidence", None),
                           "uncertain_dispatch": runner.uncertain}
        if report["trials"]:
            report["trials"][-1].setdefault("end", "batch_aborted")
        aborted = BatchAborted("Dune batch aborted; inspect " + str(report_path))
        aborted.report_path = str(report_path)
        raise aborted from error
    finally:
        runner.deadline = None
        try:
            report["cleanup"] = runner.cleanup()
        except BaseException as error:
            report["completed"] = False
            report["cleanup"] = {"status": "failed", "error": str(error),
                                  "uncertain_dispatch": runner.uncertain, "owned_ids": sorted(runner.owned)}
        report["host_elapsed_ms"] = (time.monotonic() - started) * 1000
        report["ended_unix"] = time.time()
        _json(report_path, report)
    if not report["completed"]:
        raise BatchAborted("Dune batch cleanup failed; inspect " + str(report_path))
    return report
