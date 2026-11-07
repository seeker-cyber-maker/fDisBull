"""Bounded, guest-reported QEMM observations; no host-side QPI execution.

The authored DOS helper uses only the documented read-only functions. Parsing
its output establishes what the bytes report, not when or where they were made.
Machine sessions add observed stop/run provenance separately.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import struct

REPORT_SIZE = 1120
PAGE_COUNT = 272
_STATUS = {0: 'complete', 1: 'device-open-failed', 2: 'ioctl-failed',
           3: 'ioctl-length-mismatch', 4: 'version-call-failed',
           5: 'status-call-failed', 6: 'info-call-failed', 7: 'pte-call-failed',
           8: 'null-entry-point'}
_FLAGS = {0: 31, 1: 0, 2: 0, 3: 0, 4: 1, 5: 3, 6: 7, 7: 15, 8: 0}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _bcd(word):
    digits = [(word >> shift) & 15 for shift in (12, 8, 4, 0)]
    if any(digit > 9 for digit in digits):
        raise ValueError('QPI version is not packed BCD')
    return f'{digits[0] * 10 + digits[1]}.{digits[2]}{digits[3]}'


def _region(page):
    return 'conventional-address-range' if page < 0xa0 else (
        'upper-address-range' if page < 0x100 else 'above-one-megabyte')


def parse_qpi_report(data, *, include_pages=False):
    """Parse an exact FDQPI001 record, retaining raw PTEs and partial failures."""
    if not isinstance(data, bytes) or len(data) != REPORT_SIZE:
        raise ValueError(f'QPI report must contain exactly {REPORT_SIZE} bytes')
    if type(include_pages) is not bool:
        raise ValueError('include_pages must be boolean')
    if data[:8] != b'FDQPI001' or struct.unpack_from('<H', data, 8)[0] != REPORT_SIZE:
        raise ValueError('Unsupported QPI report signature or size')
    status, ax, bx, offset, segment = struct.unpack_from('<5H', data, 10)
    enabled, stealth = data[20:22]
    count, flags = struct.unpack_from('<2H', data, 22)
    if status not in _STATUS or flags != _FLAGS[status] or any(data[29:32]):
        raise ValueError('Incomplete or inconsistent QPI report status/flags')
    if count > PAGE_COUNT or (status == 0 and count != PAGE_COUNT) or (status != 0 and count == PAGE_COUNT):
        raise ValueError('Inconsistent QPI page count')
    if status not in (0, 7) and count:
        raise ValueError('QPI report has pages before a page-table query')
    if flags & 1 and (offset | segment) == 0:
        raise ValueError('QPI entry point is null')
    version = None
    if flags & 2:
        if ax != bx:
            raise ValueError('QPI version registers disagree')
        version = _bcd(bx)
        if (bx >> 8) < 6:
            raise ValueError('This QPI acquisition protocol requires QEMM 6.00 or later')
    if flags & 4 and enabled not in (0, 1, 2, 3):
        raise ValueError('Invalid QPI enabled-state value')
    pages, ranges, frames = [], [], {}
    for page in range(count):
        raw = struct.unpack_from('<I', data, 32 + page * 4)[0]
        present = bool(raw & 1)
        physical = (raw & 0xfffff000) if present else None
        row = dict(logical_page=page, linear_start=page << 12,
                   raw_pte=f'0x{raw:08x}', present=present,
                   physical_start=physical, pte_writable=bool(raw & 2),
                   pte_user=bool(raw & 4), accessed=bool(raw & 32),
                   dirty=bool(raw & 64), software_bits=(raw >> 9) & 7)
        pages.append(row)
        if present:
            frames.setdefault(physical, []).append(page << 12)
        region = _region(page)
        last = ranges[-1] if ranges else None
        contiguous = (last and last['region'] == region and last['raw_flags'] == raw & 0xfff
                      and (physical is None if last['physical_start'] is None
                           else physical == last['physical_start'] + last['page_count'] * 4096))
        if contiguous:
            last['page_count'] += 1
            last['linear_end_exclusive'] += 4096
        else:
            ranges.append(dict(linear_start=page << 12, linear_end_exclusive=(page + 1) << 12,
                               physical_start=physical, page_count=1, raw_flags=raw & 0xfff,
                               present=present, region=region))
    result = dict(
        format='fdisbull-qpi-report-1', sha256=_sha(data), length=len(data),
        probe_status=dict(code=status, name=_STATUS[status], complete=status == 0),
        qemm=dict(evidence='guest-reported QPI; producer and freshness not independently verified',
                  entry={'segment': segment, 'offset': offset} if flags & 1 else None,
                  version=version, raw_version_ax=f'0x{ax:04x}', raw_version_bx=f'0x{bx:04x}',
                  state_raw=enabled if flags & 4 else None,
                  active=enabled in (0, 1) if flags & 4 else None,
                  auto_mode=enabled in (1, 3) if flags & 4 else None,
                  stealth_raw=stealth if flags & 8 else None,
                  stealth_mode={0: 'none', ord('M'): 'M', ord('F'): 'F'}.get(stealth, 'unknown')
                               if flags & 8 else None,
                  suspend_interrupt=data[26] if flags & 8 else None,
                  disk_buffer_kib=data[27] if flags & 8 and bx >= 0x0700 else None,
                  disk_buffer_flags_raw=data[28] if flags & 8 and bx >= 0x0700 else None,
                  raw_info=dict(cl=stealth, ch=data[26], dl=data[27], bh=data[28]) if flags & 8 else None),
        mappings=dict(page_size=4096, captured_pages=count, maximum_pages=PAGE_COUNT,
                      complete=count == PAGE_COUNT, ranges=ranges,
                      aliases=[dict(physical_start=physical, linear_starts=linear)
                               for physical, linear in sorted(frames.items()) if len(linear) > 1]),
        native_execution_validation='not_established_by_report',
        limitations=[
            'QPI describes only the first 1088 KiB of logical memory.',
            'The page loop is sequential, not an atomic memory-manager snapshot.',
            'Raw PTE permissions are not a complete PDE/PTE or access-control evaluation.',
            'No manager installation, page-table modification or interrupt/port hooking is performed.',
        ])
    if include_pages:
        result['mappings']['pages'] = pages
    return result


def probe_bytes(*, mode='breakpoint'):
    """Return the packaged, reproducible authored helper without an assembler."""
    if mode not in ('breakpoint', 'file'):
        raise ValueError('QPI probe mode must be breakpoint or file')
    root = files('fdisbull').joinpath('data')
    asset = json.loads(root.joinpath('qpi-probe.json').read_text(encoding='utf-8'))
    source = root.joinpath('FdisbullQpiProbe.txt').read_bytes()
    program = bytes.fromhex(asset['program_hex'])
    if (asset['format'] != 'fdisbull-qpi-probe-1'
            or _sha(source) != asset['source_sha256']
            or _sha(program) != asset['program_sha256']
            or len(program) > 0xff00
            or asset['report_length'] != REPORT_SIZE):
        raise ValueError('Packaged QPI helper failed its source/byte identity checks')
    mode_offset = asset['mode_file_offset']
    report_offset = asset['report_com_offset'] - 0x100
    if (type(mode_offset) is not int or not 0 <= mode_offset < report_offset
            or program[mode_offset] != 0 or report_offset + REPORT_SIZE != len(program)
            or program[report_offset:report_offset + 8] != b'FDQPI001'):
        raise ValueError('Packaged QPI helper has inconsistent offsets')
    if mode == 'file':
        program = program[:mode_offset] + b'\x01' + program[mode_offset + 1:]
    return program, {key: value for key, value in asset.items() if key != 'program_hex'}


def write_qpi_probe(output, *, mode='breakpoint'):
    """Export a helper; refuse to replace a different caller file."""
    program, asset = probe_bytes(mode=mode)
    path = Path(output).expanduser().resolve()
    if path.exists():
        if not path.is_file() or path.stat().st_size != len(program) or path.read_bytes() != program:
            raise ValueError('QPI helper output exists with different bytes')
        written = False
    else:
        with path.open('xb') as stream:
            stream.write(program)
        written = True
    return dict(format='fdisbull-qpi-probe-export-1', output=str(path), written=written,
                sha256=_sha(program), length=len(program), source_sha256=asset['source_sha256'],
                mode=mode, minimum_cpu='386', acquisition='DOS QEMM386$ IOCTL; QEMM 6.00 or later',
                qpi_calls=['GetVersion', 'GetStatus', 'GetInfo', 'GetPTE'],
                report=dict(length=REPORT_SIZE, com_offset=asset['report_com_offset'],
                            location='ES:DI with CX=1120 in the stable report-ready loop' if mode == 'breakpoint' else 'FDQPI.BIN in the current DOS directory',
                            ready_com_offset=asset['ready_com_offset'],
                            release_com_offset=asset['release_com_offset'],
                            release='Set the helper release byte from 0 to 1, then resume to exit to DOS'),
                execution='not_run',
                scope='Read-only QPI calls; file mode creates/replaces only the FDQPI.BIN output in the guest.')
