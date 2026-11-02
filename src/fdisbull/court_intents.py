"""Pure court-interaction intent evaluator; no AGI addresses or instruction VM.

The definition selects outcomes and ordered domain effects. A separate UDL
adapter binds them to the source. Animation completion is supplied by the
qualified engine; this evaluator never invents ticks or acknowledges a modal.
"""
from __future__ import annotations

import copy
from hashlib import sha256
import json

FORMAT = 'fdisbull-court-intent-uil-1'
_TEXT_KEYS = {'response', 'invisible', 'improper_position', 'repeat', 'distant'}
_NUMBERS = {'actor_x', 'actor_y', 'score', 'direction', 'sequence_countdown', 'treasure_count'}
_BOOLEANS = {'player_control', 'bowed_this_visit', 'respect_awarded', 'invisible',
             'standing_animation', 'bow_complete', 'input_ready', 'input_consumed'}
_FIELDS = _NUMBERS | _BOOLEANS | {'command'}
_INTENTS = {'input.claim', 'court.begin_bow', 'court.award_first_respect',
            'court.finish_bow', 'narration.modal'}


class CourtIntentError(ValueError):
    """Malformed definition, semantic state, event or continuation."""


class _Unknown(Exception):
    pass


def canonical_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def build_definition(resources):
    """Build executable, source-coordinate-free rules for the initial audience."""
    field = lambda name, value: {'field': name, 'eq': value}
    inside = lambda zone, value=True: {'zone': zone, 'inside': value}
    claim = {'intent': 'input.claim'}
    modal = lambda name: {'intent': 'narration.modal', 'resource': name}
    near = inside('addressing')
    return {
        'format': FORMAT, 'id': 'court.initial-audience-bow',
        'resources': dict(resources),
        'geometry': {'addressing': [18, 80, 86, 113],
                     'improper_position': [18, 80, 67, 107],
                     'distance_reference': [60, 85, 86, 113]},
        'gesture': {'start_dx': -7, 'finish_dx': 7},
        'reward': {'points': 3, 'modulus': 256},
        'requires': [{'field': 'treasure_count', 'ne': 3}],
        'command_outcomes': [
            {'id': 'unseen', 'when': [near, field('invisible', True)],
             'steps': [claim, modal('invisible')]},
            {'id': 'improper_position', 'when': [near, inside('improper_position')],
             'steps': [claim, modal('improper_position')]},
            {'id': 'bow_started', 'when': [near, field('sequence_countdown', 0),
                                          field('bowed_this_visit', False)],
             'steps': [claim, {'intent': 'court.begin_bow'},
                       {'intent': 'court.award_first_respect'}]},
            {'id': 'already_bowed_or_busy', 'when': [near],
             'steps': [claim, modal('repeat')]},
            {'id': 'too_far', 'when': [inside('distance_reference', False),
                                      inside('improper_position', False),
                                      field('sequence_countdown', 0)],
             'steps': [claim, modal('distant')]},
        ],
        'completion': {'when': [field('bow_complete', True)],
                       'steps': [{'intent': 'court.finish_bow'}, modal('response')]},
        'residual_before_command': 'refresh_position_flag',
        'host_dependencies': ['animation_scheduler', 'rendering', 'modal_input_and_clock'],
    }


def _keys(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise CourtIntentError(f'Invalid {label} fields')


def _conditions(rows, zones):
    if not isinstance(rows, list) or len(rows) > 24:
        raise CourtIntentError('Conditions must be a bounded list')
    for row in rows:
        if not isinstance(row, dict):
            raise CourtIntentError('Invalid condition')
        if 'zone' in row:
            _keys(row, ('zone', 'inside'), 'zone condition')
            if not isinstance(row['zone'], str) or row['zone'] not in zones or type(row['inside']) is not bool:
                raise CourtIntentError('Invalid spatial condition')
        else:
            operation = 'eq' if 'eq' in row else 'ne'
            _keys(row, ('field', operation), 'field condition')
            name = row['field']
            if not isinstance(name, str) or name not in _NUMBERS | _BOOLEANS:
                raise CourtIntentError('Unknown semantic condition field')
            expected = int if name in _NUMBERS else bool
            if type(row[operation]) is not expected:
                raise CourtIntentError('Condition has wrong semantic type')
            if expected is int and not 0 <= row[operation] <= 255:
                raise CourtIntentError('Condition byte outside profile')


def _steps(rows, resources):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        raise CourtIntentError('Steps must be a nonempty bounded list')
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or not isinstance(row.get('intent'), str)
                or row['intent'] not in _INTENTS):
            raise CourtIntentError('Unknown intent primitive')
        if row['intent'] == 'narration.modal':
            _keys(row, ('intent', 'resource'), 'modal step')
            if not isinstance(row['resource'], str) or row['resource'] not in resources or index != len(rows) - 1:
                raise CourtIntentError('A modal must be the final step of its phase')
        else:
            _keys(row, ('intent',), 'intent step')


