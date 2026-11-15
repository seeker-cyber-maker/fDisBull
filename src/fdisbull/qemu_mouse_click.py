"""One physical button click, passively armed on the native virtual clock.

The paired callbacks request no movement. Existing native motion and external
button state remain unobserved; this operation establishes no cursor position.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid


MOUSE_CLICK_COMMANDS = frozenset({'x-fdisbull-arm-mouse-click'})
FORMAT = 'fdisbull-mouse-click-1'
_EDGE_DELAY_NS = 2_000_000
_MAX_NS = (1 << 63) - 1


def validate_mouse_click_parameters(button='left', *, hold_ms=80):
    """Validate physical button names and a strict native hold interval."""
    from .qemu_input import _BUTTONS
    if type(button) is not str or button not in _BUTTONS:
        raise ValueError('Mouse button must be left, middle or right')
    if type(hold_ms) is not int or not 1 <= hold_ms <= 1000:
        raise ValueError('hold_ms must be an integer in 1..1000')


def _plan(button, hold_ms):
    return dict(button=button, hold_ms=hold_ms, steps=[
        dict(button=button, down=True, **{'delay-ns': _EDGE_DELAY_NS}),
        dict(button=button, down=False, **{'delay-ns': hold_ms * 1_000_000}),
    ])


def validate_native_click(value, expected):
    """Validate both edges and the entire delivered prefix before lease commit."""
    planned = expected.get('click') if expected is not None else None
    if planned is None:
        if 'click' in value:
            raise ValueError('Other native input invented a timed mouse click')
        return
    click = value.get('click')
    fields = {'button', 'hold-ms', 'steps', 'dispatched-count'}
    if (type(click) is not dict or set(click) != fields
            or any(mode in value for mode in ('press', 'typing', 'retrace'))
            or type(click['button']) is not str or click['button'] != planned['button']
            or type(click['hold-ms']) is not int or click['hold-ms'] != planned['hold_ms']
            or type(click['steps']) is not list or len(click['steps']) != 2
            or type(click['dispatched-count']) is not int
            or not 0 <= click['dispatched-count'] <= 2):
        raise ValueError('Invalid native timed mouse plan or dispatched prefix')
    count = click['dispatched-count']
    steps = click['steps']
    for index, (step, declared) in enumerate(zip(steps, planned['steps'], strict=True)):
        keys = {'button', 'down', 'delay-ns'}
        if index <= count:
            keys.add('deadline-ns')
        if index < count:
            keys.add('dispatch-ns')
        if (type(step) is not dict or set(step) != keys
                or type(step['button']) is not str or step['button'] != declared['button']
                or type(step['down']) is not bool or step['down'] != declared['down']
                or type(step['delay-ns']) is not int or step['delay-ns'] != declared['delay-ns']):
            raise ValueError('Native timed mouse step differs from its declared plan or prefix')
        if index <= count:
            due = (value['start-ns'] if index == 0 else steps[index - 1]['dispatch-ns']) + step['delay-ns']
            if (type(step['deadline-ns']) is not int or not 0 <= step['deadline-ns'] <= _MAX_NS
                    or step['deadline-ns'] != due):
                raise ValueError('Native timed mouse deadline is not relative to the actual preceding callback')
        if index < count:
            actual = step['dispatch-ns']
            if (type(actual) is not int or not step['deadline-ns'] <= actual <= value['virtual-ns']
                    or value['state'] != 'armed' and actual > value['terminal-ns']):
                raise ValueError('Native timed mouse dispatch time is invalid')
    if steps[0]['deadline-ns'] != value['deadline-ns']:
        raise ValueError('Native timed mouse first deadline changed')
    if value['state'] == 'dispatched':
        if count != 2 or steps[-1]['dispatch-ns'] != value['dispatch-ns']:
            raise ValueError('Native timed mouse completion lacks both delivered edges')
    elif value['state'] != 'failed' and count == 2:
        raise ValueError('Native timed mouse completed prefix contradicts its state')
    prior = expected.get('native', {}).get('click')
    if prior is not None:
        if count < prior['dispatched-count']:
            raise ValueError('Native timed mouse dispatched prefix regressed')
        for old, new in zip(prior['steps'], steps, strict=True):
            if any(new.get(key) != item for key, item in old.items()):
                raise ValueError('Native timed mouse changed previously observed edge evidence')


def click_receipt(native, schedule):
    planned = schedule['click']
    steps = []
    for index, step in enumerate(native['click']['steps']):
        record = schedule['records'][index]
        steps.append(dict(sequence=record['sequence'], lease=record['lease'], button=step['button'],
            down=step['down'], delay_ns=step['delay-ns'], deadline_ns=step.get('deadline-ns'),
            dispatch_ns=step.get('dispatch-ns'),
            lateness_ns=(step['dispatch-ns'] - step['deadline-ns'] if 'dispatch-ns' in step else None)))
    count = native['click']['dispatched-count']
    return dict(format=FORMAT, button=planned['button'], hold_ms=planned['hold_ms'],
                dispatched_count=count, undispatched_count=2 - count, steps=steps,
                claim='Finite native PS/2 button callback prefix and final sync per edge, with no requested movement; '
                      'pre-existing native motion, external button state, cursor position, device FIFO acceptance '
                      'and guest consumption remain unknown.')


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Timed mouse click requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError('Timed mouse click host deadline expired')


def mouse_button_click(owner, button='left', *, hold_ms=80):
    """Validate and arm one pair without executing the VM or requesting movement."""
    from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
    from .qemu_input_schedule import INPUT_SCHEDULE_COMMANDS, _invalid, _native_schedule
    validate_mouse_click_parameters(button, hold_ms=hold_ms)
    owner._input_no_transaction()
    commands = MOUSE_CLICK_COMMANDS | INPUT_SCHEDULE_COMMANDS | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'}
    if (getattr(owner.vm, 'machine_configuration', {}).get('clock_profile', {}).get('profile') != 'virtual'
            or not commands <= getattr(owner.vm, 'qmp_commands', frozenset())):
        raise ValueError('Timed mouse clicks require the native virtual clock, input and mouse-click extensions')
    state = owner._input_storage()
    if state['pending'] or state['leases'] or owner._input_schedule_bound():
        raise ValueError('Timed mouse click requires an empty input queue and no owned held leases')
    _remaining(owner)
    clock = owner._input_schedule_context()
    prior = owner._input_schedule_read(clock)
    if prior['state'] == 'armed':
        raise ValueError('Cancel the current native input schedule before a timed mouse click')
    planned = _plan(button, hold_ms)
    if clock['virtual_ns'] + _EDGE_DELAY_NS + hold_ms * 1_000_000 > _MAX_NS:
        raise ValueError('Timed mouse click nominal horizon overflows signed nanoseconds')
    # Keep both edges and their one paired lifetime private until the whole
    # native arm is validated. An uncertain or late arm is never replayed.
    token = state['session_id'] + ':' + uuid.uuid4().hex
    leases = {token: dict(device='mouse', button=button, make='python_pending', release='python_pending')}
    records = [dict(sequence=state['sequence'] + index + 1, lease=token,
                    event=dict(type='btn', data=dict(button=button, down=step['down'])))
               for index, step in enumerate(planned['steps'])]
    schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'],
                    deadline_ns=clock['virtual_ns'] + _EDGE_DELAY_NS, records=records,
                    bound=True, applied_count=0, click=planned)
    _remaining(owner)
    received = result = None
    try:
        received = owner.vm.qmp.call('x-fdisbull-arm-mouse-click', {
            'token': schedule['token'], 'button': button, 'hold-ms': hold_ms})
        native = _native_schedule(owner, received, clock, schedule)
        if native['state'] != 'armed' or native['click']['dispatched-count']:
            _invalid(owner, 'Native mouse click arm did not leave a passive undelivered pair')
        _remaining(owner)
        state['pending'] = deepcopy(records)
        state['leases'] = leases
        state['sequence'] += 2
        state['schedule'] = schedule
        result = owner._input_schedule_accept(native, clock)
        owner._input_persist('input.schedule-arm', result)
        _remaining(owner)
        copied = deepcopy(result)
        _remaining(owner)
        return copied
    except BaseException as error:
        if getattr(error, 'result', None) is None:
            error.result = (deepcopy(result) if result is not None else
                dict(operation='mouse_button_click', click_plan=deepcopy(planned),
                     native=deepcopy(received), validation_failed=True))
        owner._input_invalidate('Native mouse click arm outcome is uncertain; pair must not be replayed')
        owner.vm.close()
        raise
