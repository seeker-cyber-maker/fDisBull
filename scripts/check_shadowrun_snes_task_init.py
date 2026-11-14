#!/usr/bin/env python3
"""Compare guarded task construction against a private original write trace.

Starts task state from the source reset. Script IDs and argument words are read
from original instruction events as component inputs, not derived scene state.
No actor/scene initialization or autonomous trajectory is established.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.shadowrun_snes_field import ROM_SHA256
from fdisbull.shadowrun_snes_task_init import SOURCE, VM_SOURCE, task_init_machine

CORE = '6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_byte(state, address):
    if 0x3ee <= address < 0x3f2:
        return state['task_heap_first_header'][address - 0x3ee]
    if 0x3f2 <= address < 0xbbe:
        return state['task_heap'][address - 0x3f2]
    for start, end, name in ((0x26e, 0x2ce, 'task_frame'), (0x2ce, 0x32e, 'task_callback'),
                              (0x32e, 0x38e, 'task_next'), (0x38e, 0x3ee, 'task_link'),
                              (0xbbe, 0xc1e, 'task_wait')):
        if start <= address < end:
            offset = address - start
            return (state[name][offset // 2] >> (8 * (offset % 2))) & 0xff
    for start, name in ((0x268, 'task_list_head'), (0x26a, 'task_list_free')):
        if start <= address < start + 2:
            return (state[name] >> (8 * (address - start))) & 0xff
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--trace-dir', type=Path, required=True)
    args = p.parse_args()
    source_hashes = {str(p): sha(p.read_bytes()) for p in (SOURCE, VM_SOURCE, Path(__file__))}
    rom = args.rom.read_bytes()
    if sha(rom) != ROM_SHA256:
        raise ValueError('wrong SNES source')
    receipt_bytes = (args.trace_dir / 'receipt.json').read_bytes()
    receipt = json.loads(receipt_bytes)
    trace_bytes = (args.trace_dir / 'snes_trace.json').read_bytes()
    if (receipt['rom_sha256'] != ROM_SHA256 or receipt['core_sha256'] != CORE or
            receipt['patches'] or receipt['snes_trace_sha256'] != sha(trace_bytes)):
        raise ValueError('unexpected source, core, patches or trace hash')
    trace = json.loads(trace_bytes)
    rows = [row for row in trace['frames'] if row['frame'] == 1015]
    if len(rows) != 1 or rows[0]['dropped']:
        raise ValueError('missing or lossy construction interval')
    groups, current = [], None
    for event in rows[0]['events']:
        pc, address = event['pc'], event['address'] & 0xffff
        if pc == 0x80c29c and address == 0x73:
            if current is not None:
                raise ValueError('overlapping construction events')
            current = {'id': event['x'], 'args': [0] * 256, 'writes': {}}
        if current is None:
            continue
        if pc == 0x80c2e3:
            y, value = event['y'], event['a']
            if y < 2 or y > 256 or y & 1:
                raise ValueError('unsupported source argument write')
            current['args'][y - 2:y] = [value & 0xff, value >> 8]
        if 0x80c212 <= pc <= 0x80c335:
            if 0x268 <= address < 0x26c or 0x26e <= address < 0xc1e:
                current['writes'][address] = event['value']
        if pc == 0x80c332 and address == 0x269:
            groups.append(current)
            current = None
    if current is not None or len(groups) != 20:
        raise ValueError('incomplete original task construction sequence')
    machine = task_init_machine(rom)
    machine.call('shadowrun_snes_task_reset', 0)
    count = 0
    for index, group in enumerate(groups):
        machine.set_state({'task_init_script': group['id'], 'task_init_args': group['args']})
        machine.call('shadowrun_snes_task_create', 0)
        state = machine.snapshot()
        if not state['task_init_supported']:
            raise ValueError(f'task construction {index} refused')
        for address, expected in group['writes'].items():
            actual = source_byte(state, address)
            if actual is None:
                continue
            count += 1
            if actual != expected:
                raise ValueError(f'task construction {index} differs at {address:#x}')
    if count != 698:
        raise ValueError('unexpected compared-write coverage')
    if any(sha(Path(path).read_bytes()) != value for path, value in source_hashes.items()):
        raise ValueError('task initialization checker or source changed')
    print(json.dumps({'status': 'passed', 'source_sha256': ROM_SHA256,
                      'source_receipt_sha256': sha(receipt_bytes),
                      'trace_sha256': sha(trace_bytes), 'constructs': len(groups),
                      'compared_write_bytes': count, 'source_hashes': source_hashes,
                      'scope': 'reset-once task creation; script IDs and arguments supplied from trace; '
                               'scene and actor producers, unobserved fields and later passes excluded'}, sort_keys=True))


if __name__ == '__main__':
    main()
