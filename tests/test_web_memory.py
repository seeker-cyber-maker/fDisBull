"""Generic array/loop profiles: reference, actual Wasm and optional real GPU."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.udc_web_memory import (build_memory_block, execute_memory_uil,
                                    validate_memory_uil)


def model():
    v = {'var': '$i'}
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 8},
            'variables': {'$i': {'type': 'u32', 'initial': 0}},
            'functions': {'run': {'max_steps': 100, 'body': [
                {'op': 'while', 'limit': 8, 'condition': {'op': 'lt', 'left': v, 'right': 8}, 'body': [
                    {'op': 'store', 'index': v, 'value': {'op': 'add', 'left': {'load': v}, 'right': 1}},
                    {'op': 'set', 'var': '$i', 'value': {'op': 'add', 'left': v, 'right': 1}},
                ]}, {'op': 'return'}]}}}


def test_reference_loop_wrap_and_owned_result():
    p = model(); source = [0xffffffff, 0, 1, 2, 3, 4, 5, 6]
    result = execute_memory_uil(p, 'run', source)
    assert result['status'] == 'complete'
    assert result['words'] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert source[0] == 0xffffffff
    result['words'][1] = 99
    assert source[1] == 0


@pytest.mark.parametrize('fault', ['load', 'store', 'div', 'mod', 'loop', 'steps'])
def test_reference_refuses_atomically(fault):
    p = model(); body = p['functions']['run']['body']
    if fault == 'load': body.append({'op': 'set', 'var': '$i', 'value': {'load': 8}})
    elif fault == 'store': body.insert(1, {'op': 'store', 'index': 8, 'value': 1})
    elif fault in ('div', 'mod'): body.insert(1, {'op': 'set', 'var': '$i', 'value': {'op': fault, 'left': 5, 'right': 0}})
    elif fault == 'loop': body[0]['limit'] = 7
    else: p['functions']['run']['max_steps'] = 2
    # A return makes later operations unreachable: place bad load before it.
    if fault == 'load': body[-2], body[-1] = body[-1], body[-2]
    before = [7] * 8
    result = execute_memory_uil(p, 'run', before)
    assert result['status'] == 'refused'
    assert result['words'] == before == [7] * 8


@pytest.mark.parametrize('mutate', [
    lambda p: p['memory'].update(words=0),
    lambda p: p['memory'].update(words=131073),
    lambda p: p['variables']['$i'].update(type='u16'),
    lambda p: p['functions']['run'].update(max_steps=4000001),
    lambda p: p['functions']['run']['body'].append({'op': 'file_read'}),
    lambda p: p['functions']['run']['body'].append({'op': 'set', 'var': [], 'value': 0}),
    lambda p: p['functions']['run']['body'].append({'op': 'store', 'index': -1, 'value': 0}),
])
def test_strict_schema_preflights_untaken_nodes(mutate):
    p = model(); mutate(p)
    with pytest.raises(ValueError): validate_memory_uil(p)


def test_wrong_input_refuses_before_narrowing():
    p = model()
    for values in ([0] * 7, [0] * 7 + [-1], [0] * 7 + [True], [0] * 7 + [0x100000000]):
        with pytest.raises(ValueError): execute_memory_uil(p, 'run', values)


def test_build_identity_is_deterministic_and_existing_output_refuses(tmp_path):
    p = model()
    a = build_memory_block(p, 'run', 'wasm32-memory-1', tmp_path / 'a')
    b = build_memory_block(p, 'run', 'wasm32-memory-1', tmp_path / 'b')
    assert a == b and not a['execution'] and not a['source_to_uil']
    assert (tmp_path / 'a/block.wasm').read_bytes() == (tmp_path / 'b/block.wasm').read_bytes()
    with pytest.raises(ValueError): build_memory_block(p, 'run', 'wasm32-memory-1', tmp_path / 'a')
    with pytest.raises(ValueError): build_memory_block(p, 'missing', 'wasm32-memory-1', tmp_path / 'c')


def _prepare(tmp_path):
    programs = {'normal': model()}
    for name in ('bounds', 'div', 'loop', 'steps'):
        p = model()
        if name == 'bounds': p['functions']['run']['body'].insert(1, {'op': 'store', 'index': 8, 'value': 1})
        elif name == 'div': p['functions']['run']['body'].insert(1, {'op': 'set', 'var': '$i', 'value': {'op': 'div', 'left': 5, 'right': 0}})
        elif name == 'loop': p['functions']['run']['body'][0]['limit'] = 7
        else: p['functions']['run']['max_steps'] = 3
        programs[name] = p
    for name, p in programs.items():
        for target, sub in [('wasm32-memory-1', 'wasm'), ('webgpu-wgsl-memory-1', 'gpu')]:
            build_memory_block(p, 'run', target, tmp_path / name / sub)
    runtime = Path(__file__).parents[1] / 'src/fdisbull/web_runtime/memory.mjs'
    shutil.copyfile(runtime, tmp_path / 'memory.mjs')
    return programs


def _arithmetic():
    # Independent expected answers exercise every admitted opcode and unsigned edge.
    items = [('add', 0xffffffff, 1, 0), ('sub', 0, 1, 0xffffffff),
             ('mul', 65535, 65535, 4294836225), ('and', 0xab, 0xf0, 0xa0),
             ('or', 0xa0, 0x0b, 0xab), ('xor', 0xab, 0xff, 0x54),
             ('shl', 1, 32, 1), ('shl', 0xffffffff, 1, 0xfffffffe),
             ('shr', 0x80000000, 31, 1), ('div', 0xffffffff, 2, 2147483647),
             ('mod', 0xffffffff, 600, 495), ('eq', 7, 7, 1), ('ne', 7, 8, 1),
             ('lt', 0x80000000, 1, 0), ('le', 7, 7, 1),
             ('gt', 0xffffffff, 0, 1), ('ge', 7, 7, 1)]
    p = model(); p['memory']['words'] = len(items)
    p['functions']['run']['body'] = [
        {'op': 'store', 'index': i, 'value': {'op': op, 'left': a, 'right': b}}
        for i, (op, a, b, _) in enumerate(items)]
    return p, [item[-1] for item in items]


def test_all_unsigned_opcodes_reference():
    p, expected = _arithmetic()
    result = execute_memory_uil(p, 'run', [0] * len(expected))
    assert result['status'] == 'complete'
    assert result['words'] == expected


@pytest.mark.skipif(not shutil.which('node'), reason='Real Wasm execution requires Node')
def test_arithmetic_and_reused_json_nodes_execute_as_a_tree(tmp_path):
    p, expected = _arithmetic()
    build_memory_block(p, 'run', 'wasm32-memory-1', tmp_path / 'math')
    p = model()
    p['functions']['run']['body'] = [p['functions']['run']['body'][0]] * 2
    # The second identical loop starts with i=8 and executes zero iterations.
    build_memory_block(p, 'run', 'wasm32-memory-1', tmp_path / 'alias')
    shutil.copyfile(Path(__file__).parents[1] / 'src/fdisbull/web_runtime/memory.mjs', tmp_path / 'memory.mjs')
    script = """
