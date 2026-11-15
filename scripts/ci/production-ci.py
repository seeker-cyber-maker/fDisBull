#!/usr/bin/env python3
"""Fixed native endpoint for the existing n8n CI status/tick bridge."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE / 'fdisbull-ci-production' if (HERE / 'fdisbull-ci-production').is_dir() else HERE
sys.path.insert(0, str(MODULE_ROOT))

CONFIG = Path('/etc/fdisbull-ci-production/config.json')
STATE = Path('/var/lib/fdisbull-ci/control/recovery/production')
CONTROLLER_PROJECT = 'seeker-cyber-maker/fDisBull'
MAINTENANCE = Path('/var/lib/fdisbull-ci/control/production')


def _stop_encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _stop_directory(path,create=False):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('unsafe controller stop directory')
    if create:path.mkdir(mode=0o700,exist_ok=True)
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:
        raise ValueError('private controller stop directory required')
    return path


def _stop_bytes(path,maximum=262144):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('unsafe controller stop file')
    before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid() or before.st_mode&0o077
            or before.st_nlink!=1 or before.st_size>maximum):
        raise ValueError('private controller stop file required')
    with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb') as stream:
        opened=os.fstat(stream.fileno());data=stream.read(maximum+1);after=os.fstat(stream.fileno())
    current=path.lstat();fields=('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    if len(data)>maximum or any(getattr(before,k)!=getattr(other,k) for other in (opened,after,current) for k in fields):
        raise ValueError('controller stop file changed')
    return data


def _stop_write(path,data,mode=0o400):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),mode)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    directory=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(directory)
    finally:os.close(directory)


def _append_controller_event(root,event,runner=None):
    """One native journal append, with bounded identical ACK-loss retry only."""
    if Path(root)!=STATE:raise ValueError('fixed controller stop root required')
    _stop_directory(root)
    if (type(event) is not dict or set(event)!={'dedupe_key','phase','reason','test','context'}
            or event['phase']!='attention' or event['reason']!='ci_executor_unavailable' or type(event['test']) is not bool):
        raise ValueError('controller stop event invalid')
    match=re.fullmatch(r'controller-attention:([a-f0-9]{64})',event['dedupe_key'])
    context=event['context']
    if not match or type(context) is not dict or set(context)!={'provider','project','run_id','job_id','commit_sha','job_name','receipt_path'}:
        raise ValueError('controller stop identity invalid')
    snapshot=Path(root)/'incidents'/match[1]/'controller-attention-state.json'
    _stop_directory(snapshot.parent.parent);_stop_directory(snapshot.parent)
    patterns={'project':r'[A-Za-z0-9_./-]{1,200}','run_id':r'[A-Za-z0-9_.:-]{1,100}',
              'job_id':r'[A-Za-z0-9_.:-]{1,100}','commit_sha':r'(?:[a-f0-9]{40}|[a-f0-9]{64})',
              'job_name':r'[A-Za-z0-9_.:/ -]{1,100}'}
    if (context.get('provider') not in ('github','gitlab') or context.get('receipt_path')!=str(snapshot)
            or any(not isinstance(context.get(k),str) or not re.fullmatch(pattern,context[k]) for k,pattern in patterns.items())):
        raise ValueError('controller stop context invalid')
    snapshot_data=_stop_bytes(snapshot);digest=hashlib.sha256(snapshot_data).hexdigest()
    native='ci_'+hashlib.sha256(event['dedupe_key'].encode()).hexdigest()[:40]
    expected={'stage':'journaled','phase':'attention','incident_id':native,'event_id':'conn_'+native+'_attention'}
    payload=_stop_encode(event);run=subprocess.run if runner is None else runner
    for attempt in range(2):
        if _stop_bytes(snapshot)!=snapshot_data:raise ValueError('controller stop snapshot changed before journal append')
        try:
            result=run(['sudo','-n','-u','operations-alerts','/usr/bin/python3',
                        '/usr/local/libexec/ci_incident.py','append'],input=payload,capture_output=True,timeout=30,check=False)
        except (OSError,subprocess.SubprocessError):
            if attempt==0:continue
            raise RuntimeError('controller stop journal unavailable') from None
        try:reply=json.loads(result.stdout)
        except (AttributeError,TypeError,ValueError):
            if attempt==0:continue
            raise RuntimeError('controller stop journal unavailable') from None
        if (type(result.returncode) is not int or result.returncode!=0 or type(reply) is not dict
                or set(reply)!={'stage','phase','incident_id','event_id','execution_performed','already_present','delivery_status'}
                or any(reply.get(k)!=v for k,v in expected.items()) or reply.get('execution_performed') is not False
                or type(reply.get('already_present')) is not bool or reply.get('delivery_status')!='not_observed_here'):
            raise RuntimeError('controller stop journal reply rejected')
        return {**expected,'execution_performed':False,'snapshot_sha256':digest,'receipt_path':str(snapshot),
                'delivery_status':'not_observed_here'}
    raise RuntimeError('controller stop journal unavailable')


def append_controller_stop(root,key,stage,error_type,*,deadline_epoch=None,test=False,context=None,proof=None,runner=None):
    """Persist a real stop, never a synthetic RecoveryController/job outcome."""
    root=Path(root)
    if root!=STATE:raise ValueError('fixed controller stop root required')
    _stop_directory(root)
    if (not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,500}',key)
            or stage not in ('bootstrap','cleanup','qualification') or not isinstance(error_type,str)
            or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',error_type) or type(test) is not bool
            or deadline_epoch is not None and (type(deadline_epoch) not in (int,float)
                or not math.isfinite(deadline_epoch) or deadline_epoch<0)
            or proof is not None and type(proof) is not dict):
        raise ValueError('controller stop fields invalid')
    incident=hashlib.sha256(('controller-stop:'+stage+':'+key).encode()).hexdigest()
    directory=_stop_directory(_stop_directory(root/'incidents',create=True)/incident,create=True)
    snapshot=directory/'controller-attention-state.json';binding=directory/'controller-attention-binding.json'
    code=Path(__file__)
    if any(p.is_symlink() for p in (code,*code.parents)) or not code.is_file() or code.stat().st_uid!=os.geteuid() or code.stat().st_mode&0o022:
        raise ValueError('controller code identity unavailable')
    fingerprint=hashlib.sha256(code.read_bytes()).hexdigest()
    neutral=context is None
    context=({'provider':'github','project':CONTROLLER_PROJECT,'run_id':'controller','job_id':stage,
              'commit_sha':fingerprint,'job_name':'CI controller '+stage} if neutral else dict(context))
    if set(context)!={'provider','project','run_id','job_id','commit_sha','job_name'}:
        raise ValueError('controller stop context fields invalid')
    if not neutral and (context.get('provider')!='github' or context.get('project')!=CONTROLLER_PROJECT
            or any(not isinstance(context.get(k),str) or not re.fullmatch(r'[1-9][0-9]*',context[k]) for k in ('run_id','job_id'))
            or not isinstance(context.get('commit_sha'),str) or not re.fullmatch(r'[a-f0-9]{40}',context['commit_sha'])):
        raise ValueError('declared job context invalid')
    context={**context,'receipt_path':str(snapshot)}
    value={'schema':'fdisbull-controller-stop-1','status':'attention','key':key,'stage':stage,'error_type':error_type,
           'deadline_epoch':deadline_epoch,'test':test,'context_identity':'controller-code-fingerprint' if neutral else 'declared-job-target',
           'controller_code_sha256':fingerprint,'context':context,'proof':proof or {}}
    if len(_stop_encode(value))>262144:raise ValueError('controller stop snapshot too large')
    if not snapshot.exists() and not snapshot.is_symlink():
        if binding.exists() or binding.is_symlink():raise ValueError('controller stop binding orphaned')
        _stop_write(snapshot,_stop_encode(value)+b'\n')
        _stop_write(binding,_stop_encode({'schema':'fdisbull-controller-stop-binding-1','incident_id':incident,
                                       'snapshot_sha256':hashlib.sha256(_stop_bytes(snapshot)).hexdigest()})+b'\n')
    if any(stat.S_IMODE(p.stat().st_mode)!=0o400 for p in (snapshot,binding)):
        raise ValueError('immutable controller stop files required')
    original_data=_stop_bytes(snapshot);original=json.loads(original_data)
    # A stop retains its original controller-code fingerprint across a later
    # handler upgrade; that fingerprint is never labelled a candidate commit.
    if type(original) is dict:
        previous=original.get('controller_code_sha256')
        if not isinstance(previous,str) or not re.fullmatch(r'[a-f0-9]{64}',previous):raise ValueError('controller stop fingerprint invalid')
        value['controller_code_sha256']=previous
        if neutral:value['context']['commit_sha']=previous
    expected_binding={'schema':'fdisbull-controller-stop-binding-1','incident_id':incident,
                      'snapshot_sha256':hashlib.sha256(original_data).hexdigest()}
    if _stop_bytes(binding)!=_stop_encode(expected_binding)+b'\n' or _stop_encode(original)!=_stop_encode(value):
        raise ValueError('controller stop snapshot conflict')
    reference={'schema':'fdisbull-controller-stop-block-1','stop_id':incident,'stage':stage,'key':key,
               'error_type':error_type,'receipt_path':str(snapshot),'snapshot_sha256':expected_binding['snapshot_sha256']}
    blocked=root/'blocked.json'
    if not blocked.exists() and not blocked.is_symlink():
        try:_stop_write(blocked,_stop_encode(reference)+b'\n')
        except FileExistsError:pass
    event={'dedupe_key':'controller-attention:'+incident,'phase':'attention','reason':'ci_executor_unavailable',
           'test':test,'context':original['context']}
    try:
        result=_append_controller_event(root,event,runner)
        acknowledged=directory/'controller-stop-journal.json'
        if acknowledged.exists() or acknowledged.is_symlink():
            if _stop_bytes(acknowledged)!=_stop_encode(result)+b'\n':raise ValueError('controller stop journal conflict')
        else:_stop_write(acknowledged,_stop_encode(result)+b'\n')
        return result
    except (OSError,ValueError,RuntimeError) as error:
        unresolved=directory/'controller-stop-notification-unresolved.json'
        notice={'schema':'fdisbull-controller-stop-notification-unresolved-1','status':'attention',
                'snapshot_sha256':expected_binding['snapshot_sha256'],'reason':'native-journal-unconfirmed',
                'delivery_status':'not_observed_here','execution_performed':False}
        if unresolved.exists() or unresolved.is_symlink():
            if _stop_bytes(unresolved)!=_stop_encode(notice)+b'\n':raise ValueError('controller stop notification conflict')
        else:_stop_write(unresolved,_stop_encode(notice)+b'\n')
        raise


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('unsafe installed record')
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise ValueError('installed object required')
    return value


def verify_sources(config, root, owner):
    hashes = config.get('module_sha256')
    if not isinstance(hashes, dict) or not {'production_manifest.py', 'production-ci.py'} <= set(hashes):
        raise ValueError('exact installed source manifest missing')
    for name, expected in hashes.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.py', name)
                or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)):
            raise ValueError('invalid installed source manifest')
        path = root / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_uid != owner
                or path.stat().st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('installed source changed')
    spec = importlib.util.spec_from_file_location('installed_ci_manifest', root / 'production_manifest.py')
    manifest = importlib.util.module_from_spec(spec); spec.loader.exec_module(manifest)
    if set(hashes) != set(manifest.MODULES):
        raise ValueError('installed source manifest incomplete')
    if (config.get('entrypoint_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or config['entrypoint_sha256'] != hashes['production-ci.py']):
        raise ValueError('native entrypoint differs')


def installation_config():
    if os.geteuid() != 0:
        raise ValueError('native endpoint requires its installed service identity')
    if (CONFIG.is_symlink() or not CONFIG.is_file() or CONFIG.stat().st_uid != 0
            or CONFIG.stat().st_mode & 0o077):
        raise ValueError('private installed configuration required')
    config = read_json(CONFIG)
    if config.get('state_dir') != str(STATE):
        raise ValueError('installed state path mismatch')
    verify_sources(config, MODULE_ROOT, 0)
    return config


def runtime_factory(config, root, lease):
    # Status imports no provider implementation and performs no API/model call.
    from production_runtime import Runtime
    return Runtime(config, root, lease)


def service_factory(config):
    # Installation/source verification precedes imports of mutable local code.
    from production_control import ProductionService
    return ProductionService(config, runtime_factory)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid CI command.\n')


def record_failure(error_type,*,runner=None):
    """Replay the original blocker, including Runtime stops, through one journal."""
    _stop_directory(STATE)
    if not isinstance(error_type,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',error_type):
        raise ValueError('invalid service error category')
    blocked=STATE/'blocked.json'
    if not blocked.exists() and not blocked.is_symlink():
        record={'status':'attention','error_type':error_type,'observed_epoch':time.time()}
        path=STATE/('service-error-'+str(time.time_ns())+'.json')
        _stop_write(path,_stop_encode(record)+b'\n',mode=0o600)
        try:_stop_write(blocked,_stop_encode({**record,'receipt_path':str(path)})+b'\n',mode=0o600)
        except FileExistsError:pass
    data=_stop_bytes(blocked);record=json.loads(data)
    if type(record) is not dict:raise ValueError('controller blocker invalid')
    if record.get('schema') in ('fdisbull-one-module-maintenance-block-1','fdisbull-control-components-maintenance-block-1'):
        required={'schema','case','component_commit','old_config_sha256','old_state_sha256','history_before_sha256'}
        case=Path(record.get('case',''))
        if (not required<=set(record) or set(record)-required not in (set(),{'component_sha256'})
                or not case.is_absolute() or case.parent!=MAINTENANCE
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',case.name)
                or not isinstance(record['component_commit'],str) or not re.fullmatch(r'[a-f0-9]{40}',record['component_commit'])
                or any(not isinstance(record[k],str) or not re.fullmatch(r'[a-f0-9]{64}',record[k]) for k in
                       ('old_config_sha256','old_state_sha256','history_before_sha256'))):
            raise ValueError('maintenance metadata invalid')
        _stop_directory(case)
        if 'component_sha256' in record:
            components=record['component_sha256']
            if (type(components) is not dict or set(components)!={'production-ci.py','production_runtime.py'}
                    or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for v in components.values())):
                raise ValueError('maintenance component pins invalid')
        return {'stage':'maintenance-suppressed'}
    if record.get('schema')=='fdisbull-controller-stop-block-1':
        if set(record)!={'schema','stop_id','stage','key','error_type','receipt_path','snapshot_sha256'}:
            raise ValueError('controller stop reference invalid')
        stop_id=record['stop_id']
        if (not isinstance(stop_id,str) or not re.fullmatch(r'[a-f0-9]{64}',stop_id)
                or not isinstance(record['key'],str) or not isinstance(record['stage'],str)
                or hashlib.sha256(('controller-stop:'+record['stage']+':'+record['key']).encode()).hexdigest()!=stop_id):
            raise ValueError('controller stop reference identity differs')
        snapshot=STATE/'incidents'/stop_id/'controller-attention-state.json'
        original_data=_stop_bytes(snapshot);original=json.loads(original_data)
        if (record['receipt_path']!=str(snapshot) or record['snapshot_sha256']!=hashlib.sha256(original_data).hexdigest()
                or type(original) is not dict or original.get('stage')!=record['stage']
                or original.get('key')!=record['key'] or original.get('error_type')!=record['error_type']):
            raise ValueError('controller stop reference differs')
        context=None if original.get('context_identity')=='controller-code-fingerprint' else {
            k:v for k,v in original['context'].items() if k!='receipt_path'}
        arguments=dict(deadline_epoch=original['deadline_epoch'],test=original['test'],context=context,proof=original['proof'])
        key,stage,category=record['key'],record['stage'],record['error_type']
    else:
        category=record.get('error_type','ControllerBlocked')
        if not isinstance(category,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',category):category='ControllerBlocked'
        key='blocked:'+hashlib.sha256(data).hexdigest();stage='bootstrap'
        arguments={'proof':{'blocked_path':str(blocked),'blocked_sha256':hashlib.sha256(data).hexdigest(),'blocked_size':len(data)}}
    try:return append_controller_stop(STATE,key,stage,category,runner=runner,**arguments)
    except RuntimeError:
        stop_id=hashlib.sha256(('controller-stop:'+stage+':'+key).encode()).hexdigest()
        return {'stage':'notification-unresolved','phase':'attention','delivery_status':'not_observed_here',
                'execution_performed':False,'receipt_path':str(STATE/'incidents'/stop_id/'controller-attention-state.json')}


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('operation', choices=('status', 'run'))
    args = parser.parse_args(argv)
    previous_term = signal.signal(signal.SIGTERM, signal.SIG_IGN) if args.operation == 'run' else None
    try:
        config = installation_config()
        service = service_factory(config)
        result = service.status() if args.operation == 'status' else service.run()
        print(json.dumps(result, separators=(',', ':'), allow_nan=False))
        return 0 if args.operation == 'status' or result.get('status') in ('disabled', 'idle', 'complete') else 1
    except BlockingIOError:
        print('{"status":"busy"}')
        return 0
    except Exception as error:
        # Preserve only a safe error category; provider/log/credential text must
        # never enter the web response, journal or notification payload.
        if args.operation == 'run':
            try:
                record_failure(type(error).__name__)
            except Exception:
                pass
        if args.operation == 'status': print('{"schema_version":1,"state":"unknown"}')
        else: print(json.dumps({'status': 'attention', 'error_type': type(error).__name__}, separators=(',', ':')))
        return 1
    finally:
        if previous_term is not None: signal.signal(signal.SIGTERM, previous_term)


if __name__ == '__main__':
    raise SystemExit(main())
