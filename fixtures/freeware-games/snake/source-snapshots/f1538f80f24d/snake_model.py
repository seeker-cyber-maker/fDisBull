"""Source-assisted Snake recovery into the reusable bounded-memory UIL.

The profile contains no Snake operations. All game, input and raster semantics
below are explicit arithmetic/load/store/branch/loop nodes. Original executable,
font bytes, projects and generated UDL/UIL stay in the private study directory.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

WORDS = 70000
FONT = 1024
FRAME = 4096
SCALARS = ('snake_length', 'direction', 'pending_direction', 'paused', 'game_status',
           'score', 'rng_seed', 'tick_count', 'key_events', 'mouse_events',
           'frame_count', 'mouse_present', 'food_cell', 'turn_queued')
STATE = {name: 600 + i for i, name in enumerate(SCALARS)}
STATE.update(needs_render=614, step_requested=615, quit_requested=616,
             mouse_buttons=617, mouse_x=618, mouse_y=619, last_tick=620)
INPUT = {'kind': 630, 'ascii': 631, 'scan': 632, 'x': 633,
         'y': 634, 'buttons': 635, 'clock': 636}
TEXTS = {'title': 'SNAKE v1  SCORE ', 'paused': 'PAUSED ', 'running': 'RUNNING',
         'dead': 'DEAD   ', 'won': 'WON    ',
         'controls': 'Arrows/WASD  P:pause N:step R:reset Esc',
         'up': 'UP', 'left': 'L', 'right': 'R', 'down': 'DN',
         'pause': 'PAUSE', 'step': 'STEP', 'reset': 'RESET',
         'mouse': 'MOUSE', 'nomouse': 'KEYS '}
TEXT_LAYOUT = {}
_at = 3072
for _key, _text in TEXTS.items():
    TEXT_LAYOUT[_key] = (_at, len(_text))
    _at += len(_text)


def v(name): return {'var': '$' + name}
def ld(index): return {'load': index}
def get(name): return ld(STATE[name])
def inp(name): return ld(INPUT[name])
def ex(op, left, right): return {'op': op, 'left': left, 'right': right}
def add(a, b): return ex('add', a, b)
def sub(a, b): return ex('sub', a, b)
def eq(a, b): return ex('eq', a, b)
def ne(a, b): return ex('ne', a, b)
def lt(a, b): return ex('lt', a, b)
def ge(a, b): return ex('ge', a, b)
def both(a, b): return ex('and', a, b)
def either(a, b): return ex('or', a, b)
def u16(a): return ex('and', a, 65535)
def set_(name, value): return {'op': 'set', 'var': '$' + name, 'value': value}
def put(index, value): return {'op': 'store', 'index': index, 'value': value}
def write(name, value): return put(STATE[name], u16(value))
def inc(name): return write(name, add(get(name), 1))
def iff(condition, yes, no=()): return {'op': 'if', 'condition': condition, 'then': list(yes), 'else': list(no)}
def loop(condition, body, limit): return {'op': 'while', 'condition': condition, 'body': list(body), 'limit': limit}


def reset_body():
    result = [set_('i', 0), loop(lt(v('i'), 600), [put(v('i'), 0), set_('i', add(v('i'), 1))], 600)]
    result += [put(0, 308), put(1, 307), put(2, 306)]
    values = dict(snake_length=3, direction=1, pending_direction=1, paused=1,
                  game_status=0, score=0, rng_seed=4660, food_cell=312,
                  tick_count=0, key_events=0, mouse_events=0, frame_count=0,
                  turn_queued=0, step_requested=0, needs_render=1)
    result += [write(name, value) for name, value in values.items()]
    return result


def step_body():
    dead = [write('game_status', 1), write('paused', 1)]
    search = [write('rng_seed', u16(add(ex('mul', get('rng_seed'), 25173), 13849))),
              set_('candidate', ex('mod', get('rng_seed'), 600)), set_('found', 0), set_('tries', 0),
              loop(both(eq(v('found'), 0), lt(v('tries'), 600)), [
                  set_('occupied', 0), set_('j', 0),
                  loop(both(lt(v('j'), get('snake_length')), eq(v('occupied'), 0)), [
                      iff(eq(v('candidate'), ld(v('j'))), [set_('occupied', 1)]),
                      set_('j', add(v('j'), 1))], 600),
                  iff(eq(v('occupied'), 0), [write('food_cell', v('candidate')), set_('found', 1)],
                      [set_('candidate', ex('mod', add(v('candidate'), 1), 600))]),
                  set_('tries', add(v('tries'), 1))], 600),
              iff(eq(v('found'), 0), [write('game_status', 2), write('paused', 1), write('food_cell', 65535)])]
    safe = [iff(v('growing'), [inc('snake_length'), inc('score')]),
            set_('i', sub(get('snake_length'), 1)),
            loop(ne(v('i'), 0), [put(v('i'), ld(sub(v('i'), 1))), set_('i', sub(v('i'), 1))], 599),
            put(0, v('next')),
            iff(v('growing'), [iff(eq(get('snake_length'), 600),
                [write('game_status', 2), write('paused', 1), write('food_cell', 65535)], search)])]
    inside = [set_('next', add(ex('mul', v('y'), 30), v('x'))),
              set_('growing', eq(v('next'), get('food_cell'))),
              set_('n', sub(get('snake_length'), ex('sub', 1, v('growing')))),
              set_('i', 0), set_('collision', 0),
              loop(both(lt(v('i'), v('n')), eq(v('collision'), 0)), [
                  iff(eq(v('next'), ld(v('i'))), [set_('collision', 1)]),
                  set_('i', add(v('i'), 1))], 600),
              iff(v('collision'), dead, safe)]
    active = [inc('tick_count'),
              iff(ne(get('pending_direction'), ex('and', add(get('direction'), 2), 3)),
                  [write('direction', get('pending_direction'))]),
              write('pending_direction', get('direction')), write('turn_queued', 0),
              set_('x', ex('mod', ld(0), 30)), set_('y', ex('div', ld(0), 30)),
              iff(eq(get('direction'), 0), [set_('y', sub(v('y'), 1))], [
                  iff(eq(get('direction'), 1), [set_('x', add(v('x'), 1))], [
                      iff(eq(get('direction'), 2), [set_('y', add(v('y'), 1))], [set_('x', sub(v('x'), 1))])])]),
              iff(either(ge(v('x'), 30), ge(v('y'), 20)), dead, inside)]
    return [iff(eq(get('game_status'), 0), active)]


def queue_body(direction):
    return [iff(both(both(eq(get('game_status'), 0), eq(get('turn_queued'), 0)),
                     both(ne(direction, get('direction')), ne(direction, ex('and', add(get('direction'), 2), 3)))),
                [write('pending_direction', direction), write('turn_queued', 1), write('needs_render', 1)])]


def action_body():
    # cmd: 0 no action, 1..4 directions(up/right/down/left), 5pause,6step,7reset,8quit.
    def command_when(condition, command): return iff(condition, [set_('command', command)])
    # Match the original first-match order even for contradictory ASCII/scan pairs.
    choices = [(eq(v('ascii'), 27), 8), (eq(v('ascii'), 32), 5),
               (eq(v('ascii'), 112), 5), (eq(v('ascii'), 110), 6), (eq(v('ascii'), 114), 7),
               (either(eq(v('ascii'), 119), eq(inp('scan'), 72)), 1),
               (either(eq(v('ascii'), 100), eq(inp('scan'), 77)), 2),
               (either(eq(v('ascii'), 115), eq(inp('scan'), 80)), 3),
               (either(eq(v('ascii'), 97), eq(inp('scan'), 75)), 4)]
    dispatch_key = []
    for condition, command in reversed(choices):
        dispatch_key = [iff(condition, [set_('command', command)], dispatch_key)]
    keyboard = [inc('key_events'), set_('ascii', inp('ascii')),
                iff(both(ge(v('ascii'), 65), ex('le', v('ascii'), 90)), [set_('ascii', add(v('ascii'), 32))]),
                *dispatch_key]
    def box(x0, x1, y0, y1, cmd):
        return command_when(both(both(ge(inp('x'), x0), lt(inp('x'), x1)),
                                 both(ge(inp('y'), y0), lt(inp('y'), y1))), cmd)
    pointer = [set_('old_buttons', get('mouse_buttons')),
               write('mouse_buttons', inp('buttons')), write('mouse_x', inp('x')), write('mouse_y', inp('y')),
               iff(both(ne(ex('and', inp('buttons'), 1), 0), eq(ex('and', v('old_buttons'), 1), 0)), [
                   inc('mouse_events'),
                   box(280, 304, 40, 60, 1), box(256, 280, 64, 84, 4),
                   box(288, 312, 64, 84, 2), box(280, 304, 88, 108, 3),
                   box(256, 312, 120, 140, 5), box(256, 312, 144, 164, 6),
                   box(256, 312, 168, 188, 7)])]
    dispatch = [iff(both(ge(v('command'), 1), ex('le', v('command'), 4)), queue_body(sub(v('command'), 1))),
                iff(both(eq(v('command'), 5), eq(get('game_status'), 0)), [
                    write('paused', ex('xor', get('paused'), 1)), write('needs_render', 1), write('last_tick', inp('clock'))]),
                iff(both(both(eq(v('command'), 6), eq(get('game_status'), 0)), eq(get('paused'), 1)), [write('step_requested', 1)]),
                iff(eq(v('command'), 7), [*reset_body(), write('last_tick', inp('clock'))]),
                iff(eq(v('command'), 8), [write('quit_requested', 1)])]
    schedule = [iff(ne(get('step_requested'), 0), [
                    write('step_requested', 0),
                    iff(eq(get('paused'), 1), [*step_body(), write('needs_render', 1), write('last_tick', inp('clock'))])], [
                    iff(both(both(eq(get('paused'), 0), eq(get('game_status'), 0)),
                             ge(u16(sub(inp('clock'), get('last_tick'))), 4)),
                        [*step_body(), write('needs_render', 1), write('last_tick', inp('clock'))])])]
    return [set_('command', 0), iff(eq(inp('kind'), 1), keyboard),
            iff(both(eq(inp('kind'), 2), ne(get('mouse_present'), 0)), pointer),
            *dispatch, iff(eq(get('quit_requested'), 0), schedule)]


def rectangle(x, y, width, height, color):
    return [set_('rx', x), set_('ry', y), set_('rw', width), set_('rh', height), set_('color', color),
            set_('row', 0), loop(lt(v('row'), v('rh')), [
                set_('column', 0), loop(lt(v('column'), v('rw')), [
                    put(add(FRAME, add(ex('mul', add(v('ry'), v('row')), 320), add(v('rx'), v('column')))), v('color')),
                    set_('column', add(v('column'), 1))], 320),
                set_('row', add(v('row'), 1))], 200)]


def cell_draw(cell, color):
    return rectangle(add(8, ex('mul', ex('mod', cell, 30), 8)),
                     add(24, ex('mul', ex('div', cell, 30), 8)), 7, 7, color)


def text_draw(ptr, length, x, y):
    return [set_('text_ptr', ptr), set_('text_length', length), set_('text_x', x), set_('text_y', y),
            set_('ti', 0), loop(lt(v('ti'), v('text_length')), [
                set_('char', ld(add(v('text_ptr'), v('ti')))), set_('gy', 0),
                loop(lt(v('gy'), 8), [
                    set_('bits', ld(add(FONT, add(ex('mul', v('char'), 8), v('gy'))))), set_('gx', 0),
                    loop(lt(v('gx'), 8), [
                        set_('ink', ex('and', ex('shr', v('bits'), sub(7, v('gx'))), 1)),
                        put(add(FRAME, add(ex('mul', add(v('text_y'), v('gy')), 320),
                                          add(v('text_x'), add(ex('mul', v('ti'), 8), v('gx'))))),
                            ex('mul', v('ink'), 15)),
                        set_('gx', add(v('gx'), 1))], 8),
                    set_('gy', add(v('gy'), 1))], 8),
                set_('ti', add(v('ti'), 1))], 80)]


def fixed_text(name, x, y):
    ptr, length = TEXT_LAYOUT[name]
    return text_draw(ptr, length, x, y)


def render_body():
    # Color-index projection of the original A000 framebuffer, excluding driver cursor.
    result = [set_('pixel', 0), loop(lt(v('pixel'), 64000), [
        put(add(FRAME, v('pixel')), 0), set_('pixel', add(v('pixel'), 1))], 64000)]
    result += rectangle(6, 22, 244, 164, 8) + rectangle(8, 24, 240, 160, 0)
    result += [set_('segment', 0), loop(lt(v('segment'), get('snake_length')), [
        *cell_draw(ld(v('segment')), 2), set_('segment', add(v('segment'), 1))], 600)]
    result += cell_draw(ld(0), 10)
    result += [iff(lt(get('food_cell'), 600), cell_draw(get('food_cell'), 12))]
    for x, y, width in [(280, 40, 24), (256, 64, 24), (288, 64, 24),
                         (280, 88, 24), (256, 120, 56), (256, 144, 56), (256, 168, 56)]:
        result += rectangle(x, y, width, 20, 1)
    result += fixed_text('title', 0, 0)
    # Decimal BIOS text output: scratch digit cells are model temporaries, not game state.
    result += [set_('number', get('score')), set_('digits', 0),
               loop(either(ne(v('number'), 0), eq(v('digits'), 0)), [
                   put(add(760, v('digits')), add(48, ex('mod', v('number'), 10))),
                   set_('digits', add(v('digits'), 1)), set_('number', ex('div', v('number'), 10))], 5),
               set_('digit_index', 0), loop(lt(v('digit_index'), v('digits')), [
                   put(add(768, v('digit_index')), ld(add(760, sub(sub(v('digits'), 1), v('digit_index'))))),
                   set_('digit_index', add(v('digit_index'), 1))], 5)]
    result += text_draw(768, v('digits'), len(TEXTS['title']) * 8, 0)
    result += [iff(eq(get('game_status'), 1), fixed_text('dead', 0, 8), [
        iff(eq(get('game_status'), 2), fixed_text('won', 0, 8), [
            iff(eq(get('paused'), 0), fixed_text('running', 0, 8), fixed_text('paused', 0, 8))])])]
    result += [iff(eq(get('mouse_present'), 0), fixed_text('nomouse', 256, 8), fixed_text('mouse', 256, 8))]
    for name, x, y in [('up', 280, 40), ('left', 256, 64), ('right', 288, 64),
                        ('down', 280, 88), ('pause', 256, 120), ('step', 256, 144),
                        ('reset', 256, 168), ('controls', 0, 192)]:
        result += fixed_text(name, x, y)
    result += [inc('frame_count'), write('needs_render', 0)]
    return result


def make_program(role='uil'):
    functions = {name: {'body': body, 'max_steps': 4000000} for name, body in
                 [('step', step_body()), ('reset', reset_body()), ('action', action_body()), ('render', render_body())]}
    # Expanded helper uses are distinct program nodes, even when builder objects alias.
    functions = json.loads(json.dumps(functions))
    spans = {'step': [[0x176, 0x2f6]], 'reset': [[0xf1, 0x176]],
             'action': [[0, 0xf1], [0x2f6, 0x516]], 'render': [[0x516, 0x7a0]]}
    evidence = {'recovery': {'method': 'source-assisted, matching original MZ and period LINK map',
                            'original_sha256': 'f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be',
                            'flags': 'arithmetic FLAGS clobbered; not a logical result',
                            'graphics': 'indexed A000 pixels with the observed ROM font; driver cursor excluded'}}
    for name, function in functions.items():
        evidence['source_' + name] = {'code_module_spans': spans[name],
            'project_base': 0x10000, 'file_module_base': 512,
            'boundary': 'logical projection; shell spans include separately adapted BIOS/DOS services'}
        serial = [0]
        def annotate(nodes):
            for node in nodes:
                serial[0] += 1
                node['id'] = name + '.' + str(serial[0])
                node['evidence'] = ['source_' + name]
                for key in ('body', 'then', 'else'):
                    if isinstance(node.get(key), list): annotate(node[key])
        annotate(function['body'])
    variables = set()
    def visit(node):
        if isinstance(node, dict):
            if 'var' in node: variables.add(node['var'])
            for value in node.values(): visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    for function in functions.values(): visit(function)
    # Shared document roles retain identical semantic nodes; source details stay in evidence.
    return {'format': 'fdisbull-memory-uil-1', 'role': role, 'memory': {'words': WORDS},
            'variables': {name: {'type': 'u32', 'initial': 0} for name in sorted(variables)},
            'functions': functions, 'evidence': evidence}


def initial_words(font):
    if len(font) != 2048: raise ValueError('original font must contain 256 eight-byte glyphs')
    words = [0] * WORDS
    words[FONT:FONT + 2048] = list(font)
    for key, (ptr, length) in TEXT_LAYOUT.items(): words[ptr:ptr + length] = list(TEXTS[key].encode('ascii'))
    words[STATE['mouse_present']] = 1
    return words


def pack_state(state, words=None):
    result = [0] * WORDS if words is None else list(words)
    cells = state['all_cells'] if 'all_cells' in state else state['cells']
    if len(cells) > 600: raise ValueError('Snake adapter admits at most 600 cells')
    result[:600] = list(cells) + [0] * (600 - len(cells))
    for name in STATE:
        if name in state: result[STATE[name]] = state[name]
    return result


def core_state(words, *, include_shell=False, all_cells=False):
    names = STATE if include_shell else SCALARS
    result = {name: int(words[STATE[name]]) for name in names}
    result['cells'] = list(words[:result['snake_length']])
    if all_cells: result['all_cells'] = list(words[:600])
    return result


def _original_call(executable, map_path, state):
    import unicorn as u
    from unicorn import x86_const as r
    raw = executable.read_bytes(); h = struct.unpack_from('<14H', raw)
    end = h[2] * 512 - ((512 - h[1]) % 512)
    module = bytearray(raw[h[4] * 16:end])
    for n in range(h[3]):
        off, seg = struct.unpack_from('<HH', raw, h[12] + n * 4)
        index = seg * 16 + off
        struct.pack_into('<H', module, index, (struct.unpack_from('<H', module, index)[0] + 0x1000) & 65535)
    symbols = {name.lower(): (int(s, 16), int(o, 16)) for s, o, name in
               re.findall(r'^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+(\w+)\s*$', map_path.read_text(), re.M)}
    addr = lambda name: 0x10000 + symbols[name][0] * 16 + symbols[name][1]
    cpu = u.Uc(u.UC_ARCH_X86, u.UC_MODE_16); cpu.mem_map(0, 0x100000); cpu.mem_write(0x10000, bytes(module))
    cells = state['all_cells'] if 'all_cells' in state else state['cells']
    cpu.mem_write(addr('snake_cells'), struct.pack('<600H', *(list(cells) + [0] * (600 - len(cells)))))
    for name in SCALARS:
        if name in state: cpu.mem_write(addr(name), struct.pack('<H', state[name]))
    for name, value in [('CS', 0x1000 + symbols['snake_step'][0]), ('DS', 0x1000 + symbols['snake_cells'][0]),
                         ('ES', 0x9000), ('SS', 0x7000), ('SP', 0xfff0)]: cpu.reg_write(getattr(r, 'UC_X86_REG_' + name), value)
    cpu.mem_write(0x7fff0, struct.pack('<H', 0xff00))
    interrupts = []
    def interrupt(uc, number, _): interrupts.append(number); uc.emu_stop()
    cpu.hook_add(u.UC_HOOK_INTR, interrupt)
    cpu.emu_start(addr('snake_step'), (0x1000 + symbols['snake_step'][0]) * 16 + 0xff00, count=3000000)
    assert not interrupts and cpu.reg_read(r.UC_X86_REG_IP) == 0xff00
    result = {name: struct.unpack('<H', bytes(cpu.mem_read(addr(name), 2)))[0] for name in SCALARS}
    result['all_cells'] = list(struct.unpack('<600H', bytes(cpu.mem_read(addr('snake_cells'), 1200))))
    result['cells'] = result['all_cells'][:result['snake_length']]
    return result


def prepare(executable, map_path, vectors, output, *, font=None):
    from fdisbull.udc_web_memory import validate_memory_uil, execute_memory_uil, digest
    executable, map_path, vectors, output = [Path(p).resolve() for p in (executable, map_path, vectors, output)]
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        raise ValueError('choose a new private model output outside Git')
    raw = executable.read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    assert sha(raw) == 'f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be'
    program = make_program(); validate_memory_uil(program)
    udl = deepcopy(program); udl['role'] = 'udl'; validate_memory_uil(udl)
    assert udl['functions'] == program['functions']
    output.mkdir(parents=True)
    (output / 'snake.uil.json').write_text(json.dumps(program, indent=2) + '\n')
    (output / 'snake.udl.json').write_text(json.dumps(udl, indent=2) + '\n')
    cases = json.loads(vectors.read_text())['cases']
    # Unspecified adapter words come from the original file's initialized data,
    # never from an expected post-state or the model's result.
    original_symbols = {name.lower(): (int(s, 16), int(o, 16)) for s, o, name in
                        re.findall(r'^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+(\w+)\s*$', map_path.read_text(), re.M)}
    module_start = struct.unpack_from('<H', raw, 8)[0] * 16
    defaults = {name: struct.unpack_from('<H', raw,
                 module_start + original_symbols[name][0] * 16 + original_symbols[name][1])[0]
                for name in SCALARS}
    # Add word-wrap, seed and edge cases independently of the model's outputs.
    initial = dict(cells=[308, 307, 306], snake_length=3, direction=1, pending_direction=1,
                   paused=1, game_status=0, score=0, rng_seed=4660, tick_count=0,
                   key_events=0, mouse_events=0, frame_count=0, mouse_present=1,
                   food_cell=312, turn_queued=0)
    for y in range(20):
        for x in (2, 8, 28, 29):
            for direction in range(4):
                state = dict(initial, cells=[y * 30 + x, y * 30 + x - 1, y * 30 + x - 2],
                             pending_direction=direction, tick_count=65535, food_cell=(y * 30 + x + 30) % 600)
                if state['food_cell'] in state['cells']: state['food_cell'] = (state['food_cell'] + 1) % 600
                cases.append({'id': f'edge-{x}-{y}-{direction}', 'initial': state})
    for seed in (0, 1, 65535, 32768, 4660):
        cases.append({'id': f'eat-seed-{seed}', 'initial': dict(initial, food_cell=309, rng_seed=seed, score=65535, tick_count=65535)})
    rows = []
    mismatches = []
    for case in cases:
        normalized = dict(defaults, **case['initial'])
        before = pack_state(normalized)
        original = _original_call(executable, map_path, normalized)
        modeled = execute_memory_uil(program, 'step', before)
        assert modeled['status'] == 'complete', modeled
        got = core_state(modeled['words'], all_cells=True)
        if got != original: mismatches.append({'id': case['id'], 'original': original, 'uil': got})
        rows.append({'id': case['id'], 'initial': normalized, 'original': original})
    assert not mismatches, mismatches[:1]
    # A wrong model must fail the original comparison, even when both targets share it.
    mutant = deepcopy(program)
    def mutate(nodes):
        for node in nodes:
            if node.get('op') == 'store' and node.get('index') == STATE['tick_count']:
                node['value'] = u16(add(get('tick_count'), 2)); return True
            for key in ('body', 'then', 'else'):
                if isinstance(node.get(key), list) and mutate(node[key]): return True
        return False
    assert mutate(mutant['functions']['step']['body'])
    negative = execute_memory_uil(mutant, 'step', pack_state(rows[0]['initial']))
    assert negative['words'][STATE['tick_count']] != rows[0]['original']['tick_count']
    (output / 'original-cases.json').write_text(json.dumps({'cases': rows}, indent=2) + '\n')
    manifest = {'format': 'fdisbull-snake-memory-recovery-1', 'method': 'source-assisted known-source fixture',
                'original_sha256': sha(raw), 'map_sha256': sha(map_path.read_bytes()),
                'uil_sha256': digest(program), 'udl_sha256': digest(udl), 'cases': len(rows),
                'original_to_uil_mismatches': len(mismatches), 'negative_control_detected': True,
                'layout': {'words': WORDS, 'state': STATE, 'inputs': INPUT, 'font': FONT, 'frame': FRAME},
                'domain': 'Valid unique contiguous active snake prefix; direction enums0..3; typed u16 counters; original step preconditions',
                'scope': 'Compiled original step -> explicit bounded-memory UIL on finite constructed cases; graphics/input qualification separate'}
    if font is not None:
        font = Path(font).read_bytes()
        words = initial_words(font)
        reset = execute_memory_uil(program, 'reset', words); assert reset['status'] == 'complete'
        rendered = execute_memory_uil(program, 'render', reset['words']); assert rendered['status'] == 'complete'
        (output / 'initial-words.json').write_text(json.dumps(reset['words']) + '\n')
        (output / 'initial-frame.bin').write_bytes(bytes(rendered['words'][FRAME:FRAME + 64000]))
        manifest['font_sha256'] = sha(font)
        manifest['initial_frame_sha256'] = sha((output / 'initial-frame.bin').read_bytes())
    (output / 'recovery.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def qualify_native(originals_path, report_path):
    """Compare original input transitions and complete cursor-free indexed rasters.

    Every transition starts from that original observation's declared before
    state. A separate carried-state browser test is still required by the shell.
    """
    from fdisbull.udc_web_memory import execute_memory_uil, digest
    originals_path, report_path = Path(originals_path).resolve(), Path(report_path).resolve()
    if report_path.exists(): raise ValueError('native comparison report must be new')
    root = originals_path.parent
    original = json.loads(originals_path.read_text())
    font = (root / original['assets']['font']['file']).read_bytes()
    program = make_program()
    rows = []
    mismatches = []
    for row in original['observations']:
        target = row['after']
        if row['before'] is not None:
            words = initial_words(font)
            words[:621] = row['before']['memory_words']
            for event in row['replay']:
                for index in INPUT.values(): words[index] = 0
                words[INPUT['kind']] = {'key': 1, 'pointer': 2, 'clock': 0}[event['kind']]
                for key in ('ascii', 'scan', 'x', 'y', 'buttons'):
                    words[INPUT[key]] = event.get(key, 0)
                words[INPUT['clock']] = event['clock_low16']
                computed = execute_memory_uil(program, 'action', words)
                assert computed['status'] == 'complete'
                words = computed['words']
                if words[STATE['needs_render']]:
                    computed = execute_memory_uil(program, 'render', words)
                    assert computed['status'] == 'complete'
                    words = computed['words']
            differences = [{'index': i, 'uil': a, 'original': b}
                           for i, (a, b) in enumerate(zip(words[:621], target['memory_words'])) if a != b]
            if differences: mismatches.append({'id': row['id'], 'kind': 'state', 'differences': differences})
        words = initial_words(font); words[:621] = target['memory_words']
        rendered = execute_memory_uil(program, 'render', words)
        assert rendered['status'] == 'complete'
        raster = bytes(rendered['words'][FRAME:FRAME + 64000])
        expected = (root / row['frame']['file']).read_bytes()
        differences = [i for i, (a, b) in enumerate(zip(raster, expected)) if a != b]
        if differences:
            mismatches.append({'id': row['id'], 'kind': 'raster', 'count': len(differences),
                               'first': differences[:10]})
        rows.append({'id': row['id'], 'transition_compared': row['before'] is not None,
                     'raster_pixels': 64000, 'raster_difference_bytes': len(differences),
                     'original_raster_sha256': hashlib.sha256(expected).hexdigest(),
                     'uil_raster_sha256': hashlib.sha256(raster).hexdigest(),
                     'diagnostic': bool(row.get('intervention'))})
    report = {'format': 'fdisbull-snake-native-to-uil-1',
              'originals_sha256': hashlib.sha256(originals_path.read_bytes()).hexdigest(),
              'uil_sha256': digest(program), 'observations': rows, 'mismatches': mismatches,
              'scope': 'Per-observation normalized input/complete state and full indexed-frame comparison; cursor service excluded; original states retained as inputs; no carried-state claim'}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    return report


def verify_originals(originals_path, report_path, study_path=None, cases_path=None):
    """Verify the carried original input sequence without per-call answer resets."""
    from fdisbull.udc_web_memory import execute_memory_uil, digest
    originals_path, report_path = Path(originals_path).resolve(), Path(report_path).resolve()
    if report_path.exists(): raise ValueError('original sequence report must be new')
    root = originals_path.parent
    original = json.loads(originals_path.read_text())
    program = make_program()
    font = (root / original['assets']['font']['file']).read_bytes()
    first = original['observations'][0]
    services = {name: first['after'][name] for name in ('mouse_present', 'mouse_x', 'mouse_y', 'last_tick')}
    words = initial_words(font)
    for name, value in services.items(): words[STATE[name]] = value
    words = execute_memory_uil(program, 'reset', words)['words']
    words = execute_memory_uil(program, 'render', words)['words']
    rows, mismatches, study_rows = [], [], []
    for number, row in enumerate(original['observations']):
        intervention = row.get('intervention')
        if intervention:
            assert intervention['ordinary_reachability'] is False
            words[:621] = row['before']['memory_words']
        if row['before'] is not None:
            difference = [i for i, (a, b) in enumerate(zip(words[:621], row['before']['memory_words'])) if a != b]
            if difference: mismatches.append({'id': row['id'], 'boundary': 'carried-before', 'indices': difference[:10]})
        events = []
        for event in row['replay']:
            converted = {key: event.get(key, 0) for key in ('ascii', 'scan', 'x', 'y', 'buttons')}
            converted['kind'] = {'key': 1, 'pointer': 2, 'clock': 0}[event['kind']]
            converted['clock'] = event['clock_low16']
            events.append(converted)
            for name, index in INPUT.items(): words[index] = converted[name]
            computed = execute_memory_uil(program, 'action', words)
            assert computed['status'] == 'complete', (row['id'], computed.get('error'))
            words = computed['words']
            if words[STATE['needs_render']]:
                computed = execute_memory_uil(program, 'render', words)
                assert computed['status'] == 'complete', (row['id'], computed.get('error'))
                words = computed['words']
        state_difference = [{'index': i, 'uil': a, 'original': b}
                            for i, (a, b) in enumerate(zip(words[:621], row['after']['memory_words'])) if a != b]
        if state_difference: mismatches.append({'id': row['id'], 'boundary': 'after', 'differences': state_difference[:10]})
        raster = bytes(words[FRAME:FRAME + 64000])
        expected = (root / row['frame']['file']).read_bytes()
        raster_difference = [i for i, (a, b) in enumerate(zip(raster, expected)) if a != b]
        if raster_difference: mismatches.append({'id': row['id'], 'boundary': 'frame', 'count': len(raster_difference), 'indices': raster_difference[:10]})
        rows.append({'id': row['id'], 'state_words_compared': 621, 'state_difference_words': len(state_difference),
                     'raster_pixels_compared': 64000, 'raster_difference_bytes': len(raster_difference),
                     'original_raster_sha256': hashlib.sha256(expected).hexdigest(),
                     'uil_raster_sha256': hashlib.sha256(raster).hexdigest(),
                     'declared_diagnostic_intervention': bool(intervention)})
        study_rows.append({'id': row['id'], 'events': events,
                           'intervention': {'kind': 'declared-original-ram-state', 'words': row['before']['memory_words'],
                                            'ordinary_reachability': False} if intervention else None,
                           'expected_state': row['after']['memory_words'],
                           'frame': row['frame']})
    report = {'format': 'fdisbull-snake-carried-original-to-uil-1',
              'uil_sha256': digest(program), 'originals_sha256': hashlib.sha256(originals_path.read_bytes()).hexdigest(),
              'status': 'finite_match' if not mismatches else 'mismatch',
              'initialization': {'game': 'UIL reset; no original game-state answer copied',
                                 'services': services, 'font': 'observed live ROM font'},
              'observations': rows, 'mismatches': mismatches,
              'newly_rendered_original_frames': sum(row['frame']['newly_rendered'] for row in original['observations']),
              'scope': 'One carried-state input sequence initialized once; source-assisted; one explicit diagnostic RAM intervention; full621-word state and64000 indexed pixels at every observation; no game-state answer resets between ordinary calls'}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    if study_path is not None:
        study_path = Path(study_path)
        if study_path.exists(): raise ValueError('browser study must be new')
        payload = {'format': 'fdisbull-snake-original-replay-1',
            'uil_sha256': digest(program), 'originals_sha256': report['originals_sha256'],
            'initial_services': services, 'observations': study_rows,
            'layout': {'words': WORDS, 'state': STATE, 'inputs': INPUT, 'font': FONT, 'frame': FRAME},
            'raster_data': {row['frame']['sha256']: base64.b64encode((root / row['frame']['file']).read_bytes()).decode('ascii')
                            for row in original['observations']},
            'projection': 'indexed320x200frame; driver cursor excluded; original physical inputs normalized to BIOS/pointer values'}
        if cases_path is not None:
            cases_path = Path(cases_path)
            payload['cases'] = json.loads(cases_path.read_text())['cases']
            payload['cases_sha256'] = hashlib.sha256(cases_path.read_bytes()).hexdigest()
        study_path.write_text(json.dumps(payload, indent=2) + '\n')
    return report


if __name__ == '__main__':
    import argparse
    if len(sys.argv) > 1 and sys.argv[1] == 'verify-originals':
        parser = argparse.ArgumentParser(description=verify_originals.__doc__)
        parser.add_argument('originals', type=Path); parser.add_argument('report', type=Path)
        parser.add_argument('--study', type=Path); parser.add_argument('--cases', type=Path)
        a = parser.parse_args(sys.argv[2:])
        result = verify_originals(a.originals, a.report, a.study, a.cases)
        print(json.dumps({'status': result['status'], 'observations': len(result['observations']),
                          'mismatches': len(result['mismatches']), 'report': str(a.report)}))
        sys.exit(bool(result['mismatches']))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('executable', type=Path); parser.add_argument('map', type=Path)
        parser.add_argument('vectors', type=Path); parser.add_argument('output', type=Path)
        parser.add_argument('--font', type=Path)
        a = parser.parse_args()
        print(json.dumps(prepare(a.executable, a.map, a.vectors, a.output, font=a.font)))
