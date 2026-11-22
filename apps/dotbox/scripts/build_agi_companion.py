#!/usr/bin/env python3
"""Stage the optional Linux AGI developer companion from explicit local inputs.

This does not build native code, download dependencies, launch a guest, or change
DotBox's DOSBox-X backend. Canonical AGI APIs and their small parser subset are
copied unchanged from one immutable shared-source commit. Runtime binaries and
the observed five-library closure must match their qualified identities.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import textwrap
import zipfile


QEMU_SHA256 = "cf5a17c156389d67002e36648db0da6545f4733deb7a967ddb72e08a38c41c78"
SCENE_SHA256 = "3a5d0e8158aed4c4e6d7ec782d41b971f7caee57a7e2319c4051cc017fea6c51"
DEFAULT_SOURCE_COMMIT = "5c59c9a03e8992149fcc2643dcf15298faa14816"
RESERVE = 40 * 1024**3
PARSER_FILES = (
    "__init__.py", "agi.py", "agi_layout.py", "agi_picture.py",
    "agi_resources.py", "agi_source.py", "processor.py", "native_inno.py",
)
LIBRARIES = {
    "libpixman-1.so.0": "806ef6cd6ff8dace4332b8d611afe2f1c5ec0c1b743ea7ed0ebd48ed307618cd",
    "libz.so.1": "6c13931760210e8b391b63a337dfe4071346c4ad6e3827694edb7b6989bb16dd",
    "libglib-2.0.so.0": "980ab64e995225de1543779e3bafafac9d705904d42ca3b5eb76e7a336cc5e1d",
    "libatomic.so.1": "9558489f171274c220104894258f483055853ed8a23d4ff754c850ce55765aa2",
    "libpcre2-8.so.0": "92e9b4167f9bbc237ca8f5526d82ee99ec9f8dbd0270ef1dd0ab24e2217f48e3",
}


VERIFY_SCRIPT = r'''
#!/usr/bin/env python3
"""Verify the companion's sealed payload without importing or executing it."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import stat
import sys

def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def verify(root):
    root = root.resolve()
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    if manifest.get('schema') != 'dotbox-agi-developer-companion-1':
        raise ValueError('Unsupported companion manifest')
    expected = {item['path'] for item in manifest['files']}
    if len(expected) != len(manifest['files']) or 'MANIFEST.json' in expected:
        raise ValueError('Duplicate or self-referential manifest entry')
    for item in manifest['files']:
        rel = PurePosixPath(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Unsafe manifest path')
        path = root.joinpath(*rel.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unexpected payload symlink: ' + item['path'])
        if not path.is_file() or path.stat().st_size != item['bytes']:
            raise ValueError('Missing or resized payload: ' + item['path'])
        if digest(path) != item['sha256']:
            raise ValueError('Changed payload: ' + item['path'])
        if oct(stat.S_IMODE(path.stat().st_mode)) != item['mode']:
            raise ValueError('Changed payload mode: ' + item['path'])
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Unexpected payload symlink')
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = relative.as_posix()
        if name in expected or name in {'MANIFEST.json', '.python-path'}:
            continue
        if path.parent.name == '__pycache__' and path.suffix == '.pyc':
            source = relative.parent.parent / (path.name.split('.')[0] + '.py')
            if source.as_posix() in expected:
                continue
        raise ValueError('Unexpected payload file: ' + name)
    return {'status': 'verified', 'files': len(manifest['files']),
            'source_commit': manifest['source_commit'],
            'native_execution_performed': False}

if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parent), sort_keys=True))
'''


BOOTSTRAP_SCRIPT = r'''
#!/usr/bin/env python3
"""Create a new, offline CPython 3.12 environment for the optional companion."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
from verify_manifest import verify

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--prefix', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    verify(root)
    prefix = args.prefix.expanduser().resolve()
    if prefix.exists() or not prefix.parent.is_dir():
        raise ValueError('Prefix must be a new directory under an existing parent')
    check = ('import sys, platform; '
             'assert sys.implementation.name == "cpython"; '
             'assert sys.version_info[:2] == (3, 12); '
             'assert sys.platform == "linux"; '
             'assert platform.machine().lower() in ("x86_64", "amd64")')
    env = {key: value for key, value in os.environ.items() if not key.startswith('PIP_')}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    subprocess.run([args.python, '-I', '-c', check], check=True, timeout=10, env=env)
    subprocess.run([args.python, '-I', '-m', 'venv', str(prefix)], check=True,
                   timeout=60, env=env)
    python = prefix / 'bin/python'
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    wheels = [str(root / 'wheels' / item['name']) for item in manifest['wheels']]
    if len(wheels) != 2:
        raise ValueError('Expected exactly the pinned core and Pillow wheels')
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--disable-pip-version-check', *wheels], check=True,
                   timeout=60, env=env)
    subprocess.run([str(python), '-I', '-c',
                    'import fdisbull_core, PIL; '
                    'assert fdisbull_core.__version__ == "0.1.0.dev7"; '
                    'assert PIL.__version__ == "12.3.0"'],
                   check=True, timeout=10, env=env)
    (root / '.python-path').write_text(str(python) + '\n')
    print(json.dumps({'status': 'installed', 'python': str(python),
                      'launcher': str(root / 'bin/agi-python')}, sort_keys=True))

if __name__ == '__main__':
    main()
'''


LAUNCHER = r'''
#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${DOTBOX_AGI_PYTHON:-}" ]; then
    PYTHON=$DOTBOX_AGI_PYTHON
elif [ -f "$ROOT/.python-path" ]; then
    IFS= read -r PYTHON < "$ROOT/.python-path"
else
    echo "Set DOTBOX_AGI_PYTHON to the base release's Python or run bootstrap.py first." >&2
    exit 2
fi
if [ ! -x "$PYTHON" ]; then
    echo "The selected Python executable is unavailable: $PYTHON" >&2
    exit 2
fi
unset PYTHONHOME
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/api/src:$ROOT/api/native/qemu-agi"
export LD_LIBRARY_PATH="$ROOT/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export DOTBOX_AGI_QEMU="$ROOT/runtime/bin/qemu-system-agi"
export DOTBOX_AGI_SCENE_LIBRARY="$ROOT/runtime/lib/libagi-scene.so"
"$PYTHON" -I -c 'import sys, platform; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12) and sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64"), "This companion requires Linux x86_64 and CPython 3.12"'
exec "$PYTHON" "$@"
'''


DEMO_SCRIPT = r'''
#!/usr/bin/env python3
"""Compare an authored CPU-rendered scene with prepared explicit composition.

