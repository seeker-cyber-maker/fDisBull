"""Native code is exercised only in an explicitly admitted build directory."""
from copy import deepcopy
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile

import pytest

from fdisbull.common_uil import digest
from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_link import resolve_native_link
from fdisbull.uil_native_codegen import (emit_native_sources, encode_native_inputs,
    decode_native_results, run_native_records)
from fdisbull.uil_runtime import execute_program
from fdisbull.uil_native import _FLAGS as STRICT_C_FLAGS
from test_uil_codegen import typ, var, const, op, function, documents


def bundle(fn, initial, constants=(), resources=()):
    return documents([fn],[{'constants':list(constants),'initial':initial}],resources=resources)


def emit(docs, target='macos-arm64', arithmetic='portable-c', requirements=None):
    p,v,c,o=docs
    lock=resolve_native_link(p,v,c,o,target,arithmetic=arithmetic,module_requirements=requirements)
    return emit_native_sources(p,v,c,o,target=target,link_lock=lock)


@pytest.fixture
def native_directory():
    path=os.environ.get('FDISBULL_NATIVE_TEST_ROOT')
    if not path:pytest.skip('set FDISBULL_NATIVE_TEST_ROOT to an admitted external directory')
    root=Path(path)
    assert root.is_dir()
    assert not any((p/'.git').exists() for p in (root,*root.parents))
    with tempfile.TemporaryDirectory(prefix='native-codegen-',dir=root) as directory:
        yield Path(directory)


def host_target():
    if sys.platform=='darwin' and platform.machine().lower() in ('arm64','aarch64'):return 'macos-arm64'
    if sys.platform.startswith('linux') and platform.machine().lower() in ('x86_64','amd64'):return 'linux-x64'
    pytest.skip('no qualified host native compiler profile')


def build_native(directory, docs, arithmetic='portable-c', requirements=None):
    target=host_target();compiler=(os.environ.get('FDISBULL_NATIVE_TEST_COMPILER') or
                                 shutil.which('clang') or shutil.which('gcc'))
    if compiler is None:pytest.skip('no C compiler available')
    manifest=emit(docs,target,arithmetic,requirements)
    for name,source in manifest['sources'].items():(directory/name).write_text(source)
    program=directory/'program'
    result=subprocess.run([compiler,*STRICT_C_FLAGS,str(directory/'program.c'),str(directory/'numeric.c'),'-o',str(program)],
                          capture_output=True,text=True,timeout=90,cwd=directory)
    assert result.returncode==0,result.stderr
    return manifest,[str(program)]


@pytest.mark.parametrize('target',['macos-arm64','linux-x64','windows-x64'])
@pytest.mark.parametrize('arithmetic',['portable-c','native-asm'])
def test_sources_are_real_functions_and_actual_selected_math(target,arithmetic):
    fn=function([typ('u16')]*2,[0],[1],[{'op':'set','dst':1,'value':op('add','u16',var(0),const(0))}],constants=[typ('u16')])
    docs=bundle(fn,['0','0'],['1']);manifest=emit(docs,target,arithmetic)
    assert set(manifest['sources'])=={'program.c','numeric.c','native-core.h'}
    assert 'static int fn0(' in manifest['sources']['program.c']
    assert 'fn0_add_'+arithmetic.replace('-','_')+'(' in manifest['sources']['program.c']
    if arithmetic=='native-asm':assert '__asm__ __volatile__' in manifest['sources']['numeric.c']
    else:assert '__asm__' not in manifest['sources']['numeric.c']
    assert manifest['abi']['call_observation']=='identity-and-counts-only'
    assert manifest['program_sha256']==digest(docs[0])
    assert 'fdisbull-common-uil-1' not in manifest['sources']['program.c']
    assert '_O_BINARY' in manifest['sources']['program.c']
    assert manifest['legacy_arena_adapter']['available'] is False


