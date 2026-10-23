"""Authored byte correspondences and shared labels, independent of ISA/container.

Links identify corresponding fields, not equal values or live runtime pointers.
Names are resolved when queried, never substituted into decoded facts.
"""
from collections import deque
from contextlib import contextmanager

SHARED_LABELS_DDL = """
CREATE TABLE IF NOT EXISTS label_links(
 version INTEGER NOT NULL,id INTEGER NOT NULL,
 left_space TEXT NOT NULL,left_file TEXT NOT NULL,left_offset TEXT NOT NULL,left_last TEXT NOT NULL,
 right_space TEXT NOT NULL,right_file TEXT NOT NULL,right_offset TEXT NOT NULL,right_last TEXT NOT NULL,
 size INTEGER NOT NULL,evidence TEXT NOT NULL,author TEXT NOT NULL,
 PRIMARY KEY(version,id));
CREATE INDEX IF NOT EXISTS label_links_left ON label_links(version,left_space,left_file,left_offset);
CREATE INDEX IF NOT EXISTS label_links_right ON label_links(version,right_space,right_file,right_offset);
CREATE TABLE IF NOT EXISTS shared_label_names(
 version INTEGER NOT NULL,space TEXT NOT NULL,file TEXT NOT NULL,offset TEXT NOT NULL,
 name TEXT NOT NULL,author TEXT NOT NULL,created TEXT NOT NULL,
 PRIMARY KEY(version,space,file,offset));
CREATE TABLE IF NOT EXISTS label_link_removals(
 version INTEGER NOT NULL,link_id INTEGER NOT NULL,reason TEXT NOT NULL,
 author TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(version,link_id));
"""

MAX_LABEL_MEMBERS = 256
MAX_LABEL_LINKS = 4096


