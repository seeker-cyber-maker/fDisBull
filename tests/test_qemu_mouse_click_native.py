"""Independent IRQ12 witnesses for passively armed physical mouse clicks.

The authored guest resets a fresh PS/2 device, selects stream mode and records
its initial zero-button/zero-motion packet before enabling the IRQ log. The
packet expectations apply to that controlled fixture only: callback receipts
do not prove arbitrary FIFO acceptance, INT33 consumption, cursor coordinates
or screenshot mapping. No production click planner supplies the oracle.
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
from support.qemu_mouse_click_fixture import mouse_click_probe
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_input_retrace_native import frozen, word
from test_qemu_retrace_native import artifact_document
from test_qemu_timing_native import assert_sync, native_executions


COMMAND = 'x-fdisbull-arm-mouse-click'
EDGE_NS = 2_000_000
MS_NS = 1_000_000
BUTTON_BITS = {'left': 1, 'right': 2, 'middle': 4}


@pytest.fixture
def mouse_click_witness(tmp_path, clock_runtime, clock_disk):
    serial = 0

    @contextmanager
    def launch(*, halted=False, profile='standard', executable=None):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'mouse-click-{serial}'
        directory.mkdir()
        code, offsets = mouse_click_probe(directory, clock_runtime['nasm'], halted=halted)
        binary, project = create_project(directory, code)
        selected = (clock_runtime['executable'] if executable is None
                    else Path(executable).expanduser().resolve(strict=True))
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
                        assert word(debug, symbols, 'setup_status_ip') == 1
                        assert read_bytes(debug, symbols['setup_ack_ip'], 1) == b'\xfa'
                        assert read_bytes(debug, symbols['initial_packet_ip'], 3) == b'\x08\x00\x00'
                        assert_guest_packets(debug, symbols, b'')
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def expected_plan(button='left', hold_ms=7):
    return [dict(button=button, down=True, **{'delay-ns': EDGE_NS}),
            dict(button=button, down=False, **{'delay-ns': hold_ms * MS_NS})]


def expected_packets(button='left', count=2):
    assert count in (0, 1, 2)
    packets = bytes([0x08 | BUTTON_BITS[button], 0, 0, 0x08, 0, 0])
    return packets[:3 * count]


def assert_guest_packets(debug, symbols, expected):
    """Compare complete bytes consumed by the independent guest IRQ12 ISR."""
    assert len(expected) % 3 == 0
    assert word(debug, symbols, 'dropped_bytes_ip') == 0
    assert word(debug, symbols, 'mouse_byte_count_ip') == len(expected)
    assert word(debug, symbols, 'mouse_packet_count_ip') == len(expected) // 3
    assert read_bytes(debug, symbols['mouse_phase_ip'], 1) == b'\x00'
    if expected:
        assert read_bytes(debug, symbols['mouse_bytes_ip'], len(expected)) == expected
        assert read_bytes(debug, symbols['last_mouse_packet_ip'], 3) == expected[-3:]


def nominal_ns(hold_ms=7):
    return EDGE_NS + hold_ms * MS_NS


def assert_native_click(native, *, button='left', hold_ms=7, state, dispatched_count):
    plan = expected_plan(button, hold_ms)
    assert native['api-version'] == 1 and native['state'] == state
    assert native['event-count'] == 2
    assert all(name not in native for name in ('press', 'typing', 'retrace'))
    click = native['click']
    assert set(click) == {'button', 'hold-ms', 'steps', 'dispatched-count'}
    assert click['button'] == button and click['hold-ms'] == hold_ms
    assert type(click['dispatched-count']) is int
    assert click['dispatched-count'] == dispatched_count
    assert len(click['steps']) == 2
    assert native['deadline-ns'] == native['start-ns'] + EDGE_NS
    for index, (step, expected) in enumerate(zip(click['steps'], plan, strict=True)):
        assert {field: step[field] for field in ('button', 'down', 'delay-ns')} == expected
        assert step['down'] is expected['down']
        fields = {'button', 'down', 'delay-ns'}
        if index <= dispatched_count:
            fields.add('deadline-ns')
            origin = native['start-ns'] if index == 0 else click['steps'][index - 1]['dispatch-ns']
            assert step['deadline-ns'] == origin + expected['delay-ns']
        if index < dispatched_count:
            fields.add('dispatch-ns')
            assert step['deadline-ns'] <= step['dispatch-ns'] <= native['virtual-ns']
        assert set(step) == fields
    if state == 'armed':
        assert dispatched_count == 0
        assert 'terminal-ns' not in native and 'dispatch-ns' not in native
    elif state == 'dispatched':
        assert dispatched_count == 2
        assert native['dispatch-ns'] == native['terminal-ns'] == click['steps'][1]['dispatch-ns']
    else:
        assert state == 'cancelled' and 0 <= dispatched_count < 2
        assert 'dispatch-ns' not in native
        assert native['start-ns'] <= native['terminal-ns'] <= native['virtual-ns']
        if dispatched_count:
            assert click['steps'][dispatched_count - 1]['dispatch-ns'] <= native['terminal-ns']
    return plan


def assert_click(value, *, button='left', hold_ms=7, state, dispatched_count):
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
    assert all(name not in value for name in ('press', 'typing', 'retrace'))
    plan = assert_native_click(value['native'], button=button, hold_ms=hold_ms,
                               state=state, dispatched_count=dispatched_count)
    assert value['edge_count'] == len(value['sequences']) == 2
    assert len(set(value['sequences'])) == 2
    public = value['click']
    assert public['format'] == 'fdisbull-mouse-click-1'
    assert public['button'] == button and public['hold_ms'] == hold_ms
    assert public['dispatched_count'] == dispatched_count
    assert public['undispatched_count'] == 2 - dispatched_count
    assert len(public['steps']) == 2
    for index, (step, native_step, expected) in enumerate(
            zip(public['steps'], value['native']['click']['steps'], plan, strict=True)):
        assert step['sequence'] == value['sequences'][index]
        assert step['button'] == button and step['down'] is expected['down']
        assert step['delay_ns'] == expected['delay-ns']
        assert step['deadline_ns'] == native_step.get('deadline-ns')
        assert step['dispatch_ns'] == native_step.get('dispatch-ns')
        lateness = (native_step['dispatch-ns'] - native_step['deadline-ns']
                    if 'dispatch-ns' in native_step else None)
        assert step['lateness_ns'] == lateness
        assert step['lease'] == public['steps'][0]['lease']
    assert isinstance(public['steps'][0]['lease'], str) and public['steps'][0]['lease']
    return plan


def assert_transition(result, armed, *, button='left', hold_ms=7, state, dispatched_count):
    value = result['input_delivery']
    assert_click(value, button=button, hold_ms=hold_ms, state=state, dispatched_count=dispatched_count)
    for field in ('token', 'run', 'epoch', 'session_id', 'start_ns', 'deadline_ns', 'sequences', 'edge_count'):
        assert value[field] == armed[field]
    for before, after in zip(armed['click']['steps'], value['click']['steps'], strict=True):
        for field in ('sequence', 'lease', 'button', 'down', 'delay_ns'):
            assert before[field] == after[field]
    budget = result['clock_budget']
    assert value['observed_ns'] == budget['stopped_ns']
    assert value['terminal_ns'] <= budget['stopped_ns']
    assert all(step['dispatch-ns'] < budget['deadline_ns']
               for step in value['native']['click']['steps'][:dispatched_count])
    if state == 'cancelled':
        assert value['terminal_ns'] == value['observed_ns']
    return value


@pytest.mark.parametrize('halted', [False, True], ids=['busy', 'hlt'])
@pytest.mark.parametrize('button', ['left', 'right', 'middle'])
def test_native_mouse_click_is_passive_and_delivers_two_separately_synchronized_packets(
        mouse_click_witness, monkeypatch, halted, button):
    with mouse_click_witness(halted=halted) as (_, debug, symbols):
        assert debug.capabilities['virtual_mouse_click'] is True
        for name in ('timed_input', 'absolute_mouse', 'guest_time_control', 'completed_guest_frames'):
            assert debug.capabilities[name] is False
        before = debug.clock_observe()
        calls = native_executions(debug, monkeypatch)
        armed = debug.mouse_button_click(button, hold_ms=7)
        assert_click(armed, button=button, state='armed', dispatched_count=0)
        assert not calls
        assert_guest_packets(debug, symbols, b'')
        observed = debug.input_schedule_observe()
        assert observed['native'] == armed['native'] and observed['click'] == armed['click']
        paused = debug.clock_observe()
        assert paused['virtual_ns'] == before['virtual_ns'] == armed['start_ns']
        assert paused['counter']['value'] == before['counter']['value']
        state = debug.input_state()
        lease = armed['click']['steps'][0]['lease']
        assert state['pending_edges'] == 2 and set(state['leases']) == {lease}
        assert state['leases'][lease]['device'] == 'mouse'
        assert state['leases'][lease]['button'] == button
        assert state['leases'][lease]['make'] == state['leases'][lease]['release'] == 'python_pending'

        delta = nominal_ns() + 5 * MS_NS
        result = debug.clock_advance(delta, timeout_ms=5000)
        budget_receipt(result, delta, before=before)
        delivered = assert_transition(result, armed, button=button, state='dispatched', dispatched_count=2)
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
        assert_guest_packets(debug, symbols, expected_packets(button))
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        steps = delivered['native']['click']['steps']
        assert steps[1]['dispatch-ns'] - steps[0]['dispatch-ns'] >= 7 * MS_NS
        assert steps[1]['deadline-ns'] == steps[0]['dispatch-ns'] + 7 * MS_NS
        after = debug.clock_observe()
        if halted:
            instructions = after['counter']['value'] - before['counter']['value']
            assert 0 < instructions < 5000
            assert after['virtual_ns'] - before['virtual_ns'] > instructions * 128
            # Multiple IRQ12 bytes can arrive before HLT is reentered. The
            # complete packet log, rather than an exact wake count, is proof.
            assert 0 < word(debug, symbols, 'wakes_ip') <= 8
        debug.clock_advance(3 * MS_NS, timeout_ms=3000)
        retained = debug.input_schedule_observe()
        assert retained['click'] == delivered['click']
        assert frozen(retained['native']) == frozen(delivered['native'])
        assert_guest_packets(debug, symbols, expected_packets(button))


def test_native_mouse_click_first_stop_before_down_discards_only_unsent_edges(
        mouse_click_witness, monkeypatch):
    with mouse_click_witness() as (_, debug, symbols):
        armed = debug.mouse_button_click('left', hold_ms=7)
        assert_click(armed, state='armed', dispatched_count=0)
        lease = armed['click']['steps'][0]['lease']
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
            assert_guest_packets(debug, symbols, b'')
            assert debug.input_state()['pending_edges'] == 2
            for operation in (lambda: debug.run(timeout_ms=1000),
                              lambda: debug.input_schedule(EDGE_NS),
                              lambda: debug.mouse_button_click('middle')):
                with pytest.raises(ValueError):
                    operation()
            assert len(calls) == 1
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
        resolved = debug.input_cancel_pending()
        assert resolved['cancelled_edges'] == 2 and resolved['cancelled_leases'] == [lease]
        assert resolved['retained_dispatched_holds'] == []
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        debug.clock_advance(20 * MS_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, b'')
        assert frozen(debug.input_schedule_observe()['native']) == frozen(cancelled['native'])


def test_native_mouse_click_first_stop_after_down_packet_keeps_hold_until_explicit_release(
        mouse_click_witness, monkeypatch):
    with mouse_click_witness(profile='precise') as (_, debug, symbols):
        armed = debug.mouse_button_click('right', hold_ms=40)
        lease = armed['click']['steps'][0]['lease']
        point = debug.breakpoint(symbols['after_packet_ip'])
        calls = native_executions(debug, monkeypatch)
        try:
            result = debug.clock_advance(50 * MS_NS, timeout_ms=5000)
            budget_receipt(result, 50 * MS_NS, reached=False)
            cancelled = assert_transition(result, armed, button='right', hold_ms=40,
                                          state='cancelled', dispatched_count=1)
            assert result['outcome'] == 'breakpoint'
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert calls[0]['reply'][0].decode('ascii') == result['session']['stop_reason']['native_reply']
            assert_guest_packets(debug, symbols, expected_packets('right', 1))
            steps = cancelled['native']['click']['steps']
            assert steps[0]['dispatch-ns'] <= cancelled['terminal_ns'] < steps[1]['deadline-ns']
            assert cancelled['dispatch_ns'] is None
            state = debug.input_state()
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
                              lambda: debug.mouse_button_click('left'),
                              lambda: debug.keyboard_press('a'),
                              lambda: debug.keyboard_type('a')):
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
        assert_guest_packets(debug, symbols, expected_packets('right', 1))
        assert frozen(debug.input_schedule_observe()['native']) == frozen(cancelled['native'])
        debug.mouse_button_up(lease)
        ordinary = debug.input_schedule(EDGE_NS)
        assert 'click' not in ordinary and 'click' not in ordinary['native']
        released = debug.clock_advance(5 * MS_NS, timeout_ms=5000)['input_delivery']
        assert released['state'] == 'dispatched' and released['token'] == ordinary['token']
        assert 'click' not in released and 'click' not in released['native']
        assert_guest_packets(debug, symbols, expected_packets('right'))
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


@pytest.mark.parametrize('boundary', ['down', 'release'])
@pytest.mark.parametrize('budget_first', [False, True], ids=['click-command-first', 'budget-command-first'])
def test_native_mouse_click_equal_budget_keeps_only_the_prefix_before_cutoff(
        mouse_click_witness, boundary, budget_first):
    """Down covers both actual timer insertion orders.

    Release covers both command-arm orders. Its timer is necessarily inserted
    after the budget, because its deadline is created only at actual down.
    """
    with mouse_click_witness(halted=True) as (_, debug, symbols):
        before = debug.clock_observe()
        expected_count = 0 if boundary == 'down' else 1
        delta = EDGE_NS if boundary == 'down' else nominal_ns()
        if budget_first:
            budget_token, click_token = uuid.uuid4().hex, uuid.uuid4().hex
            clock_arm = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                {'token': budget_token, 'delta-ns': delta})
            native_arm = debug.vm.qmp.call(COMMAND,
                {'token': click_token, 'button': 'left', 'hold-ms': 7})
            assert_native_click(native_arm, state='armed', dispatched_count=0)
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
            assert_native_click(native, state='cancelled', dispatched_count=expected_count)
            assert native['terminal-ns'] == stopped['budget-stopped-ns'] == native['virtual-ns']
            cleaned = debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': budget_token})
            assert cleaned == {**stopped, 'budget-state': 'cancelled'}
            assert debug.vm.qmp.call('x-fdisbull-query-input') == native
        else:
            armed = debug.mouse_button_click('left', hold_ms=7)
            assert_click(armed, state='armed', dispatched_count=0)
            result = debug.clock_advance(delta, timeout_ms=5000)
            budget_receipt(result, delta)
            cancelled = assert_transition(result, armed, state='cancelled', dispatched_count=expected_count)
            native = cancelled['native']
            cutoff = result['clock_budget']['deadline_ns']
            assert debug.input_state()['pending_edges'] == 2 - expected_count
        assert native['click']['steps'][expected_count]['deadline-ns'] == cutoff
        assert native['reason'] in ('machine-stop', 'stop-pending', 'budget-deadline')
        assert 'dispatch-ns' not in native
        assert all(step['dispatch-ns'] < cutoff for step in native['click']['steps'][:expected_count])
        assert_guest_packets(debug, symbols, expected_packets(count=expected_count))
        if budget_first:
            # Raw QMP arms have native ownership, not invented Python leases.
            assert debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': click_token}) == native
        else:
            resolved = debug.input_cancel_pending()
            assert resolved['cancelled_edges'] == 2 - expected_count
            if expected_count:
                lease = armed['click']['steps'][0]['lease']
                assert resolved['retained_dispatched_holds'] == [lease]
                assert debug.input_state()['leases'][lease]['release'] is None
            else:
                assert resolved['retained_dispatched_holds'] == []
        debug.clock_advance(20 * MS_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, expected_packets(count=expected_count))
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(native)
        if expected_count:
            if budget_first:
                release = debug.vm.qmp.call('x-fdisbull-arm-input', {
                    'token': uuid.uuid4().hex, 'delta-ns': EDGE_NS,
                    'events': [dict(type='btn', data=dict(button='left', down=False))]})
                assert 'click' not in release
            else:
                debug.mouse_button_up(lease)
                release = debug.input_schedule(EDGE_NS)
                assert 'click' not in release['native']
            debug.clock_advance(5 * MS_NS, timeout_ms=5000)
            assert_guest_packets(debug, symbols, expected_packets())
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_mouse_click_old_seven_patch_binary_refuses_without_losing_existing_input(
        mouse_click_witness, monkeypatch):
    legacy = os.environ.get('FDISBULL_QEMU_MOUSE_CLICK_LEGACY')
    if not legacy:
        message = 'Set FDISBULL_QEMU_MOUSE_CLICK_LEGACY to the retained seven-patch QEMU'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_CLOCK') == '1':
            pytest.fail(message)
        pytest.skip(message)
    with mouse_click_witness(executable=legacy) as (_, debug, symbols):
        assert COMMAND not in debug.vm.qmp_commands
        assert debug.capabilities['virtual_mouse_click'] is False
        assert debug.capabilities['virtual_keyboard_press'] is True
        assert debug.capabilities['virtual_keyboard_type'] is True
        assert debug.capabilities['timed_input'] is False
        before = debug.clock_observe()
        registers = debug.registers()
        calls = native_executions(debug, monkeypatch)
        with pytest.raises(ValueError):
            debug.mouse_button_click('left', hold_ms=7)
        assert not calls and debug.registers() == registers
        assert debug.clock_observe()['virtual_ns'] == before['virtual_ns']
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        assert_guest_packets(debug, symbols, b'')
        lease = debug.mouse_button_down('left')['lease']
        armed = debug.input_schedule(EDGE_NS)
        assert 'click' not in armed['native']
        delivered = debug.clock_advance(5 * MS_NS, timeout_ms=5000)['input_delivery']
        assert delivered['state'] == 'dispatched' and delivered['token'] == armed['token']
        assert_guest_packets(debug, symbols, expected_packets(count=1))
        debug.mouse_button_up(lease)
        ordinary = debug.input_schedule(EDGE_NS)
        result = debug.clock_advance(5 * MS_NS, timeout_ms=5000)
        assert result['input_delivery']['state'] == 'dispatched'
        assert result['input_delivery']['token'] == ordinary['token']
        assert_guest_packets(debug, symbols, expected_packets())
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}


def test_native_mouse_click_json_script_journal_reopen_and_descriptor_transitions(
        mouse_click_witness):
    with mouse_click_witness(profile='precise') as (project, debug, symbols):
        # Every preceding setup arm is cancelled while stopped. IRQ1 is masked
        # in this fixture; no keyboard command is allowed to reach the device.
        previous = debug.keyboard_press('a', hold_ms=7, gap_ms=7)
        assert 'press' in previous['native']
        debug.input_cancel_pending()
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug

        def invoke(method, **params):
            reply = respond(dict(id='mouse-click', method=method,
                params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
            assert reply['ok'], reply
            return reply['result']

        try:
            armed = invoke('debug-mouse-button-click', button='left', hold_ms=7)
            assert_click(armed, state='armed', dispatched_count=0)
            assert_guest_packets(debug, symbols, b'')
            first = invoke('debug-clock-advance', delta_ns=nominal_ns() + 5 * MS_NS, timeout_ms=5000)
            assert_transition(first, armed, state='dispatched', dispatched_count=2)
            assert_guest_packets(debug, symbols, expected_packets())

            # Accepted modes must clear the old click descriptor, and each
            # new click must clear whichever descriptor preceded it.
            for mode in ('ordinary', 'typing', 'press', 'retrace'):
                if mode == 'ordinary':
                    debug.keyboard_key_down('a')
                    following = debug.input_schedule(EDGE_NS)
                elif mode == 'typing':
                    following = debug.keyboard_type('a', hold_ms=7, gap_ms=7)
                elif mode == 'press':
                    following = debug.keyboard_press('a', hold_ms=7, gap_ms=7)
                else:
                    debug.keyboard_key_down('a')
                    following = debug.input_schedule_retrace(edge='exit')
                assert 'click' not in following and 'click' not in following['native']
                if mode != 'ordinary':
                    assert mode in following['native']
                debug.input_cancel_pending()
                if mode != 'retrace':
                    intervening = debug.mouse_button_click('middle', hold_ms=7)
                    assert_click(intervening, button='middle', state='armed', dispatched_count=0)
                    debug.input_cancel_pending()
                assert_guest_packets(debug, symbols, expected_packets())

            # The lower accepted hold bound is exercised through a real script
            # and two device packets, not only through passive arm validation.
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='mouse.button-click', button='right', hold_ms=1),
                dict(op='clock-advance', delta_ns=nominal_ns(1) + 5 * MS_NS, timeout_ms=5000),
                dict(op='input-schedule-observe')])
            report = invoke('debug-script', script=script, timeout_ms=10000)
            assert report['ok'] and report['completed_steps'] == len(script['steps']), report
            rearmed, second, observed = [row['result'] for row in report['steps']]
            assert_click(rearmed, button='right', hold_ms=1, state='armed', dispatched_count=0)
            delivered = assert_transition(second, rearmed, button='right', hold_ms=1,
                                          state='dispatched', dispatched_count=2)
            assert rearmed['token'] != armed['token']
            assert observed['native'] == delivered['native'] and observed['click'] == delivered['click']
            assert_guest_packets(debug, symbols, expected_packets() + expected_packets('right'))
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
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


def test_native_mouse_click_one_explicit_clock_sync_step_drives_default_click(
        mouse_click_witness, monkeypatch):
    with mouse_click_witness(halted=True) as (_, debug, symbols):
        mapping = debug.clock_sync_start(tolerance_ns=0, max_lag_ns=2_000_000_000,
                                         max_wait_ns=2_000_000_000)
        calls = native_executions(debug, monkeypatch)
        armed = debug.mouse_button_click()
        assert_click(armed, hold_ms=80, state='armed', dispatched_count=0)
        assert armed['start_ns'] == mapping['anchors']['virtual_ns']
        assert armed['epoch'] == mapping['epoch'] and not calls
        assert_guest_packets(debug, symbols, b'')
        # Explicit caller-side elapsed work belongs to the mapping. The helper
        # itself does not sleep, execute, rebase or create a synchronization loop.
        time.sleep(.100)
        synchronized = debug.clock_sync_step(timeout_ms=5000)
        assert_sync(synchronized, anchor=mapping)
        assert synchronized['action'] == 'advance' and synchronized['outcome'] == 'advanced'
        assert synchronized['state'] == 'active'
        assert synchronized['target_ns'] >= armed['start_ns'] + nominal_ns(80)
        execution = synchronized['execution']
        assert_transition(execution, armed, hold_ms=80, state='dispatched', dispatched_count=2)
        assert execution['clock_budget']['deadline_ns'] == synchronized['target_ns']
        assert len(calls) == 1 and calls[0]['command'] == 'c'
        assert_guest_packets(debug, symbols, expected_packets())
        assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        stopped = debug.clock_sync_stop()
        assert stopped['token'] == mapping['token'] and stopped['anchors'] == mapping['anchors']
        assert len(calls) == 1


def test_native_mouse_click_raw_rejections_preserve_token_and_strict_hold_bounds(
        mouse_click_witness, monkeypatch):
    with mouse_click_witness() as (_, debug, symbols):
        before = debug.clock_observe()
        idle = debug.vm.qmp.call('x-fdisbull-query-input')
        assert idle['state'] == 'idle' and idle['event-count'] == 0
        arguments = {'token': uuid.uuid4().hex, 'button': 'left', 'hold-ms': 7}
        invalid = [
            {'button': 'unknown'}, {'button': 'side'}, {'button': 'extra'},
            {'button': 'wheel-up'}, {'button': 'wheel-down'},
            {'button': True}, {'button': ['left']},
            {'hold-ms': 0}, {'hold-ms': 1001}, {'hold-ms': True},
            {'hold-ms': 1.5}, {'hold-ms': '1'},
        ]
        calls = native_executions(debug, monkeypatch)
        for change in invalid:
            with pytest.raises(DebuggerError):
                debug.vm.qmp.call(COMMAND, {**arguments, **change})
            assert debug.vm.qmp.call('x-fdisbull-query-input') == idle
            clock = debug.clock_observe()
            assert clock['virtual_ns'] == before['virtual_ns']
            assert clock['counter']['value'] == before['counter']['value']
            assert_guest_packets(debug, symbols, b'')
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
        assert not calls
        armed = debug.vm.qmp.call(COMMAND, arguments)
        assert_native_click(armed, state='armed', dispatched_count=0)
        assert armed['token'] == arguments['token'] and armed['start-ns'] == before['virtual_ns']
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': uuid.uuid4().hex})
        assert debug.vm.qmp.call('x-fdisbull-query-input') == armed
        cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': arguments['token']})
        assert_native_click(cancelled, state='cancelled', dispatched_count=0)
        assert cancelled['terminal-ns'] == before['virtual_ns']
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(COMMAND, arguments)
        assert debug.vm.qmp.call('x-fdisbull-query-input') == cancelled

        # Both inclusive native bounds fit this same stopped VM. Cancelling the
        # 1000 ms plan before down avoids spending a second of guest budget.
        for hold_ms in (1, 1000):
            boundary = {**arguments, 'token': uuid.uuid4().hex, 'hold-ms': hold_ms}
            accepted = debug.vm.qmp.call(COMMAND, boundary)
            assert_native_click(accepted, hold_ms=hold_ms, state='armed', dispatched_count=0)
            cancelled = debug.vm.qmp.call('x-fdisbull-cancel-input', {'token': boundary['token']})
            assert_native_click(cancelled, hold_ms=hold_ms, state='cancelled', dispatched_count=0)
        assert not calls
        debug.clock_advance(50 * MS_NS, timeout_ms=5000)
        assert_guest_packets(debug, symbols, b'')
        assert frozen(debug.vm.qmp.call('x-fdisbull-query-input')) == frozen(cancelled)
