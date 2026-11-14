#!/usr/bin/env python3
"""Stage, verify, activate or roll back an evidence-bound fDisBull prefix.

This command only acts when explicitly invoked. Input JSON schema
fdisbull-system-install-input-1 binds every input by absolute path, size and
SHA-256; see validate_input for its closed fields. Native qualification is an
independent prerequisite, not something this installer synthesizes.
"""
from __future__ import annotations
import argparse
import contextlib
from email.parser import BytesParser
from email.policy import default
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import zipfile

DEFAULT_BASE=Path('/Users/Shared/fDisBull')
SHA=re.compile(r'[0-9a-f]{40}\Z')
HASH=re.compile(r'[0-9a-f]{64}\Z')
VERSION=re.compile(r'[0-9]+\.[0-9]+\.[0-9]+\Z')
FORBIDDEN={'.fdb','.sav','.state','.sqlite','.sqlite3','.db'}
PROFILES={'dosbox-stable','dosbox-layers','qemu-machine','wine-pe64','wine-pe32','win16'}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe_regular(path):
    p=Path(path)
    if (not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file()
            or p.suffix.lower() in FORBIDDEN):raise ValueError('absolute regular non-state input required')
    return p


def reference(ref):
    if (not isinstance(ref,dict) or set(ref)!={'path','size','sha256'} or type(ref['size']) is not int
            or ref['size']<0 or not HASH.fullmatch(str(ref['sha256']))):raise ValueError('invalid input reference')
    path=safe_regular(ref['path'])
    if path.stat().st_size!=ref['size'] or digest(path)!=ref['sha256']:raise ValueError('input identity mismatch')
    return path


def read_json(path):
    path=safe_regular(path)
    if path.stat().st_size>4*1024*1024:raise ValueError('JSON exceeds bound')
    obj=json.loads(path.read_bytes())
    if not isinstance(obj,dict):raise ValueError('JSON object required')
    return obj


def relative(value):
    if not isinstance(value,str) or not value or '\\' in value:raise ValueError('invalid relative destination')
    path=PurePosixPath(value)
    if path.is_absolute() or str(path)!=value or any(p in ('','.','..') or p.startswith('.') for p in value.split('/')):raise ValueError('unsafe relative destination')
    if path.suffix.lower() in FORBIDDEN:raise ValueError('private database or state not installable')
    return value


def _linked_ci(path,ref):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256','size'}:raise ValueError('CI inventory reference missing')
    name=relative(ref['path']); p=path.parent/name
    if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(path.parent.resolve()):raise ValueError('CI inventory path unsafe')
    if p.stat().st_size!=ref['size'] or digest(p)!=ref['sha256']:raise ValueError('CI inventory changed')
    return read_json(p)


def _tool_entries(z):
    seen=set();total=0;root=None
    for item in z.infolist():
        name=item.filename.rstrip('/');parts=name.split('/')
        if (not name or name in seen or '\\' in name or any(x in ('','.','..') for x in parts)
                or any(x.startswith('.') and x not in ('.github','.gitlab-ci.yml') for x in parts) or PurePosixPath(name).is_absolute()
                or stat.S_IFMT(item.external_attr>>16) not in (0,stat.S_IFREG,stat.S_IFDIR)
                or PurePosixPath(name).suffix.lower() in FORBIDDEN):raise ValueError('unsafe tool archive member')
        seen.add(name);root=root or parts[0]
        if parts[0]!=root or not root.startswith('fdisbull-'):raise ValueError('tool archive root invalid')
        total+=item.file_size
        if total>2_000_000_000:raise ValueError('tool archive exceeds bound')
    if not root or not {root+'/scripts/verify_system_install.py',root+'/scripts/check_local_install.py'}<=seen:
        raise ValueError('source bundle lacks system verification tools')
    return root


