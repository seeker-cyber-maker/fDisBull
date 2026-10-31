"""Native changing-source-frame acceptance using an authored DOS COM fixture.

No game assets, project database, host framebuffer, or mocked renderer is used.
The host stops at guest execution checkpoints; wall time is only a timeout.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC, DebuggerError


FIXTURE_SOURCE = Path(__file__).with_name('fixtures') / 'frame_capture.S'
# Filled from the locally assembled, disassembled authored source. This binds
# the tested machine code to its auditable source independently of the backend.
FIXTURE_SHA256 = 'ee0cd3b04c11686cdcf4eeac90611839683263e14cc4be77bd29b3a2b2009983'
CHECKPOINT = 0x600
RESUME = CHECKPOINT + 1
STATUS = 0x800
FIELDS = ('version', 'phase', 'drawn_sequence', 'completed_sequence',
          'retrace_count', 'remaining', 'checkpoint_count', 'fault')
STATUS_SIZE = 4 + 2 * len(FIELDS)
WARMUP = 3
QUOTA = 17
PROFILE = ('cpu core=normal', 'cpu cycles=fixed 157600',
           'render frameskip=0', 'render doublescan=false',
           'render scaler=none')
POINTS = [[x, y] for y in (0, 100, 199) for x in range(8)] + [
    [8, 0], [160, 100], [319, 199]]


def _assemble_fixture(directory):
    assembler, linker = shutil.which('as'), shutil.which('ld')
    if not assembler or not linker:
        pytest.fail('Native frame regression requires GNU as and ld (binutils)')
    obj, binary = directory / 'frame_capture.o', directory / 'FRAMEVID.COM'
    subprocess.run([assembler, '--32', '-o', str(obj), str(FIXTURE_SOURCE)],
                   check=True, capture_output=True, text=True)
    subprocess.run([linker, '-m', 'elf_i386', '--oformat', 'binary',
                    '-Ttext', '0x100', '-e', '_start', '-o', str(binary), str(obj)],
                   check=True, capture_output=True, text=True)
    data = binary.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
    assert data[CHECKPOINT - 0x100] == 0x90
    assert data[STATUS - 0x100:STATUS - 0x100 + 4] == b'FVID'
    assert len(data) == STATUS - 0x100 + STATUS_SIZE
    return binary


@pytest.fixture
def frame_backend(request):
    configured = os.environ.get('FDISBULL_DOSBOX')
    if not configured:
        if request.config.getoption('--require-native', default=False):
            pytest.fail('Native frame regression requires FDISBULL_DOSBOX')
        pytest.skip('Set FDISBULL_DOSBOX for native changing-frame acceptance')
    backend = Path(configured).expanduser().resolve(strict=True)
    if not backend.is_file() or not os.access(backend, os.X_OK):
        pytest.fail('FDISBULL_DOSBOX must name an executable backend')
    return backend


def _profile_wrapper(directory, backend):
    # DOSBoxRPC owns the process/pipes. This authored executable appends only
    # this test's declared fixed profile, then replaces itself with the backend.
    wrapper = directory / 'fixed-frame-profile'
    extra = [part for setting in PROFILE for part in ('-set', setting)]
    wrapper.write_text('#!' + sys.executable + '\nimport os, sys\n'
                       + f'backend = {str(backend)!r}\n'
                       + f'os.execv(backend, [backend, *sys.argv[1:], *{extra!r}])\n')
    wrapper.chmod(0o700)
    return wrapper


class FixtureSession:
    def __init__(self, rpc, game_dir):
        self.rpc = rpc
        started = rpc.call('session.start', {
            'target': {'command': 'FRAMEVID.COM', 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(game_dir)}],
            'break_at': 'entry'})
        self.sid = started['session_id']
        registers = self.call('state.get_registers')
        assert registers['cpu_mode'] == 'real'
        assert int(registers['instruction_pointer'], 16) == 0x100
        self.cs = registers['segments']['cs']
        self.call('execution.timing', {'fast_forward': False})

    def call(self, method, params=None):
        return self.rpc.call(method, {'session_id': self.sid, **(params or {})})

    def address(self, offset):
        return {'space': 'segmented', 'segment': self.cs, 'offset': f'0x{offset:08X}'}

    def read(self, offset, length):
        result = self.call('memory.read', {'address': self.address(offset), 'length': length})
        data = base64.b64decode(result['data_base64'], validate=True)
        assert len(data) == length
        assert hashlib.sha256(data).hexdigest() == result['sha256']
        return data

    def write_word(self, name, value):
        offset = STATUS + 4 + FIELDS.index(name) * 2
        old = self.read(offset, 2)
        self.call('memory.write', {'address': self.address(offset),
                  'expected_sha256': hashlib.sha256(old).hexdigest(),
                  'data_base64': base64.b64encode(struct.pack('<H', value)).decode('ascii')})

    def status(self):
        data = self.read(STATUS, STATUS_SIZE)
        assert data[:4] == b'FVID'
        status = dict(zip(FIELDS, struct.unpack('<' + 'H' * len(FIELDS), data[4:])))
        assert status['version'] == 1 and status['fault'] == 0, status
        return status

    def breakpoint(self):
        return self.call('breakpoints.create', {'kind': 'execution',
                         'address': self.address(CHECKPOINT), 'once': False})['breakpoint_id']

    def delete(self, breakpoint_id):
        self.call('breakpoints.delete', {'breakpoint_id': breakpoint_id})

    def run_to_checkpoint(self, breakpoint_id):
        before = self.call('execution.timing')
        operation = self.call('execution.continue')
        deadline = time.monotonic() + 20
        result = None
        while time.monotonic() < deadline:
            result = self.call('execution.wait', {'operation_id': operation['operation_id'],
                                                 'timeout_ms': 500})
            if not result.get('running'):
                break
        if result is None or result.get('running'):
            pause = self.call('execution.pause')
            paused = self.call('execution.wait', {'operation_id': pause['operation_id'],
                                                'timeout_ms': 3000})
            pytest.fail(f'Guest failed to reach authored frame checkpoint: {paused}')
        assert result['stop_reason']['kind'] == 'breakpoint', result
        assert result['stop_reason']['breakpoint_id'] == breakpoint_id, result
        registers = self.call('state.get_registers')
        assert int(registers['instruction_pointer'], 16) == CHECKPOINT, registers
        after = self.call('execution.timing')
        assert after['guest_ticks'] > before['guest_ticks'], (before, after)
        return {'before': before, 'after': after, 'stop': result}

    def probe(self):
        return self.call('video.probe', {'points': POINTS})

    def step_checkpoint(self):
        result = self.call('execution.step', {'mode': 'into'})
        # Current native into-step completes synchronously; retain explicit
        # bounded waiting for a backend returning an asynchronous operation.
        if result.get('operation_id'):
            result = self.call('execution.wait', {'operation_id': result['operation_id'],
                                                 'timeout_ms': 3000})
            assert not result.get('running'), result
            assert result.get('stop_reason', {}).get('kind') == 'step', result
        registers = self.call('state.get_registers')
        assert int(registers['instruction_pointer'], 16) == RESUME, registers
        return registers

    def screenshot(self):
        result = self.call('video.screenshot')
        assert result['format'] == 'png'
        data = base64.b64decode(result.pop('png_base64'), validate=True)
        assert hashlib.sha256(data).hexdigest() == result['sha256']
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            assert image.size == (320, 200)
        return result, data


def _assert_pattern(frame, phase, sequence):
    assert (frame['width'], frame['height']) == (320, 200), frame
    assert frame['source'] == 'last_completed_guest_frame'
    assert [(p['x'], p['y']) for p in frame['samples']] == [tuple(p) for p in POINTS]
    for sample in frame['samples']:
        x, y = sample['x'], sample['y']
        painted = x < 8 and (y == 0 or phase == 2)
        expected = ([0, 255, 0] if sequence & (1 << x) else [255, 0, 0]) if painted else [0, 0, 0]
        assert sample['rgb'] == expected, (phase, sequence, sample, expected, frame['frame_id'])


def _assert_progress(status, phase, *, retraces, checkpoints, sequence):
    assert status == {'version': 1, 'phase': phase, 'drawn_sequence': sequence,
                      'completed_sequence': sequence, 'retrace_count': retraces,
                      'remaining': 0, 'checkpoint_count': checkpoints, 'fault': 0}, status


def _stopped_read_check(session, frame, directory):
    before = (session.call('state.get_registers'), session.status(), session.call('execution.timing'))
    first_meta, first_png = session.screenshot()
    repeated_probe = session.probe()
    second_meta, second_png = session.screenshot()
    after = (session.call('state.get_registers'), session.status(), session.call('execution.timing'))
    assert before == after, 'Stopped frame observation advanced guest state or time'
    assert repeated_probe == frame, 'Stopped probe changed the cached frame'
    assert first_meta == second_meta and first_png == second_png
    for field in ('frame_id', 'mode_id', 'captured_ticks', 'width', 'height', 'source_bpp'):
        assert first_meta[field] == frame[field]
    (directory / 'restored-frame.png').write_bytes(first_png)
    return first_meta


def _export_evidence(directory, phase):
    """Copy only this authored fixture's generic receipts, never native states."""
    configured = os.environ.get('FDISBULL_FRAME_EVIDENCE')
    if not configured:
        return
    root = Path(configured).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f'phase-{phase}-', dir=root))
    for name in ('frame-regression.json', 'emulator.log', 'restored-frame.png'):
        source = directory / name
        if source.is_file():
            shutil.copyfile(source, output / name)


