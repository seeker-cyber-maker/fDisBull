"""Proposed finite Aqua-session CI bridge; no listener, timer, or auto-install.

Installation, launchd activation and use are separate operator decisions. A
submitted request is never relaunched after an uncertain kickstart or start.
"""
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time

CACHE=Path('/Volumes/CACHE')
CACHE_UUID='DB098A4B-7968-418F-8B20-61597F42392A'
CONTROL=CACHE/'fdisbull-ci-builds'/'production-ci-gui'
SPOOL=CONTROL/'spool'
ANCHOR=CONTROL/'anchor.json'
INSTALLATION_ID='fdisbull-gui-transport-20261114-v1'
BRIDGE=Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge')
HELPER=BRIDGE/'production_gui_transport.py'
LABEL='com.fdisbull.ci-gui-once'
ACTIVATION=BRIDGE/'gui-activation.json'
MODULES={'production_gui_transport.py','production_transport.py','production_source_transport.py',
         'production_source_publish.py','recovery_production.py','recovery_source_production.py',
         'recovery_source.py','ci_status.py','production_held_reconcile.py'}
UID=501
GH_SHA256='258d12a00ca7939294c4b9a977eae72dc74882f8c4293012126f8d2da27e9d2e'
LAUNCHCTL_SHA256='c09fb522287bee5483d281ccd145fda129cd5eba940e5716cc4a2f25c18299e3'
MAX_INPUT=32*1024*1024
MAX_OUTPUT=2*1024*1024
MAX_RETAINED=64*1024*1024
MAX_SECONDS=600
HANDSHAKE_INTERVAL=1.0
LOST_POST_REQUEST_ID='0316a157f2ec4a0b8985b67fdd9c3052a0fcc5cc501d8fcae97dbd9e9a3d6be8'
LOST_POST_ACTION_KEY='3c39f4ca9987e2166bebe419f28d979ae9e73ae19a3d01310b7ebbc7c0ef97ad:2:retry_job'
LOST_POST_ACTION_SHA256='48fe4c15922543bba43ba14d48c145730817158cb720dd19f29f6424cfb158d4'
LOST_POST_RECORD_SHA256='1679430b5f78cefc370aa2f4f69c1ddd6405a6cab1be3b08b831e1f9819fc7c9'
LOST_POST_RECORD_NAME='952ac1473c4c141b4fec74f0ce9608a0c600124a503b9924f15afe8f5831cb02.json'


