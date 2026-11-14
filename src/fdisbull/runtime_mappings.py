"""Source-bound runtime mapping history, never an implicit live address map.

Tasks are incarnations, not recyclable DOS task numbers. Each mapping is a
bounded object extent and an interval in an append-only observation journal.
Restoring a checkpoint records new intervals; it never rewrites history or RAM.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import uuid


RUNTIME_MAPPING_DDL = '''
CREATE TABLE IF NOT EXISTS runtime_mapping_tasks(
 id TEXT PRIMARY KEY, run TEXT NOT NULL, external_id TEXT NOT NULL,
 version INTEGER NOT NULL REFERENCES versions(id), started INTEGER NOT NULL,
 ended INTEGER, document TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS runtime_mapping_live_task
 ON runtime_mapping_tasks(run,external_id) WHERE ended IS NULL;
CREATE TABLE IF NOT EXISTS runtime_mapping_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL,
 operation TEXT NOT NULL, document TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS runtime_mapping_events_task
 ON runtime_mapping_events(task,sequence);
CREATE TABLE IF NOT EXISTS runtime_mapping_bindings(
 id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES runtime_mapping_tasks(id),
 opened INTEGER NOT NULL, closed INTEGER, document TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS runtime_mapping_intervals
 ON runtime_mapping_bindings(task,opened,closed);
CREATE TABLE IF NOT EXISTS runtime_mapping_checkpoints(
 id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES runtime_mapping_tasks(id),
 sequence INTEGER NOT NULL, document TEXT NOT NULL);
'''
MAX_ADDRESS = (1 << 64) - 1
MAX_ACTIVE = 4096
MAX_SPAN = 16 * 1024 * 1024
_HASH = re.compile(r'^[0-9a-f]{64}$')


def _int(value, name, low=0, high=MAX_ADDRESS):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _text(value, name, maximum=256):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f'invalid {name}')
    return value


def _json(value, limit=65536):
    # Reuse the bounded JSON validator; forbid NaN, deep trees and non-JSON types.
    from .snippet_links import _canonical
    raw = _canonical(value)
    if len(raw) > limit:
        raise ValueError('runtime mapping document exceeds its size budget')
    return raw.decode()


def _evidence(value):
    if not isinstance(value, dict) or not {'kind', 'reference', 'sha256'} <= set(value) or set(value) - {'kind', 'reference', 'sha256', 'note'}:
        raise ValueError('evidence requires kind, reference and sha256, with optional note')
    if value['kind'] not in ('recorded', 'modeled'):
        raise ValueError('evidence kind must be recorded or modeled; caller evidence is not live authentication')
    _text(value['reference'], 'evidence reference', 2048)
    if not isinstance(value['sha256'], str) or not _HASH.fullmatch(value['sha256']):
        raise ValueError('evidence requires an exact lowercase SHA-256')
    if 'note' in value:
        _text(value['note'], 'evidence note', 4096)
    _json(value)
    return deepcopy(value)


def _range(start, length, name):
    _int(start, name)
    _int(length, 'length', 1, MAX_SPAN)
    if start + length > MAX_ADDRESS + 1:
        raise ValueError(f'{name} range overflows its address domain')


def _handle(prefix):
    return prefix + ':' + uuid.uuid4().hex


class RuntimeMappingsMixin:
    def _mapping_source(self, version):
        v = self.version(version)
        source = self.source_info(v['id'])
        if not source.get('verified'):
            raise ValueError('runtime mappings require verified retained source bytes')
        return v, source['identity']['sha256']

    def _mapping_catalog(self, version):
        """Return private expected bytes separately from the public object view."""
        v, source_sha = self._mapping_source(version)
        cache = getattr(self, '_runtime_object_cache', {})
        cache_key = (v['id'], v['sha256'], source_sha)
        if cache_key in cache:
            return cache[cache_key]
        objects = {}
        document = self._document(v['id'])
        file_mappings = document.get('file_mappings', [])
        dos_fixups = document.get('dos', {}).get('relocations', [])
        for region in self.regions(v['id']):
            if self.meta['format'] == 'LE':
                # A generic alias must not bypass object widths, file-backed
                # holes or symbolic-fixup exclusions of the canonical LE view.
                continue
            object_id = f'region:{region.start:x}'
            backed = []
            for mapping in file_mappings:
                low = max(region.start, mapping['virtual_address'])
                high = min(region.start + len(region.data), mapping['virtual_address'] + mapping['file_size'])
                if low < high:
                    backed.append((low - region.start, high - region.start))
            fixups = [(r['linear_address'] - region.start, r['linear_address'] - region.start + 2)
                      for r in dos_fixups if region.start <= r['linear_address'] < region.start + len(region.data)]
            objects[object_id] = dict(id=object_id, source_view='project',
                preferred_start=region.start, length=len(region.data), bits=self.bits,
                data=region.data, backed=backed, fixups=fixups)
        # The same complete DOS carrier may be analyzed as MZ for runtime and
        # LE for static facts. Keep those address namespaces and mapped hashes
        # separate. An extra source view is admitted only on the original MZ.
        le_image = None
        if self.meta['format'] == 'LE':
            metadata = self.meta['loader_metadata']['le']
            regions = self.regions(v['id'])
        elif self.meta['format'] == 'MZ' and v['parent'] is None:
            from .le import load_le
            raw = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (v['id'],)).fetchone()
            try:
                le_image = load_le(bytes(raw[0]))
            except ValueError:
                le_image = None
            metadata = le_image.metadata['le'] if le_image else None
            regions = le_image.regions if le_image else []
        else:
            metadata, regions = None, []
        if metadata is not None:
            for obj in metadata['objects']:
                start = obj['virtual_address']
                region = next((r for r in regions if r.start == start), None)
                if region is None:
                    continue
                # Legacy uniform LE projects retained the validated object
                # flags before explicit per-object bits were added.
                bits = obj.get('bits', 32 if obj['flags'] & 0x2000 else 16)
                objects[f"le:{obj['index']}"] = dict(id=f"le:{obj['index']}",
                    source_view='le', object_index=obj['index'], preferred_start=start,
                    length=obj['virtual_size'], bits=bits, data=region.data,
                    backed=[(p['object_offset'], p['object_offset'] + p['file_size'])
                            for p in metadata['pages'] if p['object'] == obj['index'] and p['file_size']],
                    fixups=[(f['address'] - start, f['address'] - start + f['width'])
                            for f in metadata['fixups'] if start <= f['address'] < start + obj['virtual_size']])
        result = (objects, v, source_sha)
        cache[cache_key] = result
        self._runtime_object_cache = cache
        return result

    def runtime_objects(self, version=None):
        objects, v, source_sha = self._mapping_catalog(version)
        return dict(project_id=self.meta['project_id'], version=v['id'],
                    source_sha256=source_sha, version_sha256=v['sha256'],
                    objects=[{k: x for k, x in obj.items() if k not in ('data', 'backed', 'fixups')}
                             for obj in objects.values()],
                    note='LE preferred keys from a source view are not MZ instruction addresses; no runtime placement is inferred')

    def _mapping_task(self, task, active=False):
        _text(task, 'task handle')
        row = self.db.execute('SELECT * FROM runtime_mapping_tasks WHERE id=?', (task,)).fetchone()
        if row is None:
            raise ValueError('unknown task incarnation')
        document = json.loads(row['document'])
        document.update(started=row['started'], ended=row['ended'])
        v = self.version(row['version'])
        if document['version_sha256'] != v['sha256'] or document['source_sha256'] != self.source_sha256(v['id']):
            raise ValueError('task source/version identity changed')
        if active and row['ended'] is not None:
            raise ValueError('task incarnation has ended')
        return document

    def _mapping_event(self, task, operation, evidence, **details):
        document = dict(evidence=evidence, **details)
        raw = _json(document, 4 * 1024 * 1024)
        sequence = self.db.execute('INSERT INTO runtime_mapping_events(task,operation,document) VALUES (?,?,?)',
                                   (task, operation, raw)).lastrowid
        return sequence

    def runtime_task_start(self, run, external_id, evidence, version=None, capture_epoch=None):
        _text(run, 'run identity')
        _text(external_id, 'external task identity', 128)
        evidence = _evidence(evidence)
        if capture_epoch is not None:
            _text(capture_epoch, 'capture epoch')
        with self.transaction(True):
            v, source_sha = self._mapping_source(version)
            if self.db.execute('SELECT 1 FROM runtime_mapping_tasks WHERE run=? AND external_id=? AND ended IS NULL', (run, external_id)).fetchone():
                raise ValueError('an active task already uses this external identity in this run')
            local = self.db.execute('SELECT version FROM debug_runs WHERE id=?', (run,)).fetchone()
            if local is not None and local['version'] != v['id']:
                raise ValueError('local run belongs to a different code version')
            task = _handle('task')
            document = dict(id=task, run=run, external_id=external_id, version=v['id'],
                            project_id=self.meta['project_id'], source_sha256=source_sha,
                            version_sha256=v['sha256'], capture_epoch=capture_epoch,
                            snapshot_floor=self.db.execute('SELECT COALESCE(MAX(rowid),0) FROM debug_artifacts').fetchone()[0],
                            run_reference='local-debug-run' if local else 'caller-recorded-external-run',
                            evidence=evidence, qualification='caller_recorded_task_lifetime')
            event = self._mapping_event(task, 'task-start', evidence)
            self.db.execute('INSERT INTO runtime_mapping_tasks VALUES (?,?,?,?,?,NULL,?)',
                            (task, run, external_id, v['id'], event, _json(document)))
        return dict(task=task, event=event, **{'identity': self._mapping_task(task)}, guest_modified=False)

    def runtime_tasks(self, run=None, offset=0, limit=100):
        _int(offset, 'offset', 0, 1000000000)
        _int(limit, 'limit', 1, 1000)
        if run is not None:
            _text(run, 'run identity')
        rows = self.db.execute('SELECT id FROM runtime_mapping_tasks' + (' WHERE run=?' if run else '') +
                               ' ORDER BY started LIMIT ? OFFSET ?', (*((run,) if run else ()), limit + 1, offset)).fetchall()
        return dict(tasks=[self._mapping_task(r['id']) for r in rows[:limit]],
                    truncated=len(rows) > limit, next_offset=offset + limit if len(rows) > limit else None)

    def _mapping_at(self, task, at):
        if at is None:
            at = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM runtime_mapping_events').fetchone()[0]
        _int(at, 'event sequence', 0, (1 << 63) - 1)
        if at < task['started']:
            raise ValueError('event predates this task incarnation')
        if not self.db.execute('SELECT 1 FROM runtime_mapping_events WHERE sequence=?', (at,)).fetchone():
            raise ValueError('unknown event sequence')
        return at

    def _mapping_bindings(self, task, at):
        return [dict(json.loads(row['document']), opened=row['opened'], closed=row['closed'])
                for row in self.db.execute('SELECT * FROM runtime_mapping_bindings WHERE task=? AND opened<=? AND (closed IS NULL OR closed>?) ORDER BY opened,id',
                                           (task, at, at))]

    def runtime_mappings(self, task, at=None, offset=0, limit=256):
        _int(offset, 'offset', 0, 1000000000)
        _int(limit, 'limit', 1, MAX_ACTIVE)
        with self.transaction():
            identity = self._mapping_task(task)
            at = self._mapping_at(identity, at)
            rows = self._mapping_bindings(task, at)
        return dict(task=identity, at=at, bindings=rows[offset:offset + limit], count=len(rows),
                    truncated=offset + limit < len(rows),
                    next_offset=offset + limit if offset + limit < len(rows) else None,
                    validity='recorded journal state only; not proof of an unchanged mapping between observations or a currently live task')

    def _mapping_close(self, task, bindings, sequence):
        for binding in bindings:
            self.db.execute('UPDATE runtime_mapping_bindings SET closed=? WHERE id=? AND task=? AND closed IS NULL',
                            (sequence, binding, task))

    def _mapping_insert(self, task, document, sequence):
        binding = _handle('mapping')
        document = dict(document, id=binding, task=task)
        self.db.execute('INSERT INTO runtime_mapping_bindings VALUES (?,?,?,NULL,?)',
                        (binding, task, sequence, _json(document)))
        return binding

    def _mapping_spec(self, identity, object_id, object_offset, length, linear_start,
                      physical_start, selector, mapping_context, evidence):
        objects, _, _ = self._mapping_catalog(identity['version'])
        if type(object_id) is int:
            object_id = f'le:{object_id}'
        if not isinstance(object_id, str) or object_id not in objects:
            raise ValueError('unknown source object; use runtime-objects')
        obj = objects[object_id]
        _range(object_offset, length, 'object offset')
        if object_offset + length > obj['length']:
            raise ValueError('mapping exceeds the declared source object boundary')
        _range(linear_start, length, 'linear start')
        if physical_start is not None:
            _range(physical_start, length, 'physical start')
        if selector is not None:
            if not isinstance(selector, dict) or set(selector) != {'value', 'base', 'limit', 'bits'}:
                raise ValueError('selector requires value, base, limit and bits')
            _int(selector['value'], 'selector', 0, 65535)
            _int(selector['base'], 'selector base')
            _int(selector['limit'], 'selector limit')
            if type(selector['bits']) is not int or selector['bits'] not in (16, 32, 64):
                raise ValueError('invalid selector default width')
            if not selector['base'] <= linear_start or linear_start + length - 1 - selector['base'] > selector['limit']:
                raise ValueError('mapping is outside the supplied selector extent')
        if mapping_context is None:
            mapping_context = {}
        if not isinstance(mapping_context, dict):
            raise ValueError('mapping_context must be a JSON object')
        _json(mapping_context, 16384)
        return dict(object_id=object_id, object_offset=object_offset, length=length,
                    source_view=obj['source_view'], preferred_start=obj['preferred_start'] + object_offset,
                    source_sha256=identity['source_sha256'], version=identity['version'],
                    version_sha256=identity['version_sha256'], linear_start=linear_start,
                    physical_start=physical_start, selector=deepcopy(selector),
                    mapping_context=deepcopy(mapping_context), evidence=evidence,
                    qualification='caller_recorded_relation; not live authenticated', restored_from=None)

    def _mapping_publish(self, identity, spec, replace, evidence):
        task = identity['id']
        if replace is None:
            replace = []
        if not isinstance(replace, list) or len(replace) > MAX_ACTIVE or any(not isinstance(x, str) for x in replace) or len(set(replace)) != len(replace):
            raise ValueError('replace must be a bounded list of distinct binding IDs')
        at = self._mapping_at(identity, None)
        active = {b['id']: b for b in self._mapping_bindings(task, at)}
        if not set(replace) <= set(active):
            raise ValueError('replacement binding is not active in this task incarnation')
        if len(active) - len(replace) >= MAX_ACTIVE:
            raise ValueError('active mapping budget exceeded')
        for binding in active.values():
            overlap = spec['linear_start'] < binding['linear_start'] + binding['length'] and binding['linear_start'] < spec['linear_start'] + spec['length']
            if overlap and binding['id'] not in replace:
                raise ValueError('overlapping linear mapping requires explicit replacement of every affected binding')
        event = self._mapping_event(task, 'map', evidence, replacement_bindings=replace)
        self._mapping_close(task, replace, event)
        binding = self._mapping_insert(task, spec, event)
        return dict(task=task, binding=binding, event=event, guest_modified=False)

    def runtime_map(self, task, object_id, object_offset, length, linear_start, evidence,
                    physical_start=None, selector=None, mapping_context=None, replace=None):
        evidence = _evidence(evidence)
        with self.transaction(True):
            identity = self._mapping_task(task, active=True)
            spec = self._mapping_spec(identity, object_id, object_offset, length, linear_start,
                                      physical_start, selector, mapping_context, evidence)
            return self._mapping_publish(identity, spec, replace, evidence)

    def runtime_unmap(self, task, bindings, evidence):
        evidence = _evidence(evidence)
        if not isinstance(bindings, list) or not 1 <= len(bindings) <= MAX_ACTIVE or any(not isinstance(b, str) for b in bindings) or len(set(bindings)) != len(bindings):
            raise ValueError('bindings must be a nonempty bounded list of distinct binding IDs')
        with self.transaction(True):
            identity = self._mapping_task(task, active=True)
            active = {b['id'] for b in self._mapping_bindings(task, self._mapping_at(identity, None))}
            if not set(bindings) <= active:
                raise ValueError('binding is not active in this task incarnation')
            event = self._mapping_event(task, 'unmap', evidence, bindings=bindings)
            self._mapping_close(task, bindings, event)
        return dict(task=task, event=event, guest_modified=False)

    def runtime_task_end(self, task, evidence):
        evidence = _evidence(evidence)
        with self.transaction(True):
            identity = self._mapping_task(task, active=True)
            event = self._mapping_event(task, 'task-end', evidence)
            self.db.execute('UPDATE runtime_mapping_tasks SET ended=? WHERE id=?', (event, task))
            self.db.execute('UPDATE runtime_mapping_bindings SET closed=? WHERE task=? AND closed IS NULL', (event, task))
        return dict(task=task, event=event, guest_modified=False)

    def runtime_map_checkpoint(self, task, evidence):
        evidence = _evidence(evidence)
        with self.transaction(True):
            identity = self._mapping_task(task, active=True)
            bindings = [b['id'] for b in self._mapping_bindings(task, self._mapping_at(identity, None))]
            checkpoint = _handle('checkpoint')
            event = self._mapping_event(task, 'checkpoint', evidence, checkpoint=checkpoint)
            self.db.execute('INSERT INTO runtime_mapping_checkpoints VALUES (?,?,?,?)',
                            (checkpoint, task, event, _json(dict(bindings=bindings), 1024 * 1024)))
        return dict(task=task, checkpoint=checkpoint, event=event, guest_modified=False)

    def runtime_map_restore(self, task, checkpoint, evidence):
        evidence = _evidence(evidence)
        _text(checkpoint, 'checkpoint handle')
        with self.transaction(True):
            self._mapping_task(task, active=True)
            row = self.db.execute('SELECT * FROM runtime_mapping_checkpoints WHERE id=? AND task=?', (checkpoint, task)).fetchone()
            if row is None:
                raise ValueError('checkpoint belongs to another task incarnation or does not exist')
            saved = json.loads(row['document'])['bindings']
            originals = []
            for binding in saved:
                original = self.db.execute('SELECT document FROM runtime_mapping_bindings WHERE id=? AND task=?', (binding, task)).fetchone()
                if original is None:
                    raise ValueError('checkpoint references a missing binding')
                originals.append(json.loads(original[0]))
            event = self._mapping_event(task, 'restore', evidence, checkpoint=checkpoint)
            self.db.execute('UPDATE runtime_mapping_bindings SET closed=? WHERE task=? AND closed IS NULL', (event, task))
            restored = []
            for original in originals:
                original.update(restored_from=original['id'], evidence=evidence,
                                qualification='caller_recorded_restore; previous snapshot identity is historical, not fresh proof')
                restored.append(self._mapping_insert(task, original, event))
        return dict(task=task, checkpoint=checkpoint, bindings=restored, event=event, guest_modified=False)

    def runtime_resolve(self, task, address, space='linear', at=None, selector=None):
        _int(address, 'address')
        if space not in ('linear', 'physical', 'preferred', 'selector'):
            raise ValueError('unknown runtime address space')
        if space == 'selector':
            _int(selector, 'selector', 0, 65535)
        elif selector is not None:
            raise ValueError('selector applies only to selector address space')
        view = self.runtime_mappings(task, at=at, limit=MAX_ACTIVE)
        matches = []
        for binding in view['bindings']:
            point = address
            if space == 'selector':
                desc = binding['selector']
                if desc is None or desc['value'] != selector or address > desc['limit']:
                    continue
                point = desc['base'] + address
                start = binding['linear_start']
            else:
                start = binding[{'linear': 'linear_start', 'physical': 'physical_start', 'preferred': 'preferred_start'}[space]]
            if start is None or not start <= point < start + binding['length']:
                continue
            delta = point - start
            matches.append(dict(binding, object_offset=binding['object_offset'] + delta,
                                preferred_address=binding['preferred_start'] + delta,
                                linear_address=binding['linear_start'] + delta,
                                physical_address=None if binding['physical_start'] is None else binding['physical_start'] + delta))
        identities = {(b['source_sha256'], b['source_view'], b['object_id'], b['object_offset'], b['version_sha256']) for b in matches}
        return dict(task=task, at=view['at'], space=space, address=address, selector=selector,
                    matches=matches, ambiguous=len(identities) > 1, status='mapped' if matches else 'unmapped_or_unknown',
                    validity=view['validity'])

    def runtime_mapping_events(self, task, after=0, limit=100):
        self._mapping_task(task)
        _int(after, 'after', 0, (1 << 63) - 1)
        _int(limit, 'limit', 1, 1000)
        rows = self.db.execute('SELECT * FROM runtime_mapping_events WHERE task=? AND sequence>? ORDER BY sequence LIMIT ?',
                               (task, after, limit + 1)).fetchall()
        events = [dict(sequence=r['sequence'], operation=r['operation'], **json.loads(r['document'])) for r in rows[:limit]]
        return dict(task=task, events=events, truncated=len(rows) > limit,
                    next_after=events[-1]['sequence'] if len(rows) > limit else None,
                    ordering='journal append order; not a reconstructed unobserved execution timeline')

    def runtime_map_snapshot(self, task, snapshot, object_id, object_offset, length,
                             snapshot_offset=0, replace=None):
        """Qualify a local retained capture extent; never accepts foreign IDs/masks."""
        from .memory_search_runtime import _snapshot
        _int(snapshot_offset, 'snapshot offset', 0, MAX_SPAN)
        _int(length, 'length', 1, MAX_SPAN)
        with self.transaction(True):
            identity = self._mapping_task(task, active=True)
            row, data, metadata = _snapshot(self, snapshot)
            stored = self.db.execute('SELECT rowid FROM debug_artifacts WHERE id=?', (snapshot,)).fetchone()
            if stored[0] <= identity['snapshot_floor']:
                raise ValueError('snapshot predates this task incarnation; capture fresh bytes after task-start')
            context = metadata['snapshot']['context']
            expected = dict(source_sha256=identity['source_sha256'], version_id=identity['version'],
                            version_sha256=identity['version_sha256'], run_id=identity['run'],
                            task_id=identity['external_id'])
            if any(context.get(k) != v for k, v in expected.items()):
                raise ValueError('snapshot source, version, run or declared task identity differs')
            epoch = context.get('capture_epoch')
            if not epoch or identity['capture_epoch'] != epoch:
                raise ValueError('snapshot requires the task incarnation\'s explicit capture_epoch')
            if context['address_space'] != 'linear':
                raise ValueError('snapshot object bindings require an observed linear capture')
            if snapshot_offset + length > len(data):
                raise ValueError('binding exceeds captured bytes')
            address = context['region']['start'] + snapshot_offset
            evidence = dict(kind='recorded', reference='local-memory-snapshot:' + snapshot, sha256=row['sha256'])
            spec = self._mapping_spec(identity, object_id, object_offset, length, address,
                                      None, None, dict(snapshot=snapshot, mapping_id=context['mapping_id'],
                                                      capture_epoch=epoch), evidence)
            objects, _, _ = self._mapping_catalog(identity['version'])
            obj = objects[spec['object_id']]
            # Only file-backed bytes qualify. Holes/BSS and all-fixup ranges
            # cannot be used as empty witnesses for an entire object.
            intervals = sorted(obj['backed'])
            cursor, end = object_offset, object_offset + length
            for low, high in intervals:
                if low <= cursor < high:
                    cursor = min(end, high)
                if cursor == end:
                    break
            if cursor != end:
                raise ValueError('snapshot comparison crosses unbacked source bytes')
            raw = obj['data'][object_offset:end]
            actual = data[snapshot_offset:snapshot_offset + length]
            excluded = {i for low, high in obj['fixups'] for i in range(max(low, object_offset), min(high, end))}
            compared = 0
            for index, (a, b) in enumerate(zip(raw, actual, strict=True), object_offset):
                if index in excluded:
                    continue
                compared += 1
                if a != b:
                    raise ValueError('captured bytes do not match the selected source object')
            if not compared:
                raise ValueError('snapshot span contains no independently comparable source bytes')
            capture = metadata.get('capture')
            if not isinstance(capture, dict) or not isinstance(capture.get('mapping'), dict):
                raise ValueError('snapshot lacks capture mapping evidence')
            if hashlib.sha256(_json(capture['mapping']).encode()).hexdigest() != context['mapping_id']:
                raise ValueError('snapshot mapping evidence differs from its sealed identity')
            pages = capture.get('pages', [])
            if not isinstance(pages, list) or len(pages) > MAX_SPAN // 4096 + 1:
                raise ValueError('invalid snapshot page evidence')
            if capture['mapping'].get('kind') == 'observed-386-pages' and (
                    hashlib.sha256(_json(pages, 4 * 1024 * 1024).encode()).hexdigest() != capture['mapping'].get('pages_sha256')
                    or capture['mapping'].get('page_count') != len(pages)):
                raise ValueError('snapshot page evidence differs from its sealed mapping')
            page_starts = set()
            for page in pages:
                if not isinstance(page, dict) or not isinstance(page.get('linear'), str) or not isinstance(page.get('physical'), (str, int)):
                    raise ValueError('invalid snapshot page address')
                try:
                    low = int(page['linear'], 16)
                    physical = int(page['physical'], 16) if isinstance(page['physical'], str) else page['physical']
                except ValueError:
                    raise ValueError('invalid snapshot page address') from None
                _range(low, 4096, 'snapshot linear page')
                _range(physical, 4096, 'snapshot physical page')
                if low % 4096 or physical % 4096:
                    raise ValueError('snapshot page evidence must be page aligned')
                if low in page_starts:
                    raise ValueError('snapshot page evidence has ambiguous duplicate linear pages')
                page_starts.add(low)
            if capture['mapping'].get('kind') != 'observed-386-pages':
                pages = []
            physical = []
            cursor = address
            while cursor < address + length:
                page = next((p for p in pages if int(p['linear'], 16) <= cursor < int(p['linear'], 16) + 4096), None)
                if page is None:
                    break
                page_start = int(page['linear'], 16)
                physical_start = int(page['physical'], 16) if isinstance(page['physical'], str) else page['physical']
                physical.append((cursor, physical_start + cursor - page_start))
                cursor = min(address + length, page_start + 4096)
            if cursor == address + length and physical and all(p - l == physical[0][1] - physical[0][0] for l, p in physical):
                spec['physical_start'] = physical[0][1]
            spec.update(qualification='snapshot_bytes_and_capture_context_verified; task ownership remains caller-declared',
                        snapshot=snapshot, compared_bytes=compared, excluded_fixup_bytes=len(excluded),
                        verification_scope='only this captured extent at this capture; no continuous mapping, execution or allocation ownership proof')
            return self._mapping_publish(identity, spec, replace, evidence)
