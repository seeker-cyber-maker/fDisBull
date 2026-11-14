"""Publication-bound relative motion at the production QMP envelope.

The deterministic peer supplies protocol and ownership evidence. Native PS/2
packets and application pointer behavior have separate authored guest witnesses.
"""
from copy import deepcopy
from inspect import Parameter, signature
import json

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_input_schedule import INPUT_RETRACE_COMMANDS, INPUT_SCHEDULE_COMMANDS
from fdisbull.qemu_machine import MachineContext
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_keyboard_press import change, run_with_stop
from test_qemu_mapped_mouse_public import BAD_LITERALS, COMMANDS, motion_arguments
from test_qemu_vga_configuration import ConfigurationWire, vga


ARM = 'x-fdisbull-arm-display-motion'
DELAY_NS = 2_000_000


class MotionWire(ConfigurationWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.input = {'api-version': 1, 'epoch': 1, 'state': 'idle',
                      'virtual-ns': 1000, 'event-count': 0}
        self.extra_latency = {}
        self.mutate_input = lambda value: value
        self.mutate_input_envelope = lambda value: value
        self.before_command = lambda command, args: None
        self.after_arm = lambda: None
        self.reject_arm = False
        self.running = False
        self.last_input_reply = None

    def snapshot(self):
        display = deepcopy(self.display)
        display['virtual-ns'] = self.receipt['virtual-ns']
        value = dict(display=display, current=self.current())
        if self.published is not None:
            value['published'] = deepcopy(self.published)
        return value

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        self.before_command(command, args)
        if command == 'query-status' and self.running:
            self.calls.append((command, args))
            self.budgets.append(self.timeout)
            self.buffer.extend(json.dumps({'id': request['id'], 'return': {
                'running': True, 'status': 'running'}}).encode() + b'\n')
            self.delay = self.latency
            return
        if command not in INPUT_SCHEDULE_COMMANDS | {ARM}:
            super().sendall(data)
            self.delay += self.extra_latency.get(command, 0)
            return
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        now = self.receipt['virtual-ns']
        if command == ARM:
            assert set(args) == {'token', 'dx', 'dy', 'expected'}
            self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed', 'virtual-ns': now,
                'token': args['token'], 'start-ns': now, 'deadline-ns': now + DELAY_NS,
                'event-count': int(args['dx'] != 0) + int(args['dy'] != 0),
                'motion': dict(dx=args['dx'], dy=args['dy'],
                               **{'delay-ns': DELAY_NS, 'armed': self.snapshot()})}
        elif command == 'x-fdisbull-arm-input':
            self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed', 'virtual-ns': now,
                'token': args['token'], 'start-ns': now, 'deadline-ns': now + args['delta-ns'],
                'event-count': len(args['events'])}
        elif command == 'x-fdisbull-cancel-input' and self.input['state'] == 'armed':
            assert args['token'] == self.input['token']
            self.input.update(state='cancelled', reason='caller', **{'terminal-ns': now})
        self.input['virtual-ns'] = now
        value = self.mutate_input(deepcopy(self.input))
        self.last_input_reply = deepcopy(value)
        answer = ({'error': {'class': 'GenericError', 'desc': 'Authored display-motion arm refusal'}}
                  if command == ARM and self.reject_arm else {'return': value})
        envelope = self.mutate_input_envelope(dict(id=request['id'], **answer))
        self.buffer.extend(json.dumps(envelope).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)
        if command == ARM:
            self.after_arm()

    def finish(self, state='dispatched', *, now=None, reason=None, checked=True):
        now = self.input['deadline-ns'] if now is None else now
        self.receipt['virtual-ns'] = now
        self.input.update(state=state,
            reason=reason or ('dispatch-complete' if state == 'dispatched' else 'machine-stop'),
            **{'virtual-ns': now, 'terminal-ns': now})
        if state == 'dispatched':
            self.input['dispatch-ns'] = now
        else:
            self.input.pop('dispatch-ns', None)
        if 'motion' in self.input:
            if checked:
                self.input['motion']['checked'] = self.snapshot()
            else:
                self.input['motion'].pop('checked', None)


@pytest.fixture
def mapped(vga):
    o = vga
    o.wire = MotionWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= INPUT_SCHEDULE_COMMANDS | INPUT_RETRACE_COMMANDS | {ARM, 'input-send-event'}
    o.session.capabilities.update(mapped_mouse_motion=True, virtual_input_schedule=True,
                                  retrace_input_schedule=True)
    o.session.display_start()
    o.wire.publish()
    o.session.display_stop()
    o.wire.calls.clear()
    o.wire.budgets.clear()
    return o


def arguments(o, **changes):
    value = motion_arguments(window=o.wire.display['token'], update_id=o.wire.display['update-id'],
                             configuration_generation=o.wire.configuration['configuration-generation'])
    value.update(changes)
    return value


def arm_calls(o):
    return [args for name, args in o.wire.calls if name == ARM]


def arm(o, **changes):
    return o.session.mouse_move_mapped(**arguments(o, **changes))


def assert_closed(o):
    # The failed operation may have exhausted its incoming script deadline.
    # Inspect the retained ownership ledger without starting another operation
    # or widening the failed request's deadline merely to make an assertion.
    state = o.vm._physical_input
    assert o.vm.closed and o.wire.socket_closed and not state['valid']
    assert not state['pending'] and not state['leases']


def test_motion_direct_signature_requires_the_complete_declaration():
    parameters = signature(MachineContext.mouse_move_mapped).parameters
    assert list(parameters) == ['self', 'dx_pixels', 'dy_pixels', 'counts_per_pixel',
                               'window', 'update_id', 'configuration_generation', 'timeout_ms']
    assert all(parameters[name].kind == Parameter.KEYWORD_ONLY for name in
               ('counts_per_pixel', 'window', 'update_id', 'configuration_generation', 'timeout_ms'))
    assert parameters['timeout_ms'].default == 1000


