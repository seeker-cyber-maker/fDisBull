"""Bounded RTLink/Plus embedded-overlay analysis, without an external decoder.

The supported v2 table layout was researched using dreammaster/tools,
rtlink_decode/variation2.cpp (blob d6dfccff3c143d04fc169bdf2606b99105413b34).
This implementation retains source ranges, relocation records and unresolved
runtime identities. It does not copy the upstream heuristic EXE rewriter.
See docs/DOS_FORMATS_AND_RTLINK.md for provenance and qualification boundaries.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct

MAX_SOURCE = 64 * 1024 * 1024
MAX_OVERLAYS = 4096
MAX_RELOCATIONS = 262144
PROFILE = 'rtlink-plus-embedded-v2'


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _word(data, offset):
    _need(0 <= offset <= len(data) - 2, 'Truncated RTLink word')
    return struct.unpack_from('<H', data, offset)[0]


def _extent(start, size, end, label):
    _need(0 <= start <= end and 0 <= size <= end - start, label + ' exceeds source extent')


def _identity(data):
    return {'size': len(data), 'sha256': sha256(data).hexdigest()}


def _read(path):
    from .media import _snapshot
    return _snapshot(path, MAX_SOURCE)


def _mz(data):
    from .dos import load_mz
    # Reuse the canonical validator, including relocation/secondary-header checks.
    return load_mz(data, load_segment=0x10).metadata['dos']


def inspect_bytes(data: bytes) -> dict:
    """Inventory one recognized embedded v2 layout; reject unknown/ambiguous tables.

    The last paragraph may extend up to 15 bytes beyond EOF. Those bytes are
    reported as UNBACKED, never silently filled or admitted to disassembly.
    Source declarations, static hypotheses and actual runtime state stay separate.
    """
    _need(isinstance(data, bytes) and len(data) <= MAX_SOURCE, 'Expected bounded immutable source bytes')
    mz = _mz(data)
    marker = data.find(b'RTLink')
    _need(marker >= 0, 'RTLink signature absent; an appended MZ tail alone is not RTLink')
    header, resident_end = mz['header_size'], mz['declared_file_size']
    candidates = set()
    for relocation in mz['relocations']:
        if relocation['offset'] != 0:
            continue
        start = relocation['file_offset'] + 48
        if (start + 64 <= resident_end and _word(data, start + 14) == 2
                and _word(data, start + 46) == 3):
            candidates.add((start, relocation['segment']))
    _need(len(candidates) == 1,
          'RTLink v2 table missing or ambiguous; external-OVL/RTLINKST and other variants are unsupported')
    table, table_segment = next(iter(candidates))
    records = []
    relocation_total = 0
    for ordinal in range(MAX_OVERLAYS + 1):
        offset = table + ordinal * 32
        _extent(offset, 32, resident_end, 'RTLink table record')
        record = data[offset:offset + 32]
        if record == bytes(32):
            break
        _need(ordinal < MAX_OVERLAYS, 'RTLink overlay-count budget exceeded')
        bank_id = ordinal + 2
        _need(_word(record, 14) == bank_id, 'Nonsequential RTLink overlay ID or missing zero terminator')
        bank_header = struct.unpack_from('<I', record, 8)[0]
        _need(bank_header >= resident_end and bank_header % 16 == 0,
              'RTLink overlay header must be paragraph-aligned outside the resident image')
        _extent(bank_header, 16, len(data), 'RTLink overlay header')
        total_paras, header_paras, tag, relocation_start, count, extra, r1, r2 = struct.unpack_from('<8H', data, bank_header)
        _need(0 < header_paras < total_paras, 'Invalid RTLink header/total paragraph count')
        _need(relocation_start == 0, 'Unsupported RTLink relocation-start profile')
        header_size = header_paras * 16
        code_offset = bank_header + header_size
        declared_size = (total_paras - header_paras) * 16
        declared_end = bank_header + total_paras * 16
        _extent(bank_header, header_size, len(data), 'RTLink relocation header')
        _need(16 + count * 4 <= header_size, 'RTLink relocation directory crosses payload')
        shortfall = max(0, declared_end - len(data))
        _need(shortfall < 16, 'Truncated RTLink payload beyond final paragraph')
        size = declared_size - shortfall
        _need(size > 0, 'Empty RTLink payload')
        sites = []
        for index in range(count):
            at = bank_header + 16 + index * 4
            off, seg = struct.unpack_from('<HH', data, at)
            relative = seg * 16 + off
            _extent(relative, 2, size, 'RTLink relocation word')
            sites.append({'record_offset': at, 'segment': seg, 'offset': off,
                          'payload_offset': relative, 'file_offset': code_offset + relative,
                          'stored_word': _word(data, code_offset + relative)})
        records.append({'id': bank_id, 'ordinal': ordinal, 'table_record_offset': offset,
                        'descriptor_load_paragraph': _word(record, 0),
                        'header_offset': bank_header, 'header_size': header_size,
                        'header_tag': tag, 'opaque_header_words': [extra, r1, r2],
                        'file_offset': code_offset, 'size': size,
                        'declared_payload_size': declared_size, 'unbacked_declared_bytes': shortfall,
                        'sha256': sha256(data[code_offset:code_offset + size]).hexdigest(),
                        'relocations': sites})
        relocation_total += count
        _need(relocation_total <= MAX_RELOCATIONS,
              'RTLink relocation-count budget exceeded')
    _need(len(records) >= 2, 'RTLink v2 requires at least two sequential records')
    # File order need not equal the descriptor's logical bank order.
    ordered = sorted(records, key=lambda row: row['header_offset'])
    previous = resident_end
    residual = []
    for row in ordered:
        start = row['header_offset']
        _need(start >= previous, 'Overlapping RTLink payload/header extents')
        if start > previous:
            residual.append({'offset': previous, 'size': start - previous,
                             'sha256': sha256(data[previous:start]).hexdigest()})
        previous = row['file_offset'] + row['size']
    if previous < len(data):
        residual.append({'offset': previous, 'size': len(data) - previous,
                         'sha256': sha256(data[previous:]).hexdigest()})
    # A banked analysis view gives every bank an independent stable range. It
    # deliberately does NOT change segment operands, relocations or call thunks.
    mappings = [{'member': 'resident', 'file_offset': header, 'size': resident_end - header,
                 'flat_offset': 0, 'sha256': sha256(data[header:resident_end]).hexdigest()}]
    cursor = resident_end - header
    alignment = []
    for row in records:
        aligned = (cursor + 15) & ~15
        if aligned != cursor:
            alignment.append({'flat_offset': cursor, 'size': aligned - cursor, 'source': None})
        cursor = aligned
        row['flat_offset'] = cursor
        mappings.append({'member': f"overlay-{row['id']:04d}", 'file_offset': row['file_offset'],
                         'size': row['size'], 'flat_offset': cursor, 'sha256': row['sha256']})
        cursor += row['size']
    _need(cursor <= MAX_SOURCE, 'RTLink flat-view byte budget exceeded')
    by_id = {row['id']: row for row in records}
    reloc_sites = {r['file_offset'] for r in mz['relocations']}
    thunks = []
    # Recognize only the relocation-backed, fixed-width dynamic thunk form.
    # Other forms remain unresolved, rather than using a string to guess code.
    for at in sorted(site - 3 for site in reloc_sites):
        if not header <= at <= resident_end - 14:
            continue
        if data[at] != 0x9a or data[at + 5] != 0xea or _word(data, at + 8) != 0:
            continue
        alias, paragraph_delta = struct.unpack_from('<HH', data, at + 10)
        bank = by_id.get(alias + 1)  # v2 alias is 1-based descriptor ordinal.
        target = paragraph_delta * 16 + _word(data, at + 6)
        if bank is not None and target < bank['size']:
            thunks.append({'file_offset': at, 'alias': alias, 'overlay_id': bank['id'],
                           'overlay_offset': target, 'target_file_offset': bank['file_offset'] + target,
                           'target_flat_offset': bank['flat_offset'] + target,
                           'status': 'structural_candidate_not_runtime_verified'})
    return {'format': 'fdisbull-rtlink-1', 'profile': PROFILE, 'source': _identity(data),
            'input_executed': False, 'qualification': 'static-structure-only',
            'signature_offset': marker, 'mz_header_size': header,
            'mz_declared_file_size': resident_end, 'resident_relocations': mz['relocations'],
            'resident_analysis_load_segment': 0x10,
            'all_declared_payload_bytes_backed': not any(r['unbacked_declared_bytes'] for r in records),
            'flat_layout_kind': 'banked-unrelocated-analysis',
            'table_offset': table, 'table_segment': table_segment,
            'table_size_with_terminator': (len(records) + 1) * 32,
            'overlay_count': len(records), 'overlays': records,
            'relocation_count': sum(len(row['relocations']) for row in records),
            'candidate_thunks': thunks, 'opaque_file_ranges': residual,
            'mappings': mappings, 'flat_size': cursor, 'synthetic_zero_alignment': alignment,
            'unbacked_declared_bytes': sum(row['unbacked_declared_bytes'] for row in records),
            'output_runnable': False, 'relocations_applied': False,
            'unknowns': ['Only embedded v2 is implemented; external OVL/RTLINKST variants refuse.',
                         'Bank mappings are analytical, not observed runtime addresses or generations.',
                         'Not all thunk forms or cross-bank references are resolved.',
                         'Unbacked paragraph bytes are omitted, not invented.',
                         'Static validation does not prove that every payload byte is code.']}


def inspect_rtlink(path) -> dict:
    return inspect_bytes(_read(path))


def _member_bytes(data: bytes, report: dict, member: str) -> bytes:
    _need(report.get('source') == _identity(data), 'RTLink report belongs to different source bytes')
    if member == 'flat':
        flat = bytearray(report['flat_size'])
        for item in report['mappings']:
            start, size = item['file_offset'], item['size']
            flat[item['flat_offset']:item['flat_offset'] + size] = data[start:start + size]
        return bytes(flat)
    match = [item for item in report['mappings'] if item['member'] == member]
    _need(len(match) == 1, 'Unknown RTLink member; inspect first')
    item = match[0]
    return data[item['file_offset']:item['file_offset'] + item['size']]


def export_rtlink(path, output) -> dict:
    """Write one private non-runnable banked view and full source-range map."""
    from .output_artifacts import _private_directory
    data = _read(path)
    report = inspect_bytes(data)
    flat = _member_bytes(data, report, 'flat')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    _private_directory(destination.parent)
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        for name, payload in [('analysis-flat.bin', flat),
                              ('rtlink-map.json', (json.dumps(report, indent=2) + '\n').encode())]:
            with (destination / name).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(payload)
        _need(_read(path) == data, 'RTLink source changed during export')
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'format': 'fdisbull-rtlink-export-1', 'source': report['source'],
            'output': str(destination), 'flat': _identity(flat), 'overlay_count': report['overlay_count'],
            'map': 'rtlink-map.json', 'runnable': False, 'relocations_applied': False,
            'unbacked_declared_bytes': report['unbacked_declared_bytes']}


def disassemble_rtlink(path, *, overlay: int, offset: int = 0, count: int = 32) -> dict:
    """Decode original bank bytes through the existing x86 processor, never execute."""
    from .decoder import decode
    _need(type(overlay) is int, 'overlay must be an integer ID')
    _need(type(count) is int and 1 <= count <= 256, 'count must be 1..256')
    data = _read(path)
    report = inspect_bytes(data)
    rows = [r for r in report['overlays'] if r['id'] == overlay]
    _need(len(rows) == 1, 'Unknown overlay ID')
    bank = rows[0]
    _need(type(offset) is int and 0 <= offset < bank['size'], 'offset must lie in backed overlay bytes')
    start, at, instructions = offset, offset, []
    while len(instructions) < count and at < bank['size']:
        file_at = bank['file_offset'] + at
        # IP is bank-relative; a real CS binding and relocation state are unknown.
        item = decode(data[file_at:min(file_at + 15, bank['file_offset'] + bank['size'])], at, 'x86', 16)
        if item is None:
            break
        instructions.append({**item, 'file_offset': file_at, 'overlay_id': overlay,
                             'overlay_offset': at, 'flat_offset': bank['flat_offset'] + at})
        at += item['size']
    return {'format': 'fdisbull-rtlink-disassembly-1', 'source': report['source'],
            'overlay': overlay, 'offset': start, 'instructions': instructions,
            'address_space': 'unrelocated-bank-relative; not a DOS CS:IP or runtime address',
            'reachability_verified': False, 'input_executed': False}
