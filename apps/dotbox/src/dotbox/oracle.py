"""Deterministic situation and choice reduction over a bound scene observation.

This module performs no I/O, game input, live observation or state commitment.
The provider owns the meaning/freshness of facts and input-route admission.
Rules can narrow existing choices; they cannot create routes or grant readiness.
Forecasts remain an explicitly conditional sidecar, never observed scene facts.
Select from the returned scene through the existing ``scenes.select_choice``.
"""

from copy import deepcopy
import hashlib
import json
import re

from . import scenes


FORMAT = 'dotbox-oracle-assessment-1'
RULE_FORMAT = 'dotbox-oracle-rules-1'
MAX_RULE_BYTES = 128 * 1024
CLAIM = ('Deterministic evaluation of supplied bound observations; no independent '
         'authentication of live game state or replacement for provider input admission')
_ID = re.compile(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_OPS = ('eq', 'ne', 'lt', 'le', 'gt', 'ge')
_KINDS = ('hazard', 'encounter', 'objective', 'context')
_UNITS = ('frames', 'game_ticks', 'updates', 'turns')
_FORECAST_REFS = ('clock_fact', 'x_fact', 'y_fact', 'vx_fact', 'vy_fact', 'surface_y_fact')
_MIN, _MAX = -(1 << 63), (1 << 63) - 1


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _fields(value, required, optional=()):
    _require(type(value) is dict and set(required) <= set(value)
             and set(value) <= set(required) | set(optional), 'Unsupported or missing oracle fields')


def _text(value, name, limit=2048):
    _require(type(value) is str and value.strip() and len(value) <= limit,
             f'{name} must be bounded nonempty text')


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value) is not None, 'Invalid oracle identifier')


def _sha(value):
    _require(type(value) is str and _SHA.fullmatch(value) is not None, 'Invalid oracle SHA-256')


def _integer(value, low, high, name):
    _require(type(value) is int and low <= value <= high, f'Invalid bounded integer: {name}')


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError('Oracle data must be finite bounded JSON') from error


def _refs(value, name, maximum=32):
    _require(type(value) is list and len(value) <= maximum, f'{name} exceeds its list bound')
    for item in value:
        _identifier(item)
    _require(len(value) == len(set(value)), f'{name} contains duplicate references')


def _conditions(value):
    _require(type(value) is list and len(value) <= 8, 'At most eight conditions are allowed')
    for condition in value:
        _fields(condition, ('fact_id', 'op', 'value'))
        _identifier(condition['fact_id'])
        _require(condition['op'] in _OPS, 'Unsupported oracle comparison')
        expected = condition['value']
        _require(type(expected) in (str, bool, int, type(None)), 'Comparison requires a scalar value')
        if type(expected) is str:
            _require(len(expected) <= 2048, 'Comparison string exceeds its bound')
        if condition['op'] not in ('eq', 'ne'):
            _integer(expected, _MIN, _MAX, 'ordered comparison value')


def _forecast_rule(value):
    _fields(value, ('kind', 'model_id', 'qualification', 'clock_fact', 'clock_unit',
                    'x_fact', 'y_fact', 'vx_fact', 'vy_fact', 'surface_y_fact', 'horizon'))
    _require(value['kind'] == 'linear_impact' and value['model_id'] == 'linear-point-downward-v1',
             'Unsupported oracle forecast model')
    _text(value['qualification'], 'Forecast qualification')
    _require(value['clock_unit'] in _UNITS, 'Forecast clock unit must be explicit')
    _integer(value['horizon'], 1, 120, 'forecast horizon')
    for name in _FORECAST_REFS:
        _identifier(value[name])


