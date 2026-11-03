"""Authored common-UIL conformance and optional private pilot comparison.

This is an authored synthetic program, an authored stock-flow adapter, and an
intentionally miniature memory fixture. Private original media/state is never
needed by the default run. --legacy-root enables a separate-process comparison
with an explicitly selected earlier checkout; it does not run an original CPU.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

from fdisbull.common_uil import default_value, digest, required_capabilities
from fdisbull.uil_runtime import execute_program

PORTS = ('stock', 'produced', 'population', 'supported', 'support_cost')
PORT_TYPES = ('i16', 'i16', 'i8', 'i16', 'i16')


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _value(value, desc):
    return str(value) if desc['type'][0:1] in ('i', 'u') and not desc['type'].endswith('-array') else deepcopy(value)


def package(functions, constants, *, imports=None, resources=None, entry=0):
    """Bind indexed types to separate presentation values, with no native ABI."""
    program = {'format': 'fdisbull-common-uil-1', 'capabilities': [],
               'imports': deepcopy(imports or []), 'functions': deepcopy(functions), 'entry': entry}
    program['capabilities'] = sorted(required_capabilities(program))
    presentation = {'format': 'fdisbull-uil-presentation-1', 'program_sha256': digest(program),
                    'functions': [{'constants': [_value(v, d) for v, d in zip(cs, fn['constants'])],
                                   'initial': [_value(default_value(d), d) for d in fn['variables']]}
                                  for fn, cs in zip(functions, constants)],
                    'resources': deepcopy(resources or [])}
    return program, presentation


def orchestration(program, implementation=None):
    return {'format': 'fdisbull-uil-orchestration-1', 'program_sha256': digest(program),
            'bindings': [] if implementation is None else [{'import': 0, 'implementation': implementation}],
            'ownership': 'copy-in-copy-out', 'max_call_depth': 8}


def synthetic_bundle(*, host_effect=False):
    """Three source languages contribute to a new program, rather than a port."""
    from fdisbull.uil_catalog import build_catalog
    specs = [
        {'language': 'x86-16', 'code': '40', 'flags': 'unobserved',
         'inputs': ['ax'], 'outputs': ['ax'], 'bindings': {'ax': '$x'}},
        {'language': 'c-u16', 'source_text': 'ax += 1;',
         'inputs': ['ax'], 'outputs': ['ax'], 'bindings': {'ax': '$x'}},
        {'language': 'python-u16', 'source_text': 'ax = (ax + 1) & 65535',
         'inputs': ['ax'], 'outputs': ['ax'], 'bindings': {'ax': '$x'}},
        {'language': 'c-u16', 'source_text': 'ax += 2;',
         'inputs': ['ax'], 'outputs': ['ax'], 'bindings': {'ax': '$x'}},
    ]
    catalog = build_catalog(specs)
    groups = [g for g in catalog['groups'] if len(g['implementations']) == 3]
    if len(groups) != 1:
        raise AssertionError('the three explicitly wrapped increment projections must group exactly')
    group = groups[0]
    u16 = {'type': 'u16'}
    entry = {'variables': [u16, u16], 'constants': [], 'inputs': [0], 'outputs': [1],
             'max_steps': 100, 'body': [
                 {'op': 'invoke', 'block': 0, 'inputs': [{'var': 0}], 'outputs': [1]},
                 {'op': 'call', 'function': 1, 'inputs': [{'var': 1}], 'outputs': [1]}]}
    helper = {'variables': [u16], 'constants': [u16], 'inputs': [0], 'outputs': [0],
              'max_steps': 100, 'body': [
                  {'op': 'set', 'dst': 0, 'value': {'op': 'add', 'type': 'u16',
                                                       'args': [{'var': 0}, {'const': 0}]}}]}
    resources = []
    if host_effect:
        entry['constants'] = [{'type': 'resource'}]
        entry['body'].append({'op': 'effect', 'service': 'text.show', 'inputs': [{'const': 0}]})
        resources = [{'kind': 'text', 'text': 'The authored synthetic calculation is ready.'}]
    program, presentation = package([entry, helper], [[0] if host_effect else [], [7]],
        imports=[{'semantic_id': group['semantic_id'], 'inputs': [u16], 'outputs': [u16], 'effects': []}],
        resources=resources)
    return program, presentation, catalog, group


def food_legacy_program():
    """Authored restatement of public stock_flow.maintenance_contract's UIL.

    The contract's input domain is support_cost in {1,2}. That domain is outside
    the legacy statement list; food_bundle deliberately adds an explicit guard.
    """
    variables = {'$' + n: {'type': t, 'initial': 0} for n, t in zip(PORTS, PORT_TYPES)}
    variables.update({'$' + n: {'type': 'i16', 'initial': 0}
                      for n in ('consumption', 'support', 'new_stock')})
    def change(op, name, value, label):
        return {'id': label, 'op': op, 'var': '$' + name, 'value': value}
    ref = lambda name: {'var': '$' + name}
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables, 'resources': {}, 'body': [
        change('set', 'consumption', ref('population'), 'widen-population'),
        change('add', 'consumption', ref('population'), 'resident-consumption'),
        change('set', 'support', ref('supported'), 'support-base'),
        {'id': 'support-rate', 'op': 'if', 'condition': {'op': 'eq', 'left': ref('support_cost'), 'right': 2},
         'then': [change('add', 'support', ref('supported'), 'double-support')], 'else': []},
        change('set', 'new_stock', ref('stock'), 'stock-base'),
        change('add', 'new_stock', ref('produced'), 'production'),
        change('subtract', 'new_stock', ref('consumption'), 'residents'),
        change('subtract', 'new_stock', ref('support'), 'support')]}


def food_bundle():
    from fdisbull.uil_catalog import from_scalar_il
    imported = from_scalar_il(food_legacy_program(), inputs=['$' + n for n in PORTS], outputs=['$new_stock'])
    fn, cs = deepcopy(imported['function']), list(imported['constants'])
    cost = fn['inputs'][4]
    slots = [len(cs), len(cs) + 1]
    fn['constants'] += [{'type': 'i16'}, {'type': 'i16'}]
    cs += [1, 2]
    fn['body'] = [
        {'op': 'require', 'condition': {'op': 'ge', 'type': 'bool', 'args': [{'var': cost}, {'const': slots[0]}]}},
        {'op': 'require', 'condition': {'op': 'le', 'type': 'bool', 'args': [{'var': cost}, {'const': slots[1]}]}}
    ] + fn['body']
    return package([fn], [cs])


def food_vectors():
    """The public CivD food-swap pilot's deterministic 2,018 input vectors."""
    values = (-32768, -1, 0, 1, 32767)
    result = [list(v) for v in itertools.product(values, values, (-128, -1, 0, 1, 127), values, (1, 2))]
    result += [[10, 12, p, 3, c] for p in range(-128, 128) for c in (1, 2)]
    rng = random.Random(0xc17d)
    result += [[rng.randrange(-32768, 32768), rng.randrange(-32768, 32768),
                rng.randrange(-128, 128), rng.randrange(-32768, 32768), rng.choice((1, 2))]
               for _ in range(256)]
    return result