@pytest.mark.parametrize('arithmetic',['portable-c','native-asm'])
def test_native_six_alu_and_signed_division_are_width_exact(native_directory,arithmetic):
    numeric=('add','sub','mul','and','or','xor','div','mod','shl','shr')
    fn=function([typ('i64')]*12,[0,1],list(range(2,12)),[
        {'op':'set','dst':i+2,'value':op(name,'i64',var(0),var(1))} for i,name in enumerate(numeric)])
    docs=bundle(fn,['0']*12);manifest,command=build_native(native_directory,docs,arithmetic)
    inputs=[[-9223372036854775808,1],[-7,3],[9223372036854775807,1]]
    results=run_native_records(command,manifest,inputs,cwd=native_directory)
    for args,result in zip(inputs,results):
        ref=execute_program(docs[0],docs[1],docs[3],docs[2],inputs=args)
        assert result['status']==ref['status']=='complete'
        assert result['outputs']==ref['outputs'] and result['state']==ref['state']
        assert result['steps']==ref['steps']
        assert {r['provider'] for r in result['arithmetic_calls']}=={arithmetic}
        assert {r['operation'] for r in result['arithmetic_calls']}=={'add','sub','mul','and','or','xor'}


def test_mixed_components_call_two_real_helpers(native_directory):
    fn=function([typ('u16')]*3,[0],[2],[
        {'op':'set','dst':1,'value':op('add','u16',var(0),const(0))},
        {'op':'set','dst':2,'value':op('mul','u16',var(1),const(1))}],constants=[typ('u16')]*2)
    docs=bundle(fn,['0']*3,['1','3'])
    requirements={'functions':{'0':{'components':{'add':'portable-c','mul':'native-asm'}}}}
    manifest,command=build_native(native_directory,docs,requirements=requirements)
    result=run_native_records(command,manifest,[[65535],[2]],cwd=native_directory)
    assert [r['outputs'] for r in result]==[[0],[9]]
    calls={(r['operation'],r['provider'],r['calls']) for r in result[1]['arithmetic_calls']}
    assert calls=={('add','portable-c',1),('mul','native-asm',1)}


def test_scalar_copy_pruning_keeps_alias_value_after_source_overwrite(native_directory):
    fn=function([typ('u16')]*3,[0],[0,1,2],[
        {'op':'set','dst':1,'value':var(0)},
        {'op':'set','dst':0,'value':const(0)},
        {'op':'set','dst':2,'value':op('add','u16',var(1),const(1))}],constants=[typ('u16')]*2)
    docs=bundle(fn,['0']*3,['99','1']);manifest,command=build_native(native_directory,docs)
    result=run_native_records(command,manifest,[[7]],cwd=native_directory)[0]
    assert result['outputs']==[99,7,8] and result['steps']==3
    plan=manifest['scalar_value_plans']['fn0']
    assert len(plan['eliminated_copies'])==1 and plan['eliminated_copies'][0]['charge_retained']==1


@pytest.mark.parametrize('width',['u8','u16','u32','u64'])
def test_unsigned_wrap_and_signed_extension(native_directory,width):
    fn=function([typ(width),typ(width),typ('i8'),typ('u64')],[0,2],[1,3],[
        {'op':'set','dst':1,'value':op('add',width,var(0),const(0))},
        {'op':'set','dst':3,'value':op('cast','u64',var(2))}],constants=[typ(width)])
    docs=bundle(fn,['0','0','0','0'],['1']);manifest,command=build_native(native_directory,docs)
    bits=int(width[1:]);result=run_native_records(command,manifest,[[(1<<bits)-1,-1]],cwd=native_directory)[0]
    assert result['outputs']==[0,18446744073709551615]


