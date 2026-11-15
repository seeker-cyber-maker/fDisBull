"""Actual PS/2 callbacks constrained to an admitted precise VGA occurrence.

Guest IRQ1 bytes and VGA port reads are independent witnesses. A callback's
modeled phase does not establish device acceptance for arbitrary workloads,
renderer publication, full VBlank duration or a completed application frame.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import struct
import uuid

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_retrace_fixture import precise_phase, precise_timing
from support.qemu_retrace_input_fixture import (
    ABA, ENABLE_VBE, REENTER_MODE13, retrace_keyboard,
)
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_retrace_native import artifact_document, assert_legacy_model, raw_timing
from test_qemu_timing_native import expected_edge, native_executions


COMMAND = 'x-fdisbull-arm-input-retrace'
IDENTITY = ('api-version', 'epoch', 'model', 'device', 'device-type', 'console', 'head')


@pytest.fixture
def retrace_input_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(*, halted=False, profile='precise', executable=None):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'retrace-input-{serial}'
        directory.mkdir()
        code, offsets = retrace_keyboard(directory, clock_runtime['nasm'], halted=halted)
        binary, project = create_project(directory, code)
        selected = clock_runtime['executable'] if executable is None else Path(executable).expanduser().resolve(strict=True)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(selected, directory, **launch_options(
                            clock_runtime, clock_disk, qemu_clock='virtual', qemu_retrace=profile)) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) for key, value in offsets.items()}
                        park(debug, symbols['ready_ip'])
                        assert debug.capabilities['virtual_input_schedule'] is True
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def word(debug, symbols, name):
    return struct.unpack('<H', read_bytes(debug, symbols[name], 2))[0]


def key_bytes(debug, symbols, count):
    assert word(debug, symbols, 'dropped_keys_ip') == 0
    assert word(debug, symbols, 'key_count_ip') == count
    return read_bytes(debug, symbols['key_bytes_ip'], count)


def set_command(debug, symbols, value):
    old = read_bytes(debug, symbols['command_ip'], 1)
    assert old == b'\x00'
    debug.write_memory(symbols['command_ip'], bytes([value]).hex(), expected_hex=old.hex())


def period_ns(raw):
    timing = precise_timing(raw)
    return timing['ticks-per-char'] * timing['total-chars']


def native_arguments(observation, events, *, edge='enter', token=None):
    native = observation['native']
    return {'token': token or uuid.uuid4().hex, 'events': deepcopy(events), 'edge': edge,
            'expected-epoch': native['epoch'], 'expected-device': native['device'],
            'expected-model': native['model'], 'expected-generation': native['timing-generation'],
            'expected-virtual-ns': native['virtual-ns']}


def assert_arm(value, raw, edge):
    assert value['format'] == 'fdisbull-qemu-scheduled-input-1'
    assert value['state'] == value['native']['state'] == 'armed'
    assert value['dispatch_ns'] is value['terminal_ns'] is None
    assert value['requires_resolution'] is False
    assert value['guest_consumed'] is value['device_queue_accepted'] is None
    binding, native = value['retrace'], value['native']['retrace']
    assert binding['format'] == 'fdisbull-retrace-input-1'
    assert binding['edge'] == native['edge'] == edge
    assert_legacy_model(binding['before'], raw)
    assert binding['before']['run'] == value['run']
    assert binding['before']['epoch'] == value['epoch']
    assert binding['native_arm'] == native['armed'] == binding['before']['native']
    assert binding['native_check'] is None and 'checked' not in native
    assert binding['dispatch_phase_verified'] is False
    target, end = expected_edge(raw, value['start_ns'], edge)
    assert value['start_ns'] == value['observed_ns'] == native['armed']['virtual-ns']
    assert target > value['start_ns']
    assert value['deadline_ns'] == binding['target_ns'] == native['target-ns'] == target
    assert binding['window_end_ns'] == native['window-end-ns'] == end
    assert value['native']['token'] == value['token']
    assert len(value['sequences']) == value['edge_count']
    return binding


def assert_dispatched(result, armed, raw):
    value = result['input_delivery']
    assert value['state'] == value['native']['state'] == 'dispatched'
    assert value['token'] == armed['token']
    assert value['sequences'] == armed['sequences']
    assert value['run'] == value['clock']['run'] == armed['run']
    assert value['epoch'] == value['clock']['epoch'] == armed['epoch']
    assert value['requires_resolution'] is False
    assert value['guest_consumed'] is value['device_queue_accepted'] is None
    binding, native = value['retrace'], value['native']['retrace']
    for field in ('format', 'edge', 'target_ns', 'window_end_ns', 'before', 'native_arm'):
        assert binding[field] == armed['retrace'][field]
    checked = binding['native_check']
    assert checked == native['checked']
    assert native['armed'] == binding['native_arm']
    assert binding['dispatch_phase_verified'] is True
    for field in IDENTITY:
        assert checked[field] == native['armed'][field]
    assert checked['epoch'] == value['clock']['virtual_clock']['native']['epoch']
    assert checked['timing-generation'] == native['armed']['timing-generation']
    assert checked['phase-supported'] is True and 'unsupported-reason' not in checked
    assert checked['raw'] == raw
    timing = precise_timing(raw)
    assert checked['timing'] == timing
    assert checked['phase'] == precise_phase(timing, checked['virtual-ns'])
    assert checked['virtual-ns'] == value['dispatch_ns'] == value['terminal_ns']
    assert binding['target_ns'] <= value['dispatch_ns'] < binding['window_end_ns']
    assert checked['phase']['vertical-retrace'] is (binding['edge'] == 'enter')
    assert value['deadline_ns'] == binding['target_ns']
    assert value['lateness_ns'] == value['dispatch_ns'] - value['deadline_ns']
    assert value['dispatch_ns'] <= value['observed_ns'] == value['clock']['virtual_ns'] == result['clock_budget']['stopped_ns']
    return value


def assert_cancelled(result, armed, *, reason=None):
    value = result['input_delivery']
    assert value['state'] == value['native']['state'] == 'cancelled'
    assert value['token'] == armed['token'] and value['sequences'] == armed['sequences']
    assert value['dispatch_ns'] is value['lateness_ns'] is None
    assert value['requires_resolution'] is True
    binding = value['retrace']
    assert binding['dispatch_phase_verified'] is False
    for field in ('format', 'edge', 'target_ns', 'window_end_ns', 'before', 'native_arm'):
        assert binding[field] == armed['retrace'][field]
    if reason is None:
        assert value['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert binding['native_check'] is None
        assert 'checked' not in value['native']['retrace']
        assert value['terminal_ns'] == value['observed_ns'] == result['clock_budget']['stopped_ns']
    else:
        assert value['reason'] == reason
        checked = binding['native_check']
        assert checked == value['native']['retrace']['checked']
        for field in IDENTITY:
            assert checked[field] == binding['native_arm'][field]
        assert binding['target_ns'] <= value['terminal_ns'] == checked['virtual-ns'] <= value['observed_ns']
        if reason == 'retrace-timing-changed':
            assert checked['timing-generation'] > binding['native_arm']['timing-generation']
    return value


def frozen(native):
    return {key: value for key, value in native.items() if key != 'virtual-ns'}


@pytest.mark.parametrize('halted', [False, True], ids=['busy', 'hlt'])
@pytest.mark.parametrize('edge', ['enter', 'exit'])
def test_native_retrace_input_dispatch_and_guest_status_share_one_occurrence(
        retrace_input_witness, monkeypatch, halted, edge):
    with retrace_input_witness(halted=halted) as (_, debug, symbols):
        assert debug.capabilities['retrace_input_schedule'] is True
        raw = raw_timing(debug, symbols)
        opposite = 'exit' if edge == 'enter' else 'enter'
        assert debug.retrace_wait(edge=opposite, timeout_ms=3000)['synchronized']
        before = debug.clock_observe()
        lease = debug.keyboard_key_down('a')['lease']
        calls = native_executions(debug, monkeypatch)
        armed = debug.input_schedule_retrace(edge=edge)
        binding = assert_arm(armed, raw, edge)
        assert debug.input_schedule_observe()['native'] == armed['native']
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns'] == armed['start_ns']
        assert word(debug, symbols, 'key_count_ip') == 0 and not calls
        assert debug.input_state()['leases'][lease]['make'] == 'python_pending'
        point = debug.breakpoint(symbols['input_seen_ip'])
        try:
            result = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
            delivered = assert_dispatched(result, armed, raw)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert result['clock_budget']['deadline_reached'] is False
            assert len(calls) == 1 and calls[0]['command'] == 'c'
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert key_bytes(debug, symbols, 1) == b'\x1e'
            # The actual port read followed dispatch and preceded this fence.
            # Both ends are inside the same absolute vertical phase interval.
            stopped = result['clock_budget']['stopped_ns']
            assert binding['target_ns'] <= delivered['dispatch_ns'] <= stopped < binding['window_end_ns']
            sampled = read_bytes(debug, symbols['status_bytes_ip'], 1)[0]
            assert bool(sampled & 8) is (edge == 'enter')
            assert debug.input_state()['leases'][lease]['make'] == 'native_dispatched'
            after = debug.clock_observe()
            assert after['virtual_ns'] == stopped
            if halted:
                instructions = after['counter']['value'] - before['counter']['value']
                assert 0 < instructions < 1000
                assert after['virtual_ns'] - before['virtual_ns'] > instructions * 128
                assert word(debug, symbols, 'wakes_ip') == 0  # Still inside IRQ1.
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        if halted:
            budget_receipt(debug.clock_advance(1_000_000, timeout_ms=3000), 1_000_000)
            assert word(debug, symbols, 'wakes_ip') == 1


def test_native_retrace_input_aba_cancels_then_explicit_reschedule_preserves_history(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        assert debug.retrace_wait(edge='exit', timeout_ms=3000)['synchronized']
        set_command(debug, symbols, ABA)
        lease = debug.keyboard_key_down('a')['lease']
        armed = debug.input_schedule_retrace()
        assert_arm(armed, raw, 'enter')
        calls = native_executions(debug, monkeypatch)
        result = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
        budget_receipt(result, 2 * period_ns(raw))
        cancelled = assert_cancelled(result, armed, reason='retrace-timing-changed')
        checked = cancelled['retrace']['native_check']
        assert checked['timing-generation'] >= armed['retrace']['native_arm']['timing-generation'] + 2
        assert checked['raw'] == raw and checked['timing'] == precise_timing(raw)
        assert checked['phase'] == precise_phase(precise_timing(raw), checked['virtual-ns'])
        assert cancelled['terminal_ns'] < cancelled['observed_ns']
        assert raw_timing(debug, symbols) == raw
        assert read_bytes(debug, symbols['command_ip'], 1) == b'\x00'
        state = debug.input_state()
        assert state['pending_edges'] == 1 and state['leases'][lease]['make'] == 'python_pending'
        assert word(debug, symbols, 'key_count_ip') == 0 and len(calls) == 1
        with pytest.raises(ValueError, match='reschedule or cancel'):
            debug.run(timeout_ms=1000)
        with pytest.raises(ValueError, match='scheduled'):
            debug.keyboard_key_down('b')
        assert len(calls) == 1

        rearmed = debug.input_schedule_retrace()
        assert_arm(rearmed, raw, 'enter')
        assert rearmed['token'] != armed['token'] and rearmed['sequences'] == armed['sequences']
        assert rearmed['retrace']['native_arm']['timing-generation'] == checked['timing-generation']
        second = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
        delivered = assert_dispatched(second, rearmed, raw)
        assert key_bytes(debug, symbols, 1) == b'\x1e' and len(calls) == 2

        # Advance the live retrace frontier after terminal delivery. Historical
        # arm/check snapshots must stay frozen and must not rewind that frontier.
        set_command(debug, symbols, ABA)
        debug.clock_advance(period_ns(raw), timeout_ms=5000)
        current = debug.retrace_observe()
        assert_legacy_model(current, raw)
        assert current['timing_generation'] >= checked['timing-generation'] + 2
        observed = debug.input_schedule_observe()
        assert observed['retrace'] == delivered['retrace']
        assert frozen(observed['native']) == frozen(delivered['native'])
        assert observed['observed_ns'] > delivered['observed_ns']
        assert debug.retrace_observe()['timing_generation'] == current['timing_generation']
        assert key_bytes(debug, symbols, 1) == b'\x1e'


def test_native_retrace_input_vbe_change_cancels_without_discarding_pending_batch(
        retrace_input_witness):
    with retrace_input_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        assert debug.retrace_wait(edge='exit', timeout_ms=3000)['synchronized']
        set_command(debug, symbols, ENABLE_VBE)
        lease = debug.keyboard_key_down('a')['lease']
        armed = debug.input_schedule_retrace()
        assert_arm(armed, raw, 'enter')
        result = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
        budget_receipt(result, 2 * period_ns(raw))
        cancelled = assert_cancelled(result, armed, reason='retrace-timing-changed')
        checked = cancelled['retrace']['native_check']
        assert checked['phase-supported'] is False and checked['unsupported-reason'] == 'vbe-enabled'
        assert 'phase' not in checked and checked['raw']['vbe-enable'] & 1
        assert cancelled['terminal_ns'] < cancelled['observed_ns']
        assert word(debug, symbols, 'key_count_ip') == 0
        state = debug.input_state()
        with pytest.raises(ValueError):
            debug.input_schedule_retrace(edge='exit')
        retained = debug.input_state()
        assert retained['valid'] and retained['pending'] == state['pending']
        assert retained['leases'] == state['leases'] and retained['schedule']['token'] == armed['token']
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_leases'] == [lease] and resolved['cancelled_edges'] == 1
        set_command(debug, symbols, REENTER_MODE13)
        park(debug, symbols['command_done_ip'])
        current = debug.retrace_observe()
        assert_legacy_model(current, raw_timing(debug, symbols))
        assert current['timing_generation'] > checked['timing-generation']
        assert debug.input_schedule_observe()['retrace']['native_check'] == checked
        assert word(debug, symbols, 'key_count_ip') == 0


def test_native_retrace_input_keeps_original_early_breakpoint_and_never_replays(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        assert debug.retrace_wait(edge='exit', timeout_ms=3000)['synchronized']
        lease = debug.keyboard_key_down('a')['lease']
        armed = debug.input_schedule_retrace()
        point = debug.breakpoint(symbols['main_loop_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
            cancelled = assert_cancelled(result, armed)
            assert result['outcome'] == 'breakpoint' and result['clock_budget']['deadline_reached'] is False
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert cancelled['terminal_ns'] < armed['deadline_ns']
            assert word(debug, symbols, 'key_count_ip') == 0
            with pytest.raises(ValueError, match='reschedule or cancel'):
                debug.clock_advance(period_ns(raw), timeout_ms=1000)
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        assert debug.input_cancel_pending()['cancelled_leases'] == [lease]
        debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0


def test_native_retrace_input_clock_cutoff_wins_when_input_timer_is_inserted_first(
        retrace_input_witness):
    with retrace_input_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        debug.keyboard_key_down('a')
        armed = debug.input_schedule_retrace()
        assert_arm(armed, raw, 'enter')
        delta = armed['deadline_ns'] - armed['start_ns']
        result = debug.clock_advance(delta, timeout_ms=5000)
        budget_receipt(result, delta)
        cancelled = assert_cancelled(result, armed)
        assert result['clock_budget']['deadline_ns'] == armed['deadline_ns']
        assert cancelled['terminal_ns'] >= armed['deadline_ns']
        assert debug.input_state()['pending_edges'] == 1
        assert word(debug, symbols, 'key_count_ip') == 0
        debug.input_cancel_pending()
        debug.clock_advance(period_ns(raw), timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0


def test_native_retrace_input_clock_cutoff_wins_when_budget_timer_is_inserted_first(
        retrace_input_witness):
    with retrace_input_witness(halted=True) as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        before = debug.retrace_observe()
        target, end = expected_edge(raw, before['observed_ns'], 'enter')
        budget_token = uuid.uuid4().hex
        clock = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
            {'token': budget_token, 'delta-ns': target - before['observed_ns']})
        assert clock['budget-state'] == 'armed' and clock['budget-deadline-ns'] == target
        # Native wire ownership is explicit in this case. Public passive
        # retrace observation must keep rejecting the armed-budget state.
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-query-retrace')
        event = dict(type='key', data=dict(key=dict(type='qcode', data='a'), down=True))
        arguments = native_arguments(before, [event])
        armed = debug.vm.qmp.call(COMMAND, arguments)
        assert armed['state'] == 'armed' and armed['deadline-ns'] == target
        assert armed['retrace']['window-end-ns'] == end and armed['retrace']['armed'] == before['native']
        result = debug.run(timeout_ms=5000)
        assert result['outcome'] == 'stopped' and result['timed_out'] is False
        assert result['session']['stop_reason']['native_reply'][:3] in ('T02', 'S02')
        stopped_clock = debug.vm.qmp.call('x-fdisbull-query-clock')
        cancelled = debug.vm.qmp.call('x-fdisbull-query-input')
        assert stopped_clock['budget-state'] == 'stopped'
        for field in ('epoch', 'budget-token', 'budget-start-ns', 'budget-deadline-ns'):
            assert stopped_clock[field] == clock[field]
        assert target <= stopped_clock['budget-fired-ns'] <= stopped_clock['budget-stopped-ns']
        assert stopped_clock['budget-stopped-ns'] == stopped_clock['virtual-ns']
        assert stopped_clock['running'] is stopped_clock['pending-stop'] is False
        assert cancelled['state'] == 'cancelled' and cancelled['token'] == arguments['token']
        assert cancelled['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert cancelled['terminal-ns'] == stopped_clock['budget-stopped-ns'] == cancelled['virtual-ns']
        assert 'dispatch-ns' not in cancelled and 'checked' not in cancelled['retrace']
        assert word(debug, symbols, 'key_count_ip') == word(debug, symbols, 'wakes_ip') == 0
        final_clock = debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': budget_token})
        assert final_clock == {**stopped_clock, 'budget-state': 'cancelled'}
        assert debug.vm.qmp.call('x-fdisbull-query-input') == cancelled
        assert debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': arguments['token']}) == cancelled
        debug.clock_advance(period_ns(raw), timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(cancelled)


def test_native_retrace_input_cancelled_release_retains_hold_and_legacy_arm_clears_descriptor(
        retrace_input_witness):
    with retrace_input_witness() as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        lease = debug.keyboard_key_down('a')['lease']
        make = debug.input_schedule_retrace()
        assert_dispatched(debug.clock_advance(2 * period_ns(raw), timeout_ms=5000), make, raw)
        assert key_bytes(debug, symbols, 1) == b'\x1e'
        assert debug.retrace_wait(edge='exit', timeout_ms=3000)['synchronized']
        debug.keyboard_key_up(lease)
        release = debug.input_schedule_retrace()
        point = debug.breakpoint(symbols['main_loop_ip'])
        try:
            interrupted = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)
            assert_cancelled(interrupted, release)
            assert interrupted['outcome'] == 'breakpoint'
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        cancelled = debug.input_cancel_pending()
        assert cancelled['cancelled_edges'] == 1 and cancelled['cancelled_leases'] == []
        assert cancelled['retained_dispatched_holds'] == [lease]
        hold = debug.input_state()['leases'][lease]
        assert hold['make'] == 'native_dispatched' and hold['release'] is None
        debug.clock_advance(period_ns(raw), timeout_ms=5000)
        assert key_bytes(debug, symbols, 1) == b'\x1e'
        debug.keyboard_key_up(lease)
        ordinary = debug.input_schedule(1_000_000)
        assert 'retrace' not in ordinary and 'retrace' not in ordinary['native']
        delivered = debug.clock_advance(5_000_000, timeout_ms=5000)['input_delivery']
        assert delivered['state'] == 'dispatched' and delivered['token'] == ordinary['token']
        assert 'retrace' not in delivered and 'retrace' not in delivered['native']
        assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
        assert debug.input_state()['leases'] == {} and debug.input_state()['pending_edges'] == 0


def test_native_retrace_input_json_script_and_reopen_preserve_exact_phase_evidence(
        retrace_input_witness):
    with retrace_input_witness() as (project, debug, symbols):
        raw = raw_timing(debug, symbols)
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='retrace-input', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            lease = invoke('debug-keyboard-down', key='a')['lease']
            armed = invoke('debug-input-schedule-retrace', edge='enter', timeout_ms=1000)
            assert_arm(armed, raw, 'enter')
            first = invoke('debug-clock-advance', delta_ns=2 * period_ns(raw), timeout_ms=5000)
            assert_dispatched(first, armed, raw)
            invoke('debug-keyboard-up', lease=lease)
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='input-schedule-retrace', edge='exit', timeout_ms=1000),
                dict(op='clock-advance', delta_ns=2 * period_ns(raw), timeout_ms=5000),
                dict(op='input-schedule-observe')])
            report = invoke('debug-script', script=script, timeout_ms=10000)
            assert report['ok'] and report['completed_steps'] == len(script['steps']), report
            rearmed, second, observed = [row['result'] for row in report['steps']]
            assert_arm(rearmed, raw, 'exit')
            delivered = assert_dispatched(second, rearmed, raw)
            assert rearmed['token'] != armed['token']
            assert observed['native'] == delivered['native']
            assert observed['retrace'] == delivered['retrace']
            assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
            assert debug.input_state()['leases'] == {}
            path, run = project.path, debug.run_id
        finally:
            workspace.sessions.clear()
    with Project(path) as reopened:
        assert artifact_document(reopened, report['script_artifact']) == script
        saved = artifact_document(reopened, report['artifact'])
        assert public_addresses(saved) == {key: value for key, value in report.items() if key != 'artifact'}
        evidence = [json.loads(row[0]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation IN "
            "('input.schedule-arm','input.schedule-result','input.schedule-observe') ORDER BY sequence", (run,))]
        assert armed in [public_addresses(item) for item in evidence]
        assert saved['steps'][0]['result'] in evidence
        assert saved['steps'][1]['result']['input_delivery'] in evidence
        assert saved['steps'][2]['result'] in evidence
        assert reopened.debug_runs()['live_state_verified'] is False


def test_native_retrace_input_standard_profile_and_optional_old_binary_keep_delta_scheduling(
        retrace_input_witness, monkeypatch):
    candidates = [('standard', None)]
    # Root may supply the retained four-patch binary for a second short VM in
    # this case. Its absence is not reported as old-binary qualification.
    legacy = os.environ.get('FDISBULL_QEMU_RETRACE_LEGACY')
    if legacy:
        candidates.append(('precise', legacy))
    for profile, executable in candidates:
        with retrace_input_witness(profile=profile, executable=executable) as (_, debug, symbols):
            assert debug.capabilities['retrace_input_schedule'] is False
            if executable is not None:
                assert COMMAND not in debug.vm.qmp_commands
                assert debug.capabilities['retrace_observation'] is True
            else:
                assert COMMAND in debug.vm.qmp_commands
            lease = debug.keyboard_key_down('a')['lease']
            pending = deepcopy(debug.input_state()['pending'])
            before = debug.registers()
            calls = native_executions(debug, monkeypatch)
            with pytest.raises(ValueError):
                debug.input_schedule_retrace()
            assert debug.registers() == before and not calls
            assert debug.input_state()['pending'] == pending
            assert debug.input_state()['leases'][lease]['make'] == 'python_pending'
            assert debug.vm.qmp.call('x-fdisbull-query-input')['state'] == 'idle'
            ordinary = debug.input_schedule(3_000_000)
            assert 'retrace' not in ordinary and 'retrace' not in ordinary['native']
            result = debug.clock_advance(10_000_000, timeout_ms=5000)
            assert result['input_delivery']['state'] == 'dispatched'
            assert result['input_delivery']['token'] == ordinary['token']
            assert key_bytes(debug, symbols, 1) == b'\x1e'
            assert len(calls) == 1 and debug.input_state()['leases'][lease]['make'] == 'native_dispatched'


def test_native_retrace_input_rejects_stale_arm_expectations_before_timer_acceptance(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness() as (_, debug, symbols):
        before = debug.retrace_observe()
        debug.keyboard_key_down('a')
        pending = deepcopy(debug.input_state()['pending'])
        arguments = native_arguments(before, [record['event'] for record in pending])
        calls = native_executions(debug, monkeypatch)
        assert debug.vm.qmp.call('x-fdisbull-query-input')['state'] == 'idle'
        mismatches = {
            'expected-epoch': arguments['expected-epoch'] + 1,
            'expected-device': arguments['expected-device'] + '/foreign',
            'expected-model': arguments['expected-model'] + '-foreign',
            'expected-generation': max(0, arguments['expected-generation'] - 1),
            'expected-virtual-ns': arguments['expected-virtual-ns'] - 1,
        }
        assert arguments['expected-generation'] > 0 and arguments['expected-virtual-ns'] > 0
        for field, value in mismatches.items():
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(COMMAND, {**arguments, field: value})
            idle = debug.vm.qmp.call('x-fdisbull-query-input')
            assert idle['state'] == 'idle' and idle['event-count'] == 0
            assert idle['virtual-ns'] == before['observed_ns'] and 'retrace' not in idle
            assert debug.input_state()['pending'] == pending
            assert word(debug, symbols, 'key_count_ip') == 0
        assert not calls
        # A refused arm must not consume the unused token. Prove acceptance
        # with the original correct expectation, then positively disarm it
        # before clearing the still-Python-owned records.
        armed = debug.vm.qmp.call(COMMAND, arguments)
        assert armed['state'] == 'armed' and armed['token'] == arguments['token']
        assert armed['retrace']['armed'] == before['native']
        cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': arguments['token']})
        assert cancelled['state'] == 'cancelled' and 'dispatch-ns' not in cancelled
        assert 'checked' not in cancelled['retrace']
        assert debug.input_cancel_pending()['cancelled_edges'] == 1
        debug.clock_advance(period_ns(raw_timing(debug, symbols)), timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0
