#!/usr/bin/env python3
"""Check title-controller component against instruction-entry observations.

The source $01EA edge word and initial selection are supplied separately for
each case. This qualifies a component, not autonomous joypad/menu/intro replay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import author_program, canonical
from fdisbull.shadowrun_snes_menu import SOURCE, menu_machine
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

CORE = '6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def word(raw, at): return int.from_bytes(raw[at:at + 2], 'little')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'entries', 'stores', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    out = _private_directory(a.output)
    if out.exists(): raise ValueError('output must be new')
    rom = a.rom.read_bytes()
    m = menu_machine(rom)
    def read(folder, pc):
        raw = (folder / 'receipt.json').read_bytes()
        r = json.loads(raw)
        c = r['snes_checkpoints']
        if (r['rom_sha256'] != sha(rom) or r['core_sha256'] != CORE or r['patches'] or
                r['system'] != 'snes' or c['pc'] != pc or
                not c['phase'].startswith('before selected opcode')):
            raise ValueError('unexpected source identity, patch or checkpoint phase')
        result = {}
        seen_frames = set()
        serials = []
        for frame in c['frames']:
            if frame['video_frame'] in seen_frames: raise ValueError('duplicate checkpoint frame')
            seen_frames.add(frame['video_frame'])
            if frame['dropped'] or len(frame['captures']) > 1: raise ValueError('ambiguous capture')
            if not frame['captures']: continue
            item = frame['captures'][0]
            data = (folder / item['file']).read_bytes()
            reg = item['registers']
            if (len(data) != 131072 or sha(data) != item['sha256'] or
                    reg['pc'] != pc or reg['d'] or reg['p'] & 0x30 or reg['x'] != 3):
                raise ValueError('capture identity or CPU mode mismatch')
            result[frame['video_frame']] = (data, reg)
            serials.append(item['serial'])
        if any(y <= x for x, y in zip(serials, serials[1:])):
            raise ValueError('checkpoint serial order mismatch')
        run_keys = ('system', 'rom_sha256', 'core_sha256', 'frames', 'inputs',
                    'core_options', 'memory_injection_mode', 'patches',
                    'patches_input_sha256', 'patches_phase', 'state_sha256',
                    'system_ram_sha256', 'save_ram_sha256', 'ram_trace_sha256')
        return result, sha(raw), {key: r[key] for key in run_keys}
    entries, entry_hash, entry_run = read(a.entries, 0x81e274)
    stores, store_hash, store_run = read(a.stores, 0x81e30c)
    if entry_run != store_run:
        raise ValueError('checkpoint runs have different inputs, configuration or final state')
    cases = {850: (0, 0x400, 1), 900: (1, 0x400, 2), 950: (2, 0x800, 1)}
    if set(stores) != set(cases) or not set(cases).union(x + 1 for x in cases) <= entries.keys():
        raise ValueError('three complete source case boundaries are required')
    for frame, expected in cases.items():
        data, _ = entries[frame]
        observed = (word(data, 0xe), word(data, 0x1ea), stores[frame][1]['a'])
        if observed != expected:
            raise ValueError('source menu case contract mismatch')
    # Native entry takes the component's pre-set edge word as state, rather
    # than pretending to implement its unqualified physical-input producer.
    program = author_program(SOURCE.read_text() + '\nu8 menu_frame_status;void menu_frame(u8 unused){menu_frame_status=2U;shadowrun_snes_menu_control(0U);if(menu_supported)menu_frame_status=1U;}',
                             m.program['regions'], evidence=m.program['evidence'])
    from fdisbull.game_il import GameMachine
    m = GameMachine(program, {0: rom})
    watched = {str(x): sha(x.read_bytes()) for x in (SOURCE, Path(__file__).resolve())}
    out.mkdir(mode=0o700, parents=True)
    build = build_macos(program, m.snapshot(), out / 'native', entry='menu_frame')
    native = Native(out / 'native/libfdisbull_native.dylib', a.rom.resolve())
    checks = []
    native_elements = 0
    try:
        for frame in sorted(stores):
            seed, _ = entries[frame]
            expected = stores[frame][1]['a']
            initial = {'menu_selection': word(seed, 0xe), 'menu_pressed': word(seed, 0x1ea),
                       'menu_disabled': [word(seed, 0x11c0 + i * 2) for i in range(3)],
                       'menu_confirmed': 0, 'menu_supported': 0, 'menu_frame_status': 0}
            m.set_state(initial)
            for name, value in initial.items():
                for i, v in enumerate(value if isinstance(value, list) else [value]):
                    if native.lib.fdisbull_state_set(native.ctx, name.encode(), i, v):
                        raise ValueError('native component input failed')
            m.call('menu_frame', 0)
            state = m.snapshot()
            if native.step(0) or state['menu_selection'] != expected or not state['menu_supported']:
                raise AssertionError(('menu source mismatch', frame))
            if word(entries[frame + 1][0], 0xe) != expected:
                raise AssertionError('following source entry did not confirm store')
            native_elements += native.compare(state, frame)
            checks.append({'video_frame': frame, 'before': initial['menu_selection'],
                           'source_edge_word': initial['menu_pressed'], 'after': expected})
    finally: native.close()
    if any(sha(Path(k).read_bytes()) != v for k, v in watched.items()):
        raise ValueError('component changed during check')
    report = {'status': 'passed', 'source_cases': checks, 'native_elements': native_elements,
              'program_sha256': sha(canonical(program)), 'native_build': build,
              'entry_receipt_sha256': entry_hash, 'store_receipt_sha256': store_hash,
              'source_hashes': watched,
              'scope': 'source-fed three title-selection component cases; input producer, display, other menus and intro continuation unqualified'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
