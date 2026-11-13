#!/usr/bin/env python3
"""Run one registered OVH GitHub worker under the existing shared CI lease.

Linux operator command, inert until invoked. It neither dispatches a workflow
nor grants release qualification. The registered runner's credentials stay in
its private home; no credential is accepted as an argument or copied to logs.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

ROOT = Path('/var/lib/fdisbull-gh1-runner')
CONTROL = Path('/var/lib/fdisbull-ci/control/github-bootstrap-20261113')
LOCK = Path('/var/lib/fdisbull-ci/control/ci-executor.lock')


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def healthy():
    result = subprocess.run(['/usr/bin/python3', '/usr/local/libexec/operations-monitor.py', '--snapshot'],
                            capture_output=True, text=True, timeout=45, check=True)
    value = json.loads(result.stdout)
    checks = [value['doctor_observation'], value['n8n_readiness'],
              *value['health_checks'].values(), *value['websites'].values()]
    now = time.time()
    return (value.get('read_only') is True and value.get('model_required') is False
            and 0 <= now - value['observed_epoch'] <= 120
            and all(x.get('state') == 'healthy' and 0 <= now - x['checked_epoch'] <= 660 for x in checks)
            and value['doctor_observation'].get('fresh') is True
            and all(x.get('fresh') is True for x in value['health_checks'].values())
            and value['disk']['state'] == 'known' and value['disk']['free_bytes'] >= 20_100_000_000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--control-sha', required=True)
    parser.add_argument('--runner-id', type=int, required=True)
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()
    if (os.geteuid() != 0 or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.nonce)
            or not re.fullmatch('[0-9a-f]{40}', args.control_sha)
            or args.runner_id <= 0 or not 60 <= args.timeout <= 1800):
        raise ValueError('invalid finite worker invocation')
    identity = json.loads((ROOT / '.runner').read_text(encoding='utf-8-sig'))
    if (identity.get('agentId') != args.runner_id or identity.get('agentName') != 'fdisbull-ovh-ca-gh1'
            or identity.get('gitHubUrl', '').rstrip('/') != 'https://github.com/seeker-cyber-maker/fDisBull'):
        raise ValueError('registered runner differs')
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        workers = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True, timeout=20)
        if any(name.startswith('runner-') for name in workers.splitlines()):
            raise RuntimeError('GitLab worker already active')
        if subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=fdisbull.ci.provider=github'],
                                   text=True, timeout=20).strip():
            raise RuntimeError('GitHub job already active')
        if shutil.disk_usage(CONTROL).free - 1_000_000_000 < 40_000_000_000 or not healthy():
            raise RuntimeError('host admission or health unavailable')
        destination = CONTROL / args.nonce
        destination.mkdir(mode=0o700)
        save(destination / 'intent.json', {'nonce': args.nonce, 'control_sha': args.control_sha,
             'runner_id': args.runner_id, 'timeout_seconds': args.timeout, 'started_epoch': time.time()})
        with (destination / 'listener.log').open('xb') as log:
            process = subprocess.Popen(['sudo', '-n', '-H', '-u', 'fdisbull-gh1', str(ROOT / 'run.sh'), '--once'],
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            save(destination / 'started.json', {'pid': process.pid, 'runner_id': args.runner_id,
                 'stage': 'listener-started', 'qualification_claimed': False})
            deadline, reason, checks = time.monotonic() + args.timeout, None, []
            try:
                while process.poll() is None:
                    try:
                        process.wait(timeout=min(60, max(1, deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            reason = 'deadline-expired'; break
                        state = healthy(); checks.append({'healthy': state, 'observed_epoch': time.time()})
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
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
                save(destination / 'exit.json', {'exit_code': process.returncode, 'reason': reason,
                     'health_observations': checks, 'ended_epoch': time.time(), 'qualification_claimed': False})
        return 0 if process.returncode == 0 and reason is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
