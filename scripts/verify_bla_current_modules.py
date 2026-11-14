#!/usr/bin/env python3
"""Compare pinned current BLA v6/v7 originals with exact LASIK reductions.

Run storage admission before a new --prepare-output allocation. Existing
preparations are checked by replaying the static transforms in memory. Native
counterexamples and finite agreement never become a universal equivalence claim.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_bla_patch_regions import SUPPORTED_COMMIT, digest, encoded, read

SCRIPTS = Path(__file__).resolve().parent


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, timeout=10).stdout


def source_config(root, lasik_root):
    root, lasik_root = root.resolve(strict=True), lasik_root.resolve(strict=True)
    if git(root, 'rev-parse', 'HEAD').decode().strip() != SUPPORTED_COMMIT:
        raise ValueError('Unreviewed BLA revision')
    remote = git(root, 'config', '--get', 'remote.origin.url').decode().strip()
    if remote.rstrip('/').removesuffix('.git') != 'https://github.com/qybaihe/bla':
        raise ValueError('Unexpected source repository identity')
    if git(root, 'status', '--porcelain', '--', 'challenge/v6', 'challenge/v7'):
        raise ValueError('Current release inputs differ from owning checkout')
    editions, seals = [], {}
    for version in ('v6', 'v7'):
        seal_relative = f'challenge/{version}/SEAL.json'
        raw = read(root / seal_relative)
        if raw != git(root, 'show', f'{SUPPORTED_COMMIT}:{seal_relative}'):
            raise ValueError('Release seal differs from pinned Git object')
        seal = json.loads(raw)
        seals[version] = {'sha256': digest(raw), 'data': seal}
        source = root / 'challenge' / version / 'hardened'
        pins = []
        for file in sorted(source.rglob('*')):
            if file.is_symlink():
                raise ValueError('Symlink release entry')
            if not file.is_file():
                continue
            relative = file.relative_to(source).as_posix()
            payload = read(file)
            metadata = (seal.get('artifacts') or seal['files'])[relative]
            if (payload != git(root, 'show', f'{SUPPORTED_COMMIT}:challenge/{version}/hardened/{relative}')
                    or digest(payload) != metadata['sha256'] or len(payload) != metadata['bytes']):
                raise ValueError('Release artifact differs from seal or Git object')
            pins.append({'path': relative, 'bytes': len(payload), 'sha256': digest(payload)})
        editions.append({'edition': version, 'sourceRoot': str(source), 'pins': pins})
    return {'sourceCommit': SUPPORTED_COMMIT, 'editions': editions, 'lasikRoot': str(lasik_root)}, seals


def node_json(script, config, timeout=90):
    node = shutil.which('node')
    if node is None:
        raise ValueError('Node is required')
    result = subprocess.run([node, '--max-old-space-size=256', str(SCRIPTS / script)],
                            input=encoded(config), capture_output=True, timeout=timeout,
                            env={k: v for k, v in os.environ.items() if k not in ('NODE_OPTIONS', 'NODE_PATH')})
    if result.returncode:
        raise ValueError('Bounded current-module stage failed; retain existing evidence')
    return json.loads(result.stdout)


def public_entries(version):
    if version == 'v6':
        return [{'label': 'vault', 'path': 'vault.cjs'}]
    return [
        {'label': 'expr', 'path': 'core/expr.cjs', 'calls': [
            {'export': 'evaluate', 'inputClass': 'arithmetic', 'args': ['2+3*4']},
            {'export': 'evaluate', 'inputClass': 'variables', 'args': ['x*2+1', {'x': 7}]},
            {'export': 'evaluate', 'inputClass': 'invalid_expression', 'args': ['1+']},
            {'export': 'tokenize', 'inputClass': 'tokens', 'args': ['2+3*4']},
            {'export': 'format', 'inputClass': 'number', 'args': [14]}]},
        {'label': 'units', 'path': 'core/units.cjs', 'calls': [
            {'export': 'convert', 'inputClass': 'distance', 'args': [1, 'km', 'm']},
            {'export': 'dimensions', 'inputClass': 'dimension_list', 'args': []},
            {'export': 'catalog', 'inputClass': 'catalog', 'args': []}]},
        {'label': 'stats', 'path': 'core/stats.cjs', 'calls': [
            {'export': 'describe', 'inputClass': 'sample', 'args': [[4, 8, 15, 16, 23, 42]]},
            {'export': 'describe', 'inputClass': 'empty_sample', 'args': [[]]}]},
        {'label': 'license', 'path': 'core/license.cjs', 'calls': [
            {'export': 'activate', 'inputClass': 'valid_key'},
            {'export': 'activate', 'inputClass': 'single_character_mutation'},
            {'export': 'normalizeKey', 'inputClass': 'valid_key'},
            {'export': 'normalizeKey', 'inputClass': 'single_character_mutation'}]},
        {'label': 'cli', 'path': 'cli/meridian.cjs', 'calls': []},
    ]


def inline_script_hashes(tree):
    """Match the target host's inline-script selection; this is not a browser parser."""
    if not any(pin['path'] == 'panel.html' for pin in tree['pins']):
        return {}
    html = read(Path(tree['root']) / 'panel.html').decode('utf-8')
    selected = {}
    for match in re.finditer(r'<script(\s[^>]*)?>([\s\S]*?)</script>', html, re.IGNORECASE):
        attrs = match.group(1) or ''
        if (re.search(r'\bsrc\s*=', attrs) or
                re.search(r'''\btype\s*=\s*["']?(?!text/javascript|module|application/javascript)''', attrs, re.IGNORECASE)):
            continue
        selected[f'panel.html#script:{len(selected)}'] = digest(match.group(2).encode())
    return selected


