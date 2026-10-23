"""Real CLI/JSON boundaries for persistent architecture-neutral passes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import parser, respond
from fdisbull.project import Project


def cli(*arguments, expected_ok=True):
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    process = subprocess.run([sys.executable, '-m', 'fdisbull', *map(str, arguments)],
                             capture_output=True, text=True, env=env)
    assert process.returncode == (0 if expected_ok else 1), process.stderr + process.stdout
    document = json.loads(process.stdout)
    assert document['ok'] is expected_ok
    return document['result'] if expected_ok else document['error']


@pytest.fixture
def advanced_project(tmp_path):
    # Actual call setup at1000 -> authored memset helper at1020; mapped words
    # at1040. None of these bytes are executed by the tests or the analyzer.
    data = bytearray(96)
    data[:21] = bytes.fromhex('bf40100000be12000000ba04000000e80c000000c3')
    helper = bytes.fromhex('4989f84889d189f0fcf3aa4c89c0c3')
    data[0x20:0x20 + len(helper)] = helper
    data[0x40:0x48] = bytes.fromhex('0100020003000400')
    binary, database = tmp_path / 'caller.bin', tmp_path / 'caller.fdb'
    binary.write_bytes(data)
    cli('import', binary, database, '--arch', 'x86', '--bits', '64', '--base', '0x1000')
    return database, binary


def test_native_and_derived_commands_survive_process_restart(advanced_project):
    database, binary = advanced_project
    result = cli('auto-analyze', database, '--abi', 'x86_64_sysv', '--max-instructions', '100',
                 '--max-functions', '20', '--max-steps', '1000', '--max-entries', '8', '--max-rounds', '8')
    assert result['stable'] and not result['budget_exhausted']
    assert cli('advanced-status', database)['pending'] == 0
    function = cli('function-analysis', database, '0x1000')
    assert function['state'] == 'done' and not function['stale']
    assert function['result']['frame']['calls'][0]['signature_known'] is False
    membership = cli('function-membership', database, '--max-work', '1000', '--max-instructions', '100')
    assert membership['function_boundary_proven'] is False
    binary.unlink()
    effects = cli('call-effects', database, '--address', '0x1040', '--size', '4',
                  '--access', 'write', '--no-unresolved', '--limit', '20', '--offset', '0')
    assert effects['total'] == 1
    effect, = effects['items']
    assert (effect['address'], effect['size'], effect['fill_byte']) == ('0x1040', 4, 0x12)
    assert effect['runtime_observed'] is False
    assert cli('auto-analyze', database)['stable']


def test_type_commands_load_json_files_and_keep_binary_bytes(advanced_project, tmp_path):
    database, _ = advanced_project
    definition = tmp_path / 'words.json'
    definition.write_text(json.dumps(dict(kind='array', element='u16', count=4)))
    defined = cli('define-type', database, 'WordArray', definition, '--author', 'cli-test')
    assert defined['layout']['size'] == 8
    applied = cli('apply-type', database, '0x1040', 'WordArray', '--name', 'saved_words', '--author', 'cli-test')
    assert applied['name'] == 'saved_words'
    typed = cli('typed-data', database, '0x1040', '--max-items', '4')
    assert [item['value'] for item in typed['items']] == [1, 2, 3, 4]
    assert [item['bytes'] for item in typed['items']] == ['0100', '0200', '0300', '0400']
    assert cli('types', database)['bindings'][0]['type'] == 'WordArray'
    cli('rename', database, '0x1040', 'renamed_words')
    assert cli('typed-data', database, '0x1040')['items'][0]['path'] == 'renamed_words[0]'
    with Project(database) as project:
        assert project.regions(1)[0].data[0x40:0x48] == bytes.fromhex('0100020003000400')


def test_summary_and_signature_files_are_qualified_and_persistent(advanced_project, tmp_path):
    database, _ = advanced_project
    prototype = tmp_path / 'prototype.json'
    prototype.write_text(json.dumps(dict(arguments=[
        dict(name='dest', type='pointer', role='output'),
        dict(name='value', type='int', role='fill_byte'),
        dict(name='n', type='size_t', role='byte_count')], return_type='pointer')))
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps(dict(effects=[dict(access='write', pointer=dict(op='arg', name='dest'),
                                                  size=dict(op='arg', name='n'))])))
    registered = cli('set-summary', database, '0x1020', 'reviewed_fill', '--abi', 'x86_64_sysv',
                     '--prototype-file', prototype, '--summary-file', summary, '--author', 'cli-reviewer')
    assert registered['summary']['evidence_source'] == 'user_confirmed'
    assert registered['summary']['source']['author'] == 'cli-reviewer'
    stored = cli('summaries', database)['items'][0]
    assert stored['summary']['name'] == 'reviewed_fill'
    signature = tmp_path / 'signature.json'
    signature.write_text(json.dumps(dict(id='cli.fixture.fill', name='memset', arch='x86', bits=64,
                                        bytes='4989f84889d189f0fcf3aa4c89c0c3', abi='x86_64_sysv',
                                        source='authored CLI test helper')))
    assert cli('add-signature', database, signature)['signature']['id'] == 'cli.fixture.fill'
    catalog = cli('signatures', database)
    assert catalog['registered'][0]['id'] == 'cli.fixture.fill'
    assert len(catalog['builtin']) == 4
    assert cli('auto-analyze', database, '--abi', 'x86_64_sysv')['stable']
    effects = cli('call-effects', database, '--address', '0x1040', '--access', 'write', '--no-unresolved')
    assert effects['items'][0]['summary_name'] == 'reviewed_fill'


def test_advanced_json_requests_validate_inputs_and_stream_recovers(advanced_project):
    database, _ = advanced_project
    first = respond(dict(id='run', method='auto-analyze', params=dict(project=str(database), abi='x86_64_sysv')))
    assert first['ok'] and first['result']['stable']
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    requests = [dict(id=1, method='auto-analyze', params=dict(abi='unknown-abi')),
                dict(id=2, method='call-effects', params=dict(access='execute')),
                dict(id=3, method='function-analysis', params=dict(address='0x1000')),
                dict(id=4, method='advanced-status')]
    process = subprocess.run([sys.executable, '-m', 'fdisbull', 'serve', '--project', str(database)],
                             input=''.join(json.dumps(item) + '\n' for item in requests),
                             text=True, capture_output=True, env=env)
    assert process.returncode == 0, process.stderr
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    assert [item['id'] for item in replies] == [1, 2, 3, 4]
    assert [item['ok'] for item in replies] == [False, False, True, True]
    assert replies[2]['result']['state'] == 'done'


@pytest.mark.parametrize(('method', 'params'), [
    ('auto-analyze', dict(max_rounds=0)),
    ('function-membership', dict(max_work=True)),
    ('set-summary', dict(address='0x1020', name='unrecognized_identity')),
    ('add-signature', dict(signature=dict(id='bad', name='memcpy', bytes='c3'))),
])
def test_bad_advanced_json_is_a_structured_error(advanced_project, method, params):
    database, _ = advanced_project
    result = respond(dict(id=99, method=method, params=dict(project=str(database), **params)))
    assert result['id'] == 99 and not result['ok']
    assert result['error']['type'] == 'ValueError'


def test_advanced_flag_types_and_boolean_defaults():
    auto = vars(parser().parse_args(['auto-analyze', 'sample.fdb', '--start', '1000:0100',
                                    '--cs', '0x1000', '--ds', '0x4020', '--es', '0x4020', '--ss', '0x5000',
                                    '--version', '2', '--max-rounds', '3', '--abi', 'x86_16_cdecl_far']))
    assert (auto['cs'], auto['ds'], auto['es'], auto['ss'], auto['version']) == (0x1000, 0x4020, 0x4020, 0x5000, 2)
    assert auto['max_rounds'] == 3 and auto['abi'] == 'x86_16_cdecl_far'
    assert vars(parser().parse_args(['call-effects', 'sample.fdb']))['include_unresolved'] is True
    assert vars(parser().parse_args(['call-effects', 'sample.fdb', '--no-unresolved']))['include_unresolved'] is False


def test_invalid_signature_file_is_reported_as_json(advanced_project, tmp_path):
    database, _ = advanced_project
    invalid = tmp_path / 'invalid.json'
    invalid.write_text('{bad-json')
    error = cli('add-signature', database, invalid, expected_ok=False)
    assert error['type'] == 'JSONDecodeError'
