"""QEMU macros through public routing, real persistence and native I/O owners.

Only the QMP wire/CPU boundary is supplied here. These checks establish host
admission, ownership and execution composition, not physical guest consumption.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.input_macros import expand_macro
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from test_qemu_clock_budget import owned
from test_qemu_io_deadlines import QMPWire, observation
from test_qemu_io_public import raw_project
from test_qemu_input_schedule import scheduled
from test_qemu_keyboard_press import ARM, press
from test_qemu_wait import OBS, UNTIL, waiting


class MacroWire(QMPWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.running = False
        self.input_batches = []
        self.reject_input = False

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in ('query-status', 'input-send-event'):
            return super().sendall(data)
        self.requests.append(command)
        self.budgets.append(self.timeout)
        if command == 'query-status':
            response = {'return': dict(running=self.running, status='running' if self.running else 'paused')}
        else:
            self.input_batches.append(deepcopy(args['events']))
            response = ({'error': {'class': 'GenericError', 'desc': 'uncertain device dispatch'}}
                        if self.reject_input else {'return': {}})
        self.buffer.extend(json.dumps(dict(id=request['id'], **response)).encode() + b'\n')
        self.pending_delay = self.latency


def _bind(o):
    session = getattr(o, 'session', getattr(o, 'context', None))
    session.__class__ = QemuDOSProcessSession
    session.metadata = dict(session.metadata, backend='qemu-dos')
    session.rpc, session.guest_profile = o.vm, None
    session._launching, session._process, session._staging = True, None, None
    session._deadline, session._return_breakpoint = None, None
    o.vm.context = session
    previous_close = o.vm.close
    def close():
        session._input_on_close()
        previous_close()
    o.vm.close = close
    o.session = session
    return o


def _execution_peer(o):
    o.executions, o.execution_latency, o.timed_out = [], 0, False
    o.reply, o.on_execute = b'T05thread:1;', lambda: None
    o.session.breakpoints[7] = dict(address=0x7c00, access='x', kind=1, length=1)
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms, *, after_send=None):
        o.executions.append((command, timeout_ms, o.gdb.operation_deadline))
        if after_send is not None:
            o.wire.running = True
            try: after_send(o.gdb.operation_deadline)
            finally: o.wire.running = False
        o.on_execute()
        o.clock.now += o.execution_latency
        return o.reply, o.timed_out
    o.gdb.execute = execute
    return o


@pytest.fixture
def macro_owner(observation):
    o = _bind(observation)
    o.wire = MacroWire(o.clock)
    o.qmp.socket = o.wire
    return _execution_peer(o)


@pytest.fixture
def macro_press(press):
    return _execution_peer(_bind(press))


def define(o, steps, *, outputs=None, parameters=None, extra=None):
    definition = dict(format='fdisbull-macro-set-1', name='authored', macros={
        'action': dict(steps=steps, outputs=outputs or {}, parameters=parameters or {}), **(extra or {})})
    return o.session.project.debug_define_macros(definition)['id']


def invoke(o, macro_set, **options):
    return o.session.macro(macro_set, 'action', **options)


def counts(o):
    return tuple(o.session.project.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                 for table in ('debug_events', 'debug_artifacts'))


@pytest.mark.parametrize('late', [
    dict(op='keyboard.key-down', key='INVALID'),
    dict(op='keyboard.key-up', lease='0'*32 + ':' + '1'*32),
    dict(op='run', guest_ms=20),
    dict(op='run', stop_on_hook=False),
    dict(op='memory', address=0x7c00, length=0),
    dict(op='screenshot', name='../outside.png'),
    dict(op='frame-probe', points=[]),
])
def test_late_invalid_macro_is_rejected_before_effects_and_preserves_entry_lease(macro_owner, late):
    o = macro_owner
    held = o.session.keyboard_key_down('ctrl')['lease']
    before, calls, rows = deepcopy(o.session.input_state()), len(o.wire.requests), counts(o)
    saved = define(o, [dict(op='keyboard.key-down', key='a'), late])
    with pytest.raises((ValueError, TypeError)):
        invoke(o, saved)
    assert o.session.input_state() == before and held in before['leases']
    assert len(o.wire.requests) == calls and counts(o) == rows
    assert not o.executions and not o.vm.closed


def test_native_result_schema_rejects_dosbox_revision_before_queuing(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='a', **{'as': 'down'})],
                   outputs={'revision': '$down.state_revision'})
    with pytest.raises(ValueError, match='result field'):
        invoke(o, saved)
    assert not o.wire.requests and not o.executions
    assert not o.session.input_state()['leases'] and counts(o) == (0, 0)


def test_double_release_is_detected_before_the_first_make(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='a', **{'as': 'down'}),
                       dict(op='keyboard.key-up', lease='$down.lease'),
                       dict(op='keyboard.key-up', lease='$down.lease')])
    with pytest.raises(ValueError, match='owned unused'):
        invoke(o, saved)
    assert not o.wire.requests and not o.session.input_state()['leases'] and not o.vm.closed


def test_public_macro_returns_native_lease_and_persists_unchanged_delivery_claim(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='ctrl', **{'as': 'down'}), dict(op='run')],
                   outputs=dict(lease='$down.lease', delivery='$down.delivery', consumed='$down.guest_consumed'))
    workspace = DebugWorkspace()
    workspace.sessions[o.session.run_id] = o.session
    try:
        reply = respond(dict(method='debug-macro', params=dict(project=str(o.project.path),
            run=o.session.run_id, macro_set=saved, name='action', timeout_ms=500)), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert reply['ok'], reply
    result = reply['result']
    token = result['outputs']['lease']
    assert result['ok'] and len(token) == 65 and token.count(':') == 1
    assert result['outputs']['delivery'] == 'python_pending' and result['outputs']['consumed'] is None
    assert result['input_after']['physical']['leases'][token]['make'] == 'qmp_accepted'
    assert len(o.wire.input_batches) == len(o.executions) == 1
    assert not o.vm.closed and o.session._rpc_deadline is None
    row = o.project.db.execute("SELECT evidence FROM debug_events WHERE operation='macro'").fetchone()
    assert json.loads(row[0])['outputs']['lease'] == token
    artifact = o.project.db.execute('SELECT kind FROM debug_artifacts WHERE id=?', (result['artifact'],)).fetchone()
    assert artifact['kind'] == 'macro-result'


def test_typed_native_lease_parameter_releases_only_its_owner(macro_owner):
    o = macro_owner
    token = o.session.keyboard_key_down('ctrl')['lease']
    saved = define(o, [dict(op='keyboard.key-up', lease='$args.lease'), dict(op='run')],
                   parameters={'lease': {'type': 'input-lease'}})
    result = invoke(o, saved, args={'lease': token})
    assert result['ok'] and o.session.input_state()['leases'] == {}
    assert len(o.wire.input_batches) == len(o.executions) == 1
    assert [edge['data']['down'] for edge in o.wire.input_batches[0]] == [True, False]
    assert not o.vm.closed


def test_nested_macro_outputs_keep_typed_lease_identity(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='macro', name='hold', **{'as': 'held'}),
                       dict(op='keyboard.key-up', lease='$held.outputs.lease'), dict(op='run')],
        extra={'hold': dict(steps=[dict(op='keyboard.key-down', key='a', **{'as': 'down'}),
                                  dict(op='run')], outputs={'lease': '$down.lease'})})
    result = invoke(o, saved)
    assert result['ok'], result
    assert o.session.input_state()['leases'] == {} and len(o.executions) == 2
    assert [batch[0]['data']['down'] for batch in o.wire.input_batches] == [True, False]


def test_unreturned_lease_closes_without_injecting_break_or_resuming(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='a'), dict(op='run')])
    result = invoke(o, saved)
    assert not result['ok'] and o.vm.closed and o.session.closed
    assert result['cleanup'][-1]['closed'] and result['input_after']['reason'] == 'session_closed'
    assert len(o.executions) == len(o.wire.input_batches) == 1
    assert o.wire.input_batches[0][0]['data']['down'] is True
    assert not o.session._input_storage()['valid'] and not o.session._input_storage()['leases']


@pytest.mark.parametrize('reply,outcome', [(b'T05thread:1;watch:7c00;', 'watchpoint'),
                                          (b'T02thread:1;', 'stopped'), (b'W00', 'exited')])
def test_first_unexpected_native_stop_keeps_receipt_and_never_runs_later_steps(macro_owner, reply, outcome):
    o = macro_owner
    o.reply = reply
    saved = define(o, [dict(op='keyboard.key-down', key='a'), dict(op='run'),
                       dict(op='keyboard.key-down', key='b'), dict(op='run')])
    result = invoke(o, saved)
    assert not result['ok'] and o.session.closed and len(o.executions) == 1
    stop = result['execution']['steps'][-1]['result']
    assert stop['outcome'] == outcome and stop['session']['stop_reason']['native_reply'] == reply.decode()
    assert len(result['execution']['steps']) == 2 and len(o.wire.input_batches) == 1
    assert result['expanded_steps'][1]['stop_on_hook'] is True


def test_uncertain_input_dispatch_is_never_repeated(macro_owner):
    o = macro_owner
    o.wire.reject_input = True
    saved = define(o, [dict(op='keyboard.key-down', key='a'), dict(op='run'), dict(op='run')])
    result = invoke(o, saved)
    assert not result['ok'] and o.vm.closed and o.session.closed
    assert len(o.wire.input_batches) == len(o.executions) == 1
    assert 'uncertain device dispatch' in result['execution']['error']['message']


def test_native_timeout_cannot_fall_through_to_a_second_run(macro_owner):
    o = macro_owner
    o.timed_out = True
    saved = define(o, [dict(op='keyboard.key-down', key='a'), dict(op='run'), dict(op='run')])
    result = invoke(o, saved)
    assert not result['ok'] and o.session.closed and len(o.executions) == 1
    stop = result['execution']['steps'][-1]['result']
    assert stop['outcome'] == 'timeout' and stop['timed_out'] is True


def test_failed_assertion_after_release_never_runs_a_cleanup_break(macro_owner):
    o = macro_owner
    start = define(o, [dict(op='keyboard.key-down', key='ctrl', **{'as': 'held'}), dict(op='run')],
                   outputs={'lease': '$held.lease'})
    token = invoke(o, start)['outputs']['lease']
    saved = define(o, [dict(op='keyboard.key-up', lease='$args.lease'),
                       dict(op='assert', value=1, equals=2), dict(op='run')],
                   parameters={'lease': {'type': 'input-lease'}})
    result = invoke(o, saved, args={'lease': token})
    assert not result['ok'] and o.session.closed
    assert len(o.executions) == len(o.wire.input_batches) == 1
    assert o.wire.input_batches[0][0]['data']['down'] is True


def test_macro_publication_failure_retires_input_without_replaying(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='a', **{'as': 'held'}), dict(op='run')],
                   outputs={'lease': '$held.lease'})
    artifact = o.session._artifact
    def fail(name, kind, data, metadata):
        if kind == 'macro-result':
            raise OSError('authored publication failure')
        return artifact(name, kind, data, metadata)
    o.session._artifact = fail
    with pytest.raises(OSError, match='publication failure'):
        invoke(o, saved)
    assert o.session.closed and len(o.executions) == len(o.wire.input_batches) == 1
    assert not o.session._input_storage()['leases']


def test_one_deadline_reaches_qmp_and_is_restored_without_widening(macro_owner):
    o = macro_owner
    o.wire.latency = .03
    o.session._rpc_deadline, o.vm.operation_deadline, o.qmp.operation_deadline = 100.08, 100.07, 100.05
    saved = define(o, [dict(op='keyboard.key-down', key='a', **{'as': 'down'}), dict(op='run')],
                   outputs={'lease': '$down.lease'})
    result = invoke(o, saved, timeout_ms=1000)
    assert not result['ok'] and 100.049 <= o.clock.now <= 100.05
    first, second = o.wire.budgets
    assert .049 <= first <= .05 and second == pytest.approx(first - .03)
    assert o.clock.now == pytest.approx(100 + first)
    assert len(o.executions) == 1 and not o.wire.input_batches and o.vm.closed
    assert o.session._rpc_deadline == 100.08 and o.vm.operation_deadline == 100.07
    assert o.qmp.operation_deadline == 100.05 and o.gdb.operation_deadline is None


def test_lock_admission_uses_the_original_deadline_without_native_effects(macro_owner):
    o = macro_owner
    token = o.session.keyboard_key_down('a')['lease']
    before, waits = deepcopy(o.session.input_state()), []
    class Busy:
        def acquire(self, *, timeout):
            waits.append(timeout)
            return False
    o.vm.lock = Busy()
    o.session._rpc_deadline = 100.02
    saved = define(o, [dict(op='status')])
    with pytest.raises(TimeoutError, match='acquire'):
        invoke(o, saved, timeout_ms=1000)
    assert waits == pytest.approx([.02]) and o.session._input_storage()['leases'][token]
    assert o.session._input_storage()['pending'] == before['pending'] and not o.vm.closed
    assert len(o.wire.requests) == 1 and not o.executions
    # The existing fixture closes through the same lock after this test.
    import threading
    o.vm.lock = threading.RLock()
    o.session._rpc_deadline = None


def test_macro_in_saved_script_reuses_route_and_preflights_before_prior_input(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='status', **{'as': 'status'}),
                       dict(op='assert', value='$status.state', equals='stopped')])
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='macro', macro_set=saved, name='action', **{'as': 'result'}),
        dict(op='assert', value='$result.ok', equals=True)])
    result = o.session.script(script=script, timeout_ms=1000)
    assert result['ok'], result
    bad = define(o, [dict(op='keyboard.key-up', lease='a'*32 + ':' + 'b'*32)])
    script['steps'] = [dict(op='keyboard.key-down', key='a'),
                       dict(op='macro', macro_set=bad, name='action')]
    before, calls = deepcopy(o.session.input_state()), len(o.wire.requests)
    with pytest.raises(ValueError, match='owned unused'):
        execute_script(o.session, script)
    assert o.session.input_state() == before and len(o.wire.requests) == calls


def test_later_outer_script_failure_retires_the_inner_macros_native_lease(macro_owner):
    o = macro_owner
    saved = define(o, [dict(op='keyboard.key-down', key='a', **{'as': 'held'}), dict(op='run')],
                   outputs={'lease': '$held.lease'})
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='macro', macro_set=saved, name='action'),
        dict(op='assert', value=1, equals=2), dict(op='run')])
    result = execute_script(o.session, script)
    assert not result['ok'] and result['steps'][0]['result']['ok']
    assert o.session.closed and result['input_cleanup']['closed']
    assert len(o.executions) == len(o.wire.input_batches) == 1
    assert not o.session._input_storage()['leases']


def test_observation_macro_does_not_make_outer_failure_own_existing_input(macro_owner):
    o = macro_owner
    token = o.session.keyboard_key_down('ctrl')['lease']
    before = deepcopy(o.session.input_state())
    saved = define(o, [dict(op='status')])
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='macro', macro_set=saved, name='action'), dict(op='assert', value=1, equals=2)])
    result = execute_script(o.session, script)
    assert not result['ok'] and not o.session.closed and result['input_cleanup'] is None
    assert o.session.input_state() == before and token in before['leases']
    assert not o.executions and not o.wire.input_batches


def test_successful_timed_plan_is_armed_once_and_resolved_by_explicit_run(macro_press):
    o = macro_press
    o.on_execute = lambda: o.wire.stop_after(2)
    saved = define(o, [dict(op='keyboard.press', key='a', hold_ms=20), dict(op='run')])
    result = invoke(o, saved)
    assert result['ok'], result
    assert len(o.executions) == 1 and [name for name, _ in o.wire.calls].count(ARM) == 1
    assert o.session.input_state()['pending_edges'] == 0 and not o.session.input_state()['leases']


def test_interrupted_timed_suffix_stops_even_at_an_expected_breakpoint(macro_press):
    o = macro_press
    o.on_execute = lambda: o.wire.stop_after(1)
    saved = define(o, [dict(op='keyboard.press', key='a'), dict(op='run'),
                       dict(op='keyboard.press', key='b'), dict(op='run')])
    result = invoke(o, saved)
    assert not result['ok'] and o.session.closed and len(o.executions) == 1
    stop = result['execution']['steps'][-1]['result']
    assert stop['outcome'] == 'breakpoint'
    assert stop['input_delivery']['press']['dispatched_count'] == 1
    assert stop['input_delivery']['requires_resolution'] is True
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


def test_timed_arm_without_explicit_execution_is_not_successful_completion(macro_press):
    o = macro_press
    saved = define(o, [dict(op='keyboard.press', key='a')])
    result = invoke(o, saved)
    assert not result['ok'] and o.vm.closed and not o.executions
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


def test_insufficient_later_wait_budget_is_rejected_before_timed_arm(macro_press):
    o = macro_press
    saved = define(o, [dict(op='keyboard.press', key='a', hold_ms=40),
                       dict(op='wait', observations=OBS, until=UNTIL, guest_ms=10,
                            slice_ms=1, timeout_screenshot=None)])
    with pytest.raises(ValueError, match='virtual budget'):
        invoke(o, saved)
    assert not o.wire.calls and not o.executions and not o.vm.closed


def test_macro_uses_existing_virtual_wait_and_native_time_receipt(waiting):
    o = _bind(waiting)
    saved = define(o, [dict(op='wait', observations=OBS, until=UNTIL, guest_ms=10,
                            slice_ms=1, timeout_screenshot=None, **{'as': 'ready'})],
                   outputs=dict(matched='$ready.matched', elapsed_ns='$ready.guest_elapsed_ns'))
    result = invoke(o, saved)
    assert result['ok'] and result['outputs'] == dict(matched=True, elapsed_ns=1_000_064)
    assert len(o.executions) == 1 and not o.vm.closed
    o.session.close()


@pytest.mark.parametrize('entry_pending', [False, True])
def test_initial_wait_match_cannot_run_a_suffix_with_pending_input(waiting, entry_pending):
    o = _bind(waiting)
    o.gdb = o.remote
    o.vm.qmp_commands |= {'input-send-event'}
    o.session.capabilities['physical_input'] = True
    _execution_peer(o)
    if entry_pending:
        token = o.session.keyboard_key_down('a')['lease']
        before = deepcopy(o.session.input_state())
    steps = ([] if entry_pending else [dict(op='keyboard.key-down', key='a', **{'as': 'held'})])
    steps += [dict(op='wait', observations=OBS, until={'observation': 'counter', 'equals': '0000'},
                   guest_ms=10, slice_ms=1, timeout_screenshot=None), dict(op='run')]
    saved = define(o, steps, outputs={} if entry_pending else {'lease': '$held.lease'})
    result = invoke(o, saved)
    stopped = result['execution']['steps'][-1]
    assert stopped['op'] == 'wait' and stopped['result']['matched'] is True
    assert not result['ok'] and not o.executions
    assert len(result['execution']['steps']) == (1 if entry_pending else 2)
    if entry_pending:
        assert not o.session.closed and not result['cleanup']
        assert o.session.input_state() == before and token in before['leases']
        o.session.close()
    else:
        assert o.session.closed and result['cleanup'][-1]['closed']
        assert not o.session._input_storage()['leases']


def test_default_macro_expansion_preserves_legacy_lease_and_result_contract():
    spec = dict(format='fdisbull-macro-set-1', name='legacy', macros={
        'release': dict(parameters={'lease': {'type': 'input-lease'}},
                        steps=[dict(op='keyboard.key-up', lease='$args.lease')]),
        'inspect': dict(steps=[dict(op='keyboard.state', **{'as': 's'})],
                        outputs={'revision': '$s.state_revision'})})
    assert expand_macro(spec, 'release', {'lease': 'a'*32})['script']['steps'][0]['lease'] == 'a'*32
    assert 'backend' not in expand_macro(spec, 'inspect')['script']
    with pytest.raises(ValueError, match='Input lease'):
        expand_macro(spec, 'release', {'lease': 'a'*32 + ':' + 'b'*32})
