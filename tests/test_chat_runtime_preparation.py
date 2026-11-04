"""Offline shared-base reconstruction; these tiny files are not native fixtures."""
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import shutil

import pytest

spec = importlib.util.spec_from_file_location('chat_runtimes', Path(__file__).parents[1] / 'scripts/prepare_chat_runtimes.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def setup_kit(tmp_path):
    root = tmp_path / 'kit'; root.mkdir()
    name = b'TRAILER!!!\0'
    fields = (1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name), 0)
    base = b'070701' + b''.join(f'{value:08x}'.encode() for value in fields) + name
    base += b'\0' * (-len(base) % 4)
    (root / 'base.xz').write_bytes(lzma.compress(base))
    dosbox = root / 'dosbox'
    dosbox.write_bytes(b'\x7fELF\x02\x01' + bytes(12) + b'\x3e\0' + bytes(44))
    (root / 'kernel').write_bytes(b'not an executable; reconstruction unit input')
    expanded = {'size': len(base), 'sha256': hashlib.sha256(base).hexdigest()}
    original = (root / 'base.xz').read_bytes()
    outputs = runtime.materialize(root / 'base.xz', tmp_path / 'producer', dosbox, expanded)
    assert (root / 'base.xz').read_bytes() == original
    recipe = {'schema': 'fdisbull-chat-runtime-recipe-v1', 'expanded_base': expanded,
              'resources': runtime.resource_identities(dosbox), 'outputs': outputs}
    (root / 'recipe.json').write_text(json.dumps(recipe))
    roles = {'runtime_base': 'base.xz', 'runtime_recipe': 'recipe.json', 'dosbox': 'dosbox', 'kernel': 'kernel'}
    entries = [{'role': role, 'destination': path, **runtime.identity(root / path)} for role, path in roles.items()]
    (root / 'MANIFEST.json').write_text(json.dumps({'files': entries}))
    return root, outputs


def test_relocation_reconstructs_identical_images_and_reuses_verified_cache(tmp_path, monkeypatch):
    root, expected = setup_kit(tmp_path)
    relocated = tmp_path / 'different extraction path'
    shutil.copytree(root, relocated)
    cache = tmp_path / 'another cache path'
    result = runtime.prepare(relocated, cache)
    assert {profile: runtime.identity(result[profile]) for profile in expected} == expected
    monkeypatch.setattr(runtime, 'materialize', lambda *args: pytest.fail('A valid cache was rebuilt'))
    assert runtime.prepare(relocated, cache) == result
    result['wine'].write_bytes(b'changed image')
    with pytest.raises(ValueError, match='hash/size'):
        runtime.prepare(relocated, cache)


def test_bad_base_fails_before_cache_is_created(tmp_path):
    root, _ = setup_kit(tmp_path)
    (root / 'base.xz').write_bytes(b'changed archive')
    cache = tmp_path / 'consumer'
    with pytest.raises(ValueError, match='input hash/size'):
        runtime.prepare(root, cache)
    assert not cache.exists()


def test_changed_installed_resources_and_partial_cache_refuse(tmp_path):
    root, _ = setup_kit(tmp_path)
    recipe = root / 'recipe.json'; value = json.loads(recipe.read_text())
    value['resources']['wine']['init'] = '0' * 64; recipe.write_text(json.dumps(value))
    manifest = root / 'MANIFEST.json'; content = json.loads(manifest.read_text())
    next(entry for entry in content['files'] if entry['role'] == 'runtime_recipe').update(runtime.identity(recipe))
    manifest.write_text(json.dumps(content))
    with pytest.raises(ValueError, match='Installed resources'):
        runtime.prepare(root, tmp_path / 'cache')
    with pytest.raises(ValueError, match='empty'):
        runtime.materialize(root / 'base.xz', tmp_path / 'producer', root / 'dosbox', value['expanded_base'])


def test_expanded_budget_is_enforced_and_cache_cannot_overlap_kit(tmp_path):
    root, _ = setup_kit(tmp_path)
    with pytest.raises(ValueError, match='separate'):
        runtime.prepare(root, root / 'cache')
    bad = {'size': 1, 'sha256': '0' * 64}
    with pytest.raises(ValueError, match='exceeds declared budget'):
        runtime.materialize(root / 'base.xz', tmp_path / 'small', root / 'dosbox', bad)


def test_expanded_runtime_rejects_declared_size_above_hard_ceiling(tmp_path):
    with pytest.raises(ValueError, match='Invalid expanded base identity'):
        runtime.materialize(tmp_path / 'unused', tmp_path / 'cache', tmp_path / 'dosbox',
                            {'size': runtime.MAX_EXPANDED_RUNTIME_BYTES + 1, 'sha256': '0' * 64})
    assert not (tmp_path / 'cache').exists()
