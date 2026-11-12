"""Read-only, bounded format inventory shared by single and collection intake.

This is the inventory phase: it never extracts carriers, imports a program,
decodes media, or turns a candidate resource profile into header evidence.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import stat

from . import format_registry as registry

MAX_FILES = 10000
MAX_READ_BYTES = 256 * 1024 * 1024
MAX_ROOTS = 256
MAX_DEPTH = 64
MEDIA_CATEGORIES = frozenset({'image', 'audio', 'video', 'animation', 'media', 'music',
                              'image-container', 'animation-container'})
CONTAINER_CATEGORIES = frozenset({'archive', 'container', 'disc', 'resource-container',
                                  'image-container', 'animation-container'})


def _short(value, limit=512):
    return value[:limit] if isinstance(value, str) else value


def _strings(value, count=12):
    return [_short(v) for v in value[:count] if isinstance(v, str)] if isinstance(value, list) else []


def _facts(value):
    """Header scalars, not raw structures, buffers or unbounded native tables."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in islice(value.items(), 64):
        if isinstance(key, str) and (item is None or type(item) in (bool, int, float, str)):
            result[_short(key, 96)] = _short(item)
    header = value.get('header')
    if isinstance(header, dict):
        result['native_header'] = {
            k: _short(header[k]) for k in ('format', 'family', 'arch', 'bits', 'endian',
                                          'valid', 'entrypoint', 'header_offset')
            if k in header and (header[k] is None or type(header[k]) in (str, int, bool))
        }
    return result


def _module(module):
    return dict(module_id=module.get('module_id'), revision=module.get('revision'),
                api=_short(module.get('api')), capabilities=_strings(module.get('capabilities')),
                implemented=module.get('implemented') is True,
                binding_verified=module.get('binding_verified') is True,
                decoder_role=module.get('decoder_role', 'unverified'),
                limitations=_strings(module.get('limitations')))


def _identified(report):
    ident = report['identification']
    result = {k: ident.get(k) for k in ('format_id', 'name', 'category', 'status',
              'recognized', 'header_valid', 'architecture', 'validation_scope',
              'full_decode', 'native_runtime_tested')}
    result.update(header_facts=_facts(ident.get('metadata')), warnings=_strings(ident.get('warnings')),
                  decoder_modules=[dict(module_id=m.get('module_id'), revision=m.get('revision'),
                                        decoder_role=m.get('decoder_role', 'unverified'),
                                        binding_verified=m.get('binding_verified') is True)
                                   for m in ident.get('decoder_modules', [])[:64]])
    if isinstance(ident.get('mz_envelope'), dict):
        result['mz_envelope'] = _facts(ident['mz_envelope'])
    if isinstance(ident.get('image_views'), list):
        result['image_views'] = [{k: _short(v[k]) for k in (
            'image', 'format', 'arch', 'bits', 'available', 'loadable', 'valid', 'error',
            'validation_scope') if k in v} for v in ident['image_views'][:32] if isinstance(v, dict)]
    return result


def _hints(path, catalog):
    # Descriptive context hints never decide the identified format. Restrict
    # returned fields so custom catalog content cannot become a payload export.
    values = registry.resource_profile_hints(path, catalog)
    if not isinstance(values, list):
        return []
    keys = ('format_id', 'revision', 'name', 'category', 'consumer', 'confidence',
            'qualification', 'reason', 'matched_pattern', 'decoder_role')
    result = []
    for value in values[:16]:
        if isinstance(value, dict):
            row = {key: _short(value[key]) for key in keys
                   if key in value and (value[key] is None or type(value[key]) in (str, int, bool))}
            row.update(companions=_strings(value.get('companions')), recovery=_strings(value.get('recovery')))
            result.append(row)
    return result


