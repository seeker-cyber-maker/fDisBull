#!/usr/bin/env python3
"""Stage the bounded Linux/CPython 3.12 DotBox offline development bundle.

This copies already built inputs. It never compiles or executes a native binary,
installs a package, fetches a dependency, or publishes a release.
The native source archive requires its SOURCE_ARCHIVE_RECEIPT.json from source
preparation; its hash, size, recipe and upstream identity are checked here.
"""
import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RESERVE = 40 * 1024 ** 3
EXTRA_ALLOWANCE = 16 * 1024 ** 2
PROVENANCE = (
    'runtime-closure.json',
    'evidence/dependencies.json',
    'evidence/source-audit.json',
    'evidence/native-bounded-wait-receipt.json',
    'evidence/recovered-static-elf-closure.json',
)


def checked_path(value, *, directory=False, new=False):
    path = Path(value).expanduser().absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Symlink path refused: ' + str(path))
    if new:
        if path.exists():
            raise ValueError('Output already exists: ' + str(path))
        if not path.parent.is_dir():
            raise ValueError('Output parent must already exist: ' + str(path.parent))
    elif directory and not path.is_dir():
        raise ValueError('Expected a directory: ' + str(path))
    elif not directory and not path.is_file():
        raise ValueError('Expected a regular file: ' + str(path))
    return path


def files_under(root):
    result = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink payload refused: ' + str(path))
        if path.is_file():
            result.append(path)
        elif not path.is_dir():
            raise ValueError('Special payload file refused: ' + str(path))
    return result


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def admit_space(parent, growth=0):
    free = shutil.disk_usage(parent).free
    if free - growth < RESERVE:
        raise ValueError(f'40 GiB build reserve would be crossed: free={free}, growth={growth}')
    return free


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


def copy(source, target):
    checked_path(source)
    admit_space(target.parent, source.stat().st_size)
    shutil.copyfile(source, target)
    target.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
    if digest(target) != digest(source):
        raise ValueError('Copied file changed: ' + str(source))


def wheel_info(path, expected):
    with zipfile.ZipFile(path) as wheel:
        metadata = [name for name in wheel.namelist() if name.endswith('.dist-info/METADATA')]
        wheel_metadata = [name for name in wheel.namelist() if name.endswith('.dist-info/WHEEL')]
        if len(metadata) != 1 or len(wheel_metadata) != 1:
            raise ValueError('Wheel must have one distribution: ' + path.name)
        info = BytesParser().parsebytes(wheel.read(metadata[0]))
        name = re.sub(r'[-_.]+', '-', info['Name']).lower()
        if name not in expected or info['Version'] != expected[name]:
            raise ValueError('Unexpected wheel name/version: ' + path.name)
        tags = BytesParser().parsebytes(wheel.read(wheel_metadata[0])).get_all('Tag', [])
        if name in ('dotbox', 'fdisbull-core'):
            compatible = 'py3-none-any' in tags
        elif name == 'pillow':
            compatible = any(tag.startswith('cp312-cp312-') and
                             'linux' in tag and 'x86_64' in tag for tag in tags)
        else:
            compatible = any(re.match(r'^cp3(?:[8-9]|1[0-2])-abi3-.*linux.*x86_64', tag)
                             for tag in tags)
        if not compatible:
            raise ValueError('Wheel does not match the CPython 3.12/Linux x86_64 target: ' + path.name)
        expanded = sum(item.file_size for item in wheel.infolist())
    return {'name': name, 'version': info['Version'], 'path': 'wheelhouse/' + path.name,
            'sha256': digest(path), 'bytes': path.stat().st_size,
            'uncompressed_bytes': expanded, 'tags': tags}


def sanitized(value):
    """Retain native facts while removing historical absolute workspace paths."""
    if isinstance(value, dict):
        return {key: sanitized(item) for key, item in value.items()
                if key not in ('ldd_output', 'stdout', 'stderr')}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'/(?:workspace|home|tmp|var/tmp)/[^\s\"\'<>]+',
                      '<historical-local-path>', value)
    return value


