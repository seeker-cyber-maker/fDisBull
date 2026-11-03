#!/usr/bin/env python3
"""Qualify one CI commit from all mandatory job artifacts; never query a provider.

Run in the dependent GitLab summary job, whose needs require every contributing
job to succeed. This checks artifact identities and coverage receipts as well as
the dependency graph. A routine fast-only pipeline cannot produce this receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import xml.etree.ElementTree as ET

JOBS = {"ordinary": "test-and-package", "stable": "native-debugger-stable",
        "layers": "native-debugger-layers", "unified": "native-unified"}
JUNIT = {"ordinary": ['artifacts/ordinary/tests.xml'], "stable": ['native-evidence/stable/tests.xml'],
         "layers": ['native-evidence/layers/tests.xml'],
         "unified": ['native-evidence/pe/tests.xml', 'native-evidence/unified/tests.xml']}


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Missing or invalid receipt: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Invalid receipt object: {path}")
    return value


def local_path(root, name):
    if not isinstance(name, str):
        raise ValueError("Artifact path must be a string")
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or str(p) != name:
        raise ValueError(f"Unsafe artifact path: {name}")
    path = root / name
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Missing or unsafe artifact: {name}")
    return path


def identity(root, name):
    path = local_path(root, name)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {"path": name, "sha256": digest, "size": path.stat().st_size}


def verify_artifact(root, item):
    if not isinstance(item, dict) or identity(root, item.get('path')) != item:
        raise ValueError(f"Artifact identity mismatch: {item.get('path') if isinstance(item, dict) else item}")


def passing_junit(path, *, native=False):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if (any(v < 0 for v in counts.values()) or counts['tests'] <= counts['skipped'] or counts['failures'] or counts['errors']
        or (native and counts['skipped'])):
        raise ValueError(f"Missing, failing or entirely skipped tests: {path}: {counts}")
    return counts


def validate(root, source_commit, pipeline_id):
    if not re.fullmatch('[0-9a-f]{40}', source_commit) or not re.fullmatch('[0-9]+', str(pipeline_id)):
        raise ValueError("Qualification requires an exact commit and pipeline ID")
    results, job_ids = {}, set()
    for profile, job in JOBS.items():
        name = 'ordinary' if profile == 'ordinary' else 'native-' + profile
        path = root / f'artifacts/receipts/{name}.json'
        receipt = read(path)
        if (receipt.get('status') != 'passed' or receipt.get('source_commit') != source_commit
            or str(receipt.get('pipeline_id')) != str(pipeline_id) or receipt.get('job_name') != job
            or receipt.get('profile') != profile):
            raise ValueError(f"Job status, source, pipeline or profile mismatch: {job}")
        job_id = str(receipt.get('job_id'))
        if not re.fullmatch('[0-9]+', job_id) or job_id in job_ids:
            raise ValueError(f"Missing or duplicate job identity: {job}")
        job_ids.add(job_id)
        python = receipt.get('python_version', '')
        if (profile == 'layers' and python != '3.13.5') or (profile != 'layers' and not python.startswith('3.12.')):
            raise ValueError(f"Unexpected qualification interpreter: {job}: {python}")
        if receipt.get('node_version') != 'v22.23.4':
            raise ValueError(f"Unexpected qualification Node runtime: {job}")
        tests, artifacts = receipt.get('test_results'), receipt.get('artifacts')
        if (not isinstance(tests, list) or [i.get('path') for i in tests if isinstance(i, dict)] != JUNIT[profile]
            or not isinstance(artifacts, list) or not artifacts):
            raise ValueError(f"Required test/artifact captures absent: {job}")
        counts = []
        for item in tests:
            verify_artifact(root, item)
            counts.append(passing_junit(local_path(root, item['path']), native=profile != 'ordinary'))
        for item in artifacts:
            verify_artifact(root, item)
        if profile != 'ordinary' and receipt.get('backend_identity', {}).get('source_commit') != source_commit:
            raise ValueError(f"Wrong native backend source: {job}")
        results[job] = {"job_id": job_id, "receipt": identity(root, str(path.relative_to(root))),
                        "test_counts": counts, "artifacts": artifacts}
    payload = read(root / 'artifacts/receipts/package-payloads.json')
    if payload.get('source_commit') != source_commit or payload.get('tracked_worktree_dirty') is not False:
        raise ValueError("Package inventory is absent, dirty or from another commit")
    package_artifacts = payload.get('artifacts', {})
    if set(package_artifacts) != {'core', 'player', 'sdist', 'tool'}:
        raise ValueError("Package inventory lacks an artifact kind")
    ordinary = {item['path']: item for item in results['test-and-package']['artifacts']}
    for item in package_artifacts.values():
        p = 'dist/' + item['name']
        if ordinary.get(p) != {"path": p, "sha256": item['sha256'], "size": item['size_bytes']}:
            raise ValueError(f"Package inventory and ordinary job disagree: {p}")
    core = package_artifacts['core']
    tested = results['native-unified']['artifacts']
    if len(tested) != 1 or (tested[0]['sha256'], tested[0]['size']) != (core['sha256'], core['size_bytes']):
        raise ValueError("The installed-wheel native acceptance did not test the ordinary core wheel")
    return {"schema": "fdisbull-ci-qualification-1", "status": "qualified", "source_commit": source_commit,
            "pipeline_id": str(pipeline_id), "required_jobs": results,
            "package_inventory": identity(root, 'artifacts/receipts/package-payloads.json'),
            "release_authorized": False}


def write_ordinary(root):
    payload = read(root / 'artifacts/receipts/package-payloads.json')
    if payload.get('source_commit') != os.environ['CI_COMMIT_SHA'] or payload.get('tracked_worktree_dirty') is not False:
        raise ValueError("Cannot certify dirty or wrong-source package inventory")
    passing_junit(root / 'artifacts/ordinary/tests.xml')
    return {"status": "passed", "profile": "ordinary", "source_commit": os.environ['CI_COMMIT_SHA'],
            "pipeline_id": os.environ['CI_PIPELINE_ID'], "job_id": os.environ['CI_JOB_ID'],
            "job_name": os.environ['CI_JOB_NAME'], "python_version": platform.python_version(),
            "node_version": subprocess.check_output(['node', '--version'], text=True).strip(),
            "test_results": [identity(root, 'artifacts/ordinary/tests.xml')],
            "artifacts": [identity(root, 'dist/' + v['name']) for v in payload['artifacts'].values()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--source-commit', default=os.environ.get('CI_COMMIT_SHA'))
    parser.add_argument('--pipeline-id', default=os.environ.get('CI_PIPELINE_ID'))
    parser.add_argument('--write-ordinary', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Receipt exists; preserve it and choose a new output')
    try:
        result = write_ordinary(args.root) if args.write_ordinary else validate(args.root, args.source_commit, args.pipeline_id)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        parser.exit(2, f'Incomplete qualification: {exc}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(f"{result['status']}: {result['source_commit']} (pipeline {result['pipeline_id']})")


if __name__ == '__main__':
    main()
