"""Bounded assembly of supplied scene evidence; not native authentication."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import PurePosixPath
import re

_MAX_JSON = 1024 * 1024
_MAX_ARTIFACT = 16 * 1024 * 1024
_MAX_OBSERVATIONS = 1024
_MAX_INPUTS = 4096
_SHA = re.compile(r'^[0-9a-f]{64}$')


def _json(value, label):
    """Check finite, unambiguous JSON and return an isolated copy."""
    def walk(item, seen):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError('Invalid '+label)
            return
        if type(item) not in (dict, list) or id(item) in seen:
            raise ValueError('Invalid '+label)
        seen.add(id(item))
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ValueError('Invalid '+label)
            for part in item.values(): walk(part, seen)
        else:
            for part in item: walk(part, seen)
        seen.remove(id(item))
    try:
        walk(value, set())
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > _MAX_JSON:
            raise ValueError(label+' exceeds size limit')
        return deepcopy(value)
    except (RecursionError, TypeError, UnicodeError, OverflowError) as exc:
        raise ValueError('Invalid '+label) from exc


def _text(value, label):
    if type(value) is not str or not value.strip() or len(value) > 4096 or '\x00' in value:
        raise ValueError('Invalid '+label)
    return value


def _hash(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError('Invalid artifact sha256')
    return value


def _public_path(value):
    path = _text(value, 'artifact path')
    parsed = PurePosixPath(path)
    if (parsed.is_absolute() or '\\' in path or '..' in parsed.parts
            or path in ('.', '..') or '://' in path):
        raise ValueError('Public artifact path must be portable and relative')
    return path


def _count(value, label, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Invalid '+label)
    return value


def retain_evidence(operations, report):
    """Attempt every supplied retention callback and return original failures.

    Filesystem policy belongs to the callbacks. Existing primary error and
    completion fields are not changed.
    """
    if type(report) is not dict or ('persistence_errors' in report
                                    and type(report['persistence_errors']) is not list):
        raise ValueError('Invalid retention report')
    try:
        iterator = iter(operations)
    except TypeError as exc:
        raise ValueError('Invalid retention operations') from exc
    pending = []
    for operation in iterator:
        if len(pending) == _MAX_INPUTS or type(operation) not in (tuple, list) or len(operation) != 2:
            raise ValueError('Invalid retention operation')
        label, callback = operation
        _text(label, 'retention operation')
        if not callable(callback): raise ValueError('Invalid retention callback')
        pending.append((label, callback))
    failures = []
    for label, callback in pending:
        try:
            callback()
        except Exception as exc:
            failures.append(exc)
            report.setdefault('persistence_errors', []).append({'operation': label, 'error': str(exc)})
    return failures


class ReceiptAssembler:
    """Assemble supplied records with bounded checks and per-instance artifact cache.

    Hashes bind supplied bytes; they do not authenticate a source, runtime, or
    native execution. The loader owns filesystem confinement and access policy.
    """
    def __init__(self, source, runtime, artifact_loader):
        if type(source) is not dict or not source or type(runtime) is not dict or not runtime:
            raise ValueError('Source and runtime must be nonempty objects')
        if not callable(artifact_loader):
            raise ValueError('Artifact loader must be callable')
        self._source = _json(source, 'source')
        self._runtime = _json(runtime, 'runtime')
        self._loader = artifact_loader
        self._cache = {}
        self._cache_size = 0

    def artifact(self, reference, label):
        _text(label, 'artifact label')
        if type(reference) is not dict:
            raise ValueError('Invalid '+label+' artifact')
        path = _text(reference.get('path'), label+' path')
        expected = _hash(reference.get('sha256'))
        if path not in self._cache:
            try:
                raw = self._loader(path)
            except Exception as exc:
                raise ValueError('Cannot load '+label+' artifact: '+str(exc)[:1024]) from exc
            if type(raw) is not bytes or not raw or len(raw) > _MAX_ARTIFACT:
                raise ValueError('Invalid '+label+' artifact bytes')
            if self._cache_size + len(raw) > _MAX_ARTIFACT:
                raise ValueError('Artifact cache exceeds size limit')
            # Retain a successful read even on hash mismatch, avoiding a second
            # possibly different read of the same path in this snapshot.
            self._cache[path] = (raw, sha256(raw).hexdigest())
            self._cache_size += len(raw)
        raw, digest = self._cache[path]
        if digest != expected:
            raise ValueError(label+' artifact hash mismatch')
        return raw

    def frame(self, reference):
        self.artifact(reference, 'frame')
        metadata = reference.get('metadata')
        if (type(metadata) is not dict or metadata.get('source') != 'last_completed_guest_frame'
                or any(type(metadata.get(k)) is not int or metadata[k] < 0 for k in ('frame_id', 'mode_id'))
                or any(type(metadata.get(k)) is not int or metadata[k] <= 0 for k in ('width', 'height'))):
            raise ValueError('Incomplete native frame metadata')
        return {'sha256': reference['sha256'], 'metadata': _json(metadata, 'frame metadata')}

    def inputs(self, records):
        if type(records) is not list or len(records) > _MAX_INPUTS:
            raise ValueError('Invalid input records')
        result = _json(records, 'input records')
        for record in result:
            if (type(record) is not dict or type(record.get('kind')) is not str or not record['kind'].strip()
                    or record.get('delivered') is not True or record.get('complete') is not True
                    or type(record.get('delivery')) is not dict or record['delivery'].get('accepted') is not True):
                raise ValueError('Input is not completed and accepted')
        return result

    def observations(self, records, *, expected_ids, input_count=None, message_count=None, require_progress=False):
        if (type(records) is not list or len(records) > _MAX_OBSERVATIONS
                or type(expected_ids) not in (list, tuple) or not expected_ids
                or len(expected_ids) > _MAX_OBSERVATIONS or type(require_progress) is not bool):
            raise ValueError('Invalid observation arguments')
        names = [_text(item, 'expected observation id') for item in expected_ids]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate expected observation id')
        if input_count is not None: _count(input_count, 'input count', _MAX_INPUTS)
        if message_count is not None: _count(message_count, 'message count', _MAX_INPUTS)
        issues, kept, seen = [], [], set()
        record_bytes = 0
        last_frame = last_time = None
        counters = {'input_count': None, 'message_count': None}
        for index, record in enumerate(records):
            try:
                if type(record) is not dict: raise ValueError('record is not an object')
                item = _json(record, 'observation')
                record_bytes += len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                if record_bytes > _MAX_JSON:
                    issues.append({'index': index, 'reason': 'observation records exceed size limit'})
                    break
                ident = _text(item.get('id'), 'observation id')
                if ident in seen: raise ValueError('duplicate observation id')
                seen.add(ident)
                if ident not in names: raise ValueError('unexpected observation id')
                if type(item.get('state')) is not dict or not item['state']:
                    raise ValueError('missing observed state')
                frame = self.frame(item.get('frame'))
                number = frame['metadata']['frame_id']
                if last_frame is not None and number < last_frame: raise ValueError('frame id regressed')
                t = item.get('guest_ms')
                if t is not None and (type(t) not in (int, float)
                        or type(t) is float and not math.isfinite(t) or t < 0):
                    raise ValueError('invalid guest time')
                if require_progress and (t is None or last_time is not None and t <= last_time):
                    raise ValueError('guest time did not strictly increase')
                next_counts = dict(counters)
                for field, limit in (('input_count', input_count), ('message_count', message_count)):
                    value = item.get(field)
                    if value is None:
                        if limit is not None: raise ValueError('missing '+field)
                    else:
                        _count(value, field, _MAX_INPUTS)
                        if limit is not None and value > limit: raise ValueError(field+' exceeds total')
                        if counters[field] is not None and value < counters[field]: raise ValueError(field+' regressed')
                        next_counts[field] = value
                item['frame'] = frame
                kept.append(item);last_frame = number
                if t is not None: last_time = t
                counters = next_counts
            except (ValueError, TypeError, KeyError) as exc:
                issues.append({'index': index, 'reason': str(exc)})
        actual = [item['id'] for item in kept]
        missing = [name for name in names if name not in actual]
        if actual != names:
            issues.append({'reason': 'observation ids missing, extra, duplicated or out of order'})
        for field, limit in (('input_count', input_count), ('message_count', message_count)):
            if limit is not None and (not kept or counters[field] != limit):
                issues.append({'reason': 'terminal '+field+' differs from total'})
        return {'complete': not issues and not missing, 'observations': kept,
                'missing': missing, 'issues': issues}

    def receipt(self, observation_result, *, edges, artifacts=()):
        if (type(observation_result) is not dict or type(observation_result.get('complete')) is not bool
                or type(observation_result.get('observations')) is not list
                or type(observation_result.get('missing')) is not list
                or type(observation_result.get('issues')) is not list
                or type(edges) is not list or len(edges) > _MAX_OBSERVATIONS
                or type(artifacts) not in (tuple, list) or len(artifacts) > _MAX_INPUTS):
            raise ValueError('Invalid receipt arguments')
        result = _json(observation_result, 'observation result')
        copied_edges = _json(edges, 'edges')
        if any(type(edge) is not dict for edge in copied_edges):
            raise ValueError('Invalid edge')
        catalog = _json(list(artifacts), 'artifact catalog')
        bindings = {}
        paths = {}
        for item in catalog:
            if type(item) is not dict: raise ValueError('Invalid artifact catalog record')
            _text(item.get('role'), 'artifact role')
            if item.get('visibility') not in ('public', 'private'): raise ValueError('Invalid artifact visibility')
            digest = _hash(item.get('sha256'))
            if 'path' in item:
                if item['visibility'] == 'public': _public_path(item['path'])
                else: _text(item['path'], 'artifact path')
            elif item['visibility'] == 'public': raise ValueError('Public artifact requires path')
            key = (item['role'], item.get('path'))
            if bindings.setdefault(key, digest) != digest:
                raise ValueError('Artifact role and path have conflicting hashes')
            if 'path' in item and paths.setdefault(item['path'], digest) != digest:
                raise ValueError('Artifact path has conflicting hashes')
        issues = result['issues']
        if not copied_edges or any(edge.get('complete') is not True for edge in copied_edges):
            issues.append({'reason': 'one or more edges lack explicit completion'})
        positions = {}
        for index, observation in enumerate(result['observations']):
            ident = observation.get('id') if type(observation) is dict else None
            if type(ident) is not str or not ident.strip() or ident in positions:
                issues.append({'reason': 'invalid or duplicate retained observation id'})
            else:
                positions[ident] = index
        for index, edge in enumerate(copied_edges):
            before, after = edge.get('before'), edge.get('after')
            if (type(before) is not str or not before.strip() or type(after) is not str or not after.strip()
                    or before not in positions or after not in positions or positions[before] >= positions[after]):
                issues.append({'index': index, 'reason': 'edge must connect retained observations in forward order'})
        complete = (result['complete'] and bool(result['observations']) and not result['missing'] and not issues and bool(copied_edges)
                    and all(edge.get('complete') is True for edge in copied_edges))
        return {'format': 'fdisbull-scene-receipt-1', 'source': deepcopy(self._source),
                'runtime': deepcopy(self._runtime), 'complete': complete,
                'observations': result['observations'], 'missing': result['missing'],
                'issues': issues, 'edges': copied_edges, 'artifacts': catalog,
                'scope': 'Supplied records and byte hashes only; no native execution authentication.'}
