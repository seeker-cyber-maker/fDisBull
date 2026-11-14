"""Finite host-side CI intake and recovery; no timer or provider credentials.

The existing n8n monitor calls status and starts one systemd service. This
module owns the shared executor lease for that service's complete lifetime.
Provider I/O, real qualification and bounded repairs are supplied by the
installed runtime, rather than inferred from producer hints.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import quote

from production_intake import FailureInbox, export_candidates
from recovery import RecoveryController, production


OWNER = '01a1692b-22ce-7b13-9d7d-05b2d4de529e'
TERMINAL = {'complete', 'attention'}


def read_json(path, maximum=65536):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('unsafe control record')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('control record must be an object')
    return value


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink control path')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    else:
        temporary = path.with_name('.' + path.name + '.' + str(os.getpid()))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return str(path)


class ActionLedger:
    """Local durable intent and acceptance; a missing response is never a retry."""
    def __init__(self, root, clock=time.time):
        self.root, self.clock = Path(root), clock

    def _path(self, key, suffix):
        if not isinstance(key, str) or not 1 <= len(key) <= 500 or any(ord(c) < 32 for c in key):
            raise ValueError('invalid action key')
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + suffix)

    def claim(self, action, key, payload):
        path = self._path(key, '.intent.json')
        binding = {'action': action, 'action_key': key, 'payload': payload}
        if path.exists():
            old = read_json(path)
            if any(old.get(k) != v for k, v in binding.items()):
                raise ValueError('action intent conflict')
            return {'durable': True, 'new': False, 'receipt_path': str(path)}
        if self._path(key, '.accepted.json').exists():
            raise ValueError('acceptance exists without its original intent')
        write_json(path, {**binding, 'created_epoch': self.clock()}, exclusive=True)
        return {'durable': True, 'new': True, 'receipt_path': str(path)}

    def load_intent(self, key):
        path = self._path(key, '.intent.json')
        if not path.exists(): return None
        value = read_json(path)
        if (set(value) != {'action', 'action_key', 'payload', 'created_epoch'}
                or value['action_key'] != key or type(value['created_epoch']) not in (int, float)
                or not math.isfinite(value['created_epoch'])):
            raise ValueError('action intent invalid')
        return {'intent': value, 'receipt_path': str(path)}

    def started(self, key):
        value = read_json(self._path(key, '.intent.json'))
        if value.get('action_key') != key or not isinstance(value.get('created_epoch'), (int, float)):
            raise ValueError('action start unknown')
        return value['created_epoch']

    def save_acceptance(self, key, proof):
        self.started(key)
        path = self._path(key, '.accepted.json')
        value = {'action_key': key, 'proof': proof}
        if path.exists():
            if read_json(path) != value: raise ValueError('acceptance conflict')
        else: write_json(path, value, exclusive=True)
        return str(path)

    def load_acceptance(self, key):
        path = self._path(key, '.accepted.json')
        if not path.exists(): return None
        value = read_json(path)
        if value.get('action_key') != key: raise ValueError('acceptance key mismatch')
        self.started(key)
        return {'proof': value['proof'], 'receipt_path': str(path)}


@contextmanager
def executor_lease(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('preinstalled executor lock required')
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before, actual = path.stat(), os.fstat(fd)
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
            raise ValueError('executor lock changed')
        yield {'fd': fd, 'owner_pid': os.getpid(), 'device': actual.st_dev, 'inode': actual.st_ino}
    finally:
        os.close(fd)


def check_worker_cleanup(runtime):
    check = getattr(runtime, 'cleanup_blocked', None)
    if callable(check) and check() is True:
        # This path deliberately retains the caller's live shared lease. It
        # cannot launch more work or reinterpret an unknown daemon outcome.
        runtime.hold_cleanup()
        raise RuntimeError('cleanup hold resolved; canonical reconciliation required')


@contextmanager
def cleanup_guard(runtime):
    try:
        yield
    finally:
        check_worker_cleanup(runtime)


class ProductionService:
    """One finite recovery owner, with restart-safe state and bounded intake."""
    def __init__(self, config, runtime_factory, *, clock=time.time, sleeper=time.sleep,
                 discover=export_candidates):
        self.config, self.factory = dict(config), runtime_factory
        self.clock, self.sleep, self.discover = clock, sleeper, discover
        self.root = Path(config['state_dir'])
        self.active_path = self.root / 'active.json'
        if (config.get('schema') != 'fdisbull-production-ci-config-1'
                or type(config.get('enabled')) is not bool
                or not self.root.is_absolute() or '..' in self.root.parts
                or not isinstance(config.get('activated_epoch'), (int, float))
                or type(config.get('max_incident_seconds')) is not int
                or not 60 <= config['max_incident_seconds'] <= 28800):
            raise ValueError('invalid production service configuration')
        github = config.get('github')
        if (not isinstance(github, dict) or github.get('repository') != 'seeker-cyber-maker/fDisBull'
                or str(github.get('workflow_id')) != '417757453' or str(github.get('runner_id')) != '21'
                or github.get('actor') != 'seeker-cyber-maker'
                or github.get('ref') != 'codex/production-ci-recovery-20261113'
                or github.get('profile') != 'ordinary' or github.get('sole_executor_authority') is not True
                or not isinstance(github.get('control_sha'), str)
                or not re.fullmatch(r'[0-9a-f]{40}', github['control_sha'])):
            raise ValueError('production control identity missing')
        self._state_guard()

    def _state_guard(self):
        if (not self.root.is_dir() or any(p.is_symlink() for p in (self.root, *self.root.parents))
                or self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077):
            raise ValueError('preinstalled private service state required')
        marker = read_json(self.root / 'installation.json')
        if (marker.get('schema') != 'fdisbull-production-state-1'
                or marker.get('installation_id') != self.config.get('installation_id')
                or not isinstance(marker.get('installation_id'), str) or not marker['installation_id']):
            raise ValueError('service installation identity unknown')
        database = self.root / 'failure-inbox.sqlite'
        if database.is_symlink() or not database.is_file():
            raise ValueError('preinstalled durable inbox required')
        if (self.root / 'blocked.json').exists():
            raise ValueError('service requires canonical attention')

    def _inbox(self):
        self._state_guard()
        return FailureInbox(self.root / 'failure-inbox.sqlite', max_events=1024)

    def _discover(self, inbox):
        result = self.discover(self.config['export_root'], self.config['activated_epoch'],
                               limit=32, gitlab_project_id='88349936',
                               github_repository='seeker-cyber-maker/fDisBull')
        for candidate in result['candidates']:
            inbox.enqueue(candidate, now=self.clock())
        return result

    def status(self):
        if not self.config['enabled']:
            return {'schema_version': 1, 'pending_work': False}
        self._state_guard()
        # GET /ci/status is a read-only metadata check. Durable intake belongs
        # to run(), under the shared executor lease, rather than to readers.
        discovered = self.discover(self.config['export_root'], self.config['activated_epoch'],
                                   limit=32, gitlab_project_id='88349936',
                                   github_repository='seeker-cyber-maker/fDisBull')
        uri = 'file:' + quote(str(self.root / 'failure-inbox.sqlite')) + '?mode=ro'
        database = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            database.execute('PRAGMA query_only=ON')
            records = database.execute('SELECT event_key,state FROM events').fetchall()
        finally:
            database.close()
        known = {key for key, state in records}
        queued = (any(state in ('pending', 'claimed', 'needs_reconciliation') for key, state in records)
                  or any(item['event_key'] not in known for item in discovered['candidates']))
        active = read_json(self.active_path) if self.active_path.exists() else None
        running = active is not None and active.get('status') not in TERMINAL
        initial = self.config.get('initial_request') is not None and self._initial_result() is None
        return {'schema_version': 1, 'pending_work': bool(queued or running or initial)}

    def _initial_result(self):
        path = self.root / 'initial-result.json'
        if not path.exists(): return None
        value = read_json(path)
        if (set(value) != {'schema', 'request', 'verified', 'status', 'target', 'receipt_path', 'receipt_sha256'}
                or value['schema'] != 'fdisbull-initial-qualification-1'
                or value['request'] != self.config.get('initial_request') or value['verified'] is not True
                or value['status'] not in ('success', 'failed')):
            raise ValueError('initial result binding unknown')
        target = production.target(value['target'])
        if (target['provider'] != 'github' or target['source_sha'] != value['request']['source_sha']
                or target['job_name'] != 'qualification' or target['repository'] != 'seeker-cyber-maker/fDisBull'
                or target['runner_id'] != '21'):
            raise ValueError('initial result target mismatch')
        expected = self.config['github']
        if any(target[k] != expected[k] for k in ('control_sha', 'ref')):
            raise ValueError('initial control identity changed')
        receipt = Path(value['receipt_path'])
        if (not receipt.is_absolute() or self.root not in receipt.parents
                or any(p.is_symlink() for p in (receipt, *receipt.parents))
                or not receipt.is_file() or receipt.stat().st_mode & 0o077
                or hashlib.sha256(receipt.read_bytes()).hexdigest() != value['receipt_sha256']):
            raise ValueError('initial canonical receipt unavailable')
        evidence = read_json(receipt)
        if (evidence.get('schema') != 'fdisbull-production-evidence-1'
                or evidence.get('target') != target or evidence.get('job_status') != value['status']):
            raise ValueError('initial canonical evidence differs')
        return value

    def _write_initial_result(self, request, result):
        receipt = Path(result['receipt_path'])
        if (not receipt.is_file() or not receipt.is_absolute() or self.root not in receipt.parents
                or any(p.is_symlink() for p in (receipt, *receipt.parents))):
            raise ValueError('initial evidence path unverified')
        value = {'schema': 'fdisbull-initial-qualification-1', 'request': request,
                 **{k: result[k] for k in ('verified', 'status', 'target', 'receipt_path')},
                 'receipt_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()}
        write_json(self.root / 'initial-result.json', value, exclusive=True)
        self._initial_result()

    def _finish_inbox(self, inbox, active, state):
        key = active['event_key']
        payload = {'kind': 'controller_' + state['status'], 'status': state['status'],
                   'reason': state.get('reason', 'canonical_success'),
                   'canonical_source_sha': state['target']['source_sha'],
                   'provider_receipt_path': str(self.root / 'incidents' / key / 'state.json')}
        if state['status'] == 'complete':
            payload.update(verification='canonical_terminal', canonical_status='success')
        current = inbox.get(key)
        if current['state'] == 'needs_reconciliation':
            inbox.resolve_reconciliation(key, OWNER, state['status'], payload, now=self.clock())
        elif current['state'] == 'claimed':
            result = getattr(inbox, state['status'])(key, OWNER, payload, now=self.clock())
            if result['state'] == 'needs_reconciliation':
                inbox.resolve_reconciliation(key, OWNER, state['status'], payload, now=self.clock())
        elif current['state'] != state['status']:
            raise ValueError('inbox terminal state mismatch')
        active.update(status=state['status'], reason=state.get('reason'), finished_epoch=self.clock())
        write_json(self.active_path, active)

    def _await_provider(self, runtime, provider, deadline):
        while self.clock() < deadline:
            reservation = runtime.prepare({'initial_target': {'provider': provider}})
            check_worker_cleanup(runtime)
            if reservation.get('allowed') is True: return
            if reservation.get('reason') not in ('cooldown', 'busy'):
                raise ValueError('provider reservation refused')
            if runtime.health().get('state') != 'healthy':
                raise ValueError('production health unavailable')
            remaining = max(1, (reservation.get('next_refresh_at') or self.clock()+60)-self.clock())
            self.sleep(min(60, remaining, max(1, deadline-self.clock())))
        raise TimeoutError('finite provider admission deadline expired')

    def run(self):
        if not self.config['enabled']: return {'status': 'disabled'}
        with executor_lease(self.config['executor_lock']) as lease:
            runtime = self.factory(self.config, self.root, lease)
            with cleanup_guard(runtime), self._inbox() as inbox:
                self._discover(inbox)
                initial = self.config.get('initial_request')
                result_path = self.root / 'initial-result.json'
                if initial is not None and self._initial_result() is None:
                    # The host dispatch implementation retains intent before a POST
                    # and refuses unknown launch replay. It also verifies exports.
                    request_path = self.root / 'initial-request.json'
                    if request_path.exists():
                        intent = read_json(request_path)
                        if intent.get('request') != initial: raise ValueError('initial request changed')
                    else:
                        intent = {'request': initial, 'created_epoch': self.clock()}
                        write_json(request_path, intent, exclusive=True)
                    deadline = intent['created_epoch'] + self.config['max_incident_seconds']
                    while True:
                        self._await_provider(runtime, 'github', deadline)
                        result = runtime.initial_dispatch(initial)
                        check_worker_cleanup(runtime)
                        if (not isinstance(result, dict) or result.get('verified') is not True
                                or result.get('status') not in ('pending', 'success', 'failed')):
                            raise ValueError('initial qualification incomplete')
                        if result['status'] != 'pending': break
                        if not isinstance(result.get('receipt_path'), str) or not result['receipt_path']:
                            raise ValueError('initial accepted origin missing')
                        finish = getattr(runtime, 'finish_batch', None)
                        if callable(finish): finish({'initial_target': {'provider': 'github'}})
                        self.sleep(min(60, max(1, deadline-self.clock())))
                    self._write_initial_result(initial, result)
                    self._discover(inbox)
                active = read_json(self.active_path) if self.active_path.exists() else None
                if active is None or active.get('status') in TERMINAL:
                    row = inbox.db.execute("SELECT descriptor FROM events WHERE state='pending' ORDER BY created_epoch,event_key LIMIT 1").fetchone()
                    if row is not None:
                        hinted_provider = json.loads(bytes(row[0]))['provider']
                        self._await_provider(runtime, hinted_provider, self.clock()+self.config['max_incident_seconds'])
                    claim = inbox.claim(OWNER, now=self.clock(), lease_seconds=3600)
                    if claim is None: return {'status': 'idle'}
                    if claim['state'] == 'needs_reconciliation':
                        # No new controller may guess that an earlier action did
                        # not happen. A known active record is required to resume.
                        raise ValueError('orphan claim requires canonical reconciliation')
                    candidate = claim['candidate']
                    target, required = runtime.resolve_candidate(candidate)
                    check_worker_cleanup(runtime)
                    key = candidate['event_key']; directory = self.root / 'incidents' / key
                    manifest = {'incident_id': key, 'project': target.get('repository', target.get('project_id')),
                                'initial_target': target, 'required_artifacts': required,
                                'deadline_epoch': self.clock() + self.config['max_incident_seconds'],
                                'max_infrastructure_repairs': 1, 'max_source_repairs': 1}
                    write_json(directory / 'manifest.json', manifest, exclusive=True)
                    active = {'event_key': key, 'status': 'pending', 'candidate': candidate,
                              'started_epoch': self.clock()}
                    write_json(self.active_path, active)
                key = active['event_key']; directory = self.root / 'incidents' / key
                manifest = read_json(directory / 'manifest.json')
                backend = runtime.backend(manifest, directory)
                controller = RecoveryController(directory / 'state.json', manifest, backend)
                while self.clock() < manifest['deadline_epoch']:
                    # One fixed owner reserves each provider batch. Healthy jobs
                    # use host waits, never model calls; sleeps remain interruptible.
                    reservation = runtime.prepare(manifest)
                    if reservation.get('allowed') is not True:
                        if reservation.get('reason') not in ('cooldown', 'busy'):
                            raise ValueError('provider reservation refused')
                        if runtime.health().get('state') != 'healthy':
                            raise ValueError('production health unavailable')
                        remaining = max(1, (reservation.get('next_refresh_at') or self.clock()+60)-self.clock())
                        self.sleep(min(60, remaining)); continue
                    state = controller.step()
                    check_worker_cleanup(runtime)
                    if state['status'] in TERMINAL:
                        self._finish_inbox(inbox, active, state)
                        return {'status': state['status'], 'reason': state.get('reason'), 'target': state['target']}
                    if state['phase'] in ('dispatch_retry', 'dispatch_pipeline'):
                        state = controller.step()
                        check_worker_cleanup(runtime)
                        if state['status'] in TERMINAL:
                            self._finish_inbox(inbox, active, state)
                            return {'status': state['status'], 'reason': state.get('reason'), 'target': state['target']}
                    finish = getattr(runtime, 'finish_batch', None)
                    if callable(finish): finish(manifest)
                    self.sleep(1)
                # The controller owns the durable deadline/attention transition.
                state = controller.step()
                check_worker_cleanup(runtime)
                self._finish_inbox(inbox, active, state)
                return {'status': state['status'], 'reason': state.get('reason')}
