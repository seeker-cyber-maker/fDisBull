"""Immutable native backing definitions and bounded UDL-to-UDC passthrough.

No UIL is inferred; relayout emits raw code, not an executable container.
"""
from copy import deepcopy
import hashlib
import json
import uuid

from .code_backings import digest, materialize_code_backing, validate_source
from .code_blocks import group_code_backings
from .code_layout import compile_code_backings
from .udc import _name, _path

FORMAT = 'fdisbull-native-code-udc-1'
MAX_SOURCE = 64 * 1024 * 1024
MAX_DOCUMENT = 4 * 1024 * 1024
DDL = (
    '''CREATE TABLE IF NOT EXISTS native_udc_sources(
       sha256 TEXT PRIMARY KEY, data BLOB NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS native_udc_definitions(
       id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
       name TEXT NOT NULL, parent TEXT REFERENCES native_udc_definitions(id),
       sha256 TEXT NOT NULL, document TEXT NOT NULL, author TEXT NOT NULL)''',
)


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('invalid native definition JSON') from exc


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _definition_digest(version, name, parent, author, document):
    return _sha(_encoded({'version': version, 'name': name, 'parent': parent,
                          'author': author, 'document': document}))


def _source_bytes(project, version):
    row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()
    if row is None or row[0] is None:
        return None
    raw = bytes(row[0])
    if not raw or len(raw) > MAX_SOURCE:
        raise ValueError('source input outside 1..64 MiB')
    if raw.startswith(b'SQLite format 3\x00'):
        raise ValueError('project databases are not native compiler sources')
    return raw


def _check_capsule_bytes(project, capsule, selected):
    source = capsule.get('source', {})
    if (source.get('version') != selected['id'] or source.get('version_sha256') != selected['sha256']
            or source.get('source_sha256') != project.meta['source_sha256']
            or source.get('arch') != project.arch or source.get('bits') != project.bits
            or project.digest(project.regions(selected['id'])) != selected['sha256']):
        raise ValueError('native definition source version differs')
    for block in capsule['blocks']:
        raw = materialize_code_backing(block)
        address = int(block['address'], 16)
        region = project._mapping(selected['id'], address)
        if region is None or region.data[address-region.start:address-region.start+len(raw)] != raw:
            raise ValueError('native backing differs from selected source bytes')


def capture_native_definition(project, name, entries, *, version=None, cs=None,
                              max_instructions=10000, split_at=None, parent=None, author='agent'):
    """Capture immutable source-backed code, with or without a complete CFG."""
    _name(name); _name(author)
    with project.transaction(True):
        selected = project.version(version)
        v = selected['id']
        capsule = project.code_backings(entries, version=v, cs=cs, max_instructions=max_instructions)
        plan = group_code_backings(capsule, split_at=split_at)
        _check_capsule_bytes(project, capsule, selected)
        raw = _source_bytes(project, v)
        original = None
        if v == 1 and raw is not None:
            if _sha(raw) != project.meta['source_sha256']:
                raise ValueError('original source digest mismatch')
            original = {'sha256': _sha(raw), 'size': len(raw), 'filename': str(_path(project.meta['filename']))}
        document = {'format': FORMAT, 'version': v, 'source_sha256': project.meta['source_sha256'],
                    'version_sha256': selected['sha256'], 'capsule': capsule, 'plan': plan,
                    'original': original,
                    'scope': 'Native backing and grouped code only; no UIL, semantic proof or native execution.'}
        encoded = _encoded(document)
        if len(encoded) > MAX_DOCUMENT:
            raise ValueError('native definition metadata exceeds 4 MiB')
        for statement in DDL:
            project.db.execute(statement)
        latest = project.db.execute('SELECT id FROM native_udc_definitions WHERE name=? ORDER BY rowid DESC LIMIT 1', (name,)).fetchone()
        if (latest is None and parent is not None) or (latest is not None and latest['id'] != parent):
            raise ValueError('native definition update requires its latest immutable parent')
        if original is not None:
            previous = project.db.execute('SELECT data FROM native_udc_sources WHERE sha256=?', (original['sha256'],)).fetchone()
            if previous is not None and bytes(previous['data']) != raw:
                raise ValueError('native source backing digest collision or corruption')
            if previous is None:
                project.db.execute('INSERT INTO native_udc_sources VALUES (?,?)', (original['sha256'], raw))
        ident = uuid.uuid4().hex
        checksum = _definition_digest(v, name, parent, author, document)
        project.db.execute('INSERT INTO native_udc_definitions VALUES (?,?,?,?,?,?,?)',
                           (ident, v, name, parent, checksum, encoded.decode(), author))
        return native_definition_info(project, ident)


