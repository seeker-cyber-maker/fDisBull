#!/usr/bin/env python3
"""Verify and install this offline DotBox bundle into a new private prefix."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys


BUNDLE = Path(__file__).absolute().parent


def checked_path(path):
    path = Path(path).expanduser().absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Symlink path refused: ' + str(path))
    return path


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def relative_name(name):
    if not isinstance(name, str) or '\\' in name:
        raise ValueError('Invalid inventory path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or str(path) != name:
        raise ValueError('Unsafe inventory path: ' + name)
    return name


def verify_bundle():
    checked_path(BUNDLE)
    if (BUNDLE / 'INCOMPLETE').exists():
        raise ValueError('Bundle is marked incomplete')
    checksums = {}
    for line in checked_path(BUNDLE / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('Invalid checksum record')
        name = relative_name(match[2])
        if name in checksums:
            raise ValueError('Duplicate checksum record: ' + name)
        checksums[name] = match[1]
    manifest_path = checked_path(BUNDLE / 'manifest.json')
    if checksums.get('manifest.json') != digest(manifest_path):
        raise ValueError('Manifest checksum mismatch')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 'dotbox-offline-release-1':
        raise ValueError('Unsupported release inventory')
    if manifest.get('target') != {'system': 'Linux', 'architecture': 'x86_64',
                                  'implementation': 'CPython', 'python_major_minor': [3, 12]}:
        raise ValueError('Unsupported release target')
    names = set()
    for item in manifest['files']:
        name = relative_name(item['path'])
        if name in names or name in ('manifest.json', 'SHA256SUMS'):
            raise ValueError('Duplicate/reserved inventory name: ' + name)
        names.add(name)
        path = checked_path(BUNDLE / name)
        if not path.is_file() or path.stat().st_size != item['bytes']:
            raise ValueError('Missing or wrong-sized bundle file: ' + name)
        if checksums.get(name) != item['sha256'] or digest(path) != item['sha256']:
            raise ValueError('Bundle checksum mismatch: ' + name)
        if item['mode'] not in (0o644, 0o755) or stat.S_IMODE(path.stat().st_mode) != item['mode']:
            raise ValueError('Unsupported or changed payload mode: ' + name)
    if set(checksums) != names | {'manifest.json'}:
        raise ValueError('Checksum inventory and manifest differ')
    # The reserved default installation tree is mutable and is not bundle input.
    for path in BUNDLE.rglob('*'):
        relative = path.relative_to(BUNDLE)
        if relative.parts[0] == 'install':
            continue
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise ValueError('Symlink or special file in bundle: ' + str(relative))
        if path.is_file() and relative.as_posix() not in names | {'manifest.json', 'SHA256SUMS'}:
            raise ValueError('Unlisted bundle file: ' + str(relative))
    required = {'dotbox', 'fdisbull-core', 'pillow', 'iced-x86'}
    wheels = manifest['wheels']
    if len(wheels) != 4 or {item['name'] for item in wheels} != required:
        raise ValueError('Expected exactly four pinned runtime wheels')
    lock = ''.join(f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n"
                   for item in sorted(wheels, key=lambda item: item['name']))
    if (BUNDLE / 'requirements.lock').read_text() != lock:
        raise ValueError('Requirements lock differs from the wheel inventory')
    for item in wheels:
        name = relative_name(item['path'])
        if not name.startswith('wheelhouse/') or name not in names or digest(BUNDLE / name) != item['sha256']:
            raise ValueError('Wheel identity differs from the payload inventory')
    return manifest, digest(manifest_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default=str(BUNDLE / 'install'),
                        help='new installation directory; an existing path is refused')
    parser.add_argument('--verify-only', action='store_true', help='check bundle hashes without installing')
    args = parser.parse_args(argv)
    prefix = None
    created = False
    try:
        manifest, manifest_hash = verify_bundle()
        if args.verify_only:
            print(json.dumps({'status': 'verified', 'manifest_sha256': manifest_hash,
                              'files': len(manifest['files'])}))
            return 0
        if (platform.system() != 'Linux' or platform.machine().lower() not in ('x86_64', 'amd64')
                or platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 12)):
            raise ValueError('This bundle requires Linux x86_64 and CPython 3.12')
        prefix = checked_path(args.prefix)
        if prefix.exists():
            raise ValueError('Installation prefix already exists; select a new directory: ' + str(prefix))
        if not prefix.parent.is_dir():
            raise ValueError('Installation parent directory must already exist')
        if prefix.is_relative_to(BUNDLE) and prefix != BUNDLE / 'install':
            raise ValueError('Use the reserved bundle/install path or a prefix outside the bundle')
        required = manifest['install_required_free_bytes']
        if type(required) is not int or required <= 0:
            raise ValueError('Invalid installation space estimate')
        free = shutil.disk_usage(prefix.parent).free
        if free < required:
            raise ValueError(f'Insufficient installation space: need {required} bytes, have {free}')
        prefix.mkdir(mode=0o700)
        created = True
        temporary = prefix / 'tmp'
        temporary.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith('PIP_') and key not in ('PYTHONPATH', 'PYTHONHOME')}
        environment.update(PYTHONNOUSERSITE='1', PIP_CONFIG_FILE=os.devnull,
                           PIP_NO_INDEX='1', PIP_REQUIRE_VIRTUALENV='1', TMPDIR=str(temporary))
        subprocess.run([sys.executable, '-I', '-m', 'venv', '--copies', str(prefix / 'venv')],
                       check=True, env=environment)
        python = prefix / 'venv/bin/python'
        command = [str(python), '-I', '-m', 'pip', '--disable-pip-version-check',
                   'install', '--no-index', '--no-cache-dir', '--only-binary=:all:',
                   '--find-links', str(BUNDLE / 'wheelhouse'), '--require-hashes',
                   '-r', str(BUNDLE / 'requirements.lock')]
        subprocess.run(command, check=True, env=environment)
        for name in ('native', 'sources', 'provenance'):
            shutil.copytree(BUNDLE / name, prefix / name)
        (prefix / 'bin').mkdir()
        for name in ('dotbox', 'dotbox-dosbox-x'):
            shutil.copyfile(BUNDLE / 'launchers' / name, prefix / 'bin' / name)
            (prefix / 'bin' / name).chmod(0o755)
        for name in ('native/bin/dosbox-x', 'native/lib/ld-linux-x86-64.so.2'):
            (prefix / name).chmod(0o755)
        for name in ('START_HERE.md', 'RELEASE_NOTES.md', 'manifest.json', 'SHA256SUMS', 'requirements.lock'):
            shutil.copyfile(BUNDLE / name, prefix / name)
        receipt = {'format': 'dotbox-offline-install-1', 'status': 'installed',
                   'installed_utc': datetime.now(timezone.utc).isoformat(),
                   'prefix': str(prefix), 'version': manifest['version'],
                   'source_commit': manifest['source_commit'], 'manifest_sha256': manifest_hash,
                   'native_binary_sha256': digest(prefix / 'native/bin/dosbox-x'),
                   'python': sys.version, 'platform': platform.platform(),
                   'native_execution_performed': False,
                   'scope': 'Offline installation; desktop input, takeover and audio require host qualification.'}
        (prefix / 'INSTALL_RECEIPT.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': 'installed', 'prefix': str(prefix),
                          'dotbox': str(prefix / 'bin/dotbox'),
                          'native_launcher': str(prefix / 'bin/dotbox-dosbox-x'),
                          'receipt': str(prefix / 'INSTALL_RECEIPT.json')}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if created:
            (prefix / 'INSTALL_FAILED.json').write_text(json.dumps({'status': 'failed', 'error': str(error)}) + '\n')
        print(json.dumps({'status': 'failed', 'error': str(error),
                          'partial_prefix': str(prefix) if created else None}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
