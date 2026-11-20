"""Scene waits through real FDB/public routes with an authored native boundary.

Only the selected RAM transition and bounded native clock stop are supplied.
These host tests do not qualify an actual QEMU/DOS workload.
"""
from copy import copy, deepcopy
from functools import wraps
import inspect
import hashlib
import json
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_control import QemuControl
from fdisbull.scenes import SceneError, SceneSessionMixin, encoded
from support.qemu_scene_wait_assertions import initial_match_preserves_arm
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_qemu_movement import moving
from test_qemu_scenes import save, definition
from test_qemu_keyboard_press import ARM, PressWire


@pytest.fixture
def scene_waiting(moving):
    o = moving
    save(o)
    o.ram[2] = 1
    o.ready_after = 2
    advance = o.session._clock_advance_with_hooks
    def transition(delta_ns, *, timeout_ms):
        result = advance(delta_ns, timeout_ms=timeout_ms)
        if o.ready_after is not None and len(o.runs) >= o.ready_after:
            o.ram[2] = 0
        return result
    o.session._clock_advance_with_hooks = transition
    return o


@pytest.fixture
def armed_scene_wait(scene_waiting):
    """Use real clock/press/schedule validation over the deterministic QMP wire.

    RAM and GDB still use the authored stopped peer; no VM is launched. Unlike
    arm_fixed, this seam exercises the production observation receipt refresh.
    """
    o, s = scene_waiting, scene_waiting.session
    o.wire = PressWire(SimpleNamespace(now=time.monotonic()))
    o.wire.receipt['virtual-ns'] = o.wire.input['virtual-ns'] = 0
    qmp = QemuControl.__new__(QemuControl)
    qmp.socket, qmp.buffer, qmp.sequence = o.wire, bytearray(), 0
    qmp.lock, qmp.operation_deadline = threading.Lock(), None
    call = qmp.call
    def observed_call(command, arguments=None, **kwargs):
        if command == 'human-monitor-command':
            return o.peer.call(command, arguments, **kwargs)
        return call(command, arguments, **kwargs)
    qmp.call = observed_call
    s.vm.qmp = qmp
    s.vm.qmp_commands |= {ARM}
    s.vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    s.capabilities['virtual_keyboard_press'] = True
    del s.clock_observe
    o.ram[2] = 0
    s.keyboard_press('a', hold_ms=20, gap_ms=20)
    return o


def options(**changes):
    return dict(scene='room', object='actor', guest_ms=100, slice_ms=10,
                timeout_ms=3000, **changes)


def process_return(o, run, kind):
    """Model the real DOS return adapter's epoch advance and retained receipt."""
    s = o.session
    s._advance_epoch()
    resident = kind == 'guest_tsr'
    termination = dict(type='resident' if resident else 'normal', code=0,
        resident=resident, psp_segment=s._process['psp_segment'],
        parent_psp_segment=s._process['parent_psp_segment'],
        source='authored DOS EXEC helper and DOS AH=4Dh return status')
    s._process.update(state='resident' if resident else 'exited', termination=termination)
    run.update(outcome=kind, process=deepcopy(s._process))
    run['session']['stop_reason'] = dict(kind=kind, guest_exit=deepcopy(termination), breakpoint_ids=[])


def test_initial_match_never_executes_and_persists_without_frame(scene_waiting):
    o = scene_waiting
    o.ram[2] = 0
    before = deepcopy(o.session.input_state())
    result = o.session.scene_wait(**options())
    assert result['status'] == 'matched' and result['complete']
    assert result['completion_scope'] == 'declared-runtime-predicates'
    assert result['wait']['guest_elapsed_ns'] == 0 and not result['wait']['runs']
    assert not o.runs and not o.writes and o.session.input_state() == before
    assert 'frame' not in result and result['capture_context_verified']
    with Project(o.project.path) as reopened:
        stored = reopened.debug_scene_observation(result['observation'])
        assert stored['historical'] and not stored['live_state_verified']
        assert stored['result'] == result


def test_json_wait_observes_measured_progress_then_stops(scene_waiting):
    o, s = scene_waiting, scene_waiting.session
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        response = respond(dict(method='debug-scene-wait', params=dict(
            project=str(o.project.path), run=s.run_id, **options())), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert response['ok'], response
    result = response['result']
    assert result['status'] == 'matched' and result['complete']
    assert result['wait']['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert result['wait']['guest_elapsed_ns'] == 20_000_000
    assert result['wait']['guest_elapsed_ms'] == 20
    assert [p['status'] for p in result['wait']['polls']] == ['mismatch', 'mismatch', 'matched']
    assert len(result['wait']['runs']) == len(o.runs) == 2
    assert result['observation_context']['clock']['virtual_ns'] == o.now
    raw = o.project.db.execute('SELECT document FROM debug_scene_observations WHERE id=?',
                              (result['observation'],)).fetchone()[0].encode()
    assert len(raw) == result['wait']['evidence_bytes']
    assert not o.writes and not o.deliveries


def test_saved_script_wait_and_following_assertion_use_same_contract(scene_waiting):
    o = scene_waiting
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='scene-wait', **options(), **{'as': 'ready'}),
        dict(op='assert', value='$ready.status', equals='matched')])
    saved = o.project.debug_save_script('scene-wait.json', script)
    result = o.session.script(script_id=saved['script_id'])
    assert result['ok'] and result['completed_steps'] == 2, result
    assert result['steps'][0]['result']['wait']['guest_elapsed_ns'] == 20_000_000
    assert len(o.runs) == 2


