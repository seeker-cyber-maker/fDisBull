#!/usr/bin/env python3
"""Verify a handoff or create a manifest-bound, changed-files-only ZIP.

Standard library only. No network, installation, target execution or delta application.
Deletions are listed for review and are never applied by this tool.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT_METADATA = {"MANIFEST.json", "SHA256SUMS"}
IGNORED_DIRS = {"__pycache__", ".pytest_cache"}
HEX = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ValueError("Invalid relative path")
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in (".", "..", "") for part in name.split("/")):
        raise ValueError("Unsafe relative path: " + name)
    if ":" in name or "\n" in name or "\r" in name:
        raise ValueError("Nonportable relative path: " + name)
    return name


def read_manifest(data: bytes) -> dict:
    m = json.loads(data)
    if m.get("schema") != "fdisbull-handoff-manifest-1" or not ID.fullmatch(m.get("id", "")):
        raise ValueError("Unsupported manifest or invalid ID")
    entries = m.get("files")
    if not isinstance(entries, list):
        raise ValueError("Manifest files must be a list")
    seen = set()
    for row in entries:
        path = safe_name(row["path"])
        if path in seen or path in ROOT_METADATA:
            raise ValueError("Duplicate/reserved manifest path: " + path)
        seen.add(path)
        if type(row.get("bytes")) is not int or row["bytes"] < 0 or not HEX.fullmatch(row.get("sha256", "")):
            raise ValueError("Invalid file identity: " + path)
    if m.get("file_count") != len(entries):
        raise ValueError("Incorrect manifest file count")
    return m


def scan(root: Path) -> list[dict]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Input root must be a directory")
    entries = []
    for p in sorted(root.rglob("*")):
        relative = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if p.is_symlink():
            raise ValueError("Symlink refused: " + str(relative))
        if not p.is_file():
            continue
        name = safe_name(relative.as_posix())
        if name in ROOT_METADATA:
            continue
        data = p.read_bytes()
        entries.append({"path": name, "bytes": len(data), "sha256": sha(data)})
    return entries


def manifest(root: Path, identity: str, parent: dict | None = None) -> dict:
    if not ID.fullmatch(identity):
        raise ValueError("Invalid handoff ID")
    rows = scan(root)
    return {"schema": "fdisbull-handoff-manifest-1", "id": identity,
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "parent": parent,
            "file_count": len(rows), "total_bytes": sum(r["bytes"] for r in rows),
            "files": rows, "excludes": sorted(ROOT_METADATA),
            "ignored_directories": sorted(IGNORED_DIRS)}


def snapshot(root: Path, identity: str) -> dict:
    dest = root / "MANIFEST.json"
    if dest.exists() or (root / "SHA256SUMS").exists():
        raise ValueError("Refusing to overwrite existing root manifests")
    m = manifest(root, identity)
    data = encoded(m)
    with dest.open("xb") as f:
        f.write(data)
    sums = "".join(f"{r['sha256']}  {r['path']}\n" for r in m["files"])
    sums += f"{sha(data)}  MANIFEST.json\n"
    with (root / "SHA256SUMS").open("x", encoding="utf-8") as f:
        f.write(sums)
    return {"status": "passed", "id": identity, "file_count": m["file_count"],
            "manifest_sha256": sha(data)}


def verify(root: Path) -> dict:
    root = root.resolve(strict=True)
    data = (root / "MANIFEST.json").read_bytes()
    m = read_manifest(data)
    actual = {r["path"]: r for r in scan(root)}
    expected = {r["path"]: r for r in m["files"]}
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(p for p in actual.keys() & expected.keys() if actual[p] != expected[p])
        raise ValueError(json.dumps({"missing": missing, "extra": extra, "changed": changed}))
    sums = "".join(f"{r['sha256']}  {r['path']}\n" for r in m["files"])
    sums += f"{sha(data)}  MANIFEST.json\n"
    if (root / "SHA256SUMS").read_text(encoding="utf-8") != sums:
        raise ValueError("Root checksum file disagrees with manifest")
    return {"status": "passed", "id": m["id"], "file_count": len(actual),
            "manifest_sha256": sha(data), "total_bytes": sum(r["bytes"] for r in actual.values())}


def delta(base_file: Path, current: Path, output: Path, identity: str) -> dict:
    base_bytes = base_file.read_bytes()
    base = read_manifest(base_bytes)
    current = current.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(current):
        raise ValueError("Write delta outside the current tree")
    if output.exists():
        raise ValueError("Refusing to overwrite delta ZIP")
    if identity == base["id"]:
        raise ValueError("Delta ID must differ from parent")
    parent = {"id": base["id"], "manifest_sha256": sha(base_bytes)}
    result = manifest(current, identity, parent)
    old = {r["path"]: r for r in base["files"]}
    new = {r["path"]: r for r in result["files"]}
    added = [new[p] for p in sorted(new.keys() - old.keys())]
    modified = [{**new[p], "previous_sha256": old[p]["sha256"]}
                for p in sorted(new.keys() & old.keys()) if new[p] != old[p]]
    deleted = [old[p] for p in sorted(old.keys() - new.keys())]
    unchanged = sum(new[p] == old[p] for p in new.keys() & old.keys())
    result_data = encoded(result)
    d = {"schema": "fdisbull-handoff-delta-1", "id": identity, "parent": parent,
         "result_manifest_sha256": sha(result_data), "added": added, "modified": modified,
         "deleted": deleted, "unchanged_count": unchanged,
         "deletions_applied": False, "application": "manual review; no automatic overwrite or deletion"}
    files = {"DELTA.json": encoded(d), "RESULT_MANIFEST.json": result_data}
    for row in added + modified:
        data = (current / row["path"]).read_bytes()
        if sha(data) != row["sha256"] or len(data) != row["bytes"]:
            raise ValueError("Source changed while packaging: " + row["path"])
        files["payload/" + row["path"]] = data
    files["SHA256SUMS"] = "".join(f"{sha(b)}  {p}\n" for p, b in sorted(files.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, data in sorted(files.items()):
                z.writestr(name, data)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    checked = verify_delta(output, base_file)
    return {**checked, "zip": str(output), "zip_sha256": sha(output.read_bytes())}


def verify_delta(path: Path, base_file: Path) -> dict:
    base_bytes = base_file.read_bytes()
    base = read_manifest(base_bytes)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            safe_name(name)
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failure")
        d = json.loads(z.read("DELTA.json"))
        if d.get("schema") != "fdisbull-handoff-delta-1":
            raise ValueError("Unsupported delta")
        if d.get("parent") != {"id": base["id"], "manifest_sha256": sha(base_bytes)}:
            raise ValueError("Wrong parent manifest")
        result_bytes = z.read("RESULT_MANIFEST.json")
        result = read_manifest(result_bytes)
        if sha(result_bytes) != d.get("result_manifest_sha256") or result["id"] != d["id"] or result["parent"] != d["parent"]:
            raise ValueError("Result manifest mismatch")
        old = {r["path"]: r for r in base["files"]}
        new = {r["path"]: r for r in result["files"]}
        expected_added = [new[p] for p in sorted(new.keys() - old.keys())]
        expected_modified = [{**new[p], "previous_sha256": old[p]["sha256"]}
                             for p in sorted(new.keys() & old.keys()) if new[p] != old[p]]
        expected_deleted = [old[p] for p in sorted(old.keys() - new.keys())]
        expected_unchanged = sum(new[p] == old[p] for p in new.keys() & old.keys())
        if (d.get("added") != expected_added or d.get("modified") != expected_modified
                or d.get("deleted") != expected_deleted or d.get("unchanged_count") != expected_unchanged
                or d.get("deletions_applied") is not False):
            raise ValueError("Delta operation inventory mismatch")
        expected_names = {"DELTA.json", "RESULT_MANIFEST.json", "SHA256SUMS"}
        for row in expected_added + expected_modified:
            name = "payload/" + row["path"]
            expected_names.add(name)
            data = z.read(name)
            if len(data) != row["bytes"] or sha(data) != row["sha256"]:
                raise ValueError("Payload mismatch: " + row["path"])
        if set(names) != expected_names:
            raise ValueError("Unexpected/missing ZIP entries")
        sums = "".join(f"{sha(z.read(p))}  {p}\n" for p in sorted(expected_names - {"SHA256SUMS"}))
        if z.read("SHA256SUMS").decode() != sums:
            raise ValueError("Delta checksum file mismatch")
    return {"status": "passed", "id": d["id"], "parent": d["parent"],
            "added": len(expected_added), "modified": len(expected_modified),
            "deleted": len(expected_deleted), "unchanged": expected_unchanged}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("root", type=Path); s.add_argument("--id", required=True)
    v = sub.add_parser("verify"); v.add_argument("root", type=Path)
    d = sub.add_parser("delta"); d.add_argument("--base-manifest", type=Path, required=True)
    d.add_argument("--current", type=Path, required=True); d.add_argument("--output", type=Path, required=True); d.add_argument("--id", required=True)
    q = sub.add_parser("verify-delta"); q.add_argument("zip", type=Path); q.add_argument("--base-manifest", type=Path, required=True)
    a = p.parse_args()
    try:
        if a.command == "snapshot": r = snapshot(a.root, a.id)
        elif a.command == "verify": r = verify(a.root)
        elif a.command == "delta": r = delta(a.base_manifest, a.current, a.output, a.id)
        else: r = verify_delta(a.zip, a.base_manifest)
        print(json.dumps(r, indent=2)); return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
        print(f"FAILED: {e}", file=sys.stderr); return 1

if __name__ == "__main__":
    raise SystemExit(main())
