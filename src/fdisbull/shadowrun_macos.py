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
from .game_il import GameMachine, author_program, canonical, emit_c
from .shadowrun_ai_play import actor_service_from_capture, lift_actor_service
from .shadowrun_enemy_waypoint import SOURCE as WAYPOINT_SOURCE
from .shadowrun_enemy_idle import SOURCE as IDLE_SOURCE
from .shadowrun_enemy_east_slide import SOURCE as EAST_SLIDE_SOURCE
from .shadowrun_enemy_outer_slide import SOURCE as OUTER_SLIDE_SOURCE
from .shadowrun_assisted_arena import assisted_arena_from_capture, lift_assisted_arena
from .shadowrun_replay import _bundle, _read_rom, _source_capture, SNAPSHOT_FILES
from .udl_shadowrun import ROM_SHA256, lift_opening_stoker
from .shadowrun_menu import SOURCE as MENU_SOURCE, lift_menu

APP_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_macos_app.m'
COURTYARD_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_courtyard_adapter.c'
EAST_EXIT_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_enemy_east_slide_exit.c'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def lift_captured_courtyard(rom):
    """Compose the qualified captured-actor projection with a hard-stop entry."""
    base = lift_actor_service(rom)
    raw = COURTYARD_SOURCE.read_bytes();waypoint=WAYPOINT_SOURCE.read_bytes();idle=IDLE_SOURCE.read_bytes();east=EAST_SLIDE_SOURCE.read_bytes();outer=OUTER_SLIDE_SOURCE.read_bytes();east_exit=EAST_EXIT_SOURCE.read_bytes()
    source=emit_c(base)
    typedef='typedef unsigned long u32;'
    prefix='\nu32 shadowrun_ai_waypoint_table,shadowrun_courtyard_waypoint_table[7];\nu16 shadowrun_ai_waypoint_index,shadowrun_courtyard_waypoint_index[7];\nu8 shadowrun_ai_waypoint_supported,shadowrun_ai_idle_supported,shadowrun_ai_east_slide_supported,shadowrun_ai_east_slide_exit_supported;\nvoid shadowrun_ai_waypoint_arrival(void);void shadowrun_ai_idle_tick(void);void shadowrun_ai_east_slide(void);void shadowrun_ai_east_slide_exit(void);void shadowrun_ai_outer_east_slide_projection(void);'
    if source.count(typedef)!=1:raise ValueError('Courtyard type declaration changed')
    source=source.replace(typedef,typedef+prefix,1)
    def once(old,new):
        nonlocal source
        if source.count(old)!=1:raise ValueError('Courtyard actor composition changed')
        source=source.replace(old,new,1)
    once('  shadowrun_ai_outer_movement_projection();',
         '  if (shadowrun_ai_outer_flags_low==4U) shadowrun_ai_outer_east_slide_projection(); else shadowrun_ai_outer_movement_projection();')
    once('  shadowrun_ai_actor_tick();\n  if (!shadowrun_ai_supported)',
         '  if (shadowrun_ai_callback==0xb45cUL) { shadowrun_ai_idle_tick(); shadowrun_ai_supported=shadowrun_ai_idle_supported; } else { shadowrun_ai_actor_tick(); if (shadowrun_ai_supported && (shadowrun_ai_flags_low&4U)) { shadowrun_ai_east_slide_exit(); if (!shadowrun_ai_east_slide_exit_supported) shadowrun_ai_supported=0; } else if (!shadowrun_ai_supported) { shadowrun_ai_east_slide(); if (shadowrun_ai_east_slide_supported) shadowrun_ai_supported=1; } }\n  if (!shadowrun_ai_supported)')
    once('  shadowrun_ai_slot_heading[slot] = shadowrun_ai_heading;\n  shadowrun_ai_slot_move_state[slot] = shadowrun_ai_move_state;',
         '  shadowrun_ai_slot_heading[slot] = shadowrun_ai_heading; shadowrun_ai_slot_transition_heading[slot]=shadowrun_ai_transition_heading; shadowrun_target_flags_low[slot]=shadowrun_ai_flags_low;\n  shadowrun_ai_slot_move_state[slot] = shadowrun_ai_move_state;')
    once('  if (!shadowrun_ai_service_supported)\n  {\n    shadowrun_ai_slot_status[slot] = 2;',
         '  if (!shadowrun_ai_service_supported) { shadowrun_ai_waypoint_table=shadowrun_courtyard_waypoint_table[slot]; shadowrun_ai_waypoint_index=shadowrun_courtyard_waypoint_index[slot]; shadowrun_ai_waypoint_arrival(); if (shadowrun_ai_waypoint_supported) { shadowrun_ai_service_supported=1; shadowrun_courtyard_waypoint_index[slot]=shadowrun_ai_waypoint_index; } }\n  if (!shadowrun_ai_service_supported)\n  {\n    shadowrun_ai_slot_status[slot] = 2;')
    once('  shadowrun_ai_slot_direction[slot] = shadowrun_ai_service_direction;\n  if (shadowrun_ai_callback != 0xb574UL)\n    shadowrun_ai_slot_status[slot] = 2;',
         '  shadowrun_ai_slot_direction[slot] = shadowrun_ai_service_direction;\n  shadowrun_ai_slot_waypoint_x[slot]=shadowrun_ai_waypoint_x; shadowrun_ai_slot_waypoint_y[slot]=shadowrun_ai_waypoint_y;\n  if (shadowrun_ai_callback != 0xb574UL && shadowrun_ai_callback != 0xb45cUL) shadowrun_ai_slot_status[slot] = 2;')
    extra='\n'.join(line for content in (waypoint,idle,east,outer,east_exit) for line in content.decode().splitlines()
                    if line not in ('u32 shadowrun_ai_waypoint_table;','u16 shadowrun_ai_waypoint_index;',
                                    'u8 shadowrun_ai_waypoint_supported;','u8 shadowrun_ai_idle_supported;','u8 shadowrun_ai_east_slide_supported;','u8 shadowrun_ai_east_slide_exit_supported;'))
    program = author_program(source+'\n'+extra+'\n'+raw.decode(),
        [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
        evidence={'kind':'captured-courtyard-directional', 'components':[base['evidence']],
                  'adapter_sha256':_sha(raw),'waypoint_sha256':_sha(waypoint),'idle_sha256':_sha(idle),'east_slide_sha256':_sha(east),'outer_slide_sha256':_sha(outer),'east_exit_sha256':_sha(east_exit),
                  'scope':'captured actors, qualified waypoint/idle, bounded directional movement; actions refuse'})
    if COURTYARD_SOURCE.read_bytes()!=raw or WAYPOINT_SOURCE.read_bytes()!=waypoint or IDLE_SOURCE.read_bytes()!=idle or EAST_SLIDE_SOURCE.read_bytes()!=east or OUTER_SLIDE_SOURCE.read_bytes()!=outer or EAST_EXIT_SOURCE.read_bytes()!=east_exit:
        raise ValueError('Courtyard source changed while lifting')
    return program


def captured_courtyard_from_capture(rom, snapshot_path):
    """Seed the unpatched captured-courtyard actor state; no hostile is added."""
    baseline = actor_service_from_capture(rom, snapshot_path)
    _, arrays, _ = _source_capture(snapshot_path, ROM_SHA256)
    raw = arrays['ram']
    hp = raw[0x14c ^ 1]
    if hp != 10:
        raise ValueError('Unexpected captured party health')
    machine = GameMachine(lift_captured_courtyard(rom), {0:rom})
    machine.set_state(baseline.snapshot())
    memory=bytes(raw[i^1] for i in range(len(raw)))
    offsets=[0x400+i*0x100 for i in range(7)]
    tables=[int.from_bytes(memory[x+0xe0:x+0xe4],'big') for x in offsets]
    indices=[int.from_bytes(memory[x+0xe4:x+0xe6],'big') for x in offsets]
    machine.set_state({'shadowrun_courtyard_profile':1,'shadowrun_arena_hp':hp,
                       'shadowrun_courtyard_waypoint_table':tables,'shadowrun_courtyard_waypoint_index':indices})
    return machine


def build_macos_assisted_arena(path, *, rom_path, capture, output, preset='stationary'):
    """Build a private arm64 AppKit app from the reviewed source and capture.

    ``path`` is the receipt-bound opening bundle manifest. The app stores only
    an absolute reference to the caller's ROM; it does not copy the ROM into
    the bundle. Original assets and all generated output stay outside Git.
    """
    if preset not in ('stationary', 'moving', 'courtyard'):
        raise ValueError('Arena preset must be stationary, moving or courtyard')
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
    menu_source = MENU_SOURCE.read_bytes()
    menu_program = lift_menu(rom)
    if preset == 'courtyard':
        program = lift_captured_courtyard(rom)
        machine = captured_courtyard_from_capture(rom, capture_path)
    else:
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
    plist = {'CFBundleIdentifier':'org.fdisbull.shadowrun.assisted.menu.'+preset,
             'CFBundleName':'Shadowrun Assisted Arena', 'CFBundleExecutable':'ShadowrunArena',
             'CFBundlePackageType':'APPL', 'CFBundleVersion':'1',
             'NSHighResolutionCapable':True, 'FDisBullSourceROM':str(rom_file)}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
    executable = macos / 'ShadowrunArena'
    env = {k:v for k,v in os.environ.items() if not k.startswith(('DYLD_', 'CC65_', 'LD_'))}
    env['LC_ALL'] = 'C'
    command = ['/usr/bin/clang','-arch','arm64','-fobjc-arc','-O2','-framework','Cocoa',
               '-I',str(core_dir),str(APP_SOURCE),str(MENU_SOURCE),'-L',str(core_dir),'-lfdisbull_native',
               '-Wl,-rpath,@loader_path','-o',str(executable)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    (destination / 'frontend-build.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('AppKit frontend compilation failed: ' + result.stderr[-4000:])
    current = lift_captured_courtyard(rom) if preset=='courtyard' else lift_assisted_arena(rom)
    if (APP_SOURCE.read_bytes()!=source or MENU_SOURCE.read_bytes()!=menu_source or manifest_path.read_bytes()!=manifest_bytes or
        _read_rom(rom_file)!=rom or canonical(current)!=canonical(program) or canonical(lift_menu(rom))!=canonical(menu_program)):
        raise ValueError('App inputs changed during build')
    receipt = {'format':'fdisbull-shadowrun-macos-arena-1', 'preset':preset,
               'architecture':'arm64', 'source_sha256':_sha(rom),
               'program_sha256':_sha(canonical(program)), 'capture_receipt_sha256':identity['capture_json_sha256'],
               'bundle_manifest_sha256':_sha(manifest_bytes), 'frontend_source_sha256':_sha(source),
               'menu_source_sha256':_sha(menu_source), 'menu_program_sha256':_sha(canonical(menu_program)),
               'frontend_sha256':_sha(executable.read_bytes()), 'native_core':native,
               'app':'Shadowrun Arena.app', 'executable':'Shadowrun Arena.app/Contents/MacOS/ShadowrunArena',
               'display':'authored symbolic terrain and actor projection',
               'limits':(['unpatched captured courtyard','directional controls only'] if preset=='courtyard' else ['assisted encounter'])+['bounded source branches','unsupported states stop',
                         'no original artwork or death-scene claim','host timer requests 60 Hz; performance requires measurement']}
    (destination / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
