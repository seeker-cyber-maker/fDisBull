"""Artifact-checked build witnesses and independently qualified map transfers."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from .source_native import map_procedure, parse_cod, parse_link_map, sha, unpack_exepack


BUILD_DDL = (
    'CREATE TABLE IF NOT EXISTS source_builds(id TEXT PRIMARY KEY,snapshot TEXT REFERENCES snapshots(id),document TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS source_native_maps(id TEXT PRIMARY KEY,entity TEXT REFERENCES entities(id),build TEXT REFERENCES source_builds(id),document TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS source_map_transfers(id TEXT PRIMARY KEY,source_map TEXT REFERENCES source_native_maps(id),target_map TEXT REFERENCES source_native_maps(id),document TEXT NOT NULL)',
)


def _read(path, limit=64 * 1024 * 1024):
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('build artifact is missing or exceeds size budget')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('build artifact exceeds size budget')
    return value


def _artifact(directory, name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
        raise ValueError('build artifact requires a normalized relative path')
    path = directory.joinpath(*p.parts)
    if path.is_symlink() or not path.resolve().is_relative_to(directory):
        raise ValueError('build artifact cannot escape its directory')
    return path


def checked_build(catalog, snapshot, directory, original_path):
    directory = Path(directory).resolve()
    raw = _read(directory / 'build-receipt.json', 4 * 1024 * 1024)
    receipt = json.loads(raw)
    if receipt.get('schema') != 'fdisbull-civd-build-1' or receipt.get('verified') is not True:
        raise ValueError('a successful pinned CivD build receipt is required')
    if len(receipt.get('source_inputs', [])) > 2048 or len(receipt.get('artifacts', [])) > 4096:
        raise ValueError('build witness exceeds artifact budget')
    row = catalog.db.execute('SELECT document FROM snapshots WHERE id=?', (snapshot,)).fetchone()
    if row is None:
        raise ValueError('unknown source snapshot')
    source = json.loads(row[0])
    if source['revision'] != receipt.get('revision'):
        raise ValueError('build revision differs from source snapshot')
    original = _read(Path(original_path))
    digest = sha(original)
    if source['target_sha256'] != digest or receipt.get('original_sha256') != digest:
        raise ValueError('build target differs from the source snapshot original')
    inputs = {x['path']: x['sha256'] for x in receipt['source_inputs']}
    for file in source['files']:
        if inputs.get(file['path']) != file['sha256']:
            raise ValueError('build source differs from captured source')
    for name, digest in inputs.items():
        if sha(_read(_artifact(directory, PurePosixPath(name).name))) != digest:
            raise ValueError('staged build source changed')
    artifacts = {x['path']: x['sha256'] for x in receipt['artifacts']}
    for name, digest in artifacts.items():
        if sha(_read(_artifact(directory, name))) != digest:
            raise ValueError('build artifact changed: ' + name)
    for item in receipt['outputs']:
        if (item['match'] is not True or item['expected'] != item['actual']
                or artifacts.get(item['path']) != item['actual']):
            raise ValueError('build output identity is not verified')
    if artifacts.get('CIV.EXE') != sha(original):
        raise ValueError('rebuilt game differs from original')
    before, after = _read(directory / 'CIVRAW.EXE'), _read(directory / 'CIV.EXE')
    changes = [dict(file_offset=i, raw=a, corrected=b) for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(before) != len(after) or len(changes) != 4 or changes != receipt['startup_correction']:
        raise ValueError('unaccounted generated startup correction')
    view = unpack_exepack(original)
    return dict(snapshot=snapshot, revision=source['revision'], edition=source['edition'],
                original_sha256=sha(original), receipt_sha256=sha(raw), artifacts=artifacts,
                source_inputs=inputs, startup_correction=changes,
                decoded_image_sha256=view['image_sha256'], decoded_module_sha256=view['module_sha256'],
                status='build-result-and-artifacts-checked', compiler_execution='external-build-witness',
                runtime_observed=False, semantic_equivalence=False, layer_admission=False), view, directory


class SourceBuildsMixin:
    def _build_schema(self):
        # Only explicit build mutations extend an old catalog; reads never migrate
        # frozen source experiments or rewrite their original records.
        for sql in BUILD_DDL:
            self.db.execute(sql)

    def _build_put(self, table, kind, document, parents):
        from .source_catalog import _identity, _json
        identity = _identity(kind, document)
        with self.db:
            self._build_schema()
            self.db.execute('INSERT OR IGNORE INTO ' + table + ' VALUES('
                            + ','.join('?' for _ in range(len(parents) + 2)) + ')',
                            (identity, *parents, _json(document)))
        return dict(id=identity, document=document)

    def _build_get(self, table, identity):
        if not self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            raise ValueError('no recorded build/native mappings')
        row = self.db.execute('SELECT document FROM ' + table + ' WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('unknown build/native mapping')
        return json.loads(row[0])

    def _build_list(self, table, filters, offset, limit):
        from .source_catalog import _integer
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        if not self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            return dict(items=[], total=0, has_more=False)
        terms = [name + '=?' for name, value in filters if value is not None]
        args = [value for name, value in filters if value is not None]
        where = ' WHERE ' + ' AND '.join(terms) if terms else ''
        total = self.db.execute('SELECT count(*) FROM ' + table + where, args).fetchone()[0]
        rows = self.db.execute('SELECT id,document FROM ' + table + where
                              + ' ORDER BY id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return dict(items=[dict(id=r['id'], document=json.loads(r['document'])) for r in rows],
                    total=total, has_more=offset + len(rows) < total)

    def register_build(self, snapshot, directory, original_path):
        document, _, _ = checked_build(self, snapshot, directory, original_path)
        return self._build_put('source_builds', 'source-build', document, [snapshot])

    def builds(self, snapshot=None, offset=0, limit=100):
        return self._build_list('source_builds', [('snapshot', snapshot)], offset, limit)

    def map_native(self, entity, build, directory, original_path, source_line=None, project=None):
        from .source_catalog import _identity, _integer
        row = self._entity(entity)
        if row['kind'] != 'function':
            raise ValueError('compiler native mapping requires a source function entity')
        existing = self._build_get('source_builds', build)
        document, view, directory = checked_build(self, row['snapshot'], directory, original_path)
        if _identity('source-build', document) != build or document != existing:
            raise ValueError('build witness changed or belongs to another source edition')
        if source_line is not None:
            _integer(source_line, 'source_line', row['line'], row['end_line'])
        stem = PurePosixPath(row['path']).stem
        listing, link = stem + '.COD', 'CIV.MAP'
        if listing not in document['artifacts'] or link not in document['artifacts']:
            raise ValueError('compiler listing or linker map is not in the build witness')
        mapping = map_procedure(parse_link_map(_read(directory / link).decode()),
                                parse_cod(_read(directory / listing).decode()), view, '_' + row['name'], source_line)
        raw_view = unpack_exepack(_read(directory / 'CIVRAW.EXE'))
        for span in mapping['spans']:
            begin, end = span['module_offset'], span['module_offset'] + span['size']
            if raw_view['module'][begin:end] != view['module'][begin:end]:
                raise ValueError('generated startup correction intersects selected compiler code')
            data = bytearray(view['module'][span['module_offset']:span['module_offset'] + span['size']])
            for offset, segment in view['relocations']:
                site = segment * 16 + offset - span['module_offset']
                if -1 <= site < len(data):
                    if site < 0 or site + 2 > len(data):
                        raise ValueError('native span cuts a DOS load-relocation word')
                    data[site:site + 2] = b'\0\0'
            span['dos_relocation_normalized_sha256'] = sha(bytes(data))
        mapping.update(entity=entity, build=build, snapshot=row['snapshot'], source_path=row['path'],
                       source_file_sha256=row['file_sha256'], original_sha256=document['original_sha256'],
                       decoded_image_sha256=view['image_sha256'], decoded_module_sha256=view['module_sha256'],
                       listing_sha256=document['artifacts'][listing], linker_map_sha256=document['artifacts'][link],
                       profile='exepack-resident-rb16-1', source_name_inferred=True,
                       generated_startup_correction_outside_spans=True,
                       runtime_observed=False, semantic_equivalence=False, layer_admission=False)
        if source_line is not None:
            raw = self.db.execute('SELECT data FROM blobs WHERE sha=?', (row['file_sha256'],)).fetchone()[0]
            mapping['source_line_sha256'] = sha(bytes(raw).splitlines(keepends=True)[source_line - 1])
        if project is not None:
            from .project import Project
            with Project(project) as native:
                if native.meta['format'] != 'MZ' or native.meta['source_sha256'] != view['image_sha256']:
                    raise ValueError('analysis project must retain this exact derived resident MZ image')
                load_segment = native.meta['loader_metadata']['dos']['load_segment']
                spans = [dict(address=f"{load_segment + s['segment']:04x}:{s['offset']:04x}", size=s['size'])
                         for s in mapping['spans']]
                captured = native.capture_snippet(
                    row['name'] + (f':line-{source_line}' if source_line is not None else ''), spans, version=1,
                    boundary=dict(basis='compiler-listing-and-linker-map', control_flow_qualified=False),
                    evidence=dict(original_sha256=mapping['original_sha256'], profile=mapping['profile'],
                                  build=build, listing_sha256=mapping['listing_sha256']),
                    author='verified-source-build')
                endpoint = native.snippet_info(captured['id'], full=True)
                mapping['analysis_endpoint'] = {key: endpoint[key] for key in ('id', 'sha256', 'document')}
                mapping['analysis_endpoint_scope'] = 'Derived resident MZ version 1; original provenance retained separately.'
        return self._build_put('source_native_maps', 'source-native-map', mapping, [entity, build])

    def native_maps(self, entity=None, build=None, offset=0, limit=100):
        return self._build_list('source_native_maps', [('entity', entity), ('build', build)], offset, limit)

    def propagate_native_map(self, mapping, target_snapshot, directory, original_path, project=None):
        source = self._build_get('source_native_maps', mapping)
        row = self._entity(source['entity'])
        targets = self.db.execute('SELECT id FROM entities WHERE snapshot=? AND path=? AND name=? AND kind=?',
                                  (target_snapshot, row['path'], row['name'], row['kind'])).fetchall()
        if len(targets) != 1:
            raise ValueError('same-name/path candidate is missing or ambiguous; no native map inherited')
        target = self._entity(targets[0]['id'])
        line = None
        def source_bytes(entity):
            data = bytes(self.db.execute('SELECT data FROM blobs WHERE sha=?', (entity['file_sha256'],)).fetchone()[0])
            return data, data[entity['start']:entity['end']]
        original_file, original_body = source_bytes(row)
        target_file, target_body = source_bytes(target)
        if source['source_line'] is not None:
            selected = original_file.splitlines()[source['source_line'] - 1].strip()
            matches = [i + 1 for i, value in enumerate(target_file.splitlines())
                       if target['line'] <= i + 1 <= target['end_line'] and value.strip() == selected]
            if len(matches) != 1:
                raise ValueError('source statement candidate is missing or ambiguous')
            line = matches[0]
        target_build = self.register_build(target_snapshot, directory, original_path)
        mapped = self.map_native(target['id'], target_build['id'], directory, original_path, line, project)
        old, new = source['spans'], mapped['document']['spans']
        transfer = dict(source_map=mapping, target_map=mapped['id'],
                        selector='same-source-name/path; exact stripped source line when selected',
                        source_body_identical=sha(original_body) == sha(target_body),
                        native_bytes_identical=[(s['size'], s['sha256']) for s in old] == [(s['size'], s['sha256']) for s in new],
                        dos_relocation_normalized_identical=[(s['size'], s['dos_relocation_normalized_sha256']) for s in old]
                        == [(s['size'], s['dos_relocation_normalized_sha256']) for s in new],
                        qualification='candidate located, then independently checked against target build',
                        inherited_native_address=False, semantic_equivalence=False, layer_admission=False)
        return self._build_put('source_map_transfers', 'source-map-transfer', transfer, [mapping, mapped['id']])

    def map_transfers(self, mapping=None, offset=0, limit=100):
        return self._build_list('source_map_transfers', [('source_map', mapping)], offset, limit)