def food_expected(vector):
    stock, produced, population, supported, cost = vector
    if cost not in (1, 2):
        raise ValueError('unsupported maintenance domain')
    word = (stock + produced - 2 * population - supported * cost) & 65535
    return word - 65536 if word & 32768 else word


def mini_snake_program():
    """Authored 5x4 movement/raster microfixture, not the recovered Snake game.

    Words 0..6: x,y,direction,alive,score,food_x,food_y; frame at 32..51.
    Directions right/down/left/up = 0/1/2/3. Other words must be preserved.
    """
    load = lambda i: {'load': i}
    calc = lambda op, a, b: {'op': op, 'left': a, 'right': b}
    store = lambda i, v: {'op': 'store', 'index': i, 'value': v}
    cond = lambda q, yes, no=None: {'op': 'if', 'condition': q, 'then': yes, 'else': no or []}
    step = cond(load(3), [
        cond(calc('eq', load(2), 0), [store(0, calc('add', load(0), 1))]),
        cond(calc('eq', load(2), 1), [store(1, calc('add', load(1), 1))]),
        cond(calc('eq', load(2), 2), [store(0, calc('sub', load(0), 1))]),
        cond(calc('eq', load(2), 3), [store(1, calc('sub', load(1), 1))]),
        cond(calc('ge', load(0), 5), [store(3, 0)]),
        cond(calc('ge', load(1), 4), [store(3, 0)]),
        cond(load(3), [cond(calc('eq', load(0), load(5)), [
            cond(calc('eq', load(1), load(6)), [store(4, calc('add', load(4), 1))])])])])
    address = lambda x, y: calc('add', 32, calc('add', calc('mul', y, 5), x))
    raster = [
        {'op': 'set', 'var': '$pixel', 'value': 0},
        {'op': 'while', 'condition': calc('lt', {'var': '$pixel'}, 20), 'limit': 20, 'body': [
            store(calc('add', 32, {'var': '$pixel'}), 0),
            {'op': 'set', 'var': '$pixel', 'value': calc('add', {'var': '$pixel'}, 1)}]},
        store(address(load(5), load(6)), 2),
        cond(load(3), [store(address(load(0), load(1)), 1)])]
    return {'format': 'fdisbull-memory-uil-1', 'role': 'uil', 'memory': {'words': 64},
            'variables': {'$pixel': {'type': 'u32', 'initial': 0}},
            'functions': {'step': {'max_steps': 100, 'body': [step]},
                          'render': {'max_steps': 100, 'body': raster}}}


