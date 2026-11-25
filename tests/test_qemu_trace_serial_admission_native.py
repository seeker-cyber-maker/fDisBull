"""Opt-in native QMP guard for trace admission on a parallel-capable VM.

Set FDISBULL_QEMU_TRACE to the exact trace-enabled QEMU candidate. The VM has
no disk or guest media, starts paused, and exposes one active vCPU with room
for a second CPU so trace admission must reject CF_PARALLEL before capture.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time

import pytest

from fdisbull.qemu_control import QMPCommandError, QemuControl


TRACE_START = "x-fdisbull-trace-start"
EXPECTED_ERROR = "instruction trace requires serial TCG (CF_PARALLEL disabled)"


def test_trace_start_rejects_parallel_capable_vm_without_killing_qemu():
    selected = os.environ.get("FDISBULL_QEMU_TRACE")
    if not selected:
        pytest.skip("Set FDISBULL_QEMU_TRACE to opt into the native QMP admission regression")
    executable = Path(selected).expanduser().resolve(strict=True)
    assert executable.is_file() and os.access(executable, os.X_OK), executable

    with tempfile.TemporaryDirectory(prefix="fdisbull-trace-serial-") as temp:
        root = Path(temp)
        socket_path = root / "qmp.sock"
        process = subprocess.Popen(
            [
                str(executable),
                "-machine", "q35,accel=tcg",
                "-cpu", "max",
                "-smp", "cpus=1,maxcpus=2",
                "-m", "64M",
                "-nodefaults",
                "-no-user-config",
                "-display", "none",
                "-monitor", "none",
                "-serial", "null",
                "-parallel", "none",
                "-nic", "none",
                "-S",
                "-qmp", f"unix:{socket_path},server=on,wait=off",
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        qmp = None
        try:
            qmp = QemuControl(socket_path, process, time.monotonic() + 10)
            commands = {item["name"] for item in qmp.call("query-commands")}
            assert TRACE_START in commands, (
                f"Explicit FDISBULL_QEMU_TRACE candidate lacks {TRACE_START}: {executable}"
            )

            cpus = qmp.call("query-cpus-fast")
            assert isinstance(cpus, list) and len(cpus) == 1, cpus
            before = qmp.call("query-status")
            assert before.get("status") in ("prelaunch", "paused"), before
            assert process.poll() is None

            with pytest.raises(QMPCommandError) as rejected:
                qmp.call(TRACE_START, {"instruction-count": 2})
            assert EXPECTED_ERROR in str(rejected.value), rejected.value

            after = qmp.call("query-status")
            assert after.get("status") == before.get("status"), (before, after)
            assert process.poll() is None, "QEMU exited after rejecting trace admission"
        finally:
            if qmp is not None:
                try:
                    qmp.call("quit", timeout_ms=2000)
                except Exception:
                    pass
                qmp.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
