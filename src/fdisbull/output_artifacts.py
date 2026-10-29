"""Private, immutable JSON output artifacts with bounded retrieval."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:  # Fail closed where a process-safe lock is unavailable.
    fcntl = None


class ArtifactError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _fail(code):
    raise ArtifactError(code)


def _private_directory(path):
    path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    # Refuse symlink traversal and Git ancestry, including a .git file in a worktree.
    for parent in reversed((path, *path.parents)):
        if parent.is_symlink(): _fail('unsafe_path')
        if (parent / '.git').exists() or (parent / '.git').is_symlink(): _fail('inside_git')
    missing = []
    current = path
    while not current.exists():
        missing.append(current); current = current.parent
    if not current.is_dir(): _fail('unsafe_path')
    for entry in reversed(missing):
        try: entry.mkdir(mode=0o700)
        except FileExistsError: pass
        if entry.is_symlink() or not entry.is_dir(): _fail('unsafe_path')
        st = entry.stat()
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: _fail('not_private')
    st = path.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        _fail('not_private')
    return path


def _json_decode(data):
    def invalid(_): _fail('invalid_json')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: _fail('invalid_json')
            result[key] = value
        return result
    try:
        return json.loads(data.decode('utf-8'), parse_constant=invalid, object_pairs_hook=pairs)
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, ArtifactError): raise
        _fail('invalid_json')


class OutputArtifactStore:
    def __init__(self, root=None, max_artifact_bytes=64*1024*1024, max_store_bytes=512*1024*1024):
        if fcntl is None or not callable(getattr(os, 'getuid', None)):
            _fail('platform_unsupported')
        if any(type(v) is not int or v <= 0 for v in (max_artifact_bytes, max_store_bytes)):
            _fail('invalid_limit')
        if root is None:
            root = os.environ.get('FDISBULL_OUTPUT_ARTIFACT_DIR')
            if not root:
                base = os.environ.get('XDG_DATA_HOME')
                if not base:
                    base = str(Path.home() / ('Library/Application Support' if sys.platform == 'darwin' else '.local/share'))
                root = Path(base) / 'fdisbull/output-artifacts'
        try: self.root = _private_directory(root)
        except ArtifactError: raise
        except (OSError, TypeError, ValueError): _fail('unsafe_path')
        st = self.root.stat()
        self._root_identity = (st.st_dev, st.st_ino)
        self.max_artifact_bytes = max_artifact_bytes
        self.max_store_bytes = max_store_bytes

    @contextmanager
    def _lock(self):
        if fcntl is None: _fail('lock_unavailable')
        fd = None
        try:
            _private_directory(self.root)
            st = self.root.stat()
            if (st.st_dev, st.st_ino) != self._root_identity: _fail('unsafe_store')
            fd = os.open(self.root / '.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: _fail('unsafe_store')
            deadline = time.monotonic() + 1
            while True:
                try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                except BlockingIOError:
                    if time.monotonic() >= deadline: _fail('lock_timeout')
                    time.sleep(.01)
            yield
        except ArtifactError: raise
        except OSError: _fail('io_error')
        finally:
            if fd is not None:
                try: fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
                except OSError: pass

    def _path(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'out-[0-9a-f]{64}', ident): _fail('invalid_id')
        return self.root / ident

    def _usage(self):
        total = 0
        for p in self.root.iterdir():
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
                _fail('unsafe_store')
            total += st.st_size
        return total

    def _read_verified(self, ident):
        path = self._path(ident)
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as f:
                st = os.fstat(f.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: _fail('unsafe_store')
                if st.st_size > self.max_artifact_bytes: _fail('artifact_too_large')
                data = f.read(self.max_artifact_bytes + 1)
        except FileNotFoundError: _fail('not_found')
        except ArtifactError: raise
        except OSError: _fail('io_error')
        digest = hashlib.sha256(data).hexdigest()
        if digest != ident[4:] or len(data) != st.st_size: _fail('integrity_error')
        return data

    @staticmethod
    def _metadata(ident, size):
        return {'id':ident, 'sha256':ident[4:], 'bytes':size, 'media_type':'application/json'}

    def put_stream(self, chunks):
        with self._lock():
            used = self._usage()
            fd, name = tempfile.mkstemp(prefix='.partial-', dir=self.root)
            temporary = Path(name); length = 0; digest = hashlib.sha256()
            try:
                with os.fdopen(fd, 'wb') as f:
                    for count, chunk in enumerate(chunks, 1):
                        if count > 65536: _fail('stream_budget')
                        if not isinstance(chunk, bytes): _fail('invalid_chunk')
                        length += len(chunk)
                        if length > self.max_artifact_bytes: _fail('artifact_too_large')
                        if used + length > self.max_store_bytes: _fail('quota_exceeded')
                        f.write(chunk); digest.update(chunk)
                    f.flush(); os.fsync(f.fileno())
                _json_decode(temporary.read_bytes())
                ident = 'out-' + digest.hexdigest(); dest = self._path(ident)
                try: os.link(temporary, dest, follow_symlinks=False)
                except FileExistsError:
                    if self._read_verified(ident) != temporary.read_bytes(): _fail('integrity_error')
                directory = os.open(self.root, os.O_RDONLY)
                try: os.fsync(directory)
                finally: os.close(directory)
                return self._metadata(ident, length)
            except ArtifactError: raise
            except Exception: _fail('io_error')
            finally:
                try: temporary.unlink()
                except FileNotFoundError: pass

    def info(self, ident):
        with self._lock():
            data = self._read_verified(ident)
            return self._metadata(ident, len(data))

    def read(self, ident, offset=0, length=4096):
        if type(offset) is not int or type(length) is not int or offset < 0 or not 1 <= length <= 8192: _fail('invalid_range')
        with self._lock():
            data = self._read_verified(ident)
            if offset > len(data): _fail('invalid_range')
            part = data[offset:offset+length]; end = offset + len(part)
            return {**self._metadata(ident, len(data)), 'offset':offset, 'next_offset':end,
                    'data_base64':base64.b64encode(part).decode('ascii'), 'eof':end == len(data),
                    'range_complete':True, 'whole_complete':offset == 0 and end == len(data)}

    def select(self, ident, pointer='', max_bytes=16384):
        if not isinstance(pointer, str) or len(pointer) > 4096 or (pointer and not pointer.startswith('/')): _fail('invalid_pointer')
        if type(max_bytes) is not int or not 1 <= max_bytes <= 16384: _fail('invalid_limit')
        with self._lock():
            data = self._read_verified(ident); value = _json_decode(data)
            for raw in pointer.split('/')[1:]:
                if re.search(r'~(?![01])', raw): _fail('invalid_pointer')
                key = raw.replace('~1','/').replace('~0','~')
                if isinstance(value, dict):
                    if key not in value: _fail('pointer_not_found')
                    value = value[key]
                elif isinstance(value, list):
                    if not re.fullmatch(r'0|[1-9][0-9]*', key) or len(key) > 10: _fail('pointer_not_found')
                    i = int(key)
                    if i >= len(value): _fail('pointer_not_found')
                    value = value[i]
                else: _fail('pointer_not_found')
            meta = {**self._metadata(ident, len(data)), 'pointer':pointer}
            size = 0
            try:
                for part in json.JSONEncoder(ensure_ascii=False, separators=(',',':'), allow_nan=False).iterencode(value):
                    size += len(part.encode('utf-8'))
                    if size > max_bytes: return {**meta, 'complete':False, 'reason':'selection_too_large'}
            except (UnicodeError, ValueError, RecursionError): _fail('invalid_json')
            return {**meta, 'complete':True, 'value':value, 'selected_bytes':size}

    def export(self, ident, path):
        try:
            path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
            for parent in (path.parent, *path.parent.parents):
                if parent.is_symlink(): _fail('unsafe_path')
                if (parent / '.git').exists() or (parent / '.git').is_symlink(): _fail('inside_git')
            with self._lock():
                data = self._read_verified(ident)
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                except FileExistsError: _fail('already_exists')
                try:
                    with os.fdopen(fd, 'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
                except BaseException:
                    try: path.unlink()
                    except OSError: pass
                    raise
                return {**self._metadata(ident, len(data)), 'path':str(path), 'complete':True}
        except FileExistsError: _fail('already_exists')
        except ArtifactError: raise
        except (OSError, TypeError, ValueError): _fail('io_error')