def _load(name):
    path=Path(__file__).with_name(name)
    spec=importlib.util.spec_from_file_location('gui_transport_'+name.replace('.','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


# Loaded only after installed module bytes have passed activation hashes.
provider=None
source=None
SOURCE_PYTHON='/Users/tiga/miniconda/bin/python3'
SOURCE_PYTHON_SHA256='0f5374bca527c5a5e958ee94e03e55816a368533286e6315b8bf013da622fc61'
GH_BIN='/opt/homebrew/bin/gh'
PROVIDER_MAX_INPUT=16384


def _bytes(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def _digest(data):return hashlib.sha256(data).hexdigest()


def _is_sha256(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def _mount(spool,anchor):
    if not os.path.ismount(CACHE) or CACHE.is_symlink():return False
    try:
        result=subprocess.run(['/usr/sbin/diskutil','info','-plist',str(CACHE)],capture_output=True,timeout=12,check=False)
        if result.returncode!=0 or len(result.stdout)>65536:return False
        info=plistlib.loads(result.stdout)
        return (info.get('VolumeUUID')==CACHE_UUID and info.get('MountPoint')==str(CACHE)
                and info.get('Internal') is False and spool.stat().st_dev==CACHE.stat().st_dev
                and anchor.stat().st_dev==CACHE.stat().st_dev)
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):return False


def _read(path,maximum):
    if any(x.is_symlink() for x in (path,*path.parents)) or not path.is_file():raise ValueError('private file missing')
    st=path.stat()
    if st.st_uid!=os.getuid() or st.st_mode&0o077 or st.st_size>maximum:raise ValueError('unsafe private file')
    return path.read_bytes()


def _exclusive(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    dfd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(dfd)
    finally:os.close(dfd)


def _replace(path,data):
    # An interrupted replacement leaves its unique file for operator review.
    temporary=path.with_name('.pending-'+str(os.getpid())+'-'+str(time.time_ns()))
    _exclusive(temporary,data);os.replace(temporary,path)
    dfd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(dfd)
    finally:os.close(dfd)


def _request(kind,document):
    if not isinstance(document,dict):raise ValueError('invalid fixed request')
    if kind=='credential_probe' and document=={}:return
    if kind=='canonical_read':
        if document=={
                'operation':'canonical_read',
                'action_key':'induced-missing-policy-23fa9831-20261114-01',
                'request_sha256':'ac8a51ab8263044d78cf1c5726fdbb19851c2824197534b2c90fee244dea219d',
                'prestate_sha256':'cd4326afdb1ce6dd848c6bba5b7e429c1168d2d82d834abb2089d0762ea4cf28'}:
            return
        raise ValueError('historical reconciliation binding differs')
    if kind=='provider':
        op=document.get('operation')
        if op=='reserve' and set(document)=={'operation','provider'} and document['provider'] in ('github','gitlab'):return
        if op=='receipt' and set(document)=={'operation','action_key'}:
            if isinstance(document['action_key'],str) and 1<=len(document['action_key'])<=500 and not any(ord(c)<32 for c in document['action_key']):return
        if op=='request' and set(document) in ({'operation','provider','method','path','payload'},
                                              {'operation','provider','method','path','payload','action_key'}):
            provider.validate(document['provider'],document['method'],document['path'],document['payload'])
            key=document.get('action_key')
            if document['method']=='GET' and key is None:return
            if document['method']=='POST' and isinstance(key,str) and 1<=len(key)<=500 and not any(ord(c)<32 for c in key):return
    elif kind=='source':
        op=document.get('operation')
        if op in ('prepare','reconcile_prepare') and set(document)=={'operation','target','evidence'}:
            target,_,_=source.validate_bundle(document['evidence'])
            if target==source.identity.target(document['target']):return
        if op in ('repair','reconcile') and set(document)=={'operation','key','payload'}:
            key,payload=document['key'],document['payload']
            if (isinstance(key,str) and 1<=len(key)<=500 and not any(ord(c)<32 for c in key)
                    and isinstance(payload,dict) and set(payload)=={'target','source_prepare'}
                    and isinstance(payload['source_prepare'],dict) and set(payload['source_prepare'])=={'event_key'}
                    and isinstance(payload['source_prepare']['event_key'],str)
                    and re.fullmatch('[0-9a-f]{64}',payload['source_prepare']['event_key'])):
                source.identity.target(payload['target']);return
    raise ValueError('request outside fixed bridge contract')


def _runner_cleanup_proven(value):
    """Only normal bounded returns prove this worker process group is gone."""
    return (type(value) is dict and set(value)=={'returncode','stdout','stderr','timed_out','overflow'}
            and type(value.get('returncode')) is int and isinstance(value.get('stdout'),bytes)
            and isinstance(value.get('stderr'),bytes) and type(value.get('timed_out')) is bool
            and type(value.get('overflow')) is bool and value['returncode']>=0
            and value['timed_out'] is False and value['overflow'] is False)


def _child(argv,input_bytes,*,timeout=MAX_SECONDS):
    """Use the installed, hash-verified bounded runner; unknown stays unknown."""
    env=provider._clean_env()
    for key in ('GH_CONFIG_DIR','GITHUB_CONFIG_DIR','GLAB_CONFIG_DIR','DYLD_INSERT_LIBRARIES','DYLD_LIBRARY_PATH'):
        env.pop(key,None)
    result=provider._source.run_command(argv,cwd='/',env=env,input_bytes=input_bytes,timeout=timeout)
    if (not isinstance(result,dict) or not isinstance(result.get('stdout'),bytes)
            or not isinstance(result.get('stderr'),bytes)):
        raise RuntimeError('child outcome unknown')
    if len(result['stdout'])+len(result['stderr'])>MAX_OUTPUT:
        return {**result,'overflow':True}
    return result


def _activation():
    """Read only an operator-installed, hash-pinned activation record."""
    if Path(__file__).resolve()!=HELPER or os.getuid()!=UID:raise RuntimeError('fixed GUI identity unavailable')
    value=json.loads(_read(ACTIVATION,16384))
    if (not isinstance(value,dict) or set(value)!={'schema','allowed_kinds','modules','interpreters'}
            or value['schema']!='fdisbull-gui-activation-1' or not isinstance(value['allowed_kinds'],list)
            or not value['allowed_kinds'] or len(set(value['allowed_kinds']))!=len(value['allowed_kinds'])
            or 'credential_probe' not in value['allowed_kinds']
            or not set(value['allowed_kinds'])<={'credential_probe','provider','source','canonical_read'}
            or not isinstance(value['modules'],dict) or set(value['modules'])!=MODULES
            or not isinstance(value['interpreters'],dict) or set(value['interpreters'])!={'provider','source'}):
        raise RuntimeError('GUI activation invalid')
    if (any(x.is_symlink() for x in (BRIDGE,*BRIDGE.parents)) or not BRIDGE.is_dir()
            or BRIDGE.stat().st_uid!=os.getuid() or BRIDGE.stat().st_mode&0o077):raise RuntimeError('GUI code root unsafe')
    for name,digest in value['modules'].items():
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise RuntimeError('GUI module pin invalid')
        if _digest(_read(BRIDGE/name,MAX_INPUT))!=digest:raise RuntimeError('GUI module changed')
    for kind,path in (('provider','/usr/bin/python3'),('source',SOURCE_PYTHON)):
        info=value['interpreters'][kind]
        if (not isinstance(info,dict) or set(info)!={'path','sha256'} or info['path']!=path
                or not isinstance(info['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',info['sha256'])):
            raise RuntimeError('GUI interpreter pin invalid')
        executable=Path(path).resolve(strict=True)
        with executable.open('rb') as stream:
            h=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        if h.hexdigest()!=info['sha256'] or kind=='source' and info['sha256']!=SOURCE_PYTHON_SHA256:
            raise RuntimeError('GUI interpreter changed')
    if Path(sys.executable).resolve()!=Path(SOURCE_PYTHON).resolve():raise RuntimeError('GUI caller interpreter differs')
    for path,digest in ((GH_BIN,GH_SHA256),('/bin/launchctl',LAUNCHCTL_SHA256)):
        with Path(path).resolve(strict=True).open('rb') as stream:
            h=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        if h.hexdigest()!=digest:raise RuntimeError('fixed executable changed')
    global provider,source
    if provider is None:provider=_load('production_transport.py')
    if source is None:source=_load('production_source_transport.py')
    if provider.GH_BIN!=GH_BIN or source.SOURCE_PYTHON!=SOURCE_PYTHON or source.SOURCE_PYTHON_SHA256!=SOURCE_PYTHON_SHA256:
        raise RuntimeError('installed helper pins differ')
    return value


def _aqua_session():
    """Use the system security-session graphic/remote flags, without keychain access."""
    try:
        if sys.platform!='darwin' or os.getuid()!=UID:return False
        api=ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security').SessionGetInfo
        api.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32)]
        api.restype=ctypes.c_int32
        session=ctypes.c_uint32();attributes=ctypes.c_uint32()
        return (api(0xffffffff,ctypes.byref(session),ctypes.byref(attributes))==0
                and session.value!=0 and bool(attributes.value&0x0010) and not attributes.value&0x1000)
    except (OSError,AttributeError):return False


def credential_availability(*,runner=None,timeout=15,activation_check=None):
    """Proposal-only account availability check; token output is discarded."""
    (activation_check or _activation)()
    runner=runner or provider._source.run_command
    env=provider._clean_env()
    for key in ('GH_CONFIG_DIR','GITHUB_CONFIG_DIR','DYLD_INSERT_LIBRARIES','DYLD_LIBRARY_PATH'):
        env.pop(key,None)
    try:
        result=runner([provider.GH_BIN,'auth','token','--user','seeker-cyber-maker','--hostname','github.com','--no-refresh'],
                      cwd='/',env=env,input_bytes=None,timeout=min(15,timeout))
        return {'available':isinstance(result,dict) and result.get('returncode')==0
                and result.get('timed_out') is False and result.get('overflow') is False
                and isinstance(result.get('stdout'),bytes) and bool(result['stdout'].strip())}
    except Exception:return {'available':False}


class GuiSpool:
    def __init__(self,spool=SPOOL,anchor=ANCHOR,*,mount=None,clock=time.time,kick=None,runner=None,activation=None,probe=None,gui_check=None,
                 handshake_seconds=10,monotonic=time.monotonic,sleep=time.sleep):
        self.spool=Path(spool);self.anchor=Path(anchor);self.mount=mount or _mount;self.clock=clock
        self.kick=kick or self._kick;self.runner=runner or _child
        self.activation=activation or _activation;self.probe=probe or credential_availability
        self.gui_check=gui_check or _aqua_session
        if type(handshake_seconds) not in (int,float) or not 0<=handshake_seconds<=10:raise ValueError('invalid handshake bound')
        self.handshake_seconds=handshake_seconds;self.monotonic=monotonic;self.sleep=sleep

    def _check(self):
        if not self.mount(self.spool,self.anchor):raise RuntimeError('CACHE mount unavailable')
        self.activation()
        if (any(x.is_symlink() for x in (self.spool,*self.spool.parents)) or not self.spool.is_dir()
                or self.spool.stat().st_uid!=os.getuid() or self.spool.stat().st_mode&0o077):raise RuntimeError('private spool unavailable')
        if (not self.anchor.parent.is_dir() or self.anchor.parent.stat().st_uid!=os.getuid()
                or self.anchor.parent.stat().st_mode&0o077):raise RuntimeError('private anchor unavailable')
        anchor_data=_read(self.anchor,4096)
        entries=list(self.spool.iterdir())
        if any(p.is_symlink() or not p.is_file() for p in entries):raise RuntimeError('invalid retained spool')
        if sum(p.stat().st_size for p in entries)+self.anchor.stat().st_size>MAX_RETAINED:
            raise RuntimeError('retention budget exceeded')
        marker=json.loads(_read(self.spool/'installation.json',4096))
        if marker!={'installation_id':INSTALLATION_ID,'volume_uuid':CACHE_UUID}:raise RuntimeError('installation mismatch')
        history=json.loads(_read(self.spool/'history.json',1024*1024));anchor=json.loads(anchor_data)
        if (not isinstance(history,dict) or set(history)!={'schema','sequence','requests'}
                or history['schema']!='fdisbull-gui-history-1' or type(history['sequence']) is not int or history['sequence']<0
                or not isinstance(history['requests'],dict) or len(history['requests'])>4096
                or history['sequence']<len(history['requests'])
                or anchor!={'installation_id':INSTALLATION_ID,'sequence':history['sequence'],'history_sha256':_digest(_bytes(history))}):
            raise RuntimeError('history or anchor mismatch')
        lock=self.spool/'lane.lock'
        _read(lock,4096)
        expected={'installation.json','history.json','lane.lock'}
        for request_id,entry in history['requests'].items():
            if not re.fullmatch('[0-9a-f]{64}',request_id) or not isinstance(entry,dict):raise RuntimeError('invalid history')
            phase=entry.get('phase');req=self.spool/(request_id+'.request')
            if phase not in ('submitted','started','complete','expired','reconciled-read','terminalunknown') or _digest(_read(req,MAX_INPUT))!=entry.get('request_sha256'):
                raise RuntimeError('request history changed')
            expected.add(req.name)
            if phase in ('started','complete','reconciled-read','terminalunknown'):
                started=self.spool/(request_id+'.started')
                if json.loads(_read(started,4096))!={'request_id':request_id,'request_sha256':entry['request_sha256']}:
                    raise RuntimeError('start history changed')
                expected.add(started.name)
            if phase in ('complete','expired','terminalunknown'):
                done=self.spool/(request_id+'.done')
                if _digest(_read(done,MAX_OUTPUT))!=entry.get('done_sha256'):raise RuntimeError('result history changed')
                value=json.loads(_read(done,MAX_OUTPUT))
                if phase=='terminalunknown' and (set(value) not in ({'status','request_id','reason'},
                                                                       {'status','request_id','reason','runner'})
                        or value.get('status')!='unknown' or value.get('request_id')!=request_id
                        or value.get('reason') not in ('runner_nonzero','runner_invalid_json',
                            'runner_error','runner_output_invalid','operator_reconciled_post_cleanup')):
                    raise RuntimeError('terminal unknown result changed')
                if 'runner' in value:
                    run=value['runner']
                    if (not isinstance(run,dict) or set(run)!={'returncode','timed_out','overflow'}
                            or type(run.get('returncode')) is not int or type(run.get('timed_out')) is not bool
                            or type(run.get('overflow')) is not bool):
                        raise RuntimeError('terminal runner summary invalid')
                expected.add(done.name)
            if phase=='reconciled-read':
                cert=self.spool/(request_id+'.read-reconciliation.json')
                content=_read(cert,16384)
                if _digest(content)!=entry.get('reconciliation_sha256'):raise RuntimeError('read reconciliation changed')
                value=json.loads(content)
                if (not isinstance(value,dict) or set(value)!={'schema','request_id','request_sha256','result','operator_receipt_sha256','operator_receipt_text'}
                        or value.get('schema')!='fdisbull-gui-read-reconciliation-1'
                        or value.get('request_id')!=request_id or value.get('request_sha256')!=entry.get('request_sha256')
                        or value.get('result')!='unknown' or not isinstance(value.get('operator_receipt_text'),str)
                        or _digest(value['operator_receipt_text'].encode('utf-8'))!=value.get('operator_receipt_sha256')):
                    raise RuntimeError('read reconciliation binding invalid')
                expected.add(cert.name)
            if phase=='terminalunknown' and 'reconciliation_sha256' in entry:
                cert=self.spool/(request_id+'.post-reconciliation.json')
                content=_read(cert,16384)
                if _digest(content)!=entry.get('reconciliation_sha256'):raise RuntimeError('post reconciliation changed')
                value=json.loads(content)
                if (not isinstance(value,dict) or set(value)!={'schema','request_id','request_sha256','result','operator_receipt_sha256','operator_receipt_text'}
                        or value.get('schema')!='fdisbull-gui-post-reconciliation-1'
                        or value.get('request_id')!=request_id or value.get('request_sha256')!=entry.get('request_sha256')
                        or value.get('result')!='unknown' or not isinstance(value.get('operator_receipt_text'),str)
                        or _digest(value['operator_receipt_text'].encode('utf-8'))!=value.get('operator_receipt_sha256')):
                    raise RuntimeError('post reconciliation binding invalid')
                expected.add(cert.name)
        if sum(v['phase'] in ('submitted','started') for v in history['requests'].values())>1:
            raise RuntimeError('multiple active spool lanes')
        actual={p.name for p in self.spool.iterdir()}
        if actual!=expected:raise RuntimeError('unrecognized or partial spool history')
        return history

    def _locked(self):
        # Check only stable acquisition prerequisites before waiting: the
        # ledger and its anchor may be between replacements under this lock.
        if not self.mount(self.spool,self.anchor):raise RuntimeError('CACHE mount unavailable')
        if (any(x.is_symlink() for x in (self.spool,*self.spool.parents)) or not self.spool.is_dir()
                or self.spool.stat().st_uid!=os.getuid() or self.spool.stat().st_mode&0o077):
            raise RuntimeError('private spool unavailable')
        lock=self.spool/'lane.lock'
        before=lock.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_mode&0o077
                or before.st_nlink!=1 or before.st_size>4096):raise RuntimeError('unsafe lane lock')
        fd=os.open(lock,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        stream=os.fdopen(fd,'r+')
        def check_lock():
            info=os.fstat(stream.fileno());path_info=lock.lstat()
            if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(path_info.st_mode)
                    or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_nlink!=1
                    or info.st_size>4096 or (info.st_dev,info.st_ino)!=(path_info.st_dev,path_info.st_ino)
                    or (info.st_dev,info.st_ino)!=(before.st_dev,before.st_ino)):
                raise RuntimeError('unsafe lane lock')
        try:
            check_lock()
            fcntl.flock(stream,fcntl.LOCK_EX)
            check_lock()
            self._check()
        except BaseException:stream.close();raise
        return stream

    def _save(self,history):
        data=_bytes(history)
        _replace(self.spool/'history.json',data)
        _replace(self.anchor,_bytes({'installation_id':INSTALLATION_ID,'sequence':history['sequence'],'history_sha256':_digest(data)}))
        self._check()

    def _kick(self,timeout=15):
        result=subprocess.run(['/bin/launchctl','kickstart','gui/501/'+LABEL],capture_output=True,timeout=timeout,check=False)
        if result.returncode!=0 or len(result.stdout)>65536 or len(result.stderr)>65536:
            raise RuntimeError('kickstart outcome unknown')

    def _expire_submitted(self,history,key,entry):
        # Caller holds the lane lock; no worker has crossed the started marker.
        done={'status':'expired','request_id':key};data=_bytes(done)
        _exclusive(self.spool/(key+'.done'),data);entry.update(phase='expired',done_sha256=_digest(data))
        history['sequence']+=1;self._save(history)
        return done

    def _start_handshake(self,key):
        # A prior launchd worker may still be exiting after publishing its
        # result. Wake the *same unstarted request* while time remains; never
        # kill a worker or reissue a provider operation. A failed/ambiguous kick
        # exits immediately, and every kick follows a successful predecessor.
        deadline=self.monotonic()+self.handshake_seconds
        while self.monotonic()<deadline:
            self.sleep(min(HANDSHAKE_INTERVAL,max(0,deadline-self.monotonic())))
            with self._locked():
                history=self._check();entry=history['requests'].get(key)
                if not isinstance(entry,dict):raise RuntimeError('submitted request unavailable')
                if entry.get('phase')!='submitted':return
                doc=json.loads(_read(self.spool/(key+'.request'),MAX_INPUT))
                if self.clock()>=doc['expires_epoch']:
                    self._expire_submitted(history,key,entry);return
                remaining=deadline-self.monotonic()
                if remaining<=0:return
                # Keep the lock across the non-destructive kick so no child can
                # cross the durable start boundary between the check and wake.
                if self.kick==self._kick:self.kick(timeout=min(2,remaining))
                else:self.kick()  # injectable test kick

    def submit(self,kind,document,expires_epoch,nonce):
        if kind not in self.activation().get('allowed_kinds',[]):raise RuntimeError('GUI kind not approved')
        _request(kind,document)
        now=self.clock()
        if (type(expires_epoch) not in (int,float) or not now<expires_epoch<=now+MAX_SECONDS):raise ValueError('invalid expiry')
        if not isinstance(nonce,str) or not re.fullmatch('[0-9a-f]{64}',nonce):raise ValueError('invalid request nonce')
        content=_bytes({'kind':kind,'request':document,'expires_epoch':expires_epoch,'nonce':nonce})
        if len(content)>MAX_INPUT or kind=='provider' and len(content)>PROVIDER_MAX_INPUT:raise ValueError('request exceeds bound')
        request_id=nonce
        with self._locked():
            history=self._check();old=history['requests'].get(request_id)
            if old is not None:
                if old['request_sha256']!=_digest(content):raise ValueError('request nonce conflicts')
                return {'status':'known','request_id':request_id,'phase':old['phase']}
            if any(item.get('phase') in ('submitted','started') for item in history['requests'].values()):raise RuntimeError('lane occupied')
            allocated=sum(p.stat().st_size for p in self.spool.iterdir() if p.is_file())+self.anchor.stat().st_size
            if allocated+len(content)+MAX_OUTPUT+2*1024*1024+65536>MAX_RETAINED:raise RuntimeError('retention budget exhausted')
            _exclusive(self.spool/(request_id+'.request'),content)
            history['requests'][request_id]={'phase':'submitted','request_sha256':_digest(content)}
            history['sequence']+=1;self._save(history)
        # Only successful kicks may be followed by a bounded wake handshake.
        # An ambiguous kick returns unknown without any further kick.
        try:
            self.kick()
            self._start_handshake(request_id)
        except Exception:return {'status':'unknown','request_id':request_id}
        return {'status':'pending','request_id':request_id}

    def result(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{64}',request_id):raise ValueError('invalid request id')
        with self._locked():
            history=self._check();item=history['requests'].get(request_id)
            if item is None:return {'status':'missing'}
            if item['phase'] in ('started','reconciled-read'):return {'status':'unknown','request_id':request_id}
            if item['phase']=='submitted':
                doc=json.loads(_read(self.spool/(request_id+'.request'),MAX_INPUT))
                if self.clock()>=doc['expires_epoch']:return self._expire_submitted(history,request_id,item)
                return {'status':'pending','request_id':request_id}
            return json.loads(_read(self.spool/(request_id+'.done'),MAX_OUTPUT))

    def reconcile_expired_read(self,receipt_path,receipt_sha256):
        """Operator-only: close a verified dead GET lane, preserving unknown outcome.

        This method is intentionally not exposed through main() or the GUI RPC.
        The caller independently collects and verifies the bounded process and
        launchctl evidence recorded in the private receipt.
        """
        if not isinstance(receipt_sha256,str) or not re.fullmatch('[0-9a-f]{64}',receipt_sha256):
            raise ValueError('operator receipt hash invalid')
        receipt_path=Path(receipt_path)
        if not receipt_path.is_absolute() or self.spool in receipt_path.parents:
            raise ValueError('operator receipt path invalid')
        receipt_bytes=_read(receipt_path,16384)
        if _digest(receipt_bytes)!=receipt_sha256:raise ValueError('operator receipt hash mismatch')
        receipt=json.loads(receipt_bytes)
        required={'schema','request_id','request_sha256','history_sequence','request_expiry','observed_epoch',
                  'helper_sha256','recovery_source_sha256','launchagent','process_scan','launchctl_evidence'}
        if not isinstance(receipt,dict) or set(receipt)!=required or receipt.get('schema')!='fdisbull-gui-read-cleanup-1':
            raise ValueError('operator receipt invalid')
        key=receipt['request_id'];now=self.clock()
        if (not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key)
                or not isinstance(receipt['request_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',receipt['request_sha256'])
                or type(receipt['history_sequence']) is not int
                or type(receipt['request_expiry']) not in (int,float) or type(receipt['observed_epoch']) not in (int,float)
                or not math.isfinite(receipt['request_expiry']) or not math.isfinite(receipt['observed_epoch'])
                or not receipt['request_expiry']<=receipt['observed_epoch']<=now
                or now-receipt['observed_epoch']>300):
            raise ValueError('operator receipt time or identity invalid')
        launch=receipt['launchagent'];scan=receipt['process_scan'];launch_evidence=receipt['launchctl_evidence']
        if (not isinstance(launch,dict) or set(launch)!={'label','runs','last_exit_code','running','pid'}
                or launch['label']!=LABEL or type(launch['runs']) is not int or launch['runs']<1
                or type(launch['last_exit_code']) is not int or launch['last_exit_code']!=0 or launch['running'] is not False or launch['pid'] is not None
                or not isinstance(scan,dict) or set(scan)!={'matched_children','path','sha256'}
                or type(scan['matched_children']) is not int or scan['matched_children']!=0
                or not isinstance(launch_evidence,dict) or set(launch_evidence)!={'path','sha256'}):
            raise ValueError('operator cleanup evidence invalid')
        for item in (scan,launch_evidence):
            path=Path(item['path']) if isinstance(item.get('path'),str) else Path('.')
            if (not path.is_absolute() or self.spool in path.parents or not isinstance(item.get('sha256'),str)
                    or not re.fullmatch('[0-9a-f]{64}',item['sha256'])
                    or _digest(_read(path,65536))!=item['sha256']):raise ValueError('operator evidence hash mismatch')
        with self._locked():
            history=self._check();entry=history['requests'].get(key)
            if (history['sequence']!=receipt['history_sequence'] or not isinstance(entry,dict)
                    or entry.get('phase')!='started' or entry.get('request_sha256')!=receipt['request_sha256']):
                raise ValueError('read history changed')
            doc=json.loads(_read(self.spool/(key+'.request'),MAX_INPUT));request=doc.get('request')
            if (doc.get('nonce')!=key or doc.get('kind')!='provider' or doc.get('expires_epoch')!=receipt['request_expiry']
                    or not isinstance(request,dict) or set(request)!={'operation','provider','method','path','payload'}
                    or request.get('operation')!='request' or request.get('method')!='GET' or request.get('payload') is not None):
                raise ValueError('not an expired provider GET')
            _request('provider',request)
            pins=self.activation().get('modules',{})
            if (not isinstance(pins,dict) or receipt['helper_sha256']!=pins.get('production_gui_transport.py')
                    or receipt['recovery_source_sha256']!=pins.get('recovery_source.py')
                    or any(not isinstance(receipt[k],str) or not re.fullmatch('[0-9a-f]{64}',receipt[k])
                           for k in ('helper_sha256','recovery_source_sha256'))):
                raise ValueError('cleanup source pin mismatch')
            cert={'schema':'fdisbull-gui-read-reconciliation-1','request_id':key,
                  'request_sha256':entry['request_sha256'],'result':'unknown',
                  'operator_receipt_sha256':receipt_sha256,'operator_receipt_text':receipt_bytes.decode('utf-8')}
            data=_bytes(cert)
            if len(data)>16384:raise ValueError('operator receipt too large')
            _exclusive(self.spool/(key+'.read-reconciliation.json'),data)
            entry.update(phase='reconciled-read',reconciliation_sha256=_digest(data))
            history['sequence']+=1;self._save(history)
            return {'status':'unknown','request_id':key,'reconciled':True}

    def _finish_unknown(self,request_id,reason,runner_result=None):
        if reason not in ('runner_nonzero','runner_invalid_json',
                          'runner_error','runner_output_invalid'):
            raise ValueError('unknown terminal reason invalid')
        with self._locked():
            history=self._check();entry=history['requests'].get(request_id)
            if not isinstance(entry,dict) or entry.get('phase')!='started':
                raise RuntimeError('start identity changed')
            done={'status':'unknown','request_id':request_id,'reason':reason}
            if runner_result is not None:
                if not _runner_cleanup_proven(runner_result):raise ValueError('runner cleanup record invalid')
                done['runner']={'returncode':runner_result['returncode'],'timed_out':runner_result['timed_out'],
                                'overflow':runner_result['overflow']}
            data=_bytes(done)
            _exclusive(self.spool/(request_id+'.done'),data)
            entry.update(phase='terminalunknown',done_sha256=_digest(data))
            history['sequence']+=1;self._save(history)
            return done

    def _verify_lost_post_bridge_record(self,receipt,bridge):
        expected_record=bridge.state/LOST_POST_RECORD_NAME
        if str(expected_record)!=receipt.get('bridge_record_path'):
            raise ValueError('historical bridge path mismatch')
        history=bridge._ensure()
        record_bytes=_read(expected_record,provider.MAX_INPUT)
        if _digest(record_bytes)!=LOST_POST_RECORD_SHA256:
            raise ValueError('historical bridge record changed')
        record=json.loads(record_bytes)
        if record!={'action_key':LOST_POST_ACTION_KEY,
                    'request_sha256':LOST_POST_ACTION_SHA256,'status':'unknown'}:
            raise ValueError('historical bridge action differs')
        if history.get('actions',{}).get(expected_record.name)!=LOST_POST_RECORD_SHA256:
            raise ValueError('historical bridge mirror differs')
        anchor_bytes=_read(bridge.anchor,1024*1024)
        if (history.get('sequence')!=receipt.get('bridge_anchor_sequence')
                or _digest(anchor_bytes)!=receipt.get('bridge_anchor_sha256')):
            raise ValueError('historical bridge anchor changed')

    def reconcile_expired_historical_post(self,receipt_path,receipt_sha256):
        """Close only the one lost historical retry POST; never infer acceptance."""
        if not isinstance(receipt_sha256,str) or not re.fullmatch('[0-9a-f]{64}',receipt_sha256):
            raise ValueError('operator receipt hash invalid')
        receipt_path=Path(receipt_path)
        if not receipt_path.is_absolute() or self.spool in receipt_path.parents:
            raise ValueError('operator receipt path invalid')
        receipt_bytes=_read(receipt_path,16384)
        if _digest(receipt_bytes)!=receipt_sha256:raise ValueError('operator receipt hash mismatch')
        receipt=json.loads(receipt_bytes)
        required={'schema','request_id','request_sha256','history_sequence','request_expiry','observed_epoch',
                  'helper_sha256','recovery_source_sha256','launchagent','process_scan','launchctl_evidence',
                  'bridge_action_key','bridge_request_sha256','bridge_record_path','bridge_record_sha256',
                  'bridge_anchor_sequence','bridge_anchor_sha256'}
        if not isinstance(receipt,dict) or set(receipt)!=required or receipt.get('schema')!='fdisbull-gui-post-cleanup-1':
            raise ValueError('operator receipt invalid')
        key=receipt['request_id'];now=self.clock()
        if (key!=LOST_POST_REQUEST_ID
                or not isinstance(receipt['request_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',receipt['request_sha256'])
                or type(receipt['history_sequence']) is not int
                or type(receipt['request_expiry']) not in (int,float) or type(receipt['observed_epoch']) not in (int,float)
                or not math.isfinite(receipt['request_expiry']) or not math.isfinite(receipt['observed_epoch'])
                or not receipt['request_expiry']<=receipt['observed_epoch']<=now
                or now-receipt['observed_epoch']>300):
            raise ValueError('operator receipt time or identity invalid')
        launch=receipt['launchagent'];scan=receipt['process_scan'];launch_evidence=receipt['launchctl_evidence']
        if (not isinstance(launch,dict) or set(launch)!={'label','runs','last_exit_code','running','pid'}
                or launch.get('label')!=LABEL or type(launch.get('runs')) is not int or launch['runs']<1
                or type(launch.get('last_exit_code')) is not int or launch['last_exit_code']!=0
                or launch.get('running') is not False or launch.get('pid') is not None
                or not isinstance(scan,dict) or set(scan)!={'matched_children','path','sha256'}
                or type(scan.get('matched_children')) is not int or scan['matched_children']!=0
                or not isinstance(launch_evidence,dict) or set(launch_evidence)!={'path','sha256'}):
            raise ValueError('operator cleanup evidence invalid')
        for item in (scan,launch_evidence):
            path=Path(item['path']) if isinstance(item.get('path'),str) else Path('.')
            if (not path.is_absolute() or self.spool in path.parents or not isinstance(item.get('sha256'),str)
                    or not re.fullmatch('[0-9a-f]{64}',item['sha256'])
                    or _digest(_read(path,65536))!=item['sha256']):
                raise ValueError('operator evidence hash mismatch')
        if (receipt.get('bridge_action_key')!=LOST_POST_ACTION_KEY
                or receipt.get('bridge_request_sha256')!=LOST_POST_ACTION_SHA256
                or receipt.get('bridge_record_sha256')!=LOST_POST_RECORD_SHA256
                or type(receipt.get('bridge_anchor_sequence')) is not int
                or not _is_sha256(receipt.get('bridge_anchor_sha256'))):
            raise ValueError('historical action binding mismatch')
        activation=self.activation()
        pins=activation.get('modules',{})
        if (not isinstance(pins,dict) or receipt['helper_sha256']!=pins.get('production_gui_transport.py')
                or receipt['recovery_source_sha256']!=pins.get('recovery_source.py')
                or any(not isinstance(receipt[k],str) or not re.fullmatch('[0-9a-f]{64}',receipt[k])
                       for k in ('helper_sha256','recovery_source_sha256'))):
            raise ValueError('cleanup source pin mismatch')
        if provider is None:raise RuntimeError('provider bridge unavailable')
        bridge=provider.ProviderBridge(provider.STATE_DIR,anchor_file=provider.ANCHOR_FILE)
        with self._locked():
            history=self._check();entry=history['requests'].get(key)
            if (history['sequence']!=receipt['history_sequence'] or not isinstance(entry,dict)
                    or entry.get('phase')!='started' or entry.get('request_sha256')!=receipt['request_sha256']):
                raise ValueError('read history changed')
            doc=json.loads(_read(self.spool/(key+'.request'),MAX_INPUT));request=doc.get('request')
            if (doc.get('nonce')!=key or doc.get('kind')!='provider' or doc.get('expires_epoch')!=receipt['request_expiry']
                    or not isinstance(request,dict)
                    or set(request)!={'operation','provider','method','path','payload','action_key'}
                    or request.get('operation')!='request' or request.get('provider')!='github'
                    or request.get('method')!='POST' or request.get('action_key')!=LOST_POST_ACTION_KEY):
                raise ValueError('not the historical retry POST')
            _request('provider',request)
            if provider.request_digest('github','POST',request['path'],request['payload'])!=LOST_POST_ACTION_SHA256:
                raise ValueError('historical retry request digest differs')
            with bridge._bridge_lock():
                self._verify_lost_post_bridge_record(receipt,bridge)
                latest=self.clock()
                if latest<receipt['observed_epoch'] or latest-receipt['observed_epoch']>300:
                    raise ValueError('operator cleanup evidence expired while waiting')
                done={'status':'unknown','request_id':key,'reason':'operator_reconciled_post_cleanup'}
                data=_bytes(done)
                _exclusive(self.spool/(key+'.done'),data)
                cert={'schema':'fdisbull-gui-post-reconciliation-1','request_id':key,
                      'request_sha256':entry['request_sha256'],'result':'unknown',
                      'operator_receipt_sha256':receipt_sha256,'operator_receipt_text':receipt_bytes.decode('utf-8')}
                cert_bytes=_bytes(cert)
                if len(cert_bytes)>16384:raise ValueError('operator receipt too large')
                _exclusive(self.spool/(key+'.post-reconciliation.json'),cert_bytes)
                entry.update(phase='terminalunknown',done_sha256=_digest(data),
                             reconciliation_sha256=_digest(cert_bytes))
                history['sequence']+=1;self._save(history)
                return done

    def worker(self):
        if self.gui_check() is not True:raise RuntimeError('Aqua session unavailable')
        with self._locked():
            history=self._check();pending=[(k,v) for k,v in history['requests'].items() if v['phase']=='submitted']
            if len(pending)!=1:return {'status':'idle'}
            key,entry=pending[0];request_path=self.spool/(key+'.request');doc=json.loads(_read(request_path,MAX_INPUT))
            if set(doc)!={'kind','request','expires_epoch','nonce'} or doc['nonce']!=key:raise ValueError('invalid submitted envelope')
            _request(doc['kind'],doc['request'])
            if doc['kind'] not in self.activation().get('allowed_kinds',[]):raise RuntimeError('GUI kind not approved')
            if self.clock()>=doc['expires_epoch']:
                return self._expire_submitted(history,key,entry)
            _exclusive(self.spool/(key+'.started'),_bytes({'request_id':key,'request_sha256':entry['request_sha256']}))
            entry['phase']='started';history['sequence']+=1;self._save(history)
        # Child input is the exact validated request only, never a shell command.
        # Keep original envelope immutable; create a separate bounded input file.
        # Existing helpers read a single JSON object from stdin.
        targets={'provider':'production_transport.py','source':'production_source_transport.py',
                 'canonical_read':'production_held_reconcile.py','credential_probe':'production_transport.py'}
        command=[('/usr/bin/python3' if doc['kind']=='provider' else SOURCE_PYTHON),'-I',
                 str(BRIDGE/targets[doc['kind']])]
        cleanup_proven=False;terminal_reason=None
        try:
            self._check()
            remaining=doc['expires_epoch']-self.clock()
            if remaining<=0:raise RuntimeError('request expired before child')
            if doc['kind']=='credential_probe':
                value=self.probe(timeout=min(15,remaining))
                if not isinstance(value,dict) or set(value)!={'available'} or type(value['available']) is not bool:
                    raise RuntimeError('credential probe outcome unknown')
                outcome={'returncode':0,'stdout':_bytes(value),'stderr':b'',
                         'timed_out':False,'overflow':False}
            else:
                outcome=self.runner(command,_bytes(doc['request']),timeout=min(MAX_SECONDS,remaining))
            cleanup_proven=_runner_cleanup_proven(outcome)
            if not cleanup_proven:raise RuntimeError('child result unknown')
            if len(outcome['stdout'])+len(outcome['stderr'])>MAX_OUTPUT:
                terminal_reason='runner_output_invalid'
            elif outcome['returncode']!=0:terminal_reason='runner_nonzero'
            if terminal_reason is not None:
                return self._finish_unknown(key,terminal_reason,outcome)
            try:value=json.loads(outcome['stdout'])
            except (ValueError,UnicodeError):
                return self._finish_unknown(key,'runner_invalid_json',outcome)
            if not isinstance(value,dict) or 'error' in value:
                return self._finish_unknown(key,'runner_error',outcome)
            done={'status':'complete','request_id':key,'result':value}
            data=_bytes(done)
            if len(data)>MAX_OUTPUT:
                return self._finish_unknown(key,'runner_output_invalid',outcome)
        except Exception:
            # A thrown runner exception does not prove its owned process group
            # has been reaped. Keep the lane held for local reconciliation.
            return {'status':'unknown','request_id':key}
        with self._locked():
            history=self._check();entry=history['requests'].get(key)
            if not entry or entry.get('phase')!='started':raise RuntimeError('start identity changed')
            _exclusive(self.spool/(key+'.done'),data);entry.update(phase='complete',done_sha256=_digest(data))
            history['sequence']+=1;self._save(history)
        return {'status':'complete','request_id':key}


def main(argv=None):
    try:
        args=list(sys.argv[1:] if argv is None else argv)
        if args==['worker']:
            result=GuiSpool().worker()
        elif args==['request']:
            raw=sys.stdin.buffer.read(MAX_INPUT+1)
            if len(raw)>MAX_INPUT:raise ValueError('request too large')
            doc=json.loads(raw)
            if not isinstance(doc,dict):raise ValueError('invalid request')
            if set(doc)=={'operation','kind','request','expires_epoch','nonce'} and doc['operation']=='submit':
                result=GuiSpool().submit(doc['kind'],doc['request'],doc['expires_epoch'],doc['nonce'])
            elif set(doc)=={'operation','request_id'} and doc['operation']=='result':
                result=GuiSpool().result(doc['request_id'])
            else:raise ValueError('unsupported operation')
        else:raise ValueError('unsupported invocation')
        print(json.dumps(result,separators=(',',':')))
        return 0
    except Exception:
        print('{"error":"gui_transport_unavailable"}')
        return 1


if __name__=='__main__':sys.exit(main())
