"""Public project, JSON and CLI seams for the bounded DOS compiler."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from fdisbull.cli import respond
from fdisbull.project import Project


ASSUMPTIONS = dict.fromkeys(('no_code_reads', 'no_code_writes', 'no_computed_entries',
                             'address_identity_unobserved', 'timing_unobserved'), True)
PROJECTION = {'bindings': {'ax': '$value'}, 'inputs': [], 'outputs': ['ax']}


def fixture(tmp_path):
    source = tmp_path/'GAME.COM'
    source.write_bytes(bytes.fromhex('b80100eb0190f4') + bytes(9) + bytes.fromhex('0601'))
    path = tmp_path/'private.fdb'
    with Project.create(path, source, image='com') as project:
        project.analyze()
        native = project.udc_native_capture('original', ['1000:0100'])
        plan = project.udc_native_info(native['id'], include_blocks=True)['document']['plan']
        compute = next(b for b in plan['blocks'] if b['bytes'] == 'b80100eb01')
        stop = next(b for b in plan['blocks'] if b['bytes'] == 'f4')
    return path, source, native, compute, stop


def cli(*args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),
               PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run([sys.executable, '-B', '-m', 'fdisbull', *map(str, args)],
                               env=env, text=True, capture_output=True, timeout=30)
    return completed, json.loads(completed.stdout)


@pytest.mark.parametrize('container', ['com', 'mz'])
def test_cli_defines_selects_and_compiles_variable_size_block(tmp_path, container):
    path, source, native, compute, stop = fixture(tmp_path)
    data = tmp_path/'data.json'; data.write_text(json.dumps([{'id': 'table', 'ip': 0x110, 'size': 2}]))
    refs = tmp_path/'refs.json'; refs.write_text(json.dumps([
        {'kind': 'near-code-pointer', 'data': 'table', 'offset': 0,
         'target': stop['id'], 'expected_hex': '0601'}]))
    completed, response = cli('udc-dos-define', path, 'standard', native['id'],
                                '--data', data, '--references', refs)
    assert completed.returncode == 0 and response['ok'], response
    definition = response['result']['id']
    assert 'document' not in response['result']
    projection = tmp_path/'projection.json'; projection.write_text(json.dumps(PROJECTION))
    completed, response = cli('udc-dos-implementation', path, definition, compute['id'],
                                'b80100b80100', '--expected-block-revision', compute['block_revision'],
                                '--purpose', 'register-equivalence', '--projection', projection)
    assert completed.returncode == 0 and response['ok'], response
    implementation = response['result']['id']
    completed, inspected = cli('udc-dos-implementation-info', path, implementation)
    assert completed.returncode == 0 and inspected['ok'], inspected
    assert inspected['result']['qualification']['status'] == 'equivalent_under_assumptions'
    selection = tmp_path/'selection.json'; selection.write_text(json.dumps({compute['id']: implementation}))
    assertions = tmp_path/'assumptions.json'; assertions.write_text(json.dumps(ASSUMPTIONS))
    completed, emitted = cli('udc-dos-compile', path, definition,
                               '--implementations', selection, '--assumptions', assertions,
                               '--container', container)
    assert completed.returncode == 0 and emitted['ok'], emitted
    result = emitted['result']; raw = bytes.fromhex(result['bytes'])
    assert result['qualification'] == 'structural_only' and result['native_execution'] is False
    prefix = 0 if container == 'com' else 0x120
    assert raw[prefix] == 0xe9
    assert int.from_bytes(raw[prefix+0x10:prefix+0x12], 'little') == result['ports'][stop['id']]
    assert result['implementations'][compute['id']]['id'] == implementation
    with Project(path) as project:
        exact = project.udc_native_compile(native['id'])
        assert bytes.fromhex(exact['bytes']) == source.read_bytes()


def test_json_compile_reports_experiment_without_upgrading_projection(tmp_path):
    path, _, native, compute, stop = fixture(tmp_path)
    with Project(path) as project:
        definition = project.udc_dos_define('standard', native['id'],
            data=[{'id': 'table', 'ip': 0x110, 'size': 2}], references=[{
                'kind': 'near-code-pointer', 'data': 'table', 'offset': 0,
                'target': stop['id'], 'expected_hex': '0601'}])
        implementation = project.udc_dos_implementation(definition['id'], compute['id'], 'b80200',
            expected_block_revision=compute['block_revision'])
    response = respond({'method': 'udc-dos-compile', 'params': {'project': str(path),
        'definition': definition['id'], 'implementations': {compute['id']: implementation['id']},
        'assumptions': ASSUMPTIONS}})
    assert response['ok'], response
    selected = response['result']['implementations'][compute['id']]
    assert selected['purpose'] == 'experiment' and selected['qualification']['status'] == 'unverified'
    assert response['result']['qualification'] == 'structural_only'


def test_cli_refuses_missing_assumptions_and_wrong_revision(tmp_path):
    path, _, native, compute, _ = fixture(tmp_path)
    with Project(path) as project:
        definition = project.udc_dos_define('standard', native['id'])['id']
    completed, response = cli('udc-dos-compile', path, definition)
    assert completed.returncode != 0 and not response['ok']
    completed, response = cli('udc-dos-implementation', path, definition, compute['id'], '90',
                                '--expected-block-revision', '0'*64)
    assert completed.returncode != 0 and not response['ok']
