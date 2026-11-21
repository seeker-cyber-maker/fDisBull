"""Shared checkout inputs become complete standalone wheel/sdist/kit payloads."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BASE_NAMES = ('headless-agent.patch', 'source-manifest.json', 'COPYING')


def _build(source, destination, kind):
    destination.mkdir()
    code = ('from setuptools import build_meta; import sys; '
            "print(getattr(build_meta, 'build_' + sys.argv[1])(sys.argv[2]))")
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    environment.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-c', code, kind, str(destination)],
                            cwd=source, env=environment, capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    outputs = list(destination.iterdir())
    assert len(outputs) == 1, outputs
    return outputs[0]


def _wheel_resources(path):
    prefix = 'dotbox/resources/'
    with zipfile.ZipFile(path) as archive:
        return {name.removeprefix(prefix): archive.read(name)
                for name in archive.namelist() if name.startswith(prefix)}


def test_direct_and_sdist_wheels_keep_complete_standalone_native_resources(tmp_path):
    combined = tmp_path / 'combined'
    product = combined / 'apps/dotbox'
    shutil.copytree(ROOT, product, ignore=shutil.ignore_patterns(
        '.git', '.pytest_cache', '__pycache__', '*.pyc', '*.egg-info', 'build', 'dist'))
    (combined / 'pyproject.toml').write_text('[project]\nname = "fdisbull"\n')
    canonical = combined / 'experimental/dosbox-x'
    canonical.mkdir(parents=True)
    expected = {}
    for name in BASE_NAMES:
        source = ROOT / 'native/dosbox-x' / name
        if not source.is_file():
            source = ROOT.parents[1] / 'experimental/dosbox-x' / name
        expected[name] = source.read_bytes()
        (canonical / name).write_bytes(expected[name])
        (product / 'native/dosbox-x' / name).unlink(missing_ok=True)
        assert not (product / 'native/dosbox-x' / name).exists()

    direct = _build(product, tmp_path / 'direct', 'wheel')
    archive = _build(product, tmp_path / 'sdist', 'sdist')
    standalone = tmp_path / 'standalone'
    standalone.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(standalone, filter='data')
    unpacked, = standalone.iterdir()
    inventory = (unpacked / 'src/dotbox.egg-info/SOURCES.txt').read_text().splitlines()
    for name, payload in expected.items():
        logical = 'native/dosbox-x/' + name
        assert (unpacked / logical).read_bytes() == payload
        assert inventory.count(logical) == 1
        assert not (product / logical).exists()
    assert not (unpacked / '.git').exists()

    rebuilt = _build(unpacked, tmp_path / 'rebuilt', 'wheel')
    payloads = _wheel_resources(rebuilt)
    assert _wheel_resources(direct) == payloads
    for name, payload in expected.items():
        assert payloads['native/dosbox-x/' + name] == payload

    # Import only the wheel and stdlib, with neither application installed.
    exported = tmp_path / 'exported-kit'
    code = ('import sys; sys.path.insert(0, sys.argv[1]); '
            'from dotbox.kit import export_resources; export_resources(sys.argv[2])')
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code,
                             str(rebuilt), str(exported)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    code = ("import runpy, sys; module = runpy.run_path(sys.argv[1]); "
            "print(len(module['load_recipe']()['result_files']))")
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code,
                             str(exported / 'native/prepare_source.py')], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == '38'