def validate_intent(document):
    _keys(document, ('format', 'id', 'resources', 'geometry', 'gesture', 'reward',
                     'requires', 'command_outcomes', 'completion',
                     'residual_before_command', 'host_dependencies'), 'court UIL')
    if document['format'] != FORMAT or not isinstance(document['id'], str) or not 1 <= len(document['id']) <= 160:
        raise CourtIntentError('Invalid court profile identity')
    resources = document['resources']
    if not isinstance(resources, dict) or set(resources) != _TEXT_KEYS:
        raise CourtIntentError('Invalid court resources')
    if any(not isinstance(text, str) or len(text.encode()) > 16384 for text in resources.values()):
        raise CourtIntentError('Invalid or excessive narrative text')
    geometry = document['geometry']
    if not isinstance(geometry, dict) or set(geometry) != {'addressing', 'improper_position', 'distance_reference'}:
        raise CourtIntentError('Invalid court geometry')
    for rectangle in geometry.values():
        if (not isinstance(rectangle, list) or len(rectangle) != 4 or
                any(type(v) is not int or not 0 <= v <= 255 for v in rectangle) or
                rectangle[0] > rectangle[2] or rectangle[1] > rectangle[3]):
            raise CourtIntentError('Invalid inclusive rectangle')
    _keys(document['gesture'], ('start_dx', 'finish_dx'), 'gesture')
    if any(type(v) is not int or not -255 <= v <= 255 for v in document['gesture'].values()):
        raise CourtIntentError('Invalid gesture displacement')
    _keys(document['reward'], ('points', 'modulus'), 'reward')
    if (type(document['reward']['points']) is not int or not 0 <= document['reward']['points'] <= 255
            or document['reward']['modulus'] != 256 or type(document['reward']['modulus']) is not int):
        raise CourtIntentError('Invalid score arithmetic profile')
    _conditions(document['requires'], geometry)
    rules = document['command_outcomes']
    if not isinstance(rules, list) or not 1 <= len(rules) <= 16:
        raise CourtIntentError('Invalid outcome count')
    names = set()
    for rule in rules:
        _keys(rule, ('id', 'when', 'steps'), 'outcome')
        if not isinstance(rule['id'], str) or not 1 <= len(rule['id']) <= 100 or rule['id'] in names:
            raise CourtIntentError('Invalid or duplicate outcome identity')
        names.add(rule['id'])
        _conditions(rule['when'], geometry)
        _steps(rule['steps'], resources)
    _keys(document['completion'], ('when', 'steps'), 'completion')
    _conditions(document['completion']['when'], geometry)
    _steps(document['completion']['steps'], resources)
    if document['residual_before_command'] != 'refresh_position_flag':
        raise CourtIntentError('Unknown residual binding')
    if document['host_dependencies'] != ['animation_scheduler', 'rendering', 'modal_input_and_clock']:
        raise CourtIntentError('Missing host timing or presentation contract')
    return document


def validate_state(state):
    _keys(state, _FIELDS, 'semantic state')
    for name in _NUMBERS:
        if state[name] is not None and (type(state[name]) is not int or not 0 <= state[name] <= 255):
            raise CourtIntentError(f'Invalid byte field {name}')
    for name in _BOOLEANS:
        if state[name] is not None and type(state[name]) is not bool:
            raise CourtIntentError(f'Invalid Boolean field {name}')
    if state['command'] not in (None, 'bow', 'bow_to_king'):
        raise CourtIntentError('Unsupported command identity')


def _known(state, name):
    value = state[name]
    if value is None:
        raise _Unknown(name)
    return value


