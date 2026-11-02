"""Bounded build/listing witnesses for source-to-native correspondence.

The EXEPACK view is resident-only, for static analysis. Overlay payloads remain
identified in the original file; this is not a runnable whole-game conversion.
"""
from __future__ import annotations

import hashlib
import re
import struct


MAX_IMAGE = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack_exepack(data):
    """Decode the 16-byte RB header profile and retain literal/fill provenance."""
    if not isinstance(data, bytes) or not 64 <= len(data) <= 64 * MAX_IMAGE:
        raise ValueError('EXEPACK source requires 64 bytes..64 MiB')
    h = list(struct.unpack_from('<14H', data))
    magic, last, pages, count, paragraphs = h[:5]
    declared = (pages - 1) * 512 + last if last else pages * 512
    header, ip, cs = paragraphs * 16, h[10], h[11]
    base = header + cs * 16
    if (magic != 0x5a4d or count != 0 or ip != 16 or not 28 <= header < base
            or last > 511 or not base + ip <= declared <= len(data)
            or data[base + ip - 2:base + ip] != b'RB'):
        raise ValueError('unsupported or malformed EXEPACK MZ/header profile')
    fields = struct.unpack_from('<' + 'H' * (ip // 2), data, base)
    real_ip, real_cs, _, exepack_size, real_sp, real_ss, destination = fields[:7]
    maximum = destination * 16
    if not 0 < maximum <= MAX_IMAGE or not base + ip < base + exepack_size <= declared:
        raise ValueError('invalid EXEPACK destination/stub bounds')
    packed, pointer = data[header:base], base - header - 1
    while pointer >= 0 and packed[pointer] == 0xff:
        pointer -= 1
    reverse, pending, final = bytearray(), [], False
    while pointer >= 0:
        opcode = packed[pointer]
        pointer -= 1
        if pointer < 1:
            raise ValueError('truncated EXEPACK count')
        amount = int.from_bytes(packed[pointer - 1:pointer + 1], 'little')
        pointer -= 2
        if not amount or len(reverse) + amount > maximum:
            raise ValueError('invalid EXEPACK run length')
        begin = len(reverse)
        if opcode & 0xfe == 0xb0:
            if pointer < 0:
                raise ValueError('truncated EXEPACK fill')
            reverse.extend(bytes([packed[pointer]]) * amount)
            pending.append(dict(reverse_start=begin, size=amount, kind='fill',
                                packed_offset=header + pointer, value=packed[pointer]))
            pointer -= 1
        elif opcode & 0xfe == 0xb2:
            if pointer + 1 < amount:
                raise ValueError('truncated EXEPACK literal')
            start = pointer - amount + 1
            reverse.extend(packed[start:pointer + 1][::-1])
            pending.append(dict(reverse_start=begin, size=amount, kind='literal', packed_offset=header + start))
            pointer -= amount
        else:
            raise ValueError('unsupported EXEPACK opcode')
        if opcode & 1:
            final = True
            break
    if not final or len(reverse) + pointer + 1 > maximum:
        raise ValueError('EXEPACK has no bounded final record')
    if pointer >= 0:
        pending.append(dict(reverse_start=len(reverse), size=pointer + 1, kind='literal', packed_offset=header))
        reverse.extend(packed[:pointer + 1][::-1])
    module = bytes(reverse[::-1])
    runs = []
    for run in reversed(pending):
        run = dict(run)
        run['module_offset'] = len(module) - run.pop('reverse_start') - run['size']
        runs.append(run)
    marker = b'Packed file is corrupt'
    stub = data[base:base + exepack_size]
    positions = [m.start() for m in re.finditer(re.escape(marker), stub)]
    if len(positions) != 1:
        raise ValueError('EXEPACK relocation marker is missing or ambiguous')
    position = base + positions[0] + len(marker)
    relocations = []
    for group in range(16):
        if position + 2 > base + exepack_size:
            raise ValueError('truncated EXEPACK relocation group')
        amount = struct.unpack_from('<H', data, position)[0]
        position += 2
        if position + amount * 2 > base + exepack_size:
            raise ValueError('truncated EXEPACK relocations')
        for _ in range(amount):
            offset = struct.unpack_from('<H', data, position)[0]
            position += 2
            segment = group * 0x1000
            if segment * 16 + offset + 2 > len(module):
                raise ValueError('EXEPACK relocation exceeds decoded module')
            relocations.append((offset, segment))
    if position != base + exepack_size:
        raise ValueError('unexplained EXEPACK relocation tail')
    reloc_data = b''.join(struct.pack('<HH', *r) for r in relocations)
    header_size = (28 + len(reloc_data) + 15) & ~15
    total = header_size + len(module)
    out = [0x5a4d, total % 512, (total + 511) // 512, len(relocations), header_size // 16,
           h[5], h[6], real_ss, real_sp, 0, real_ip, real_cs, 28, 0]
    image = struct.pack('<14H', *out) + reloc_data + bytes(header_size - 28 - len(reloc_data)) + module
    return dict(image=image, module=module, relocations=relocations, runs=runs,
                source_sha256=sha(data), image_sha256=sha(image), module_sha256=sha(module),
                original_overlay_offset=declared, original_overlay_size=len(data) - declared,
                original_overlay_sha256=sha(data[declared:]), resident_only=True, runnable_game=False)


def packed_provenance(view, start, size):
    if type(start) is not int or type(size) is not int or start < 0 or size < 1 or start + size > len(view['module']):
        raise ValueError('native span exceeds resident module')
    spans = []
    for run in view['runs']:
        begin, end = max(start, run['module_offset']), min(start + size, run['module_offset'] + run['size'])
        if begin < end:
            offset = run['packed_offset'] + (begin - run['module_offset'] if run['kind'] == 'literal' else 0)
            spans.append(dict(module_offset=begin, size=end - begin, kind=run['kind'], packed_offset=offset))
    if sum(x['size'] for x in spans) != size:
        raise ValueError('incomplete packed provenance')
    return spans


def parse_link_map(text):
    segments, symbols = {}, {}
    for line in text.splitlines():
        match = re.fullmatch(r'\s*([0-9A-F]+)H\s+([0-9A-F]+)H\s+([0-9A-F]+)H\s+(\S+)\s+CODE\s*', line)
        if match:
            start, stop, length = (int(match[i], 16) for i in (1, 2, 3))
            if ((stop + 1 - start != length if length else stop != start) or match[4] in segments):
                raise ValueError('inconsistent or ambiguous linker code segment')
            segments[match[4]] = dict(start=start, end=start + length)
        match = re.fullmatch(r'\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\s+Res\s+(\S+)\s*', line)
        if match:
            value = dict(segment=int(match[1], 16), offset=int(match[2], 16))
            previous = symbols.setdefault(match[3], value)
            if previous != value:
                raise ValueError('ambiguous resident linker symbol')
    return dict(segments=segments, symbols=symbols)


def parse_cod(text):
    """Read emitted function ranges/line sites; operands may contain linker placeholders."""
    result, current, line_number = {}, None, None
    segment = None
    for line in text.splitlines():
        match = re.fullmatch(r"(\S+)\s+SEGMENT\s+WORD PUBLIC 'CODE'", line.strip())
        if match:
            segment = match[1]
        match = re.fullmatch(r'; Line (\d+)', line)
        if match:
            line_number = int(match[1])
        match = re.fullmatch(r'(\S+)\s+PROC\s+(FAR|NEAR)', line.strip())
        if match:
            if current is not None or match[1] in result:
                raise ValueError('nested or ambiguous compiler procedure')
            current = dict(symbol=match[1], segment_name=segment, records=[], abi_distance=match[2].lower())
        match = re.match(r'\s*\*\*\*\s+([0-9a-fA-F]+)\s+((?:[0-9a-fA-F]{2}(?:\s+|$))+)', line)
        if current is not None and match:
            data = bytes.fromhex(match[2])
            assembly = line[match.end():].strip().split()
            current['records'].append(dict(offset=int(match[1], 16), size=len(data), source_line=line_number,
                                           mnemonic=assembly[0].lower() if assembly else None))
        match = re.fullmatch(r'(\S+)\s+ENDP', line.strip())
        if match:
            if current is None or current['symbol'] != match[1] or not current['records']:
                raise ValueError('unmatched or empty compiler procedure')
            records = current['records']
            current['start'] = min(r['offset'] for r in records)
            current['end'] = max(r['offset'] + r['size'] for r in records)
            result[current['symbol']] = current
            current = None
    if current is not None:
        raise ValueError('unterminated compiler procedure')
    return result


def map_procedure(link_map, cod, view, symbol, source_line=None):
    if symbol not in link_map['symbols'] or symbol not in cod:
        raise ValueError('compiler/linker symbol is missing')
    public, procedure = link_map['symbols'][symbol], cod[symbol]
    absolute = public['segment'] * 16 + public['offset']
    contribution = link_map['segments'].get(procedure['segment_name'])
    if contribution is None or absolute - procedure['start'] != contribution['start']:
        raise ValueError('compiler/linker contribution bases disagree')
    if source_line is None:
        pieces = [dict(offset=procedure['start'], size=procedure['end'] - procedure['start'])]
    else:
        pieces = []
        for record in procedure['records']:
            if record['source_line'] != source_line:
                continue
            if pieces and pieces[-1]['offset'] + pieces[-1]['size'] == record['offset']:
                pieces[-1]['size'] += record['size']
            else:
                pieces.append(dict(offset=record['offset'], size=record['size']))
        if not pieces:
            raise ValueError('compiler listing has no emitted records for the selected line')
    spans = []
    for piece in pieces:
        offset = absolute + piece['offset'] - procedure['start']
        size = piece['size']
        if offset < contribution['start'] or offset + size > contribution['end']:
            raise ValueError('emitted span exceeds linker contribution')
        raw = view['module'][offset:offset + size]
        if len(raw) != size:
            raise ValueError('emitted span exceeds resident image')
        relative_ip = public['offset'] + piece['offset'] - procedure['start']
        if relative_ip + size > 65536:
            raise ValueError('native span crosses real-mode CS window')
        spans.append(dict(module_offset=offset, segment=public['segment'], offset=relative_ip,
                          size=size, sha256=sha(raw), packed_spans=packed_provenance(view, offset, size)))
    return dict(symbol=symbol, segment_name=procedure['segment_name'],
                object_start=procedure['start'], object_end=procedure['end'], source_line=source_line,
                abi_distance=procedure['abi_distance'], spans=spans,
                scope='Verified-build compiler/linker correspondence in an unpacked resident view; no runtime or semantic equivalence.')


def static_call_sites(link_map, cod, view, caller, callees):
    """Use native instruction facts for selected direct calls; not call coverage."""
    import iced_x86 as ix
    procedure, public = cod[caller], link_map['symbols'][caller]
    contribution = public['segment'] * 16 + public['offset'] - procedure['start']
    sites = []
    for record in procedure['records']:
        if record['mnemonic'] != 'call':
            continue
        start = contribution + record['offset']
        data = view['module'][start:start + record['size']]
        ip = start - public['segment'] * 16
        for instruction in ix.Decoder(16, data, ip=ip):
            if instruction.is_invalid or instruction.flow_control != ix.FlowControl.CALL:
                continue
            if instruction.op0_kind == ix.OpKind.FAR_BRANCH16:
                destination = instruction.far_branch_selector, instruction.far_branch16
            elif instruction.op0_kind == ix.OpKind.NEAR_BRANCH16:
                destination = public['segment'], instruction.near_branch16
            else:
                continue
            for callee in callees:
                expected = link_map['symbols'][callee]
                if destination != (expected['segment'], expected['offset']):
                    continue
                offset = public['segment'] * 16 + instruction.ip16
                sites.append(dict(caller=caller, callee=callee, source_line=record['source_line'],
                                  segment=public['segment'], offset=instruction.ip16,
                                  module_offset=offset, size=instruction.len,
                                  packed_spans=packed_provenance(view, offset, instruction.len),
                                  basis='native direct-call operand and checked linker symbol',
                                  runtime_observed=False))
    return sites
