"""NEW S16 qualification, never a replay of the lost 1ecf4b5 test revision.

No native default is selected. An independently reviewed JSON admission must
pin both exact producers, every tool/firmware/host input, and a private
output tree. Run this file with -x under a finite outer supervisor. Missing
admission skips the opt-in lane, or fails when its REQUIRE selector is set.
The 600-second work limit is separate from bounded owned-process cleanup.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import wave

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_clock import clock_timer_stop_is_ordinary
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.native_cold_process import run_owned_cold, terminate_as_exception
from support.qemu_sb16_s16_recovery_fixture import (
    BLOCK_BYTES, BLOCKS, ENCODINGS, FRONTIERS, FUTURE_NS, GEOMETRIES,
    POSITIVE_CASES, PROFILE, REPORT_SIZE, RING_BYTES, UNSAFE_CASES, VoiceCase,
    block_pcm, build_fixture, expected_dma_progress, parse_report,
)
from test_qemu_clock_budget_native import budget_receipt
from test_qemu_dos_process_native import com_address, read_bytes


ADMISSION_FORMAT = 'fdisbull-s16-recovery-native-admission-20261122-2'
NATIVE_BOUNDS = dict(cases=32, owners=91, work_seconds=600,
    case_seconds=45, cold_seconds=30, cleanup_grace_seconds=2,
    post_entry_guest_ns=2_000_000_000, future_ns=FUTURE_NS,
    output_bytes=512 * 1024 * 1024, checkpoint_bytes=16 * 1024 * 1024)
LOG_MAX_BYTES = 256 * 1024
OWNED_FILES = (
    'tests/support/qemu_sb16_s16_recovery_fixture.py',
    'tests/test_qemu_sb16_s16_recovery_fixture.py',
    'tests/test_qemu_sb16_s16_recovery_native.py',
    'tests/support/native_cold_process.py', 'tests/test_native_cold_process.py',
)
LEGACY_CASES = tuple(VoiceCase(f'legacy-c{channels}-fifo{int(fifo)}',
    channels=channels, fifo=fifo) for channels in (1, 2) for fifo in (False, True))
CORRUPTIONS = {
    'unsupported-width': ('sw_bits', 24, 'SB16 checkpoint software voice state is invalid'),
    'out-of-range-rate': ('sw_freq', 0, 'SB16 checkpoint software voice state is invalid'),
    'zero-resampler-increment': ('rate_increment', 0, 'SB16 checkpoint resampler phase is invalid'),
    'destination-signedness': ('sw_signed', 0, 'SB16 checkpoint recreated graph or software format differs'),
}
CORE2_FIELDS = (
    'magic', 'version', 'sample_size', 'byte_order', 'has_hw', 'has_sw', 'has_capture',
    'hw_size', 'hw_pos', 'hw_timestamp', 'hw_enabled', 'hw_pending_disable',
    'emul_size', 'emul_pos', 'emul_pending', 'sw_freq', 'sw_channels', 'sw_bits',
    'sw_signed', 'sw_swap', 'sw_total', 'sw_active', 'sw_empty', 'sw_size', 'sw_pos',
    'sw_mute', 'sw_l', 'sw_r', 'rate_opos', 'rate_increment', 'rate_ipos',
    'rate_last_l', 'rate_last_r', 'cap_size', 'cap_pos', 'cap_timestamp', 'cap_enabled',
    'csw_total', 'csw_active', 'csw_empty', 'csw_mute', 'csw_l', 'csw_r',
)


def stationary_clock(before, after):
    """Keep every native field; only observation metadata may advance."""
    for key in ('sequence', 'host_monotonic_ns'):
        assert type(before[key]) is type(after[key]) is int
        assert 0 < before[key] < after[key], (key, before, after)
    left, right = deepcopy(before), deepcopy(after)
    for value in (left, right):
        value.pop('sequence')
        value.pop('host_monotonic_ns')
    assert left == right, ('paused clock changed', before, after)


def comparable_clock(value):
    """Explicit restore identities only; no native timing/status field is lost.

    Native stop classes are separately checked as stopped before removing the
    two documented debugger-vs-load status labels. The complete originals stay
    in every receipt. Epochs and random budget tokens are fresh ownership.
    """
    value = deepcopy(value)
    for name in ('epoch', 'run', 'sequence', 'host_monotonic_ns'):
        assert name in value
        value.pop(name)
    native = value['virtual_clock']['native']
    assert value['session'] == {'state': 'stopped', 'scope': 'all machine vCPUs'}
    assert value['native_state']['running'] is native['running'] is False
    assert native['pending-stop'] is False
    assert native['status'] in ('prelaunch', 'paused', 'debug')
    assert value['native_state']['status'] in ('prelaunch', 'paused', 'debug')
    value['native_state'].pop('status')
    native.pop('status')
    assert type(native['epoch']) is int and native['epoch'] > 0
    native.pop('epoch')
    if 'budget-token' in native:
        assert isinstance(native['budget-token'], str) and native['budget-token']
        native.pop('budget-token')
    return value


def corrupt_core2(encoded, damage):
    """Change exactly one documented uint64; never use an inferred offset."""
    if damage not in CORRUPTIONS or not isinstance(encoded, str) or len(encoded) > 8 * 1024 * 1024:
        raise ValueError('Invalid explicit core2 corruption')
    raw = bytearray(base64.b64decode(encoded, validate=True))
    if base64.b64encode(raw).decode('ascii') != encoded or len(raw) < 8 * len(CORE2_FIELDS):
        raise ValueError('Core2 header is not complete/canonical')
    magic = 0x4644424155443032
    orders = [order for order in ('<', '>') if struct.unpack_from(order+'Q', raw)[0] == magic]
    if len(orders) != 1:
        raise ValueError('Expected exact SB16 core2 magic')
    order = orders[0]
    words = struct.unpack_from(order + str(len(CORE2_FIELDS)) + 'Q', raw)
    header = dict(zip(CORE2_FIELDS, words, strict=True))
    if (header['version'] != 2 or header['byte_order'] != (1234 if order == '<' else 4321)
            or header['has_sw'] != 1 or header['sw_bits'] != 16 or header['sw_signed'] != 1):
        raise ValueError('Expected a complete signed S16 core2 voice')
    field, changed, _ = CORRUPTIONS[damage]
    struct.pack_into(order+'Q', raw, 8 * CORE2_FIELDS.index(field), changed)
    return base64.b64encode(raw).decode('ascii')


def _json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


@contextmanager
def preserved_context(context, report, label):
    """Use the public context protocol without replacing a body's failure."""
    value = context.__enter__()
    try:
        yield value
    except BaseException as primary:
        try:
            context.__exit__(type(primary), primary, primary.__traceback__)
        except BaseException as cleanup:
            fault = dict(context=label, error=type(cleanup).__name__+': '+str(cleanup))
            report.setdefault('context_cleanup_faults', []).append(fault)
            primary.add_note(label+' cleanup failed: '+fault['error'])
        raise
    else:
        try:
            context.__exit__(None, None, None)
        except BaseException as cleanup:
            fault = dict(context=label, error=type(cleanup).__name__+': '+str(cleanup))
            report.setdefault('context_cleanup_faults', []).append(fault)
            raise


