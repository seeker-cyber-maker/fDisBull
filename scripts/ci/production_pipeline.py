#!/usr/bin/env python3
"""Run one durable, finite source-to-release pipeline on the VPS host."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import signal
import subprocess
import sys
import time
import tomllib
import uuid

REQUEST_ROOT = Path('/var/lib/fdisbull-ci/control/production')
STATE_ROOT = Path('/var/lib/fdisbull-ci/control/recovery/production')
DATA_ROOT = Path('/var/lib/fdisbull-ci')
SOURCE_ROOT = Path('/var/lib/fdisbull-ci/control/production/sources')
OUTPUT_ROOT = Path('/var/lib/fdisbull-ci/results/pipelines')
REPOSITORY = 'seeker-cyber-maker/fDisBull'
REPOSITORY_URL = 'https://github.com/' + REPOSITORY + '.git'
REPOSITORY_ID = 1431097789
VERSION = '0.35.0'
TAG = 'v' + VERSION
MAX_REQUEST = 128 * 1024
MAX_DEADLINE = 8 * 60 * 60
DRIVER_TIMEOUT = 2 * 60 * 60
HEX = re.compile(r'[0-9a-f]{64}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
ASSET_OPTIONS = {
    'dosbox_upstream_archive': '--dosbox-upstream-archive',
    'dosbox_upstream_sha256': '--dosbox-upstream-sha256',
    'retained_base_manifest': '--retained-base-manifest',
    'retained_base_sha256': '--retained-base-sha256',
    'retained_base_root': '--retained-base-root',
    'retained_os_base': '--retained-os-base',
    'retained_windows_fixtures':'--retained-windows-fixtures',
    'authored_win16_fixture': '--authored-win16-fixture',
    'reuse_stable_backend': '--reuse-stable-backend',
    'reuse_layers_backend': '--reuse-layers-backend',
}
RETAINED_BASE_KEYS = {'retained_base_manifest', 'retained_base_sha256', 'retained_base_root', 'retained_os_base'}
OWNER_LABEL = 'n8n-release-pipeline'


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _private_dir(path: Path) -> None:
    if (path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.geteuid()
            or path.stat().st_mode & 0o077):
        raise ValueError('private pipeline directory unavailable')


def _json_file(path: Path, maximum=MAX_REQUEST, *, private=True) -> dict:
    if (path.is_symlink() or not path.is_file() or path.stat().st_uid != os.geteuid()
            or path.stat().st_mode & 0o022 or (private and path.stat().st_mode & 0o077) or path.stat().st_size > maximum):
        raise ValueError('private pipeline file unavailable')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('pipeline JSON object required')
    return value


def _contained(path_value, root: Path, *, exists=False) -> Path:
    if not isinstance(path_value, str) or not path_value.startswith('/'):
        raise ValueError('pipeline path must be absolute')
    path = Path(path_value)
    if str(path) != path_value or any(part in ('.', '..') for part in PurePosixPath(path_value).parts):
        raise ValueError('unsafe pipeline path')
    root = Path(root)
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError('pipeline path outside authorized root') from None
    if path == root:
        raise ValueError('pipeline path must name a child')
    if exists:
        if path.is_symlink() or not path.exists() or any(p.is_symlink() for p in (path, *path.parents) if p != Path('/')):
            raise ValueError('pipeline path unavailable')
    else:
        parent = path.parent
        if not parent.is_dir() or parent.is_symlink() or any(p.is_symlink() for p in parent.parents if p != Path('/')):
            raise ValueError('pipeline parent unavailable')
        if path.exists() or path.is_symlink():
            raise ValueError('pipeline path already exists')
    return path


def _destination(path_value,root):
    """Retained output is valid for readback; new execution checks freshness."""
    path=Path(path_value) if isinstance(path_value,str) else None
    if path is not None and path.exists():
        result=_contained(path_value,root,exists=True)
        if not result.is_dir():raise ValueError('pipeline destination must be a directory')
        return result
    return _contained(path_value,root)


def _validate_options(value):
    if not isinstance(value, dict) or set(value) - set(ASSET_OPTIONS):
        raise ValueError('unsupported driver option')
    if not {'dosbox_upstream_archive', 'dosbox_upstream_sha256', 'authored_win16_fixture'} <= set(value):
        raise ValueError('native/offline inputs are required')
    if not HEX.fullmatch(str(value['dosbox_upstream_sha256'])):
        raise ValueError('invalid DOSBox upstream archive hash')
    if set(value) & RETAINED_BASE_KEYS and not RETAINED_BASE_KEYS <= set(value):
        raise ValueError('retained base options must be complete')
    normalized = {}
    for name, item in value.items():
        if name.endswith('_sha256'):
            if not HEX.fullmatch(str(item)):
                raise ValueError('invalid driver input hash')
            normalized[name] = item
            continue
        path = _contained(item, DATA_ROOT, exists=True)
        normalized[name] = str(path)
    return normalized


def inspect_request(config_pointer) -> dict:
    """Read and validate one immutable, root-private release request."""
    if (not isinstance(config_pointer, dict) or set(config_pointer) != {'path', 'sha256'}
            or not HEX.fullmatch(str(config_pointer['sha256']))):
        raise ValueError('invalid request pointer')
    path = _contained(config_pointer['path'], REQUEST_ROOT, exists=True)
    if path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o077:
        raise ValueError('request is not root-private')
    raw = path.read_bytes()
    if len(raw) > MAX_REQUEST or hashlib.sha256(raw).hexdigest() != config_pointer['sha256']:
        raise ValueError('request hash or size mismatch')
    request = json.loads(raw)
    expected = {'schema', 'key', 'source_sha', 'version', 'tag', 'source_root', 'output_root',
                'driver_options', 'deadline_seconds', 'publish'}
    if (not isinstance(request, dict) or set(request) != expected
            or request['schema'] != 'fdisbull-production-release-request-1'
            or not isinstance(request['key'], str) or not 1 <= len(request['key']) <= 180
            or any(ord(c) < 32 for c in request['key'])
            or not SHA.fullmatch(str(request['source_sha']))
            or request['version'] != VERSION or request['tag'] != TAG
            or type(request['deadline_seconds']) is not int
            or not 1 <= request['deadline_seconds'] <= MAX_DEADLINE
            or request['publish'] is not True):
        raise ValueError('release request schema or identity invalid')
    request['source_root'] = str(_destination(request['source_root'], SOURCE_ROOT))
    request['output_root'] = str(_destination(request['output_root'], OUTPUT_ROOT))
    if Path(request['source_root']).is_relative_to(Path(request['output_root'])) or Path(request['output_root']).is_relative_to(Path(request['source_root'])):
        raise ValueError('source and output roots overlap')
    request['driver_options'] = _validate_options(request['driver_options'])
    request['_request_sha256'] = config_pointer['sha256']
    request['_request_path'] = str(path)
    return request


def _write_once(path: Path, value) -> None:
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    _write_bytes_once(path, data)


def _write_bytes_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _replace(path: Path, value) -> None:
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    _write_once(temp, value)
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _clean_env():
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': '/nonexistent',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never',
            'LC_ALL': 'C.UTF-8'}


def _command(args, *, cwd='/', timeout=60, deadline=None, guard=None, health=None):
    command_deadline = time.monotonic() + timeout
    if deadline is not None:
        command_deadline = min(command_deadline, deadline)
    process = subprocess.Popen(args, cwd=cwd, env=_clean_env(), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    for stream in buffers:
        selector.register(stream, selectors.EVENT_READ)
    last_health = 0.0
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= command_deadline:
                raise TimeoutError('bounded pipeline command deadline expired')
            if guard is not None:
                guard()
            if health is not None and now - last_health >= 60:
                value = health()
                if not isinstance(value, dict) or value.get('state') != 'healthy':
                    raise RuntimeError('host health unavailable')
                last_health = now
            for key, _ in selector.select(min(1.0, command_deadline - now)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = buffers[key.fileobj]
                target.extend(chunk)
                if len(target) > 1024 * 1024:
                    raise ValueError('pipeline command output exceeded bound')
        code = process.wait(timeout=max(.01, command_deadline - time.monotonic()))
        if code != 0:
            raise RuntimeError('bounded pipeline command failed')
        return bytes(buffers[process.stdout])
    except BaseException:
        _terminate(process)
        raise
    finally:
        selector.close()
        process.stdout.close(); process.stderr.close()


def _source_checkout(request, deadline, *, guard, health, state_root):
    source = Path(request['source_root'])
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists() or source.is_symlink():
        raise ValueError('source checkout already exists')
    remaining = max(1, int(deadline - time.monotonic()))
    _command(['/usr/bin/git', 'init', str(source)], timeout=30,
             deadline=deadline, guard=guard, health=health)
    _command(['/usr/bin/git', 'remote', 'add', 'origin', REPOSITORY_URL], cwd=str(source),
             timeout=30, deadline=deadline, guard=guard, health=health)
    _save_progress(state_root / 'last-progress.json', phase='source-cloned', request=request)
    remaining = max(1, int(deadline - time.monotonic()))
    _command(['/usr/bin/git', 'fetch', '--depth=1', '--no-tags', 'origin', request['source_sha']], cwd=str(source),
             timeout=min(600, remaining), deadline=deadline, guard=guard, health=health)
    _save_progress(state_root / 'last-progress.json', phase='source-fetched', request=request)
    _command(['/usr/bin/git', 'checkout', '--detach', request['source_sha']], cwd=str(source), timeout=60,
             deadline=deadline, guard=guard, health=health)
    remote = _command(['/usr/bin/git', 'remote', 'get-url', 'origin'], cwd=str(source),
                      deadline=deadline, guard=guard, health=health).decode().strip()
    head = _command(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=str(source),
                    deadline=deadline, guard=guard, health=health).decode().strip()
    status = _command(['/usr/bin/git', 'status', '--porcelain', '--untracked-files=all'], cwd=str(source),
                      deadline=deadline, guard=guard, health=health).decode()
    if remote != REPOSITORY_URL or head != request['source_sha'] or status:
        raise ValueError('canonical source checkout identity or cleanliness failed')
    with (source / 'pyproject.toml').open('rb') as stream:
        project = tomllib.load(stream).get('project', {})
    if project.get('version') != VERSION:
        raise ValueError('source version differs from requested release')
    return source


def _host_receipt(path):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('production pipeline requires Linux x86_64')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if not UUID.fullmatch(boot_id):
        raise ValueError('host boot identity unavailable')
    value = {'schema': 'fdisbull-local-docker-host-v1', 'execution_origin': 'local-linux',
             'architecture': 'x86_64', 'host_boot_id': boot_id, 'host_name': platform.node(),
             'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _write_once(path, value)
    return value


def _driver_argv(source, output, receipt, options):
    driver = source / 'scripts/ci/boat-linux.py'
    argv = [sys.executable, str(driver), '--source', str(source), '--output', str(output),
            '--worker-receipt', str(receipt), '--local-host', '--profile', 'all',
            '--windows-acceptance', 'pe64-pe32-win16', '--timeout', str(DRIVER_TIMEOUT)]
    for capability in ('wine64','dos','pe32','win16-guards'):
        argv.extend(['--require-os-capability',capability])
    for name, option in ASSET_OPTIONS.items():
        if name in options:
            argv.extend([option, str(options[name])])
    return argv


def _save_progress(path, *, phase, request, run_id=None, detail=None):
    _replace(path, {'schema': 'fdisbull-production-pipeline-progress-1', 'phase': phase,
                    'request_sha256': request['_request_sha256'], 'source_sha': request['source_sha'],
                    'run_id': run_id, 'detail': detail, 'observed_at': time.time()})


def _read_run_id(output, source_sha):
    run_file = Path(output) / 'run.json'
    if not run_file.exists() or run_file.is_symlink():
        return None
    try:record = _json_file(run_file,private=False)
    except (FileNotFoundError,json.JSONDecodeError):return None
    run_id = record.get('local_run_id')
    if (not UUID.fullmatch(str(run_id)) or record.get('source_commit') != source_sha
            or record.get('execution_origin') != 'local-linux'):
        raise ValueError('driver run identity mismatch')
    return run_id


def _docker_json(args, *, deadline=None, guard=None, health=None):
    out = _command(['/usr/bin/docker', *args], timeout=45, deadline=deadline,
                   guard=guard, health=health)
    return out.decode().strip()


def _owned_container_ids(run_id, source_sha, *, deadline=None, guard=None, health=None):
    output = _docker_json(['ps', '-aq', '--filter', 'label=fdisbull.ci.owner=' + OWNER_LABEL,
                           '--filter', 'label=fdisbull.ci.pipeline_run=' + run_id,
                           '--filter', 'label=fdisbull.ci.source=' + source_sha],
                          deadline=deadline, guard=guard, health=health)
    ids = [line for line in output.splitlines() if line]
    if any(not re.fullmatch(r'[0-9a-f]{12,64}', value) for value in ids) or len(ids) > 128:
        raise ValueError('owned container list invalid')
    return ids


def _inspect_container(container_id, run_id, source_sha, *, deadline=None, guard=None, health=None):
    raw = _docker_json(['inspect', container_id], deadline=deadline, guard=guard, health=health)
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError('owned container inspect unavailable')
    row = rows[0]
    labels = (row.get('Config') or {}).get('Labels')
    state = row.get('State')
    if (not isinstance(labels, dict) or labels.get('fdisbull.ci.owner') != OWNER_LABEL
            or labels.get('fdisbull.ci.pipeline_run') != run_id
            or labels.get('fdisbull.ci.source') != source_sha
            or not isinstance(state, dict) or type(state.get('Running')) is not bool):
        raise ValueError('container ownership identity mismatch')
    return state['Running']


def _stop_owned(run_id, source_sha, *, deadline=None, guard=None, health=None):
    if run_id is None:
        return {'checked': 0, 'stopped': 0, 'running_after': 0}
    ids = _owned_container_ids(run_id, source_sha, deadline=deadline, guard=guard, health=health)
    stopped = 0
    for container_id in ids:
        if _inspect_container(container_id, run_id, source_sha, deadline=deadline, guard=guard, health=health):
            _docker_json(['stop', '--time', '10', container_id], deadline=deadline, guard=guard, health=health)
            stopped += 1
    remaining = [container_id for container_id in
                 _owned_container_ids(run_id, source_sha, deadline=deadline, guard=guard, health=health)
                 if _inspect_container(container_id, run_id, source_sha,
                                       deadline=deadline, guard=guard, health=health)]
    if remaining:
        raise RuntimeError('owned container cleanup incomplete')
    return {'checked': len(ids), 'stopped': stopped, 'running_after': 0}


def _drive(argv, *, output, request, state_root, guard, health, deadline, sleeper):
    log_path = state_root / 'pipeline.log'
    process = subprocess.Popen(argv, cwd='/', env=_clean_env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
    run_id = None
    last_health = 0.0
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        with log_path.open('xb') as log:
            while selector.get_map():
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError('pipeline deadline expired')
                guard()
                if now - last_health >= 60:
                    current = health()
                    if not isinstance(current, dict) or current.get('state') != 'healthy':
                        raise RuntimeError('host health unavailable')
                    last_health = now
                observed_run = _read_run_id(output, request['source_sha'])
                if observed_run is not None:
                    run_id = observed_run
                wait = min(1.0, deadline - now, max(0.1, 60.0 - (now - last_health)))
                for _, _ in selector.select(wait):
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        selector.unregister(process.stdout)
                        break
                    log.write(chunk); log.flush()
                    if len(chunk) <= 65536:
                        lines = chunk.decode('utf-8', 'replace').splitlines()
                        if lines:
                            _save_progress(state_root / 'last-progress.json', phase='driver', request=request,
                                           run_id=run_id, detail=lines[-1][:300])
                    observed_run = _read_run_id(output, request['source_sha'])
                    if observed_run is not None:
                        run_id = observed_run
            code = process.wait(timeout=max(1, deadline - time.monotonic()))
            if code != 0:
                raise RuntimeError('pipeline driver returned nonzero')
    except BaseException:
        _terminate(process)
        raise
    finally:
        selector.close()
        if process.stdout is not None:
            process.stdout.close()
    return run_id


def _terminate(process):
    if process.poll() is None:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=10)


def _identity(root: Path, relative: str):
    pure = PurePosixPath(relative)
    if pure.is_absolute() or str(pure) != relative or any(p in ('', '.', '..') for p in pure.parts):
        raise ValueError('unsafe qualification artifact path')
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('qualification artifact missing or unsafe')
    return {'path': relative, 'sha256': _digest(path), 'size': path.stat().st_size}


def _read_linked(root: Path, ref):
    if (not isinstance(ref, dict) or set(ref) != {'path', 'sha256', 'size'}
            or not HEX.fullmatch(str(ref['sha256'])) or type(ref['size']) is not int or ref['size'] < 0):
        raise ValueError('linked qualification evidence identity invalid')
    actual = _identity(root, ref['path'])
    if (actual['sha256'], actual['size']) != (ref['sha256'], ref['size']):
        raise ValueError('linked qualification evidence changed')
    value = json.loads((root / ref['path']).read_bytes())
    if not isinstance(value, dict):
        raise ValueError('linked qualification JSON object required')
    return value


def _release_manifest(request, output_root):
    qualification_root = output_root / 'qualification'
    qualification_path = qualification_root / 'qualification.json'
    qualification_ref = _identity(qualification_root, 'qualification.json')
    qualification = _read_linked(qualification_root, qualification_ref)
    if (qualification.get('schema') != 'fdisbull-ci-qualification-1'
            or qualification.get('status') != 'qualified'
            or qualification.get('source_commit') != request['source_sha']):
        raise ValueError('exact-source final qualification missing')
    package_ref = qualification.get('package_inventory')
    package = _read_linked(qualification_root, package_ref)
    if (package.get('schema') != 'fdisbull-package-payloads-1'
            or package.get('source_commit') != request['source_sha']
            or package.get('tracked_worktree_dirty') is not False
            or not isinstance(package.get('artifacts'), dict)
            or set(package['artifacts']) != {'core', 'player', 'sdist', 'tool'}):
        raise ValueError('exact-source package inventory invalid')
    assets = []
    for kind in ('core', 'player', 'sdist', 'tool'):
        item = package['artifacts'][kind]
        if (not isinstance(item, dict) or not isinstance(item.get('name'), str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', item['name'])
                or not HEX.fullmatch(str(item.get('sha256')))
                or type(item.get('size_bytes')) is not int or item['size_bytes'] <= 0):
            raise ValueError('package artifact identity invalid')
        identity = _identity(qualification_root, 'dist/' + item['name'])
        if (identity['sha256'], identity['size']) != (item['sha256'], item['size_bytes']):
            raise ValueError('package bytes differ from package inventory')
        assets.append({'name': item['name'], 'path': str(qualification_root / identity['path']),
                       'size': identity['size'], 'sha256': identity['sha256']})
    chat = qualification.get('chat_consumer')
    if not isinstance(chat, dict):
        raise ValueError('offline chat consumer evidence missing')
    receipt = _read_linked(qualification_root, chat.get('receipt'))
    verifier_ref = chat.get('verifier')
    verifier = _read_linked(qualification_root, verifier_ref)
    if (verifier.get('schema') != 'fdisbull-chat-consumer-verification-v1'
            or verifier.get('status') != 'passed' or verifier.get('source_commit') != request['source_sha']
            or verifier.get('test_source_commit') != request['source_sha']
            or verifier.get('network_interfaces') != ['lo']
            or verifier.get('skipped') != 0 or verifier.get('native_failures') != 0):
        raise ValueError('network-disabled consumer did not pass without skips')
    windows = verifier.get('windows_native_qualification', {})
    extended = verifier.get('extended_windows', {})
    if (windows.get('pe32') != 'passed' or windows.get('win16') != 'passed'
            or any((extended.get(k) or {}).get('status') != 'passed' for k in ('pe32', 'win16'))):
        raise ValueError('consumer PE32 or Win16 evidence missing')
    if (receipt.get('schema')!='fdisbull-chat-consumer-job-v1' or receipt.get('status')!='passed'
            or receipt.get('source_commit')!=request['source_sha']
            or receipt.get('test_source_commit')!=request['source_sha']
            or receipt.get('source_access')!='absent'):
        raise ValueError('consumer receipt identity or isolation differs')
    import xml.etree.ElementTree as ET
    junit_ref=receipt.get('junit')
    if not isinstance(junit_ref,dict):raise ValueError('consumer JUnit missing')
    junit_path=qualification_root/junit_ref['path']
    if _identity(qualification_root,junit_ref['path'])!=junit_ref:
        raise ValueError('consumer JUnit identity differs')
    junit=ET.parse(junit_path).getroot()
    if (not junit.findall('.//testcase') or any(junit.findall('.//'+tag) for tag in ('failure','error','skipped'))):
        raise ValueError('consumer JUnit did not pass')
    archive_ref = chat.get('archive')
    if not isinstance(archive_ref,dict) or verifier.get('archive_sha256')!=archive_ref.get('sha256'):
        raise ValueError('consumer verifier archive differs')
    archive = _identity(qualification_root, archive_ref['path'])
    if ((archive['sha256'], archive['size']) != (archive_ref.get('sha256'), archive_ref.get('size'))
            or receipt.get('archive') != archive_ref or receipt.get('verifier') != verifier_ref):
        raise ValueError('consumer archive and linked receipts disagree')
    assets.append({'name': Path(archive['path']).name,
                   'path': str(qualification_root / archive['path']), 'size': archive['size'],
                   'sha256': archive['sha256']})
    if len({asset['name'] for asset in assets}) != 5:
        raise ValueError('release asset names are not unique')
    checksum_path = output_root / 'SHA256SUMS'
    checksum_data = ''.join(f"{item['sha256']}  {item['name']}\n" for item in assets).encode()
    _write_bytes_once(checksum_path, checksum_data)
    checksum_id = {'sha256': hashlib.sha256(checksum_data).hexdigest(), 'size': len(checksum_data)}
    assets.append({'name': 'SHA256SUMS', 'path': str(checksum_path), **checksum_id})
    notes = (f'fDisBull {VERSION}\n\nSource commit: {request["source_sha"]}\n\n'
             f'Qualification: {qualification_ref["sha256"]}\n')
    manifest = {'schema': 'fdisbull-release-inputs-1', 'repository': REPOSITORY,
                'repository_id': REPOSITORY_ID, 'source_sha': request['source_sha'],
                'version': VERSION, 'tag': TAG,
                'qualification': {'root': str(qualification_root), 'path': 'qualification.json',
                                  'sha256': qualification_ref['sha256']},
                'assets': assets, 'notes': notes}
    manifest_path = output_root / 'RELEASE-INPUTS.json'
    _write_once(manifest_path, manifest)
    return manifest_path, _digest(manifest_path), manifest


def _valid_publisher_result(value, request):
    if (not isinstance(value, dict) or value.get('status') != 'completed'
            or value.get('source_sha') != request['source_sha'] or value.get('tag') != TAG
            or not isinstance(value.get('release_url'), str)):
        return False
    return value['release_url'] == f'https://github.com/{REPOSITORY}/releases/tag/{TAG}'


def _write_result(path, request, status, *, release_url=None, reason=None, cleanup=None):
    value = {'schema': 'fdisbull-production-release-result-1',
             'request_sha256': request['_request_sha256'], 'status': status,
             'source_sha': request['source_sha'], 'tag': TAG,
             'release_url': release_url if status == 'complete' else None,
             'reason': reason, 'cleanup': cleanup,
             'owned_cleanup_verified': isinstance(cleanup,dict) and cleanup.get('running_after')==0,
             'source_root': request['source_root'], 'output_root': request['output_root'],
             'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _write_once(path, value)
    return value


def run(request, state_root, *, guard, health, publisher, clock=time.time, sleeper=time.sleep):
    """Execute one intent under the caller's existing lease; never replay intent."""
    if not isinstance(request, dict) or not HEX.fullmatch(str(request.get('_request_sha256', ''))):
        raise ValueError('validated request required')
    state_root = Path(state_root)
    expected_state = STATE_ROOT / 'pipelines' / request['_request_sha256']
    if state_root != expected_state:
        raise ValueError('pipeline state root does not match request identity')
    _private_dir(state_root)
    request_path = Path(request['_request_path'])
    request = inspect_request({'path': str(request_path), 'sha256': request['_request_sha256']})
    result_path = state_root / 'result.json'
    intent_path = state_root / 'intent.json'
    if result_path.exists() or result_path.is_symlink():
        result = _json_file(result_path)
        if (result.get('schema') != 'fdisbull-production-release-result-1'
                or result.get('request_sha256') != request['_request_sha256']
                or result.get('source_sha') != request['source_sha'] or result.get('tag') != TAG
                or result.get('status') not in ('complete', 'attention')):
            raise ValueError('existing pipeline result binding mismatch')
        return result
    if intent_path.exists() or intent_path.is_symlink():
        return _write_result(result_path, request, 'attention', reason='unknown-existing-intent')
    _write_once(intent_path, {'schema': 'fdisbull-production-release-intent-1',
                              'request_sha256': request['_request_sha256'], 'key': request['key'],
                              'source_sha': request['source_sha'], 'tag': TAG, 'created_at': clock()})
    deadline = time.monotonic() + request['deadline_seconds']
    output_root = Path(request['output_root'])
    run_id = None
    cleanup = {'checked':0,'stopped':0,'running_after':0,'scope':'before-driver'}
    try:
        guard()
        status = health()
        if not isinstance(status, dict) or status.get('state') != 'healthy':
            raise RuntimeError('host health unavailable')
        _save_progress(state_root / 'last-progress.json', phase='source-clone-starting', request=request)
        source = _source_checkout(request, deadline, guard=guard, health=health, state_root=state_root)
        guard()
        output_root.mkdir(mode=0o700,parents=False, exist_ok=False)
        receipt_path = state_root / 'local-docker-host.json'
        _host_receipt(receipt_path)
        argv = _driver_argv(source, output_root, receipt_path, request['driver_options'])
        _save_progress(state_root / 'last-progress.json', phase='driver-starting', request=request)
        cleanup = None
        run_id = _drive(argv, output=output_root, request=request, state_root=state_root,
                        guard=guard, health=health, deadline=deadline, sleeper=sleeper)
        run_id = run_id or _read_run_id(output_root, request['source_sha'])
        if run_id is None:
            raise ValueError('driver run receipt missing')
        cleanup_deadline = max(deadline, time.monotonic() + 120)
        cleanup = _stop_owned(run_id, request['source_sha'], deadline=cleanup_deadline, guard=guard)
        guard()
        if time.monotonic() >= deadline:
            raise TimeoutError('pipeline deadline expired before publication')
        manifest_path, manifest_sha, _ = _release_manifest(request, output_root)
        _save_progress(state_root / 'last-progress.json', phase='publishing', request=request, run_id=run_id)
        published = publisher(request['key'], {'manifest_path': str(manifest_path),
                                                'manifest_sha256': manifest_sha})
        if not _valid_publisher_result(published, request):
            return _write_result(result_path, request, 'attention', reason='release-publication-unverified',
                                 cleanup=cleanup)
        return _write_result(result_path, request, 'complete', release_url=published['release_url'],
                             cleanup=cleanup)
    except BaseException as error:
        try:
            run_id = run_id or _read_run_id(output_root, request['source_sha'])
            cleanup_deadline = max(deadline, time.monotonic() + 120)
            cleanup = (_stop_owned(run_id, request['source_sha'], deadline=cleanup_deadline,
                                   guard=guard) if run_id else cleanup)
        except BaseException:
            cleanup = {'status': 'unknown'}
        try:
            return _write_result(result_path, request, 'attention', reason=type(error).__name__, cleanup=cleanup)
        except FileExistsError:
            return _json_file(result_path)


