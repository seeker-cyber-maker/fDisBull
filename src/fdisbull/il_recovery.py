"""Source-linked primitive recovery and immutable project IL revisions.

Recovery recognizes selected source operations. It does not infer arbitrary
function semantics or certify equivalence from a witness supplied by a caller.
"""
from copy import deepcopy
import hashlib
import json
import sqlite3
import uuid

from .interaction_il import validate_il
from .zmachine import decode_v3


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def recover_v3_attributes(data, offsets, *, source_file, object_variable, bindings):
    """Lower source set_attr/clear_attr instructions to the shared IL nodes.

    ``bindings`` maps attribute numbers to caller-selected semantic names. The
    binding of a source variable to an object is a separate runtime witness;
    this function records the source variable and never guesses the object.
    """
    if (not isinstance(data, bytes) or len(data) < 64 or data[0] != 3
            or not isinstance(offsets, list) or not 1 <= len(offsets) <= 64
            or any(type(a) is not int or a < 64 for a in offsets)
            or len(set(offsets)) != len(offsets)
            or not isinstance(source_file, str) or not source_file
            or type(object_variable) is not int or not 16 <= object_variable <= 255
            or not isinstance(bindings, dict)):
        raise ValueError('Invalid bounded v3 recovery request')
    source_hash = hashlib.sha256(data).hexdigest()
    variables, evidence, body = {}, {}, []
    for offset in offsets:
        instruction = decode_v3(data, offset)
        operands = instruction['operands']
        if (instruction['op'] not in ('set_attr', 'clear_attr') or len(operands) != 2
                or operands[0] != {'kind': 'variable', 'value': object_variable}
                or operands[1]['kind'] not in ('small', 'large')
                or not 0 <= operands[1]['value'] < 32):
            raise ValueError('Source instruction does not match attribute rule')
        attribute = operands[1]['value']
        if attribute not in bindings or not isinstance(bindings[attribute], str):
            raise ValueError('An explicit attribute name binding is required')
        name = bindings[attribute]
        if name in variables:
            raise ValueError('Attribute bindings must be distinct for this slice')
        variables[name] = {'type': 'bool', 'initial': False}
        ref = f'source-{offset:x}'
        evidence[ref] = {'file': source_file, 'sha256': source_hash,
                         'range': [offset, instruction['end']], 'bytes': instruction['bytes'],
                         'language': 'z-machine-v3', 'source_variable': object_variable,
                         'attribute': attribute,
                         'binding_status': 'caller_named_requires_runtime_correspondence'}
        body.append({'id': ref, 'op': 'set', 'var': name,
                     'value': instruction['op'] == 'set_attr', 'evidence': [ref]})
    document = {'format': 'fdisbull-il-1', 'role': 'udl', 'variables': variables,
                'resources': {}, 'evidence': evidence, 'body': body}
    validate_il(document)
    return document


def save_il(project, name, document, *, version=None, parent=None, author='agent'):
    """Persist one immutable revision, checking file-bound source spans in DB."""
    validate_il(document)
    if not isinstance(name, str) or not 1 <= len(name) <= 128 or not isinstance(author, str) or not author:
        raise ValueError('IL revision requires a name and author')
    encoded = _encoded(document)
    project.db.execute('''CREATE TABLE IF NOT EXISTS interaction_il (
        id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
        name TEXT NOT NULL, parent TEXT REFERENCES interaction_il(id),
        sha256 TEXT NOT NULL, author TEXT NOT NULL, document TEXT NOT NULL)''')
    with project.transaction(True):
        v = project.version(version)['id']
        _verify_sources(project, document, v)
        previous = project.db.execute('SELECT * FROM interaction_il WHERE version=? AND name=? ORDER BY rowid DESC LIMIT 1', (v, name)).fetchone()
        if previous is not None and parent != previous['id']:
            raise ValueError('Updating IL requires its current immutable parent revision')
        if previous is None and parent is not None:
            raise ValueError('A first IL revision cannot have a parent')
        digest = hashlib.sha256(encoded).hexdigest()
        if previous is not None and previous['sha256'] == digest:
            return load_il(project, previous['id'], version=v)
        ident = uuid.uuid4().hex
        project.db.execute('INSERT INTO interaction_il VALUES (?,?,?,?,?,?,?)',
                           (ident, v, name, parent, digest, author, encoded.decode()))
    return load_il(project, ident, version=v)


def _verify_sources(project, document, version):
    files = {}
    for item in document.get('evidence', {}).values():
        if 'file' not in item:
            continue  # Other evidence is retained as a claim, not verified here.
        if not {'sha256', 'range', 'bytes'} <= set(item):
            raise ValueError('File evidence requires its hash, range and source bytes')
        start, end = item['range']
        if end <= start or end - start > 65536:
            raise ValueError('Source span exceeds its bound')
        name = item['file']
        if not isinstance(name, str): raise ValueError('Invalid source file name')
        if name not in files:
            row = project.db.execute('SELECT data,sha256 FROM external_files WHERE version=? AND name=?', (version,name)).fetchone()
            if row is None: raise ValueError('Source file must be attached to this project version')
            raw = bytes(row['data'])
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Stored source file hash mismatch')
            files[name] = (row['sha256'], raw)
        digest, raw = files[name]
        if (digest != item['sha256'] or end > len(raw)
                or raw[start:end].hex() != item['bytes']):
            raise ValueError('Source evidence differs from the immutable project file')


def load_il(project, revision, *, version=None):
    v = project.version(version)['id']
    try:
        row = project.db.execute('SELECT * FROM interaction_il WHERE id=? AND version=?', (revision, v)).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError('No stored IL revisions') from exc
    if row is None:
        raise ValueError('Unknown IL revision')
    document = json.loads(row['document'])
    validate_il(document)
    if hashlib.sha256(_encoded(document)).hexdigest() != row['sha256']:
        raise ValueError('Stored IL revision hash mismatch')
    _verify_sources(project, document, v)
    return {k: row[k] for k in ('id', 'version', 'name', 'parent', 'sha256', 'author')} | {'document': deepcopy(document)}
