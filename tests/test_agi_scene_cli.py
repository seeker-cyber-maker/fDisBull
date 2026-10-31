"""Public AGI census surface; authored source independent of the producer."""
import json
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import respond


def assert_hashes(doc):
    def digest(value):
        return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=True).encode()).hexdigest()
    assert doc['sha256'] == digest({k: v for k, v in doc.items() if k != 'sha256'})
    for row in doc['logics']:
        ir = row.get('ir', {})
        if ir.get('body_included'):
            assert ir['sha256'] == digest(ir['instructions'])
            assert all(type(i['end_offset']) is int for i in ir['instructions'])


def source(root):
    # One assignment and a variable room transfer. Proper empty message table.
    code = bytes([3, 30, 7, 19, 30])
    payload = len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])
    (root / 'LOGDIR').write_bytes(bytes(3))
    for filename in ('PICDIR', 'VIEWDIR', 'SNDDIR'):
        (root / filename).write_bytes(b'')
    (root / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)


def test_projectless_json_uses_selected_stage_and_keeps_ir(tmp_path):
    source(tmp_path)
    result = respond({'method': 'agi-scenes', 'params': {
        'game_dir': str(tmp_path), 'profile': '2.917', 'stage': 'resolve', 'include_ir': True,
    }}, default_project='must-not-open.fdb')
    assert result['ok'], result
    doc = result['result']
    assert doc['scenes'][0]['room'] == 7
    assert doc['coverage']['accepted_uil_interactions'] == 0
    assert doc['executable'] is False
    assert doc['logics'][0]['ir']['instruction_count'] == 2
    assert len(doc['logics'][0]['ir']['instructions']) == 2
    assert not list(tmp_path.glob('*.fdb'))
    assert_hashes(doc)


def test_real_cli_outline_and_resolve(tmp_path):
    source(tmp_path)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    outputs = {}
    for stage in ('outline', 'resolve'):
        completed = subprocess.run([
            sys.executable, '-m', 'fdisbull', 'agi-scenes', str(tmp_path),
            '--profile', '2.917', '--stage', stage,
            '--include-ir',
        ], env=env, capture_output=True, text=True, timeout=20)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        response = json.loads(completed.stdout)
        assert response['ok'], response
        outputs[stage] = response['result']
        assert_hashes(outputs[stage])
    assert outputs['outline']['scenes'] == []
    assert [scene['room'] for scene in outputs['resolve']['scenes']] == [7]
    assert outputs['outline']['coverage']['present_logics'] == 1
    assert outputs['outline']['logics'][0]['ir']['sha256'] == outputs['resolve']['logics'][0]['ir']['sha256']


@pytest.mark.parametrize('option,value', [('profile', 'SCI'), ('stage', 'execute'),
                                         ('max_updates', True), ('include_ir', 1),
                                         ('include_text', 'yes')])
def test_invalid_public_options_fail_without_a_project(tmp_path, option, value):
    source(tmp_path)
    params = {'game_dir': str(tmp_path), 'profile': '2.917', option: value}
    response = respond({'method': 'agi-scenes', 'params': params})
    assert response['ok'] is False


def test_global_instruction_budget_keeps_an_opaque_resource(tmp_path):
    source(tmp_path)
    result = respond({'method': 'agi-scenes', 'params': {
        'game_dir': str(tmp_path), 'profile': '2.917', 'max_instructions': 1,
    }})
    assert result['ok'], result
    doc = result['result']
    assert doc['coverage']['present_logics'] == 1
    assert doc['coverage']['instruction_budget_stops'] == 1
    assert doc['coverage']['logic_layout_complete'] is False
    assert doc['coverage']['value_analysis_complete'] is False
    assert doc['logics'][0]['status'] == 'instruction_budget'
    assert doc['logics'][0]['opaque_resource'] is True
    assert doc['logics'][0]['representation'] == 'low_level_ir'