def test_large_array_calls_own_frames_and_record_exact_import_identity(native_directory):
    array={'type':'u32-array','length':70000}
    child=function([array],[0],[0],[{'op':'store','array':0,'index':const(0),'value':const(1)}],constants=[typ('u32')]*2)
    catalog=build_catalog([{'language':'common','function':child,'constants':['65536','17']}]);group=catalog['groups'][0];impl=group['implementations'][0]
    entry=function([array,array],[0],[0,1],[{'op':'invoke','block':0,'inputs':[var(0)],'outputs':[1]}])
    docs=documents([entry],[{'constants':[],'initial':[[0]*70000,[0]*70000]}],catalog=catalog,
                   imports=[{'semantic_id':group['semantic_id'],'inputs':[array],'outputs':[array],'effects':[]}],bindings=[{'import':0,'implementation':impl['id']}])
    manifest,command=build_native(native_directory,docs)
    values=[0]*70000;values[65536]=9;values[-1]=23
    result=run_native_records(command,manifest,[[values]],cwd=native_directory)[0]
    assert result['outputs'][0]==values
    expected=values.copy();expected[65536]=17;assert result['outputs'][1]==expected
    assert result['calls'][0]['implementation']==impl['id'] and result['calls'][0]['status']=='complete'
    assert result['calls'][0]['observation']=='identity-and-counts-only'
    assert 'inputs' not in result['calls'][0]


@pytest.mark.parametrize('failure',['division','shift','bounds','loop','budget'])
def test_native_refusal_rolls_back_owned_state(native_directory,failure):
    array={'type':'u8-array','length':2};body=[{'op':'set','dst':0,'value':const(0)}]
    if failure in ('division','shift'):
        body.append({'op':'set','dst':0,'value':op('div' if failure=='division' else 'shl','u8',var(0),var(1))})
    elif failure=='bounds':body.append({'op':'store','array':2,'index':var(1),'value':var(0)})
    else:body.append({'op':'while','condition':const(1),'limit':2,'body':[]})
    fn=function([typ('u8'),typ('u8'),array],[0,1,2],[0],body,constants=[typ('u8'),typ('bool')],max_steps=2 if failure=='budget' else 100)
    docs=bundle(fn,['0','0',[0,0]],['42',True]);manifest,command=build_native(native_directory,docs)
    value={'division':0,'shift':8,'bounds':2}.get(failure,0)
    row=run_native_records(command,manifest,[[9,value,[3,4]]],cwd=native_directory)[0]
    assert row['status']=='refused' and row['state']==[9,value,[3,4]] and row['outputs']==row['events']==[]


def test_native_effects_are_plans_and_empty_pending_frame_exists(native_directory):
    fn=function([],[],[],[{'op':'effect','service':'text.show','inputs':[const(0)]}],constants=[typ('resource')])
    docs=bundle(fn,[],[0],[{'kind':'text','text':'Win! é'}]);manifest,command=build_native(native_directory,docs)
    row=run_native_records(command,manifest,[[]],cwd=native_directory)[0]
    assert row['status']=='pending_host' and row['state']==row['proposed_state']==row['outputs']==[]
    assert row['events']==[{'service':'text.show','inputs':[0],'resource':{'kind':'text','text':'Win! é'}}]


def test_framing_and_scalar_ranges_are_strict(native_directory):
    fn=function([typ('u8')],[0],[0],[{'op':'return'}]);docs=bundle(fn,['0'])
    manifest,command=build_native(native_directory,docs)
    raw=subprocess.run(command,input=encode_native_inputs(manifest,[7]),capture_output=True,check=True).stdout
    assert decode_native_results(manifest,raw)[0]['outputs']==[7]
    for damaged in [raw[:-1],raw+b'x',b'wrong'+raw[5:],raw[:12],raw[:12]+struct.pack('<IQQQ',0,2,1,0)+raw[40:]]:
        with pytest.raises(ValueError):decode_native_results(manifest,damaged)
    changed=bytearray(raw);changed[-1]=255
    with pytest.raises(ValueError):decode_native_results(manifest,bytes(changed))
    with pytest.raises(ValueError):encode_native_inputs(manifest,[256])
    bad=encode_native_inputs(manifest,[7])+b'x'
    assert subprocess.run(command,input=bad,capture_output=True).returncode!=0


def test_text_slots_and_stale_lock_are_not_silently_lowered():
    fn=function([typ('text')],[0],[0],[{'op':'return'}]);docs=bundle(fn,[''])
    lock=resolve_native_link(*[docs[i] for i in (0,1,2,3)],'macos-arm64')
    with pytest.raises(ValueError,match='text'):
        emit_native_sources(*docs,target='macos-arm64',link_lock=lock)
    fn=function([typ('u8')],[0],[0],[{'op':'return'}]);docs=bundle(fn,['0'])
    lock=resolve_native_link(*docs,'macos-arm64');lock['target']='linux-x64'
    with pytest.raises(ValueError):emit_native_sources(*docs,target='macos-arm64',link_lock=lock)


