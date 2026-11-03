"""Differentially check generated Python UDC against the existing fDisBull pilot VM.

This is a bounded same-model check and is NOT independent-emulator validation.
Every single step compares registers, RAM, display, timers, stack, keyboard,
PC, RNG state, and the declared instruction/trap outcome.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from chip8lab.vm import Machine, Trap
from .generator import compile_file


def import_generated(path: Path):
    spec = importlib.util.spec_from_file_location('generated_chip8_udc_local', path)
    if spec is None or spec.loader is None: raise ValueError('cannot import generated module')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def injected_keys(mode: str, index: int) -> set[int]:
    if mode == 'idle': return set()
    if mode == 'hold5': return {5}
    if mode == 'pulses':
        return {5} if (index // 31) % 4 == 1 else {4} if (index // 31) % 4 == 3 else set()
    raise ValueError('unknown key schedule')


def step_with_trap(callback, machine):
    try:
        return ('result', callback(machine)), None
    except Trap as exc:
        return ('trap', exc.code), {'kind': exc.code, 'address': exc.address,
                                   'word': exc.word}


def check(rom: Path, generated: Path, *, seeds=(0, 1), modes=('idle','hold5','pulses'),
          steps=1200, tick_period=11) -> dict:
    candidate = import_generated(generated)
    raw = rom.read_bytes()
    results = []
    total_native, total_fallback, total_checked = 0, 0, 0
    fallback_families = Counter()
    specialized_families = Counter()
    for seed in seeds:
        for mode in modes:
            baseline = Machine(seed=seed)
            baseline.load_rom(raw)
            lower = candidate.build_machine(rom, seed=seed)
            native = fallback = 0
            stop = None
            for index in range(steps):
                if tick_period and index and index % tick_period == 0:
                    baseline.tick_60hz(); lower.tick_60hz()
                baseline.keys = injected_keys(mode, index)
                lower.keys = injected_keys(mode, index)
                spec = candidate.can_run_specialized(lower)
                pc_before = baseline.pc
                a, at = step_with_trap(lambda m:m.step(), baseline)
                b, bt = step_with_trap(candidate.step, lower)
                total_checked += 1
                if a != b or at != bt or baseline.state_digest() != lower.state_digest():
                    return {'status': 'counterexample', 'source_sha256': sha256(raw).hexdigest(),
                            'source': rom.name, 'seed': seed, 'key_schedule': mode,
                            'step': index, 'pc': pc_before, 'original_outcome': a,
                            'python_outcome': b, 'original_trap': at,
                            'python_trap': bt, 'original_digest': baseline.state_digest(),
                            'python_digest': lower.state_digest(),
                            'native_steps': native, 'fallback_steps': fallback}
                if spec:
                    native += 1; specialized_families[lower.last_family] += 1
                else:
                    fallback += 1; fallback_families[lower.last_family] += 1
                if a[0] == 'trap' or a == ('result','waiting'):
                    stop = a[1]
                    break
            results.append({'seed': seed, 'key_schedule': mode,
                            'compared_steps': native+fallback,
                            'specialized_steps': native, 'original_backed_steps': fallback,
                            'stopped': stop or 'budget',
                            'last_pc': baseline.pc,
                            'final_digest': baseline.state_digest()})
            total_native += native; total_fallback += fallback
    return {'status': 'passed', 'source': rom.name, 'source_sha256': sha256(raw).hexdigest(),
            'generated_python_sha256': sha256(generated.read_bytes()).hexdigest(),
            'comparison': 'exact equality per step to same authored CHIP-8 pilot VM',
            'independent_emulator_oracle': False,
            'compared_steps': total_checked,
            'specialized_steps': total_native,
            'original_backed_steps': total_fallback,
            'specialized_fraction': round(total_native/max(1,total_checked),6),
            'specialized_families_executed': dict(sorted(specialized_families.items())),
            'original_backed_families_executed': dict(sorted(fallback_families.items())),
            'runs': results,
            'assertion_scope': 'Only observed initial states, key schedules, seed, timer policy and bounded steps',
            'trusted_runtime': 'existing chip8lab.vm Machine, not production fdisbull-uil-compile'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True,
                        help='Output generated Python module; keep outside public Git')
    parser.add_argument('--steps', type=int, default=1200)
    parser.add_argument('--tick-period', type=int, default=11)
    args = parser.parse_args(argv)
    if not 1 <= args.steps <= 50000 or args.tick_period < 0:
        parser.error('invalid bounded replay')
    receipt, path = compile_file(args.rom, args.out, max_steps=max(1000,args.steps),tick_period=args.tick_period)
    result = check(args.rom, args.out, steps=args.steps,tick_period=args.tick_period)
    report = args.out.with_suffix('.verification.json')
    report.write_text(json.dumps(result,indent=2,sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'rom':str(args.rom),'generated':str(args.out),
                      'candidate_receipt':str(path),'verification':str(report),
                      'status':result['status'],'matched_steps':result.get('compared_steps'),
                      'specialized_steps':result.get('specialized_steps'),
                      'fallback_steps':result.get('original_backed_steps')},sort_keys=True))
    return 0 if result['status']=='passed' else 1


if __name__ == '__main__': raise SystemExit(main())