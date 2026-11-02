"""Authored native build/admission checks, separate from execution qualification."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import pytest

from fdisbull.common_uil import digest
from fdisbull.uil_native import (emit_native_program, compile_native_program,
                                seal_native_program, build_native_program)


def fixture(typ='u16'):
    function={'variables':[{'type':typ}],'constants':[], 'inputs':[0], 'outputs':[0],
              'max_steps':100, 'body':[]}
    if typ=='u16':
        function['constants']=[{'type':'u16'}]
        function['body']=[{'op':'set','dst':0,'value':{'op':'add','type':'u16',
                            'args':[{'var':0},{'const':0}]}}]
    program={'format':'fdisbull-common-uil-1','capabilities':['core.scalar@1'],
             'imports':[],'functions':[function],'entry':0}
    presentation={'format':'fdisbull-uil-presentation-1','program_sha256':digest(program),
                  'functions':[{'initial':['' if typ=='text' else '0'],
                                'constants':['1'] if typ=='u16' else []}], 'resources':[]}
    catalog={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
    plan={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(program),
          'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':8}
    return program,presentation,catalog,plan


def rewrite_manifest(directory, change):
    path=directory/'source-manifest.json'
    data=json.loads(path.read_text());change(data)
    data.pop('realization_sha256')
    data['realization_sha256']=digest(data)
    path.write_text(json.dumps(data))


def test_emit_admits_complete_closure_and_retains_all_sources(tmp_path):
    docs=fixture();before=deepcopy(docs);destination=tmp_path/'native'
    result=emit_native_program(*docs,destination,target='linux-x64')
    assert docs==before and result['stage']=='source-emitted'
    assert result['execution'] is False and result['host_effect_execution'] is False
    for name,sha in result['sources'].items():
        assert hashlib.sha256((destination/name).read_bytes()).hexdigest()==sha
    assert result['closure']['link_lock']['closure']['program_sha256']==digest(docs[0])
    assert not (destination/result['executable']).exists()


@pytest.mark.parametrize('bad',['provider','version','text','target'])
def test_unsupported_or_unknown_native_bindings_refuse_before_output(tmp_path,bad):
    destination=tmp_path/'refused';kwargs={'target':'macos-arm64'};docs=fixture()
    if bad=='provider':kwargs['module_requirements']={'functions':{'0':{'pins':{'requirement:'+'0'*64:'provider:'+'0'*64}}}}
    elif bad=='version':kwargs['module_requirements']={'functions':{'0':{'requires':[{'intrinsic':'sound.play','version':2}]}}}
    elif bad=='text':docs=fixture('text')
    else:kwargs['target']='unknown-native-target'
    with pytest.raises(ValueError):emit_native_program(*docs,destination,**kwargs)
    assert not destination.exists()


@pytest.mark.parametrize('change',['source','abi','commands','generator','builder','profile','execution','extra'])
def test_rehashed_source_manifest_tampering_refuses_before_compiler(tmp_path,change):
    directory=tmp_path/'native';manifest=emit_native_program(*fixture(),directory,target='linux-x64')
    if change=='source':
        name=next(iter(manifest['sources']));(directory/name).write_text('/* replaced source */')
    else:
        def mutate(data):
            if change=='abi':data['abi']['word']='native-pointer'
            elif change=='commands':data['compile_commands'][0].append('-DBAD_RECIPE=1')
            elif change=='generator':data['generator_sha256']='0'*64
            elif change=='builder':data['builder_sha256']='0'*64
            elif change=='profile':data['source_profile']['scope']='unqualified replacement claim'
            elif change=='execution':data['host_effect_execution']=True
            else:data['extra_native_authority']=True
        rewrite_manifest(directory,mutate)
    with pytest.raises(ValueError):compile_native_program(directory,c_compiler='/nonexistent/compiler-must-never-run')
    assert not (directory/'build.json').exists()
    assert not any((directory/name).exists() for name in manifest['objects'])


def test_source_artifact_symlink_and_existing_destination_refuse(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();(existing/'keep').write_text('kept')
    with pytest.raises(ValueError):emit_native_program(*fixture(),existing)
    assert (existing/'keep').read_text()=='kept'
    link=tmp_path/'link';link.symlink_to(existing,target_is_directory=True)
    with pytest.raises(ValueError):emit_native_program(*fixture(),link)
    output=tmp_path/'native';manifest=emit_native_program(*fixture(),output)
    source=next(iter(manifest['sources']));retained=tmp_path/'retained.c'
    (output/source).rename(retained);(output/source).symlink_to(retained)
    with pytest.raises(ValueError):compile_native_program(output,c_compiler='/nonexistent/compiler-must-never-run')
    assert not (output/'build.json').exists()


def test_output_below_git_marker_and_hardlinked_source_refuse(tmp_path):
    repository=tmp_path/'authored-git-marker';repository.mkdir()
    (repository/'.git').write_text('gitdir: /authored/fixture-only')
    with pytest.raises(ValueError,match='Git'):
        emit_native_program(*fixture(),repository/'private-output')
    assert not (repository/'private-output').exists()
    output=tmp_path/'native';manifest=emit_native_program(*fixture(),output)
    source=next(iter(manifest['sources']))
    os.link(output/source,tmp_path/'linked-source.c')
    with pytest.raises(ValueError,match='regular'):
        compile_native_program(output,c_compiler='/nonexistent/compiler-must-never-run')


@pytest.mark.parametrize('kind',['symlink','missing'])
def test_compiler_tmp_directory_cannot_escape_or_fall_back(tmp_path,kind):
    output=tmp_path/'native';emit_native_program(*fixture(),output,target='linux-x64')
    (output/'tmp').rmdir()
    outside=tmp_path/'outside';outside.mkdir()
    if kind=='symlink':(output/'tmp').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='tmp|temporary|directory'):
        compile_native_program(output,c_compiler='/nonexistent/compiler-must-never-run')
    assert not list(outside.iterdir())


def test_compiler_target_mismatch_leaves_sources_without_native_artifacts(tmp_path):
    output=tmp_path/'native';manifest=emit_native_program(*fixture(),output,target='windows-x64')
    # This authored negative fixture identifies itself as a Linux compiler. It
    # never reports a successful compilation or manufactures a native image.
    compiler=tmp_path/'wrong-compiler'
    compiler.write_text('#!'+sys.executable+'\nimport sys\n'
                        'print("authored-linux-compiler" if "--version" in sys.argv else "x86_64-linux-gnu")\n')
    compiler.chmod(0o700)
    with pytest.raises(ValueError,match='target'):
        compile_native_program(output,c_compiler=compiler)
    assert not (output/'build.json').exists()
    assert not any((output/name).exists() for name in manifest['objects']+[manifest['executable']])


def test_existing_compile_artifact_and_incomplete_seal_refuse(tmp_path):
    output=tmp_path/'native';manifest=emit_native_program(*fixture(),output,target='linux-x64')
    with pytest.raises(ValueError,match='incomplete'):seal_native_program(output)
    (output/manifest['objects'][0]).write_bytes(b'authored incomplete object')
    with pytest.raises(ValueError,match='already exist'):compile_native_program(output)
    assert not (output/'build.json').exists()


def test_compiler_probe_timeout_is_a_bounded_refusal(tmp_path,monkeypatch):
    import fdisbull.uil_native as native
    output=tmp_path/'native';emit_native_program(*fixture(),output,target='linux-x64')
    def expired(command,**kwargs):
        raise subprocess.TimeoutExpired(command,kwargs.get('timeout',10))
    monkeypatch.setattr(native.subprocess,'run',expired)
    with pytest.raises(ValueError,match='probe|timeout'):
        compile_native_program(output,c_compiler=sys.executable)
    assert not (output/'build.json').exists()


def test_unknown_provider_in_a_rehashed_source_lock_refuses_before_compile(tmp_path):
    output=tmp_path/'native';emit_native_program(*fixture(),output,target='linux-x64')
    def mutate(manifest):
        closure=manifest['closure'];lock=closure['link_lock']
        lock['builtin_provider_ids'][0]='provider:'+'0'*64
        lock['sha256']=digest({k:v for k,v in lock.items() if k!='sha256'})
        manifest['closure_sha256']=digest(closure)
        manifest['link_lock_sha256']=lock['sha256']
    rewrite_manifest(output,mutate)
    with pytest.raises(ValueError):compile_native_program(output,c_compiler='/nonexistent/compiler-must-never-run')
    assert not (output/'build.json').exists()


def test_direct_json_and_cli_source_link_build_entry_points(tmp_path):
    from fdisbull.cli import respond
    docs=fixture();params=dict(zip(('program','presentation','catalog','orchestration'),docs))
    response=respond({'method':'uil-link','params':{**params,'target':'linux-x64'}})
    assert response['ok'] and response['result']['target']=='linux-x64'
    emitted=respond({'method':'uil-compile','params':{**params,'target':'linux-x64',
                     'output':str(tmp_path/'api-native'),'source_only':True}})
    assert emitted['ok'] and emitted['result']['stage']=='source-emitted'
    failure=respond({'method':'uil-build','params':{'output':str(tmp_path/'api-native'),'c_compiler':'/nonexistent/compiler'}})
    assert failure['ok'] is False
    failed_seal=respond({'method':'uil-seal','params':{'output':str(tmp_path/'api-native')}})
    assert failed_seal['ok'] is False
    names=('program','presentation','catalog','orchestration');files={}
    for name,value in zip(names,docs):
        path=tmp_path/(name+'.json');path.write_text(json.dumps(value));files[name]=str(path)
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).parents[1]/'src')
    command=[sys.executable,'-m','fdisbull','uil-link',files['program'],'--presentation',files['presentation'],
             '--catalog',files['catalog'],'--orchestration',files['orchestration'],'--target','linux-x64']
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['target']=='linux-x64'
    source_command=[sys.executable,'-m','fdisbull','uil-compile',files['program'],
        '--presentation',files['presentation'],'--catalog',files['catalog'],
        '--orchestration',files['orchestration'],'--target','linux-x64',
        '--source-only','--output',str(tmp_path/'cli-native')]
    source_result=subprocess.run(source_command,env=env,capture_output=True,text=True,timeout=20)
    assert source_result.returncode==0,source_result.stdout+source_result.stderr
    assert json.loads(source_result.stdout)['stage']=='source-emitted'
    for command in ('uil-build','uil-seal'):
        refusal_command=[sys.executable,'-m','fdisbull',command,str(tmp_path/'cli-native')]
        if command=='uil-build':refusal_command += ['--c-compiler','/nonexistent/compiler']
        result=subprocess.run(refusal_command,
                              env=env,capture_output=True,text=True,timeout=20)
        assert result.returncode==1
        assert json.loads(result.stdout)['status']=='refused'


@pytest.mark.skipif(sys.platform!='darwin' or platform.machine()!='arm64',reason='actual Apple ARM64 compiler/image admission')
def test_real_macos_compile_and_lief_sealing_are_distinct_from_execution(tmp_path):
    compiler=shutil.which('clang')
    if not compiler:pytest.skip('Apple ARM64 compiler unavailable')
    output=tmp_path/'native'
    built=build_native_program(*fixture(),output,target='macos-arm64',c_compiler=compiler)
    assert built['stage']=='compiled'
    assert built['image']=={'format':'Mach-O','architecture':'arm64','kind':'executable'}
    assert built['execution'] is False and built['host_effect_execution'] is False
    assert built['compiler']['commands'] and all(c['returncode']==0 for c in built['compiler']['commands'])
    assert json.loads((output/'build.json').read_text())['realization_sha256']==built['realization_sha256']
    with pytest.raises(ValueError,match='sealed'):seal_native_program(output)


def _compile_external_sources(output):
    compiler=shutil.which('clang')
    if not compiler:pytest.skip('Apple ARM64 compiler unavailable')
    manifest=emit_native_program(*fixture(),output,target='macos-arm64')
    env=os.environ.copy();env['TMPDIR']=str(output/'tmp')
    for command in manifest['compile_commands']:
        completed=subprocess.run([compiler,*command[1:]],cwd=output,env=env,
                                 capture_output=True,text=True,timeout=45)
        assert completed.returncode==0,completed.stderr
    return manifest


@pytest.mark.skipif(sys.platform!='darwin' or platform.machine()!='arm64',reason='actual externally compiled ARM64 artifacts')
def test_external_mac_seal_api_binds_real_objects_and_executable(tmp_path):
    from fdisbull.cli import respond
    output=tmp_path/'external-native';manifest=_compile_external_sources(output)
    response=respond({'method':'uil-seal','params':{'output':str(output),
        'compiler_evidence':{'scope':'supplied evidence for authored external compile; not execution'}}})
    assert response['ok'],response
    sealed=response['result']
    assert sealed['stage']=='compiled' and sealed['execution'] is False
    for name in manifest['objects']+[manifest['executable']]:
        assert sealed['artifacts'][name]==hashlib.sha256((output/name).read_bytes()).hexdigest()


@pytest.mark.skipif(sys.platform!='darwin' or platform.machine()!='arm64',reason='real executable needed to isolate object-admission refusal')
def test_external_seal_refuses_corrupted_object_even_with_real_executable(tmp_path):
    output=tmp_path/'external-native';manifest=_compile_external_sources(output)
    (output/manifest['objects'][0]).write_bytes(b'authored invalid object header')
    with pytest.raises(ValueError,match='object|Mach-O'):seal_native_program(output)
    assert not (output/'build.json').exists()
