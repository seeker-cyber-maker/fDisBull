"""Public opt-in native stopped-control routing and failure preservation.

Authored packet peers exercise host validation and public envelopes only.
These tests do not launch QEMU or qualify native dispatch/mutation coverage.
Recovered after a workspace rollback; the final failure tests were rebuilt
from the recorded contract where their original source was not retained.
"""
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_video_frame import video
from test_qemu_video_frame_state import state_observation
from test_qemu_stopped_control import ARM, QUERY, PROCESS, native_state


ARM_OP = 'stopped-control-arm'
ARM_METHOD = 'debug-stopped-control-arm'
OBSERVE_OP = 'video-frame-state-observe'
OBSERVE_METHOD = 'debug-video-frame-state-observe'
FORMAT = 'fdisbull-qemu-stopped-control-1'
RANGES = [{'address': 0x7c00, 'length': 4}]


@pytest.fixture
def public_native(native_state):
    # The shared peer adds its new commands after constructing the session.
    # Production capability discovery instead reads the launch-time catalog.
    native_state.session.capabilities['native_stopped_control'] = True
    return native_state


@pytest.fixture
def workspace(public_native):
    value = DebugWorkspace()
    value.sessions[public_native.session.run_id] = public_native.session
    try:
        yield value
    finally:
        value.sessions.clear()


def script(*steps, backend='qemu-machine'):
    value = dict(format='fdisbull-script-1', steps=list(steps))
    if backend is not None:
        value['backend'] = backend
    return value


def request(workspace, o, method, **params):
    return respond(dict(id=9, method=method, params=dict(
        project=str(o.project.path), run=o.session.run_id, **params)), debugger=workspace)


def calls(o):
    return len(o.wire.calls), len(o.gdb_wire.commands)


def test_stopped_control_route_is_explicit_and_discoverable(public_native):
    o = public_native
    assert ARM_METHOD in METHODS and OPERATIONS[ARM_OP] == 'stopped_control_arm'
    assert 'native_control_token' in METHODS[OBSERVE_METHOD]
    assert 'stopped_control_arm' not in DebugSession.__dict__
    assert ARM_OP in o.session.script_operations
    assert o.session.capabilities['completed_guest_frames'] is False


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_native_grammars_accept_arm_and_token_references_without_dispatch(public_native, backend):
    o = public_native
    o.session.metadata['backend'] = backend
    value = script(dict(op=ARM_OP, timeout_ms='$timeout', **{'as': 'control'}),
        dict(op=OBSERVE_OP, ram_ranges=deepcopy(RANGES),
             native_control_token='$control.token'), backend=backend)
    before = calls(o)
    assert validate_script(value) == value['steps']
    assert validate_script(value, session=o.session) == value['steps']
    assert calls(o) == before


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
@pytest.mark.parametrize('route', ['json', 'script'])
def test_public_arm_and_observe_preserve_real_native_receipts(public_native, workspace,
                                                            backend, route, monkeypatch):
    o = public_native
    o.session.metadata['backend'] = backend
    retained = {}

    def recorder(name):
        original = getattr(o.session, name)

        @wraps(original)
        def invoke(**params):
            result = original(**params)
            retained[name] = deepcopy(result)
            return result

        return invoke

    for name in ('stopped_control_arm', 'video_frame_state_observe'):
        monkeypatch.setattr(o.session, name, recorder(name))
    with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
        if route == 'json':
            response = request(workspace, o, ARM_METHOD, timeout_ms=1000)
            assert response['ok'] is True
            armed = response['result']
            response = request(workspace, o, OBSERVE_METHOD, ram_ranges=deepcopy(RANGES),
                               native_control_token=armed['token'])
            assert response['ok'] is True
            observed = response['result']
        else:
            value = script(dict(op=ARM_OP, **{'as': 'control'}),
                dict(op=OBSERVE_OP, ram_ranges=deepcopy(RANGES),
                     native_control_token='$control.token'), backend=backend)
            response = request(workspace, o, 'debug-script', script=value)
            assert response['ok'] and response['result']['ok']
            assert response['result']['completed_steps'] == 2
            armed, observed = [step['result'] for step in response['result']['steps']]
    assert armed == retained['stopped_control_arm']
    assert observed == retained['video_frame_state_observe']
    assert armed['format'] == FORMAT and armed['complete'] is True
    assert armed['token'] == armed['native']['token']
    assert armed['native']['process-id'] == PROCESS
    assert observed['complete'] is True and observed['atomic'] is False
    assert observed['native_mutation_revision'] is None
    assert observed['native_control']['scope'] == 'stopped-native-control-admission-v1'
    assert observed['native_control']['before'] == observed['native_control']['after']
    assert observed['source']['exported'] is None
    assert observed['source']['rgb_origin'] == 'previously-verified-immutable-export'
    commands = [name for name, _ in o.wire.calls]
    assert commands.count(ARM) == 1 and commands.count(QUERY) == 2
    assert 'x-fdisbull-export-video-frame' not in commands
    assert not o.vm.closed


