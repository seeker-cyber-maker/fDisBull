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


def build(*, rom_path, ram, save_ram, output, profile='static-morgue'):
    """Compile the exact captured SNES scene to a private native ARM64 app.

    The caller owns the ROM, frame-2999 WRAM and qualified save-RAM capture.
    Their hashes are checked by the source adapter. The app embeds private
    collision data and seed values, and references the caller's original ROM.
    None of these generated files are tool publication artifacts.
    """
    if profile not in ('static-morgue','live-morgue','npc-intro'):
        raise ValueError('Unknown SNES study profile')
    destination=_private_directory(output)
    if destination.exists():
        raise ValueError('Native SNES output must be a new private directory')
    rom_file,rom=_input(rom_path,1048576)
    _,snapshot=_input(ram,131072)
    _,save=_input(save_ram,8192)
    source=APP_SOURCE.read_bytes()
    if profile=='live-morgue':
        from .shadowrun_snes_live import machine_from_live_capture
        factory=machine_from_live_capture
    elif profile=='npc-intro':
        from .shadowrun_snes_npc import demo_from_capture
        factory=demo_from_capture
    else:factory=None
    if factory:machine,regions=factory(rom,snapshot,save)
    else:machine=machine_from_capture(rom,snapshot,save);regions={0:rom,1:snapshot}
    program=machine.program
    destination.mkdir(mode=0o700)
    native=build_macos(program,machine.snapshot(),destination/'native-core',
                       entry='shadowrun_snes_frame',immutable_regions={k:v for k,v in regions.items() if k!=0})
    (destination/'program.uil.json').write_bytes(canonical(program))
    (destination/'seed.json').write_text(json.dumps(machine.snapshot(),sort_keys=True)+'\n')
    app=destination/'Shadowrun SNES Study.app'
    binary=app/'Contents/MacOS'
    binary.mkdir(parents=True,mode=0o700)
    shutil.copyfile(destination/'native-core/libfdisbull_native.dylib',binary/'libfdisbull_native.dylib')
    if _sha((binary/'libfdisbull_native.dylib').read_bytes())!=native['dylib_sha256']:
        raise ValueError('Native core changed while assembling the app')
    info={'CFBundleIdentifier':'org.fdisbull.shadowrun.snes.study.'+profile,
          'CFBundleName':{'static-morgue':'Shadowrun SNES Study','live-morgue':'Shadowrun SNES Live Collision','npc-intro':'Shadowrun SNES NPC Walking'}[profile],'CFBundleExecutable':'ShadowrunSNESStudy',
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
    current=factory(rom,snapshot,save)[0] if factory else machine_from_capture(rom,snapshot,save)
    if canonical(current.program)!=canonical(program) or current.snapshot()!=machine.snapshot():
        raise ValueError('SNES source adapter changed during compilation')
    capture=dict(CAPTURE)
    if profile=='live-morgue':capture['scope']='prepared scene; reconstructed mutable collision lists and projected actor flags, fixed captured 7F tables, bounded analysis updates'
    if profile=='npc-intro':capture={'frame':2000,'rom_sha256':_sha(rom),'wram_sha256':_sha(snapshot),'actor_slots':[0x44,0x46],'scope':'two coordinate-target, noncolliding NPC kinematic projections'}
    receipt={'format':'fdisbull-shadowrun-snes-macos-1','architecture':'arm64','profile':profile,
             'capture':capture,'program_sha256':_sha(canonical(program)),
             'seed_sha256':_sha((destination/'seed.json').read_bytes()),'native_core':native,
             'frontend_source_sha256':_sha(source),'frontend_sha256':_sha(executable.read_bytes()),
             'app':app.name,'executable':str(executable.relative_to(destination)),
             'display':'authored world-coordinate grid and selected actor markers; no original camera or artwork',
             'limits':['prepared source scene; bounded source projection',
                       'source script transitions and full scene progression unqualified',
                       'unsupported states stop with the complete native state unchanged',
                       'private build embeds captured game data; do not publish',
                       'host requests 60 Hz; no full-game or presentation equivalence claim']}
    if profile=='live-morgue':receipt['limits']+=['experimental live collision rebuild, fixed captured 7F tables and explicit analysis-step budget']
    if profile=='static-morgue':receipt['limits']+=['captured static collision data; autonomous actors unqualified']
    if profile=='npc-intro':receipt['limits']+=['two noncolliding NPC controllers/kinematics only; rendering flags and animation excluded; direction/task changes refuse']
    (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
