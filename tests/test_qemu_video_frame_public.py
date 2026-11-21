"""Explicit source-frame routes retain their Python envelopes and stop policy.

Transport peers test host routing/validation only; no native executable is
imported or launched. Raw RGBA is deliberately absent from JSON and scripts.
"""
from copy import deepcopy
from functools import wraps
import json

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_qemu_video_control import control, stopped
from test_qemu_video_frame import audio, observation, video


ROUTES = {
    'video-frame-start': ('debug-video-frame-start', 'video_frame_start'),
    'video-frame-observe': ('debug-video-frame-observe', 'video_frame_observe'),
    'video-frame-stop': ('debug-video-frame-stop', 'video_frame_stop'),
    'video-frame-probe': ('debug-video-frame-probe', 'video_frame_probe'),
    'capture-video-frame': ('debug-capture-video-frame', 'capture_video_frame'),
    'video-frame-advance': ('debug-video-frame-advance', 'video_frame_advance'),
}


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def enable_control(o):
    o.session.capabilities['video_frame_control'] = True
    return o


def request(workspace, o, method, **params):
    return respond(dict(id=1, method=method, params=dict(
        project=str(o.project.path), run=o.session.run_id, **params)), debugger=workspace)


def test_source_routes_are_discoverable_and_rgba_remains_python_only():
    for operation, (method, python_name) in ROUTES.items():
        assert method in METHODS and OPERATIONS[operation] == python_name
        assert python_name not in DebugSession.__dict__
    assert 'video-frame-rgba' not in OPERATIONS and 'debug-video-frame-rgba' not in METHODS


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_source_script_grammar_has_six_explicit_routes_without_legacy_capabilities(control, backend):
    o = enable_control(control)
    o.session.metadata['backend'] = backend
    for operation in ROUTES:
        params = {'points': []} if operation == 'video-frame-probe' else {}
        value = script(dict(op=operation, **params), backend=backend)
        assert validate_script(value, session=o.session) == value['steps']
        assert validate_script(value) == value['steps']
        assert operation in o.session.script_operations
    assert o.session.capabilities['completed_guest_frames'] is False
    assert not o.wire.calls and not o.executions


