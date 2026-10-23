"""Immutable project-local data files, addressed by file identity and offset.

These snapshots never become native mappings or executable analysis seeds.
Structural types describe the saved bytes; pointer values remain encodings.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .typesystem import _field_at, _int, _name, type_layout


MAX_EXTERNAL_FILE_SIZE = 64 * 1024 * 1024
MAX_EXTERNAL_BYTES_PER_VERSION = 64 * 1024 * 1024
MAX_FILE_READ = 65536

EXTERNAL_FILES_DDL = """
CREATE TABLE IF NOT EXISTS external_files(
    version INTEGER NOT NULL, name TEXT NOT NULL, filename TEXT NOT NULL,
    kind TEXT NOT NULL, sha256 TEXT NOT NULL, data BLOB NOT NULL,
    author TEXT NOT NULL, PRIMARY KEY(version,name));
CREATE TABLE IF NOT EXISTS file_type_bindings(
    version INTEGER NOT NULL, file TEXT NOT NULL, offset INTEGER NOT NULL,
    name TEXT NOT NULL, type_name TEXT NOT NULL, size INTEGER NOT NULL,
    author TEXT NOT NULL, PRIMARY KEY(version,file,offset));
"""


def _file_name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or value in ('.', '..') or not value.strip()
            or '/' in value or '\\' in value
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise ValueError('file name must contain 1..256 characters without slashes or control characters')
    return value


def _author(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError('author must contain 1..256 characters')
    return value


def _offset(value):
    return _int(value, 'file offset', 0, (1 << 63) - 1)


def _compact_layout(layout):
    """Describe one level without exponentially repeating nested definitions."""
    result={key:layout[key] for key in ('name','kind','size','signed','target','address_space','segment','count') if key in layout}
    if layout['kind']=='array':
        result['element']={key:layout['element'][key] for key in ('name','kind','size')}
    if layout['kind']=='struct':
        result['fields']=[dict(name=field['name'],offset=field['offset'],type=field['type']['name'],size=field['type']['size']) for field in layout['fields']]
    return result


class ExternalFilesMixin:
    def _external_file(self, v, name):
        """Return metadata without fetching the possibly large snapshot BLOB."""
        name = _file_name(name)
        row = self.db.execute(
            'SELECT version,name,filename,kind,sha256,length(data) AS size,author '
            'FROM external_files WHERE version=? AND name=?', (v, name)).fetchone()
        if row is None:
            raise ValueError(f'unknown external file: {name}')
        return row

    def attach_file(self, path, name=None, kind='data', version=None, author='agent'):
        author = _author(author)
        kind = _name(kind)
        try:
            source = Path(path)
        except (TypeError, ValueError) as error:
            raise ValueError('path must identify a regular data file') from error
        filename = _file_name(source.name)
        name = _file_name(filename if name is None else name)
        try:
            if not source.is_file():
                raise ValueError('path must identify a regular data file')
            if source.stat().st_size > MAX_EXTERNAL_FILE_SIZE:
                raise ValueError('external file exceeds the 64 MiB per-file limit')
            with source.open('rb') as stream:
                data = stream.read(MAX_EXTERNAL_FILE_SIZE + 1)
        except OSError as error:
            raise ValueError(f'cannot read external file: {error}') from error
        if len(data) > MAX_EXTERNAL_FILE_SIZE:
            raise ValueError('external file exceeds the 64 MiB per-file limit')
        sha256 = hashlib.sha256(data).hexdigest()
        with self.transaction(True):
            v = self.version(version)['id']
            previous = self.db.execute(
                'SELECT sha256 FROM external_files WHERE version=? AND name=?', (v, name)).fetchone()
            if previous is not None:
                if previous['sha256'] != sha256:
                    raise ValueError('external file name already has different immutable bytes in this version')
                return dict(self._external_file(v, name), created=False, idempotent=True)
            total = self.db.execute(
                'SELECT coalesce(sum(length(data)),0) FROM external_files WHERE version=?', (v,)).fetchone()[0]
            if total + len(data) > MAX_EXTERNAL_BYTES_PER_VERSION:
                raise ValueError('external files exceed the 64 MiB aggregate limit for this version')
            self.db.execute('INSERT INTO external_files VALUES (?,?,?,?,?,?,?)',
                            (v, name, filename, kind, sha256, data, author))
            return dict(self._external_file(v, name), created=True, idempotent=False)

    def external_files(self, version=None, limit=200, offset=0):
        limit = _int(limit, 'limit', 1, 10000)
        offset = _offset(offset)
        with self.transaction():
            v = self.version(version)['id']
            total, total_bytes = self.db.execute(
                'SELECT count(*),coalesce(sum(length(data)),0) FROM external_files WHERE version=?', (v,)).fetchone()
            rows = self.db.execute(
                'SELECT e.version,e.name,e.filename,e.kind,e.sha256,length(e.data) AS size,e.author,'
                '(SELECT count(*) FROM file_type_bindings b WHERE b.version=e.version AND b.file=e.name) AS binding_count '
                'FROM external_files e WHERE e.version=? ORDER BY e.name LIMIT ? OFFSET ?',
                (v, limit, offset)).fetchall()
            return dict(version=v, items=[dict(row) for row in rows], total=total, total_bytes=total_bytes,
                        limit=limit, offset=offset, truncated=offset + len(rows) < total)

    def file_bytes(self, name, offset=0, size=64, version=None):
        offset = _offset(offset)
        size = _int(size, 'size', 0, MAX_FILE_READ)
        with self.transaction():
            v = self.version(version)['id']
            row = self._external_file(v, name)
            if offset > row['size']:
                raise ValueError('file offset exceeds the external file size')
            raw = bytes(self.db.execute(
                'SELECT substr(data,?,?) FROM external_files WHERE version=? AND name=?',
                (offset + 1, size, v, row['name'])).fetchone()[0])
            return dict(version=v, file=row['name'], offset=offset, file_size=row['size'],
                        requested_size=size, size=len(raw), bytes=raw.hex(),
                        ascii=''.join(chr(byte) if 32 <= byte < 127 else '.' for byte in raw),
                        eof=offset + len(raw) == row['size'], truncated=len(raw) < size,
                        complete=offset == 0 and len(raw) == row['size'], sha256=row['sha256'])

    def apply_file_type(self, file, type_name, offset=0, name=None, version=None, author='agent'):
        file, type_name, offset = _file_name(file), _name(type_name), _offset(offset)
        name = _name(name) if name is not None else f'data_{offset:x}'
        author = _author(author)
        with self.transaction(True):
            v = self.version(version)['id']
            row = self._external_file(v, file)
            layout = type_layout(type_name, self._type_registry(v))
            size = layout['size']
            if offset + size > row['size']:
                raise ValueError('file type binding must fit in the external file')
            for other in self.db.execute(
                    'SELECT offset,size FROM file_type_bindings WHERE version=? AND file=? AND offset!=?',
                    (v, file, offset)):
                if offset < other['offset'] + other['size'] and offset + size > other['offset']:
                    raise ValueError('file type bindings overlap')
            self.db.execute('INSERT OR REPLACE INTO file_type_bindings VALUES (?,?,?,?,?,?,?)',
                            (v, file, offset, name, type_name, size, author))
            return dict(version=v, file=file, file_offset=offset, name=name, type=_compact_layout(layout), size=size,
                        source='user-assigned interpretation of immutable external file bytes')

    def _validate_file_types(self, v, registry):
        """Check all dependent bindings against a proposed type registry."""
        previous_file, previous_end, sizes = None, 0, []
        for row in self.db.execute(
                'SELECT b.*,length(e.data) AS file_size FROM file_type_bindings b '
                'LEFT JOIN external_files e ON e.version=b.version AND e.name=b.file '
                'WHERE b.version=? ORDER BY b.file,b.offset', (v,)):
            size = type_layout(row['type_name'], registry)['size']
            if row['file_size'] is None or row['offset'] < 0 or row['offset'] + size > row['file_size']:
                raise ValueError('updated file type binding exceeds its external file')
            if row['file'] == previous_file and row['offset'] < previous_end:
                raise ValueError('updated file type bindings would overlap')
            previous_file, previous_end = row['file'], row['offset'] + size
            sizes.append(dict(file=row['file'], offset=row['offset'], size=size))
        return sizes

    def _update_file_type_sizes(self, v, registry):
        with self.transaction(True):
            sizes = self._validate_file_types(v, registry)
            self.db.executemany('UPDATE file_type_bindings SET size=? WHERE version=? AND file=? AND offset=?',
                                [(item['size'], v, item['file'], item['offset']) for item in sizes])
            return sizes

    def _raw_file_type_location(self, v, file, offset):
        file, offset = _file_name(file), _offset(offset)
        metadata = self._external_file(v, file)
        if offset > metadata['size']:
            raise ValueError('file offset exceeds the external file size')
        row = self.db.execute(
            'SELECT * FROM file_type_bindings WHERE version=? AND file=? AND offset<=? '
            'ORDER BY offset DESC LIMIT 1', (v, file, offset)).fetchone()
        if row is None or offset >= row['offset'] + row['size']:
            return None
        layout = type_layout(row['type_name'], self._type_registry(v))
        field = _field_at(layout, offset - row['offset'])
        return dict(file=file, file_offset=offset, binding_offset=row['offset'], binding_name=row['name'],
                    binding_type=row['type_name'], name=row['name'] + field['path'], **field)

    def _file_type_location(self, v, file, offset):
        return self._raw_file_type_location(v, file, offset)

    def typed_file(self, file, offset=0, version=None, max_items=256):
        file, offset = _file_name(file), _offset(offset)
        max_items = _int(max_items, 'max_items', 1, 4096)
        with self.transaction():
            v = self.version(version)['id']
            metadata = self._external_file(v, file)
            row = self.db.execute(
                'SELECT * FROM file_type_bindings WHERE version=? AND file=? AND offset=?',
                (v, file, offset)).fetchone()
            if row is None:
                raise ValueError('typed-file requires an exact file type binding offset')
            layout = type_layout(row['type_name'], self._type_registry(v))
            if offset + layout['size'] > metadata['size']:
                raise ValueError('file type binding exceeds its external file')
            data = bytes(self.db.execute(
                'SELECT substr(data,?,?) FROM external_files WHERE version=? AND name=?',
                (offset + 1, layout['size'], v, file)).fetchone()[0])
            items, truncated, work = [], False, 0
            work_limit = max_items * 32 + 1024

            def visit(t, relative, path):
                nonlocal truncated, work
                if truncated:
                    return
                work += 1
                if len(items) >= max_items or work > work_limit:
                    truncated = True
                    return
                if t['kind'] == 'struct':
                    for field in t['fields']:
                        visit(field['type'], relative + field['offset'], path + '.' + field['name'])
                        if truncated:
                            break
                elif t['kind'] == 'array':
                    for index in range(t['count']):
                        visit(t['element'], relative + index * t['element']['size'], path + f'[{index}]')
                        if truncated:
                            break
                else:
                    raw = data[relative:relative + t['size']]
                    item = dict(file=file, file_offset=offset + relative, path=path, type=t['name'],
                                kind=t['kind'], size=t['size'], bytes=raw.hex(),
                                value=int.from_bytes(raw, 'little', signed=t.get('signed', False)))
                    if t['kind'] == 'pointer':
                        item.update(target_type=t['target'], address_space=t['address_space'],
                                    interpretation='encoded pointer value only; no native or file target inferred')
                    item["name"] = self._file_label(v, file, offset + relative)
                    items.append(item)

            visit(layout, 0, row['name'])
            return dict(version=v, file=file, file_offset=offset, layout=_compact_layout(layout), layout_expanded=False, binding=dict(row),
                        items=items, truncated=truncated, budget_exhausted=work > work_limit,
                        sha256=metadata['sha256'], byte_order='little',
                        source='immutable external file bytes; user-assigned structural interpretation')
