"""Bounded, offline record discovery that stays ready when navigation is blocked.

Every result names its actual source directory and file. Name spacing and file
partitions are hypotheses, not game schemas; no occupancy or field semantics are
invented. A single content digest per file distinguishes same-size rewrites and
different copies. Readers preserve raw bytes so provisional interpretations can
be changed without losing information. No emulator or Project is required.
"""

from collections import Counter, defaultdict
from hashlib import sha256
import os
from pathlib import Path
import re


_NAME = re.compile(rb"[A-Za-z][A-Za-z .'-]{3,47}(?=[^A-Za-z .'-]|$)")
_VERSION = 'fdisbull-record-frontier-1'


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError('source label must contain 1..256 characters')
    return value


def _read(path, maximum):
    # Limit the actual read, including a file that grows after stat().
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(data) > maximum:
        raise ValueError(f'file exceeds {maximum} byte read budget')
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('file changed during read; retry this source after its writer settles')
    return data, after


def _source(path, label, data, stat=None):
    result = {'label': label, 'path': str(path), 'size': len(data),
              'sha256': sha256(data).hexdigest()}
    if stat is not None:
        result['mtime_ns'] = stat.st_mtime_ns
    return result


def _names(data, maximum):
    result = []
    truncated = False
    for match in _NAME.finditer(data):
        text = match.group().rstrip(b' .\'-')
        if len(text) < 4 or sum(chr(c).isalpha() for c in text) < 4:
            continue
        # A suffix of a longer printable run is not a new name start.
        if match.start() and data[match.start()-1] in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .'-":
            continue
        if len(result) == maximum:
            truncated = True
            break
        result.append({'offset': match.start(), 'text': text.decode('ascii')})
    return result, truncated


