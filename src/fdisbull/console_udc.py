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


def validate_console_program(program, *, level=False):
    validate_il(program)
    variable_limit, node_limit, depth_limit = (64, 1024, 32) if level else (32, 256, 8)
    if program['role'] != 'uil' or program['resources'] or not 1 <= len(program['variables']) <= variable_limit:
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
        if count > node_limit or depth > depth_limit:
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
            if count > node_limit or depth > depth_limit:
                raise ValueError('console UDC node/depth budget exceeded')
            if block['op'] in ('set', 'add', 'subtract'):
                if block['var'] == '$buttons':
                    raise ValueError('$buttons is read-only controller input')
                compatible({'var': block['var']}, block['value'])
            elif block['op'] == 'lookup':
                if block['var'] == '$buttons':
                    raise ValueError('$buttons is read-only controller input')
                table = program['tables'][block['table']]
                if table['type'] != 'u8' or len(table['values']) != 256 or width(block['index']) not in (None, 8):
                    raise ValueError('NES lookup requires a 256-entry u8 table and u8 index')
            elif block['op'] == 'if':
                condition(block['condition'], depth + 1)
                body(block['then'], depth + 1)
                body(block['else'], depth + 1)
            else:
                raise ValueError('unsupported console operation: ' + block['op'])
    body(program['body'], 1)
    return program


def compile_console_rom(program: dict, *, target: str, display_variable: str | None = None,
                        scene: dict | None = None) -> dict:
    """Return native ROM bytes and a portable metadata manifest, without writing."""
    if target not in TARGETS:
        raise ValueError('target must be nes or genesis')
    validate_console_program(program, level=scene is not None)
    if target == 'genesis' and (scene is not None or program.get('tables')):
        raise ValueError('Genesis compiler does not support the NES level/table profile')
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
    if scene is not None:
        if display_variable is not None:
            raise ValueError('level scenes supply their own display bindings')
        from .udc_nes_level import build
    elif target == 'nes':
        from .udc_nes import build
    else:
        from .udc_genesis import build
    result = (build(program, layout, scene=scene) if scene is not None else
              build(program, layout, display_variable=display_variable))
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
    if scene is not None:
        manifest['scene_sha256'] = hashlib.sha256(_encoded(scene)).hexdigest()
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
                      display_variable: str | None = None, scene: dict | None = None) -> dict:
    destination = _private_directory(output)
    result = compile_console_rom(program, target=target, display_variable=display_variable, scene=scene)
    manifest = result['manifest']
    name = 'program.nes' if target == 'nes' else 'program.md'
    manifest['files'] = {'rom': name, 'uil': 'program.uil.json', 'manifest': 'manifest.json'}
    temporary = Path(tempfile.mkdtemp(prefix='.console-udc-', dir=destination.parent))
    try:
        (temporary / name).write_bytes(result['rom'])
        (temporary / 'program.uil.json').write_text(json.dumps(program, indent=2) + '\n')
        if scene is not None:
            manifest['files']['scene'] = 'scene.json'
            (temporary / 'scene.json').write_text(json.dumps(scene, indent=2) + '\n')
        (temporary / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if destination.exists():
            raise ValueError('console compiler output appeared during compilation')
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'output_directory': str(destination), **manifest}