def _matches(rows, state, geometry):
    for row in rows:
        if 'zone' in row:
            x, y = _known(state, 'actor_x'), _known(state, 'actor_y')
            left, top, right, bottom = geometry[row['zone']]
            matched = (left <= x <= right and top <= y <= bottom) == row['inside']
        else:
            value = _known(state, row['field'])
            matched = value == row['eq'] if 'eq' in row else value != row['ne']
        if not matched:
            return False
    return True


def evaluate_event(document, state, event):
    """Execute one selected dispatch segment or acknowledge its pending modal.

    ``cycle`` means the qualified room-dispatch segment, not a whole AGI cycle.
    ``bow_complete`` is an observed engine event in the supplied state. A new
    command runs before that completion, and a new bow clears stale completion.
    Acknowledgement resumes the same segment without claiming a new command.
    """
    validate_intent(document)
    validate_state(state)
    if not isinstance(event, dict) or event.get('kind') not in ('cycle', 'ack'):
        raise CourtIntentError('Invalid court event')
    phase = 'command'
    if event['kind'] == 'cycle':
        _keys(event, ('kind',), 'dispatch event')
    else:
        _keys(event, ('kind', 'continuation'), 'acknowledgement')
        token = event['continuation']
        _keys(token, ('model_sha256', 'state_sha256', 'next_phase', 'resource'), 'continuation')
        if (token['model_sha256'] != canonical_digest(document) or
                token['state_sha256'] != canonical_digest(state) or
                token['next_phase'] not in ('completion', 'end') or not isinstance(token['resource'], str)
                or token['resource'] not in document['resources']):
            raise CourtIntentError('Stale or invalid modal continuation')
        phase = token['next_phase']
    current, effects, executed = copy.deepcopy(state), [], []
    outcome, continuation = 'no_bow_action', None

    def perform(steps, next_phase):
        nonlocal continuation
        for step in steps:
            name = step['intent']
            if name == 'input.claim':
                current['input_consumed'] = True
            elif name == 'court.begin_bow':
                current['actor_x'] = (_known(current, 'actor_x') + document['gesture']['start_dx']) % 256
                current.update(bowed_this_visit=True, player_control=False, direction=0,
                               standing_animation=True, bow_complete=False)
            elif name == 'court.award_first_respect':
                if _known(current, 'respect_awarded'):
                    continue
                current['score'] = (_known(current, 'score') + document['reward']['points']) % 256
                current['respect_awarded'] = True
            elif name == 'court.finish_bow':
                current['actor_x'] = (_known(current, 'actor_x') + document['gesture']['finish_dx']) % 256
                current.update(bow_complete=False, standing_animation=False,
                               player_control=True, direction=0)
            elif name == 'narration.modal':
                continuation = {'model_sha256': canonical_digest(document),
                                'state_sha256': canonical_digest(current),
                                'next_phase': next_phase, 'resource': step['resource']}
            effects.append(dict(step))
            executed.append(name)

    try:
        if not _matches(document['requires'], current, document['geometry']):
            raise _Unknown('outside_declared_audience')
        if phase == 'command':
            # The original position-classification flag is still an explicit
            # source implementation detail. It is not counted as recovered intent.
            _known(current, 'actor_x'); _known(current, 'actor_y')
            effects.append({'residual_ir': document['residual_before_command']})
            available = _known(current, 'input_ready') and not _known(current, 'input_consumed')
            if available:
                if current['command'] is None:
                    raise _Unknown('unrecovered_parser_command')
                for rule in document['command_outcomes']:
                    if _matches(rule['when'], current, document['geometry']):
                        outcome = rule['id']
                        perform(rule['steps'], 'completion')
                        break
            phase = 'completion'
        if phase == 'completion' and continuation is None:
            if _matches(document['completion']['when'], current, document['geometry']):
                perform(document['completion']['steps'], 'end')
                outcome = 'bow_completed'
    except _Unknown as error:
        return {'status': 'unrecovered', 'outcome': 'unrecovered', 'reason': str(error),
                'state': copy.deepcopy(state), 'effects': [], 'executed_intents': [],
                'continuation': None}
    return {'status': 'awaiting_ack' if continuation else 'slice_complete',
            'outcome': outcome, 'state': current, 'effects': effects,
            'executed_intents': executed, 'continuation': continuation}
