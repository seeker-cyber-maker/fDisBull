"""Target-bound replay recipes and Genesis toolchain snapshot checks."""
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import pytest

from fdisbull import genesis_replay as replay
from fdisbull.game_il import canonical


def record(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save_lock(bundle, lock):
    (bundle / 'replay.json').write_bytes(canonical(lock) + b'\n')


def genesis_inspection_bundle(tmp_path):
    bundle = tmp_path / 'genesis-bundle'
    bundle.mkdir()
    files, modules = {}, {}
    for name, relative in replay.MODULE_PATHS.items():
        raw = canonical({'fixture': name, 'claim': 'inert target fixture'}) + b'\n'
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files[relative] = record(raw)
        modules[name] = {'path': relative, **record(raw),
                         'canonical_sha256': hashlib.sha256(canonical(
                             {'fixture': name, 'claim': 'inert target fixture'})).hexdigest()}
    output = b'fixture; never executed'
    (bundle / 'native').mkdir()
    (bundle / 'native/program.md').write_bytes(output)
    files['native/program.md'] = record(output)
    engine = {'fixture.py': record(b'# inert\n')}
    (bundle / 'captured/engine').mkdir(parents=True)
    (bundle / 'captured/engine/fixture.py').write_bytes(b'# inert\n')
    files['captured/engine/fixture.py'] = engine['fixture.py']
    tools = {}
    for name in replay._m68k_input_names():
        raw = ('inert fixture tool: ' + name).encode()
        target = bundle / 'captured/toolchain' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        tools[name] = record(raw)
        files['captured/toolchain/' + name] = tools[name]
    recipe = replay._recipe('efficient', None, target='genesis')
    lock = {
        'format': replay.FORMAT, 'profile': replay.PROFILE, 'recipe': recipe,
        'source': {'platform': 'genesis', **record(b'fixture original source')},
        'modules': modules, 'files': files, 'engine': engine,
        'toolchain': tools,
        'toolchain_host': {'platform': sys.platform, 'machine': platform.machine(),
                           'dependencies': []},
        'expected_output': {'path': 'native/program.md', **record(output)},
        'qualification': {'native_execution': 'not run'},
    }
    save_lock(bundle, lock)
    return bundle, lock


def test_recipe_is_explicit_per_target_and_keeps_nes_contract():
    nes = replay._recipe('efficient', None)
    genesis = replay._recipe('efficient', None, target='genesis')
    assert nes['id'] == 'miniplanets-procedural-nes-1'
    assert nes['target'] == 'nes'
    assert genesis['id'] == 'miniplanets-procedural-genesis-1'
    assert genesis['target'] == 'genesis'
    assert genesis['limits'] != nes['limits']
    with pytest.raises(ValueError, match='target'):
        replay._recipe('efficient', None, target='sms')


def test_genesis_tool_input_closure_is_bounded_and_target_specific():
    names = replay._m68k_input_names()
    assert 'bin/m68k-elf-gcc' in names
    assert 'bin/m68k-elf-as' in names
    assert 'libexec/gcc/m68k-elf/16.2.0/cc1' in names
    assert 'libexec/gcc/m68k-elf/16.2.0/collect2' in names
    assert 'bin/cc65' not in names


def test_genesis_bundle_inspection_binds_genesis_output_and_recipe(tmp_path):
    bundle, lock = genesis_inspection_bundle(tmp_path)
    result = replay.inspect_bundle(bundle)
    assert result['target'] == 'genesis'
    assert result['payloads_intact'] is True
    assert result['expected_rom_sha256'] == lock['expected_output']['sha256']
    assert result['implementation_match'] is False


def test_inspection_does_not_resolve_lock_selected_host_dylibs(tmp_path, monkeypatch):
    bundle, lock = genesis_inspection_bundle(tmp_path)
    lock['toolchain_host']['dependencies'] = [{
        'path': str(tmp_path / 'does-not-exist.dylib'),
        'size': 0, 'sha256': '0' * 64,
    }]
    save_lock(bundle, lock)
    monkeypatch.setattr(replay, '_verify_host_tool_dependencies',
                        lambda _: pytest.fail('inspection accessed an external dylib'))
    result = replay.inspect_bundle(bundle)
    assert result['payloads_intact'] is True
    assert result['host_tool_dependencies_verified'] is False


def test_replay_target_cannot_be_changed_from_locked_genesis(tmp_path):
    bundle, _ = genesis_inspection_bundle(tmp_path)
    with pytest.raises(ValueError, match='target differs'):
        replay.replay_bundle(bundle, tmp_path / 'out', rom_path=tmp_path / 'source.bin',
                             m68k_root=tmp_path / 'tools')
    assert not (tmp_path / 'out').exists()


def test_genesis_bundle_rejects_modified_captured_compiler(tmp_path):
    bundle, lock = genesis_inspection_bundle(tmp_path)
    tool = bundle / 'captured/toolchain/bin/m68k-elf-gcc'
    tool.write_bytes(tool.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='changed replay payload'):
        replay.inspect_bundle(bundle)


def test_opt_in_real_genesis_bundle_replay(tmp_path):
    rom = os.environ.get('FDISBULL_MINIPLANETS_ROM')
    tool_root = os.environ.get('FDISBULL_M68K_ROOT')
    if not rom or not tool_root:
        pytest.skip('requires explicit private REV04 ROM and trusted m68k root')
    built = replay.write_bundle(rom, tmp_path / 'bundle', target='genesis',
                                m68k_root=tool_root)
    checked = replay.inspect_bundle(tmp_path / 'bundle')
    assert checked['payloads_intact'] and checked['target'] == 'genesis'
    replayed = replay.replay_bundle(tmp_path / 'bundle', tmp_path / 'replayed',
                                    rom_path=rom, target='genesis',
                                    m68k_root=tool_root)
    assert replayed['rom_bytes_match'] and replayed['rom_sha256'] == built['rom_sha256']
