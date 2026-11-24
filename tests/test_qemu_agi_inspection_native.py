"""Optional read-only inspection of an explicitly selected AGI producer."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

import pytest

from fdisbull.native_cpu import inspect_native_cpu
from fdisbull.qemu_control import QemuControl


def test_native_agi_cpu_inspection():
    selected = os.environ.get('FDISBULL_QEMU_AGI')
    if not selected:
        pytest.skip('Set FDISBULL_QEMU_AGI to an AGI QEMU executable')
    executable = Path(selected).expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail('FDISBULL_QEMU_AGI must name an executable native candidate')
    with tempfile.TemporaryDirectory(prefix='fdb-agi-inspect-') as directory:
        root = Path(directory)
        program = root / 'program.agi'
        program.write_bytes(b'\0')  # Authored AGI return instruction.
        socket = root / 'qmp.sock'
        command = [str(executable), '-M', 'agi-test', '-accel', 'tcg,thread=single',
                   '-kernel', str(program), '-S', '-display', 'none', '-serial', 'none',
                   '-monitor', 'none', '-nodefaults', '-no-user-config',
                   '-qmp', f'unix:{socket},server=on,wait=off']
        with (root / 'qemu.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log)
            control = None
            try:
                control = QemuControl(socket, process, time.monotonic() + 20)
                result = inspect_native_cpu(control, expected_target='agi', timeout_ms=10000)
                assert result['format'] == 'fdisbull-native-cpu-inventory-2'
                assert result['expected_target'] == 'agi'
                assert result['cpu_source'] == 'query-cpus-fast'
                assert result['target']['arch'] == 'agi'
                assert len(result['cpus']) == 1
                assert result['cpu_paths'] == [result['cpus'][0]['qom-path']]
                assert result['cpu_paths'][0].startswith('/machine/')
                assert result['status']['running'] is False
                assert process.poll() is None
                assert control.call('query-status')['running'] is False
            finally:
                if control is not None:
                    control.close()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            assert process.poll() is not None
