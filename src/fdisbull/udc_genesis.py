"""Compile the restricted console UIL to native Mega Drive 68000 code.

The frontend is responsible for validating the UIL and allocating work RAM.
This module emits a standalone cartridge, not a 68000 interpreter.
"""
from __future__ import annotations

import struct


def translation_profiles():
    """Discover reviewed Genesis-source replay routes, separately from build()."""
    from .genesis_replay import profiles
    return profiles()


def inspect_translation_source(path):
    from .genesis_replay import inspect_source
    return inspect_source(path)


def write_translation(path, output, **options):
    """Capture Genesis-source UIL and a registered console lowering privately."""
    from .genesis_replay import write_bundle
    return write_bundle(path, output, **options)


def inspect_translation_bundle(path):
    from .genesis_replay import inspect_bundle
    return inspect_bundle(path)


def replay_translation(path, output, **options):
    from .genesis_replay import replay_bundle
    return replay_bundle(path, output, **options)


class _Assembler:
    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.fixups = []
        self.counter = 0

    def word(self, n):
        self.data.extend(struct.pack('>H', n & 0xffff))

    def long(self, n):
        self.data.extend(struct.pack('>I', n & 0xffffffff))

    def label(self, name):
        if name in self.labels:
            raise ValueError(f'duplicate label {name}')
        self.labels[name] = len(self.data)

    def fresh(self):
        self.counter += 1
        return f'_L{self.counter}'

    def branch(self, opcode, label):
        self.word(opcode)
        pos = len(self.data)
        self.word(0)
        self.fixups.append((pos, label))

    def resolve(self):
        for pos, label in self.fixups:
            displacement = self.labels[label] - pos
            if not -32768 <= displacement <= 32767:
                raise ValueError('Genesis branch exceeds 16-bit range')
            struct.pack_into('>h', self.data, pos, displacement)
        return self.data

    def imm_abs(self, width, value, address):
        self.word({8: 0x13fc, 16: 0x33fc, 32: 0x23fc}[width])
        (self.long if width == 32 else self.word)(value)
        self.long(address)

    def load(self, width, address, reg=0):
        self.word((0x1039 if width == 8 else 0x3039) | (reg << 9))
        self.long(address)

    def store(self, width, address, reg=0):
        self.word((0x13c0 if width == 8 else 0x33c0) | reg)
        self.long(address)

    def imm_reg(self, width, value, reg=0):
        self.word((0x103c if width == 8 else 0x303c) | (reg << 9))
        self.word(value)


VDP_DATA = 0xC00000
VDP_CTRL = 0xC00004
PAD = 0xA10003


def _boot(a, layout, display):
    a.label('reset')
    a.word(0x46fc); a.word(0x2700)  # mask interrupts
    a.load(8, 0xA10001)
    a.word(0x0200); a.word(0x000f)  # andi.b #15,d0
    skip = a.fresh(); a.branch(0x6700, skip)
    a.imm_abs(32, 0x53454741, 0xA14000)  # TMSS
    a.label(skip)
    a.imm_abs(16, 0x0100, 0xA11100)  # stop Z80
    a.imm_abs(16, 0, 0xA11200)
    for value in (0x9f, 0xbf, 0xdf, 0xff):
        a.imm_abs(8, value, 0xC00011)
    a.imm_abs(8, 0x40, 0xA10009)  # TH output
    a.imm_abs(8, 0x40, PAD)
    # Plane A at C000, sprite table at D000, 320x224, 64x32 plane.
    for reg in (0x8004, 0x8104, 0x8230, 0x833c, 0x8407, 0x8568,
                0x8700, 0x8b00, 0x8c81, 0x8d3f, 0x8f02, 0x9001):
        a.imm_abs(16, reg, VDP_CTRL)
    # Palette entry 0 black, entry 1 bright white.
    a.imm_abs(32, 0xc0000000, VDP_CTRL)
    a.imm_abs(16, 0, VDP_DATA); a.imm_abs(16, 0x0eee, VDP_DATA)
    # Tile zero is blank; tile one is solid palette colour 1.
    a.imm_abs(32, 0x40000000, VDP_CTRL)
    for value in [0] * 8 + [0x11111111] * 8:
        a.imm_abs(32, value, VDP_DATA)
    # Clear name table, including unused rows.
    a.imm_abs(32, 0x40000003, VDP_CTRL)
    a.imm_reg(16, 2047)
    clear = a.fresh(); a.label(clear)
    a.imm_abs(16, 0, VDP_DATA)
    a.word(0x51c8); pos = len(a.data); a.word(0); a.fixups.append((pos, clear))
    a.imm_abs(16, 0, 0xFFFFF0)
    for var in layout.values():
        a.imm_abs(var['width'], var['initial'], var['address'])
    a.imm_abs(16, 0xa55a, 0xfffff2)
    a.imm_abs(16, 0x8174, VDP_CTRL)  # display on, VBlank interrupt disabled by SR
    a.label('frame')
    # Poll a transition into vertical blank, so one update happens per frame.
    clear = a.fresh(); a.label(clear)
    a.load(16, VDP_CTRL); a.word(0x0800); a.word(3); a.branch(0x6600, clear)
    blank = a.fresh(); a.label(blank)
    a.load(16, VDP_CTRL); a.word(0x0800); a.word(3); a.branch(0x6700, blank)
    if '$buttons' in layout:
        _read_pad(a, layout['$buttons']['address'])
    # BSR.W logic_tick.
    a.branch(0x6100, 'logic_tick')
    a.word(0x5279); a.long(0xFFFFF0)  # addq.w #1, frame counter
    if display is not None:
        # One sprite at y=80; x is the unsigned UIL coordinate + hardware bias.
        a.imm_abs(32, 0x50000003, VDP_CTRL)
        a.imm_abs(16, 208, VDP_DATA)
        a.imm_abs(16, 0, VDP_DATA)
        a.imm_abs(16, 1, VDP_DATA)
        a.word(0x7000)
        if display is None:
            a.imm_reg(8, 120)
        else:
            a.load(8, layout[display]['address'])
        a.word(0x0640); a.word(128)
        a.store(16, VDP_DATA)
    a.branch(0x6000, 'frame')


