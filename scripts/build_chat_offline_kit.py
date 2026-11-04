#!/usr/bin/env python3
"""Assemble a hash-bound Linux chat kit from an explicitly prepared inventory.

This does not build, install, download, or qualify any of its inputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import shutil
import zipfile
import struct
from email.parser import BytesParser
from email.policy import default

REQUIRED_ROLES = {
    'python', 'loader', 'dosbox', 'qemu', 'firmware', 'kernel',
    'wine_initramfs', 'dos_initramfs', 'source_companion', 'license',
    'wheel_core', 'wheel_player', 'wheel_z3', 'closure_receipt',
    'python_receipt', 'dosbox_receipt', 'qemu_receipt', 'wine_receipt',
    'pe_fixture', 'verifier',
}
RUNTIME_WHEELS = {'fdisbull', 'fdisbull-player', 'iced-x86', 'capstone', 'lief', 'pillow', 'z3-solver', 'unicorn', 'dnfile', 'dncil', 'pefile', 'tree-sitter', 'tree-sitter-c', 'pycparser', 'zstandard'}
ELF_ROLES = {'python', 'loader', 'dosbox', 'qemu'}
SINGLE_ROLES = REQUIRED_ROLES - {'firmware', 'license'}
FORBIDDEN = {'.fdb', '.sav', '.state', '.png', '.jpg', '.jpeg', '.gif', '.bmp'}


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def is_elf64_x86_64(header):
    return len(header) >= 20 and header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 62


def destination(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('invalid destination')
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ('.', '..') for part in value.split('/')) or not re.fullmatch(r'[A-Za-z0-9_+.,@/=-]+', value):
        raise ValueError(f'unsafe destination: {value}')
    if any(part.startswith('.') for part in p.parts) or p.suffix.lower() in FORBIDDEN:
        raise ValueError(f'private or hidden payload prohibited: {value}')
    if p.parts[0] in {'bin', 'MANIFEST.json', 'README.txt'}:
        raise ValueError(f'reserved destination: {value}')
    return p



def wheel_destination(filename, dist_info):
    """Map the supported pinned-prefix wheel schemes; never silently drop data."""
    if (not isinstance(filename, str) or not filename or '\\' in filename
            or filename.startswith('/') or any(x in ('', '.', '..') for x in filename.split('/'))):
        raise ValueError('unsafe wheel member')
    if not isinstance(dist_info, str) or '/' in dist_info or not dist_info.endswith('.dist-info'):
        raise ValueError('invalid wheel dist-info directory')
    parts = filename.split('/')
    base = 'python/lib/python3.13/site-packages/'
    if parts[0].endswith('.data'):
        if parts[0] != dist_info[:-len('.dist-info')] + '.data' or len(parts) < 3:
            raise ValueError('invalid wheel data directory')
        scheme = parts[1]
        if scheme == 'data':
            base = 'python/'
        elif scheme not in ('purelib', 'platlib'):
            # Scripts can require installer shebang transformations; headers
            # require an explicit distribution-specific install scheme.
            raise ValueError('unsupported wheel data destination requiring verified install scheme: ' + scheme)
        parts = parts[2:]
    return str(destination(base + '/'.join(parts)))


def load_inventory(path):
    inventory = json.loads(Path(path).read_text())
    if inventory.get('schema') != 'fdisbull-chat-offline-inventory-v1':
        raise ValueError('invalid inventory schema')
    identities = inventory.get('identities', {})
    for name in ('source_commit', 'test_source_commit'):
        if not re.fullmatch(r'[0-9a-f]{40,64}', identities.get(name, '')):
            raise ValueError(f'invalid {name}')
    if identities.get('python') != '3.13.5' or identities.get('qemu') != '9.2.4':
        raise ValueError('requires CPython 3.13.5 and QEMU 9.2.4 identities')
    if not identities.get('wine') or not identities.get('version'):
        raise ValueError('missing Wine or package version identity')
    entries, roles, paths = inventory.get('files', []), {}, set()
    if not isinstance(entries, list) or not entries:
        raise ValueError('empty inventory')
    for item in entries:
        target = str(destination(item['destination']))
        if target in paths:
            raise ValueError(f'duplicate destination: {target}')
        paths.add(target)
        src = Path(item['source'])
        if not src.is_absolute() or src.is_symlink() or not src.is_file():
            raise ValueError(f'input must be an absolute regular file: {src}')
        if not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', '')) or sha256(src) != item['sha256']:
            raise ValueError(f'hash mismatch: {src}')
        if item.get('size') != src.stat().st_size or isinstance(item.get('size'), bool):
            raise ValueError(f'size mismatch: {src}')
        role = item.get('role', 'payload')
        roles.setdefault(role, []).append(target)
        if role in ELF_ROLES:
            with src.open('rb') as f:
                header = f.read(20)
                if not is_elf64_x86_64(header):
                    raise ValueError(f'{role} must be ELF64 little-endian x86-64')
    profile = inventory.get('profile', 'prebuilt')
    if profile not in ('prebuilt', 'shared'):
        raise ValueError('unknown profile')
    required = REQUIRED_ROLES if profile == 'prebuilt' else (REQUIRED_ROLES - {'wine_initramfs', 'dos_initramfs'}) | {'runtime_base', 'runtime_recipe', 'runtime_preparer', 'windows_runtime_base', 'windows_runtime_recipe'}
    if profile == 'shared' and ({'wine_initramfs', 'dos_initramfs'} & roles.keys()):
        raise ValueError('shared profile must not contain prebuilt initramfs')
    if profile == 'shared' and roles.get('runtime_preparer') != ['tools/preparer.py']:
        raise ValueError('runtime_preparer must be tools/preparer.py')
    missing = required - roles.keys()
    if missing:
        raise ValueError(f'missing roles: {sorted(missing)}')
    for role in required - {'firmware', 'license'}:
        if len(roles[role]) != 1:
            raise ValueError(f'exactly one {role} required')
    if roles['python'][0] != 'python/bin/python3.13':
        raise ValueError('python must be at python/bin/python3.13')
    if not any(p.startswith('python/lib/python3.13/') and '/site-packages/fdisbull/' in p for p in paths):
        raise ValueError('prepared Python lacks fdisbull package')
    for package in ('fdisbull_player', 'z3'):
        if not any(p.startswith('python/lib/python3.13/site-packages/' + package + '/') for p in paths):
            raise ValueError(f'prepared Python lacks {package}')
    if not any(p.startswith('python/lib/python3.13/encodings/') for p in paths):
        raise ValueError('prepared Python lacks standard library encodings')
    if not any(p.startswith('python/lib/python3.13/site-packages/fdisbull/skills/') for p in paths):
        raise ValueError('prepared Python lacks bundled skills')
    if not any(p.startswith('lib/') for p in paths):
        raise ValueError('private ELF libraries missing')
    for role in ('wheel_core', 'wheel_player', 'wheel_z3'):
        if not roles[role][0].startswith('wheels/') or not roles[role][0].endswith('.whl'):
            raise ValueError(f'{role} must be a wheel in wheels/')
    for role, expected in [('wheel_core', 'fdisbull'), ('wheel_player', 'fdisbull-player'), ('wheel_z3', 'z3-solver')]:
        item = next(x for x in entries if x.get('role') == role)
        with zipfile.ZipFile(item['source']) as wheel:
            metadata = [n for n in wheel.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1]
            if len(metadata) != 1:
                raise ValueError(f'invalid wheel metadata: {role}')
            msg = BytesParser(policy=default).parsebytes(wheel.read(metadata[0]))
            if re.sub(r'[-_.]+', '-', msg.get('Name', '')).lower() != expected:
                raise ValueError(f'wrong wheel distribution: {role}')
            if role != 'wheel_z3' and msg.get('Version') != identities['version']:
                raise ValueError(f'wheel version mismatch: {role}')
            if not any(n.endswith('.dist-info/RECORD') and n.count('/') == 1 for n in wheel.namelist()):
                raise ValueError(f'wheel missing RECORD: {role}')
    pins = inventory.get('wheel_versions')
    if not isinstance(pins, dict) or set(pins) != RUNTIME_WHEELS or not all(isinstance(v, str) and v for v in pins.values()):
        raise ValueError('wheel_versions must pin the complete runtime distribution set')
    wheel_names = set()
    for item in entries:
        if item['destination'].startswith('wheels/'):
            if not item['destination'].endswith('.whl'):
                raise ValueError('wheelhouse contains non-wheel')
            with zipfile.ZipFile(item['source']) as wheel:
                meta = [n for n in wheel.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1]
                if len(meta) != 1:
                    raise ValueError('invalid wheelhouse metadata')
                msg = BytesParser(policy=default).parsebytes(wheel.read(meta[0]))
                name = re.sub(r'[-_.]+', '-', msg.get('Name', '')).lower()
                if name in wheel_names:
                    raise ValueError('duplicate wheel distribution')
                if name not in pins or msg.get('Version') != pins[name]:
                    raise ValueError(f'wheel version missing or differs from pin: {name}')
                wheel_names.add(name)
                if profile == 'shared':
                    by_dest = {x['destination']: x for x in entries}
                    for member in wheel.infolist():
                        if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                            continue
                        installed = wheel_destination(member.filename, meta[0].split('/')[0])
                        match = by_dest.get(installed)
                        if (match is None or match['size'] != member.file_size
                                or hashlib.sha256(wheel.read(member)).hexdigest() != match['sha256']):
                            raise ValueError(f'installed wheel member missing or changed: {installed}')
    if wheel_names != RUNTIME_WHEELS:
        raise ValueError(f'wrong wheelhouse distributions: {sorted(wheel_names)}')
    # The receipt binds the dependency enumerator's complete file set. It must
    # list the exact ELF objects inspected and every resolved library destination.
    receipt_item = next(x for x in entries if x.get('role') == 'closure_receipt')
    closure = json.loads(Path(receipt_item['source']).read_text())
    if closure.get('schema') != 'fdisbull-elf-closure-v1' or closure.get('complete') is not True:
        raise ValueError('closure receipt must declare a complete ELF traversal')
    objects = closure.get('objects')
    if not isinstance(objects, list) or not objects:
        raise ValueError('closure objects missing')
    checked = set()
    for obj in objects:
        p = str(destination(obj['path']))
        if p not in paths or p in checked:
            raise ValueError(f'unknown or duplicate closure object: {p}')
        checked.add(p)
        needed = obj.get('needed')
        if not isinstance(needed, dict):
            raise ValueError('closure object needs dependency map')
        for soname, target in needed.items():
            if not isinstance(soname, str) or '/' in soname or not soname:
                raise ValueError('invalid soname')
            private = target.startswith('lib/') or target.startswith('python/lib/python3.13/site-packages/') or target.startswith('python/lib/python3.13/lib-dynload/')
            if target not in paths or not private or PurePosixPath(target).name != soname:
                raise ValueError(f'unresolved library: {soname}')
            matched = next(x for x in entries if x['destination'] == target)
            with Path(matched['source']).open('rb') as f:
                if not is_elf64_x86_64(f.read(20)):
                    raise ValueError(f'dependency is not a host ELF: {soname}')
    for item in entries:
        with Path(item['source']).open('rb') as stream:
            header = stream.read(20)
        firmware = item.get('role') == 'firmware' and item['destination'].startswith('native/qemu/share/qemu/')
        is_elf = header.startswith(b'\x7fELF') and not firmware
        if is_elf and not is_elf64_x86_64(header):
            raise ValueError(f'unsupported ELF architecture: {item["destination"]}')
        if is_elf and item['destination'] not in checked:
            raise ValueError(f'closure omits ELF object: {item["destination"]}')
    for role in ELF_ROLES:
        if roles[role][0] not in checked:
            raise ValueError(f'closure does not cover {role}')
    return inventory, roles


def wrapper(loader, target, python=False, module=None, qemu=False):
    command = '"$ROOT/' + loader + '" --inhibit-cache --library-path "$ROOT/lib" "$ROOT/' + target + '"'
    if python:
        command += ' -s -P'
    if module:
        command += ' -m ' + module
    if qemu:
        command += ' -L "$ROOT/native/qemu/share/qemu"'
    return ('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)\n'
            'unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH LD_PRELOAD\nexport PYTHONNOUSERSITE=1\n' +
            ('export PYTHONHOME="$ROOT/python"\n' if python else '') +
            'exec ' + command + ' "$@"\n')


def build(inventory_path, output, compression='zip', max_bytes=2_000_000_000):
    inventory, roles = load_inventory(inventory_path)
    output = Path(output).absolute()
    if output.exists():
        raise ValueError('output already exists')
    if not output.parent.is_dir():
        raise ValueError('output parent must already exist')
    with tempfile.TemporaryDirectory(prefix='.chat-kit-', dir=output.parent) as tmp:
        root = Path(tmp) / 'fdisbull-chat-offline'
        root.mkdir()
        profile = inventory.get('profile', 'prebuilt')
        delivered = [x for x in inventory['files'] if profile != 'shared' or not x['destination'].startswith('wheels/')]
        for item in delivered:
            dst = root / str(destination(item['destination']))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item['source'], dst)
            if sha256(dst) != item['sha256']:
                raise ValueError(f'input changed during copy: {item["source"]}')
            dst.chmod(0o755 if item.get('executable', False) or item.get('role') in ELF_ROLES else 0o644)
        (root / 'bin').mkdir()
        loader = roles['loader'][0]
        for name, role, module in [('python', 'python', None), ('fdisbull', 'python', 'fdisbull'), ('player', 'python', 'fdisbull_player'), ('dosbox', 'dosbox', None), ('qemu', 'qemu', None)]:
            p = root / 'bin' / name
            p.write_text(wrapper(loader, roles[role][0], role == 'python', module, qemu=role == 'qemu'))
            p.chmod(0o755)
        names = ['python', 'fdisbull', 'player', 'dosbox', 'qemu']
        if profile == 'shared':
            prepare = root / 'bin/prepare-runtimes'
            prepare.write_text('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)\nexec "$ROOT/bin/python" -s -P "$ROOT/tools/preparer.py" --kit "$ROOT" "$@"\n')
            prepare.chmod(0o755)
            names.append('prepare-runtimes')
        generated = [{'destination': 'bin/' + name, 'sha256': sha256(root / 'bin' / name), 'size': (root / 'bin' / name).stat().st_size, 'role': 'entrypoint'} for name in names]
        readme = root / 'README.txt'
        text = (f"fDisBull {inventory['identities']['version']} Linux x86-64 offline kit\n"
                f"Source commit: {inventory['identities']['source_commit']}\n"
                "Profile: Linux DOS/PE analysis, player and Z3.\n\n"
                "Start here:\n"
                "  ./bin/fdisbull --help\n"
                "  ./bin/fdisbull agent-skill --reference SKILL.md\n"
                "  ./bin/player --help\n")
        if profile == 'shared':
            text += ("  ./bin/prepare-runtimes --cache /absolute/writable/cache\n"
                     "This prepares compact DOS and Wine PE64 images. The full Windows\n"
                     "image is included separately and can be reconstructed offline:\n"
                     "  ./bin/prepare-runtimes --windows --cache /absolute/writable/windows-cache\n"
                     "Select that image explicitly for the larger Windows profile with\n"
                     "memory_mib=8192. Check the delivery receipts for tested capabilities;\n"
                     "runtime reconstruction alone does not establish native compatibility.\n"
                     "Runtime preparation is fully local and returns Wine, DOS and kernel paths.\n")
        text += ("\nUse ./bin/dosbox for the private DOS backend; use ./bin/qemu with\n"
                 "the prepared kernel and guest runtime paths for PE analysis.\n"
                 "Portable Python and the runtime requirements are bundled; no pip or downloads are needed.\n"
                 "Keep your own games, projects and states outside this immutable kit.\n"
                 "The builder assembles inputs; consult the delivery message for consumer qualification.\n")
        readme.write_text(text)
        generated.append({'destination': 'README.txt', 'sha256': sha256(readme),
                          'size': readme.stat().st_size, 'role': 'documentation'})
        public = {'schema': 'fdisbull-chat-offline-manifest-v1', 'identities': inventory['identities'], 'wheel_versions': inventory['wheel_versions'], 'profile': profile,
                  'wheel_artifacts': [{'name': Path(x['destination']).name, 'sha256': x['sha256'], 'size': x['size']} for x in inventory['files'] if x['destination'].startswith('wheels/')],
                  'files': [{k: v for k, v in x.items() if k != 'source'} for x in delivered] + generated,
                  'qualification': 'not-qualified-by-builder'}
        (root / 'MANIFEST.json').write_text(json.dumps(public, indent=2, sort_keys=True) + '\n')
        if compression == 'zip':
            with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path in sorted(root.rglob('*')):
                    if path.is_file():
                        archive.write(path, (Path(root.name) / path.relative_to(root)).as_posix())
        else:
            with tarfile.open(output, 'x:' + compression) as tar:
                tar.add(root, arcname=root.name, recursive=True)
        if output.stat().st_size > max_bytes:
            raise ValueError(f'archive exceeds {max_bytes} bytes; candidate retained unqualified: {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--compression', choices=('zip', 'xz', 'gz'), default='zip')
    parser.add_argument('--max-bytes', type=int, default=2_000_000_000)
    args = parser.parse_args()
    try:
        build(args.inventory, args.output, args.compression, args.max_bytes)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f'chat kit: {exc}\n')


if __name__ == '__main__':
    main()
