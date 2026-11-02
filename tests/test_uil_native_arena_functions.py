"""Indexed native arena entry points use the same typed, owned function cores."""
from copy import deepcopy
import os
import shutil
import subprocess

import pytest

from fdisbull.common_uil import digest
from fdisbull.uil_native import _FLAGS as STRICT_C_FLAGS
from test_uil_codegen import const, documents, function, op, typ, var
from test_uil_native_codegen import build_native, emit, native_directory


def arena_bundle(*, entry=0):
    array = {'type': 'u32-array', 'length': 4}
    load = lambda index: {'op': 'load', 'array': 0, 'index': const(index)}
    increment = function([array], [0], [0], [
        {'op': 'store', 'array': 0, 'index': const(0),
         'value': op('add', 'u32', load(0), const(1))},
        {'op': 'require', 'condition': op('ne', 'bool', load(1), const(0))},
        {'op': 'return'}], constants=[typ('u32')] * 2)
    multiply = function([array], [0], [0], [
        {'op': 'store', 'array': 0, 'index': const(0),
         'value': op('mul', 'u32', load(0), const(1))},
        {'op': 'store', 'array': 0, 'index': const(2),
         'value': op('add', 'u32', load(0), const(3))},
        {'op': 'return'}], constants=[typ('u32')] * 4)
    scalar = function([typ('u32')], [0], [0], [{'op': 'return'}])
    shorter = function([{'type': 'u32-array', 'length': 2}], [0], [0],
                       [{'op': 'return'}])
    caller = function([array], [0], [0], [
        {'op': 'call', 'function': 1, 'inputs': [var(0)], 'outputs': [0]},
        {'op': 'return'}])
    docs = documents([increment, multiply, scalar, shorter, caller], [
        {'initial': [[0] * 4], 'constants': ['0', '1']},
        {'initial': [[0] * 4], 'constants': ['0', '3', '2', '7']},
        {'initial': ['0'], 'constants': []},
        {'initial': [[0] * 2], 'constants': []},
        {'initial': [[0] * 4], 'constants': []}])
    docs[0]['entry'] = entry
    docs[1]['program_sha256'] = docs[3]['program_sha256'] = digest(docs[0])
    return docs


def test_indexed_arena_metadata_excludes_incompatible_shape_and_length():
    docs = arena_bundle()
    before = deepcopy(docs)
    manifest = emit(docs)
    assert docs == before
    adapter = manifest['legacy_arena_adapter']
    assert adapter['available'] and adapter['words'] == 4
    assert adapter['symbol'] == 'fdb_block'
    assert adapter['function_symbol'] == 'fdb_function_block'
    assert adapter['function_limited_symbol'] == 'fdb_function_block_limit'
    assert adapter['aggregate_step_limit'] == {'min': 1, 'max': 4000000,
                                               'exhaustion': 'before-next-charge'}
    assert adapter['functions'] == [
        {'index': 0, 'words': 4}, {'index': 1, 'words': 4}, {'index': 4, 'words': 4}]
    assert manifest['abi']['legacy_arena_adapter'] == adapter
    header = manifest['sources']['native-core.h']
    assert '#define FDB_NATIVE_ARENA_WORDS 4u' in header
    assert '#define FDB_NATIVE_ARENA_FUNCTION_COUNT 3u' in header
    assert 'fdb_function_block(uint32_t function_index, uint32_t *words)' in header
    assert 'fdb_function_block_limit(uint32_t function_index, uint32_t *words, uint32_t remaining_steps)' in header


@pytest.mark.parametrize('arithmetic', ['portable-c', 'native-asm'])
@pytest.mark.parametrize('entry', [0, 1])
def test_native_indexed_arena_functions_and_refusals_are_atomic(native_directory, arithmetic, entry):
    manifest, _ = build_native(native_directory, arena_bundle(entry=entry), arithmetic)
    assert [row['index'] for row in manifest['legacy_arena_adapter']['functions']] == [0, 1, 4]
    caller = native_directory / 'indexed-caller.c'
    caller.write_text('''#include "native-core.h"
#include <stdio.h>
int main(void){
 uint32_t words[4]={UINT32_MAX,1,23,42},before[4];FdbBlockResult r;
 r=fdb_block(words);printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,words[0],words[2]);
 words[0]=5;r=fdb_function_block(1u,words);
 printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,words[0],words[2]);
 words[0]=7;r=fdb_function_block(4u,words);
 printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,words[0],words[2]);
 words[0]=9;words[1]=0;memcpy(before,words,sizeof(words));
 r=fdb_function_block(0u,words);
 printf("%u %u %u %d\\n",r.status,r.steps,r.cut,memcmp(before,words,sizeof(words))==0);
 uint32_t rejected[3]={2u,3u,UINT32_MAX};
 for(unsigned i=0;i<3;i++){r=fdb_function_block(rejected[i],words);
 printf("%u %u %u %d\\n",r.status,r.steps,r.cut,memcmp(before,words,sizeof(words))==0);}
 r=fdb_function_block(1u,NULL);printf("%u %u %u\\n",r.status,r.steps,r.cut);
 return 0;
}''')
    compiler = os.environ.get('FDISBULL_NATIVE_TEST_COMPILER') or shutil.which('clang') or shutil.which('gcc')
    executable = native_directory / 'indexed-caller'
    built = subprocess.run([compiler, *STRICT_C_FLAGS, '-DFDB_NATIVE_NO_MAIN',
        str(native_directory / 'program.c'), str(native_directory / 'numeric.c'),
        str(caller), '-o', str(executable)], capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        '0 3 0 0 23' if entry == 0 else '0 3 0 4294967293 4',
        '0 3 0 15 22', '0 5 0 21 28', '1 2 0 1',
        '1 0 0 1', '1 0 0 1', '1 0 0 1', '1 0 0']


