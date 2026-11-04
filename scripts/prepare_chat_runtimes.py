#!/usr/bin/env python3
"""Reconstruct hash-bound guest images from one local offline base.

The immutable kit supplies every input. Only the caller's writable cache changes;
no network, package manager, compiler download or host library is used here.
"""
import argparse
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import re


MAX_EXPANDED_RUNTIME_BYTES = 6 * 1024**3


def identity(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'size': Path(path).stat().st_size}


def one(root, manifest, role):
    matches = [entry for entry in manifest['files'] if entry.get('role') == role]
    if len(matches) != 1:
        raise ValueError('Exactly one runtime input required: ' + role)
    entry = matches[0]
    name = entry['destination']
    if not isinstance(name, str) or '\\' in name or not name or any(
            part in ('', '.', '..') for part in name.split('/')) or name.startswith('/'):
        raise ValueError('Unsafe runtime input path')
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError('Unsafe or absent runtime input')
    if identity(path) != {key: entry[key] for key in ('sha256', 'size')}:
        raise ValueError('Runtime input hash/size mismatch: ' + role)
    return path


def resource_identities(dosbox):
    from fdisbull.wine_runtime import resources as wine_resources
    from fdisbull.dos_runtime import resources as dos_resources
    return {'wine': {name: identity(path)['sha256'] for name, path in wine_resources().items()},
            'dos': {name: identity(path)['sha256'] for name, path in
                    dict(dos_resources(), **{'opt/fdisbull/dosbox-x': dosbox}).items()}}


def materialize(base, cache, dosbox, expanded, *, windows_only=False):
    """Build-side measurement primitive; its result alone is not qualification."""
    from fdisbull.wine_runtime import prepare as prepare_wine
    from fdisbull.dos_runtime import prepare as prepare_dos
    if (not isinstance(expanded, dict) or type(expanded.get('size')) is not int
            or not 0 < expanded['size'] <= MAX_EXPANDED_RUNTIME_BYTES
            or not re.fullmatch('[0-9a-f]{64}', expanded.get('sha256', ''))):
        raise ValueError('Invalid expanded base identity')
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError('New runtime cache must be empty')
    # Canonical basename and empty gzip filename make reconstruction independent
    # of the receiving agent's extraction and cache paths.
    canonical = cache / 'base.cpio.gz'
    digest = hashlib.sha256(); total = 0
    with lzma.open(base, 'rb') as source, canonical.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=1) as target:
            while block := source.read(8 * 1024**2):
                total += len(block)
                if total > expanded['size']:
                    raise ValueError('Expanded runtime base exceeds declared budget')
                digest.update(block); target.write(block)
    if {'sha256': digest.hexdigest(), 'size': total} != expanded:
        raise ValueError('Expanded runtime base identity mismatch')
    prepare_wine(canonical, cache / 'wine.cpio.gz')
    if not windows_only:
        prepare_dos(canonical, cache / 'dos.cpio.gz', dosbox)
    return {profile: identity(cache / (profile + '.cpio.gz')) for profile in (('wine',) if windows_only else ('wine', 'dos'))}


def prepare(root, cache):
    root = Path(root).resolve(strict=True); cache = Path(cache).resolve()
    if cache == root or cache.is_relative_to(root) or root.is_relative_to(cache):
        raise ValueError('Runtime cache must be separate from the kit')
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    base = one(root, manifest, 'runtime_base')
    recipe = json.loads(one(root, manifest, 'runtime_recipe').read_text())
    dosbox = one(root, manifest, 'dosbox'); kernel = one(root, manifest, 'kernel')
    if recipe.get('schema') != 'fdisbull-chat-runtime-recipe-v1':
        raise ValueError('Unsupported runtime recipe')
    if recipe.get('resources') != resource_identities(dosbox):
        raise ValueError('Installed resources do not match runtime recipe')
    expected = recipe.get('outputs')
    if not isinstance(expected, dict) or set(expected) != {'wine', 'dos'}:
        raise ValueError('Both runtime identities are required')
    for value in expected.values():
        if (not isinstance(value, dict) or set(value) != {'sha256', 'size'}
                or type(value['size']) is not int or value['size'] <= 0
                or not re.fullmatch('[0-9a-f]{64}', value.get('sha256', ''))):
            raise ValueError('Invalid runtime output identity')
    receipt = cache / 'runtime-cache.json'
    if receipt.exists():
        if receipt.is_symlink() or json.loads(receipt.read_text()) != recipe:
            raise ValueError('Runtime cache belongs to another recipe')
        if any((cache / (profile + '.cpio.gz')).is_symlink() or
               not (cache / (profile + '.cpio.gz')).is_file() for profile in expected):
            raise ValueError('Runtime cache contains an unsafe image')
        actual = {profile: identity(cache / (profile + '.cpio.gz')) for profile in expected}
    else:
        actual = materialize(base, cache, dosbox, recipe.get('expanded_base'))
    if actual != expected:
        raise ValueError('Reconstructed runtime hash/size mismatch')
    if not receipt.exists():
        with receipt.open('x') as stream:
            json.dump(recipe, stream, indent=2); stream.write('\n')
    return {'wine': cache / 'wine.cpio.gz', 'dos': cache / 'dos.cpio.gz', 'kernel': kernel}


def prepare_windows(root, cache):
    """Reconstruct the separately inventoried full Windows image offline."""
    root = Path(root).resolve(strict=True); cache = Path(cache).resolve()
    if cache == root or cache.is_relative_to(root) or root.is_relative_to(cache):
        raise ValueError('Runtime cache must be separate from the kit')
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    base = one(root, manifest, 'windows_runtime_base')
    recipe = json.loads(one(root, manifest, 'windows_runtime_recipe').read_text())
    dosbox = one(root, manifest, 'dosbox')
    if recipe.get('schema') != 'fdisbull-chat-windows-recipe-v1':
        raise ValueError('Unsupported Windows runtime recipe')
    if recipe.get('resources') != resource_identities(dosbox)['wine']:
        raise ValueError('Installed Windows resources do not match recipe')
    expected = recipe.get('output')
    if (not isinstance(expected, dict) or set(expected) != {'sha256', 'size'}
            or type(expected['size']) is not int or expected['size'] <= 0
            or not re.fullmatch('[0-9a-f]{64}', expected.get('sha256', ''))):
        raise ValueError('Invalid Windows runtime output identity')
    receipt = cache / 'runtime-cache.json'
    if receipt.exists():
        if receipt.is_symlink() or json.loads(receipt.read_text()) != recipe:
            raise ValueError('Runtime cache belongs to another recipe')
        image = cache / 'wine.cpio.gz'
        if image.is_symlink() or not image.is_file():
            raise ValueError('Runtime cache contains an unsafe image')
        actual = identity(image)
    else:
        actual = materialize(base, cache, dosbox, recipe.get('expanded_base'), windows_only=True)['wine']
    if actual != expected:
        raise ValueError('Reconstructed Windows runtime hash/size mismatch')
    if not receipt.exists():
        with receipt.open('x') as stream:
            json.dump(recipe, stream, indent=2); stream.write('\n')
    return cache / 'wine.cpio.gz'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--windows', action='store_true', help='Reconstruct the full Windows runtime')
    args = parser.parse_args()
    paths = {'windows': prepare_windows(args.kit, args.cache)} if args.windows else prepare(args.kit, args.cache)
    print(json.dumps({key: str(path) for key, path in paths.items()}, indent=2))


if __name__ == '__main__':
    main()
