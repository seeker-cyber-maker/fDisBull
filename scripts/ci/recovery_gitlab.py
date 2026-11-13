"""Bounded GitLab/OVH adapter for the finite CI recovery controller.

No operation starts automatically. The caller owns the long-lived executor
lease, the controller loop, and source repair authorization.
"""
import base64
from contextlib import contextmanager
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import select
import shlex
import subprocess
import time
from urllib.parse import quote, urlencode


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CI_STATUS = _load(Path(__file__).resolve().parents[1] / 'ci_status.py', 'ci_status_recovery')
WEBSITES = ('https://www.brewsterjennings.ca/', 'https://release.brewsterjennings.ca/')
CHECKS = ('n8n_service', 'n8n_mcp', 'n8n_monitor_workflow', 'n8n_assistant_key')
REPO = 'brewster-jennings-group/fdisbull'

# All values arrive through JSON stdin, never interpolated into shell code.
REMOTE = r'''import base64,fcntl,hashlib,importlib.util,json,os,pathlib,re,subprocess,sys,time
p=json.load(sys.stdin)
op=p['op']; incident=p['incident']
if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',incident): raise ValueError('incident')
control=pathlib.Path('/var/lib/fdisbull-ci/control/recovery')/incident
root=pathlib.Path('/var/lib/fdisbull-ci/results')
def safe_directory(path):
 for part in reversed((path,*path.parents)):
  if part.is_symlink(): raise ValueError('symlink parent')
  if part.exists() and not part.is_dir(): raise ValueError('non-directory parent')
 path.mkdir(parents=True,exist_ok=True,mode=0o700)
 if any(part.is_symlink() for part in (path,*path.parents)):raise ValueError('symlink parent')
def put(name,data):
 if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',name): raise ValueError('name')
 safe_directory(control)
 path=control/name
 try:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 except FileExistsError:
  if path.is_symlink() or not path.is_file() or path.read_bytes()!=data: raise ValueError('receipt conflict')
 else:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 return str(path)
def receipt(name,value): return put(name,(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode())
def idle():
 result=subprocess.run(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,timeout=15,check=True)
 if any(name.startswith('runner-') for name in result.stdout.splitlines()): raise ValueError('runner not idle')
if op=='health':
 r=subprocess.run(['/usr/bin/python3','/usr/local/libexec/operations-monitor.py','--snapshot'],capture_output=True,text=True,timeout=45,check=True)
 value=json.loads(r.stdout);path=receipt(p['name'],value);out={'snapshot':value,'receipt_path':path}
elif op=='install_verifier':
 data=base64.b64decode(p['content'],validate=True)
 if hashlib.sha256(data).hexdigest()!=p['sha256']:raise ValueError('helper hash')
 out={'path':put('ovh-export-'+p['sha256']+'.py',data)}
elif op=='verify':
 helper=control/('ovh-export-'+p['sha256']+'.py')
 if helper.is_symlink() or hashlib.sha256(helper.read_bytes()).hexdigest()!=p['sha256']:raise ValueError('helper mismatch')
 spec=importlib.util.spec_from_file_location('export_verify',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 value=module.verify_job_export(root,p['pipeline_id'],p['job_id'],p['source_sha'],p['job_name'],expected_job_status=p['job_status'])
 name='result.json' if p['job_status']=='success' else 'diagnostic.json'
 evidence=root/p['pipeline_id']/p['job_id']/'exported'/'artifacts'/'recovery'/name
 if evidence.is_symlink() or not evidence.is_file():raise ValueError('missing rehearsal evidence')
 result=json.loads(evidence.read_text())
 if result.get('incident_id')!=incident or result.get('source_commit')!=p['source_sha'] or result.get('profile')!='ci-recovery-rehearsal':raise ValueError('diagnostic identity')
 if p['job_status']=='success' and result.get('passed') is not True:raise ValueError('success result incomplete')
 value.update(diagnostic=result,provider_failure_reason=p.get('failure_reason'))
 path=receipt('export-'+p['pipeline_id']+'-'+p['job_id']+'.json',value)
 out={'receipt_path':path,'result':value}
elif op=='repair':
 idle()
 data=base64.b64decode(p['content'],validate=True)
 if hashlib.sha256(data).hexdigest()!=p['sha256']:raise ValueError('marker mismatch')
 directory=root/'recovery-inputs'/incident
 safe_directory(directory)
 path=directory/'ready.json'
 try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 except FileExistsError:
  if path.is_symlink() or not path.is_file() or path.read_bytes()!=data:raise ValueError('marker conflict')
 else:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 value={'status':'completed','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'marker_path':str(path)}
 out={'status':'completed','receipt_path':receipt('repair-'+p['keyhash']+'.json',value)}
elif op=='read_repair':
 path=control/('repair-'+p['keyhash']+'.json')
 if path.is_symlink() or not path.is_file():raise ValueError('missing repair receipt')
 value=json.loads(path.read_text());marker=root/'recovery-inputs'/incident/'ready.json'
 if value.get('status')!='completed' or value.get('sha256')!=p['sha256'] or marker.is_symlink() or hashlib.sha256(marker.read_bytes()).hexdigest()!=p['sha256']:raise ValueError('repair proof mismatch')
 out={'status':'completed','receipt_path':str(path)}
elif op=='receipt':
 out={'receipt_path':receipt(p['name'],p['value'])}
elif op=='emit':
 r=subprocess.run(['sudo','-n','-u','operations-alerts','/usr/bin/python3','/usr/local/libexec/ci_incident.py','append'],input=json.dumps(p['event']),capture_output=True,text=True,timeout=30,check=True)
 out=json.loads(r.stdout)
else:raise ValueError('unknown operation')
print(json.dumps(out,separators=(',',':')))
'''


