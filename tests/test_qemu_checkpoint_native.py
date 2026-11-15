"""Real QEMU internal-snapshot witness; does not qualify public save-state.

The image and program are authored here. The caller selects both executables;
the test starts two owned QEMU processes and never uses production launch code.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest

from fdisbull.gdb_rpc import GDBRemote
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_checkpoint import snapshot_job
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_machine import MachineContext
from fdisbull.qemu_transport import PipeChannel, create_fifo_pair, open_fifo_pair
from fdisbull.project import Project
from support.qemu_dos_fixture import boot_fixture


def _executables():
    selected = []
    required = os.environ.get('FDISBULL_REQUIRE_QEMU_DOS') == '1'
    for key in ('FDISBULL_QEMU_DOS', 'FDISBULL_QEMU_IMG'):
        value = os.environ.get(key)
        if not value:
            if required:
                pytest.fail('Missing required ' + key)
            pytest.skip('Supply ' + key + ' for real native checkpoint witness')
        path = Path(value).expanduser().resolve(strict=True)
        assert path.is_file() and os.access(path, os.X_OK), key
        selected.append(str(path))
    return selected


def _boot_image():
    image, _ = boot_fixture()
    image = bytearray(image)
    # The first stage writes sector 2 via BIOS, sets a RAM word and AX, and
    # stops at A. Continuing performs a second distinct write and stops at B.
    code = bytearray.fromhex(
        'faea0600c007'       # CLI; far jump 07c0:0006
        '31c08ed88ec08ed0'   # zero DS/ES/SS
        'bc007cfb'           # stack 0000:7c00; STI
    )
    def write_sector(marker):
        code.extend(bytes.fromhex('c6060006') + bytes([marker]))
        code.extend(bytes.fromhex('b80103bb0006b9020030f6cd13'))
        # On BIOS failure park outside the success breakpoints.
        code.extend(bytes.fromhex('7302ebfe'))
    write_sector(0x41)
    code.extend(bytes.fromhex('c70600501111b85713'))
    stop_a = 0x7c00 + len(code)
    code.extend(b'\x90')
    write_sector(0x42)
    code.extend(bytes.fromhex('c70600502222b86824'))
    stop_b = 0x7c00 + len(code)
    code.extend(bytes.fromhex('ebfe'))
    assert len(code) < 510
    image[:512] = bytes(code).ljust(510, b'\0') + b'\x55\xaa'
    return bytes(image), stop_a, stop_b


class _Machine:
    def __init__(self, executable, image, directory):
        self.lock = threading.RLock()
        self.qmp = self.gdb = self.process = None
        self.closed = False
        self.transport = 'pipe'
        self.machine_stopped = True
        self.machine_configuration = {'cpus': 1}
        self.channels = []
        gdb_path = directory / 'gdb'
        create_fifo_pair(gdb_path)
        command = [executable, '-machine', 'pc', '-cpu', '486', '-accel', 'tcg',
                   '-smp', '1', '-m', '32M', '-nic', 'none', '-display', 'none',
                   '-monitor', 'none', '-serial', 'none', '-no-reboot', '-S',
                   '-blockdev', 'driver=file,filename=' + str(image) + ',node-name=fdbfile',
                   '-blockdev', 'driver=qcow2,file=fdbfile,node-name=disk0',
                   '-device', 'ide-hd,drive=disk0', '-boot', 'order=c',
                   '-qmp', 'stdio', '-chardev', 'pipe,path=' + str(gdb_path) + ',id=gdb',
                   '-gdb', 'chardev:gdb']
        firmware = os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE')
        if firmware:
            command.extend(['-L', firmware])
        self.gdb_path = gdb_path
        self.log = (directory / 'qemu.log').open('wb')
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.log, bufsize=0)
            channel = PipeChannel(self.process.stdout, self.process.stdin, process=self.process)
            self.channels.append(channel)
            self.qmp = QemuControl(None, self.process, time.monotonic() + 30, channel=channel)
            self.qmp_commands = frozenset(item['name'] for item in self.qmp.call('query-commands'))
        except BaseException:
            self.close()
            raise

    def debugger(self):
        if self.gdb is None:
            channel = open_fifo_pair(self.gdb_path, self.process)
            self.channels.append(channel)
            self.gdb = GDBRemote(None, self.process, time.monotonic() + 30, channel=channel)
        return self.gdb

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.gdb is not None:
            self.gdb.close()
        if self.qmp is not None:
            self.qmp.close()
        for channel in self.channels:
            channel.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log.close()


def _run_to(context, address):
    point = context.breakpoint(address)
    result = context.run(timeout_ms=30000)
    assert result['outcome'] == 'breakpoint', result
    context.delete_breakpoint(point['breakpoint_id'])


def _disk_byte(qemu_img, source, target):
    subprocess.run([qemu_img, 'convert', '-f', 'qcow2', '-O', 'raw', str(source), str(target)],
                   check=True, timeout=60)
    with target.open('rb') as stream:
        stream.seek(512)
        return stream.read(1)


def _accumulator(registers):
    values = registers['registers']
    return int(values['rax' if 'rax' in values else 'eax'], 16) & 0xffff


def test_native_snapshot_cold_restore_cpu_ram_and_guest_disk(tmp_path):
    executable, qemu_img = _executables()
    source_bytes, stop_a, stop_b = _boot_image()
    source = tmp_path / 'authored.raw'
    source.write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    disk = tmp_path / 'owned.qcow2'
    subprocess.run([qemu_img, 'convert', '-f', 'raw', '-O', 'qcow2', str(source), str(disk)],
                   check=True, timeout=60)
    first_dir = tmp_path / 'first'
    first_dir.mkdir()
    copy = tmp_path / 'cold.qcow2'
    machine = _Machine(executable, disk, first_dir)
    try:
        context = MachineContext(machine)
        _run_to(context, stop_a)
        before = context.registers()
        assert context.memory(0x5000, length=2)['hex'] == '1111'
        assert _accumulator(before) == 0x1357
        snapshot_job(machine, 'save', tag='saved', vmstate='disk0', devices=['disk0'])
        assert machine.qmp.call('query-status')['running'] is False
        # Copy while QEMU still owns the stopped image, matching the intended
        # production capture boundary. The fresh process below must prove that
        # the copied on-disk image contains a usable snapshot.
        shutil.copyfile(disk, copy)
        assert machine.qmp.call('query-status')['running'] is False
        _run_to(context, stop_b)
        assert context.memory(0x5000, length=2)['hex'] == '2222'
        assert _accumulator(context.registers()) == 0x2468
    finally:
        machine.close()
    assert _disk_byte(qemu_img, disk, tmp_path / 'after-b.raw') == b'B'
    second_dir = tmp_path / 'second'
    second_dir.mkdir()
    restored = _Machine(executable, copy, second_dir)
    try:
        snapshot_job(restored, 'load', tag='saved', vmstate='disk0', devices=['disk0'])
        assert restored.qmp.call('query-status')['running'] is False
        context = MachineContext(restored)
        after = context.registers()
        assert context.memory(0x5000, length=2)['hex'] == '1111'
        assert _accumulator(after) == 0x1357
        assert after['instruction_pointer'] == before['instruction_pointer']
        assert after['registers']['cs'] == before['registers']['cs']
    finally:
        restored.close()
    assert _disk_byte(qemu_img, copy, tmp_path / 'after-restore.raw') == b'A'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha


def test_native_pending_input_refuses_before_snapshot_dispatch(tmp_path):
    executable, qemu_img = _executables()
    source_bytes, stop_a, _ = _boot_image()
    source = tmp_path / 'authored.raw'
    source.write_bytes(source_bytes)
    disk = tmp_path / 'owned.qcow2'
    subprocess.run([qemu_img, 'convert', '-f', 'raw', '-O', 'qcow2', str(source), str(disk)],
                   check=True, timeout=60)
    directory = tmp_path / 'machine'
    directory.mkdir()
    machine = _Machine(executable, disk, directory)
    try:
        context = MachineContext(machine)
        _run_to(context, stop_a)
        context.mouse_move_relative(1, 0)
        with pytest.raises(ValueError, match='released machine input'):
            snapshot_job(machine, 'save', tag='refused', vmstate='disk0', devices=['disk0'])
        assert not machine.closed
        assert machine.qmp.call('query-status')['running'] is False
        assert not any(job.get('type') == 'snapshot-save' for job in machine.qmp.call('query-jobs'))
    finally:
        machine.close()


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_public_raw_checkpoint_survives_project_and_machine_restart(tmp_path, backend):
    executable, qemu_img = _executables()
    firmware = os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE')
    if not firmware:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS') == '1':
            pytest.fail('FDISBULL_QEMU_DOS_FIRMWARE is required for checkpoint identity')
        pytest.skip('Supply explicitly pinned firmware for public checkpoint acceptance')
    source_bytes, stop_a, stop_b = _boot_image()
    source = tmp_path / 'authored.raw'
    source.write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    project_path = tmp_path / 'checkpoint.fdb'

    def launch(project):
        return project.debugger(executable, tmp_path, backend=backend, qemu_transport='pipe',
                                qemu_firmware=firmware, qemu_checkpoint_tool=qemu_img)

    with Project.create(project_path, source, arch='x86', bits=32,
                        base=0x7c00, entry=0x7c00) as project:
        with launch(project) as debug:
            assert debug.capabilities['save_states'] is True
            _run_to(debug, stop_a)
            before = debug.registers()
            memory = debug.memory_snapshot(0x5000, length=2, space='physical')['artifact']
            search = project.memory_search_start(memory, mode='equal', value=0x1111, width=2)['artifact']
            plan = project.memory_edit_plan(search, offset=0, value=0x3333)['artifact']
            rule = project.memory_rule_create(search, offset=0, value=0x4444)['artifact']
            saved = debug.save_state('raw.qcow2')
            assert saved['metadata']['format'] == 'fdisbull-qemu-raw-qcow2-v1'
            _run_to(debug, stop_b)
            assert debug.memory(0x5000, length=2)['hex'] == '2222'
            assert _accumulator(debug.registers()) == 0x2468
            debug.load_state(saved['artifact'])
            assert debug.memory(0x5000, length=2)['hex'] == '1111'
            with pytest.raises(ValueError, match='context changed'):
                debug.memory_apply(plan)
            tick = debug.memory_rule_tick(rule)
            assert not tick['applied']
            assert debug.memory(0x5000, length=2)['hex'] == '1111'
    with Project(project_path) as project:
        info = project.debug_state_info(saved['artifact'])
        assert info['sha256'] == saved['sha256']
        assert info['metadata']['backend'] == backend
        with launch(project) as debug:
            old_process = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert old_process.poll() is not None
            assert restored['checkpoint_epoch'] == 1
            assert restored['source_binding_restored'] is False
            assert debug.status()['state'] == 'stopped'
            assert debug.memory(0x5000, length=2)['hex'] == '1111'
            actual = debug.registers()
            assert _accumulator(actual) == 0x1357
            assert actual['instruction_pointer'] == before['instruction_pointer']
            # Disk contents are read after closing the owned QEMU image.
            restored_disk = tmp_path / 'public-restored.qcow2'
            shutil.copyfile(debug.vm.checkpoint_disk, restored_disk)
            row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (saved['artifact'],)).fetchone()
            invalid_metadata = dict(saved['metadata'], tag='missing-snapshot')
            invalid = project._debug_artifact(debug.run_id, 'missing.qcow2', 'state',
                                              bytes(row['data']), invalid_metadata)
            owned_process = debug.vm.process
            with pytest.raises(DebuggerError, match='Snapshot job failed'):
                debug.load_state(invalid['artifact'])
            assert debug.closed
            assert owned_process.poll() is not None
    assert _disk_byte(qemu_img, restored_disk, tmp_path / 'public-restored.raw') == b'A'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
