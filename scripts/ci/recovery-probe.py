#!/usr/bin/env python3
"""Exercise a real, isolated CI input/source failure without native rebuilds."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re


def source_check():
    path = Path(__file__).with_name('recovery_probe_logic.py')
    spec = importlib.util.spec_from_file_location('recovery_probe_logic', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = [({}, False), ({'complete': False, 'errors': []}, False),
             ({'complete': True, 'errors': []}, True),
             ({'complete': True, 'errors': ['missing-frame']}, False),
             ({'complete': 'yes', 'errors': []}, False)]
    values = [{'observation': observation, 'expected': expected,
               'actual': module.capture_ready(observation)}
              for observation, expected in cases]
    return {'kind': 'source', 'reason': 'incomplete_capture_accepted',
            'source_file': 'scripts/ci/recovery_probe_logic.py', 'cases': values,
            'passed': all(case['actual'] is case['expected'] for case in values)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-check', action='store_true')
    args = parser.parse_args()
    if args.source_check:
        result = source_check()
        print(json.dumps(result, sort_keys=True))
        return 0 if result['passed'] else 1
    incident = os.environ['FDISBULL_RECOVERY_INCIDENT']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', incident):
        raise ValueError('Invalid rehearsal identity')
    expected = os.environ['FDISBULL_RECOVERY_INPUT_SHA256']
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid owned-input identity')
    path = Path('/ci-host-results/recovery-inputs') / incident / 'ready.json'
    output = Path('artifacts/recovery')
    output.mkdir(parents=True, exist_ok=True)
    result = {'source_commit': os.environ['CI_COMMIT_SHA'],
              'incident_id': incident, 'profile': 'ci-recovery-rehearsal'}
    if path.is_symlink():
        result.update(kind='blocked', reason='owned_input_identity_mismatch')
        code = 79
    elif not path.exists():
        result.update(kind='infrastructure', reason='missing_ci_owned_input',
                      input_sha256=expected)
        code = 78
    elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        result.update(kind='blocked', reason='owned_input_identity_mismatch')
        code = 79
    else:
        result.update(source_check(), input_sha256=expected)
        code = 0 if result['passed'] else 1
    name = 'result.json' if code == 0 else 'diagnostic.json'
    with (output / name).open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
