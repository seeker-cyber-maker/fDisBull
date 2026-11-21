"""One explicitly admitted native DOS return after one public asynchronous resume.

This source is not execution admission. The separate original-owner controller
must admit the exact producer tuple, source, deadline and output envelope.
The authored COM exits with 42; a stopped PC alone never qualifies its return.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from fdisbull import dos_process_helper as helper
from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline


EXIT_COM = bytes.fromhex('b82a4ccd21')
FIXTURE_SHA256 = 'ef892afebf7fabb6142f6f024536a9c51bc48f3b2158a060c7ba1eae0dcaa956'
QEMU_SHA256 = 'b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af'
QEMU_IMG_SHA256 = 'b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03'
BOOT_SHA256 = '552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc'
WORK_SECONDS, CLEANUP_SECONDS = 45, 10
STATUS_POLL_LIMIT, RUNNING_WAIT_MS = 32, 5
PUBLIC_CALL_LIMIT, NATIVE_CALL_LIMIT = 36, 1024
REPORT_LIMIT, LOG_LIMIT = 4 * 1024**2, 2 * 1024**2


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _error(error):
    return dict(type=type(error).__name__, message=str(error), notes=list(getattr(error, '__notes__', [])))


def _remaining(deadline, maximum=1000):
    value = int((deadline - time.monotonic()) * 1000)
    if value < 1:
        raise TimeoutError('Original asynchronous-return witness work deadline expired')
    return min(maximum, value)


def _write_json(path, value):
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    assert len(data) <= REPORT_LIMIT, 'Asynchronous-return evidence exceeded its byte cap'
    temporary = path.with_suffix(path.suffix + '.writing')
    temporary.write_bytes(data)
    temporary.replace(path)


def _word(registers, name):
    value = registers['registers'][name]
    value = int(value, 16) if type(value) is str else value
    assert type(value) is int and 0 <= value <= 0xffff
    return value


@pytest.fixture(scope='module', autouse=True)
def require_owned_async_return_gate(request):
    if os.environ.get('FDISBULL_REQUIRE_ASYNC_RETURN') != '1':
        pytest.skip('Requires the separately admitted one-owner native asynchronous-return gate')
    assert getattr(request.config, '_fdisbull_async_return_owned_gate', None) == 'fdisbull-async-return-owned-gate-1'
    assert request.config.option.maxfail == 1 and not getattr(request.config.option, 'numprocesses', None)
    assert sys.platform.startswith('linux')


@pytest.fixture
def async_return_runtime(tmp_path):
    for parent in (tmp_path.resolve(), *tmp_path.resolve().parents):
        assert not (parent / '.git').exists(), 'Private native output requires no Git ancestor'
    selected = dict(qemu='FDISBULL_QEMU_DOS', qemu_img='FDISBULL_QEMU_IMG',
        boot='FDISBULL_QEMU_DOS_BOOT_IMAGE', mcopy='FDISBULL_QEMU_DOS_MCOPY',
        firmware='FDISBULL_QEMU_DOS_FIRMWARE')
    assert all(os.environ.get(name) for name in selected.values()), 'Required pinned runtime input is missing'
    runtime = {name: Path(os.environ[variable]).absolute() for name, variable in selected.items()}
    for name, path in runtime.items():
        assert path.is_dir() if name == 'firmware' else path.is_file(), (name, path)
        if name not in ('firmware', 'boot'):
            assert os.access(path, os.X_OK), (name, path)
    for name, sha in (('qemu', QEMU_SHA256), ('qemu_img', QEMU_IMG_SHA256), ('boot', BOOT_SHA256)):
        assert digest(runtime[name]) == sha, 'Wrong retained producer or boot image: ' + name
    return runtime


class _Journal:
    def __init__(self, directory):
        self.directory = directory
        self.deadline = time.monotonic() + WORK_SECONDS
        self.phase = 'constructor'
        self.value = dict(format='fdisbull-qemu-dos-async-return-1', backend='qemu', complete=False,
            fixture_hex=EXIT_COM.hex(), fixture_sha256=FIXTURE_SHA256, fixture_bytes=len(EXIT_COM),
            owner={}, calls=[], native_calls=[], running_waits=[],
            status_poll_limit=STATUS_POLL_LIMIT, running_wait_ms=RUNNING_WAIT_MS,
            work_deadline_monotonic=self.deadline, no_retry=True, no_post_stop_execution=True,
            scope='One authored DOS child return after one public resume; no game or strict-pause qualification')

    def save(self):
        self.value['phase'] = self.phase
        _write_json(self.directory / 'async-return-result.json', self.value)

    def call(self, method, arguments, action, *, native=False):
        _remaining(self.deadline)
        rows = self.value['native_calls' if native else 'calls']
        assert len(rows) < (NATIVE_CALL_LIMIT if native else PUBLIC_CALL_LIMIT)
        row = dict(index=len(rows), phase=self.phase, method=method, arguments=deepcopy(arguments),
                   host_before_ns=time.monotonic_ns())
        rows.append(row)
        try:
            result = action()
            row['reply'] = deepcopy(result)
            return result
        except BaseException as error:
            row['error'] = _error(error)
            raise
        finally:
            row['host_after_ns'] = time.monotonic_ns()
            primary = sys.exception()
            try:
                self.save()
            except BaseException as error:
                if primary is None:
                    raise
                primary.add_note('Asynchronous-return journal retention failed: ' + repr(error))


@contextmanager
def _trace(debug, journal):
    vm, qmp, remote, serial = debug.vm, debug.vm.qmp, debug.vm.gdb, debug._channel
    process = vm.process
    assert process.poll() is None and remote is not None
    vm.operation_deadline = qmp.operation_deadline = remote.operation_deadline = journal.deadline
    originals = qmp.call, remote.request, remote.execute, debug._read, debug._receive_report

    def current():
        assert debug.vm is vm and vm.qmp is qmp and vm.gdb is remote and vm.process is process
        assert debug._channel is serial and process.poll() is None
        _remaining(journal.deadline)

    def call(method, arguments=None):
        current()
        value = journal.call('public.' + method, arguments,
                             lambda: getattr(debug, method)(**(arguments or {})))
        current()
        return value

    def qmp_call(method, arguments=None, timeout_ms=30000, **kwargs):
        current()
        return journal.call('qmp.' + method, dict(arguments=arguments, timeout_ms=timeout_ms, **kwargs),
            lambda: originals[0](method, arguments, timeout_ms, **kwargs), native=True)

    def request(command, timeout_ms=10000):
        current()
        raw = command.encode('ascii') if type(command) is str else command
        value = journal.call('gdb.request', dict(command_hex=raw.hex(), timeout_ms=timeout_ms),
            lambda: dict(reply_hex=originals[1](command, timeout_ms).hex()), native=True)
        return bytes.fromhex(value['reply_hex'])

    def execute(command, timeout_ms, **kwargs):
        # Record the attempted violation without dispatching an extra instruction.
        def refused():
            raise AssertionError('No GDB execution is admitted after the stopped COM entry')
        return journal.call('gdb.execute', dict(command=str(command), timeout_ms=timeout_ms), refused, native=True)

    def read(address, length):
        current()
        value = journal.call('helper.memory', dict(address=address, length=length),
                             lambda: dict(hex=originals[3](address, length).hex()), native=True)
        current()
        return bytes.fromhex(value['hex'])

    def receive(deadline):
        current()
        def original():
            report, raw = originals[4](deadline)
            return dict(report=report, hex=raw.hex())
        value = journal.call('helper.serial_report', dict(deadline=deadline), original, native=True)
        current()
        return value['report'], bytes.fromhex(value['hex'])

    qmp.call, remote.request, remote.execute = qmp_call, request, execute
    debug._read, debug._receive_report = read, receive
    try:
        yield call
    finally:
        qmp.call, remote.request, remote.execute, debug._read, debug._receive_report = originals


def _campaign(debug, journal, call):
    journal.phase = 'stopped-entry'
    status = call('status')
    registers = call('registers')
    ip = registers['instruction_pointer']
    assert registers['cpu_mode'] == 'real' and (int(ip, 16) if type(ip) is str else ip) == 0x100
    address = _word(registers, 'cs') * 16 + 0x100
    source = call('memory', dict(address=address, length=len(EXIT_COM), space='physical'))
    assert source['length'] == len(EXIT_COM) and bytes.fromhex(source['hex']) == EXIT_COM
    assert status['state'] == 'stopped' and status['native_state']['running'] is False
    assert status['process']['state'] == 'active' and status['process']['source_mapping']['live'] is True
    assert debug._serial_buffer == bytearray()
    ready = helper.parse_report(debug._ready_bytes, debug._nonce)
    assert ready == debug._ready and ready['type'] == 'ready'
    assert debug._helper == helper.build_loader('A:\\EXIT42.COM', b'', debug._nonce)
    point = debug._return_breakpoint
    expected = dict(kind=1, access='x', length=1, owner='user',
                    address=ready['helper_segment'] * 16 + ready['exit_wait_ip'])
    assert debug.breakpoints == {point: expected}
    journal.value['entry'] = dict(status=status, registers=registers, source=source,
        ready=ready, ready_hex=debug._ready_bytes.hex(), nonce_hex=debug._nonce.hex(),
        helper_sha256=_sha(debug._helper), helper_hex=debug._helper.hex(),
        return_control=dict(identifier=point, record=deepcopy(expected)),
        process_epoch=status['process']['capture_epoch'])
    journal.save()
    journal.phase = 'resume'
    result = journal.value['resume_result'] = call('resume')
    polls = []
    journal.value['poll_results'] = polls
    for number in range(1, STATUS_POLL_LIMIT + 1):
        assert type(result['native_state']['running']) is bool
        if not result['native_state']['running']:
            break
        assert result['state'] == 'running' and result['native_state']['status'] == 'running'
        # The only host waits occur after a still-running reply, before another
        # permitted status observation. They never extend the original deadline.
        assert _remaining(journal.deadline, 1000) > RUNNING_WAIT_MS
        began = time.monotonic_ns()
        time.sleep(RUNNING_WAIT_MS / 1000)
        journal.value['running_waits'].append(dict(before_poll=number, requested_ms=RUNNING_WAIT_MS,
            host_before_ns=began, host_after_ns=time.monotonic_ns()))
        journal.phase = 'poll-' + str(number)
        result = call('status')
        polls.append(result)
    assert result['state'] == 'stopped' and result['native_state']['running'] is False, 'No actual stop within the fixed polling cap'
    journal.phase = 'return-evidence'
    journal.value['terminal_result'] = deepcopy(result)
    before_native = len(journal.value['native_calls'])
    process, stopped = result['process'], result['process_stop']
    assert process['state'] == 'exited' and process['capture_epoch'] != journal.value['entry']['process_epoch']
    assert process['source_mapping']['live'] is False and process['source_mapping']['live_ranges'] == []
    assert process['source_mapping']['status'] == 'invalidated-on-process-exit'
    termination = process['termination']
    assert termination['type'] == 'normal' and termination['code'] == 42 and termination['dos_ax'] == 42
    assert termination['resident'] is False and termination['psp_segment'] == ready['child_psp']
    assert termination['parent_psp_segment'] == ready['helper_psp']
    assert stopped['outcome'] == 'guest_exit' and stopped['process'] == process
    assert stopped['session']['state'] == 'stopped' and stopped['session']['stop_reason']['kind'] == 'guest_exit'
    assert stopped['session']['stop_reason']['guest_exit'] == termination
    assert stopped['registers']['cpu_mode'] == 'real' and stopped['registers']['linear_pc'] == hex(expected['address'])
    native_stop = stopped['native_machine_stop']
    assert native_stop['kind'] == 'stopped' and native_stop['native_reply'] is None
    assert native_stop['classification_complete'] is False and native_stop['breakpoint_ids'] == []
    assert native_stop['native_state'] == result['native_state'] and native_stop['address'] == hex(expected['address'])
    assert stopped['stop']['trigger'] == 'guest_exit' and stopped['stop']['context'] == 'dos-process'
    assert debug._return_breakpoint is None and debug.breakpoints == {} and debug._dos_async_pending is None
    assert debug._serial_buffer == bytearray() and not debug._checkpoint_entry_clean
    native = journal.value['native_calls']
    serial = [row['reply'] for row in native if row['method'] == 'helper.serial_report']
    report_address = ready['helper_segment'] * 16 + ready['report_offset']
    memory = [row['reply']['hex'] for row in native if row['method'] == 'helper.memory'
              and row['arguments'] == dict(address=report_address, length=helper.REPORT_SIZE)]
    assert len(serial) == len(memory) == 1 and serial[0]['hex'] == memory[0]
    observed = helper.parse_report(bytes.fromhex(memory[0]), debug._nonce)
    assert observed == serial[0]['report'] and observed['type'] == 'terminated' and observed['dos_result'] == 42
    assert all(observed[key] == value for key, value in ready.items() if key not in ('type', 'record_type', 'dos_result'))
    controls = [row for row in native if row['method'] in ('qmp.cont', 'qmp.stop', 'gdb.execute')]
    assert [row['method'] for row in controls] == ['qmp.cont'] and controls[0]['reply'] == {}
    removal = f'z1,{expected["address"]:x},1'.encode().hex()
    removed = [row for row in native if row['method'] == 'gdb.request'
               and row['arguments']['command_hex'] == removal]
    assert len(removed) == 1 and removed[0]['reply']['reply_hex'] == b'OK'.hex()
    # These are host-only FDB observations. There is no extra public status,
    # guest read, settling operation or execution after the first actual stop.
    def persisted():
        _remaining(journal.deadline)
        metadata = json.loads(debug.project.db.execute(
            'SELECT metadata FROM debug_runs WHERE id=?', (debug.run_id,)).fetchone()[0])
        events = list(debug.project.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation='dos-process-return'", (debug.run_id,)))
        return dict(process=metadata['process'], return_events=[json.loads(row[0]) for row in events])
    first = persisted()
    second = persisted()
    assert first == second and first['process'] == process and len(first['return_events']) == 1
    assert first['return_events'][0]['outcome'] == 'guest_exit'
    assert first['return_events'][0]['process'] == process
    assert len(journal.value['native_calls']) == before_native
    journal.value.update(return_memory_hex=memory[0], return_serial_hex=serial[0]['hex'], return_report=observed,
        persistence=first, persistence_observations=[first, second], persistence_repeated_equal=True,
        return_control_after=dict(identifier=debug._return_breakpoint, breakpoints=deepcopy(debug.breakpoints),
                                  pending=debug._dos_async_pending, checkpoint_entry_clean=debug._checkpoint_entry_clean),
        private_return_control_removed=True,
        source_lifetime_invalidated=True, observed_exit_code=42, poll_count=len(polls),
        no_native_calls_after_terminal_observation=True, qualified_before_cleanup=True)
    journal.save()


def _save_logs(descriptors, directory):
    result = {}
    for name, descriptor in descriptors.items():
        size = os.fstat(descriptor).st_size
        assert size <= LOG_LIMIT
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks, remaining = [], LOG_LIMIT + 1
        while remaining:
            part = os.read(descriptor, min(65536, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        data = b''.join(chunks)
        assert len(data) == size == os.fstat(descriptor).st_size
        with (directory / name).open('xb') as stream:
            stream.write(data)
        result[name] = dict(bytes=len(data), sha256=_sha(data), complete_after_exit=True)
    return result


@contextmanager
def _owner(directory, runtime, journal):
    source = directory / 'EXIT42.COM'
    source.write_bytes(EXIT_COM)
    process, cleanup_began = None, None
    descriptors = {}
    try:
        disk = prepare_dos_baseline(runtime['boot'], directory / 'return-boot.img', runtime['mcopy'])
        journal.value['prepared_boot_sha256'] = disk['prepared_sha256']
        _remaining(journal.deadline)
        with Project.create(directory / 'return.fdb', source, image='com') as project:
            with project.debugger(str(runtime['qemu']), directory, backend='qemu-dos',
                    dos_boot_image=str(disk['image']), dos_mcopy=str(runtime['mcopy']),
                    dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
                    qemu_firmware=str(runtime['firmware']), qemu_checkpoint_tool=str(runtime['qemu_img']),
                    qemu_clock='virtual', qemu_retrace='precise',
                    boot_timeout_ms=_remaining(journal.deadline, 15000)) as debug:
                process = debug.vm.process
                journal.value['owner']['pid'] = process.pid
                journal.value['machine_configuration'] = deepcopy(debug.vm.machine_configuration)
                try:
                    root = Path(debug.vm.temporary.name)
                    for name in ('qemu.log', 'boot.log'):
                        descriptors[name] = os.open(root / name, os.O_RDONLY)
                    with _trace(debug, journal) as call:
                        yield debug, call
                finally:
                    cleanup_began = time.monotonic()
        assert digest(runtime['boot']) == BOOT_SHA256 and digest(disk['image']) == disk['prepared_sha256']
        journal.value['boot_inputs_unchanged'] = True
    finally:
        primary = sys.exception()
        failure = None
        try:
            if process is not None:
                journal.value['owner'].update(reaped=process.poll() is not None, returncode=process.returncode,
                    cleanup_seconds=time.monotonic() - cleanup_began if cleanup_began is not None else None)
                assert process.poll() == 0, 'Original QEMU owner did not reap with exit zero'
                assert cleanup_began is not None and journal.value['owner']['cleanup_seconds'] <= CLEANUP_SECONDS
            journal.value['logs'] = _save_logs(descriptors, directory)
            assert source.read_bytes() == EXIT_COM
            if primary is None:
                assert journal.value['qualified_before_cleanup'] is True
                assert journal.value['boot_inputs_unchanged'] is True
                journal.value['complete'] = True
        except BaseException as error:
            failure = error
            journal.value.setdefault('cleanup_errors', []).append(_error(error))
        finally:
            for descriptor in descriptors.values():
                try:
                    os.close(descriptor)
                except OSError as error:
                    failure = failure or error
                    journal.value.setdefault('cleanup_errors', []).append(_error(error))
            try:
                journal.save()
            except BaseException as error:
                failure = failure or error
        if failure is not None:
            if primary is None:
                raise failure
            primary.add_note('Asynchronous-return original owner cleanup failed: ' + repr(failure))


def test_native_one_resume_observes_verified_dos_exit42(tmp_path, async_return_runtime):
    assert _sha(EXIT_COM) == FIXTURE_SHA256
    journal = _Journal(tmp_path)
    try:
        with _owner(tmp_path, async_return_runtime, journal) as (debug, call):
            _campaign(debug, journal, call)
        assert journal.value['qualified_before_cleanup'] is True and journal.value['owner']['reaped'] is True
        journal.value['complete'] = True
    except BaseException as error:
        journal.value['failure'] = _error(error)
        raise
    finally:
        primary = sys.exception()
        try:
            journal.save()
        except BaseException as error:
            if primary is None:
                raise
            primary.add_note('Asynchronous-return final evidence retention failed: ' + repr(error))
