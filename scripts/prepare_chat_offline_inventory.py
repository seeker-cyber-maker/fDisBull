#!/usr/bin/env python3
"""Stage explicit Linux inputs and derive a chat-kit ELF inventory, without installs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from email.policy import default

spec = importlib.util.spec_from_file_location('chat_kit_builder', Path(__file__).with_name('build_chat_offline_kit.py'))
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


def run(argv):
    return subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}).stdout


def ldd_dependencies(path, ldd):
    """Resolve trusted supplied ELF with Linux ldd; reject every unresolved line."""
    try:
        out = run([str(ldd), str(path)])
    except subprocess.CalledProcessError as exc:
        text = (exc.stdout or '') + (exc.stderr or '')
        if text.strip() in ('statically linked', 'not a dynamic executable'):
            return {}
        raise ValueError(f'ldd failed for {path}: {text.strip()}') from exc
    if out.strip() == 'statically linked':
        return {}
    found = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith('linux-vdso'):
            continue
        if 'not found' in line:
            raise ValueError(f'unresolved dependency for {path}: {line}')
        match = re.match(r'([^\s/]+)\s+=>\s+(/\S+)\s+\(0x[0-9a-fA-F]+\)$', line)
        if match:
            name, source = match.groups()
        else:
            match = re.match(r'(/\S+)\s+\(0x[0-9a-fA-F]+\)$', line)
            if not match:
                raise ValueError(f'unrecognized ldd output for {path}: {line}')
            source = match.group(1)
            name = Path(source).name
        if name in found and Path(found[name]).resolve() != Path(source).resolve():
            raise ValueError(f'conflicting ldd dependency: {name}')
        found[name] = source
    return found


def is_elf(path):
    with path.open('rb') as f:
        return f.read(4) == b'\x7fELF'


def dependency_destination(soname, source, sources):
    """Prefer a unique inventoried Python-vendored library with identical origin."""
    resolved = Path(source).resolve(strict=True)
    candidates = [dest for dest, origin in sources.items()
                  if (dest.startswith('python/lib/python3.13/site-packages/')
                      or dest.startswith('python/lib/python3.13/lib-dynload/'))
                  and PurePosixPath(dest).name == soname
                  and Path(origin).resolve(strict=True) == resolved]
    if len(candidates) > 1:
        raise ValueError(f'ambiguous inventoried dependency: {soname}')
    return candidates[0] if candidates else 'lib/' + soname



def installed_wheel_member(prefix, filename, payload, dist_info):
    """Verify actual installed bytes at the mapped prefix-confined location."""
    prefix = Path(prefix).resolve(strict=True)
    dest = kit.wheel_destination(filename, dist_info)
    installed = prefix / dest.removeprefix('python/')
    if (not installed.is_file() or installed.is_symlink()
            or not installed.resolve(strict=True).is_relative_to(prefix)
            or installed.stat().st_size != len(payload)
            or hashlib.sha256(payload).hexdigest() != kit.sha256(installed)):
        raise ValueError(f'installed wheel member missing or changed: {dest}')
    return installed, dest


def prepare(config, stage, resolver=ldd_dependencies):
    stage = Path(stage).absolute()
    if not stage.is_dir() or any(stage.iterdir()):
        raise ValueError('stage must be an existing empty directory')
    prefix = Path(config['python_prefix']).resolve(strict=True)
    wheels = Path(config['wheelhouse']).resolve(strict=True)
    ldd = Path(config['ldd']).resolve(strict=True)
    sources = {}
    roles = {}
    origins = {}
    def add(source, dest, role='payload'):
        dest = str(kit.destination(dest, role=role))
        source = Path(source).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f'not a regular input: {source}')
        if dest in sources:
            if kit.sha256(source) != kit.sha256(sources[dest]):
                raise ValueError(f'conflicting payload: {dest}')
            return
        sources[dest] = source
        roles[dest] = role
        origins[dest] = str(source)
    add(prefix / 'bin/python3.13', 'python/bin/python3.13', 'python')
    stdlib = prefix / 'lib/python3.13'
    excluded = {'site-packages', '__pycache__', 'test', 'tests', 'ensurepip', 'pip', 'idlelib', 'tkinter', 'turtledemo'}
    for root, dirs, files in os.walk(stdlib, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in excluded and not x.startswith('.'))
        for name in sorted(files):
            source = Path(root) / name
            if name.endswith(('.pyc', '.pyo')) or name.startswith('.'):
                continue
            add(source, 'python/lib/python3.13/' + source.relative_to(stdlib).as_posix())
    pins = config['wheel_versions']
    if set(pins) != kit.RUNTIME_WHEELS:
        raise ValueError('wheel_versions does not pin the complete runtime set')
    seen = set()
    for wheel in sorted(wheels.glob('*.whl')):
        with zipfile.ZipFile(wheel) as z:
            metadata = [x for x in z.namelist() if x.endswith('.dist-info/METADATA') and x.count('/') == 1]
            if len(metadata) != 1:
                raise ValueError(f'invalid wheel metadata: {wheel.name}')
            msg = BytesParser(policy=default).parsebytes(z.read(metadata[0]))
            name = re.sub(r'[-_.]+', '-', msg.get('Name', '')).lower()
            if name not in pins or name in seen or msg.get('Version') != pins[name]:
                raise ValueError(f'unexpected, duplicate, or wrong wheel version: {name}')
            seen.add(name)
            role = {'fdisbull': 'wheel_core', 'fdisbull-player': 'wheel_player', 'z3-solver': 'wheel_z3'}.get(name, 'payload')
            add(wheel, 'wheels/' + wheel.name, role)
            for member in z.infolist():
                if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                    continue
                installed, dest = installed_wheel_member(
                    prefix, member.filename, z.read(member), metadata[0].split('/')[0])
                add(installed, dest)
    if seen != kit.RUNTIME_WHEELS:
        raise ValueError(f'missing runtime wheels: {sorted(kit.RUNTIME_WHEELS - seen)}')
    for item in config['inputs']:
        add(item['source'], item['destination'], item.get('role', 'payload'))
    if roles.get('native/qemu/bin/qemu-system-x86_64') != 'qemu':
        raise ValueError('qemu must use native/qemu/bin/qemu-system-x86_64')
    if not any(p.startswith('native/qemu/share/qemu/') and roles[p] == 'firmware' for p in sources):
        raise ValueError('QEMU firmware must be under native/qemu/share/qemu')
    # Resolve all ELF dependencies recursively. Each SONAME maps to one hash.
    pending = [p for p in sources if not p.startswith('wheels/') and not (roles[p] == 'firmware' and p.startswith('native/qemu/share/qemu/')) and is_elf(sources[p])]
    closure, visited = [], set()
    while pending:
        dest = pending.pop()
        if dest in visited:
            continue
        visited.add(dest)
        mapping = {}
        for soname, source in resolver(sources[dest], ldd).items():
            if not re.fullmatch(r'[A-Za-z0-9_+.,@=-]+', soname):
                raise ValueError(f'unsafe SONAME: {soname}')
            target = dependency_destination(soname, source, sources)
            add(source, target)
            mapping[soname] = target
            if target not in visited:
                pending.append(target)
        closure.append({'path': dest, 'needed': mapping})
    receipt_path = stage / 'elf-closure.json'
    receipt_path.write_text(json.dumps({'schema': 'fdisbull-elf-closure-v1', 'complete': True,
                                        'method': 'linux-ldd-recursive', 'objects': closure}, indent=2) + '\n')
    # Inputs are copied only after all dependency resolution succeeds.
    strip_targets = set(config.get('strip_debug', []))
    if not strip_targets <= set(sources):
        raise ValueError('unknown strip target')
    if any(p.startswith(('python/', 'wheels/')) for p in strip_targets):
        raise ValueError('cannot strip wheel or Python prefix files')
    strip = Path(config['strip']).resolve(strict=True) if strip_targets else None
    strip_version = run([str(strip), '--version']).splitlines()[0] if strip else None
    entries, transformations = [], []
    for dest, source in sorted(sources.items()):
        if dest.startswith('wheels/'):
            staged = source
        else:
            staged = stage / 'payload' / dest
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, staged)
            if dest in strip_targets:
                if not is_elf(staged):
                    raise ValueError(f'not ELF for strip: {dest}')
                before = kit.sha256(staged)
                run([str(strip), '--strip-debug', str(staged)])
                transformations.append({'destination': dest, 'original_sha256': before,
                                        'derived_sha256': kit.sha256(staged)})
        entries.append({'source': str(staged), 'destination': dest, 'role': roles[dest],
                        'size': staged.stat().st_size, 'sha256': kit.sha256(staged)})
    entries.append({'source': str(receipt_path), 'destination': 'receipts/elf-closure.json',
                    'role': 'closure_receipt', 'size': receipt_path.stat().st_size,
                    'sha256': kit.sha256(receipt_path)})
    provenance = stage / 'provenance.json'
    provenance.write_text(json.dumps({'schema': 'fdisbull-chat-staging-v1', 'sources': origins,
                                      'strip_version': strip_version, 'transformations': transformations}, indent=2) + '\n')
    inventory = {'schema': 'fdisbull-chat-offline-inventory-v1', 'profile': 'shared',
                 'identities': config['identities'], 'wheel_versions': pins, 'files': entries}
    if config.get('windows_acceptance') is not None:
        inventory['windows_acceptance'] = config['windows_acceptance']
    output = stage / 'inventory.json'
    output.write_text(json.dumps(inventory, indent=2) + '\n')
    # Validate the full inventory using the same checks as the archive builder.
    kit.load_inventory(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--stage', required=True, help='existing empty admitted external directory')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.exit(1, 'inventory preparation requires Linux\n')
    try:
        output = prepare(json.loads(Path(args.config).read_text()), args.stage)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'inventory: {exc}\n')
    print(output)


if __name__ == '__main__':
    main()
