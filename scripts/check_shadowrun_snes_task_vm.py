#!/usr/bin/env python3
"""Compare source-seeded task VM slices with private intro WRAM observations.

Arrival events are injected at the component boundary and actor callbacks are
acknowledged without modeling them. This is not a composed scene comparison.
The selected endpoint snapshots are used only for comparisons.
"""
import argparse
import json
from pathlib import Path

from fdisbull.shadowrun_snes_script import tasks_from_capture


def word(data, address):
    return int.from_bytes(data[address:address + 2], 'little')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True)
    p.add_argument('--captures', required=True, type=Path)
    args = p.parse_args()
    captures = args.captures
    seed = (captures / 'ram-002000.bin').read_bytes()
    machine = tasks_from_capture(Path(args.rom).read_bytes(), seed)
    callbacks = []

    def run(task):
        machine.set_state({'task_index': task, 'task_vm_resume_value': 0})
        for _ in range(16):
            machine.call('shadowrun_snes_task_vm', 0)
            state = machine.snapshot()
            if state['task_vm_status'] == 1:
                return state
            if state['task_vm_status'] != 2:
                raise ValueError('unsupported VM state or budget')
            fn = state['task_vm_callback']
            callbacks.append([task, fn, state['task_vm_arg0'],
                              state['task_vm_arg1'], state['task_vm_arg2']])
            if fn == 0xd1:
                machine.set_state({'task_callback_success': 1})
                machine.call('shadowrun_snes_task_callback_complete', 0)
            else:
                machine.call('shadowrun_snes_task_native', 0)
                if not machine.snapshot()['task_native_supported']:
                    raise ValueError('unsupported native callback')
        raise ValueError('callback budget')

    def compare(state, task, frame):
        source = (captures / f'ram-{frame:06}.bin').read_bytes()
        i = task // 2
        source_frame = word(source, 0x26e + task)
        checks = {'pc': (state['task_vm_pc'], word(source, source_frame + 3)),
                  'wait': (state['task_wait'][i], word(source, 0xbbe + task)),
                  'delay': (state['task_delay'][i], word(source, 0xc1e + task)),
                  'flags': (state['task_flags'][i], word(source, 0xc7e + task))}
        if any(a != b for a, b in checks.values()):
            raise ValueError(f'task {task:#x} frame {frame}: {checks}')
        return {'task': task, 'original_frame': frame, 'fields_matched': list(checks)}

    results = []
    machine.set_state({'task_index': 0x10})
    for _ in range(5):
        machine.call('shadowrun_snes_task_check', 0)
    results.append(compare(run(0x10), 0x10, 2005))
    for task, frame in ((0x10, 2041), (0x12, 2052)):
        machine.set_state({'task_index': task})
        machine.call('shadowrun_snes_task_signal', 0)
        machine.call('shadowrun_snes_task_check', 0)
        results.append(compare(run(task), task, frame))
    print(json.dumps({'status': 'passed', 'comparisons': results, 'callbacks': callbacks,
                      'scope': 'seeded-once task component; injected arrival signals; '
                               'actor callbacks acknowledged only; no scene parity',
                      'unresolved': 'entity flag clearing by task 0x08 is outside this component schedule'},
                     sort_keys=True))


if __name__ == '__main__':
    main()
