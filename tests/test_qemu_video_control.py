"""Host ownership and first-stop boundaries at the production QMP envelope.

The peer is deliberately hostile protocol input, not a raster/phase oracle.
Native raster, timing, keyboard and GDB-packet evidence has a separate authored
fixture. These cases never import or launch a native executable.
"""
from copy import deepcopy
import json
from threading import RLock
from types import MethodType, SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_hooks import QemuHookSessionMixin
from fdisbull.qemu_machine import MachineContext, MachineDebugSession
from fdisbull.qemu_video_control import VIDEO_FRAME_CONTROL_COMMANDS
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_video_frame import VideoWire, video


def stopped(kind='stopped', *, reply='T02', hits=None):
    ids = [17] if kind in ('breakpoint', 'watchpoint') else []
    return dict(context='machine', outcome=kind, timed_out=False,
        session=dict(state='stopped', stop_reason=dict(kind=kind, address='0x7c20',
            breakpoint_ids=ids, native_reply=reply)), breakpoints=ids,
        registers=dict(linear_pc='0x7c20', registers={'eip': '0x7c20'}),
        hook_hits=[] if hits is None else hits)


class FenceWire(VideoWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.fence = None
        self.changes = {name: lambda value: value for name in ('arm', 'query', 'cancel')}
        self.before_control = lambda command, args: None
        self.after_control = lambda command: None

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in VIDEO_FRAME_CONTROL_COMMANDS:
            return super().sendall(data)
        self.before_control(command, args)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-arm-video-frame':
            assert args['stream-token'] == self.video['token']
            assert args['expected-stream-generation'] == self.video['stream-generation']
            assert args['expected-frame-sequence'] == self.video['frame-sequence']
            assert args['expected-epoch'] == self.receipt['epoch']
            self.fence = {'api-version': 1, 'model': 'qemu-video-frame-fence-v1',
                'token': args['token'], 'stream-token': self.video['token'],
                'stream-generation': self.video['stream-generation'], 'epoch': 1,
                'configuration-generation': 7, 'timing-generation': 4,
                'baseline-frame-sequence': self.video['frame-sequence'],
                'baseline-rows-sampled': self.video['rows-sampled'],
                'armed-ns': self.receipt['virtual-ns'], 'state': 'armed',
                'released': False, 'stop-pending': False, 'stop-consumed': False}
            phase = 'arm'
        elif command == 'x-fdisbull-query-video-frame-fence':
            assert args == {'token': self.fence['token']}
            phase = 'query'
        else:
            assert args == {'token': self.fence['token']}
            if self.fence['state'] == 'armed':
                self.fence['state'] = 'cancelled'
            self.fence['released'] = True
            phase = 'cancel'
        value = self.changes[phase](deepcopy(self.fence))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency
        self.after_control(command)

    def accept(self, *, consumed=True):
        self.publish()
        self.fence.update(state='completed', **{'completed-frame': deepcopy(self.video['frame']),
            'stop-consumed': consumed, 'stop-ns': self.receipt['virtual-ns']})

    def abort(self, *, consumed=True):
        self.receipt['virtual-ns'] += 16
        self.video.update(state='invalidated', reason='configuration-changed',
                          **{'in-progress': False, 'rows-sampled': 0})
        for key in ('frame', 'next-deadline-ns'):
            self.video.pop(key, None)
        self.fence.update(state='aborted', reason='configuration-changed',
            **{'stop-consumed': consumed, 'stop-ns': self.receipt['virtual-ns']})


@pytest.fixture
def control(video):
    o = video
    o.wire = FenceWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= VIDEO_FRAME_CONTROL_COMMANDS
    o.executions = []
    o.actual = stopped()
    o.dispatch = lambda: o.wire.accept()

    def execute(*, timeout_ms, stop_on_hook):
        o.executions.append(dict(timeout_ms=timeout_ms, stop_on_hook=stop_on_hook))
        o.dispatch()
        return deepcopy(o.actual)

    o.session._run_with_hooks = execute
    return o


def commands(o, name):
    return [args for command, args in o.wire.calls if command == name]


def intent_count(o):
    return o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation="
                               "'machine-video-frame-advance-intent'").fetchone()[0]