def _copy_owned_log(source, target):
    """Read at most cap+1, retaining a capped prefix without a false full hash."""
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Owned emulator log is not a regular file')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Owned emulator log identity changed while opening')
        data = stream.read(LOG_MAX_BYTES+1)
        after = os.fstat(stream.fileno())
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if identity(before) != identity(after) or identity(source.lstat()) != identity(after):
        raise ValueError('Owned emulator log changed during its stopped copy')
    retained = data[:LOG_MAX_BYTES]
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(retained)
    copied = digest(target)
    if copied != hashlib.sha256(retained).hexdigest():
        raise ValueError('Retained emulator log did not match its copied bytes')
    complete = len(data) == before.st_size and len(data) <= LOG_MAX_BYTES
    return dict(status='complete' if complete else 'truncated', source_bytes=before.st_size,
        retained_bytes=len(retained), retained_sha256=copied,
        full_sha256=copied if complete else None, cap_bytes=LOG_MAX_BYTES,
        path=str(target), complete=complete)


def preserve_owner_logs(temporary, destination, process, owner_receipt):
    """Wrap only this owned TemporaryDirectory; cleanup is always attempted."""
    original_cleanup = temporary.cleanup
    source_root, destination = Path(temporary.name), Path(destination)
    invoked = False
    def cleanup():
        nonlocal invoked
        if invoked:
            return original_cleanup()
        invoked = True
        primary = sys.exception()
        first = None
        receipt = dict(format='fdisbull-s16-recovery-owner-logs-1',
            per_log_cap_bytes=LOG_MAX_BYTES, process_reaped=None,
            complete=False, cleanup_attempted=False, cleanup_succeeded=False, files={}, errors=[])
        owner_receipt['native_logs'] = receipt
        def failure(error, stage):
            nonlocal first
            if first is None:
                first = error
            receipt['errors'].append(dict(stage=stage, error=type(error).__name__+': '+str(error)))
        try:
            try:
                receipt['process_reaped'] = process.poll() is not None
                if not receipt['process_reaped']:
                    raise RuntimeError('Emulator owner was not reaped before log preservation')
                destination.mkdir(mode=0o700, parents=True, exist_ok=False)
            except BaseException as error:
                failure(error, 'admission')
            if not receipt['errors']:
                for name in ('qemu.log', 'boot.log'):
                    try:
                        result = _copy_owned_log(source_root/name, destination/name)
                        receipt['files'][name] = result
                        if not result['complete']:
                            failure(ValueError('Emulator log exceeded the 256KiB retention cap: '+name), name)
                    except FileNotFoundError as error:
                        receipt['files'][name] = dict(status='missing', complete=False,
                            full_sha256=None, retained_bytes=0)
                        failure(error, name)
                    except BaseException as error:
                        receipt['files'][name] = dict(status='error', complete=False,
                            full_sha256=None, error=type(error).__name__+': '+str(error))
                        failure(error, name)
        finally:
            receipt['cleanup_attempted'] = True
            try:
                original_cleanup()
                receipt['cleanup_succeeded'] = True
            except BaseException as error:
                failure(error, 'temporary-cleanup')
        receipt['complete'] = not receipt['errors'] and len(receipt['files']) == 2
        if first is not None:
            first.log_retention_receipt = receipt
            if primary is not None:
                primary.add_note('Emulator log preservation/cleanup failed: '+repr(receipt['errors']))
                primary.log_retention_receipt = receipt
            else:
                raise first
    temporary.cleanup = cleanup


def _usage(root):
    allocated = logical = 0
    for path in (root, *root.rglob('*')):
        info = path.lstat()
        allocated += info.st_blocks * 512
        if stat.S_ISREG(info.st_mode):
            logical += info.st_size
        elif stat.S_ISLNK(info.st_mode):
            assert path.resolve().is_relative_to(root), 'Output link escaped counted tree'
        else:
            assert (stat.S_ISDIR(info.st_mode) or stat.S_ISFIFO(info.st_mode)
                    or stat.S_ISSOCK(info.st_mode)), 'Unexpected special output file'
    return dict(allocated=allocated, logical=logical)


