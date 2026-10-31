#!/usr/bin/env python3
"""Measure bounded SH-2 word scans. Raw results may contain private game bytes."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import itertools
import importlib.metadata
import json
import math
import os
import stat
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time

from fdisbull.rom_asm import BACKENDS, MAX_SOURCE_BYTES, disassemble_rom


def integer(s):
    return int(s, 0)


def stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {"values": values, "median": statistics.median(values), "min": ordered[0],
            "max": ordered[-1], "p95_nearest_rank": ordered[math.ceil(.95 * len(ordered)) - 1]}


def cpu_name():
    if sys.platform == "darwin":
        p = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout.strip()
    return platform.processor() or "unknown"


def compare(a, b):
    left = {r['address']: r['normalized'] for r in a['instructions']}
    right = {r['address']: r['normalized'] for r in b['instructions']}
    addresses = range(a['mapping']['address'], a['mapping']['address'] + a['attempted_words'] * 2, 2)
    result = {"both_decoded": 0, "both_unknown": 0, "left_only_decoded": 0,
              "right_only_decoded": 0, "mnemonic_agreement": 0, "operand_agreement": 0,
              "both_agreement": 0}
    for address in addresses:
        x, y = left.get(address), right.get(address)
        if x is None and y is None:
            result['both_unknown'] += 1
        elif x is None:
            result['right_only_decoded'] += 1
        elif y is None:
            result['left_only_decoded'] += 1
        else:
            result['both_decoded'] += 1
            m, o = x['mnemonic'] == y['mnemonic'], x['operands'] == y['operands']
            result['mnemonic_agreement'] += m
            result['operand_agreement'] += o
            result['both_agreement'] += m and o
    return result



def private_output(path):
    resolved = path.expanduser().resolve()
    for ancestor in (resolved, *resolved.parents):
        if (ancestor / ".git").exists():
            raise ValueError("raw output directory must be outside every Git worktree")
    return resolved


def read_source(path):
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_SOURCE_BYTES:
            raise ValueError("source must be a nonempty regular file at most 64 MiB")
        data = stream.read(MAX_SOURCE_BYTES + 1)
        after, current = os.fstat(stream.fileno()), path.stat()
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current) or len(data) != before.st_size:
            raise ValueError("source changed during read")
        return data


def check_result(result, data, base, offset, length):
    mapping = result["mapping"]
    if (result["source_sha256"] != hashlib.sha256(data).hexdigest()
            or result["range_sha256"] != hashlib.sha256(data[offset:offset + length]).hexdigest()
            or result["source_size"] != len(data) or mapping["base_address"] != base
            or mapping["file_offset"] != offset or mapping["address"] != base + offset
            or mapping["length"] != length or result["max_instructions"] != length // 2
            or result["attempted_words"] != length // 2 or result["mode"] != "word-scan"
            or result["executed"] is not False or result["code_discovered"] is not False
            or result["persisted"] is not False):
        raise RuntimeError("benchmark result failed source, mapping, budget or execution checks")


def fact_signature(result):
    return json.dumps({"instructions": result["instructions"], "undecoded_words": result["undecoded_words"],
                       "rejected_native_facts": result.get("rejected_native_facts", [])},
                      sort_keys=True, separators=(",", ":"))


def source_hashes():
    root = Path(__file__).resolve().parent.parent
    paths = ["scripts/benchmark_rom_asm.py", "src/fdisbull/rom_asm.py", "src/fdisbull/rom_asm_capstone.py",
             "src/fdisbull/rom_asm_ghidra.py", "src/fdisbull/rom_asm_saturn.py",
             "src/fdisbull/ghidra_scripts/RomAsm.java", "src/fdisbull/ghidra_scripts/RomAsmServer.java",
             "patches/capstone-5.0.9-sh-profile-gating.patch", "tests/rom_asm_sh2_vectors.json"]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}


def accuracy_gate(args, session, backends=BACKENDS):
    fixture = json.loads((Path(__file__).resolve().parent.parent / 'tests/rom_asm_sh2_vectors.json').read_text())
    cases = fixture['cases'] + [{'name': 'reject_sh2a_rtv_n', 'hex': '027b', 'mnemonic': None, 'operands': None}]
    results = {}
    for backend in backends:
        failures = []
        for case in cases:
            report = disassemble_rom(bytes.fromhex(case['hex']), backend=backend,
                base_address=case.get('address', fixture['base_address']), mode='word-scan',
                ghidra_home=args.ghidra_home, saturn_recomp_root=args.saturn_root,
                ghidra_session=session if backend == 'ghidra' else None, timeout=args.timeout)
            rows = report['instructions']
            expected = case['mnemonic']
            if ((expected is None and rows) or
                    (expected is not None and (len(rows) != 1 or rows[0]['normalized'] !=
                        {'mnemonic': expected, 'operands': case['operands']}))):
                failures.append(case['name'])
        results[backend] = {'cases': len(cases), 'passed': len(cases) - len(failures), 'failed_cases': failures}
    if any(r['failed_cases'] for r in results.values()):
        raise RuntimeError(f'accuracy gate failed: {results}')
    return results


def collect(args, data, offsets, summary, output_dir):
    records = {backend: [] for backend in BACKENDS}
    with ExitStack() as owned:
        session = None
        if args.ghidra_mode == 'persistent':
            from fdisbull.rom_asm_ghidra import GhidraDecodeSession
            session = owned.enter_context(GhidraDecodeSession(ghidra_home=args.ghidra_home, timeout=args.timeout))
        pid = session._proc.pid if session is not None else None
        summary['ghidra_session'] = {'mode': args.ghidra_mode,
            'startup_seconds': session.startup_seconds if session is not None else None,
            'persistent_processes': 1 if session is not None else 0}
        preflight = time.perf_counter()
        summary['accuracy_gate'] = accuracy_gate(args, session)
        summary['accuracy_gate_seconds'] = time.perf_counter() - preflight
        summary['warmup_runs'] = []
        for repetition in range(-args.warmup_rounds, args.repetitions):
            for sample_index, offset in enumerate(offsets):
                shift = (repetition + sample_index) % len(BACKENDS)
                order = BACKENDS[shift:] + BACKENDS[:shift]
                for backend in order:
                    warmup = repetition < 0
                    label = f'warmup {repetition + args.warmup_rounds + 1}' if warmup else f'round {repetition + 1}/{args.repetitions}'
                    print(f'{label}, sample {sample_index + 1}/{len(offsets)}, {backend}', flush=True)
                    if not warmup:
                        summary['execution_order'].append({'round': repetition + 1, 'sample_index': sample_index, 'backend': backend})
                    start = time.perf_counter()
                    result = disassemble_rom(data, base_address=args.base, backend=backend, offset=offset,
                        length=args.sample_length, max_instructions=args.sample_length // 2,
                        mode='word-scan', ghidra_home=args.ghidra_home,
                        ghidra_session=session if backend == 'ghidra' else None,
                        saturn_recomp_root=args.saturn_root, timeout=args.timeout)
                    api_wall = time.perf_counter() - start
                    check_result(result, data, args.base, offset, args.sample_length)
                    if session is not None and session._proc.pid != pid:
                        raise RuntimeError('persistent Ghidra process changed during measurement')
                    earlier = next((r['result'] for r in records[backend] if r['sample_index'] == sample_index), None)
                    if earlier is not None and fact_signature(earlier) != fact_signature(result):
                        raise RuntimeError(f'{backend} produced unstable facts for sample {sample_index}')
                    name = (f'warmup-{repetition + args.warmup_rounds + 1:02d}' if warmup else f'round-{repetition + 1:02d}') + f'-sample-{sample_index + 1:02d}-{backend}.json'
                    (output_dir / name).write_text(json.dumps(result, indent=2) + '\n')
                    item = {'round': repetition + 1, 'sample_index': sample_index,
                        'api_wall_seconds': api_wall, 'backend_wall_seconds': result['backend_elapsed_seconds'],
                        'engine_loop_seconds': result.get('decode_seconds'), 'result': result}
                    if warmup:
                        summary['warmup_runs'].append({k: v for k, v in item.items() if k != 'result'} | {'backend': backend})
                    else:
                        records[backend].append(item)
    return records

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--base', type=integer, required=True)
    ap.add_argument('--ghidra-home', required=True)
    ap.add_argument('--saturn-root', required=True)
    ap.add_argument('--output-dir', type=Path, required=True, help='new private directory for raw results')
    ap.add_argument('--repetitions', type=int, default=5)
    ap.add_argument('--sample-offset', action='append', type=integer)
    ap.add_argument('--sample-length', type=int, default=2048)
    ap.add_argument('--timeout', type=float, default=180)
    ap.add_argument('--ghidra-mode', choices=('fresh', 'persistent'), default='fresh')
    ap.add_argument('--warmup-rounds', type=int, default=1)
    args = ap.parse_args()
    offsets = args.sample_offset if args.sample_offset is not None else [0, 0x10000, 0x40000, 0x80000]
    if args.repetitions < 1 or not 0 <= args.warmup_rounds <= 10 or args.sample_length < 2 or args.sample_length > 65536 or args.sample_length % 2:
        ap.error('repetitions must be positive and sample length must be even and in 2..65536')
    if len(set(offsets)) != len(offsets) or any(x < 0 or x % 2 for x in offsets):
        ap.error('sample offsets must be unique nonnegative even integers')
    try:
        output_dir = private_output(args.output_dir)
        data = read_source(args.source)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    if any(x + args.sample_length > len(data) for x in offsets):
        ap.error('sample extends beyond input')
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    samples = [{"offset": x, "length": args.sample_length,
                "sha256": hashlib.sha256(data[x:x + args.sample_length]).hexdigest()} for x in offsets]
    summary = {"schema": "fdisbull-rom-asm-benchmark-1", "source_sha256": hashlib.sha256(data).hexdigest(),
               "source_size": len(data), "base_address": args.base, "samples": samples, "source_file_hashes": source_hashes(),
               "repetitions": args.repetitions, "mode": "word-scan", "engines": {}, "comparisons": [], "execution_order": [],
               "environment": {"python": platform.python_version(), "os": platform.platform(),
                               "cpu": cpu_name(), "clock": vars(time.get_clock_info('perf_counter'))},
               "scope": "Static aligned word hypotheses; selected ranges include data and do not establish reachable code. Agreement is not an oracle. Engine loop times measure different work; API and backend wall times include different overheads."}
    records = collect(args, data, offsets, summary, output_dir)
    for backend, runs in records.items():
        summary['engines'][backend] = {"versions": sorted({r['result']['engine_version'] for r in runs}),
            "distribution_version": importlib.metadata.version("capstone") if backend == "capstone" else None,
            "engine_identities": [r["result"].get("engine_identity") for r in runs if r["result"].get("engine_identity") is not None],
            "runs": [{k: v for k, v in r.items() if k != 'result'} | {"decoded_words": r['result']['decoded_words'],
                     "undecoded_words": len(r['result']['undecoded_words'])} for r in runs],
            "timing": {key: stats([r[key] for r in runs if r[key] is not None]) for key in
                       ('api_wall_seconds', 'backend_wall_seconds', 'engine_loop_seconds')}}
    if args.ghidra_mode == 'persistent':
        values = [r['api_wall_seconds'] for r in records['ghidra']]
        summary['ghidra_session']['startup_plus_measured_api_seconds'] = summary['ghidra_session']['startup_seconds'] + sum(values)
        summary['ghidra_session']['startup_charged_api_mean_seconds'] = summary['ghidra_session']['startup_plus_measured_api_seconds'] / len(values)
    for repetition in range(1, args.repetitions + 1):
        for sample_index in range(len(offsets)):
            for left, right in itertools.combinations(BACKENDS, 2):
                a = next(r['result'] for r in records[left] if r['round'] == repetition and r['sample_index'] == sample_index)
                b = next(r['result'] for r in records[right] if r['round'] == repetition and r['sample_index'] == sample_index)
                summary['comparisons'].append({"round": repetition, "sample_index": sample_index, "left": left, "right": right, **compare(a, b)})
    if source_hashes() != summary['source_file_hashes']:
        raise RuntimeError('benchmark or adapter source changed during measurement')
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
