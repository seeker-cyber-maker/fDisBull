"""Pure Keen observation projection for the existing scene/oracle contracts.

This finite adapter describes the qualified first-level observation schema. It
does not read memory, establish live freshness, discover visibility, or execute
inputs. The caller supplies the exact observation/context/evidence and existing
choices. Choice gates, references and labels are copied unchanged. Optional
role bindings add only resource/objective constraints in the oracle sidecar.

Actor slots are observation-local subjects, not permanent entity identities.
Explicit ``permitted_actor_slots`` authorizes the corresponding facts and their
derived relationships for player presentation; the default is internal. Neither
``nearby`` nor activity establishes visibility. Prior-state comparisons require
the same provider/session/branch and adjacent qualified game ticks. Predictions
and forecasts are deliberately absent from the observed scene facts.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json

from dotbox.scenes import validate_scene


SOURCE_SHA256 = '36a22dbd3119c0b4cdff7adaf50a8abc3b11c21f7bc0d4d7c0d5dbf7b347e3ae'
PHASE = 'post_actor_pre_refresh'
PLAYER_SLOT, CARROT_SLOT, BONUS_SLOT = 0, 40, 31
WORLD_UNITS_PER_PIXEL = 16
FACT_IDS = ('player_x', 'player_y', 'flower_power', 'score', 'game_ticks',
            'carrot_present', 'carrot_active', 'carrot_gap_world',
            'carrot_vertical_overlap', 'carrot_approaching',
            'bonus_collectible', 'bonus_x', 'bonus_y', 'bonus_points')


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, low, high, name):
    _need(type(value) is int and low <= value <= high, f'Invalid {name}')
    return value


def _text(value, name, limit=256):
    _need(type(value) is str and value.strip() and len(value) <= limit, f'Invalid {name}')
    return value


def _body(actor):
    _need(isinstance(actor, Mapping), 'Missing actor body')
    result = {key: _integer(actor.get(key), 0, 65535, 'actor ' + key)
              for key in ('x', 'y', 'left', 'top', 'right', 'bottom')}
    _need(result['left'] <= result['right'] and result['top'] <= result['bottom'],
          'Invalid actor rectangle')
    return result


def _state(state):
    _need(isinstance(state, Mapping), 'Expected decoded state')
    try:
        encoded = json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError('State must contain bounded finite JSON') from error
    _need(len(encoded.encode()) <= 128 * 1024, 'State exceeds finite adapter bound')
    _need(state.get('phase') == PHASE and state.get('coherent_game_update') is True,
          'Qualified post-actor observation required')
    _need(state.get('level') == 1 and type(state.get('level')) is int
          and state.get('playstate') == 0 and type(state.get('playstate')) is int
          and state.get('difficulty') == 2 and type(state.get('difficulty')) is int,
          'Only normal first-level gameplay is admitted')
    world = state.get('map')
    _need(isinstance(world, Mapping) and (world.get('width'), world.get('height')) == (136, 37),
          'Qualified map dimensions required')
    segments = world.get('plane_segments')
    _need(type(segments) in (list, tuple) and len(segments) == 3, 'Missing map binding')
    for value in (*segments, world.get('tile_info_segment')):
        _integer(value, 1, 65535, 'map segment')
    clock = state.get('clock')
    _need(isinstance(clock, Mapping) and type(clock.get('tics')) is int and clock['tics'] == 2,
          'Only two game ticks per observation are admitted')
    _integer(clock.get('time_count'), 0, 2**32 - 1, 'game clock')
    _integer(state.get('flowers'), 0, 32767, 'flower-power inventory')
    _integer(state.get('score'), 0, 2**32 - 1, 'score')
    player = state.get('player')
    _body(player)
    _need(player.get('slot') == PLAYER_SLOT and type(player.get('slot')) is int
          and player.get('class_name') == 'keen', 'Expected current player')
    return state


def _actor(state, slot):
    """A missing local projection stays unknown unless the live list excludes it."""
    matches = []
    for field in ('objects', 'nearby'):
        if field not in state:
            continue
        values = state[field]
        _need(type(values) is list and len(values) <= 100, 'Invalid actor projection')
        slots = []
        for value in values:
            _need(isinstance(value, Mapping), 'Invalid projected actor')
            current = _integer(value.get('slot'), 0, 99, 'actor slot')
            slots.append(current)
            if current == slot:
                matches.append(value)
        _need(len(set(slots)) == len(slots), 'Repeated projected actor slot')
    if state.get('watched_actor_slot') == slot and 'watched_actor' in state:
        if state['watched_actor'] is not None:
            _need(isinstance(state['watched_actor'], Mapping), 'Invalid watched actor')
            matches.append(state['watched_actor'])
    live = state.get('live_actor_slots')
    if live is not None:
        _need(type(live) is list and len(live) <= 100
              and all(type(value) is int and 0 <= value < 100 for value in live)
              and len(set(live)) == len(live), 'Invalid complete live-slot list')
    if not matches:
        return (False if live is not None and slot not in live else None), None
    actor = matches[0]
    _need(actor.get('slot') == slot and type(actor.get('slot')) is int,
          'Watched actor slot differs')
    _need(live is None or slot in live, 'Actor contradicts complete live-slot list')
    for other in matches[1:]:
        _need(all(actor[key] == other[key] for key in actor.keys() & other.keys()),
              'Conflicting current actor projections')
    _text(actor.get('class_name'), 'actor class', 64)
    _integer(actor.get('active'), 0, 3, 'actor activity')
    _integer(actor.get('pointer'), 1, 65535, 'actor pointer')
    _body(actor)
    return True, actor


def _gap(player, actor):
    return max(0, player['left'] - actor['right'], actor['left'] - player['right'])


def _overlap_y(player, actor):
    return player['top'] <= actor['bottom'] and actor['top'] <= player['bottom']


def _map_binding(state):
    world = state['map']
    return tuple(world['plane_segments']), world['tile_info_segment']


def build_keen_oracle_inputs(state, *, source_sha256, edition, observation_id,
                             state_context, evidence_ref, choices, choice_roles=None,
                             permitted_actor_slots=(), previous=None):
    """Return ``{'scene': ..., 'rules': ...}`` without input or state mutation.

    ``choice_roles`` may map ``attack`` and ``collect_bonus`` to distinct IDs
    already present in ``choices``. Positive resources never grant readiness.
    ``previous`` optionally contains exactly ``state``, ``observation_id``,
    ``state_context`` and ``evidence_ref``. It supports an observed closing-gap
    relation, not an extrapolated contact ETA. Context tokens may change with
    revision; provider/session/branch must remain identical.
    """
    _need(source_sha256 == SOURCE_SHA256, 'Source differs from the qualified Keen binding')
    _text(edition, 'edition')
    _text(observation_id, 'observation ID')
    _text(evidence_ref, 'evidence reference', 1024)
    state = _state(state)
    _need(type(permitted_actor_slots) in (list, tuple, set, frozenset)
          and len(permitted_actor_slots) <= 100
          and all(type(slot) is int and 0 <= slot < 100 for slot in permitted_actor_slots),
          'Invalid explicitly permitted actor slots')
    permitted = set(permitted_actor_slots)
    _need(type(choices) is list, 'Provider choices must be a list')
    roles = {} if choice_roles is None else choice_roles
    _need(isinstance(roles, Mapping) and set(roles) <= {'attack', 'collect_bonus'}
          and all(type(value) is str for value in roles.values())
          and len(set(roles.values())) == len(roles), 'Invalid choice-role binding')
    packet = {'format': 'dotbox-scene-1', 'source_sha256': source_sha256,
              'edition': edition, 'scene_id': 'keen_level_one',
              'observation_id': observation_id, 'state_context': deepcopy(state_context),
              'title': 'Keen Dreams: current level', 'facts': [], 'choices': [],
              'guide_sources': [], 'guide_claims': []}
    validate_scene(packet)  # Validate the caller's full context before comparing it.
    player = state['player']
    present, carrot = _actor(state, CARROT_SLOT)
    bonus_present, bonus = _actor(state, BONUS_SLOT)
    is_carrot = carrot is not None and carrot['class_name'] == 'carrot'
    active = (carrot['active'] == 1 if is_carrot else False if present is not None else None)
    gap = _gap(player, carrot) if is_carrot else None
    overlap = _overlap_y(player, carrot) if is_carrot else None
    approaching = None
    if previous is not None:
        _need(isinstance(previous, Mapping) and set(previous) ==
              {'state', 'observation_id', 'state_context', 'evidence_ref'}, 'Invalid previous observation')
        prior = _state(previous['state'])
        _text(previous['observation_id'], 'previous observation ID')
        _text(previous['evidence_ref'], 'previous evidence reference', 1024)
        prior_packet = {**packet, 'observation_id': previous['observation_id'],
                        'state_context': deepcopy(previous['state_context'])}
        validate_scene(prior_packet)
        context = previous['state_context']
        _need(all(context[key] == state_context[key] for key in
                  ('provider_id', 'session_id', 'branch_id'))
              and context['revision'] < state_context['revision']
              and previous['observation_id'] != observation_id,
              'Previous observation belongs to a different or stale context')
        _need(_map_binding(prior) == _map_binding(state)
              and state['clock']['time_count'] - prior['clock']['time_count'] == 2,
              'Previous observation is not adjacent in the qualified map and game clock')
        _, before = _actor(prior, CARROT_SLOT)
        if active and before is not None and before['class_name'] == 'carrot' and before['active'] == 1:
            if before['pointer'] == carrot['pointer']:
                dx = carrot['x'] - before['x']
                toward = ((carrot['right'] <= player['left'] and dx > 0)
                          or (carrot['left'] >= player['right'] and dx < 0))
                approaching = bool(overlap and toward and gap < _gap(prior['player'], before))
    collectible = (bonus['class_name'] == 'bonus' and bonus.get('temp1') == 0
                   if bonus is not None else False if bonus_present is False else None)
    if bonus is not None and bonus['class_name'] == 'bonus':
        _integer(bonus.get('temp1'), 0, 11, 'bonus kind')
    bx, by = (bonus['x'], bonus['y']) if collectible else (None, None)
    facts = packet['facts']

    def fact(identity, subject, predicate, value, text, slots, *, detail=None):
        item = {'id': identity, 'subject': subject, 'predicate': predicate,
                'value': value, 'text': text,
                'audience': 'player' if set(slots) <= permitted else 'internal',
                'observation_id': observation_id, 'evidence_ref': evidence_ref}
        if detail is not None:
            item['detail'] = detail
        facts.append(item)

    fact('player_x', 'player', 'world_x', player['x'],
         f"Your horizontal position is {player['x'] / 16:g} game pixels.", (PLAYER_SLOT,))
    fact('player_y', 'player', 'world_y', player['y'],
         f"Your vertical position is {player['y'] / 16:g} game pixels.", (PLAYER_SLOT,))
    fact('flower_power', 'player', 'flower_power', state['flowers'],
         f"Flower power: {state['flowers']}.", (PLAYER_SLOT,))
    fact('score', 'player', 'score', state['score'], f"Score: {state['score']}.", (PLAYER_SLOT,))
    fact('game_ticks', 'game', 'game_ticks', state['clock']['time_count'],
         'The qualified game clock is recorded in game ticks.', ())
    facts[-1]['audience'] = 'internal'
    fact('carrot_present', 'carrot_slot_40', 'present_in_live_list', present,
         'The watched actor is present.' if present else
         'The watched actor is absent.' if present is False else 'The watched actor is not locally observed.',
         (CARROT_SLOT,))
    fact('carrot_active', 'carrot_slot_40', 'active_carrot', active,
         'The carrot is active.' if active else
         'No active carrot is established in the watched slot.' if active is False else
         'The carrot activity is unknown.', (CARROT_SLOT,))
    fact('carrot_gap_world', 'carrot_slot_40', 'horizontal_body_gap_world', gap,
         f'The horizontal gap to the carrot is {gap / 16:g} game pixels.' if gap is not None else
         'The current carrot gap is unknown.', (PLAYER_SLOT, CARROT_SLOT))
    fact('carrot_vertical_overlap', 'carrot_slot_40', 'body_height_overlap', overlap,
         'Your body heights overlap.' if overlap else
         'Your body heights do not overlap.' if overlap is False else 'Height overlap is unknown.',
         (PLAYER_SLOT, CARROT_SLOT))
    fact('carrot_approaching', 'carrot_slot_40', 'observed_closing_motion', approaching,
         'The carrot moved closer during the last update.' if approaching else
         'No closing carrot motion was observed in the last update.' if approaching is False else
         'Closing carrot motion is not established from adjacent active observations.',
         (PLAYER_SLOT, CARROT_SLOT))
    fact('bonus_collectible', 'bonus_slot_31', 'available_type_zero_bonus', collectible,
         'The optional 100-point bonus remains uncollected.' if collectible else
         'The tracked 100-point bonus is no longer collectible.' if collectible is False else
         'The optional bonus is not currently observed.', (BONUS_SLOT,))
    fact('bonus_x', 'bonus_slot_31', 'world_x', bx,
         f'The bonus horizontal position is {bx / 16:g} game pixels.' if bx is not None else
         'No current collectible horizontal position is established.', (BONUS_SLOT,))
    fact('bonus_y', 'bonus_slot_31', 'world_y', by,
         f'The bonus vertical position is {by / 16:g} game pixels.' if by is not None else
         'No current collectible vertical position is established.', (BONUS_SLOT,))
    fact('bonus_points', 'bonus_slot_31', 'points_if_collected', 100 if collectible else None,
         'Collecting this optional bonus awards 100 points.' if collectible else
         'No current collectible reward is established.', (BONUS_SLOT,))
    packet['choices'] = deepcopy(choices)
    packet = validate_scene(packet)
    choice_ids = {choice['id'] for choice in packet['choices']}
    _need(set(roles.values()) <= choice_ids, 'Role binding references an absent provider choice')
    conditions = lambda identity, op, value: {'fact_id': identity, 'op': op, 'value': value}
    situations = [
        {'id': 'carrot_encounter', 'kind': 'encounter', 'priority': 70,
         'text': 'An active carrot is nearby at your height.',
         'when': [conditions('carrot_active', 'eq', True),
                  conditions('carrot_vertical_overlap', 'eq', True),
                  conditions('carrot_gap_world', 'le', 3072)],
         'fact_ids': ['carrot_active', 'carrot_vertical_overlap', 'carrot_gap_world']},
        {'id': 'carrot_closing', 'kind': 'encounter', 'priority': 80,
         'text': 'The carrot moved closer during the last update.',
         'when': [conditions('carrot_approaching', 'eq', True)],
         'fact_ids': ['carrot_active', 'carrot_approaching', 'carrot_gap_world']},
        {'id': 'empty_flower_power', 'kind': 'context', 'priority': 60,
         'text': 'You have no flower power to throw.',
         'when': [conditions('flower_power', 'eq', 0)], 'fact_ids': ['flower_power']},
        {'id': 'optional_bonus', 'kind': 'objective', 'priority': 20,
         'text': 'An optional 100-point bonus remains uncollected.',
         'when': [conditions('bonus_collectible', 'eq', True)],
         'fact_ids': ['bonus_collectible', 'bonus_x', 'bonus_y', 'bonus_points']},
    ]
    actions = []
    if 'attack' in roles:
        actions.append({'choice_id': roles['attack'],
                        'when': [conditions('flower_power', 'ge', 1),
                                 conditions('carrot_active', 'eq', True)],
                        'situation_ids': [], 'priority': 80,
                        'reason': 'A current active carrot and nonzero flower power are required; provider gates still apply.'})
    if 'collect_bonus' in roles:
        actions.append({'choice_id': roles['collect_bonus'],
                        'when': [conditions('bonus_collectible', 'eq', True)],
                        'situation_ids': ['optional_bonus'], 'priority': 20,
                        'reason': 'The observed type-zero bonus must still be collectible; no route is inferred.'})
    rules = {'format': 'dotbox-oracle-rules-1', 'source_sha256': source_sha256,
             'edition': edition,
             'qualification': 'Finite normal first-level Keen projection; qualified caller observations and existing route assertions; source-informed bonus/resource meanings; no live authentication or collision forecast.',
             'situations': situations, 'actions': actions}
    return {'scene': packet, 'rules': rules}
