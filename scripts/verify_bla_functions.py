#!/usr/bin/env python3
"""Qualify pinned BLA exported functions under an explicit observer contract.

Actual targets and the materialized clean reference stay external. Structural
correspondence and finite runtime agreement are reported separately from full
state differences and from universal JavaScript equivalence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from verify_bla_patch_regions import SUPPORTED_COMMIT, SUPPORTED_L1, digest, encoded, read


ARCHIVE = 'challenge/archive/v6-tiered-protect/'
PINS = {
    'template': (ARCHIVE + 'clean/target.template.cjs',
                 '778817e12406de83c720ea66be64baa40b61e479f3e9ce5ee693c2bfd73d8fc0'),
    'L1': (ARCHIVE + 'artifacts/L1.cjs', SUPPORTED_L1),
    'L2': (ARCHIVE + 'artifacts/L2.cjs',
           '7ff91aa77246dbbe762da0d5e7ac5e3d05a01240d97d7bd25d15f79281909dde'),
    'L3': (ARCHIVE + 'artifacts/L3.cjs',
           '9b372c94a85dfaa441df54f4a793547749e12f7883bc1eab33b5af6f391fbdef'),
    'commitment': (ARCHIVE + 'commitment.json',
                   'ac55bf604a82e2623044021622035d64c4ac7df46d2aab996ed948a6ba433f34'),
}


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True, timeout=10).stdout.strip()


def campaign(root, babel_root):
    root, babel_root = root.resolve(strict=True), babel_root.resolve(strict=True)
    if git(root, 'rev-parse', 'HEAD') != SUPPORTED_COMMIT:
        raise ValueError('Unreviewed BLA source revision')
    remote = git(root, 'config', '--get', 'remote.origin.url')
    if remote.rstrip('/').removesuffix('.git') != 'https://github.com/qybaihe/bla':
        raise ValueError('Unexpected BLA repository identity')
    if git(root, 'status', '--porcelain', '--', *[item[0] for item in PINS.values()]):
        raise ValueError('Selected source differs from the owning checkout')
    files = {}
    for name, (relative, expected) in PINS.items():
        raw = read(root / relative)
        if digest(raw) != expected:
            raise ValueError('Selected source hash differs from reviewed artifact: ' + name)
        files[name] = raw
    commitment = json.loads(files['commitment'])
    for tier in ('L1', 'L2', 'L3'):
        if commitment['artifactSha256'][tier] != PINS[tier][1]:
            raise ValueError('Published commitment differs from target artifact')
    node = shutil.which('node')
    if node is None:
        raise ValueError('Node is required for the original-function campaign')
    scripts = Path(__file__).resolve().parent
    driver, analyzer = scripts / 'bla_function_runtime.cjs', scripts / 'bla_function_analysis.cjs'
    heap_prover = scripts / 'bla_shadow_heap_proof.cjs'
    noninterference_prover = scripts / 'bla_heap_noninterference.cjs'
    composer = scripts / 'bla_function_equivalence.cjs'
    config = {'root': str(root), 'babelRoot': str(babel_root),
              'template': {'path': PINS['template'][0], 'sha256': PINS['template'][1]},
              'targets': [{'tier': name, 'path': PINS[name][0], 'sha256': PINS[name][1]}
                          for name in ('L1', 'L2', 'L3')],
              'seedBases': [0, 4660],
              'commitment': {key: commitment[key] for key in ('keySha256', 'flagSha256')}}
    result = subprocess.run([node, '--max-old-space-size=256', str(driver)], input=encoded(config),
                            capture_output=True, timeout=60,
                            env={key: value for key, value in os.environ.items()
                                 if key not in ('NODE_OPTIONS', 'NODE_PATH')})
    if result.returncode:
        raise ValueError('Bounded original-function driver failed; no equivalence receipt produced')
    observation = json.loads(result.stdout)
    if (not isinstance(observation, dict) or not isinstance(observation.get('tiers'), list)
            or [item.get('tier') for item in observation['tiers']] != ['L1', 'L2', 'L3']):
        raise ValueError('Driver returned incomplete target coverage')
    for item in observation['tiers']:
        mutation = item.get('static', {}).get('mutation_summary', {})
        proof = mutation.get('proof', {})
        noninterference = mutation.get('noninterference', {})
        whole = item.get('static', {}).get('whole_function_equivalence', {})
        if (item.get('source_sha256') != PINS[item['tier']][1]
                or item.get('caller_observations_equal') is not True
                or item.get('private_heap_effects_equal_to_clean') is not False
                or type(item.get('actual_crypto_cases')) is not int or item['actual_crypto_cases'] < 1
                or type(item.get('modeled_call_cases')) is not int or item['modeled_call_cases'] < 1
                or item.get('static', {}).get('status') != 'structural_correspondence_under_assumptions'):
            raise ValueError('Driver did not qualify each pinned function observation contract')
        if (proof.get('status') != 'proved'
                or proof.get('source', {}).get('sha256') != PINS[item['tier']][1]
                or proof.get('source', {}).get('ast_identity_verified') is not True
                or not mutation.get('mutator_source_sha256')
                or proof.get('source', {}).get('mutator_sha256') != mutation['mutator_source_sha256']
                or proof.get('invariant', {}).get('initialized') is not True
                or proof.get('invariant', {}).get('preserved') is not True
                or proof.get('termination', {}).get('proved') is not True
                or mutation.get('totality_assumption') is not None
                or set(mutation.get('discharged_obligations', [])) != {
                    'shadow_heap_shape_preservation', 'shadow_heap_termination'}):
            raise ValueError('Shadow-heap preservation and termination were not proved for the pinned source')
        if (noninterference.get('status') != 'proved'
                or noninterference.get('source', {}).get('sha256') != PINS[item['tier']][1]
                or not proof.get('certificate_sha256')
                or noninterference.get('heap_certificate_sha256') != proof['certificate_sha256']
                or whole.get('status') != 'equivalent_under_contract'
                or not noninterference.get('certificate_sha256')
                or whole.get('noninterference_certificate_sha256') != noninterference['certificate_sha256']
                or whole.get('source', {}).get('target_sha256') != PINS[item['tier']][1]
                or whole.get('source', {}).get('template_sha256') != PINS['template'][1]
                or [function.get('role') for function in whole.get('functions', [])] != [
                    'sha256Hex', 'deriveFlagMask', 'decodeFlagCipher', 'tryUnlock']):
            raise ValueError('Noninterference and whole-function contracts were not composed for the pinned sources')
    analyzer_packages = {}
    for name in ('parser', 'traverse', 'generator'):
        package = babel_root / '@babel' / name
        metadata = json.loads(read(package / 'package.json'))
        entry = package / metadata.get('main', 'index.js')
        analyzer_packages['@babel/' + name] = {'version': metadata['version'],
            'package_sha256': digest(read(package / 'package.json')), 'entry_sha256': digest(read(entry))}
    report = {'format': 'fdisbull-bla-function-campaign-1',
              'status': 'proved_whole_function_contracts_with_runtime_observations',
              'source': {'repository': remote, 'commit': SUPPORTED_COMMIT,
                         'files': {name: {'path': PINS[name][0], 'bytes': len(raw), 'sha256': digest(raw)}
                                   for name, raw in files.items()}},
              'tool_sha256': {path.name: digest(path.read_bytes()) for path in
                              (Path(__file__), driver, analyzer, heap_prover, noninterference_prover, composer)},
              'runtime_limits': {'node_old_space_mib': 256, 'subprocess_timeout_seconds': 60},
              'analyzer_packages': analyzer_packages,
              'observations': observation,
              'claim_ceiling': 'Whole-function observational equivalence proved under explicit heap/guard/call contracts; unrestricted JavaScript contextual equivalence unproved',
              'shadow_heap_obligations': {
                  'shape_preservation': 'proved', 'termination': 'proved', 'noninterference': 'proved',
                  'basis': 'Source-checked inductive numeric-heap invariant, loop ranking and two-run public-state frame',
                  'scope': 'Admitted ordinary private heap and numeric deltas under standard JavaScript intrinsics'},
              'full_state_equivalence': False,
              'limitations': [
                  'Hardened functions mutate private shadow heaps absent from the clean reference.',
                  'Heap preservation and termination are proved within the admitted source/model; ordinary writable unaliased objects and stable intrinsics/prototypes remain boundary conditions.',
                  'Function source/name introspection, Error stacks, timing, resource exhaustion and hostile callbacks are excluded.',
                  'Controlled crypto-return scenarios are call-contract tests, not actual valid-key acceptance.',
                  'The clean template is materialized from commitment-checked target constants; it is not an independently built original.',
                  'The whole-function proof is relative to its stated observer/provider contract; finite runtime crosschecks remain separate.']}
    report['report_sha256'] = digest(encoded(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--babel-root', type=Path, required=True,
                        help='Existing trusted Babel node_modules root; no dependencies are downloaded')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = campaign(args.root, args.babel_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'report_sha256': report['report_sha256'],
                      'tiers': len(report['observations']['tiers']),
                      'claim_ceiling': report['claim_ceiling']}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('BLA function campaign failed; no new verified receipt', file=sys.stderr)
        raise SystemExit(2)
