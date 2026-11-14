"""Prepared client for the reviewed, finite Aqua-session spool.

This module does not enable the remote allowed kinds or install any service.
Caller-provided action keys are durably bound before a single submit. An
uncertain submit is only followed by read-only result requests, never replayed.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from recovery_source import run_command

STATE=Path('/var/lib/fdisbull-ci/control/recovery/production/gui-client')
HELPER='/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/production_gui_transport.py'
PYTHON='/Users/tiga/miniconda/bin/python3'
MAX_REQUEST=32*1024*1024
MAX_REPLY=2*1024*1024
TERMINAL_UNKNOWN_REASONS={'runner_nonzero','runner_invalid_json','runner_error','runner_output_invalid',
                         'operator_reconciled_post_cleanup'}


class CompletedGuiFailure(RuntimeError):
    """The GUI child returned normally, but its operation result is unknown."""
    def __init__(self,reason,returncode):
        if reason not in TERMINAL_UNKNOWN_REASONS or type(returncode) is not int or returncode<0:
            raise ValueError('invalid completed GUI failure')
        self.reason,self.returncode=reason,returncode
        super().__init__('GUI child completed with unknown operation result')


class GuiTransportError(RuntimeError):
    """A finite transport call failed before a validated response arrived."""


def _bytes(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def _hash(data):return hashlib.sha256(data).hexdigest()


class GuiClient:
    def __init__(self,state_dir=STATE,*,runner=None,clock=time.time,sleep=time.sleep,monotonic=time.monotonic):
        self.state=Path(state_dir);self.runner=runner or run_command;self.clock=clock;self.sleep=sleep;self.monotonic=monotonic

    def _check(self):
        p=self.state
        if (not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)) or not p.is_dir()
                or p.stat().st_uid!=os.geteuid() or p.stat().st_mode&0o077):raise ValueError('GUI client state unavailable')
        marker=p/'installation.json';lock=p/'client.lock';history=p/'history.json'
        for f in (marker,lock,history):
            if f.is_symlink() or not f.is_file() or f.stat().st_uid!=os.geteuid() or f.stat().st_mode&0o077:
                raise ValueError('GUI client installation unavailable')
        if marker.stat().st_size>4096 or json.loads(marker.read_text())!={'schema':'fdisbull-gui-client-1'}:raise ValueError('GUI client marker mismatch')
        if history.stat().st_size>1024*1024:raise ValueError('GUI client history exceeds bound')
        data=json.loads(history.read_text())
        if (not isinstance(data,dict) or set(data)!={'schema','entries'}
                or data['schema']!='fdisbull-gui-client-history-1' or not isinstance(data['entries'],dict)
                or len(data['entries'])>4096):raise ValueError('invalid GUI client history')
        actual={x.name for x in p.iterdir()}
        expected={'installation.json','client.lock','history.json'}|{key+'.json' for key in data['entries']}
        if actual!=expected:raise ValueError('GUI client history missing or unrecognized')
        for nonce,digest in data['entries'].items():
            item=p/(nonce+'.json')
            if (not isinstance(nonce,str) or not re.fullmatch('[0-9a-f]{64}',nonce)
                    or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)
                    or item.is_symlink() or not item.is_file() or item.stat().st_uid!=os.geteuid()
                    or item.stat().st_mode&0o077 or item.stat().st_size>4096 or _hash(item.read_bytes())!=digest):
                raise ValueError('GUI client history mismatch')
        return data

    def _intent(self,kind,doc,key,timeout):
        self._check()
        if (kind not in ('provider','source') or not isinstance(doc,dict) or not isinstance(key,str)
                or not key or len(key)>500 or any(ord(c)<32 for c in key)):
            raise ValueError('invalid GUI action')
        if type(timeout) not in (int,float) or not 0<timeout<=600:raise ValueError('invalid GUI timeout')
        payload=_bytes({'kind':kind,'request':doc})
        if len(payload)>MAX_REQUEST:raise ValueError('GUI request exceeds bound')
        nonce=_hash(('gui-client:'+kind+':'+key).encode())
        path=self.state/(nonce+'.json');lockfd=os.open(self.state/'client.lock',os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(lockfd,'r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);history=self._check()
            if path.exists() or path.is_symlink():
                if (path.is_symlink() or not path.is_file() or path.stat().st_uid!=os.geteuid()
                        or path.stat().st_mode&0o077 or path.stat().st_size>4096):raise ValueError('unsafe GUI intent')
                value=json.loads(path.read_text())
                if (value.get('schema')!='fdisbull-gui-client-intent-1' or type(value.get('expires_epoch')) not in (int,float)
                        or value.get('nonce')!=nonce or value.get('kind')!=kind or value.get('action_key')!=key
                        or value.get('request_sha256')!=_hash(payload)):
                    raise ValueError('GUI action binding changed')
                return value,False
            now=self.clock();value={'schema':'fdisbull-gui-client-intent-1','nonce':nonce,'kind':kind,'action_key':key,
                                    'request_sha256':_hash(payload),'expires_epoch':now+timeout}
            data=_bytes(value);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            history['entries'][nonce]=_hash(data)
            temporary=self.state/('.history-'+nonce)
            hfd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(hfd,'wb') as stream:stream.write(_bytes(history));stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.state/'history.json')
            dfd=os.open(self.state,os.O_RDONLY)
            try:os.fsync(dfd)
            finally:os.close(dfd)
            return value,True

    def _remote(self,doc,*,timeout=45):
        payload=_bytes(doc)
        if len(payload)>MAX_REQUEST:raise ValueError('GUI request exceeds bound')
        argv=['/usr/bin/tailscale','ssh','tiga@100.76.103.43',PYTHON,'-I',HELPER,'request']
        markers=('TOKEN','API_KEY','PASSWORD','SECRET','CREDENTIAL','AUTHORIZATION')
        env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in markers)}
        try:result=self.runner(argv,cwd='/',env=env,input_bytes=payload,timeout=timeout)
        except (OSError,TimeoutError):raise GuiTransportError('GUI transport outcome unknown') from None
        if not isinstance(result,dict):raise RuntimeError('GUI transport outcome unknown')
        if result.get('overflow') is not False:raise RuntimeError('GUI transport outcome unknown')
        if result.get('timed_out') is True:
            raise GuiTransportError('GUI transport outcome unknown')
        if type(result.get('returncode')) is int and result['returncode']!=0:
            # A structured helper rejection is an application outcome, not a
            # transport blip; never retry it as though no response arrived.
            raw=result.get('stdout')
            if isinstance(raw,bytes) and len(raw)<=MAX_REPLY:
                try:failure=json.loads(raw)
                except (ValueError,UnicodeError):failure=None
                if isinstance(failure,dict) and 'error' in failure:
                    raise RuntimeError('GUI transport outcome unknown')
            raise GuiTransportError('GUI transport outcome unknown')
        if (result.get('returncode')!=0 or result.get('timed_out') is not False
                or result.get('overflow') is not False or not isinstance(result.get('stdout'),bytes)
                or len(result['stdout'])>MAX_REPLY):raise RuntimeError('GUI transport outcome unknown')
        try:value=json.loads(result['stdout'])
        except (ValueError,UnicodeError):raise RuntimeError('GUI transport outcome unknown') from None
        if not isinstance(value,dict) or 'error' in value:raise RuntimeError('GUI transport outcome unknown')
        return value

    def call(self,kind,doc,*,key=None,timeout=600):
        # GETs/receipt reads are new logical calls. Mutations supply their own
        # stable key; repeated calls use the old nonce and never resubmit.
        if key is None:key='read:'+secrets.token_hex(32)
        intent,new=self._intent(kind,doc,key,timeout);nonce=intent['nonce']
        if new and self.clock()<intent['expires_epoch']:
            try:
                sent=self._remote({'operation':'submit','kind':kind,'request':doc,
                                   'expires_epoch':intent['expires_epoch'],'nonce':nonce},timeout=min(45,timeout))
                if sent.get('request_id')!=nonce or sent.get('status') not in ('pending','known','unknown'):
                    raise RuntimeError('GUI submit outcome unknown')
            except Exception:
                # This request might already be queued; only read its receipt.
                pass
        while True:
            # Receipt lookup has its own total budget, including one bounded
            # transport retry; action expiry never truncates a retained read.
            deadline=self.monotonic()+45
            for attempt in range(2):
                remaining=deadline-self.monotonic()
                if remaining<=0:raise RuntimeError('GUI result outcome unknown')
                try:
                    result=self._remote({'operation':'result','request_id':nonce},timeout=remaining)
                    break
                except GuiTransportError:
                    if attempt==1:raise RuntimeError('GUI result outcome unknown') from None
            if result.get('request_id') not in (None,nonce):raise RuntimeError('GUI result identity mismatch')
            if result.get('status')=='complete':
                value=result.get('result')
                if not isinstance(value,dict):raise RuntimeError('GUI result invalid')
                return value
            if result.get('status')=='unknown' and self._completed_unknown(result,nonce):
                raise CompletedGuiFailure(result['reason'],result['runner']['returncode'])
            if result.get('status') in ('missing','expired'):raise RuntimeError('GUI action outcome unknown')
            if result.get('status') not in ('pending','unknown'):raise RuntimeError('GUI result invalid')
            if self.clock()>=intent['expires_epoch']:raise RuntimeError('GUI action outcome unknown')
            self.sleep(min(2,max(0,intent['expires_epoch']-self.clock())))

    @staticmethod
    def _completed_unknown(result,nonce):
        if (set(result)!={'status','request_id','reason','runner'} or result.get('request_id')!=nonce
                or result.get('reason') not in TERMINAL_UNKNOWN_REASONS):return False
        runner=result['runner']
        return (isinstance(runner,dict) and set(runner)=={'returncode','timed_out','overflow'}
                and type(runner.get('returncode')) is int and runner['returncode']>=0
                and runner.get('timed_out') is False and runner.get('overflow') is False)


class GuiProviderTransport:
    request_budget=2
    # Reserve enough batch lifetime for both bounded GET HTTP starts, including
    # GUI handoff/result lookup between them; this is not a reply deadline.
    request_window_seconds=180
    action_window_seconds=75  # One action-bound POST; no POST replay.
    def __init__(self,provider,client):
        if provider not in ('github','gitlab'):raise ValueError('invalid provider')
        self.provider,self.client=provider,client
        # GitLab verifies its pinned principal with a charged GET (up to 30s)
        # before the single POST, after the GUI handoff. Both starts must fit.
        self.action_window_seconds=110 if provider=='gitlab' else 75
    def request(self,method,path,payload=None):
        if method!='GET':raise ValueError('POST requires action binding')
        doc={'operation':'request','provider':self.provider,'method':method,'path':path,'payload':payload}
        try:return self.client.call('provider',doc,timeout=60)
        except CompletedGuiFailure:
            # A fresh nonce buys one read-only retry. A second unknown or any
            # uncertain child start is surfaced to the caller without replay.
            return self.client.call('provider',doc,timeout=60)
    def for_action(self,key):
        def request(method,path,payload=None):
            if method!='POST':raise ValueError('action binding is POST only')
            doc={'operation':'request','provider':self.provider,'method':method,'path':path,'payload':payload,'action_key':key}
            return self.client.call('provider',doc,key='provider-action:'+key,timeout=60)
        return request
    def receipt(self,key):return self.client.call('provider',{'operation':'receipt','action_key':key},timeout=60)
    def reserve(self):return self.client.call('provider',{'operation':'reserve','provider':self.provider},timeout=60)


class GuiSourceTransport:
    def __init__(self,client):self.client=client
    def _call(self,operation,*,binding=None,**fields):
        doc={'operation':operation,**fields}
        stable=('source-'+operation+':'+binding) if binding is not None else None
        result=self.client.call('source',doc,key=stable,timeout=590)
        if set(result)!={'result'}:raise RuntimeError('GUI source result invalid')
        return result['result']
    def prepare(self,target,evidence):
        key=_hash(_bytes({'target':target,'evidence':evidence}))
        return self._call('prepare',binding=key,target=target,evidence=evidence)
    def reconcile_prepare(self,target,evidence):return self._call('reconcile_prepare',target=target,evidence=evidence)
    def repair(self,key,payload):return self._call('repair',binding=key,key=key,payload=payload)
    def reconcile(self,key,payload):return self._call('reconcile',key=key,payload=payload)
