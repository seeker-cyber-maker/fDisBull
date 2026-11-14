"""Sparse renderer observations keep a separate public publication contract."""
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.qemu_machine import MachineContext
from test_qemu_io_public import raw_project, stopped_session


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def test_sparse_renderer_probe_is_discoverable_without_a_legacy_frame_stub():
    assert 'debug-display-probe' in METHODS
    assert OPERATIONS['display-probe'] == 'display_probe'
    assert 'display_probe' not in DebugSession.__dict__


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_sparse_renderer_probe_script_grammar_preserves_legacy_frame_refusal(raw_project, tmp_path, backend):
    session, peer = stopped_session(raw_project, tmp_path)
    session.metadata['backend'] = backend
    session.capabilities['renderer_probe'] = True
    value = script(dict(op='display-probe', points=[[4, 3], [0, 0], [4, 3]],
                        window='owned-publication', update_id=1), backend=backend)
    assert validate_script(value, session=session) == value['steps']
    assert validate_script(value) == value['steps']
    assert 'display-probe' in session.script_operations
    for old in ('frame-probe', 'click', 'click-frame'):
        options = dict(points=[]) if old == 'frame-probe' else dict(x=0, y=0)
        with pytest.raises(ValueError, match='Unsupported'):
            validate_script(script(dict(op=old, **options), backend=backend))
    assert not peer.calls


@pytest.mark.parametrize('options', [dict(points=[]),
    dict(points=[[2, 4], [0, 0]], window='owned', update_id=8, timeout_ms=73)])
def test_json_probe_route_preserves_optional_identity_and_default_bound(raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    calls = []
    def probe(points, *, window=None, update_id=None, timeout_ms=1000):
        calls.append(dict(points=points, window=window, update_id=update_id, timeout_ms=timeout_ms))
        return dict(format='fdisbull-renderer-probe-1', pixels=[], completed_guest_frame=None)
    session.display_probe = probe
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=3, method='debug-display-probe', params=dict(
            project=str(raw_project.path), run=session.run_id, context='machine', **options)),
            debugger=workspace)
        assert response['ok'], response
        assert response['result']['completed_guest_frame'] is None
        assert calls == [dict({'window': None, 'update_id': None, 'timeout_ms': 1000}, **options)]
        assert not peer.calls
    finally:
        workspace.sessions.clear()
        session.close()


def test_probe_capability_requires_every_native_command_and_virtual_profile(raw_project, tmp_path):
    from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
    from fdisbull.qemu_display import DISPLAY_COMMANDS, DISPLAY_PROBE_COMMANDS
    session, peer = stopped_session(raw_project, tmp_path)
    vm = session.vm
    commands = DISPLAY_COMMANDS | DISPLAY_PROBE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    for missing in sorted(commands):
        vm.qmp_commands = commands - {missing}
        assert MachineContext(vm).capabilities['renderer_probe'] is False, missing
    vm.qmp_commands = commands - DISPLAY_PROBE_COMMANDS
    context = MachineContext(vm)
    assert context.capabilities['renderer_capture'] is True
    assert context.capabilities['renderer_probe'] is False
    with pytest.raises(ValueError, match='native extension'):
        context.display_probe([])
    vm.qmp_commands = commands
    context = MachineContext(vm)
    assert context.capabilities['renderer_probe'] is True
    for capability in ('completed_guest_frames', 'timed_input', 'guest_time_control', 'absolute_mouse'):
        assert context.capabilities[capability] is False
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('instruction', 1)
    assert MachineContext(vm).capabilities['renderer_probe'] is False
    assert not peer.calls


def test_missing_probe_capability_refuses_whole_script_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['renderer_capture'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with pytest.raises(ValueError, match='native extension'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                       dict(op='display-probe', points=[])))
    assert not writes and not peer.calls