def mini_initial():
    words = [0] * 64
    words[:7] = [1, 1, 0, 1, 0, 2, 1]
    words[63] = 0xdeadbeef
    return words


def mini_expected(words, function):
    out = list(words)
    if function == 'step' and out[3]:
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[out[2]]
        out[0], out[1] = (out[0] + dx) & 0xffffffff, (out[1] + dy) & 0xffffffff
        if out[0] >= 5 or out[1] >= 4:
            out[3] = 0
        elif out[0:2] == out[5:7]:
            out[4] = (out[4] + 1) & 0xffffffff
    if function == 'render':
        out[32:52] = [0] * 20
        out[32 + out[6] * 5 + out[5]] = 2
        if out[3]:
            out[32 + out[1] * 5 + out[0]] = 1
    return out


def memory_bundle(program, function):
    from fdisbull.uil_catalog import from_memory_uil
    imported = from_memory_uil(program, function)
    return package([imported['function']], [imported['constants']])


def run_emitted(directory, target, inputs):
    executable = [sys.executable, str(Path(directory) / 'program.py')]
    if target == 'javascript':
        node = shutil.which('node')
        if node is None:
            raise RuntimeError('JavaScript qualification requires a local node executable')
        executable = [node, str(Path(directory) / 'program.mjs')]
    proc = subprocess.run(executable, input=''.join(json.dumps({'inputs': x}) + '\n' for x in inputs),
                          capture_output=True, text=True, timeout=180, check=True)
    rows = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(rows) != len(inputs):
        raise AssertionError('standalone process did not answer every input exactly once')
    return rows


_LEGACY_SCRIPT = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root / 'src'))
request = json.load(sys.stdin)
if request['kind'] == 'food':
    from fdisbull.stock_flow import maintenance_contract
    from fdisbull.interaction_il import execute_il
    contract = maintenance_contract()
    program = contract['behavior']['program']
    values = []
    for vector in request['vectors']:
        state = {k: v['initial'] for k,v in program['variables'].items()}
        state.update(dict(zip(['$stock','$produced','$population','$supported','$support_cost'], vector)))
        result = execute_il(program, state=state)
        if result['status'] != 'complete': raise RuntimeError(result.get('error', 'legacy food refusal'))
        values.append(result['state']['$new_stock'])
    print(json.dumps({'values': values, 'program': program}))
elif request['kind'] == 'memory':
    from fdisbull.udc_web_memory import execute_memory_uil
    result = execute_memory_uil(request['program'], request['function'], request['words'])
    if result['status'] != 'complete': raise RuntimeError(result.get('error', 'legacy memory refusal'))
    print(json.dumps({'words':result['words']}))