def _rules(value, scene):
    encoded = _encode(value)
    _require(len(encoded) <= MAX_RULE_BYTES, 'Oracle rules exceed the 128 KiB byte bound')
    _fields(value, ('format', 'source_sha256', 'edition', 'qualification', 'situations', 'actions'))
    _require(value['format'] == RULE_FORMAT, 'Unsupported oracle rule format')
    _sha(value['source_sha256'])
    _text(value['edition'], 'Rule edition', 256)
    _text(value['qualification'], 'Rule qualification')
    _require(value['source_sha256'] == scene['source_sha256'] and value['edition'] == scene['edition'],
             'Oracle source or edition differs from the bound scene')
    _require(type(value['situations']) is list and len(value['situations']) <= 16,
             'At most sixteen situations are allowed')
    ids = set()
    for situation in value['situations']:
        _fields(situation, ('id', 'kind', 'priority', 'text', 'when', 'fact_ids'), ('forecast',))
        _identifier(situation['id'])
        _require(situation['id'] not in ids, 'Duplicate situation identifier')
        ids.add(situation['id'])
        _require(situation['kind'] in _KINDS, 'Unsupported situation kind')
        _integer(situation['priority'], 0, 100, 'situation priority')
        _text(situation['text'], 'Situation text')
        _conditions(situation['when'])
        _refs(situation['fact_ids'], 'Situation fact IDs')
        if 'forecast' in situation:
            _forecast_rule(situation['forecast'])
    _require(type(value['actions']) is list and len(value['actions']) <= 32,
             'At most thirty-two action rules are allowed')
    choice_ids = {choice['id'] for choice in scene['choices']}
    used = set()
    for action in value['actions']:
        _fields(action, ('choice_id', 'when', 'situation_ids', 'priority', 'reason'))
        _identifier(action['choice_id'])
        _require(action['choice_id'] in choice_ids, 'Oracle action references an unknown existing choice')
        _require(action['choice_id'] not in used, 'Duplicate choice rule')
        used.add(action['choice_id'])
        _conditions(action['when'])
        _refs(action['situation_ids'], 'Action situation IDs', 16)
        _require(set(action['situation_ids']) <= ids, 'Action references an unknown situation')
        _integer(action['priority'], 0, 100, 'action priority')
        _text(action['reason'], 'Action reason')
    return json.loads(encoded), hashlib.sha256(encoded).hexdigest()


def _and(values):
    values = tuple(values)
    return 'false' if 'false' in values else 'unknown' if 'unknown' in values else 'true'


def _or(values):
    values = tuple(values)
    return 'true' if 'true' in values else 'unknown' if 'unknown' in values else 'false'


def _value(facts, identity, observation):
    fact = facts.get(identity)
    if fact is None or fact['observation_id'] != observation or fact['audience'] != 'player':
        return None
    return fact['value']


def _condition_status(conditions, facts, observation):
    results = []
    for condition in conditions:
        actual = _value(facts, condition['fact_id'], observation)
        expected, op = condition['value'], condition['op']
        if actual is None or expected is None:
            results.append('unknown')
            continue
        if op in ('eq', 'ne'):
            equal = type(actual) is type(expected) and actual == expected
            result = equal if op == 'eq' else not equal
        elif type(actual) is not int:
            results.append('unknown')
            continue
        else:
            result = {'lt': actual < expected, 'le': actual <= expected,
                      'gt': actual > expected, 'ge': actual >= expected}[op]
        results.append('true' if result else 'false')
    return _and(results)