def test_exact_target_and_actual_stop_are_separate_and_intent_precedes_arm(control):
    o = control
    o.session.video_frame_start()
    o.wire.before_control = lambda command, args: (
        None if command != 'x-fdisbull-arm-video-frame' or intent_count(o) == 1
        else pytest.fail('Native arm preceded durable intent'))
    result = o.session.video_frame_advance()
    assert result['format'] == 'fdisbull-video-frame-advance-1'
    assert result['advance_completed'] is True and result['completed_source_raster'] is True
    assert result['outcome'] == 'stopped' and result['native_result'] == o.actual
    assert result['baseline_frame_sequence'] == 0 and result['frame']['frame-id'] == 1
    assert result['source']['before'].get('frame') is None
    assert result['source']['after']['frame'] == result['frame']
    assert result['fence']['released'] == dict(result['fence']['observed'], released=True)
    assert result['fence']['released']['stop-pending'] is False
    assert result['stop_consumed'] is True and len(o.executions) == 1
    assert result['legacy_phase_equivalence'] is result['application_frame_complete'] is None
    assert result['frame_state_equivalence'] is None
    assert o.vm._active_video_frame_fence is None and o.session._video_frame_fence_context is None
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    assert o.session.capabilities['completed_guest_frames'] is False
    result['frame']['rows'][0]['actual-ns'] = 0
    assert o.wire.fence['completed-frame']['rows'][0]['actual-ns'] > 0


def test_unchanged_pixels_still_advance_exactly_one_source_ordinal(control):
    o = control
    o.session.video_frame_start()
    first = o.session.video_frame_advance()
    second = o.session.video_frame_advance()
    assert second['baseline_frame_sequence'] == first['frame']['frame-id'] == 1
    assert second['frame']['frame-id'] == 2 and second['advance_completed']
    assert first['frame']['pixel-sha256'] == second['frame']['pixel-sha256']
    assert first['fence']['arm']['token'] != second['fence']['arm']['token']
    assert len(o.executions) == 2 and intent_count(o) == 2


def test_incomplete_advance_never_reuses_the_previously_retained_frame(control):
    o = control
    o.session.video_frame_start()
    o.wire.publish()
    old = o.session.video_frame_observe()['frame']
    o.dispatch = lambda: None
    o.actual = stopped('breakpoint', reply='T05')
    result = o.session.video_frame_advance()
    assert result['outcome'] == 'breakpoint' and result['native_result'] == o.actual
    assert not result['advance_completed'] and not result['completed_source_raster']
    assert result['frame'] is None and result['source']['after']['frame'] == old
    assert result['fence']['released']['state'] == 'cancelled'
    assert 'stop-ns' not in result['fence']['released']
    assert not o.vm.closed and len(o.executions) == 1


@pytest.mark.parametrize('kind,reply', [('breakpoint', 'T05'), ('watchpoint', 'T05watch:30000;'),
                                       ('step', 'T05'), ('exception', 'T06')])
def test_accepted_raster_cannot_hide_a_different_actual_stop(control, kind, reply):
    o = control
    o.session.video_frame_start()
    o.dispatch = lambda: o.wire.accept(consumed=False)
    o.actual = stopped(kind, reply=reply)
    result = o.session.video_frame_advance()
    assert result['completed_source_raster'] and result['frame']['frame-id'] == 1
    assert not result['advance_completed'] and result['stop_consumed'] is False
    assert result['outcome'] == kind and result['native_result'] == o.actual
    assert not o.vm.closed and len(o.executions) == 1


