"""Native NES presentation for an explicit UIL program and a 16-by-16 scene.

The game rules remain in UIL. This adapter supplies a flat map, authored icons,
controller sampling, stable published state and vblank-only display updates.
"""
from __future__ import annotations

from .udc_nes import _Asm, _emit_logic, _emit_tables, _logic_cycles


MAX_LOGIC_CYCLES = 20000
MAX_PUBLISHED_BYTES = 96
FRAME_COUNTER = 0x7f0
READY = 0x7f2
WORKING_OFFSET = 0x100


# Five-by-seven authored diagnostic font, not recovered game graphics.
_FONT = {
    'A': (14,17,17,31,17,17,17), 'B': (30,17,17,30,17,17,30),
    'C': (14,17,16,16,16,17,14), 'D': (30,17,17,17,17,17,30),
    'E': (31,16,16,30,16,16,31), 'F': (31,16,16,30,16,16,16),
    'G': (14,17,16,23,17,17,15), 'H': (17,17,17,31,17,17,17),
    'I': (14,4,4,4,4,4,14), 'J': (7,2,2,2,18,18,12),
    'K': (17,18,20,24,20,18,17), 'L': (16,16,16,16,16,16,31),
    'M': (17,27,21,21,17,17,17), 'N': (17,25,21,19,17,17,17),
    'O': (14,17,17,17,17,17,14), 'P': (30,17,17,30,16,16,16),
    'Q': (14,17,17,17,21,18,13), 'R': (30,17,17,30,20,18,17),
    'S': (15,16,16,14,1,1,30), 'T': (31,4,4,4,4,4,4),
    'U': (17,17,17,17,17,17,14), 'V': (17,17,17,17,17,10,4),
    'W': (17,17,17,21,21,21,10), 'X': (17,17,10,4,10,17,17),
    'Y': (17,17,10,4,4,4,4), 'Z': (31,1,2,4,8,16,31),
    '0': (14,17,19,21,25,17,14), '1': (4,12,4,4,4,4,14),
    '2': (14,17,1,2,4,8,31), '3': (30,1,1,14,1,1,30),
    '4': (2,6,10,18,31,2,2), '5': (31,16,16,30,1,1,30),
    '6': (14,16,16,30,17,17,14), '7': (31,1,2,4,8,8,8),
    '8': (14,17,17,14,17,17,14), '9': (14,17,17,15,1,1,14),
    '/': (1,2,2,4,8,8,16), '-': (0,0,0,31,0,0,0),
    '!': (4,4,4,4,4,0,4), ':': (0,4,4,0,4,4,0),
}


def _characters():
    data = bytearray(8192)

    def tile(index, rows, color=1):
        data[index * 16:index * 16 + 8] = bytes(rows if color & 1 else (0,) * 8)
        data[index * 16 + 8:index * 16 + 16] = bytes(rows if color & 2 else (0,) * 8)

    tile(1, (0,0,0,0,0,0,0x10,0))       # sparse floor
    tile(2, (255,129,189,165,165,189,129,255))  # walls
    tile(3, (129,66,36,24,24,36,66,129), 2)   # hazard
    tile(4, (60,66,153,165,165,153,66,60), 3) # goal
    tile(5, (24,36,36,24,16,24,16,0))        # key sprite
    tile(6, (0,0,60,60,60,60,0,0))           # player dot
    tile(7, (0,66,36,24,24,36,66,0))         # lost player
    for char, rows in _FONT.items():
        tile(ord(char), (0, *(row << 1 for row in rows)))
    return bytes(data)


