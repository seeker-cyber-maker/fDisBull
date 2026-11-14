#!/usr/bin/env python3
"""Verify that the active shared installation matches a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

DEFAULT_BASE = Path("/Users/Shared/fDisBull")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def _bound_document(prefix: Path, ref, expected_path: str) -> dict:
    if (not isinstance(ref, dict) or set(ref) != {'path','sha256'} or ref.get('path') != expected_path
            or not re.fullmatch(r'[a-f0-9]{64}', str(ref.get('sha256', '')))):
        raise ValueError('activation evidence reference invalid')
    path=prefix / expected_path
    if (any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file()
            or not path.resolve().is_relative_to(prefix) or path.stat().st_size > 1024*1024):
        raise ValueError('activation evidence path invalid')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('activation evidence hash mismatch')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('activation evidence invalid')
    return value


def _activation_proof(prefix: Path, current: Path, receipt: dict, version: str, commit: str, *, precheck: bool) -> None:
    attempt=receipt.get('activation_attempt')
    if not isinstance(attempt,str) or not re.fullmatch(r'[a-f0-9]{32}',attempt):
        raise ValueError('activation attempt invalid')
    intent_ref=receipt.get('activation_intent')
    intent=_bound_document(prefix,intent_ref,f'share/activations/{attempt}/intent.json')
    selected='releases/'+prefix.name
    required={'schema','attempt','source_commit','version','previous_selector','new_selector','staged_receipt_sha256'}
    if (not required <= set(intent) or intent.get('schema')!='fdisbull-install-activation-2'
            or intent.get('attempt')!=attempt or intent.get('source_commit')!=commit or intent.get('version')!=version
            or intent.get('new_selector')!=selected or os.readlink(current)!=selected
            or not re.fullmatch(r'[a-f0-9]{64}',str(intent.get('staged_receipt_sha256','')))
            or ('legacy_intent_sha256' in intent and not re.fullmatch(r'[a-f0-9]{64}',str(intent['legacy_intent_sha256'])))
            or (intent.get('previous_selector') is not None and not isinstance(intent['previous_selector'],str))):
        raise ValueError('activation intent binding mismatch')
    if precheck:return
    complete=_bound_document(prefix,receipt.get('activation_complete'),f'share/activations/{attempt}/complete.json')
    fields={'schema','attempt','source_commit','version','previous_selector','new_selector','intent_sha256','command_resolution','precheck_result'}
    if (set(complete)!=fields or complete.get('schema')!='fdisbull-install-activation-complete-2'
            or complete.get('attempt')!=attempt or complete.get('source_commit')!=commit
            or complete.get('version')!=version or complete.get('previous_selector')!=intent['previous_selector']
            or complete.get('new_selector')!=selected or complete.get('intent_sha256')!=intent_ref['sha256']):
        raise ValueError('activation completion binding mismatch')
    proof=complete.get('precheck_result');route=complete.get('command_resolution')
    if (not isinstance(proof,dict) or proof.get('status')!='prechecked'
            or proof.get('selected_default') is not True or proof.get('active_default') is not False
            or proof.get('version')!=version or proof.get('source_commit')!=commit
            or not isinstance(route,dict) or route.get('prefix')!=str(prefix) or route.get('version')!=version
            or not isinstance(route.get('caller_path'),str) or not route['caller_path']
            or not isinstance(route.get('wrapper'),str) or not route['wrapper']
            or not re.fullmatch(r'[a-f0-9]{64}',str(route.get('wrapper_sha256','')))):
        raise ValueError('activation precheck or command resolution invalid')
    native=route.get('native_commands')
    if (not isinstance(native,dict) or not isinstance(native.get('dosbox'),str) or not native['dosbox']
            or not isinstance(native.get('qemu'),str) or not native['qemu'] or not isinstance(native.get('targets'),list)
            or any(not isinstance(x,str) for x in native['targets']) or len(native['targets'])!=len(set(native['targets']))
            or set(native['targets'])!={'dosbox-x','dosbox-layers','qemu-system-x86_64'}):
        raise ValueError('activation native command resolution invalid')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--version", help="required installed version")
    parser.add_argument("--commit", help="required source commit")
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    parser.add_argument("--activation-precheck", action="store_true", help=argparse.SUPPRESS)
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
        expected_status = "activating" if args.activation_precheck else "active_verified"
        if receipt.get("status") != expected_status:
            raise ValueError(
                f"installation is not {expected_status}: {receipt.get('status')!r}"
            )
        _activation_proof(installation,current,receipt,version,commit,precheck=args.activation_precheck)
        verifier = installation / "share" / "verify-system.py"
        if not verifier.is_file():
            raise ValueError(f"missing verifier: {verifier}")
        environment = dict(
            os.environ,
            PYTHONPATH="",
            PYTHONNOUSERSITE="1",
            PYTHONDONTWRITEBYTECODE="1",
        )
        command = [
                str(installation / "venv/bin/python"),
                "-B",
                "-I",
                str(verifier),
                "verify",
            ]
        if args.activation_precheck:
            command.append('--activation-precheck')
        result = subprocess.run(
            command,
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
        if args.activation_precheck:
            valid = (proof.get('status') == 'prechecked' and proof.get('selected_default') is True
                     and proof.get('active_default') is False)
        else:
            valid = (proof.get('status') == 'passed' and proof.get('selected_default') is True
                     and proof.get('active_default') is True)
        if not valid or proof.get('version') != version or proof.get('source_commit') != commit:
            raise ValueError(f"active verification failed: {proof}")
        report.update(
            status="prechecked" if args.activation_precheck else "passed",
            selected_default=True,
            active_default=not args.activation_precheck,
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
            f"{'PRECHECKED' if args.activation_precheck else 'PASSED'}: {report['version']} {report['source_commit']} -> "
            f"{report['selector']} ({report['payload_entries']} entries)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
