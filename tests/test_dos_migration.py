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
from scripts.dosbox_rpc_census import census


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
    # Full-source replay includes unchanged upstream diagnostics outside every
    # patch hunk. It validates declarations and dispatch, with pinned inputs.
    discovered = set(census(ROOT)['methods'])
    modules = {Path(inspect.getfile(cls)) for cls in DebugSession.__mro__ if cls is not object}
    modules.update(ROOT / ('src/fdisbull/' + name) for name in (
        'dosbox_rpc.py', 'debug_state.py', 'runtime_observations.py',
        'debug_wait.py', 'screenshot_codecs.py', 'runtime_code.py', 'keyboard_input.py',
        'frame_coherence.py', 'runtime_source_matching.py'))
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
                # No namespace allowlist: a new diagnostic family must not
                # disappear just because its prefix was absent historically.
                if re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+', method):
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


def test_diagnostic_rpc_consumers_remain_unqualified_until_dispositioned():
    output = migration_status(surface='debug.output.read')['rpc_methods'][0]
    diagnostic = migration_status(surface='debugger.execute_command')['rpc_methods'][0]
    assert output['qualification'] == diagnostic['qualification'] == 'unqualified'
    assert output['current_status'] == 'partial'
    assert 'debug-diagnostics' in output['native_route']
    assert 'not the DOSBox ordered diagnostic-record stream' in output['native_route']
    assert diagnostic['current_status'] == 'partial'
    assert diagnostic['legacy_contract']['allowed_commands'] == ['HELP', 'CPU', 'PIC']
    assert diagnostic['legacy_contract']['requires_stopped'] is True
    assert 'runtime_source_matching._descriptors' in diagnostic['consumers']
    assert output['disposition']['status'] == diagnostic['disposition']['status'] == 'open'
    assert migration_status()['default_switch_gate']['eligible'] is False


def test_work_plan_partitions_every_inventory_obligation_once():
    report = migration_status(details=True)
    plan = json.loads((ROOT / 'docs/DOS_QEMU_PARITY_WORK.json').read_text())
    rows = [r for key in ('rpc_methods', 'public_methods', 'extra_surfaces') for r in report[key]]
    identifiers = [r.get('method', r.get('id')) for r in rows]
    planned = [name for group in plan['work_groups'] for name in group['surface_ids']]
    assert len(planned) == len(set(planned))
    assert set(planned) == set(identifiers)
    assert {key: plan['coverage'][key] for key in report['inventory_counts']} == report['inventory_counts']
    assert plan['coverage']['total'] == len(rows) == 143
    assert report['inventory_counts']['rpc_methods'] == 37
    assert report['default_switch_gate']['unqualified_surfaces'] == len(rows)
    assert plan['policy']['qualified_surfaces_added'] == 0
    assert plan['policy']['qualified_campaigns_added'] == 0


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