def _forecast(rule, facts, binding):
    result = {'kind': rule['kind'], 'status': 'unknown', 'model_id': rule['model_id'],
              'qualification': rule['qualification'],
              **{key: binding[key] for key in ('source_sha256', 'rules_sha256', 'scene_sha256', 'observation_id')},
              'clock_unit': rule['clock_unit'], 'horizon': rule['horizon'],
              'dependency_fact_ids': list(dict.fromkeys(rule[key] for key in _FORECAST_REFS)),
              'assumptions': ['Constant velocity during every declared clock step.',
                              'Positive y points downward; the surface is fixed and horizontal.',
                              'No intervening collision, motion change or input changes this path.',
                              'The supplied clock unit and discrete point-contact model are qualified by the caller.',
                              'Frames, when selected, mean simulation frames rather than screenshots or rendering cadence.'],
              'origin_clock': None, 'eta': None, 'deadline': None, 'contact_point': None, 'reason': None}
    values = [_value(facts, rule[key], binding['observation_id']) for key in _FORECAST_REFS]
    if any(type(value) is not int for value in values):
        result['reason'] = 'missing_or_noninteger_dependencies'
        return result
    if any(not _MIN <= value <= _MAX for value in values):
        result.update(status='unavailable', reason='numeric_dependencies_out_of_range')
        return result
    clock, x, y, vx, vy, surface = values
    result['origin_clock'] = clock
    if clock < 0 or vy <= 0 or y >= surface:
        result.update(status='unavailable', reason='not_a_future_downward_impact')
        return result
    distance = surface - y
    if distance > _MAX:
        result.update(status='unavailable', reason='prediction_out_of_range')
        return result
    steps, remainder = divmod(distance, vy)
    steps += int(remainder != 0)
    if steps > rule['horizon']:
        result.update(status='unavailable', reason='no_impact_within_horizon')
        return result
    x_travel, y_travel = vx * steps, vy * steps
    contact_x, deadline = x + x_travel, clock + steps
    if (not _MIN <= x_travel <= _MAX or not 0 <= y_travel <= _MAX
            or not _MIN <= y + y_travel <= _MAX
            or not _MIN <= contact_x <= _MAX or deadline > _MAX):
        result.update(status='unavailable', reason='prediction_out_of_range')
        return result
    result.update(status='predicted', eta=steps, deadline=deadline,
                  contact_point=[contact_x, surface])
    return result


def _provider_status(choice, visible_ids, observation):
    values, reasons = [], []
    for field, reason in (('available', 'provider_unavailable'), ('enabled', 'provider_disabled'),
                          ('ready', 'provider_not_ready')):
        value = choice.get(field, True)
        values.append('true' if value is True else 'false' if value is False else 'unknown')
        if value is not True:
            reasons.append(reason if value is False else reason + '_unknown')
    if choice['observation_id'] != observation:
        values.append('unknown')
        reasons.append('stale_choice_observation')
    if not set(choice['requires']) <= visible_ids:
        values.append('unknown')
        reasons.append('required_public_facts_unavailable')
    return _and(values), reasons


def _hud(view, situations):
    """Render only the already permitted presentation, without private bindings."""
    result = {'format': 'dotbox-oracle-hud-1', **{
        key: deepcopy(view[key]) for key in ('title', 'scene_id', 'observation_id', 'scene_sha256',
                                             'facts', 'choices', 'suggested_choice_ids', 'choice_prompt')}}
    result['situations'] = []
    units = {'frames': ('simulation frame', 'simulation frames'),
             'game_ticks': ('game tick', 'game ticks'),
             'updates': ('update', 'updates'), 'turns': ('turn', 'turns')}
    for situation in situations:
        public = {key: situation[key] for key in ('id', 'kind', 'priority', 'text', 'status')}
        if 'forecast' in situation:
            forecast = situation['forecast']
            if forecast['status'] == 'predicted':
                shown = {key: deepcopy(forecast[key]) for key in
                         ('status', 'eta', 'clock_unit', 'deadline', 'contact_point')}
                x, y = shown['contact_point']
                unit = units[shown['clock_unit']][int(shown['eta'] != 1)]
                shown['text'] = (f'Contact predicted at ({x}, {y}) in {shown["eta"]} {unit} '
                                 'if motion remains unchanged.')
            else:
                shown = {'status': forecast['status'], 'text':
                         'Contact timing is unknown.' if forecast['status'] == 'unknown'
                         else 'No contact estimate is available.'}
            public['forecast'] = shown
        result['situations'].append(public)
    return result


