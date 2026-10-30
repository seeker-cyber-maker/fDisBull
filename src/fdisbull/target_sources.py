"""Explicit, identity-scoped static target binding and divergent source layers."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import uuid

from .target_storage import STORAGE, connect, identity, storage_report

SOURCES_DDL = '''
CREATE TABLE IF NOT EXISTS target_sources(
 version INTEGER PRIMARY KEY REFERENCES versions(id), document TEXT NOT NULL);
'''


class TargetSourcesMixin:
    def _instruction_hex(self, value):
        return self.db.store.put(value) if hasattr(self.db, 'store') else value

    def source_sha256(self, version=None):
        """Identity of this version's container, distinct from the base import."""
        v = self.version(version)['id']
        row = self.db.execute('SELECT document FROM target_sources WHERE version=?', (v,)).fetchone()
        return json.loads(row[0])['identity']['sha256'] if row else self.meta['source_sha256']

    def _record_derived_source(self, parent, version):
        row = self.db.execute('SELECT document FROM target_sources WHERE version=?',(parent,)).fetchone()
        source = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(version,)).fetchone()
        if row and source and source[0] is not None:
            document = json.loads(row[0])
            document.pop('approval', None)
            document.update(identity=identity(source[0]), base_version=parent,
                            origin='explicit authored patch; mapped-byte and container identities may differ')
            self.db.execute('INSERT INTO target_sources VALUES (?,?)',(version,json.dumps(document)))

    def source_info(self, version=None):
        v = self.version(version)['id']
        row = self.db.execute('SELECT document FROM target_sources WHERE version=?', (v,)).fetchone()
        if not row:
            return {'version': v, 'storage': 'legacy-embedded', 'verified': False,
                    'note': 'Legacy source identity unavailable; inspect storage and explicitly migrate to a new derivative.'}
        document = json.loads(row[0])
        original = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (v,)).fetchone()
        verified = original is not None and original[0] is not None
        if verified and identity(original[0]) != document['identity']:
            raise ValueError('source identity record disagrees with verified external object')
        return {'version': v, **document, 'verified': verified,
                'verification': 'byte identity against the recorded import; not publisher authenticity, trust or licensing'}

    def _source_image(self, path, version):
        from .loader import load_image
        row = self.db.execute('SELECT document FROM target_sources WHERE version=?', (version,)).fetchone()
        if not row:
            raise ValueError('source binding requires an external-source identity; explicitly migrate legacy projects first')
        document = json.loads(row[0])
        # load_image reads once and returns the immutable validated snapshot.
        image = load_image(path, **document['loader_options'])
        if (image.arch, image.bits, image.format, image.entry) != (self.arch, self.bits, self.meta['format'], self.meta['entry']):
            raise ValueError('candidate layout/processor/entry differs; explicitly start a separate analysis')
        return document, image

    def source_candidate(self, path, version=None):
        v = self.version(version)
        document, image = self._source_image(path, v['id'])
        candidate = identity(image.source_bytes)
        exact = candidate == document['identity']
        approval = {'project_id': self.meta['project_id'], 'base_version': v['id'],
                    'base_mapped_sha256': v['sha256'], 'base_identity': document['identity'],
                    'candidate_identity': candidate, 'loader_options': document['loader_options']}
        return {'exact_match': exact, 'candidate_identity': candidate,
                'approval_required': not exact, 'approval': approval if not exact else None,
                'attached': False, 'executed': False,
                'choices': ['explicitly approve this layer', 'explicitly create a separate analysis', 'leave unattached'] if not exact else ['bind exact source']}

    def bind_source(self, path, version=None, approval=None):
        """Bind immutable data, never run a binary. Approval is an exact receipt.

        The caller must obtain the user's approval for this receipt; producing
        a candidate receipt is not approval. Booleans/generic flags are rejected.
        """
        from .project import key, now
        v = self.version(version)
        document, image = self._source_image(path, v['id'])
        candidate = identity(image.source_bytes)
        expected = {'project_id': self.meta['project_id'], 'base_version': v['id'],
                    'base_mapped_sha256': v['sha256'], 'base_identity': document['identity'],
                    'candidate_identity': candidate, 'loader_options': document['loader_options']}
        exact = candidate == document['identity']
        if exact:
            if approval is not None:
                raise ValueError('exact source binding does not accept a divergence approval')
            if self.digest(image.regions) != v['sha256']:
                raise ValueError('source matches the container but not this mapped version; bind its recorded external store')
        elif type(approval) is not dict or json.dumps(approval, sort_keys=True, separators=(',', ':')) != json.dumps(expected, sort_keys=True, separators=(',', ':')):
            raise ValueError('source diverges: exact user approval for this project/base/candidate is required; nothing attached. Explicitly choose a separate analysis if desired')
        if not hasattr(self.db, 'store'):
            raise ValueError('source layers require an external-storage project')
        # Nothing persists (even to the private store) until identity/approval is checked.
        with self.transaction(True):
            if exact:
                for region in image.regions:
                    self.db.store.put(region.data)
                self.db.store.put(image.source_bytes)
                for row in self.db.execute('SELECT address,size FROM instructions WHERE version=?',(v['id'],)):
                    address = int(row['address'],16)
                    region = next((r for r in image.regions if r.start <= address and address + row['size'] <= r.start + len(r.data)),None)
                    if region is not None:
                        self.db.store.put(region.data[address-region.start:address-region.start+row['size']].hex())
                return {'version': v['id'], 'identity': candidate, 'attached': True, 'layer': False, 'executed': False}
            cur = self.db.execute('INSERT INTO versions(parent,label,origin,sha256,created) VALUES (?,?,?,?,?)',
                                  (v['id'], 'approved external source layer', 'explicit user source approval', self.digest(image.regions), now()))
            child = cur.lastrowid
            for r in image.regions:
                self.db.execute('INSERT INTO regions VALUES (?,?,?,?,?,?)', (child, r.name, key(r.start), r.data, r.executable, r.writable))
            self._init_information(image, child)
            record = {'identity': candidate, 'format': image.format, 'arch': image.arch, 'bits': image.bits,
                      'loader_options': document['loader_options'], 'loader': document['loader'],
                      'schema': 9, 'approval': expected, 'base_version': v['id']}
            self.db.execute('INSERT INTO target_sources VALUES (?,?)', (child, json.dumps(record)))
            return {'version': child, 'parent': v['id'], 'identity': candidate, 'attached': True, 'layer': True, 'executed': False}

    def new_source_analysis(self, path, project, version=None):
        row = self.db.execute('SELECT document FROM target_sources WHERE version=?', (self.version(version)['id'],)).fetchone()
        if not row:
            raise ValueError('legacy source needs explicit loader options via import')
        options = json.loads(row[0])['loader_options']
        with type(self).create(project, path, **options) as separate:
            return {'project': str(separate.path), 'source': separate.source_info(), 'existing_analysis_preserved': True, 'executed': False}

    @classmethod
    def migrate_external(cls, source, destination):
        """Explicit streaming derivative. Never copy raw pages or rewrite source.

        Do not open a legacy Project first: opening it may apply historical
        additive migrations. Work from a read-only SQLite snapshot instead.
        """
        report = storage_report(source)
        if report['storage'] == STORAGE:
            raise ValueError('project already uses external storage')
        target = Path(destination).resolve()
        if target == Path(source).resolve():
            raise ValueError('migration requires a separate new destination; preserve the private original')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as old:
                old.execute('BEGIN')
                # Copy table DDL, then stream cells through the external encoder.
                # No legacy raw page enters the derivative/WAL/freelist.
                with closing(connect(target, external=True)) as new:
                    tables = old.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                    for table, sql in tables:
                        new.execute(sql)
                    new.execute(SOURCES_DDL)
                    for table, sql in tables:
                        quoted = '"' + table.replace('"', '""') + '"'
                        columns = [c[1] for c in old.execute(f'PRAGMA table_info({quoted})')]
                        for row in old.execute(f'SELECT * FROM {quoted}'):
                            values = list(row)
                            if table == 'instructions':
                                pos = columns.index('bytes')
                                values[pos] = new.store.put(values[pos])
                            new.execute(f'INSERT INTO {quoted} VALUES ({",".join("?" for _ in values)})', values)
                    for name, sql in old.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
                        new.execute(sql)
                    metadata = {k: json.loads(v) for k, v in old.execute('SELECT key,value FROM metadata')
                                if k not in ('application', 'schema')}
                    columns = {name for name, _ in tables}
                    if 'binary_info' in columns:
                        for version, raw in old.execute('SELECT version,source_bytes FROM binary_info WHERE source_bytes IS NOT NULL'):
                            if new.execute('SELECT 1 FROM target_sources WHERE version=?', (version,)).fetchone():
                                continue
                            options = {'entry': metadata['entry'], 'module': True}
                            loader = metadata.get('loader_metadata', {})
                            fmt = metadata['format']
                            if fmt == 'raw':
                                start = old.execute('SELECT start FROM regions WHERE version=? ORDER BY start LIMIT 1', (version,)).fetchone()
                                options.update(arch=metadata['arch'], bits=metadata['bits'], base=int(start[0],16))
                            elif fmt in ('COM','MZ','LE','PE'):
                                options['image'] = fmt.lower()
                                if fmt in ('COM','MZ'):
                                    options['load_segment'] = loader.get('dos', {}).get('load_segment', 0x1000)
                            if loader.get('slice_arch'):
                                options['slice_arch'] = loader['slice_arch']
                            record = {'identity':identity(raw), 'format':fmt, 'arch':metadata['arch'],
                                      'bits':metadata['bits'], 'loader_options':options, 'schema':9,
                                      'loader':{'name':'fdisbull.load_image','version':'unknown legacy import'},
                                      'migration':{'source_schema':report['schema'],
                                                   'qualification':'identity measured from retained legacy bytes; loader options reconstructed, mapping must still match before binding'}}
                            new.execute('INSERT INTO target_sources VALUES (?,?)', (version,json.dumps(record)))
                    # The normal constructor applies additive old-schema upgrades,
                    # preserving the legacy schema value until that has happened.
                    new.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('storage', json.dumps(STORAGE)))
                    new.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('project_id', json.dumps(uuid.uuid4().hex)))
                    new.commit()
            with cls(target) as migrated:
                result = migrated.storage_info()
            return {'source_preserved': True, 'derivative': str(target), **result,
                    'note': 'Known byte columns and structured raw caches externalized; arbitrary free text and unknown extension schemas still require review. Legacy source binding may need a fresh import.'}
        except BaseException:
            target.unlink(missing_ok=True)
            Path(str(target) + '-wal').unlink(missing_ok=True)
            Path(str(target) + '-shm').unlink(missing_ok=True)
            raise

    def storage_info(self):
        return storage_report(self.path)
