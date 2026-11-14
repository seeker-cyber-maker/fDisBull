#!/usr/bin/env python3
"""Run one registered OVH GitHub worker under the existing shared CI lease.

Linux operator command, inert until invoked. It neither dispatches a workflow
nor grants release qualification. The registered runner's credentials stay in
its private home; no credential is accepted as an argument or copied to logs.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time

ROOT = Path('/var/lib/fdisbull-gh1-runner')
CONTROL = Path('/var/lib/fdisbull-ci/control/github-bootstrap-20261113')
LOCK = Path('/var/lib/fdisbull-ci/control/ci-executor.lock')
CLEANUP_BLOCKER = Path('/var/lib/fdisbull-ci/control/production/github-cleanup-blocked.json')


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def verify_lease(fd, owner, device, inode):
    """Verify the inherited locked file and the live owning controller; do not flock."""
    actual = os.fstat(fd)
    path = LOCK.stat()
    owner_fd_root = Path('/proc') / str(owner) / 'fd'
    if (os.getppid() != owner or actual.st_dev != device or actual.st_ino != inode
            or path.st_dev != device or path.st_ino != inode or not owner_fd_root.is_dir()):
        return False
    matching_fd = False
    for child in owner_fd_root.iterdir():
        try:
            st = child.stat()
            if (st.st_dev, st.st_ino) == (device, inode): matching_fd = True; break
        except OSError:
            continue
    if not matching_fd: return False
    return _has_flock(Path('/proc/locks').read_text(), owner, device, inode)


def _has_flock(text, owner, device, inode):
    device_key = '%02x:%02x:%d' % (os.major(device), os.minor(device), inode)
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[1:4] == ['FLOCK', 'ADVISORY', 'WRITE'] and fields[4] == str(owner) and fields[5] == device_key:
            return True
    return False


def health_gate(receipt):
    path = Path(__file__).with_name('offline-qualification.py')
    spec = importlib.util.spec_from_file_location('offline_health_gate', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.capture_health(receipt).get('continue') is True


def _docker(args, runner):
    result = runner(['docker', *args], capture_output=True, text=True, timeout=35, check=False)
    if result.returncode != 0: raise RuntimeError('docker operation unavailable')
    return result.stdout


def cleanup_owned(labels, *, runner=subprocess.run, sleeper=time.sleep):
    """Stop and verify only containers bearing every exact run label."""
    result = {'status': 'unknown', 'labels': dict(labels), 'containers': [], 'reason': None}
    try:
        if (set(labels) != {'fdisbull.ci.provider', 'fdisbull.ci.run_id', 'fdisbull.ci.run_attempt',
                            'fdisbull.ci.control_sha'}
                or labels['fdisbull.ci.provider'] != 'github'
                or not all(re.fullmatch(r'[1-9][0-9]*', labels[k]) for k in ('fdisbull.ci.run_id', 'fdisbull.ci.run_attempt'))
                or not re.fullmatch(r'[0-9a-f]{40}', labels['fdisbull.ci.control_sha'])):
            raise ValueError('invalid ownership labels')
        filters = [item for k, v in sorted(labels.items()) for item in ('--filter', 'label=' + k + '=' + v)]
        def enumerate_ids():
            ids = _docker(['ps', '-aq', '--no-trunc', *filters], runner).splitlines()
            if len(ids) > 64 or len(ids) != len(set(ids)) or any(not re.fullmatch(r'[0-9a-f]{64}', x) for x in ids):
                raise ValueError('invalid container inventory')
            return ids
        def inspect(cid):
            data = json.loads(_docker(['inspect', cid], runner))
            if (not isinstance(data, list) or len(data) != 1 or data[0].get('Id') != cid
                    or not isinstance(data[0].get('Config'), dict)
                    or not isinstance(data[0]['Config'].get('Labels'), dict)
                    or any(data[0]['Config']['Labels'].get(k) != v for k, v in labels.items())
                    or not isinstance(data[0].get('State'), dict)
                    or type(data[0]['State'].get('Running')) is not bool):
                raise ValueError('container inspection mismatch')
            return data[0]['State']['Running']
        ids = enumerate_ids()
        for cid in ids:
            running = inspect(cid)
            entry = {'id': cid, 'initial_running': running, 'stop': 'not_needed', 'final_running': None}
            result['containers'].append(entry)
            if running:
                _docker(['stop', '--time', '20', cid], runner)
                entry['stop'] = 'requested'
            entry['final_running'] = inspect(cid)
            if entry['final_running']: raise RuntimeError('owned container still running')
        # Re-read after a short settling interval: Docker daemon work may
        # outlive its initiating listener even after the process is reaped.
        for _ in range(2):
            sleeper(1)
            if set(enumerate_ids()) != set(ids): raise RuntimeError('container inventory changed')
        result['status'] = 'clean'
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, RuntimeError, json.JSONDecodeError) as error:
        result['reason'] = type(error).__name__
    return result


def _block_cleanup(value):
    CLEANUP_BLOCKER.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if CLEANUP_BLOCKER.exists() or CLEANUP_BLOCKER.is_symlink(): return
    save(CLEANUP_BLOCKER, value)
    directory = os.open(CLEANUP_BLOCKER.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)


def verify_job_inputs(path):
    path = Path(path)
    if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_dir()
            or path.stat().st_uid != os.geteuid() or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise ValueError('private job inputs unavailable')
    return path


def capsule_path(run_id, attempt):
    if not all(isinstance(x, str) and re.fullmatch(r'[1-9][0-9]*', x) for x in (run_id, attempt)):
        raise ValueError('invalid capsule identity')
    return LOCK.parent / 'production' / 'job-inputs' / 'health' / run_id / (attempt + '.json')


def existing_capsule(path, expected, now=None):
    if not path.exists() and not path.is_symlink(): return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 69632:
        raise ValueError('existing health capsule unavailable')
    capsule = json.loads(path.read_bytes())
    if not isinstance(capsule, dict) or any(capsule.get(k) != v for k, v in expected.items()):
        raise ValueError('existing health capsule mismatch')
    spec = importlib.util.spec_from_file_location('offline_health_capsule', Path(__file__).with_name('offline-qualification.py'))
    health = importlib.util.module_from_spec(spec); spec.loader.exec_module(health)
    envelope = capsule.get('host_health')
    if (not isinstance(envelope, dict) or envelope.get('helper_sha256') != health.HELPER_SHA256
            or envelope.get('failure') is not None or not health._valid(envelope.get('record'))):
        raise ValueError('existing health capsule invalid')
    record = envelope['record']; stamp = record.get('observed_epoch')
    current = time.time() if now is None else now
    if (record['healthy'] is not True or record['receipt']['durable'] is not True
            or type(stamp) not in (int, float) or not 0 <= current - stamp <= 120):
        raise ValueError('existing health capsule stale')
    return capsule


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--control-sha', required=True)
    parser.add_argument('--runner-id', type=int, required=True)
    parser.add_argument('--timeout', type=int, default=14400)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-attempt', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--control-ref', required=True)
    parser.add_argument('--lease-fd', type=int, required=True)
    parser.add_argument('--lease-owner-pid', type=int, required=True)
    parser.add_argument('--lease-dev', type=int, required=True)
    parser.add_argument('--lease-ino', type=int, required=True)
    args = parser.parse_args()
    if (os.geteuid() != 0 or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.nonce)
            or not re.fullmatch('[0-9a-f]{40}', args.control_sha)
            or args.runner_id != 21 or not 60 <= args.timeout <= 14400
            or not re.fullmatch(r'[1-9][0-9]*', args.run_id) or not re.fullmatch(r'[1-9][0-9]*', args.run_attempt)
            or not re.fullmatch(r'[0-9a-f]{40}', args.source_sha)
            or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', args.control_ref) or '..' in args.control_ref):
        raise ValueError('invalid finite worker invocation')
    identity = json.loads((ROOT / '.runner').read_text(encoding='utf-8-sig'))
    if (identity.get('agentId') != args.runner_id or identity.get('agentName') != 'fdisbull-ovh-ca-gh1'
            or identity.get('gitHubUrl', '').rstrip('/') != 'https://github.com/seeker-cyber-maker/fDisBull'):
        raise ValueError('registered runner differs')
    if not verify_lease(args.lease_fd, args.lease_owner_pid, args.lease_dev, args.lease_ino):
        raise RuntimeError('inherited executor lease unverified')
    if CLEANUP_BLOCKER.exists() or CLEANUP_BLOCKER.is_symlink():
        raise RuntimeError('unresolved GitHub container cleanup')
    workers = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True, timeout=20)
    if any(name.startswith('runner-') for name in workers.splitlines()):
        raise RuntimeError('GitLab worker already active')
    if subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=fdisbull.ci.provider=github'],
                               text=True, timeout=20).strip():
        raise RuntimeError('GitHub job already active')
    if shutil.disk_usage(CONTROL).free - 12_000_000_000 < 20_000_000_000:
        raise RuntimeError('host admission unavailable')
    inputs_root = verify_job_inputs(LOCK.parent / 'production' / 'job-inputs')
    for path in (inputs_root / 'health', inputs_root / 'health' / args.run_id):
        if path.is_symlink(): raise ValueError('unsafe health capsule directory')
    capsule_file = capsule_path(args.run_id, args.run_attempt)
    capsule_dir = capsule_file.parent
    capsule_identity = {'schema': 'fdisbull-host-health-capsule-1', 'run_id': args.run_id,
                        'run_attempt': args.run_attempt, 'source_sha': args.source_sha,
                        'control_sha': args.control_sha, 'ref': args.control_ref}
    prior_capsule = existing_capsule(capsule_file, capsule_identity)
    destination = CONTROL / args.nonce
    destination.mkdir(mode=0o700)
    health_path = destination / 'health-start.json'
    if not health_gate(health_path):
        raise RuntimeError('host health unavailable')
    capsule_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if prior_capsule is None:
        capsule = {**capsule_identity, 'host_health': json.loads(health_path.read_text())}
        save(capsule_file, capsule)
    directory_fd = os.open(capsule_dir, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory_fd)
    finally: os.close(directory_fd)
    save(destination / 'intent.json', {'nonce': args.nonce, 'control_sha': args.control_sha,
         'runner_id': args.runner_id, 'timeout_seconds': args.timeout, 'started_epoch': time.time()})
    with (destination / 'listener.log').open('xb') as log:
        process = subprocess.Popen(['sudo', '-n', '-H', '-u', 'fdisbull-gh1', str(ROOT / 'run.sh'), '--once'],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline, reason, checks = time.monotonic() + args.timeout, None, []
        try:
            save(destination / 'started.json', {'pid': process.pid, 'runner_id': args.runner_id,
                 'stage': 'listener-started', 'qualification_claimed': False})
            while process.poll() is None:
                try:
                    process.wait(timeout=min(60, max(1, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        reason = 'deadline-expired'; break
                    state = verify_lease(args.lease_fd, args.lease_owner_pid, args.lease_dev, args.lease_ino) and health_gate(destination / ('health-' + str(len(checks)) + '.json'))
                    checks.append({'healthy': state, 'observed_epoch': time.time()})
                    if not state:
                        reason = 'production-health-unavailable'; break
            if reason is not None:
                os.killpg(process.pid, signal.SIGINT)
                try: process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        except Exception:
            reason = 'worker-observation-unknown'
        finally:
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
                except (OSError, subprocess.SubprocessError): reason = 'worker-cleanup-unknown'
            labels = {'fdisbull.ci.provider': 'github', 'fdisbull.ci.run_id': args.run_id,
                      'fdisbull.ci.run_attempt': args.run_attempt,
                      'fdisbull.ci.control_sha': args.control_sha}
            cleanup = cleanup_owned(labels)
            if reason == 'worker-cleanup-unknown':
                cleanup['status'] = 'unknown'
                cleanup['reason'] = 'listener_process_unreaped'
            try:
                save(destination / 'cleanup.json', cleanup)
                directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            except OSError:
                cleanup = {'status': 'unknown', 'labels': labels, 'reason': 'receipt_write_failed'}
            if cleanup['status'] != 'clean':
                try: _block_cleanup(cleanup)
                except OSError: pass
                reason = 'owned-container-cleanup-unknown'
            try:
                save(destination / 'exit.json', {'exit_code': process.returncode, 'reason': reason,
                     'health_observations': checks, 'ended_epoch': time.time(), 'qualification_claimed': False})
            except OSError:
                try: _block_cleanup({'status': 'unknown', 'labels': labels, 'reason': 'exit_receipt_write_failed'})
                except OSError: pass
                reason = 'owned-container-cleanup-unknown'

    if reason == 'owned-container-cleanup-unknown': return 86
    return 0 if process.returncode == 0 and reason is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
