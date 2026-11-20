"""Independent authored native stop witnesses for the next source raster.

This is a separate opt-in fence slice. Expected source times and pixels derive
from authored VGA state, not candidate-returned deadlines. Real GDB execution,
IRQ journals and instruction-after-OUT markers qualify stop behavior. The
authored tracker case does not qualify DESQview/provider discovery.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import uuid

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from support.dos_process_fixture import digest
from support.qemu_video_frame_fence_fixture import FENCE_COMMANDS, fence_program
from support.qemu_video_frame_fixture import expected_rgb, frame_schedule, guest_video_timing
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, create_project, launch_options, process_record, read_bytes
from test_qemu_video_frame_native import (
    _advance_to, _assert_frame, _clock_equal, _export, _later, _query,
)


ARM = 'x-fdisbull-arm-video-frame'
FENCE_QUERY = 'x-fdisbull-query-video-frame-fence'
CANCEL = 'x-fdisbull-cancel-video-frame-fence'
SOURCE_START = 'x-fdisbull-start-video-frame'
SOURCE_STOP = 'x-fdisbull-stop-video-frame'
FENCE_MODEL = 'qemu-video-frame-fence-v1'


@pytest.fixture
def fence_witness(tmp_path, clock_runtime, clock_disk, record_property):
    serial = 0

    @contextmanager
    def launch():
        nonlocal serial
        serial += 1
        directory = tmp_path / f'source-fence-{serial}'
        directory.mkdir()
        code, offsets = fence_program(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        record_property('authored_fence_com_sha256', hashlib.sha256(code).hexdigest())
        record_property('fence_oracle', 'guest VGA timing/RGB, actual GDB packets, instruction and IRQ journals')
        record_property('legacy_phase_equivalence', 'unqualified; fixed native source-row model only')
        debug = None
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                qemu_clock='virtual', qemu_retrace='precise')) as debug:
                        assert {ARM, FENCE_QUERY, CANCEL} <= set(debug.vm.qmp_commands)
                        info = process_record(debug)
                        symbols = {name: com_address(info, offset) for name, offset in offsets.items()}
                        park(debug, symbols['ready'])
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def _start(debug, symbols):
    # Read independently authored timing BEFORE starting the stream. The
    # returned native deadline never selects a row, expected pixel or stop.
    timing = guest_video_timing(read_bytes(debug, symbols['timing_raw'], 11))
    before = debug.clock_observe()
    started = debug.video_frame_start()
    native = started['native']
    assert started['format'] == 'fdisbull-video-frame-stream-1'
    assert native == _query(debug) and native['state'] == 'observing'
    assert native.get('frame') is None and native['rows-sampled'] == 0
    assert native['virtual-ns'] == native['start-ns'] == before['virtual_ns']
    _clock_equal(before, debug.clock_observe())
    return native, frame_schedule(timing, before['virtual_ns'])


def _byte(debug, symbols, name):
    return read_bytes(debug, symbols[name], 1)[0]


def _dword(debug, symbols, name):
    return int.from_bytes(read_bytes(debug, symbols[name], 4), 'little')


def _journal(debug, symbols):
    count = _byte(debug, symbols, 'scan_count')
    assert count <= 32 and _byte(debug, symbols, 'scan_overflow') == 0
    return read_bytes(debug, symbols['scan_codes'], count) if count else b''


def _save(project, name, **evidence):
    path = Path(project.path).parent / (name + '.json')
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


def _request(debug, symbols, name):
    value, _ = FENCE_COMMANDS[name]
    assert _byte(debug, symbols, 'command') == 0
    debug.write_memory(symbols['command'], bytes([value]).hex(), expected_hex='00')


def _guest_command(debug, symbols, name):
    before = debug.clock_observe()
    _request(debug, symbols, name)
    park(debug, symbols[FENCE_COMMANDS[name][1]])
    assert _byte(debug, symbols, 'command') == 0
    return before, debug.clock_observe()


def _arm_arguments(source, *, token=None):
    return {'token': token or uuid.uuid4().hex, 'stream-token': source['token'],
            'expected-stream-generation': source['stream-generation'],
            'expected-frame-sequence': source['frame-sequence'], 'expected-epoch': source['epoch']}


def _arm(debug):
    source, clock = _query(debug), debug.clock_observe()
    receipt = debug.vm.qmp.call(ARM, _arm_arguments(source))
    assert receipt['api-version'] == 1 and receipt['model'] == FENCE_MODEL
    assert receipt['state'] == 'armed' and not receipt['released']
    assert not receipt['stop-pending'] and not receipt['stop-consumed']
    assert receipt['stream-token'] == source['token']
    assert receipt['stream-generation'] == source['stream-generation']
    assert receipt['epoch'] == source['epoch']
    assert receipt['baseline-frame-sequence'] == source['frame-sequence']
    assert receipt['baseline-rows-sampled'] == source['rows-sampled']
    assert receipt['armed-ns'] == clock['virtual_ns']
    assert receipt['configuration-generation'] > 0 and receipt['timing-generation'] > 0
    assert receipt.get('completed-frame') is None
    return receipt


def _fence(debug, token):
    return debug.vm.qmp.call(FENCE_QUERY, {'token': token})


def _release(debug, receipt):
    token = receipt['token']
    result = debug.vm.qmp.call(CANCEL, {'token': token})
    expected = dict(receipt, released=True, **{'stop-pending': False})
    if receipt['state'] == 'armed':
        expected['state'] = 'cancelled'
    assert result == expected
    assert _fence(debug, token) == debug.vm.qmp.call(CANCEL, {'token': token}) == result
    return result


def _raw_run(debug):
    arm = _arm(debug)
    result = debug.run(timeout_ms=5000, stop_on_hook=True)
    observed = _fence(debug, arm['token'])
    assert not result['timed_out'] and result['session']['state'] == 'stopped'
    released = _release(debug, observed)
    return result, arm, observed, released


def _ordinary_completed(debug, native_result, arm, observed, schedule):
    assert native_result['outcome'] == 'stopped'
    assert native_result['session']['stop_reason']['native_reply'][:3] in ('S02', 'T02')
    assert observed['state'] == 'completed' and observed['stop-consumed'] is True
    assert not observed['stop-pending']
    frame = observed['completed-frame']
    assert frame['frame-id'] == arm['baseline-frame-sequence'] + 1
    for key in ('epoch', 'stream-generation', 'configuration-generation', 'timing-generation'):
        assert frame[key] == arm[key] == observed[key]
    stopped = debug.clock_observe()['virtual_ns']
    assert observed['stop-ns'] == stopped
    assert frame['completed-ns'] <= stopped < _later(schedule)['rows'][0]
    return frame


def _image(project, debug, schedule, expected):
    source = _query(debug)
    frame = _assert_frame(source, schedule, expected)
    actual = _export(debug, source)
    directory = Path(project.path).parent
    (directory / f'expected-frame-{frame["frame-id"]}.rgb').write_bytes(expected)
    (directory / f'actual-frame-{frame["frame-id"]}.rgb').write_bytes(actual)
    assert actual == expected
    return frame


def _public(debug, *, completed, accepted, consumed, stop_on_hook=True):
    before, clock = _query(debug), debug.clock_observe()
    result = debug.video_frame_advance(timeout_ms=5000, stop_on_hook=stop_on_hook)
    assert result['format'] == 'fdisbull-video-frame-advance-1'
    assert result['advance_completed'] is completed
    assert result['completed_source_raster'] is accepted
    assert result['stop_consumed'] is consumed
    assert result['outcome'] == result['native_result']['outcome']
    assert not result['native_result']['timed_out']
    assert result['stream'] == before['token'] and result['stream_generation'] == before['stream-generation']
    assert result['baseline_frame_sequence'] == before['frame-sequence']
    assert result['source']['before'] == before and result['source']['after'] == _query(debug)
    _clock_equal(clock, result['clocks']['before'])
    _clock_equal(debug.clock_observe(), result['clocks']['after'])
    for field in ('legacy_phase_equivalence', 'application_frame_complete', 'frame_state_equivalence'):
        assert result[field] is None
    fence = result['fence']
    assert fence['arm']['state'] == 'armed' and fence['released']['released'] is True
    assert fence['arm']['model'] == FENCE_MODEL and fence['arm']['api-version'] == 1
    for receipt_key, source_key in (('stream-token', 'token'), ('stream-generation', 'stream-generation'),
                                    ('epoch', 'epoch'), ('baseline-frame-sequence', 'frame-sequence'),
                                    ('baseline-rows-sampled', 'rows-sampled')):
        assert fence['arm'][receipt_key] == before[source_key]
    assert fence['arm']['armed-ns'] == clock['virtual_ns']
    assert not fence['released']['stop-pending']
    assert fence['observed']['stop-consumed'] is consumed
    assert result['frame'] == fence['observed'].get('completed-frame')
    assert fence['released'].get('completed-frame') == result['frame']
    assert fence['released']['stop-consumed'] == consumed
    expected_release = dict(fence['observed'], released=True, **{'stop-pending': False})
    if expected_release['state'] == 'armed':
        expected_release['state'] = 'cancelled'
    assert fence['released'] == expected_release
    return result


@contextmanager
def _actual_gdb_sends(debug, monkeypatch):
    """Observe the real transport; never replace a stop or execute result."""
    remote, calls = debug.vm.gdb, []
    original = remote.execute

    def execute(command, timeout_ms, **kwargs):
        row = dict(command=command, timeout_ms=timeout_ms)
        calls.append(row)
        reply, timed_out = original(command, timeout_ms, **kwargs)
        row.update(reply=reply.decode('ascii'), timed_out=timed_out)
        return reply, timed_out

    with monkeypatch.context() as patch:
        patch.setattr(remote, 'execute', execute)
        yield calls


def _neutral_hook(debug, address):
    registers = debug.registers()['registers']
    name = 'ebx' if 'ebx' in registers else 'rbx'
    value = int(registers[name], 16)
    return debug.hook(address, space='linear', once=False, max_hits=2,
        actions=[{'op': 'registers', 'registers': {name: {'expected': value, 'value': value}}}])


def _aborted_step(debug, symbols, result, before, *, commands, calls):
    assert result['outcome'] == 'step'
    assert result['native_result']['session']['stop_reason']['native_reply'][:3] in ('S05', 'T05')
    assert [row['command'] for row in calls] == commands
    assert all(not row['timed_out'] and row['reply'][:3] in ('S05', 'T05') for row in calls)
    assert int(debug.registers()['linear_pc'], 16) == symbols['abort_after']
    assert _byte(debug, symbols, 'after_abort') == 0
    assert _journal(debug, symbols) == b''
    observed = result['fence']['observed']
    assert observed['state'] == 'aborted' and observed['reason']
    assert not observed['stop-pending'] and not observed['stop-consumed']
    assert result['frame'] is None and observed.get('completed-frame') is None
    assert _query(debug)['state'] == 'invalidated' and _query(debug).get('frame') is None
    clock = debug.clock_observe()
    assert before['virtual_ns'] < clock['virtual_ns'] == observed['stop-ns']
    assert clock['counter']['value'] > before['counter']['value']


class _AuthoredTracker:
    """Approved provider seam; every breakpoint and displaced step is real."""
    def __init__(self):
        self.internal_breakpoints = set()
        self.events = []
        self.provider = object()

    def before_execution(self, reason):
        self.events.append(dict(operation='before', reason=reason))

    def after_stop(self, reason):
        self.events.append(dict(operation='after', reason=reason))

    def internal_stop(self, event):
        self.events.append(dict(operation='internal', event=deepcopy(event)))
        matched = set(event['breakpoints'])
        return bool(matched) and matched <= self.internal_breakpoints

    def status(self):
        return dict(enabled=True, provider='authored-stop-recorder')

    def close(self, reason):
        self.events.append(dict(operation='close', reason=reason))


def test_native_source_fence_passive_cas_and_release(fence_witness, monkeypatch):
    with fence_witness() as (project, debug, symbols):
        _, schedule = _start(debug, symbols)
        native, arm, completed, _ = _raw_run(debug)
        _ordinary_completed(debug, native, arm, completed, schedule)
        _image(project, debug, schedule, expected_rgb())
        source, clock, registers = _query(debug), debug.clock_observe(), debug.registers()
        keys = debug.vm.qmp.call('x-fdisbull-query-frame-keys')
        for field, value in (
            ('expected-epoch', source['epoch'] + 1),
            ('expected-stream-generation', source['stream-generation'] + 1),
            ('expected-frame-sequence', source['frame-sequence'] + 1),
            ('stream-token', uuid.uuid4().hex),
        ):
            arguments = _arm_arguments(source)
            arguments[field] = value
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(ARM, arguments)
            assert _query(debug) == source
        active = _arm(debug)
        for command, arguments in (
            (ARM, _arm_arguments(source)),
            (FENCE_QUERY, {'token': uuid.uuid4().hex}),
            (CANCEL, {'token': uuid.uuid4().hex}),
            (SOURCE_START, {'token': uuid.uuid4().hex}),
            (SOURCE_STOP, {'token': source['token']}),
        ):
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(command, arguments)
            assert _fence(debug, active['token']) == active
        assert _export(debug, source) == expected_rgb()
        probe = debug.vm.qmp.call('x-fdisbull-probe-video-frame', {
            'token': source['token'], 'frame-id': source['frame']['frame-id'],
            'points': [{'x': 10, 'y': 10}, {'x': 319, 'y': 199}],
        })
        assert probe['info'] == source
        assert probe['pixels'] == [dict(x=10, y=10, r=4, g=85, b=170),
                                   dict(x=319, y=199, r=0, g=255, b=0)]
        cancelled = _release(debug, active)
        assert cancelled['state'] == 'cancelled' and cancelled.get('completed-frame') is None
        assert _query(debug) == source and debug.registers() == registers
        assert debug.vm.qmp.call('x-fdisbull-query-frame-keys') == keys
        _clock_equal(clock, debug.clock_observe())
        # Reset retires both old authorities. Observe the actual event and
        # changed native epoch; system_reset's command reply is insufficient.
        reset_arm = _arm(debug)
        before_reset = debug.vm.qmp.call('x-fdisbull-query-clock')
        reads = []
        original_read = debug.vm.qmp._read

        def read(*args, **kwargs):
            reply = original_read(*args, **kwargs)
            reads.append(deepcopy(reply))
            return reply

        debug.vm.qmp.call('set-action', {'reboot': 'reset'}, timeout_ms=1000)
        deadline = time.monotonic() + 2
        with monkeypatch.context() as patch:
            patch.setattr(debug.vm.qmp, '_read', read)
            debug.vm.qmp.call('system_reset', timeout_ms=1000)
            reset = None
            for _ in range(16):
                remaining = int((deadline - time.monotonic()) * 1000)
                assert remaining > 0, reads
                reset = debug.vm.qmp.call('x-fdisbull-query-clock', timeout_ms=min(1000, remaining))
                if (any(reply.get('event') == 'RESET' for reply in reads)
                        and reset['epoch'] != before_reset['epoch']):
                    break
            assert any(reply.get('event') == 'RESET' for reply in reads), reads
            assert reset['epoch'] != before_reset['epoch'], reset
        assert reset['budget-state'] == 'invalidated' and reset['budget-supported'] is False
        for command, arguments in (
            (FENCE_QUERY, {'token': reset_arm['token']}),
            (CANCEL, {'token': reset_arm['token']}),
            (SOURCE_STOP, {'token': source['token']}),
            ('x-fdisbull-export-video-frame', {'token': source['token'],
             'frame-id': source['frame']['frame-id'],
             'filename': str(Path(project.path).parent / 'retired-frame.ppm')}),
        ):
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(command, arguments, timeout_ms=1000)
        assert not (Path(project.path).parent / 'retired-frame.ppm').exists()
        _save(project, 'reset-retirement', before=before_reset, after=reset,
              real_qmp_reads=reads, old_source=source, old_fence=reset_arm,
              scope='stopped reset retirement only; base clock remains invalid')


def test_native_source_fence_next_raster_and_prearm_rows(fence_witness):
    with fence_witness() as (project, debug, symbols):
        _, schedule = _start(debug, symbols)
        prior_id = None
        for index in range(2):
            selected = _later(schedule, index)
            native, arm, observed, _ = _raw_run(debug)
            frame = _ordinary_completed(debug, native, arm, observed, selected)
            assert frame == _image(project, debug, selected, expected_rgb())
            if prior_id is not None:
                assert frame['frame-id'] == prior_id + 1
            prior_id = frame['frame-id']
        selected = _later(schedule, 2)
        previous, following = selected['rows'][99:101]
        _advance_to(debug, following - selected['line_ns'] // 2)
        assert _query(debug)['rows-sampled'] == 100
        before, after = _guest_command(debug, symbols, 'mutate')
        assert previous < before['virtual_ns'] <= after['virtual_ns'] < following
        native, arm, observed, _ = _raw_run(debug)
        assert arm['baseline-rows-sampled'] == 100
        frame = _ordinary_completed(debug, native, arm, observed, selected)
        expected = expected_rgb(split_row=100, changed_vram=True)
        assert frame == _image(project, debug, selected, expected)
        assert frame['frame-id'] == prior_id + 1
        assert expected != expected_rgb(split_row=0, changed_vram=True)
        assert expected != expected_rgb(split_row=100, changed_vram=True, wrong_qemu_dac=True)


def test_native_source_fence_halted_cpu_has_no_late_warp(fence_witness):
    with fence_witness() as (project, debug, symbols):
        _guest_command(debug, symbols, 'halt')
        _, schedule = _start(debug, symbols)
        native, arm, observed, _ = _raw_run(debug)
        frame = _ordinary_completed(debug, native, arm, observed, schedule)
        assert frame == _image(project, debug, schedule, expected_rgb())
        assert _byte(debug, symbols, 'halt_wakes') == 0
        assert _journal(debug, symbols) == b''
        before = debug.clock_observe()
        delta = schedule['period_ns'] * 2
        budget_receipt(debug.clock_advance(delta, timeout_ms=5000), delta, before=before)
        after = debug.clock_observe()
        assert after['counter']['value'] == before['counter']['value']
        assert _byte(debug, symbols, 'halt_wakes') == 0
        assert _query(debug)['frame-sequence'] == frame['frame-id'] + 2


def test_native_source_fence_preserves_early_breakpoint_and_hook(fence_witness, monkeypatch):
    with fence_witness() as (project, debug, symbols):
        for kind in ('breakpoint', 'hook'):
            park(debug, symbols['loop_start'])
            started, schedule = _start(debug, symbols)
            point = (debug.breakpoint(symbols['hook_site']) if kind == 'breakpoint'
                     else _neutral_hook(debug, symbols['hook_site']))
            before = _dword(debug, symbols, 'iterations')
            try:
                with _actual_gdb_sends(debug, monkeypatch) as calls:
                    result = _public(debug, completed=False, accepted=False, consumed=False)
                assert result['outcome'] == kind
                assert result['native_result']['session']['stop_reason']['native_reply'][:3] in ('S05', 'T05')
                assert [row['command'] for row in calls] == ['c']
                assert _dword(debug, symbols, 'iterations') == before + 1
                assert debug.clock_observe()['virtual_ns'] < schedule['rows'][-1]
                assert result['fence']['observed']['state'] == 'armed'
                assert result['fence']['released']['state'] == 'cancelled'
                assert _query(debug)['frame-sequence'] == started['frame-sequence']
                _save(project, 'early-' + kind, result=result, real_gdb=calls,
                      iterations_before=before, iterations_after=_dword(debug, symbols, 'iterations'))
            finally:
                if kind == 'breakpoint':
                    debug.delete_breakpoint(point['breakpoint_id'])
                else:
                    debug.delete_hook(point['hook'])
            # A separate exact clock owner must cross the old target time;
            # a leaked private fence request would preempt this budget.
            _advance_to(debug, schedule['rows'][-1] + schedule['period_ns'])
            assert _dword(debug, symbols, 'iterations') > before + 1
            stopped = debug.video_frame_stop()
            assert stopped['native']['token'] == started['token']


def test_native_source_fence_hook_displaced_out_does_not_resume(fence_witness, monkeypatch):
    with fence_witness() as (project, debug, symbols):
        _, schedule = _start(debug, symbols)
        native, arm, observed, _ = _raw_run(debug)
        previous = _ordinary_completed(debug, native, arm, observed, schedule)
        _image(project, debug, schedule, expected_rgb())
        hook = _neutral_hook(debug, symbols['abort_site'])
        try:
            _request(debug, symbols, 'blank')
            arrival = debug.run(timeout_ms=5000, stop_on_hook=True)
            assert arrival['outcome'] == 'hook'
            assert arrival['session']['stop_reason']['native_reply'][:3] in ('S05', 'T05')
            assert int(debug.registers()['linear_pc'], 16) == symbols['abort_site']
            assert _byte(debug, symbols, 'after_abort') == 0
            before = debug.clock_observe()
            with _actual_gdb_sends(debug, monkeypatch) as calls:
                result = _public(debug, completed=False, accepted=False, consumed=False)
            _aborted_step(debug, symbols, result, before, commands=['s'], calls=calls)
            assert debug.clock_observe()['virtual_ns'] < _later(schedule)['rows'][-1]
            assert result['baseline_frame_sequence'] == previous['frame-id']
            _save(project, 'displaced-hook', arrival=arrival, before=before, result=result,
                  real_gdb=calls, pc=debug.registers()['linear_pc'],
                  after_abort=_byte(debug, symbols, 'after_abort'), irq_journal=_journal(debug, symbols).hex())
        finally:
            debug.delete_hook(hook['hook'])


def test_native_source_fence_internal_tracker_displaced_out_does_not_resume(
        fence_witness, monkeypatch, record_property):
    with fence_witness() as (project, debug, symbols):
        _, schedule = _start(debug, symbols)
        native, arm, observed, _ = _raw_run(debug)
        previous = _ordinary_completed(debug, native, arm, observed, schedule)
        _request(debug, symbols, 'blank')
        recorder = _AuthoredTracker()
        prior_tracker = getattr(debug, '_automatic_runtime_tracker', None)
        prior_callback = getattr(debug, '_automatic_tracking_callback_active', False)
        point = None
        record_property('tracker_scope', 'authored recorder provider; real native GDB breakpoint/displacement')
        try:
            debug._automatic_runtime_tracker = recorder
            debug._automatic_tracking_callback_active = True
            try:
                point = debug.breakpoint(symbols['abort_site'])
            finally:
                debug._automatic_tracking_callback_active = prior_callback
            recorder.internal_breakpoints.add(point['breakpoint_id'])
            before = debug.clock_observe()
            with _actual_gdb_sends(debug, monkeypatch) as calls:
                result = _public(debug, completed=False, accepted=False, consumed=False)
            _aborted_step(debug, symbols, result, before, commands=['c', 's'], calls=calls)
            assert debug.clock_observe()['virtual_ns'] < _later(schedule)['rows'][-1]
            assert result['baseline_frame_sequence'] == previous['frame-id']
            events = [entry['event'] for entry in recorder.events if entry['operation'] == 'internal']
            assert len(events) == 1 and events[0]['outcome'] == 'breakpoint'
            assert events[0]['breakpoints'] == [point['breakpoint_id']]
            assert events[0]['session']['stop_reason']['native_reply'][:3] in ('S05', 'T05')
            assert result['native_result']['internal_tracking_stops'] == 1
            _save(project, 'displaced-authored-tracker', before=before, result=result,
                  real_gdb=calls, tracker_events=recorder.events,
                  pc=debug.registers()['linear_pc'], after_abort=_byte(debug, symbols, 'after_abort'),
                  irq_journal=_journal(debug, symbols).hex(),
                  scope='authored recorder provider; no DESQview/provider-discovery qualification')
        finally:
            debug._automatic_tracking_callback_active = True
            try:
                if point is not None:
                    debug.delete_breakpoint(point['breakpoint_id'])
            finally:
                debug._automatic_runtime_tracker = prior_tracker
                debug._automatic_tracking_callback_active = prior_callback


def test_native_source_fence_running_page_aba_aborts_then_requires_fresh_stream(fence_witness):
    with fence_witness() as (project, debug, symbols):
        started, schedule = _start(debug, symbols)
        _request(debug, symbols, 'page_aba')
        before = debug.clock_observe()
        result = _public(debug, completed=False, accepted=False, consumed=True)
        observed = result['fence']['observed']
        assert result['outcome'] == 'stopped'
        assert result['native_result']['session']['stop_reason']['native_reply'][:3] in ('S02', 'T02')
        assert observed['state'] == 'aborted' and observed['reason']
        assert observed.get('completed-frame') is None and result['frame'] is None
        stopped = debug.clock_observe()
        assert before['virtual_ns'] < observed['stop-ns'] == stopped['virtual_ns'] < schedule['rows'][-1]
        invalidated = _query(debug)
        assert invalidated['state'] == 'invalidated' and invalidated.get('frame') is None
        assert invalidated['frame-sequence'] == started['frame-sequence']
        # The first configuration write owns the abort. Only after release do
        # we let the authored guest restore its original page and park.
        park(debug, symbols['aba_done'])
        assert _byte(debug, symbols, 'command') == 0
        assert _byte(debug, symbols, 'page_before') == _byte(debug, symbols, 'page_after')
        assert _query(debug)['state'] == 'invalidated'
        fresh, fresh_schedule = _start(debug, symbols)
        assert fresh['token'] != started['token']
        assert fresh['stream-generation'] == started['stream-generation'] + 1
        assert fresh['frame-sequence'] == started['frame-sequence']
        clean = _public(debug, completed=True, accepted=True, consumed=True)
        frame = _ordinary_completed(debug, clean['native_result'], clean['fence']['arm'],
                                    clean['fence']['observed'], fresh_schedule)
        assert frame == _image(project, debug, fresh_schedule, expected_rgb())
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-probe-video-frame', {'token': started['token'],
                'frame-id': frame['frame-id'], 'points': [{'x': 0, 'y': 0}]})
        _save(project, 'page-aba', before=before, aborted=result, invalidated=invalidated,
              page_before=_byte(debug, symbols, 'page_before'), page_after=_byte(debug, symbols, 'page_after'),
              fresh=clean)


def test_native_source_fence_controller_orders_refuse_without_dispatch(fence_witness):
    with fence_witness() as (project, debug, symbols):
        _start(debug, symbols)
        display = debug.display_start(period_ns=20_000_000)
        source, clock, registers = _query(debug), debug.clock_observe(), debug.registers()
        keys = debug.vm.qmp.call('x-fdisbull-query-frame-keys')
        pending = debug.vm.qmp.call('x-fdisbull-query-input')
        event = {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': 'a'}, 'down': True}}
        controllers = (
            ('clock', 'x-fdisbull-arm-clock-budget', {'delta-ns': 1_000_000},
             'x-fdisbull-query-clock', 'x-fdisbull-cancel-clock-budget'),
            ('renderer', 'x-fdisbull-arm-display-frame', {'display-token': display['window']},
             'x-fdisbull-query-display-frame', 'x-fdisbull-cancel-display-frame'),
            ('input', 'x-fdisbull-arm-input', {'delta-ns': 1_000_000, 'events': [event]},
             'x-fdisbull-query-input', 'x-fdisbull-cancel-input'),
        )
        arm = _arm(debug)
        refusals = []
        attempts = [(command, dict(arguments, token=uuid.uuid4().hex))
                    for _, command, arguments, _, _ in controllers]
        attempts.extend((
            ('x-fdisbull-apply-frame-key-edges', {'token': uuid.uuid4().hex,
                'expected-generation': keys['generation'], 'edges': [{'key': 'a', 'pressed': True}]}),
            ('x-fdisbull-instrumented-checkpoint-export', None),
            ('x-fdisbull-instrumented-snapshot-load', {'job-id': uuid.uuid4().hex,
                'tag': 'authored-missing-snapshot', 'vmstate': 'disk0', 'devices': ['disk0']}),
        ))
        for command, arguments in attempts:
            with pytest.raises(DebuggerError, match='fence') as refused:
                debug.vm.qmp.call(command, arguments, timeout_ms=1000)
            refusals.append(dict(command=command, error=str(refused.value)))
            assert _fence(debug, arm['token']) == arm
            assert _query(debug) == source
            assert debug.vm.qmp.call('x-fdisbull-query-frame-keys') == keys
            assert debug.vm.qmp.call('x-fdisbull-query-input') == pending
            assert debug.registers() == registers and _journal(debug, symbols) == b''
            _clock_equal(clock, debug.clock_observe())
        _release(debug, arm)
        reverse = []
        for name, command, arguments, query, cancel in controllers:
            token = uuid.uuid4().hex
            owner = debug.vm.qmp.call(command, dict(arguments, token=token), timeout_ms=1000)
            query_args = {'token': token} if name == 'renderer' else None
            retained = debug.vm.qmp.call(query, query_args, timeout_ms=1000)
            with pytest.raises(DebuggerError) as refused:
                debug.vm.qmp.call(ARM, _arm_arguments(source), timeout_ms=1000)
            assert debug.vm.qmp.call(query, query_args, timeout_ms=1000) == retained
            released = debug.vm.qmp.call(cancel, {'token': token}, timeout_ms=1000)
            reverse.append(dict(controller=name, owner=owner, retained=retained,
                                error=str(refused.value), released=released))
            assert _query(debug) == source
            assert debug.vm.qmp.call('x-fdisbull-query-frame-keys') == keys
            assert debug.registers() == registers and _journal(debug, symbols) == b''
            _clock_equal(clock, debug.clock_observe())
        _save(project, 'controller-orders', forward_refusals=refusals, reverse=reverse,
              source=source, clock=clock, keys=keys, registers=registers,
              scope='native guards, no checkpoint payload or scheduled edge dispatched')


def test_native_source_fence_stopped_edges_are_not_irq_consumption(fence_witness):
    with fence_witness() as (project, debug, symbols):
        _, schedule = _start(debug, symbols)
        assert _journal(debug, symbols) == b''
        before, registers = debug.clock_observe(), debug.registers()
        make = debug.frame_inputs([{'key': 'a', 'pressed': True}], timeout_ms=1000)
        assert make['guest_consumed'] is None and make['repeat_supported'] is False
        assert make['held'] == ['a'] and make['native']['accepted-edges'] == 1
        assert make['native']['translated'] is True and make['native']['scancode-set'] == 2
        assert debug.registers() == registers and _journal(debug, symbols) == b''
        _clock_equal(before, debug.clock_observe())
        disabled = _public(debug, completed=True, accepted=True, consumed=True)
        frame = _ordinary_completed(debug, disabled['native_result'], disabled['fence']['arm'],
                                    disabled['fence']['observed'], schedule)
        assert frame == _image(project, debug, schedule, expected_rgb())
        assert _journal(debug, symbols) == b''  # CLI is an authored nonconsumption witness.
        # The occupied controller output buffer intentionally admits no new
        # edge. Enable IRQ1 and consume the make before submitting the break.
        before_enable, after_enable = _guest_command(debug, symbols, 'enable_irq')
        assert before_enable['virtual_ns'] <= after_enable['virtual_ns'] < _later(schedule)['rows'][-1]
        enabled = _public(debug, completed=True, accepted=True, consumed=True)
        frame = _ordinary_completed(debug, enabled['native_result'], enabled['fence']['arm'],
                                    enabled['fence']['observed'], _later(schedule))
        assert frame == _image(project, debug, _later(schedule), expected_rgb())
        assert _journal(debug, symbols) == bytes.fromhex('1e')
        before_break, registers = debug.clock_observe(), debug.registers()
        release = debug.frame_inputs([{'key': 'a', 'pressed': False}], timeout_ms=1000)
        assert release['guest_consumed'] is None and release['repeat_supported'] is False
        assert release['held'] == [] and release['native']['accepted-edges'] == 2
        assert debug.registers() == registers and _journal(debug, symbols) == bytes.fromhex('1e')
        _clock_equal(before_break, debug.clock_observe())
        released = _public(debug, completed=True, accepted=True, consumed=True)
        frame = _ordinary_completed(debug, released['native_result'], released['fence']['arm'],
                                    released['fence']['observed'], _later(schedule, 2))
        assert frame == _image(project, debug, _later(schedule, 2), expected_rgb())
        assert _journal(debug, symbols) == bytes.fromhex('1e9e')
        state = debug.keyboard_state()['keyboard']
        assert state['frame_keys'] == [] and state['native']['held'] == []
        assert state['native']['accepted-edges'] == 2
        _save(project, 'input-versus-consumption', make=make, disabled=disabled,
              before_enable=before_enable, after_enable=after_enable, enabled=enabled,
              release=release, released=released,
              irq_journal=_journal(debug, symbols).hex(), keyboard=state,
              scope='accepted stopped edges and authored IRQ1 consumption; no typematic/application claim')