'''


def legacy_compare(root, python, request):
    """Deliberately isolate package roots and decoder versions in a subprocess."""
    proc = subprocess.run([str(python), '-B', '-c', _LEGACY_SCRIPT, str(Path(root).resolve())],
                          input=json.dumps(request), text=True, capture_output=True,
                          timeout=180, check=True)
    return json.loads(proc.stdout)


def private_snake(manifest_path, legacy_root, legacy_python, *, output=None, targets=()):
    from fdisbull.uil_codegen import compile_program
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text())
    program = manifest['program']
    initial = manifest.get('initial', manifest.get('initial_words'))
    if initial is None and 'initial_path' in manifest:
        data = json.loads((path.parent / manifest['initial_path']).read_text())
        initial = data if isinstance(data, list) else data['initial']
    if not isinstance(initial, list) or len(initial) != program['memory']['words']:
        raise ValueError('private manifest needs exact initial/initial_words array or initial_path')
    words = list(initial)
    rows = []
    for name in ('reset', 'step', 'render'):
        if name not in program['functions']:
            continue
        expected = legacy_compare(legacy_root, legacy_python,
            {'kind': 'memory', 'program': program, 'function': name, 'words': words})['words']
        common, presentation = memory_bundle(program, name)
        result = execute_program(common, presentation, inputs=[words])
        if result['status'] != 'complete' or result['outputs'] != [expected]:
            raise AssertionError('private Snake legacy/common mismatch in ' + name)
        generated = []
        for target in targets:
            directory = Path(output) / ('private-snake-' + name + '-' + target)
            empty = {'format': 'fdisbull-uil-catalog-1', 'groups': [], 'rejected': []}
            artifact = compile_program(common, presentation, empty, orchestration(common), directory, target=target)
            emitted = run_emitted(directory, target, [[words]])[0]
            if emitted['status'] != 'complete' or emitted['outputs'] != [expected]:
                raise AssertionError('private Snake generated output mismatch in ' + name + '/' + target)
            generated.append({'target': target, 'artifacts': artifact['artifacts'], 'result_sha256': digest(emitted['outputs'][0])})
        rows.append({'function': name, 'status': result['status'], 'steps': result['steps'],
                     'words': len(words), 'result_sha256': digest(expected),
                     'common_program_sha256': digest(common), 'generated': generated})
        words = expected
    if not rows:
        raise ValueError('private Snake manifest has none of reset/step/render')
    return {'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'legacy_program_sha256': digest(program), 'initial_sha256': digest(initial), 'comparisons': rows,
            'claim': 'prepared model/evaluator comparison; no original CPU or host input qualification'}


def qualify(output, *, targets=('python', 'javascript'), legacy_root=None,
            legacy_python=sys.executable, snake_manifest=None):
    from fdisbull.uil_codegen import compile_program
    output = Path(output).resolve()
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        raise ValueError('choose a new private output directory outside Git')
    if snake_manifest and not legacy_root:
        raise ValueError('--snake-manifest requires --legacy-root')
    output.mkdir(parents=True, mode=0o700)
    program, presentation, catalog, group = synthetic_bundle()
    vectors = [[x] for x in (0, 1, 65527, 65528, 65535)]
    reports = []
    for impl in group['implementations']:
        plan = orchestration(program, impl['id'])
        expected = [execute_program(program, presentation, plan, catalog, inputs=x) for x in vectors]
        _check([r['outputs'] for r in expected] == [[(x[0] + 8) & 65535] for x in vectors], 'synthetic independent formula mismatch')
        for target in targets:
            directory = output / ('synthetic-' + impl['language'] + '-' + target)
            artifact = compile_program(program, presentation, catalog, plan, directory, target=target)
            actual = run_emitted(directory, target, vectors)
            for a, e in zip(actual, expected):
                _check({k: a[k] for k in ('status', 'outputs', 'state', 'events')} == {k: e[k] for k in ('status', 'outputs', 'state', 'events')}, 'synthetic standalone mismatch')
            reports.append({'source_language': impl['language'], 'target': target, 'cases': len(vectors),
                            'implementation': impl['id'], 'artifacts': artifact['artifacts']})
    food, food_presentation = food_bundle()
    cases = food_vectors()
    answers = [food_expected(v) for v in cases]
    got = [execute_program(food, food_presentation, inputs=v) for v in cases]
    _check([r['outputs'][0] for r in got if r['status'] == 'complete'] == answers, 'food common/formula mismatch')
    food_reports = []
    empty = {'format': 'fdisbull-uil-catalog-1', 'groups': [], 'rejected': []}
    for target in targets:
        directory = output / ('food-' + target)
        artifact = compile_program(food, food_presentation, empty, orchestration(food), directory, target=target)
        actual = run_emitted(directory, target, cases)
        _check(all(r['status'] == 'complete' for r in actual), 'food standalone refusal')
        _check([r['outputs'][0] for r in actual] == answers, 'food standalone/formula mismatch')
        food_reports.append({'target': target, 'cases': len(cases), 'artifacts': artifact['artifacts']})
    mini = mini_snake_program()
    memory_reports = []
    words = mini_initial()
    for name in ('step', 'render'):
        common, view = memory_bundle(mini, name)
        answer = mini_expected(words, name)
        _check(execute_program(common, view, inputs=[words])['outputs'] == [answer], 'miniature common/independent memory mismatch')
        for target in targets:
            directory = output / ('mini-snake-' + name + '-' + target)
            artifact = compile_program(common, view, empty, orchestration(common), directory, target=target)
            result = run_emitted(directory, target, [[words]])[0]
            _check(result['status'] == 'complete' and result['outputs'] == [answer], 'miniature standalone/independent memory mismatch')
            memory_reports.append({'function': name, 'target': target, 'artifacts': artifact['artifacts']})
        words = answer
    report = {'format': 'fdisbull-common-uil-conformance-1', 'synthetic': reports,
              'same_synthetic_program_sha256': digest(program), 'food': food_reports,
              'food_vectors_sha256': digest(cases), 'miniature_memory': memory_reports,
              'limits': ['exact normalized grouping, not general semantic proof',
                         'generated Python/JavaScript execution, not source CPU or native game qualification',
                         'authored miniature Snake fixture, not recovery of the original game']}
    if legacy_root:
        legacy_path = Path(legacy_root).resolve()
        report['legacy_sources'] = {name: hashlib.sha256((legacy_path / 'src' / 'fdisbull' / name).read_bytes()).hexdigest()
                                    for name in ('stock_flow.py', 'interaction_il.py', 'udc_web_memory.py')}
        report['legacy_root'] = str(legacy_path)
        report['legacy_head'] = subprocess.run(['git', '-C', str(legacy_path), 'rev-parse', 'HEAD'],
                                               capture_output=True, text=True, check=True).stdout.strip()
        baseline = legacy_compare(legacy_root, legacy_python, {'kind': 'food', 'vectors': cases})
        _check(baseline['values'] == answers, 'legacy food/formula mismatch')
        _check(baseline['program'] == food_legacy_program(), 'legacy food source statement identity changed')
        # Retain source identity rather than the legacy source program/state.
        report['legacy_food'] = {'cases': len(cases), 'program_sha256': digest(baseline['program']),
                                 'result_sha256': digest(baseline['values']), 'mismatches': 0}
        if snake_manifest:
            report['private_snake'] = private_snake(snake_manifest, legacy_root, legacy_python, output=output, targets=targets)
    (output / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--legacy-root', type=Path)
    parser.add_argument('--legacy-python', type=Path, default=Path(sys.executable))
    parser.add_argument('--snake-manifest', type=Path)
    parser.add_argument('--python-only', action='store_true')
    args = parser.parse_args(argv)
    report = qualify(args.output, targets=('python',) if args.python_only else ('python', 'javascript'),
                     legacy_root=args.legacy_root, legacy_python=args.legacy_python,
                     snake_manifest=args.snake_manifest)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
