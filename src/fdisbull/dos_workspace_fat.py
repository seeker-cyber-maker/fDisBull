"""Deterministic FAT16 workspace volumes and a two-partition DOS disk.

This module has no host-directory traversal or guest-runtime side effects.
Callers must inventory and pin the source tree separately, then pass the
bounded DOS 8.3 view here. The C volume is a supplied 1.44 MiB FAT12 FreeDOS
floppy image; the D volume is an ordinary private FAT16 block device.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import math
import re
import struct


SECTOR = 512
FLOPPY_BYTES = 1474560
DEFAULT_WORKSPACE_BYTES = 32 * 1024 * 1024
MIN_WORKSPACE_BYTES = 4 * 1024 * 1024
MAX_WORKSPACE_BYTES = 48 * 1024 * 1024
MAX_ENTRIES = 8192
MAX_DEPTH = 16
MAX_FILE_BYTES = MAX_WORKSPACE_BYTES
_C_START_LBA = 2048
_GEOMETRY_HEADS = 16
_GEOMETRY_SECTORS = 63
_SHORT_COMPONENT = re.compile(r"[A-Z0-9!#$%&'()@^_`{}~+\-]{1,8}(?:\.[A-Z0-9!#$%&'()@^_`{}~+\-]{1,3})?\Z")
_RESERVED_NAMES = frozenset({'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$'} |
    {f'COM{i}' for i in range(1, 10)} | {f'LPT{i}' for i in range(1, 10)})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _align(value: int, multiple: int) -> int:
    return (value + multiple - 1) // multiple * multiple


def _dos_word(value, label):
    if value is None:
        return 0x0021 if label == 'date' else 0
    if type(value) is not int or not 0 <= value <= 0xffff:
        raise ValueError(f'DOS {label} must be a packed 16-bit word')
    if label == 'date':
        year, month, day = (value >> 9) & 0x7f, (value >> 5) & 0xf, value & 0x1f
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            raise ValueError('DOS date has invalid month or day fields')
    else:
        hour, minute, two_seconds = (value >> 11) & 0x1f, (value >> 5) & 0x3f, value & 0x1f
        if hour > 23 or minute > 59 or two_seconds > 29:
            raise ValueError('DOS time has invalid hour, minute or second fields')
    return value


def _path_parts(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or path.startswith(('\\', '/')) or '/' in path:
        raise ValueError('Workspace path must be relative and use DOS backslashes')
    parts = tuple(path.split('\\'))
    if len(parts) > MAX_DEPTH or any(not part for part in parts):
        raise ValueError('Workspace path is empty or exceeds the directory depth limit')
    result = []
    for part in parts:
        upper = part.upper()
        if not _SHORT_COMPONENT.fullmatch(upper) or upper in ('.', '..'):
            raise ValueError('Workspace paths require unambiguous DOS 8.3 components')
        base = upper.split('.', 1)[0]
        if base in _RESERVED_NAMES:
            raise ValueError('Workspace path uses a reserved DOS device name')
        result.append(upper)
    return tuple(result)


def _short_name(part: str) -> bytes:
    base, dot, extension = part.partition('.')
    if len(base) > 8 or len(extension) > 3:
        raise ValueError('Workspace name does not fit DOS 8.3 format')
    try:
        return (base.ljust(8) + (extension if dot else '').ljust(3)).encode('ascii')
    except UnicodeEncodeError as error:
        raise ValueError('Workspace short names must be ASCII') from error


def _normalize_entries(entries):
    if not isinstance(entries, Mapping):
        raise ValueError('Workspace entries must be a path-keyed mapping')
    if len(entries) > MAX_ENTRIES:
        raise ValueError('Workspace exceeds the bounded entry count')
    nodes = {'': dict(path='', type='directory', attributes=0x10,
                      dos_date=0x0021, dos_time=0, data=b'', explicit=True)}
    for raw_path, raw_spec in entries.items():
        parts = _path_parts(raw_path)
        if not isinstance(raw_spec, Mapping):
            raise ValueError('Workspace entry specifications must be mappings')
        kind = raw_spec.get('type')
        if kind not in ('file', 'directory'):
            raise ValueError('Workspace entry type must be file or directory')
        data = raw_spec.get('data', b'')
        if kind == 'directory':
            if data not in (b'', None):
                raise ValueError('Directories cannot carry file bytes')
            data = b''
        elif not isinstance(data, bytes):
            raise ValueError('Workspace file data must be bytes')
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('Workspace file exceeds the bounded size')
        default_attr = 0x20 if kind == 'file' else 0x10
        attributes = raw_spec.get('attributes', default_attr)
        if type(attributes) is not int or not 0 <= attributes <= 0xff:
            raise ValueError('DOS attributes must be an unsigned byte')
        if attributes & 0x08 or attributes & 0x0f not in (0, 0x01, 0x02, 0x04, 0x07):
            raise ValueError('Volume-label or unsupported DOS attributes are not admitted')
        if kind == 'directory':
            if attributes & 0x20:
                raise ValueError('Directories cannot carry the archive attribute')
            attributes |= 0x10
        elif attributes & 0x10:
            raise ValueError('Regular files cannot carry the directory attribute')
        node_path = '\\'.join(parts)
        if node_path in nodes:
            raise ValueError('Workspace contains duplicate or conflicting DOS paths')
        node = dict(path=node_path, type=kind, attributes=attributes,
                    dos_date=_dos_word(raw_spec.get('dos_date'), 'date'),
                    dos_time=_dos_word(raw_spec.get('dos_time'), 'time'),
                    data=data, explicit=True)
        nodes[node_path] = node
        for depth in range(1, len(parts)):
            parent = '\\'.join(parts[:depth])
            existing = nodes.get(parent)
            if existing is None:
                nodes[parent] = dict(path=parent, type='directory', attributes=0x10,
                    dos_date=0x0021, dos_time=0, data=b'', explicit=False)
            elif existing['type'] != 'directory':
                raise ValueError('A workspace file is used as a parent directory')
    if len(nodes) - 1 > MAX_ENTRIES:
        raise ValueError('Workspace including implicit directories exceeds the entry count')
    children = {path: [] for path, node in nodes.items() if node['type'] == 'directory'}
    for path, node in nodes.items():
        if not path:
            continue
        parent, _, name = path.rpartition('\\')
        children[parent].append((name, path, node))
    for rows in children.values():
        rows.sort(key=lambda row: row[0])
    return nodes, children


def _layout_fat16(size_bytes):
    if type(size_bytes) is not int or size_bytes % SECTOR or not MIN_WORKSPACE_BYTES <= size_bytes <= MAX_WORKSPACE_BYTES:
        raise ValueError('Workspace volume must be sector-aligned and 4..48 MiB')
    total = size_bytes // SECTOR
    for sectors_per_cluster in (1, 2, 4, 8, 16, 32, 64):
        root_entries = 512
        root_sectors = root_entries * 32 // SECTOR
        fat_sectors = 1
        for _ in range(32):
            clusters = (total - 1 - 2 * fat_sectors - root_sectors) // sectors_per_cluster
            wanted = math.ceil((clusters + 2) * 2 / SECTOR)
            if wanted == fat_sectors:
                break
            fat_sectors = wanted
        clusters = (total - 1 - 2 * fat_sectors - root_sectors) // sectors_per_cluster
        if 4085 <= clusters <= 65524 and fat_sectors <= 0xffff:
            return dict(total=total, spc=sectors_per_cluster, reserved=1, fats=2,
                        fat_sectors=fat_sectors, root_entries=root_entries,
                        root_sectors=root_sectors, first_data=1 + 2 * fat_sectors + root_sectors,
                        clusters=clusters)
    raise ValueError('Workspace size cannot be represented as bounded FAT16')


def build_volume(entries, size_bytes=DEFAULT_WORKSPACE_BYTES) -> bytes:
    """Build one deterministic FAT16 volume from a DOS-short-path inventory."""
    layout = _layout_fat16(size_bytes)
    nodes, children = _normalize_entries(entries)
    cluster_size = layout['spc'] * SECTOR
    next_cluster = 2
    fat = [0xfff8, 0xffff]

    def allocate(count):
        nonlocal next_cluster
        if count == 0:
            return []
        end = next_cluster + count
        if end > layout['clusters'] + 2:
            raise ValueError('Workspace contents exceed the FAT16 volume')
        result = list(range(next_cluster, end))
        next_cluster = end
        while len(fat) < end:
            fat.append(0)
        for index, cluster in enumerate(result):
            fat[cluster] = result[index + 1] if index + 1 < len(result) else 0xffff
        return result

    # Allocate all directory extents before files, in a stable depth/path order.
    directories = sorted((node for path, node in nodes.items() if path),
                         key=lambda node: (node['type'] != 'directory', node['path'].count('\\'), node['path']))
    for node in directories:
        if node['type'] != 'directory':
            continue
        entries_count = len(children[node['path']]) + 2
        node['clusters'] = allocate(max(1, math.ceil(entries_count * 32 / cluster_size)))
        node['first_cluster'] = node['clusters'][0]
    for node in sorted((item for item in nodes.values() if item['type'] == 'file'), key=lambda row: row['path']):
        needed = math.ceil(len(node['data']) / cluster_size)
        node['clusters'] = allocate(needed)
        node['first_cluster'] = node['clusters'][0] if node['clusters'] else 0

    volume = bytearray(size_bytes)
    boot = memoryview(volume)[:SECTOR]
    boot[0:3] = b'\xeb\x3c\x90'
    boot[3:11] = b'FDBFAT16'
    struct.pack_into('<HBHBHHBHHHII', boot, 11, SECTOR, layout['spc'], layout['reserved'],
                     layout['fats'], layout['root_entries'],
                     layout['total'] if layout['total'] <= 0xffff else 0,
                     0xf8, layout['fat_sectors'], _GEOMETRY_SECTORS, _GEOMETRY_HEADS,
                     0, layout['total'] if layout['total'] > 0xffff else 0)
    boot[36] = 0x80
    boot[37] = 0
    boot[38] = 0x29
    struct.pack_into('<I', boot, 39, 0x46444231)
    boot[43:54] = b'FDBWORK    '
    boot[54:62] = b'FAT16   '
    boot[510:512] = b'\x55\xaa'

    fat_start = SECTOR
    fat_bytes = bytearray(layout['fat_sectors'] * SECTOR)
    for cluster, value in enumerate(fat):
        if cluster >= layout['clusters'] + 2:
            break
        struct.pack_into('<H', fat_bytes, cluster * 2, value)
    volume[fat_start:fat_start + len(fat_bytes)] = fat_bytes
    second_fat = fat_start + len(fat_bytes)
    volume[second_fat:second_fat + len(fat_bytes)] = fat_bytes

    root_offset = (layout['reserved'] + layout['fats'] * layout['fat_sectors']) * SECTOR
    data_offset = layout['first_data'] * SECTOR

    def short_entry(name, node, first_cluster, *, dot=False):
        raw = bytearray(32)
        raw[:11] = _short_name(name) if not dot else (b'.          ' if name == '.' else b'..         ')
        attr = node['attributes']
        if dot:
            attr = 0x10
        raw[11] = attr
        struct.pack_into('<H', raw, 14, node['dos_time'])
        struct.pack_into('<H', raw, 16, node['dos_date'])
        struct.pack_into('<H', raw, 18, node['dos_date'])
        struct.pack_into('<H', raw, 22, node['dos_time'])
        struct.pack_into('<H', raw, 24, node['dos_date'])
        struct.pack_into('<H', raw, 26, first_cluster)
        struct.pack_into('<I', raw, 28, len(node['data']) if node['type'] == 'file' else 0)
        return raw

    def directory_bytes(node):
        rows = []
        if node['path']:
            parent = node['path'].rpartition('\\')[0]
            rows.append(short_entry('.', node, node['first_cluster'], dot=True))
            parent_cluster = nodes[parent]['first_cluster'] if parent else 0
            rows.append(short_entry('..', node, parent_cluster, dot=True))
        for name, _path, child in children[node['path']]:
            rows.append(short_entry(name, child, child['first_cluster']))
        raw = b''.join(rows) + b'\x00' * (len(node['clusters']) * cluster_size - len(rows) * 32)
        return raw

    def write_chain(clusters, payload):
        for index, cluster in enumerate(clusters):
            start = data_offset + (cluster - 2) * cluster_size
            part = payload[index * cluster_size:(index + 1) * cluster_size]
            volume[start:start + cluster_size] = part.ljust(cluster_size, b'\x00')

    root_rows = [short_entry(name, child, child['first_cluster'])
                 for name, _path, child in children['']]
    if len(root_rows) > layout['root_entries']:
        raise ValueError('Workspace root directory exceeds its fixed FAT16 entry table')
    root_data = b''.join(root_rows)
    volume[root_offset:root_offset + len(root_data)] = root_data
    for node in directories:
        if node['type'] == 'directory':
            write_chain(node['clusters'], directory_bytes(node))
    for node in nodes.values():
        if node['type'] == 'file':
            write_chain(node['clusters'], node['data'])
    return bytes(volume)


class _Fat16:
    def __init__(self, data: bytes):
        if not isinstance(data, bytes) or len(data) < MIN_WORKSPACE_BYTES or len(data) > MAX_WORKSPACE_BYTES or len(data) % SECTOR:
            raise ValueError('FAT16 workspace volume has an unsupported byte length')
        if data[510:512] != b'\x55\xaa':
            raise ValueError('FAT16 workspace boot signature is missing')
        if _u16(data, 11) != SECTOR:
            raise ValueError('Workspace volume must use 512-byte sectors')
        self.spc = data[13]
        self.reserved = _u16(data, 14)
        self.fats = data[16]
        self.root_entries = _u16(data, 17)
        total = _u16(data, 19) or _u32(data, 32)
        self.fat_sectors = _u16(data, 22)
        self.hidden_sectors = _u32(data, 28)
        self.sectors = len(data) // SECTOR
        self.root_sectors = math.ceil(self.root_entries * 32 / SECTOR)
        if (not self.spc or self.spc & (self.spc - 1) or self.spc > 64
                or self.reserved < 1 or self.fats != 2 or not self.root_entries
                or not self.fat_sectors or total != self.sectors):
            raise ValueError('Unsupported or malformed FAT16 BPB')
        self.first_data = self.reserved + self.fats * self.fat_sectors + self.root_sectors
        if self.first_data >= total:
            raise ValueError('FAT16 data region lies outside the volume')
        self.clusters = (total - self.first_data) // self.spc
        if not 4085 <= self.clusters <= 65524:
            raise ValueError('Workspace volume is not FAT16')
        fat_start = self.reserved * SECTOR
        fat_bytes = self.fat_sectors * SECTOR
        needed = (self.clusters + 2) * 2
        if fat_bytes < needed:
            raise ValueError('FAT16 allocation table is too short')
        self.fat_data = data[fat_start:fat_start + fat_bytes]
        if data[fat_start + fat_bytes:fat_start + 2 * fat_bytes] != self.fat_data:
            raise ValueError('FAT16 copies disagree')
        self.fat = [_u16(self.fat_data, index * 2) for index in range(self.clusters + 2)]
        self.data = data
        self.cluster_bytes = self.spc * SECTOR
        self.data_offset = self.first_data * SECTOR
        self.root_offset = (self.reserved + self.fats * self.fat_sectors) * SECTOR
        self.root_bytes = self.root_entries * 32
        self.used = set()
        self.count = 0

    def chain(self, first, *, expected=None):
        if first == 0 and expected == 0:
            return []
        if not 2 <= first < self.clusters + 2:
            raise ValueError('Invalid FAT16 first cluster')
        result = []
        seen = set()
        current = first
        while True:
            if not 2 <= current < self.clusters + 2 or current in seen or current in self.used:
                raise ValueError('FAT16 cluster chain is invalid, cyclic or cross-linked')
            seen.add(current)
            result.append(current)
            if len(result) > self.clusters:
                raise ValueError('FAT16 chain exceeds the volume cluster count')
            value = self.fat[current]
            if value >= 0xfff8:
                break
            if value == 0xfff7 or 0xfff0 <= value <= 0xfff6 or value < 2:
                raise ValueError('FAT16 chain reaches a free, reserved or bad cluster')
            current = value
        self.used.update(seen)
        if expected is not None and len(result) < expected:
            raise ValueError('FAT16 file chain is shorter than its declared size')
        return result

    def bytes_for(self, clusters, size=None):
        chunks = []
        for cluster in clusters:
            start = self.data_offset + (cluster - 2) * self.cluster_bytes
            chunk = self.data[start:start + self.cluster_bytes]
            if len(chunk) != self.cluster_bytes:
                raise ValueError('FAT16 cluster extends beyond the volume')
            chunks.append(chunk)
        result = b''.join(chunks)
        return result if size is None else result[:size]


def parse_volume(data: bytes) -> dict[str, dict]:
    """Parse a strict FAT16 8.3 view; refuse LFN, corruption and cross-links."""
    fs = _Fat16(data)
    result = {}
    root = data[fs.root_offset:fs.root_offset + fs.root_bytes]
    active_dirs = set()

    def parse_directory(path, raw, depth):
        if depth > MAX_DEPTH:
            raise ValueError('FAT16 directory tree exceeds the depth limit')
        for offset in range(0, len(raw), 32):
            entry = raw[offset:offset + 32]
            if len(entry) < 32 or entry[0] == 0:
                break
            if entry[0] == 0xe5:
                continue
            attr = entry[11]
            if attr == 0x0f:
                raise ValueError('Long filename entries are outside the supported FAT16 workspace contract')
            if attr & 0x08:
                continue
            if entry[0] == ord('.'):
                continue
            name_raw = entry[:8].decode('ascii', errors='strict').rstrip(' ')
            ext_raw = entry[8:11].decode('ascii', errors='strict').rstrip(' ')
            name = name_raw + ('.' + ext_raw if ext_raw else '')
            if not _SHORT_COMPONENT.fullmatch(name):
                raise ValueError('FAT16 directory contains an invalid short name')
            parts = tuple(part for part in (path + '\\' + name).split('\\') if part)
            canonical = '\\'.join(parts)
            if canonical in result:
                raise ValueError('FAT16 directory contains duplicate paths')
            if attr & 0xc0 or attr & 0x08 or (attr & 0x10 and attr & 0x20):
                raise ValueError('FAT16 entry has unsupported attribute combinations')
            first = _u16(entry, 26)
            size = _u32(entry, 28)
            dos_time = _u16(entry, 22)
            dos_date = _u16(entry, 24)
            _dos_word(dos_time, 'time'); _dos_word(dos_date, 'date')
            if attr & 0x10:
                if size != 0 or first < 2:
                    raise ValueError('FAT16 directory has invalid size or cluster')
                if first in active_dirs:
                    raise ValueError('FAT16 directory graph contains a cycle')
                clusters = fs.chain(first)
                active_dirs.add(first)
                child_raw = fs.bytes_for(clusters)
                result[canonical] = dict(type='directory', data=b'', attributes=attr,
                                         dos_date=dos_date, dos_time=dos_time)
                fs.count += 1
                if fs.count > MAX_ENTRIES:
                    raise ValueError('FAT16 directory exceeds the entry count limit')
                parse_directory(canonical, child_raw, depth + 1)
                active_dirs.remove(first)
            else:
                expected = math.ceil(size / fs.cluster_bytes)
                if size == 0 and first != 0:
                    raise ValueError('Empty FAT16 file has an unexpected allocated cluster chain')
                clusters = fs.chain(first, expected=expected) if expected else fs.chain(first, expected=0)
                content = fs.bytes_for(clusters, size)
                result[canonical] = dict(type='file', data=content, attributes=attr,
                                         dos_date=dos_date, dos_time=dos_time)
                fs.count += 1
                if fs.count > MAX_ENTRIES or size > MAX_FILE_BYTES:
                    raise ValueError('FAT16 file set exceeds its bounded limits')

    parse_directory('', root, 0)
    for cluster in range(2, fs.clusters + 2):
        if cluster not in fs.used and fs.fat[cluster] != 0:
            raise ValueError('FAT16 volume contains an unowned allocated cluster')
    return result


def _chs(lba):
    cylinder, remainder = divmod(lba, _GEOMETRY_HEADS * _GEOMETRY_SECTORS)
    head, sector0 = divmod(remainder, _GEOMETRY_SECTORS)
    if cylinder > 1023:
        return b'\xfe\xff\xff'
    sector = sector0 + 1
    return bytes((head, sector | ((cylinder >> 2) & 0xc0), cylinder & 0xff))


def _partition(status, kind, first_lba, sectors):
    if not 0 < sectors <= 0xffffffff or not 0 <= first_lba <= 0xffffffff:
        raise ValueError('Partition extent is outside the MBR LBA range')
    return bytes((status,)) + _chs(first_lba) + bytes((kind,)) + _chs(first_lba + sectors - 1) + struct.pack('<II', first_lba, sectors)


def _mbr_boot_code(start_lba):
    """Build the exact self-relocating LBA MBR body mirrored by the ASM."""
    # First copy all 512 bytes away from 0000:7c00. Loading the C VBR into
    # 0000:7c00 would otherwise overwrite this code before INT 13h returns.
    code = bytearray.fromhex('fa31c08ed88ec0be007cbf0006b90001fcf3a5ea18006000')
    if len(code) != 24:
        raise AssertionError('MBR relocation prologue layout changed')
    drive_offset = 65
    dap_offset = 66
    code += bytes.fromhex('31c08ed0bc007c8cc88ed8fb8816')
    code += struct.pack('<H', drive_offset)
    code += b'\xbe' + struct.pack('<H', dap_offset)
    code += bytes.fromhex('b442cd130e1f72098a16')
    code += struct.pack('<H', drive_offset)
    code += bytes.fromhex('ea007c0000cd18f4ebfe')
    if len(code) != drive_offset:
        raise AssertionError('Relocated MBR body layout changed')
    code += b'\x00'
    dap = bytearray.fromhex('10000100007c0000') + struct.pack('<Q', start_lba)
    code += dap
    if len(code) != dap_offset + 16:
        raise AssertionError('Relocated MBR DAP layout changed')
    return bytes(code).ljust(440, b'\x00')


def _validate_system_volume(system_bytes):
    if not isinstance(system_bytes, bytes) or len(system_bytes) != FLOPPY_BYTES:
        raise ValueError('FreeDOS system volume must be the pinned 1.44 MiB floppy image')
    from .qemm_runtime import _FATVolume
    volume = _FATVolume(system_bytes)
    if volume.partition is not None or volume.bits != 12 or volume.boot_device != 'floppy':
        raise ValueError('FreeDOS system input must be a standalone FAT12 floppy volume')
    return volume


def _patched_system_vbr(system_bytes, hidden_sectors):
    _validate_system_volume(system_bytes)
    result = bytearray(system_bytes)
    struct.pack_into('<H', result, 24, _GEOMETRY_SECTORS)
    struct.pack_into('<H', result, 26, _GEOMETRY_HEADS)
    struct.pack_into('<I', result, 28, hidden_sectors)
    result[36] = 0x80
    return bytes(result)


def _partition_layout(composite):
    if not isinstance(composite, bytes) or len(composite) < 512 or len(composite) % SECTOR:
        raise ValueError('Composite DOS disk must contain whole sectors')
    if composite[510:512] != b'\x55\xaa':
        raise ValueError('Composite DOS disk lacks an MBR signature')
    entries = []
    active = []
    for index in range(4):
        raw = composite[446 + index * 16:462 + index * 16]
        status, kind = raw[0], raw[4]
        first, count = struct.unpack_from('<II', raw, 8)
        if status not in (0, 0x80):
            raise ValueError('Composite MBR has invalid partition status')
        if kind == 0 and (first or count or status):
            raise ValueError('Composite MBR has malformed empty partition entry')
        if kind:
            if not first or not count or first + count > len(composite) // SECTOR:
                raise ValueError('Composite MBR partition lies outside the disk')
            if status == 0x80:
                active.append(index)
            entries.append(dict(index=index, status=status, type=kind, start_lba=first,
                                sectors=count, offset=first * SECTOR, size=count * SECTOR))
    if len(entries) != 2 or len(active) != 1:
        raise ValueError('Composite disk requires exactly active C and data D primary partitions')
    entries.sort(key=lambda item: item['start_lba'])
    c, d = entries
    if (c['index'] != active[0] or c['type'] != 0x01 or c['status'] != 0x80
            or c['start_lba'] != _C_START_LBA or c['size'] != FLOPPY_BYTES
            or d['type'] != 0x06 or d['status'] != 0
            or d['start_lba'] + d['sectors'] != len(composite) // SECTOR):
        raise ValueError('Composite partition identities differ from the C:FAT12 / D:FAT16 contract')
    if c['start_lba'] + c['sectors'] > d['start_lba']:
        raise ValueError('Composite DOS partitions overlap')
    if composite[:440] != _mbr_boot_code(c['start_lba']):
        raise ValueError('Composite MBR boot code differs from the authored relocating loader')
    c_volume = composite[c['offset']:c['offset'] + c['size']]
    _validate_system_volume(c_volume)
    if (_u32(c_volume, 28) != c['start_lba'] or c_volume[36] != 0x80
            or _u16(c_volume, 24) != _GEOMETRY_SECTORS
            or _u16(c_volume, 26) != _GEOMETRY_HEADS):
        raise ValueError('C:FAT12 BPB differs from the composite disk geometry')
    d_volume = composite[d['offset']:d['offset'] + d['size']]
    d_fs = _Fat16(d_volume)
    if (d_fs.hidden_sectors != d['start_lba']
            or _u16(d_volume, 24) != _GEOMETRY_SECTORS
            or _u16(d_volume, 26) != _GEOMETRY_HEADS):
        raise ValueError('D:FAT16 BPB differs from its partition start or geometry')
    parse_volume(d_volume)
    return {'C': c, 'D': d}


def build_composite(system_bytes: bytes, workspace_volume: bytes):
    """Compose C:FAT12 and D:FAT16 with a relocating INT 13h MBR loader.

    Returns ``(composite_disk_bytes, partitions_receipt)``. The receipt pins
    exact partition positions and content hashes; it does not claim the system
    image has booted or FreeDOS has mounted D:.
    """
    _validate_system_volume(system_bytes)
    _Fat16(workspace_volume)
    parse_volume(workspace_volume)
    c_start = _C_START_LBA
    c_sectors = len(system_bytes) // SECTOR
    d_start = _align(c_start + c_sectors, 2048)
    d_sectors = len(workspace_volume) // SECTOR
    total_sectors = d_start + d_sectors
    if total_sectors * SECTOR >= 64 * 1024 * 1024:
        raise ValueError('Composite system/workspace disk must remain below the 64 MiB profile limit')
    composite = bytearray(total_sectors * SECTOR)
    composite[:440] = _mbr_boot_code(c_start)
    composite[440:444] = hashlib.sha256(system_bytes + workspace_volume).digest()[:4]
    composite[446:462] = _partition(0x80, 0x01, c_start, c_sectors)
    composite[462:478] = _partition(0x00, 0x06, d_start, d_sectors)
    composite[510:512] = b'\x55\xaa'
    c_volume = _patched_system_vbr(system_bytes, c_start)
    d_volume = bytearray(workspace_volume)
    if _u32(d_volume, 28) != 0:
        raise ValueError('Input D:FAT16 workspace must be a standalone zero-hidden-sector volume')
    struct.pack_into('<I', d_volume, 28, d_start)
    c_offset, d_offset = c_start * SECTOR, d_start * SECTOR
    composite[c_offset:c_offset + len(c_volume)] = c_volume
    composite[d_offset:d_offset + len(d_volume)] = d_volume
    result = bytes(composite)
    layout = _partition_layout(result)
    receipt = dict(format='fdisbull-dos-workspace-disk-1', size=len(result),
        sha256=_sha(result), geometry=dict(heads=_GEOMETRY_HEADS, sectors_per_track=_GEOMETRY_SECTORS),
        partitions={name: {key: entry[key] for key in ('index', 'status', 'type', 'start_lba', 'sectors', 'offset', 'size')}
                    for name, entry in layout.items()},
        c_sha256=_sha(c_volume), source_workspace_sha256=_sha(workspace_volume), d_sha256=_sha(d_volume),
        mbr_loader='authored INT 13h extensions read C VBR at LBA 2048 and preserve BIOS DL=0x80; boot not runtime-verified')
    return result, receipt


def composite(system_bytes: bytes, workspace_volume: bytes):
    """Public alias for :func:`build_composite`."""
    return build_composite(system_bytes, workspace_volume)


def volume_layout(composite: bytes) -> dict[str, dict]:
    """Validate the composite partition table and return byte extents."""
    return {name: dict(value) for name, value in _partition_layout(composite).items()}


def replace_workspace(composite: bytes, new_volume: bytes) -> bytes:
    """Replace D with a validated same-size FAT16 image, retaining C and MBR."""
    layout = _partition_layout(composite)
    _Fat16(new_volume)
    target = layout['D']
    if len(new_volume) != target['size']:
        raise ValueError('Replacement workspace volume must retain its admitted size')
    parse_volume(new_volume)
    result = bytearray(composite)
    start = target['offset']
    if _u32(new_volume, 28) not in (0, target['start_lba']):
        raise ValueError('Replacement D:FAT16 image has an unexpected hidden-sector origin')
    mounted = bytearray(new_volume)
    struct.pack_into('<I', mounted, 28, target['start_lba'])
    result[start:start + target['size']] = mounted
    return bytes(result)
