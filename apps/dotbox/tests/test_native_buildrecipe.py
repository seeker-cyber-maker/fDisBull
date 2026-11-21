"""Standalone native preparation uses DotBox-owned inputs and immutable Git source."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'native'


def _preparer():
    spec = importlib.util.spec_from_file_location('dotbox_native_preparation', NATIVE / 'prepare_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(payload):
    return hashlib.sha256(payload).hexdigest()


def _git(repository, *args):
    return subprocess.run(['git', '-C', str(repository), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _tiny_recipe(tmp_path):
    """Two authored source patches exercise the real export/apply/verify path."""
    repository = tmp_path / 'upstream'
    repository.mkdir()
    _git(repository, 'init')
    (repository / 'src').mkdir()
    (repository / 'src/control.cpp').write_bytes(b'upstream\n')
    _git(repository, 'add', '.')
    _git(repository, '-c', 'user.name=DotBox native test', '-c', 'user.email=test@example.invalid',
         'commit', '-m', 'Authored native preparation fixture')
    resources = tmp_path / 'resources'
    (resources / 'dosbox-x').mkdir(parents=True)
    (resources / 'dosbox-x/headless-agent.patch').write_text(
        '--- a/src/control.cpp\n+++ b/src/control.cpp\n@@ -1 +1 @@\n-upstream\n+base\n')
    (resources / 'input-control.patch').write_text(
        '--- a/src/control.cpp\n+++ b/src/control.cpp\n@@ -1 +1 @@\n-base\n+cooperative\n')
    base_hash = _hash((resources / 'dosbox-x/headless-agent.patch').read_bytes())
    overlay_hash = _hash((resources / 'input-control.patch').read_bytes())
    commit = _git(repository, 'rev-parse', 'HEAD')
    base = {'baseline_commit': commit, 'patch_sha256': base_hash,
            'source_files': [{'path': 'src/control.cpp', 'sha256': _hash(b'base\n'), 'size': 5}]}
    overlay = {'upstream_commit': commit, 'fdisbull_patch_sha256': base_hash,
               'overlay_sha256': overlay_hash, 'base_files': {'src/control.cpp': _hash(b'base\n')},
               'result_files': {'src/control.cpp': _hash(b'cooperative\n')}}
    (resources / 'dosbox-x/source-manifest.json').write_text(json.dumps(base))
    (resources / 'manifest.json').write_text(json.dumps(overlay))
    recipe = {'format': 'dotbox-native-source-1',
              'upstream': {'commit': commit, 'tree': _git(repository, 'rev-parse', 'HEAD^{tree}')},
              'base_provenance': {'patch_sha256': base_hash},
              'inputs': {str(path.relative_to(resources)): _hash(path.read_bytes())
                         for path in resources.rglob('*') if path.is_file()},
              'result_files': overlay['result_files']}
    (resources / 'build-recipe.json').write_text(json.dumps(recipe))
    return repository, resources


def test_recipe_is_bound_to_dotbox_owned_source_and_notices():
    recipe = _preparer().load_recipe()
    assert recipe['upstream']['commit'] == '029bd65c5dcc7cdc7f2e14e35278620d9707d969'
    assert recipe['base_provenance']['commit'] == 'ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9'
    assert len(recipe['result_files']) == 38
    assert '--enable-dosbox_agent' in recipe['build']['commands'][1]
    assert '--enable-debug=heavy' in recipe['build']['commands'][1]
    assert '--enable-sdl2' in recipe['build']['commands'][1]
    path = _preparer()._input_path
    assert 'GNU GENERAL PUBLIC LICENSE' in path(NATIVE, 'dosbox-x/COPYING').read_text()
    patch_paths = {line.removeprefix('+++ b/') for line in
                   path(NATIVE, 'dosbox-x/headless-agent.patch').read_text().splitlines()
                   if line.startswith('+++ b/')}
    base = json.loads(path(NATIVE, 'dosbox-x/source-manifest.json').read_text())
    assert patch_paths == {entry['path'] for entry in base['source_files']}


def test_preparation_exports_immutable_commit_and_repeats_without_mutation(tmp_path):
    repository, resources = _tiny_recipe(tmp_path)
    (repository / 'src/control.cpp').write_bytes(b'unrelated active work\n')
    output = tmp_path / 'prepared'
    app = _preparer()
    result = app.prepare_source(output, upstream=repository, resource_root=resources)
    assert result['status'] == 'prepared' and result['native_build_performed'] is False
    assert (output / 'src/control.cpp').read_bytes() == b'cooperative\n'
    assert not (output / '.git').exists()
    assert (repository / 'src/control.cpp').read_bytes() == b'unrelated active work\n'
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in output.rglob('*') if path.is_file()}
    assert app.prepare_source(output, upstream=repository, resource_root=resources)['status'] == 'already_prepared'
    assert app.verify_source(output, resource_root=resources)['status'] == 'verified'
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}


def _combined_recipe(tmp_path):
    repository, resources = _tiny_recipe(tmp_path)
    combined = tmp_path / 'combined'
    native = combined / 'apps/dotbox/native'
    native.parent.mkdir(parents=True)
    resources.rename(native)
    (combined / 'pyproject.toml').write_text('[project]\nname = "fdisbull"\n')
    base = combined / 'experimental/dosbox-x'
    base.mkdir(parents=True)
    for name in ('headless-agent.patch', 'source-manifest.json'):
        (native / 'dosbox-x' / name).rename(base / name)
    return repository, native, base


def test_combined_source_preparation_uses_canonical_base_without_copying_it(tmp_path):
    repository, native, base = _combined_recipe(tmp_path)
    output = tmp_path / 'prepared'
    result = _preparer().prepare_source(output, upstream=repository, resource_root=native)
    assert result['status'] == 'prepared'
    assert (output / 'src/control.cpp').read_bytes() == b'cooperative\n'
    assert not (native / 'dosbox-x/headless-agent.patch').exists()
    assert (base / 'headless-agent.patch').is_file()


@pytest.mark.parametrize('alteration', ['changed', 'missing', 'symlink', 'unrecognized_repository'])
def test_combined_source_refuses_invalid_base_before_creating_output(tmp_path, alteration):
    repository, native, base = _combined_recipe(tmp_path)
    patch = base / 'headless-agent.patch'
    if alteration == 'changed':
        patch.write_bytes(patch.read_bytes() + b'\nchanged')
    elif alteration == 'missing':
        patch.unlink()
    elif alteration == 'symlink':
        target = tmp_path / 'redirected.patch'
        patch.rename(target)
        patch.symlink_to(target)
    else:
        (base.parents[1] / 'pyproject.toml').write_text('[project]\nname = "another-product"\n')
    output = tmp_path / 'refused'
    with pytest.raises(ValueError):
        _preparer().prepare_source(output, upstream=repository, resource_root=native)
    assert not output.exists()
    assert not list(tmp_path.glob('.refused-*'))


def test_invalid_bundled_base_is_not_replaced_by_valid_canonical_input(tmp_path):
    repository, native, base = _combined_recipe(tmp_path)
    (native / 'dosbox-x/headless-agent.patch').write_bytes(b'damaged local input')
    output = tmp_path / 'refused'
    with pytest.raises(ValueError, match='hash mismatch'):
        _preparer().prepare_source(output, upstream=repository, resource_root=native)
    assert not output.exists()
    assert (base / 'headless-agent.patch').is_file()


def test_preparation_rejects_damaged_inputs_before_output(tmp_path):
    repository, resources = _tiny_recipe(tmp_path)
    (resources / 'input-control.patch').write_text('damaged patch\n')
    output = tmp_path / 'prepared'
    with pytest.raises(ValueError, match='hash mismatch: input-control.patch'):
        _preparer().prepare_source(output, upstream=repository, resource_root=resources)
    assert not output.exists()
    assert not list(tmp_path.glob('.prepared-*'))


def test_preparation_preserves_conflicting_output_and_rejects_changed_source(tmp_path):
    repository, resources = _tiny_recipe(tmp_path)
    output = tmp_path / 'prepared'
    output.mkdir()
    (output / 'keep').write_text('user work')
    with pytest.raises(ValueError, match='hash mismatch'):
        _preparer().prepare_source(output, upstream=repository, resource_root=resources)
    assert (output / 'keep').read_text() == 'user work'
    shutil.rmtree(output)
    app = _preparer()
    app.prepare_source(output, upstream=repository, resource_root=resources)
    (output / 'src/control.cpp').write_bytes(b'changed after preparation\n')
    with pytest.raises(ValueError, match='hash mismatch: src/control.cpp'):
        app.verify_source(output, resource_root=resources)


def test_preparation_rejects_wrong_upstream_without_publishing_partial_tree(tmp_path):
    repository, resources = _tiny_recipe(tmp_path)
    recipe = json.loads((resources / 'build-recipe.json').read_text())
    recipe['upstream']['tree'] = '0' * 40
    (resources / 'build-recipe.json').write_text(json.dumps(recipe))
    with pytest.raises(ValueError, match='pinned commit and tree'):
        _preparer().prepare_source(tmp_path / 'prepared', upstream=repository, resource_root=resources)
    assert not (tmp_path / 'prepared').exists()
    assert not list(tmp_path.glob('.prepared-*'))
