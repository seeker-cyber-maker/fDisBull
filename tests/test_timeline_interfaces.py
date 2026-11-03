"""Public discovery and whole-route validation before native side effects."""
import pytest
import threading
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.wine_debugger import PEDebugSession
from fdisbull.debug_timeline import FrameTimelineSessionMixin, timeline_locked
from fdisbull.debugger import DebugSession
from fdisbull import dosbox_rpc


ALIASES = ('frame-advance', 'frame-inputs', 'timeline-start', 'timeline-status',
           'timeline-advance', 'timeline-rewind', 'timeline-stop', 'timeline-pin', 'timeline-image')


def test_timeline_methods_are_discoverable_but_require_owned_live_context():
    for name in ALIASES:
        assert 'debug-'+name in METHODS
        assert not respond({'method': 'debug-'+name, 'params': {'run': 'not-owned'}})['ok']
        assert name not in PEDebugSession.script_operations


@pytest.mark.parametrize('backend', ['wine-qemu', 'ida-wine-qemu', 'dosbox-qemu'])
def test_borrowed_operations_remain_reentrant_under_the_existing_backend_lock(backend):
    stable = threading.RLock()
    session = SimpleNamespace(metadata={'backend': backend}, rpc=SimpleNamespace(vm=object(), lock=stable))
    if backend != 'dosbox-qemu':
        session._delta_lock = stable
    @timeline_locked
    def borrowed_script_scope(self):
        assert FrameTimelineSessionMixin._timeline_gate(self) is stable
        with self.rpc.lock:
            return 'owned'
    with stable:
        assert borrowed_script_scope(session) == 'owned'
    assert not hasattr(session, '_timeline_lock')


def test_frame_script_accepts_explicit_edges_points_and_preservation_policy():
    steps = validate_script({'format': 'fdisbull-script-1', 'steps': [
        {'op': 'frame-advance', 'frames': 1},
        {'op': 'timeline-start', 'max_frames': 32, 'storage_mode': 'delta', 'keyframe_interval': 8},
        {'op': 'timeline-advance', 'frames': 4, 'inputs': [
            {'frame': 0, 'edges': [{'key': 'kp5', 'pressed': True}]},
            {'frame': 1, 'edges': [{'key': 'kp5', 'pressed': False}]}]},
        {'op': 'timeline-rewind', 'frames': 2, 'policy': {
            'name': 'preserve-rng', 'preserve_memory': [{'address': '0x1a607', 'length': 2}],
            'allow_partial_resume': True}},
        {'op': 'timeline-advance', 'frames': 1},
        {'op': 'timeline-pin', 'name': 'branch.sav'},
    ]})
    assert len(steps) == 6


class NoSideEffects:
    def _artifact(self, *args, **kwargs):
        pytest.fail('Malformed later operations must reject before creating route artifacts')


@pytest.mark.parametrize('step', [
    {'op': 'frame-advance', 'frames': True},
    {'op': 'frame-advance', 'frames': 129},
    {'op': 'timeline-start', 'max_frames': 0},
    {'op': 'timeline-start', 'max_captures': 65537},
    {'op': 'timeline-start', 'max_bytes': 1},
    {'op': 'timeline-start', 'storage_mode': 'invalid'},
    {'op': 'timeline-start', 'keyframe_interval': 0},
    {'op': 'timeline-start', 'keyframe_interval': 129},
    {'op': 'timeline-start', 'keyframe_interval': True},
    {'op': 'timeline-pin', 'name': '../escape.sav'},
    {'op': 'timeline-image', 'name': ''},
    {'op': 'frame-inputs', 'edges': [{'key': 'a', 'pressed': 1}]},
    {'op': 'frame-inputs', 'edges': [{'key': 'esc', 'pressed': True}, {'key': 'escape', 'pressed': False}]},
    {'op': 'timeline-advance', 'frames': 2, 'inputs': [{'frame': 2, 'edges': []}]},
    {'op': 'timeline-advance', 'frames': '$count', 'inputs': [{'frame': 128, 'edges': []}]},
    {'op': 'timeline-rewind', 'policy': {'preserve_memory': [{'address': '0xa0000', 'length': 2}]}},
    {'op': 'timeline-rewind', 'policy': {'preserve_memory': '$rng', 'allow_partial_resume': 'yes'}},
])
def test_bad_later_frame_operation_rejects_before_earlier_execution(step):
    with pytest.raises(ValueError):
        execute_script(NoSideEffects(), {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'run', 'guest_ms': 1}, step]})


class LegacyScriptSession(FrameTimelineSessionMixin):
    def __init__(self):
        self.run_id = 'legacy'
        self.rpc = SimpleNamespace(capabilities={})
        self.metadata = {}
        self.closed = False
        self.artifacts, self.mutations = [], []

    def _artifact(self, name, kind, data, metadata):
        self.artifacts.append(kind)
        return {'artifact': 'stored', 'metadata': metadata}

    def run(self, **kwargs):
        self.mutations.append(kwargs)
        return {'outcome': 'guest_time'}


@pytest.mark.parametrize('step', [
    {'op': 'frame-advance'}, {'op': 'frame-inputs', 'edges': []},
    {'op': 'timeline-start'}, {'op': 'timeline-advance'}, {'op': 'timeline-rewind'},
    {'op': 'timeline-pin'}, {'op': 'timeline-image'},
])
def test_missing_frame_capability_rejects_entire_route_before_earlier_side_effects(step):
    session = LegacyScriptSession()
    with pytest.raises(ValueError, match='frame_timeline capability'):
        execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'run', 'guest_ms': 1}, step]})
    assert session.mutations == [] and session.artifacts == []


def test_legacy_scripts_and_local_timeline_status_cleanup_need_no_frame_capability():
    session = LegacyScriptSession()
    del session.rpc.capabilities
    result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
        {'op': 'run', 'guest_ms': 1}, {'op': 'timeline-status'}, {'op': 'timeline-stop'}]})
    assert result['ok'] and len(session.mutations) == 1
    assert session.timeline_status()['retained_points'] == 0


@pytest.mark.parametrize('recording,step', [
    (False, {'op': 'frame-inputs', 'edges': [{'key': 'right', 'pressed': True}]}),
    (True, {'op': 'frame-inputs', 'edges': [{'key': 'right', 'pressed': True}]}),
    (True, {'op': 'timeline-advance', 'inputs': [
        {'frame': 0, 'edges': [{'key': 'right', 'pressed': True}]}]}),
])
def test_failed_frame_route_closes_after_physical_input(recording, step):
    from test_debug_timeline import Session, start
    session = Session()
    try:
        if recording:
            start(session)
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            step, {'op': 'assert', 'value': False, 'equals': True}]})
        assert not result['ok'] and result['completed_steps'] == 1
        assert session.keys == {'right'}  # Accepted once; cleanup never replays input.
        assert session.calls.count('input.keyboard.frame_edges') == 1
        assert session.closed
        assert result['input_cleanup']['closed']
    finally:
        session.db.close()


@pytest.mark.parametrize('step', [
    {'op': 'frame-inputs', 'edges': []},
    {'op': 'timeline-advance'},
    {'op': 'timeline-advance', 'inputs': [{'frame': 0, 'edges': []}]},
])
def test_failed_frame_route_without_input_preserves_session(step):
    from test_debug_timeline import Session, start
    session = Session()
    try:
        start(session)
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            step, {'op': 'assert', 'value': False, 'equals': True}]})
        assert not result['ok'] and result['completed_steps'] == 1
        assert not session.keys and not session.closed
        assert result['input_cleanup'] is None
        assert session.timeline_status()['valid']
    finally:
        session.db.close()


def frame_restore_session(operation, initial_keys, restored_keys):
    from fdisbull.anchor_stones import AnchorStoneSessionMixin
    from test_debug_timeline import Session, start
    session = Session()
    session.keys = set(restored_keys)
    start(session)
    checkpoint = session._frame_timeline['points'][0]['checkpoint']
    session.timeline_advance()
    edges = [dict(key=key, pressed=False) for key in set(restored_keys) - set(initial_keys)]
    edges += [dict(key=key, pressed=True) for key in set(initial_keys) - set(restored_keys)]
    if edges:
        session.frame_inputs(edges)
    if operation == 'timeline-rewind':
        step = {'op': operation, 'frames': 1}
    else:
        session.load_state = lambda artifact: session._restore_native_checkpoint(checkpoint)
        session.load_anchor_stone = lambda artifact: AnchorStoneSessionMixin.load_anchor_stone(session, artifact)
        step = {'op': operation, 'artifact': 'owned-test-checkpoint'}
    return session, step


@pytest.mark.parametrize('operation', ['timeline-rewind', 'load-state', 'load-anchor-stone'])
@pytest.mark.parametrize('initial_keys,restored_keys,should_close', [
    ([], ['right'], True),
    (['right'], ['right'], False),
    (['right', 'left'], ['right'], False),
    ([], [], False),
])
def test_failed_restore_route_cleans_only_newly_held_frame_keys(operation, initial_keys, restored_keys, should_close):
    session, step = frame_restore_session(operation, initial_keys, restored_keys)
    try:
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            step, {'op': 'assert', 'value': False, 'equals': True}]})
        assert not result['ok'] and result['completed_steps'] == 1
        assert session.restores == 1 and session.keys == set(restored_keys)
        assert session.closed is should_close
        assert bool(result['input_cleanup']) is should_close
    finally:
        session.db.close()


@pytest.mark.parametrize('unavailable', ['exception', 'missing-ownership'])
def test_failed_restore_route_with_unknown_frame_ownership_closes(unavailable):
    session, step = frame_restore_session('load-state', [], [])
    original = session.call
    def lose_ownership_after_restore(method, params=None):
        if method == 'input.keyboard.state' and session.restores:
            if unavailable == 'exception':
                raise TimeoutError('restored ownership reply unavailable')
            return {'keyboard': {}}
        return original(method, params)
    session.call = lose_ownership_after_restore
    try:
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            step, {'op': 'assert', 'value': False, 'equals': True}]})
        assert not result['ok'] and result['completed_steps'] == 1
        assert session.restores == 1 and session.closed
        assert result['input_cleanup']['closed']
    finally:
        session.db.close()


def test_restore_error_after_mutation_still_cleans_new_frame_ownership():
    session, step = frame_restore_session('load-state', [], ['right'])
    original = session.load_state
    def restore_then_lose_receipt(artifact):
        original(artifact)
        raise ValueError('restore receipt unavailable')
    session.load_state = restore_then_lose_receipt
    try:
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [step]})
        assert not result['ok'] and result['completed_steps'] == 0
        assert result['error']['message'] == 'restore receipt unavailable'
        assert session.restores == 1 and session.keys == {'right'} and session.closed
        assert result['input_cleanup']['closed']
    finally:
        session.db.close()


def test_restore_refusal_with_preexisting_frame_keys_keeps_session_open():
    session, _ = frame_restore_session('timeline-rewind', ['right'], ['right'])
    try:
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'timeline-rewind', 'frames': 4096}]})
        assert not result['ok'] and result['completed_steps'] == 0
        assert session.restores == 0 and session.keys == {'right'}
        assert not session.closed and result['input_cleanup'] is None
    finally:
        session.db.close()


@pytest.mark.parametrize('operation', ['load-anchor-stone', 'delta-recover'])
@pytest.mark.parametrize('later_failure,restored_keys,should_close', [
    (False, ['right'], False),
    (True, [], False),
    (True, ['right'], True),
])
def test_frozen_delta_recovery_script_preserves_unknown_entry_ownership(
        operation, later_failure, restored_keys, should_close):
    session, step = frame_restore_session('load-anchor-stone', [], restored_keys)
    session._cpu_delta_history = {'frozen': True}
    original_call, original_load = session.call, session.load_state
    refused_queries = []
    def guarded_call(method, params=None):
        if method == 'input.keyboard.state' and session._cpu_delta_history['frozen']:
            refused_queries.append(method)
            raise ValueError('CPU delta partial state is frozen; load a full native checkpoint before execution or capture')
        return original_call(method, params)
    def recover(artifact=None):
        result = original_load(artifact)
        session._cpu_delta_history['frozen'] = False
        return result
    session.call, session.load_state = guarded_call, recover
    session.cpu_delta_recover = recover
    if operation == 'delta-recover':
        step = {'op': operation}
    steps = [step]
    if later_failure:
        steps.append({'op': 'assert', 'value': False, 'equals': True})
    try:
        result = execute_script(session, {'format': 'fdisbull-script-1', 'steps': steps})
        assert result['ok'] is not later_failure
        assert refused_queries == ['input.keyboard.state']
        assert session.restores == 1 and not session._cpu_delta_history['frozen']
        assert session.keys == set(restored_keys) and session.closed is should_close
        assert bool(result['input_cleanup']) is should_close
    finally:
        session.db.close()


def test_unavailable_entry_frame_ownership_refuses_before_restore():
    session, step = frame_restore_session('load-state', [], [])
    original = session.call
    session.call = lambda method, params=None: ({'keyboard': {}} if method == 'input.keyboard.state'
                                               else original(method, params))
    try:
        with pytest.raises(ValueError, match='ownership is unavailable'):
            execute_script(session, {'format': 'fdisbull-script-1', 'steps': [step]})
        assert session.restores == 0 and not session.closed and not session.artifacts
    finally:
        session.db.close()


@pytest.mark.parametrize('process_status', [None, 0, 'unknown'])
@pytest.mark.parametrize('receipt_fails', [False, True])
def test_failed_transport_cleanup_releases_cache_and_terminal_ownership(process_status, receipt_fails):
    session = SimpleNamespace(closed=False, run_id='owned', _frame_timeline={'points': [b'private state']},
        _keyboard_leases={'lease': 'enter'}, _launch_alias=None, _timeline_lock=threading.RLock())
    events, updates, bindings = [], [], []
    def close_rpc():
        assert session._timeline_lock._is_owned()
        raise RuntimeError('native cleanup failed')
    def poll():
        if process_status == 'unknown':
            raise OSError('process status unavailable')
        return process_status
    session.rpc = SimpleNamespace(close=close_rpc, process=SimpleNamespace(poll=poll))
    session.call = lambda method, params=None: {'operation_id': 'stop'} if method == 'session.stop' else {'running': False}
    session._invalidate_runtime_bindings = lambda: bindings.append('invalidated')
    def event(operation, result):
        events.append((operation, dict(result)))
        if receipt_fails:
            raise ValueError('receipt unavailable')
    session._event = event
    session.project = SimpleNamespace(transaction=lambda write: nullcontext(),
        db=SimpleNamespace(execute=lambda *args: updates.append(args)), _live_debuggers=[session])
    # Failure-triggered close must be reentrant inside an already-owned action.
    with session._timeline_lock:
        with pytest.raises(RuntimeError, match='native cleanup failed'):
            DebugSession.close(session)
    assert session.closed and session._frame_timeline is None and session._keyboard_leases == {}
    assert bindings == ['invalidated'] and updates
    assert session.project._live_debuggers == []
    receipt = events[0][1]
    assert receipt['cleanup_errors'][0]['phase'] == 'rpc.close'
    assert receipt['process_reaped'] is (None if process_status == 'unknown' else process_status is not None)


@pytest.mark.parametrize('unreapable', [False, True])
def test_pipe_cleanup_error_still_attempts_both_descriptors_process_and_temporary_cleanup(monkeypatch, unreapable):
    calls = []
    class Process:
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            calls.append('terminate')
        def wait(self, timeout):
            calls.append('wait')
            if unreapable:
                raise subprocess.TimeoutExpired('authored-process', timeout)
            self.returncode = 0
            return 0
        def kill(self):
            calls.append('kill')
    rpc = object.__new__(dosbox_rpc.DOSBoxRPC)
    rpc.reader, rpc.writer, rpc.process = 11, 12, Process()
    rpc.temporary = SimpleNamespace(cleanup=lambda: calls.append('temporary'))
    def close_pipe(fd):
        calls.append(fd)
        if fd == 11:
            raise OSError('authored pipe cleanup failure')
    # Replace this module's os binding, without affecting pytest's own descriptors.
    monkeypatch.setattr(dosbox_rpc, 'os', SimpleNamespace(close=close_pipe))
    with pytest.raises(OSError, match='authored pipe cleanup failure'):
        rpc.close()
    assert calls[:2] == [11, 12]
    assert 'terminate' in calls and 'wait' in calls and calls[-1] == 'temporary'
    assert ('kill' in calls) is unreapable
    assert (rpc.process.poll() is None) is unreapable
    assert rpc.reader is None and rpc.writer is None and rpc.temporary is None