def compile_console_path(path: str | Path, *, scene_path: str | Path | None = None,
                         region_path: str | Path | None = None, cc65_root: str | Path | None = None,
                         m68k_root: str | Path | None = None, **kwargs) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 8*1024*1024:
        raise ValueError('expected one UIL JSON file within its profile size limit')
    program=json.loads(path.read_text())
    if isinstance(program,dict) and program.get('format')=='fdisbull-genesis-replay-1':
        from .udc_genesis import replay_translation
        target=kwargs.pop('target',None)
        if (target not in TARGETS or scene_path is not None
                or kwargs.pop('display_variable',None) is not None):
            raise ValueError('Genesis replay profile requires a registered console target')
        if region_path is None:
            raise ValueError('Genesis replay requires the exact --region cartridge')
        return replay_translation(path,rom_path=region_path,target=target,
                                  cc65_root=cc65_root,m68k_root=m68k_root,**kwargs)
    if isinstance(program,dict) and program.get('format')=='fdisbull-shadowrun-opening-replay-1':
        target=kwargs.pop('target',None)
        output=kwargs.pop('output',None)
        if (target!='nes' or scene_path is not None or kwargs.pop('display_variable',None) is not None
                or m68k_root is not None):
            raise ValueError('Shadowrun opening replay is a registered NES-only profile')
        if region_path is None or cc65_root is None or output is None:
            raise ValueError('Shadowrun opening replay requires --region, --cc65-root and --output')
        if kwargs:
            raise ValueError('Unexpected Shadowrun opening compiler options')
        from .shadowrun_replay import build_opening
        return build_opening(path,rom_path=region_path,cc65_root=cc65_root,output=output)
    if isinstance(program,dict) and program.get('format')=='fdisbull-game-il-2':
        target=kwargs.pop('target',None)
        if target not in TARGETS or scene_path is not None or kwargs.pop('display_variable',None) is not None:
            raise ValueError('Procedural game profile requires a console target with its own globe presentation')
        if region_path is None:raise ValueError('Procedural game compilation requires the original --region cartridge')
        region=Path(region_path).expanduser().resolve()
        if not region.is_file() or region.stat().st_size!=524288:raise ValueError('Expected qualified 512KiB source region')
        if target=='genesis':
            if m68k_root is None or cc65_root is not None:
                raise ValueError('Genesis procedural game requires explicit --m68k-root')
            from .udc_genesis_game import write_genesis_game
            return write_genesis_game(program,region.read_bytes(),m68k_root=m68k_root,**kwargs)
        if m68k_root is not None:raise ValueError('--m68k-root applies to the Genesis target')
        from .udc_nes_game import write_nes_game
        return write_nes_game(program,region.read_bytes(),cc65_root=cc65_root,**kwargs)
    if path.stat().st_size>65536:raise ValueError('expected one UIL-v1 JSON file at most 64 KiB')
    if region_path is not None or cc65_root is not None or m68k_root is not None:
        raise ValueError('region/toolchain options apply only to procedural game UIL')
    if scene_path is not None:
        scene_path = Path(scene_path)
        if not scene_path.is_file() or scene_path.stat().st_size > 65536:
            raise ValueError('expected one scene JSON file at most 64 KiB')
        if 'scene' in kwargs:
            raise ValueError('supply scene or scene_path, not both')
        kwargs['scene'] = json.loads(scene_path.read_text())
    return write_console_rom(program, **kwargs)


def console_targets():
    return {'format': 'fdisbull-console-udc-targets-1', 'targets': list(TARGETS),
        'types': ['u8', 'u16'], 'operations': ['set', 'add', 'subtract', 'if'],
        'conditions': ['eq', 'bit_test', 'not', 'and'], 'variable_limit': 32,
        'node_limit': 256, 'depth_limit': 8,
        'additional_profiles': {'nes-level': {'target': 'nes', 'scene': 'fdisbull-console-scene-1',
            'operations': ['set', 'add', 'subtract', 'lookup', 'if'],
            'variable_limit': 64, 'node_limit': 1024, 'depth_limit': 32,
            'table_type': 'u8', 'table_entries': 256},
            'miniplanets-full': {'target':'nes','format':'fdisbull-game-il-2','mapper':4,
                'additional_target':'genesis','genesis_toolchain':'m68k-elf GCC, -m68000 -mshort',
                'procedures':True,'mutable_arrays':True,'external_toolchain':'cc65 with wrapped-call bank support',
                'source_contract':'exact reviewed Miniplanets REV04 profile; original region required'},
            'genesis-replay': {'target':'nes','format':'fdisbull-genesis-replay-1',
                'additional_target':'genesis',
                'source_platform':'genesis','semantic_modules':['game','audio','presentation','psg'],
                'source_contract':'registered identity-bound source/model/lowering; explicit trusted tools and original ROM required'},
            'shadowrun-opening': {'target':'nes','format':'fdisbull-shadowrun-opening-replay-1',
                'source_platform':'genesis','source_profile':'shadowrun-genesis-opening-stoker-assisted-v1',
                'interaction':'assisted captured opening and guarded Stoker request/UI projection',
                'source_contract':'one exact ROM, provenance-bound RAM/VDP snapshot and bounded observed atlas; explicit cc65 and original ROM required',
                'whole_game_automatic_lifting':False}},
        'scope': 'native compilation of an explicit UIL subset; not a complete source-console lifter or hardware conversion'}
