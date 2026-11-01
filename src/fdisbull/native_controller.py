"""Bounded ordinary-input control for an existing native debug session.

The caller owns state interpretation, explicit owned-stop handling and cleanup.
This controller never edits guest state or retries an uncertain side effect.
"""
import math
import time
from copy import deepcopy


class NativeControlError(RuntimeError):
    pass


def _positive(value, label, *, zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or not zero and value == 0):
        raise ValueError(label+' must be a finite '+('nonnegative' if zero else 'positive')+' number')
    return value


class BoundedNativeController:
    """Reuse budgets, a transport journal, input settlement and bounded waits.

    ``stop_handler`` must explicitly return True for a stop it owns and has
    resolved. It accounts for any execution it performs with ``account_guest``.
    Errors latch this controller; observations and cleanup remain caller-owned.
    Construct a new controller only after the caller establishes a new valid
    context. A fresh controller does not itself recover an uncertain guest.
    """
    def __init__(self, session, *, read_state, total_guest_ms, total_timeout_ms,
                 journal=None, inputs=None, stop_handler=None, fast_forward=False,
                 clock=time.monotonic, admission_check=None, input_advance=None):
        _positive(total_guest_ms, 'Guest budget');_positive(total_timeout_ms, 'Wall budget')
        if not callable(read_state) or not callable(clock) or stop_handler is not None and not callable(stop_handler):
            raise ValueError('State reader, clock and optional stop handler must be callable')
        if any(value is not None and not callable(value) for value in (admission_check,input_advance)):
            raise ValueError('Optional admission and input-execution adapters must be callable')
        if type(fast_forward) is not bool or journal is not None and not isinstance(journal, list) or inputs is not None and not isinstance(inputs, list):
            raise ValueError('Invalid controller journal, inputs or fast-forward setting')
        self.session, self.read_state, self.stop_handler = session, read_state, stop_handler
        self.admission_check, self.input_advance = admission_check, input_advance
        self.journal = [] if journal is None else journal
        self.inputs = [] if inputs is None else inputs
        self.guest_budget_ms, self.wall_budget_ms = total_guest_ms, total_timeout_ms
        self.clock = clock;self.deadline = clock()+total_timeout_ms/1000
        self.guest_elapsed = 0;self.fast_forward = fast_forward
        self.blocked_reason = None;self.waits = []
        self.last_observation = None;self.last_keyboard_state = None

    def status(self):
        return {'guest_elapsed_ms': self.guest_elapsed, 'guest_budget_ms': self.guest_budget_ms,
                'wall_budget_ms': self.wall_budget_ms, 'blocked_reason': self.blocked_reason,
                'input_count': len(self.inputs), 'waits': deepcopy(self.waits),
                'last_observation': deepcopy(self.last_observation),
                'last_keyboard_state': deepcopy(self.last_keyboard_state)}

    def _active(self):
        if self.blocked_reason is not None:
            raise NativeControlError('Controller stopped: '+self.blocked_reason)
        if self.clock() >= self.deadline or self.guest_elapsed >= self.guest_budget_ms:
            self.blocked_reason = 'route budget exhausted'
            raise NativeControlError(self.blocked_reason)
        if self.admission_check is not None:
            try:self.admission_check()
            except BaseException as error:self._block(error);raise

    def _block(self, error):
        if self.blocked_reason is None:
            self.blocked_reason = type(error).__name__+': '+str(error)

    def remaining_limits(self, guest=100, wall=10000):
        self._active();_positive(guest, 'Slice guest budget');_positive(wall, 'Slice wall budget')
        g = min(int(guest), int(self.guest_budget_ms-self.guest_elapsed))
        w = min(int(wall), int((self.deadline-self.clock())*1000))
        if g <= 0 or w <= 0:
            raise NativeControlError('No whole-millisecond budget remains')
        return g, w

    def account_guest(self, elapsed):
        """Account measured guest progress, including explicitly owned observers."""
        try:
            _positive(elapsed, 'Returned guest progress', zero=True)
            self.guest_elapsed += elapsed
            if self.guest_elapsed > self.guest_budget_ms or self.clock() >= self.deadline:
                raise NativeControlError('Route budget exhausted after native execution')
        except BaseException as error:
            self._block(error);raise

    def advance(self, ms=100):
        self._active();_positive(ms, 'Advance duration')
        end = self.guest_elapsed+ms
        try:
            while self.guest_elapsed < end:
                guest, wall = self.remaining_limits(min(100, end-self.guest_elapsed), 10000)
                attempt = {'kind': 'run', 'attempted': True, 'result': None}
                self.journal.append(attempt)
                try:
                    out = self.session.run(guest_ms=guest, timeout_ms=wall,
                                           fast_forward=self.fast_forward, stop_on_hook=True)
                except BaseException as error:
                    attempt['error'] = str(error);raise
                attempt['result'] = deepcopy(out)
                if not isinstance(out, dict) or 'guest_elapsed_ms' not in out:
                    raise NativeControlError('Missing native progress result')
                self.account_guest(out['guest_elapsed_ms'])
                if out.get('outcome') == 'guest_time' and not out.get('hook_hits'):
                    if out['guest_elapsed_ms'] == 0:
                        raise NativeControlError('Native slice returned no guest progress')
                elif self.stop_handler is None or self.stop_handler(out) is not True:
                    raise NativeControlError('Foreign or unresolved native stop preserved')
            if self.clock() >= self.deadline:
                raise NativeControlError('Wall budget exhausted after owned stop')
            observed = self.read_state();self.last_observation = deepcopy(observed)
            if self.clock() >= self.deadline:
                raise NativeControlError('Wall budget exhausted after observation')
            return observed
        except BaseException as error:
            self._block(error);raise

    def _idle(self):
        record = self.session.keyboard_state()
        self.last_keyboard_state = deepcopy(record)
        if self.clock() >= self.deadline:
            raise NativeControlError('Wall budget exhausted after keyboard observation')
        k = record.get('keyboard', {}) if isinstance(record, dict) else {}
        return all(type(k.get(n)) is int and k[n] == 0
                   for n in ('pending_events', 'owned_keys', 'queued_guest_ms'))

    def _input(self, name, send, guest_ms):
        self._active()
        try:
            if not self._idle():
                raise NativeControlError('Existing keyboard input is not settled')
            item = {'kind': 'keyboard', 'key': name, 'delivered': None, 'complete': False}
            self.inputs.append(item);self.journal.append({'kind': 'input', 'record': item})
            try:
                receipt = send()
            except BaseException as error:
                item['error'] = str(error);raise
            item['delivery'] = deepcopy(receipt)
            accepted = receipt.get('accepted') if isinstance(receipt, dict) else None
            item['delivered'] = accepted if type(accepted) is bool else None
            # No execution, retry or additional input after an uncertain delivery.
            if item['delivered'] is not True:
                raise NativeControlError('Input rejected or delivery outcome unknown')
            (self.input_advance or self.advance)(guest_ms)
            item['complete'] = self._idle()
            if not item['complete']:
                raise NativeControlError('Input consumption is not settled')
            return receipt
        except BaseException as error:
            self._block(error);raise

    def press(self, key, ms=150, *, hold_ms=60, gap_ms=50):
        if not isinstance(key, str) or not key:
            raise ValueError('Nonempty key required')
        _positive(ms, 'Input execution budget');_positive(hold_ms, 'Hold duration')
        _positive(gap_ms, 'Gap duration', zero=True)
        return self._input('press:'+key,
                           lambda: self.session.keyboard_press(key, hold_ms=hold_ms, gap_ms=gap_ms),
                           max(ms, hold_ms+gap_ms))

    def type_text(self, text, *, hold_ms=30, gap_ms=30, guest_ms=None):
        if not isinstance(text, str) or not text:
            raise ValueError('Nonempty text required')
        _positive(hold_ms, 'Hold duration');_positive(gap_ms, 'Gap duration', zero=True)
        ms = len(text)*(hold_ms+gap_ms)+150 if guest_ms is None else guest_ms
        _positive(ms, 'Text execution budget')
        return self._input('type:'+text,
                           lambda: self.session.keyboard_type(text, hold_ms=hold_ms, gap_ms=gap_ms), ms)

    def wait(self, predicate, label, budget=3000, *, slice_ms=50):
        if not callable(predicate) or not isinstance(label, str) or not label:
            raise ValueError('Wait needs a predicate and label')
        _positive(budget, 'Wait guest budget');_positive(slice_ms, 'Wait slice')
        self._active();end = min(self.guest_elapsed+budget, self.guest_budget_ms)
        record = {'label': label, 'guest_start': self.guest_elapsed, 'polls': 0,
                  'last_observation': None, 'complete': False}
        self.waits.append(record);self.journal.append({'kind': 'wait', 'record': record})
        try:
            while True:
                if self.blocked_reason is not None:
                    raise NativeControlError('Controller stopped: '+self.blocked_reason)
                if self.clock() >= self.deadline:
                    raise NativeControlError('Wait wall budget exhausted')
                observed = self.read_state();record['last_observation'] = deepcopy(observed)
                record['polls'] += 1
                if self.clock() >= self.deadline:
                    raise NativeControlError('Wait wall budget exhausted after observation')
                ready = predicate(observed)
                if type(ready) is not bool:
                    raise NativeControlError('Wait predicate must return a boolean')
                if self.clock() >= self.deadline:
                    raise NativeControlError('Wait wall budget exhausted after predicate')
                if self.guest_elapsed > end:
                    raise NativeControlError(label+' exceeded its measured guest budget')
                if ready:
                    record.update(complete=True, guest_elapsed_ms=self.guest_elapsed-record['guest_start'])
                    return observed
                if self.guest_elapsed >= end:
                    raise NativeControlError(label+' did not complete within budget')
                self.advance(min(slice_ms, end-self.guest_elapsed))
        except BaseException as error:
            record.update(error=str(error), guest_elapsed_ms=self.guest_elapsed-record['guest_start'])
            self._block(error);raise
