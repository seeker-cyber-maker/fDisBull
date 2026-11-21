"""Bounded, source-informed Carrot Courier state rules over supplied observations.

``CarrotModel(profile).predict_walk_phase(actor, tics=..., source_sha256=...)``
predicts the walking state/counter and proposed movement before tile clipping.
It does not predict collision-resolved displacement. ``reaction_decision``
separately requires ``phase='reaction_callback_entry'`` and current post-collision
contacts; a normal loop snapshot does not establish that phase.

The authored rules follow Carrot walk states/CarrotReact/CarrotAirReact and
DoActor/StateMachine/ChangeState in the released Keen Dreams source. The caller
must qualify the exact binary, callback meanings, state mapping and observation
phase privately. A matching supplied source hash is a guard, not authentication.
Profiles contain four ordered walking-state IDs and one leap ID, not guessed
runtime addresses. State records are checked against this finite rule family.

Only an ordinary active carrot and two game ticks per update are admitted. There
is no activation, deactivation, RNG, gravity, terrain, collider or contact
simulation here. Other contacts or reactions may change the final observation.
No I/O, emulator access, input, mutation of supplied data or state commitment
occurs. Predictions require later observation; code alone is not current state.
"""
from __future__ import annotations

from collections.abc import Mapping
import re


PROFILE_FORMAT = 'dotbox-keen-carrot-profile-1'
PREDICTION_FORMAT = 'dotbox-keen-carrot-prediction-1'
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_PROFILE_FIELDS = {'format', 'source_sha256', 'qualification', 'walk_states', 'leap_state'}
_RECORD_FIELDS = ('progress', 'skippable', 'push_to_floor', 'tic_time',
                  'x_move', 'y_move', 'next_state')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, low, high, name):
    _require(type(value) is int and low <= value <= high, f'{name} outside {low}..{high}')
    return value


class CarrotModel:
    """A caller-qualified finite state family, without a second game engine."""

    def __init__(self, profile):
        _require(isinstance(profile, Mapping) and set(profile) == _PROFILE_FIELDS,
                 'Profile requires the documented source, qualification and state mapping')
        _require(profile['format'] == PROFILE_FORMAT, 'Unsupported carrot profile format')
        source = profile['source_sha256']
        _require(type(source) is str and _SHA.fullmatch(source) is not None,
                 'Profile requires a lowercase source SHA-256')
        qualification = profile['qualification']
        _require(type(qualification) is str and qualification.strip() and len(qualification) <= 2048,
                 'Profile requires a bounded private qualification locator')
        states = profile['walk_states']
        _require(type(states) in (list, tuple) and len(states) == 4,
                 'Exactly four ordered walking states are required')
        self._walks = tuple(_integer(value, 1, 65535, 'walking state') for value in states)
        self._leap = _integer(profile['leap_state'], 1, 65535, 'leap state')
        _require(len(set((*self._walks, self._leap))) == 5, 'State IDs must be distinct')
        self._source = source

    def _actor(self, actor, tics, source_sha256, *, allow_leap):
        _require(type(source_sha256) is str and source_sha256 == self._source,
                 'Observation source differs from the qualified profile')
        _require(type(tics) is int and tics == 2, 'Only two game ticks are modeled')
        _require(isinstance(actor, Mapping), 'Expected an observed actor mapping')
        _require(actor.get('class_name') == 'carrot', 'Only the carrot class is modeled')
        active = _integer(actor.get('active'), 0, 3, 'activity')
        _require(active == 1, 'An ordinary active carrot is required; activation is not modeled')
        direction = _integer(actor.get('xdir'), -1, 1, 'direction')
        _require(direction != 0, 'A left or right direction is required')
        state = _integer(actor.get('state'), 1, 65535, 'state')
        walking = state in self._walks
        _require(walking or (allow_leap and state == self._leap), 'Unmodeled carrot state')
        count = _integer(actor.get('ticcount'), 0, 4 if walking else 0, 'state ticcount')
        if walking:
            following = self._walks[(self._walks.index(state) + 1) % 4]
            values = (0, 0, 1, 5, 128, 0, following)
        else:
            values = (2, 0, 0, 0, 0, 0, 0)
        record = actor.get('state_record')
        _require(isinstance(record, Mapping), 'Missing observed state record')
        for key, expected in zip(_RECORD_FIELDS, values):
            _require(type(record.get(key)) is int and record[key] == expected,
                     f'State record {key} differs from the qualified rule')
        return state, count, direction, walking

    def predict_walk_phase(self, actor, *, tics, source_sha256):
        """Predict only the state-machine phase; prior motion is not accumulated."""
        state, count, direction, _ = self._actor(actor, tics, source_sha256, allow_leap=False)
        count += tics
        crossed = count >= 5
        following = self._walks[(self._walks.index(state) + 1) % 4] if crossed else state
        return {'schema': PREDICTION_FORMAT, 'rule': 'carrot_walk_phase',
                'scope': 'state_machine_before_clipping', 'source_sha256': self._source,
                'state': following, 'ticcount': count - 5 if crossed else count,
                'crossed_state_boundary': crossed,
                'proposed_xmove': 128 * direction if crossed else 0, 'proposed_ymove': 0,
                'collision_resolved': False}

    def reaction_decision(self, actor, *, tics, source_sha256, phase):
        """Predict selected callback effects, leaving final position unspecified.

        Contacts must belong to this callback entry, after the relevant movement,
        clipping and actor contacts. The caller's phase assertion is not verified
        by this pure model. A ledge rollback is intermediate: ChangeState selects
        a new shape, resets movement/counter, and clips again. Landing also invokes
        ChangeState, whose push-to-floor work is outside this decision model.
        """
        _require(phase == 'reaction_callback_entry', 'Current reaction-callback phase is required')
        _, _, direction, walking = self._actor(actor, tics, source_sha256, allow_leap=True)
        contacts = {key: _integer(actor.get(key), -32768, 32767, key)
                    for key in ('hitnorth', 'hiteast', 'hitsouth', 'hitwest')}
        effects, rollback = {}, None
        decision = 'no_motion_state_change'
        reclips = False
        if walking:
            if direction == 1 and contacts['hitwest']:
                decision, effects = 'turn_left', {'xdir': -1}
            elif direction == -1 and contacts['hiteast']:
                decision, effects = 'turn_right', {'xdir': 1}
            elif not contacts['hitnorth']:
                xmove = _integer(actor.get('xmove'), -32768, 32767, 'xmove')
                ymove = _integer(actor.get('ymove'), -32768, 32767, 'ymove')
                rollback = {'x_delta': -xmove, 'y_delta': -ymove}
                decision, reclips = 'ledge_leap', True
                effects = {'state': self._leap, 'ticcount': 0,
                           'xspeed': 32 * direction, 'yspeed': -40}
        else:
            if contacts['hitsouth']:
                decision, effects = 'ceiling_stop', {'yspeed': 0}
            if contacts['hitnorth']:
                decision, reclips = 'land', True
                effects.update(state=self._walks[0], ticcount=0)
        return {'schema': PREDICTION_FORMAT, 'rule': 'carrot_reaction',
                'scope': 'reaction_callback_decision', 'source_sha256': self._source,
                'decision': decision, 'effects': effects, 'intermediate_rollback': rollback,
                'change_state_reclips': reclips, 'final_position': None,
                'collision_resolved': False}
