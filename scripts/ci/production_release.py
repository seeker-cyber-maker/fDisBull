#!/usr/bin/env python3
"""Finite draft-first release worker. Partial effects are retained; no mutation replay."""
import fcntl
import hashlib
import importlib.util
import json
import os
import plistlib
from pathlib import Path, PurePosixPath
import re
import selectors
import shlex
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('release_provider', HERE / 'production_transport.py')
provider = importlib.util.module_from_spec(spec); spec.loader.exec_module(provider)
CACHE = Path('/Volumes/CACHE/fdisbull-ci-builds/release-publish')
RESULTS = '/var/lib/fdisbull-ci/results/'
REPO = 'seeker-cyber-maker/fDisBull'
API = '/repos/' + REPO
VERSION = '0.35.0'
TAG = 'v' + VERSION
GH = '/opt/homebrew/bin/gh'
SSH = ['/usr/bin/tailscale', 'ssh', 'ubuntu@100.101.7.35']
HEX = re.compile(r'[0-9a-f]{64}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
# Root reads an already-bound path; the request is data on stdin, never shell text.
REMOTE = r'''import json,os,stat,sys
r=json.load(sys.stdin);p=r['path'];prefix='/var/lib/fdisbull-ci/results/'
assert isinstance(p,str) and p.startswith(prefix) and all(x not in ('','.','..') for x in p[1:].split('/'))
fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
parts=p[1:].split('/')
for name in parts[:-1]:
 n=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=n
f=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd);s=os.fstat(f)
assert stat.S_ISREG(s.st_mode) and (r['size'] is None or s.st_size==r['size']) and s.st_size<=r['cap'] and (not r['root_owned'] or s.st_uid==0)
while True:
 b=os.read(f,1048576)
 if not b:break
 sys.stdout.buffer.write(b)
'''


def digest(path):
    with path.open('rb') as f:
        h=hashlib.sha256()
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()


def cache_available():
    root=Path('/Volumes/CACHE')
    if (not os.path.ismount(root) or root.is_symlink() or not CACHE.is_dir()
            or any(x.is_symlink() for x in (CACHE,*CACHE.parents)) or CACHE.stat().st_dev!=root.stat().st_dev):return False
    try:
        result=provider._source.run_command(['/usr/sbin/diskutil','info','-plist',str(root)],cwd='/',timeout=12)
        if result.get('returncode')!=0 or result.get('timed_out') or result.get('overflow'):return False
        info=plistlib.loads(result['stdout'])
        return info.get('VolumeUUID')=='DB098A4B-7968-418F-8B20-61597F42392A' and info.get('MountPoint')==str(root) and info.get('Internal') is False
    except (OSError,ValueError,KeyError,TypeError):return False



def safe_path(path):
    if not isinstance(path,str) or not path.startswith(RESULTS):raise ValueError('unsafe result path')
    p=PurePosixPath(path)
    if str(p)!=path or any(x in ('.','..') for x in p.parts):raise ValueError('unsafe result path')
    return path


def write_once(path,obj):
    data=(json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)


def fetch(path,size,sha,target,deadline,*,root_owned=False):
    cap = size if size is not None else 2*1024*1024
    safe_path(path)
    if (size is not None and (type(size) is not int or not 0<=size<=2_000_000_000)) or not HEX.fullmatch(str(sha)):raise ValueError('invalid input identity')
    if target.exists():
        if target.is_symlink() or not target.is_file() or (size is not None and target.stat().st_size!=size) or target.stat().st_size>cap or digest(target)!=sha:raise ValueError('cached input differs')
        return
    command=SSH+['sudo -n /usr/bin/python3 -I -c '+shlex.quote(REMOTE)]
    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        request=json.dumps({'path':path,'size':size,'cap':cap,'root_owned':root_owned}).encode();p.stdin.write(request);p.stdin.close()
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait();raise
    h=hashlib.sha256();total=0;sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ)
    try:
        with os.fdopen(fd,'wb') as out:
            while sel.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('input transfer deadline')
                for _,_ in sel.select(min(1,remaining)):
                    b=os.read(p.stdout.fileno(),1024*1024)
                    if not b:sel.unregister(p.stdout);break
                    total+=len(b)
                    if total>cap:raise ValueError('input exceeds expected size')
                    h.update(b);out.write(b)
            out.flush();os.fsync(out.fileno())
        if p.wait(timeout=max(.01,deadline-time.monotonic()))!=0 or (size is not None and total!=size) or h.hexdigest()!=sha:raise ValueError('input transfer mismatch')
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait();raise
    finally:sel.close();p.stdout.close()


