#!/usr/bin/env python3
"""Install the bounded SCUMM target into a private QEMU 10.0.13 source tree.

SPDX-License-Identifier: GPL-2.0-or-later

Only six pinned registration files and the explicit overlay paths are touched.
--check is read-only. Reapplication permits prior recorded overlay contents, so
the build owner can apply reviewed compile fixes without rewriting other work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


from registration_check import REGISTRATIONS, plan_registration


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="scumm-overlay-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--source", dest="source_option", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if bool(args.source) == bool(args.source_option):
        parser.error("supply exactly one source path, positional or --source")
    source = (args.source or args.source_option).resolve(strict=True)
    if (source / "VERSION").read_text().strip() != "10.0.13":
        raise ValueError("only the pinned QEMU 10.0.13 source is supported")
    overlay = Path(__file__).resolve().parent / "overlay"
    receipt_path = source / ".fdisbull-scumm-overlay.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    previous_files = previous.get("files", {})
    planned: dict[str, bytes] = {}

    for relative in REGISTRATIONS:
        path = source / relative
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"registration path is not a regular source path: {relative}")
        current = path.read_bytes()
        planned[relative] = plan_registration(relative, current)

    for item in sorted(overlay.rglob("*")):
        if not item.is_file():
            continue
        if item.is_symlink():
            raise ValueError(f"overlay symlinks are not supported: {item}")
        relative = item.relative_to(overlay).as_posix()
        path = source / relative
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"overlay destination escapes its source path: {relative}")
        data = item.read_bytes()
        if path.exists():
            existing = path.read_bytes()
            if existing != data and sha(existing) != previous_files.get(relative):
                raise ValueError(f"unrecognized existing overlay file: {relative}")
        planned[relative] = data

    receipt = {
        "schema": "fdisbull-scumm-overlay-1",
        "qemu_version": "10.0.13",
        "source": str(source),
        "files": {name: sha(data) for name, data in sorted(planned.items())},
    }
    # All paths and original hashes are validated before the first write.
    changed = [name for name, data in planned.items()
               if not (source / name).exists() or (source / name).read_bytes() != data]
    if not args.check:
        for name in changed:
            atomic_write(source / name, planned[name])
        atomic_write(receipt_path, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"check_only": args.check, "source": str(source),
                      "files": len(planned), "changed": changed,
                      "overlay_identity": sha(json.dumps(receipt["files"], sort_keys=True).encode())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
