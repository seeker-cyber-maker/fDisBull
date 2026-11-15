"""Owned physical input queued in Python, then admitted once by running QEMU.

QMP acceptance is an input-device dispatch receipt. It does not establish guest
consumption, a completed frame, or any elapsed guest time. The owning machine
context serializes every public operation with its VM lock. Only its bounded
GDB-continue operation may call ``_input_after_continue``.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time
import uuid

from .dosbox_rpc import DebuggerError


FORMAT = 'fdisbull-qemu-physical-input-1'
MAX_PENDING_EDGES = 256
MAX_LEASES = 64
MAX_RELATIVE_DELTA = 32767
_BUTTONS = frozenset(('left', 'middle', 'right'))
_QCODE = {
    'escape': 'esc', 'enter': 'ret', 'space': 'spc', 'pageup': 'pgup',
    'pagedown': 'pgdn', 'kp5': 'kp_5', '-': 'minus', '=': 'equal',
    '[': 'bracket_left', ']': 'bracket_right', ';': 'semicolon',
    "'": 'apostrophe', '`': 'grave_accent', '\\': 'backslash',
    ',': 'comma', '.': 'dot', '/': 'slash',
}


def require_released_machine_input(vm):
    """Existing native state formats cannot restore Python input ownership."""
    state = getattr(vm, '_physical_input', None)
    if state is not None and (state['pending'] or state['leases'] or not state['valid']):
        raise ValueError('Native checkpoint requires released machine input and an empty physical queue')


def _key(value):
    # Import lazily: keyboard_input imports the public debugger validator.
    from .keyboard_input import KEYS
    if type(value) is not str or value not in KEYS:
        raise ValueError('Unknown keyboard key; use lowercase physical key names')
    value = 'escape' if value == 'esc' else value
    return value, _QCODE.get(value, value)


def _not_running(error):
    """Recognize only QEMU's explicit, non-delivering run-state rejection."""
    if not isinstance(error, DebuggerError):
        return False
    prefix = 'QMP input-send-event: '
    if not str(error).startswith(prefix):
        return False
    try:
        reply = json.loads(str(error)[len(prefix):])
    except (ValueError, TypeError):
        return False
    return (type(reply) is dict and reply.get('class') == 'GenericError'
            and reply.get('desc') == 'VM not running')


