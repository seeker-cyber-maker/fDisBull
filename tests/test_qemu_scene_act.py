"""Named keyboard actions through real storage and public QEMU contracts.

Host tests supply authored QMP/GDB boundaries; they do not qualify a live VM.
"""
from copy import copy, deepcopy
from functools import wraps
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
from fdisbull.scenes import SceneError, encoded
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_qemu_movement import moving
from test_qemu_scenes import save, definition
from test_qemu_keyboard_press import ARM, PressWire


def action_definition():
    doc = definition()
    doc.update(format='fdisbull-scene-3', action_profile=dict(kind='qemu-virtual-keyboard', version=1))
    doc['objects'][0].update(action=dict(kind='press', key='a', modifiers=[], hold_ms=20, gap_ms=40),
        guest_ms=100, timeout_ms=3000,
        outcome={'compare':dict(left={'runtime_memory':dict(binding='move-state',offset=2,type='u8')},op='ge',right=1)})
    return doc


@pytest.fixture
def acting(moving):
    """Real stopped RAM/input validation; authored native clock/callback stop.

    QMP envelope/press/prefix ownership and FDB are production code. Only the
    stopped GDB peer, native callback progress, and selected RAM transition are
    authored; no VM or device consumption is claimed by these host checks.
    """
    o, s = moving, moving.session
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
    o.info = save(o, action_definition())
    o.reads_at_stop = None
    o.effect_after = 1
    o.later_delivery = True
    o.timer_partial = False
    def advance(delta_ns, *, timeout_ms):
        assert delta_ns > 0 and timeout_ms > 0
        clock = s.clock_observe()
        begin = o.wire.receipt['virtual-ns']
        interrupted = o.stop_on == len(o.runs) + 1
        finish = begin + (2_000_000 if interrupted and not o.timer_partial else delta_ns)
        if o.wire.input['state'] == 'armed':
            o.wire.stop_after(1 if interrupted else len(o.wire.input['press']['steps']),
                lateness=delta_ns-12_000_000 if o.timer_partial else 0, stopped_ns=finish)
        else:
            o.wire.receipt['virtual-ns'] = finish
        o.wire.counter += 1
        delivery = s.input_schedule_observe()
        if o.progress and len(o.runs) + 1 >= o.effect_after:
            o.ram[2], o.ram[3] = 1, 0
        result = dict(outcome='breakpoint' if interrupted else 'stopped', timed_out=False,
            clock_budget=dict(epoch=clock['epoch'],start_ns=begin,stopped_ns=finish,deadline_reached=not interrupted),
            input_delivery=delivery,
            session=dict(state='stopped',stop_reason=dict(kind='breakpoint' if interrupted else 'stopped',
                breakpoint_ids=[7] if interrupted else [],native_reply='T05thread:1;' if interrupted else 'T02thread:1;')))
        if o.runs and not o.later_delivery:
            result.pop('input_delivery')
        o.runs.append(result)
        o.reads_at_stop = len(o.reads)
        return result
    s._clock_advance_with_hooks = advance
    return o


def options(**changes):
    return dict(scene='room', object='actor', slice_ms=10, **changes)


def request(o, method='debug-scene-act', **params):
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        return respond(dict(method=method, params=dict(project=str(o.project.path),
            run=o.session.run_id, **params)), debugger=workspace)
    finally:
        workspace.sessions.clear()


def arm_count(o):
    return sum(name == ARM for name, _ in o.wire.calls)


def assert_stored(o, result):
    stored = o.project.db.execute('SELECT document FROM debug_scene_observations WHERE id=?',
                                (result['observation'],)).fetchone()[0]
    assert json.loads(stored) == {key:value for key,value in result.items() if key != 'observation'}
    assert len(stored.encode()) == result['action_wait']['evidence_bytes']
    with Project(o.project.path) as reopened:
        assert reopened.debug_scene_observation(result['observation'])['result'] == result


def test_action_arms_once_then_observes_destination_without_old_readiness(acting):
    o, s = acting, acting.session
    result = s.scene_act(**options())
    assert result['status'] == 'matched' and result['complete']
    assert result['before']['status'] == 'matched' and result['before']['initial_outcome'] is False
    assert result['input']['attempted'] and result['input']['accepted'] and result['input']['completed']
    assert result['input']['device_queue_accepted'] is result['input']['guest_consumed'] is None
    assert result['effect']['matched'] is True and result['effect']['observation']['outcome'] is True
    assert result['effect']['observation']['availability'] == {}
    assert o.ram[2:4] == b'\x01\x00'  # The old scene/readiness are now both false.
    assert arm_count(o) == len(o.runs) == len(result['action_wait']['polls']) == 1
    assert result['action_wait']['guest_elapsed_ns'] == 32_000_000
    assert result['intention']['consumed'] and not result['intention']['replay']
    plan = dict(result['plan']); pin = plan.pop('sha256')
    assert pin == hashlib.sha256(encoded(plan)).hexdigest()
    assert plan['press'] == o.info['definition']['objects'][0]['action']
    assert not s.input_state()['leases'] and not s._input_pending() and not o.closed
    assert_stored(o, result)


