#!/usr/bin/env python3
"""Build the tool-only source ZIP from an explicit set of source directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "AGENTS.md", "pyproject.toml", "MANIFEST.in")
SOURCE_PATTERNS = (
    ("src/fdisbull", "*.py"),
    ("src/fdisbull/wine_guest", "*.c"),
    ("src/fdisbull/wine_guest", "*.sh"),
    ("tests", "*.py"),
    ("tests", "wine_gui_fixture.c"),
    ("docs", "*.md"),
    ("scripts", "*.py"),
)


def release_files(root: Path) -> list[Path]:
    """Exclude examples, generated files and experimental backends by construction."""
    files = [root / name for name in ROOT_FILES]
    for directory, pattern in SOURCE_PATTERNS:
        files.extend((root / directory).rglob(pattern))
    selected = []
    for path in sorted(set(files)):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Release input must be a regular file: {path}")
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            continue
        selected.append(path)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    files = release_files(ROOT)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / f"fdisbull-{version}-tool.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"fdisbull-{version}/{path.relative_to(ROOT).as_posix()}")
    print(f"Built {destination} ({len(files)} source files)")


if __name__ == "__main__":
    main()
