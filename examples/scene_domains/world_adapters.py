"""Adapt the committed Syndicate/Civ JSON profiles into coordinate domains.

The profile definitions were inspected at 121ce8274ebdb731349d0577f850959f8affb412.
No original assets, action code, camera transforms or collision rules are used.
Hashes bind supplied documents; they do not authenticate the claimed observation.
"""
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from fdisbull.scene_domains import validate_coordinate_domains


DEFINITION_COMMIT = '121ce8274ebdb731349d0577f850959f8affb412'
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_OBJECTS = 1024
_ROUTE_STATUSES = {'candidate_requires_validation', 'unresolved_elevation_connector',
                   'no_candidate_approach', 'no_candidate_route'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, low=0, high=65535):
    _require(type(value) is int and low <= value <= high, 'Invalid world integer')
    return value


def _text(value):
    _require(type(value) is str and bool(value.strip()) and len(value) <= 128,
             'Invalid world identity or role')
    return value


def _hash(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
             'Missing or invalid supplied state/source hash')
    return value


def _json(value, limit=MAX_INPUT_BYTES):
    """Preflight work/depth/string/byte caps before allocating canonical JSON."""
    nodes, size = 0, 0

    def visit(item, depth):
        nonlocal nodes, size
        nodes += 1
        _require(nodes <= 400000 and depth <= 16, 'World JSON work/depth limit exceeded')
        kind = type(item)
        if kind is dict:
            _require(len(item) <= 4096, 'World JSON dictionary limit exceeded')
            size += 2 + max(0, len(item)-1)
            for key, child in item.items():
                _require(type(key) is str and len(key) <= 256, 'Invalid world JSON key')
                size += len(json.dumps(key, ensure_ascii=False).encode()) + 1
                visit(child, depth+1)
        elif kind is list:
            _require(len(item) <= 400000, 'World JSON array limit exceeded')
            size += 2 + max(0, len(item)-1)
            for child in item:
                visit(child, depth+1)
        else:
            _require(kind in (str, int, float, bool, type(None)), 'World input must be JSON')
            if kind is str:
                _require(len(item) <= 4096, 'World JSON string limit exceeded')
            if kind is int:
                _require(-(1 << 63) <= item < (1 << 63), 'World JSON integer limit exceeded')
            if kind is float:
                _require(math.isfinite(item), 'World JSON requires finite numbers')
            size += len(json.dumps(item, ensure_ascii=False, allow_nan=False).encode())
        _require(size <= limit, 'World JSON byte limit exceeded')

    visit(value, 0)
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def _document(value):
    _require(type(value) is dict, 'Expected world JSON object')
    return sha256(_json(value)).hexdigest()


def load_world_json(path):
    """Read at most four MiB from one ordinary JSON file; never write output."""
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), 'Expected ordinary world JSON file')
    with path.open('rb') as stream:
        raw = stream.read(MAX_INPUT_BYTES+1)
    _require(len(raw) <= MAX_INPUT_BYTES, 'World JSON byte limit exceeded')

    def pairs(entries):
        result = {}
        for key, value in entries:
            _require(key not in result, 'Duplicate world JSON key')
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('Invalid bounded world JSON') from error
    _document(value)
    return value


def _raw_position(value):
    _require(type(value) is list and len(value) == 3, 'Expected exact raw XYZ')
    return [_integer(v) for v in value]


def _finish(objects, world, space, provenance, alerts):
    _require(type(alerts) is bool, 'Alerts must be boolean')
    result = {'format': 'fdisbull-coordinate-domains-1', 'space': space,
              'bounds': {'world': world, 'room': None, 'collision': None, 'viewport': None},
              'objects': objects, 'expectations': [], 'alerts': alerts, 'provenance': provenance}
    _json(result, MAX_OUTPUT_BYTES)
    return validate_coordinate_domains(result)


