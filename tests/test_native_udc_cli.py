"""Public direct native UDL-to-UDC route keeps baseline and relayout distinct."""
import json
import os
from pathlib import Path
import subprocess
import sys

from fdisbull.cli import respond
from fdisbull.project import Project


ASSUMPTIONS = dict.fromkeys(('no_code_reads', 'no_code_writes', 'no_computed_entries',
                             'address_identity_unobserved', 'timing_unobserved'), True)


def _project(tmp_path):
    binary = tmp_path/'OVERLAP.BIN'; binary.write_bytes(bytes.fromhex('7401a8aac3'))
    path = tmp_path/'private.fdb'
    with Project.create(path, binary, arch='x86', bits=16, base=0x1000) as project:
        project.analyze()
    return path, binary


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),
               PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run([sys.executable, '-B', '-m', 'fdisbull', *map(str, args)],
                               env=env, capture_output=True, text=True, timeout=20)
    return completed, json.loads(completed.stdout)


def test_cli_direct_passthrough_after_reopen_without_uil_or_original_file(tmp_path):
    path, binary = _project(tmp_path)
    completed, captured = _cli('udc-native-capture', path, 'overlap',
                               '--entry', '0x1002', '--entry', '0x1003')
    assert completed.returncode == 0 and captured['ok'], captured
    definition = captured['result']['id']
    assert 'document' not in captured['result']
    binary.unlink()
    completed, inspected = _cli('udc-native-info', path, definition)
    assert completed.returncode == 0 and inspected['ok'], inspected
    completed, emitted = _cli('udc-native-compile', path, definition)
    assert completed.returncode == 0 and emitted['ok'], emitted
    result = emitted['result']
    assert result['mode'] == 'original-layout'
    assert result['qualification'] == 'original_bytes_only'
    assert result['byte_identity'] and not result['source_layout_modified']
    assert result['bytes'] == '7401a8aac3'
    assert result['filename'] == 'OVERLAP.BIN'
    assert result['native_execution'] is False and result['semantic_qualification'] == 'unverified'
    assert 'uil' not in result and 'layout' not in result


def test_json_grouping_and_udc_compile_share_stable_ports_across_placement(tmp_path):
    path, _ = _project(tmp_path)
    with Project(path) as project:
        grouped = project.code_blocks([0x1002, 0x1003])
        assert grouped['source_layout_modified'] is False and grouped['group_placement'] == 'unplaced'
        definition = project.udc_native_capture('experiment', [0x1002, 0x1003])
    groups = [block['id'] for block in grouped['blocks']]
    results = []
    for order in (groups, list(reversed(groups))):
        response = respond({'method': 'udc-native-compile', 'params': {
            'project': str(path), 'definition': definition['id'], 'mode': 'relayout',
            'base': 0x200, 'assumptions': ASSUMPTIONS, 'block_order': order}})
        assert response['ok'], response
        result = response['result']; layout = result['layout']
        assert result['qualification'] == 'structural_only' and not result['byte_identity']
        assert set(layout['logical_blocks']) == set(groups)
        assert layout['placement']['block_order'] == order
        assert layout['entries']['x86:16:little@0x1003'] != layout['entries']['x86:16:little@0x1002']+1
        results.append(result)
    assert results[0]['definition_sha256'] == results[1]['definition_sha256']
    assert results[0]['capsule_sha256'] == results[1]['capsule_sha256']
    assert results[0]['plan_sha256'] == results[1]['plan_sha256']
    assert results[0]['layout_sha256'] != results[1]['layout_sha256']


def test_cli_relayout_requires_explicit_assertions_and_default_rejects_placement(tmp_path):
    path, _ = _project(tmp_path)
    with Project(path) as project:
        definition = project.udc_native_capture('overlap', [0x1002, 0x1003])['id']
    completed, result = _cli('udc-native-compile', path, definition, '--mode', 'relayout')
    assert completed.returncode != 0 and not result['ok']
    completed, result = _cli('udc-native-compile', path, definition, '--base', '0x200')
    assert completed.returncode != 0 and not result['ok']
    assertions = tmp_path/'assumptions.json'; assertions.write_text(json.dumps(ASSUMPTIONS))
    completed, result = _cli('udc-native-compile', path, definition, '--mode', 'relayout',
                              '--base', '0x200', '--assumptions', assertions)
    assert completed.returncode == 0 and result['ok'], result
    assert result['result']['layout']['entries']['x86:16:little@0x1002'] == 0x200


def test_code_blocks_cli_honors_explicit_instruction_boundary(tmp_path):
    source = tmp_path/'linear.bin'; source.write_bytes(bytes.fromhex('9090c3'))
    path = tmp_path/'linear.fdb'
    with Project.create(path, source, arch='x86', bits=16, base=0x1000) as project:
        project.analyze()
    completed, result = _cli('code-blocks', path, '--entry', '0x1000',
                              '--split-at', 'x86:16:little@0x1001')
    assert completed.returncode == 0 and result['ok'], result
    assert len(result['result']['blocks']) == 2
    assert result['result']['source_layout_modified'] is False
