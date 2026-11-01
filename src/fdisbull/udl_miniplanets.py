"""Source-bound Stage 1-1 gameplay recovery for the official Miniplanets ROM.

This is a reviewed specialization of the game's native rules, not a general
68000 decompiler. ROM/data identity is checked before any model is produced.
The map and lookup data are read from the supplied ROM, never bundled here.

This altered implementation expresses its bounded gameplay as UIL, with an
authored terminal/reset shell and a separate flattened NES presentation.
"""
from __future__ import annotations

import hashlib

MINIPLANETS_LICENSE = "©2016, 2022 Javier Degirolmo\n\nThis software is provided 'as-is', without any express or implied warranty.\nIn no event will the authors be held liable for any damages arising from the\nuse of this software.\n\nPermission is granted to anyone to use this software for any purpose,\nincluding commercial applications, and to alter it and redistribute it\nfreely, subject to the following restrictions:\n\n1. The origin of this software must not be misrepresented; you must not\n   claim that you wrote the original software. If you use this software\n   in a product, an acknowledgment in the product documentation would be\n   appreciated but is not required.\n2. Altered source versions must be plainly marked as such, and must not be\n   misrepresented as being the original software.\n3. This notice may not be removed or altered from any source distribution."


ROM_SHA256 = 'e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7'
UPSTREAM_COMMIT = '0ac9c395289cc5d0837c96d45e61a27300e8eebc'
CODE_RANGES = {
    'update_subpixel': (0x02fe, 0x032e),
    'init_player': (0x43a4, 0x43dc), 'run_player': (0x43dc, 0x468a),
    'locomotion': (0x44de, 0x4566), 'get_tile': (0x3c8c, 0x3cae),
    'run_key': (0x4b90, 0x4c10), 'collides_player': (0x49a0, 0x49e2),
    'hurt_player_ex': (0x49e6, 0x4a26), 'win_stage': (0x3792, 0x37b4),
    'play_sfx_request': (0x7c8, 0x7de),
}
DATA_RANGES = {'map': (0x616e0, 0x617e0), 'object': (0x617e0, 0x617e5),
               'joy_angle': (0x468a, 0x469a), 'angle_distance': (0x65b88, 0x65b9c),
               'collision': (0xa514, 0xa537), 'stage_header': (0x655ca, 0x655d2)}


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _pad(values):
    if len(values) > 256 or any(type(v) is not int or not 0 <= v <= 255 for v in values):
        raise ValueError('invalid recovered byte table')
    return {'type': 'u8', 'values': list(values) + [0] * (256-len(values))}


def _tables(world, collision, joy, distances):
    """Partially evaluate the original signed-word add/ASR over finite inputs."""
    if len(world) != 256 or len(collision) != 35 or len(joy) != 16 or len(distances) != 10:
        raise ValueError('unexpected level table dimensions')
    signatures, phase_class = [], []
    for phase in range(256):
        signature = tuple(((n + phase) >> 8) & 255 for n in distances)
        if signature not in signatures:
            signatures.append(signature)
        phase_class.append(signatures.index(signature))
    count = len(signatures)
    if count * 16 > 256:
        raise ValueError('momentum classes exceed byte index')
    def angle(pad):
        original = ((pad & 1) << 3) | ((pad & 2) << 1) | ((pad & 4) >> 2) | ((pad & 8) >> 2)
        return joy[original]
    xs, ys = [], []
    for pad in range(16):
        direction = angle(pad)
        for signature in signatures:
            xs.append(0 if direction == 255 else signature[direction])
            ys.append(0 if direction == 255 else signature[direction+2])
    return {
        'directions': _pad([angle(i & 15) for i in range(256)]),
        'reverse': _pad([int(f'{i:08b}'[::-1], 2) for i in range(256)]),
        'phase_class': _pad(phase_class),
        'pad_offset': _pad([(i & 15) * count for i in range(256)]),
        'delta_x': _pad(xs), 'delta_y': _pad(ys),
        'x_nibble': _pad([i >> 4 for i in range(256)]),
        'y_nibble': _pad([i & 240 for i in range(256)]),
        'world': _pad(list(world)), 'collision': _pad(list(collision)),
        'radius8': _pad([int(i <= 8 or i >= 248) for i in range(256)]),
    }


