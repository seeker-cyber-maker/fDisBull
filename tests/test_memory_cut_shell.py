"""Actual compute checks for selectable nested blocks under one frozen UIL."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull import udc_memory_layers as layers
from fdisbull.udc_memory_shell import build_memory_shell
from fdisbull.udc_web_memory import execute_memory_uil


def model(budget=7):
    increment = {'op': 'add', 'left': {'load': 0},
                 'right': {'op': 'add', 'left': {'load': 9}, 'right': 1}}
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 16},
            'variables': {}, 'functions': {
                'advance': {'max_steps': budget, 'body': [
                    {'id': 'advance.prefix', 'op': 'store', 'index': {'load': 11},
                     'value': {'op': 'add', 'left': {'load': 0}, 'right': 1}},
                    {'id': 'advance.private-temporary', 'op': 'store', 'index': 3, 'value': 8},
                    {'id': 'advance.branch', 'op': 'if',
                     'condition': {'op': 'eq', 'left': {'load': 10}, 'right': 1},
                     'then': [
                         {'id': 'advance.math', 'op': 'store', 'index': 0, 'value': increment},
                         {'id': 'advance.inner-tail', 'op': 'store', 'index': 1, 'value': 1}],
                     'else': [{'id': 'advance.other', 'op': 'store', 'index': 1, 'value': 0}]},
                    {'id': 'advance.restore-temporary', 'op': 'store', 'index': 3, 'value': 7},
                    {'id': 'advance.outer-tail', 'op': 'store', 'index': 2,
                     'value': {'op': 'add', 'left': {'load': 2}, 'right': 1}}]},
                'math': {'max_steps': 1, 'body': [
                    {'id': 'math.add', 'op': 'store', 'index': 0, 'value': deepcopy(increment)}]},
                'constructor': {'max_steps': 1, 'body': [
                    {'id': 'constructor.add', 'op': 'store', 'index': 0,
                     'value': {'op': 'add', 'left': {'load': 0}, 'right': 3}}]},
                'draw': {'max_steps': 5, 'body': [
                    {'id': 'draw.first', 'op': 'store', 'index': 4,
                     'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                    {'id': 'draw.second', 'op': 'store', 'index': 5, 'value': 0},
                    {'id': 'draw.third', 'op': 'store', 'index': 6, 'value': 1},
                    {'id': 'draw.fourth', 'op': 'store', 'index': 7,
                     'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                    {'id': 'draw.done', 'op': 'store', 'index': 1, 'value': 0}]}}}


def plan():
    return {'format': 'fdisbull-memory-orchestration-1', 'title': 'Nested word block',
            'help': 'A source-defined counter with a selected nested math block.',
            'initialize': 'advance', 'concurrency': 'ordered-events',
            'bindings': {fn: 'wasm' for fn in model()['functions']}, 'inputs': list(range(8, 15)),
            'outputs': {'advance': [[0, 3]], 'math': [[0, 1]], 'constructor': [[0, 1]],
                        'draw': [[1, 1], [4, 4]]},
            'commit_ranges': [[0, 3], [4, 4]], 'replace_ranges': [[0, 3], [4, 4]],
            'scratch_ranges': [[15, 1]], 'guards': [
                {'index': 0, 'min': 0, 'max': 1000}, {'index': 3, 'min': 7, 'max': 7}],
            'render': {'function': 'draw', 'when_nonzero': 1},
            'frame': {'offset': 4, 'width': 2, 'height': 2,
                      'palette': {'0': [0, 0, 0], '1': [255, 255, 255]}},
            'events': {'function': 'advance', 'kind': 8, 'ascii': 9, 'scan': 10, 'x': 11,
                       'y': 12, 'buttons': 13, 'clock': 14, 'quit_index': 2,
                       'keyboard_kind': 1, 'pointer_kind': 2, 'clock_kind': 3, 'tick_ms': 55},
            'keymap': {'KeyA': {'ascii': 0, 'scan': 0}}, 'logic_functions': ['advance', 'math']}


def initial():
    return [0, 0, 0, 7] + [0] * 12


def cut_plan(program):
    return {'format': 'fdisbull-memory-cuts-1', 'module_uil_sha256': digest(program),
            'cuts': [{'caller': 'advance', 'entry': 'advance.math', 'callee': 'math'}]}


def selected(project, program):
    result = {}
    arena = {'arena': {'type': 'u32-array', 'words': 16}}
    for backend, target in [('wasm', 'wasm32-memory-1'), ('webgpu', 'webgpu-wgsl-memory-1')]:
        bindings = {}
        for fn in program['functions']:
            contract = layers.register_contract(project, {
                'format': 'fdisbull-block-contract-1', 'name': 'nested.' + fn,
                'inputs': arena, 'outputs': arena,
                'behavior': {'kind': 'memory-uil', 'program': program, 'function': fn}})
            layer = layers.register_layer(project, {
                'format': 'fdisbull-udl-layer-1', 'name': backend + '.' + fn,
                'contract': contract['id'], 'implementation': {
                    'backend': 'memory-uil', 'target': target, 'program': program, 'function': fn}})
            bindings[fn] = layer['id']
        result[backend] = layers.select_layers(project, 'nested.' + backend, bindings,
                                               program=program, target=target)['id']
    return result


def prepare(tmp_path):
    source = tmp_path / 'authored.com'
    source.write_bytes(bytes.fromhex('b8004ccd21'))
    with Project.create(tmp_path / 'nested.fdb', source, image='com') as project:
        for directory, budget in [('browser', 7), ('budget-browser', 6)]:
            program = model(budget)
            build_memory_shell(project, selected(project, program), plan(), initial(),
                               tmp_path / directory, cuts=cut_plan(program))
    patches = [{10: 1, 9: 2}, {10: 0, 9: 7}, {10: 1, 9: 0}, {10: 1, 9: 4}]
    state = initial()
    vectors = []
    for patch in patches:
        words = state.copy()
        for key, value in patch.items():
            words[key] = value
        result = execute_memory_uil(model(), 'advance', words)
        assert result['status'] == 'complete'
        charged = result['steps']
        words = result['words']
        if words[1]:
            result = execute_memory_uil(model(), 'draw', words)
            assert result['status'] == 'complete'
            words = result['words']
        for start, count in plan()['commit_ranges']:
            state[start:start + count] = words[start:start + count]
        vectors.append({'patch': patch, 'words': state.copy(), 'caller_steps': charged})
    (tmp_path / 'vectors.json').write_text(json.dumps(vectors))
    shutil.copyfile(Path(__file__).with_name('memory_cut_shell_checks.mjs'),
                    tmp_path / 'memory_cut_shell_checks.mjs')


def test_cut_builder_keeps_canonical_identity_and_memory_domain(tmp_path):
    original = model()
    preserved = deepcopy(original)
    prepare(tmp_path)
    manifest = json.loads((tmp_path / 'browser/memory-shell.json').read_text())
    assert original == preserved == manifest['program']
    assert manifest['module_uil_sha256'] == digest(original)
    assert manifest['cuts']['module_uil_sha256'] == digest(original)
    assert manifest['cuts_sha256'] == digest(manifest['cuts'])
    for variants in manifest['cut_variants'].values():
        for variant in variants['advance'].values():
            abi = variant['build']['abi']
            assert abi['memory_words'] == 16 and abi['report_steps'] is True
            assert abi['capture_locals'] == [manifest['cuts']['functions']['advance']['token_local']]
    words = initial()
    words[10] = 1
    assert execute_memory_uil(model(6), 'advance', words)['status'] == 'refused'
    words[11] = 16
    assert execute_memory_uil(model(), 'advance', words)['status'] == 'refused'


def run_runtime(tmp_path, gpu):
    prepare(tmp_path)
    arguments = [shutil.which('node'), 'memory_cut_shell_checks.mjs', 'browser', 'budget-browser',
                 'vectors.json']
    if gpu:
        arguments.append('--gpu')
    run = subprocess.run(arguments, cwd=tmp_path, capture_output=True, text=True, timeout=80)
    assert run.returncode == 0, run.stdout + run.stderr
    receipt = json.loads(run.stdout.strip().splitlines()[-1])
    assert receipt['status'] == 'passed' and len(receipt['checks']) >= 12
    if gpu:
        assert receipt['adapter']['isFallbackAdapter'] is False
        assert 'selected-nested-gpu-and-wasm-backings-carry-reference-state' in receipt['checks']
    (tmp_path / 'runtime-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


@pytest.mark.skipif(not shutil.which('node'), reason='Actual Wasm needs Node')
def test_actual_nested_wasm_shell(tmp_path):
    run_runtime(tmp_path, False)


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'),
                    reason='Actual GPU needs explicit dependency root')
def test_actual_nested_mixed_gpu_shell(tmp_path):
    run_runtime(tmp_path, True)
