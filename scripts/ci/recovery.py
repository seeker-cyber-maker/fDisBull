"""Finite, durable recovery decisions for one explicitly selected CI incident.

The backend provides authoritative observation, bounded execution and shared
host serialization. This module does not start a watcher or establish delivery.
"""
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time


TARGET_KEYS = ('pipeline_id', 'job_id', 'source_sha', 'job_name', 'runner_id')
ACTIONS = {'repair_infrastructure', 'retry_job', 'repair_source', 'start_pipeline'}


def _target(value):
    if not isinstance(value, dict) or set(value) != set(TARGET_KEYS):
        raise ValueError('invalid target fields')
    if any(not isinstance(value[k], (str, int)) or isinstance(value[k], bool)
           or not str(value[k]) for k in ('pipeline_id', 'job_id', 'runner_id')):
        raise ValueError('invalid target identity')
    if any(not str(value[k]).isdecimal() for k in ('pipeline_id', 'job_id', 'runner_id')):
        raise ValueError('invalid target identity')
    if not isinstance(value['job_name'], str) or not value['job_name']:
        raise ValueError('invalid job name')
    if not isinstance(value['source_sha'], str) or not re.fullmatch(r'[0-9a-f]{40}', value['source_sha']):
        raise ValueError('invalid source sha')
    return {k: str(value[k]) if k in ('pipeline_id', 'job_id', 'runner_id') else value[k] for k in TARGET_KEYS}


