"""Guest export and source proof without starting a container service."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load('local_export', 'scripts/ci/export-local-artifacts.py')
runner = load('local_runner_guest', 'scripts/ci/local-linux.py')


def git(work, *args):
    return subprocess.run(['git', '-C', str(work), *args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


@pytest.fixture
def source(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    git(work, 'init', '-b', 'fixture')
    git(work, 'config', 'user.name', 'Fixture')
    git(work, 'config', 'user.email', 'fixture@example.invalid')
    (work / 'tracked').write_text('source')
    git(work, 'add', 'tracked')
    git(work, 'commit', '-m', 'fixture')
    return work, git(work, 'rev-parse', 'HEAD')


def test_guest_exports_selected_regular_evidence_and_records_clean_source(source, tmp_path):
    work, sha = source
    (work / 'dist').mkdir()
    (work / 'dist/core.whl').write_bytes(b'wheel')
    backend = work / '.native/backends/layers/dosbox-x'
    backend.parent.mkdir(parents=True)
    backend.write_bytes(b'authored executable fixture')
    backend.chmod(0o755)
    (work / 'private-game.exe').write_bytes(b'not selected')
    out = tmp_path / 'phase/exported'
    exporter.export(work, out, sha)
    assert (out / 'dist/core.whl').read_bytes() == b'wheel'
    assert (out / '.native/backends/layers/dosbox-x').stat().st_mode & 0o111 == 0o111
    assert not (out / 'private-game.exe').exists()
    assert json.loads((out.parent / 'source-postcheck.json').read_text()) == {
        'source_commit': sha, 'expected_source_commit': sha,
        'tracked_worktree_dirty': False, 'export_success': True}


def test_guest_export_fails_closed_for_dirty_source(source, tmp_path):
    work, sha = source
    (work / 'tracked').write_text('changed')
    out = tmp_path / 'phase/exported'
    out.parent.mkdir()
    with pytest.raises(ValueError, match='source changed'):
        exporter.export(work, out, sha)
    assert out.is_dir()
    proof = json.loads((out.parent / 'source-postcheck.json').read_text())
    assert proof['tracked_worktree_dirty'] is True and proof['export_success'] is True


def test_guest_export_rejects_selected_symlink(source, tmp_path):
    work, sha = source
    (work / 'dist').mkdir()
    (work / 'dist/core.whl').symlink_to(work / 'tracked')
    out = tmp_path / 'phase/exported'
    with pytest.raises(ValueError, match='Symlink'):
        exporter.export(work, out, sha)
    assert json.loads((out.parent / 'source-postcheck.json').read_text())['export_success'] is False


def test_guest_execution_uses_native_work_and_tmp_paths():
    env = runner.job_environment('ordinary', 'a' * 40, 'run', 'job')
    assert env['CI_PROJECT_DIR'] == '/work'
    assert env['CI_BUILDS_DIR'] == '/ci-builds'
    assert env['TMPDIR'] == '/ci-tmp'
    assert env['PIP_CACHE_DIR'] == '/ci-cache/pip'
    command = runner.job_command('ordinary')
    assert 'cp -a /source/. /work/' in command
    assert 'export-local-artifacts.py' in command
    assert subprocess.run(['bash', '-n', '-c', command]).returncode == 0


def test_host_requires_matching_guest_proof_and_successful_export(source, tmp_path):
    work, sha = source
    out = tmp_path / 'phase/exported'
    exporter.export(work, out, sha)
    assert runner.verify_guest_postcheck(out.parent, sha)['export_success'] is True
    proof = out.parent / 'source-postcheck.json'
    data = json.loads(proof.read_text())
    for key, value in [('source_commit', 'b' * 40), ('tracked_worktree_dirty', True),
                       ('export_success', False)]:
        changed = dict(data, **{key: value})
        proof.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            runner.verify_guest_postcheck(out.parent, sha)
    proof.unlink()
    with pytest.raises(ValueError):
        runner.verify_guest_postcheck(out.parent, sha)


def test_unified_uses_isolated_native_docker_and_pinned_amd64_child():
    image = {'image_reference': 'docker.io/library/python@sha256:' + 'a' * 64,
             'image_digest': 'sha256:' + 'b' * 64}
    env = runner.job_environment('unified-prepare', 'c' * 40, 'run', 'job')
    command = runner.unified_command(image, env)
    assert 'source /source/scripts/ci/local-docker.sh' in command
    assert 'linux/amd64' in command and '--network host' in command
    assert 'docker.io/library/python@sha256:' + 'b' * 64 in command
    assert 'FDISBULL_LOCAL_DOCKER=0' in command
    assert 'DOCKER_HOST=unix:///var/run/docker.sock' in command
    assert '/run/fdisbull-local-docker/docker.sock' in command
    assert 'src=/source,dst=/source,readonly' in command
    assert 'src=/run-data,dst=/run-data' in command
    assert '--privileged' not in command and '--cap-add' not in command
    assert subprocess.run(['bash', '-n', '-c', command]).returncode == 0


def test_image_identity_selects_amd64_and_arm64_variants():
    variant = lambda arch, digit: {'platform': {'architecture': arch, 'os': 'linux'},
                                   'digest': 'sha256:' + digit * 64}
    data = [{'configuration': {'name': 'docker.io/library/python:3.12-bookworm',
                               'descriptor': {'digest': 'sha256:' + 'a' * 64}},
             'variants': [variant('amd64', 'b'), variant('arm64', 'c')]}]
    assert runner.image_identity(data)['image_digest'] == 'sha256:' + 'b' * 64
    assert runner.image_identity(data, 'arm64')['image_digest'] == 'sha256:' + 'c' * 64
    with pytest.raises(ValueError, match='arm64'):
        runner.image_identity([dict(data[0], variants=data[0]['variants'][:1])], 'arm64')


def test_unified_export_selects_only_declared_runtime_inputs(source, tmp_path):
    work, sha = source
    expected = ['.native/pe/qemu-9.2.4/build/qemu-system-x86_64', '.native/pe/linux-amd64',
                '.native/pe/runtime.cpio.gz', '.native/pe/oracle.exe',
                '.native/pe/dos-runtime.cpio.gz', '.native/backends/layers/dosbox-x']
    for name in expected:
        p = work / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(name.encode())
    private = work / '.native/pe/private-game.exe'
    private.write_bytes(b'private')
    out = tmp_path / 'phase/exported'
    exporter.export(work, out, sha)
    assert all((out / name).is_file() for name in expected)
    assert not (out / '.native/pe/private-game.exe').exists()
