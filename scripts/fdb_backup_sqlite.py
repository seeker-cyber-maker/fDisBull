#!/usr/bin/env python3
"""Internal fresh-process SQLite snapshot worker; no VFS or CPython internals.

The parent admits regular inodes and passes their open descriptors. This worker
runs with site imports disabled and no concurrent threads or earlier SQLite
connections, so each connect's new regular descriptor can be bound directly.
The source uses SQLite's online backup protocol, including committed WAL data.
"""
from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

SPEC = importlib.util.spec_from_file_location('_private_fdb_backup', Path(__file__).with_name('fdb_backup.py'))
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


def _identity(descriptor):
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('SQLite admission requires a regular descriptor')
    return value.st_dev, value.st_ino


def _regular_descriptors():
    """Inspect this single-threaded process; fail closed on unsupported hosts."""
    for directory in ('/proc/self/fd', '/dev/fd'):
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        result = {}
        for name in names:
            if not name.isdecimal():
                continue
            descriptor = int(name)
            try:
                value = os.fstat(descriptor)
            except OSError as error:
                if error.errno == errno.EBADF:
                    continue  # The descriptor-directory listing closed its own FD.
                raise
            if stat.S_ISREG(value.st_mode):
                result[descriptor] = value.st_dev, value.st_ino
        return result
    raise ValueError('SQLite opened-descriptor inspection is unavailable')


def _connect(path, admitted, *, readonly, timeout, immutable=False):
    expected = _identity(admitted)
    before = _regular_descriptors()
    # Writable SQLite never receives a mutable user/stage pathname. This
    # descriptor alias stays anchored for the child's lifetime; any sidecar
    # namespace is devfs rather than an unrelated replacement directory.
    if not readonly or immutable:
        directory = '/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
        path = Path(directory) / str(admitted)
    database = path.as_uri() + ('?mode=ro' + ('&immutable=1' if immutable else '') if readonly else '?mode=rw')
    connection = sqlite3.connect(database, uri=True, timeout=timeout)
    try:
        after = _regular_descriptors()
        opened = {fd: value for fd, value in after.items() if before.get(fd) != value}
        matches = [fd for fd, value in opened.items() if value == expected]
        if len(matches) != 1:
            raise ValueError('SQLite database identity differs from admitted descriptor')
        if not readonly or immutable:
            names = connection.execute('PRAGMA database_list').fetchall()
            if names != [(0, 'main', str(path))]:
                raise ValueError('SQLite does not preserve the descriptor-alias namespace')
        return connection, matches[0]
    except BaseException:
        connection.close()
        raise


def _pin_sidecars(source, parentfd, sourcefd):
    if not stat.S_ISDIR(os.fstat(parentfd).st_mode):
        raise ValueError('SQLite source parent descriptor is not a directory')
    result = {}
    try:
        for suffix in ('-wal', '-shm'):
            try:
                descriptor = os.open(source.name + suffix, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parentfd)
            except FileNotFoundError:
                continue
            result[suffix] = descriptor
            identity = _identity(descriptor)
            if identity == _identity(sourcefd) or any(
                    identity == _identity(other) for name, other in result.items() if name != suffix):
                raise ValueError('SQLite sidecar aliases an admitted file')
        return result
    except BaseException:
        for descriptor in result.values():
            os.close(descriptor)
        raise


def _source_handles(before, main, sidecars, *, wal, exclude=()):
    current = _regular_descriptors()
    expected = {_identity(fd) for fd in sidecars.values()}
    opened = {fd: value for fd, value in current.items()
              if before.get(fd) != value and fd != main and fd not in exclude}
    if any(value not in expected for value in opened.values()):
        raise ValueError('SQLite WAL/SHM identity differs from admitted sidecars')
    if wal and (set(sidecars) != {'-wal', '-shm'}
                or not expected <= set(opened.values())):
        raise ValueError('SQLite WAL/SHM open handles cannot be established')
    return opened