class Runtime:
    def __init__(self, config_path, expected_sha):
        self.config_path = Path(config_path).resolve(strict=True)
        assert digest(self.config_path) == expected_sha, 'Admission bytes changed'
        self.config_sha = expected_sha
        self.config = json.loads(self.config_path.read_text())
        assert self.config['format'] == ADMISSION_FORMAT
        assert self.config['limits'] == NATIVE_BOUNDS, 'Bounds are not caller overrides'
        self.root = Path(self.config['host_root']).resolve(strict=True)
        assert Path(__file__).resolve() == self.root/'tests/test_qemu_sb16_s16_recovery_native.py'
        assert Path(sys.modules[Project.__module__].__file__).resolve() == self.root/'src/fdisbull/project.py'
        self.output = Path(self.config['output_root']).resolve(strict=True)
        assert not self.output.is_relative_to(self.root)
        self.check_output_destination()
        assert not any((parent/'.git').exists() for parent in (self.output, *self.output.parents))
        self.store = self.output/'target-store'
        assert os.environ.get('FDISBULL_TARGET_STORE') == str(self.store)
        assert Path(tempfile.gettempdir()).resolve().is_relative_to(self.output)
        self.start = time.monotonic()
        self.deadline = self.start + NATIVE_BOUNDS['work_seconds']
        self.owners = 0
        self.completed = []
        with tempfile.TemporaryFile(dir=self.output) as probe:
            marker = b'fDisBull native S16 recovery destination'
            probe.write(marker)
            probe.flush()
            os.fsync(probe.fileno())
            probe.seek(0)
            assert probe.read() == marker, 'Private output destination failed write readback'
        self.verify_inputs()
        self.resources()

    def verify_inputs(self):
        assert digest(self.config_path) == self.config_sha
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.root,
            capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        assert head == self.config['host_head'] and re.fullmatch('[0-9a-f]{40}', head)
        files = self.config['host_files']
        assert isinstance(files, dict) and set(OWNED_FILES) <= set(files) and len(files) <= 5000
        actual_python = {str(path.relative_to(self.root)) for directory in ('src/fdisbull', 'tests')
                         for path in (self.root/directory).rglob('*.py')}
        assert actual_python <= set(files), 'Admission must pin the product Python closure'
        for name, expected in files.items():
            path = (self.root/name).resolve(strict=True)
            assert path.is_relative_to(self.root) and digest(path) == expected, name
        for name, item in self.config['tools'].items():
            path = Path(item['path']).absolute()
            assert path.is_file() and os.access(path, os.X_OK) and digest(path) == item['sha256'], name
            if name in ('candidate', 'legacy', 'qemu_img'):
                assert digest(item['image_path']) == item['image_sha256'], name
        assert set(self.config['tools']) == {'candidate', 'legacy', 'qemu_img', 'nasm', 'mcopy', 'python'}
        assert Path(self.config['tools']['python']['path']).absolute() == Path(sys.executable).absolute()
        assert self.config['tools']['candidate']['image_sha256'] != self.config['tools']['legacy']['image_sha256']
        boot = self.config['boot_image']
        assert boot['sha256'] == '552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc'
        assert digest(boot['path']) == boot['sha256']
        firmware = self.config['firmware']
        root = Path(firmware['root']).resolve(strict=True)
        actual = {str(path.relative_to(root)): digest(path) for path in root.rglob('*') if path.is_file()}
        assert actual == firmware['files'] and actual

    def check_output_destination(self):
        info = self.output.lstat()
        assert stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o077, 'Private output must be mode0700'
        assert self.config['output_identity'] == dict(device=info.st_dev, inode=info.st_ino), (
            'Private output directory or backing volume identity changed', str(self.output))

    def resources(self):
        assert time.monotonic() < self.deadline, 'Aggregate native work deadline expired'
        self.check_output_destination()
        usage = _usage(self.output)
        assert max(usage.values()) <= NATIVE_BOUNDS['output_bytes'], usage
        return usage

    def project(self, project):
        assert project.db.store.root.resolve() == self.store.resolve(), 'TargetStore escaped owned output'
        assert os.environ.get('FDISBULL_TARGET_STORE') == str(self.store)
        self.resources()


@pytest.fixture(scope='module')
def native_runtime(request):
    selected = os.environ.get('FDISBULL_QEMU_S16_RECOVERY_CONFIG')
    expected = os.environ.get('FDISBULL_QEMU_S16_RECOVERY_CONFIG_SHA256')
    if not selected or not expected:
        message = 'Explicit reviewed S16 recovery admission and its SHA256 are required'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_S16_RECOVERY') == '1':
            pytest.fail(message)
        pytest.skip(message)
    assert request.config.option.maxfail == 1, 'Native matrix requires first-failure stop (-x)'
    assert not getattr(request.config.option, 'numprocesses', None), 'Native owners must be sequential'
    runtime = Runtime(selected, expected)
    previous_handler = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, terminate_as_exception)
    try:
        yield runtime
    finally:
        try:
            runtime.verify_inputs()
            _json(runtime.output/'matrix-postflight.json', dict(format=PROFILE,
                owners_admitted_or_reserved=runtime.owners, completed=runtime.completed,
                usage=runtime.resources()))
            runtime.resources()
        finally:
            signal.signal(signal.SIGTERM, previous_handler)


