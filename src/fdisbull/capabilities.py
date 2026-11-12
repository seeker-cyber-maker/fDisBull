"""Read-only discovery of this imported copy; no native imports or tool launches."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil

from . import __version__

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PYTHON = {'iced-x86': ('iced_x86', 'iced-x86'), 'capstone': ('capstone', 'capstone'),
           'lief': ('lief', 'lief'), 'Pillow': ('PIL', 'Pillow'),
           'z3': ('z3', 'z3-solver')}
_COMMON_NATIVE_PROVIDERS = ('common_uil.py', 'uil_catalog.py', 'uil_api.py',
    'uil_native.py', 'uil_native_codegen.py', 'uil_link.py', 'uil_dataflow.py', 'uil_runtime.py')
_COMMON_DESKTOP_PROVIDERS = (*_COMMON_NATIVE_PROVIDERS, 'uil_desktop.py',
    'native_runtime/memory-desktop.c', 'native_runtime/memory-desktop.h',
    'native_runtime/memory-appkit.m', 'native_runtime/memory-x11.c',
    'native_runtime/memory-win32.c')


def _python_dependency(name, distribution):
    # All names are top-level and allowlisted: find_spec need not import parents.
    try:
        present = importlib.util.find_spec(name) is not None
    except (ImportError, OSError, ValueError):
        present = False
    try:
        version = importlib.metadata.version(distribution)
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        version = None
    return {'kind': 'python', 'status': 'detected' if present else 'not_found',
            'version': version, 'validation': 'not_imported'}


def _tool(name, explicit):
    if explicit is not None and (not isinstance(explicit, str) or not explicit.strip()
                                 or len(explicit) > 4096 or '\x00' in explicit):
        raise ValueError('tool paths must be nonempty strings of at most 4096 characters')
    selected = explicit if explicit is not None else shutil.which(name)
    try:
        path = Path(selected).expanduser() if selected else None
    except (RuntimeError, OSError) as exc:
        raise ValueError('cannot expand the selected tool path') from exc
    try:
        detected = path is not None and path.is_file() and os.access(path, os.X_OK)
    except OSError:
        detected = False
    return {'kind': 'executable', 'status': 'detected' if detected else 'not_found',
            'selection': 'explicit' if explicit is not None else 'PATH',
            'path': str(path) if path is not None else None, 'version': None,
            'validation': 'not_executed'}


def _entry(identifier, implementation, architectures, methods, providers, requires, scope,
           *, maturity='bounded', **extra):
    return {'id': identifier, 'implementation': implementation, 'maturity': maturity,
            'architectures': architectures, 'interfaces': methods, 'providers': providers,
            'requires': requires, 'scope': scope, **extra}


def _catalog():
    return [
        _entry('inspect.file-formats', 'partial', ['container-dependent'],
               ['cli:format-modules', 'cli:file-identify', 'cli:intake-inventory'], ['format_registry.py', 'format_media.py', 'intake.py', 'inspection.py', 'image_views.py'], [],
               'Versioned SQLite header facts and bounded signature/architecture/media probes. Recognition, structural validation, decoder availability and native execution are separate.'),
        _entry('media.smk2-framing', 'partial', ['architecture-neutral'],
               ['cli:media-inspect', 'cli:smk-frame'], ['smacker.py', 'media.py'], ['ffmpeg', 'ffprobe'],
               'Bounded native SMK2 FULL/SKIP framing with exact selected images/palettes and complete original audio. Independent decoding does not qualify an original game or arbitrary seeking.'),
        _entry('decode.x86', 'implemented', ['x86-16', 'x86-32', 'x86-64'],
               ['python:decoder.decode', 'cli:disasm'], ['decoder.py'], ['iced-x86', 'capstone'],
               'Native instruction facts; indirect and segmented targets may remain unresolved.'),
        _entry('decode.arm64', 'implemented', ['arm64-le'],
               ['python:decoder.decode', 'cli:disasm'], ['decoder.py'], ['capstone', 'iced-x86'],
               'Four-byte native instruction facts; no inferred resolution of PAC or dynamic dispatch.'),
        _entry('decode.chip8', 'implemented', ['chip8-classic-16be'],
               ['cli:import --arch chip8', 'python:decoder.decode', 'cli:analyze'],
               ['chip8.py', 'loader.py', 'decoder.py'], ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Pilot-default classic words in 4 KiB RAM; SYS/SCHIP/XO refused. No independent historical qualification.', maturity='experimental'),
        _entry('compare.x86', 'implemented', ['x86-16', 'x86-32', 'x86-64'],
               ['cli:decoder-check'], ['decoder_check.py', 'decoder.py'], ['iced-x86', 'capstone'],
               'Iced/Capstone instruction comparison for x86; no two-engine ARM64 comparison.'),
        _entry('analysis.recursive', 'partial', ['x86-16', 'x86-32', 'x86-64', 'arm64-le', 'chip8-classic-16be'],
               ['cli:import', 'cli:analyze', 'cli:analysis-status'], ['project.py', 'loader.py', 'decoder.py'],
               ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Persistent bounded traversal; candidate functions and pending work are not whole-program coverage.'),
        _entry('analysis.dos-driver', 'partial', ['x86-16'],
               ['cli:import --image sys', 'cli:analyze', 'cli:inspect'],
               ['dos_driver.py', 'dos.py', 'loader.py', 'dos_analysis.py'],
               ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Flat/MZ device headers and Strategy/Interrupt roots; request state unknown. Static-only partial analysis.'),
        _entry('analysis.le-driver', 'partial', ['x86-16', 'x86-32'],
               ['cli:le-driver-inspect', 'cli:le-driver-disasm'],
               ['le_driver.py', 'qemm_tools.py'], ['iced-x86', 'capstone'],
               'Mixed-width object views/symbolic fixups. VxD INT20 needs explicit ABI. No whole-module CFG or execution.'),
        _entry('backing.macho-arm64', 'partial', ['arm64-le'], ['cli:code-backings'],
               ['code_backings.py', 'macho_slices.py'], ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Source-bound selected instructions, slice/file offsets and byte version; no Swift semantic lift.',
               maturity='experimental'),
        _entry('compare.macho-arm64', 'partial', ['arm64-le'], ['cli:ghidra-arm64'],
               ['ghidra_arm64.py', 'data/FdisbullGhidraArm64.txt'],
               ['lief', 'iced-x86', 'capstone', 'Pillow', 'ghidra-headless', 'java'],
               'Source-bound Ghidra facts for up to 256 selected four-byte instruction addresses per call.',
               maturity='experimental'),
        _entry('decompile.macho-arm64', 'partial', ['arm64-le'], ['cli:ghidra-arm64'],
               ['ghidra_arm64.py', 'data/FdisbullGhidraArm64.txt'],
               ['lief', 'iced-x86', 'capstone', 'Pillow', 'ghidra-headless', 'java'],
               'Ghidra C diagnostic for a selected function accepted inside a 4 KiB entry window; not full app recovery.',
               maturity='experimental', independent_decompiler=True),
        _entry('debug.macos-arm64', 'partial', ['arm64-le'], ['cli:macos-observe'],
               ['macos_lldb.py', '_macos_lldb_driver.py'], ['lief', 'iced-x86', 'capstone', 'Pillow', 'lldb'],
               'One explicit source-bound launch to one symbol; no attach, persistent session or UI recorder.',
               maturity='experimental', required_host={'system': 'Darwin', 'machine': 'arm64'}),
        _entry('macos.reversible-capture', 'partial', ['arm64', 'x86-64'],
               ['cli:macos-snapshot', 'cli:macos-session', 'cli:macos-session-recover'],
               ['macos_capture.py', 'macos_session.py', 'data/FdisbullMacCapture.swift'], ['swiftc'],
               'macOS 14+ display-bound native PNG/AX capture; explicit live action, owned-change restoration and recovery journal. Native permissions not checked here.',
               maturity='experimental', required_host={'system': 'Darwin'}),
        _entry('debug.dos', 'partial', ['x86-16'], ['cli:debug', 'cli:doctor', 'cli:dos-migration'],
               ['debugger.py', 'dosbox_rpc.py'], ['lief', 'iced-x86', 'capstone', 'Pillow', 'dos-backend'],
               'DOSBox remains default. Native qemu-dos has experimental COM/MZ and TSR observations via debug-dos-process; dos-migration tracks remaining parity.'),
        _entry('debug.chip8', 'partial', ['chip8-classic-16be'],
               ['cli:debug --backend qemu-chip8', 'json:debug-launch'],
               ['qemu_chip8.py', 'gdb_rpc.py', 'qemu_control.py'], ['chip8-backend'],
               'CPU-only TCG run/step, registers/RAM, breakpoints and exact-runtime snapshots. No devices/layers/hooks/histories/trials.', maturity='experimental'),
        _entry('debug.qemm-guest', 'partial', ['x86-16', 'x86-32'],
               ['cli:qemm-config', 'cli:qemm-profile', 'cli:debug --backend qemu-machine --guest-profile qemm',
                'json:debug-memory-translation', 'json:debug-qemm-observe'],
               ['qemm_runtime.py', 'qemu_machine.py', 'dos_memory.py', 'qpi.py'],
               ['lief', 'iced-x86', 'capstone', 'Pillow', 'qemu-system', 'qemm-boot-image'],
               'Pinned FAT12/16 image, 486/32 MiB guest, observed v86/386 maps. QEMM/title compatibility needs qualification.',
               maturity='experimental'),
        _entry('inspect.qpi-report', 'partial', ['x86-16'],
               ['cli:qpi-probe', 'cli:qpi-report'],
               ['qpi.py', 'qemm_tools.py', 'data/FdisbullQpiProbe.txt', 'data/qpi-probe.json'], [],
               'QPI helper/1088 KiB map report. Parsing proves no producer, freshness or native execution.'),
        _entry('debug.desqview', 'partial', ['x86-16', 'x86-32'],
               ['cli:desqview-profile', 'cli:desqview-module-inspect', 'json:debug-desqview-observe'],
               ['desqview.py', 'desqview_runtime.py', 'data/FdisbullDesqviewProbe.txt', 'data/desqview-probe.json'], [],
               'DVR/API facts, profiles and cooperative helper. Stopped backend required; kernel compatibility unqualified.',
               maturity='experimental'),
        _entry('debug.memory-search', 'partial', ['x86-16', 'x86-32'],
               ['json:debug-memory-snapshot', 'cli:memory-search-start', 'json:debug-memory-rule-run'],
               ['memory_search.py', 'memory_search_runtime.py', 'memory_rules.py'], [],
               'Persistent searches/guarded edits on paused DOSBox/machine. Task lifetime/maps required; allocation reuse unknown.'),
        _entry('debug.execution-search', 'partial', ['x86-16','x86-32','x86-64'],
               ['json:debug-trace-until','cli:event-search-start','cli:event-trace-query'],
               ['execution_events.py','event_search.py','execution_trace.py'], ['lief','iced-x86','capstone','Pillow'],
               'Live DOS16 predicates; offline qualified site/register candidates. No function/OEP proof.'),
        _entry('debug.pe64', 'partial', ['x86-64'], ['cli:debug', 'cli:doctor'],
               ['wine_debugger.py', 'wine_rpc.py'], ['lief', 'iced-x86', 'capstone', 'Pillow', 'pe64-backend'],
               'Configured Wine/QEMU guest or IDA backend; kernel, guest and backend identities required.'),
        _entry('debug.pe32', 'partial', ['x86-32'], ['cli:debug','json:debug-step'],
               ['wine_debugger.py','wine_arch.py','wine_rpc.py','wine_guest/agent.c','windows_ui.py'],
               ['lief','iced-x86','capstone','Pillow','pe32-backend'],
               'PE32 Wine/QEMU: WOW64 contexts, source maps, bounded control/watches and Windows UI. Requires qualified 32-bit runtime.',
               maturity='experimental'),
        _entry('debug.win16', 'partial', ['x86-16'], ['cli:debug --backend wine-ne'],
               ['win16_debugger.py','ne.py','wine_rpc.py','wine_guest/agent.c','windows_ui.py'],
               ['lief','iced-x86','capstone','Pillow','win16-backend'],
               'NE carrier with observed source/selector bindings; stale bindings refuse. Six non-stack register edits require paired native/WOW runtime and 16-bit LDT stop. No checkpoints/layers/deltas or general Win3.x qualification.',
               maturity='experimental'),
        _entry('debug.windows-scenes', 'partial', ['x86-16','x86-32','x86-64'],
               ['json:debug-scene-act','json:debug-scene-wait','json:debug-keyboard-press','json:debug-frame-probe','cli:debug --dot-mode'],
               ['windows_ui.py','scenes.py','scene_values.py','wine_guest/agent.c'],
               ['lief','iced-x86','capstone','Pillow','windows-backend'],
               'Guest input, source-bound frames and host-time scene waits. Dot-mode reads retained frames without input forwarding. Device/title qualification is separate.',
               maturity='experimental'),
        _entry('debug.scummvm-agi', 'partial', ['agi-vm'],
               ['cli:debug --backend scummvm-agi', 'json:debug-engine-state', 'json:debug-step'],
               ['scummvm_debugger.py', 'scummvm_rpc.py', 'debugger.py', 'scenes.py', 'scene_values.py'],
               ['lief', 'iced-x86', 'capstone', 'Pillow', 'scummvm-backend'],
               'Patched ScummVM AGI replacement engine: bounded script control, typed VM state, input, stored frames and cycle-level native saves; no original DOS execution or exact machine checkpoint.',
               maturity='experimental'),
        _entry('debug.scummvm-kyra', 'partial', ['kyra-emc2'],
               ['cli:debug --backend scummvm-kyra','json:debug-engine-state','json:debug-step'],
               ['scummvm_kyra.py','scummvm_rpc.py','debugger.py'],
               ['Pillow','scummvm-kyra-sidecar'],
               'Controller/contract scaffold only, synthetic RPC fixtures passed. No native Kyra sidecar built or qualified; stock ScummVM refused.',
               maturity='experimental'),
        _entry('debug.scummvm-gob', 'partial', ['gob-vm'],
               ['cli:debug --backend scummvm-gob','json:debug-engine-state','json:debug-read-variable','json:debug-step'],
               ['scummvm_gob.py','scummvm_rpc.py','debugger.py','scenes.py','scene_values.py'],
               ['lief','iced-x86','capstone','Pillow','scummvm-backend'],
               'Patched ScummVM Gob Inter_v3 for Lost in Time (lit/lit1/lit2): source-bound TOT control, typed variable arena, scoped watches, input and stored frames. Native game saves and loaded-script patching are unsupported.',
               maturity='experimental'),
        _entry('lift.asm-u16', 'partial', ['x86-16'], ['cli:udl-lift-asm'],
               ['udl_blocks.py'], ['capstone'],
               'Restricted straight-line uint16 register blocks; no general memory, control-flow or ABI recovery.'),
        _entry('lift.c-u16', 'partial', ['source-c-u16'], ['cli:udl-lift-c'],
               ['udl_blocks.py'], ['capstone'],
               'Restricted uint16 C input reader; it consumes C source and is not a binary decompiler.'),
        _entry('view.c-x86-16', 'partial', ['x86-16'], ['python:udl_blocks.asm_to_c'],
               ['udl_blocks.py'], ['capstone'],
               'Restricted C statement view from the same ASM lift; no independent decompilation.',
               independent_decompiler=False),
        _entry('uil.primitive', 'partial', ['architecture-neutral'], ['cli:il-check', 'cli:il-run'],
               ['interaction_il.py'], [],
               'fdisbull-il-1 scalar/block evaluation; graphics/audio/input remain pending host events, not performed effects.'),
        _entry('verify.block-z3', 'partial', ['x86-16', 'source-c-u16'], ['cli:udl-verify'],
               ['udl_blocks.py', 'proofs.py'], ['capstone', 'z3'],
               'Bounded source-block/model comparison under explicit assumptions; no native app equivalence.'),
        _entry('compile.dos', 'partial', ['x86-16'], ['cli:udc-capture', 'cli:udc-compile'],
               ['udc.py'], ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Original-backed bounded DOS definitions with preserved unsupported residuals; not arbitrary UIL compilation.'),
        _entry('compile.common-native', 'partial', ['arm64-le', 'x86-64'],
               ['cli:uil-compile', 'cli:uil-link', 'cli:uil-components', 'cli:uil-build', 'cli:uil-seal'],
               list(_COMMON_NATIVE_PROVIDERS), ['lief', 'iced-x86', 'capstone', 'Pillow', 'native-c-compiler'],
               'Bounded numeric/bool/resource/fixed-array common UIL with C/assembly leaves and owned ABI. Effects stay planned; target compiler required. No general app recovery.',
               targets=['macos-arm64', 'linux-x64', 'windows-x64']),
        _entry('uil.common-desktop', 'partial', ['arm64-le', 'x86-64'],
               ['cli:uil-desktop', 'cli:uil-desktop-build', 'cli:uil-desktop-seal'],
               list(_COMMON_DESKTOP_PROVIDERS),
               ['lief', 'iced-x86', 'capstone', 'Pillow', 'native-c-compiler', 'native-window-services'],
               'Fixed-u32-arena AppKit/X11/Win64 shell with declared frame/input adapters and C/assembly/mixed choices. Build, original-code and native device/callback gates are separate.',
               targets=['macos-arm64', 'linux-x64', 'windows-x64']),
        _entry('uil.native-app-export', 'unsupported', ['arm64-le'], [], [], [],
               'General macOS app or SwiftUI-to-UIL semantic recovery is not implemented.', maturity='proposed'),
        _entry('uil.macos-host-effects', 'unsupported', ['architecture-neutral'], [], [], [],
               'No UIL executor for UserDefaults, IOPM, notifications, network or asynchronous sensors.', maturity='proposed'),
        _entry('compile.macos-arm64', 'unsupported', ['arm64-le'], [], [], [],
               'General recovered macOS/SwiftUI app compilation remains unsupported; compile.common-native and uil.common-desktop are separate bounded profiles.',
               maturity='proposed', bounded_alternatives=['compile.common-native', 'uil.common-desktop']),
    ]


def _sources(entries):
    # Fixed inventory only; never recurse, inspect a target or read Git history.
    paths = {'__init__.py', 'cli.py', 'capabilities.py'}
    paths.update(name for item in entries for name in item['providers'])
    result = {}
    for name in sorted(paths):
        try:
            with (_PACKAGE_ROOT / name).open('rb') as stream:
                data = stream.read(2 * 1024 * 1024 + 1)
            result[name] = ({'status': 'too_large'} if len(data) > 2 * 1024 * 1024 else
                            {'status': 'read', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        except OSError:
            result[name] = {'status': 'unreadable'}
    return result


def capabilities(*, analyze_headless=None, lldb=None, java=None):
    """Catalog this imported copy. Detection never establishes backend usability."""
    entries = _catalog()
    dependencies = {key: _python_dependency(*names) for key, names in _PYTHON.items()}
    dependencies.update({
        'ghidra-headless': _tool('analyzeHeadless', analyze_headless),
        'lldb': _tool('lldb', lldb), 'java': _tool('java', java),
        'swiftc': _tool('swiftc', None),
        'ffmpeg': _tool('ffmpeg', None), 'ffprobe': _tool('ffprobe', None),
        'qemu-system': _tool('qemu-system-x86_64', None),
        'qemm-boot-image': {'kind': 'configuration', 'status': 'not_selected'},
        'dos-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'chip8-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'pe64-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'pe32-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'win16-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'windows-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'scummvm-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'scummvm-kyra-sidecar': {'kind': 'configuration', 'status': 'not_selected'},
        'native-c-compiler': {'kind': 'configuration', 'status': 'not_selected'},
        'native-window-services': {'kind': 'configuration', 'status': 'not_selected'},
    })
    host = {'system': platform.system(), 'machine': platform.machine()}
    sources = _sources(entries)
    for item in entries:
        if item['implementation'] == 'unsupported':
            available = 'unsupported'
        elif any(host.get(key) != value for key, value in item.get('required_host', {}).items()):
            available = 'host_unsupported'
        elif any(sources[name]['status'] != 'read' for name in item['providers']):
            available = 'component_missing'
        elif any(dependencies[name]['status'] == 'not_found' for name in item['requires']):
            available = 'missing_dependencies'
        elif any(dependencies[name]['status'] == 'not_selected' for name in item['requires']):
            available = 'not_checked'
        else:
            available = 'dependencies_detected'
        item.update(availability=available, runtime_validation='not_run')
    try:
        distribution_version = importlib.metadata.version('fdisbull')
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        distribution_version = None
    return {
        'format': 'fdisbull-capabilities-1',
        'package': {'runtime_version': __version__, 'distribution_version': distribution_version,
                    'imported_from': str(_PACKAGE_ROOT), 'source_revision': None,
                    'release_status': 'not_determined',
                    'provider_fingerprint': hashlib.sha256(json.dumps(sources, sort_keys=True,
                                                          separators=(',', ':')).encode()).hexdigest(),
                    'identity_scope': 'Provider hashes only; no build/release certification.'},
        'discovery': {'external_tools_executed': False, 'targets_executed': False,
                      'native_modules_imported': False, 'runtime_validation': 'not_run'},
        'host': host, 'dependencies': dependencies, 'capabilities': entries, 'sources': sources,
        'limitations': [
            'Scoped imported-copy catalog; not every method or installation.',
            'Requirements include CLI imports; Python calls may need fewer.',
            'Presence proves no compatibility, permission or execution.',
            'PATH may select shims; tool versions/configuration are unchecked.',
            'Native/desktop profiles need selected, separately qualified compiler/window services.',
            'Release inclusion needs source hashes and review receipts, not version labels.',
        ],
    }
