"""Safety and distribution checks for RFC 0001 authored fixtures."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / 'docs/uil-rfcs/0001'
EXAMPLE_NAMES = {
    'README.md',
    'check_examples.py',
    'commit.js',
    'commit.py',
    'commit.rs',
    'native-observation.json',
    'native_probe.py',
    'source-definition-observation.json',
    'vectors.json',
}
EXAMPLE_PATHS = {f'docs/uil-rfcs/0001/{name}' for name in EXAMPLE_NAMES}


def test_example_scripts_have_no_optimization_stripped_assertions():
    for name in ('check_examples.py', 'native_probe.py'):
        tree = ast.parse((EXAMPLE_DIR / name).read_text())
        assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree)), name


def test_release_archive_uses_exact_example_allowlist(tmp_path):
    import runpy

    build = runpy.run_path(str(ROOT / 'scripts/build_release.py'))
    selected = {path.relative_to(ROOT).as_posix() for path in build['release_files'](ROOT)}
    example_selected = {path for path in selected if path.startswith('docs/uil-rfcs/0001/')}
    assert example_selected == EXAMPLE_PATHS

    manifest_lines = (ROOT / 'MANIFEST.in').read_text().splitlines()
    assert 'prune docs/uil-rfcs/0001' in manifest_lines
    manifest_examples = {
        line.removeprefix('include ')
        for line in manifest_lines
        if line.startswith('include docs/uil-rfcs/0001/')
    }
    assert manifest_examples == EXAMPLE_PATHS

    # Exercise the release selector against a synthetic tree containing
    # unlisted game/state-looking additions in the fixture directory.
    scratch = tmp_path / 'source'
    for name in build['ROOT_FILES']:
        path = scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('placeholder')
    for name in build['DOC_EXAMPLE_FILES']:
        path = scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('placeholder')
    (scratch / 'docs/uil-rfcs/0001/GAME.EXE').write_bytes(b'fixture only')
    (scratch / 'docs/uil-rfcs/0001/checkpoint.sav').write_bytes(b'fixture only')
    (scratch / 'docs/uil-rfcs/0001/unlisted.json').write_text('{}')
    (scratch / 'docs/uil-rfcs/0001/unlisted.md').write_text('not on the authored allowlist')
    scratch_selected = {
        path.relative_to(scratch).as_posix()
        for path in build['release_files'](scratch)
    }
    assert EXAMPLE_PATHS <= scratch_selected
    assert not any(path.endswith(('GAME.EXE', 'checkpoint.sav', 'unlisted.json', 'unlisted.md'))
                   for path in scratch_selected)
    assert {path for path in scratch_selected if path.startswith('docs/uil-rfcs/0001/')} == EXAMPLE_PATHS


@pytest.mark.skipif(not shutil.which('rustc') or not shutil.which('node'),
                    reason='the authored checker requires already installed Rust and Node')
def test_example_checker_rejects_bad_vector_under_python_optimized(tmp_path):
    scratch = tmp_path / 'source'
    examples = scratch / 'docs/uil-rfcs/0001'
    examples.mkdir(parents=True)
    for name in ('check_examples.py', 'commit.py', 'commit.js', 'commit.rs', 'vectors.json'):
        shutil.copyfile(EXAMPLE_DIR / name, examples / name)
    il = scratch / 'src/fdisbull/interaction_il.py'
    il.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'src/fdisbull/interaction_il.py', il)

    vectors_path = examples / 'vectors.json'
    vectors = json.loads(vectors_path.read_text())
    vectors['cases'][0]['after'][0] = '999999'
    vectors_path.write_text(json.dumps(vectors))
    output = tmp_path / 'checker-output'
    result = subprocess.run(
        [sys.executable, '-O', '-B', str(examples / 'check_examples.py'),
         '--output', str(output)],
        cwd=scratch, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert 'pass-through result or input immutability check failed' in result.stderr
    assert not (output / 'receipt.json').exists()


def test_native_probe_rejects_wrong_executable_hash_under_python_optimized(tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    (game / 'DINOPARK.EXE').write_bytes(b'not the qualified executable')
    project = tmp_path / 'project.fdb'
    project.write_bytes(b'placeholder; validation must stop before opening this')
    backend = tmp_path / 'backend'
    backend.write_bytes(b'not the qualified backend')
    output = tmp_path / 'derived-output'
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, '-O', '-B', str(EXAMPLE_DIR / 'native_probe.py'),
         '--project', str(project), '--game-dir', str(game),
         '--backend', str(backend), '--output', str(output)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert 'captured DINOPARK.EXE hash does not match' in result.stderr
    assert not output.exists()
