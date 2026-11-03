"""Genuine OpenWatcom NE execution of generic memory UIL, not Snake parity.

The optional offline guest must supply a real 16-bit Windows compiler/runtime.
All arithmetic operands are loaded at runtime in the edge grid; an optimizer
cannot replace the tested operations with constant initializer values.
"""
from copy import deepcopy
from importlib.resources import files
import hashlib
import importlib.util
import json
import os
import struct
import uuid

import pytest

from fdisbull.udc_memory_win16 import WIN16_MEMORY_HEADER, emit_win16_memory_function
from fdisbull.udc_web_memory import execute_memory_uil, digest


VM = os.environ.get('FDISBULL_WIN16_VM_CLIENT')
pytestmark = pytest.mark.skipif(not VM, reason='requires a genuine OpenWatcom/Win16 offline guest')
MASK = 0xffffffff


def model(words=8):
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': words},
        'variables': {'$i': {'type': 'u32', 'initial': 0}},
        'functions': {'run': {'max_steps': 100, 'body': [
            {'op': 'while', 'limit': 8, 'condition': {'op': 'lt', 'left': {'var': '$i'}, 'right': 8}, 'body': [
                {'op': 'store', 'index': {'var': '$i'}, 'value': {'op': 'add', 'left': {'load': {'var': '$i'}}, 'right': 1}},
                {'op': 'set', 'var': '$i', 'value': {'op': 'add', 'left': {'var': '$i'}, 'right': 1}}]},
            {'op': 'return'}]}}}