def test_six_json_routes_preserve_actual_source_envelopes_and_4096_ordered_samples(control, monkeypatch):
    o = enable_control(control)
    monkeypatch.setattr('time.monotonic_ns', lambda: 100_000_000_000)
    delegated = {}

    def recorder(name):
        original = getattr(o.session, name)

        @wraps(original)
        def invoke(*args, **kwargs):
            value = original(*args, **kwargs)
            delegated[name] = deepcopy(value)
            return value

        return invoke

    for name in ('video_frame_observe', 'video_frame_probe'):
        monkeypatch.setattr(o.session, name, recorder(name))
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    points = [[7, 9]] + [[0, 0]] * 4094 + [[7, 9]]
    try:
        with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
            start = request(workspace, o, 'debug-video-frame-start')['result']
            assert start['format'] == 'fdisbull-video-frame-stream-1' and start['frame_id'] is None
            advance = request(workspace, o, 'debug-video-frame-advance')['result']
            assert advance['format'] == 'fdisbull-video-frame-advance-1' and advance['advance_completed']
            assert advance['native_result'] == o.actual and advance['outcome'] == 'stopped'
            observed = request(workspace, o, 'debug-video-frame-observe')['result']
            assert observed == delegated['video_frame_observe']
            identity = dict(stream=observed['stream'], frame_id=observed['frame_id'])
            probe = request(workspace, o, 'debug-video-frame-probe', points=points, **identity)['result']
            assert probe == delegated['video_frame_probe']
            assert probe['clock']['sequence'] > observed['clock']['sequence']
            for field in ('run', 'epoch', 'clock_profile', 'counter', 'virtual_ns', 'virtual_clock'):
                assert probe['clock'][field] == observed['clock'][field]
            assert probe['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170]) for x, y in points]
            capture = request(workspace, o, 'debug-capture-video-frame', name='source.png', **identity)['result']
            assert capture['metadata']['frame'] == observed['frame'] and capture['artifact']
            stopped_stream = request(workspace, o, 'debug-video-frame-stop')['result']
            assert stopped_stream['state'] == 'stopped' and stopped_stream['frame'] == observed['frame']
            assert request(workspace, o, 'debug-video-frame-rgba')['ok'] is False
        assert len(o.executions) == 1
    finally:
        workspace.sessions.clear()


def test_script_routes_resolve_identity_and_preserve_dictionaries_without_rgba_serialization(control):
    o = enable_control(control)
    points = [[319, 199]] + [[0, 0]] * 4094 + [[319, 199]]
    value = script(
        dict(op='video-frame-start', **{'as': 'stream'}),
        dict(op='video-frame-advance', **{'as': 'advance'}),
        dict(op='video-frame-observe', **{'as': 'observed'}),
        dict(op='video-frame-probe', points=points, stream='$observed.stream', frame_id='$observed.frame_id'),
        dict(op='capture-video-frame', stream='$observed.stream', frame_id='$observed.frame_id'),
        dict(op='video-frame-stop'))
    report = execute_script(o.session, value)
    assert report['ok'] and report['completed_steps'] == report['requested_steps'] == 6
    results = [item['result'] for item in report['steps']]
    assert all(type(item) is dict for item in results)
    assert results[1]['advance_completed'] is True and results[1]['native_result'] == o.actual
    assert results[3]['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170]) for x, y in points]
    assert results[4]['metadata']['frame_id'] == results[2]['frame_id'] == 1
    assert results[5]['state'] == 'stopped'
    assert json.loads(json.dumps(report)) == report
    assert len(o.executions) == 1


@pytest.mark.parametrize('operation,capability', [
    ('video-frame-probe', 'video_frame_capture'), ('video-frame-advance', 'video_frame_control'),
])
def test_missing_capability_refuses_whole_route_before_an_earlier_write(control, operation, capability):
    o = enable_control(control)
    o.session.capabilities[capability] = False
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    params = {'points': []} if operation == 'video-frame-probe' else {}
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), dict(op=operation, **params))
    with pytest.raises(ValueError, match='native extension'):
        execute_script(o.session, value)
    assert not writes and not o.wire.calls and not o.executions
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('step', [
    dict(op='video-frame-probe', points=[[0, 0]] * 4097),
    dict(op='video-frame-probe', points=[['$p.x', 200]]),
    dict(op='video-frame-probe', points=[[True, '$p.y']]),
    dict(op='video-frame-probe', points=[('$p.x', 0)]),
    dict(op='video-frame-probe', points='$p.points', timeout_ms=False),
    dict(op='video-frame-probe', points=[], stream='$p.stream'),
    dict(op='video-frame-probe', points=[], stream='', frame_id='$p.id'),
    dict(op='video-frame-probe', points=[], stream='$p.stream', frame_id=0),
    dict(op='capture-video-frame', name='../escape.png', stream='$p.stream', frame_id='$p.id'),
    dict(op='capture-video-frame', name='$p.name', max_bytes=True),
    dict(op='video-frame-start', timeout_ms=600001),
    dict(op='video-frame-observe', timeout_ms=0),
    dict(op='video-frame-stop', timeout_ms=False),
    dict(op='video-frame-advance', timeout_ms='$p.timeout', stop_on_hook=1),
    dict(op='video-frame-probe', points=[], mode_id=1),
    dict(op='video-frame-rgba'),
])
def test_visible_bad_literals_cannot_hide_behind_references_or_an_earlier_mutation(control, step):
    o = enable_control(control)
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), step)
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(o.session, value)
    assert not writes and not o.wire.calls and not o.executions