def native_inputs(root):
    selected = []
    for name in ('bin', 'lib', 'licenses'):
        selected.extend(files_under(checked_path(root / name, directory=True)))
    if [p.relative_to(root).as_posix() for p in selected if p.parent == root / 'bin'] != ['bin/dosbox-x']:
        raise ValueError('Native bin directory must contain exactly dosbox-x')
    for name in ('bin/dosbox-x', 'lib/ld-linux-x86-64.so.2'):
        with checked_path(root / name).open('rb') as source:
            data = source.read(20)
        if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 62:
            raise ValueError('Expected a Linux x86_64 ELF: ' + name)
    prior = json.loads(checked_path(root / PROVENANCE[3]).read_text())
    recipe_hash = digest(ROOT / 'native/build-recipe.json')
    if prior['native']['recipe_sha256'] != recipe_hash:
        raise ValueError('Recovered native recipe differs from this source')
    if prior['native']['executable_sha256'] != digest(root / 'bin/dosbox-x'):
        raise ValueError('Recovered native binary differs from its receipt')
    closure = json.loads(checked_path(root / PROVENANCE[4]).read_text())
    if closure['missing_dt_needed_entries']:
        raise ValueError('Recovered static ELF closure is incomplete')
    entries = {item['path']: item for item in closure['entries']}
    actual = {'native/' + p.relative_to(root).as_posix(): p for p in selected
              if p.is_relative_to(root / 'bin') or p.is_relative_to(root / 'lib')}
    if set(entries) != set(actual):
        raise ValueError('Static closure inventory differs from native files')
    for name, path in actual.items():
        if digest(path) != entries[name]['sha256']:
            raise ValueError('Static closure identity mismatch: ' + name)
    for name in PROVENANCE:
        checked_path(root / name)
    return selected, recipe_hash


