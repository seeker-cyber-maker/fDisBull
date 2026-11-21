#!/usr/bin/env python3
"""Apply the pinned DotBox input-control overlay to prepared DOSBox-X source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_overlay(source: Path, *, check: bool = False) -> dict:
    source = source.resolve(strict=True)
    manifest = json.loads((HERE / 'manifest.json').read_text())
    patch = HERE / 'input-control.patch'
    if _digest(patch) != manifest['overlay_sha256']:
        raise ValueError('Native overlay hash differs from its manifest')
    result_files = manifest['result_files']
    for name in result_files:
        path = source / name
        if any((source / parent).is_symlink() for parent in path.relative_to(source).parents if str(parent) != '.'):
            raise ValueError('Native overlay paths must not contain symlinks')
        if path.is_symlink():
            raise ValueError('Native overlay paths must not be symlinks')
    if all((source / name).is_file() and _digest(source / name) == digest
           for name, digest in result_files.items()):
        return {'status': 'already_applied', 'source': str(source),
                'protocol': 'dotbox-input-control-1'}
    for name, digest in manifest['base_files'].items():
        path = source / name
        if not path.is_file() or _digest(path) != digest:
            raise ValueError('Prepared DOSBox-X source does not match pinned base: ' + name)
    for name in set(result_files) - set(manifest['base_files']):
        if (source / name).exists():
            raise ValueError('Refusing to overwrite an existing overlay file: ' + name)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True,
                   capture_output=True, text=True)
    if check:
        return {'status': 'compatible', 'source': str(source),
                'protocol': 'dotbox-input-control-1'}
    subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True,
                   capture_output=True, text=True)
    for name, digest in result_files.items():
        if _digest(source / name) != digest:
            raise ValueError('Applied overlay did not produce expected bytes: ' + name)
    return {'status': 'applied', 'source': str(source),
            'protocol': 'dotbox-input-control-1'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='upstream source with the pinned native base patch applied')
    parser.add_argument('--check', action='store_true', help='validate without changing source')
    args = parser.parse_args()
    try:
        result = apply_overlay(args.source, check=args.check)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
