"""Legacy frame controls at the real host QMP envelope; no native execution."""
from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_dos_frames import QemuDOSFramesMixin
from fdisbull.qemu_frame_contract import configure_frame_contract
from fdisbull.qemu_machine import QemuMachine
from fdisbull.qemu_observation_authority import ObservationAuthority
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_qemu_video_control import control, stopped
from test_qemu_video_frame import audio, observation, video
from test_qemu_observation_cleanup import Process, Resource, client


@pytest.fixture
def source_step(control):
    o = control
    o.session.capabilities['video_frame_control'] = True
    o.vm.observation_authority = ObservationAuthority(o.vm)
    o.vm.observation_authority.bind(qmp=o.qmp, gdb=o.gdb)
    configure_frame_contract(o.session)
    return o


def script(*steps, backend='qemu-machine'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


def operations(o):
    return [row[0] for row in o.project.db.execute('SELECT operation FROM debug_events')]


def test_frame_step_shares_the_retained_frame_identity_and_post_execution_revision(source_step):
    o = source_step
    o.session.video_frame_start()
    before = o.session.status()
    result = o.session.call('frame.step', {'session_id': o.session.session_id})
    after = o.session.status()
    probe = o.session.frame_probe([])
    rgba = o.session.frame_rgba(encoding='png')
    assert result['completed'] is True and result['state'] == 'stopped'
    assert result['stop_reason']['kind'] == 'frame'
    assert result['native_advance']['native_result'] == o.actual
    assert result['registers'] == o.actual['registers']
    assert result['state_revision'] > before['state_revision']
    for value in (after, probe, rgba.metadata):
        assert value['session_id'] == result['session_id']
        assert value['state_revision'] == result['state_revision']
    for value in (probe, rgba.metadata):
        for name in ('frame_id', 'mode_id', 'frame_identity', 'source', 'frame_profile',
                     'source_bpp', 'captured_ns', 'captured_ticks', 'captured_ticks_clock'):
            assert value[name] == result[name]
    assert result['source_bpp'] == 24 and result['frame_id'] == 1
    assert result['guest_ticks'] == result['native_advance']['clocks']['after']['virtual_ns'] // 1_000_000
    assert result['guest_ticks_clock'] == 'QEMU_CLOCK_VIRTUAL_milliseconds'
    assert result['baseline_rows_sampled'] == 0
    assert len(result['native_advance']['frame']['rows']) == 200
    assert result['legacy_phase_equivalence'] is result['application_frame_complete'] is None
    assert o.session.capabilities['frame_step'] is True
    assert o.session.capabilities['completed_guest_frames'] is False
    assert operations(o).count('machine-video-frame-advance-intent') == 1
    assert operations(o).count('machine-video-frame-advance') == 1
    assert 'frame-step' not in operations(o)
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_frame_step_keeps_prearm_rows_in_the_existing_source_fence(source_step):
    o = source_step
    o.session.video_frame_start()
    o.wire.video.update(**{'rows-sampled': 100, 'in-progress': True})
    def complete():
        o.wire.accept()
        o.wire.video.update(**{'rows-sampled': 0, 'in-progress': False})
    o.dispatch = complete
    result = o.session.frame_step()
    assert result['completed'] and result['baseline_rows_sampled'] == 100
    assert result['native_advance']['fence']['arm']['baseline-rows-sampled'] == 100
    assert result['frame_id'] == 1 and len(o.executions) == 1


def test_existing_legacy_step_consumer_accepts_the_projected_boundary(source_step):
    from fdisbull.debug_timeline import FrameTimelineSessionMixin
    o = source_step
    o.session.video_frame_start()
    history = dict(last_native_frame_id=None)
    first = FrameTimelineSessionMixin._timeline_step(o.session, history)
    second = FrameTimelineSessionMixin._timeline_step(o.session, history)
    assert first['frame_id'] == 1 and second['frame_id'] == history['last_native_frame_id'] == 2
    assert first['completed'] and second['completed']


@pytest.mark.parametrize('state', ['idle', 'stopped', 'invalidated'])
def test_source_step_never_starts_repairs_or_falls_back_to_a_renderer(source_step, state):
    o = source_step
    if state != 'idle':
        o.session.video_frame_start()
        if state == 'stopped':
            o.session.video_frame_stop()
        else:
            o.wire.video.update(state='invalidated', reason='configuration-changed')
            o.wire.video.pop('next-deadline-ns')
    before = len(o.wire.calls)
    with pytest.raises(ValueError, match='explicitly started observing stream'):
        o.session.advance_frames()
    assert not o.executions and not o.vm.closed
    assert not any(command in ('x-fdisbull-start-video-frame', 'x-fdisbull-start-display',
                               'x-fdisbull-arm-display-frame', 'screendump')
                   for command, _ in o.wire.calls[before:])


@pytest.mark.parametrize('options', [dict(frames=0), dict(frames=129), dict(frames=True),
    dict(timeout_ms=0), dict(timeout_ms=True), dict(frames=1, timeout_ms=600001)])
def test_bad_advance_parameters_refuse_before_lock_or_wire(source_step, options):
    o = source_step
    class NoLock:
        def acquire(self, **kwargs):
            pytest.fail('Invalid declaration reached the machine lock')
    old = o.vm.lock
    o.vm.lock = NoLock()
    try:
        with pytest.raises(ValueError):
            o.session.advance_frames(**options)
    finally:
        o.vm.lock = old
    assert not o.wire.calls and not o.executions


def test_missing_step_capability_refuses_before_lock_and_legacy_rpc_params_are_exact(source_step):
    o = source_step
    for params in ({'frames': 2}, {'session_id': 'foreign'}, {'timeout_ms': False}):
        with pytest.raises((TypeError, ValueError)):
            o.session.call('frame.step', params)
    o.session.capabilities['frame_step'] = False
    class NoLock:
        def acquire(self, **kwargs):
            pytest.fail('Missing capability reached the machine lock')
    old = o.vm.lock
    o.vm.lock = NoLock()
    try:
        with pytest.raises(ValueError, match='frame_step capability'):
            o.session.frame_step()
    finally:
        o.vm.lock = old
    assert not o.wire.calls and not o.executions


@pytest.mark.parametrize('accepted,consumed', [(False, False), (True, False), (True, True)])
def test_actual_breakpoint_is_never_relabelled_as_a_completed_step(source_step, accepted, consumed):
    o = source_step
    o.session.video_frame_start()
    o.wire.publish()
    old = deepcopy(o.wire.video['frame'])
    o.actual = stopped('breakpoint', reply='T05')
    o.dispatch = (lambda: o.wire.accept(consumed=consumed)) if accepted else lambda: None
    result = o.session.frame_step()
    assert result['completed'] is False and result['state'] == 'stopped'
    assert result['stop_reason'] == o.actual['session']['stop_reason']
    assert result['registers'] == o.actual['registers']
    assert result['native_advance']['native_result'] == o.actual
    assert result['completed_source_raster'] is accepted
    assert result['frame_id'] == (2 if accepted else None)
    if not accepted:
        assert result['native_advance']['source']['after']['frame'] == old
        assert result['frame_identity'] is None
    assert len(o.executions) == 1 and not o.vm.closed


def test_batch_returns_only_the_completed_prefix_and_actual_interruption(source_step):
    o = source_step
    o.session.video_frame_start()
    def dispatch():
        if len(o.executions) == 1:
            o.wire.accept()
        else:
            o.actual = stopped('watchpoint', reply='T05watch:30000;')
    o.dispatch = dispatch
    result = o.session.advance_frames(frames=3)
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 1
    assert len(result['frames']) == 1 and result['frames'][0]['frame_id'] == 1
    assert result['stop'] == o.actual
    assert result['interrupted_frame']['native_advance']['native_result'] == o.actual
    assert result['interrupted_frame']['frame_id'] is None
    assert len(o.executions) == 2 and not o.vm.closed


def test_source_abort_retains_the_actual_result_and_allows_explicit_recovery(source_step):
    o = source_step
    o.session.video_frame_start()
    o.dispatch = lambda: o.wire.abort()
    result = o.session.advance_frames()
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 0
    assert result['interrupted_frame']['native_advance']['fence']['observed']['state'] == 'aborted'
    assert result['interrupted_frame']['frame_id'] is None and not o.vm.closed
    o.session.video_frame_start()
    o.dispatch = lambda: o.wire.accept()
    assert o.session.frame_step()['completed']


@pytest.mark.parametrize('reply,exitcode', [('W00', 0), ('X09', -9)])
def test_original_owner_exit_has_no_fabricated_post_exit_frame_or_reads(source_step, reply, exitcode):
    o = source_step
    o.session.video_frame_start()
    # Match the real VM surface: close() retains process, clears the channels,
    # and establishes process.poll(); it never invents a vm.closed attribute.
    del o.vm.closed
    process = SimpleNamespace(returncode=None, stdin=None, stdout=None)
    process.poll = lambda: process.returncode
    o.vm.process, o.vm.temporary = process, None
    o.gdb.close = lambda: setattr(o.gdb, 'socket', None)
    o.vm.close = MethodType(QemuMachine.close, o.vm)
    o.actual = dict(outcome='exited', timed_out=False, session=dict(state='exited',
        stop_reason=dict(kind='exited', native_reply=reply, breakpoint_ids=[])), registers=None)
    o.dispatch = lambda: setattr(process, 'returncode', exitcode)
    result = o.session.advance_frames(frames=2)
    interrupted = result['interrupted_frame']
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 0
    assert result['stop'] == o.actual and interrupted['state'] == 'exited'
    assert interrupted['owner_exited'] and interrupted['frame_id'] is None
    assert interrupted['completed_source_raster'] is None and interrupted['guest_ticks'] is None
    assert interrupted['native_advance']['source']['after'] is None
    assert not any(command == 'x-fdisbull-query-video-frame-fence' for command, _ in o.wire.calls)
    assert len(o.executions) == 1 and o.vm.process is process and process.poll() == exitcode
    assert o.vm.qmp is o.vm.gdb is None and not hasattr(o.vm, 'closed')


def test_batch_never_executes_or_closes_a_replacement_owner(source_step, monkeypatch):
    o = source_step
    o.session.video_frame_start()
    old_step = o.session.frame_step
    replacement_closes = []
    replacement = SimpleNamespace(close=lambda: replacement_closes.append(True))
    def replace(**kwargs):
        result = old_step(**kwargs)
        o.session.vm = replacement
        return result
    monkeypatch.setattr(o.session, 'frame_step', replace)
    try:
        with pytest.raises(DebuggerError, match='owner') as caught:
            o.session.advance_frames(frames=2)
        assert len(o.executions) == 1 and o.vm.closed and not replacement_closes
        assert caught.value.frame_advance_evidence['requested_frames'] == 2
    finally:
        o.session.vm = o.vm


@pytest.mark.parametrize('replacement', ['qmp', 'gdb', 'qmp_socket', 'gdb_socket'])
@pytest.mark.parametrize('failure', ['between_steps', 'controller_exception'])
def test_replaced_channels_never_become_real_close_targets(source_step, monkeypatch, replacement, failure):
    o = source_step
    o.session.video_frame_start()
    # Exercise QemuMachine.close and the real QMP/GDB client close methods,
    # including a second caller cleanup after the original handler returned.
    del o.vm.closed
    process = Process()
    o.vm.process, o.vm.temporary = process, None
    original_gdb = client(GDBRemote, 'original-gdb')
    o.gdb = o.vm.gdb = original_gdb
    o.vm.observation_authority.bind(gdb=original_gdb)
    o.vm.close = MethodType(QemuMachine.close, o.vm)
    original_socket = original_gdb.socket if replacement.startswith('gdb') else o.qmp.socket
    original_closes = []
    actual_close = original_socket.close
    def close_original_socket():
        original_closes.append(True)
        return actual_close()
    monkeypatch.setattr(original_socket, 'close', close_original_socket)
    foreign = Resource('replacement-socket')
    foreign_client = client(GDBRemote if replacement.startswith('gdb') else QemuControl,
                            'replacement-client')
    def replace():
        if replacement.endswith('_socket'):
            getattr(o.vm, replacement.split('_')[0]).socket = foreign
        else:
            setattr(o.vm, replacement, foreign_client)
    if failure == 'between_steps':
        step = o.session.frame_step
        def wrapped(**kwargs):
            result = step(**kwargs)
            replace()
            return result
        monkeypatch.setattr(o.session, 'frame_step', wrapped)
        invoke = lambda: o.session.advance_frames(frames=2)
    else:
        advance = o.session.video_frame_advance
        def wrapped(**kwargs):
            result = advance(**kwargs)
            replace()
            error = DebuggerError('authored controller exception after resource replacement')
            error.result = result
            raise error
        monkeypatch.setattr(o.session, 'video_frame_advance', wrapped)
        invoke = o.session.frame_step
    with pytest.raises(DebuggerError) as caught:
        invoke()
    o.vm.close()
    assert len(o.executions) == 1 and process.terminates == process.waits == 1
    assert process.kills == 0 and original_closes == [True]
    assert (original_socket.closed if replacement.startswith('gdb') else original_socket.socket_closed)
    assert foreign.closes == foreign_client.socket.closes == 0
    assert not hasattr(o.vm, 'closed')
    if replacement.endswith('_socket'):
        assert getattr(o.vm, replacement.split('_')[0]).socket is foreign
    else:
        assert getattr(o.vm, replacement) is foreign_client
    if failure == 'between_steps':
        assert caught.value.frame_advance_evidence['completed_frames'] == 1
        assert caught.value.frame_advance_evidence['frames'][0]['registers'] == o.actual['registers']
    else:
        assert caught.value.result['native_result'] == o.actual


@pytest.mark.parametrize('failure', ['between_steps', 'controller_exception'])
def test_retained_process_cleanup_never_selects_a_replacement(source_step, monkeypatch, failure):
    o = source_step
    o.session.video_frame_start()
    calls = []
    process = SimpleNamespace(returncode=None, stdin=None, stdout=None)
    process.poll = lambda: process.returncode
    def terminate():
        calls.append('original-terminate')
        process.returncode = -15
    process.terminate = terminate
    process.wait = lambda timeout: process.returncode
    process.kill = lambda: pytest.fail('The exited original required no kill')
    replacement = SimpleNamespace(poll=lambda: None,
        terminate=lambda: pytest.fail('A replacement process was terminated'),
        kill=lambda: pytest.fail('A replacement process was killed'))
    o.vm.process, o.vm.temporary = process, None
    o.gdb.close = lambda: setattr(o.gdb, 'socket', None)
    if failure == 'between_steps':
        step = o.session.frame_step
        def replace(**kwargs):
            result = step(**kwargs)
            o.vm.process = replacement
            return result
        monkeypatch.setattr(o.session, 'frame_step', replace)
        invoke = lambda: o.session.advance_frames(frames=2)
    else:
        advance = o.session.video_frame_advance
        def replace(**kwargs):
            result = advance(**kwargs)
            o.vm.process = replacement
            error = DebuggerError('authored controller exception after process replacement')
            error.result = result
            raise error
        monkeypatch.setattr(o.session, 'video_frame_advance', replace)
        invoke = o.session.frame_step
    try:
        with pytest.raises(DebuggerError) as caught:
            invoke()
        assert calls == ['original-terminate'] and len(o.executions) == 1
        assert o.vm.process is replacement and o.vm.qmp is o.vm.gdb is None
        if failure == 'between_steps':
            assert caught.value.frame_advance_evidence['completed_frames'] == 1
        else:
            assert caught.value.result['native_result'] == o.actual
    finally:
        o.vm.process = process


def test_multiple_steps_share_one_outer_deadline_and_restore_channel_bounds(source_step):
    o = source_step
    o.session.video_frame_start()
    o.vm.operation_deadline = o.clock.now + .3
    o.qmp.operation_deadline = o.clock.now + .25
    o.gdb.operation_deadline = o.clock.now + .2
    original = (o.vm.operation_deadline, o.qmp.operation_deadline, o.gdb.operation_deadline)
    def dispatch():
        o.clock.advance(.04)
        o.wire.accept()
    o.dispatch = dispatch
    result = o.session.advance_frames(frames=2, timeout_ms=5000)
    assert result['outcome'] == 'completed' and result['completed_frames'] == 2
    assert 1 <= o.executions[1]['timeout_ms'] < o.executions[0]['timeout_ms'] <= 200
    assert (o.vm.operation_deadline, o.qmp.operation_deadline, o.gdb.operation_deadline) == original
    assert result['frames'][1]['frame_id'] == result['frames'][0]['frame_id'] + 1


def test_late_batch_retains_completed_evidence_and_closes_original_owner(source_step, monkeypatch):
    o = source_step
    o.session.video_frame_start()
    step = o.session.frame_step
    def late(**kwargs):
        result = step(**kwargs)
        o.clock.advance(.2)
        return result
    monkeypatch.setattr(o.session, 'frame_step', late)
    with pytest.raises(TimeoutError) as caught:
        o.session.advance_frames(frames=2, timeout_ms=100)
    assert len(o.executions) == 1 and o.vm.closed
    assert caught.value.frame_advance_evidence['frames'][0]['native_advance']['advance_completed']


def test_dos_advance_dispatches_source_capability_without_renderer_or_checkpoint_admission(source_step):
    o = source_step
    o.session.__class__ = type('SourceStepDOS', (QemuDOSFramesMixin, type(o.session)), {})
    o.session.metadata['backend'] = 'qemu-dos'
    o.session.capabilities['frame_timeline'] = False
    def forbidden(*args, **kwargs):
        pytest.fail('Source-only advancement reached renderer/history admission')
    o.session._frame_capability = o.session._history_admission = forbidden
    o.session.video_frame_start()
    result = o.session.advance_frames(frames=2)
    assert result['outcome'] == 'completed' and result['completed_frames'] == 2
    assert result['source'] == 'qemu_completed_source_raster'
    assert not any('display' in command for command, _ in o.wire.calls)


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_json_and_script_source_advance_do_not_require_a_renderer_timeline(source_step, backend):
    o = source_step
    o.session.metadata['backend'] = backend
    o.session.capabilities['frame_timeline'] = False
    o.session.video_frame_start()
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=o.directory / 'outputs')):
            reply = respond(dict(id=1, method='debug-frame-advance', params=dict(
                project=str(o.project.path), run=o.session.run_id, frames=1, timeout_ms=500)),
                debugger=workspace)
        assert reply['ok'], reply
        result = reply['result']
        assert result['completed_frames'] == 1 and result['frames'][0]['frame_id'] == 1
        report = execute_script(o.session, script(dict(op='frame-advance', frames=2), backend=backend))
        assert report['ok'] and report['steps'][0]['result']['completed_frames'] == 2
        assert report['steps'][0]['result']['frames'][-1]['frame_id'] == 3
    finally:
        workspace.sessions.clear()


