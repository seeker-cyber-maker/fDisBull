#!/usr/bin/env python3
"""Finite exact-source Docker CI on an already provisioned Boat Linux worker.

No provider API, credential handling, automatic cleanup, or VM provisioning.
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
import signal
import stat
import subprocess
import sys
import uuid
import zipfile

spec = importlib.util.spec_from_file_location('fdisbull_local_linux', Path(__file__).with_name('local-linux.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)
for name in ('JOBS', 'PREPARE_JOB', 'IMAGES', 'EXPECTED_BYTES', 'CHAT_ARCHIVE', 'profiles_for',
             'expected_bytes', 'now', 'safe_env', 'capture', 'save', 'source_identity', 'clone_source',
             'read_regular_json', 'artifact_identity', 'collect', 'verify_guest_postcheck',
             'job_environment', 'job_command', 'stage_backend_reuse', 'stage_prepared_unified',
             'prepared_unified_stage', 'stage_chat_archive', 'write_chat_prepare_receipt', 'unified_input_verifier'):
    globals()[name] = getattr(local, name)


def read_worker(path):
    data = read_regular_json(path)
    if (set(data) != {'schema', 'execution_origin', 'boat_sandbox_id', 'type', 'architecture', 'host_boot_id', 'observed_at'}
        or data.get('schema') != 'fdisbull-boat-worker-v1' or data.get('execution_origin') != 'boat-linux'
        or not re.fullmatch(r'bx_[a-z0-9]+', str(data.get('boat_sandbox_id', '')))
        or data.get('architecture') != 'x86_64' or data.get('type') not in ('small', 'default', 'large', 'xlarge')
        or not isinstance(data.get('observed_at'), str) or not data['observed_at']):
        raise ValueError('Invalid Boat worker receipt')
    try:
        if str(uuid.UUID(data['host_boot_id'])) != data['host_boot_id']:
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError('Invalid Boat worker boot identity') from None
    try:
        observed = datetime.datetime.fromisoformat(data['observed_at'].replace('Z', '+00:00'))
        if observed.utcoffset() is None:
            raise ValueError
    except ValueError:
        raise ValueError('Invalid Boat worker observation time') from None
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Boat executor requires Linux x86_64')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != data['host_boot_id']:
        raise ValueError('Boat worker receipt boot identity differs from current host')
    return data


def admit_destinations(parent, expected, reserve):
    docker_root = Path(capture(['docker', 'info', '--format', '{{.DockerRootDir}}']).strip()).resolve(strict=True)
    result = {}
    devices = set()
    for label, path in (('output', parent), ('docker_store', docker_root)):
        dev = path.stat().st_dev
        if dev in devices:
            continue
        devices.add(dev)
        usage = shutil.disk_usage(path)
        if usage.free - expected < reserve:
            raise ValueError(f'Storage admission rejected for {label}: free={usage.free}, expected={expected}, reserve={reserve}')
        result[label] = {'free_bytes': usage.free, 'expected_bytes': expected, 'reserve_bytes': reserve}
    return result


def docker_image_identity(index_digest, manifest, inspect):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', str(index_digest)):
        raise ValueError('Invalid Docker index digest')
    descriptors = manifest.get('manifests')
    if descriptors is None:
        digest = index_digest
    else:
        variants = [v for v in descriptors if v.get('platform', {}).get('os') == 'linux'
                    and v.get('platform', {}).get('architecture') == 'amd64'
                    and v.get('platform', {}).get('variant') in (None, '', 'v1')]
        if len(variants) != 1:
            raise ValueError('Expected one Linux AMD64 image manifest')
        digest = variants[0].get('digest')
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', str(digest)) or not isinstance(inspect, dict)
        or inspect.get('Os') != 'linux' or inspect.get('Architecture') != 'amd64'):
        raise ValueError('Docker image is not the pinned Linux AMD64 variant')
    return {'image_digest': digest, 'image_index_digest': index_digest}



def normalize_repository(name):
    """Docker Hub's familiar names and fully qualified names identify one repo."""
    if not isinstance(name, str) or not name or '@' in name:
        raise ValueError('Invalid Docker repository name')
    parts = name.split('/')
    if parts[0] in ('docker.io', 'index.docker.io', 'registry-1.docker.io'):
        parts = parts[1:]
    elif len(parts) > 1 and ('.' in parts[0] or ':' in parts[0] or parts[0] == 'localhost'):
        return '/'.join(parts)
    if len(parts) == 1:
        parts.insert(0, 'library')
    if not all(parts):
        raise ValueError('Invalid Docker repository name')
    return 'docker.io/' + '/'.join(parts)


