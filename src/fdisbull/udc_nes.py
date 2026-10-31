"""Bounded UIL-to-NES mapper-0 ROM emitter.

The output contains native 6502 code, not an interpreter. Unsupported constructs
are rejected; no emulation or whole-game recovery is implied.
"""
from __future__ import annotations


class _Asm:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fixups = []
        self.serial = 0

    def label(self, name):
        if name in self.labels:
            raise ValueError('duplicate code label')
        self.labels[name] = 0x8000 + len(self.code)

    def emit(self, *values):
        self.code.extend(values)

    def absolute(self, op, addr):
        self.emit(op, addr & 255, addr >> 8)

    def jump(self, op, label):
        self.emit(op, 0, 0)
        self.fixups.append((len(self.code) - 2, label))

    def unique(self):
        self.serial += 1
        return f'_L{self.serial}'

    def branch_false(self, branch_true, label):
        # Opposite branch skips an absolute jump: no relative-range limit.
        self.emit(branch_true, 3)
        self.jump(0x4c, label)

    def finish(self):
        for offset, label in self.fixups:
            if label not in self.labels:
                raise ValueError('unresolved code label')
            addr = self.labels[label]
            self.code[offset:offset + 2] = bytes((addr & 255, addr >> 8))
        if len(self.code) > 0x7ffa:
            raise ValueError('NES program exceeds mapper-0 PRG capacity')
        return self.code


# Conservative sum over every instruction, including both sides of branches.
# Each conditional branch assumes the taken, page-crossing cost. This scan
# covers the emitted instruction bytes exactly and fails closed on new opcodes.
_LOGIC_OPCODES = {
    0xa9: (2, 2), 0xad: (3, 4),  # LDA
    0x8d: (3, 4),                # STA
    0x69: (2, 2), 0x6d: (3, 4),  # ADC
    0xe9: (2, 2), 0xed: (3, 4),  # SBC
    0x18: (1, 2), 0x38: (1, 2),  # CLC, SEC
    0xc9: (2, 2), 0xcd: (3, 4),  # CMP
    0x29: (2, 2),                # AND
    0xf0: (2, 4), 0xd0: (2, 4),  # BEQ, BNE
    0x4c: (3, 3), 0x60: (1, 6),  # JMP, RTS
}
_MAX_LOGIC_CYCLES = 1000


def _logic_cycles(code):
    offset = cycles = 0
    while offset < len(code):
        spec = _LOGIC_OPCODES.get(code[offset])
        if spec is None:
            raise ValueError('unknown NES logic opcode in cycle budget')
        size, cost = spec
        if offset + size > len(code):
            raise ValueError('truncated NES logic opcode in cycle budget')
        offset += size
        cycles += cost
    return cycles

