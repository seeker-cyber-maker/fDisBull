"""Provider-specific identities and proof contracts for finite CI recovery.

Adapters must verify provider evidence before returning these compact receipts.
This module does not observe, dispatch, poll, or establish provider authority.
"""
import re

SCHEMAS = {
    'gitlab': ('provider','project_id','pipeline_id','job_id','source_sha','job_name','runner_id','ref'),
    'github': ('provider','repository','run_id','run_attempt','job_id','source_sha','job_name','runner_id','ref','control_sha'),
    'ovh-local': ('provider','run_id','attempt','source_sha','job_name','host_id','container_id'),
}
NUMERIC = {'project_id','pipeline_id','job_id','runner_id','run_attempt','attempt'}


def target(value):
    if not isinstance(value, dict) or value.get('provider') not in SCHEMAS:
        raise ValueError('unknown production provider')
    provider=value['provider']; keys=SCHEMAS[provider]
    if set(value) != set(keys): raise ValueError('invalid production target fields')
    result=dict(value)
    numeric = NUMERIC.intersection(keys) | ({'run_id'} if provider == 'github' else set())
    for key in numeric:
        v=value[key]
        if isinstance(v,bool) or not isinstance(v,(int,str)) or not str(v).isascii() or not str(v).isdecimal() or int(v)<=0:
            raise ValueError('invalid production numeric identity')
        result[key]=str(int(v))
    if not isinstance(value['source_sha'],str) or not re.fullmatch('[0-9a-f]{40}',value['source_sha']):
        raise ValueError('invalid production source sha')
    if (not isinstance(value['job_name'],str) or not value['job_name'] or len(value['job_name'])>200
            or any(ord(c)<32 or ord(c)==127 for c in value['job_name'])):
        raise ValueError('invalid production job name')
    if provider=='github' and (not isinstance(value['repository'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value['repository'])):
        raise ValueError('invalid GitHub repository')
    if provider in ('gitlab','github') and not valid_ref(value.get('ref')):
        raise ValueError('invalid hosted ref')
    if provider == 'github' and (not isinstance(value['control_sha'],str) or not re.fullmatch('[0-9a-f]{40}',value['control_sha'])):
        raise ValueError('invalid GitHub control sha')
    if provider=='ovh-local':
        if (not isinstance(value['run_id'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value['run_id'])
                or not isinstance(value['host_id'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value['host_id'])
                or not isinstance(value['container_id'],str) or not re.fullmatch('[0-9a-f]{64}',value['container_id'])):
            raise ValueError('invalid local execution identity')
    return result


def valid_ref(value):
    return (isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_./-]{1,200}',value))
            and '..' not in value and not value.startswith(('/', '-')) and not value.endswith(('/', '.')))


def transition(old, new, action, candidate_sha=None, candidate_ref=None):
    old, new=target(old), target(new)
    if new['provider'] != old['provider'] or new['job_name'] != old['job_name']:
        raise ValueError('provider or job changed')
    provider=old['provider']
    for key in ({'gitlab':('project_id','runner_id'), 'github':('repository','runner_id'), 'ovh-local':('host_id',)}[provider]):
        if new[key] != old[key]: raise ValueError('execution authority changed')
    if provider == 'github' and (new['ref'] != old['ref'] or new['control_sha'] != old['control_sha']):
        raise ValueError('GitHub control identity changed')
    if action=='retry_job':
        if new['source_sha'] != old['source_sha']: raise ValueError('retry source changed')
        if provider=='gitlab' and new['ref'] != old['ref']: raise ValueError('retry ref changed')
        if provider=='gitlab' and (new['pipeline_id'] != old['pipeline_id'] or new['job_id'] == old['job_id']): raise ValueError('invalid GitLab retry')
        if provider=='github' and (new['run_id'] != old['run_id'] or int(new['run_attempt']) != int(old['run_attempt'])+1 or new['job_id'] == old['job_id']): raise ValueError('invalid GitHub retry')
        if provider=='ovh-local' and (new['run_id'] != old['run_id'] or int(new['attempt']) != int(old['attempt'])+1 or new['container_id'] == old['container_id']): raise ValueError('invalid local retry')
    elif action=='start_pipeline':
        if not candidate_sha or new['source_sha'] != candidate_sha or candidate_sha == old['source_sha']:
            raise ValueError('new source identity invalid')
        if provider in ('gitlab','github') and not valid_ref(candidate_ref): raise ValueError('candidate ref missing')
        if provider == 'gitlab' and new['ref'] != candidate_ref: raise ValueError('candidate ref mismatch')
        if provider=='gitlab' and (new['pipeline_id'] == old['pipeline_id'] or new['job_id'] == old['job_id']): raise ValueError('new GitLab pipeline required')
        if provider=='github' and (new['run_id'] == old['run_id'] or new['job_id'] == old['job_id'] or new['run_attempt'] != '1'): raise ValueError('new GitHub run required')
        if provider=='ovh-local' and (new['run_id'] == old['run_id'] or new['container_id'] == old['container_id'] or new['attempt'] != '1'): raise ValueError('new local run required')
    else: raise ValueError('invalid transition action')
    return new


def origin_proof(result, action_key):
    proof=result.get('origin_proof') if isinstance(result,dict) else None
    return (isinstance(proof,dict) and proof.get('verified') is True
            and proof.get('kind') in ('durable-accepted-action','canonical-origin')
            and proof.get('action_key') == action_key
            and isinstance(proof.get('receipt_path'),str) and bool(proof['receipt_path']))


def candidate_checkout_proof(evidence, target_value):
    proof = evidence.get('candidate_checkout')
    if not isinstance(proof, dict) or proof.get('verified') is not True:
        return False
    return (all(proof.get(k) == target_value[k] for k in
                ('source_sha', 'control_sha', 'run_id', 'run_attempt', 'job_id'))
            and isinstance(proof.get('receipt_path'), str) and bool(proof['receipt_path']))


def reproducer_proof(classification, source_sha):
    proof = classification.get('reproducer')
    return (isinstance(proof, dict) and proof.get('verified') is True
            and proof.get('source_sha') == source_sha and proof.get('baseline') == 'failed'
            and isinstance(proof.get('receipt_path'), str) and bool(proof['receipt_path']))