class RecoveryController:
    def __init__(self, state_path, manifest, backend):
        self.path = Path(state_path)
        self.lock_path = self.path.with_name(self.path.name + '.lock')
        self.backend = backend
        self.manifest = copy.deepcopy(manifest)
        if not isinstance(manifest, dict) or not isinstance(manifest.get('incident_id'), str) or not manifest['incident_id']:
            raise ValueError('invalid incident')
        if not isinstance(manifest.get('project'), (str, int)) or not str(manifest['project']):
            raise ValueError('invalid project')
        _target(manifest.get('initial_target'))
        if not isinstance(manifest.get('deadline_epoch'), (int, float)) or isinstance(manifest['deadline_epoch'], bool):
            raise ValueError('invalid deadline')
        for key in ('max_infrastructure_repairs', 'max_source_repairs'):
            if not isinstance(manifest.get(key), int) or isinstance(manifest[key], bool) or not 0 <= manifest[key] <= 1:
                raise ValueError('invalid repair budget')

    def _save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.' + self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, sort_keys=True, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            dfd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _load(self):
        if self.path.exists():
            state = json.loads(self.path.read_text())
            if state.get('manifest') != self.manifest:
                raise ValueError('persisted manifest mismatch')
            return state
        return {'manifest': self.manifest, 'target': _target(self.manifest['initial_target']),
                'status': 'pending', 'phase': 'observe', 'observations': [], 'evidence': [],
                'classifications': [], 'health': [], 'actions': [], 'notifications': [],
                'counts': {'infrastructure': 0, 'source': 0}}

    def _attention(self, state, reason):
        state['status'], state['phase'], state['reason'] = 'attention', 'attention', reason
        self._save(state)
        self._notify(state, 'attention')

    def _notify(self, state, phase):
        # This is a journal receipt only; it cannot establish execution or delivery.
        try:
            receipt = self.backend.emit(phase, copy.deepcopy(state))
            entry = {'phase': phase, 'journal_receipt': receipt}
        except Exception as exc:
            entry = {'phase': phase, 'error': type(exc).__name__}
        state['notifications'].append(entry)
        self._save(state)

    def _health(self, state):
        try:
            result = self.backend.health()
        except Exception:
            self._attention(state, 'health-unknown')
            return False
        if not isinstance(result, dict) or result.get('state') not in ('healthy', 'unhealthy', 'unknown'):
            self._attention(state, 'health-unknown')
            return False
        state['health'].append(copy.deepcopy(result))
        self._save(state)
        if result['state'] != 'healthy' or not isinstance(result.get('receipt_path'), str) or not result['receipt_path']:
            self._attention(state, 'health-' + (result['state'] if result['state'] != 'healthy' else 'unknown'))
            return False
        return True

    def _apply(self, state, result):
        action = state['actions'][-1]
        if not isinstance(result, dict) or result.get('status') not in ('completed', 'failed'):
            self._attention(state, 'action-result-unknown')
            return
        action['result'] = copy.deepcopy(result)
        if result['status'] != 'completed' or not isinstance(result.get('receipt_path'), str) or not result['receipt_path']:
            self._attention(state, 'action-failed-or-receipt-unknown')
            return
        try:
            if action['action'] == 'repair_infrastructure':
                state['phase'] = 'dispatch_retry'
            elif action['action'] == 'repair_source':
                sha = result.get('source_sha')
                if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha) or sha == state['target']['source_sha']:
                    raise ValueError('invalid repaired sha')
                state['candidate_sha'] = sha
                state['phase'] = 'dispatch_pipeline'
            else:
                new = _target(result.get('target'))
                old = state['target']
                if new['job_name'] != old['job_name'] or new['runner_id'] != old['runner_id']:
                    raise ValueError('rerun identity mismatch')
                if action['action'] == 'retry_job':
                    if new['pipeline_id'] != old['pipeline_id'] or new['job_id'] == old['job_id'] or new['source_sha'] != old['source_sha']:
                        raise ValueError('invalid retry target')
                elif (new['pipeline_id'] == old['pipeline_id'] or new['job_id'] == old['job_id']
                      or new['source_sha'] != state['candidate_sha']):
                    raise ValueError('invalid pipeline target')
                state['target'], state['phase'] = new, 'observe'
        except (KeyError, ValueError, TypeError):
            self._attention(state, 'action-target-mismatch')
            return
        self._save(state)
        self._notify(state, action['action'] + '-completed')

    def _start(self, state, action, payload):
        if action not in ACTIONS:
            raise ValueError('invalid action')
        key = self.manifest['incident_id'] + ':' + str(len(state['actions']) + 1) + ':' + action
        record = {'action': action, 'key': key, 'payload': copy.deepcopy(payload), 'result': None}
        state['actions'].append(record)
        state['phase'] = 'action_pending'
        self._save(state)  # Durable intent precedes the non-idempotent call.
        try:
            result = self.backend.perform(action, key, copy.deepcopy(payload))
        except Exception:
            state['reason'] = 'action-uncertain-awaiting-reconciliation'
            self._save(state)
            return
        self._apply(state, result)

    def step(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self._load()
            self._save(state)
            if state['status'] in ('complete', 'attention'):
                return copy.deepcopy(state)
            if time.time() >= self.manifest['deadline_epoch']:
                self._attention(state, 'deadline-expired')
                return copy.deepcopy(state)
            if state['phase'] == 'action_pending':
                record = state['actions'][-1]
                try:
                    result = self.backend.reconcile_action(record['action'], record['key'], copy.deepcopy(record['payload']))
                except Exception:
                    result = None
                if result is None:
                    self._attention(state, 'action-uncertain')
                else:
                    self._apply(state, result)
                return copy.deepcopy(state)
            if state['phase'] in ('dispatch_retry', 'dispatch_pipeline'):
                if self._health(state):
                    action = 'retry_job' if state['phase'] == 'dispatch_retry' else 'start_pipeline'
                    payload = {'project': self.manifest['project'], 'target': copy.deepcopy(state['target'])}
                    if action == 'start_pipeline':
                        payload['source_sha'] = state['candidate_sha']
                    self._start(state, action, payload)
                return copy.deepcopy(state)
            try:
                observation = self.backend.observe(copy.deepcopy(state['target']))
                if not isinstance(observation, dict):
                    raise ValueError('invalid observation')
                observed_target = _target({k: observation[k] for k in TARGET_KEYS})
                if observed_target != state['target']:
                    raise ValueError('identity mismatch')
                if observation.get('status') not in ('running', 'success', 'failed', 'canceled', 'unknown'):
                    raise ValueError('invalid status')
            except Exception:
                self._attention(state, 'observation-unknown-or-mismatch')
                return copy.deepcopy(state)
            state['observations'].append(copy.deepcopy(observation))
            self._save(state)
            if observation['status'] == 'running':
                return copy.deepcopy(state)
            if observation['status'] in ('unknown', 'canceled'):
                self._attention(state, 'job-' + observation['status'])
                return copy.deepcopy(state)
            try:
                evidence = self.backend.retain(copy.deepcopy(observation))
                if (not isinstance(evidence, dict) or evidence.get('status') != 'export-verified'
                        or evidence.get('job_status') != observation['status']
                        or not isinstance(evidence.get('receipt_path'), str) or not evidence['receipt_path']):
                    raise ValueError('invalid evidence')
            except Exception:
                self._attention(state, 'export-evidence-unknown')
                return copy.deepcopy(state)
            state['evidence'].append(copy.deepcopy(evidence))
            self._save(state)
            if observation['status'] == 'success':
                if self._health(state):
                    state['status'], state['phase'] = 'complete', 'complete'
                    self._save(state)
                    self._notify(state, 'complete')
                return copy.deepcopy(state)
            try:
                classification = self.backend.classify(copy.deepcopy(observation), copy.deepcopy(evidence))
                if (not isinstance(classification, dict) or classification.get('kind') not in ('infrastructure', 'source', 'blocked')
                        or not isinstance(classification.get('reason'), str) or not classification['reason']
                        or not isinstance(classification.get('fingerprint'), str) or not classification['fingerprint']):
                    raise ValueError('invalid classification')
            except Exception:
                self._attention(state, 'classification-unknown')
                return copy.deepcopy(state)
            repeated = any(c['fingerprint'] == classification['fingerprint'] for c in state['classifications'])
            state['classifications'].append(copy.deepcopy(classification))
            self._save(state)
            kind = classification['kind']
            if repeated:
                self._attention(state, 'repeated-failure')
            elif kind == 'blocked':
                self._attention(state, 'failure-blocked')
            elif state['counts'][kind] >= self.manifest['max_' + kind + '_repairs']:
                self._attention(state, kind + '-budget-exhausted')
            elif self._health(state):
                state['counts'][kind] += 1
                action = 'repair_infrastructure' if kind == 'infrastructure' else 'repair_source'
                payload = {'project': self.manifest['project'], 'target': copy.deepcopy(state['target']),
                           'observation': copy.deepcopy(observation), 'evidence': copy.deepcopy(evidence),
                           'classification': copy.deepcopy(classification)}
                self._start(state, action, payload)
            return copy.deepcopy(state)
