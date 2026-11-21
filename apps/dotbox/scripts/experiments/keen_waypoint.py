"""Finite, source-informed horizontal waypoint experiment for one Keen binding.

``make_policy(initial_state, args)`` returns a pure KeenLoop policy with a JSON
``result`` receipt. It performs no I/O or native calls. The caller owns source,
hook, input-delay and fresh corridor qualification; this module does not discover
or qualify those bindings. It accepts only the small level-one starting corridor,
two ticks per update, neutral standing followed by one unreversed walk and stop.

The recurrence is authored from DoActor/StateMachine and KeenStandThink/
KeenWalkThink in released source revision
15be5be4a3382d0a1d99e1202219a84b09b11273. Walking moves before its thinker sees
release. A standing start can also process excess ticks after changing state.
There is no universal fixed stopping distance, acceleration model or path planner.

``input_delay_updates`` must be an explicitly measured 0 or 1. Phase names do
not imply delay. Every subsequent decoded input and horizontal state is checked
against the prediction; mismatch ends the policy without another hold. KeenLoop
still owns its bounded release cleanup and the caller owns terminal close.

``corridor_verified`` attests a fresh per-trial terrain check by the caller.
Map-pointer, camera, contact and nearby-actor guards do not continuously re-read
terrain and cannot prove absence of arbitrary in-place map edits. The admitted
corridor must have static, nonanimated clear body tiles and flat safe floor.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math


STAND = 0x0FE8
WALKS = (0x1498, 0x14B6, 0x14D4, 0x14F2)
ORIGIN_MIN, ORIGIN_MAX = 32320, 33920
MOTION_FIELDS = ('x', 'state', 'ticcount', 'xdir', 'xmove')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _int(value, low, high, name):
    _require(type(value) is int and low <= value <= high, f'{name} outside {low}..{high}')
    return value


def _motion(player):
    _require(isinstance(player, Mapping), 'Missing player state')
    motion = {key: player[key] for key in MOTION_FIELDS}
    _int(motion['x'], 0, 65535, 'x')
    _require(motion['state'] == STAND or motion['state'] in WALKS, 'Unmodeled player state')
    _int(motion['ticcount'], 0, 3 if motion['state'] == STAND else 5, 'state ticcount')
    _require(type(motion['xdir']) is int and motion['xdir'] in (-1, 1), 'Unmodeled direction')
    _int(motion['xmove'], -72, 72, 'horizontal movement')
    return motion


def predict_update(player, axis, *, tics=2):
    """One flat-floor update with input ALREADY sampled by the game.

    Returns only horizontal model fields. Raw ymove is attempted floor motion,
    not actual vertical displacement, and deliberately is not integrated here.
    """
    _require(type(tics) is int and tics == 2, 'Only two game ticks are modeled')
    _require(type(axis) is int and axis in (-1, 0, 1), 'Invalid sampled input axis')
    value = _motion(player)
    phase, direction = value['ticcount'], value['xdir']
    if value['state'] == STAND:
        if axis == 0:
            return {**value, 'ticcount': (phase + 2) % 4, 'xmove': 0}
        excess = max(0, phase + 2 - 4)
        dx = axis * 24 * (2 + excess)
        return {'x': value['x'] + dx, 'state': WALKS[0], 'ticcount': excess,
                'xdir': axis, 'xmove': dx}
    if axis == 0:
        dx = direction * 24 * min(2, 6 - phase)
        return {'x': value['x'] + dx, 'state': STAND, 'ticcount': max(0, phase + 2 - 6),
                'xdir': direction, 'xmove': dx}
    _require(axis == direction, 'In-motion reversal is not modeled')
    next_phase = phase + 2
    return {'x': value['x'] + direction * 48,
            'state': WALKS[(WALKS.index(value['state']) + next_phase // 6) % 4],
            'ticcount': next_phase % 6, 'xdir': direction, 'xmove': direction * 48}


def predict_stop_x(player, input_delay_updates):
    """Pending old-input updates, then the first consumed neutral update."""
    _int(input_delay_updates, 0, 1, 'calibrated input delay')
    value = _motion(player)
    if value['state'] == STAND:
        return value['x']
    for _ in range(input_delay_updates):
        value = predict_update(value, value['xdir'])
    return predict_update(value, 0)['x']


def stop_choices(player, input_delay_updates):
    """Settled x after release now versus holding one more update, then release."""
    _require(player['state'] in WALKS, 'Stop choices require walking state')
    now = predict_stop_x(player, input_delay_updates)
    later = predict_stop_x(predict_update(player, player['xdir']), input_delay_updates)
    return now, later


def _map_identity(state):
    world = state['map']
    _require(isinstance(world, Mapping), 'Missing map identity')
    segments = world['plane_segments']
    _require(isinstance(segments, (list, tuple)) and len(segments) == 3, 'Invalid map planes')
    for segment in (*segments, world['tile_info_segment']):
        _int(segment, 1, 65535, 'map segment')
    return (world['width'], world['height'], tuple(segments), world['tile_info_segment'])


class WaypointPolicy:
    def __init__(self, initial_state, args):
        self.direction = getattr(args, 'direction', None)
        _require(self.direction in ('left', 'right'), 'direction must be left or right')
        self.axis = -1 if self.direction == 'left' else 1
        self.delay = _int(getattr(args, 'input_delay_updates', None), 0, 1, 'calibrated input delay')
        distance = getattr(args, 'distance_px', None)
        _require(type(distance) in (int, float) and math.isfinite(distance)
                 and 24 <= distance <= (52 if self.axis == -1 else 32)
                 and distance * 16 == int(distance * 16), 'distance outside finite corridor scope')
        tolerance = getattr(args, 'tolerance_px', 3)
        _require(type(tolerance) in (int, float) and math.isfinite(tolerance)
                 and 0 <= tolerance <= 3, 'tolerance must be between 0 and 3 pixels')
        self.tolerance = tolerance
        self.limit = _int(getattr(args, 'cycles', 80), 4, 120, 'cycle limit')
        self.settle_samples = _int(getattr(args, 'settle_samples', 3), 2, 4, 'stable sample count')
        _require(isinstance(initial_state, Mapping), 'Missing initial state')
        try:
            self.initial = deepcopy(initial_state)
            self.map_identity = _map_identity(initial_state)
            self.camera = deepcopy(initial_state['camera'])
            self.phase = initial_state['phase']
            _require(self.phase in ('pre_input', 'post_actor_pre_refresh'), 'Unqualified observation phase')
            self._guard(initial_state)
            p = initial_state['player']
            _require(p['x'] == 33280 and p['state'] == STAND and p['xmove'] == 0
                     and initial_state['input']['xaxis'] == 0, 'Initial pose must be fresh neutral standing')
        except (KeyError, TypeError) as error:
            raise ValueError(f'Missing initial field: {error}') from error
        self.target = p['x'] + self.axis * int(distance * 16)
        _require(ORIGIN_MIN <= self.target <= ORIGIN_MAX, 'Target leaves qualified corridor')
        self.pending = [0] * self.delay
        self.expected = self.expected_axis = None
        self.sequence = -1
        self.previous_position = None
        self.released = self.finished = False
        self.stable_samples = 0
        self.result = {'schema': 'dotbox-keen-waypoint-experiment-1', 'outcome': 'running',
            'direction': self.direction, 'distance_px': distance, 'initial_x': p['x'],
            'target_x': self.target, 'input_delay_updates': self.delay, 'phase': self.phase,
            'tolerance_px': tolerance, 'release_sequence': None, 'stable_samples': 0,
            'decisions': [], 'scope': 'Finite flat-floor candidate; caller-qualified source, delay and corridor'}

    def _guard(self, state):
        _require(isinstance(state, Mapping), 'Missing decoded state')
        _require(state['coherent_game_update'] is True and state['phase'] == self.phase,
                 'Observation phase changed')
        _require((state['level'], state['playstate'], state['lives']) == (1, 0, 3),
                 'Gameplay scene or lives changed')
        _require(state['corridor_verified'] is True, 'Fresh per-trial corridor qualification required')
        _require(_map_identity(state) == self.map_identity and self.map_identity[:2] == (136, 37),
                 'Map identity changed')
        _require(state['camera'] == self.camera, 'Camera changed outside the local corridor')
        _require(type(state['clock']['tics']) is int and state['clock']['tics'] == 2,
                 'Only two game ticks are modeled')
        control = state['input']
        _require(type(control['xaxis']) is int and control['xaxis'] in (-1, 0, 1)
                 and all(control[key] == 0 for key in
                         ('yaxis', 'button0', 'button1', 'button0held', 'button1held')),
                 'Non-horizontal input is outside this policy')
        p = state['player']
        _motion(p)
        _require(p['nothink'] == 0, 'Player thinker is suppressed')
        _require(p['hitnorth'] == 1, 'Flat safe floor contact required')
        _require(all(p[key] == 0 for key in ('hiteast', 'hitsouth', 'hitwest')),
                 'Unexpected side or ceiling contact')
        _require(ORIGIN_MIN <= p['x'] <= ORIGIN_MAX and p['y'] == 7695
                 and 32000 <= p['left'] <= p['right'] < 34304
                 and 7695 <= p['top'] <= 7743 and p['bottom'] == 8191,
                 'Player leaves qualified body corridor')
        walking = p['state'] in WALKS
        record = p['state_record']
        following = WALKS[(WALKS.index(p['state']) + 1) % 4] if walking else STAND
        expected = {'progress': 4 if walking else 3, 'skippable': int(walking),
                    'push_to_floor': 1, 'tic_time': 6 if walking else 4,
                    'x_move': 24 if walking else 0, 'y_move': 0 if walking else 16,
                    'next_state': following}
        _require(all(record[key] == value for key, value in expected.items()),
                 'State record differs from horizontal model')
        actors = state['nearby']
        _require(isinstance(actors, list) and len(actors) <= 100, 'Missing bounded nearby actor observation')
        for actor in actors:
            _require(isinstance(actor, Mapping) and type(actor['active']) is int, 'Invalid nearby actor')
            if actor['active']:
                _require(actor['class_name'] == 'bonus', 'Active nearby actor outside qualified profile')
                _require(actor['right'] < 32000 or actor['left'] >= 34304
                         or actor['bottom'] < 7680 or actor['top'] > 8191,
                         'Nearby actor intersects the corridor')

    def _finish(self, outcome, **details):
        self.finished = True
        self.result.update(outcome=outcome, stable_samples=self.stable_samples, **details)
        return None

    def __call__(self, observation):
        if self.finished:
            return None
        try:
            _require(observation['coherence'] == 'qualified_hook', 'Unqualified observation coherence')
            sequence = observation['sequence']
            _require(type(sequence) is int and sequence == self.sequence + 1,
                     'Observation sequence repeated or skipped')
            _require(sequence < self.limit - 1, 'Finite waypoint update limit reached')
            state = observation['state']
            self._guard(state)
            p, control = state['player'], state['input']
            if self.sequence < 0:
                _require(_motion(p) == _motion(self.initial['player']) and control['xaxis'] == 0,
                         'Initial observation changed before admission')
            else:
                _require(control['xaxis'] == self.expected_axis, 'Observed sampled input differs from calibrated delay')
                _require(_motion(p) == self.expected, 'Observed horizontal state differs from prediction')
            self.sequence = sequence
            position = (p['x'], p['y'], p['bottom'])
            if self.released:
                stable = (control['xaxis'] == 0 and p['state'] == STAND and p['xmove'] == 0
                          and position == self.previous_position)
                self.stable_samples = self.stable_samples + 1 if stable else 0
                if self.stable_samples >= self.settle_samples:
                    error = (p['x'] - self.target) / 16
                    return self._finish('settled' if abs(error) <= self.tolerance else 'outside_tolerance',
                                        settled_x=p['x'], error_px=error, final_sequence=sequence)
            elif p['state'] in WALKS:
                now, later = stop_choices(p, self.delay)
                self.result['decisions'].append({'sequence': sequence, 'x': p['x'],
                    'state': p['state'], 'ticcount': p['ticcount'],
                    'release_now_x': now, 'hold_one_more_x': later})
                if abs(now - self.target) <= abs(later - self.target):
                    self.released = True
                    self.result.update(release_sequence=sequence, predicted_settled_x=now)
            desired = 0 if self.released else self.axis
            self.pending.append(desired)
            sampled = self.pending.pop(0)
            predicted = predict_update(p, sampled)
            _require(ORIGIN_MIN <= predicted['x'] <= ORIGIN_MAX, 'Prediction leaves qualified corridor')
            self.expected, self.expected_axis = predicted, sampled
            self.previous_position = position
            self.result['stable_samples'] = self.stable_samples
            return set() if self.released else {self.direction}
        except (ValueError, KeyError, TypeError) as error:
            return self._finish('refused', reason=str(error), last_sequence=self.sequence)


def make_policy(initial_state, args):
    """Runner injection seam; construction validates admission before any input."""
    return WaypointPolicy(initial_state, args)
