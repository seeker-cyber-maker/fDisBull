"""Real native ARM64 arithmetic, bounded control flow and atomic arena results."""
from copy import deepcopy
import ctypes
import hashlib
import json
import platform
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.udc_memory_native import build_native_memory_block, emit_memory_function, NATIVE_MEMORY_HEADER
from fdisbull.udc_web_memory import execute_memory_uil, digest

NATIVE=sys.platform=='darwin' and platform.machine()=='arm64' and shutil.which('clang')
native=pytest.mark.skipif(not NATIVE,reason='requires real macOS ARM64 clang and execution')


def model():
    return {'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':8},
        'variables':{'$i':{'type':'u32','initial':0}},
        'functions':{'run':{'max_steps':100,'body':[
            {'op':'while','limit':8,'condition':{'op':'lt','left':{'var':'$i'},'right':8},
             'body':[{'op':'store','index':{'var':'$i'},'value':{'op':'add','left':{'load':{'var':'$i'}},'right':1}},
                     {'op':'set','var':'$i','value':{'op':'add','left':{'var':'$i'},'right':1}}]},
            {'op':'return'}]}}}


class Result(ctypes.Structure):
    _fields_=[('status',ctypes.c_uint32),('steps',ctypes.c_uint32),('cut',ctypes.c_uint32)]


def load(root):
    library=ctypes.CDLL(str(root/'block.dylib'))
    library.fdb_block.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
    library.fdb_block.restype=Result
    return library


def call(library,words):
    arena=(ctypes.c_uint32*len(words))(*words)
    result=library.fdb_block(arena)
    return {'status':'complete' if result.status==0 else 'refused',
            'words':list(arena),'steps':result.steps,'cut':result.cut}


@pytest.mark.parametrize('symbol',['','return','__reserved','bad-name',None,23])
def test_invalid_native_symbol_refuses_before_emission(symbol):
    with pytest.raises(ValueError,match='symbol'):emit_memory_function(model(),'run',symbol)


@pytest.mark.parametrize('capture',['$missing',0,[],{}])
def test_unknown_capture_refuses(capture):
    with pytest.raises(ValueError,match='capture'):emit_memory_function(model(),'run','safe',capture_local=capture)


def test_whole_program_validation_and_owned_source():
    value=model();saved=deepcopy(value)
    emitted=emit_memory_function(value,'run','safe',capture_local='$i')
    assert value==saved and 'FdbBlockResult safe(uint32_t *fdb_words)' in emitted
    value['functions']['unused']={'max_steps':1,'body':[{'op':'host-effect'}]}
    with pytest.raises(ValueError):emit_memory_function(value,'run','safe')


@native
@pytest.mark.parametrize('case',['normal','empty','early_return','zero_loop','nested','load_bounds',
    'store_bounds','div_zero','mod_zero','loop_limit','budget','exact_budget','ordered_trap'])
