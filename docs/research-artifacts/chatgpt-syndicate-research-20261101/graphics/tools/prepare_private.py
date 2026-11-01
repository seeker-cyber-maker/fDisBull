"""Prepare this study's exact LE image without changing the source executable.

Usage: python prepare_private.py /owned/MAIN.EXE /new/private/directory
Requires the pinned fDisBull 0.26.0 package. No program is executed.
"""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from fdisbull.le import load_le

EXPECTED = 'bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078'

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if version('fdisbull') != '0.26.0':
        raise ValueError('Reproduction is pinned to fDisBull 0.26.0.')
    raw = args.source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Wrong MAIN.EXE identity; do not reuse these addresses.')
    root = args.destination.expanduser().absolute()
    if root.exists() or any(p.is_symlink() or (p / '.git').exists() for p in (root, *root.parents)):
        raise ValueError('Choose a new private destination outside Git and symlink ancestry.')
    image = load_le(raw)
    if {r.start for r in image.regions} != {0x10000, 0x50000, 0x70000, 0x80000}:
        raise ValueError('Unexpected mapped region set.')
    root.mkdir(parents=True, mode=0o700)
    (root / 'evidence').mkdir(mode=0o700)
    manifest = {'original_sha256': EXPECTED, 'regions': {}}
    for region in image.regions:
        target = root / f'region-{region.start:x}.bin'
        target.write_bytes(region.data)
        manifest['regions'][hex(region.start)] = {
            'size': len(region.data), 'sha256': hashlib.sha256(region.data).hexdigest()}
    (root / 'region-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'destination': str(root), 'source_sha256': EXPECTED,
                      'regions': len(image.regions), 'executed': False}))

if __name__ == '__main__':
    main()