def read_json(path):
    if path.stat().st_size>2*1024*1024:raise ValueError('JSON exceeds bound')
    value=json.loads(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('invalid JSON')
    return value


_GITHUB_ENV = None


def github_env(deadline):
    """Use the existing named account without switching gh's active account."""
    global _GITHUB_ENV
    if _GITHUB_ENV is None:
        remaining=min(15,deadline-time.monotonic())
        if remaining<=0:raise TimeoutError('release credential deadline')
        result=provider._source.run_command([GH,'auth','token','--hostname','github.com',
            '--user','seeker-cyber-maker','--no-refresh'],cwd='/',env=provider._clean_env(),timeout=remaining)
        token=result.get('stdout',b'').strip()
        if (result.get('returncode')!=0 or result.get('timed_out') or result.get('overflow')
                or not isinstance(token,bytes) or not 0<len(token)<=4096
                or b'\n' in token or b'\r' in token):raise ValueError('release credential context unavailable')
        env=provider._clean_env();env['GH_TOKEN']=token.decode('ascii','strict');_GITHUB_ENV=env
    return dict(_GITHUB_ENV)


def gh(args,deadline,body=None):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('release deadline')
    env=github_env(deadline)
    result=provider._source.run_command([GH,*args],cwd='/',env=env,input_bytes=body,timeout=remaining)
    if result.get('timed_out') or result.get('overflow') or type(result.get('returncode')) is not int:raise RuntimeError('GitHub outcome unknown')
    return result


def api(path,deadline):
    result=gh(['api','--hostname','github.com','--include','--method','GET',path],deadline)
    response=provider._parse(result['stdout'],False)
    if result['returncode'] and response['http_status']<400:raise RuntimeError('GitHub result unknown')
    return response['http_status'],response['data']


def checked_ref(value,maximum=2_000_000):
    if not isinstance(value,dict) or set(value)!={'path','sha256','size'} or not HEX.fullmatch(str(value['sha256'])) or type(value['size']) is not int or not 0<=value['size']<=maximum:raise ValueError('invalid evidence identity')
    p=PurePosixPath(value['path'])
    if p.is_absolute() or str(p)!=value['path'] or any(x in ('.','..') for x in p.parts):raise ValueError('unsafe evidence path')
    return value


def linked(root,ref,cache,deadline):
    ref=checked_ref(ref);name='evidence-'+ref['sha256']
    target=cache/name;fetch(root+'/'+ref['path'],ref['size'],ref['sha256'],target,deadline)
    return target


def validate_manifest(m):
    if (set(m)!={'schema','repository','repository_id','source_sha','version','tag','qualification','assets','notes'}
        or m['schema']!='fdisbull-release-inputs-1' or m['repository']!=REPO or m['repository_id']!=1431097789
        or not SHA.fullmatch(str(m['source_sha'])) or m['version']!=VERSION or m['tag']!=TAG
        or not isinstance(m['notes'],str) or len(m['notes'].encode())>65536 or '\x00' in m['notes']):raise ValueError('release manifest invalid')
    q=m['qualification']
    if not isinstance(q,dict) or set(q)!={'root','path','sha256'} or not HEX.fullmatch(str(q.get('sha256'))):raise ValueError('qualification identity invalid')
    safe_path(q['root']+'/x');checked_ref({'path':q['path'],'sha256':q['sha256'],'size':0})
    if not isinstance(m['assets'],list) or len(m['assets'])!=6:raise ValueError('six qualified release assets required')
    seen=set()
    for a in m['assets']:
        if (not isinstance(a,dict) or set(a)!={'name','path','size','sha256'} or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}',str(a['name']))
                or a['name'] in seen or not HEX.fullmatch(str(a['sha256'])) or type(a['size']) is not int or not 0<a['size']<=2_000_000_000):raise ValueError('asset invalid')
        safe_path(a['path']);seen.add(a['name'])
    if 'SHA256SUMS' not in seen:raise ValueError('SHA256SUMS asset required')
    if next(a for a in m['assets'] if a['name']=='SHA256SUMS')['size']>65536:raise ValueError('checksum asset exceeds bound')
    return q


