"""Classic CHIP-8 instruction facts for the authored pilot's declared profile.

This is a static classifier, not an execution or historical-compatibility claim.
The patterns derive from examples/chip8_pilot/chip8lab/decoder.py; legacy SYS,
SCHIP and XO extensions are outside this profile.
"""

PROFILE = 'chip8-classic-pilot-default-v1'
MEMORY_SIZE = 0x1000
ROM_BASE = 0x200
MAX_ROM_SIZE = MEMORY_SIZE - ROM_BASE

# mask, value, family, presentation form. Specific encodings precede envelopes.
_PATTERNS = (
    (0xffff, 0x00e0, 'CLS', ''), (0xffff, 0x00ee, 'RET', ''),
    (0xf000, 0x1000, 'JP', 'nnn'), (0xf000, 0x2000, 'CALL', 'nnn'),
    (0xf000, 0x3000, 'SE_VX_KK', 'x,kk'), (0xf000, 0x4000, 'SNE_VX_KK', 'x,kk'),
    (0xf00f, 0x5000, 'SE_VX_VY', 'x,y'), (0xf000, 0x6000, 'LD_VX_KK', 'x,kk'),
    (0xf000, 0x7000, 'ADD_VX_KK', 'x,kk'), (0xf00f, 0x8000, 'LD_VX_VY', 'x,y'),
    (0xf00f, 0x8001, 'OR', 'x,y'), (0xf00f, 0x8002, 'AND', 'x,y'),
    (0xf00f, 0x8003, 'XOR', 'x,y'), (0xf00f, 0x8004, 'ADD_VX_VY', 'x,y'),
    (0xf00f, 0x8005, 'SUB', 'x,y'), (0xf00f, 0x8006, 'SHR', 'x,y'),
    (0xf00f, 0x8007, 'SUBN', 'x,y'), (0xf00f, 0x800e, 'SHL', 'x,y'),
    (0xf00f, 0x9000, 'SNE_VX_VY', 'x,y'), (0xf000, 0xa000, 'LD_I', 'nnn'),
    (0xf000, 0xb000, 'JP_V0', 'nnn'), (0xf000, 0xc000, 'RND', 'x,kk'),
    (0xf000, 0xd000, 'DRW', 'x,y,n'), (0xf0ff, 0xe09e, 'SKP', 'x'),
    (0xf0ff, 0xe0a1, 'SKNP', 'x'), (0xf0ff, 0xf007, 'LD_VX_DT', 'x'),
    (0xf0ff, 0xf00a, 'WAIT_KEY', 'x'), (0xf0ff, 0xf015, 'LD_DT_VX', 'x'),
    (0xf0ff, 0xf018, 'LD_ST_VX', 'x'), (0xf0ff, 0xf01e, 'ADD_I_VX', 'x'),
    (0xf0ff, 0xf029, 'FONT', 'x'), (0xf0ff, 0xf033, 'BCD', 'x'),
    (0xf0ff, 0xf055, 'SAVE', 'x'), (0xf0ff, 0xf065, 'LOAD', 'x'),
)
_SKIP = frozenset(('SE_VX_KK', 'SNE_VX_KK', 'SE_VX_VY', 'SNE_VX_VY', 'SKP', 'SKNP'))


def decode(data: bytes, address: int) -> dict | None:
    """Return one static instruction fact, or None for an unsupported encoding.

    Memory via I and the V0-indexed jump remain unresolved without live state.
    A skip at the end of memory has no in-range static taken target.
    """
    if type(address) is not int or address < 0 or address >= MEMORY_SIZE - 1 or address & 1:
        return None
    if len(data) < 2:
        return None
    word = int.from_bytes(data[:2], 'big')
    match = next(((name, form) for mask, value, name, form in _PATTERNS
                  if word & mask == value), None)
    if match is None:
        return None
    family, form = match
    x, y, kk, nnn, n = (word >> 8) & 15, (word >> 4) & 15, word & 255, word & 0xfff, word & 15
    values = {'x': f'v{x:x}', 'y': f'v{y:x}', 'kk': f'0x{kk:02x}',
              'nnn': f'0x{nnn:03x}', 'n': f'0x{n:x}'}
    operands = ', '.join(values[item] for item in form.split(',') if item)
    mnemonic = family.lower()
    flow, target = 'next', None
    if family in _SKIP:
        flow = 'conditional'
        target = address + 4 if address + 4 < MEMORY_SIZE else None
    elif family in ('JP', 'CALL'):
        flow, target = ('jump' if family == 'JP' else 'call'), nnn
    elif family == 'JP_V0':
        flow = 'indirect_jump'
    elif family == 'RET':
        flow = 'return'
    references = []
    if target is not None:
        references.append(dict(operand_index=0 if family in ('JP', 'CALL') else -1,
                               role='code', target=target, width=2))
    # I-addressed accesses and dynamic code targets are intentionally not guessed.
    immediates = []
    for index, item in enumerate(form.split(',') if form else ()):
        if item in ('kk', 'nnn', 'n') and not (family in ('JP', 'CALL') and item == 'nnn'):
            immediates.append(dict(operand_index=index, value={'kk': kk, 'nnn': nnn, 'n': n}[item]))
    return dict(address=address, size=2, bytes=bytes(data[:2]).hex(), mnemonic=mnemonic,
                operands=operands, text=mnemonic + (' ' + operands if operands else ''),
                flow=flow, target=target, data_refs=[], references=references,
                immediates=immediates)
