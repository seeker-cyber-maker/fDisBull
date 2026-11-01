"""Timeline ownership and full-state contracts, without substituting for native qualification."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import sqlite3
import time
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull.debug_timeline import FrameTimelineSessionMixin, timeline_locked
from fdisbull.debug_timeline import validate_edges, validate_schedule, validate_timeline_policy


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Session(FrameTimelineSessionMixin):
    def __init__(self):
        self.closed = False
        self.run_id, self.version = 'live', {'id': 1}
        self.metadata = dict(backend='dosbox', source_sha256='source', version_sha256='version',
            emulator_sha256='native', runtime_profile='real', runtime_load_segment=0x1000, game_dir='/private/game')
        self.rpc = SimpleNamespace(capabilities={'frame_timeline': True})
        self.static_base, self.delta, self.module_size = 0x10000, 0, 64
        self.ram, self.cpu, self.keys = bytearray(512), 0, set()
        self.native_frame = 0
        self.edge_capacity = 32
        self.manifest = [{'path': 'authored.exe', 'sha256': 'original'}]
        self.calls, self.events, self.artifacts = [], [], []
        self.captures = self.restores = 0
        self.fail_capture = self.fail_restore = self.fail_step = self.bad_image = False
        self.fail_write = False
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE artifacts(kind TEXT, data BLOB, metadata TEXT)')

    def _disk_manifest(self):
        return deepcopy(self.manifest)

    def _layer_state(self):
        return {'active': [], 'ram_applied': {}}

    def _event(self, operation, result):
        self.events.append((operation, deepcopy(result)))

    def _artifact(self, name, kind, data, metadata):
        self.db.execute('INSERT INTO artifacts VALUES (?,?,?)', (kind, data, json.dumps(metadata)))
        result = dict(artifact=str(len(self.artifacts)), name=name, sha256=sha(data), size=len(data), metadata=deepcopy(metadata))
        self.artifacts.append(result)
        return result

    @timeline_locked
    def call(self, method, params=None):
        if self.closed:
            raise ValueError('closed')
        self._timeline_before_call(method, params)
        deadline = getattr(self, '_rpc_deadline', None)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('shared deadline expired')
        self.calls.append(method)
        params = params or {}
        if method == 'session.status':
            return {'state': 'stopped'}
        if method == 'input.keyboard.state':
            return {'keyboard': {'pending_events': 0, 'owned_keys': 0, 'frame_keys': sorted(self.keys),
                                 'frame_edge_capacity': self.edge_capacity}}
        if method == 'input.mouse.state':
            return {'mouse': {'release_pending': False}}
        if method == 'input.keyboard.frame_edges':
            for edge in params['edges']:
                (self.keys.add if edge['pressed'] else self.keys.remove)(edge['key'])
            return {'accepted': True, 'keyboard': {'frame_keys': sorted(self.keys)}}
        if method == 'frame.step':
            self.cpu += 1
            self.ram[0] += 1
            self.native_frame += 1
            if self.fail_step:
                raise TimeoutError('unknown frame outcome')
            return dict(frame_id=self.native_frame, captured_ticks=self.cpu * 16, guest_ticks=self.cpu * 16,
                        state='stopped', completed=True, stop_reason={'kind': 'frame'})
        if method == 'video.screenshot':
            if not self.native_frame:
                raise ValueError('No complete framebuffer is available')
            stream = io.BytesIO()
            Image.new('RGB', (2, 2), (self.ram[0], 0, 0)).save(stream, format='PNG')
            data = stream.getvalue()
            return dict(png_base64=base64.b64encode(data).decode(), sha256='bad' if self.bad_image else sha(data),
                        width=2, height=2, frame_id=self.native_frame, mode_id=1)
        if method in ('memory.read', 'memory.write'):
            offset = int(params['address']['offset'], 16) - self.static_base
            if method == 'memory.read':
                data = bytes(self.ram[offset:offset + params['length']])
                return dict(data_base64=base64.b64encode(data).decode(), sha256=sha(data))
            data = base64.b64decode(params['data_base64'])
            assert sha(bytes(self.ram[offset:offset + len(data)])) == params['expected_sha256']
            if self.fail_write:
                raise TimeoutError('unknown RAM write outcome')
            self.ram[offset:offset + len(data)] = data
            return {}
        if method in ('state.load', 'state.save', 'execution.continue'):
            return {}
        raise AssertionError(method)

    def _capture_native_checkpoint(self, max_bytes=None):
        self.captures += 1
        if self.fail_capture:
            raise ValueError('capture failure')
        data = json.dumps(dict(cpu=self.cpu, ram=list(self.ram), keys=sorted(self.keys))).encode()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('state budget')
        return dict(data=data, sha256=sha(data), metadata=dict(self.metadata,
            disk_manifest=deepcopy(self.manifest), registers={'cpu': self.cpu}, frame_keys=sorted(self.keys)))

    def _restore_native_checkpoint(self, checkpoint):
        self.restores += 1
        with self._timeline_full_load():
            self.call('state.load')
            state = json.loads(checkpoint['data'])
            self.cpu, self.ram, self.keys = state['cpu'], bytearray(state['ram']), set(state['keys'])
            if self.fail_restore:
                raise TimeoutError('unknown native restore outcome')
            self.metadata.pop('timeline_experiment', None)
            if 'timeline_experiment' in checkpoint['metadata']:
                self.metadata['timeline_experiment'] = deepcopy(checkpoint['metadata']['timeline_experiment'])
            self._timeline_loaded()
        return dict(sha256=checkpoint['sha256'], registers={'cpu': self.cpu}, state='stopped')

    def close(self):
        self.closed = True


@pytest.fixture
def debug():
    session = Session()
    yield session
    session.db.close()


def start(debug, **kwargs):
    return debug.timeline_start(max_state_bytes=8192, max_image_bytes=1024, **kwargs)


def test_full_states_and_input_branching_are_live_only(debug):
    status = start(debug)
    assert status['point_kind'] == 'initial-paused' and debug.cpu == 0
    assert debug.artifacts == []
    debug.timeline_advance(3, inputs=[{'frame': 0, 'edges': [{'key': 'right', 'pressed': True}]}])
    assert debug.cpu == 3 and debug.keys == {'right'}
    debug.timeline_rewind(2)
    assert debug.cpu == 1 and debug.ram[0] == 1 and debug.keys == {'right'}
    old_branch = debug.timeline_status()['branch']
    debug.timeline_advance(inputs=[{'frame': 0, 'edges': [{'key': 'right', 'pressed': False}]}])
    assert debug.cpu == 2 and debug.keys == set()
    status = debug.timeline_status()
    assert status['branch'] != old_branch and status['retained_points'] == 3
    assert debug.artifacts == []
    debug.timeline_stop()
    assert debug.timeline_status()['retained_points'] == 0 and debug.cpu == 2


def test_pending_input_can_be_cancelled_without_replaying_it(debug):
    start(debug)
    initial = debug.timeline_status()['checkpoint_sha256']
    debug.frame_inputs([{'key': 'enter', 'pressed': True}])
    assert debug.timeline_status()['current_dirty'] and debug.keys == {'enter'}
    assert debug.timeline_status()['checkpoint_sha256'] == initial
    with pytest.raises(ValueError, match='dirty'):
        debug.timeline_pin()
    debug.timeline_rewind(0)
    assert debug.keys == set() and debug.cpu == 0
    assert debug.timeline_status()['current_cached']
    debug.timeline_advance(inputs=[{'frame': 0, 'edges': [{'key': 'escape', 'pressed': True}]}])
    assert debug.keys == {'escape'} and debug.cpu == 1


def test_pin_and_stored_image_do_not_recapture_or_execute(debug):
    start(debug)
    debug.timeline_advance(2)
    debug.timeline_rewind()
    before = (debug.captures, debug.cpu, len(debug.calls))
    stone = debug.timeline_pin('manual.sav')
    image = debug.timeline_image('history.png')
    assert (debug.captures, debug.cpu, len(debug.calls)) == before
    assert stone['sha256'] == debug.timeline_status()['checkpoint_sha256']
    row = debug.db.execute("SELECT data FROM artifacts WHERE kind='screenshot'").fetchone()
    with Image.open(io.BytesIO(row[0])) as stored:
        assert stored.getpixel((0, 0)) == (1, 0, 0)
    assert image['metadata']['stored_frame']


def test_policy_preserves_dynamic_ram_outside_original_module(debug):
    debug.ram[256] = 3
    start(debug)
    debug.timeline_advance(2)
    debug.ram[256] = 9  # Diagnostic current RNG value in dynamic conventional RAM.
    result = debug.timeline_rewind(policy={'name': 'rng', 'preserve_memory': [
        {'address': '0x10100', 'length': 1}], 'allow_partial_resume': True})
    assert debug.cpu == 1 and debug.ram[0] == 1 and debug.ram[256] == 9
    assert result['full_native_state_loaded'] and not result['full_machine_restored']
    assert not result['resume_safe'] and result['execution_allowed']
    assert debug.timeline_status()['current_dirty']
    with pytest.raises(ValueError, match='dirty'):
        debug.timeline_pin()
    debug.timeline_advance()
    assert debug.timeline_status()['current_cached']
    assert debug.timeline_pin()['metadata']['timeline_experiment']['policy']['name'] == 'rng'


def test_frozen_policy_cannot_be_bypassed_by_stop_or_restart(debug):
    start(debug)
    debug.timeline_advance(2)
    debug.timeline_rewind(policy={'preserve_memory': [{'address': '0x10000', 'length': 1}]})
    for action in (debug.timeline_stop, lambda: start(debug), debug.advance_frames,
                   lambda: debug.call('execution.continue'), lambda: debug.call('state.save')):
        with pytest.raises(ValueError, match='frozen|Restore'):
            action()
    debug.timeline_rewind(0)
    debug.timeline_advance()
    assert not debug.closed


@pytest.mark.parametrize('failure', ['capture', 'step', 'image', 'restore', 'write'])
def test_uncertain_forward_restore_or_policy_failure_closes(debug, failure):
    start(debug)
    debug.timeline_advance(2)
    setattr(debug, {'capture': 'fail_capture', 'step': 'fail_step', 'image': 'bad_image',
                    'restore': 'fail_restore', 'write': 'fail_write'}[failure], True)
    with pytest.raises((ValueError, TimeoutError)):
        if failure in ('capture', 'step', 'image'):
            debug.timeline_advance()
        else:
            debug.timeline_rewind(policy={'preserve_memory': [{'address': '0x10000', 'length': 1}],
                                           'allow_partial_resume': True})
    assert debug.closed and not debug.timeline_status()['valid']


def test_retained_ring_and_cumulative_capture_budget(debug):
    start(debug, max_frames=2, max_captures=5)
    debug.timeline_advance(4)
    status = debug.timeline_status()
    assert status['retained_points'] == 3 and status['available_back'] == 2
    assert status['captures_used'] == 5 and status['bytes_used'] <= status['max_bytes']
    calls = list(debug.calls)
    with pytest.raises(ValueError, match='capture budget'):
        debug.timeline_advance()
    assert debug.calls == calls
    debug.timeline_rewind(2)
    assert debug.cpu == 2


@pytest.mark.parametrize('tamper', ['data', 'metadata', 'image'])
def test_envelope_corruption_refuses_before_restore(debug, tamper):
    start(debug)
    debug.timeline_advance(2)
    point = debug._frame_timeline['points'][1]
    if tamper == 'data':
        point['checkpoint']['data'] = b'bad'
    elif tamper == 'metadata':
        point['checkpoint']['metadata']['frame_keys'] = ['enter']
    else:
        point['image'] = b'bad'
    with pytest.raises(ValueError, match='hash'):
        debug.timeline_rewind()
    assert debug.restores == 0 and not debug.closed


def test_external_mutation_invalidates_before_dispatch_and_receipts_are_detached(debug):
    result = start(debug)
    result['points'][0]['checkpoint_sha256'] = 'changed'
    assert debug.timeline_status()['checkpoint_sha256'] != 'changed'
    debug.call('execution.continue')
    assert not debug.timeline_status()['valid']
    with pytest.raises(ValueError):
        debug.timeline_rewind(0)


@pytest.mark.parametrize('edges', [[{'key': 'enter', 'pressed': 1}], [{'key': 'unknown', 'pressed': True}],
    [{'key': 'esc', 'pressed': True}, {'key': 'escape', 'pressed': False}], [{'key': 'enter'}]])
def test_bad_edges_refuse_without_native_calls(debug, edges):
    with pytest.raises(ValueError):
        debug.frame_inputs(edges)
    assert not debug.calls


def test_schedule_is_preflighted_in_full_before_first_frame(debug):
    start(debug)
    before = list(debug.calls)
    with pytest.raises(ValueError):
        debug.timeline_advance(2, inputs=[{'frame': 1, 'edges': [{'key': 'enter', 'pressed': 1}]}])
    assert debug.cpu == 0 and debug.calls == before
    validate_edges('$edges', allow_references=True)
    validate_schedule([{'frame': '$offset', 'edges': '$edges'}], '$frames', allow_references=True)
    validate_timeline_policy({'preserve_memory': '$ranges'}, allow_references=True)


def test_new_branch_keeps_logical_frame_indices_contiguous(debug):
    start(debug)
    debug.timeline_advance(6)
    debug.timeline_rewind(4)
    debug.timeline_advance(2)
    status = debug.timeline_status()
    assert [p['frame'] for p in status['points']] == [0, 1, 2, 3, 4]
    assert status['captures_used'] == 9
    assert debug.cpu == 4


@pytest.mark.parametrize('active', [False, True])
def test_unknown_input_delivery_closes_even_before_dirty_receipt(debug, active):
    if active:
        start(debug)
    original = debug.call
    def accepted_then_lost_reply(method, params=None):
        result = original(method, params)
        if method == 'input.keyboard.frame_edges':
            raise TimeoutError('accepted input, reply lost')
        return result
    debug.call = accepted_then_lost_reply
    with pytest.raises(TimeoutError, match='reply lost'):
        debug.frame_inputs([{'key': 'enter', 'pressed': True}])
    assert debug.closed and debug.keys == {'enter'}


def test_unrecorded_frame_timeout_closes(debug):
    debug.fail_step = True
    with pytest.raises(TimeoutError):
        debug.advance_frames()
    assert debug.closed


def test_error_receipt_failure_cannot_skip_close_or_mask_original_error(debug):
    start(debug)
    debug.fail_step = True
    def unavailable_receipt(operation, result):
        raise sqlite3.OperationalError('receipt unavailable')
    debug._event = unavailable_receipt
    with pytest.raises(TimeoutError, match='unknown frame outcome'):
        debug.timeline_advance()
    assert debug.closed and not debug.timeline_status()['valid']


def test_manual_verified_full_load_clears_frozen_guard_without_reconnecting_history(debug):
    start(debug)
    debug.timeline_advance(2)
    checkpoint = deepcopy(debug._frame_timeline['points'][0]['checkpoint'])
    debug.timeline_rewind(policy={'preserve_memory': [{'address': '0x10000', 'length': 1}]})
    debug._restore_native_checkpoint(checkpoint)
    assert not debug._frame_timeline['mixed_frozen']
    assert not debug.timeline_status()['valid']
    debug.call('execution.continue')


def test_expired_deadline_never_starts_frame_and_keeps_history_usable(debug, monkeypatch):
    start(debug)
    debug._rpc_deadline = 1.0
    monkeypatch.setattr(time, 'monotonic', lambda: 2.0)
    calls = list(debug.calls)
    with pytest.raises(TimeoutError):
        debug.timeline_advance()
    assert debug.calls == calls and debug.cpu == 0 and not debug.closed
    assert debug.timeline_status()['valid']


def test_image_dimensions_must_match_the_decoded_stored_png(debug):
    start(debug)
    original = debug.call
    def wrong_dimensions(method, params=None):
        result = original(method, params)
        if method == 'video.screenshot':
            result['width'] += 1
        return result
    debug.call = wrong_dimensions
    with pytest.raises(ValueError, match='dimensions'):
        debug.timeline_advance()
    assert debug.closed


def test_timeline_lock_supports_borrowed_methods():
    borrowed = timeline_locked(lambda self: 7)
    foreign = SimpleNamespace()
    assert borrowed(foreign) == 7
    with FrameTimelineSessionMixin._timeline_full_load(foreign):
        FrameTimelineSessionMixin._timeline_loaded(foreign)


def test_status_payload_denominators_match_the_retained_blobs(debug):
    start(debug)
    debug.timeline_advance(2)
    status = debug.timeline_status()
    assert status['state_payload_bytes'] == sum(p['checkpoint_size'] for p in status['points'])
    assert status['image_payload_bytes'] == sum(p['image_size'] for p in status['points'])
    assert status['bytes_used'] == status['state_bytes_used'] + status['image_bytes_used'] + status['input_bytes_used']


def test_invalidation_cannot_remove_frozen_input_guard(debug):
    start(debug)
    debug.timeline_advance(2)
    debug.timeline_rewind(policy={'preserve_memory': [{'address': '0x10000', 'length': 1}]})
    debug._timeline_invalidate('input identities changed')
    calls = list(debug.calls)
    with pytest.raises(ValueError, match='frozen'):
        debug.frame_inputs([{'key': 'enter', 'pressed': True}])
    assert debug.keys == set() and debug.calls == calls


def test_only_canonical_missing_initial_frame_is_optional(debug):
    from fdisbull.dosbox_rpc import DebuggerError
    original = debug.call
    def missing_frame(method, params=None):
        if method == 'video.screenshot':
            raise DebuggerError('Stored frame unavailable (FRAMEBUFFER_UNAVAILABLE)')
        return original(method, params)
    debug.call = missing_frame
    assert start(debug)['retained_points'] == 1
    with pytest.raises(ValueError, match='no completed'):
        debug.timeline_image()
    with pytest.raises(DebuggerError):
        debug.timeline_advance()
    assert debug.closed


def test_restoring_a_recorded_mixed_context_keeps_its_provenance(debug):
    start(debug)
    debug.timeline_advance(2)
    debug.timeline_rewind(policy={'name': 'mixed-rng', 'preserve_memory': [
        {'address': '0x10000', 'length': 1}], 'allow_partial_resume': True})
    debug.timeline_advance(2)
    restored = debug.timeline_rewind()
    assert restored['experiment']['policy']['name'] == 'mixed-rng'
    assert not restored['resume_safe'] and not restored['full_machine_restored']
    assert not debug.timeline_status()['resume_safe']


@pytest.mark.parametrize('change', [{'completed': False}, {'stop_reason': {'kind': 'breakpoint'}}])
def test_stopped_frame_receipt_alone_is_not_completed_frame_evidence(debug, change):
    start(debug)
    original = debug.call
    def interrupted_frame(method, params=None):
        result = original(method, params)
        if method == 'frame.step':
            result.update(change)
        return result
    debug.call = interrupted_frame
    with pytest.raises(ValueError, match='completed frame'):
        debug.timeline_advance()
    assert debug.captures == 1 and debug.timeline_status()['cursor'] == 0
    assert debug.closed


def test_complete_scheduled_key_ownership_is_checked_before_first_frame(debug):
    start(debug)
    schedule = [{'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]},
                {'frame': 2, 'edges': [{'key': 'a', 'pressed': True}]}]
    with pytest.raises(ValueError, match='already'):
        debug.timeline_advance(3, inputs=schedule)
    assert 'frame.step' not in debug.calls and 'input.keyboard.frame_edges' not in debug.calls
    assert debug.cpu == 0 and not debug.keys and not debug.closed
    assert debug.timeline_status()['valid']


def test_durable_events_do_not_copy_the_whole_live_point_ring(debug):
    start(debug)
    result = debug.timeline_advance(3)
    assert len(result['timeline']['points']) == 4
    event = next(receipt for name, receipt in reversed(debug.events) if name == 'timeline-advance')
    assert 'points' not in event['timeline']
    assert event['completed_frames'] == 3


def test_scheduled_input_journal_budget_refusal_preserves_future_and_session(debug):
    start(debug)
    debug.timeline_advance(2)
    debug.timeline_rewind(2)
    history = debug._frame_timeline
    initial_size = history['points'][0]['bytes']
    # There is room for the next maximum-sized state/image, but not its
    # additional input journal. The existing future remains valid and intact.
    history['max_bytes'] = initial_size + history['max_state_bytes'] + history['max_image_bytes'] + 128
    before = debug.timeline_status()
    calls = list(debug.calls)
    with pytest.raises(ValueError, match='reserve'):
        debug.timeline_advance(inputs=[{'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]}])
    assert debug.timeline_status() == before
    assert debug.calls == calls and debug.cpu == 0 and not debug.keys and not debug.closed


@pytest.mark.parametrize('status_state,status_revision,accepted', [
    ('stopped', 19, True), ('stopped', 20, False), ('stopped', None, False), ('running', 19, False)])
def test_native_frame_receipt_without_state_requires_matching_stopped_revision(
        debug, status_state, status_revision, accepted):
    start(debug)
    original = debug.call
    def native_contract(method, params=None):
        result = original(method, params)
        if method == 'frame.step':
            del result['state']
            result['state_revision'] = 19
        elif method == 'session.status' and debug.native_frame:
            result.update(state=status_state, state_revision=status_revision)
        return result
    debug.call = native_contract
    if accepted:
        result = debug.timeline_advance()
        assert result['completed_frames'] == 1
        assert result['frames'][0]['native_frame']['state'] == 'stopped'
        assert result['frames'][0]['native_frame']['boundary_verified_by']
    else:
        with pytest.raises(ValueError, match='readback'):
            debug.timeline_advance()
        assert debug.closed and debug.captures == 1


@pytest.mark.parametrize('operation', ['frame-inputs', 'timeline-advance'])
def test_known_fifo_capacity_refusal_keeps_future_and_session(debug, operation):
    start(debug)
    debug.timeline_advance(3)
    debug.timeline_rewind(2)
    debug.edge_capacity = 0
    before = debug.timeline_status()
    calls = len(debug.calls)
    with pytest.raises(ValueError, match='FIFO'):
        if operation == 'frame-inputs':
            debug.frame_inputs([{'key': 'a', 'pressed': True}])
        else:
            debug.timeline_advance(inputs=[{'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]}])
    assert debug.timeline_status() == before
    assert 'input.keyboard.frame_edges' not in debug.calls[calls:]
    assert 'frame.step' not in debug.calls[calls:]
    assert debug.cpu == 1 and not debug.keys and not debug.closed


def test_later_input_batch_capacity_is_checked_before_its_cache_transition(debug):
    start(debug)
    original = debug.call
    def fill_fifo_after_first_frame(method, params=None):
        result = original(method, params)
        if method == 'frame.step':
            debug.edge_capacity = 0
        return result
    debug.call = fill_fifo_after_first_frame
    with pytest.raises(ValueError, match='FIFO'):
        debug.timeline_advance(2, inputs=[{'frame': 1, 'edges': [{'key': 'a', 'pressed': True}]}])
    status = debug.timeline_status()
    assert status['valid'] and status['current_cached'] and status['cursor'] == 1
    assert status['captures_used'] == 2 and debug.cpu == 1 and not debug.keys
    assert debug.calls.count('frame.step') == 1 and 'input.keyboard.frame_edges' not in debug.calls
    assert not debug.closed


def test_32_edge_batch_boundary_and_missing_capacity_refusal(debug):
    edges = [{'key': key, 'pressed': True} for key in 'abcdefghijklmnopqrstuvwxyz012345']
    validate_edges(edges)
    with pytest.raises(ValueError, match='32'):
        validate_edges(edges + [{'key': '6', 'pressed': True}])
    debug.edge_capacity = None
    with pytest.raises(ValueError, match='capacity'):
        debug.frame_inputs(edges)
    assert not debug.keys and not debug.closed
    debug.edge_capacity = 32
    debug.frame_inputs(edges)
    assert len(debug.keys) == 32
