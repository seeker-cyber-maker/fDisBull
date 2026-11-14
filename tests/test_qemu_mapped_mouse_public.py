"""Declared relative motion has its own public capability and binding contract."""
from copy import deepcopy
import json
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from fdisbull.qemu_display import DISPLAY_COMMANDS, DISPLAY_PROBE_COMMANDS
from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
from fdisbull.qemu_machine import MachineContext
from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration
from fdisbull.qemu_vga_configuration import VGA_CONFIGURATION_COMMANDS
from test_qemu_io_public import raw_project, stopped_session


ARM = 'x-fdisbull-arm-display-motion'
COMMANDS = (VIRTUAL_CLOCK_COMMANDS | DISPLAY_COMMANDS | RETRACE_COMMANDS |
            VGA_CONFIGURATION_COMMANDS | INPUT_SCHEDULE_COMMANDS | {ARM, 'input-send-event'})


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def motion_arguments(**changes):
    value = dict(dx_pixels=6, dy_pixels=-4,
                 counts_per_pixel={'x': [2, 3], 'y': [3, 2]},
                 window='owned-retained-window', update_id=7,
                 configuration_generation=5, timeout_ms=1000)
    value.update(changes)
    return value


def test_mapped_mouse_has_a_direct_machine_operation():
    assert callable(getattr(MachineContext, 'mouse_move_mapped', None))
    assert not hasattr(DebugSession, 'mouse_move_mapped')


def test_mapped_mouse_has_a_json_operation():
    assert 'debug-mouse-move-mapped' in METHODS
    description = METHODS['debug-mouse-move-mapped']
    for field in ('dx_pixels', 'dy_pixels', 'counts_per_pixel', 'window',
                  'update_id', 'configuration_generation', 'timeout_ms'):
        assert field in description


def test_mapped_mouse_has_a_saved_script_operation():
    assert OPERATIONS.get('mouse.move-mapped') == 'mouse_move_mapped'


@pytest.fixture
def public_motion(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['mapped_mouse_motion'] = True
    try:
        yield session, peer
    finally:
        session.close()


def select_motion(vm):
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    vm.qmp_commands = COMMANDS


def earlier_write():
    return dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00')


def assert_no_effects(session, peer, calls):
    assert not calls and not peer.calls and session.vm.qmp is peer
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_motion_script_grammar_keeps_absolute_clicks_unavailable(public_motion, backend):
    session, peer = public_motion
    session.metadata['backend'] = backend
    value = script(dict(op='mouse.move-mapped', **motion_arguments()), backend=backend)
    assert validate_script(value) == value['steps']
    assert validate_script(value, session=session) == value['steps']
    assert 'mouse.move-mapped' in session.script_operations
    for operation in ('click', 'click-frame'):
        with pytest.raises(ValueError, match='Unsupported'):
            validate_script(script(dict(op=operation, x=1, y=2), backend=backend))
    with pytest.raises(ValueError, match='Unsupported'):
        validate_script(dict(format='fdisbull-script-1', steps=value['steps']))
    assert not peer.calls


@pytest.mark.parametrize('context', [None, 'machine'])
@pytest.mark.parametrize('timeout', [None, 73])
def test_json_motion_route_forwards_complete_declaration_and_default_timeout(public_motion, context, timeout):
    session, peer = public_motion
    calls = []
    options = motion_arguments()
    if timeout is None:
        options.pop('timeout_ms')
    else:
        options['timeout_ms'] = timeout

    def move(dx_pixels, dy_pixels, *, counts_per_pixel, window, update_id,
             configuration_generation, timeout_ms=1000):
        calls.append(dict(dx_pixels=dx_pixels, dy_pixels=dy_pixels,
                          counts_per_pixel=counts_per_pixel, window=window, update_id=update_id,
                          configuration_generation=configuration_generation, timeout_ms=timeout_ms))
        return dict(state='armed', motion={'binding_verified': False}, guest_consumed=None)

    session.mouse_move_mapped = move
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    params = dict(project=str(session.project.path), run=session.run_id, **options)
    if context is not None:
        params['context'] = context
    try:
        response = respond(dict(id=41, method='debug-mouse-move-mapped', params=params), debugger=workspace)
        assert response['ok'], response
        assert response['result']['state'] == 'armed'
        assert calls == [motion_arguments(timeout_ms=1000 if timeout is None else timeout)]
        assert not peer.calls
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('change,missing', [({'dx_pixels': True}, None), ({'timeout_ms': 0}, None),
    ({'origin': [0, 0]}, None), ({'configuration_generation': 0}, None), ({}, 'window')])
def test_json_invalid_signature_or_literal_refuses_without_native_io(public_motion, change, missing):
    session, peer = public_motion
    options = motion_arguments(**change)
    if missing is not None:
        del options[missing]
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=42, method='debug-mouse-move-mapped', params=dict(
            project=str(session.project.path), run=session.run_id, context='machine', **options)),
            debugger=workspace)
        assert not response['ok'], response
        assert not peer.calls and session.vm.qmp is peer
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('missing', sorted(COMMANDS))
def test_motion_capability_requires_every_native_dependency(public_motion, missing):
    session, peer = public_motion
    select_motion(session.vm)
    session.vm.qmp_commands -= {missing}
    context = MachineContext(session.vm).bind(session.project, session.run_id)
    assert context.capabilities['mapped_mouse_motion'] is False, missing
    with pytest.raises(ValueError):
        context.mouse_move_mapped(**motion_arguments())
    assert not peer.calls and session.vm.qmp is peer