@pytest.mark.parametrize('process_addresses', [False, True],
                         ids=['without-process-addresses', 'with-process-addresses'])
def test_bounded_json_export_recovers_full_result_without_repeating_wait(scene_waiting, tmp_path, process_addresses):
    o, s = scene_waiting, scene_waiting.session
    if process_addresses:
        advance = s._clock_advance_with_hooks
        def process_boundary(*args, **kwargs):
            result = advance(*args, **kwargs)
            result['process'] = dict(state='active',
                allocation=dict(start=0x24000, end=0x26000, paragraphs=512),
                drivers=dict(status='observed', headers=[
                    dict(address=0xa000, attributes=0x8004, character=True, name='NUL'),
                    dict(address=0xa100, attributes=0x8000, character=True, name='CON')]))
            return result
        s._clock_advance_with_hooks = process_boundary
    observed_waits = []
    original_wait = s.scene_wait
    @wraps(original_wait)
    def capture_wait(*args, **kwargs):
        result = original_wait(*args, **kwargs)
        observed_waits.append(deepcopy(result))
        return result
    s.scene_wait = capture_wait
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        with output_policy_context(OutputPolicy(max_inline_bytes=4096, artifact_dir=tmp_path / 'outputs')):
            reply = respond(dict(method='debug-scene-wait', params=dict(
                project=str(o.project.path), run=s.run_id, **options())), debugger=workspace)
            assert reply['ok'], reply
            marker = reply['result']
            assert marker['format'] == 'fdisbull-output-ref-1' and not marker['complete']
            assert marker['execution']['complete'] is True and marker['retry_safe'] is False
            before = (len(o.runs), o.now, len(o.project.debug_scene_observations()['observations']))
            output = tmp_path / 'scene-wait-response.json'
            exported = respond(dict(method='output-export', params=dict(
                artifact=marker['artifact']['id'], output=str(output))))
            assert exported['ok'], exported
            raw = output.read_bytes()
            assert len(raw) == marker['artifact']['bytes']
            assert hashlib.sha256(raw).hexdigest() == marker['artifact']['sha256']
            result = json.loads(raw)['result']
            assert result['status'] == 'matched' and result['wait']['guest_elapsed_ns'] == 20_000_000
            assert before == (len(o.runs), o.now, len(o.project.debug_scene_observations()['observations']))
            assert len(observed_waits) == 1
            canonical = observed_waits[0]
            assert result == public_addresses(canonical)
            assert canonical['wait']['runs'] == o.runs
            if process_addresses:
                for original, projected in zip(canonical['wait']['runs'], result['wait']['runs'], strict=True):
                    allocation = original['process']['allocation']
                    assert allocation == dict(start=0x24000, end=0x26000, paragraphs=512)
                    assert projected['process']['allocation'] == dict(start='0x24000', end='0x26000', paragraphs=512)
                    headers = original['process']['drivers']['headers']
                    public_headers = projected['process']['drivers']['headers']
                    assert [header['address'] for header in headers] == [0xa000, 0xa100]
                    assert [header['address'] for header in public_headers] == ['0xa000', '0xa100']
                    assert all(header['character'] is True for header in public_headers)
            assert o.project.debug_scene_observation(canonical['observation'])['result'] == canonical
    finally:
        workspace.sessions.clear()
        s.scene_wait = original_wait
    with Project(o.project.path) as reopened:
        historical = reopened.debug_scene_observation(canonical['observation'])
        assert historical['result'] == canonical and historical['historical'] and not historical['live_state_verified']


def test_json_terminal_error_retains_the_persisted_scene_result(scene_waiting):
    o, s = scene_waiting, scene_waiting.session
    o.stop_on = 1
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        reply = respond(dict(method='debug-scene-wait', params=dict(
            project=str(o.project.path), run=s.run_id, **options())), debugger=workspace)
    finally:workspace.sessions.clear()
    assert not reply['ok'] and reply['error']['type'] == 'SceneError'
    result = reply['error']['result']
    assert result['status'] == 'stopped' and not result['complete']
    assert result['wait']['stop'] == o.runs[0] and len(o.runs) == 1
    assert o.project.debug_scene_observation(result['observation'])['result'] == result


@pytest.mark.parametrize('error_type', [OSError, RuntimeError])
def test_json_primary_error_and_scene_wait_prefix_both_survive(scene_waiting, error_type):
    o, s = scene_waiting, scene_waiting.session
    primary = error_type('authored native execution failure')
    primary.result = {'native_stop': 'T05thread:1;', 'observed_prefix': ['first-native-stop']}
    def failed(*args, **kwargs):raise primary
    s._clock_advance_with_hooks = failed
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        reply = respond(dict(method='debug-scene-wait', params=dict(
            project=str(o.project.path), run=s.run_id, **options())), debugger=workspace)
    finally:workspace.sessions.clear()
    assert not reply['ok'] and reply['error']['type'] == error_type.__name__
    assert reply['error']['result'] == primary.result
    partial = reply['error']['scene_wait_result']
    assert partial == primary.scene_wait_result and partial['wait']['polls']
    assert not partial['wait']['clock_progress_complete'] and o.closed


