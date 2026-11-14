#!/usr/bin/env python3
"""Run the genuine ordinary qualification under a bound GitHub/OVH job.

The native profiles are not implemented here. No release qualification is claimed.
"""
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
import subprocess
import sys
import time
import urllib.request


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


HERE = Path(__file__).resolve().parent
bootstrap = load('github_bootstrap_helpers', HERE / 'github-bootstrap.py')
exporter = load('ordinary_export_helpers', HERE / 'export-local-artifacts.py')
health = load('offline_health_gate', HERE / 'offline-qualification.py')
bounded = load('production_bounded_runner', HERE / 'recovery_source.py')
MAX_LOG = 4 * 1024 * 1024
POLICY_PATH = Path('/ci-control/production/qualification-policy.json')
REQUIRED_ARTIFACTS = ('artifacts/ordinary/tests.xml', 'artifacts/ordinary/required-contracts.xml',
                      'artifacts/receipts/package-payloads.json', 'artifacts/receipts/ordinary.json')
REPO = 'seeker-cyber-maker/fDisBull'


def api_get(path, token):
    request = urllib.request.Request('https://api.github.com' + path, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(data) > 1024 * 1024:
            raise ValueError('canonical response unavailable')
    return json.loads(data)


def canonical_identity(env, request):
    if (env.get('GITHUB_REPOSITORY') != REPO or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_JOB') != 'qualification' or env.get('RUNNER_NAME') != 'fdisbull-ovh-ca-gh1'):
        raise ValueError('unexpected execution context')
    run, attempt = env.get('GITHUB_RUN_ID', ''), env.get('GITHUB_RUN_ATTEMPT', '')
    if not all(re.fullmatch(r'[1-9][0-9]*', x) for x in (run, attempt)):
        raise ValueError('invalid run identity')
    sha, ref = env.get('GITHUB_SHA', ''), env.get('GITHUB_REF_NAME', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', ref):
        raise ValueError('invalid control identity')
    base = '/repos/' + REPO + '/actions'
    run_doc = request(base + '/runs/' + run + '/attempts/' + attempt)
    if (not isinstance(run_doc, dict) or str(run_doc.get('id')) != run
            or str(run_doc.get('run_attempt')) != attempt or run_doc.get('head_sha') != sha
            or run_doc.get('head_branch') != ref or (run_doc.get('repository') or {}).get('full_name') != REPO):
        raise ValueError('canonical run mismatch')
    jobs = []
    for page in range(1, 11):
        doc = request(base + '/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100&page=' + str(page))
        if not isinstance(doc, dict) or type(doc.get('total_count')) is not int or not isinstance(doc.get('jobs'), list):
            raise ValueError('canonical job list invalid')
        jobs.extend(doc['jobs'])
        if len(jobs) == doc['total_count']: break
        if len(jobs) > doc['total_count'] or len(doc['jobs']) != 100: raise ValueError('incomplete job list')
    else: raise ValueError('job list exceeds bound')
    candidates = [j for j in jobs if isinstance(j, dict) and j.get('name') == 'qualification']
    if len(candidates) != 1: raise ValueError('job is not unique')
    listed = candidates[0]; jid = listed.get('id')
    if type(jid) is not int or jid <= 0: raise ValueError('missing canonical job id')
    job = request(base + '/jobs/' + str(jid))
    fields = ('id', 'run_id', 'name', 'head_sha', 'runner_id')
    if (not isinstance(job, dict) or any(job.get(k) != listed.get(k) for k in fields)
            or str(job.get('run_id')) != run or job.get('head_sha') != sha
            or job.get('runner_id') != 21 or job.get('status') != 'in_progress'):
        raise ValueError('canonical job or runner mismatch')
    return {'repository': REPO, 'run_id': run, 'run_attempt': attempt, 'job_id': str(jid),
            'runner_id': '21', 'job_name': 'qualification', 'control_sha': sha, 'ref': ref}


def sanitized_env(env, identity, source_sha, candidate):
    forbidden = ('TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'API_KEY', 'AUTH', 'PROXY')
    result = {k: v for k, v in env.items() if not any(x in k.upper() for x in forbidden)}
    for key in ('CI_PIPELINE_ID', 'CI_JOB_ID', 'CI_RUNNER_ID'): result.pop(key, None)
    candidate = Path(candidate).resolve(strict=True)
    builds_dir = candidate.parent
    if not candidate.is_dir() or builds_dir == candidate or not os.access(builds_dir, os.W_OK):
        raise ValueError('candidate builds parent unavailable')
    result.update(FDISBULL_EXECUTION_ORIGIN='github', CI_COMMIT_SHA=source_sha, CI_JOB_NAME='qualification',
                  CI_PROJECT_DIR=str(candidate), CI_BUILDS_DIR=str(builds_dir),
                  FDISBULL_GITHUB_REPOSITORY=identity['repository'], FDISBULL_GITHUB_CONTROL_REF=identity['ref'],
                  FDISBULL_GITHUB_CONTROL_SHA=identity['control_sha'])
    for key in ('run_id', 'run_attempt', 'job_id', 'runner_id'):
        result['FDISBULL_GITHUB_' + key.upper()] = identity[key]
    return result


def run_ordinary(candidate, env, log_path):
    proc = subprocess.Popen(['bash', 'scripts/ci/test-and-package.sh'], cwd=candidate, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    kept = total = 0
    with open(log_path, 'xb') as log:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk: break
            total += len(chunk)
            piece = chunk[:max(0, MAX_LOG - kept)]
            log.write(piece); kept += len(piece)
        log.flush(); os.fsync(log.fileno())
    return proc.wait(), {'total_bytes': total, 'retained_bytes': kept, 'truncated': total > kept}


SYSTEM_PACKAGES = ('ca-certificates', 'curl', 'xz-utils', 'git', 'build-essential', 'clang',
                   'libx11-dev', 'pkg-config', 'zlib1g-dev', 'libzstd-dev')


def run_system_prepare(env, log_path, *, runner=bounded.run_command):
    """Install the same fixed OS prerequisites as GitLab, with bounded capture."""
    child_env = dict(env, DEBIAN_FRONTEND='noninteractive')
    commands = (('/usr/bin/apt-get', 'update'),
                ('/usr/bin/apt-get', 'install', '-y', '--no-install-recommends', *SYSTEM_PACKAGES))
    steps = []; retained = bytearray(); status = 'passed'
    for command in commands:
        try:
            result = runner(list(command), cwd='/', env=child_env, input_bytes=None, timeout=300)
            valid = (isinstance(result, dict) and isinstance(result.get('stdout'), bytes)
                     and isinstance(result.get('stderr'), bytes) and type(result.get('returncode')) is int
                     and type(result.get('timed_out')) is bool and type(result.get('overflow')) is bool
                     and len(result['stdout']) <= bounded.LIMIT and len(result['stderr']) <= bounded.LIMIT)
            if not valid: raise ValueError('invalid process result')
            payload = result['stdout'] + result['stderr']
            remaining = max(0, MAX_LOG - len(retained)); retained.extend(payload[:remaining])
            ok = result['returncode'] == 0 and not result['timed_out'] and not result['overflow']
            steps.append({'name': 'update' if command[1] == 'update' else 'install',
                          'exit_code': result['returncode'], 'timed_out': result['timed_out'],
                          'overflow': result['overflow'] or len(payload) > remaining, 'passed': ok})
            if not ok: status = 'failed'; break
        except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError):
            steps.append({'name': 'update' if command[1] == 'update' else 'install',
                          'exit_code': None, 'timed_out': False, 'overflow': False, 'passed': False})
            status = 'failed'; break
    if status == 'failed' and not retained: retained.extend(b'System prerequisite preparation failed.\n')
    bootstrap._write_exclusive(log_path, bytes(retained))
    return {'status': status, 'steps': steps, 'capture_limit_bytes': MAX_LOG}


def read_health(identity, source_sha, control_root):
    path = Path(control_root) / 'production' / 'health' / identity['run_id'] / (identity['run_attempt'] + '.json')
    bootstrap._no_symlink_parents(path)
    if path.stat().st_size > health.MAX_RECORD_BYTES + 4096: raise ValueError('health capsule too large')
    capsule = json.loads(path.read_bytes())
    if (not isinstance(capsule, dict) or capsule.get('schema') != 'fdisbull-host-health-capsule-1'
            or any(capsule.get(k) != identity[k] for k in ('run_id', 'run_attempt', 'control_sha', 'ref'))
            or capsule.get('source_sha') != source_sha): raise ValueError('health capsule identity mismatch')
    envelope = capsule.get('host_health')
    if (not isinstance(envelope, dict) or envelope.get('helper_sha256') != health.HELPER_SHA256
            or envelope.get('failure') is not None or not health._valid(envelope.get('record'))):
        raise ValueError('health capsule invalid')
    record = envelope['record']; stamp = record.get('observed_epoch')
    if (record['healthy'] is not True or record['receipt']['durable'] is not True
            or type(stamp) not in (int, float) or not 0 <= time.time() - stamp <= 120):
        raise ValueError('health capsule stale or unhealthy')
    return capsule


def execute(candidate, source_sha, nonce, output, *, env, request, policy_sha, runner=run_ordinary,
            system_preparer=run_system_prepare,
            host_root=Path('/ci-host-results'), control=None, mounted=bootstrap._mounted, policy_path=POLICY_PATH,
            control_root=Path('/ci-control')):
    if (not re.fullmatch(r'[0-9a-f]{40}', source_sha) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', nonce)
            or not isinstance(policy_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', policy_sha)):
        raise ValueError('invalid candidate identity')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64': raise ValueError('Linux x86_64 required')
    identity = canonical_identity(env, request)
    capsule = read_health(identity, source_sha, control_root)
    candidate = Path(candidate).resolve(strict=True); control = Path(control).resolve(strict=True)
    bootstrap._clean_candidate(control, identity['control_sha']); bootstrap._clean_candidate(candidate, source_sha)
    host_root = Path(host_root).absolute()
    run_root = host_root / identity['run_id'] / identity['run_attempt']
    bootstrap._no_symlink_parents(run_root)
    if not run_root.is_dir() or not mounted(run_root): raise ValueError('host results mount unavailable')
    if shutil.disk_usage(run_root).free - 12_000_000_000 < 20_000_000_000: raise ValueError('storage admission refused')
    parent = run_root / 'qualification'
    bootstrap._no_symlink_parents(parent); parent.mkdir(parents=True, exist_ok=True)
    dest = parent / identity['job_id']
    if dest.exists() or dest.is_symlink(): raise ValueError('existing host export')
    # The uniquely created directory is observable while the job runs; job.json
    # is written last and is the closed-export marker. Never replace prior output.
    dest.mkdir(mode=0o700)
    staging = dest
    start = {'schema': 'fdisbull-github-candidate-start-1', **identity, 'source_sha': source_sha, 'nonce': nonce,
             'candidate_head': bootstrap._git(candidate, 'rev-parse', 'HEAD'),
             'control_head': bootstrap._git(control, 'rev-parse', 'HEAD')}
    bootstrap._write_exclusive(staging / 'candidate-start.json', (json.dumps(start, sort_keys=True) + '\n').encode())
    bootstrap._write_exclusive(staging / 'caller-health.json', (json.dumps({'target': {**identity, 'source_sha': source_sha},
                                                           'host_capsule': capsule}, sort_keys=True) + '\n').encode())
    for directory in (staging, parent):
        fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)
    expected_policy = {'schema': 'fdisbull-ci-qualification-policy-1', 'profile': 'ordinary',
                       'repository': REPO, 'runner_id': 21, 'cpus': 2, 'memory_mib': 9216,
                       'additional_swap': False, 'required_artifacts': list(REQUIRED_ARTIFACTS)}
    policy_path = Path(policy_path)
    try:
        bootstrap._no_symlink_parents(policy_path)
        if not policy_path.exists():
            raise FileNotFoundError()
        if not policy_path.is_file():
            raise ValueError('invalid policy file')
        policy_bytes = policy_path.read_bytes()
        if len(policy_bytes) > 16384 or hashlib.sha256(policy_bytes).hexdigest() != policy_sha:
            raise ValueError('policy hash mismatch')
        if json.loads(policy_bytes) != expected_policy:
            raise ValueError('policy schema mismatch')
        policy_error = None
    except FileNotFoundError:
        policy_error = 'missing_ci_owned_input'
    except (OSError, ValueError, UnicodeError):
        policy_error = 'qualification_policy_invalid'
    if policy_error:
        system_result = {'status': 'skipped', 'steps': [], 'capture_limit_bytes': MAX_LOG}
        bootstrap._write_exclusive(staging / 'system-preparation.log', b'')
        diagnostic = {'kind': 'infrastructure', 'reason': policy_error, 'input_key': 'qualification-policy',
                      'expected_sha256': policy_sha, 'target': {'provider': 'github', **identity, 'source_sha': source_sha}}
        dest_diag = candidate / 'artifacts' / 'recovery' / 'diagnostic.json'
        dest_diag.parent.mkdir(parents=True, exist_ok=True)
        bootstrap._write_exclusive(dest_diag, (json.dumps(diagnostic, sort_keys=True) + '\n').encode())
        message = b'Qualification policy preflight refused.\n'
        bootstrap._write_exclusive(staging / 'qualification.log', message)
        code, log_meta = 1, {'total_bytes': len(message), 'retained_bytes': len(message), 'truncated': False}
    else:
        child_env = sanitized_env(env, identity, source_sha, candidate)
        system_result = system_preparer(child_env, staging / 'system-preparation.log')
        if not isinstance(system_result, dict) or system_result.get('status') not in ('passed', 'failed'):
            raise ValueError('system preparation outcome unknown')
        if system_result['status'] == 'passed':
            code, log_meta = runner(candidate, child_env, staging / 'qualification.log')
        else:
            prep_log = (staging / 'system-preparation.log').read_bytes()
            if not prep_log: prep_log = b'System prerequisite preparation failed.\n'
            bootstrap._write_exclusive(staging / 'qualification.log', prep_log)
            code, log_meta = 1, {'total_bytes': len(prep_log), 'retained_bytes': len(prep_log),
                                 'truncated': False, 'basis': 'bounded-system-preparation-capture'}
    bootstrap._write_exclusive(staging / 'system-preparation.json', (json.dumps(system_result, sort_keys=True) + '\n').encode())
    if type(code) is not int: raise ValueError('qualification outcome unknown')
    exporter.export(candidate, staging / 'exported', source_sha)
    bootstrap._clean_candidate(control, identity['control_sha'])
    selected = []
    for item in sorted((staging / 'exported').rglob('*')):
        if item.is_symlink(): raise ValueError('symlink in export')
        if item.is_file():
            relative = item.relative_to(staging / 'exported')
            original = candidate / relative
            bootstrap._no_symlink_parents(original)
            with item.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            with original.open('rb') as stream: source_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if item.stat().st_size != original.stat().st_size or digest != source_digest:
                raise ValueError('host export differs from original')
            selected.append({'path': relative.as_posix(), 'size': item.stat().st_size, 'sha256': digest})
    required = set(REQUIRED_ARTIFACTS)
    if code == 0 and not required <= {item['path'] for item in selected}: raise ValueError('ordinary artifacts incomplete')
    (staging / 'inventory.json').write_text(json.dumps(selected, sort_keys=True) + '\n')
    meta = {'schema': 'fdisbull-production-job-export-1', **identity, 'source_sha': source_sha,
            'job_status': 'success' if code == 0 else 'failed', 'qualification_exit_code': code,
            'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'export_success': True,
            'files': len(selected), 'project_directory': str(candidate), 'log': log_meta,
            'qualification_stage': 'system-preparation' if system_result['status'] == 'failed' else
                                   'policy-preflight' if policy_error else 'ordinary-tests'}
    for name in ('candidate-start.json', 'caller-health.json', 'source-postcheck.json', 'inventory.json', 'qualification.log',
                 'system-preparation.json', 'system-preparation.log'):
        data = (staging / name).read_bytes(); meta[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    for f in staging.rglob('*'):
        if f.is_file():
            with f.open('rb') as stream: os.fsync(stream.fileno())
    for directory in sorted((p for p in staging.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)
    fd = os.open(staging, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)
    bootstrap._write_exclusive(staging / 'job.json', (json.dumps(meta, sort_keys=True) + '\n').encode())
    fd = os.open(staging, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)
    out = Path(output); bootstrap._no_symlink_parents(out); out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(dest, out / 'qualification')
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'source-sha', 'nonce', 'output', 'control', 'policy-sha'): p.add_argument('--' + name, required=True)
    args = p.parse_args()
    token = os.environ.get('GITHUB_TOKEN')
    if not token: return 1
    try:
        meta = execute(args.candidate, args.source_sha, args.nonce, args.output, env=os.environ,
                       request=lambda path: api_get(path, token), control=args.control, policy_sha=args.policy_sha)
    except Exception as exc:
        print(json.dumps({'status': 'incomplete', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps({'status': meta['job_status'], 'native_profile': 'unsupported'}))
    return 0 if meta['job_status'] == 'success' else 1


if __name__ == '__main__': raise SystemExit(main())