def validate_input(path):
    doc=read_json(path)
    fields={'schema','source_commit','version','artifacts','dependencies','backends','resources','proofs','native_log_root'}
    if (set(doc)!=fields or doc['schema']!='fdisbull-system-install-input-1'
            or not SHA.fullmatch(str(doc['source_commit'])) or not VERSION.fullmatch(str(doc['version']))):raise ValueError('input manifest schema or identity invalid')
    source=doc['source_commit'];version=doc['version']
    artifacts=doc['artifacts']
    if not isinstance(artifacts,dict) or set(artifacts)!={'core','player','sdist','tool'}:raise ValueError('four artifact roles required')
    artifact_paths={k:reference(v) for k,v in artifacts.items()}
    if len({p.name for p in artifact_paths.values()})!=4:raise ValueError('artifact names collide')
    if (artifact_paths['core'].suffix!='.whl' or artifact_paths['player'].suffix!='.whl'
            or not artifact_paths['sdist'].name.endswith('.tar.gz') or artifact_paths['tool'].suffix!='.zip'):
        raise ValueError('artifact formats invalid')
    with zipfile.ZipFile(artifact_paths['tool']) as z:
        root=_tool_entries(z)
        if root!='fdisbull-'+version:raise ValueError('tool source version differs')
        for helper in ('verify_system_install.py','check_local_install.py'):
            local=Path(__file__).with_name(helper)
            info=z.getinfo(root+'/scripts/'+helper)
            if info.file_size>2*1024*1024 or not local.is_file() or z.read(info)!=local.read_bytes():
                raise ValueError('source bundle verification helper differs')
    with tarfile.open(artifact_paths['sdist'],'r:gz') as tar:
        metadata_path='fdisbull-'+version+'/PKG-INFO'
        matches=[m for m in tar.getmembers() if m.name==metadata_path and m.isfile()]
        if len(matches)!=1 or matches[0].size>2*1024*1024:raise ValueError('sdist metadata missing')
        metadata=BytesParser(policy=default).parsebytes(tar.extractfile(matches[0]).read())
        if metadata.get('Name')!='fdisbull' or metadata.get('Version')!=version:raise ValueError('sdist version or distribution differs')
    for role,expected in [('core','fdisbull'),('player','fdisbull-player')]:
        with zipfile.ZipFile(artifact_paths[role]) as z:
            names=[n for n in z.namelist() if n.endswith('.dist-info/METADATA') and n.count('/')==1]
            if len(names)!=1:raise ValueError('wheel metadata missing')
            metadata=BytesParser(policy=default).parsebytes(z.read(names[0]))
            normalized=re.sub(r'[-_.]+','-',str(metadata.get('Name',''))).lower()
            if normalized!=expected or metadata.get('Version')!=version:raise ValueError('wheel version or distribution differs')
    deps=doc['dependencies']
    if not isinstance(deps,list) or not deps:raise ValueError('pinned dependency wheels required')
    dep_paths=[]
    for dep in deps:
        if not isinstance(dep,dict) or set(dep)!={'wheel','pypi_identity'}:raise ValueError('dependency provenance required')
        wheel=reference(dep['wheel']); proof=read_json(reference(dep['pypi_identity']))
        rows=proof.get('files',[])
        matches=[row for row in rows if isinstance(row,dict) and row.get('filename')==wheel.name]
        if (wheel.suffix!='.whl' or proof.get('schema')!='fdisbull-retained-third-party-wheel-pypi-identity-v1'
                or len(matches)!=1 or matches[0].get('metadata_match') is not True or matches[0].get('yanked') is not False
                or matches[0].get('packagetype')!='bdist_wheel'
                or not str(matches[0].get('pypi_file_url','')).startswith('https://files.pythonhosted.org/')
                or not str(matches[0].get('pypi_release_api','')).startswith('https://pypi.org/pypi/')
                or matches[0].get('pypi_sha256')!=dep['wheel']['sha256']
                or matches[0].get('pypi_size')!=dep['wheel']['size']):raise ValueError('dependency PyPI identity mismatch')
        dep_paths.append(wheel)
    if len({p.name for p in dep_paths})!=len(dep_paths):raise ValueError('dependency wheel names collide')
    backends=doc['backends'];resources=doc['resources']
    if not isinstance(backends,dict) or not backends or not isinstance(resources,list) or not resources:raise ValueError('declared native inputs required')
    for name,ref in backends.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',name):raise ValueError('invalid backend name')
        reference(ref)
    destinations=set()
    for item in resources:
        if not isinstance(item,dict) or set(item)!={'destination','input'}:raise ValueError('resource entry invalid')
        name=relative(item['destination'])
        if not name.startswith('resources/') or name in destinations:raise ValueError('resource destination invalid')
        destinations.add(name);reference(item['input'])
    proofs=doc['proofs']
    if not isinstance(proofs,dict) or set(proofs)!={'ci','release','delivery','native'}:raise ValueError('four qualification proofs required')
    proof_paths={k:reference(v) for k,v in proofs.items()}; ci,release,delivery,native=(read_json(proof_paths[k]) for k in ('ci','release','delivery','native'))
    if ci.get('schema')!='fdisbull-ci-qualification-1' or ci.get('status')!='qualified' or ci.get('source_commit')!=source:raise ValueError('CI qualification differs')
    inventory=_linked_ci(proof_paths['ci'],ci.get('package_inventory'))
    if inventory.get('schema')!='fdisbull-package-payloads-1' or inventory.get('source_commit')!=source or inventory.get('tracked_worktree_dirty') is not False:raise ValueError('CI package inventory invalid')
    if not isinstance(inventory.get('artifacts'),dict) or set(inventory['artifacts'])!={'core','player','sdist','tool'}:raise ValueError('CI package inventory incomplete')
    for role,ref in artifacts.items():
        row=inventory.get('artifacts',{}).get(role,{})
        if (row.get('name'),row.get('size_bytes'),row.get('sha256'))!=(artifact_paths[role].name,ref['size'],ref['sha256']):raise ValueError('CI artifact differs: '+role)
    tag='v'+version;expected_release='https://github.com/seeker-cyber-maker/fDisBull/releases/tag/'+tag
    if (release.get('schema')!='fdisbull-production-release-result-1' or release.get('status')!='complete'
            or release.get('source_sha')!=source or release.get('tag')!=tag or release.get('release_url')!=expected_release
            or not isinstance(release.get('download_url'),str) or not release['download_url'].startswith('https://release.brewsterjennings.ca/ci-')):raise ValueError('published pipeline result invalid')
    delivery_ref=release.get('delivery_receipt',{})
    if not isinstance(delivery_ref.get('path'),str) or delivery_ref.get('sha256')!=proofs['delivery']['sha256']:raise ValueError('pipeline delivery reference differs')
    if (delivery.get('schema')!='fdisbull-cdn-delivery-1' or delivery.get('status')!='passed'
            or delivery.get('source_sha')!=source or delivery.get('url')!=release['download_url']
            or not HASH.fullmatch(str(delivery.get('sha256'))) or delivery.get('full_sha256')!=delivery.get('sha256')
            or delivery.get('resume_sha256')!=delivery.get('sha256') or type(delivery.get('resume_offset')) is not int
            or delivery['resume_offset']<=0):raise ValueError('CDN receipt invalid')
    if (native.get('schema')!='fdisbull-macos-native-qualification-1' or native.get('status')!='passed'
            or native.get('source_commit')!=source or native.get('version')!=version or native.get('platform')!='darwin' or native.get('architecture')!='arm64'
            or native.get('backends')!={k:v['sha256'] for k,v in backends.items()}
            or native.get('resources')!={v['destination']:v['input']['sha256'] for v in resources}):raise ValueError('native qualification identity differs')
    build=native.get('build_receipts')
    if not isinstance(build,dict) or set(build)!=set(backends):raise ValueError('native backend build receipts missing')
    for name,row in build.items():
        if (not isinstance(row,dict) or row.get('artifact_sha256')!=backends[name]['sha256']
                or not HASH.fullmatch(str(row.get('upstream_sha256')))
                or (row.get('patch_sha256') is not None and not HASH.fullmatch(str(row.get('patch_sha256'))))
                or ('dosbox' in name.lower() and not HASH.fullmatch(str(row.get('patch_sha256'))))
                or not isinstance(row.get('commands'),list) or not row['commands']):raise ValueError('native build chain invalid')
        for command in row['commands']:
            if (not isinstance(command,dict) or not isinstance(command.get('argv'),list) or not command['argv']
                    or any(not isinstance(x,str) or not x for x in command['argv'])
                    or type(command.get('returncode')) is not int or command['returncode']!=0):raise ValueError('native build command invalid')
    log_root=Path(doc['native_log_root'])
    if not log_root.is_absolute() or any(p.is_symlink() for p in (log_root,*log_root.parents)) or not log_root.is_dir():raise ValueError('native log root invalid')
    commands=native.get('commands')
    if not isinstance(commands,list) or not commands:raise ValueError('native command evidence required')
    native_count=0;covered=set()
    for row in commands:
        if (not isinstance(row,dict) or not isinstance(row.get('argv'),list) or not row['argv']
                or any(not isinstance(x,str) or not x for x in row['argv']) or type(row.get('returncode')) is not int
                or row['returncode']!=0 or type(row.get('native_cases')) is not int or row['native_cases']<=0):raise ValueError('native command evidence invalid')
        profiles=row.get('profiles')
        if (not isinstance(profiles,list) or not profiles or any(not isinstance(x,str) for x in profiles)
                or len(set(profiles))!=len(profiles) or not set(profiles)<=PROFILES
                or row['native_cases']<len(profiles)):raise ValueError('native profile evidence invalid')
        covered.update(profiles)
        for key in ('stdout','stderr'):
            ref=row.get(key)
            if not isinstance(ref,dict) or set(ref)!={'path','size','sha256'}:raise ValueError('native command log reference invalid')
            name=relative(ref['path'])
            if not name.startswith('share/native-logs/'):raise ValueError('native command log destination invalid')
            reference({**ref,'path':str(log_root/name)})
        native_count+=row['native_cases']
    if native_count<=0 or covered!=PROFILES:raise ValueError('native profile coverage incomplete')
    spec=importlib.util.spec_from_file_location('fdisbull_install_proof_verifier',Path(__file__).with_name('verify_system_install.py'))
    if spec is None or spec.loader is None:raise ValueError('system proof verifier unavailable')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.validate_proofs({'ci':ci,'native':native,'release':release,'delivery':delivery},
                             version,source,{k:v['sha256'] for k,v in backends.items()},
                             {v['destination']:v['input']['sha256'] for v in resources})
    return doc


