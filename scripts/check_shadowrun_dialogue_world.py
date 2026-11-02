#!/usr/bin/env python3
"""Compare the prompt GameIL against controlled original 68000 execution.

ROM, core and byte-retaining receipts stay in a new private output directory.
Controlled entry does not establish ordinary game reachability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_dialogue import lift_dialogue, read_prompt
from fdisbull.shadowrun_world import read_scene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True)
    ap.add_argument('--core', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    rom, core = Path(args.rom).resolve(), Path(args.core).resolve()
    data = rom.read_bytes()
    machine = GameMachine(lift_dialogue(data), {})
    scenes = [read_scene(data, i) for i in range(56)]
    cases = []
    for address in (0xf4aa0, 0xf4ab4):
        prompt = read_prompt(data, address)
        for buttons in range(8):
            flags = ((buttons & 1) << 6) | ((buttons & 2) << 3) | ((buttons & 4) << 3)
            enabled = ('00' if len(prompt.options) > 1 else 'ff') + ('00' if len(prompt.options) > 2 else 'ff')
            cases.append({'name': f'{address:x}-{buttons}', 'registers': {'A0': address + 16},
                'ram': [{'address': 0xffdd22, 'data': f'{flags:02x}'},
                        {'address': 0xfff0d2, 'data': enabled}]})
    contract = {'name': 'prompt-input', 'entry': 0x1f522,
        'code_ranges': [{'start': 0x1f522, 'end': 0x1f572}],
        'stop_pcs': [0x1f572, 0x1f3c4, 0x1f50c], 'max_instructions': 18, 'cases': cases}
    output = _private_directory(args.output)
    output.mkdir()
    (output / 'contract.json').write_text(json.dumps(contract))
    command = [sys.executable, str(ROOT / 'scripts' / 'probe_genesis_function.py'),
               '--rom', str(rom), '--core', str(core), '--contract', str(output / 'contract.json'),
               '--output', str(output / 'native')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    receipt = json.loads((output / 'native' / 'receipt.json').read_text())
    if not receipt['complete'] or not receipt['inputs_unchanged'] or len(receipt['cases']) != len(cases):
        raise AssertionError('native receipt incomplete')
    for index, native in enumerate(receipt['cases']):
        address = (0xf4aa0, 0xf4ab4)[index // 8]
        prompt = read_prompt(data, address)
        buttons = index % 8
        flags = ((buttons & 1) << 6) | ((buttons & 2) << 3) | ((buttons & 4) << 3)
        targets = prompt.targets + (0,) * (3 - len(prompt.targets))
        machine.set_state(dict(zip(('shadowrun_dialogue_buttons', 'shadowrun_dialogue_option_count',
            'shadowrun_dialogue_terminal', 'shadowrun_dialogue_target_a', 'shadowrun_dialogue_target_b',
            'shadowrun_dialogue_target_c'), (flags, len(prompt.options), 0, *targets))))
        machine.call('shadowrun_dialogue_select')
        state, registers = machine.snapshot(), native['registers_after']
        pc = registers['PC']
        expected = (0, 0) if pc == 0x1f50c else ((1 if pc == 0x1f572 else 2), registers['A0'])
        actual = (state['shadowrun_dialogue_result'], state['shadowrun_dialogue_value'])
        if actual != expected:
            raise AssertionError(f"{cases[index]['name']}: {actual} != {expected}")
    machine.set_state({'shadowrun_dialogue_buttons': 64, 'shadowrun_dialogue_option_count': 1,
                       'shadowrun_dialogue_target_a': 0x80000000})
    machine.call('shadowrun_dialogue_select')
    if machine.snapshot()['shadowrun_dialogue_result'] != 4:
        raise AssertionError('negative target was not refused')
    if rom.read_bytes() != data:
        raise AssertionError('source changed during check')
    summary = {'status': 'passed', 'native_cases': len(cases), 'negative_target': 'refused',
        'source_sha256': hashlib.sha256(data).hexdigest(), 'scene_count': len(scenes),
        'unique_profiles': len({scene.profile for scene in scenes}),
        'collision_rows': sum(len(scene.collision) for scene in scenes),
        'event_tables': sum(scene.event_table is not None for scene in scenes),
        'scope': 'controlled input selection; negative target refusal; static scene inventory'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
