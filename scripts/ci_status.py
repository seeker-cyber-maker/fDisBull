#!/usr/bin/env python3
"""Read a shared CI snapshot, or let its owner make one bounded refresh.

This development helper reports observations, never acceptance or release
qualification. It has no watch, force, retry, owner takeover, or resume mode.
Supports both GitLab (gitlab.com, active 30-day trial) and GitHub (portable
fallback / unit-test compatibility).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import quote

try:
    import fcntl
except ImportError:
    fcntl = None

INTERVAL_SECONDS = 300
FETCH_TIMEOUT_SECONDS = 30
PAGE_SIZE = 100
SCHEMA = 1


class StatusError(ValueError):
    pass


class FetchError(Exception):
    def __init__(self, code, provider_stop=False):
        super().__init__(code)
        self.code, self.provider_stop = code, provider_stop


def _identity(repo, sha, host, owner, refresh):
    if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', repo):
        raise StatusError('repo must be an explicit OWNER/REPOSITORY')
    if repo.count('/') != 1 and 'gitlab' not in str(host).lower():
        raise StatusError('repo must be an explicit OWNER/REPOSITORY')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise StatusError('sha must contain exactly 40 hexadecimal characters')
    if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
        raise StatusError('host must be an explicit hostname without a scheme or path')
    if owner is not None and (not isinstance(owner, str) or not 1 <= len(owner) <= 128
                              or owner.strip() != owner or any(ord(c) < 32 or ord(c) == 127 for c in owner)):
        raise StatusError('owner must contain 1..128 printable characters')
    if refresh and owner is None:
        raise StatusError('refresh requires an owner ID')
    return repo.lower(), sha.lower(), host.lower()


def default_state_dir(cwd=None):
    """Sibling worktrees resolve to the same ordinary Git common directory."""
    result = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                            cwd=cwd, capture_output=True, text=True, timeout=5, check=True)
    return Path(result.stdout.strip()).resolve() / 'fdisbull-ci-status'


def _read(path):
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise StatusError('invalid local CI state file')
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise StatusError('unreadable local CI state; no refresh attempted') from exc
    if not isinstance(value, dict):
        raise StatusError('invalid local CI state')
    return value


def _write(path, value):
    """Make a reservation durable before starting the external operation."""
    fd, name = tempfile.mkstemp(prefix='.ci-status-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, separators=(',', ':'), allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def _locked(directory):
    if fcntl is None:
        raise StatusError('process-safe CI status locking is unavailable')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / '.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _restricted(message):
    message = message.lower()
    return any(s in message for s in ('account has been flagged', 'account is flagged',
                                     'account is restricted', 'account has been restricted',
                                     'owner is restricted', 'owner has been restricted',
                                     'owner has been flagged', 'owner is flagged',
                                     'account is currently restricted', 'owner is currently restricted',
                                     'owner marked spammy', 'owner has been marked spammy',
                                     'actions has been disabled for this user',
                                     'account has been suspended', 'account is suspended',
                                     'account has been blocked', 'user is blocked',
                                     'pipeline minutes quota', 'ci/cd minutes quota'))


def _is_gitlab_host(host):
    return 'gitlab' in host.lower()


def _normalize_gitlab_pipelines(rows, sha):
    """Convert a GitLab /projects/:id/pipelines JSON list into workflow_runs shape."""
    if not isinstance(rows, list):
        raise FetchError('invalid_provider_shape')
    if len(rows) > PAGE_SIZE:
        raise FetchError('invalid_provider_count')
    status_map = {
        'success': ('completed', 'success'),
        'failed': ('completed', 'failure'),
        'canceled': ('completed', 'cancelled'),
        'skipped': ('completed', 'skipped'),
        'manual': ('waiting', None),
        'scheduled': ('queued', None),
        'created': ('queued', None),
        'waiting_for_resource': ('queued', None),
        'preparing': ('queued', None),
        'pending': ('queued', None),
        'running': ('in_progress', None),
    }
    workflow_runs = []
    for item in rows:
        if not isinstance(item, dict):
            raise FetchError('invalid_provider_shape')
        raw_status = str(item.get('status') or '')
        mapped_status, conclusion = status_map.get(raw_status, (raw_status or 'unknown', None))
        workflow_runs.append({
            'id': item.get('id'),
            'workflow_id': item.get('iid', item.get('id')),
            'name': f"GitLab Pipeline ({item.get('ref') or 'unknown'})",
            'event': item.get('source') or 'gitlab_pipeline',
            'status': mapped_status,
            'conclusion': conclusion,
            'run_attempt': 1,
            'head_sha': item.get('sha'),
        })
    return {'total_count': len(workflow_runs), 'workflow_runs': workflow_runs}


def fetch_gitlab_runs(host, repo, sha):
    """Exactly one glab api invocation; no pagination or application-level retry."""
    encoded_repo = quote(repo, safe='')
    endpoint = f'projects/{encoded_repo}/pipelines?sha={sha}&per_page={PAGE_SIZE}'
    env = dict(os.environ, GLAB_CHECK_UPDATE='false', NO_PROMPT='1', GLAB_PAGER='cat')
    env.pop('GLAB_DEBUG', None)
    try:
        result = subprocess.run(['glab', 'api', '--hostname', host, '--method', 'GET', endpoint],
                                capture_output=True, text=True, timeout=FETCH_TIMEOUT_SECONDS, env=env)
    except subprocess.TimeoutExpired as exc:
        raise FetchError('provider_timeout') from exc
    except UnicodeError as exc:
        raise FetchError('invalid_provider_output') from exc
    except OSError as exc:
        raise FetchError('provider_command_unavailable') from exc
    if result.returncode:
        message = result.stderr + '\n' + result.stdout
        code = re.search(r'HTTP\s+(401|403|429)\b', message, re.IGNORECASE)
        if code:
            raise FetchError('provider_http_' + code[1], provider_stop=True)
        if _restricted(message):
            raise FetchError('provider_restriction', provider_stop=True)
        if 'glab auth login' in message.lower() or 'not logged into' in message.lower():
            raise FetchError('provider_authentication_required', provider_stop=True)
        raise FetchError('provider_request_failed')
    try:
        document = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise FetchError('invalid_provider_json') from exc
    if isinstance(document, dict):
        if _restricted(str(document.get('message', ''))):
            raise FetchError('provider_restriction', provider_stop=True)
        if 'workflow_runs' in document:
            return document
        raise FetchError('invalid_provider_shape')
    return _normalize_gitlab_pipelines(document, sha)


def fetch_runs(host, repo, sha):
    """Exactly one provider API invocation."""
    if _is_gitlab_host(host):
        return fetch_gitlab_runs(host, repo, sha)
    endpoint = f'repos/{repo}/actions/runs?head_sha={sha}&per_page={PAGE_SIZE}'
    env = dict(os.environ, GH_PROMPT_DISABLED='1', GH_PAGER='cat')
    # Debug output can contain request details; it is neither needed nor stored.
    env.pop('GH_DEBUG', None)
    try:
        result = subprocess.run(['gh', 'api', '--hostname', host, '--method', 'GET', endpoint],
                                capture_output=True, text=True, timeout=FETCH_TIMEOUT_SECONDS, env=env)
    except subprocess.TimeoutExpired as exc:
        raise FetchError('provider_timeout') from exc
    except UnicodeError as exc:
        raise FetchError('invalid_provider_output') from exc
    except OSError as exc:
        raise FetchError('provider_command_unavailable') from exc
    if result.returncode:
        # Never echo raw stderr, credentials, response bodies or inherited env.
        message = result.stderr + '\n' + result.stdout
        code = re.search(r'HTTP\s+(401|403|429)\b', message, re.IGNORECASE)
        if code:
            raise FetchError('provider_http_' + code[1], provider_stop=True)
        if _restricted(message):
            raise FetchError('provider_restriction', provider_stop=True)
        if 'gh auth login' in message.lower() or 'not logged into' in message.lower():
            raise FetchError('provider_authentication_required', provider_stop=True)
        raise FetchError('provider_request_failed')
    try:
        document = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise FetchError('invalid_provider_json') from exc
    if isinstance(document, dict) and _restricted(str(document.get('message', ''))):
        raise FetchError('provider_restriction', provider_stop=True)
    return document


def _snapshot(document, host, repo, sha, observed):
    if isinstance(document, list) and _is_gitlab_host(host):
        document = _normalize_gitlab_pipelines(document, sha)
    if not isinstance(document, dict) or not isinstance(document.get('workflow_runs'), list):
        raise FetchError('invalid_provider_shape')
    rows, total = document['workflow_runs'], document.get('total_count')
    if type(total) is not int or total < len(rows) or len(rows) > PAGE_SIZE:
        raise FetchError('invalid_provider_count')
    compact, ids = [], set()
    for run in rows:
        if not isinstance(run, dict) or run.get('head_sha') != sha:
            raise FetchError('provider_sha_mismatch')
        if type(run.get('id')) is not int or run['id'] <= 0 or run['id'] in ids:
            raise FetchError('invalid_provider_run_identity')
        ids.add(run['id'])
        compact.append({key: run.get(key) for key in
                        ('id', 'workflow_id', 'name', 'event', 'status', 'conclusion', 'run_attempt', 'head_sha')})
    return dict(schema=SCHEMA, host=host, repo=repo, sha=sha, observed_at=observed,
                observation_status='truncated' if total > len(rows) else 'found' if rows else 'missing',
                total_count=total, runs=compact)


def check_status(*, repo, sha, host='github.com', state_dir=None, refresh=False,
                 owner=None, clock=None, fetch=None):
    repo, sha, host = _identity(repo, sha, host, owner, refresh)
    now = (clock or time.time)()
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise StatusError('invalid local clock')
    root = Path(state_dir) if state_dir is not None else default_state_dir()
    directory = root / hashlib.sha256(f'{host}/{repo}'.encode()).hexdigest()
    base = dict(schema=SCHEMA, host=host, repo=repo, sha=sha, queried_at=now,
                refresh_requested=refresh, refresh_performed=False, qualification='observation_only')
    with _locked(directory) as acquired:
        if not acquired:
            return dict(base, status='missing', source='none', refresh_reason='busy', runs=[])
        state_path, cache_path = directory / 'state.json', directory / (sha + '.json')
        state = _read(state_path)
        if state is None:
            state = dict(schema=SCHEMA, host=host, repo=repo, owner=None,
                         next_allowed_at=0, provider_stop=None)
        if (state.get('schema'), state.get('host'), state.get('repo')) != (SCHEMA, host, repo):
            raise StatusError('local CI state identity mismatch')
        next_allowed = state.get('next_allowed_at')
        if (not {'owner', 'provider_stop', 'next_allowed_at'} <= state.keys()
                or type(next_allowed) not in (int, float) or not math.isfinite(next_allowed)
                or next_allowed < 0 or not (state.get('owner') is None or isinstance(state['owner'], str))
                or not (state.get('provider_stop') is None or isinstance(state['provider_stop'], dict))):
            raise StatusError('invalid local CI cooldown/owner state')
        cached = _read(cache_path)
        if cached is not None:
            if ((cached.get('schema'), cached.get('host'), cached.get('repo'), cached.get('sha'))
                    != (SCHEMA, host, repo, sha)
                    or type(cached.get('observed_at')) not in (int, float)
                    or not math.isfinite(cached['observed_at'])
                    or cached.get('observation_status') not in ('found', 'missing', 'truncated', 'error')
                    or not isinstance(cached.get('runs'), list)
                    or any(not isinstance(run, dict) or run.get('head_sha') != sha for run in cached['runs'])):
                raise StatusError('local CI cache identity or shape mismatch')
        reason = 'cache_only'
        if refresh:
            if state['owner'] is not None and state['owner'] != owner:
                reason = 'owner_conflict'
            elif state['provider_stop'] is not None:
                reason = 'provider_stopped'
            elif now < next_allowed:
                reason = 'cooldown'
            else:
                state.update(owner=owner, next_allowed_at=now + INTERVAL_SECONDS)
                _write(state_path, state)
                base['refresh_performed'] = True
                reason = 'refreshed'
                try:
                    cached = _snapshot((fetch or fetch_runs)(host, repo, sha), host, repo, sha, now)
                except FetchError as exc:
                    cached = dict(schema=SCHEMA, host=host, repo=repo, sha=sha, observed_at=now,
                                  observation_status='error', error=exc.code, total_count=None, runs=[])
                    if exc.provider_stop:
                        state['provider_stop'] = dict(reason=exc.code, observed_at=now)
                        _write(state_path, state)
                _write(cache_path, cached)
        result = dict(base, owner=state['owner'], next_refresh_at=state['next_allowed_at'],
                      provider_stop=state['provider_stop'], refresh_reason=reason)
        if cached is None:
            return dict(result, status='missing', source='none', runs=[])
        observed = cached['observed_at']
        status = cached['observation_status']
        result.update(status=('fresh' if base['refresh_performed'] else 'cached') if status == 'found' else status,
                      source='fresh' if base['refresh_performed'] else 'cache', observation_status=status,
                      observed_at=observed, cache_age_seconds=max(0, now - observed),
                      clock_skew_detected=now < observed, total_count=cached.get('total_count'), runs=cached['runs'])
        if 'error' in cached:
            result['error'] = cached['error']
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='explicit OWNER/REPOSITORY')
    parser.add_argument('--sha', required=True, help='exact full 40-character head SHA')
    parser.add_argument('--host', default='github.com')
    parser.add_argument('--state-dir', type=Path, help='isolated shared-state root; default is Git common directory')
    parser.add_argument('--refresh', action='store_true', help='owner may make one refresh if the shared gate permits it')
    parser.add_argument('--owner', help='stable local refresh-owner ID; required with --refresh')
    args = parser.parse_args(argv)
    try:
        receipt = check_status(**vars(args))
    except (StatusError, OSError, subprocess.SubprocessError) as exc:
        # Local errors also remain structured; no alternate provider operation.
        receipt = dict(schema=SCHEMA, status='error', source='local', error=type(exc).__name__,
                       host=args.host, repo=args.repo, sha=args.sha,
                       refresh_performed=False, qualification='observation_only')
        if isinstance(exc, StatusError):
            receipt['detail'] = str(exc)
        print(json.dumps(receipt, separators=(',', ':')))
        return 1
    print(json.dumps(receipt, separators=(',', ':')))
    return int(receipt['status'] == 'error' or receipt.get('provider_stop') is not None
               or receipt['refresh_reason'] == 'owner_conflict')


if __name__ == '__main__':
    raise SystemExit(main())