def _write(path, value, *, replace=False):
    data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    name=path.with_name('.'+path.name+'.'+uuid.uuid4().hex) if replace else path
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o644)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if replace:os.replace(name,path)
    fd=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)


def _copy(ref,destination,*,executable=False):
    source=reference(ref);destination.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o755 if executable else 0o644)
    with source.open('rb') as src,os.fdopen(fd,'wb') as dst:
        shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
    if destination.stat().st_size!=ref['size'] or digest(destination)!=ref['sha256'] or digest(source)!=ref['sha256']:
        raise ValueError('copied input changed')
    return {'path':str(destination),'sha256':ref['sha256']}


def _extract_tool(archive,destination):
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        root=_tool_entries(z)
        for item in z.infolist():
            name=item.filename.rstrip('/');parts=name.split('/')
            target=destination.joinpath(*parts)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            target.chmod(0o644)
    verifier=destination/root/'scripts/verify_system_install.py';checker=destination/root/'scripts/check_local_install.py'
    if not verifier.is_file() or not checker.is_file():raise ValueError('source bundle lacks system verification tools')
    return verifier,checker


def _env(work):
    return {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
            'PIP_NO_INDEX':'1','PIP_NO_CACHE_DIR':'1','PIP_CONFIG_FILE':'/dev/null',
            'FDISBULL_TARGET_STORE':str(work/'target-store'),
            'FDISBULL_OUTPUT_ARTIFACT_DIR':str(work/'artifacts'),'TMPDIR':str(work/'tmp')}