@pytest.mark.parametrize('pixels,scale,expected', [
    ((6, -4), {'x': [2, 3], 'y': [3, 2]}, (4, -6)),
    ((-6, 4), {'x': [2, 3], 'y': [3, 2]}, (-4, 6)),
    ((6, -4), {'x': [-2, 3], 'y': [-3, 2]}, (-4, 6)),
    ((127, 0), {'x': [32767, 32767], 'y': [1, 1]}, (127, 0)),
    ((0, -127), {'x': [1, 1], 'y': [32767, 32767]}, (0, -127)),
    ((-127, 127), {'x': [1, 1], 'y': [1, 1]}, (-127, 127)),
])
def test_motion_arms_one_passive_batch_with_exact_nonzero_axis_order(mapped, pixels, scale, expected):
    o = mapped
    declaration = arguments(o, dx_pixels=pixels[0], dy_pixels=pixels[1], counts_per_pixel=scale)
    result = o.session.mouse_move_mapped(**declaration)
    dx, dy = expected
    assert result['state'] == 'armed' and result['edge_count'] == int(dx != 0) + int(dy != 0)
    assert result['deadline_ns'] == result['start_ns'] + DELAY_NS
    assert result['dispatch_ns'] is result['terminal_ns'] is result['lateness_ns'] is None
    motion = result['motion']
    assert motion['format'] == 'fdisbull-mapped-mouse-motion-1'
    assert (motion['dx_pixels'], motion['dy_pixels']) == pixels
    assert (motion['dx'], motion['dy']) == expected
    assert motion['counts_per_pixel'] == scale and motion['delay_ns'] == DELAY_NS
    assert motion['binding_verified'] is False and motion['native_check'] is None
    assert motion['native_arm'] == result['native']['motion']['armed'] == motion['before']['native']
    assert motion['before']['configuration_matches'] is True
    for name in ('guest_pixel_displacement', 'guest_pointer_position', 'mapping_verified',
                 'raster_coherence', 'target_reached'):
        assert motion[name] is None
    assert result['guest_consumed'] is result['device_queue_accepted'] is None
    state = o.session.input_state()
    assert not state['leases']
    assert [item['event'] for item in state['pending']] == [
        dict(type='rel', data=dict(axis=axis, value=count))
        for axis, count in (('x', dx), ('y', dy)) if count]
    assert all(item['lease'] is None for item in state['pending'])
    assert result['sequences'] == list(range(1, len(state['pending']) + 1))
    assert len(arm_calls(o)) == 1
    assert not any(name in ('cont', 'input-send-event', 'screendump',
                           'x-fdisbull-start-display', 'x-fdisbull-stop-display',
                           'x-fdisbull-arm-clock-budget') for name, _ in o.wire.calls)


def test_arm_sends_every_exact_publication_and_configuration_reference(mapped):
    o = mapped
    result = arm(o)
    call = arm_calls(o)[0]
    assert call == dict(token=result['token'], dx=4, dy=-6, expected={
        'epoch': 1, 'virtual-ns': 1000, 'device': '/machine/unattached/device[0]',
        'model': o.wire.configuration['model'], 'configuration-generation': 5,
        'window': o.wire.display['token'], 'update-id': 1, 'published-ns': 1000,
        'width': 320, 'height': 200})


def test_declaration_and_returned_receipt_do_not_alias_owned_plan(mapped):
    o = mapped
    declaration = arguments(o)
    result = o.session.mouse_move_mapped(**declaration)
    expected = deepcopy(result['motion'])
    declaration['counts_per_pixel']['x'][0] = 99
    result['motion']['counts_per_pixel']['y'][1] = 99
    result['motion']['native_arm']['current']['raw']['crtc'][0] = 99
    observed = o.session.input_schedule_observe()
    assert observed['motion'] == expected
    assert o.session.input_state()['pending'][0]['event']['data']['value'] == 4


@pytest.mark.parametrize('options', BAD_LITERALS)
def test_bad_direct_literal_cannot_touch_qmp_or_allocate_input(mapped, options):
    o = mapped
    before = o.session.input_state()
    with pytest.raises((ValueError, TypeError)):
        arm(o, **options)
    assert not o.wire.calls and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('field', ['dx_pixels', 'dy_pixels', 'counts_per_pixel', 'window',
                                 'update_id', 'configuration_generation'])
def test_missing_direct_argument_refuses_without_native_io(mapped, field):
    options = arguments(mapped)
    del options[field]
    with pytest.raises(TypeError):
        mapped.session.mouse_move_mapped(**options)
    assert not mapped.wire.calls and not mapped.vm.closed


def test_direct_signature_and_invalid_literals_precede_deadline_creation(mapped, monkeypatch):
    def forbidden_deadline(*args, **kwargs):
        pytest.fail('Invalid motion reached deadline creation')

    monkeypatch.setattr('fdisbull.operation_budget.request_deadline', forbidden_deadline)
    with pytest.raises(TypeError):
        mapped.session.mouse_move_mapped(6, -4, {'x': [2, 3], 'y': [3, 2]})
    with pytest.raises(ValueError):
        arm(mapped, counts_per_pixel={'x': [1, 4], 'y': [1, 1]})
    assert not mapped.wire.calls and not mapped.vm.closed


def test_motion_requires_a_project_before_native_io(mapped):
    o = mapped
    project = o.session.project
    o.session.project = None
    try:
        with pytest.raises(ValueError, match='project'):
            arm(o)
    finally:
        o.session.project = project
    assert not o.wire.calls and not o.vm.closed


