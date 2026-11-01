#!/usr/bin/env python3
"""Compare a bounded captured Genesis route to an NES publication trace.

Inputs and the JSON result belong outside the checkout. This checks only the
published fields at matching, caller-selected frames; it is not a full-scene
or unassisted-play qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path


FIELDS = (
    ('player_x', 4, 0x0100), ('player_y', 6, 0x0104),
    ('heading', 8, 0x012e), ('pad_sample', 10, 0xdd22),
    ('direction', 12, 0xdd04), ('camera_x', 14, 0xddc6),
    ('camera_y', 16, 0xddc8), ('scroll_ax', 18, 0xdd08),
    ('scroll_ay', 20, 0xdd0a),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


NES_CORE_SHA = '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
GENESIS_CORE_SHA = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
SOURCE_ROM_SHA = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'


def checked_receipt(receipt, *, system, core_sha, rom_sha):
    if (not isinstance(receipt, dict) or receipt.get('system') != system or
            receipt.get('core_sha256') != core_sha or receipt.get('rom_sha256') != rom_sha or
            receipt.get('patches') != [] or receipt.get('patch_trace') != [] or
            receipt.get('memory_injection_mode') != 'no memory patches' or
            type(receipt.get('frames')) is not int or receipt['frames'] <= 0):
        raise ValueError('Receipt identity, frame count, or no-patch contract differs')


def scheduled_mask(receipt, frame):
    inputs=receipt.get('inputs');mapping=receipt.get('input_map')
    if not isinstance(inputs,list) or not isinstance(mapping,dict):
        raise ValueError('Receipt lacks explicit input schedule')
    mask=0
    for entry in inputs:
        if (not isinstance(entry,dict) or set(entry)!={'start','end','buttons'} or
                type(entry['start']) is not int or type(entry['end']) is not int or
                not 0 <= entry['start'] < entry['end'] <= receipt['frames'] or
                not isinstance(entry['buttons'],list)):
            raise ValueError('Malformed receipt input schedule')
        for button in entry['buttons']:
            if not isinstance(button,str) or button.upper() not in mapping:
                raise ValueError('Unknown receipt input')
            code=mapping[button.upper()]
            if type(code) is not int or not 0 <= code < 16:raise ValueError('Invalid input map')
            if entry['start'] <= frame < entry['end']:mask |= 1 << code
    return mask


def indexed_frames(raw, receipt):
    if digest(raw) != receipt.get('ram_trace_sha256'):
        raise ValueError('Target trace differs from its receipt')
    trace=json.loads(raw)
    if not isinstance(trace,dict) or not isinstance(trace.get('frames'),list):
        raise ValueError('Malformed target trace')
    rows=trace['frames']
    if len(rows)!=receipt['frames']:
        raise ValueError('Incomplete target trace')
    frames={}
    for index,item in enumerate(rows):
        if (not isinstance(item,dict) or type(item.get('frame')) is not int or
            item['frame'] != index or item['frame'] in frames or
            type(item.get('input_mask')) is not int or not 0 <= item['input_mask'] < 65536):
            raise ValueError('Missing, duplicate, or malformed target frame')
        frames[index]=item
    return frames


def captured_file(root, capture, relative):
    records=capture.get('files')
    if not isinstance(records,dict) or not isinstance(records.get(relative),dict):
        raise ValueError('Source capture lacks required file binding: '+relative)
    record=records[relative]
    if set(record)!={'size','sha256'} or type(record['size']) is not int or not 0<=record['size']<=8*1024*1024:
        raise ValueError('Invalid source capture file identity')
    path=root/relative
    if not path.is_file() or path.stat().st_size!=record['size']:
        raise ValueError('Missing or changed source capture file: '+relative)
    raw=path.read_bytes()
    if len(raw)!=record['size'] or digest(raw)!=record['sha256']:
        raise ValueError('Changed source capture file: '+relative)
    return raw


def select_completed(frames, start, count):
    selected=[]
    last=None
    for nf in sorted(k for k in frames if k>=start):
        state=bytes.fromhex(frames[nf]['raw']['state'])
        if len(state) not in (24,26):raise ValueError('Logical comparison requires a sequenced publication')
        if state[22]&1:continue
        tick=state[23]
        if last is not None and tick==last:continue
        if last is not None and tick!=((last+1)&255):
            raise ValueError('A completed target tick was not observed')
        selected.append(nf);last=tick
        if len(selected)==count:break
    if len(selected)!=count:raise ValueError('Insufficient completed target ticks')
    return selected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ('nes-trace', 'nes-rom', 'source-rom', 'capture-dir', 'output'):
        ap.add_argument('--' + flag, required=True)
    ap.add_argument('--nes-start', required=True, type=int)
    ap.add_argument('--source-start', required=True, type=int)
    ap.add_argument('--count', required=True, type=int)
    ap.add_argument('--input-mask', required=True, type=lambda value: int(value, 0))
    ap.add_argument('--nes-receipt', help='target receipt; defaults to receipt.json beside trace')
    ap.add_argument('--logical', action='store_true',
                    help='compare successive stable completed ticks rather than equal physical frames')
    args = ap.parse_args()
    out = Path(args.output).expanduser().resolve()
    if out.exists() or any((p / '.git').exists() for p in (out.parent, *out.parents)):
        raise ValueError('Choose a new private output outside Git')
    if not (1 <= args.count <= 10000 and args.nes_start >= 0 and args.source_start >= 0
            and 0 <= args.input_mask < 65536):
        raise ValueError('Invalid bounded comparison range or input mask')
    trace_path = Path(args.nes_trace).expanduser().resolve()
    raw_trace = trace_path.read_bytes()
    target_receipt_path = Path(args.nes_receipt).expanduser().resolve() if args.nes_receipt else trace_path.with_name('receipt.json')
    target_receipt_raw = target_receipt_path.read_bytes()
    target_receipt = json.loads(target_receipt_raw)
    target_rom_sha = digest(Path(args.nes_rom).read_bytes())
    source_rom_sha = digest(Path(args.source_rom).read_bytes())
    if source_rom_sha != SOURCE_ROM_SHA:
        raise ValueError('Unexpected source cartridge identity')
    checked_receipt(target_receipt, system='nes', core_sha=NES_CORE_SHA, rom_sha=target_rom_sha)
    frames = indexed_frames(raw_trace, target_receipt)
    capture = Path(args.capture_dir).expanduser().resolve()
    if capture.name != 'native':
        raise ValueError('Source capture directory must be its native subdirectory')
    source_root = capture.parent
    capture_raw = (source_root/'capture.json').read_bytes()
    capture_receipt = json.loads(capture_raw)
    if (not isinstance(capture_receipt,dict) or capture_receipt.get('format') != 'fdisbull-private-genesis-scenes-1'
            or capture_receipt.get('assistance') != 'ordinary controller schedule; no memory patches'
            or capture_receipt.get('inputs',{}).get('rom',{}).get('sha256') != source_rom_sha
            or capture_receipt.get('inputs',{}).get('core',{}).get('sha256') != GENESIS_CORE_SHA):
        raise ValueError('Source capture provenance differs')
    source_receipt_raw = captured_file(source_root,capture_receipt,'native/receipt.json')
    source_receipt = json.loads(source_receipt_raw)
    checked_receipt(source_receipt, system='genesis', core_sha=GENESIS_CORE_SHA, rom_sha=source_rom_sha)
    if source_receipt['frames'] != capture_receipt.get('frames') or args.source_start+args.count>source_receipt['frames']:
        raise ValueError('Incomplete source capture frame range')
    mismatches, hashes = [], []
    selected=[]
    if args.logical:
        selected=select_completed(frames,args.nes_start,args.count)
    else:
        selected=list(range(args.nes_start,args.nes_start+args.count))
    for index in range(args.count):
        nf, sf = selected[index], args.source_start + index
        record = frames[nf]
        if (record['input_mask'] != scheduled_mask(target_receipt,nf)
                or scheduled_mask(source_receipt,sf) != args.input_mask):
            raise ValueError('Input schedule does not match the compared frames')
        nes = bytes.fromhex(record['raw']['state'])
        source = captured_file(source_root,capture_receipt,f'native/scene-{sf:06d}/ram.bin')
        hashes.append(digest(source))
        if len(source) != 65536 or len(nes) not in (22, 24, 26):
            raise ValueError('Unexpected source or target RAM record size')
        if len(nes)>=24 and nes[22]&1:
            raise ValueError(f'Frame {nf} sampled an incomplete target publication')
        if nes[:2] != b'SW' or nes[2:4] != b'\1\0' or record['input_mask'] != args.input_mask:
            mismatches.append({'nes_frame': nf, 'source_frame': sf,
                               'field': 'publication/input/status', 'target': nes[:4].hex(),
                               'input_mask': record['input_mask']})
        for name, target_offset, source_offset in FIELDS:
            # Genesis Plus GX exposes the 68000 work RAM as host-order words.
            expected = int.from_bytes(source[source_offset:source_offset+2], 'little')
            actual = int.from_bytes(nes[target_offset:target_offset+2], 'little')
            if expected != actual:
                mismatches.append({'nes_frame': nf, 'source_frame': sf,
                                   'field': name, 'source': expected, 'target': actual})
    report = {'format': 'fdisbull-shadowrun-opening-route-comparison-1',
              'count': args.count, 'source_start': args.source_start,
              'nes_start': args.nes_start, 'comparison': 'completed logical ticks' if args.logical else 'physical frames',
              'target_frames': selected, 'expected_input_mask': args.input_mask,
              'fields': [name for name, _, _ in FIELDS], 'mismatches': mismatches,
              'source_rom_sha256': source_rom_sha,
              'nes_rom_sha256': target_rom_sha,
              'nes_receipt_sha256': digest(target_receipt_raw),
              'source_capture_sha256': digest(capture_raw),
              'source_receipt_sha256': digest(source_receipt_raw),
              'target_patches': 0, 'source_patches': 0,
              'nes_trace_sha256': digest(raw_trace), 'source_ram_sha256': hashes,
              'limits': ['caller selects frame correspondence',
                         'target cartridge may use a preseeded initial state; runtime RAM patches are rejected',
                         'published fields only; no graphics or full-state parity']}
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'{args.count} frames, {len(mismatches)} mismatches; {out}')
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
