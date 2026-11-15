"""Independent IRQ1 witnesses for a finite, passively armed native chord.

Expected edge order and relative delays come from the caller's declared plan.
Guest scancodes prove consumption in this authored fixture only. Native
callback receipts do not generally prove FIFO acceptance or physical release.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import time
import uuid

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime
from test_qemu_dos_process_native import read_bytes
from test_qemu_input_retrace_native import (
    frozen, key_bytes, period_ns, retrace_input_witness, word,
)
from test_qemu_retrace_native import artifact_document, raw_timing
from test_qemu_timing_native import assert_sync, native_executions


COMMAND = 'x-fdisbull-arm-keyboard-press'
EDGE_NS = 2_000_000
MS_NS = 1_000_000
SCANCODES = {'a': 0x1e, 'shift': 0x2a, 'ctrl': 0x1d, 'alt': 0x38}


def expected_plan(key='a', modifiers=(), hold_ms=7):
    """Independent finite chord order; no production planner is imported."""
    return ([{'key': name, 'down': True, 'delay-ns': EDGE_NS}
             for name in (*modifiers, key)]
            + [{'key': key, 'down': False, 'delay-ns': hold_ms * MS_NS}]
            + [{'key': name, 'down': False, 'delay-ns': EDGE_NS}
               for name in reversed(modifiers)])


def expected_bytes(plan):
    return bytes(SCANCODES[step['key']] | (0 if step['down'] else 0x80) for step in plan)


def nominal_ns(plan):
    return sum(step['delay-ns'] for step in plan)


def assert_native_press(native, *, key='a', modifiers=(), hold_ms=7, gap_ms=1000,
                        state, dispatched_count):
    plan = expected_plan(key, modifiers, hold_ms)
    assert native['api-version'] == 1 and native['state'] == state
    assert native['event-count'] == len(plan) and 'retrace' not in native
    press = native['press']
    assert set(press) == {'key', 'modifiers', 'hold-ms', 'gap-ms', 'steps', 'dispatched-count'}
    assert press['key'] == key and press['modifiers'] == list(modifiers)
    assert press['hold-ms'] == hold_ms and press['gap-ms'] == gap_ms
    assert type(press['dispatched-count']) is int and press['dispatched-count'] == dispatched_count
    assert len(press['steps']) == len(plan)
    assert native['deadline-ns'] == native['start-ns'] + EDGE_NS
    for index, (step, expected) in enumerate(zip(press['steps'], plan, strict=True)):
        assert {field: step[field] for field in ('key', 'down', 'delay-ns')} == expected
        known_deadline = index <= dispatched_count
        delivered = index < dispatched_count
        fields = {'key', 'down', 'delay-ns'}
        if known_deadline:
            fields.add('deadline-ns')
            origin = native['start-ns'] if index == 0 else press['steps'][index - 1]['dispatch-ns']
            assert step['deadline-ns'] == origin + expected['delay-ns']
        if delivered:
            fields.add('dispatch-ns')
            assert step['deadline-ns'] <= step['dispatch-ns'] <= native['virtual-ns']
        assert set(step) == fields
    if state == 'armed':
        assert dispatched_count == 0
        assert 'terminal-ns' not in native and 'dispatch-ns' not in native
    elif state == 'dispatched':
        assert dispatched_count == len(plan)
        assert native['dispatch-ns'] == native['terminal-ns'] == press['steps'][-1]['dispatch-ns']
    else:
        assert state == 'cancelled' and 0 <= dispatched_count < len(plan)
        assert 'dispatch-ns' not in native
        assert native['start-ns'] <= native['terminal-ns'] <= native['virtual-ns']
        if dispatched_count:
            assert press['steps'][dispatched_count - 1]['dispatch-ns'] <= native['terminal-ns']
    return plan


def assert_press(value, *, key='a', modifiers=(), hold_ms=7, gap_ms=1000,
                 state, dispatched_count):
    assert value['format'] == 'fdisbull-qemu-scheduled-input-1'
    assert value['state'] == state and value['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert value['run'] == value['clock']['run']
    assert value['epoch'] == value['clock']['epoch']
    assert value['native']['epoch'] == value['clock']['virtual_clock']['native']['epoch']
    assert value['observed_ns'] == value['clock']['virtual_ns'] == value['native']['virtual-ns']
    assert value['token'] == value['native']['token']
    assert value['start_ns'] == value['native']['start-ns']
    assert value['deadline_ns'] == value['native']['deadline-ns']
    assert value['terminal_ns'] == value['native'].get('terminal-ns')
    assert value['dispatch_ns'] == value['native'].get('dispatch-ns')
    assert value['lateness_ns'] is None  # A whole chord is not one late edge.
    assert value['guest_consumed'] is value['device_queue_accepted'] is None
    assert value['requires_resolution'] is (state == 'cancelled')
    plan = assert_native_press(value['native'], key=key, modifiers=modifiers,
        hold_ms=hold_ms, gap_ms=gap_ms, state=state, dispatched_count=dispatched_count)
    assert value['edge_count'] == len(plan) == len(value['sequences'])
    assert len(set(value['sequences'])) == len(plan)
    public = value['press']
    assert public['format'] == 'fdisbull-keyboard-press-1'
    assert public['key'] == key and public['modifiers'] == list(modifiers)
    assert public['hold_ms'] == hold_ms and public['gap_ms'] == gap_ms
    assert public['gap_applied'] is False
    assert public['dispatched_count'] == dispatched_count
    assert public['undispatched_count'] == len(plan) - dispatched_count
    assert len(public['steps']) == len(plan)
    leases = {}
    for index, (step, native_step, expected) in enumerate(
            zip(public['steps'], value['native']['press']['steps'], plan, strict=True)):
        assert step['sequence'] == value['sequences'][index]
        assert step['key'] == step['qcode'] == expected['key']
        assert step['down'] is expected['down'] and step['delay_ns'] == expected['delay-ns']
        assert step['deadline_ns'] == native_step.get('deadline-ns')
        assert step['dispatch_ns'] == native_step.get('dispatch-ns')
        lateness = (native_step['dispatch-ns'] - native_step['deadline-ns']
                    if 'dispatch-ns' in native_step else None)
        assert step['lateness_ns'] == lateness
        if expected['down']:
            assert step['lease'] not in leases.values()
            leases[expected['key']] = step['lease']
        else:
            assert step['lease'] == leases[expected['key']]
    return plan


def assert_transition(result, armed, *, key='a', modifiers=(), hold_ms=7, gap_ms=1000,
                      state, dispatched_count):
    value = result['input_delivery']
    assert_press(value, key=key, modifiers=modifiers, hold_ms=hold_ms,
                 gap_ms=gap_ms, state=state, dispatched_count=dispatched_count)
    for field in ('token', 'run', 'epoch', 'session_id', 'start_ns', 'deadline_ns', 'sequences', 'edge_count'):
        assert value[field] == armed[field]
    for before, after in zip(armed['press']['steps'], value['press']['steps'], strict=True):
        for field in ('sequence', 'lease', 'key', 'qcode', 'down', 'delay_ns'):
            assert before[field] == after[field]
    budget = result['clock_budget']
    assert value['observed_ns'] == budget['stopped_ns']
    assert value['terminal_ns'] <= budget['stopped_ns']
    for step in value['native']['press']['steps'][:dispatched_count]:
        assert step['dispatch-ns'] < budget['deadline_ns']
    if state == 'cancelled':
        assert value['terminal_ns'] == value['observed_ns']
    return value


@pytest.mark.parametrize('halted', [False, True], ids=['busy', 'hlt'])
@pytest.mark.parametrize('modifiers', [(), ('shift',), ('shift', 'ctrl', 'alt')],
                         ids=['plain', 'shift', 'caller-order-full-chord'])
def test_native_keyboard_press_is_passive_and_dispatches_the_declared_relative_chord(
        retrace_input_witness, monkeypatch, halted, modifiers):
    with retrace_input_witness(halted=halted, profile='standard') as (_, debug, symbols):
        assert debug.capabilities['virtual_keyboard_press'] is True
        assert debug.capabilities['timed_input'] is False
        before = debug.clock_observe()
        calls = native_executions(debug, monkeypatch)
        armed = debug.keyboard.press('a', modifiers=modifiers, hold_ms=7, gap_ms=1000)
        plan = assert_press(armed, modifiers=modifiers, state='armed', dispatched_count=0)
        assert not calls and word(debug, symbols, 'key_count_ip') == 0
        observed = debug.input_schedule_observe()
        assert observed['native'] == armed['native'] and observed['press'] == armed['press']
        paused = debug.clock_observe()
        assert paused['virtual_ns'] == before['virtual_ns'] == armed['start_ns']
        assert paused['counter']['value'] == before['counter']['value']
        state = debug.keyboard.state()
        assert state['pending_edges'] == len(plan) and len(state['leases']) == len(modifiers) + 1
        assert all(lease['make'] == lease['release'] == 'python_pending' for lease in state['leases'].values())

        delta = nominal_ns(plan) + 5 * MS_NS
        result = debug.clock_advance(delta, timeout_ms=5000)
        budget_receipt(result, delta)
        delivered = assert_transition(result, armed, modifiers=modifiers,
                                     state='dispatched', dispatched_count=len(plan))
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
        assert key_bytes(debug, symbols, len(plan)) == expected_bytes(plan)
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        native_steps = delivered['native']['press']['steps']
        make_index, break_index = len(modifiers), len(modifiers) + 1
        assert native_steps[break_index]['dispatch-ns'] - native_steps[make_index]['dispatch-ns'] >= 7 * MS_NS
        # An odd millisecond hold is not integral in the declared 128 ns
        # instruction quantum. The busy chord exposes actual callback lateness;
        # the following modifier break must start its delay at that real time.
        if not halted and len(modifiers) == 3:
            main_break = native_steps[break_index]
            assert main_break['dispatch-ns'] > main_break['deadline-ns'], delivered
            assert native_steps[break_index + 1]['deadline-ns'] == main_break['dispatch-ns'] + EDGE_NS
        # gap_ms=1000 is retained, but cannot be a tail timer: this bounded
        # operation ends much earlier and the whole chord is already complete.
        assert result['clock_budget']['stopped_ns'] < armed['start_ns'] + 1000 * MS_NS
        after = debug.clock_observe()
        if halted:
            instructions = after['counter']['value'] - before['counter']['value']
            assert 0 < instructions < 2000
            assert after['virtual_ns'] - before['virtual_ns'] > instructions * 128
            assert word(debug, symbols, 'wakes_ip') == len(plan)
        debug.clock_advance(3 * MS_NS, timeout_ms=3000)
        retained = debug.input_schedule_observe()
        assert retained['press'] == delivered['press']
        assert frozen(retained['native']) == frozen(delivered['native'])
        assert key_bytes(debug, symbols, len(plan)) == expected_bytes(plan)


def test_native_keyboard_press_first_stop_before_make_discards_only_unsent_edges(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness(profile='standard') as (_, debug, symbols):
        armed = debug.keyboard_press('a', hold_ms=7, gap_ms=1000)
        assert_press(armed, state='armed', dispatched_count=0)
        lease = armed['press']['steps'][0]['lease']
        point = debug.breakpoint(symbols['main_loop_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(20 * MS_NS, timeout_ms=5000)
            budget_receipt(result, 20 * MS_NS, reached=False)
            cancelled = assert_transition(result, armed, state='cancelled', dispatched_count=0)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert cancelled['terminal_ns'] < cancelled['deadline_ns']
            assert word(debug, symbols, 'key_count_ip') == 0
            assert debug.input_state()['pending_edges'] == 2
            with pytest.raises(ValueError):
                debug.run(timeout_ms=1000)
            with pytest.raises(ValueError):
                debug.input_schedule(EDGE_NS)
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 2 and resolved['cancelled_leases'] == [lease]
        assert resolved['retained_dispatched_holds'] == []
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        debug.clock_advance(20 * MS_NS, timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0
        assert frozen(debug.input_schedule_observe()['native']) == frozen(cancelled['native'])


def test_native_keyboard_press_first_stop_after_make_retains_hold_until_explicit_release(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness(profile='precise') as (_, debug, symbols):
        armed = debug.keyboard_press('a', hold_ms=40, gap_ms=1000)
        lease = armed['press']['steps'][0]['lease']
        point = debug.breakpoint(symbols['input_seen_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(50 * MS_NS, timeout_ms=5000)
            budget_receipt(result, 50 * MS_NS, reached=False)
            cancelled = assert_transition(result, armed, hold_ms=40,
                                          state='cancelled', dispatched_count=1)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert key_bytes(debug, symbols, 1) == b'\x1e'
            steps = cancelled['native']['press']['steps']
            assert steps[0]['dispatch-ns'] <= cancelled['terminal_ns'] < steps[1]['deadline-ns']
            assert cancelled['dispatch_ns'] is None  # One make is not a completed press.
            state = debug.keyboard.state()
            assert state['pending_edges'] == 1
            assert state['pending'][0]['sequence'] == armed['sequences'][1]
            assert state['leases'][lease]['make'] == 'native_dispatched'
            assert state['leases'][lease]['release'] == 'python_pending'
            for _ in range(2):
                assert debug.input_schedule_observe()['native'] == cancelled['native']
                assert debug.input_state()['pending'] == state['pending']
                assert debug.input_state()['leases'] == state['leases']
            for operation in (lambda: debug.run(timeout_ms=1000),
                              lambda: debug.input_schedule(EDGE_NS),
                              debug.input_schedule_retrace,
                              lambda: debug.keyboard_press('b')):
                with pytest.raises(ValueError):
                    operation()
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 1 and resolved['cancelled_leases'] == []
        assert resolved['retained_dispatched_holds'] == [lease]
        assert debug.input_state()['leases'][lease]['make'] == 'native_dispatched'
        assert debug.input_state()['leases'][lease]['release'] is None
        debug.clock_advance(50 * MS_NS, timeout_ms=5000)
        assert key_bytes(debug, symbols, 1) == b'\x1e'
        debug.keyboard_key_up(lease)
        ordinary = debug.input_schedule(EDGE_NS)
        assert 'press' not in ordinary and 'press' not in ordinary['native']
        released = debug.clock_advance(5 * MS_NS, timeout_ms=5000)['input_delivery']
        assert released['state'] == 'dispatched' and released['token'] == ordinary['token']
        assert 'press' not in released and 'press' not in released['native']
        assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


@pytest.mark.parametrize('boundary', ['make', 'release'])
@pytest.mark.parametrize('budget_first', [False, True], ids=['press-command-first', 'budget-command-first'])
def test_native_keyboard_press_equal_budget_keeps_only_the_prefix_before_cutoff(
        retrace_input_witness, boundary, budget_first):
    """Make covers both true timer insertion orders.

    Release covers both command-arm orders. Its timer is always inserted after
    the budget: the release deadline becomes known only at actual make, and
    stopping then to arm a budget would already cancel the remaining suffix.
    """
    with retrace_input_witness(halted=True, profile='standard') as (_, debug, symbols):
        before = debug.clock_observe()
        expected_count = 0 if boundary == 'make' else 1
        delta = EDGE_NS if boundary == 'make' else EDGE_NS + 7 * MS_NS
        if budget_first:
            budget_token, press_token = uuid.uuid4().hex, uuid.uuid4().hex
            clock_arm = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                {'token': budget_token, 'delta-ns': delta})
            native_arm = debug.vm.qmp.call(COMMAND,
                {'token': press_token, 'key': 'a', 'modifiers': [], 'hold-ms': 7, 'gap-ms': 1000})
            assert_native_press(native_arm, state='armed', dispatched_count=0)
            assert native_arm['start-ns'] == clock_arm['budget-start-ns'] == before['virtual_ns']
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'stopped' and result['timed_out'] is False
            assert result['session']['stop_reason']['native_reply'][:3] in ('T02', 'S02')
            stopped = debug.vm.qmp.call('x-fdisbull-query-clock')
            native = debug.vm.qmp.call('x-fdisbull-query-input')
            assert stopped['budget-state'] == 'stopped'
            for field in ('epoch', 'budget-token', 'budget-start-ns', 'budget-deadline-ns'):
                assert stopped[field] == clock_arm[field]
            cutoff = stopped['budget-deadline-ns']
            assert cutoff <= stopped['budget-fired-ns'] <= stopped['budget-stopped-ns'] == stopped['virtual-ns']
            assert_native_press(native, state='cancelled', dispatched_count=expected_count)
            assert native['terminal-ns'] == stopped['budget-stopped-ns'] == native['virtual-ns']
            cleaned = debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': budget_token})
            assert cleaned == {**stopped, 'budget-state': 'cancelled'}
            assert debug.vm.qmp.call('x-fdisbull-query-input') == native
        else:
            armed = debug.keyboard_press('a', hold_ms=7, gap_ms=1000)
            assert_press(armed, state='armed', dispatched_count=0)
            result = debug.clock_advance(delta, timeout_ms=5000)
            budget_receipt(result, delta)
            cancelled = assert_transition(result, armed, state='cancelled', dispatched_count=expected_count)
            native = cancelled['native']
            cutoff = result['clock_budget']['deadline_ns']
            assert debug.input_state()['pending_edges'] == 2 - expected_count
        assert native['press']['steps'][expected_count]['deadline-ns'] == cutoff
        assert native['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert 'dispatch-ns' not in native
        assert all(step['dispatch-ns'] < cutoff for step in native['press']['steps'][:expected_count])
        assert word(debug, symbols, 'wakes_ip') == expected_count
        if expected_count:
            assert key_bytes(debug, symbols, 1) == b'\x1e'
        else:
            assert word(debug, symbols, 'key_count_ip') == 0
        if budget_first:
            # This branch explicitly owns the native wire sequence, rather
            # than pretending raw commands created Python keyboard leases.
            assert debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': press_token}) == native
        else:
            resolved = debug.input_cancel_pending()
            assert resolved['cancelled_edges'] == 2 - expected_count
            if expected_count:
                lease = armed['press']['steps'][0]['lease']
                assert resolved['retained_dispatched_holds'] == [lease]
                assert debug.input_state()['leases'][lease]['release'] is None
            else:
                assert resolved['retained_dispatched_holds'] == []
        debug.clock_advance(20 * MS_NS, timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == expected_count
        if expected_count:
            if budget_first:
                release = debug.vm.qmp.call('x-fdisbull-arm-input', {
                    'token': uuid.uuid4().hex, 'delta-ns': EDGE_NS,
                    'events': [dict(type='key', data=dict(key=dict(type='qcode', data='a'), down=False))]})
                assert 'press' not in release
            else:
                debug.keyboard_key_up(lease)
                release = debug.input_schedule(EDGE_NS)
                assert 'press' not in release['native']
            debug.clock_advance(5 * MS_NS, timeout_ms=5000)
            assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_keyboard_press_old_five_patch_binary_refuses_without_losing_existing_input(
        retrace_input_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_KEYBOARD_PRESS_LEGACY')
    if not legacy:
        message = 'Set FDISBULL_QEMU_KEYBOARD_PRESS_LEGACY to the retained five-patch QEMU'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    with retrace_input_witness(profile='precise', executable=legacy) as (_, debug, symbols):
        assert COMMAND not in debug.vm.qmp_commands
        assert debug.capabilities['virtual_keyboard_press'] is False
        assert debug.capabilities['timed_input'] is False
        assert debug.capabilities['retrace_input_schedule'] is True
        before = debug.clock_observe()
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        for operation in (lambda: debug.keyboard.press('a'), lambda: debug.keyboard.type('a')):
            with pytest.raises(ValueError):
                operation()
        assert not calls and debug.registers() == registers
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        lease = debug.keyboard_key_down('a')['lease']
        with pytest.raises(ValueError):
            debug.keyboard_press('b')
        assert debug.input_state()['pending_edges'] == 1
        assert debug.input_state()['leases'][lease]['make'] == 'python_pending'
        raw = raw_timing(debug, symbols)
        armed = debug.input_schedule_retrace()
        assert 'press' not in armed['native']
        delivered = debug.clock_advance(2 * period_ns(raw), timeout_ms=5000)['input_delivery']
        assert delivered['state'] == 'dispatched' and delivered['token'] == armed['token']
        assert delivered['retrace']['dispatch_phase_verified'] is True
        assert key_bytes(debug, symbols, 1) == b'\x1e'
        debug.keyboard_key_up(lease)
        ordinary = debug.input_schedule(EDGE_NS)
        result = debug.clock_advance(5 * MS_NS, timeout_ms=5000)
        assert result['input_delivery']['state'] == 'dispatched'
        assert result['input_delivery']['token'] == ordinary['token']
        assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
        assert debug.input_state()['leases'] == {}


def test_native_keyboard_press_json_script_journal_and_reopen_keep_actual_edge_evidence(
        retrace_input_witness):
    with retrace_input_witness(profile='precise') as (project, debug, symbols):
        # A new press clears a retained retrace descriptor, and a subsequent
        # retrace arm clears the completed press descriptor. Neither passive
        # setup arm here is allowed to emit a scancode.
        debug.keyboard_key_down('a')
        previous = debug.input_schedule_retrace()
        assert 'retrace' in previous['native']
        debug.input_cancel_pending()
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='keyboard-press', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            armed = invoke('debug-keyboard-press', key='a', modifiers=['shift'], hold_ms=7, gap_ms=1000)
            first_plan = assert_press(armed, modifiers=('shift',), state='armed', dispatched_count=0)
            assert 'retrace' not in armed['native'] and word(debug, symbols, 'key_count_ip') == 0
            first = invoke('debug-clock-advance', delta_ns=nominal_ns(first_plan) + 5 * MS_NS, timeout_ms=5000)
            assert_transition(first, armed, modifiers=('shift',), state='dispatched', dispatched_count=4)
            assert key_bytes(debug, symbols, 4) == expected_bytes(first_plan)
            full_modifiers = ('shift', 'ctrl', 'alt')
            full_plan = expected_plan(modifiers=full_modifiers)
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='keyboard.press', key='a', modifiers=list(full_modifiers), hold_ms=7, gap_ms=1000),
                dict(op='clock-advance', delta_ns=nominal_ns(full_plan) + 5 * MS_NS, timeout_ms=5000),
                dict(op='input-schedule-observe')])
            report = invoke('debug-script', script=script, timeout_ms=10000)
            assert report['ok'] and report['completed_steps'] == len(script['steps']), report
            rearmed, second, observed = [row['result'] for row in report['steps']]
            assert_press(rearmed, modifiers=full_modifiers, state='armed', dispatched_count=0)
            delivered = assert_transition(second, rearmed, modifiers=full_modifiers,
                                          state='dispatched', dispatched_count=8)
            assert rearmed['token'] != armed['token']
            assert observed['native'] == delivered['native'] and observed['press'] == delivered['press']
            assert key_bytes(debug, symbols, 12) == expected_bytes(first_plan) + expected_bytes(full_plan)
            assert invoke('debug-keyboard-state')['leases'] == {}
            debug.keyboard_key_down('a')
            following = debug.input_schedule_retrace(edge='exit')
            assert 'press' not in following and 'press' not in following['native']
            assert 'retrace' in following['native']
            debug.input_cancel_pending()
            assert word(debug, symbols, 'key_count_ip') == 12
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


def test_native_keyboard_press_one_explicit_clock_sync_step_drives_the_owned_chord(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness(halted=True, profile='standard') as (_, debug, symbols):
        mapping = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=2_000_000_000,
                                         max_wait_ns=2_000_000_000)
        calls = native_executions(debug, monkeypatch)
        armed = debug.keyboard.press('a', hold_ms=3, gap_ms=1000)
        plan = assert_press(armed, hold_ms=3, state='armed', dispatched_count=0)
        assert armed['start_ns'] == mapping['anchors']['virtual_ns']
        assert armed['epoch'] == mapping['epoch'] and not calls
        # Real caller work belongs to the explicit mapping. This is test-side
        # elapsed work, not an implicit sleep performed by keyboard.press.
        time.sleep(.025)
        synchronized = debug.clock_sync_step(timeout_ms=5000)
        assert_sync(synchronized, anchor=mapping)
        assert synchronized['action'] == 'advance' and synchronized['outcome'] == 'advanced'
        assert synchronized['state'] == 'active'
        assert synchronized['target_ns'] >= armed['start_ns'] + nominal_ns(plan)
        execution = synchronized['execution']
        assert_transition(execution, armed, hold_ms=3, state='dispatched', dispatched_count=2)
        assert execution['clock_budget']['deadline_ns'] == synchronized['target_ns']
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert key_bytes(debug, symbols, 2) == b'\x1e\x9e'
        assert word(debug, symbols, 'wakes_ip') == 2
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        stopped = debug.clock_sync_stop()
        assert stopped['token'] == mapping['token'] and stopped['anchors'] == mapping['anchors']
        assert len(calls) == 1


def test_native_keyboard_press_command_rejections_do_not_consume_the_owner_token(
        retrace_input_witness, monkeypatch):
    with retrace_input_witness(profile='standard') as (_, debug, symbols):
        before = debug.clock_observe()
        idle = debug.vm.qmp.call('x-fdisbull-query-input')
        assert idle['state'] == 'idle' and idle['event-count'] == 0
        arguments = {'token': uuid.uuid4().hex, 'key': 'a', 'modifiers': [],
                     'hold-ms': 7, 'gap-ms': 1000}
        invalid = [
            {'hold-ms': 0}, {'hold-ms': 1001}, {'gap-ms': 0}, {'gap-ms': 1001},
            {'modifiers': ['ctrl', 'ctrl']}, {'modifiers': ['a']},
            {'modifiers': ['ctrl', 'alt', 'shift', 'ctrl']},
            {'key': 'shift', 'modifiers': ['shift']},
        ]
        calls = native_executions(debug, monkeypatch)
        for change in invalid:
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(COMMAND, {**arguments, **change})
            assert debug.vm.qmp.call('x-fdisbull-query-input') == idle
            clock = debug.clock_observe()
            assert clock['virtual_ns'] == before['virtual_ns']
            assert clock['counter']['value'] == before['counter']['value']
            assert word(debug, symbols, 'key_count_ip') == 0
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        assert not calls
        armed = debug.vm.qmp.call(COMMAND, arguments)
        assert_native_press(armed, state='armed', dispatched_count=0)
        assert armed['token'] == arguments['token'] and armed['start-ns'] == before['virtual_ns']
        cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': arguments['token']})
        assert_native_press(cancelled, state='cancelled', dispatched_count=0)
        assert cancelled['terminal-ns'] == before['virtual_ns']
        debug.clock_advance(20 * MS_NS, timeout_ms=5000)
        assert word(debug, symbols, 'key_count_ip') == 0
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(cancelled)
