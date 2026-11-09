"""Physical timed button clicks retain a distinct coordinate-free contract."""
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.qemu_machine import MachineContext
from test_qemu_io_public import raw_project, stopped_session


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def test_native_mouse_click_operation_is_discoverable():
    assert 'debug-mouse-button-click' in METHODS
    assert OPERATIONS['mouse.button-click'] == 'mouse_button_click'
    assert 'mouse_button_click' not in DebugSession.__dict__


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_native_mouse_click_script_grammar_has_no_coordinates(raw_project, tmp_path, backend):
    session, peer = stopped_session(raw_project, tmp_path)
    session.metadata['backend'] = backend
    session.capabilities['virtual_mouse_click'] = True
    value = script(dict(op='mouse.button-click', button='middle', hold_ms=17),
                   backend=backend)
    assert validate_script(value, session=session) == value['steps']
    assert validate_script(value) == value['steps']
    assert 'mouse.button-click' in session.script_operations
    assert not peer.calls


@pytest.mark.parametrize('options', [{}, {'button': 'right', 'hold_ms': 77}])
def test_native_mouse_click_json_route_and_defaults(raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    calls = []
    def click_button(button='left', *, hold_ms=80):
        calls.append(dict(button=button, hold_ms=hold_ms))
        return dict(state='armed', token='owned-click', guest_consumed=None)
    session.mouse_button_click = click_button
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=37, method='debug-mouse-button-click', params=dict(
            project=str(raw_project.path), run=session.run_id, context='machine', **options)),
            debugger=workspace)
        assert response['ok'], response
        assert response['result']['state'] == 'armed'
        assert calls == [dict({'button': 'left', 'hold_ms': 80}, **options)]
        assert not peer.calls
    finally:
        workspace.sessions.clear()
        session.close()


def test_mouse_click_capability_refuses_before_earlier_script_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities.update(virtual_keyboard_press=True, virtual_keyboard_type=True)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with pytest.raises(ValueError, match='mouse|click|clock'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                       dict(op='mouse.button-click')))
    assert not writes and not peer.calls


