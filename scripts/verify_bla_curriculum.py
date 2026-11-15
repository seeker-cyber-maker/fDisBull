#!/usr/bin/env python3
"""Build and verify an authored PE curriculum with retained BLA controls.

This is a finite CPU-emulation experiment, not Windows loader qualification,
a blind recovery score, or a whole-program equivalence theorem. Outputs and
databases belong in a new external directory. No supplied teaching EXE runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys


MASK = (1 << 64) - 1
OUTPUT = 0x60000000
STACK = 0x70000000
STOP = 0x50000000
NONVOLATILE = ('rbx', 'rbp', 'rdi', 'rsi', 'r12', 'r13', 'r14', 'r15')
LEVELS = (
    ('baseline', None, None),
    ('postbuild-stealth', None, 'stealth'),
    ('anchor-stealth', 'stealth', 'stealth'),
    ('anchor-balanced', 'balanced', 'balanced'),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def oracle(x, limit, old):
    """Caller contract, independently evaluated with mathematical integers."""
    if any(type(v) is not int or not 0 <= v <= MASK for v in (x, limit, old)):
        raise ValueError('Contract inputs must be unsigned 64-bit integers')
    return old if x > limit else ((x ^ 90) + 7) % (1 << 64)


def case_vectors():
    boundaries = (0, 1, 0x59, 0x5a, 0x5b, (1 << 32) - 1,
                  1 << 32, (1 << 63) - 1, 1 << 63, MASK - 1, MASK)
    cases = [(x, limit, 0x0123456789abcdef) for x in boundaries for limit in boundaries]
    rng = random.Random(0xB1A2026)
    for _ in range(64):
        x, limit, old = (rng.getrandbits(64) for _ in range(3))
        cases.extend(((x, limit, old), (x, x, old)))
    # Same-input repetition after other calls detects some hidden state dependence.
    return cases + [(0, 0, MASK), (MASK, MASK, 0), (0, 0, MASK),
                    ((MASK - 6) ^ 0x5a, MASK, 1),  # XOR result plus 7 wraps to zero.
                    (0, 0, 97)]  # A required store whose final bytes already match.


def inspect_pe(path):
    import pefile
    raw = Path(path).read_bytes()
    pe = pefile.PE(data=raw)
    if (pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20b
            or not pe.FILE_HEADER.Characteristics & 0x2000
            or pe.OPTIONAL_HEADER.AddressOfEntryPoint != 0):
        raise ValueError('Expected an entry-free PE64 DLL')
    if getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        raise ValueError('Curriculum must not require host API imports')
    exports = {s.name.decode('ascii'): s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols
               if s.name and not s.forwarder}
    if not {'bounded_core', 'bounded_update'} <= exports.keys():
        raise ValueError('Authored function exports are missing')
    sections = []
    for section in pe.sections:
        sections.append({'name': section.Name.rstrip(b'\0').decode('ascii'),
                         'rva': section.VirtualAddress,
                         'virtual_bytes': section.Misc_VirtualSize,
                         'raw_bytes': section.SizeOfRawData,
                         'executable': bool(section.Characteristics & 0x20000000),
                         'writable': bool(section.Characteristics & 0x80000000),
                         'raw_sha256': sha(section.get_data())})
    result = {'sha256': sha(raw), 'bytes': len(raw), 'exports': exports,
              'image_base': pe.OPTIONAL_HEADER.ImageBase,
              'image_bytes': pe.OPTIONAL_HEADER.SizeOfImage, 'sections': sections}
    return pe, result


class FunctionCPU:
    """Execute the complete wrapper without substituting BLA calls or writes."""
    def __init__(self, path):
        import unicorn as u
        from unicorn import x86_const as r
        self.u, self.r = u, r
        self.pe, self.identity = inspect_pe(path)
        self.cpu = u.Uc(u.UC_ARCH_X86, u.UC_MODE_64)
        self.base = self.identity['image_base']
        self.cpu.mem_map(self.base, (self.identity['image_bytes'] + 4095) & ~4095)
        self.cpu.mem_write(self.base, self.pe.get_memory_mapped_image())
        self.cpu.mem_map(STACK, 0x10000)
        self.cpu.mem_map(OUTPUT, 4096)
        self.cpu.mem_map(STOP, 4096)
        self.cpu.mem_write(STOP, b'\x90')
        self.writes = []
        self.cpu.hook_add(u.UC_HOOK_MEM_WRITE, self._write)

    def _write(self, cpu, access, address, size, value, data):
        self.writes.append((address, size))

    def call(self, x, limit, old, *, entry='bounded_update', capture=False):
        from fdisbull.wine_arch import register_names
        cpu, r = self.cpu, self.r
        for name in register_names(64) - {'rip', 'rflags'}:
            cpu.reg_write(getattr(r, 'UC_X86_REG_' + name.upper()), 0)
        saved = {name: 0x1122334400000000 + index for index, name in enumerate(NONVOLATILE)}
        for name, value in saved.items():
            cpu.reg_write(getattr(r, 'UC_X86_REG_' + name.upper()), value)
        sp = STACK + 0x8008  # Win64 entry: RSP % 16 == 8, with caller shadow space.
        cpu.mem_write(sp, struct.pack('<Q', STOP))
        before = b'\xa5' * 8 + struct.pack('<Q', old) + b'\x5a' * 8
        cpu.mem_write(OUTPUT, before)
        for name, value in (('rcx', x), ('rdx', limit), ('r8', OUTPUT + 8), ('rsp', sp)):
            cpu.reg_write(getattr(r, 'UC_X86_REG_' + name.upper()), value)
        cpu.reg_write(r.UC_X86_REG_EFLAGS, 0x202)
        self.writes = []
        events = []

        def trace(guest, address, size, _):
            events.append({'address': hex(address), 'project_address': hex(address),
                'bytes': bytes(guest.mem_read(address, size)).hex(),
                'registers': {'rip': hex(address), 'rflags': hex(guest.reg_read(r.UC_X86_REG_EFLAGS)),
                    'thread': 1, 'general': {name: hex(guest.reg_read(getattr(
                        r, 'UC_X86_REG_' + name.upper())))
                        for name in sorted(register_names(64) - {'rip', 'rflags'})}}})
        hook = cpu.hook_add(self.u.UC_HOOK_CODE, trace) if capture else None
        try:
            cpu.emu_start(self.base + self.identity['exports'][entry], STOP, count=10000)
        finally:
            if hook is not None:
                cpu.hook_del(hook)
        if cpu.reg_read(r.UC_X86_REG_RIP) != STOP:
            raise ValueError('Function did not return within 10000 instructions')
        if cpu.reg_read(r.UC_X86_REG_RSP) != sp + 8 or any(
                cpu.reg_read(getattr(r, 'UC_X86_REG_' + name.upper())) != value
                for name, value in saved.items()):
            raise ValueError('Win64 stack or nonvolatile GPR contract was violated')
        after = bytes(cpu.mem_read(OUTPUT, 24))
        if before[:8] != after[:8] or before[16:] != after[16:]:
            raise ValueError('Output canary was modified')
        effects = {'output': 0, 'stack': 0, 'image': 0}
        image_writes = set()
        for address, size in self.writes:
            if OUTPUT + 8 <= address and address + size <= OUTPUT + 16:
                effects['output'] += 1
            elif STACK <= address and address + size <= STACK + 0x10000:
                effects['stack'] += 1
            else:
                section = next((s for s in self.identity['sections'] if s['writable']
                    and self.base + s['rva'] <= address
                    and address + size <= self.base + s['rva'] + s['virtual_bytes']), None)
                if section is None:
                    raise ValueError('Write escaped output, stack and declared writable image sections')
                effects['image'] += 1
                image_writes.update(range(address - self.base, address - self.base + size))
        return {'value': struct.unpack('<Q', after[8:16])[0], 'writes': effects,
                'image_write_rvas': sorted(image_writes), 'events': events,
                'memory': {'entry': [{'address': hex(OUTPUT + 8), 'hex': before[8:16].hex()}],
                           'exit': [{'address': hex(OUTPUT + 8), 'hex': after[8:16].hex()}]}}


def exercise(path, cases, *, mutation=False):
    cpu = FunctionCPU(path)
    mismatches, writes, image_bytes = [], {'output': 0, 'stack': 0, 'image': 0}, set()
    rejected_writes = 0
    for index, (x, limit, old) in enumerate(cases):
        observed = cpu.call(x, limit, old)
        expected = oracle(x, limit, old)
        actual_contract = old if mutation and x >= limit else expected
        expected_writes = int(x < limit if mutation else x <= limit)
        if observed['value'] != actual_contract or observed['writes']['output'] != expected_writes:
            raise ValueError('Function did not implement its declared guard/store variant')
        if observed['value'] != expected or observed['writes']['output'] != int(x <= limit):
            mismatches.append({'case': index, 'x': x, 'limit': limit, 'old': old,
                               'expected': expected, 'observed': observed['value'],
                               'expected_output_writes': int(x <= limit),
                               'observed_output_writes': observed['writes']['output']})
        rejected_writes += int(x > limit and observed['writes']['output'] != 0)
        for key in writes:
            writes[key] += observed['writes'][key]
        image_bytes.update(observed['image_write_rvas'])
    if rejected_writes or (not mutation and mismatches):
        raise ValueError('Authored caller contract failed')
    if mutation and not any(row['x'] == row['limit'] for row in mismatches):
        raise ValueError('Guard mutation did not yield an equality-boundary witness')
    return {'cases': len(cases), 'agreement': len(cases) - len(mismatches),
            'mismatches': mismatches, 'write_counts': writes,
            'image_write_rvas': sorted(image_bytes), 'rejected_output_writes': rejected_writes,
            'state_lifetime': 'One retained CPU per variant; image state persists between calls',
            'abi_check': 'Win64 nonvolatile GPRs and stack; SIMD/OS behavior unqualified'}


def analyze(path, output):
    from fdisbull.project import Project
    with Project.create(output, path) as project:
        result = project.analyze(max_instructions=20000)
        facts = {name: project.db.execute(f'SELECT count(*) FROM {name} WHERE version=1').fetchone()[0]
                 for name in ('instructions', 'functions', 'xrefs')}
        identity = project.meta['source_sha256']
        if not result['stable']:
            raise ValueError('Authored analysis did not reach its bounded fixed point')
    with Project(output) as reopened:
        if reopened.meta['source_sha256'] != identity:
            raise ValueError('Analysis restart changed source identity')
        if facts['instructions'] != reopened.db.execute(
                'SELECT count(*) FROM instructions WHERE version=1').fetchone()[0]:
            raise ValueError('Analysis restart changed instruction count')
    return {'source_sha256': identity, 'analysis': result, 'facts': facts,
            'restart_verified': True}


def core_comparison(left, right, *, mutation=False, evidence_dir=None, contract=None):
    """Contract only the real core paths, never discard the wrapper's BLA call."""
    if contract is not None and not isinstance(contract, dict):
        raise ValueError('Regional contract override must be an object')
    from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
    from fdisbull.pe_region_equivalence import compare_pe_regions, expand_pe_contraction
    reports = []
    # Align accepted with accepted, rejected with rejected. Pairing different
    # path roles can yield a domain counterexample without a function difference.
    for x, limit in ((0, 1), (1, 0)):
        samples, traces = [], []
        for path in (left, right):
            cpu = FunctionCPU(path)
            sample = cpu.call(x, limit, MASK, entry='bounded_core', capture=True)
            events = sample['events']
            # RET is the common exit boundary, not an interpreted regional instruction.
            normalize_trace('wine-qemu', events, version=1)
            trace = {'mapping': {'backend': 'wine-qemu', 'bits': 64,
                'source_sha256': cpu.identity['sha256'], 'version_sha256': cpu.identity['sha256']},
                'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'events': events}
            traces.append(trace)
            samples.append(sample)
        correspondence = [{'baseline': traces[0]['events'][index]['identity'] | {},
                           'layer': traces[1]['events'][index]['identity'] | {},
                           'evidence': 'Retained authored bounded_core export and observed return boundary'}
                          for index in (0, -1)]
        for row in correspondence:
            for side in ('baseline', 'layer'):
                row[side] = {key: row[side][key] for key in ('source_version', 'context', 'project_address')}
        regional_contract = {'live_registers': ['rsp', *NONVOLATILE], 'live_flags': 0,
                      'entry_registers': {'r8': hex(OUTPUT + 8)},
                      'memory_ranges': [{'address': hex(OUTPUT + 8), 'length': 8}],
                      'memory_model': 'private_ordinary_ram', 'memory_observation': 'final'}
        regional_contract.update(contract or {})
        result = compare_pe_regions(*traces, correspondence=correspondence, contract=regional_contract,
            baseline_memory=samples[0]['memory'], layer_memory=samples[1]['memory'], timeout_ms=5000)
        if result['contraction']:
            expanded = expand_pe_contraction(result['contraction'], *traces,
                baseline_memory=samples[0]['memory'], layer_memory=samples[1]['memory'])
            if expanded != {'baseline': traces[0], 'layer': traces[1],
                            'baseline_memory': samples[0]['memory'], 'layer_memory': samples[1]['memory']}:
                raise ValueError('Controlled contraction failed to restore exact traces')
        replay = None
        if mutation and result['counterexample']:
            witness = result['counterexample']
            inputs = witness['entry_general']
            wx, wl = int(inputs['rcx'], 16), int(inputs['rdx'], 16)
            old = int.from_bytes(bytes(int(witness['entry_memory'][hex(OUTPUT + 8 + i)], 16)
                                       for i in range(8)), 'little')
            a, b = (FunctionCPU(path).call(wx, wl, old) for path in (left, right))
            replay = {'x': wx, 'limit': wl, 'old': old, 'baseline': a['value'],
                      'mutation': b['value'], 'baseline_output_writes': a['writes']['output'],
                      'mutation_output_writes': b['writes']['output'],
                      'scope': 'Solver input/output-memory projection replayed on complete wrappers in Unicorn'}
            if wx != wl or (a['value'] == b['value'] and a['writes']['output'] == b['writes']['output']):
                raise ValueError('Guard counterexample did not replay as a boundary effect difference')
        evidence_file, evidence_sha256 = None, None
        if evidence_dir is not None:
            evidence_file = 'core-accepted.json' if x <= limit else 'core-rejected.json'
            raw = (json.dumps({'capture_engine': 'Unicorn', 'baseline': traces[0], 'layer': traces[1],
                'baseline_memory': samples[0]['memory'], 'layer_memory': samples[1]['memory']},
                sort_keys=True, indent=2) + '\n').encode()
            (evidence_dir / evidence_file).write_bytes(raw)
            evidence_sha256 = sha(raw)
        reports.append({'sample': {'x': x, 'limit': limit}, 'proof': result,
                        'capture_engine': 'Unicorn 2, normalized to PE completed-step schema',
                        'contraction_expansion_verified': result['contraction'] is not None,
                        'witness_replay': replay, 'evidence_file': evidence_file,
                        'evidence_sha256': evidence_sha256})
    return reports


def run_command(argv, root, log_name):
    env = os.environ.copy()
    env['TMPDIR'] = str(root / 'tmp')
    result = subprocess.run([str(x) for x in argv], cwd=root, env=env,
                            capture_output=True, timeout=60)
    (root / (log_name + '.stdout')).write_bytes(result.stdout)
    (root / (log_name + '.stderr')).write_bytes(result.stderr)
    record = {'argv': [str(x) for x in argv], 'exit': result.returncode,
              'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr)}
    with (root / 'commands.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    if result.returncode:
        raise ValueError(f'{log_name} failed; retained command logs contain diagnostics')
    return record


def campaign(args):
    root = args.output.resolve()
    if root.exists() or not root.parent.is_dir():
        raise ValueError('Output must be a new directory under an existing external parent')
    admission = Path.home() / '.codex/bin/storage_admit.py'
    subprocess.run([sys.executable, str(admission), '--path', str(root.parent),
                    '--expected-bytes', '50000000'], check=True)
    root.mkdir()
    (root / 'tmp').mkdir()
    os.environ['FDISBULL_TARGET_STORE'] = str(root / 'objects')
    source = Path(__file__).resolve().parents[1] / 'fixtures/behavior-curriculum/bounded_update.c'
    shutil.copyfile(source, root / source.name)
    package = json.loads((args.bla_cli.parent.parent / 'package.json').read_text())
    if package.get('name') != 'bla-agents' or package.get('version') != '3.2.4':
        raise ValueError('This curriculum was reviewed for BLA 3.2.4')
    dist = sorted(args.bla_cli.parent.rglob('*.js'))
    tool_inputs = [{'path': str(p.relative_to(args.bla_cli.parent)), 'sha256': sha(p.read_bytes())}
                   for p in dist]
    tools = {'bla_package': {k: package[k] for k in ('name', 'version', 'engines')},
             'bla_cli_sha256': sha(args.bla_cli.read_bytes()),
             'bla_dist_js_sha256': sha(json.dumps(tool_inputs, sort_keys=True).encode()),
             'executable_sha256': {name: sha(path.resolve().read_bytes()) for name, path in
                                   (('node', args.node), ('clang', args.clang), ('linker', args.linker))},
             'versions': {}}
    for name, command in (('node', [args.node, '--version']),
                          ('clang', [args.clang, '--version']), ('linker', [args.linker, '--version'])):
        tools['versions'][name] = subprocess.check_output(command, text=True).strip()
    cases = case_vectors()
    records = []
    for name, header, post in LEVELS[:args.max_level + 1] + (('guard-mutation', None, None),):
        directory = root / name
        directory.mkdir()
        defines = []
        if header:
            run_command([args.node, args.bla_cli, 'emit-headers', '--lang', 'c', '--intensity', header,
                         '--seed', args.seed, '--output', directory / 'bla_shield.h', '--json'],
                        root, name + '-header')
            defines.append('-DBLA_PROTECTED')
        if name == 'guard-mutation':
            defines.append('-DGUARD_MUTATION')
        obj, compiled, target = directory / 'target.obj', directory / 'compiled.dll', directory / 'target.dll'
        run_command([args.clang, '--target=x86_64-pc-windows-msvc', '-O1', '-ffreestanding',
                     '-fno-stack-protector', '-fno-asynchronous-unwind-tables', *defines,
                     '-I', directory, '-c', root / source.name, '-o', obj], root, name + '-compile')
        run_command([args.linker, '/dll', '/noentry', '/nodefaultlib', '/machine:x64', '/fixed',
                     '/opt:noref', '/opt:noicf', '/timestamp:0', '/out:' + str(compiled), obj],
                    root, name + '-link')
        if post:
            run_command([args.node, args.bla_cli, 'protect', compiled, '--intensity', post,
                         '--seed', args.seed, '--output', target, '--json'], root, name + '-protect')
        else:
            shutil.copyfile(compiled, target)
        _, identity = inspect_pe(target)
        _, compile_identity = inspect_pe(compiled)
        text = lambda doc: [s['raw_sha256'] for s in doc['sections'] if s['executable']]
        if text(identity) != text(compile_identity):
            raise ValueError('Post-build protection changed executable sections; re-review needed')
        record = {'level': name, 'header_intensity': header, 'postbuild_intensity': post,
                  'seed': args.seed, 'target': identity, 'compiled': compile_identity,
                  'postbuild_executable_sections_identical': True,
                  'runtime': exercise(target, cases, mutation=name == 'guard-mutation'),
                  'fdisbull': analyze(target, directory / 'target.fdb')}
        if header:
            record['header_sha256'] = sha((directory / 'bla_shield.h').read_bytes())
        expected_image_writes = 4 * len(cases) if header else 0
        if record['runtime']['write_counts']['image'] != expected_image_writes:
            raise ValueError('Generated anchor execution did not match its four-write control')
        record['core_regions'] = core_comparison(root / 'baseline/target.dll', target,
                                                mutation=name == 'guard-mutation', evidence_dir=directory)
        expected_status = 'different' if name == 'guard-mutation' else 'equivalent_under_contract'
        if any(row['proof']['status'] != expected_status for row in record['core_regions']):
            raise ValueError(f'{name}: regional proof did not establish expected {expected_status}; re-review needed')
        records.append(record)
    report = {'format': 'fdisbull-authored-bla-curriculum-1', 'tools': tools,
        'campaign_script_sha256': sha(Path(__file__).read_bytes()),
        'source_sha256': sha(source.read_bytes()), 'cases_sha256': sha(json.dumps(cases).encode()),
        'commands_sha256': sha((root / 'commands.jsonl').read_bytes()),
        'contract': 'If unsigned x<=limit store ((x XOR 90)+7) modulo 2^64; otherwise leave out untouched',
        'records': records,
        'limits': ['Finite Unicorn direct-function calls with caller output disjoint from DLL and active stack, not native Windows or loader qualification',
                   'BLA heap writes and scratch stack writes are retained and measured; whole-memory equality is not claimed',
                   'Core proofs cover the captured accepted/rejected paths under declared live-state/RAM contracts',
                   'This is a known-answer calibration corpus, not a blind recovery score or evidence of training improvement',
                   'BLA native postprocessing adds noise; intensity is not a measured semantic difficulty scale']}
    (root / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bla-cli', type=lambda x: Path(x).resolve(), required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--linker', type=Path, required=True)
    parser.add_argument('--seed', default='fdisbull-known-target-v1')
    parser.add_argument('--max-level', type=int, choices=range(4), default=3)
    args = parser.parse_args()
    try:
        report = campaign(args)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Curriculum not qualified: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'output': str(args.output), 'levels': len(report['records']),
                      'status': 'finite_verification_complete'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
