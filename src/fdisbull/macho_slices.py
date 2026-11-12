"""Bounded Mach-O universal inventory and explicit CPU-slice selection.

Offsets in the inventory refer to the original container. The selected bytes
remain a complete thin Mach-O, whose internal file offsets are slice-relative.
This helper neither maps an image nor rewrites any bytes or file offsets.
"""
from __future__ import annotations

import hashlib
import struct

MAX_MACHO_SIZE = 64 * 1024 * 1024
MAX_MACHO_SLICES = 128
_THIN = {b'\xce\xfa\xed\xfe': (32, 'little'), b'\xcf\xfa\xed\xfe': (64, 'little'),
         b'\xfe\xed\xfa\xce': (32, 'big'), b'\xfe\xed\xfa\xcf': (64, 'big')}
_FAT = {b'\xca\xfe\xba\xbe': (32, 'big'), b'\xbe\xba\xfe\xca': (32, 'little'),
        b'\xca\xfe\xba\xbf': (64, 'big'), b'\xbf\xba\xfe\xca': (64, 'little')}
_CPUS = {7: ('x86', 32, 'x86'), 0x01000007: ('x86', 64, 'x86_64'),
         0x0100000C: ('arm64', 64, 'arm64')}
_SELECTORS = {'x86', 'x86_64', 'arm64'}