import fs from 'node:fs/promises';import assert from 'node:assert/strict';
import {createWasmMemoryProvider} from './memory.mjs';
const expected=EXPECTED;
for(const name of ['math','alias']) {
 const build=JSON.parse(await fs.readFile(name+'/build.json'));
 const provider=await createWasmMemoryProvider(build,await fs.readFile(name+'/block.wasm'));
 const result=await provider.invoke(new Uint32Array(build.abi.memory_words));
 assert.equal(result.status,'complete');assert.deepEqual(Array.from(result.words),name==='math'?expected:Array(8).fill(1));
 await provider.dispose();
}
""".replace('EXPECTED', json.dumps(expected))
    (tmp_path / 'run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'), 'run.mjs'], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Real Wasm execution requires Node')
def test_actual_wasm_arrays_loops_faults_and_input_ownership(tmp_path):
    _prepare(tmp_path)
    script = """
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createWasmMemoryProvider} from './memory.mjs';
for(const name of ['normal','bounds','div','loop','steps']) {
 const build=JSON.parse(await fs.readFile(name+'/wasm/build.json'));
 const provider=await createWasmMemoryProvider(build,await fs.readFile(name+'/wasm/block.wasm'));
 const values=[0xffffffff,0,1,2,3,4,5,6];
 const run=provider.invoke(values);values[0]=42;
 const result=await run;
 assert.equal(result.status,name==='normal'?'complete':'refused');
 assert.deepEqual(Array.from(result.words),name==='normal'?[0,1,2,3,4,5,6,7]:[0xffffffff,0,1,2,3,4,5,6]);
 assert.throws(()=>provider.invoke([-1,0,0,0,0,0,0,0]));
 assert.throws(()=>provider.invoke([0,0,0,0,0,0,0,0x100000000]));
 const description=provider.describe();description.abi.memory_words=99;
 assert.equal(provider.describe().abi.memory_words,8);
 await provider.dispose();assert.equal(provider.closed,true);
 await assert.rejects(provider.invoke([0,0,0,0,0,0,0,0]));
}
console.log('passed');
"""
    (tmp_path / 'run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'), 'run.mjs'], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == 'passed'


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'), reason='Real GPU needs explicit dependency root')
def test_actual_gpu_matches_wasm_and_atomic_faults(tmp_path):
    _prepare(tmp_path)
    arithmetic, expected = _arithmetic()
    build_memory_block(arithmetic, 'run', 'webgpu-wgsl-memory-1', tmp_path / 'math')
    script = """
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {createGPUMemoryProvider} from './memory.mjs';
const require=createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT,'package.json'));
const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
let gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]);
const adapter=await gpu.requestAdapter();assert.equal(adapter.info.isFallbackAdapter,false);
const device=await adapter.requestDevice();
try {
 for(const name of ['normal','bounds','div','loop','steps']) {
  const build=JSON.parse(await fs.readFile(name+'/gpu/build.json'));
  const provider=await createGPUMemoryProvider(build,await fs.readFile(name+'/gpu/block.wgsl','utf8'),{device});
  const values=[0xffffffff,0,1,2,3,4,5,6];const task=provider.invoke(values);values[0]=42;
  const result=await task;assert.equal(result.status,name==='normal'?'complete':'refused');
  assert.deepEqual(Array.from(result.words),name==='normal'?[0,1,2,3,4,5,6,7]:[0xffffffff,0,1,2,3,4,5,6]);
  await provider.dispose();
 }
 const mathBuild=JSON.parse(await fs.readFile('math/build.json'));
 const math=await createGPUMemoryProvider(mathBuild,await fs.readFile('math/block.wgsl','utf8'),{device});
 const mathResult=await math.invoke(new Uint32Array(mathBuild.abi.memory_words));
 assert.equal(mathResult.status,'complete');assert.deepEqual(Array.from(mathResult.words),EXPECTED);
 await math.dispose();
 const b=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_SRC});b.destroy();
} finally {device.destroy();gpu=null;}
console.log('passed');
""".replace('EXPECTED', json.dumps(expected))
    (tmp_path / 'run.mjs').write_text(script)
    run = subprocess.run([shutil.which('node'), 'run.mjs'], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == 'passed'