@pytest.mark.parametrize('route', ['json', 'script'])
def test_absent_native_capability_keeps_explicit_none_observation_cooperative(public_native, workspace, route):
    o = public_native
    o.session.capabilities['native_stopped_control'] = False
    params = dict(ram_ranges=deepcopy(RANGES), native_control_token=None)
    if route == 'json':
        response = request(workspace, o, OBSERVE_METHOD, **params)
        assert response['ok']
        observed = response['result']
    else:
        report = execute_script(o.session, script(dict(op=OBSERVE_OP, **params)))
        assert report['ok'] and report['completed_steps'] == 1
        observed = report['steps'][0]['result']
    assert observed['complete'] and observed.get('native_control') is None
    commands = [name for name, _ in o.wire.calls]
    assert ARM not in commands and QUERY not in commands
    assert 'x-fdisbull-export-video-frame' in commands


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
@pytest.mark.parametrize('selection', ['arm', 'literal', 'reference'])
def test_missing_native_capability_refuses_before_an_earlier_write(public_native, workspace,
                                                                 backend, selection):
    o = public_native
    o.session.metadata['backend'] = backend
    o.session.capabilities['native_stopped_control'] = False
    assert o.session.capabilities['video_frame_state_observe'] is True
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    if selection == 'arm':
        step, method, params = dict(op=ARM_OP), ARM_METHOD, {}
    else:
        token = '$control.token' if selection == 'reference' else 'a' * 32
        params = dict(ram_ranges=deepcopy(RANGES), native_control_token=token)
        step, method = dict(op=OBSERVE_OP, **params), OBSERVE_METHOD
    before = calls(o)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), step, backend=backend)
    with pytest.raises(ValueError, match='native_stopped_control'):
        execute_script(o.session, value)
    assert not writes and calls(o) == before
    if selection != 'reference':
        response = request(workspace, o, method, **params)
        assert not response['ok'] and 'native_stopped_control' in response['error']['message']
        assert calls(o) == before


@pytest.mark.parametrize('op,params', [
    (ARM_OP, {'timeout_ms': False}),
    (ARM_OP, {'timeout_ms': 0}),
    (ARM_OP, {'timeout_ms': 600001}),
    (ARM_OP, {'token': 'a' * 32}),
    (OBSERVE_OP, {'native_control_token': ''}),
    (OBSERVE_OP, {'native_control_token': 'a' * 31}),
    (OBSERVE_OP, {'native_control_token': 'A' * 32}),
    (OBSERVE_OP, {'native_control_token': 'g' * 32}),
    (OBSERVE_OP, {'native_control_token': True}),
    (OBSERVE_OP, {'native_control_token': {}}),
    (OBSERVE_OP, {'native_control_token': []}),
])
def test_bad_public_literals_refuse_before_dispatch_or_earlier_mutation(public_native, workspace, op, params):
    o = public_native
    params = deepcopy(params)
    if op == OBSERVE_OP:
        params['ram_ranges'] = deepcopy(RANGES)
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    before = calls(o)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), dict(op=op, **params))
    with pytest.raises((TypeError, ValueError)):
        validate_script(value)
    with pytest.raises((TypeError, ValueError)):
        execute_script(o.session, value)
    response = request(workspace, o, ARM_METHOD if op == ARM_OP else OBSERVE_METHOD, **params)
    assert not response['ok']
    assert not writes and calls(o) == before and not o.vm.closed


@pytest.mark.parametrize('op,params,bindings', [
    (ARM_OP, {'timeout_ms': '$timeout'}, {'timeout': False}),
    (ARM_OP, {'timeout_ms': '$timeout'}, {'timeout': 600001}),
    (OBSERVE_OP, {'native_control_token': '$token'}, {'token': True}),
    (OBSERVE_OP, {'native_control_token': '$token'}, {'token': ''}),
    (OBSERVE_OP, {'native_control_token': '$token'}, {'token': 'A' * 32}),
    (OBSERVE_OP, {'native_control_token': '$token'}, {'token': []}),
])
def test_resolved_parameters_fail_before_timeout_clamp_or_dispatch(public_native, op, params, bindings):
    o = public_native
    params = deepcopy(params)
    if op == OBSERVE_OP:
        params['ram_ranges'] = deepcopy(RANGES)
    before = calls(o)
    report = execute_script(o.session, script(dict(op=op, **params)), bindings=bindings)
    assert not report['ok'] and report['completed_steps'] == 0
    assert calls(o) == before and not o.vm.closed


@pytest.mark.parametrize('backend', [None, 'wine-qemu', 'qemu-chip8'])
def test_arm_is_not_available_in_other_script_grammars(backend):
    with pytest.raises(ValueError, match='Unsupported operation|native QEMU'):
        validate_script(script(dict(op=ARM_OP), backend=backend))


@pytest.mark.parametrize('method', [ARM_METHOD, OBSERVE_METHOD])
def test_native_capability_cannot_admit_an_otherwise_wrong_json_backend(public_native, workspace, method):
    o = public_native
    o.session.metadata['backend'] = 'qemu-chip8'
    params = (dict(ram_ranges=deepcopy(RANGES), native_control_token='a' * 32)
              if method == OBSERVE_METHOD else {})
    before = calls(o)
    response = request(workspace, o, method, **params)
    assert not response['ok']
    assert calls(o) == before


