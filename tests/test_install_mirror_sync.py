"""Isolated preview, installation and receive-hook wake contract."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

import pytest

from test_mirror_sync_service import ROOT, branch, cmd, mirrors, publish


def installer_args(m):
    installer = ROOT / 'scripts' / 'install_mirror_sync.py'
    fake = m['root'] / 'fake-diskutil'
    fake.write_text('''#!/bin/sh
cat <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>MountPoint</key><string>/</string><key>VolumeUUID</key><string>TEST-UUID</string></dict></plist>
XML
''')
    fake.chmod(0o755)
    fake_worker = m['root'] / 'authored-worker.py'
    fake_worker.write_text('# Authored fixture; installer must never launch it.\n')
    fake_checker = m['root'] / 'authored-storage-checker.py'
    fake_checker.write_text('# Authored fixture; installer must never launch it.\n')
    fake_admission_script = m['root'] / 'authored-storage-admission.py'
    fake_admission_script.write_text('# Authored fixture; installer must never launch it.\n')
    state = m['root'] / 'service-state'
    plist = m['root'] / 'agent.plist'
    args = ['/Users/tiga/miniconda/bin/python3', installer, '--hub', m['hub'],
        '--cache', m['cache'], '--gitlab', 'https://fixture.invalid/repository.git', '--state-dir', state,
        '--plist', plist, '--git', '/opt/homebrew/bin/git', '--python', '/Users/tiga/miniconda/bin/python3',
        '--worker-source', fake_worker, '--storage-checker-source', fake_checker,
        '--storage-admission-script', fake_admission_script,
        '--diskutil', fake, '--volume', '/=TEST-UUID']
    return args, state, plist, fake_worker


def test_installer_preview_apply_hook_and_disable(mirrors):
    m = mirrors
    args, state, plist, fake_worker = installer_args(m)
    preview = cmd(*args, env=m['env'])
    assert json.loads(preview.stdout)['action'] == 'preview'
    assert not state.exists() and not plist.exists() and not (m['hub'] / 'hooks' / 'post-receive').exists()
    applied = cmd(*args, '--apply', env=m['env'])
    assert json.loads(applied.stdout)['launches_service'] is False
    assert not m['cache'].exists()
    assert (state / 'runtime' / 'mirror_sync_service.py').read_bytes() == fake_worker.read_bytes()
    config = json.loads((state / 'config.json').read_text())
    assert config['storage'] == {'mode': 'none'}
    checker = state / 'runtime' / 'mirror_storage_admit.py'
    assert checker.read_bytes() == (m['root'] / 'authored-storage-checker.py').read_bytes()
    manifest = json.loads((state / 'install-manifest.json').read_text())
    assert manifest['storage_checker_sha256'] == hashlib.sha256(checker.read_bytes()).hexdigest()
    wake = state / 'wake'
    os.utime(wake, (1, 1))
    updated = branch(m, m['base'], 'wake without executing sync')
    started = time.monotonic()
    publish(m, 'hub', updated, 'refs/heads/hook-witness')
    assert time.monotonic() - started < 3
    assert wake.stat().st_mtime > 1
    assert not m['cache'].exists()
    disabled = cmd(*args, '--disable', env=m['env'])
    assert json.loads(disabled.stdout)['action'] == 'disable'
    assert not (m['hub'] / 'hooks' / 'post-receive').exists()
    assert not plist.exists() and not m['cache'].exists()


@pytest.mark.parametrize('target', ['hook', 'plist'])
def test_installer_refuses_dangling_owned_path_symlinks(mirrors, target):
    m = mirrors
    args, state, plist, _ = installer_args(m)
    path = m['hub'] / 'hooks' / 'post-receive' if target == 'hook' else plist
    path.symlink_to(m['root'] / 'missing-symlink-target')
    result = cmd(*args, '--apply', env=m['env'], check=False)
    assert result.returncode != 0
    assert path.is_symlink() and not (m['root'] / 'missing-symlink-target').exists()
    assert not state.exists()


def test_installer_refuses_global_unmanaged_hookspath(mirrors):
    m = mirrors
    args, state, plist, _ = installer_args(m)
    gitconfig = m['root'] / 'global-gitconfig'
    hooks = m['root'] / 'external-hooks'
    hooks.mkdir()
    gitconfig.write_text('[core]\n\thooksPath = ' + str(hooks) + '\n')
    env = dict(m['env'], GIT_CONFIG_GLOBAL=str(gitconfig))
    result = cmd(*args, '--apply', env=env, check=False)
    assert result.returncode != 0
    assert not state.exists() and not plist.exists()
    assert list(hooks.iterdir()) == []


@pytest.mark.parametrize('already_refuse', [True, False])
def test_disable_recovers_interrupted_install_receive_state(mirrors, already_refuse):
    m = mirrors
    args, state, plist, _ = installer_args(m)
    cmd(*args, '--apply', env=m['env'])
    manifest = state / 'install-manifest.json'
    data = json.loads(manifest.read_text())
    data.update(phase='installing', installed=False)
    manifest.write_text(json.dumps(data))
    if not already_refuse:
        cmd('git', '--git-dir', m['hub'], 'config', '--unset-all',
            'receive.denyCurrentBranch', env=m['env'])
    result = cmd(*args, '--disable', env=m['env'])
    assert json.loads(result.stdout)['action'] == 'disable'
    assert not plist.exists() and not (m['hub'] / 'hooks' / 'post-receive').exists()
    current = cmd('git', '--git-dir', m['hub'], 'config', '--local', '--get-all',
                  'receive.denyCurrentBranch', env=m['env'], check=False)
    assert current.returncode == 1


def test_disable_retains_identical_files_that_predated_install(mirrors):
    import importlib.util
    m = mirrors
    args, state, plist, _ = installer_args(m)
    spec = importlib.util.spec_from_file_location('mirror_installer_fixture', ROOT / 'scripts' / 'install_mirror_sync.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    hook = m['hub'] / 'hooks' / 'post-receive'
    hook_bytes = installer.hook_contents(state / 'wake')
    plist_bytes = installer.plist_contents(Path('/Users/tiga/miniconda/bin/python3'),
        state / 'runtime' / 'mirror_sync_service.py', state / 'config.json', state, state / 'wake')
    hook.write_bytes(hook_bytes)
    hook.chmod(0o755)
    plist.write_bytes(plist_bytes)
    cmd(*args, '--apply', env=m['env'])
    cmd(*args, '--disable', env=m['env'])
    assert hook.read_bytes() == hook_bytes and plist.read_bytes() == plist_bytes


@pytest.mark.parametrize('mode', ['apply', 'disable'])
def test_installer_refuses_busy_worker_lock_without_changing_installed_files(mirrors, mode):
    m = mirrors
    args, state, plist, fake_worker = installer_args(m)
    cmd(*args, '--apply', env=m['env'])
    hook = m['hub'] / 'hooks' / 'post-receive'
    managed = [state / 'runtime' / 'mirror_sync_service.py',
               state / 'runtime' / 'mirror_storage_admit.py', state / 'config.json',
               state / 'install-manifest.json', hook, plist]
    before = {path: path.read_bytes() for path in managed}
    prior_manifest = json.loads(before[state / 'install-manifest.json'])
    if mode == 'apply':
        fake_worker.write_text('# Authored replacement; must wait for the lock.\n')
    with (state / 'run.lock').open('r+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = cmd(*args, '--' + mode, env=m['env'], check=False)
        assert result.returncode == 2
        assert 'busy' in result.stderr
        assert {path: path.read_bytes() for path in managed} == before
    assert cmd('git', '--git-dir', m['hub'], 'config', '--local', '--get-all',
               'receive.denyCurrentBranch', env=m['env']).stdout.strip() == 'refuse'
    if mode == 'apply':
        cmd(*args, '--apply', env=m['env'])
        assert (state / 'runtime' / 'mirror_sync_service.py').read_bytes() == fake_worker.read_bytes()
        updated_manifest = json.loads((state / 'install-manifest.json').read_text())
        assert updated_manifest['original_deny_current_branch'] == prior_manifest['original_deny_current_branch']
    else:
        cmd(*args, '--disable', env=m['env'])
        assert not plist.exists() and not hook.exists()


@pytest.mark.parametrize('option,value', [
    ('--storage-checker-source', 'relative.py'),
])
def test_installer_rejects_invalid_storage_options(mirrors, option, value):
    m = mirrors
    args, state, plist, _ = installer_args(m)
    result = cmd(*args, option, value, env=m['env'], check=False)
    assert result.returncode == 2
    assert not state.exists() and not plist.exists()


@pytest.mark.parametrize('url', ['https://github.com/fixture/inactive.git',
                               'ssh://ssh.github.com/fixture/inactive.git'])
def test_installer_rejects_inactive_github(mirrors, url):
    m = mirrors
    args, state, plist, _ = installer_args(m)
    result = cmd(*args, '--gitlab', url, env=m['env'], check=False)
    assert result.returncode == 2 and 'GitHub mirror is inactive' in result.stderr
    assert not state.exists() and not plist.exists()


def test_installer_storage_overrides_and_legacy_manifest_migration(mirrors):
    m = mirrors
    args, state, _, _ = installer_args(m)
    cmd(*args, '--apply', env=m['env'])
    config_path = state / 'config.json'
    manifest_path = state / 'install-manifest.json'
    checker_path = state / 'runtime' / 'mirror_storage_admit.py'
    config = json.loads(config_path.read_text())
    config.pop('storage')
    legacy_config = (json.dumps(config, indent=2, sort_keys=True) + '\n').encode()
    config_path.write_bytes(legacy_config)
    manifest = json.loads(manifest_path.read_text())
    manifest.pop('storage_checker_sha256')
    manifest['config_sha256'] = hashlib.sha256(legacy_config).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    checker_path.unlink()
    baseline = state / 'refs.json'
    baseline.write_bytes(b'prior cache identity and cursor\n')
    cmd(*args, '--storage-expected-bytes', '2000000000',
        '--storage-reserve-bytes', '50000000000', '--apply', env=m['env'])
    migrated = json.loads(config_path.read_text())
    assert migrated['storage'] == {'mode': 'none'}
    new_manifest = json.loads(manifest_path.read_text())
    assert new_manifest['storage_checker_sha256'] == hashlib.sha256(checker_path.read_bytes()).hexdigest()
    assert new_manifest['original_deny_current_branch'] == manifest['original_deny_current_branch']
    assert baseline.read_bytes() == b'prior cache identity and cursor\n'


def test_managed_upgrade_preserves_enabled_github_peer(mirrors):
    m = mirrors
    args, state, _, _ = installer_args(m)
    cmd(*args, '--apply', env=m['env'])
    config = state / 'config.json'
    value = json.loads(config.read_text())
    peer = dict(url='https://github.com/seeker-cyber-maker/fDisBull.git',
                cache=str(m['root'] / 'github-cache.git'),
                state_dir=str(m['root'] / 'github-state'), tag_exceptions=[])
    value['github'] = peer
    config.write_text(json.dumps(value))
    manifest = state / 'install-manifest.json'
    recorded = json.loads(manifest.read_text())
    recorded['config_sha256'] = hashlib.sha256(config.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(recorded))
    cmd(*args, '--apply', env=m['env'])
    assert json.loads(config.read_text())['github'] == peer