def evidence(m,cache,deadline):
    q=validate_manifest(m);root=q['root'];source=m['source_sha']
    qualified=cache/('evidence-'+q['sha256'])
    fetch(root+'/'+q['path'],None,q['sha256'],qualified,deadline)
    doc=read_json(qualified)
    if doc.get('schema')!='fdisbull-ci-qualification-1' or doc.get('status')!='qualified' or doc.get('source_commit')!=source:raise ValueError('qualification invalid')
    package=read_json(linked(root,doc.get('package_inventory'),cache,deadline))
    if package.get('schema')!='fdisbull-package-payloads-1' or package.get('source_commit')!=source or package.get('tracked_worktree_dirty') is not False:raise ValueError('package evidence invalid')
    packages=package.get('artifacts');assets={x['name']:x for x in m['assets']}
    if not isinstance(packages,dict) or set(packages)!={'core','player','sdist','tool'}:raise ValueError('package inventory incomplete')
    if len({v.get('name') for v in packages.values() if isinstance(v,dict)})!=4:raise ValueError('package identities overlap')
    for v in packages.values():
        if not isinstance(v,dict) or v.get('name') not in assets or (assets[v['name']]['sha256'],assets[v['name']]['size'])!=(v.get('sha256'),v.get('size_bytes')):raise ValueError('package asset mismatch')
    chat=doc.get('chat_consumer')
    if not isinstance(chat,dict):raise ValueError('chat consumer missing')
    receipt=read_json(linked(root,chat.get('receipt'),cache,deadline))
    verifier=read_json(linked(root,chat.get('verifier'),cache,deadline))
    archive=checked_ref(chat.get('archive'),maximum=2_000_000_000)
    matches=[a for a in m['assets'] if (a['sha256'],a['size'])==(archive['sha256'],archive['size'])]
    if (len(matches)!=1 or matches[0]['name'] in {v['name'] for v in packages.values()} | {'SHA256SUMS'}
            or receipt.get('schema')!='fdisbull-chat-consumer-job-v1'
            or receipt.get('status')!='passed' or receipt.get('source_commit')!=source
            or receipt.get('test_source_commit')!=source or receipt.get('source_access')!='absent'
            or receipt.get('archive')!=archive or receipt.get('verifier')!=chat['verifier']):raise ValueError('chat archive evidence mismatch')
    if (verifier.get('schema')!='fdisbull-chat-consumer-verification-v1' or verifier.get('status')!='passed'
        or verifier.get('source_commit')!=source or verifier.get('test_source_commit')!=source
        or verifier.get('archive_sha256')!=archive['sha256'] or verifier.get('network_interfaces')!=['lo']
        or verifier.get('skipped')!=0 or verifier.get('native_failures')!=0):raise ValueError('consumer evidence invalid')
    windows=verifier.get('windows_native_qualification',{});extended=verifier.get('extended_windows',{})
    if windows.get('pe32')!='passed' or windows.get('win16')!='passed' or any(extended.get(k,{}).get('status')!='passed' for k in ('pe32','win16')):raise ValueError('extended Windows evidence missing')
    junit=ET.parse(linked(root,receipt.get('junit'),cache,deadline)).getroot()
    suites=[junit] if junit.tag=='testsuite' else junit.findall('testsuite')
    if (not suites or any(int(s.get(k,'0'))!=0 for s in suites for k in ('failures','errors','skipped'))
            or junit.findall('.//failure') or junit.findall('.//error') or junit.findall('.//skipped')
            or not junit.findall('.//testcase')):raise ValueError('consumer JUnit incomplete')
    return archive, packages, verifier


