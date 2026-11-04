#!/usr/bin/env python3
"""Run finite, exact-commit Linux checks using the guarded local container CLI.

Each leg has a separate shallow source clone and retained log. No provider API,
runner credential, global service installation or automatic retry is involved.
Containers are stopped, not pruned; their files and failed attempts are retained.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import shlex
import signal
import subprocess
import sys
import uuid

CLI = Path('/Users/tiga/.local/bin/container')
ADMISSION = Path('/Users/tiga/.codex/bin/storage_admit.py')
JOBS = {'ordinary': 'test-and-package', 'stable': 'native-debugger-stable',
        'layers': 'native-debugger-layers', 'unified': 'native-unified',
        'chat-prepare': 'chat-native-prepare', 'chat-consumer': 'chat-native-consumer'}
PREPARE_JOB = 'native-unified-prepare'
IMAGES = {'ordinary': 'docker.io/library/python:3.12-bookworm',
          'stable': 'docker.io/library/python:3.12-bookworm',
          'layers': 'docker.io/library/python:3.13.5-bookworm',
          'unified': 'docker.io/library/python:3.12-bookworm',
          'unified-prepare': 'docker.io/library/python:3.12-bookworm',
          'chat-prepare': 'docker.io/library/python:3.13.5-bookworm',
          'chat-consumer': 'docker.io/library/python:3.13.5-bookworm'}
UNIFIED_INPUTS = ('.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
                  '.native/pe/linux-amd64', '.native/pe/runtime.cpio.gz',
                  '.native/pe/dos-runtime.cpio.gz', '.native/pe/oracle.exe',
                  '.native/backends/layers/dosbox-x')
EXPECTED_BYTES = {'ordinary': 12_000_000_000, 'stable': 14_000_000_000,
                  'layers': 18_000_000_000, 'unified-prepare': 35_000_000_000,
                  'unified': 16_000_000_000, 'chat-prepare': 8_000_000_000,
                  'chat-consumer': 8_000_000_000}


def profiles_for(profile):
    if profile == 'qualify':
        return []
    if profile == 'all':
        return ['ordinary', 'stable', 'layers', 'unified-prepare', 'chat-prepare', 'chat-consumer', 'unified']
    return ['unified-prepare', 'unified'] if profile == 'unified' else [profile]


def expected_bytes(args, profile):
    override = getattr(args, 'expected_bytes', None)
    return EXPECTED_BYTES[profile] if override is None else override


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def safe_env():
    # Keep provider job identities and Git trace switches out of host command
    # context. Guest environment is separately enumerated in job_environment.
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('GIT_TRACE', 'GIT_CURL_VERBOSE', 'CI_'))}


def capture(args, *, cwd=None, timeout=60):
    return subprocess.check_output(args, cwd=cwd, env=safe_env(),
                                   text=True, stderr=subprocess.PIPE, timeout=timeout)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def source_identity(source, *, generated_outputs=False):
    status = ['git', 'status', '--porcelain']
    if generated_outputs:
        status.append('--untracked-files=no')
    if capture(status, cwd=source).strip():
        raise ValueError('Source must be clean, including new authored files')
    sha = capture(['git', 'rev-parse', 'HEAD'], cwd=source).strip()
    branch = capture(['git', 'symbolic-ref', '--short', 'HEAD'], cwd=source).strip()
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Expected one exact source commit')
    return sha, branch


def clone_source(source, destination, sha, branch):
    # --no-local uses a shallow upload-pack transfer, rather than copying the
    # original Git config, worktree pointer, credentials or complete history.
    capture(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-local', '--depth', '1', '--single-branch',
             '--branch', branch, str(source), str(destination)], timeout=180)
    if source_identity(destination) != (sha, branch):
        raise ValueError('Source moved during snapshot; preserve this attempt and start a new run')


def image_identity(value, architecture="amd64"):
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError('Expected exactly one local image inspection')
    config = value[0]['configuration']
    index_digest = config['descriptor']['digest']
    variants = [v for v in value[0]['variants']
                if v['platform'].get('architecture') == architecture
                and v['platform'].get('os') == 'linux']
    if len(variants) != 1:
        raise ValueError(f'The pulled image must contain exactly one Linux {architecture} variant')
    digest = variants[0]['digest']
    if not all(re.fullmatch(r'sha256:[0-9a-f]{64}', d) for d in (index_digest, digest)):
        raise ValueError('Invalid immutable image identity')
    # Whitelist fields: image/container inspection also contains environment
    # variables and must never be printed wholesale.
    return {'image_digest': digest, 'image_index_digest': index_digest,
            'image_reference': config['name'].split('@')[0].rsplit(':', 1)[0] + '@' + index_digest}


def job_environment(profile, sha, run_id, job_id):
    env = {'CI_PROJECT_DIR': '/work', 'CI_BUILDS_DIR': '/ci-builds',
           'CI_COMMIT_SHA': sha, 'CI_JOB_NAME': PREPARE_JOB if profile == 'unified-prepare' else JOBS[profile],
           'FDISBULL_EXECUTION_ORIGIN': 'local-linux',
           'FDISBULL_LOCAL_RUN_ID': run_id, 'FDISBULL_LOCAL_JOB_ID': job_id,
           'TMPDIR': '/ci-tmp', 'PIP_CACHE_DIR': '/ci-cache/pip',
           'PYTHONDONTWRITEBYTECODE': '1', 'DEBIAN_FRONTEND': 'noninteractive'}
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


def unified_command(image, environment):
    """Run the AMD64 job inside a native ARM64 VM's isolated Docker daemon."""
    pinned = image['image_reference'].split('@', 1)[0] + '@' + image['image_digest']
    args = ['docker', 'run', '--name', 'fdisbull-unified-' + environment['FDISBULL_LOCAL_JOB_ID'][:8],
            '--platform', 'linux/amd64', '--network', 'host',
            '--mount', 'type=bind,src=/source,dst=/source,readonly',
            '--mount', 'type=bind,src=/run-data,dst=/run-data',
            '--mount', 'type=bind,src=/run/fdisbull-local-docker/docker.sock,dst=/var/run/docker.sock']
    for key, value in environment.items():
        args.extend(['--env', key + '=' + value])
    args.extend([pinned, 'bash', '-ec', job_command('unified-prepare')])
    return ('set -Eeuo pipefail; export DEBIAN_FRONTEND=noninteractive; '
            'apt-get update; apt-get install -y --no-install-recommends docker.io; '
            'mkdir -p /run-data/orchestrator; cd /run-data/orchestrator; '
            'export FDISBULL_EXECUTION_ORIGIN=local-linux FDISBULL_LOCAL_DOCKER=1; '
            'source /source/scripts/ci/local-docker.sh; '
            + shlex.join(['docker', 'pull', '--platform', 'linux/amd64', pinned]) + '; '
            + shlex.join(args))


