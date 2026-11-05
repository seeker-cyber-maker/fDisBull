"""Read-only, observer-scoped views over an authored large-world fixture.

This study is a projection adapter, not a game simulator, pathfinder, action
executor, production Z parser, or automatic observation/recovery system.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import uuid


PROFILE = 'z-world-view-study-1'
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_ENTITIES = 4096
MAX_CURSORS = 256


def exact(value, required, optional=()):
    if (type(value) is not dict or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise ValueError('Unexpected or missing fields')


def text(value, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise ValueError('A nonempty bounded string is required')


def records(value, maximum, key='id'):
    if type(value) is not list or len(value) > maximum:
        raise ValueError('A bounded record list is required')
    result = {}
    for item in value:
        if type(item) is not dict or key not in item:
            raise ValueError('Missing record identity')
        text(item[key])
        if item[key] in result:
            raise ValueError('Duplicate record identity')
        result[item[key]] = item
    return result


def string_list(value, known=None):
    if type(value) is not list or len(value) > MAX_ENTITIES:
        raise ValueError('A bounded string list is required')
    for item in value:
        text(item)
        if known is not None and item not in known:
            raise ValueError('Unresolved reference')
    if len(set(value)) != len(value):
        raise ValueError('Duplicate list member')


def json_value(value, depth=0):
    """Bound nested public/private data without inventing game field types."""
    if depth > 8:
        raise ValueError('Value nesting exceeded')
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if len(value) > 4096:
            raise ValueError('Text value too large')
        return
    if type(value) is list and len(value) <= MAX_ENTITIES:
        for child in value:
            json_value(child, depth + 1)
        return
    if type(value) is dict and len(value) <= 128:
        for key, child in value.items():
            text(key)
            json_value(child, depth + 1)
        return
    raise ValueError('Unsupported or oversized JSON value')


def validate(document):
    exact(document, ('format', 'world', 'clock', 'spaces', 'entities', 'views', 'observers', 'actions'))
    if document['format'] != PROFILE:
        raise ValueError('Unsupported world-view study profile')
    exact(document['world'], ('id', 'setting', 'evidence', 'coverage'))
    text(document['world']['id'])
    text(document['world']['setting'])
    if (document['world']['evidence'] != 'authored-design-fixture'
            or document['world']['coverage'] != 'illustrative-partial'):
        raise ValueError('This study accepts explicitly authored partial fixtures only')
    exact(document['clock'], ('unit', 'position'))
    if document['clock']['unit'] not in ('simulation_tick', 'turn'):
        raise ValueError('Unsupported illustrative clock domain')
    if type(document['clock']['position']) is not int or document['clock']['position'] < 0:
        raise ValueError('Clock position must be a nonnegative integer')

    spaces = records(document['spaces'], 128)
    for space in spaces.values():
        exact(space, ('id', 'kind', 'parent', 'dimensions'))
        if space['kind'] not in ('grid', 'graph', 'abstract'):
            raise ValueError('Unsupported space kind')
        if type(space['dimensions']) is not int or space['dimensions'] not in (0, 2, 3):
            raise ValueError('Unsupported coordinate dimensions')
        if space['kind'] != 'grid' and space['dimensions'] != 0:
            raise ValueError('Graph and abstract spaces have no coordinates in this study')
        if space['kind'] == 'grid' and space['dimensions'] not in (2, 3):
            raise ValueError('Grid space needs coordinate dimensions')
        parent = space['parent']
        if parent is not None and (type(parent) is not str or parent not in spaces):
            raise ValueError('Unresolved parent space')
    check_parent_cycles(spaces)

    entities = records(document['entities'], MAX_ENTITIES)
    for entity in entities.values():
        exact(entity, ('id', 'kind', 'state', 'bindings'))
        text(entity['kind'])
        for field in ('state', 'bindings'):
            if type(entity[field]) is not dict:
                raise ValueError('Private state and bindings must be objects')
            json_value(entity[field])

    views = records(document['views'], 128)
    for view in views.values():
        exact(view, ('id', 'title', 'parent', 'spaces', 'descendants', 'kinds', 'entities'))
        text(view['title'])
        if view['parent'] is not None and (type(view['parent']) is not str or view['parent'] not in views):
            raise ValueError('Unresolved parent view')
        if type(view['descendants']) is not bool:
            raise ValueError('Exact Boolean descendants policy required')
        string_list(view['spaces'], spaces)
        string_list(view['kinds'])
        string_list(view['entities'], entities)
    check_parent_cycles(views)

    actions = records(document['actions'], 128)
    for action in actions.values():
        exact(action, ('id', 'label', 'uil_contract_ref', 'binding_status'))
        for field in ('label', 'uil_contract_ref'):
            text(action[field])
        if action['binding_status'] != 'unbound':
            raise ValueError('This adapter cannot execute action contracts')

    observers = records(document['observers'], 32)
    for observer in observers.values():
        exact(observer, ('id', 'records', 'actions'))
        string_list(observer['actions'], actions)
        observations = records(observer['records'], MAX_ENTITIES, 'entity')
        for observation in observations.values():
            exact(observation, ('entity', 'fields'))
            if observation['entity'] not in entities:
                raise ValueError('Observation refers to an unknown entity identity')
            fields = observation['fields']
            if type(fields) is not dict or not fields or len(fields) > 64:
                raise ValueError('A nonempty bounded field map is required')
            for name, fact in fields.items():
                text(name)
                if type(fact) is not dict:
                    raise ValueError('Knowledge field must be an object')
                if fact.get('knowledge') == 'unknown':
                    exact(fact, ('knowledge',))
                    continue
                exact(fact, ('knowledge', 'value', 'observed_at'))
                if fact['knowledge'] not in ('current', 'remembered'):
                    raise ValueError('Unsupported knowledge state')
                stamp = fact['observed_at']
                exact(stamp, ('unit', 'position'))
                if (stamp['unit'] != document['clock']['unit'] or type(stamp['position']) is not int
                        or not 0 <= stamp['position'] <= document['clock']['position']):
                    raise ValueError('Observation time is outside this snapshot domain')
                if fact['knowledge'] == 'current' and stamp['position'] != document['clock']['position']:
                    raise ValueError('Current knowledge must identify the current snapshot coordinate')
                json_value(fact['value'])
                if name == 'location':
                    validate_location(fact['value'], spaces)
                if name in ('label', 'kind'):
                    text(fact['value'])
    encoded = json.dumps(document, allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise ValueError('Document exceeds the study byte limit')
    return True


def check_parent_cycles(table):
    for identifier in table:
        seen = set()
        cursor = identifier
        while cursor is not None:
            if cursor in seen:
                raise ValueError('Parent graph contains a cycle')
            seen.add(cursor)
            cursor = table[cursor]['parent']


def validate_location(location, spaces):
    exact(location, ('space',), ('position',))
    if type(location['space']) is not str or location['space'] not in spaces:
        raise ValueError('Location uses an unknown space')
    dimensions = spaces[location['space']]['dimensions']
    if dimensions == 0:
        if 'position' in location:
            raise ValueError('Abstract/graph locations cannot invent coordinates')
    else:
        position = location.get('position')
        if (type(position) is not list or len(position) != dimensions
                or any(type(x) is not int for x in position)):
            raise ValueError('Grid location requires the declared integer coordinates')


class WorldView:
    """One stored snapshot, many passive views; no simulation is performed."""

    def __init__(self, document):
        self._session = uuid.uuid4().hex
        self._revision = -1
        self._cursors = OrderedDict()
        self.replace_snapshot(document)

    def replace_snapshot(self, document):
        """Ingest a new/restored fixture; equal values still create a new epoch."""
        validate(document)
        self._document = deepcopy(document)
        self._revision += 1
        self._cursors.clear()
        self._spaces = {item['id']: item for item in self._document['spaces']}
        self._views = {item['id']: item for item in self._document['views']}
        self._observers = {item['id']: item for item in self._document['observers']}
        self._actions = {item['id']: item for item in self._document['actions']}

    def private_snapshot(self):
        return deepcopy(self._document)

    def epoch(self):
        return {'session': self._session, 'revision': self._revision}

    def _space_matches(self, space_id, view):
        if not view['spaces']:
            return True
        cursor = space_id
        while cursor is not None:
            if cursor in view['spaces']:
                return True
            if not view['descendants']:
                return False
            cursor = self._spaces[cursor]['parent']
        return False

    def _matches(self, observation, view):
        # Filter only admitted observations. Hidden authoritative location, kind,
        # ownership, and changes must never alter this observer's membership.
        if view['entities'] and observation['entity'] not in view['entities']:
            return False
        fields = observation['fields']
        if view['kinds']:
            kind = fields.get('kind', {'knowledge': 'unknown'})
            if kind['knowledge'] == 'unknown' or kind['value'] not in view['kinds']:
                return False
        if view['spaces']:
            location = fields.get('location', {'knowledge': 'unknown'})
            if location['knowledge'] == 'unknown' or not self._space_matches(location['value']['space'], view):
                return False
        return True

    def observe(self, view_id, observer_id, limit=3, cursor=None):
        if type(view_id) is not str or view_id not in self._views:
            raise ValueError('Unknown view')
        if type(observer_id) is not str or observer_id not in self._observers:
            raise ValueError('Unknown observer')
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError('Page size must be an integer1..128')
        scope = (self._session, self._revision, self._document['world']['id'], view_id, observer_id, limit)
        offset = 0
        if cursor is not None:
            if type(cursor) is not str or cursor not in self._cursors:
                raise ValueError('Unknown or expired cursor')
            previous_scope, offset = self._cursors[cursor]
            if previous_scope != scope:
                raise ValueError('Cursor belongs to a different epoch, observer, view, or page size')
        view = self._views[view_id]
        observer = self._observers[observer_id]
        known = sorted((row for row in observer['records'] if self._matches(row, view)),
                       key=lambda row: row['entity'])
        page = known[offset:offset + limit]
        end = offset + len(page)
        next_cursor = None
        if end < len(known):
            next_cursor = uuid.uuid4().hex
            if len(self._cursors) >= MAX_CURSORS:
                self._cursors.popitem(last=False)
            self._cursors[next_cursor] = (scope, end)
        actions = [{key: self._actions[action_id][key] for key in ('id', 'label', 'binding_status')}
                   for action_id in observer['actions']]
        return {'format': 'z-world-observation-study-1', 'world': self._document['world']['id'],
                'view': {'id': view['id'], 'title': view['title']}, 'observer': observer_id,
                'epoch': self.epoch(), 'clock': deepcopy(self._document['clock']),
                'entities': deepcopy(page), 'action_descriptions': actions,
                'actions_executable': False, 'next_cursor': next_cursor,
                'coverage': {'basis': 'observer records matching the requested view',
                             'total_known_matches': len(known), 'offset': offset, 'returned': len(page),
                             'has_more': end < len(known), 'all_matches_in_this_response': offset == 0 and end == len(known),
                             'world_recovery': 'not_claimed', 'fixture': 'illustrative-partial'}}


def read_document(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError('Document exceeds the study byte limit')

    def no_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=no_duplicate_keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', choices=('syndicate', 'civilization', 'colonization'))
    parser.add_argument('--view')
    parser.add_argument('--observer', default='player')
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()
    document = read_document(Path(__file__).resolve().parent / 'examples' / (args.fixture + '.json'))
    view = args.view or document['views'][0]['id']
    print(json.dumps(WorldView(document).observe(view, args.observer, args.limit), indent=2))


if __name__ == '__main__':
    main()
