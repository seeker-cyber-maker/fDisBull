"""Bounded, commandless intake of retained production CI failure hints.

This module reads only compact export descriptors. Provider status, authority,
and terminal outcome must be established by a separate canonical adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time


GITLAB_SCHEMA = 'fdisbull-ovh-result-export-v1'
GITHUB_SCHEMA = 'fdisbull-production-job-export-1'
HINT_SCHEMA = 'fdisbull-production-failure-hint-1'
INBOX_SCHEMA = 'fdisbull-production-failure-inbox-1'
MAX_LIMIT = 32
MAX_SCAN = 256
MAX_METADATA_BYTES = 64 * 1024
MAX_POSTCHECK_BYTES = 64 * 1024
MAX_INVENTORY_BYTES = 1024 * 1024
MAX_INVENTORY_ITEMS = 4096
MAX_DIAGNOSTICS = 64
MAX_DESCRIPTOR_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 8192
MAX_RECEIPTS_PER_EVENT = 64

_SAFE_REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
_SHA = re.compile(r'[0-9a-f]{40}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_NUMERIC_DIR = re.compile(r'[1-9][0-9]*\Z')
_NONTERMINAL = {'created', 'pending', 'running', 'in_progress', 'preparing',
                'waiting_for_resource', 'queued', 'requested', 'manual', 'scheduled', 'delayed'}
_SUCCESS = {'success', 'succeeded', 'passed'}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _safe_tree_path(root: Path, path: Path) -> bool:
    """Reject symlink roots/components and paths escaping the configured root."""
    try:
        root_abs = Path(os.path.abspath(root))
        path_abs = Path(os.path.abspath(path))
        path_abs.relative_to(root_abs)
    except (OSError, ValueError):
        return False
    for ancestor in (root_abs, *root_abs.parents):
        if ancestor.is_symlink():
            return False
    current = root_abs
    try:
        for part in path_abs.relative_to(root_abs).parts:
            current = current / part
            if current.is_symlink():
                return False
    except ValueError:
        return False
    return True


def _read_json(path: Path, root: Path, maximum: int):
    if not _safe_tree_path(root, path) or not path.is_file():
        raise ValueError('unsafe_or_missing_file')
    size = path.stat().st_size
    if size < 1 or size > maximum:
        raise ValueError('file_size_out_of_bounds')
    data = path.read_bytes()
    if len(data) != size:
        raise ValueError('file_changed_during_read')
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError('invalid_json') from None
    if not isinstance(value, dict) and path.name != 'inventory.json':
        raise ValueError('invalid_json_shape')
    return value, data


def _epoch(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value >= 0 else None
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        result = parsed.astimezone(timezone.utc).timestamp()
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, OverflowError):
        return None


def _safe_relative(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        return False
    if value.startswith('/') or '\\' in value or '\x00' in value:
        return False
    parts = value.split('/')
    return all(part not in ('', '.', '..') for part in parts)


def _inventory(path: Path, root: Path):
    """Read and validate the small closed inventory manifest, never its payloads."""
    if not path.exists() and not path.is_symlink():
        return None
    value, data = _read_json(path, root, MAX_INVENTORY_BYTES)
    if not isinstance(value, list) or len(value) > MAX_INVENTORY_ITEMS:
        raise ValueError('invalid_inventory_shape')
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {'path', 'size', 'sha256'}:
            raise ValueError('invalid_inventory_item')
        if (not _safe_relative(item['path']) or item['path'] in seen
                or type(item['size']) is not int or item['size'] < 0
                or not isinstance(item['sha256'], str) or not _HASH.fullmatch(item['sha256'])):
            raise ValueError('invalid_inventory_item')
        seen.add(item['path'])
    return {'path': str(path), 'size': len(data), 'sha256': _digest(data), 'items': len(value)}


def _postcheck(path: Path, root: Path, source_sha: str):
    if not path.exists() and not path.is_symlink():
        return None
    value, data = _read_json(path, root, MAX_POSTCHECK_BYTES)
    if (value.get('source_commit') != source_sha
            or value.get('expected_source_commit') != source_sha
            or type(value.get('tracked_worktree_dirty')) is not bool
            or type(value.get('export_success')) is not bool):
        raise ValueError('invalid_source_postcheck')
    return {'path': str(path), 'size': len(data), 'sha256': _digest(data),
            'export_success': value['export_success'],
            'tracked_worktree_dirty': value['tracked_worktree_dirty']}


def _terminal_hint(status):
    if not isinstance(status, str) or not status or len(status) > 64:
        return None
    normalized = status.casefold()
    if normalized in _SUCCESS or normalized in _NONTERMINAL:
        return None
    if normalized in {'failed', 'failure', 'timed_out', 'timeout', 'action_required'}:
        return 'failed'
    if normalized in {'canceled', 'cancelled'}:
        return 'canceled'
    return 'unknown_terminal'


def _event_key(provider: str, namespace: str, run_id: str, attempt, job_id: str, source_sha: str):
    key = [provider, namespace, run_id, attempt, job_id, source_sha]
    return _digest(_json_bytes(key))


def _candidate(provider, namespace, run_id, attempt, job_id, source_sha, job_name,
               status, finished_epoch, metadata_path, metadata_data, postcheck, inventory,
               producer_fields):
    key = _event_key(provider, namespace, run_id, attempt, job_id, source_sha)
    return {
        'schema': HINT_SCHEMA,
        'event_key': key,
        'verification': 'unverified_hint',
        'provider': provider,
        'project_or_repository': namespace,
        'run_id': run_id,
        'attempt': attempt,
        'job_id': job_id,
        'source_sha': source_sha,
        'job_name': job_name,
        'reported_status': status,
        'finished_epoch': finished_epoch,
        'metadata_path': str(metadata_path),
        'metadata_sha256': _digest(metadata_data),
        'source_postcheck': postcheck,
        'inventory': inventory,
        'producer_fields': producer_fields,
    }


def _candidate_from_gitlab(root, pipeline_dir, job_dir, project_id, activated_epoch):
    meta_path = job_dir / 'job.json'
    meta, data = _read_json(meta_path, root, MAX_METADATA_BYTES)
    if meta.get('schema') != GITLAB_SCHEMA:
        raise ValueError('wrong_gitlab_schema')
    pipeline, job = pipeline_dir.name, job_dir.name
    if (not _NUMERIC_DIR.fullmatch(pipeline) or not _NUMERIC_DIR.fullmatch(job)
            or meta.get('pipeline_id') != pipeline or meta.get('job_id') != job):
        raise ValueError('gitlab_path_identity_mismatch')
    source_sha = meta.get('source_commit')
    job_name = meta.get('job_name')
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise ValueError('invalid_source_sha')
    if not isinstance(job_name, str) or not job_name or len(job_name) > 200 or any(ord(c) < 32 for c in job_name):
        raise ValueError('invalid_job_name')
    reported = meta.get('job_status')
    if not isinstance(reported, str) or not reported or len(reported) > 64:
        raise ValueError('invalid_reported_status')
    if 'export_success' in meta and type(meta['export_success']) is not bool:
        raise ValueError('invalid_export_success')
    if 'files' in meta and (type(meta['files']) is not int or meta['files'] < 0):
        raise ValueError('invalid_file_count')
    status = _terminal_hint(reported)
    if status is None:
        return None
    finished = _epoch(meta.get('finished_at'))
    if finished is None:
        raise ValueError('unknown_finished_time')
    if finished < activated_epoch:
        return None
    if not isinstance(project_id, str) or not project_id.isdecimal() or int(project_id) <= 0:
        raise ValueError('gitlab_project_namespace_required')
    post = _postcheck(job_dir / 'source-postcheck.json', root, source_sha)
    inventory = _inventory(job_dir / 'inventory.json', root)
    producer_fields = {}
    if 'export_success' in meta:
        producer_fields['export_success'] = meta['export_success']
    if 'files' in meta:
        producer_fields['files'] = meta['files']
    return _candidate('gitlab', str(int(project_id)), pipeline, None, job, source_sha,
                       job_name, status, finished, meta_path, data, post, inventory,
                       producer_fields)


def _candidate_from_github(root, run_dir, attempt_dir, job_dir, repository, activated_epoch):
    meta_path = job_dir / 'job.json'
    meta, data = _read_json(meta_path, root, MAX_METADATA_BYTES)
    if meta.get('schema') != GITHUB_SCHEMA:
        raise ValueError('wrong_github_schema')
    run_id, attempt, job = run_dir.name, attempt_dir.name, job_dir.name
    if (not all(_NUMERIC_DIR.fullmatch(v) for v in (run_id, attempt, job))
            or meta.get('run_id') != run_id or meta.get('run_attempt') != attempt
            or meta.get('job_id') != job):
        raise ValueError('github_path_identity_mismatch')
    repo = meta.get('repository')
    if (not isinstance(repository, str) or not _SAFE_REPO.fullmatch(repository)
            or repo != repository):
        raise ValueError('github_repository_namespace_missing_or_mismatch')
    source_sha = meta.get('source_sha')
    job_name = meta.get('job_name')
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise ValueError('invalid_source_sha')
    if not isinstance(job_name, str) or not job_name or len(job_name) > 200 or any(ord(c) < 32 for c in job_name):
        raise ValueError('invalid_job_name')
    reported = meta.get('job_status')
    if not isinstance(reported, str) or not reported or len(reported) > 64:
        raise ValueError('invalid_reported_status')
    status = _terminal_hint(reported)
    if status is None:
        return None
    finished = _epoch(meta.get('finished_at'))
    if finished is None:
        raise ValueError('unknown_finished_time')
    if finished < activated_epoch:
        return None
    post = _postcheck(job_dir / 'source-postcheck.json', root, source_sha)
    inventory = _inventory(job_dir / 'inventory.json', root)
    producer_fields = {}
    for name in ('control_sha', 'ref', 'runner_id', 'export_success', 'qualification_exit_code', 'files'):
        value = meta.get(name)
        if name in ('control_sha',) and value is not None and (not isinstance(value, str) or not _SHA.fullmatch(value)):
            raise ValueError('invalid_control_sha')
        if name == 'ref' and value is not None and (not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value)):
            raise ValueError('invalid_ref')
        if name == 'runner_id' and value is not None and (isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isdecimal()):
            raise ValueError('invalid_runner_id')
        if name == 'export_success' and value is not None and type(value) is not bool:
            raise ValueError('invalid_export_success')
        if name in ('qualification_exit_code', 'files') and value is not None and (type(value) is not int or value < 0):
            raise ValueError('invalid_numeric_producer_field')
        if value is not None:
            producer_fields[name] = str(value) if name == 'runner_id' else value
    return _candidate('github', repository, run_id, str(int(attempt)), job, source_sha,
                       job_name, status, finished, meta_path, data, post, inventory,
                       producer_fields)


def export_candidates(root, activated_epoch, limit=32, *, gitlab_project_id=None,
                      github_repository=None):
    """Return bounded failed-job hints from the two known export layouts.

    Entries before activation, successful jobs, and nonterminal statuses are
    ignored. Malformed or unnamespaced entries appear only as compact
    diagnostics. No provider status is inferred from these files.
    """
    if (isinstance(activated_epoch, bool) or not isinstance(activated_epoch, (int, float))
            or not math.isfinite(activated_epoch) or activated_epoch < 0):
        raise ValueError('invalid activation epoch')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError('limit must be between 1 and 32')
    root = Path(root)
    if root.is_symlink() or not root.exists() or not root.is_dir():
        raise ValueError('export root must be an existing non-symlink directory')
    if gitlab_project_id is not None and (isinstance(gitlab_project_id, bool)
            or not isinstance(gitlab_project_id, (str, int)) or not str(gitlab_project_id).isdecimal()
            or int(gitlab_project_id) <= 0):
        raise ValueError('invalid GitLab project namespace')
    if gitlab_project_id is not None:
        gitlab_project_id = str(int(gitlab_project_id))
    if github_repository is not None and (not isinstance(github_repository, str)
            or not _SAFE_REPO.fullmatch(github_repository)):
        raise ValueError('invalid GitHub repository namespace')

    candidates, diagnostics = [], []
    examined = 0

    def diagnostic(provider, path, reason):
        if len(diagnostics) < MAX_DIAGNOSTICS:
            try: relative = str(Path(path).relative_to(root))
            except ValueError: relative = '<outside-root>'
            diagnostics.append({'provider': provider, 'path': relative, 'state': 'unknown', 'reason': reason})

    def dirs(path, pattern=None):
        if not _safe_tree_path(root, path) or not path.is_dir():
            return []
        provider = 'github' if 'github' in path.relative_to(root).parts else 'gitlab'
        entries = []
        try:
            with os.scandir(path) as scan:
                for entry in scan:
                    if pattern and not pattern.fullmatch(entry.name):
                        continue
                    if entry.is_symlink():
                        diagnostic(provider, path / entry.name, 'symlink_directory')
                        continue
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        continue
                    entries.append(entry.name)
                    if len(entries) >= MAX_SCAN:
                        break
        except OSError:
            diagnostic(provider, path, 'directory_unreadable')
            return []
        return sorted(entries, key=lambda value: (int(value) if value.isdecimal() else -1, value), reverse=True)

    def maybe_add(provider, fn, args, path):
        nonlocal examined
        if examined >= MAX_SCAN or len(candidates) >= limit:
            return
        examined += 1
        try:
            candidate = fn(*args)
            if candidate is not None:
                candidates.append(candidate)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            diagnostic(provider, path, str(exc) if str(exc) in {
                'unsafe_or_missing_file', 'file_size_out_of_bounds', 'file_changed_during_read',
                'invalid_json', 'invalid_json_shape', 'wrong_gitlab_schema', 'wrong_github_schema',
                'gitlab_path_identity_mismatch', 'github_path_identity_mismatch', 'invalid_source_sha',
                'invalid_job_name', 'invalid_reported_status', 'invalid_file_count',
                'unknown_finished_time', 'gitlab_project_namespace_required',
                'github_repository_namespace_missing_or_mismatch', 'invalid_source_postcheck',
                'invalid_inventory_shape', 'invalid_inventory_item', 'invalid_control_sha', 'invalid_ref',
                'invalid_runner_id', 'invalid_export_success', 'invalid_numeric_producer_field'} else 'invalid_or_unreadable_metadata')

    for pipeline_name in dirs(root, _NUMERIC_DIR):
        pipeline_dir = root / pipeline_name
        for job_name in dirs(pipeline_dir, _NUMERIC_DIR):
            job_dir = pipeline_dir / job_name
            maybe_add('gitlab', _candidate_from_gitlab,
                      (root, pipeline_dir, job_dir, gitlab_project_id, float(activated_epoch)), job_dir)
            if examined >= MAX_SCAN or len(candidates) >= limit:
                break
        if examined >= MAX_SCAN or len(candidates) >= limit:
            break

    github_root = root / 'github'
    if len(candidates) < limit and examined < MAX_SCAN and github_root.exists():
        for run_name in dirs(github_root, _NUMERIC_DIR):
            run_dir = github_root / run_name
            for attempt_name in dirs(run_dir, _NUMERIC_DIR):
                attempt_dir = run_dir / attempt_name
                qualification = attempt_dir / 'qualification'
                for job_name in dirs(qualification, _NUMERIC_DIR):
                    job_dir = qualification / job_name
                    maybe_add('github', _candidate_from_github,
                              (root, run_dir, attempt_dir, job_dir, github_repository, float(activated_epoch)), job_dir)
                    if examined >= MAX_SCAN or len(candidates) >= limit:
                        break
                if examined >= MAX_SCAN or len(candidates) >= limit:
                    break
            if examined >= MAX_SCAN or len(candidates) >= limit:
                break

    return {'schema': HINT_SCHEMA, 'candidates': candidates[:limit],
            'diagnostics': diagnostics, 'scanned_entries': examined,
            'truncated': examined >= MAX_SCAN or len(candidates) >= limit}


class FailureInbox:
    """SQLite-backed immutable queue with durable claims and no auto-replay."""

    def __init__(self, path, *, max_events=1024, max_descriptor_bytes=MAX_DESCRIPTOR_BYTES,
                 max_receipt_bytes=MAX_RECEIPT_BYTES):
        if type(max_events) is not int or not 1 <= max_events <= 100_000:
            raise ValueError('invalid inbox capacity')
        if type(max_descriptor_bytes) is not int or not 1024 <= max_descriptor_bytes <= 1024 * 1024:
            raise ValueError('invalid descriptor capacity')
        if type(max_receipt_bytes) is not int or not 512 <= max_receipt_bytes <= 64 * 1024:
            raise ValueError('invalid receipt capacity')
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError('inbox database may not be a symlink')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for ancestor in (self.path.parent, *self.path.parent.parents):
            if ancestor.is_symlink():
                raise ValueError('inbox database path may not contain symlinks')
        for suffix in ('-wal', '-shm'):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.is_symlink():
                raise ValueError('inbox database sidecar may not be a symlink')
        self.max_events = max_events
        self.max_descriptor_bytes = max_descriptor_bytes
        self.max_receipt_bytes = max_receipt_bytes
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(
            event_key TEXT PRIMARY KEY, descriptor BLOB NOT NULL, state TEXT NOT NULL,
            created_epoch REAL NOT NULL, claim_owner TEXT, claim_expires_epoch REAL,
            latest_receipt INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS receipts(
            event_key TEXT NOT NULL REFERENCES events(event_key), seq INTEGER NOT NULL,
            state TEXT NOT NULL, actor TEXT NOT NULL, observed_epoch REAL NOT NULL,
            payload BLOB NOT NULL, PRIMARY KEY(event_key,seq));
          CREATE INDEX IF NOT EXISTS events_by_state ON events(state,created_epoch,event_key);
        ''')
        row = self.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
        if row is None:
            self.db.execute("INSERT INTO metadata(key,value) VALUES('schema',?)", (INBOX_SCHEMA,))
        elif row[0] != INBOX_SCHEMA:
            self.db.close()
            raise ValueError('unsupported inbox schema')
        if self.path.is_symlink():
            self.db.close()
            raise ValueError('inbox database became a symlink')

    def close(self):
        self.db.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    @staticmethod
    def _validate_candidate(candidate):
        if not isinstance(candidate, dict) or candidate.get('schema') != HINT_SCHEMA:
            raise ValueError('invalid candidate schema')
        if set(candidate) != {'schema', 'event_key', 'verification', 'provider',
                'project_or_repository', 'run_id', 'attempt', 'job_id', 'source_sha',
                'job_name', 'reported_status', 'finished_epoch', 'metadata_path',
                'metadata_sha256', 'source_postcheck', 'inventory', 'producer_fields'}:
            raise ValueError('invalid candidate fields')
        if candidate.get('verification') != 'unverified_hint':
            raise ValueError('candidate must remain unverified')
        provider = candidate.get('provider')
        namespace = candidate.get('project_or_repository')
        if provider == 'gitlab':
            if not isinstance(namespace, str) or not namespace.isdecimal() or int(namespace) <= 0:
                raise ValueError('GitLab project namespace missing')
            attempt = candidate.get('attempt')
            if attempt is not None: raise ValueError('GitLab attempt must remain unknown')
        elif provider == 'github':
            if not isinstance(namespace, str) or not _SAFE_REPO.fullmatch(namespace):
                raise ValueError('GitHub repository namespace missing')
            attempt = candidate.get('attempt')
            if not isinstance(attempt, str) or not _NUMERIC_DIR.fullmatch(attempt):
                raise ValueError('GitHub attempt missing')
        else:
            raise ValueError('unsupported provider')
        for name in ('run_id', 'job_id'):
            if not isinstance(candidate.get(name), str) or not _NUMERIC_DIR.fullmatch(candidate[name]):
                raise ValueError('invalid candidate provider identity')
        source_sha = candidate.get('source_sha')
        if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
            raise ValueError('invalid candidate source identity')
        if candidate.get('reported_status') not in ('failed', 'canceled', 'unknown_terminal'):
            raise ValueError('candidate is not a failure hint')
        if not isinstance(candidate.get('job_name'), str) or not candidate['job_name'] or len(candidate['job_name']) > 200:
            raise ValueError('invalid candidate job name')
        if _epoch(candidate.get('finished_epoch')) is None:
            raise ValueError('invalid candidate completion time')
        if not isinstance(candidate.get('metadata_path'), str) or len(candidate['metadata_path']) > 2048:
            raise ValueError('invalid metadata path')
        if (not Path(candidate['metadata_path']).is_absolute()
                or '..' in Path(candidate['metadata_path']).parts
                or any(ord(c) < 32 for c in candidate['metadata_path'])):
            raise ValueError('invalid metadata path')
        if not isinstance(candidate.get('metadata_sha256'), str) or not _HASH.fullmatch(candidate['metadata_sha256']):
            raise ValueError('invalid metadata hash')
        for key in ('source_postcheck', 'inventory'):
            value = candidate.get(key)
            if value is not None and (not isinstance(value, dict)
                    or set(value) != ({'path', 'size', 'sha256', 'export_success', 'tracked_worktree_dirty'}
                                      if key == 'source_postcheck' else {'path', 'size', 'sha256', 'items'})):
                raise ValueError('invalid candidate evidence identity')
            if value is not None and (not isinstance(value['path'], str) or len(value['path']) > 2048
                    or not Path(value['path']).is_absolute() or '..' in Path(value['path']).parts
                    or any(ord(c) < 32 for c in value['path'])
                    or type(value['size']) is not int or value['size'] < 1
                    or not isinstance(value['sha256'], str) or not _HASH.fullmatch(value['sha256'])):
                raise ValueError('invalid candidate evidence identity')
            if key == 'source_postcheck' and value is not None and (
                    type(value['export_success']) is not bool or type(value['tracked_worktree_dirty']) is not bool):
                raise ValueError('invalid source postcheck identity')
            if key == 'inventory' and value is not None and (type(value['items']) is not int or value['items'] < 0):
                raise ValueError('invalid inventory identity')
        if not isinstance(candidate.get('producer_fields'), dict) or set(candidate['producer_fields']) - {
                'export_success', 'files', 'control_sha', 'ref', 'runner_id', 'qualification_exit_code'}:
            raise ValueError('invalid producer fields')
        for key, value in candidate['producer_fields'].items():
            if key == 'export_success' and type(value) is not bool:
                raise ValueError('invalid producer field')
            if key in ('files', 'qualification_exit_code') and (type(value) is not int or value < 0):
                raise ValueError('invalid producer field')
            if key == 'control_sha' and (not isinstance(value, str) or not _SHA.fullmatch(value)):
                raise ValueError('invalid producer field')
            if key == 'runner_id' and (not isinstance(value, str) or not value.isdecimal()):
                raise ValueError('invalid producer field')
            if key == 'ref' and (not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value)):
                raise ValueError('invalid producer field')
        expected = _event_key(provider, namespace, candidate['run_id'], attempt,
                              candidate['job_id'], source_sha)
        if candidate.get('event_key') != expected:
            raise ValueError('event key mismatch')

    def _receipt(self, event_key, state, actor, payload, now):
        if (not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', actor)
                or isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0):
            raise ValueError('invalid receipt actor/time')
        if not isinstance(payload, dict) or set(payload) - {
            'kind', 'reason', 'status', 'provider_receipt_path', 'canonical_status',
            'canonical_source_sha', 'observed_epoch', 'verification', 'claim_expires_epoch',
            'parent_event_key', 'parent_state_path', 'parent_state_sha256', 'evidence_receipt_path', 'evidence_receipt_sha256'
        }:
            raise ValueError('receipt fields are not allowlisted')
        if not isinstance(payload.get('kind'), str) or not payload['kind'] or len(payload['kind']) > 64:
            raise ValueError('receipt kind required')
        for key, value in payload.items():
            if isinstance(value, str) and (len(value) > 1024 or any(ord(c) < 32 for c in value)):
                raise ValueError('invalid receipt value')
            if key == 'observed_epoch' and _epoch(value) is None:
                raise ValueError('invalid receipt epoch')
            if key in ('parent_event_key','parent_state_sha256','evidence_receipt_sha256') and (not isinstance(value,str) or not _HASH.fullmatch(value)):
                raise ValueError('invalid related evidence hash')
            if key in ('parent_state_path','evidence_receipt_path') and (not isinstance(value,str) or not Path(value).is_absolute() or '..' in Path(value).parts):
                raise ValueError('invalid related evidence path')
            if key == 'canonical_source_sha' and (not isinstance(value, str) or not _SHA.fullmatch(value)):
                raise ValueError('invalid receipt source sha')
            if key in ('reason', 'status', 'provider_receipt_path', 'canonical_status', 'verification') and not isinstance(value, str):
                raise ValueError('invalid receipt field type')
            if key == 'claim_expires_epoch' and _epoch(value) is None:
                raise ValueError('invalid receipt claim expiry')
        data = _json_bytes(payload)
        if len(data) > self.max_receipt_bytes:
            raise ValueError('receipt exceeds configured bound')
        row = self.db.execute('SELECT COUNT(*),COALESCE(MAX(seq),0)+1 FROM receipts WHERE event_key=?', (event_key,)).fetchone()
        if row[0] >= MAX_RECEIPTS_PER_EVENT:
            raise OverflowError('event receipt capacity full')
        seq = row[1]
        self.db.execute('INSERT INTO receipts(event_key,seq,state,actor,observed_epoch,payload) VALUES(?,?,?,?,?,?)',
                        (event_key, seq, state, actor, float(now), data))
        self.db.execute('UPDATE events SET latest_receipt=? WHERE event_key=?', (seq, event_key))
        return {'seq': seq, 'state': state, 'actor': actor, 'observed_epoch': float(now), 'payload': payload}

    def enqueue(self, candidate, *, now=None):
        self._validate_candidate(candidate)
        data = _json_bytes(candidate)
        if len(data) > self.max_descriptor_bytes:
            raise ValueError('candidate descriptor exceeds configured bound')
        now = time.time() if now is None else now
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            raise ValueError('invalid enqueue time')
        key = candidate['event_key']
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT descriptor,state FROM events WHERE event_key=?', (key,)).fetchone()
            if old:
                if bytes(old[0]) != data:
                    raise ValueError('event key conflicts with immutable payload')
                result = {'event_key': key, 'state': old[1], 'duplicate': True}
                self.db.execute('COMMIT')
                return result
            count = self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            if count >= self.max_events:
                raise OverflowError('failure inbox capacity full')
            self.db.execute('INSERT INTO events(event_key,descriptor,state,created_epoch) VALUES(?,?,?,?)',
                            (key, data, 'pending', float(now)))
            self._receipt(key, 'pending', 'intake', {'kind': 'enqueued', 'verification': 'unverified_hint'}, now)
            self.db.execute('COMMIT')
            return {'event_key': key, 'state': 'pending', 'duplicate': False}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def related_attention(self, candidate, proof, *, now=None):
        """Close only an unclaimed pending hint linked to a terminal parent."""
        self._validate_candidate(candidate)
        fields={'parent_event_key','parent_state_path','parent_state_sha256','evidence_receipt_path','evidence_receipt_sha256'}
        if not isinstance(proof,dict) or set(proof)!=fields or proof['parent_event_key']==candidate['event_key']:
            raise ValueError('invalid related incident proof')
        now=time.time() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            parent=self.db.execute('SELECT state FROM events WHERE event_key=?',(proof['parent_event_key'],)).fetchone()
            child=self.db.execute('SELECT descriptor,state FROM events WHERE event_key=?',(candidate['event_key'],)).fetchone()
            if (not parent or parent[0] not in ('complete','attention') or not child
                    or bytes(child[0])!=_json_bytes(candidate) or child[1]!='pending'):
                self.db.execute('COMMIT');return False
            self.db.execute("UPDATE events SET state='attention' WHERE event_key=? AND state='pending'",(candidate['event_key'],))
            self._receipt(candidate['event_key'],'attention','intake',
                          {'kind':'related_failed_attempt','status':'attention','verification':'retained_canonical_failure',**proof},now)
            self.db.execute('COMMIT');return True
        except Exception:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def claim(self, owner, *, now=None, lease_seconds=300):
        if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', owner):
            raise ValueError('invalid claim owner')
        now = time.time() if now is None else now
        if (isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now)
                or now < 0 or isinstance(lease_seconds, bool) or not isinstance(lease_seconds, (int, float))
                or not math.isfinite(lease_seconds) or not 1 <= lease_seconds <= 3600):
            raise ValueError('invalid claim clock/lease')
        now, expires = float(now), float(now + lease_seconds)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            unresolved = self.db.execute(
                "SELECT event_key,claim_owner,descriptor FROM events WHERE state='needs_reconciliation' ORDER BY created_epoch,event_key LIMIT 1"
            ).fetchone()
            if unresolved:
                key, old_owner, descriptor = unresolved
                rec = self._latest_receipt(key)
                self.db.execute('COMMIT')
                return {'event_key': key, 'state': 'needs_reconciliation',
                        'previous_owner': old_owner, 'candidate': json.loads(bytes(descriptor)),
                        'receipt': rec}
            expired = self.db.execute(
                "SELECT event_key,claim_owner,descriptor FROM events WHERE state='claimed' AND claim_expires_epoch<=? ORDER BY created_epoch,event_key LIMIT 1",
                (now,)).fetchone()
            if expired:
                key, old_owner, descriptor = expired
                self.db.execute("UPDATE events SET state='needs_reconciliation' WHERE event_key=? AND state='claimed'", (key,))
                rec = self._receipt(key, 'needs_reconciliation', 'inbox',
                                    {'kind': 'claim_expired', 'reason': 'canonical_reconciliation_required'}, now)
                self.db.execute('COMMIT')
                return {'event_key': key, 'state': 'needs_reconciliation',
                        'previous_owner': old_owner, 'candidate': json.loads(bytes(descriptor)),
                        'receipt': rec}
            row = self.db.execute("SELECT event_key,descriptor FROM events WHERE state='pending' ORDER BY created_epoch,event_key LIMIT 1").fetchone()
            if not row:
                self.db.execute('COMMIT')
                return None
            key, descriptor = row
            changed = self.db.execute("UPDATE events SET state='claimed',claim_owner=?,claim_expires_epoch=? WHERE event_key=? AND state='pending'",
                                      (owner, expires, key)).rowcount
            if changed != 1:
                raise RuntimeError('claim race')
            rec = self._receipt(key, 'claimed', owner,
                                {'kind': 'claim', 'claim_expires_epoch': expires,
                                 'verification': 'unverified_hint'}, now)
            self.db.execute('COMMIT')
            return {'event_key': key, 'state': 'claimed', 'owner': owner,
                    'expires_epoch': expires, 'candidate': json.loads(bytes(descriptor)),
                    'receipt': rec}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def _finish(self, event_key, state, owner, receipt, *, now=None):
        if not isinstance(event_key, str) or not _HASH.fullmatch(event_key):
            raise ValueError('invalid event key')
        if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', owner):
            raise ValueError('invalid actor')
        if state == 'complete' and (not isinstance(receipt, dict)
                or receipt.get('verification') != 'canonical_terminal'):
            raise ValueError('complete requires canonical terminal verification')
        now = time.time() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT state,claim_owner,claim_expires_epoch FROM events WHERE event_key=?',
                                  (event_key,)).fetchone()
            if not row: raise KeyError('unknown event key')
            old_state, old_owner, expires = row
            if old_state != 'claimed' or old_owner != owner:
                raise ValueError('event is not claimed by this owner')
            if expires is None or expires <= now:
                self.db.execute("UPDATE events SET state='needs_reconciliation' WHERE event_key=?", (event_key,))
                rec = self._receipt(event_key, 'needs_reconciliation', 'inbox',
                                    {'kind': 'claim_expired', 'reason': 'canonical_reconciliation_required'}, now)
                self.db.execute('COMMIT')
                return {'event_key': event_key, 'state': 'needs_reconciliation', 'receipt': rec}
            self.db.execute('UPDATE events SET state=?,claim_owner=NULL,claim_expires_epoch=NULL WHERE event_key=?',
                            (state, event_key))
            rec = self._receipt(event_key, state, owner, receipt, now)
            self.db.execute('COMMIT')
            return {'event_key': event_key, 'state': state, 'receipt': rec}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def complete(self, event_key, owner, receipt, *, now=None):
        return self._finish(event_key, 'complete', owner, receipt, now=now)

    def attention(self, event_key, owner, receipt, *, now=None):
        return self._finish(event_key, 'attention', owner, receipt, now=now)

    def resolve_reconciliation(self, event_key, owner, state, receipt, *, now=None):
        if state not in ('pending', 'complete', 'attention'):
            raise ValueError('invalid reconciliation state')
        if not isinstance(receipt, dict):
            raise ValueError('invalid reconciliation receipt')
        if state == 'pending' and receipt.get('verification') != 'canonical_no_action':
            raise ValueError('return to pending requires canonical no-action proof')
        if state == 'complete' and receipt.get('verification') != 'canonical_terminal':
            raise ValueError('complete reconciliation requires canonical terminal proof')
        if not isinstance(event_key, str) or not _HASH.fullmatch(event_key):
            raise ValueError('invalid event key')
        if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', owner):
            raise ValueError('invalid actor')
        now = time.time() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT state,claim_owner FROM events WHERE event_key=?', (event_key,)).fetchone()
            if not row: raise KeyError('unknown event key')
            if row[0] != 'needs_reconciliation' or row[1] != owner:
                raise ValueError('event does not require this owner reconciliation')
            self.db.execute('UPDATE events SET state=?,claim_owner=NULL,claim_expires_epoch=NULL WHERE event_key=?',
                            (state, event_key))
            rec = self._receipt(event_key, state, owner, receipt, now)
            self.db.execute('COMMIT')
            return {'event_key': event_key, 'state': state, 'receipt': rec}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def get(self, event_key):
        row = self.db.execute('SELECT descriptor,state,claim_owner,claim_expires_epoch,latest_receipt FROM events WHERE event_key=?',
                              (event_key,)).fetchone()
        if not row: return None
        receipt = self._latest_receipt(event_key) if row[4] else None
        return {'candidate':json.loads(bytes(row[0])),'state':row[1],
                'claim_owner':row[2],'claim_expires_epoch':row[3],'receipt':receipt}

    def _latest_receipt(self, event_key):
        row = self.db.execute('SELECT seq,state,actor,observed_epoch,payload FROM receipts WHERE event_key=? ORDER BY seq DESC LIMIT 1',
                              (event_key,)).fetchone()
        if not row: return None
        return {'seq':row[0],'state':row[1],'actor':row[2],
                'observed_epoch':row[3],'payload':json.loads(bytes(row[4]))}


__all__ = ['FailureInbox', 'export_candidates']