def _syndicate(scene, map_model):
    fingerprint = _document(scene)
    _require(scene.get('schema') == 'syndicate-diagnostic-scene-research-1',
             'Unsupported Syndicate schema')
    coordinates = scene.get('coordinates')
    _require(type(coordinates) is dict and coordinates == {'x_y_units_per_tile': 256,
             'z_units_per_level': 128, 'screen_coordinates': False}
             and type(coordinates['x_y_units_per_tile']) is int
             and type(coordinates['z_units_per_level']) is int
             and coordinates['screen_coordinates'] is False, 'Unsupported Syndicate units')
    state_hash = _hash(scene.get('source_state_sha256'))
    map_number = _integer(scene.get('map_number'))
    entities = scene.get('entities')
    _require(type(entities) is list and len(entities) <= MAX_OBJECTS, 'Syndicate object limit exceeded')
    ids = set()
    for entity in entities:
        _require(type(entity) is dict, 'Invalid Syndicate entity')
        ident = _text(entity.get('id'))
        _require(ident not in ids, 'Duplicate Syndicate source identity')
        ids.add(ident)
        _raw_position(entity.get('position_raw'))
    _require(scene.get('selected') in ids, 'Selected Syndicate entity absent')
    world, dimensions, model_hash, sources = None, None, None, None
    if map_model is not None:
        model_hash = _document(map_model)
        bound_scene = map_model.get('scene')
        _require(type(bound_scene) is dict and bound_scene.get('source_state_sha256') == state_hash
                 and _integer(map_model.get('map_number')) == map_number
                 and _integer(bound_scene.get('map_number')) == map_number, 'Map model belongs to another scene')
        dimensions = map_model.get('dimensions')
        _require(type(dimensions) is list and len(dimensions) == 3, 'Missing map-model dimensions')
        dimensions = [_integer(dimensions[0], 1, 128), _integer(dimensions[1], 1, 128),
                      _integer(dimensions[2], 2, 32)]
        hashes = map_model.get('source_hashes')
        _require(type(hashes) is dict, 'Missing map-model source hashes')
        sources = {key: _hash(hashes.get(key)) for key in ('map', 'classes')}
        world = [0, 0, dimensions[0]*256, dimensions[1]*256]
    return fingerprint, state_hash, map_number, entities, world, dimensions, model_hash, sources


def syndicate_domains(scene, *, map_model=None, alerts=True):
    """Project raw XY; preserve each raw Z without merging floors or inventing boxes.

    The summary has no dimensions. World bounds require its matching semantic
    map-model, whose source hashes and dimensions are retained as supplied facts.
    """
    fingerprint, state_hash, number, entities, world, dimensions, model_hash, sources = _syndicate(scene, map_model)
    objects, bindings, seen = [], {}, set()
    for entity in entities:
        _require(type(entity) is dict, 'Invalid Syndicate entity')
        ident, role = _text(entity.get('id')), _text(entity.get('category'))
        _require(ident not in seen, 'Duplicate Syndicate source identity')
        seen.add(ident)
        xyz = _raw_position(entity.get('position_raw'))
        if 'position' in entity:
            position = entity['position']
            _require(type(position) is list and len(position) == 3 and all(
                type(v) in (int, float) and v == xyz[i]/(128 if i == 2 else 256)
                for i, v in enumerate(position)), 'Raw/display Syndicate coordinates disagree')
        objects.append({'id': ident, 'role': role, 'pose': xyz[:2], 'render': None, 'collision': None})
        bindings[ident] = {'source_id': ident, 'position_raw': xyz, 'z_raw': xyz[2],
                           'z_units_per_level': 128, 'elevation_layer': xyz[2]//128,
                           'elevation_remainder_raw': xyz[2]%128}
    _require(scene.get('selected') in seen, 'Selected Syndicate entity absent')
    provenance = {'definition_commit': DEFINITION_COMMIT, 'source_schema': scene['schema'],
        'input_canonical_sha256': fingerprint, 'supplied_source_state_sha256': state_hash,
        'map_number': number, 'map_model_canonical_sha256': model_hash,
        'map_dimensions': dimensions, 'supplied_map_source_hashes': sources,
        'selected_source_id': scene['selected'], 'object_bindings': bindings,
        'scope': 'Supplied raw XY metadata; elevation remains per identity. No projected floor overlap, camera, render/collision footprint, terrain safety, reachability or execution is established.'}
    return _finish(objects, world, {'name': 'syndicate-map-'+str(number)+'-raw-xy',
                   'unit': '1/256 tile'}, provenance, alerts)


def civilization_domains(world, *, alerts=True):
    """Adapt civ-world-0 tile points and stable record keys, without gameplay rules."""
    fingerprint = _document(world)
    _require(world.get('format') == 'civ-world-0' and world.get('dimensions') == [80, 50]
             and all(type(v) is int for v in world['dimensions']), 'Unsupported Civilization world')
    state_hash = _hash(world.get('source_state_sha256'))
    source = world.get('source')
    _require(type(source) is dict, 'Missing Civilization source identity')
    identity = {key: _hash(source.get(key)) for key in ('sve_sha256', 'map_sha256', 'map_file_sha256')}
    identity['edition'] = _text(source.get('edition'))
    collections = [world.get(key) for key in ('cities', 'units', 'resources')]
    _require(all(type(items) is list for items in collections) and sum(map(len, collections)) <= MAX_OBJECTS,
             'Civilization object limit exceeded or inventory missing')
    objects, bindings, seen = [], {}, set()
    for role, items in zip(('city', 'unit', 'resource'), collections):
        for item in items:
            _require(type(item) is dict, 'Invalid Civilization object')
            xy = [_integer(item.get('x'), 0, 79), _integer(item.get('y'), 0, 49)]
            if role == 'city':
                key = [_integer(item.get('index'), 0, 127)]
            elif role == 'unit':
                key = [_integer(item.get('civ'), 0, 7), _integer(item.get('slot'), 0, 127)]
            else:
                key = xy
            ident = role+'-'+'-'.join(map(str, key))
            _require(ident not in seen, 'Duplicate Civilization source record key')
            seen.add(ident)
            objects.append({'id': ident, 'role': role, 'pose': xy, 'render': None, 'collision': None})
            bindings[ident] = {'source_collection': role+'s' if role != 'city' else 'cities',
                               'source_key': key, 'id_kind': 'derived_from_source_record_key',
                               'elevation': None}
    return _finish(objects, [0, 0, 80, 50], {'name': 'civilization-world-tiles', 'unit': 'tile'},
        {'definition_commit': DEFINITION_COMMIT, 'source_schema': 'civ-world-0',
         'input_canonical_sha256': fingerprint, 'supplied_source_state_sha256': state_hash,
         'supplied_source_identity': identity, 'object_bindings': bindings,
         'scope': 'Saved tile census only. Elevation, camera, render/collision bounds, unit movement rules, terrain safety and teleport execution are unknown.'}, alerts)


