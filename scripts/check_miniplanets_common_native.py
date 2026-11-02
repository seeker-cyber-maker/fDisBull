#!/usr/bin/env python3
"""Qualify source-bound procedural UIL against controlled original CPU calls.

Inputs/outputs containing original map or text bytes stay in a fresh private
directory. This component protocol is separate from ordinary game completion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, author_program, canonical
from check_miniplanets_native import CORE_SHA, ROM_SHA, run_batches, _private_output


def sha(value):
    return hashlib.sha256(value).hexdigest()


def bcd(value):
    return int(str(value), 16)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'core', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    rom_path, core_path = Path(args.rom).resolve(), Path(args.core).resolve()
    rom = rom_path.read_bytes()
    if sha(rom) != ROM_SHA or sha(core_path.read_bytes()) != CORE_SHA:
        parser.error('exact qualified ROM and Genesis core required')
    out = _private_output(args.output)
    out.mkdir()
    sources = ['src/fdisbull/game_sources/miniplanets_full.c',
               'src/fdisbull/game_sources/miniplanets_actors.c',
               'src/fdisbull/game_il.py',
               'src/fdisbull/data/miniplanets_full_contract.json',
               'scripts/check_miniplanets_common_native.py',
               'scripts/probe_genesis_function.py']
    hashes = {name: sha((ROOT / name).read_bytes()) for name in sources}
    source = '\n'.join((ROOT / name).read_text() for name in sources[:2])
    program = author_program(source, [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA}])
    facts = json.loads((ROOT / sources[3]).read_text())
    machine = GameMachine(program, {0: rom}, environment={'hv16': [0], 'sound_busy': [0]})
    zero = machine.snapshot()
    baseline = {**zero, 'stage_name': 0x11, 'lives': 5, 'timer_ok': 255,
                'belt_ok': 255, 'time_setting': 2, 'life_setting': 2,
                'time_secs': 0x60, 'time_frames': 60, 'next_life': 0x15000,
                'keys_left': 1, 'player_x': 64, 'player_y': 64, 'player_angle': 2,
                'rng_seed': 0x2345}
    cases = {name: [] for name in facts['procedures']}

    def add(entry, name, update=None, arguments=()):
        cases[entry].append({'name': name, 'before': {**baseline, **(update or {})},
                             'arguments': list(arguments)})

    for phase in range(256):
        add('update_subpixel', f'phase-{phase}', {'anim': phase})
    for tile in range(35):
        for direction in range(16):
            for phase in (0, 255):
                add('run_player', f'tile{tile}-pad{direction}-sub{phase}',
                    {'world': [tile] * 256, 'joy_hold': direction, 'subpixel': phase})
    for jump in (0, 1, 16, 23, 24, 25, 47, 48):
        for spring in (0, 1, 40):
            for press in (0, 16, 32, 64):
                add('run_player', f'jump{jump}-spring{spring}-press{press}',
                    {'player_jump': jump, 'player_spring': spring, 'joy_press': press})
    for ending in range(4):
        for x, y in ((0, 0), (31, 31), (32, 32), (33, 255), (64, 192)):
            add('run_player', f'ending{ending}-position{x}-{y}',
                {'ending_phase': ending, 'player_x': x, 'player_y': y})
    for value in (1, 27, 28, 29, 63, 64, 95, 96):
        for field in ('player_win', 'player_die'):
            add('run_player', f'{field}-{value}', {field: value, 'ingame_status': 2})
    for setting in range(5):
        for score in (0, 9999, 14999, 999998, 999999):
            for points in (0, 1, 50, 500, 100000):
                for lives in (5, 99):
                    add('add_score', f'setting{setting}-score{score}-points{points}-lives{lives}',
                        {'score': bcd(score), 'lives': bcd(lives), 'life_setting': setting},
                        (bcd(points),))
        for seconds in (0, 1, 59, 90):
            for frames in (0, 1, 63, 64, 65, 255):
                add('run_tally', f'setting{setting}-secs{seconds}-frames{frames}',
                    {'time_setting': setting, 'time_secs': bcd(seconds),
                     'time_frames': frames, 'ingame_status': 2})
    for phase in range(4):
        for timer in (0, 1, 31, 32, 63, 64, 179, 180, 255):
            for fade in (0, 59, 60):
                add('run_ending', f'phase{phase}-timer{timer}-fade{fade}',
                    {'ending_phase': phase, 'ending_timer': timer, 'ending_fade': fade})
    for seconds in (0, 1, 30, 59, 90):
        for frames in (0, 1, 2, 59, 60, 255):
            add('update_level_timer', f'secs{seconds}-frames{frames}',
                {'time_secs': bcd(seconds), 'time_frames': frames})
            for guard in ('player_win', 'player_die', 'end_game', 'ending_phase', 'timer_ok'):
                add('update_level_timer', f'secs{seconds}-frames{frames}-guard{guard}',
                    {'time_secs': bcd(seconds), 'time_frames': frames,
                     guard: 0 if guard == 'timer_ok' else 1})
    for phase in range(5):
        for timer in (0, 31, 32, 119, 120, 127, 239, 240, 255):
            for bonus in (0, 500, 5000):
                add('update_clear_all', f'phase{phase}-timer{timer}-bonus{bonus}',
                    {'clear_phase': phase, 'clear_timer': timer,
                     'clear_qisha_pos': -4 if phase == 0 else 0,
                     'stage_bonus': bcd(bonus)})
    for text in (0xFFFFFFFF, 0xFF000000, 0x00000000, 0x07050307,
                 0x08040100, 0x04010306, 0x02040107, 0x00030702,
                 0x05010303, 0x02000602, 0x01020304):
        for press in (0, 16, 32, 64, 96, 128, 255):
            add('update_password_dial', f'password{text:08x}-press{press}',
                {'entered_password': text, 'joy_press': press,
                 'password_dial_anim': list(range(10))})
    for hold in (0, 4, 8, 12):
        for digit in range(10):
            for delay in (0, 1, 6):
                add('update_password_dial', f'hold{hold}-digit{digit}-delay{delay}',
                    {'entered_password': 0xFFFFFFFF, 'joy_hold': hold,
                     'password_dial': digit, 'password_delay': delay})

    # Sample the actual immutable staff-roll writer's legal pointer states.
    machine.set_state(baseline)
    machine.call('enter_credits')
    serial = 0
    for tick in range(12000):
        before = machine.snapshot()
        if before['credits_delay'] == 1 or tick % 127 == 0:
            add('update_credits_text', f'credits-{serial}', before)
            serial += 1
        machine.call('update_credits_text')
        if machine.snapshot()['credits_source'] == 0x491D8:
            add('update_credits_text', f'credits-{serial}', machine.snapshot())
            break
    else:
        raise AssertionError('staff-roll writer failed to reach original terminator')

    summary = {'format': 'miniplanets-common-uil-original-cpu-1', 'status': 'running',
               'source_sha256': ROM_SHA, 'core_sha256': CORE_SHA,
               'program_sha256': sha(canonical(program)), 'source_hashes': hashes,
               'tree_sha256': sha(json.dumps(program['tree'], sort_keys=True, separators=(',', ':')).encode()),
               'native_instructions': 0, 'native_master_cycles': 0,
               'counts': {}, 'first_divergence': None,
               'qualification': 'controlled component entries; not natural whole-game completion'}
    total_steps = 0
    try:
        for entry, group in cases.items():
            fact = facts['procedures'][entry]
            mapping = {**facts['contexts']['common'], **facts['contexts'][fact['context']]}
            watch = [{'name': k, 'address': v['address'], 'length': v['length']}
                     for k, v in mapping.items()]
            native = []
            expected = []
            for item in group:
                state = item['before']
                machine.set_state(state)
                result = machine.call(entry, *item['arguments'])
                total_steps += result['steps']
                after = machine.snapshot()
                def encode(name, value):
                    field = mapping[name]
                    if isinstance(value, list): return bytes(value).hex()
                    value = value + field.get('pointer_base', 0)
                    return (value & ((1 << (8 * field['length'])) - 1)).to_bytes(field['length'], 'big').hex()
                native.append({'name': item['name'],
                    'ram': [{'address': v['address'], 'data': encode(k, state[k])}
                            for k, v in mapping.items()],
                    'registers': dict(zip(fact.get('arguments', []), item['arguments']))})
                expected.append({k: encode(k, after[k]) for k in mapping})
            common = {'entry': fact['entry'],
                      'code_ranges': [{'start': a, 'end': b} for a, b in fact['ranges']],
                      'watch': watch, 'max_instructions': 640,
                      'max_master_cycles': 1000000, 'stack_scratch_bytes': 256}
            if 'stop_pcs' in fact:
                common['stop_pcs'] = fact['stop_pcs']
            reports = run_batches(out, entry, common, native, rom_path, core_path)
            summary['native_instructions'] += sum(r['instructions_executed'] for r in reports)
            summary['native_master_cycles'] += sum(r['master_cycles'] for r in reports)
            for item, wanted, observed in zip(group, expected, reports):
                for field, value in wanted.items():
                    if observed['ram_after'][field] != value:
                        summary['first_divergence'] = {'procedure': entry, 'case': item['name'],
                            'field': field, 'uil': value, 'original': observed['ram_after'][field]}
                        raise AssertionError(f'{entry} diverged: {item["name"]} / {field}')
            summary['counts'][entry] = len(group)
            print(entry, len(group), 'passed', flush=True)
        summary['uil_steps'] = total_steps
        summary['inputs_unchanged'] = hashes == {name: sha((ROOT / name).read_bytes()) for name in sources}
        summary['status'] = 'passed' if summary['inputs_unchanged'] else 'source-changed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['failure'] = str(exc)
        raise
    finally:
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
