"""MZ container scaffold for the checked single-segment DOS code layout.

This is an output adapter, not an importer/relinker for arbitrary MZ games.
It preserves code/data IPs and emits its own loader-relocated startup sequence.
"""
from copy import deepcopy
from hashlib import sha256
import struct

from .code_backings import digest


def wrap_com_layout(layout):
    """Wrap an internal COM layout receipt; no file writes or native execution."""
    if (not isinstance(layout, dict)
            or layout.get('format') != 'fdisbull-dos-com-compilation-1'
            or layout.get('target') != 'dos-com16-i386'
            or layout.get('entry_ip') != 0x100):
        raise ValueError('MZ scaffold requires a checked COM16 layout')
    source = deepcopy(layout)
    checksum = source.pop('layout_sha256', None)
    if checksum != digest(source):
        raise ValueError('COM layout digest differs')
    encoded = source.get('bytes')
    if not isinstance(encoded, str) or len(encoded) > 2 * 0xef00:
        raise ValueError('COM image exceeds MZ single-segment code/data bounds')
    try:
        code = bytes.fromhex(encoded)
    except ValueError as exc:
        raise ValueError('invalid COM layout bytes') from exc
    if (not 3 <= len(code) <= 0xef00 or code[0] != 0xe9
            or sha256(code).hexdigest() != source.get('sha256')):
        raise ValueError('invalid COM layout payload or entry jump')

    # DOS enters an MZ with DS/ES referring to the PSP. Preserve caller AX and
    # flags while establishing the single-segment code layout's DS/ES contract.
    # The loader adds its actual load segment to the MOV immediate at 00F9h.
    module = bytearray(0x100) + code
    module[0xf7:0x100] = bytes.fromhex('50b800008ed88ec058')
    paragraphs = (len(module) + 15) // 16
    extra = 0x1000 - paragraphs  # Full 64 KiB for code/data plus reserved stack.
    length = 0x20 + len(module)
    header = struct.pack('<14H', 0x5a4d, length % 512, (length + 511) // 512,
                         1, 2, extra, extra, 0, 0xfffe, 0, 0xf7, 0, 0x1c, 0)
    raw = header + struct.pack('<HH', 0xf9, 0) + module

    result = deepcopy(source)
    result.update(format='fdisbull-dos-mz-compilation-1', target='dos-mz16-i386',
                  bytes=raw.hex(), sha256=sha256(raw).hexdigest(), entry_ip=0xf7,
                  code_layout_sha256=checksum, source_com_sha256=source['sha256'])
    # These offsets name emitted bytes, not retained source-file locations.
    for item in result['data'] + result['fixups']:
        item['file_offset'] += 0x120
    for item in result['occurrences']:
        item['file_offset'] = 0x20 + item['output_ip']
    result['output_ranges'].extend([
        {'kind': 'zero_padding', 'start_ip': 0, 'end_ip': 0xf7},
        {'kind': 'mz_startup', 'start_ip': 0xf7, 'end_ip': 0x100},
    ])
    result['output_ranges'].sort(key=lambda item: item['start_ip'])
    for item in result['output_ranges']:
        item['file_offset'] = 0x20 + item['start_ip']
        item['file_end'] = 0x20 + item['end_ip']
    result['container'] = {
        'format': 'MZ', 'header_size': 0x20, 'module_size': len(module),
        'allocation_size': 0x10000, 'initial_cs': 0, 'initial_ss': 0,
        'initial_ip': 0xf7, 'initial_sp': 0xfffe, 'overlay_size': 0,
        'min_extra_paragraphs': extra, 'max_extra_paragraphs': extra,
    }
    result['loader_relocations'] = [{
        'kind': 'load-segment-word', 'segment': 0, 'offset': 0xf9,
        'file_offset': 0x20 + 0xf9, 'original_word': 0,
        'purpose': 'DS/ES initialization from the loader-selected segment',
    }]
    result['abi'] = {**result['abi'], 'file_offset_to_ip': -0x20,
                     'startup': 'AX/flags preserved; DS/ES initialized by relocated scaffold',
                     'initial_ss': 0, 'initial_sp': 0xfffe}
    result['layout_sha256'] = digest(result)
    return result