@pytest.mark.parametrize('change', [
    lambda r: r.update(timed_out=True, outcome='timeout'),
    lambda r: r['session']['stop_reason'].update(classification_complete=False),
    lambda r: r.update(layer_conflict={'fault': 'authored'}),
    lambda r: r.update(save_boundary_conflict=True),
    lambda r: r['session']['stop_reason'].update(native_reply='T05'),
    lambda r: r.update(guest_tsr={'state': 'resident'}),
])
def test_receipt_stop_consumed_does_not_override_actual_stop_classification(control, change):
    o = control
    o.session.video_frame_start()
    change(o.actual)
    result = o.session.video_frame_advance()
    assert result['completed_source_raster'] and result['stop_consumed']
    assert not result['advance_completed'] and result['native_result'] == o.actual


@pytest.mark.parametrize('stop_on_hook', [False, True])
def test_prior_hook_history_is_preserved_under_the_requested_stop_policy(control, stop_on_hook):
    o = control
    o.session.video_frame_start()
    o.actual = stopped(hits=[{'hook': 'earlier', 'stop': {'native_reply': 'T05'}}])
    result = o.session.video_frame_advance(stop_on_hook=stop_on_hook)
    assert result['advance_completed'] is (not stop_on_hook)
    assert result['native_result'] == o.actual
    assert o.executions[0]['stop_on_hook'] is stop_on_hook


def test_known_source_abort_releases_control_and_allows_an_explicit_new_stream(control):
    o = control
    o.session.video_frame_start()
    o.dispatch = lambda: o.wire.abort()
    result = o.session.video_frame_advance()
    assert not result['advance_completed'] and not result['completed_source_raster']
    assert result['frame'] is None and result['source']['after']['state'] == 'invalidated'
    assert result['fence']['released']['state'] == 'aborted' and result['stop_consumed']
    assert not o.vm.closed and o.vm._active_video_frame_fence is None
    next_stream = o.session.video_frame_start()
    assert next_stream['stream_generation'] == 2
    o.dispatch = lambda: o.wire.accept()
    assert o.session.video_frame_advance()['advance_completed']


def test_proven_original_owner_exit_retains_native_result_with_unknown_post_exit_evidence(control):
    o = control
    o.session.video_frame_start()
    o.vm.process = SimpleNamespace(poll=lambda: 0 if o.vm.closed else None)
    o.dispatch = lambda: None
    o.actual = dict(outcome='exited', timed_out=False, session=dict(state='exited',
        stop_reason=dict(kind='exited', native_reply='W00', breakpoint_ids=[])), registers=None)
    result = o.session.video_frame_advance()
    assert result['outcome'] == 'exited' and result['native_result'] == o.actual
    assert result['owner_exited'] and result['advance_completed'] is False
    assert result['completed_source_raster'] is result['stop_consumed'] is result['frame'] is None
    assert result['source']['after'] is result['clocks']['after'] is None
    assert result['fence']['observed'] is result['fence']['released'] is None
    assert result['owner']['run'] == o.session.run_id and result['owner']['stream'] == result['stream']
    assert not commands(o, 'x-fdisbull-query-video-frame-fence')
    assert not commands(o, 'x-fdisbull-cancel-video-frame-fence') and o.vm.closed


def test_claimed_machine_exit_with_a_live_owner_cannot_use_the_exit_shortcut(control):
    o = control
    o.session.video_frame_start()
    o.vm.process = SimpleNamespace(poll=lambda: None)
    original_close, closes = o.vm.close, []
    o.vm.close = lambda: closes.append(True)
    o.dispatch = lambda: None
    o.actual = dict(outcome='exited', timed_out=False, session=dict(state='exited',
        stop_reason=dict(kind='exited', native_reply='W00', breakpoint_ids=[])), registers=None)
    try:
        with pytest.raises(DebuggerError, match='reaped original') as caught:
            o.session.video_frame_advance()
        assert len(closes) == 2
        assert caught.value.video_frame_advance_evidence['native_result'] == o.actual
        assert caught.value.video_frame_advance_evidence['owner']['run'] == o.session.run_id
        assert not commands(o, 'x-fdisbull-query-video-frame-fence')
    finally:
        o.vm.close = original_close


