"""Offline tests for release evidence and single-shot publication boundaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/ci'))
spec=importlib.util.spec_from_file_location('production_release_test',ROOT/'scripts/ci/production_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


def manifest():
    return {'schema':'fdisbull-release-inputs-1','repository':'seeker-cyber-maker/fDisBull','repository_id':1431097789,
        'source_sha':'a'*40,'version':'0.35.0','tag':'v0.35.0',
        'qualification':{'root':'/var/lib/fdisbull-ci/results/case','path':'qualification.json','sha256':'a'*64},
        'assets':[{'name':f'asset-{i}','path':f'/var/lib/fdisbull-ci/results/case/asset-{i}','size':1,'sha256':str(i)*64} for i in range(5)]+[{'name':'SHA256SUMS','path':'/var/lib/fdisbull-ci/results/case/SHA256SUMS','size':1,'sha256':'a'*64}],
        'notes':'bounded notes'}


def test_manifest_rejects_wrong_repo_paths_and_duplicate_asset():
    m=manifest();release.validate_manifest(m)
    m['assets'][0]['path']='/var/lib/fdisbull-ci/results/../outside'
    with pytest.raises(ValueError):release.validate_manifest(m)
    m=manifest();m['repository_id']=42
    with pytest.raises(ValueError):release.validate_manifest(m)
    m=manifest();m['assets'][1]['name']=m['assets'][0]['name']
    with pytest.raises(ValueError):release.validate_manifest(m)


def test_remote_state_requires_published_exact_tag_and_all_digests(tmp_path,monkeypatch):
    m=manifest();rows=[{'id':i+1,'name':a['name'],'size':a['size'],'state':'uploaded','digest':'sha256:'+a['sha256'],'browser_download_url':'https://example.test/'+a['name']} for i,a in enumerate(m['assets'])]
    def api(path,deadline):
        if '/releases/tags/' in path:return 200,{'id':7,'tag_name':release.TAG,'draft':False,'prerelease':False,'html_url':'https://github.com/'+release.REPO+'/releases/tag/'+release.TAG}
        if '/git/ref/tags/' in path:return 200,{'object':{'type':'commit','sha':m['source_sha']}}
        if '/assets?' in path:return 200,rows
        raise AssertionError(path)
    monkeypatch.setattr(release,'api',api)
    result=release.remote_state(m,tmp_path,time.monotonic()+10)
    assert result['status']=='completed' and result['source_sha']==m['source_sha'] and len(result['assets'])==6
    rows[0]['digest']='sha256:'+'f'*64
    assert release.remote_state(m,tmp_path,time.monotonic()+10)['reason']=='asset-digest-mismatch'
    rows.pop()
    assert release.remote_state(m,tmp_path,time.monotonic()+10)['status']=='attention'


def test_mutation_intent_precedes_cli_and_is_never_overwritten(tmp_path,monkeypatch):
    path=tmp_path/'intent.json';calls=[]
    def gh(args,deadline):
        calls.append(json.loads(path.read_text()));return {'returncode':1}
    monkeypatch.setattr(release,'gh',gh)
    monkeypatch.setattr(release,'api',lambda path,deadline:(200,{'login':'seeker-cyber-maker'}))
    with pytest.raises(RuntimeError,match='unknown'):release.mutation(['release','create','v0.35.0'],path,time.monotonic()+10)
    assert calls==[{'argv_kind':['create','v0.35.0'],'started':True}]
    with pytest.raises(FileExistsError):release.mutation(['release','create','v0.35.0'],path,time.monotonic()+10)
    assert len(calls)==1


def test_gui_release_contract_is_fixed_and_reconcile_not_mutation_key():
    spec=importlib.util.spec_from_file_location('gui_release_test',ROOT/'scripts/ci/production_gui_transport.py')
    gui=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui)
    payload={'manifest_path':'/var/lib/fdisbull-ci/results/case/release.json','manifest_sha256':'a'*64}
    gui._request('release',{'operation':'publish','key':'case-1','payload':payload})
    with pytest.raises(ValueError):gui._request('release',{'operation':'publish','key':'case-1','payload':{**payload,'manifest_path':'/tmp/release.json'}})
    spec=importlib.util.spec_from_file_location('gui_release_client_test',ROOT/'scripts/ci/production_gui_client.py')
    clientmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(clientmod)
    calls=[]
    class Client:
        def call(self,*args,**kwargs):calls.append((args,kwargs));return {'status':'attention'}
    transport=clientmod.GuiReleaseTransport(Client());transport.publish('case-1',payload);transport.reconcile('case-1',payload)
    assert calls[0][1]['key']=='release-publish:case-1' and 'key' not in calls[1][1]


def test_transfer_streams_bounded_content_and_rejects_mismatch(tmp_path,monkeypatch):
    import subprocess
    real=subprocess.Popen
    def fake_ssh(command,**kwargs):
        return real([sys.executable,'-c','import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b"fixture")'],**kwargs)
    monkeypatch.setattr(release.subprocess,'Popen',fake_ssh)
    identity=hashlib.sha256(b'fixture').hexdigest()
    release.fetch('/var/lib/fdisbull-ci/results/case/asset',7,identity,tmp_path/'ok',time.monotonic()+10)
    assert (tmp_path/'ok').read_bytes()==b'fixture'
    with pytest.raises(ValueError,match='mismatch'):
        release.fetch('/var/lib/fdisbull-ci/results/case/asset',7,'a'*64,tmp_path/'bad',time.monotonic()+10)


def test_draft_upload_readback_then_publish_without_replay(tmp_path,monkeypatch):
    import io
    import zipfile
    m=manifest(); m['assets']=[]; blobs={}; packages={}
    for kind in ('core','player','sdist','tool'):
        name=kind+'.bin';data=kind.encode();blobs[name]=data
        packages[kind]={'name':name,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
    kit={'windows_acceptance':'pe64-pe32-win16','identities':{'source_commit':'a'*40,'test_source_commit':'a'*40,'version':'0.35.0'},
         'wheel_artifacts':[{'name':packages[k]['name'],'size':packages[k]['size_bytes'],'sha256':packages[k]['sha256']} for k in ('core','player')]}
    kitbytes=json.dumps(kit).encode();archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:z.writestr('fdisbull-chat-offline/MANIFEST.json',kitbytes)
    blobs['chat.zip']=archive.getvalue()
    binary=[]
    for name,data in blobs.items():
        binary.append({'name':name,'path':'/var/lib/fdisbull-ci/results/case/'+name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    blobs['SHA256SUMS']=''.join(a['sha256']+'  '+a['name']+'\n' for a in binary).encode()
    checksum={'name':'SHA256SUMS','path':'/var/lib/fdisbull-ci/results/case/SHA256SUMS','size':len(blobs['SHA256SUMS']),'sha256':hashlib.sha256(blobs['SHA256SUMS']).hexdigest()}
    m['assets']=binary+[checksum];raw=json.dumps(m).encode();mhash=hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(release,'CACHE',tmp_path)
    monkeypatch.setattr(release,'cache_available',lambda:True)
    def fetch(path,size,sha,target,deadline,**kwargs):
        data=raw if path.endswith('/release.json') else blobs[Path(path).name]
        assert hashlib.sha256(data).hexdigest()==sha
        if not target.exists():target.write_bytes(data)
    monkeypatch.setattr(release,'fetch',fetch)
    chat=binary[-1];archive_ref={'path':'chat.zip','size':chat['size'],'sha256':chat['sha256']}
    monkeypatch.setattr(release,'evidence',lambda *a:(archive_ref,packages,{'manifest_sha256':hashlib.sha256(kitbytes).hexdigest()}))
    monkeypatch.setattr(release.provider._source,'run_command',lambda *a,**k:{'returncode':0,'timed_out':False,'overflow':False})
    def api(path,deadline):
        if path=='/user':return 200,{'login':'seeker-cyber-maker'}
        if path==release.API:return 200,{'id':1431097789,'full_name':release.REPO}
        return 404,None
    monkeypatch.setattr(release,'api',api)
    effects=[];remote={'draft':True,'assets':[]}
    def gh(args,deadline):
        effects.append(args[1]);
        if args[1]=='upload':remote['assets'].append({'name':Path(args[3]).name,'id':len(remote['assets'])+1})
        if args[1]=='edit':remote['draft']=False
        return {'returncode':0}
    monkeypatch.setattr(release,'gh',gh)
    def state(manifest,cache,deadline):
        if not remote['draft']:return {'status':'completed','release_url':'https://github.com/'+release.REPO+'/releases/tag/'+release.TAG,'source_sha':m['source_sha'],'draft':False,'assets':remote['assets'][:]}
        return {'status':'attention','reason':'draft-or-incomplete','draft':True,'assets':remote['assets'][:]}
    monkeypatch.setattr(release,'remote_state',state)
    payload={'manifest_path':'/var/lib/fdisbull-ci/results/case/release.json','manifest_sha256':mhash}
    assert release.run({'operation':'publish','key':'release-1','payload':payload})['status']=='completed'
    assert effects==['create']+['upload']*6+['edit']
    assert release.run({'operation':'publish','key':'release-1','payload':payload})['status']=='attention'
    assert release.run({'operation':'reconcile','key':'release-1','payload':payload})['status']=='completed'
    assert effects==['create']+['upload']*6+['edit']


def test_evidence_requires_same_source_assets_and_extended_windows(tmp_path,monkeypatch):
    m=manifest();source=m['source_sha'];items=m['assets'];packages={}
    for kind,a in zip(('core','player','sdist','tool'),items[:4]):
        packages[kind]={'name':a['name'],'sha256':a['sha256'],'size_bytes':a['size']}
    archive={'path':'chat.zip','size':items[4]['size'],'sha256':items[4]['sha256']}
    def ref(name):return {'path':name,'size':1,'sha256':'b'*64}
    receipt={'schema':'fdisbull-chat-consumer-job-v1','status':'passed','source_commit':source,'test_source_commit':source,'source_access':'absent','archive':archive,'verifier':ref('verifier.json'),'junit':ref('junit.xml')}
    verifier={'schema':'fdisbull-chat-consumer-verification-v1','status':'passed','source_commit':source,'test_source_commit':source,'archive_sha256':archive['sha256'],'network_interfaces':['lo'],'skipped':0,'native_failures':0,'windows_native_qualification':{'pe32':'passed','win16':'passed'},'extended_windows':{'pe32':{'status':'passed'},'win16':{'status':'passed'}}}
    docs={'qualification.json':{'schema':'fdisbull-ci-qualification-1','status':'qualified','source_commit':source,'package_inventory':ref('packages.json'),'chat_consumer':{'receipt':ref('receipt.json'),'verifier':ref('verifier.json'),'archive':archive}},'packages.json':{'schema':'fdisbull-package-payloads-1','source_commit':source,'tracked_worktree_dirty':False,'artifacts':packages},'receipt.json':receipt,'verifier.json':verifier}
    for name,value in docs.items():(tmp_path/name).write_text(json.dumps(value))
    (tmp_path/'junit.xml').write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>')
    monkeypatch.setattr(release,'fetch',lambda path,size,sha,target,deadline,**kw:target.write_bytes((tmp_path/'qualification.json').read_bytes()))
    monkeypatch.setattr(release,'linked',lambda root,ref,cache,deadline:tmp_path/ref['path'])
    assert release.evidence(m,tmp_path,time.monotonic()+10)[0]==archive
    verifier['windows_native_qualification']['win16']='not-tested';(tmp_path/'verifier.json').write_text(json.dumps(verifier))
    with pytest.raises(ValueError,match='extended Windows'):release.evidence(m,tmp_path,time.monotonic()+10)


def test_large_archive_identity_is_separate_from_small_evidence_limit():
    ref={'path':'.native/chat/output/fdisbull-chat-offline.zip','sha256':'a'*64,'size':1_100_000_000}
    with pytest.raises(ValueError):release.checked_ref(ref)
    assert release.checked_ref(ref,maximum=2_000_000_000)==ref


def test_gh_explicitly_selects_existing_account_and_keeps_token_in_process(monkeypatch):
    monkeypatch.setattr(release,'_GITHUB_ENV',None);calls=[]
    def runner(argv,**kw):
        calls.append((argv,kw.get('env')))
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':b'test-fixture-token\n','stderr':b''}
    monkeypatch.setattr(release.provider._source,'run_command',runner)
    env=release.github_env(time.monotonic()+30)
    assert '--user' in calls[0][0] and calls[0][0][calls[0][0].index('--user')+1]=='seeker-cyber-maker'
    assert 'GH_TOKEN' not in calls[0][1] and env['GH_TOKEN']=='test-fixture-token'
    assert release.github_env(time.monotonic()+30)==env and len(calls)==1


def test_draft_can_precede_tag_creation_but_cannot_claim_published_completion(tmp_path,monkeypatch):
    m=manifest();state={'draft':True}
    def api(path,deadline):
        if '/releases/tags/' in path:return 200,{'id':7,'tag_name':release.TAG,'draft':state['draft'],'prerelease':False,'target_commitish':m['source_sha'],'html_url':'https://github.com/'+release.REPO+'/releases/tag/'+release.TAG}
        if '/git/ref/tags/' in path:return 404,{}
        if '/assets?' in path:return 200,[]
        raise AssertionError(path)
    monkeypatch.setattr(release,'api',api)
    result=release.remote_state(m,tmp_path,time.monotonic()+10)
    assert result['status']=='attention' and result['draft'] and result['tag_state']=='not-created-draft'
    state['draft']=False
    with pytest.raises(RuntimeError,match='tag readback unknown'):release.remote_state(m,tmp_path,time.monotonic()+10)


def test_preflight_proves_existing_actor_primary_source_and_unused_tag_without_mutation(monkeypatch):
    calls=[];source='a'*40
    def api(path,deadline):
        calls.append(path)
        if path=='/user':return 200,{'login':'seeker-cyber-maker'}
        if path==release.API:return 200,{'id':1431097789,'full_name':release.REPO,'permissions':{'push':True}}
        if '/commits/' in path:return 200,{'sha':source}
        return 404,{}
    monkeypatch.setattr(release,'api',api);monkeypatch.setattr(release,'cache_available',lambda:True)
    monkeypatch.setattr(release,'mutation',lambda *a:pytest.fail('preflight must not mutate'))
    result=release.run({'operation':'preflight','key':'release-035','payload':{'source_sha':source,'version':'0.35.0','tag':'v0.35.0'}})
    assert result['status']=='ready' and result['publication_performed'] is False and len(calls)==5
