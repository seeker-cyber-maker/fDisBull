"""Proposed finite Aqua-session CI bridge; no listener, timer, or auto-install.

Installation, launchd activation and use are separate operator decisions. A
submitted request is never relaunched after an uncertain kickstart or start.
"""
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
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
         'recovery_source.py','ci_status.py'}
UID=501
GH_SHA256='258d12a00ca7939294c4b9a977eae72dc74882f8c4293012126f8d2da27e9d2e'
LAUNCHCTL_SHA256='c09fb522287bee5483d281ccd145fda129cd5eba940e5716cc4a2f25c18299e3'
MAX_INPUT=32*1024*1024
MAX_OUTPUT=2*1024*1024
MAX_RETAINED=64*1024*1024
MAX_SECONDS=600


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
            or not set(value['allowed_kinds'])<={'credential_probe','provider','source'}
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
    def __init__(self,spool=SPOOL,anchor=ANCHOR,*,mount=None,clock=time.time,kick=None,runner=None,activation=None,probe=None,gui_check=None):
        self.spool=Path(spool);self.anchor=Path(anchor);self.mount=mount or _mount;self.clock=clock
        self.kick=kick or self._kick;self.runner=runner or _child
        self.activation=activation or _activation;self.probe=probe or credential_availability
        self.gui_check=gui_check or _aqua_session

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
            if phase not in ('submitted','started','complete','expired') or _digest(_read(req,MAX_INPUT))!=entry.get('request_sha256'):
                raise RuntimeError('request history changed')
            expected.add(req.name)
            if phase in ('started','complete'):
                started=self.spool/(request_id+'.started')
                if json.loads(_read(started,4096))!={'request_id':request_id,'request_sha256':entry['request_sha256']}:
                    raise RuntimeError('start history changed')
                expected.add(started.name)
            if phase in ('complete','expired'):
                done=self.spool/(request_id+'.done')
                if _digest(_read(done,MAX_OUTPUT))!=entry.get('done_sha256'):raise RuntimeError('result history changed')
                expected.add(done.name)
        if sum(v['phase'] in ('submitted','started') for v in history['requests'].values())>1:
            raise RuntimeError('multiple active spool lanes')
        actual={p.name for p in self.spool.iterdir()}
        if actual!=expected:raise RuntimeError('unrecognized or partial spool history')
        return history

    def _locked(self):
        self._check()
        fd=os.open(self.spool/'lane.lock',os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        stream=os.fdopen(fd,'r+');fcntl.flock(stream,fcntl.LOCK_EX)
        try:self._check()
        except BaseException:stream.close();raise
        return stream

    def _save(self,history):
        data=_bytes(history)
        _replace(self.spool/'history.json',data)
        _replace(self.anchor,_bytes({'installation_id':INSTALLATION_ID,'sequence':history['sequence'],'history_sha256':_digest(data)}))
        self._check()

    def _kick(self):
        result=subprocess.run(['/bin/launchctl','kickstart','gui/501/'+LABEL],capture_output=True,timeout=15,check=False)
        if result.returncode!=0 or len(result.stdout)>65536 or len(result.stderr)>65536:
            raise RuntimeError('kickstart outcome unknown')

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
        # Never repeat kickstart after an ambiguous response. The request remains
        # submitted even if launchctl raises or the caller disconnects.
        try:self.kick()
        except Exception:return {'status':'unknown','request_id':request_id}
        return {'status':'pending','request_id':request_id}

    def result(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{64}',request_id):raise ValueError('invalid request id')
        with self._locked():
            history=self._check();item=history['requests'].get(request_id)
            if item is None:return {'status':'missing'}
            if item['phase']=='started':return {'status':'unknown','request_id':request_id}
            if item['phase']=='submitted':return {'status':'pending','request_id':request_id}
            return json.loads(_read(self.spool/(request_id+'.done'),MAX_OUTPUT))

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
                done={'status':'expired','request_id':key};data=_bytes(done)
                _exclusive(self.spool/(key+'.done'),data);entry.update(phase='expired',done_sha256=_digest(data))
                history['sequence']+=1;self._save(history);return done
            _exclusive(self.spool/(key+'.started'),_bytes({'request_id':key,'request_sha256':entry['request_sha256']}))
            entry['phase']='started';history['sequence']+=1;self._save(history)
        # Child input is the exact validated request only, never a shell command.
        # Keep original envelope immutable; create a separate bounded input file.
        # Existing helpers read a single JSON object from stdin.
        command=[('/usr/bin/python3' if doc['kind']=='provider' else SOURCE_PYTHON),'-I',
                 str(BRIDGE/('production_transport.py' if doc['kind']=='provider' else 'production_source_transport.py'))]
        try:
            self._check()
            remaining=doc['expires_epoch']-self.clock()
            if remaining<=0:raise RuntimeError('request expired before child')
            if doc['kind']=='credential_probe':
                value=self.probe(timeout=min(15,remaining))
                if not isinstance(value,dict) or set(value)!={'available'} or type(value['available']) is not bool:
                    raise RuntimeError('credential probe outcome unknown')
                outcome={'returncode':0,'stdout':_bytes(value),'timed_out':False,'overflow':False}
            else:
                outcome=self.runner(command,_bytes(doc['request']),timeout=min(MAX_SECONDS,remaining))
            if (not isinstance(outcome,dict) or outcome.get('returncode')!=0 or outcome.get('timed_out') is not False
                    or outcome.get('overflow') is not False or not isinstance(outcome.get('stdout'),bytes)
                    or len(outcome['stdout'])>MAX_OUTPUT):raise RuntimeError('child result unknown')
            value=json.loads(outcome['stdout'])
            if not isinstance(value,dict) or 'error' in value:raise RuntimeError('child result unknown')
            done={'status':'complete','request_id':key,'result':value}
            data=_bytes(done)
            if len(data)>MAX_OUTPUT:raise RuntimeError('result exceeds bound')
        except Exception:
            # A child may have mutated the provider before its result was lost.
            # Preserve started without done forever; the caller reconciles.
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
