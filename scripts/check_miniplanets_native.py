#!/usr/bin/env python3
"""Compare declared level-state transitions with original Miniplanets CPU code.

The supplied before/after states are observations to check, not a CPU model.
Original UpdateSubpixel, RunPlayer and RunKey execute through the pinned core.
This is a controlled stage-1 projection; ordinary gameplay reachability, global
clock/score rules, audio rendering and post-win/death screens are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA = 'e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7'
CORE_SHA = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
PLAYER = 0xff088c
OBJECT = 0xff0894
KEYS = 0xff0783
MAP = 0xff0786
WATCH = [
    {'name': 'player', 'address': PLAYER, 'length': 8},
    {'name': 'keys', 'address': KEYS, 'length': 1},
    {'name': 'status', 'address': 0xff0782, 'length': 1},
    {'name': 'sound_requests', 'address': 0xff075e, 'length': 2},
    {'name': 'key_object', 'address': OBJECT, 'length': 4},
]
PLAYER_FIELDS = {'$x': 0, '$y': 1, '$angle': 2, '$action': 3,
                 '$jump': 4, '$win': 6, '$dead': 7}
REQUIRED = set(PLAYER_FIELDS) | {'$keys', '$key_active', '$phase',
                               '$buttons', '$prev_buttons'}
SOURCES = ('scripts/check_miniplanets_native.py', 'scripts/probe_genesis_function.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in SOURCES}


def _private_output(path):
    out = Path(path).expanduser().resolve()
    if out.exists() or not out.parent.is_dir():
        raise ValueError('output must be new and its parent must exist')
    if any((p / '.git').exists() for p in (out, *out.parents)):
        raise ValueError('native byte-retaining output must be outside Git')
    return out


def load_cases(path):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('case file exceeds 16 MiB')
    cases = json.loads(path.read_bytes())
    if not isinstance(cases, list) or not 1 <= len(cases) <= 5000:
        raise ValueError('cases must be a list of 1..5000 transitions')
    names = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'name', 'before', 'after'}:
            raise ValueError('case requires name, before and after')
        name = case['name']
        if not isinstance(name, str) or not name or len(name) > 128 or name in names:
            raise ValueError('case names must be unique nonempty strings up to 128 characters')
        names.add(name)
        for key in ('before', 'after'):
            state = case[key]
            if not isinstance(state, dict) or not REQUIRED <= set(state):
                raise ValueError('state lacks required level-profile variables')
            if any(type(state[k]) is not int or not 0 <= state[k] <= 255 for k in REQUIRED):
                raise ValueError('level-profile state values must be u8 integers')
            if state['$keys'] not in (0, 1) or state['$key_active'] not in (0, 1):
                raise ValueError('stage-1 profile has one binary key state')
    return cases


def native_buttons(value):
    # Public profile: R,L,U,D,A,B,Start,Select. Original: U,D,L,R,B,C,A,Start.
    return sum(native for bit, native in ((0, 8), (1, 4), (2, 1), (3, 2),
                                          (4, 64), (5, 16), (6, 128))
               if value & (1 << bit))


def _seed(address, data):
    return {'address': address, 'data': bytes(data).hex()}


def _contract(entry, ranges, watch):
    return {'entry': entry,
            'code_ranges': [{'start': start, 'end': end} for start, end in ranges],
            'watch': watch, 'stack_scratch_bytes': 64,
            'max_instructions': 256, 'max_master_cycles': 100000}


def run_batches(out, label, common, cases, rom, core):
    reports = []
    for start in range(0, len(cases), 200):
        number = start // 200
        contract_path = out / f'{label}-{number:03d}.json'
        contract_path.write_text(json.dumps({**common, 'cases': cases[start:start + 200]}) + '\n')
        destination = out / f'{label}-{number:03d}'
        proc = subprocess.run([
            sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
            '--rom', str(rom), '--core', str(core), '--contract', str(contract_path),
            '--output', str(destination)], capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise RuntimeError(f'{label} native worker failed: {proc.stderr[-2000:]}')
        report = json.loads((destination / 'receipt.json').read_text())
        if (not report['complete'] or not report['inputs_unchanged'] or
                report['source_sha256'] != ROM_SHA or report['core_sha256'] != CORE_SHA):
            raise RuntimeError(f'{label} native evidence is incomplete or changed')
        if len(report['cases']) != len(cases[start:start + 200]):
            raise RuntimeError(f'{label} native case count mismatch')
        reports.extend(report['cases'])
    return reports


def player_bytes(state):
    return bytes((state['$x'], state['$y'], state['$angle'], state['$action'],
                  state['$jump'], 0, state['$win'], state['$dead']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'core', 'cases', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    rom_path, core_path = Path(args.rom).resolve(), Path(args.core).resolve()
    rom = rom_path.read_bytes()
    if sha(rom) != ROM_SHA or sha(core_path.read_bytes()) != CORE_SHA:
        parser.error('exact qualified Miniplanets ROM and Genesis core required')
    cases = load_cases(args.cases)
    out = _private_output(args.output)
    frozen = source_hashes()
    cases_sha = sha(Path(args.cases).read_bytes())
    out.mkdir()
    active, skipped = [], []
    for case in cases:
        before = case['before']
        if before['$buttons'] & 64:
            skipped.append({'name': case['name'], 'reason': 'authored Start-reset adapter'})
        elif before['$dead'] or before['$win']:
            skipped.append({'name': case['name'], 'reason': 'authored terminal-screen adapter'})
        else:
            active.append(case)
    summary = {
        'format': 'miniplanets-original-native-level-transitions-1', 'status': 'running',
        'source_sha256': ROM_SHA, 'core_sha256': CORE_SHA, 'cases_sha256': cases_sha,
        'source_hashes': frozen, 'cases_supplied': len(cases), 'active_cases': len(active),
        'excluded_cases': skipped,
        'scope': 'original RunPlayer then RunKey RAM projection under explicit stage-1 caller state',
        'assumptions': ['stage 1-1 map and single original key object',
                        'EndingPhase, ShakeTimer, Muteki and PlayerSpring are zero',
                        'source sound-request code executes; rendered audio excluded',
                        'registers reset between declared calls; only declared RAM projection compared',
                        'global clock, score tally, rendering and ordinary game reachability excluded',
                        'Start reset and terminal screen are authored adapters excluded here'],
    }
    def save():
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    def fail(stage, name, expected, observed):
        summary['first_divergence'] = {'stage': stage, 'name': name,
                                       'expected': expected, 'observed': observed}
        raise AssertionError(f'original native {stage} divergence at {name}')
    save()
    try:
        if not active:
            raise ValueError('no active gameplay transitions supplied')
        # Qualify the phase mapping from the independent original CPU, before
        # using its actual outputs as inputs to RunPlayer.
        phase_contract = _contract(0x2fe, [(0x2fe, 0x32e)], [
            {'name': 'subpixel', 'address': 0xff075a, 'length': 2}])
        phases = [{'name': f'phase{i:03d}', 'ram': [
            _seed(0xff0758, i.to_bytes(2, 'big'))]} for i in range(256)]
        phase_reports = run_batches(out, 'phase', phase_contract, phases, rom_path, core_path)
        phase_values = []
        for i, report in enumerate(phase_reports):
            value = int(report['ram_after']['subpixel'], 16)
            expected = int(f'{i:08b}'[::-1], 2)
            if value != expected:
                fail('UpdateSubpixel', report['contract']['name'], expected, value)
            phase_values.append(value)
        summary['native_phase_cases_checked'] = 256
        summary['native_phase_table_sha256'] = sha(bytes(phase_values))
        save()

        player_contract = _contract(0x43dc, [
            (0x43dc, 0x468a), (0x3c8c, 0x3cae), (0x49e6, 0x4a26),
            (0x3792, 0x37b4), (0x7c8, 0x7de)], WATCH)
        player_cases = []
        world = rom[0x616e0:0x617e0]
        for case in active:
            before = case['before']
            held = native_buttons(before['$buttons'])
            pressed = held & ~native_buttons(before['$prev_buttons']) & 255
            object_data = bytes((before['$key_active'], 0, 0x60, 0))
            player_cases.append({'name': case['name'], 'ram': [
                _seed(MAP, world),
                _seed(PLAYER, player_bytes(before) + object_data),
                _seed(0xff004a, (held, pressed)),
                _seed(0xff075a, phase_values[before['$phase']].to_bytes(2, 'big')),
                _seed(0xff0782, (0, before['$keys']))]})
        players = run_batches(out, 'player', player_contract, player_cases, rom_path, core_path)
        key_cases, key_sources = [], []
        for case, report in zip(active, players):
            raw = bytes.fromhex(report['ram_after']['player'])
            observed = {name: raw[offset] for name, offset in PLAYER_FIELDS.items()}
            expected = {name: case['after'][name] for name in PLAYER_FIELDS}
            if observed != expected:
                fail('RunPlayer', case['name'], expected, observed)
            if case['before']['$key_active']:
                key_sources.append(case)
                key_cases.append({'name': case['name'], 'registers': {'A0': OBJECT}, 'ram': [
                    _seed(PLAYER, raw + bytes.fromhex(report['ram_after']['key_object'])),
                    _seed(KEYS, bytes.fromhex(report['ram_after']['keys'])),
                    _seed(0xff0782, bytes.fromhex(report['ram_after']['status'])),
                    _seed(0xff075e, bytes.fromhex(report['ram_after']['sound_requests']))]})
            else:
                observed = {'$keys': int(report['ram_after']['keys'], 16),
                            '$key_active': int(report['ram_after']['key_object'][:2], 16)}
                expected = {name: case['after'][name] for name in observed}
                if observed != expected:
                    fail('inactive key dispatch', case['name'], expected, observed)
        summary['native_player_cases_checked'] = len(players)
        save()

        key_contract = _contract(0x4b90, [
            (0x4b90, 0x4c10), (0x49a0, 0x49e2), (0x7c8, 0x7de)], WATCH)
        keys = run_batches(out, 'key', key_contract, key_cases, rom_path, core_path)
        for case, report in zip(key_sources, keys):
            observed = {'$keys': int(report['ram_after']['keys'], 16),
                        '$key_active': int(report['ram_after']['key_object'][:2], 16)}
            expected = {name: case['after'][name] for name in observed}
            if observed != expected:
                fail('RunKey', case['name'], expected, observed)
        summary['native_key_cases_checked'] = len(keys)
        summary['active_transitions_checked'] = len(active)
        summary['native_instructions_executed'] = sum(
            report['instructions_executed'] for report in phase_reports + players + keys)
        summary['native_master_cycles'] = sum(
            report['master_cycles'] for report in phase_reports + players + keys)
        summary['native_changed_ram_outside_contract'] = sum(
            len(report['changes_outside_watches_and_stack'])
            for report in phase_reports + players + keys)
        if (source_hashes() != frozen or sha(rom_path.read_bytes()) != ROM_SHA or
                sha(core_path.read_bytes()) != CORE_SHA or
                sha(Path(args.cases).read_bytes()) != cases_sha):
            raise RuntimeError('source, core, cases or oracle scripts changed during verification')
        summary['inputs_unchanged'] = True
        summary['status'] = 'passed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['failure'] = f'{type(exc).__name__}: {exc}'
        save()
        raise
    save()
    print(out / 'summary.json')


if __name__ == '__main__':
    main()
