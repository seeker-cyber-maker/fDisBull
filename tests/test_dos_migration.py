"""A new DOS capability cannot silently vanish from the migration ledger."""
import ast
import inspect
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from fdisbull.cli import main, respond
from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.dos_migration import migration_status


ROOT = Path(__file__).resolve().parents[1]


def public_dos_routes():
    tree = ast.parse(inspect.getsource(DebugWorkspace))
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                    and key.value.startswith('debug-') and isinstance(value, ast.Constant)
                    and isinstance(value.value, str) and hasattr(DebugSession, value.value)):
                found[key.value] = value.value
    return found


def test_every_public_dos_route_is_classified_once():
    report = migration_status(details=True)
    actual = public_dos_routes()
    declared = report['public_methods']
    assert len({row['method'] for row in declared}) == len(declared)
    assert {row['method']: row['operation'] for row in declared} == actual
    assert len(declared) >= 83
    # Refusing routes are intentional compatibility behavior, not missing ports.
    for row in declared:
        if row['method'] in ('debug-write-memory', 'debug-write-registers'):
            assert row['legacy_status'] == 'explicitly_refused'


def test_native_protocol_and_host_consumers_have_no_unclassified_dos_methods():
    report = migration_status(details=True)
    declared = {row['method'] for row in report['rpc_methods']}
    assert len(declared) == len(report['rpc_methods'])
    discovered = set()
    # Inspect the supplied native source patches, including layer-only commands.
    for path in (ROOT / 'experimental/dosbox-x/headless-agent.patch',
                 ROOT / 'experimental/dosbox-x/layers/headless-agent.patch'):
        text = '\n'.join(line for line in path.read_text().splitlines() if not line.startswith('-'))
        discovered.update(re.findall(r'\bmethod\s*==\s*"([a-z][a-z_.]+)"', text))
    modules = {Path(inspect.getfile(cls)) for cls in DebugSession.__mro__ if cls is not object}
    modules.update(ROOT / ('src/fdisbull/' + name) for name in (
        'dosbox_rpc.py', 'debug_state.py', 'runtime_observations.py',
        'debug_wait.py', 'screenshot_codecs.py', 'runtime_code.py', 'keyboard_input.py', 'frame_coherence.py'))
    for path in modules:
        if not path.is_file():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('call', '_keyboard_call') and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                method = node.args[0].value
                if node.func.attr == '_keyboard_call':
                    method = 'input.keyboard.' + method
                if re.fullmatch(r'(agent|session|execution|state|memory|breakpoints|trace|video|input|frame|layers)\.[a-z_.]+', method):
                    discovered.add(method)
    assert discovered == declared


def test_slices_are_dependency_ordered_and_witnesses_exist():
    report = migration_status(details=True)
    seen = set()
    for item in report['slices']:
        assert item['id'] not in seen
        assert set(item['depends_on']) <= seen
        assert item['gate']
        for path in item['witness_tests']:
            assert (ROOT / path).is_file(), path
        seen.add(item['id'])
    for key in ('rpc_methods', 'public_methods', 'extra_surfaces'):
        assert all(row['slice'] in seen for row in report[key])


def test_unqualified_slices_keep_default_and_fallback_policy_explicit():
    report = migration_status()
    assert report['native_backend'] == 'qemu-dos'
    assert report['default_backend'] == 'dosbox'
    assert report['retained_fallback_backends'] == ['dosbox', 'dosbox-qemu']
    assert report['automatic_runtime_fallback'] is False
    assert report['dosbox_removal_permitted'] is False
    assert report['default_switch_gate']['eligible'] is False
    assert report['default_switch_gate']['unqualified_surfaces'] > 0
    assert report['runtime_validation'] == 'not_run'
    assert 'public_methods' not in report  # The ordinary summary stays compact.
    report['default_backend'] = 'accidental-caller-mutation'
    assert migration_status()['default_backend'] == 'dosbox'


def test_catalog_is_projectless_and_filterable(tmp_path, capsys):
    assert main(['dos-migration', '--surface', 'debug-layer-enable']) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply['ok']
    assert reply['result']['public_methods'][0]['slice'] == 'layers-hooks'
    reply = respond({'method': 'dos-migration', 'params': {'slice': 'checkpoints'}},
                    default_project=str(tmp_path / 'does-not-exist.fdb'))
    assert reply['ok']
    assert {row['slice'] for row in reply['result']['public_methods']} == {'checkpoints'}
    for options in ({'surface': 'missing'}, {'slice': 'missing'}, {'details': 1}):
        with pytest.raises(ValueError):
            migration_status(**options)


def test_missing_operation_reports_slice_without_fallback(tmp_path):
    workspace = DebugWorkspace()
    path = (tmp_path / 'project.fdb').resolve()
    workspace.sessions['one'] = SimpleNamespace(project=SimpleNamespace(path=path),
        metadata={'backend': 'qemu-dos'})
    with pytest.raises(ValueError, match='slice=layers-hooks.*No fallback was launched'):
        workspace.invoke('debug-layer-enable', path, {'run': 'one', 'layer': 'test'})