def _scene(program, layout, scene):
    required = {'format', 'width', 'height', 'tile_values', 'collision_values',
                'player_x', 'player_y', 'jump', 'dead', 'win', 'key_active', 'key_x', 'key_y'}
    if not isinstance(scene, dict) or not required <= set(scene):
        raise ValueError('incomplete NES level scene')
    if scene['format'] != 'fdisbull-console-scene-1' or scene['width'] != 16 or scene['height'] != 16:
        raise ValueError('NES level scene requires a 16-by-16 map')
    tiles, collisions = scene['tile_values'], scene['collision_values']
    if (not isinstance(tiles, list) or len(tiles) != 256 or
            not isinstance(collisions, list) or not 1 <= len(collisions) <= 256 or
            any(type(v) is not int or not 0 <= v <= 2 for v in collisions) or
            any(type(v) is not int or not 0 <= v < len(collisions) for v in tiles)):
        raise ValueError('invalid NES scene map or collision classification')
    for role in ('player_x', 'player_y', 'jump', 'dead', 'win', 'key_active'):
        if scene[role] not in layout or layout[scene[role]]['width'] != 8:
            raise ValueError('scene bindings must name declared u8 variables')
    for role in ('key_x', 'key_y'):
        if type(scene[role]) is not int or not 0 <= scene[role] <= 255:
            raise ValueError('scene key coordinates must be unsigned bytes')
    for field in ('title', 'subtitle'):
        if field in scene and (not isinstance(scene[field], str) or not 1 <= len(scene[field]) <= 28 or
                               any(char != ' ' and char not in _FONT for char in scene[field])):
            raise ValueError('scene captions must use the authored font and fit 28 characters')
    if type(scene.get('goal_tile', 4)) is not int or not 0 <= scene.get('goal_tile', 4) < len(collisions):
        raise ValueError('invalid scene goal tile')
    if '$buttons' not in layout or layout['$buttons']['width'] != 8:
        raise ValueError('NES level profile requires a u8 controller variable')
    # A scene must display a table actually supplied to the UIL program.
    if not any(table.get('type') == 'u8' and table.get('values') == tiles
               for table in program.get('tables', {}).values()):
        raise ValueError('scene map differs from all declared UIL tables')
    if not any(table.get('type') == 'u8' and table.get('values', [])[:len(collisions)] == collisions
               for table in program.get('tables', {}).values()):
        raise ValueError('scene collisions differ from all declared UIL tables')
    return scene


def _nametable(scene):
    image = bytearray(1024)
    for row in range(16):
        for column in range(16):
            tile = scene['tile_values'][row * 16 + column]
            collision = scene['collision_values'][tile]
            rendered = 4 if tile == scene.get('goal_tile', 4) else (2 if collision == 1 else 3 if collision == 2 else 1)
            image[(row + 5) * 32 + column + 8] = rendered
    for row, text in ((1, scene.get('title', 'UIL LEVEL / NES')), (2, scene.get('subtitle', 'NATIVE UIL GAMEPLAY')),
                      (23, 'DPAD MOVE  A/B JUMP'), (25, 'START RESTART'),
                      (27, 'WALLS BLOCK  WATER HURTS')):
        start = row * 32 + (32 - len(text)) // 2
        image[start:start + len(text)] = text.encode('ascii')
    return bytes(image)


def _constant(a, value, destination):
    a.emit(0xa9, value); a.absolute(0x8d, destination)


