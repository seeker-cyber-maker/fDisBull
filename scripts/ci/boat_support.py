#!/usr/bin/env python3
"""Boat-only execution additions; preserve the retained local Linux contract.

The shared local driver remains authoritative for pinned upstream transport and
retained runtime validation. This module adds event-bound Boat origins and a
fresh network-disabled chat-kit consumer without replacing those local gates.
"""
from __future__ import annotations
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import uuid

_spec = importlib.util.spec_from_file_location('fdisbull_local_base', Path(__file__).with_name('local-linux.py'))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
for _name in dir(_base):
    if not _name.startswith('_'):
        globals()[_name] = getattr(_base, _name)
JOBS = dict(_base.JOBS, **{'chat-prepare': 'native-chat-prepare', 'chat-consumer': 'native-chat-consumer'})
IMAGES = dict(_base.IMAGES, **{'chat-prepare': 'docker.io/library/python:3.13.5-bookworm', 'chat-consumer': 'docker.io/library/python:3.13.5-bookworm'})
EXPECTED_BYTES = dict(_base.EXPECTED_BYTES, **{'chat-prepare': 32_000_000_000, 'chat-consumer': 32_000_000_000})
CHAT_ARCHIVE = '.native/chat/output/fdisbull-chat-offline.zip'


def expected_bytes(args, profile):
    override = getattr(args, 'expected_bytes', None)
    return EXPECTED_BYTES[profile] if override is None else override


def profiles_for(profile):
    if profile == 'qualify':
        return []
    if profile == 'all':
        return ['ordinary', 'stable', 'layers', 'unified-prepare', 'chat-prepare', 'chat-consumer', 'unified']
    return ['unified-prepare', 'unified'] if profile == 'unified' else [profile]

def job_environment(profile, sha, run_id, job_id, *, origin='local-linux', boat_sandbox_id=None, boat_worker_receipt=None):
    env = {'CI_PROJECT_DIR': '/work', 'CI_BUILDS_DIR': '/ci-builds',
           'CI_COMMIT_SHA': sha, 'CI_JOB_NAME': PREPARE_JOB if profile == 'unified-prepare' else JOBS[profile],
           'FDISBULL_EXECUTION_ORIGIN': origin,
           'FDISBULL_LOCAL_RUN_ID': run_id, 'FDISBULL_LOCAL_JOB_ID': job_id,
           'TMPDIR': '/ci-tmp', 'PIP_CACHE_DIR': '/ci-cache/pip',
           'PYTHONDONTWRITEBYTECODE': '1', 'DEBIAN_FRONTEND': 'noninteractive'}
    if origin == 'boat-linux':
        env.update(FDISBULL_BOAT_SANDBOX_ID=boat_sandbox_id,
                   FDISBULL_BOAT_WORKER_RECEIPT=json.dumps(boat_worker_receipt, sort_keys=True))
    if profile in ('stable', 'layers'):
        env.update(FDISBULL_PROFILE=profile,
                   FDISBULL_PATCH_DIRECTORY='experimental/dosbox-x' + ('/layers' if profile == 'layers' else ''),
                   FDISBULL_DOSBOX=f'/work/.native/backends/{profile}/dosbox-x',
                   FDISBULL_DOSBOX_SOURCE='/work/.native/dosbox-x')
    elif profile in ('unified', 'unified-prepare'):
        env.update(FDISBULL_PE_QEMU='/work/.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
                   FDISBULL_PE_KERNEL='/work/.native/pe/linux-amd64',
                   FDISBULL_PE_INITRAMFS='/work/.native/pe/runtime.cpio.gz',
                   FDISBULL_PE_FIXTURE='/work/.native/pe/oracle.exe',
                   FDISBULL_PE_EVIDENCE='/work/native-evidence/pe/artifacts', FDISBULL_REQUIRE_PE='1',
                   FDISBULL_DOSBOX='/work/.native/backends/layers/dosbox-x',
                   FDISBULL_MACHINE_QEMU='/work/.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
                   FDISBULL_DOS_KERNEL='/work/.native/pe/linux-amd64',
                   FDISBULL_DOS_INITRAMFS='/work/.native/pe/dos-runtime.cpio.gz',
                   FDISBULL_MACHINE_EVIDENCE='/work/native-evidence/unified/boot',
                   FDISBULL_DOS_QEMU_EVIDENCE='/work/native-evidence/unified/dos',
                   FDISBULL_REQUIRE_MACHINE='1', FDISBULL_REQUIRE_DOS_QEMU='1')
        if profile == 'unified-prepare':
            env.update(FDISBULL_LOCAL_DOCKER='0',
                       FDISBULL_LOCAL_DOCKER_BUILD_NETWORK='host',
                       DOCKER_HOST='unix:///var/run/docker.sock',
                       FDISBULL_UNIFIED_PREPARE_ONLY='1')
        else:
            env['FDISBULL_UNIFIED_PREPARED'] = '1'
    return env

