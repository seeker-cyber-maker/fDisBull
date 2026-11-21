"""Pure, reversible factoring of compact Keen observations for a planner stream.

``StateEncoder.encode(state)`` returns JSON records. Feed them, in order, to
``StateDecoder.accept(record)``; only a state record returns a reconstructed
observation. ``encode_states`` and ``decode_records`` provide batch equivalents.
The controller keeps its original mapping; this module does no I/O or gameplay.

Repeated phase/map/admission fields and player/nearby-actor state definitions are
interned by complete content hashes, with small stream-local references. A
changed definition receives a new reference even when its pointer is unchanged.
Every other field, including actor motion, inputs, clocks, physics, camera,
level, playstate and lives, remains in each observation. Unknown fields, actor
order, slot/pointer values and missing fields are retained exactly.

Format 2 optionally factors state_name/state_record from a nearby list of at most
100 JSON objects. Other finite-JSON nearby values, mixed lists and longer lists
pass through unchanged. Definition values are preserved without interpreting
their game meaning. Non-JSON values remain unsupported. Format 1 streams require
their original decoder; this version refuses their header rather than guessing.

This is a representation experiment, not a world reader or a hazard model. Map
pointers do not prove unchanged terrain; admission flags are copied reports,
not renewed qualification. Reconstruction does not confer freshness or input
authority. Source/session/timeline guards remain the caller's responsibility.
"""
from __future__ import annotations

import hashlib
import json


FORMAT = 'dotbox-keen-world-stream-2'
MAX_STATE_BYTES = 16384
MAX_RECORD_BYTES = MAX_STATE_BYTES + 1024
MAX_REFERENCES = 1024
MAX_STATES = 10000
MAX_NEARBY = 100
CONTEXT_FIELDS = frozenset(('phase', 'coherent_game_update', 'phase_meaning',
                            'input_semantics', 'map', 'corridor_verified'))
DEFINITION_FIELDS = frozenset(('state_name', 'state_record'))