class CaseRun:
    def __init__(self, runtime, directory, case, owner_limit):
        self.runtime, self.directory, self.case = runtime, Path(directory).resolve(), case.validate()
        assert self.directory.is_relative_to(runtime.output)
        self.deadline = min(runtime.deadline, time.monotonic()+NATIVE_BOUNDS['case_seconds'])
        self.owner_limit, self.machines, self.processes, self.owner_rows = owner_limit, [], [], []
        self.report = dict(format=PROFILE, new_authorship=True, case=case.record(), passed=False,
            stops=[], owners=self.owner_rows, no_host_guest_memory_or_register_writes=True)
        self.path = self.directory/'native-s16-recovery.json'
        self.disk = prepare_dos_baseline(runtime.config['boot_image']['path'],
            self.directory/'boot.img', runtime.config['tools']['mcopy']['path'],
            config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
        self.code, self.offsets = build_fixture(self.directory,
            runtime.config['tools']['nasm']['path'], case)
        self.source = self.directory/'S16REC.COM'
        self.source.write_bytes(self.code)
        self.db = self.directory/'recovery.fdb'
        self.report.update(source_sha256=digest(self.source), disk_sha256=self.disk['prepared_sha256'],
            offsets=self.offsets, original_boot_sha256=self.disk['source_sha256'])
        _json(self.path, self.report)

    def remaining(self, ceiling=15000):
        self.runtime.resources()
        value = int((self.deadline-time.monotonic())*1000)
        assert value > 0, 'S16 case deadline expired'
        return min(value, ceiling)

    def verify_files(self):
        assert self.source.read_bytes() == self.code
        assert digest(self.disk['image']) == self.disk['prepared_sha256']
        assert digest(self.runtime.config['boot_image']['path']) == self.disk['source_sha256']

    @contextmanager
    def owners(self, producer='candidate'):
        """Hook the actual constructor, including public replacement owners."""
        from fdisbull.qemu_machine import QemuMachine
        original = QemuMachine.__init__
        def construct(machine, *args, **kwargs):
            self.remaining()
            assert len(self.processes) < self.owner_limit, 'Case owner count exhausted before spawn'
            assert self.runtime.owners < NATIVE_BOUNDS['owners'], 'Aggregate owner count exhausted'
            prior = kwargs.get('on_spawn')
            def spawned(process):
                if not any(owned is process for owned in self.processes):
                    self.processes.append(process)
                    self.machines.append(machine)
                    self.runtime.owners += 1
                    self.owner_rows.append(dict(pid=process.pid, spawn_owned=True, admitted=False, reaped=False,
                        producer=producer, image_sha256=self.runtime.config['tools'][producer]['image_sha256']))
                    preserve_owner_logs(machine.temporary,
                        self.directory/'owner-logs'/self.path.stem/f'owner-{len(self.processes):02d}',
                        process, self.owner_rows[-1])
                    _json(self.path, self.report)
                if prior is not None:
                    prior(process)
            kwargs['on_spawn'] = spawned
            try:
                original(machine, *args, **kwargs)
                expected = self.runtime.config['tools'][producer]
                assert machine.inputs['qemu']['sha256'] == expected['sha256']
                assert machine.inputs['qemu_image']['sha256'] == expected['image_sha256']
                index = next(index for index, process in enumerate(self.processes)
                             if process is machine.process)
                self.owner_rows[index].update(admitted=True,
                    executed_image=deepcopy(machine.inputs['qemu_image']),
                    launcher_image=deepcopy(machine.inputs['qemu']))
                _json(self.path, self.report)
            except BaseException as error:
                if getattr(machine, 'process', None) is not None:
                    try:
                        machine.close()
                    except BaseException as cleanup:
                        error.add_note('Constructor cleanup: '+repr(cleanup))
                raise
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(QemuMachine, '__init__', construct)
            yield

    @contextmanager
    def launch(self, project, producer='candidate'):
        self.runtime.project(project)
        tools = self.runtime.config['tools']
        session = project.debugger(tools[producer]['path'], self.directory, backend='qemu-dos',
            dos_boot_image=str(self.disk['image']), dos_mcopy=tools['mcopy']['path'],
            qemu_firmware=self.runtime.config['firmware']['root'], qemu_transport='pipe',
            qemu_checkpoint_tool=tools['qemu_img']['path'], qemu_clock='virtual',
            qemu_audio='sb16-opl' if self.case.capture_format == 's16-stereo' else 'sb16',
            boot_timeout_ms=self.remaining(20000))
        with preserved_context(session, self.report, 'debug-session') as debug:
            # All passive QMP/GDB operations inherit the same case deadline;
            # no missing timeout keyword can silently regain a fresh budget.
            debug._set_deadline(self.deadline)
            yield debug

    @contextmanager
    def project(self, *, create=False):
        context = Project.create(self.db, self.source, image='com') if create else Project(self.db)
        with preserved_context(context, self.report, 'project') as project:
            self.runtime.project(project)
            yield project

    def finish(self, error=None):
        cleanup = []
        for machine in self.machines:
            if machine.process.poll() is None:
                try:
                    machine.close()
                except BaseException as failure:
                    cleanup.append(repr(failure))
        for process, row in zip(self.processes, self.owner_rows, strict=True):
            row.update(reaped=process.poll() is not None, returncode=process.returncode)
        try:
            assert not cleanup, cleanup
            assert all(row['reaped'] and row['returncode'] == 0 for row in self.owner_rows), self.owner_rows
            assert all(row.get('native_logs', {}).get('complete') is True for row in self.owner_rows), self.owner_rows
            self.verify_files()
            self.report['postflight_usage'] = self.runtime.resources()
        except BaseException as failure:
            if error is None:
                error = failure
            else:
                error.add_note('S16 postflight: '+repr(failure))
        if error is not None:
            self.report.update(passed=False, primary_error=type(error).__name__+': '+str(error),
                cleanup_errors=cleanup)
        try:
            _json(self.path, self.report)
            self.runtime.resources()
        except BaseException as persistence:
            if error is None:
                error = persistence
            else:
                error.add_note('S16 final receipt: '+repr(persistence))
        if error is not None:
            error.s16_receipt = self.report
            raise error
        self.runtime.completed.append(self.case.name)


@contextmanager
def case_run(runtime, directory, case, owners):
    run = CaseRun(runtime, directory, case, owners)
    try:
        yield run
    except BaseException as error:
        run.finish(error)
    else:
        run.report['passed'] = True
        run.finish()


def symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    assert type(info['source_mapping']['runtime_base']) is int
    return {key: com_address(info, value) for key, value in offsets.items() if key != 'report_size'}


def park(run, debug, name):
    locations = symbols(debug, run.offsets)
    point = debug.breakpoint(locations[name])
    failed = debug.breakpoint(locations['failed'])
    result = debug.run(timeout_ms=run.remaining(10000))
    run.report['stops'].append(dict(target=name, result=deepcopy(result)))
    _json(run.path, run.report)
    assert result['outcome'] == 'breakpoint' and result.get('timed_out') is False, result
    ids = result['session']['stop_reason']['breakpoint_ids']
    assert point['breakpoint_id'] in ids and failed['breakpoint_id'] not in ids, result
    # An unexpected first stop has no deletion/run/step/advance suffix.
    debug.delete_breakpoint(point['breakpoint_id'])
    debug.delete_breakpoint(failed['breakpoint_id'])
    return result


def sample(run, project, debug, label):
    run.remaining()
    owner, process = debug.vm, debug.vm.process
    before = debug.clock_observe()
    locations = symbols(debug, run.offsets)
    raw = read_bytes(debug, locations['report'], REPORT_SIZE)
    report = parse_report(raw)
    assert report['failure'] == 0, report
    assert (report['bits'], report['channels'], report['rate'], report['auto'], report['fifo']) == (
        run.case.bits, run.case.channels, run.case.rate, int(run.case.auto), int(run.case.fifo))
    assert (report['frontier'], report['geometry'], report['encoding']) == (
        FRONTIERS.index(run.case.frontier), GEOMETRIES.index(run.case.geometry), ENCODINGS.index(run.case.encoding))
    physical = report['buffer_physical']
    arena = read_bytes(debug, locations['arena'], 16384)
    ring = None
    if physical:
        assert physical % RING_BYTES == 0 and locations['arena'] <= physical
        assert physical+RING_BYTES <= locations['arena']+16384
        ring = read_bytes(debug, physical, RING_BYTES)
        active = report['refill_active']
        assert 0 <= active <= BLOCKS
        for block, generation in enumerate(report['generations']):
            if active != block+1:
                assert ring[block*BLOCK_BYTES:(block+1)*BLOCK_BYTES] == block_pcm(block, generation, bits=run.case.bits)
    else:
        assert run.case.frontier == 'absent' and report['stage'] == 0 and arena == bytes(16384)
    device = owner.qmp.call('x-fdisbull-query-sb16')
    assert device['api-version'] == 1
    assert (device['iobase'], device['irq'], device['dma'], device['dma16'], device['version']) == (0x220, 7, 1, 5, 0x0405)
    expected_profile = 'sb16-opl' if run.case.capture_format == 's16-stereo' else 'sb16'
    assert device['audiodev-id'] == 'fdisbull-'+expected_profile
    artifact = debug.capture_audio(label+'.wav')
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact['artifact'],)).fetchone()
    with wave.open(io.BytesIO(bytes(row['data'])), 'rb') as stream:
        geometry = (2, 2, 32000) if run.case.capture_format == 's16-stereo' else (1, 1, 32000)
        assert stream.getparams()[:3] == geometry
        pcm = stream.readframes(stream.getnframes())
    audio = debug.audio_observe()
    assert audio['dropped_frames'] == 0 and audio['state'] == 'capturing'
    assert len(pcm) == audio['frames'] * audio['sample_format']['bytes_per_frame']
    cpu = debug.registers()
    after = debug.clock_observe()
    stationary_clock(before, after)
    assert debug.vm is owner and owner.process is process and process.poll() is None
    result = dict(cpu=cpu, report_hex=raw.hex(), report=report,
        arena_hex=arena.hex(), ring_hex=ring.hex() if ring is not None else None,
        device=device, pcm_hex=pcm.hex(), pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        chunks=deepcopy(audio['native']['chunks']), audio=audio, artifact=artifact,
        clock=after, clocks=dict(before=before, after=after))
    run.report.setdefault('samples', {})[label] = result
    _json(run.path, run.report)
    run.remaining()
    return result