def evaluate_oracle(scene, rules, *, expected_scene_sha256, expected_observation_id,
                    expected_state_context, choice_limit=3):
    """Reduce existing choices using current public facts and qualified rules.

    Forecasts and private reasons remain outside the scene's observation facts.
    ``hud`` exposes permitted descriptions and explicit conditional forecasts,
    while omitting private qualification, evidence and input-context metadata.
    The result is a copied scene, not a state update or an execution lease.
    Compile before recording one packet per provider revision in SceneStore.
    """
    scene = scenes.validate_scene(scene)
    _sha(expected_scene_sha256)
    _text(expected_observation_id, 'Expected observation ID')
    _integer(choice_limit, 1, 32, 'choice limit')
    _require('state_context' in scene, 'Oracle evaluation requires a provider state context')
    scene_sha = scenes._digest(scene)
    _require(scene_sha == expected_scene_sha256 and scene['observation_id'] == expected_observation_id
             and _encode(scene['state_context']) == _encode(expected_state_context),
             'Stale or changed scene, observation or provider context')
    rules, rules_sha = _rules(rules, scene)
    observation = scene['observation_id']
    binding = {'source_sha256': scene['source_sha256'], 'scene_sha256': scene_sha,
               'rules_sha256': rules_sha, 'observation_id': observation,
               'state_context': deepcopy(scene['state_context'])}
    facts = {fact['id']: fact for fact in scene['facts']}
    visible_ids = {fact['id'] for fact in scene['facts']
                   if fact['observation_id'] == observation and fact['audience'] == 'player'}
    situations, situation_status = [], {}
    for rule in rules['situations']:
        dependencies = list(dict.fromkeys(rule['fact_ids'] + [item['fact_id'] for item in rule['when']]))
        status = _and((_condition_status(rule['when'], facts, observation),
                       'true' if all(_value(facts, identity, observation) is not None
                                     for identity in dependencies) else 'unknown'))
        situation_status[rule['id']] = status
        if status == 'true':
            situation = {key: rule[key] for key in ('id', 'kind', 'priority', 'text')}
            situation.update(status='derived', fact_ids=dependencies, observation_id=observation)
            if 'forecast' in rule:
                situation['forecast'] = _forecast(rule['forecast'], facts, binding)
            situations.append(situation)
    situations.sort(key=lambda item: -item['priority'])

    action_rules = {rule['choice_id']: rule for rule in rules['actions']}
    assessments, ranks = [], {}
    for choice in scene['choices']:
        provider, reasons = _provider_status(choice, visible_ids, observation)
        rule = action_rules.get(choice['id'])
        condition, situation = 'true', 'true'
        if rule is not None:
            condition = _condition_status(rule['when'], facts, observation)
            if rule['situation_ids']:
                situation = _or(situation_status[identity] for identity in rule['situation_ids'])
            for label, state in (('condition', condition), ('situation', situation)):
                if state != 'true':
                    reasons.append(label + '_' + state)
            gate = _and((condition, situation))
            if gate != 'true' and choice.get('enabled', True) is True:
                choice['enabled'] = False if gate == 'false' else None
        status = _and((provider, condition, situation))
        if rule is not None and status == 'true' and choice.get('suggestion', 'normal') != 'on_request':
            choice['suggestion'] = 'prefer'
            ranks[choice['id']] = rule['priority']
        assessments.append({'choice_id': choice['id'], 'audience': 'internal',
                            'status': {'true': 'eligible', 'false': 'blocked', 'unknown': 'unknown'}[status],
                            'reason': rule['reason'] if rule is not None else None, 'reasons': reasons,
                            'condition_status': condition, 'situation_status': situation,
                            'provider_eligible': provider == 'true'})
    # Stable sorting preserves declaration order for equal priorities and unruled choices.
    scene['choices'].sort(key=lambda choice: (0, -ranks[choice['id']]) if choice['id'] in ranks else (1, 0))
    scene = scenes.validate_scene(scene)
    view = scenes.project_scene(scene, choice_limit=choice_limit)
    return {'format': FORMAT, 'binding': binding, 'scene': scene,
            'view': view, 'hud': _hud(view, situations),
            'situations': situations, 'action_assessments': assessments,
            'execution': 'not_performed', 'claim': CLAIM}