class GitLabRecoveryBackend:
    def __init__(self, config, legacy, source_repair, *, transport=None, provider=None, status_api=None):
        self.config = dict(config)
        self.legacy = legacy
        self.source_repair = source_repair
        self.provider = provider or legacy.GitLab()
        self.status_api = status_api or CI_STATUS
        self.transport = transport
        self.next_refresh_at = None
        self.refresh_reason = None
        self.prepared = False
        self._lease_held = False
        self._lease_process = None
        self.jobs = {}
        self.state_dir = Path(config['state_dir'])
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.provider_state_dir = Path(config['provider_state_dir']) if config.get('provider_state_dir') is not None else self.status_api.default_state_dir(config['repo_root'])
        self.incident = config['incident_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', self.incident):
            raise ValueError('invalid incident')
        if int(config['project_id']) != 88349936 or int(config['runner_id']) != 58990209:
            raise ValueError('unauthorized project or runner')
        self.project = str(config['project_id'])
        self.runner = str(config['runner_id'])
        self.prefix = config['ssh_prefix']
        if (not isinstance(self.prefix, list) or len(self.prefix) < 2
                or any(not isinstance(x, str) or not x or '\n' in x or '\x00' in x for x in self.prefix)
                or not re.fullmatch(r'(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9_.:-]+', self.prefix[-1])
                or Path(self.prefix[0]).name not in ('ssh', 'tailscale')):
            raise ValueError('invalid native SSH argv')
        if not isinstance(config['deadline_epoch'], (float, int)) or not math.isfinite(config['deadline_epoch']):
            raise ValueError('invalid deadline')
        if config['deadline_epoch'] - time.time() > 3500:
            raise ValueError('incident exceeds finite host lease')
        data = config['marker_bytes'].encode('utf-8')
        if hashlib.sha256(data).hexdigest() != config['marker_sha256']:
            raise ValueError('marker hash mismatch')
        if not re.fullmatch(r'[0-9a-f-]{36}', config['expected_boot_id']):
            raise ValueError('invalid expected boot id')
        if not isinstance(config['ref'], str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', config['ref']) or '..' in config['ref']:
            raise ValueError('invalid ref')

    def rpc(self, code, payload):
        if self.transport is not None:
            return self.transport(code, payload)
        encoded = base64.b64encode(code.encode()).decode()
        command = 'sudo -n /usr/bin/python3 -c ' + shlex.quote("import base64;exec(base64.b64decode('" + encoded + "'))")
        result = subprocess.run([*self.prefix, command], input=json.dumps(payload), text=True,
                                capture_output=True, timeout=65, check=True)
        return json.loads(result.stdout)

    def _rpc(self, op, **payload):
        return self.rpc(REMOTE, {'op': op, 'incident': self.incident, **payload})

    @contextmanager
    def lease(self):
        if self._lease_held:
            raise RuntimeError('lease already held')
        if self.transport is not None and hasattr(self.transport, 'lease'):
            with self.transport.lease():
                self._lease_held = True
                try: yield self
                finally: self._lease_held = False
            return
        duration = min(3600, math.ceil(self.config['deadline_epoch'] - time.time() + 60))
        if duration <= 60:
            raise RuntimeError('incident deadline expired')
        code = "import fcntl,os,signal,subprocess,sys;signal.alarm(" + str(duration) + ");f=open('/var/lib/fdisbull-ci/control/ci-executor.lock','a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);r=subprocess.run(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,timeout=15,check=True);assert not any(x.startswith('runner-') for x in r.stdout.splitlines());print('LEASED',flush=True);sys.stdin.read()"
        command = 'sudo -n /usr/bin/python3 -c ' + shlex.quote(code)
        process = subprocess.Popen([*self.prefix, command], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self._lease_process = process
        try:
            if not select.select([process.stdout], [], [], 30)[0] or process.stdout.readline().strip() != 'LEASED':
                raise RuntimeError('host lease or idle check unavailable')
            self._lease_held = True
            yield self
        finally:
            self._lease_held = False
            self._lease_process = None
            if process.stdin: process.stdin.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)

    def prepare_step(self, state_or_none):
        state = state_or_none or {'phase': 'observe'}
        phase = state.get('phase')
        pending_action = (state.get('actions') or [{}])[-1].get('action')
        needs = (phase in ('observe', 'dispatch_retry', 'dispatch_pipeline')
                 or (phase == 'action_pending' and pending_action in ('retry_job', 'start_pipeline')))
        self.prepared = False
        if not needs:
            return True
        result = self.status_api.reserve_refresh(repo=REPO, host='gitlab.com', owner=self.config['owner_id'], state_dir=self.provider_state_dir)
        self.next_refresh_at = result.get('next_refresh_at')
        self.refresh_reason = result.get('reason')
        self.prepared = result.get('allowed') is True
        return self.prepared

    def _request(self, method, path, body=None):
        if self._lease_process is not None and self._lease_process.poll() is not None:
            raise RuntimeError('host lease ended')
        if not self.prepared:
            raise RuntimeError('repository refresh not reserved')
        resource = 'other'
        if '/repository/branches/' in path: resource = 'branch'
        elif re.search(r'/jobs/\d+/retry$', path): resource = 'job_retry'
        elif re.search(r'/pipelines/\d+/jobs\?', path): resource = 'pipeline_jobs'
        elif re.search(r'/pipelines/\d+$', path): resource = 'pipeline_detail'
        elif re.search(r'/pipelines\?', path): resource = 'pipeline_list'
        elif path.endswith('/pipeline'): resource = 'pipeline_create'
        elif re.search(r'/jobs/\d+$', path): resource = 'job_detail'
        receipt = self.state_dir / ('provider-request-' + str(time.time_ns()) + '-' + os.urandom(8).hex() + '.json')
        record = {'method': method if method in ('GET', 'POST') else 'other', 'resource': resource,
                  'state': 'started', 'started_epoch': time.time()}
        self.status_api._write(receipt, record)
        try:
            response = self.provider.request(method, path, body=body)
        except Exception as exc:
            message = str(exc).lower()
            http = re.fullmatch(r'gitlab (get|post) returned http ([1-5][0-9]{2})', message)
            transport = re.fullmatch(r'gitlab (get|post) transport error \((urlerror|timeouterror|httpexception)\)', message)
            record.update(state='error', error_class=type(exc).__name__ if type(exc).__name__ in
                          ('RuntimeError', 'TimeoutError', 'ValueError', 'OSError') else 'other')
            if http and http.group(1).upper() == method: record['http_status'] = int(http.group(2))
            if transport and transport.group(1).upper() == method: record['transport_type'] = transport.group(2)
            self.status_api._write(receipt, record)
            reason = next(('provider_http_' + code for code in ('401', '403', '429') if re.search(r'http\s+' + code + r'\b', message)), None)
            if reason is None and CI_STATUS._restricted(message): reason = 'provider_restriction'
            if reason:
                result = self.status_api.record_provider_stop(repo=REPO, host='gitlab.com', owner=self.config['owner_id'], reason=reason, state_dir=self.provider_state_dir)
                if not result.get('recorded') and result.get('reason') != 'provider_stopped':
                    raise RuntimeError('provider stop could not be persisted') from None
            raise
        record['state'] = 'response_received'
        if isinstance(response, dict) and type(response.get('id')) is int and response['id'] >= 0:
            record['result_id'] = response['id']
        self.status_api._write(receipt, record)
        return response

    def _job_list(self, pipeline):
        jobs = []
        for page in range(1, 11):
            batch = self._request('GET', f'/projects/{self.project}/pipelines/{pipeline}/jobs?per_page=100&page={page}&include_retried=true')
            if not isinstance(batch, list): raise ValueError('invalid jobs response')
            jobs.extend(batch)
            if len(batch) < 100: return jobs
        raise ValueError('job list exceeds bound')

    def observe(self, target):
        pipe = self._request('GET', f"/projects/{self.project}/pipelines/{target['pipeline_id']}")
        job = self._request('GET', f"/projects/{self.project}/jobs/{target['job_id']}")
        if (str(pipe.get('id')) != str(target['pipeline_id']) or pipe.get('sha') != target['source_sha']
                or str(pipe.get('project_id')) != self.project or str(job.get('id')) != str(target['job_id'])
                or str(job.get('pipeline', {}).get('id')) != str(target['pipeline_id'])
                or job.get('commit', {}).get('id') != target['source_sha'] or job.get('name') != target['job_name']):
            raise ValueError('provider identity mismatch')
        status = job.get('status')
        runner = job.get('runner') or {}
        observed_runner = str(runner['id']) if runner.get('id') is not None else None
        if status in ('running', 'success', 'failed', 'canceled') and observed_runner != self.runner:
            raise ValueError('executed job runner unknown or mismatched')
        mapped = 'running' if status in ('created', 'pending', 'preparing', 'waiting_for_resource', 'running') else status
        if mapped not in ('running', 'success', 'failed', 'canceled'):
            mapped = 'unknown'
        self.jobs[str(target['job_id'])] = job
        return {**target, 'status': mapped, 'provider_status': status,
                'observed_runner_id': observed_runner, 'runner_verified': observed_runner == self.runner,
                'failure_reason': job.get('failure_reason')}

    def _bind_legacy(self, target):
        legacy = self.legacy
        legacy.PIPELINE_ID, legacy.PROJECT_ID = int(target['pipeline_id']), int(self.project)
        legacy.EXPECTED_SHA = target['source_sha']
        legacy.REMOTE_RESULTS = '/var/lib/fdisbull-ci/results/' + str(target['pipeline_id'])
        legacy.LOCAL_STATUS = self.state_dir / ('legacy-' + str(target['pipeline_id']) + '-' + target['source_sha'] + '.json')
        legacy.REMOTE_PUT = re.sub(r'^root=.*$', 'root=' + repr(legacy.REMOTE_RESULTS), legacy.REMOTE_PUT, count=1, flags=re.M)
        prefix = list(self.prefix)
        legacy.ssh_command = lambda code, args: [*prefix, 'sudo -n python3 -c ' + shlex.quote(code), *args]

    def retain(self, observation):
        self._bind_legacy(observation)
        state = self.legacy.load_state()
        job = self.jobs.get(str(observation['job_id']))
        if not job: raise ValueError('missing verified provider job')
        self.legacy.save_trace(self.provider, job, state)
        saved = state['saved_jobs'].get(str(observation['job_id']), {})
        if saved.get('trace_available') is not True: raise ValueError('trace unavailable')
        helper = (Path(self.config['repo_root']) / 'scripts/ci/ovh-export.py').read_bytes()
        sha = hashlib.sha256(helper).hexdigest()
        self._rpc('install_verifier', content=base64.b64encode(helper).decode(), sha256=sha)
        out = self._rpc('verify', sha256=sha, pipeline_id=str(observation['pipeline_id']),
                        job_id=str(observation['job_id']), source_sha=observation['source_sha'],
                        job_name=observation['job_name'], job_status=observation['status'],
                        failure_reason=observation.get('failure_reason'))
        result = out['result']
        if result.get('status') != 'export-verified' or result.get('job_status') != observation['status']:
            raise ValueError('export verification failed')
        evidence = {'status': 'export-verified', 'job_status': observation['status'],
                    'receipt_path': out['receipt_path'], 'diagnostic': result['diagnostic'],
                    'failure_reason': observation.get('failure_reason')}
        if observation['status'] == 'failed':
            down_path = self.state_dir / ('down-' + self.incident + '.json')
            if down_path.is_symlink(): raise ValueError('unsafe down receipt')
            if down_path.exists():
                first = json.loads(down_path.read_text())
            else:
                first = {'observation': observation, 'receipt_path': evidence['receipt_path']}
                self.status_api._write(down_path, first)
            self._incident_event('down', first['observation'], first['receipt_path'], 'ci_job_failed')
        return evidence

    def classify(self, observation, evidence):
        diagnostic = evidence.get('diagnostic', {})
        pair = (diagnostic.get('kind'), diagnostic.get('reason'))
        if pair not in (('infrastructure', 'missing_ci_owned_input'), ('source', 'incomplete_capture_accepted')):
            return {'kind': 'blocked', 'reason': 'unrecognized_diagnostic', 'fingerprint': 'unrecognized'}
        if diagnostic.get('input_sha256') != self.config['marker_sha256']:
            return {'kind': 'blocked', 'reason': 'input_hash_mismatch', 'fingerprint': 'input_hash_mismatch'}
        if pair[0] == 'source' and diagnostic.get('passed') is not False:
            return {'kind': 'blocked', 'reason': 'source_diagnostic_incomplete', 'fingerprint': 'source_diagnostic_incomplete'}
        return {'kind': pair[0], 'reason': pair[1], 'fingerprint': pair[1]}

    def health(self):
        try:
            out = self._rpc('health', name='health-' + str(time.time_ns()) + '.json')
            now = time.time()
            s = out['snapshot']
            observed = s['observed_epoch']
            if (not isinstance(observed, (int, float)) or not 0 <= now - observed <= 120
                    or s.get('read_only') is not True or s.get('model_required') is not False
                    or s.get('boot_id') != self.config['expected_boot_id']):
                return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            checks = [s['doctor_observation'], s['n8n_readiness'], *[s['health_checks'][k] for k in CHECKS], *[s['websites'][k] for k in WEBSITES]]
            states = [v['state'] for v in checks]
            if any(x not in ('healthy', 'unhealthy', 'unknown') for x in states): raise ValueError('invalid state')
            for check in checks:
                checked = check.get('checked_epoch')
                if not isinstance(checked, (int, float)) or not 0 <= now - checked <= 660:
                    return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            if (s['doctor_observation'].get('fresh') is not True
                    or any(s['health_checks'][k].get('fresh') is not True for k in CHECKS)):
                return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            if s['disk']['state'] != 'known' or not isinstance(s['disk']['free_bytes'], int):
                return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            if not isinstance(s['disk'].get('checked_epoch'), (int, float)) or not 0 <= now - s['disk']['checked_epoch'] <= 120:
                return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            if 'unhealthy' in states or s['disk']['free_bytes'] < 20_100_000_000:
                return {'state': 'unhealthy', 'receipt_path': out['receipt_path']}
            if 'unknown' in states:
                return {'state': 'unknown', 'receipt_path': out['receipt_path']}
            return {'state': 'healthy', 'receipt_path': out['receipt_path']}
        except Exception:
            return {'state': 'unknown', 'receipt_path': None}

    def _intent_path(self, key):
        return self.state_dir / ('action-' + hashlib.sha256(key.encode()).hexdigest() + '.json')

    def _intent(self, action, key, payload):
        path = self._intent_path(key)
        if path.exists() or path.is_symlink(): raise RuntimeError('action intent already exists; reconcile only')
        record = {'incident': self.incident, 'action': action, 'key': key,
                  'payload': payload, 'created_epoch': time.time()}
        self.status_api._write(path, record)
        return record

    def _load_intent(self, action, key, payload):
        path = self._intent_path(key)
        if path.is_symlink(): raise ValueError('unsafe intent')
        record = json.loads(path.read_text())
        if (record.get('incident'), record.get('action'), record.get('key'), record.get('payload')) != (self.incident, action, key, payload):
            raise ValueError('intent mismatch')
        return record

    def _action_receipt(self, key, value):
        name = 'action-' + hashlib.sha256(key.encode()).hexdigest() + '.json'
        return self._rpc('receipt', name=name, value=value)['receipt_path']

    def _make_target(self, job, pipeline, sha, previous):
        if (not isinstance(job, dict) or job.get('name') != previous['job_name']
                or not str(job.get('id', '')).isdecimal()
                or str(job.get('pipeline', {}).get('id')) != str(pipeline)
                or job.get('commit', {}).get('id') != sha):
            raise ValueError('new job identity mismatch')
        runner = job.get('runner')
        if runner is not None and str(runner.get('id')) != self.runner:
            raise ValueError('new job runner mismatch')
        return {'pipeline_id': str(pipeline), 'job_id': str(job['id']), 'source_sha': sha,
                'job_name': previous['job_name'], 'runner_id': self.runner}

    def _pipeline_target(self, pipeline, sha, previous, action_id):
        value = self._request('GET', f'/projects/{self.project}/pipelines/{pipeline}')
        if (str(value.get('id')) != str(pipeline) or str(value.get('project_id')) != self.project
                or value.get('sha') != sha or value.get('ref') != self.config['ref']
                or not isinstance(value.get('name'), str)
                or not value['name'].endswith(' action:' + action_id)):
            raise ValueError('new pipeline identity mismatch')
        jobs = self._job_list(pipeline)
        if len(jobs) != 1 or jobs[0].get('name') != 'ci-recovery-rehearsal':
            raise ValueError('pipeline does not contain exactly the rehearsal job')
        return self._make_target(jobs[0], pipeline, sha, previous)

    def perform(self, action, key, payload):
        self.ensure_lease()
        if action == 'repair_source':
            self._intent(action, key, payload)
            return self.source_repair(key, payload, self)
        if action == 'repair_infrastructure':
            classification = payload.get('classification', {})
            if (classification.get('kind'), classification.get('reason')) != ('infrastructure', 'missing_ci_owned_input'):
                raise ValueError('repair is not allowlisted')
            self._intent(action, key, payload)
            return self._rpc('repair', content=base64.b64encode(self.config['marker_bytes'].encode()).decode(),
                             sha256=self.config['marker_sha256'], keyhash=hashlib.sha256(key.encode()).hexdigest())
        if action not in ('retry_job', 'start_pipeline'): raise ValueError('action not allowlisted')
        self._intent(action, key, payload)
        old = payload['target']
        if action == 'retry_job':
            result = self._request('POST', f"/projects/{self.project}/jobs/{old['job_id']}/retry", body=b'{}')
            target = self._make_target(result, old['pipeline_id'], old['source_sha'], old)
            if target['job_id'] == str(old['job_id']): raise ValueError('retry returned old job')
        else:
            branch = self._request('GET', f"/projects/{self.project}/repository/branches/{quote(self.config['ref'], safe='')}")
            if branch.get('commit', {}).get('id') != payload['source_sha']:
                raise ValueError('ref does not point at repaired source')
            action_id = hashlib.sha256(key.encode()).hexdigest()
            inputs = {'recovery': '1', 'recovery_incident': self.incident,
                      'recovery_input_sha256': self.config['marker_sha256'], 'recovery_action_id': action_id}
            body = json.dumps({'ref': self.config['ref'], 'inputs': inputs}).encode()
            pipeline = self._request('POST', f'/projects/{self.project}/pipeline', body=body)
            if not isinstance(pipeline, dict) or not str(pipeline.get('id', '')).isdecimal(): raise ValueError('unknown new pipeline')
            target = self._pipeline_target(str(pipeline['id']), payload['source_sha'], old, action_id)
        path = self._action_receipt(key, {'action': action, 'target': target, 'status': 'completed'})
        return {'status': 'completed', 'target': target, 'receipt_path': path}

    def ensure_lease(self):
        if not self._lease_held: raise RuntimeError('host executor lease required')
        if time.time() >= self.config['deadline_epoch']: raise RuntimeError('deadline expired')
        if self._lease_process is not None and self._lease_process.poll() is not None:
            raise RuntimeError('host lease ended')

    def reconcile_action(self, action, key, payload):
        if not self._lease_held: raise RuntimeError('host executor lease required')
        try:
            intent = self._load_intent(action, key, payload)
        except (OSError, ValueError):
            return None
        if action == 'repair_source':
            reconcile = getattr(self.source_repair, 'reconcile', None)
            return reconcile(key, payload, self) if callable(reconcile) else None
        if action == 'repair_infrastructure':
            # Reconciliation is read-only: remote receipt must already exist.
            try:
                out = self._rpc('read_repair', keyhash=hashlib.sha256(key.encode()).hexdigest(), sha256=self.config['marker_sha256'])
                return out if out.get('status') == 'completed' else None
            except Exception:
                return None
        old = payload['target']
        candidates = []
        if action == 'retry_job':
            for job in self._job_list(old['pipeline_id']):
                if str(job.get('id')) == str(old['job_id']) or job.get('name') != old['job_name']:
                    continue
                try:
                    created = datetime.datetime.fromisoformat(job['created_at'].replace('Z', '+00:00')).timestamp()
                    target = self._make_target(job, old['pipeline_id'], old['source_sha'], old)
                    if created >= math.floor(intent['created_epoch']) - 1: candidates.append(target)
                except (KeyError, TypeError, ValueError):
                    continue
        elif action == 'start_pipeline':
            rows = self._request('GET', f'/projects/{self.project}/pipelines?' + urlencode({'ref': self.config['ref'], 'sha': payload['source_sha'], 'per_page': 100}))
            if not isinstance(rows, list) or len(rows) >= 100: return None
            action_id = hashlib.sha256(key.encode()).hexdigest()
            for pipeline in rows:
                try:
                    created = datetime.datetime.fromisoformat(pipeline['created_at'].replace('Z', '+00:00')).timestamp()
                    if created < math.floor(intent['created_epoch']) - 1 or pipeline.get('sha') != payload['source_sha'] or pipeline.get('ref') != self.config['ref']: continue
                    pid = str(pipeline['id'])
                    candidates.append(self._pipeline_target(pid, payload['source_sha'], old, action_id))
                except (KeyError, TypeError, ValueError):
                    continue
        if len(candidates) != 1:
            return None
        target = candidates[0]
        path = self._action_receipt(key, {'action': action, 'target': target, 'status': 'completed'})
        return {'status': 'completed', 'target': target, 'receipt_path': path}

    def _incident_event(self, phase, observation, receipt, reason):
        event = {'dedupe_key': self.incident, 'phase': phase, 'reason': reason, 'test': False,
                 'context': {'provider': 'gitlab', 'project': REPO, 'run_id': str(observation['pipeline_id']),
                             'job_id': str(observation['job_id']), 'commit_sha': observation['source_sha'],
                             'job_name': observation['job_name'], 'receipt_path': receipt}}
        return self._rpc('emit', event=event)

    def emit(self, phase, state):
        if phase not in ('complete', 'attention'):
            return {'stage': 'local-journal-only', 'phase': phase}
        observations, evidence = state.get('observations', []), state.get('evidence', [])
        if not observations or not evidence:
            return {'stage': 'local-journal-only', 'phase': phase}
        if phase == 'complete':
            if state.get('status') != 'complete' or observations[-1].get('status') != 'success' or evidence[-1].get('job_status') != 'success':
                raise ValueError('recovery not verified')
            return self._incident_event('recovered', observations[-1], evidence[-1]['receipt_path'], 'ci_requalified')
        # Attention must refer to the immutable first verified failed observation.
        for observation in observations:
            if observation.get('status') == 'failed':
                for item in evidence:
                    if item.get('job_status') == 'failed':
                        return self._incident_event('attention', observation, item['receipt_path'], 'ci_repair_failed')
        return {'stage': 'local-journal-only', 'phase': phase}
