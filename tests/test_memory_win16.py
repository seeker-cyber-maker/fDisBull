"""C89 segmented lowering tests; host execution is not Win16 qualification."""
from copy import deepcopy
import ctypes
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from fdisbull.udc_memory_win16 import (WIN16_MEMORY_HEADER, emit_win16_memory_function,
    win16_function_receipt, segmented_layout)
from fdisbull.udc_web_memory import execute_memory_uil,digest

CC=shutil.which('clang') or shutil.which('gcc')
compiled=pytest.mark.skipif(not CC,reason='requires a real local C compiler')


def model(words=8):
    return {'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':words},
        'variables':{'$i':{'type':'u32','initial':0}},'functions':{'run':{'max_steps':100,'body':[
            {'op':'while','limit':8,'condition':{'op':'lt','left':{'var':'$i'},'right':8},'body':[
                {'op':'store','index':{'var':'$i'},'value':{'op':'add','left':{'load':{'var':'$i'}},'right':1}},
                {'op':'set','var':'$i','value':{'op':'add','left':{'var':'$i'},'right':1}}]},
            {'op':'return'}]}}}


# This carrier is deliberately paged, including the >64KB cases. It provides
# storage and fault injection only; expected logic comes from independent UIL.
CARRIER=r'''
#include <stdlib.h>
#include <string.h>
#define PAGE_WORDS 8192UL
#define PAGE_COUNT 16
struct Fdb16Arena { FdbU32 count; FdbU32 *pages[PAGE_COUNT]; };
static FdbU32 fail_read=4294967295UL, fail_write=4294967295UL;
static int fail_clone,fail_restore;
static FdbU32 reads,writes,first_read=4294967295UL;
FdbU32 fdb16_word_count(const Fdb16Arena *a) { return a?a->count:0UL; }
static Fdb16Arena *new_arena(FdbU32 n) {
    Fdb16Arena *a;FdbU32 p,count;
    if(!n || n>131072UL)return NULL;
    a=(Fdb16Arena*)calloc(1,sizeof(*a));if(!a)return NULL;a->count=n;
    count=(n+PAGE_WORDS-1UL)/PAGE_WORDS;
    for(p=0UL;p<count;p++) {
        a->pages[p]=(FdbU32*)calloc((size_t)PAGE_WORDS,sizeof(FdbU32));
        if(!a->pages[p]){fdb16_release(a);return NULL;}
    }
    return a;
}
void fdb16_release(Fdb16Arena *a) {
    FdbU32 p;if(!a)return;
    for(p=0UL;p<PAGE_COUNT;p++)free(a->pages[p]);free(a);
}
int fdb16_read(const Fdb16Arena *a,FdbU32 i,FdbU32 *v) {
    ++reads;if(first_read==4294967295UL)first_read=i;
    if(!a || !v || i>=a->count || i==fail_read)return 1;
    *v=a->pages[i/PAGE_WORDS][i%PAGE_WORDS];return 0;
}
int fdb16_write(Fdb16Arena *a,FdbU32 i,FdbU32 v) {
    ++writes;if(!a || i>=a->count || i==fail_write)return 1;
    a->pages[i/PAGE_WORDS][i%PAGE_WORDS]=v;return 0;
}
int fdb16_copy(Fdb16Arena *a,const Fdb16Arena *b) {
    FdbU32 p,count;if(fail_restore || !a || !b || a->count!=b->count)return 1;
    count=(a->count+PAGE_WORDS-1UL)/PAGE_WORDS;
    for(p=0UL;p<count;p++)memcpy(a->pages[p],b->pages[p],(size_t)PAGE_WORDS*sizeof(FdbU32));
    return 0;
}
Fdb16Arena *fdb16_clone(const Fdb16Arena *a) {
    Fdb16Arena *b;int held;
    if(fail_clone)return NULL;b=new_arena(a->count);if(!b)return NULL;
    held=fail_restore;fail_restore=0;
    if(fdb16_copy(b,a)){fdb16_release(b);b=NULL;}fail_restore=held;return b;
}
static FdbBlockResult actual_block(Fdb16Arena *);
#if defined(_WIN32)
#define EXPORTED __declspec(dllexport)
#else
#define EXPORTED
#endif
EXPORTED int probe(FdbU32 *words,FdbU32 count,FdbU32 *result,
                  FdbU32 read_fault,FdbU32 write_fault,int clone_fault,int restore_fault) {
    Fdb16Arena *a;FdbU32 p;FdbBlockResult r;
    a=new_arena(count);if(!a)return 1;
    for(p=0UL;p<count;p++)a->pages[p/PAGE_WORDS][p%PAGE_WORDS]=words[p];
    fail_read=read_fault;fail_write=write_fault;fail_clone=clone_fault;fail_restore=restore_fault;
    reads=writes=0UL;first_read=4294967295UL;r=actual_block(a);
    for(p=0UL;p<count;p++)words[p]=a->pages[p/PAGE_WORDS][p%PAGE_WORDS];
    result[0]=r.status;result[1]=r.steps;result[2]=r.cut;result[3]=reads;result[4]=writes;result[5]=first_read;
    fdb16_release(a);return 0;
}
'''


