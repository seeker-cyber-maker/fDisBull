"""Public source-raster/state routes preserve the separately scoped receipt.

The authored QMP/GDB peers establish host routing and refusal behavior. These
tests do not launch a producer or qualify native/whole-machine coherence.
"""
from copy import deepcopy
from functools import wraps
import json

import pytest

from fdisbull.cli import METHODS, public_addresses, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_video_frame import video
from test_qemu_video_frame_state import state_observation


FORMAT = 'fdisbull-source-raster-state-observation-1'
OP = 'video-frame-state-observe'
METHOD = 'debug-video-frame-state-observe'
RANGES = [{'address': 0x7c00, 'length': 4}]


def script(*steps, backend='qemu-machine'):
    value = dict(format='fdisbull-script-1', steps=list(steps))
    if backend is not None:
        value['backend'] = backend
    return value


def request(workspace, o, method=METHOD, **params):
    return respond(dict(id=7, method=method, params=dict(
        project=str(o.project.path), run=o.session.run_id, **params)), debugger=workspace)


def calls(o):
    return len(o.wire.calls), len(o.gdb_wire.commands)


def test_state_route_has_its_own_capability_and_keeps_legacy_frame_claims(state_observation):
    o = state_observation
    assert METHOD in METHODS and OPERATIONS[OP] == 'video_frame_state_observe'
    assert 'video_frame_state_observe' not in DebugSession.__dict__
    assert OP in o.session.script_operations
    assert o.session.capabilities['completed_guest_frames'] is False
    assert o.session.capabilities['video_frame_state_observe'] is True
    assert 'frame-state-observe' not in OPERATIONS


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_native_grammars_validate_the_distinct_observation_without_dispatch(state_observation, backend):
    o = state_observation
    o.session.metadata['backend'] = backend
    prior = calls(o)
    value = script(dict(op=OP, ram_ranges=deepcopy(RANGES)), backend=backend)
    assert validate_script(value) == value['steps']
    assert validate_script(value, session=o.session) == value['steps']
    assert calls(o) == prior


def test_json_and_script_preserve_real_observations_and_typed_ram_addresses(state_observation, monkeypatch):
    o = state_observation
    observed = []
    original = o.session.video_frame_state_observe

    @wraps(original)
    def retain(**params):
        result = original(**params)
        observed.append(deepcopy(result))
        return result

    monkeypatch.setattr(o.session, 'video_frame_state_observe', retain)
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
            direct = request(workspace, o, ram_ranges=deepcopy(RANGES))
            assert direct['ok'] is True
            assert direct['result'] == observed[-1]
            value = script(dict(op=OP, ram_ranges=deepcopy(RANGES)))
            routed = request(workspace, o, method='debug-script', script=value)
            assert routed['ok'] and routed['result']['ok']
            assert routed['result']['completed_steps'] == 1
            nested = routed['result']['steps'][0]['result']
            assert nested == observed[-1]
        for result in (direct['result'], nested):
            assert result['format'] == FORMAT and result['complete'] is True
            assert result['atomic'] is False
            assert result['application_frame_complete'] is None
            assert result['frame_state_equivalence'] is None
            assert result['legacy_phase_equivalence'] is None
            assert result['state_before'] == result['state_after']
            assert result['input']['all_devices_neutral'] is None
            assert result['input']['mouse_state'] is None
            assert json.loads(json.dumps(result, allow_nan=False)) == result
        # Check the documented integer contract independently of its nesting.
        assert public_addresses({'format': FORMAT, 'selection': {'ram_ranges': RANGES}})[
            'selection']['ram_ranges'][0]['address'] == 0x7c00
        assert type(public_addresses({'format': FORMAT, 'address': 0x7c00})['address']) is int
        assert public_addresses({'address': 0x7c00}) == {'address': '0x7c00'}
        assert o.session.capabilities['completed_guest_frames'] is False
    finally:
        workspace.sessions.clear()


def test_script_resolves_nested_range_references_to_the_same_selected_projection(state_observation):
    o = state_observation
    value = script(dict(op=OP, ram_ranges=[{'address': '$selected.address', 'length': '$selected.length'}]))
    report = execute_script(o.session, value, bindings={'selected': dict(RANGES[0])})
    assert report['ok'] and report['completed_steps'] == 1
    result = report['steps'][0]['result']
    assert result['format'] == FORMAT and result['complete'] is True
    assert result['state_before'] == result['state_after']


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_missing_state_capability_refuses_whole_script_before_earlier_write(state_observation, backend):
    o = state_observation
    o.session.metadata['backend'] = backend
    o.session.capabilities['video_frame_state_observe'] = False
    # Source capture alone must never admit the stronger observation route.
    assert o.session.capabilities['video_frame_capture'] is True
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    before = calls(o)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op=OP, ram_ranges=deepcopy(RANGES)), backend=backend)
    with pytest.raises(ValueError, match='owned control authority'):
        execute_script(o.session, value)
    assert not writes and calls(o) == before
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        response = request(workspace, o, ram_ranges=deepcopy(RANGES))
        assert response['ok'] is False
        assert 'owned control authority' in response['error']['message']
        assert calls(o) == before
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('params', [
    {'ram_ranges': []},
    {'ram_ranges': [{'address': 0x1000 + i * 4, 'length': 4} for i in range(17)]},
    {'ram_ranges': [{'address': True, 'length': '$n'}]},
    {'ram_ranges': [{'address': '$address', 'length': 0}]},
    {'ram_ranges': [{'address': 0x7c00, 'length': True}]},
    {'ram_ranges': [{'address': '$address', 'length': 4097}]},
    {'ram_ranges': [{'address': i * 4096, 'length': 4096} for i in range(5)]},
    {'ram_ranges': [{'address': 0x7c00, 'length': 4}, {'address': 0x7c03, 'length': 4}]},
    {'ram_ranges': [{'address': 0xa0000, 'length': 1}]},
    {'ram_ranges': [{'address': 0x9ffff, 'length': 2}]},
    {'ram_ranges': [{'address': 0xc0000000, 'length': 1}]},
    {'ram_ranges': [{'address': 0x7c00, 'length': 4, 'space': 'virtual'}]},
    {'ram_ranges': '$selected', 'timeout_ms': False},
    {'ram_ranges': '$selected', 'timeout_ms': 600001},
    {'ram_ranges': '$selected', 'stream': '$stream'},
    {'ram_ranges': '$selected', 'stream': '', 'frame_id': '$id'},
    {'ram_ranges': '$selected', 'stream': '$stream', 'frame_id': 0},
    {'ram_ranges': '$selected', 'mode_id': 1},
])
def test_bad_visible_literals_refuse_before_any_earlier_mutation(state_observation, params):
    o = state_observation
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    before = calls(o)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), dict(op=OP, **params))
    with pytest.raises((ValueError, TypeError)):
        validate_script(value)
    with pytest.raises((ValueError, TypeError)):
        execute_script(o.session, value)
    assert not writes and calls(o) == before