def _load(project, definition):
    try:
        row = project.db.execute('SELECT * FROM native_udc_definitions WHERE id=?', (definition,)).fetchone()
    except Exception as exc:
        if 'no such table' in str(exc): raise ValueError('no native UDC definitions') from exc
        raise
    if row is None: raise ValueError('unknown native UDC definition')
    try:
        document = json.loads(row['document'])
        if (len(row['document'].encode()) > MAX_DOCUMENT or document.get('format') != FORMAT
                or document.get('version') != row['version']
                or _definition_digest(row['version'], row['name'], row['parent'], row['author'], document) != row['sha256']):
            raise ValueError('native definition integrity mismatch')
        selected = project.version(row['version'])
        if document.get('version_sha256') != selected['sha256'] or document.get('source_sha256') != project.meta['source_sha256']:
            raise ValueError('native definition source version differs')
        capsule = document['capsule']; plan = document['plan']
        if digest({k:v for k,v in capsule.items() if k != 'sha256'}) != capsule.get('sha256'):
            raise ValueError('native capsule integrity mismatch')
        _check_capsule_bytes(project, capsule, selected)
        regenerated = group_code_backings(capsule, split_at=plan['split_at'])
        if plan != regenerated:
            raise ValueError('native grouping plan integrity mismatch')
        original = document['original']
        if original is not None:
            if selected['id'] != 1 or set(original) != {'sha256','size','filename'} or original['sha256'] != project.meta['source_sha256']:
                raise ValueError('original backing identity mismatch')
            _path(original['filename'])
            stored = project.db.execute('SELECT data FROM native_udc_sources WHERE sha256=?', (original['sha256'],)).fetchone()
            binary = _source_bytes(project, 1)
            if stored is None or binary is None or bytes(stored['data']) != binary or len(binary) != original['size'] or _sha(binary) != original['sha256']:
                raise ValueError('original backing missing or corrupted')
        return row, document
    except (KeyError, TypeError, IndexError, RecursionError) as exc:
        raise ValueError('malformed native UDC definition') from exc


def _graph_status(project, document, version):
    """Freshly validate graph facts; exact bytes remain usable if facts drift."""
    try:
        check = validate_source(project, document['capsule'], version=version)
    except ValueError:
        return {'graph_complete': None, 'graph_validation': 'unverified',
                'graph_validation_reason': 'Current graph facts do not validate the captured graph.'}
    return {'graph_complete': bool(check['graph_complete'] and document['plan']['complete']),
            'graph_validation': 'verified',
            'graph_validation_scope': 'Stored graph topology and source bytes only; evidence metadata is not authenticated.'}


def native_definition_info(project, definition, *, include_blocks=False):
    """Inspect a pinned definition; default output omits retained code bytes."""
    if type(include_blocks) is not bool: raise ValueError('include_blocks must be boolean')
    with project.transaction():
        row, doc = _load(project, definition)
        cap, plan = doc['capsule'], doc['plan']
        result = {'id': row['id'], 'name': row['name'], 'parent': row['parent'], 'author': row['author'],
                  'sha256': row['sha256'], 'version': row['version'], 'format': FORMAT,
                  'source_sha256': doc['source_sha256'], 'version_sha256': doc['version_sha256'],
                  'capsule_sha256': cap['sha256'], 'plan_sha256': plan['sha256'],
                  **_graph_status(project, doc, row['version']),
                  'instruction_count': len(cap['blocks']), 'block_count': len(plan['blocks']),
                  'original_layout_available': doc['original'] is not None,
                  'qualification': 'native_backings_only', 'semantic_qualification': 'unverified',
                  'scope': doc['scope']}
        if include_blocks: result['document'] = deepcopy(doc)
        return result