def assert_exact(actual, expected, *, restored):
    for key in ('cpu', 'report_hex', 'report', 'arena_hex', 'ring_hex', 'device',
                'pcm_hex', 'pcm_sha256', 'chunks'):
        assert actual[key] == expected[key], key
    left, right = deepcopy(actual['audio']['native']), deepcopy(expected['audio']['native'])
    for value in (left, right):
        value.pop('epoch')
        value.pop('token')
    assert left == right, 'Native audio content/geometry changed'
    assert actual['audio']['sample_format'] == expected['audio']['sample_format']
    if restored:
        assert actual['audio']['window'] != expected['audio']['window']
        assert actual['clock']['epoch'] != expected['clock']['epoch']
        assert actual['clock']['virtual_clock']['native']['epoch'] == expected['clock']['virtual_clock']['native']['epoch']+1
        old_budget = expected['clock']['virtual_clock']['native'].get('budget-token')
        if old_budget is not None:
            assert actual['clock']['virtual_clock']['native']['budget-token'] != old_budget
        assert comparable_clock(actual['clock']) == comparable_clock(expected['clock'])
    else:
        assert actual['audio']['window'] == expected['audio']['window']
        stationary_clock(expected['clock'], actual['clock'])


def selected(run, value):
    report, device, case = value['report'], value['device'], run.case
    if case.frontier == 'absent':
        assert not device['voice-present'] and not device['dma-active'] and report['stage'] == 0
        return
    assert report['stage'] == 2 and report['refill_active'] == 0
    assert (report['reset_byte'], report['major'], report['minor']) == (0xaa, 4, 5)
    assert device['voice-present']
    assert (device['voice-frequency'], device['voice-channels'], device['voice-bits'], device['voice-signed']) == (
        case.rate, case.channels, 16, True)
    assert device['block-size'] == case.block_bytes and device['dma-length'] == case.dma_bytes
    assert 0 < device['left-till-irq'] <= case.block_bytes and device['left-till-irq'] % (2*case.channels) == 0
    if case.frontier == 'masked':
        assert device['dma-mask'] & 2 and device['dma-status'] & 0x20 and device['dma-active']
    elif case.frontier == 'irq16':
        assert device['irq-status'] & 2 and report['irq_count'] == 0
    elif case.frontier == 'irq-both':
        assert device['irq-status'] & 3 == 3 and report['irq_count'] == 0
    elif case.frontier in ('halted', 'inactive'):
        assert not device['dma-active'] and not device['voice-active']
        if case.frontier == 'inactive':
            assert report['irq_count'] == 1
    else:
        assert device['dma-active'] and device['voice-active']
        delta = expected_dma_progress(report['initial_address'], report['selected_address'])
        assert delta['bytes'] > 0


