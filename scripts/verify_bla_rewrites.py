#!/usr/bin/env python3
"""Check seeded reachable rewrites, held-out binaries and frozen blind solvers.

The original C fixture defines the experiment. Generated assembly is a separate
authored transformation, followed by BLA's native post-build noise pass. All
artifacts and original evidence remain outside Git. No teaching sample runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import verify_bla_curriculum as base
from scripts.bla_reachable_rewrites import generate_assembly


def storage_decision(parent, waiver=None):
    if waiver:
        return {'mode': 'explicit_user_waiver', 'instruction': waiver}
    command = [sys.executable, str(Path.home() / '.codex/bin/storage_admit.py'),
               '--path', str(parent), '--expected-bytes', '100000000']
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return {'mode': 'admission', 'result': json.loads(result.stdout)}


def heldout_cases(seed, count=128):
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    cases = list(base.case_vectors())
    for _ in range(count):
        x, limit, old = (rng.getrandbits(64) for _ in range(3))
        cases.extend(((x, limit, old), (x, x, old)))
    return cases


def register_observation(path, cases):
    """Observe actual complete-wrapper GPR/FLAGS state separately from liveness."""
    from fdisbull.wine_arch import register_names
    cpu = base.FunctionCPU(path)
    samples = []
    for x, limit, old in cases:
        value = cpu.call(x, limit, old)
        samples.append({'x': x, 'limit': limit, 'old': old, 'value': value['value'],
            'general': {name: hex(cpu.cpu.reg_read(getattr(cpu.r, 'UC_X86_REG_' + name.upper())))
                        for name in sorted(register_names(64) - {'rip', 'rflags'})},
            'flags': hex(cpu.cpu.reg_read(cpu.r.UC_X86_REG_EFLAGS)), 'writes': value['writes']})
    return samples


def summarize_samples(baseline, candidate):
    if len(baseline) != len(candidate):
        raise ValueError('Different sample counts')
    differences = []
    for a, b in zip(baseline, candidate):
        if (a['x'], a['limit'], a['old']) != (b['x'], b['limit'], b['old']):
            raise ValueError('Different sample inputs')
        if set(a['general']) != set(b['general']):
            raise ValueError('Different register observation sets')
        differences.append({'x': a['x'], 'limit': a['limit'],
            'differing_gprs': {name: {'baseline': a['general'][name], 'rewrite': b['general'][name]}
                               for name in a['general'] if a['general'][name] != b['general'][name]},
            'flags_xor': hex(int(a['flags'], 16) ^ int(b['flags'], 16)),
            'output_and_store_equal': a['value'] == b['value'] and a['writes'] == b['writes']})
    return differences


def reachable_core_bytes(path):
    cpu = base.FunctionCPU(path)
    result = cpu.call(0, 1, base.MASK, entry='bounded_core', capture=True)
    return bytes.fromhex(''.join(event['bytes'] for event in result['events']))


def make_protocol(root, generator_hash, heldout_count):
    """Freeze generator identity before selecting unseen transformation seeds."""
    if type(heldout_count) is not int or not 1 <= heldout_count <= 8:
        raise ValueError('heldout_count must be 1..8')
    if (root / 'protocol.json').exists() or (root / 'protocol.sha256').exists():
        raise ValueError('Earlier frozen protocol must be preserved')
    nonce = os.urandom(32).hex()
    protocol = {'format': 'fdisbull-reachable-rewrite-protocol-1',
        'generator_sha256': generator_hash, 'source_sha256': base.sha(
            (ROOT / 'fixtures/behavior-curriculum/bounded_update.c').read_bytes()),
        'development_seeds': ['development-a', 'development-b'],
        'heldout_seeds': [hashlib.sha256(f'{nonce}:{i}'.encode()).hexdigest()[:32]
                          for i in range(heldout_count)],
        'input_seed': hashlib.sha256((nonce + ':input').encode()).hexdigest(),
        'levels': [1, 2, 3],
        'heldout_meaning': 'Seeds sampled after generator identity was frozen; no adaptation within this cohort',
        'observation_contract': 'Caller output/store, RSP and Win64 nonvolatile GPRs; volatile GPRs/FLAGS separately retained',
        'blind_packet': 'One held-out DLL per fresh agent; ABI and IO protocol disclosed; source/oracle/generator/other targets excluded'}
    raw = (json.dumps(protocol, indent=2) + '\n').encode()
    with (root / 'protocol.json').open('xb') as stream:
        stream.write(raw)
    with (root / 'protocol.sha256').open('x') as stream:
        stream.write(base.sha(raw) + '\n')
    return protocol


def replay_protocol(root, path, generator_hash, heldout_count):
    """Replay an already frozen cohort without sampling replacement seeds."""
    if type(heldout_count) is not int or not 1 <= heldout_count <= 8:
        raise ValueError('heldout_count must be 1..8')
    if (root / 'protocol.json').exists() or (root / 'protocol.sha256').exists():
        raise ValueError('Earlier frozen protocol must be preserved')
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError('Frozen protocol exceeds its bounded schema')
    protocol = json.loads(raw)
    if (not isinstance(protocol, dict) or protocol.get('format') != 'fdisbull-reachable-rewrite-protocol-1'
            or protocol.get('generator_sha256') != generator_hash
            or protocol.get('source_sha256') != base.sha(
                (ROOT / 'fixtures/behavior-curriculum/bounded_update.c').read_bytes())
            or protocol.get('development_seeds') != ['development-a', 'development-b']
            or protocol.get('levels') != [1, 2, 3]):
        raise ValueError('Frozen protocol does not match the source/generator contract')
    seeds = protocol.get('heldout_seeds')
    if (not isinstance(seeds, list) or len(seeds) != heldout_count or not 1 <= len(seeds) <= 8
            or any(not isinstance(s, str) or not re.fullmatch('[0-9a-f]{32}', s) for s in seeds)
            or len(set(seeds)) != len(seeds)
            or not isinstance(protocol.get('input_seed'), str)
            or not re.fullmatch('[0-9a-f]{64}', protocol['input_seed'])):
        raise ValueError('Frozen protocol has invalid or mismatched cohort seeds')
    with (root / 'protocol.json').open('xb') as stream:
        stream.write(raw)
    with (root / 'protocol.sha256').open('x') as stream:
        stream.write(base.sha(raw) + '\n')
    return protocol


def campaign(args):
    root = args.output.resolve()
    if root.exists() or not root.parent.is_dir():
        raise ValueError('Output must be new beneath an existing external parent')
    decision = storage_decision(root.parent, args.storage_waiver)
    root.mkdir()
    (root / 'tmp').mkdir()
    os.environ['FDISBULL_TARGET_STORE'] = str(root / 'objects')
    generator = ROOT / 'scripts/bla_reachable_rewrites.py'
    generator_hash = base.sha(generator.read_bytes())
    campaign_hash = base.sha(Path(__file__).read_bytes())
    tool_inputs = {name: base.sha(path.resolve().read_bytes()) for name, path in
        (('clang', args.clang), ('linker', args.linker), ('node', args.node), ('bla_cli', args.bla_cli))}
    protocol = (replay_protocol(root, args.protocol, generator_hash, args.heldout_count)
                if getattr(args, 'protocol', None) else make_protocol(root, generator_hash, args.heldout_count))
    protocol_hash = base.sha((root / 'protocol.json').read_bytes())
    source = ROOT / 'fixtures/behavior-curriculum/bounded_update.c'
    shutil.copyfile(source, root / 'original.c')
    baseline_dir = root / 'baseline'
    baseline_dir.mkdir()
    baseline = baseline_dir / 'target.dll'
    base.run_command([args.clang, '--target=x86_64-pc-windows-msvc', '-O1', '-ffreestanding',
        '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-c', root / 'original.c',
        '-o', baseline_dir / 'target.obj'], root, 'baseline-compile')

    def link(obj, path, label):
        base.run_command([args.linker, '/dll', '/noentry', '/nodefaultlib', '/machine:x64',
            '/fixed', '/opt:noref', '/opt:noicf', '/timestamp:0', '/out:' + str(path), obj], root, label)

    link(baseline_dir / 'target.obj', baseline, 'baseline-link')
    cases = heldout_cases(protocol['input_seed'])
    sample_inputs = ((0, 1, base.MASK), (1, 0, base.MASK), (base.MASK, base.MASK, 0))
    baseline_samples = register_observation(baseline, sample_inputs)
    original_core = reachable_core_bytes(baseline)
    records = []
    definitions = [(group, index, seed, level, False)
        for group, seeds in (('development', protocol['development_seeds']), ('heldout', protocol['heldout_seeds']))
        for index, seed in enumerate(seeds) for level in protocol['levels']]
    definitions.append(('negative-control', 0, protocol['heldout_seeds'][0], 3, True))
    for group, index, seed, level, mutation in definitions:
        if base.sha(generator.read_bytes()) != generator_hash:
            raise ValueError('Generator changed after held-out seed selection; cohort is invalid')
        name = f'{group}-{index}-level{level}'
        directory = root / name
        directory.mkdir()
        assembly = generate_assembly(seed, level, mutation=mutation)
        (directory / 'rewrite.s').write_text(assembly)
        obj, compiled, target = (directory / x for x in ('rewrite.obj', 'compiled.dll', 'target.dll'))
        base.run_command([args.clang, '--target=x86_64-pc-windows-msvc', '-c', directory / 'rewrite.s',
                          '-o', obj], root, name + '-assemble')
        link(obj, compiled, name + '-link')
        base.run_command([args.node, args.bla_cli, 'protect', compiled, '--intensity', 'stealth',
                          '--seed', seed, '--output', target, '--json'], root, name + '-protect')
        _, identity = base.inspect_pe(target)
        _, compiled_identity = base.inspect_pe(compiled)
        executable = lambda doc: [(s['rva'], s['raw_sha256']) for s in doc['sections'] if s['executable']]
        if executable(identity) != executable(compiled_identity):
            raise ValueError('BLA changed executable sections; re-review required')
        code = reachable_core_bytes(target)
        if code == original_core:
            raise ValueError('Rewrite did not change reachable core instructions')
        runtime = base.exercise(target, cases, mutation=mutation)
        proofs = base.core_comparison(baseline, target, mutation=mutation, evidence_dir=directory,
                                      contract={'memory_observation': 'ordered'})
        expected = 'different' if mutation else 'equivalent_under_contract'
        if any(row['proof']['status'] != expected for row in proofs):
            raise ValueError(name + ': scoped regional proof failed; retain cohort and inspect')
        # Widened observations must stay separate from the ABI projection.
        from fdisbull.wine_arch import register_names
        all_gprs = base.core_comparison(baseline, target,
            contract={'memory_observation': 'ordered',
                      'live_registers': sorted(register_names(64) - {'rip', 'rflags'})})
        flags = base.core_comparison(baseline, target,
            contract={'memory_observation': 'ordered', 'live_flags': 0xffffffff})
        defined_flags = base.core_comparison(baseline, target,
            contract={'memory_observation': 'ordered', 'live_flags': 0x8c5})  # CF/PF/ZF/SF/OF.
        records.append({'name': name, 'group': group, 'seed': seed, 'level': level, 'mutation': mutation,
            'assembly_sha256': base.sha(assembly.encode()), 'target': identity,
            'reachable_core_sha256': base.sha(code), 'reachable_core_changed': True,
            'postbuild_executable_sections_identical': True, 'runtime': runtime,
            'regions': proofs, 'all_gpr_projection': [x['proof'] for x in all_gprs],
            'all_flags_projection': [x['proof'] for x in flags],
            'flags_projection_without_undefined_af': [x['proof'] for x in defined_flags],
            'sampled_architectural_differences': summarize_samples(baseline_samples,
                register_observation(target, sample_inputs)),
            'fdisbull': base.analyze(target, directory / 'target.fdb')})
    baseline_record = {'target': base.inspect_pe(baseline)[1], 'runtime': base.exercise(baseline, cases),
        'fdisbull': base.analyze(baseline, baseline_dir / 'target.fdb')}
    if (base.sha(generator.read_bytes()) != generator_hash
            or base.sha(Path(__file__).read_bytes()) != campaign_hash
            or base.sha(source.read_bytes()) != protocol['source_sha256']
            or base.sha((root / 'original.c').read_bytes()) != protocol['source_sha256']
            or base.sha((root / 'protocol.json').read_bytes()) != protocol_hash):
        raise ValueError('Campaign inputs changed after cohort freeze; no qualified report')
    for name, path in (('clang', args.clang), ('linker', args.linker), ('node', args.node), ('bla_cli', args.bla_cli)):
        if base.sha(path.resolve().read_bytes()) != tool_inputs[name]:
            raise ValueError('Tool identity changed during campaign')
    report = {'format': 'fdisbull-reachable-rewrite-campaign-1', 'storage': decision,
        'campaign_script_sha256': campaign_hash,
        'generator_sha256': generator_hash, 'protocol_sha256': protocol_hash,
        'protocol_replayed': bool(getattr(args, 'protocol', None)),
        'cases_sha256': base.sha(json.dumps(cases).encode()), 'cases_per_target': len(cases),
        'baseline': baseline_record, 'records': records,
        'tools': {name: {'sha256': base.sha(path.resolve().read_bytes()),
                        'version': subprocess.check_output([path, '--version'], text=True).strip()}
                  for name, path in (('clang', args.clang), ('linker', args.linker), ('node', args.node))},
        'bla_cli_sha256': base.sha(args.bla_cli.read_bytes()),
        'commands_sha256': base.sha((root / 'commands.jsonl').read_bytes()),
        'limits': ['CPU emulation and captured-path proofs; native Windows/Wine loader behavior unqualified',
                   'Authored assembly transformations are distinct from the BLA post-build noise pass',
                   'Caller output must be valid and disjoint from DLL image/active stack',
                   'Volatile GPRs and FLAGS are not ABI outputs; their widened comparisons are reported separately',
                   'Held-out transformation seeds do not establish unseen algorithm or training generalization']}
    (root / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def grade_solver(solver, output, seed, *, cases=None):
    """Grade a frozen standalone solver without target, source, network or credentials."""
    from scripts.bla_blind_recovery import sandbox_profile
    vectors = cases if cases is not None else heldout_cases(seed, count=1000)
    if not vectors:
        raise ValueError('A nonempty grading cohort is required')
    for row in vectors:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError('Grading inputs must be unsigned triples')
        base.oracle(*row)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Grade output must be new beneath an existing parent')
    output.mkdir()
    (output / 'tmp').mkdir()
    frozen = solver.read_bytes()
    (output / 'solver.py').write_bytes(frozen)
    # The grader workspace holds no binary, oracle, source or expected-output file.
    profile = sandbox_profile(output, Path(sys.prefix), readonly=[output / 'solver.py'])
    (output / 'grader.sb').write_text(profile)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(output), 'TMPDIR': str(output / 'tmp'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    stdin = ''.join(json.dumps(row) + '\n' for row in vectors)
    result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(output / 'grader.sb'),
        sys.executable, '-I', str(output / 'solver.py')], input=stdin, text=True,
        cwd=output, env=env, capture_output=True, timeout=20)
    (output / 'stdout.txt').write_text(result.stdout)
    (output / 'stderr.txt').write_text(result.stderr)
    rows = result.stdout.splitlines()
    failures = []
    if result.returncode or len(rows) != len(vectors):
        failures.append({'kind': 'process_or_row_count', 'exit': result.returncode,
                         'actual_rows': len(rows), 'expected_rows': len(vectors)})
    else:
        for index, (line, (x, limit, old)) in enumerate(zip(rows, vectors)):
            try:
                observed = json.loads(line)
                valid = (isinstance(observed, dict) and set(observed) == {'value', 'writes'}
                    and type(observed['value']) is int and type(observed['writes']) is int
                    and observed['value'] == base.oracle(x, limit, old)
                    and observed['writes'] == int(x <= limit))
            except (ValueError, TypeError):
                valid = False
            if not valid:
                failures.append({'case': index, 'kind': 'recovered_effect_contract_mismatch'})
    report = {'format': 'fdisbull-blind-recovery-grade-1', 'solver_sha256': base.sha(frozen),
        'cases': len(vectors), 'passed': not failures, 'failures': failures,
        'cases_sha256': base.sha(json.dumps(vectors).encode()), 'seed_commitment': base.sha(seed.encode()),
        'execution': 'Frozen standalone Python in source/target/network-denied grading workspace',
        'stdout_sha256': base.sha(result.stdout.encode()), 'stderr_sha256': base.sha(result.stderr.encode())}
    (output / 'grade.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('campaign')
    build.add_argument('--output', type=Path, required=True)
    for tool in ('clang', 'linker', 'node', 'bla-cli'):
        # lld selects its flavor from argv[0]; keep the lld-link symlink name.
        build.add_argument('--' + tool, type=lambda p: Path(p).expanduser().absolute(), required=True)
    build.add_argument('--heldout-count', type=int, default=3)
    build.add_argument('--protocol', type=Path, help='Replay an unchanged frozen seed cohort')
    build.add_argument('--storage-waiver')
    grade = sub.add_parser('grade')
    grade.add_argument('--solver', type=Path, required=True)
    grade.add_argument('--output', type=Path, required=True)
    grade.add_argument('--seed', required=True)
    args = parser.parse_args()
    if args.command == 'campaign':
        report = campaign(args)
        print(json.dumps({'output': str(args.output), 'targets': len(report['records']) + 1,
                          'cases_per_target': report['cases_per_target']}))
    else:
        report = grade_solver(args.solver, args.output, args.seed)
        print(json.dumps(report))
        return 0 if report['passed'] else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