def source_receipt(archive, receipt_path, recipe_hash):
    receipt = json.loads(checked_path(receipt_path).read_text())
    recipe = json.loads((ROOT / 'native/build-recipe.json').read_text())
    if (receipt.get('format') != 'dotbox-prepared-source-archive-1'
            or receipt.get('status') != 'verified'
            or receipt.get('archive_readback_all_hashes_verified') is not True
            or receipt.get('filename') != archive.name
            or receipt.get('bytes') != archive.stat().st_size
            or receipt.get('sha256') != digest(archive)
            or receipt.get('recipe_sha256') != recipe_hash
            or receipt.get('upstream') != recipe['upstream']):
        raise ValueError('Native source archive does not match its verified recipe-bound receipt')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'wheelhouse', 'native-root', 'native-source', 'native-source-receipt',
                 'dotbox-sdist', 'core-sdist', 'source-commit'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    output = None
    created = False
    try:
        if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit):
            raise ValueError('source-commit must be an exact lowercase 40-character Git commit')
        repository = ROOT.parents[1]
        if (repository / '.git').exists():
            head = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
            if head != args.source_commit:
                raise ValueError('source-commit differs from the builder checkout HEAD')
            subprocess.run(['git', '-C', str(repository), 'diff', '--quiet', 'HEAD', '--'], check=True)
            source_binding = 'clean tracked checkout at exact supplied commit'
        else:
            source_binding = 'supplied commit declaration; standalone source has no Git attestation'
        output = checked_path(args.output, new=True)
        wheelhouse = checked_path(args.wheelhouse, directory=True)
        native = checked_path(args.native_root, directory=True)
        sources = [checked_path(value) for value in
                   (args.native_source, args.dotbox_sdist, args.core_sdist)]
        if len({path.name for path in sources}) != 3:
            raise ValueError('Source archive basenames must be distinct')
        if any(not re.fullmatch(r'[A-Za-z0-9_.-]+', path.name) for path in sources):
            raise ValueError('Source archive names must be simple basenames')
        version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
        expected = {'dotbox': version, 'fdisbull-core': '0.1.0.dev7',
                    'pillow': '12.3.0', 'iced-x86': '1.22.0'}
        wheels = files_under(wheelhouse)
        if len(wheels) != 4 or any(path.suffix != '.whl' or path.parent != wheelhouse for path in wheels):
            raise ValueError('wheelhouse must contain exactly the four runtime wheels and no other files')
        wheel_records = [wheel_info(path, expected) for path in wheels]
        if {item['name'] for item in wheel_records} != set(expected):
            raise ValueError('Each runtime distribution must occur exactly once')
        native_files, recipe_hash = native_inputs(native)
        source_receipt_path = checked_path(args.native_source_receipt)
        source_archive_receipt = source_receipt(sources[0], source_receipt_path, recipe_hash)
        templates = ROOT / 'release'
        for name in ('install.py', 'dotbox.sh', 'dotbox-dosbox-x.sh', 'START_HERE.md'):
            checked_path(templates / name)
        payload = wheels + sources + native_files
        planned = sum(path.stat().st_size for path in payload) + EXTRA_ALLOWANCE
        free_before = admit_space(output.parent, planned)
        output.mkdir(mode=0o700)
        created = True
        (output / 'INCOMPLETE').write_text('Bundle staging is incomplete. Do not install.\n')
        for path in payload:
            if path in wheels:
                relative = Path('wheelhouse') / path.name
            elif path in sources:
                relative = Path('sources') / path.name
            else:
                relative = Path('native') / path.relative_to(native)
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy(path, target)
        for name in PROVENANCE:
            source = native / name
            json_write(output / 'provenance' / Path(name).name,
                       {'format': 'dotbox-sanitized-native-provenance-1',
                        'source_file_sha256': digest(source), 'original_local_paths_removed': True,
                        'content': sanitized(json.loads(source.read_text()))})
        json_write(output / 'provenance/native-source-archive-receipt.json',
                   {'format': 'dotbox-sanitized-native-provenance-1',
                    'source_file_sha256': digest(source_receipt_path), 'original_local_paths_removed': True,
                    'content': sanitized(source_archive_receipt)})
        copy(ROOT / 'native/build-recipe.json', output / 'provenance/native-build-recipe.json')
        copy(ROOT / 'docs' / f'RELEASE-{version}.md', output / 'RELEASE_NOTES.md')
        copy(templates / 'install.py', output / 'install.py')
        (output / 'launchers').mkdir()
        for name in ('dotbox', 'dotbox-dosbox-x'):
            copy(templates / (name + '.sh'), output / 'launchers' / name)
            (output / 'launchers' / name).chmod(0o755)
        (output / 'START_HERE.md').write_text((templates / 'START_HERE.md').read_text().replace('@VERSION@', version))
        (output / 'START_HERE.md').chmod(0o644)
        lock = ''.join(f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n"
                       for item in sorted(wheel_records, key=lambda item: item['name']))
        (output / 'requirements.lock').write_text(lock)
        (output / 'requirements.lock').chmod(0o644)
        (output / 'INCOMPLETE').unlink()
        records = [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size,
                    'sha256': digest(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
                   for path in files_under(output)]
        native_bytes = sum(path.stat().st_size for path in native_files)
        source_bytes = sum(path.stat().st_size for path in sources)
        expanded = sum(item['uncompressed_bytes'] for item in wheel_records)
        manifest = {
            'format': 'dotbox-offline-release-1', 'version': version,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_commit': args.source_commit, 'source_binding': source_binding,
            'target': {'system': 'Linux', 'architecture': 'x86_64', 'implementation': 'CPython',
                       'python_major_minor': [3, 12]},
            'native': {'binary': 'native/bin/dosbox-x', 'loader': 'native/lib/ld-linux-x86-64.so.2',
                       'library_directory': 'native/lib', 'recipe_sha256': recipe_hash,
                       'binary_sha256': digest(native / 'bin/dosbox-x')},
            'wheels': sorted(wheel_records, key=lambda item: item['name']), 'files': records,
            'install_required_free_bytes': 2 * (native_bytes + source_bytes + expanded) + 128 * 1024 ** 2,
            'build_space': {'minimum_reserve_bytes': RESERVE, 'free_before': free_before,
                            'free_after': admit_space(output)},
            'scope': 'Offline development bundle; no native execution, desktop qualification, CI, tag or publication performed by this builder.'}
        json_write(output / 'manifest.json', manifest)
        checksum_records = records + [{'path': 'manifest.json', 'sha256': digest(output / 'manifest.json')}]
        (output / 'SHA256SUMS').write_text(''.join(f"{item['sha256']}  {item['path']}\n"
                                                for item in sorted(checksum_records, key=lambda item: item['path'])))
        (output / 'SHA256SUMS').chmod(0o644)
        print(json.dumps({'status': 'staged', 'output': str(output), 'version': version,
                          'manifest_sha256': digest(output / 'manifest.json'), 'payload_files': len(records),
                          'native_execution_performed': False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        if created:
            (output / 'INCOMPLETE').write_text(str(error) + '\n')
        print(json.dumps({'status': 'failed', 'error': str(error),
                          'partial_output': str(output) if created else None}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
