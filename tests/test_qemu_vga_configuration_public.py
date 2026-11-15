"""Public configuration routing and admission, separate from native evidence.

These cases use real projects and the existing stopped boundary peer. Positive
dispatch sentinels qualify forwarding and saved-script receipts only; native
configuration snapshots and their clock/generation validators run separately.
"""
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
from fdisbull.qemu_machine import MachineContext
from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration
from fdisbull.qemu_vga_configuration import VGA_CONFIGURATION_COMMANDS
from test_qemu_io_public import raw_project, stopped_session


CONFIGURATION_COMMANDS = (VGA_CONFIGURATION_COMMANDS | DISPLAY_COMMANDS |
                          RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS)


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


@pytest.fixture
def public_configuration(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['vga_configuration'] = True
    try:
        yield session, peer
    finally:
        session.close()


def selected_configuration(vm):
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    vm.qmp_commands = CONFIGURATION_COMMANDS


def assert_no_preflight_effects(session, peer, writes):
    assert not writes and not peer.calls and session.vm.qmp is peer
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_vga_configuration_has_a_direct_machine_operation():
    assert callable(getattr(MachineContext, 'vga_configuration_observe', None))
    assert not hasattr(DebugSession, 'vga_configuration_observe')


def test_vga_configuration_has_a_json_operation():
    assert 'debug-vga-configuration' in METHODS
    assert 'vga_configuration' in METHODS['debug-vga-configuration']
    assert 'timeout_ms' in METHODS['debug-vga-configuration']


def test_vga_configuration_has_a_saved_script_operation():
    assert OPERATIONS.get('vga-configuration') == 'vga_configuration_observe'


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_configuration_grammar_keeps_frame_and_coordinate_operations_separate(public_configuration, backend):
    session, peer = public_configuration
    session.metadata['backend'] = backend
    value = script(dict(op='vga-configuration', timeout_ms=73), backend=backend)
    assert validate_script(value, session=session) == value['steps']
    assert validate_script(value) == value['steps']
    assert 'vga-configuration' in session.script_operations
    for old in ('frame-probe', 'click', 'click-frame'):
        options = dict(points=[]) if old == 'frame-probe' else dict(x=0, y=0)
        with pytest.raises(ValueError, match='Unsupported'):
            validate_script(script(dict(op=old, **options), backend=backend))
    with pytest.raises(ValueError, match='Unsupported'):
        validate_script(dict(format='fdisbull-script-1', steps=[dict(op='vga-configuration')]))
    assert not peer.calls


@pytest.mark.parametrize('options', [{}, {'timeout_ms': 73}])
@pytest.mark.parametrize('context', [None, 'machine'])
def test_json_route_preserves_default_and_explicit_timeout(public_configuration, options, context):
    session, peer = public_configuration
    calls = []
    observation = dict(format='fdisbull-vga-configuration-1', current={'configuration_generation': 7},
                       published=None, configuration_matches=None, completed_guest_frame=None,
                       guest_frame_id=None, cursor_mapping=None, raster_coherence=None)

    def observe(*, timeout_ms=1000):
        calls.append(timeout_ms)
        return deepcopy(observation)

    session.vga_configuration_observe = observe
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    params = dict(project=str(session.project.path), run=session.run_id, **options)
    if context is not None:
        params['context'] = context
    try:
        response = respond(dict(id=31, method='debug-vga-configuration', params=params), debugger=workspace)
        assert response['ok'], response
        assert response['result'] == observation
        assert calls == [options.get('timeout_ms', 1000)] and not peer.calls
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('options', [dict(timeout_ms=True), dict(timeout_ms=0),
                                    dict(timeout_ms=600001), dict(mode_id=1)])
def test_json_invalid_values_or_signature_refuse_before_native_io(public_configuration, options):
    session, peer = public_configuration
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=32, method='debug-vga-configuration', params=dict(
            project=str(session.project.path), run=session.run_id, **options)), debugger=workspace)
        assert not response['ok'], response
        assert response['error']['type'] in ('ValueError', 'TypeError')
        assert not peer.calls and session.vm.qmp is peer
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('missing', sorted(CONFIGURATION_COMMANDS))
def test_configuration_capability_requires_every_native_dependency(public_configuration, missing):
    session, peer = public_configuration
    selected_configuration(session.vm)
    session.vm.qmp_commands -= {missing}
    context = MachineContext(session.vm).bind(session.project, session.run_id)
    assert context.capabilities['vga_configuration'] is False, missing
    with pytest.raises(ValueError, match='native extension'):
        context.vga_configuration_observe()
    assert not peer.calls and session.vm.qmp is peer