class QemuPhysicalInputMixin:
    """Owned physical edges and finite native virtual-clock input plans."""

    def _input_storage(self):
        state = getattr(self.vm, '_physical_input', None)
        if state is None:
            closed = getattr(self.vm, '_physical_input_closed', False) or self.vm.qmp is None
            state = dict(session_id=uuid.uuid4().hex, valid=not closed,
                         invalid_reason='VM closed' if closed else None,
                         sequence=0, pending=[], leases={}, last_delivery=None,
                         invalidated_edges=0, invalidated_leases=0)
            self.vm._physical_input = state
        return state

    def _input_no_transaction(self):
        project = getattr(self, 'project', None)
        if project is not None and project.db.in_transaction:
            raise ValueError('Physical input requires a project outside a caller-owned transaction')

    def _input_schedule_bound(self):
        state = getattr(self.vm, '_physical_input', None)
        return bool(state and state['valid'] and (state.get('schedule') or {}).get('bound'))

    def _input_prepare(self, *, allow_schedule=False):
        self._input_no_transaction()
        state = self._input_storage()
        if not state['valid'] or self.vm.qmp is None:
            raise ValueError('Physical input ownership is invalid or the VM is closed')
        if not allow_schedule and self._input_schedule_bound():
            raise ValueError('Resolve the scheduled input batch before queueing another physical edge')
        # A native schedule already excluded frame ownership when it armed.
        # Its observation/cancellation must remain possible until resolved.
        # New input still positively detaches an empty frame-key owner first.
        bound_schedule = allow_schedule and self._input_schedule_bound()
        if bound_schedule and getattr(self.vm, '_frame_key_owner', None) is not None:
            raise DebuggerError('Bound input schedule conflicts with frame-key ownership')
        frame_keys = getattr(self, '_frame_keys_before_physical_input', None)
        if frame_keys is not None and not bound_schedule:
            frame_keys()
        if 'input-send-event' not in getattr(self.vm, 'qmp_commands', ()):
            raise ValueError('Selected QEMU does not provide input-send-event')
        native = self.vm.qmp.call('query-status')
        if type(native) is not dict or type(native.get('running')) is not bool:
            raise DebuggerError('QEMU input admission requires a valid native run state')
        if native['running']:
            raise ValueError('Pause the machine before queueing or cancelling physical input')
        return state

    def _input_receipt(self, delivery, **fields):
        state = self._input_storage()
        return dict(format=FORMAT, context='machine', scope='owned VM input devices',
                    session_id=state['session_id'],
                    run=getattr(self, 'run_id', None), delivery=delivery,
                    guest_consumed=None, **fields)

    def _input_persist(self, operation, receipt):
        if getattr(self, 'project', None) is None:
            return
        try:
            self._event(operation, receipt)
        except BaseException:
            # An input transition may already exist in Python or in QEMU.
            # Never return an apparently usable session without its evidence.
            self._input_invalidate('Physical input evidence persistence failed')
            self.vm.close()
            raise

    def _input_invalidate(self, reason):
        state = self._input_storage()
        state['valid'] = False
        state['invalid_reason'] = reason
        state['invalidated_edges'] += len(state['pending'])
        state['invalidated_leases'] += len(state['leases'])
        state['pending'].clear()
        state['leases'].clear()
        if state.get('schedule') is not None:
            state['schedule'].get('lease_reservations', {}).clear()

    def _input_on_close(self):
        # Called by the VM owner before tearing down its transports. Closing a
        # machine invalidates leases; it never pretends to inject releases.
        self.vm._physical_input_closed = True
        state = getattr(self.vm, '_physical_input', None)
        if state is not None and state['valid']:
            self._input_invalidate('VM closed; no physical release was injected')

    def _input_pending(self):
        state = getattr(self.vm, '_physical_input', None)
        return bool(state is not None and state['valid'] and state['pending'])

    def _input_reserve(self, state, count, *, lease=False):
        if len(state['pending']) + count > MAX_PENDING_EDGES:
            raise ValueError('Physical input queue exceeds 256 pending edges')
        if lease and len(state['leases']) >= MAX_LEASES:
            raise ValueError('Physical input exceeds 64 active leases')

    def _input_append(self, state, event, *, lease=None):
        state['sequence'] += 1
        record = dict(sequence=state['sequence'], event=event, lease=lease)
        state['pending'].append(record)
        return record

    def _input_down(self, device, name, qcode=None):
        state = self._input_prepare()
        field = 'key' if device == 'keyboard' else 'button'
        if any(item['device'] == device and item[field] == name
               for item in state['leases'].values()):
            raise ValueError('This physical input already has an active lease')
        self._input_reserve(state, 1, lease=True)
        token = state['session_id'] + ':' + uuid.uuid4().hex
        lease = dict(device=device, **{field: name}, make='python_pending', release=None)
        event = (dict(type='key', data=dict(key=dict(type='qcode', data=qcode), down=True))
                 if device == 'keyboard' else dict(type='btn', data=dict(button=name, down=True)))
        state['leases'][token] = lease
        record = self._input_append(state, event, lease=token)
        result = self._input_receipt('python_pending', lease=token, **{field: name},
                                    sequence=record['sequence'], pending_edges=len(state['pending']),
                                    claim='Physical make scheduled in Python; QEMU dispatch and guest consumption are not established.')
        self._input_persist(device + '.key_down' if device == 'keyboard' else 'mouse.button_down', result)
        return result

    def _input_up(self, device, token):
        if type(token) is not str or not 1 <= len(token) <= 128:
            raise ValueError('Expected an owned unused physical input lease')
        state = self._input_prepare()
        lease = state['leases'].get(token)
        if lease is None or lease['device'] != device or lease['release'] is not None:
            raise ValueError('Expected an owned unused physical input lease')
        self._input_reserve(state, 1)
        field = 'key' if device == 'keyboard' else 'button'
        name = lease[field]
        event = (dict(type='key', data=dict(key=dict(type='qcode', data=_QCODE.get(name, name)), down=False))
                 if device == 'keyboard' else dict(type='btn', data=dict(button=name, down=False)))
        record = self._input_append(state, event, lease=token)
        lease['release'] = 'python_pending'
        result = self._input_receipt('python_pending', lease=token, **{field: name},
                                    sequence=record['sequence'], release='python_pending',
                                    pending_edges=len(state['pending']),
                                    claim='Physical break scheduled in Python; the release has not been dispatched or observed by the guest.')
        self._input_persist(device + '.key_up' if device == 'keyboard' else 'mouse.button_up', result)
        return result

    @property
    def keyboard(self):
        from .keyboard_input import GuestKeyboard
        return GuestKeyboard(self)

    def keyboard_key_down(self, key):
        key, qcode = _key(key)
        return self._input_down('keyboard', key, qcode)

    def keyboard_key_up(self, lease):
        return self._input_up('keyboard', lease)

    def keyboard_state(self):
        """Return the shared VM queue; physical keyboard state is not observed."""
        return self.input_state()

    def keyboard_press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
        from .qemu_keyboard_press import keyboard_press
        return keyboard_press(self, key, modifiers=modifiers, hold_ms=hold_ms, gap_ms=gap_ms)

    def keyboard_type(self, text, *, hold_ms=40, gap_ms=40):
        from .qemu_keyboard_type import keyboard_type
        return keyboard_type(self, text, hold_ms=hold_ms, gap_ms=gap_ms)

    def mouse_move_relative(self, dx, dy):
        if (type(dx) is not int or type(dy) is not int
                or not -MAX_RELATIVE_DELTA <= dx <= MAX_RELATIVE_DELTA
                or not -MAX_RELATIVE_DELTA <= dy <= MAX_RELATIVE_DELTA
                or dx == dy == 0):
            raise ValueError('Relative mouse deltas must be integers in -32767..32767 with at least one nonzero axis')
        state = self._input_prepare()
        events = [dict(type='rel', data=dict(axis=axis, value=value))
                  for axis, value in (('x', dx), ('y', dy)) if value]
        self._input_reserve(state, len(events))
        records = [self._input_append(state, event) for event in events]
        result = self._input_receipt('python_pending', dx=dx, dy=dy,
                                    sequences=[item['sequence'] for item in records],
                                    pending_edges=len(state['pending']),
                                    claim='Relative controller motion scheduled in Python; no screen position or guest consumption is established.')
        self._input_persist('mouse.move_relative', result)
        return result

    def mouse_button_down(self, button):
        if type(button) is not str or button not in _BUTTONS:
            raise ValueError('Mouse button must be left, middle or right')
        return self._input_down('mouse', button)

    def mouse_button_up(self, lease):
        return self._input_up('mouse', lease)

    def mouse_button_click(self, button='left', *, hold_ms=80):
        from .qemu_mouse_click import mouse_button_click
        return mouse_button_click(self, button, hold_ms=hold_ms)

    def mouse_move_mapped(self, dx_pixels, dy_pixels, *, counts_per_pixel, window,
                          update_id, configuration_generation, timeout_ms=1000):
        from .qemu_mapped_mouse import mouse_move_mapped
        return mouse_move_mapped(self, dx_pixels, dy_pixels, counts_per_pixel=counts_per_pixel,
            window=window, update_id=update_id, configuration_generation=configuration_generation,
            timeout_ms=timeout_ms)

    def input_state(self):
        state = self._input_storage()
        return dict(format=FORMAT, context='machine', scope='owned VM input devices',
                    session_id=state['session_id'], run=getattr(self, 'run_id', None),
                    valid=state['valid'], invalid_reason=state['invalid_reason'],
                    pending_edges=len(state['pending']), pending=deepcopy(state['pending']),
                    leases=deepcopy(state['leases']), last_delivery=deepcopy(state['last_delivery']),
                    schedule=deepcopy(state.get('schedule_receipt')),
                    invalidated_edges=state['invalidated_edges'], invalidated_leases=state['invalidated_leases'],
                    guest_consumed=None, physical_state='not observed',
                    semantics='Owned queue and last validated receipts; scheduled dispatch reports virtual time separately, never device acceptance, guest consumption, pixel position or frame completion')

    def input_cancel_pending(self):
        state = self._input_prepare(allow_schedule=True)
        cancel_native = getattr(self, '_input_schedule_before_cancel', None)
        scheduled = cancel_native() if cancel_native is not None else None
        count = len(state['pending'])
        cancelled, retained = [], []
        for token, lease in list(state['leases'].items()):
            if lease['make'] == 'python_pending':
                cancelled.append(token)
                del state['leases'][token]
            else:
                lease['release'] = None
                retained.append(token)
        state['pending'].clear()
        if state.get('schedule') is not None:
            state['schedule']['bound'] = False
            state['schedule_receipt']['requires_resolution'] = False
        reservations = (state.get('schedule') or {}).get('lease_reservations')
        cancelled_reservations = list(reservations) if reservations is not None else None
        if reservations is not None:
            reservations.clear()
        if scheduled is not None:
            scheduled['requires_resolution'] = False
        result = self._input_receipt('cancelled_unsent', cancelled_edges=count,
                                    cancelled_leases=cancelled, retained_dispatched_holds=retained,
                                    claim='Only unsent transitions cancelled; accepted holds still require an explicit release.')
        if scheduled is not None:
            result['schedule'] = scheduled
        if cancelled_reservations is not None:
            result['cancelled_reserved_leases'] = cancelled_reservations
        self._input_persist('input.cancel_pending', result)
        return result

    def _input_mark_dispatched(self, state, records, delivery):
        """Commit one confirmed dispatch into the existing lease ledger."""
        for record in records:
            if record['lease'] is None:
                continue
            lease = state['leases'][record['lease']]
            if record['event']['data']['down']:
                lease['make'] = delivery
            else:
                del state['leases'][record['lease']]
        state['pending'].clear()

    def _input_mark_prefix_dispatched(self, state, records, delivery):
        """Commit a validated finite-press prefix without discarding its suffix."""
        if state['pending'][:len(records)] != records:
            raise DebuggerError('Owned timed keyboard pending prefix changed')
        # Check the complete update against a private ledger before publishing
        # any make/break transition. No partial host commit can hide an error.
        leases = deepcopy(state['leases'])
        for record in records:
            lease = leases.get(record['lease'])
            if lease is None or lease['device'] != 'keyboard':
                raise DebuggerError('Owned timed keyboard lease disappeared')
            if record['event']['data']['down']:
                if lease['make'] != 'python_pending':
                    raise DebuggerError('Owned timed keyboard make was already dispatched')
                lease['make'] = delivery
            else:
                if lease['make'] != delivery or lease['release'] != 'python_pending':
                    raise DebuggerError('Owned timed keyboard break has no dispatched make')
                del leases[record['lease']]
        state['leases'] = leases
        del state['pending'][:len(records)]

    def _input_mark_text_prefix_dispatched(self, state, schedule, records, delivery):
        """Atomically activate future makes and consume only their paired breaks.

        A 64-character text can reserve 128 distinct lifetimes but holds at most
        two keys at once. Future reservations never occupy active lease slots.
        The entire newly validated prefix is reconciled privately before commit.
        """
        if state['pending'][:len(records)] != records:
            raise DebuggerError('Owned timed text pending prefix changed')
        leases = deepcopy(state['leases'])
        reservations = deepcopy(schedule['lease_reservations'])
        if len(reservations) > MAX_PENDING_EDGES // 2:
            raise DebuggerError('Owned timed text reservations exceed the bounded plan')
        for record in records:
            token = record['lease']
            event = record['event']['data']
            if event['down']:
                reserved = reservations.pop(token, None)
                if (reserved is None or set(reserved) != {'device', 'key'}
                        or reserved['device'] != 'keyboard' or token in leases
                        or _QCODE.get(reserved['key'], reserved['key']) != event['key']['data']
                        or any(lease['device'] == 'keyboard' and lease['key'] == reserved['key']
                               for lease in leases.values())
                        or len(leases) >= MAX_LEASES):
                    raise DebuggerError('Owned timed text make has no unique reserved lifetime')
                leases[token] = dict(reserved, make=delivery, release='python_pending')
            else:
                lease = leases.get(token)
                if (lease is None or lease['device'] != 'keyboard'
                        or _QCODE.get(lease['key'], lease['key']) != event['key']['data']
                        or lease['make'] != delivery or lease['release'] != 'python_pending'):
                    raise DebuggerError('Owned timed text break has no dispatched make')
                del leases[token]
        state['leases'] = leases
        schedule['lease_reservations'] = reservations
        del state['pending'][:len(records)]

    def _input_mark_click_prefix_dispatched(self, state, records, delivery):
        """Commit a validated mouse prefix against one private paired ledger."""
        if state['pending'][:len(records)] != records:
            raise DebuggerError('Owned timed mouse pending prefix changed')
        leases = deepcopy(state['leases'])
        for record in records:
            event = record['event']
            data = event.get('data') if type(event) is dict else None
            lease = leases.get(record['lease'])
            if (lease is None or lease['device'] != 'mouse'
                    or type(event) is not dict or set(event) != {'type', 'data'}
                    or event['type'] != 'btn' or type(data) is not dict
                    or set(data) != {'button', 'down'} or type(data['down']) is not bool
                    or type(data['button']) is not str or data['button'] not in _BUTTONS
                    or data['button'] != lease['button']):
                raise DebuggerError('Owned timed mouse edge has no matching mouse lease')
            if data['down']:
                if lease['make'] != 'python_pending' or lease['release'] != 'python_pending':
                    raise DebuggerError('Owned timed mouse make lost its pending paired release')
                lease['make'] = delivery
            else:
                if lease['make'] != delivery or lease['release'] != 'python_pending':
                    raise DebuggerError('Owned timed mouse break has no dispatched make')
                del leases[record['lease']]
        state['leases'] = leases
        del state['pending'][:len(records)]

    def _input_after_continue(self, deadline):
        """Try once after GDB continue; never resume or retry an input batch.

        Cross-channel ordering is not atomic. A stopped observation or the
        explicit QMP run-state rejection leaves the queue unsent. Even a
        successful batch can precede an immediate breakpoint without the guest
        consuming any of its events.
        """
        self._input_no_transaction()
        state = self._input_storage()
        if not state['valid']:
            raise ValueError('Physical input ownership is invalid')
        if self._input_schedule_bound():
            raise ValueError('Native scheduled input cannot use immediate QMP dispatch')
        records = deepcopy(state['pending'])
        if not records:
            return self._input_receipt('not_dispatched', reason='No pending physical input', edge_count=0)

        def remaining():
            value = int((deadline - time.monotonic()) * 1000)
            if value <= 0:
                raise TimeoutError('Physical input dispatch deadline expired')
            return min(value, 600000)

        def not_dispatched(reason, native=None):
            receipt = self._input_receipt('not_dispatched', reason=reason, native_status=native,
                                          edge_count=len(records), pending_edges=len(state['pending']))
            state['last_delivery'] = receipt
            self._input_persist('input.dispatch', receipt)
            return deepcopy(receipt)

        if deadline <= time.monotonic():
            return not_dispatched('Operation deadline expired before input dispatch')
        try:
            native = self.vm.qmp.call('query-status', timeout_ms=remaining())
        except BaseException:
            self._input_invalidate('QMP status failed during owned input execution')
            self.vm.close()
            raise
        if type(native) is not dict or type(native.get('running')) is not bool:
            self._input_invalidate('Invalid QMP status during owned input execution')
            self.vm.close()
            raise DebuggerError('QEMU input dispatch requires a valid native run state')
        if not native['running']:
            return not_dispatched('QEMU was not running at input admission', native)
        if deadline <= time.monotonic():
            return not_dispatched('Operation deadline expired before input dispatch', native)
        try:
            reply = self.vm.qmp.call('input-send-event', {'events': [item['event'] for item in records]},
                                     timeout_ms=remaining())
            if reply != {}:
                raise DebuggerError('Unexpected QMP input dispatch acknowledgement')
        except BaseException as error:
            if _not_running(error):
                return not_dispatched('QEMU stopped before accepting the input batch', native)
            receipt = self._input_receipt('delivery_unknown', edge_count=len(records),
                                          reason=type(error).__name__,
                                          claim='Input dispatch outcome is uncertain; ownership invalidated and VM closed without replay.')
            state['last_delivery'] = receipt
            self._input_invalidate('QMP input delivery is unknown; batch must not be replayed')
            try:
                self._input_persist('input.dispatch', receipt)
            finally:
                self.vm.close()
            raise
        self._input_mark_dispatched(state, records, 'qmp_accepted')
        receipt = self._input_receipt('qmp_accepted', edge_count=len(records),
                                      sequences=[item['sequence'] for item in records],
                                      pending_edges=0,
                                      claim='QEMU accepted physical input events; guest consumption and elapsed guest time are not established.')
        state['last_delivery'] = receipt
        self._input_persist('input.dispatch', receipt)
        return deepcopy(receipt)