def test_first_stop_preserves_input_prefix_and_never_reads_effect(acting):
    o = acting; o.stop_on = 1
    with pytest.raises(SceneError) as caught:
        o.session.scene_act(**options())
    result = caught.value.result
    assert result['status'] == 'stopped' and not result['complete']
    assert result['input']['accepted'] is True and result['input']['completed'] is False
    assert result['input']['delivery']['press']['dispatched_count'] == 1
    assert result['effect']['matched'] is result['effect']['observation'] is None
    assert result['action_wait']['stop'] is o.runs[0] and result['action_wait']['polls'] == []
    assert len(o.reads) == o.reads_at_stop
    assert arm_count(o) == len(o.runs) == 1 and o.session.input_state()['leases'] and not o.closed
    assert_stored(o, result)


def test_valid_partial_press_at_ordinary_timer_stop_retains_holds(acting):
    o = acting; o.stop_on = 1; o.timer_partial = True
    advance = o.session._clock_advance_with_hooks
    def timer(*args, **kwargs):
        result = advance(*args, **kwargs)
        result['outcome'] = 'stopped'
        result['clock_budget']['deadline_reached'] = True
        result['session']['stop_reason'].update(kind='stopped',breakpoint_ids=[],native_reply='T02thread:1;')
        return result
    o.session._clock_advance_with_hooks = timer
    with pytest.raises(SceneError) as caught:
        o.session.scene_act(**options())
    result = caught.value.result
    assert result['status'] == 'stopped' and result['action_wait']['input_interrupted'] is True
    assert result['input']['accepted'] is True and result['input']['completed'] is False
    assert result['action_wait']['guest_elapsed_ns'] == 32_000_000
    assert result['input']['delivery']['press']['steps'][0]['dispatch_ns'] == 22_000_000
    assert result['action_wait']['stop'] is o.runs[0] and result['action_wait']['polls'] == []
    assert len(o.reads) == o.reads_at_stop and o.session.input_state()['leases'] and not o.closed
    assert_stored(o, result)


@pytest.mark.parametrize('reason', ['not-ready', 'already-matched'])
def test_initial_refusals_leave_input_owner_and_clock_untouched(acting, reason):
    o = acting
    if reason == 'not-ready':
        o.ram[3] = 0
    else:
        doc = action_definition(); doc['objects'][0]['outcome'] = {'constant':True}
        o.project.debug_save_scene('room', doc, parent=o.info['id'])
    before = deepcopy(o.session.input_state())
    process = deepcopy(o.session._process)
    with pytest.raises(SceneError) as caught:
        o.session.scene_act(**options())
    result = caught.value.result
    assert result['status'] == ('mismatch' if reason == 'not-ready' else 'outcome-already-matched')
    assert result['input']['attempted'] is result['input']['accepted'] is False
    assert result['action_wait']['guest_elapsed_ns'] == 0 and result['action_wait']['polls'] == []
    assert o.session.input_state() == before and o.session._process == process
    assert not arm_count(o) and not o.runs and not o.closed
    assert_stored(o, result)


def test_delayed_outcome_keeps_completed_delivery_without_a_later_receipt(acting):
    o = acting; o.effect_after = 3; o.later_delivery = False
    result = o.session.scene_act(**options())
    assert result['complete'] and result['input']['completed'] is True
    assert result['action_wait']['guest_elapsed_ns'] == 52_000_000
    assert [poll['outcome'] for poll in result['action_wait']['polls']] == [False, False, True]
    assert arm_count(o) == 1 and len(o.runs) == 3
    assert_stored(o, result)


def test_false_destination_times_out_at_measured_budget_without_rearming(acting):
    o = acting; o.progress = False
    with pytest.raises(SceneError) as caught:
        o.session.scene_act(**options(guest_ms=42))
    result = caught.value.result
    assert result['status'] == 'timeout' and result['input']['completed'] is True
    assert result['effect']['matched'] is False
    assert result['action_wait']['guest_elapsed_ns'] == 42_000_000
    assert result['action_wait']['guest_budget_overshoot_ms'] == 0
    assert arm_count(o) == 1 and len(o.runs) == 2 and not o.closed
    assert_stored(o, result)