def download_asset(asset_id, expected, target, deadline):
    if target.exists():
        if target.is_symlink() or target.stat().st_size!=expected['size'] or digest(target)!=expected['sha256']:raise ValueError('asset readback differs')
        return
    if not cache_available():raise ValueError('release cache unavailable')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('asset readback deadline')
    p=subprocess.Popen([GH,'api','--hostname','github.com','-H','Accept: application/octet-stream',API+'/releases/assets/'+str(asset_id)],
        cwd='/',env=github_env(deadline),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    try:fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait();raise
    h=hashlib.sha256();count=0;sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ)
    try:
        with os.fdopen(fd,'wb') as out:
            while sel.get_map():
                if time.monotonic()>=deadline:raise TimeoutError('asset readback deadline')
                for _,_ in sel.select(min(1,deadline-time.monotonic())):
                    b=os.read(p.stdout.fileno(),1024*1024)
                    if not b:sel.unregister(p.stdout);break
                    count+=len(b)
                    if count>expected['size']:raise ValueError('asset readback exceeds bound')
                    h.update(b);out.write(b)
            out.flush();os.fsync(out.fileno())
        if p.wait(timeout=max(.01,deadline-time.monotonic()))!=0 or count!=expected['size'] or h.hexdigest()!=expected['sha256']:raise ValueError('asset readback differs')
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
        p.wait();raise
    finally:sel.close();p.stdout.close()


def remote_state(m,cache,deadline):
    code,release=api(API+'/releases/tags/'+TAG,deadline)
    if code==404:return {'status':'attention','reason':'release-not-found'}
    if (code!=200 or not isinstance(release,dict) or release.get('tag_name')!=TAG
            or type(release.get('id')) is not int or release.get('id')<=0
            or release.get('html_url')!='https://github.com/'+REPO+'/releases/tag/'+TAG):raise RuntimeError('release readback unknown')
    partial={'release_id':release['id'],'release_url':release.get('html_url'),'draft':release.get('draft'),'assets':[]}
    refcode,ref=api(API+'/git/ref/tags/'+TAG,deadline)
    if refcode==404 and release.get('draft') is True:
        # A draft may precede tag creation. Its requested full commit must be
        # explicit; the published result still requires the actual tag below.
        if release.get('target_commitish')!=m['source_sha']:
            return {'status':'attention','reason':'draft-target-mismatch',**partial}
        obj={'type':'commit','sha':m['source_sha']}
        partial['tag_state']='not-created-draft'
    elif refcode==200 and isinstance(ref,dict):
        obj=ref.get('object',{});partial['tag_state']='created'
    else:raise RuntimeError('tag readback unknown')
    if obj.get('type')=='tag':
        code,tag=api(API+'/git/tags/'+str(obj.get('sha')),deadline)
        if code!=200 or not isinstance(tag,dict):raise RuntimeError('annotated tag readback unknown')
        obj=tag.get('object',{})
    if obj.get('type')!='commit' or obj.get('sha')!=m['source_sha']:return {'status':'attention','reason':'tag-target-mismatch',**partial}
    code,listed=api(API+'/releases/'+str(release['id'])+'/assets?per_page=100',deadline)
    if code!=200 or not isinstance(listed,list):raise RuntimeError('asset list unknown')
    expected={a['name']:a for a in m['assets']};seen=set()
    for row in listed:
        if not isinstance(row,dict) or type(row.get('id')) is not int or not isinstance(row.get('name'),str):raise ValueError('invalid release asset')
        name=row['name'];partial['assets'].append({'id':row['id'],'name':name,'url':row.get('browser_download_url')})
        if name not in expected or name in seen:return {'status':'attention','reason':'unexpected-assets',**partial}
        seen.add(name);item=expected[name]
        if row.get('size')!=item['size'] or row.get('state')!='uploaded':return {'status':'attention','reason':'asset-size-or-state',**partial}
        if row.get('digest') is None:
            download_asset(row['id'],item,cache/('readback-'+str(row['id'])),deadline)
        elif row['digest']!='sha256:'+item['sha256']:
            return {'status':'attention','reason':'asset-digest-mismatch',**partial}
    complete=seen==set(expected)
    if complete and release.get('draft') is False and release.get('prerelease') is False:
        return {'status':'completed','source_sha':m['source_sha'],'tag':TAG,**partial}
    return {'status':'attention','reason':'draft-or-incomplete',**partial}


