"""One owned GitHub qualification dispatch and listener, under an existing lease.

The local executor lease serializes this host only. It does not exclude other
GitHub actors: callers must establish and explicitly assert sole executor
authority for the selected workflow/ref. Ambiguous origin remains unknown.
This module never starts a watcher or acquires a second lock.
"""
import base64
import copy
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


transport_contract = _load('production_transport_host', 'production_transport.py')
production = _load('production_identity_host', 'recovery_production.py')
REPOSITORY = 'seeker-cyber-maker/fDisBull'
WORKFLOW = '417757453'
BASE = '/repos/' + REPOSITORY + '/actions'


class CleanupUnknown(RuntimeError):
    """Owned container cleanup is unproven; caller must retain the lease."""
    requires_executor_hold = True


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def _write(path, value):
    data = _bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    return str(path)


def _read_bytes(path, maximum=65536):
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('receipt unavailable')
    data = path.read_bytes()
    if len(data) > maximum: raise ValueError('receipt exceeds bound')
    value = json.loads(data)
    if not isinstance(value, dict): raise ValueError('receipt malformed')
    return value, data


def _read(path, maximum=65536):
    return _read_bytes(path, maximum)[0]


class GitHubHost:
    def __init__(self, config, state_root, transport, lease_fd, lease_owner_pid, lease_dev, lease_ino,
                 *, lease_check, trace_capture, action_started=None, listener_runner=subprocess.Popen, clock=time.time,
                 control_root=Path('/var/lib/fdisbull-ci/control')):
        self.config = dict(config)
        if (self.config.get('sole_executor_authority') is not True
                or self.config.get('repository') != REPOSITORY or str(self.config.get('workflow_id')) != WORKFLOW
                or str(self.config.get('runner_id')) != '21' or self.config.get('profile') != 'ordinary'
                or not re.fullmatch(r'[0-9a-f]{40}', str(self.config.get('control_sha', '')))
                or not production.valid_ref(self.config.get('ref'))
                or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', str(self.config.get('actor', '')))):
            raise ValueError('unqualified GitHub host configuration')
        if (type(lease_fd) is not int or lease_fd < 0 or type(lease_owner_pid) is not int or lease_owner_pid <= 0
                or type(lease_dev) is not int or lease_dev < 0 or type(lease_ino) is not int or lease_ino <= 0
                or not callable(lease_check)):
            raise ValueError('invalid inherited lease')
        self.state = Path(state_root)
        if not self.state.is_dir() or any(p.is_symlink() for p in (self.state, *self.state.parents)):
            raise ValueError('existing private state directory required')
        if self.state.stat().st_uid != os.getuid() or self.state.stat().st_mode & 0o077:
            raise ValueError('private state directory required')
        if not callable(trace_capture): raise ValueError('trace capture required')
        self.transport, self.lease_check, self.listener_runner, self.clock = transport, lease_check, listener_runner, clock
        self.trace_capture, self.action_started = trace_capture, action_started
        self.fd, self.owner, self.dev, self.ino = lease_fd, lease_owner_pid, lease_dev, lease_ino
        self.export_root = Path(self.config['export_root']) / 'github'
        self.once = Path(__file__).with_name('github-once.py')
        self.control_root = Path(control_root)
        self.blocker = self.control_root / 'production' / 'github-cleanup-blocked.json'

    def _lease(self):
        if self.blocker.exists() or self.blocker.is_symlink():
            raise CleanupUnknown('unresolved GitHub container cleanup')
        if self.lease_check(self.fd, self.owner, self.dev, self.ino) is not True:
            raise RuntimeError('executor lease unavailable')

    def _path(self, key, suffix):
        if not isinstance(key, str) or not 1 <= len(key) <= 500 or any(ord(c) < 32 for c in key):
            raise ValueError('invalid action key')
        return self.state / (hashlib.sha256(key.encode()).hexdigest() + '.' + suffix + '.json')

    def _get(self, path):
        response = self.transport.request('GET', path)
        if (not isinstance(response, dict) or response.get('http_status') != 200 or 'data' not in response):
            raise RuntimeError('canonical provider read unavailable')
        return response['data']

    def _accept(self, key, path, body, expected):
        receipt = self.transport.receipt(key)
        receipt = receipt.get('receipt') if isinstance(receipt, dict) else None
        digest = transport_contract.request_digest('github', 'POST', path, body)
        if (not isinstance(receipt, dict) or receipt.get('action_key') != key
                or receipt.get('status') != 'accepted' or receipt.get('request_sha256') != digest):
            return None
        env = receipt.get('envelope')
        if not isinstance(env, dict) or env.get('http_status') != expected or env.get('data') is not None:
            return None
        proof = {'action_key': key, 'request_sha256': digest, 'http_status': expected}
        proof_path = self._path(key, 'acceptance')
        if proof_path.exists():
            if _read(proof_path) != proof: raise ValueError('acceptance conflicts')
        else: _write(proof_path, proof)
        return str(proof_path)

    def _matching_run(self, nonce, started_epoch):
        matches = []
        nonce_rows = []
        for page in range(1, 11):
            result = self._get(BASE + '/workflows/' + WORKFLOW + '/runs?per_page=100&page=' + str(page))
            if not isinstance(result, dict) or not isinstance(result.get('workflow_runs'), list):
                raise ValueError('invalid workflow runs')
            batch = result['workflow_runs']
            if len(batch) > 100: raise ValueError('oversize workflow runs')
            for row in batch:
                if isinstance(row, dict) and row.get('display_title') == 'OVH qualification ' + nonce:
                    nonce_rows.append(row)
                try:
                    parsed = datetime.fromisoformat(row.get('created_at', '').replace('Z', '+00:00'))
                    if parsed.tzinfo is None: continue
                    created = parsed.timestamp()
                except (AttributeError, TypeError, ValueError, OverflowError):
                    continue
                if (int(started_epoch) - 1 <= created <= self.clock() + 30 and isinstance(row, dict) and row.get('display_title') == 'OVH qualification ' + nonce
                        and row.get('event') == 'workflow_dispatch' and str(row.get('workflow_id')) == WORKFLOW
                        and row.get('head_sha') == self.config['control_sha']
                        and row.get('head_branch') == self.config['ref'].removeprefix('refs/heads/')
                        and (row.get('repository') or {}).get('full_name') == REPOSITORY
                        and (row.get('actor') or {}).get('login') == self.config['actor']):
                    matches.append(row)
            if len(batch) < 100: break
        else: raise ValueError('workflow runs exceed bounded list')
        if len(nonce_rows) != 1 or len(matches) != 1: return None
        row = matches[0]
        rid = row.get('id')
        if type(rid) is not int or rid <= 0 or row.get('run_attempt') != 1: return None
        canonical = self._get(BASE + '/runs/' + str(rid) + '/attempts/1')
        for field in ('id', 'run_attempt', 'display_title', 'event', 'workflow_id', 'head_sha', 'head_branch', 'created_at'):
            if canonical.get(field) != row.get(field): raise ValueError('run identity changed')
        if (canonical.get('repository') or {}).get('full_name') != REPOSITORY or (canonical.get('actor') or {}).get('login') != self.config['actor']:
            raise ValueError('run actor or repository changed')
        return canonical

    def initial_dispatch(self, key, candidate_sha):
        self._lease()
        if not isinstance(candidate_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', candidate_sha):
            raise ValueError('invalid candidate SHA')
        nonce = hashlib.sha256(key.encode()).hexdigest()
        body = {'ref': self.config['ref'], 'inputs': {'nonce': nonce, 'candidate_sha': candidate_sha}}
        path = BASE + '/workflows/' + WORKFLOW + '/dispatches'
        intent = {'action_key': key, 'candidate_sha': candidate_sha, 'nonce': nonce,
                  'request_sha256': transport_contract.request_digest('github', 'POST', path, body),
                  'created_epoch': self.clock()}
        intent_path = self._path(key, 'dispatch-intent')
        if intent_path.exists(): raise RuntimeError('dispatch already attempted; reconcile only')
        _write(intent_path, intent)
        result = self.transport.for_action(key)('POST', path, body)
        if not isinstance(result, dict) or result.get('http_status') != 204 or result.get('data') is not None:
            raise RuntimeError('dispatch outcome unknown')
        return self.reconcile_initial(key, candidate_sha)

    def reconcile_initial(self, key, candidate_sha):
        self._lease()
        intent = _read(self._path(key, 'dispatch-intent'))
        nonce = hashlib.sha256(key.encode()).hexdigest()
        body = {'ref': self.config['ref'], 'inputs': {'nonce': nonce, 'candidate_sha': candidate_sha}}
        path = BASE + '/workflows/' + WORKFLOW + '/dispatches'
        if (intent.get('action_key') != key or intent.get('candidate_sha') != candidate_sha
                or intent.get('nonce') != nonce or intent.get('request_sha256') != transport_contract.request_digest('github', 'POST', path, body)):
            raise ValueError('dispatch intent mismatch')
        accepted = self._accept(key, path, body, 204)
        if accepted is None:
            envelope=self.transport.receipt(key)
            held=envelope.get('receipt') if isinstance(envelope,dict) else None
            digest=transport_contract.request_digest('github','POST',path,body)
            if (not isinstance(held,dict) or held.get('status')!='certified_not_sent'
                    or key!=transport_contract.HELD_ACTION_KEY or digest!=transport_contract.HELD_REQUEST_SHA256
                    or held.get('action_key')!=key or held.get('request_sha256')!=digest
                    or held.get('old_record_sha256')!=transport_contract.HELD_RECORD_SHA256
                    or not isinstance(held.get('verifier_cert_sha256'),str)
                    or not re.fullmatch('[0-9a-f]{64}',held['verifier_cert_sha256'])):
                return None
            # The pinned bridge consumes the separately installed permit before
            # this only possible POST. Unknown attempts never regain the permit.
            self._lease()
            response=self.transport.for_action(key)('POST',path,body)
            if not isinstance(response,dict) or response.get('http_status')!=204 or response.get('data') is not None:
                raise RuntimeError('certified dispatch outcome unknown')
            accepted=self._accept(key,path,body,204)
            if accepted is None:raise RuntimeError('certified dispatch acceptance unavailable')
        run = self._matching_run(nonce, intent['created_epoch'])
        if run is None: return None
        rid = str(run['id'])
        self.run_listener(key, nonce, rid, '1', candidate_sha)
        target = self._target_for_run(rid, '1', candidate_sha)
        if not target: return None
        job = self._get(BASE + '/jobs/' + target['job_id'])
        status = self._status(job)
        result = {'target': target, 'status': status, 'acceptance_receipt': accepted}
        receipt_path = self._path(key, 'initial-result-' + status)
        if receipt_path.exists():
            if _read(receipt_path) != result: raise ValueError('initial result conflicts')
        else: _write(receipt_path, result)
        result['receipt_path'] = str(receipt_path)
        return result

    def _listener_admission(self, run_id):
        """Reject other active runs; the local lease cannot exclude external actors."""
        seen = set(); selected = None
        active = {'queued', 'in_progress', 'waiting', 'requested', 'pending'}
        for page in range(1, 11):
            doc = self._get(BASE + '/workflows/' + WORKFLOW + '/runs?per_page=100&page=' + str(page))
            if not isinstance(doc, dict) or not isinstance(doc.get('workflow_runs'), list):
                raise ValueError('workflow admission unavailable')
            rows = doc['workflow_runs']
            if len(rows) > 100: raise ValueError('workflow admission exceeds bound')
            for row in rows:
                if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= 0:
                    raise ValueError('workflow run identity unavailable')
                rid = str(row['id']); status = row.get('status')
                if rid in seen or status not in active | {'completed'}:
                    raise ValueError('workflow run status unknown or duplicated')
                seen.add(rid)
                if rid == run_id: selected = status
                elif status in active: raise RuntimeError('another workflow run is active')
            if len(rows) < 100: break
        else: raise ValueError('workflow admission exceeds bound')
        if selected is None: raise ValueError('selected workflow run unavailable')
        return selected in active

    def run_listener(self, key, nonce, run_id, attempt, candidate_sha):
        self._lease()
        if not all(isinstance(v, str) and re.fullmatch(r'[1-9][0-9]*', v) for v in (run_id, attempt)):
            raise ValueError('invalid listener run identity')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', nonce) or not re.fullmatch(r'[0-9a-f]{40}', candidate_sha):
            raise ValueError('invalid listener source')
        path = self._path(key, 'listener-intent')
        desired = {'action_key': key, 'nonce': nonce, 'run_id': run_id, 'run_attempt': attempt,
                   'source_sha': candidate_sha, 'control_sha': self.config['control_sha'], 'ref': self.config['ref']}
        if path.exists():
            if _read(path) != desired: raise ValueError('listener identity conflicts')
            # An earlier intent may have started a process before any receipt.
            # Only an exact clean receipt permits reconciliation, never respawn.
            self._verify_cleanup(key, nonce, run_id, attempt, candidate_sha)
            return None
        if not self._listener_admission(run_id):
            return None
        _write(path, desired)
        args = ['/usr/bin/python3', str(self.once), '--nonce', nonce, '--control-sha', self.config['control_sha'],
                '--runner-id', '21', '--run-id', run_id, '--run-attempt', attempt, '--source-sha', candidate_sha,
                '--control-ref', self.config['ref'], '--lease-fd', str(self.fd), '--lease-owner-pid', str(self.owner),
                '--lease-dev', str(self.dev), '--lease-ino', str(self.ino)]
        try:
            proc = self.listener_runner(args, pass_fds=(self.fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _write(self._path(key, 'listener-started'), {'action_key': key, 'pid': proc.pid, 'run_id': run_id, 'run_attempt': attempt})
        except BaseException:
            self._cleanup_unknown(key, run_id, attempt, 'listener_start_unknown')
        deadline = time.monotonic() + 14500
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._cleanup_unknown(key, run_id, attempt, 'listener_timeout')
            # The owned listener checks lease/health and stops its own process
            # group. Keep waiting so loss of the parent lease cannot orphan it.
            try:
                code = proc.wait(timeout=min(60, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
            except BaseException:
                self._cleanup_unknown(key, run_id, attempt, 'listener_wait_unknown')
        if code == 86:
            self._cleanup_unknown(key, run_id, attempt, 'listener_reported_unknown')
        receipt = self._verify_cleanup(key, nonce, run_id, attempt, candidate_sha)
        _write(self._path(key, 'listener-exit'), {'action_key': key, 'pid': proc.pid, 'exit_code': code,
                                                 'cleanup_verified': True, 'cleanup_receipt': str(receipt)})
        return code

    def _verify_cleanup(self, key, nonce, run_id, attempt, candidate_sha):
        receipt = self.control_root / 'github-bootstrap-20261113' / nonce / 'cleanup.json'
        labels = {'fdisbull.ci.provider': 'github', 'fdisbull.ci.run_id': run_id,
                  'fdisbull.ci.run_attempt': attempt,
                  'fdisbull.ci.control_sha': self.config['control_sha']}
        try:
            clean = _read(receipt)
            if (self.blocker.exists() or self.blocker.is_symlink() or clean.get('status') != 'clean'
                    or clean.get('labels') != labels or type(clean.get('containers')) is not list
                    or any(type(v) is not dict or v.get('final_running') is not False for v in clean['containers'])):
                raise ValueError('cleanup not confirmed')
        except (OSError, ValueError, TypeError):
            self._cleanup_unknown(key, run_id, attempt, 'listener_cleanup_unverified')
        return receipt

    def _cleanup_unknown(self, key, run_id, attempt, reason):
        # Failure to persist this marker is still unknown; the caller retains
        # the lease and must not dispatch again. Never clear it here.
        marker = {'status': 'unknown', 'action_key': key, 'run_id': run_id, 'run_attempt': attempt, 'reason': reason}
        try:
            self.blocker.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if not self.blocker.exists() and not self.blocker.is_symlink(): _write(self.blocker, marker)
        except OSError:
            pass
        raise CleanupUnknown('owned GitHub container cleanup unknown; retain executor lease')

    def after_acceptance(self, action, key, payload, proof):
        """Supervise at most one listener for an already durably accepted action."""
        self._lease()
        if action not in ('retry_job', 'start_pipeline') or proof.get('action') != action:
            raise ValueError('invalid accepted action')
        old = production.target(payload['target'])
        if old['provider'] != 'github' or old['repository'] != REPOSITORY:
            raise ValueError('invalid accepted target')
        nonce = hashlib.sha256(key.encode()).hexdigest()
        if action == 'retry_job':
            run_id, attempt, source = old['run_id'], str(int(old['run_attempt']) + 1), old['source_sha']
            latest = self._get(BASE + '/runs/' + run_id)
            if str(latest.get('run_attempt')) == old['run_attempt']: return None
            if str(latest.get('run_attempt')) != attempt: raise ValueError('ambiguous retry attempt')
            run = self._get(BASE + '/runs/' + run_id + '/attempts/' + attempt)
            if (str(run.get('id')) != run_id or str(run.get('run_attempt')) != attempt
                    or run.get('head_sha') != self.config['control_sha']
                    or run.get('head_branch') != self.config['ref'].removeprefix('refs/heads/')
                    or (run.get('repository') or {}).get('full_name') != REPOSITORY
                    or (run.get('actor') or {}).get('login') != self.config['actor']):
                raise ValueError('retry run identity mismatch')
        else:
            if not callable(self.action_started): raise ValueError('action start evidence required')
            started = self.action_started(key)
            if type(started) not in (int, float) or not math.isfinite(started): raise ValueError('action start evidence invalid')
            run = self._matching_run(nonce, started)
            if run is None: return None
            run_id, attempt, source = str(run['id']), '1', payload['source_sha']
        return self.run_listener(key, nonce, run_id, attempt, source)

    def resolve_dispatch(self, key, proof, payload):
        """Return a nonce-linked target only once canonical and source bound."""
        if not callable(self.action_started): raise ValueError('action start evidence required')
        started = self.action_started(key)
        if type(started) not in (int, float) or not math.isfinite(started): raise ValueError('action start evidence invalid')
        nonce = hashlib.sha256(key.encode()).hexdigest()
        run = self._matching_run(nonce, started)
        if run is None: return None
        target = self._target_for_run(str(run['id']), '1', payload['source_sha'])
        if target is None: return None
        receipt = {'action_key': key, 'nonce': nonce, 'target': target}
        path = self._path(key, 'dispatch-origin')
        if path.exists():
            if _read(path) != receipt: raise ValueError('dispatch origin changed')
        else: _write(path, receipt)
        return {'verified': True, 'target': target, 'nonce': nonce, 'receipt_path': str(path)}

    def _target_for_run(self, run_id, attempt, candidate_sha):
        result = self._get(BASE + '/runs/' + run_id + '/attempts/' + attempt + '/jobs?per_page=100&page=1')
        if not isinstance(result, dict) or type(result.get('total_count')) is not int or not isinstance(result.get('jobs'), list):
            raise ValueError('invalid attempt jobs')
        if result['total_count'] != len(result['jobs']) or result['total_count'] > 100:
            raise ValueError('attempt jobs not complete')
        jobs = [j for j in result['jobs'] if isinstance(j, dict) and j.get('name') == 'qualification']
        if len(jobs) != 1: return None
        job = jobs[0]
        if (type(job.get('id')) is not int or job['id'] <= 0 or str(job.get('run_id')) != run_id
                or job.get('head_sha') != self.config['control_sha'] or str(job.get('runner_id')) != '21'):
            return None
        target = {'provider': 'github', 'repository': REPOSITORY, 'run_id': run_id, 'run_attempt': attempt,
                  'job_id': str(job['id']), 'source_sha': candidate_sha, 'job_name': 'qualification', 'runner_id': '21',
                  'ref': self.config['ref'], 'control_sha': self.config['control_sha']}
        run = self._get(BASE + '/runs/' + run_id + '/attempts/' + attempt)
        actual = self._get(BASE + '/jobs/' + target['job_id'])
        if any(job.get(k) != actual.get(k) for k in ('id', 'run_id', 'name', 'head_sha', 'runner_id')):
            raise ValueError('canonical job mismatch')
        self.source_binding(target, run, actual)
        return target

    @staticmethod
    def _status(job):
        if job.get('status') in ('queued', 'in_progress', 'waiting', 'requested', 'pending'): return 'running'
        if job.get('status') == 'completed':
            return {'success': 'success', 'failure': 'failed', 'timed_out': 'failed', 'cancelled': 'canceled'}.get(job.get('conclusion'), 'unknown')
        return 'unknown'

    def source_binding(self, target, run, job):
        target = production.target(target)
        if (target['provider'] != 'github' or target['repository'] != REPOSITORY
                or target['control_sha'] != self.config['control_sha'] or target['ref'] != self.config['ref']
                or target['runner_id'] != '21' or target['job_name'] != 'qualification'):
            raise ValueError('invalid GitHub target')
        folder = self.export_root / target['run_id'] / target['run_attempt'] / 'qualification' / target['job_id']
        start_path = folder / 'candidate-start.json'
        start, start_data = _read_bytes(start_path)
        if (start.get('schema') != 'fdisbull-github-candidate-start-1'
                or start.get('candidate_head') != target['source_sha'] or start.get('control_head') != target['control_sha']
                or any(str(start.get(k)) != str(v) for k, v in target.items() if k != 'provider')
                or str(run.get('id')) != target['run_id'] or str(run.get('run_attempt')) != target['run_attempt']
                or run.get('head_sha') != target['control_sha']
                or run.get('head_branch') != target['ref'].removeprefix('refs/heads/')
                or (run.get('repository') or {}).get('full_name') != REPOSITORY
                or str(job.get('id')) != target['job_id'] or str(job.get('run_id')) != target['run_id']
                or job.get('head_sha') != target['control_sha'] or job.get('name') != target['job_name']
                or str(job.get('runner_id')) != '21'
                or not isinstance(start.get('nonce'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', start['nonce'])):
            raise ValueError('candidate start binding mismatch')
        digest = hashlib.sha256(start_data).hexdigest()
        receipt = {'target': target, 'start_sha256': digest, 'start_path': str(start_path)}
        path = self.state / ('source-' + hashlib.sha256(_bytes(target)).hexdigest() + '.json')
        if path.exists():
            if _read(path) != receipt: raise ValueError('source binding changed')
        else: _write(path, receipt)
        return {'verified': True, 'target': target, 'receipt_path': str(path)}

    def capture_provider(self, observation):
        target = production.target({k: observation[k] for k in production.SCHEMAS['github']})
        run = self._get(BASE + '/runs/' + target['run_id'] + '/attempts/' + target['run_attempt'])
        job = self._get(BASE + '/jobs/' + target['job_id'])
        self.source_binding(target, run, job)
        jobs = self._get(BASE + '/runs/' + target['run_id'] + '/attempts/' + target['run_attempt'] + '/jobs?per_page=100&page=1')
        if (not isinstance(jobs, dict) or not isinstance(jobs.get('jobs'), list)
                or type(jobs.get('total_count')) is not int or jobs['total_count'] != len(jobs['jobs'])
                or jobs['total_count'] > 100): raise ValueError('attempt job list unavailable')
        matches = [j for j in jobs['jobs'] if isinstance(j, dict) and str(j.get('id')) == target['job_id']]
        if len(matches) != 1 or any(matches[0].get(k) != job.get(k) for k in ('id', 'run_id', 'name', 'head_sha', 'runner_id')):
            raise ValueError('job not linked to attempt')
        if self._status(job) != observation['status'] or observation['status'] not in ('failed', 'success'):
            raise ValueError('provider terminal outcome mismatch')
        result = self.trace_capture(copy.deepcopy(target))
        if not isinstance(result, dict) or result.get('encoding') != 'base64': raise ValueError('provider log unavailable')
        raw = base64.b64decode(result.get('data', ''), validate=True)
        if not raw or len(raw) > 1024 * 1024 or result.get('size') != len(raw) or result.get('sha256') != hashlib.sha256(raw).hexdigest():
            raise ValueError('provider log invalid')
        return {'verified': True, 'target': target, 'job_status': observation['status'],
                'metadata': {'run': run, 'job': job}, 'trace': result}