def test_public_json_success_preserves_full_canonical_projection(acting):
    o = acting
    captured = []
    original = o.session.scene_act
    @wraps(original)
    def capture(*args, **kwargs):
        result = original(*args, **kwargs); captured.append(result); return result
    o.session.scene_act = capture
    before_advance = o.session._clock_advance_with_hooks
    def process(*args, **kwargs):
        result = before_advance(*args, **kwargs)
        result['process'] = dict(state='active', allocation=dict(start=0x18000,end=0x28000),
            drivers=dict(headers=[dict(address=0xa000,name='CON')]))
        return result
    o.session._clock_advance_with_hooks = process
    reply = request(o, **options())
    assert reply['ok'], reply
    assert len(captured) == 1 and reply['result'] == public_addresses(captured[0])
    raw_process = captured[0]['action_wait']['runs'][0]['process']
    public_process = reply['result']['action_wait']['runs'][0]['process']
    assert type(raw_process['allocation']['start']) is int
    assert public_process['allocation']['start'] == hex(raw_process['allocation']['start'])
    assert public_process['drivers']['headers'][0]['address'] == hex(raw_process['drivers']['headers'][0]['address'])
    assert_stored(o, captured[0])
    assert arm_count(o) == len(o.runs) == 1


def test_json_first_stop_is_canonical_and_never_serializes_a_second_action(acting):
    o = acting; o.stop_on = 1
    reply = request(o, **options())
    assert not reply['ok'] and reply['error']['type'] == 'SceneError', reply
    result = reply['error']['result']
    assert result['status'] == 'stopped' and result['effect']['matched'] is None
    assert result['action_wait']['stop'] == o.runs[0]
    assert len(o.reads) == o.reads_at_stop and not o.closed
    assert_stored(o, result)
    assert arm_count(o) == len(o.runs) == 1


def script(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=list(steps))


def test_prior_write_canary_is_a_real_valid_script_effect(acting):
    o = acting
    result = o.session.script(script(dict(op='write-memory',address=ADDRESS+2,data_hex='09',expected_hex='00')))
    assert result['ok'] and o.ram[2] == 9 and o.writes == [(ADDRESS+2,b'\x09','physical')]


def test_saved_script_id_dispatches_one_action_and_retains_exact_report(acting):
    o = acting
    route = script(dict(op='scene-act', **options(), **{'as':'action'}),
                   dict(op='assert',value='$action.input.completed',equals=True),
                   dict(op='assert',value='$action.effect.matched',equals=True))
    saved = o.project.debug_save_script('action.json', route)
    result = o.session.script(script_id=saved['script_id'])
    assert result['ok'] and result['completed_steps'] == 3, result
    assert_stored(o, result['steps'][0]['result'])
    raw = o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (result['artifact'],)).fetchone()[0]
    assert json.loads(raw) == {key:value for key,value in result.items() if key != 'artifact'}
    assert arm_count(o) == len(o.runs) == 1


def test_script_first_stop_preserves_owned_hold_and_action_error(acting):
    o = acting; o.stop_on = 1
    result = o.session.script(script(dict(op='scene-act', **options()),
        dict(op='write-memory',address=ADDRESS+2,data_hex='09',expected_hex='01')))
    assert not result['ok'] and result['completed_steps'] == 0
    assert result['steps'][0]['error']['type'] == 'SceneError'
    assert result['steps'][0]['result']['status'] == 'stopped'
    assert result['input_cleanup'] is None and o.session.input_state()['leases'] and not o.closed
    assert not o.writes and arm_count(o) == len(o.runs) == 1


@pytest.mark.parametrize('change', [dict(compact=1),dict(handle_popups=True),dict(guest_ms=True),
    dict(timeout_ms=True),dict(timeout_ms=60001),dict(slice_ms=0),dict(object=None),dict(guest_ms=32)])
def test_literal_invalid_action_precedes_prior_script_ram_write(acting, change):
    o = acting
    chosen = dict(options(), **change)
    with pytest.raises((ValueError, TypeError)):
        o.session.script(script(dict(op='write-memory', address=ADDRESS+2,data_hex='09',expected_hex='00'),
                               dict(op='scene-act', **chosen)))
    assert not o.writes and not o.runs and not arm_count(o) and not o.closed


