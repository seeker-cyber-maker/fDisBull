"""Original-backed DOS block compilation; no implicit native execution.

This first UDC reconstructs an unchanged image from immutable block backings.
Only explicitly lifted register blocks make semantic claims. Unmapped bytes
remain original dependencies, not invented UIL operations. Generated DOS
lowering, relocation and edits to an unsupported block are outside this target.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import uuid

from .interaction_il import change_role, validate_il
from .udl_blocks import verify_block

FORMAT = 'fdisbull-original-dos-udc-1'
MAX_BYTES = 64 * 1024 * 1024
CHUNK = 65536
DDL = '''
CREATE TABLE IF NOT EXISTS udc_definitions(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 name TEXT NOT NULL, parent TEXT REFERENCES udc_definitions(id),
 sha256 TEXT NOT NULL, document TEXT NOT NULL, author TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS udc_blocks(
 definition TEXT NOT NULL REFERENCES udc_definitions(id),
 artifact TEXT NOT NULL, block TEXT NOT NULL, data BLOB NOT NULL,
 PRIMARY KEY(definition,artifact,block));
'''


class UDCQualificationError(ValueError):
    def __init__(self, message, verification):
        super().__init__(message)
        self.verification = verification


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _path(value):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('invalid artifact path')
    p = PurePosixPath(value)
    devices = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1,10)}
    if (p.is_absolute() or PureWindowsPath(value).drive or ':' in value or
            any(c in value for c in '<>"|?*') or
            any(part in ('', '.', '..', '.git') or part.endswith(('.', ' ')) or part.split('.')[0].upper() in devices for part in value.split('/'))):
        raise ValueError('artifact paths must be local, canonical relative paths')
    lower = value.lower()
    if (lower.endswith(('.fdb', '.db', '.sqlite', '.sqlite3', '.sav', '.state', '.mig.gz',
                         '.fdb-wal', '.fdb-shm', '.db-wal', '.db-shm', '.sqlite-wal', '.sqlite-shm'))
            or p.name.lower().startswith('dinosg.')):
        raise ValueError('project databases and saved states are not compiler resources')
    return p


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.strip():
        raise ValueError('definition requires a name and author')
    return value


def _semantic_digest(program):
    """Role and evidence do not turn identical blocks into different behavior."""
    validate_il(program)
    def strip(value):
        if isinstance(value, list): return [strip(v) for v in value]
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ('id', 'evidence', 'role')}
        return value
    # Variable names remain actual v1 state keys, not interchangeable aliases.
    return _sha(_encoded(strip(program)))


def _qualify(lift, program):
    validate_il(program)
    result = verify_block(lift, change_role(program, 'uil'))
    if result['status'] != 'equivalent_under_assumptions':
        raise UDCQualificationError('block equivalence was not established', result)
    return result


def _definition_digest(version, name, parent, author, document):
    return _sha(_encoded({'version': version, 'name': name, 'parent': parent,
                          'author': author, 'document': document}))


def capture_dos_definition(project, name, *, resources=None, semantic_blocks=None,
                           version=1, parent=None, author='agent', main_name=None):
    """Capture immutable original bytes and optional source-qualified block IL.

    ``semantic_blocks`` contains {id, offset, lift} records for primary-file
    spans. Resources map output paths to immutable attached-file names. There
    is no reading from arbitrary paths or execution of definitions in evidence.
    The initial target deliberately accepts original static version 1 only.
    """
    _name(name); _name(author)
    v = project.version(version)
    if v['id'] != 1 or project.meta['format'] not in ('MZ', 'COM') or project.arch != 'x86' or project.bits != 16:
        raise ValueError('first DOS UDC requires original static x86-16 MZ/COM version 1')
    if project.digest(project.regions(1)) != v['sha256']:
        raise ValueError('stored image version digest mismatch')
    row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()
    if row is None or row[0] is None:
        raise ValueError('original file bytes are unavailable')
    raw = bytes(row[0])
    if _sha(raw) != project.meta['source_sha256']:
        raise ValueError('original file digest mismatch')
    primary = str(_path(project.meta['filename'] if main_name is None else main_name))
    if primary.casefold() == 'udc-manifest.json':
        raise ValueError('reserved compiler manifest path')
    if resources is None: resources = {}
    if not isinstance(resources, dict) or len(resources) > 255:
        raise ValueError('resources must be an explicit path-to-attached-file mapping')
    sources = {primary: raw}
    for path, attached in resources.items():
        path = str(_path(path))
        if path.casefold() in {p.casefold() for p in sources} or path.casefold() == 'udc-manifest.json':
            raise ValueError('duplicate or reserved output path')
        info = project._external_file(1, attached)
        _path(info['filename'])
        if info['kind'].lower() in ('state', 'checkpoint', 'database', 'project'):
            raise ValueError('saved states and project databases are not compiler resources')
        data = bytes(project.db.execute('SELECT data FROM external_files WHERE version=1 AND name=?', (attached,)).fetchone()[0])
        if data.startswith(b'SQLite format 3\x00'):
            raise ValueError('SQLite databases are not compiler resources')
        if _sha(data) != info['sha256']:
            raise ValueError('attached resource digest mismatch')
        sources[path] = data
    if not raw or sum(map(len, sources.values())) > MAX_BYTES:
        raise ValueError('compiler inputs exceed 64 MiB')
    # Reject file/directory collisions before writing any output.
    paths = [PurePosixPath(p.casefold()) for p in sources]
    if any(a != b and a in b.parents for a in paths for b in paths):
        raise ValueError('artifact path collision')
    semantic_blocks = [] if semantic_blocks is None else semantic_blocks
    if not isinstance(semantic_blocks, list) or len(semantic_blocks) > 256:
        raise ValueError('too many semantic blocks')
    selected, ids = [], set()
    for entry in semantic_blocks:
        if not isinstance(entry, dict) or set(entry) != {'id', 'offset', 'lift'}:
            raise ValueError('semantic block requires id, offset and lift')
        ident, offset, lift = entry['id'], entry['offset'], entry['lift']
        _name(ident)
        if ident in ids or type(offset) is not int or offset < 0 or not isinstance(lift, dict) or lift.get('source_kind') != 'asm16':
            raise ValueError('invalid or duplicate source block')
        ids.add(ident)
        code = bytes.fromhex(lift['source'])
        if not code or raw[offset:offset + len(code)] != code:
            raise ValueError('lift does not match its original file span')
        loader = project.meta['loader_metadata']
        if not any(m['file_offset'] <= offset and offset + len(code) <= m['file_offset'] + m['file_size']
                   for m in loader.get('file_mappings', [])):
            raise ValueError('semantic block is outside the file-backed DOS load module')
        if any(offset < relocation['file_offset'] + 2 and relocation['file_offset'] < offset + len(code)
               for relocation in loader.get('dos', {}).get('relocations', [])):
            raise ValueError('semantic blocks overlapping DOS relocations require a relocated model')
        proof = _qualify(lift, lift['uil'])
        selected.append((offset, offset + len(code), ident, deepcopy(lift), proof))
    selected.sort(key=lambda b: b[0])
    if any(a[1] > b[0] for a, b in zip(selected, selected[1:])):
        raise ValueError('semantic source blocks overlap')
    document = {'format': FORMAT, 'target': 'original-dos', 'primary': primary,
                'version': 1, 'version_sha256': v['sha256'], 'source_sha256': _sha(raw),
                'profile': {'arch': 'x86', 'bits': 16, 'container': project.meta['format'],
                            'entry': project.meta['entry'], 'layout': 'original file layout'},
                'artifacts': [], 'semantic_blocks': {},
                'scope': 'unchanged original-backed file reconstruction; opaque regions retain original dependencies'}
    payloads = []
    for path, data in sources.items():
        artifact = {'path': path, 'size': len(data), 'sha256': _sha(data), 'blocks': []}
        ranges = selected if path == primary else []
        cursor = 0
        def add(start, end, ident, kind):
            blob = data[start:end]
            artifact['blocks'].append({'id': ident, 'offset': start, 'size': len(blob), 'sha256': _sha(blob), 'kind': kind})
            payloads.append((path, ident, blob))
        def gaps(end):
            nonlocal cursor
            while cursor < end:
                stop = min(cursor + CHUNK, end)
                add(cursor, stop, 'original-' + format(cursor, 'x'), 'original')
                cursor = stop
        for start, end, ident, lift, proof in ranges:
            gaps(start)
            # Namespace semantic IDs separately from automatically retained bytes.
            add(start, end, 'semantic-' + ident, 'asm16')
            document['semantic_blocks'][ident] = {'artifact': path, 'offset': start,
                'backing': 'semantic-' + ident, 'lift': lift,
                'udl': change_role(lift['uil'], 'udl'),
                'contract_sha256': _semantic_digest(lift['uil']), 'verification': proof}
            cursor = end
        gaps(len(data))
        document['artifacts'].append(artifact)
    encoded = _encoded(document)
    if len(encoded) > 4 * 1024 * 1024:
        raise ValueError('definition metadata exceeds 4 MiB')
    with project.transaction(True):
        for statement in DDL.split(';'):
            if statement.strip(): project.db.execute(statement)
        previous = project.db.execute('SELECT * FROM udc_definitions WHERE version=1 AND name=? ORDER BY rowid DESC LIMIT 1', (name,)).fetchone()
        if (previous is None and parent is not None) or (previous is not None and parent != previous['id']):
            raise ValueError('definition update requires its current immutable parent')
        if previous is not None and previous['document'] == encoded.decode() and previous['author'] == author:
            return definition_info(project, previous['id'])
        digest = _definition_digest(1, name, parent, author, document)
        ident = uuid.uuid4().hex
        project.db.execute('INSERT INTO udc_definitions VALUES (?,?,?,?,?,?,?)', (ident, 1, name, parent, digest, encoded.decode(), author))
        project.db.executemany('INSERT INTO udc_blocks VALUES (?,?,?,?)', ((ident, path, block, blob) for path, block, blob in payloads))
    return definition_info(project, ident)


def _load(project, definition):
    try:
        row = project.db.execute('SELECT * FROM udc_definitions WHERE id=?', (definition,)).fetchone()
    except Exception as error:
        if 'no such table' in str(error): raise ValueError('no UDC definitions') from error
        raise
    if row is None: raise ValueError('unknown UDC definition')
    doc = json.loads(row['document'])
    if (_definition_digest(row['version'], row['name'], row['parent'], row['author'], doc) != row['sha256']
            or doc.get('format') != FORMAT or doc.get('version') != row['version'] or row['version'] != 1):
        raise ValueError('definition integrity mismatch')
    if project.version(1)['sha256'] != doc['version_sha256'] or project.digest(project.regions(1)) != doc['version_sha256']:
        raise ValueError('source image version differs')
    return row, doc


def definition_info(project, definition, *, include_blocks=False):
    row, doc = _load(project, definition)
    result = {'id': row['id'], 'name': row['name'], 'parent': row['parent'], 'author': row['author'],
              'sha256': row['sha256'], 'version': row['version'], 'format': FORMAT,
              'primary': doc['primary'], 'profile': doc['profile'],
              'artifacts': [{k: a[k] for k in ('path', 'size', 'sha256')} for a in doc['artifacts']],
              'block_count': sum(len(a['blocks']) for a in doc['artifacts']),
              'semantic_block_count': len(doc['semantic_blocks']), 'scope': doc['scope']}
    if include_blocks: result['document'] = deepcopy(doc)
    return result


def shared_programs(project, definition, *, role='uil'):
    """UDL and UIL retain the same shared nodes, source and operand bindings."""
    _, doc = _load(project, definition)
    return {name: change_role(block['udl'], role) for name, block in doc['semantic_blocks'].items()}


def compile_dos(project, definition, output_dir, *, programs=None):
    """Reconstruct private DOS artifacts from checked per-block native backings.

    A changed UIL candidate needs a successful Z3 check for the declared pure
    register boundary. Missing proof or unsupported semantics never silently
    becomes the original implementation. Compilation does not execute a guest.
    """
    row, doc = _load(project, definition)
    programs = shared_programs(project, definition) if programs is None else programs
    if not isinstance(programs, dict) or set(programs) != set(doc['semantic_blocks']):
        raise ValueError('every mapped block requires exactly one UIL program')
    proofs = {}
    for name, block in doc['semantic_blocks'].items():
        program = programs[name]
        if not isinstance(program, dict) or program.get('role') != 'uil': raise ValueError('compiler input must use the shared UIL role')
        # Recheck even unchanged candidates: a persisted old receipt cannot
        # silently supply a missing solver or authorize different inputs.
        proofs[name] = _qualify(block['lift'], program)
    target = Path(output_dir).resolve()
    if target.exists() or any((p / '.git').exists() for p in (target, *target.parents)):
        raise ValueError('compiler output must be new and outside Git')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic reservation prevents replacing even an empty directory created
    # between preflight and writing. The final manifest marks completion.
    target.mkdir(mode=0o700, exist_ok=False)
    temp = target
    owned = target.stat()
    artifacts = []
    try:
        for artifact in doc['artifacts']:
            path = _path(artifact['path']); dest = temp.joinpath(*path.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            cursor, digest = 0, hashlib.sha256()
            with dest.open('xb') as out:
                for block in artifact['blocks']:
                    if block['offset'] != cursor or type(block['size']) is not int or block['size'] <= 0:
                        raise ValueError('block layout is incomplete or overlapping')
                    payload = project.db.execute('SELECT data FROM udc_blocks WHERE definition=? AND artifact=? AND block=?', (definition, artifact['path'], block['id'])).fetchone()
                    if payload is None: raise ValueError('missing original block backing')
                    data = bytes(payload[0])
                    if len(data) != block['size'] or _sha(data) != block['sha256']:
                        raise ValueError('original block backing integrity mismatch')
                    out.write(data); digest.update(data); cursor += len(data)
                out.flush(); os.fsync(out.fileno())
            if cursor != artifact['size'] or digest.hexdigest() != artifact['sha256']:
                raise ValueError('compiled artifact differs from its original identity')
            os.chmod(dest, 0o600)
            artifacts.append({'path': artifact['path'], 'size': cursor, 'sha256': digest.hexdigest()})
        receipt = {'format': 'fdisbull-udc-compilation-1', 'definition': definition,
                   'definition_sha256': row['sha256'], 'target': 'original-dos',
                   'primary': doc['primary'], 'artifacts': artifacts,
                   'qualification': {'byte_identity': True, 'semantic_blocks': len(proofs),
                       'status': 'equivalent_under_assumptions' if proofs else 'original_bytes_only',
                       'proofs': proofs},
                   'scope': doc['scope'], 'generated_dos_lowering': False,
                   'native_execution': False}
        (temp / 'udc-manifest.json').write_bytes(_encoded(receipt) + b'\n')
    except BaseException:
        if temp.exists():
            current = temp.stat()
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino): shutil.rmtree(temp)
        raise
    return {'output': str(target), **receipt}
