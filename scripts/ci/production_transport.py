"""Finite allowlisted private provider bridge. No listener or credential transfer."""
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import plistlib
import tempfile
from pathlib import Path
import re
import sys
import time
from contextlib import contextmanager
from urllib.parse import parse_qsl

_spec=importlib.util.spec_from_file_location('recovery_source',Path(__file__).with_name('recovery_source.py'))
_source=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_source)
_status_path=Path(__file__).with_name('ci_status.py')
if not _status_path.exists(): _status_path=Path(__file__).parent.parent/'ci_status.py'
_spec_status=importlib.util.spec_from_file_location('ci_status',_status_path)
_status=importlib.util.module_from_spec(_spec_status);_spec_status.loader.exec_module(_status)

# Installed bridge must pin this path during review; never supplied by the caller.
STATE_DIR = '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state'
ANCHOR_FILE = '/Users/tiga/.local/state/fdisbull-ci-production/bridge-anchor.json'
VOLUME_UUID = '5DB767EC-4FB1-4B21-82B2-80B994B827E8'
INSTALLATION_ID = 'fdisbull-production-bridge-20261113-01'
GITLAB_USER_ID = 43957127
GITLAB_USERNAME = 'TiGa-RCE'
CANONICAL_REPO = '/Volumes/CODEX/Codex_Projects/fDisBull'
OWNER = '01a1692b-22ce-7b13-9d7d-05b2d4de529e'
SCOPES = {'github':('github.com','seeker-cyber-maker/fDisBull'),
          'gitlab':('gitlab.com','brewster-jennings-group/fdisbull')}
BATCH_PREFIX = '__bridge_batch__:'
MAX_INPUT=16384
GH='/repos/seeker-cyber-maker/fDisBull/actions'
GL='/projects/88349936'
NUM=r'[1-9][0-9]{0,19}'
GH_BIN='/opt/homebrew/bin/gh'
GLAB_BIN='/opt/homebrew/bin/glab'


class BudgetExceeded(RuntimeError):
    pass


class ProviderStop(RuntimeError):
    pass


def _ref(value):
    return (isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_./-]{1,200}',value) is not None
            and '..' not in value and not value.startswith(('/', '-')) and not value.endswith(('/', '.')))


