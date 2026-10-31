"""Persistence and real-compute orchestration using a non-game word fixture."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fdisbull.project import Project
from fdisbull import udc_memory_layers as layers
from fdisbull.udc_memory_shell import build_memory_shell, validate_plan


def program(bad=False):
    add = {'op': 'add', 'left': {'load': 0}, 'right': {'op': 'add', 'left': {'load': 9}, 'right': 1}}
    advance = [{'op': 'store', 'index': 0, 'value': add}, {'op': 'store', 'index': 1, 'value': 1}]
    if bad: advance.append({'op': 'store', 'index': 3, 'value': 8})
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 16}, 'variables': {},
            'functions': {'advance': {'max_steps': 100, 'body': advance},
                          'draw': {'max_steps': 100, 'body': [
                              {'op': 'store', 'index': 4, 'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                              {'op': 'store', 'index': 5, 'value': 0},
                              {'op': 'store', 'index': 6, 'value': 1},
                              {'op': 'store', 'index': 7, 'value': {'op': 'and', 'left': {'load': 0}, 'right': 1}},
                              {'op': 'store', 'index': 1, 'value': 0}]}}}


def plan():
    return {'format': 'fdisbull-memory-orchestration-1', 'title': 'Word counter',
            'help': 'Generic four-pixel fixture', 'initialize': 'advance', 'concurrency': 'ordered-events',
            'bindings': {'advance': 'wasm', 'draw': 'wasm'}, 'inputs': list(range(8, 15)),
            'outputs': {'advance': [[0, 2]], 'draw': [[1, 1], [4, 4]]},
            'commit_ranges': [[0, 3], [4, 4]], 'replace_ranges': [[0, 3], [4, 4]],
            'scratch_ranges': [[15, 1]], 'guards': [{'index': 0, 'min': 0, 'max': 1000},
                                                 {'index': 3, 'min': 7, 'max': 7}],
            'render': {'function': 'draw', 'when_nonzero': 1},
            'frame': {'offset': 4, 'width': 2, 'height': 2, 'palette': {'0': [0, 0, 0], '1': [255, 255, 255]}},
            'events': {'function': 'advance', 'kind': 8, 'ascii': 9, 'scan': 10, 'x': 11, 'y': 12,
                       'buttons': 13, 'clock': 14, 'quit_index': 2,
                       'keyboard_kind': 1, 'pointer_kind': 2, 'clock_kind': 3, 'tick_ms': 55},
            'keymap': {'KeyA': {'ascii': 0, 'scan': 0}}, 'logic_functions': ['advance']}


def initial():
    return [0, 0, 0, 7] + [0] * 12


def selected(project, model):
    choices = {}
    contracts = {}
    for backend, target in [('wasm', 'wasm32-memory-1'), ('webgpu', 'webgpu-wgsl-memory-1')]:
        bindings = {}
        for fn in model['functions']:
            arena = {'arena': {'type': 'u32-array', 'words': 16}}
            document = {'format': 'fdisbull-block-contract-1', 'name': 'word.' + fn,
                        'inputs': arena, 'outputs': arena,
                        'behavior': {'kind': 'memory-uil', 'program': model, 'function': fn}}
            contract = layers.register_contract(project, document)
            contracts[fn] = contract
            layer = layers.register_layer(project, {'format': 'fdisbull-udl-layer-1', 'name': backend + '.' + fn,
                'contract': contract['id'], 'implementation': {'backend': 'memory-uil', 'target': target,
                                                               'program': model, 'function': fn}})
            bindings[fn] = layer['id']
        choices[backend] = layers.select_layers(project, 'word.' + backend, bindings, program=model, target=target)['id']
    return choices, contracts


def project_at(tmp_path):
    source = tmp_path / 'authored.com'; source.write_bytes(bytes.fromhex('b8004ccd21'))
    return Project.create(tmp_path / 'word.fdb', source, image='com')


def test_records_reopen_immutable_and_scalar_profiles_refuse(tmp_path):
    from fdisbull.udc_layers import register_contract as scalar_contract
    from fdisbull.udc_web import build_web_block
    model = program()
    with project_at(tmp_path) as p:
        choices, contracts = selected(p, model)
        model['functions']['advance']['body'][0]['value'] = 99
        stored = p.udl_selection_info(choices['wasm'], full=True)['document']
        assert stored['program'] == program()
        with pytest.raises(ValueError): scalar_contract(p, contracts['advance']['document'])
        with pytest.raises(ValueError): build_web_block(p, choices['wasm'], tmp_path / 'bad-scalar')
    with Project(tmp_path / 'word.fdb') as p:
        assert p.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        for choice in choices.values():
            result = layers.run_selection(p, choice, 'advance', initial())
            assert result['status'] == 'complete' and result['words'][0:4] == [1, 1, 0, 7]
            assert result['words'][8:] == initial()[8:]
        wrong = copy.deepcopy(p.udl_layer_info(stored['bindings']['advance'], full=True)['document'])
        wrong['implementation']['program']['functions']['advance']['body'][0]['value'] = 99
        with pytest.raises(ValueError): layers.register_layer(p, wrong)


def test_builder_resolves_every_exact_endpoint_and_new_outputs(tmp_path):
    with project_at(tmp_path) as p:
        choices, _ = selected(p, program())
        manifest = build_memory_shell(p, choices, plan(), initial(), tmp_path / 'browser')
        assert set(manifest['variants']) == {'wasm', 'webgpu'}
        for backend in manifest['variants'].values():
            assert set(backend) == {'advance', 'draw'}
            assert all(x['build']['module_uil_sha256'] == manifest['module_uil_sha256'] for x in backend.values())
        assert not manifest['execution'] and not manifest['source_to_uil']
        with pytest.raises(ValueError): build_memory_shell(p, choices, plan(), initial(), tmp_path / 'browser')
        with pytest.raises(ValueError): build_memory_shell(p, {'wasm': choices['webgpu'], 'webgpu': choices['wasm']}, plan(), initial(), tmp_path / 'wrong')


@pytest.mark.parametrize('extra', [{'adapter': {'ignored': True}}, {'domain': {'arena': 'unrealized'}}])
def test_selection_revalidates_generic_stored_layer_before_execution(tmp_path, extra):
    with project_at(tmp_path) as p:
        choices, _ = selected(p, program())
        selected_doc = p.udl_selection_info(choices['wasm'], full=True)['document']
        bad_layer = p.udl_layer_info(selected_doc['bindings']['advance'], full=True)['document']
        bad_layer.update(extra)
        # The generic immutable store retains declarations; semantic consumers
        # must still reject unsupported profile meaning when reading them.
        bad = p.store_udl_layer(bad_layer)
        bindings = {**selected_doc['bindings'], 'advance': bad['id']}
        with pytest.raises(ValueError):
            layers.select_layers(p, 'bad-layer', bindings, program=program(), target='wasm32-memory-1')
        raw_choice = p.store_udl_selection({**selected_doc, 'name': 'raw-bad-layer', 'bindings': bindings})
        with pytest.raises(ValueError): layers.run_selection(p, raw_choice['id'], 'advance', initial())


@pytest.mark.parametrize('mutate', [
    lambda p: p['commit_ranges'].append([15, 1]),
    lambda p: p['outputs']['advance'].append([3, 1]),
    lambda p: p['inputs'].append(0),
    lambda p: p['frame'].update(offset=14),
    lambda p: p['keymap']['KeyA'].update(ascii=256),
    lambda p: p['events'].update(tick_ms=float('nan')),
])
def test_plan_rejects_ambiguous_footprints_and_invalid_services(mutate):
    value = plan(); mutate(value)
    with pytest.raises(ValueError): validate_plan(value, program())


def prepare_runtime(tmp_path):
    with project_at(tmp_path) as p:
        choices, _ = selected(p, program())
        build_memory_shell(p, choices, plan(), initial(), tmp_path / 'browser')
        choices, _ = selected(p, program(bad=True))
        build_memory_shell(p, choices, plan(), initial(), tmp_path / 'bad-browser')
    helper = Path(__file__).with_name('memory_shell_checks.mjs')
    shutil.copyfile(helper, tmp_path / 'memory_shell_checks.mjs')


@pytest.mark.skipif(not shutil.which('node'), reason='Real Wasm shell checks need Node')
def test_actual_wasm_memory_shell_contracts(tmp_path):
    prepare_runtime(tmp_path)
    run = subprocess.run([shutil.which('node'), 'memory_shell_checks.mjs', 'browser', 'bad-browser'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=40)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result['status'] == 'passed' and len(result['checks']) >= 12


@pytest.mark.skipif(not os.environ.get('FDISBULL_WEBGPU_MODULE_ROOT'), reason='Real GPU needs explicit dependency root')
def test_actual_mixed_memory_shell_contracts(tmp_path):
    prepare_runtime(tmp_path)
    run = subprocess.run([shutil.which('node'), 'memory_shell_checks.mjs', 'browser', 'bad-browser', '--gpu'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result['status'] == 'passed' and result['adapter']['isFallbackAdapter'] is False
    assert 'mixed-bindings-and-carried-state' in result['checks']
