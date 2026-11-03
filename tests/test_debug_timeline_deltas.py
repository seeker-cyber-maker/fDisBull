"""Lossless native-payload history, distinct from selected CPU/RAM undo."""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from test_debug_timeline import Session, start


@pytest.fixture
def debug():
    session = Session()
    yield session
    session.db.close()


def test_delta_history_pins_complete_native_bytes_and_restores_input(debug):
    start(debug, storage_mode='delta', keyframe_interval=8)
    debug.timeline_advance(3, inputs=[
        {'frame': 0, 'edges': [{'key': 'right', 'pressed': True}]},
        {'frame': 2, 'edges': [{'key': 'right', 'pressed': False}]},
    ])
    status = debug.timeline_status()
    assert status['storage_mode'] == 'delta' and status['delta_state_points'] > 0
    assert status['retained_encoded_state_payload_bytes'] < status['reconstructed_state_payload_bytes']
    before = (debug.captures, debug.cpu, len(debug.calls))
    pinned = debug.timeline_pin()
    assert (debug.captures, debug.cpu, len(debug.calls)) == before
    data = debug.db.execute("SELECT data FROM artifacts WHERE kind='state'").fetchone()[0]
    assert hashlib.sha256(data).hexdigest() == pinned['sha256'] == status['checkpoint_sha256']
    assert json.loads(data) == dict(cpu=3, ram=list(debug.ram), keys=[])
    debug.timeline_rewind(2)
    assert debug.cpu == 1 and debug.ram[0] == 1 and debug.keys == {'right'}
    assert debug.timeline_status()['resume_safe']


def test_delta_eviction_rebases_independent_successor_and_branch(debug):
    start(debug, storage_mode='delta', keyframe_interval=8, max_frames=2)
    debug.timeline_advance(9)
    status = debug.timeline_status()
    assert status['retained_points'] == 3 and status['points'][0]['storage_kind'] == 'full'
    assert status['bytes_used'] <= status['max_bytes']
    debug.timeline_rewind(2)
    assert debug.cpu == 7
    branch = debug.timeline_status()['branch']
    debug.timeline_advance()
    assert debug.cpu == 8 and debug.timeline_status()['branch'] != branch
    assert debug.timeline_status()['cursor'] == 8
    debug.timeline_rewind()
    assert debug.cpu == 7


def test_rebase_preserves_existing_context_envelopes_and_releases_base(debug):
    start(debug, storage_mode='delta', keyframe_interval=8, max_frames=2)
    debug.timeline_advance(2)
    previous = {p['id']: p['envelope_sha256'] for p in debug._frame_timeline['points']}
    removed = debug._frame_timeline['points'][0]['id']
    debug.timeline_advance()
    points = debug._frame_timeline['points']
    assert removed not in {p['id'] for p in points}
    for point in points:
        if point['id'] in previous:
            assert point['envelope_sha256'] == previous[point['id']]
    assert 'delta' not in points[0] and points[1]['delta']['depth'] == 1
    assert 'data' not in points[1]['checkpoint']
    assert debug.timeline_status()['codec_transient_bound_bytes'] >= 6 * debug.timeline_status()['raw_checkpoint_limit_bytes']


def test_full_and_delta_public_pins_and_images_match_for_the_same_authored_native_context():
    full, delta = Session(), Session()
    try:
        start(full)
        start(delta, storage_mode='delta', keyframe_interval=4)
        for index in range(16):
            inputs = [{'frame': 0, 'edges': [{'key': 'right', 'pressed': index % 2 == 0}]}]
            full.timeline_advance(inputs=inputs)
            delta.timeline_advance(inputs=inputs)
            assert full.timeline_pin()['sha256'] == delta.timeline_pin()['sha256']
            assert full.timeline_image()['sha256'] == delta.timeline_image()['sha256']
        assert delta.timeline_status()['delta_state_points'] > 0
        assert full.captures == delta.captures == 17
    finally:
        full.db.close()
        delta.db.close()


@pytest.mark.parametrize('kind', ['payload', 'base', 'descriptor', 'ancestor', 'image'])
def test_delta_corruption_refuses_restore_pin_and_forward_before_mutation(debug, kind):
    start(debug, storage_mode='delta', keyframe_interval=8)
    debug.timeline_advance(3)
    points = debug._frame_timeline['points']
    point = points[2]
    if kind == 'payload':
        point['delta']['payload'] += b'x'
    elif kind == 'base':
        point['delta']['base_point'] = points[0]['id']
    elif kind == 'descriptor':
        point['delta']['result_size'] += 1
    elif kind == 'ancestor':
        points[0]['checkpoint']['data'] += b'x'
    else:
        point['image'] = b'corrupt'
    before = (debug.cpu, bytes(debug.ram), set(debug.keys), debug.captures, debug.restores)
    with pytest.raises(ValueError):
        debug.timeline_rewind()
    with pytest.raises(ValueError):
        debug.timeline_pin()
    with pytest.raises(ValueError):
        debug.timeline_advance()
    assert (debug.cpu, bytes(debug.ram), set(debug.keys), debug.captures, debug.restores) == before
    assert not debug.closed