def _runtime(a, variables, display):
    a.label('reset')
    a.emit(0x78, 0xd8, 0xa2, 0xff, 0x9a, 0xe8)  # SEI, CLD, stack, X=0
    for addr in (0x2000, 0x2001, 0x4010, 0x4015):
        a.absolute(0x8e, addr)
    a.emit(0xa9, 0x40); a.absolute(0x8d, 0x4017)
    a.absolute(0x2c, 0x2002)
    for n in range(2):
        a.label(f'boot_wait{n}')
        a.absolute(0x2c, 0x2002); a.emit(0x10, 0xfb)  # BPL
    # Hide all sprites. OAM lives at $0200, reserved from program variables.
    a.emit(0xa2, 0x00, 0xa9, 0xff)
    a.label('clear_oam'); a.absolute(0x9d, 0x0200); a.emit(0xe8, 0xd0, 0xfa)
    # Four-byte sprite: Y, tile, attributes, X.
    for addr, value in ((0x200, 100), (0x201, 0), (0x202, 0)):
        a.emit(0xa9, value); a.absolute(0x8d, addr)
    # Background + sprite palette; tile 0 uses color index 1.
    a.emit(0xa9, 0x3f); a.absolute(0x8d, 0x2006)
    a.emit(0xa9, 0x00); a.absolute(0x8d, 0x2006)
    for value in (0x0f, 0x30, 0x21, 0x11) * 8:
        a.emit(0xa9, value); a.absolute(0x8d, 0x2007)
    for data in variables.values():
        addr, width, initial = data['address'], data['width'], data['initial']
        for i in range(width // 8):
            a.emit(0xa9, (initial >> (8 * i)) & 255); a.absolute(0x8d, addr + i)
    # Frame counter at $07F0-$07F1, kept outside user allocations.
    a.emit(0xa9, 0); a.absolute(0x8d, 0x7f0); a.absolute(0x8d, 0x7f1)
    a.emit(0xa9, 0x5a); a.absolute(0x8d, 0x7f2)
    a.emit(0xa9, 0xa5); a.absolute(0x8d, 0x7f3)
    a.absolute(0x2c, 0x2002)
    a.emit(0xa9, 0); a.absolute(0x8d, 0x2005); a.absolute(0x8d, 0x2005)
    a.emit(0xa9, 0x14 if display is not None else 0); a.absolute(0x8d, 0x2001)
    a.label('frame_wait_clear'); a.absolute(0x2c, 0x2002); a.emit(0x30, 0xfb)
    a.label('frame_wait_set'); a.absolute(0x2c, 0x2002); a.emit(0x10, 0xfb)
    # Controller register serial order A,B,Select,Start,Up,Down,Left,Right.
    if '$buttons' in variables:
        addr = variables['$buttons']['address']
        a.emit(0xa9, 1); a.absolute(0x8d, 0x4016)
        a.emit(0xa9, 0); a.absolute(0x8d, 0x4016); a.absolute(0x8d, addr)
        for mask in (0x10, 0x20, 0x80, 0x40, 0x04, 0x08, 0x02, 0x01):
            a.absolute(0xad, 0x4016); a.emit(0x29, 1, 0xf0, 8)
            a.absolute(0xad, addr); a.emit(0x09, mask); a.absolute(0x8d, addr)
    a.jump(0x20, 'logic_tick')
    a.absolute(0xee, 0x7f0); a.emit(0xd0, 3); a.absolute(0xee, 0x7f1)
    if display is None:
        a.emit(0xa9, 120)
    else:
        a.absolute(0xad, variables[display]['address'])
    a.absolute(0x8d, 0x0203)
    a.emit(0xa9, 0); a.absolute(0x8d, 0x2003)
    a.emit(0xa9, 2); a.absolute(0x8d, 0x4014)
    a.jump(0x4c, 'frame_wait_clear')
    a.label('interrupt'); a.emit(0x40)


def build(program: dict, layout: dict, *, display_variable: str | None = None) -> dict:
    """Compile the supported UIL subset into a 32 KiB mapper-0 NES ROM."""
    if program.get('format') != 'fdisbull-il-1' or program.get('role') != 'uil' or program.get('resources') != {}:
        raise ValueError('unsupported NES program format or resources')
    if not isinstance(layout, dict) or set(layout) != set(program.get('variables', {})):
        raise ValueError('invalid NES variable layout')
    occupied = set()
    for name, v in layout.items():
        if not isinstance(v, dict) or set(v) != {'address', 'width', 'initial'}:
            raise ValueError('invalid NES variable layout')
        addr, width, initial = v['address'], v['width'], v['initial']
        if type(addr) is not int or width not in (8, 16) or type(initial) is not int or not 0 <= initial < (1 << width):
            raise ValueError('invalid NES variable layout')
        cells = set(range(addr, addr + width // 8))
        if not cells <= set(range(0x300, 0x7f0)) or cells & occupied:
            raise ValueError('NES variable layout overlaps reserved RAM')
        occupied |= cells
        declared = program['variables'][name]
        if declared.get('type') != f'u{width}' or declared.get('initial') != initial:
            raise ValueError('NES variable declaration differs from layout')
    if '$buttons' in layout and layout['$buttons']['width'] != 8:
        raise ValueError('NES buttons must be u8')
    if display_variable is not None and (display_variable not in layout or layout[display_variable]['width'] != 8):
        raise ValueError('NES display variable must name a u8')
    a = _Asm()

    def operand(value, width, byte, imm, absolute):
        if type(value) is int:
            if not 0 <= value < (1 << width):
                raise ValueError('NES literal outside variable width')
            a.emit(imm, (value >> (8 * byte)) & 255)
        elif isinstance(value, dict) and set(value) == {'var'} and value['var'] in layout:
            v = layout[value['var']]
            if v['width'] != width:
                raise ValueError('NES operand width mismatch')
            a.absolute(absolute, v['address'] + byte)
        else:
            raise ValueError('unsupported NES operand')

    def width_for(left, right):
        widths = [layout[v['var']]['width'] for v in (left, right)
                  if isinstance(v, dict) and set(v) == {'var'} and v['var'] in layout]
        if widths and any(w != widths[0] for w in widths):
            raise ValueError('NES operand width mismatch')
        return widths[0] if widths else 16

    def condition(c, yes, no):
        if not isinstance(c, dict):
            raise ValueError('unsupported NES condition')
        op = c.get('op')
        if op == 'not' and set(c) == {'op', 'condition'}:
            condition(c['condition'], no, yes)
        elif op == 'and' and set(c) == {'op', 'conditions'} and isinstance(c['conditions'], list):
            for child in c['conditions']:
                nxt = a.unique(); condition(child, nxt, no); a.label(nxt)
            a.jump(0x4c, yes)
        elif op == 'eq' and set(c) == {'op', 'left', 'right'}:
            width = width_for(c['left'], c['right'])
            for i in range(width // 8):
                operand(c['left'], width, i, 0xa9, 0xad)
                operand(c['right'], width, i, 0xc9, 0xcd)
                a.branch_false(0xf0, no)
            a.jump(0x4c, yes)
        elif op == 'bit_test' and set(c) == {'op', 'value', 'bit'}:
            bit = c['bit']; width = width_for(c['value'], 0)
            if type(bit) is not int or not 0 <= bit < width:
                raise ValueError('NES bit index outside operand')
            operand(c['value'], width, bit // 8, 0xa9, 0xad)
            a.emit(0x29, 1 << (bit % 8)); a.branch_false(0xd0, no); a.jump(0x4c, yes)
        else:
            raise ValueError('unsupported NES condition')

    def nodes(items):
        if not isinstance(items, list):
            raise ValueError('NES body must be a list')
        for node in items:
            if not isinstance(node, dict):
                raise ValueError('unsupported NES statement')
            op = node.get('op')
            if op == 'if' and set(node) <= {'id', 'op', 'condition', 'then', 'else', 'evidence'} and all(k in node for k in ('condition', 'then', 'else')):
                yes, no, end = a.unique(), a.unique(), a.unique()
                condition(node['condition'], yes, no); a.label(yes); nodes(node['then']); a.jump(0x4c, end)
                a.label(no); nodes(node['else']); a.label(end)
            elif op in ('set', 'add', 'subtract') and set(node) <= {'id', 'op', 'var', 'value', 'evidence'} and 'value' in node and node.get('var') in layout:
                if node['var'] == '$buttons':
                    raise ValueError('NES buttons are read-only')
                target = layout[node['var']]; width = target['width']
                if op == 'add': a.emit(0x18)
                if op == 'subtract': a.emit(0x38)
                for i in range(width // 8):
                    if op != 'set': a.absolute(0xad, target['address'] + i)
                    imm, absolute = {'set': (0xa9, 0xad), 'add': (0x69, 0x6d), 'subtract': (0xe9, 0xed)}[op]
                    operand(node['value'], width, i, imm, absolute)
                    a.absolute(0x8d, target['address'] + i)
            else:
                raise ValueError('unsupported NES statement')

    _runtime(a, layout, display_variable)
    a.label('logic_tick'); nodes(program.get('body')); a.emit(0x60)
    a.label('logic_tick_end')
    code = a.finish()
    start = a.labels['logic_tick'] - 0x8000
    end = a.labels['logic_tick_end'] - 0x8000
    cycles = _logic_cycles(code[start:end])
    if cycles > _MAX_LOGIC_CYCLES:
        raise ValueError('NES logic cycle budget exceeded')
    prg = bytearray([0xff]) * 0x8000; prg[:len(code)] = code
    for offset, label in ((0x7ffa, 'interrupt'), (0x7ffc, 'reset'), (0x7ffe, 'interrupt')):
        addr = a.labels[label]; prg[offset:offset + 2] = bytes((addr & 255, addr >> 8))
    chr_data = bytearray(0x2000); chr_data[:8] = b'\xff' * 8
    header = b'NES\x1a' + bytes((2, 1, 0, 0)) + bytes(8)
    return {'rom': header + bytes(prg) + bytes(chr_data),
            'symbols': {'reset': a.labels['reset'], 'nmi': a.labels['interrupt'],
                        'irq': a.labels['interrupt'], 'logic_tick': a.labels['logic_tick'],
                        'logic_tick_end': a.labels['logic_tick_end'],
                        'runtime_frame_counter': 0x7f0, 'runtime_ready': 0x7f2},
            'diagnostics': [], 'profile': {'mapper': 0, 'prg_bytes': 0x8000,
                'chr_bytes': 0x2000, 'variable_endian': 'little', 'display_variable': display_variable,
                'frame_counter_endian': 'little', 'screen': [256, 240],
                'logic_cycles_upper_bound': cycles, 'max_logic_cycles': _MAX_LOGIC_CYCLES}}
