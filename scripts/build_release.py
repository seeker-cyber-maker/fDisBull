#!/usr/bin/env python3
"""Build the tool-only source ZIP from an explicit set of source directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "MANIFEST.in", "player/pyproject.toml")
DOC_EXAMPLE_FILES = (
    "docs/uil-rfcs/0001/README.md",
    "docs/uil-rfcs/0001/check_examples.py",
    "docs/uil-rfcs/0001/commit.js",
    "docs/uil-rfcs/0001/commit.py",
    "docs/uil-rfcs/0001/commit.rs",
    "docs/uil-rfcs/0001/native-observation.json",
    "docs/uil-rfcs/0001/native_probe.py",
    "docs/uil-rfcs/0001/source-definition-observation.json",
    "docs/uil-rfcs/0001/vectors.json",
    "docs/uil-rfcs/0002/vectors.json",
    "docs/uil-rfcs/0002/replay-summary.json",
)
SOURCE_PATTERNS = (
    ("src/fdisbull", "*.py"),
    ("player/fdisbull_player", "*.py"),
    ("src/fdisbull/data", "*.json"),
    ("src/fdisbull/data", "*.txt"),
    ("src/fdisbull/skills", "*.md"),
    ("src/fdisbull/wine_guest", "*.c"),
    ("src/fdisbull/wine_guest", "*.sh"),
    ("src/fdisbull/ida_guest", "*.c"),
    ("src/fdisbull/ida_guest", "*.sh"),
    ("src/fdisbull/ida_guest", "SDK-LICENSE.txt"),
    ("src/fdisbull/dos_guest", "*.sh"),
    ("tests", "*.py"),
    ("tests", "wine_gui_fixture.c"),
    ("tests", "dosbox_zip_empty_write.cpp"),
    ("tests", "ida_rpc_vectors.json"),
    ("docs", "*.md"),
    ("docs/evidence/spatial-2026-10-29", "verification.json"),
    ("docs/evidence/zork-2026-10-29", "verification.json"),
    ("docs/evidence/zork-uil-2026-10-29", "verification.json"),
    ("docs/evidence/zork-intents-2026-10-29", "verification.json"),
    ("docs/evidence/scene-recovery-2026-10-29", "representation-paths.json"),
    ("docs/evidence/scene-recovery-2026-10-29", "scene-pipeline-summary.json"),
    ("docs/evidence/zmachine-processor-2026-10-29", "verification.json"),
    ("docs/evidence/zork-scenes-2026-10-30", "verification.json"),
    ("docs/evidence/udc-2026-10-29", "dino.json"),
    ("docs/evidence/udc-2026-10-29", "zork.json"),
    ("docs/evidence/udc-2026-10-29", "synthetic.json"),
    ("docs/evidence/output-024", "amplification.json"),
    ("docs/evidence/output-024", "dinopark-native.json"),
    ("docs/evidence/output-024", "dinopark-output.json"),
    ("docs/evidence/output-024", "tests.json"),
    ("docs/evidence/integration-025", "zork.json"),
    ("docs/evidence/integration-025", "dinopark.json"),
    ("docs/evidence/integration-025", "tests.json"),
    ("docs/evidence/integration-025", "packages.json"),
    ("docs/evidence/integration-026", "verification.json"),
    ("scripts", "*.py"),
)


def release_files(root: Path) -> list[Path]:
    """Select tool sources plus the exact authored RFC fixture allowlist."""
    files = [root / name for name in (*ROOT_FILES, *DOC_EXAMPLE_FILES)]
    for directory, pattern in SOURCE_PATTERNS:
        candidates = ((root / directory).glob(pattern) if directory == "player/fdisbull_player"
                      else (root / directory).rglob(pattern))
        if directory == "docs":
            fixture_root = root / "docs/uil-rfcs/0001"
            files.extend(path for path in candidates if fixture_root not in path.parents)
        else:
            files.extend(candidates)
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
