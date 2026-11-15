#!/usr/bin/env python3
"""Recheck pinned BLA core contracts, module effects and native CLI observations.

An observed initialization difference is retained as a counterexample. A missing
commitment-matching external key never becomes an acceptance claim.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from verify_bla_functions import PINS, campaign as function_campaign
from verify_bla_patch_regions import digest, encoded, read


def campaign(root, babel_root, witness_path=None):
    root, babel_root = root.resolve(strict=True), babel_root.resolve(strict=True)
    # The owning campaign checks revision, clean selected paths, commitments,
    # providers and independently recomputed core proof chains before execution.
    functions = function_campaign(root, babel_root)
    commitment = json.loads(read(root / PINS['commitment'][0]))
    scripts = Path(__file__).resolve().parent
    driver = scripts / 'bla_module_campaign.cjs'
    node = shutil.which('node')
    if node is None:
        raise ValueError('Node is required for native module observations')
    config = {'root': str(root), 'babelRoot': str(babel_root),
              'template': {'path': PINS['template'][0], 'sha256': PINS['template'][1]},
              'targets': [{'tier': tier, 'path': PINS[tier][0], 'sha256': PINS[tier][1]}
                          for tier in ('L1', 'L2', 'L3')],
              'commitment': {key: commitment[key] for key in ('keySha256', 'flagSha256')},
              'witnessPath': str(witness_path.resolve(strict=True)) if witness_path else None}
    result = subprocess.run([node, '--max-old-space-size=256', str(driver)], input=encoded(config),
                            capture_output=True, timeout=60,
                            env={key: value for key, value in os.environ.items()
                                 if key not in ('NODE_OPTIONS', 'NODE_PATH')})
    if result.returncode:
        raise ValueError('Bounded original-module driver failed; no verified receipt')
    modules = json.loads(result.stdout)
    validate_modules(modules, functions)
    report = {'format': 'fdisbull-bla-module-campaign-1',
              'status': 'initialization_difference_with_cli_contract_and_native_observations',
              'source': functions['source'],
              'function_campaign': functions,
              'modules': modules,
              'tool_sha256': {path.name: digest(path.read_bytes()) for path in
                              (Path(__file__), driver, scripts / 'bla_module_equivalence.cjs',
                               scripts / 'bla_module_runtime.cjs')},
              'whole_module_equivalence': False,
              'claim_ceiling': 'Original require initialization differs; CLI equivalence is conditional on the checked source and host contracts; real acceptance requires an external commitment-matching key',
              'limitations': [
                  'Whole-module equivalence is false for a global-property or event-registration observer.',
                  'CLI source congruence and finite native CLI observations are separate evidence.',
                  'A missing valid-key witness leaves actual acceptance unverified; modeled provider success never discharges it.',
                  'The clean reference is materialized from target constants, not an independently built release.',
                  'Stable intrinsic/provider/clock/console/exit semantics and the explicit observer contracts remain assumptions.',
                  'No native Windows, whole-repository or hosted CI qualification is inferred.']}
    report['report_sha256'] = digest(encoded(report))
    return report


def validate_modules(modules, functions):
    """Reject incomplete target coverage and stale proof/runtime identities."""
    if (not isinstance(modules, dict)
            or modules.get('format') != 'fdisbull-bla-module-driver-1'
            or modules.get('template_sha256') != PINS['template'][1]
            or [item.get('tier') for item in modules.get('proofs', [])] != ['L1', 'L2', 'L3']):
        raise ValueError('Module driver returned incomplete source coverage')
    for item in modules['proofs']:
        proof = item.get('proof', {})
        core = next(row['static'] for row in functions['observations']['tiers']
                    if row['tier'] == item['tier'])
        if (proof.get('status') != 'different'
                or proof.get('source', {}).get('target_sha256') != PINS[item['tier']][1]
                or proof.get('source', {}).get('template_sha256') != PINS['template'][1]
                or proof.get('initialization', {}).get('status') != 'different'
                or proof.get('cli', {}).get('status') != 'equivalent_under_contract'
                or proof.get('selected_function_equivalence', {}).get('certificate_sha256') !=
                   core['whole_function_equivalence']['certificate_sha256']
                or proof.get('cli', {}).get('initialization_prefix', {}).get('seed_certificate_sha256') !=
                   core['seed_invariant_proof']['certificate_sha256']
                or proof.get('cli', {}).get('initialization_prefix', {}).get('heap_certificate_sha256') !=
                   core['mutation_summary']['proof']['certificate_sha256']
                or proof.get('initialization', {}).get('all_executed_initializers_classified') is not True
                or proof.get('cli', {}).get('termination', {}).get('post_dispatch_initializers_unreachable') is not True
                or not proof.get('certificate_sha256')):
            raise ValueError('Module difference and CLI contracts were not source-qualified')
    # Runtime receipt validation is below the static proof boundary: observations
    # cannot upgrade a false whole-module relation or an absent key witness.
    validate_runtime(modules, functions)


def validate_runtime(modules, functions):
    runtime = modules.get('runtime', {})
    witness = runtime.get('witness', {})
    missing = witness.get('status') == 'missing'
    acceptance = witness.get('status') == 'verified_against_real_native_implementations'
    expected_status = ('verified_finite_rejections_real_acceptance_pending' if missing else
                       'verified_finite_native_acceptance_and_rejection_observations')
    provider_runtime = functions['observations']['provider_validation']['runtime']
    expected_labels = ['missing', 'empty', 'short', 'min_length_wrong_key',
                       'max_length_wrong_key', 'too_long', 'unicode_wrong_key',
                       'honeypot', 'ordinary_wrong_key']
    if acceptance:
        expected_labels += ['valid_key', 'valid_key_extra_argument', 'single_character_mutation']
    if (runtime.get('schema') != 'bla-native-module-cli-v1'
            or not (missing or acceptance) or runtime.get('status') != expected_status
            or witness.get('real_valid_key_verified') is not acceptance
            or runtime.get('real_valid_key_acceptance_verified') is not acceptance
            or runtime.get('reference_source_sha256') != modules.get('reference_sha256')
            or not modules.get('reference_sha256')
            or runtime.get('loader_sha256') != digest((Path(__file__).parent / 'bla_module_runtime.cjs').read_bytes())
            or any(runtime.get('runtime', {}).get(key) != provider_runtime.get(key)
                   for key in ('node', 'openssl', 'fips', 'executable_sha256'))
            or runtime.get('provider_substitutions') is not False
            or runtime.get('function_bodies_rewritten') is not False
            or runtime.get('target_observer_suffix') is not False
            or runtime.get('rejection_paths_verified') is not True
            or runtime.get('all_cli_observations_equal') is not True
            or runtime.get('all_module_observations_equal') is not False
            or runtime.get('cases_per_cli') != len(expected_labels)
            or [row.get('tier') for row in runtime.get('targets', [])] != ['L1', 'L2', 'L3']):
        raise ValueError('Native module/CLI evidence is incomplete or stale')
    reference = runtime.get('reference', {})
    if reference.get('module', {}).get('observation', {}).get('source_sha256') != modules['reference_sha256']:
        raise ValueError('Native reference initialization is unqualified')
    for index, row in enumerate([reference, *runtime['targets']]):
        cli = row.get('cli', [])
        module = row.get('module', {})
        observations = module.get('observation', {}).get('rows', [])
        if (row.get('rejection_paths_verified') is not True
                or row.get('real_valid_key_acceptance_verified') is not acceptance
                or [case.get('input_class') for case in cli] != expected_labels
                or [case.get('input_class') for case in observations] != expected_labels
                or module.get('exit_status') != 0 or module.get('stdout_bytes') != 0
                or module.get('stderr_bytes') != 0):
            raise ValueError('Native module/CLI case coverage is incomplete')
        for case, result in zip(cli, observations):
            valid = case['input_class'] in ('valid_key', 'valid_key_extra_argument')
            if (case.get('native_cli_dispatch_returned') is not False
                    or case.get('exit_status') != (0 if valid else 1)
                    or case.get('flag_commitment_matches') is not valid
                    or result.get('result_kind') != 'return'
                    or result.get('result_type') != ('string' if valid else 'null')
                    or result.get('flag_commitment_matches') is not valid
                    or (valid and case.get('stderr_bytes') != 0)
                    or (index and case.get('equal_to_reference') is not True)):
                raise ValueError('Native acceptance/rejection classification failed')
        if not index:
            continue
        proof = modules['proofs'][index - 1]['proof']
        effects = proof['initialization'].get('global_effects', [])
        delta = module.get('observation', {}).get('initialization_global_descriptor_delta', [])
        matching = [change for change in delta if len(effects) == 1 and
                    change.get('key', {}).get('name_sha256') == effects[0].get('property_name_sha256')]
        reference_delta = reference['module']['observation'].get('initialization_global_descriptor_delta', [])
        if (row.get('source_sha256') != PINS[row['tier']][1]
                or module.get('observation', {}).get('source_sha256') != PINS[row['tier']][1]
                or row.get('function_results_equal') is not True
                or row.get('cli_observations_equal') is not True
                or row.get('module_observations_equal') is not False
                or row.get('initialization_global_effects_equal') is not False
                or row.get('export_reflection_equal') is not False
                or len(effects) != 1 or len(matching) != 1
                or any(change.get('key') == matching[0].get('key') for change in reference_delta)
                or matching[0].get('change') != 'added'
                or matching[0].get('after', {}).get('kind') != 'accessor'
                or matching[0].get('after', {}).get('enumerable') is not False
                or matching[0].get('after', {}).get('configurable') is not True
                or not matching[0].get('after', {}).get('get')):
            raise ValueError('Native initialization counterexample is missing or disagrees with source proof')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--babel-root', type=Path, required=True)
    parser.add_argument('--valid-key-file', type=Path,
                        help='Private external UTF-8 key witness; no key is emitted')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = campaign(args.root, args.babel_root, args.valid_key_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'report_sha256': report['report_sha256'],
                      'whole_module_equivalence': False, 'claim_ceiling': report['claim_ceiling']}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('BLA module campaign failed; no new verified receipt', file=sys.stderr)
        raise SystemExit(2)
