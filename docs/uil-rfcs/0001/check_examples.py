"""RFC experiment: four backings for one synthetic intent, not a UIL compiler."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reference_il', HERE.parents[2] / 'src/fdisbull/interaction_il.py')
il = importlib.util.module_from_spec(spec); spec.loader.exec_module(il)
KEYS = ('cash', 'working', 'stock', 'pending', 'expense')


class FixtureValidationError(ValueError):
    """Raised when a fixture result violates the RFC example contract."""


def require(condition, message):
    """Keep fixture validation active under ``python -O``."""
    if not condition:
        raise FixtureValidationError(message)


def admitted(case):
    if set(case) != {'state', 'ready'} or type(case['ready']) is not bool:
        raise ValueError('invalid input fields')
    values = case['state']
    if (not isinstance(values, list) or len(values) != 5 or
        any(not isinstance(v, str) or not re.fullmatch(r'0|[1-9][0-9]*', v) or int(v) > 0xffffffff for v in values)):
        raise ValueError('invalid u32 decimal strings')
    cash, working, stock, pending, _ = map(int, values)
    return case['ready'] and cash - working == 500 and pending - stock == 20


def program(values, ready):
    return {'format': 'fdisbull-il-1', 'role': 'udl',
        'variables': {**{'$' + k: {'type': 'u32', 'initial': int(v)} for k, v in zip(KEYS, values)},
                      '$ready': {'type': 'bool', 'initial': ready}},
        'resources': {k: {'kind': 'text', 'text': k} for k in ('stock', 'expense', 'cash')},
        'body': [
            {'id': 'qualify', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$ready'}, 'right': True}},
            {'id': 'copy-stock', 'op': 'set', 'var': '$stock', 'value': {'var': '$pending'}},
            {'id': 'stock-event', 'op': 'text', 'resource': 'stock'},
            {'id': 'post-expense', 'op': 'add', 'var': '$expense', 'value': 500},
            {'id': 'expense-event', 'op': 'text', 'resource': 'expense'},
            {'id': 'commit-cash', 'op': 'set', 'var': '$cash', 'value': {'var': '$working'}},
            {'id': 'cash-event', 'op': 'text', 'resource': 'cash'}]}


def pass_through(doc):
    """No UDL→UIL conversion. Existing IL is already executable in this profile."""
    result = il.execute_il(doc)
    encode = lambda s: {k: str(s['$' + k]) for k in KEYS}
    checkpoints = []
    if result['complete']:
        # Evaluate prefixes on independent initial copies; no host mutation.
        for length in (3, 5, 7):
            prefix = deepcopy(doc); prefix['body'] = prefix['body'][:length]
            checkpoints.append(encode(il.execute_il(prefix)['state']))
    return {'status': result['status'], 'state': encode(result['state']),
            'events': [e['resource'] for e in result['events']], 'checkpoints': checkpoints}


def run(command):
    return subprocess.run(command, capture_output=True, text=True, check=True, timeout=30).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True, help='new private output directory outside Git')
    args = ap.parse_args()
    output = args.output.resolve()
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        ap.error('output must be new and outside Git')
    rustc, node = shutil.which('rustc'), shutil.which('node')
    if not rustc or not node:
        ap.error('existing rustc and node are required; no tools are installed')
    output.mkdir(parents=True)
    executable = output / 'synthetic-commit'
    run([rustc, '--edition=2021', str(HERE / 'commit.rs'), '-o', str(executable)])
    vectors = json.loads((HERE / 'vectors.json').read_text())
    results = []
    for c in vectors['cases']:
        ready = admitted({k: c[k] for k in ('state', 'ready')})
        doc = program(c['state'], ready)
        expected = {'status': c['status'], 'state': dict(zip(KEYS, c['after'])),
            'events': vectors['ordered_effects'] if c['status'] == 'complete' else [],
            'checkpoints': [dict(zip(KEYS, s)) for s in c['checkpoints']]}
        original = deepcopy(doc)
        actual = pass_through(doc)
        require(doc == original and actual == expected,
                f"{c['id']}: pass-through result or input immutability check failed")
        require(il.execute_il(doc) == il.execute_il(il.change_role(doc, 'uil')),
                f"{c['id']}: role conversion changed execution")
        commands = {'python': [sys.executable, str(HERE / 'commit.py')],
                    'javascript': [node, str(HERE / 'commit.js')], 'rust': [str(executable)]}
        for name, command in commands.items():
            observed = json.loads(run(command + c['state'] + ['1' if ready else '0']))
            require(observed == expected,
                    f"{c['id']}: {name} backing disagrees with expected result")
        results.append({'case': c['id'], 'admitted': ready, 'backings_agree': ['pass-through', *commands]})
    for bad in vectors['malformed']:
        try:
            admitted(bad)
        except ValueError:
            continue
        raise AssertionError('malformed input accepted')
    unsupported = program(vectors['cases'][0]['state'], True)
    unsupported['body'].append({'id': 'native', 'op': 'execute_native', 'address': 'untrusted'})
    require(il.execute_il(unsupported)['status'] == 'refused',
            'unsupported native operation was not refused')
    planned = program(vectors['cases'][0]['state'], True)
    planned['resources']['image'] = {'kind': 'graphic', 'uri': 'fixture-only'}
    planned['body'].append({'id': 'image', 'op': 'load_graphic', 'resource': 'image', 'x': 0, 'y': 0})
    require(il.execute_il(planned)['status'] == 'refused',
            'planned graphics operation was not refused without capability')
    require(il.execute_il(planned, capabilities=['graphics'])['status'] == 'pending_host',
            'planned graphics operation did not remain pending for a host')
    # A cheaper alternative with equal final state but different observable
    # order is not eligible. Scores are invented fixture units, not timings.
    reference = pass_through(program(vectors['cases'][0]['state'], True))
    wrong = deepcopy(reference); wrong['events'] = ['cash', 'expense', 'stock']
    candidates = [{'id': 'existing', 'score': 20, 'result': reference},
                  {'id': 'new-equivalent', 'score': 10, 'result': deepcopy(reference)},
                  {'id': 'cheap-wrong-order', 'score': 1, 'result': wrong}]
    qualified = [c for c in candidates if c['result'] == reference]
    winner = min(qualified, key=lambda c: (c['score'], c['id']))['id']
    require(winner == 'new-equivalent',
            'candidate selection did not reject the wrong event order')
    receipt = {'format': 'rfc-0001-synthetic-check-1', 'cases': results,
        'malformed_refused': len(vectors['malformed']), 'backing_comparisons': len(results) * 4,
        'role_conversion_required': False, 'selected_fixture_candidate': winner,
        'cost_kind': 'invented fixture units, not measurements',
        'wrong_order_rejected': True, 'compiler_definition_propagation_implemented': False,
        'versions': {'python': sys.version.split()[0], 'node': run([node, '--version']).strip(),
                     'rustc': run([rustc, '--version']).strip()},
        'source_digests': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (HERE / n for n in ('commit.py', 'commit.js', 'commit.rs', 'vectors.json'))}}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
