#!/usr/bin/env python3
"""Download and verify the ten fDisBull 0.29.0 GitLab generic-package files.

Requires Python 3.10+, and a GitLab API token with access to private project 88349936.
Supply GITLAB_TOKEN or use a previously authenticated `glab auth token`.
No game binaries or private user data are requested or included.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECT_ID = 88349936
TAG = "v0.29.0"
TAG_COMMIT = "09a820952ad3f54d0d0707db0515a8010f7eceb1"
PACKAGE_GROUPS = {
    74791804: ("fdisbull-release-packages", "0.29.0-20261101", 6),
    74791785: ("fdisbull-tool-packages", "0.29.0-20261101", 4),
}
EXPECTED_SHA256 = {
    "fdisbull-0.29.0-linux-x86_64-offline.tar.gz": "b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f",
    "fdisbull-0.29.0-linux-x86_64-source-companion.tar": "f9560466383cbb4a8e1096434889d7009ae9fcca4b0d2511c25f4d61ea95d118",
    "fdisbull-0.29.0-linux-x86_64-dependencies.tar.gz": "e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6",
    "fdisbull-0.29.0-py3-none-any.whl": "0fbebc6142ecdb686c924f3c3d6f8ad0f3ed20b1453f378a9c8156e2cca538f6",
    "fdisbull-0.29.0.tar.gz": "c839319fd153d9c2f6933afd9662a0c837889d2dc9a2fb80310e2c51d0ae65e8",
}
EXPECTED_BYTES = {
    "fdisbull-0.29.0-linux-x86_64-offline.tar.gz": 103013282,
    "fdisbull-0.29.0-linux-x86_64-source-companion.tar": 106905600,
}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def token_from_user_environment():
    token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GITLAB_PRIVATE_TOKEN")
    if token:
        return token.strip()
    if shutil.which("glab"):
        proc = subprocess.run(["glab", "auth", "token"], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    raise RuntimeError(
        "A GitLab API token is needed. Authenticate with `glab auth login` on this "
        "machine, or set GITLAB_TOKEN in your terminal. Do not paste tokens into chat."
    )


def read_json(api_root, token, path):
    url = api_root.rstrip("/") + path
    request = Request(url, headers={"PRIVATE-TOKEN": token, "Accept": "application/json"})
    with urlopen(request, timeout=60) as resp:
        return json.load(resp)


def fetch(api_root, token, path, destination, expected_sha=None, expected_size=None):
    url = api_root.rstrip("/") + path
    temporary = destination.with_name(destination.name + ".partial")
    digest = hashlib.sha256()
    total = 0
    request = Request(url, headers={"PRIVATE-TOKEN": token})
    try:
        with urlopen(request, timeout=120) as resp, temporary.open("wb") as file:
            while True:
                block = resp.read(1024 * 1024)
                if not block:
                    break
                file.write(block)
                digest.update(block)
                total += len(block)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    actual_sha = digest.hexdigest()
    if expected_sha is not None and expected_sha.lower() != actual_sha:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch: {destination.name}: {actual_sha} != {expected_sha}")
    if expected_size is not None and expected_size != total:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Size mismatch: {destination.name}: {total} != {expected_size}")
    temporary.replace(destination)
    return actual_sha, total


def checksum_lines(path):
    """Parse sha256sum-compatible lines; hashes are scoped to basenames."""
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Fa-f0-9]{64})\s+[*]?(.+)", line)
        if not match:
            raise RuntimeError(f"Unrecognized checksum line in {path.name}: {line[:100]}")
        name = Path(match.group(2).removeprefix("./")).name
        checksum = match.group(1).lower()
        if name in entries and entries[name] != checksum:
            raise RuntimeError(f"Conflicting checksums for {name}")
        entries[name] = checksum
    if not entries:
        raise RuntimeError("SHA256SUMS did not contain any hashes")
    return entries


def run(args):
    token = token_from_user_environment()
    api = "https://gitlab.com/api/v4"
    release = read_json(api, token, f"/projects/{PROJECT_ID}/releases/{quote(TAG, safe='')}")
    actual_tag_sha = release.get("commit", {}).get("id")
    if actual_tag_sha != TAG_COMMIT:
        raise RuntimeError(f"Unexpected release tag commit: {actual_tag_sha}")
    folder = args.output.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    inventory = []
    for package_id, (expected_name, expected_version, expected_count) in PACKAGE_GROUPS.items():
        package = read_json(api, token, f"/projects/{PROJECT_ID}/packages/{package_id}")
        if (package.get("name"), package.get("version")) != (expected_name, expected_version):
            raise RuntimeError(f"Unexpected GitLab package metadata: {package_id}")
        rows = read_json(api, token, f"/projects/{PROJECT_ID}/packages/{package_id}/package_files?per_page=100")
        if not isinstance(rows, list) or len(rows) != expected_count:
            raise RuntimeError(f"Package {package_id} returned {len(rows) if isinstance(rows, list) else 'invalid'} files, expected {expected_count}")
        for item in rows:
            filename = item.get("file_name")
            if not filename or Path(filename).name != filename or filename.startswith("."):
                raise RuntimeError(f"Unexpected filename in GitLab package {package_id}: {filename!r}")
            sha = item.get("file_sha256")
            if sha is not None and not SHA256.fullmatch(sha.lower()):
                raise RuntimeError(f"Invalid GitLab SHA-256 for {filename}")
            inventory.append({"package_id": package_id, "package": expected_name, "version": expected_version,
                              "filename": filename, "file_sha256": sha.lower() if sha else None,
                              "size": item.get("size")})
    names = [f["filename"] for f in inventory]
    if len(names) != 10 or len(set(names)) != 10:
        raise RuntimeError("Expected ten distinct release files")
    for name in ("SHA256SUMS", "BUILD.json", *EXPECTED_SHA256):
        if name not in names:
            raise RuntimeError(f"Missing required full-release asset: {name}")
    # Verify the publishing metadata before downloading any large assets.
    outcomes = []
    for f in inventory:
        name = f["filename"]
        package_path = f"/projects/{PROJECT_ID}/packages/generic/{quote(f['package'],safe='')}/{quote(f['version'],safe='')}/{quote(name,safe='')}"
        expected = EXPECTED_SHA256.get(name) or f.get("file_sha256")
        size_expected = EXPECTED_BYTES.get(name) or f.get("size")
        path = folder / name
        if path.exists():
            with path.open("rb") as existing:
                data_sha = hashlib.file_digest(existing, "sha256").hexdigest()
            if expected and data_sha == expected and (size_expected is None or path.stat().st_size == size_expected):
                print(f"Verified existing: {name}", flush=True)
                outcomes.append({**f, "sha256": data_sha, "size": path.stat().st_size, "reused": True})
                continue
        print(f"Downloading: {name}", flush=True)
        sha, size = fetch(api, token, package_path, path, expected_sha=expected, expected_size=size_expected)
        outcomes.append({**f, "sha256": sha, "size": size, "reused": False})
    published = checksum_lines(folder / "SHA256SUMS")
    for f in outcomes:
        named_expected = published.get(f["filename"])
        if named_expected is not None and named_expected != f["sha256"]:
            raise RuntimeError(f"Publisher manifest mismatch for {f['filename']}")
    # Every entry in the publisher's manifest must refer to a verified downloaded file.
    for name, digest in published.items():
        matching = next((f for f in outcomes if f["filename"] == name), None)
        if matching is None or matching["sha256"] != digest:
            raise RuntimeError(f"Unexpected or mismatching publisher checksum: {name}")
    build_metadata = json.loads((folder / "BUILD.json").read_text(encoding="utf-8"))
    receipt = {"format": "fdisbull-v0.29.0-download-receipt-1", "tag": TAG,
               "tag_commit": TAG_COMMIT, "project_id": PROJECT_ID,
               "publisher_manifest_checked": True,
               "files": outcomes, "build_metadata": build_metadata}
    (folder / "VERIFIED-DOWNLOAD.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Verified all {len(outcomes)} files in {folder}", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "fdisbull-0.29.0-full")
    args = parser.parse_args()
    try:
        return run(args)
    except (RuntimeError, HTTPError, URLError, OSError, ValueError) as exc:
        print(f"Cannot complete the verified download: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())