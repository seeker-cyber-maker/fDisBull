#!/usr/bin/env python3
"""Compare a source-seeded full task pass with a caller-selected WRAM checkpoint.

This is a task scheduler/VM component check. It does not run actor movement or
establish that a video-frame boundary is always a game-logic boundary.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.shadowrun_snes_script import tasks_from_capture


def word(data, address):
    return int.from_bytes(data[address:address + 2], 'little')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--seed', required=True, type=Path)
    parser.add_argument('--next-checkpoint', required=True, type=Path)
    args = parser.parse_args()
    seed, expected = args.seed.read_bytes(), args.next_checkpoint.read_bytes()
    if len(expected) != 131072:
        raise ValueError('expected checkpoint must be 128 KiB WRAM')
    machine = tasks_from_capture(args.rom.read_bytes(), seed)
    current, order = word(seed, 0x268), []
    while not current & 0x8000:
        if current >= 96 or current & 1 or current in order:
            raise ValueError('invalid source active task list')
        order.append(current)
        current = word(seed, 0x32e + current)
    ready, callbacks = [], []
    for task in order:
        machine.set_state({'task_index': task, 'task_list_current': task})
        machine.call('shadowrun_snes_task_check', 0)
        state = machine.snapshot()
        if not state['task_supported']:
            raise ValueError(f'unsupported wait state on task {task:#x}')
        if not state['task_ready']:
            continue
        ready.append(task)
        for _ in range(256):
            machine.call('shadowrun_snes_task_vm', 0)
            state = machine.snapshot()
            if state['task_vm_status'] == 1:
                break
            if state['task_vm_status'] == 4:
                machine.call('shadowrun_snes_task_terminate', 0)
                if not machine.snapshot()['task_supported']:
                    raise ValueError(f'unsupported termination on task {task:#x}')
                break
            if state['task_vm_status'] != 2:
                raise ValueError(f"task {task:#x}: unsupported opcode {state['task_vm_fault_op']:#x} "
                                 f"at {state['task_vm_fault_pc']:#x}, native {state['task_vm_fault_fn']:#x}")
            callbacks.append([task, state['task_vm_callback'], state['task_vm_arg0']])
            machine.call('shadowrun_snes_task_native', 0)
            if not machine.snapshot()['task_native_supported']:
                raise ValueError(f"task {task:#x}: callback {state['task_vm_callback']:#x} requires adapter")
        else:
            raise ValueError('callback budget')
    state = machine.snapshot()
    differences = []
    count = 0
    for task in order:
        for name, base in (('task_wait', 0xbbe), ('task_delay', 0xc1e), ('task_flags', 0xc7e)):
            count += 1
            if state[name][task // 2] != word(expected, base + task):
                differences.append([task, name, state[name][task // 2], word(expected, base + task)])
        frame = state['task_frame'][task // 2]
        if 0x3f2 <= frame <= 0xbba:
            index = frame - 0x3f2 + 3
            pc = state['task_heap'][index] | state['task_heap'][index + 1] << 8
            count += 1
            if pc != word(expected, frame + 3):
                differences.append([task, 'pc', pc, word(expected, frame + 3)])
    result = {'status': 'passed' if not differences else 'mismatch',
              'seed_sha256': hashlib.sha256(seed).hexdigest(),
              'comparison_sha256': hashlib.sha256(expected).hexdigest(),
              'active_tasks': order, 'ready_tasks': ready, 'callbacks': callbacks,
              'compared_fields': count, 'differences': differences,
              'scope': 'one source-seeded scheduler pass; task PC, wait, delay and flags only'}
    print(json.dumps(result, sort_keys=True))
    if differences:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
