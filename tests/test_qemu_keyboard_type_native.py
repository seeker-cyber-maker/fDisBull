"""Independent IRQ1 witnesses for a passively armed native text sequence.

The small explicit US-layout table below is the fixture's oracle. It does not
import a production planner or infer guest layout from callback receipts.
Actual scancode bytes qualify consumption only in this authored IRQ1 program.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_retrace_input_fixture import retrace_keyboard
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_input_retrace_native import frozen, key_bytes, word
from test_qemu_keyboard_press_native import assert_press
from test_qemu_retrace_native import artifact_document
from test_qemu_timing_native import assert_sync, native_executions


COMMAND = 'x-fdisbull-arm-keyboard-type'
EDGE_NS = 2_000_000
MS_NS = 1_000_000

# Each row declares physical key, QEMU qcode, IBM set-1 make byte and Shift.
# The native matrix deliberately repeats lifetimes and exercises CR and LF
# separately; the host contract suite supplies exhaustive accepted-ASCII cases.
US_CHARACTERS = {
    'a': ('a', 'a', 0x1e, False),
    'A': ('a', 'a', 0x1e, True),
    'b': ('b', 'b', 0x30, False),
    'c': ('c', 'c', 0x2e, False),
    '0': ('0', '0', 0x0b, False),
    '!': ('1', '1', 0x02, True),
    '\r': ('enter', 'ret', 0x1c, False),
    '\n': ('enter', 'ret', 0x1c, False),
    '\t': ('tab', 'tab', 0x0f, False),
    ' ': ('space', 'spc', 0x39, False),
    '~': (chr(96), 'grave_accent', 0x29, True),
}


def expected_plan(text, *, hold_ms=7, gap_ms=11):
    """Declare character lifetimes and delays independently of native/host code."""
    steps = []
    for character_index, character in enumerate(text):
        key, qcode, scan, shifted = US_CHARACTERS[character]
        chord = []
        if shifted:
            chord.append(('shift', 'shift', 0x2a, True, EDGE_NS))
        chord.extend((
            (key, qcode, scan, True, EDGE_NS),
            (key, qcode, scan, False, hold_ms * MS_NS),
        ))
        if shifted:
            chord.append(('shift', 'shift', 0x2a, False, EDGE_NS))
        for index, (name, code, byte, down, delay) in enumerate(chord):
            if character_index and index == 0:
                delay += gap_ms * MS_NS
            steps.append(dict(key=name, qcode=code, scan=byte, down=down,
                              delay_ns=delay, character_index=character_index))
    return steps


def expected_bytes(plan):
    return bytes(step['scan'] | (0 if step['down'] else 0x80) for step in plan)


def nominal_ns(plan):
    return sum(step['delay_ns'] for step in plan)


@pytest.fixture
def typing_witness(tmp_path, clock_runtime, clock_disk):
    """Use the existing IRQ1 program with an explicitly enlarged private buffer."""
    serial = 0

    @contextmanager
    def launch(*, halted=False, profile='standard', executable=None):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'keyboard-type-{serial}'
        directory.mkdir()
        code, offsets = retrace_keyboard(
            directory, clock_runtime['nasm'], halted=halted, capacity=256)
        binary, project = create_project(directory, code)
        selected = (clock_runtime['executable'] if executable is None else
                    Path(executable).expanduser().resolve(strict=True))
        debug = None
        try:
            with project:
                try:
                    with project.debugger(selected, directory, **launch_options(
                            clock_runtime, clock_disk, qemu_clock='virtual',
                            qemu_retrace=profile)) as debug:
                        info = process_record(debug)
                        symbols = {name: com_address(info, offset)
                                   for name, offset in offsets.items()}
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


def assert_guest_bytes(debug, symbols, wanted):
    assert word(debug, symbols, 'dropped_keys_ip') == 0
    assert word(debug, symbols, 'key_count_ip') == len(wanted)
    if wanted:
        assert key_bytes(debug, symbols, len(wanted)) == wanted


def assert_native_typing(native, text, *, hold_ms=7, gap_ms=11,
                         state, dispatched_count):
    plan = expected_plan(text, hold_ms=hold_ms, gap_ms=gap_ms)
    assert native['api-version'] == 1 and native['state'] == state
    assert native['event-count'] == len(plan)
    assert 'press' not in native and 'retrace' not in native
    typing = native['typing']
    assert set(typing) == {'text', 'hold-ms', 'gap-ms', 'steps', 'dispatched-count'}
    assert typing['text'] == text
    assert typing['hold-ms'] == hold_ms and typing['gap-ms'] == gap_ms
    assert type(typing['dispatched-count']) is int
    assert typing['dispatched-count'] == dispatched_count
    assert len(typing['steps']) == len(plan)
    assert native['deadline-ns'] == native['start-ns'] + EDGE_NS
    for index, (step, expected) in enumerate(zip(typing['steps'], plan, strict=True)):
        assert {key: step[key] for key in ('key', 'down', 'delay-ns')} == {
            'key': expected['qcode'], 'down': expected['down'],
            'delay-ns': expected['delay_ns']}
        fields = {'key', 'down', 'delay-ns'}
        if index <= dispatched_count:
            fields.add('deadline-ns')
            origin = (native['start-ns'] if index == 0 else
                      typing['steps'][index - 1]['dispatch-ns'])
            assert step['deadline-ns'] == origin + expected['delay_ns']
        if index < dispatched_count:
            fields.add('dispatch-ns')
            assert step['deadline-ns'] <= step['dispatch-ns'] <= native['virtual-ns']
        assert set(step) == fields
    if state == 'armed':
        assert dispatched_count == 0
        assert 'terminal-ns' not in native and 'dispatch-ns' not in native
    elif state == 'dispatched':
        assert dispatched_count == len(plan)
        assert native['dispatch-ns'] == native['terminal-ns'] == typing['steps'][-1]['dispatch-ns']
    else:
        assert state == 'cancelled' and 0 <= dispatched_count < len(plan)
        assert 'dispatch-ns' not in native
        assert native['start-ns'] <= native['terminal-ns'] <= native['virtual-ns']
        if dispatched_count:
            assert typing['steps'][dispatched_count - 1]['dispatch-ns'] <= native['terminal-ns']
    return plan


def assert_typing(value, text, *, hold_ms=7, gap_ms=11, state, dispatched_count):
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
    assert value['lateness_ns'] is None
    assert value['guest_consumed'] is value['device_queue_accepted'] is None
    assert value['requires_resolution'] is (state == 'cancelled')
    plan = assert_native_typing(value['native'], text, hold_ms=hold_ms,
        gap_ms=gap_ms, state=state, dispatched_count=dispatched_count)
    assert value['edge_count'] == len(plan) == len(value['sequences'])
    assert len(set(value['sequences'])) == len(plan)
    public = value['typing']
    assert public['format'] == 'fdisbull-keyboard-type-1'
    assert public['text'] == text
    assert public['hold_ms'] == hold_ms and public['gap_ms'] == gap_ms
    assert public['dispatched_count'] == dispatched_count
    assert public['undispatched_count'] == len(plan) - dispatched_count
    assert len(public['steps']) == len(plan)
    active, used = {}, set()
    for index, (step, native_step, expected) in enumerate(zip(
            public['steps'], value['native']['typing']['steps'], plan, strict=True)):
        assert step['sequence'] == value['sequences'][index]
        for field in ('key', 'qcode', 'down', 'delay_ns', 'character_index'):
            assert step[field] == expected[field]
        assert step['deadline_ns'] == native_step.get('deadline-ns')
        assert step['dispatch_ns'] == native_step.get('dispatch-ns')
        assert step['lateness_ns'] == (
            native_step['dispatch-ns'] - native_step['deadline-ns']
            if 'dispatch-ns' in native_step else None)
        if step['down']:
            assert step['key'] not in active
            assert step['lease'] not in used
            active[step['key']] = step['lease']
            used.add(step['lease'])
            assert len(active) <= 2
        else:
            assert active.pop(step['key']) == step['lease']
    assert not active
    return plan


def assert_owned_prefix(debug, receipt, count):
    """Only makes in the delivered prefix may occupy active lease slots."""
    state = debug.input_state()
    steps = receipt['typing']['steps']
    active = {}
    for step in steps[:count]:
        if step['down']:
            active[step['lease']] = step['key']
        else:
            del active[step['lease']]
    assert len(active) <= 2
    assert set(state['leases']) == set(active)
    for lease, key in active.items():
        assert state['leases'][lease]['device'] == 'keyboard'
        assert state['leases'][lease]['key'] == key
        assert state['leases'][lease]['make'] == 'native_dispatched'
        assert state['leases'][lease]['release'] == 'python_pending'
    assert state['pending_edges'] == len(steps) - count
    assert [row['sequence'] for row in state['pending']] == receipt['sequences'][count:]
    return state


def assert_transition(result, armed, text, *, hold_ms=7, gap_ms=11,
                      state, dispatched_count):
    value = result['input_delivery']
    assert_typing(value, text, hold_ms=hold_ms, gap_ms=gap_ms,
                  state=state, dispatched_count=dispatched_count)
    for field in ('token', 'run', 'epoch', 'session_id', 'start_ns',
                  'deadline_ns', 'sequences', 'edge_count'):
        assert value[field] == armed[field]
    for before, after in zip(armed['typing']['steps'], value['typing']['steps'], strict=True):
        for field in ('sequence', 'lease', 'key', 'qcode', 'down',
                      'delay_ns', 'character_index'):
            assert before[field] == after[field]
    budget = result['clock_budget']
    assert value['observed_ns'] == budget['stopped_ns']
    assert value['terminal_ns'] <= budget['stopped_ns']
    assert all(step['dispatch-ns'] < budget['deadline_ns']
               for step in value['native']['typing']['steps'][:dispatched_count])
    if state == 'cancelled':
        assert value['terminal_ns'] == value['observed_ns']
    return value


@pytest.mark.parametrize('halted', [False, True], ids=['busy', 'hlt'])
@pytest.mark.parametrize('text', ['aa0a', 'AA!!', '\r\n\t ~'],
                         ids=['repeated-lowercase', 'repeated-shift', 'controls-space-tilde'])
def test_native_keyboard_type_is_passive_and_preserves_relative_character_timing(
        typing_witness, monkeypatch, halted, text):
    with typing_witness(halted=halted) as (_, debug, symbols):
        assert debug.capabilities['virtual_keyboard_type'] is True
        assert debug.capabilities['virtual_keyboard_press'] is True
        assert debug.capabilities['timed_input'] is False
        before = debug.clock_observe()
        calls = native_executions(debug, monkeypatch)
        armed = debug.keyboard.type(text, hold_ms=7, gap_ms=11)
        plan = assert_typing(armed, text, state='armed', dispatched_count=0)
        assert_owned_prefix(debug, armed, 0)
        assert not calls
        assert_guest_bytes(debug, symbols, b'')
        observed = debug.input_schedule_observe()
        assert observed['native'] == armed['native']
        assert observed['typing'] == armed['typing']
        paused = debug.clock_observe()
        assert paused['virtual_ns'] == before['virtual_ns'] == armed['start_ns']
        assert paused['counter']['value'] == before['counter']['value']

        delta = nominal_ns(plan) + 5 * MS_NS
        result = debug.clock_advance(delta, timeout_ms=5000)
        budget_receipt(result, delta)
        delivered = assert_transition(result, armed, text,
            state='dispatched', dispatched_count=len(plan))
        assert_owned_prefix(debug, delivered, len(plan))
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
        assert_guest_bytes(debug, symbols, expected_bytes(plan))
        # A trailing gap would require at least nominal+11 ms. The declared
        # sequence has already completed at a budget ending only 5 ms later.
        assert result['clock_budget']['stopped_ns'] < armed['start_ns'] + nominal_ns(plan) + 11 * MS_NS
        steps = delivered['native']['typing']['steps']
        for index, expected in enumerate(plan):
            if not expected['down'] and expected['key'] != 'shift':
                assert steps[index]['dispatch-ns'] - steps[index - 1]['dispatch-ns'] >= 7 * MS_NS
            if index and expected['character_index'] != plan[index - 1]['character_index']:
                assert steps[index]['deadline-ns'] == steps[index - 1]['dispatch-ns'] + 13 * MS_NS
        if not halted and text == 'AA!!':
            late = [index for index, step in enumerate(steps[:-1])
                    if step['dispatch-ns'] > step['deadline-ns']]
            assert late, delivered
            for index in late:
                assert steps[index + 1]['deadline-ns'] == steps[index]['dispatch-ns'] + plan[index + 1]['delay_ns']
        after = debug.clock_observe()
        if halted:
            instructions = after['counter']['value'] - before['counter']['value']
            assert 0 < instructions < 1000 * len(plan)
            assert after['virtual_ns'] - before['virtual_ns'] > instructions * 128
            assert word(debug, symbols, 'wakes_ip') == len(plan)
        debug.clock_advance(3 * MS_NS, timeout_ms=3000)
        retained = debug.input_schedule_observe()
        assert retained['typing'] == delivered['typing']
        assert frozen(retained['native']) == frozen(delivered['native'])
        assert_guest_bytes(debug, symbols, expected_bytes(plan))


def test_native_keyboard_type_accepts_64_shifted_characters_with_unique_lifetimes(
        typing_witness, monkeypatch):
    text = 'A' * 64
    with typing_witness(halted=True) as (_, debug, symbols):
        calls = native_executions(debug, monkeypatch)
        armed = debug.keyboard_type(text, hold_ms=1, gap_ms=1)
        plan = assert_typing(armed, text, hold_ms=1, gap_ms=1,
                             state='armed', dispatched_count=0)
        assert len(plan) == 256 and nominal_ns(plan) == 511 * MS_NS
        makes = [step for step in armed['typing']['steps'] if step['down']]
        assert len({step['lease'] for step in makes}) == 128
        assert len({step['lease'] for step in makes if step['key'] == 'shift'}) == 64
        assert_owned_prefix(debug, armed, 0)
        assert not calls
        delta = 516 * MS_NS
        result = debug.clock_advance(delta, timeout_ms=10000)
        budget_receipt(result, delta)
        delivered = assert_transition(result, armed, text, hold_ms=1, gap_ms=1,
                                       state='dispatched', dispatched_count=256)
        assert_owned_prefix(debug, delivered, 256)
        assert len(calls) == 1
        assert_guest_bytes(debug, symbols, b'\x2a\x1e\x9e\xaa' * 64)
        assert word(debug, symbols, 'wakes_ip') == 256


def test_native_keyboard_type_original_stop_before_make_discards_future_reservations(
        typing_witness, monkeypatch):
    with typing_witness(profile='precise') as (_, debug, symbols):
        armed = debug.keyboard_type('Aa', hold_ms=7, gap_ms=11)
        assert_typing(armed, 'Aa', state='armed', dispatched_count=0)
        point = debug.breakpoint(symbols['main_loop_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(50 * MS_NS, timeout_ms=5000)
            budget_receipt(result, 50 * MS_NS, reached=False)
            cancelled = assert_transition(result, armed, 'Aa',
                                          state='cancelled', dispatched_count=0)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert cancelled['terminal_ns'] < cancelled['deadline_ns']
            assert_owned_prefix(debug, cancelled, 0)
            assert_guest_bytes(debug, symbols, b'')
            for operation in (lambda: debug.run(timeout_ms=1000),
                              lambda: debug.keyboard_type('b'),
                              lambda: debug.keyboard_press('b'),
                              lambda: debug.input_schedule(EDGE_NS),
                              debug.input_schedule_retrace):
                with pytest.raises(ValueError):
                    operation()
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 6
        assert resolved['retained_dispatched_holds'] == []
        assert debug.input_state()['pending_edges'] == 0
        assert debug.input_state()['leases'] == {}
        debug.clock_advance(50 * MS_NS, timeout_ms=5000)
        assert_guest_bytes(debug, symbols, b'')
        assert frozen(debug.input_schedule_observe()['native']) == frozen(cancelled['native'])


def test_native_keyboard_type_stop_after_shift_retains_only_the_delivered_hold(
        typing_witness, monkeypatch):
    with typing_witness(profile='precise') as (_, debug, symbols):
        armed = debug.keyboard_type('Aa', hold_ms=7, gap_ms=11)
        shift = armed['typing']['steps'][0]['lease']
        point = debug.breakpoint(symbols['input_seen_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(50 * MS_NS, timeout_ms=5000)
            budget_receipt(result, 50 * MS_NS, reached=False)
            cancelled = assert_transition(result, armed, 'Aa',
                                          state='cancelled', dispatched_count=1)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert_guest_bytes(debug, symbols, b'\x2a')
            steps = cancelled['native']['typing']['steps']
            assert steps[0]['dispatch-ns'] <= cancelled['terminal_ns'] < steps[1]['deadline-ns']
            state = assert_owned_prefix(debug, cancelled, 1)
            assert set(state['leases']) == {shift}
            assert cancelled['dispatch_ns'] is None
            for _ in range(2):
                assert debug.input_schedule_observe()['native'] == cancelled['native']
                assert debug.input_state()['pending'] == state['pending']
                assert debug.input_state()['leases'] == state['leases']
            for operation in (lambda: debug.run(timeout_ms=1000),
                              lambda: debug.keyboard_type('b'),
                              lambda: debug.keyboard_press('b'),
                              lambda: debug.input_schedule(EDGE_NS),
                              debug.input_schedule_retrace):
                with pytest.raises(ValueError):
                    operation()
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 5
        assert resolved['retained_dispatched_holds'] == [shift]
        assert set(debug.input_state()['leases']) == {shift}
        assert debug.input_state()['leases'][shift]['release'] is None
        debug.clock_advance(50 * MS_NS, timeout_ms=5000)
        assert_guest_bytes(debug, symbols, b'\x2a')
        debug.keyboard_key_up(shift)
        ordinary = debug.input_schedule(EDGE_NS)
        assert 'typing' not in ordinary and 'typing' not in ordinary['native']
        released = debug.clock_advance(5 * MS_NS, timeout_ms=5000)['input_delivery']
        assert released['state'] == 'dispatched' and released['token'] == ordinary['token']
        assert_guest_bytes(debug, symbols, b'\x2a\xaa')
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_keyboard_type_budget_between_characters_leaves_no_held_key(
        typing_witness):
    with typing_witness(halted=True) as (_, debug, symbols):
        armed = debug.keyboard_type('aA', hold_ms=7, gap_ms=11)
        result = debug.clock_advance(15 * MS_NS, timeout_ms=5000)
        budget_receipt(result, 15 * MS_NS)
        cancelled = assert_transition(result, armed, 'aA',
                                      state='cancelled', dispatched_count=2)
        assert_owned_prefix(debug, cancelled, 2)
        assert debug.input_state()['leases'] == {}
        assert_guest_bytes(debug, symbols, b'\x1e\x9e')
        native = cancelled['native']['typing']['steps']
        assert native[1]['dispatch-ns'] < cancelled['terminal_ns'] < native[2]['deadline-ns']
        with pytest.raises(ValueError):
            debug.run(timeout_ms=1000)
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 4
        assert resolved['retained_dispatched_holds'] == []
        debug.clock_advance(30 * MS_NS, timeout_ms=5000)
        assert_guest_bytes(debug, symbols, b'\x1e\x9e')
        next_arm = debug.keyboard_type('b', hold_ms=7, gap_ms=11)
        next_result = debug.clock_advance(14 * MS_NS, timeout_ms=5000)
        assert_transition(next_result, next_arm, 'b', state='dispatched', dispatched_count=2)
        assert_guest_bytes(debug, symbols, b'\x1e\x9e\x30\xb0')
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


@pytest.mark.parametrize('boundary', ['first-make', 'first-release', 'next-character'])
@pytest.mark.parametrize('budget_first', [False, True], ids=['type-command-first', 'budget-command-first'])
def test_native_keyboard_type_equal_budget_cancels_the_undelivered_suffix(
        typing_witness, boundary, budget_first):
    """Only first-make covers both actual timer insertion orders.

    A release or next-character timer is created after preceding callbacks,
    so the budget already exists in both command-arm orders for those cases.
    """
    with typing_witness(halted=True) as (_, debug, symbols):
        before = debug.clock_observe()
        expected_count, delta = {
            'first-make': (0, 2 * MS_NS),
            'first-release': (1, 9 * MS_NS),
            'next-character': (2, 22 * MS_NS),
        }[boundary]
        if budget_first:
            budget_token, type_token = uuid.uuid4().hex, uuid.uuid4().hex
            clock_arm = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                {'token': budget_token, 'delta-ns': delta})
            native_arm = debug.vm.qmp.call(COMMAND,
                {'token': type_token, 'text': 'aA', 'hold-ms': 7, 'gap-ms': 11})
            assert_native_typing(native_arm, 'aA', state='armed', dispatched_count=0)
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
            assert_native_typing(native, 'aA', state='cancelled', dispatched_count=expected_count)
            assert native['terminal-ns'] == stopped['budget-stopped-ns'] == native['virtual-ns']
            cleaned = debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': budget_token})
            assert cleaned == {**stopped, 'budget-state': 'cancelled'}
            assert debug.vm.qmp.call('x-fdisbull-query-input') == native
        else:
            armed = debug.keyboard_type('aA', hold_ms=7, gap_ms=11)
            assert_typing(armed, 'aA', state='armed', dispatched_count=0)
            result = debug.clock_advance(delta, timeout_ms=5000)
            budget_receipt(result, delta)
            cancelled = assert_transition(result, armed, 'aA',
                state='cancelled', dispatched_count=expected_count)
            assert_owned_prefix(debug, cancelled, expected_count)
            native = cancelled['native']
            cutoff = result['clock_budget']['deadline_ns']
        assert native['typing']['steps'][expected_count]['deadline-ns'] == cutoff
        assert native['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert 'dispatch-ns' not in native
        assert all(step['dispatch-ns'] < cutoff
                   for step in native['typing']['steps'][:expected_count])
        wanted = b'\x1e\x9e'[:expected_count]
        assert_guest_bytes(debug, symbols, wanted)
        assert word(debug, symbols, 'wakes_ip') == expected_count
        if budget_first:
            # This branch explicitly owns raw QMP state. It does not claim
            # that native-only commands created Python keyboard leases.
            assert debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': type_token}) == native
        else:
            resolved = debug.input_cancel_pending()
            assert resolved['cancelled_edges'] == 6 - expected_count
            if expected_count == 1:
                lease = armed['typing']['steps'][0]['lease']
                assert resolved['retained_dispatched_holds'] == [lease]
                assert debug.input_state()['leases'][lease]['release'] is None
            else:
                assert resolved['retained_dispatched_holds'] == []
        debug.clock_advance(30 * MS_NS, timeout_ms=5000)
        assert_guest_bytes(debug, symbols, wanted)
        if expected_count == 1:
            if budget_first:
                ordinary = debug.vm.qmp.call('x-fdisbull-arm-input', {
                    'token': uuid.uuid4().hex, 'delta-ns': EDGE_NS,
                    'events': [dict(type='key', data=dict(
                        key=dict(type='qcode', data='a'), down=False))]})
                assert 'typing' not in ordinary
            else:
                debug.keyboard_key_up(lease)
                ordinary = debug.input_schedule(EDGE_NS)
                assert 'typing' not in ordinary['native']
            debug.clock_advance(5 * MS_NS, timeout_ms=5000)
            assert_guest_bytes(debug, symbols, b'\x1e\x9e')
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_keyboard_type_old_six_patch_binary_refuses_and_retains_press(
        typing_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_KEYBOARD_TYPE_LEGACY')
    if not legacy:
        message = 'Set FDISBULL_QEMU_KEYBOARD_TYPE_LEGACY to the retained six-patch QEMU'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    with typing_witness(executable=legacy) as (_, debug, symbols):
        assert COMMAND not in debug.vm.qmp_commands
        assert debug.capabilities['virtual_keyboard_type'] is False
        assert debug.capabilities['virtual_keyboard_press'] is True
        assert debug.capabilities['virtual_input_schedule'] is True
        assert debug.capabilities['timed_input'] is False
        before, registers = debug.clock_observe(), debug.registers()
        calls = native_executions(debug, monkeypatch)
        for operation in (lambda: debug.keyboard_type('a'), lambda: debug.keyboard.type('A')):
            with pytest.raises(ValueError):
                operation()
        assert not calls and debug.registers() == registers
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        assert_guest_bytes(debug, symbols, b'')
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        armed = debug.keyboard.press('a', modifiers=['shift'], hold_ms=7, gap_ms=1000)
        assert_press(armed, modifiers=('shift',), state='armed', dispatched_count=0)
        delivered = debug.clock_advance(18 * MS_NS, timeout_ms=5000)['input_delivery']
        assert_press(delivered, modifiers=('shift',), state='dispatched', dispatched_count=4)
        assert delivered['token'] == armed['token'] and 'typing' not in delivered['native']
        assert_guest_bytes(debug, symbols, b'\x2a\x1e\x9e\xaa')
        assert len(calls) == 1
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_keyboard_type_json_script_and_reopen_preserve_sequence_evidence(
        typing_witness):
    with typing_witness(profile='precise') as (project, debug, symbols):
        previous = debug.keyboard_press('a')
        assert 'press' in previous['native']
        debug.input_cancel_pending()
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='keyboard-type', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            armed = invoke('debug-keyboard-type', text='Aa', hold_ms=7, gap_ms=11)
            first_plan = assert_typing(armed, 'Aa', state='armed', dispatched_count=0)
            assert 'press' not in armed['native'] and 'retrace' not in armed['native']
            assert_guest_bytes(debug, symbols, b'')
            first = invoke('debug-clock-advance',
                           delta_ns=nominal_ns(first_plan) + 5 * MS_NS, timeout_ms=5000)
            assert_transition(first, armed, 'Aa', state='dispatched', dispatched_count=6)
            assert_guest_bytes(debug, symbols, expected_bytes(first_plan))

            debug.keyboard_key_down('b')
            ordinary = debug.input_schedule(EDGE_NS)
            assert 'typing' not in ordinary and 'typing' not in ordinary['native']
            debug.input_cancel_pending()
            passive = debug.keyboard_type('b', hold_ms=7, gap_ms=11)
            assert 'typing' in passive['native'] and 'press' not in passive['native']
            debug.input_cancel_pending()
            debug.keyboard_key_down('c')
            retrace = debug.input_schedule_retrace()
            assert 'typing' not in retrace and 'typing' not in retrace['native']
            assert 'retrace' in retrace['native']
            debug.input_cancel_pending()

            second_text = '\t!'
            second_plan = expected_plan(second_text)
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='keyboard.type', text=second_text, hold_ms=7, gap_ms=11),
                dict(op='clock-advance', delta_ns=nominal_ns(second_plan) + 5 * MS_NS, timeout_ms=5000),
                dict(op='input-schedule-observe')])
            report = invoke('debug-script', script=script, timeout_ms=10000)
            assert report['ok'] and report['completed_steps'] == len(script['steps']), report
            rearmed, second, observed = [row['result'] for row in report['steps']]
            assert_typing(rearmed, second_text, state='armed', dispatched_count=0)
            delivered = assert_transition(second, rearmed, second_text,
                                          state='dispatched', dispatched_count=6)
            assert rearmed['token'] != armed['token']
            assert 'retrace' not in rearmed['native']
            assert observed['native'] == delivered['native']
            assert observed['typing'] == delivered['typing']
            wanted = expected_bytes(first_plan) + expected_bytes(second_plan)
            assert_guest_bytes(debug, symbols, wanted)
            assert invoke('debug-keyboard-state')['leases'] == {}
            following = debug.keyboard_press('a')
            assert 'press' in following['native']
            assert 'typing' not in following and 'typing' not in following['native']
            debug.input_cancel_pending()
            assert_guest_bytes(debug, symbols, wanted)
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


def test_native_keyboard_type_one_explicit_clock_sync_step_drives_the_sequence(
        typing_witness, monkeypatch):
    with typing_witness(halted=True) as (_, debug, symbols):
        mapping = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=2_000_000_000,
                                         max_wait_ns=2_000_000_000)
        calls = native_executions(debug, monkeypatch)
        armed = debug.keyboard.type('ab', hold_ms=3, gap_ms=4)
        plan = assert_typing(armed, 'ab', hold_ms=3, gap_ms=4,
                             state='armed', dispatched_count=0)
        assert armed['start_ns'] == mapping['anchors']['virtual_ns']
        assert armed['epoch'] == mapping['epoch'] and not calls
        # Real caller work belongs to the explicitly started mapping. Typing
        # itself is passive and does not sleep, rebase, or execute a character.
        time.sleep(.035)
        synchronized = debug.clock_sync_step(timeout_ms=5000)
        assert_sync(synchronized, anchor=mapping)
        assert synchronized['action'] == 'advance' and synchronized['outcome'] == 'advanced'
        assert synchronized['state'] == 'active'
        assert synchronized['target_ns'] >= armed['start_ns'] + nominal_ns(plan)
        execution = synchronized['execution']
        assert_transition(execution, armed, 'ab', hold_ms=3, gap_ms=4,
                          state='dispatched', dispatched_count=4)
        assert execution['clock_budget']['deadline_ns'] == synchronized['target_ns']
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert_guest_bytes(debug, symbols, b'\x1e\x9e\x30\xb0')
        assert word(debug, symbols, 'wakes_ip') == 4
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        stopped = debug.clock_sync_stop()
        assert stopped['token'] == mapping['token'] and stopped['anchors'] == mapping['anchors']
        assert len(calls) == 1


def test_native_keyboard_type_command_rejections_do_not_consume_the_owner_token(
        typing_witness, monkeypatch):
    with typing_witness() as (_, debug, symbols):
        before = debug.clock_observe()
        idle = debug.vm.qmp.call('x-fdisbull-query-input')
        assert idle['state'] == 'idle' and idle['event-count'] == 0
        arguments = {'token': uuid.uuid4().hex, 'text': 'aA', 'hold-ms': 7, 'gap-ms': 11}
        invalid = [
            {'text': ''}, {'text': 'a' * 65}, {'text': 'a\x01b'},
            {'text': 'a\x00b'}, {'text': 'aé'}, {'text': 'a\x7f'},
            {'text': ['a']}, {'hold-ms': 0}, {'hold-ms': 1001},
            {'hold-ms': True}, {'gap-ms': 0}, {'gap-ms': 1001},
        ]
        calls = native_executions(debug, monkeypatch)
        for change in invalid:
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(COMMAND, {**arguments, **change})
            assert debug.vm.qmp.call('x-fdisbull-query-input') == idle
            clock = debug.clock_observe()
            assert clock['virtual_ns'] == before['virtual_ns']
            assert clock['counter']['value'] == before['counter']['value']
            assert_guest_bytes(debug, symbols, b'')
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        assert not calls
        armed = debug.vm.qmp.call(COMMAND, arguments)
        assert_native_typing(armed, 'aA', state='armed', dispatched_count=0)
        assert armed['token'] == arguments['token'] and armed['start-ns'] == before['virtual_ns']
        cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': arguments['token']})
        assert_native_typing(cancelled, 'aA', state='cancelled', dispatched_count=0)
        assert cancelled['terminal-ns'] == before['virtual_ns']
        debug.clock_advance(50 * MS_NS, timeout_ms=5000)
        assert_guest_bytes(debug, symbols, b'')
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(cancelled)