@pytest.mark.parametrize('options', [
    dict(points=[['$p.x', -1]]), dict(points=[[True, '$p.y']]),
    dict(points=['$p.point', [0, 8192]]), dict(points=['$p.point'] * 257),
    dict(points=[('$p.x', 0)]), dict(points=[['$p.x', 0, 1]]),
    dict(points='$p.points', timeout_ms=False),
    dict(points='$p.points', window='$p.window'),
    dict(points=[], update_id='$p.id'),
    dict(points=[], window='$p.window', update_id=0),
    dict(points=[], window='', update_id='$p.id'),
    dict(points=[], window='$p.window', update_id='$p.id', timeout_ms=0),
    dict(points=[], frame_id=1), dict(points=[], mode_id=1),
])
def test_visible_bad_literals_refuse_before_earlier_effects_even_with_references(raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['renderer_probe'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op='display-probe', **options))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, value)
    assert not writes and not peer.calls


@pytest.mark.parametrize('options,bindings', [
    (dict(points='$p.points'), {'p': {'points': [[True, 0]]}}),
    (dict(points=['$p.point']), {'p': {'point': [0, 8192]}}),
    (dict(points=[['$p.x', 0]]), {'p': {'x': -1}}),
    (dict(points=[], window='$p.window', update_id='$p.id'), {'p': {'window': None, 'id': 1}}),
    (dict(points=[], window='$p.window', update_id='$p.id'), {'p': {'window': 'w', 'id': True}}),
    (dict(points=[], timeout_ms='$p.timeout'), {'p': {'timeout': True}}),
    (dict(points=[], timeout_ms='$p.timeout'), {'p': {'timeout': 0}}),
    (dict(points=[], timeout_ms='$p.timeout'), {'p': {'timeout': 1000000}}),
])
def test_resolved_parameters_validate_before_dispatch_or_timeout_clamping(raw_project, tmp_path, options, bindings):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['renderer_probe'] = True
    calls = []
    session.display_probe = lambda *args, **kwargs: calls.append((args, kwargs))
    report = execute_script(session, script(dict(op='display-probe', **options)), bindings=bindings)
    assert not report['ok'] and not calls and not peer.calls


def test_reference_resolution_preserves_order_and_probe_default_bound(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['renderer_probe'] = True
    calls = []
    def probe(points, *, window=None, update_id=None, timeout_ms=1000):
        calls.append(dict(points=points, window=window, update_id=update_id, timeout_ms=timeout_ms))
        return dict(pixels=[])
    session.display_probe = probe
    report = execute_script(session, script(dict(op='display-probe',
        points=[['$p.x', 1], '$p.point'], window='$p.window', update_id='$p.id')),
        bindings={'p': {'x': 4, 'point': [2, 3], 'window': 'owned', 'id': 12}})
    assert report['ok'], report
    assert calls == [dict(points=[[4, 1], [2, 3]], window='owned', update_id=12, timeout_ms=1000)]
    assert not peer.calls


def test_transaction_refuses_probe_and_whole_script_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['renderer_probe'] = True
    from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
    from fdisbull.qemu_display import DISPLAY_COMMANDS, DISPLAY_PROBE_COMMANDS
    session.vm.qmp_commands = VIRTUAL_CLOCK_COMMANDS | DISPLAY_COMMANDS | DISPLAY_PROBE_COMMANDS
    session.vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    raw_project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            session.display_probe([])
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                           dict(op='display-probe', points=[])))
        assert not writes and not peer.calls and session.vm.qmp is peer
    finally:
        raw_project.db.rollback()


@pytest.mark.parametrize('options', [dict(points=[[True, 0]]), dict(points=[], update_id=1),
                                    dict(points=[], timeout_ms=True), dict(points=[], frame_id=1)])
@pytest.mark.parametrize('expired', [False, True], ids=['busy-owner', 'expired-deadline'])
def test_invalid_direct_probe_precedes_lock_and_deadline_admission(raw_project, tmp_path, options, expired):
    session, peer = stopped_session(raw_project, tmp_path)
    attempted = []
    class BusyLock:
        def acquire(self, *, timeout):
            attempted.append(timeout)
            return False
    session.vm.lock = BusyLock()
    if expired:
        session._rpc_deadline = time.monotonic() - 1
    with pytest.raises((ValueError, TypeError)):
        session.display_probe(**options)
    assert not attempted and not peer.calls and session.vm.qmp is peer
