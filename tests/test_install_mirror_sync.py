"""Isolated preview, installation and receive-hook wake contract."""
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
    state = m['root'] / 'service-state'
    plist = m['root'] / 'agent.plist'
    args = ['/Users/tiga/miniconda/bin/python3', installer, '--hub', m['hub'],
        '--cache', m['cache'], '--gitlab', 'https://fixture.invalid/repository.git', '--state-dir', state,
        '--plist', plist, '--git', '/opt/homebrew/bin/git', '--python', '/Users/tiga/miniconda/bin/python3',
        '--worker-source', fake_worker, '--diskutil', fake, '--volume', '/=TEST-UUID']
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
