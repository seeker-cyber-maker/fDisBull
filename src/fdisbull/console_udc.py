"""Native NES/Genesis compilation of an explicit, bounded UIL subset.

The backends generate instructions and console startup code. They neither
emulate a source console nor discover an arbitrary game's rules.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .interaction_il import validate_il

TARGETS = ('nes', 'genesis')
BUTTON_BITS = {'right': 0, 'left': 1, 'up': 2, 'down': 3, 'a': 4, 'b': 5, 'start': 6, 'select': 7}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate_console_program(program):
    validate_il(program)
    if program['role'] != 'uil' or program['resources'] or not 1 <= len(program['variables']) <= 32:
        raise ValueError('console UDC requires UIL, 1..32 variables and no resources')
    variables = program['variables']
    if any(v['type'] not in ('u8', 'u16') for v in variables.values()):
        raise ValueError('console UDC supports unsigned u8 and u16 variables only')
    if '$buttons' in variables and variables['$buttons']['type'] != 'u8':
        raise ValueError('$buttons is a reserved u8 controller input')
    count = 0

    def width(value):
        if type(value) is int and 0 <= value <= 65535:
            return None
        if isinstance(value, dict) and set(value) == {'var'} and value['var'] in variables:
            return int(variables[value['var']]['type'][1:])
        raise ValueError('unsupported console operand')

    def compatible(left, right):
        a, b = width(left), width(right)
        if a and b and a != b:
            raise ValueError('mixed-width console operands are unsupported')
        selected = a or b or 16
        for value in (left, right):
            if type(value) is int and value >= 1 << selected:
                raise ValueError('console operand literal exceeds selected width')
        return selected

    def condition(c, depth):
        nonlocal count
        count += 1
        if count > 256 or depth > 8:
            raise ValueError('console UDC node/depth budget exceeded')
        op = c['op']
        if op == 'eq':
            compatible(c['left'], c['right'])
        elif op == 'bit_test':
            selected = width(c['value']) or 16
            if not 0 <= c['bit'] < selected:
                raise ValueError('console bit test exceeds operand width')
        elif op == 'not':
            condition(c['condition'], depth + 1)
        elif op == 'and':
            for child in c['conditions']:
                condition(child, depth + 1)
        else:
            raise ValueError('unsupported console condition')

    def body(blocks, depth):
        nonlocal count
        for block in blocks:
            count += 1
            if count > 256 or depth > 8:
                raise ValueError('console UDC node/depth budget exceeded')
            if block['op'] in ('set', 'add', 'subtract'):
                if block['var'] == '$buttons':
                    raise ValueError('$buttons is read-only controller input')
                compatible({'var': block['var']}, block['value'])
            elif block['op'] == 'if':
                condition(block['condition'], depth + 1)
                body(block['then'], depth + 1)
                body(block['else'], depth + 1)
            else:
                raise ValueError('unsupported console operation: ' + block['op'])
    body(program['body'], 1)
    return program


def compile_console_rom(program: dict, *, target: str, display_variable: str | None = None) -> dict:
    """Return native ROM bytes and a portable metadata manifest, without writing."""
    if target not in TARGETS:
        raise ValueError('target must be nes or genesis')
    validate_console_program(program)
    if display_variable is not None and (display_variable not in program['variables'] or
                                        program['variables'][display_variable]['type'] != 'u8'):
        raise ValueError('display_variable must name a u8 variable')
    cursor = 0x300 if target == 'nes' else 0xff0000
    layout = {}
    for name in sorted(program['variables']):
        item = program['variables'][name]
        width = int(item['type'][1:])
        if width == 16 and cursor % 2:
            cursor += 1
        layout[name] = {'address': cursor, 'width': width, 'initial': item['initial']}
        cursor += width // 8
    if target == 'nes':
        from .udc_nes import build
    else:
        from .udc_genesis import build
    result = build(program, layout, display_variable=display_variable)
    from .roms import inspect_rom
    inspection = inspect_rom(result['rom'])
    if not inspection['valid']:
        raise RuntimeError('generated console cartridge failed structural inspection')
    manifest = {'format': 'fdisbull-console-udc-1', 'target': target,
        'program_sha256': hashlib.sha256(_encoded(program)).hexdigest(),
        'rom_sha256': hashlib.sha256(result['rom']).hexdigest(), 'rom_size': len(result['rom']),
        'profile': result['profile'], 'variables': layout, 'symbols': result['symbols'],
        'architectural_byte_order': 'little' if target == 'nes' else 'big',
        'button_bits': BUTTON_BITS, 'unsupported_buttons': [] if target == 'nes' else ['select'],
        'display_variable': display_variable, 'diagnostics': result['diagnostics'],
        'executed': False, 'validation_scope': 'compiled declared UIL subset and cartridge structure; runtime/timing require separate checks'}
    return {'rom': result['rom'], 'manifest': manifest}


def _private_directory(path):
    destination = Path(path).expanduser().resolve()
    if any((p / '.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('console compiler output must be outside Git worktrees')
    if destination.exists():
        raise ValueError('console compiler output directory must be new')
    if not destination.parent.is_dir():
        raise ValueError('console compiler output parent directory must exist')
    return destination


def write_console_rom(program: dict, *, target: str, output: str | Path,
                      display_variable: str | None = None) -> dict:
    destination = _private_directory(output)
    result = compile_console_rom(program, target=target, display_variable=display_variable)
    manifest = result['manifest']
    name = 'program.nes' if target == 'nes' else 'program.md'
    manifest['files'] = {'rom': name, 'uil': 'program.uil.json', 'manifest': 'manifest.json'}
    temporary = Path(tempfile.mkdtemp(prefix='.console-udc-', dir=destination.parent))
    try:
        (temporary / name).write_bytes(result['rom'])
        (temporary / 'program.uil.json').write_text(json.dumps(program, indent=2) + '\n')
        (temporary / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if destination.exists():
            raise ValueError('console compiler output appeared during compilation')
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'output_directory': str(destination), **manifest}


def compile_console_path(path: str | Path, **kwargs) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('expected one UIL JSON file at most 64 KiB')
    return write_console_rom(json.loads(path.read_text()), **kwargs)


def console_targets():
    return {'format': 'fdisbull-console-udc-targets-1', 'targets': list(TARGETS),
        'types': ['u8', 'u16'], 'operations': ['set', 'add', 'subtract', 'if'],
        'conditions': ['eq', 'bit_test', 'not', 'and'], 'variable_limit': 32,
        'node_limit': 256, 'depth_limit': 8,
        'scope': 'native compilation of an explicit UIL subset; not a complete source-console lifter or hardware conversion'}