@pytest.mark.parametrize('kind,closed', [('guest_exit', False), ('guest_tsr', False),
                                      ('guest_exit', True), ('guest_tsr', True)])
def test_dos_exit_or_residency_uses_closed_owner_shortcut_only_after_reaping(control, kind, closed):
    o = control
    o.session.video_frame_start()
    o.vm.process = SimpleNamespace(poll=lambda: 0 if o.vm.closed else None)
    o.actual = stopped()
    o.actual['native_machine_stop'] = deepcopy(o.actual['session']['stop_reason'])
    o.actual['outcome'] = kind
    o.actual['process'] = dict(state='resident' if kind == 'guest_tsr' else 'exited',
                               termination={'category': 'authored'}, machine_closed=closed)
    o.actual['session']['stop_reason'] = dict(kind=kind, breakpoint_ids=[])
    o.dispatch = o.vm.close if closed else lambda: None
    result = o.session.video_frame_advance()
    assert result['outcome'] == kind and result['native_result'] == o.actual
    assert result['advance_completed'] is False
    if closed:
        assert result['owner_exited'] and result['source']['after'] is None
        assert result['completed_source_raster'] is None
        assert not commands(o, 'x-fdisbull-query-video-frame-fence')
    else:
        assert not o.vm.closed and result['source']['after']['state'] == 'observing'
        assert result['fence']['released']['state'] == 'cancelled'
        assert result['completed_source_raster'] is False


def test_partial_rows_are_not_restarted_and_may_precede_arm(control):
    o = control
    o.session.video_frame_start()
    # Literal peer schedule: H=32, first row=32008, row 100=38408.
    o.wire.video.update(**{'in-progress': True, 'rows-sampled': 100,
                           'next-deadline-ns': 38408})
    o.wire.receipt['virtual-ns'] = 38380

    def finish_partial():
        o.wire.receipt['virtual-ns'] = 1000
        o.wire.accept()
        o.wire.video.update(**{'in-progress': False, 'rows-sampled': 0})

    o.dispatch = finish_partial
    result = o.session.video_frame_advance()
    assert result['advance_completed'] and result['fence']['arm']['baseline-rows-sampled'] == 100
    assert result['frame']['first-sample-ns'] < result['fence']['arm']['armed-ns']
    assert result['frame']['completed-ns'] >= result['fence']['arm']['armed-ns']


@pytest.mark.parametrize('kwargs', [{'timeout_ms': True}, {'timeout_ms': 0},
    {'timeout_ms': 600001}, {'stop_on_hook': 1}, {'frames': 2}, {'inputs': []}])
def test_invalid_or_combined_arguments_refuse_before_native_io(control, kwargs):
    o = control
    before = list(o.wire.calls)
    with pytest.raises((TypeError, ValueError)):
        o.session.video_frame_advance(**kwargs)
    assert o.wire.calls == before and not o.executions and intent_count(o) == 0


def test_missing_observing_stream_is_not_implicitly_started(control):
    o = control
    with pytest.raises(ValueError, match='explicitly started'):
        o.session.video_frame_advance()
    assert not commands(o, 'x-fdisbull-start-video-frame')
    assert not commands(o, 'x-fdisbull-arm-video-frame') and not o.executions
    assert intent_count(o) == 0 and not o.vm.closed


