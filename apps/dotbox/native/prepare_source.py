#!/usr/bin/env python3
"""Prepare pinned DotBox DOSBox-X source without an fDisBull installation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile


HERE = Path(__file__).resolve().parent
RECEIPT = '.dotbox-source.json'


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not relative.parts or relative.is_absolute() or '..' in relative.parts or '\\' in name:
        raise ValueError('Invalid native source path: ' + name)
    path = root.joinpath(*relative.parts)
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        raise ValueError('Native source paths must not contain symlinks: ' + name)
    return path


def _verify(root: Path, files: dict[str, str]) -> None:
    for name, expected in files.items():
        path = _path(root, name)
        if not path.is_file() or _digest(path) != expected:
            raise ValueError('Native source hash mismatch: ' + name)


def load_recipe(resource_root: Path = HERE) -> dict:
    """Validate the DotBox-owned preparation inputs before creating output."""
    recipe = json.loads((resource_root / 'build-recipe.json').read_text())
    if recipe['format'] != 'dotbox-native-source-1':
        raise ValueError('Unsupported native source recipe')
    _verify(resource_root, recipe['inputs'])
    base = json.loads((resource_root / 'dosbox-x/source-manifest.json').read_text())
    overlay = json.loads((resource_root / 'manifest.json').read_text())
    if not (base['baseline_commit'] == overlay['upstream_commit'] == recipe['upstream']['commit']):
        raise ValueError('Native source baseline identities disagree')
    if not (base['patch_sha256'] == overlay['fdisbull_patch_sha256'] ==
            recipe['inputs']['dosbox-x/headless-agent.patch'] == recipe['base_provenance']['patch_sha256']):
        raise ValueError('Native base patch identities disagree')
    if recipe['inputs']['input-control.patch'] != overlay['overlay_sha256']:
        raise ValueError('Native ownership patch identities disagree')
    expected = {entry['path']: entry['sha256'] for entry in base['source_files']}
    if any(expected.get(name) != digest for name, digest in overlay['base_files'].items()):
        raise ValueError('Native ownership base does not match native source manifest')
    expected.update(overlay['result_files'])
    if expected != recipe['result_files']:
        raise ValueError('Native result hashes disagree')
    return recipe


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(['git', *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def _identity(recipe: dict, resource_root: Path) -> dict:
    return {'format': 'dotbox-prepared-native-1',
            'recipe_sha256': _digest(resource_root / 'build-recipe.json'),
            'upstream_commit': recipe['upstream']['commit'],
            'upstream_tree': recipe['upstream']['tree'],
            'base_patch_sha256': recipe['inputs']['dosbox-x/headless-agent.patch'],
            'ownership_patch_sha256': recipe['inputs']['input-control.patch'],
            'source_files_verified': len(recipe['result_files']),
            'native_build_performed': False}


def verify_source(source: Path, *, resource_root: Path = HERE) -> dict:
    """Verify every changed source file; this does not qualify a built binary."""
    recipe = load_recipe(resource_root)
    source = source.resolve(strict=True)
    _verify(source, recipe['result_files'])
    expected = _identity(recipe, resource_root)
    receipt = _path(source, RECEIPT)
    if not receipt.is_file() or json.loads(receipt.read_text()) != expected:
        raise ValueError('Prepared native source receipt does not match this recipe')
    return dict(expected, status='verified', source=str(source))


def prepare_source(destination: Path, *, upstream: Path | None = None,
                   resource_root: Path = HERE) -> dict:
    """Export an immutable upstream commit and apply both verified source patches.

    A local Git object store permits offline preparation, even when its working
    tree is in use. Only the pinned commit is read; existing work is untouched.
    With no local store, fetch the one pinned commit into a temporary bare repo.
    """
    recipe = load_recipe(resource_root)
    destination = destination.absolute()
    if destination.is_symlink():
        raise ValueError('Native source destination must not be a symlink')
    if destination.exists():
        return dict(verify_source(destination, resource_root=resource_root), status='already_prepared')
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    with tempfile.TemporaryDirectory(prefix='.' + destination.name + '-', dir=parent) as temporary:
        stage = Path(temporary)
        repository = upstream.resolve(strict=True) if upstream else stage / 'upstream.git'
        if upstream is None:
            _git('init', '--bare', str(repository))
            _git('-C', str(repository), 'fetch', '--depth=1', '--no-tags',
                 recipe['upstream']['repository'], recipe['upstream']['commit'])
        commit = recipe['upstream']['commit']
        if (_git('rev-parse', commit + '^{commit}', cwd=repository) != commit or
                _git('rev-parse', commit + '^{tree}', cwd=repository) != recipe['upstream']['tree']):
            raise ValueError('Upstream Git source does not match the pinned commit and tree')
        archive = stage / 'upstream.tar'
        _git('archive', '--format=tar', '--output=' + str(archive), commit, cwd=repository)
        source = stage / 'source'
        source.mkdir()
        with tarfile.open(archive) as payload:
            payload.extractall(source, filter='data')
        base = json.loads((resource_root / 'dosbox-x/source-manifest.json').read_text())
        overlay = json.loads((resource_root / 'manifest.json').read_text())
        for name in ('dosbox-x/headless-agent.patch', 'input-control.patch'):
            patch = str((resource_root / name).resolve(strict=True))
            _git('apply', '--check', patch, cwd=source)
            _git('apply', patch, cwd=source)
            if name == 'dosbox-x/headless-agent.patch':
                _verify(source, {entry['path']: entry['sha256'] for entry in base['source_files']})
                _verify(source, overlay['base_files'])
        _verify(source, recipe['result_files'])
        receipt = _identity(recipe, resource_root)
        (source / RECEIPT).write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        # Rename only the newly prepared tree. Never overlay an existing output.
        if destination.exists() or destination.is_symlink():
            raise ValueError('Native source destination appeared during preparation')
        source.rename(destination)
    return dict(receipt, status='prepared', source=str(destination))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='new source directory outside the checkout')
    parser.add_argument('--upstream', type=Path,
                        help='local DOSBox-X Git repository containing the pinned commit (offline)')
    parser.add_argument('--check', action='store_true', help='verify a previously prepared tree without writes')
    args = parser.parse_args()
    try:
        result = (verify_source(args.destination) if args.check else
                  prepare_source(args.destination, upstream=args.upstream))
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or str(error)
        parser.exit(1, detail.rstrip() + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
