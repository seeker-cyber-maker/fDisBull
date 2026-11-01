"""Build/seal the common typed core through the existing native target recipes.

The portable-C kernel seam and compiler/image checks come from the bounded
native pilots (web-udc 016ad75b). Their old database and u32-only program
contracts are not imported. Compilation, sealing and execution are separate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

from .common_uil import canonical_bytes, digest, load_json, validate_realization

FORMAT = 'fdisbull-common-uil-native-build-1'
TARGETS = {
    'macos-arm64': {'compiler': 'clang', 'triple': 'arm64-apple-macos13.0',
                    'architecture': 'arm64', 'image': 'Mach-O', 'executable': 'program',
                    'abi': 'aapcs64-apple', 'compile': ['--target=arm64-apple-macos13.0'], 'link': []},
    'linux-x64': {'compiler': 'gcc', 'triple': 'x86_64-linux-gnu',
                  'architecture': 'x86-64', 'image': 'ELF64', 'executable': 'program',
                  'abi': 'sysv-x86-64', 'compile': [], 'link': []},
    'windows-x64': {'compiler': 'x86_64-w64-mingw32-gcc', 'triple': 'x86_64-w64-mingw32',
                    'architecture': 'x86-64', 'image': 'PE32+', 'executable': 'program.exe',
                    'abi': 'ms-x64', 'compile': [],
                    'link': ['-static-libgcc', '-Wl,--no-insert-timestamp']},
}
_SOURCE = re.compile(r'[a-z][a-z0-9_-]*\.(?:c|h)\Z')
_FLAGS = ['-std=c11', '-O1', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-variable', '-Wno-unused-but-set-variable',
          '-Wno-unused-function', '-Wno-unused-label', '-Wno-unused-parameter']
_SCOPE = 'typed native computation probe and planned intrinsics; OS window/input/audio require separate host qualification'
_REUSE = {'source_commit': '016ad75b854050110b02f3c96189c6a124ce5ae5',
          'seam': 'portable C kernel, per-target compiler recipes, private outputs and native image-kind sealing'}


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('native artifacts must be owned regular files')
    return path


def _private(path, *, new=False):
    path = Path(path).expanduser().absolute()
    if new and os.path.lexists(path):
        raise ValueError('choose a new native output directory')
    if not new and (path.is_symlink() or not path.is_dir()):
        raise ValueError('native output must be an existing owned directory')
    path = path.resolve()
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise ValueError('native output must remain outside Git')
    return path


def _seal_document(document):
    document = deepcopy(document)
    document.pop('realization_sha256', None)
    document['realization_sha256'] = digest(document)
    return document


def _write_new(path, document):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + '\n')


def _commands(target, source_names, compiler):
    spec = TARGETS[target]
    objects = [str(Path(n).with_suffix('.o')) for n in source_names if n.endswith('.c')]
    common = [str(compiler), *spec['compile'], *_FLAGS]
    commands = [[*common, '-c', source, '-o', obj]
                for source, obj in zip([n for n in source_names if n.endswith('.c')], objects)]
    commands.append([str(compiler), *spec['compile'], *objects, *spec['link'], '-o', spec['executable']])
    return commands, objects


def emit_native_program(program, presentation, catalog, orchestration, output_dir,
                        target='macos-arm64', *, arithmetic='portable-c', module_requirements=None):
    """Resolve and emit a new private native realization; execute nothing."""
    if target not in TARGETS:
        raise ValueError('choose macos-arm64, linux-x64 or windows-x64')
    from .uil_link import resolve_native_link
    from .uil_native_codegen import emit_native_sources
    program, presentation, catalog, orchestration = deepcopy((program, presentation, catalog, orchestration))
    validate_realization(program, presentation, catalog, orchestration)
    lock = resolve_native_link(program, presentation, catalog, orchestration, target,
                               arithmetic=arithmetic, module_requirements=module_requirements)
    emitted = emit_native_sources(program, presentation, catalog, orchestration, target=target, link_lock=lock)
    sources = emitted['sources']
    if (type(sources) is not dict or not sources or len(sources) > 16
            or any(type(n) is not str or not _SOURCE.fullmatch(n) or type(s) is not str for n, s in sources.items())
            or not any(n.endswith('.c') for n in sources)):
        raise ValueError('invalid native source mapping')
    if sum(len(s.encode('utf-8')) for s in sources.values()) > 32 * 1024 * 1024:
        raise ValueError('native source allocation budget exceeded')
    destination = _private(output_dir, new=True)
    source_hashes = {n: hashlib.sha256(s.encode('utf-8')).hexdigest() for n, s in sorted(sources.items())}
    commands, objects = _commands(target, sorted(sources), TARGETS[target]['compiler'])
    # The running image emits this exact source closure identity, including
    # target, ABI, generator and dataflow profiles. Keep one scope throughout.
    closure = deepcopy(emitted['closure'])
    if emitted['closure_sha256'] != digest(closure):
        raise ValueError('native emitter closure identity differs')
    manifest = {'format': FORMAT, 'stage': 'source-emitted', 'target': target,
                'target_profile': deepcopy(TARGETS[target]), 'entry': program['entry'],
                'program_sha256': digest(program), 'presentation_sha256': digest(presentation),
                'catalog_sha256': digest(catalog), 'orchestration_sha256': digest(orchestration),
                'closure_sha256': digest(closure), 'link_lock_sha256': emitted['link_lock_sha256'],
                'closure': closure, 'abi': deepcopy(emitted['abi']),
                'source_profile': {k: deepcopy(v) for k, v in emitted.items() if k not in ('sources', 'abi', 'closure', 'link_lock')},
                'generator_sha256': _sha(Path(__file__).with_name('uil_native_codegen.py')),
                'builder_sha256': _sha(__file__), 'sources': source_hashes,
                'objects': objects, 'executable': TARGETS[target]['executable'],
                'compile_commands': commands, 'artifacts': deepcopy(source_hashes),
                'execution': False, 'host_effect_execution': False,
                'scope': _SCOPE, 'backend_reuse': deepcopy(_REUSE)}
    manifest = _seal_document(manifest)
    destination.mkdir(parents=True, mode=0o700)
    (destination / 'tmp').mkdir(mode=0o700)
    for name, source in sources.items():
        with (destination / name).open('x', encoding='utf-8') as stream:
            stream.write(source)
    _write_new(destination / 'source-manifest.json', manifest)
    return manifest


def _admit_source(directory):
    root = _private(directory)
    manifest = load_json(_regular(root / 'source-manifest.json'))
    if manifest.get('format') != FORMAT or manifest.get('stage') != 'source-emitted':
        raise ValueError('expected a native source manifest')
    if _seal_document(manifest) != manifest:
        raise ValueError('native source manifest integrity differs')
    if manifest['target'] not in TARGETS or manifest['target_profile'] != TARGETS[manifest['target']]:
        raise ValueError('native target profile differs')
    closure = manifest['closure']
    validate_realization(closure['program'], closure['presentation'], closure['catalog'], closure['orchestration'])
    if digest(closure) != manifest['closure_sha256']:
        raise ValueError('native closure differs')
    if closure['link_lock']['sha256'] != manifest['link_lock_sha256']:
        raise ValueError('native link-lock identity differs')
    for key in ('program', 'presentation', 'catalog', 'orchestration'):
        if digest(closure[key]) != manifest[key + '_sha256']:
            raise ValueError('native document identity differs')
    # The lock is recomputed by the resolver in code generation. A source record
    # grants no authority to supply shell commands or arbitrary providers.
    from .uil_native_codegen import emit_native_sources
    check = emit_native_sources(closure['program'], closure['presentation'], closure['catalog'],
                                closure['orchestration'], target=manifest['target'], link_lock=closure['link_lock'])
    profile = {k: deepcopy(v) for k, v in check.items() if k not in ('sources', 'abi', 'closure', 'link_lock')}
    expected_keys = {'format','stage','target','target_profile','entry','program_sha256','presentation_sha256',
                     'catalog_sha256','orchestration_sha256','closure_sha256','link_lock_sha256','closure','abi',
                     'source_profile','generator_sha256','builder_sha256','sources','objects','executable',
                     'compile_commands','artifacts','execution','host_effect_execution','scope','backend_reuse',
                     'realization_sha256'}
    if (set(manifest) != expected_keys or manifest['source_profile'] != profile
            or check['closure'] != closure or manifest['entry'] != closure['program']['entry']
            or manifest['generator_sha256'] != _sha(Path(__file__).with_name('uil_native_codegen.py'))
            or manifest['builder_sha256'] != _sha(__file__)
            or manifest['execution'] is not False or manifest['host_effect_execution'] is not False
            or manifest['scope'] != _SCOPE or manifest['backend_reuse'] != _REUSE
            or manifest['artifacts'] != manifest['sources']):
        raise ValueError('native source metadata/generator profile differs')
    expected = {n: hashlib.sha256(s.encode('utf-8')).hexdigest() for n, s in sorted(check['sources'].items())}
    if expected != manifest['sources'] or check['abi'] != manifest['abi']:
        raise ValueError('native source no longer matches admitted generation')
    for name, sha in expected.items():
        if not _SOURCE.fullmatch(name) or _sha(_regular(root / name)) != sha:
            raise ValueError('native source artifact differs')
    commands, objects = _commands(manifest['target'], sorted(expected), TARGETS[manifest['target']]['compiler'])
    if commands != manifest['compile_commands'] or objects != manifest['objects'] or manifest['executable'] != TARGETS[manifest['target']]['executable']:
        raise ValueError('native compiler recipe differs')
    return root, manifest


def _compiler(path, target, env):
    candidate = path or shutil.which(TARGETS[target]['compiler'])
    if candidate is None:
        raise ValueError('native target compiler is unavailable; emit source-only for its prepared environment')
    compiler = Path(candidate).expanduser().resolve(strict=True)
    if not compiler.is_file():
        raise ValueError('native compiler must be a regular executable')
    try:
        result = subprocess.run([str(compiler), '--version'], capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('native compiler version probe failed') from exc
    if result.returncode or not result.stdout.splitlines():
        raise ValueError('native compiler version probe failed')
    version = result.stdout.splitlines()[0]
    if target == 'macos-arm64':
        if 'clang' not in version.lower():
            raise ValueError('macOS ARM64 backend requires clang')
        triple = TARGETS[target]['triple']
    else:
        try:
            probe = subprocess.run([str(compiler), '-dumpmachine'], capture_output=True, text=True, timeout=10, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('native compiler target probe failed') from exc
        triple = probe.stdout.strip()
        if probe.returncode or not triple.startswith('x86_64') or ('linux' if target == 'linux-x64' else 'mingw') not in triple:
            raise ValueError('compiler target does not match native realization')
    return compiler, {'path': str(compiler), 'sha256': _sha(compiler), 'version': version, 'triple': triple}


def _image(path, target):
    import lief
    if target == 'macos-arm64':
        parsed = lief.MachO.parse(str(path))
        if parsed is None or len(parsed) != 1:
            raise ValueError('native output is not one Mach-O image')
        image = parsed.at(0)
        if image.header.cpu_type != lief.MachO.Header.CPU_TYPE.ARM64 or image.header.file_type != lief.MachO.Header.FILE_TYPE.EXECUTE:
            raise ValueError('native output is not an ARM64 executable')
    elif target == 'linux-x64':
        image = lief.ELF.parse(str(path))
        if (image is None or image.header.machine_type != lief.ELF.ARCH.X86_64
                or int(image.header.identity_class) != 2 or int(image.header.identity_data) != 1
                or int(image.header.file_type) not in (2, 3)
                or (int(image.header.file_type) == 3 and not image.has_interpreter)
                or not image.entrypoint):
            raise ValueError('native output is not a little-endian ELF64 x86-64 executable')
    else:
        image = lief.PE.parse(str(path))
        if (image is None or image.header.machine != lief.PE.Header.MACHINE_TYPES.AMD64
                or int(image.optional_header.magic) != 0x20b
                or int(image.optional_header.subsystem) != 3
                or int(image.header.characteristics) & 0x2000):
            raise ValueError('native output is not a Win64 console executable')
    return {'format': TARGETS[target]['image'], 'architecture': TARGETS[target]['architecture'], 'kind': 'executable'}


def _object(path, target):
    import lief
    if target == 'macos-arm64':
        parsed = lief.MachO.parse(str(path))
        if parsed is None or len(parsed) != 1:
            raise ValueError('native object is not one Mach-O image')
        image = parsed.at(0)
        if image.header.cpu_type != lief.MachO.Header.CPU_TYPE.ARM64 or image.header.file_type != lief.MachO.Header.FILE_TYPE.OBJECT:
            raise ValueError('native object architecture/kind differs')
    elif target == 'linux-x64':
        image = lief.ELF.parse(str(path))
        if (image is None or image.header.machine_type != lief.ELF.ARCH.X86_64
                or int(image.header.identity_class) != 2 or int(image.header.identity_data) != 1
                or int(image.header.file_type) != 1):
            raise ValueError('native object is not ELF64 x86-64 relocatable')
    else:
        raw = Path(path).read_bytes()
        if len(raw) < 20:
            raise ValueError('native COFF object is truncated')
        machine, count, _, _, _, optional, _ = struct.unpack_from('<HHIIIHH', raw)
        if machine != 0x8664 or not 1 <= count <= 65535 or optional != 0 or 20 + count * 40 > len(raw):
            raise ValueError('native object is not a standard AMD64 COFF object')


def seal_native_program(directory, *, compiler_evidence=None):
    """Check an externally compiled result against its retained source closure."""
    root, source = _admit_source(directory)
    if (root / 'build.json').exists():
        raise ValueError('native build is already sealed')
    names = [*source['objects'], source['executable']]
    for name in names:
        if os.path.lexists(root / name):
            _regular(root / name)
        else:
            raise ValueError('native compilation is incomplete')
    image = _image(root / source['executable'], source['target'])
    for name in source['objects']:
        _object(root / name, source['target'])
    if compiler_evidence is not None:
        canonical_bytes(compiler_evidence)
    manifest = deepcopy(source)
    manifest.update(stage='compiled', image=image, compiler=deepcopy(compiler_evidence),
                    source_manifest_sha256=_sha(root / 'source-manifest.json'))
    manifest['artifacts'].update({n: _sha(root / n) for n in names})
    manifest = _seal_document(manifest)
    _write_new(root / 'build.json', manifest)
    return manifest


def compile_native_program(directory, *, c_compiler=None):
    root, source = _admit_source(directory)
    tmp = root / 'tmp'
    if tmp.is_symlink() or not tmp.is_dir():
        raise ValueError('native compiler requires its owned temporary directory')
    if any(os.path.lexists(root / n) for n in [*source['objects'], source['executable'], 'build.json']):
        raise ValueError('native build artifacts already exist; choose a fresh realization')
    env = os.environ.copy()
    env['TMPDIR'] = str(tmp)
    compiler, info = _compiler(c_compiler, source['target'], env)
    commands, _ = _commands(source['target'], sorted(source['sources']), compiler)
    log = []
    for command in commands:
        try:
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            _write_new(root / 'compile-failure.json', {'commands': log, 'compiler': info, 'error': type(exc).__name__})
            raise ValueError('native compiler failed or timed out; no retry') from exc
        log.append({'command': command, 'returncode': result.returncode, 'stderr': result.stderr[:8000]})
        if result.returncode:
            _write_new(root / 'compile-failure.json', {'commands': log, 'compiler': info})
            raise ValueError('native compilation failed: ' + result.stderr[:1600])
    info['commands'] = log
    return seal_native_program(root, compiler_evidence=info)


def build_native_program(program, presentation, catalog, orchestration, output_dir,
                         target='macos-arm64', *, arithmetic='portable-c', module_requirements=None,
                         c_compiler=None, source_only=False):
    if type(source_only) is not bool:
        raise ValueError('source_only must be boolean')
    emitted = emit_native_program(program, presentation, catalog, orchestration, output_dir, target,
                                  arithmetic=arithmetic, module_requirements=module_requirements)
    return emitted if source_only else compile_native_program(output_dir, c_compiler=c_compiler)