def job_command(profile):
    setup = (
        'set -Eeuo pipefail; mkdir -p /work /ci-builds /ci-tmp /ci-cache/pip; '
        'cp -a /source/. /work/; cd /work; '
        'git config --global --add safe.directory /work; '
        "trap 'job_rc=$?; trap - EXIT; set +e; "
        'python scripts/ci/export-local-artifacts.py --work /work '
        '--output /run-data/exported --source-commit "$CI_COMMIT_SHA"; '
        'export_rc=$?; if [ "$export_rc" -ne 0 ]; then exit "$export_rc"; fi; '
        "exit \"$job_rc\"' EXIT; "
    )
    # Check the real guest before installations or compiler work. Rosetta is
    # recorded as a host implementation detail, not called hardware parity.
    runtime = ('import json,platform,sys; '
               'assert sys.platform == "linux" and platform.machine() == "x86_64"; '
               + ('assert platform.python_version() == "3.13.5"; ' if profile in ('layers', 'chat-prepare', 'chat-consumer')
                  else 'assert sys.version_info[:2] == (3,12); ')
               + 'print(json.dumps({"python":platform.python_version(),"machine":platform.machine(),"system":sys.platform}))')
    setup += 'python -c ' + shlex.quote(runtime) + ' > /run-data/runtime.json; '
    if profile == 'ordinary':
        return setup + ('apt-get update && apt-get install -y --no-install-recommends '
                        'ca-certificates curl xz-utils git build-essential clang libx11-dev && '
                        'bash scripts/ci/test-and-package.sh')
    if profile == 'chat-prepare':
        return setup + 'bash scripts/ci/native-chat-prepare.sh'
    if profile == 'unified-prepare':
        return setup + 'bash scripts/ci/native-unified.sh'
    if profile == 'unified':
        return setup + 'bash scripts/ci/unified-acceptance.sh'
    script = 'native-debugger'
    return setup + f'bash scripts/ci/{script}.sh && python scripts/ci/native-receipt.py {profile}'

