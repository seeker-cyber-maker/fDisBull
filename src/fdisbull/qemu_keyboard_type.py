"""One finite US-layout text plan on the native virtual clock.

Each character owns fresh key lifetimes. Future makes reserve identities in
the plan, separately from held leases; only validated callbacks activate them.
The caller explicitly executes the guest and resolves any interrupted suffix.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid


KEYBOARD_TYPE_COMMANDS = frozenset({'x-fdisbull-arm-keyboard-type'})
FORMAT = 'fdisbull-keyboard-type-1'
_EDGE_DELAY_NS = 2_000_000
_MAX_NS = (1 << 63) - 1
_SHIFTED = dict(zip('!@#$%^&*()_+{}|:"<>?~', "1234567890-=[]\\;',./`", strict=True))


def validate_keyboard_type_parameters(text, *, hold_ms=40, gap_ms=40):
    """Reject the complete unsupported text before any admission or mutation."""
    from .keyboard_input import validate_keyboard
    if type(text) is not str:
        raise ValueError('text requires 1..64 US-layout ASCII characters')
    for name, value in (('hold_ms', hold_ms), ('gap_ms', gap_ms)):
        if type(value) is not int or not 1 <= value <= 1000:
            raise ValueError(name + ' must be an integer in 1..1000')
    validate_keyboard(text=text, hold_ms=hold_ms, gap_ms=gap_ms)


def _plan(text, hold_ms, gap_ms):
    from .qemu_input import _key
    names, character_indices, steps = [], [], []
    for character_index, char in enumerate(text):
        shifted = 'A' <= char <= 'Z' or char in _SHIFTED
        name = (_SHIFTED[char] if char in _SHIFTED else char.lower() if shifted
                else {' ': 'space', '\r': 'enter', '\n': 'enter', '\t': 'tab'}.get(char, char))
        chord = ([('shift', True, _EDGE_DELAY_NS)] if shifted else [])
        chord += [(name, True, _EDGE_DELAY_NS), (name, False, hold_ms * 1_000_000)]
        if shifted:
            chord.append(('shift', False, _EDGE_DELAY_NS))
        for index, (key, down, delay) in enumerate(chord):
            if character_index and index == 0:
                delay += gap_ms * 1_000_000
            names.append(key)
            character_indices.append(character_index)
            steps.append(dict(key=_key(key)[1], down=down, **{'delay-ns': delay}))
    return dict(text=text, hold_ms=hold_ms, gap_ms=gap_ms, names=names,
                character_indices=character_indices, steps=steps)


def validate_native_typing(value, expected):
    """Validate all immutable steps and callback evidence before lease commit."""
    planned = expected.get('typing') if expected is not None else None
    if planned is None:
        if 'typing' in value:
            raise ValueError('Other native input invented a timed keyboard text plan')
        return
    typing = value.get('typing')
    fields = {'text', 'hold-ms', 'gap-ms', 'steps', 'dispatched-count'}
    if (type(typing) is not dict or set(typing) != fields or 'press' in value or 'retrace' in value
            or type(typing['text']) is not str or typing['text'] != planned['text']
            or any(type(typing[native]) is not int or typing[native] != planned[public]
                   for native, public in (('hold-ms', 'hold_ms'), ('gap-ms', 'gap_ms')))
            or type(typing['steps']) is not list or len(typing['steps']) != len(planned['steps'])
            or type(typing['dispatched-count']) is not int
            or not 0 <= typing['dispatched-count'] <= len(planned['steps'])):
        raise ValueError('Invalid native timed text plan or dispatched prefix')
    count, steps = typing['dispatched-count'], typing['steps']
    for index, (step, declared) in enumerate(zip(steps, planned['steps'], strict=True)):
        fields = {'key', 'down', 'delay-ns'}
        if index <= count:
            fields.add('deadline-ns')
        if index < count:
            fields.add('dispatch-ns')
        if (type(step) is not dict or set(step) != fields
                or type(step['key']) is not str or step['key'] != declared['key']
                or type(step['down']) is not bool or step['down'] != declared['down']
                or type(step['delay-ns']) is not int or step['delay-ns'] != declared['delay-ns']):
            raise ValueError('Native timed text step differs from its declared plan or prefix')
        if index <= count:
            due = (value['start-ns'] if index == 0 else steps[index - 1]['dispatch-ns']) + step['delay-ns']
            if (type(step['deadline-ns']) is not int or not 0 <= step['deadline-ns'] <= _MAX_NS
                    or step['deadline-ns'] != due):
                raise ValueError('Native timed text deadline is not relative to the actual preceding callback')
        if index < count:
            actual = step['dispatch-ns']
            if (type(actual) is not int or not step['deadline-ns'] <= actual <= value['virtual-ns']
                    or value['state'] != 'armed' and actual > value['terminal-ns']):
                raise ValueError('Native timed text dispatch time is invalid')
    if steps[0]['deadline-ns'] != value['deadline-ns']:
        raise ValueError('Native timed text first deadline changed')
    if value['state'] == 'dispatched':
        if count != len(steps) or steps[-1]['dispatch-ns'] != value['dispatch-ns']:
            raise ValueError('Native timed text completion lacks the whole delivered plan')
    elif value['state'] != 'failed' and count == len(steps):
        raise ValueError('Native timed text completed prefix contradicts its state')
    prior = expected.get('native', {}).get('typing')
    if prior is not None:
        if count < prior['dispatched-count']:
            raise ValueError('Native timed text dispatched prefix regressed')
        for old, new in zip(prior['steps'], steps, strict=True):
            if any(new.get(key) != item for key, item in old.items()):
                raise ValueError('Native timed text changed previously observed edge evidence')


def typing_receipt(native, schedule):
    planned = schedule['typing']
    steps = []
    for index, step in enumerate(native['typing']['steps']):
        record = schedule['records'][index]
        steps.append(dict(sequence=record['sequence'], lease=record['lease'],
            key=planned['names'][index], qcode=step['key'], down=step['down'],
            character_index=planned['character_indices'][index], delay_ns=step['delay-ns'],
            deadline_ns=step.get('deadline-ns'), dispatch_ns=step.get('dispatch-ns'),
            lateness_ns=(step['dispatch-ns'] - step['deadline-ns'] if 'dispatch-ns' in step else None)))
    count = native['typing']['dispatched-count']
    return dict(format=FORMAT, text=planned['text'], hold_ms=planned['hold_ms'], gap_ms=planned['gap_ms'],
                dispatched_count=count, undispatched_count=len(steps) - count, steps=steps,
                claim='Finite US-layout physical-key callback prefix and final sync per edge; '
                      'guest layout, lock state, FIFO acceptance and text consumption remain unknown. '
                      'Gaps precede later characters only; there is no trailing gap timer.')


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Timed keyboard text requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError('Timed keyboard text host deadline expired')


def keyboard_type(owner, text, *, hold_ms=40, gap_ms=40):
    """Passively arm a complete text plan without executing or replaying it."""
    from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
    from .qemu_input import MAX_PENDING_EDGES
    from .qemu_input_schedule import INPUT_SCHEDULE_COMMANDS, _invalid, _native_schedule
    validate_keyboard_type_parameters(text, hold_ms=hold_ms, gap_ms=gap_ms)
    owner._input_no_transaction()
    if (getattr(owner.vm, 'machine_configuration', {}).get('clock_profile', {}).get('profile') != 'virtual'
            or not KEYBOARD_TYPE_COMMANDS | INPUT_SCHEDULE_COMMANDS | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'}
                   <= getattr(owner.vm, 'qmp_commands', frozenset())):
        raise ValueError('Timed keyboard text requires qualified guest-time control with the native virtual clock and keyboard-type extension')
    state = owner._input_storage()
    if state['pending'] or state['leases'] or owner._input_schedule_bound():
        raise ValueError('Timed keyboard text requires an empty input queue and no owned held leases')
    _remaining(owner)
    clock = owner._input_schedule_context()
    prior = owner._input_schedule_read(clock)
    if prior['state'] == 'armed':
        raise ValueError('Cancel the current native input schedule before timed keyboard text')
    planned = _plan(text, hold_ms, gap_ms)
    if len(planned['steps']) > MAX_PENDING_EDGES:
        raise ValueError('Timed keyboard text exceeds the bounded physical input queue')
    if clock['virtual_ns'] + sum(step['delay-ns'] for step in planned['steps']) > _MAX_NS:
        raise ValueError('Timed keyboard text nominal horizon overflows signed nanoseconds')
    # Reservations are bounded future lifetimes, not active held leases. Each
    # repeated key/Shift gets a new identity; a consumed lifetime is never reused.
    reservations, active, records = {}, {}, []
    for index, step in enumerate(planned['steps']):
        name = planned['names'][index]
        if step['down']:
            token = state['session_id'] + ':' + uuid.uuid4().hex
            reservations[token] = dict(device='keyboard', key=name)
            active[name] = token
        else:
            token = active.pop(name)
        records.append(dict(sequence=state['sequence'] + index + 1, lease=token,
            event=dict(type='key', data=dict(key=dict(type='qcode', data=step['key']), down=step['down']))))
    schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'],
        deadline_ns=clock['virtual_ns'] + _EDGE_DELAY_NS, records=records,
        bound=True, applied_count=0, typing=planned, lease_reservations=reservations)
    _remaining(owner)
    received = result = None
    try:
        received = owner.vm.qmp.call('x-fdisbull-arm-keyboard-type', {
            'token': schedule['token'], 'text': text, 'hold-ms': hold_ms, 'gap-ms': gap_ms})
        native = _native_schedule(owner, received, clock, schedule)
        if native['state'] != 'armed' or native['typing']['dispatched-count']:
            _invalid(owner, 'Native keyboard text arm did not leave a passive undelivered plan')
        _remaining(owner)
        state['pending'] = deepcopy(records)
        state['sequence'] += len(records)
        state['schedule'] = schedule
        result = owner._input_schedule_accept(native, clock)
        owner._input_persist('input.schedule-arm', result)
        _remaining(owner)
        return deepcopy(result)
    except BaseException as error:
        if getattr(error, 'result', None) is None:
            error.result = (deepcopy(result) if result is not None else
                dict(operation='keyboard_type', typing_plan=deepcopy(planned),
                     native=deepcopy(received), validation_failed=True))
        owner._input_invalidate('Native keyboard text arm outcome is uncertain; text must not be replayed')
        owner.vm.close()
        raise
