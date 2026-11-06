#!/usr/bin/env python3
"""Run one whole Boat CI session, then request a snapshot-preserving stop.

Run this finite controller on the authenticated Mac. It never resumes a VM,
changes retention/billing, removes data, or uses a forced stop.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import time
import uuid


# Sent as code, not installed as a service. No personal Boat token enters the VM.
# Only the existing notifier reads its already-provisioned private config.
GUEST = r'''
import datetime, fcntl, json, os, pathlib, signal, subprocess, sys, time
c = json.loads(sys.argv[1])
mode = sys.argv[2]
root = pathlib.Path(c['output'])
session = root / ('session-' + c['session_id'])
result_path = session / 'result.json'
ignore_names = ('.boatignore', '.boxignore', '.oneignore')
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path, value):
    with path.open('w') as f:
        json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
def identity(pid):
    try:
        text = pathlib.Path('/proc/%d/stat' % pid).read_text()
        return {'boot_id': pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'start_ticks': text[text.rfind(')') + 2:].split()[19]}
    except FileNotFoundError: return None
def group_exists(pid):
    try: os.killpg(pid, 0); return True
    except ProcessLookupError: return False
def safe_path(path):
    if not path.is_absolute() or not path.is_relative_to('/home/user') or '.cache' in path.parts:
        raise ValueError('Evidence must be in persistent /home/user storage')
    for p in (path, *path.parents):
        if p.is_symlink(): raise ValueError('Persistent path has a symlink ancestor')
        if any((p / n).exists() or (p / n).is_symlink() for n in ignore_names):
            raise ValueError('Snapshot ignore file requires explicit review before CI')
    if path.exists():
        for p in path.rglob('*'):
            if p.name in ignore_names:
                raise ValueError('Snapshot ignore file inside evidence requires review')
            if p.is_symlink() and not p.resolve().is_relative_to(root):
                raise ValueError('Evidence symlink leaves the persistent result directory')
if mode == 'alert':
    import runpy, uuid
    notify = runpy.run_path(c['notify_script'])
    cfg = json.loads(pathlib.Path(c['notify_config']).read_text())
    data = {'project': cfg['project'], 'source': 'ci', 'kind': 'failed',
        'worker_id': c['worker'], 'run_id': root.name + ':shutdown',
        'commit': c['commit'], 'phase': 'ci-shutdown', 'exit_code': 2,
        'receipt': str(result_path)}
    accepted = notify['send'](cfg, data, str(uuid.uuid4()))
    try:
        safe_path(root)
        if session.exists(): save(session / 'shutdown-notification.json', {'accepted_by_relay': accepted})
    except ValueError: pass
    print(json.dumps({'accepted_by_relay': accepted}))
    sys.exit(0)
safe_path(root)
if mode == 'check':
    if subprocess.check_output(['docker', 'ps', '-q'], text=True).strip():
        raise ValueError('Another Docker workload is running; exclusive CI stop refused')
    print(json.dumps({'persistent_results': True, 'no_running_containers': True}))
    sys.exit(0)
if mode == 'finish':
    # A transport error does not prove the remote process exited. Terminate only
    # this session's recorded process group before taking the final snapshot.
    control_path = session / 'child.json'
    if control_path.exists():
        child = json.loads(control_path.read_text())
        if child['session_id'] != c['session_id']:
            raise ValueError('CI child identity differs')
        pid = child['pid']
        if not result_path.exists():
            current = identity(pid)
            if current is not None:
                if current != child['process_identity'] or os.getpgid(pid) != pid:
                    raise ValueError('CI child process identity differs; refusing to signal it')
                os.killpg(pid, signal.SIGTERM)
                end = time.monotonic() + 60
                while time.monotonic() < end and not result_path.exists(): time.sleep(.2)
        if identity(pid) == child['process_identity']:
            raise ValueError('CI child has not exited; snapshot preservation is unconfirmed')
        if group_exists(pid):
            raise ValueError('CI process group is still present; refusing premature snapshot')
    if not result_path.exists():
        raise ValueError('CI completion/finalization receipt is absent')
    result = json.loads(result_path.read_text())
    if result.get('session_id') != c['session_id']:
        raise ValueError('CI completion identity differs')
    if subprocess.check_output(['docker', 'ps', '-q'], text=True).strip():
        raise ValueError('Docker workloads are still running; refusing premature shutdown')
    safe_path(root)
    os.sync()
    print(json.dumps({'result': result, 'persistent_results_flushed': True}))
    sys.exit(0)
if mode != 'run': raise ValueError('Unknown session action')
root.mkdir(exist_ok=True)
session.mkdir()  # Preserve every earlier attempt.
lock_path = root.parent / '.boat-ci-session.lock'
lock = lock_path.open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
result = {'session_id': c['session_id'], 'source_commit': c['commit'],
          'started_at': now(), 'ci_exit_code': None, 'ci_status': 'unconfirmed'}
child = None
def interrupt(signum, frame):
    if child is not None:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
with (session / 'ci.log').open('x') as log:
    try:
        sha = subprocess.check_output(['git', '-C', c['source'], 'rev-parse', 'HEAD'], text=True).strip()
        if sha != c['commit']: raise ValueError('Remote source differs from requested commit')
        worker = json.loads(pathlib.Path(c['worker_receipt']).read_text())
        if worker['boat_sandbox_id'] != c['worker']:
            raise ValueError('Worker receipt names a different VM')
        command = ['python3', c['notify_script'], '--config', c['notify_config'],
            '--worker', c['worker'], '--run', root.name, '--commit', c['commit'],
            '--phase', 'whole-ci', '--receipt', str(result_path),
            '--timeout', str(c['timeout']), '--', 'python3',
            str(pathlib.Path(c['source']) / 'scripts/ci/boat-linux.py'),
            '--source', c['source'], '--output', c['output'],
            '--worker-receipt', c['worker_receipt'], '--profile', 'all', *c['ci_args']]
        environment = dict(os.environ, FDISBULL_BOAT_SESSION_ID=c['session_id'])
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env=environment)
        save(session / 'child.json', {'session_id': c['session_id'], 'pid': child.pid,
                                     'process_identity': identity(child.pid)})
        result['ci_exit_code'] = child.wait(timeout=c['timeout'] + 120)
        result['ci_status'] = 'passed' if result['ci_exit_code'] == 0 else 'failed'
    except (Exception, KeyboardInterrupt) as e:
        result['ci_status'] = 'interrupted' if isinstance(e, KeyboardInterrupt) else 'failed'
        result['error_type'] = type(e).__name__
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=10)
            except ProcessLookupError: pass
        result['ci_exit_code'] = 130 if isinstance(e, KeyboardInterrupt) else 2
    finally:
        result['finished_at'] = now()
        log.flush(); os.fsync(log.fileno())
        save(result_path, result)
        os.sync()
print(json.dumps(result))
'''


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Missing timezone in Boat snapshot time')
    return parsed


def save(path, value):
    temporary = path.with_suffix('.pending')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def cli(boat, *args, timeout=60):
    result = subprocess.run([boat, '--no-update', '--json', *args], capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Boat {args[0]} failed (exit {result.returncode})')
    return json.loads(result.stdout)


def preservation_guard(info, retention, worker):
    vm = info.get('sandbox', {})
    if vm.get('id') != worker or vm.get('snapshots') is not True or vm.get('dataExpiredAt') is not None:
        raise ValueError('Boat identity/snapshot preservation is not confirmed')
    if retention.get('enabled') is not False or retention.get('snapshotsOff') is not False:
        raise ValueError('Delete-on-stop or disabled snapshots: automatic stop refused')
    return vm


def remote(boat, worker, config, action, timeout):
    command = shlex.join(['python3', '-c', GUEST, json.dumps(config), action])
    # SSH writes the guest's one JSON result directly; `boat exec --json` has a
    # provider envelope/stream format and is not the guest result itself.
    result = subprocess.run([boat, '--no-update', 'ssh', worker, command],
                            capture_output=True, text=True, timeout=timeout + 30)
    if result.returncode:
        raise RuntimeError(f'Boat remote {action} failed (exit {result.returncode})')
    return json.loads(result.stdout)


def stop_and_verify(boat, worker, not_before, deadline=600, poll=2):
    info = cli(boat, 'info', worker)
    preservation_guard(info, cli(boat, 'data-retention', 'status'), worker)
    stopped = {'stopped', 'archived'}
    if info['sandbox'].get('state') not in stopped:
        # No force, delete, resume, cleanup, or account changes on any path.
        try:
            cli(boat, 'stop', worker, timeout=120)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
            # An interrupted response can still have applied the stop. Read
            # back the state; never blindly replay or fall back to --force.
            pass
    end = time.monotonic() + deadline
    while True:
        vm = preservation_guard(cli(boat, 'info', worker),
                                cli(boat, 'data-retention', 'status'), worker)
        if vm.get('state') in stopped:
            if (vm.get('snapshotAvailable') is not True or vm.get('lastSnapshotStatus') != 'completed'
                or not vm.get('snapshotVerifiedAt') or not vm.get('snapshotCompletedAt')
                or timestamp(vm['snapshotCompletedAt']) < timestamp(not_before)
                or timestamp(vm['snapshotVerifiedAt']) < timestamp(vm['snapshotCompletedAt'])):
                raise ValueError('VM stopped but a fresh resumable snapshot is not verified')
            return {key: vm.get(key) for key in ('id', 'state', 'stoppedAt', 'snapshotAvailable',
                    'lastSnapshotStatus', 'snapshotCompletedAt', 'snapshotVerifiedAt')}
        if time.monotonic() >= end:
            raise TimeoutError('Boat stop/snapshot completion remains unconfirmed')
        time.sleep(poll)


def run_session(args):
    config = {key: getattr(args, key) for key in ('worker', 'source', 'output', 'worker_receipt',
               'commit', 'notify_script', 'notify_config', 'timeout', 'ci_args')}
    config['session_id'] = str(uuid.uuid4())
    receipt = {'schema': 'fdisbull-boat-session-v1', 'session_id': config['session_id'],
               'worker': args.worker, 'source_commit': args.commit, 'remote_output': args.output,
               'started_at': now(), 'ci_status': 'not-started', 'stop_status': 'not-requested'}
    if args.receipt.exists() or args.receipt.is_symlink():
        raise ValueError('Preserve the earlier lifecycle receipt; choose a new path')
    vm = preservation_guard(cli(args.boat, 'info', args.worker),
                            cli(args.boat, 'data-retention', 'status'), args.worker)
    if vm.get('state') not in ('running', 'ready', 'active'):
        raise ValueError('Worker is not running; this command never resumes or starts a VM')
    remote(args.boat, args.worker, config, 'check', 60)
    save(args.receipt, receipt)
    try:
        receipt['ci_status'] = 'running'
        save(args.receipt, receipt)
        receipt['ci_result'] = remote(args.boat, args.worker, config, 'run', args.timeout + 240)
        receipt['ci_status'] = receipt['ci_result'].get('ci_status', 'unconfirmed')
    except (Exception, KeyboardInterrupt) as error:
        receipt['ci_status'] = 'unconfirmed'
        receipt['ci_transport_error'] = type(error).__name__
    finally:
        # This runs for CI errors, transport errors, timeout, SIGINT and SIGTERM.
        # The small remote finalizer stops only this run's recorded child group,
        # flushes partial evidence, and leaves every file/container intact.
        try:
            sealed = remote(args.boat, args.worker, config, 'finish', 100)
            receipt['preservation'] = sealed
            receipt['ci_result'] = sealed['result']
            receipt['ci_status'] = sealed['result']['ci_status']
        except (Exception, KeyboardInterrupt) as error:
            receipt['preservation'] = {'persistent_results_flushed': False,
                                       'error_type': type(error).__name__}
        save(args.receipt, receipt)
        if receipt['preservation'].get('persistent_results_flushed') is True:
            try:
                # An earlier live snapshot cannot prove preservation of final
                # results. Require one completed after the finalizer returned.
                receipt['snapshot_not_before'] = now()
                save(args.receipt, receipt)
                receipt['snapshot'] = stop_and_verify(args.boat, args.worker, receipt['snapshot_not_before'],
                                                      deadline=args.stop_timeout)
                receipt['stop_status'] = 'stopped-snapshot-verified'
            except (Exception, KeyboardInterrupt) as error:
                receipt['stop_status'] = 'unconfirmed'
                receipt['stop_error_type'] = type(error).__name__
        else:
            receipt['stop_status'] = 'blocked-results-not-finalized'
        if receipt['stop_status'] != 'stopped-snapshot-verified':
            try:
                receipt['shutdown_alert'] = remote(args.boat, args.worker, config, 'alert', 60)
            except (Exception, KeyboardInterrupt) as error:
                receipt['shutdown_alert'] = {'accepted_by_relay': False,
                                             'error_type': type(error).__name__}
        receipt['finished_at'] = now()
        save(args.receipt, receipt)
    return 0 if (receipt['ci_status'] == 'passed'
                 and receipt['preservation'].get('persistent_results_flushed') is True
                 and receipt['stop_status'] == 'stopped-snapshot-verified') else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boat', default='boat')
    p.add_argument('--worker', required=True)
    p.add_argument('--source', required=True, help='Already staged remote source directory')
    p.add_argument('--output', required=True, help='Persistent remote result directory')
    p.add_argument('--worker-receipt', required=True, help='Fresh remote worker boot receipt')
    p.add_argument('--commit', required=True)
    p.add_argument('--receipt', type=Path, required=True, help='New local lifecycle receipt')
    p.add_argument('--notify-script', default='/home/user/fdisbull-ci/notify/notify.py')
    p.add_argument('--notify-config', default='/home/user/fdisbull-ci/notify/config.secret.json')
    p.add_argument('--timeout', type=int, default=7200, help='Whole CI timeout, in seconds')
    p.add_argument('--stop-timeout', type=int, default=600)
    p.add_argument('ci_args', nargs=argparse.REMAINDER, help='Additional boat-linux.py input arguments after --')
    a = p.parse_args()
    a.ci_args = a.ci_args[1:] if a.ci_args[:1] == ['--'] else a.ci_args
    if not re.fullmatch(r'bx_[A-Za-z0-9_-]+', a.worker) or not re.fullmatch(r'[0-9a-f]{40}', a.commit):
        p.error('Require explicit Boat ID and full source commit')
    if a.timeout <= 0 or a.stop_timeout <= 0:
        p.error('Timeouts must be positive')
    allowed = {'--reuse-stable-backend', '--reuse-layers-backend', '--dosbox-upstream-archive',
               '--dosbox-upstream-sha256', '--retained-base-manifest', '--retained-base-sha256',
               '--retained-base-root', '--retained-os-base', '--retained-windows-fixtures',
               '--require-os-capability', '--expected-bytes', '--reserve-bytes'}
    if len(a.ci_args) % 2 or any(a.ci_args[i] not in allowed for i in range(0, len(a.ci_args), 2)):
        p.error('Only explicit input/storage arguments are allowed; the profile is always all')
    for name in ('source', 'output', 'worker_receipt', 'notify_script', 'notify_config'):
        value = PurePosixPath(getattr(a, name))
        if not value.is_absolute() or not value.is_relative_to('/home/user') or '..' in value.parts:
            p.error('Remote paths must be explicit persistent /home/user paths')
    source, output = PurePosixPath(a.source), PurePosixPath(a.output)
    if output.is_relative_to(source) or source.is_relative_to(output):
        p.error('Source and results must be separate directories')
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    import signal
    signal.signal(signal.SIGTERM, interrupted)
    try:
        return run_session(a)
    except (Exception, KeyboardInterrupt) as error:
        print(f'Boat CI session not started: {type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
