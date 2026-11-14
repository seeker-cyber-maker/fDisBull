#!/usr/bin/env python3
"""Validate and optionally stage the fixed fDisBull production control install.

This is a first-install initializer, not a migration or repair tool. The normal
operation is a read-only plan. Applying requires an explicit role and flag.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('install_manifest', HERE / 'production_manifest.py')
_manifest_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_manifest_module)
MODULES = frozenset(_manifest_module.MODULES)

BUNDLE_SCHEMA = 'fdisbull-production-control-bundle-1'
CONTROL_REF = 'codex/production-ci-recovery-20261113'
UNIT_NAME = 'fdisbull-ci-production.service'
POLICY_NAME = 'qualification-policy.json'
UNIT_SOURCE = HERE / UNIT_NAME
POLICY_SHA256 = '36b34e8b17309855408e4d0556bf047be3135ceb455359c806a45967c2a3ffeb'
INSTALLATION_ID = 'fdisbull-production-ci-20261113-01'
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024

# Fixed deployment identities. The bundle path is the only caller-selected path.
CODEX_ROOT = Path('/Volumes/CODEX')
CODEX_UUID = '5DB767EC-4FB1-4B21-82B2-80B994B827E8'
MAC_CODE = Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge')
MAC_PROVIDER_STATE = Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state')
MAC_SOURCE_STATE = Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-source-state')
MAC_ANCHOR = Path('/Users/tiga/.local/state/fdisbull-ci-production/bridge-anchor.json')
MAC_STATUS_STATE = Path('/Volumes/CODEX/Codex_Projects/fDisBull/.git/fdisbull-ci-status')
MAC_SOURCE_PYTHON = {'path': '/Users/tiga/miniconda/bin/python3', 'version': '3.13.13',
                     'sha256': '0f5374bca527c5a5e958ee94e03e55816a368533286e6315b8bf013da622fc61'}
ACTIVATION_MODULES = ('production_source_transport.py', 'production_source_publish.py',
                      'recovery_production.py', 'recovery_source_production.py',
                      'recovery_source.py', 'production_transport.py', 'ci_status.py')

VPS_ENTRY = Path('/usr/local/libexec/fdisbull-ci-production.py')
VPS_MODULES = Path('/usr/local/libexec/fdisbull-ci-production')
VPS_CONFIG = Path('/etc/fdisbull-ci-production/config.json')
VPS_UNIT = Path('/etc/systemd/system/fdisbull-ci-production.service')
VPS_CONTROL = Path('/var/lib/fdisbull-ci/control/production')
VPS_POLICY = VPS_CONTROL / 'qualification-policy.canonical.json'
VPS_JOB_INPUTS = VPS_CONTROL / 'job-inputs'
VPS_ACTIVE_POLICY = VPS_JOB_INPUTS / POLICY_NAME
VPS_STATE = Path('/var/lib/fdisbull-ci/control/recovery/production')
VPS_EXPORTS = Path('/var/lib/fdisbull-ci/results')
VPS_EXECUTOR_LOCK = Path('/var/lib/fdisbull-ci/control/ci-executor.lock')
VPS_BRIDGE = MAC_CODE / 'production_transport.py'
VPS_INSTALLATION_ID = INSTALLATION_ID
VPS_GITHUB = {'repository': 'seeker-cyber-maker/fDisBull', 'workflow_id': '417757453',
              'runner_id': '21', 'actor': 'seeker-cyber-maker', 'ref': CONTROL_REF,
              'profile': 'ordinary', 'sole_executor_authority': True,
              'export_root': str(VPS_EXPORTS)}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_regular(path, maximum):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('bundle contains a symlink')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > maximum:
            raise ValueError('bundle entry is not a bounded single-link regular file')
        chunks, remaining = [], maximum + 1
        while remaining:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b''.join(chunks)
        if len(data) > maximum:
            raise ValueError('bundle entry exceeds size limit')
        return data
    finally:
        os.close(fd)


def validate_bundle(bundle):
    """Return validated bytes and manifest; never imports or executes bundle code."""
    root = Path(bundle)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('absolute bundle directory required')
    if any(parent.is_symlink() for parent in root.parents):
        raise ValueError('bundle path contains a symlink')
    manifest_bytes = _read_regular(root / 'manifest.json', MAX_MANIFEST_BYTES)
    manifest = json.loads(manifest_bytes)
    expected_fields = {'schema', 'control_sha', 'control_ref', 'module_sha256',
                       'entrypoint_sha256', 'unit_sha256', 'policy_sha256'}
    if type(manifest) is not dict or set(manifest) != expected_fields:
        raise ValueError('bundle manifest fields mismatch')
    if (manifest['schema'] != BUNDLE_SCHEMA
            or not isinstance(manifest['control_sha'], str)
            or not re.fullmatch(r'[0-9a-f]{40}', manifest['control_sha'])
            or manifest['control_ref'] != CONTROL_REF):
        raise ValueError('bundle source identity mismatch')
    hashes = manifest['module_sha256']
    if (type(hashes) is not dict or set(hashes) != MODULES
            or any(not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v)
                   for v in hashes.values())):
        raise ValueError('bundle module allowlist mismatch')
    for field in ('entrypoint_sha256', 'unit_sha256', 'policy_sha256'):
        if not isinstance(manifest[field], str) or not re.fullmatch(r'[0-9a-f]{64}', manifest[field]):
            raise ValueError('bundle digest malformed')
    if (manifest['entrypoint_sha256'] != hashes.get('production-ci.py')
            or manifest['policy_sha256'] != POLICY_SHA256):
        raise ValueError('bundle entrypoint or policy pin mismatch')
    allowed = {'manifest.json', UNIT_NAME, POLICY_NAME, *MODULES}
    actual = set()
    for entry in root.iterdir():
        if entry.is_symlink() or not (entry.is_file() and entry.name in allowed):
            raise ValueError('bundle has an unexpected entry')
        actual.add(entry.name)
    if actual != allowed:
        raise ValueError('bundle file set is incomplete')
    files = {}
    for name, digest in hashes.items():
        data = _read_regular(root / name, MAX_FILE_BYTES)
        if _sha(data) != digest:
            raise ValueError('bundle module digest mismatch')
        files[name] = data
    unit = _read_regular(root / UNIT_NAME, MAX_FILE_BYTES)
    policy = _read_regular(root / POLICY_NAME, MAX_FILE_BYTES)
    if _sha(unit) != manifest['unit_sha256'] or _sha(policy) != POLICY_SHA256:
        raise ValueError('bundle unit or policy digest mismatch')
    if b'ExecStart=/usr/bin/python3 /usr/local/libexec/fdisbull-ci-production.py run' not in unit:
        raise ValueError('unit target differs from fixed native entrypoint')
    return {'manifest': manifest, 'modules': files, 'unit': unit, 'policy': policy,
            'manifest_sha256': _sha(manifest_bytes)}


def _externally_pinned(checked, expected_control_sha, expected_manifest_sha256):
    if (not isinstance(expected_control_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', expected_control_sha)
            or checked['manifest']['control_sha'] != expected_control_sha):
        raise ValueError('explicit source commit pin mismatch')
    if (not isinstance(expected_manifest_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_manifest_sha256)
            or checked['manifest_sha256'] != expected_manifest_sha256):
        raise ValueError('explicit bundle manifest pin mismatch')
    return checked


def plan(role, bundle, *, expected_control_sha, expected_manifest_sha256,
         enable_source_review_approved=False, install_active_policy_input=False):
    checked = validate_bundle(bundle)
    _externally_pinned(checked, expected_control_sha, expected_manifest_sha256)
    if role not in ('mac', 'vps'):
        raise ValueError('fixed role must be mac or vps')
    if role == 'mac' and install_active_policy_input:
        raise ValueError('active policy input is a VPS-only option')
    if role == 'vps' and enable_source_review_approved:
        raise ValueError('source activation is a Mac-only option')
    manifest = checked['manifest']
    files = []
    if role == 'mac':
        files.extend({'path': str(MAC_CODE / name), 'mode': '0600', 'sha256': digest}
                     for name, digest in sorted(manifest['module_sha256'].items()))
        files += [
            {'path': str(MAC_PROVIDER_STATE / 'installation.json'), 'mode': '0600', 'kind': 'genesis-marker'},
            {'path': str(MAC_PROVIDER_STATE / 'actions.lock'), 'mode': '0600', 'kind': 'empty-lock'},
            {'path': str(MAC_ANCHOR), 'mode': '0600', 'kind': 'empty-genesis-anchor'},
            {'path': str(MAC_SOURCE_STATE), 'mode': '0700', 'kind': 'empty-private-directory'},
        ]
        if enable_source_review_approved:
            files.append({'path': str(MAC_CODE / 'source-activation.json'), 'mode': '0600',
                          'kind': 'explicitly-approved-activation',
                          'module_sha256': {name: manifest['module_sha256'][name] for name in ACTIVATION_MODULES}})
        return {'schema': 'fdisbull-production-install-plan-1', 'role': role,
                'control_sha': manifest['control_sha'], 'bundle_manifest_sha256': checked['manifest_sha256'],
                'source_activation': bool(enable_source_review_approved), 'files': files}
    files.extend({'path': str(VPS_MODULES / name), 'mode': '0644', 'sha256': digest}
                 for name, digest in sorted(manifest['module_sha256'].items()))
    files += [
        {'path': str(VPS_ENTRY), 'mode': '0755', 'sha256': manifest['entrypoint_sha256']},
        {'path': str(VPS_CONFIG), 'mode': '0600', 'kind': 'disabled-config'},
        {'path': str(VPS_UNIT), 'mode': '0644', 'sha256': manifest['unit_sha256']},
        {'path': str(VPS_POLICY), 'mode': '0400', 'sha256': manifest['policy_sha256']},
        {'path': str(VPS_JOB_INPUTS), 'mode': '0700', 'kind': 'private-job-inputs'},
        {'path': str(VPS_STATE / 'installation.json'), 'mode': '0600', 'kind': 'genesis-marker'},
        {'path': str(VPS_STATE / 'failure-inbox.sqlite'), 'mode': '0600', 'kind': 'empty-durable-inbox'},
    ]
    if install_active_policy_input:
        files.append({'path': str(VPS_ACTIVE_POLICY), 'mode': '0644',
                      'kind': 'explicitly-installed-qualification-input', 'sha256': manifest['policy_sha256']})
    return {'schema': 'fdisbull-production-install-plan-1', 'role': role,
            'control_sha': manifest['control_sha'], 'bundle_manifest_sha256': checked['manifest_sha256'],
            'active_policy_input': bool(install_active_policy_input), 'files': files}


def _safe_existing_path(path, *, required=False, device=None):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('target path contains a symlink')
    if required and not path.exists():
        raise RuntimeError('required target parent is missing')
    if path.exists():
        st = path.stat()
        if not stat.S_ISDIR(st.st_mode):
            raise RuntimeError('target parent is not a directory')
        if device is not None and st.st_dev != device:
            raise RuntimeError('target parent crossed a volume boundary')
    return path


def _assert_absent(paths):
    for path in paths:
        path = Path(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError('first-install target already exists')


def _exclusive(path, data, mode):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    dfd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _open_dir_at(parent_fd, name, device):
    fd = os.open(name, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0),
                 dir_fd=parent_fd)
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or st.st_dev != device:
        os.close(fd)
        raise RuntimeError('pinned target directory identity mismatch')
    return fd


def _mkdir_at(parent_fd, name, mode, device):
    os.mkdir(name, mode, dir_fd=parent_fd)
    fd = _open_dir_at(parent_fd, name, device)
    os.fchmod(fd, mode)
    if stat.S_IMODE(os.fstat(fd).st_mode) != mode:
        os.close(fd)
        raise RuntimeError('created directory mode mismatch')
    return fd


def _exclusive_at(directory_fd, name, data, mode):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
                 mode, dir_fd=directory_fd)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)


def _mkdir(path, mode, *, device=None):
    path = Path(path)
    _safe_existing_path(path.parent, required=True, device=device)
    os.mkdir(path, mode)
    os.chmod(path, mode)
    st = path.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != mode:
        raise RuntimeError('created directory identity mismatch')
    if device is not None and st.st_dev != device:
        raise RuntimeError('created directory crossed a volume boundary')


def _disk_uuid():
    result = subprocess.run(['/usr/sbin/diskutil', 'info', '-plist', str(CODEX_ROOT)],
                            check=True, capture_output=True, timeout=15)
    info = plistlib.loads(result.stdout)
    if info.get('MountPoint') != str(CODEX_ROOT):
        raise RuntimeError('CODEX mount identity unavailable')
    return info.get('VolumeUUID')


def _activation_bytes(module_hashes):
    value = {'schema': 'fdisbull-source-activation-1', 'approved': True,
             'selection_profile': 'single-failure-direct-imports-1', 'publisher': 'candidate-ref-v1',
             'module_sha256': {name: module_hashes[name] for name in ACTIVATION_MODULES},
             'source_interpreter': MAC_SOURCE_PYTHON}
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def apply_mac(bundle, *, expected_control_sha, expected_manifest_sha256,
              enable_source_review_approved=False):
    if platform.system() != 'Darwin' or os.geteuid() == 0:
        raise RuntimeError('Mac install requires the local non-root operator')
    checked = validate_bundle(bundle)
    _externally_pinned(checked, expected_control_sha, expected_manifest_sha256)
    # This identity gate runs before any mkdir, including the private anchor parent.
    if _disk_uuid() != CODEX_UUID:
        raise RuntimeError('pinned CODEX volume UUID mismatch')
    _safe_existing_path(CODEX_ROOT, required=True)
    root_fd = os.open(CODEX_ROOT, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    device = os.fstat(root_fd).st_dev
    if _disk_uuid() != CODEX_UUID or CODEX_ROOT.stat().st_dev != device:
        os.close(root_fd)
        raise RuntimeError('pinned CODEX volume changed during admission')
    try:
        projects_fd = _open_dir_at(root_fd, 'Codex_Projects', device)
        try:
            targets_fd = _open_dir_at(projects_fd, 'fDisBull-targets-private', device)
        finally:
            os.close(projects_fd)
    except BaseException:
        os.close(root_fd)
        raise
    for path in (MAC_CODE.parent, MAC_PROVIDER_STATE.parent, MAC_SOURCE_STATE.parent):
        _safe_existing_path(path, required=True, device=device)
    _safe_existing_path(MAC_STATUS_STATE, required=True)
    _safe_existing_path(MAC_ANCHOR.parent.parent, required=True)
    anchor_parent = MAC_ANCHOR.parent
    targets = [MAC_CODE, MAC_PROVIDER_STATE, MAC_SOURCE_STATE, anchor_parent, MAC_ANCHOR]
    _assert_absent(targets)
    # Never create a fresh status namespace: it is shared with the ordinary CI status tool.
    try:
        code_fd = _mkdir_at(targets_fd, MAC_CODE.name, 0o700, device)
        provider_fd = _mkdir_at(targets_fd, MAC_PROVIDER_STATE.name, 0o700, device)
        source_fd = _mkdir_at(targets_fd, MAC_SOURCE_STATE.name, 0o700, device)
        try:
            for name, data in checked['modules'].items():
                _exclusive_at(code_fd, name, data, 0o600)
            provider_marker = {'installation_id': 'fdisbull-production-bridge-20261113-01',
                               'volume_uuid': CODEX_UUID}
            _exclusive_at(provider_fd, 'installation.json',
                          (json.dumps(provider_marker, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o600)
            _exclusive_at(provider_fd, 'actions.lock', b'', 0o600)
            if enable_source_review_approved:
                _exclusive_at(code_fd, 'source-activation.json',
                              _activation_bytes(checked['manifest']['module_sha256']), 0o600)
        finally:
            os.close(code_fd); os.close(provider_fd); os.close(source_fd)
        # Anchor parent is separate from CODEX; it too is created relative to an
        # already-open trusted parent after proving the history leaf absent.
        anchor_parent_base = MAC_ANCHOR.parent.parent
        _safe_existing_path(anchor_parent_base, required=True)
        anchor_base_fd = os.open(anchor_parent_base, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
                                 | getattr(os, 'O_NOFOLLOW', 0))
        try:
            anchor_dir_fd = _mkdir_at(anchor_base_fd, MAC_ANCHOR.parent.name, 0o700,
                                      os.fstat(anchor_base_fd).st_dev)
            try:
                anchor = {'installation_id': 'fdisbull-production-bridge-20261113-01',
                          'volume_uuid': CODEX_UUID, 'sequence': 0, 'actions': {}}
                _exclusive_at(anchor_dir_fd, MAC_ANCHOR.name,
                              (json.dumps(anchor, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o600)
            finally:
                os.close(anchor_dir_fd)
        finally:
            os.close(anchor_base_fd)
    finally:
        os.close(targets_fd)
        os.close(root_fd)
    return {'applied': True, 'role': 'mac', 'control_sha': checked['manifest']['control_sha'],
            'source_activation': bool(enable_source_review_approved)}


def _vps_config(manifest):
    return {'schema': 'fdisbull-production-ci-config-1', 'enabled': False,
            'installation_id': VPS_INSTALLATION_ID, 'bridge_path': str(VPS_BRIDGE),
            'state_dir': str(VPS_STATE), 'export_root': str(VPS_EXPORTS),
            'executor_lock': str(VPS_EXECUTOR_LOCK), 'activated_epoch': int(time.time()),
            'max_incident_seconds': 28800, 'incident_test': False,
            'github': {**VPS_GITHUB, 'control_sha': manifest['control_sha']},
            'module_sha256': manifest['module_sha256'],
            'entrypoint_sha256': manifest['entrypoint_sha256']}


def _write_tree(directory, files, *, file_mode=0o644):
    _mkdir(directory, 0o755)
    for name, data in files.items():
        _exclusive(directory / name, data, file_mode)


def apply_vps(bundle, *, expected_control_sha, expected_manifest_sha256,
              install_active_policy_input=False):
    if platform.system() != 'Linux' or os.geteuid() != 0:
        raise RuntimeError('VPS install requires the root operator on Linux')
    checked = validate_bundle(bundle)
    _externally_pinned(checked, expected_control_sha, expected_manifest_sha256)
    destinations = [VPS_ENTRY, VPS_MODULES, VPS_CONFIG, VPS_UNIT, VPS_POLICY,
                    VPS_JOB_INPUTS, VPS_STATE]
    if install_active_policy_input:
        destinations.append(VPS_ACTIVE_POLICY)
    _assert_absent(destinations)
    for path in (VPS_ENTRY.parent, VPS_MODULES.parent, VPS_CONFIG.parent.parent, VPS_UNIT.parent,
                 VPS_CONTROL, VPS_STATE.parent):
        _safe_existing_path(path, required=True)
    if not VPS_EXECUTOR_LOCK.is_file() or VPS_EXECUTOR_LOCK.is_symlink():
        raise RuntimeError('preinstalled shared executor lock missing')
    for d in (VPS_ENTRY.parent, VPS_MODULES.parent, VPS_CONFIG.parent.parent, VPS_UNIT.parent,
              VPS_CONTROL, VPS_STATE.parent):
        if d.stat().st_uid != 0:
            raise RuntimeError('existing system parent is not root-owned')
    if stat.S_IMODE(VPS_CONTROL.stat().st_mode) & 0o077:
        raise RuntimeError('existing private control directory permissions invalid')
    if not VPS_CONFIG.parent.exists():
        _mkdir(VPS_CONFIG.parent, 0o755)
    # Establish a disabled config and genesis state before installing the unit.
    _mkdir(VPS_STATE, 0o700)
    marker = {'schema': 'fdisbull-production-state-1', 'installation_id': VPS_INSTALLATION_ID}
    _exclusive(VPS_STATE / 'installation.json',
               (json.dumps(marker, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o600)
    _exclusive(VPS_CONFIG, (json.dumps(_vps_config(checked['manifest']), sort_keys=True,
                                      separators=(',', ':')) + '\n').encode(), 0o600)
    _write_tree(VPS_MODULES, checked['modules'])
    _exclusive(VPS_ENTRY, checked['modules']['production-ci.py'], 0o755)
    _exclusive(VPS_POLICY, checked['policy'], 0o400)
    _mkdir(VPS_JOB_INPUTS, 0o700)
    if install_active_policy_input:
        _exclusive(VPS_ACTIVE_POLICY, checked['policy'], 0o644)
    # Initialize the pinned empty inbox using the installed, hash-verified source.
    sys.path.insert(0, str(VPS_MODULES))
    spec = importlib.util.spec_from_file_location('installed_production_intake', VPS_MODULES / 'production_intake.py')
    intake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(intake)
    with intake.FailureInbox(VPS_STATE / 'failure-inbox.sqlite'):
        pass
    os.chmod(VPS_STATE / 'failure-inbox.sqlite', 0o600)
    _exclusive(VPS_UNIT, checked['unit'], 0o644)
    verify = subprocess.run(['/usr/bin/systemd-analyze', 'verify', str(VPS_UNIT)],
                            capture_output=True, timeout=30)
    if verify.returncode != 0:
        raise RuntimeError('systemd unit verification failed; installed files retained for review')
    return {'applied': True, 'role': 'vps', 'control_sha': checked['manifest']['control_sha'],
            'enabled': False, 'systemd_verified': True,
            'active_policy_input': bool(install_active_policy_input)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('mac', 'vps'), required=True)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--expected-control-sha', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--apply', action='store_true', help='write only the fixed first-install targets')
    parser.add_argument('--enable-source-review-approved', action='store_true',
                        help='create the reviewed Mac source activation file')
    parser.add_argument('--install-active-policy-input', action='store_true',
                        help='install the fixed active VPS qualification input')
    args = parser.parse_args(argv)
    try:
        result = plan(args.role, args.bundle,
                      expected_control_sha=args.expected_control_sha,
                      expected_manifest_sha256=args.expected_manifest_sha256,
                      enable_source_review_approved=args.enable_source_review_approved,
                      install_active_policy_input=args.install_active_policy_input)
        if args.apply:
            if args.role == 'mac':
                result = apply_mac(args.bundle,
                                   expected_control_sha=args.expected_control_sha,
                                   expected_manifest_sha256=args.expected_manifest_sha256,
                                   enable_source_review_approved=args.enable_source_review_approved)
            else:
                result = apply_vps(args.bundle,
                                   expected_control_sha=args.expected_control_sha,
                                   expected_manifest_sha256=args.expected_manifest_sha256,
                                   install_active_policy_input=args.install_active_policy_input)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'refused', 'reason': type(exc).__name__}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
