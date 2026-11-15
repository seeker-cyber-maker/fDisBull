"""Incomplete or relabeled evidence cannot qualify a current-module campaign."""
import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def receipts(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('current_campaign_test', scripts / 'verify_bla_current_modules.py')
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    prepared, seals = {'editions': []}, {}
    result = {'format': 'fdisbull-bla-current-module-driver-1', 'editions': []}
    for version in ('v6', 'v7'):
        entries = runner.public_entries(version)
        names = [entry['path'] for entry in entries]
        if version == 'v6': names += ['panel.html', 'core.wasm']
        trees = {}
        for side in ('original', 'reduced'):
            root = tmp_path / version / side; root.mkdir(parents=True)
            pins = []
            for name in names:
                raw = b'<script>void 0;</script>' if name == 'panel.html' else (version + side + name).encode()
                if name == 'panel.html': (root / name).write_bytes(raw)
                pins.append({'path': name, 'sha256': runner.digest(raw), 'bytes': len(raw)})
            trees[side] = {'root': str(root), 'pins': pins}
        prepared['editions'].append({'edition': version, **trees})
        seals[version] = {'data': {'keySha256': runner.digest(version.encode())}}
        static_modules = []
        for name in sorted([name for name in names if name.endswith('.cjs')] +
                           (['panel.html#script:0'] if version == 'v6' else [])):
            sides = {}
            for side in ('original', 'reduced'):
                hashes = {x['path']: x['sha256'] for x in trees[side]['pins']}
                hashes.update(runner.inline_script_hashes(trees[side]))
                sides[side] = {'source': {'sha256': hashes[name]}}
            static_modules.append({'module_path': name, **sides})
        static = {'status': 'observational_equivalence_unproved', 'source_execution': False,
                  'modules': static_modules, 'changed_source_integrity_inputs': [{} for _ in range(10)]}
        runtime = {'schema': 'bla-current-native-module-comparison-1', 'edition': version,
                   'status': 'finite_observations_differ', 'original_real_acceptance_verified': True,
                   'reduced_real_acceptance_verified': version == 'v6',
                   'all_module_observations_equal': False, 'all_measured_cli_observations_equal': False,
                   'all_cli_observations_equal': version == 'v6',
                   'loader_sha256': runner.digest((scripts / 'bla_current_module_runtime.cjs').read_bytes()),
                   'witness': {'key_sha256': seals[version]['data']['keySha256']},
                   'observation_context': {'plain_cli': {'exit_listener_installed': False, 'global_descriptor_priming': False},
                     'measured_cli_and_modules': {'exit_listener_installed': True, 'global_descriptor_priming': True}},
                   **{key: False for key in ('provider_substitutions', 'function_bodies_rewritten',
                      'filesystem_substitutions', 'target_observer_suffix', 'native_exit_replaced')}}
        cli_labels = (['missing', 'empty', 'short', 'too_long', 'help', 'valid_key', 'single_character_mutation',
                       'honeypot_1', 'honeypot_2', 'honeypot_3'] if version == 'v6' else
                      ['missing', 'help', 'version', 'calc', 'convert', 'units', 'stats', 'license_missing',
                       'license_bad_format', 'valid_key', 'single_character_mutation', 'license_extra_argument'])
        api_rows = []
        for side in ('original', 'reduced'):
            hashes = {x['path']: x['sha256'] for x in trees[side]['pins']}
            cli_entry = 'vault.cjs' if version == 'v6' else 'cli/meridian.cjs'
            def row(label, mode, source):
                accepted = label == 'valid_key' and (side == 'original' or version == 'v6')
                return {'input_class': label, 'mode': mode, 'source_sha256': source, 'completed': True,
                        'exit_status': 0 if accepted else 1, 'output_commitment_matches': accepted,
                        'equal_to_original': not (version == 'v7' and label == 'valid_key')}
            native_modules = []
            for entry in entries:
                calls = []
                for call in entry.get('calls', []):
                    valid = entry['label'] == 'license' and call['export'] == 'activate' and call['inputClass'] == 'valid_key'
                    projection = {'export': call['export'], 'input_class': call['inputClass'], 'result_kind': 'return',
                                  'accepted': valid and side == 'original', 'output_commitment_matches': valid and side == 'original'}
                    calls.append({**projection, 'exports_before': {}, 'exports_after': {},
                                  'global_descriptor_delta': [], 'process_event_listener_delta': []})
                    if side == 'original':
                        api_rows.append({'module': entry['label'], 'export': call['export'], 'input_class': call['inputClass'],
                                         'original': projection, 'equal': not valid})
                    else:
                        api_rows[len([x for x in api_rows if 'reduced' in x])]['reduced'] = projection
                for label in (['missing', 'valid_key', 'single_character_mutation'] if version == 'v6' else ['import_and_calls']):
                    native_modules.append({'label': entry['label'], **row(label, 'module', hashes[entry['path']]),
                        'controls': [{'phase': 'native_exit_observed', 'calls': copy.deepcopy(calls)}]})
            runtime[side] = {'cli': [row(label, 'cli', hashes[cli_entry]) for label in cli_labels],
                             'measured_cli': [row(label, 'observed_cli', hashes[cli_entry]) for label in
                                              ['missing', 'valid_key', 'single_character_mutation']],
                             'modules': native_modules}
        item = {'edition': version, 'analysis': static, 'runtime': runtime, 'api_comparison': {'rows': api_rows}}
        if version == 'v6':
            item['wasm'] = {side: {'source_sha256': next(x['sha256'] for x in trees[side]['pins'] if x['path'] == 'core.wasm'),
                                  'export_count': 252 if side == 'original' else 2} for side in trees}
        result['editions'].append(item)
    return runner, result, prepared, seals


def test_complete_counterexamples_remain_different_and_native_coverage_complete(receipts):
    runner, result, prepared, seals = receipts
    runner.validate_result(result, prepared, seals)


@pytest.mark.parametrize('defect', ['drop_cli', 'drop_measured', 'drop_module', 'drop_call', 'entry_swap',
    'drop_static', 'fragment_hash', 'promote_module', 'promote_reduced', 'missing_output', 'wrong_key',
    'missing_slice', 'wasm_surface', 'api_projection', 'api_equality', 'filesystem_overlay',
    'plain_observer', 'unknown_static', 'incomplete_native', 'duplicate_api_input'])
def test_stale_incomplete_or_promoted_receipts_fail_closed(receipts, defect):
    runner, result, prepared, seals = receipts
    v6, v7 = result['editions']; runtime = v7['runtime']
    if defect == 'drop_cli': runtime['original']['cli'].pop()
    elif defect == 'drop_measured': runtime['reduced']['measured_cli'].pop()
    elif defect == 'drop_module': runtime['original']['modules'].pop()
    elif defect == 'drop_call': runtime['original']['modules'][0]['controls'][0]['calls'].pop()
    elif defect == 'entry_swap': runtime['original']['cli'][0]['source_sha256'] = runtime['original']['modules'][0]['source_sha256']
    elif defect == 'drop_static': v7['analysis']['modules'].pop()
    elif defect == 'fragment_hash': v6['analysis']['modules'][0]['original']['source']['sha256'] = '0' * 64
    elif defect == 'promote_module': runtime['all_module_observations_equal'] = True
    elif defect == 'promote_reduced': runtime['reduced_real_acceptance_verified'] = True
    elif defect == 'missing_output': runtime['original']['cli'][9]['output_commitment_matches'] = False
    elif defect == 'wrong_key': runtime['witness']['key_sha256'] = '0' * 64
    elif defect == 'missing_slice': v7['analysis']['changed_source_integrity_inputs'].pop()
    elif defect == 'wasm_surface': v6['wasm']['reduced']['export_count'] = 252
    elif defect == 'api_projection': v7['api_comparison']['rows'][0]['original']['result_kind'] = 'throw'
    elif defect == 'api_equality': v7['api_comparison']['rows'][-4]['equal'] = True
    elif defect == 'filesystem_overlay': runtime['filesystem_substitutions'] = True
    elif defect == 'plain_observer': runtime['observation_context']['plain_cli']['exit_listener_installed'] = True
    elif defect == 'unknown_static': v7['analysis']['status'] = 'unknown'
    elif defect == 'incomplete_native': runtime['original']['cli'][0]['completed'] = False
    elif defect == 'duplicate_api_input': v7['api_comparison']['rows'][-2] = copy.deepcopy(v7['api_comparison']['rows'][-1])
    with pytest.raises(ValueError):
        runner.validate_result(result, prepared, seals)
