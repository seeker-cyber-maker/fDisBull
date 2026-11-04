#!/usr/bin/env python3
"""Bind locally prepared unified-runtime inputs to one source, run and build job."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil

from execution_identity import canonical_uuid

ROOT = Path.cwd()
MANIFEST = Path('native-evidence/pe/prepared-inputs.json')
IDENTITY = Path('native-evidence/pe/backend-identity.json')
FIRMWARE = Path('native-evidence/pe/firmware')
RESOURCES = {
    'wine': {'init': 'src/fdisbull/wine_guest/init.sh', 'opt/fdisbull/agent.c': 'src/fdisbull/wine_guest/agent.c',
             'opt/fdisbull/broker.py': 'src/fdisbull/wine_guest/broker.py', 'opt/fdisbull/selftest.c': 'src/fdisbull/wine_guest/selftest.c'},
    'dos': {'init': 'src/fdisbull/dos_guest/init.sh', 'opt/fdisbull/dos_broker.py': 'src/fdisbull/dos_guest/broker.py',
            'opt/fdisbull/remote/__init__.py': 'src/fdisbull/dos_guest/__init__.py',
            'opt/fdisbull/remote/dosbox_rpc.py': 'src/fdisbull/dosbox_rpc.py'}}
INPUT_PATHS = {'FDISBULL_PE_QEMU': '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
               'FDISBULL_PE_KERNEL': '.native/pe/linux-amd64',
               'FDISBULL_PE_INITRAMFS': '.native/pe/runtime.cpio.gz',
               'FDISBULL_PE_FIXTURE': '.native/pe/oracle.exe',
               'FDISBULL_DOSBOX': '.native/backends/layers/dosbox-x',
               'FDISBULL_DOS_INITRAMFS': '.native/pe/dos-runtime.cpio.gz'}
KEYS = tuple(INPUT_PATHS)


def checked_path(name, root=ROOT):
    if not isinstance(name, str):
        raise ValueError('artifact path must be a string')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('unsafe artifact path')
    root = Path(root).resolve()
    path = root / name
    if any((root / Path(*p.parts[:i])).is_symlink() for i in range(1, len(p.parts) + 1)):
        raise ValueError(f'symlink in artifact path: {name}')
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f'missing or unsafe artifact: {name}')
    return path


def item(path, root=ROOT):
    root = Path(root).resolve()
    path = Path(os.path.abspath(path))
    name = path.relative_to(root).as_posix()
    path = checked_path(name, root)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': name, 'sha256': sha, 'size': path.stat().st_size}


def regular_files(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('firmware directory missing or unsafe')
    files = []
    for base, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            path = Path(base) / name
            if path.is_symlink():
                raise ValueError('firmware symlinks are not accepted')
        files.extend(Path(base) / n for n in names)
    if not files:
        raise ValueError('firmware set is empty')
    return sorted(files)


def context():
    if os.environ.get('FDISBULL_EXECUTION_ORIGIN') != 'local-linux':
        raise ValueError('prepared runtime is local Linux only')
    sha = os.environ['CI_COMMIT_SHA']
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('invalid source commit')
    return sha, canonical_uuid(os.environ.get('FDISBULL_LOCAL_RUN_ID'))


def checked_wheel(root, identity):
    root = Path(root).resolve()
    prepared = list((root / '.native/pe/packages').glob('fdisbull-*.whl'))
    ordinary = list((root / 'dist').glob('fdisbull-*.whl'))
    if len(prepared) != 1 or len(ordinary) != 1:
        raise ValueError('exactly one prepared and ordinary core wheel is required')
    tested, source = item(prepared[0], root), item(ordinary[0], root)
    if prepared[0].name != ordinary[0].name or (tested['sha256'], tested['size']) != (source['sha256'], source['size']):
        raise ValueError('prepared and ordinary core wheels differ')
    reference = identity['wheel']
    if (tested['sha256'], tested['size']) != (reference['sha256'], reference['size']):
        raise ValueError('backend identity wheel mismatch')
    return tested


def check_resources(root, source_root, inputs):
    receipts = {}
    for kind in ('wine', 'dos'):
        relative = Path('native-evidence/pe') / ('runtime-preparation.json' if kind == 'wine' else 'dos-runtime-preparation.json')
        document = json.loads(checked_path(str(relative), root).read_text())
        runtime_key = 'FDISBULL_PE_INITRAMFS' if kind == 'wine' else 'FDISBULL_DOS_INITRAMFS'
        if document.get('runtime_sha256') != inputs[runtime_key]['sha256']:
            raise ValueError(f'{kind} runtime receipt does not match prepared input')
        expected = dict(RESOURCES[kind])
        if kind == 'dos':
            expected['opt/fdisbull/dosbox-x'] = None
        hashes = document.get('resources')
        if not isinstance(hashes, dict) or set(hashes) != set(expected):
            raise ValueError(f'{kind} runtime resource set mismatch')
        if kind == 'dos' and hashes['opt/fdisbull/dosbox-x'] != inputs['FDISBULL_DOSBOX']['sha256']:
            raise ValueError('DOS runtime backend mismatch')
        if source_root is not None:
            for guest_path, source_name in RESOURCES[kind].items():
                path = checked_path(source_name, source_root)
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if hashes[guest_path] != digest:
                    raise ValueError(f'{kind} runtime source resource mismatch: {source_name}')
        receipts[kind] = item(Path(root) / relative, root)
    return receipts


def prepare():
    sha, run = context()
    build_job = canonical_uuid(os.environ.get('FDISBULL_LOCAL_JOB_ID'))
    identity = json.loads(IDENTITY.read_text())
    if identity.get('source_commit') != sha:
        raise ValueError('backend identity source mismatch')
    inputs = {key: item(os.environ[key]) for key in KEYS}
    if any(inputs[key]['path'] != INPUT_PATHS[key] for key in KEYS):
        raise ValueError('unexpected runtime input path')
    if len({x['path'] for x in inputs.values()}) != len(KEYS):
        raise ValueError('runtime inputs must be distinct')
    for key, value in inputs.items():
        reference = identity['inputs'][key]
        if (value['sha256'], value['size']) != (reference['sha256'], reference['size']):
            raise ValueError(f'backend identity mismatch: {key}')
    source = Path('.native/pe/qemu-9.2.4/pc-bios')
    if len(regular_files(source)) != 171:
        raise ValueError('QEMU firmware source must contain 171 regular files')
    if FIRMWARE.exists():
        raise ValueError('firmware destination already exists')
    shutil.copytree(source, FIRMWARE)
    firmware = [item(p) for p in regular_files(FIRMWARE)]
    for name in ('bios-256k.bin', 'vgabios-stdvga.bin'):
        if not (FIRMWARE / name).is_file():
            raise ValueError(f'required QEMU firmware missing: {name}')
    resource_receipts = check_resources(ROOT, ROOT, inputs)
    tested_wheel = checked_wheel(ROOT, identity)
    manifest = {'schema': 'fdisbull-unified-runtime-inputs-1', 'source_commit': sha,
                'local_run_id': run, 'build_job_id': build_job, 'inputs': inputs,
                'backend_identity': item(IDENTITY), 'tested_wheel': tested_wheel,
                'firmware': firmware, 'resource_receipts': resource_receipts}
    with MANIFEST.open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')


def verify(root=None, source_sha=None, run_uuid=None, build_job_uuid=None, source_root=None, install_firmware=None):
    local = root is None
    root = ROOT if local else Path(root).resolve()
    if local:
        source_sha, run_uuid = context()
        build_job_uuid = os.environ.get('FDISBULL_UNIFIED_BUILD_JOB_ID')
        source_root = ROOT
    if not isinstance(source_sha, str) or len(source_sha) != 40 or any(c not in '0123456789abcdef' for c in source_sha):
        raise ValueError('invalid source commit')
    canonical_uuid(run_uuid)
    canonical_uuid(build_job_uuid)
    manifest = json.loads(checked_path(str(MANIFEST), root).read_text())
    if (manifest.get('schema') != 'fdisbull-unified-runtime-inputs-1'
            or manifest.get('source_commit') != source_sha or manifest.get('local_run_id') != run_uuid
            or manifest.get('build_job_id') != build_job_uuid):
        raise ValueError('prepared runtime source, run or build identity mismatch')
    inputs = manifest.get('inputs')
    if not isinstance(inputs, dict) or set(inputs) != set(KEYS):
        raise ValueError('prepared runtime requires six inputs')
    if len({v.get('path') for v in inputs.values() if isinstance(v, dict)}) != len(KEYS):
        raise ValueError('runtime inputs must be distinct')
    for key, value in inputs.items():
        if not isinstance(value, dict) or value.get('path') != INPUT_PATHS[key] or item(checked_path(value.get('path'), root), root) != value:
            raise ValueError(f'prepared runtime input mismatch: {key}')
        if local and item(os.environ[key], root) != value:
            raise ValueError(f'prepared runtime environment mismatch: {key}')
    if manifest.get('backend_identity') != item(root / IDENTITY, root):
        raise ValueError('backend identity changed')
    identity = json.loads(checked_path(str(IDENTITY), root).read_text())
    if identity.get('source_commit') != source_sha:
        raise ValueError('backend identity source mismatch')
    if manifest.get('tested_wheel') != checked_wheel(root, identity):
        raise ValueError('tested wheel identity mismatch')
    for key, value in inputs.items():
        ref = identity['inputs'][key]
        if (value['sha256'], value['size']) != (ref['sha256'], ref['size']):
            raise ValueError(f'backend identity mismatch: {key}')
    files = [item(p, root) for p in regular_files(root / FIRMWARE)]
    if len(files) != 171 or files != manifest.get('firmware'):
        raise ValueError('QEMU firmware content mismatch')
    if check_resources(root, source_root, inputs) != manifest.get('resource_receipts'):
        raise ValueError('runtime resource preparation evidence changed')
    if install_firmware is not None:
        destination = Path(install_firmware)
        if os.path.lexists(destination):
            raise ValueError('firmware destination already exists')
        shutil.copytree(root / FIRMWARE, destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'verify'])
    parser.add_argument('--install-firmware', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.install_firmware is not None:
            parser.error('--install-firmware applies only to verify')
        prepare()
    else:
        verify(install_firmware=args.install_firmware)
    print('unified runtime inputs', args.action, 'passed')


if __name__ == '__main__':
    main()
