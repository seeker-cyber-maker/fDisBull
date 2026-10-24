#!/usr/bin/env python3
"""Check built archives for tool-only contents and complete test-source helpers."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

EXCLUDED_DIRECTORIES = {"examples", "history", "experimental", "build", "dist", ".git", "__pycache__"}
EXCLUDED_SUFFIXES = {".fdb", ".db", ".sqlite", ".sqlite3", ".sav", ".state", ".exe", ".com", ".dll", ".bin", ".dat", ".so", ".dylib", ".o", ".pyc"}
REQUIRED_TEST_HELPERS = {"tests/fixtures_formats.py", "tests/fixtures_macho.py"}
REQUIRED_PE_RESOURCES = {"wine_guest/agent.c", "wine_guest/init.sh", "wine_guest/broker.py"}


def archive_names(path: Path) -> list[str]:
    if path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Corrupt ZIP: {path}")
            return [item.filename for item in archive.infolist() if not item.is_dir()]
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if any(item.issym() or item.islnk() for item in members):
                raise ValueError(f"Source archive contains links: {path}")
            return [item.name for item in members if item.isfile()]
    raise ValueError(f"Unsupported distribution archive: {path}")


def check_archive(path: Path) -> int:
    names = archive_names(path)
    if not names:
        raise ValueError(f"Empty archive: {path}")
    entries = [PurePosixPath(name) for name in names]
    for entry in entries:
        if entry.is_absolute() or ".." in entry.parts:
            raise ValueError(f"Invalid archive path: {entry}")
        if EXCLUDED_DIRECTORIES.intersection(entry.parts):
            raise ValueError(f"Excluded directory in {path.name}: {entry}")
        if entry.suffix.lower() in EXCLUDED_SUFFIXES or ".fdb-" in entry.name.lower():
            raise ValueError(f"Excluded binary/data file in {path.name}: {entry}")
    if path.suffix == ".whl":
        roots = {entry.parts[0] for entry in entries}
        metadata = {name for name in roots if name.startswith("fdisbull-") and name.endswith(".dist-info")}
        if len(metadata) != 1 or roots != {"fdisbull", *metadata}:
            raise ValueError(f"Wheel contains files outside fdisbull and its metadata: {sorted(roots)}")
        if "fdisbull/__init__.py" not in names:
            raise ValueError("Wheel is missing fdisbull/__init__.py")
        missing = {"fdisbull/" + name for name in REQUIRED_PE_RESOURCES} - set(names)
        if missing:
            raise ValueError(f"Wheel is missing PE backend sources: {sorted(missing)}")
    else:
        roots = {entry.parts[0] for entry in entries}
        if len(roots) != 1 or not next(iter(roots)).startswith("fdisbull-"):
            raise ValueError(f"Unexpected source archive root: {sorted(roots)}")
        relative = {PurePosixPath(*entry.parts[1:]).as_posix() for entry in entries}
        required = REQUIRED_TEST_HELPERS | {"src/fdisbull/__init__.py", "pyproject.toml", "tests/wine_gui_fixture.c"}
        required |= {"src/fdisbull/" + name for name in REQUIRED_PE_RESOURCES}
        missing = required - relative
        if missing:
            raise ValueError(f"Source archive is missing required files: {sorted(missing)}")
    return len(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="*", type=Path)
    args = parser.parse_args()
    archives = args.archives or sorted(
        path for path in (Path(__file__).resolve().parents[1] / "dist").glob("*")
        if path.suffix in {".whl", ".zip"} or path.name.endswith(".tar.gz")
    )
    if not archives:
        parser.error("No distribution archives found; build them first")
    for path in archives:
        print(f"OK {path.name}: {check_archive(path)} tool-only entries")


if __name__ == "__main__":
    main()