def test_script_retains_primary_error_and_separate_wait_prefix(scene_waiting, tmp_path):
    o = scene_waiting
    primary = OSError('authored native execution failure')
    primary.result = {'native_stop': 'T05thread:1;', 'observed_prefix': ['first-native-stop']}
    def failed(*args, **kwargs):raise primary
    o.session._clock_advance_with_hooks = failed
    scripted = o.session.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='scene-wait', **options()), dict(op='assert', value=True, equals=True)]))
    assert not scripted['ok'] and scripted['completed_steps'] == 0 and len(scripted['steps']) == 1
    step = scripted['steps'][0]
    assert step['result'] == primary.result and step['scene_wait_result'] == primary.scene_wait_result
    assert step['scene_wait_result']['wait']['polls'] and o.closed
    output = tmp_path / 'failed-script.json'
    o.project.debug_export(scripted['artifact'], output)
    assert json.loads(output.read_text())['steps'][0] == step


def test_bounded_json_error_export_retains_stop_without_replay(scene_waiting, tmp_path):
    o, s = scene_waiting, scene_waiting.session
    o.stop_on = 1
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        with output_policy_context(OutputPolicy(max_inline_bytes=4096, artifact_dir=tmp_path / 'outputs')):
            reply = respond(dict(method='debug-scene-wait', params=dict(
                project=str(o.project.path), run=s.run_id, **options())), debugger=workspace)
            assert not reply['ok'] and reply['error']['type'] == 'SceneError'
            marker = reply['output']
            assert marker['format'] == 'fdisbull-output-ref-1' and not marker['complete']
            assert marker['execution']['ok'] is False and marker['retry_safe'] is False
            before = (len(o.runs), o.now, len(o.reads))
            output = tmp_path / 'failed-wait.json'
            exported = respond(dict(method='output-export', params=dict(
                artifact=marker['artifact']['id'], output=str(output))))
            assert exported['ok'], exported
            raw = output.read_bytes()
            assert len(raw) == marker['artifact']['bytes']
            assert hashlib.sha256(raw).hexdigest() == marker['artifact']['sha256']
            result = json.loads(raw)['error']['result']
            assert result['wait']['stop'] == o.runs[0] and not result['complete']
            assert before == (len(o.runs), o.now, len(o.reads))
    finally:workspace.sessions.clear()


def test_first_breakpoint_wins_before_post_stop_predicate_read(scene_waiting):
    o = scene_waiting
    o.stop_on, o.ready_after = 1, 1
    reads_at_stop = []
    advance = o.session._clock_advance_with_hooks
    def stopped(*args, **kwargs):
        result = advance(*args, **kwargs)
        reads_at_stop.append(len(o.reads))
        return result
    o.session._clock_advance_with_hooks = stopped
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**options())
    result = error.value.result
    assert result['status'] == 'stopped' and not result['complete']
    assert result['wait']['stop'] is o.runs[0]
    assert len(result['wait']['polls']) == len(o.runs) == 1
    assert len(o.reads) == reads_at_stop[0]
    assert o.ram[2] == 0 and result['scene_matched'] is False
    assert o.project.debug_scene_observation(result['observation'])['result']['wait']['stop'] == o.runs[0]


def test_false_predicate_exhausts_virtual_budget_without_extra_run(scene_waiting):
    o = scene_waiting
    o.ready_after = None
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**dict(options(), guest_ms=20))
    result = error.value.result
    assert result['status'] == 'timeout' and not result['complete']
    assert result['wait']['outcome'] == 'guest_budget'
    assert result['wait']['guest_elapsed_ns'] == 20_000_000 and len(o.runs) == 2


def test_unsupported_frame_scene_refuses_before_native_io(scene_waiting):
    from test_scene_domain_integration import scene as frame_definition
    o = scene_waiting
    legacy = o.project.debug_save_scene('legacy', frame_definition(o.project))
    before = (len(o.reads), len(o.peer.qmp_calls))
    with pytest.raises(ValueError, match='scene-2'):
        o.session.scene_wait(legacy['id'])
    assert before == (len(o.reads), len(o.peer.qmp_calls))
    assert not o.runs and not o.writes


def test_public_signature_matches_existing_scene_wait(scene_waiting):
    assert inspect.signature(type(scene_waiting.session).scene_wait) == inspect.signature(SceneSessionMixin.scene_wait)


