"""Safely unpack supported GOG Inno Setup payloads with fDisBull's native reader.

No subprocess, Wine, or external innoextract binary is needed. Unsupported
Inno versions and external slices fail closed instead of guessing file data.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import time

try:
    from .native_inno import NativeInno, InnoRefused, SUPPORTED
except ImportError:
    # Standalone source-only qualification outside the installed fDisBull package.
    from native_inno import NativeInno, InnoRefused, SUPPORTED

MANIFEST = 'gog-unpack-manifest.json'


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _inputs(path):
    prefix = path.stem.casefold() + '-'
    parts = [p for p in path.parent.iterdir() if p.is_file()
             and p.name.casefold().startswith(prefix) and p.suffix.casefold() == '.bin']
    return [{'name': p.name, 'size': p.stat().st_size, 'sha256': _digest(p)}
            for p in [path, *sorted(parts)]]


def _safe_inventory(files):
    seen = set()
    for name in files:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or '\\' in name or ':' in name or '\x00' in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or path.as_posix() != name):
            raise ValueError(f'Unsafe or ambiguous installer member: {name!r}')
        folded = name.casefold()
        if folded in seen or folded == MANIFEST.casefold():
            raise ValueError(f'Colliding installer member: {name!r}')
        seen.add(folded)
    if not files:raise ValueError('No files matched the installer selection')
    return sorted(files)


def _prepare(path, include, timeout):
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError('timeout must be an integer from 1 to 3600 seconds')
    if include is None:include=[]
    if not isinstance(include,list) or any(not isinstance(p,str) or not p or '\x00' in p for p in include):
        raise ValueError('include must be a list of nonempty path filters')
    source=Path(path).expanduser().resolve(strict=True)
    if not source.is_file():raise ValueError('Expected a local GOG Inno Setup installer file')
    deadline=time.monotonic()+timeout
    inputs=_inputs(source)
    native=NativeInno.open(source,deadline=deadline)
    names=[item['path'] for item in native.inventory]
    if include:
        names=[name for name in names if any(
            fnmatch.fnmatchcase(name.casefold(), pattern.casefold()) or
            name.casefold().startswith(pattern.casefold().rstrip('/')+'/')
            for pattern in include)]
    files=_safe_inventory(names)
    result={'format':'fdisbull-gog-unpack-1',
            'installer':str(source), 'inputs':inputs,
            'adjacent_parts':'Matching basename-*.bin files hashed; only embedded slices supported.',
            'extractor':{'implementation':'fdisbull-native-inno', 'profile':SUPPORTED,
                         'requires_innoextract':False},
            'include':include,'files':files,'warnings':'', 'installer_executed':False,
            'source_sha256':native.source_sha256}
    return source, native, result, deadline


def list_gog(path, *, include=None, timeout=300):
    source, _, result, deadline=_prepare(path,include,timeout)
    if _inputs(source) != result['inputs']:
        raise ValueError('Installer inputs changed during inventory')
    return result


def unpack_gog(path, output, *, include=None, timeout=300):
    destination=Path(output).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output already exists; choose a new private directory')
    if not destination.parent.is_dir():
        raise ValueError('Output parent must already be a directory')
    source, native, result, deadline=_prepare(path,include,timeout)
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix='.inno-',dir=destination) as temp:
            staging=Path(temp)
            # native requires a new path to atomically own the extraction root
            data_root=staging/'payload'
            native.extract_selected(data_root,result['files'],emit_manifest=False,deadline=deadline)
            files=[]
            for item in sorted(data_root.rglob('*')):
                mode=item.lstat().st_mode
                if stat.S_ISDIR(mode):continue
                if not stat.S_ISREG(mode):
                    raise ValueError('Native decoder produced a non-regular file')
                name=item.relative_to(data_root).as_posix()
                with item.open('rb') as stream:magic=stream.read(4)
                files.append({'path':name,'size':item.stat().st_size,'sha256':_digest(item),
                              'executable_candidate': item.suffix.casefold() in ('.exe','.com')
                              or magic[:2] in (b'MZ',b'ZM')})
            if sorted(x['path'] for x in files)!=result['files']:
                raise ValueError('Extracted files do not match the selected inventory')
            if _inputs(source)!=result['inputs']:
                raise ValueError('Installer inputs changed during extraction')
            result.update(output=str(destination),files=files,manifest=str(destination/MANIFEST))
            for member in data_root.iterdir():member.rename(destination/member.name)
        with (destination/MANIFEST).open('x',encoding='utf-8') as handle:
            json.dump(result,handle,indent=2,ensure_ascii=True);handle.write('\n')
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise