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
        {'op': 'timeline-start', 'max_frames': 32},
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
