#!/usr/bin/env python3
"""Qualify source menu transitions and the original automatic field walk."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_menu import SOURCE, lift_menu
from fdisbull.shadowrun_replay import _read_rom


def sha(b): return hashlib.sha256(b).hexdigest()


def main():
    p = argparse.ArgumentParser()
    for name in ('rom', 'cursor-receipt', 'baseline-menu', 'menu-capture', 'intro-capture', 'field-capture', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    rom = _read_rom(a.rom); raw = SOURCE.read_bytes(); checker = Path(__file__).read_bytes(); program = lift_menu(rom)
    machine = GameMachine(program, {0: rom})
    receipt = a.cursor_receipt.read_bytes()
    if sha(receipt) != 'c0f2f4074d55de51fc1c2cfec9e8e21192f5267caba7b4300614e946a905d32d':
        raise ValueError('unreviewed original cursor probe')
    native = json.loads(receipt)
    if not native['complete'] or not native['inputs_unchanged'] or len(native['cases']) != 15:
        raise ValueError('incomplete original cursor probe')
    for case, result in zip(native['contract']['cases'], native['cases']):
        top = case['registers']['D3']; delta = case['registers']['D2'] & 255
        initial = int(case['ram'][0]['data'], 16)
        pressed = {255: 0x100, 0: 0, 1: 0x200}[delta]
        machine.set_state({'shadowrun_menu_phase': 0 if top == 1 else 1,
                           'shadowrun_menu_cursor': initial, 'shadowrun_menu_preview': initial,
                           'shadowrun_menu_pressed': pressed})
        machine.call('shadowrun_menu_tick'); state = machine.snapshot()
        if (not state['shadowrun_menu_supported'] or result['registers_after']['PC'] != 0xc3a2 or
            state['shadowrun_menu_cursor'] != int(result['ram_after']['cursor'], 16) or
            result['changes_outside_watches_and_stack']):
            raise AssertionError(('cursor', case['name'], state, result))
    def capture(root, receipt_hash, capture_hash):
        if sha((root / 'native/receipt.json').read_bytes()) != receipt_hash:
            raise ValueError('original source receipt mismatch')
        data = (root / 'capture.json').read_bytes()
        if sha(data) != capture_hash: raise ValueError('original capture manifest mismatch')
        return json.loads(data)
    nav = capture(a.menu_capture, '42ea42af549931e20a2f7c608f923233161e97412d1fcbaf27cd7be6f6abe04d',
                  '330ced193d9926d4c29fa6ab0f0aa912b84339e83d94d8eec76f3715a0f06e6e')
    baseline = capture(a.baseline_menu, '018c04d3addce86d750ebc34c0165c55a07388a690a3a119b33daf3af55266dd',
                       '76973a51067312c657b8b05c3e32c4638c507bd84d83078be8f20c78832ef843')
    field = capture(a.field_capture, 'c2bdc90e2ab753ea178f22424b218e8586a8e7ef0864d3e0108b37ac5306144f',
                    '6512e6aff12ad978feec46a5b1a65234ace1e9c695477cf5665997562d6ac182')
    field_receipt = json.loads((a.field_capture / 'native/receipt.json').read_bytes())
    if field_receipt['patches'] or any(x['end'] > 4765 and x['start'] < 5255
                                       for x in field_receipt['inputs']):
        raise ValueError('field walk has patches or scheduled controller input')
    intro = capture(a.intro_capture, '4364f8a3d0ec47ae938cffb6754ce84a80cf6edad7bd6436277a4b16298a74be',
                    'd41be0da39d9461d5aa1c37ed7ace2082b41869a34b0742d54ce943d1d714eb6')
    def read(root, manifest, name):
        raw = (root / name).read_bytes()
        if sha(raw) != manifest['files'][name]['sha256']: raise ValueError('captured file changed')
        return raw
    def memory(root, manifest, frame):
        raw = read(root, manifest, f'native/scene-{frame:06d}/ram.bin')
        if len(raw) != 65536: raise ValueError('bad RAM length')
        return bytes(raw[i ^ 1] for i in range(65536))
    def word(b, offset): return int.from_bytes(b[offset:offset+2], 'big')
    machine = GameMachine(program, {0: rom})
    start = memory(a.baseline_menu, baseline, 1380)
    if word(start, 0xdd22) != 0x8080 or start[0xf0dc] != 0:
        raise AssertionError('original Start edge mismatch')
    machine.set_state({'shadowrun_menu_pressed': word(start, 0xdd22)})
    machine.call('shadowrun_menu_tick')
    if (machine.snapshot()['shadowrun_menu_phase'], machine.snapshot()['shadowrun_menu_cursor']) != (0, 0):
        raise AssertionError('Start unexpectedly changed the menu')
    actions = (1370, 1380, 1390, 1410, 1420, 1430)
    for frame in actions:
        b = memory(a.menu_capture, nav, frame)
        machine.set_state({'shadowrun_menu_pressed': word(b, 0xdd22)})
        machine.call('shadowrun_menu_tick'); s = machine.snapshot()
        if not s['shadowrun_menu_supported'] or s['shadowrun_menu_cursor'] != b[0xf0dc]:
            raise AssertionError(('menu event', frame, s, b[0xf0dc]))
        if s['shadowrun_menu_phase'] in (1, 2) and s['shadowrun_menu_preview'] != b[0xf0ae]:
            raise AssertionError(('menu preview', frame))
    if (s['shadowrun_menu_phase'], s['shadowrun_menu_archetype'], word(b, 0x10e)) != (2, 0, 3):
        raise AssertionError('Samurai initializer handoff mismatch')
    intro_frames = (1799, 2000, 2200, 2400, 2600, 2800, 3000, 3200,
                    3400, 3600, 3800, 4000, 4200, 4400)
    for frame in intro_frames:
        b = memory(a.intro_capture, intro, frame)
        callback = int.from_bytes(b[0x13a:0x13e], 'big')
        if (word(b, 0x100), word(b, 0x104), word(b, 0x10e), callback) != (1920, 1920, 3, 0xb45c):
            raise AssertionError(('sampled cinematic actor', frame))
    if any(word(memory(a.field_capture, field, f), 0xdd22) for f in (5249, 5250, 5251)):
        raise AssertionError('field movement was not input-free')
    positions = [(word(memory(a.field_capture, field, f), 0x100),
                  word(memory(a.field_capture, field, f), 0x104)) for f in (5249, 5250, 5251)]
    if positions != [(15584, 10440), (15584, 10410), (15584, 10380)]:
        raise AssertionError(('arrival', positions))
    trace = json.loads(read(a.field_capture, field, 'native/ram-writes.json'))
    pairs = {(x['pc'], x['address']) for x in trace if x['frame'] in (5249, 5250, 5251)}
    if not {(0xbbec, 0xff0100), (0xbbf0, 0xff0104), (0xace2, 0xff013c)} <= pairs:
        raise AssertionError('source movement writer/callback witness missing')
    if not any(x['pc'] == 0xace2 and x['address'] == 0xff013c and x['value'] == 0xb574
               for x in trace if x['frame'] in (5249, 5250, 5251)):
        raise AssertionError('source movement callback value missing')
    if SOURCE.read_bytes() != raw or Path(__file__).read_bytes() != checker:
        raise ValueError('menu source or checker changed during check')
    a.output.mkdir(mode=0o700, parents=True)
    result = {'status':'passed','source_sha256':sha(rom),'program_sha256':sha(canonical(program)),
              'authoring_sha256':sha(raw),'cursor_original_receipt_sha256':sha(receipt),
              'checker_sha256':sha(checker),
              'cursor_cases':15,'full_core_menu_action_frames':list(actions),
              'menu_capture_sha256':sha((a.menu_capture/'capture.json').read_bytes()),
              'start_edge_capture_sha256':sha((a.baseline_menu/'capture.json').read_bytes()),
              'intro_capture_sha256':sha((a.intro_capture/'capture.json').read_bytes()),
              'cinematic_actor_sample_frames':list(intro_frames),
              'arrival_capture_sha256':sha((a.field_capture/'capture.json').read_bytes()),
              'arrival_frames':[5249,5250,5251],'arrival_controller_pressed':0,
              'arrival_writer_pc':[0xbbec,0xbbf0],'arrival_moving_callback':0xb574,
              'scope':'original source menu cursor/confirm only and original automatic arrival writer evidence; initializer, load menu, dialogue and cinematic combat excluded'}
    out=a.output/'summary.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','summary_sha256':sha(out.read_bytes())}))

if __name__ == '__main__': main()