@pytest.mark.parametrize('fields', [
    {'api-version': True}, {'model': 'renderer'}, {'token': 'foreign'},
    {'stream-token': 'foreign'}, {'stream-generation': 2}, {'epoch': 2},
    {'configuration-generation': 0}, {'baseline-frame-sequence': 1},
    {'baseline-rows-sampled': True}, {'armed-ns': 1001},
    {'released': True}, {'stop-pending': True}, {'stop-consumed': True},
    {'stop-ns': 1000}, {'extra': 0},
])
def test_hostile_arm_receipt_closes_without_execution(control, fields):
    o = control
    o.session.video_frame_start()
    o.wire.changes['arm'] = lambda value: dict(value, **fields)
    with pytest.raises(DebuggerError) as caught:
        o.session.video_frame_advance()
    assert o.vm.closed and not o.executions and intent_count(o) == 1
    assert caught.value.video_frame_advance_evidence['fence']['received'] is not None


@pytest.mark.parametrize('change', [
    lambda r: r.update(**{'stop-pending': True}),
    lambda r: r.update(released=True),
    lambda r: r.update(**{'stop-ns': r['armed-ns']}),
    lambda r: r.pop('completed-frame'),
    lambda r: r['completed-frame'].update(**{'frame-id': 2}),
    lambda r: r['completed-frame'].update(**{'configuration-generation': 8}),
    lambda r: r['completed-frame']['rows'].pop(),
])
def test_unverified_terminal_receipt_never_becomes_success(control, change):
    o = control
    o.session.video_frame_start()
    def corrupt(value):
        change(value)
        return value
    o.wire.changes['query'] = corrupt
    with pytest.raises(DebuggerError) as caught:
        o.session.video_frame_advance()
    assert o.vm.closed and len(o.executions) == 1
    assert caught.value.video_frame_advance_evidence['native_result'] == o.actual
    assert not commands(o, 'x-fdisbull-cancel-video-frame-fence')


@pytest.mark.parametrize('change', [
    lambda r: r.update(released=False),
    lambda r: r.update(state='cancelled'),
    lambda r: r.update(**{'stop-consumed': False}),
    lambda r: r['completed-frame'].update(**{'pixel-sha256': '1' * 64}),
])
def test_release_cannot_edit_the_frozen_completion(control, change):
    o = control
    o.session.video_frame_start()
    def corrupt(value):
        change(value)
        return value
    o.wire.changes['cancel'] = corrupt
    with pytest.raises(DebuggerError) as caught:
        o.session.video_frame_advance()
    assert o.vm.closed and len(o.executions) == 1
    assert len(commands(o, 'x-fdisbull-cancel-video-frame-fence')) == 1
    assert caught.value.video_frame_advance_evidence['fence']['observed']['state'] == 'completed'


def test_fence_and_current_source_must_name_identical_pixels(control):
    o = control
    o.session.video_frame_start()
    def execute():
        o.wire.accept()
        o.wire.video['frame']['pixel-sha256'] = '2' * 64
    o.dispatch = execute
    with pytest.raises(DebuggerError, match='retained raster'):
        o.session.video_frame_advance()
    assert o.vm.closed and len(o.executions) == 1


def test_arm_must_preserve_partial_source_progress(control):
    o = control
    o.session.video_frame_start()
    o.wire.after_control = lambda command: (o.wire.video.update(**{'next-deadline-ns': 99999})
        if command == 'x-fdisbull-arm-video-frame' else None)
    with pytest.raises(DebuggerError, match='changed the stopped stream'):
        o.session.video_frame_advance()
    assert o.vm.closed and not o.executions


@pytest.mark.parametrize('phase', ['intent', 'publication'])
def test_persistence_failure_retains_received_evidence_and_never_replays(control, phase):
    o = control
    o.session.video_frame_start()
    event = o.session._event
    operation = 'machine-video-frame-advance' + ('-intent' if phase == 'intent' else '')
    def fail(name, result):
        if name == operation:
            raise OSError('authored persistence failure')
        event(name, result)
    o.session._event = fail
    with pytest.raises(OSError) as caught:
        o.session.video_frame_advance()
    assert o.vm.closed and len(o.executions) == (0 if phase == 'intent' else 1)
    evidence = caught.value.video_frame_advance_evidence
    assert evidence['stage'] == phase
    if phase == 'publication':
        assert evidence['native_result'] == o.actual
        assert evidence['result']['frame']['frame-id'] == 1
        assert evidence['fence']['released']['released']
    else:
        assert not commands(o, 'x-fdisbull-arm-video-frame')