def cases():
    result = []
    def add(name, program, before, *, cut=0, atomic=True, faults=(MASK, MASK, 0, 0), expected=None):
        observed = execute_memory_uil(program, 'run', before)
        expected = expected or dict(status=0 if observed['status'] == 'complete' else 1,
            steps=observed['steps'], words=observed['words'], cut=cut if observed['status'] == 'complete' else 0)
        capture = '$held' if '$held' in program['variables'] else '$i'
        result.append(dict(name=name, program=program, before=before, atomic=atomic,
                           capture=capture, faults=faults, expected=expected))
    for name in ('normal', 'empty', 'early_return', 'zero_loop', 'nested', 'load_bounds',
                 'store_bounds', 'div_zero', 'mod_zero', 'loop_limit', 'budget', 'exact_budget', 'ordered_trap'):
        p = model()
        body = p['functions']['run']['body']
        if name == 'empty':
            body.clear()
        elif name == 'early_return':
            body[:] = [{'op': 'return'}, {'op': 'store', 'index': 8, 'value': 99}]
        elif name == 'zero_loop':
            body[0]['condition'] = 0
        elif name == 'nested':
            p['variables']['$j'] = {'type': 'u32', 'initial': 0}
            body[0]['condition']['right'] = 2
            body[0]['body'][:0] = [{'op': 'set', 'var': '$j', 'value': 0},
                {'op': 'while', 'limit': 2, 'condition': {'op': 'lt', 'left': {'var': '$j'}, 'right': 2},
                 'body': [{'op': 'set', 'var': '$j', 'value': {'op': 'add', 'left': {'var': '$j'}, 'right': 1}}]}]
        elif name in ('load_bounds', 'store_bounds', 'div_zero', 'mod_zero', 'ordered_trap'):
            fault = {'op': 'store', 'index': 8, 'value': 1} if name == 'store_bounds' else {
                'op': 'set', 'var': '$i', 'value': {'load': 8} if name == 'load_bounds' else
                {'op': name.split('_')[0], 'left': 17, 'right': 0}}
            if name == 'ordered_trap':
                fault = {'op': 'set', 'var': '$i', 'value': {
                    'op': 'add', 'left': {'load': 8}, 'right': {'load': 7}}}
            body.insert(1, fault)
        elif name == 'loop_limit':
            body[0]['limit'] = 7
        elif name == 'budget':
            p['functions']['run']['max_steps'] = 26
        elif name == 'exact_budget':
            p['functions']['run']['max_steps'] = 27
        cut = dict(normal=8, nested=2, exact_budget=8).get(name, 0)
        for repeat in range(2):
            add(name + '/' + str(repeat), p, [MASK, 0, 1, 2, 3, 4, 5, 6], cut=cut)
    operations = ('add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'shr',
                  'div', 'mod', 'eq', 'ne', 'lt', 'le', 'gt', 'ge')
    dynamic = {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 18},
        'variables': {'$held': {'type': 'u32', 'initial': 0x80000001}},
        'functions': {'run': {'max_steps': 16, 'body': [
            {'op': 'store', 'index': 2 + i, 'value': {
                'op': op, 'left': {'load': 0}, 'right': {'load': 1}}} for i, op in enumerate(operations)]}}}
    edges = (0, 1, 0x7fff, 0x8000, 0xffff, 0x10000, 0x7fffffff, 0x80000000, MASK)
    for a in edges:
        for b in edges:
            add('dynamic/%08x/%08x' % (a, b), dynamic, [a, b] + [0] * 16, cut=0x80000001)
    operands = ((MASK, 2), (0, 1), (MASK, 3), (0xf0f0, 0xff), (0xf0f0, 0xff),
        (0xf0f0, 0xff), (0x80000001, 33), (0x80000001, 33), (MASK, 3), (MASK, 3),
        (5, 5), (5, 5), (MASK, 0), (MASK, MASK), (MASK, 0), (0, 0))
    literal = deepcopy(dynamic)
    literal['memory']['words'] = 16
    literal['variables']['$held']['initial'] = MASK
    literal['functions']['run']['body'] = [{'op': 'store', 'index': i,
        'value': {'op': op, 'left': a, 'right': b}}
        for i, (op, (a, b)) in enumerate(zip(operations, operands))]
    for repeat in range(2):
        add('literal/' + str(repeat), literal, [0] * 16, cut=MASK)
    indices = (8191, 8192, 16383, 16384, 65535, 65536, 69999)
    large = model(70000)
    large['functions']['run']['body'] = [{'op': 'store', 'index': i,
        'value': {'op': 'add', 'left': {'load': i}, 'right': 1}} for i in indices]
    before = [0] * 70000
    for n, i in enumerate(indices):
        before[i] = MASK if n % 2 else n
    for repeat in range(2):
        add('70000-words/' + str(repeat), large, before)
    # A 16-bit int must not narrow either the loop counter, captured local or
    # charged budget. The short case writes first, then refuses at return.
    counter = model(1)
    counter['functions']['run'] = {'max_steps': 140002, 'body': [
        {'op': 'while', 'limit': 70000,
         'condition': {'op': 'lt', 'left': {'var': '$i'}, 'right': 69999},
         'body': [{'op': 'set', 'var': '$i', 'value': {'op': 'add', 'left': {'var': '$i'}, 'right': 1}}]},
        {'op': 'store', 'index': 0, 'value': {'var': '$i'}}, {'op': 'return'}]}
    add('u32-counter-budget-complete', counter, [0], cut=69999)
    short_counter = deepcopy(counter)
    short_counter['functions']['run']['max_steps'] -= 1
    add('u32-counter-budget-refusal', short_counter, [0])
    # These are declared storage faults around the real paged carrier, not
    # simulated resource exhaustion. The initial while statement also costs
    # one step: read index3 fails at12 and write index4 at15.
    for name, faults, steps in [('read-fault', (3, MASK, 0, 0), 12),
                                ('write-fault', (MASK, 4, 0, 0), 15),
                                ('clone-fault', (MASK, MASK, 1, 0), 0)]:
        add(name, model(), [0] * 8, faults=faults,
            expected=dict(status=2, steps=steps, words=[0] * 8, cut=0))
    faulting = model()
    faulting['functions']['run']['body'].insert(1, {'op': 'store', 'index': 8, 'value': 1})
    add('private-partial', faulting, [0] * 8, atomic=False,
        expected=dict(status=1, steps=27, words=[1] * 8, cut=0))
    add('restore-fault', faulting, [0] * 8, faults=(MASK, MASK, 0, 1),
        expected=dict(status=2, steps=27, words=[1] * 8, cut=0))
    return result


HOOKS = r'''#include "M16HOST.H"
static FdbU32 bad_read,bad_write,bad_clone,bad_copy,reads,writes,first_read;
void probe_set(FdbU32 r,FdbU32 w,FdbU32 c,FdbU32 s){
bad_read=r;bad_write=w;bad_clone=c;bad_copy=s;reads=writes=0UL;first_read=4294967295UL;}
FdbU32 probe_reads(void){return reads;}FdbU32 probe_writes(void){return writes;}
FdbU32 probe_first(void){return first_read;}
static int probe_read(const Fdb16Arena *a,FdbU32 i,FdbU32 *v){
reads++;if(first_read==4294967295UL)first_read=i;
return i==bad_read?1:fdb16_read(a,i,v);}
static int probe_write(Fdb16Arena *a,FdbU32 i,FdbU32 v){
writes++;return i==bad_write?1:fdb16_write(a,i,v);}
static Fdb16Arena *probe_clone(const Fdb16Arena *a){return bad_clone?NULL:fdb16_clone(a);}
static int probe_copy(Fdb16Arena *a,const Fdb16Arena *b){return bad_copy?1:fdb16_copy(a,b);}
#define fdb16_read probe_read
#define fdb16_write probe_write
#define fdb16_clone probe_clone
#define fdb16_copy probe_copy
'''