def analyze_record_bytes(data, *, source, min_stride=8, max_stride=512,
                         min_records=3, max_records=4096, max_candidates=8,
                         max_strings=256):
    """Find name-aligned strides and arithmetic partitions in supplied bytes.

    ``source`` is a caller-supplied JSON identity (typically label/path/size).
    Name candidates require three different rows at one field offset. Exact
    adjacent-name spacing ranks before divisors/multiples of that spacing.
    Name spacing can suggest full rows followed by an unassigned tail; an
    imperfect file-size divisor does not discard those candidates. Exact
    divisor partitions remain available for cross-file count matching.
    """
    if not isinstance(data, bytes) or len(data) > 16 * 1024 * 1024:
        raise ValueError('data must be bytes of at most 16 MiB')
    if not isinstance(source, dict):
        raise ValueError('source must be an identity object')
    _integer(min_stride, 'min_stride', 1, 4096)
    _integer(max_stride, 'max_stride', min_stride, 4096)
    _integer(min_records, 'min_records', 2, 65536)
    _integer(max_records, 'max_records', min_records, 65536)
    _integer(max_candidates, 'max_candidates', 1, 64)
    _integer(max_strings, 'max_strings', 3, 4096)
    names, strings_limited = _names(data, max_strings)
    partitions, candidates = [], []
    for stride in range(min_stride, min(max_stride, len(data) // min_records) + 1):
        count, tail = divmod(len(data), stride)
        if not min_records <= count <= max_records:
            continue
        if not tail:
            partitions.append({'stride': stride, 'record_count': count})
        groups = defaultdict(list)
        for name in names:
            offset = name['offset'] % stride
            if name['offset'] < count * stride and offset + len(name['text']) <= stride:
                groups[offset].append(name)
        for offset, group in groups.items():
            if len(group) < 3:
                continue
            gaps = Counter(b['offset'] - a['offset'] for a, b in zip(group, group[1:]))
            exact = gaps[stride]
            examples = [{'row': name['offset'] // stride, **name} for name in group[:4]]
            candidates.append({'stride': stride, 'record_count': count,
                               'trailing_bytes': tail,
                               'name_offset': offset, 'matched_names': len(group),
                               'adjacent_stride_matches': exact, 'examples': examples,
                               'basis': 'repeated ASCII-name offsets; field meanings unknown'})
    candidates.sort(key=lambda c: (-c['adjacent_stride_matches'], -c['matched_names'],
                                   c['stride'], c['name_offset']))
    return {'source': dict(source), 'status': 'bounded_candidates',
            'name_candidates': candidates[:max_candidates], 'partitions': partitions,
            'strings': names[:8], 'strings_found': len(names),
            'limits': {'max_strings': max_strings, 'strings_truncated': strings_limited,
                       'candidates_truncated': len(candidates) > max_candidates,
                       'min_stride': min_stride, 'max_stride': max_stride,
                       'min_records': min_records, 'max_records': max_records},
            'claim': 'Candidate layouts only; repeated rows do not establish occupancy or semantics.'}


def _paths(root, maximum, errors):
    """Yield a bounded deterministic walk, excluding symlinks and special files."""
    seen, directories = 0, 0

    def walk_error(error):
        errors.append({'path': str(error.filename or root), 'reason': str(error)})

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        directories += 1
        if directories > maximum * 4:
            yield None
            return
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            if seen == maximum:
                yield None
                return
            seen += 1
            yield path


def snapshot_record_files(root, label, *, max_files=256, max_file_bytes=4194304,
                          max_total_bytes=33554432, max_candidates=8):
    """Inventory and analyze one directory; a failed file never stops siblings."""
    _label(label)
    _integer(max_files, 'max_files', 1, 4096)
    _integer(max_file_bytes, 'max_file_bytes', 1, 16777216)
    _integer(max_total_bytes, 'max_total_bytes', 1, 268435456)
    _integer(max_candidates, 'max_candidates', 1, 64)
    root = Path(root).expanduser().resolve()
    result = {'label': label, 'path': str(root), 'files': [], 'errors': [],
              'bytes_read': 0, 'files_truncated': False}
    if not root.is_dir():
        result['errors'].append({'path': str(root), 'reason': 'source directory is unavailable'})
        return result
    for path in _paths(root, max_files, result['errors']):
        if path is None:
            result['files_truncated'] = True
            break
        relative = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
            remaining = max_total_bytes - result['bytes_read']
            if size > max_file_bytes or size > remaining:
                result['errors'].append({'path': str(path), 'relative_path': relative,
                                         'size': size, 'reason': 'file exceeds remaining read budget'})
                continue
            data, stat = _read(path, min(max_file_bytes, remaining))
            result['bytes_read'] += len(data)
            source = _source(path, label, data, stat)
            analysis = analyze_record_bytes(data, source=source, max_candidates=max_candidates)
            result['files'].append({**source, 'relative_path': relative,
                                    'name_candidates': analysis['name_candidates'],
                                    'partitions': analysis['partitions'],
                                    'strings': analysis['strings'],
                                    'candidate_limits': analysis['limits']})
        except (OSError, ValueError) as error:
            result['errors'].append({'path': str(path), 'relative_path': relative,
                                     'reason': str(error)})
    return result


def compare_record_snapshots(before, after):
    """Compare matching relative paths, preserving both source identities.

    A missing file is ``removed`` only if the new inventory is complete and did
    not fail to read that path; otherwise it stays ``unobserved``.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError('before and after must be snapshot objects')
    old = {f['relative_path']: f for f in before.get('files', [])}
    new = {f['relative_path']: f for f in after.get('files', [])}
    unread = {e.get('relative_path') for e in after.get('errors', [])}
    # A directory traversal error may hide several files. A per-file failure
    # has relative_path and can be scoped precisely; all other walk failures
    # keep missing files unknown instead of inventing removals.
    unavailable = any('relative_path' not in e for e in after.get('errors', []))
    changes = []
    for relative in sorted(old.keys() | new.keys()):
        a, b = old.get(relative), new.get(relative)
        if a is None:
            kind = 'new'
        elif b is None:
            kind = ('unobserved' if after.get('files_truncated') or unavailable or relative in unread
                    else 'removed')
        elif a['sha256'] != b['sha256']:
            kind = 'changed'
        else:
            kind = 'same_bytes'
        changes.append({'relative_path': relative, 'kind': kind,
                        'before': {key: a[key] for key in ('label', 'path', 'size', 'sha256')} if a else None,
                        'after': {key: b[key] for key in ('label', 'path', 'size', 'sha256')} if b else None})
    return changes


def _shared_counts(source, maximum=64):
    counts = defaultdict(list)
    for file in source['files']:
        named = {c['stride'] for c in file['name_candidates'] if c['adjacent_stride_matches']}
        for p in file['partitions']:
            counts[p['record_count']].append({'path': file['path'], 'relative_path': file['relative_path'],
                                               'stride': p['stride'], 'name_supported': p['stride'] in named})
    rows = [{'source_label': source['label'], 'source_root': source['path'],
             'record_count': count, 'files': files,
             'basis': 'equal arithmetic row counts; relationship unverified'}
            for count, files in counts.items() if len(files) >= 2]
    rows.sort(key=lambda r: (-sum(f['name_supported'] for f in r['files']),
                             -len(r['files']), -r['record_count']))
    return rows[:maximum], len(rows) > maximum


def record_frontier(roots, *, previous=None, runtime_blocker=None, max_files=256,
                    max_file_bytes=4194304, max_total_bytes=33554432, max_candidates=8,
                    max_ready_tasks=32):
    """Return ready offline tasks independently of an optional runtime blocker.

    ``roots`` is 1..16 objects with ``path`` and distinct ``label`` fields.
    ``previous`` may be the preceding result of this function. File/read budgets
    apply across the whole call, not once per root. Cross-source comparisons use
    adjacent declared roots, useful for supplied -> strategic -> handoff -> save.
    Same-source changes compare the previous snapshot; relationships always name
    their source and remain candidates. No polling or automatic runtime work.
    """
    if not isinstance(roots, (list, tuple)) or not 1 <= len(roots) <= 16:
        raise ValueError('roots must contain 1..16 labeled source directories')
    _integer(max_files, 'max_files', 1, 4096)
    _integer(max_file_bytes, 'max_file_bytes', 1, 16777216)
    _integer(max_total_bytes, 'max_total_bytes', 1, 268435456)
    _integer(max_candidates, 'max_candidates', 1, 64)
    _integer(max_ready_tasks, 'max_ready_tasks', 1, 4096)
    if previous is not None and (not isinstance(previous, dict) or previous.get('schema') != _VERSION):
        raise ValueError('previous must be an earlier record_frontier result')
    if runtime_blocker is not None and (not isinstance(runtime_blocker, str) or len(runtime_blocker) > 4096):
        raise ValueError('runtime_blocker must be a short description')
    labels = set()
    selected = []
    for root in roots:
        if not isinstance(root, dict) or set(root) != {'path', 'label'}:
            raise ValueError('each root needs exactly path and label')
        label = _label(root['label'])
        if label in labels:
            raise ValueError('source labels must be distinct')
        labels.add(label)
        selected.append((root['path'], label))
    result = {'schema': _VERSION, 'sources': [], 'changes': [], 'source_comparisons': [],
              'shared_record_counts': [], 'ready_tasks': [], 'blocked_tasks': [], 'errors': []}
    old_sources = {(s['label'], s['path']): s for s in (previous or {}).get('sources', [])}
    task_versions = {}
    files_left, bytes_left = max_files, max_total_bytes
    for path, label in selected:
        if files_left == 0 or bytes_left == 0:
            source = {'label': label, 'path': str(Path(path).expanduser().resolve()),
                      'files': [], 'bytes_read': 0, 'files_truncated': True,
                      'errors': [{'path': str(path), 'reason': 'overall inventory budget exhausted'}]}
        else:
            source = snapshot_record_files(path, label, max_files=files_left,
                                            max_file_bytes=max_file_bytes, max_total_bytes=bytes_left,
                                            max_candidates=max_candidates)
        result['sources'].append(source)
        result['errors'].extend({'source_label': label, **e} for e in source['errors'])
        files_left -= len(source['files']) + sum('relative_path' in e for e in source['errors'])
        files_left = max(0, files_left)
        bytes_left -= source['bytes_read']
        prior = old_sources.get((label, source['path']))
        changes = compare_record_snapshots(prior or {}, source)
        result['changes'].extend(changes)
        changed = {c['relative_path']: c['kind'] for c in changes}
        for file in source['files']:
            if changed[file['relative_path']] not in ('new', 'changed') or file['size'] == 0:
                continue
            candidates = file['name_candidates']
            task = {'kind': 'record_census' if candidates else 'inspect_partitions',
                                          'source_label': label, 'path': file['path'], 'size': file['size'],
                                          'change': changed[file['relative_path']],
                                          'candidate': candidates[0] if candidates else None,
                                          'requires_runtime': False,
                                          'next': ('Read candidate rows with read_record_rows; keep raw bytes and provisional labels.'
                                                   if candidates else 'Inspect file partitions and shared row counts; no UI prerequisite.')}
            key = (file['relative_path'], file['sha256'])
            earlier = task_versions.get(key)
            if earlier:
                task['also_sources'] = earlier.get('also_sources', []) + [
                    {'source_label': earlier['source_label'], 'path': earlier['path']}]
            task_versions[key] = task
        shared, limited = _shared_counts(source)
        result['shared_record_counts'].extend(shared)
        source['shared_counts_truncated'] = limited
    for before, after in zip(result['sources'], result['sources'][1:]):
        differences = compare_record_snapshots(before, after)
        result['source_comparisons'].append({'before_label': before['label'], 'after_label': after['label'],
                                             'files': differences})
        for difference in differences:
            if difference['after']:
                key = (difference['relative_path'], difference['after']['sha256'])
                task = task_versions.get(key)
                if task and task['source_label'] == after['label']:
                    task['change_from_previous_source'] = difference['kind']
    source_order = {source['label']: index for index, source in enumerate(result['sources'])}
    tasks = list(task_versions.values())
    tasks.sort(key=lambda t: (t.get('change_from_previous_source') not in ('new', 'changed'),
                              not bool(t['candidate']), -source_order[t['source_label']], t['path']))
    result['ready_tasks'] = tasks[:max_ready_tasks]
    if runtime_blocker:
        result['blocked_tasks'].append({'kind': 'runtime', 'reason': runtime_blocker,
                                        'blocks_offline_tasks': False})
    result['limits'] = {'max_files': max_files, 'max_file_bytes': max_file_bytes,
                        'max_total_bytes': max_total_bytes, 'bytes_read': max_total_bytes-bytes_left,
                        'files_observed': sum(len(s['files']) for s in result['sources']),
                        'max_ready_tasks': max_ready_tasks, 'ready_tasks_total': len(tasks),
                        'ready_tasks_omitted': max(0, len(tasks)-max_ready_tasks)}
    result['status'] = 'partial' if result['errors'] or any(s['files_truncated'] for s in result['sources']) else 'ready'
    return result


def read_record_rows(path, *, stride, source_label, name_offset=None, name_length=48,
                     start=0, limit=256, max_file_bytes=4194304):
    """Read a bounded raw-preserving census using an explicitly chosen stride.

    ``raw_hex`` concatenation plus ``trailing_hex`` reconstructs the full source
    only when ``complete`` is true. Partial censuses expose the remaining row
    count. A name is an ASCII observation, never proof that a slot is occupied.
    """
    _integer(stride, 'stride', 1, 65536)
    _label(source_label)
    _integer(start, 'start', 0, 1048576)
    _integer(limit, 'limit', 1, 4096)
    _integer(max_file_bytes, 'max_file_bytes', 1, 16777216)
    _integer(name_length, 'name_length', 1, 4096)
    if name_offset is not None:
        _integer(name_offset, 'name_offset', 0, stride-1)
    path = Path(path).expanduser().resolve()
    data, stat = _read(path, max_file_bytes)
    count, remainder = divmod(len(data), stride)
    if start > count:
        raise ValueError('start is past the final full record')
    end = min(count, start + limit)
    rows = []
    for index in range(start, end):
        offset = index * stride
        raw = data[offset:offset + stride]
        row = {'index': index, 'offset': offset, 'raw_hex': raw.hex()}
        if name_offset is not None:
            value = raw[name_offset:min(stride, name_offset + name_length)].split(b'\0', 1)[0]
            row['name_bytes_hex'] = value.hex()
            row['name'] = value.decode('ascii') if all(32 <= b < 127 for b in value) else None
        rows.append(row)
    return {'source': _source(path, source_label, data, stat), 'stride': stride,
            'record_count': count, 'rows': rows, 'start': start, 'next_row': end if end < count else None,
            'complete': start == 0 and end == count, 'trailing_offset': count*stride,
            'trailing_hex': data[count*stride:].hex() if remainder else '',
            'claim': 'Raw rows under a selected candidate layout; occupancy and field meanings are not inferred.'}
