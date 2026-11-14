#!/usr/bin/env python3
"""Verify a bounded manual GitHub/OVH bootstrap; never qualify a release."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

MIN_RESERVE = 20_000_000_000
TARGET_RESERVE = 40_000_000_000
EXPECTED_ALLOCATION = 1_000_000_000


def _git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, timeout=30, check=True)
    return result.stdout.strip()


def _clean_candidate(repo, sha):
    if _git(repo, 'rev-parse', 'HEAD') != sha:
        raise ValueError('candidate HEAD mismatch')
    if _git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('candidate tracked source is dirty')


def _mounted(path):
    # A bind mount may share its device with the host root, so inspect mountinfo.
    target = str(path.resolve(strict=True)).replace(' ', '\\040').replace('\t', '\\011')
    with open('/proc/self/mountinfo', encoding='utf-8') as stream:
        return any(line.split(' ', 5)[4] == target for line in stream if len(line.split(' ', 5)) >= 5)


def _no_symlink_parents(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink(): raise ValueError('symlink in destination path')


def _write_exclusive(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def _atomic_publish(source, destination):
    # Linux renameat2 with RENAME_NOREPLACE prevents replacing even an empty directory.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None: raise RuntimeError('atomic no-replace rename unavailable')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def execute(candidate, source_sha, nonce, output, *, env=None, host_root=Path('/ci-host-results'),
            control=None, mounted=_mounted, system=platform.system, machine=platform.machine):
    env = os.environ if env is None else env
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha): raise ValueError('invalid candidate SHA')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', nonce): raise ValueError('invalid nonce')
    expected = {'GITHUB_REPOSITORY': 'seeker-cyber-maker/fDisBull', 'GITHUB_SERVER_URL': 'https://github.com',
                'GITHUB_EVENT_NAME': 'workflow_dispatch', 'RUNNER_NAME': 'fdisbull-ovh-ca-gh1'}
    if any(env.get(k) != v for k, v in expected.items()): raise ValueError('GitHub execution identity mismatch')
    if system() != 'Linux' or machine() != 'x86_64': raise ValueError('Linux x86_64 required')
    run_id, attempt = env.get('GITHUB_RUN_ID', ''), env.get('GITHUB_RUN_ATTEMPT', '')
    control_sha, job = env.get('GITHUB_SHA', ''), env.get('GITHUB_JOB', '')
    if not re.fullmatch('[0-9]+', run_id) or not re.fullmatch('[0-9]+', attempt): raise ValueError('run identity missing')
    if not re.fullmatch('[0-9a-f]{40}', control_sha) or job != 'bootstrap': raise ValueError('control identity missing')
    host_root = Path(host_root).absolute()
    _no_symlink_parents(host_root)
    if not host_root.is_dir() or not mounted(host_root): raise ValueError('host results mount unavailable')
    free = shutil.disk_usage(host_root).free
    if free - EXPECTED_ALLOCATION < MIN_RESERVE: raise ValueError('host storage admission refused')
    candidate = Path(candidate).resolve(strict=True)
    control = Path(control or Path(__file__).resolve().parents[2]).resolve(strict=True)
    _clean_candidate(control, control_sha)
    _clean_candidate(candidate, source_sha)
    output = Path(output).absolute()
    _no_symlink_parents(output)
    if output.exists(): raise ValueError('output already exists')
    parent = host_root / run_id / attempt
    _no_symlink_parents(parent)
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / 'bootstrap'
    if destination.exists() or destination.is_symlink(): raise ValueError('bootstrap export already exists')
    staging = Path(tempfile.mkdtemp(prefix='.bootstrap-', dir=parent))
    empty = staging / 'empty-receipts'
    empty.mkdir()
    check_output = staging / 'qualification-should-not-exist.json'
    check = subprocess.run([sys.executable, str(control / 'scripts/check_ci_qualification.py'), '--root', str(empty),
                            '--source-commit', source_sha, '--pipeline-id', '0', '--output', str(check_output)],
                           capture_output=True, text=True, timeout=30, check=False)
    missing = ['ordinary.json', 'native-stable.json', 'native-layers.json', 'native-unified.json']
    if (check.returncode != 2 or 'Incomplete qualification: Missing or invalid receipt:' not in check.stderr
            or not check.stderr.rstrip().endswith('ordinary.json') or check_output.exists()
            or any((empty / 'artifacts/receipts' / name).exists() for name in missing)):
        raise ValueError('qualification checker did not reject missing receipts')
    _clean_candidate(control, control_sha)
    _clean_candidate(candidate, source_sha)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    runtime = {'schema': 'fdisbull-github-ovh-bootstrap-v1', 'stage': 'completed',
               'release_ready': False, 'qualification_claimed': False, 'repository': expected['GITHUB_REPOSITORY'],
               'server_url': expected['GITHUB_SERVER_URL'], 'event': expected['GITHUB_EVENT_NAME'],
               'control_sha': control_sha, 'source_sha': source_sha, 'run_id': run_id, 'run_attempt': attempt,
               'job_name': job, 'runner_name': expected['RUNNER_NAME'], 'nonce': nonce, 'observed_at': now,
               'platform': {'system': system(), 'machine': machine(), 'python': platform.python_version()},
               'source_postcheck': {'candidate_head': source_sha, 'tracked_worktree_dirty': False,
                                    'control_head': control_sha, 'control_tracked_worktree_dirty': False},
               'storage': {'free_bytes': free, 'expected_bytes': EXPECTED_ALLOCATION,
                           'minimum_reserve_bytes': MIN_RESERVE, 'target_reserve_bytes': TARGET_RESERVE},
               'qualification_check': {'status': 'rejected_missing_receipts', 'exit_code': check.returncode,
                                       'missing': missing, 'pipeline_id': None,
                                       'validation_sentinel': '0 is a checker argument only; not a provider identity'},
               'provider_job_id': None}
    handoff = {'schema': 'fdisbull-github-ovh-handoff-v1', 'stage': 'completed', 'release_ready': False,
               'source_sha': source_sha, 'control_sha': control_sha, 'run_id': run_id, 'run_attempt': attempt,
               'nonce': nonce, 'provider_job_id': None,
               'next': 'Resolve canonical GitHub job ID; ordinary and required-native qualification remain separate.'}
    files = {}
    for name, value in [('runtime.json', runtime), ('handoff.json', handoff)]:
        data = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
        _write_exclusive(staging / name, data)
        files[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    inventory = {'schema': 'fdisbull-github-bootstrap-inventory-v1', 'files': files}
    data = (json.dumps(inventory, indent=2, sort_keys=True) + '\n').encode()
    _write_exclusive(staging / 'inventory.json', data)
    # Empty checker input is a transient control directory, excluded from export.
    empty.rmdir()
    dfd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    _atomic_publish(staging, destination)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('runtime.json', 'handoff.json', 'inventory.json'):
        data = (destination / name).read_bytes()
        _write_exclusive(output / name, data)
        if (output / name).read_bytes() != data: raise ValueError('artifact readback mismatch')
    return runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = execute(args.candidate, args.source_sha, args.nonce, args.output)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'incomplete', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps({'stage': result['stage'], 'release_ready': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
