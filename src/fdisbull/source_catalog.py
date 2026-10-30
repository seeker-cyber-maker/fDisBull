"""Private source snapshots and rebuildable retrieval, separate from native mappings.

Names and syntactic occurrences are source evidence, not recovered binary facts.
Embedding vectors are supplied explicitly: this module never downloads a model,
executes source/build commands, or sends source to a service.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path, PurePosixPath
import re
import sqlite3
import struct


MAX_FILE = 4 * 1024 * 1024
MAX_SNAPSHOT = 64 * 1024 * 1024
CARD_BYTES = 1200
CARD_OVERLAP = 160
DDL = """
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO metadata VALUES('application','fdisbull-source-catalog-1');
CREATE TABLE blobs(sha TEXT PRIMARY KEY,data BLOB NOT NULL);
CREATE TABLE snapshots(id TEXT PRIMARY KEY,document TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE files(snapshot TEXT REFERENCES snapshots(id),path TEXT,sha TEXT REFERENCES blobs(sha),
 language TEXT,status TEXT,errors INTEGER,PRIMARY KEY(snapshot,path));
CREATE TABLE entities(id TEXT PRIMARY KEY,snapshot TEXT,path TEXT,kind TEXT,name TEXT,
 owner TEXT,start INTEGER,end INTEGER,line INTEGER,end_line INTEGER,parse_error INTEGER,
 FOREIGN KEY(snapshot,path) REFERENCES files(snapshot,path));
CREATE INDEX entity_snapshot ON entities(snapshot,path,start);
CREATE TABLE occurrences(entity TEXT REFERENCES entities(id),name TEXT,kind TEXT,start INTEGER,end INTEGER);
CREATE INDEX occurrence_name ON occurrences(name,entity);
CREATE TABLE cards(sha TEXT PRIMARY KEY,text TEXT NOT NULL);
CREATE TABLE entity_cards(entity TEXT REFERENCES entities(id),card TEXT REFERENCES cards(sha),
 start INTEGER,end INTEGER,PRIMARY KEY(entity,card,start));
CREATE VIRTUAL TABLE card_fts USING fts5(sha UNINDEXED,text,tokenize='porter unicode61');
CREATE TABLE models(id TEXT PRIMARY KEY,document TEXT NOT NULL,dimensions INTEGER NOT NULL);
CREATE TABLE embeddings(model TEXT REFERENCES models(id),card TEXT REFERENCES cards(sha),
 vector BLOB NOT NULL,PRIMARY KEY(model,card));
CREATE TABLE concepts(id TEXT PRIMARY KEY,key TEXT UNIQUE,document TEXT NOT NULL);
CREATE TABLE concept_links(id TEXT PRIMARY KEY,concept TEXT REFERENCES concepts(id),
 entity TEXT REFERENCES entities(id),document TEXT NOT NULL);
"""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _identity(kind, value):
    return kind + ':' + _sha(_json(value).encode())


def _text(value, name, maximum=4096):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\0' in value:
        raise ValueError(f'{name} requires nonempty text of at most {maximum} characters')
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('expected a lowercase SHA-256 digest')
    return value


def _words(text):
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text).replace('_', ' ')
    return re.findall(r'[a-zA-Z0-9]+', text.lower())


def _vector(value, dimensions):
    if (not isinstance(value, (list, tuple)) or len(value) != dimensions
            or any(type(x) not in (float, int) or not math.isfinite(x) for x in value)):
        raise ValueError('vector must have the model dimension and finite numeric components')
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('vector must have a finite nonzero norm')
    return [x / norm for x in value]


def _name_node(node):
    """Follow declarators instead of guessing function names from source text."""
    while node is not None:
        if node.type in ('identifier', 'field_identifier', 'type_identifier'):
            return node
        child = node.child_by_field_name('declarator')
        if child is None:
            child = next((c for c in node.named_children
                          if c.type in ('identifier', 'field_identifier', 'type_identifier',
                                        'function_declarator', 'pointer_declarator',
                                        'array_declarator', 'parenthesized_declarator')), None)
        node = child
    return None


def _c_parser():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_c
    except ImportError as exc:
        raise ValueError('C indexing needs the optional fdisbull[source] dependencies') from exc
    return Parser(Language(tree_sitter_c.language())), {
        'frontend': 'tree-sitter-c',
        'tree_sitter': importlib.metadata.version('tree-sitter'),
        'tree_sitter_c': importlib.metadata.version('tree-sitter-c'),
        'binding_resolution': False,
    }


def _extract(parser, data):
    tree = parser.parse(data)
    entities, errors = [], 0
    stack = [(tree.root_node, '')]
    while stack:
        node, owner = stack.pop()
        errors += int(node.is_error or node.is_missing)
        name_node = None
        kind = None
        if node.type == 'function_definition':
            name_node, kind = _name_node(node.child_by_field_name('declarator')), 'function'
        elif (node.type in ('struct_specifier', 'union_specifier', 'enum_specifier')
              and node.child_by_field_name('body') is not None):
            name_node, kind = node.child_by_field_name('name'), 'type'
        elif node.type in ('preproc_def', 'preproc_function_def'):
            name_node, kind = node.child_by_field_name('name'), 'macro'
        elif node.type == 'field_declaration':
            for child in node.children_by_field_name('declarator'):
                found = _name_node(child)
                if found is not None:
                    entities.append((node, 'field', found.text.decode('utf-8'), owner))
        if name_node is not None:
            name = name_node.text.decode('utf-8')
            entities.append((node, kind, name, owner))
            if kind in ('function', 'type'):
                owner = name
        stack.extend((child, owner) for child in reversed(node.named_children))
    return entities, errors


class SourceCatalog:
    """A collection can contain many source editions and native target identities."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ValueError('source catalog does not exist; use source-create')
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        try:
            row = self.db.execute("SELECT value FROM metadata WHERE key='application'").fetchone()
            if row is None or row[0] != 'fdisbull-source-catalog-1':
                raise ValueError('unsupported source catalog')
        except Exception:
            self.db.close()
            raise

    @classmethod
    def create(cls, path):
        path = Path(path)
        with path.open('xb'):
            pass
        db = sqlite3.connect(path)
        try:
            db.executescript('BEGIN IMMEDIATE;\n' + DDL + '\nCOMMIT;')
        except Exception:
            db.rollback()
            db.close()
            path.unlink()
            raise
        finally:
            db.close()
        return cls(path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def info(self):
        tables = ('snapshots', 'files', 'blobs', 'entities', 'cards', 'models', 'concepts', 'concept_links', 'embeddings')
        return dict(format='fdisbull-source-catalog-1',
                    counts={t: self.db.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in tables},
                    native_mappings_created=False, source_execution=False,
                    scope='Source-assisted retrieval; syntax and authored links do not establish binary equivalence.')

    def import_tree(self, root, paths, repository, revision, edition, source_role,
                    target_path=None, declared_output_sha256=None, parse_c=True):
        root = Path(root).resolve(strict=True)
        for name, value in (('repository', repository), ('revision', revision), ('edition', edition)):
            _text(value, name)
        if source_role not in ('original-source', 'reconstructed-source', 'generated-source'):
            raise ValueError('source_role must distinguish original, reconstructed or generated source')
        if type(parse_c) is not bool:
            raise ValueError('parse_c must be boolean')
        if (not isinstance(paths, list) or not 1 <= len(paths) <= 2048
                or any(not isinstance(p, str) for p in paths) or len(set(paths)) != len(paths)):
            raise ValueError('paths must be 1..2048 distinct relative source paths')
        parser, frontend = _c_parser() if parse_c else (None, {'frontend': 'none'})
        target = None
        if target_path is not None:
            digest = hashlib.sha256()
            with Path(target_path).open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            target = digest.hexdigest()
        if declared_output_sha256 is not None:
            _digest(declared_output_sha256)
            if target is None or target != declared_output_sha256:
                raise ValueError('declared output hash must match the supplied native target')
        prepared, total = [], 0
        for path in sorted(paths):
            relative = PurePosixPath(path)
            if (not path or relative.is_absolute() or '..' in relative.parts or '\\' in path
                    or str(relative) != path or any(ord(c) < 32 for c in path)):
                raise ValueError('source path must be a normalized relative POSIX path')
            source = root.joinpath(*relative.parts)
            if any(parent.is_symlink() for parent in (source, *source.parents) if parent != root.parent):
                raise ValueError('source symlinks are not followed')
            if not source.is_file() or source.stat().st_size > MAX_FILE:
                raise ValueError('source must be a regular file of at most 4 MiB')
            with source.open('rb') as stream:
                data = stream.read(MAX_FILE + 1)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_SNAPSHOT:
                raise ValueError('source snapshot exceeds size budget')
            language = 'c' if source.suffix.lower() in ('.c', '.h') else 'opaque'
            status, extracted, errors = 'retained-unparsed', [], 0
            if language == 'c' and parser is not None:
                try:
                    data.decode('utf-8')
                except UnicodeDecodeError:
                    status = 'unsupported-text-encoding'
                else:
                    extracted, errors = _extract(parser, data)
                    status = 'partial-syntax' if errors else 'syntax-indexed'
            prepared.append((path, data, language, status, extracted, errors))
        document = dict(repository=repository, revision=revision, edition=edition, source_role=source_role,
                        revision_status='caller-declared',
                        frontend=frontend, target_sha256=target,
                        target_relationship='declared-build-output' if declared_output_sha256 else 'unqualified-association',
                        build_verified=False, native_equivalence=False, card_format='source-window-1',
                        files=[dict(path=p, sha256=_sha(d)) for p, d, *_ in prepared])
        identity = _identity('source', document)
        if self.db.execute('SELECT 1 FROM snapshots WHERE id=?', (identity,)).fetchone():
            return dict(id=identity, created=False, document=document)
        with self.db:
            self.db.execute('INSERT INTO snapshots VALUES(?,?,?)',
                            (identity, _json(document), datetime.now(timezone.utc).isoformat()))
            for path, data, language, status, extracted, errors in prepared:
                sha = _sha(data)
                self.db.execute('INSERT OR IGNORE INTO blobs VALUES(?,?)', (sha, data))
                self.db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',
                                (identity, path, sha, language, status, errors))
                for node, kind, name, owner in extracted:
                    entity = _identity('entity', [identity, path, kind, name, node.start_byte, node.end_byte])
                    self.db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                    (entity, identity, path, kind, name, owner, node.start_byte, node.end_byte,
                                     node.start_point.row + 1, node.end_point.row + 1, int(node.has_error)))
                    if kind == 'function':
                        todo = [node]
                        while todo:
                            child = todo.pop()
                            if child.type in ('identifier', 'field_identifier', 'type_identifier'):
                                self.db.execute('INSERT INTO occurrences VALUES(?,?,?,?,?)',
                                                (entity, child.text.decode('utf-8'), child.type,
                                                 child.start_byte, child.end_byte))
                            todo.extend(reversed(child.named_children))
                    # Context is source text, never an inferred behavioral summary.
                    prefix = f'{kind} {name} {owner} {path}\n' + ' '.join(_words(name + ' ' + owner)) + '\n'
                    previous, following = node.prev_named_sibling, node.next_named_sibling
                    if previous is not None and previous.type == 'comment' and node.start_byte - previous.start_byte <= 2048:
                        prefix += 'Adjacent source comment: ' + previous.text.decode('utf-8') + '\n'
                    if (following is not None and following.type == 'comment'
                            and following.start_point.row == node.end_point.row
                            and following.end_byte - node.end_byte <= 2048):
                        prefix += 'Adjacent source comment: ' + following.text.decode('utf-8') + '\n'
                    for start in range(node.start_byte, node.end_byte, CARD_BYTES - CARD_OVERLAP):
                        end = min(start + CARD_BYTES, node.end_byte)
                        text = prefix + data[start:end].decode('utf-8', errors='replace')
                        card = _sha(text.encode())
                        inserted = self.db.execute('INSERT OR IGNORE INTO cards VALUES(?,?)', (card, text)).rowcount
                        if inserted:
                            self.db.execute('INSERT INTO card_fts VALUES(?,?)', (card, text))
                        self.db.execute('INSERT INTO entity_cards VALUES(?,?,?,?)', (entity, card, start, end))
                        if end == node.end_byte:
                            break
        return dict(id=identity, created=True, document=document,
                    files=len(prepared), partial_files=sum(bool(p[-1]) for p in prepared),
                    entities=sum(len(p[-2]) for p in prepared))

    def snapshots(self, offset=0, limit=100):
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        total = self.db.execute('SELECT count(*) FROM snapshots').fetchone()[0]
        items = []
        for row in self.db.execute('SELECT * FROM snapshots ORDER BY created,id LIMIT ? OFFSET ?', (limit, offset)):
            document = json.loads(row['document'])
            file_count = len(document.pop('files'))
            items.append(dict(id=row['id'], document=document, file_count=file_count))
        return dict(items=items, total=total, has_more=offset + len(items) < total)

    def files(self, snapshot=None, offset=0, limit=100):
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        where, args = (' WHERE f.snapshot=?', [snapshot]) if snapshot is not None else ('', [])
        sql = ' FROM files f JOIN blobs b ON b.sha=f.sha' + where
        total = self.db.execute('SELECT count(*)' + sql, args).fetchone()[0]
        rows = self.db.execute('SELECT f.*,length(b.data) AS size' + sql
                              + ' ORDER BY f.snapshot,f.path LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, has_more=offset + len(rows) < total)

    def _entity(self, entity):
        row = self.db.execute('SELECT e.*,f.sha AS file_sha256,s.document AS source_document '
                              'FROM entities e JOIN files f ON f.snapshot=e.snapshot AND f.path=e.path '
                              'JOIN snapshots s ON s.id=e.snapshot WHERE e.id=?', (entity,)).fetchone()
        if row is None:
            raise ValueError('unknown source entity')
        return dict(row)

    def entities(self, snapshot=None, name=None, kind=None, offset=0, limit=100):
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        terms, args = [], []
        for key, value in (('snapshot', snapshot), ('name', name), ('kind', kind)):
            if value is not None:
                terms.append(key + '=?')
                args.append(value)
        where = ' WHERE ' + ' AND '.join(terms) if terms else ''
        total = self.db.execute('SELECT count(*) FROM entities' + where, args).fetchone()[0]
        rows = self.db.execute('SELECT * FROM entities' + where + ' ORDER BY snapshot,path,start,id LIMIT ? OFFSET ?',
                               (*args, limit, offset)).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, has_more=offset + len(rows) < total,
                    scope='Syntactic candidates; names are not resolved bindings or native symbols.')

    def source_text(self, entity, offset=0, size=4096):
        _integer(offset, 'offset', 0, MAX_FILE)
        _integer(size, 'size', 0, 16384)
        row = self._entity(entity)
        if offset > row['end'] - row['start']:
            raise ValueError('offset exceeds source entity')
        start, end = row['start'] + offset, min(row['start'] + offset + size, row['end'])
        data = self.db.execute('SELECT substr(data,?,?) FROM blobs WHERE sha=?',
                               (start + 1, end - start, row['file_sha256'])).fetchone()[0]
        return dict(entity=entity, path=row['path'], start=start, end=end, file_sha256=row['file_sha256'],
                    text=bytes(data).decode('utf-8', errors='replace'), truncated=end < row['end'])

    def occurrences(self, name, snapshot=None, offset=0, limit=100):
        _text(name, 'name', 256)
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        where, args = ' WHERE o.name=?', [name]
        if snapshot is not None:
            where += ' AND e.snapshot=?'
            args.append(snapshot)
        sql = (' FROM occurrences o JOIN entities e ON e.id=o.entity' + where)
        total = self.db.execute('SELECT count(*)' + sql, args).fetchone()[0]
        rows = self.db.execute('SELECT o.*,e.snapshot,e.path,e.name AS owner' + sql
                               + ' ORDER BY e.snapshot,e.path,o.start LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, has_more=offset + len(rows) < total,
                    scope='Exact identifier spelling occurrences; no binding resolution or read/write classification.')

    def cards(self, model=None, offset=0, limit=100):
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        where, args = '', []
        if model is not None:
            self._model(model)
            where, args = ' WHERE NOT EXISTS(SELECT 1 FROM embeddings e WHERE e.card=c.sha AND e.model=?)', [model]
        total = self.db.execute('SELECT count(*) FROM cards c' + where, args).fetchone()[0]
        rows = self.db.execute('SELECT sha,text FROM cards c' + where + ' ORDER BY sha LIMIT ? OFFSET ?',
                               (*args, limit, offset)).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, has_more=offset + len(rows) < total)

    def register_model(self, name, revision, dimensions, preprocessing):
        _text(name, 'model name')
        _text(revision, 'model revision')
        _text(preprocessing, 'preprocessing')
        _integer(dimensions, 'dimensions', 1, 4096)
        document = dict(name=name, revision=revision, dimensions=dimensions, preprocessing=preprocessing)
        identity = _identity('embedding-model', document)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO models VALUES(?,?,?)', (identity, _json(document), dimensions))
        return dict(id=identity, document=document)

    def _model(self, identity):
        row = self.db.execute('SELECT * FROM models WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('unknown embedding model')
        return row

    def embed_cards(self, model, items):
        dimensions = self._model(model)['dimensions']
        if not isinstance(items, list) or not 1 <= len(items) <= 512:
            raise ValueError('items must contain 1..512 card/vector pairs')
        prepared, seen = [], {}
        for item in items:
            if not isinstance(item, dict) or set(item) != {'card', 'vector'}:
                raise ValueError('each embedding requires only card and vector')
            card = _digest(item['card'])
            if not self.db.execute('SELECT 1 FROM cards WHERE sha=?', (card,)).fetchone():
                raise ValueError('unknown source card')
            vector = _vector(item['vector'], dimensions)
            payload = struct.pack('<' + 'f' * dimensions, *vector)
            if card in seen and seen[card] != payload:
                raise ValueError('conflicting duplicate embedding in one batch')
            seen[card] = payload
            old = self.db.execute('SELECT vector FROM embeddings WHERE model=? AND card=?', (model, card)).fetchone()
            if old is not None and old[0] != payload:
                raise ValueError('embedding is immutable; use a new model/preprocessing revision')
            prepared.append((model, card, payload))
        with self.db:
            self.db.executemany('INSERT OR IGNORE INTO embeddings VALUES(?,?,?)', prepared)
        return dict(model=model, accepted=len(prepared), scope='Caller-supplied embeddings; no model executed by fDisBull.')

    def search(self, query, mode='lexical', model=None, vector=None, snapshots=None, kind=None, limit=10):
        _text(query, 'query', 4096)
        _integer(limit, 'limit', 1, 100)
        if mode not in ('lexical', 'vector', 'hybrid'):
            raise ValueError('mode must be lexical, vector or hybrid')
        if snapshots is not None and (not isinstance(snapshots, list) or not 1 <= len(snapshots) <= 100):
            raise ValueError('snapshots must contain 1..100 explicit source snapshot IDs')
        where, args = [], []
        if snapshots:
            if any(not self.db.execute('SELECT 1 FROM snapshots WHERE id=?', (s,)).fetchone() for s in snapshots):
                raise ValueError('unknown source snapshot')
            where.append('e.snapshot IN (' + ','.join('?' for _ in snapshots) + ')')
            args.extend(snapshots)
        if kind is not None:
            where.append('e.kind=?')
            args.append(kind)
        eligible = [dict(r) for r in self.db.execute(
            'SELECT ec.*,e.snapshot,e.path,e.name,e.kind,e.line,e.parse_error,f.status AS file_status '
            'FROM entity_cards ec JOIN entities e ON e.id=ec.entity '
            'JOIN files f ON f.snapshot=e.snapshot AND f.path=e.path'
            + (' WHERE ' + ' AND '.join(where) if where else ''), args)]
        allowed = {r['card'] for r in eligible}
        lexical, semantic = [], []
        if mode in ('lexical', 'hybrid'):
            words = list(dict.fromkeys(_words(query)))[:64]
            if words:
                expression = ' OR '.join('"' + word + '"' for word in words)
                lexical = [r[0] for r in self.db.execute(
                    'SELECT sha FROM card_fts WHERE card_fts MATCH ? ORDER BY bm25(card_fts),sha', (expression,))
                           if r[0] in allowed]
        embedded = 0
        if mode in ('vector', 'hybrid'):
            row = self._model(model)
            q = _vector(vector, row['dimensions'])
            scores = []
            for r in self.db.execute('SELECT card,vector FROM embeddings WHERE model=?', (model,)):
                if r['card'] in allowed:
                    values = struct.unpack('<' + 'f' * row['dimensions'], r['vector'])
                    scores.append((math.fsum(a * b for a, b in zip(q, values)), r['card']))
            embedded = len(scores)
            semantic = [card for score, card in sorted(scores, key=lambda x: (-x[0], x[1]))]
        ranks = {}
        for ordering in (lexical, semantic):
            for index, card in enumerate(ordering):
                ranks[card] = ranks.get(card, 0.0) + 1.0 / (60 + index + 1)
        best = {}
        for row in eligible:
            if row['card'] not in ranks:
                continue
            candidate = dict(row, score=ranks[row['card']])
            old = best.get(row['entity'])
            if old is None or (-candidate['score'], candidate['card'], candidate['start']) < (-old['score'], old['card'], old['start']):
                best[row['entity']] = candidate
        items = sorted(best.values(), key=lambda r: (-r['score'], r['name'], r['path'],
                                                     r['start'], r['kind'], r['snapshot']))[:limit]
        return dict(items=items, mode=mode, score_kind='reciprocal-rank-fusion-k60',
                    tie_break='name,path,start,kind,snapshot',
                    eligible_cards=len(allowed), embedded_cards=embedded,
                    embedding_coverage=embedded / len(allowed) if allowed and mode != 'lexical' else None,
                    matching_entities=len(best), truncated=len(best) > limit,
                    scope='Candidate ranking, not confidence, exhaustive semantic coverage, equivalence or UDL admission.')

    def register_concept(self, key, description, unit='unspecified', author='agent'):
        for name, value in (('key', key), ('description', description), ('unit', unit), ('author', author)):
            _text(value, name)
        document = dict(key=key, description=description, unit=unit, author=author)
        identity = _identity('concept', document)
        old = self.db.execute('SELECT id FROM concepts WHERE key=?', (key,)).fetchone()
        if old is not None and old[0] != identity:
            raise ValueError('concept definition is immutable; use a new revision key')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO concepts VALUES(?,?,?)', (identity, key, _json(document)))
        return dict(id=identity, document=document)

    def link_concept(self, concept, entity, relation, evidence, assurance='candidate', author='agent'):
        if not self.db.execute('SELECT 1 FROM concepts WHERE id=?', (concept,)).fetchone():
            raise ValueError('unknown concept')
        self._entity(entity)
        if relation not in ('represents', 'mentions', 'implements', 'related'):
            raise ValueError('relation must distinguish represents, mentions, implements or related')
        for name, value in (('evidence', evidence), ('assurance', assurance), ('author', author)):
            _text(value, name)
        document = dict(concept=concept, entity=entity, relation=relation, evidence=evidence,
                        assurance=assurance, author=author, assertion_status='authored-declaration',
                        binary_equivalence=False, layer_admission=False)
        identity = _identity('concept-link', document)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO concept_links VALUES(?,?,?,?)',
                            (identity, concept, entity, _json(document)))
        return dict(id=identity, document=document)

    def concept_bindings(self, concept, offset=0, limit=100):
        _integer(offset, 'offset', 0, 1 << 31)
        _integer(limit, 'limit', 1, 1000)
        if not self.db.execute('SELECT 1 FROM concepts WHERE id=?', (concept,)).fetchone():
            raise ValueError('unknown concept')
        total = self.db.execute('SELECT count(*) FROM concept_links WHERE concept=?', (concept,)).fetchone()[0]
        rows = self.db.execute('SELECT l.id,l.document,e.snapshot,e.path,e.name,e.kind,e.line '
                               'FROM concept_links l JOIN entities e ON e.id=l.entity WHERE l.concept=? '
                               'ORDER BY e.snapshot,e.path,e.start,l.id LIMIT ? OFFSET ?', (concept, limit, offset)).fetchall()
        return dict(items=[dict(r, document=json.loads(r['document'])) for r in rows],
                    total=total, has_more=offset + len(rows) < total,
                    scope='Exact enumeration of recorded claims; unmapped concepts and versions remain unknown.')