def enter_capture(run, project, debug, *, unsafe=False):
    entry_clock = debug.clock_observe()
    run.report['entry_clock'] = entry_clock
    if run.case.frontier != 'absent':
        park(run, debug, 'ready')
    run.report['audio_start'] = debug.audio_start(max_frames=80000, capture_format=run.case.capture_format)
    if run.case.frontier != 'absent':
        park(run, debug, 'started' if unsafe else 'selected')
    result = sample(run, project, debug, 'captured')
    assert result['clock']['virtual_ns']-entry_clock['virtual_ns'] < NATIVE_BOUNDS['post_entry_guest_ns']
    if not unsafe:
        selected(run, result)
    return result


def advance(run, project, debug, captured, label):
    before = debug.clock_observe()
    result = debug.clock_advance(FUTURE_NS, timeout_ms=run.remaining())
    run.report.setdefault('advances', {})[label] = deepcopy(result)
    _json(run.path, run.report)
    budget_receipt(result, FUTURE_NS, before=before)
    assert clock_timer_stop_is_ordinary(result), result
    state = sample(run, project, debug, label)
    report = state['report']
    assert report['stage'] == 3 and report['busy_count'] > captured['report']['busy_count']
    assert report['irq_count'] > captured['report']['irq_count']
    assert state['pcm_hex'].startswith(captured['pcm_hex'])
    assert len(state['pcm_hex']) > len(captured['pcm_hex']) and len(set(bytes.fromhex(state['pcm_hex']))) > 1
    if run.case.auto:
        assert sum(report['generations']) > sum(captured['report']['generations'])
        assert state['ring_hex'] != captured['ring_hex']
    if run.case.frontier == 'future-rate':
        assert state['device']['voice-frequency'] == 22050 and report['irq_count'] == 2
    assert state['clock']['virtual_ns']-run.report['entry_clock']['virtual_ns'] < NATIVE_BOUNDS['post_entry_guest_ns']
    return state


def restore(run, project, debug, control, label):
    run.runtime.project(project)
    old = debug.vm.process
    former = debug.dos_process_info()['capture_epoch']
    loaded = debug.load_state(control['saved']['artifact'], timeout_ms=run.remaining(20000))
    run.report.setdefault('restores', {})[label] = loaded
    assert old.poll() is not None and old is not debug.vm.process and debug.vm.process.poll() is None
    assert loaded['source_binding_restored'] is True
    assert debug.dos_process_info()['capture_epoch'] not in (former, control['origin_epoch'])
    actual = sample(run, project, debug, label+'-captured')
    assert_exact(actual, control['captured'], restored=True)
    assert actual['clock']['virtual_clock']['native']['epoch'] == control['captured']['clock']['virtual_clock']['native']['epoch']+1
    return actual


def _cold_control(run, control):
    return dict(control, config=str(run.runtime.config_path), config_sha256=run.runtime.config_sha,
        directory=str(run.directory), db=str(run.db), source=str(run.source),
        source_sha256=digest(run.source), disk=str(run.disk['image']),
        disk_sha256=run.disk['prepared_sha256'], original_boot_sha256=run.disk['source_sha256'],
        case=run.case.record(), offsets=run.offsets, deadline=run.deadline,
        entry_clock=run.report['entry_clock'])


def _cold_restore(control_path, expected_sha):
    """Separate Python and separate native processes; no inherited live VM."""
    signal.signal(signal.SIGTERM, terminate_as_exception)
    assert digest(control_path) == expected_sha, 'Cold control bytes changed'
    control = json.loads(Path(control_path).read_text())
    runtime = Runtime(control['config'], control['config_sha256'])
    run = CaseRun.__new__(CaseRun)
    run.runtime = runtime
    run.directory = Path(control['directory']).resolve(strict=True)
    assert run.directory.is_relative_to(runtime.output)
    run.case = VoiceCase(**control['case']).validate()
    run.deadline = min(control['deadline'], runtime.deadline,
        time.monotonic()+NATIVE_BOUNDS['cold_seconds'])
    run.owner_limit, run.machines, run.processes, run.owner_rows = 2, [], [], []
    run.report = dict(format=PROFILE, cold_python_pid=os.getpid(), passed=False,
        owners=run.owner_rows, entry_clock=control['entry_clock'], stops=[])
    run.path = run.directory/'cold-native-s16.json'
    run.source, run.db = Path(control['source']), Path(control['db'])
    assert run.source.parent == run.db.parent == run.directory
    run.code = run.source.read_bytes()
    assert digest(run.source) == control['source_sha256']
    run.offsets = control['offsets']
    run.disk = dict(image=Path(control['disk']), prepared_sha256=control['disk_sha256'],
        source_sha256=control['original_boot_sha256'])
    assert run.disk['image'].parent == run.directory
    run.verify_files()
    primary = None
    try:
        with run.owners(), run.project() as project:
            runtime.project(project)
            state = project.debug_state_info(control['saved']['artifact'])
            assert state['sha256'] == control['saved']['sha256']
            with run.launch(project) as debug:
                assert debug.run_id != control['origin_run']
                restore(run, project, debug, control, 'cold')
                actual = advance(run, project, debug, control['captured'], 'cold-future')
                assert_exact(actual, control['future'], restored=True)
                assert actual['clock']['virtual_clock']['native']['epoch'] == control['future']['clock']['virtual_clock']['native']['epoch']+1
                run.report['full_future_exact'] = True
        runtime.verify_inputs()
        assert digest(control_path) == expected_sha
        run.report['passed'] = True
    except BaseException as error:
        primary = error
    finally:
        run.finish(primary)


