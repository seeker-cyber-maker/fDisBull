#!/usr/bin/env python3
"""Qualify one CI commit from all mandatory job artifacts; never query a provider.

Run in the dependent GitLab summary job, whose needs require every contributing
job to succeed. This checks artifact identities and coverage receipts as well as
the dependency graph. A routine fast-only pipeline cannot produce this receipt.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent / "ci"))
from execution_identity import canonical_uuid, execution_identity, validate_boat_receipt_identity
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


def boat_identity(root, source_commit, run_id):
    run = read(local_path(root, 'artifacts/receipts/boat-run.json'))
    proof = validate_boat_receipt_identity(run.get('boat_worker_receipt'))
    verify_artifact(root, proof)
    worker = read(local_path(root, proof['path']))
    sandbox = run.get('boat_sandbox_id')
    if (run.get('execution_origin') != 'boat-linux' or run.get('source_commit') != source_commit
        or run.get('local_run_id') != run_id or not isinstance(sandbox, str)
        or not re.fullmatch(r'bx_[A-Za-z0-9_-]+', sandbox)
        or worker.get('schema') != 'fdisbull-boat-worker-v1'
        or worker.get('execution_origin') != 'boat-linux' or worker.get('boat_sandbox_id') != sandbox
        or worker.get('type') not in ('small', 'default', 'large', 'xlarge') or worker.get('architecture') != 'x86_64'):
        raise ValueError('Boat run or worker identity mismatch')
    canonical_uuid(worker.get('host_boot_id'))
    try:
        observed = datetime.datetime.fromisoformat(worker['observed_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('Missing timezone')
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid Boat worker observation time') from exc
    return {'boat_sandbox_id': sandbox, 'boat_worker_receipt': proof}


def check_execution_binding(record, origin, boat):
    if record.get('execution_origin') != origin:
        raise ValueError('Execution origin mismatch')
    if origin == 'boat-linux':
        if any(record.get(key) != value for key, value in boat.items()):
            raise ValueError('Boat worker identity mismatch')
    elif 'boat_sandbox_id' in record or 'boat_worker_receipt' in record:
        raise ValueError('Local execution cannot claim a Boat worker')


REUSE_FILES = {
    'build_identity_sha256': 'build-identity.json',
    'build_process_sha256': 'build-process.json',
    'build_manifest_sha256': 'build-manifest.json',
    'build_config_sha256': 'config.log',
}
REUSE_FIELDS = frozenset((*REUSE_FILES, 'build_source_commit', 'build_image_digest'))
BOAT_REUSE_FILES = {'build_boat_worker_sha256': 'build-boat-worker.json',
                    'build_boat_run_sha256': 'build-boat-run.json',
                    'build_source_postcheck_sha256': 'build-source-postcheck.json'}
BOAT_REUSE_FIELDS = frozenset((*BOAT_REUSE_FILES, 'build_execution_origin'))


def verify_reused_backend(root, profile, backend, artifacts, process):
    """Re-read retained build provenance; never infer a build from test success."""
    base = f'native-evidence/{profile}/'
    indicators = ('reuse-provenance.json', 'build-identity.json', 'build-process.json', 'build-manifest.json', *BOAT_REUSE_FILES.values())
    present = lambda path: path.exists() or path.is_symlink()
    if not (REUSE_FIELDS | BOAT_REUSE_FIELDS).intersection(backend) and not any(present(root / base / name) for name in indicators):
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
        or build_process.get('execution_origin') not in ('local-linux', 'boat-linux')
        or build_process.get('job_name') != JOBS[profile]
        or not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image)
        or build_process.get('image_digest') != image or process.get('image_digest') != image):
        raise ValueError('Reused backend build source, process or image mismatch')
    if build_process.get('execution_origin') == 'boat-linux':
        if not BOAT_REUSE_FIELDS.issubset(backend) or backend.get('build_execution_origin') != 'boat-linux':
            raise ValueError('Original Boat reuse provenance is incomplete')
        for field, name in BOAT_REUSE_FILES.items():
            item = identity(root, base + name)
            if item['sha256'] != backend[field]:
                raise ValueError('Original Boat reuse proof hash mismatch: ' + name)
            proofs[name] = item
        spec = importlib.util.spec_from_file_location('fdisbull_native_boat_reuse',
                       Path(__file__).resolve().parent / 'ci/native_backend_reuse.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checked = module.boat_provenance(root / base, build_process, build_sha)
        if any(backend.get(key) != value for key, value in checked.items()):
            raise ValueError('Original Boat reuse provenance mismatch')
        if present(marker_path) and any(marker.get(key) != backend[key] for key in BOAT_REUSE_FIELDS):
            raise ValueError('Original Boat reuse marker mismatch')
    elif BOAT_REUSE_FIELDS.intersection(backend) or any(present(root / base / name) for name in BOAT_REUSE_FILES.values()):
        raise ValueError('Local reuse cannot claim Boat build provenance')
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


def verify_local_unified_preparation(root, source_commit, run_id, canonical_job_ids, receipt, process, origin, boat):
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
    if origin == 'boat-linux':
        check_execution_binding(completed, origin, boat)
    check_execution_binding(build, origin, boat)
    if (build.get('source_commit') != source_commit
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
    reused = verify_unified_base_reuse(root, checked, receipt['backend_identity'], build)
    return {'build_job_id': build_job, 'prepared_manifest': manifest_ref, 'reused_base': reused, **proof}


def verify_unified_base_reuse(root, manifest, backend, preparation_process):
    """A retained compiler/OS base never becomes a fabricated current build."""
    marker = 'native-evidence/pe/reuse/origin.json'
    present = (root / marker).exists() or (root / marker).is_symlink()
    declared = backend.get('reuse_origin')
    if not present and declared is None:
        return None
    if declared != marker:
        raise ValueError('Unified reused base needs its typed origin marker')
    local_path(root, marker)
    source = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('fdisbull_unified_base_reuse', source / 'scripts/ci/unified-base-reuse.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    origin = module.verify_reuse(root, source)
    if origin['image_digest'] != preparation_process.get('image_digest'):
        raise ValueError('Unified reused base image differs from current preparation')
    for key, filename in (('FDISBULL_PE_QEMU', 'qemu'), ('FDISBULL_PE_KERNEL', 'kernel'),
                          ('FDISBULL_PE_FIXTURE', 'oracle')):
        if manifest['inputs'][key]['sha256'] != origin['files'][filename]:
            raise ValueError('Current unified input differs from its reused original: ' + key)
    firmware = {item['path'].replace('native-evidence/pe/firmware/', 'firmware/', 1): item['sha256']
                for item in manifest['firmware']}
    if firmware != origin['firmware']:
        raise ValueError('Current firmware differs from the reused original')
    if identity(root, 'native-evidence/pe/runtime-packages.txt')['sha256'] != origin['files']['wine-packages.txt']:
        raise ValueError('Current Wine package inventory differs from the reused original')
    for name in ('runtime-preparation.json', 'dos-runtime-preparation.json'):
        if read(local_path(root, 'native-evidence/pe/' + name)).get('base_sha256') != origin['files']['wine-base']:
            raise ValueError('Current runtime was not rebuilt from the declared reused base')
    return {'origin': identity(root, marker), 'original_source_commit': origin['source_commit'],
            'original_build_job_id': origin['local_job_id']}


def passing_junit(path, *, native=False):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if (any(v < 0 for v in counts.values()) or counts['tests'] <= counts['skipped'] or counts['failures'] or counts['errors']
        or (native and counts['skipped'])):
        raise ValueError(f"Missing, failing or entirely skipped tests: {path}: {counts}")
    return counts


CHAT_CHECKS = frozenset({'dos_screenshot','dos_keyboard','dos_restore','pe_breakpoint','pe_memory',
    'pe_screenshot','pe_click','pe_trace','pe_restore','solver_counterexample','solver_equivalence',
    'player_save','player_resume','skill_fdisbull','skill_gamefaqs'})


def verify_chat_consumer(root, source_commit, local_run_id, other_jobs, package_artifacts, origin, boat):
    """Require a separately executed, artifact-bound offline consumer run."""
    if local_run_id is None:
        raise ValueError('Complete chat qualification requires local consumer process evidence')
    receipt_path = 'artifacts/receipts/chat-consumer.json'
    process_path = 'artifacts/receipts/local-process-chat-consumer.json'
    producer_path = 'artifacts/receipts/local-process-chat-prepare.json'
    prepare_path = 'artifacts/receipts/chat-prepare.json'
    preparation = read(local_path(root, prepare_path))
    receipt = read(local_path(root, receipt_path))
    process = read(local_path(root, process_path))
    producer = read(local_path(root, producer_path))
    for record in (receipt, preparation, process, producer):
        check_execution_binding(record, origin, boat)
    job_id = canonical_uuid(receipt.get('local_job_id'))
    producer_id = canonical_uuid(receipt.get('producer_job_id'))
    if job_id == producer_id or job_id in other_jobs or producer_id in other_jobs:
        raise ValueError('Chat producer and consumer job identities must be distinct')
    if (receipt.get('schema') != 'fdisbull-chat-consumer-job-v1' or receipt.get('status') != 'passed'
        or receipt.get('source_commit') != source_commit or receipt.get('test_source_commit') != source_commit
        or receipt.get('execution_origin') != origin or receipt.get('local_run_id') != local_run_id
        or receipt.get('source_access') != 'absent' or receipt.get('source_check') != 'artifact-and-host-clone'):
        raise ValueError('Chat consumer receipt source or run mismatch')
    for observed, expected_id, name in ((process,job_id,'chat-native-consumer'),(producer,producer_id,'chat-native-prepare')):
        if (observed.get('execution_origin') != origin or observed.get('local_run_id') != local_run_id
            or observed.get('local_job_id') != expected_id or observed.get('job_name') != name
            or observed.get('source_commit') != source_commit or observed.get('termination') != 'exited'
            or type(observed.get('exit_code')) is not int or observed.get('exit_code') != 0
            or observed.get('container_state_after_stop') != 'stopped'
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(observed.get('image_digest', '')))
            or not isinstance(observed.get('runtime'), dict) or observed['runtime'].get('system') != 'linux'
            or observed['runtime'].get('machine') != 'x86_64' or observed['runtime'].get('python') != '3.13.5'):
            raise ValueError('Chat producer or consumer process evidence failed')
    if (preparation.get('schema') != 'fdisbull-chat-prepare-job-v1' or preparation.get('status') != 'passed'
        or preparation.get('execution_origin') != origin or preparation.get('source_commit') != source_commit
        or preparation.get('test_source_commit') != source_commit or preparation.get('local_run_id') != local_run_id
        or preparation.get('local_job_id') != producer_id or preparation.get('tracked_worktree_dirty') is not False
        or preparation.get('export_success') is not True):
        raise ValueError('Chat preparation receipt source or run mismatch')
    archive, verification = receipt.get('archive'), receipt.get('verifier')
    host_postcheck, junit = receipt.get('host_source_postcheck'), receipt.get('junit')
    for item in (archive, verification, host_postcheck, junit): verify_artifact(root, item)
    postcheck = read(local_path(root, host_postcheck['path']))
    if (postcheck.get('schema') != 'fdisbull-chat-host-source-postcheck-v1'
        or postcheck.get('source_commit') != source_commit or postcheck.get('expected_source_commit') != source_commit
        or postcheck.get('tracked_worktree_dirty') is not False or postcheck.get('export_success') is not True
        or postcheck.get('archive_sha256') != archive['sha256']):
        raise ValueError('Chat host source postcheck mismatch')
    passing_junit(local_path(root, junit['path']), native=True)
    if archive['size'] > 500_000_000:
        raise ValueError('Chat archive exceeds 500 MB qualification limit')
    if process.get('archive') != archive or producer.get('archive') != archive or preparation.get('archive') != archive or process.get('verifier') != verification or process.get('junit') != junit or process.get('host_source_postcheck') != host_postcheck:
        raise ValueError('Chat process artifacts do not match receipt')
    result = read(local_path(root, verification['path']))
    if (result.get('schema') != 'fdisbull-chat-consumer-verification-v1' or result.get('status') != 'passed'
        or result.get('source_commit') != source_commit or result.get('test_source_commit') != source_commit
        or result.get('archive_sha256') != archive['sha256'] or result.get('python') != '3.13.5'
        or result.get('network_interfaces') != ['lo'] or result.get('python_origin') != 'kit'
        or result.get('python_mappings') != 'kit' or result.get('loader_closure') != 'kit-lib'
        or type(result.get('elf_objects_checked')) is not int or result['elf_objects_checked'] < 1
        or type(result.get('skipped')) is not int or result['skipped'] != 0
        or type(result.get('native_failures')) is not int or result['native_failures'] != 0
        or result.get('profiles') != ['dos','wine','player','z3']):
        raise ValueError('Chat verifier isolation, native or identity evidence failed')
    checks = result.get('checks')
    if not isinstance(checks, dict) or set(checks) != CHAT_CHECKS or any(checks[name] is not True for name in CHAT_CHECKS):
        raise ValueError('Chat verifier required capability missing or failed')
    for name in ('dos_screenshot_sha256','pe_screenshot_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(result.get(name, ''))):
            raise ValueError('Chat screenshot identity missing')
    runtime = result.get('runtime_sha256')
    if not isinstance(runtime, dict) or set(runtime) != {'dos','wine'} or any(not re.fullmatch(r'[0-9a-f]{64}', str(x)) for x in runtime.values()):
        raise ValueError('Chat prepared runtime identity missing')
    with zipfile.ZipFile(local_path(root, archive['path'])) as zipped:
        members = [i for i in zipped.infolist() if i.filename == 'fdisbull-chat-offline/MANIFEST.json']
        if len(members) != 1 or members[0].file_size > 2 * 1024 * 1024:
            raise ValueError('Chat archive manifest missing or duplicated')
        data = zipped.read(members[0])
    if hashlib.sha256(data).hexdigest() != result.get('manifest_sha256'):
        raise ValueError('Chat manifest differs from consumer evidence')
    manifest = json.loads(data)
    if manifest.get('identities', {}).get('source_commit') != source_commit or manifest.get('identities', {}).get('test_source_commit') != source_commit:
        raise ValueError('Chat manifest source identity mismatch')
    wheels = manifest.get('wheel_artifacts')
    if not isinstance(wheels, list): raise ValueError('Chat wheel identities missing')
    for kind in ('core','player'):
        expected = package_artifacts[kind]
        matches = [w for w in wheels if isinstance(w, dict) and w.get('name') == expected['name']]
        if len(matches) != 1 or matches[0] != {'name':expected['name'],'sha256':expected['sha256'],'size':expected['size_bytes']}:
            raise ValueError('Chat wheel differs from ordinary package: ' + kind)
    return {'receipt':identity(root, receipt_path),'process_receipt':identity(root,process_path),
            'producer_process_receipt':identity(root,producer_path),'preparation_receipt':identity(root,prepare_path),'archive':archive,'verifier':verification,
            'local_job_id':job_id,'producer_job_id':producer_id}


def validate(root, source_commit, pipeline_id=None, *, local_run_id=None, legacy_dos_only=False):
    if not isinstance(source_commit, str) or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError("Qualification requires an exact commit")
    if local_run_id is None:
        if not re.fullmatch('[0-9]+', str(pipeline_id)):
            raise ValueError("Qualification requires an exact pipeline ID")
    else:
        canonical_uuid(local_run_id)
        if pipeline_id is not None:
            raise ValueError("Local qualification cannot claim a GitLab pipeline")
    origin = 'gitlab' if local_run_id is None else read(local_path(root, 'artifacts/receipts/ordinary.json')).get('execution_origin')
    if origin not in ('gitlab', 'local-linux', 'boat-linux') or (local_run_id is not None and origin == 'gitlab'):
        raise ValueError('Invalid qualification execution origin')
    boat = boat_identity(root, source_commit, local_run_id) if origin == 'boat-linux' else None
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
            check_execution_binding(receipt, origin, boat)
            if (receipt.get('execution_origin') != origin
                or receipt.get('local_run_id') != local_run_id
                or 'pipeline_id' in receipt or 'job_id' in receipt):
                raise ValueError(f"Job origin or local run mismatch: {job}")
            job_id = canonical_uuid(receipt.get('local_job_id'))
            process_path = root / f'artifacts/receipts/local-process-{profile}.json'
            process = read(process_path)
            check_execution_binding(process, origin, boat)
            if (process.get('execution_origin') != origin
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
            root, source_commit, local_run_id, job_ids, unified_receipt, unified_process, origin, boat)
    chat = None if legacy_dos_only else verify_chat_consumer(root, source_commit, local_run_id, job_ids, package_artifacts, origin, boat)
    result = {"schema": "fdisbull-ci-qualification-1", "status": "legacy-dos-only" if legacy_dos_only else "qualified", "source_commit": source_commit,
              "required_jobs": results,
              "package_inventory": identity(root, 'artifacts/receipts/package-payloads.json'),
              "release_authorized": False}
    if chat is not None:
        result['chat_consumer'] = chat
    if local_run_id is not None:
        result.update(execution_origin=origin, local_run_id=local_run_id)
        if boat is not None:
            result.update(boat)
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
    parser.add_argument('--legacy-dos-only', action='store_true', help='Report a partial legacy result without qualifying chat delivery')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Receipt exists; preserve it and choose a new output')
    try:
        result = write_ordinary(args.root) if args.write_ordinary else validate(args.root, args.source_commit, args.pipeline_id, local_run_id=args.local_run_id, legacy_dos_only=args.legacy_dos_only)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        parser.exit(2, f'Incomplete qualification: {exc}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(f"{result['status']}: {result['source_commit']} ({result.get('execution_origin', 'gitlab')}: {result.get('local_run_id', result.get('pipeline_id'))})")


if __name__ == '__main__':
    main()