Only authored LOGIC, PIC and VIEW bytes are used. The plan is supplied directly;
this does not claim automatic scene recovery or original-game compatibility.
Run through bin/agi-python and choose a new output directory outside the kit.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter_ns

from PIL import Image, ImageDraw
from fdisbull.native_inno import NativeInno
from runtime_pack import build_package, dump_package
from runtime_harness import QemuAGIRuntime
from prepared_scene import (
    DecodedAssetCache, PreparedSceneAssets, PreparedSceneRenderer, PLAN_SCHEMA,
    PROFILE,
)

QEMU_SHA256 = 'cf5a17c156389d67002e36648db0da6545f4733deb7a967ddb72e08a38c41c78'
SCENE_SHA256 = '3a5d0e8158aed4c4e6d7ec782d41b971f7caee57a7e2319c4051cc017fea6c51'
PALETTE = [
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255),
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.expanduser().resolve()
    if out.exists() or not out.parent.is_dir():
        raise ValueError('Output must be a new directory under an existing parent')
    binary = Path(os.environ['DOTBOX_AGI_QEMU'])
    library = Path(os.environ['DOTBOX_AGI_SCENE_LIBRARY'])
    if sha256(binary.read_bytes()).hexdigest() != QEMU_SHA256:
        raise ValueError('Unexpected AGI CPU binary')
    if sha256(library.read_bytes()).hexdigest() != SCENE_SHA256:
        raise ValueError('Unexpected prepared-scene renderer')
    started = perf_counter_ns()
    # One loop, one 8x8 cel. Each row has two authored four-pixel runs.
    rows = b''.join(bytes([0xA4, 0xE4, 0]) if y % 2 == 0
                    else bytes([0xE4, 0xA4, 0]) for y in range(8))
    view = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 8, 8, 15]) + rows
    picture = bytes([0xF0, 1, 0xF8, 0, 0, 0xFF])  # blue background
    # v50=7; load/draw PIC2 through v51; create and draw actor1 using VIEW7.
    code = bytes([3, 50, 7, 3, 51, 2, 24, 51, 25, 51, 30, 7, 33, 1,
                  41, 1, 7, 37, 1, 76, 100, 54, 1, 8, 35, 1, 70, 1, 0])
    package = dump_package(build_package(
        logics=[{'id': 0, 'code': code, 'messages': []}],
        pictures=[{'id': 2, 'data': picture}],
        views=[{'id': 7, 'data': view}],
    ))
    package_preparation_ns = perf_counter_ns() - started
    package_sha = sha256(package).hexdigest()
    plan = {'schema': PLAN_SCHEMA, 'profile': PROFILE, 'package_sha256': package_sha,
            'background': {'picture': 2}, 'layers': [
                {'actor_id': 1, 'view': 7, 'loop': 0, 'cel': 0,
                 'x': 76, 'y': 100, 'priority': 8}]}
    assets = PreparedSceneAssets(package, cache=DecodedAssetCache())
    renderer = PreparedSceneRenderer(library, expected_sha256=SCENE_SHA256)
    cold = renderer.render(plan, assets)
    warm = renderer.render(plan, assets)
    # Independent expected planes from the authored rectangle and run colors.
    visual = bytearray([1]) * (160 * 168)
    priority = bytearray([4]) * (160 * 168)
    for row in range(8):
        at = (93 + row) * 160 + 76
        colors = [10] * 4 + [14] * 4 if row % 2 == 0 else [14] * 4 + [10] * 4
        visual[at:at + 8] = bytes(colors)
        priority[at:at + 8] = bytes([8]) * 8
    assert cold['visual'] == warm['visual'] == bytes(visual)
    assert cold['priority'] == warm['priority'] == bytes(priority)
    native_started = perf_counter_ns()
    with QemuAGIRuntime(binary, package, timeout=10) as vm:
        process = vm.process
        native_launch_ns = perf_counter_ns() - native_started
        vm.configure(mask=3, capacity=128)
        run_started = perf_counter_ns()
        state = vm.run(step_budget=100)
        native = vm.scene()
        native_execute_capture_ns = perf_counter_ns() - run_started
        inputs = vm.scene_inputs()
        assert state['guest']['status'] == 'return'
        assert state['guest']['variables'][50] == 7
        assert inputs['scene']['draw_order'] == [1]
        actor = inputs['scene']['actors'][0]
        assert all(actor[key] == value for key, value in {
            'id': 1, 'view': 7, 'loop': 0, 'cel': 0,
            'x': 76, 'y': 100, 'priority': 8}.items())
        assert bytes.fromhex(native['visual']) == bytes(visual)
        assert bytes.fromhex(native['priority']) == bytes(priority)
    assert process.poll() is not None, 'Native child was not reaped'
    assert NativeInno.__module__ == 'fdisbull.native_inno'
    out.mkdir()
    (out / 'authored-package.json').write_bytes(package)
    (out / 'authored-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    comparison = Image.new('RGB', (1280, 720), '#161b22')
    for offset, plane in ((0, bytes.fromhex(native['visual'])), (640, warm['visual'])):
        indexed = Image.frombytes('P', (160, 168), plane)
        indexed.putpalette([component for rgb in PALETTE for component in rgb] + [0] * 720)
        scene = indexed.convert('RGB').resize((640, 672), Image.Resampling.NEAREST)
        comparison.paste(scene, (offset, 48))
    draw = ImageDraw.Draw(comparison)
    draw.text((18, 16), 'AGI CPU: authored LOGIC executed', fill='white', font_size=18)
    draw.text((658, 16), 'Prepared scene: no AGI CPU execution', fill='white', font_size=18)
    comparison.save(out / 'authored-scene-comparison.png')
    report = {
        'schema': 'dotbox-agi-companion-authored-smoke-1', 'status': 'passed',
        'scope': 'One authored package and explicit scene plan; Linux x86_64 only.',
        'binary_sha256': QEMU_SHA256, 'scene_library_sha256': SCENE_SHA256,
        'package_sha256': package_sha, 'visual_sha256': sha256(visual).hexdigest(),
        'priority_sha256': sha256(priority).hexdigest(),
        'native_status': state['guest']['status'], 'variable_50': 7,
        'native_and_prepared_planes_equal': True,
        'native_child_reaped': True, 'native_child_returncode': process.returncode,
        'timing_ns': {'package_preparation': package_preparation_ns,
                      'asset_preparation': assets.preparation_ns,
                      'renderer_load': renderer.preparation_ns,
                      'prepared_cold': cold['timing_ns']['total'],
                      'prepared_warm': warm['timing_ns']['total'],
                      'native_launch': native_launch_ns,
                      'native_execute_and_capture': native_execute_capture_ns},
        'timing_scope': 'One smoke sample; stages have different boundaries and are not throughput ratios.',
        'minimum_scene_inputs': ['package/resource identities', 'optional background picture',
                                'ordered actor/view/loop/cel/x/y/priority records'],
        'raw_asset_sizes': {'logic_code': len(code), 'picture': len(picture), 'view': len(view)},
        'cold_cache_delta': cold['cache_delta'], 'warm_cache_delta': warm['cache_delta'],
    }
    (out / 'smoke-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
'''


README = '''
# Optional AGI developer companion for DotBox

This separate Linux x86_64 kit packages the existing AGI CPU experiment and its
prepared scene renderer. Use it for authored AGI programs, bounded resource
inspection, native CPU capture, and explicit scene composition. DotBox's normal
play service continues to use its DOSBox-X package; this kit is not a
`dotbox serve` backend.

## Start with an installed Python

Use the base release's CPython 3.12 interpreter if it already has the bundled
`fdisbull-core==0.1.0.dev7` and `Pillow==12.3.0`. Give the launcher the exact
interpreter path:

```sh
python3 verify_manifest.py
DOTBOX_AGI_PYTHON=/path/to/dotbox-prefix/venv/bin/python \\
  bin/agi-python examples/authored_scene.py --output /private/new-agi-demo
```

Or create a separate CPython 3.12 environment using the two included wheels:

```sh
python3.12 bootstrap.py --prefix /private/new-agi-environment
bin/agi-python examples/authored_scene.py --output /private/new-agi-demo
```

The bootstrap verifies the sealed payload, refuses an existing destination,
uses `pip --no-index --no-deps`, and records its interpreter for the launcher.
It does not install the full fDisBull application. Runtime data and the demo's
output directory remain separate from the tool/source package.

## What the example checks

The example creates its own tiny LOGIC, PIC and VIEW resources. It executes the
LOGIC in the packaged CPU and independently composes its explicit scene plan
through the existing prepared renderer. Both visual and priority planes must
match independently specified pixels. The output includes a side-by-side PNG,
the authored inputs, preparation/composition timings, and a process-cleanup
receipt. A single smoke timing is not a throughput benchmark.

The minimal composition plan contains the package identity, an optional
background picture, and ordered records of actor, VIEW, loop, cel, x, y and
priority. Once the decoded assets are prepared, repeated composition needs no
LOGIC execution. Establishing such a plan from an original program remains a
separate evidence task.

## Existing APIs and bounded parser subset

The unchanged APIs and their contracts are under `api/native/qemu-agi/`:

- `runtime_pack.py`: explicit packages and bounded AGI v2 directory loading.
- `runtime_harness.py`: the native CPU, source-bound capture and bounded steps.
- `prepared_scene.py`: immutable asset preparation and ordered composition.
- `processor_harness.py`: native instruction records through the existing seam.
- `SCENE_PREPARATION.md` and `RUNTIME.md`: input contracts and limits.

The unchanged `api/src/fdisbull/` files are a small AGI and NativeInno parser
subset from the same source commit. They preserve their canonical namespace;
they are not an installed full fDisBull application. Non-AGI `NativeProcessor`
and `CILMethodProcessor` adapters in the unchanged `processor.py` are outside
this subset and need their separate application dependencies. `NativeInno`
supports only its declared Inno 5.6.2 Unicode/GOG layout and does not execute
installers. Supply your own authorized inputs explicitly.

`bin/agi-python` sets only this kit's API search paths, raw native executable,
renderer path and library path. It does not start a CPU until your API call
does so. Ordinary CPU calls retain ownership, hash and timeout checks.

## Native and source identities

- Native AGI CPU: `QEMU_HASH`.
- Prepared renderer: `SCENE_HASH`.
- Canonical shared source commit: `SOURCE_COMMIT`.
- Full prepared QEMU 10.0.13 corresponding source is in `sources/` with its
  complete file/link inventory. Build output is stored separately and is not
  included. The source archive excludes only generated overlay-location
  metadata and any VCS/cache directories; the normalized overlay receipt is
  retained in `sources/BUILD_PROVENANCE.json`.
- Renderer C/header/source notices are included unchanged alongside its API.
- The core wheel includes its license; its complete package source is also
  included under `sources/fdisbull-core/`.

`MANIFEST.json` binds every payload file. `sources/BUILD_PROVENANCE.json` records
the historical native build inputs/configuration and the fresh source identity
checks; it does not claim a reproducible binary rebuild during packaging.
Native and dependency notices are retained under `runtime/licenses/`.

## Platform and qualification

The five packaged support libraries are the exact observed Linux closure apart
from the host ABI: the Linux loader, libc, libm and glibc's CP437 conversion
module remain host requirements. Use a compatible Linux x86_64 host. macOS,
Windows, arbitrary-host portability, original-DOS equivalence and full-game
compatibility are not established by this kit. The explicit runtime profile is
nominal AGI 2.917 / Sarien-compatible; consult the unchanged runtime docs for
its supported command catalog and remaining limits.

This package contains tool binaries/source and an authored demo. Original game
files, private cases, saved machine states and prior test archives are excluded.
'''


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def copy_file(source: Path, target: Path, *, expected: str | None = None) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Expected ordinary explicit input: {source}")
    actual = digest(source)
    if expected is not None and actual != expected:
        raise ValueError(f"Input identity differs: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(stat.S_IMODE(source.stat().st_mode) & 0o777)
    if digest(target) != actual:
        raise ValueError(f"Copy verification failed: {target}")


def canonical_paths(repo: Path, commit: str, prefix: str) -> list[Path]:
    names = git(repo, "ls-tree", "-r", "--name-only", "-z", commit, "--", prefix)
    return [Path(os.fsdecode(name)) for name in names.split(b"\0") if name]


def copy_canonical(repo: Path, commit: str, relative: Path, target: Path) -> dict:
    expected = sha256(git(repo, "show", f"{commit}:{relative.as_posix()}")).hexdigest()
    copy_file(repo / relative, target, expected=expected)
    return {"path": relative.as_posix(), "sha256": expected}


def wheel_identity(path: Path, package: str, version: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(matches) != 1:
            raise ValueError("Expected one wheel distribution")
        metadata = archive.read(matches[0]).decode("utf-8")
        if not re.search(rf"^Name: {re.escape(package)}$", metadata, re.M | re.I) \
                or not re.search(rf"^Version: {re.escape(version)}$", metadata, re.M):
            raise ValueError("Wheel package/version differs from companion contract")
    if package.lower() == "pillow" and "cp312-cp312-manylinux_2_27_x86_64" not in path.name:
        raise ValueError("Expected the qualified CPython 3.12 Linux x86_64 Pillow wheel")
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path),
            "package": package, "version": version}


def archive_source(source: Path, target: Path) -> dict:
    """Retain source files and safe internal links, never following symlinks."""
    source = source.resolve()
    entries = []
    paths = []
    for top, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in {".git", "__pycache__"})
        for name in list(dirs):
            path = Path(top) / name
            if path.is_symlink():
                paths.append(path)
                dirs.remove(name)
        paths.extend(Path(top) / name for name in files
                     if name != ".fdisbull-agi-overlay.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0,
                                               compresslevel=6) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(paths):
                relative = path.relative_to(source).as_posix()
                info = archive.gettarinfo(str(path), arcname="qemu-10.0.13-agi/" + relative)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                info.mode &= 0o777
                if path.is_symlink():
                    link = os.readlink(path)
                    if Path(link).is_absolute() or not path.resolve().is_relative_to(source):
                        raise ValueError(f"External source link refused: {relative}")
                    archive.addfile(info)
                    entries.append({"path": relative, "type": "symlink", "target": link})
                elif info.isfile():
                    expected = digest(path)
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                    if digest(path) != expected:
                        raise ValueError(f"Source changed while archiving: {relative}")
                    entries.append({"path": relative, "type": "file", "bytes": info.size,
                                    "sha256": expected, "mode": oct(info.mode)})
                else:
                    raise ValueError(f"Unexpected source file type: {relative}")
    inventory = {"schema": "dotbox-agi-qemu-source-inventory-1", "files": entries,
                 "source_archive": target.name, "source_archive_sha256": digest(target),
                 "source_archive_bytes": target.stat().st_size}
    write_json(target.with_name("QEMU_SOURCE_INVENTORY.json"), inventory)
    return {key: value for key, value in inventory.items() if key != "files"} | {
        "file_count": sum(row["type"] == "file" for row in entries),
        "symlink_count": sum(row["type"] == "symlink" for row in entries),
        "uncompressed_file_bytes": sum(row.get("bytes", 0) for row in entries),
    }


def stage(args) -> dict:
    repo, out = args.repo.resolve(), args.output.resolve()
    qemu_source = args.qemu_source.resolve()
    if out.exists() or not out.parent.is_dir():
        raise ValueError("Output must be a new directory under an existing parent")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("An immutable source commit is required")
    git(repo, "cat-file", "-e", args.source_commit + "^{commit}")
    # Conservative admission covers source archive, inventory, payload and an
    # outer deliverable archive without depending on a compression estimate.
    source_bytes = sum(path.stat().st_size for path in qemu_source.rglob("*")
                       if path.is_file() and not path.is_symlink())
    free_before = shutil.disk_usage(out.parent).free
    if free_before - (3 * source_bytes + 128 * 1024**2) < RESERVE:
        raise RuntimeError("Source packaging would violate the 40 GiB reserve")
    if digest(args.runtime_binary) != QEMU_SHA256 or digest(args.scene_library) != SCENE_SHA256:
        raise ValueError("Qualified native input identity differs")
    for name, expected in LIBRARIES.items():
        if digest(args.runtime_cache / "lib" / name) != expected:
            raise ValueError(f"Qualified library identity differs: {name}")
    core = wheel_identity(args.core_wheel, "fdisbull-core", "0.1.0.dev7")
    pillow = wheel_identity(args.pillow_wheel, "Pillow", "12.3.0")
    native = repo / "native/qemu-agi"
    source_manifest = json.loads((native / "source-manifest.json").read_text())
    for relative, expected in source_manifest["source_files"].items():
        if digest(native / relative) != expected:
            raise ValueError(f"Canonical overlay manifest differs: {relative}")
        if relative.startswith("overlay/") and digest(qemu_source / relative.removeprefix("overlay/")) != expected:
            raise ValueError(f"Prepared native source differs: {relative}")
    applied = json.loads((qemu_source / ".fdisbull-agi-overlay.json").read_text())
    for relative, expected in applied["files"].items():
        if digest(qemu_source / relative) != expected:
            raise ValueError(f"Prepared source receipt differs: {relative}")
    scene_receipt = json.loads(args.scene_build_receipt.read_text())
    if scene_receipt["library_sha256"] != SCENE_SHA256:
        raise ValueError("Renderer build receipt differs")
    for relative, expected in scene_receipt["input_sha256"].items():
        if digest(native / relative) != expected:
            raise ValueError(f"Renderer corresponding source differs: {relative}")
    out.mkdir()
    copy_file(args.runtime_binary, out / "runtime/bin/qemu-system-agi", expected=QEMU_SHA256)
    copy_file(args.scene_library, out / "runtime/lib/libagi-scene.so", expected=SCENE_SHA256)
    for name, expected in LIBRARIES.items():
        copy_file(args.runtime_cache / "lib" / name, out / "runtime/lib" / name, expected=expected)
    runtime_cache = json.loads((args.runtime_cache / "RUNTIME_CACHE.json").read_text())
    for item in runtime_cache["licenses"]:
        name = Path(item["path"]).name
        copy_file(args.runtime_cache / "licenses" / name,
                  out / "runtime/licenses" / name, expected=item["sha256"])
    copied_sources = []
    for relative in canonical_paths(repo, args.source_commit, "native/qemu-agi"):
        copied_sources.append(copy_canonical(repo, args.source_commit, relative, out / "api" / relative))
    for name in PARSER_FILES:
        relative = Path("src/fdisbull") / name
        copied_sources.append(copy_canonical(repo, args.source_commit, relative, out / "api" / relative))
    for relative in canonical_paths(repo, args.source_commit, "packages/fdisbull-core"):
        copied_sources.append(copy_canonical(repo, args.source_commit, relative,
            out / "sources/fdisbull-core" / relative.relative_to("packages/fdisbull-core")))
    for name in ("LICENSE", "COPYING"):
        if (repo / name).is_file():
            copied_sources.append(copy_canonical(repo, args.source_commit, Path(name), out / "api" / name))
    for path in (args.core_wheel, args.pillow_wheel):
        copy_file(path, out / "wheels" / path.name)
    for name, text in (("verify_manifest.py", VERIFY_SCRIPT), ("bootstrap.py", BOOTSTRAP_SCRIPT),
                       ("bin/agi-python", LAUNCHER), ("examples/authored_scene.py", DEMO_SCRIPT)):
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip())
        path.chmod(0o755)
    readme = textwrap.dedent(README).lstrip().replace("QEMU_HASH", QEMU_SHA256)
    readme = readme.replace("SCENE_HASH", SCENE_SHA256).replace("SOURCE_COMMIT", args.source_commit)
    (out / "README.md").write_text(readme)
    print(json.dumps({"stage": "payload_verified", "output": str(out),
                      "canonical_files": len(copied_sources)}, sort_keys=True), flush=True)
    source_archive = archive_source(qemu_source, out / "sources/qemu-10.0.13-agi-source.tar.gz")
    build_receipt = json.loads((args.build_provenance / "compile-01.json").read_text())
    configure_receipt = json.loads((args.build_provenance / "configure-01.json").read_text())
    if build_receipt["binary"]["sha256"] != QEMU_SHA256 or build_receipt["returncode"] != 0:
        raise ValueError("Native build receipt does not bind the qualified binary")
    provenance = {
        "schema": "dotbox-agi-companion-source-provenance-1",
        "shared_repository": "https://github.com/seeker-cyber-maker/fDisBull",
        "source_commit": args.source_commit,
        "canonical_copied_inputs": copied_sources,
        "qemu_upstream_version": source_manifest["qemu_version"],
        "declared_upstream_archive_sha256": source_manifest["archive_sha256"],
        "qemu_source_archive": source_archive,
        "applied_overlay": {key: value for key, value in applied.items() if key != "source"},
        "historical_native_build": {
            "compile_receipt_sha256": digest(args.build_provenance / "compile-01.json"),
            "configure_receipt_sha256": digest(args.build_provenance / "configure-01.json"),
            "configure_arguments": configure_receipt["command"][1:],
            "build_command": ["ninja", "-j2", "qemu-system-agi"],
            "finished_at": build_receipt["finished_at"],
            "binary_sha256": QEMU_SHA256,
            "compilation_during_packaging": False,
        },
        "renderer_build": {
            "receipt_sha256": digest(args.scene_build_receipt),
            "input_sha256": scene_receipt["input_sha256"],
            "compiler": scene_receipt["compiler"],
            "command": ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC",
                        "-shared", "api/native/qemu-agi/sarien_scene.c", "-o", "libagi-scene.so"],
            "library_sha256": SCENE_SHA256,
        },
        "host_requirements": ["Linux x86_64", "CPython 3.12", "compatible ELF loader/libc/libm",
                              "glibc CP437 conversion module"],
        "source_identity_checks": "All canonical copied inputs and both native overlays verified by SHA256.",
        "scope": "No prior evidence archive, game resource, saved state or private case is included.",
    }
    write_json(out / "sources/BUILD_PROVENANCE.json", provenance)
    copy_file(Path(__file__).resolve(), out / "sources/build_agi_companion.py")
    rows = []
    for path in sorted(out.rglob("*")):
        if path.is_file():
            rows.append({"path": path.relative_to(out).as_posix(), "bytes": path.stat().st_size,
                         "sha256": digest(path), "mode": oct(stat.S_IMODE(path.stat().st_mode))})
    result = {
        "schema": "dotbox-agi-developer-companion-1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "native_binary_sha256": QEMU_SHA256, "scene_library_sha256": SCENE_SHA256,
        "wheels": [core, pillow], "files": rows,
        "self_exclusion": "MANIFEST.json is excluded; final archive SHA256 is recorded externally.",
        "native_execution_performed_by_packager": False,
        "free_bytes_before": free_before, "free_bytes_after": shutil.disk_usage(out).free,
        "minimum_free_bytes": RESERVE,
    }
    if result["free_bytes_after"] < RESERVE:
        raise RuntimeError("Post-packaging storage reserve violated")
    write_json(out / "MANIFEST.json", result)
    return {key: value for key, value in result.items() if key != "files"} | {
        "output": str(out), "payload_file_count": len(rows),
        "payload_bytes": sum(row["bytes"] for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
    for option in ("runtime-binary", "runtime-cache", "qemu-source", "scene-library",
                   "scene-build-receipt", "build-provenance", "core-wheel", "pillow-wheel", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    print(json.dumps(stage(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
