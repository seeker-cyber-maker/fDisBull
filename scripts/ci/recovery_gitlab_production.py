"""Finite GitLab production-job adapter; all provider and host I/O is injected."""
import copy
import importlib.util
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location('recovery_production', Path(__file__).with_name('recovery_production.py'))
_production = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_production)
_transport_spec = importlib.util.spec_from_file_location('production_transport', Path(__file__).with_name('production_transport.py'))
_transport = importlib.util.module_from_spec(_transport_spec)
_transport_spec.loader.exec_module(_transport)


def _accepted_envelope(envelope):
    if (not isinstance(envelope,dict) or set(envelope) != {'http_status','data','request_id'}
            or envelope['http_status'] != 201 or not isinstance(envelope['data'],dict)
            or set(envelope['data']) != {'id'}):
        return False
    identity=envelope['data']['id']
    rid=envelope['request_id']
    return (not isinstance(identity,bool) and str(identity or '').isascii() and str(identity or '').isdecimal()
            and int(identity)>0 and (rid is None or isinstance(rid,str)
                and re.fullmatch(r'[A-Za-z0-9:._-]{1,128}',rid) is not None))


class GitLabRecoveryBackend:
    def __init__(self, *, transport, retain, classify, health, emit, claim_action, save_acceptance,
                 load_acceptance, repair_infrastructure, repair_source, reconcile_other, lease,
                 required_artifacts, candidate_readback, dispatch_policy, retry_policy, provider_stop,
                 project_id='88349936', runner_id='58990209'):
        if str(project_id) != '88349936' or str(runner_id) != '58990209':
            raise ValueError('project or runner not pinned')
        if (not isinstance(required_artifacts,(tuple,list)) or not required_artifacts
                or any(not isinstance(x,str) or not x for x in required_artifacts)
                or len(set(required_artifacts)) != len(required_artifacts)):
            raise ValueError('required artifacts missing')
        self.project_id, self.runner_id = str(project_id), str(runner_id)
        self.transport, self.retain_callback, self.classify_callback = transport, retain, classify
        self.health_callback, self.emit_callback = health, emit
        self.claim_action, self.save_acceptance, self.load_acceptance = claim_action, save_acceptance, load_acceptance
        self.repairs={'repair_infrastructure':repair_infrastructure,'repair_source':repair_source}
        self.reconcile_other, self.lease = reconcile_other, lease
        self.candidate_readback, self.dispatch_policy, self.retry_policy, self.provider_stop = candidate_readback, dispatch_policy, retry_policy, provider_stop
        self.required_artifacts=frozenset(required_artifacts)
        self.base='/projects/'+self.project_id
        self.observed={}

    def _target(self,value):
        target=_production.target(value)
        if target['provider'] != 'gitlab' or target['project_id'] != self.project_id or target['runner_id'] != self.runner_id:
            raise ValueError('GitLab target authority mismatch')
        return target

    def _request(self,method,path,payload=None,expected=200,action_key=None):
        if method == 'POST':
            if not isinstance(action_key,str) or not action_key: raise ValueError('action key required')
            result=self.transport.for_action(action_key)(method,path,payload)
        else:
            result=self.transport.request(method,path,payload)
        if not isinstance(result,dict) or set(result) != {'http_status','data','request_id'}:
            raise RuntimeError('provider response unknown')
        code=result['http_status']
        if code in (401,403,429):
            self.provider_stop(code)
            raise RuntimeError('provider restricted')
        if code != expected:
            raise RuntimeError('provider response unavailable')
        rid=result['request_id']
        if rid is not None and (not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9:._-]{1,128}',rid)):
            raise RuntimeError('invalid request id')
        return result

    def _read_job(self,target,allow_unassigned=False):
        pipeline=self._request('GET',self.base+'/pipelines/'+target['pipeline_id'])['data']
        job=self._request('GET',self.base+'/jobs/'+target['job_id'])['data']
        if (not isinstance(pipeline,dict) or str(pipeline.get('id')) != target['pipeline_id']
                or str(pipeline.get('project_id')) != self.project_id or pipeline.get('sha') != target['source_sha']
                or pipeline.get('ref') != target['ref'] or not isinstance(job,dict)
                or str(job.get('id')) != target['job_id'] or job.get('name') != target['job_name']
                or job.get('commit',{}).get('id') != target['source_sha'] or job.get('ref') != target['ref']
                or not isinstance(job.get('pipeline'),dict)
                or str(job['pipeline'].get('id')) != target['pipeline_id']
                or str(job['pipeline'].get('project_id')) != self.project_id
                or job['pipeline'].get('sha') != target['source_sha']
                or job['pipeline'].get('ref') != target['ref']):
            raise ValueError('canonical pipeline or job identity mismatch')
        runner=job.get('runner')
        if runner is None and allow_unassigned and job.get('status') in ('created','pending','preparing','waiting_for_resource'):
            return job,False
        if not isinstance(runner,dict) or str(runner.get('id')) != self.runner_id:
            raise ValueError('runner not verified')
        return job,True

    def observe(self,target):
        target=self._target(target)
        job,_=self._read_job(target)
        raw=job.get('status')
        if raw in ('created','pending','preparing','waiting_for_resource','running'): status='running'
        else: status={'success':'success','failed':'failed','canceled':'canceled'}.get(raw,'unknown')
        observation={**target,'status':status,'provider_status':raw,'failure_reason':job.get('failure_reason')}
        self.observed[(target['pipeline_id'],target['job_id'])]=copy.deepcopy(observation)
        return observation

    def retain(self,observation):
        target=self._target({k:observation[k] for k in _production.SCHEMAS['gitlab']})
        if self.observed.get((target['pipeline_id'],target['job_id'])) != observation:
            raise ValueError('unverified observation')
        evidence=self.retain_callback(copy.deepcopy(observation),sorted(self.required_artifacts))
        if (not isinstance(evidence,dict) or evidence.get('status') != 'export-verified'
                or evidence.get('job_status') != observation['status'] or evidence.get('target') != target
                or not isinstance(evidence.get('receipt_path'),str) or not evidence['receipt_path']
                or any(evidence.get(k) is not True for k in ('host_export_verified','closed_inventory_verified',
                                                            'source_postcheck_verified','provider_trace_verified'))):
            raise ValueError('closed job export unavailable')
        if observation['status'] == 'success' and (evidence.get('required_artifacts_verified') is not True
                or not isinstance(evidence.get('required_artifacts_receipt'),str) or not evidence['required_artifacts_receipt']
                or not isinstance(evidence.get('verified_artifacts'),list)
                or len(evidence['verified_artifacts']) != len(self.required_artifacts)
                or any(not isinstance(x,str) for x in evidence['verified_artifacts'])
                or set(evidence['verified_artifacts']) != self.required_artifacts):
            raise ValueError('required artifacts unavailable')
        return evidence

    def classify(self,observation,evidence):
        result=self.classify_callback(copy.deepcopy(observation),copy.deepcopy(evidence))
        if (not isinstance(result,dict) or result.get('verified') is not True
                or result.get('kind') not in ('infrastructure','source','blocked')
                or not isinstance(result.get('reason'),str) or not result['reason']
                or not isinstance(result.get('fingerprint'),str) or not result['fingerprint']
                or result.get('kind') != 'blocked' and result.get('eligible_for_repair') is not True):
            return {'kind':'blocked','reason':'classification_unverified','fingerprint':'classification_unverified'}
        if result['kind']=='source' and not _production.reproducer_proof(result,observation['source_sha']):
            return {'kind':'blocked','reason':'reproducer_unverified','fingerprint':'reproducer_unverified'}
        return result

    def health(self): return self.health_callback()
    def emit(self,phase,state): return self.emit_callback(phase,copy.deepcopy(state))

    def _request_spec(self,action,payload,old):
        if action=='retry_job': return self.base+'/jobs/'+old['job_id']+'/retry',{}
        sha,ref=payload.get('source_sha'),payload.get('candidate_ref')
        if (not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha) or sha==old['source_sha']
                or not _production.valid_ref(ref)): raise ValueError('invalid candidate identity')
        return self.base+'/pipeline',{'ref':ref}

    def perform(self,action,key,payload):
        if self.lease() is not True: raise RuntimeError('executor lease unavailable')
        if action in self.repairs: return self.repairs[action](key,copy.deepcopy(payload))
        if action not in ('retry_job','start_pipeline'): raise ValueError('unsupported action')
        old=self._target(payload['target'])
        path,body=self._request_spec(action,payload,old)
        if action=='retry_job':
            observation=self.observe(old)
            policy=self.retry_policy(copy.deepcopy(old),copy.deepcopy(observation))
            if (observation['status'] != 'failed' or not isinstance(policy,dict)
                    or policy.get('verified') is not True or policy.get('allowed') is not True
                    or policy.get('target') != old or type(policy.get('native')) is not bool
                    or policy['native'] and policy.get('manual_gate_qualified') is not True
                    or not isinstance(policy.get('receipt_path'),str) or not policy['receipt_path']):
                raise ValueError('retry origin or native gate unverified')
        else:
            readback=self.candidate_readback(payload['candidate_ref'],payload['source_sha'])
            policy=self.dispatch_policy(copy.deepcopy(old),copy.deepcopy(payload))
            if (not isinstance(readback,dict) or readback.get('verified') is not True
                    or readback.get('ref') != payload['candidate_ref'] or readback.get('source_sha') != payload['source_sha']
                    or not isinstance(readback.get('receipt_path'),str) or not readback['receipt_path']
                    or not isinstance(policy,dict) or policy.get('verified') is not True
                    or policy.get('allowed') is not True or policy.get('native') is not False
                    or policy.get('target') != old or policy.get('candidate_ref') != payload['candidate_ref']
                    or policy.get('source_sha') != payload['source_sha']
                    or not isinstance(policy.get('receipt_path'),str) or not policy['receipt_path']):
                raise ValueError('source dispatch or native manual gate unverified')
        claim=self.claim_action(action,key,copy.deepcopy(payload))
        if not isinstance(claim,dict) or claim.get('durable') is not True or claim.get('new') is not True:
            raise RuntimeError('action already claimed or intent unavailable')
        response=self._request('POST',path,body,201,action_key=key)
        if not _accepted_envelope(response): raise RuntimeError('accepted identity unknown')
        data=response['data']
        if str(data['id']) == (old['job_id'] if action=='retry_job' else old['pipeline_id']):
            raise RuntimeError('accepted identity reused')
        proof={'action':action,'target':old,'request':{'method':'POST','path':path,'payload':body},'envelope':response}
        receipt=self.save_acceptance(key,copy.deepcopy(proof))
        if not isinstance(receipt,str) or not receipt: raise RuntimeError('acceptance not durable')
        result=self.reconcile_action(action,key,payload)
        if result is None: raise RuntimeError('accepted action linkage unavailable')
        return result

    def _pipeline_jobs(self,pipeline_id):
        found=[]
        for page in range(1,11):
            rows=self._request('GET',self.base+'/pipelines/'+pipeline_id+'/jobs?per_page=100&page='+str(page))['data']
            if not isinstance(rows,list) or len(rows)>100: raise ValueError('invalid job listing')
            found.extend(rows)
            if len(rows)<100: return found
        raise ValueError('job listing exceeds bound')

    def reconcile_action(self,action,key,payload):
        if self.lease() is not True: return None
        if action not in ('retry_job','start_pipeline'): return self.reconcile_other(action,key,copy.deepcopy(payload))
        old=self._target(payload['target']);path,body=self._request_spec(action,payload,old)
        saved=self.load_acceptance(key)
        if saved is None:
            # Only the bridge's durable acceptance can repair a lost local save.
            # An unknown receipt or mismatched digest is never evidence of a POST.
            bridge=self.transport.receipt(key)
            if not isinstance(bridge,dict) or set(bridge) != {'receipt'}:
                return None
            receipt=bridge['receipt']
            if (not isinstance(receipt,dict) or set(receipt) != {'action_key','request_sha256','status','envelope'}
                    or receipt['action_key'] != key or receipt['status'] != 'accepted'
                    or receipt['request_sha256'] != _transport.request_digest('gitlab','POST',path,body)
                    or not _accepted_envelope(receipt['envelope'])):
                return None
            proof={'action':action,'target':old,'request':{'method':'POST','path':path,'payload':body},
                   'envelope':copy.deepcopy(receipt['envelope'])}
            local_path=self.save_acceptance(key,copy.deepcopy(proof))
            if not isinstance(local_path,str) or not local_path:
                return None
            saved={'proof':proof,'receipt_path':local_path}
        if not isinstance(saved,dict) or set(saved)!={'proof','receipt_path'} or not isinstance(saved['receipt_path'],str) or not saved['receipt_path']: return None
        proof=saved['proof']
        if (not isinstance(proof,dict) or set(proof)!={'action','target','request','envelope'}
                or proof['action'] != action or proof['target'] != old
                or proof['request'] != {'method':'POST','path':path,'payload':body}): return None
        env=proof['envelope']
        if not _accepted_envelope(env): return None
        identity=env['data'].get('id')
        if isinstance(identity,bool) or not str(identity or '').isascii() or not str(identity or '').isdecimal() or int(identity)<=0: return None
        identity=str(int(identity))
        origin={'verified':True,'kind':'durable-accepted-action','action_key':key,'receipt_path':saved['receipt_path']}
        pending={'status':'pending','receipt_path':saved['receipt_path'],'origin_proof':origin}
        new=dict(old)
        if action=='retry_job':
            if identity == old['job_id']: return None
            new['job_id']=identity
        else:
            if identity == old['pipeline_id']: return None
            new.update(pipeline_id=identity,source_sha=payload['source_sha'],ref=payload['candidate_ref'])
            pipeline=self._request('GET',self.base+'/pipelines/'+identity)['data']
            if (not isinstance(pipeline,dict) or str(pipeline.get('id'))!=identity or str(pipeline.get('project_id'))!=self.project_id
                    or pipeline.get('sha')!=new['source_sha'] or pipeline.get('ref')!=new['ref']): return None
            matches=[j for j in self._pipeline_jobs(identity) if isinstance(j,dict) and j.get('name')==old['job_name']]
            if not matches and pipeline.get('status') in ('created','pending','preparing','running'): return pending
            if len(matches)!=1: return None
            jid=matches[0].get('id')
            if isinstance(jid,bool) or not str(jid or '').isascii() or not str(jid or '').isdecimal() or int(jid)<=0 or str(jid)==old['job_id']: return None
            new['job_id']=str(int(jid))
        _,assigned=self._read_job(new,allow_unassigned=True)
        if not assigned: return pending
        self.observe(new)
        result={'status':'completed','target':new,'receipt_path':saved['receipt_path'],'origin_proof':origin}
        if action=='start_pipeline': result['candidate_ref']=payload['candidate_ref']
        return result