def test_nine_layer_commands_retain_renderer_capabilities_and_refuse_new_helper(public_configuration):
    session, peer = public_configuration
    selected_configuration(session.vm)
    session.vm.qmp_commands = CONFIGURATION_COMMANDS - VGA_CONFIGURATION_COMMANDS | DISPLAY_PROBE_COMMANDS
    context = MachineContext(session.vm).bind(session.project, session.run_id)
    assert context.capabilities['renderer_capture'] is True
    assert context.capabilities['renderer_probe'] is True
    assert context.capabilities['retrace_observation'] is True
    assert context.capabilities['vga_configuration'] is False
    with pytest.raises(ValueError, match='native extension'):
        context.vga_configuration_observe()
    assert not peer.calls and session.vm.qmp is peer


def test_configuration_capability_does_not_require_sparse_probe_or_widen_claims(public_configuration):
    session, peer = public_configuration
    selected_configuration(session.vm)
    context = MachineContext(session.vm)
    assert context.capabilities['vga_configuration'] is True
    assert context.capabilities['renderer_capture'] is True
    assert context.capabilities['renderer_probe'] is False
    for name in ('completed_guest_frames', 'absolute_mouse', 'timed_input', 'guest_time_control'):
        assert context.capabilities[name] is False
    assert not peer.calls


@pytest.mark.parametrize('clock,retrace', [('standard', 'precise'), ('instruction', 'precise'),
                                         ('virtual', 'standard'), ('virtual', None)])
def test_configuration_discovery_requires_both_selected_profiles(public_configuration, clock, retrace):
    session, peer = public_configuration
    selected_configuration(session.vm)
    session.vm.machine_configuration['clock_profile'] = machine_clock_configuration(clock, 1)
    if retrace is None:
        session.vm.machine_configuration.pop('retrace_profile')
    else:
        # Discovery flags are metadata checks, not proof of a successful launch.
        session.vm.machine_configuration['retrace_profile'] = {'profile': retrace}
    assert MachineContext(session.vm).capabilities['vga_configuration'] is False
    assert not peer.calls


def test_missing_configuration_capability_refuses_whole_script_before_earlier_write(public_configuration):
    session, peer = public_configuration
    session.capabilities.update(vga_configuration=False, renderer_capture=True, retrace_observation=True)
    writes = []
    session.write_memory = lambda address, data_hex, expected_hex: writes.append((address, data_hex, expected_hex))
    with pytest.raises(ValueError, match='native extension'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'),
                                       dict(op='vga-configuration')))
    assert_no_preflight_effects(session, peer, writes)