@pytest.mark.parametrize('value', [True,0,60001,'bad'])
def test_resolved_timeout_is_validated_before_remaining_budget_clamp(acting, value):
    o = acting
    # Resolve from an authored script binding; the public production dispatcher
    # still performs declaration validation before its remaining-time clamp.
    from fdisbull.debug_script import execute_script
    route = script(dict(op='scene-act',**options(timeout_ms='$bound.value')))
    result = execute_script(o.session,route,bindings={'bound':{'value':value}})
    assert not result['ok'] and result['steps'][0]['error']['type'] == 'ValueError'
    assert not o.runs and not arm_count(o) and not o.closed


@pytest.mark.parametrize('owner_kind', ['held','pending','invalid','frame-empty','frame-held'])
def test_preexisting_input_refuses_before_script_effects_without_taking_ownership(acting, owner_kind):
    o, s = acting, acting.session
    if owner_kind in ('held','pending'):
        lease = s.keyboard_key_down('a')['lease']
        if owner_kind == 'held':
            state = s._input_storage()
            s._input_mark_dispatched(state, deepcopy(state['pending']), 'qmp_accepted')
            assert lease in state['leases']
    elif owner_kind == 'invalid':
        s._input_storage()['valid'] = False
    else:
        s.vm._frame_key_owner = dict(token='other', keys=[] if owner_kind=='frame-empty' else ['a'])
    before = deepcopy(getattr(s.vm,'_physical_input',None))
    frame = getattr(s.vm,'_frame_key_owner',None)
    with pytest.raises(ValueError):
        s.script(script(dict(op='write-memory',address=ADDRESS+2,data_hex='09',expected_hex='00'),
                        dict(op='scene-act',**options())))
    assert getattr(s.vm,'_physical_input',None) == before and getattr(s.vm,'_frame_key_owner',None) is frame
    assert not o.writes and not o.runs and not arm_count(o) and not o.closed


def test_scene_three_is_passive_for_check_but_refused_by_wait_before_script_effects(acting):
    o = acting
    assert o.session.scene_check('room',object='actor')['status'] == 'matched'
    with pytest.raises(ValueError, match='scene-2'):
        o.session.scene_wait('room',object='actor')
    with pytest.raises(ValueError, match='scene-2'):
        o.session.script(script(dict(op='write-memory',address=ADDRESS+2,data_hex='09',expected_hex='00'),
                               dict(op='scene-wait',scene='room',object='actor')))
    assert not o.writes and not o.runs and not arm_count(o)


@pytest.mark.parametrize('route', ['python','json','script'])
def test_primary_runtime_error_keeps_native_result_and_separate_action_prefix(acting, route):
    o = acting
    error = RuntimeError('authored callback failed after accepting the arm')
    error.result = {'native_stop':'retained first evidence'}
    def broken(*args, **kwargs):
        raise error
    o.session._clock_advance_with_hooks = broken
    if route == 'python':
        with pytest.raises(RuntimeError) as caught:
            o.session.scene_act(**options())
        assert caught.value is error
        observed, prefix = error.result, error.scene_act_result
    elif route == 'json':
        reply = request(o, **options())
        assert not reply['ok'] and reply['error']['type'] == 'RuntimeError'
        observed, prefix = reply['error']['result'], reply['error']['scene_act_result']
    else:
        report = o.session.script(script(dict(op='scene-act', **options())))
        assert not report['ok'] and report['completed_steps'] == 0
        record = report['steps'][0]
        assert record['error']['type'] == 'RuntimeError'
        observed, prefix = record['result'], record['scene_act_result']
    assert observed == {'native_stop':'retained first evidence'}
    assert prefix['input']['attempted'] and prefix['input']['accepted'] is True
    assert prefix['input']['completed'] is None and prefix['effect']['matched'] is None
    assert prefix['action_wait']['clock_progress_complete'] is False
    assert arm_count(o) == 1 and not o.runs and o.closed
    assert o.project.db.execute('SELECT count(*) FROM debug_scene_observations').fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['arm','arm-journal','native-validation'])