@pytest.mark.parametrize('change', [
    {'guest_ms': 0}, {'guest_ms': 120001}, {'guest_ms': True},
    {'timeout_ms': 0}, {'timeout_ms': 60001}, {'timeout_ms': None},
    {'slice_ms': 0}, {'slice_ms': 1001}, {'slice_ms': False},
    {'compact': 0}, {'object': 7}, {'scene': ''},
])
def test_invalid_literals_refuse_direct_and_script_before_prior_ram_write(scene_waiting, change):
    o = scene_waiting
    before = (len(o.reads), len(o.peer.qmp_calls))
    with pytest.raises((ValueError, TypeError)):
        o.session.scene_wait(**dict(options(), **change))
    step = dict(op='scene-wait', **dict(options(), **change))
    if 'scene' not in change:
        step['scene'] = '$later.scene_revision'
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-runtime-memory', binding='move-state', offset=2, data_hex='00', expected_hex='01'), step])
    with pytest.raises((ValueError, TypeError)):
        o.session.script(script)
    assert before == (len(o.reads), len(o.peer.qmp_calls))
    assert not o.runs and not o.writes and o.ram[2] == 1


def test_resolved_boolean_timeout_rejected_before_script_timeout_clamp(scene_waiting):
    o = scene_waiting
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='scene-check', scene='room', **{'as': 'before'}),
        dict(op='scene-wait', **dict(options(), timeout_ms='$before.complete'))])
    result = o.session.script(script)
    assert not result['ok'] and result['completed_steps'] == 1
    assert 'integer' in result['error']['message'] and not o.runs and not o.writes


def test_literal_frame_profile_refuses_before_prior_script_write(scene_waiting):
    from test_scene_domain_integration import scene as frame_definition
    o = scene_waiting
    o.project.debug_save_scene('legacy', frame_definition(o.project))
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-runtime-memory', binding='move-state', offset=2, data_hex='00', expected_hex='01'),
        dict(op='scene-wait', scene='legacy')])
    with pytest.raises(ValueError, match='scene-2'):
        o.session.script(script)
    assert not o.writes and not o.runs


@pytest.mark.parametrize('kind', ['watchpoint', 'exception', 'guest_exit', 'guest_tsr', 'exited', 'timeout', 'hook'])
def test_each_terminal_stop_is_kept_without_a_post_stop_ram_read(scene_waiting, kind):
    o = scene_waiting
    o.ready_after = 1
    advance = o.session._clock_advance_with_hooks
    reads_at_stop = []
    def stopped(*args, **kwargs):
        run = advance(*args, **kwargs)
        run['outcome'] = kind
        if kind == 'hook':run['hook_hits'] = [{'id': 'authored-observer'}]
        if kind in ('guest_exit', 'guest_tsr'):
            process_return(o, run, kind)
        reads_at_stop.append(len(o.reads))
        return run
    o.session._clock_advance_with_hooks = stopped
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**options())
    result = error.value.result
    assert result['status'] == 'stopped' and not result['complete']
    assert result['wait']['outcome'] == kind and result['wait']['stop'] is o.runs[0]
    assert len(result['wait']['polls']) == len(o.runs) == 1
    assert len(o.reads) == reads_at_stop[0] and not o.closed


@pytest.mark.parametrize('change', ['checkpoint', 'process-epoch', 'psp', 'projection', 'process-state'])
def test_terminal_stop_rejects_unrelated_lifetime_changes(scene_waiting, change):
    o = scene_waiting
    o.stop_on = 1
    advance = o.session._clock_advance_with_hooks
    reads_at_stop = []
    def changed(*args, **kwargs):
        run = advance(*args, **kwargs)
        if change == 'checkpoint':o.session._checkpoint_epoch = 99
        elif change == 'process-epoch':o.session._process['capture_epoch'] += ':wrong'
        elif change == 'psp':o.session._process['psp_segment'] += 1
        elif change == 'projection':o.session._qemu_cpu_delta_history = dict(id='changed', frozen=True)
        else:o.session._process['state'] = 'exited'
        reads_at_stop.append(len(o.reads))
        return run
    o.session._clock_advance_with_hooks = changed
    with pytest.raises(ValueError, match='journal owner') as error:o.session.scene_wait(**options())
    assert error.value.scene_wait_result['wait']['stop'] is o.runs[0]
    assert len(o.runs) == 1 and len(o.reads) == reads_at_stop[0] and o.closed
    assert not o.project.debug_scene_observations()['observations']


@pytest.mark.parametrize('change', ['checkpoint', 'psp', 'projection', 'receipt'])
def test_real_dos_return_does_not_excuse_unrelated_identity_changes(scene_waiting, change):
    o = scene_waiting
    advance = o.session._clock_advance_with_hooks
    def changed(*args, **kwargs):
        run = advance(*args, **kwargs)
        process_return(o, run, 'guest_exit')
        if change == 'checkpoint':o.session._checkpoint_epoch = 99
        elif change == 'psp':
            o.session._process['psp_segment'] += 1
            run['process'] = deepcopy(o.session._process)
        elif change == 'projection':o.session._qemu_cpu_delta_history = dict(id='changed', frozen=True)
        else:run['session']['stop_reason']['guest_exit']['resident'] = True
        return run
    o.session._clock_advance_with_hooks = changed
    with pytest.raises(ValueError, match='journal owner') as error:o.session.scene_wait(**options())
    assert error.value.scene_wait_result['wait']['stop'] is o.runs[0]
    assert len(o.runs) == 1 and o.closed and not o.project.debug_scene_observations()['observations']


