#!/usr/bin/env python3
"""Run a registered Shadowrun component conformance cartridge in FCEUmm.

This qualifies the UIL-to-6502 edge. Controlled original-68000 comparisons are
recorded by the separate source-component checks; this is not game progression.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.shadowrun_replay import _json, _new_private_directory, _read
from fdisbull.shadowrun_systems import export_system, build_system_check

CORE_SHA = '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compare(trace, expected):
    watch = expected['watch']
    seen = {}
    complete = False
    current = -1
    for row in trace['frames']:
        data = bytes.fromhex(row['raw']['publication'])
        if len(data) != 4 + 4 * len(watch):
            raise ValueError('Native publication has wrong size')
        if data[3] not in (0x53, 0x57) or data[0] & 1:
            continue
        index = int.from_bytes(data[1:3], 'little')
        if index >= len(expected['reference_results']):
            raise ValueError('Native case index outside contract')
        if data[0] != (2 * (index + 1)) % 256:
            raise AssertionError('Native publication sequence differs from case index')
        if index not in (current, current + 1) or complete and (index != current or data[3] != 0x57):
            raise AssertionError('Native cases are out of order or follow completion')
        current = index
        values = {name: int.from_bytes(data[4+4*i:8+4*i], 'little')
                  for i, name in enumerate(watch)}
        want = {k: v & 0xffffffff for k, v in expected['reference_results'][index].items()}
        if values != want:
            raise AssertionError(f'NES/UIL mismatch in case {index}: {values} != {want}')
        if index in seen and seen[index] != values:
            raise AssertionError('Repeated native case publication changed')
        seen[index] = values
        if data[3] == 0x57:
            if index != len(expected['reference_results']) - 1 or len(seen) != len(expected['reference_results']):
                raise AssertionError('Completion marker preceded final case')
            complete = True
    if not complete or set(seen) != set(range(len(expected['reference_results']))):
        raise AssertionError('Native execution did not publish every case and completion')
    return {'cases': len(seen), 'differences': 0, 'completed': True}


def main():
    verifier_hash = sha(Path(__file__).read_bytes())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True)
    parser.add_argument('--core', required=True)
    parser.add_argument('--rom', required=True, help='Exact private original Genesis cartridge')
    parser.add_argument('--cases', required=True, help='Caller-selected scalar case document')
    parser.add_argument('--cc65-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build = Path(args.build).resolve()
    expected, expected_raw = _json(build / 'check.json')
    if expected.get('format') != 'fdisbull-shadowrun-system-nes-check-1':
        raise ValueError('Expected registered NES component check')
    core = Path(args.core).resolve()
    rom = build / 'check.nes'
    rom_hash = sha(_read(rom, 40976, exact=40976))
    if rom_hash != expected['cartridge_sha256'] or sha(core.read_bytes()) != CORE_SHA:
        raise ValueError('Cartridge or pinned core identity mismatch')
    out = _new_private_directory(args.output)
    out.mkdir(mode=0o700)
    # Recreate the source lift, expected values and executable. Receipt labels
    # alone cannot establish which program produced a private cartridge.
    export_system(args.rom, system=expected['system'], output=out / 'fresh-source')
    fresh = build_system_check(out / 'fresh-source/manifest.json', rom_path=args.rom,
                               procedure=expected['procedure'], cases_path=args.cases,
                               cc65_root=args.cc65_root, output=out / 'fresh-build')
    for key in ('system', 'procedure', 'source_sha256', 'program_sha256', 'case_document_sha256',
                'cartridge_sha256', 'watch', 'reference_results', 'publication'):
        if expected.get(key) != fresh[key]:
            raise AssertionError('Recorded check disagrees with a fresh source build: ' + key)
    (out / 'watch.json').write_text(json.dumps([
        {'name': 'publication', 'offset': 0x700, 'length': expected['publication']['length']}]))
    host = ROOT / 'scripts/check_console_udc.py'
    host_hash = sha(host.read_bytes())
    run = subprocess.run([sys.executable, str(host), '--core', str(core), '--rom', str(rom),
                          '--system', 'nes', '--frames', str(180 + len(expected['reference_results']) * 4),
                          '--watch', str(out / 'watch.json'), '--output', str(out / 'native')],
                         capture_output=True, text=True, timeout=180)
    (out / 'run.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError('Native NES component execution failed: ' + run.stderr[-2500:])
    receipt, _ = _json(out / 'native/receipt.json')
    trace_raw = _read(out / 'native/ram_trace.json', 16 * 1024 * 1024)
    if (receipt['rom_sha256'] != rom_hash or receipt['core_sha256'] != CORE_SHA or
            receipt['ram_trace_sha256'] != sha(trace_raw) or receipt.get('patches') or
            sha(host.read_bytes()) != host_hash or sha(rom.read_bytes()) != rom_hash or
            sha(core.read_bytes()) != CORE_SHA):
        raise AssertionError('Native witness provenance or immutability failed')
    result = compare(json.loads(trace_raw), fresh)
    if sha(Path(__file__).read_bytes()) != verifier_hash:
        raise AssertionError('Native comparison script changed during execution')
    result.update({'format': 'fdisbull-shadowrun-system-nes-comparison-1',
                   'system': expected['system'], 'procedure': expected['procedure'],
                   'program_sha256': expected['program_sha256'], 'cartridge_sha256': rom_hash,
                   'core_sha256': CORE_SHA, 'trace_sha256': sha(trace_raw),
                   'build_receipt_sha256': sha(expected_raw), 'host_sha256': host_hash,
                   'fresh_build_sha256': sha((out / 'fresh-build/check.json').read_bytes()),
                   'verifier_sha256': verifier_hash,
                   'claim': 'finite actual NES 6502 outputs match UIL; source fidelity is a separate boundary'})
    (out / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
