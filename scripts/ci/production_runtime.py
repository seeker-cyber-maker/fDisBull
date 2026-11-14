"""Composition of the finite production CI controller and its qualified seams."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time


def _module(name):
    path=Path(__file__).with_name(name)
    spec=importlib.util.spec_from_file_location('runtime_'+name.replace('-','_').replace('.','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


production=_module('recovery_production.py')
transport_module=_module('production_transport.py')
evidence_module=_module('production_evidence.py')
github_module=_module('recovery_github.py')
gitlab_module=_module('recovery_gitlab_production.py')
host_module=_module('production_github_host.py')
policy_module=_module('production_policy.py')
health_module=_module('offline-qualification.py')
control_module=_module('production_control.py')
source_module=_module('production_source_transport.py')
gui_client_module=_module('production_gui_client.py')

REPO='seeker-cyber-maker/fDisBull'
BRIDGE='/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/production_transport.py'
RECOVERY=Path('/var/lib/fdisbull-ci/control/recovery')
LOCK=Path('/var/lib/fdisbull-ci/control/ci-executor.lock')
CLEANUP_BLOCKER=Path('/var/lib/fdisbull-ci/control/production/github-cleanup-blocked.json')
EXPORT=Path('/var/lib/fdisbull-ci/results')
ORDINARY=sorted(evidence_module.ORDINARY)
MODULES=set(_module('production_manifest.py').MODULES)


def _private(path):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts or any(x.is_symlink() for x in (path,*path.parents)):
        raise ValueError('unsafe private path')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not path.is_dir() or path.stat().st_uid!=os.geteuid() or path.stat().st_mode&0o077:
        raise ValueError('private directory unavailable')
    return path


class _GatedTransport:
    """Reuse only this process's still-current reservation; each HTTP costs budget."""
    def __init__(self,raw,guard,clock,provider):
        self.raw,self.guard,self.clock,self.provider=raw,guard,clock,provider
        self.expires=0;self.remaining=0
    def prepare(self,minimum=1):
        self.guard();now=self.clock()
        if now<self.expires and self.remaining>=minimum:
            return {'allowed':True,'reason':'active_batch','next_refresh_at':self.expires}
        if now<self.expires:
            return {'allowed':False,'reason':'cooldown','next_refresh_at':self.expires}
        result=self.raw.reserve()
        if result.get('allowed') is True:
            expiry=result.get('next_refresh_at')
            # The remote reservation starts during the round trip, rather than
            # at the caller's earlier timestamp. Validate on receipt.
            observed=self.clock()
            if type(expiry) not in (int,float) or not observed<expiry<=observed+301:raise ValueError('invalid reservation')
            self.expires=expiry;self.remaining=100
        return result
    def _use(self,amount):
        result=self.prepare(amount)
        if result.get('allowed') is not True:raise RuntimeError('provider reservation unavailable')
        self.remaining-=amount
    def request(self,method,path,payload=None):
        if method!='GET':raise ValueError('POST needs action binding')
        self._use(1);return self.raw.request(method,path,payload)
    def for_action(self,key):
        def post(method,path,payload=None):
            if method!='POST':raise ValueError('action POST required')
            self._use(2 if self.provider=='gitlab' else 1)
            return self.raw.for_action(key)(method,path,payload)
        return post
    def receipt(self,key):self.guard();return self.raw.receipt(key)


class _SourceDispatchGuard:
    def __init__(self,backend,verify):self.backend,self.verify=backend,verify
    def __getattr__(self,name):return getattr(self.backend,name)
    def perform(self,action,key,payload):
        if action=='start_pipeline':
            proof=self.verify(payload.get('candidate_ref'),payload.get('source_sha'))
            if not isinstance(proof,dict) or proof.get('verified') is not True:
                raise RuntimeError('candidate publication unavailable')
        return self.backend.perform(action,key,payload)