def test_ten_layer_runtime_keeps_prior_capabilities_without_mapped_motion(public_motion):
    session, peer = public_motion
    select_motion(session.vm)
    session.vm.qmp_commands = COMMANDS - {ARM} | DISPLAY_PROBE_COMMANDS
    context = MachineContext(session.vm).bind(session.project, session.run_id)
    for name in ('renderer_capture', 'renderer_probe', 'retrace_observation',
                 'vga_configuration', 'virtual_input_schedule'):
        assert context.capabilities[name] is True, name
    assert context.capabilities['mapped_mouse_motion'] is False
    with pytest.raises(ValueError):
        context.mouse_move_mapped(**motion_arguments())
    assert not peer.calls


def test_motion_capability_does_not_require_probe_or_button_helpers_or_widen_claims(public_motion):
    session, peer = public_motion
    select_motion(session.vm)
    context = MachineContext(session.vm)
    assert context.capabilities['mapped_mouse_motion'] is True
    assert context.capabilities['renderer_probe'] is False
    assert context.capabilities['virtual_mouse_click'] is False
    for name in ('absolute_mouse', 'timed_input', 'guest_time_control', 'completed_guest_frames'):
        assert context.capabilities[name] is False
    assert not peer.calls


@pytest.mark.parametrize('clock,retrace', [('standard', 'precise'), ('instruction', 'precise'),
                                         ('virtual', 'standard'), ('virtual', None)])
def test_motion_capability_requires_both_selected_profiles(public_motion, clock, retrace):
    session, peer = public_motion
    select_motion(session.vm)
    session.vm.machine_configuration['clock_profile'] = machine_clock_configuration(clock, 1)
    if retrace is None:
        session.vm.machine_configuration.pop('retrace_profile')
    else:
        session.vm.machine_configuration['retrace_profile'] = {'profile': retrace}
    assert MachineContext(session.vm).capabilities['mapped_mouse_motion'] is False
    assert not peer.calls


def test_missing_motion_capability_refuses_whole_script_before_earlier_write(public_motion):
    session, peer = public_motion
    session.capabilities.update(mapped_mouse_motion=False, vga_configuration=True,
                                virtual_input_schedule=True, renderer_capture=True)
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    with pytest.raises(ValueError):
        execute_script(session, script(earlier_write(), dict(op='mouse.move-mapped', **motion_arguments())))
    assert_no_effects(session, peer, writes)