def test_arm_primary_error_survives_failed_owner_cleanup(acting, failure):
    o, s = acting, acting.session
    original_event = s._event
    if failure == 'arm':
        o.wire.reject_arm = True
        expected = DebuggerError
    elif failure == 'arm-journal':
        def journal(operation, value):
            if operation == 'input.schedule-arm':
                raise OSError('authored arm journal failure')
            return original_event(operation, value)
        s._event = journal
        expected = OSError
    else:
        o.wire.mutate = lambda value: dict(value, **{'event-count':999}) if value['state']=='armed' else value
        expected = DebuggerError
    def failed_close():
        o.closed.append(True)
        raise RuntimeError('secondary close failure')
    s.vm.close = failed_close
    with pytest.raises(expected) as caught:
        s.scene_act(**options())
    error = caught.value
    assert error.input_cleanup_error == 'RuntimeError'
    assert error.scene_act_result['input']['attempted'] is True
    assert error.scene_act_result['input']['accepted'] is None
    assert error.scene_act_result['effect']['matched'] is None
    assert not o.runs and arm_count(o) == 1 and o.closed


@pytest.mark.parametrize('when', ['passive-query','press-context','arm','schedule-query'])
def test_owner_swap_with_malformed_native_reply_never_closes_foreign_machine(acting, when):
    from fdisbull.qemu_machine import QemuMachine
    o, s = acting, acting.session
    original = s.vm
    original._close_started = False
    original.process.stdin = original.process.stdout = None
    original.process.poll = lambda:0 if original._close_started else None
    original.close_observer = s._on_machine_closed
    o.peer.close = lambda:setattr(o.peer,'socket',None)
    def real_close():
        o.closed.append(True);original._close_started=True;QemuMachine.close(original)
    original.close = real_close
    replacement = copy(original)
    foreign_closes = []
    replacement.qmp = SimpleNamespace(socket=object(),operation_deadline=None)
    replacement.gdb = SimpleNamespace(socket=object(),operation_deadline=None)
    replacement.close = lambda: foreign_closes.append(True)
    replacement._physical_input = dict(session_id='foreign',valid=True,pending=[],leases={})
    foreign_state = deepcopy(replacement._physical_input)
    process, epoch, closed = deepcopy(s._process), s._runtime_epoch, s.closed
    if when=='press-context':
        context=s._input_schedule_context;contexts=[]
        def changed_context():
            result=context();contexts.append(True)
            if len(contexts)==3:s.vm=replacement
            return result
        s._input_schedule_context=changed_context
    call = original.qmp.call
    def switched(command, arguments=None, **kwargs):
        value = call(command, arguments, **kwargs)
        selected = (command == ARM if when=='arm' else
                    command=='x-fdisbull-query-input' if when in ('passive-query','schedule-query') else False)
        if selected:
            s.vm = replacement
            return {'malformed':'must never reach replacement validation'}
        return value
    if when == 'schedule-query':
        s.keyboard_press('a',hold_ms=20,gap_ms=40)
    original.qmp.call = switched
    with pytest.raises(ValueError, match='owner changed'):
        if when == 'schedule-query':
            s.input_schedule_observe()
        else:
            s.scene_act(**options())
    assert s.vm is replacement and not foreign_closes
    assert replacement.lock is original.lock  # Same stable lock is not owner identity.
    assert replacement.qmp.socket is not None and replacement.gdb.socket is not None
    assert replacement._physical_input == foreign_state
    assert not hasattr(replacement,'_fdisbull_control_quarantine')
    assert s._process == process and s._runtime_epoch == epoch and s.closed is closed
    assert original._physical_input_closed and not original._physical_input['valid']
    assert o.closed
    s.vm = original


def test_manifest_change_during_readiness_refuses_the_pinned_plan(acting):
    o = acting
    def revise():
        doc = action_definition(); doc['objects'][0]['action']['key'] = 'b'
        o.project.debug_save_scene('room',doc,parent=o.info['id'])
    o.after_read = revise
    with pytest.raises(ValueError, match='manifest changed') as caught:
        o.session.scene_act(**options())
    prefix = caught.value.scene_act_result
    assert prefix['plan']['manifest_sha256'] == o.info['sha256']
    assert prefix['input']['attempted'] is False and not arm_count(o) and not o.runs


def test_readiness_fence_refuses_new_frame_owner_without_detaching_it(acting):
    o = acting; frame = {'token':'new-frame','keys':[]}
    o.after_read = lambda: setattr(o.session.vm,'_frame_key_owner',frame)
    with pytest.raises(ValueError, match='frame-key'):
        o.session.scene_act(**options())
    assert o.session.vm._frame_key_owner is frame
    assert not arm_count(o) and not o.runs and not o.closed