def repository_digests(inspect, repository):
    expected = normalize_repository(repository)
    values = []
    for item in inspect.get('RepoDigests', []):
        if not isinstance(item, str) or item.count('@') != 1:
            raise ValueError('Invalid Docker repository digest')
        name, digest = item.split('@')
        if normalize_repository(name) == expected:
            values.append(digest)
    return values


def verify_platform_inspection(inspect, repository, digest):
    if inspect.get('Os') != 'linux' or inspect.get('Architecture') != 'amd64':
        raise ValueError('Pinned Docker image inspection failed')
    descriptor = inspect.get('Descriptor')
    descriptor_digest = descriptor.get('digest') if isinstance(descriptor, dict) else None
    if descriptor_digest != digest and digest not in repository_digests(inspect, repository):
        raise ValueError('Pulled Docker platform descriptor does not match selected digest')


def pull_image(reference, log):
    with log.open('x') as stream:
        subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', reference], stdout=stream,
                       stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
    inspected = json.loads(capture(['docker', 'image', 'inspect', reference]))
    if len(inspected) != 1:
        raise ValueError('Docker image inspection ambiguous')
    repo = reference.rsplit(':', 1)[0]
    digests = repository_digests(inspected[0], repo)
    if len(set(digests)) != 1:
        raise ValueError('Docker repository digest missing or ambiguous')
    index = digests[0]
    manifest = json.loads(capture(['docker', 'buildx', 'imagetools', 'inspect', '--raw', repo + '@' + index], timeout=120))
    identity = docker_image_identity(index, manifest, inspected[0])
    pinned = repo + '@' + identity['image_digest']
    with log.open('a') as stream:
        subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', pinned], stdout=stream,
                       stderr=subprocess.STDOUT, env=safe_env(), check=True, timeout=600)
    target = json.loads(capture(['docker', 'image', 'inspect', pinned]))
    if len(target) != 1:
        raise ValueError('Pinned Docker image inspection ambiguous')
    verify_platform_inspection(target[0], repo, identity['image_digest'])
    identity['image_reference'] = repo + '@' + index
    return identity



def extract_consumer_kit(archive, destination, expected_sha):
    """Extract bounded regular ZIP content without executing archive data."""
    archive, destination = Path(archive), Path(destination)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > 500_000_000:
        raise ValueError('Missing or oversized consumer archive')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha:
            raise ValueError('Consumer archive identity mismatch')
    destination.mkdir()  # Preserve failed or interrupted attempts.
    seen = set()
    total = 0
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            name = item.filename
            parts = name.split('/')
            if item.is_dir():
                parts = parts[:-1]
            if (not parts or parts[0] != 'fdisbull-chat-offline' or name.startswith('/')
                or '\\' in name or any(p in ('', '.', '..') for p in parts)):
                raise ValueError('Unsafe consumer ZIP member')
            canonical = '/'.join(parts)
            if canonical in seen:
                raise ValueError('Duplicate consumer ZIP member')
            seen.add(canonical)
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (item.is_dir() and kind == stat.S_IFREG) or (not item.is_dir() and kind == stat.S_IFDIR):
                raise ValueError('Consumer ZIP contains a link or special file')
            if len(parts) == 1:
                if not item.is_dir():
                    raise ValueError('Consumer ZIP root must be a directory')
                continue
            total += item.file_size
            if total > 2 * 1024**3:
                raise ValueError('Consumer extraction exceeds bounded workspace')
            target = destination.joinpath(*parts[1:])
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(item) as source, target.open('xb') as output:
                while block := source.read(1024**2):
                    output.write(block)
            target.chmod(mode & 0o777 if mode else 0o644)
    if not seen:
        raise ValueError('Empty consumer ZIP')


def docker_command(profile, name, image, work, guest_data, stage, environment, reuse=False, consumer_kit=None):
    command = ['docker', 'run', '--name', name, '--platform', 'linux/amd64', '--cpus', '4', '--memory', '8g', '--workdir', '/']
    if profile == 'chat-consumer':
        if consumer_kit is None:
            raise ValueError('Consumer kit mount missing')
        command += ['--network', 'none',
                    '--mount', f'type=bind,source={consumer_kit},target=/fdisbull-chat-offline,readonly',
                    '--mount', f'type=bind,source={stage},target=/input,readonly',
                    '--mount', f'type=bind,source={guest_data},target=/run-data']
        shell = 'bash /input/bootstrap.sh /input/archive.zip /run-data --mounted-kit'
    else:
        command += ['--mount', f'type=bind,source={work},target=/source,readonly',
                    '--mount', f'type=bind,source={guest_data},target=/run-data']
        if profile == 'unified-prepare' and not reuse:
            command += ['--network', 'host', '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock']
        shell = job_command(profile)
    for key, value in environment.items():
        command += ['--env', key + '=' + value]
    return command + [image['image_reference'], 'bash', '-ec', shell]