BAD_LITERALS = [
    {'dx_pixels': True}, {'dx_pixels': None}, {'dx_pixels': 1.0}, {'dx_pixels': '6'},
    {'dx_pixels': -8192}, {'dx_pixels': 8192}, {'dy_pixels': False}, {'dy_pixels': 8192},
    {'dx_pixels': 0, 'dy_pixels': 0},
    {'counts_per_pixel': None}, {'counts_per_pixel': []},
    {'counts_per_pixel': {'x': [1, 1]}},
    {'counts_per_pixel': {'x': [1, 1], 'y': [1, 1], 'z': [1, 1]}},
    {'counts_per_pixel': {'x': (1, 1), 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, 1, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [True, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [0, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [32768, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [-32768, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, True], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, 0], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, -1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, 32768], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1.0, 1], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': [1, 1], 'y': [1, 3]}},
    {'counts_per_pixel': {'x': [100, 1], 'y': [1, 1]}},
    {'window': None}, {'window': ''}, {'window': True}, {'window': 'a\0b'}, {'window': 'w' * 129},
    {'update_id': True}, {'update_id': 0}, {'update_id': -1}, {'update_id': 1 << 64},
    {'configuration_generation': True}, {'configuration_generation': 0},
    {'configuration_generation': 1 << 64},
    {'timeout_ms': None}, {'timeout_ms': True}, {'timeout_ms': 0},
    {'timeout_ms': -1}, {'timeout_ms': 600001}, {'timeout_ms': 1.5}, {'timeout_ms': '1000'},
]


@pytest.mark.parametrize('options', BAD_LITERALS)
def test_invalid_literal_motion_refuses_before_earlier_script_effects(public_motion, options):
    session, peer = public_motion
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    value = script(earlier_write(), dict(op='mouse.move-mapped', **motion_arguments(**options)))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, value)
    assert_no_effects(session, peer, writes)


@pytest.mark.parametrize('options', [
    {'dx_pixels': 1, 'dy_pixels': '$b.dy', 'counts_per_pixel': {'x': [1, 2], 'y': '$b.y'}},
    {'dx_pixels': 128, 'dy_pixels': '$b.dy', 'counts_per_pixel': {'x': [1, 1], 'y': '$b.y'}},
    {'dx_pixels': '$b.dx', 'dy_pixels': 3, 'counts_per_pixel': {'x': '$b.x', 'y': [-1, 2]}},
    {'dx_pixels': '$b.dx', 'dy_pixels': -128, 'counts_per_pixel': {'x': '$b.x', 'y': [1, 1]}},
    {'dx_pixels': 0, 'dy_pixels': 0, 'counts_per_pixel': '$b.scale'},
    {'dx_pixels': '$b.dx', 'counts_per_pixel': {'x': [True, '$b.den'], 'y': [1, 1]}},
    {'counts_per_pixel': {'x': '$b.x', 'y': [1, 0]}},
    {'counts_per_pixel': '$b.scale', 'configuration_generation': 0},
    {'window': '$b.window', 'update_id': True},
    {'timeout_ms': 600001, 'dx_pixels': '$b.dx'},
])
def test_known_axis_and_literal_validation_cannot_hide_behind_other_references(public_motion, options):
    session, peer = public_motion
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    value = script(earlier_write(), dict(op='mouse.move-mapped', **motion_arguments(**options)))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, value)
    assert_no_effects(session, peer, writes)


@pytest.mark.parametrize('field', ['dx_pixels', 'dy_pixels', 'counts_per_pixel', 'window',
                                 'update_id', 'configuration_generation'])
def test_every_required_motion_argument_is_checked_before_earlier_effects(public_motion, field):
    session, peer = public_motion
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    options = motion_arguments()
    del options[field]
    value = script(earlier_write(), dict(op='mouse.move-mapped', **options))
    with pytest.raises(TypeError):
        validate_script(value)
    with pytest.raises(TypeError):
        execute_script(session, value)
    assert_no_effects(session, peer, writes)


@pytest.mark.parametrize('field', ['x', 'y', 'button', 'origin', 'mode_id', 'frame_id', 'allow_references'])
def test_extra_signature_fields_refuse_even_when_all_values_are_references(public_motion, field):
    session, peer = public_motion
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    options = {key: '$b.' + key for key in motion_arguments()}
    options[field] = '$b.extra'
    value = script(earlier_write(), dict(op='mouse.move-mapped', **options))
    with pytest.raises(TypeError):
        validate_script(value)
    with pytest.raises(TypeError):
        execute_script(session, value)
    assert_no_effects(session, peer, writes)