def _cold(run, control):
    assert run.runtime.owners+2 <= NATIVE_BOUNDS['owners']
    # Reserve the child's maximum before spawn. If it fails before its final
    # receipt, this remains a conservative bound, never an invented reap.
    run.runtime.owners += 2
    run.report['cold_owner_reservation'] = 2
    control_path = run.directory/'cold-control.json'
    _json(control_path, _cold_control(run, control))
    control_sha = digest(control_path)
    run.report['cold_control_sha256'] = control_sha
    command = [sys.executable, str(Path(__file__).resolve()), '--cold', str(control_path), control_sha]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=os.pathsep.join((str(run.runtime.root/'src'), str(run.runtime.root/'tests'))),
        FDISBULL_TARGET_STORE=str(run.runtime.store))
    available = min(NATIVE_BOUNDS['cold_seconds'], run.remaining(30000)/1000)
    try:
        result, receipt = run_owned_cold(command, cwd=run.runtime.root, env=env,
            log_path=run.directory/'cold.log', receipt_path=run.directory/'cold-process.json',
            timeout=available, grace=NATIVE_BOUNDS['cleanup_grace_seconds'])
    finally:
        # Raw files are retained even when parsing a partial receipt is not
        # possible; a secondary inspection must not replace a primary error.
        primary = sys.exception()
        for key, name in (('cold_process', 'cold-process.json'), ('cold', 'cold-native-s16.json')):
            try:
                receipt_path = run.directory/name
                if receipt_path.exists():
                    run.report[key] = json.loads(receipt_path.read_text())
            except BaseException as inspection:
                if primary is None:
                    raise
                primary.add_note('Retained cold receipt could not be decoded: '+repr(inspection))
    child = run.report['cold']
    assert digest(control_path) == control_sha
    assert result.returncode == 0 and receipt['passed'], receipt
    assert receipt['leader_reaped'] and receipt['group_gone'] and not receipt['cleanup_error']
    assert child['passed'] and child['cold_python_pid'] != os.getpid()
    assert len(child['owners']) == 2 and all(row['reaped'] and row['returncode'] == 0 for row in child['owners'])
    assert all(row['pid'] not in {process.pid for process in run.processes} for row in child['owners'])
    assert child['full_future_exact']
    assert_exact(child['samples']['cold-future'], control['future'], restored=True)
    assert child['samples']['cold-future']['audio']['window'] != control['hot_window']


@pytest.mark.parametrize('voice', POSITIVE_CASES, ids=lambda case: case.name)
def test_s16_recovery_full_future_hot_and_separate_python_cold(native_runtime, tmp_path, voice):
    with case_run(native_runtime, tmp_path, voice, 2) as run:
        with run.owners(), run.project(create=True) as project:
            with run.launch(project) as debug:
                captured = enter_capture(run, project, debug)
                saved = debug.save_state('signed16-captured.state', max_bytes=NATIVE_BOUNDS['checkpoint_bytes'])
                after = sample(run, project, debug, 'after-save')
                assert_exact(after, captured, restored=False)
                control = dict(saved=saved, captured=captured, origin_run=debug.run_id,
                    origin_epoch=debug.dos_process_info()['capture_epoch'])
                run.report['saved'] = saved
                future = advance(run, project, debug, captured, 'original-future')
                control['future'] = future
                restore(run, project, debug, control, 'hot')
                hot = advance(run, project, debug, captured, 'hot-future')
                assert_exact(hot, future, restored=True)
                assert hot['clock']['virtual_clock']['native']['epoch'] == future['clock']['virtual_clock']['native']['epoch']+1
                control['hot_window'] = hot['audio']['window']
                run.report['full_hot_future_exact'] = True
        assert len(run.processes) == 2
        _cold(run, control)


def _capture_refusal(run, project, debug, *, legacy=False):
    before = enter_capture(run, project, debug, unsafe=True)
    expected = ('SB16 checkpoint supports U8 mono/stereo' if legacy else
        'SB16 checkpoint supports U8 or signed little-endian S16 mono/stereo voices at 5000..45000 Hz'
        if run.case.encoding != 's16' else
        'SB16 S16 checkpoint requires coherent complete frames on incrementing DMA5')
    if legacy:
        assert (before['device']['voice-bits'], before['device']['voice-signed']) == (16, True)
    elif run.case.encoding == 'u16':
        assert (before['device']['voice-bits'], before['device']['voice-signed']) == (16, False)
    elif run.case.encoding == 's8':
        assert (before['device']['voice-bits'], before['device']['voice-signed']) == (8, True)
    elif run.case.geometry == 'partial-block':
        assert before['device']['block-size'] % 4 == 2
    elif run.case.geometry == 'partial-ring':
        assert before['device']['dma-length'] % 4 == 2
    owner, process = debug.vm, debug.vm.process
    with pytest.raises(ValueError, match=re.escape(expected)) as refused:
        debug.save_state('deliberately-refused.state', max_bytes=NATIVE_BOUNDS['checkpoint_bytes'])
    run.report['capture_refusal'] = str(refused.value)
    assert debug.vm is owner and owner.process is process and process.poll() is None and not debug.closed
    after = sample(run, project, debug, 'after-refusal')
    assert_exact(after, before, restored=False)
    assert len(run.processes) == 1


