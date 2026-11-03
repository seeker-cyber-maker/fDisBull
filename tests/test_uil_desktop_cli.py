"""Desktop routing tests; native GUI/runtime qualification has separate gates."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from fdisbull.cli import METHODS, main, respond
from fdisbull.uil_api import invoke_common
from fdisbull.uil_desktop import load_desktop_json


NAMES = ('program', 'presentation', 'catalog', 'orchestration', 'plan', 'initial')
METHOD_NAMES = ('uil-desktop', 'uil-desktop-build', 'uil-desktop-seal')


@pytest.fixture
def desktop_stub(monkeypatch):
    calls = []
    module = ModuleType('fdisbull.uil_desktop')
    module.load_desktop_json = load_desktop_json
    def operation(name):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            return {'operation': name, 'function_index': 7, 'execution': False}
        return call
    for name in ('emit_desktop_shell', 'build_desktop_shell',
                 'compile_desktop_shell', 'seal_desktop_shell'):
        setattr(module, name, operation(name))
    monkeypatch.setitem(sys.modules, 'fdisbull.uil_desktop', module)
    return calls


def inputs(tmp_path):
    documents = dict(zip(NAMES, ({'functions': [0]}, {'values': [1]},
        {'groups': []}, {'bindings': []}, {'function_names': ['draw']}, [11, 22])))
    params = {**documents, 'output': str(tmp_path/'new-private-shell')}
    return documents, params


@pytest.mark.parametrize('source_only', [False, True])
def test_json_desktop_is_projectless_and_preserves_indexed_documents(tmp_path, desktop_stub, source_only):
    documents, params = inputs(tmp_path)
    variants = [{'name': 'c', 'label': 'C', 'arithmetic': 'portable-c'}]
    params.update(source_only=source_only, variants=variants, target='linux-x64')
    before = deepcopy(params)
    sentinel = tmp_path/'must-not-create.fdb'
    result = respond({'method': 'uil-desktop', 'params': params}, default_project=str(sentinel))
    assert result['ok'] and result['result']['function_index'] == 7
    assert params == before and not sentinel.exists()
    name, args, kwargs = desktop_stub[0]
    assert name == ('emit_desktop_shell' if source_only else 'build_desktop_shell')
    assert args == (*documents.values(), params['output'])
    assert kwargs['variants'] == variants and kwargs['target'] == 'linux-x64'
    assert 'project' not in kwargs


@pytest.mark.parametrize('method, expected', [
    ('uil-desktop-build', 'compile_desktop_shell'),
    ('uil-desktop-seal', 'seal_desktop_shell')])
def test_build_and_seal_are_projectless(tmp_path, desktop_stub, method, expected):
    output = str(tmp_path/'existing-private-shell')
    params = {'output': output}
    if method == 'uil-desktop-build': params['c_compiler'] = '/explicit/compiler'
    result = respond({'method': method, 'params': params},
                     default_project=str(tmp_path/'must-not-create.fdb'))
    assert result['ok']
    name, args, kwargs = desktop_stub[0]
    assert name == expected and args == (output,)
    assert kwargs == ({'c_compiler': '/explicit/compiler'} if method.endswith('build') else {})


def test_cli_desktop_reads_six_documents_and_variant_file(tmp_path, desktop_stub, capsys):
    documents, params = inputs(tmp_path)
    paths = []
    for name, document in documents.items():
        path = tmp_path/(name+'.json');path.write_text(json.dumps(document));paths.append(str(path))
    variants = [{'name': 'assembly', 'label': 'Assembly', 'arithmetic': 'native-asm'}]
    variant_path = tmp_path/'variants.json';variant_path.write_text(json.dumps(variants))
    assert main(['uil-desktop', *paths, params['output'], '--target', 'windows-x64',
                 '--source-only', '--variants', str(variant_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['function_index'] == 7
    assert desktop_stub[0] == ('emit_desktop_shell', (*documents.values(), params['output']),
                              {'target': 'windows-x64', 'variants': variants})


@pytest.mark.parametrize('period', [54.92549323064085, float('nan'), float('inf')])
def test_cli_plan_clock_allows_only_finite_fractional_host_values(tmp_path, desktop_stub, capsys, period):
    import math
    documents, params = inputs(tmp_path)
    documents['plan']['events'] = {'tick_ms': period}
    paths = []
    for name, document in documents.items():
        path = tmp_path/(name+'.json');path.write_text(json.dumps(document));paths.append(str(path))
    result = main(['uil-desktop', *paths, params['output'], '--source-only'])
    response = json.loads(capsys.readouterr().out)
    if math.isfinite(period):
        assert result == 0 and response['execution'] is False
        assert desktop_stub[0][1][4]['events']['tick_ms'] == period
    else:
        assert result == 1 and response['status'] == 'refused'
        assert 'finite' in response['error'] and not desktop_stub


def test_fractional_values_remain_forbidden_in_uil_documents(tmp_path, desktop_stub):
    _, params = inputs(tmp_path)
    path = tmp_path/'program.json';path.write_text('{"untrusted_value": 0.5}')
    params['program'] = str(path)
    reply = respond({'method': 'uil-desktop', 'params': params})
    assert not reply['ok'] and not desktop_stub


@pytest.mark.parametrize('method', ['uil-desktop-build', 'uil-desktop-seal'])
def test_cli_existing_shell_routes(tmp_path, desktop_stub, capsys, method):
    args = [method, str(tmp_path/'shell')]
    if method == 'uil-desktop-build': args += ['--c-compiler', '/explicit/compiler']
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['execution'] is False
    assert desktop_stub[0][0] == ('compile_desktop_shell' if method.endswith('build') else 'seal_desktop_shell')


@pytest.mark.parametrize('source_only', [1, 'yes', None])
def test_non_boolean_source_mode_refuses_before_emitter(tmp_path, desktop_stub, source_only):
    _, params = inputs(tmp_path);params['source_only'] = source_only
    reply = respond({'method': 'uil-desktop', 'params': params})
    assert not reply['ok'] and not desktop_stub


def test_source_only_does_not_silently_ignore_compiler(tmp_path, desktop_stub):
    _, params = inputs(tmp_path);params.update(source_only=True, c_compiler='/compiler')
    with pytest.raises(ValueError, match='source-only'):
        invoke_common('uil-desktop', params)
    assert not desktop_stub


@pytest.mark.parametrize('method', METHOD_NAMES)
def test_unknown_fields_refuse_before_any_operation(tmp_path, desktop_stub, method):
    _, params = inputs(tmp_path)
    if method != 'uil-desktop': params = {'output': params['output']}
    params['unexpected'] = True
    reply = respond({'method': method, 'params': params})
    assert not reply['ok'] and not desktop_stub


def test_real_method_catalog_and_cli_help_expose_desktop_routes():
    assert set(METHOD_NAMES) <= METHODS.keys()
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]/'src')}
    metadata = subprocess.run([sys.executable, '-m', 'fdisbull', 'methods'],
        env=env, capture_output=True, text=True, timeout=20)
    assert metadata.returncode == 0, metadata.stderr
    for method in METHOD_NAMES:
        assert method in json.dumps(json.loads(metadata.stdout))
        help_result = subprocess.run([sys.executable, '-m', 'fdisbull', method, '--help'],
            env=env, capture_output=True, text=True, timeout=20)
        assert help_result.returncode == 0, help_result.stdout+help_result.stderr
    assert 'source-only' in METHODS['uil-desktop'] or 'source_only' in METHODS['uil-desktop']
