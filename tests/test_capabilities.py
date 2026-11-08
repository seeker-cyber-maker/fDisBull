"""Discovery must work before native dependencies, targets or live tests."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import main, respond


def catalog(report):
    return {item['id']: item for item in report['capabilities']}


def test_cli_and_projectless_json_agree(capsys):
    assert main(['capabilities']) == 0
    cli = json.loads(capsys.readouterr().out)
    reply = respond({'method': 'capabilities'}, default_project='/does/not/exist.fdb')
    assert cli['ok'] and reply['ok']
    assert cli['result'] == reply['result']
    assert cli['result']['format'] == 'fdisbull-capabilities-1'
    # The expanded 0.32 catalog plus candidate identity fields stay within
    # half the ordinary 64 KiB reply limit.
    assert len(json.dumps(cli).encode()) < 33 * 1024
    assert all(item['status'] == 'read' for item in cli['result']['sources'].values())


def test_discovery_needs_no_site_packages_or_native_imports():
    root = Path(__file__).resolve().parents[1]
    code = '''
import json, sys
from fdisbull.cli import invoke
report = invoke('capabilities', {})
assert not ({'fdisbull.project', 'fdisbull.ghidra_arm64', 'fdisbull.macos_lldb',
             'fdisbull.uil_native', 'fdisbull.uil_native_codegen', 'fdisbull.uil_desktop',
             'lief', 'capstone', 'iced_x86', 'PIL'} & set(sys.modules))
print(json.dumps(report))
'''
    result = subprocess.run([sys.executable, '-S', '-c', code], cwd=root,
                            env={**os.environ, 'PYTHONPATH': str(root / 'src')},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['dependencies']['capstone']['status'] == 'not_found'
    assert catalog(report)['decode.arm64']['availability'] == 'missing_dependencies'


def test_discovery_never_starts_a_tool_or_target(monkeypatch):
    import fdisbull.capabilities as module

    def forbidden(*args, **kwargs):
        raise AssertionError('discovery launched a process')

    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    report = module.capabilities()
    assert report['discovery'] == {
        'external_tools_executed': False, 'targets_executed': False,
        'native_modules_imported': False, 'runtime_validation': 'not_run',
    }
    assert all(item['runtime_validation'] == 'not_run' for item in report['capabilities'])


def test_detected_executable_is_not_runtime_validation(tmp_path, monkeypatch):
    import fdisbull.capabilities as module
    monkeypatch.setattr(module.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(module, '_python_dependency', lambda name, distribution: {
        'kind': 'python', 'status': 'detected', 'version': None, 'validation': 'not_imported'})
    fake = tmp_path / 'tool'
    fake.write_text('#!/bin/sh\nexit 99\n')
    fake.chmod(0o700)
    report = module.capabilities(analyze_headless=str(fake), lldb=str(fake), java=str(fake))
    items = catalog(report)
    assert report['dependencies']['ghidra-headless']['status'] == 'detected'
    assert items['decompile.macho-arm64']['availability'] == 'dependencies_detected'
    assert items['debug.macos-arm64']['availability'] == 'dependencies_detected'
    assert items['decompile.macho-arm64']['runtime_validation'] == 'not_run'
    assert items['debug.macos-arm64']['runtime_validation'] == 'not_run'


def test_explicit_paths_do_not_fall_back_to_path(tmp_path, monkeypatch):
    import fdisbull.capabilities as module
    monkeypatch.setattr(module.shutil, 'which', lambda name: sys.executable)
    directory = tmp_path / 'directory'
    directory.mkdir()
    not_executable = tmp_path / 'file'
    not_executable.write_text('plain file')
    not_executable.chmod(0o600)
    report = module.capabilities(analyze_headless=str(tmp_path / 'absent'),
                                 lldb=str(directory), java=str(not_executable))
    assert all(report['dependencies'][name]['status'] == 'not_found'
               for name in ('ghidra-headless', 'lldb', 'java'))


def test_path_expansion_failure_stays_in_protocol(monkeypatch):
    import fdisbull.capabilities as module

    def unknown_user(self):
        raise RuntimeError('cannot determine home directory')

    monkeypatch.setattr(module.Path, 'expanduser', unknown_user)
    reply = respond({'method': 'capabilities', 'params': {'lldb': '~unknown/tool'}})
    assert not reply['ok'] and reply['error']['type'] == 'ValueError'


def test_wrong_host_and_unsupported_semantics_are_explicit(monkeypatch):
    import fdisbull.capabilities as module
    monkeypatch.setattr(module.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    items = catalog(module.capabilities())
    assert items['debug.macos-arm64']['availability'] == 'host_unsupported'
    for name in ('uil.native-app-export', 'uil.macos-host-effects', 'compile.macos-arm64'):
        assert items[name]['implementation'] == 'unsupported'
        assert items[name]['availability'] == 'unsupported'
    assert 'input reader' in items['lift.c-u16']['scope']
    assert 'statement view' in items['view.c-x86-16']['scope']
    assert '4 KiB' in items['decompile.macho-arm64']['scope']
    assert items['view.c-x86-16']['independent_decompiler'] is False
    assert items['decompile.macho-arm64']['maturity'] == 'experimental'


@pytest.mark.parametrize('params', [{'unknown': True}, {'project': 'x'}, {'lldb': []},
                                     {'java': True}, {'analyze_headless': ''}])
def test_bad_parameters_are_refused(params):
    assert not respond({'method': 'capabilities', 'params': params})['ok']


def test_provider_identity_changes_when_source_changes(tmp_path, monkeypatch):
    import fdisbull.capabilities as module
    monkeypatch.setattr(module, '_PACKAGE_ROOT', tmp_path)
    (tmp_path / 'decoder.py').write_text('first')
    first = module.capabilities()
    (tmp_path / 'decoder.py').write_text('second')
    second = module.capabilities()
    assert first['package']['provider_fingerprint'] != second['package']['provider_fingerprint']
    assert first['package']['source_revision'] is None
    assert second['package']['release_status'] == 'not_determined'
    assert first['sources']['decoder.py']['sha256'] != second['sources']['decoder.py']['sha256']
    assert catalog(first)['decompile.macho-arm64']['availability'] == 'component_missing'


def test_common_native_and_desktop_are_bounded_unqualified_discovery_entries():
    from fdisbull.capabilities import capabilities
    report = capabilities();items = catalog(report)
    assert set(items['compile.common-native']['interfaces']) == {
        'cli:uil-compile', 'cli:uil-link', 'cli:uil-components', 'cli:uil-build', 'cli:uil-seal'}
    assert set(items['uil.common-desktop']['interfaces']) == {
        'cli:uil-desktop', 'cli:uil-desktop-build', 'cli:uil-desktop-seal'}
    for name in ('compile.common-native', 'uil.common-desktop'):
        item = items[name]
        assert item['implementation'] == 'partial' and item['maturity'] == 'bounded'
        assert item['targets'] == ['macos-arm64', 'linux-x64', 'windows-x64']
        assert item['availability'] in ('not_checked', 'missing_dependencies')
        assert item['runtime_validation'] == 'not_run'
        assert all(report['sources'][path]['status'] == 'read' for path in item['providers'])
    assert report['dependencies']['native-c-compiler'] == {'kind': 'configuration', 'status': 'not_selected'}
    assert report['dependencies']['native-window-services'] == {'kind': 'configuration', 'status': 'not_selected'}
    assert items['compile.macos-arm64']['implementation'] == 'unsupported'
    assert items['compile.macos-arm64']['bounded_alternatives'] == ['compile.common-native', 'uil.common-desktop']


def test_desktop_template_changes_and_missing_files_affect_discovery(tmp_path, monkeypatch):
    import fdisbull.capabilities as module
    original = module._PACKAGE_ROOT
    providers = catalog(module.capabilities())['uil.common-desktop']['providers']
    for name in providers:
        target = tmp_path/name;target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original/name).read_bytes())
    monkeypatch.setattr(module, '_PACKAGE_ROOT', tmp_path)
    first = module.capabilities()
    path = tmp_path/'native_runtime/memory-appkit.m'
    path.write_bytes(path.read_bytes()+b'\n/* Authored identity probe. */\n')
    changed = module.capabilities()
    assert first['package']['provider_fingerprint'] != changed['package']['provider_fingerprint']
    assert first['sources']['native_runtime/memory-appkit.m']['sha256'] != changed['sources']['native_runtime/memory-appkit.m']['sha256']
    path.unlink()
    missing = module.capabilities()
    assert catalog(missing)['uil.common-desktop']['availability'] == 'component_missing'


def test_mutating_returned_common_catalog_does_not_expand_fixed_file_reads():
    from fdisbull.capabilities import capabilities
    first = capabilities()
    catalog(first)['uil.common-desktop']['providers'].append('../unadmitted-input')
    second = capabilities()
    assert '../unadmitted-input' not in second['sources']
    assert '../unadmitted-input' not in catalog(second)['uil.common-desktop']['providers']