def _queue_reasons(ident):
    status, category = ident.get('status', ''), ident.get('category')
    if status == 'unknown':
        yield 'unknown-format', 'Recover a header or consumer-bound resource profile; a suffix is only a hint.'
        return
    if status == 'recognized-invalid':
        yield 'invalid-header-or-variant', 'Investigate the stated header refusal against the original consumer; do not assume corruption.'
        return
    if 'unsupported' in status or status == 'recognized-header-limit':
        yield 'unsupported-profile', 'Qualify the missing size/layout/header capability without modifying the source.'
    if category in MEDIA_CATEGORIES:
        roles = {m.get('decoder_role') for m in ident.get('decoder_modules', []) if m.get('binding_verified')}
        if roles & {'pixel-reader', 'media-decoder-and-framer', 'media-decoder', 'video-reader'}:
            yield 'media-validation-needed', 'Check the linked reader accepts this profile, then independently decode; intake has not decoded media.'
        else:
            yield 'media-decoder-recovery', 'Recover or qualify the missing complete media decoder; header recognition alone is insufficient.'
    if category in CONTAINER_CATEGORIES:
        yield 'container-members-not-inventoried', 'Use a qualified bounded member reader, preserve provenance, then inventory the selected outputs separately.'
    if category in ('executable', 'console-media'):
        yield 'embedded-media-unqualified', 'Header/image loading establishes neither presence nor absence of embedded media. Qualify executable resources or console banks and their consumers separately before converting assets.'
    if any(view.get('loadable') is False and view.get('error') for view in ident.get('image_views', [])):
        yield 'image-view-recovery', 'Qualify the refused image view separately from any valid executable stub.'
    tail = ident.get('mz_envelope', {})
    if ident.get('format_id') == 'dos-mz' and tail.get('trailing_bytes', 0) and not tail.get('secondary_header_offset'):
        yield 'opaque-tail-recovery', 'Recover the tail/overlay/packer consumer before treating trailing bytes as mapped code or disposable media.'