def _run(argv,work,*,timeout=300,json_output=False,capture=False):
    process=subprocess.Popen([str(x) for x in argv],cwd=work,env=_env(work),stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    sel=selectors.DefaultSelector();buffers={process.stdout:bytearray(),process.stderr:bytearray()}
    for stream in buffers:sel.register(stream,selectors.EVENT_READ)
    deadline=time.monotonic()+timeout
    try:
        while sel.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('verification command timed out')
            for key,_ in sel.select(min(1,remaining)):
                block=os.read(key.fileobj.fileno(),65536)
                if not block:sel.unregister(key.fileobj);continue
                buffers[key.fileobj].extend(block)
                if len(buffers[key.fileobj])>1024*1024:raise ValueError('verification output too large')
        if process.wait(timeout=max(.01,deadline-time.monotonic()))!=0:raise ValueError('command failed: '+str(argv[0]))
    except BaseException:
        # A finished leader can leave children holding either output pipe.
        # This process created the session; drain its exact group regardless
        # of leader liveness rather than leaving those children behind.
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();raise
    finally:
        sel.close();process.stdout.close();process.stderr.close()
    stdout=bytes(buffers[process.stdout])
    if json_output:
        obj=json.loads(stdout)
        if not isinstance(obj,dict):raise ValueError('command returned invalid JSON')
        return obj
    return stdout if capture else None


def _workspace(base):
    root=base/'checks';root.mkdir(mode=0o700,exist_ok=True)
    if root.is_symlink() or not root.is_dir():raise ValueError('private check root unavailable')
    work=Path(tempfile.mkdtemp(prefix='candidate-',dir=root));work.chmod(0o700)
    for name in ('tmp','target-store','artifacts'): (work/name).mkdir(mode=0o700)
    return work


def _cli_probe(prefix,base):
    work=_workspace(base);code=bytes.fromhex('b81300cd100e1f30e4cd16a20001ebfe')+bytes(1024)
    header=bytearray(32);header[:2]=b'MZ';size=32+len(code)
    struct.pack_into('<13H',header,2,*[size%512,(size+511)//512,0,2,0,0xffff,0,0x400,0,0,0,0x1c,0])
    target=work/'authored.exe';target.write_bytes(header+code);project=work/'intake.fdb'
    cli=prefix/'venv/bin/fdisbull'; values=[]
    for args in (['import',str(target),str(project)],['analyze',str(project),'--max-instructions','64'],['status',str(project)]):
        value=_run([cli,*args],work,timeout=60,json_output=True)
        if value.get('ok') is not True:raise ValueError('candidate CLI intake failed')
        values.append(value)
    counts=values[-1].get('result',{}).get('counts',{})
    if not project.is_file() or type(counts.get('instructions')) is not int or counts['instructions']<1:raise ValueError('candidate CLI persisted analysis missing')
    return {'status':'passed','workspace':str(work),'fixture_sha256':digest(target),'persisted_instructions':counts['instructions']}


def _verify(prefix,base,*,active_required=False,activation_precheck=False):
    work=_workspace(base)
    manifest=prefix/'share/install-manifest.json';verifier=prefix/'share/verify-system.py'
    argv=[prefix/'venv/bin/python','-B','-I',verifier,'--prefix',prefix,'--manifest',manifest]
    if activation_precheck:argv.append('--activation-precheck')
    result=_run(argv,work,timeout=300,json_output=True)
    expected='prechecked' if activation_precheck else 'passed'
    if (result.get('status')!=expected or (active_required and result.get('active_default') is not True)
            or activation_precheck and (result.get('selected_default') is not True or result.get('active_default') is not False)):
        raise ValueError('system verifier rejected candidate')
    return {'verifier':result,'cli':_cli_probe(prefix,base)}


def _inventory(prefix):
    excluded={'INSTALLATION.json','PAYLOAD.json','share/install-manifest.json'};result={}
    for p in sorted(prefix.rglob('*')):
        if p.is_symlink() or not p.is_file():continue
        name=p.relative_to(prefix).as_posix()
        if name in excluded or p.suffix=='.pyc' or '__pycache__' in p.parts:continue
        result[name]={'size':p.stat().st_size,'sha256':digest(p)}
    return result


def _base(value,*,create=False):
    base=Path(value).expanduser().absolute()
    if any(p.is_symlink() for p in (base,*base.parents)):raise ValueError('base path contains symlink')
    if create:base.mkdir(mode=0o755,parents=False,exist_ok=True)
    if not base.is_dir():raise ValueError('installation base unavailable')
    for p in (base,*base.parents):
        if (p/'.git').exists():raise ValueError('installation base must be outside Git')
    return base


@contextlib.contextmanager
def _lock(base):
    fd=os.open(base/'.install.lock',os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def stage(input_path,base):
    doc=validate_input(input_path);base=_base(base,create=True)
    with _lock(base):
        doc=validate_input(input_path)
        releases=base/'releases';releases.mkdir(mode=0o755,exist_ok=True)
        if releases.is_symlink():raise ValueError('unsafe releases directory')
        prefix=releases/(doc['version']+'-'+doc['source_commit'][:12])
        prefix.mkdir(mode=0o755,exist_ok=False)
        share=prefix/'share';share.mkdir()
        artifact_refs={};wheel_paths=[]
        for role,ref in doc['artifacts'].items():
            dst=share/'artifacts'/Path(ref['path']).name;_copy(ref,dst)
            artifact_refs[role]={'path':dst.relative_to(prefix).as_posix(),'sha256':ref['sha256']}
        for index,dep in enumerate(doc['dependencies']):
            dst=share/'wheels'/Path(dep['wheel']['path']).name;_copy(dep['wheel'],dst);wheel_paths.append(dst)
            _copy(dep['pypi_identity'],share/'dependency-proofs'/('%03d.json'%index))
        verifier,checker=_extract_tool(share/'artifacts'/Path(doc['artifacts']['tool']['path']).name,share/'tool-source')
        shutil.copyfile(verifier,share/'verify-system.py');shutil.copyfile(checker,share/'check-local-install.py')
        backends={}
        for name,ref in doc['backends'].items():
            dst=prefix/'backend/native-macos-arm64'/name;_copy(ref,dst,executable=True)
            backends[name]={'path':dst.relative_to(prefix).as_posix(),'sha256':ref['sha256']}
        for item in doc['resources']:_copy(item['input'],prefix/relative(item['destination']))
        proofs={}
        for name,ref in doc['proofs'].items():
            dst=share/'proofs'/(name+'.json');_copy(ref,dst)
            proofs[name]={'path':dst.relative_to(prefix).as_posix(),'sha256':ref['sha256']}
        ci_doc=read_json(share/'proofs/ci.json');ci_ref=ci_doc['package_inventory']
        _copy({**ci_ref,'path':str(Path(doc['proofs']['ci']['path']).parent/ci_ref['path'])},
              share/'proofs/ci-package-inventory.json')
        native=read_json(share/'proofs/native.json');log_root=Path(doc['native_log_root'])
        for row in native['commands']:
            for key in ('stdout','stderr'):
                ref=row[key];dst=prefix/relative(ref['path']);dst.parent.mkdir(parents=True,exist_ok=True)
                full={**ref,'path':str(log_root/ref['path'])}
                if dst.exists():
                    if dst.is_symlink() or digest(dst)!=ref['sha256']:raise ValueError('conflicting native logs')
                else:_copy(full,dst)
        work=_workspace(base)
        if sys.version_info[:2]<(3,12):raise ValueError('Python 3.12 or newer required')
        _run([sys.executable,'-B','-I','-m','venv','--copies',prefix/'venv'],work,timeout=300)
        wheels=[share/'artifacts'/Path(doc['artifacts'][role]['path']).name for role in ('core','player')]+wheel_paths
        _run([prefix/'venv/bin/python','-B','-m','pip','install','--no-index','--no-deps','--no-compile',*wheels],work,timeout=600)
        _run([prefix/'venv/bin/python','-B','-m','pip','check'],work,timeout=60)
        runtime={'format':'fdisbull-system-runtime-1','version':doc['version'],'source_commit':doc['source_commit'],
                 'installation':str(prefix),'backends':{k:str(prefix/v['path']) for k,v in backends.items()},
                 'resources':{item['destination']:str(prefix/item['destination']) for item in doc['resources']}}
        _write(prefix/'RUNTIME.json',runtime)
        _write(prefix/'INSTALLATION.json',{'status':'candidate','version':doc['version'],'source_commit':doc['source_commit']})
        files=_inventory(prefix)
        _write(prefix/'PAYLOAD.json',{'schema':'fdisbull-system-payload-1','files':files})
        manifest={'schema':'fdisbull-system-install-manifest-1','version':doc['version'],'source_commit':doc['source_commit'],
                  'base':str(base),'files':files,'backends':backends,'proofs':proofs,'artifacts':artifact_refs}
        _write(share/'install-manifest.json',manifest)
        proof=_verify(prefix,base)
        _write(prefix/'INSTALLATION.json',{'status':'staged_verified','version':doc['version'],
                'source_commit':doc['source_commit'],'verification':proof},replace=True)
        return {'status':'staged_verified','prefix':str(prefix),'source_commit':doc['source_commit']}


def _candidate(prefix,base):
    p=Path(prefix).absolute()
    if (any(x.is_symlink() for x in (p,*p.parents)) or not p.is_dir()
            or p.parent != base/'releases'):raise ValueError('candidate must be a real direct release child')
    receipt=read_json(p/'INSTALLATION.json');manifest=read_json(p/'share/install-manifest.json')
    if (manifest.get('schema')!='fdisbull-system-install-manifest-1' or manifest.get('base')!=str(base)
            or manifest.get('version')!=receipt.get('version') or manifest.get('source_commit')!=receipt.get('source_commit')
            or receipt.get('status') not in ('staged_verified','activating','rolling_back','active_verified')):raise ValueError('candidate installation receipt invalid')
    return p,receipt,manifest


def verify(prefix,base):
    base=_base(base)
    with _lock(base):
        prefix,_,manifest=_candidate(prefix,base)
        return {'status':'passed','prefix':str(prefix),'source_commit':manifest['source_commit'],'proof':_verify(prefix,base)}


def _selector(base):
    current=base/'current'
    if not current.exists() and not current.is_symlink():return None
    if not current.is_symlink():raise ValueError('current selector is not a symlink')
    target=os.readlink(current);resolved=current.resolve(strict=True)
    if resolved.parent!=base/'releases' or not resolved.is_dir():raise ValueError('current selector outside releases')
    return target


def _switch(base,target):
    current=base/'current'
    if target is None:
        if not current.is_symlink():raise ValueError('selector changed during rollback')
        current.unlink()
    else:
        tmp=base/('.current-'+uuid.uuid4().hex)
        os.symlink(target,tmp)
        os.replace(tmp,current)
    fd=os.open(base,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)


def _verify_backend_resolution(prefix,manifest,*,dosbox_route=Path('/usr/local/bin/fdisbull-dosbox'),
                               qemu_route=Path('/usr/local/bin/fdisbull-qemu')):
    required={'dosbox-x','dosbox-layers','qemu-system-x86_64'}
    backends=manifest.get('backends',{})
    if not required <= set(backends):raise ValueError('shared native command backends missing')
    for name in required:
        ref=backends[name];target=prefix/'backend/native-macos-arm64'/name
        if ref.get('path')!=target.relative_to(prefix).as_posix() or not target.is_file() or digest(target)!=ref.get('sha256'):
            raise ValueError('shared native command target mismatch')
    if not dosbox_route.is_symlink() or dosbox_route.resolve()!=prefix/'backend/native-macos-arm64/dosbox-x':
        raise ValueError('DOSBox command does not follow selected backend')
    if (qemu_route.is_symlink() or not qemu_route.is_file()
            or digest(qemu_route)!='e7117098fff41d16f7c07773f8ae7d4e6ddb29b74871b87e560ff18481679e01'):
        raise ValueError('QEMU command is not the known selector-following wrapper')
    return {'dosbox':str(dosbox_route),'qemu':str(qemu_route),'targets':sorted(required)}


def _verify_resolution(base,prefix,version):
    """Prove the existing caller route is the known selector-following wrapper."""
    if base!=DEFAULT_BASE:raise ValueError('default command route is not configured for this base')
    wrapper=Path('/usr/local/bin/fdisbull')
    user_wrapper=Path.home()/'.local/bin/fdisbull'
    expected='881b3a11c2c4fff82b2d5a42c4f992beff4a85a168c8507ed8f2dadf7ace3b25'
    route=shutil.which('fdisbull')
    if (not route or not wrapper.is_file() or wrapper.is_symlink() or digest(wrapper)!=expected
            or not user_wrapper.is_symlink() or user_wrapper.resolve()!=wrapper
            or Path(route).resolve()!=wrapper):
        raise ValueError('caller PATH does not resolve to the verified selector-following fdisbull wrapper')
    work=_workspace(base)
    for executable in (wrapper,user_wrapper,Path(route)):
        if _run([executable,'--version'],work,timeout=60,capture=True).decode('utf-8','strict').strip()!=version:
            raise ValueError('selector-following wrapper version differs')
    backends=_verify_backend_resolution(prefix,read_json(prefix/'share/install-manifest.json'))
    return {'caller_path':route,'wrapper':str(wrapper),'wrapper_sha256':expected,'version':version,
            'prefix':str(prefix),'native_commands':backends}


def _postcheck(prefix,base,manifest,*,activation_precheck=False):
    work=_workspace(base)
    argv=[prefix/'venv/bin/python','-B','-I',prefix/'share/check-local-install.py',
          '--base',base,'--version',manifest['version'],'--commit',manifest['source_commit'],'--json']
    if activation_precheck:argv.append('--activation-precheck')
    result=_run(argv,work,timeout=300,json_output=True)
    expected='prechecked' if activation_precheck else 'passed'
    if (result.get('status')!=expected or result.get('source_commit')!=manifest['source_commit']
            or result.get('version')!=manifest['version']
            or activation_precheck and (result.get('selected_default') is not True or result.get('active_default') is not False)):
        raise ValueError('postcheck local install failed')
    return result


def _previous_available(base,previous):
    if previous is None:return
    if not isinstance(previous,str) or not previous or '\x00' in previous:raise ValueError('previous selector invalid')
    target=(base/previous).resolve(strict=True)
    if target.parent!=base/'releases' or not target.is_dir():raise ValueError('previous selector unavailable')


def _attempt(prefix,receipt,manifest,base):
    attempt=receipt.get('activation_attempt');ref=receipt.get('activation_intent')
    if not isinstance(attempt,str) or not re.fullmatch('[0-9a-f]{32}',attempt):raise ValueError('activation attempt identity missing')
    expected='share/activations/'+attempt+'/intent.json'
    if (not isinstance(ref,dict) or set(ref)!={'path','sha256'} or ref['path']!=expected
            or not HASH.fullmatch(str(ref['sha256']))):raise ValueError('activation intent reference invalid')
    path=safe_regular(prefix/expected)
    if digest(path)!=ref['sha256']:raise ValueError('activation intent changed')
    intent=read_json(path)
    if (intent.get('schema')!='fdisbull-install-activation-2' or intent.get('attempt')!=attempt
            or intent.get('source_commit')!=manifest['source_commit'] or intent.get('version')!=manifest['version']
            or intent.get('new_selector')!='releases/'+prefix.name):raise ValueError('activation intent binding invalid')
    _previous_available(base,intent.get('previous_selector'))
    backup=safe_regular(path.parent/'staged.json')
    if digest(backup)!=intent.get('staged_receipt_sha256'):raise ValueError('staged receipt backup changed')
    staged=read_json(backup)
    if (staged.get('status')!='staged_verified' or staged.get('version')!=manifest['version']
            or staged.get('source_commit')!=manifest['source_commit']):raise ValueError('staged receipt backup identity invalid')
    return path.parent,intent,staged


def _close_attempt(path,value):
    # Reconciliation may finish an already-observed compensation, never replace
    # the original closure or replay a selector switch that already happened.
    if path.exists() or path.is_symlink():
        existing=read_json(path)
        keys=('schema','attempt','source_commit','version','restored_selector')
        if any(existing.get(k)!=value.get(k) for k in keys):raise ValueError('activation closure conflicts')
        return existing
    _write(path,value)
    return value


def _restore_attempt(prefix,base,receipt,manifest,*,reason):
    folder,intent,staged=_attempt(prefix,receipt,manifest,base)
    previous=intent['previous_selector'];selected=intent['new_selector'];current=_selector(base)
    if current not in (previous,selected):
        raise RuntimeError('selector changed outside activation; reconciliation required')
    # Clear any final marker durably before a compensating selector mutation.
    if receipt['status']!='rolling_back':
        receipt={**receipt,'status':'rolling_back'}
        _write(prefix/'INSTALLATION.json',receipt,replace=True)
    if _selector(base)==selected:_switch(base,previous)
    if _selector(base)!=previous:raise RuntimeError('activation selector rollback failed')
    closure={'schema':'fdisbull-install-rollback-2','attempt':intent['attempt'],
             'source_commit':manifest['source_commit'],'version':manifest['version'],
             'restored_selector':previous,'reason':reason}
    _close_attempt(folder/'rollback-complete.json',closure)
    _write(prefix/'INSTALLATION.json',staged,replace=True)
    return {'status':'rolled_back','restored_selector':previous,'attempt':intent['attempt']}


def _confirm_active(prefix,base,receipt,manifest):
    _,intent,_=_attempt(prefix,receipt,manifest,base)
    if _selector(base)!='releases/'+prefix.name:raise ValueError('active candidate is not selected; reconcile explicitly')
    _verify(prefix,base,active_required=True)
    _verify_resolution(base,prefix,manifest['version'])
    _postcheck(prefix,base,manifest)
    return {'status':'active_verified','prefix':str(prefix),'previous_selector':intent['previous_selector'],
            'already_active':True,'attempt':receipt['activation_attempt']}


def activate(prefix,base):
    base=_base(base)
    with _lock(base):
        prefix,receipt,manifest=_candidate(prefix,base)
        if receipt['status']=='active_verified':return _confirm_active(prefix,base,receipt,manifest)
        if receipt['status']!='staged_verified':raise ValueError('interrupted activation; run reconcile before a new attempt')
        _verify(prefix,base)
        previous=_selector(base);selected='releases/'+prefix.name
        if previous==selected:raise ValueError('candidate already selected without a complete activation')
        _previous_available(base,previous)
        # Older fixed-name attempts remain untouched. New attempts are unique.
        legacy=prefix/'share/activation-intent.json'
        legacy_sha=None
        if legacy.exists() or legacy.is_symlink():
            old=read_json(legacy)
            if (old.get('schema')!='fdisbull-install-activation-1' or old.get('source_commit')!=manifest['source_commit']
                    or old.get('version')!=manifest['version'] or old.get('previous_selector')!=previous
                    or old.get('new_selector')!=selected):raise ValueError('legacy activation effects require reconciliation')
            legacy_sha=digest(legacy)
        attempt=uuid.uuid4().hex;folder=prefix/'share/activations'/attempt
        folder.mkdir(parents=True,exist_ok=False)
        _write(folder/'staged.json',receipt)
        intent={'schema':'fdisbull-install-activation-2','attempt':attempt,'source_commit':manifest['source_commit'],
                'version':manifest['version'],'previous_selector':previous,'new_selector':selected,
                'staged_receipt_sha256':digest(folder/'staged.json')}
        if legacy_sha is not None:intent['legacy_intent_sha256']=legacy_sha
        _write(folder/'intent.json',intent)
        pending={**receipt,'status':'activating','activation_attempt':attempt,'previous_selector':previous,
                 'activation_intent':{'path':(folder/'intent.json').relative_to(prefix).as_posix(),
                                      'sha256':digest(folder/'intent.json')}}
        try:
            _write(prefix/'INSTALLATION.json',pending,replace=True)
            if _selector(base)!=previous:raise ValueError('selector changed before activation')
            _switch(base,selected)
            _verify(prefix,base,activation_precheck=True)
            route=_verify_resolution(base,prefix,manifest['version'])
            precheck=_postcheck(prefix,base,manifest,activation_precheck=True)
            if _selector(base)!=selected:raise ValueError('selector changed during activation checks')
            complete={'schema':'fdisbull-install-activation-complete-2','attempt':attempt,
                      'source_commit':manifest['source_commit'],'version':manifest['version'],
                      'new_selector':selected,'previous_selector':previous,
                      'intent_sha256':pending['activation_intent']['sha256'],
                      'command_resolution':route,'precheck_result':precheck}
            _write(folder/'complete.json',complete)
            # All substantive live checks and their durable proof precede this
            # final marker. Public verification refuses the activating phase.
            final={**pending,'status':'active_verified','activation_complete':{
                'path':(folder/'complete.json').relative_to(prefix).as_posix(),'sha256':digest(folder/'complete.json')}}
            _write(prefix/'INSTALLATION.json',final,replace=True)
            _verify(prefix,base,active_required=True)
            _postcheck(prefix,base,manifest)
            return {'status':'active_verified','prefix':str(prefix),'previous_selector':previous,'attempt':attempt}
        except BaseException:
            # Re-read durable state: a write/switch can take effect before its
            # caller sees an error. Compensation observes which effect exists.
            actual=read_json(prefix/'INSTALLATION.json')
            if actual.get('activation_attempt')==attempt:
                _restore_attempt(prefix,base,actual,manifest,reason='activation-failed')
            elif actual!=receipt:raise RuntimeError('activation receipt changed; reconciliation required')
            raise


def reconcile(prefix,base):
    """Explicitly restore an interrupted owned attempt; never run it forward."""
    base=_base(base)
    with _lock(base):
        prefix,receipt,manifest=_candidate(prefix,base)
        if receipt['status']=='active_verified':return _confirm_active(prefix,base,receipt,manifest)
        if receipt['status']=='staged_verified':
            if _selector(base)=='releases/'+prefix.name:raise ValueError('staged candidate unexpectedly selected')
            return {'status':'staged_verified','prefix':str(prefix),'reconciliation_performed':False}
        return _restore_attempt(prefix,base,receipt,manifest,reason='explicit-reconciliation')


def rollback(prefix,base):
    base=_base(base)
    with _lock(base):
        prefix,receipt,manifest=_candidate(prefix,base)
        if receipt['status']=='staged_verified':
            if _selector(base)=='releases/'+prefix.name:raise ValueError('staged candidate unexpectedly selected')
            return {'status':'already_inactive','current_selector':_selector(base),'already_inactive':True}
        return _restore_attempt(prefix,base,receipt,manifest,reason='explicit-rollback')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=DEFAULT_BASE)
    sub=parser.add_subparsers(dest='command',required=True)
    s=sub.add_parser('stage');s.add_argument('--manifest',type=Path,required=True)
    for name in ('verify','activate','rollback','reconcile'):
        p=sub.add_parser(name);p.add_argument('--prefix',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        value=stage(args.manifest,args.base) if args.command=='stage' else globals()[args.command](args.prefix,args.base)
        print(json.dumps(value,sort_keys=True));return 0
    except Exception as error:
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'error':str(error)},sort_keys=True));return 1


if __name__=='__main__':
    def _interrupted(_signum,_frame):raise KeyboardInterrupt()
    for _signum in (signal.SIGTERM,signal.SIGHUP):signal.signal(_signum,_interrupted)
    raise SystemExit(main())