def test_incompatible_entry_does_not_invent_an_arena_anchor():
    manifest = emit(arena_bundle(entry=2))
    assert manifest['legacy_arena_adapter']['available'] is False
    assert manifest['legacy_arena_adapter']['functions'] == []
    assert 'FdbBlockResult fdb_function_block(' not in manifest['sources']['program.c']


@pytest.mark.parametrize('arithmetic', ['portable-c', 'native-asm'])
def test_native_remaining_budget_stops_before_next_charge_and_rolls_back(native_directory, arithmetic):
    build_native(native_directory, arena_bundle(), arithmetic)
    caller = native_directory/'limited-caller.c'
    caller.write_text('''#include "native-core.h"
#include <stdio.h>
uint64_t fdb_math_count(unsigned,unsigned);
int main(void){
 uint32_t a[4]={5,1,23,42},b[4],before[4];FdbBlockResult r,s;
 memcpy(b,a,sizeof(a));r=fdb_function_block_limit(1u,a,3u);s=fdb_function_block(1u,b);
 printf("%u %u %u %u %u %d %d\\n",r.status,r.steps,r.cut,s.status,s.steps,memcmp(a,b,sizeof(a))==0,fdb_math_count(1u,0u)>0);
 a[0]=5;a[1]=1;a[2]=23;a[3]=42;memcpy(before,a,sizeof(a));
 r=fdb_function_block_limit(1u,a,2u);
 printf("%u %u %u %d\\n",r.status,r.steps,r.cut,memcmp(a,before,sizeof(a))==0);
 r=fdb_function_block_limit(4u,a,4u);
 printf("%u %u %u %d\\n",r.status,r.steps,r.cut,memcmp(a,before,sizeof(a))==0);
 r=fdb_function_block_limit(4u,a,5u);
 printf("%u %u %u %u %u\\n",r.status,r.steps,r.cut,a[0],a[2]);
 memcpy(before,a,sizeof(a));uint32_t invalid[2]={0u,FDB_NATIVE_ARENA_MAX_STEPS+1u};
 for(unsigned i=0;i<2;i++){r=fdb_function_block_limit(1u,a,invalid[i]);
 printf("%u %u %u %d %d\\n",r.status,r.steps,r.cut,memcmp(a,before,sizeof(a))==0,fdb_math_count(1u,0u)==0);}
 r=fdb_function_block_limit(1u,a,3u);if(r.status||!fdb_math_count(1u,0u)){return 4;}
 memcpy(before,a,sizeof(a));
 r=fdb_function_block_limit(UINT32_MAX,a,3u);
 printf("%u %u %u %d %d\\n",r.status,r.steps,r.cut,memcmp(a,before,sizeof(a))==0,fdb_math_count(1u,0u)==0);
 return 0;
}''')
    compiler = os.environ.get('FDISBULL_NATIVE_TEST_COMPILER') or shutil.which('clang') or shutil.which('gcc')
    executable = native_directory/'limited-caller'
    built = subprocess.run([compiler, *STRICT_C_FLAGS, '-DFDB_NATIVE_NO_MAIN',
        str(native_directory/'program.c'), str(native_directory/'numeric.c'), str(caller),
        '-o', str(executable)], capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        '0 3 0 0 3 1 1', '1 2 0 1', '1 4 0 1', '0 5 0 15 22',
        '1 0 0 1 1', '1 0 0 1 1', '1 0 0 1 1']


def test_effectful_closure_does_not_admit_other_array_functions():
    docs = arena_bundle()
    docs[0]['functions'][2]['constants'] = [typ('resource')]
    docs[0]['functions'][2]['body'] = [
        {'op': 'effect', 'service': 'text.show', 'inputs': [const(0)]}]
    docs[0]['capabilities'].append('host.effects@1')
    docs[0]['capabilities'].sort()
    docs[1]['resources'] = [{'kind': 'text', 'text': 'A planned event'}]
    docs[1]['functions'][2]['constants'] = [0]
    docs[1]['program_sha256'] = docs[3]['program_sha256'] = digest(docs[0])
    manifest = emit(docs)
    assert manifest['legacy_arena_adapter']['available'] is False
    assert manifest['legacy_arena_adapter']['functions'] == []