class Runtime:
    def __init__(self,config,state_root,lease,*,trace_capture=None,clock=time.time,
                 transport_factory=None,host_factory=None,health_capture=None,incident_runner=None,
                 lease_check=None,uid=None,sleeper=time.sleep,cleanup_runner=None,source_transport=None,gui_client_factory=None):
        self.config=dict(config);self.root=Path(state_root);self.lease=dict(lease);self.clock=clock
        self._uid=uid or os.geteuid
        if (self._uid()!=0 or self.config.get('bridge_path')!=BRIDGE
                or self.config.get('state_dir')!=str(RECOVERY/'production')
                or self.root!=Path(self.config['state_dir']) or self.config.get('export_root')!=str(EXPORT)
                or self.config.get('executor_lock')!=str(LOCK)
                or type(self.config.get('incident_test',False)) is not bool):
            raise ValueError('runtime installation pins mismatch')
        gh=self.config.get('github')
        if (not isinstance(gh,dict) or gh.get('repository')!=REPO or str(gh.get('workflow_id'))!='417757453'
                or str(gh.get('runner_id'))!='21' or gh.get('actor')!='seeker-cyber-maker'
                or gh.get('ref')!='codex/production-ci-recovery-20261113' or gh.get('profile')!='ordinary'
                or gh.get('sole_executor_authority') is not True or gh.get('export_root')!=str(EXPORT)
                or not isinstance(gh.get('control_sha'),str) or not re.fullmatch('[0-9a-f]{40}',gh['control_sha'])):
            raise ValueError('github pins invalid')
        hashes=self.config.get('module_sha256')
        if not isinstance(hashes,dict) or set(hashes)!=MODULES or any(not isinstance(x,str) or not re.fullmatch('[0-9a-f]{64}',x) for x in hashes.values()):
            raise ValueError('source manifest missing')
        self.hashes=hashes
        self._lease_check=lease_check or self._check_lease
        self._health_capture=health_capture or health_module.capture_health
        self._incident_runner=incident_runner or subprocess.run
        self._trace_capture=trace_capture;self._cleanup_unknown=False;self._cleanup_key=None;self._last_incident=None
        self._sleep=sleeper;self._cleanup_runner=cleanup_runner or transport_module._source.run_command
        self._guard(check_cleanup=False)
        gui=self.config.get('gui_transport',{'enabled':False,'state_dir':str(self.root/'gui-client')})
        if (not isinstance(gui,dict) or set(gui)!={'enabled','state_dir'} or type(gui['enabled']) is not bool
                or gui['state_dir']!=str(self.root/'gui-client')):
            raise ValueError('GUI transport configuration mismatch')
        if gui['enabled']:
            client=(gui_client_factory or gui_client_module.GuiClient)(gui['state_dir'])
            factory=transport_factory or (lambda provider:gui_client_module.GuiProviderTransport(provider,client))
            self.source=source_transport or gui_client_module.GuiSourceTransport(client)
        else:
            factory=transport_factory or (lambda provider:transport_module.SSHProviderTransport(provider,BRIDGE))
            self.source=source_transport or source_module.SSHSourceTransport()
        self.transports={p:_GatedTransport(factory(p),self._guard,clock,p) for p in ('github','gitlab')}
        self.host_factory=host_factory or host_module.GitHubHost
        self._host=None

    def _check_lease(self):
        try:
            fd=self.lease['fd'];actual=os.fstat(fd);target=LOCK.stat()
            once=_module('github-once.py')
            return (self.lease['owner_pid']==os.getpid() and actual.st_dev==self.lease['device']==target.st_dev
                    and actual.st_ino==self.lease['inode']==target.st_ino
                    and once._has_flock(Path('/proc/locks').read_text(),os.getpid(),actual.st_dev,actual.st_ino))
        except (OSError,KeyError,TypeError):return False

    def _guard(self,check_cleanup=True):
        if check_cleanup and self.cleanup_blocked():
            self._cleanup_unknown=True
            raise host_module.CleanupUnknown('unresolved worker cleanup')
        if self._lease_check() is not True:raise RuntimeError('executor lease unavailable')
        for name,digest in self.hashes.items():
            path=Path(__file__).with_name(name)
            if name=='ci_status.py' and not path.exists():path=Path(__file__).parent.parent/name
            if any(x.is_symlink() for x in (path,*path.parents)) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('runtime source identity changed')

    def _admitted(self):
        self._guard()
        return True

    def cleanup_blocked(self):
        return self._cleanup_unknown or CLEANUP_BLOCKER.exists() or CLEANUP_BLOCKER.is_symlink()

    def _after_acceptance(self,host,action,key,payload,proof):
        try:return host.after_acceptance(action,key,payload,proof)
        except host_module.CleanupUnknown:
            self._cleanup_unknown=True;self._cleanup_key=key
            raise

    def _recover_cleanup_key(self):
        if self._cleanup_key:return
        try:
            marker=control_module.read_json(CLEANUP_BLOCKER)
            host=self._github_host()
            key=marker.get('action_key')
            if isinstance(key,str) and 1<=len(key)<=500 and host._path(key,'listener-intent').is_file():
                self._cleanup_key=key;return
            labels=marker.get('labels')
            if not isinstance(labels,dict) or labels.get('fdisbull.ci.provider')!='github':return
            paths=list(host.state.glob('*.listener-intent.json'))
            if len(paths)>1024:return
            matches=[]
            for path in paths:
                item=control_module.read_json(path);candidate=item.get('action_key')
                if (isinstance(candidate,str) and 1<=len(candidate)<=500 and host._path(candidate,'listener-intent')==path
                        and item.get('run_id')==labels.get('fdisbull.ci.run_id')
                        and item.get('run_attempt')==labels.get('fdisbull.ci.run_attempt')
                        and item.get('control_sha')==labels.get('fdisbull.ci.control_sha')):
                    matches.append(candidate)
            if len(matches)==1:self._cleanup_key=matches[0]
        except (OSError,ValueError,TypeError,KeyError):return

    def _verify_cleanup(self):
        # One bounded read-only check of the exact owned listener and containers.
        try:
            host=self._github_host();key=self._cleanup_key
            if not key:return False
            intent=control_module.read_json(host._path(key,'listener-intent'))
            started=control_module.read_json(host._path(key,'listener-started'))
            if (intent.get('action_key')!=key or started.get('action_key')!=key
                    or intent.get('run_id')!=started.get('run_id') or intent.get('run_attempt')!=started.get('run_attempt')
                    or not isinstance(intent.get('source_sha'),str) or not re.fullmatch('[0-9a-f]{40}',intent['source_sha'])
                    or intent.get('control_sha')!=self.config['github']['control_sha']
                    or intent.get('nonce')!=hashlib.sha256(key.encode()).hexdigest()
                    or not all(isinstance(intent.get(k),str) and re.fullmatch(r'[1-9][0-9]*',intent[k]) for k in ('run_id','run_attempt'))
                    or type(started.get('pid')) is not int or started['pid']<=1):return False
            worker_path=host.control_root/'github-bootstrap-20261113'/intent['nonce']/'started.json'
            worker=control_module.read_json(worker_path)
            if (type(worker.get('pid')) is not int or worker['pid']<=1 or worker.get('runner_id')!=21
                    or worker.get('stage')!='listener-started'):return False
            for pid in (started['pid'],worker['pid']):
                try:os.kill(pid,0);return False
                except ProcessLookupError:pass
            try:os.killpg(worker['pid'],0);return False
            except ProcessLookupError:pass
            labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':intent['run_id'],
                    'fdisbull.ci.run_attempt':intent['run_attempt'],'fdisbull.ci.control_sha':intent['control_sha']}
            filters=[v for k,val in sorted(labels.items()) for v in ('--filter','label='+k+'='+val)]
            def docker(args):
                out=self._cleanup_runner(['docker',*args],cwd='/',timeout=20)
                if (not isinstance(out,dict) or out.get('returncode')!=0 or out.get('timed_out') is not False
                        or out.get('overflow') is not False or not isinstance(out.get('stdout'),bytes)):
                    raise ValueError('container inspection unavailable')
                return out['stdout']
            def inventory():
                ids=docker(['ps','-aq','--no-trunc',*filters]).decode('ascii').splitlines()
                if len(ids)>128 or len(set(ids))!=len(ids) or any(not re.fullmatch('[0-9a-f]{64}',v) for v in ids):
                    raise ValueError('invalid container inventory')
                return ids
            ids=inventory()
            for cid in ids:
                rows=json.loads(docker(['inspect',cid]))
                if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('Id')!=cid
                        or any((rows[0].get('Config') or {}).get('Labels',{}).get(k)!=v for k,v in labels.items())
                        or (rows[0].get('State') or {}).get('Running') is not False):return False
            return set(inventory())==set(ids)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):return False

    def hold_cleanup(self):
        # Do not release the executor while cleanup is unknown; only explicit
        # operator removal of an existing blocker plus fresh ownership evidence
        # (or verified cleanup if marker creation failed) can end the hold.
        self._cleanup_unknown=True
        self._recover_cleanup_key()
        recorded=False;notified=False;safe=self._verify_cleanup()
        while True:
            if not recorded:
                try:
                    directory=_private(self.root/'cleanup-attention')
                    key=hashlib.sha256(str(self._cleanup_key or 'unknown').encode()).hexdigest()
                    path=directory/(key+'.json')
                    value={'status':'attention','reason':'ci_executor_unavailable','action_key_sha256':key}
                    if path.exists():
                        if control_module.read_json(path)!=value:raise ValueError('cleanup attention conflict')
                    else:control_module.write_json(path,value,exclusive=True)
                    recorded=True
                except (OSError,ValueError,RuntimeError):pass
            if not notified and self._last_incident is not None:
                incident,state=self._last_incident
                try:self._emit(incident,'attention',state,attention_reason='ci_executor_unavailable');notified=True
                except Exception:pass
            if recorded and not CLEANUP_BLOCKER.exists() and not CLEANUP_BLOCKER.is_symlink() and safe:
                self._cleanup_unknown=False;return
            self._sleep(60)
            if not CLEANUP_BLOCKER.exists() and not CLEANUP_BLOCKER.is_symlink():safe=self._verify_cleanup()

    def prepare(self,manifest):
        return self.transports[manifest['initial_target']['provider']].prepare(25)

    def finish_batch(self,manifest):
        gate=self.transports[manifest['initial_target']['provider']]
        gate.remaining=0

    def health(self):
        self._guard();path=_private(self.root/'health')/('health-'+str(time.time_ns())+'.json')
        result=self._health_capture(path)
        if result.get('continue') is True:return {'state':'healthy','receipt_path':str(path)}
        state='unhealthy' if result.get('reason')=='unhealthy' else 'unknown'
        return {'state':state,'receipt_path':str(path)}

    def _trace(self,target):
        self._guard()
        tr=self.transports[target['provider']]
        if callable(self._trace_capture):return self._trace_capture(copy.deepcopy(target),tr)
        path=('/repos/'+REPO+'/actions/jobs/'+target['job_id']+'/logs' if target['provider']=='github'
              else '/projects/88349936/jobs/'+target['job_id']+'/trace')
        result=tr.request('GET',path)
        if result.get('http_status')!=200 or not isinstance(result.get('data'),dict):raise RuntimeError('private provider trace unavailable')
        return result['data']

    def _github_host(self,ledger=None):
        if self._host is None:
            state=_private(self.root/'github-host');lease=self.lease
            self._host=self.host_factory(self.config['github'],state,self.transports['github'],lease['fd'],lease['owner_pid'],
                lease['device'],lease['inode'],lease_check=lambda *args:self._admitted(),trace_capture=self._trace,
                action_started=lambda key: self._ledger.started(key),clock=self.clock)
        if ledger is not None:self._ledger=ledger
        return self._host

    def _capture_gitlab(self,observation):
        target=production.target({k:observation[k] for k in production.SCHEMAS['gitlab']})
        tr=self.transports['gitlab'];base='/projects/88349936'
        def get(path):
            r=tr.request('GET',path)
            if r.get('http_status')!=200:raise ValueError('provider metadata unavailable')
            return r['data']
        pipe=get(base+'/pipelines/'+target['pipeline_id']);job=get(base+'/jobs/'+target['job_id'])
        return {'verified':True,'target':target,'job_status':observation['status'],
                'metadata':{'pipeline':pipe,'job':job},'trace':self._trace(target)}

    def _initial_capture(self,observation):
        """Reuse only the exact already verified initial job's private capture."""
        path=self.root/'initial-result.json'
        if not path.exists() and not path.is_symlink():return None
        value=control_module.read_json(path)
        if not isinstance(value,dict) or value.get('target')!={k:observation[k] for k in production.SCHEMAS[observation['provider']]}:
            return None
        request=self.config.get('initial_request')
        if (set(value)!={'schema','request','verified','status','target','receipt_path','receipt_sha256'}
                or value['schema']!='fdisbull-initial-qualification-1' or value['verified'] is not True
                or value['request']!=request or not isinstance(request,dict)
                or set(request)!={'key','source_sha'} or not isinstance(request['key'],str) or not request['key']
                or request['source_sha']!=value['target']['source_sha']
                or value['status']!=observation['status'] or value['status'] not in ('failed','success')):
            raise ValueError('initial capture binding unavailable')
        initial=hashlib.sha256(('initial:'+request['key']).encode()).hexdigest()
        directory=self.root/'initial'/initial/'evidence'
        target=value['target'];name=hashlib.sha256(json.dumps({'target':target,'status':value['status']},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        receipt=directory/(name+'.evidence.json');metadata=directory/(name+'.provider.json');trace=directory/(name+'.trace')
        if str(receipt)!=value['receipt_path']:raise ValueError('initial capture path mismatch')
        def read_private(p,limit):
            p=evidence_module._regular(p)
            if p.stat().st_mode&0o077 or p.stat().st_uid!=os.geteuid() or p.stat().st_size>limit:
                raise ValueError('initial capture unavailable')
            return p.read_bytes()
        receipt_bytes=read_private(receipt,65536)
        if hashlib.sha256(receipt_bytes).hexdigest()!=value['receipt_sha256']:raise ValueError('initial receipt changed')
        record=json.loads(receipt_bytes);metadata_bytes=read_private(metadata,131072);trace_bytes=read_private(trace,1024*1024)
        folder=EXPORT/'github'/target['run_id']/target['run_attempt']/'qualification'/target['job_id']
        if (not isinstance(record,dict) or record.get('schema')!='fdisbull-production-evidence-1'
                or record.get('target')!=target or record.get('job_status')!=value['status']
                or record.get('export_job_sha256')!=evidence_module._digest(evidence_module._regular(folder/'job.json'))
                or record.get('inventory_sha256')!=evidence_module._digest(evidence_module._regular(folder/'inventory.json'))
                or record.get('provider_metadata_sha256')!=hashlib.sha256(metadata_bytes).hexdigest()
                or record.get('provider_trace_sha256')!=hashlib.sha256(trace_bytes).hexdigest()):
            raise ValueError('initial capture hash mismatch')
        return {'verified':True,'target':target,'job_status':value['status'],
                'metadata':json.loads(metadata_bytes),'trace':trace_bytes}

    def _evidence(self,target,private):
        profile=self._profile(target);root=EXPORT/'github' if target['provider']=='github' else EXPORT
        capture=self._github_host().capture_provider if target['provider']=='github' else self._capture_gitlab
        def capture_or_initial(observation):
            retained=self._initial_capture(observation) if observation['provider']=='github' else None
            return retained if retained is not None else capture(observation)
        return evidence_module.ProductionEvidence(root,_private(private),profile,capture_or_initial)

    @staticmethod
    def _profile(target):
        names={'test-and-package':'ordinary','qualification':'ordinary','native-debugger-stable':'stable',
               'native-debugger-layers':'layers','native-unified':'unified'}
        if target['job_name'] not in names:raise ValueError('unsupported job profile')
        return names[target['job_name']]

    def _required(self,target):
        profile=self._profile(target)
        if profile=='ordinary':return list(ORDINARY)
        # Read the captured profile receipt as a hint; ProductionEvidence verifies
        # every referenced path and its closed inventory before success.
        folder=EXPORT/target['pipeline_id']/target['job_id']/'exported'
        name,junits=evidence_module.PROFILES[profile];path=folder/'artifacts/receipts'/name
        if path.is_symlink() or not path.is_file():
            # A failed native export need not contain success artifacts. These
            # stable logical paths still prevent a future false completion.
            return ['artifacts/receipts/'+name,*junits]
        receipt=json.loads(path.read_text());artifacts=receipt.get('artifacts')
        if not isinstance(artifacts,list) or not artifacts:raise ValueError('native artifact hints missing')
        paths=[x.get('path') for x in artifacts if isinstance(x,dict)]
        if len(paths)!=len(artifacts) or any(not isinstance(p,str) or not p or p.startswith('/') or '..' in Path(p).parts for p in paths):
            raise ValueError('native artifact hint invalid')
        return list(dict.fromkeys(['artifacts/receipts/'+name,*junits,*paths]))

    def _gitlab_gate(self,target,observation):
        native=self._profile(target)!='ordinary'
        if native:
            tr=self.transports['gitlab'];base='/projects/88349936';jobs=[]
            for page in range(1,11):
                r=tr.request('GET',base+'/pipelines/'+target['pipeline_id']+'/jobs?per_page=100&page='+str(page))
                if r.get('http_status')!=200 or not isinstance(r.get('data'),list):raise ValueError('gate job list unavailable')
                rows=r['data'];jobs.extend(rows)
                if len(rows)<100:break
            else:raise ValueError('gate job list incomplete')
            found=[j for j in jobs if isinstance(j,dict) and j.get('name')=='native-qualification' and j.get('status')=='success']
            if len(found)!=1:raise ValueError('native gate not qualified')
            gate=tr.request('GET',base+'/jobs/'+str(found[0]['id']))
            job=gate.get('data') if gate.get('http_status')==200 else None
            if (not isinstance(job,dict) or job.get('name')!='native-qualification' or job.get('status')!='success'
                    or str(job.get('id'))!=str(found[0]['id'])
                    or str((job.get('pipeline') or {}).get('id'))!=target['pipeline_id']
                    or str((job.get('pipeline') or {}).get('project_id'))!=target['project_id']
                    or (job.get('commit') or {}).get('id')!=target['source_sha'] or job.get('ref')!=target['ref']):
                raise ValueError('native gate identity mismatch')
        path=_private(self.root/'gate')/(hashlib.sha256(json.dumps(target,sort_keys=True).encode()).hexdigest()+'.json')
        value={'target':target,'native':native,'manual_gate_qualified':native}
        if path.exists():
            if control_module.read_json(path)!=value:raise ValueError('gate receipt conflict')
        else:control_module.write_json(path,value,exclusive=True)
        return {'verified':True,'allowed':True,'native':native,'manual_gate_qualified':native,'receipt_path':str(path),'target':target}

    def _emit(self,incident,phase,state,*,attention_reason='ci_repair_failed'):
        if phase not in ('down','attention','complete'):return {'stage':'local-journal-only','phase':phase}
        evidence=state.get('evidence',[]);observations=state.get('observations',[])
        expected='success' if phase=='complete' else 'failed'
        if phase=='complete' and state.get('status')!='complete':raise ValueError('completion not verified')
        pairs=[(o,e) for o in observations for e in evidence if o.get('status')==expected
               and e.get('job_status')==expected and e.get('status')=='export-verified'
               and e.get('target')=={k:o.get(k) for k in production.SCHEMAS[o.get('provider')] }]
        if not pairs:return {'stage':'local-journal-only','phase':phase}
        observation,retained=pairs[-1] if phase=='complete' else pairs[0]
        receipt=Path(retained['receipt_path'])
        if (not receipt.is_absolute() or RECOVERY not in receipt.parents or not receipt.is_file()
                or any(p.is_symlink() for p in (receipt,*receipt.parents)) or receipt.stat().st_mode&0o077):
            raise ValueError('incident evidence path invalid')
        provider=observation['provider'];project=observation.get('repository','brewster-jennings-group/fdisbull')
        if attention_reason not in ('ci_repair_failed','ci_executor_unavailable'):raise ValueError('invalid attention reason')
        event={'dedupe_key':incident,'phase':'recovered' if phase=='complete' else phase,
               'reason':{'down':'ci_job_failed','attention':attention_reason,'complete':'ci_requalified'}[phase],
               'test':self.config.get('incident_test') is True,
               'context':{'provider':provider,'project':project,'run_id':str(observation.get('run_id',observation.get('pipeline_id'))),
                          'job_id':str(observation['job_id']),'commit_sha':observation['source_sha'],
                          'job_name':observation['job_name'],'receipt_path':str(receipt)}}
        self._guard(check_cleanup=attention_reason!='ci_executor_unavailable')
        if phase=='down':self._last_incident=(incident,copy.deepcopy(state))
        result=self._incident_runner(['sudo','-n','-u','operations-alerts','/usr/bin/python3',
                         '/usr/local/libexec/ci_incident.py','append'],input=json.dumps(event).encode(),
                         capture_output=True,timeout=30,check=False)
        if result.returncode!=0:raise RuntimeError('incident journal unavailable')
        return {'stage':'journaled','phase':event['phase']}

    def _source_bundle(self,target,evidence):
        if (evidence.get('status')!='export-verified' or evidence.get('job_status')!='failed'
                or evidence.get('target')!=target or any(evidence.get(k) is not True for k in
                    ('host_export_verified','closed_inventory_verified','source_postcheck_verified','provider_trace_verified'))):
            raise ValueError('source export unverified')
        receipt=Path(evidence.get('receipt_path',''))
        if RECOVERY not in receipt.parents or receipt.stat().st_mode&0o077:raise ValueError('source receipt outside private state')
        def read(path,maximum):
            path=evidence_module._regular(path)
            if path.stat().st_size<1 or path.stat().st_size>maximum:raise ValueError('source evidence exceeds bound')
            return path.read_bytes()
        rb=read(receipt,65536);record=json.loads(rb)
        if record.get('schema')!='fdisbull-production-evidence-1' or record.get('target')!=target or record.get('job_status')!='failed':
            raise ValueError('source receipt identity mismatch')
        folder=(EXPORT/'github'/target['run_id']/target['run_attempt']/'qualification'/target['job_id']
                if target['provider']=='github' else EXPORT/target['pipeline_id']/target['job_id'])
        job=read(folder/'job.json',65536);inventory=read(folder/'inventory.json',source_module.MAX_INVENTORY)
        junit=read(folder/'exported'/source_module.JUNIT,source_module.MAX_JUNIT)
        digest=lambda data:hashlib.sha256(data).hexdigest()
        if digest(job)!=record.get('export_job_sha256') or digest(inventory)!=record.get('inventory_sha256'):
            raise ValueError('source closed export changed')
        rows=json.loads(inventory)
        found=[x for x in rows if isinstance(x,dict) and x.get('path')==source_module.JUNIT] if isinstance(rows,list) else []
        if len(found)!=1 or found[0].get('size')!=len(junit) or found[0].get('sha256')!=digest(junit):
            raise ValueError('source JUnit missing or changed')
        enc=lambda data:base64.b64encode(data).decode('ascii')
        bundle={'target':target,'evidence_receipt_path':str(receipt),'evidence_receipt_sha256':digest(rb),
                'evidence_receipt_base64':enc(rb),'job_base64':enc(job),'inventory_base64':enc(inventory),
                'junit_path':source_module.JUNIT,'junit_base64':enc(junit)}
        event=digest(json.dumps({'target':target,'receipt_sha256':digest(rb),'junit_sha256':digest(junit)},
                                 sort_keys=True,separators=(',',':')).encode())
        return bundle,event

    def _classify(self,observation,evidence,incidentdir,deadline):
        decision=policy_module.classify(observation,evidence)
        if decision.get('kind')!='blocked':return decision
        target=production.target({k:observation[k] for k in production.SCHEMAS[observation['provider']]})
        if ((target['provider'],target['job_name']) not in (('github','qualification'),('gitlab','test-and-package'))
                or self.clock()+600>deadline):return decision
        try:
            state_path=incidentdir/'state.json'
            if state_path.exists() and control_module.read_json(state_path).get('counts',{}).get('source',0)>=1:return decision
            bundle,event=self._source_bundle(target,evidence)
            fingerprint=hashlib.sha256((target['source_sha']+hashlib.sha256(base64.b64decode(bundle['junit_base64'])).hexdigest()).encode()).hexdigest()
            if state_path.exists() and any(c.get('fingerprint')==fingerprint for c in control_module.read_json(state_path).get('classifications',[])):
                return decision
            if self.health().get('state')!='healthy':return decision
            intent=incidentdir/('source-prepare-'+event+'.json')
            record={'target':target,'event_key':event,'receipt_sha256':bundle['evidence_receipt_sha256']}
            self._guard()
            if intent.exists():
                if control_module.read_json(intent)!=record:raise ValueError('source preparation intent conflict')
                prepared=self.source.reconcile_prepare(target,bundle)
            else:
                control_module.write_json(intent,record,exclusive=True)
                prepared=self.source.prepare(target,bundle)
            self._guard()
            if (self.clock()+600>deadline or not isinstance(prepared,dict) or prepared.get('schema')!='fdisbull-source-reproducer-1'
                    or prepared.get('status')!='verified_reproducer' or prepared.get('event_key')!=event
                    or prepared.get('target')!=target or prepared.get('baseline')!='failed'
                    or prepared.get('selection_profile')!='single-failure-direct-imports-1'
                    or prepared.get('linux_parity') is not False or prepared.get('requires_linux_requalification') is not True
                    or not isinstance(prepared.get('receipt_path'),str) or not prepared['receipt_path']):return decision
            return {'verified':True,'eligible_for_repair':True,'kind':'source','reason':'verified_source_reproducer',
                    'fingerprint':fingerprint,'source_prepare':{'event_key':event},
                    'reproducer':{'verified':True,'source_sha':target['source_sha'],'baseline':'failed','receipt_path':prepared['receipt_path']}}
        except host_module.CleanupUnknown:raise
        except Exception:return decision

    def _source_action(self,key,payload,incidentdir,deadline,reconcile=False):
        self._guard()
        if not reconcile and self.clock()+600>deadline:raise RuntimeError('source worker deadline insufficient')
        target=production.target(payload['target']);classification=payload.get('classification',{})
        prepare=classification.get('source_prepare')
        if not isinstance(prepare,dict) or set(prepare)!={'event_key'} or not re.fullmatch('[0-9a-f]{64}',str(prepare.get('event_key',''))):
            raise ValueError('verified source preparation missing')
        minimal={'target':target,'source_prepare':prepare}
        result=self.source.reconcile(key,minimal) if reconcile else self.source.repair(key,minimal)
        self._guard()
        if result is None and reconcile:return None
        if not self._valid_publication(result,target,prepare['event_key']):raise RuntimeError('dual-provider candidate unverified')
        record={'key':key,'payload':minimal,'result':result}
        path=incidentdir/('source-publication-'+hashlib.sha256(key.encode()).hexdigest()+'.json')
        if path.exists():
            if control_module.read_json(path)!=record:raise ValueError('publication receipt conflict')
        else:control_module.write_json(path,record,exclusive=True)
        if reconcile:
            result={**result,'origin_proof':{'verified':True,'kind':'durable-accepted-action','action_key':key,'receipt_path':str(path)}}
        return result

    @staticmethod
    def _valid_publication(value,target,event):
        if not isinstance(value,dict) or value.get('status')!='completed' or value.get('base_sha')!=target['source_sha']:
            return False
        sha=value.get('source_sha');ref=value.get('candidate_ref');pub=value.get('publication')
        return (isinstance(sha,str) and re.fullmatch('[0-9a-f]{40}',sha) is not None and sha!=target['source_sha']
                and ref=='codex/ci-repair-'+event and isinstance(value.get('receipt_path'),str) and bool(value['receipt_path'])
                and isinstance(pub,dict) and pub.get('verified') is True and pub.get('source_sha')==sha
                and pub.get('candidate_ref')==ref and isinstance(pub.get('receipt_path'),str) and bool(pub['receipt_path'])
                and all(isinstance(pub.get(p),dict) and pub[p].get('verified') is True
                    and pub[p].get('source_sha')==sha and pub[p].get('candidate_ref')==ref for p in ('github','gitlab')))

    def _candidate_readback(self,ref,sha,incidentdir,deadline):
        self._guard()
        if self.clock()+600>deadline:raise RuntimeError('candidate readback deadline insufficient')
        records=[]
        paths=list(incidentdir.glob('source-publication-*.json'))
        if len(paths)>4:raise ValueError('candidate publication inventory exceeds bound')
        for path in paths:
            record=control_module.read_json(path)
            if record.get('result',{}).get('source_sha')==sha and record.get('result',{}).get('candidate_ref')==ref:records.append(record)
        if len(records)!=1:raise ValueError('candidate publication receipt unavailable')
        record=records[0];payload=record['payload'];value=self.source.reconcile(record['key'],payload)
        self._guard()
        if self.clock()>=deadline:raise RuntimeError('candidate readback exceeded deadline')
        if not self._valid_publication(value,payload['target'],payload['source_prepare']['event_key']) or value['source_sha']!=sha or value['candidate_ref']!=ref:
            raise ValueError('candidate provider readback unavailable')
        return {'verified':True,'ref':ref,'source_sha':sha,'receipt_path':value['publication']['receipt_path']}

    def backend(self,manifest,incidentdir):
        self._guard();target=production.target(manifest['initial_target']);incident=manifest['incident_id']
        if not isinstance(incident,str) or not re.fullmatch('[0-9a-f]{64}',incident):raise ValueError('incident identity invalid')
        if Path(incidentdir) not in (self.root/'incidents'/incident,self.root/'initial'/incident):
            raise ValueError('incident directory mismatch')
        incidentdir=_private(incidentdir)
        ledger=control_module.ActionLedger(_private(incidentdir/'actions'))
        repair=policy_module.KnownInputRepair(incidentdir,ensure_lease=self._admitted)
        required=manifest['required_artifacts']
        retain=self._evidence(target,incidentdir/'evidence')
        deadline=manifest['deadline_epoch']
        def reconcile(action,key,payload):
            if action=='repair_source':return self._source_action(key,payload,incidentdir,deadline,reconcile=True)
            if action!='repair_infrastructure':return None
            value=repair.reconcile(key,payload)
            if value is None:return None
            return {**value,'origin_proof':{'verified':True,'kind':'durable-accepted-action',
                       'action_key':key,'receipt_path':value['receipt_path']}}
        common=dict(retain=retain,classify=lambda obs,ev:self._classify(obs,ev,incidentdir,deadline),health=self.health,
                    emit=lambda phase,state:self._emit(incident,phase,state),claim_action=ledger.claim,
                    save_acceptance=ledger.save_acceptance,load_acceptance=ledger.load_acceptance,
                    repair_infrastructure=repair.repair,repair_source=lambda key,payload:self._source_action(key,payload,incidentdir,deadline),reconcile_other=reconcile,
                    lease=self._admitted,required_artifacts=required)
        if target['provider']=='github':
            host=self._github_host(ledger)
            backend=github_module.GitHubRecoveryBackend(repository=REPO,control_sha=self.config['github']['control_sha'],
                transport=self.transports['github'],source_binding=host.source_binding,resolve_dispatch=host.resolve_dispatch,
                after_acceptance=lambda action,key,payload,proof:self._after_acceptance(host,action,key,payload,proof),workflow_id=417757453,
                load_intent=ledger.load_intent,sole_executor_authority=self.config['github']['sole_executor_authority'],
                actor=self.config['github']['actor'],**common)
            return _SourceDispatchGuard(backend,lambda ref,sha:self._candidate_readback(ref,sha,incidentdir,deadline))
        if target['provider']=='gitlab':
            return gitlab_module.GitLabRecoveryBackend(transport=self.transports['gitlab'],
                candidate_readback=lambda ref,sha:self._candidate_readback(ref,sha,incidentdir,deadline),
                dispatch_policy=lambda t,p: {'verified':True,'allowed':self._profile(t)=='ordinary','native':self._profile(t)!='ordinary',
                    'receipt_path':self._candidate_readback(p['candidate_ref'],p['source_sha'],incidentdir,deadline)['receipt_path'],
                    'target':t,'candidate_ref':p['candidate_ref'],'source_sha':p['source_sha']},retry_policy=self._gitlab_gate,provider_stop=lambda code:None,**common)
        raise ValueError('unsupported provider')

    def resolve_candidate(self,hint):
        self._guard()
        if not isinstance(hint,dict) or hint.get('verification')!='unverified_hint':raise ValueError('invalid intake hint')
        provider=hint.get('provider');source=hint.get('source_sha');name=hint.get('job_name')
        if provider=='github':
            target={'provider':'github','repository':REPO,'run_id':hint['run_id'],'run_attempt':hint['attempt'],
                    'job_id':hint['job_id'],'source_sha':source,'job_name':name,'runner_id':'21',
                    'ref':self.config['github']['ref'],'control_sha':self.config['github']['control_sha']}
        elif provider=='gitlab':
            tr=self.transports['gitlab'];base='/projects/88349936'
            res=tr.request('GET',base+'/jobs/'+hint['job_id'])
            job=res.get('data') if res.get('http_status')==200 else None
            if not isinstance(job,dict) or not isinstance(job.get('ref'),str):raise ValueError('canonical target unavailable')
            target={'provider':'gitlab','project_id':'88349936','pipeline_id':hint['run_id'],'job_id':hint['job_id'],
                    'source_sha':source,'job_name':name,'runner_id':'58990209','ref':job['ref']}
        else:raise ValueError('provider unsupported')
        target=production.target(target);required=self._required(target)
        # Construct the actual adapter for canonical observation. Producer hints
        # do not establish a failure or source binding.
        key=hint['event_key']
        if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('invalid event identity')
        directory=_private(self.root/'incidents'/key)
        manifest={'incident_id':key,'initial_target':target,'required_artifacts':required,
                  'deadline_epoch':self.clock()+self.config['max_incident_seconds']}
        observed=self.backend(manifest,directory).observe(target)
        if observed.get('status')!='failed':raise ValueError('canonical failure unavailable')
        return target,required

    def initial_dispatch(self,request):
        self._guard()
        if not isinstance(request,dict) or set(request)!={'key','source_sha'}:raise ValueError('invalid initial request')
        key,sha=request['key'],request['source_sha']
        if self.health().get('state')!='healthy':raise RuntimeError('initial health unavailable')
        host=self._github_host()
        try:
            if host._path(key,'dispatch-intent').exists():result=host.reconcile_initial(key,sha)
            else:result=host.initial_dispatch(key,sha)
        except host_module.CleanupUnknown:
            self._cleanup_unknown=True;self._cleanup_key=key
            raise
        if result is None or isinstance(result,dict) and result.get('status')=='running':
            nonce=hashlib.sha256(key.encode()).hexdigest()
            path='/repos/'+REPO+'/actions/workflows/417757453/dispatches'
            body={'ref':self.config['github']['ref'],'inputs':{'nonce':nonce,'candidate_sha':sha}}
            accepted=host._accept(key,path,body,204)
            if not isinstance(accepted,str) or not accepted:raise RuntimeError('initial dispatch acceptance unknown')
            return {'status':'pending','verified':True,'receipt_path':accepted}
        if not isinstance(result,dict) or result.get('status') not in ('success','failed'):raise RuntimeError('initial provider target unknown')
        target=production.target(result['target']);incident=hashlib.sha256(('initial:'+key).encode()).hexdigest()
        directory=_private(self.root/'initial'/incident)
        manifest={'incident_id':incident,'initial_target':target,'required_artifacts':list(ORDINARY),
                  'deadline_epoch':self.clock()+self.config['max_incident_seconds']}
        backend=self.backend(manifest,directory);observation=backend.observe(target)
        if observation['status']!=result['status']:raise ValueError('initial provider outcome mismatch')
        evidence=backend.retain(observation)
        if observation['status']=='success' and (evidence.get('required_artifacts_verified') is not True
                or set(evidence.get('verified_artifacts',[]))!=set(ORDINARY)):
            raise ValueError('initial success artifacts unverified')
        return {'verified':True,'status':observation['status'],'target':target,'receipt_path':evidence['receipt_path']}