MAIN = r'''#include "M16HOST.H"
#include <string.h>
void probe_set(FdbU32,FdbU32,FdbU32,FdbU32);
FdbU32 probe_reads(void);FdbU32 probe_writes(void);FdbU32 probe_first(void);
PROTOTYPES
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show){
Fdb16File *in,*out;Fdb16Arena *arena;FdbBlockResult result;
FdbU32 count,row,f,n,pairs,i,index,value,faults[4];char magic[8];int failed,j;
(void)instance;(void)previous;(void)command;(void)show;
in=fdb16_file_open("IN.BIN",0);if(!in)return 2;
if(fdb16_file_read(in,magic,8UL) || memcmp(magic,"FDBNIN1\0",8) || fdb16_read32(in,&count)){fdb16_file_close(in);return 2;}
out=fdb16_file_open("OUT.BIN",1);if(!out){fdb16_file_close(in);return 2;}
failed=fdb16_write_bytes(out,"FDBNOP1\0",8UL) || fdb16_write32(out,count);
for(row=0UL;row<count && !failed;row++){
failed=fdb16_read32(in,&f) || fdb16_read32(in,&n) || fdb16_read32(in,&pairs);
for(j=0;j<4 && !failed;j++)failed=fdb16_read32(in,&faults[j]);
if(failed)break;arena=fdb16_create(n);if(!arena){failed=1;break;}
for(i=0UL;i<pairs && !failed;i++)failed=fdb16_read32(in,&index) || fdb16_read32(in,&value) || fdb16_write(arena,index,value);
if(failed){fdb16_release(arena);break;}
probe_set(faults[0],faults[1],faults[2],faults[3]);
switch(f){DISPATCH default:failed=1;break;}
if(!failed)failed=fdb16_write32(out,row) || fdb16_write32(out,n) ||
fdb16_write32(out,result.status) || fdb16_write32(out,result.steps) || fdb16_write32(out,result.cut) ||
fdb16_write32(out,probe_reads()) || fdb16_write32(out,probe_writes()) || fdb16_write32(out,probe_first()) || fdb16_dump_words(out,arena);
fdb16_release(arena);
}
if(!failed)failed=fdb16_file_eof(in)!=1 || fdb16_write_bytes(out,"DONEOP1\0",8UL);
if(fdb16_file_close(in))failed=1;if(fdb16_file_close(out))failed=1;
return failed?2:0;
}
'''

# The linked common object's unused GUI-facing entry points still require a
# core ABI. This fixture never calls those stubs and carries no game logic.
STUB = r'''#include "M16HOST.H"
const Fdb16Config *fdb16_config(void){return NULL;}
int fdb16_core_open(const char *p){(void)p;return 1;}
const Fdb16Arena *fdb16_core_words(void){return NULL;}
int fdb16_core_initialize(FdbU32 c){(void)c;return 1;}
int fdb16_core_dispatch(FdbU32 a,FdbU32 b,FdbU32 c,FdbU32 d,FdbU32 e,FdbU32 f,FdbU32 g){
(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;return 1;}
int fdb16_core_call(FdbU16 f,const Fdb16Arena *p,FdbU32 n,int r){(void)f;(void)p;(void)n;(void)r;return 1;}
int fdb16_core_replace(const Fdb16Arena *p){(void)p;return 1;}
int fdb16_core_select(FdbU16 s,FdbU16 v){(void)s;(void)v;return 1;}
int fdb16_core_selected(FdbU16 s){(void)s;return -1;}
Fdb16Count fdb16_core_revision(void){Fdb16Count v={0UL,0UL};return v;}
Fdb16Count fdb16_core_calls(FdbU16 f){(void)f;return fdb16_core_revision();}
Fdb16Count fdb16_core_region_calls(FdbU16 s,FdbU16 v){(void)s;(void)v;return fdb16_core_revision();}
const char *fdb16_core_error(void){return "unused authored core";}
void fdb16_core_close(void){}
'''