def _program(tables, key_x, key_y):
    """Build the reviewed logical rules; caller supplies source-derived tables."""
    initials = {'$buttons': 0, '$x': 0, '$y': 0, '$angle': 2, '$action': 0,
                '$jump': 16, '$dead': 0, '$win': 0, '$keys': 1, '$key_active': 1,
                '$phase': 0, '$subpixel': 0, '$direction': 255, '$dx': 0, '$dy': 0,
                '$next_x': 0, '$next_y': 0, '$index': 0, '$tile': 0, '$collision': 0,
                '$tmp_x': 0, '$tmp_y': 0, '$test_x': 0, '$test_y': 0,
                '$prev_buttons': 0, '$pressed_jump': 0, '$blocked_x': 0, '$blocked_y': 0}
    counter = 0
    def var(name):
        return {'var': name}
    def node(op, **fields):
        nonlocal counter
        counter += 1
        return {'id': f'level_{counter:04d}', 'op': op, **fields}
    def assign(name, value):
        return node('set', var=name, value=value)
    def arithmetic(op, name, value):
        return node(op, var=name, value=value)
    def lookup(name, table, index):
        return node('lookup', var=name, table=table, index=index)
    def eq(name, value):
        return {'op': 'eq', 'left': var(name), 'right': value}
    def neg(condition):
        return {'op': 'not', 'condition': condition}
    def conjunction(*conditions):
        return {'op': 'and', 'conditions': list(conditions)}
    def bit(name, index):
        return {'op': 'bit_test', 'value': var(name), 'bit': index}
    def branch(condition, yes, no=()):
        return node('if', condition=condition, then=list(yes), **{'else': list(no)})
    def tile_at(x, y):
        return [lookup('$index', 'x_nibble', var(x)), lookup('$tile', 'y_nibble', var(y)),
                arithmetic('add', '$index', var('$tile')),
                lookup('$tile', 'world', var('$index')),
                lookup('$collision', 'collision', var('$tile'))]

    frame = [assign('$pressed_jump', 0)]
    for button in (4, 5):
        frame.append(branch(conjunction(bit('$buttons', button), neg(bit('$prev_buttons', button))),
                            [assign('$pressed_jump', 1)]))
    frame += [lookup('$subpixel', 'reverse', var('$phase')),
              lookup('$tmp_x', 'phase_class', var('$subpixel')),
              lookup('$index', 'pad_offset', var('$buttons')),
              arithmetic('add', '$index', var('$tmp_x')),
              lookup('$dx', 'delta_x', var('$index')),
              lookup('$dy', 'delta_y', var('$index')),
              lookup('$direction', 'directions', var('$buttons')),
              assign('$action', 0),
              branch(neg(eq('$direction', 255)),
                     [assign('$action', 1), assign('$angle', var('$direction'))]),
              assign('$blocked_x', 0), assign('$blocked_y', 0),
              assign('$next_x', var('$x')), arithmetic('add', '$next_x', var('$dx'))]
    frame += tile_at('$next_x', '$y')
    frame.append(branch(eq('$collision', 1), [assign('$blocked_x', 1)],
                        [assign('$x', var('$next_x'))]))
    frame += [assign('$next_y', var('$y')), arithmetic('add', '$next_y', var('$dy'))]
    frame += tile_at('$x', '$next_y')
    frame.append(branch(eq('$collision', 1), [assign('$blocked_y', 1)],
                        [assign('$y', var('$next_y'))]))

    # Stage 1-1 contains no springs, belts, shaking, ending or moving hazards.
    # The original decrements a jump before checking the resulting ground state.
    frame.append(branch(neg(eq('$jump', 0)), [arithmetic('subtract', '$jump', 1)]))
    water = [assign('$dead', 1), assign('$action', 6), assign('$angle', 255)]
    goal = [assign('$win', 1)]
    manual_jump = [branch(eq('$pressed_jump', 1), [assign('$jump', 48)])]
    grounded = tile_at('$x', '$y')
    grounded.append(branch(eq('$collision', 2), water,
                           [branch(conjunction(eq('$tile', 4), eq('$keys', 0)), goal, manual_jump)]))
    frame.append(branch(neg(eq('$jump', 0)), [assign('$action', 2)], grounded))

    # RunObjects follows RunPlayer. CollidesPlayer permits the first jump frame
    # (48) as well as ground state (0), and uses signed-byte wrapped distances.
    key_test = [assign('$tmp_x', key_x), arithmetic('subtract', '$tmp_x', var('$x')),
                assign('$tmp_y', key_y), arithmetic('subtract', '$tmp_y', var('$y')),
                lookup('$test_x', 'radius8', var('$tmp_x')),
                lookup('$test_y', 'radius8', var('$tmp_y')),
                branch(conjunction(eq('$test_x', 1), eq('$test_y', 1)),
                       [arithmetic('subtract', '$keys', 1), assign('$key_active', 0)])]
    can_collect = conjunction(eq('$key_active', 1), eq('$dead', 0),
                              neg(conjunction(neg(eq('$jump', 0)), neg(eq('$jump', 48)))))
    frame.append(branch(can_collect, key_test))
    frame.append(arithmetic('add', '$phase', 1))

    reset = [assign(name, initial) for name, initial in initials.items() if name != '$buttons']
    reset.append(assign('$prev_buttons', var('$buttons')))
    active = branch(conjunction(eq('$dead', 0), eq('$win', 0)), frame)
    body = [branch(bit('$buttons', 6), reset,
                   [active, assign('$prev_buttons', var('$buttons'))])]
    return {'format': 'fdisbull-il-1', 'role': 'uil',
            'variables': {name: {'type': 'u8', 'initial': value} for name, value in initials.items()},
            'resources': {}, 'tables': tables, 'body': body}


