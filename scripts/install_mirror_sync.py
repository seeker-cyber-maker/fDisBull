#!/usr/bin/env python3
"""Preview or install the local, user-owned fDisBull mirror wake service.

This command never starts launchd, initializes a cache, or contacts a remote.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

LABEL = 'org.fdisbull.mirror-sync'
FORMAT = 'fdisbull-mirror-sync-1'
MANIFEST = 'fdisbull-mirror-install-1'
DEFAULT_HUB = '/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git'
DEFAULT_CACHE = '/Volumes/CODEX/Codex_Projects/active/fDisBull-mirror-sync/transport.git'
DEFAULT_GITLAB = 'https://gitlab.com/brewster-jennings-group/fdisbull.git'
DEFAULT_STORAGE_ADMISSION_SCRIPT = '/Users/tiga/.codex/bin/storage_admit.py'
DEFAULT_STORAGE_EXPECTED_BYTES = 1_000_000_000
DEFAULT_STORAGE_RESERVE_BYTES = 40_000_000_000
MIN_STORAGE_RESERVE_BYTES = 40_000_000_000
DEFAULT_VOLUMES = [('/Volumes/CODEX', '5DB767EC-4FB1-4B21-82B2-80B994B827E8'),
                   ('/Volumes/GitHub', '340727DA-0AC5-46F5-AD9B-29DB8CADD25A')]


def absolute(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('Paths must be absolute: ' + str(value))
    return Path(os.path.abspath(path))


def reject_symlinks(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError('Managed path contains a symlink: ' + str(current))


def parse_volume(text):
    path, sep, uuid = text.rpartition('=')
    if not sep or not uuid.strip():
        raise ValueError('Volume must have PATH=UUID form')
    return {'path': str(absolute(path)), 'uuid': uuid.strip().upper()}


def verify_volumes(volumes, diskutil):
    for volume in volumes:
        path = volume['path']
        if not os.path.ismount(path):
            raise ValueError('Expected volume is not mounted: ' + path)
        try:
            raw = subprocess.run([str(diskutil), 'info', '-plist', path], check=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout
            info = plistlib.loads(raw)
        except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException) as error:
            raise ValueError('Cannot inspect expected volume: ' + path) from error
        if (not isinstance(info, dict) or info.get('MountPoint') != path
                or str(info.get('VolumeUUID', '')).upper() != volume['uuid']):
            raise ValueError('Mounted volume identity differs: ' + path)


def _inside(path, volumes):
    return any(path == Path(v['path']) or Path(v['path']) in path.parents for v in volumes)


def git_call(git, hub, *args, optional=False):
    result = subprocess.run([str(git), '--git-dir=' + str(hub), 'config', '--local', *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    if result.returncode and not (optional and result.returncode in (1, 5)):
        raise ValueError('Cannot inspect or update local hub Git configuration')
    return result.stdout.decode('utf-8').split('\0')[:-1] if '-z' in args else result.stdout.decode('utf-8').splitlines()


def local_values(git, hub, key):
    return git_call(git, hub, '-z', '--get-all', key, optional=True)


def effective_values(git, hub, key):
    result = subprocess.run([str(git), '--git-dir=' + str(hub), 'config', '-z', '--get-all', key],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    if result.returncode not in (0, 1):
        raise ValueError('Cannot inspect effective hub Git configuration')
    return result.stdout.decode('utf-8').split('\0')[:-1]


def set_values(git, hub, key, values):
    git_call(git, hub, '--unset-all', key, optional=True)
    for value in values:
        git_call(git, hub, '--add', key, value)


def bytes_hash(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.fdisbull-mirror-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def install_lock(state):
    """Exclude the worker and other installers before changing managed files."""
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / 'run.lock'
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Invalid existing state control file: ' + str(path))
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Mirror worker or installer is busy') from error
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def hook_contents(wake):
    return ('#!/bin/sh\n# Managed by fDisBull mirror sync.\n'
            '/bin/cat >/dev/null\n'
            '/usr/bin/touch ' + shlex.quote(str(wake)) + ' 2>/dev/null || :\n'
            'exit 0\n').encode()


def plist_contents(python, worker, config, state, wake):
    return plistlib.dumps(dict(Label=LABEL, ProgramArguments=[str(python), str(worker), '--config', str(config)],
        WorkingDirectory=str(state), StartInterval=60, WatchPaths=[str(wake)], RunAtLoad=True,
        StandardOutPath='/dev/null', StandardErrorPath='/dev/null'), sort_keys=True)


def _read_manifest(path):
    if path.is_symlink():
        raise ValueError('Installation manifest must not be a symlink')
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('format') != MANIFEST
            or data.get('phase') not in ('installing', 'installed', 'disabled')
            or type(data.get('installed')) is not bool
            or data['installed'] != (data['phase'] == 'installed')
            or not isinstance(data.get('original_deny_current_branch'), list)
            or len(data['original_deny_current_branch']) > 1
            or any(not isinstance(value, str) for value in data['original_deny_current_branch'])
            or type(data.get('hook_preexisting')) is not bool
            or type(data.get('plist_preexisting')) is not bool):
        raise ValueError('Unrecognized existing mirror installation manifest')
    return data


def _path_matches(path, data):
    return path.is_file() and not path.is_symlink() and path.read_bytes() == data


def build_plan(args):
    hub, cache, state, plist = map(absolute, (args.hub, args.cache, args.state_dir, args.plist))
    git = absolute(args.git or shutil.which('git') or '')
    python = absolute(args.python)
    worker_source = absolute(args.worker_source)
    checker_source = absolute(args.storage_checker_source)
    admission_script = absolute(args.storage_admission_script)
    diskutil = absolute(args.diskutil)
    if (type(args.storage_expected_bytes) is not int or args.storage_expected_bytes <= 0
            or type(args.storage_reserve_bytes) is not int
            or args.storage_reserve_bytes < MIN_STORAGE_RESERVE_BYTES):
        raise ValueError('Storage estimate must be positive and reserve must be at least 40 GB')
    if not admission_script.is_file():
        raise ValueError('Storage admission script is not available: ' + str(admission_script))
    volumes = [parse_volume(value) for value in args.volume] if args.volume else [
        {'path': path, 'uuid': uuid} for path, uuid in DEFAULT_VOLUMES]
    if len({v['path'] for v in volumes}) != len(volumes):
        raise ValueError('Duplicate declared volume root')
    verify_volumes(volumes, diskutil)
    for path in (hub, cache, state, plist):
        reject_symlinks(path)
    if not _inside(hub, volumes) or not _inside(cache, volumes):
        raise ValueError('Hub and cache must be on declared mounted volumes')
    if not hub.is_dir() or not (hub / 'config').is_file():
        raise ValueError('The local hub must already exist')
    if not git.is_file() or not os.access(git, os.X_OK) or not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('Git and Python must be absolute executable files')
    probe = subprocess.run([str(git), '--git-dir=' + str(hub), 'rev-parse', '--is-bare-repository'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    if probe.returncode or probe.stdout.strip() != b'true':
        raise ValueError('The local hub must be a bare Git repository')
    hooks_config = effective_values(git, hub, 'core.hooksPath')
    if len(hooks_config) > 1:
        raise ValueError('Multiple core.hooksPath values require manual review')
    hook_dir = (hub / 'hooks') if not hooks_config else Path(hooks_config[0]).expanduser()
    if not hook_dir.is_absolute():
        hook_dir = hub / hook_dir
    hook_dir = absolute(str(hook_dir))
    hook = hook_dir / 'post-receive'
    reject_symlinks(hook)
    wake, runtime, checker, config, manifest = (state / 'wake',
        state / 'runtime' / 'mirror_sync_service.py', state / 'runtime' / 'mirror_storage_admit.py',
        state / 'config.json', state / 'install-manifest.json')
    managed_hook = hook_contents(wake)
    if hooks_config and not _path_matches(hook, managed_hook):
        raise ValueError('Existing core.hooksPath is not an identical managed hook')
    if hook.is_symlink() or (hook.exists() and not _path_matches(hook, managed_hook)):
        raise ValueError('Existing post-receive hook is not an identical managed hook')
    payload = dict(format=FORMAT, git=str(git), hub=str(hub), gitlab=args.gitlab, cache=str(cache),
                   state_dir=str(state), volumes=volumes, command_timeout_s=45, run_timeout_s=55,
                   storage=dict(python=str(python), checker=str(checker),
                       admission_script=str(admission_script),
                       expected_bytes=args.storage_expected_bytes,
                       reserve_bytes=args.storage_reserve_bytes))
    remote = urlsplit(args.gitlab)
    if remote.hostname and (remote.hostname.lower() == 'github.com'
                            or remote.hostname.lower().endswith('.github.com')):
        raise ValueError('GitHub mirror is inactive')
    if (remote.scheme not in ('https', 'ssh', 'git') or not remote.netloc
            or remote.username is not None or remote.password is not None
            or remote.query or remote.fragment or any(c in args.gitlab for c in ('\n', '\r', '\0'))):
        raise ValueError('GitLab remote must be a credential-free supported URL')
    plist_data = plist_contents(python, runtime, config, state, wake)
    previous = _read_manifest(manifest)
    if previous is not None and any(previous.get(k) != v for k, v in
            {'hub':str(hub),'hook':str(hook),'plist':str(plist),'state_dir':str(state)}.items()):
        raise ValueError('Existing installation manifest identifies a different target')
    if plist.is_symlink() or (plist.exists() and not _path_matches(plist, plist_data)):
        raise ValueError('Existing LaunchAgent plist is not the managed configuration')
    if not worker_source.is_file():
        raise ValueError('Mirror worker source is not available: ' + str(worker_source))
    if not checker_source.is_file():
        raise ValueError('Mirror storage checker source is not available: ' + str(checker_source))
    for path in (state, state / 'runtime', plist.parent, hook_dir):
        if path.is_symlink():
            raise ValueError('Managed directories must not be symlinks')
    current = local_values(git, hub, 'receive.denyCurrentBranch')
    phase = previous.get('phase', 'installed' if previous.get('installed') else 'disabled') if previous else None
    original = previous.get('original_deny_current_branch') if previous else None
    if phase == 'installed' and current != ['refuse']:
        raise ValueError('Managed receive setting changed since installation')
    if phase == 'installing' and current not in (original, ['refuse']):
        raise ValueError('Receive setting changed during interrupted installation')
    if len(current) > 1:
        raise ValueError('Multiple receive.denyCurrentBranch values require manual review')
    if phase == 'disabled' and current != original:
        raise ValueError('Receive setting changed after disable; review before reinstalling')
    config_data = (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode()
    worker_data = worker_source.read_bytes()
    checker_data = checker_source.read_bytes()
    for path, data, field in ((runtime, worker_data, 'runtime_sha256'),
                              (checker, checker_data, 'storage_checker_sha256'),
                              (config, config_data, 'config_sha256')):
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise ValueError('Existing managed file is not a regular file: ' + str(path))
            known = previous and previous.get(field) == bytes_hash(path.read_bytes())
            if not known and path.read_bytes() != data:
                raise ValueError('Existing runtime or configuration is not managed: ' + str(path))
    for path in (state / 'wake', state / 'run.lock'):
        if path.exists() and (not path.is_file() or path.is_symlink()):
            raise ValueError('Invalid existing state control file: ' + str(path))
    manifest_value = previous or dict(format=MANIFEST, hub=str(hub), hook=str(hook), plist=str(plist),
        state_dir=str(state), original_deny_current_branch=current,
        hook_sha256=bytes_hash(managed_hook), plist_sha256=bytes_hash(plist_data),
        hook_preexisting=hook.exists(), plist_preexisting=plist.exists(), installed=False, phase='disabled')
    if previous is not None and (previous.get('hook_sha256') != bytes_hash(managed_hook)
            or previous.get('plist_sha256') != bytes_hash(plist_data)):
        raise ValueError('Managed hook or plist differs from installation manifest')
    return dict(hub=hub, cache=cache, state=state, plist=plist, git=git, python=python,
                worker_source=worker_source, checker_source=checker_source,
                hook=hook, wake=wake, runtime=runtime, checker=checker, config=config,
                manifest=manifest, manifest_value=manifest_value, payload=payload,
                manifest_before=manifest.read_bytes() if manifest.exists() else None,
                hook_data=managed_hook, plist_data=plist_data, worker_data=worker_data,
                checker_data=checker_data,
                config_data=config_data, current=current)


def _require_current_manifest(plan):
    current = plan['manifest'].read_bytes() if plan['manifest'].exists() else None
    if current != plan['manifest_before']:
        raise ValueError('Installation manifest changed after preview; inspect and retry')


def apply(plan):
    with install_lock(plan['state']):
        _require_current_manifest(plan)
        _apply_locked(plan)


def _apply_locked(plan):
    state = plan['state']
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    manifest = dict(plan['manifest_value'], installed=False, phase='installing',
                    runtime_sha256=bytes_hash(plan['worker_data']),
                    storage_checker_sha256=bytes_hash(plan['checker_data']),
                    config_sha256=bytes_hash(plan['config_data']))
    # Persist recovery information before any change to the bare hub.
    atomic_write(plan['manifest'], (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
    atomic_write(plan['runtime'], plan['worker_data'], 0o700)
    atomic_write(plan['checker'], plan['checker_data'], 0o700)
    atomic_write(plan['config'], plan['config_data'])
    for name in ('wake', 'run.lock'):
        path = state / name
        if path.exists() and (not path.is_file() or path.is_symlink()):
            raise ValueError('Invalid existing state control file: ' + str(path))
        path.touch(mode=0o600, exist_ok=True)
    atomic_write(plan['plist'], plan['plist_data'], 0o600)
    atomic_write(plan['hook'], plan['hook_data'], 0o755)
    set_values(plan['git'], plan['hub'], 'receive.denyCurrentBranch', ['refuse'])
    atomic_write(plan['manifest'], (json.dumps(dict(manifest, installed=True, phase='installed'),
        indent=2, sort_keys=True) + '\n').encode())


def disable(plan):
    with install_lock(plan['state']):
        _require_current_manifest(plan)
        _disable_locked(plan)


def _disable_locked(plan):
    manifest = plan['manifest_value']
    phase = manifest.get('phase', 'installed' if manifest.get('installed') else 'disabled')
    if phase not in ('installed', 'installing'):
        raise ValueError('No active managed installation to disable')
    for path, data in ((plan['hook'], plan['hook_data']), (plan['plist'], plan['plist_data'])):
        if path.is_symlink() or (path.exists() and not _path_matches(path, data)):
            raise ValueError('Managed file changed; refusing to remove: ' + str(path))
    current = local_values(plan['git'], plan['hub'], 'receive.denyCurrentBranch')
    original = manifest['original_deny_current_branch']
    if current == ['refuse']:
        set_values(plan['git'], plan['hub'], 'receive.denyCurrentBranch', original)
    elif phase != 'installing' or current != original:
        raise ValueError('Managed receive setting changed; refusing to restore')
    for path, preexisting in ((plan['hook'], manifest.get('hook_preexisting')),
                              (plan['plist'], manifest.get('plist_preexisting'))):
        if path.exists() and not preexisting: path.unlink()
    atomic_write(plan['manifest'], (json.dumps(dict(manifest, installed=False, phase='disabled'),
        indent=2, sort_keys=True) + '\n').encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--disable', action='store_true')
    parser.add_argument('--hub', default=DEFAULT_HUB)
    parser.add_argument('--cache', default=DEFAULT_CACHE)
    parser.add_argument('--gitlab', default=DEFAULT_GITLAB)
    parser.add_argument('--state-dir', default=str(Path.home() / '.local/state/fdisbull-mirror'))
    parser.add_argument('--plist', default=str(Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')))
    parser.add_argument('--git', default=shutil.which('git'))
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--worker-source', default=str(Path(__file__).resolve().with_name('mirror_sync_service.py')))
    parser.add_argument('--storage-checker-source', default=str(Path(__file__).resolve().with_name('mirror_storage_admit.py')))
    parser.add_argument('--storage-admission-script', default=DEFAULT_STORAGE_ADMISSION_SCRIPT)
    parser.add_argument('--storage-expected-bytes', type=int, default=DEFAULT_STORAGE_EXPECTED_BYTES)
    parser.add_argument('--storage-reserve-bytes', type=int, default=DEFAULT_STORAGE_RESERVE_BYTES)
    parser.add_argument('--diskutil', default='/usr/sbin/diskutil')
    parser.add_argument('--volume', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args)
        if args.apply: apply(plan)
        elif args.disable: disable(plan)
        print(json.dumps(dict(action='apply' if args.apply else 'disable' if args.disable else 'preview',
            config=plan['payload'], hook=str(plan['hook']), plist=str(plan['plist']),
            runtime=str(plan['runtime']), manifest=str(plan['manifest']),
            deny_current_branch_before=plan['current'], launches_service=False), indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('mirror installer: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
