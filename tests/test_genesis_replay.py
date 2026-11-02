"""Replay lock integrity checks. Original game inputs remain external/private.

Authored fixtures only exercise byte-level bundle inspection; they do not claim
that a synthetic JSON module is a qualified game or executable cartridge.
"""
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from fdisbull import genesis_replay as replay
from fdisbull.game_il import canonical


def record(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save_lock(bundle, lock):
    (bundle / 'replay.json').write_bytes(canonical(lock) + b'\n')


def authored_inspection_bundle(tmp_path):
    """Structurally valid inert test data, never passed off as recovered UIL."""
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    files, modules = {}, {}
    for name, relative in replay.MODULE_PATHS.items():
        payload = {'fixture': name, 'claim': 'authored data, not game UIL'}
        raw = canonical(payload) + b'\n'
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files[relative] = record(raw)
        modules[name] = {'path': relative, **record(raw),
                         'canonical_sha256': hashlib.sha256(canonical(payload)).hexdigest()}
    cartridge = b'authored-only-not-a-cartridge'
    (bundle / 'native').mkdir()
    (bundle / 'native/program.nes').write_bytes(cartridge)
    files['native/program.nes'] = record(cartridge)
    engine = {'fixture_engine.py': record(b'# inert authored fixture\n')}
    engine_file = bundle / 'captured/engine/fixture_engine.py'
    engine_file.parent.mkdir(parents=True, exist_ok=True)
    engine_file.write_bytes(b'# inert authored fixture\n')
    files['captured/engine/fixture_engine.py'] = engine['fixture_engine.py']
    tools = {}
    for name in replay.TOOL_INPUTS:
        raw = ('inert authored tool fixture: ' + name).encode()
        target = bundle / 'captured/toolchain' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        tools[name] = record(raw)
        files['captured/toolchain/' + name] = tools[name]
    lock = {
        'format': replay.FORMAT, 'profile': replay.PROFILE,
        'recipe': replay._recipe('efficient', None),
        'source': {'platform': 'genesis', **record(b'authored-only')},
        'modules': modules, 'files': files, 'engine': engine, 'toolchain': tools,
        'expected_output': {'path': 'native/program.nes', **record(cartridge)},
        'qualification': {'native_execution': 'fixture only; no runtime evidence'},
    }
    save_lock(bundle, lock)
    return bundle, lock


def test_unknown_source_preflight_is_not_semantic_recovery(tmp_path):
    path = tmp_path / 'unknown.bin'
    path.write_bytes(bytes(0x200))
    result = replay.inspect_source(path)
    assert result['source'] == record(path.read_bytes())
    assert result['supported'] is False
    assert result['profile'] is None
    assert result['status'] == 'unsupported-semantic-profile'
    assert result['executed'] is False
    with pytest.raises(ValueError):
        replay.write_bundle(path, tmp_path / 'out', cc65_root=tmp_path / 'missing')
    assert not (tmp_path / 'out').exists()


def test_registry_discloses_bounded_profile():
    result = replay.profiles()
    assert result['source_platform'] == 'genesis'
    profile = next(p for p in result['profiles'] if p['id'] == replay.PROFILE)
    assert profile['target'] == 'nes'
    assert profile['whole_rom_automatic_lifting'] is False
    assert set(profile['semantic_modules']) == {'game', 'audio', 'presentation', 'psg'}


def test_authored_inspection_is_structural_and_never_executes(tmp_path):
    bundle, _ = authored_inspection_bundle(tmp_path)
    result = replay.inspect_bundle(bundle)
    assert result['payloads_intact'] is True
    assert result['executed'] is False
    assert result['implementation_match'] is False
    assert result['qualification_claims']['native_execution'].startswith('fixture only')
    assert result['qualification_claims_verified'] is False
    assert result['native_execution'] == 'not run by inspection'


@pytest.mark.parametrize('bad', ['../outside', '/absolute', 'uil/../outside',
                                 'uil//name', './name', 'uil/./name', 'uil\\name', ''])
def test_unsafe_inventory_paths_fail_closed(tmp_path, bad):
    bundle, lock = authored_inspection_bundle(tmp_path)
    lock['files'][bad] = record(b'')
    save_lock(bundle, lock)
    with pytest.raises(ValueError, match='Unsafe replay payload path'):
        replay.inspect_bundle(bundle)


def test_payload_symlink_and_direct_lock_symlink_are_refused(tmp_path):
    bundle, lock = authored_inspection_bundle(tmp_path)
    outside = tmp_path / 'elsewhere'
    outside.write_bytes((bundle / 'uil/game.uil.json').read_bytes())
    (bundle / 'uil/game.uil.json').unlink()
    (bundle / 'uil/game.uil.json').symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        replay.inspect_bundle(bundle)
    (bundle / 'uil/game.uil.json').unlink()
    (bundle / 'uil/game.uil.json').write_bytes(outside.read_bytes())
    actual = bundle / 'real-lock.json'
    actual.write_bytes((bundle / 'replay.json').read_bytes())
    (bundle / 'replay.json').unlink()
    (bundle / 'replay.json').symlink_to(actual)
    for argument in (bundle, bundle / 'replay.json'):
        with pytest.raises(ValueError):
            replay.inspect_bundle(argument)


def test_corrupt_payload_missing_module_and_bad_canonical_hash_fail(tmp_path):
    bundle, lock = authored_inspection_bundle(tmp_path)
    game = bundle / 'uil/game.uil.json'
    original = game.read_bytes()
    game.write_bytes(original + b' ')
    with pytest.raises(ValueError, match='changed replay payload'):
        replay.inspect_bundle(bundle)
    game.write_bytes(original)
    changed = copy.deepcopy(lock)
    del changed['modules']['audio']
    save_lock(bundle, changed)
    with pytest.raises(ValueError, match='Missing semantic UIL module'):
        replay.inspect_bundle(bundle)
    changed = copy.deepcopy(lock)
    changed['modules']['presentation']['canonical_sha256'] = '0' * 64
    save_lock(bundle, changed)
    with pytest.raises(ValueError, match='canonical'):
        replay.inspect_bundle(bundle)


def test_unregistered_recipe_and_stale_profile_refused(tmp_path):
    bundle, lock = authored_inspection_bundle(tmp_path)
    for change in ('recipe', 'profile'):
        changed = copy.deepcopy(lock)
        if change == 'recipe':
            changed['recipe']['id'] = 'unregistered-recipe'
        else:
            changed['profile'] = 'unregistered-profile'
        save_lock(bundle, changed)
        with pytest.raises(ValueError, match='recipe|Unsupported replay lock'):
            replay.inspect_bundle(bundle)


def test_output_inside_git_is_refused_before_source_inspection(tmp_path):
    (tmp_path / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='outside Git'):
        replay.write_bundle(tmp_path / 'missing.rom', tmp_path / 'output', cc65_root=tmp_path)
    assert not (tmp_path / 'output').exists()


@pytest.fixture(scope='module')
def real_inputs():
    rom, cc65 = os.environ.get('FDISBULL_MINIPLANETS_ROM'), os.environ.get('FDISBULL_CC65_ROOT')
    if not rom or not cc65:
        pytest.skip('requires explicit private REV04 ROM and trusted cc65 root')
    return Path(rom), Path(cc65)


@pytest.fixture(scope='module')
def real_bundle(tmp_path_factory, real_inputs):
    rom, cc65 = real_inputs
    root = tmp_path_factory.mktemp('genesis-replay')
    result = replay.write_bundle(rom, root / 'bundle', cc65_root=cc65)
    return root, result, rom, cc65


def test_real_bundle_replays_twice_to_exact_same_native_bytes(real_bundle, monkeypatch):
    from fdisbull import udc_nes_game
    root, initial, rom, cc65 = real_bundle
    original_run = udc_nes_game._run
    executed_tools = []
    def check_tool_origin(argv, work):
        binary = Path(argv[0]).resolve()
        assert not binary.is_relative_to((root / 'bundle').resolve())
        assert 'trusted-toolchain' in binary.parts
        executed_tools.append(binary.name)
        return original_run(argv, work)
    monkeypatch.setattr(udc_nes_game, '_run', check_tool_origin)
    assert initial['executed'] is False
    info = replay.inspect_bundle(root / 'bundle')
    assert info['payloads_intact'] and info['implementation_match'] and not info['executed']
    first = replay.replay_bundle(root / 'bundle', root / 'first', rom_path=rom, cc65_root=cc65)
    second = replay.replay_bundle(root / 'bundle/replay.json', root / 'second', rom_path=rom, cc65_root=cc65)
    assert first['rom_bytes_match'] and second['rom_bytes_match']
    assert first['inputs_unchanged'] and second['inputs_unchanged']
    assert not first['executed_bundle_code'] and not second['executed_bundle_code']
    assert first['native_execution'].startswith('not run')
    images = [(root / name / 'native/program.nes').read_bytes() for name in ('bundle', 'first', 'second')]
    assert images[0] == images[1] == images[2]
    assert first['rom_sha256'] == second['rom_sha256'] == initial['rom_sha256']
    assert initial['rom_sha256'] == '1cf6e29d02c991af6bc9a8ced6668adb2a91a81b6c2318770d27379afb751db0'
    assert {'cc65', 'ca65', 'ld65', 'od65'} <= set(executed_tools)


@pytest.mark.parametrize('module', ['game', 'audio', 'presentation', 'psg', 'scene'])
def test_rebound_module_tampering_is_refused_before_compilation(real_bundle, tmp_path, monkeypatch, module):
    """An attacker can recalculate hashes, but cannot rewrite the registered model."""
    from fdisbull import udc_nes_game
    root, _, rom, cc65 = real_bundle
    bundle = tmp_path / 'forged'
    shutil.copytree(root / 'bundle', bundle)
    lock = json.loads((bundle / 'replay.json').read_bytes())
    relative = lock['modules'][module]['path']
    payload = bundle / relative
    value = json.loads(payload.read_bytes())
    if module == 'game':
        value.setdefault('evidence', {})['forged_replay_test'] = 'not an authorized provenance claim'
    else:
        value['forged_replay_test'] = 'not the registered semantic module'
    raw = canonical(value) + b'\n'
    payload.chmod(0o600)
    payload.write_bytes(raw)
    lock['files'][relative] = record(raw)
    lock['modules'][module].update(record(raw))
    lock['modules'][module]['canonical_sha256'] = hashlib.sha256(canonical(value)).hexdigest()
    save_lock(bundle, lock)
    assert replay.inspect_bundle(bundle)['payloads_intact']  # Hashes alone are not semantic authenticity.
    invoked = []
    def forbidden(*args, **kwargs):
        invoked.append(True)
        raise AssertionError('compiler reached before semantic mismatch was rejected')
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', forbidden)
    with pytest.raises(ValueError, match='registered source/model'):
        replay.replay_bundle(bundle, tmp_path / 'out', rom_path=rom, cc65_root=cc65)
    assert not invoked and not (tmp_path / 'out').exists()


def test_changed_rom_is_refused_before_compilation(real_bundle, tmp_path, monkeypatch):
    from fdisbull import udc_nes_game
    root, _, rom, cc65 = real_bundle
    changed = bytearray(rom.read_bytes())
    changed[-1] ^= 1
    path = tmp_path / 'changed-rom.bin'
    path.write_bytes(changed)
    invoked = []
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', lambda *a, **k: invoked.append(True))
    with pytest.raises(ValueError, match='ROM identity'):
        replay.replay_bundle(root / 'bundle', tmp_path / 'out', rom_path=path, cc65_root=cc65)
    assert not invoked and not (tmp_path / 'out').exists()


def test_missing_and_mismatched_explicit_tools_fail_before_compilation(real_bundle, tmp_path, monkeypatch):
    from fdisbull import udc_nes_game
    root, _, rom, cc65 = real_bundle
    tools = tmp_path / 'trusted-tools'
    tools.mkdir()
    invoked = []
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', lambda *a, **k: invoked.append(True))
    with pytest.raises(ValueError, match='missing'):
        replay.replay_bundle(root / 'bundle', tmp_path / 'missing-out', rom_path=rom, cc65_root=tools)
    assert not invoked and not (tmp_path / 'missing-out').exists()
    lock = json.loads((root / 'bundle/replay.json').read_bytes())
    for rel in lock['toolchain']:
        src = cc65 / rel
        dst = tools / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    with (tools / 'bin/ca65').open('ab') as output:
        output.write(b'changed')
    with pytest.raises(ValueError, match='toolchain differs'):
        replay.replay_bundle(root / 'bundle', tmp_path / 'mismatch-out', rom_path=rom, cc65_root=tools)
    assert not invoked and not (tmp_path / 'mismatch-out').exists()


@pytest.mark.parametrize('category', ['engine', 'toolchain'])
def test_real_bundle_captured_inputs_cannot_be_omitted_from_inventory(real_bundle, tmp_path, category):
    root, _, _, _ = real_bundle
    bundle = tmp_path / 'incomplete'
    shutil.copytree(root / 'bundle', bundle)
    lock = json.loads((bundle / 'replay.json').read_bytes())
    prefix = 'captured/' + category + '/'
    relative = next(name for name in lock['files'] if name.startswith(prefix))
    del lock['files'][relative]
    (bundle / relative).unlink()
    save_lock(bundle, lock)
    with pytest.raises(ValueError):
        replay.inspect_bundle(bundle)


def test_tool_changed_after_capture_builds_from_captured_bytes(real_inputs, tmp_path, monkeypatch):
    """A private test tool changes after capture; no profile identity is mocked."""
    rom, cc65 = real_inputs
    private_tools = tmp_path / 'mutable-tool-source'
    for relative in replay.TOOL_INPUTS:
        src, dst = cc65 / relative, private_tools / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    original = (private_tools / 'bin/ca65').read_bytes()
    capture = replay._capture_tools
    called = []
    def capture_then_edit(trusted_root, destination):
        records = capture(trusted_root, destination)
        (private_tools / 'bin/ca65').write_bytes(original + b'after-capture')
        called.append(True)
        return records
    monkeypatch.setattr(replay, '_capture_tools', capture_then_edit)
    result = replay.write_bundle(rom, tmp_path / 'bundle', cc65_root=private_tools)
    assert called == [True]
    assert (private_tools / 'bin/ca65').read_bytes() != original
    assert (tmp_path / 'bundle/captured/toolchain/bin/ca65').read_bytes() == original
    lock = json.loads((tmp_path / 'bundle/replay.json').read_bytes())
    assert lock['toolchain']['bin/ca65'] == record(original)
    assert result['rom_sha256'] == '1cf6e29d02c991af6bc9a8ced6668adb2a91a81b6c2318770d27379afb751db0'


def test_reformatted_module_rebound_to_new_hash_is_not_replayable(real_bundle, tmp_path, monkeypatch):
    from fdisbull import udc_nes_game
    root, _, rom, cc65 = real_bundle
    bundle = tmp_path / 'noncanonical'
    shutil.copytree(root / 'bundle', bundle)
    lock = json.loads((bundle / 'replay.json').read_bytes())
    relative = lock['modules']['game']['path']
    path = bundle / relative
    value = json.loads(path.read_bytes())
    raw = json.dumps(value, indent=2).encode() + b'\n'
    assert raw != path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(raw)
    lock['files'][relative] = record(raw)
    lock['modules']['game'].update(record(raw))
    save_lock(bundle, lock)
    assert replay.inspect_bundle(bundle)['payloads_intact']
    called = []
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', lambda *a, **k: called.append(True))
    with pytest.raises(ValueError, match='registered source/model'):
        replay.replay_bundle(bundle, tmp_path / 'out', rom_path=rom, cc65_root=cc65)
    assert not called and not (tmp_path / 'out').exists()


@pytest.mark.parametrize('relative,mode', [('lib/nes.lib', 'missing'),
                                           ('asminc/longbranch.mac', 'missing'),
                                           ('lib/nes.lib', 'changed'),
                                           ('asminc/longbranch.mac', 'changed')])
def test_missing_or_changed_runtime_and_assembler_input_refused(real_bundle, tmp_path, monkeypatch, relative, mode):
    from fdisbull import udc_nes_game
    root, _, rom, cc65 = real_bundle
    tools = tmp_path / 'tools'
    for name in replay.TOOL_INPUTS:
        if name == relative and mode == 'missing':
            continue
        source, target = cc65 / name, tools / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if mode == 'changed':
        with (tools / relative).open('ab') as output:
            output.write(b'changed')
    called = []
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', lambda *a, **k: called.append(True))
    with pytest.raises(ValueError, match='missing|toolchain differs'):
        replay.replay_bundle(root / 'bundle', tmp_path / 'out', rom_path=rom, cc65_root=tools)
    assert not called and not (tmp_path / 'out').exists()


def test_source_changed_during_preflight_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'unknown.rom'
    source.write_bytes(bytes(0x200))
    real_read = Path.read_bytes
    calls = []
    def read_then_edit(path):
        data = real_read(path)
        if path == source and not calls:
            calls.append(True)
            path.write_bytes(b'changed while preflight was reading')
        return data
    monkeypatch.setattr(Path, 'read_bytes', read_then_edit)
    with pytest.raises(ValueError, match='changed during preflight'):
        replay.inspect_source(source)
    assert calls == [True]


def test_implementation_drift_after_initial_capture_refuses_publish(real_inputs, tmp_path, monkeypatch):
    """Simulate a later implementation read changing; never accept forged identity."""
    from fdisbull import udc_nes_game
    rom, cc65 = real_inputs
    real_engine_bytes = replay._engine_bytes
    calls = []
    def drifted_engine():
        value = real_engine_bytes()
        calls.append(True)
        if len(calls) > 1:
            value['game_sources/nes_display_fast.s'] += b'\n; changed after capture\n'
        return value
    monkeypatch.setattr(replay, '_engine_bytes', drifted_engine)
    compiled = []
    monkeypatch.setattr(udc_nes_game, 'build_nes_game', lambda *a, **k: compiled.append(True))
    with pytest.raises(ValueError, match='implementation differs'):
        replay.write_bundle(rom, tmp_path / 'out', cc65_root=cc65)
    assert len(calls) >= 2 and not compiled and not (tmp_path / 'out').exists()


def test_mixed_qualified_recipe_preserves_selection_on_replay(real_inputs, tmp_path):
    rom, cc65 = real_inputs
    selection = {'run_objects': 'baseline'}
    built = replay.write_bundle(rom, tmp_path / 'bundle', cc65_root=cc65,
                                procedures=selection)
    info = replay.inspect_bundle(tmp_path / 'bundle')
    assert info['recipe']['procedures'] == selection
    assert info['recipe']['variant'] == 'efficient'
    replayed = replay.replay_bundle(tmp_path / 'bundle', tmp_path / 'out',
                                    rom_path=rom, cc65_root=cc65)
    assert replayed['rom_bytes_match']
    assert replayed['rom_sha256'] == built['rom_sha256']
    assert (tmp_path / 'bundle/native/program.nes').read_bytes() == (tmp_path / 'out/native/program.nes').read_bytes()


def test_unregistered_mixed_procedure_never_publishes(real_inputs, tmp_path):
    rom, cc65 = real_inputs
    with pytest.raises(ValueError, match='Unknown game procedure|unqualified'):
        replay.write_bundle(rom, tmp_path / 'bundle', cc65_root=cc65,
                            procedures={'does_not_exist': 'baseline'})
    assert not (tmp_path / 'bundle').exists()


def test_packaged_semantic_references_are_in_engine_capture():
    captured = replay._engine_bytes()
    assert 'data/miniplanets_presentation.uil.json' in captured
    assert 'data/miniplanets_psg.uil.json' in captured
