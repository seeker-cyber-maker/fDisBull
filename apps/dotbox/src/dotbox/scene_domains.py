"""Pure coordinate-domain layout audits, independent of navigation authority.

Every rectangle is half-open and expressed in the supplied common space.
Rendered and collision extents are independent local boxes relative to a pose.
No camera transform, live observation, expected engine behavior or safe path is
inferred. Expected-margin policies affect alerts, never the geometry facts.
"""

# First-party extraction from fDisBull 0.34.1: fdisbull/scene_domains.py
# Original file SHA-256: b37200848be4f2ccaeadb984780e5d33ce3d69c7b8ba16f0743ebd02f02736ca
# Retained optional descriptor validation only; layout auditing omitted.

import json


_DOMAINS = ('world', 'room', 'collision', 'viewport')
_PARTS = ('render', 'collision')
_SIDES = ('left', 'top', 'right', 'bottom')
_MIN, _MAX = -(1 << 31), (1 << 31)-1
_LIMIT = 1024*1024


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError('Invalid coordinate-domain fields')


def _integer(value, minimum=_MIN, maximum=_MAX):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid coordinate-domain integer')


def _text(value, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('Invalid coordinate-domain text')


def _rectangle(value):
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('Expected half-open rectangle or null')
    for coordinate in value:
        _integer(coordinate)
    if value[0] >= value[2] or value[1] >= value[3]:
        raise ValueError('Known rectangles must have positive extent')


def _names(value, allowed=None, maximum=128):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError('Invalid coordinate-domain scope list')
    for name in value:
        _text(name)
        if allowed is not None and name not in allowed:
            raise ValueError('Unknown coordinate-domain scope')
    if len(set(value)) != len(value):
        raise ValueError('Duplicate coordinate-domain scope')


def _encoded(document):
    try:
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError('Coordinate domains require finite JSON') from error
    if len(encoded) > _LIMIT:
        raise ValueError('Coordinate-domain descriptor exceeds one MiB')
    return encoded


def validate_coordinate_domains(document):
    """Validate the entire bounded descriptor without modifying it.

    Bounds/parts are nonempty signed-int32 rectangles or null (unknown).
    Domain names refer to distinct bounds in one explicitly declared space;
    naming a space or expectation is a declaration, not evidence of accuracy.
    """
    _encoded(document)
    _fields(document, ('format', 'space', 'bounds', 'objects', 'expectations', 'alerts', 'provenance'))
    if document['format'] != 'fdisbull-coordinate-domains-1' or type(document['alerts']) is not bool:
        raise ValueError('Invalid coordinate-domain format or alerts switch')
    _fields(document['space'], ('name', 'unit'))
    for value in document['space'].values():
        _text(value)
    _fields(document['bounds'], _DOMAINS)
    for rectangle in document['bounds'].values():
        _rectangle(rectangle)
    objects = document['objects']
    if not isinstance(objects, list) or len(objects) > 1024:
        raise ValueError('Coordinate domains require at most 1024 objects')
    ids = set()
    for obj in objects:
        _fields(obj, ('id', 'role', 'pose', 'render', 'collision'))
        _text(obj['id']); _text(obj['role'])
        if obj['id'] in ids:
            raise ValueError('Duplicate coordinate-domain object')
        ids.add(obj['id'])
        pose = obj['pose']
        if pose is not None:
            if not isinstance(pose, list) or len(pose) != 2:
                raise ValueError('Object pose requires x,y or null')
            for value in pose:
                _integer(value)
        for part in _PARTS:
            _rectangle(obj[part])
    expectations = document['expectations']
    if not isinstance(expectations, list) or len(expectations) > 128:
        raise ValueError('Coordinate domains require at most 128 expectations')
    ids = set()
    for rule in expectations:
        _fields(rule, ('id', 'mechanism', 'roles', 'domains', 'parts', 'max_margins', 'reason', 'evidence_status'))
        for key in ('id', 'mechanism', 'evidence_status'):
            _text(rule[key])
        _text(rule['reason'], 1024)
        if rule['id'] in ids:
            raise ValueError('Duplicate coordinate-domain expectation')
        ids.add(rule['id'])
        _names(rule['roles'])
        _names(rule['domains'], _DOMAINS, 4)
        _names(rule['parts'], _PARTS, 2)
        _fields(rule['max_margins'], _SIDES)
        for value in rule['max_margins'].values():
            _integer(value, 0)
    provenance = document['provenance']
    if (not isinstance(provenance, dict) or not provenance
            or any(not isinstance(key, str) or not key.strip() for key in provenance)):
        raise ValueError('Coordinate domains require declared provenance')
    return document
