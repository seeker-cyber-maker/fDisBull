"""Console media inspection with original file offsets and explicit limits."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

MAX_ROM_SIZE = 64 * 1024 * 1024
DISC_PREFIX_SIZE = 4096


def _input(data):
    if not isinstance(data, bytes):
        raise ValueError('ROM inspection requires bytes')
    if len(data) > MAX_ROM_SIZE:
        raise ValueError('ROM inspection input exceeds 64 MiB')


def probe_rom(data: bytes) -> dict | None:
    _input(data)
    from .rom_disc import parse_sega_disc
    from .rom_nes import parse_nes
    from .rom_sega import parse_genesis, parse_sms
    from .rom_snes import parse_snes
    for parser in (parse_sega_disc, parse_nes, parse_genesis, parse_sms, parse_snes):
        result = parser(data)
        if result is not None:
            result['loadable'] = False
            result['validation_scope'] = 'bounded container structure and declared metadata; no CPU mapping, disassembly or execution'
            return result
    return None


def inspect_rom(data: bytes) -> dict:
    _input(data)
    result = probe_rom(data) or {'format': 'unknown', 'family': 'unknown',
        'platform': None, 'arch': None, 'bits': None, 'endian': None,
        'header_offset': None, 'valid': False, 'detection': None,
        'metadata': {}, 'regions': [], 'loadable': False,
        'warnings': ['No supported console-media header recognized; filename extensions are not evidence']}
    if result['family'] == 'console disc':
        from .rom_disc import parse_disc_volume
        sector = result['metadata']['sector_size']
        offset = 16 * sector
        volume = parse_disc_volume(data[offset:offset + sector], sector_size=sector,
                                   physical_sectors=len(data) // sector)
        if volume is not None:
            result['filesystem'] = volume
            result['valid'] = result['valid'] and volume['valid']
            result['warnings'].extend(volume['warnings'])
            result['metadata']['primary_volume_descriptor_parsed'] = volume['format'] == 'ISO 9660 primary volume descriptor'
            result['regions'].append({'name': 'sector-16 volume descriptor candidate', 'kind': 'volume_descriptor_sector',
                                      'file_offset': offset, 'file_size': min(sector, len(data) - offset)})
    return {**result, 'report_format': 'fdisbull-rom-inspection-1',
            'source_size': len(data), 'source_sha256': hashlib.sha256(data).hexdigest(),
            'hash_scope': 'complete supplied bytes'}


def inspect_rom_path(path: str | Path) -> dict:
    """Read cartridges within 64 MiB; sample a disc prefix and one ISO descriptor."""
    from .rom_disc import parse_sega_disc, parse_disc_volume
    if Path(path).suffix.lower() == '.cue':
        from .disc import inspect_disc_path
        return inspect_disc_path(path)
    if not Path(path).is_file():
        raise ValueError('ROM inspection requires a regular file')
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('ROM inspection requires a regular file')
        prefix = stream.read(DISC_PREFIX_SIZE)
        result = parse_sega_disc(prefix, file_size=before.st_size)
        if result is not None:
            sector = result['metadata']['sector_size']
            offset = 16 * sector
            stream.seek(offset)
            block = stream.read(sector)
            volume = parse_disc_volume(block, sector_size=sector, physical_sectors=before.st_size // sector)
            samples = [{'file_offset': 0, 'file_size': len(prefix),
                        'sha256': hashlib.sha256(prefix).hexdigest()}]
            if block:
                samples.append({'file_offset': offset, 'file_size': len(block),
                                'sha256': hashlib.sha256(block).hexdigest()})
            if volume is not None:
                result['filesystem'] = volume
                result['valid'] = result['valid'] and volume['valid']
                result['warnings'].extend(volume['warnings'])
                result['metadata']['primary_volume_descriptor_parsed'] = volume['format'] == 'ISO 9660 primary volume descriptor'
                result['regions'].append({'name': 'sector-16 volume descriptor candidate', 'kind': 'volume_descriptor_sector',
                                          'file_offset': offset, 'file_size': len(block)})
            result = {**result, 'report_format': 'fdisbull-rom-inspection-1',
                      'source_size': before.st_size, 'source_sha256': None,
                      'prefix_size': len(prefix), 'prefix_sha256': hashlib.sha256(prefix).hexdigest(),
                      'sampled_regions': samples,
                      'hash_scope': 'sampled regions only; whole-file identity not established', 'loadable': False,
                      'validation_scope': 'sector-zero descriptor, framing and optional sector-16 primary volume descriptor'}
        else:
            if before.st_size > MAX_ROM_SIZE:
                raise ValueError('unrecognized media over 64 MiB; a disc reader is required')
            data = prefix + stream.read(MAX_ROM_SIZE + 1 - len(prefix))
            result = inspect_rom(data)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('input changed during inspection')
    return result
