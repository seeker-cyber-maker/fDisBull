"""Real selected region calculations with explicit behavior alternatives."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull import udc_memory_layers as exact_layers
from fdisbull import udc_memory_regions as regions
from fdisbull.udc_memory_shell import build_memory_shell
from fdisbull.udc_web_memory import execute_memory_uil


def expression(multiplier=1, increment=1):
    return {'op': 'and', 'left': {'op': 'add', 'left': {
        'op': 'mul', 'left': {'load': 0}, 'right': multiplier},
        'right': increment}, 'right': 255}


def model():
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 16},
            'variables': {}, 'functions': {
                'advance': {'max_steps': 5, 'body': [
                    {'id': 'advance.prefix', 'op': 'store', 'index': 2,
                     'value': {'op': 'add', 'left': {'load': 2}, 'right': 1}},
                    {'id': 'advance.branch', 'op': 'if',
                     'condition': {'op': 'eq', 'left': {'load': 10}, 'right': 1},
                     'then': [
                         {'id': 'advance.update', 'op': 'store', 'index': 0,
                          'value': expression()},
                         {'id': 'advance.changed', 'op': 'store', 'index': 1, 'value': 1}],
                     'else': []},
                    {'id': 'advance.tail', 'op': 'store', 'index': 2,
                     'value': {'op': 'add', 'left': {'load': 2}, 'right': 1}}]},
                'draw': {'max_steps': 5, 'body': [
                    {'id': 'draw.first', 'op': 'store', 'index': 4,
                     'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                    {'id': 'draw.second', 'op': 'store', 'index': 5, 'value': 0},
                    {'id': 'draw.third', 'op': 'store', 'index': 6, 'value': 1},
                    {'id': 'draw.fourth', 'op': 'store', 'index': 7,
                     'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                    {'id': 'draw.done', 'op': 'store', 'index': 1, 'value': 0}]}}}


def initial():
    return [10, 0, 0, 7] + [0] * 12


def shell_plan():
    return {'format': 'fdisbull-memory-orchestration-1', 'title': 'Selected update',
            'help': 'A generic one-word update with a declared alternative.',
            'initialize': 'advance', 'concurrency': 'ordered-events',
            'bindings': {'advance': 'wasm', 'draw': 'wasm', 'update': 'wasm'},
            'inputs': list(range(8, 15)),
            'outputs': {'advance': [[0, 3]], 'draw': [[1, 1], [4, 4]], 'update': [[0, 1]]},
            'commit_ranges': [[0, 3], [4, 4]], 'replace_ranges': [[0, 3], [4, 4]],
            'scratch_ranges': [[15, 1]], 'guards': [
                {'index': 0, 'min': 0, 'max': 65535}, {'index': 3, 'min': 7, 'max': 7}],
            'render': {'function': 'draw', 'when_nonzero': 1},
            'frame': {'offset': 4, 'width': 2, 'height': 2,
                      'palette': {'0': [0, 0, 0], '1': [255, 255, 255]}},
            'events': {'function': 'advance', 'kind': 8, 'ascii': 9, 'scan': 10,
                       'x': 11, 'y': 12, 'buttons': 13, 'clock': 14, 'quit_index': 2,
                       'keyboard_kind': 1, 'pointer_kind': 2, 'clock_kind': 3, 'tick_ms': 55},
            'keymap': {'KeyA': {'ascii': 0, 'scan': 0}}, 'logic_functions': ['advance']}


def exact_selections(project, program):
    result = {}
    arena = {'arena': {'type': 'u32-array', 'words': 16}}
    for backend, target in [('wasm', 'wasm32-memory-1'), ('webgpu', 'webgpu-wgsl-memory-1')]:
        bindings = {}
        for fn in program['functions']:
            contract = exact_layers.register_contract(project, {
                'format': 'fdisbull-block-contract-1', 'name': 'owner.' + fn,
                'inputs': arena, 'outputs': arena,
                'behavior': {'kind': 'memory-uil', 'program': program, 'function': fn}})
            layer = exact_layers.register_layer(project, {
                'format': 'fdisbull-udl-layer-1', 'name': backend + '.' + fn,
                'contract': contract['id'], 'implementation': {'backend': 'memory-uil',
                    'target': target, 'program': program, 'function': fn}})
            bindings[fn] = layer['id']
        result[backend] = exact_layers.select_layers(project, 'owner.' + backend,
            bindings, program=program, target=target)['id']
    return result


def region_plan(project, program):
    descriptor = {'name': 'update',
                  'source': {'function': 'advance', 'entry': 'advance.update', 'count': 1},
                  'reads': [0], 'output': {'index': 0, 'min': 0, 'max': 255}}
    arena = {'arena': {'type': 'u32-array', 'words': 16}}
    contract = regions.register_contract(project, {'format': 'fdisbull-block-contract-1',
        'name': 'selected.update', 'inputs': arena, 'outputs': arena,
        'behavior': {'kind': 'memory-region', 'program': program, 'region': descriptor}})
    variants = {}
    for name, value in [('original', expression()), ('alternate', expression(5, 3)), ('outside', 256)]:
        implementation = {'format': 'fdisbull-memory-uil-1', 'role': 'uil',
            'memory': {'words': 16}, 'variables': {}, 'functions': {'update': {
                'max_steps': 1, 'body': [{'op': 'store', 'index': 0, 'value': value}]}}}
        choices = {}
        for backend, target in [('wasm', 'wasm32-memory-1'), ('webgpu', 'webgpu-wgsl-memory-1')]:
            layer = regions.register_layer(project, {'format': 'fdisbull-udl-layer-1',
                'name': backend + '.' + name, 'contract': contract['id'],
                'assurance': 'exact-source-region' if name == 'original' else 'intentional-behavior-variant',
                'implementation': {'backend': 'memory-region', 'target': target,
                    'program': implementation, 'function': 'update'}})
            choices[backend] = regions.select_layers(project, name + '.' + backend,
                {'update': layer['id']}, program=program, target=target)['id']
        variants[name] = {'label': name.title(), 'selections': choices}
    return {'format': 'fdisbull-memory-regions-1', 'module_uil_sha256': digest(program),
            'allow_behavior_variants': True,
            'slots': {'update': {'label': 'Update algorithm', 'default': 'original', 'variants': variants}}}


def prepare(tmp_path):
    source = tmp_path / 'authored.com'; source.write_bytes(bytes.fromhex('b8004ccd21'))
    program = model()
    with Project.create(tmp_path / 'region.fdb', source, image='com') as project:
        build_memory_shell(project, exact_selections(project, program), shell_plan(), initial(),
            tmp_path / 'browser', cuts={'format': 'fdisbull-memory-cuts-2',
                'module_uil_sha256': digest(program),
                'cuts': [{'caller': 'advance', 'entry': 'advance.update', 'callee': 'update'}]},
            regions=region_plan(project, program))
    words = initial(); words[10] = 1
    result = execute_memory_uil(program, 'advance', words)
    assert result['status'] == 'complete' and result['steps'] == 5
    result = execute_memory_uil(program, 'draw', result['words'])
    expected = initial()
    for start, count in shell_plan()['commit_ranges']:
        expected[start:start + count] = result['words'][start:start + count]
    (tmp_path / 'expected.json').write_text(json.dumps(expected))
    shutil.copyfile(Path(__file__).with_name('memory_region_shell_checks.mjs'),
                    tmp_path / 'memory_region_shell_checks.mjs')


def test_region_builder_preserves_canonical_and_honest_realization_hashes(tmp_path):
    preserved = deepcopy(model()); prepare(tmp_path)
    manifest = json.loads((tmp_path / 'browser/memory-shell.json').read_text())
    assert manifest['program'] == preserved == model()
    assert manifest['module_uil_sha256'] == digest(preserved)
    assert set(manifest['program']['functions']) == {'advance', 'draw'}
    assert set(manifest['execution_program']['functions']) == {'advance', 'draw', 'update'}
    assert manifest['execution_uil_sha256'] == digest(manifest['execution_program'])
    assert manifest['cuts']['module_uil_sha256'] == manifest['execution_uil_sha256']
    for target in manifest['region_variants'].values():
        for choice, variant in target['update'].items():
            program = manifest['regions']['slots']['update']['variants'][choice]['program']
            assert variant['build']['module_uil_sha256'] == digest(program)
            assert variant['build']['module_uil_sha256'] != manifest['module_uil_sha256']
            assert variant['build']['abi']['memory_words'] == 16


def run_runtime(tmp_path, gpu):
    prepare(tmp_path)
    args = [shutil.which('node'), 'memory_region_shell_checks.mjs', 'browser', 'expected.json']
    if gpu: args.append('--gpu')
    run = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=100)
    assert run.returncode == 0, run.stdout + run.stderr
    receipt = json.loads(run.stdout.strip().splitlines()[-1])
    assert receipt['status'] == 'passed' and len(receipt['checks']) >= 12
    if gpu: assert receipt['adapter']['isFallbackAdapter'] is False
    (tmp_path / 'runtime-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


@pytest.mark.skipif(not shutil.which('node'), reason='Actual Wasm needs Node')
def test_actual_region_wasm_shell(tmp_path):
    run_runtime(tmp_path, False)


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'),
                    reason='Actual GPU needs explicit dependency root')
def test_actual_region_mixed_gpu_shell(tmp_path):
    run_runtime(tmp_path, True)