def snapshot(source, destination, sourcefd, snapshotfd, referencesfd, end, maximum, source_parentfd):
    source_db = destination_db = None
    sidecars = {}
    try:
        backup._deadline(end)
        sidecars = _pin_sidecars(source, source_parentfd, sourcefd)
        source_before = _regular_descriptors()
        source_db, source_main = _connect(source, sourcefd, readonly=True, timeout=min(1, max(.001, end-time.monotonic())))
        # Keep the same read transaction through online backup. A main descriptor
        # alone cannot identify the WAL/SHM chosen at SQLite's first page read.
        source_db.execute('BEGIN')
        source_db.execute('PRAGMA schema_version').fetchone()
        wal = source_db.execute('PRAGMA journal_mode').fetchone() == ('wal',)
        source_handles = _source_handles(source_before, source_main, sidecars, wal=wal)
        if not source_db.in_transaction:
            raise ValueError('SQLite source read transaction is not held')
        # Discover an unsupported/canonicalizing VFS through an immutable
        # read-only connection, before ANY writable SQLite connection exists.
        preflight, _ = _connect(destination, snapshotfd, readonly=True, immutable=True,
            timeout=min(1, max(.001, end-time.monotonic())))
        preflight.close()
        destination_db, destination_main = _connect(destination, snapshotfd, readonly=False, timeout=min(1, max(.001, end-time.monotonic())))
        # Only this private disposable file is writable. Do not create/delete
        # journal sidecars through a pathname that might later be moved.
        if destination_db.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone() != ('exclusive',):
            raise ValueError('Private snapshot exclusive locking unavailable')
        if destination_db.execute('PRAGMA journal_mode=OFF').fetchone() != ('off',):
            raise ValueError('Private snapshot journal policy unavailable')
        if destination_db.execute('PRAGMA page_count').fetchone() != (0,):
            raise ValueError('Private snapshot must start empty')
        destination_db.set_progress_handler(lambda: int(time.monotonic() >= end), 10000)
        page_size = source_db.execute('PRAGMA page_size').fetchone()[0]

        def progress(_status, _remaining, total):
            backup._deadline(end)
            if total * page_size > maximum:
                raise ValueError('FDB snapshot exceeds size bound')

        source_db.backup(destination_db, pages=256, progress=progress, sleep=.01)
        backup._deadline(end)
        if not source_db.in_transaction or any(
                _identity(fd) != identity for fd, identity in source_handles.items()):
            raise ValueError('SQLite source WAL/SHM handles changed')
        if _identity(source_main) != _identity(sourcefd) or _identity(destination_main) != _identity(snapshotfd):
            raise ValueError('SQLite admitted descriptor changed')
        # Copying page one also copies its WAL format. EXCLUSIVE + OFF prevents
        # the backup/close path from touching writable pathname sidecars. Never
        # query this destination again: a separate immutable read-only connection
        # validates the completed snapshot without consulting WAL/SHM paths.
        return {'format': 'fdisbull-private-sqlite-backup-1', 'status': 'completed',
                'bound_inodes': {'source': list(_identity(source_main)), 'snapshot': list(_identity(destination_main))}}
    finally:
        if destination_db is not None:
            destination_db.close()
        if source_db is not None:
            source_db.close()
        for descriptor in sidecars.values():
            os.close(descriptor)


def scan(destination, snapshotfd, referencesfd, end, maximum):
    destination_db = None
    try:
        before = backup._hash_descriptor(snapshotfd, end, maximum)
        destination_db, main = _connect(destination, snapshotfd, readonly=True,
            immutable=True, timeout=min(1, max(.001, end-time.monotonic())))
        destination_db.set_progress_handler(lambda: int(time.monotonic() >= end), 10000)
        if destination_db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('FDB snapshot integrity check failed')
        count = 0

        def emit(reference):
            nonlocal count
            raw = (json.dumps(reference, sort_keys=True, separators=(',', ':')) + '\n').encode()
            if len(raw) > 512:
                raise ValueError('SQLite reference record exceeds bound')
            view = memoryview(raw)
            while view:
                backup._deadline(end)
                written = os.write(referencesfd, view)
                if written <= 0:
                    raise OSError('SQLite reference write made no progress')
                view = view[written:]
            count += 1

        tables = destination_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        for (name,) in tables:
            backup._deadline(end)
            if not isinstance(name, str) or '\0' in name:
                raise ValueError('Invalid SQLite table name')
            quoted = '"' + name.replace('"', '""') + '"'
            for row in destination_db.execute('SELECT * FROM ' + quoted):
                for value in row:
                    backup._references(value, emit, end)
        if _identity(main) != _identity(snapshotfd):
            raise ValueError('SQLite admitted descriptor changed')
        if backup._hash_descriptor(snapshotfd, end, maximum) != before:
            raise ValueError('Private snapshot changed during immutable scan')
        os.fsync(referencesfd)
        return {'format': 'fdisbull-private-sqlite-backup-1', 'status': 'completed',
                'bound_inodes': {'snapshot': list(_identity(main))}, 'references': count}
    finally:
        if destination_db is not None:
            destination_db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('backup', 'scan'), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    for name in ('source-fd', 'snapshot-fd', 'references-fd', 'source-parent-fd'):
        parser.add_argument('--' + name, type=int, required=True)
    parser.add_argument('--deadline', type=float, required=True)
    parser.add_argument('--max-database', type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'backup':
            value = snapshot(args.source, args.snapshot, args.source_fd, args.snapshot_fd,
                             args.references_fd, args.deadline, args.max_database, args.source_parent_fd)
        else:
            value = scan(args.snapshot, args.snapshot_fd, args.references_fd, args.deadline, args.max_database)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)[:1000]}))
        return 1
    print(json.dumps(value, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
