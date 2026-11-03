"""Fail-closed validation for an explicitly selected stable backend build."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

UPSTREAM = '029bd65c5dcc7cdc7f2e14e35278620d9707d969'
FLAGS = ['--enable-sdl2', '--enable-debug=heavy', '--enable-dosbox_agent',
         '--disable-avcodec', '--disable-libslirp', '--disable-libfluidsynth']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(directory, manifest_path, image_digest):
    directory = Path(directory)
    files = [directory / name for name in ('dosbox-x', 'build-identity.json', 'config.log',
                                            'build-manifest.json', 'build-process.json')]
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Missing or unsafe reuse input')
    binary, raw, config, old_manifest, process = files
    identity = json.loads(raw.read_text())
    if any(key in identity for key in ('build_source_commit', 'build_identity_sha256',
                                       'build_process_sha256', 'build_manifest_sha256',
                                       'build_config_sha256', 'build_image_digest')):
        raise ValueError('Original compiled build evidence required; reused build identity is not accepted')
    prior = json.loads(process.read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    sha = identity.get('source_commit')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid build source commit')
    if (prior.get('source_commit') != sha or prior.get('execution_origin') != 'local-linux'
            or prior.get('job_name') != 'native-debugger-stable'
            or prior.get('image_digest') != image_digest
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(image_digest))):
        raise ValueError('Build process identity or image mismatch')
    if (old_manifest.read_bytes() != Path(manifest_path).read_bytes()
            or manifest.get('baseline_commit') != UPSTREAM
            or identity.get('upstream_commit') != UPSTREAM
            or identity.get('profile') != 'experimental/dosbox-x'
            or identity.get('configure_flags') != FLAGS
            or identity.get('patch_sha256') != manifest.get('patch_sha256')
            or identity.get('backend_sha256') != digest(binary)):
        raise ValueError('Stable backend build identity or source manifest mismatch')
    with binary.open('rb') as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\x3e\x00':
        raise ValueError('Stable backend must be little-endian ELF64 x86-64')
    if not config.stat().st_size:
        raise ValueError('Build config log is empty')
    return {'build_source_commit': sha, 'build_identity_sha256': digest(raw),
            'build_process_sha256': digest(process), 'build_manifest_sha256': digest(old_manifest),
            'build_config_sha256': digest(config), 'build_image_digest': image_digest}


def main():
    directory, manifest, image, evidence, binary_output = map(Path, sys.argv[1:])
    provenance = verify(directory, manifest, str(image))
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ('build-identity.json', 'config.log', 'build-manifest.json', 'build-process.json'):
        shutil.copy2(directory / name, evidence / name)
    binary_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(directory / 'dosbox-x', binary_output)
    (evidence / 'reuse-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    main()
