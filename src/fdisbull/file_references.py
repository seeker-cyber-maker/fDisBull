"""Authored links between instruction identities and independent file offsets.

These are evidence annotations, not recovered runtime mappings. They never
inject resource bytes into native memory or contribute control-flow edges.
"""
from .dos_views import _segmented

FILE_REFERENCES_DDL = """
CREATE TABLE IF NOT EXISTS file_references(
 version INTEGER NOT NULL,context TEXT NOT NULL,source TEXT NOT NULL,
 file TEXT NOT NULL,file_offset INTEGER NOT NULL,width INTEGER NOT NULL,
 count INTEGER NOT NULL,stride INTEGER NOT NULL,access TEXT NOT NULL,
 instruction_bytes TEXT NOT NULL,evidence TEXT NOT NULL,author TEXT NOT NULL,
 PRIMARY KEY(version,context,source,file,file_offset));
CREATE INDEX IF NOT EXISTS file_references_target ON file_references(version,file,file_offset);
"""


class FileReferencesMixin:
    def _file_reference_view(self, v, row, max_locations=16):
        source = int(row['source'], 16)
        instruction = self.db.execute(
            'SELECT bytes FROM instructions WHERE version=? AND context=? AND address=?',
            (v, row['context'], row['source'])).fetchone()
        original = bytes.fromhex(row['instruction_bytes'])
        region = self._mapping(v, source)
        current = (region.data[source-region.start:source-region.start+len(original)]
                   if region else b'')
        stale = current != original
        active = bool(not stale and instruction and instruction['bytes'] == row['instruction_bytes'])
        locations = []
        for index in range(min(row['count'], max_locations)):
            offset = row['file_offset'] + index * row['stride']
            location = self._file_type_location(v, row['file'], offset)
            locations.append(dict(file_offset=offset, width=row['width'], type=location,
                                  name=location['name'] if location else f"{row['file']}+0x{offset:x}"))
        metadata = self._external_file(v, row['file'])
        return dict(source=hex(source), context=row['context'],
                    segmented_address=_segmented(source, row['context']),
                    file=row['file'], file_sha256=metadata['sha256'],
                    file_offset=row['file_offset'], width=row['width'], count=row['count'],
                    stride=row['stride'], access=row['access'], locations=locations,
                    locations_truncated=row['count'] > len(locations),
                    extent_end_exclusive=row['file_offset']+(row['count']-1)*row['stride']+row['width'],
                    active=active, stale=stale,
                    state='stale_bytes' if stale else 'active' if active else 'awaiting_decode',
                    evidence=row['evidence'], author=row['author'],
                    instruction_bytes=row['instruction_bytes'], runtime_observed=False,
                    identity_basis='authored_file_reference',
                    scope='Declared file-offset relationship; no runtime memory mapping or execution is inferred.')

    def file_reference(self, address, file, offset=0, width=1, count=1, stride=None,
                       access='unknown', evidence=None, cs=None, version=None, author='agent'):
        from .project import integer, key, number
        offset = number(offset)
        width = integer(width, 'width', 1, 1 << 20)
        count = integer(count, 'count', 1, 4096)
        stride = width if stride is None else integer(stride, 'stride', 1, 1 << 20)
        if access not in ('read', 'write', 'read_write', 'address', 'unknown'):
            raise ValueError('access must be read, write, read_write, address or unknown')
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 4096:
            raise ValueError('evidence must contain 1..4096 characters explaining this relationship')
        if not isinstance(author, str) or not author.strip() or len(author) > 256:
            raise ValueError('author must contain 1..256 characters')
        with self.transaction(True):
            v = self.version(version)['id']
            attached = self._external_file(v, file)
            if offset+(count-1)*stride+width > attached['size']:
                raise ValueError('file reference exceeds attached file bytes')
            if self.meta['format'] == 'MZ':
                a, selector = self._dos_parse_address(address, cs)
                rows = self.db.execute('SELECT context,bytes FROM instructions WHERE version=? AND address=?',
                                       (v, key(a))).fetchall()
                if selector is not None:
                    rows = [r for r in rows if r['context'] == f'x86:16:little:cs={selector:04x}']
                if len(rows) > 1:
                    raise ValueError('source has multiple CS interpretations; specify cs or CS:IP')
            else:
                if cs is not None:raise ValueError('cs applies only to DOS MZ projects')
                a = number(address)
                rows = self.db.execute('SELECT context,bytes FROM instructions WHERE version=? AND context=? AND address=?',
                                       (v, self.context, key(a))).fetchall()
            if not rows:raise ValueError('file reference requires an exact stored instruction identity')
            context, raw = rows[0]['context'], rows[0]['bytes']
            self.db.execute('INSERT OR REPLACE INTO file_references VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (v, context, key(a), file, offset, width, count, stride, access, raw, evidence, author))
            row = self.db.execute('SELECT * FROM file_references WHERE version=? AND context=? AND source=? AND file=? AND file_offset=?',
                                  (v, context, key(a), file, offset)).fetchone()
            return dict(version=v, reference=self._file_reference_view(v, row))

    def file_xrefs(self, file, offset=0, size=1, version=None, limit=200,
                   page_offset=0, include_stale=True):
        from .project import integer, number
        offset = number(offset)
        size = integer(size, 'size', 1, 64 << 20)
        limit = integer(limit, 'limit', 1, 10000)
        page_offset = integer(page_offset, 'page_offset', 0, (1 << 63)-1)
        if not isinstance(include_stale, bool):raise ValueError('include_stale must be boolean')
        with self.transaction():
            v = self.version(version)['id']
            attached = self._external_file(v, file)
            if offset+size > attached['size']:raise ValueError('query exceeds attached file bytes')
            items = [];total = 0
            rows = self.db.execute('SELECT * FROM file_references WHERE version=? AND file=? AND file_offset<? ORDER BY source,context,file_offset',
                                   (v, file, offset+size))
            for row in rows:
                # Exact strided intervals: bytes between elements are not hits.
                low = max(0, (offset-row['file_offset']-row['width'])//row['stride']+1)
                high = min(row['count']-1, (offset+size-1-row['file_offset'])//row['stride'])
                if low > high:continue
                view = self._file_reference_view(v, row)
                if not include_stale and not view['active']:continue
                if page_offset <= total < page_offset+limit:
                    view['matched_elements'] = dict(first=low, last=high)
                    items.append(view)
                total += 1
            return dict(version=v, file=file, file_offset=offset, size=size,
                        sha256=attached['sha256'], items=items, total=total,
                        page_offset=page_offset, has_more=page_offset+len(items)<total,
                        scope='Authored file-offset references, not native xrefs or observed I/O.')

    def _file_reference_display(self, v, context, address, display):
        from .project import key
        total=self.db.execute('SELECT COUNT(*) FROM file_references WHERE version=? AND context=? AND source=?',
                              (v,context,key(address))).fetchone()[0]
        rows = self.db.execute('SELECT * FROM file_references WHERE version=? AND context=? AND source=? ORDER BY file,file_offset LIMIT 8',
                               (v, context, key(address))).fetchall()
        views = [self._file_reference_view(v, row, max_locations=4) for row in rows]
        labels = []
        for item in views:
            if not item['active']:continue
            label = item['locations'][0]['name']
            if len(label)>160:label=label[:157]+'...'
            if item['count'] > 1:label += f" (+{item['stride']} stride, {item['count']} elements)"
            labels.append(f"file {item['file']}+0x{item['file_offset']:x}: {label} [authored]")
            if len(labels)==3:break
        if total>len(labels):labels.append(f'{total-len(labels)} additional file references; use file-xrefs')
        return display+(' ; '+', '.join(labels) if labels else ''), views, dict(total=total,returned=len(views),truncated=total>len(views))
