import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tarfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(ROOT / 'scripts/build_dosbox_source_companion.py'))['build']


def test_companion_notice_uses_project_version(tmp_path):
    source = tmp_path / 'upstream'
    source.mkdir()
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    (source / 'source.c').write_text('original\n')
    subprocess.run(['git', '-C', str(source), 'add', 'source.c'], check=True)
    subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c',
                    'user.email=test@example.invalid', 'commit', '-qm', 'baseline'], check=True)
    baseline = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    patched = b'patched\n'
    (source / 'source.c').write_bytes(patched)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'baseline_commit': baseline, 'patch_sha256': 'a' * 64,
                                    'source_files': [{'path': 'source.c', 'sha256': hashlib.sha256(patched).hexdigest()}]}))
    output = tmp_path / 'companion.tar'
    build(source, manifest, 'b' * 40, output)
    with tarfile.open(output) as archive:
        notice = archive.extractfile('source-companion/README.txt').read().decode()
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    assert notice.startswith(f'DOSBox-X corresponding source for fDisBull {version}\n')