def _data(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError('Mach-O input must be bytes')
    size = value.nbytes if isinstance(value, memoryview) else len(value)
    if not 4 <= size <= MAX_MACHO_SIZE:
        raise ValueError('Mach-O input must contain 4 bytes to 64 MiB')
    return value if isinstance(value, bytes) else bytes(value)


def _thin(data, offset, size):
    magic = data[offset:offset + 4]
    if magic not in _THIN:
        raise ValueError('Mach-O slice must contain a thin Mach-O header')
    bits, endian = _THIN[magic]
    header_size = 32 if bits == 64 else 28
    if size < header_size:
        raise ValueError('truncated thin Mach-O header')
    prefix = '<' if endian == 'little' else '>'
    cpu, subtype, file_type, count, command_size, flags = struct.unpack_from(prefix + '6I', data, offset + 4)
    if count > 4096 or command_size > size - header_size or count * 8 > command_size:
        raise ValueError('thin Mach-O load-command extent or count is invalid')
    position, last = offset + header_size, offset + header_size + command_size
    for _ in range(count):
        if position + 8 > last:
            raise ValueError('truncated thin Mach-O load command')
        length = struct.unpack_from(prefix + 'I', data, position + 4)[0]
        if length < 8 or position + length > last:
            raise ValueError('invalid thin Mach-O load-command extent')
        position += length
    supported = _CPUS.get(cpu)
    if supported and supported[1] != bits:
        raise ValueError('thin Mach-O CPU type conflicts with header bitness')
    return dict(arch=supported[0] if supported else None, bits=bits,
                selector=supported[2] if supported else None, supported=supported is not None,
                cpu_type=cpu, cpu_subtype=subtype, subtype_base=subtype & 0x00FFFFFF,
                subtype_capabilities=subtype & 0xFF000000, endian=endian,
                header_size=header_size, file_type=file_type, command_count=count,
                command_bytes=command_size, flags=flags)


def macho_slices(data) -> list[dict]:
    """Inventory thin or universal32/64 Mach-O, or raise ValueError.

    Validate every slice, including those that will not be selected: the table
    must fit, slices must be nonempty, aligned, disjoint, outside the table and
    inside the original file, and their thin CPU/subtype fields must match.
    Unsupported CPUs remain visible with supported=False; they cannot be selected.
    Alignment is the on-disk power-of-two exponent; alignment_bytes is its value.
    """
    data = _data(data)
    magic = data[:4]
    if magic in _THIN:
        return [dict(_thin(data, 0, len(data)), index=0, offset=0, size=len(data),
                     end_exclusive=len(data), alignment=None, alignment_bytes=None,
                     reserved=None, is_fat=False, container='thin', container_bits=None,
                     container_endian=_THIN[magic][1])]
    if magic not in _FAT:
        raise ValueError('input is not a thin or universal Mach-O')
    bits, endian = _FAT[magic]
    if len(data) < 8:
        raise ValueError('truncated universal Mach-O header')
    prefix = '<' if endian == 'little' else '>'
    count = struct.unpack_from(prefix + 'I', data, 4)[0]
    if not 1 <= count <= MAX_MACHO_SLICES:
        raise ValueError('universal Mach-O slice count must be in 1..128')
    stride = 32 if bits == 64 else 20
    table_end = 8 + count * stride
    if table_end > len(data):
        raise ValueError('truncated universal Mach-O slice table')
    records = []
    for index in range(count):
        position = 8 + index * stride
        if bits == 64:
            cpu, subtype, offset, size, alignment, reserved = struct.unpack_from(prefix + 'IIQQII', data, position)
            if reserved:
                raise ValueError('universal64 Mach-O reserved field must be zero')
        else:
            cpu, subtype, offset, size, alignment = struct.unpack_from(prefix + '5I', data, position)
            reserved = None
        if not size or offset < table_end or offset + size > len(data) or offset + size > 1 << bits:
            raise ValueError('universal Mach-O slice extent is outside the file or overlaps its table')
        if alignment >= bits or offset % (1 << alignment):
            raise ValueError('universal Mach-O slice offset violates its alignment')
        records.append(dict(index=index, cpu_type=cpu, cpu_subtype=subtype, offset=offset,
                            size=size, end_exclusive=offset + size, alignment=alignment,
                            alignment_bytes=1 << alignment, reserved=reserved, is_fat=True,
                            container='fat', container_bits=bits, container_endian=endian))
    previous_end = table_end
    for record in sorted(records, key=lambda item: item['offset']):
        if record['offset'] < previous_end:
            raise ValueError('universal Mach-O slices overlap')
        previous_end = record['end_exclusive']
    result = []
    for record in records:
        thin = _thin(data, record['offset'], record['size'])
        if thin['cpu_type'] != record['cpu_type'] or thin['cpu_subtype'] != record['cpu_subtype']:
            raise ValueError('universal Mach-O CPU or subtype does not match its thin slice header')
        result.append(dict(record, **{key: value for key, value in thin.items() if key not in ('cpu_type', 'cpu_subtype')}))
    return result


def select_macho_slice(data, architecture=None) -> tuple[bytes, dict]:
    """Return one thin image plus original-container selection metadata.

    Fat inputs always require an explicit x86(32), x86_64 or arm64 selector.
    More than one matching CPU/subtype is an error; no subtype preference or
    host-architecture guess is made. A selector on a thin input must also match
    its bitness. The caller retains original bytes and adds slice_offset to
    thin-relative file mappings, disk metadata and patch translations.
    """
    data = _data(data)
    if architecture is not None and (not isinstance(architecture, str) or architecture not in _SELECTORS):
        raise ValueError('Mach-O architecture selector must be x86, x86_64 or arm64')
    slices = macho_slices(data)
    fat = slices[0]['is_fat']
    if fat and architecture is None:
        raise ValueError('universal Mach-O requires an explicit architecture selector')
    matches = [item for item in slices if item['supported'] and (architecture is None or item['selector'] == architecture)]
    if not matches:
        raise ValueError('requested Mach-O architecture/bitness is absent or unsupported')
    if len(matches) != 1:
        raise ValueError('Mach-O architecture selection is ambiguous across CPU subtypes')
    selected = matches[0]
    thin = data[selected['offset']:selected['end_exclusive']]
    metadata = dict(selected, architecture=selected['selector'], requested_architecture=architecture,
                    slice_index=selected['index'], slice_offset=selected['offset'], slice_size=selected['size'],
                    source_size=len(data), source_sha256=hashlib.sha256(data).hexdigest(),
                    slice_sha256=hashlib.sha256(thin).hexdigest(), slices=slices)
    return thin, metadata