def intake_inventory(paths, *, catalog_path=None, max_files=MAX_FILES,
                     max_read_bytes=MAX_READ_BYTES, max_binary_bytes=registry.MAX_BINARY_BYTES):
    """Inventory one or many explicit file/directory roots through one kernel.

    Complete describes bounded filesystem enumeration and identification only.
    Containers are not expanded; decoding, loading and runtime tests stay not-run.
    Directory links are reported and not followed. Regular file links retain
    their requested and resolved paths. Catalog output must be outside inputs.
    """
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_ROOTS:
        raise ValueError('paths must contain 1..256 explicit input roots')
    for name, value, upper in (('max_files', max_files, MAX_FILES),
                                ('max_read_bytes', max_read_bytes, 4 * 1024 * 1024 * 1024),
                                ('max_binary_bytes', max_binary_bytes, registry.MAX_BINARY_BYTES)):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError(f'{name} must be a positive integer at most {upper}')
    roots = []
    for raw in paths:
        if not isinstance(raw, (str, os.PathLike)) or not os.fspath(raw):
            raise ValueError('Each input root must be a nonempty filesystem path')
        path = Path(os.path.abspath(os.path.expanduser(os.fspath(raw))))
        roots.append(dict(root_index=len(roots), path=str(path), complete=True))
    requested_catalog = None if catalog_path is None else Path(os.path.abspath(os.path.expanduser(os.fspath(catalog_path))))
    if requested_catalog is not None:
        destination = requested_catalog.resolve()
        for root in roots:
            path = Path(root['path'])
            resolved = path.resolve()
            if destination == resolved or path.is_dir() and destination.is_relative_to(resolved):
                raise ValueError('Catalog must be outside all input roots')
            if path.is_dir() and any(parent.exists() and os.path.samefile(path, parent)
                                     for parent in destination.parents):
                raise ValueError('Catalog must be outside all input roots')
            if destination.exists() and path.exists() and os.path.samefile(path, destination):
                raise ValueError('Source and catalog must be different files')
    # Enumerate first: otherwise an input symlink to an external catalog could
    # be mutated by seeding before its eventual file-level alias refusal.
    catalog = None
    files, skipped, errors, recovery = [], [], [], {}
    pending = []
    bytes_read = visits = 0
    discovered = len(roots)
    stop_reason = None
    max_entries = max_files * 4 + len(roots)

    def issue(root, member, kind, message):
        root['complete'] = False
        errors.append(dict(root_index=root['root_index'], member=member,
                           kind=kind, message=_short(str(message), 1000)))

    def enqueue(record, reason, action):
        ident = record['identification']
        hints = record.get('candidate_profiles', [])
        suffix = Path(record['member']).suffix.casefold()
        hint_ids = tuple(sorted(str(h.get('format_id')) for h in hints if h.get('format_id')))
        key = (reason, ident.get('format_id'), suffix if not ident.get('format_id') else '', hint_ids)
        if key not in recovery:
            token = hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).hexdigest()[:20]
            recovery[key] = dict(recovery_id=token, reason=reason, format_id=ident.get('format_id'),
                category=ident.get('category'), extension_hint=(suffix or None) if not ident.get('format_id') else None,
                extension_hints=[],
                candidate_profiles=hints, grouping_evidence='Reported format ID, or filename suffix/context candidates only; no semantic-equivalence claim.',
                next_action=action, count=0, members=[])
        group = recovery[key]
        if suffix and suffix not in group['extension_hints'] and len(group['extension_hints']) < 128:
            group['extension_hints'].append(suffix)
            group['extension_hints'].sort()
        group['count'] += 1
        group['members'].append(dict(root_index=record['root_index'], member=record['member'], file_index=record['file_index']))

    def visit_file(root, path, member, info, linked):
        nonlocal stop_reason
        if len(files) >= max_files:
            stop_reason = 'max-files'
            issue(root, member, 'budget', 'File inventory budget exhausted; remaining members were not inspected.')
            return
        record = dict(file_index=len(files), root_index=root['root_index'], member=member,
                      path=str(path), is_symlink=linked, resolved_path=str(path.resolve()),
                      source_size=info.st_size, status='pending-identification')
        files.append(record)
        pending.append((root, path, member, info, record))

    def identify_pending(root, path, member, info, record):
        nonlocal bytes_read, stop_reason
        remaining = max_read_bytes - bytes_read
        if remaining <= 0:
            stop_reason = 'max-read-bytes'
            record['status'] = 'read-budget-not-inspected'
            issue(root, member, 'budget', 'Aggregate source-read budget exhausted before this file.')
            return
        allowance = min(remaining, registry.MAX_IDENTIFY_READ_BYTES)
        try:
            report = registry._identify_file_with_catalog(path, catalog,
                        max_binary_bytes=max_binary_bytes, max_read_bytes=allowance)
        except Exception as error:
            used = getattr(error, 'bytes_read', allowance)
            used = used if type(used) is int and 0 <= used <= allowance else allowance
            bytes_read += used
            record.update(status='identification-error', bytes_read=used,
                          sampled_regions=getattr(error, 'sampled_regions', []))
            if isinstance(error, registry.ReadBudgetExceeded):
                record['status'] = 'read-budget-not-inspected'
                stop_reason = 'max-read-bytes'
                issue(root, member, 'budget', error)
            else:
                io_error = isinstance(error, OSError)
                issue(root, member, 'io-error' if io_error else 'reader-refusal', error)
                if not io_error:
                    record['identification'] = dict(format_id=None, category='unknown', status='reader-refusal',
                        recognized=False, header_valid=None)
                    enqueue(record, 'reader-refusal', 'Investigate the reader refusal and original consumer without assuming source corruption or format support.')
            return
        used = report['source']['bytes_read']
        if type(used) is not int or not 0 <= used <= allowance:
            raise ValueError('File identifier violated its aggregate read accounting contract')
        bytes_read += used
        record.update(status='observed-awaiting-path-check', source=report['source'], bytes_read=used)
        opened = report['source'].get('opened_identity', {})
        before_identity = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
        opened_identity = tuple(opened.get(k) for k in ('device', 'inode', 'mtime_ns', 'ctime_ns'))
        try:
            after = path.stat()
            after_identity = (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
            stable = (before_identity == opened_identity == after_identity
                      and info.st_size == report['source']['size'] == after.st_size
                      and str(path.resolve()) == record['resolved_path'])
        except OSError as error:
            record['status'] = 'source-changed'
            issue(root, member, 'io-error', error)
            return
        if not stable:
            record['status'] = 'source-changed'
            issue(root, member, 'source-changed', 'Source path/identity changed between enumeration, opening and final verification.')
            return
        # Outer status reports completed inspection, not format recognition.
        # Unknown, invalid and unsupported results remain in the nested
        # identification.status field; callers must not treat 'inspected' as
        # evidence that a decoder recognized the source.
        record.update(status='inspected', identification=_identified(report))
        if record['identification']['status'] == 'unknown':
            record['candidate_profiles'] = _hints(path, catalog)
        for reason, action in _queue_reasons(record['identification']):
            enqueue(record, reason, action)

    def walk(root, path, member, depth):
        nonlocal visits, discovered, stop_reason
        if stop_reason:
            root['complete'] = False
            return
        visits += 1
        if visits > max_entries:
            stop_reason = 'max-filesystem-entries'
            issue(root, member, 'budget', 'Filesystem-entry budget exhausted before complete enumeration.')
            return
        try:
            info = path.lstat()
            linked = stat.S_ISLNK(info.st_mode)
            if linked:
                info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                if linked:
                    root['complete'] = False
                    skipped.append(dict(root_index=root['root_index'], member=member,
                        reason='directory-symlink-not-followed', path=str(path), resolved_path=str(path.resolve())))
                    return
                if depth > MAX_DEPTH:
                    issue(root, member, 'depth-limit', 'Directory nesting exceeds 64; descendants not inventoried.')
                    return
                # Materialize at most the remaining bounded entry count. A huge
                # directory cannot defeat admission through sorted(scandir()).
                children = []
                with os.scandir(path) as entries:
                    for entry in entries:
                        if discovered >= max_entries:
                            stop_reason = 'max-filesystem-entries'
                            issue(root, member, 'budget', 'Directory exceeds the remaining entry budget; descendants not inventoried.')
                            return
                        discovered += 1
                        children.append(entry.name)
                for name in sorted(children):
                    child_member = name if member == '.' else member + '/' + name
                    walk(root, path / name, child_member, depth + 1)
                    if stop_reason:
                        break
            elif stat.S_ISREG(info.st_mode):
                visit_file(root, path, member, info, linked)
            else:
                root['complete'] = False
                skipped.append(dict(root_index=root['root_index'], member=member,
                    reason='non-regular-file-not-read', path=str(path)))
        except OSError as error:
            issue(root, member, 'io-error', error)

    for root in roots:
        path = Path(root['path'])
        walk(root, path, '.', 0)
        root['files_reported'] = sum(row['root_index'] == root['root_index'] for row in files)
    enumeration_complete = all(root['complete'] for root in roots)
    if requested_catalog is not None and enumeration_complete:
        for root, path, member, _, record in pending:
            try:
                if (path.resolve() == destination or destination.exists() and os.path.samefile(path, destination)):
                    raise ValueError('An input member aliases the catalog; refusing before catalog seeding')
            except OSError as error:
                issue(root, member, 'io-error', error)
                record['status'] = 'io-error-before-catalog'
                enumeration_complete = False
    if requested_catalog is None:
        persistence = 'in-memory'
        catalog_argument = None
    elif enumeration_complete:
        persistence = 'persisted'
        catalog_argument = requested_catalog
    else:
        persistence = 'not-written-incomplete-enumeration'
        catalog_argument = None
    catalog = registry.format_catalog(catalog_path=catalog_argument)
    modules = [_module(module) for module in catalog['modules']]
    read_stopped = False
    for root, path, member, info, record in pending:
        if record['status'] != 'pending-identification':
            continue
        if read_stopped:
            record['status'] = 'read-budget-not-inspected'
            root['complete'] = False
            continue
        identify_pending(root, path, member, info, record)
        read_stopped = stop_reason == 'max-read-bytes'
    counts = Counter(row.get('identification', {}).get('status', row['status']) for row in files)
    return dict(format='fdisbull-intake-inventory-1', complete=all(root['complete'] for root in roots),
        inventory_scope='Explicit filesystem roots only; carriers and resource archives are not expanded or decoded.',
        roots=roots, files=files, skipped=skipped, errors=errors,
        catalog=dict(path=catalog.get('catalog_path'), requested_path=str(requested_catalog) if requested_catalog else None,
            persistence=persistence, schema_version=catalog['schema_version'],
            contains_file_payloads=catalog.get('contains_file_payloads'),
            content_qualification=catalog.get('catalog_content_qualification')),
        decoder_modules=modules, recovery_queue=sorted(recovery.values(), key=lambda row: row['recovery_id']),
        summary=dict(files_reported=len(files), statuses=dict(sorted(counts.items())),
                     recovery_groups=len(recovery), recovery_pending=bool(recovery)),
        budgets=dict(max_files=max_files, max_read_bytes=max_read_bytes, max_binary_bytes=max_binary_bytes,
                     bytes_read=bytes_read, filesystem_entries_visited=visits,
                     filesystem_entries_discovered=discovered, max_filesystem_entries=max_entries,
                     stop_reason=stop_reason),
        input_executed=False, inspected_source_bytes_persisted=False, executables_modified=False,
        full_media_decode=False, native_runtime_tested=False)
