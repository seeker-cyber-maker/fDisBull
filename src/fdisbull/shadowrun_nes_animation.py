"""Private CNROM right-walk animation experiment, based on a source capture.

This is a separate, finite profile, not a general Shadowrun NES backend. The
source-derived actor material and generated cartridge must remain private.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

from .game_il import canonical, emit_c
from .shadowrun_animation import ANIMATION_SOURCE, lift_animation_counter, observed_poses, observed_right_walk_pose
from .shadowrun_scene_assets import decode_vdp_snapshot
from .udc_nes_shadowrun import build_opening_atlas_probe

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_nes_animation.c'
EXPECTED_FRAMES = list(range(5999, 6061))
CAPTURE_RECEIPT_SHA256 = 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c'
RIGHT_POSE_POINTERS = (0x9e8e, 0x9e46, 0x9e58, 0x9e10, 0x9e22, 0x9dec, 0x9dfe)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _word(raw: bytes, address: int) -> int:
    return (raw[address ^ 1] << 8) | raw[(address + 1) ^ 1]


def _round16(value: int) -> int:
    value &= 0xffff
    if value & 0x8000:
        value -= 0x10000
    return (value >> 4) + bool(value & 8)


def build_right_walk_animation_probe(rom: bytes, capture_dir, output, *, cc65_root,
                                     atlas_rgb: bytes, atlas_coverage: bytes,
                                     atlas_conflicts: bytes, atlas_origin_x: int,
                                     atlas_origin_y: int, atlas_row_offset: int = 0,
                                     max_pattern_merges: int = 0) -> dict:
    """Build a separately registered, finite, right-only animated NES probe.

    It validates the one observed source run and its sprite-anchor relationship
    before compiling. Inputs outside this run's qualified selector/pose boundary
    refuse; palette reduction and CNROM are target adaptations.
    """
    capture = Path(capture_dir).resolve()
    root=Path(cc65_root).expanduser().resolve()
    base_platform=Path(__file__).parent / 'game_sources/shadowrun_nes_atlas.c'
    tracked={'backend_module':Path(__file__).resolve(), 'backend_c':SOURCE,
             'counter_author_c':ANIMATION_SOURCE, 'base_platform_c':base_platform,
             'cl65':root/'bin/cl65', 'cc65':root/'bin/cc65',
             'ca65':root/'bin/ca65', 'ld65':root/'bin/ld65',
             'nes_cfg':root/'cfg/nes.cfg', 'nes_lib':root/'lib/nes.lib'}
    tracked_hashes={name:_sha(path.read_bytes()) for name,path in tracked.items()}
    counter_program=lift_animation_counter(rom)
    receipt_raw = (capture / 'capture.json').read_bytes()
    if _sha(receipt_raw) != CAPTURE_RECEIPT_SHA256:
        raise ValueError('right-walk profile requires the reviewed capture receipt')
    receipt = json.loads(receipt_raw)
    observed = observed_poses(rom, capture, EXPECTED_FRAMES)
    poses, observations = observed['poses'], observed['observations']
    if len(poses) != 7:
        raise ValueError('unexpected observed pose set')
    files = receipt['files']
    rams = []
    for frame in EXPECTED_FRAMES:
        rel = f'native/scene-{frame:06d}/ram.bin'
        raw = (capture / rel).read_bytes()
        expected = files.get(rel, {})
        if len(raw) != 65536 or expected.get('size') != len(raw) or expected.get('sha256') != _sha(raw):
            raise ValueError('captured actor RAM does not match receipt')
        rams.append(raw)
    # Refuse a different observed state even when the caller supplied a valid
    # receipt. This profile's timing and pose identities are source-qualified
    # on this finite run only.
    if receipt.get('assistance') != 'ordinary controller schedule; no memory patches':
        raise ValueError('right-walk profile requires ordinary unpatched capture')
    offsets=[]
    for pointer in RIGHT_POSE_POINTERS:
        for off in (8, 10):
            value=int.from_bytes(rom[pointer+off:pointer+off+2], 'big', signed=True)
            if not -128 <= value <= 127:
                raise ValueError('unsupported source sprite anchor')
            offsets.append(value & 255)
    for i in range(1, len(observations)):
        prior=rams[i-1]; item=observations[i]
        result=observed_right_walk_pose(rom, _word(prior,0x10e), _word(prior,0x116), _word(prior,0x11e))
        pose=result['pose']
        if item['pose'] != pose:
            raise ValueError('observed selector/pose phase mismatch')
        ptr=RIGHT_POSE_POINTERS[pose]
        x=_round16(_word(prior,0x100)-_word(prior,0xddc6))+int.from_bytes(rom[ptr+8:ptr+10],'big',signed=True)
        y=_round16(_word(prior,0x104)-_word(prior,0xddc8))+int.from_bytes(rom[ptr+10:ptr+12],'big',signed=True)
        if (x,y)!=(item['screen_x'],item['screen_y']):
            raise ValueError('source sprite anchor mismatch')
    initial=rams[0]
    if (_word(initial,0x10e),_word(initial,0x116),_word(initial,0x11e)) != (3,0x10,0):
        raise ValueError('unsupported initial actor state')
    def data(name):
        return (capture/f'native/scene-005999/{name}.bin').read_bytes()
    scene=decode_vdp_snapshot(data('vram'),data('cram'),data('vsram'),data('reg'))
    out=Path(output).expanduser().resolve()
    result=build_opening_atlas_probe(rom,scene,initial,out,actor_sat_index=1,cc65_root=cc65_root,
        atlas_rgb=atlas_rgb,atlas_coverage=atlas_coverage,atlas_conflicts=atlas_conflicts,
        atlas_origin_x=atlas_origin_x,atlas_origin_y=atlas_origin_y,atlas_row_offset=atlas_row_offset,
        max_pattern_merges=max_pattern_merges,enable_stoker=False)
    # The base builder generates this private platform copy. Changes are
    # applied only there; its source and other existing backend are untouched.
    platform=(out/'platform.c').read_text()
    def replace_once(old, new):
        nonlocal platform
        if platform.count(old)!=1: raise ValueError('opening platform integration point changed')
        platform=platform.replace(old,new,1)
    replace_once('void main(void) {', '#include "shadowrun_nes_animation.c"\n\nvoid main(void) {')
    replace_once('    shadowrun_seed_scene();', '    shadowrun_seed_scene();\n'
        f'    shadowrun_anim_accumulator={_word(initial,0x11a)}U;\n'
        f'    shadowrun_anim_increment={_word(initial,0x118)}U;\n'
        f'    shadowrun_anim_threshold={_word(initial,0x11c)}U;\n'
        f'    shadowrun_anim_index={_word(initial,0x11e)}U;\n'
        f'    shadowrun_anim_flags={initial[0x111^1]}U;')
    replace_once('        wait_vblank();pad=read_pad();\n        if (!view_fault) {',
                 '        wait_vblank();pad=read_pad();\n        if (!view_fault && anim_allow(pad)) {')
    replace_once('            shadowrun_opening_frame(pad);\n#endif\n        }',
                 '            shadowrun_opening_frame(pad);\n#endif\n            anim_after();\n        }')
    replace_once('PUBLICATION[2]=view_fault?5:shadowrun_opening_status;',
                 'PUBLICATION[2]=anim_fault?6:(view_fault?5:shadowrun_opening_status);')
    replace_once('        PUBLICATION[23]++;',
        '        PUBLICATION[26]=anim_display;PUBLICATION[27]=anim_pending;PUBLICATION[28]=anim_fault;\n'
        '        PUBLICATION[29]=(u8)shadowrun_anim_index;PUBLICATION[30]=(u8)shadowrun_anim_accumulator;\n'
        '        PUBLICATION[31]=(u8)(shadowrun_anim_accumulator>>8);\n        PUBLICATION[23]++;')
    replace_once('            place_actor();OAMADDR=0;OAMDMA=2;',
                 '            if(anim_started && !anim_fault) anim_place_actor();OAMADDR=0;OAMDMA=2;')
    (out/'platform.c').write_text(platform)
    source=SOURCE.read_bytes();(out/'shadowrun_nes_animation.c').write_bytes(source)
    (out/'anim.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n'+emit_c(counter_program))
    pose_oam=b''.join(p['oam_offsets'].ljust(64,b'\xf0') for p in poses)
    counts=bytes(len(p['oam_offsets'])//4 for p in poses)
    if any(n>16 for n in counts) or any(p['palette']!=poses[0]['palette'] for p in poses):
        raise ValueError('unsupported target pose geometry or palette')
    (out/'anim-oam.bin').write_bytes(pose_oam)
    (out/'anim-count.bin').write_bytes(counts)
    (out/'anim-offsets.bin').write_bytes(bytes(offsets))
    (out/'anim-selector.bin').write_bytes(rom[0xc062:0xc072])
    with (out/'data.s').open('a') as f:
        f.write('\n.export _shadowrun_anim_oam,_shadowrun_anim_count,_shadowrun_anim_offsets,_shadowrun_anim_selector_table,_shadowrun_anim_bank_values\n'
                '_shadowrun_anim_oam: .incbin "anim-oam.bin"\n_shadowrun_anim_count: .incbin "anim-count.bin"\n'
                '_shadowrun_anim_offsets: .incbin "anim-offsets.bin"\n_shadowrun_anim_selector_table: .incbin "anim-selector.bin"\n'
                '_shadowrun_anim_bank_values: .byte 0,1,2,3,4,5,6,7\n')
    tool=root/'bin/cl65'
    cmd=[str(tool),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),'--lib-path',str(root/'lib'),
         '-I',str(root/'include'),'-m','animation.map','-Ln','animation-labels.txt','-o','animated.nes',
         'game.c','platform.c','seed.c','anim.c','data.s']
    env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    run=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'animation-build.log').write_text(run.stdout+run.stderr)
    if run.returncode: raise ValueError('NES animation build failed: '+run.stderr[-4000:])
    raw=(out/'animated.nes').read_bytes()
    if raw[:4]!=b'NES\x1a' or len(raw)!=16+32768+8192:
        raise ValueError('unexpected base cartridge layout')
    background=(out/'chr.bin').read_bytes()[:4096]
    chr_banks=b''.join(background+p['chr'] for p in poses+[poses[0]])
    # The base probe may require four-screen VRAM for its four nametables;
    # retain that property when replacing mapper 0 with CNROM.
    base_header=(out/'probe.nes').read_bytes()[:16]
    header=bytearray(raw[:16]);header[5]=8
    header[6]=(base_header[6]&15)|0x30;header[7]&=15
    image=bytes(header)+raw[16:16+32768]+chr_banks
    (out/'animated.nes').write_bytes(image)
    if any(_sha(path.read_bytes()) != tracked_hashes[name] for name,path in tracked.items()):
        raise ValueError('build source or toolchain changed during build')
    if (capture/'capture.json').read_bytes()!=receipt_raw:
        raise ValueError('capture receipt changed during build')
    for frame in EXPECTED_FRAMES:
        for name in ('vram','cram','vsram','reg','ram'):
            rel=f'native/scene-{frame:06d}/{name}.bin'
            payload=(capture/rel).read_bytes();record=files.get(rel,{})
            if record.get('size') != len(payload) or record.get('sha256') != _sha(payload):
                raise ValueError('capture payload changed during build')
    manifest={'format':'fdisbull-shadowrun-right-walk-animation-1','rom_sha256':_sha(rom),
              'capture_receipt_sha256':_sha(receipt_raw),'source_sha256':_sha(source),
              'counter_gameil_sha256':_sha(canonical(counter_program)),
              'build_sources_and_toolchain_sha256':tracked_hashes,
              'generated_counter_c_sha256':_sha((out/'anim.c').read_bytes()),
              'generated_platform_c_sha256':_sha((out/'platform.c').read_bytes()),
              'generated_game_c_sha256':_sha((out/'game.c').read_bytes()),
              'capture_payloads_revalidated_after_build':True,
              'output_sha256':_sha(image),'base_output_sha256':result['output_sha256'],
              'source_pose_anchor_checks':60,'source_selector_pose_checks':61,'pose_count':7,
              'publication':{'address':0x700,'length':32,'status_byte':2,'rom_fault_byte':3,
                             'sequence_byte':22,'completed_tick_byte':23,
                             'display_pose_byte':26,'pending_pose_byte':27,'animation_fault_byte':28,
                             'animation_index_byte':29,'animation_accumulator_little_endian':30,
                             'status_6':'animation input or unsupported-state refusal',
                             'animation_fault_values':{'0':'none','1':'unsupported input or state',
                                                       '2':'60-update observation limit reached'},
                             'sequence_contract':'odd during publication, even after complete; counters wrap modulo 256'},
              'scope':'right-only observed opening animation with source counter and selector; CNROM target adaptation',
              'limitations':['stops after 60 completed right-walk updates',
                             'refuses other actions and unsupported selector/index states',
                             'no sound','no complete game','no hardware timing or NES visual parity claim']}
    (out/'animation-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