@pytest.mark.parametrize('arithmetic',['portable-c','native-asm'])
def test_signed_minimum_divide_by_negative_one_wraps_without_c_ub(native_directory,arithmetic):
    fn=function([typ('i64')]*4,[0,1],[2,3],[
        {'op':'set','dst':2,'value':op('div','i64',var(0),var(1))},
        {'op':'set','dst':3,'value':op('mod','i64',var(0),var(1))}])
    docs=bundle(fn,['0']*4);manifest,command=build_native(native_directory,docs,arithmetic)
    row=run_native_records(command,manifest,[[-9223372036854775808,-1]],cwd=native_directory)[0]
    assert row['status']=='complete' and row['outputs']==[-9223372036854775808,0]


def test_native_call_and_event_capacity_refuse_atomically(native_directory):
    child=function([typ('u16')],[0],[0],[{'op':'return'}])
    catalog=build_catalog([{'language':'common','function':child,'constants':[]}]);g=catalog['groups'][0];impl=g['implementations'][0]
    entry=function([typ('u16')]*2,[1],[0],[
        {'op':'while','condition':op('lt','bool',var(0),var(1)),'limit':1025,'body':[
            {'op':'invoke','block':0,'inputs':[var(0)],'outputs':[0]},
            {'op':'set','dst':0,'value':op('add','u16',var(0),const(0))}]}],constants=[typ('u16')],max_steps=20000)
    docs=documents([entry],[{'constants':['1'],'initial':['0','0']}],catalog=catalog,
                   imports=[{'semantic_id':g['semantic_id'],'inputs':[typ('u16')],'outputs':[typ('u16')],'effects':[]}],bindings=[{'import':0,'implementation':impl['id']}])
    manifest,command=build_native(native_directory,docs)
    success,refused=run_native_records(command,manifest,[[1024],[1025]],cwd=native_directory)
    assert success['outputs']==[1024] and len(success['calls'])==1024
    assert refused['status']=='refused' and refused['state']==[0,1025] and len(refused['calls'])==1024
    assert refused['outputs']==refused['events']==[]
    assert all(c['status']=='complete' for c in refused['calls'])


def test_decoder_rejects_false_provider_and_unexpected_json_fields(native_directory):
    fn=function([typ('u16')],[0],[0],[{'op':'set','dst':0,'value':op('add','u16',var(0),const(0))}],constants=[typ('u16')])
    manifest,command=build_native(native_directory,bundle(fn,['0'],['1']))
    raw=subprocess.run(command,input=encode_native_inputs(manifest,[7]),capture_output=True,check=True).stdout
    size,sc,oc,pc=struct.unpack_from('<IQQQ',raw,12);row=json.loads(raw[40:40+size]);body=raw[40+size:]
    def changed(document):
        data=json.dumps(document,separators=(',',':')).encode()
        return raw[:12]+struct.pack('<IQQQ',len(data),sc,oc,pc)+data+body
    wrong=deepcopy(row);wrong['arithmetic_calls'][0]['provider']='native-asm'
    with pytest.raises(ValueError,match='provider'):decode_native_results(manifest,changed(wrong))
    wrong=deepcopy(row);wrong['state']='fabricated'
    with pytest.raises(ValueError,match='fields'):decode_native_results(manifest,changed(wrong))
    wrong=deepcopy(manifest);wrong['abi']['output_types']=[typ('i16')]
    with pytest.raises(ValueError,match='closure'):decode_native_results(wrong,raw)