def test_real_native_results_charges_capture_and_refusal(tmp_path,case):
    p=model();body=p['functions']['run']['body']
    if case=='empty':body.clear()
    elif case=='early_return':body[:]=[{'op':'return'},{'op':'store','index':8,'value':99}]
    elif case=='zero_loop':body[0]['condition']=0
    elif case=='nested':
        p['variables']['$j']={'type':'u32','initial':0}
        body[0]['condition']['right']=2
        body[0]['body'][:0]=[{'op':'set','var':'$j','value':0},
            {'op':'while','limit':2,'condition':{'op':'lt','left':{'var':'$j'},'right':2},
             'body':[{'op':'set','var':'$j','value':{'op':'add','left':{'var':'$j'},'right':1}}]}]
    elif case in ('load_bounds','store_bounds','div_zero','mod_zero','ordered_trap'):
        fault={'op':'store','index':8,'value':1} if case=='store_bounds' else {
            'op':'set','var':'$i','value':{'load':8} if case=='load_bounds' else
            {'op':case.split('_')[0],'left':17,'right':0}}
        if case=='ordered_trap':
            fault={'op':'set','var':'$i','value':{'op':'add',
                'left':{'load':8},'right':{'op':'div','left':3,'right':0}}}
        body.insert(1,fault)
    elif case=='loop_limit':body[0]['limit']=7
    elif case=='budget':p['functions']['run']['max_steps']=26
    elif case=='exact_budget':p['functions']['run']['max_steps']=27
    before=[0xffffffff,0,1,2,3,4,5,6]
    expected=execute_memory_uil(p,'run',before)
    root=tmp_path/'native';receipt=build_native_memory_block(p,'run',root,capture_local='$i')
    assert receipt['module_uil_sha256']==digest(p) and receipt['native_execution'] is False
    assert receipt['target']=='macos-arm64-memory-1'
    for name,expected_hash in receipt['artifacts'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected_hash
    lib=load(root)
    for _ in range(2):
        observed=call(lib,before)
        assert {key:observed[key] for key in ('status','words','steps')}=={key:expected[key] for key in ('status','words','steps')}
        assert observed['cut']==({'normal':8,'empty':0,'early_return':0,'zero_loop':0,'nested':2,'exact_budget':8}.get(case,0) if expected['status']=='complete' else 0)
    wire=struct.pack('<8I',*before)*2
    result=subprocess.run([str(root/'probe')],input=wire,capture_output=True,timeout=30)
    assert result.returncode==0 and len(result.stdout)==2*(3+8)*4
    for offset in (0,44):
        row=struct.unpack_from('<11I',result.stdout,offset)
        assert row[:3]==(0 if expected['status']=='complete' else 1,expected['steps'],observed['cut'])
        assert list(row[3:])==expected['words']
    partial=subprocess.run([str(root/'probe')],input=wire[:3],capture_output=True,timeout=30)
    assert partial.returncode==2 and partial.stdout==b''


@native
def test_real_unsigned_operations_and_reused_initial_locals(tmp_path):
    operands={'add':(0xffffffff,2),'sub':(0,1),'mul':(0xffffffff,3),
        'and':(0xf0f0,0xff),'or':(0xf0f0,0xff),'xor':(0xf0f0,0xff),
        'shl':(0x80000001,33),'shr':(0x80000001,33),'div':(0xffffffff,3),
        'mod':(0xffffffff,3),'eq':(5,5),'ne':(5,5),'lt':(0xffffffff,0),
        'le':(0xffffffff,0xffffffff),'gt':(0xffffffff,0),'ge':(0,0)}
    expected=[1,0xffffffff,0xfffffffd,0xf0,0xf0ff,0xf00f,2,0x40000000,
              1431655765,0,1,0,0,1,1,1]
    p={'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':16},
       'variables':{'$held':{'type':'u32','initial':0xffffffff}},
       'functions':{'run':{'max_steps':16,'body':[
           {'op':'store','index':i,'value':{'op':op,'left':a,'right':b}}
           for i,(op,(a,b)) in enumerate(operands.items())]}}}
    root=tmp_path/'ops';build_native_memory_block(p,'run',root,capture_local='$held')
    library=load(root)
    for _ in range(2):
        actual=call(library,[0]*16)
        assert actual=={'status':'complete','words':expected,'steps':16,'cut':0xffffffff}
    assert library.fdb_block(None).status==1


@native
def test_output_paths_and_target_guards(tmp_path):
    with pytest.raises(ValueError):build_native_memory_block(model(),'run',tmp_path/'bad',target='x86_64-apple-macos11')
    assert not (tmp_path/'bad').exists()
    existing=tmp_path/'existing';existing.mkdir()
    with pytest.raises(ValueError):build_native_memory_block(model(),'run',existing)
    git=tmp_path/'repo';git.mkdir();(git/'.git').mkdir()
    with pytest.raises(ValueError,match='Git'):build_native_memory_block(model(),'run',git/'output')


@native
def test_emitted_function_can_link_into_objective_c_shell(tmp_path):
    source=NATIVE_MEMORY_HEADER+emit_memory_function(model(),'run','native_model')
    source+='\nint main(void) { uint32_t w[8]={0}; return native_model(w).status; }\n'
    (tmp_path/'shell.m').write_text(source)
    done=subprocess.run([shutil.which('clang'),'-x','objective-c','-std=c11','-O1',
                         str(tmp_path/'shell.m'),'-o',str(tmp_path/'shell')],capture_output=True,text=True,timeout=60)
    assert done.returncode==0,done.stderr
    assert subprocess.run([str(tmp_path/'shell')],capture_output=True,timeout=30).returncode==0