def test_missing_native_vga_admission_closes_without_arming(mapped):
    o = mapped
    del o.vm.native_retrace_admission
    with pytest.raises(DebuggerError, match='admission'):
        arm(o)
    assert not arm_calls(o)
    assert_closed(o)


def test_two_contexts_share_one_motion_plan_and_do_not_create_cursor_state(mapped):
    o = mapped
    armed = arm(o)
    other = MachineContext(o.vm).bind(o.project, o.session.run_id)
    before = o.session.input_state()
    calls = list(o.wire.calls)
    with pytest.raises(ValueError):
        other.mouse_move_mapped(**arguments(o))
    assert o.wire.calls == calls and other.input_state() == before
    assert other.input_state()['schedule']['token'] == armed['token']
    assert 'cursor' not in other.input_state() and not o.vm.closed


@pytest.mark.parametrize('profile', ['clock_profile', 'retrace_profile'])
def test_lost_selected_profile_invalidates_already_admitted_vga_owner(mapped, profile):
    o = mapped
    o.session.input_state()
    o.vm.machine_configuration[profile]['profile'] = 'standard'
    with pytest.raises(DebuggerError):
        arm(o)
    assert not o.wire.calls
    assert_closed(o)


def test_fresh_standard_profile_refuses_motion_without_invalidating_owner(observation):
    o = observation
    o.vm.qmp_commands = COMMANDS
    o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard', 1)
    with pytest.raises(ValueError, match='precise'):
        o.session.mouse_move_mapped(**motion_arguments())
    assert not o.wire.requests and not o.vm.closed


@pytest.mark.parametrize('refusal', ['transaction', 'pending-motion', 'held-button', 'armed'])
def test_motion_cannot_take_over_conflicting_owner_state(mapped, refusal):
    o = mapped
    if refusal == 'pending-motion':
        o.session.mouse_move_relative(1, 0)
    elif refusal == 'held-button':
        o.session.mouse_button_down('left')
        o.session.input_schedule(1000)
        o.wire.finish()
        o.session.input_schedule_observe()
    elif refusal == 'armed':
        arm(o)
    calls, before = list(o.wire.calls), o.session.input_state()
    if refusal == 'transaction':
        with o.project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                arm(o)
    else:
        with pytest.raises(ValueError):
            arm(o)
    assert o.wire.calls == calls and o.session.input_state() == before and not o.vm.closed


def test_running_owner_refuses_without_arming_or_queuing(mapped):
    o = mapped
    o.wire.running = True
    before = o.session.input_state()
    with pytest.raises((ValueError, DebuggerError)):
        arm(o)
    assert not arm_calls(o) and o.session.input_state()['pending'] == before['pending']


@pytest.mark.parametrize('refusal', ['observing', 'empty', 'wrong-window', 'wrong-update',
                                   'wrong-generation', 'configuration-changed', 'width', 'height'])
def test_known_binding_refusal_keeps_owner_live_and_never_arms(mapped, refusal):
    o = mapped
    options = arguments(o)
    if refusal in ('observing', 'empty'):
        o.session.display_start()
        if refusal == 'observing':
            o.wire.publish()
        else:
            o.session.display_stop()
        options['window'] = o.wire.display['token']
    elif refusal == 'wrong-window':
        options['window'] = 'another-window'
    elif refusal == 'wrong-update':
        options['update_id'] = 2
    elif refusal == 'wrong-generation':
        options['configuration_generation'] = 6
    elif refusal == 'configuration-changed':
        o.wire.configuration['configuration-generation'] = 7
        o.wire.configuration['raw']['crtc'][0x0d] = 8
        options['configuration_generation'] = 7
    elif refusal == 'width':
        options.update(dx_pixels=320, counts_per_pixel={'x': [1, 4], 'y': [3, 2]})
    elif refusal == 'height':
        options.update(dy_pixels=-200, counts_per_pixel={'x': [2, 3], 'y': [1, 4]})
    o.wire.calls.clear()
    before = o.session.input_state()
    with pytest.raises(ValueError):
        o.session.mouse_move_mapped(**options)
    assert not arm_calls(o) and o.session.input_state() == before and not o.vm.closed
    assert not any(name in ('x-fdisbull-start-display', 'x-fdisbull-stop-display', 'cont')
                   for name, _ in o.wire.calls)


def test_valid_motion_can_use_an_old_retained_publication_without_claiming_fresh_pixels(mapped):
    o = mapped
    o.wire.receipt['virtual-ns'] = 9_000_001_000
    result = arm(o)
    assert result['motion']['before']['display']['published_ns'] == 1000
    assert result['motion']['before']['current']['observed_ns'] == 9_000_001_000
    assert result['motion']['raster_coherence'] is None


def test_dispatched_motion_retains_callback_binding_and_never_invents_pointer_position(mapped):
    o = mapped
    armed = arm(o)
    run_with_stop(o, lambda: o.wire.finish(now=armed['deadline_ns'] + 321))
    result = o.session.run(timeout_ms=1000)
    delivered = result['input_delivery']
    assert delivered['state'] == 'dispatched' and delivered['lateness_ns'] == 321
    assert delivered['motion']['binding_verified'] is True
    assert delivered['motion']['native_arm'] == armed['motion']['native_arm']
    assert delivered['motion']['native_check'] == o.wire.input['motion']['checked']
    assert delivered['motion']['native_check']['current']['virtual-ns'] == delivered['dispatch_ns']
    assert delivered['motion']['guest_pixel_displacement'] is None
    assert delivered['motion']['guest_pointer_position'] is None
    assert delivered['guest_consumed'] is delivered['device_queue_accepted'] is None
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert not delivered['requires_resolution'] and not o.session.input_state()['pending']
    assert not o.session.input_state()['leases']
    assert o.session.input_schedule_observe()['native'] == delivered['native']
    following = arm(o)
    assert following['token'] != armed['token'] and following['sequences'] == [3, 4]


