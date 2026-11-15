"""Finite, durable recovery decisions for one explicitly selected CI incident.

The backend provides authoritative observation, bounded execution and shared
host serialization. This module does not start a watcher or establish delivery.
"""
import copy
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time


TARGET_KEYS = ('pipeline_id', 'job_id', 'source_sha', 'job_name', 'runner_id')
ACTIONS = {'repair_infrastructure', 'retry_job', 'repair_source', 'start_pipeline'}
_spec = importlib.util.spec_from_file_location('recovery_production', Path(__file__).with_name('recovery_production.py'))
production = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(production)


def _target(value):
    if isinstance(value, dict) and 'provider' in value:
        return production.target(value)
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
        initial = _target(manifest.get('initial_target'))
        self.production = 'provider' in initial
        if self.production:
            if initial['provider'] == 'gitlab' and str(manifest['project']) != initial['project_id']:
                raise ValueError('manifest project differs from target')
            if initial['provider'] == 'github' and manifest['project'] != initial['repository']:
                raise ValueError('manifest repository differs from target')
            artifacts = manifest.get('required_artifacts')
            if (not isinstance(artifacts,list) or not artifacts or len(artifacts)>100
                    or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}',x) for x in artifacts)
                    or len(set(artifacts)) != len(artifacts)):
                raise ValueError('production manifest requires explicit unique artifacts')
        if not isinstance(manifest.get('deadline_epoch'), (int, float)) or isinstance(manifest['deadline_epoch'], bool) or not math.isfinite(manifest['deadline_epoch']):
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
        allowed = ('completed', 'failed', 'pending') if self.production else ('completed', 'failed')
        if not isinstance(result, dict) or result.get('status') not in allowed:
            self._attention(state, 'action-result-unknown')
            return
        action['result'] = copy.deepcopy(result)
        if result['status'] == 'pending':
            # A provider can accept a request before assigning its real runner
            # or publishing the candidate binding. Keep the original intent;
            # the next step reconciles it rather than sending another request.
            if (action['action'] not in ('retry_job', 'start_pipeline')
                    or not isinstance(result.get('receipt_path'), str) or not result['receipt_path']
                    or not production.origin_proof(result, action['key'])):
                self._attention(state, 'pending-action-origin-unverified')
                return
            self._save(state)
            return
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
                if self.production and state['target']['provider'] in ('gitlab','github'):
                    if not production.valid_ref(result.get('candidate_ref')):
                        raise ValueError('candidate ref missing')
                    state['candidate_ref'] = result['candidate_ref']
                state['candidate_sha'] = sha
                state['phase'] = 'dispatch_pipeline'
            else:
                new = _target(result.get('target'))
                old = state['target']
                if self.production:
                    if (action['action'] == 'start_pipeline' and old['provider'] in ('gitlab','github')
                            and result.get('candidate_ref') != state.get('candidate_ref')):
                        raise ValueError('dispatch candidate ref mismatch')
                    new = production.transition(old, new, action['action'], state.get('candidate_sha'), state.get('candidate_ref'))
                    state['target'], state['phase'] = new, 'observe'
                    self._save(state)
                    self._notify(state, action['action'] + '-completed')
                    return
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
        if self.production and action in ('retry_job', 'start_pipeline') and any(
                item['action'] == action for item in state['actions']):
            self._attention(state, 'rerun-budget-exhausted')
            return
        key = self.manifest['incident_id'] + ':' + str(len(state['actions']) + 1) + ':' + action
        record = {'action': action, 'key': key, 'payload': copy.deepcopy(payload), 'result': None}
        state['actions'].append(record)
        state['phase'] = 'action_pending'
        self._save(state)  # Durable intent precedes the non-idempotent call.
        try:
            result = self.backend.perform(action, key, copy.deepcopy(payload))
        except Exception as exc:
            state['reason'] = 'action-uncertain-awaiting-reconciliation'
            self._save(state)
            if getattr(exc, 'requires_executor_hold', False) is True:
                # A daemon-owned worker may still be active. The service must
                # retain the shared lease; ordinary uncertainty cannot hide it.
                raise
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
                except Exception as exc:
                    if getattr(exc, 'requires_executor_hold', False) is True:
                        state['reason'] = 'executor-cleanup-unknown'
                        self._save(state)
                        raise
                    result = None
                if result is None:
                    self._attention(state, 'action-uncertain')
                elif self.production and not production.origin_proof(result, record['key']):
                    self._attention(state, 'action-origin-unverified')
                else:
                    self._apply(state, result)
                return copy.deepcopy(state)
            if state['phase'] in ('dispatch_retry', 'dispatch_pipeline'):
                if self._health(state):
                    action = 'retry_job' if state['phase'] == 'dispatch_retry' else 'start_pipeline'
                    payload = {'project': self.manifest['project'], 'target': copy.deepcopy(state['target'])}
                    if action == 'start_pipeline':
                        payload['source_sha'] = state['candidate_sha']
                        if self.production and state['target']['provider'] in ('gitlab','github'):
                            payload['candidate_ref'] = state['candidate_ref']
                    self._start(state, action, payload)
                return copy.deepcopy(state)
            try:
                observation = self.backend.observe(copy.deepcopy(state['target']))
                if not isinstance(observation, dict):
                    raise ValueError('invalid observation')
                observed_target = _target({k: observation[k] for k in state['target']})
                if observed_target != state['target']:
                    raise ValueError('identity mismatch')
                if observation.get('status') not in ('running', 'success', 'failed', 'canceled', 'unknown'):
                    raise ValueError('invalid status')
            except Exception:
                self._attention(state, 'observation-unknown-or-mismatch')
                return copy.deepcopy(state)
            state['observations'].append(copy.deepcopy(observation))
            self._save(state)
            if self.production and observation.get('provider_stop') is not None:
                self._attention(state, 'provider-stopped')
                return copy.deepcopy(state)
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
                if (self.production and state['target']['provider'] == 'github'
                        and not production.candidate_checkout_proof(evidence, state['target'])):
                    raise ValueError('GitHub candidate checkout identity is unverified')
            except Exception:
                self._attention(state, 'export-evidence-unknown')
                return copy.deepcopy(state)
            state['evidence'].append(copy.deepcopy(evidence))
            self._save(state)
            if (self.production and observation['status'] == 'failed'
                    and not any(n.get('phase') == 'down' for n in state['notifications'])):
                # Only a canonical failed job with retained original evidence
                # enters the incident journal. A producer hint is insufficient.
                self._notify(state, 'down')
            if observation['status'] == 'success':
                if self.production and (evidence.get('required_artifacts_verified') is not True
                        or not isinstance(evidence.get('required_artifacts_receipt'), str)
                        or not evidence['required_artifacts_receipt']
                        or not isinstance(evidence.get('verified_artifacts'),list)
                        or len(evidence['verified_artifacts']) != len(self.manifest['required_artifacts'])
                        or any(not isinstance(x,str) for x in evidence['verified_artifacts'])
                        or set(evidence['verified_artifacts']) != set(self.manifest['required_artifacts'])):
                    self._attention(state, 'required-artifacts-unverified')
                    return copy.deepcopy(state)
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
            elif self.production and kind == 'source' and not production.reproducer_proof(classification, state['target']['source_sha']):
                self._attention(state, 'source-reproducer-unverified')
            elif self._health(state):
                state['counts'][kind] += 1
                action = 'repair_infrastructure' if kind == 'infrastructure' else 'repair_source'
                payload = {'project': self.manifest['project'], 'target': copy.deepcopy(state['target']),
                           'observation': copy.deepcopy(observation), 'evidence': copy.deepcopy(evidence),
                           'classification': copy.deepcopy(classification)}
                self._start(state, action, payload)
            return copy.deepcopy(state)
