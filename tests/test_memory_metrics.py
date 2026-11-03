"""Opt-in exact charges across real Wasm/GPU success, refusal and traps."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.udc_web_memory import build_memory_block, execute_memory_uil


def model():
    v = {'var': '$i'}
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 8},
            'variables': {'$i': {'type': 'u32', 'initial': 0}},
            'functions': {'run': {'max_steps': 100, 'body': [
                {'op': 'while', 'limit': 8, 'condition': {'op': 'lt', 'left': v, 'right': 8}, 'body': [
                    {'op': 'store', 'index': v, 'value': {'op': 'add', 'left': {'load': v}, 'right': 1}},
                    {'op': 'set', 'var': '$i', 'value': {'op': 'add', 'left': v, 'right': 1}},
                ]}, {'op': 'return'}]}}}


@pytest.mark.parametrize('target,artifact,artifact_hash,receipt_hash', [
    ('wasm32-memory-1', 'block.wasm',
     'fef1e3a63ef8389b2d83f53c960146c2a9d731feac699f959862ddf77317af5b',
     'a3c505246423842e37ee7040d6f595afc23092a6feb5ad7ac0e73bb55fd0180c'),
    ('webgpu-wgsl-memory-1', 'block.wgsl',
     '572fb731bb51772b08c8c24ae6a5d275c78b9e606c1bc2a3555563cccec27ccb',
     'bf6983233334e2e5da3916a8492084a7849a717569a70e1aec1b733bc5f58a50'),
])
def test_default_retains_pre_metrics_artifact_and_receipt_bytes(tmp_path, target, artifact, artifact_hash, receipt_hash):
    # Captured from the unchanged compiler before this optional ABI was added.
    first = build_memory_block(model(), 'run', target, tmp_path / 'first')
    second = build_memory_block(model(), 'run', target, tmp_path / 'second', report_steps=False)
    assert first == second and 'report_steps' not in first['abi']
    for root in ('first', 'second'):
        assert hashlib.sha256((tmp_path / root / artifact).read_bytes()).hexdigest() == artifact_hash
        assert hashlib.sha256((tmp_path / root / 'build.json').read_bytes()).hexdigest() == receipt_hash


@pytest.mark.parametrize('invalid', [None, 0, 1, 'true', [], {}])
def test_metrics_option_requires_exact_bool_before_writing(tmp_path, invalid):
    with pytest.raises(ValueError, match='boolean'):
        build_memory_block(model(), 'run', 'wasm32-memory-1', tmp_path / 'output', report_steps=invalid)
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('invalid', [None, '$i', [1], ['$unknown'], ['$i', '$i'], {'$i': True}])
def test_capture_requires_distinct_declared_names(tmp_path, invalid):
    with pytest.raises(ValueError, match='local capture'):
        build_memory_block(model(), 'run', 'wasm32-memory-1', tmp_path / 'output', capture_locals=invalid)
    assert not (tmp_path / 'output').exists()


def _prepare(tmp_path):
    cases = {}
    for name in ('normal', 'empty', 'early_return', 'zero_loop', 'nested',
                 'bounds_load', 'bounds_store', 'div', 'mod', 'loop_limit', 'budget', 'exact_budget', 'capture_only', 'metrics_only'):
        p = model()
        body = p['functions']['run']['body']
        if name == 'empty':
            body.clear()
        elif name == 'early_return':
            body[:] = [{'op': 'return'}, {'op': 'store', 'index': 8, 'value': 99}]
        elif name == 'zero_loop':
            body[0]['condition'] = 0
        elif name == 'nested':
            # Two outer iterations, each containing a fresh two-step inner loop.
            p['variables']['$j'] = {'type': 'u32', 'initial': 0}
            body[0]['condition']['right'] = 2
            body[0]['body'][:0] = [
                {'op': 'set', 'var': '$j', 'value': 0},
                {'op': 'while', 'limit': 2,
                 'condition': {'op': 'lt', 'left': {'var': '$j'}, 'right': 2},
                 'body': [{'op': 'set', 'var': '$j', 'value': {'op': 'add', 'left': {'var': '$j'}, 'right': 1}}]}]
        elif name in ('bounds_load', 'bounds_store', 'div', 'mod'):
            fault = {'op': 'store', 'index': 8, 'value': 1} if name == 'bounds_store' else {
                'op': 'set', 'var': '$i',
                'value': {'load': 8} if name == 'bounds_load' else {'op': name, 'left': 17, 'right': 0}}
            body.insert(1, fault)
        elif name == 'loop_limit':
            body[0]['limit'] = 7
        elif name == 'budget':
            p['functions']['run']['max_steps'] = 26
        elif name == 'exact_budget':
            p['functions']['run']['max_steps'] = 27
        elif name == 'capture_only':
            p['variables']['$z'] = {'type': 'u32', 'initial': 0xffffffff}
            body.pop()  # Capture must also happen on ordinary fallthrough.
        input_words = [0xffffffff, 0, 1, 2, 3, 4, 5, 6]
        expected = execute_memory_uil(p, 'run', input_words)
        for target, sub in [('wasm32-memory-1', 'wasm'), ('webgpu-wgsl-memory-1', 'gpu')]:
            captures = ['$z', '$i'] if name == 'capture_only' else ([] if name == 'metrics_only' else ['$i'])
            receipt = build_memory_block(p, 'run', target, tmp_path / name / sub,
                                         report_steps=name != 'capture_only',
                                         capture_locals=captures)
            assert receipt['abi'].get('report_steps', False) is (name != 'capture_only')
            assert receipt['abi'].get('capture_locals', []) == sorted(captures)
            assert receipt['abi']['memory_words'] == 8
        cases[name] = {'input': input_words, 'expected': {k: expected[k] for k in ('status', 'words', 'steps')}}
        if expected['status'] == 'complete' and name != 'metrics_only':
            cases[name]['expected']['locals'] = {'$i': {'normal': 8, 'empty': 0, 'early_return': 0,
                'zero_loop': 0, 'nested': 2, 'exact_budget': 8, 'capture_only': 8}[name]}
        if name == 'capture_only':
            del cases[name]['expected']['steps']
            cases[name]['expected']['locals']['$z'] = 0xffffffff
    # Independent counts: loop admission + 9 conditions + 16 body operations + return.
    assert cases['normal']['expected']['steps'] == 27
    assert cases['budget']['expected']['steps'] == 26
    assert cases['exact_budget']['expected']['steps'] == 27
    assert cases['empty']['expected']['steps'] == 0
    assert cases['early_return']['expected']['steps'] == 1
    assert cases['zero_loop']['expected']['steps'] == 3
    assert cases['nested']['expected']['steps'] == 23
    (tmp_path / 'cases.json').write_text(json.dumps(cases))
    shutil.copyfile(Path(__file__).parents[1] / 'src/fdisbull/web_runtime/memory.mjs', tmp_path / 'memory.mjs')
    shutil.copyfile(Path(__file__).with_name('metrics_checks.mjs'), tmp_path / 'metrics_checks.mjs')


@pytest.mark.skipif(not shutil.which('node'), reason='Real Wasm requires Node')
def test_actual_wasm_exact_charges_and_refusal_ownership(tmp_path):
    _prepare(tmp_path)
    run = subprocess.run([shutil.which('node'), 'metrics_checks.mjs', 'wasm'], cwd=tmp_path,
                         capture_output=True, text=True, timeout=45)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout.splitlines()[-1])['invocations'] == 28


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'), reason='Real GPU requires explicit dependency root')
def test_actual_gpu_exact_charges_and_refusal_ownership(tmp_path):
    _prepare(tmp_path)
    run = subprocess.run([shutil.which('node'), 'metrics_checks.mjs', 'gpu'], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout.splitlines()[-1])['invocations'] == 28
