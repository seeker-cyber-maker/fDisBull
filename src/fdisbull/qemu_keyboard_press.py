"""One finite, passively armed chord on the native virtual clock.

Relative delays begin at actual dispatch callbacks. A stop cancels the suffix;
already dispatched makes remain owned holds until explicitly released.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid


KEYBOARD_PRESS_COMMANDS = frozenset({'x-fdisbull-arm-keyboard-press'})
FORMAT = 'fdisbull-keyboard-press-1'
_EDGE_DELAY_NS = 2_000_000
_MAX_NS = (1 << 63) - 1


def validate_keyboard_press_parameters(key, *, modifiers=(), hold_ms=40, gap_ms=40):
    """Validate shared physical names and strict native millisecond bounds."""
    from .keyboard_input import validate_keyboard
    from .qemu_input import _key
    for name, value in (('hold_ms', hold_ms), ('gap_ms', gap_ms)):
        if type(value) is not int or not 1 <= value <= 1000:
            raise ValueError(name + ' must be an integer in 1..1000')
    _key(key)
    validate_keyboard(key=key, modifiers=modifiers, hold_ms=hold_ms, gap_ms=gap_ms)


def _plan(key, modifiers, hold_ms, gap_ms):
    from .qemu_input import _key
    key, qcode = _key(key)
    names = [*modifiers, key, key, *reversed(modifiers)]
    codes = [_key(name)[1] for name in names]
    makes = len(modifiers) + 1
    steps = [dict(key=code, down=index < makes,
                  **{'delay-ns': hold_ms * 1_000_000 if index == makes else _EDGE_DELAY_NS})
             for index, code in enumerate(codes)]
    return dict(key=key, qcode=qcode, modifiers=list(modifiers),
                hold_ms=hold_ms, gap_ms=gap_ms, names=names, steps=steps)


def validate_native_press(value, expected):
    """Validate the entire native prefix before any host lease is changed."""
    planned = expected.get('press') if expected is not None else None
    if planned is None:
        if 'press' in value:
            raise ValueError('Ordinary native input invented a timed keyboard press')
        return
    press = value.get('press')
    fields = {'key', 'modifiers', 'hold-ms', 'gap-ms', 'steps', 'dispatched-count'}
    if (type(press) is not dict or set(press) != fields or 'retrace' in value
            or type(press['key']) is not str or press['key'] != planned['qcode']
            or type(press['modifiers']) is not list
            or any(type(item) is not str for item in press['modifiers'])
            or press['modifiers'] != planned['modifiers']
            or any(type(press[native]) is not int or press[native] != planned[public]
                   for native, public in (('hold-ms', 'hold_ms'), ('gap-ms', 'gap_ms')))
            or type(press['steps']) is not list or len(press['steps']) != len(planned['steps'])
            or type(press['dispatched-count']) is not int
            or not 0 <= press['dispatched-count'] <= len(planned['steps'])):
        raise ValueError('Invalid native timed keyboard plan or dispatched prefix')
    count = press['dispatched-count']
    steps = press['steps']
    for index, (step, declared) in enumerate(zip(steps, planned['steps'], strict=True)):
        keys = {'key', 'down', 'delay-ns'}
        if index <= count:
            keys.add('deadline-ns')
        if index < count:
            keys.add('dispatch-ns')
        if (type(step) is not dict or set(step) != keys
                or type(step['key']) is not str or step['key'] != declared['key']
                or type(step['down']) is not bool or step['down'] != declared['down']
                or type(step['delay-ns']) is not int or step['delay-ns'] != declared['delay-ns']):
            raise ValueError('Native timed keyboard step differs from its declared plan or prefix')
        if index <= count:
            due = (value['start-ns'] if index == 0 else steps[index - 1]['dispatch-ns']) + step['delay-ns']
            if (type(step['deadline-ns']) is not int or not 0 <= step['deadline-ns'] <= _MAX_NS
                    or step['deadline-ns'] != due):
                raise ValueError('Native timed keyboard deadline is not relative to the actual preceding callback')
        if index < count:
            actual = step['dispatch-ns']
            if (type(actual) is not int or not step['deadline-ns'] <= actual <= value['virtual-ns']
                    or value['state'] != 'armed' and actual > value['terminal-ns']):
                raise ValueError('Native timed keyboard dispatch time is invalid')
    if steps[0]['deadline-ns'] != value['deadline-ns']:
        raise ValueError('Native timed keyboard first deadline changed')
    if value['state'] == 'dispatched':
        if count != len(steps) or steps[-1]['dispatch-ns'] != value['dispatch-ns']:
            raise ValueError('Native timed keyboard completion lacks the whole delivered chord')
    elif value['state'] != 'failed' and count == len(steps):
        raise ValueError('Native timed keyboard completed prefix contradicts its state')
    prior = expected.get('native', {}).get('press')
    if prior is not None:
        if count < prior['dispatched-count']:
            raise ValueError('Native timed keyboard dispatched prefix regressed')
        for old, new in zip(prior['steps'], steps, strict=True):
            if any(new.get(key) != item for key, item in old.items()):
                raise ValueError('Native timed keyboard changed previously observed edge evidence')


def press_receipt(native, schedule):
    planned = schedule['press']
    steps = []
    for index, step in enumerate(native['press']['steps']):
        record = schedule['records'][index]
        steps.append(dict(sequence=record['sequence'], lease=record['lease'], key=planned['names'][index],
            qcode=step['key'], down=step['down'], delay_ns=step['delay-ns'],
            deadline_ns=step.get('deadline-ns'), dispatch_ns=step.get('dispatch-ns'),
            lateness_ns=(step['dispatch-ns'] - step['deadline-ns'] if 'dispatch-ns' in step else None)))
    count = native['press']['dispatched-count']
    return dict(format=FORMAT, key=planned['key'], modifiers=deepcopy(planned['modifiers']),
                hold_ms=planned['hold_ms'], gap_ms=planned['gap_ms'], gap_applied=False,
                dispatched_count=count, undispatched_count=len(steps) - count, steps=steps,
                claim='Finite native PS/2 callback prefix and final sync per edge; '
                      'device FIFO acceptance and guest consumption remain unknown. '
                      'gap_ms has no effect for one chord; there is no tail timer.')


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Timed keyboard press requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError('Timed keyboard press host deadline expired')


def keyboard_press(owner, key, *, modifiers=(), hold_ms=40, gap_ms=40):
    """Validate and arm once without running the VM or releasing other holds."""
    from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
    from .qemu_input_schedule import INPUT_SCHEDULE_COMMANDS, _invalid, _native_schedule
    validate_keyboard_press_parameters(key, modifiers=modifiers, hold_ms=hold_ms, gap_ms=gap_ms)
    owner._input_no_transaction()
    if (getattr(owner.vm, 'machine_configuration', {}).get('clock_profile', {}).get('profile') != 'virtual'
            or not KEYBOARD_PRESS_COMMANDS | INPUT_SCHEDULE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
                   <= getattr(owner.vm, 'qmp_commands', frozenset())):
        raise ValueError('Timed keyboard presses require qualified guest-time control with the native virtual clock and keyboard-press extension')
    state = owner._input_storage()
    if state['pending'] or state['leases'] or owner._input_schedule_bound():
        raise ValueError('Timed keyboard press requires an empty input queue and no owned held leases')
    _remaining(owner)
    clock = owner._input_schedule_context()
    prior = owner._input_schedule_read(clock)
    if prior['state'] == 'armed':
        raise ValueError('Cancel the current native input schedule before a timed keyboard press')
    planned = _plan(key, modifiers, hold_ms, gap_ms)
    if clock['virtual_ns'] + sum(step['delay-ns'] for step in planned['steps']) > _MAX_NS:
        raise ValueError('Timed keyboard press nominal horizon overflows signed nanoseconds')
    # Build candidate ownership separately. A refused arm cannot publish a
    # half-created queue; an accepted or uncertain late arm closes without replay.
    tokens = {name: state['session_id'] + ':' + uuid.uuid4().hex
              for name in [*planned['modifiers'], planned['key']]}
    leases = {token: dict(device='keyboard', key=name, make='python_pending', release='python_pending')
              for name, token in tokens.items()}
    records = [dict(sequence=state['sequence'] + index + 1, lease=tokens[planned['names'][index]],
                    event=dict(type='key', data=dict(key=dict(type='qcode', data=step['key']), down=step['down'])))
               for index, step in enumerate(planned['steps'])]
    schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'],
                    deadline_ns=clock['virtual_ns'] + _EDGE_DELAY_NS, records=records,
                    bound=True, applied_count=0, press=planned)
    _remaining(owner)
    received = result = None
    try:
        received = owner.vm.qmp.call('x-fdisbull-arm-keyboard-press', {
            'token': schedule['token'], 'key': planned['qcode'], 'modifiers': planned['modifiers'],
            'hold-ms': hold_ms, 'gap-ms': gap_ms})
        native = _native_schedule(owner, received, clock, schedule)
        if native['state'] != 'armed' or native['press']['dispatched-count']:
            _invalid(owner, 'Native keyboard press arm did not leave a passive undelivered chord')
        _remaining(owner)
        state['pending'] = deepcopy(records)
        state['leases'] = leases
        state['sequence'] += len(records)
        state['schedule'] = schedule
        result = owner._input_schedule_accept(native, clock)
        owner._input_persist('input.schedule-arm', result)
        _remaining(owner)
        return deepcopy(result)
    except BaseException as error:
        if getattr(error, 'result', None) is None:
            error.result = (deepcopy(result) if result is not None else
                dict(operation='keyboard_press', press_plan=deepcopy(planned),
                     native=deepcopy(received), validation_failed=True))
        owner._input_invalidate('Native keyboard press arm outcome is uncertain; chord must not be replayed')
        owner.vm.close()
        raise
