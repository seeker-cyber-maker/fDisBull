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
        _entry('decode.x86', 'implemented', ['x86-16', 'x86-32', 'x86-64'],
               ['python:decoder.decode', 'cli:disasm'], ['decoder.py'], ['iced-x86', 'capstone'],
               'Native instruction facts; indirect and segmented targets may remain unresolved.'),
        _entry('decode.arm64', 'implemented', ['arm64-le'],
               ['python:decoder.decode', 'cli:disasm'], ['decoder.py'], ['capstone', 'iced-x86'],
               'Four-byte native instruction facts; no inferred resolution of PAC or dynamic dispatch.'),
        _entry('compare.x86', 'implemented', ['x86-16', 'x86-32', 'x86-64'],
               ['cli:decoder-check'], ['decoder_check.py', 'decoder.py'], ['iced-x86', 'capstone'],
               'Iced/Capstone instruction comparison for x86; no two-engine ARM64 comparison.'),
        _entry('analysis.recursive', 'partial', ['x86-16', 'x86-32', 'x86-64', 'arm64-le'],
               ['cli:import', 'cli:analyze', 'cli:analysis-status'], ['project.py', 'loader.py', 'decoder.py'],
               ['lief', 'iced-x86', 'capstone', 'Pillow'],
               'Persistent bounded traversal; candidate functions and pending work are not whole-program coverage.'),
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
        _entry('debug.dos', 'partial', ['x86-16'], ['cli:debug', 'cli:doctor'],
               ['debugger.py', 'dosbox_rpc.py'], ['lief', 'iced-x86', 'capstone', 'Pillow', 'dos-backend'],
               'Configured compatible DOSBox backend; backend identity and doctor acceptance are separate gates.'),
        _entry('debug.pe64', 'partial', ['x86-64'], ['cli:debug', 'cli:doctor'],
               ['wine_debugger.py', 'wine_rpc.py'], ['lief', 'iced-x86', 'capstone', 'Pillow', 'pe64-backend'],
               'Configured Wine/QEMU guest or IDA backend; kernel, guest and backend identities required.'),
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
        _entry('uil.native-app-export', 'unsupported', ['arm64-le'], [], [], [],
               'General macOS app or SwiftUI-to-UIL semantic recovery is not implemented.', maturity='proposed'),
        _entry('uil.macos-host-effects', 'unsupported', ['architecture-neutral'], [], [], [],
               'No UIL executor for UserDefaults, IOPM, notifications, network or asynchronous sensors.', maturity='proposed'),
        _entry('compile.macos-arm64', 'unsupported', ['arm64-le'], [], [], [],
               'No general macOS ARM64 compiler for a UIL app model.', maturity='proposed'),
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
        'dos-backend': {'kind': 'configuration', 'status': 'not_selected'},
        'pe64-backend': {'kind': 'configuration', 'status': 'not_selected'},
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
                    'identity_scope': 'Listed provider file hashes only; no embedded build commit or release certification.'},
        'discovery': {'external_tools_executed': False, 'targets_executed': False,
                      'native_modules_imported': False, 'runtime_validation': 'not_run'},
        'host': host, 'dependencies': dependencies, 'capabilities': entries, 'sources': sources,
        'limitations': [
            'This is a scoped catalog of the imported copy, not every installed version or every fDisBull method.',
            'Requirements cover all listed interfaces, including CLI front-end imports; a direct Python call may need fewer.',
            'Module/executable presence does not prove importability, compatible versions, permission or successful execution.',
            'PATH discovery may select shims; Java/Ghidra/LLDB versions and configuration are not validated.',
            'A version string or experimental label does not certify release inclusion; compare source hashes and review receipts.',
        ],
    }
