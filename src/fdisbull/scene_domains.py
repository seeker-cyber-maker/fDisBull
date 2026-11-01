"""Pure coordinate-domain layout audits, independent of navigation authority.

Every rectangle is half-open and expressed in the supplied common space.
Rendered and collision extents are independent local boxes relative to a pose.
No camera transform, live observation, expected engine behavior or safe path is
inferred. Expected-margin policies affect alerts, never the geometry facts.
"""
from copy import deepcopy
from hashlib import sha256
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


def _relationship(obj, part, domain, bounds, rules, alerts):
    pose, local = obj['pose'], obj[part]
    missing = [name for name, value in (('pose', pose), ('part', local), ('domain', bounds)) if value is None]
    absolute = ([pose[0]+local[0], pose[1]+local[1], pose[0]+local[2], pose[1]+local[3]]
                if pose is not None and local is not None else None)
    record = {'object_id': obj['id'], 'role': obj['role'], 'part': part, 'domain': domain,
              'pose': deepcopy(pose), 'local_bounds': deepcopy(local), 'absolute_bounds': absolute,
              'domain_bounds': deepcopy(bounds), 'clipped_bounds': None, 'overhang': None,
              'relation': 'unknown', 'unknown': missing, 'anomaly_candidate': None,
              'anomaly_flag': None if alerts else False, 'layout_notice': True,
              'disposition': 'unknown', 'expectation': None,
              'suppressed_by': [] if alerts else ['global_alerts_disabled']}
    if missing:
        return record
    left, top, right, bottom = absolute
    dl, dt, dr, db = bounds
    clipped = [max(left, dl), max(top, dt), min(right, dr), min(bottom, db)]
    contained = left >= dl and top >= dt and right <= dr and bottom <= db
    intersects = clipped[0] < clipped[2] and clipped[1] < clipped[3]
    relation = 'contained' if contained else 'crosses' if intersects else 'outside'
    overhang = dict(zip(_SIDES, (max(0, dl-left), max(0, dt-top), max(0, right-dr), max(0, bottom-db))))
    record.update(relation=relation, clipped_bounds=clipped if intersects else None,
                  overhang=overhang, anomaly_candidate=not contained,
                  anomaly_flag=bool(alerts and not contained), layout_notice=not contained,
                  disposition='contained' if contained else 'unexplained')
    if not contained:
        for rule in rules:
            if (obj['role'] in rule['roles'] and part in rule['parts'] and domain in rule['domains']
                    and all(overhang[side] <= rule['max_margins'][side] for side in _SIDES)):
                record['expectation'] = {key: rule[key] for key in ('id', 'mechanism', 'reason', 'evidence_status')}
                record['disposition'] = 'expected'
                record['anomaly_flag'] = False
                record['suppressed_by'].append('expectation:'+rule['id'])
                break
    return record


def audit_coordinate_domains(document, max_checks=4096):
    """Audit supplied extents algebraically, without allocating world rasters.

    Complete means all requested relationships were examined, even when inputs
    were explicitly unknown. The caller must supply any coordinate conversion;
    poses are declarations, not fresh or temporal observations. Neither an
    expected relation nor disabled alerts authorizes movement or placement.
    """
    validate_coordinate_domains(document)
    _integer(max_checks, 1, 8192)
    result = {'format': 'fdisbull-coordinate-domain-audit-1', 'complete': True,
              'descriptor_sha256': sha256(_encoded(document)).hexdigest(),
              'space': deepcopy(document['space']), 'alerts': document['alerts'],
              'examined': 0, 'total_comparisons': len(document['objects'])*len(_PARTS)*len(_DOMAINS),
              'relations': [], 'provenance': deepcopy(document['provenance']),
              'scope': 'Supplied common-space geometry only; no live observation, transform, temporal crossing, passability, reachability, teleport or native qualification.'}
    summary = {'count_scope': 'all_comparisons', 'examined': 0,
               'total_comparisons': result['total_comparisons'],
               'unexamined': result['total_comparisons'],
               'dispositions': dict.fromkeys(('contained', 'expected', 'unexplained', 'unknown'), 0),
               'anomaly_flags': dict.fromkeys(('raised', 'not_raised', 'unknown'), 0),
               'unknown_relations': 0, 'suppressed_candidates': 0, 'layout_notices': 0}
    result['summary'] = summary
    for obj in document['objects']:
        for part in _PARTS:
            for domain in _DOMAINS:
                if result['examined'] == max_checks:
                    result['complete'] = False
                    summary['count_scope'] = 'examined_only'
                    return result
                record = _relationship(obj, part, domain, document['bounds'][domain],
                                       document['expectations'], document['alerts'])
                result['relations'].append(record)
                result['examined'] += 1
                summary['examined'] += 1
                summary['unexamined'] -= 1
                summary['dispositions'][record['disposition']] += 1
                summary['anomaly_flags']['unknown' if record['anomaly_flag'] is None else
                                         'raised' if record['anomaly_flag'] else 'not_raised'] += 1
                summary['unknown_relations'] += record['relation'] == 'unknown'
                summary['suppressed_candidates'] += record['anomaly_candidate'] is True and record['anomaly_flag'] is False
                summary['layout_notices'] += record['layout_notice']
    return result