def test_returned_post_close_process_receipt_keeps_the_exact_terminal_stop(scene_waiting):
    o = scene_waiting
    advance = o.session._clock_advance_with_hooks
    reads_at_stop = []
    def closed(*args, **kwargs):
        run = advance(*args, **kwargs)
        process_return(o, run, 'guest_exit')
        o.session._on_machine_closed()
        o.session.closed = True
        run['process'] = deepcopy(o.session._process)
        run['session']['state'] = 'closed'
        del run['clock_budget']
        reads_at_stop.append(len(o.reads))
        return run
    o.session._clock_advance_with_hooks = closed
    with pytest.raises(SceneError) as error:o.session.scene_wait(**options())
    result = error.value.result
    assert result['wait']['stop'] is o.runs[0] and result['wait']['outcome'] == 'guest_exit'
    assert result['wait']['stop']['process']['capture_epoch'] == 'source-run:process:3'
    assert not result['wait']['clock_progress_complete']
    assert len(o.runs) == 1 and len(o.reads) == reads_at_stop[0]


def test_closed_clock_error_keeps_dos_return_receipt_and_primary_error(scene_waiting):
    from fdisbull.dosbox_rpc import DebuggerError
    o = scene_waiting
    advance = o.session._clock_advance_with_hooks
    primary = DebuggerError('Machine closed before its native clock budget could be observed')
    def closed(*args, **kwargs):
        run = advance(*args, **kwargs)
        process_return(o, run, 'guest_exit')
        o.session._on_machine_closed()
        run['process'] = deepcopy(o.session._process)
        run['session']['state'] = 'closed'
        del run['clock_budget']
        primary.result = run
        raise primary
    o.session._clock_advance_with_hooks = closed
    with pytest.raises(DebuggerError) as error:o.session.scene_wait(**options())
    assert error.value is primary and primary.result is o.runs[0]
    assert primary.result['outcome'] == 'guest_exit' and primary.result['process']['machine_closed']
    assert primary.result['process']['capture_epoch'] == 'source-run:process:3'
    assert len(o.runs) == 1 and not primary.scene_wait_result['wait']['clock_progress_complete']


def test_terminal_stop_without_clock_readback_preserves_known_prefix(scene_waiting):
    o = scene_waiting
    advance = o.session._clock_advance_with_hooks
    def stopped(*args, **kwargs):
        run = advance(*args, **kwargs)
        run.update(outcome='guest_exit')
        del run['clock_budget']
        return run
    o.session._clock_advance_with_hooks = stopped
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**options())
    wait = error.value.result['wait']
    assert wait['stop'] is o.runs[0] and wait['outcome'] == 'guest_exit'
    assert wait['guest_elapsed_ns'] == 0 and not wait['clock_progress_complete']
    assert len(o.runs) == 1


def test_virtual_overshoot_cannot_turn_a_late_match_into_success(scene_waiting):
    o = scene_waiting
    o.ready_after = 1
    advance = o.session._clock_advance_with_hooks
    def overshoot(delta_ns, **kwargs):
        return advance(delta_ns + 64, **kwargs)
    o.session._clock_advance_with_hooks = overshoot
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**dict(options(), guest_ms=10))
    result = error.value.result
    assert result['status'] == 'timeout' and not result['complete']
    assert result['scene_matched'] is True
    assert result['wait']['guest_elapsed_ns'] == 10_000_064
    assert result['wait']['guest_budget_overshoot_ms'] > 0 and len(o.runs) == 1


def test_unknown_binding_is_terminal_without_execution(scene_waiting):
    o = scene_waiting
    o.session._invalidate_runtime_bindings()
    before = len(o.reads)
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**options())
    assert error.value.result['status'] == 'unavailable' and not error.value.result['complete']
    assert not error.value.result['capture_context_verified']
    assert len(o.reads) == before and not o.runs and not o.closed


def test_unavailable_observation_without_context_keeps_original_failure(scene_waiting, monkeypatch):
    from fdisbull import qemu_scenes
    o = scene_waiting
    o.session._invalidate_runtime_bindings()
    observe = qemu_scenes._observe
    def unavailable(*args, **kwargs):
        result = observe(*args, **kwargs)
        assert result['status'] == 'unavailable'
        result.pop('observation_context')
        return result
    monkeypatch.setattr(qemu_scenes, '_observe', unavailable)
    with pytest.raises(SceneError) as error:o.session.scene_wait(**options())
    result = error.value.result
    assert result['status'] == 'unavailable' and result['wait']['outcome'] == 'unavailable'
    assert result['error'] == result['wait']['polls'][0]['error']
    assert o.project.debug_scene_observation(result['observation'])['result'] == result
    assert 'final_clock' not in result['wait'] and not o.runs


def test_ambiguous_companion_is_terminal_without_execution(scene_waiting):
    o = scene_waiting
    o.ram[2] = 0
    save(o, name='conflict')
    with pytest.raises(SceneError) as error:
        o.session.scene_wait(**options())
    assert error.value.result['status'] == 'ambiguous' and error.value.result['conflicts']
    assert not o.runs