def enqueue(source_sha):
    """Queue a frozen integration for the existing n8n timer; start no worker."""
    import importlib.util
    if (os.geteuid()!=0 or not SHA.fullmatch(str(source_sha))
            or Path(__file__).resolve()!=Path('/usr/local/libexec/fdisbull-ci-production/production_pipeline.py')):
        raise ValueError('installed root queue endpoint required')
    entry_path=Path('/usr/local/libexec/fdisbull-ci-production.py')
    spec=importlib.util.spec_from_file_location('pipeline_queue_entry',entry_path)
    entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    old=entry.installation_config()
    import production_control as control
    with control.executor_lease(old['executor_lock']):
        current=entry.installation_config()
        if current!=old:raise ValueError('queue configuration changed')
        if (STATE_ROOT/'blocked.json').exists():raise ValueError('unresolved controller attention')
        template=_json_file(REQUEST_ROOT/'release-0.35.0-template.json')
        if set(template)!={'driver_options','deadline_seconds','publish','version','tag'}:
            raise ValueError('queue template fields differ')
        key='release-0.35.0-'+source_sha
        request={'schema':'fdisbull-production-release-request-1','key':key,'source_sha':source_sha,
                 'source_root':str(SOURCE_ROOT/source_sha),'output_root':str(OUTPUT_ROOT/key),**template}
        SOURCE_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        OUTPUT_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=REQUEST_ROOT/(key+'.json')
        data=(json.dumps(request,sort_keys=True,indent=2)+'\n').encode()
        if path.exists():
            if path.is_symlink() or path.read_bytes()!=data:raise ValueError('queued source request differs')
        else:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o400)
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        pointer={'path':str(path),'sha256':hashlib.sha256(data).hexdigest()}
        inspect_request(pointer)
        previous=current.get('pipeline_request')
        if previous is not None and previous!=pointer:
            raise ValueError('another release request is configured; preserve and reconcile it first')
        if previous!=pointer:
            current['pipeline_request']=pointer
            pending=entry.CONFIG.with_name(entry.CONFIG.name+'.queue-'+source_sha)
            _write_once(pending,current);os.replace(pending,entry.CONFIG)
            fd=os.open(entry.CONFIG.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            if entry.installation_config()!=current:raise ValueError('queued configuration readback differs')
        return {'status':'queued','source_sha':source_sha,'request':pointer,'worker_started_here':False}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Enqueue an approved frozen primary source for n8n.')
    parser.add_argument('--enqueue',required=True,metavar='FULL_SOURCE_SHA')
    args=parser.parse_args()
    print(json.dumps(enqueue(args.enqueue),sort_keys=True))
