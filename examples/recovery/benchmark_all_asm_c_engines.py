#!/usr/bin/env python3
"""Compare four ASM-to-C engines only after the same bounded proof passes.

Times include each renderer's request path. Proof and output comparison are
performed after each timer stops. External tool installation is not timed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time

from fdisbull.udl_blocks import asm_to_c, lift_asm_block, qualify_asm_c_view


CASES = (
    ('initialized_ax_2', bytes.fromhex('b8640040')),
    ('initialized_ax_16', bytes.fromhex('b86400') + b'\x40' * 15),
    ('input_dependent_ax', bytes.fromhex('05c80048')),
)


def _file_sha256(path):
    if path is None or not Path(path).is_file():
        return None
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(*, ghidra=None, java_home=None, reko=None, dotnet=None, dcc=None,
        repeats=3, timeout_s=120):
    if type(repeats) is not int or not 1 <= repeats <= 100:
        raise ValueError('repeats must be 1..100')
    if type(timeout_s) not in (int, float) or timeout_s <= 0:
        raise ValueError('timeout_s must be positive')
    configs = {
        'builtin': {},
        'ghidra': {'tool_path': ghidra, 'runtime_path': java_home},
        'reko': {'tool_path': reko, 'runtime_path': dotnet},
        'dcc': {'tool_path': dcc},
    }
    report = {'format': 'fdisbull-asm-c-all-engine-benchmark-1',
              'method': {'repeats': repeats,
                         'timing': 'wall seconds per rendering call; proof and output checks occur after each timer stops',
                         'gate': 'Every initial and timed normalized view must be equivalent_under_assumptions and identical within its engine; other outcomes have no accepted timing',
                         'scope': 'Authored x86-16 straight-line register blocks; native C listings, DOS interrupts, memory, flags, ABI and runtime behavior are not proved',
                         'deployment': 'builtin warm Python call; external engines launch fresh tool processes for each call'},
              'host': {'system': platform.system(), 'machine': platform.machine(),
                       'python': platform.python_version()},
              'tools': {name: {key: str(value) if value is not None else None
                               for key, value in config.items()} |
                        {'tool_sha256': _file_sha256(config.get('tool_path')),
                         'runtime_sha256': _file_sha256(config.get('runtime_path'))}
                        for name, config in configs.items()},
              'cases': []}
    for name, source in CASES:
        lift = lift_asm_block(source, {'ax': '$result'}, inputs=['ax'], outputs=['ax'])
        engines = {}
        for engine, config in configs.items():
            if engine != 'builtin' and not config['tool_path']:
                engines[engine] = {'status': 'unavailable', 'reason': 'tool_path not configured'}
                continue
            try:
                def render():
                    return asm_to_c(lift, engine=engine, timeout_s=timeout_s, **config)

                initial = render()
                proof = qualify_asm_c_view(lift, initial)
                if proof['status'] != 'equivalent_under_assumptions':
                    engines[engine] = {'status': 'unqualified', 'proof_status': proof['status']}
                    continue
                samples = []
                for _ in range(repeats):
                    started = time.perf_counter()
                    view = render()
                    elapsed = time.perf_counter() - started
                    if view['text'] != initial['text'] or view['source_sha256'] != lift['sha256']:
                        raise ValueError('timed output changed')
                    repeated_proof = qualify_asm_c_view(lift, view)
                    if repeated_proof['status'] != 'equivalent_under_assumptions':
                        raise ValueError('timed output is not qualified: ' + repeated_proof['status'])
                    samples.append(elapsed)
                engines[engine] = {'status': 'qualified', 'source_sha256': lift['sha256'],
                                   'text_sha256': hashlib.sha256(initial['text'].encode()).hexdigest(),
                                   'text': initial['text'], 'native_c_sha256': (
                                       hashlib.sha256(initial['native_c'].encode()).hexdigest()
                                       if initial['native_c'] is not None else None),
                                   'proof_status': proof['status'], 'samples_s': samples,
                                   'median_s': statistics.median(samples),
                                   'minimum_s': min(samples), 'maximum_s': max(samples),
                                   'engine_result_format': initial['engine_result_format']}
            except Exception as exc:
                engines[engine] = {'status': 'unknown', 'error_type': type(exc).__name__,
                                   'reason': str(exc)}
        qualified = [x for x in engines.values() if x['status'] == 'qualified']
        report['cases'].append({'name': name, 'source_hex': source.hex(),
                                'source_sha256': lift['sha256'],
                                'normalized_outputs_identical': (
                                    len({x['text_sha256'] for x in qualified}) == 1
                                    if len(qualified) == len(configs) else None),
                                'engines': engines})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghidra', help='Ghidra analyzeHeadless executable')
    parser.add_argument('--java-home', help='Java home for Ghidra')
    parser.add_argument('--reko', help='Reko CLI executable or reko.dll')
    parser.add_argument('--dotnet', help='dotnet executable for reko.dll')
    parser.add_argument('--dcc', help='DCC executable')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=120, dest='timeout_s')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output
    report = run(**{k: v for k, v in vars(args).items() if k != 'output'})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output),
                      'case_statuses': [{k: v['status'] for k, v in case['engines'].items()}
                                        for case in report['cases']]}))


if __name__ == '__main__':
    main()