@pytest.mark.parametrize('step', [dict(op='frame-advance', frames=0),
    dict(op='frame-advance', frames='$count', timeout_ms=False)])
def test_source_script_literal_preflight_precedes_an_earlier_write(source_step, step):
    o = source_step
    writes = []
    o.session.write_memory = lambda **kwargs: writes.append(kwargs)
    with pytest.raises(ValueError):
        execute_script(o.session, script(dict(op='write-memory', address=0x7c00, data_hex='90'), step))
    assert not writes and not o.wire.calls and not o.executions


def test_source_script_capability_and_transaction_preflight_precede_effects(source_step):
    o = source_step
    writes = []
    o.session.write_memory = lambda **kwargs: writes.append(kwargs)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90'), dict(op='frame-advance'))
    o.session.capabilities['frame_step'] = False
    with pytest.raises(ValueError):
        execute_script(o.session, value)
    o.session.capabilities['frame_step'] = True
    with o.project.transaction(True):
        with pytest.raises(ValueError, match='transaction'):
            validate_script(value, session=o.session)
    assert not writes and not o.wire.calls and not o.executions


def test_source_script_first_stop_preserves_the_receipt_and_skips_following_write(source_step):
    o = source_step
    o.session.video_frame_start()
    o.actual = stopped('breakpoint', reply='T05')
    o.dispatch = lambda: None
    writes = []
    o.session.write_memory = lambda **kwargs: writes.append(kwargs)
    report = execute_script(o.session, script(dict(op='frame-advance', frames=2),
        dict(op='write-memory', address=0x7c00, data_hex='90')))
    assert not report['ok'] and not writes and len(o.executions) == 1
    assert report['steps'][0]['result']['stop'] == o.actual
    assert report['steps'][0]['result']['completed_frames'] == 0 and not o.vm.closed
