"""Release preparation refuses mismatched source and incomplete trust/readiness."""
from pathlib import Path
import runpy
import subprocess

import pytest

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_pypi_release.py'))


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def release(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Release Test')
    git(tmp_path, 'config', 'user.email', 'release-test@example.invalid')
    (tmp_path/'player').mkdir()
    (tmp_path/'src/fdisbull').mkdir(parents=True)
    for manifest in ('pyproject.toml', 'player/pyproject.toml'):
        (tmp_path/manifest).write_text('[project]\nversion = "1.2.3"\n')
    (tmp_path/'src/fdisbull/__init__.py').write_text('__version__ = "1.2.3"\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'Test release source')
    sha = git(tmp_path, 'rev-parse', 'HEAD')
    git(tmp_path, 'update-ref', 'refs/remotes/origin/main', sha)
    git(tmp_path, 'tag', 'v1.2.3')
    return tmp_path, sha


def test_source_requires_exact_head_tag_and_all_versions(release):
    root, sha = release
    assert CHECK['check_source'](root, 'v1.2.3', sha) == '1.2.3'
    for manifest in ('pyproject.toml', 'player/pyproject.toml', 'src/fdisbull/__init__.py'):
        original = (root/manifest).read_text()
        (root/manifest).write_text(original.replace('1.2.3', '1.2.4'))
        with pytest.raises(ValueError, match='version mismatch'):
            CHECK['check_source'](root, 'v1.2.3', sha)
        (root/manifest).write_text(original)
    with pytest.raises(ValueError, match='source does not match'):
        CHECK['check_source'](root, 'v1.2.3', '0'*40)
    git(root, 'commit', '--allow-empty', '-qm', 'Other source')
    newer = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='Tag does not match'):
        CHECK['check_source'](root, 'v1.2.3', newer)


@pytest.mark.parametrize('tag', ['main', '--help', 'v1.2.3rc1', 'v1.2', 'v1.2.3;echo nope'])
def test_source_rejects_arbitrary_refs(release, tag):
    root, sha = release
    with pytest.raises(ValueError, match='stable'):
        CHECK['check_source'](root, tag, sha)


def test_source_must_be_on_main_history(release):
    root, sha = release
    git(root, 'checkout', '--orphan', 'unrelated')
    git(root, 'commit', '-qm', 'Unrelated main')
    git(root, 'update-ref', 'refs/remotes/origin/main', git(root, 'rev-parse', 'HEAD'))
    git(root, 'checkout', '--detach', sha)
    with pytest.raises(subprocess.CalledProcessError):
        CHECK['check_source'](root, 'v1.2.3', sha)


def test_source_rejects_uncommitted_build_inputs(release):
    root, sha = release
    (root/'unreviewed.py').write_text('raise RuntimeError("unreviewed")\n')
    with pytest.raises(ValueError, match='clean checkout'):
        CHECK['check_source'](root, 'v1.2.3', sha)


@pytest.mark.parametrize('enabled,ready', [('', ''), ('true', ''), ('', 'true'), ('false', 'true')])
def test_publication_is_disabled_until_explicitly_ready(release, enabled, ready):
    with pytest.raises(ValueError, match='Publication disabled'):
        CHECK['check_license'](release[0], enabled, ready)


def test_readiness_also_requires_both_license_metadata_fields(release):
    root, _ = release
    for manifest in ('pyproject.toml', 'player/pyproject.toml'):
        with pytest.raises(ValueError, match='License metadata'):
            CHECK['check_license'](root, 'true', 'true')
        with (root/manifest).open('a') as stream:
            stream.write('license = "LicenseRef-Owner-Approved"\n')
    CHECK['check_license'](root, 'true', 'true')


def run(**changes):
    return {'id': 100, 'head_sha': 'a'*40, 'event': 'push', 'status': 'completed',
            'conclusion': 'success', 'path': '.github/workflows/ci.yml',
            'head_repository': {'full_name': 'seeker-cyber-maker/fDisBull'}, **changes}


@pytest.mark.parametrize('change', [dict(head_sha='b'*40), dict(event='pull_request'),
                                    dict(status='in_progress'), dict(conclusion='failure'),
                                    dict(path='.github/workflows/other.yml'),
                                    dict(head_repository={'full_name': 'other/fDisBull'})])
def test_ci_requires_trusted_success_on_the_exact_sha(change):
    with pytest.raises(ValueError, match='Latest trusted'):
        CHECK['successful_run']([run(**change)], 'a'*40, 'ci.yml')


def test_ci_uses_latest_eligible_run():
    assert CHECK['successful_run']([run()], 'a'*40, 'ci.yml')['id'] == 100
    with pytest.raises(ValueError, match='Latest trusted'):
        CHECK['successful_run']([run(), run(id=101, conclusion='failure')], 'a'*40, 'ci.yml')
    assert CHECK['successful_run']([run(), run(id=101, event='pull_request')], 'a'*40, 'ci.yml')['id'] == 100