def admit(parent, expected, reserve):
    result = subprocess.run([sys.executable, str(ADMISSION), '--path', str(parent),
                             '--expected-bytes', str(expected), '--destination-reserve-bytes', str(reserve)],
                            env=safe_env(), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('Storage admission rejected: ' + result.stdout.strip())
    return json.loads(result.stdout)


def admit_destinations(parent, expected, reserve):
    result = {'output': admit(parent, expected, reserve)}
    # Image layers, guest root disks and the builder always use CACHE, even
    # when the caller keeps source/results on the separate CODEX pool.
    store = Path('/Volumes/CACHE/AppleContainer')
    if os.stat(parent).st_dev != os.stat(store).st_dev:
        result['container_store'] = admit(store, expected, reserve)
    return result


def run_container(args, log, timeout, name):
    termination = 'exited'
    with log.open('x') as stream:
        process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT,
                                   env=safe_env(), start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            termination = 'timeout-or-interrupted'
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            code = process.returncode
        finally:
            # Stop only this uniquely named job; never stop unrelated services
            # or prune images/containers as part of qualification.
            stopped = subprocess.run([str(CLI), 'stop', name], env=safe_env(),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45)
    try:
        state = json.loads(capture([str(CLI), 'inspect', name]))[0]['status']['state']
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        state = 'unknown'
    return code, termination, process.pid, stopped.returncode, state


def collect(work, output):
    selections = ['dist/*', 'artifacts/receipts/*.json', 'artifacts/ordinary/*',
                  'native-evidence/**/*', '.native/backends/**/*', '.native/offline/output/*',
                  '.native/pe/packages/*.whl', '.native/chat/output/*', *UNIFIED_INPUTS]
    for pattern in selections:
        for path in work.glob(pattern):
            relative = path.relative_to(work)
            if any((work / Path(*relative.parts[:i])).is_symlink()
                   for i in range(1, len(relative.parts) + 1)):
                raise ValueError('Symlink in selected CI outputs')
            if not path.is_file():
                continue
            target = output / path.relative_to(work)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
                    raise ValueError('Conflicting outputs: ' + str(target.relative_to(output)))
            else:
                shutil.copy2(path, target)


def verify_guest_postcheck(guest_data, sha):
    path = guest_data / 'source-postcheck.json'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Guest source postcheck missing or invalid')
    try:
        postcheck = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError('Guest source postcheck missing or invalid') from exc
    if (not isinstance(postcheck, dict) or postcheck.get('source_commit') != sha
            or postcheck.get('expected_source_commit') != sha
            or postcheck.get('tracked_worktree_dirty') is not False
            or postcheck.get('export_success') is not True
            or not (guest_data / 'exported').is_dir()
            or (guest_data / 'exported').is_symlink()):
        raise ValueError('Guest source postcheck or evidence export failed')
    return postcheck


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
    old_manifest = subprocess.check_output(
        ['git', 'show', f'{build_sha}:{directory}/source-manifest.json'],
        cwd=source, env=safe_env(), timeout=60)
    stage = work / f'.native/reuse-{profile}'
    stage.mkdir(parents=True, exist_ok=False)
    for name, path in paths.items():
        shutil.copy2(path, stage / name)
    (stage / 'build-manifest.json').write_bytes(old_manifest)
    native_backend_reuse.verify(stage, work / directory / 'source-manifest.json', image_digest, profile)


def unified_input_verifier(source):
    """Load the candidate's pure verifier without importing its product code."""
    script = source / 'scripts/ci/unified-runtime-inputs.py'
    spec = importlib.util.spec_from_file_location('fdisbull_ci_unified_inputs', script)
    module = importlib.util.module_from_spec(spec)
    original = sys.path[:]
    try:
        sys.path.insert(0, str(script.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original
    return module


def read_regular_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Missing or invalid local preparation proof')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Invalid local preparation proof object')
    return value


def prepared_unified_stage(source, run_root, output, sha, run_id):
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
    if (process.get('execution_origin') != 'local-linux'
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


def stage_prepared_unified(source, run_root, output, work, sha, run_id):
    process = prepared_unified_stage(source, run_root, output, sha, run_id)
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


CHAT_ARCHIVE = '.native/chat/output/fdisbull-chat-offline.zip'


def artifact_identity(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe artifact: ' + name)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': name, 'sha256': digest, 'size': path.stat().st_size}



def write_chat_prepare_receipt(output, guest_data, process, sha, run_id):
    """Issue producer evidence only after the real process and guest export pass."""
    if (process.get('execution_origin') != 'local-linux'
        or process.get('source_commit') != sha or process.get('local_run_id') != run_id
        or process.get('job_name') != JOBS['chat-prepare']
        or type(process.get('exit_code')) is not int or process['exit_code'] != 0
        or process.get('termination') != 'exited' or process.get('container_state_after_stop') != 'stopped'
        or process.get('runtime') != {'system': 'linux', 'machine': 'x86_64', 'python': '3.13.5'}):
        raise ValueError('Chat producer process did not pass')
    verify_guest_postcheck(guest_data, sha)
    identity = artifact_identity(output, CHAT_ARCHIVE)
    if identity['size'] > 500_000_000 or process.get('archive') != identity:
        raise ValueError('Chat producer archive did not pass')
    receipt = {'schema': 'fdisbull-chat-prepare-job-v1', 'status': 'passed',
               'execution_origin': 'local-linux', 'source_commit': sha, 'test_source_commit': sha,
               'local_run_id': run_id, 'local_job_id': process['local_job_id'],
               'tracked_worktree_dirty': False, 'export_success': True, 'archive': identity}
    target = output / 'artifacts/receipts/chat-prepare.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    save(target, receipt)
    return receipt


def stage_chat_archive(run_root, output, stage, sha, run_id):
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
    if (identity['size'] > 500_000_000 or process.get('execution_origin') != 'local-linux'
        or receipt.get('schema') != 'fdisbull-chat-prepare-job-v1'
        or receipt.get('execution_origin') != 'local-linux'
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


def consumer_command(cli, name, image, stage, guest_data, bootstrap):
    # The only input mount is the archive and small bootstrap; no checkout or
    # host runtime is exposed to the consumer.
    return [str(cli), 'run', '--name', name, '--arch', 'amd64', '--rosetta',
            '--cpus', '4', '--memory', '8G', '--workdir', '/', '--cap-add', 'SYS_ADMIN',
            '--mount', f'type=bind,source={stage},target=/input,readonly',
            '--mount', f'type=bind,source={guest_data},target=/run-data',
            image['image_reference'], 'bash', '-ec', bootstrap]


def execute(args):
    source = args.source.resolve()
    sha, branch = source_identity(source)
    run_root = args.output.absolute()
    if not any(run_root.is_relative_to(Path(p)) for p in ('/Volumes/CACHE', '/Volumes/CODEX')):
        raise ValueError('Use an external CACHE or CODEX output directory')
    if run_root.is_relative_to(source) or source.is_relative_to(run_root):
        raise ValueError('Output must be outside the source checkout')
    parent = run_root if run_root.exists() else run_root.parent
    # Initial control-file admission is small; every new material leg gets its
    # own budget after completed legs have been checked. A resumed preparation
    # must not require the original compiler allocation a second time.
    if args.profile == 'qualify':
        if not run_root.is_dir() or not (run_root / 'run.json').is_file():
            raise ValueError('Readback qualification requires an existing local run')
    else:
        admit_destinations(parent, 0, args.reserve_bytes)
    run_root.mkdir(exist_ok=True)
    manifest_path = run_root / 'run.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest['source_commit'] != sha or manifest['source'] != str(source):
            raise ValueError('Cannot resume a different source commit or checkout')
    else:
        manifest = {'schema': 'fdisbull-local-linux-run-1', 'execution_origin': 'local-linux',
                    'local_run_id': str(uuid.uuid4()), 'source_commit': sha, 'source': str(source),
                    'created_at': now(), 'host_platform': platform.platform()}
        save(manifest_path, manifest)
    output = run_root / 'qualification'
    output.mkdir(exist_ok=True)
    profiles = profiles_for(args.profile)
    for profile in profiles:
        reuse_backend = getattr(args, f'reuse_{profile}_backend', None) if profile in ('stable', 'layers') else None
        receipt_path = output / f'artifacts/receipts/local-process-{profile}.json'
        if receipt_path.exists():
            marker = run_root / profile / 'completed.json'
            process = json.loads(receipt_path.read_text())
            if (marker.is_file() and process.get('exit_code') == 0
                    and json.loads(marker.read_text()).get('local_job_id') == process.get('local_job_id')):
                if profile == 'unified-prepare':
                    prepared_unified_stage(source, run_root, output, sha, manifest['local_run_id'])
                print(f'{profile}: retained completed leg', flush=True)
                continue
            raise ValueError('Failed attempt retained; use a new run directory')
        if profile != 'ordinary' and not (output / 'artifacts/receipts/ordinary.json').exists():
            raise ValueError('Ordinary package acceptance must pass first')
        if profile in ('unified', 'unified-prepare', 'chat-prepare') and not all((output / f'artifacts/receipts/native-{p}.json').exists() for p in ('stable', 'layers')):
            raise ValueError('Both DOS native profiles must pass before unified acceptance')
        phase = run_root / profile
        phase.mkdir()  # never overwrite an interrupted or failed attempt
        reuse_unified = getattr(args, 'reuse_unified_base', None) if profile == 'unified-prepare' else None
        reuse_module = None
        if reuse_unified is not None:
            script = source / 'scripts/ci/unified-base-reuse.py'
            spec = importlib.util.spec_from_file_location('unified_base_reuse', script)
            reuse_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(reuse_module)
            donor_process = read_regular_json(Path(reuse_unified).resolve(strict=True).parent.parent / 'process.json')
            reuse_module.validate(reuse_unified, source, donor_process.get('image_digest'))
        estimate = (8_000_000_000 if reuse_unified is not None and args.expected_bytes is None
                    else expected_bytes(args, profile))
        save(phase / 'storage-admission.json', admit_destinations(run_root, estimate, args.reserve_bytes))
        job_id = str(uuid.uuid4())
        name = f'fdb-ci-{profile}-{job_id[:8]}'
        print(f'{profile}: preparing exact source {sha}; container {name}', flush=True)
        clone_source(source, phase / 'work', sha, branch)
        work = phase / 'work'
        if profile not in ('ordinary', 'chat-consumer'):
            shutil.copytree(output / 'dist', work / 'dist')
        if profile in ('unified', 'unified-prepare', 'chat-prepare'):
            shutil.copytree(output / '.native/backends/layers', work / '.native/backends/layers')
            shutil.copytree(output / 'native-evidence/layers', work / 'native-evidence/layers')
        preparation = None
        if profile in ('unified', 'chat-prepare'):
            preparation = stage_prepared_unified(source, run_root, output, work, sha, manifest['local_run_id'])
        if profile == 'chat-prepare':
            for relative in ('.native/offline/output', 'artifacts/receipts'):
                shutil.copytree(output / relative, work / relative, dirs_exist_ok=True)
        chat_producer = chat_archive = None
        if profile == 'chat-consumer':
            chat_producer, chat_archive = stage_chat_archive(run_root, output, phase / 'input', sha, manifest['local_run_id'])
            shutil.copy2(work / 'scripts/ci/native-chat-consumer.sh', phase / 'input/bootstrap.sh')
        with (phase / 'image-pull.log').open('x') as log:
            subprocess.run([str(CLI), 'image', 'pull', '--arch', 'amd64', IMAGES[profile]],
                           stdout=log, stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
        image = image_identity(json.loads(capture([str(CLI), 'image', 'inspect', IMAGES[profile]])))
        orchestrator = None
        if profile == 'unified-prepare' and reuse_unified is None:
            with (phase / 'orchestrator-image-pull.log').open('x') as log:
                subprocess.run([str(CLI), 'image', 'pull', '--arch', 'arm64', IMAGES[profile]],
                               stdout=log, stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
            orchestrator = image_identity(json.loads(capture([str(CLI), 'image', 'inspect', IMAGES[profile]])), 'arm64')
            if orchestrator['image_index_digest'] != image['image_index_digest']:
                raise ValueError('AMD64 and ARM64 images do not share one pinned index')
        if reuse_unified is not None:
            reuse_module.stage(reuse_unified, work, image['image_digest'], work / '.native/reuse-unified')
        if reuse_backend is not None:
            stage_backend_reuse(source, reuse_backend, work, image['image_digest'], profile)
        save(phase / 'image.json', image)
        if orchestrator is not None:
            save(phase / 'orchestrator-image.json', orchestrator)
        guest_data = phase / 'guest-data'
        guest_data.mkdir()
        command = [str(CLI), 'run', '--name', name, '--arch', 'arm64' if orchestrator else 'amd64', '--rosetta',
                   '--cpus', '4', '--memory', '8G', '--workdir', '/',
                   '--mount', f'type=bind,source={work},target=/source,readonly',
                   '--mount', f'type=bind,source={guest_data},target=/run-data']
        environment = job_environment(profile, sha, manifest['local_run_id'], job_id)
        if preparation is not None:
            if profile == 'unified' and preparation['image_digest'] != image['image_digest']:
                raise ValueError('Prepared runtime build and test images differ')
            environment['FDISBULL_UNIFIED_BUILD_JOB_ID'] = preparation['local_job_id']
        if reuse_unified is not None:
            environment['FDISBULL_UNIFIED_REUSE_BASE'] = '1'
        if reuse_backend is not None:
            environment.update(FDISBULL_REUSE_BACKEND='1', FDISBULL_REUSE_IMAGE_DIGEST=image['image_digest'])
        if profile == 'chat-consumer':
            environment.update(FDISBULL_CHAT_PRODUCER_JOB_ID=chat_producer['local_job_id'],
                               FDISBULL_CHAT_ARCHIVE_SHA256=chat_archive['sha256'])
            bootstrap = 'bash /input/bootstrap.sh /input/archive.zip /run-data'
            command = consumer_command(CLI, name, image, phase / 'input', guest_data, bootstrap)
            insert = command.index(image['image_reference'])
            for key, value in environment.items():
                command[insert:insert] = ['--env', key + '=' + value]
                insert += 2
        elif orchestrator is not None:
            command += ['--cap-add', 'ALL', orchestrator['image_reference'],
                        'bash', '-ec', unified_command(image, environment)]
        else:
            for key, value in environment.items():
                command += ['--env', key + '=' + value]
            command += [image['image_reference'], 'bash', '-ec', job_command(profile)]
        started = now()
        code, termination, pid, stop_code, state = run_container(command, phase / 'container.log', args.timeout, name)
        try:
            data = json.loads((guest_data / 'runtime.json').read_text())
            runtime = {k: data[k] for k in ('python', 'machine', 'system')}
        except (OSError, ValueError, KeyError):
            runtime = None
        process = {'execution_origin': 'local-linux', 'source_commit': sha,
                   'local_run_id': manifest['local_run_id'], 'local_job_id': job_id,
                   'job_name': PREPARE_JOB if profile == 'unified-prepare' else JOBS[profile],
                   'termination': termination, 'exit_code': code,
                   **image, 'container_name': name, 'host_process_id': pid,
                   'started_at': started, 'finished_at': now(), 'stop_cli_exit_code': stop_code,
                   'container_state_after_stop': state, 'runtime': runtime}
        if orchestrator is not None:
            process['orchestrator_image_digest'] = orchestrator['image_digest']
        save(phase / 'process.json', process)
        # Preserve even partial selected evidence from a failed job; never turn
        # such artifacts into a completed leg without the host and guest gates.
        exported = guest_data / 'exported'
        if exported.is_dir():
            collect(exported, output)
        if profile == 'chat-prepare' and (output / CHAT_ARCHIVE).is_file():
            process['archive'] = artifact_identity(output, CHAT_ARCHIVE)
        if code or termination != 'exited' or state != 'stopped' or runtime is None:
            raise ValueError(f'{profile} did not pass; preserved log: {phase / "container.log"}')
        if profile == 'chat-consumer':
            if artifact_identity(output, CHAT_ARCHIVE) != chat_archive:
                raise ValueError('Chat archive changed during consumer')
            with (phase / 'input/archive.zip').open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != chat_archive['sha256']:
                    raise ValueError('Staged chat archive changed during consumer')
            if source_identity(work) != (sha, branch):
                raise ValueError('Frozen host clone changed during chat consumer')
            post_path = output / 'native-evidence/chat/host-source-postcheck.json'
            post_path.parent.mkdir(parents=True, exist_ok=True)
            save(post_path, {'schema': 'fdisbull-chat-host-source-postcheck-v1',
                'source_commit': sha, 'expected_source_commit': sha,
                'tracked_worktree_dirty': False, 'export_success': True,
                'archive_sha256': chat_archive['sha256']})
            identities = {'archive': chat_archive,
                'verifier': artifact_identity(output, 'native-evidence/chat/acceptance.json'),
                'junit': artifact_identity(output, 'native-evidence/chat/tests.xml'),
                'host_source_postcheck': artifact_identity(output, 'native-evidence/chat/host-source-postcheck.json')}
            process.update(identities)
            receipt_path_chat = output / 'artifacts/receipts/chat-consumer.json'
            receipt_path_chat.parent.mkdir(parents=True, exist_ok=True)
            save(receipt_path_chat, {'schema': 'fdisbull-chat-consumer-job-v1', 'status': 'passed',
                'execution_origin': 'local-linux', 'source_commit': sha, 'test_source_commit': sha,
                'local_run_id': manifest['local_run_id'], 'local_job_id': job_id,
                'producer_job_id': chat_producer['local_job_id'], 'source_access': 'absent',
                'source_check': 'artifact-and-host-clone', **identities})
        else:
            verify_guest_postcheck(guest_data, sha)
        if profile == 'chat-prepare':
            write_chat_prepare_receipt(output, guest_data, process, sha, manifest['local_run_id'])
        (phase / 'process.json').write_text(json.dumps(process, indent=2) + '\n')
        if profile == 'unified-prepare':
            unified_input_verifier(source).verify(output, sha, manifest['local_run_id'], job_id,
                                                  source_root=source)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        save(receipt_path, process)
        save(phase / 'completed.json', {'local_job_id': job_id, 'source_commit': sha, 'completed_at': now()})
        if profile == 'unified-prepare':
            evidence = output / 'native-evidence/pe'
            for name, value in [('preparation-process.json', process),
                                ('preparation-source-postcheck.json', verify_guest_postcheck(guest_data, sha)),
                                ('preparation-completed.json', read_regular_json(phase / 'completed.json'))]:
                save(evidence / name, value)
            prepared_unified_stage(source, run_root, output, sha, manifest['local_run_id'])
        print(f'{profile}: process exited successfully; evidence retained', flush=True)
    if args.profile in ('all', 'qualify'):
        checker = run_root / 'ordinary/work/scripts/check_ci_qualification.py'
        subprocess.run([sys.executable, str(checker), '--root', str(output), '--source-commit', sha,
                        '--local-run-id', manifest['local_run_id'], '--output', str(output / 'qualification.json')],
                       env=safe_env(), check=True, timeout=180)
    print(json.dumps({'source_commit': sha, 'local_run_id': manifest['local_run_id'],
                      'output': str(output), 'release_authorized': False}), flush=True)


def main():
    # SIGTERM from a finite supervisor follows the same bounded cleanup path
    # as Ctrl-C. SIGKILL is inherently uncatchable; retained names aid recovery.
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse-unified-base', type=Path, help='Explicit completed original unified preparation guest export; reruns all current acceptance')
    parser.add_argument('--reuse-stable-backend', type=Path, help='Explicit prior stable exported evidence root; reruns all tests')
    parser.add_argument('--reuse-layers-backend', type=Path, help='Explicit prior layers exported evidence root; reruns all tests and offline-kit checks')
    parser.add_argument('--profile', choices=['all', *JOBS, 'unified-prepare', 'qualify'], default='all')
    parser.add_argument('--expected-bytes', type=int, help='Conservative per-leg allocation override; defaults: prepare35GB, unified tests16GB, chat legs8GB each, ordinary12GB, stable14GB, layers18GB')
    parser.add_argument('--reserve-bytes', type=int, default=40_000_000_000)
    parser.add_argument('--timeout', type=int, default=7200, help='Per-container wall-clock seconds')
    args = parser.parse_args()
    if (args.expected_bytes is not None and args.expected_bytes < 0) or args.reserve_bytes < 20_000_000_000 or args.timeout <= 0:
        parser.error('Require nonnegative estimate, at least 20 GB reserve and positive timeout')
    try:
        execute(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Captured provider/image metadata and inherited environments stay private.
        parser.exit(2, f'Local verification incomplete: {exc}\n')


if __name__ == '__main__':
    main()
