"""Owned native ARM64 shell composition using source-defined word fixtures."""
from copy import deepcopy
import ctypes
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys
import threading

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull.udc_memory_macos import build_memory_macos_shell


def _fixture(name):
    spec=importlib.util.spec_from_file_location('native_fixture_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


region_fixture=_fixture('test_memory_region_shell')
cut_fixture=_fixture('test_memory_cut_shell')
NATIVE=sys.platform=='darwin' and platform.machine()=='arm64' and shutil.which('clang')
pytestmark=pytest.mark.skipif(not NATIVE,reason='requires native macOS ARM64 execution')
U32=ctypes.c_uint32
SIZE=ctypes.c_size_t
PTR=ctypes.POINTER(U32)


class Shell:
    def __init__(self,root):
        self.manifest=json.loads((root/'native-shell.json').read_text())
        self.library=ctypes.CDLL(str(root/self.manifest['library']))
        signatures={
            'fdb_word_count':([],SIZE),'fdb_words':([],PTR),
            'fdb_copy_words':([PTR,SIZE],ctypes.c_int),
            'fdb_function_index':([ctypes.c_char_p],ctypes.c_int),
            'fdb_call':([SIZE,PTR,PTR,SIZE,ctypes.c_int],ctypes.c_int),
            'fdb_dispatch':([PTR,PTR,SIZE,ctypes.c_int],ctypes.c_int),
            'fdb_initialize':([U32],ctypes.c_int),
            'fdb_select_region':([SIZE,SIZE],ctypes.c_int),
            'fdb_selected_region':([SIZE],ctypes.c_int),
            'fdb_replace_words':([PTR,SIZE],ctypes.c_int),
            'fdb_revision':([],ctypes.c_uint64),
            'fdb_invocation_count':([SIZE],ctypes.c_uint64),
            'fdb_region_invocation_count':([SIZE,SIZE],ctypes.c_uint64),
            'fdb_last_steps':([],U32),'fdb_last_error':([],ctypes.c_char_p),
            'fdb_close':([],None),'fdb_closed':([],ctypes.c_int),
        }
        for name,(args,result) in signatures.items():
            fn=getattr(self.library,name);fn.argtypes=args;fn.restype=result
        self.words_count=self.library.fdb_word_count()
        self.functions=self.manifest['runtime']['function_order']
        self.regions=sorted((self.manifest.get('regions') or {}).get('slots',{}))

    def words(self):
        result=(U32*self.words_count)()
        assert self.library.fdb_copy_words(result,self.words_count)==0
        return list(result)

    def index(self,name):
        index=self.library.fdb_function_index(name.encode())
        assert index>=0
        assert self.functions[index]==name
        return index

    def invoke(self,name,patch=None,render=True):
        patch=patch or {}
        indices=(U32*len(patch))(*patch)
        values=(U32*len(patch))(*patch.values())
        return self.library.fdb_call(self.index(name),indices,values,len(patch),int(render))

    def replace(self,words):
        return self.library.fdb_replace_words((U32*len(words))(*words),len(words))

    def choice(self,region,name):
        slot=self.regions.index(region)
        variants=sorted(self.manifest['regions']['slots'][region]['variants'])
        return self.library.fdb_select_region(slot,variants.index(name))

    def region_count(self,region,name):
        slot=self.regions.index(region)
        variant=sorted(self.manifest['regions']['slots'][region]['variants']).index(name)
        return self.library.fdb_region_invocation_count(slot,variant)


def build_regions(tmp_path,program=None):
    source=tmp_path/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    canonical=program if program is not None else region_fixture.model();plan=region_fixture.shell_plan()
    with Project.create(tmp_path/'region.fdb',source,image='com') as project:
        choices=region_fixture.exact_selections(project,canonical)
        region_plan=region_fixture.region_plan(project,canonical)
        result=build_memory_macos_shell(project,choices,plan,region_fixture.initial(),tmp_path/'native',
            cuts={'format':'fdisbull-memory-cuts-2','module_uil_sha256':digest(canonical),
                'cuts':[{'caller':'advance','entry':'advance.update','callee':'update'}]},
            regions=region_plan,with_app=False)
    return Shell(tmp_path/'native'),result


def test_native_builder_preserves_canonical_source_and_realization_identity(tmp_path):
    shell,result=build_regions(tmp_path)
    manifest=shell.manifest
    assert manifest['program']==region_fixture.model()
    assert manifest['module_uil_sha256']==digest(region_fixture.model())
    assert manifest['plan']==region_fixture.shell_plan()
    assert manifest['execution_uil_sha256']==digest(manifest['execution_program'])
    assert manifest['execution_uil_sha256']!=manifest['module_uil_sha256']
    assert result==manifest and manifest['architecture']=='arm64'
    assert manifest['native_execution'] is False and manifest['application'] is None
    assert shell.functions==['advance','draw','update']
    assert shell.words()==region_fixture.initial()
    for name,variant in manifest['regions']['slots']['update']['variants'].items():
        expected=digest(variant['program'])
        assert variant['identities']['wasm']['implementation_uil_sha256']==expected
        assert variant['identities']['webgpu']['implementation_uil_sha256']==expected
        assert expected!=manifest['module_uil_sha256']
        native=manifest['realizations']['region/update/'+name]
        assert native['module_uil_sha256']==expected and native['target']==manifest['target']
    # Original persisted selection targets retain their source identity. The
    # native realization is a separately labelled output, not a retargeted row.
    with Project(tmp_path/'region.fdb') as project:
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert all(project.udl_selection_info(v,full=True)['document']['program']==region_fixture.model()
            for v in [x['selection'] for x in manifest['source_endpoints']['wasm'].values()])
        for backend,target in [('wasm','wasm32-memory-1'),('webgpu','webgpu-wgsl-memory-1')]:
            source=project.udl_selection_info(manifest['source_selections'][backend],full=True)['document']
            assert source['target']==target
    shell.library.fdb_close()


def test_native_source_regions_switch_original_alternative_original_with_carried_state(tmp_path):
    shell,_=build_regions(tmp_path)
    for count,(choice,value) in enumerate([('original',11),('alternate',58),('original',59)],1):
        before=shell.words()
        assert shell.choice('update',choice)==0
        assert shell.words()==before
        assert shell.invoke('advance',{10:1})==0,shell.library.fdb_last_error()
        words=shell.words()
        assert words[0]==value and words[2]==2*count and words[3]==7
        assert words[1]==0 and words[4:8]==[value&1,0,1,value&1]
        assert words[8:]==[0]*8
        assert shell.library.fdb_revision()==count
    assert shell.region_count('update','original')==2
    assert shell.region_count('update','alternate')==1
    assert shell.region_count('update','outside')==0
    assert shell.library.fdb_invocation_count(shell.index('advance'))==3
    assert shell.library.fdb_invocation_count(shell.index('update'))==3
    assert shell.library.fdb_invocation_count(shell.index('draw'))==3
    shell.library.fdb_close()


def test_native_source_budget_excludes_suspend_adapters_and_region_observation_is_private(tmp_path):
    shell,_=build_regions(tmp_path)
    assert shell.invoke('advance',{10:1},render=False)==0
    assert shell.words()[0:4]==[11,1,2,7]
    assert shell.library.fdb_last_steps()==5
    assert shell.region_count('update','original')==1
    assert shell.library.fdb_invocation_count(shell.index('draw'))==0
    shell.library.fdb_close()


def test_native_untaken_region_and_input_ownership(tmp_path):
    shell,_=build_regions(tmp_path)
    assert shell.choice('update','alternate')==0
    assert shell.invoke('advance',{10:0},render=False)==0
    assert shell.words()[0:4]==[10,0,2,7]
    assert shell.library.fdb_last_steps()==3
    assert shell.region_count('update','alternate')==0
    copied=(U32*16)()
    assert shell.library.fdb_copy_words(copied,16)==0
    copied[0]=99
    assert shell.words()[0]==10
    shell.library.fdb_close()


def test_native_declared_region_range_refuses_before_owner_continuation_or_commit(tmp_path):
    shell,_=build_regions(tmp_path)
    assert shell.choice('update','outside')==0
    before=shell.words();revision=shell.library.fdb_revision()
    assert shell.invoke('advance',{10:1})==1
    assert shell.words()==before and shell.library.fdb_revision()==revision
    assert shell.region_count('update','outside')==1
    assert shell.library.fdb_last_steps()==3
    assert shell.library.fdb_invocation_count(shell.index('draw'))==0
    assert shell.library.fdb_last_error()
    shell.library.fdb_close()


def test_native_complete_owner_output_footprint_refuses_atomically(tmp_path):
    program=region_fixture.model()
    program['functions']['advance']['body'][-1]['index']=3
    shell,_=build_regions(tmp_path,program=program)
    before=shell.words()
    assert shell.invoke('advance',{10:1})==1
    assert shell.words()==before and shell.library.fdb_revision()==0
    assert shell.region_count('update','original')==1
    assert shell.library.fdb_invocation_count(shell.index('draw'))==0
    assert b'output' in shell.library.fdb_last_error().lower()
    shell.library.fdb_close()


def test_native_patch_replace_and_invalid_selection_refuse_without_state_changes(tmp_path):
    shell,_=build_regions(tmp_path)
    before=shell.words();revision=shell.library.fdb_revision()
    assert shell.invoke('advance',{3:0})==1
    assert shell.library.fdb_select_region(0,999)==1
    assert shell.library.fdb_select_region(999,0)==1
    assert shell.library.fdb_function_index(b'missing')==-1
    assert shell.library.fdb_call(999,None,None,0,0)==1
    assert shell.library.fdb_copy_words((U32*15)(),15)==1
    assert shell.library.fdb_call(shell.index('advance'),None,None,1,0)==1
    readonly=before.copy();readonly[3]=8
    assert shell.replace(readonly)==1
    immutable_input=before.copy();immutable_input[8]=10
    assert shell.replace(immutable_input)==1
    invalid_palette=before.copy();invalid_palette[4]=2
    assert shell.replace(invalid_palette)==1
    guarded=before.copy();guarded[0]=65536
    assert shell.replace(guarded)==1
    assert shell.replace(before[:-1])==1
    assert shell.words()==before and shell.library.fdb_revision()==revision
    valid=before.copy();valid[0]=99
    assert shell.replace(valid)==0 and shell.words()[0]==99
    shell.library.fdb_close()


def test_native_mutations_refuse_on_worker_thread_and_close_is_terminal(tmp_path):
    shell,_=build_regions(tmp_path)
    before=shell.words();out=[]
    def worker():
        out.extend([shell.invoke('advance',{10:1}),shell.choice('update','alternate'),shell.replace(before)])
    thread=threading.Thread(target=worker);thread.start();thread.join(timeout=10)
    assert not thread.is_alive() and out==[1,1,1]
    assert shell.words()==before and shell.library.fdb_revision()==0
    shell.library.fdb_close();shell.library.fdb_close()
    assert shell.library.fdb_closed()==1
    assert shell.invoke('advance',{10:1})==1
    assert shell.choice('update','original')==1
    assert shell.replace(before)==1
    assert shell.library.fdb_initialize(0)==1
    assert shell.library.fdb_copy_words((U32*16)(),16)==1


@pytest.mark.parametrize('budget,accepted',[(7,True),(6,False)])
def test_native_aggregate_budget_and_transient_private_guard(tmp_path,budget,accepted):
    source=tmp_path/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    program=cut_fixture.model(budget)
    with Project.create(tmp_path/'cut.fdb',source,image='com') as project:
        build_memory_macos_shell(project,cut_fixture.selected(project,program),cut_fixture.plan(),
            cut_fixture.initial(),tmp_path/'native',cuts=cut_fixture.cut_plan(program),with_app=False)
    shell=Shell(tmp_path/'native');before=shell.words()
    status=shell.invoke('advance',{10:1},render=False)
    assert status==(0 if accepted else 1)
    if accepted:
        assert shell.words()[0:4]==[2,1,1,7]
        assert shell.library.fdb_last_steps()==7
    else:
        assert shell.words()==before and shell.library.fdb_revision()==0
        assert b'budget' in shell.library.fdb_last_error().lower()
    shell.library.fdb_close()


def test_native_empty_callee_and_udl_role_remains_explicit(tmp_path):
    # Empty native leaf functions are valid, but cuts require a nonempty exact
    # region. UDL is not silently accepted as a stored semantic source contract.
    source=tmp_path/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    program=cut_fixture.model();program['functions']['empty']={'max_steps':1,'body':[]}
    plan=cut_fixture.plan();plan['bindings']['empty']='wasm';plan['outputs']['empty']=[[0,1]]
    with Project.create(tmp_path/'empty.fdb',source,image='com') as project:
        build_memory_macos_shell(project,cut_fixture.selected(project,program),plan,
            cut_fixture.initial(),tmp_path/'native',with_app=False)
    shell=Shell(tmp_path/'native');before=shell.words()
    assert shell.invoke('empty',render=False)==0 and shell.words()==before
    assert shell.library.fdb_last_steps()==0
    wrong=deepcopy(program);wrong['role']='udl'
    with Project(tmp_path/'empty.fdb') as project:
        with pytest.raises(ValueError):cut_fixture.selected(project,wrong)
    shell.library.fdb_close()