@pytest.mark.parametrize('reason', ['machine-stop', 'stop-pending', 'budget-deadline'])
def test_precheck_stop_retains_unsent_motion_without_a_callback_snapshot(mapped, reason):
    o = mapped
    armed = arm(o)
    when = armed['deadline_ns'] if reason == 'budget-deadline' else armed['start_ns'] + 1
    o.wire.finish('cancelled', now=when, reason=reason, checked=False)
    result = o.session.input_schedule_observe()
    assert result['state'] == 'cancelled' and result['requires_resolution'] is True
    assert result['motion']['binding_verified'] is False and result['motion']['native_check'] is None
    assert result['dispatch_ns'] is None and o.session.input_state()['pending_edges'] == 2
    before = o.session.input_state()
    assert o.session.input_schedule_observe()['native'] == result['native']
    assert o.session.input_state()['pending'] == before['pending']


@pytest.mark.parametrize('change_kind', ['generation', 'aba', 'window', 'observer-state'])
def test_semantic_callback_cancellation_retains_actual_failed_binding(mapped, change_kind):
    o = mapped
    armed = arm(o)
    if change_kind in ('generation', 'aba'):
        o.wire.configuration['configuration-generation'] += 2
        if change_kind == 'generation':
            o.wire.configuration['raw']['crtc'][0x0d] = 8
        reason = 'display-motion-configuration-changed'
    elif change_kind == 'window':
        o.wire.display['token'] = 'replacement-window'
        reason = 'display-motion-publication-changed'
    else:
        o.wire.display['state'] = 'observing'
        del o.wire.display['stop-ns']
        reason = 'display-motion-publication-changed'
    o.wire.finish('cancelled', reason=reason)
    result = o.session.input_schedule_observe()
    assert result['state'] == 'cancelled' and result['reason'] == reason
    assert result['motion']['binding_verified'] is False and result['requires_resolution'] is True
    assert result['motion']['native_arm'] == armed['motion']['native_arm']
    assert result['motion']['native_check'] == o.wire.input['motion']['checked']
    assert result['dispatch_ns'] is None and o.session.input_state()['pending_edges'] == 2
    assert not o.vm.closed


@pytest.mark.parametrize('reschedule', ['generic', 'retrace'])
def test_cancelled_motion_cannot_be_converted_to_an_unguarded_schedule(mapped, reschedule):
    o = mapped
    armed = arm(o)
    o.wire.finish('cancelled', now=armed['start_ns'] + 1, checked=False)
    o.session.input_schedule_observe()
    calls, before = list(o.wire.calls), o.session.input_state()
    with pytest.raises(ValueError):
        if reschedule == 'generic':
            o.session.input_schedule(1000)
        else:
            o.session.input_schedule_retrace()
    assert o.wire.calls == calls and o.session.input_state() == before
    cancelled = o.session.input_cancel_pending()
    assert cancelled['cancelled_edges'] == 2 and not cancelled['retained_dispatched_holds']
    assert not o.session.input_state()['pending'] and not o.session.input_state()['leases']
    fresh = arm(o)
    assert fresh['token'] != armed['token'] and fresh['state'] == 'armed'


def test_explicit_cancel_disarms_before_forgetting_the_single_motion_batch(mapped):
    o = mapped
    arm(o, dx_pixels=0)
    result = o.session.input_cancel_pending()
    assert result['cancelled_edges'] == 1 and result['cancelled_leases'] == []
    assert not result['retained_dispatched_holds']
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-cancel-input') == 1
    assert o.wire.input['state'] == 'cancelled' and 'checked' not in o.wire.input['motion']
    assert not o.session.input_state()['pending'] and not o.vm.closed


@pytest.mark.parametrize('path,replacement', [
    (('api-version',), True), (('epoch',), 2), (('virtual-ns',), 1001),
    (('token',), 'unowned'), (('start-ns',), 999), (('deadline-ns',), DELAY_NS + 1001),
    (('event-count',), True), (('event-count',), 1), (('event-count',), 3),
    (('extra',), 1), (('press',), {}), (('typing',), {}), (('click',), {}), (('retrace',), {}),
    (('motion',), None), (('motion', 'dx'), True), (('motion', 'dx'), 5),
    (('motion', 'dy'), -5), (('motion', 'delay-ns'), True), (('motion', 'delay-ns'), 1),
    (('motion', 'extra'), 1), (('motion', 'checked'), None), (('motion', 'armed'), None),
    (('motion', 'armed', 'extra'), 1),
    (('motion', 'armed', 'display', 'token'), 'another-window'),
    (('motion', 'armed', 'display', 'width'), 321),
    (('motion', 'armed', 'display', 'height'), 201),
    (('motion', 'armed', 'display', 'period-ns'), 2_000_000),
    (('motion', 'armed', 'current', 'epoch'), 2),
    (('motion', 'armed', 'current', 'device'), '/machine/another-vga'),
    (('motion', 'armed', 'current', 'model'), 'invented-model'),
    (('motion', 'armed', 'current', 'virtual-ns'), 1001),
    (('motion', 'armed', 'current', 'configuration-generation'), 6),
    (('motion', 'armed', 'current', 'raw', 'crtc', 13), 8),
    (('motion', 'armed', 'current', 'raw', 'graphics'), [0] * 15),
    (('motion', 'armed', 'current', 'raw', 'display-enabled'), 1),
    (('motion', 'armed', 'current', 'raw', 'misc-output'), 256),
    (('motion', 'armed', 'published', 'configuration-generation'), 4),
    (('motion', 'armed', 'published', 'raw', 'crtc', 13), 8),
])
def test_malformed_arm_never_publishes_candidate_motion_ownership(mapped, path, replacement):
    o = mapped
    o.wire.mutate_input = lambda value: change(value, path, replacement) if 'motion' in value else value
    with pytest.raises(DebuggerError) as caught:
        arm(o)
    assert_closed(o)
    assert o.vm._physical_input['sequence'] == 0 and len(arm_calls(o)) == 1
    assert caught.value.result['native'] == o.wire.last_input_reply