@pytest.mark.parametrize('change', ['selected', 'companion', 'epoch'])
def test_changed_manifest_or_epoch_after_run_refuses_before_another_poll(scene_waiting, change):
    o = scene_waiting
    advance = o.session._clock_advance_with_hooks
    reads_at_stop = []
    def changed(*args, **kwargs):
        run = advance(*args, **kwargs)
        if change == 'epoch':
            o.session._runtime_epoch += ':new'
            o.session._process['capture_epoch'] = o.session._runtime_epoch
        elif change == 'selected':
            info = o.project.debug_scene_info('room')
            doc = deepcopy(info['definition'])
            doc['objects'][0]['name'] = 'changed'
            o.project.debug_save_scene('room', doc, parent=info['id'])
        else:save(o, name='added-companion')
        reads_at_stop.append(len(o.reads))
        return run
    o.session._clock_advance_with_hooks = changed
    with pytest.raises(ValueError, match='changed') as error:
        o.session.scene_wait(**options())
    assert error.value.scene_wait_result['wait']['runs'][0] is o.runs[0]
    assert len(o.runs) == 1 and len(o.reads) == reads_at_stop[0] and o.closed


def test_replacement_owner_is_never_locked_or_closed(scene_waiting):
    o, s = scene_waiting, scene_waiting.session
    owner = s.vm
    replacement = copy(owner)
    class ForeignLock:
        calls = 0
        def acquire(self, **kwargs):self.calls += 1;return True
        def release(self):pass
    replacement.lock = ForeignLock()
    replacement_closed = []
    replacement.close = lambda: replacement_closed.append(True)
    clock = s.clock_observe
    def changed():
        value = clock();s.vm = replacement;return value
    s.clock_observe = changed
    try:
        with pytest.raises(ValueError, match='owner'):
            s.scene_wait(**options())
        assert replacement.lock.calls == 0 and not replacement_closed and not o.runs
    finally:s.vm = owner


def test_inherited_deadline_is_one_bound_and_restored(scene_waiting):
    o, s = scene_waiting, scene_waiting.session
    now = time.monotonic()
    s._rpc_deadline, s._deadline = now + 2.5, now + 2
    s.vm.operation_deadline, o.peer.operation_deadline = now + 1.8, now + 1.5
    expected = (s._rpc_deadline, s._deadline, s.vm.operation_deadline, o.peer.operation_deadline)
    o.deadlines.clear()
    assert s.scene_wait(**options())['complete']
    assert o.deadlines and all(values == (expected[-1],) * 4 for values in o.deadlines)
    assert (s._rpc_deadline, s._deadline, s.vm.operation_deadline, o.peer.operation_deadline) == expected


def test_expired_deadline_refuses_before_any_native_read(scene_waiting):
    o = scene_waiting
    o.session._rpc_deadline = time.monotonic() - 1
    before = (len(o.reads), len(o.peer.qmp_calls))
    with pytest.raises(TimeoutError):o.session.scene_wait(**options())
    assert before == (len(o.reads), len(o.peer.qmp_calls)) and not o.runs


def test_lock_admission_consumes_same_deadline_before_observation(scene_waiting, monkeypatch):
    from fdisbull import qemu_scene_wait
    o = scene_waiting
    now = [time.monotonic()]
    monkeypatch.setattr(qemu_scene_wait.time, 'monotonic', lambda: now[0])
    class LateLock:
        requested = None
        released = False
        def acquire(self, *, timeout):
            self.requested = timeout
            now[0] += 4
            return True
        def release(self):self.released = True
    lock = LateLock()
    o.session.vm.lock = lock
    before = (len(o.reads), len(o.peer.qmp_calls))
    with pytest.raises(TimeoutError):o.session.scene_wait(**options())
    assert 0 < lock.requested <= 3 and lock.released
    assert before == (len(o.reads), len(o.peer.qmp_calls)) and not o.runs


def test_deadline_after_first_run_retains_prefix_and_closes_original_owner(scene_waiting, monkeypatch):
    from fdisbull import qemu_scene_wait
    o = scene_waiting
    now = [time.monotonic()]
    monkeypatch.setattr(qemu_scene_wait.time, 'monotonic', lambda: now[0])
    advance = o.session._clock_advance_with_hooks
    def late(*args, **kwargs):
        result = advance(*args, **kwargs);now[0] += 4;return result
    o.session._clock_advance_with_hooks = late
    with pytest.raises(TimeoutError) as error:o.session.scene_wait(**options())
    assert len(error.value.scene_wait_result['wait']['runs']) == len(o.runs) == 1
    assert error.value.scene_wait_result['wait']['guest_elapsed_ns'] == 10_000_000
    assert o.closed


def test_native_primary_error_is_not_replaced_by_wait_or_cleanup(scene_waiting):
    o = scene_waiting
    primary = OSError('authored native observation loss')
    primary.result = {'native_stop': 'T05thread:1;'}
    def failed(*args, **kwargs):raise primary
    o.session._clock_advance_with_hooks = failed
    def bad_close():raise RuntimeError('authored publication failure')
    o.session.close = bad_close
    with pytest.raises(OSError) as error:o.session.scene_wait(**options())
    assert error.value is primary and primary.result == {'native_stop': 'T05thread:1;'}
    assert primary.scene_wait_result['wait']['polls']
    assert not primary.scene_wait_result['wait']['clock_progress_complete']
    assert primary.scene_wait_cleanup_error == 'RuntimeError' and o.closed


