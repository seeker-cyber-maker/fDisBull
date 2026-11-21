"""Strict paired pause observations on one explicitly admitted producer tuple.

This source is not an execution admission. The one native node requires a
separate finite ownership controller. All four immediate stopped brackets are
retained, including drift; there is no settling read, allowed delta or retry.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline


BUSY_COM = bytes.fromhex('b83412bb78564043ebfc')
FIXTURE_SHA256 = 'fc98fc96de8fa01651cd36f3877242a0cc35cf306621d2236db205e9b3718d91'
DOSBOX_SHA256 = 'bfdacbed027ae16f48256abc5d0309cc8984569a2946dabea2f4d43907d43e71'
QEMU_SHA256 = 'b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af'
QEMU_IMG_SHA256 = 'b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03'
BOOT_SHA256 = '552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc'
WAITS_MS = (25, 35, 45, 55, 65, 75, 85, 95)
PROFILE = ('dosbox machine=svga_s3', 'cpu core=normal', 'cpu cycles=fixed 157600',
           'render frameskip=0', 'render doublescan=false', 'render scaler=none',
           'video scanline render on demand=false', 'video vga palette update on full load=true',
           'video enable 8-bit dac=false')
WORK_SECONDS, CLEANUP_SECONDS = 50, 10
PUBLIC_CALL_LIMIT, NATIVE_CALL_LIMIT = 512, 1024
REPORT_LIMIT, LOG_LIMIT = 8 * 1024**2, 2 * 1024**2
BDA_ADDRESS, BDA_LENGTH = 0x46C, 5
HOST_CLOCK_FIELDS = frozenset({'sequence', 'host_monotonic_ns'})


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _error(error):
    return {'type': type(error).__name__, 'message': str(error),
            'notes': list(getattr(error, '__notes__', []))}


def _remaining(deadline, maximum=1000):
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining < 1:
        raise TimeoutError('Strict paired pause owner exhausted its work deadline')
    return min(maximum, remaining)


def _word(registers, *names):
    for name in names:
        for fields in (registers.get('registers', {}), registers.get('general', {}),
                       registers.get('segments', {})):
            if name in fields:
                value = fields[name]
                if type(value) is str:
                    value = int(value, 16)
                assert type(value) is int and value >= 0
                return value & 0xFFFF
    raise AssertionError('Missing observed CPU field: ' + '/'.join(names))


def _pair(registers):
    # Ignore no stopped-state field. This separate progress witness concerns
    # only the two words changed by the independent authored INC/INC loop.
    return [_word(registers, 'ax', 'eax', 'rax'), _word(registers, 'bx', 'ebx', 'rbx')]


def _ip(registers):
    value = registers['instruction_pointer']
    return int(value, 16) if type(value) is str else value


def _write_json(path, value):
    data = (json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False) + '\n').encode()
    assert len(data) <= REPORT_LIMIT, 'Strict pause evidence exceeded its byte budget'
    temporary = path.with_suffix(path.suffix + '.writing')
    temporary.write_bytes(data)
    temporary.replace(path)


@pytest.fixture(scope='module', autouse=True)
def require_owned_paired_pause_gate(request):
    if os.environ.get('FDISBULL_REQUIRE_PAIRED_PAUSE') != '1':
        pytest.skip('Requires the separately admitted two-owner strict pause gate')
    assert getattr(request.config, '_fdisbull_paired_pause_owned_gate', None) == 'fdisbull-paired-pause-owned-gate-1'
    assert request.config.option.maxfail == 1
    assert not getattr(request.config.option, 'numprocesses', None)
    assert sys.platform.startswith('linux'), 'The proposed owner/log policy is explicitly Linux'


@pytest.fixture
def paired_pause_runtime(tmp_path):
    for parent in (tmp_path.resolve(), *tmp_path.resolve().parents):
        assert not (parent / '.git').exists(), 'Private native output requires no Git ancestor'
    selected = {
        'dosbox': os.environ.get('FDISBULL_PAIRED_PAUSE_DOSBOX'),
        'dosbox_lib': os.environ.get('FDISBULL_PAIRED_PAUSE_DOSBOX_LIB'),
        'qemu': os.environ.get('FDISBULL_QEMU_DOS'),
        'qemu_img': os.environ.get('FDISBULL_QEMU_IMG'),
        'boot': os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE'),
        'mcopy': os.environ.get('FDISBULL_QEMU_DOS_MCOPY'),
        'firmware': os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'),
    }
    missing = [name for name, value in selected.items() if not value]
    if missing:
        pytest.fail('Required strict pause inputs missing: ' + ', '.join(missing))
    runtime = {name: Path(value).expanduser().absolute() for name, value in selected.items()}
    for name, path in runtime.items():
        directory = name in ('dosbox_lib', 'firmware')
        assert path.is_dir() if directory else path.is_file(), (name, path)
        if name != 'boot' and not directory:
            assert os.access(path, os.X_OK), (name, path)
    for name, expected in (('dosbox', DOSBOX_SHA256), ('qemu', QEMU_SHA256),
                           ('qemu_img', QEMU_IMG_SHA256), ('boot', BOOT_SHA256)):
        assert digest(runtime[name]) == expected, 'Wrong pinned pause input: ' + name
    runtime['disk'] = prepare_dos_baseline(runtime['boot'], tmp_path / 'pause-boot.img', runtime['mcopy'])
    wrapper = tmp_path / 'strict-pause-dosbox-profile'
    arguments = [item for setting in PROFILE for item in ('-set', setting)]
    wrapper.write_text('#!' + sys.executable + '\nimport os, sys\n'
        + f'native = {str(runtime["dosbox"])!r}\n'
        + "environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ', "
          "'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME') if key in os.environ}\n"
        + f'environment.update(LD_LIBRARY_PATH={str(runtime["dosbox_lib"])!r}, '
          "SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
        + f'os.execve(native, [native, *sys.argv[1:], *{arguments!r}], environment)\n')
    wrapper.chmod(0o700)
    runtime['wrapper'] = wrapper
    return runtime


class _Journal:
    def __init__(self, directory, backend):
        self.directory, self.backend = directory, backend
        self.deadline = time.monotonic() + WORK_SECONDS
        self.phase = 'constructor'
        self.value = {'backend': backend, 'phase': self.phase, 'calls': [], 'native_calls': [],
                      'episodes': [], 'complete': False, 'owner': {},
                      'fixture_sha256': FIXTURE_SHA256}

    def save(self):
        self.value['phase'] = self.phase
        _write_json(self.directory / 'pause-observations.json', self.value)

    def call(self, method, arguments, action, *, native=False):
        _remaining(self.deadline)
        rows = self.value['native_calls' if native else 'calls']
        assert len(rows) < (NATIVE_CALL_LIMIT if native else PUBLIC_CALL_LIMIT)
        row = {'index': len(rows), 'phase': self.phase, 'method': method,
               'arguments': deepcopy(arguments), 'host_before_ns': time.monotonic_ns()}
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
                primary.add_note('Strict pause journal retention failed: ' + repr(error))


def _save_logs(descriptors, directory):
    receipts = {}
    for name, descriptor in descriptors.items():
        size = os.fstat(descriptor).st_size
        assert size <= LOG_LIMIT, 'Native log exceeded its fixed budget'
        os.lseek(descriptor, 0, os.SEEK_SET)
        parts = []
        remaining = LOG_LIMIT + 1
        while remaining:
            part = os.read(descriptor, min(65536, remaining))
            if not part:
                break
            parts.append(part)
            remaining -= len(part)
        data = b''.join(parts)
        assert len(data) == size == os.fstat(descriptor).st_size
        with (directory / name).open('xb') as output:
            output.write(data)
        receipts[name] = {'bytes': len(data), 'sha256': _sha(data), 'complete_after_exit': True}
    return receipts


class _Dosbox:
    def __init__(self, rpc, journal, directory):
        self.rpc, self.journal, self.sid = rpc, journal, None
        journal.value.update(requested_profile=list(PROFILE), effective_profile_verified=False,
                             capabilities=deepcopy(rpc.capabilities), clock_domain='PIC_Ticks_milliseconds')
        assert rpc.capabilities.get('timing', {}).get('guest_clock') == 'PIC_Ticks_milliseconds'
        assert rpc.capabilities.get('timing', {}).get('fast_forward') is True
        start = self.call('session.start', {'target': {'command': 'PVERIFY.COM', 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(directory)}], 'break_at': 'entry'}, maximum=15000)
        assert start['state'] == 'stopped' and start['stop_reason']['kind'] == 'startup'
        self.sid = start['session_id']
        assert self.call('execution.timing', {'fast_forward': False})['fast_forward'] is False
        self.last_clock = None

    def call(self, method, params=None, *, maximum=1000):
        arguments = dict(params or {})
        if self.sid is not None:
            arguments['session_id'] = self.sid
        result = self.journal.call(method, arguments, lambda: self.rpc.call(
            method, arguments, timeout_ms=_remaining(self.journal.deadline, maximum)))
        assert self.sid is None or result.get('session_id') == self.sid
        return result

    def clock(self):
        value = self.call('execution.timing')
        assert type(value['guest_ticks']) is int and value['guest_ticks'] >= 0
        assert value['fast_forward'] is False
        return value

    def registers(self):
        return self.call('state.get_registers')

    def status(self):
        value = self.call('session.status')
        assert value['state'] == 'stopped'
        return value

    def memory(self, address, length):
        value = self.call('memory.read', {'address': {'space': 'physical', 'offset': f'0x{address:08x}'},
                                         'length': length})
        data = base64.b64decode(value['data_base64'], validate=True)
        assert len(data) == value['byte_count'] == length and _sha(data) == value['sha256']
        return value, data

    def run_pause(self, wait_ms, episode):
        self.journal.phase = f'episode-{len(self.journal.value["episodes"])}-running'
        running = episode['resume_ack'] = self.call('execution.continue')
        assert running.get('state') == 'running' and running.get('stop_reason') is None
        waited = episode['running_wait'] = self.call('execution.wait', {
            'operation_id': running['operation_id'], 'timeout_ms': wait_ms})
        assert waited.get('running') is True and waited.get('stop_reason') is None
        self.journal.phase = f'episode-{len(self.journal.value["episodes"])}-pause'
        try:
            acknowledgement = episode['pause_ack'] = self.call('execution.pause')
            operation = acknowledgement['operation_id']
        except ValueError as error:
            if not str(error).endswith('(TARGET_NOT_RUNNING)'):
                raise
            # Preserve the historical acknowledged-race path; do not send a
            # second pause or continue. The actual stop must still say pause.
            episode['pause_race'] = _error(error)
            operation = running['operation_id']
        stopped = episode['first_stop'] = self.call('execution.wait', {
            'operation_id': operation, 'timeout_ms': 500})
        assert stopped.get('running', False) is False and stopped['state'] == 'stopped'
        assert stopped['stop_reason']['kind'] == 'pause'
        self.journal.save()
        return stopped

    def compare(self, blocks, stop):
        first = blocks[0]
        for block in blocks:
            assert block == first, 'Legacy stopped clock/status/register/RAM drift'
            assert block['clock_before'] == block['clock_after']
            for name in ('clock_before', 'status', 'registers', 'code', 'bda', 'clock_after'):
                assert block[name]['state_revision'] == stop['state_revision']
            assert block['status']['last_stop'] == stop['stop_reason']
        return first['clock_before']['guest_ticks']


class _Qemu:
    def __init__(self, debug, journal):
        self.debug, self.journal, self.vm = debug, journal, debug.vm
        self.qmp, self.remote = self.vm.qmp, self.vm.gdb
        assert self.remote is not None and self.vm.process.poll() is None
        self.last_host_clock = None
        self.vm.operation_deadline = journal.deadline
        self.qmp.operation_deadline = self.remote.operation_deadline = journal.deadline
        journal.value.update(clock_domain='QEMU_CLOCK_VIRTUAL',
                             host_clock_bookkeeping_fields=sorted(HOST_CLOCK_FIELDS),
                             machine_configuration=deepcopy(self.vm.machine_configuration))

    def call(self, method, arguments=None):
        assert self.debug.vm is self.vm and self.vm.qmp is self.qmp and self.vm.gdb is self.remote
        assert self.vm.process.poll() is None
        return self.journal.call('public.' + method, arguments, lambda: getattr(self.debug, method)(**(arguments or {})))

    @contextmanager
    def native_trace(self):
        call, request, execute = self.qmp.call, self.remote.request, self.remote.execute

        def qmp(method, arguments=None, timeout_ms=30000, **kwargs):
            return self.journal.call('qmp.' + method,
                {'arguments': arguments, 'timeout_ms': timeout_ms, **kwargs},
                lambda: call(method, arguments, timeout_ms, **kwargs), native=True)

        def gdb(command, timeout_ms=10000):
            raw = command.encode('ascii') if type(command) is str else command
            reply = None

            def action():
                nonlocal reply
                reply = request(command, timeout_ms)
                return {'reply_hex': reply.hex()}

            self.journal.call('gdb.request', {'command_hex': raw.hex(), 'timeout_ms': timeout_ms}, action, native=True)
            return reply

        def run(command, timeout_ms, **kwargs):
            raw = command.encode('ascii') if type(command) is str else command
            reply = None

            def action():
                nonlocal reply
                reply = execute(command, timeout_ms, **kwargs)
                return {'reply_hex': reply[0].hex(), 'timed_out': reply[1]}

            self.journal.call('gdb.execute', {'command_hex': raw.hex(), 'timeout_ms': timeout_ms}, action, native=True)
            return reply

        self.qmp.call, self.remote.request, self.remote.execute = qmp, gdb, run
        try:
            yield
        finally:
            self.qmp.call, self.remote.request, self.remote.execute = call, request, execute

    def clock(self):
        value = self.call('clock_observe')
        assert value['format'] == 'fdisbull-machine-clock-1' and value['session']['state'] == 'stopped'
        assert type(value['virtual_ns']) is int and value['virtual_ns'] >= 0
        assert value['counter']['state'] == 'observed' and type(value['counter']['value']) is int
        assert value['virtual_clock']['domain'] == 'QEMU_CLOCK_VIRTUAL'
        assert value['virtual_clock']['native']['virtual-ns'] == value['virtual_ns']
        assert value['virtual_clock']['native']['budget-state'] == 'idle'
        assert type(value['sequence']) is int and type(value['host_monotonic_ns']) is int
        if self.last_host_clock is not None:
            assert value['sequence'] == self.last_host_clock['sequence'] + 1
            assert value['host_monotonic_ns'] >= self.last_host_clock['host_monotonic_ns']
            assert value['epoch'] == self.last_host_clock['epoch']
            assert value['virtual_clock']['native']['epoch'] == self.last_host_clock['virtual_clock']['native']['epoch']
        self.last_host_clock = value
        return value

    def registers(self):
        return self.call('registers')

    def status(self):
        value = self.call('status')
        assert value['state'] == 'stopped' and value['native_state']['running'] is False
        assert value['native_state']['status'] == 'paused'
        return value

    def memory(self, address, length):
        value = self.call('memory', {'address': address, 'length': length, 'space': 'physical'})
        data = bytes.fromhex(value['hex'])
        assert len(data) == value['length'] == length
        return value, data

    def run_pause(self, wait_ms, episode):
        self.journal.phase = f'episode-{len(self.journal.value["episodes"])}-running'
        native_begin = len(self.journal.value['native_calls'])
        resumed = episode['resume_result'] = self.call('resume')
        assert resumed['state'] == 'running' and resumed['native_state']['running'] is True
        assert resumed['native_state']['status'] == 'running'
        _remaining(self.journal.deadline)
        began = time.monotonic_ns()
        # This is the declared running interval, before pause. No sleep or
        # retry occurs after the actual stopped result or in a read bracket.
        time.sleep(wait_ms / 1000)
        episode['running_wait'] = {'requested_host_ms': wait_ms, 'host_before_ns': began,
                                   'host_after_ns': time.monotonic_ns()}
        self.journal.phase = f'episode-{len(self.journal.value["episodes"])}-pause'
        stopped = episode['first_stop'] = self.call('pause')
        assert stopped['state'] == 'stopped' and stopped['native_state']['running'] is False
        assert stopped['native_state']['status'] == 'paused'
        native = self.journal.value['native_calls'][native_begin:]
        acknowledgements = [row for row in native if row['method'] in ('qmp.cont', 'qmp.stop')]
        assert [row['method'] for row in acknowledgements] == ['qmp.cont', 'qmp.stop']
        assert all(row.get('reply') == {} for row in acknowledgements)
        episode['control_ack_native_indices'] = [row['index'] for row in acknowledgements]
        # The empty native stop acknowledgement is retained separately from
        # the actual query-status/public pause result. No operation ID exists.
        self.journal.save()
        return stopped

    def compare(self, blocks, stop):
        def guest_clock(clock):
            return {key: value for key, value in clock.items() if key not in HOST_CLOCK_FIELDS}

        first = blocks[0]
        reference = guest_clock(first['clock_before'])
        for block in blocks:
            for name in ('status', 'registers', 'code', 'bda'):
                assert block[name] == first[name], 'QEMU stopped ' + name + ' drift'
            assert guest_clock(block['clock_before']) == reference == guest_clock(block['clock_after']), 'QEMU guest clock drift'
            assert block['status']['native_state'] == stop['native_state']
        return first['clock_before']['virtual_ns']


def _campaign(adapter, journal):
    journal.phase = 'initial-stopped-reference'
    initial_clock = adapter.clock()
    initial_registers = adapter.registers()
    assert initial_registers['cpu_mode'] == 'real' and _ip(initial_registers) == 0x100
    source_address = _word(initial_registers, 'cs') * 16 + 0x100
    code, data = adapter.memory(source_address, len(BUSY_COM))
    assert data == BUSY_COM
    journal.value['initial'] = {'clock': initial_clock, 'registers': initial_registers, 'code': code}
    previous_pair = _pair(initial_registers)
    previous_clock = (initial_clock['guest_ticks'] if journal.backend == 'dosbox' else initial_clock['virtual_ns'])
    previous_counter = initial_clock.get('counter', {}).get('value')
    for number, wait_ms in enumerate(WAITS_MS, 1):
        episode = {'number': number, 'running_wait_ms': wait_ms, 'blocks': []}
        journal.value['episodes'].append(episode)
        stop = adapter.run_pause(wait_ms, episode)
        journal.phase = f'episode-{number}-immediate-observations'
        native_begin = len(journal.value['native_calls'])
        for _ in range(4):
            block = {}
            episode['blocks'].append(block)
            block['clock_before'] = adapter.clock()
            block['status'] = adapter.status()
            block['registers'] = adapter.registers()
            block['code'], code_bytes = adapter.memory(source_address, len(BUSY_COM))
            block['bda'], _ = adapter.memory(BDA_ADDRESS, BDA_LENGTH)
            block['clock_after'] = adapter.clock()
            # Shape/address/transport failures stop immediately. A valid
            # observed value mismatch is assessed only after all four blocks.
            assert len(code_bytes) == len(BUSY_COM)
        journal.save()
        current_clock = adapter.compare(episode['blocks'], stop)
        first = episode['blocks'][0]
        code_bytes = (base64.b64decode(first['code']['data_base64'], validate=True)
                      if journal.backend == 'dosbox' else bytes.fromhex(first['code']['hex']))
        assert code_bytes == BUSY_COM, 'Authored source RAM changed'
        current_pair = _pair(first['registers'])
        assert current_clock > previous_clock, 'Explicit running interval did not advance the observed guest clock'
        assert current_pair != previous_pair, 'Explicit running interval did not establish changed AX/BX'
        progress = {'clock_before': previous_clock, 'clock_after': current_clock,
                    'ax_bx_before': previous_pair, 'ax_bx_after': current_pair}
        if journal.backend == 'qemu':
            current_counter = first['clock_before']['counter']['value']
            assert current_counter > previous_counter, 'Explicit resume did not advance native icount'
            progress.update(icount_before=previous_counter, icount_after=current_counter)
            previous_counter = current_counter
            native = journal.value['native_calls'][native_begin:]
            assert not any(row['method'] in ('qmp.cont', 'qmp.stop', 'gdb.execute') for row in native)
            assert all(row['method'] in ('qmp.query-status', 'qmp.query-replay', 'qmp.x-fdisbull-query-clock',
                'qmp.human-monitor-command', 'gdb.request') for row in native)
            allowed_requests = {b'g', b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:0', b'Qqemu.PhyMemMode:1',
                                f'm{source_address:x},{len(BUSY_COM):x}'.encode(),
                                f'm{BDA_ADDRESS:x},{BDA_LENGTH:x}'.encode()}
            for row in native:
                if row['method'] == 'gdb.request':
                    assert bytes.fromhex(row['arguments']['command_hex']) in allowed_requests
                elif row['method'] == 'qmp.human-monitor-command':
                    assert row['arguments']['arguments'] == {'command-line': 'info registers'}
        episode.update(exact_stopped_equality=True, resumed_progress=progress)
        previous_pair, previous_clock = current_pair, current_clock
        journal.save()
    journal.value['complete'] = True


@contextmanager
def _owner(backend, directory, runtime, journal):
    source = directory / 'PVERIFY.COM'
    source.write_bytes(BUSY_COM)
    process, rpc, debug = None, None, None
    descriptors = {}
    cleanup_began = None
    try:
        if backend == 'dosbox':
            def spawned(value):
                nonlocal process
                assert process is None
                process = value
                journal.value['owner']['pid'] = value.pid
                descriptors['emulator.log'] = os.open(f'/proc/{value.pid}/fd/1', os.O_RDONLY)

            try:
                rpc = DOSBoxRPC(runtime['wrapper'], directory, on_spawn=spawned)
                yield _Dosbox(rpc, journal, directory)
            finally:
                cleanup_began = time.monotonic()
                if rpc is not None:
                    rpc.close()
        else:
            with Project.create(directory / 'pause.fdb', source, image='com') as project:
                with project.debugger(str(runtime['qemu']), directory, backend='qemu-dos',
                        dos_boot_image=str(runtime['disk']['image']), dos_mcopy=str(runtime['mcopy']),
                        dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
                        qemu_firmware=str(runtime['firmware']), qemu_checkpoint_tool=str(runtime['qemu_img']),
                        qemu_clock='virtual', qemu_retrace='precise',
                        boot_timeout_ms=_remaining(journal.deadline, 15000)) as debug:
                    process = debug.vm.process
                    journal.value['owner']['pid'] = process.pid
                    root = Path(debug.vm.temporary.name)
                    try:
                        for name in ('qemu.log', 'boot.log'):
                            descriptors[name] = os.open(root / name, os.O_RDONLY)
                        adapter = _Qemu(debug, journal)
                        with adapter.native_trace():
                            yield adapter
                    finally:
                        cleanup_began = time.monotonic()
    finally:
        primary = sys.exception()
        failure = None
        try:
            if process is not None:
                journal.value['owner'].update(reaped=process.poll() is not None, returncode=process.returncode,
                    cleanup_seconds=time.monotonic() - cleanup_began if cleanup_began else None)
                assert process.poll() is not None, 'Original pause owner was not reaped'
                if cleanup_began is not None:
                    assert journal.value['owner']['cleanup_seconds'] <= CLEANUP_SECONDS
            journal.value['logs'] = _save_logs(descriptors, directory)
            assert source.read_bytes() == BUSY_COM
        except BaseException as error:
            failure = error
            journal.value.setdefault('cleanup_errors', []).append(_error(error))
        finally:
            # This is the sole descriptor-close path, including when reaping
            # fails before _save_logs. The independent controller still owns
            # any uncertain native lifetime and its complete-log retention.
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
            primary.add_note('Strict pause owner cleanup/retention failed: ' + repr(failure))


def test_native_paired_strict_pause_keeps_immediate_clock_register_ram_brackets(tmp_path, paired_pause_runtime):
    runtime = paired_pause_runtime
    assert _sha(BUSY_COM) == FIXTURE_SHA256
    result = {'format': 'fdisbull-paired-strict-pause-1', 'complete': False,
              'fixture_sha256': FIXTURE_SHA256, 'running_waits_ms': list(WAITS_MS),
              'brackets_per_stop': 4, 'no_settling': True, 'allowed_guest_delta': 0,
              'owners': [], 'clock_domains_compared_numerically': False,
              'scope': 'Finite immediate stopped observations on the authored busy loop; no indefinite quiescence or game claim'}
    try:
        for backend in ('dosbox', 'qemu'):
            directory = tmp_path / backend
            directory.mkdir()
            journal = _Journal(directory, backend)
            result['owners'].append(journal.value)
            try:
                with _owner(backend, directory, runtime, journal) as adapter:
                    _campaign(adapter, journal)
            except BaseException as error:
                journal.value['failure'] = _error(error)
                try:
                    journal.save()
                except BaseException as retention:
                    error.add_note('Strict pause failure retention failed: ' + repr(retention))
                raise
            assert journal.value['complete'] and journal.value['owner']['reaped']
            assert len(journal.value['episodes']) == 8
        assert digest(runtime['boot']) == BOOT_SHA256
        assert digest(runtime['disk']['image']) == runtime['disk']['prepared_sha256']
        result['complete'] = True
    except BaseException as error:
        result['failure'] = _error(error)
        raise
    finally:
        primary = sys.exception()
        try:
            _write_json(tmp_path / 'paired-pause-result.json', result)
        except BaseException as error:
            if primary is None:
                raise
            primary.add_note('Strict paired pause result retention failed: ' + repr(error))
