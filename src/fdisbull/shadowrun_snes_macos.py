"""Private native projection of the recovered SNES opening-scene movement."""
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
from .shadowrun_snes_field import CAPTURE, machine_from_capture
from .udc_macos import build_macos

APP_SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_macos_app.m'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _input(path, size):
    selected=Path(path).expanduser()
    if selected.is_symlink() or not selected.is_file() or selected.stat().st_size!=size:
        raise ValueError('Source input must be a regular file of the expected size')
    return selected.resolve(),selected.read_bytes()


def build(*, rom_path, ram, save_ram, output):
    """Compile the exact captured SNES scene to a private native ARM64 app.

    The caller owns the ROM, frame-2999 WRAM and qualified save-RAM capture.
    Their hashes are checked by the source adapter. The app embeds private
    collision data and seed values, and references the caller's original ROM.
    None of these generated files are tool publication artifacts.
    """
    destination=_private_directory(output)
    if destination.exists():
        raise ValueError('Native SNES output must be a new private directory')
    rom_file,rom=_input(rom_path,1048576)
    _,snapshot=_input(ram,131072)
    _,save=_input(save_ram,8192)
    source=APP_SOURCE.read_bytes()
    machine=machine_from_capture(rom,snapshot,save)
    program=machine.program
    destination.mkdir(mode=0o700)
    native=build_macos(program,machine.snapshot(),destination/'native-core',
                       entry='shadowrun_snes_frame',immutable_regions={1:snapshot})
    (destination/'program.uil.json').write_bytes(canonical(program))
    (destination/'seed.json').write_text(json.dumps(machine.snapshot(),sort_keys=True)+'\n')
    app=destination/'Shadowrun SNES Study.app'
    binary=app/'Contents/MacOS'
    binary.mkdir(parents=True,mode=0o700)
    shutil.copyfile(destination/'native-core/libfdisbull_native.dylib',binary/'libfdisbull_native.dylib')
    if _sha((binary/'libfdisbull_native.dylib').read_bytes())!=native['dylib_sha256']:
        raise ValueError('Native core changed while assembling the app')
    info={'CFBundleIdentifier':'org.fdisbull.shadowrun.snes.study',
          'CFBundleName':'Shadowrun SNES Study','CFBundleExecutable':'ShadowrunSNESStudy',
          'CFBundlePackageType':'APPL','CFBundleVersion':'1','NSHighResolutionCapable':True,
          'FDisBullSourceROM':str(rom_file)}
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    executable=binary/'ShadowrunSNESStudy'
    command=['/usr/bin/clang','-arch','arm64','-fobjc-arc','-O2','-framework','Cocoa',
             '-I',str(destination/'native-core'),str(APP_SOURCE),
             '-L',str(destination/'native-core'),'-lfdisbull_native',
             '-Wl,-rpath,@loader_path','-o',str(executable)]
    environment={k:v for k,v in os.environ.items() if not k.startswith(('DYLD_','CC65_','LD_'))}
    result=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=120)
    (destination/'frontend-build.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise ValueError('SNES frontend build failed: '+result.stderr[-4000:])
    if APP_SOURCE.read_bytes()!=source or rom_file.read_bytes()!=rom:
        raise ValueError('App input changed during compilation')
    current=machine_from_capture(rom,snapshot,save)
    if canonical(current.program)!=canonical(program) or current.snapshot()!=machine.snapshot():
        raise ValueError('SNES source adapter changed during compilation')
    receipt={'format':'fdisbull-shadowrun-snes-macos-1','architecture':'arm64',
             'capture':CAPTURE,'program_sha256':_sha(canonical(program)),
             'seed_sha256':_sha((destination/'seed.json').read_bytes()),'native_core':native,
             'frontend_source_sha256':_sha(source),'frontend_sha256':_sha(executable.read_bytes()),
             'app':app.name,'executable':str(executable.relative_to(destination)),
             'display':'authored world-coordinate grid and player marker; no original camera or artwork',
             'limits':['prepared source scene; bounded movement and source collision branches',
                       'captured static collision data; autonomous actors and scene changes unqualified',
                       'unsupported states stop with the complete native state unchanged',
                       'private build embeds captured game data; do not publish',
                       'host requests 60 Hz; no full-game or presentation equivalence claim']}
    (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
