"""Decode a privately extracted game's RNC1 resources into a new private tree.

Usage: python decode_resources.py /private/extracted /private/work/decoded
Non-RNC files are copied unchanged. Originals are never overwritten. This is
not an installer reader. Source extraction must supply named original files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from rnc1 import unpack

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    source, destination = args.source.resolve(), args.destination.expanduser().absolute()
    if not source.is_dir():
        raise ValueError('Source must be an existing extracted directory.')
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError('Choose a new destination outside the original tree.')
    if any(p.is_symlink() or (p / '.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('Decoded resources must remain private, outside Git/symlinks.')
    destination.mkdir(parents=True, mode=0o700)
    records = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlink input refused: {path}')
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if len(raw) > 128 * 1024 * 1024:
            raise ValueError('Input exceeds this bounded study reader.')
        data, detail = unpack(raw) if raw.startswith(b'RNC\x01') else (raw, {})
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({'path': relative.as_posix(), 'stored_size': len(raw),
                        'stored_sha256': hashlib.sha256(raw).hexdigest(),
                        'decoded_size': len(data), 'decoded_sha256': hashlib.sha256(data).hexdigest(),
                        'encoding': 'RNC1' if detail else 'raw', **detail})
    (destination.parent / 'decoded-resource-identities.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'files': len(records), 'RNC1': sum(r['encoding'] == 'RNC1' for r in records)}))

if __name__ == '__main__':
    main()