def test_poll_and_evidence_bounds_end_before_another_execution(scene_waiting, monkeypatch):
    from fdisbull import qemu_scene_wait
    o = scene_waiting
    monkeypatch.setattr(qemu_scene_wait, 'MAX_POLLS', 1)
    with pytest.raises(SceneError) as error:o.session.scene_wait(**options())
    assert error.value.result['wait']['outcome'] == 'poll_budget' and not o.runs
    monkeypatch.setattr(qemu_scene_wait, 'MAX_POLLS', 1000)
    monkeypatch.setattr(qemu_scene_wait, 'MAX_EVIDENCE_BYTES', 1)
    with pytest.raises(ValueError, match='evidence budget') as error:o.session.scene_wait(**options())
    assert error.value.scene_wait_result['wait']['evidence_bytes'] > 1 and not o.runs


def test_final_evidence_bound_counts_the_full_stored_document(scene_waiting, monkeypatch):
    from fdisbull import qemu_scene_wait
    o = scene_waiting
    o.ram[2] = 0
    result = o.session.scene_wait(**options())
    raw = o.project.db.execute('SELECT document FROM debug_scene_observations WHERE id=?',
                              (result['observation'],)).fetchone()[0].encode()
    assert len(raw) == result['wait']['evidence_bytes']
    # The last observation appears at top level and in polls. Summing receipt
    # lengths would miss this duplication and incorrectly admit this limit.
    receipts = sum(len(encoded(p)) for p in result['wait']['polls'])
    limit = len(raw) - 1000
    assert receipts < limit
    monkeypatch.setattr(qemu_scene_wait, 'MAX_EVIDENCE_BYTES', limit)
    before = len(o.project.debug_scene_observations()['observations'])
    with pytest.raises(ValueError, match='evidence budget') as error:
        o.session.scene_wait(**options())
    partial = error.value.scene_wait_result
    assert partial['wait']['polls'] and not partial['complete'] and 'observation' not in partial
    assert len(o.project.debug_scene_observations()['observations']) == before
    assert not o.runs and not o.closed


def test_late_publication_keeps_stored_receipt_without_relabeling_it(scene_waiting, monkeypatch):
    from fdisbull import qemu_scene_wait
    o = scene_waiting
    original = qemu_scene_wait.store
    def late(session, result):
        saved = original(session, result)
        monkeypatch.setattr(qemu_scene_wait.time, 'monotonic', lambda: 10**12)
        return saved
    monkeypatch.setattr(qemu_scene_wait, 'store', late)
    with pytest.raises(TimeoutError) as error:o.session.scene_wait(**options())
    partial = error.value.scene_wait_result
    assert 'observation' not in partial and partial['retained_observation']
    saved = o.project.debug_scene_observation(partial['retained_observation'])['result']
    assert saved['status'] == 'matched' and saved['complete'] and saved['wait']['outcome'] == 'predicate'
    assert partial['status'] == 'unavailable' and partial['wait']['outcome'] == 'error'
    assert len(o.runs) == 2 and o.closed


def test_frozen_undo_refuses_wait_even_if_initially_matched(scene_waiting):
    o = scene_waiting
    o.ram[2] = 0
    o.session._qemu_cpu_delta_history = dict(frozen=True, valid=False)
    before = len(o.reads)
    with pytest.raises(ValueError, match='frozen'):
        o.session.scene_wait(**options())
    assert len(o.reads) == before and not o.runs
    assert o.session.scene_check('room')['status'] == 'unavailable'
    o.session.bind_runtime_memory('move-state', ADDRESS, length=4, expected_hex='4142',
        provenance='fresh selected frozen state witness', space='physical')
    assert o.session.scene_check('room')['status'] == 'matched'


def test_compact_result_retains_full_persisted_wait(scene_waiting):
    o = scene_waiting
    result = o.session.scene_wait(**dict(options(), compact=True))
    assert result['reply_format'] == 'fdisbull-scene-compact-1'
    assert result['wait']['polls_count'] == 3 and 'polls' not in result['wait']
    full = o.project.debug_scene_observation(result['observation'])['result']
    assert len(full['wait']['polls']) == 3 and full['wait']['polls'][0]['memory_captures']


def arm_fixed(o):
    s = o.session
    lease = s.keyboard_key_down('a')['lease']
    state = s._input_storage()
    records = deepcopy(state['pending'])
    state['schedule'] = dict(bound=True, token='authored-arm', start_ns=0, deadline_ns=20_000_000,
        records=records, applied_count=0, native=dict(state='armed', token='authored-arm',
            **{'start-ns': 0, 'virtual-ns': 0, 'event-count': len(records)}))
    s.input_schedule_observe = lambda: {'observed_ns': o.now}
    return lease


