"""Schema-9 boundary storing private target objects separately from the FDB.

SQLite retains size/hash references. The project connection resolves them from
an independently private object store, verifying every read. This is storage
separation, not a sanitizer for arbitrary user-authored text or exported UIL.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

PREFIX = 'fdisbull-external-object-1:'
JSON_KEY = '$fdisbull_external_object_1'
MAX_OBJECT = 128 * 1024 * 1024
STORAGE = 'external-objects-1'


def identity(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def reference(value):
    if not isinstance(value, str):
        return None
    if value.startswith(PREFIX):
        encoded = value[len(PREFIX):]
    elif value.startswith('{"' + JSON_KEY + '":'):
        encoded = None
    else:
        return None
    try:
        ref = json.loads(encoded) if encoded is not None else json.loads(value)[JSON_KEY]
        if (set(ref) != {'size', 'sha256', 'encoding'} or type(ref['size']) is not int
                or not 0 <= ref['size'] <= MAX_OBJECT or ref['encoding'] not in ('bytes', 'text')
                or len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256'])):
            raise ValueError
        return ref
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('invalid external object identity') from error


class TargetStore:
    def __init__(self, root=None):
        default = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'fdisbull/target-objects'
        self.root = Path(root or os.environ.get('FDISBULL_TARGET_STORE', default)).expanduser().absolute()
        for parent in (self.root, *self.root.parents):
            if parent.is_symlink() or (parent / '.git').exists() or (parent / '.git').is_symlink():
                raise ValueError('target object store must be private, outside Git and without symlink ancestry')

    def put(self, value):
        encoding = 'text' if isinstance(value, str) else 'bytes'
        data = value.encode('utf-8') if encoding == 'text' else bytes(value)
        if len(data) > MAX_OBJECT:
            raise ValueError('external object exceeds 128 MiB')
        ref = {**identity(data), 'encoding': encoding}
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise ValueError('target object store permissions must be private (0700)')
        path = self.root / ref['sha256']
        if path.is_symlink():
            raise ValueError('target object cannot be a symlink')
        if path.exists():
            self.get(PREFIX + json.dumps(ref, sort_keys=True))
        else:
            # Exclusive creation prevents following a competing symlink. Interrupted
            # writes remain detectable by the length/hash check; never trust a name.
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                self.get(PREFIX + json.dumps(ref, sort_keys=True))
            else:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        if encoding == 'text' and value.startswith('{'):
            try:
                document = json.loads(value)
            except ValueError:
                document = None
            if isinstance(document, dict):
                # Preserve the two semantic index selectors used by SQLite. The
                # complete record (including all raw caches) remains external.
                envelope = {JSON_KEY: ref}
                if isinstance(document.get('kind'), str):
                    envelope['kind'] = document['kind']
                if isinstance(document.get('source'), dict) and isinstance(document['source'].get('kind'), str):
                    envelope['source'] = {'kind': document['source']['kind']}
                return json.dumps(envelope, separators=(',', ':'))
        return PREFIX + json.dumps(ref, sort_keys=True, separators=(',', ':'))

    def get(self, value):
        ref = reference(value)
        if ref is None:
            return value
        path = self.root / ref['sha256']
        if path.is_symlink():
            raise ValueError('external target object is a symlink')
        try:
            with path.open('rb') as stream:
                data = stream.read(ref['size'] + 1)
        except FileNotFoundError as error:
            raise ValueError(f"external target object missing: sha256={ref['sha256']}; supply the verified source/store") from error
        if identity(data) != {k: ref[k] for k in ('size', 'sha256')}:
            raise ValueError('external target object size/SHA-256 mismatch; no bytes attached')
        return data.decode('utf-8') if ref['encoding'] == 'text' else data


# These structured records may contain raw memory, guards, original instructions,
# or opaque backend evidence. Externalize the entire value when detected, rather
# than deleting one nested byte field and silently invalidating its certificate.
RAW_KEYS = {'bytes', 'bytes_hex', 'data_hex', 'expected_hex', 'witness_hex', 'data_base64',
            'hex', 'source_bytes', 'initial', 'memory_bytes', 'raw_bytes', 'pixels-hex',
            'execute-mask-hex', 'execute-bytes-hex', 'execute-base-hex'}


def contains_raw(value):
    if isinstance(value, dict):
        return any(k in RAW_KEYS or (k.endswith(('_hex', '_base64', '_bytes')) and isinstance(v, (str, list, dict)))
                   or contains_raw(v) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_raw(v) for v in value)
    return False


class ExternalConnection(sqlite3.Connection):
    """Adapt payload parameters before SQLite sees them (including its WAL).

    SQL-level copies retain references. This is an internal Project connection,
    not a sandbox for arbitrary SQL: clients must use the public Project APIs.
    """
    def configure(self, store):
        self.store = store
        self.row_factory = self._row
        self.create_function('fdb_length', 1, self._length)
        self.create_function('fdb_substr', 3, self._substr)

    def _encode(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            return self.store.put(value)
        if isinstance(value, str):
            if reference(value) is not None:
                return value
            if value.startswith(('{', '[')):
                try:
                    raw = contains_raw(json.loads(value))
                except (ValueError, RecursionError):
                    raw = False
                if raw:
                    return self.store.put(value)
        return value

    def execute(self, sql, parameters=(), /):
        if hasattr(self, 'store'):
            parameters = ({k: self._encode(v) for k, v in parameters.items()} if isinstance(parameters, dict)
                          else tuple(self._encode(v) for v in parameters))
        return super().execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters, /):
        if hasattr(self, 'store'):
            seq_of_parameters = [({k: self._encode(v) for k, v in p.items()} if isinstance(p, dict)
                                  else tuple(self._encode(v) for v in p)) for p in seq_of_parameters]
        return super().executemany(sql, seq_of_parameters)

    def _row(self, cursor, values):
        decoded = []
        for column, value in zip(cursor.description, values):
            try:
                value = self.store.get(value)
            except ValueError as error:
                if 'external target object missing:' not in str(error):
                    raise
                # Research remains readable without the instruction byte cache or
                # source container. No source-dependent operation gets fake bytes.
                if column[0] == 'source_bytes':
                    value = None
                elif column[0] == 'bytes':
                    value = ''
                else:
                    raise
            decoded.append(value)
        return sqlite3.Row(cursor, tuple(decoded))

    def _length(self, value):
        ref = reference(value)
        return ref['size'] if ref else (len(value) if value is not None else None)

    def _substr(self, value, start, count):
        value = self.store.get(value)
        if value is None:
            return None
        if start < 1 or count < 0:
            raise ValueError('external payload slices require positive offsets and nonnegative lengths')
        return value[start - 1:start - 1 + count]


def connect(path, *, external=False, store=None):
    db = sqlite3.connect(path, timeout=30, factory=ExternalConnection if external else sqlite3.Connection)
    db.row_factory = sqlite3.Row
    if external:
        db.configure(store or TargetStore())
    else:
        db.create_function('fdb_length', 1, lambda x: len(x) if x is not None else None)
        db.create_function('fdb_substr', 3, lambda x, start, size: x[start-1:start-1+size] if x is not None else None)
    return db


def storage_report(path):
    """Read-only detection; never migrate on inspection or infer safety by suffix."""
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        metadata = dict(db.execute('SELECT key,value FROM metadata'))
        external = metadata.get('storage') == json.dumps(STORAGE)
        payloads = []
        for table, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
            quoted = '"' + table.replace('"', '""') + '"'
            for col in db.execute(f'PRAGMA table_info({quoted})'):
                field = '"' + col[1].replace('"', '""') + '"'
                byte_column = col[2].upper() == 'BLOB' or (table == 'instructions' and col[1] == 'bytes')
                record_column = table == 'debug_events' and col[1] == 'evidence'
                if byte_column or record_column or col[2].upper() == 'TEXT':
                    for (value,) in db.execute(f'SELECT {field} FROM {quoted} WHERE {field} IS NOT NULL'):
                        if value in ('', b'') or reference(value) is not None:
                            continue
                        raw_json = False
                        if isinstance(value,str) and value.startswith(('{','[')):
                            try:
                                raw_json = contains_raw(json.loads(value))
                            except (ValueError,RecursionError):
                                pass
                        if byte_column or record_column or raw_json:
                            payloads.append({'table': table, 'column': col[1]})
                            break
        return {'schema': int(metadata['schema']), 'storage': STORAGE if external else 'legacy-embedded',
                'embedded_payload_columns': payloads,
                'publication_ready': False,
                'note': 'Storage inventory only. Review free text, semantic representations, exports and external dependencies before publication.'}
