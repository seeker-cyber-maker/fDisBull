"""Offline source transport uses authored Git fixtures, never a network remote."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('offline_local_ci', ROOT / 'scripts/ci/local-linux.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def git(path, *args):
    env = {'PATH': os.environ['PATH'], 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}
    return subprocess.check_output(['git', '-C', str(path), *args], env=env, text=True,
                                   stderr=subprocess.PIPE).strip()


@pytest.fixture
def archive_fixture(tmp_path):
    source, bare = tmp_path / 'source', tmp_path / 'bare'
    source.mkdir()
    bare.mkdir()
    git(source, 'init', '-b', 'fixture')
    (source / 'authored.txt').write_text('authored offline upstream\n')
    git(source, 'add', 'authored.txt')
    git(source, '-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-m', 'authored source')
    pin = git(source, 'rev-parse', 'HEAD')
    git(bare, 'init', '--bare')
    git(bare, 'fetch', '--depth', '1', str(source), pin + ':refs/heads/upstream')
    git(bare, 'symbolic-ref', 'HEAD', 'refs/heads/upstream')
    path = tmp_path / 'upstream.tar'
    with tarfile.open(path, 'w') as archive:
        for name in ('HEAD', 'config', 'objects', 'refs', 'shallow'):
            archive.add(bare / name, arcname='dosbox-x.git/' + name)
    return path, pin, hashlib.sha256(path.read_bytes()).hexdigest()


def test_checked_archive_is_staged_with_original_identity(archive_fixture, tmp_path, monkeypatch):
    path, pin, digest = archive_fixture
    monkeypatch.setattr(runner, 'DOSBOX_UPSTREAM_COMMIT', pin)
    result = runner.stage_upstream_archive(path, digest, tmp_path / 'work')
    assert result['upstream_commit'] == pin
    assert result['archive_sha256'] == digest
    assert (tmp_path / 'work' / runner.DOSBOX_UPSTREAM_ARCHIVE).read_bytes() == path.read_bytes()


@pytest.mark.parametrize('defect', ['wrong-hash', 'wrong-ref', 'alternates', 'unsafe-config',
                                  'symlink', 'traversal', 'duplicate', 'missing-ref'])
def test_untrusted_source_archives_fail_closed(archive_fixture, tmp_path, defect):
    path, pin, digest = archive_fixture
    if defect == 'wrong-hash':
        digest = '0' * 64
    else:
        changed = tmp_path / 'changed.tar'
        with tarfile.open(path, 'r:') as original, tarfile.open(changed, 'w') as output:
            for member in original:
                if defect == 'missing-ref' and member.name == 'dosbox-x.git/refs/heads/upstream':
                    continue
                data = original.extractfile(member).read() if member.isfile() else None
                if defect == 'wrong-ref' and member.name == 'dosbox-x.git/refs/heads/upstream':
                    data = b'0' * 40 + b'\n'
                if defect == 'unsafe-config' and member.name == 'dosbox-x.git/config':
                    data = b'[core]\nrepositoryformatversion = 0\nbare = true\nfsmonitor = unsafe\n'
                if data is not None:
                    member.size = len(data)
                output.addfile(member, io.BytesIO(data) if data is not None else None)
            if defect in ('alternates', 'traversal', 'duplicate', 'symlink'):
                name = {'alternates': 'dosbox-x.git/objects/info/alternates',
                        'traversal': 'dosbox-x.git/../escape',
                        'duplicate': 'dosbox-x.git/HEAD', 'symlink': 'dosbox-x.git/linked'}[defect]
                member = tarfile.TarInfo(name)
                if defect == 'symlink':
                    member.type, member.linkname = tarfile.SYMTYPE, '/outside'
                    output.addfile(member)
                else:
                    member.size = 1
                    output.addfile(member, io.BytesIO(b'x'))
        path = changed
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        runner.upstream_archive_identity(path, digest, expected_commit=pin)


def test_local_native_plan_without_archive_stops_before_admission(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'source_identity', lambda path: ('a' * 40, 'fixture'))
    monkeypatch.setattr(runner, 'admit_destinations', lambda *args: pytest.fail('No worker or allocation expected'))
    with pytest.raises(ValueError, match='explicit pinned DOSBox upstream'):
        runner.execute(SimpleNamespace(source=tmp_path, profile='stable'))


def native_source_function():
    source = (ROOT / 'scripts/ci/native-debugger.sh').read_text()
    return source.split('prepare_dosbox_source() {', 1)[1].split('# End finite source-transport seam.', 1)[0]


def test_native_source_transport_fetches_only_the_verified_local_repository(archive_fixture, tmp_path):
    path, pin, digest = archive_fixture
    work = tmp_path / 'guest'
    (work / 'scripts/ci').mkdir(parents=True)
    shutil.copy2(ROOT / 'scripts/ci/local-linux.py', work / 'scripts/ci/local-linux.py')
    env = {'PATH': os.environ['PATH'], 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
           'FDISBULL_EXECUTION_ORIGIN': 'local-linux',
           'FDISBULL_DOSBOX_UPSTREAM_ARCHIVE': str(path), 'FDISBULL_DOSBOX_UPSTREAM_SHA256': digest,
           'PYTHONDONTWRITEBYTECODE': '1'}
    script = 'set -euo pipefail\nprepare_dosbox_source() {' + native_source_function() + '\nprepare_dosbox_source "$1"\n'
    subprocess.run(['bash', '-c', script, 'offline-fixture', pin], cwd=work, env=env,
                   check=True, capture_output=True, text=True, timeout=30)
    source = work / '.native/dosbox-x'
    assert git(source, 'rev-parse', 'HEAD') == pin
    assert git(source, 'remote', 'get-url', 'origin') == str(work / '.native/upstream/unpacked/dosbox-x.git')
    assert (source / 'authored.txt').read_text() == 'authored offline upstream\n'


def test_native_local_source_transport_refuses_network_fallback(tmp_path):
    env = {'PATH': os.environ['PATH'], 'FDISBULL_EXECUTION_ORIGIN': 'local-linux'}
    script = 'set -euo pipefail\nprepare_dosbox_source() {' + native_source_function() + '\nprepare_dosbox_source pinned\n'
    result = subprocess.run(['bash', '-c', script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'explicit verified offline upstream' in result.stderr
    assert not (tmp_path / '.native').exists()
