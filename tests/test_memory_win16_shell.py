"""Authored Win16 emission, ownership and genuine NE admission contracts.

Ordinary tests never execute image bytes. The opt-in SDK test admits only the
actual compiler's NE files, without making native execution or game claims.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import uuid
import zlib

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull import udc_memory_layers as layers
from fdisbull.udc_memory_win16_shell import (emit_memory_win16_shell,
    compile_memory_win16_shell,seal_memory_win16_shell,inspect_windows_ne)
from test_memory_region_shell import (model,initial,shell_plan,exact_selections,region_plan)


def emit_fixture(root,*,destination=None,plan=None,program=None,initial_words=None,with_regions=True,emitter=emit_memory_win16_shell):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    source=root/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    canonical=deepcopy(model() if program is None else program)
    plan=deepcopy(shell_plan() if plan is None else plan);plan['events']['quit_index']=15
    words=initial() if initial_words is None else initial_words
    destination=root/'native' if destination is None else Path(destination)
    with Project.create(root/'authored.fdb',source,image='com') as project:
        if with_regions:
            selections=exact_selections(project,canonical);regions=region_plan(project,canonical)
            cuts={'format':'fdisbull-memory-cuts-2','module_uil_sha256':digest(canonical),
                'cuts':[{'caller':'advance','entry':'advance.update','callee':'update'}]}
        else:
            selections={};regions=cuts=None
            plan['bindings'].pop('update',None);plan['outputs'].pop('update',None)
            arena={'arena':{'type':'u32-array','words':canonical['memory']['words']}}
            for backend,target in [('wasm','wasm32-memory-1'),('webgpu','webgpu-wgsl-memory-1')]:
                bindings={}
                for function in canonical['functions']:
                    contract=layers.register_contract(project,{'format':'fdisbull-block-contract-1',
                        'name':'owner.'+function,'inputs':arena,'outputs':arena,
                        'behavior':{'kind':'memory-uil','program':canonical,'function':function}})
                    layer=layers.register_layer(project,{'format':'fdisbull-udl-layer-1','name':backend+'.'+function,
                        'contract':contract['id'],'implementation':{'backend':'memory-uil','target':target,
                            'program':canonical,'function':function}})
                    bindings[function]=layer['id']
                selections[backend]=layers.select_layers(project,'owner.'+backend,bindings,
                    program=canonical,target=target)['id']
        before={key:deepcopy(project.udl_selection_info(value,full=True)) for key,value in selections.items()}
        result=emitter(project,selections,plan,words,destination,cuts=cuts,regions=regions)
        assert {key:project.udl_selection_info(value,full=True) for key,value in selections.items()}==before
    assert source.read_bytes()==bytes.fromhex('b8004ccd21')
    return result,destination


def test_win16_emission_preserves_source_selections_uil_and_initial_payload(tmp_path):
    manifest,directory=emit_fixture(tmp_path/'input')
    assert manifest['stage']=='source-only' and manifest['native_execution'] is False
    assert manifest['source_to_uil'] is False
    assert manifest['architecture']=='x86-16' and manifest['platform']=='windows-x86-16'
    assert manifest['program']==model() and manifest['module_uil_sha256']==digest(model())
    assert manifest['module_udl_sha256']==digest({**model(),'role':'udl'})
    assert manifest['execution_uil_sha256']==digest(manifest['execution_program'])
    assert manifest['execution_uil_sha256']!=manifest['module_uil_sha256']
    assert manifest['runtime']['chrome_encoding']=='cp1252'
    assert manifest['source_selections'] and manifest['source_endpoints']
    assert manifest['runtime']['region_controls'][0]['name']=='update'
    assert {v['name'] for v in manifest['runtime']['region_controls'][0]['variants']}=={'original','alternate','outside'}
    raw=(directory/'INITIAL.BIN').read_bytes();assert raw[:8]==b'FDBINI1\0'
    assert struct.unpack_from('<I',raw,8)[0]==16 and list(struct.unpack('<16I',raw[12:]))==initial()
    assert zlib.crc32(raw[12:])==manifest['runtime']['initial_data_crc32']
    for name,expected in manifest['source_artifacts'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==expected
    assert (directory/'source-shell.json').read_bytes()==(directory/'native-shell.json').read_bytes()
    with Project(tmp_path/'input'/'authored.fdb') as project:
        for backend,target in [('wasm','wasm32-memory-1'),('webgpu','webgpu-wgsl-memory-1')]:
            source=project.udl_selection_info(manifest['source_selections'][backend],full=True)['document']
            assert source['target']==target and source['program']==model()
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_win16_cp1252_chrome_and_fractional_clock_are_explicit(tmp_path):
    plan=shell_plan();plan['title']='Crème “café” €';plan['help']='Quote " and slash \\'
    plan['events']['tick_ms']=54.92549323064085
    manifest,directory=emit_fixture(tmp_path/'input',plan=plan)
    header=(directory/'M16CFG.H').read_text()
    assert '\\350' in header and '\\223' in header and '\\351' in header and '\\200' in header
    assert '\\042' in header and '\\134' in header
    assert format(plan['events']['tick_ms'],'.17g') in header
    assert manifest['plan']['events']['tick_ms']==plan['events']['tick_ms']
    assert manifest['plan']['title']==plan['title']


def test_win16_mouse_only_plan_uses_c89_placeholder_with_zero_key_count(tmp_path):
    plan=shell_plan();plan['keymap']={}
    manifest,directory=emit_fixture(tmp_path/'input',plan=plan)
    header=(directory/'M16CFG.H').read_text()
    assert 'fdb_keys[] = {{0}};' in header
    assert manifest['plan']['keymap']=={} and manifest['runtime']['key_order']==[]


def test_win16_agent_emit_dispatch_preserves_bound_source_without_compiling(tmp_path):
    from fdisbull.udc_api import invoke
    def emitter(project,selections,plan,initial,destination,**options):
        return invoke(project,'emit-memory-win16-shell',{'selections':selections,'plan':plan,
            'initial':initial,'destination':str(destination),**options})
    manifest,directory=emit_fixture(tmp_path/'input',emitter=emitter)
    assert manifest['stage']=='source-only' and manifest['native_execution'] is False
    assert manifest['source_selections'] and manifest['module_uil_sha256']==digest(model())
    assert not (directory/'PROGRAM.EXE').exists() and not (directory/'PROBE.EXE').exists()


def test_win16_agent_build_dispatch_leaves_source_recipe_when_sdk_is_absent(tmp_path):
    from fdisbull.udc_api import invoke
    def emitter(project,selections,plan,initial,destination,**options):
        return invoke(project,'build-memory-win16-shell',{'selections':selections,'plan':plan,
            'initial':initial,'destination':str(destination),'c_compiler':'/does-not-exist',
            'linker':'/does-not-exist',**options})
    with pytest.raises(ValueError,match='separate Open Watcom'):
        emit_fixture(tmp_path/'input',emitter=emitter)
    directory=tmp_path/'input/native';manifest=json.loads((directory/'native-shell.json').read_text())
    assert manifest['stage']=='source-only' and manifest['native_execution'] is False
    assert manifest['source_to_uil'] is False and manifest['commands']
    assert (directory/'source-shell.json').read_bytes()==(directory/'native-shell.json').read_bytes()
    assert not (directory/'PROGRAM.EXE').exists() and not (directory/'PROBE.EXE').exists()
    assert (tmp_path/'input/authored.com').read_bytes()==bytes.fromhex('b8004ccd21')


@pytest.mark.parametrize('text',['Unsupported snowman ☃','NUL\0inside'])
def test_win16_refuses_unrepresentable_chrome_before_output(tmp_path,text):
    plan=shell_plan();plan['title']=text;output=tmp_path/'native'
    with pytest.raises(ValueError,match='CP1252|NUL'):
        emit_fixture(tmp_path/'input',destination=output,plan=plan)
    assert not output.exists()


def test_win16_refuses_arena_over_profile_limit(tmp_path):
    program=model();program['memory']['words']=131073
    with pytest.raises(ValueError,match='profile'):
        emit_fixture(tmp_path/'input',program=program,initial_words=initial()+[0]*(131073-16),with_regions=False)
    assert not (tmp_path/'input/native').exists()


def test_win16_refuses_indexed_frame_over_segment_limit(tmp_path):
    program=model();program['memory']['words']=70000;plan=shell_plan()
    plan['frame'].update(offset=16,width=1024,height=65)
    plan['commit_ranges'].append([16,1024*65]);plan['replace_ranges'].append([16,1024*65])
    with pytest.raises(ValueError,match='indexed frame'):
        emit_fixture(tmp_path/'input',program=program,plan=plan,initial_words=initial()+[0]*(70000-16),with_regions=False)


def test_win16_refuses_overlapping_input_service_fields(tmp_path):
    plan=shell_plan();plan['events']['scan']=plan['events']['ascii']
    with pytest.raises(ValueError,match='distinct'):
        emit_fixture(tmp_path/'input',plan=plan)


def test_win16_emission_refuses_existing_path_and_git_ancestry(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'keep';sentinel.write_bytes(b'unchanged')
    with pytest.raises(ValueError,match='new private'):
        emit_fixture(tmp_path/'input1',destination=existing)
    assert sentinel.read_bytes()==b'unchanged'
    git=tmp_path/'fake-git';git.mkdir();(git/'.git').mkdir()
    with pytest.raises(ValueError,match='outside Git'):
        emit_fixture(tmp_path/'input2',destination=git/'native')


def test_win16_compiler_rejects_changed_recipe_before_execution(tmp_path):
    manifest,directory=emit_fixture(tmp_path/'input')
    manifest['commands'][0][-1]='../original.bin'
    (directory/'native-shell.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='recipe'):
        compile_memory_win16_shell(directory,c_compiler='/does-not-exist',linker='/does-not-exist')


@pytest.mark.parametrize('change',['response-file','missing-common'])
def test_win16_rejects_forged_source_set_even_with_matching_receipts_and_recipe(tmp_path,change):
    from fdisbull.udc_memory_win16_shell import _win16_recipe
    manifest,directory=emit_fixture(tmp_path/'input')
    if change=='response-file':
        contents=b'-fo=unexpected.obj\n';(directory/'@FLAGS.C').write_bytes(contents)
        manifest['source_artifacts']['@FLAGS.C']=hashlib.sha256(contents).hexdigest()
    else:del manifest['source_artifacts']['M16COMM.C']
    with pytest.raises(ValueError,match='source|realization|artifact'):
        manifest['commands']=_win16_recipe(manifest)
        for name in ('native-shell.json','source-shell.json'):(directory/name).write_text(json.dumps(manifest))
        compile_memory_win16_shell(directory,c_compiler='/does-not-exist',linker='/does-not-exist')


def test_win16_refuses_changed_source_before_seal(tmp_path):
    _,directory=emit_fixture(tmp_path/'input');path=directory/'M16CORE.C';path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='source artifact changed'):
        seal_memory_win16_shell(directory)


@pytest.mark.parametrize('name',['native-shell.json','source-shell.json','M16CORE.C'])
def test_win16_rejects_symlink_receipt_or_source(tmp_path,name):
    _,directory=emit_fixture(tmp_path/'input');original=directory/name
    retained=tmp_path/'retained';retained.write_bytes(original.read_bytes())
    expected=retained.read_bytes();original.unlink();original.symlink_to(retained)
    with pytest.raises(ValueError,match='owned regular Win16 artifact required: '+re.escape(name)):
        seal_memory_win16_shell(directory)
    assert retained.read_bytes()==expected


@pytest.mark.parametrize('name',['PROGRAM.EXE','PROBE.EXE','M16CORE.OBJ','PROGRAM.MAP'])
@pytest.mark.parametrize('link_kind',['symlink','hardlink'])
def test_win16_rejects_linked_outputs_before_invoking_compiler(tmp_path,name,link_kind):
    _,directory=emit_fixture(tmp_path/'input');retained=tmp_path/'original.bin';retained.write_bytes(b'original remains unchanged')
    if link_kind=='symlink':(directory/name).symlink_to(retained)
    else:os.link(retained,directory/name)
    with pytest.raises(ValueError,match='owned fresh compiler outputs required'):
        compile_memory_win16_shell(directory,c_compiler=sys.executable,linker=sys.executable)
    assert retained.read_bytes()==b'original remains unchanged'


@pytest.mark.parametrize('name',['native-shell.json','source-shell.json'])
def test_win16_rejects_hardlinked_receipts_before_seal(tmp_path,name):
    _,directory=emit_fixture(tmp_path/'input');retained=tmp_path/'retained';os.link(directory/name,retained)
    expected=retained.read_bytes()
    with pytest.raises(ValueError,match='owned regular Win16 artifact required: '+re.escape(name)):
        seal_memory_win16_shell(directory)
    assert retained.read_bytes()==expected


def test_win16_build_cannot_hide_git_ancestor_behind_parent_alias(tmp_path):
    _,directory=emit_fixture(tmp_path/'input')
    git=tmp_path/'fake-git';(git/'.git').mkdir(parents=True);(git/'deep').mkdir()
    moved=git/'deep/native';shutil.move(directory,moved)
    alias=tmp_path/'alias';alias.symlink_to(git/'deep',target_is_directory=True)
    with pytest.raises(ValueError,match='private|Git'):
        compile_memory_win16_shell(alias/'native',c_compiler='/does-not-exist',linker='/does-not-exist')


@pytest.mark.parametrize('data',[b'',b'MZ',b'PE\0\0'+bytes(128),
    b'MZ'+bytes(58)+struct.pack('<I',0xffffffff)+bytes(128),
    b'MZ'+bytes(58)+struct.pack('<I',64)+b'NE'+bytes(62)])
def test_ne_parser_refuses_malformed_samples_without_native_claim(data):
    with pytest.raises(ValueError):inspect_windows_ne(data)


@pytest.mark.skipif(not os.environ.get('FDISBULL_WIN16_VM_CLIENT'),reason='requires explicit genuine OpenWatcom guest')
def test_win16_seals_only_real_compiler_ne_artifacts_and_keeps_receipt_immutable(tmp_path):
    manifest,directory=emit_fixture(tmp_path/'input')
    source_receipt=(directory/'source-shell.json').read_bytes()
    spec=importlib.util.spec_from_file_location('fdb_win16_shell_guest',os.environ['FDISBULL_WIN16_VM_CLIENT'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);client=module.Client()
    job='shell16-'+uuid.uuid4().hex[:12]
    for name in manifest['source_artifacts']:client.put(job,name,(directory/name).read_bytes())
    evidence=[]
    for recipe in manifest['commands']:
        result=client.run(job,recipe,timeout=180);assert result['exit_code']==0,(recipe,result)
        evidence.append({'command':recipe,'exit_code':result['exit_code']})
    outputs=[name[:-2]+'.OBJ' for name in manifest['source_artifacts'] if name.endswith('.C')]
    outputs+=['PROGRAM.EXE','PROBE.EXE','PROGRAM.MAP','PROBE.MAP']
    for name in outputs:(directory/name).write_bytes(client.get(job,name))
    admitted=seal_memory_win16_shell(directory,compiler_evidence=evidence)
    assert admitted['stage']=='compiled' and admitted['native_execution'] is False
    assert admitted['source_to_uil'] is False and admitted['source_selections']==manifest['source_selections']
    assert admitted['images']['PROGRAM.EXE']['format']=='NE'
    assert admitted['images']['PROBE.EXE']['target_os']=='Windows'
    assert (directory/'source-shell.json').read_bytes()==source_receipt
    assert seal_memory_win16_shell(directory)==admitted
    executable=directory/'PROGRAM.EXE';data=executable.read_bytes()
    invalid=bytearray(data);offset=struct.unpack_from('<I',data,60)[0];invalid[offset+54]=1
    with pytest.raises(ValueError,match='Windows NE'):
        inspect_windows_ne(bytes(invalid))
    executable.write_bytes(data+b'changed')
    with pytest.raises(ValueError,match='immutable'):
        seal_memory_win16_shell(directory)
