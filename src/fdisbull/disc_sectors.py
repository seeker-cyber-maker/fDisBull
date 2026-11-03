"""Bounded, read-only Mode 1 sector access with original-file provenance."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

_SYNC = b'\x00' + b'\xff' * 10 + b'\x00'


class DataTrackReader:
    """One data track; audio and generated gaps cannot become filesystem data."""

    def __init__(self, path, *, mode, start_sector=0, sector_count=None,
                 max_read_bytes=16 * 1024 * 1024, max_reads=8192, expected_identity=None):
        if mode not in ('MODE1/2048', 'MODE1/2352'):
            raise ValueError('only MODE1/2048 and MODE1/2352 data tracks are supported')
        if (type(start_sector) is not int or start_sector < 0
                or type(max_read_bytes) is not int or not 2048 <= max_read_bytes <= 64 * 1024 * 1024
                or type(max_reads) is not int or not 1 <= max_reads <= 32768):
            raise ValueError('invalid data-track reader bounds')
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file():
            raise ValueError('data track must be a regular file')
        self.stream = os.fdopen(os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb')
        self.before = os.fstat(self.stream.fileno())
        self.sector_size = 2352 if mode == 'MODE1/2352' else 2048
        self.user_offset = 16 if self.sector_size == 2352 else 0
        try:
            if expected_identity is not None and expected_identity != self._identity(self.before):
                raise ValueError('track identity changed after CUE inspection')
            if not stat.S_ISREG(self.before.st_mode) or self.before.st_size % self.sector_size:
                raise ValueError('track is not a whole number of supported sectors')
            available = self.before.st_size // self.sector_size
            if sector_count is None:
                sector_count = available - start_sector
            if (type(sector_count) is not int or sector_count <= 0
                    or start_sector + sector_count > available):
                raise ValueError('selected data-track range exceeds the file')
        except Exception:
            self.stream.close()
            raise
        self.start_sector, self.sector_count = start_sector, sector_count
        self.max_read_bytes, self.max_reads = max_read_bytes, max_reads
        self.bytes_read = 0
        self.read_count = 0
        self.samples = {}

    def __enter__(self):
        return self

    @staticmethod
    def _identity(info):
        return dict(dev=info.st_dev, ino=info.st_ino, size=info.st_size,
                    mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)

    def __exit__(self, exc_type, exc, traceback):
        try:
            after = os.fstat(self.stream.fileno())
            current = self.path.stat()
        finally:
            self.stream.close()
        if exc_type is None and (self._identity(self.before) != self._identity(after)
                                 or self._identity(after) != self._identity(current)):
            raise ValueError('data track changed during inspection')

    def read_sector(self, lba):
        if type(lba) is not int or not 0 <= lba < self.sector_count:
            raise ValueError('logical sector is outside selected data track')
        if self.read_count >= self.max_reads or self.bytes_read + self.sector_size > self.max_read_bytes:
            raise ValueError('data-track read budget exceeded')
        offset = (self.start_sector + lba) * self.sector_size
        self.stream.seek(offset)
        data = self.stream.read(self.sector_size)
        self.read_count += 1
        self.bytes_read += len(data)
        if len(data) != self.sector_size:
            raise ValueError('truncated physical sector')
        if self.sector_size == 2352 and (data[:12] != _SYNC or data[15] != 1):
            raise ValueError('physical sector lacks raw Mode 1 framing')
        self.samples[offset] = {'file_offset': offset, 'file_size': len(data),
                                'sha256': hashlib.sha256(data).hexdigest()}
        return data[self.user_offset:self.user_offset + 2048]

    def backing(self, lba, size):
        if type(lba) is not int or type(size) is not int or lba < 0 or size < 0:
            raise ValueError('invalid extent')
        count = (size + 2047) // 2048
        if lba + count > self.sector_count:
            raise ValueError('extent exceeds selected data track')
        return {'file': str(self.path), 'physical_sector_offset': (self.start_sector + lba) * self.sector_size,
                'sector_size': self.sector_size, 'user_data_offset': self.user_offset,
                'user_bytes_per_sector': 2048, 'logical_size': size, 'sector_count': count,
                'contiguous': self.sector_size == 2048}

    def provenance(self):
        return {'file': str(self.path), 'source_size': self.before.st_size,
                'file_identity': self._identity(self.before),
                'source_sha256': None, 'hash_scope': 'sampled physical sectors only',
                'selected_start_sector': self.start_sector, 'selected_sector_count': self.sector_count,
                'bytes_read': self.bytes_read, 'read_count': self.read_count,
                'sampled_regions': list(self.samples.values()), 'edc_ecc_verified': False}
