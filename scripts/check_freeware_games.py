#!/usr/bin/env python3
"""Validate the explicit three-game review corpus and its deterministic ZIP.

This is an integrity/ownership inventory, not execution, equivalence, license
authentication, or proof that every historical artifact has been recovered.
The review corpus is deliberately separate from tool-only distributions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
GAMES = frozenset({'tic-tac-toe', 'five-dice', 'snake'})
FORMATS = frozenset({'dos-com', 'dos-mz', 'x86-16-block', 'python-reference', 'uil-module',
    'source-reference', 'pe32', 'pe64', 'windows-ne', 'elf64', 'macho-arm64',
    'browser-bundle', 'module-wasm', 'module-wgsl', 'archive-zip', 'archive-tar'})
MANIFEST_FORMAT = 'fdisbull-freeware-game-versions-1'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _relative(value):
    _require(type(value) is str and bool(value), 'nonempty relative path required')
    path = PurePosixPath(value)
    _require(not path.is_absolute() and '..' not in path.parts and
             path.as_posix() == value and '\\' not in value and ':' not in value and
             not any(ord(character) < 32 for character in value) and
             all(part not in ('.', '..') and not part.endswith((' ', '.')) for part in path.parts),
             'unsafe or noncanonical relative path: ' + repr(value))
    return value


def _digest(value):
    _require(type(value) is str and SHA256.fullmatch(value), 'lowercase SHA-256 required')
    return value


def _private_state(name):
    name = PurePosixPath(name).name.lower()
    return (name.endswith(('.fdb', '.db', '.sqlite', '.sqlite3', '.sav', '.state', '.mig.gz'))
            or any(marker in name for marker in ('.fdb-', '.sqlite-', '.sqlite3-')))


def _pairs(values):
    result = {}
    for name, value in values:
        _require(name not in result, 'duplicate manifest JSON key: ' + name)
        result[name] = value
    return result


def _nonfinite(value):
    raise ValueError('nonfinite manifest JSON number: ' + value)


def _hash_stream(stream):
    hasher = hashlib.sha256()
    count = 0
    while chunk := stream.read(65536):
        hasher.update(chunk)
        count += len(chunk)
    return count, hasher.hexdigest()


def _inventory(root):
    root = Path(root).expanduser().absolute()
    _require(not root.is_symlink() and root.is_dir(), 'regular corpus directory required; symlinks forbidden')
    root = root.resolve()
    actual = set()
    for directory, directories, filenames in os.walk(root, followlinks=False):
        for name in directories:
            _require(not (Path(directory) / name).is_symlink(), 'corpus directory symlink forbidden')
        for name in filenames:
            path = Path(directory) / name
            _require(not path.is_symlink(), 'corpus file symlink forbidden: ' + str(path.relative_to(root)))
            _require(stat.S_ISREG(path.stat().st_mode), 'nonregular corpus file forbidden')
            actual.add(path.relative_to(root).as_posix())
    _require('manifest.json' in actual, 'corpus manifest.json missing')
    raw = (root / 'manifest.json').read_bytes()
    manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    _require(type(manifest) is dict and manifest.get('format') == MANIFEST_FORMAT, 'unsupported corpus manifest')
    games = manifest.get('games')
    _require(type(games) is list and all(type(game) is str for game in games) and
             len(games) == len(GAMES) and set(games) == GAMES,
             'corpus must contain exactly tic-tac-toe, five-dice, snake')
    records = manifest.get('files')
    _require(type(records) is list and bool(records), 'nonempty file inventory required')
    files, folded = {}, set()
    for record in records:
        _require(type(record) is dict and {'path', 'sha256', 'bytes', 'game', 'category'} <= set(record),
                 'complete file inventory record required')
        name = _relative(record['path'])
        _require(name != 'manifest.json' and name not in files and name.casefold() not in folded,
                 'duplicate, case-colliding, or reserved inventory path: ' + name)
        _require(not _private_state(name), 'private database/state is outside the freeware exception: ' + name)
        _digest(record['sha256'])
        _require(type(record['bytes']) is int and record['bytes'] >= 0, 'nonnegative file byte count required')
        _require(record['game'] is None or type(record['game']) is str and record['game'] in GAMES,
                 'file game is outside the three-game exception: ' + name)
        _require(type(record['category']) is str and bool(record['category'].strip()), 'explicit file category required')
        _require('executable' not in record or type(record['executable']) is bool, 'file executable flag must be boolean')
        files[name] = record
        folded.add(name.casefold())
    _require(actual == {*files, 'manifest.json'},
             'corpus inventory differs: missing=' + repr(sorted(set(files) - actual)) +
             ', extra=' + repr(sorted(actual - {*files, 'manifest.json'})))
    for name, record in files.items():
        path = root / name
        with path.open('rb') as stream:
            count, sha = _hash_stream(stream)
        _require(count == record['bytes'] and sha == record['sha256'], 'file hash/size differs: ' + name)
    versions = manifest.get('versions')
    _require(type(versions) is list and bool(versions), 'nonempty version inventory required')
    by_id = {}
    for version in versions:
        _require(type(version) is dict and {'id', 'game', 'artifact', 'format', 'sha256', 'parent',
                                          'behavior', 'qualification'} <= set(version), 'complete version record required')
        identifier = version['id']
        _require(type(identifier) is str and bool(identifier.strip()) and identifier not in by_id,
                 'unique nonempty version id required')
        _require(type(version['game']) is str and version['game'] in GAMES, 'version game outside exception')
        _require(type(version['format']) is str and version['format'] in FORMATS, 'unsupported version format')
        artifact = _relative(version['artifact'])
        _require(artifact in files and files[artifact]['game'] == version['game'],
                 'version artifact missing or assigned to another game: ' + identifier)
        _require(_digest(version['sha256']) == files[artifact]['sha256'], 'version artifact hash differs: ' + identifier)
        _require(version['parent'] is None or type(version['parent']) is str and bool(version['parent']),
                 'version parent must be an id or null')
        for field in ('behavior', 'qualification'):
            _require(type(version[field]) in (str, dict) and bool(version[field]), 'explicit version ' + field + ' required')
        if 'kind' in version:
            _require(version['kind'] in ('full-game', 'block', 'reference'), 'unsupported version kind')
            if version['format'] in ('x86-16-block', 'python-reference', 'uil-module', 'source-reference', 'module-wasm', 'module-wgsl'):
                _require(version['kind'] != 'full-game', 'partial/reference module cannot claim full-game kind')
        if version['format'] == 'dos-com':
            _require(1 <= files[artifact]['bytes'] <= 65280, 'DOS COM byte count outside bounded image profile')
        by_id[identifier] = version
    _require({version['game'] for version in versions} == GAMES, 'every allowed game needs at least one version')
    for identifier, version in by_id.items():
        seen = {identifier}
        parent = version['parent']
        while parent is not None:
            _require(parent in by_id, 'unknown version parent: ' + parent)
            _require(by_id[parent]['game'] == version['game'], 'version parent belongs to another game')
            _require(parent not in seen, 'cyclic version lineage')
            seen.add(parent)
            parent = by_id[parent]['parent']
    licenses = manifest.get('licenses')
    _require(type(licenses) is dict and set(licenses) == GAMES, 'license references required for exactly three games')
    for game, license_ in licenses.items():
        _require(type(license_) is dict and {'path', 'identifier'} <= set(license_), 'complete license reference required')
        name = _relative(license_['path'])
        _require(name in files and files[name]['game'] in (None, game), 'license reference missing or belongs to another game')
        _require(type(license_['identifier']) is str and bool(license_['identifier'].strip()), 'license identifier required')
    notices = manifest.get('additional_notices', [])
    _require(type(notices) is list, 'additional_notices must be a list')
    notice_ids = set()
    for notice in notices:
        _require(type(notice) is dict and {'id', 'game', 'path', 'identifier', 'source', 'asset', 'sha256', 'scope'} <= set(notice),
                 'complete additional font notice required')
        identifier = notice['id']
        _require(type(identifier) is str and bool(identifier) and identifier not in notice_ids, 'unique additional notice id required')
        notice_ids.add(identifier)
        _require(notice['game'] == 'snake' and notice['identifier'] == 'GPL-2.0-or-later', 'additional font notice must identify Snake GPL-2.0-or-later')
        _require(type(notice['scope']) is str and bool(notice['scope'].strip()), 'font notice scope required')
        for field in ('path', 'source', 'asset'):
            name = _relative(notice[field])
            _require(name in files and files[name]['game'] == 'snake', 'font notice reference missing or belongs to another game')
        _require(_digest(notice['sha256']) == files[notice['asset']]['sha256'], 'font notice asset hash differs')
    font_asset = 'snake/runtime-font/int10_font_08.bin'
    if font_asset in files:
        _require(any(notice['id'] == 'dosbox-x-font-8x8' and notice['asset'] == font_asset for notice in notices),
                 'included DOSBox-X font requires its bound additional notice')
    _require(type(manifest.get('provenance')) is dict and type(manifest.get('coverage')) is dict,
             'provenance and coverage objects required')
    report = {'ok': True, 'format': MANIFEST_FORMAT, 'games': sorted(GAMES), 'files': len(files),
              'versions': len(versions), 'bytes': sum(record['bytes'] for record in files.values()),
              'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'scope': 'inventory integrity; no game execution or behavioral qualification'}
    native_executables = {version['artifact'] for version in versions if version['format'] in ('elf64', 'macho-arm64')}
    modes = {name: 0o100755 if record.get('executable', False) or name in native_executables else 0o100644
             for name, record in files.items()}
    modes['manifest.json'] = 0o100644
    return root, raw, files, report, modes


def check_corpus(root):
    return _inventory(root)[3]


def _check_archive(inventory, archive):
    root, raw, files, report, modes = inventory
    archive = Path(archive).expanduser().absolute()
    _require(not archive.is_symlink() and archive.is_file(), 'regular archive required; symlinks forbidden')
    expected = {'freeware-games/manifest.json': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    expected.update({'freeware-games/' + name: record for name, record in files.items()})
    try:
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            names = [member.filename for member in members]
            _require(len(names) == len(set(names)) and set(names) == set(expected), 'archive membership differs or duplicates exist')
            _require(not source.comment, 'archive comment is outside the inventory')
            _require(members and min(member.header_offset for member in members) == 0, 'archive preamble is outside the inventory')
            for member in members:
                _require(member.orig_filename == member.filename and not member.is_dir() and
                         stat.S_IFMT(member.external_attr >> 16) in (0, stat.S_IFREG) and
                         not member.flag_bits & 1 and not member.extra and not member.comment and
                         member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                         'archive symlink, directory, encrypted, or untracked metadata entry forbidden')
                relative = member.filename.removeprefix('freeware-games/')
                _require(member.create_system == 3 and (member.external_attr >> 16) & 0o777 == modes[relative] & 0o777,
                         'archive executable permissions differ: ' + member.filename)
                record = expected[member.filename]
                _require(member.file_size == record['bytes'], 'archive member byte count differs: ' + member.filename)
                with source.open(member) as stream:
                    count, sha = _hash_stream(stream)
                _require(count == record['bytes'] and sha == record['sha256'], 'archive member bytes differ: ' + member.filename)
        with archive.open('rb') as container:
            container.seek(-22, os.SEEK_END)
            footer = container.read(22)
        _require(footer[:4] == b'PK\x05\x06' and footer[-2:] == b'\0\0', 'archive trailing bytes are outside the inventory')
    except (zipfile.BadZipFile, RuntimeError, zlib.error) as error:
        raise ValueError('archive CRC/container failure: ' + str(error)) from error
    with archive.open('rb') as stream:
        count, sha = _hash_stream(stream)
    return {'ok': True, 'members': len(expected), 'bytes': count, 'sha256': sha}


def check_archive(root, archive):
    return _check_archive(_inventory(root), archive)


def write_archive(root, destination):
    inventory = _inventory(root)
    corpus, raw, files, report, modes = inventory
    destination = Path(destination).expanduser().absolute()
    _require(destination.suffix.lower() == '.zip', 'companion archive must use .zip')
    _require(not destination.is_symlink(), 'linked archive output forbidden')
    destination = destination.resolve()
    _require(destination != corpus and corpus not in destination.parents, 'archive output must stay outside corpus')
    if destination.exists():
        status = destination.stat()
        _require(stat.S_ISREG(status.st_mode) and status.st_nlink == 1, 'owned regular archive output required; links forbidden')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + destination.name + '-', suffix='.tmp', dir=destination.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
                for name in sorted([*files, 'manifest.json']):
                    member = zipfile.ZipInfo('freeware-games/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                    member.create_system = 3
                    member.external_attr = modes[name] << 16
                    member.compress_type = zipfile.ZIP_DEFLATED
                    with output.open(member, 'w') as target:
                        if name == 'manifest.json':
                            target.write(raw)
                        else:
                            with (corpus / name).open('rb') as source:
                                while chunk := source.read(65536):
                                    target.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        result = _check_archive(inventory, temporary)
        os.replace(temporary, destination)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'fixtures/freeware-games')
    parser.add_argument('--write-archive', type=Path, metavar='OUT')
    parser.add_argument('--archive', type=Path, metavar='ZIP')
    args = parser.parse_args()
    try:
        result = {'ok': True, 'corpus': check_corpus(args.root)}
        if args.write_archive:
            result['written_archive'] = write_archive(args.root, args.write_archive)
        if args.archive:
            result['archive'] = check_archive(args.root, args.archive)
    except (ValueError, OSError) as error:
        parser.exit(1, json.dumps({'ok': False, 'error': str(error)}, separators=(',', ':')) + '\n')
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