def _copy_json(value, limit, *, max_depth=32):
    """Reject non-JSON coercions and return an isolated canonical JSON copy."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > max_depth or nodes > MAX_STATE_BYTES:
            raise ValueError('JSON nesting or node count exceeds the stream limit')
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('JSON object keys must be strings')
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError('Stream values must use ordinary JSON types')
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')
        if len(encoded) > limit:
            raise ValueError('JSON bytes exceed the stream limit')
        return json.loads(encoded), encoded
    except (TypeError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError('Stream values must be bounded finite JSON') from error


def _state(value):
    result, _ = _copy_json(value, MAX_STATE_BYTES)
    if type(result) is not dict or type(result.get('player')) is not dict:
        raise ValueError('A compact state requires a player object')
    return result


def _fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError('Unexpected stream record fields')


def _reference(value):
    if type(value) is not int or not 0 <= value < MAX_REFERENCES:
        raise ValueError('Invalid stream reference')
    return value


def _intern(kind, table, content, records):
    _, encoded = _copy_json(content, MAX_STATE_BYTES)
    digest = hashlib.sha256(encoded).hexdigest()
    if digest not in table:
        if len(table) >= MAX_REFERENCES:
            raise ValueError('Context or definition count exceeds the stream limit')
        table[digest] = len(table)
        records.append({'type': kind, 'ref': table[digest], 'sha256': digest, 'value': content})
    return table[digest]


class StateEncoder:
    """Intern content within one bounded stream; return independent records."""

    def __init__(self):
        self._contexts = {}
        self._definitions = {}
        self._count = 0

    def encode(self, state):
        value = _state(state)
        if self._count >= MAX_STATES:
            raise ValueError('Observation count exceeds the stream limit')
        context = {key: value.pop(key) for key in sorted(CONTEXT_FIELDS) if key in value}
        player = value['player']
        definition = {key: player.pop(key) for key in sorted(DEFINITION_FIELDS) if key in player}
        records = [] if self._count else [{'type': 'start', 'format': FORMAT}]
        # Stage all new definitions so a refusal cannot consume references.
        contexts, definitions = dict(self._contexts), dict(self._definitions)
        context_ref = _intern('context', contexts, context, records)
        definition_ref = _intern('definition', definitions, definition, records)
        state_record = {'type': 'state', 'context': context_ref,
                        'definition': definition_ref, 'value': value}
        nearby = value.get('nearby')
        if (type(nearby) is list and len(nearby) <= MAX_NEARBY
                and all(type(actor) is dict for actor in nearby)):
            references = []
            for actor in nearby:
                content = {key: actor.pop(key) for key in sorted(DEFINITION_FIELDS) if key in actor}
                references.append(_intern('definition', definitions, content, records) if content else None)
            if any(reference is not None for reference in references):
                state_record['nearby_definitions'] = references
        records.append(state_record)
        self._contexts, self._definitions = contexts, definitions
        self._count += 1
        return records


class StateDecoder:
    """Validate ordered records and reconstruct states without shared aliases."""

    def __init__(self):
        self._started = False
        self._contexts = []
        self._definitions = []
        self._count = 0

    def accept(self, record):
        # The record adds one object around a state/definition. Their own
        # validation below retains the depth-32 limit after unwrapping.
        record, _ = _copy_json(record, MAX_RECORD_BYTES, max_depth=33)
        if type(record) is not dict:
            raise ValueError('Expected a stream record object')
        kind = record.get('type')
        if not self._started:
            _fields(record, ('type', 'format'))
            if kind != 'start' or record['format'] != FORMAT:
                raise ValueError('Expected the supported stream header')
            self._started = True
            return None
        if kind in ('context', 'definition'):
            _fields(record, ('type', 'ref', 'sha256', 'value'))
            table = self._contexts if kind == 'context' else self._definitions
            allowed = CONTEXT_FIELDS if kind == 'context' else DEFINITION_FIELDS
            reference = _reference(record['ref'])
            if reference != len(table):
                raise ValueError('A definition must introduce the next unused reference')
            content = record['value']
            if type(content) is not dict or not set(content) <= allowed:
                raise ValueError('Unexpected context or state-definition fields')
            content, encoded = _copy_json(content, MAX_STATE_BYTES)
            if record['sha256'] != hashlib.sha256(encoded).hexdigest():
                raise ValueError('Context or definition content hash differs')
            table.append(content)
            return None
        if kind != 'state':
            raise ValueError('Unknown or repeated stream header/record type')
        expected = ('type', 'context', 'definition', 'value')
        if 'nearby_definitions' in record:
            expected += ('nearby_definitions',)
        _fields(record, expected)
        if self._count >= MAX_STATES:
            raise ValueError('Observation count exceeds the stream limit')
        context, definition = _reference(record['context']), _reference(record['definition'])
        if context >= len(self._contexts) or definition >= len(self._definitions):
            raise ValueError('State uses an unknown context or definition reference')
        value = _state(record['value'])
        if set(value) & CONTEXT_FIELDS or set(value['player']) & DEFINITION_FIELDS:
            raise ValueError('State record duplicates factored fields')
        if 'nearby_definitions' in record:
            references, nearby = record['nearby_definitions'], value.get('nearby')
            if (type(references) is not list or type(nearby) is not list
                    or not 1 <= len(references) == len(nearby) <= MAX_NEARBY
                    or not any(reference is not None for reference in references)
                    or any(type(actor) is not dict for actor in nearby)):
                raise ValueError('Nearby references require a matching bounded list of objects')
            for actor, reference in zip(nearby, references):
                if set(actor) & DEFINITION_FIELDS:
                    raise ValueError('Nearby actor duplicates factored definition fields')
                if reference is not None:
                    reference = _reference(reference)
                    if reference >= len(self._definitions):
                        raise ValueError('Nearby actor uses an unknown definition reference')
                    actor.update(self._definitions[reference])
        value.update(self._contexts[context])
        value['player'].update(self._definitions[definition])
        result = _state(value)
        self._count += 1
        return result


def encode_states(states):
    """Return the complete bounded stream, including its header and definitions."""
    encoder = StateEncoder()
    return [record for state in states for record in encoder.encode(state)]


def decode_records(records):
    """Reconstruct every state from a complete ordered stream of JSON records."""
    decoder = StateDecoder()
    states = []
    for record in records:
        state = decoder.accept(record)
        if state is not None:
            states.append(state)
    return states
