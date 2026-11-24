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


REGISTRATIONS = {
    "hw/Kconfig": (
        "f7940f36d1aa7b15a554f6378be03a85ddc9a40e2608b107c9d7c5dd2ccbe3d0",
        "source avr/Kconfig\n", "source avr/Kconfig\nsource scumm/Kconfig\n"),
    "hw/meson.build": (
        "c3bc3f1e22ff16eea62af2e2fe8642d1d683e9ec8307c5f05ba5d66171678d5b",
        "subdir('avr')\n", "subdir('avr')\nsubdir('scumm')\n"),
    "target/Kconfig": (
        "ac823c76c3267069432d63943e82cb067fb9ead2451785b798558457327e6544",
        "source avr/Kconfig\n", "source avr/Kconfig\nsource scumm/Kconfig\n"),
    "target/meson.build": (
        "43d9537ac1fc911a9c76cd03ddc59753795e2acb3e76de4a9f0ba683c49f345b",
        "subdir('avr')\n", "subdir('avr')\nsubdir('scumm')\n"),
    "include/system/arch_init.h": (
        "2bed554869e91d03a85060eb3e006592b7cf3488c029edab55c6a3f23201e20f",
        "    QEMU_ARCH_LOONGARCH = (1 << 23),\n",
        "    QEMU_ARCH_LOONGARCH = (1 << 23),\n    QEMU_ARCH_SCUMM = (1 << 26),\n"),
    "qapi/machine.json": (
        "78f0ecaa75dbb8c69c93cefe915e735fddb49de315bd267d5fd92f5678f961f6",
        "  'data' : [ 'aarch64', 'alpha', 'arm', 'avr', 'hppa', 'i386',\n",
        "  'data' : [ 'aarch64', 'scumm', 'alpha', 'arm', 'avr', 'hppa', 'i386',\n"),
}


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

    for relative, (expected, old, new) in REGISTRATIONS.items():
        path = source / relative
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"registration path is not a regular source path: {relative}")
        current = path.read_bytes()
        old_b, new_b = old.encode(), new.encode()
        if sha(current) == expected:
            base = current
        else:
            variants = [new_b]
            bases = [current.replace(variant, old_b, 1) for variant in variants
                     if current.count(variant) == 1]
            bases = [candidate for candidate in bases if sha(candidate) == expected]
            if len(bases) != 1:
                raise ValueError(f"unrecognized modified registration: {relative}")
            base = bases[0]
        if base.count(old_b) != 1:
            raise ValueError(f"ambiguous registration anchor: {relative}")
        planned[relative] = base.replace(old_b, new_b, 1)

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
