"""Regression checks for replay tool closure and untrusted dependency metadata."""
import platform
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fdisbull import genesis_replay, udc_genesis_game


def test_untrusted_host_dependency_size_is_checked_before_read(tmp_path, monkeypatch):
    path = tmp_path / 'large-dylib'
    with path.open('wb') as f:
        f.truncate(genesis_replay.MAX_FILE + 1)
    original = Path.read_bytes

    def guarded_read(self):
        if self == path:
            pytest.fail('oversized lock-selected file was read into memory')
        return original(self)

    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    expected = {'platform': sys.platform, 'machine': platform.machine(),
                'dependencies': [{'path': str(path), 'size': path.stat().st_size,
                                  'sha256': '0' * 64}]}
    with pytest.raises(ValueError):
        genesis_replay._verify_host_tool_dependencies(expected)


def test_native_tool_subprocess_drops_dyld_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv('DYLD_INSERT_LIBRARIES', '/untrusted/inject.dylib')
    monkeypatch.setenv('DYLD_LIBRARY_PATH', '/untrusted/libs')
    observed = {}

    def fake_run(args, **kwargs):
        observed.update(kwargs['env'])
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(udc_genesis_game.subprocess, 'run', fake_run)
    udc_genesis_game._run(['compiler'], tmp_path)
    assert not any(key.startswith('DYLD_') for key in observed)


def test_unresolved_dynamic_library_reference_is_not_silently_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(genesis_replay.sys, 'platform', 'darwin')
    monkeypatch.setattr(genesis_replay.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=0, stdout='compiler:\n\t@rpath/unbound.dylib (compatibility version 1.0.0, current version 1.0.0)\n'))
    with pytest.raises(ValueError):
        genesis_replay._host_tool_dependencies(tmp_path, {'bin/m68k-elf-gcc': b''})