@pytest.mark.parametrize('step,bindings', [
    (dict(op='video-frame-probe', points='$p.points'), {'p': {'points': [[0, 0]] * 4097}}),
    (dict(op='video-frame-probe', points=['$p.point']), {'p': {'point': [0, 200]}}),
    (dict(op='video-frame-probe', points=[['$p.x', 0]]), {'p': {'x': True}}),
    (dict(op='video-frame-probe', points=[], stream='$p.stream', frame_id='$p.id'),
     {'p': {'stream': None, 'id': 1}}),
    (dict(op='video-frame-probe', points=[], stream='$p.stream', frame_id='$p.id'),
     {'p': {'stream': 'owned', 'id': True}}),
    (dict(op='capture-video-frame', name='$p.name'), {'p': {'name': '../escape.png'}}),
    (dict(op='capture-video-frame', max_bytes='$p.size'), {'p': {'size': False}}),
    (dict(op='video-frame-observe', timeout_ms='$p.timeout'), {'p': {'timeout': 600001}}),
    (dict(op='video-frame-stop', timeout_ms='$p.timeout'), {'p': {'timeout': False}}),
    (dict(op='video-frame-advance', stop_on_hook='$p.stop'), {'p': {'stop': 1}}),
])
def test_resolved_source_parameters_validate_before_native_dispatch_or_timeout_clamp(control, step, bindings):
    o = enable_control(control)
    report = execute_script(o.session, script(step), bindings=bindings)
    assert report['ok'] is False and report['completed_steps'] == 0
    assert not o.wire.calls and not o.executions and not o.vm.closed


def test_transaction_refuses_the_whole_source_route_before_an_earlier_write(video):
    o = video
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    o.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(o.session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                            dict(op='video-frame-probe', points=[])))
        assert not writes and not o.wire.calls
    finally:
        o.project.db.rollback()


@pytest.mark.parametrize('accepted', [False, True], ids=['earlier-stop', 'accepted-raster-with-user-stop'])
def test_interrupted_source_advance_stops_script_with_the_actual_result(control, accepted):
    o = enable_control(control)
    o.session.video_frame_start()
    o.actual = stopped('breakpoint', reply='T05')
    o.dispatch = (lambda: o.wire.accept(consumed=False)) if accepted else (lambda: None)
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    report = execute_script(o.session, script(dict(op='video-frame-advance'),
        dict(op='write-memory', address=0x7c00, data_hex='90')))
    assert report['ok'] is False and report['completed_steps'] == 0 and len(report['steps']) == 1
    result = report['steps'][0]['result']
    assert result['format'] == 'fdisbull-video-frame-advance-1' and result['native_result'] == o.actual
    assert result['advance_completed'] is False and result['completed_source_raster'] is accepted
    assert result['outcome'] == 'breakpoint' and result['stop_consumed'] is False
    assert result['fence']['released']['released'] is True
    assert not writes and len(o.executions) == 1 and not o.vm.closed


def test_script_probe_keeps_one_outer_deadline_across_all_native_chunks(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    original = o.wire.sendall
    def delayed(data):
        original(data)
        if json.loads(data)['execute'] == 'x-fdisbull-probe-video-frame':
            o.wire.delay = .030
    o.wire.sendall = delayed
    report = execute_script(o.session, script(dict(op='video-frame-probe', points=[[7, 9]] * 4096,
                                                  timeout_ms=1000)), timeout_ms=50)
    assert report['ok'] is False and report['error']['type'] == 'TimeoutError'
    # Script admission floors the remaining allowance to whole milliseconds.
    # Binary floating point can conservatively turn 50 ms into 49 ms; neither
    # chunk may refresh that inherited allowance or exceed the original end.
    budgets = [budget for (command, _), budget in zip(o.wire.calls, o.wire.budgets, strict=True)
               if command == 'x-fdisbull-probe-video-frame']
    assert len(budgets) == 2 and .049 - 1e-9 <= budgets[0] <= .050 + 1e-9
    assert budgets[1] == pytest.approx(budgets[0] - .030)
    assert o.clock.now == pytest.approx(100 + budgets[0])
    assert 100.049 - 1e-9 <= o.clock.now <= 100.050 + 1e-9 and o.vm.closed
    assert len(report['steps'][0]['result']['probe_chunks']) == 1


def test_json_probe_failure_retains_received_chunks_under_the_normal_output_policy(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    count = 0
    def inconsistent(value):
        nonlocal count
        count += 1
        if count == 2:
            value['pixels'][-1]['r'] = 1
        return value
    o.wire.change_probe = inconsistent
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
            response = request(workspace, o, 'debug-video-frame-probe', points=[[7, 9]] * 257)
        assert response['ok'] is False
        evidence = response['error']['result']
        assert evidence['format'] == 'fdisbull-video-frame-error-1' and evidence['result'] is None
        assert len(evidence['probe_chunks']) == 2
        assert evidence['probe_chunks'][-1]['pixels'][-1]['r'] == 1 and o.vm.closed
    finally:
        workspace.sessions.clear()
