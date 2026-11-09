"""The retained text routes admit only the explicitly advertised native sequence."""
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineContext
from test_qemu_io_public import raw_project, stopped_session


def script(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-machine', steps=list(steps))


def test_native_type_uses_existing_script_grammar(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_type'] = True
    value = script(dict(op='keyboard.type', text='Aa!\r\n\t', hold_ms=17, gap_ms=93))
    assert validate_script(value, session=session) == value['steps']
    assert validate_script(value) == value['steps']
    assert 'keyboard.type' in session.script_operations
    assert not peer.calls


def test_native_type_preserves_json_route_and_namespace(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    calls = []
    def type_text(text, *, hold_ms=40, gap_ms=40):
        calls.append(dict(text=text, hold_ms=hold_ms, gap_ms=gap_ms))
        return dict(state='armed', token='owned-text', guest_consumed=None)
    session.keyboard_type = type_text
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    options = dict(text='aA!\r\n\t', hold_ms=19, gap_ms=77)
    try:
        assert OPERATIONS['keyboard.type'] == 'keyboard_type'
        assert 'debug-keyboard-type' in METHODS
        response = respond(dict(id=37, method='debug-keyboard-type', params=dict(
            project=str(raw_project.path), run=session.run_id, context='machine', **options)),
            debugger=workspace)
        assert response['ok'], response
        assert response['result']['state'] == 'armed'
        assert session.keyboard.type(**options) == response['result']
        assert calls == [options, options] and not peer.calls
    finally:
        workspace.sessions.clear()
        session.close()


def test_native_type_capability_refuses_before_earlier_script_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_press'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with pytest.raises(ValueError, match='text|typing|type|clock'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                       dict(op='keyboard.type', text='a')))
    assert not writes and not peer.calls


@pytest.mark.parametrize('options', [
    {'text': True}, {'text': None}, {'text': ''}, {'text': 'a' * 65},
    {'text': 'a' * 63 + '\u00e9'}, {'text': '\x00'}, {'text': '\x7f'},
    {'hold_ms': True}, {'hold_ms': 0}, {'hold_ms': 1001},
    {'gap_ms': 1.5}, {'gap_ms': 0}, {'gap_ms': 1001},
    {'text': '$selection.text', 'hold_ms': -1},
])
def test_native_type_bad_literal_refuses_entire_script(raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_type'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op='keyboard.type', **dict({'text': 'a'}, **options)))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, value)
    assert not writes and not peer.calls


def test_native_type_caller_transaction_refuses_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_type'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    raw_project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                           dict(op='keyboard.type', text='a')))
        assert not writes and not peer.calls
    finally:
        raw_project.db.rollback()


@pytest.mark.parametrize('field,value', [
    ('text', ''), ('text', 'a' * 65), ('text', 'valid prefix\u00e9'),
    ('text', None), ('text', True), ('hold_ms', True), ('hold_ms', 1001),
    ('gap_ms', 0), ('gap_ms', 1.5),
])
def test_native_type_validates_resolved_values_before_native_arm(raw_project, tmp_path, field, value):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_type'] = True
    calls = []
    session.keyboard_type = lambda *args, **kwargs: calls.append((args, kwargs))
    options = dict(text='a', hold_ms=7, gap_ms=11)
    options[field] = '$selection.value'
    result = execute_script(session, script(dict(op='keyboard.type', **options)),
                            bindings={'selection': {'value': value}})
    assert not result['ok'] and not calls and not peer.calls


def test_failed_script_closes_after_passive_type_arm(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_keyboard_type'] = True
    calls = []
    def type_text(text, *, hold_ms=40, gap_ms=40):
        calls.append(('type', text))
        return dict(state='armed', token='owned-text', guest_consumed=None)
    session.keyboard_type = type_text
    session.close = lambda: calls.append(('close',))
    result = execute_script(session, script(dict(op='keyboard.type', text='aA'),
                                          dict(op='assert', value=False, equals=True)))
    assert not result['ok'] and result['completed_steps'] == 1
    assert calls == [('type', 'aA'), ('close',)]
    assert result['input_cleanup']['closed'] is True
    assert not peer.calls


def test_native_type_capability_requires_all_native_seams(raw_project, tmp_path):
    from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
    from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
    session, peer = stopped_session(raw_project, tmp_path)
    vm = session.vm
    commands = VIRTUAL_CLOCK_COMMANDS | INPUT_SCHEDULE_COMMANDS | {
        'input-send-event', 'x-fdisbull-arm-keyboard-type'}
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    for missing in sorted(commands):
        vm.qmp_commands = commands - {missing}
        assert MachineContext(vm).capabilities['virtual_keyboard_type'] is False, missing
    vm.qmp_commands = commands
    context = MachineContext(vm)
    assert context.capabilities['virtual_keyboard_type'] is True
    assert context.capabilities['timed_input'] is False
    assert context.capabilities['guest_time_control'] is False
    assert context.capabilities['completed_guest_frames'] is False
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard', 1)
    assert MachineContext(vm).capabilities['virtual_keyboard_type'] is False
    assert not peer.calls


def test_type_outer_deadline_retains_accepted_receipt_and_closes(raw_project, tmp_path, monkeypatch):
    from fdisbull.qemu_machine import machine_trace_operation
    session, peer = stopped_session(raw_project, tmp_path)
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    observed = []
    receipt = dict(state='armed', token='deadline-text')
    def keyboard_type(owner, text, *, hold_ms=40, gap_ms=40):
        observed.append((owner.vm.operation_deadline, owner._deadline,
                         owner.vm.qmp.operation_deadline))
        clock[0] = 101.001
        return receipt
    wrapped = machine_trace_operation(keyboard_type, label='Timed keyboard text',
                                     default_timeout_ms=1000)
    with pytest.raises(TimeoutError) as caught:
        wrapped(session, 'aa')
    assert caught.value.result == receipt
    assert observed == [(101.0, 101.0, 101.0)]
    assert session.vm.qmp is None
    assert session.input_state()['valid'] is False
    assert session.vm.operation_deadline is None and session._deadline is None
    assert peer.operation_deadline is None and not peer.calls


def test_type_admission_keeps_tighter_incoming_bounds(raw_project, tmp_path, monkeypatch):
    from fdisbull.qemu_machine import machine_trace_operation
    session, peer = stopped_session(raw_project, tmp_path)
    monkeypatch.setattr(time, 'monotonic', lambda: 100.0)
    session._rpc_deadline = 100.6
    session._deadline = 100.5
    session.vm.operation_deadline = 100.4
    peer.operation_deadline = 100.3
    def keyboard_type(owner, text, *, hold_ms=40, gap_ms=40):
        assert owner.vm.operation_deadline == owner._deadline == peer.operation_deadline == 100.3
        return dict(state='armed')
    wrapped = machine_trace_operation(keyboard_type, label='Timed keyboard text',
                                     default_timeout_ms=1000)
    assert wrapped(session, 'aa') == dict(state='armed')
    assert session._deadline == 100.5 and session.vm.operation_deadline == 100.4
    assert peer.operation_deadline == 100.3 and session._rpc_deadline == 100.6
