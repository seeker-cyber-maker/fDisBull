"""Registered Shadowrun semantic components and native NES conformance builds.

These components extend the recovery work; a conformance cartridge is not a
playable game. Original execution and target compilation are separate gates.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess

from .game_il import GameMachine, canonical, emit_c, validate_program
from .shadowrun_replay import _json, _new_private_directory, _read, _read_rom

FORMAT = 'fdisbull-shadowrun-system-1'
REGISTRY = {
    'inventory': ('shadowrun_inventory', 'lift_inventory'),
    'combat': ('shadowrun_combat', 'lift_combat'),
    'dialogue': ('shadowrun_dialogue', 'lift_dialogue'),
    'animation': ('shadowrun_animation', 'lift_animation_counter'),
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def catalog():
    return {'format': 'fdisbull-shadowrun-systems-1',
            'systems': list(REGISTRY), 'target': 'nes',
            'whole_game': False,
            'contract': 'reviewed source-bound procedural components; not complete game systems',
            'native_check': 'headless 6502 conformance cartridge, not gameplay',
            'unrecovered': ['complete world and scene transitions', 'field combat and enemy AI',
                            'inventory menus and item dispatch', 'dialogue command interpreter',
                            'general animation selection and presentation', 'music and sound driver',
                            'missions, Matrix, saves, endings and complete progression']}


def lift_system(rom: bytes, system: str):
    if system not in REGISTRY:
        raise ValueError('Unknown registered Shadowrun system')
    module, function = REGISTRY[system]
    result = getattr(importlib.import_module('.' + module, __package__), function)(rom)
    validate_program(result)
    return result


def export_system(rom_path, *, system, output):
    rom = _read_rom(rom_path)
    program = lift_system(rom, system)
    raw = canonical(program)
    out = _new_private_directory(output)
    out.mkdir(mode=0o700)
    (out / 'program.uil.json').write_bytes(raw)
    manifest = {'format': FORMAT, 'system': system, 'source_sha256': _sha(rom),
                'program_sha256': _sha(raw), 'whole_game': False,
                'scope': program.get('evidence', {})}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def inspect_system(path):
    path = Path(path).expanduser()
    if path.name != 'manifest.json' or path.is_symlink():
        raise ValueError('Expected a system manifest.json')
    manifest, _ = _json(path)
    if (manifest.get('format') != FORMAT or manifest.get('system') not in REGISTRY or
            manifest.get('whole_game') is not False):
        raise ValueError('Unsupported Shadowrun system bundle')
    raw = _read(path.parent / 'program.uil.json', 8 * 1024 * 1024)
    if _sha(raw) != manifest.get('program_sha256'):
        raise ValueError('System program hash mismatch')
    program, _ = _json(path.parent / 'program.uil.json')
    validate_program(program)
    return manifest


def _checked_cases(program, procedure, states, watch, *, regions=None):
    """Validate a finite scalar contract, obtaining reference results first."""
    machine = GameMachine(program, regions)
    if (not isinstance(procedure, str) or procedure not in machine.functions or
            machine.functions[procedure].decl.type.args is not None and
            # The profile exposes void functions, with no implicit host inputs.
            emit_c(program).find(procedure + '(void)') < 0):
        raise ValueError('Choose a registered zero-argument UIL procedure')
    if (not isinstance(states, list) or not 1 <= len(states) <= 512 or
            not isinstance(watch, list) or not 1 <= len(watch) <= 12 or
            len(set(watch)) != len(watch)):
        raise ValueError('Expected 1..512 cases and 1..12 distinct scalar outputs')
    types = machine.global_types
    scalar = {k: t for k, t in types.items() if isinstance(t, tuple) and len(t) == 2
              and type(t[0]) is int and t[0] in (8, 16, 32)}
    if any(type(k) is not str or k not in scalar for k in watch):
        raise ValueError('Watch names must identify scalar UIL globals')
    baseline = machine.snapshot()
    keys = sorted(states[0]) if isinstance(states[0], dict) else []
    if not keys or any(k not in scalar for k in keys):
        raise ValueError('Cases must set named scalar UIL globals')
    results = []
    for state in states:
        if not isinstance(state, dict) or sorted(state) != keys:
            raise ValueError('Every case must set the same fields')
        for name, value in state.items():
            bits, signed = scalar[name]
            lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError('Case value outside the UIL integer domain')
        machine.set_state(baseline)
        machine.set_state(state)
        machine.call(procedure)
        results.append({k: machine.snapshot()[k] for k in watch})
    return scalar, baseline, keys, results


def _probe_source(program, procedure, states, watch, *, regions=None):
    scalar, baseline, keys, results = _checked_cases(program, procedure, states, watch, regions=regions)
    # Arrays are not exposed through this finite scalar test contract.
    if any(isinstance(v, list) for v in baseline.values()):
        raise ValueError('This conformance build supports scalar component state only')
    declarations = emit_c(program)
    lines = [declarations, '#define PUB ((volatile unsigned char*)0x0700)',
             '#define STATUS (*(volatile unsigned char*)0x2002)',
             'static void wait_frame(void){while(STATUS&128U){}while(!(STATUS&128U)){} }']
    for key in keys:
        bits, signed = scalar[key]
        ctype = ('signed ' if signed else 'unsigned ') + {8: 'char', 16: 'int', 32: 'long'}[bits]
        values = ','.join(str(s[key]) + ('L' if signed else 'UL') for s in states)
        lines.append(f'static const {ctype} cases_{key}[{len(states)}]={{{values}}};')
    lines += ['void main(void){unsigned int i;unsigned long value;',
              '*(volatile unsigned char*)0x2000=0;*(volatile unsigned char*)0x2001=0;',
              'PUB[0]=0;PUB[1]=0;PUB[2]=0;PUB[3]=0;', f'for(i=0;i<{len(states)}U;i++){{',
              'wait_frame();PUB[0]++;']
    for key, value in baseline.items():
        lines.append(f'{key}={value}L;')
    for key in keys:
        lines.append(f'{key}=cases_{key}[i];')
    lines += [f'{procedure}();', 'PUB[1]=(unsigned char)i;PUB[2]=(unsigned char)(i>>8);']
    for index, key in enumerate(watch):
        lines.append(f'value=(unsigned long){key};')
        for byte in range(4):
            lines.append(f'PUB[{4+4*index+byte}]=(unsigned char)(value>>{8*byte});')
    lines += ['PUB[3]=0x53;PUB[0]++;}', 'PUB[3]=0x57;for(;;){} }']
    return '\n'.join(lines) + '\n', results


def build_system_check(manifest_path, *, rom_path, procedure, cases_path,
                       cc65_root, output):
    """Compile registered semantics and finite scalar cases to a real NES ROM.

    The reference is the UIL interpreter. Agreement with original 68000 code
    must be checked separately, using the component's source-bound probe.
    """
    builder_hash = _sha(Path(__file__).read_bytes())
    manifest = inspect_system(manifest_path)
    rom = _read_rom(rom_path)
    program = lift_system(rom, manifest['system'])
    if (_sha(rom) != manifest.get('source_sha256') or
            _sha(canonical(program)) != manifest['program_sha256']):
        raise ValueError('System must match a fresh registered source lift')
    contract, contract_raw = _json(Path(cases_path))
    if set(contract) != {'states', 'watch'}:
        raise ValueError('Case document requires states and watch only')
    source, results = _probe_source(program, procedure, contract['states'], contract['watch'], regions={0: rom})
    root = Path(cc65_root).expanduser().resolve()
    paths = [root / 'bin' / n for n in ('cl65', 'cc65', 'ca65', 'ld65')]
    paths += [root / 'cfg' / 'nes.cfg', root / 'lib' / 'nes.lib']
    if not all(p.is_file() for p in paths):
        raise ValueError('Expected an explicitly prepared cc65 NES toolchain')
    tools = {str(p.relative_to(root)): _sha(p.read_bytes()) for p in paths}
    out = _new_private_directory(output)
    out.mkdir(mode=0o700)
    (out / 'check.c').write_text(source)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CC65_', 'LD_', 'DYLD_'))}
    env['LC_ALL'] = 'C'
    run = subprocess.run([str(paths[0]), '-t', 'nes', '-Oirs', '-C', str(root / 'cfg/nes.cfg'),
                          '--lib-path', str(root / 'lib'), '-I', str(root / 'include'),
                          '-m', 'check.map', '-Ln', 'labels.txt', '-o', 'check.nes', 'check.c'],
                         cwd=out, env=env, capture_output=True, text=True, timeout=120)
    (out / 'build.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise ValueError('NES system check did not compile: ' + run.stderr[-2500:])
    image = _read(out / 'check.nes', 16 + 32768 + 8192, exact=16 + 32768 + 8192)
    if image[:6] != b'NES\x1a\x02\x01':
        raise ValueError('Unexpected NES conformance cartridge layout')
    if any(_sha(p.read_bytes()) != tools[str(p.relative_to(root))] for p in paths):
        raise ValueError('Toolchain changed during compilation')
    if _sha(canonical(lift_system(rom, manifest['system']))) != manifest['program_sha256']:
        raise ValueError('Registered source changed during compilation')
    if _sha(Path(__file__).read_bytes()) != builder_hash:
        raise ValueError('Component builder changed during compilation')
    receipt = {'format': 'fdisbull-shadowrun-system-nes-check-1', 'system': manifest['system'],
               'procedure': procedure, 'source_sha256': _sha(rom),
               'program_sha256': manifest['program_sha256'], 'case_document_sha256': _sha(contract_raw),
               'harness_sha256': _sha(source.encode()), 'builder_sha256': builder_hash,
               'cartridge_sha256': _sha(image), 'toolchain_sha256': tools,
               'watch': contract['watch'], 'reference_results': results,
               'publication': {'offset': 0x700, 'length': 4 + 4 * len(contract['watch']),
                               'sequence': 0, 'case_index_le': [1, 2],
                               'marker': {'offset': 3, 'running': 0x53, 'complete': 0x57},
                               'outputs': 'four little-endian bytes per watched value'},
               'whole_game': False, 'native_execution_verified': False,
               'claim': 'compiled real NES conformance cartridge; native run and original-code comparison are separate'}
    (out / 'check.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