@pytest.mark.parametrize('timeout', [None, True, False, 0, -1, 600001, 1.0, '1000'])
def test_bad_literal_timeout_refuses_whole_script_before_earlier_effects(public_configuration, timeout):
    session, peer = public_configuration
    writes = []
    session.write_memory = lambda address, data_hex, expected_hex: writes.append((address, data_hex, expected_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'),
                   dict(op='vga-configuration', timeout_ms=timeout))
    with pytest.raises(ValueError):
        validate_script(value)
    with pytest.raises(ValueError):
        execute_script(session, value)
    assert_no_preflight_effects(session, peer, writes)


@pytest.mark.parametrize('options', [dict(mode_id=1), dict(frame_id=1), dict(window='old'),
    dict(points=[]), dict(configuration_generation=1), dict(timeout_ms='$bound.ms', unexpected='$bound.value'),
    dict(allow_references=True)])
def test_bad_script_signature_refuses_even_when_values_are_references(public_configuration, options):
    session, peer = public_configuration
    writes = []
    session.write_memory = lambda address, data_hex, expected_hex: writes.append((address, data_hex, expected_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'),
                   dict(op='vga-configuration', **options))
    with pytest.raises(TypeError):
        validate_script(value)
    with pytest.raises(TypeError):
        execute_script(session, value)
    assert_no_preflight_effects(session, peer, writes)


def test_transaction_preflight_refuses_observation_before_earlier_script_write(public_configuration):
    session, peer = public_configuration
    selected_configuration(session.vm)
    writes = []
    session.write_memory = lambda address, data_hex, expected_hex: writes.append((address, data_hex, expected_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'), dict(op='vga-configuration'))
    session.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            session.vga_configuration_observe()
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, value)
        assert session.project.db.in_transaction
        assert_no_preflight_effects(session, peer, writes)
    finally:
        session.project.db.rollback()


@pytest.mark.parametrize('timeout', [None, True, False, 0, -1, 600001, 1.0, '1000', [], {}])
def test_resolved_timeout_validates_before_dispatch_and_budget_clamping(public_configuration, timeout):
    session, peer = public_configuration
    calls = []

    def observe(*, timeout_ms=1000):
        calls.append(timeout_ms)
        return {}

    session.vga_configuration_observe = observe
    value = script(dict(op='vga-configuration', timeout_ms='$bound.ms'))
    assert validate_script(value) == value['steps']
    report = execute_script(session, value, bindings={'bound': {'ms': timeout}})
    assert not report['ok'] and report['completed_steps'] == 0, report
    assert report['error']['type'] == 'ValueError'
    assert not calls and not peer.calls


@pytest.mark.parametrize('options,bindings,outer_ms,expected', [
    ({}, {}, 60000, 1000),
    ({'timeout_ms': 73}, {}, 60000, 73),
    ({'timeout_ms': 1}, {}, 60000, 1),
    ({'timeout_ms': 600000}, {}, 125, 125),
    ({'timeout_ms': '$bound.ms'}, {'bound': {'ms': 73}}, 60000, 73),
    ({'timeout_ms': '$bound.ms'}, {'bound': {'ms': 600000}}, 125, 125),
    ({}, {}, 125, 125),
])
def test_script_default_explicit_and_resolved_bounds_preserve_tighter_allowance(
        public_configuration, monkeypatch, options, bindings, outer_ms, expected):
    session, peer = public_configuration
    calls = []

    def observe(*, timeout_ms=1000):
        calls.append(timeout_ms)
        return dict(configuration_matches=None)

    session.vga_configuration_observe = observe
    # The 125 ms outer limit has an exact binary representation. A fixed clock
    # makes this a budget-propagation witness rather than a wall-speed assertion.
    monkeypatch.setattr('fdisbull.debug_script.time.monotonic', lambda: 100.0)
    report = execute_script(session, script(dict(op='vga-configuration', **options)),
                            timeout_ms=outer_ms, bindings=bindings)
    assert report['ok'] and report['completed_steps'] == 1, report
    assert calls == [expected] and not peer.calls


def test_saved_script_result_retains_configuration_and_unknown_fields(public_configuration):
    session, peer = public_configuration
    observation = dict(format='fdisbull-vga-configuration-1', current={'configuration_generation': 9},
                       published={'configuration_generation': 7}, configuration_matches=False,
                       publication_configuration_semantics='configuration_observed_at_publication',
                       completed_guest_frame=None, guest_frame_id=None,
                       cursor_mapping=None, raster_coherence=None)
    calls = []

    def observe(*, timeout_ms=1000):
        calls.append(timeout_ms)
        return deepcopy(observation)

    session.vga_configuration_observe = observe
    value = script(dict(op='vga-configuration', **{'as': 'configuration'}),
        dict(op='assert', value='$configuration.configuration_matches', equals=False),
        dict(op='assert', value='$configuration.cursor_mapping', equals=None))
    report = session.script(value)
    assert report['ok'] and report['completed_steps'] == 3, report
    stored = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (report['artifact'],)).fetchone()[0]
    history = json.loads(bytes(stored))
    assert history['steps'][0]['result'] == observation
    assert history['input_cleanup'] is None and calls == [1000] and not peer.calls


def test_script_retains_partial_configuration_error_without_repeating_dispatch(public_configuration):
    session, peer = public_configuration
    evidence = dict(format='fdisbull-vga-configuration-error-1', stage='configuration-query',
                    received=True, native=None)
    calls = []

    def observe(*, timeout_ms=1000):
        calls.append(timeout_ms)
        error = DebuggerError('Configuration observation failed')
        error.result = deepcopy(evidence)
        raise error

    session.vga_configuration_observe = observe
    report = execute_script(session, script(dict(op='vga-configuration')))
    assert not report['ok'] and report['completed_steps'] == 0
    assert report['steps'][0]['result'] == evidence
    assert calls == [1000] and not peer.calls
    stored = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (report['artifact'],)).fetchone()[0]
    assert json.loads(bytes(stored))['steps'][0]['result'] == evidence


@pytest.mark.parametrize('args,options', [((1,), {}), ((), {'timeout_ms': True}),
                                       ((), {'timeout_ms': 0}), ((), {'mode_id': 1})])
@pytest.mark.parametrize('expired', [False, True], ids=['busy-owner', 'expired-deadline'])
def test_invalid_direct_signature_and_timeout_precede_admission(public_configuration, args, options, expired):
    session, peer = public_configuration
    attempted = []

    class BusyLock:
        def acquire(self, *, timeout):
            attempted.append(timeout)
            return False

    session.vm.lock = BusyLock()
    if expired:
        session._rpc_deadline = time.monotonic() - 1
    with pytest.raises((ValueError, TypeError)):
        session.vga_configuration_observe(*args, **options)
    assert not attempted and not peer.calls and session.vm.qmp is peer