@pytest.mark.parametrize('fault', ['null-return', 'missing-return', 'native-error'])
def test_missing_or_rejected_native_arm_retains_failure_and_cannot_be_replayed(mapped, fault):
    o = mapped
    if fault == 'null-return':
        o.wire.mutate_input = lambda value: None if 'motion' in value else value
    elif fault == 'missing-return':
        def omit(envelope):
            if isinstance(envelope.get('return'), dict) and 'motion' in envelope['return']:
                envelope.pop('return')
            return envelope
        o.wire.mutate_input_envelope = omit
    else:
        o.wire.reject_arm = True
    with pytest.raises(DebuggerError) as caught:
        arm(o)
    assert caught.value.result is not None and len(arm_calls(o)) == 1
    assert_closed(o)
    assert o.vm._physical_input['sequence'] == 0
    assert not any(name in ('input-send-event', 'cont', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)


@pytest.mark.parametrize('fault', [
    'missing-check', 'null-check', 'missing-arm', 'early-check', 'current-clock', 'display-clock',
    'generation-regression', 'generation-changed', 'same-generation-raw',
    'publication-raw', 'publication-generation', 'publication-dimensions', 'publication-time',
    'stop-time', 'device', 'epoch', 'unknown-field', 'changed-motion',
    'invented-config-cancel', 'invented-publication-cancel', 'wrong-cancel-priority',
    'check-on-stop-cancel', 'early-semantic-cancel',
])
def test_invalid_callback_proof_is_rejected_before_pending_event_commit(mapped, monkeypatch, fault):
    o = mapped
    armed = arm(o)
    o.wire.finish()
    value = o.wire.input
    motion = value['motion']
    checked = motion['checked']
    if fault == 'missing-check':
        del motion['checked']
    elif fault == 'null-check':
        motion['checked'] = None
    elif fault == 'missing-arm':
        del motion['armed']
    elif fault == 'early-check':
        value['terminal-ns'] = value['dispatch-ns'] = armed['deadline_ns'] - 1
    elif fault in ('current-clock', 'display-clock'):
        checked['current' if fault == 'current-clock' else 'display']['virtual-ns'] -= 1
    elif fault == 'generation-regression':
        checked['current']['configuration-generation'] = 4
    elif fault == 'generation-changed':
        checked['current']['configuration-generation'] = 6
    elif fault == 'same-generation-raw':
        checked['current']['raw']['crtc'][13] = 8
    elif fault == 'publication-raw':
        checked['published']['raw']['crtc'][13] = 8
    elif fault == 'publication-generation':
        checked['current']['configuration-generation'] = 6
        checked['published']['configuration-generation'] = 6
    elif fault == 'publication-dimensions':
        checked['display']['width'] = 321
    elif fault == 'publication-time':
        checked['display']['published-ns'] += 1
        checked['published']['virtual-ns'] += 1
    elif fault == 'stop-time':
        checked['display']['stop-ns'] += 1
    elif fault == 'device':
        checked['current']['device'] = '/machine/another-vga'
    elif fault == 'epoch':
        checked['current']['epoch'] = 2
    elif fault == 'unknown-field':
        checked['extra'] = 1
    elif fault == 'changed-motion':
        motion['dx'] = 5
    else:
        value.update(state='cancelled')
        del value['dispatch-ns']
        value['reason'] = ('display-motion-configuration-changed' if fault in
                           ('invented-config-cancel', 'early-semantic-cancel')
                           else 'display-motion-publication-changed')
        if fault == 'wrong-cancel-priority':
            checked['current']['configuration-generation'] = 6
        elif fault == 'check-on-stop-cancel':
            value['reason'] = 'machine-stop'
        elif fault == 'early-semantic-cancel':
            value['terminal-ns'] = armed['deadline_ns'] - 1
            checked['current']['virtual-ns'] = value['terminal-ns']
            checked['display']['virtual-ns'] = value['terminal-ns']
            checked['current']['configuration-generation'] = 6
    committed = []
    monkeypatch.setattr(o.session, '_input_mark_dispatched', lambda *args: committed.append(args))
    with pytest.raises(DebuggerError) as caught:
        o.session.input_schedule_observe()
    assert not committed and caught.value.result['native'] == o.wire.last_input_reply
    assert_closed(o)


def test_configuration_change_wins_when_publication_also_changes(mapped):
    o = mapped
    arm(o)
    o.wire.configuration['configuration-generation'] += 1
    o.wire.display['token'] = 'replacement-window'
    o.wire.finish('cancelled', reason='display-motion-configuration-changed')
    result = o.session.input_schedule_observe()
    assert result['reason'] == 'display-motion-configuration-changed'
    assert result['motion']['native_check']['display']['token'] == 'replacement-window'
    assert not result['motion']['binding_verified'] and not o.vm.closed


def test_empty_replacement_window_cancels_without_inventing_a_publication_stamp(mapped):
    o = mapped
    armed = arm(o)
    o.wire.display = {'api-version': 1, 'epoch': 1, 'state': 'observing',
        'virtual-ns': armed['deadline_ns'], 'period-ns': 1_000_000, 'updates': 0,
        'token': 'empty-replacement', 'start-ns': armed['deadline_ns']}
    o.wire.published = None
    o.wire.finish('cancelled', reason='display-motion-publication-changed')
    result = o.session.input_schedule_observe()
    assert result['reason'] == 'display-motion-publication-changed'
    assert 'published' not in result['motion']['native_check']
    assert result['motion']['native_arm'] == armed['motion']['native_arm']
    assert not o.vm.closed and o.session.input_state()['pending_edges'] == 2


def test_semantic_cancellation_can_precede_the_actual_execution_stop(mapped):
    o = mapped
    armed = arm(o)

    def callback():
        o.wire.configuration['configuration-generation'] += 1
        o.wire.finish('cancelled', reason='display-motion-configuration-changed')
        o.wire.receipt['virtual-ns'] += 100

    run_with_stop(o, callback)
    result = o.session.run(timeout_ms=1000)
    delivered = result['input_delivery']
    assert delivered['terminal_ns'] == armed['deadline_ns']
    assert delivered['native']['virtual-ns'] == armed['deadline_ns'] + 100
    assert delivered['motion']['native_check']['current']['virtual-ns'] == armed['deadline_ns']
    assert delivered['requires_resolution'] and not o.vm.closed


@pytest.mark.parametrize('terminal', ['dispatched', 'cancelled'])
def test_later_observation_keeps_historical_arm_and_callback_times(mapped, terminal):
    o = mapped
    arm(o)
    if terminal == 'cancelled':
        o.wire.configuration['configuration-generation'] += 1
    o.wire.finish(terminal, reason='display-motion-configuration-changed' if terminal == 'cancelled' else None)
    first = o.session.input_schedule_observe()
    o.wire.receipt['virtual-ns'] += 10_000
    later = o.session.input_schedule_observe()
    assert later['native']['virtual-ns'] == first['native']['virtual-ns'] + 10_000
    assert later['motion'] == first['motion']
    assert later['terminal_ns'] == first['terminal_ns'] and not o.vm.closed


@pytest.mark.parametrize('fault', ['reason', 'arm', 'check', 'state'])
def test_terminal_motion_evidence_cannot_be_rewritten(mapped, fault):
    o = mapped
    arm(o)
    o.wire.finish()
    o.session.input_schedule_observe()
    if fault == 'reason':
        o.wire.input['reason'] = 'another-reason'
    elif fault == 'arm':
        o.wire.input['motion']['armed']['current']['raw']['crtc'][0] = 1
    elif fault == 'check':
        o.wire.input['motion']['checked']['display']['width'] = 321
    else:
        o.wire.input.update(state='cancelled', reason='machine-stop')
        o.wire.input.pop('dispatch-ns')
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert_closed(o)


@pytest.mark.parametrize('mode', ['idle', 'ordinary'])
def test_other_schedule_modes_cannot_adopt_unsolicited_motion_evidence(mapped, mode):
    o = mapped
    if mode == 'ordinary':
        o.session.mouse_move_relative(1, 0)
        o.session.input_schedule(1000)
    o.wire.input['motion'] = {}
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert_closed(o)


@pytest.mark.parametrize('dispatch,budget_ns,accepted', [
    (False, DELAY_NS, True), (True, DELAY_NS, False), (True, DELAY_NS + 1000, True),
])
def test_owned_budget_cutoff_precedes_motion_callback_commit(mapped, dispatch, budget_ns, accepted):
    o = mapped
    armed = arm(o)

    def callback():
        cutoff = o.wire.receipt['budget-deadline-ns']
        if dispatch:
            o.wire.finish(now=armed['deadline_ns'])
        else:
            o.wire.finish('cancelled', now=cutoff, reason='budget-deadline', checked=False)
        o.wire.receipt.update({'virtual-ns': cutoff, 'budget-state': 'stopped',
                              'budget-fired-ns': cutoff, 'budget-stopped-ns': cutoff})

    run_with_stop(o, callback, reply=b'T02thread:1;')
    if accepted:
        result = o.session.clock_advance(budget_ns, timeout_ms=1000)
        assert result['input_delivery']['state'] == ('dispatched' if dispatch else 'cancelled')
        assert result['input_delivery']['motion']['binding_verified'] is dispatch
        assert not o.vm.closed
    else:
        with pytest.raises(DebuggerError) as caught:
            o.session.clock_advance(budget_ns, timeout_ms=1000)
        assert caught.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert caught.value.result['input_schedule_native']['token'] == armed['token']
        assert_closed(o)


@pytest.mark.parametrize('fault', ['native-failed', 'malformed', 'persistence'])
def test_execution_failure_keeps_actual_stop_and_raw_motion_evidence(mapped, monkeypatch, fault):
    o = mapped
    armed = arm(o)

    def callback():
        o.wire.finish()
        if fault == 'native-failed':
            o.wire.input.update(state='failed', reason='Selected mouse handler changed')
            o.wire.input.pop('dispatch-ns')
        elif fault == 'malformed':
            o.wire.input['motion']['dx'] = 5

    if fault == 'persistence':
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-result':
                raise OSError('Authored motion result persistence failure')
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    run_with_stop(o, callback)
    with pytest.raises(OSError if fault == 'persistence' else DebuggerError) as caught:
        o.session.run(timeout_ms=1000)
    result = caught.value.result
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['input_schedule_native']['token'] == armed['token']
    assert result['input_schedule_native']['motion'] == o.wire.input['motion']
    assert_closed(o)


@pytest.mark.parametrize('fault', ['lost-arm', 'persistence', 'persistence-overrun', 'final-copy'])
def test_uncertain_or_late_arm_closes_and_retains_available_evidence(mapped, monkeypatch, fault):
    from fdisbull import qemu_mapped_mouse
    o = mapped
    o.session._rpc_deadline = o.clock.now + .125
    if fault == 'lost-arm':
        o.wire.extra_latency[ARM] = 1
    elif fault == 'final-copy':
        original = qemu_mapped_mouse.deepcopy
        expired = []

        def copy(value):
            result = original(value)
            if isinstance(value, dict) and value.get('format') == 'fdisbull-qemu-scheduled-input-1' and not expired:
                expired.append(True)
                o.clock.advance(.125)
            return result

        monkeypatch.setattr(qemu_mapped_mouse, 'deepcopy', copy)
    else:
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-arm':
                if fault == 'persistence':
                    raise OSError('Authored motion arm persistence failure')
                o.clock.advance(.125)
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    with pytest.raises(OSError if fault == 'persistence' else TimeoutError) as caught:
        arm(o)
    assert caught.value.result is not None and len(arm_calls(o)) == 1
    assert_closed(o)
    assert not any(name in ('input-send-event', 'cont', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)
    assert o.vm.operation_deadline is o.qmp.operation_deadline is None


def test_one_shrinking_deadline_covers_observation_and_native_arm_reply(mapped):
    o = mapped
    o.session._rpc_deadline = o.clock.now + .125
    o.wire.latency = .001
    o.wire.extra_latency[ARM] = .125
    with pytest.raises(TimeoutError):
        arm(o)
    assert o.clock.now == pytest.approx(100.125)
    assert o.wire.calls[-1][0] == ARM and 0 < o.wire.budgets[-1] < .125
    assert o.wire.budgets == sorted(o.wire.budgets, reverse=True)
    assert_closed(o)


def test_observation_timeout_cannot_reach_native_arm(mapped):
    o = mapped
    o.wire.extra_latency['x-fdisbull-query-vga-configuration'] = 1
    with pytest.raises(TimeoutError) as caught:
        arm(o, timeout_ms=125)
    assert caught.value.result is not None and not arm_calls(o)
    assert o.vm._physical_input['sequence'] == 0
    assert_closed(o)


def test_changed_stopped_clock_bracket_preserves_both_clocks_and_configuration(mapped):
    o = mapped
    o.wire.after_configuration = lambda: setattr(o.wire, 'counter', o.wire.counter + 1)
    with pytest.raises(DebuggerError) as caught:
        arm(o)
    evidence = caught.value.result
    assert evidence['native'] == o.wire.last_configuration_reply
    assert evidence['clocks']['before']['counter'] != evidence['clocks']['after']['counter']
    assert not arm_calls(o)
    assert_closed(o)


@pytest.mark.parametrize('expired', [False, True])
def test_lock_or_preexpired_deadline_refuses_without_native_io(mapped, expired):
    o = mapped
    before = o.session.input_state()
    o.session._rpc_deadline = o.clock.now + (0 if expired else .125)
    waits = []

    class BusyLock:
        def acquire(self, *, timeout):
            assert not expired
            waits.append(timeout)
            o.clock.advance(timeout)
            return False

    original = o.vm.lock
    o.vm.lock = BusyLock()
    try:
        with pytest.raises(TimeoutError):
            arm(o)
    finally:
        o.vm.lock = original
        o.session._rpc_deadline = None
    assert waits == ([] if expired else pytest.approx([.125]))
    assert not o.wire.calls and o.session.input_state() == before and not o.vm.closed


def test_native_delay_overflow_refuses_before_arm_or_pending_records(mapped):
    o = mapped
    o.wire.receipt['virtual-ns'] = (1 << 63) - DELAY_NS
    with pytest.raises(ValueError):
        arm(o)
    assert not arm_calls(o) and not o.session.input_state()['pending'] and not o.vm.closed


def test_motion_journal_retains_declaration_and_actual_binding_after_owner_close(mapped):
    from fdisbull.project import Project
    o = mapped
    armed = arm(o)
    o.wire.finish()
    delivered = o.session.input_schedule_observe()
    o.session.close()
    with Project(o.project.path) as reopened:
        evidence = [json.loads(row[0]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE operation IN "
            "('input.schedule-arm','input.schedule-observe') ORDER BY sequence")]
        assert armed in evidence and delivered in evidence
        assert reopened.debug_runs()['live_state_verified'] is False
    assert delivered['motion']['guest_pointer_position'] is None


@pytest.mark.parametrize('boundary', ['first-qmp', 'configuration-observation'])
def test_gap_caller_scale_mutation_cannot_rewrite_the_accepted_request(mapped, boundary):
    o = mapped
    declaration = arguments(o)
    entered = deepcopy(declaration)
    mutations = []

    def mutate_scale():
        if not mutations:
            declaration['counts_per_pixel']['x'][:] = [1, 1]
            declaration['counts_per_pixel']['y'][:] = [-1, 1]
            mutations.append(True)

    if boundary == 'first-qmp':
        o.wire.before_command = lambda command, args: mutate_scale()
    else:
        o.wire.after_configuration = mutate_scale
    result = o.session.mouse_move_mapped(**declaration)
    assert mutations and declaration['counts_per_pixel'] != entered['counts_per_pixel']
    assert (arm_calls(o)[0]['dx'], arm_calls(o)[0]['dy']) == (4, -6)
    assert (result['motion']['dx'], result['motion']['dy']) == (4, -6)
    assert result['motion']['counts_per_pixel'] == entered['counts_per_pixel']
    assert o.session.input_schedule_observe()['motion']['counts_per_pixel'] == entered['counts_per_pixel']


@pytest.mark.parametrize('knowledge', ['configuration', 'display-replacement'])
def test_gap_known_pre_callback_observation_rejects_forged_old_binding(mapped, monkeypatch, knowledge):
    o = mapped
    armed = arm(o)
    old = deepcopy(armed['motion']['native_arm'])
    if knowledge == 'configuration':
        # A paused QOM-like mutation can advance generation without time.
        o.wire.configuration['configuration-generation'] += 2
        o.wire.configuration['raw']['crtc'][13] = 8
        known = o.session.vga_configuration_observe()
        assert known['current']['configuration_generation'] == 7
        assert known['configuration_matches'] is False
    else:
        # A real public start/publish/stop establishes a different owned window
        # before the input deadline.  No private VM frontier is fabricated.
        o.session.display_start()
        o.wire.publish()
        o.session.display_stop()
        known = o.session.vga_configuration_observe()
        assert known['display']['window'] != armed['motion']['before']['display']['window']
        assert known['display']['state'] == 'stopped'
    assert known['current']['observed_ns'] == armed['start_ns']

    # Forge a later dispatch that is internally consistent only with the arm,
    # while contradicting the intervening public observation.
    o.wire.configuration = deepcopy(old['current'])
    o.wire.display = deepcopy(old['display'])
    o.wire.published = deepcopy(old['published'])
    o.wire.finish(now=armed['deadline_ns'])
    committed = []
    monkeypatch.setattr(o.session, '_input_mark_dispatched', lambda *args: committed.append(args))
    with pytest.raises(DebuggerError) as caught:
        o.session.input_schedule_observe()
    assert not committed and caught.value.result['native'] == o.wire.last_input_reply
    assert_closed(o)


@pytest.mark.parametrize('knowledge', ['configuration', 'display-replacement'])
def test_historical_callback_remains_valid_after_later_public_observation(mapped, knowledge):
    o = mapped
    armed = arm(o)
    o.wire.finish(now=armed['deadline_ns'])
    actual_check = deepcopy(o.wire.input['motion']['checked'])
    callback_ns = actual_check['current']['virtual-ns']
    o.wire.receipt['virtual-ns'] = callback_ns + 100
    if knowledge == 'configuration':
        o.wire.configuration['configuration-generation'] += 2
        o.wire.configuration['raw']['crtc'][13] = 8
    else:
        o.session.display_start()
        o.wire.publish()
        o.session.display_stop()
    known = o.session.vga_configuration_observe()
    assert known['current']['observed_ns'] > callback_ns
    if knowledge == 'configuration':
        assert known['current']['configuration_generation'] == 7
        assert actual_check['current']['configuration-generation'] == 5
    else:
        assert known['display']['window'] != actual_check['display']['token']
        assert known['display']['published_ns'] > callback_ns

    # This is the first host read of the terminal input receipt.  Its frozen
    # callback predates the newer public observation and must remain valid.
    delivered = o.session.input_schedule_observe()
    assert delivered['state'] == 'dispatched' and delivered['motion']['binding_verified'] is True
    assert delivered['dispatch_ns'] == callback_ns
    assert delivered['motion']['native_check'] == actual_check
    assert delivered['motion']['native_arm'] == armed['motion']['native_arm']
    assert delivered['native']['virtual-ns'] == known['current']['observed_ns']
    assert not o.session.input_state()['pending'] and not o.session.input_state()['leases']
    assert delivered['motion']['guest_pointer_position'] is None and not o.vm.closed


def test_equal_time_post_callback_qom_change_does_not_retroactively_cancel_motion(mapped):
    o = mapped
    armed = arm(o)
    o.wire.finish(now=armed['deadline_ns'])
    actual_check = deepcopy(o.wire.input['motion']['checked'])
    callback_ns = actual_check['current']['virtual-ns']
    # A QOM-like write after the callback does not advance the stopped clock.
    o.wire.configuration['configuration-generation'] += 2
    o.wire.configuration['raw']['crtc'][13] = 8
    known = o.session.vga_configuration_observe()
    assert known['current']['observed_ns'] == callback_ns
    assert known['current']['configuration_generation'] == 7
    assert actual_check['current']['configuration-generation'] == 5

    delivered = o.session.input_schedule_observe()
    assert delivered['state'] == 'dispatched' and delivered['motion']['binding_verified'] is True
    assert delivered['dispatch_ns'] == callback_ns
    assert delivered['motion']['native_check'] == actual_check
    assert delivered['motion']['native_arm'] == armed['motion']['native_arm']
    assert not o.session.input_state()['pending'] and not o.vm.closed


def test_gap_new_window_display_frontier_rejects_later_update_with_earlier_publication_time(mapped, monkeypatch):
    o = mapped
    armed = arm(o)
    configuration_queries = len([name for name, _ in o.wire.calls
                                 if name == 'x-fdisbull-query-vga-configuration'])
    o.session.display_start()
    o.wire.receipt['virtual-ns'] = 1200
    o.wire.publish()
    first = o.session.display_observe()
    o.wire.receipt['virtual-ns'] = 1400
    o.wire.publish()
    latest = o.session.display_observe()
    assert first['window'] == latest['window'] != armed['motion']['before']['display']['window']
    assert (first['update_id'], first['published_ns']) == (1, 1200)
    assert (latest['update_id'], latest['published_ns']) == (2, 1400)
    assert len([name for name, _ in o.wire.calls
                if name == 'x-fdisbull-query-vga-configuration']) == configuration_queries

    # The forged callback advances the new window's update ID but moves its
    # publication time backward relative to two established public observations.
    # It is coherent against the old arm alone because that arm used another
    # window; the newer display-only frontier must still constrain its history.
    o.wire.display.update(updates=3, **{'update-id': 3, 'published-ns': 1300})
    o.wire.published['virtual-ns'] = 1300
    o.wire.finish('cancelled', now=armed['deadline_ns'], reason='display-motion-publication-changed')
    accepted = []
    original = o.session._input_schedule_accept

    def accept(*args, **kwargs):
        accepted.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(o.session, '_input_schedule_accept', accept)
    with pytest.raises(DebuggerError) as caught:
        o.session.input_schedule_observe()
    assert not accepted and caught.value.result['native'] == o.wire.last_input_reply
    assert_closed(o)