def syndicate_destination_inventory(map_model, *, candidate_routes=None):
    """Inventory declared anchors/route proposals; never execute or certify them."""
    _require(type(map_model) is dict, 'Expected map-model JSON object')
    scene = map_model.get('scene')
    _, state_hash, number, entities, _, _, model_hash, _ = _syndicate(scene, map_model)
    positions = {entity['id']: entity['position_raw'] for entity in entities}
    anchors = map_model.get('waypoints')
    routes = [] if candidate_routes is None else candidate_routes
    _require(type(anchors) is list and type(routes) is list and len(anchors)+len(routes) <= 256,
             'Destination inventory limit exceeded or anchors missing')
    routes_hash = sha256(_json(routes)).hexdigest()
    destinations, seen = [], set()
    for anchor in anchors:
        _require(type(anchor) is dict, 'Invalid declared anchor')
        name, position = _text(anchor.get('name')), anchor.get('position')
        _require(type(position) is list and len(position) == 3, 'Missing anchor XYZ')
        raw = []
        for value, scale in zip(position, (256, 256, 128)):
            _require(type(value) in (int, float) and math.isfinite(value), 'Invalid anchor coordinate')
            scaled = value*scale
            _require(scaled == int(scaled), 'Anchor cannot be represented exactly in raw units')
            raw.append(_integer(int(scaled)))
        ident = 'waypoint-'+name.replace(' ', '-')
        destinations.append({'id': ident, 'source_id': name, 'source_kind': 'map-model-waypoint',
            'position_raw': raw, 'status': 'declared_diagnostic_anchor',
            'safety': 'unknown', 'execution': 'unknown'})
    for index, route in enumerate(routes):
        _require(type(route) is dict and route.get('format') == 'syndicate-candidate-route-1'
                 and route.get('source_state_sha256') == state_hash
                 and _integer(route.get('map_number')) == number
                 and route.get('status') in _ROUTE_STATUSES
                 and route.get('qualification') == 'conditional_model_only', 'Unbound candidate route')
        actor, target = _text(route.get('actor_id')), _text(route.get('target_id'))
        _require(actor in positions and target in positions and actor != target
                 and _raw_position(route.get('start_raw')) == positions[actor]
                 and _raw_position(route.get('target_raw')) == positions[target],
                 'Candidate route entity/position differs from supplied scene')
        ident = route.get('plan_id')
        if ident is not None:
            ident = _hash(ident)
        position = route.get('approach_raw')
        if route['status'] == 'candidate_requires_validation':
            position = _raw_position(position)
        else:
            _require(position is None, 'Failed route must not declare a destination')
        destinations.append({'id': 'plan-'+ident if ident else 'route-'+str(index),
            'source_id': ident, 'source_kind': 'candidate-route',
            'actor_id': actor, 'target_id': target,
            'position_raw': position, 'target_position_raw': _raw_position(route.get('target_raw')),
            'status': route['status'], 'safety': 'unknown', 'execution': 'unknown'})
    for item in destinations:
        _require(item['id'] not in seen, 'Duplicate destination identity')
        seen.add(item['id'])
    result = {'format': 'fdisbull-scene-destination-inventory-1',
        'coordinates': {'x_y_units_per_tile': 256, 'z_units_per_level': 128},
        'destinations': destinations, 'provenance': {'definition_commit': DEFINITION_COMMIT,
            'supplied_source_state_sha256': state_hash, 'map_number': number,
            'map_model_canonical_sha256': model_hash,
            'candidate_routes_canonical_sha256': routes_hash,
            'scope': 'Definitions and conditional proposals only. Historical exercise is not encoded in map-model anchors; no safe/qualified teleport or execution authority is inferred.'}}
    _json(result, MAX_OUTPUT_BYTES)
    return result