def _boot(a, layout):
    a.label('reset')
    a.emit(0x78, 0xd8, 0xa2, 0xff, 0x9a, 0xe8)
    for address in (0x2000, 0x2001, 0x4010, 0x4015):
        a.absolute(0x8e, address)
    _constant(a, 0x40, 0x4017)
    a.absolute(0x2c, 0x2002)
    for index in range(2):
        a.label(f'boot_wait{index}')
        a.absolute(0x2c, 0x2002); a.emit(0x10, 0xfb)
    a.emit(0xa2, 0, 0xa9, 0xff)
    a.label('clear_oam'); a.absolute(0x9d, 0x200); a.emit(0xe8, 0xd0, 0xfa)
    # All nametable and attribute bytes are initialized while rendering is off.
    _constant(a, 0x20, 0x2006); _constant(a, 0, 0x2006)
    a.emit(0xa2, 0)
    for page in range(4):
        a.label(f'nametable_copy{page}')
        a.jump(0xbd, f'nametable:{page}'); a.absolute(0x8d, 0x2007)
        a.emit(0xe8, 0xd0, 0xf7)
    _constant(a, 0x3f, 0x2006); _constant(a, 0, 0x2006)
    palette = (0x0f,0x30,0x16,0x28) * 4 + (0x0f,0x30,0x21,0x11) + (0x0f,0x28,0x18,0x38) + (0x0f,0x16,0x06,0x26) + (0x0f,0x2a,0x1a,0x3a)
    for value in palette:
        _constant(a, value, 0x2007)
    for binding in layout.values():
        for index in range(binding['width'] // 8):
            value = (binding['initial'] >> (index * 8)) & 255
            _constant(a, value, binding['address'] + index)
            _constant(a, value, binding['address'] + WORKING_OFFSET + index)
    _constant(a, 0, FRAME_COUNTER); _constant(a, 0, FRAME_COUNTER + 1)
    _constant(a, 0x5a, READY); _constant(a, 0xa5, READY + 1)
    _constant(a, 0, 0x2005); _constant(a, 0, 0x2005)
    _constant(a, 0x1e, 0x2001)


def _controller(a, address):
    _constant(a, 1, 0x4016); _constant(a, 0, 0x4016); _constant(a, 0, address)
    for mask in (0x10,0x20,0x80,0x40,0x04,0x08,0x02,0x01):
        a.absolute(0xad, 0x4016); a.emit(0x29, 1, 0xf0, 8)
        a.absolute(0xad, address); a.emit(0x09, mask); a.absolute(0x8d, address)


def _presentation(a, layout, scene):
    def load(role):
        a.absolute(0xad, layout[scene[role]]['address'])

    a.label('presentation')
    load('player_y'); a.emit(0x4a, 0x18, 0x69, 35); a.absolute(0x8d, 0x200)
    load('jump'); no_jump = a.unique(); a.branch_false(0xd0, no_jump)
    a.absolute(0xad, 0x200); a.emit(0x38, 0xe9, 3); a.absolute(0x8d, 0x200)
    a.label(no_jump)
    load('player_x'); a.emit(0x4a, 0x18, 0x69, 60); a.absolute(0x8d, 0x203)
    _constant(a, 6, 0x201); _constant(a, 0, 0x202)
    load('dead'); live = a.unique(); a.branch_false(0xd0, live)
    _constant(a, 7, 0x201); _constant(a, 2, 0x202)
    actor_done = a.unique(); a.jump(0x4c, actor_done); a.label(live)
    load('jump'); grounded = a.unique(); a.branch_false(0xd0, grounded)
    _constant(a, 3, 0x202); a.label(grounded)
    load('win'); no_win = a.unique(); a.branch_false(0xd0, no_win)
    _constant(a, 3, 0x202); a.label(no_win)
    for name in ('$blocked_x', '$blocked_y'):
        if name in layout:
            a.absolute(0xad, layout[name]['address']); clear = a.unique(); a.branch_false(0xd0, clear)
            _constant(a, 2, 0x202); a.label(clear)
    a.label(actor_done)
    _constant(a, 5, 0x205); _constant(a, 1, 0x206)
    _constant(a, 60 + scene['key_x'] // 2, 0x207)
    load('key_active'); key_gone = a.unique(); key_done = a.unique()
    a.branch_false(0xd0, key_gone)
    _constant(a, 35 + scene['key_y'] // 2, 0x204); a.jump(0x4c, key_done)
    a.label(key_gone); _constant(a, 255, 0x204); a.label(key_done)
    _constant(a, 0, 0x2003); _constant(a, 2, 0x4014)
    # The goal changes from yellow to green once the key has been collected.
    _constant(a, 0x3f, 0x2006); _constant(a, 3, 0x2006)
    load('key_active'); unlocked = a.unique(); color_done = a.unique()
    a.branch_false(0xd0, unlocked)
    a.emit(0xa9, 0x28); a.jump(0x4c, color_done)
    a.label(unlocked); a.emit(0xa9, 0x2a); a.label(color_done); a.absolute(0x8d, 0x2007)
    # Select one fixed-width, authored status line.
    load('dead'); hud_alive = a.unique(); a.branch_false(0xd0, hud_alive)
    message_dead = a.unique(); message_win = a.unique(); message_open = a.unique(); message_key = a.unique(); hud_end = a.unique()
    a.jump(0x4c, message_dead); a.label(hud_alive)
    load('win'); hud_play = a.unique(); a.branch_false(0xd0, hud_play)
    a.jump(0x4c, message_win); a.label(hud_play)
    load('key_active'); need_key = a.unique(); a.branch_false(0xf0, need_key)
    a.jump(0x4c, message_open); a.label(need_key); a.jump(0x4c, message_key)
    for label, text_label in ((message_dead, 'hud:dead'), (message_win, 'hud:win'), (message_open, 'hud:open'), (message_key, 'hud:key')):
        a.label(label)
        _constant(a, 0x20, 0x2006); _constant(a, 3 * 32 + 4, 0x2006)
        a.emit(0xa2, 0)
        loop = a.unique(); a.label(loop); a.jump(0xbd, text_label)
        a.absolute(0x8d, 0x2007); a.emit(0xe8, 0xe0, 24, 0xd0, 0xf5)
        a.jump(0x4c, hud_end)
    a.label(hud_end)
    a.absolute(0x2c, 0x2002)
    _constant(a, 0, 0x2006); _constant(a, 0, 0x2006)
    _constant(a, 0, 0x2005); _constant(a, 0, 0x2005)
    a.emit(0x60)


def build(program: dict, layout: dict, *, scene: dict) -> dict:
    """Compile UIL gameplay with a stable RAM projection and NES scene adapter."""
    from .console_udc import validate_console_program
    validate_console_program(program, level=True)
    if not isinstance(layout, dict) or set(layout) != set(program['variables']):
        raise ValueError('invalid NES level variable layout')
    occupied = set()
    for name, binding in layout.items():
        if not isinstance(binding, dict) or set(binding) != {'address', 'width', 'initial'}:
            raise ValueError('invalid NES level binding')
        address, width, initial = (binding[k] for k in ('address', 'width', 'initial'))
        if (type(address) is not int or width not in (8, 16) or type(initial) is not int or
                not 0 <= initial < 1 << width):
            raise ValueError('invalid NES level binding')
        cells = set(range(address, address + width // 8))
        if cells & occupied or not cells <= set(range(0x300, 0x380)):
            raise ValueError('NES level public RAM must fit the reserved 128-byte publication area')
        occupied |= cells
        if program['variables'][name] != {'type': f'u{width}', 'initial': initial}:
            raise ValueError('NES level declaration differs from binding')
    _scene(program, layout, scene)
    # The fixed renderer, worst-case HUD branch/loop costs, 514-cycle OAM DMA,
    # frame counter and vblank-entry latency reserve 1,450 CPU cycles. Each
    # published byte adds an absolute LDA/STA pair (8 cycles). Cap publication
    # below the NTSC vblank window even for mixed-width programs.
    if len(occupied) > MAX_PUBLISHED_BYTES:
        raise ValueError('NES level publication exceeds the vblank byte budget')
    working = {name: {**binding, 'address': binding['address'] + WORKING_OFFSET}
               for name, binding in layout.items()}
    a = _Asm()
    _boot(a, layout)
    a.absolute(0x2c, 0x2002)
    a.label('frame_logic')
    _controller(a, working['$buttons']['address'])
    a.jump(0x20, 'logic_tick')
    a.label('wait_vblank'); a.absolute(0x2c, 0x2002); a.emit(0x10, 0xfb)
    for address in sorted(occupied):
        a.absolute(0xad, address + WORKING_OFFSET); a.absolute(0x8d, address)
    a.jump(0x20, 'presentation')
    a.absolute(0xee, FRAME_COUNTER); a.emit(0xd0, 3); a.absolute(0xee, FRAME_COUNTER + 1)
    # More than a complete vblank interval: the next controller read occurs
    # after the display-update tail, while the published state remains stable.
    for index in range(2):
        a.emit(0xa2, 0)
        a.label(f'frame_delay{index}'); a.emit(0xca, 0xd0, 0xfd)
    a.jump(0x4c, 'frame_logic')
    a.label('interrupt'); a.emit(0x40)
    _presentation(a, layout, scene)
    _emit_logic(a, program, working)
    _emit_tables(a, program)
    for label, text in (('hud:dead', 'WATER! START TO RETRY'), ('hud:win', 'LEVEL CLEAR! START'),
                        ('hud:open', 'GOAL UNLOCKED'), ('hud:key', 'GET KEY THEN FIND GOAL')):
        a.label(label); a.emit(*text.ljust(24).encode('ascii'))
    nametable = _nametable(scene)
    for page in range(4):
        a.label(f'nametable:{page}'); a.emit(*nametable[page * 256:(page + 1) * 256])
    code = a.finish()
    start, end = (a.labels[k] - 0x8000 for k in ('logic_tick', 'logic_tick_end'))
    cycles = _logic_cycles(code[start:end])
    if cycles > MAX_LOGIC_CYCLES:
        raise ValueError('NES level logic cycle budget exceeded')
    prg = bytearray([255]) * 32768
    prg[:len(code)] = code
    for offset, label in ((0x7ffa, 'interrupt'), (0x7ffc, 'reset'), (0x7ffe, 'interrupt')):
        address = a.labels[label]; prg[offset:offset + 2] = address.to_bytes(2, 'little')
    return {'rom': b'NES\x1a' + bytes((2,1,0,0)) + bytes(8) + bytes(prg) + _characters(),
            'symbols': {'reset': a.labels['reset'], 'logic_tick': a.labels['logic_tick'],
                        'logic_tick_end': a.labels['logic_tick_end'], 'presentation': a.labels['presentation'],
                        'runtime_frame_counter': FRAME_COUNTER, 'runtime_ready': READY},
            'profile': {'mapper': 0, 'prg_bytes': 32768, 'chr_bytes': 8192,
                        'screen': [256,240], 'map_screen_origin': [64,40], 'world_pixel_scale': [1,2],
                        'variable_endian': 'little', 'frame_counter_endian': 'little',
                        'logic_cycles_upper_bound': cycles, 'max_logic_cycles': MAX_LOGIC_CYCLES,
                        'presentation_cycles_upper_bound': 1450 + 8 * len(occupied),
                        'max_published_bytes': MAX_PUBLISHED_BYTES,
                        'published_snapshot': True, 'working_variables': working,
                        'input_publication': 'sampled for logic, published on the following vblank',
                        'display_adapter': 'authored flat 2D icons and HUD; source game rules execute as UIL',
                        'input_bits': 'right,left,up,down,A,B,Start,Select', 'ppu_updates': 'vblank only'},
            'diagnostics': []}