@pytest.mark.parametrize('field,value', [
    ('dx_pixels', True), ('dy_pixels', 8192), ('counts_per_pixel', {'x': [1, 4], 'y': [1, 1]}),
    ('counts_per_pixel', {'x': [100, 1], 'y': [1, 1]}), ('counts_per_pixel', {'x': [1, 0], 'y': [1, 1]}),
    ('window', None), ('update_id', 0), ('configuration_generation', True),
    ('timeout_ms', None), ('timeout_ms', True), ('timeout_ms', 0), ('timeout_ms', 600001),
    ('timeout_ms', 1.0), ('timeout_ms', '1000'),
])
def test_resolved_motion_values_validate_before_dispatch_or_timeout_clamping(public_motion, field, value):
    session, peer = public_motion
    calls = []
    session.mouse_move_mapped = lambda *args, **kwargs: calls.append((args, kwargs))
    options = motion_arguments(**{field: '$b.value'})
    declaration = script(dict(op='mouse.move-mapped', **options))
    assert validate_script(declaration) == declaration['steps']
    report = execute_script(session, declaration, timeout_ms=125, bindings={'b': {'value': value}})
    assert not report['ok'] and report['completed_steps'] == 0, report
    assert report['error']['type'] in ('ValueError', 'TypeError')
    assert not calls and not peer.calls


def test_nested_reference_resolution_preserves_axis_order_and_original_ratios(public_motion):
    session, peer = public_motion
    calls = []
    session.mouse_move_mapped = lambda **kwargs: calls.append(deepcopy(kwargs)) or dict(state='armed')
    declaration = script(dict(op='mouse.move-mapped', **motion_arguments(
        dx_pixels='$b.dx', dy_pixels='$b.dy', counts_per_pixel={'x': ['$b.num', 3], 'y': '$b.y'},
        window='$b.window', update_id='$b.update', configuration_generation='$b.generation')))
    report = execute_script(session, declaration, bindings={'b': dict(
        dx=6, dy=-4, num=2, y=[3, 2], window='owned-retained-window', update=7, generation=5)})
    assert report['ok'], report
    assert calls == [motion_arguments()] and not peer.calls


@pytest.mark.parametrize('timeout,outer_ms,expected', [(None, 60000, 1000), (73, 60000, 73),
    (1, 60000, 1), (600000, 125, 125), ('$b.ms', 125, 125), (None, 125, 125)])
def test_motion_script_preserves_default_and_tighter_shared_deadline(public_motion, monkeypatch,
                                                                   timeout, outer_ms, expected):
    session, peer = public_motion
    calls = []
    session.mouse_move_mapped = lambda **kwargs: calls.append(kwargs['timeout_ms']) or dict(state='armed')
    options = motion_arguments()
    if timeout is None:
        options.pop('timeout_ms')
    else:
        options['timeout_ms'] = timeout
    monkeypatch.setattr('fdisbull.debug_script.time.monotonic', lambda: 100.0)
    report = execute_script(session, script(dict(op='mouse.move-mapped', **options)),
                            timeout_ms=outer_ms, bindings={'b': {'ms': 600000}})
    assert report['ok'], report
    assert calls == [expected] and not peer.calls


def test_motion_transaction_refuses_before_earlier_script_write(public_motion):
    session, peer = public_motion
    select_motion(session.vm)
    writes = []
    session.write_memory = lambda **kwargs: writes.append(kwargs)
    session.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            session.mouse_move_mapped(**motion_arguments())
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(earlier_write(), dict(op='mouse.move-mapped', **motion_arguments())))
        assert session.project.db.in_transaction
        assert_no_effects(session, peer, writes)
    finally:
        session.project.db.rollback()


@pytest.mark.parametrize('options', [{'dx_pixels': True}, {'timeout_ms': 0}, {'update_id': 0},
    {'counts_per_pixel': {'x': [1, 4], 'y': [1, 1]}}, {'origin': [0, 0]}])
@pytest.mark.parametrize('expired', [False, True], ids=['busy-owner', 'expired-deadline'])
def test_invalid_direct_motion_precedes_lock_and_deadline_admission(public_motion, options, expired):
    session, peer = public_motion
    attempted = []

    class BusyLock:
        def acquire(self, *, timeout):
            attempted.append(timeout)
            return False

    session.vm.lock = BusyLock()
    if expired:
        session._rpc_deadline = time.monotonic() - 1
    with pytest.raises((ValueError, TypeError)):
        session.mouse_move_mapped(**motion_arguments(**options))
    assert not attempted and not peer.calls and session.vm.qmp is peer


