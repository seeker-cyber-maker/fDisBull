#!/usr/bin/env python3
"""Verify immutable OS/QEMU components; create fresh candidate runtime overlays.

This is component reuse, never reuse of another commit's prepared-input manifest.
The caller pins the complete provenance document, and both host and guest verify
the component bytes. The old job outcome remains evidence, not new qualification.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile

from execution_identity import canonical_uuid

SCHEMA = 'fdisbull-retained-runtime-base-1'
QEMU_SOURCE_SHA = 'f3cc1c4eabfdb288218ac3e33763dbe9e276d8bc890b867a2335d58de2ddd39a'
KERNEL_SHA = 'd8808aa4ca188560da1e6d749dcb930c87a5fd8b11ebff1f3fa6d728af35203d'
PATHS = {'FDISBULL_PE_QEMU': '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
         'FDISBULL_PE_KERNEL': '.native/pe/linux-amd64',
         'FDISBULL_PE_FIXTURE': '.native/pe/oracle.exe'}
SOURCE_ARCHIVE = '.native/pe/qemu-9.2.4.tar.xz'
FIRMWARE = '.native/pe/qemu-9.2.4/pc-bios'
OLD_WINE = '.native/pe/runtime.cpio.gz'
EXTRA_OMIT = ('init', 'opt/fdisbull', 'opt/ci', 'root', 'home', 'tmp', 'var/tmp')
WINDOWS_FIXTURES = {'selector.exe': None,
    'PROGRAM.EXE': '9efbfb2264508bd10f2b20d3614973bea36b8abb2074574f68002fe52aee4804',
    'INITIAL.BIN': 'fb3d1d818f01776cd05e7daa7d851b6c948d398250afdfa5ac44894e9cf0b7fa'}
REQUIRED = {'wine64': {'usr/bin/Xvfb', 'usr/bin/python3.12',
                       'usr/bin/x86_64-w64-mingw32-gcc-13-win32'},
            'pe32': {'usr/bin/i686-w64-mingw32-gcc-13-win32',
                     'usr/i686-w64-mingw32/lib/libuser32.a',
                     'usr/i686-w64-mingw32/lib/libgdi32.a',
                     'opt/wine-stable/bin/wine',
                     'opt/wine-stable/lib/wine/i386-windows/kernel32.dll'},
            'win16-guards': {'opt/wine-stable/lib/wine/i386-windows/winevdm.exe',
                             'opt/wine-stable/lib/wine/i386-windows/krnl386.exe16'}}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Missing or symlinked retained component: ' + str(path))
    return path


def checked(root, name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('Unsafe component path')
    return regular(Path(root) / name)


def item(path, name=None):
    path = regular(path)
    return {'path': path.name if name is None else name, 'sha256': digest(path),
            'size': path.stat().st_size}


def load(path):
    return json.loads(regular(path).read_text())


def cpio_inventory(path):
    """Stream all concatenated newc members, with a bounded total payload."""
    files, total, records = {}, 0, 0
    with gzip.open(path, 'rb') as source:
        while True:
            first = source.read(1)
            while first == b'\0':
                first = source.read(1)
            if not first:
                break
            header = first + source.read(109)
            if len(header) != 110 or header[:6] != b'070701':
                raise ValueError('Expected gzip/newc OS base')
            fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
            mode, nlink, size, namesize = fields[1], fields[4], fields[6], fields[11]
            total += size
            if not 1 <= namesize <= 4096 or size > 1024**3 or total > 8*1024**3:
                raise ValueError('OS base exceeds the bounded CPIO inventory')
            encoded = source.read(namesize)
            padding = source.read(-(110+namesize) % 4)
            if len(encoded) != namesize or encoded[-1:] != b'\0' or len(padding) != -(110+namesize) % 4:
                raise ValueError('Truncated CPIO name')
            name = encoded[:-1].decode().removeprefix('./')
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise ValueError('Unsafe CPIO path')
            if nlink > 1 and not stat.S_ISDIR(mode):
                raise ValueError('Unexpanded CPIO hard link')
            hasher = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = source.read(min(8*1024**2, remaining))
                if not chunk:
                    raise ValueError('Truncated CPIO data')
                hasher.update(chunk)
                remaining -= len(chunk)
            if len(source.read(-size % 4)) != -size % 4:
                raise ValueError('Truncated CPIO padding')
            files[name] = {'mode': mode, 'size': size, 'sha256': hasher.hexdigest()}
            records += 1
    capabilities = ['wine64', 'dos']
    for capability, names in REQUIRED.items():
        if not all(n in files and stat.S_ISREG(files[n]['mode']) for n in names):
            if capability == 'wine64':
                raise ValueError('OS base is missing the concrete Wine64 compiler/runtime dependencies')
            continue
        if capability not in capabilities:
            capabilities.append(capability)
    if 'pe32' not in capabilities and 'win16-guards' in capabilities:
        capabilities.remove('win16-guards')
    return {'payload_bytes': total, 'records': records, 'capabilities': capabilities,
            'dependency_files': {n: files[n] for names in REQUIRED.values() for n in sorted(names) if n in files}}


def firmware_identity(root):
    directory = Path(root) / FIRMWARE
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Missing QEMU firmware')
    files = sorted(p for p in directory.rglob('*') if p.is_file())
    if len(files) != 171 or any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Expected exactly 171 regular QEMU firmware files')
    values = [item(p, p.relative_to(directory).as_posix()) for p in files]
    names = {v['path']: v for v in values}
    if not {'bios-256k.bin', 'vgabios-stdvga.bin'} <= names.keys():
        raise ValueError('Required QEMU firmware is absent')
    observed = {}
    with tarfile.open(checked(root, SOURCE_ARCHIVE), 'r:xz') as archive:
        prefix = 'qemu-9.2.4/pc-bios/'
        for member in archive:
            if not member.name.startswith(prefix) or not member.isfile():
                continue
            name = member.name[len(prefix):]
            if name in observed or name not in names:
                raise ValueError('QEMU source firmware set differs')
            stream = archive.extractfile(member)
            observed[name] = {'path': name, 'size': member.size,
                              'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    if observed != names:
        raise ValueError('QEMU firmware differs from the pinned original source archive')
    return values


def original_proof(value):
    source, process, post = value['origin_source_commit'], value['origin_process'], value['origin_source_postcheck']
    if not re.fullmatch('[0-9a-f]{40}', str(source)):
        raise ValueError('Invalid original build source')
    canonical_uuid(process.get('local_run_id'))
    canonical_uuid(process.get('local_job_id'))
    if (process.get('source_commit') != source or process.get('execution_origin') != 'local-linux'
            or process.get('job_name') != 'native-unified' or process.get('termination') != 'exited'
            or type(process.get('exit_code')) is not int or process.get('container_state_after_stop') != 'stopped'
            or process.get('runtime', {}).get('system') != 'linux'
            or process.get('runtime', {}).get('machine') != 'x86_64'
            or not re.fullmatch('sha256:[0-9a-f]{64}', str(process.get('image_digest')))):
        raise ValueError('Original build process provenance mismatch')
    if (post.get('source_commit') != source or post.get('expected_source_commit') != source
            or post.get('tracked_worktree_dirty') is not False or post.get('export_success') is not True):
        raise ValueError('Original source postcheck failed')
    identity = value['origin_backend_identity']
    if identity.get('source_commit') != source:
        raise ValueError('Original backend identity source mismatch')
    if (value['qemu_source']['sha256'] != QEMU_SOURCE_SHA
            or value['inputs']['FDISBULL_PE_KERNEL']['sha256'] != KERNEL_SHA):
        raise ValueError('Original source pins changed')
    for key, component in value['inputs'].items():
        ref = identity['inputs'][key]
        if (component['sha256'], component['size']) != (ref['sha256'], ref['size']):
            raise ValueError('Original component identity mismatch: ' + key)
    if value['original_wine_receipt']['runtime_sha256'] != identity['inputs']['FDISBULL_PE_INITRAMFS']['sha256']:
        raise ValueError('Original runtime build receipt mismatch')
    if (value['shared_os_base']['sha256'], value['shared_os_base']['size']) != (
            identity['inputs']['FDISBULL_PE_INITRAMFS']['sha256'], identity['inputs']['FDISBULL_PE_INITRAMFS']['size']):
        raise ValueError('Small Wine64/DOS OS base differs from original build proof')
    recipe = value['origin_build_recipe']
    if (recipe['sha256'] != hashlib.sha256(recipe['text'].encode()).hexdigest()
            or QEMU_SOURCE_SHA not in recipe['text'] or KERNEL_SHA not in recipe['text']):
        raise ValueError('Original build recipe pin mismatch')


def windows_fixtures(root):
    if set(p.name for p in Path(root).iterdir()) != set(WINDOWS_FIXTURES):
        raise ValueError('Authored Windows fixture directory must contain exactly three declared files')
    values = {name: item(checked(root, name), name) for name in WINDOWS_FIXTURES}
    for name, expected in WINDOWS_FIXTURES.items():
        if expected is not None and values[name]['sha256'] != expected:
            raise ValueError('Declared authored Snake fixture hash mismatch')
        if name.endswith('.exe') or name.endswith('.EXE'):
            data = checked(root, name).read_bytes()
            offset = int.from_bytes(data[60:64], 'little')
            if data[:2] != b'MZ' or data[offset:offset+2] != b'NE':
                raise ValueError('Authored selector/Snake must be NE executables')
    return values


def verify(manifest, root, os_base, expected_sha, *, required=(), fixtures=None):
    manifest, root, os_base = regular(manifest), Path(root), regular(os_base)
    if not re.fullmatch('[0-9a-f]{64}', str(expected_sha)) or digest(manifest) != expected_sha:
        raise ValueError('Retained OS/component manifest hash mismatch')
    value = load(manifest)
    if value.get('schema') != SCHEMA or set(value.get('inputs', {})) != set(PATHS):
        raise ValueError('Not a retained component-base manifest; foreign prepared manifests are rejected')
    original_proof(value)
    for key, name in PATHS.items():
        if item(checked(root, name), name) != value['inputs'][key]:
            raise ValueError('Changed retained component: ' + key)
    source = item(checked(root, SOURCE_ARCHIVE), SOURCE_ARCHIVE)
    if source != value['qemu_source'] or source['sha256'] != QEMU_SOURCE_SHA:
        raise ValueError('QEMU source archive pin mismatch')
    if value['inputs']['FDISBULL_PE_KERNEL']['sha256'] != KERNEL_SHA:
        raise ValueError('Kernel pin mismatch')
    if firmware_identity(root) != value['firmware']:
        raise ValueError('Changed retained firmware')
    if item(os_base) != value['os_base']:
        raise ValueError('Changed retained OS base')
    if item(checked(root, OLD_WINE), OLD_WINE) != value['shared_os_base']:
        raise ValueError('Changed small Wine64/DOS OS base')
    inventory = cpio_inventory(os_base)
    if inventory != value['os_inventory'] or not set(required) <= set(inventory['capabilities']):
        raise ValueError('Requested OS capabilities are unavailable or dependency files changed')
    if value.get('windows_fixtures') is not None:
        if not {'pe32', 'win16-guards'} <= set(inventory['capabilities']):
            raise ValueError('Authored Windows fixtures require the qualified OS dependencies')
        if fixtures is None or windows_fixtures(fixtures) != value['windows_fixtures']:
            raise ValueError('Windows authored fixtures are missing or changed')
    return value


def create(root, os_base, process, postcheck, source, output, os_provenance, fixtures=None):
    root, source = Path(root), Path(source)
    identity = load(checked(root, 'native-evidence/pe/backend-identity.json'))
    sha = identity['source_commit']
    if not re.fullmatch('[0-9a-f]{40}', str(sha)):
        raise ValueError('Invalid original build source')
    recipe = subprocess.check_output(['git', 'show', sha + ':scripts/ci/native-unified.sh'], cwd=source, text=True)
    fixture = subprocess.check_output(['git', 'show', sha + ':tests/wine_gui_fixture.c'], cwd=source)
    value = {'schema': SCHEMA, 'origin_source_commit': sha, 'origin_process': load(process),
             'origin_source_postcheck': load(postcheck), 'origin_backend_identity': identity,
             'origin_build_recipe': {'path': 'scripts/ci/native-unified.sh', 'text': recipe,
                                     'sha256': hashlib.sha256(recipe.encode()).hexdigest()},
             'original_wine_receipt': load(checked(root, 'native-evidence/pe/runtime-preparation.json')),
             'original_dos_receipt': load(checked(root, 'native-evidence/pe/dos-runtime-preparation.json')),
             'original_os_packages': checked(root, 'native-evidence/pe/runtime-packages.txt').read_text(),
             'original_rootfs_image': checked(root, 'native-evidence/pe/rootfs-image.txt').read_text().strip(),
             'fixture_source_sha256': hashlib.sha256(fixture).hexdigest(),
             'inputs': {key: item(checked(root, name), name) for key, name in PATHS.items()},
             'qemu_source': item(checked(root, SOURCE_ARCHIVE), SOURCE_ARCHIVE),
             'firmware': firmware_identity(root), 'os_base': item(os_base),
             'shared_os_base': item(checked(root, OLD_WINE), OLD_WINE),
             'os_inventory': cpio_inventory(os_base), 'os_provenance': [
                 {'name': Path(p).name, 'sha256': digest(p), 'document': load(p)} for p in os_provenance],
             'qualification_claimed': False,
             'boundary': 'Immutable OS/QEMU components only; fresh source/run/job/wheel and runtime overlays required.'}
    if fixtures is not None:
        value['windows_fixtures'] = windows_fixtures(fixtures)
    original_proof(value)
    with Path(output).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    verify(output, root, os_base, digest(output), fixtures=fixtures)
    return value


def estimate(os_base, dosbox_size, *, source_root, shared_os_base=None):
    """Measure the exact compressed immutable stream, not an assumed ratio."""
    spec = importlib.util.spec_from_file_location('candidate_wine_runtime', Path(source_root)/'src/fdisbull/wine_runtime.py')
    wine_runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wine_runtime)
    class Counter:
        count = 0
        def write(self, data):
            self.count += len(data)
            return len(data)
        def flush(self):
            pass
    counter = Counter()
    shared_counter = Counter()
    old = wine_runtime.OMIT
    try:
        wine_runtime.OMIT = (*old, *EXTRA_OMIT)
        with gzip.GzipFile(fileobj=counter, mode='wb', mtime=0, compresslevel=1) as stream:
            wine_runtime.compact_base(os_base, stream)
        with gzip.GzipFile(fileobj=shared_counter, mode='wb', mtime=0, compresslevel=1) as stream:
            wine_runtime.compact_base(shared_os_base or os_base, stream)
    finally:
        wine_runtime.OMIT = old
    # Three runtimes. Bound newc+deflate resource growth by 2x actual resource
    # lengths (including the new DOS binary), plus 4 MiB metadata per image.
    resources = sum(p.stat().st_size for p in (Path(source_root)/'src/fdisbull/wine_guest').glob('*') if p.is_file())
    resources += sum(p.stat().st_size for p in (Path(source_root)/'src/fdisbull/dos_guest').glob('*') if p.is_file())
    runtime_bound = counter.count + 2*shared_counter.count + 2*(2*resources + dosbox_size) + 12*1024**2
    # Three retained copies: guest root, exported host files, qualification.
    # 4 GB additionally covers worker OS packages, pip, source clones and small
    # QEMU/kernel/firmware/fixture copies. No nested Docker, rootfs or QEMU build.
    total = 3*runtime_bound + 4_000_000_000
    return {'expected_bytes': ((total + 999_999_999)//1_000_000_000)*1_000_000_000,
            'measured_compacted_gzip_bytes': counter.count, 'runtime_bound_bytes': runtime_bound,
            'measured_small_compacted_gzip_bytes': shared_counter.count,
            'retained_copies': 3, 'system_and_small_component_budget': 4_000_000_000}


def prepare(manifest, root, os_base, expected_sha, required):
    from fdisbull import dos_runtime, wine_runtime
    value = verify(manifest, root, os_base, expected_sha, required=required,
                   fixtures=os.environ.get('FDISBULL_RETAINED_WINDOWS_FIXTURES'))
    layers = load('native-evidence/layers/backend-identity.json')
    if (layers.get('source_commit') != os.environ['CI_COMMIT_SHA']
            or layers.get('backend_sha256') != digest(os.environ['FDISBULL_DOSBOX'])):
        raise ValueError('Current candidate layers backend identity mismatch')
    if digest('tests/wine_gui_fixture.c') != value['fixture_source_sha256']:
        raise ValueError('Current oracle source differs from retained authored fixture')
    for key, name in PATHS.items():
        destination = Path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError('Refusing to overwrite runtime component')
        shutil.copy2(checked(root, name), destination)
    shutil.copytree(Path(root)/FIRMWARE, FIRMWARE)
    evidence = Path('native-evidence/pe')
    evidence.mkdir(parents=True, exist_ok=True)
    old = wine_runtime.OMIT
    try:
        wine_runtime.OMIT = (*old, *EXTRA_OMIT)
        shared = checked(root, OLD_WINE)
        wine = wine_runtime.prepare(shared, os.environ['FDISBULL_PE_INITRAMFS'])
        dos = dos_runtime.prepare(shared, os.environ['FDISBULL_DOS_INITRAMFS'], os.environ['FDISBULL_DOSBOX'])
        windows = wine_runtime.prepare(os_base, 'native-evidence/pe/windows-runtime.cpio.gz')
    finally:
        wine_runtime.OMIT = old
    for name, document in (('runtime-preparation.json', wine), ('dos-runtime-preparation.json', dos),
                           ('windows-runtime-preparation.json', windows)):
        (evidence/name).write_text(json.dumps(document, indent=2)+'\n')
    shutil.copyfile(manifest, evidence/'retained-base-manifest.json')
    receipt = {'schema': 'fdisbull-retained-base-preparation-1', 'source_commit': os.environ['CI_COMMIT_SHA'],
               'local_run_id': canonical_uuid(os.environ['FDISBULL_LOCAL_RUN_ID']),
               'build_job_id': canonical_uuid(os.environ['FDISBULL_LOCAL_JOB_ID']),
               'manifest_sha256': expected_sha, 'origin_source_commit': value['origin_source_commit'],
               'origin_job_exit_code': value['origin_process']['exit_code'],
               'os_capabilities': value['os_inventory']['capabilities'],
               'required_os_capabilities': required, 'previous_project_resources_removed': list(EXTRA_OMIT)}
    (evidence/'retained-base-preparation.json').write_text(json.dumps(receipt, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create_parser = sub.add_parser('create')
    for name in ('root', 'os-base', 'process', 'postcheck', 'source', 'output'):
        create_parser.add_argument('--'+name, type=Path, required=True)
    create_parser.add_argument('--os-provenance', type=Path, action='append', default=[])
    create_parser.add_argument('--windows-fixtures', type=Path)
    for name in ('verify', 'prepare'):
        p = sub.add_parser(name)
        for field in ('manifest', 'root', 'os-base'):
            p.add_argument('--'+field, type=Path, required=True)
        p.add_argument('--sha256', required=True)
        p.add_argument('--windows-fixtures', type=Path)
        p.add_argument('--require', choices=['wine64', 'dos', 'pe32', 'win16-guards'], action='append', default=[])
    args = parser.parse_args()
    if args.action == 'create':
        create(args.root, args.os_base, args.process, args.postcheck, args.source, args.output, args.os_provenance, args.windows_fixtures)
    elif args.action == 'verify':
        verify(args.manifest, args.root, args.os_base, args.sha256, required=args.require, fixtures=args.windows_fixtures)
    else:
        if os.environ.get('FDISBULL_EXECUTION_ORIGIN') != 'local-linux':
            raise ValueError('Retained preparation is local Linux only')
        prepare(args.manifest, args.root, args.os_base, args.sha256, args.require)
    print('retained runtime base', args.action, 'passed')


if __name__ == '__main__':
    main()