def test_arm_script_transaction_guard_precedes_earlier_write(public_native):
    o = public_native
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    before = calls(o)
    o.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(o.session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                            dict(op=ARM_OP)))
        assert not writes and calls(o) == before
    finally:
        o.project.db.rollback()


@pytest.mark.parametrize('route', ['json', 'script'])
def test_missing_scope_never_autoarms_or_falls_back(public_native, workspace, route):
    o = public_native
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    params = dict(ram_ranges=deepcopy(RANGES), native_control_token='a' * 32)
    before = calls(o)
    if route == 'json':
        response = request(workspace, o, OBSERVE_METHOD, **params)
        assert response['ok'] is False
    else:
        report = execute_script(o.session, script(dict(op=OBSERVE_OP, **params),
            dict(op='write-memory', address=0x7c00, data_hex='90')))
        assert report['ok'] is False and report['completed_steps'] == 0
        assert len(report['steps']) == 1
    assert calls(o) == before and not writes and not o.vm.closed


@pytest.mark.parametrize('route', ['json', 'script'])
def test_native_observer_failure_keeps_actual_both_receipts_and_stops_script(public_native, workspace, route):
    o = public_native
    token = o.session.stopped_control_arm()['token']
    queries, writes = [], []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))

    def change(value):
        queries.append(1)
        return dict(value, generation=value['generation'] + 2) if len(queries) == 2 else value

    o.native_change = change
    params = dict(ram_ranges=deepcopy(RANGES), native_control_token=token)
    with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
        if route == 'json':
            response = request(workspace, o, OBSERVE_METHOD, **params)
            assert response['ok'] is False
            value = response['error']['result']
        else:
            report = execute_script(o.session, script(dict(op=OBSERVE_OP, **params),
                dict(op='write-memory', address=0x7c00, data_hex='90')))
            assert report['ok'] is False and report['completed_steps'] == 0
            assert len(report['steps']) == 1
            value = report['steps'][0]['result']
    assert value['format'] == 'fdisbull-source-raster-state-observation-1'
    assert value['complete'] is False and value['native_control']['complete'] is False
    assert value['native_control']['before']['generation'] == 17
    assert value['native_control']['after']['generation'] == 19
    assert value['state_before'] == value['state_after']
    assert value['native_mutation_revision'] is None and value['atomic'] is False
    assert not writes and o.vm.closed


@pytest.mark.parametrize('route', ['json', 'script'])
def test_uncertain_arm_keeps_actual_native_reply_and_stops_script(public_native, workspace, route):
    o = public_native
    o.native_change = lambda value: dict(value, generation=True)
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
        if route == 'json':
            response = request(workspace, o, ARM_METHOD)
            assert response['ok'] is False
            value = response['error']['result']
        else:
            report = execute_script(o.session, script(dict(op=ARM_OP),
                dict(op='write-memory', address=0x7c00, data_hex='90')))
            assert report['ok'] is False and report['completed_steps'] == 0
            assert len(report['steps']) == 1
            value = report['steps'][0]['result']
    assert value['format'] == FORMAT and value['complete'] is False
    assert value['native']['generation'] is True
    assert value['native']['process-id'] == PROCESS
    assert not writes and o.vm.closed


@pytest.mark.parametrize('route', ['json', 'script'])
@pytest.mark.parametrize('replacement', ['process', 'qmp-socket', 'gdb-socket'])
def test_original_owner_preflight_failure_survives_public_envelope(public_native, workspace,
                                                                 route, replacement):
    o = public_native
    token = o.session.stopped_control_arm()['token']
    touched = []
    foreign = SimpleNamespace(closed=False, recv=lambda *_: touched.append('recv'),
        sendall=lambda *_: touched.append('send'), close=lambda: touched.append('close'))
    if replacement == 'process':
        original = o.vm.process
        o.vm.process = foreign
    else:
        protocol = replacement.split('-')[0]
        client = getattr(o.vm, protocol)
        original = client.socket
        client.socket = foreign
    before = calls(o)
    params = dict(ram_ranges=deepcopy(RANGES), native_control_token=token)
    try:
        with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
            if route == 'json':
                response = request(workspace, o, OBSERVE_METHOD, **params)
                assert response['ok'] is False
                value = response['error']['result']
            else:
                report = execute_script(o.session, script(dict(op=OBSERVE_OP, **params)))
                assert report['ok'] is False and report['completed_steps'] == 0
                value = report['steps'][0]['result']
        assert value['format'] == 'fdisbull-source-raster-state-observation-1'
        assert value['stage'] == 'original-owner-binding' and value['complete'] is False
        assert value['native_control']['complete'] is False
        assert value['native_control']['before'] is value['native_control']['after'] is None
        assert calls(o) == before and not touched
        if replacement != 'process':
            assert client.socket is foreign
    finally:
        if replacement == 'process':
            o.vm.process = original