def validate_result(result, prepared, seals):
    if (result.get('format') != 'fdisbull-bla-current-module-driver-1'
            or [e.get('edition') for e in result.get('editions', [])] != ['v6', 'v7']):
        raise ValueError('Incomplete current-edition coverage')
    for item, tree in zip(result['editions'], prepared['editions']):
        version, static, runtime = item['edition'], item.get('analysis', {}), item.get('runtime', {})
        if (static.get('status') != 'observational_equivalence_unproved'
                or static.get('source_execution') is not False
                or runtime.get('schema') != 'bla-current-native-module-comparison-1'
                or runtime.get('edition') != version or runtime.get('status') != 'finite_observations_differ'
                or runtime.get('original_real_acceptance_verified') is not True
                or runtime.get('reduced_real_acceptance_verified') is not (version == 'v6')
                or runtime.get('all_module_observations_equal') is not False
                or runtime.get('all_measured_cli_observations_equal') is not False
                or runtime.get('all_cli_observations_equal') is not (version == 'v6')
                or runtime.get('loader_sha256') != digest((SCRIPTS / 'bla_current_module_runtime.cjs').read_bytes())
                or any(runtime.get(key) is not False for key in (
                    'provider_substitutions', 'function_bodies_rewritten', 'filesystem_substitutions',
                    'target_observer_suffix', 'native_exit_replaced'))
                or runtime.get('witness', {}).get('key_sha256') != seals[version]['data']['keySha256']):
            raise ValueError('Native/source comparison failed its pinned counterexample boundary')
        observed_calls = {}
        for side in ('original', 'reduced'):
            expected = {x['path']: x['sha256'] for x in tree[side]['pins']}
            fragment_hashes = inline_script_hashes(tree[side])
            expected_modules = sorted([x for x in expected if x.endswith('.cjs')] + list(fragment_hashes))
            if sorted(x['module_path'] for x in static.get('modules', [])) != expected_modules:
                raise ValueError('Incomplete static module closure')
            for module in static.get('modules', []):
                name = module['module_path']
                if module[side]['source']['sha256'] != (expected.get(name) or fragment_hashes.get(name)):
                    raise ValueError('Static inventory source mismatch')
            observations = runtime.get(side, {})
            expected_labels = (['missing', 'empty', 'short', 'too_long', 'help', 'valid_key',
                                'single_character_mutation', 'honeypot_1', 'honeypot_2', 'honeypot_3']
                               if version == 'v6' else ['missing', 'help', 'version', 'calc', 'convert',
                                'units', 'stats', 'license_missing', 'license_bad_format', 'valid_key',
                                'single_character_mutation', 'license_extra_argument'])
            if [x.get('input_class') for x in observations.get('cli', [])] != expected_labels:
                raise ValueError('Incomplete CLI case coverage')
            measured_labels = ['missing', 'valid_key', 'single_character_mutation']
            if [x.get('input_class') for x in observations.get('measured_cli', [])] != measured_labels:
                raise ValueError('Incomplete measured CLI coverage')
            entries = public_entries(version)
            expected_module_rows = [(entry['label'], label) for entry in entries for label in
                                    (measured_labels if version == 'v6' else ['import_and_calls'])]
            if [(row.get('label'), row.get('input_class')) for row in observations.get('modules', [])] != expected_module_rows:
                raise ValueError('Incomplete native module coverage')
            cli_entry = 'vault.cjs' if version == 'v6' else 'cli/meridian.cjs'
            for mode, name in [('cli', 'cli'), ('measured_cli', 'observed_cli')]:
                if any(row.get('source_sha256') != expected[cli_entry] or row.get('mode') != name
                       for row in observations[mode]):
                    raise ValueError('CLI source entry mismatch')
            entry_paths = {entry['label']: entry['path'] for entry in entries}
            entry_calls = {entry['label']: [(call['export'], call['inputClass']) for call in entry.get('calls', [])]
                           for entry in entries}
            for row in observations['modules']:
                if row.get('source_sha256') != expected[entry_paths[row['label']]] or row.get('mode') != 'module':
                    raise ValueError('Native module source entry mismatch')
                exits = [control for control in row.get('controls', []) if control.get('phase') == 'native_exit_observed']
                if len(exits) != 1 or [(call.get('export'), call.get('input_class')) for call in exits[0].get('calls', [])] != entry_calls[row['label']]:
                    raise ValueError('Incomplete native public-call coverage')
                for call in exits[0].get('calls', []):
                    observed_calls[(side, row['label'], call['export'], call['input_class'])] = {
                        k: v for k, v in call.items() if k not in (
                            'global_descriptor_delta', 'process_event_listener_delta', 'exports_before', 'exports_after')}
            rows = observations.get('cli', []) + observations.get('measured_cli', []) + observations.get('modules', [])
            if not rows or any(row.get('completed') is not True or row.get('source_sha256') not in expected.values()
                               for row in rows):
                raise ValueError('Missing or stale native observations')
            valid = next(row for row in observations['cli'] if row['input_class'] == 'valid_key')
            mutation = next(row for row in observations['cli'] if row['input_class'] == 'single_character_mutation')
            accepts = side == 'original' or version == 'v6'
            if (valid['exit_status'] != (0 if accepts else 1)
                    or valid['output_commitment_matches'] is not accepts
                    or mutation['exit_status'] != 1 or mutation['output_commitment_matches'] is not False):
                raise ValueError('Real-key acceptance/rejection was not validated')
        context = runtime.get('observation_context', {})
        if (context.get('plain_cli', {}).get('exit_listener_installed') is not False
                or context.get('plain_cli', {}).get('global_descriptor_priming') is not False
                or context.get('measured_cli_and_modules', {}).get('exit_listener_installed') is not True
                or context.get('measured_cli_and_modules', {}).get('global_descriptor_priming') is not True):
            raise ValueError('Observer contexts are not distinguished')
        mismatches = [x['input_class'] for x in runtime['reduced']['cli'] if not x.get('equal_to_original')]
        if mismatches != ([] if version == 'v6' else ['valid_key']):
            raise ValueError('Unexpected plain CLI difference coverage')
        if version == 'v6':
            wasm = item.get('wasm', {})
            if (wasm.get('original', {}).get('source_sha256') != next(x['sha256'] for x in tree['original']['pins'] if x['path'] == 'core.wasm')
                    or wasm.get('reduced', {}).get('source_sha256') != next(x['sha256'] for x in tree['reduced']['pins'] if x['path'] == 'core.wasm')
                    or wasm['original']['export_count'] != 252 or wasm['reduced']['export_count'] != 2):
                raise ValueError('Wasm interface counterexample missing')
        elif len(static.get('changed_source_integrity_inputs', [])) != 10:
            raise ValueError('Changed source-byte dependency slice incomplete')
        if version == 'v7':
            api_rows = item.get('api_comparison', {}).get('rows', [])
            if ([(row['module'], row['export'], row['input_class']) for row in api_rows] != [
                    (entry['label'], call['export'], call['inputClass']) for entry in public_entries('v7') for call in entry['calls']]
                    or [(row['module'], row['export'], row['input_class']) for row in api_rows if not row['equal']] !=
                       [('license', 'activate', 'valid_key')]):
                raise ValueError('Incomplete or unexpected public API comparison')
            for row in api_rows:
                for side in ('original', 'reduced'):
                    if row.get(side) != observed_calls[(side, row['module'], row['export'], row['input_class'])]:
                        raise ValueError('API result projection differs from native observation')
                if row['equal'] is not (row['original'] == row['reduced']):
                    raise ValueError('API equality label differs from observed result')
            activation = next(row for row in api_rows if row['export'] == 'activate' and row['input_class'] == 'valid_key')
            if (activation['original'].get('result_kind') != 'return'
                    or activation['original'].get('accepted') is not True
                    or activation['original'].get('output_commitment_matches') is not True
                    or activation['reduced'].get('result_kind') != 'return'
                    or activation['reduced'].get('accepted') is not False
                    or activation['reduced'].get('output_commitment_matches') is not False):
                raise ValueError('Native API acceptance counterexample missing')