def build(tmp_path,program,*,atomic=True,capture='$i'):
    text=WIN16_MEMORY_HEADER+CARRIER+emit_win16_memory_function(program,'run','actual_block',capture_local=capture,atomic=atomic)
    source=tmp_path/'program.c';source.write_text(text)
    library=tmp_path/('block.dylib' if sys.platform=='darwin' else 'block.so')
    command=[CC,'-std=c89','-O1','-Wall','-Wextra','-Werror=declaration-after-statement',
        '-Werror=implicit-function-declaration','-Werror=long-long',
        '-Wno-unused-variable','-Wno-unused-but-set-variable','-Wno-unused-label',
        '-dynamiclib' if sys.platform=='darwin' else '-shared','-fPIC',str(source),'-o',str(library)]
    run=subprocess.run(command,text=True,capture_output=True,timeout=60)
    assert run.returncode==0,run.stdout+run.stderr
    lib=ctypes.CDLL(str(library));u=ctypes.c_uint32;pointer=ctypes.POINTER(u)
    lib.probe.argtypes=[pointer,u,pointer,u,u,ctypes.c_int,ctypes.c_int];lib.probe.restype=ctypes.c_int
    def invoke(before,*,read_fault=0xffffffff,write_fault=0xffffffff,clone_fault=0,restore_fault=0):
        words=(u*len(before))(*before);result=(u*6)()
        assert lib.probe(words,len(before),result,read_fault,write_fault,clone_fault,restore_fault)==0
        return {'status':result[0],'steps':result[1],'cut':result[2],'words':list(words),
                'reads':result[3],'writes':result[4],'first_read':result[5]}
    return invoke


def test_full_arena_layout_preserves_high_words_and_source_identity():
    p=model(70000);before=deepcopy(p);layout=segmented_layout(p)
    assert p==before and layout['module_uil_sha256']==digest(p)
    assert layout['logical_words']==70000 and layout['logical_bytes']==280000
    assert layout['page_words']==8192 and layout['maximum_page_bytes']==32768
    assert layout['pages']==9 and layout['last_page_words']==4464


@pytest.mark.parametrize('symbol',['','if','__reserved','bad-name',None,32])
def test_invalid_symbols_refuse(symbol):
    with pytest.raises(ValueError):emit_win16_memory_function(model(),'run',symbol)


def test_invalid_options_and_whole_program_refuse_without_editing_source():
    p=model();saved=deepcopy(p)
    for options in [{'capture_local':'$unknown'},{'atomic':1},{'max_automatic_bytes':True}]:
        with pytest.raises(ValueError):emit_win16_memory_function(p,'run','valid',**options)
    assert p==saved
    p['functions']['unexecuted']={'max_steps':1,'body':[{'op':'host-call'}]}
    with pytest.raises(ValueError):emit_win16_memory_function(p,'run','valid')


@compiled
@pytest.mark.parametrize('case',['normal','empty','early_return','zero_loop','nested','load_bounds',
    'store_bounds','div_zero','mod_zero','loop_limit','budget','exact_budget','ordered_trap'])
