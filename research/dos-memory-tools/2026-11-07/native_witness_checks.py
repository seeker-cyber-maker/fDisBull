"""Bounded input snapshots and positive verdicts for the two DOS experiments.

These checks qualify one declared stop and complete file effects. They do not
establish compatibility, authenticity, timing equivalence, or a general patch
format. They contain no original program bytes and need no native backend.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


MAX_FILE = 2 * 1024 * 1024
MAX_DIRECTORY = 16 * 1024 * 1024
MAX_FILES = 128


def identity(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def require_hash(data, expected, label):
    result = identity(data)
    if result["sha256"] != expected:
        raise ValueError(label + " identity does not match the inspected input")
    return result


def read_file(path, *, limit=MAX_FILE):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular non-symlink input: " + path.name)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Input exceeds the byte budget: " + path.name)
    return data


def snapshot_directory(directory):
    """Read a flat, bounded directory once; reject ignored or ambiguous entries."""
    files, names, total = {}, set(), 0
    for path in sorted(Path(directory).iterdir()):
        if len(files) >= MAX_FILES:
            raise ValueError("Directory exceeds the file-count budget")
        name = path.name.casefold()
        if name in names:
            raise ValueError("Ambiguous DOS filename: " + path.name)
        names.add(name)
        data = read_file(path)
        total += len(data)
        if total > MAX_DIRECTORY:
            raise ValueError("Directory exceeds the aggregate byte budget")
        files[path.name] = data
    return files


def manifest(files):
    return {name: identity(data) for name, data in sorted(files.items())}


def new_private_output(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("Private output must not have symlink ancestry")
        if (parent / ".git").exists() or parent.name == ".git":
            raise ValueError("Private output must be outside a Git checkout")
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    return path


def file_effects(before, expected, observed):
    """Compare complete byte snapshots, including files outside the patch target."""
    if not expected:
        raise ValueError("Expected output inventory must not be empty")
    missing = sorted(expected.keys() - observed.keys())
    unexpected = sorted(observed.keys() - expected.keys())
    differing = sorted(name for name in expected.keys() & observed.keys()
                       if expected[name] != observed[name])
    changed = sorted(name for name in before.keys() | observed.keys()
                     if before.get(name) != observed.get(name))
    return {"all_expected_file_bytes_match": not (missing or unexpected or differing),
            "missing_files": missing, "unexpected_files": unexpected,
            "different_files": differing, "changed_files": changed,
            "expected_files": manifest(expected), "observed_files": manifest(observed)}


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an address/register value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("Missing address/register value")


def _segmented(address):
    if not isinstance(address, dict) or address.get("space") != "segmented":
        raise ValueError("Expected a segmented runtime address")
    segment, offset = _number(address.get("segment")), _number(address.get("offset"))
    if not 0 <= segment <= 0xFFFF or not 0 <= offset <= 0xFFFF:
        raise ValueError("Runtime CS:IP is outside the real-mode witness contract")
    return segment, offset


def verify_completion(armed, completed, registers, *, run_id, offset):
    """Require the armed stop, its relocated CS:IP, and a normal child exit.

    The child's AL is recorded but never interpreted as a success code. The
    separate complete-file comparison determines the observed patch effect.
    Missing fields fail rather than borrowing an observation from another run.
    """
    project_address = 0x10000 + offset
    runtime = _segmented(armed.get("address"))
    breakpoint_id, session_id = armed.get("breakpoint_id"), armed.get("session_id")
    if (not isinstance(breakpoint_id, str) or not breakpoint_id
            or not isinstance(session_id, str) or not session_id
            or not isinstance(run_id, str) or not run_id
            or armed.get("run") != run_id or completed.get("run") != run_id):
        raise ValueError("Completion identity does not match the armed run/session")
    if (armed.get("kind") != "execution" or armed.get("bytes_verified") is not True
            or _number(armed.get("project_address")) != project_address
            or _number(armed.get("project_cs")) != 0x1000 or runtime[1] != offset):
        raise ValueError("Completion breakpoint is not the verified authored endpoint")
    if completed.get("outcome") != "breakpoint" or completed.get("timed_out") is not False:
        raise ValueError("Execution did not complete at a breakpoint within budget")
    session = completed.get("session", {})
    reason = session.get("stop_reason", {})
    if (session.get("session_id") != session_id or session.get("state") != "stopped"
            or reason.get("kind") != "breakpoint" or reason.get("breakpoint_id") != breakpoint_id
            or _segmented(reason.get("address")) != runtime
            or _number(reason.get("project_address")) != project_address
            or reason.get("cpu_mode") != "real"):
        raise ValueError("Stopped execution is not the exact armed completion breakpoint")
    stop = completed.get("stop", {})
    if (stop.get("trigger") != "breakpoint" or stop.get("native_kind") != "breakpoint"
            or _segmented(stop.get("causing_instruction")) != runtime
            or _segmented(stop.get("resume_pc")) != runtime
            or stop.get("registers_stage") != "before-instruction"
            or stop.get("instruction_completed") is not False or stop.get("cpu_mode") != "real"):
        raise ValueError("Native stop does not identify the authored completion instruction")
    cs = _number(registers.get("segments", {}).get("cs"))
    ip = _number(registers.get("instruction_pointer"))
    if (registers.get("session_id") != session_id or (cs, ip) != runtime
            or registers.get("cpu_mode") != "real"
            or _number(registers.get("project_address")) != project_address):
        raise ValueError("Final registers do not match the exact completion CS:IP")
    for field, expected in (("cs", cs), ("ip", ip)):
        if field in registers and _number(registers[field]) != expected:
            raise ValueError("Final register aliases disagree")
    ax = _number(registers.get("general", {}).get("eax")) & 0xFFFF
    if ax >> 8:
        raise ValueError("Child did not report normal DOS termination")
    return {"exact_completion_breakpoint_verified": True, "run_id": run_id,
            "breakpoint_id": breakpoint_id, "session_id": session_id,
            "runtime_cs": cs, "runtime_ip": ip, "project_address": project_address,
            "dos_ax": ax, "dos_termination_type_ah": ax >> 8, "dos_return_code_al": ax & 255,
            "exit_al_is_not_a_success_test": True}
