#!/usr/bin/env python3
"""Compare the built-in and Ghidra-backed ASM-to-C views.

This is a bounded representation benchmark over authored x86-16 byte blocks,
not a game or general decompiler benchmark. Ghidra launch, import,
disassembly, decompilation and shutdown are included in every Ghidra call's
wall time. The ratio explicitly compares fresh Ghidra requests with warm
in-process built-in requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time

from fdisbull.udl_blocks import asm_to_c, lift_asm_block, lift_c_block, verify_block


def _summary(samples):
    return {'unit': 'seconds_per_call', 'repeats': len(samples),
            'median': statistics.median(samples), 'minimum': min(samples),
            'maximum': max(samples), 'samples': samples}


def _tool_identity(path, java_home):
    identity = {'analyze_headless': path, 'java_home': java_home,
                'java': None, 'ghidra_version': None}
    if path:
        resolved = shutil.which(path) if os.path.basename(path) == path else path
        identity['analyze_headless_resolved'] = str(Path(resolved).resolve()) if resolved else None
        if resolved and Path(resolved).is_file():
            try:
                proc = subprocess.run([resolved, '--help'], capture_output=True,
                                      text=True, timeout=5, env=_env(java_home))
                identity['ghidra_version'] = next((line.strip() for line in
                    (proc.stdout + proc.stderr).splitlines() if 'Ghidra' in line), None)
            except (OSError, subprocess.TimeoutExpired):
                pass
    java = (str(Path(java_home) / 'bin' / 'java') if java_home else shutil.which('java'))
    if java:
        try:
            proc = subprocess.run([java, '-version'], capture_output=True, text=True,
                                  timeout=5, env=_env(java_home))
            identity['java'] = (proc.stderr or proc.stdout).splitlines()[0]
        except (OSError, subprocess.TimeoutExpired):
            identity['java'] = 'unavailable'
    return identity


def _env(java_home):
    env = os.environ.copy()
    if java_home:
        env['JAVA_HOME'] = str(Path(java_home).resolve())
        env['PATH'] = str(Path(java_home) / 'bin') + os.pathsep + env.get('PATH', '')
    return env


def _measure(call, repeats):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    return _summary(samples)


def run(*, repeats=3, analyze_headless=None, java_home=None, timeout_s=120):
    if type(repeats) is not int or not 1 <= repeats <= 100:
        raise ValueError('repeats must be 1..100')
    if type(timeout_s) not in (int, float) or timeout_s <= 0:
        raise ValueError('timeout_s must be positive')
    bindings, inputs, outputs = {'ax': '$value'}, ['ax'], ['ax']
    identity = _tool_identity(analyze_headless, java_home)
    blocks = []
    cases = [
        (2, 'initialized_ax', bytes.fromhex('b8640040')),
        (16, 'initialized_ax', bytes.fromhex('b86400') + bytes([0x40]) * 15),
        # Retain the previously observed decoder/decompiler boundary as a
        # separately labeled diagnostic probe, not as a latency comparison.
        (2, 'uninitialized_ax_failure_probe', bytes.fromhex('05c80048')),
    ]
    for instruction_count, case_kind, raw in cases:
        # Initialize AX so Ghidra can form a decompiled function value. Inputs
        # and output bindings remain identical across all engines and cases.
        # The separately labeled probe intentionally omits initialization.
        lift = lift_asm_block(raw, bindings, inputs=inputs, outputs=outputs)
        engines = {}
        for engine in ('builtin', 'ghidra'):
            if engine == 'ghidra' and not analyze_headless:
                engines[engine] = {'status': 'unknown', 'reason': 'analyze_headless was not supplied'}
                continue
            try:
                def render(engine=engine):
                    return asm_to_c(lift, engine=engine,
                                    analyze_headless=analyze_headless,
                                    java_home=java_home, timeout_s=timeout_s)
                sample = render()
                if not isinstance(sample, dict) or not isinstance(sample.get('text'), str):
                    raise ValueError('engine did not return parseable text field')
                # Warm in-process rendering is meaningful only for the built-in path.
                if engine == 'builtin':
                    # Builtin has no process boundary to cold-start; report its
                    # steady in-process renderer separately from Ghidra launches.
                    timings = {'warm_in_process': _measure(render, repeats)}
                else:
                    # Each invocation launches/analyzes through analyzeHeadless.
                    timings = {'cold_end_to_end': _measure(render, repeats)}
                c_lift = lift_c_block(sample['text'], bindings, inputs=inputs, outputs=outputs)
                proof = verify_block(lift, c_lift['uil'])
                engines[engine] = {'status': 'measured', 'text': sample['text'],
                    'text_sha256': hashlib.sha256(sample['text'].encode()).hexdigest(),
                    'timings': timings, 'equivalence': proof['status'],
                    'proof_scope': proof.get('scope'), 'proof_assumptions': proof.get('assumptions', [])}
                if engine == 'ghidra':
                    engines[engine]['ghidra_version'] = sample.get('ghidra_version')
                    ghidra_c = sample.get('ghidra_c')
                    diagnostics = sample.get('diagnostics')
                    engines[engine]['ghidra_decompiler'] = {
                        'text': ghidra_c,
                        'sha256': hashlib.sha256(ghidra_c.encode()).hexdigest()
                            if isinstance(ghidra_c, str) else None,
                        'characters': len(ghidra_c) if isinstance(ghidra_c, str) else None,
                        'diagnostics': diagnostics,
                    }
            except Exception as exc:
                # Failures stay explicit; a timeout or unsupported output is not a negative proof.
                engines[engine] = {'status': 'unknown', 'error_type': type(exc).__name__,
                                   'reason': str(exc)}
        measured = [v for v in engines.values() if v.get('status') == 'measured']
        proof_statuses = [v.get('equivalence') for v in measured]
        if 'counterexample' in proof_statuses:
            equivalence_gate = 'counterexample'
        elif len(measured) == 2 and all(status == 'equivalent_under_assumptions' for status in proof_statuses):
            equivalence_gate = 'passed'
        else:
            equivalence_gate = 'unknown'
        equivalent = equivalence_gate == 'passed'
        ratio = {'status': 'unknown', 'value': None,
                 'reason': 'both engine equivalence checks must pass'}
        if equivalent:
            ghidra_median = engines['ghidra']['timings']['cold_end_to_end']['median']
            builtin_median = engines['builtin']['timings']['warm_in_process']['median']
            ratio = {'status': 'observed', 'value': ghidra_median / builtin_median,
                     'definition': 'Ghidra cold-process median / builtin warm in-process median',
                     'interpretation': 'Observed request-latency ratio across different deployment modes, not a pure algorithm speed ratio.'}
        blocks.append({'instruction_count': instruction_count, 'case_kind': case_kind,
            'source_hex': raw.hex(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'bindings': bindings,
            'inputs': inputs, 'outputs': outputs, 'engines': engines,
            'outputs_identical': (measured[0]['text'] == measured[1]['text']) if len(measured) == 2 else None,
            'equivalence_gate': equivalence_gate,
            'observed_request_latency_ratio': ratio})
    return {'format': 'fdisbull-asm-c-engine-benchmark-1',
        'environment': {'python': sys.version.split()[0], 'platform': platform.platform(),
                        'ghidra': identity},
        'method': {'repeats': repeats, 'setup': 'One unmeasured output-validation invocation precedes timing. Every measured call starts with source bytes; Ghidra calls include process startup, project setup, import, disassembly, decompilation, extraction and shutdown.',
                   'warmup': 'Builtin warm_in_process is measured after the unmeasured validation call. Ghidra subprocesses are launched for every measured call.',
                   'comparable_stage': 'ASM bytes to parseable normalized C view. The timed Ghidra request also obtains the decompiler C output and diagnostics, retained separately; Ghidra cold_end_to_end includes its full per-call overhead. Builtin warm_in_process is reported separately and is not presented as cold-start equivalent.',
                   'excluded': ['Installation/download time', 'human or agent interpretation time', 'game execution and whole-game recovery'],
                   'limitation': 'Authored straight-line register blocks only; this does not demonstrate game recovery, native parity, general C decompilation quality, or whole-program performance. The report includes two initialized AX timing cases and one separate uninitialized AX failure probe; a Ghidra decompile failure remains unknown and has no latency ratio.'},
        'cases': blocks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyze-headless', help='Exact path to Ghidra analyzeHeadless; omit to leave Ghidra timing unknown')
    parser.add_argument('--java-home', help='JAVA_HOME for Ghidra')
    parser.add_argument('--timeout', type=float, default=120, dest='timeout_s')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True, help='Private JSON destination outside the repository')
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 100 or args.timeout_s <= 0:
        parser.error('repeats must be 1..100 and timeout positive')
    report = run(repeats=args.repeats, analyze_headless=args.analyze_headless,
                 java_home=args.java_home, timeout_s=args.timeout_s)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'cases': len(report['cases']),
                      'equivalence_gates': [c['equivalence_gate'] for c in report['cases']]}))


if __name__ == '__main__':
    main()