def test_false_condition_is_valid_low_level_ir(tmp_path):
    code = bytes.fromhex('ff00ff0200120700')
    payload = len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])
    source(tmp_path)
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    result = respond({'method': 'agi-scenes', 'params': {
        'game_dir': str(tmp_path), 'profile': '2.917', 'include_ir': True,
    }})
    assert result['ok'], result
    doc = result['result']
    assert doc['coverage']['logic_layout_complete'] is True
    token = doc['logics'][0]['conditions'][0]['ordered_tokens'][0]
    assert token['opcode'] == 0 and token['operation'] == 'false'
    assert token['operands'] == []
    assert doc['logics'][0]['ir']['instructions'][0]['conditions'][0] == token


def test_context_dependent_trace_command_never_proves_one_branch(tmp_path):
    # The second trace.on consumes an extra byte on the original traced path.
    # A fixed-width CFG would lose the assignment of 9 and falsely prove 7.
    code = bytes.fromhex('0c0a95ff0701ff0600032807fe05009500032809132800')
    payload = len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])
    source(tmp_path)
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    result = respond({'method': 'agi-scenes', 'params': {
        'game_dir': str(tmp_path), 'profile': '2.917', 'include_ir': True,
    }})
    assert result['ok'], result
    doc = result['result']
    assert doc['logics'][0]['status'] == 'layout_error'
    assert 'trace.on' in doc['logics'][0]['error']
    assert doc['logics'][0]['opaque_resource'] is True
    assert doc['coverage']['value_analysis_complete'] is False
    assert doc['scenes'] == []


def test_code_byte_budget_charges_large_condition_operands(tmp_path):
    # Two action instructions, but a long condition and its operands still
    # consume decode/output space. This bound is independent of action count.
    code = bytes([255, 14, 10]) + bytes([1, 0]) * 10 + bytes([255, 0, 0, 0])
    payload = len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])
    source(tmp_path)
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    result = respond({'method': 'agi-scenes', 'params': {
        'game_dir': str(tmp_path), 'profile': '2.917', 'max_code_bytes': 20,
    }})
    assert result['ok'], result
    doc = result['result']
    assert doc['logics'][0]['status'] == 'instruction_budget'
    assert 'code-byte budget' in doc['logics'][0]['error']
    assert doc['coverage']['logic_layout_complete'] is False


def test_vocabulary_and_inventory_bindings_keep_text_opt_in(tmp_path):
    source(tmp_path)
    code = bytes.fromhex('ff0e010700ff02005c0000')
    payload = len(code).to_bytes(2, 'little') + code + bytes([0, 2, 0])
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    # One A-indexed word, group 7; one encrypted object, ID 0 at room 5.
    header = bytearray(52)
    header[:2] = (52).to_bytes(2, 'big')
    (tmp_path / 'WORDS.TOK').write_bytes(bytes(header) + b'\0\x1e\x0f\x0f\x13\x9a\x00\x07')
    plain = bytes([3, 0, 1, 3, 0, 5]) + b'authored item\0'
    key = b'Avis Durgan'
    (tmp_path / 'OBJECT').write_bytes(bytes(v ^ key[i % len(key)] for i, v in enumerate(plain)))
    for include_text in (False, True):
        response = respond({'method': 'agi-scenes', 'params': {
            'game_dir': str(tmp_path), 'profile': '2.917', 'include_text': include_text,
        }})
        assert response['ok'], response
        doc = response['result']
        assert_hashes(doc)
        assert doc['coverage']['vocabulary_groups'] == 1
        assert doc['coverage']['inventory_objects'] == 1
        pattern = doc['logics'][0]['command_patterns'][0]
        assert pattern['word_groups'] == [{'number': 7, 'dictionary_status': 'ok', 'role': 'word_group'}]
        assert doc['logics'][0]['references'][0]['resource_status'] == [{'number': 0, 'status': 'ok'}]
        encoded = json.dumps(doc)
        assert ('apple' in encoded) is include_text
        assert ('authored item' in encoded) is include_text