def test_final_native_input_fence_refuses_a_late_empty_frame_owner(acting):
    o=acting;frame={'token':'late-frame','keys':[]};call=o.session.vm.qmp.call;queries=[]
    def changed(command,arguments=None,**kwargs):
        result=call(command,arguments,**kwargs)
        if command=='x-fdisbull-query-input':
            queries.append(True)
            if len(queries)==2:o.session.vm._frame_key_owner=frame
        return result
    o.session.vm.qmp.call=changed
    with pytest.raises(ValueError,match='frame-key'):
        o.session.scene_act(**options())
    assert o.session.vm._frame_key_owner is frame and len(queries)==2
    assert not arm_count(o) and not o.runs and not o.closed


def test_reentrant_attempt_cannot_consume_the_outer_intention_twice(acting):
    o = acting; nested = []
    def reenter():
        with pytest.raises(ValueError, match='already in progress') as caught:
            o.session.scene_act(**options())
        nested.append(caught.value.scene_act_result)
    o.after_read = reenter
    result = o.session.scene_act(**options())
    assert result['complete'] and len(nested) == 1
    assert nested[0]['attempt_id'] != result['attempt_id'] and not nested[0]['intention']['consumed']
    assert arm_count(o) == len(o.runs) == 1
    assert not hasattr(o.session.vm,'_scene_act_intention')


def test_original_deadline_includes_preflight_and_keeps_storage_unstarted(acting, monkeypatch):
    from fdisbull import qemu_scene_act
    o = acting; clock = SimpleNamespace(now=time.monotonic())
    monkeypatch.setattr(time,'monotonic',lambda:clock.now)
    preflight = qemu_scene_act.preflight
    def slow(*args, **kwargs):
        result = preflight(*args, **kwargs); clock.now += .050; return result
    monkeypatch.setattr(qemu_scene_act,'preflight',slow)
    with pytest.raises(TimeoutError):
        o.session.scene_act(**options(timeout_ms=20))
    assert not arm_count(o) and not o.runs and not o.closed
    assert o.project.db.execute('SELECT count(*) FROM debug_scene_observations').fetchone()[0] == 0


def test_owner_is_captured_before_preflight_even_with_same_lock(acting, monkeypatch):
    from fdisbull import qemu_scene_act
    o, s = acting, acting.session; original = s.vm
    replacement = copy(original)
    preflight = qemu_scene_act.preflight
    def replaced(*args, **kwargs):
        result = preflight(*args, **kwargs); s.vm = replacement; return result
    monkeypatch.setattr(qemu_scene_act,'preflight',replaced)
    with pytest.raises(ValueError, match='during preflight'):
        s.scene_act(**options())
    assert not arm_count(o) and not o.runs and not o.closed
    s.vm = original


def test_independent_inherited_bounds_are_intersected_and_restored(acting):
    o, s = acting, acting.session; now = time.monotonic()
    s._rpc_deadline, s._deadline = now+8, now+7
    s.vm.operation_deadline = now+6
    s.vm.qmp.operation_deadline, o.peer.operation_deadline = now+1.5, now+5
    before = (s._rpc_deadline,s._deadline,s.vm.operation_deadline,s.vm.qmp.operation_deadline,o.peer.operation_deadline)
    result = s.scene_act(**options())
    assert result['complete']
    assert (s._rpc_deadline,s._deadline,s.vm.operation_deadline,s.vm.qmp.operation_deadline,o.peer.operation_deadline) == before
    assert all(all(value <= before[3] for value in limits if value is not None) for limits in o.deadlines[1:])


@pytest.mark.parametrize('readiness', [False, True])
def test_action_publication_failure_preserves_primary_and_closes_only_after_input(acting, monkeypatch, readiness):
    from fdisbull import qemu_scene_act
    o = acting
    if not readiness:o.ram[3]=0
    error = OSError('authored final observation publication failure')
    def failed(*args, **kwargs):raise error
    monkeypatch.setattr(qemu_scene_act,'store',failed)
    with pytest.raises(OSError) as caught:
        o.session.scene_act(**options())
    assert caught.value is error and bool(o.closed) is readiness
    assert error.scene_act_result['input']['attempted'] is readiness
    assert arm_count(o) == int(readiness)
    assert o.project.db.execute('SELECT count(*) FROM debug_scene_observations').fetchone()[0] == 0


def test_late_persisted_receipt_is_retained_once_without_late_success(acting, monkeypatch):
    from fdisbull import qemu_scene_act
    o = acting; clock = SimpleNamespace(now=time.monotonic()); calls=[]
    monkeypatch.setattr(time,'monotonic',lambda:clock.now)
    store = qemu_scene_act.store
    def slow_store(*args, **kwargs):
        result=store(*args,**kwargs);calls.append(result);clock.now+=10;return result
    monkeypatch.setattr(qemu_scene_act,'store',slow_store)
    with pytest.raises(TimeoutError) as caught:
        o.session.scene_act(**options())
    prefix=caught.value.scene_act_result
    assert len(calls)==1 and prefix['retained_observation']==calls[0]['observation']
    assert not prefix['complete'] and calls[0]['complete'] and o.closed
    assert_stored(o,calls[0])