def test_delta_failed_preflight_rebase_preserves_old_future(debug):
    start(debug, storage_mode='delta', keyframe_interval=8, max_frames=3)
    debug.timeline_advance(3)
    debug.timeline_rewind(2)
    history = debug._frame_timeline
    before = deepcopy(history['points'])
    identity = (history['cursor'], history['branch'], history['next_frame'])
    history['max_bytes'] = 1
    calls = list(debug.calls)
    with pytest.raises(ValueError, match='reserve'):
        debug.timeline_advance()
    assert history['points'] == before
    assert (history['cursor'], history['branch'], history['next_frame']) == identity
    assert debug.calls == calls and not debug.closed


def test_delta_rng_preservation_freeze_and_provenance_remain(debug):
    debug.ram[256] = 3
    start(debug, storage_mode='delta', keyframe_interval=8)
    debug.timeline_advance(2)
    debug.ram[256] = 9
    returned = debug.timeline_rewind(policy={
        'name': 'current-rng', 'preserve_memory': [{'address': '0x10100', 'length': 1}]})
    assert debug.cpu == 1 and debug.ram[256] == 9
    assert not returned['resume_safe'] and not returned['execution_allowed']
    with pytest.raises(ValueError):
        debug.timeline_advance()
    with pytest.raises(ValueError):
        debug.timeline_stop()
    debug.timeline_rewind(0)
    assert debug.ram[256] == 3
    debug.timeline_advance()
    debug.ram[256] = 11
    debug.timeline_rewind(policy={'name': 'explicit-mixed', 'preserve_memory': [
        {'address': '0x10100', 'length': 1}], 'allow_partial_resume': True})
    debug.timeline_advance()
    pinned = debug.timeline_pin()
    assert pinned['metadata']['timeline_experiment']['policy']['name'] == 'explicit-mixed'
    assert not debug.timeline_status()['resume_safe']


@pytest.mark.parametrize('interval', [1, 4])
def test_periodic_keyframes_bound_all_reconstruction_chains(debug, interval):
    start(debug, storage_mode='delta', keyframe_interval=interval)
    debug.timeline_advance(9)
    status = debug.timeline_status()
    assert all(p['delta_depth'] < interval for p in status['points'])
    assert all(p['storage_kind'] == 'full' for p in status['points'] if p['frame'] % interval == 0)
    assert status['captures_used'] == debug.captures == 10
    assert status['bytes_used'] == status['state_bytes_used'] + status['image_bytes_used'] + status['input_bytes_used']
    assert status['state_payload_bytes'] == status['retained_encoded_state_payload_bytes']
    assert status['reconstructed_state_payload_bytes'] == sum(p['checkpoint_size'] for p in status['points'])


def test_expired_delta_decode_deadline_does_not_start_guest_work(debug):
    start(debug, storage_mode='delta')
    debug.timeline_advance(2)
    debug._rpc_deadline = time.monotonic() - 1
    calls = list(debug.calls)
    with pytest.raises(TimeoutError, match='codec'):
        debug.timeline_advance()
    assert debug.calls == calls and debug.cpu == 2 and not debug.closed


def test_delta_encode_expiry_after_completed_frame_closes_uncertain_operation(debug, monkeypatch):
    from fdisbull import frame_state_codec
    start(debug, storage_mode='delta')
    original = frame_state_codec.encode
    def expired(*args, **kwargs):
        result = original(*args, **kwargs)
        debug._rpc_deadline = time.monotonic() - 1
        return result
    monkeypatch.setattr(frame_state_codec, 'encode', expired)
    with pytest.raises(TimeoutError, match='codec'):
        debug.timeline_advance()
    assert debug.cpu == 1 and debug.closed


@pytest.mark.parametrize('options', [
    {'storage_mode': 'unknown'}, {'keyframe_interval': 0},
    {'keyframe_interval': 129}, {'keyframe_interval': True},
])
def test_delta_options_refuse_before_native_calls(debug, options):
    with pytest.raises(ValueError):
        start(debug, **options)
    assert debug.calls == [] and debug.captures == 0


def test_json_workspace_routes_delta_options_to_the_owned_session(debug, tmp_path):
    from fdisbull.debugger import DebugWorkspace
    debug.project = SimpleNamespace(path=tmp_path.resolve())
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    status = workspace.invoke('debug-timeline-start', tmp_path, dict(
        run=debug.run_id, storage_mode='delta', keyframe_interval=4,
        max_state_bytes=8192, max_image_bytes=1024))
    assert status['storage_mode'] == 'delta' and status['keyframe_interval'] == 4
