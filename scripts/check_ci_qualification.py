#!/usr/bin/env python3
"""Qualify one CI commit from all mandatory job artifacts; never query a provider.

Run in the dependent GitLab summary job, whose needs require every contributing
job to succeed. This checks artifact identities and coverage receipts as well as
the dependency graph. A routine fast-only pipeline cannot produce this receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "ci"))
from execution_identity import canonical_uuid, execution_identity
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


REUSE_FILES = {
    'build_identity_sha256': 'build-identity.json',
    'build_process_sha256': 'build-process.json',
    'build_manifest_sha256': 'build-manifest.json',
    'build_config_sha256': 'config.log',
}
REUSE_FIELDS = frozenset((*REUSE_FILES, 'build_source_commit', 'build_image_digest'))


def verify_reused_backend(root, profile, backend, artifacts, process):
    """Re-read retained build provenance; never infer a build from test success."""
    base = f'native-evidence/{profile}/'
    indicators = ('reuse-provenance.json', 'build-identity.json', 'build-process.json', 'build-manifest.json')
    present = lambda path: path.exists() or path.is_symlink()
    if not REUSE_FIELDS.intersection(backend) and not any(present(root / base / name) for name in indicators):
        return None
    if profile not in ('stable', 'layers') or not isinstance(process, dict):
        raise ValueError('Reused backend requires a local native process')
    if not REUSE_FIELDS.issubset(backend):
        raise ValueError('Reused backend provenance is incomplete')
    proofs = {}
    marker_path = root / base / 'reuse-provenance.json'
    if present(marker_path):
        marker = read(local_path(root, base + 'reuse-provenance.json'))
        if any(marker.get(field) != backend[field] for field in REUSE_FIELDS):
            raise ValueError('Reused backend provenance marker mismatch')
        proofs['reuse-provenance.json'] = identity(root, base + 'reuse-provenance.json')
    for field, filename in REUSE_FILES.items():
        item = identity(root, base + filename)
        if item['sha256'] != backend[field]:
            raise ValueError(f'Reused backend provenance hash mismatch: {filename}')
        proofs[filename] = item
    original = read(local_path(root, base + 'build-identity.json'))
    build_process = read(local_path(root, base + 'build-process.json'))
    manifest = read(local_path(root, base + 'build-manifest.json'))
    build_sha = backend['build_source_commit']
    image = backend['build_image_digest']
    if (not isinstance(build_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', build_sha)
        or original.get('source_commit') != build_sha
        or build_process.get('source_commit') != build_sha
        or build_process.get('execution_origin') != 'local-linux'
        or build_process.get('job_name') != JOBS[profile]
        or not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image)
        or build_process.get('image_digest') != image or process.get('image_digest') != image):
        raise ValueError('Reused backend build source, process or image mismatch')
    expected_profile = 'experimental/dosbox-x' + ('/layers' if profile == 'layers' else '')
    if (original.get('profile') != expected_profile or backend.get('profile') != expected_profile
        or original.get('upstream_commit') != manifest.get('baseline_commit')
        or backend.get('upstream_commit') != original.get('upstream_commit')
        or original.get('patch_sha256') != manifest.get('patch_sha256')
        or backend.get('patch_sha256') != original.get('patch_sha256')
        or not isinstance(original.get('configure_flags'), list)
        or backend.get('configure_flags') != original.get('configure_flags')):
        raise ValueError('Reused backend original build metadata mismatch')
    binary_path = f'.native/backends/{profile}/dosbox-x'
    binary = next((item for item in artifacts if item.get('path') == binary_path), None)
    if (binary is None or original.get('backend_sha256') != binary.get('sha256')
        or backend.get('backend_sha256') != binary.get('sha256')):
        raise ValueError('Reused backend binary identity mismatch')
    return proofs


def verify_local_unified_preparation(root, source_commit, run_id, canonical_job_ids, receipt, process):
    """Bind independently prepared runtime inputs to the tested local job."""
    base = 'native-evidence/pe/'
    manifest_ref = receipt.get('prepared_manifest')
    if not isinstance(manifest_ref, dict) or manifest_ref.get('path') != base + 'prepared-inputs.json':
        raise ValueError('Local unified prepared manifest missing')
    verify_artifact(root, manifest_ref)
    manifest = read(local_path(root, base + 'prepared-inputs.json'))
    build_job = canonical_uuid(manifest.get('build_job_id'))
    if build_job in canonical_job_ids:
        raise ValueError('Preparation job identity duplicates a qualification job')
    paths = {name: base + 'preparation-' + name + '.json'
             for name in ('process', 'source-postcheck', 'completed')}
    proof = {name: identity(root, path) for name, path in paths.items()}
    build = read(local_path(root, paths['process']))
    postcheck = read(local_path(root, paths['source-postcheck']))
    completed = read(local_path(root, paths['completed']))
    if (build.get('execution_origin') != 'local-linux' or build.get('source_commit') != source_commit
        or build.get('local_run_id') != run_id or build.get('local_job_id') != build_job
        or build.get('job_name') != 'native-unified-prepare' or build.get('termination') != 'exited'
        or type(build.get('exit_code')) is not int or build.get('exit_code') != 0
        or build.get('container_state_after_stop') != 'stopped'
        or build.get('image_digest') != process.get('image_digest')
        or build.get('runtime') != process.get('runtime')):
        raise ValueError('Unified preparation process identity or runtime mismatch')
    if (postcheck.get('source_commit') != source_commit
        or postcheck.get('expected_source_commit') != source_commit
        or postcheck.get('tracked_worktree_dirty') is not False
        or postcheck.get('export_success') is not True):
        raise ValueError('Unified preparation source postcheck failed')
    if (completed.get('source_commit') != source_commit or completed.get('local_job_id') != build_job
        or not isinstance(completed.get('completed_at'), str) or not completed['completed_at']):
        raise ValueError('Unified preparation completion marker mismatch')
    spec = importlib.util.spec_from_file_location('fdisbull_unified_runtime_inputs',
                    Path(__file__).resolve().parent / 'ci/unified-runtime-inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checked = module.verify(root, source_commit, run_id, build_job, source_root=None)
    if (receipt.get('runtime_inputs') != list(checked['inputs'].values())
        or receipt.get('resource_receipts') != list(checked['resource_receipts'].values())
        or receipt.get('firmware') != checked['firmware']
        or receipt.get('artifacts') != [checked['tested_wheel'], *checked['inputs'].values()]
        or receipt.get('backend_identity') != read(local_path(root, checked['backend_identity']['path']))):
        raise ValueError('Unified acceptance receipt does not match prepared runtime')
    return {'build_job_id': build_job, 'prepared_manifest': manifest_ref, **proof}


def passing_junit(path, *, native=False):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if (any(v < 0 for v in counts.values()) or counts['tests'] <= counts['skipped'] or counts['failures'] or counts['errors']
        or (native and counts['skipped'])):
        raise ValueError(f"Missing, failing or entirely skipped tests: {path}: {counts}")
    return counts


def validate(root, source_commit, pipeline_id=None, *, local_run_id=None):
    if not isinstance(source_commit, str) or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError("Qualification requires an exact commit")
    if local_run_id is None:
        if not re.fullmatch('[0-9]+', str(pipeline_id)):
            raise ValueError("Qualification requires an exact pipeline ID")
    else:
        canonical_uuid(local_run_id)
        if pipeline_id is not None:
            raise ValueError("Local qualification cannot claim a GitLab pipeline")
    results, job_ids = {}, set()
    unified_receipt = unified_process = None
    for profile, job in JOBS.items():
        name = 'ordinary' if profile == 'ordinary' else 'native-' + profile
        path = root / f'artifacts/receipts/{name}.json'
        receipt = read(path)
        if (receipt.get('status') != 'passed' or receipt.get('source_commit') != source_commit
            or receipt.get('job_name') != job or receipt.get('profile') != profile):
            raise ValueError(f"Job status, source or profile mismatch: {job}")
        process = None
        if local_run_id is None:
            if (receipt.get('execution_origin', 'gitlab') != 'gitlab'
                or str(receipt.get('pipeline_id')) != str(pipeline_id)
                or 'local_run_id' in receipt or 'local_job_id' in receipt):
                raise ValueError(f"Job origin or pipeline mismatch: {job}")
            job_id = str(receipt.get('job_id'))
            if not re.fullmatch('[0-9]+', job_id):
                raise ValueError(f"Missing job identity: {job}")
        else:
            if (receipt.get('execution_origin') != 'local-linux'
                or receipt.get('local_run_id') != local_run_id
                or 'pipeline_id' in receipt or 'job_id' in receipt):
                raise ValueError(f"Job origin or local run mismatch: {job}")
            job_id = canonical_uuid(receipt.get('local_job_id'))
            process_path = root / f'artifacts/receipts/local-process-{profile}.json'
            process = read(process_path)
            if (process.get('execution_origin') != 'local-linux'
                or process.get('local_run_id') != local_run_id
                or process.get('local_job_id') != job_id
                or process.get('job_name') != job or process.get('source_commit') != source_commit
                or process.get('termination') != 'exited' or type(process.get('exit_code')) is not int
                or process.get('exit_code') != 0
                or process.get('container_state_after_stop') != 'stopped'
                or not isinstance(process.get('runtime'), dict)
                or process['runtime'].get('system') != 'linux'
                or process['runtime'].get('machine') != 'x86_64'
                or process['runtime'].get('python') != receipt.get('python_version')
                or not isinstance(process.get('image_digest'), str)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', process['image_digest'])):
                raise ValueError(f"Missing, failed or mismatched local process evidence: {job}")
        if job_id in job_ids:
            raise ValueError(f"Duplicate job identity: {job}")
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
        reuse = None
        if profile in ('stable', 'layers'):
            reuse = verify_reused_backend(root, profile, receipt.get('backend_identity', {}), artifacts, process)
        results[job] = {"local_job_id" if local_run_id else "job_id": job_id,
                        "receipt": identity(root, str(path.relative_to(root))),
                        "test_counts": counts, "artifacts": artifacts}
        if reuse is not None:
            results[job]['build_provenance'] = reuse
        if local_run_id is not None:
            results[job]['process_receipt'] = identity(root, str(process_path.relative_to(root)))
            if profile == 'unified':
                unified_receipt, unified_process = receipt, process
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
    if (not tested or (local_run_id is None and len(tested) != 1)
        or (tested[0]['sha256'], tested[0]['size']) != (core['sha256'], core['size_bytes'])):
        raise ValueError("The installed-wheel native acceptance did not test the ordinary core wheel")
    if local_run_id is not None:
        results['native-unified']['preparation'] = verify_local_unified_preparation(
            root, source_commit, local_run_id, job_ids, unified_receipt, unified_process)
    result = {"schema": "fdisbull-ci-qualification-1", "status": "qualified", "source_commit": source_commit,
              "required_jobs": results,
              "package_inventory": identity(root, 'artifacts/receipts/package-payloads.json'),
              "release_authorized": False}
    if local_run_id is not None:
        result.update(execution_origin='local-linux', local_run_id=local_run_id)
    else:
        result['pipeline_id'] = str(pipeline_id)
    return result


def write_ordinary(root):
    payload = read(root / 'artifacts/receipts/package-payloads.json')
    if payload.get('source_commit') != os.environ['CI_COMMIT_SHA'] or payload.get('tracked_worktree_dirty') is not False:
        raise ValueError("Cannot certify dirty or wrong-source package inventory")
    passing_junit(root / 'artifacts/ordinary/tests.xml')
    return {"status": "passed", "profile": "ordinary", "source_commit": os.environ['CI_COMMIT_SHA'],
            **execution_identity(), "python_version": platform.python_version(),
            "node_version": subprocess.check_output(['node', '--version'], text=True).strip(),
            "test_results": [identity(root, 'artifacts/ordinary/tests.xml')],
            "artifacts": [identity(root, 'dist/' + v['name']) for v in payload['artifacts'].values()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--source-commit', default=os.environ.get('CI_COMMIT_SHA'))
    parser.add_argument('--pipeline-id', default=os.environ.get('CI_PIPELINE_ID'))
    parser.add_argument('--local-run-id', default=None)
    parser.add_argument('--write-ordinary', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Receipt exists; preserve it and choose a new output')
    try:
        result = write_ordinary(args.root) if args.write_ordinary else validate(args.root, args.source_commit, args.pipeline_id, local_run_id=args.local_run_id)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        parser.exit(2, f'Incomplete qualification: {exc}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(f"{result['status']}: {result['source_commit']} ({result.get('execution_origin', 'gitlab')}: {result.get('local_run_id', result.get('pipeline_id'))})")


if __name__ == '__main__':
    main()
