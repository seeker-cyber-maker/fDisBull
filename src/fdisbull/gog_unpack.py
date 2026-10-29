"""Read GOG Inno Setup payloads using the host's native innoextract program."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile


MANIFEST = 'gog-unpack-manifest.json'


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _inputs(path):
    # These adjacent parts are provenance candidates, not proof of consumption.
    prefix = path.stem.casefold() + '-'
    parts = [p for p in path.parent.iterdir() if p.is_file()
             and p.name.casefold().startswith(prefix) and p.suffix.casefold() == '.bin']
    return [{'name': p.name, 'size': p.stat().st_size, 'sha256': _digest(p)}
            for p in [path, *sorted(parts)]]


def _run(tool, args, timeout):
    try:
        result = subprocess.run([tool, *args], capture_output=True, text=True,
                                encoding='utf-8', errors='strict', timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ValueError(f'innoextract timed out after {timeout} seconds') from error
    except UnicodeError as error:
        raise ValueError('innoextract returned a non-UTF-8 inventory or diagnostic') from error
    if result.returncode:
        diagnostic = (result.stderr or result.stdout).strip()[-4000:]
        raise ValueError(f'innoextract failed ({result.returncode}): {diagnostic}')
    return result


def _safe_inventory(text):
    files = []
    seen = set()
    for name in text.splitlines():
        if not name:
            continue
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or '\\' in name or ':' in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or path.as_posix() != name):
            raise ValueError(f'Unsafe or ambiguous installer member: {name!r}')
        folded = name.casefold()
        if folded in seen or folded == MANIFEST.casefold():
            raise ValueError(f'Colliding installer member: {name!r}')
        seen.add(folded)
        files.append(name)
    if not files:
        raise ValueError('No files matched the installer selection')
    return sorted(files)


def _prepare(path, include, timeout):
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError('timeout must be an integer from 1 to 3600 seconds')
    if include is None:
        include = []
    if not isinstance(include, list) or any(not isinstance(p, str) or not p
                                           or '\x00' in p for p in include):
        raise ValueError('include must be a list of nonempty innoextract path filters')
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError('Expected a local GOG Inno Setup installer file')
    tool = shutil.which('innoextract')
    if tool is None:
        raise ValueError('Install native innoextract first (macOS: brew install innoextract; '
                         'Debian/Ubuntu: apt install innoextract). Wine is not required.')
    versions = _run(tool, ['--version'], timeout).stdout.splitlines()
    if not versions or not versions[0].startswith('innoextract '):
        raise ValueError('Native reader did not identify itself as innoextract')
    version = versions[0]
    options = ['--silent', '--color=0', '--progress=0', '--no-extract-unknown']
    for item in include:
        options += ['--include', item]
    inputs = _inputs(source)
    inventory = _run(tool, ['--list', *options, str(source)], timeout)
    files = _safe_inventory(inventory.stdout)
    return source, tool, options, dict(
        format='fdisbull-gog-unpack-1', installer=str(source), inputs=inputs,
        adjacent_parts='Matching basename-*.bin files hashed; use is not individually traced.',
        extractor=dict(path=tool, version=version), include=include, files=files,
        warnings=inventory.stderr.strip(), installer_executed=False)


def list_gog(path, *, include=None, timeout=300):
    """Return a read-only, filtered installer inventory; never launch its EXE."""
    source, _, _, result = _prepare(path, include, timeout)
    if _inputs(source) != result['inputs']:
        raise ValueError('Installer inputs changed during inventory')
    return result


def unpack_gog(path, output, *, include=None, timeout=300):
    """Extract to a new directory, verify the listing, and retain file hashes."""
    destination = Path(output).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output already exists; choose a new private directory')
    if not destination.parent.is_dir():
        raise ValueError('Output parent must already be a directory')
    source, tool, options, result = _prepare(path, include, timeout)
    # Exclusive mkdir owns the new destination even if another writer races us.
    # Staging and final payload share a filesystem, so publication moves files
    # without copying large disc images a second time.
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix='.inno-', dir=destination) as temp:
            staging = Path(temp)
            extraction = _run(tool, ['--extract', *options, '--output-dir',
                                     str(staging), str(source)], timeout)
            files = []
            for item in sorted(staging.rglob('*')):
                mode = item.lstat().st_mode
                if stat.S_ISDIR(mode):
                    continue
                if not stat.S_ISREG(mode):
                    raise ValueError('Extractor produced a link or non-regular file')
                name = item.relative_to(staging).as_posix()
                with item.open('rb') as stream:
                    magic = stream.read(4)
                files.append(dict(path=name, size=item.stat().st_size, sha256=_digest(item),
                    executable_candidate=(item.suffix.casefold() in ('.exe', '.com')
                                          or magic[:2] in (b'MZ', b'ZM'))))
            if sorted(i['path'] for i in files) != result['files']:
                raise ValueError('Extracted files do not match the selected inventory')
            if _inputs(source) != result['inputs']:
                raise ValueError('Installer inputs changed during extraction')
            result.update(output=str(destination), files=files,
                          manifest=str(destination / MANIFEST),
                          warnings='\n'.join(filter(None, [result['warnings'], extraction.stderr.strip()])))
            for item in staging.iterdir():
                item.rename(destination / item.name)
        with (destination / MANIFEST).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write('\n')
        return result
    except BaseException:
        # Only the exclusively created directory belongs to this attempt.
        shutil.rmtree(destination)
        raise
