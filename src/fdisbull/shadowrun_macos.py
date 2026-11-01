"""Private AppKit frontend for the source-bound assisted Shadowrun arena."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

from .console_udc import _private_directory
from .game_il import canonical
from .shadowrun_assisted_arena import assisted_arena_from_capture, lift_assisted_arena
from .shadowrun_replay import _bundle, _read_rom, _source_capture, SNAPSHOT_FILES
from .udl_shadowrun import lift_opening_stoker

APP_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_macos_app.m'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def build_macos_assisted_arena(path, *, rom_path, capture, output, preset='stationary'):
    """Build a private arm64 AppKit app from the reviewed source and capture.

    ``path`` is the receipt-bound opening bundle manifest. The app stores only
    an absolute reference to the caller's ROM; it does not copy the ROM into
    the bundle. Original assets and all generated output stay outside Git.
    """
    if preset not in ('stationary', 'moving'):
        raise ValueError('Arena preset must be stationary or moving')
    destination = _private_directory(output)
    selected_manifest = Path(path).expanduser()
    _, _, payloads = _bundle(selected_manifest)
    manifest_path = selected_manifest.resolve()
    manifest_bytes = manifest_path.read_bytes()
    rom_file = Path(rom_path).expanduser().resolve()
    rom = _read_rom(rom_file)
    if canonical(lift_opening_stoker(rom)) != canonical(json.loads(payloads['program.uil.json'])):
        raise ValueError('Bundle differs from current source lift')
    capture_path = Path(capture).expanduser().resolve() / 'native/scene-005999'
    identity, arrays, _ = _source_capture(capture_path, _sha(rom))
    if identity['capture_json_sha256'] != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':
        raise ValueError('Expected the reviewed scene-2 capture')
    if any(arrays[field] != payloads[name] for name, (field, _) in SNAPSHOT_FILES.items()):
        raise ValueError('Capture differs from the reviewed bundle')
    source = APP_SOURCE.read_bytes()
    program = lift_assisted_arena(rom)
    machine = assisted_arena_from_capture(rom, capture_path, moving=preset == 'moving')
    if canonical(machine.program) != canonical(program):
        raise ValueError('Arena source changed while preparing the build')
    from .udc_macos import build_macos

    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    core_dir = destination / 'native-core'
    native = build_macos(program, machine.snapshot(), core_dir)
    app = destination / 'Shadowrun Arena.app'
    macos = app / 'Contents/MacOS'
    macos.mkdir(parents=True, mode=0o700)
    library = macos / 'libfdisbull_native.dylib'
    shutil.copyfile(core_dir / 'libfdisbull_native.dylib', library)
    if _sha(library.read_bytes()) != native['dylib_sha256']:
        raise ValueError('Native library changed while assembling app')
    plist = {'CFBundleIdentifier':'org.fdisbull.shadowrun.assisted',
             'CFBundleName':'Shadowrun Assisted Arena', 'CFBundleExecutable':'ShadowrunArena',
             'CFBundlePackageType':'APPL', 'CFBundleVersion':'1',
             'NSHighResolutionCapable':True, 'FDisBullSourceROM':str(rom_file)}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
    executable = macos / 'ShadowrunArena'
    env = {k:v for k,v in os.environ.items() if not k.startswith(('DYLD_', 'CC65_', 'LD_'))}
    env['LC_ALL'] = 'C'
    command = ['/usr/bin/clang','-arch','arm64','-fobjc-arc','-O2','-framework','Cocoa',
               '-I',str(core_dir),str(APP_SOURCE),'-L',str(core_dir),'-lfdisbull_native',
               '-Wl,-rpath,@loader_path','-o',str(executable)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    (destination / 'frontend-build.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('AppKit frontend compilation failed: ' + result.stderr[-4000:])
    if (APP_SOURCE.read_bytes()!=source or manifest_path.read_bytes()!=manifest_bytes or
        _read_rom(rom_file)!=rom or canonical(lift_assisted_arena(rom))!=canonical(program)):
        raise ValueError('App inputs changed during build')
    receipt = {'format':'fdisbull-shadowrun-macos-arena-1', 'preset':preset,
               'architecture':'arm64', 'source_sha256':_sha(rom),
               'program_sha256':_sha(canonical(program)), 'capture_receipt_sha256':identity['capture_json_sha256'],
               'bundle_manifest_sha256':_sha(manifest_bytes), 'frontend_source_sha256':_sha(source),
               'frontend_sha256':_sha(executable.read_bytes()), 'native_core':native,
               'app':'Shadowrun Arena.app', 'executable':'Shadowrun Arena.app/Contents/MacOS/ShadowrunArena',
               'display':'authored symbolic terrain and actor projection',
               'limits':['assisted encounter','bounded source branches','unsupported states stop',
                         'no original artwork or death-scene claim','host timer requests 60 Hz; performance requires measurement']}
    (destination / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
