#!/usr/bin/env python3
"""Compare distribution payloads with Git-tracked runtime and test support files.

Run from the authoritative checkout against all four freshly built artifacts.
This is a completeness and byte-identity check, not a privacy or runtime test;
run check_dist.py and isolated entry-point checks separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# The whole directories are the contract. New tracked resources must be shipped,
# regardless of extension; do not silently exclude unfamiliar files here.
CORE = "src/fdisbull/"
PLAYER = "player/fdisbull_player/"
SOURCE_SUPPORT = (
    "native/qemu-clock/",
    "native/qemu-media/",
    "native/qemu-input/",
    "native/qemu-retrace/",
    "native/qemu-input-retrace/",
    "native/qemu-keyboard-press/",
    "native/qemu-keyboard-type/",
    "tests/",
    "scripts/",
    ".github/workflows/",
    ".gitlab-ci.yml",
    "skills/dos-target-media-rip/",
    "docs/evidence/gog-galaxy-chimprec-2026-11-02/receipt.json",
    "docs/evidence/scummvm-2026-11-01/verification.json",
    "docs/evidence/scummvm-2026-11-01/comparison.json",
    "docs/evidence/scummvm-gob-2026-11-01/verification.json",
    "docs/evidence/scummvm-gob-2026-11-01/comparison.json",
    "docs/evidence/0.32.0-release/README.md",
    "docs/evidence/0.32.0-release/intake.json",
    "docs/evidence/0.33.0-release/README.md",
    "docs/evidence/0.33.0-release/intake.json",
)


def tracked_payload(root: Path) -> dict[str, bytes]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", CORE, PLAYER, *SOURCE_SUPPORT],
        check=True, stdout=subprocess.PIPE,
    )
    files = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Tracked payload is not a regular file: {name}")
        files[name] = path.read_bytes()
    if not any(n.startswith(CORE) for n in files) or not any(n.startswith(PLAYER) for n in files):
        raise ValueError("Source inventory lacks tracked core or player package")
    return files


def archive_payload(path: Path) -> dict[str, bytes]:
    result = {}
    def add(name: str, data: bytes) -> None:
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or str(p) != name or name in result:
            raise ValueError(f"Unsafe or duplicate archive member: {name}")
        result[name] = data
    if path.name.endswith((".zip", ".whl")):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                # Unix symlinks must not be accepted as ordinary payloads.
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Archive contains a symlink: {item.filename}")
                add(item.filename, archive.read(item))
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            for item in archive:
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError(f"Archive contains a non-regular file: {item.name}")
                stream = archive.extractfile(item)
                if stream is None:
                    raise ValueError(f"Cannot read archive member: {item.name}")
                add(item.name, stream.read())
    else:
        raise ValueError(f"Unsupported archive: {path}")
    return result


def check_payload(source: dict[str, bytes], archive: dict[str, bytes], kind: str) -> None:
    if kind in {"sdist", "tool"}:
        roots = {name.split("/", 1)[0] for name in archive}
        if len(roots) != 1 or not next(iter(roots), "").startswith("fdisbull-"):
            raise ValueError(f"{kind}: unexpected source archive roots: {sorted(roots)}")
        prefix = next(iter(roots)) + "/"
        expected = {prefix + n: b for n, b in source.items()}
        # Detect unexpected package files too, without rejecting metadata or docs.
        actual_names = {n for n in archive if any(n.startswith(prefix + p) for p in (CORE, PLAYER, *SOURCE_SUPPORT))}
    elif kind in {"core", "player"}:
        source_prefix, package_prefix = (CORE, "fdisbull/") if kind == "core" else (PLAYER, "fdisbull_player/")
        expected = {package_prefix + n[len(source_prefix):]: b for n, b in source.items() if n.startswith(source_prefix)}
        actual_names = {n for n in archive if n.startswith(package_prefix)}
    else:
        raise ValueError(f"Unknown artifact kind: {kind}")
    missing = sorted(set(expected) - set(archive))
    unexpected = sorted(actual_names - set(expected))
    changed = sorted(n for n, b in expected.items() if n in archive and hashlib.sha256(b).digest() != hashlib.sha256(archive[n]).digest())
    if missing or unexpected or changed:
        raise ValueError(f"{kind} payload mismatch: missing={missing}; unexpected={unexpected}; changed={changed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    for kind in ("core", "player", "sdist", "tool"):
        parser.add_argument("--" + kind, type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Write a JSON receipt only after all comparisons pass")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Receipt output already exists; choose a new path")
    source = tracked_payload(args.source_root)
    for kind in ("core", "player", "sdist", "tool"):
        path = getattr(args, kind)
        check_payload(source, archive_payload(path), kind)
        print(f"OK {kind}: {path}")
    if args.output:
        commit = subprocess.check_output(["git", "-C", str(args.source_root), "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(args.source_root), "status", "--porcelain", "--untracked-files=no"], text=True).strip())
        artifacts = {}
        for kind in ("core", "player", "sdist", "tool"):
            path = getattr(args, kind)
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            artifacts[kind] = {"name": path.name, "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}
        receipt = {"schema": "fdisbull-package-payloads-1", "source_commit": commit, "tracked_worktree_dirty": dirty,
                   "inventory_counts": {"core": sum(n.startswith(CORE) for n in source),
                                        "player": sum(n.startswith(PLAYER) for n in source),
                                        "source_total": len(source)}, "artifacts": artifacts}
        with args.output.open("x") as stream:
            stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
