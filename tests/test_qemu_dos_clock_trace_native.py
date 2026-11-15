"""Native source boundaries joined to independently observed virtual time.

These witnesses run authored DOS programs through the separately supplied
clock-enabled QEMU. A source observation is a stopped snapshot; its clock is
neither an instruction-retirement certificate nor proof that input caused it.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
import re
import sqlite3

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from support.dos_process_fixture import com_exit, digest
from support.qemu_io_fixture import raw_keyboard_mouse
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, live_word, number,
    process_record, read_bytes,
)


# MOV AX,7; INC AX; NOP; JMP $. The first two observed stop intervals end at
# 0103h and 0104h. No DOS service, input or self-modification is involved.
PROGRAM = bytes.fromhex('b80700 40 90 ebfe')


@pytest.fixture
def timed_source(clock_runtime, clock_disk, tmp_path):
    serial = 0

    @contextmanager
    def launch(source=PROGRAM, *, profile='virtual', builder=None):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'source-clock-{serial}'
        directory.mkdir()
        offsets = {}
        if builder is not None:
            source, offsets = builder(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, source)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                             qemu_clock=profile)) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) if key.endswith('_ip') else value
                                   for key, value in offsets.items()}
                        if 'ready_ip' in symbols:
                            park(debug, symbols['ready_ip'])
                        yield directory, project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == source
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def artifact_document(project, artifact):
    # Project's ExternalConnection resolves and verifies external object
    # references before returning a row; this also supports legacy blobs.
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',
                             (artifact,)).fetchone()
    assert row is not None
    data = bytes(row['data'])
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    return json.loads(data)


def temporal_range(observation, *, start_ns=None, end_ns=None):
    now = observation['virtual_ns']
    return dict(kind='virtual-time-range', run=observation['run'],
                epoch=observation['epoch'],
                native_epoch=observation['virtual_clock']['native']['epoch'],
                start_ns=now if start_ns is None else start_ns,
                end_ns=now + 1 if end_ns is None else end_ns)


def assert_clock(clock, anchor):
    assert set(clock) == {'format', 'domain', 'run', 'epoch', 'native_epoch',
                          'virtual_ns', 'icount', 'before', 'after'}
    assert clock['format'] == 'fdisbull-source-clock-1'
    assert clock['domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert clock['run'] == anchor['run']
    assert clock['epoch'] == anchor['epoch'] and re.fullmatch('[0-9a-f]{32}', clock['epoch'])
    assert clock['native_epoch'] == anchor['virtual_clock']['native']['epoch']
    for key in ('virtual_ns', 'icount', 'native_epoch'):
        assert type(clock[key]) is int and clock[key] >= 0
        assert clock['before'][key] == clock[key] == clock['after'][key]
    for side in ('before', 'after'):
        assert set(clock[side]) == {'sequence', 'virtual_ns', 'icount', 'native_epoch'}
        assert type(clock[side]['sequence']) is int and clock[side]['sequence'] > 0
    assert anchor['sequence'] < clock['before']['sequence'] < clock['after']['sequence']


def assert_clock_order(clocks):
    for before, after in zip(clocks, clocks[1:]):
        assert before['after']['sequence'] < after['before']['sequence']
        assert before['virtual_ns'] <= after['virtual_ns']
        assert before['icount'] <= after['icount']


def test_native_source_clock_brackets_survive_queries_search_and_reopen(timed_source):
    with timed_source() as (_, project, debug, _):
        database = project.path
        base = project.regions(1)[0].start
        anchor = debug.clock_observe()
        journal_before = project.db.execute(
            "SELECT count(*) FROM debug_events WHERE operation='machine-clock-observe'").fetchone()[0]
        result = debug.trace_until(
            dict(kind='pc-range', space='project', start=base + 3, end=base + 4),
            name='stopped-clock-brackets.json', max_steps=3, timeout_ms=3000)
        assert result['outcome'] == 'predicate' and result['steps'] == 1, result
        assert result['matched'] and result['exact_stop'] and result['source_window_closed']
        assert live_word(debug.registers(), 'rax', 'eax', 'ax') == 7
        document = artifact_document(project, result['trace_artifact'])
        assert len(document['events']) == 2
        clocks = [event['clock'] for event in document['events']]
        for event, clock in zip(document['events'], clocks):
            assert_clock(clock, anchor)
            assert event['observation']['instruction_completed'] is not True
        assert_clock_order(clocks)
        assert clocks[0]['virtual_ns'] == anchor['virtual_ns'] < clocks[1]['virtual_ns']
        assert clocks[0]['icount'] == anchor['counter']['value'] < clocks[1]['icount']
        assert result['matched_event']['clock'] == clocks[1]
        assert project.db.execute(
            "SELECT count(*) FROM debug_events WHERE operation='machine-clock-observe'").fetchone()[0] == journal_before

        # The end is exclusive: the snapshot exactly at the second timestamp
        # must be omitted, although it belongs to the same stopped trace.
        selected = temporal_range(anchor, start_ns=clocks[0]['virtual_ns'],
                                  end_ns=clocks[1]['virtual_ns'])
        query = project.event_trace_query(result['trace_artifact'], predicate=selected)
        assert query['matched_count'] == 1 and query['rows'][0]['pc']['project'] == base
        assert query['rows'][0]['clock'] == clocks[0]
        search = project.event_search_start(result['trace_artifact'], predicate=selected,
                                             label='first-observed-time')
        witnesses = project.event_search_results(search['artifact'])
        assert witnesses['candidate_count'] == 1 and len(witnesses['samples']) == 1
        assert witnesses['samples'][0]['clock'] == clocks[0]
    with Project(database) as reopened:
        assert reopened.event_trace_query(result['trace_artifact'], predicate=selected) == query
        assert reopened.event_search_results(search['artifact']) == witnesses
        assert artifact_document(reopened, result['trace_artifact']) == document
        assert reopened.debug_runs()['live_state_verified'] is False


def test_native_count_trace_retains_the_final_clock_without_an_extra_event(timed_source):
    with timed_source() as (_, project, debug, _):
        anchor = debug.clock_observe()
        result = debug.trace('two-intervals.json', count=2, timeout_ms=3000)
        document = artifact_document(project, result['artifact'])
        assert result['metadata']['complete'] and document['complete']
        assert document['requested_count'] == len(document['events']) == 2
        assert [event['bytes'] for event in document['events']] == ['b80700', '40']
        collector = document['collector']
        assert collector['steps'] == collector['attempted_steps'] == 2
        endpoint = collector['current_stop']
        assert number(endpoint['address']['offset']) == 0x104
        final_clock = endpoint['clock']
        assert_clock(final_clock, anchor)
        clocks = [event['clock'] for event in document['events']] + [final_clock]
        assert_clock_order(clocks)
        assert final_clock['virtual_ns'] > clocks[-2]['virtual_ns']
        assert final_clock['icount'] > clocks[-2]['icount']
        actual_stop = debug.clock_observe()
        assert final_clock['virtual_ns'] == actual_stop['virtual_ns']
        assert final_clock['icount'] == actual_stop['counter']['value']
        query = project.event_trace_query(result['artifact'], predicate=temporal_range(
            anchor, end_ns=final_clock['virtual_ns'] + 1))
        assert query['scanned_events'] == query['matched_count'] == len(query['rows']) == 2
        assert query['endpoint_clock'] == final_clock
        assert [row['clock'] for row in query['rows']] == clocks[:-1]
        assert live_word(debug.registers(), 'rax', 'eax', 'ax') == 8
        assert all(event['observation']['instruction_completed'] is None
                   for event in document['events'])


def test_native_literal_time_predicate_routes_through_json_and_saved_script(timed_source):
    with timed_source() as (_, project, debug, _):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='source-clock', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)),
                debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            anchor = invoke('debug-clock-observe')
            current = temporal_range(anchor)
            zero = invoke('debug-trace-until', until=current, max_steps=3,
                          timeout_ms=3000, name='json-current-clock.json')
            assert zero['outcome'] == 'predicate' and zero['steps'] == 0
            assert zero['matched_event']['clock']['virtual_ns'] == current['start_ns']
            future = temporal_range(anchor, start_ns=anchor['virtual_ns'] + 1,
                                    end_ns=anchor['virtual_ns'] + 1_000_000)
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='trace-until', until=future, max_steps=3, timeout_ms=3000,
                     name='script-future-clock.json')])
            assert '$' not in json.dumps(script)
            report = invoke('debug-script', script=script, timeout_ms=5000)
            assert report['ok'] and report['completed_steps'] == 1, report
            matched = report['steps'][0]['result']
            assert matched['outcome'] == 'predicate' and matched['steps'] == 1
            clock = matched['matched_event']['clock']
            assert_clock(clock, anchor)
            assert future['start_ns'] <= clock['virtual_ns'] < future['end_ns']
            saved_trace = artifact_document(project, matched['trace_artifact'])
            assert saved_trace['collector']['until'] == future
            assert artifact_document(project, report['script_artifact']) == script
            database = project.path
        finally:
            workspace.sessions.clear()
    with Project(database) as reopened:
        saved_report = artifact_document(reopened, report['artifact'])
        assert saved_report['steps'][0]['result']['matched_event']['clock'] == clock
        assert artifact_document(reopened, matched['trace_artifact']) == saved_trace


def test_native_foreign_time_identity_and_nonvirtual_profile_refuse_before_steps(timed_source):
    with timed_source() as (_, project, debug, _):
        anchor = debug.clock_observe()
        valid = temporal_range(anchor, end_ns=anchor['virtual_ns'] + 1_000_000)
        registers = debug.registers()
        artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
        foreign_values = dict(run=debug.run_id + '-foreign',
                              epoch='0' * 32 if anchor['epoch'] != '0' * 32 else '1' * 32,
                              native_epoch=valid['native_epoch'] + 1)
        for field, value in foreign_values.items():
            with pytest.raises(ValueError):
                debug.trace_until(dict(valid, **{field: value}), max_steps=3, timeout_ms=3000)
            assert debug.registers() == registers
            assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == artifacts
        after = debug.clock_observe()
        assert after['virtual_ns'] == anchor['virtual_ns']
        assert after['counter']['value'] == anchor['counter']['value']
    with timed_source(profile='instruction') as (_, project, debug, _):
        before = debug.clock_observe()
        registers = debug.registers()
        artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
        # This identity is syntactically valid, but the selected profile has no
        # native virtual-time observation with which it could be established.
        unavailable = dict(valid, run=debug.run_id)
        with pytest.raises(ValueError):
            debug.trace_until(unavailable, max_steps=3, timeout_ms=3000)
        assert debug.registers() == registers
        assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == artifacts
        assert debug.clock_observe()['counter']['value'] == before['counter']['value']


def test_native_clock_trace_preserves_a_real_watchpoint_before_time_match(timed_source):
    # MOV byte [0109],42; idle loop; independent data byte at 0109h.
    source = bytes.fromhex('c606090142 ebfe 000000')
    with timed_source(source) as (_, project, debug, _):
        info = process_record(debug)
        watched = com_address(info, 0x109)
        point = debug.breakpoint(watched, access='w', length=1)
        anchor = debug.clock_observe()
        until = temporal_range(anchor, start_ns=anchor['virtual_ns'] + 1,
                               end_ns=anchor['virtual_ns'] + 1_000_000)
        result = debug.trace_until(until, max_steps=3, timeout_ms=3000)
        assert result['outcome'] == 'foreign_stop', result
        assert result['attempted_steps'] == 1 and result['steps'] == 0
        assert not result['matched'] and not result['exact_stop'] and not result['source_window_closed']
        native = result['foreign_stop']
        assert native['outcome'] == 'watchpoint'
        assert 'watch:' in native['session']['stop_reason']['native_reply']
        assert point['breakpoint_id'] in native['session']['stop_reason']['breakpoint_ids']
        assert point['breakpoint_id'] in debug.breakpoints
        assert read_bytes(debug, watched, 1) == b'\x42'
        document = artifact_document(project, result['trace_artifact'])
        assert len(document['events']) == 1 and not document['window']['closed']
        assert_clock(document['events'][0]['clock'], anchor)
        assert document['events'][0]['observation']['instruction_completed'] is None
        assert document['collector']['current_stop']['session']['stop_reason'] == native['session']['stop_reason']
        assert debug.status()['state'] == 'stopped'


def test_native_step_survives_rejected_following_clock_evidence(timed_source, monkeypatch):
    with timed_source() as (_, project, debug, _):
        anchor = debug.clock_observe()
        step, qmp_call = debug.step, debug.vm.qmp.call
        executed, corrupted = [], []

        def observe_step(*args, **kwargs):
            native = step(*args, **kwargs)
            executed.append(deepcopy(native))
            return native

        def reject_next_clock(command, *args, **kwargs):
            value = qmp_call(command, *args, **kwargs)
            if command == 'x-fdisbull-query-clock' and executed and not corrupted:
                corrupted.append(command)
                # Fault injection occurs after the real QMP response and an
                # actual native step, not at the collector or saved artifact.
                return dict(value, **{'virtual-ns': True})
            return value

        monkeypatch.setattr(debug, 'step', observe_step)
        monkeypatch.setattr(debug.vm.qmp, 'call', reject_next_clock)
        result = debug.trace_until(dict(kind='register', register='ax', equals=99),
                                   max_steps=3, timeout_ms=3000)
        assert result['outcome'] == 'error' and result['error']['type'] == 'DebuggerError', result
        assert result['attempted_steps'] == result['steps'] == len(executed) == 1
        assert corrupted == ['x-fdisbull-query-clock']
        assert not result['matched'] and not result['exact_stop'] and not result['source_window_closed']
        assert result['current_stop']['session']['stop_reason'] == executed[0]['session']['stop_reason']
        assert result['current_stop']['timed_out'] is False
        assert 'clock' not in result['current_stop'], 'A rejected bracket cannot certify the endpoint clock'
        assert debug.vm.process.poll() is not None
        assert debug.dos_process_info()['source_mapping']['live'] is False
        document = artifact_document(project, result['trace_artifact'])
        assert len(document['events']) == 1 and not document['window']['closed']
        assert_clock(document['events'][0]['clock'], anchor)
        assert document['events'][0]['observation']['instruction_completed'] is None
        assert document['collector']['current_stop'] == result['current_stop']


@pytest.mark.parametrize('failure', ['register-observation', 'machine-step-journal'])
def test_native_clock_trace_retains_stop_when_step_postprocessing_fails(
        timed_source, monkeypatch, failure):
    with timed_source() as (_, project, debug, _):
        anchor = debug.clock_observe()
        remote = debug.vm.debugger()
        execute, qmp_call = remote.execute, debug.vm.qmp.call
        replies, rejected_registers = [], []

        def observe_execution(command, *args, **kwargs):
            reply = execute(command, *args, **kwargs)
            if command == 's':
                replies.append(reply)
            return reply

        def reject_register_observation(command, *args, **kwargs):
            value = qmp_call(command, *args, **kwargs)
            if (command == 'human-monitor-command' and replies
                    and not rejected_registers):
                # Both the native stop and HMP register response were actually
                # received; only the subsequent host observation is rejected.
                rejected_registers.append(value)
                raise OSError('authored post-stop register observation failure')
            return value

        monkeypatch.setattr(remote, 'execute', observe_execution)
        if failure == 'register-observation':
            monkeypatch.setattr(debug.vm.qmp, 'call', reject_register_observation)
        else:
            with project.transaction(True):
                project.db.execute("""
                    CREATE TRIGGER reject_machine_step BEFORE INSERT ON debug_events
                    WHEN NEW.operation = 'machine-step'
                    BEGIN SELECT RAISE(ABORT, 'authored machine-step journal failure'); END
                """)
        result = debug.trace_until(dict(kind='register', register='ax', equals=99),
                                   max_steps=3, timeout_ms=3000)
        assert result['outcome'] == 'error', result
        assert result['error']['type'] == (
            'OSError' if failure == 'register-observation' else 'IntegrityError')
        assert result['attempted_steps'] == len(replies) == 1
        assert result['steps'] == 0, 'The native step never returned a classified result to the collector'
        reply, timed_out = replies[0]
        assert reply[:1] in (b'T', b'S') and timed_out is False
        native = result['current_stop']
        assert native['session']['stop_reason']['native_reply'] == reply.decode('ascii')
        assert native['timed_out'] is False
        assert 'clock' not in native, 'No stable source bracket was obtained after this stop'
        if failure == 'register-observation':
            assert len(rejected_registers) == 1 and rejected_registers[0]
            assert native['registers'] is None
            assert native['session']['stop_reason']['classification_complete'] is False
        else:
            assert native['outcome'] == 'step'
            assert live_word(native['registers'], 'rax', 'eax', 'ax') == 7
        assert not result['matched'] and not result['exact_stop'] and not result['source_window_closed']
        assert debug.vm.process.poll() is not None
        assert debug.dos_process_info()['source_mapping']['live'] is False
        assert project.db.execute(
            "SELECT count(*) FROM debug_events WHERE run=? AND operation='machine-step'",
            (debug.run_id,)).fetchone()[0] == 0
        document = artifact_document(project, result['trace_artifact'])
        assert len(document['events']) == 1 and not document['window']['closed']
        assert_clock(document['events'][0]['clock'], anchor)
        assert document['events'][0]['observation']['instruction_completed'] is None
        assert document['collector']['current_stop'] == native


def test_native_dos_return_journal_failure_preserves_observed_guest_exit(
        timed_source, monkeypatch):
    with timed_source(com_exit(37)) as (_, project, debug, _):
        remote = debug.vm.debugger()
        execute = remote.execute
        replies = []

        def observe_execution(command, *args, **kwargs):
            reply = execute(command, *args, **kwargs)
            if command == 'c':
                replies.append(reply)
            return reply

        monkeypatch.setattr(remote, 'execute', observe_execution)
        with project.transaction(True):
            project.db.execute("""
                CREATE TRIGGER reject_dos_return BEFORE INSERT ON debug_events
                WHEN NEW.operation = 'dos-process-return'
                BEGIN SELECT RAISE(ABORT, 'authored DOS-return journal failure'); END
            """)
        with pytest.raises(sqlite3.IntegrityError, match='authored DOS-return journal failure') as caught:
            debug.run(timeout_ms=3000)
        assert len(replies) == 1
        reply, timed_out = replies[0]
        assert reply[:1] in (b'T', b'S') and timed_out is False
        result = caught.value.result
        assert result['outcome'] == 'guest_exit', result
        assert result['session']['state'] == 'stopped' and result['timed_out'] is False
        assert result['native_machine_stop']['native_reply'] == reply.decode('ascii')
        assert result['native_machine_stop']['kind'] == 'breakpoint'
        termination = result['process']['termination']
        assert termination['type'] == 'normal' and termination['code'] == 37
        assert result['process']['state'] == 'exited'
        assert result['process']['source_mapping']['live'] is False
        assert result['session']['stop_reason']['kind'] == result['stop']['trigger'] == 'guest_exit'
        assert result['session']['stop_reason']['guest_exit'] == termination
        assert result['stop']['causing_instruction'] is result['stop']['instruction_completed'] is None
        assert debug.vm.process.poll() is not None
        assert project.db.execute(
            "SELECT count(*) FROM debug_events WHERE run=? AND operation='dos-process-return'",
            (debug.run_id,)).fetchone()[0] == 0
        # The already-persisted machine stop still has its independent native
        # classification, even though the DOS return journal insert failed.
        row = project.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation='machine-run' ORDER BY sequence DESC LIMIT 1",
            (debug.run_id,)).fetchone()
        assert json.loads(row['evidence'])['session']['stop_reason'] == result['native_machine_stop']


def test_native_source_clock_joins_input_dispatch_and_renderer_evidence(timed_source):
    with timed_source(builder=raw_keyboard_mouse) as (_, project, debug, symbols):
        assert read_bytes(debug, symbols['setup_status_ip'], 2) == b'\x01\x00'
        anchor = debug.clock_observe()
        before = debug.trace('before-input-time.json', count=2, timeout_ms=3000)
        before_events = artifact_document(project, before['artifact'])['events']
        display = debug.display_start(period_ns=2_000_000)
        lease = debug.keyboard_key_down('a')['lease']
        armed = debug.input_schedule(5_000_000)
        stopped = debug.clock_advance(20_000_000, timeout_ms=5000)
        delivery = stopped['input_delivery']
        assert delivery['state'] == 'dispatched' and delivery['token'] == armed['token']
        assert read_bytes(debug, symbols['keyboard_bytes_ip'], 1) == b'\x1e'
        assert debug.input_state()['leases'][lease]['make'] == 'native_dispatched'
        capture = debug.capture_display('input-time-publication.png')
        published = capture['metadata']
        assert delivery['guest_consumed'] is delivery['device_queue_accepted'] is None
        assert published['completed_guest_frame'] is None
        assert published['epoch'] == delivery['epoch'] == display['epoch'] == anchor['epoch']
        assert published['published_ns'] >= delivery['dispatch_ns']
        pixels = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                    (capture['artifact'],)).fetchone()[0]
        with Image.open(io.BytesIO(pixels)) as image:
            image = image.convert('RGB')
            assert image.width % 320 == image.height % 200 == 0
            assert image.getpixel((10 * (image.width // 320), 10 * (image.height // 200))) == (255, 0, 0)

        # Park in the authored main loop, so a PIT/IRQ boundary cannot turn
        # this temporal join into a claim about an unbound BIOS instruction.
        park(debug, symbols['after_draw_ip'])
        after = debug.trace('after-input-time.json', count=3, timeout_ms=3000)
        after_events = artifact_document(project, after['artifact'])['events']
        assert len(before_events) == 2 and len(after_events) == 3
        for event in before_events + after_events:
            assert_clock(event['clock'], anchor)
            assert event['source_qualification']['qualified'] is True
            assert event['observation']['instruction_completed'] is not True
        assert max(event['clock']['virtual_ns'] for event in before_events) < delivery['dispatch_ns']
        assert min(event['clock']['virtual_ns'] for event in after_events) >= published['published_ns']
        assert all(event['clock']['native_epoch'] == delivery['native']['epoch'] == published['native']['epoch']
                   for event in after_events)
        selected = temporal_range(anchor, start_ns=delivery['dispatch_ns'],
                                  end_ns=after_events[-1]['clock']['virtual_ns'] + 1)
        assert project.event_trace_query(before['artifact'], predicate=selected)['matched_count'] == 0
        joined = project.event_trace_query(after['artifact'], predicate=selected)
        assert joined['matched_count'] == 3
        assert [row['clock'] for row in joined['rows']] == [event['clock'] for event in after_events]
