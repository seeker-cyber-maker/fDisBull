#!/usr/bin/env python3
"""Build the Linux x86-64 offline distribution from explicitly supplied artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import tomllib
import importlib.util
import zipfile
from email.parser import BytesParser
from email.policy import default

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
if not re.fullmatch(r'[0-9A-Za-z.+!]+', VERSION):
    raise ValueError('Invalid project version')
REQUIRED = {'fdisbull': VERSION, 'fdisbull-player': VERSION, 'iced-x86': '1.21.0', 'capstone': '5.0.9',
            'lief': '1.0.0', 'z3-solver': '5.3.2.0'}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()

def inspect_wheel(path, python_tag):
    parts = path.name[:-4].split('-')
    if len(parts) < 5 or not path.name.endswith('.whl'):
        raise ValueError(f'invalid wheel filename: {path.name}')
    py, abi, platform = parts[-3:]
    minor = int(python_tag[2:])
    py_ok = any((t == 'py3' and a == 'none') or
                (t == python_tag and a in ('none', 'abi3', python_tag)) or
                (t.startswith('cp3') and t[3:].isdigit() and int(t[2:]) <= minor and a == 'abi3')
                for t in py.split('.') for a in abi.split('.'))
    platform_ok = platform == 'any' or any((p.startswith('manylinux') or p == 'linux_x86_64')
                                           and p.endswith('_x86_64') for p in platform.split('.'))
    if not py_ok or not platform_ok:
        raise ValueError(f'wheel does not target {python_tag} Linux x86_64: {path.name}')
    with zipfile.ZipFile(path) as z:
        metadata = [n for n in z.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1]
        if len(metadata) != 1:
            raise ValueError(f'wheel must contain one METADATA: {path.name}')
        msg = BytesParser(policy=default).parsebytes(z.read(metadata[0]))
    name, version = normalize(msg['Name']), str(msg['Version'])
    if normalize(parts[0]) != name or parts[1] != version:
        raise ValueError(f'wheel filename and metadata disagree: {path.name}')
    if name in ('fdisbull', 'fdisbull-player'):
        spec = importlib.util.spec_from_file_location('_offline_dist_guard', ROOT / 'scripts/check_dist.py')
        guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
        guard.check_archive(path)
    return name, version

INSTALL = r'''#!/bin/sh
set -eu
unset PYTHONPATH PYTHONHOME
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 1 ]; then echo "Usage: $0 NEW_VENV_PATH" >&2; exit 2; fi
DEST=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")
if [ -e "$DEST" ] || [ -L "$DEST" ]; then echo "Destination already exists" >&2; exit 1; fi
cd "$HERE"
sha256sum -c SHA256SUMS
python3 -c 'import platform,sys; assert sys.version_info[:3] == (3,13,5), "Python 3.13.5 required"; assert sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 required"'
python3 -m venv "$DEST"
"$DEST/bin/python" -m pip install --no-index --find-links "$HERE/wheels" --require-hashes -r "$HERE/requirements.txt"
"$DEST/bin/python" -c 'import importlib.metadata as m; assert m.version("fdisbull") == "__FDISBULL_VERSION__"; assert m.version("fdisbull-player") == "__FDISBULL_VERSION__"; import fdisbull_player; import z3; x=z3.Int("x"); s=z3.Solver(); s.add(x+1 != 1+x); assert s.check()==z3.unsat; s=z3.Solver(); s.add(x+1 != x); assert s.check()==z3.sat; print("Installed fdisbull and fdisbull-player __FDISBULL_VERSION__; Z3 equivalent and counterexample checks passed")'
printf '%s\n' "DOSBox backend with private libraries: $HERE/bin/dosbox"
'''

def build(args):
    if not re.fullmatch(r'[0-9a-f]{40,64}', args.source_commit):
        raise ValueError('source commit must be a full lowercase hexadecimal object ID')
    if args.python_tag != 'cp313':
        raise ValueError('only cp313 / Python 3.13.5 is supported')
    wheels = sorted(Path(args.wheelhouse).glob('*.whl'))
    found = {}
    for wheel in wheels:
        if wheel.is_symlink():
            raise ValueError(f'wheel must not be a symlink: {wheel}')
        name, version = inspect_wheel(wheel, args.python_tag)
        if name in found:
            raise ValueError(f'duplicate wheel for {name}')
        found[name] = (version, wheel)
    for name, version in REQUIRED.items():
        if name not in found or found[name][0] != version:
            raise ValueError(f'required wheel missing or wrong version: {name}=={version}')
    if 'pillow' not in found:
        raise ValueError('required wheel missing: pillow')
    pv = found['pillow'][0].split('.')
    if not pv[0].isdigit() or not 10 <= int(pv[0]) < 13 or (int(pv[0]) == 10 and (len(pv) < 2 or int(pv[1]) < 4)):
        raise ValueError('Pillow version outside >=10.4,<13')
    # No optional or arbitrary data can enter via the wheelhouse.
    if set(found) != set(REQUIRED) | {'pillow'}:
        raise ValueError('wheelhouse contains unexpected distributions')
    backend = Path(args.backend)
    libs = [Path(p) for p in args.sdl_lib]
    if not libs or any(not re.fullmatch(r'libSDL2_net[^/]*\.so(?:\.[0-9]+)*', p.name) for p in libs):
        raise ValueError('at least one explicitly named SDL2_net shared library is required')
    if len({p.name for p in libs}) != len(libs):
        raise ValueError('SDL library names must be unique')
    for p in [backend, *libs, Path(args.source_companion), Path(args.backend_receipt), Path(args.patch_manifest),Path(args.dosbox_license),Path(args.sdl_license)]:
        if not p.is_file() or p.is_symlink():
            raise ValueError(f'input must be a regular non-symlink file: {p}')
    if not tarfile.is_tarfile(args.source_companion):
        raise ValueError('source companion must be a tar archive')
    receipt = json.loads(Path(args.backend_receipt).read_text())
    if receipt.get('source_commit') != args.source_commit or receipt.get('backend_sha256') != digest(backend):
        raise ValueError('backend receipt does not match source commit and backend bytes')
    manifest_data = json.loads(Path(args.patch_manifest).read_text())
    if receipt.get('patch_sha256') != manifest_data.get('patch_sha256') or receipt.get('upstream_commit') != manifest_data.get('baseline_commit'):
        raise ValueError('backend receipt and patch manifest disagree')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'fdisbull-{VERSION}-linux-x86_64-offline.tar.gz'
    suffix = '.tar.gz' if str(args.source_companion).endswith('.tar.gz') else '.tar'
    companion = out / (f'fdisbull-{VERSION}-linux-x86_64-source-companion' + suffix)
    if archive.exists() or companion.exists():
        raise ValueError('output already exists')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / f'fdisbull-{VERSION}-linux-x86_64-offline'
        for d in ('wheels', 'bin', 'lib', 'evidence','licenses'):
            (root / d).mkdir(parents=True, exist_ok=True)
        for _, wheel in found.values(): shutil.copyfile(wheel, root / 'wheels' / wheel.name)
        shutil.copyfile(backend, root / 'bin' / 'dosbox-x')
        (root / 'bin' / 'dosbox-x').chmod(0o755)
        (root/'bin'/'dosbox').write_text('#!/bin/sh\nset -eu\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport LD_LIBRARY_PATH="$HERE/../lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\nexec "$HERE/dosbox-x" "$@"\n')
        (root/'bin'/'dosbox').chmod(0o755)
        for p in libs: shutil.copyfile(p, root / 'lib' / p.name)
        shutil.copyfile(args.dosbox_license,root/'licenses'/'DOSBox-X-COPYING.txt')
        shutil.copyfile(args.sdl_license,root/'licenses'/'SDL2_net-copyright.txt')
        for p, name in [(Path(args.backend_receipt), 'backend-receipt'), (Path(args.patch_manifest), 'patch-manifest')]:
            shutil.copyfile(p, root / 'evidence' / name)
        shutil.copyfile(args.source_companion, companion)
        manifest = {'source_commit': args.source_commit, 'python': '3.13.5', 'platform': 'linux-x86_64',
                    'source_companion': companion.name, 'source_companion_sha256': digest(companion),
                    'backend_sha256': digest(backend), 'backend_receipt_sha256': digest(Path(args.backend_receipt)),
                    'patch_manifest_sha256': digest(Path(args.patch_manifest)),
                    'wheels': {n: {'version': v, 'filename': p.name, 'sha256': digest(p)} for n, (v, p) in sorted(found.items())}}
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        (root / 'requirements.txt').write_text(''.join(f'{n}=={v} --hash=sha256:{digest(p)}\n' for n, (v,p) in sorted(found.items())))
        (root/'README.txt').write_text(f'fDisBull {VERSION} Linux x86-64 offline kit, including standalone player and genuine Z3.\n'
            'Requires Python 3.13.5 and system SDL2, GL/X11, FreeType, PNG, ncurses, zlib and a compatible glibc.\n'
            'Run ./install.sh /absolute/path/to/NEW-venv; use bin/dosbox as the backend. Headless is default.\n'
            'No game assets, saved states or project databases are supplied. Existing projects are not changed.\n'
            f'Keep {companion.name} with this binary kit; manifest.json records its SHA-256 and source identity.\n'
            'The paired source includes the upstream GPL license; private SDL2_net notices are in licenses/.\n'
            'Z3 checks concern supplied bounded models and assumptions, not full recovered-program correctness.\n')
        (root / 'install.sh').write_text(INSTALL.replace('__FDISBULL_VERSION__', VERSION))
        (root / 'install.sh').chmod(0o755)
        files = sorted(p for p in root.rglob('*') if p.is_file())
        (root / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(root).as_posix()}\n' for p in files))
        # Fixed metadata and gzip timestamp give identical output for identical inputs.
        import gzip
        with archive.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz, tarfile.open(fileobj=gz, mode='w') as tar:
            for p in [root, *sorted(root.rglob('*'))]:
                info = tar.gettarinfo(str(p), arcname=str(p.relative_to(root.parent)))
                info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 0
                if p.is_file():
                    with p.open('rb') as f: tar.addfile(info, f)
                else: tar.addfile(info)
    return archive, companion

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('wheelhouse', 'backend', 'source-companion', 'source-commit', 'backend-receipt', 'patch-manifest', 'dosbox-license','sdl-license','output'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--sdl-lib', action='append', required=True)
    p.add_argument('--python-tag', default='cp313')
    args = p.parse_args()
    try:
        for result in build(args): print(result)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        p.error(str(exc))

if __name__ == '__main__': main()
