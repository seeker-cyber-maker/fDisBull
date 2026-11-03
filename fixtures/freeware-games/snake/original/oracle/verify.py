#!/usr/bin/env python3
"""Qualify the authored DOS original, not a recovered or converted game."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

SCALARS = ('snake_length', 'direction', 'pending_direction', 'paused', 'game_status',
           'score', 'rng_seed', 'tick_count', 'key_events', 'mouse_events',
           'frame_count', 'mouse_present', 'food_cell', 'turn_queued')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def symbols(build):
    found = {}
    for s, o, name in re.findall(r'^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+(\w+)\s*$',
                               (build / 'SNAKE.MAP').read_text(), re.M):
        found[name.lower()] = (int(s, 16), int(o, 16))
    assert all(name in found for name in (*SCALARS, 'snake_cells', 'snake_step', 'reset_game'))
    return found


def pure(build, vectors, dependency):
    if dependency:
        sys.path.append(str(dependency))
    import unicorn as u
    from unicorn import x86_const as r
    raw = (build / 'SNAKE.EXE').read_bytes()
    h = struct.unpack_from('<14H', raw)
    size = h[2] * 512 - ((512 - h[1]) % 512)
    code = bytearray(raw[h[4] * 16:size])
    for n in range(h[3]):
        off, seg = struct.unpack_from('<HH', raw, h[12] + n * 4)
        index = seg * 16 + off
        struct.pack_into('<H', code, index, (struct.unpack_from('<H', code, index)[0] + 0x1000) & 0xffff)
    sym = symbols(build)
    address = lambda name: 0x10000 + sym[name][0] * 16 + sym[name][1]
    rows = []
    for case in json.loads(vectors.read_text())['cases']:
        cpu = u.Uc(u.UC_ARCH_X86, u.UC_MODE_16)
        cpu.mem_map(0, 0x100000)
        cpu.mem_write(0x10000, bytes(code))
        for name, value in case['initial'].items():
            if name == 'cells':
                cpu.mem_write(address('snake_cells'), struct.pack('<' + 'H' * len(value), *value))
            else:
                cpu.mem_write(address(name), struct.pack('<H', value))
        for name, value in (('CS', 0x1000 + sym['snake_step'][0]),
                            ('DS', 0x1000 + sym['snake_cells'][0]), ('ES', 0x9000),
                            ('SS', 0x7000), ('SP', 0xfff0), ('AX', 0x1111), ('BX', 0x2222),
                            ('CX', 0x3333), ('DX', 0x4444), ('SI', 0x5555), ('DI', 0x6666), ('BP', 0x7777)):
            cpu.reg_write(getattr(r, 'UC_X86_REG_' + name), value)
        preserved = {name: cpu.reg_read(getattr(r, 'UC_X86_REG_' + name))
                     for name in ('AX', 'BX', 'CX', 'DX', 'SI', 'DI', 'BP', 'DS', 'ES', 'SS')}
        cpu.mem_write(0x7fff0, struct.pack('<H', 0xff00))
        interrupts = []
        def no_os(uc, number, _):
            interrupts.append(number)
            uc.emu_stop()
        cpu.hook_add(u.UC_HOOK_INTR, no_os)
        end = (0x1000 + sym['snake_step'][0]) * 16 + 0xff00
        cpu.emu_start(address('snake_step'), end, count=3000000)
        assert not interrupts, (case['id'], 'OS interrupt in pure kernel', interrupts)
        assert cpu.reg_read(r.UC_X86_REG_IP) == 0xff00, (case['id'], 'did not return')
        assert cpu.reg_read(r.UC_X86_REG_SP) == 0xfff2, 'Unbalanced return stack'
        assert {name: cpu.reg_read(getattr(r, 'UC_X86_REG_' + name)) for name in preserved} == preserved
        actual = {name: struct.unpack('<H', bytes(cpu.mem_read(address(name), 2)))[0]
                  for name in SCALARS}
        actual['cells'] = list(struct.unpack('<' + 'H' * actual['snake_length'],
                                            bytes(cpu.mem_read(address('snake_cells'), actual['snake_length'] * 2))))
        assert {key: actual[key] for key in case['expected']} == case['expected'], (case['id'], actual, case['expected'])
        rows.append(dict(id=case['id'], passed=True, register_contract=True, os_interrupts=0))
    return dict(format='fdisbull-snake-pure-validation-1', executable_sha256=sha(build / 'SNAKE.EXE'),
                vectors_sha256=sha(vectors), source_sha256=sha(build / 'SNAKE.ASM'),
                engine='Unicorn ' + u.__version__, cases=rows,
                scope='Real compiled step bytes; independently authored specification cases; constructed states, not ordinary-play reachability')


def native(build, output, emulator):
    from fdisbull.project import Project
    from fdisbull import __version__
    sym = symbols(build)
    address = lambda name: hex(0x10000 + sym[name][0] * 16 + sym[name][1])
    original = sha(build / 'SNAKE.EXE')
    output.mkdir(parents=True, exist_ok=False)
    project_path = output / 'snake.fdb'
    checks = []
    frames = []
    with Project.create(project_path, build / 'SNAKE.EXE') as p:
        analysis = p.analyze(max_instructions=6000)
        analysis_status = p.analysis_status()
        with p.debugger(emulator, build, version=1) as d:
            pid = d.rpc.process.pid
            def run(ms=180):
                result = d.run(guest_ms=ms, fast_forward=True, timeout_ms=10000)
                assert result['outcome'] == 'guest_time', result
            def state():
                base = int(address('snake_cells'), 16)
                end = int(address('turn_queued'), 16) + 2
                raw = bytes.fromhex(d.memory(hex(base), length=end - base)['hex'])
                result = {name: struct.unpack_from('<H', raw, int(address(name), 16) - base)[0] for name in SCALARS}
                result['cells'] = list(struct.unpack_from('<' + 'H' * result['snake_length'], raw))
                return result
            def check(name, **want):
                actual = state()
                assert {key: actual[key] for key in want} == want, (name, want, actual)
                checks.append(dict(name=name, passed=True, expected=want, observed=actual))
                print(name, 'passed', flush=True)
                return actual
            def press(key):
                receipt = d.keyboard_press(key, hold_ms=25, gap_ms=25)
                assert receipt
                run()
            def click(x, y):
                frame = d.screenshot('click-context.png')
                receipt = d.click(x, y, hold_ms=50, mode_id=frame['metadata']['mode_id'])
                assert receipt
                run()
            def capture(name):
                frame = d.screenshot(name + '.png')
                p.debug_export(frame['artifact'], output / (name + '.png'))
                frames.append(frame)
            run(300)
            check('startup-paused', cells=[308, 307, 306], paused=1, tick_count=0,
                  score=0, snake_length=3, food_cell=312, rng_seed=4660, game_status=0, frame_count=1)
            capture('initial')
            vram = base64.b64decode(d.call('memory.read', {'address': {'space': 'linear', 'offset': '0x000A0000'}, 'length': 64000})['data_base64'])
            for x, y, color in ((72, 104, 10), (64, 104, 2), (56, 104, 2), (104, 104, 12), (6, 22, 8), (8, 24, 0)):
                assert vram[y * 320 + x] == color, (x, y, color, vram[y * 320 + x])
            checks.append(dict(name='real-vga-framebuffer', passed=True, witnesses=6))
            before = state()
            run(600)
            assert state() == before
            checks.append(dict(name='paused-clock-does-not-advance', passed=True))
            press('left')
            check('keyboard-reverse-rejected', pending_direction=1, turn_queued=0, tick_count=0)
            press('up')
            check('keyboard-up-queued', pending_direction=0, turn_queued=1, cells=[308, 307, 306])
            press('down')
            check('second-turn-before-step-rejected', pending_direction=0, turn_queued=1)
            press('n')
            check('keyboard-single-step', cells=[278, 308, 307], direction=0, pending_direction=0, tick_count=1, paused=1)
            for key, heading, cells in [('left', 3, [277, 278, 308]), ('down', 2, [307, 277, 278]), ('right', 1, [308, 307, 277])]:
                press(key)
                press('n')
                check('arrow-' + key, direction=heading, cells=cells)
            press('r')
            for key, heading, cells in [('w', 0, [278, 308, 307]), ('a', 3, [277, 278, 308]), ('s', 2, [307, 277, 278]), ('d', 1, [308, 307, 277])]:
                press(key)
                press('n')
                check('wasd-' + key, direction=heading, cells=cells)
            press('r')
            check('keyboard-reset-repeats-state', cells=[308, 307, 306], paused=1, score=0, tick_count=0, rng_seed=4660, frame_count=1)
            for _ in range(4):
                press('n')
            check('ordinary-play-eating', cells=[312, 311, 310, 309], snake_length=4, score=1, food_cell=389, rng_seed=10589, tick_count=4)
            capture('eaten')
            assert state()['mouse_present'] == 1, 'This acceptance requires an actual installed mouse driver'
            click(280, 178)
            check('mouse-reset', cells=[308, 307, 306], tick_count=0, paused=1, score=0, rng_seed=4660)
            for x, y, heading, cells in [(290, 50, 0, [278, 308, 307]), (268, 74, 3, [277, 278, 308]),
                                         (290, 98, 2, [307, 277, 278]), (300, 74, 1, [308, 307, 277])]:
                old = state()['mouse_events']
                click(x, y)
                check('mouse-direction-' + str(heading), pending_direction=heading, mouse_events=old + 1)
                click(280, 154)
                check('mouse-step-' + str(heading), cells=cells, direction=heading, paused=1)
            capture('mouse-controls')
            click(280, 130)
            running = check('mouse-unpause', paused=0)
            run(350)
            assert state()['tick_count'] > running['tick_count']
            checks.append(dict(name='clock-advances-running-game', passed=True))
            press('p')
            check('keyboard-pause', paused=1)
            click(280, 178)
            for _ in range(22):
                press('n')
            check('ordinary-wall-collision', game_status=1, paused=1, snake_length=4, cells=[329, 328, 327, 326], tick_count=22, score=1)
            frozen = state()
            press('n')
            after = state()
            assert all(after[k] == frozen[k] for k in (*('cells', 'snake_length', 'tick_count', 'game_status', 'score', 'rng_seed'),))
            checks.append(dict(name='terminal-input-does-not-step', passed=True))
            capture('dead')
            press('r')
            check('restart-after-death', game_status=0, paused=1, cells=[308, 307, 306], score=0)
            press('space')
            check('space-unpause', paused=0)
            press('space')
            check('space-pause', paused=1)
            raw_exe = (build / 'SNAKE.EXE').read_bytes()
            module_start = struct.unpack_from('<H', raw_exe, 8)[0] * 16
            module = raw_exe[module_start:]
            exit_bytes = bytes.fromhex('b80300cd10b8004ccd21')
            assert module.count(exit_bytes) == 1
            # Observe restored video mode before DOS_Terminate revokes access.
            before_terminate = hex(0x10000 + module.index(exit_bytes) + 5)
            bp = d.breakpoint(before_terminate)
            d.keyboard_press('escape', hold_ms=25, gap_ms=25)
            stopped = d.run(fast_forward=True, timeout_ms=10000)
            assert stopped['outcome'] == 'breakpoint', stopped
            mode = d.call('memory.read', {'address': {'space': 'linear', 'offset': '0x00000449'}, 'length': 1})
            assert base64.b64decode(mode['data_base64']) == b'\x03'
            d.delete_breakpoint(bp['breakpoint_id'])
            exit_result = d.run(guest_ms=200, fast_forward=True, timeout_ms=10000)
            assert exit_result['outcome'] == 'guest_exit', exit_result
            assert exit_result['session']['state'] == 'exited'
            assert exit_result['stop']['guest_exit']['requested_exit_code'] == 0
            checks.append(dict(name='escape-restores-text-and-exits', passed=True))
        assert d.rpc.process.poll() is not None
    with Project(project_path) as p:
        assert p.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        p.debug_export(frames[0]['artifact'], output / 'initial-after-reopen.png')
        assert (output / 'initial.png').read_bytes() == (output / 'initial-after-reopen.png').read_bytes()
        checks.append(dict(name='database-reopen-and-stored-frame-export', passed=True))
    assert sha(build / 'SNAKE.EXE') == original
    return dict(format='fdisbull-snake-native-validation-1', executable_sha256=original,
                fdisbull_version=__version__, backend=str(emulator), backend_sha256=sha(emulator),
                process_pid=pid, process_reaped=True, analysis=analysis, analysis_status=analysis_status,
                checks=checks, frames=frames, source_and_state_maps='oracle-assisted',
                scope='Actual VGA/keyboard/mouse/timer paths of the authored DOS original; no conversion qualification')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('pure', 'native'))
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--unicorn-site', type=Path)
    parser.add_argument('--vectors', type=Path, default=Path(__file__).with_name('vectors.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--backend', type=Path)
    a = parser.parse_args()
    assert not a.report.exists(), 'Report must be new'
    result = pure(a.build, a.vectors, a.unicorn_site) if a.phase == 'pure' else native(a.build, a.output, a.backend)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'checks': len(result.get('checks', result.get('cases', []))), 'report': str(a.report)}))