@pytest.mark.parametrize('changed', ['epoch','manifest'])
def test_post_store_authority_change_retains_committed_receipt_as_failure(acting,monkeypatch,changed):
    from fdisbull import qemu_scene_act
    o=acting;store=qemu_scene_act.store;calls=[]
    def changed_store(*args,**kwargs):
        result=store(*args,**kwargs);calls.append(result)
        if changed=='epoch':o.session._advance_epoch()
        else:
            doc=action_definition();doc['objects'][0]['action']['key']='b'
            o.project.debug_save_scene('room',doc,parent=o.info['id'])
        return result
    monkeypatch.setattr(qemu_scene_act,'store',changed_store)
    with pytest.raises(ValueError,match='changed') as caught:
        o.session.scene_act(**options())
    assert len(calls)==1 and caught.value.scene_act_result['retained_observation']==calls[0]['observation']
    assert not caught.value.scene_act_result['complete'] and calls[0]['complete'] and o.closed
    assert_stored(o,calls[0])


def test_oversized_observed_run_keeps_bounded_honest_prefix_and_primary(acting):
    from fdisbull.qemu_scene_act import MAX_EVIDENCE_BYTES
    o=acting;advance=o.session._clock_advance_with_hooks
    def large(*args, **kwargs):
        result=advance(*args,**kwargs);result['authored_extra']='x'*MAX_EVIDENCE_BYTES;return result
    o.session._clock_advance_with_hooks=large
    with pytest.raises(ValueError,match='8 MiB') as caught:
        o.session.scene_act(**options())
    prefix=caught.value.scene_act_result
    assert len(encoded(prefix))<=MAX_EVIDENCE_BYTES
    assert not prefix['complete'] and prefix['evidence_omissions']
    assert prefix['input']['accepted'] is True and prefix['input']['completed'] is True
    assert not prefix['action_wait']['polls'] and o.closed


@pytest.mark.parametrize('terminal', ['guest_exit','guest_tsr'])
def test_authentic_terminal_epoch_change_preserves_first_stop_before_effect(acting,terminal):
    from test_qemu_scene_wait import process_return
    o=acting;advance=o.session._clock_advance_with_hooks;epoch=o.session._runtime_epoch
    def returned(*args,**kwargs):
        run=advance(*args,**kwargs);process_return(o,run,terminal);return run
    o.session._clock_advance_with_hooks=returned
    with pytest.raises(SceneError) as caught:
        o.session.scene_act(**options())
    result=caught.value.result
    assert result['status']=='stopped' and result['action_wait']['stop'] is o.runs[0]
    assert result['effect']['matched'] is result['effect']['observation'] is None
    assert not result['action_wait']['polls'] and len(o.reads)==o.reads_at_stop
    assert o.session._runtime_epoch != epoch and not o.closed
    assert_stored(o,result)


def test_timeline_gate_wait_intersects_tighter_transport_deadline(acting,monkeypatch):
    from fdisbull.debug_timeline import FrameTimelineSessionMixin
    o=acting;clock=SimpleNamespace(now=time.monotonic())
    monkeypatch.setattr(time,'monotonic',lambda:clock.now)
    class Gate:
        requested=None
        released=False
        def acquire(self,*,timeout):
            self.requested=timeout;clock.now+=.050;return True
        def release(self):self.released=True
    gate=Gate()
    monkeypatch.setattr(FrameTimelineSessionMixin,'_timeline_gate',lambda self:gate)
    o.session.vm.qmp.operation_deadline=clock.now+.020
    before=(len(o.reads),len(o.wire.calls))
    with pytest.raises(TimeoutError):o.session.scene_act(**options())
    assert 0<gate.requested<=.020000001 and gate.released
    assert before==(len(o.reads),len(o.wire.calls)) and not arm_count(o) and not o.closed


