"""Disposable installer wiring and rejection tests; no native qualification."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_system_test',ROOT/'scripts/install_system.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


def ref(path):
    return {'path':str(path),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return ref(path)


def doc(path,value):return put(path,(json.dumps(value)+'\n').encode())


def fixture(tmp_path):
    source='a'*40;version='0.35.0';inp=tmp_path/'input';inp.mkdir()
    artifacts={}
    for role,name,distribution in [('core','fdisbull-0.35.0-py3-none-any.whl','fdisbull'),('player','fdisbull_player-0.35.0-py3-none-any.whl','fdisbull-player')]:
        path=inp/name
        with zipfile.ZipFile(path,'w') as z:z.writestr(distribution.replace('-','_')+'-0.35.0.dist-info/METADATA',f'Name: {distribution}\nVersion: {version}\n')
        artifacts[role]=ref(path)
    path=inp/'fdisbull-0.35.0.tar.gz'
    with tarfile.open(path,'w:gz') as t:
        data=b'Name: fdisbull\nVersion: 0.35.0\n';info=tarfile.TarInfo('fdisbull-0.35.0/PKG-INFO');info.size=len(data);t.addfile(info,io.BytesIO(data))
    artifacts['sdist']=ref(path);path=inp/'fdisbull-0.35.0-tool.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name in ('verify_system_install.py','check_local_install.py'):
            z.write(ROOT/'scripts'/name,'fdisbull-0.35.0/scripts/'+name)
        z.writestr('fdisbull-0.35.0/.github/workflows/example.yml','name: test')
        z.writestr('fdisbull-0.35.0/docs/guide.md','docs')
    artifacts['tool']=ref(path)
    wheel=put(inp/'dep-1.0-py3-none-any.whl',b'dep')
    pypi=doc(inp/'pypi.json',{'schema':'fdisbull-retained-third-party-wheel-pypi-identity-v1','files':[{'filename':Path(wheel['path']).name,'metadata_match':True,'yanked':False,'packagetype':'bdist_wheel','pypi_file_url':'https://files.pythonhosted.org/example','pypi_release_api':'https://pypi.org/pypi/dep/1/json','pypi_sha256':wheel['sha256'],'pypi_size':wheel['size']}]})
    backend=put(inp/'backend',b'synthetic backend');resource=put(inp/'kernel',b'synthetic kernel')
    log_root=inp/'logs';out=put(log_root/'share/native-logs/stdout',b'one native case');err=put(log_root/'share/native-logs/stderr',b'')
    for row in (out,err):row['path']=str(Path(row['path']).relative_to(log_root))
    delivery={'schema':'fdisbull-cdn-delivery-1','status':'passed','source_sha':source,'size':30,'sha256':'b'*64,'full_sha256':'b'*64,'resume_sha256':'b'*64,'resume_offset':10,'url':'https://release.brewsterjennings.ca/ci-0.35.0/transfer-'+'1'*32+'-fdisbull-0.35.0-'+source+'-chat-offline.zip'}
    delivery_ref=doc(inp/'delivery.json',delivery)
    result={'schema':'fdisbull-production-release-result-1','status':'complete','source_sha':source,'tag':'v'+version,'release_url':'https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v'+version,'download_url':delivery['url'],'delivery_receipt':{'path':'/var/lib/fdisbull-ci/results/delivery.json','sha256':delivery_ref['sha256']}}
    release_ref=doc(inp/'release.json',result)
    inventory={'schema':'fdisbull-package-payloads-1','source_commit':source,'tracked_worktree_dirty':False,'artifacts':{k:{'name':Path(v['path']).name,'size_bytes':v['size'],'sha256':v['sha256']} for k,v in artifacts.items()}}
    inv=doc(inp/'package.json',inventory);inv['path']='package.json'
    ci_ref=doc(inp/'ci.json',{'schema':'fdisbull-ci-qualification-1','status':'qualified','source_commit':source,'package_inventory':inv})
    native={'schema':'fdisbull-macos-native-qualification-1','status':'passed','source_commit':source,'version':version,'platform':'darwin','architecture':'arm64','backends':{'qemu':backend['sha256']},'resources':{'resources/kernel':resource['sha256']},'commands':[{'argv':['qemu-native-test'],'returncode':0,'native_cases':6,'profiles':sorted(installer.PROFILES),'stdout':out,'stderr':err}],'build_receipts':{'qemu':{'artifact_sha256':backend['sha256'],'upstream_sha256':'c'*64,'patch_sha256':None,'commands':[{'argv':['ninja','qemu-system-x86_64'],'returncode':0}]}}}
    native_ref=doc(inp/'native.json',native)
    data={'schema':'fdisbull-system-install-input-1','source_commit':source,'version':version,'artifacts':artifacts,'dependencies':[{'wheel':wheel,'pypi_identity':pypi}],'backends':{'qemu':backend},'resources':[{'destination':'resources/kernel','input':resource}],'proofs':{'ci':ci_ref,'release':release_ref,'delivery':delivery_ref,'native':native_ref},'native_log_root':str(log_root)}
    manifest=inp/'input.json';doc(manifest,data)
    return manifest,data,native


def test_input_accepts_only_bound_complete_evidence(tmp_path):
    path,data,native=fixture(tmp_path)
    assert installer.validate_input(path)['source_commit']==data['source_commit']
    native['commands'][0]['native_cases']=0
    data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    with pytest.raises(ValueError,match='native command evidence'):installer.validate_input(path)


def test_missing_build_chain_or_modified_native_backend_refuses_before_stage(tmp_path):
    path,data,native=fixture(tmp_path)
    native['build_receipts']={};data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    with pytest.raises(ValueError,match='build receipts'):installer.validate_input(path)
    native['build_receipts']={'qemu':{'artifact_sha256':data['backends']['qemu']['sha256'],'upstream_sha256':'c'*64,'patch_sha256':None,'commands':[{'argv':['ninja'],'returncode':0}]}}
    data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    Path(data['backends']['qemu']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='input identity mismatch'):installer.validate_input(path)


def test_stage_refuses_invalid_input_before_creating_base(tmp_path):
    path,data,native=fixture(tmp_path);native['commands'][0]['returncode']=1
    data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    base=tmp_path/'not-created'
    with pytest.raises(ValueError,match='native command evidence'):installer.stage(path,base)
    assert not base.exists()


def test_stage_wiring_uses_only_declared_inputs_with_simulated_verification(tmp_path,monkeypatch):
    path,data,native=fixture(tmp_path);base=tmp_path/'base'
    def fake_run(argv,*args,**kwargs):
        if 'venv' in argv:
            assert '--copies' in argv
            target=Path(argv[-1]);(target/'bin').mkdir(parents=True)
            (target/'bin/python').write_bytes(b'simulated python')
        return None
    monkeypatch.setattr(installer,'_run',fake_run)
    monkeypatch.setattr(installer,'_verify',lambda *args,**kwargs:{'status':'simulated'})
    result=installer.stage(path,base);prefix=Path(result['prefix'])
    manifest=json.loads((prefix/'share/install-manifest.json').read_text())
    assert result['status']=='staged_verified' and manifest['source_commit']==data['source_commit']
    assert manifest['backends']['qemu']['sha256']==data['backends']['qemu']['sha256']
    assert (prefix/'resources/kernel').read_bytes()==b'synthetic kernel'
    assert (prefix/'share/native-logs/stdout').read_bytes()==b'one native case'
    assert '.github/workflows/example.yml' in '\n'.join(manifest['files'])
    assert not (base/'current').exists()


def test_activation_route_failure_rolls_back_exact_selector(tmp_path,monkeypatch):
    base=tmp_path/'base';releases=base/'releases';old=releases/'old';prefix=releases/'candidate'
    old.mkdir(parents=True);(prefix/'share').mkdir(parents=True)
    (base/'current').symlink_to('releases/old')
    installer._write(prefix/'INSTALLATION.json',{'status':'staged_verified','source_commit':'a'*40,'version':'0.35.0'})
    installer._write(prefix/'share/install-manifest.json',{'schema':'fdisbull-system-install-manifest-1','source_commit':'a'*40,'version':'0.35.0','base':str(base)})
    monkeypatch.setattr(installer,'_verify',lambda *a,**kw:{'status':'simulated'})
    def fail(*args):raise ValueError('caller PATH does not resolve to verified wrapper')
    monkeypatch.setattr(installer,'_verify_resolution',fail)
    with pytest.raises(ValueError,match='caller PATH'):installer.activate(prefix,base)
    assert (base/'current').is_symlink() and (base/'current').readlink()==Path('releases/old')
    assert installer.read_json(prefix/'INSTALLATION.json')['status']=='staged_verified'
    assert old.is_dir()


@pytest.mark.parametrize('mutation,match',[
    (lambda n:n['resources'].update({'resources/kernel':'d'*64}),'qualification identity'),
    (lambda n:n['commands'][0]['profiles'].remove('win16'),'profile coverage'),
    (lambda n:n['commands'][0]['profiles'].append('win16'),'profile evidence'),
    (lambda n:n['commands'][0].update(native_cases=1),'profile evidence'),
])
def test_native_resources_and_six_profiles_fail_closed(tmp_path,mutation,match):
    path,data,native=fixture(tmp_path);mutation(native)
    data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    with pytest.raises(ValueError,match=match):installer.validate_input(path)


def test_dosbox_build_requires_a_patched_source_receipt(tmp_path):
    path,data,native=fixture(tmp_path)
    data['backends']={'dosbox-stable':data['backends']['qemu']}
    native['backends']={'dosbox-stable':data['backends']['dosbox-stable']['sha256']}
    native['build_receipts']={'dosbox-stable':native['build_receipts']['qemu']}
    data['proofs']['native']=doc(Path(data['proofs']['native']['path']),native);doc(path,data)
    with pytest.raises(ValueError,match='build chain'):installer.validate_input(path)


def test_simulated_activate_and_rollback_restore_previous_selector(tmp_path,monkeypatch):
    base=tmp_path/'base';releases=base/'releases';old=releases/'old';prefix=releases/'candidate'
    old.mkdir(parents=True);(prefix/'share').mkdir(parents=True);(base/'current').symlink_to('releases/old')
    installer._write(prefix/'INSTALLATION.json',{'status':'staged_verified','source_commit':'a'*40,'version':'0.35.0'})
    installer._write(prefix/'share/install-manifest.json',{'schema':'fdisbull-system-install-manifest-1','source_commit':'a'*40,'version':'0.35.0','base':str(base)})
    monkeypatch.setattr(installer,'_verify',lambda *a,**kw:{'status':'simulated'})
    monkeypatch.setattr(installer,'_verify_resolution',lambda *a:{'status':'simulated'})
    monkeypatch.setattr(installer,'_run',lambda *a,**kw:{'status':'passed'})
    result=installer.activate(prefix,base)
    assert result['status']=='active_verified' and (base/'current').readlink()==Path('releases/candidate')
    assert installer.rollback(prefix,base)['restored_selector']=='releases/old'
    assert (base/'current').readlink()==Path('releases/old') and old.is_dir()


def test_bounded_runner_captures_real_command_and_rejects_failure(tmp_path):
    import sys
    work=tmp_path/'work';work.mkdir()
    assert installer._run([sys.executable,'-c','import json; print(json.dumps({"ok": True}))'],work,json_output=True)=={'ok':True}
    with pytest.raises(ValueError,match='command failed'):
        installer._run([sys.executable,'-c','raise SystemExit(1)'],work)


def test_existing_native_routes_require_all_selected_backend_targets(tmp_path):
    prefix=tmp_path/'candidate';native=prefix/'backend/native-macos-arm64';native.mkdir(parents=True)
    refs={}
    for name in ('dosbox-x','dosbox-layers','qemu-system-x86_64'):
        path=native/name;path.write_bytes(('authored route fixture '+name).encode())
        refs[name]={'path':str(path.relative_to(prefix)),'sha256':installer.digest(path)}
    link=tmp_path/'dosbox';link.symlink_to(native/'dosbox-x')
    wrapper=tmp_path/'qemu';wrapper.write_text('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd /Users/Shared/fDisBull/current && pwd -P)\nexec "$ROOT/backend/native-macos-arm64/qemu-system-x86_64" "$@"\n')
    assert installer._verify_backend_resolution(prefix,{'backends':refs},dosbox_route=link,qemu_route=wrapper)['targets']==sorted(refs)
    with pytest.raises(ValueError,match='backends missing'):
        installer._verify_backend_resolution(prefix,{'backends':{'qemu':refs['qemu-system-x86_64']}},dosbox_route=link,qemu_route=wrapper)
    (native/'dosbox-x').write_bytes(b'changed')
    with pytest.raises(ValueError,match='target mismatch'):
        installer._verify_backend_resolution(prefix,{'backends':refs},dosbox_route=link,qemu_route=wrapper)
