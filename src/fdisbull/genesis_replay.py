"""Private, source-bound Genesis -> executable UIL -> console replay bundles.

The registry is deliberately explicit. Container recognition is not semantic
recovery; a larger or different ROM remains unsupported until its own lifter,
resource bindings, lowering and independent qualification have been added.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

from .game_il import canonical

FORMAT = 'fdisbull-genesis-replay-1'
PROFILE = 'miniplanets-remix-rev04'
RECIPE = 'miniplanets-procedural-nes-1'
GENESIS_RECIPE = 'miniplanets-procedural-genesis-1'
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
TOOL_NAMES = ('cc65', 'ca65', 'ld65', 'od65')
TOOL_INPUTS = (*('bin/' + n for n in TOOL_NAMES), 'lib/nes.lib', 'asminc/longbranch.mac')
M68K_TOOL_NAMES = ('gcc', 'as', 'ld', 'nm', 'objcopy', 'readelf')
M68K_VERSION = '16.2.0'
OTOOL = Path('/usr/bin/otool')
PACKAGE = Path(__file__).resolve().parent
MODULE_PATHS = {
    'game': 'uil/game.uil.json',
    'audio': 'uil/audio.uil.json',
    'presentation': 'uil/presentation.uil.json',
    'psg': 'uil/psg.uil.json',
    'scene': 'uil/scene.json',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _record(raw):
    return {'size': len(raw), 'sha256': _sha(raw)}


def _record_file(path, limit=MAX_FILE):
    path = Path(path)
    before = path.stat()
    if not path.is_file() or before.st_size > limit:
        raise ValueError('File exceeds the bounded input limit')
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError('File exceeds the bounded input limit')
            digest.update(chunk)
    after = path.stat()
    if size != before.st_size or after.st_size != before.st_size:
        raise ValueError('File changed while its identity was read')
    return {'size': size, 'sha256': digest.hexdigest()}


def _tool_env():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('DYLD_', 'LD_')) and key not in {
               'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH',
               'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
           }}
    env['LC_ALL'] = 'C'
    return env


def _json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('Replay JSON exceeds the bounded file limit')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError('Replay JSON exceeds the bounded file limit')
    return json.loads(raw)


def _source(path):
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Expected one original ROM within the 64 MiB inspection limit')
    raw = source.read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Original ROM grew beyond the inspection limit')
    return source, raw


def profiles():
    from .udl_miniplanets import ROM_SHA256
    return {
        'format': 'fdisbull-genesis-replay-profiles-1',
        'source_platform': 'genesis',
        'profiles': [{
            'id': PROFILE, 'source_size': 524288, 'source_sha256': ROM_SHA256,
            'recovery': 'reviewed source-bound specialization',
            'target': 'nes', 'recipe': RECIPE,
            'game_format': 'fdisbull-game-il-2',
            'semantic_modules': ['game', 'audio', 'presentation', 'psg'],
            'variants': ['efficient', 'baseline', 'mixed-qualified'],
            'whole_rom_automatic_lifting': False,
            'additional_target': 'genesis',
            'genesis_recipe': GENESIS_RECIPE,
        }],
        'genesis_native_output': 'reviewed procedural full-game compiler, exact-profile only',
        'unknown_rom_policy': 'inspect container, report unsupported; never substitute this game profile',
    }


def inspect_source(path):
    from .roms import inspect_rom
    source, raw = _source(path)
    facts = inspect_rom(raw)
    known = profiles()['profiles'][0]
    matches = len(raw) == known['source_size'] and _sha(raw) == known['source_sha256']
    if source.read_bytes() != raw:
        raise ValueError('Original ROM changed during preflight')
    return {
        'format': 'fdisbull-genesis-replay-preflight-1',
        'source': _record(raw), 'inspection': facts,
        'supported': matches, 'profile': PROFILE if matches else None,
        'status': 'recognized-reviewed-profile' if matches else 'unsupported-semantic-profile',
        'reason': 'Exact reviewed source identity' if matches else
                  'Parsing does not recover game rules, resource codecs, memory/device semantics or a target adapter',
        'executed': False,
    }


def _versions():
    return {'python': list(sys.version_info[:2]),
            'pycparser': importlib.metadata.version('pycparser')}


def _engine_bytes():
    """Capture inert implementation files, never import Python from a bundle."""
    paths = list(PACKAGE.glob('*.py'))
    paths += [p for p in (PACKAGE / 'game_sources').iterdir() if p.is_file()]
    paths += [PACKAGE / 'data' / name for name in (
        'miniplanets_full_contract.json', 'miniplanets_presentation.uil.json',
        'miniplanets_psg.uil.json')]
    return {p.relative_to(PACKAGE).as_posix(): p.read_bytes() for p in sorted(paths)}


def _recipe(variant, procedures, target='nes'):
    if variant not in ('efficient', 'baseline'):
        raise ValueError('Expected efficient or baseline variant')
    if target not in ('nes', 'genesis'):
        raise ValueError('Expected NES or Genesis target')
    if procedures is not None:
        if (variant != 'efficient' or not isinstance(procedures, dict)
                or len(procedures) > 512
                or any(not isinstance(k, str) or v not in ('baseline', 'efficient')
                       for k, v in procedures.items())):
            raise ValueError('Expected a bounded reviewed procedure-to-variant mapping')
    recipe = {
        'id': RECIPE if target == 'nes' else GENESIS_RECIPE,
        'source_profile': PROFILE, 'target': target,
        'variant': variant, 'procedures': procedures,
        'integer_model': 'cc65-int16-long32',
        'lowerings': {
            'game': 'reviewed procedural UIL to C and native 6502 intrinsics',
            'audio': 'typed source events with reviewed NES arrangement',
            'presentation': 'registered native planner/clear specialization of the executable reference',
            'psg': 'registered native PSG specialization of the executable reference',
        },
        'limits': [
            'Only this exact reviewed ROM/profile has a whole-game NES lowering',
            'Presentation geometry and NES cycle budgets are not Genesis hardware semantics',
            'PSG UIL covers the declared subroutines, not the complete FM/PCM/APU driver',
            'Reference/native conformance and original-CPU/runtime checks are separate qualification',
        ],
    }
    if target == 'genesis':
        recipe['lowerings']['game'] = 'reviewed procedural UIL to C and native 68000 code'
        recipe['lowerings']['audio'] = 'original source-bound Sona hardware driver retained at exact ROM addresses'
        recipe['lowerings']['presentation'] = 'reviewed quantized globe data adapter for Genesis VDP'
        recipe['lowerings']['psg'] = 'typed bounded reference module; Genesis audio remains on retained Sona driver'
        recipe['limits'] = [
            'Only this exact reviewed ROM/profile has a whole-game Genesis lowering',
            'Presentation is adapted quantized globe output, not original Genesis pixel parity',
            'PSG UIL covers the declared subroutines, not the complete FM/PCM/Sona driver',
            'Reference/native conformance and original-CPU/runtime checks are separate qualification',
            'Original unused game code is retained as inert data/code and is not the new rules implementation',
            'Genesis audio uses the preserved original Sona/Z80 device driver; new audio logic is not claimed',
        ]
    return recipe


def _programs(rom, recipe):
    from .udl_miniplanets_full import checked_rom, lift_full_game, mix_full_game_variants
    from .miniplanets_audio import recover_audio
    from .presentation_il import lift_presentation
    from .psg_il import lift_psg
    checked_rom(rom)
    result = (mix_full_game_variants(rom, recipe['procedures'])
              if recipe['procedures'] is not None else
              lift_full_game(rom, variant=recipe['variant']))
    return {'game': result['program'], 'scene': result['scene'],
            'audio': recover_audio(rom), 'presentation': lift_presentation(),
            'psg': lift_psg()}


def _verify_module_sources(modules, engine):
    units = modules['game']['evidence']['authoring_units']
    for name, digest in units.items():
        if engine['game_sources/' + name]['sha256'] != digest:
            raise ValueError('Game authoring input changed during semantic capture')
    for name, source in (('presentation', 'miniplanets_presentation_uil.c'),
                         ('psg', 'miniplanets_psg_uil.c')):
        if (modules[name].get('evidence', {}).get('source_sha256') !=
                engine['game_sources/' + source]['sha256']):
            raise ValueError('Semantic source changed during capture: ' + name)


def _safe_payload(root, name):
    if (not isinstance(name, str) or not name or len(name) > 512
            or '\\' in name or '\x00' in name
            or any(part in ('', '.', '..') for part in name.split('/'))
            or PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe replay payload path')
    p = root
    for part in name.split('/'):
        p = p / part
        if p.is_symlink():
            raise ValueError('Replay payload symlinks are not accepted')
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('Replay payload escapes its bundle')
    return p


def _write_file(root, name, raw, *, executable=False):
    if len(raw) > MAX_FILE:
        raise ValueError('Replay payload exceeds the bounded file limit')
    path = _safe_payload(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o500 if executable else 0o400)
    return _record(raw)


def _m68k_inputs(root):
    names = {'bin/m68k-elf-' + name for name in M68K_TOOL_NAMES}
    names |= {
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/cc1',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/collect2',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/liblto_plugin.so',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/liblto_plugin.la',
    }
    for relative in ('lib/gcc/m68k-elf/' + M68K_VERSION,
                     'm68k-elf/bin', 'm68k-elf/lib/ldscripts'):
        base = root / relative
        if not base.is_dir():
            raise ValueError('Prepared m68k toolchain is missing ' + relative)
        for path in base.rglob('*'):
            if path.is_file() or path.is_symlink():
                names.add(path.relative_to(root).as_posix())
    resolved = {}
    for name in sorted(names):
        path = root / name
        if not path.exists():
            raise ValueError('Prepared trusted m68k root is missing ' + name)
        actual = path.resolve()
        if not actual.is_relative_to(root):
            raise ValueError('Prepared m68k toolchain has an external symlink: ' + name)
        if not actual.is_file():
            raise ValueError('Prepared m68k toolchain input is not a file: ' + name)
        _record_file(actual)
        with actual.open('rb') as stream:
            raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE or len(raw) != actual.stat().st_size:
            raise ValueError('Prepared m68k input changed or exceeds the file limit: ' + name)
        resolved[name] = raw
    return resolved


def _host_tool_dependencies(root, inputs):
    """Bind non-system dylibs used by the prepared macOS cross compiler."""
    result = {'platform': sys.platform, 'machine': platform.machine(),
              'dependencies': []}
    if sys.platform != 'darwin':
        raise ValueError('This prepared m68k toolchain is qualified only on macOS')
    if not OTOOL.is_file():
        raise ValueError('Required macOS otool is unavailable')
    inspected = [name for name in inputs if name.startswith(
        ('bin/m68k-elf-', 'libexec/gcc/m68k-elf/' + M68K_VERSION + '/cc1',
         'libexec/gcc/m68k-elf/' + M68K_VERSION + '/collect2',
         'm68k-elf/bin/'))]
    seen = set()
    for name in inspected:
        path = root / name
        process = subprocess.run([str(OTOOL), '-L', str(path)], capture_output=True,
                                 text=True, timeout=30, env=_tool_env())
        if process.returncode:
            raise ValueError('Could not inspect host dependencies for ' + name)
        for line in process.stdout.splitlines()[1:]:
            dependency = line.strip().split(' (compatibility version', 1)[0]
            if dependency.startswith(('/usr/lib/', '/System/Library/')):
                continue
            if not dependency.startswith('/'):
                raise ValueError('Unresolved host library reference: ' + dependency)
            dep_path = Path(dependency)
            if not dep_path.is_file():
                raise ValueError('Missing host dependency: ' + dependency)
            if dependency not in seen:
                seen.add(dependency)
                result['dependencies'].append({'path': dependency,
                                               **_record_file(dep_path)})
    result['dependencies'].sort(key=lambda item: item['path'])
    return result


def _verify_host_tool_dependencies(expected):
    if (not isinstance(expected, dict) or set(expected) !=
            {'platform', 'machine', 'dependencies'} or
            expected.get('platform') != sys.platform or
            expected.get('machine') != platform.machine()):
        raise ValueError('Host platform differs from the captured Genesis toolchain')
    deps = expected.get('dependencies')
    if not isinstance(deps, list):
        raise ValueError('Missing captured Genesis host dependency inventory')
    seen = set()
    for item in deps:
        path = item.get('path') if isinstance(item, dict) else None
        if (not isinstance(item, dict) or set(item) != {'path', 'size', 'sha256'} or
                not isinstance(path, str) or not Path(path).is_absolute() or
                path in seen or type(item.get('size')) is not int or
                not 0 <= item['size'] <= MAX_FILE or
                not isinstance(item.get('sha256'), str) or len(item['sha256']) != 64):
            raise ValueError('Invalid host dependency identity')
        seen.add(path)
        if not Path(path).is_file():
            raise ValueError('Captured Genesis host dependency is unavailable')
        if _record_file(path) != {k: item.get(k) for k in ('size', 'sha256')}:
            raise ValueError('Captured Genesis host dependency changed: ' + path)


def _capture_tools(trusted_root, destination, target='nes'):
    """Copy from the explicit trusted path, never execute a bundle-supplied tool."""
    root = Path(trusted_root).expanduser().resolve()
    result = {}
    metadata = None
    if target == 'nes':
        inputs = TOOL_INPUTS
    elif target == 'genesis':
        payloads = _m68k_inputs(root)
        inputs = tuple(payloads)
        metadata = _host_tool_dependencies(root, payloads)
    else:
        raise ValueError('Expected NES or Genesis toolchain target')
    total = 0
    for name in inputs:
        path = root / name
        if not path.is_file():
            raise ValueError('Prepared trusted ' + target + ' root is missing ' + name)
        raw = payloads[name] if target == 'genesis' else path.read_bytes()
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError('Prepared trusted toolchain exceeds replay capture limits')
        result[name] = _write_file(
            destination, name, raw,
            executable=(target == 'genesis' and
                        (name.startswith(('bin/', 'm68k-elf/bin/')) or
                         name.endswith(('/cc1', '/collect2', '.so')))) or
                       (name.startswith('bin/') and name.split('/')[-1] in TOOL_NAMES))
    return result, metadata


def _verify_tools(root, expected, target):
    required = set(TOOL_INPUTS) if target == 'nes' else set(_m68k_input_names())
    if (not isinstance(expected, dict) or not required.issubset(expected)
            or (target == 'nes' and set(expected) != required)
            or (target == 'genesis' and any(not (
                name.startswith('bin/m68k-elf-') or
                name.startswith('libexec/gcc/m68k-elf/' + M68K_VERSION + '/') or
                name.startswith('lib/gcc/m68k-elf/' + M68K_VERSION + '/') or
                name.startswith('m68k-elf/bin/') or
                name.startswith('m68k-elf/lib/ldscripts/')
            ) for name in expected))):
        raise ValueError('Unexpected toolchain contract')
    for name, record in expected.items():
        path = _safe_payload(root, name)
        if not path.is_file() or _record(path.read_bytes()) != record:
            raise ValueError('Captured toolchain changed: ' + name)


def _verify_engine(expected):
    current = {name: _record(raw) for name, raw in _engine_bytes().items()}
    if current != expected:
        raise ValueError('Installed implementation differs from replay lock; select the matching tool version')


def _m68k_input_names():
    # Exact fixed compiler closure; the full GCC target runtime tree is added at
    # capture time from the trusted root and recorded in the lock.
    return tuple(sorted({
        'bin/m68k-elf-' + name for name in M68K_TOOL_NAMES
    } | {
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/cc1',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/collect2',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/liblto_plugin.so',
        'libexec/gcc/m68k-elf/' + M68K_VERSION + '/liblto_plugin.la',
    }))


def _verify_compilation(manifest, engine, tools, target):
    for name, digest in manifest['adapter_sources'].items():
        if engine['game_sources/' + name]['sha256'] != digest:
            raise ValueError('Compiler captured an adapter outside the replay lock')
    if target == 'nes':
        for name, record in manifest['toolchain'].items():
            if tools['bin/' + name]['sha256'] != record['sha256']:
                raise ValueError('Compiler/toolchain binding differs')
        if manifest['runtime_resources']['nes.lib']['sha256'] != tools['lib/nes.lib']['sha256']:
            raise ValueError('Compiler runtime binding differs')
    else:
        for name, record in manifest['toolchain'].items():
            relative = 'bin/m68k-elf-' + name
            if relative not in tools or tools[relative]['sha256'] != record['sha256']:
                raise ValueError('Compiler/toolchain binding differs: ' + name)
        runtime = manifest['runtime_resources']['libgcc.a']['sha256']
        runtime_path = 'lib/gcc/m68k-elf/' + M68K_VERSION + '/m68000/libgcc.a'
        if runtime_path not in tools or runtime != tools[runtime_path]['sha256']:
            raise ValueError('Genesis GCC runtime binding differs')


def _publish(temporary, destination):
    if destination.exists():
        raise ValueError('Replay output appeared during compilation')
    temporary.rename(destination)


def write_bundle(path, output, *, cc65_root=None, m68k_root=None,
                 target='nes', profile=PROFILE, variant='efficient',
                 procedures=None):
    """Lift, capture, compile and seal a new private replay bundle."""
    from .console_udc import _private_directory
    destination = _private_directory(output)
    if profile != PROFILE:
        raise ValueError('Unsupported Genesis semantic profile')
    if target not in ('nes', 'genesis'):
        raise ValueError('Expected NES or Genesis target')
    toolchain_root = cc65_root if target == 'nes' else m68k_root
    if toolchain_root is None:
        raise ValueError('A trusted ' + target + ' toolchain root is required')
    source, rom = _source(path)
    recipe = _recipe(variant, procedures, target=target)
    engine_raw = _engine_bytes()
    engine = {name: _record(raw) for name, raw in engine_raw.items()}
    modules = _programs(rom, recipe)  # reject unknown source before tools or outputs
    _verify_module_sources(modules, engine)
    _verify_engine(engine)
    temporary = Path(tempfile.mkdtemp(prefix='.genesis-replay-', dir=destination.parent))
    try:
        artifacts = {}
        for name, relative in MODULE_PATHS.items():
            raw = canonical(modules[name]) + b'\n'
            artifacts[name] = {'path': relative, **_write_file(temporary, relative, raw),
                               'canonical_sha256': _sha(canonical(modules[name]))}
        for name, raw in engine_raw.items():
            _write_file(temporary, 'captured/engine/' + name, raw)
        tool_root = temporary / 'captured/toolchain'
        tools, host_dependencies = (
            _capture_tools(toolchain_root, tool_root) if target == 'nes' else
            _capture_tools(toolchain_root, tool_root, target))
        if target == 'nes':
            from .udc_nes_game import build_nes_game
            manifest = build_nes_game(modules['game'], rom, temporary / 'native',
                                      cc65_root=tool_root)
            output_path = 'native/program.nes'
        else:
            from .udc_genesis_game import build_genesis_game
            manifest = build_genesis_game(modules['game'], rom, temporary / 'native',
                                          m68k_root=tool_root)
            output_path = 'native/program.md'
        _verify_compilation(manifest, engine, tools, target)
        _verify_tools(tool_root, tools, target)
        if target == 'genesis':
            _verify_host_tool_dependencies(host_dependencies)
        _verify_engine(engine)
        if source.read_bytes() != rom:
            raise ValueError('Original ROM changed during bundle generation')
        files = {}
        for p in sorted(temporary.rglob('*')):
            if p.is_file():
                files[p.relative_to(temporary).as_posix()] = _record(p.read_bytes())
        if sum(r['size'] for r in files.values()) > MAX_TOTAL or len(files) > 2048:
            raise ValueError('Replay bundle exceeds its total payload budget')
        lock = {
            'format': FORMAT, 'profile': PROFILE, 'recipe': recipe,
            'source': {'platform': 'genesis', **_record(rom)},
            'original_region': 'external; provide the exact original ROM for replay',
            'modules': artifacts, 'engine': engine, 'versions': _versions(),
            'toolchain': tools, 'toolchain_host': host_dependencies, 'files': files,
            'expected_output': {'path': output_path,
                                **_record((temporary / output_path).read_bytes())},
            'qualification': {
                'source_to_uil': 'reviewed identity-bound specialization, not automatic whole-ROM recovery',
                'semantic_modules': 'executable typed references; registered native specializations',
            'native_build': 'completed; target-specific output hash bound',
                'native_execution': 'not run by bundle creation',
                'proof': 'No whole-game formal-equivalence or physical-hardware claim',
            },
            'private_contains_game_data': True,
        }
        raw = canonical(lock) + b'\n'
        (temporary / 'replay.json').write_bytes(raw)
        _publish(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'format': FORMAT, 'output_directory': str(destination),
            'lock_sha256': _sha(raw), 'source_sha256': _sha(rom),
            'program_sha256': artifacts['game']['canonical_sha256'],
            'rom_sha256': lock['expected_output']['sha256'],
            'modules': {k: {'path': v['path'], 'sha256': v['canonical_sha256']}
                        for k, v in artifacts.items()},
            'target': target, 'executed': False}


def _load_bundle(path):
    requested = Path(path).expanduser()
    if requested.is_symlink():
        raise ValueError('Replay lock symlinks are not accepted')
    given = requested.resolve()
    root = given if given.is_dir() else given.parent
    lock_path = root / 'replay.json' if given.is_dir() else given
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError('Expected a replay bundle directory or replay.json')
    if not lock_path.is_file() or lock_path.stat().st_size > MAX_FILE:
        raise ValueError('Replay lock exceeds the bounded file limit')
    with lock_path.open('rb') as stream:
        lock_raw = stream.read(MAX_FILE + 1)
    if len(lock_raw) > MAX_FILE:
        raise ValueError('Replay lock exceeds the bounded file limit')
    lock = json.loads(lock_raw)
    if (not isinstance(lock, dict) or lock.get('format') != FORMAT
            or lock.get('profile') != PROFILE):
        raise ValueError('Unsupported replay lock')
    recipe = lock.get('recipe')
    if (not isinstance(recipe, dict) or
            recipe != _recipe(recipe.get('variant'), recipe.get('procedures'),
                               target=recipe.get('target'))):
        raise ValueError('Replay recipe is not a registered lowering contract')
    target = recipe['target']
    files = lock.get('files')
    if not isinstance(files, dict) or not 1 <= len(files) <= 2048:
        raise ValueError('Invalid replay payload inventory')
    total = 0
    for name, expected in files.items():
        payload = _safe_payload(root, name)
        if (not isinstance(expected, dict) or set(expected) != {'size', 'sha256'}
                or type(expected['size']) is not int or not 0 <= expected['size'] <= MAX_FILE):
            raise ValueError('Invalid replay file identity')
        total += expected['size']
        if total > MAX_TOTAL:
            raise ValueError('Replay bundle exceeds total payload limit')
        if (not payload.is_file() or payload.stat().st_size != expected['size']
                or _record(payload.read_bytes()) != expected):
            raise ValueError('Missing or changed replay payload: ' + name)
    engine = lock.get('engine')
    tools = lock.get('toolchain')
    required_tools = set(TOOL_INPUTS) if target == 'nes' else set(_m68k_input_names())
    if (not isinstance(engine, dict) or not engine or not isinstance(tools, dict)
            or not required_tools.issubset(tools)
            or (target == 'nes' and set(tools) != required_tools)):
        raise ValueError('Missing captured implementation/toolchain inventory')
    for prefix, inventory in (('captured/engine/', engine),
                              ('captured/toolchain/', tools)):
        for name, expected in inventory.items():
            captured = prefix + name
            _safe_payload(root, captured)
            if files.get(captured) != expected:
                raise ValueError('Captured input is missing or unbound: ' + captured)
    modules = lock.get('modules')
    if not isinstance(modules, dict) or set(modules) != set(MODULE_PATHS):
        raise ValueError('Missing semantic UIL module')
    for name, expected_path in MODULE_PATHS.items():
        item = modules[name]
        if (not isinstance(item, dict) or item.get('path') != expected_path
                or {k: item.get(k) for k in ('size', 'sha256')} != files.get(expected_path)):
            raise ValueError('Invalid semantic module binding')
        data = _json(_safe_payload(root, expected_path))
        if _sha(canonical(data)) != item.get('canonical_sha256'):
            raise ValueError('Changed canonical semantic module')
    output_path = 'native/program.nes' if target == 'nes' else 'native/program.md'
    output = lock.get('expected_output', {})
    if (not isinstance(output, dict) or output.get('path') != output_path
            or {k: output.get(k) for k in ('size', 'sha256')} != files.get(output_path)):
        raise ValueError('Invalid expected cartridge binding')
    host = lock.get('toolchain_host')
    if target == 'genesis':
        if (not isinstance(host, dict) or set(host) !=
                {'platform', 'machine', 'dependencies'} or
                not isinstance(host.get('dependencies'), list)):
            raise ValueError('Invalid Genesis host dependency contract')
        for item in host['dependencies']:
            if (not isinstance(item, dict) or set(item) !=
                    {'path', 'size', 'sha256'} or
                    not isinstance(item.get('path'), str) or
                    not Path(item['path']).is_absolute() or
                    type(item.get('size')) is not int or
                    not 0 <= item['size'] <= MAX_FILE or
                    not isinstance(item.get('sha256'), str) or
                    len(item['sha256']) != 64):
                raise ValueError('Invalid Genesis host dependency identity')
    elif host is not None:
        raise ValueError('Unexpected host dependency contract for NES toolchain')
    return root, lock, _record(lock_raw)


def inspect_bundle(path):
    """Validate retained bytes only; do not execute tools or expose game payloads."""
    _, lock, identity = _load_bundle(path)
    return {'format': FORMAT, 'lock': identity, 'source': lock['source'],
            'recipe': lock['recipe'], 'modules': {
                k: {'path': v['path'], 'sha256': v['canonical_sha256']}
                for k, v in lock['modules'].items()},
            'expected_rom_sha256': lock['expected_output']['sha256'],
            'target': lock['recipe']['target'],
            'payload_files_checked': len(lock['files']), 'payloads_intact': True,
            'host_tool_dependencies_verified': False,
            'implementation_match': lock.get('engine') ==
                {k: _record(v) for k, v in _engine_bytes().items()},
            'qualification_claims': lock.get('qualification', {}),
            'qualification_claims_verified': False,
            'native_execution': 'not run by inspection',
            'executed': False}


def replay_bundle(path, output, *, rom_path, cc65_root=None, m68k_root=None,
                  target='nes'):
    """Rebuild under a matching implementation and explicit trusted toolchain."""
    from .console_udc import _private_directory
    destination = _private_directory(output)
    root, lock, lock_identity = _load_bundle(path)
    if target != lock['recipe']['target']:
        raise ValueError('Replay target differs from the locked recipe')
    toolchain_root = cc65_root if target == 'nes' else m68k_root
    if toolchain_root is None:
        raise ValueError('A trusted ' + target + ' toolchain root is required')
    _verify_engine(lock.get('engine'))
    if lock.get('versions') != _versions():
        raise ValueError('Replay parser/Python version differs from the lock')
    source, rom = _source(rom_path)
    if lock.get('source') != {'platform': 'genesis', **_record(rom)}:
        raise ValueError('Original ROM identity differs from replay lock')
    modules = _programs(rom, lock['recipe'])
    _verify_module_sources(modules, lock['engine'])
    for name, relative in MODULE_PATHS.items():
        if (_safe_payload(root, relative).read_bytes() != canonical(modules[name]) + b'\n'):
            raise ValueError('UIL differs from its registered source/model: ' + name)
    temporary = Path(tempfile.mkdtemp(prefix='.genesis-build-', dir=destination.parent))
    try:
        tools, host_dependencies = (
            _capture_tools(toolchain_root, temporary / 'trusted-toolchain')
            if target == 'nes' else
            _capture_tools(toolchain_root, temporary / 'trusted-toolchain', target))
        if tools != lock['toolchain']:
            raise ValueError('Explicit trusted toolchain differs from replay lock')
        if host_dependencies != lock.get('toolchain_host'):
            raise ValueError('Genesis host dependencies differ from replay lock')
        if target == 'genesis':
            _verify_host_tool_dependencies(host_dependencies)
        if target == 'nes':
            from .udc_nes_game import build_nes_game
            manifest = build_nes_game(modules['game'], rom, temporary / 'native',
                                      cc65_root=temporary / 'trusted-toolchain')
            output_path = 'native/program.nes'
        else:
            from .udc_genesis_game import build_genesis_game
            manifest = build_genesis_game(modules['game'], rom, temporary / 'native',
                                          m68k_root=temporary / 'trusted-toolchain')
            output_path = 'native/program.md'
        _verify_compilation(manifest, lock['engine'], tools, target)
        output_identity = _record((temporary / output_path).read_bytes())
        if output_identity != {k: lock['expected_output'][k] for k in ('size', 'sha256')}:
            raise ValueError('Replayed native cartridge differs from locked output')
        _verify_tools(temporary / 'trusted-toolchain', tools, target)
        if target == 'genesis':
            _verify_host_tool_dependencies(host_dependencies)
        _verify_engine(lock['engine'])
        _, final_lock, final_identity = _load_bundle(root)
        if final_lock != lock or final_identity != lock_identity or source.read_bytes() != rom:
            raise ValueError('Replay input changed during compilation')
        receipt = {'format': 'fdisbull-genesis-replay-result-1',
                   'recipe': lock['recipe']['id'], 'target': target,
                   'lock': lock_identity,
                   'source_sha256': _sha(rom),
                   'program_sha256': lock['modules']['game']['canonical_sha256'],
                   'rom_sha256': output_identity['sha256'],
                   'rom_bytes_match': True, 'inputs_unchanged': True,
                   'trusted_toolchain_matched': True,
                   'executed_bundle_code': False,
                   'native_execution': 'not run; separate original/native verification required',
                   'output_directory': str(destination)}
        (temporary / 'replay-result.json').write_bytes(canonical(receipt) + b'\n')
        _publish(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return receipt
