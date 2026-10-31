"""Sega CD/Saturn sector-zero descriptors, without filesystem or track loading.

References: https://github.com/file/file/blob/master/magic/Magdir/console
and https://github.com/SaturnSDK/Saturn-SDK-Tool-IPMaker .
"""

_SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
_CD_IDS = (b'SEGADISCSYSTEM  ', b'SEGABOOTDISC    ', b'SEGADATADISC    ')


def _text(data):
    return data.decode('ascii', errors='replace').strip(' \x00')


def parse_iso_primary(block: bytes, *, physical_sectors: int) -> dict | None:
    """Parse only an ISO 9660 primary volume descriptor at logical sector 16.

    ECMA-119: https://ecma-international.org/publications-and-standards/standards/ecma-119/
    Directory traversal, other descriptors and extent contents are not read.
    """
    if len(block) < 7 or block[1:6] != b'CD001' or block[0] != 1:
        return None
    result = {'format': 'ISO 9660 primary volume descriptor', 'valid': False,
              'warnings': [], 'directory_traversal': False}
    if len(block) < 2048:
        result['warnings'].append('Truncated primary volume descriptor')
        return result
    issues = result['warnings']
    def dual(pos, width, label):
        little = int.from_bytes(block[pos:pos + width], 'little')
        big = int.from_bytes(block[pos + width:pos + 2 * width], 'big')
        if little != big:
            issues.append(label + ' little/big-endian copies disagree')
        return little
    count = dual(80, 4, 'volume space size')
    size = dual(128, 2, 'logical block size')
    root_extent = dual(158, 4, 'root directory extent')
    root_size = dual(166, 4, 'root directory size')
    if (block[6] != 1 or size != 2048 or not count or block[156] < 34
            or not block[181] & 2 or block[188:190] != b'\x01\x00'):
        issues.append('Unsupported or invalid descriptor version, block size or root record')
    if count > physical_sectors:
        issues.append('Declared volume exceeds available physical track sectors; individual file completeness is unknown')
    if not root_size or root_extent < 18:
        issues.append('Root directory has no data or overlaps the descriptor/system area')
    if root_extent + block[157] + (root_size + 2047) // 2048 > min(count, physical_sectors):
        issues.append('Root directory extent exceeds the bounded volume')
    result.update(system_id=_text(block[8:40]), volume_id=_text(block[40:72]),
                  declared_sectors=count, physical_sectors=physical_sectors,
                  logical_block_size=size, root_directory_lba=root_extent,
                  root_directory_size=root_size, valid=not issues)
    return result


def parse_disc_volume(sector_data: bytes, *, sector_size: int, physical_sectors: int) -> dict | None:
    """Validate the observed sector-16 framing before reading its user bytes."""
    if not sector_data:
        return None
    if sector_size == 2352:
        if len(sector_data) < 2352 or sector_data[:12] != _SYNC or sector_data[15] != 1:
            return {'format': 'unverified ISO volume candidate', 'valid': False,
                    'directory_traversal': False,
                    'warnings': ['Sector 16 lacks a complete raw Mode 1 frame; ISO descriptor not interpreted']}
        block = sector_data[16:2064]
    else:
        block = sector_data
    return parse_iso_primary(block, physical_sectors=physical_sectors)


def parse_sega_disc(data: bytes, *, file_size: int | None = None) -> dict | None:
    """Inspect a first-sector prefix; file_size is the complete track size."""
    if not isinstance(data, bytes):
        raise ValueError('disc inspection requires bytes')
    if len(data) > 64 * 1024 * 1024:
        raise ValueError('disc prefix exceeds 64 MiB')
    total = len(data) if file_size is None else file_size
    if type(total) is not int or total < len(data):
        raise ValueError('file_size must cover the supplied prefix')
    # A data track must start here. CUE pregaps, audio tracks and CHD require
    # separate readers; searching arbitrary offsets would invent track origin.
    choices = [(0, 2048, 'cooked 2048')]
    if data[:12] == _SYNC and len(data) >= 16:
        if data[15] == 1:
            choices.append((16, 2352, 'raw Mode 1 / 2352'))
    for offset, sector, framing in choices:
        signature = data[offset:offset + 16]
        saturn = signature == b'SEGA SEGASATURN '
        if not saturn and signature not in _CD_IDS:
            continue
        warnings = []
        valid = True
        if len(data) < offset + 256 or total < sector:
            valid = False
            warnings.append('Truncated first data sector or system descriptor')
        if total % sector:
            valid = False
            warnings.append('Track length is not a whole number of declared sectors')
        meta = {'signature': _text(signature), 'sector_size': sector,
                'sector_user_data_offset': offset, 'framing': framing,
                'track_origin': 'supplied file starts at data-track sector zero',
                'primary_volume_descriptor_parsed': False, 'directory_traversal': False}
        if len(data) >= offset + 256:
            h = data[offset:offset + 256]
            if saturn:
                meta.update(maker=_text(h[0x10:0x20]), product=_text(h[0x20:0x2a]),
                            version=_text(h[0x2a:0x30]), release_date=_text(h[0x30:0x38]),
                            device=_text(h[0x38:0x40]), region=_text(h[0x40:0x4a]),
                            peripherals=_text(h[0x50:0x60]), title=_text(h[0x60:0xd0]),
                            declared_ip_size=int.from_bytes(h[0xe0:0xe4], 'big'))
            # Mega-CD uses the cartridge-style software information at 0x100;
            # keep the system-ID descriptor narrow instead of guessing IP code.
        if not saturn and len(data) >= offset + 512:
            h = data[offset:offset + 512]
            meta.update(domestic_title=_text(h[0x120:0x150]),
                        overseas_title=_text(h[0x150:0x180]), product=_text(h[0x180:0x18e]))
        warnings.append('Filesystem contents, other tracks, security and execution are unverified')
        return {'format': 'Sega Saturn disc' if saturn else 'Sega CD disc',
                'family': 'console disc', 'platform': 'Sega Saturn' if saturn else 'Sega CD / Mega-CD',
                'arch': 'sh2' if saturn else 'm68000', 'bits': 32 if saturn else 16,
                'endian': 'big', 'header_offset': offset, 'valid': valid, 'descriptor_valid': valid,
                'detection': 'magic', 'metadata': meta,
                'regions': [{'name': 'sector-zero system descriptor', 'kind': 'header',
                             'file_offset': offset, 'file_size': min(256 if saturn else 512, max(0, len(data) - offset))}],
                'warnings': warnings}
    return None