def test_one_inherited_deadline_reaches_wire_and_cannot_publish_a_late_result(control):
    o = control
    o.session.video_frame_start()
    o.session._rpc_deadline = o.clock.now + .05
    o.wire.budgets.clear()
    def late():
        o.wire.accept()
        o.clock.advance(.051)
    o.dispatch = late
    with pytest.raises(TimeoutError) as caught:
        o.session.video_frame_advance(timeout_ms=5000)
    assert o.vm.closed and len(o.executions) == 1
    assert max(o.wire.budgets) <= .05 + 1e-9
    assert o.executions[0]['timeout_ms'] <= 50
    assert caught.value.video_frame_advance_evidence['native_result'] == o.actual
    assert not commands(o, 'x-fdisbull-cancel-video-frame-fence')


def test_owner_replacement_after_execution_closes_only_the_original(control):
    o = control
    o.session.video_frame_start()
    replacement = SimpleNamespace(closed=False)
    replacement.close = lambda: setattr(replacement, 'closed', True)
    def replace():
        o.wire.accept()
        o.session.vm = replacement
    o.dispatch = replace
    try:
        with pytest.raises(DebuggerError, match='owner changed') as caught:
            o.session.video_frame_advance()
        assert o.vm.closed and not replacement.closed
        assert caught.value.video_frame_advance_evidence['native_result'] == o.actual
    finally:
        o.session.vm = o.vm


@pytest.mark.parametrize('controller', ['source', 'renderer', 'clock', 'sync', 'input', 'schedule', 'undo'])
def test_competing_owner_refuses_before_intent_arm_or_execution(control, controller):
    o = control
    o.session.video_frame_start()
    if controller == 'source':
        o.vm._active_video_frame_fence = {'kind': 'video-source', 'token': 'other'}
    elif controller == 'renderer':
        o.vm._active_frame_fence = 'renderer'
    elif controller == 'clock':
        o.vm._active_clock_budget = {'budget-state': 'armed'}
    elif controller == 'sync':
        o.vm._clock_sync = {'state': 'active'}
    elif controller in ('input', 'schedule'):
        state = o.session._input_storage()
        if controller == 'input':
            state['leases']['held'] = {'key': 'a'}
        else:
            state['schedule'] = {'bound': True}
    else:
        from fdisbull.qemu_cpu_undo_guard import before_operation
        o.session._qemu_cpu_delta_history = {'frozen': True}
        o.vm.history_operation_guard = lambda name, args, kwargs: before_operation(o.session, name, args, kwargs)
    with pytest.raises(ValueError):
        o.session.video_frame_advance()
    assert not commands(o, 'x-fdisbull-arm-video-frame') and not o.executions
    assert intent_count(o) == 0 and not o.vm.closed


@pytest.mark.parametrize('operation', ['clock', 'renderer', 'input', 'frame-keys', 'detach',
    'checkpoint', 'instrumented', 'machine-checkpoint', 'undo', 'source-start', 'source-stop', 'sync'])
