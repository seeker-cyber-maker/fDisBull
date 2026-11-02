#!/usr/bin/env python3
"""Verify that the active shared installation matches a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_BASE = Path("/Users/Shared/fDisBull")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--version", help="required installed version")
    parser.add_argument("--commit", help="required source commit")
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    args = parser.parse_args()
    base = args.base.expanduser().resolve()
    current = base / "current"
    report: dict[str, object] = {
        "format": "fdisbull-local-install-check-1",
        "base": str(base),
    }
    try:
        if not current.is_symlink():
            raise ValueError(f"missing shared selector: {current}")
        installation = current.resolve()
        if not installation.is_relative_to(base / "releases"):
            raise ValueError(f"selector points outside releases: {installation}")
        runtime = read(installation / "RUNTIME.json")
        receipt = read(installation / "INSTALLATION.json")
        version = str(runtime["version"])
        commit = str(runtime["source_commit"])
        if args.version is not None and version != args.version:
            raise ValueError(
                f"installed version {version!r} != required {args.version!r}"
            )
        if args.commit is not None and commit != args.commit:
            raise ValueError(f"installed commit {commit!r} != required {args.commit!r}")
        if receipt.get("version") != version or receipt.get("source_commit") != commit:
            raise ValueError("installation receipt identity mismatch")
        if receipt.get("status") != "active_verified":
            raise ValueError(
                f"installation is not active_verified: {receipt.get('status')!r}"
            )
        verifier = installation / "share" / "verify-system.py"
        if not verifier.is_file():
            raise ValueError(f"missing verifier: {verifier}")
        environment = dict(
            os.environ,
            PYTHONPATH="",
            PYTHONNOUSERSITE="1",
            PYTHONDONTWRITEBYTECODE="1",
        )
        result = subprocess.run(
            [
                str(installation / "venv/bin/python"),
                "-B",
                "-I",
                str(verifier),
                "verify",
            ],
            cwd="/private/tmp",
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(
                (result.stdout + result.stderr).strip() or "verifier failed"
            )
        proof = json.loads(result.stdout)
        if proof.get("status") != "passed" or proof.get("active_default") is not True:
            raise ValueError(f"active verification failed: {proof}")
        report.update(
            status="passed",
            selector=os.readlink(current),
            installation=str(installation),
            version=version,
            source_commit=commit,
            payload_entries=proof.get("payload_entries"),
            payload_manifest_sha256=sha256(installation / "PAYLOAD.json"),
            wheel_resources=proof.get("wheel_resources"),
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        if args.json:
            print(json.dumps(report, sort_keys=True))
        else:
            print(f"FAILED: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            f"PASSED: {report['version']} {report['source_commit']} -> "
            f"{report['selector']} ({report['payload_entries']} entries)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