def test_fixed_arm_uses_one_full_first_slice_and_keeps_held_lease(scene_waiting):
    o = scene_waiting
    o.ready_after = 1
    # This case waits for the authored state byte while retaining a held key;
    # the movement fixture's separate "released" byte is deliberately false.
    info = o.project.debug_scene_info('room')
    doc = deepcopy(info['definition'])
    doc['objects'][0]['ready'] = {'constant': True}
    o.project.debug_save_scene('room', doc, parent=info['id'])
    lease = arm_fixed(o)
    advance = o.session._clock_advance_with_hooks
    def delivered(*args, **kwargs):
        run = advance(*args, **kwargs)
        run['input_delivery'] = dict(token='authored-arm', state='dispatched', requires_resolution=False)
        return run
    o.session._clock_advance_with_hooks = delivered
    result = o.session.scene_wait(**options())
    assert result['wait']['input_plan']['effective_first_slice_ns'] == 30_000_000
    assert result['wait']['guest_elapsed_ns'] == 30_000_000 and len(o.runs) == 1
    assert lease in o.session.input_state()['leases']
    assert not result['wait']['input_plan']['release'] and len(o.deliveries) == 1


def test_immediate_match_leaves_fixed_arm_completely_undispatched(armed_scene_wait):
    o = armed_scene_wait
    calls = len(o.wire.calls)
    result = initial_match_preserves_arm(o.session, lambda: o.session.scene_wait(**options()))
    assert not o.runs and not o.deliveries and not o.writes and not o.closed
    commands = [name for name, _ in o.wire.calls[calls:]]
    assert commands.count('x-fdisbull-query-input') == 1
    assert set(commands) == {'query-status', 'query-replay', 'x-fdisbull-query-clock',
                             'x-fdisbull-query-input'}
    assert o.project.debug_scene_observation(result['observation'])['result'] == result


@pytest.mark.parametrize('fault', ['token', 'queue', 'cursor', 'native-clock'])
def test_initial_match_revalidates_native_arm_before_reading_predicates(armed_scene_wait, fault):
    o = armed_scene_wait
    state = o.session._input_storage()
    def changed(value):
        if fault == 'token':value['token'] = 'unowned-token'
        elif fault == 'queue':state['pending'][0]['sequence'] += 1
        elif fault == 'cursor':
            state['schedule']['applied_count'] = 1
            state['pending'] = deepcopy(state['schedule']['records'][1:])
        else:value['virtual-ns'] += 1
        return value
    o.wire.mutate = changed
    reads = len(o.reads)
    with pytest.raises(DebuggerError) as error:o.session.scene_wait(**options())
    assert error.value.scene_wait_result['wait']['polls'] == []
    assert len(o.reads) == reads and not o.runs and not o.deliveries and not o.writes
    assert o.closed and not state['valid']


@pytest.mark.parametrize('field', ['host_monotonic_ns', 'sequence'])
@pytest.mark.parametrize('fault', ['boolean', 'regressed'])
def test_initial_match_oracle_rejects_invalid_receipt_telemetry(armed_scene_wait, field, fault):
    o, s = armed_scene_wait, armed_scene_wait.session
    original = s.input_schedule_observe
    before = s.input_state()['schedule']['clock'][field]
    def invalid_telemetry():
        result = original()  # Real native receipt validation and owned-state refresh.
        value = True if fault == 'boolean' else before - 1
        result['clock'][field] = value
        s._input_storage()['schedule_receipt']['clock'][field] = value
        return result
    s.input_schedule_observe = invalid_telemetry
    # Fault only the observation metadata after its real validation. The wait
    # completes and persists; this tests the acceptance oracle, not a claimed
    # production rejection of impossible host clock samples.
    count = len(o.project.debug_scene_observations()['observations'])
    with pytest.raises(AssertionError, match=field):
        initial_match_preserves_arm(s, lambda: s.scene_wait(**options()))
    assert len(o.project.debug_scene_observations()['observations']) == count + 1
    assert not o.runs and not o.deliveries and not o.writes and not o.closed


@pytest.mark.parametrize('fault', ['partial', 'uncertain', 'motion', 'insufficient-budget'])
def test_invalid_or_partial_input_arm_refuses_without_reads_or_effects(scene_waiting, fault):
    o = scene_waiting
    arm_fixed(o)
    state = o.session._input_storage()
    kwargs = options()
    if fault == 'partial':state['schedule']['applied_count'] = 1
    elif fault == 'uncertain':state['valid'] = False
    elif fault == 'motion':state['schedule']['motion'] = {}
    else:kwargs['guest_ms'] = 30
    before = (len(o.reads), len(o.peer.qmp_calls), deepcopy(state))
    with pytest.raises(ValueError):o.session.scene_wait(**kwargs)
    assert (len(o.reads), len(o.peer.qmp_calls), state) == before
    assert not o.runs and not o.deliveries and not o.closed


def test_interrupted_input_stop_never_reads_a_now_true_predicate(scene_waiting):
    o = scene_waiting
    o.ready_after = 1
    lease = arm_fixed(o)
    advance = o.session._clock_advance_with_hooks
    def interrupted(*args, **kwargs):
        run = advance(*args, **kwargs)
        run['input_delivery'] = dict(token='authored-arm', state='cancelled', requires_resolution=True)
        return run
    o.session._clock_advance_with_hooks = interrupted
    with pytest.raises(SceneError) as error:o.session.scene_wait(**options())
    wait = error.value.result['wait']
    assert wait['outcome'] == 'input_interrupted' and wait['stop'] is o.runs[0]
    assert len(wait['polls']) == len(o.runs) == 1 and lease in o.session.input_state()['leases']
    assert not o.closed