def compile_native_definition(project, definition, *, mode='original-layout', assumptions=None,
                              base=0, order=None, block_order=None, entry_references=None):
    """Return exact retained source or an explicitly assumed structural code layout."""
    if mode not in ('original-layout','relayout'): raise ValueError('unknown native UDC mode')
    with project.transaction():
        row, doc = _load(project, definition)
        common = {'format': 'fdisbull-native-udc-compilation-1', 'definition': row['id'],
                  'definition_sha256': row['sha256'], 'version': row['version'],
                  'source_sha256': doc['source_sha256'], 'version_sha256': doc['version_sha256'],
                  'capsule_sha256': doc['capsule']['sha256'], 'plan_sha256': doc['plan']['sha256'],
                  'mode': mode, 'semantic_qualification': 'unverified', 'native_execution': False}
        if mode == 'original-layout':
            if assumptions is not None or type(base) is not int or base != 0 or order is not None or block_order is not None or entry_references is not None:
                raise ValueError('layout options do not apply to original-layout')
            original = doc['original']
            if original is None: raise ValueError('original-layout unavailable for this source version')
            raw = bytes(project.db.execute('SELECT data FROM native_udc_sources WHERE sha256=?', (original['sha256'],)).fetchone()['data'])
            result = {**common, 'filename': original['filename'], 'bytes': raw.hex(), 'sha256': _sha(raw),
                      'qualification': 'original_bytes_only', 'byte_identity': True,
                      'source_layout_modified': False, 'original_file_offsets_preserved': True,
                      **_graph_status(project, doc, row['version']),
                      'container_writer': False}
        else:
            if not doc['capsule']['complete'] or not doc['plan']['complete']:
                raise ValueError('relayout requires a complete graph')
            validate_source(project, doc['capsule'], version=row['version'])
            if order is not None and block_order is not None:
                raise ValueError('order and block_order are mutually exclusive')
            groups = doc['plan']['blocks']
            group_ids = [group['id'] for group in groups]
            if block_order is not None:
                if (not isinstance(block_order, list) or len(block_order) != len(group_ids)
                        or any(not isinstance(item, str) for item in block_order)
                        or len(set(block_order)) != len(block_order) or set(block_order) != set(group_ids)):
                    raise ValueError('block_order must contain every logical block exactly once')
                placement = list(block_order)
            else:
                placement = group_ids
            by_group = {group['id']: group for group in groups}
            atom_order = order if order is not None else [atom for group_id in placement for atom in by_group[group_id]['instructions']]
            layout = compile_code_backings(doc['capsule'], order=atom_order, base=base,
                                           assumptions=assumptions, entry_references=entry_references)
            occurrence = {item['node']: item for item in layout['occurrences']}
            layout['logical_blocks'] = {
                group['id']: {'entry': group['entry'],
                              'entry_address': occurrence[group['entry']]['output_address'],
                              'block_revision': group['block_revision'],
                              'source_document_sha256': doc['capsule']['sha256'],
                              'context': group['context'],
                              'instruction_occurrences': [deepcopy(occurrence[item]) for item in group['instructions']]}
                for group in groups}
            layout['placement'] = {'mode': 'atom_order' if order is not None else 'block_order',
                                   'block_order': None if order is not None else placement,
                                   'instruction_order': list(atom_order),
                                   'scope': 'Groups order their member instructions; explicit fallthrough jumps remain between instructions.'}
            layout['sha256'] = digest({k:v for k,v in layout.items() if k != 'sha256'})
            result = {**common, 'bytes': layout['bytes'], 'layout_sha256': layout['sha256'],
                      'layout': layout, 'qualification': 'structural_only', 'byte_identity': False,
                      'container_writer': False, 'original_file_offsets_preserved': False,
                      'source_layout_modified': True, 'graph_complete': True,
                      'scope': 'Explicit block or instruction placement; no generic compiler or arbitrary replacement.'}
        return deepcopy(result)
