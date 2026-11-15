"""Saved-script admission includes stopped clock preflight and persistence."""
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull.debug_script import execute_script
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_dos_process import QemuDOSProcessSession


@pytest.mark.parametrize('preflight_seconds,artifact_seconds', [
    (0.75, 0.50), (0.0, 1.25),
], ids=['clock-preflight-consumes-script-budget', 'route-artifact-consumes-script-budget'])
def test_source_clock_script_does_not_reset_budget_before_earlier_write(
        monkeypatch, preflight_seconds, artifact_seconds):
    now = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    session = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
    session.run_id = 'run-a'
    session.metadata = dict(backend='qemu-dos', runtime_profile='dos-exec-load-only-v1')
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session._deadline = None
    session.vm = SimpleNamespace(lock=threading.RLock(), gdb=None,
        qmp=SimpleNamespace(operation_deadline=None, socket=True), operation_deadline=None,
        machine_configuration=dict(cpus=1, clock_profile=machine_clock_configuration('virtual', 1)))
    samples, writes = [], []

    def snapshot():
        # Keep the production preflight and machine_trace_operation wrapper.
        # Only the passive observation's elapsed host time is supplied here.
        samples.append(now[0])
        now[0] += preflight_seconds
        return dict(epoch='a' * 32, virtual_clock=dict(native=dict(epoch=1)))

    def artifact(name, kind, data, metadata):
        if kind == 'script':
            now[0] += artifact_seconds
        return dict(artifact='authored-' + kind)

    session._clock_snapshot = snapshot
    session._artifact = artifact
    session.write_registers = lambda registers: writes.append((now[0], registers)) or dict(written=True)
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-registers', registers={'rax': {'expected': 0, 'value': 1}}),
        {'op': 'trace-until', 'until': dict(kind='virtual-time-range', run='run-a',
            epoch='a' * 32, native_epoch=1, start_ns=0, end_ns=1024), 'max_steps': 1},
    ])
    try:
        result = execute_script(session, script, timeout_ms=1000)
    except TimeoutError:
        # Refusing before the script artifact is also a valid admission result.
        result = None
    assert samples == [100.0]
    assert not writes, 'A preceding script write ran after the original host deadline'
    if result is not None:
        assert result['ok'] is False and result['completed_steps'] == 0
        assert result['error']['type'] == 'TimeoutError'
    assert session._deadline is None and session.vm.operation_deadline is None
    assert session.vm.qmp.operation_deadline is None