def _name(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 256
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        raise ValueError('label must contain 1..256 characters without controls')
    return value


class SharedLabelsMixin:
    @contextmanager
    def _label_transaction(self):
        # Preserve atomicity even if a caller catches a failed merge inside its
        # own larger transaction. Project.transaction alone reuses that scope.
        with self.transaction(True):
            self.db.execute('SAVEPOINT shared_label_edit')
            try:
                yield
            except BaseException:
                self.db.execute('ROLLBACK TO shared_label_edit')
                self.db.execute('RELEASE shared_label_edit')
                raise
            else:
                self.db.execute('RELEASE shared_label_edit')

    def _label_endpoint(self, v, endpoint, size=1):
        from .project import key, number
        if not isinstance(endpoint, dict):
            raise ValueError('label endpoint must be {file,offset} or {address}')
        if set(endpoint) == {'address'}:
            offset = self._address(endpoint['address'])
            region = self._mapping(v, offset)
            if region is None or offset + size > region.start + len(region.data):
                raise ValueError('label endpoint must fit in one mapped region')
            return ('memory', '', offset)
        if set(endpoint) == {'file', 'offset'}:
            metadata = self._external_file(v, endpoint['file'])
            offset = number(endpoint['offset'])
            if offset + size > metadata['size']:
                raise ValueError('label endpoint exceeds attached file bytes')
            return ('file', metadata['name'], offset)
        raise ValueError('label endpoint must be exactly {file,offset} or {address}')

    @staticmethod
    def _endpoint_view(point):
        space, file, offset = point
        return dict(file=file, offset=offset) if space == 'file' else dict(address=hex(offset))

    def _label_component(self, v, point):
        from .project import key
        queue, seen, edges, positions = deque([point]), {point}, {}, {}
        while queue:
            space, file, offset = queue.popleft()
            location = key(offset)
            rows = self.db.execute(
                'SELECT l.* FROM label_links l WHERE l.version=? AND '
                'NOT EXISTS (SELECT 1 FROM label_link_removals r WHERE r.version=l.version AND r.link_id=l.id) AND '
                '((left_space=? AND left_file=? AND left_offset<=? AND left_last>=?) OR '
                '(right_space=? AND right_file=? AND right_offset<=? AND right_last>=?))',
                (v, space, file, location, location, space, file, location, location))
            for row in rows:
                edges[row['id']] = row
                for side, other in (('left', 'right'), ('right', 'left')):
                    if row[side+'_space'] != space or row[side+'_file'] != file:
                        continue
                    relative = offset - int(row[side+'_offset'], 16)
                    if not 0 <= relative < row['size']:
                        continue
                    identity = (row['id'], side)
                    if identity in positions and positions[identity] != relative:
                        raise ValueError('contradictory label links: offset cycle aliases different bytes of a range')
                    positions[identity] = relative
                    target = (row[other+'_space'], row[other+'_file'],
                              int(row[other+'_offset'], 16) + relative)
                    if target not in seen:
                        if len(seen) >= MAX_LABEL_MEMBERS:
                            raise ValueError('label component exceeds 256 corresponding locations')
                        seen.add(target)
                        queue.append(target)
        return sorted(seen), [edges[n] for n in sorted(edges)]

    def _component_names(self, v, members):
        from .project import key
        result = []
        for space, file, offset in members:
            row = self.db.execute(
                'SELECT * FROM shared_label_names WHERE version=? AND space=? AND file=? AND offset=?',
                (v, space, file, key(offset))).fetchone()
            if row:
                result.append(row)
        return result

    def _fallback_label(self, v, members):
        from .project import key
        for space, file, offset in members:
            if space == 'memory':
                row = self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",
                                      (v, self.context, key(offset))).fetchone()
                if row:
                    return row[0]
        # Structural paths remain live: revising a type also changes linked views.
        for space, file, offset in members:
            if space == 'file':
                location = self._raw_file_type_location(v, file, offset)
                if location:
                    return location['name']
        for space, file, offset in members:
            if space == 'memory':
                location = self._raw_type_location(v, offset)
                if location:
                    return location['name']
        for space, file, offset in members:
            if space == 'file':
                return f'{file}+0x{offset:x}'
        from .project import key
        address = members[0][2]
        row = self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",
                              (v, self.context, key(address))).fetchone()
        if row:
            return row[0]
        if self.meta['format'] == 'MZ':
            from .dos_views import DOSViewsMixin
            return DOSViewsMixin._dos_label(self,v,address)
        from .analysis import AnalysisMixin
        return AnalysisMixin._label(self,v,address)

    def _shared_name(self, v, point):
        members, links = self._label_component(v, point)
        names = self._component_names(v, members)
        if names:
            return names[0]['name']
        return self._fallback_label(v, members) if links else None

    def _set_shared_name(self, v, point, name, author):
        from .project import key, now
        name = _name(name)
        members, _ = self._label_component(v, point)
        for space, file, offset in members:
            self.db.execute('DELETE FROM shared_label_names WHERE version=? AND space=? AND file=? AND offset=?',
                            (v, space, file, key(offset)))
        space, file, offset = members[0]
        self.db.execute('INSERT INTO shared_label_names VALUES (?,?,?,?,?,?,?)',
                        (v, space, file, key(offset), name, author, now()))

    def _native_is_shared(self, v, address):
        members, links = self._label_component(v, ('memory', '', address))
        return bool(links or self._component_names(v, members))

    def _effect_labels(self, v, effect):
        from .project import number
        shown = dict(effect)
        target = effect.get('address')
        shown['target_name'] = self._label(v, target) if isinstance(target, int) else None
        for field in ('call_site', 'callee'):
            address = effect.get(field)
            if isinstance(address, (int,str)):
                shown[field+'_name'] = self._label(v, number(address))
        return shown

    def _rename_linked_native(self, v, address, name, author):
        point = ('memory', '', address)
        members, links = self._label_component(v, point)
        if links or self._component_names(v, members):
            self._set_shared_name(v, point, name, author)

    def link_labels(self, left, right, size=1, evidence=None, name=None, version=None, author='agent'):
        from .project import integer, key, now
        from .external_files import _author
        size = integer(size, 'size', 1, 1 << 20)
        author = _author(author)
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 4096:
            raise ValueError('evidence must contain 1..4096 characters explaining the field correspondence')
        if name is not None:
            _name(name)
        with self._label_transaction():
            v = self.version(version)['id']
            a, b = self._label_endpoint(v, left, size), self._label_endpoint(v, right, size)
            if a == b:
                raise ValueError('label endpoints must be different locations')
            rows = self.db.execute('SELECT * FROM label_links WHERE version=? ORDER BY id', (v,)).fetchall()
            removed = {r[0] for r in self.db.execute('SELECT link_id FROM label_link_removals WHERE version=?', (v,))}
            duplicate = next((r for r in rows if r['id'] not in removed and r['size'] == size and
                ((a == (r['left_space'], r['left_file'], int(r['left_offset'], 16)) and
                  b == (r['right_space'], r['right_file'], int(r['right_offset'], 16))) or
                 (b == (r['left_space'], r['left_file'], int(r['left_offset'], 16)) and
                  a == (r['right_space'], r['right_file'], int(r['right_offset'], 16))))), None)
            if duplicate:
                if name is not None:
                    self._set_shared_name(v, a, name, author)
                return self.label_info(left, version=v)
            if len(rows) >= MAX_LABEL_LINKS:
                raise ValueError('version exceeds 4096 retained label links, including removed history')
            # Retain existing native labels as explicit choices before merging.
            # Earlier native annotations shadowed by a shared rename stay historical.
            annotations = self.db.execute(
                "SELECT * FROM annotations WHERE version=? AND context=? AND kind='name'",
                (v, self.context)).fetchall()
            if len(annotations) > 10000:
                raise ValueError('label validation exceeds 10000 native annotations')
            for row in annotations:
                point = ('memory', '', int(row['address'], 16))
                members, links = self._label_component(v, point)
                if not links and not any(point[:2] == p[:2] and p[2] <= point[2] < p[2]+size for p in (a, b)):
                    continue
                if not self._component_names(v, members):
                    self.db.execute('INSERT OR IGNORE INTO shared_label_names VALUES (?,?,?,?,?,?,?)',
                                    (v, *point[:2], row['address'], row['text'], row['author'], row['created']))
            identifier = max((r['id'] for r in rows), default=0) + 1
            self.db.execute('INSERT INTO label_links VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (v, identifier, a[0], a[1], key(a[2]), key(a[2]+size-1),
                 b[0], b[1], key(b[2]), key(b[2]+size-1), size, evidence, author))
            if name is not None:
                self._set_shared_name(v, a, name, author)
            rows = self.db.execute(
                'SELECT l.* FROM label_links l WHERE l.version=? AND '
                'NOT EXISTS (SELECT 1 FROM label_link_removals r WHERE r.version=l.version AND r.link_id=l.id)',
                (v,)).fetchall()
            probes = set()
            for row in rows:
                for side in ('left', 'right'):
                    for position in ('offset', 'last'):
                        probes.add((row[side+'_space'], row[side+'_file'], int(row[side+'_'+position], 16)))
            for row in self.db.execute('SELECT * FROM shared_label_names WHERE version=?', (v,)):
                probes.add((row['space'], row['file'], int(row['offset'], 16)))
            work = 0
            checked = set()
            for probe in sorted(probes):
                if probe in checked:
                    continue
                members, _ = self._label_component(v, probe)
                checked.update(members)
                work += len(members)
                if work > 100000:
                    raise ValueError('label link validation budget exhausted; split the correspondence')
                if len({r['name'] for r in self._component_names(v, members)}) > 1:
                    raise ValueError('conflicting explicit labels; resolve with name or rename the conflicting fields first')
            return self.label_info(left, version=v)

    def _label_link_view(self, v, row):
        removal = self.db.execute(
            'SELECT reason,author,created FROM label_link_removals WHERE version=? AND link_id=?',
            (v, row['id'])).fetchone()
        return dict(id=row['id'],
                    left=self._endpoint_view((row['left_space'],row['left_file'],int(row['left_offset'],16))),
                    right=self._endpoint_view((row['right_space'],row['right_file'],int(row['right_offset'],16))),
                    size=row['size'], evidence=row['evidence'], author=row['author'],
                    active=removal is None, removal=dict(removal) if removal else None)

    def label_links(self, version=None, include_removed=False, limit=200, offset=0):
        from .project import integer
        limit = integer(limit, 'limit', 1, 10000)
        offset = integer(offset, 'offset', 0, (1 << 63)-1)
        if not isinstance(include_removed, bool):
            raise ValueError('include_removed must be boolean')
        with self.transaction():
            v = self.version(version)['id']
            predicate = '' if include_removed else (
                ' AND NOT EXISTS (SELECT 1 FROM label_link_removals r WHERE r.version=l.version AND r.link_id=l.id)')
            total = self.db.execute('SELECT count(*) FROM label_links l WHERE l.version=?'+predicate, (v,)).fetchone()[0]
            rows = self.db.execute('SELECT l.* FROM label_links l WHERE l.version=?'+predicate+' ORDER BY l.id LIMIT ? OFFSET ?',
                                   (v, limit, offset)).fetchall()
            return dict(version=v, items=[self._label_link_view(v,row) for row in rows],
                        total=total, limit=limit, offset=offset, has_more=offset+len(rows)<total,
                        include_removed=include_removed)

    def unlink_labels(self, link_id, reason=None, version=None, author='agent'):
        from .project import integer, now
        from .external_files import _author
        link_id = integer(link_id, 'link_id', 1, (1 << 63)-1)
        author = _author(author)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 4096:
            raise ValueError('reason must contain 1..4096 characters explaining the removal')
        with self._label_transaction():
            v = self.version(version)['id']
            row = self.db.execute('SELECT * FROM label_links WHERE version=? AND id=?', (v, link_id)).fetchone()
            if row is None:
                raise ValueError('unknown label link in this version')
            link = self._label_link_view(v, row)
            left, right = link['left'], link['right']
            left_before = self.label_info(left, version=v)
            right_before = self.label_info(right, version=v)
            removed = link['active']
            if removed:
                self.db.execute('INSERT INTO label_link_removals VALUES (?,?,?,?,?)',
                                (v, link_id, reason, author, now()))
            left_after = self.label_info(left, version=v)
            right_after = self.label_info(right, version=v)
            return dict(version=v, removed=removed, link=self._label_link_view(v,row),
                        left=dict(before=left_before, after=left_after),
                        right=dict(before=right_before, after=right_after),
                        still_connected=right in left_after['members'],
                        connectivity_scope='starting_endpoints',
                        note='Only this range link is removed. Shared names stay at their stored anchors; '
                             'detached locations resolve remaining local labels/types. Independently authored '
                             'native names and instruction file references are preserved.')

    def rename_file(self, file, offset, name, version=None, author='agent'):
        from .external_files import _author
        author = _author(author)
        with self._label_transaction():
            v = self.version(version)['id']
            endpoint = dict(file=file, offset=offset)
            point = self._label_endpoint(v, endpoint)
            self._set_shared_name(v, point, name, author)
            return self.label_info(endpoint, version=v)

    def label_info(self, endpoint, version=None):
        with self.transaction():
            v = self.version(version)['id']
            point = self._label_endpoint(v, endpoint)
            members, links = self._label_component(v, point)
            names = self._component_names(v, members)
            return dict(version=v, endpoint=self._endpoint_view(point),
                        name=names[0]['name'] if names else self._fallback_label(v, members),
                        explicit=bool(names), label_author=names[0]['author'] if names else None,
                        label_anchor=self._endpoint_view((names[0]['space'],names[0]['file'],int(names[0]['offset'],16))) if names else None,
                        members=[self._endpoint_view(p) for p in members],
                        links=[self._label_link_view(v,r) for r in links],
                        runtime_observed=False,
                        scope='Authored field correspondence; values, pointer state, execution and native xrefs are not inferred.')

    def _label(self, v, a):
        return self._shared_name(v, ('memory', '', a)) or super()._label(v, a)

    def _dos_label(self, v, a, context=None):
        return self._shared_name(v, ('memory', '', a)) or super()._dos_label(v, a, context)

    def _type_location(self, v, a):
        location = self._raw_type_location(v, a)
        if location:
            location = {**location, 'name': self._shared_name(v, ('memory', '', a)) or location['name']}
        return location

    def _file_type_location(self, v, file, offset):
        location = self._raw_file_type_location(v, file, offset)
        if location:
            location = {**location, 'name': self._shared_name(v, ('file', file, offset)) or location['name']}
        return location

    def _file_label(self, v, file, offset):
        shared = self._shared_name(v, ('file', file, offset))
        location = self._raw_file_type_location(v, file, offset)
        return shared or (location['name'] if location else f'{file}+0x{offset:x}')

    def _presentation(self, v, a):
        shown = super()._presentation(v, a)
        return {**shown, 'name': self._label(v, a)}

    def _dos_presentation(self, v, a, context=None):
        shown = super()._dos_presentation(v, a, context)
        return {**shown, 'name': self._dos_label(v, a, context)}
