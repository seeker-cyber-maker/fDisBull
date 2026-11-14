"""GitHub actual-job adapter for the finite recovery controller.

All I/O is injected. This module never starts a listener, acquires a lease,
dispatches a new workflow, downloads artifacts, or contacts GitHub by itself.
A transport's POST response must report the observed HTTP status explicitly;
GitHub's rerun-job success is 201 with no response body.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import re


_spec = importlib.util.spec_from_file_location('production_transport', Path(__file__).with_name('production_transport.py'))
_transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transport)


class GitHubRecoveryBackend:
    def __init__(self, *, repository, control_sha, transport, source_binding,
                 retain, classify, health, emit, claim_action, save_acceptance, load_acceptance,
                 repair_infrastructure, repair_source, resolve_dispatch, reconcile_other,
                 lease, required_artifacts, workflow_id, after_acceptance=None):
        if not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('invalid repository')
        if not isinstance(control_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', control_sha):
            raise ValueError('invalid control SHA')
        if (not isinstance(required_artifacts, (tuple, list)) or not required_artifacts
                or any(not isinstance(x, str) or not x for x in required_artifacts)
                or len(set(required_artifacts)) != len(required_artifacts)):
            raise ValueError('required artifact names must be explicit')
        self.repository, self.control_sha = repository, control_sha
        self.transport, self.source_binding = transport, source_binding
        self.retain_callback, self.classify_callback = retain, classify
        self.health_callback, self.emit_callback = health, emit
        self.claim_action, self.save_acceptance, self.load_acceptance = claim_action, save_acceptance, load_acceptance
        if isinstance(workflow_id, bool) or not str(workflow_id).isascii() or not str(workflow_id).isdecimal() or int(workflow_id) <= 0:
            raise ValueError('invalid workflow ID')
        self.workflow_id = str(int(workflow_id))
        self.repairs = {'repair_infrastructure': repair_infrastructure, 'repair_source': repair_source}
        self.resolve_dispatch = resolve_dispatch
        self.after_acceptance = after_acceptance
        self.reconcile_other, self.lease = reconcile_other, lease
        self.required_artifacts = frozenset(required_artifacts)
        self.base = '/repos/' + repository + '/actions'
        self.observed = {}

    def _target(self, value):
        keys = {'provider', 'repository', 'run_id', 'run_attempt', 'job_id', 'source_sha', 'job_name', 'runner_id', 'ref', 'control_sha'}
        if type(value) is not dict or set(value) != keys or value['provider'] != 'github' or value['repository'] != self.repository:
            raise ValueError('target repository or fields mismatch')
        for name in ('run_id', 'run_attempt', 'job_id', 'runner_id'):
            v = value[name]
            if isinstance(v, bool) or not isinstance(v, (int, str)) or not str(v).isascii() or not str(v).isdecimal() or int(v) <= 0:
                raise ValueError('invalid target identity')
        if not isinstance(value['source_sha'], str) or not re.fullmatch(r'[0-9a-f]{40}', value['source_sha']):
            raise ValueError('invalid source SHA')
        if (value['control_sha'] != self.control_sha or not isinstance(value['ref'], str)
                or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', value['ref']) or '..' in value['ref']
                or value['ref'].startswith(('/', '-')) or value['ref'].endswith(('/', '.'))):
            raise ValueError('invalid control identity')
        if (not isinstance(value['job_name'], str) or not 1 <= len(value['job_name']) <= 200
                or any(ord(c) < 32 or ord(c) == 127 for c in value['job_name'])):
            raise ValueError('invalid job name')
        return {k: str(int(v)) if k in ('run_id', 'run_attempt', 'job_id', 'runner_id') else v for k, v in value.items()}

    def _get(self, path):
        envelope = self.transport.request('GET', path)
        if type(envelope) is not dict or set(envelope) != {'http_status', 'data', 'request_id'} or envelope['http_status'] != 200:
            raise ValueError('provider read unavailable')
        return envelope['data']

    def _attempt_jobs(self, target):
        jobs = []
        for page in range(1, 11):
            value = self._get(self.base + '/runs/' + target['run_id'] + '/attempts/' + target['run_attempt']
                                 + '/jobs?per_page=100&page=' + str(page))
            if type(value) is not dict or type(value.get('jobs')) is not list or type(value.get('total_count')) is not int:
                raise ValueError('invalid attempt job list')
            jobs.extend(value['jobs'])
            if len(jobs) > value['total_count'] or len(value['jobs']) > 100:
                raise ValueError('inconsistent attempt job list')
            if len(jobs) == value['total_count']:
                return jobs
            if len(value['jobs']) != 100:
                raise ValueError('incomplete attempt job list')
        raise ValueError('attempt job list exceeds bound')

    def observe(self, target):
        target = self._target(target)
        run = self._get(self.base + '/runs/' + target['run_id'] + '/attempts/' + target['run_attempt'])
        job = self._get(self.base + '/jobs/' + target['job_id'])
        if (type(run) is not dict or str(run.get('id')) != target['run_id']
                or str(run.get('run_attempt')) != target['run_attempt']
                or (run.get('repository') or {}).get('full_name') != self.repository
                or run.get('head_sha') != self.control_sha or run.get('head_branch') != target['ref'].removeprefix('refs/heads/') or type(job) is not dict
                or str(job.get('id')) != target['job_id'] or str(job.get('run_id')) != target['run_id']
                or job.get('name') != target['job_name'] or job.get('head_sha') != self.control_sha
                or str(job.get('runner_id')) != target['runner_id']):
            raise ValueError('canonical job or run identity mismatch')
        matches = [j for j in self._attempt_jobs(target) if type(j) is dict and str(j.get('id')) == target['job_id']]
        if len(matches) != 1 or any(matches[0].get(k) != job.get(k) for k in ('id', 'run_id', 'head_sha', 'name', 'runner_id')):
            raise ValueError('job is not uniquely linked to this run attempt')
        binding = self.source_binding(copy.deepcopy(target), copy.deepcopy(run), copy.deepcopy(job))
        if (type(binding) is not dict or binding.get('verified') is not True
                or binding.get('target') != target or not isinstance(binding.get('receipt_path'), str)
                or not binding['receipt_path']):
            raise ValueError('candidate SHA binding unavailable')
        raw, conclusion = job.get('status'), job.get('conclusion')
        if raw in ('queued', 'in_progress', 'waiting', 'requested', 'pending'):
            status = 'running'
        elif raw == 'completed':
            status = {'success': 'success', 'failure': 'failed', 'timed_out': 'failed',
                      'cancelled': 'canceled'}.get(conclusion, 'unknown')
        else:
            status = 'unknown'
        observation = {**target, 'status': status, 'provider_status': raw, 'conclusion': conclusion,
                       'control_sha': self.control_sha, 'source_binding_receipt': binding['receipt_path']}
        self.observed[(target['run_id'], target['run_attempt'], target['job_id'])] = copy.deepcopy(observation)
        return observation

    def retain(self, observation):
        target = self._target({k: observation[k] for k in ('provider', 'repository', 'run_id', 'run_attempt',
                                                           'job_id', 'source_sha', 'job_name', 'runner_id', 'ref', 'control_sha')})
        if self.observed.get((target['run_id'], target['run_attempt'], target['job_id'])) != observation:
            raise ValueError('observation not verified by this backend')
        evidence = self.retain_callback(copy.deepcopy(observation), sorted(self.required_artifacts))
        if (type(evidence) is not dict or evidence.get('status') != 'export-verified'
                or evidence.get('job_status') != observation['status'] or evidence.get('target') != target
                or evidence.get('host_export_verified') is not True
                or not isinstance(evidence.get('receipt_path'), str) or not evidence['receipt_path']
                or observation['status'] == 'success' and type(evidence.get('verified_artifacts')) is not list
                or observation['status'] == 'success' and (set(evidence['verified_artifacts']) != self.required_artifacts
                    or len(evidence['verified_artifacts']) != len(self.required_artifacts))
                or observation['status'] == 'failed' and evidence.get('failed_log_verified') is not True):
            raise ValueError('required retained evidence unavailable')
        return evidence

    def classify(self, observation, evidence):
        result = self.classify_callback(copy.deepcopy(observation), copy.deepcopy(evidence))
        if (type(result) is not dict or result.get('verified') is not True
                or result.get('kind') not in ('infrastructure', 'source', 'blocked')
                or not isinstance(result.get('reason'), str) or not result['reason']
                or not isinstance(result.get('fingerprint'), str) or not result['fingerprint']):
            return {'kind': 'blocked', 'reason': 'classification_unverified', 'fingerprint': 'classification_unverified'}
        if result['kind'] != 'blocked' and result.get('eligible_for_repair') is not True:
            return {'kind': 'blocked', 'reason': 'repair_not_verified', 'fingerprint': 'repair_not_verified'}
        return result

    def health(self):
        return self.health_callback()

    def emit(self, phase, state):
        return self.emit_callback(phase, copy.deepcopy(state))

    def perform(self, action, key, payload):
        if self.lease() is not True:
            raise RuntimeError('executor lease unavailable')
        if action in self.repairs:
            return self.repairs[action](key, copy.deepcopy(payload))
        if action not in ('retry_job', 'start_pipeline'):
            raise ValueError('action not supported')
        old = self._target(payload['target'])
        if action == 'start_pipeline':
            sha = payload.get('source_sha')
            if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha) or sha == old['source_sha']:
                raise ValueError('changed candidate SHA required')
        if action == 'retry_job':
            previous = self.observe(old)
            latest = self._get(self.base + '/runs/' + old['run_id'])
            if (previous['status'] != 'failed' or type(latest) is not dict
                    or str(latest.get('id')) != old['run_id']
                    or str(latest.get('run_attempt')) != old['run_attempt']
                    or latest.get('head_sha') != self.control_sha
                    or (latest.get('repository') or {}).get('full_name') != self.repository):
                raise ValueError('retry origin is not the latest failed attempt')
        claim = self.claim_action(action, key, copy.deepcopy(payload))
        if type(claim) is not dict or claim.get('durable') is not True or claim.get('new') is not True:
            raise RuntimeError('retry intent unavailable or already claimed; reconcile only')
        path, body, accepted_status = self._action_request(action, key, payload, old)
        response = self.transport.for_action(key)('POST', path, body)
        if (type(response) is not dict or set(response) != {'http_status', 'data', 'request_id'}
                or response['http_status'] != accepted_status or response['data'] is not None
                or response['request_id'] is not None and (not isinstance(response['request_id'], str)
                    or not re.fullmatch(r'[A-Za-z0-9:._-]{1,128}', response['request_id']))):
            raise RuntimeError('rerun response unknown')
        proof = {'action': action, 'target': old, 'request': {'method': 'POST',
                 'path': path, 'payload': body},
                 'envelope': response}
        saved = self.save_acceptance(key, copy.deepcopy(proof))
        if not isinstance(saved, str) or not saved:
            raise RuntimeError('accepted response not durably retained')
        return self.reconcile_action(action, key, payload)

    def _action_request(self, action, key, payload, old):
        if action == 'retry_job':
            return self.base + '/jobs/' + old['job_id'] + '/rerun', {}, 201
        nonce = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return (self.base + '/workflows/' + self.workflow_id + '/dispatches',
                {'ref': old['ref'], 'inputs': {'nonce': nonce, 'candidate_sha': payload['source_sha']}}, 204)

    def reconcile_action(self, action, key, payload):
        if self.lease() is not True:
            return None
        if action not in ('retry_job', 'start_pipeline'):
            return self.reconcile_other(action, key, copy.deepcopy(payload))
        old = self._target(payload['target'])
        path, body, accepted_status = self._action_request(action, key, payload, old)
        accepted = self.load_acceptance(key)
        if accepted is None:
            remote = self.transport.receipt(key)
            remote = remote.get('receipt') if type(remote) is dict else None
            if type(remote) is not dict or remote.get('action_key') != key or remote.get('status') != 'accepted':
                return None
            digest = _transport.request_digest('github', 'POST', path, body)
            if remote.get('request_sha256') != digest:
                return None
            envelope = remote.get('envelope')
            proof = {'action': action, 'target': old, 'request': {'method': 'POST', 'path': path, 'payload': body}, 'envelope': envelope}
            receipt_path = self.save_acceptance(key, copy.deepcopy(proof))
            if not isinstance(receipt_path, str) or not receipt_path:
                return None
            accepted = {'proof': proof, 'receipt_path': receipt_path}
        if (type(accepted) is not dict or set(accepted) != {'proof', 'receipt_path'}
                or not isinstance(accepted['receipt_path'], str) or not accepted['receipt_path']):
            return None
        proof = accepted['proof']
        if (type(proof) is not dict or set(proof) != {'action', 'target', 'request', 'envelope'}
                or proof['action'] != action or proof['target'] != old
                or proof['request'] != {'method': 'POST', 'path': path, 'payload': body}
                or type(proof['envelope']) is not dict
                or set(proof['envelope']) != {'http_status', 'data', 'request_id'}
                or proof['envelope']['http_status'] != accepted_status or proof['envelope']['data'] is not None
                or proof['envelope']['request_id'] is not None and (not isinstance(proof['envelope']['request_id'], str)
                    or not re.fullmatch(r'[A-Za-z0-9:._-]{1,128}', proof['envelope']['request_id']))):
            return None
        if self.after_acceptance is not None:
            self.after_acceptance(action, key, copy.deepcopy(payload), copy.deepcopy(proof))
        pending = {'status': 'pending', 'receipt_path': accepted['receipt_path'],
                   'origin_proof': {'verified': True, 'kind': 'durable-accepted-action',
                                    'action_key': key, 'receipt_path': accepted['receipt_path']}}
        if action == 'start_pipeline':
            linked = self.resolve_dispatch(key, copy.deepcopy(proof), copy.deepcopy(payload))
            if (type(linked) is not dict or linked.get('verified') is not True
                    or linked.get('nonce') != body['inputs']['nonce']
                    or not isinstance(linked.get('receipt_path'), str) or not linked['receipt_path']):
                return pending
            try:
                new = self._target(linked['target'])
                if (new['run_id'] == old['run_id'] or new['job_id'] == old['job_id']
                        or new['run_attempt'] != '1' or new['source_sha'] != payload['source_sha']
                        or any(new[k] != old[k] for k in ('repository', 'job_name', 'runner_id', 'ref', 'control_sha'))):
                    raise ValueError('dispatch linkage mismatch')
                self.observe(new)
            except (KeyError, TypeError, ValueError):
                return pending
            return {'status': 'completed', 'target': new, 'receipt_path': accepted['receipt_path'],
                    'candidate_ref': payload.get('candidate_ref'),
                    'origin_proof': {'verified': True, 'kind': 'durable-accepted-action',
                                     'action_key': key, 'receipt_path': linked['receipt_path']}}
        new = {**old, 'run_attempt': str(int(old['run_attempt']) + 1)}
        latest = self._get(self.base + '/runs/' + old['run_id'])
        if (type(latest) is not dict or str(latest.get('id')) != old['run_id']
                or latest.get('head_sha') != self.control_sha
                or (latest.get('repository') or {}).get('full_name') != self.repository):
            return None
        if str(latest.get('run_attempt')) == old['run_attempt']:
            return pending
        if str(latest.get('run_attempt')) != new['run_attempt']:
            return None
        run = self._get(self.base + '/runs/' + old['run_id'] + '/attempts/' + new['run_attempt'])
        if (type(run) is not dict or str(run.get('id')) != old['run_id']
                or str(run.get('run_attempt')) != new['run_attempt'] or run.get('head_sha') != self.control_sha
                or run.get('head_branch') != old['ref'].removeprefix('refs/heads/')
                or (run.get('repository') or {}).get('full_name') != self.repository):
            return None
        candidates = [j for j in self._attempt_jobs(new) if type(j) is dict and j.get('name') == old['job_name']
                      and str(j.get('id')) != old['job_id'] and str(j.get('run_id')) == old['run_id']
                      and j.get('head_sha') == self.control_sha and str(j.get('runner_id')) == old['runner_id']]
        if not candidates:
            return pending
        if len(candidates) != 1:
            return None
        new['job_id'] = str(candidates[0]['id'])
        try:
            self.observe(new)
        except ValueError:
            return pending
        return {'status': 'completed', 'target': new, 'receipt_path': accepted['receipt_path'],
                'origin_proof': {'verified': True, 'kind': 'durable-accepted-action',
                                 'action_key': key, 'receipt_path': accepted['receipt_path']}}
