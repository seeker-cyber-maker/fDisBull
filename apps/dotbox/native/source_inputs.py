"""Resolve native build inputs from a complete delivery or the combined source.

This stdlib-only helper is included in exported kits. Deliveries contain ordinary
local files; only the exact combined-checkout layout can use the canonical base.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tomllib


SHARED_BASE_INPUTS = frozenset({
    'dosbox-x/headless-agent.patch',
    'dosbox-x/source-manifest.json',
    'dosbox-x/COPYING',
})


def _local_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (not relative.parts or relative.is_absolute() or '..' in relative.parts or
            '\\' in name or str(relative) != name):
        raise ValueError('Invalid source resource path: ' + name)
    path = Path(root).absolute().joinpath(*relative.parts)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Source resources must not contain symlinks: ' + name)
    return path


def native_input_path(native_root: Path, name: str) -> Path:
    """Find a pinned base file without maintaining another checkout copy.

    Bundled inputs always win and must still match the existing recipe. A
    damaged or symlinked local file is refused, never replaced by a fallback.
    Other native resources remain local to the product or exported kit.
    """
    native_root = Path(native_root).absolute()
    path = _local_path(native_root, name)
    if name not in SHARED_BASE_INPUTS:
        return path
    if not path.exists():
        product = native_root.parent
        repository = product.parent.parent
        project = _local_path(repository, 'pyproject.toml')
        if (native_root != repository / 'apps/dotbox/native' or
                not project.is_file() or
                tomllib.loads(project.read_text()).get('project', {}).get('name') != 'fdisbull'):
            raise ValueError('Missing bundled native source input: ' + name)
        path = _local_path(repository, 'experimental/' + name)
    recipe = json.loads(_local_path(native_root, 'build-recipe.json').read_text())
    expected = recipe.get('inputs', {}).get(name)
    if (not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected) or
            not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
        raise ValueError('Native source hash mismatch: ' + name)
    return path


def resource_path(product_root: Path, name: str) -> Path:
    """Resolve one manifest resource, retaining its standalone logical path."""
    local = _local_path(product_root, name)
    if name.startswith('native/'):
        return native_input_path(Path(product_root) / 'native', name.removeprefix('native/'))
    return local


class SourceResources:
    """The joinpath seam used by DotBox's source-only kit inventory."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def joinpath(self, name: str) -> Path:
        return resource_path(self.root, name)