def _read_pad(a, address):
    a.word(0x7400)  # moveq #0,d2
    for th, mapping in ((0x40, ((3, 0), (2, 1), (0, 2), (1, 3), (4, 5))),
                        (0, ((4, 4), (5, 6)))):
        a.imm_abs(8, th, PAD)
        a.word(0x4e71); a.word(0x4e71); a.word(0x4e71)
        a.load(8, PAD)
        for source, target in mapping:
            skip = a.fresh()
            a.word(0x0800); a.word(source)  # btst immediate,d0
            a.branch(0x6600, skip)  # pressed is active low
            a.word(0x08c2); a.word(target)  # bset immediate,d2
            a.label(skip)
    a.imm_abs(8, 0x40, PAD)
    a.store(8, address, 2)


def _value(a, value, width, layout, reg=0):
    if isinstance(value, int):
        a.imm_reg(width, value, reg)
    elif isinstance(value, dict) and set(value) == {'var'}:
        a.load(width, layout[value['var']]['address'], reg)
    else:
        raise ValueError('unsupported Genesis value')


def _condition(a, condition, layout, yes, no):
    op = condition['op']
    if op == 'not':
        _condition(a, condition['condition'], layout, no, yes)
    elif op == 'and':
        items = condition['conditions']
        for item in items[:-1]:
            nxt = a.fresh()
            _condition(a, item, layout, nxt, no)
            a.label(nxt)
        if items:
            _condition(a, items[-1], layout, yes, no)
        else:
            a.branch(0x6000, yes)
    elif op in ('eq', 'bit_test'):
        left = condition['left'] if op == 'eq' else condition['value']
        right = condition.get('right')
        width = 16 if op == 'bit_test' and type(left) is int else (16 if any(type(value) is int and value > 255 for value in (left, right)) else 8)
        for value in (left, right):
            if isinstance(value, dict) and 'var' in value:
                width = layout[value['var']]['width']
                break
        _value(a, left, width, layout)
        if op == 'eq':
            _value(a, right, width, layout, 1)
            a.word(0xb001 if width == 8 else 0xb041)  # cmp d1,d0
            a.branch(0x6700, yes)
        else:
            a.word(0x0800); a.word(condition['bit'])
            a.branch(0x6600, yes)
        a.branch(0x6000, no)
    else:
        raise ValueError(f'unsupported Genesis condition {op!r}')


def _nodes(a, nodes, layout):
    for node in nodes:
        op = node['op']
        if op == 'if':
            yes, no, end = a.fresh(), a.fresh(), a.fresh()
            _condition(a, node['condition'], layout, yes, no)
            a.label(yes); _nodes(a, node['then'], layout); a.branch(0x6000, end)
            a.label(no); _nodes(a, node.get('else', []), layout); a.label(end)
        elif op in ('set', 'add', 'subtract'):
            dest = layout[node['var']]
            width = dest['width']
            if op == 'set':
                _value(a, node['value'], width, layout)
            else:
                a.load(width, dest['address'])
                _value(a, node['value'], width, layout, 1)
                a.word((0xd001 if op == 'add' else 0x9001) | (0x40 if width == 16 else 0))
            a.store(width, dest['address'])
        else:
            raise ValueError(f'unsupported Genesis node {op!r}')