def lift_level(rom: bytes, *, stage: int = 0) -> dict:
    """Recover the fingerprinted ROM's first level as standard UIL plus scene.

    Source-derived gameplay runs until first death/win. The frozen terminal
    display and Start reset are authored adapters; original score/tally/lives,
    time limit, audio and rendering are outside the declared logical boundary.
    """
    if not isinstance(rom, bytes) or _sha(rom) != ROM_SHA256:
        raise ValueError('unsupported Miniplanets ROM identity')
    if type(stage) is not int or stage != 0:
        raise ValueError('only the verified Stage 1-1 is supported')
    def data(name):
        start, end = DATA_RANGES[name]
        return rom[start:end]
    world, collision, joy = data('map'), data('collision'), data('joy_angle')
    raw_distances = data('angle_distance')
    distances = [int.from_bytes(raw_distances[i:i+2], 'big', signed=True)
                 for i in range(0, 20, 2)]
    obj = data('object')
    if obj[0] != 1 or obj[3:] != b'\x00\xff' or set(world) - {0, 1, 2, 3, 4}:
        raise ValueError('level contains unmodeled objects or tile mechanics')
    tables = _tables(world, collision, joy, distances)
    program = _program(tables, obj[1], obj[2])
    program['evidence'] = {'upstream_origin': {
        'sha256': ROM_SHA256, 'uri': 'https://github.com/sikthehedgehog/miniplanets/tree/' + UPSTREAM_COMMIT,
        'notice': MINIPLANETS_LICENSE,
        'alteration': 'Reviewed Stage 1-1 UIL specialization with authored NES presentation and terminal/reset adapters'}}
    from .interaction_il import validate_il
    validate_il(program)
    regions = {name: {'offset': start, 'length': end-start,
                      'sha256': _sha(rom[start:end])}
               for name, (start, end) in {**CODE_RANGES, **DATA_RANGES}.items()}
    scene = {'format': 'fdisbull-console-scene-1', 'width': 16, 'height': 16,
             'title': 'MINIPLANETS', 'subtitle': 'STAGE 1-1',
             'tile_values': list(world), 'collision_values': list(collision),
             'player_x': '$x', 'player_y': '$y', 'jump': '$jump', 'dead': '$dead',
             'win': '$win', 'key_active': '$key_active', 'key_x': obj[1], 'key_y': obj[2]}
    return {'program': program, 'scene': scene, 'provenance': {
        'profile': 'miniplanets-remix-rev04-stage1-1-logical-1',
        'source_sha256': ROM_SHA256, 'upstream_commit': UPSTREAM_COMMIT,
        'upstream': 'https://github.com/sikthehedgehog/miniplanets',
        'recovery': 'reviewed source-bound specialization, not generic native decompilation',
        'regions': regions, 'stage': 0,
        'scope': 'active Stage 1-1 movement, walls, jumping, water, single key and goal',
        'authored_adapters': ['flattened NES presentation', 'freeze at first death/win', 'Start reset'],
        'excluded': ['score/tally', 'lives', 'time limit', 'audio', 'original rendering',
                     'other levels', 'ending', 'cheats', 'pause']}}