@pytest.mark.parametrize('options', [
    {'button': True}, {'button': None}, {'button': ''}, {'button': 'LEFT'},
    {'button': 'wheel-up'}, {'button': 'side'}, {'button': 1},
    {'hold_ms': True}, {'hold_ms': None}, {'hold_ms': 1.5}, {'hold_ms': '80'},
    {'hold_ms': 0}, {'hold_ms': 1001}, {'x': 20}, {'y': 40},
    {'button': '$selection.button', 'hold_ms': 0},
    {'button': 'wheel-down', 'hold_ms': '$selection.hold_ms'},
])
def test_mouse_click_bad_literal_refuses_entire_script(raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_mouse_click'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op='mouse.button-click', **options))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, value)
    assert not writes and not peer.calls


def test_mouse_click_transaction_refuses_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_mouse_click'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    raw_project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                           dict(op='mouse.button-click')))
        assert not writes and not peer.calls
    finally:
        raw_project.db.rollback()


@pytest.mark.parametrize('field,value', [
    ('button', ''), ('button', 'extra'), ('button', None), ('button', True),
    ('hold_ms', True), ('hold_ms', 0), ('hold_ms', 1001), ('hold_ms', 1.5),
])
def test_mouse_click_revalidates_resolved_values_before_arm(raw_project, tmp_path, field, value):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_mouse_click'] = True
    calls = []
    session.mouse_button_click = lambda *args, **kwargs: calls.append((args, kwargs))
    options = dict(button='left', hold_ms=7)
    options[field] = '$selection.value'
    result = execute_script(session, script(dict(op='mouse.button-click', **options)),
                            bindings={'selection': {'value': value}})
    assert not result['ok'] and not calls and not peer.calls


def test_failed_script_closes_after_passive_mouse_click_arm(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_mouse_click'] = True
    calls = []
    def click_button(button='left', *, hold_ms=80):
        calls.append(('click', button, hold_ms))
        return dict(state='armed', token='owned-click', guest_consumed=None)
    session.mouse_button_click = click_button
    session.close = lambda: calls.append(('close',))
    result = execute_script(session, script(dict(op='mouse.button-click', button='right'),
                                          dict(op='assert', value=False, equals=True)))
    assert not result['ok'] and result['completed_steps'] == 1
    assert calls == [('click', 'right', 80), ('close',)]
    assert result['input_cleanup']['closed'] is True and not peer.calls


def test_mouse_click_capability_requires_every_native_seam(raw_project, tmp_path):
    from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
    from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
    session, peer = stopped_session(raw_project, tmp_path)
    vm = session.vm
    commands = VIRTUAL_CLOCK_COMMANDS | INPUT_SCHEDULE_COMMANDS | {
        'input-send-event', 'x-fdisbull-arm-mouse-click'}
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    for missing in sorted(commands):
        vm.qmp_commands = commands - {missing}
        assert MachineContext(vm).capabilities['virtual_mouse_click'] is False, missing
    vm.qmp_commands = commands
    context = MachineContext(vm)
    assert context.capabilities['virtual_mouse_click'] is True
    for name in ('timed_input', 'absolute_mouse', 'guest_time_control', 'completed_guest_frames'):
        assert context.capabilities[name] is False
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard', 1)
    assert MachineContext(vm).capabilities['virtual_mouse_click'] is False
    assert not peer.calls


@pytest.mark.parametrize('options', [{'button': 'wheel-up'}, {'hold_ms': True}])
@pytest.mark.parametrize('expired', [False, True], ids=['busy-owner', 'expired-deadline'])
def test_invalid_direct_click_refuses_before_lock_admission(raw_project, tmp_path, options, expired):
    session, peer = stopped_session(raw_project, tmp_path)
    attempted = []
    class BusyLock:
        def acquire(self, *, timeout):
            attempted.append(timeout)
            return False
    session.vm.lock = BusyLock()
    if expired:
        session._rpc_deadline = time.monotonic() - 1
    with pytest.raises(ValueError):
        session.mouse_button_click(**options)
    assert not attempted and not peer.calls
    assert session.vm.qmp is peer


def test_actual_click_wrapper_retains_late_arm_receipt_and_closes(raw_project, tmp_path, monkeypatch):
    from fdisbull import qemu_mouse_click
    session, peer = stopped_session(raw_project, tmp_path)
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    observed = []
    receipt = dict(state='armed', token='deadline-click')
    def click_button(owner, button='left', *, hold_ms=80):
        observed.append((owner.vm.operation_deadline, owner._deadline,
                         owner.vm.qmp.operation_deadline))
        clock[0] = 101.001
        return receipt
    monkeypatch.setattr(qemu_mouse_click, 'mouse_button_click', click_button)
    with pytest.raises(TimeoutError) as caught:
        session.mouse_button_click()
    assert caught.value.result == receipt and observed == [(101.0, 101.0, 101.0)]
    assert session.vm.qmp is None and session.input_state()['valid'] is False
    assert session.vm.operation_deadline is None and session._deadline is None
    assert peer.operation_deadline is None and not peer.calls


def test_actual_click_wrapper_preserves_tighter_incoming_bounds(raw_project, tmp_path, monkeypatch):
    from fdisbull import qemu_mouse_click
    session, peer = stopped_session(raw_project, tmp_path)
    monkeypatch.setattr(time, 'monotonic', lambda: 100.0)
    session._rpc_deadline, session._deadline = 100.6, 100.5
    session.vm.operation_deadline, peer.operation_deadline = 100.4, 100.3
    def click_button(owner, button='left', *, hold_ms=80):
        assert owner.vm.operation_deadline == owner._deadline == peer.operation_deadline == 100.3
        return dict(state='armed')
    monkeypatch.setattr(qemu_mouse_click, 'mouse_button_click', click_button)
    assert session.mouse_button_click('middle', hold_ms=1) == dict(state='armed')
    assert session._deadline == 100.5 and session.vm.operation_deadline == 100.4
    assert peer.operation_deadline == 100.3 and session._rpc_deadline == 100.6


@pytest.mark.parametrize('operation,params', [
    ('click', {'x': 3, 'y': 7}),
    ('click-frame', {'x': 3, 'y': 7, 'mode_id': 1, 'frame_id': 2}),
])
def test_pixel_click_routes_remain_unavailable_on_native_qemu(raw_project, tmp_path, operation, params):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['virtual_mouse_click'] = True
    calls = []
    session.mouse_button_click = lambda *args, **kwargs: calls.append((args, kwargs))
    with pytest.raises(ValueError):
        validate_script(script(dict(op=operation, **params)), session=session)
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=38, method='debug-' + operation, params=dict(
            project=str(raw_project.path), run=session.run_id, **params)), debugger=workspace)
        assert not response['ok'] and not calls and not peer.calls
    finally:
        workspace.sessions.clear()
        session.close()