def test_real_c89_status_steps_capture_and_atomic_refusal(tmp_path,case):
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
        if case=='ordered_trap':fault={'op':'set','var':'$i','value':{'op':'add',
            'left':{'load':8},'right':{'load':7}}}
        body.insert(1,fault)
    elif case=='loop_limit':body[0]['limit']=7
    elif case=='budget':p['functions']['run']['max_steps']=26
    elif case=='exact_budget':p['functions']['run']['max_steps']=27
    before=[0xffffffff,0,1,2,3,4,5,6];expected=execute_memory_uil(p,'run',before)
    invoke=build(tmp_path,p)
    for _ in range(2):
        got=invoke(before)
        assert got['status']==(0 if expected['status']=='complete' else 1)
        assert got['words']==expected['words'] and got['steps']==expected['steps']
        assert got['cut']==({'normal':8,'empty':0,'early_return':0,'zero_loop':0,'nested':2,'exact_budget':8}.get(case,0) if expected['status']=='complete' else 0)
        if case=='ordered_trap':assert got['reads']==8


@compiled
def test_all_unsigned_operations_and_reused_initial_locals(tmp_path):
    operands={'add':(0xffffffff,2),'sub':(0,1),'mul':(0xffffffff,3),
        'and':(0xf0f0,0xff),'or':(0xf0f0,0xff),'xor':(0xf0f0,0xff),
        'shl':(0x80000001,33),'shr':(0x80000001,33),'div':(0xffffffff,3),
        'mod':(0xffffffff,3),'eq':(5,5),'ne':(5,5),'lt':(0xffffffff,0),
        'le':(0xffffffff,0xffffffff),'gt':(0xffffffff,0),'ge':(0,0)}
    expected=[1,0xffffffff,0xfffffffd,0xf0,0xf0ff,0xf00f,2,0x40000000,
              1431655765,0,1,0,0,1,1,1]
    p={'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':16},
       'variables':{'$held':{'type':'u32','initial':0xffffffff}},'functions':{'run':{'max_steps':16,
       'body':[{'op':'store','index':i,'value':{'op':op,'left':a,'right':b}}
               for i,(op,(a,b)) in enumerate(operands.items())]}}}
    invoke=build(tmp_path,p,capture='$held')
    for _ in range(2):
        got=invoke([0]*16);assert got['status']==0 and got['steps']==16
        assert got['words']==expected and got['cut']==0xffffffff


@compiled
def test_cross_page_and_cross_64kb_indices_are_exact(tmp_path):
    indices=[8191,8192,16383,16384,65535,65536,69999]
    p=model(70000);p['functions']['run']['body']=[{'op':'store','index':i,
        'value':{'op':'add','left':{'load':i},'right':1}} for i in indices]
    before=[0]*70000
    for n,i in enumerate(indices):before[i]=0xffffffff if n%2 else n
    got=build(tmp_path,p)(before);expected=execute_memory_uil(p,'run',before)
    assert got['status']==0 and got['words']==expected['words'] and got['steps']==7
    assert got['reads']==7 and got['writes']==7


@compiled
def test_carrier_faults_are_distinct_and_rollback_is_explicit(tmp_path):
    p=model();before=[0]*8;invoke=build(tmp_path,p)
    for options in ({'read_fault':3},{'write_fault':4},{'clone_fault':1}):
        got=invoke(before,**options);assert got['status']==2 and got['words']==before and got['cut']==0
    p['functions']['run']['body'].insert(1,{'op':'store','index':8,'value':1})
    # An explicit private phase does not promise its own rollback; the owner
    # discards that arena on refusal. This mode must not silently imply atomicity.
    private=tmp_path/'private';private.mkdir();call=build(private,p,atomic=False)
    got=call(before);assert got['status']==1 and got['words']==[1]*8
    atomic=tmp_path/'atomic';atomic.mkdir();call=build(atomic,p)
    got=call(before,restore_fault=1);assert got['status']==2 and got['words']==[1]*8


def test_receipt_and_automatic_budget_are_scoped_to_source_emission():
    p=model();source=emit_win16_memory_function(p,'run','actual_block')
    receipt=win16_function_receipt(p,'run','actual_block')
    assert receipt['source_sha256']==hashlib.sha256(source.encode()).hexdigest()
    assert receipt['module_uil_sha256']==digest(p) and receipt['native_execution'] is False
    assert receipt['atomic'] and receipt['conservative_automatic_bytes']<=16384
    with pytest.raises(ValueError,match='frame budget'):emit_win16_memory_function(p,'run','actual_block',max_automatic_bytes=64)