def stage_backend_reuse(source, export_root, work, image_digest, profile):
    """Stage explicitly selected evidence; never change the retained build."""
    import native_backend_reuse
    if profile not in native_backend_reuse.PROFILES:
        raise ValueError('Unsupported original backend profile')
    directory = native_backend_reuse.PROFILES[profile]
    export_root = Path(export_root).resolve(strict=True)
    phase = export_root.parent.parent
    paths = {
        'dosbox-x': export_root / f'.native/backends/{profile}/dosbox-x',
        'build-identity.json': export_root / f'native-evidence/{profile}/backend-identity.json',
        'config.log': export_root / f'native-evidence/{profile}/config.log',
        'build-process.json': phase / 'process.json',
    }
    for path in paths.values():
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or unsafe original backend build evidence')
    build = json.loads(paths['build-identity.json'].read_text())
    build_sha = build.get('source_commit')
    if not isinstance(build_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', build_sha):
        raise ValueError('Invalid original backend build source')
    process = read_regular_json(paths['build-process.json'])
    if process.get('execution_origin') == 'boat-linux':
        old_source = phase / 'work'
        if old_source.is_symlink() or source_identity(old_source, generated_outputs=True)[0] != build_sha:
            raise ValueError('Original Boat source snapshot is not clean at build SHA')
        old_manifest_path = old_source / directory / 'source-manifest.json'
        old_manifest = subprocess.check_output(
            ['git', 'show', f'HEAD:{directory}/source-manifest.json'],
            cwd=old_source, env=safe_env(), timeout=60)
        if old_manifest_path.is_symlink() or old_manifest_path.read_bytes() != old_manifest:
            raise ValueError('Original Boat source manifest changed')
        verify_guest_postcheck(phase / 'guest-data', build_sha)
        paths.update({'build-boat-worker.json': phase.parent / 'qualification/artifacts/receipts/boat-worker.json',
                      'build-boat-run.json': phase.parent / 'qualification/artifacts/receipts/boat-run.json',
                      'build-source-postcheck.json': phase / 'guest-data/source-postcheck.json'})
        if any(path.is_symlink() or not path.is_file() for path in paths.values()):
            raise ValueError('Missing or unsafe original Boat build proof')
    else:
        old_manifest = subprocess.check_output(
            ['git', 'show', f'{build_sha}:{directory}/source-manifest.json'],
            cwd=source, env=safe_env(), timeout=60)
    stage = work / f'.native/reuse-{profile}'
    stage.mkdir(parents=True, exist_ok=False)
    for name, path in paths.items():
        shutil.copy2(path, stage / name)
    (stage / 'build-manifest.json').write_bytes(old_manifest)
    native_backend_reuse.verify(stage, work / directory / 'source-manifest.json', image_digest, profile)

def prepared_unified_stage(source, run_root, output, sha, run_id, *, origin='local-linux', boat_sandbox_id=None, boat_worker_receipt=None):
    """Require the completed real build, not merely a manifest with valid hashes."""
    phase = run_root / 'unified-prepare'
    process = read_regular_json(phase / 'process.json')
    marker = read_regular_json(phase / 'completed.json')
    job_id = process.get('local_job_id')
    try:
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid local preparation job identity') from None
    if (process.get('execution_origin') != origin
            or (origin == 'boat-linux' and (process.get('boat_sandbox_id') != boat_sandbox_id or process.get('boat_worker_receipt') != boat_worker_receipt))
            or process.get('source_commit') != sha or process.get('local_run_id') != run_id
            or process.get('job_name') != PREPARE_JOB or process.get('exit_code') != 0
            or type(process.get('exit_code')) is not int
            or process.get('termination') != 'exited'
            or process.get('container_state_after_stop') != 'stopped'
            or marker.get('local_job_id') != job_id or marker.get('source_commit') != sha
            or not isinstance(process.get('runtime'), dict)
            or process['runtime'].get('system') != 'linux'
            or process['runtime'].get('machine') != 'x86_64'
            or not process['runtime'].get('python', '').startswith('3.12.')):
        raise ValueError('Local unified preparation did not complete for this source and run')
    postcheck = verify_guest_postcheck(phase / 'guest-data', sha)
    copies = {'preparation-process.json': process,
              'preparation-source-postcheck.json': postcheck,
              'preparation-completed.json': marker}
    for name, value in copies.items():
        if read_regular_json(output / 'native-evidence/pe' / name) != value:
            raise ValueError('Changed local preparation provenance')
    unified_input_verifier(source).verify(output, sha, run_id, job_id, source_root=source)
    return process

def stage_prepared_unified(source, run_root, output, work, sha, run_id, *, origin='local-linux', boat_sandbox_id=None, boat_worker_receipt=None):
    process = prepared_unified_stage(source, run_root, output, sha, run_id, origin=origin, boat_sandbox_id=boat_sandbox_id, boat_worker_receipt=boat_worker_receipt)
    selections = (*UNIFIED_INPUTS, 'native-evidence/pe/**/*', '.native/pe/packages/*.whl')
    for pattern in selections:
        for path in output.glob(pattern):
            relative = path.relative_to(output)
            if any((output / Path(*relative.parts[:i])).is_symlink()
                   for i in range(1, len(relative.parts) + 1)):
                raise ValueError('Symlink in prepared runtime inputs')
            if not path.is_file():
                continue
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                with target.open('rb') as a, path.open('rb') as b:
                    if hashlib.file_digest(a, 'sha256').digest() != hashlib.file_digest(b, 'sha256').digest():
                        raise ValueError('Conflicting staged runtime input')
            else:
                shutil.copy2(path, target)
    unified_input_verifier(source).verify(work, sha, run_id, process['local_job_id'], source_root=work)
    return process

def artifact_identity(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe artifact: ' + name)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': name, 'sha256': digest, 'size': path.stat().st_size}

def write_chat_prepare_receipt(output, guest_data, process, sha, run_id, *, origin='local-linux', boat_sandbox_id=None, boat_worker_receipt=None):
    """Issue producer evidence only after the real process and guest export pass."""
    if (process.get('execution_origin') != origin
        or (origin == 'boat-linux' and (process.get('boat_sandbox_id') != boat_sandbox_id or process.get('boat_worker_receipt') != boat_worker_receipt))
        or process.get('source_commit') != sha or process.get('local_run_id') != run_id
        or process.get('job_name') != JOBS['chat-prepare']
        or type(process.get('exit_code')) is not int or process['exit_code'] != 0
        or process.get('termination') != 'exited' or process.get('container_state_after_stop') != 'stopped'
        or process.get('runtime') != {'system': 'linux', 'machine': 'x86_64', 'python': '3.13.5'}):
        raise ValueError('Chat producer process did not pass')
    verify_guest_postcheck(guest_data, sha)
    identity = artifact_identity(output, CHAT_ARCHIVE)
    if identity['size'] > 2_000_000_000 or process.get('archive') != identity:
        raise ValueError('Chat producer archive did not pass')
    receipt = {'schema': 'fdisbull-chat-prepare-job-v1', 'status': 'passed',
               'execution_origin': origin, 'source_commit': sha, 'test_source_commit': sha,
               'local_run_id': run_id, 'local_job_id': process['local_job_id'],
               'tracked_worktree_dirty': False, 'export_success': True, 'archive': identity}
    if origin == 'boat-linux':
        receipt.update(boat_sandbox_id=boat_sandbox_id, boat_worker_receipt=boat_worker_receipt)
    target = output / 'artifacts/receipts/chat-prepare.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    save(target, receipt)
    return receipt

def stage_chat_archive(run_root, output, stage, sha, run_id, *, origin='local-linux', boat_sandbox_id=None, boat_worker_receipt=None):
    process = read_regular_json(run_root / 'chat-prepare/process.json')
    marker = read_regular_json(run_root / 'chat-prepare/completed.json')
    receipt = read_regular_json(output / 'artifacts/receipts/chat-prepare.json')
    job = process.get('local_job_id')
    try:
        if str(uuid.UUID(job)) != job:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid chat producer identity') from None
    identity = artifact_identity(output, CHAT_ARCHIVE)
    if (identity['size'] > 2_000_000_000 or process.get('execution_origin') != origin
        or (origin == 'boat-linux' and (process.get('boat_sandbox_id') != boat_sandbox_id or process.get('boat_worker_receipt') != boat_worker_receipt or receipt.get('boat_sandbox_id') != boat_sandbox_id or receipt.get('boat_worker_receipt') != boat_worker_receipt))
        or receipt.get('schema') != 'fdisbull-chat-prepare-job-v1'
        or receipt.get('execution_origin') != origin
        or receipt.get('test_source_commit') != sha
        or receipt.get('tracked_worktree_dirty') is not False
        or receipt.get('export_success') is not True
        or process.get('source_commit') != sha
        or process.get('local_run_id') != run_id or process.get('job_name') != JOBS['chat-prepare']
        or type(process.get('exit_code')) is not int or process['exit_code'] != 0
        or process.get('termination') != 'exited' or process.get('container_state_after_stop') != 'stopped'
        or process.get('runtime') != {'system': 'linux', 'machine': 'x86_64', 'python': '3.13.5'}
        or marker.get('local_job_id') != job or marker.get('source_commit') != sha
        or process.get('archive') != identity or receipt.get('archive') != identity
        or receipt.get('local_job_id') != job or receipt.get('source_commit') != sha
        or receipt.get('local_run_id') != run_id or receipt.get('status') != 'passed'):
        raise ValueError('Chat producer or archive does not match this run')
    verify_guest_postcheck(run_root / 'chat-prepare/guest-data', sha)
    stage.mkdir()
    shutil.copy2(output / CHAT_ARCHIVE, stage / 'archive.zip')
    with (stage / 'archive.zip').open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != identity['sha256']:
            raise ValueError('Staged chat archive differs from producer')
    return process, identity

def collect(work, output):
    _base.collect(work, output)
    root = work / '.native/chat/output'
    if root.exists():
        for path in root.iterdir():
            if path.is_symlink() or not path.is_file():
                raise ValueError('Unsafe chat producer output')
            relative = path.relative_to(work)
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if artifact_identity(work, str(relative)) != artifact_identity(output, str(relative)):
                    raise ValueError('Conflicting chat output')
            else:
                shutil.copy2(path, target)