@pytest.mark.parametrize('params,bindings', [
    ({'ram_ranges': '$selected'}, {'selected': []}),
    ({'ram_ranges': ['$range']}, {'range': {'address': 0x7c00, 'length': False}}),
    ({'ram_ranges': [{'address': '$address', 'length': 4}]}, {'address': 0xa0000}),
    ({'ram_ranges': [{'address': 0x7c00, 'length': '$length'}]}, {'length': 4097}),
    ({'ram_ranges': '$ranges'}, {'ranges': [dict(address=0x7c00, length=4), dict(address=0x7c02, length=4)]}),
    ({'ram_ranges': RANGES, 'timeout_ms': '$timeout'}, {'timeout': 600001}),
    ({'ram_ranges': RANGES, 'timeout_ms': '$timeout'}, {'timeout': False}),
    ({'ram_ranges': RANGES, 'stream': '$stream', 'frame_id': '$id'}, {'stream': None, 'id': 1}),
    ({'ram_ranges': RANGES, 'stream': '$stream', 'frame_id': '$id'}, {'stream': 'owned', 'id': True}),
])
def test_resolved_parameters_refuse_before_dispatch_or_timeout_clamping(state_observation, params, bindings):
    o = state_observation
    before = calls(o)
    report = execute_script(o.session, script(dict(op=OP, **deepcopy(params))), bindings=bindings)
    assert report['ok'] is False and report['completed_steps'] == 0
    assert calls(o) == before and not o.vm.closed


def test_transaction_refuses_observation_script_before_an_earlier_write(state_observation):
    o = state_observation
    writes = []
    o.session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    before = calls(o)
    o.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(o.session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                dict(op=OP, ram_ranges=deepcopy(RANGES))))
        assert not writes and calls(o) == before
    finally:
        o.project.db.rollback()


@pytest.mark.parametrize('backend', [None, 'wine-qemu', 'qemu-chip8'])
def test_legacy_and_other_backend_grammars_do_not_alias_the_observer(backend):
    with pytest.raises(ValueError, match='Unsupported operation|native QEMU'):
        validate_script(script(dict(op=OP, ram_ranges=deepcopy(RANGES)), backend=backend))


@pytest.mark.parametrize('route', ['json', 'script'])
def test_failed_real_rgb_export_retains_observation_and_cleanup_evidence_on_public_routes(state_observation, route, monkeypatch):
    o = state_observation
    o.wire.bad_export = True
    original = o.session.video_frame_state_observe
    extra = dict(video_frame_state_cleanup_error='AuthoredOwnerCleanupError',
                 video_frame_cleanup_error='AuthoredSourceCleanupError',
                 video_frame_file_cleanup_error='PermissionError',
                 video_frame_state_evidence_error='AuthoredBoundedEvidenceError')

    @wraps(original)
    def retain_cleanup(**params):
        try:
            return original(**params)
        except Exception as error:
            # The actual corrupt export supplies the failure and observation.
            # Independently authored secondary failures exercise both public
            # envelopes without changing the observer's primary error.
            for field, message in extra.items():
                setattr(error, field, message)
            raise

    monkeypatch.setattr(o.session, 'video_frame_state_observe', retain_cleanup)
    if route == 'script':
        report = execute_script(o.session, script(dict(op=OP, ram_ranges=deepcopy(RANGES))))
        assert report['ok'] is False and report['completed_steps'] == 0
        envelope = report['steps'][0]
    else:
        workspace = DebugWorkspace()
        workspace.sessions[o.session.run_id] = o.session
        try:
            with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
                response = request(workspace, o, ram_ranges=deepcopy(RANGES))
            assert response['ok'] is False
            envelope = response['error']
        finally:
            workspace.sessions.clear()
    receipts = [envelope.get('result'), envelope.get('video_frame_state_evidence')]
    partial = next(item for item in receipts if isinstance(item,dict) and item.get('format') == FORMAT)
    assert partial['complete'] is False and partial['atomic'] is False
    assert partial['issues'] and partial['state_before'] is not None
    assert {field: envelope[field] for field in extra} == extra
    assert o.vm.closed
