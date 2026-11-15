"""Independent guest witnesses for bounded retrace and cooperative host sync.

Host elapsed time is measured, never asserted to equal a requested sleep.
The sync mapping deliberately counts all host time since explicit start.
Neither a modeled retrace edge nor clock convergence proves guest completion.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
import time

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_clock_fixture import (
    PIT_DIVISOR, PIT_INPUT_HZ, busy_clock, halted_clock, pit_clock,
)
from support.qemu_retrace_fixture import precise_timing, retrace_ports
from support.qemu_timing_fixture import halted_retrace, terminating_clock
from test_qemu_clock_budget_native import (
    budget_receipt, clock_disk, clock_runtime, dword, park,
)
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_input_schedule_native import input_witness, word
from test_qemu_retrace_native import (
    artifact_document, assert_legacy_model, raw_timing,
)


@pytest.fixture
def timing_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(builder=busy_clock, *, clock='virtual', retrace='standard'):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'timing-{serial}'
        directory.mkdir()
        code, offsets = builder(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                             qemu_clock=clock, qemu_retrace=retrace)) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) for key, value in offsets.items()}
                        park(debug, symbols['ready_ip'])
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def native_executions(debug, monkeypatch):
    """Record actual GDB execution requests and replies, without replacing them."""
    remote = debug.vm.debugger()
    execute = remote.execute
    calls = []

    def observed(command, *args, **kwargs):
        record = {'command': command}
        calls.append(record)
        result = execute(command, *args, **kwargs)
        record['reply'] = deepcopy(result)
        return result

    monkeypatch.setattr(remote, 'execute', observed)
    return calls


def expected_edge(raw, now, edge):
    timing = precise_timing(raw)
    line_ns = timing['htotal'] * timing['ticks-per-char']
    period = timing['total-chars'] * timing['ticks-per-char']
    entry = timing['vstart'] * line_ns
    exit_ns = (timing['vend'] + 1) * line_ns
    width = exit_ns - entry
    assert 0 < width < period
    phase = entry if edge == 'enter' else exit_ns % period
    target = now + ((phase - now) % period or period)
    end = target + (width if edge == 'enter' else period - width)
    return target, end


def assert_wait(value, raw, edge):
    assert value['format'] == 'fdisbull-retrace-wait-1'
    assert value['edge'] == edge
    before, after = value['before'], value['after']
    assert_legacy_model(before, raw)
    target, end = expected_edge(raw, before['observed_ns'], edge)
    assert value['target_ns'] == target and value['window_end_ns'] == end
    assert value['completed_renderer_update'] is value['completed_guest_frame'] is value['guest_frame_id'] is None
    execution = value['execution']
    assert execution is not None
    budget = execution['clock_budget']
    assert budget['start_ns'] == before['observed_ns']
    assert budget['requested_delta_ns'] == target - before['observed_ns']
    assert budget['deadline_ns'] == target
    if value['synchronized']:
        assert value['outcome'] == 'synchronized'
        assert_legacy_model(after, raw)
        assert before['epoch'] == after['epoch'] and before['native_epoch'] == after['native_epoch']
        assert before['device'] == after['device'] and before['model'] == after['model']
        assert before['timing_generation'] == after['timing_generation']
        assert budget['deadline_reached'] and execution['timed_out'] is False
        assert execution['outcome'] == execution['session']['state'] == 'stopped'
        reason = execution['session']['stop_reason']
        assert reason['kind'] == 'stopped' and reason['breakpoint_ids'] == []
        assert reason.get('classification_complete', True) is True
        assert reason['native_reply'][:3] in ('T02', 'S02')
        assert not {'guest_exit', 'guest_tsr', 'data_access'} & reason.keys()
        assert not {'native_machine_stop', 'guest_exit', 'guest_tsr'} & execution.keys()
        assert execution['process']['state'] == 'active'
        assert execution['process']['termination'] is None
        assert execution['stop']['trigger'] == execution['stop']['native_kind'] == 'stopped'
        assert execution['stop']['context'] == 'machine'
        assert execution['stop']['instruction_completed'] is execution['stop']['causing_instruction'] is None
        assert target <= budget['fired_ns'] <= budget['stopped_ns'] < end
        assert after['observed_ns'] == budget['stopped_ns']
        assert after['phase']['vertical-retrace'] is (edge == 'enter')


def assert_sync(value, *, anchor=None):
    assert value['format'] == 'fdisbull-clock-sync-1'
    assert value['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert value['host_clock_domain'] == 'time.monotonic_ns'
    assert value['rate'] == {'virtual_ns': 1, 'host_ns': 1}
    assert value['token']
    if anchor is not None:
        for key in ('token', 'run', 'epoch', 'native_epoch', 'anchors', 'config', 'rate'):
            assert value[key] == anchor[key]
    for name in ('before', 'after'):
        sample = value[name]
        assert sample['run'] == value['run'] and sample['epoch'] == value['epoch']
        assert sample['virtual_clock']['native']['epoch'] == value['native_epoch']
        assert sample['host_monotonic_ns'] <= value['host_' + name + '_ns']
    origin = value['anchors']
    target_before = origin['virtual_ns'] + value['host_before_ns'] - origin['host_ns']
    target_after = origin['virtual_ns'] + value['host_after_ns'] - origin['host_ns']
    assert value['drift_before_ns'] == value['before']['virtual_ns'] - target_before
    assert value['drift_after_ns'] == value['after']['virtual_ns'] - target_after
    assert value['within_tolerance'] is (abs(value['drift_after_ns']) <= value['config']['tolerance_ns'])
    if value['operation'] == 'step':
        assert value['target_ns'] == target_before
    assert value['host_after_ns'] >= value['host_before_ns'] >= origin['host_ns']


@pytest.mark.parametrize('builder', [retrace_ports, halted_retrace], ids=['busy', 'cli-hlt'])
def test_native_retrace_wait_reaches_only_the_requested_absolute_occurrence(
        timing_witness, monkeypatch, builder):
    with timing_witness(builder, retrace='precise') as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        calls = native_executions(debug, monkeypatch)
        for edge in ('enter', 'exit', 'enter'):
            prior = debug.clock_observe()
            result = debug.retrace_wait(edge=edge, timeout_ms=3000)
            assert result['synchronized'], result
            assert_wait(result, raw, edge)
            assert result['target_ns'] > prior['virtual_ns']
            assert calls[-1]['command'] == 'c'
            assert result['execution']['session']['stop_reason']['native_reply'] == calls[-1]['reply'][0].decode('ascii')
            if builder is halted_retrace:
                after = result['after']['clocks']['after']
                instructions = after['counter']['value'] - prior['counter']['value']
                elapsed = after['virtual_ns'] - prior['virtual_ns']
                assert elapsed > instructions * 128
                assert dword(debug, symbols, 'unexpected_wakes_ip') == 0
        assert len(calls) == 3
        assert debug.clock_observe()['virtual_clock']['native']['budget-state'] in ('stopped', 'cancelled')


def test_native_retrace_wait_detects_aba_without_retargeting_or_retry(timing_witness, monkeypatch):
    with timing_witness(retrace_ports, retrace='precise') as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        # Exit first, leaving almost a full non-retrace interval in which the
        # short authored A -> B -> A sequence can finish before the next entry.
        initial = debug.retrace_wait(edge='exit', timeout_ms=3000)
        assert initial['synchronized'], initial
        debug.write_memory(symbols['command_ip'], '05', expected_hex='00')
        before = debug.retrace_observe()
        calls = native_executions(debug, monkeypatch)
        changed = debug.retrace_wait(edge='enter', timeout_ms=3000)
        assert changed['outcome'] == 'timing-changed' and changed['synchronized'] is False, changed
        assert_wait(changed, raw, 'enter')
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert changed['execution']['clock_budget']['deadline_reached']
        assert changed['after']['timing_generation'] >= before['timing_generation'] + 2
        assert changed['before']['raw'] == changed['after']['raw'] == raw_timing(debug, symbols)
        assert changed['before']['timing'] == changed['after']['timing']
        assert read_bytes(debug, symbols['command_ip'], 1) == b'\x00'
        assert changed['execution']['session']['stop_reason']['native_reply'] == calls[0]['reply'][0].decode('ascii')


def test_native_retrace_wait_preserves_debugger_stop_without_retry(timing_witness, monkeypatch):
    with timing_witness(retrace_ports, retrace='precise') as (_, debug, symbols):
        raw = raw_timing(debug, symbols)
        assert debug.retrace_wait(edge='exit', timeout_ms=3000)['synchronized']
        point = debug.breakpoint(symbols['dispatch_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.retrace_wait(edge='enter', timeout_ms=3000)
            assert result['outcome'] == 'interrupted' and result['synchronized'] is False, result
            assert_wait(result, raw, 'enter')
            native = result['execution']
            assert native['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in native['session']['stop_reason']['breakpoint_ids']
            assert native['clock_budget']['deadline_reached'] is False
            assert result['after']['observed_ns'] < result['target_ns']
            assert len(calls) == 1 and calls[0]['command'] == 'c'
            assert native['session']['stop_reason']['native_reply'] == calls[0]['reply'][0].decode('ascii')
            assert debug.status()['state'] == 'stopped'
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])


@pytest.mark.parametrize('builder', [busy_clock, halted_clock, pit_clock], ids=['busy', 'cli-hlt', 'pit-irq'])
def test_native_clock_sync_catches_host_work_without_double_counting_native_progress(
        timing_witness, monkeypatch, builder):
    with timing_witness(builder) as (_, debug, symbols):
        assert debug.capabilities['host_clock_sync'] is True
        assert debug.capabilities['retrace_wait'] is False
        started = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=1_000_000_000,
                                          max_wait_ns=1_000_000_000)
        assert_sync(started)
        prior = debug.clock_advance(2_000_000, timeout_ms=3000)
        budget_receipt(prior, 2_000_000)
        count_before = (dword(debug, symbols, 'loop_count_ip') if builder is busy_clock else
                        dword(debug, symbols, 'irq_count_ip') if builder is pit_clock else 0)
        calls = native_executions(debug, monkeypatch)
        time.sleep(.020)  # Deliberate host work/idle; the measured elapsed value is authoritative.
        first = debug.clock_sync_step(timeout_ms=3000)
        assert_sync(first, anchor=started)
        assert first['state'] == 'active' and first['action'] == 'advance' and first['outcome'] == 'advanced', first
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        execution = first['execution']
        budget = execution['clock_budget']
        assert budget['deadline_reached'] and execution['timed_out'] is False
        assert budget['deadline_ns'] == first['target_ns']
        assert budget['requested_delta_ns'] == first['target_ns'] - first['before']['virtual_ns']
        assert first['before']['virtual_ns'] > started['anchors']['virtual_ns']
        assert budget['requested_delta_ns'] < first['host_before_ns'] - started['anchors']['host_ns']
        assert first['after']['virtual_ns'] == budget['stopped_ns']
        assert first['actual_wait_ns'] == 0
        if builder is busy_clock:
            assert dword(debug, symbols, 'loop_count_ip') > count_before
        elif builder is halted_clock:
            instructions = first['after']['counter']['value'] - first['before']['counter']['value']
            assert budget['elapsed_ns'] > instructions * 128
            assert dword(debug, symbols, 'unexpected_wakes_ip') == 0
        else:
            interrupts = dword(debug, symbols, 'irq_count_ip') - count_before
            expected = budget['elapsed_ns'] * PIT_INPUT_HZ // (PIT_DIVISOR * 1_000_000_000)
            assert expected - 2 <= interrupts <= expected + 2
            assert interrupts > 0
        # Later correction uses the original mapping, including all actual
        # native progress and correction/control overhead already observed.
        time.sleep(.005)
        second = debug.clock_sync_step(timeout_ms=3000)
        assert_sync(second, anchor=started)
        assert second['action'] == 'advance' and second['state'] == 'active', second
        assert len(calls) == 2
        assert second['target_ns'] - first['target_ns'] == second['host_before_ns'] - first['host_before_ns']
        assert second['execution']['clock_budget']['requested_delta_ns'] == second['target_ns'] - second['before']['virtual_ns']


def test_native_clock_sync_ahead_wait_is_host_only(timing_witness, monkeypatch):
    with timing_witness(halted_clock) as (_, debug, symbols):
        started = debug.clock_sync_start(tolerance_ns=1_000_000, max_lag_ns=1_000_000_000,
                                          max_wait_ns=1_000_000_000)
        budget_receipt(debug.clock_advance(300_000_000, timeout_ms=3000), 300_000_000)
        calls = native_executions(debug, monkeypatch)
        ahead = debug.clock_sync_observe()
        assert_sync(ahead, anchor=started)
        assert ahead['drift_after_ns'] > started['config']['tolerance_ns'], {
            'setup': 'The 300 ms virtual lead must exceed elapsed host setup time',
            'observed': ahead,
        }
        sleeps = []
        real_sleep = time.sleep

        def observed_sleep(seconds):
            record = {'seconds': seconds, 'before_ns': time.monotonic_ns()}
            sleeps.append(record)
            try:
                return real_sleep(seconds)
            finally:
                record['after_ns'] = time.monotonic_ns()

        with monkeypatch.context() as sleep_patch:
            sleep_patch.setattr(time, 'sleep', observed_sleep)
            result = debug.clock_sync_step(timeout_ms=3000)
        assert_sync(result, anchor=started)
        assert result['drift_before_ns'] > result['config']['tolerance_ns'], {
            'setup': ahead, 'step': result,
        }
        assert result['action'] == 'wait' and result['outcome'] == 'waited' and result['state'] == 'active', result
        assert result['execution'] is None and not calls
        assert result['wait_deadline_host_ns'] == started['anchors']['host_ns'] + result['before']['virtual_ns'] - started['anchors']['virtual_ns']
        assert result['requested_wait_ns'] == result['drift_before_ns']
        assert len(sleeps) == 1, sleeps
        sleep = sleeps[0]
        assert 0 < sleep['seconds'] <= result['requested_wait_ns'] / 1_000_000_000 <= result['config']['max_wait_ns'] / 1_000_000_000
        assert 0 < sleep['after_ns'] - sleep['before_ns'] <= result['actual_wait_ns']
        assert result['host_before_ns'] <= sleep['before_ns'] < sleep['after_ns'] <= result['host_after_ns']
        assert result['after']['virtual_ns'] == result['before']['virtual_ns']
        assert result['after']['counter']['value'] == result['before']['counter']['value']
        assert dword(debug, symbols, 'unexpected_wakes_ip') == 0


def test_native_clock_sync_excess_host_gap_latches_without_native_correction(timing_witness, monkeypatch):
    with timing_witness() as (_, debug, _):
        started = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=1,
                                          max_wait_ns=1_000_000_000)
        calls = native_executions(debug, monkeypatch)
        time.sleep(.005)
        limited = debug.clock_sync_step(timeout_ms=1000)
        assert_sync(limited, anchor=started)
        assert limited['state'] == 'desynchronized' and limited['outcome'] == 'lag-limit', limited
        assert limited['action'] == 'none' and limited['execution'] is None and not calls
        assert limited['before']['virtual_ns'] == limited['after']['virtual_ns']
        assert limited['actual_wait_ns'] == 0
        observed = debug.clock_sync_observe()
        assert observed['state'] == 'desynchronized' and observed['anchors'] == started['anchors']
        with pytest.raises(ValueError):
            debug.clock_sync_step()
        with pytest.raises(ValueError):
            debug.clock_sync_start()
        assert not calls
        stopped = debug.clock_sync_stop()
        assert stopped['state'] == 'stopped'
        restarted = debug.clock_sync_start(max_lag_ns=1_000_000_000, max_wait_ns=1_000_000_000)
        assert restarted['token'] != started['token']
        assert restarted['anchors']['host_ns'] > started['anchors']['host_ns']
        assert restarted['anchors']['virtual_ns'] == started['anchors']['virtual_ns']


def test_native_sync_early_stop_preserves_scheduled_input_first_stop_semantics(input_witness, monkeypatch):
    with input_witness() as (_, debug, symbols):
        started = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=1_000_000_000,
                                          max_wait_ns=1_000_000_000)
        debug.keyboard_key_down('a')
        armed = debug.input_schedule(5_000_000)
        point = debug.breakpoint(symbols['before_draw_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            time.sleep(.020)
            result = debug.clock_sync_step(timeout_ms=3000)
            assert_sync(result, anchor=started)
            assert result['state'] == 'interrupted' and result['outcome'] == 'interrupted', result
            native = result['execution']
            assert native['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in native['session']['stop_reason']['breakpoint_ids']
            assert native['session']['stop_reason']['native_reply'] == calls[0]['reply'][0].decode('ascii')
            assert native['clock_budget']['deadline_reached'] is False
            delivery = native['input_delivery']
            assert delivery['state'] == 'cancelled' and delivery['token'] == armed['token']
            assert delivery['dispatch_ns'] is None and delivery['requires_resolution'] is True
            assert word(debug, symbols, 'keyboard_count_ip') == 0
            with pytest.raises(ValueError):
                debug.clock_sync_step()
            assert len(calls) == 1
            debug.clock_sync_stop()
            with pytest.raises(ValueError, match='reschedule or cancel'):
                debug.run(timeout_ms=1000)
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        debug.input_cancel_pending()
        debug.clock_advance(20_000_000, timeout_ms=3000)
        assert word(debug, symbols, 'keyboard_count_ip') == 0


def test_native_sync_dos_return_remains_the_original_process_stop(timing_witness, monkeypatch):
    with timing_witness(terminating_clock) as (_, debug, _):
        started = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=1_000_000_000,
                                          max_wait_ns=1_000_000_000)
        calls = native_executions(debug, monkeypatch)
        time.sleep(.020)
        result = debug.clock_sync_step(timeout_ms=3000)
        assert_sync(result, anchor=started)
        assert result['state'] == 'interrupted' and result['outcome'] == 'interrupted', result
        native = result['execution']
        assert native['outcome'] == 'guest_exit' and native['process']['termination']['code'] == 37
        assert native['native_machine_stop']['native_reply'] == calls[0]['reply'][0].decode('ascii')
        assert native['clock_budget']['deadline_reached'] is False
        assert len(calls) == 1
        with pytest.raises(ValueError):
            debug.clock_sync_step()
        assert len(calls) == 1


def test_native_sync_journal_failure_retains_actual_execution(timing_witness, monkeypatch):
    with timing_witness(halted_clock) as (project, debug, _):
        started = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=1_000_000_000,
                                          max_wait_ns=1_000_000_000)
        with project.transaction(True):
            project.db.execute("""
                CREATE TRIGGER reject_sync_step BEFORE INSERT ON debug_events
                WHEN NEW.operation = 'machine-clock-sync-step'
                BEGIN SELECT RAISE(ABORT, 'authored timing-sync journal failure'); END
            """)
        calls = native_executions(debug, monkeypatch)
        time.sleep(.020)
        with pytest.raises(sqlite3.IntegrityError, match='authored timing-sync journal failure') as caught:
            debug.clock_sync_step(timeout_ms=3000)
        result = caught.value.result
        assert result['token'] == started['token'] and result['anchors'] == started['anchors']
        assert result['state'] in ('interrupted', 'invalidated')
        native = result['execution']
        assert native['clock_budget']['deadline_reached']
        assert native['session']['stop_reason']['native_reply'] == calls[0]['reply'][0].decode('ascii')
        assert len(calls) == 1
        with pytest.raises((ValueError, DebuggerError)):
            debug.clock_sync_step()
        assert len(calls) == 1
        assert project.db.execute(
            "SELECT count(*) FROM debug_events WHERE run=? AND operation='machine-clock-sync-step'",
            (debug.run_id,)).fetchone()[0] == 0


def test_native_timing_json_script_and_saved_evidence_preserve_anchors_after_reopen(timing_witness):
    with timing_witness(retrace_ports, retrace='precise') as (project, debug, symbols):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='timing', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            initial = invoke('debug-clock-sync-start', tolerance_ns=1_000_000_000,
                             max_lag_ns=1_000_000_000, max_wait_ns=1_000_000_000)
            assert invoke('debug-clock-sync-stop')['state'] == 'stopped'
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='clock-sync-start', tolerance_ns=1_000_000_000,
                     max_lag_ns=1_000_000_000, max_wait_ns=1_000_000_000),
                dict(op='retrace-wait', edge='enter', timeout_ms=3000),
                dict(op='clock-sync-observe'), dict(op='clock-sync-step'),
                dict(op='clock-sync-stop')])
            report = invoke('debug-script', script=script, timeout_ms=5000)
            assert report['ok'] and report['completed_steps'] == 5, report
            started, waited, observed, synchronized, stopped = [row['result'] for row in report['steps']]
            assert started['token'] != initial['token']
            assert_wait(waited, raw_timing(debug, symbols), 'enter')
            assert waited['synchronized']
            for value in (observed, synchronized, stopped):
                assert_sync(value, anchor=started)
            assert synchronized['action'] == 'none' and synchronized['outcome'] == 'within-tolerance'
            assert synchronized['execution'] is None and synchronized['actual_wait_ns'] == 0
            assert stopped['state'] == 'stopped'
            again = invoke('debug-clock-sync-stop')
            assert again['state'] == 'stopped' and again['token'] == started['token']
            assert again['anchors'] == started['anchors']
            path = project.path
        finally:
            workspace.sessions.clear()
    with Project(path) as reopened:
        assert artifact_document(reopened, report['script_artifact']) == script
        saved = artifact_document(reopened, report['artifact'])
        # The artifact retains Python receipts; respond formats address fields
        # as hex strings only after the script result has been persisted.
        assert public_addresses(saved) == {key: value for key, value in report.items() if key != 'artifact'}
        evidence = [json.loads(row[0]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation IN ('machine-retrace-wait','machine-clock-sync-step') ORDER BY sequence",
            (started['run'],))]
        assert saved['steps'][1]['result'] in evidence
        assert saved['steps'][3]['result'] in evidence
        assert reopened.debug_runs()['live_state_verified'] is False


def test_native_standard_clock_refuses_timing_controls_without_execution(timing_witness, monkeypatch):
    with timing_witness(clock='standard') as (_, debug, _):
        assert debug.capabilities['host_clock_sync'] is False
        assert debug.capabilities['retrace_wait'] is False
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        for operation in (debug.clock_sync_start, debug.retrace_wait):
            with pytest.raises(ValueError):
                operation()
        assert not calls and debug.registers() == registers
        assert debug.step(timeout_ms=1000)['outcome'] == 'step'