def test_reverse_controller_admission_preserves_the_source_owner(operation):
    from fdisbull.qemu_clock import MachineClockMixin
    from fdisbull.qemu_clock_sync import QemuClockSyncMixin
    from fdisbull.qemu_dos_checkpoint import _preflight
    from fdisbull.qemu_dos_frames import QemuDOSFramesMixin
    from fdisbull.qemu_frame_keys import QemuFrameKeysMixin
    from fdisbull.qemu_input import QemuPhysicalInputMixin
    from fdisbull.qemu_instrumented_checkpoint import preflight
    from fdisbull.qemu_cpu_undo_runtime import _admission
    from fdisbull.qemu_video_frame import QemuVideoFrameMixin
    owner = {'kind': 'video-source', 'token': 'owned'}
    session = SimpleNamespace(vm=SimpleNamespace(lock=RLock(), _active_video_frame_fence=deepcopy(owner)))
    session._frame_keys_prepare = MethodType(QemuFrameKeysMixin._frame_keys_prepare, session)
    calls = {
        'clock': lambda: MachineClockMixin._clock_advance(session, 1, timeout_ms=5000, hook_aware=False),
        'renderer': lambda: QemuDOSFramesMixin._frame_execute(session, None, 'renderer'),
        'input': lambda: QemuPhysicalInputMixin._input_prepare(session),
        'frame-keys': lambda: QemuFrameKeysMixin.frame_inputs(session, []),
        'detach': lambda: QemuFrameKeysMixin._frame_keys_before_physical_input(session),
        'checkpoint': lambda: _preflight(session),
        'instrumented': lambda: preflight(session),
        'machine-checkpoint': lambda: MachineDebugSession._checkpoint_preflight(session),
        'undo': lambda: _admission(session),
        'source-start': lambda: QemuVideoFrameMixin.video_frame_start(session),
        'source-stop': lambda: QemuVideoFrameMixin.video_frame_stop(session),
        'sync': lambda: QemuClockSyncMixin.clock_sync_start(session),
    }
    with pytest.raises(ValueError, match='source-frame fence'):
        calls[operation]()
    assert session.vm._active_video_frame_fence == owner


def _real_hook_runner(o, *, pending):
    session = o.session
    session._run_with_hooks = MethodType(QemuHookSessionMixin._run_with_hooks, session)
    session._qemu_hook_pending = 'hook' if pending else None
    session._qemu_hook_pending_task = None
    session._qemu_hooks = {'hook': dict(hook='hook', breakpoint_id=17, access='x',
                                      runtime_address=0x7c00, length=1)}
    session._delete_hook_breakpoint = lambda identifier: None
    session.breakpoint = lambda address, **kwargs: {'breakpoint_id': 18}
    session._hook_reindex = lambda controls: setattr(session, '_qemu_hooks', {x['hook']: x for x in controls})
    session._dispatch_qemu_hook = lambda result: None
    return session


@pytest.mark.parametrize('terminal', ['completed', 'aborted'])
def test_source_terminal_during_pending_hook_step_prevents_another_continue(control, terminal):
    o = control
    o.session.video_frame_start()
    session = _real_hook_runner(o, pending=True)
    sent = []
    def execute(command, timeout_ms):
        sent.append(command)
        (o.wire.accept(consumed=False) if terminal == 'completed' else o.wire.abort(consumed=False))
        return stopped('step', reply='T05')
    session._execute = execute
    result = session.video_frame_advance()
    assert sent == ['s'] and result['outcome'] == 'step' and not result['advance_completed']
    assert result['completed_source_raster'] is (terminal == 'completed')
    assert session._qemu_hook_pending == 'hook' and not o.vm.closed


def test_terminal_coincident_hook_is_not_displaced_when_hooks_may_continue(control):
    o = control
    o.session.video_frame_start()
    session = _real_hook_runner(o, pending=False)
    sent = []
    def execute(command, timeout_ms):
        sent.append(command)
        o.wire.accept(consumed=False)
        return stopped('breakpoint', reply='T05')
    session._execute = execute
    session._dispatch_qemu_hook = lambda result: {'hook': 'hook', 'breakpoint_id': 17, 'stop': deepcopy(result)}
    result = session.video_frame_advance(stop_on_hook=False)
    assert sent == ['c'] and result['outcome'] == 'hook'
    assert result['completed_source_raster'] and not result['advance_completed']
    assert result['native_result']['session']['stop_reason']['native_reply'] == 'T05'


