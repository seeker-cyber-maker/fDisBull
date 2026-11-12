"""Shared, bounded action continuations over provider-owned observations.

The backing supplies preparation, original input and evidence predicates. This
module never invents an effect or repeats an input while waiting for arrival.
"""
from copy import deepcopy
import uuid


class ActionContinuation:
    def __init__(self, action, *, event=None, max_slices=12, slice_ms=500):
        if not isinstance(action, str) or not 1 <= len(action) <= 128:
            raise ValueError('Invalid continuation action')
        if type(max_slices) is not int or not 0 <= max_slices <= 120:
            raise ValueError('Invalid continuation observation budget')
        if type(slice_ms) is not int or not 1 <= slice_ms <= 1000:
            raise ValueError('Invalid continuation time slice')
        self.event = event or (lambda item: None)
        self.max_slices, self.slice_ms = max_slices, slice_ms
        self.record = {'id': uuid.uuid4().hex, 'action': action, 'input': 'not_sent',
                       'effect': 'unknown', 'arrival': 'pending', 'destination': None,
                       'slices': 0, 'requested_guest_ms': 0}

    def _emit(self, stage, **detail):
        self.event({'phase': 'action_continuation', 'stage': stage,
                    'continuation': deepcopy(self.record), **detail})

    def send_once(self, send, *, prepare=None):
        if self.record['input'] != 'not_sent':
            raise ValueError('Continuation input has already been attempted')
        if prepare is not None:
            prepare()
            self._emit('prepared')
        # Record uncertainty BEFORE crossing the original-input boundary.
        self.record['input'] = 'attempted'
        self._emit('input-attempted')
        result = send()
        if isinstance(result, dict) and result.get('accepted') is True and result.get('delivery') == 'queued':
            self.record['input'] = 'queued'
        self._emit('input-result', result=result)
        return result

    def wait(self, observe, advance):
        """Observe {destinations, interruptions, evidence}; advance sends no input.

        More than one destination is ambiguous. A known interruption or an
        unmatched transition may settle within the remaining guest-time budget.
        Calling wait again never renews that budget or resends the action.
        """
        while True:
            observed = observe()
            destinations = observed['destinations']
            interruptions = observed['interruptions']
            if (not isinstance(destinations, list) or not isinstance(interruptions, list)
                    or not all(isinstance(x, str) for x in destinations + interruptions)):
                raise ValueError('Invalid continuation observation')
            self._emit('observation', observation=deepcopy(observed), following_input='not_sent')
            if len(destinations) == 1 and not interruptions:
                self.record.update(arrival='qualified', destination=destinations[0])
                self._emit('arrival-qualified')
                return deepcopy(self.record)
            if len(destinations) > 1 or self.record['slices'] >= self.max_slices:
                self.record['arrival'] = 'ambiguous' if len(destinations) > 1 else 'unqualified'
                self._emit('arrival-incomplete')
                return deepcopy(self.record)
            # Consume the budget before the callback, including failed advances.
            self.record['slices'] += 1
            self.record['requested_guest_ms'] += self.slice_ms
            advance(self.slice_ms)

    def confirm_effect(self):
        """Only a backing's independently qualified effect may call this."""
        if self.record['input'] != 'queued' or self.record['arrival'] != 'qualified':
            raise ValueError('Effect confirmation lacks qualified input/arrival')
        self.record['effect'] = 'applied-confirmed'
        self._emit('effect-confirmed')
        return deepcopy(self.record)
