"""Immutable, project-owned searches over qualified execution observations.

This adapter never executes a guest or infers a function. Search candidates are
reconstructed from their retained trace lineage before use. Artifact digests
detect changed records; they are not authentication for caller-supplied JSON.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from . import execution_events as kernel


MAX_BYTES = 16 * 1024 * 1024
MAX_HISTORY = 128
MAX_CAPTURE_RECEIPTS = 4096
FORMAT = 'fdisbull-event-search-artifact-1'
_BACKENDS = frozenset(('dosbox', 'dosbox-qemu', 'wine-qemu', 'ida-wine-qemu'))
_MUTABLE_MAPPING = frozenset(('execution_origin', 'checkpoint_intervention',
    'delta_experiment', 'timeline_experiment', 'qemu_pid', 'restored_from',
    'capabilities', 'window_requested', 'dot_mode'))
_STATE_FIELDS = frozenset(('format', 'registers', 'native_sha256', 'native_size',
    'storage', 'capture', 'target_paused', 'host_files_restored', 'derivation'))
_ENVELOPE_KEYS = frozenset(('format', 'owner', 'generation', 'parent', 'trace',
                            'regions', 'operation', 'state'))
_IDENTITY_KEYS = frozenset(('source_sha256', 'version_sha256', 'version', 'backend'))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum}')
    return value


def _identifier(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or any(ord(character) < 32 for character in value)):
        raise ValueError('An owned artifact identifier is required')
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid stored SHA-256 identity')
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON field in retained event evidence')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON value in retained event evidence: ' + value)


def _document(data):
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('Invalid JSON in retained event evidence') from error
    if type(value) is not dict:
        raise ValueError('Retained event evidence must be a JSON object')
    return value


def _artifact(project, identifier, kind):
    """Check the size before materializing a possibly external artifact blob."""
    _identifier(identifier)
    row = project.db.execute('''SELECT a.id,a.run,a.name,a.kind,a.sha256,a.metadata,
        fdb_length(a.data) AS size,r.version,r.metadata AS run_metadata,
        v.sha256 AS version_sha256 FROM debug_artifacts a
        JOIN debug_runs r ON r.id=a.run JOIN versions v ON v.id=r.version
        WHERE a.id=?''', (identifier,)).fetchone()
    if row is None or row['kind'] != kind:
        raise ValueError('Unknown owned ' + kind + ' artifact')
    if type(row['size']) is not int or not 0 < row['size'] <= MAX_BYTES:
        raise ValueError('Retained event artifact exceeds its 16 MiB budget')
    _digest(row['sha256'])
    data = bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                    (identifier,)).fetchone()[0])
    if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError('Retained event artifact failed its size or hash check')
    return dict(row), _document(data)


def _backend(project, metadata):
    value = metadata.get('backend')
    if value is None and project.meta['format'] in ('MZ', 'COM', 'SYS'):
        value = 'dosbox'
    if type(value) is not str or value not in _BACKENDS:
        raise ValueError('Event searches require a qualified DOS or PE trace backend')
    return value


def _mapping_identity(project, metadata):
    if type(metadata) is not dict:
        raise ValueError('Trace requires retained launch mapping metadata')
    backend = _backend(project, metadata)
    required = ('static_load_segment', 'runtime_load_segment') if backend.startswith('dosbox') else (
        'static_image_base', 'runtime_image_base')
    if any(key not in metadata for key in required):
        raise ValueError('Trace requires explicit static and runtime image mapping bases')
    result = {key: value for key, value in metadata.items()
            if key not in _MUTABLE_MAPPING and key != 'backend'} | {
                'backend': backend}
    maximum = 0xffff if backend.startswith('dosbox') else (1 << 64) - 1
    for key in required:
        value = result[key]
        if type(value) is str and re.fullmatch(r'0[xX][0-9a-fA-F]{1,17}', value):
            value = int(value, 16)
        result[key] = _integer(value, key + ' mapping base', 0, maximum)
    if 'runtime_inputs' in result:
        inputs = result['runtime_inputs']
        if type(inputs) is not dict or len(inputs) > 32:
            raise ValueError('Invalid retained backend input identities')
        normalized = {}
        for name, item in inputs.items():
            if type(item) is not dict or 'sha256' not in item:
                raise ValueError('Retained backend input lacks a content identity')
            normalized[name] = dict(sha256=_digest(item['sha256']))
        result['runtime_inputs'] = normalized
    return result


def _capture_sequence(project, row):
    """Bind historical mapping to its bounded, decoded creation receipt.

    Artifact events can be external objects. SQLite sees their storage envelope,
    not the artifact ID in the decoded document, so JSON extraction in SQL cannot
    identify this receipt. Validate count and total size before reading them.
    """
    sizes = project.db.execute('''SELECT sequence,fdb_length(evidence) AS size
        FROM debug_events WHERE run=? AND operation='artifact'
        ORDER BY sequence LIMIT ?''', (row['run'], MAX_CAPTURE_RECEIPTS + 1)).fetchall()
    if (len(sizes) > MAX_CAPTURE_RECEIPTS
            or any(type(item['size']) is not int or not 0 < item['size'] <= MAX_BYTES for item in sizes)
            or sum(item['size'] for item in sizes) > MAX_BYTES):
        raise ValueError('Historical trace creation receipts exceed the count or size budget')
    matches = []
    for item in project.db.execute('''SELECT sequence,evidence FROM debug_events
            WHERE run=? AND operation='artifact' ORDER BY sequence LIMIT ?''',
            (row['run'], MAX_CAPTURE_RECEIPTS)):
        receipt = _document(item['evidence'])
        if receipt.get('artifact') == row['id']:
            matches.append((item['sequence'], receipt))
            if len(matches) > 1:
                break
    if len(matches) != 1:
        raise ValueError('Historical trace requires its unique artifact creation receipt')
    sequence, receipt = matches[0]
    expected = dict(artifact=row['id'], run=row['run'], version=row['version'],
                    kind=row['kind'], sha256=row['sha256'], size=row['size'])
    if _json({key: receipt.get(key) for key in expected}) != _json(expected):
        raise ValueError('Historical trace differs from its artifact creation receipt')
    return sequence


def _historical_pe_mapping(project, row, captured, current, metadata):
    """An ordered successful restore can explain a changed PE process mapping.

    Offline trace comparison needs only the retained state manifest and success
    receipt; it never loads a native checkpoint or requires its machine payload.
    Every event is still checked against the immutable captured mapping below.
    """
    if current['backend'] not in ('wine-qemu', 'ida-wine-qemu'):
        return False
    changed_by_restore = {'runtime_image_base', 'target_pid'}
    if (_json({key: value for key, value in captured.items() if key not in changed_by_restore})
            != _json({key: value for key, value in current.items() if key not in changed_by_restore})):
        return False
    restored = metadata.get('restored_from')
    if type(restored) is not str or not restored:
        return False
    sequence = _capture_sequence(project, row)
    latest = project.db.execute('''SELECT sequence,fdb_length(evidence) AS size FROM debug_events
        WHERE run=? AND operation='load-state' ORDER BY sequence DESC LIMIT 1''', (row['run'],)).fetchone()
    if latest is None or latest['sequence'] <= sequence:
        return False
    if type(latest['size']) is not int or not 0 < latest['size'] <= MAX_BYTES:
        raise ValueError('Historical restore receipt exceeds its size budget')
    receipt = _document(project.db.execute('SELECT evidence FROM debug_events WHERE sequence=?',
                                          (latest['sequence'],)).fetchone()[0])
    if (receipt.get('artifact') != restored or receipt.get('state') != 'stopped'
            or receipt.get('error') is not None or receipt.get('ok') is False):
        return False
    state_row, state = _artifact(project, restored, 'state')
    if (state_row['version'] != row['version'] or receipt.get('sha256') != state_row['sha256']
            or state.get('format') != 'fdisbull-qemu-native-1'
            or type(state.get('metadata')) is not dict):
        return False
    state_mapping = {key: value for key, value in state['metadata'].items() if key not in _STATE_FIELDS}
    return _json(_mapping_identity(project, state_mapping)) == _json(current)


def _regions(mapped, supplied):
    if supplied is None:
        supplied = []
        for index, (start, end, name) in enumerate(mapped):
            identifier = f'project:{index}:{start:x}:{end:x}'
            if type(name) is not str or not name.strip() or len(name) > 256:
                name = identifier
            supplied.append(dict(id=identifier, name=name, space='project', start=start, end=end))
    return kernel.validate_regions(supplied)


def _qualify_image(compiled, mapped):
    """Caller region labels cannot establish original-image membership.

    A changed instruction can still be compared by its observed byte hash, but
    a site outside the selected image is not a cross-run source identity. A PC
    inside the image remains a valid PC even when its decoded instruction spans
    beyond the mapped bytes; only that instruction's site becomes unqualified.
    """
    for event in compiled['events']:
        address = event['pc']['project']
        if address is None:
            continue
        containing = next(((start, end) for start, end, _ in mapped if start <= address < end), None)
        if containing is None:
            event['pc']['project'] = None
            event['site'] = None
            event['source_qualification'] = 'PC is outside the selected source image'
            linear = event['pc']['linear']
            event['region'] = next((region for region in compiled['regions']
                if region['space'] == 'linear' and linear is not None
                and region['start'] <= linear < region['end']), None)
        elif event['site'] is not None and address + event['size'] > containing[1]:
            event['site'] = None
            event['source_qualification'] = 'Instruction extends beyond its mapped source region'
    compiled['unqualified_events'] = sum(event['site'] is None for event in compiled['events'])


def _trace_reference(row):
    return dict(artifact=row['id'], sha256=row['sha256'], run=row['run'], version=row['version'])


def _trace(project, identifier, *, regions=None):
    row, document = _artifact(project, identifier, 'trace')
    metadata = _document(row['run_metadata'])
    mapping = document.get('mapping')
    if type(mapping) is not dict:
        raise ValueError('Stored trace lacks its launch mapping identity')
    if (type(document.get('version')) is not int or document['version'] != row['version']
            or metadata.get('source_sha256') != project.meta['source_sha256']
            or metadata.get('version_sha256') != row['version_sha256']
            or mapping.get('source_sha256') != metadata['source_sha256']
            or mapping.get('version_sha256') != metadata['version_sha256']):
        raise ValueError('Trace source or version differs from its owning project run')
    _digest(metadata['source_sha256'])
    _digest(metadata['version_sha256'])
    captured_mapping = _mapping_identity(project, mapping)
    current_mapping = _mapping_identity(project, metadata)
    if (_json(captured_mapping) != _json(current_mapping)
            and not _historical_pe_mapping(project, row, captured_mapping, current_mapping, metadata)):
        raise ValueError('Trace mapping differs from the retained run launch identity')
    mapped = [(region.start, region.start + len(region.data), region.name)
              for region in project.regions(row['version']) if region.data]
    compiled = kernel.normalize_trace(document, regions=_regions(mapped, regions))
    expected = dict(source_sha256=metadata['source_sha256'], version_sha256=row['version_sha256'],
                    version=row['version'], backend=_backend(project, metadata))
    if (_json(compiled['identity']) != _json(expected) or compiled['run'] != row['run']):
        raise ValueError('Normalized trace identity differs from its owning run')
    _qualify_image(compiled, mapped)
    compiled['artifact'] = dict(id=row['id'], sha256=row['sha256'])
    return row, compiled


def _search_document(project, identifier):
    row, envelope = _artifact(project, identifier, 'event-search')
    if envelope.keys() != _ENVELOPE_KEYS or envelope['format'] != FORMAT:
        raise ValueError('Invalid event search envelope')
    _integer(envelope['generation'], 'search generation', 0, MAX_HISTORY - 1)
    owner = envelope['owner']
    if (type(owner) is not dict or owner.keys() != _IDENTITY_KEYS | {'run'}
            or owner['run'] != row['run'] or type(owner['version']) is not int
            or owner['version'] != row['version']
            or owner['version_sha256'] != row['version_sha256']
            or owner['source_sha256'] != project.meta['source_sha256']):
        raise ValueError('Event search differs from its owning source or run')
    _digest(owner['source_sha256'])
    _digest(owner['version_sha256'])
    _identifier(owner['run'])
    if type(owner['backend']) is not str or owner['backend'] not in _BACKENDS:
        raise ValueError('Unsupported retained event search backend')
    parent = envelope['parent']
    if parent is not None:
        if type(parent) is not dict or parent.keys() != {'artifact', 'sha256'}:
            raise ValueError('Invalid event search parent reference')
        _identifier(parent['artifact'])
        _digest(parent['sha256'])
    reference = envelope['trace']
    if type(reference) is not dict or reference.keys() != {'artifact', 'sha256', 'run', 'version'}:
        raise ValueError('Invalid event search trace reference')
    _identifier(reference['artifact'])
    _identifier(reference['run'])
    _digest(reference['sha256'])
    _integer(reference['version'], 'trace reference version', 1, (1 << 63) - 1)
    operation = envelope['operation']
    if type(operation) is not dict:
        raise ValueError('Invalid retained search operation')
    keys = {'mode', 'predicate', 'label'}
    if parent is None:
        keys |= {'feature', 'registers'}
    if (operation.keys() != keys or type(operation['mode']) is not str or operation['mode'] not in
            (('start',) if parent is None else ('retain', 'exclude'))):
        raise ValueError('Invalid retained search operation')
    normalized = kernel.validate_regions(envelope['regions'])
    if _json(normalized) != _json(envelope['regions']):
        raise ValueError('Retained search regions are not canonical')
    return row, envelope


def _operation(state, mode):
    history = state['history'][-1]
    result = dict(mode=mode, predicate=deepcopy(history['predicate']), label=history['label'])
    if mode == 'start':
        result.update(feature=state['feature'],
                      registers=deepcopy(state['registers']) if state['feature'] == 'register-value' else None)
    return result


def _load_search(project, identifier):
    """Replay a bounded lineage without retaining every large intermediate state."""
    _identifier(identifier)
    chain, visited = [], set()
    current, expected_sha = identifier, None
    while True:
        if current in visited or len(chain) >= MAX_HISTORY:
            raise ValueError('Event search lineage is cyclic or exceeds 128 trials')
        visited.add(current)
        row, envelope = _search_document(project, current)
        if expected_sha is not None and expected_sha != row['sha256']:
            raise ValueError('Event search parent artifact changed')
        chain.append(dict(artifact=current, sha256=row['sha256']))
        if envelope['parent'] is None:
            break
        current, expected_sha = envelope['parent']['artifact'], envelope['parent']['sha256']
    state, owner, regions, previous, references = None, None, None, None, []
    for generation, reference in enumerate(reversed(chain)):
        row, envelope = _search_document(project, reference['artifact'])
        if row['sha256'] != reference['sha256']:
            raise ValueError('Event search changed during lineage verification')
        if envelope['generation'] != generation or envelope['parent'] != previous:
            raise ValueError('Event search generation or parent lineage differs')
        if generation == 0:
            owner, regions = envelope['owner'], envelope['regions']
        elif _json(envelope['owner']) != _json(owner) or _json(envelope['regions']) != _json(regions):
            raise ValueError('Event search lineage changes source, owner or region identity')
        trace_row, compiled = _trace(project, envelope['trace']['artifact'], regions=regions)
        if (_trace_reference(trace_row) != envelope['trace']
                or _json(compiled['identity']) != _json({key: owner[key] for key in _IDENTITY_KEYS})):
            raise ValueError('Referenced trace changed or differs from the search identity')
        operation = envelope['operation']
        if generation == 0:
            if trace_row['run'] != owner['run']:
                raise ValueError('Initial trace and event search have different owning runs')
            state = kernel.start_search(compiled, **{key: operation[key]
                for key in ('feature', 'registers', 'predicate', 'label')})
        else:
            state = kernel.refine_search(state, compiled, **operation)
        kernel.validate_search(envelope['state'])
        if (_json(state) != _json(envelope['state'])
                or _json(_operation(state, operation['mode'])) != _json(operation)):
            raise ValueError('Retained search state differs from its verified trace lineage')
        references.append(envelope['trace'])
        previous = reference
    return row, envelope, state, references


def _save(project, envelope):
    raw = _json(envelope)
    if len(raw) > MAX_BYTES:
        raise ValueError('Event search exceeds its 16 MiB artifact budget')
    preview = kernel.search_results(envelope['state'], limit=16)
    artifact = project._debug_artifact(envelope['owner']['run'], 'event-search.json', 'event-search', raw,
        dict(format=FORMAT, generation=envelope['generation'], trace_artifact=envelope['trace']['artifact'],
             parent_search_artifact=(envelope['parent'] or {}).get('artifact')))
    return {key: value for key, value in artifact.items() if key != 'metadata'} | {
        'trace_artifact': envelope['trace']['artifact'], 'generation': envelope['generation'],
        'results': preview}


class EventSearchProjectMixin:
    """Persistent event-set narrowing; all operations work without a live guest."""

    def event_search_start(self, trace, *, feature='site', registers=None, predicate=None,
                           label='trial', regions=None):
        with self.transaction(True):
            row, compiled = _trace(self, trace, regions=regions)
            state = kernel.start_search(compiled, feature=feature, registers=registers,
                                        predicate=predicate, label=label)
            envelope = dict(format=FORMAT, owner=dict(compiled['identity'], run=row['run']), generation=0,
                parent=None, trace=_trace_reference(row), regions=compiled['regions'],
                operation=_operation(state, 'start'), state=state)
            return _save(self, envelope)

    def event_search_refine(self, search, trace, *, mode='retain', predicate=None, label='trial'):
        with self.transaction(True):
            row, previous, state, _ = _load_search(self, search)
            if previous['generation'] + 1 >= MAX_HISTORY:
                raise ValueError('Event search lineage exceeds 128 trials')
            trace_row, compiled = _trace(self, trace, regions=previous['regions'])
            if _json(compiled['identity']) != _json(state['identity']):
                raise ValueError('Cannot refine an event search across source, version or backend identities')
            state = kernel.refine_search(state, compiled, mode=mode, predicate=predicate, label=label)
            envelope = dict(format=FORMAT, owner=previous['owner'], generation=previous['generation'] + 1,
                parent=dict(artifact=search, sha256=row['sha256']), trace=_trace_reference(trace_row),
                regions=previous['regions'], operation=_operation(state, mode), state=state)
            return _save(self, envelope)

    def event_search_results(self, search, *, offset=0, limit=64):
        with self.transaction():
            _, envelope, state, references = _load_search(self, search)
            return dict(search_artifact=search, trace_artifact=envelope['trace']['artifact'],
                        owner=deepcopy(envelope['owner']), trace_references=references,
                        **kernel.search_results(state, offset=offset, limit=limit))

    def event_trace_query(self, trace, *, predicate, regions=None, offset=0, limit=64):
        _integer(offset, 'offset', 0, (1 << 63) - 1)
        _integer(limit, 'limit', 1, 256)
        checked = kernel.validate_predicate(predicate)
        with self.transaction():
            row, compiled = _trace(self, trace, regions=regions)
            matches = unknown = 0
            rows, unknown_examples = [], []
            events = compiled['events']
            initial = events[0] if events else None
            for index, event in enumerate(events):
                evaluation = kernel.evaluate_predicate(checked, event, initial=initial,
                    previous=events[index - 1] if index else None)
                if evaluation['matched'] is None:
                    unknown += 1
                    if len(unknown_examples) < 8:
                        unknown_examples.append(dict(index=event['index'], unknown=evaluation['unknown']))
                elif evaluation['matched'] is True:
                    if offset <= matches < offset + limit:
                        rows.append(dict(deepcopy(event), trace_artifact=trace,
                                         evaluation=evaluation))
                    matches += 1
            return dict(trace_artifact=trace, trace_sha256=row['sha256'], run=row['run'],
                identity=compiled['identity'], predicate=checked, regions=compiled['regions'],
                window=compiled['window'], complete=compiled['window']['closed'],
                scanned_events=len(compiled['events']), matched_count=matches,
                unknown_count=unknown, unmatched_count=len(compiled['events']) - matches - unknown,
                unknown_examples=unknown_examples, offset=offset, limit=limit, rows=rows,
                next_offset=offset + len(rows) if offset + len(rows) < matches else None,
                scope='Retrospective observations only; no claim the live target stopped at a returned match')