def test_failed_hook_terminal_query_retains_step_and_never_closes_a_replacement(control):
    o = control
    o.session.video_frame_start()
    session = _real_hook_runner(o, pending=True)
    replacement = SimpleNamespace(closed=False)
    replacement.close = lambda: setattr(replacement, 'closed', True)
    sent = []
    def execute(command, timeout_ms):
        sent.append(command)
        o.wire.abort(consumed=False)
        return stopped('step', reply='T05')
    session._execute = execute
    o.wire.after_control = lambda command: (setattr(session, 'vm', replacement)
        if command == 'x-fdisbull-query-video-frame-fence' else None)
    try:
        with pytest.raises(DebuggerError, match='owner changed') as caught:
            session.video_frame_advance()
        assert sent == ['s'] and o.vm.closed and not replacement.closed
        assert caught.value.video_frame_advance_evidence['native_result']['outcome'] == 'step'
        assert caught.value.video_frame_advance_evidence['native_result']['session']['stop_reason']['native_reply'] == 'T05'
    finally:
        session.vm = o.vm


def _real_tracker_runner(o, *, coincident):
    from test_late_tracking_stop import Recorder
    session = o.session
    session._run_with_hooks = lambda *, timeout_ms, stop_on_hook: session._execute('c', timeout_ms)
    tracker = session._automatic_runtime_tracker = Recorder()
    remote = SimpleNamespace(socket=object(), operation_deadline=None, calls=[], requests=[], pc=0x7c00)
    def request(text, *, timeout_ms=10000):
        remote.requests.append(text)
        return b'OK'
    def execute(command, timeout_ms, **kwargs):
        remote.calls.append(command)
        if command == 'c':
            remote.pc = 0x7c20
            if coincident:
                o.wire.accept(consumed=False)
        else:
            remote.pc += 2
            o.wire.abort(consumed=False)
        return b'T05', False
    remote.request, remote.execute = request, execute
    o.vm.gdb = remote
    session._stopped = lambda: remote
    session.registers = lambda: dict(linear_pc=hex(remote.pc), cpu_mode='real',
        address_state={'machine_vcpus': 1}, registers={'cs': '0x0', 'eip': hex(remote.pc)})
    session._automatic_tracking_callback_active = True
    try:
        point = session.breakpoint(0x7c20)['breakpoint_id']
    finally:
        session._automatic_tracking_callback_active = False
    tracker.internal_breakpoints.add(point)
    return remote, tracker


def test_source_abort_during_internal_tracker_step_prevents_hidden_continue(control):
    o = control
    o.session.video_frame_start()
    remote, tracker = _real_tracker_runner(o, coincident=False)
    result = o.session.video_frame_advance()
    assert remote.calls == ['c', 's']
    assert remote.requests == ['Z1,7c20,1', 'z1,7c20,1', 'Z1,7c20,1']
    assert result['outcome'] == 'step' and result['fence']['released']['state'] == 'aborted'
    assert not result['advance_completed'] and not o.vm.closed
    assert len([x for x in tracker.events if x[0] == 'internal']) == 1


def test_coincident_internal_breakpoint_is_recorded_without_displacement(control):
    o = control
    o.session.video_frame_start()
    remote, tracker = _real_tracker_runner(o, coincident=True)
    result = o.session.video_frame_advance()
    assert remote.calls == ['c'] and remote.requests == ['Z1,7c20,1']
    assert result['outcome'] == 'breakpoint' and not result['advance_completed']
    assert result['completed_source_raster'] and not result['stop_consumed']
    assert o.session._automatic_internal_pending['pc'] == '0x7c20'
    assert len([x for x in tracker.events if x[0] == 'internal']) == 1


def test_capability_advertises_only_source_control(control):
    o = control
    caps = MachineContext(o.vm).capabilities
    assert caps['video_frame_control'] and caps['video_frame_capture']
    assert caps['completed_guest_frames'] is False
    o.vm.qmp_commands -= {'x-fdisbull-cancel-video-frame-fence'}
    assert MachineContext(o.vm).capabilities['video_frame_control'] is False
