"""Immutable source captures and authored layer declarations; never execution.

Source/version/context/span hashes identify endpoints across project copies.
Captured bytes leave the database only through explicit include_bytes requests.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import re
import uuid

MAX_DOCUMENT = 4 * 1024 * 1024
MAX_SPANS = 256
MAX_BYTES = 16 * 1024 * 1024
MAX_SOURCE = 64 * 1024 * 1024
_FORMATS = dict(snippet='fdisbull-snippet-1', link='fdisbull-snippet-link-1',
                contract='fdisbull-block-contract-1', layer='fdisbull-udl-layer-1',
                selection='fdisbull-udl-selection-1')
_ID = re.compile(r'^(snippet|link|contract|layer|selection):([0-9a-f]{64})$')
_HASH = re.compile(r'^[0-9a-f]{64}$')
SNIPPET_DDL = '''
CREATE TABLE IF NOT EXISTS snippet_objects(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
 document TEXT NOT NULL, author TEXT NOT NULL, created TEXT NOT NULL,
 local_version INTEGER REFERENCES versions(id));
CREATE INDEX IF NOT EXISTS snippet_objects_kind ON snippet_objects(kind,created,id);
CREATE TABLE IF NOT EXISTS snippet_payloads(
 object_id TEXT NOT NULL REFERENCES snippet_objects(id), span INTEGER NOT NULL,
 role TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY(object_id,span,role));
'''


def _sha(data):return hashlib.sha256(data).hexdigest()


def _text(value, field, maximum=256):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f'{field} must contain 1..{maximum} characters without controls')
    return value


def _integer(value, field, low=0, high=(1 << 64) - 1):
    if type(value) is not int or not low <= value <= high:raise ValueError(f'{field} is outside integer bounds')
    return value


def _canonical(value):
    nodes = 0
    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 100000 or depth > 64:raise ValueError('document exceeds JSON node/depth budget')
        if type(item) is dict:
            if any(type(k) is not str for k in item):raise ValueError('JSON object keys must be strings')
            for child in item.values():visit(child, depth + 1)
        elif type(item) is list:
            for child in item:visit(child, depth + 1)
        elif type(item) is int:
            if item.bit_length() > 4096:raise ValueError('JSON integer exceeds budget')
        elif type(item) is float:
            if not math.isfinite(item):raise ValueError('JSON numbers must be finite')
        elif item is not None and type(item) not in (str, bool):raise ValueError('document must contain JSON values only')
    visit(value)
    try:raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, UnicodeError) as exc:raise ValueError('invalid JSON document') from exc
    if len(raw) > MAX_DOCUMENT:raise ValueError('document exceeds the 4 MiB limit')
    return raw


def _identity(kind, document):
    raw = _canonical(document); sha = _sha(raw)
    return kind + ':' + sha, sha, raw.decode()


def _id(value, kind):
    if not isinstance(value, str) or not _ID.fullmatch(value) or not value.startswith(kind + ':'):
        raise ValueError(kind + ' reference must be an exact immutable ID')
    return value


def _mapped_bytes(regions, address, size):
    cursor, pieces = address, []
    while cursor < address + size:
        region = next((r for r in regions if r.start <= cursor < r.start + len(r.data)), None)
        if region is None:raise ValueError('snippet span exceeds mapped version bytes')
        end = min(address + size, region.start + len(region.data))
        pieces.append(region.data[cursor - region.start:end - region.start]); cursor = end
    return b''.join(pieces)


@contextmanager
def _atomic(project):
    with project.transaction(True):
        name = 'snippet_' + uuid.uuid4().hex
        project.db.execute('SAVEPOINT ' + name)
        try:yield
        except BaseException:
            project.db.execute('ROLLBACK TO ' + name); project.db.execute('RELEASE ' + name)
            raise
        else:project.db.execute('RELEASE ' + name)


class SnippetLinksMixin:
    def _snippet_record(self, object_id, kind):
        _id(object_id, kind)
        row = self.db.execute('SELECT * FROM snippet_objects WHERE id=?', (object_id,)).fetchone()
        if row is None:raise ValueError('unknown ' + kind + ' ID')
        try:document = json.loads(row['document'])
        except (ValueError, TypeError) as exc:raise ValueError('stored document is corrupt') from exc
        if type(document) is not dict:raise ValueError('stored immutable document is not an object')
        identity, sha, _ = _identity(kind, document)
        if identity != object_id or sha != row['sha256'] or row['kind'] != kind or document.get('format') != _FORMATS[kind] or document.get('author') != row['author']:
            raise ValueError('stored immutable document digest mismatch')
        return row, document

    def _snippet_put(self, kind, document, local_version=None):
        from .project import now
        object_id, sha, encoded = _identity(kind, document)
        if self.db.execute('SELECT 1 FROM snippet_objects WHERE id=?', (object_id,)).fetchone():
            previous, _ = self._snippet_record(object_id, kind)
            if local_version is not None and previous['local_version'] is None:
                self.db.execute('UPDATE snippet_objects SET local_version=? WHERE id=?', (local_version, object_id))
        else:self.db.execute('INSERT INTO snippet_objects VALUES (?,?,?,?,?,?,?)', (object_id, kind, sha, encoded, document['author'], now(), local_version))
        return dict(id=object_id, sha256=sha, document=json.loads(encoded))

    def _snippet_source(self):
        row = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()
        if row is None or row[0] is None:raise ValueError('retained original source bytes are unavailable')
        raw = bytes(row[0])
        if not 1 <= len(raw) <= MAX_SOURCE:raise ValueError('retained original source is outside the 64 MiB budget')
        if _sha(raw) != self.meta['source_sha256']:raise ValueError('retained original source digest mismatch')
        return raw

    def _snippet_context(self, context):
        context = self.context if context is None else _text(context, 'context')
        if self.meta['format'] in ('MZ', 'COM'):
            if not re.fullmatch(r'x86:16:little(?::cs=[0-9a-fA-F]{4})?', context):raise ValueError('invalid DOS snippet context')
        elif context != self.context:raise ValueError('snippet context does not match project image architecture/view')
        return context

    def capture_snippet(self, name, spans, version=None, context=None, boundary=None, evidence=None, author='agent'):
        name, author = _text(name, 'name', 128), _text(author, 'author')
        if type(spans) is not list or not 1 <= len(spans) <= MAX_SPANS:raise ValueError('snippet requires 1..256 ordered spans')
        context = self._snippet_context(context)
        with _atomic(self):
            v = self.version(version); regions = self.regions(v['id'])
            if self.digest(regions) != v['sha256']:raise ValueError('stored byte-version digest mismatch')
            original = self._snippet_source(); original_sha = self.meta['source_sha256']
            mappings = self._document(v['id']).get('file_mappings', [])
            if self.meta['format'] in ('MZ', 'COM'):
                selectors = {self._dos_parse_address(part['address'])[1] for part in spans if type(part) is dict and 'address' in part}
                selectors.discard(None)
                if len(selectors) > 1:raise ValueError('capture requires one exact DOS decode context')
                if selectors:
                    inferred = f'x86:16:little:cs={selectors.pop():04x}'
                    if context != self.context and context != inferred:raise ValueError('span CS conflicts with explicit context')
                    context = inferred
            parts, payloads, total = [], [], 0
            for index, requested in enumerate(spans):
                if type(requested) is not dict:raise ValueError('span must be an object')
                size = _integer(requested.get('size'), 'span size', 1, MAX_BYTES); total += size
                if total > MAX_BYTES:raise ValueError('snippet exceeds the 16 MiB captured-byte limit')
                if set(requested) == {'address', 'size'}:
                    a = self._address(requested['address'])
                    if self.meta['format'] in ('MZ', 'COM'):
                        a, selector = self._dos_parse_address(requested['address'])
                        if selector is not None:
                            inferred = f'x86:16:little:cs={selector:04x}'
                            if context != self.context and context != inferred:raise ValueError('span CS conflicts with explicit context')
                            context = inferred
                        if ':cs=' in context:
                            cs = int(context.rsplit('=', 1)[1], 16)
                            if not 0 <= a - cs * 16 < 65536 or a - cs * 16 + size > 65536:raise ValueError('DOS span crosses explicit CS offset bounds')
                    if self.meta['format'] == 'NE' and (a & 65535) + size > 65536:raise ValueError('NE span crosses a logical segment boundary')
                    if a + size > 1 << 64:raise ValueError('mapped span exceeds address bounds')
                    raw = _mapped_bytes(regions, a, size)
                    part = dict(space='mapped', address=a, size=size, sha256=_sha(raw), backing=None)
                    offsets = {m['file_offset'] + a - m['virtual_address'] for m in mappings if m.get('virtual_address') is not None and m['virtual_address'] <= a and a + size <= m['virtual_address'] + m.get('file_size', 0)}
                    intersects = any(m.get('virtual_address') is not None and m.get('file_size', 0) and m['virtual_address'] < a + size and m['virtual_address'] + m['file_size'] > a for m in mappings)
                    if intersects and not offsets:raise ValueError('split spans at source-file mapping/allocation boundaries')
                    if len(offsets) > 1:raise ValueError('snippet source-file mapping is ambiguous')
                    if offsets:
                        offset = offsets.pop()
                        if not 0 <= offset <= len(original) - size:raise ValueError('source mapping exceeds retained original bytes')
                        backing = original[offset:offset + size]
                        part['backing'] = dict(file='source', file_sha256=original_sha, file_offset=offset, size=size, sha256=_sha(backing))
                        payloads.append((index, 'source', backing))
                    if self.meta['format'] == 'NE':
                        from .ne import logical_location
                        part['logical_location'] = logical_location(a)
                elif set(requested) == {'file', 'offset', 'size'}:
                    offset = _integer(requested['offset'], 'file offset'); file = _text(requested['file'], 'file', 128)
                    if file == 'source':data, file_sha = original, original_sha
                    else:
                        metadata = self._external_file(v['id'], file)
                        data = bytes(self.db.execute('SELECT data FROM external_files WHERE version=? AND name=?', (v['id'], file)).fetchone()[0]); file_sha = metadata['sha256']
                        if _sha(data) != file_sha:raise ValueError('attached file digest mismatch')
                    if offset + size > len(data):raise ValueError('snippet span exceeds retained file bytes')
                    raw = data[offset:offset + size]
                    part = dict(space='file', file=file, offset=offset, size=size, sha256=_sha(raw), file_sha256=file_sha, backing=None)
                else:raise ValueError('span must be exactly {address,size} or {file,offset,size}')
                parts.append(part); payloads.append((index, 'bytes', raw))
            document = dict(format=_FORMATS['snippet'], name=name, author=author, context=context,
                source=dict(source_sha256=original_sha, version=v['id'], version_sha256=v['sha256'], image_format=self.meta['format'], image_view=self.meta['loader_metadata'].get('selected_image'), arch=self.arch, bits=self.bits, endian='little'),
                spans=parts, boundary=dict(status='authored', description=boundary), evidence=evidence)
            receipt = self._snippet_put('snippet', document, v['id'])
            self._snippet_store_payloads(receipt['id'], document, payloads)
            return receipt

    def _snippet_store_payloads(self, object_id, document, payloads):
        for index, role, raw in payloads:
            expected = document['spans'][index] if role == 'bytes' else document['spans'][index]['backing']
            if expected is None or len(raw) != expected['size'] or _sha(raw) != expected['sha256']:raise ValueError('snippet payload digest/extent mismatch')
            old = self.db.execute('SELECT data FROM snippet_payloads WHERE object_id=? AND span=? AND role=?', (object_id, index, role)).fetchone()
            if old is not None and bytes(old[0]) != raw:raise ValueError('immutable snippet payload conflict')
            self.db.execute('INSERT OR IGNORE INTO snippet_payloads VALUES (?,?,?,?)', (object_id, index, role, raw))

    def _snippet_checked(self, object_id, include_bytes=False):
        row, document = self._snippet_record(object_id, 'snippet'); local = row['local_version'] is not None
        self._snippet_validate_endpoint(document)
        if local:
            v = self.version(row['local_version'])
            source = document['source']
            if source['version'] != v['id'] or source['arch'] != self.arch or source['bits'] != self.bits or source['image_format'] != self.meta['format'] or source['image_view'] != self.meta['loader_metadata'].get('selected_image'):
                raise ValueError('snippet local source identity mismatch')
            self._snippet_context(document['context'])
            regions = self.regions(v['id'])
            if self.digest(regions) != document['source']['version_sha256'] or v['sha256'] != document['source']['version_sha256']:raise ValueError('snippet bound byte-version digest mismatch')
            original = self._snippet_source()
            if _sha(original) != document['source']['source_sha256']:raise ValueError('snippet bound original source digest mismatch')
            files = {'source': (original, document['source']['source_sha256'])}
            for part in document['spans']:
                if part['space'] == 'mapped':
                    if _sha(_mapped_bytes(regions, part['address'], part['size'])) != part['sha256']:raise ValueError('snippet mapped source span digest mismatch')
                    if part['backing'] is not None:
                        b = part['backing']; raw = original[b['file_offset']:b['file_offset'] + b['size']]
                        if len(raw) != b['size'] or _sha(raw) != b['sha256']:raise ValueError('snippet original backing digest mismatch')
                else:
                    file = part['file']
                    if file not in files:
                        metadata = self._external_file(v['id'], file)
                        raw = bytes(self.db.execute('SELECT data FROM external_files WHERE version=? AND name=?', (v['id'], file)).fetchone()[0])
                        if _sha(raw) != metadata['sha256']:raise ValueError('attached source digest mismatch')
                        files[file] = raw, metadata['sha256']
                    raw, sha = files[file]
                    captured = raw[part['offset']:part['offset'] + part['size']]
                    if sha != part['file_sha256'] or len(captured) != part['size'] or _sha(captured) != part['sha256']:raise ValueError('snippet file source digest mismatch')
        rows = self.db.execute('SELECT * FROM snippet_payloads WHERE object_id=?', (object_id,)).fetchall()
        payloads = {(r['span'], r['role']): bytes(r['data']) for r in rows}
        expected = {(i, 'bytes') for i in range(len(document['spans']))} | {(i, 'source') for i, p in enumerate(document['spans']) if p['backing'] is not None}
        available = set(payloads) == expected
        if payloads and not available or local and not available:raise ValueError('snippet payload inventory mismatch')
        for (index, role), raw in payloads.items():
            part = document['spans'][index] if role == 'bytes' else document['spans'][index]['backing']
            if part is None or len(raw) != part['size'] or _sha(raw) != part['sha256']:raise ValueError('stored snippet payload digest mismatch')
        if include_bytes:
            if not available:raise ValueError('raw bytes unavailable for external endpoint; supply explicit full payloads')
            for index, part in enumerate(document['spans']):
                part['bytes_hex'] = payloads[(index, 'bytes')].hex()
                if part['backing'] is not None:part['source_bytes_hex'] = payloads[(index, 'source')].hex()
        return row, document, dict(binding_status='local-source-verified' if local else 'external-endpoint-declaration', payload_available=available)

    @staticmethod
    def _snippet_view(row, document, full=False, **status):
        result = dict(id=row['id'], sha256=row['sha256'], kind=row['kind'], name=document['name'], author=row['author'], created=row['created'], **status)
        if row['local_version'] is not None:result['version'] = row['local_version']
        if full:result['document'] = document
        return result

    def snippet_info(self, snippet, full=False, include_bytes=False):
        if type(full) is not bool or type(include_bytes) is not bool:raise ValueError('full/include_bytes must be boolean')
        with self.transaction():
            row, doc, status = self._snippet_checked(snippet, include_bytes)
            return self._snippet_view(row, doc, full or include_bytes, **status)

    @staticmethod
    def _snippet_validate_endpoint(document):
        if type(document) is not dict or document.get('format') != _FORMATS['snippet']:raise ValueError('invalid portable snippet format')
        if set(document) != {'format', 'name', 'author', 'context', 'source', 'spans', 'boundary', 'evidence'}:raise ValueError('unsupported portable snippet fields')
        for field in ('name', 'author', 'context'):_text(document.get(field), field)
        source = document.get('source')
        if type(source) is not dict or any(not isinstance(source.get(f), str) or not _HASH.fullmatch(source[f]) for f in ('source_sha256', 'version_sha256')):raise ValueError('portable snippet requires source and byte-version digests')
        _integer(source.get('version'), 'source version', 1)
        if set(source) != {'source_sha256', 'version', 'version_sha256', 'image_format', 'image_view', 'arch', 'bits', 'endian'}:raise ValueError('invalid portable source fields')
        _text(source.get('image_format'), 'image format', 32); _text(source.get('arch'), 'architecture', 32)
        _integer(source.get('bits'), 'architecture bits', 1, 128)
        if source.get('endian') != 'little' or source.get('image_view') is not None and source['image_view'] not in ('mz', 'com', 'pe', 'le', 'ne'):raise ValueError('invalid source image view/endian')
        expected_view = {'MZ': 'mz', 'COM': 'com', 'PE': 'pe', 'NE': 'ne', 'LE': 'le'}.get(source['image_format'])
        if source['image_view'] is not None and source['image_view'] != expected_view:raise ValueError('source format/view mismatch')
        if type(document['boundary']) is not dict or document['boundary'].get('status') != 'authored':raise ValueError('snippet boundaries must remain authored declarations')
        base_context = f"{source['arch']}:{source['bits']}:little"
        if source['image_format'] == 'NE':
            if source['arch'] != 'x86' or source['bits'] != 16 or source['image_view'] != 'ne' or document['context'] != base_context + ':ne':raise ValueError('invalid portable NE decode context')
        elif source['image_format'] in ('MZ', 'COM'):
            if source['arch'] != 'x86' or source['bits'] != 16 or not re.fullmatch(r'x86:16:little(?::cs=[0-9a-fA-F]{4})?', document['context']):raise ValueError('invalid portable DOS decode context')
        elif document['context'] != base_context:raise ValueError('portable context does not match source architecture')
        parts = document.get('spans')
        if type(parts) is not list or not 1 <= len(parts) <= MAX_SPANS:raise ValueError('invalid portable span count')
        total = 0
        for part in parts:
            if type(part) is not dict or part.get('space') not in ('mapped', 'file'):raise ValueError('invalid portable span')
            total += _integer(part.get('size'), 'span size', 1, MAX_BYTES)
            allowed = {'space', 'size', 'sha256', 'backing', 'bytes_hex', 'source_bytes_hex'}
            allowed |= {'address', 'logical_location'} if part['space'] == 'mapped' else {'file', 'offset', 'file_sha256'}
            if not set(part) <= allowed or 'backing' not in part:raise ValueError('invalid portable span fields')
            if not isinstance(part.get('sha256'), str) or not _HASH.fullmatch(part['sha256']):raise ValueError('invalid span digest')
            if part['space'] == 'mapped':
                _integer(part.get('address'), 'mapped address')
                if part['address'] + part['size'] > 1 << 64:raise ValueError('portable mapped extent exceeds address bounds')
                if source['image_format'] in ('MZ', 'COM') and ':cs=' in document['context']:
                    cs = int(document['context'].rsplit('=', 1)[1], 16)
                    if not 0 <= part['address'] - cs * 16 < 65536 or part['address'] - cs * 16 + part['size'] > 65536:raise ValueError('portable DOS span exceeds CS bounds')
                if source['image_format'] == 'NE':
                    from .ne import logical_location
                    if not 0x10000 <= part['address'] <= 0xffffffff or (part['address'] & 65535) + part['size'] > 65536 or part.get('logical_location') != logical_location(part['address']):raise ValueError('invalid portable NE logical identity')
            else:
                _text(part.get('file'), 'file', 128); _integer(part.get('offset'), 'file offset')
                from .external_files import _file_name
                _file_name(part['file'])
                if not _HASH.fullmatch(str(part.get('file_sha256', ''))) or part['file'] == 'source' and part['file_sha256'] != source['source_sha256']:raise ValueError('invalid file source digest')
                if part['offset'] + part['size'] > MAX_SOURCE:raise ValueError('portable file extent exceeds source budget')
            if part.get('backing') is not None:
                b = part['backing']
                if type(b) is not dict or b.get('size') != part['size'] or not _HASH.fullmatch(str(b.get('sha256', ''))) or not _HASH.fullmatch(str(b.get('file_sha256', ''))):raise ValueError('invalid portable source backing')
                _integer(b.get('file_offset'), 'source file offset')
                if b['file_offset'] + b['size'] > MAX_SOURCE:raise ValueError('portable original backing exceeds source budget')
                if set(b) != {'file', 'file_sha256', 'file_offset', 'size', 'sha256'} or b['file'] != 'source' or b['file_sha256'] != source['source_sha256']:raise ValueError('invalid portable original backing identity')
        if total > MAX_BYTES:raise ValueError('portable snippet exceeds captured-byte budget')

    def _snippet_endpoint(self, value):
        if isinstance(value, str):
            _, document, _ = self._snippet_checked(value)
            return dict(id=value, sha256=value.split(':')[1], document=document), []
        if type(value) is not dict or not {'id', 'sha256', 'document'} <= set(value):raise ValueError('endpoint requires a snippet ID or full portable receipt')
        if type(value['document']) is not dict:raise ValueError('portable endpoint document must be an object')
        document, payloads = dict(value['document']), []
        if type(document.get('spans')) is not list or not 1 <= len(document['spans']) <= MAX_SPANS:raise ValueError('invalid portable span count')
        document['spans'] = [dict(part) if type(part) is dict else part for part in document['spans']]
        for index, part in enumerate(document['spans']):
            if type(part) is not dict:raise ValueError('invalid portable span')
            for field, role in (('bytes_hex', 'bytes'), ('source_bytes_hex', 'source')):
                if field in part:
                    encoded = part.pop(field)
                    expected = part if role == 'bytes' else part.get('backing')
                    if type(expected) is not dict:raise ValueError('invalid explicit payload backing')
                    size = _integer(expected.get('size'), 'payload size', 1, MAX_BYTES)
                    if not isinstance(encoded, str) or len(encoded) != 2 * size:raise ValueError('explicit payload extent mismatch')
                    payloads.append((index, role, encoded))
        document = json.loads(_canonical(document))
        self._snippet_validate_endpoint(document)
        try:payloads = [(index, role, bytes.fromhex(encoded)) for index, role, encoded in payloads]
        except (TypeError, ValueError) as exc:raise ValueError('invalid explicit snippet payload') from exc
        identity, sha, _ = _identity('snippet', document)
        if identity != value['id'] or sha != value['sha256']:raise ValueError('portable endpoint digest mismatch')
        if payloads:
            expected = {(i, 'bytes') for i in range(len(document['spans']))} | {(i, 'source') for i, p in enumerate(document['spans']) if p['backing'] is not None}
            if {(i, role) for i, role, raw in payloads} != expected:raise ValueError('explicit endpoint payloads must be complete')
        return dict(id=identity, sha256=sha, document=document), payloads

    def link_snippets(self, sources, targets, kind, domain, evidence, assurance='candidate', adapters=None, unknowns=None, author='agent', name=None):
        _text(kind, 'relation kind', 128); _text(author, 'author')
        if type(domain) is not dict or not domain:raise ValueError('relation requires an explicit admitted domain object')
        if not isinstance(evidence, (str, dict, list)) or not evidence or not isinstance(assurance, (str, dict)) or not assurance:raise ValueError('relation requires explicit evidence and assurance')
        if any(type(side) is not list or not 1 <= len(side) <= MAX_SPANS for side in (sources, targets)):raise ValueError('relation requires bounded nonempty endpoint lists')
        with _atomic(self):
            endpoints = [self._snippet_endpoint(item) for item in sources + targets]
            for endpoint, payloads in endpoints:
                self._snippet_put('snippet', endpoint['document']); self._snippet_store_payloads(endpoint['id'], endpoint['document'], payloads)
            document = dict(format=_FORMATS['link'], name=_text(name or kind, 'name', 128), author=author,
                sources=[x[0]['id'] for x in endpoints[:len(sources)]], targets=[x[0]['id'] for x in endpoints[len(sources):]],
                relation=kind, domain=domain, evidence=evidence, assurance=assurance, adapters=adapters or [], unknowns=unknowns or [], assertion_status='authored-declaration')
            return self._snippet_put('link', document)

    def _snippet_register(self, kind, document, author=None):
        if type(document) is not dict:raise ValueError('document must be an object')
        document = json.loads(_canonical(document)); author = document.get('author', 'agent') if author is None else author
        _text(author, 'author')
        if 'author' in document and document['author'] != author:raise ValueError('explicit author conflicts with immutable document author')
        document['author'] = author
        if document.get('format') != _FORMATS[kind]:raise ValueError('invalid ' + kind + ' document format')
        _text(document.get('name'), 'name', 128); _canonical(document)
        with _atomic(self):
            if kind == 'contract':
                for field in ('inputs', 'outputs'):
                    typed = document.get(field)
                    if type(typed) is not dict or len(typed) > 256 or any(not isinstance(t, (str, dict)) or not t for t in typed.values()):raise ValueError('contract inputs/outputs must be bounded typed maps')
                    for port in typed:_text(port, 'typed port', 128)
                if type(document.get('behavior')) is not dict or not document['behavior']:raise ValueError('contract requires a behavior descriptor')
            elif kind == 'layer':
                self._snippet_document_info('contract', document.get('contract'), True)
                if type(document.get('implementation')) is not dict or not document['implementation']:raise ValueError('layer requires an implementation descriptor')
                if 'adapter' in document and type(document['adapter']) is not dict:raise ValueError('layer adapter must be a descriptor object')
                if document.get('snippet') is not None:self._snippet_checked(document['snippet'])
            elif kind == 'selection':
                bindings = document.get('bindings')
                if type(bindings) is not dict or not 1 <= len(bindings) <= 256:raise ValueError('selection requires bounded exact layer bindings')
                for slot, layer in bindings.items():_text(slot, 'logical slot', 128); self._snippet_document_info('layer', layer, True)
            return self._snippet_put(kind, document)

    def store_contract(self, document, author=None):return self._snippet_register('contract', document, author)
    def store_udl_layer(self, document, author=None):return self._snippet_register('layer', document, author)
    def store_udl_selection(self, document, author=None):return self._snippet_register('selection', document, author)

    def _snippet_document_info(self, kind, object_id, full=False):
        if type(full) is not bool:raise ValueError('full must be boolean')
        with self.transaction():
            row, document = self._snippet_record(object_id, kind)
            if kind == 'layer':
                self._snippet_record(document['contract'], 'contract')
                if document.get('snippet') is not None:self._snippet_checked(document['snippet'])
            elif kind == 'selection':
                for layer in set(document['bindings'].values()):self._snippet_document_info('layer', layer)
            elif kind == 'link':
                for endpoint in document['sources'] + document['targets']:self._snippet_checked(endpoint)
            return self._snippet_view(row, document, full)

    def contract_info(self, contract, full=False):return self._snippet_document_info('contract', contract, full)
    def udl_layer_info(self, layer, full=False):return self._snippet_document_info('layer', layer, full)
    def udl_selection_info(self, selection, full=False):return self._snippet_document_info('selection', selection, full)
    def snippet_link_info(self, link, full=False):return self._snippet_document_info('link', link, full)

    def _snippet_list(self, kind, version=None, limit=200, offset=0, full=False):
        _integer(limit, 'limit', 1, 10000); _integer(offset, 'offset', 0, (1 << 63) - 1)
        if type(full) is not bool:raise ValueError('full must be boolean')
        with self.transaction():
            query, params = 'kind=?', [kind]
            if version is not None:query += ' AND local_version=?'; params.append(self.version(version)['id'])
            total = self.db.execute('SELECT count(*) FROM snippet_objects WHERE ' + query, params).fetchone()[0]
            rows = self.db.execute('SELECT id FROM snippet_objects WHERE ' + query + ' ORDER BY created,id LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
            items = [self.snippet_info(r[0], full=full) if kind == 'snippet' else self._snippet_document_info(kind, r[0], full) for r in rows]
            return dict(items=items, total=total, offset=offset, has_more=offset + len(items) < total)

    def snippets(self, version=None, limit=200, offset=0, full=False):return self._snippet_list('snippet', version, limit, offset, full)
    def snippet_links(self, limit=200, offset=0, full=False):return self._snippet_list('link', None, limit, offset, full)
    def contracts(self, limit=200, offset=0, full=False):return self._snippet_list('contract', None, limit, offset, full)
    def udl_layers(self, limit=200, offset=0, full=False):return self._snippet_list('layer', None, limit, offset, full)
    def udl_selections(self, limit=200, offset=0, full=False):return self._snippet_list('selection', None, limit, offset, full)
