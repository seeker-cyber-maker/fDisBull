"""Owned QMP harness for the explicitly supplied experimental AGI QEMU binary.

This module never discovers or installs a runtime. Each instance owns one child,
one raw authored program, and QMP pipes (or an explicitly selected Unix socket).
JSON state is read only
while the machine is stopped. Native elapsed time, when exposed by the target,
is separate from ``last_run_wall_ns`` (which includes QMP overhead).
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time


class HarnessError(RuntimeError):
    """The owned native process or its QMP contract failed."""


class QMPError(HarnessError):
    """A command was explicitly rejected by QMP."""


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guest_state(state):
    """Copy the complete authoritative guest object, excluding observation cost.

    Do not enumerate selected scalar fields here: adding a guest field must
    automatically broaden neutrality comparisons instead of being ignored.
    """
    if not isinstance(state, dict) \
            or state.get("schema") != "fdisbull-agi-native-state-1" \
            or not isinstance(state.get("guest"), dict):
        raise HarnessError("Unsupported AGI native state schema")
    return deepcopy(state["guest"])


class QemuAGI:
    """Run ``agi-test`` with raw bytecode and stopped QOM controls.

    Public API: ``configure(mask=..., capacity=..., step_budget=...)``,
    ``restart()``, ``clear_events()``, ``run(step_budget=...)``, ``state()`` and
    ``events()``. ``run`` returns the target's state dictionary after a bounded
    stop; it does not interpret or replace native execution.
    """

    def __init__(self, binary, code, *, timeout=10.0, extra_args=(), evidence_dir=None,
                 transport="stdio"):
        executable = Path(binary).expanduser().resolve()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError("An explicit executable AGI QEMU binary is required")
        if type(code) is not bytes or not 1 <= len(code) <= 65536:
            raise ValueError("Authored raw bytecode must contain 1..65536 bytes")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
                or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        if not isinstance(extra_args, (list, tuple)) \
                or any(not isinstance(arg, str) for arg in extra_args):
            raise ValueError("extra_args must be a sequence of command arguments")
        if transport not in ("stdio", "unix"):
            raise ValueError("transport must be stdio or unix")
        self.timeout = float(timeout)
        self.transport = transport
        self.evidence_dir = None if evidence_dir is None else Path(evidence_dir).resolve()
        if self.evidence_dir is not None and not self.evidence_dir.is_dir():
            raise ValueError("evidence_dir must be an existing caller-owned directory")
        self.failure_evidence = None
        self.binary = executable
        self.binary_sha256 = _sha256_file(executable)
        self.source_sha256 = hashlib.sha256(code).hexdigest()
        # Keep AF_UNIX paths short even when the caller's evidence root is long.
        self._temporary = tempfile.TemporaryDirectory(prefix="fdb-agi-")
        self.directory = Path(self._temporary.name)
        self.program = self.directory / "program.agi"
        self.program.write_bytes(code)
        self.log_path = self.directory / "qemu.log"
        self.socket_path = self.directory / "qmp.sock"
        self.process = None
        self._socket = None
        self._connected = False
        self._log = None
        self._buffer = bytearray()
        self._qmp_events = deque()
        self._sequence = 0
        self.last_run_wall_ns = None
        self.cpu_path = None
        self.command = [
            str(executable), "-M", "agi-test", "-accel", "tcg,thread=single",
            "-kernel", str(self.program), "-S", "-display", "none",
            "-serial", "none", "-monitor", "none", "-nodefaults",
            "-no-user-config", "-qmp",
            ("stdio" if transport == "stdio" else
             f"unix:{self.socket_path},server=on,wait=off"), *extra_args,
        ]
        try:
            self._log = self.log_path.open("wb")
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE if transport == "stdio" else subprocess.DEVNULL,
                stdout=subprocess.PIPE if transport == "stdio" else self._log,
                stderr=self._log, cwd=self.directory, start_new_session=True, bufsize=0,
            )
            self._connect()
            greeting = self._receive(time.monotonic() + self.timeout)
            if not isinstance(greeting.get("QMP"), dict):
                raise HarnessError("Missing QMP greeting")
            self.qmp("qmp_capabilities")
            self._require_stopped()
            cpus = self.qmp("query-cpus-fast")
            if not isinstance(cpus, list) or len(cpus) != 1 \
                    or not isinstance(cpus[0].get("qom-path"), str):
                raise HarnessError("Expected exactly one discoverable AGI CPU")
            self.cpu_path = cpus[0]["qom-path"]
        except BaseException:
            self.close(failed=True)
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.close(failed=exc_type is not None)

    def log_tail(self):
        if not self.log_path.exists():
            return ""
        with self.log_path.open("rb") as stream:
            stream.seek(max(0, self.log_path.stat().st_size - 16384))
            return stream.read().decode("utf-8", "replace")

    def _connect(self):
        if self.transport == "stdio":
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            self._connected = True
            return
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise HarnessError(f"AGI QEMU exited during startup: {self.log_tail()}")
            channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                channel.connect(str(self.socket_path))
                self._socket = channel
                self._connected = True
                return
            except (FileNotFoundError, ConnectionRefusedError):
                channel.close()
                time.sleep(0.01)
            except BaseException:
                channel.close()
                raise
        raise HarnessError(f"AGI QMP startup timed out: {self.log_tail()}")

    def _receive(self, deadline):
        while True:
            if b"\n" in self._buffer:
                line, _, rest = self._buffer.partition(b"\n")
                self._buffer = bytearray(rest)
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise HarnessError("Malformed QMP JSON") from error
                if not isinstance(message, dict):
                    raise HarnessError("QMP message must be an object")
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessError(f"QMP response timed out: {self.log_tail()}")
            try:
                if self.transport == "stdio":
                    fd = self.process.stdout.fileno()
                    ready, _, _ = select.select([fd], [], [], remaining)
                    if not ready:
                        raise TimeoutError("QMP pipe read deadline")
                    chunk = os.read(fd, 65536)
                else:
                    self._socket.settimeout(remaining)
                    chunk = self._socket.recv(65536)
            except (BlockingIOError, InterruptedError):
                continue
            except (socket.timeout, OSError) as error:
                raise HarnessError(f"QMP receive failed: {self.log_tail()}") from error
            if not chunk:
                raise HarnessError(f"QMP closed unexpectedly: {self.log_tail()}")
            self._buffer.extend(chunk)
            if len(self._buffer) > 32 * 1024 * 1024:
                raise HarnessError("QMP response exceeded 32 MiB")

    def _remember_event(self, message):
        if len(self._qmp_events) >= 1024:
            raise HarnessError("Unconsumed QMP event budget exhausted")
        self._qmp_events.append(message)

    def qmp(self, execute, arguments=None):
        """Send one command, retaining asynchronous events until its response."""
        if not self._connected:
            raise HarnessError("QMP session is closed")
        self._sequence += 1
        request = {"execute": execute, "id": self._sequence}
        if arguments is not None:
            request["arguments"] = arguments
        raw = json.dumps(request).encode("utf-8") + b"\n"
        try:
            if self.transport == "stdio":
                fd = self.process.stdin.fileno()
                deadline = time.monotonic() + self.timeout
                while raw:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("QMP pipe write deadline")
                    _, ready, _ = select.select([], [fd], [], remaining)
                    if not ready:
                        raise TimeoutError("QMP pipe write deadline")
                    try:
                        written = os.write(fd, raw)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not written:
                        raise OSError("QMP pipe closed during write")
                    raw = raw[written:]
            else:
                self._socket.settimeout(self.timeout)
                self._socket.sendall(raw)
        except OSError as error:
            raise HarnessError("QMP send failed; command is not replayed") from error
        deadline = time.monotonic() + self.timeout
        while True:
            message = self._receive(deadline)
            if "event" in message:
                self._remember_event(message)
                continue
            if message.get("id") != self._sequence:
                raise HarnessError("QMP response identity differs")
            if "error" in message:
                raise QMPError(f"{execute}: {message['error']}")
            if "return" not in message:
                raise HarnessError("QMP response has no result")
            return message["return"]

    def _require_stopped(self):
        status = self.qmp("query-status")
        if not isinstance(status, dict) or status.get("running") is not False:
            raise HarnessError("AGI state/control operations require a stopped CPU")
        return status

    def get(self, name):
        self._require_stopped()
        return self.qmp("qom-get", {"path": self.cpu_path, "property": name})

    def set(self, name, value):
        self._require_stopped()
        return self.qmp("qom-set", {
            "path": self.cpu_path, "property": name, "value": value,
        })

    def configure(self, *, mask=None, capacity=None, step_budget=None):
        for name, value in (("agi-observation-mask", mask),
                            ("agi-observation-capacity", capacity),
                            ("agi-step-budget", step_budget)):
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError(f"{name} requires a nonnegative integer")
                self.set(name, value)

    def restart(self):
        self.set("agi-restart", True)

    def clear_events(self):
        self.set("agi-observation-clear", True)

    def _json_property(self, name):
        value = self.get(name)
        if not isinstance(value, str):
            raise HarnessError(f"{name} must expose JSON as a string")
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise HarnessError(f"Invalid {name} JSON") from error

    def state(self):
        value = self._json_property("agi-state-json")
        if not isinstance(value, dict):
            raise HarnessError("AGI state must be an object")
        return value

    def events(self):
        value = self._json_property("agi-events-json")
        if not isinstance(value, dict) \
                or value.get("schema") != "fdisbull-agi-native-events-1" \
                or not isinstance(value.get("events"), list):
            raise HarnessError("Unsupported AGI native events schema")
        return value

    def _run_stopped(self, *, step_budget=None):
        """Own one bounded cont/STOP interval without selecting a state payload."""
        self._require_stopped()
        if step_budget is not None:
            self.configure(step_budget=step_budget)
        # A STOP from a preceding invocation cannot complete the next one.
        self._qmp_events.clear()
        start = time.perf_counter_ns()
        self.qmp("cont")
        deadline = time.monotonic() + self.timeout
        status = self.qmp("query-status")
        while status.get("running") is True:
            if any(event.get("event") == "STOP" for event in self._qmp_events):
                self._qmp_events.clear()
                status = self.qmp("query-status")
            else:
                message = self._receive(deadline)
                if "event" not in message:
                    raise HarnessError("Unexpected QMP response while awaiting stop")
                self._remember_event(message)
        self._require_stopped()
        self.last_run_wall_ns = time.perf_counter_ns() - start

    def run(self, *, step_budget=None):
        self._run_stopped(step_budget=step_budget)
        return self.state()

    def close(self, *, failed=False):
        process = self.process
        if process is not None and process.poll() is None:
            if self._connected:
                try:
                    self.qmp("quit")
                except (HarnessError, OSError):
                    pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        self._connected = False
        if self._log is not None:
            self._log.close()
            self._log = None
        if failed and self.evidence_dir is not None and self.failure_evidence is None:
            destination = Path(tempfile.mkdtemp(prefix="agi-failure-", dir=self.evidence_dir))
            self.failure_evidence = destination
            # Explicit -d/-D operation logs are owned by the caller. Bound this
            # diagnostic copy independently so a failure cannot fill evidence.
            with self.log_path.open("rb") as stream:
                log = stream.read(1024 * 1024)
            (destination / "qemu.log").write_bytes(log)
            (destination / "command.json").write_text(json.dumps({
                "command": self.command, "binary_sha256": self.binary_sha256,
                "source_sha256": self.source_sha256,
                "returncode": None if process is None else process.poll(),
                "log_truncated": self.log_path.stat().st_size > len(log),
            }, indent=2) + "\n", encoding="utf-8")
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