def mutation(args,record,deadline):
    code,user=api('/user',deadline)
    if code!=200 or not isinstance(user,dict) or user.get('login')!='seeker-cyber-maker':raise ValueError('GitHub principal mismatch')
    write_once(record,{'argv_kind':args[1:3], 'started':True})
    result=gh(args,deadline)
    if result['returncode']!=0:raise RuntimeError('mutation outcome unknown')


def run(doc):
    if not isinstance(doc,dict) or set(doc)!={'operation','key','payload'} or doc['operation'] not in ('publish','reconcile','preflight'):raise ValueError('invalid request')
    key=doc['key'];payload=doc['payload']
    if doc['operation']=='preflight':
        if (not isinstance(key,str) or not 1<=len(key)<=500 or not isinstance(payload,dict)
                or set(payload)!={'source_sha','version','tag'} or not SHA.fullmatch(str(payload['source_sha']))
                or payload['version']!=VERSION or payload['tag']!=TAG):raise ValueError('release preflight input invalid')
        if not cache_available():raise ValueError('release cache unavailable')
        deadline=time.monotonic()+120
        code,user=api('/user',deadline)
        if code!=200 or not isinstance(user,dict) or user.get('login')!='seeker-cyber-maker':raise ValueError('GitHub principal mismatch')
        code,repo=api(API,deadline)
        if (code!=200 or not isinstance(repo,dict) or repo.get('id')!=1431097789
                or repo.get('full_name')!=REPO or (repo.get('permissions') or {}).get('push') is not True):raise ValueError('release repository access unavailable')
        code,commit=api(API+'/commits/'+payload['source_sha'],deadline)
        if code!=200 or not isinstance(commit,dict) or commit.get('sha')!=payload['source_sha']:raise ValueError('primary source unavailable')
        if api(API+'/git/ref/tags/'+TAG,deadline)[0]!=404 or api(API+'/releases/tags/'+TAG,deadline)[0]!=404:raise ValueError('tag or release already exists')
        return {'status':'ready','source_sha':payload['source_sha'],'tag':TAG,'repository_id':1431097789,'publication_performed':False}
    if not isinstance(key,str) or not 1<=len(key)<=500 or any(ord(c)<32 for c in key):raise ValueError('invalid key')
    if not isinstance(payload,dict) or set(payload)!={'manifest_path','manifest_sha256'} or not HEX.fullmatch(str(payload['manifest_sha256'])):raise ValueError('invalid payload')
    safe_path(payload['manifest_path']);deadline=time.monotonic()+570
    if not cache_available():raise ValueError('release cache unavailable')
    incoming=CACHE/('input-'+payload['manifest_sha256']);fetch(payload['manifest_path'],None,payload['manifest_sha256'],incoming,deadline,root_owned=True)
    manifest=read_json(incoming);validate_manifest(manifest)
    cache=CACHE/(TAG+'-'+manifest['source_sha'])
    cache.mkdir(mode=0o700,exist_ok=True)
    if cache.is_symlink() or cache.stat().st_uid!=os.getuid() or cache.stat().st_mode&0o077:raise ValueError('unsafe release cache')
    lockfd=os.open(cache/'lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(lockfd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        binding={'key':key,'manifest_sha256':payload['manifest_sha256'],'source_sha':manifest['source_sha']}
        bindpath=cache/'binding.json'
        if bindpath.exists():
            if read_json(bindpath)!=binding:raise ValueError('release binding changed')
        elif doc['operation']=='publish':write_once(bindpath,binding)
        else:raise ValueError('unknown release key')
        archive,packages,verifier=evidence(manifest,cache,deadline)
        for a in manifest['assets']:
            fetch(a['path'],a['size'],a['sha256'],cache/a['name'],deadline)
        binary_assets=[a for a in manifest['assets'] if a['name']!='SHA256SUMS']
        lines=(cache/'SHA256SUMS').read_text('ascii').splitlines()
        if len(lines)!=5 or set(lines)!={a['sha256']+'  '+a['name'] for a in binary_assets}:
            raise ValueError('checksum asset differs from binary assets')
        archive_asset=next(a for a in manifest['assets'] if (a['sha256'],a['size'])==(archive['sha256'],archive['size']))
        with zipfile.ZipFile(cache/archive_asset['name']) as z:
            members=[x for x in z.infolist() if x.filename=='fdisbull-chat-offline/MANIFEST.json']
            if len(members)!=1 or members[0].file_size>2*1024*1024:raise ValueError('kit manifest missing')
            kit_bytes=z.read(members[0]);kit=json.loads(kit_bytes)
        if (kit.get('windows_acceptance')!='pe64-pe32-win16'
                or kit.get('identities',{}).get('source_commit')!=manifest['source_sha']
                or kit.get('identities',{}).get('test_source_commit')!=manifest['source_sha']
                or kit.get('identities',{}).get('version')!=VERSION
                or hashlib.sha256(kit_bytes).hexdigest()!=verifier.get('manifest_sha256')):raise ValueError('kit source or Windows acceptance mismatch')
        for kind in ('core','player'):
            item=packages[kind]
            if {'name':item['name'],'size':item['size_bytes'],'sha256':item['sha256']} not in kit.get('wheel_artifacts',[]):raise ValueError('kit wheel mismatch')
        code,user=api('/user',deadline)
        if code!=200 or not isinstance(user,dict) or user.get('login')!='seeker-cyber-maker':raise ValueError('GitHub principal mismatch')
        code,repo=api(API,deadline)
        if code!=200 or not isinstance(repo,dict) or repo.get('id')!=1431097789 or repo.get('full_name')!=REPO:raise ValueError('GitHub repository mismatch')
        if doc['operation']=='reconcile':return remote_state(manifest,cache,deadline)
        if any(cache.glob('intent-*.json')):return {'status':'attention','reason':'mutation-already-attempted'}
        if api(API+'/git/ref/tags/'+TAG,deadline)[0]!=404 or api(API+'/releases/tags/'+TAG,deadline)[0]!=404:raise ValueError('tag or release already exists')
        notes=cache/'notes.txt'
        fd=os.open(notes,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w') as f:f.write(manifest['notes']);f.flush();os.fsync(f.fileno())
        try:
            mutation(['release','create',TAG,'--repo',REPO,'--draft','--target',manifest['source_sha'],'--title',TAG,'--notes-file',str(notes)],cache/'intent-create.json',deadline)
            state=remote_state(manifest,cache,deadline)
            write_once(cache/'readback-create.json',state)
            if state.get('draft') is not True or state.get('reason')!='draft-or-incomplete' or state.get('assets'):return {'status':'attention','reason':'draft-readback-invalid','partial':state}
            for i,a in enumerate(manifest['assets']):
                mutation(['release','upload',TAG,str(cache/a['name']),'--repo',REPO],cache/('intent-upload-%02d.json'%i),deadline)
                state=remote_state(manifest,cache,deadline);write_once(cache/('readback-upload-%02d.json'%i),state)
                if state.get('draft') is not True or state.get('reason')!='draft-or-incomplete' or {x['name'] for x in state.get('assets',[])}!={x['name'] for x in manifest['assets'][:i+1]}:return {'status':'attention','reason':'upload-readback-invalid','partial':state}
            mutation(['release','edit',TAG,'--repo',REPO,'--draft=false'],cache/'intent-publish.json',deadline)
            state=remote_state(manifest,cache,deadline);write_once(cache/'readback-publish.json',state);return state
        except Exception:
            partial={'status':'attention','reason':'readback-unavailable'}
            try:partial=remote_state(manifest,cache,deadline)
            except Exception:pass
            result={'status':'attention','reason':'mutation-or-readback-unknown','receipt_dir':str(cache),'partial':partial}
            try:write_once(cache/'attention.json',result)
            except FileExistsError:pass
            return result


def main():
    def interrupt(_signum,_frame):raise KeyboardInterrupt()
    for signum in (signal.SIGTERM,signal.SIGHUP):signal.signal(signum,interrupt)
    try:
        raw=sys.stdin.buffer.read(16385)
        if len(raw)>16384:raise ValueError('request exceeds bound')
        result=run(json.loads(raw));print(json.dumps(result,separators=(',',':')));return 0
    except Exception:
        print('{"status":"attention","reason":"release-preflight-or-reconciliation-failed"}');return 0


if __name__=='__main__':raise SystemExit(main())
