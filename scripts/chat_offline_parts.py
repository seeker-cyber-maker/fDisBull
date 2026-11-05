#!/usr/bin/env python3
"""Split or reconstruct one hash-bound offline-kit ZIP without network access."""
import argparse
import hashlib
import json
from pathlib import Path

MAX_ARCHIVE = 2_000_000_000
MAX_PART = 250_000_000
BLOCK = 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while data := f.read(BLOCK):
            h.update(data)
    return h.hexdigest()


def split(archive, directory, chunk_size=MAX_PART):
    archive, directory = Path(archive), Path(directory)
    if archive.is_symlink() or not archive.is_file() or not 0 < archive.stat().st_size <= MAX_ARCHIVE:
        raise ValueError('Archive is missing, unsafe or oversized')
    if type(chunk_size) is not int or not 0 < chunk_size <= MAX_PART:
        raise ValueError('Invalid part size')
    if directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
        raise ValueError('Parts directory must be an existing empty directory')
    files = []
    whole = hashlib.sha256()
    with archive.open('rb') as source:
        remaining = archive.stat().st_size
        while remaining:
            name = f'part-{len(files) + 1:06d}'
            target = directory / name
            length = min(chunk_size, remaining)
            h = hashlib.sha256()
            with target.open('xb') as out:
                left = length
                while left:
                    data = source.read(min(BLOCK, left))
                    if not data:
                        raise ValueError('Archive changed during split')
                    out.write(data); h.update(data); whole.update(data); left -= len(data)
            files.append({'name': name, 'size': length, 'sha256': h.hexdigest()})
            remaining -= length
        if source.read(1):
            raise ValueError('Archive changed during split')
    if digest(archive) != whole.hexdigest():
        raise ValueError('Archive changed during split')
    manifest = {'schema': 'fdisbull-chat-parts-v1', 'archive_size': sum(p['size'] for p in files),
                'archive_sha256': whole.hexdigest(), 'parts': files}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def reassemble(directory, output):
    directory, output = Path(directory), Path(output)
    manifest_path = directory / 'manifest.json'
    if directory.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Missing or unsafe parts manifest')
    manifest = json.loads(manifest_path.read_text())
    parts = manifest.get('parts')
    if manifest.get('schema') != 'fdisbull-chat-parts-v1' or not isinstance(parts, list) or not parts:
        raise ValueError('Invalid parts manifest')
    if type(manifest.get('archive_size')) is not int or not 0 < manifest['archive_size'] <= MAX_ARCHIVE:
        raise ValueError('Invalid archive size')
    total = 0
    for index, part in enumerate(parts, 1):
        if (not isinstance(part, dict) or set(part) != {'name', 'size', 'sha256'}
                or part['name'] != f'part-{index:06d}' or type(part['size']) is not int
                or not 0 < part['size'] <= MAX_PART or not isinstance(part['sha256'], str)
                or len(part['sha256']) != 64 or any(c not in '0123456789abcdef' for c in part['sha256'])):
            raise ValueError('Invalid part identity')
        total += part['size']
        path = directory / part['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != part['size'] or digest(path) != part['sha256']:
            raise ValueError('Missing or changed part')
    if total != manifest['archive_size']:
        raise ValueError('Part sizes do not match archive')
    h = hashlib.sha256()
    with output.open('xb') as out:
        for part in parts:
            with (directory / part['name']).open('rb') as source:
                while data := source.read(BLOCK):
                    h.update(data); out.write(data)
    if output.stat().st_size != total or h.hexdigest() != manifest.get('archive_sha256'):
        raise ValueError('Reassembled archive identity mismatch')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    a = sub.add_parser('split'); a.add_argument('archive', type=Path); a.add_argument('directory', type=Path); a.add_argument('--chunk-size', type=int, default=MAX_PART)
    a = sub.add_parser('reassemble'); a.add_argument('directory', type=Path); a.add_argument('archive', type=Path)
    args = parser.parse_args()
    result = split(args.archive, args.directory, args.chunk_size) if args.action == 'split' else reassemble(args.directory, args.archive)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
