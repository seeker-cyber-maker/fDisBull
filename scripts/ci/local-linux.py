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
        'layers': 'native-debugger-layers', 'unified': 'native-unified'}
IMAGES = {'ordinary': 'docker.io/library/python:3.12-bookworm',
          'stable': 'docker.io/library/python:3.12-bookworm',
          'layers': 'docker.io/library/python:3.13.5-bookworm',
          'unified': 'docker.io/library/python:3.12-bookworm'}


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
           'CI_COMMIT_SHA': sha, 'CI_JOB_NAME': JOBS[profile],
           'FDISBULL_EXECUTION_ORIGIN': 'local-linux',
           'FDISBULL_LOCAL_RUN_ID': run_id, 'FDISBULL_LOCAL_JOB_ID': job_id,
           'TMPDIR': '/ci-tmp', 'PIP_CACHE_DIR': '/ci-cache/pip',
           'PYTHONDONTWRITEBYTECODE': '1', 'DEBIAN_FRONTEND': 'noninteractive'}
    if profile in ('stable', 'layers'):
        env.update(FDISBULL_PROFILE=profile,
                   FDISBULL_PATCH_DIRECTORY='experimental/dosbox-x' + ('/layers' if profile == 'layers' else ''),
                   FDISBULL_DOSBOX=f'/work/.native/backends/{profile}/dosbox-x',
                   FDISBULL_DOSBOX_SOURCE='/work/.native/dosbox-x')
    elif profile == 'unified':
        env.update(FDISBULL_LOCAL_DOCKER='0',
                   FDISBULL_LOCAL_DOCKER_BUILD_NETWORK='host',
                   DOCKER_HOST='unix:///var/run/docker.sock',
                   FDISBULL_PE_QEMU='/work/.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
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
               + ('assert platform.python_version() == "3.13.5"; ' if profile == 'layers'
                  else 'assert sys.version_info[:2] == (3,12); ')
               + 'print(json.dumps({"python":platform.python_version(),"machine":platform.machine(),"system":sys.platform}))')
    setup += 'python -c ' + shlex.quote(runtime) + ' > /run-data/runtime.json; '
    if profile == 'ordinary':
        return setup + ('apt-get update && apt-get install -y --no-install-recommends '
                        'ca-certificates curl xz-utils git build-essential clang libx11-dev && '
                        'bash scripts/ci/test-and-package.sh')
    script = 'native-unified' if profile == 'unified' else 'native-debugger'
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
    args.extend([pinned, 'bash', '-ec', job_command('unified')])
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
                  '.native/pe/packages/*.whl']
    for pattern in selections:
        for path in work.glob(pattern):
            if path.is_symlink():
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


def execute(args):
    source = args.source.resolve()
    sha, branch = source_identity(source)
    run_root = args.output.absolute()
    if not any(run_root.is_relative_to(Path(p)) for p in ('/Volumes/CACHE', '/Volumes/CODEX')):
        raise ValueError('Use an external CACHE or CODEX output directory')
    if run_root.is_relative_to(source) or source.is_relative_to(run_root):
        raise ValueError('Output must be outside the source checkout')
    parent = run_root if run_root.exists() else run_root.parent
    admit_destinations(parent, args.expected_bytes, args.reserve_bytes)
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
    profiles = list(JOBS) if args.profile == 'all' else ([] if args.profile == 'qualify' else [args.profile])
    for profile in profiles:
        receipt_path = output / f'artifacts/receipts/local-process-{profile}.json'
        if receipt_path.exists():
            marker = run_root / profile / 'completed.json'
            process = json.loads(receipt_path.read_text())
            if (marker.is_file() and process.get('exit_code') == 0
                    and json.loads(marker.read_text()).get('local_job_id') == process.get('local_job_id')):
                print(f'{profile}: retained completed leg', flush=True)
                continue
            raise ValueError('Failed attempt retained; use a new run directory')
        if profile != 'ordinary' and not (output / 'artifacts/receipts/ordinary.json').exists():
            raise ValueError('Ordinary package acceptance must pass first')
        if profile == 'unified' and not all((output / f'artifacts/receipts/native-{p}.json').exists() for p in ('stable', 'layers')):
            raise ValueError('Both DOS native profiles must pass before unified acceptance')
        phase = run_root / profile
        phase.mkdir()  # never overwrite an interrupted or failed attempt
        save(phase / 'storage-admission.json', admit_destinations(run_root, args.expected_bytes, args.reserve_bytes))
        job_id = str(uuid.uuid4())
        name = f'fdb-ci-{profile}-{job_id[:8]}'
        print(f'{profile}: preparing exact source {sha}; container {name}', flush=True)
        clone_source(source, phase / 'work', sha, branch)
        work = phase / 'work'
        if profile != 'ordinary':
            shutil.copytree(output / 'dist', work / 'dist')
        if profile == 'unified':
            shutil.copytree(output / '.native/backends/layers', work / '.native/backends/layers')
            shutil.copytree(output / 'native-evidence/layers', work / 'native-evidence/layers')
        with (phase / 'image-pull.log').open('x') as log:
            subprocess.run([str(CLI), 'image', 'pull', '--arch', 'amd64', IMAGES[profile]],
                           stdout=log, stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
        image = image_identity(json.loads(capture([str(CLI), 'image', 'inspect', IMAGES[profile]])))
        orchestrator = None
        if profile == 'unified':
            with (phase / 'orchestrator-image-pull.log').open('x') as log:
                subprocess.run([str(CLI), 'image', 'pull', '--arch', 'arm64', IMAGES[profile]],
                               stdout=log, stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
            orchestrator = image_identity(json.loads(capture([str(CLI), 'image', 'inspect', IMAGES[profile]])), 'arm64')
            if orchestrator['image_index_digest'] != image['image_index_digest']:
                raise ValueError('AMD64 and ARM64 images do not share one pinned index')
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
        if orchestrator is not None:
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
                   'job_name': JOBS[profile], 'termination': termination, 'exit_code': code,
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
        if code or termination != 'exited' or state != 'stopped' or runtime is None:
            raise ValueError(f'{profile} did not pass; preserved log: {phase / "container.log"}')
        verify_guest_postcheck(guest_data, sha)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        save(receipt_path, process)
        save(phase / 'completed.json', {'local_job_id': job_id, 'source_commit': sha, 'completed_at': now()})
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
    parser.add_argument('--profile', choices=['all', *JOBS, 'qualify'], default='all')
    parser.add_argument('--expected-bytes', type=int, default=12_000_000_000)
    parser.add_argument('--reserve-bytes', type=int, default=40_000_000_000)
    parser.add_argument('--timeout', type=int, default=7200, help='Per-container wall-clock seconds')
    args = parser.parse_args()
    if args.expected_bytes < 0 or args.reserve_bytes < 20_000_000_000 or args.timeout <= 0:
        parser.error('Require nonnegative estimate, at least 20 GB reserve and positive timeout')
    try:
        execute(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Captured provider/image metadata and inherited environments stay private.
        parser.exit(2, f'Local verification incomplete: {exc}\n')


if __name__ == '__main__':
    main()