def run_container(command, log, timeout, name):
    termination = 'exited'
    with log.open('x') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=safe_env(), start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            termination = 'timeout-or-interrupted'
            subprocess.run(['docker', 'stop', '--time', '10', name], env=safe_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=10)
    stop_code = None
    try:
        state = json.loads(capture(['docker', 'inspect', '--format', '{{json .State}}', name]))
        if not state.get('Running') and state.get('Status') == 'exited' and type(state.get('ExitCode')) is int:
            actual_code = state['ExitCode']
            if termination == 'exited' and code != actual_code:
                termination = 'docker-exit-mismatch'
            code = actual_code
            status = 'stopped'
        else:
            status = str(state.get('Status', 'unknown'))
    except (OSError, ValueError, subprocess.SubprocessError):
        status = 'unknown'
    return code, termination, process.pid, stop_code, status
def execute(args):
    source = args.source.resolve()
    sha, branch = source_identity(source)
    run_root = args.output.absolute()
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
    worker = read_worker(args.worker_receipt)
    worker_path = run_root / 'qualification/artifacts/receipts/boat-worker.json'
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    if worker_path.exists():
        if worker_path.read_bytes() != args.worker_receipt.read_bytes():
            raise ValueError('Worker receipt changed for resumed run')
    else:
        shutil.copyfile(args.worker_receipt, worker_path)
    worker_ref = artifact_identity(run_root / 'qualification', 'artifacts/receipts/boat-worker.json')
    boat_id = worker['boat_sandbox_id']
    manifest_path = run_root / 'run.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (manifest['source_commit'] != sha or manifest['source'] != str(source)
            or manifest.get('execution_origin') != 'boat-linux' or manifest.get('boat_sandbox_id') != boat_id
            or manifest.get('boat_worker_receipt') != worker_ref):
            raise ValueError('Cannot resume a different source commit or checkout')
    else:
        manifest = {'schema': 'fdisbull-boat-linux-run-1', 'execution_origin': 'boat-linux',
                    'boat_sandbox_id': boat_id, 'boat_worker_receipt': worker_ref,
                    'local_run_id': str(uuid.uuid4()), 'source_commit': sha, 'source': str(source),
                    'created_at': now(), 'host_platform': platform.platform()}
        save(manifest_path, manifest)
    output = run_root / 'qualification'
    output.mkdir(exist_ok=True)
    run_receipt = output / 'artifacts/receipts/boat-run.json'
    if run_receipt.exists():
        if read_regular_json(run_receipt) != manifest:
            raise ValueError('Boat run receipt changed')
    else:
        save(run_receipt, manifest)
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
                    prepared_unified_stage(source, run_root, output, sha, manifest['local_run_id'], origin='boat-linux', boat_sandbox_id=boat_id, boat_worker_receipt=worker_ref)
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
            preparation = stage_prepared_unified(source, run_root, output, work, sha, manifest['local_run_id'], origin='boat-linux', boat_sandbox_id=boat_id, boat_worker_receipt=worker_ref)
        if profile == 'chat-prepare':
            for relative in ('.native/offline/output', 'artifacts/receipts'):
                shutil.copytree(output / relative, work / relative, dirs_exist_ok=True)
        chat_producer = chat_archive = None
        if profile == 'chat-consumer':
            chat_producer, chat_archive = stage_chat_archive(run_root, output, phase / 'input', sha, manifest['local_run_id'], origin='boat-linux', boat_sandbox_id=boat_id, boat_worker_receipt=worker_ref)
            shutil.copy2(work / 'scripts/ci/native-chat-consumer.sh', phase / 'input/bootstrap.sh')
            extract_consumer_kit(phase / 'input/archive.zip', phase / 'consumer-kit', chat_archive['sha256'])
        image = pull_image(IMAGES[profile], phase / 'image-pull.log')
        if reuse_unified is not None:
            reuse_module.stage(reuse_unified, work, image['image_digest'], work / '.native/reuse-unified')
        if reuse_backend is not None:
            stage_backend_reuse(source, reuse_backend, work, image['image_digest'], profile)
        save(phase / 'image.json', image)
        guest_data = phase / 'guest-data'
        guest_data.mkdir()
        environment = job_environment(profile, sha, manifest['local_run_id'], job_id,
                                      origin='boat-linux', boat_sandbox_id=boat_id,
                                      boat_worker_receipt=worker_ref)
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
        command = docker_command(profile, name, image, work, guest_data, phase / 'input', environment,
                                 reuse_unified is not None, consumer_kit=phase / 'consumer-kit' if profile == 'chat-consumer' else None)
        started = now()
        code, termination, pid, stop_code, state = run_container(command, phase / 'container.log', args.timeout, name)
        try:
            data = json.loads((guest_data / 'runtime.json').read_text())
            runtime = {k: data[k] for k in ('python', 'machine', 'system')}
        except (OSError, ValueError, KeyError):
            runtime = None
        process = {'execution_origin': 'boat-linux', 'boat_sandbox_id': boat_id,
                   'boat_worker_receipt': worker_ref, 'source_commit': sha,
                   'local_run_id': manifest['local_run_id'], 'local_job_id': job_id,
                   'job_name': PREPARE_JOB if profile == 'unified-prepare' else JOBS[profile],
                   'termination': termination, 'exit_code': code,
                   **image, 'container_name': name, 'host_process_id': pid,
                   'started_at': started, 'finished_at': now(), 'stop_cli_exit_code': stop_code,
                   'container_state_after_stop': state, 'runtime': runtime}
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
        if source_identity(work, generated_outputs=True) != (sha, branch):
            raise ValueError('Frozen host clone changed during Boat job')
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
                'execution_origin': 'boat-linux', 'boat_sandbox_id': boat_id,
                   'boat_worker_receipt': worker_ref, 'source_commit': sha, 'test_source_commit': sha,
                'local_run_id': manifest['local_run_id'], 'local_job_id': job_id,
                'producer_job_id': chat_producer['local_job_id'], 'source_access': 'absent',
                'source_check': 'artifact-and-host-clone', **identities})
        else:
            verify_guest_postcheck(guest_data, sha)
        if profile == 'chat-prepare':
            write_chat_prepare_receipt(output, guest_data, process, sha, manifest['local_run_id'], origin='boat-linux', boat_sandbox_id=boat_id, boat_worker_receipt=worker_ref)
        (phase / 'process.json').write_text(json.dumps(process, indent=2) + '\n')
        if profile == 'unified-prepare':
            unified_input_verifier(source).verify(output, sha, manifest['local_run_id'], job_id,
                                                  source_root=source)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        save(receipt_path, process)
        save(phase / 'completed.json', {'local_job_id': job_id, 'source_commit': sha, 'completed_at': now(),
             'execution_origin': 'boat-linux', 'boat_sandbox_id': boat_id, 'boat_worker_receipt': worker_ref})
        if profile == 'unified-prepare':
            evidence = output / 'native-evidence/pe'
            for name, value in [('preparation-process.json', process),
                                ('preparation-source-postcheck.json', verify_guest_postcheck(guest_data, sha)),
                                ('preparation-completed.json', read_regular_json(phase / 'completed.json'))]:
                save(evidence / name, value)
            prepared_unified_stage(source, run_root, output, sha, manifest['local_run_id'], origin='boat-linux', boat_sandbox_id=boat_id, boat_worker_receipt=worker_ref)
        print(f'{profile}: process exited successfully; evidence retained', flush=True)
    if args.profile in ('all', 'qualify'):
        checker = run_root / 'ordinary/work/scripts/check_ci_qualification.py'
        subprocess.run([sys.executable, str(checker), '--root', str(output), '--source-commit', sha,
                        '--local-run-id', manifest['local_run_id'], '--output', str(output / 'qualification.json')],
                       env=safe_env(), check=True, timeout=180)
    print(json.dumps({'source_commit': sha, 'local_run_id': manifest['local_run_id'],
                      'output': str(output), 'release_authorized': False}), flush=True)



def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker-receipt', type=Path, required=True)
    parser.add_argument('--reuse-unified-base', type=Path)
    parser.add_argument('--reuse-stable-backend', type=Path)
    parser.add_argument('--reuse-layers-backend', type=Path)
    parser.add_argument('--profile', choices=['all', *JOBS, 'unified-prepare', 'qualify'], default='all')
    parser.add_argument('--expected-bytes', type=int)
    parser.add_argument('--reserve-bytes', type=int, default=20_000_000_000)
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    if args.reserve_bytes < 20_000_000_000 or args.timeout <= 0 or (args.expected_bytes is not None and args.expected_bytes < 0):
        parser.error('Require nonnegative estimate, at least 20 GB reserve, and positive timeout')
    try:
        execute(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(2, f'Boat verification incomplete: {exc}\n')


if __name__ == '__main__':
    main()