@pytest.mark.parametrize('voice', UNSAFE_CASES, ids=lambda case: case.name)
def test_s16_recovery_unsupported_geometry_refuses_without_mutating_owner(native_runtime, tmp_path, voice):
    with case_run(native_runtime, tmp_path, voice, 1) as run:
        with run.owners(), run.project(create=True) as project:
            with run.launch(project) as debug:
                _capture_refusal(run, project, debug)


@pytest.mark.parametrize('voice', LEGACY_CASES, ids=lambda case: case.name)
def test_s16_recovery_explicit_fresh_parent_producer_retains_u8_only_refusal(native_runtime, tmp_path, voice):
    with case_run(native_runtime, tmp_path, voice, 1) as run:
        run.report['legacy_control'] = 'Pinned 31-patch parent producer'
        with run.owners('legacy'), run.project(create=True) as project:
            with run.launch(project, 'legacy') as debug:
                _capture_refusal(run, project, debug, legacy=True)


def corrupt_artifact(run, project, debug, saved, damage):
    from fdisbull import qemu_dos_checkpoint as checkpoint
    row = project.db.execute('SELECT data,sha256,metadata FROM debug_artifacts WHERE id=?',
        (saved['artifact'],)).fetchone()
    data = bytes(row['data'])
    assert row['sha256'] == saved['sha256'] == hashlib.sha256(data).hexdigest()
    machine, bundle = checkpoint._unarchive(data)
    record = bundle['instrumentation']
    state = json.loads(record['state'])
    assert state['audio']['profile'] == 'sb16' and state['audio']['active'] is True
    old_core = state['audio']['core-base64']
    state['audio']['core-base64'] = corrupt_core2(old_core, damage)
    record['state'] = checkpoint._json(state).decode('utf-8')
    record['sha256'] = checkpoint._sha(record['state'].encode('utf-8'))
    metadata = json.loads(row['metadata'])
    metadata['instrumentation']['sha256'] = record['sha256']
    metadata['sidecar_sha256'] = checkpoint._sha(checkpoint._json(bundle))
    changed = checkpoint._archive(machine, bundle)
    artifact = debug._artifact('changed-'+damage+'.state', 'state', changed, metadata)
    run.report['corruption'] = dict(damage=damage, before_core_sha256=hashlib.sha256(
        base64.b64decode(old_core)).hexdigest(), after_core_sha256=hashlib.sha256(
        base64.b64decode(state['audio']['core-base64'])).hexdigest(), artifact=artifact,
        every_outer_hash_recomputed=True, original_checkpoint_unchanged=True)
    assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
    return artifact


@pytest.mark.parametrize('damage', tuple(CORRUPTIONS))
def test_s16_recovery_corrupt_core_reaches_native_guard_and_closes_uncertain_owners(native_runtime, tmp_path, damage):
    voice = VoiceCase('corrupt-'+damage, auto=True, channels=2, rate=11025)
    with case_run(native_runtime, tmp_path, voice, 2) as run:
        with run.owners(), run.project(create=True) as project:
            with run.launch(project) as debug:
                captured = enter_capture(run, project, debug)
                saved = debug.save_state('valid-before-corruption.state', max_bytes=NATIVE_BOUNDS['checkpoint_bytes'])
                assert_exact(sample(run, project, debug, 'after-valid-save'), captured, restored=False)
                bad = corrupt_artifact(run, project, debug, saved, damage)
                owner = debug.vm
                prefix = 'QMP x-fdisbull-instrumented-checkpoint-import: '
                with pytest.raises(DebuggerError, match='^'+re.escape(prefix)) as refused:
                    debug.load_state(bad['artifact'], timeout_ms=run.remaining(20000))
                native = json.loads(str(refused.value)[len(prefix):])
                assert native == {'class': 'GenericError', 'desc': CORRUPTIONS[damage][2]}, native
                run.report['restore_refusal'] = native
                assert len(run.machines) == 2 and run.machines[0] is owner
                assert debug.closed and all(machine.process.poll() is not None for machine in run.machines)
                assert all(machine.qmp is None and machine.gdb is None for machine in run.machines)
                assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']


def test_s16_recovery_producer_identity_refuses_before_native_import(native_runtime, tmp_path):
    voice = VoiceCase('producer-identity', auto=True, channels=2, rate=11025)
    with case_run(native_runtime, tmp_path, voice, 2) as run:
        with run.project(create=True) as project:
            with run.owners(), run.launch(project) as debug:
                enter_capture(run, project, debug)
                saved = debug.save_state('candidate-only.state', max_bytes=NATIVE_BOUNDS['checkpoint_bytes'])
                run.report['candidate_saved'] = saved
            with run.owners('legacy'), run.launch(project, 'legacy') as debug:
                owner, process = debug.vm, debug.vm.process
                before_cpu, before_clock = debug.registers(), debug.clock_observe()
                with pytest.raises(ValueError, match='Process checkpoint sidecar or runtime identity differs') as refused:
                    debug.load_state(saved['artifact'], timeout_ms=run.remaining(20000))
                run.report['producer_refusal'] = str(refused.value)
                assert len(run.machines) == 2, 'Wrong producer reached fresh destination construction'
                assert debug.vm is owner and owner.process is process and process.poll() is None
                assert not debug.closed and debug.registers() == before_cpu
                stationary_clock(before_clock, debug.clock_observe())


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != '--cold':
        raise SystemExit('Use the reviewed pytest matrix or its explicit --cold child only')
    _cold_restore(sys.argv[2], sys.argv[3])