def test_failed_script_closes_after_passive_motion_arm(public_motion):
    session, peer = public_motion
    calls = []
    session.mouse_move_mapped = lambda **kwargs: calls.append(('motion', kwargs)) or dict(state='armed')
    session.close = lambda: calls.append(('close',))
    report = execute_script(session, script(dict(op='mouse.move-mapped', **motion_arguments()),
                                          dict(op='assert', value=False, equals=True)))
    assert not report['ok'] and report['completed_steps'] == 1
    assert calls == [('motion', motion_arguments()), ('close',)]
    assert report['input_cleanup']['closed'] is True and not peer.calls


def test_saved_script_preserves_motion_binding_and_unknown_guest_outcomes(public_motion):
    session, peer = public_motion
    receipt = dict(format='fdisbull-qemu-scheduled-input-1', state='armed',
        guest_consumed=None, device_queue_accepted=None,
        motion=dict(format='fdisbull-mapped-mouse-motion-1', binding_verified=False,
                    dx_pixels=6, dy_pixels=-4, dx=4, dy=-6,
                    counts_per_pixel={'x': [2, 3], 'y': [3, 2]},
                    guest_pixel_displacement=None, guest_pointer_position=None,
                    mapping_verified=None, raster_coherence=None, target_reached=None))
    session.mouse_move_mapped = lambda **kwargs: deepcopy(receipt)
    report = session.script(script(dict(op='mouse.move-mapped', **motion_arguments(), **{'as': 'motion'}),
        dict(op='assert', value='$motion.motion.binding_verified', equals=False),
        dict(op='assert', value='$motion.motion.guest_pointer_position', equals=None)))
    assert report['ok'] and report['completed_steps'] == 3, report
    stored = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (report['artifact'],)).fetchone()[0]
    assert json.loads(bytes(stored))['steps'][0]['result'] == receipt
    assert not peer.calls


def test_script_preserves_partial_motion_error_and_does_not_repeat_arm(public_motion):
    session, peer = public_motion
    evidence = dict(operation='mouse_move_mapped', native=None, validation_failed=True,
                    motion_plan={'dx': 4, 'dy': -6})
    calls = []

    def move(**kwargs):
        calls.append(kwargs)
        error = DebuggerError('Authored motion arm failure')
        error.result = deepcopy(evidence)
        raise error

    session.mouse_move_mapped = move
    report = execute_script(session, script(dict(op='mouse.move-mapped', **motion_arguments())))
    assert not report['ok'] and report['steps'][0]['result'] == evidence
    stored = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (report['artifact'],)).fetchone()[0]
    assert json.loads(bytes(stored))['steps'][0]['result'] == evidence
    assert calls == [motion_arguments()] and not peer.calls


def test_actual_motion_wrapper_retains_late_arm_receipt_and_invalidates_owner(public_motion, monkeypatch):
    from fdisbull import qemu_mapped_mouse
    session, peer = public_motion
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    observed = []
    receipt = dict(state='armed', token='late-motion', motion={'binding_verified': False})

    def move(owner, *args, **kwargs):
        observed.append((owner._deadline, owner.vm.operation_deadline, peer.operation_deadline))
        clock[0] = 100.126
        return receipt

    monkeypatch.setattr(qemu_mapped_mouse, 'mouse_move_mapped', move)
    with pytest.raises(TimeoutError) as caught:
        session.mouse_move_mapped(**motion_arguments(timeout_ms=125))
    assert caught.value.result == receipt and observed == [(100.125, 100.125, 100.125)]
    assert session.vm.qmp is None and not session.input_state()['valid']
    assert session._deadline is session.vm.operation_deadline is peer.operation_deadline is None
    assert not peer.calls


def test_actual_motion_wrapper_preserves_each_tighter_incoming_bound(public_motion, monkeypatch):
    from fdisbull import qemu_mapped_mouse
    session, peer = public_motion
    monkeypatch.setattr(time, 'monotonic', lambda: 100.0)
    session._rpc_deadline, session._deadline = 100.6, 100.5
    session.vm.operation_deadline, peer.operation_deadline = 100.4, 100.3

    def move(owner, *args, **kwargs):
        assert owner._deadline == owner.vm.operation_deadline == peer.operation_deadline == 100.3
        return dict(state='armed')

    monkeypatch.setattr(qemu_mapped_mouse, 'mouse_move_mapped', move)
    assert session.mouse_move_mapped(**motion_arguments()) == dict(state='armed')
    assert session._rpc_deadline == 100.6 and session._deadline == 100.5
    assert session.vm.operation_deadline == 100.4 and peer.operation_deadline == 100.3
    assert not peer.calls