def validate(provider,method,path,payload):
    if len(json.dumps(payload,separators=(',',':')).encode()) > MAX_INPUT: raise ValueError('payload too large')
    if provider not in ('github','gitlab') or method not in ('GET','POST') or not isinstance(path,str) or len(path)>500:
        raise ValueError('request not allowed')
    if any(c in path for c in ('#','%','\\','\n','\r')) or path.count('?')>1: raise ValueError('invalid path')
    root,sep,query=path.partition('?')
    if sep:
        pairs=parse_qsl(query,keep_blank_values=True,strict_parsing=True)
        if (method!='GET' or not pairs or len(pairs)>2 or len(dict(pairs))!=len(pairs)
                or any(k not in ('per_page','page') or not re.fullmatch(r'[1-9][0-9]{0,2}',v) for k,v in pairs)
                or any(k=='per_page' and int(v)>100 or k=='page' and int(v)>10 for k,v in pairs)):
            raise ValueError('query not allowed')
    patterns=([GH+r'/runs/'+NUM, GH+r'/runs/'+NUM+r'/attempts/'+NUM,
               GH+r'/runs/'+NUM+r'/attempts/'+NUM+r'/jobs',GH+r'/runs/'+NUM+r'/jobs',
               GH+r'/runs/'+NUM+r'/artifacts',GH+r'/artifacts/'+NUM,GH+r'/jobs/'+NUM,GH+r'/jobs/'+NUM+r'/logs',
               GH+r'/workflows/(?:ovh-bootstrap\.yml|417757453)/runs'] if provider=='github' else
              [GL+r'/pipelines/'+NUM, GL+r'/pipelines/'+NUM+r'/jobs',GL+r'/jobs/'+NUM,GL+r'/jobs/'+NUM+r'/trace'])
    if method=='GET':
        if payload is not None or not any(re.fullmatch(p,root) for p in patterns): raise ValueError('GET not allowed')
        if sep and not root.endswith(('/jobs','/artifacts','/runs')): raise ValueError('query not allowed here')
        return 'raw' if root.endswith(('/logs','/trace')) else 'json'
    if sep: raise ValueError('POST query not allowed')
    if provider=='github' and re.fullmatch(GH+r'/jobs/'+NUM+r'/rerun',root):
        if payload not in ({},None): raise ValueError('invalid retry body')
        return 'json'
    if provider=='github' and re.fullmatch(GH+r'/workflows/(?:ovh-bootstrap\.yml|417757453)/dispatches',root):
        if (not isinstance(payload,dict) or set(payload)!={'ref','inputs'} or not _ref(payload['ref'])
                or not isinstance(payload['inputs'],dict) or set(payload['inputs'])!={'nonce','candidate_sha'}
                or not isinstance(payload['inputs']['nonce'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',payload['inputs']['nonce'])
                or not isinstance(payload['inputs']['candidate_sha'],str) or not re.fullmatch('[0-9a-f]{40}',payload['inputs']['candidate_sha'])):
            raise ValueError('invalid dispatch body')
        return 'json'
    if provider=='gitlab' and re.fullmatch(GL+r'/jobs/'+NUM+r'/retry',root):
        if payload not in ({},None): raise ValueError('invalid retry body')
        return 'json'
    if provider=='gitlab' and root==GL+'/pipeline':
        if not isinstance(payload,dict) or set(payload)!={'ref'} or not _ref(payload['ref']): raise ValueError('invalid pipeline body')
        return 'json'
    raise ValueError('POST not allowed')



def request_digest(provider,method,path,payload):
    validate(provider,method,path,payload)
    document={'provider':provider,'method':method,'path':path,'payload':payload}
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _clean_env():
    blocked=('TOKEN','API_KEY','PASSWORD','SECRET','CREDENTIAL')
    return {k:v for k,v in os.environ.items() if not any(x in k.upper() for x in blocked)
            and k not in ('GH_HOST','GITLAB_HOST','GLAB_HOST','GH_REPO','GITLAB_REPO')}



def _redact(value):
    if isinstance(value,dict):
        return {k:_redact(v) for k,v in value.items() if isinstance(k,str)
                and not any(x in k.lower() for x in ('token','password','secret','authorization','credential','private_key'))}
    if isinstance(value,list): return [_redact(v) for v in value]
    return value


def _parse(output,raw):
    # No header or stderr content leaves this function.
    boundary=b'\r\n\r\n' if b'\r\n\r\n' in output else b'\n\n'
    if boundary not in output: raise RuntimeError('response unknown')
    head,body=output.split(boundary,1)
    lines=head.replace(b'\r\n',b'\n').split(b'\n')
    match=re.fullmatch(rb'HTTP/\S+\s+([1-5][0-9][0-9])(?:\s+[^\r\n]*)?',lines[0])
    if not match: raise RuntimeError('response unknown')
    code=int(match.group(1));request_id=None
    for line in lines[1:]:
        name,colon,value=line.partition(b':')
        if colon and name.lower() in (b'x-request-id',b'x-github-request-id'):
            v=value.strip().decode('ascii','ignore')
            if re.fullmatch(r'[A-Za-z0-9:._-]{1,128}',v): request_id=v
    if code >= 400: return {'http_status':code,'data':None,'request_id':request_id}
    if not body.strip():data=None
    elif raw:
        if len(body)>1024*1024: raise BudgetExceeded('raw response exceeds budget')
        data={'encoding':'base64','size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'data':base64.b64encode(body).decode('ascii')}
    else:
        try:data=_redact(json.loads(body))
        except (ValueError,UnicodeError):raise RuntimeError('response unknown') from None
    return {'http_status':code,'data':data,'request_id':request_id}



def _mounted_codex(state,anchor):
    root=Path('/Volumes/CODEX')
    if not os.path.ismount(root) or root.is_symlink(): return False
    try:
        result=_source.run_command(['/usr/sbin/diskutil','info','-plist',str(root)],cwd='/',timeout=12)
        if result.get('returncode')!=0 or result.get('timed_out') is not False or result.get('overflow') is not False:
            return False
        info=plistlib.loads(result['stdout'])
        return (info.get('VolumeUUID')==VOLUME_UUID and info.get('MountPoint')==str(root)
                and info.get('Internal') is False and state.stat().st_dev==root.stat().st_dev)
    except (OSError,ValueError,KeyError,TypeError): return False


def _atomic_existing(path,value):
    data=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.pending-')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(str(path.parent),os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)

class ProviderBridge:
    def __init__(self,state_dir,runner=None,*,anchor_file=ANCHOR_FILE,mount_validator=None,gitlab_principal=None,
                 status_api=None,status_dir=None,clock=None):
        self.state=Path(state_dir);self.anchor=Path(anchor_file)
        self.runner=runner or _source.run_command
        self.mount_validator=mount_validator or _mounted_codex
        self.principal=gitlab_principal if gitlab_principal is not None else (GITLAB_USER_ID,GITLAB_USERNAME)
        self.status_api=status_api or _status;self.status_dir=Path(status_dir) if status_dir is not None else None
        self.clock=clock or time.time

    def _run(self,argv,env,input_bytes=None,timeout=30):
        r=self.runner(argv,cwd='/',env=env,input_bytes=input_bytes,timeout=timeout)
        if isinstance(r,dict) and r.get('overflow') is True: raise BudgetExceeded('response exceeds budget')
        if (not isinstance(r,dict) or r.get('timed_out') is not False or r.get('overflow') is not False
                or not isinstance(r.get('stdout'),bytes) or not isinstance(r.get('stderr'),bytes)
                or len(r['stdout'])>_source.LIMIT or len(r['stderr'])>_source.LIMIT):
            raise RuntimeError('provider transport unknown')
        return r

    def _call_provider(self,provider,method,path,payload,raw):
        env=_clean_env()
        if provider=='github':
            token=self._run([GH_BIN,'auth','token','--user','seeker-cyber-maker','--hostname','github.com','--no-refresh'],env,timeout=15)
            value=token['stdout'].strip()
            if token.get('returncode')!=0 or not value or len(value)>4096 or b'\n' in value or b'\r' in value:
                raise ProviderStop('provider_authentication_required')
            env['GH_TOKEN']=value.decode('ascii','strict')
            argv=[GH_BIN,'api','--hostname','github.com','--include','--method',method,path]
            if raw:
                # CI logs contain ANSI bytes. Capture original bounded bytes
                # privately; they are encoded for the RPC and never printed to
                # a terminal, notification, or model prompt.
                argv.append('--allow-escape-sequences')
        else:
            argv=[GLAB_BIN,'api','--hostname','gitlab.com','--include','--method',method,path]
        body=None
        if method=='POST':
            argv.extend(['--input','-']);body=json.dumps(payload or {},separators=(',',':')).encode()
        result=self._run(argv,env,input_bytes=body,timeout=30)
        response=_parse(result['stdout'],raw)
        if result.get('returncode')!=0 and response['http_status']<400: raise RuntimeError('provider transport unknown')
        return response

    def _scope_state(self,provider):
        if provider not in SCOPES:raise ValueError('invalid provider')
        host,repo=SCOPES[provider]
        directory=self.status_dir if self.status_dir is not None else self.status_api.default_state_dir(CANONICAL_REPO)
        directory=Path(directory)
        # Shared state must pre-exist: never silently start a new throttle namespace.
        scope=self.status_api._directory(directory,host.lower(),repo.lower())
        if (not directory.is_dir() or directory.is_symlink() or not (scope/'state.json').is_file()
                or (scope/'state.json').is_symlink()):raise RuntimeError('shared provider state unavailable')
        if self.status_dir is None and directory.stat().st_dev!=self.state.stat().st_dev:
            raise RuntimeError('shared provider state is off volume')
        return host,repo,directory,scope

    @contextmanager
    def _bridge_lock(self):
        self._ensure()
        fd=os.open(str(self.state/'actions.lock'),os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'r+') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            self._ensure()
            yield

    def reserve(self,provider):
        with self._bridge_lock():
            host,repo,directory,_=self._scope_state(provider)
            now=self.status_api._clock_value(self.clock)
            result=self.status_api.reserve_refresh(repo=repo,host=host,owner=OWNER,state_dir=directory,clock=self.clock)
            if result.get('allowed') is True:
                batch={'kind':'provider-batch','provider':provider,'owner':OWNER,'start':now,
                       'expires':result['next_refresh_at'],'remaining':100}
                self._save_mirrored(self._file(BATCH_PREFIX+provider),batch)
            return {k:result.get(k) for k in ('allowed','reason','next_refresh_at')}

    def _send(self,provider,method,path,payload,raw):
        # The shared lock excludes another owner/stop update until this one HTTP
        # response is known. The action lock is already held by request().
        host,repo,directory,scope=self._scope_state(provider)
        stop=None;failure=None
        with self.status_api._locked(scope) as acquired:
            if not acquired:raise RuntimeError('shared provider gate busy')
            state=self.status_api._load_state(scope/'state.json',host.lower(),repo.lower())
            batch_path=self._file(BATCH_PREFIX+provider)
            if not batch_path.is_file() or batch_path.is_symlink():raise RuntimeError('provider batch unavailable')
            batch=json.loads(batch_path.read_text());now=self.status_api._clock_value(self.clock)
            if (not isinstance(batch,dict) or batch.get('kind')!='provider-batch' or batch.get('provider')!=provider
                    or batch.get('owner')!=OWNER or state['owner']!=OWNER or state['provider_stop'] is not None
                    or type(batch.get('start')) not in (int,float) or type(batch.get('expires')) not in (int,float)
                    or not batch['start']<=now<batch['expires'] or batch['expires']!=state['next_allowed_at']
                    or type(batch.get('remaining')) is not int or not 1<=batch['remaining']<=100):
                raise RuntimeError('provider batch expired or stopped')
            self._save_mirrored(batch_path,{**batch,'remaining':batch['remaining']-1})
            try:
                response=self._call_provider(provider,method,path,payload,raw)
            except ProviderStop as exc:
                stop=str(exc);failure=exc;response=None
            if response is not None and response['http_status'] in (401,403,429):
                stop='provider_http_'+str(response['http_status'])
            if stop:
                # Persist before releasing the shared lock; record_provider_stop is
                # also invoked below using the existing public helper.
                if state['provider_stop'] is None:
                    state['provider_stop']={'reason':stop,'observed_at':now}
                    self.status_api._write(scope/'state.json',state)
        if stop:
            self.status_api.record_provider_stop(repo=repo,host=host,owner=OWNER,reason=stop,state_dir=directory,clock=self.clock)
        if failure is not None:raise failure
        return response

    def _file(self,key):
        if not isinstance(key,str) or not 1<=len(key)<=500 or any(ord(c)<32 for c in key): raise ValueError('invalid action key')
        return self.state/(hashlib.sha256(key.encode()).hexdigest()+'.json')

    def _ensure(self):
        # Installation is an explicit operator step; serving never creates roots or markers.
        if not self.mount_validator(self.state,self.anchor): raise RuntimeError('external mount unavailable')
        root=self.state
        if (any(p.is_symlink() for p in (root,*root.parents)) or not root.is_dir()
                or root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077):
            raise RuntimeError('private state unavailable')
        marker=root/'installation.json'
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_mode&0o077:
            raise RuntimeError('installation marker unavailable')
        if json.loads(marker.read_text())!={'installation_id':INSTALLATION_ID,'volume_uuid':VOLUME_UUID}:
            raise RuntimeError('installation marker mismatch')
        lock=root/'actions.lock'
        if lock.is_symlink() or not lock.is_file() or lock.stat().st_mode&0o077:
            raise RuntimeError('state lock missing')
        anchor=self.anchor;parent=anchor.parent
        if (any(p.is_symlink() for p in (anchor,*anchor.parents)) or not parent.is_dir()
                or parent.stat().st_uid!=os.getuid() or parent.stat().st_mode&0o077
                or not anchor.is_file() or anchor.stat().st_uid!=os.getuid() or anchor.stat().st_mode&0o077
                or anchor.stat().st_size>1024*1024):
            raise RuntimeError('history anchor unavailable')
        history=json.loads(anchor.read_text())
        if (not isinstance(history,dict) or set(history)!={'installation_id','volume_uuid','sequence','actions'}
                or history['installation_id']!=INSTALLATION_ID or history['volume_uuid']!=VOLUME_UUID
                or type(history['sequence']) is not int or history['sequence']<0
                or not isinstance(history['actions'],dict) or len(history['actions'])>10000):
            raise RuntimeError('invalid history anchor')
        entries={}
        for path in root.iterdir():
            if not re.fullmatch(r'[0-9a-f]{64}\.json',path.name):continue
            if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077 or path.stat().st_size>MAX_INPUT:
                raise RuntimeError('invalid history')
            entries[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        if entries!=history['actions'] or history['sequence']<len(entries):
            raise RuntimeError('action history mismatch')
        return history

    def _save_mirrored(self,record,value):
        history=self._ensure()
        data=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
        actions=dict(history['actions']);actions[record.name]=hashlib.sha256(data).hexdigest()
        _atomic_existing(self.anchor,{**history,'actions':actions,'sequence':history['sequence']+1})
        _atomic_existing(record,value)
        self._ensure()

    def _verify_gitlab_principal(self):
        identity=self.principal
        if (not isinstance(identity,tuple) or len(identity)!=2 or isinstance(identity[0],bool)
                or not isinstance(identity[0],int) or identity[0]<=0
                or not isinstance(identity[1],str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',identity[1])):
            raise RuntimeError('GitLab account pin unavailable')
        response=self._send('gitlab','GET','user',None,False)
        data=response.get('data')
        if (response.get('http_status')!=200 or not isinstance(data,dict)
                or type(data.get('id')) is not int or (data['id'],data.get('username'))!=identity):
            host,repo,directory,_=self._scope_state('gitlab')
            self.status_api.record_provider_stop(repo=repo,host=host,owner=OWNER,reason='provider_account_mismatch',state_dir=directory,clock=self.clock)
            raise RuntimeError('GitLab account mismatch or unavailable')

    def receipt(self,key):
        self._ensure();path=self._file(key)
        if path.is_symlink(): raise RuntimeError('invalid receipt')
        if not path.exists(): return None
        value=json.loads(path.read_text())
        if value.get('action_key') != key: raise RuntimeError('receipt mismatch')
        return value

    def request(self,provider,method,path,payload=None,action_key=None):
        raw=validate(provider,method,path,payload)=='raw'
        self._ensure()
        if method=='GET':
            if action_key is not None: raise ValueError('unexpected action key')
            with self._bridge_lock(): return self._send(provider,method,path,payload,raw)
        if isinstance(action_key,str) and action_key.startswith(BATCH_PREFIX):raise ValueError('reserved action key')
        record=self._file(action_key)
        try:
            with self._bridge_lock():
                digest=request_digest(provider,method,path,payload)
                old=self.receipt(action_key)
                if old:
                    if old.get('request_sha256')!=digest: raise RuntimeError('action key reused')
                    if old.get('status')=='accepted':return old['envelope']
                    raise RuntimeError('previous action outcome unknown')
                intent={'action_key':action_key,'request_sha256':digest,'status':'unknown'}
                self._save_mirrored(record,intent)
                if provider=='gitlab':self._verify_gitlab_principal()
                self._ensure()
                response=self._send(provider,method,path,payload,raw)
                expected=201 if provider=='gitlab' or path.endswith('/rerun') else 204
                if response['http_status']==expected:
                    data=response['data']
                    if provider=='gitlab':
                        if not isinstance(data,dict) or isinstance(data.get('id'),bool) or not str(data.get('id','')).isascii() or not str(data.get('id','')).isdecimal() or int(data['id'])<=0:
                            raise RuntimeError('accepted identity unknown')
                        response={**response,'data':{'id':int(data['id'])}}
                    elif data is not None: raise RuntimeError('accepted response unknown')
                    self._save_mirrored(record,{**intent,'status':'accepted','envelope':response})
                return response
        except BaseException:
            raise


class SSHProviderTransport:
    def __init__(self,provider,bridge_path,*,runner=None):
        if provider not in ('github','gitlab') or not isinstance(bridge_path,str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+\.py',bridge_path) or '..' in bridge_path.split('/'):
            raise ValueError('invalid bridge configuration')
        self.provider,self.bridge_path,self.runner=provider,bridge_path,runner or _source.run_command

    def _call(self,doc):
        argv=['/usr/bin/tailscale','ssh','tiga@100.76.103.43','/usr/bin/python3',self.bridge_path]
        r=self.runner(argv,cwd='/',env=_clean_env(),input_bytes=json.dumps(doc,separators=(',',':')).encode(),timeout=45)
        if (not isinstance(r,dict) or r.get('returncode')!=0 or r.get('timed_out') is not False or r.get('overflow') is not False
                or not isinstance(r.get('stdout'),bytes) or len(r['stdout'])>_source.LIMIT): raise RuntimeError('bridge outcome unknown')
        try: value=json.loads(r['stdout'])
        except (ValueError,UnicodeError):raise RuntimeError('bridge outcome unknown') from None
        if not isinstance(value,dict) or 'error' in value: raise RuntimeError('bridge outcome unknown')
        return value

    def request(self,method,path,payload=None):
        if method!='GET': raise ValueError('POST requires bound action key')
        validate(self.provider,method,path,payload)
        return self._call({'operation':'request','provider':self.provider,'method':method,'path':path,'payload':payload})

    def for_action(self,key):
        def request(method,path,payload=None):
            if method!='POST': raise ValueError('action binding is POST only')
            validate(self.provider,method,path,payload)
            return self._call({'operation':'request','provider':self.provider,'method':method,'path':path,'payload':payload,'action_key':key})
        return request

    def receipt(self,key): return self._call({'operation':'receipt','action_key':key})

    def reserve(self): return self._call({'operation':'reserve','provider':self.provider})


def main():
    try:
        data=sys.stdin.buffer.read(MAX_INPUT+1)
        if len(data)>MAX_INPUT: raise ValueError('input too large')
        doc=json.loads(data)
        if not isinstance(doc,dict): raise ValueError('invalid request')
        bridge=ProviderBridge(STATE_DIR)
        if doc.get('operation')=='reserve' and set(doc)=={'operation','provider'}:
            result=bridge.reserve(doc['provider'])
        elif doc.get('operation')=='receipt' and set(doc)=={'operation','action_key'}:
            result={'receipt':bridge.receipt(doc['action_key'])}
        elif doc.get('operation')=='request' and set(doc) in ({'operation','provider','method','path','payload'},
                                                                  {'operation','provider','method','path','payload','action_key'}):
            result=bridge.request(doc['provider'],doc['method'],doc['path'],doc['payload'],doc.get('action_key'))
        else: raise ValueError('invalid operation')
        print(json.dumps(result,separators=(',',':')))
    except BudgetExceeded:
        print('{"error":"output_budget_exceeded"}')
        return 1
    except Exception:
        print('{"error":"request_unavailable"}')
        return 1
    return 0


if __name__=='__main__': sys.exit(main())
