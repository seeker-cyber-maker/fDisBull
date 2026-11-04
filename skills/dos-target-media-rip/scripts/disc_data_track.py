#!/usr/bin/env python3
"""Inventory ordinary ISO9660 and optionally copy a verified data-only ISO."""
import argparse
import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path

class Disc:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = self.path.open('rb')
        self.size = self.path.stat().st_size
        self.logical_sectors = None
        for sector, payload in ((2048, 0), (2352, 16)):
            self.stream.seek(16*sector+payload)
            if self.stream.read(7) == b'\x01CD001\x01':
                self.sector, self.payload = sector, payload
                break
        else:
            self.stream.close()
            raise ValueError('No supported ISO9660 primary volume at sector 16')
        if self.size % self.sector:
            raise ValueError('Incomplete physical sector')

    @staticmethod
    def both32(data, offset):
        a = struct.unpack_from('<I', data, offset)[0]
        b = struct.unpack_from('>I', data, offset+4)[0]
        if a != b:
            raise ValueError('ISO dual-endian field mismatch')
        return a

    def read(self, offset, size):
        limit = (self.logical_sectors or self.size//self.sector)*2048
        if offset < 0 or size < 0 or offset+size > limit:
            raise ValueError('Read outside the declared data volume')
        parts = []
        while size:
            sector, within = divmod(offset, 2048)
            take = min(size, 2048-within)
            if self.sector == 2352:
                self.stream.seek(sector*self.sector)
                header = self.stream.read(16)
                if header[:12] != b'\0'+b'\xff'*10+b'\0' or header[15] != 1:
                    raise ValueError('Data sector is not ordinary MODE1/2352')
            self.stream.seek(sector*self.sector+self.payload+within)
            data = self.stream.read(take)
            if len(data) != take:
                raise ValueError('Short sector read')
            parts.append(data)
            offset += take
            size -= take
        return b''.join(parts)

    def inventory(self):
        pvd = self.read(16*2048, 2048)
        self.logical_sectors = self.both32(pvd, 80)
        if not 17 <= self.logical_sectors <= self.size//self.sector:
            raise ValueError('Invalid data-volume sector count')
        if struct.unpack_from('<H', pvd, 128)[0] != 2048 or struct.unpack_from('>H', pvd, 130)[0] != 2048:
            raise ValueError('Unsupported logical block size')
        rows, seen = [], set()
        def walk(prefix, lba, size):
            if (lba, size) in seen:
                raise ValueError('Directory cycle or alias unsupported')
            seen.add((lba, size))
            data = self.read(lba*2048, size)
            pos = 0
            while pos < len(data):
                length = data[pos]
                if length == 0:
                    pos = (pos//2048+1)*2048
                    continue
                record = data[pos:pos+length]
                if len(record) < 34 or len(record) != length:
                    raise ValueError('Short directory record')
                if 33+record[32] > len(record):
                    raise ValueError('Truncated directory name')
                pos += length
                name_bytes = record[33:33+record[32]]
                if name_bytes in (b'\0', b'\1'):
                    continue
                name = name_bytes.decode('ascii').split(';')[0].rstrip('.')
                if not name or name in ('.', '..') or '/' in name or '\\' in name:
                    raise ValueError('Unsafe ISO path')
                extent, amount = self.both32(record, 2), self.both32(record, 10)
                if record[25] & 0x80:
                    raise ValueError('Multi-extent file unsupported')
                path = prefix+name
                if record[25] & 2:
                    walk(path+'/', extent, amount)
                else:
                    digest = hashlib.sha256()
                    for offset in range(0, amount, 1024*1024):
                        digest.update(self.read(extent*2048+offset, min(1024*1024, amount-offset)))
                    rows.append({'path': path, 'bytes': amount, 'sha256': digest.hexdigest()})
        root = pvd[156:190]
        walk('', self.both32(root, 2), self.both32(root, 10))
        rows.sort(key=lambda f: f['path'])
        if len({r['path'] for r in rows}) != len(rows):
            raise ValueError('Duplicate file path')
        return {'volume': pvd[40:72].decode('ascii').strip(),
                'logical_sectors': self.logical_sectors, 'files': rows}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--iso', type=Path)
    ap.add_argument('--data-sectors', type=int, help='Explicit data-track sector count from a verified CUE, including MODE1 padding')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists() or args.report.is_symlink():
        raise ValueError('Refusing to overwrite an existing report or source')
    if args.report.resolve() == args.source.resolve() or (args.iso and args.report.resolve() == args.iso.resolve()):
        raise ValueError('Report, source and ISO paths must be distinct')
    source = Disc(args.source)
    try:
        original = source.inventory()
        with args.source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        report = {'source': str(args.source.resolve()), 'source_sha256': digest,
                  'source_bytes': source.size, 'sector_bytes': source.sector,
                  'trailing_unconverted_bytes': source.size-original['logical_sectors']*source.sector,
                  'inventory': original, 'audio': 'No audio conversion or track-layout claim.'}
        if args.iso:
            if args.iso.exists():
                raise ValueError('Refusing to overwrite an existing ISO')
            copy_sectors = original['logical_sectors'] if args.data_sectors is None else args.data_sectors
            if not original['logical_sectors'] <= copy_sectors <= source.size//source.sector:
                raise ValueError('Data track count does not contain the declared volume')
            args.iso.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.iso-data-', dir=args.iso.parent)
            os.close(fd)
            temp = Path(name)
            try:
                with temp.open('wb') as output:
                    source.logical_sectors = copy_sectors
                    for offset in range(0, copy_sectors*2048, 1024*1024):
                        output.write(source.read(offset, min(1024*1024, copy_sectors*2048-offset)))
                    source.logical_sectors = original['logical_sectors']
                converted = Disc(temp)
                try:
                    if converted.inventory() != original:
                        raise ValueError('Converted ISO file inventory differs')
                finally:
                    converted.stream.close()
                with temp.open('rb') as stream:
                    iso_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
                os.link(temp, args.iso)
                report['derived_iso'] = {'path': str(args.iso.resolve()), 'bytes': temp.stat().st_size,
                                         'sha256': iso_hash, 'all_file_payloads_identical': True,
                                         'copied_data_sectors': copy_sectors,
                                         'preserved_padding_sectors': copy_sectors-original['logical_sectors']}
                report['trailing_unconverted_bytes'] = source.size-copy_sectors*source.sector
            finally:
                temp.unlink(missing_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x') as output:
            output.write(json.dumps(report, indent=2)+'\n')
        print(json.dumps({'volume': original['volume'], 'files': len(original['files']),
                          'source_bytes': source.size, 'derived_iso': report.get('derived_iso')}))
    finally:
        source.stream.close()

if __name__ == '__main__':
    main()