def build(program: dict, layout: dict, *, display_variable: str | None = None) -> dict:
    """Produce a native 68000 cartridge from frontend-validated restricted UIL."""
    from .console_udc import validate_console_program
    validate_console_program(program)
    if not isinstance(layout, dict) or set(layout) != set(program['variables']):
        raise ValueError('Genesis layout must bind every declared variable exactly once')
    occupied = set()
    for name, binding in layout.items():
        if not isinstance(binding, dict) or set(binding) != {'address', 'width', 'initial'}:
            raise ValueError('invalid Genesis variable binding')
        address, width, initial = (binding[k] for k in ('address', 'width', 'initial'))
        declaration = program['variables'][name]
        if (type(address) is not int or type(width) is not int or
                width != int(declaration['type'][1:]) or type(initial) is not int or
                initial != declaration['initial'] or address < 0xff0000 or
                address + width // 8 > 0xfffff0 or (width == 16 and address % 2)):
            raise ValueError('invalid Genesis variable binding')
        addresses = set(range(address, address + width // 8))
        if occupied & addresses:
            raise ValueError('overlapping Genesis variable bindings')
        occupied |= addresses
    if display_variable is not None and (display_variable not in layout or
                                         layout[display_variable]['width'] != 8):
        raise ValueError('display variable must name a u8 variable')
    a = _Assembler()
    _boot(a, layout, display_variable)
    a.label('logic_tick')
    _nodes(a, program['body'], layout)
    a.word(0x4e75)  # RTS
    a.label('logic_tick_end')
    a.label('exception')
    a.branch(0x6000, 'exception')
    code = a.resolve()
    # The bound applies only to this compiler's emitted 68000 subset. Charging
    # 64 cycles per instruction exceeds the cost of every supported form.
    from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs
    start, end = a.labels['logic_tick'], a.labels['logic_tick_end']
    logic = bytes(code[start:end])
    instructions = list(Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000).disasm(logic, 0x200 + start))
    allowed = {'move.b', 'move.w', 'add.b', 'add.w', 'sub.b', 'sub.w',
               'cmp.b', 'cmp.w', 'btst.b', 'beq.w', 'bne.w', 'bra.w', 'rts'}
    if (sum(i.size for i in instructions) != len(logic) or
            any(i.mnemonic not in allowed for i in instructions)):
        raise ValueError('unsupported or undecodable generated Genesis logic')
    logic_cycles = 64 * len(instructions)
    if logic_cycles > 6000:
        raise ValueError('Genesis logic exceeds the 6000-cycle conservative budget')
    if len(code) > 0x3ffe00:
        raise ValueError('Genesis ROM exceeds supported 4 MiB cartridge size')
    size = max(0x8000, (0x200 + len(code) + 1) & ~1)
    rom = bytearray(size)
    for offset in range(0, 0x100, 4):
        struct.pack_into('>I', rom, offset, 0x200 + a.labels['exception'])
    struct.pack_into('>II', rom, 0, 0x00fffffc, 0x200 + a.labels['reset'])
    def field(offset, length, value):
        rom[offset:offset + length] = value.encode('ascii')[:length].ljust(length, b' ')
    field(0x100, 16, 'SEGA MEGA DRIVE ')
    field(0x110, 16, '(C)FDB 2026.OCT')
    field(0x120, 48, 'FDISBULL UDC')
    field(0x150, 48, 'FDISBULL UDC')
    field(0x180, 14, 'GM 00000000-00')
    field(0x190, 16, 'J')
    struct.pack_into('>IIII', rom, 0x1a0, 0, size - 1, 0x00ff0000, 0x00ffffff)
    field(0x1f0, 16, 'JUE')
    rom[0x200:0x200 + len(code)] = code
    checksum = sum(struct.unpack_from('>H', rom, i)[0] for i in range(0x200, len(rom), 2)) & 0xffff
    struct.pack_into('>H', rom, 0x18e, checksum)
    return {'rom': bytes(rom), 'symbols': {'logic_tick': 0x200 + a.labels['logic_tick'],
                                           'reset': 0x200 + a.labels['reset'],
                                           'runtime_frame_counter': 0xFFFFF0,
                                           'runtime_ready': 0xFFFFF2,
                                           'logic_tick_end': 0x200 + a.labels['logic_tick_end']},
            'diagnostics': [],
            'profile': {'cpu': 'm68000', 'console': 'genesis', 'native_code': True,
                        'input': 'three-button port A; select unavailable',
                        'display': display_variable, 'logic_cycles_upper_bound': logic_cycles,
                        'max_logic_cycles': 6000}}
