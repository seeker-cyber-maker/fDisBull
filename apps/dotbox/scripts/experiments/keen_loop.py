"""Experimental local feedback/timing loop over an already owned native session.

No launch, ownership transfer, memory write, save/restore, disk write, or model
call occurs here. Screenshots are disabled unless frame_sink is supplied.
One controller must own the native channel throughout.
The caller qualifies the source-bound RAM range, decoder, controls and policy;
there are deliberately no guessed Keen addresses or key bindings in this file.

``KeenLoop(session_or_call, profile=..., binding=..., decoder=...).run(...)``
accepts NativeSession or ``call(method, params, timeout_ms=...)``. Adapter callers
must supply capabilities; available session metadata is checked against the
profile's source hash. The mutable binding requires run_id, session_id,
generation, timeline and state_revision. Change it or call invalidate() after an
external timeline change. Native restores also invalidate the generation. A loop
is one-shot; returned observations are evidence, never reusable action tokens.

A profile requires source_sha256, address (linear conventional RAM), length and
qualification (a caller-owned evidence locator). Optional boundary contains
breakpoint_id, max_frames (<=8), max_guest_ms (<=120). Without it, renderer
boundaries are NOT established game-update boundaries. With it, only that exact
qualified breakpoint admits decoding; reaching a time/frame limit is a coherence
miss, preserved without another input or resume. This does not qualify the hook.

The pure policy receives a copied observation and returns a desired key set, or
None to finish. neutral_policy returns an empty set. Edges are sent only on change.
An optional synchronous frame_sink(png_bytes, metadata) receives validated native
PNG bytes and copied metadata after the initial sample and every frame_every
accepted updates (default 4). It receives no session or state-control interface.
The image is the last completed guest frame, not a phase-synchronized rendering
of the state observation. Only an admitted qualified hook establishes coherent
game updates; presentation never changes that admission or advances execution.
Screenshot, decode and sink costs are recorded separately and included in host
time and completed-cycle pacing. Initial presentation precedes the pacing epoch.
The sink must be trusted, synchronous and bounded, with no native operations,
disk writes or model calls. A sink exception uses the same fresh-fence cleanup
as a pure callback failure; screenshot uncertainty preserves the stopped target.
One outer host deadline includes a cleanup reserve, and total guest allowance
includes a reserved 20 ms release drain. An RPC exception, context change or
unexpected stop forbids all further calls. Pure callback failures can clean up
only at a freshly fenced known stop. Release plus bounded drain does not prove
the game's handler consumed the release. The caller still owns terminal close.

Cadence is host pacing, not a claim about game update rate. Fast-forward is only
changed when explicitly selected and is restored on safe completion. All timing
and compact observations stay in memory for the caller to store after the run.
Guest totals count verified execution, including a coherence miss with valid
accounting. guest_accounting_complete is false after uncertain/invalid step
receipts; a partial known total must then not be presented as all guest progress.
Decoder and policy callbacks must be bounded and pure. A synchronous callback,
including a presentation sink, cannot be preempted by this helper's host deadline.
No native throughput or hard callback deadline is promised.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import inspect
import json
import math
import re
import time

from dotbox.keyboard_input import KEYS
from dotbox.operation_budget import deadline_scope
from dotbox.screenshot_codecs import decode_screenshot


def neutral_policy(observation):
    """Observe timing/state without selecting gameplay input."""
    return ()


class _Stop(Exception):
    def __init__(self, outcome, message, *, preserve=True):
        super().__init__(message)
        self.outcome, self.preserve = outcome, preserve


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _latencies(values):
    ordered = sorted(values)
    return {name: ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None
            for name, fraction in (('p50', .50), ('p95', .95), ('max', 1))}


class KeenLoop:
    def __init__(self, session_or_call, *, profile, binding, decoder,
                 policy=neutral_policy, capabilities=None, metadata=None,
                 frame_sink=None, frame_every=4,
                 clock=time.monotonic, sleep=time.sleep):
        self.target = session_or_call
        self.native = not callable(session_or_call) and callable(getattr(session_or_call, 'call', None))
        if not self.native and not callable(session_or_call):
            raise TypeError('Expected an existing NativeSession or call adapter')
        if not callable(decoder) or not callable(policy):
            raise TypeError('decoder and policy must be pure callables')
        if frame_sink is not None and (not callable(frame_sink) or inspect.iscoroutinefunction(frame_sink)
                                       or inspect.isasyncgenfunction(frame_sink)
                                       or inspect.isgeneratorfunction(frame_sink)):
            raise TypeError('frame_sink must be a synchronous callable or None')
        if type(frame_every) is not int or frame_every < 1:
            raise ValueError('frame_every must be a positive integer')
        self.frame_sink, self.frame_every = frame_sink, frame_every
        if not isinstance(profile, Mapping) or not isinstance(binding, Mapping):
            raise ValueError('profile and binding must be mappings')
        self.profile = deepcopy(dict(profile))
        digest = self.profile.get('source_sha256')
        if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('profile requires a lowercase source SHA-256')
        if not isinstance(self.profile.get('qualification'), str) or not self.profile['qualification'].strip():
            raise ValueError('profile requires its qualification evidence locator')
        address = _integer(self.profile.get('address'), 0, 0x9ffff, 'address')
        length = _integer(self.profile.get('length'), 1, 65536, 'bounded region length')
        if address + length > 0xa0000:
            raise ValueError('Compact region must remain inside conventional RAM')
        self.address = {'space': 'linear', 'offset': f'0x{address:08X}'}
        self.binding = binding
        self.expected = {key: binding.get(key) for key in
                         ('run_id', 'session_id', 'generation', 'timeline', 'state_revision')}
        for key in ('run_id', 'session_id', 'timeline'):
            if not isinstance(self.expected[key], str) or not self.expected[key]:
                raise ValueError(f'binding requires a nonempty {key}')
        for key in ('generation', 'state_revision'):
            _integer(self.expected[key], 0, (1 << 53) - 1, key)
        self.capabilities = deepcopy(capabilities if capabilities is not None else
                                    getattr(getattr(session_or_call, 'rpc', None), 'capabilities', {}))
        self.metadata = getattr(session_or_call, 'metadata', None)
        if self.metadata is None:
            self.metadata = metadata
        self.decoder, self.policy = decoder, policy
        self.clock, self.sleep = clock, sleep
        boundary = self.profile.get('boundary', {})
        if not isinstance(boundary, Mapping):
            raise ValueError('profile boundary must be a mapping')
        self.hook = boundary.get('breakpoint_id')
        if boundary and (not isinstance(self.hook, str) or not self.hook):
            raise ValueError('Qualified boundary requires an explicit breakpoint_id')
        self.max_profile_frames = _integer(boundary.get('max_frames', 2), 1, 8, 'profile max_frames')
        self.max_profile_ms = _integer(boundary.get('max_guest_ms', 40), 1, 120, 'profile max_guest_ms')
        self.invalidated = None
        self.started = False

    def invalidate(self, reason='External context change'):
        self.invalidated = str(reason)

    def _local(self):
        if self.invalidated or self.binding.get('valid') is False:
            raise _Stop('invalidated', self.invalidated or 'Binding invalidated')
        if any(self.binding.get(key) != value for key, value in self.expected.items()):
            raise _Stop('invalidated', 'Session, timeline or initial observation binding changed')
        for key in ('run_id', 'session_id'):
            observed = getattr(self.target, key, self.expected[key])
            if observed != self.expected[key]:
                raise _Stop('invalidated', f'Native {key} changed')
        if self.metadata is not None and self.metadata.get('source_sha256') != self.profile['source_sha256']:
            raise _Stop('invalidated', 'Session source hash differs from qualified profile')

    def _rpc(self, method, params=None, *, mutation=False):
        self._local()
        remaining = int((self.call_deadline - self.clock()) * 1000)
        if remaining <= 0:
            raise _Stop('host_budget', 'Host admission deadline reached', preserve=False)
        payload = {'session_id': self.expected['session_id'], **(params or {})}
        start = self.clock()
        event = {'method': method, 'start_ms': (start - self.start) * 1000}
        self.calls.append(event)
        if mutation:
            self.safe = False
        if method == 'frame.step':
            self.accounting_complete = False
        try:
            if self.native:
                with deadline_scope(self.target, self.call_deadline, rpc_ms=min(2000, remaining),
                                    admission_ms=0, cleanup_ms=0):
                    result = self.target.call(method, payload)
            else:
                result = self.target(method, payload, timeout_ms=min(2000, remaining))
        except Exception as error:
            self.safe = False
            event.update(error=type(error).__name__, elapsed_ms=(self.clock() - start) * 1000)
            raise _Stop('transport_uncertain', f'{method}: {error}') from error
        event['elapsed_ms'] = (self.clock() - start) * 1000
        self.last_reply = deepcopy(result)
        self._local()
        if (not isinstance(result, dict) or result.get('session_id') != self.expected['session_id']
                or type(result.get('state_revision')) is not int):
            raise _Stop('unexpected_stop', f'{method}: invalid session/revision receipt')
        return result

    def _revision(self, reply, delta=0):
        if reply['state_revision'] != self.revision + delta:
            raise _Stop('invalidated', 'Native state revision changed outside the admitted operation')
        self.revision = reply['state_revision']

    def _fence(self):
        status = self._rpc('session.status')
        self._revision(status)
        reason = status.get('last_stop', status.get('stop_reason'))
        if status.get('state') != 'stopped' or not isinstance(reason, dict):
            raise _Stop('unexpected_stop', 'Expected the same stopped target')
        if self.stop is not None and reason != self.stop:
            raise _Stop('unexpected_stop', 'Stopped reason changed outside the controller')
        if self.stop is None and self.hook and (reason.get('kind') != 'breakpoint'
                                                or reason.get('breakpoint_id') != self.hook):
            raise _Stop('coherence_miss', 'Initial state is not at the qualified execution hook')
        control = self._rpc('input.control')
        self._revision(control)
        if control.get('owner') != 'agent' or control.get('generation') != self.expected['generation']:
            raise _Stop('invalidated', 'Native owner or control generation changed')
        self.stop, self.safe = deepcopy(reason), True

    def _keyboard(self, reply, expected):
        data = reply.get('keyboard', {})
        keys = data.get('frame_keys')
        if (not isinstance(keys, list) or any(not isinstance(key, str) for key in keys)
                or len(keys) != len(set(keys)) or set(keys) != expected
                or data.get('pending_events') != 0 or data.get('owned_keys') != 0):
            raise _Stop('unexpected_stop', 'Keyboard ownership or queued input does not match this loop')

    def _edges(self, desired):
        if desired == self.held:
            return
        edges = ([{'key': key, 'pressed': False} for key in sorted(self.held - desired)] +
                 [{'key': key, 'pressed': True} for key in sorted(desired - self.held)])
        reply = self._rpc('input.keyboard.frame_edges',
                          {'edges': edges, 'control_generation': self.expected['generation']}, mutation=True)
        self._revision(reply, 1)
        if reply.get('accepted') is not True or reply.get('delivery') != 'hardware_edges_at_paused_boundary':
            raise _Stop('unexpected_stop', 'Frame-key edges lack the expected acknowledgement')
        self._keyboard(reply, desired)
        self.held, self.safe = set(desired), True

    def _timing(self, selected=None):
        params = {} if selected is None else {'fast_forward': selected}
        reply = self._rpc('execution.timing', params, mutation=selected is not None)
        if type(reply.get('fast_forward')) is not bool or type(reply.get('guest_ticks')) is not int:
            raise _Stop('unexpected_stop', 'Invalid timing receipt')
        self._revision(reply, int(selected is not None and self.fast != selected))
        if selected is not None and reply['fast_forward'] != selected:
            raise _Stop('unexpected_stop', 'Fast-forward selection was not acknowledged')
        if self.ticks is not None and reply['guest_ticks'] != self.ticks:
            raise _Stop('invalidated', 'Guest time changed at the stopped timing boundary')
        self.fast, self.ticks, self.safe = reply['fast_forward'], reply['guest_ticks'], True

    def _capture(self, sequence):
        reply = self._rpc('memory.read', {'address': self.address, 'length': self.profile['length']})
        self._revision(reply)
        try:
            raw = base64.b64decode(reply['data_base64'], validate=True)
        except (KeyError, ValueError, TypeError) as error:
            raise _Stop('unexpected_stop', 'Invalid compact memory payload') from error
        digest = hashlib.sha256(raw).hexdigest()
        if (len(raw) != self.profile['length'] or reply.get('byte_count') != len(raw)
                or reply.get('address') != self.address or reply.get('sha256') != digest):
            raise _Stop('unexpected_stop', 'Memory range/length/hash receipt does not match the profile')
        try:
            state = deepcopy(self.decoder(raw))
            if not isinstance(state, Mapping) or len(json.dumps(state, allow_nan=False).encode()) > 16384:
                raise ValueError('Decoder must return a compact finite JSON mapping')
        except Exception as error:
            raise _Stop('callback_error', f'Decoder: {error}', preserve=False) from error
        self._local()
        return {'sequence': sequence, 'binding': deepcopy(self.expected), 'state_revision': self.revision,
                'guest_ticks': self.ticks, 'frame_id': self.frame, 'state': state,
                'memory_sha256': digest, 'coherence': 'qualified_hook' if self.hook else 'renderer_unqualified'}

    def _present(self, observation):
        if self.frame_sink is None or observation['sequence'] % self.frame_every:
            return
        started = self.clock()
        state_ref = {key: observation[key] for key in
                     ('sequence', 'state_revision', 'guest_ticks', 'frame_id', 'coherence')}
        event = {'sequence': observation['sequence'], 'state_observation': deepcopy(state_ref),
                 'captured': False, 'published': False, 'rpc_ms': 0.0, 'decode_ms': 0.0, 'sink_ms': 0.0}
        self.presentations.append(event)
        stage = 'screenshot_rpc'
        try:
            rpc_start = self.clock()
            try:
                reply = self._rpc('video.screenshot', {'encoding': 'png'})
                self._revision(reply)
            finally:
                event['rpc_ms'] = (self.clock() - rpc_start) * 1000
            stage, decode_start = 'decode', self.clock()
            try:
                if (reply.get('format') != 'png' or reply.get('source') != 'last_completed_guest_frame'
                        or any(type(reply.get(key)) is not int or reply[key] < 0
                               for key in ('frame_id', 'mode_id', 'captured_ticks'))):
                    raise ValueError('Screenshot lacks a valid completed-frame identity')
                png, metadata = decode_screenshot(reply)
            except Exception as error:
                raise _Stop('unexpected_stop', f'Screenshot: {error}') from error
            finally:
                event['decode_ms'] = (self.clock() - decode_start) * 1000
            event['captured'] = True
            event['frame'] = {key: metadata[key] for key in
                              ('frame_id', 'mode_id', 'captured_ticks', 'width', 'height', 'sha256', 'source')}
            metadata.update(state_observation=deepcopy(state_ref), phase_synchronized=False)
            stage, sink_start = 'sink', self.clock()
            try:
                delivered = self.frame_sink(bytes(png), deepcopy(metadata))
                if inspect.isawaitable(delivered) or inspect.isasyncgen(delivered) or inspect.isgenerator(delivered):
                    if inspect.iscoroutine(delivered) or inspect.isgenerator(delivered):
                        delivered.close()
                    raise TypeError('frame_sink must complete synchronously')
            except Exception as error:
                raise _Stop('callback_error', f'Frame sink: {error}', preserve=False) from error
            finally:
                event['sink_ms'] = (self.clock() - sink_start) * 1000
            event['published'] = True
            stage = 'context'
            self._local()
        except _Stop as stopped:
            event['error'] = {'stage': stage, 'outcome': stopped.outcome,
                              'type': type(stopped.__cause__ or stopped).__name__, 'message': str(stopped)}
            raise
        finally:
            event['total_ms'] = (self.clock() - started) * 1000

    def _step(self, frames, milliseconds, *, drain=False):
        reply = self._rpc('frame.step', {'max_frames': frames, 'max_guest_ms': milliseconds}, mutation=True)
        self._revision(reply, 1)
        b = reply.get('bounded', {})
        names = ('max_frames', 'max_guest_ms', 'frames_completed', 'guest_elapsed_ms',
                 'guest_ticks_before', 'guest_ticks_after', 'guest_tick_bits')
        if any(type(b.get(name)) is not int for name in names):
            raise _Stop('unexpected_stop', 'Missing native bounded accounting')
        elapsed, completed, bits = b['guest_elapsed_ms'], b['frames_completed'], b['guest_tick_bits']
        if (b['max_frames'] != frames or b['max_guest_ms'] != milliseconds or bits not in (32, 64)
                or not 0 <= completed <= frames or not 0 <= elapsed <= milliseconds
                or b['guest_ticks_before'] != self.ticks
                or (b['guest_ticks_after'] - b['guest_ticks_before']) % (1 << bits) != elapsed
                or reply.get('guest_ticks') != b['guest_ticks_after']
                or reply.get('boundary') != 'bounded_execution_then_safe_fetch'):
            raise _Stop('unexpected_stop', 'Native step accounting or clock continuity is inconsistent')
        # Account verified execution even if its stopping boundary is not a
        # coherent sample. A refusal must not erase time the guest already ran.
        self.ticks, self.frame = b['guest_ticks_after'], reply.get('frame_id')
        self.total_guest += elapsed
        if not drain:
            self.feedback_guest += elapsed
        self.accounting_complete = True
        reason, cause = reply.get('stop_reason', {}), b.get('stop_cause')
        own_hook = self.hook and cause == 'breakpoint' and reason.get('kind') == 'breakpoint' and reason.get('breakpoint_id') == self.hook
        # The installed runtime can name a frame-budget stop "budget" too.
        # Preserve the specific bounded cause and check its counters, rather
        # than treating that outer stop label as the renderer/frame counter.
        budget_stop = reason.get('kind') in ('frame', 'budget') and (
            (cause == 'frame_limit' and completed == frames and reply.get('completed') is True) or
            (cause == 'guest_time_limit' and elapsed == milliseconds))
        if not own_hook and (not budget_stop or (self.hook and not drain)):
            raise _Stop('coherence_miss' if budget_stop else 'unexpected_stop',
                        'Step did not stop at the qualified observation boundary')
        if completed == elapsed == 0:
            raise _Stop('unexpected_stop', 'Bounded step made no progress')
        registers = reply.get('registers', {})
        if registers.get('session_id') != self.expected['session_id'] or registers.get('state_revision') != self.revision:
            raise _Stop('unexpected_stop', 'Stopped register receipt belongs to another observation')
        self.stop, self.safe = deepcopy(reason), True
        return reply

    def run(self, *, max_cycles=120, total_guest_ms=2000, host_timeout_ms=5000,
            max_frames=1, max_guest_ms=30, pace_hz=None, fast_forward=None):
        if self.started:
            raise ValueError('KeenLoop is one-shot; bind a fresh observation for another run')
        _integer(max_cycles, 1, 10000, 'max_cycles')
        _integer(total_guest_ms, 21, 600000, 'total_guest_ms including drain reserve')
        _integer(host_timeout_ms, 251, 600000, 'host_timeout_ms including cleanup reserve')
        _integer(max_frames, 1, self.max_profile_frames, 'max_frames')
        _integer(max_guest_ms, 1, self.max_profile_ms, 'max_guest_ms')
        if fast_forward is not None and type(fast_forward) is not bool:
            raise ValueError('fast_forward must be explicitly boolean or unspecified')
        if pace_hz is not None and (type(pace_hz) not in (int, float) or not math.isfinite(pace_hz) or not 1 <= pace_hz <= 1000):
            raise ValueError('pace_hz must be finite and in 1..1000')
        cap = self.capabilities.get('execution', {}).get('bounded_frame_step', {})
        if (cap.get('schema') != 'dotbox-bounded-frame-step-1'
                or type(cap.get('max_frames')) is not int or cap['max_frames'] < max_frames
                or type(cap.get('max_guest_ms')) is not int or cap['max_guest_ms'] < max_guest_ms
                or self.capabilities.get('input', {}).get('cooperative_control') != 'dotbox-input-control-1'
                or self.capabilities.get('limits', {}).get('max_memory_read_bytes', 0) < self.profile['length']
                or (fast_forward is not None and self.capabilities.get('timing', {}).get('fast_forward') is not True)):
            raise ValueError('Required native capabilities are absent or incompatible')
        self.started = True
        self.start = self.clock()
        deadline = self.start + host_timeout_ms / 1000
        inherited = getattr(self.target, '_rpc_deadline', None)
        if inherited is not None:
            deadline = min(deadline, inherited)
        self.call_deadline = deadline - .250
        self.revision, self.stop = self.expected['state_revision'], None
        self.ticks, self.frame, self.fast, original_fast = None, None, None, None
        self.safe, self.held = False, set()
        self.accounting_complete = True
        self.total_guest = self.feedback_guest = 0
        self.calls, samples, self.presentations = [], [], []
        self.last_reply = None
        cleanup = {'status': 'preserved', 'game_consumption_verified': False}
        outcome, error, preserve, missed, feedback_start = 'cycle_limit', None, False, 0, None
        try:
            self._local()
            self._fence()
            keyboard = self._rpc('input.keyboard.state')
            self._revision(keyboard)
            self._keyboard(keyboard, set())
            self._timing()
            original_fast = self.fast
            if fast_forward is not None and fast_forward != self.fast:
                self._timing(fast_forward)
            observation = self._capture(0)
            self._present(observation)
            feedback_start = self.clock()
            for index in range(max_cycles):
                if self.total_guest >= total_guest_ms - 20:
                    outcome = 'guest_limit'
                    break
                cycle_start, first_call = self.clock(), len(self.calls)
                self._local()
                try:
                    desired = self.policy(deepcopy(observation))
                    if desired is not None:
                        if (not isinstance(desired, (set, frozenset, list, tuple)) or len(desired) > 8
                                or any(not isinstance(key, str) or key not in KEYS for key in desired)
                                or len(set(desired)) != len(desired)):
                            raise ValueError('Policy must return <=8 unique physical keys or None')
                        desired = set(desired)
                except Exception as callback_error:
                    raise _Stop('callback_error', f'Policy: {callback_error}', preserve=False) from callback_error
                self._fence()  # Recheck after callbacks, immediately before input/execution.
                if desired is None:
                    outcome = 'policy_stop'
                    break
                self._edges(desired)
                step = self._step(max_frames, min(max_guest_ms, total_guest_ms - 20 - self.total_guest))
                observation = self._capture(index + 1)
                try:
                    self._present(observation)
                finally:
                    finished = self.clock()
                    samples.append({**observation, 'desired_keys': sorted(desired), 'step': step,
                                    'cycle_latency_ms': (finished - cycle_start) * 1000,
                                    'rpc_count': len(self.calls) - first_call})
                    if pace_hz is not None:
                        target = feedback_start + (index + 1) / pace_hz
                        missed += int(finished > target)
                if pace_hz is not None:
                    delay = min(target, self.call_deadline) - self.clock()
                    if delay > 0:
                        self.sleep(delay)
        except _Stop as stopped:
            outcome, error, preserve = stopped.outcome, str(stopped), stopped.preserve
        feedback_end = self.clock()
        self.call_deadline = deadline
        if not preserve and self.safe:
            try:
                self._fence()
                if self.held:
                    self._edges(set())
                    self._step(1, min(20, total_guest_ms - self.total_guest), drain=True)
                    keyboard = self._rpc('input.keyboard.state')
                    self._revision(keyboard)
                    self._keyboard(keyboard, set())
                    cleanup['status'] = 'released_and_drained'
                else:
                    cleanup['status'] = 'neutral'
                if original_fast is not None and self.fast != original_fast:
                    self._timing(original_fast)
            except _Stop as stopped:
                cleanup.update(status='incomplete', reason=str(stopped))
                outcome, error = stopped.outcome, str(stopped)
        elapsed = self.clock() - self.start
        self.invalidated = 'Completed one-shot observation scope'
        return {'schema': 'dotbox-keen-loop-experiment-1', 'outcome': outcome, 'error': error,
                'binding': deepcopy(self.expected), 'profile': deepcopy(self.profile),
                'source_check': 'session_metadata' if self.metadata is not None else 'caller_qualified_adapter',
                'samples': samples, 'rpc_timings': self.calls, 'last_reply': self.last_reply,
                'cleanup': cleanup, 'held_keys': sorted(self.held), 'observation_valid': False,
                'timing': {'selected_fast_forward': fast_forward, 'original_fast_forward': original_fast,
                           'final_fast_forward': self.fast, 'pace_hz': pace_hz},
                'presentation': {'enabled': self.frame_sink is not None, 'frame_every': self.frame_every,
                                 'cadence': 'initial_and_every_n_accepted_updates', 'phase_synchronized': False,
                                 'attempted': len(self.presentations),
                                 'captured': sum(row['captured'] for row in self.presentations),
                                 'published': sum(row['published'] for row in self.presentations),
                                 'errors': sum('error' in row for row in self.presentations),
                                 **{key: sum(row[key] for row in self.presentations)
                                    for key in ('rpc_ms', 'decode_ms', 'sink_ms', 'total_ms')},
                                 'events': self.presentations},
                'metrics': {'cycles': len(samples), 'feedback_guest_ms': self.feedback_guest,
                            'total_guest_ms': self.total_guest, 'host_ms': elapsed * 1000,
                            'guest_accounting_complete': self.accounting_complete,
                            'feedback_host_ms': (feedback_end - feedback_start) * 1000 if feedback_start is not None else 0,
                            'guest_host_ratio': self.total_guest / (elapsed * 1000) if elapsed > 0 else None,
                            'cycle_latency_ms': _latencies([row['cycle_latency_ms'] for row in samples]),
                            'rpc_latency_ms': _latencies([row['elapsed_ms'] for row in self.calls]),
                            'missed_paced_deadlines': missed}}