def test_native_event_count_limit_is_real(native_directory):
    fn=function([typ('u16'),typ('u16')],[1],[0],[
        {'op':'while','condition':op('lt','bool',var(0),var(1)),'limit':257,'body':[
            {'op':'effect','service':'text.show','inputs':[const(0)]},
            {'op':'set','dst':0,'value':op('add','u16',var(0),const(1))}]}],constants=[typ('resource'),typ('u16')],max_steps=10000)
    docs=bundle(fn,['0','0'],[0,'1'],[{'kind':'text','text':'Outcome'}])
    manifest,command=build_native(native_directory,docs)
    pending,refused=run_native_records(command,manifest,[[256],[257]],cwd=native_directory)
    assert pending['status']=='pending_host' and len(pending['events'])==256
    assert refused['status']=='refused' and refused['state']==[0,257] and refused['events']==[]


def test_native_event_byte_limit_counts_utf8_not_characters(native_directory):
    text='é'*131000
    fn=function([typ('u8'),typ('u8')],[1],[0],[
        {'op':'while','condition':op('lt','bool',var(0),var(1)),'limit':5,'body':[
            {'op':'effect','service':'text.show','inputs':[const(0)]},
            {'op':'set','dst':0,'value':op('add','u8',var(0),const(1))}]}],constants=[typ('resource'),typ('u8')],max_steps=100)
    docs=bundle(fn,['0','0'],[0,'1'],[{'kind':'text','text':text}])
    manifest,command=build_native(native_directory,docs)
    pending,refused=run_native_records(command,manifest,[[4],[5]],cwd=native_directory)
    assert pending['status']=='pending_host' and len(pending['events'])==4
    assert sum(len(json.dumps(e,ensure_ascii=False,separators=(',',':')).encode()) for e in pending['events'])<=1048576
    assert refused['status']=='refused' and refused['state']==[0,5] and refused['events']==[]


@pytest.mark.parametrize('arithmetic',['portable-c','native-asm'])
def test_existing_fdb_block_arena_abi_commits_only_completed_work(native_directory,arithmetic):
    array={'type':'u32-array','length':4}
    fn=function([array],[0],[0],[
        {'op':'store','array':0,'index':const(0),'value':op('add','u32',{'op':'load','array':0,'index':const(0)},const(1))},
        {'op':'require','condition':op('ne','bool',{'op':'load','array':0,'index':const(1)},const(0))},
        {'op':'return'}],constants=[typ('u32')]*2)
    manifest,_=build_native(native_directory,bundle(fn,[[0]*4],['0','1']),arithmetic)
    assert manifest['legacy_arena_adapter']['available'] is True
    assert manifest['abi']['legacy_arena_adapter']['capture_local'] is False
    caller=native_directory/'caller.c'
    caller.write_text('''#include "native-core.h"
#include <stdio.h>
int main(void){uint32_t words[4]={UINT32_MAX,1,23,42};FdbBlockResult r;
 r=fdb_block(words);printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,words[0],words[2]);
 words[0]=9;words[1]=0;r=fdb_block(words);printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,words[0],words[2]);
 r=fdb_block(NULL);printf("%u %u %u\\n",r.status,r.steps,r.cut);return 0;}''')
    compiler=os.environ.get('FDISBULL_NATIVE_TEST_COMPILER') or shutil.which('clang') or shutil.which('gcc');exe=native_directory/'adapter'
    result=subprocess.run([compiler,*STRICT_C_FLAGS,'-DFDB_NATIVE_NO_MAIN',str(native_directory/'program.c'),
                           str(native_directory/'numeric.c'),str(caller),'-o',str(exe)],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
    assert result.stdout.splitlines()==['0 3 0 0 23','1 2 0 9 23','1 0 0']


def test_effectful_array_does_not_claim_legacy_arena_compatibility():
    array={'type':'u32-array','length':1}
    fn=function([array],[0],[0],[{'op':'effect','service':'text.show','inputs':[const(0)]}],constants=[typ('resource')])
    manifest=emit(bundle(fn,[[0]],[0],[{'kind':'text','text':'Planned'}]))
    assert manifest['legacy_arena_adapter']['available'] is False
    assert '#define FDB_NATIVE_ARENA_ADAPTER 0' in manifest['sources']['native-core.h']
    assert 'FdbBlockResult fdb_block(' not in manifest['sources']['program.c']