@pytest.mark.parametrize('failed', [False,True])
def test_bounded_json_export_preserves_entire_receipt_without_replay(acting,tmp_path,failed):
    o=acting;captured=[];original=o.session.scene_act
    if failed:o.stop_on=1
    @wraps(original)
    def capture(*args,**kwargs):
        try:result=original(*args,**kwargs)
        except SceneError as error:
            captured.append(deepcopy(error.result));raise
        captured.append(deepcopy(result));return result
    o.session.scene_act=capture
    with output_policy_context(OutputPolicy(max_inline_bytes=4096,artifact_dir=tmp_path/'outputs')):
        reply=request(o,**options())
        marker=reply.get('result') if reply['ok'] else reply.get('output')
        assert marker['format']=='fdisbull-output-ref-1' and marker['retry_safe'] is False,reply
        assert marker['execution']['ok'] is (not failed)
        if not failed:assert marker['execution']['complete'] is True
        before=(arm_count(o),len(o.runs),len(o.wire.calls),len(o.reads))
        output=tmp_path/'action-response.json'
        exported=respond(dict(method='output-export',params=dict(artifact=marker['artifact']['id'],output=str(output))))
        assert exported['ok'],exported
        raw=output.read_bytes()
        assert len(raw)==marker['artifact']['bytes'] and hashlib.sha256(raw).hexdigest()==marker['artifact']['sha256']
        full=json.loads(raw)
        assert len(captured)==1
        assert (full['error']['result'] if failed else full['result']) == (captured[0] if failed else public_addresses(captured[0]))
        assert before==(arm_count(o),len(o.runs),len(o.wire.calls),len(o.reads))
    assert_stored(o,captured[0])


@pytest.mark.parametrize('attempted', [False,True])
def test_script_report_publication_failure_preserves_original_error_and_action_disposition(acting,monkeypatch,attempted):
    o,s=acting,acting.session
    if not attempted:o.ram[3]=0
    primary=RuntimeError('authored native callback primary')
    primary.result={'native':'observed original boundary'}
    if attempted:
        def failed_run(*args,**kwargs):raise primary
        s._clock_advance_with_hooks=failed_run
    artifact=s._artifact
    def failed_artifact(name,kind,data,metadata):
        if kind=='script-result':raise OSError('authored script result publication failure')
        return artifact(name,kind,data,metadata)
    monkeypatch.setattr(s,'_artifact',failed_artifact)
    reply=request(o,'debug-script',script=script(dict(op='scene-act',**options())))
    assert not reply['ok']
    failure=reply['error']
    assert failure['type']==('RuntimeError' if attempted else 'SceneError')
    assert failure['script_publication_error']['type']=='OSError'
    report=failure['script_result'];record=report['steps'][0]
    assert not report['ok'] and report['completed_steps']==0
    if attempted:
        assert failure['result']==primary.result and record['result']==primary.result
        assert record['scene_act_result']['input']['attempted'] is True
    else:
        assert failure['result']['input']['attempted'] is False
        assert record['result']==failure['result']
    assert bool(o.closed) is attempted and arm_count(o)==int(attempted)


def test_late_script_report_retains_stored_artifact_without_success_or_replay(acting,monkeypatch):
    o,s=acting,acting.session;clock=SimpleNamespace(now=time.monotonic());publications=[]
    monkeypatch.setattr(time,'monotonic',lambda:clock.now)
    artifact=s._artifact
    def late(name,kind,data,metadata):
        result=artifact(name,kind,data,metadata)
        if kind=='script-result':publications.append(result);clock.now+=70
        return result
    monkeypatch.setattr(s,'_artifact',late)
    reply=request(o,'debug-script',script=script(dict(op='scene-act',**options())))
    assert not reply['ok'] and reply['error']['type']=='TimeoutError',reply
    report=reply['error']['script_result']
    assert report['artifact']==publications[0]['artifact'] and len(publications)==1
    assert report['steps'][0]['result']['complete'] and o.closed
    raw=o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(report['artifact'],)).fetchone()[0]
    assert json.loads(raw)=={key:value for key,value in report.items() if key!='artifact'}
    assert arm_count(o)==len(o.runs)==1


def test_public_action_refuses_passive_scene_without_input_or_execution(moving):
    o, s = moving, moving.session
    info = save(o)
    before = deepcopy(s.input_state())
    workspace = DebugWorkspace()
    workspace.sessions[s.run_id] = s
    try:
        reply = respond(dict(method='debug-scene-act', params=dict(
            project=str(o.project.path), run=s.run_id,
            scene=info['id'], object='actor')), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert not reply['ok'] and reply['error']['type'] == 'ValueError', reply
    assert 'scene-3' in reply['error']['message'], reply
    assert s.input_state() == before
    assert not o.runs and not o.writes and not o.deliveries and not o.closed