def campaign(root, lasik_root, prepared_path, key_files):
    config, seals = source_config(root, lasik_root)
    prepared = node_json('bla_current_module_prepare.cjs', {**config, 'manifestPath': str(prepared_path.resolve(strict=True))})
    if prepared.get('verification', {}).get('exact_reduction_replayed') is not True:
        raise ValueError('Exact static reduction replay missing')
    runtime_editions = []
    for item in prepared['editions']:
        version = item['edition']
        entries = public_entries(version)
        runtime_editions.append({'edition': version,
            'original': {**item['original'], 'moduleEntries': entries},
            'reduced': {**item['reduced'], 'moduleEntries': entries},
            'commitment': {'keySha256': seals[version]['data']['keySha256'],
                           'outputSha256': seals[version]['data'].get('flagSha256') or seals[version]['data']['certSha256']},
            'witnessPath': str(key_files[version].resolve(strict=True))})
    result = node_json('bla_current_module_campaign.cjs', {'editions': runtime_editions,
        'babelRoot': str(lasik_root.resolve(strict=True) / 'node_modules')}, timeout=120)
    validate_result(result, prepared, seals)
    # Recheck the prepared files and static transform after native execution.
    node_json('bla_current_module_prepare.cjs', {**config, 'manifestPath': str(prepared_path.resolve(strict=True))})
    report = {'format': 'fdisbull-bla-current-module-campaign-1',
              'status': 'verified_module_counterexamples_with_finite_native_comparison',
              'source_commit': SUPPORTED_COMMIT,
              'seal_sha256': {k: v['sha256'] for k, v in seals.items()},
              'preparation': prepared, 'comparison': result,
              'whole_module_equivalence': {'v6': False, 'v7': False},
              'tool_sha256': {name: digest((SCRIPTS / name).read_bytes()) for name in (
                  Path(__file__).name, 'bla_current_module_prepare.cjs', 'bla_current_module_campaign.cjs',
                  'bla_current_module_analysis.cjs', 'bla_current_module_runtime.cjs')},
              'limitations': [
                  'Static inventories and dependency slices are conservative, explicitly incomplete source evidence; no universal JavaScript equivalence proof.',
                  'Native CLI/export agreement is finite; initialization/reflective interfaces differ.',
                  'Measured runs install an explicit exit observer; plain CLI runs do not.',
                  'V7 reduced activation reads its own changed source files; no integrity rebinding or filesystem overlay is used.',
                  'Wasm export/custom-section reflection remains observable despite retained core host behavior.',
                  'The LASIK distribution is fingerprinted and transformations replayed, without claiming independent build provenance.',
                  'Keys, raw target source, returned flags/certificates and heap contents remain external.',
                  'No native Windows, hosted CI or full-repository qualification is inferred.']}
    report['report_sha256'] = digest(encoded(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--lasik-root', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepared', type=Path)
    group.add_argument('--prepare-output', type=Path)
    parser.add_argument('--v6-key-file', type=Path, required=True)
    parser.add_argument('--v7-key-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepared = args.prepared
    if args.prepare_output:
        config, _ = source_config(args.root, args.lasik_root)
        stage = node_json('bla_current_module_prepare.cjs', {**config, 'outputRoot': str(args.prepare_output.absolute())})
        prepared = Path(stage['manifest'])
    report = campaign(args.root, args.lasik_root, prepared, {'v6': args.v6_key_file, 'v7': args.v7_key_file})
    with args.output.open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'report_sha256': report['report_sha256'],
                      'whole_module_equivalence': report['whole_module_equivalence']}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        print('Current BLA module campaign failed; no new qualified receipt', file=sys.stderr)
        raise SystemExit(2)
