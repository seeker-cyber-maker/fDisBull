#!/usr/bin/env python3
"""Reproduce the static extraction and 36-target comparison for this exact input set.

This is a bounded inspection tool, not Inno Setup, innoextract, or a general
installer emulator. It never executes Windows code. Run without Python -O.
Output includes privately extracted licensed assets; do not publish that tree.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import inno_probe
import extract_verified_payloads

INPUTS = {
    'patch': 'patch_space_quest_1_-_the_sarien_encounter_2.2_galaxy_hotfix_(20261)_to_2.2_GOG_v2_(88857).exe',
    'space_quest': 'setup_space_quest_1_-_the_sarien_encounter_2.2_gog_v2_(88857).exe',
    'ultima': 'setup_ultima_iv_-_quest_of_the_avatar_1.0_cs_(28045).exe',
}
EXPECTED = {
    'patch': '7b3ae423b768c1176229ad0c43260c677de615a17f6e8cedb75509ac3fa2815c',
    'space_quest': '99dc2a147e55d49c77e0dd83084118601fb1a2e958cb06dad34a064087beeb94',
    'ultima': '0a1274103fa6cad2dc79982be6623c091e9d2489c9e4ed059deeee35ff7d31a9',
}


def prepare_headers(input_dir: Path, output_dir: Path) -> None:
    signature = b'Inno Setup Setup Data (5.6.2) (u)'
    for key, filename in INPUTS.items():
        data = (input_dir / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != EXPECTED[key]:
            raise ValueError(f'{key}: input identity differs from the inspected installer')
        candidates = []
        for match in re.finditer(re.escape(signature), data):
            offset = match.start()
            try:
                primary, next_offset = inno_probe.block(data, offset + 64)
                secondary, end = inno_probe.block(data, next_offset)
                if secondary and len(secondary) % 74 == 0:
                    candidates.append((offset, next_offset, primary, secondary))
            except (ValueError, EOFError, IndexError, inno_probe.lzma.LZMAError):
                continue
        if len(candidates) != 1:
            raise ValueError(f'{key}: expected exactly one checksum-valid header pair')
        offset, next_offset, primary, secondary = candidates[0]
        directory = output_dir / key
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'header0.bin').write_bytes(primary)
        (directory / 'header1.bin').write_bytes(secondary)
        (directory / 'offsets.json').write_text(json.dumps({'header': offset, 'header1': next_offset}))
        strings = [m.group().decode('utf-16le')
                   for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', primary)]
        (directory / 'header_strings.txt').write_text('\n'.join(strings) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error('Do not use Python -O: this probe uses assertions for integrity checks')
    if args.output_dir.exists():
        parser.error('Use a new output directory to avoid mixing evidence')
    args.output_dir.mkdir(parents=True)
    inno_probe.ROOT = extract_verified_payloads.ROOT = args.output_dir
    inno_probe.INPUT = extract_verified_payloads.INPUT = args.input_dir
    prepare_headers(args.input_dir, args.output_dir)
    inno_probe.main()
    for key in INPUTS:
        extract_verified_payloads.main(key)
    manifest = json.loads((args.output_dir / 'patch/replacement_manifest.json').read_text())
    if len(manifest) != 36 or any(row['kind'] != 'complete_zlib_replacement' for row in manifest):
        raise ValueError('Unexpected patch target set')
    comparison = []
    for row in manifest:
        patch_bytes = (args.output_dir / 'patch/payload' / row['path']).read_bytes()
        full_bytes = (args.output_dir / 'space_quest/app' / row['path']).read_bytes()
        comparison.append({'path': row['path'], 'identical_to_full_installer': patch_bytes == full_bytes})
    if not all(row['identical_to_full_installer'] for row in comparison):
        raise ValueError('A replacement differs from the full installer')
    (args.output_dir / 'patch/full_comparison.json').write_text(json.dumps(comparison, indent=2) + '\n')
    print(json.dumps({'patch_targets': len(manifest), 'identical': len(comparison), 'native_execution': False}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AssertionError) as exc:
        print(f'Static intake stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)
