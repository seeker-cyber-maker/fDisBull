"""Private native controls for a separate Shadowrun AI profile.

The first control validates native dead-procedure elimination against the
frozen static-NPC GameIL. It does not itself implement or claim NPC AI.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

from .game_il import canonical
from .shadowrun_ai_play import emit_reachable_c, actor_service_from_capture, lift_actor_service
from .shadowrun_nes_play import build_play
from .shadowrun_play import lift_play
from .shadowrun_replay import _read_rom
from . import shadowrun_ai_play


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def build_pruned_control(manifest_path, *, rom_path, capture, cc65_root, output):
    """Build a new private static-profile control with unreachable C removed.

    Both source trees and toolchain are rechecked; an executable is not native
    execution evidence. Existing Shadowrun play builds remain untouched.
    """
    own_source = Path(__file__).read_bytes()
    selector_source = Path(shadowrun_ai_play.__file__).read_bytes()
    rom = _read_rom(rom_path)
    program = lift_play(rom)
    native, selection = emit_reachable_c(program, roots=['shadowrun_play_frame'])
    if set(selection['omitted']) != {'shadowrun_linked_launch', 'shadowrun_linked_tick',
                                     'shadowrun_player_walk_direct'}:
        raise ValueError('Unexpected native call graph; refusing unreviewed pruning')
    out = Path(output).expanduser().resolve()
    base = build_play(manifest_path, rom_path=rom_path, capture=capture,
                      cc65_root=cc65_root, output=out)
    if base['program_sha256'] != _sha(canonical(program)):
        raise ValueError('Static control source differs from fresh lift')
    baseline = (out/'play.nes').read_bytes()
    baseline_receipt = (out/'play-receipt.json').read_bytes()
    (out/'baseline.nes').write_bytes(baseline)
    (out/'baseline-receipt.json').write_bytes(baseline_receipt)
    (out/'game.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n' + native)
    root = Path(cc65_root).expanduser().resolve()
    tool = root/'bin/cl65'
    paths = [tool, root/'bin/cc65', root/'bin/ca65', root/'bin/ld65',
             root/'cfg/nes.cfg', root/'lib/nes.lib']
    before = {str(path): _sha(path.read_bytes()) for path in paths}
    env = {k:v for k,v in os.environ.items() if not k.startswith(('CC65_', 'LD_', 'DYLD_'))}
    env['LC_ALL'] = 'C'
    run = subprocess.run([str(tool), '-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),
                          '--lib-path',str(root/'lib'),'-I',str(root/'include'),
                          '-m','control.map','-Ln','control-labels.txt','-o','control.nes',
                          'game.c','platform.c','seed.c','data.s'],
                         cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'control-build.log').write_text(run.stdout+run.stderr)
    if run.returncode:
        raise ValueError('Pruned NES control build failed: '+run.stderr[-4000:])
    built = (out/'control.nes').read_bytes()
    if built[:4] != b'NES\x1a' or len(built) != 16+32768+8192:
        raise ValueError('Unexpected NES control layout')
    # Preserve the validated target's mapper flags and CHR projection.
    image = baseline[:16] + built[16:16+32768] + baseline[16+32768:]
    (out/'play.nes').write_bytes(image)
    if (_read_rom(rom_path) != rom or _sha(canonical(lift_play(rom))) != _sha(canonical(program)) or
            Path(__file__).read_bytes() != own_source or
            Path(shadowrun_ai_play.__file__).read_bytes() != selector_source or
            any(_sha(path.read_bytes()) != before[str(path)] for path in paths)):
        raise ValueError('Source or toolchain changed during control build')
    receipt = {'format':'fdisbull-shadowrun-ai-native-control-1',
               'source_rom_sha256':_sha(rom), 'program_sha256':_sha(canonical(program)),
               'output_sha256':_sha(image), 'baseline_sha256':_sha(baseline),
               'baseline_receipt_sha256':_sha(baseline_receipt),
               'native_c_sha256':_sha(native.encode()), 'selection':selection,
               'selector_source_sha256':_sha(selector_source),
               'toolchain_sha256':before, 'executed':False,
               'scope':'static-NPC source model with unreachable native procedures omitted; no AI'}
    (out/'play-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def build_directional_actor_profile(manifest_path, *, rom_path, capture, cc65_root, output):
    """Build a separate calm-actor directional experiment, not complete AI."""
    own_source=Path(__file__).read_bytes()
    selector_source=Path(shadowrun_ai_play.__file__).read_bytes()
    rom=_read_rom(rom_path)
    program=lift_actor_service(rom)
    model=actor_service_from_capture(rom,Path(capture)/'native/scene-005999')
    if canonical(program)!=canonical(model.program):raise ValueError('Actor lift changed')
    native,selection=emit_reachable_c(program,roots=['shadowrun_ai_frame'])
    out=Path(output).expanduser().resolve()
    baseline=build_play(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=out)
    base_image=(out/'play.nes').read_bytes()
    (out/'baseline.nes').write_bytes(base_image)
    (out/'baseline-receipt.json').write_bytes((out/'play-receipt.json').read_bytes())
    (out/'game.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n'+native)
    state=model.snapshot()
    names=[name for name in state if name.startswith('shadowrun_ai_slot_')]
    names += ['shadowrun_ai_service_pause','shadowrun_ai_combat_global','shadowrun_ai_visible_alert']
    names += ['shadowrun_ai_overlap_flags','shadowrun_ai_overlap_x','shadowrun_ai_overlap_y',
              'shadowrun_ai_overlap_target','shadowrun_ai_overlap_attacker']
    assignments=[];declarations=[]
    for name in names:
        value=state[name]
        typ=('u32' if name in ('shadowrun_ai_slot_callback','shadowrun_ai_overlap_target','shadowrun_ai_overlap_attacker') else
             'u8' if name in ('shadowrun_ai_slot_corners','shadowrun_ai_slot_status',
                              'shadowrun_ai_slot_equipment_flags','shadowrun_ai_slot_attribute',
                              'shadowrun_ai_slot_max_hp','shadowrun_ai_slot_direction','shadowrun_ai_service_pause',
                              'shadowrun_ai_slot_b3_unknown','shadowrun_ai_overlap_flags','shadowrun_ai_visible_alert',
                              'shadowrun_ai_slot_visible_class','shadowrun_ai_slot_visibility_unknown') else 'u16')
        suffix='UL' if typ=='u32' else 'U'
        if isinstance(value,list):
            declarations.append(f'extern {typ} {name}[];')
            assignments.extend(f'    {name}[{i}]={v}{suffix};' for i,v in enumerate(value))
        else:
            declarations.append(f'extern {typ} {name};')
            assignments.append(f'    {name}={value}{suffix};')
    platform=(out/'platform.c').read_text()
    def replace_once(text,old,new):
        if text.count(old)!=1:raise ValueError('Unexpected native platform source')
        return text.replace(old,new)
    platform=replace_once(platform,'#define PPUCTRL',
        '\n'.join(declarations)+'\nextern const u8 shadowrun_ai_move_tables[];\nextern void shadowrun_ai_frame(u8);\n#define PPUCTRL')
    platform=replace_once(platform,'    if(region!=0) {rom_fault=1;return 0;}\n',
        '    if(region!=0) {rom_fault=1;return 0;}\n'
        '    if(offset>=0xbd72UL && offset<0xc081UL) {i=(u16)(offset-0xbd72UL);return ((u16)shadowrun_ai_move_tables[i]<<8)|shadowrun_ai_move_tables[i+1];}\n')
    platform=replace_once(platform,'    shadowrun_seed_scene();\n',
                          '    shadowrun_seed_scene();\n'+'\n'.join(assignments)+'\n')
    platform=replace_once(platform,'pad=read_pad();shadowrun_play_frame(pad);',
                          'pad=read_pad();shadowrun_ai_frame(pad);')
    platform=replace_once(platform,'        PUBLICATION[23]++;PUBLICATION[22]++;',
        '        for(i=0;i<7;i++) {u16 at=84U+i*5U; PUBLICATION[at]=shadowrun_ai_slot_status[i];'
        'PUBLICATION[at+1]=(u8)shadowrun_target_x[i];PUBLICATION[at+2]=(u8)(shadowrun_target_x[i]>>8);'
        'PUBLICATION[at+3]=(u8)shadowrun_target_y[i];PUBLICATION[at+4]=(u8)(shadowrun_target_y[i]>>8);}\n'
        '        PUBLICATION[23]++;PUBLICATION[22]++;')
    platform=replace_once(platform,'if ((shadowrun_target_flags[i]&1U) && ax>=view_x',
                          'if (shadowrun_ai_slot_status[i]==1U && (shadowrun_target_flags[i]&1U) && ax>=view_x')
    (out/'platform.c').write_text(platform)
    (out/'actor-move-tables.bin').write_bytes(rom[0xbd72:0xc082])
    with (out/'data.s').open('a') as f:
        f.write('\n.export _shadowrun_ai_move_tables\n_shadowrun_ai_move_tables: .incbin "actor-move-tables.bin"\n')
    root=Path(cc65_root).expanduser().resolve()
    paths=[root/'bin'/x for x in ('cl65','cc65','ca65','ld65')]+[root/'cfg/nes.cfg',root/'lib/nes.lib']
    before={str(path):_sha(path.read_bytes()) for path in paths}
    env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    run=subprocess.run([str(root/'bin/cl65'),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),
                        '--lib-path',str(root/'lib'),'-I',str(root/'include'),'-m','actor.map',
                        '-Ln','actor-labels.txt','-o','actor.nes','game.c','platform.c','seed.c','data.s'],
                       cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'actor-build.log').write_text(run.stdout+run.stderr)
    if run.returncode:raise ValueError('Actor NES build failed: '+run.stderr[-4000:])
    built=(out/'actor.nes').read_bytes()
    if built[:4]!=b'NES\x1a' or len(built)!=16+32768+8192:raise ValueError('Unexpected NES layout')
    image=base_image[:16]+built[16:16+32768]+base_image[16+32768:]
    (out/'play.nes').write_bytes(image)
    if (_read_rom(rom_path)!=rom or canonical(lift_actor_service(rom))!=canonical(program) or
        Path(__file__).read_bytes()!=own_source or Path(shadowrun_ai_play.__file__).read_bytes()!=selector_source or
        any(_sha(path.read_bytes())!=before[str(path)] for path in paths)):
        raise ValueError('Source or toolchain changed during actor build')
    receipt={'format':'fdisbull-shadowrun-nes-directional-actors-1',
        'source_rom_sha256':_sha(rom),'program_sha256':_sha(canonical(program)),
        'output_sha256':_sha(image),'baseline_sha256':_sha(base_image),
        'native_c_sha256':_sha(native.encode()),'selector_source_sha256':_sha(selector_source),
        'selection':selection,'toolchain_sha256':before,'baseline_program_sha256':baseline['program_sha256'],
        'scope':'direction-only calm captured actors; unsupported action and actor states refuse',
        'excluded':['enemy attacks','damage to player','actor idle and near-waypoint callbacks','inventory','targeting','firing','scene travel'],
        'executed':False}
    (out/'play-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