def test_real_ne_unsigned_operations_atomicity_and_full_segmented_arena(tmp_path):
    spec = importlib.util.spec_from_file_location('fdb_win16_native_ops_guest', VM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.Client()
    job = 'w16-ops-' + uuid.uuid4().hex[:12]
    corpus = cases()
    functions = {}
    script = bytearray(b'FDBNIN1\0' + struct.pack('<I', len(corpus)))
    for item in corpus:
        key = (digest(item['program']), item['atomic'], item['capture'])
        if key not in functions:
            functions[key] = (len(functions), item)
        function = functions[key][0]
        pairs = [(i, v) for i, v in enumerate(item['before']) if v]
        script.extend(struct.pack('<7I', function, len(item['before']), len(pairs), *item['faults']))
        for index, value in pairs:
            script.extend(struct.pack('<2I', index, value))
    source = HOOKS
    prototypes, dispatch = [], []
    for number, item in functions.values():
        symbol = 'native_' + str(number)
        source += '\n#pragma code_seg("OP' + str(number) + '")\n' + emit_win16_memory_function(
            item['program'], 'run', symbol, atomic=item['atomic'], capture_local=item['capture'])
        prototypes.append('FdbBlockResult ' + symbol + '(Fdb16Arena *);')
        dispatch.append('case ' + str(number) + 'UL:result=' + symbol + '(arena);break;')
    main = MAIN.replace('PROTOTYPES', '\n'.join(prototypes)).replace('DISPATCH', '\n'.join(dispatch))
    sources = {'M16ABI.H': WIN16_MEMORY_HEADER.encode(), 'OPS.C': source.encode(),
               'MAIN.C': main.encode(), 'STUB.C': STUB.encode(), 'IN.BIN': bytes(script)}
    for alias, name in [('M16HOST.H', 'memory-win16.h'), ('M16COM.C', 'memory-win16-common.c')]:
        sources[alias] = files('fdisbull').joinpath('native_runtime/' + name).read_bytes()
    for name, data in sources.items():
        (tmp_path / name).write_bytes(data)
        client.put(job, name, data)
    (tmp_path / 'cases.json').write_text(json.dumps(corpus, separators=(',', ':')) + '\n')
    argv = ['wcl', '-bt=windows', '-ml', '-zq', '-w4', '-i=/opt/watcom/h', '-i=/opt/watcom/h/win',
            '-l=windows', '-fe=OPS.EXE', 'MAIN.C', 'OPS.C', 'M16COM.C', 'STUB.C']
    built = client.run(job, argv, timeout=180)
    assert built['exit_code'] == 0, built['stdout'] + built['stderr']
    image = client.get(job, 'OPS.EXE')
    (tmp_path / 'OPS.EXE').write_bytes(image)
    assert image[:2] == b'MZ'
    ne = struct.unpack_from('<I', image, 0x3c)[0]
    assert image[ne:ne + 2] == b'NE' and image[ne + 0x36] == 2
    ran = client.run(job, ['wine', 'OPS.EXE'], timeout=180)
    assert ran['exit_code'] == 0, ran
    data = client.get(job, 'OUT.BIN')
    (tmp_path / 'OUT.BIN').write_bytes(data)
    assert data[:12] == b'FDBNOP1\0' + struct.pack('<I', len(corpus))
    at = 12
    for row, item in enumerate(corpus):
        ordinal, words, status, steps, cut, reads, writes, first_read = struct.unpack_from('<8I', data, at)
        at += 32
        assert ordinal == row and words == len(item['before']), item['name']
        actual = list(struct.unpack_from('<' + str(words) + 'I', data, at))
        at += words * 4
        expected = item['expected']
        assert (status, steps, cut) == (expected['status'], expected['steps'], expected['cut']), item['name']
        assert actual == expected['words'], item['name']
        if item['name'].startswith('ordered_trap/'):
            assert reads == 8 and first_read == 0
        if item['name'].startswith('70000-words/'):
            assert reads == writes == 7 and first_read == 8191
    assert data[at:] == b'DONEOP1\0', 'missing footer or trailing bytes is not a completed batch'
    receipt = dict(schema='fdisbull-win16-native-memory-qualification-v1', result='passed',
        cases=len(corpus), unique_functions=len(functions), guest_job=job, compiler=argv,
        build=built, runtime=ran, logical_words_max=max(len(c['before']) for c in corpus),
        operations=16, dynamic_operand_pairs=81,
        ceiling='Generic authored UIL/ABI qualification, separate from recovered Snake versus DOS.',
        artifacts=[dict(name=p.name, bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(tmp_path.iterdir()) if p.is_file()])
    (tmp_path / 'qualification.json').write_text(json.dumps(receipt, indent=2) + '\n')
