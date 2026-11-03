#!/usr/bin/env python3
"""Compare two real Capstone native libraries across all 16-bit SH-2 words.

Pass directories containing the platform's expected libcapstone filename, for
example: python scripts/check_capstone_sh_profile.py --original DIR --patched DIR
Uses this Python environment's Capstone binding; subprocesses isolate libraries.
The corrected source build must be supplied separately; no installation occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fdisbull.rom_asm_capstone import _outside_sh2_profile

PATCH = ROOT / "patches/capstone-5.0.9-sh-profile-gating.patch"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def child():
    import capstone
    library = Path(capstone._cs._name).resolve()
    expected = Path(os.environ['FDISBULL_EXPECTED_LIBRARY_DIR']).resolve()
    if library.parent != expected:
        raise RuntimeError('Capstone did not load the requested library directory')
    decoder = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    facts = {}
    for word in range(65536):
        item = next(decoder.disasm(word.to_bytes(2, 'big'), 0, count=1), None)
        if item is not None:
            facts[f'{word:04x}'] = [item.mnemonic, item.op_str]
    extension = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2A | capstone.CS_MODE_BIG_ENDIAN)
    control = next(extension.disasm(bytes.fromhex('027b0009'), 0, count=1), None)
    print(json.dumps({'library_sha256': digest(library.read_bytes()), 'facts': facts,
                      'sh2a_control': [control.mnemonic, control.op_str] if control else None}, sort_keys=True))


def read_library(directory: Path) -> dict:
    environment = os.environ.copy()
    environment['LIBCAPSTONE_PATH'] = str(directory.resolve())
    environment['FDISBULL_EXPECTED_LIBRARY_DIR'] = str(directory.resolve())
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'],
                            env=environment, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path)
    parser.add_argument('--patched', type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child()
        return
    if not args.original or not args.patched:
        parser.error('--original and --patched are required')
    original = read_library(args.original)
    patched = read_library(args.patched)
    left, right = original['facts'], patched['facts']
    removed = set(left) - set(right)
    added = set(right) - set(left)
    changed = {key for key in set(left) & set(right) if left[key] != right[key]}
    guarded = {f'{word:04x}' for word in range(65536) if _outside_sh2_profile(word)}
    summary = {'words_tested': 65536, 'original_library_sha256': original['library_sha256'],
               'patched_library_sha256': patched['library_sha256'], 'source_patch_sha256': digest(PATCH.read_bytes()),
               'original_decoded': len(left), 'patched_decoded': len(right),
               'removed': len(removed), 'added': len(added), 'changed': len(changed),
               'guard_missing': len(removed - guarded), 'guard_extra': len(guarded - removed),
               'original_sh2a_control': original['sh2a_control'], 'patched_sh2a_control': patched['sh2a_control'],
               'removed_words_sha256': digest(('\n'.join(sorted(removed)) + '\n').encode())}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if (original['library_sha256'] == patched['library_sha256'] or added or changed or
            removed != guarded or original['sh2a_control'] != ['rtv/n', 'r2'] or
            patched['sh2a_control'] != ['rtv/n', 'r2']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
