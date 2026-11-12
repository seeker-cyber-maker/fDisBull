"""Build and select a private, provenance-bound minimal FreeDOS 1.4 runtime.

The component is data only; it neither installs QEMU nor launches a guest.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

FORMAT = 'fdisbull-freedos-runtime-1'
VERSION = '1.4-minimal-1'
LOCK = {
    'boot': '552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc',
    'kernel': '43ed55fec6e795bb24e658302c7fae9eec9eb8dfeaba15734317b3f8302706d6',
    'freecom': '3a7cfa03cce242031926cd67b69e1fd030d1c27127885d927629945f3137b6f0',
}
REQUIRED = ('system.img', 'source/kernel.zip', 'source/freecom.zip', 'NOTICE.md', 'recipe.json', 'build.py')
CONFIG = b'SWITCHES=/F\r\nFILES=40\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\nSHELL=C:\\COMMAND.COM C:\\ /E:2048 /P=C:\\FDAUTO.BAT\r\n'
BATCH = b'@echo off\r\nSET FDISBULL_RUNTIME=1\r\nC:\r\nCD \\\r\n'


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _input(path, expected, limit):
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file() or p.stat().st_size > limit:
        raise ValueError('Invalid or oversized FreeDOS input')
    data = p.read_bytes()
    if _digest(data) != expected:
        raise ValueError('FreeDOS input hash does not match the locked release')
    return data


def _member(data, name, limit):
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        matches = [item for item in archive.infolist() if item.filename == name]
        if len(matches) != 1 or matches[0].file_size > limit or matches[0].is_dir():
            raise ValueError('FreeDOS package member is missing or oversized')
        return archive.read(matches[0])


def _file(root, relative):
    path = root / relative
    current = root
    for part in Path(relative).parts:
        if part in ('.', '..'):
            raise ValueError('Invalid FreeDOS component path')
        current = current / part
        if current.is_symlink():
            raise ValueError('FreeDOS component paths cannot contain symlinks')
    if not path.is_file():
        raise ValueError('FreeDOS component file missing: ' + relative)
    return path


def resolve_runtime(path=None):
    """Validate the selected component and return its root, image and manifest."""
    chosen = path if path is not None else os.environ.get('FDISBULL_FREEDOS_RUNTIME')
    if not chosen:
        raise ValueError('Select a FreeDOS runtime path or set FDISBULL_FREEDOS_RUNTIME')
    root = Path(chosen).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('FreeDOS runtime must be a directory')
    manifest_path = _file(root, 'manifest.json')
    if manifest_path.stat().st_size > 65536:
        raise ValueError('FreeDOS runtime manifest is oversized')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('format') != FORMAT
            or manifest.get('version') != VERSION or set(manifest.get('files', {})) != set(REQUIRED)):
        raise ValueError('Invalid FreeDOS runtime manifest')
    for name in REQUIRED:
        record = manifest['files'][name]
        file = _file(root, name)
        if (not isinstance(record, dict) or set(record) != {'size', 'sha256'}
                or type(record['size']) is not int or not 0 <= record['size'] <= 8_000_000
                or file.stat().st_size != record['size'] or _digest(file.read_bytes()) != record['sha256']):
            raise ValueError('FreeDOS runtime file identity differs: ' + name)
    for name, key in [('source/kernel.zip', 'kernel'), ('source/freecom.zip', 'freecom')]:
        if manifest['files'][name]['sha256'] != LOCK[key]:
            raise ValueError('FreeDOS source package is not the locked release')
    return dict(root=str(root), image=str(root / 'system.img'), manifest=manifest)


def runtime_info(path=None):
    """Return the verified component identity, without exposing host input paths."""
    return resolve_runtime(path)['manifest']


def _recipe_files():
    if __package__:
        from importlib.resources import files
        resources = files('fdisbull').joinpath('data')
        return {'NOTICE.md': resources.joinpath('freedos-runtime-notice.txt').read_bytes(),
                'recipe.json': resources.joinpath('freedos-runtime-recipe.json').read_bytes()}
    # A copied build.py in the portable component uses its sibling inputs.
    source_tree = Path(__file__).resolve().parent
    return {name: (source_tree / name).read_bytes() for name in ('NOTICE.md', 'recipe.json')}


def prepare_runtime(boot_image, kernel_package, freecom_package, output, *, mtools_dir):
    """Build a new private component; all inputs must match the release lock.

    Output must not exist. Failed builds remain for inspection and are never
    adopted as valid components without the completed manifest.
    """
    boot = _input(boot_image, LOCK['boot'], 1_474_560)
    kernel = _input(kernel_package, LOCK['kernel'], 4_000_000)
    freecom = _input(freecom_package, LOCK['freecom'], 4_000_000)
    kern = _member(kernel, 'BIN/KERNL86.SYS', 100_000)
    shell = _member(freecom, 'BIN/COMMAND.COM', 200_000)
    # Require both source payloads before creating anything.
    _member(kernel, 'SOURCE/KERNEL/SOURCES.ZIP', 2_000_000)
    _member(freecom, 'SOURCE/FREECOM/SOURCES.ZIP', 3_000_000)
    out = Path(output).expanduser().absolute()
    out.mkdir(mode=0o700)
    (out / 'source').mkdir(); (out / 'staging').mkdir()
    (out / 'source/kernel.zip').write_bytes(kernel)
    (out / 'source/freecom.zip').write_bytes(freecom)
    (out / 'staging/boot.img').write_bytes(boot)
    for name, data in [('KERNEL.SYS', kern), ('COMMAND.COM', shell), ('FDCONFIG.SYS', CONFIG), ('FDAUTO.BAT', BATCH)]:
        (out / 'staging' / name).write_bytes(data)
    for name, data in _recipe_files().items():
        (out / name).write_bytes(data)
    (out / 'build.py').write_bytes(Path(__file__).read_bytes())
    img = out / 'system.img'
    img.write_bytes(bytes(len(boot)))
    tools = Path(mtools_dir).expanduser().resolve(strict=True)
    # -B preserves the FreeDOS boot loader, while mformat builds a clean FAT12.
    subprocess.run([str(tools / 'mformat'), '-i', str(img), '-f', '1440', '-B', str(out / 'staging/boot.img'), '::'],
                   check=True, capture_output=True, timeout=30)
    for name in ('KERNEL.SYS', 'COMMAND.COM', 'FDCONFIG.SYS', 'FDAUTO.BAT'):
        subprocess.run([str(tools / 'mcopy'), '-i', str(img), str(out / 'staging' / name), '::' + name],
                       check=True, capture_output=True, timeout=30)
    for name, expected in [('::/KERNEL.SYS', kern), ('::/COMMAND.COM', shell)]:
        result = subprocess.run([str(tools / 'mtype'), '-i', str(img), name],
                                check=True, capture_output=True, timeout=30)
        if result.stdout != expected:
            raise ValueError('Built FreeDOS image binary does not match its source package')
    files = {name: dict(size=(out / name).stat().st_size, sha256=_digest((out / name).read_bytes())) for name in REQUIRED}
    manifest = dict(format=FORMAT, version=VERSION, files=files,
                    boot_source_sha256=LOCK['boot'], boot_validation='pending')
    (out / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    resolve_runtime(out)
    with zipfile.ZipFile(out / 'freedos-runtime.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json', *REQUIRED):
            archive.write(out / name, name)
    return resolve_runtime(out)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Build a locked FreeDOS runtime component')
    parser.add_argument('--boot-image', required=True)
    parser.add_argument('--kernel-package', required=True)
    parser.add_argument('--freecom-package', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mtools-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_runtime(args.boot_image, args.kernel_package, args.freecom_package,
                                     args.output, mtools_dir=args.mtools_dir)['manifest'], sort_keys=True))