@pytest.mark.parametrize('phase', [1, 2], ids=['changed-first-row', 'changed-every-row'])
def test_changed_source_frames_refresh_after_restore(tmp_path, frame_backend, phase, record_property):
    game_dir = tmp_path / 'guest'
    game_dir.mkdir()
    binary = _assemble_fixture(game_dir)
    wrapper = _profile_wrapper(tmp_path, frame_backend)
    report = {'format': 'fdisbull-authored-frame-regression-1', 'phase': phase,
              'fixture_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'fixture_source_sha256': hashlib.sha256(FIXTURE_SOURCE.read_bytes()).hexdigest(),
              'fixture_test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'backend_sha256': hashlib.sha256(frame_backend.read_bytes()).hexdigest(),
              'profile': list(PROFILE), 'quota_guest_retraces': QUOTA,
              'frame_id_semantics': 'accepted agent snapshot sequence, not retraces or AVI frames',
              'passed': False}
    record_property('fixture_sha256', report['fixture_sha256'])
    record_property('backend_sha256', report['backend_sha256'])
    rpc = None
    session = None
    try:
        rpc = DOSBoxRPC(wrapper, game_dir)
        assert rpc.capabilities.get('save_states'), rpc.capabilities
        session = FixtureSession(rpc, game_dir)
        bp = session.breakpoint()
        report['warmup_run'] = session.run_to_checkpoint(bp)
        report['warmup_status'] = session.status()
        _assert_progress(report['warmup_status'], 0, retraces=WARMUP, checkpoints=1, sequence=0)
        baseline = session.probe()
        _assert_pattern(baseline, 0, 0)
        report['baseline_frame'] = baseline

        # Save beyond the checkpoint instruction; native restore clears the
        # last-breakpoint suppression state and must not immediately re-hit it.
        session.delete(bp)
        session.write_word('phase', phase)
        session.write_word('remaining', QUOTA)
        armed = session.status()
        saved_registers = session.step_checkpoint()
        assert session.status() == armed
        checkpoint = (tmp_path / 'animated.sav').resolve()
        session.call('state.save', {'path': str(checkpoint)})
        assert checkpoint.is_file() and checkpoint.stat().st_size > 0
        report['checkpoint_sha256'] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        report['saved_status'] = armed

        bp = session.breakpoint()
        report['first_run'] = session.run_to_checkpoint(bp)
        report['first_status'] = session.status()
        _assert_progress(report['first_status'], phase, retraces=WARMUP + QUOTA,
                         checkpoints=2, sequence=QUOTA)
        # Record stale/absent first-run frames, then still exercise restore.
        try:
            report['first_frame'] = session.probe()
        except DebuggerError as error:
            report['first_frame_error'] = str(error)

        session.delete(bp)
        session.call('state.load', {'path': str(checkpoint)})
        restored_registers = session.call('state.get_registers')
        for field in ('cpu_mode', 'general', 'segments', 'instruction_pointer', 'flags'):
            assert restored_registers[field] == saved_registers[field], field
        assert session.status() == armed
        with pytest.raises(DebuggerError, match='No complete framebuffer') as invalidated:
            session.probe()
        report['immediate_restore_probe_error'] = str(invalidated.value)

        bp = session.breakpoint()
        report['restored_run'] = session.run_to_checkpoint(bp)
        report['restored_status'] = session.status()
        _assert_progress(report['restored_status'], phase, retraces=WARMUP + QUOTA,
                         checkpoints=2, sequence=QUOTA)
        try:
            frame = session.probe()
        except DebuggerError as error:
            report['restored_frame_error'] = str(error)
            pytest.fail('Completed authored changing frames remain unavailable after restore: ' + str(error))
        report['restored_frame'] = frame
        _assert_pattern(frame, phase, QUOTA)
        assert frame['frame_id'] > baseline['frame_id'], report
        assert frame['mode_id'] != baseline['mode_id'], report
        timing = report['restored_run']
        assert timing['before']['guest_ticks'] <= frame['captured_ticks'] <= timing['after']['guest_ticks']
        report['stopped_screenshot'] = _stopped_read_check(session, frame, tmp_path)
        assert 'first_frame' in report, report
        _assert_pattern(report['first_frame'], phase, QUOTA)
        assert report['first_frame']['frame_id'] > baseline['frame_id'], report
        report['passed'] = True
    finally:
        cleanup_error = None
        if rpc is not None:
            try:
                if session is not None:
                    stopped = session.call('session.stop')
                    report['cleanup'] = (session.call('execution.wait', {
                        'operation_id': stopped['operation_id'], 'timeout_ms': 3000})
                        if stopped.get('operation_id') else stopped)
                    assert not report['cleanup'].get('running'), report['cleanup']
            except Exception as error:
                cleanup_error = error
                report['cleanup_error'] = repr(cleanup_error)
            finally:
                if rpc.temporary is not None:
                    log = Path(rpc.temporary.name) / 'emulator.log'
                    if log.exists():
                        (tmp_path / 'emulator.log').write_bytes(log.read_bytes())
                rpc.close()
                report['process_reaped'] = rpc.process is None or rpc.process.poll() is not None
        passed_before_cleanup = report['passed']
        if cleanup_error is not None:
            report['passed'] = False
        (tmp_path / 'frame-regression.json').write_text(json.dumps(report, indent=2) + '\n')
        _export_evidence(tmp_path, phase)
        if passed_before_cleanup and cleanup_error is not None:
            raise AssertionError('Native frame assertions passed but cleanup failed') from cleanup_error
