"""Private, bounded NES inventory-browser experiment for the captured scene."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .game_il import canonical, emit_c
from .shadowrun_play import SOURCE as PLAY_SOURCE, DEBUG_SOURCE, SHOT_SOURCE, TARGET_SOURCE, ACTOR_SOURCE, ORDERED_SOURCE, LINKED_SOURCES, captured_target_state, lift_play
from .shadowrun_inventory import SOURCE as INVENTORY_SOURCE
from .shadowrun_field_combat import SOURCE as FIELD_SOURCE, MOTION_SOURCE
from .shadowrun_replay import (_bundle, _read_rom, _sha, _source_capture,
                               ANIMATED_ATLAS_SHA256, SNAPSHOT_FILES)
from .shadowrun_scene_assets import decode_vdp_snapshot
from .udc_nes_shadowrun import build_opening_atlas_probe

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_nes_play.c'


def _font(chr_data: bytes, first: int):
    # Authored hexadecimal font and cursor; not source artwork.
    rows = {
        '0':'01110 10001 10011 10101 11001 10001 01110','1':'00100 01100 00100 00100 00100 00100 01110',
        '2':'01110 10001 00001 00010 00100 01000 11111','3':'11110 00001 00001 01110 00001 00001 11110',
        '4':'00010 00110 01010 10010 11111 00010 00010','5':'11111 10000 10000 11110 00001 00001 11110',
        '6':'01110 10000 10000 11110 10001 10001 01110','7':'11111 00001 00010 00100 01000 01000 01000',
        '8':'01110 10001 10001 01110 10001 10001 01110','9':'01110 10001 10001 01111 00001 00001 01110',
        'A':'01110 10001 10001 11111 10001 10001 10001','B':'11110 10001 10001 11110 10001 10001 11110',
        'C':'01111 10000 10000 10000 10000 10000 01111','D':'11110 10001 10001 10001 10001 10001 11110',
        'E':'11111 10000 10000 11110 10000 10000 11111','F':'11111 10000 10000 11110 10000 10000 10000',
        '>':'10000 01000 00100 00010 00100 01000 10000',
        'I':'11111 00100 00100 00100 00100 00100 11111','N':'10001 11001 10101 10011 10001 10001 10001',
        'V':'10001 10001 10001 10001 10001 01010 00100','T':'11111 00100 00100 00100 00100 00100 00100',
        'O':'01110 10001 10001 10001 10001 10001 01110','R':'11110 10001 10001 11110 10100 10010 10001',
        'Y':'10001 10001 01010 00100 00100 00100 00100','S':'01111 10000 10000 01110 00001 00001 11110',
        'L':'10000 10000 10000 10000 10000 10000 11111','U':'10001 10001 10001 10001 10001 10001 01110',
        'W':'10001 10001 10001 10101 10101 10101 01010','Q':'01110 10001 10001 10001 10101 10010 01101','M':'10001 11011 10101 10101 10001 10001 10001','P':'11110 10001 10001 11110 10000 10000 10000','X':'10001 10001 01010 00100 01010 10001 10001',
    }
    if first + len(rows) > 256: raise ValueError('Atlas has insufficient space for menu font')
    data=bytearray(chr_data); mapping={c:first+i for i,c in enumerate(rows)}
    for c, bits in rows.items():
        base=mapping[c]*16
        data[base:base+16]=bytes(16)
        for row, b in enumerate(bits.split()): data[base+row]=int(b,2)<<2
    table=bytearray(1024)
    for row,line in ((2,'INVENTORY'),(18,'ARMOR'),(20,'WEAPON AMMO'),(24,'A EQUIP'),(26,'START EXIT')):
        for col,c in enumerate(line):
            if c!=' ': table[row*32+3+col]=mapping[c]
    return bytes(data),bytes(table)+bytes((0x0f,0x30,0x10,0x00))*4,bytes(mapping[c] for c in '0123456789ABCDEF>')+bytes([0])


def build_play(manifest_path, *, rom_path, capture, cc65_root, output):
    """Build a new private cartridge; unsupported actions explicitly refuse."""
    manifest_raw=Path(manifest_path).read_bytes()
    tracked={p:p.read_bytes() for p in (SOURCE,PLAY_SOURCE,DEBUG_SOURCE,SHOT_SOURCE,TARGET_SOURCE,ACTOR_SOURCE,ORDERED_SOURCE,FIELD_SOURCE,MOTION_SOURCE,INVENTORY_SOURCE,Path(__file__),*LINKED_SOURCES)}
    _, manifest, payloads = _bundle(manifest_path)
    rom=_read_rom(rom_path)
    from .udl_shadowrun import lift_opening_stoker
    if canonical(lift_opening_stoker(rom)) != canonical(json.loads(payloads['program.uil.json'])):
        raise ValueError('Bundle differs from current source lift')
    if any(_sha(payloads[n]) != digest for n,digest in ANIMATED_ATLAS_SHA256.items()):
        raise ValueError('Play profile requires independently reviewed atlas')
    identity, arrays, _ = _source_capture(Path(capture)/'native/scene-005999', _sha(rom))
    if identity['capture_json_sha256'] != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':
        raise ValueError('Play profile requires the reviewed scene-2 capture')
    if any(arrays[field] != payloads[name] for name,(field,_) in SNAPSHOT_FILES.items()):
        raise ValueError('Play capture differs from bundle')
    program=lift_play(rom)
    scene=decode_vdp_snapshot(arrays['vram'],arrays['cram'],arrays['vsram'],arrays['reg'])
    out=Path(output).expanduser().resolve()
    base=build_opening_atlas_probe(rom,scene,arrays['ram'],out,actor_sat_index=1,cc65_root=cc65_root,
        atlas_rgb=payloads['atlas/vdp-rgb.bin'],atlas_coverage=payloads['atlas/vdp-coverage.bin'],
        atlas_conflicts=payloads['atlas/vdp-conflicts.bin'],atlas_origin_x=768,atlas_origin_y=512,
        atlas_row_offset=0,max_pattern_merges=0,enable_stoker=False)
    os.chmod(out,0o700)
    raw=arrays['ram']; memory=bytes(raw[i^1] for i in range(len(raw)))
    seed='\n'.join([*(f'    shadowrun_inventory_cell{i}={memory[0x166+i]}U;' for i in range(8)),
        *(f'    shadowrun_play_phase{i}={memory[0x16e+i]}U;' for i in range(8)),
        f'    shadowrun_inventory_equipped_armor={memory[0x176]}U;',
        f'    shadowrun_play_action_gate={memory[0xf09f]}U;', f'    shadowrun_play_weapon_slot={memory[0x156]}U;', f'    shadowrun_play_weapon_item={memory[0x157]}U;', f'    shadowrun_play_ammo={memory[0x14e]}U;', f'    shadowrun_play_weapon_aux={memory[0x19d]}U;', f'    shadowrun_field_rng={int.from_bytes(memory[0xf9f8:0xf9fa],"big")}U;', '    shadowrun_play_shot_eligible=1;', f'    shadowrun_play_shot_timer={int.from_bytes(memory[0x1dc:0x1de],"big")}U;', f'    shadowrun_field_death_timer={memory[0xf0ce]}U;', f'    shadowrun_field_type13_deaths={memory[0xfbfa]}U;', f'    shadowrun_field_party_counter_a={memory[0x18d]}U;', f'    shadowrun_field_party_counter_b={memory[0x28d]}U;', f'    shadowrun_field_party_counter_c={memory[0x38d]}U;'])
    for name,values in captured_target_state(memory).items():
        if isinstance(values,list):
            seed+='\n'+'\n'.join(f'    {name}[{i}]={v}U;' for i,v in enumerate(values))
        else: seed+=f'\n    {name}={values}U;'
    platform=SOURCE.read_text().replace('    /* PLAY_SEED */',seed)
    (out/'platform.c').write_text(platform)
    (out/'game.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n'+emit_c(program))
    # Every 32-pixel source cell becomes one eight-pixel target tile. These
    # categories show byte ranges, not collision or visual appearance.
    word=lambda a:int.from_bytes(memory[a:a+2], 'big')
    xmin,xmax,ymin,ymax=word(0xddd6),word(0xddd2),word(0xddd8),word(0xddd4)
    names=[bytearray(1024) for _ in range(4)]
    for y in range(44):
        for x in range(64):
            v=memory[0x1700+y*64+x]
            category=0 if x*32>xmax or x*32+31<xmin or y*32>ymax or y*32+31<ymin else (1 if v==0 else 2 if v==127 else 3 if v<128 else 4)
            names[(y//30)*2+x//32][(y%30)*32+x%32]=category
    # Authored tiles distinguish unknown, zero, 127, low and high raw bytes.
    patterns=[bytes(16), bytes([0x18]*8+[0]*8), bytes([0xff]*8+[0]*8),
              bytes([0x55,0xaa]*4+[0]*8),bytes([0xff,0x81]*4+[0xff]*8)]
    chr_base=bytearray(8192)
    for i,p in enumerate(patterns):chr_base[i*16:i*16+16]=p
    chr_base[4096:4112]=bytes([0x18,0x3c,0x7e,0xff,0xff,0x7e,0x3c,0x18]+[0]*8)
    chr_base[4112:4128]=bytes([0x81,0x42,0x24,0x18,0x18,0x24,0x42,0x81]+[0]*8)
    chr_data,screen,hexchars=_font(bytes(chr_base),5)
    palette=bytes([0x0f,0x10,0x20,0x30]*4+[0x0f,0x30,0x20,0x10,0x0f,0x16,0x27,0x30]+[0x0f,0x30,0x20,0x10]*2)
    chr_mutable=bytearray(chr_data)
    for i in range(16):chr_mutable[4096+(2+i)*16:4096+(3+i)*16]=chr_mutable[(5+i)*16:(6+i)*16]
    chr_data=bytes(chr_mutable)
    (out/'scene.bin').write_bytes(palette)
    (out/'weapon-table.bin').write_bytes(rom[0xd4594:0xd4596])
    (out/'linked-tables.bin').write_bytes(rom[0x15a4c:0x16396])
    (out/'chr.bin').write_bytes(chr_data);(out/'play-screen.bin').write_bytes(screen);(out/'play-hex.bin').write_bytes(hexchars)
    data_source=(out/'data.s').read_text()
    data_source=data_source.replace('_shadowrun_table_camera,_shadowrun_camera_valid', '_shadowrun_table_camera')
    data_source=data_source.replace('_shadowrun_camera_valid: .incbin "camera-valid.bin"\n','')
    (out/'data.s').write_text(data_source)
    with (out/'data.s').open('a') as f:
        f.write('\n.export _shadowrun_linked_tables\n_shadowrun_linked_tables: .incbin "linked-tables.bin"\n.export _shadowrun_weapon_table\n_shadowrun_weapon_table: .incbin "weapon-table.bin"\n.export _shadowrun_play_screen,_shadowrun_play_hex\n_shadowrun_play_screen: .incbin "play-screen.bin"\n_shadowrun_play_hex: .incbin "play-hex.bin"\n')
    root=Path(cc65_root).expanduser().resolve()
    cmd=[str(root/'bin/cl65'),'-t','nes','-Oirs','-C',str(root/'cfg/nes.cfg'),'--lib-path',str(root/'lib'),
         '-I',str(root/'include'),'-m','play.map','-Ln','play-labels.txt','-o','play.nes',
         'game.c','platform.c','seed.c','data.s']
    env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    run=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'play-build.log').write_text(run.stdout+run.stderr)
    if run.returncode: raise ValueError('NES play build failed: '+run.stderr[-4000:])
    image=(out/'play.nes').read_bytes()
    if image[:4]!=b'NES\x1a' or len(image)!=16+32768+8192: raise ValueError('Unexpected NES layout')
    header=bytearray(image[:16]);header[6]=(out/'probe.nes').read_bytes()[6]
    image=bytes(header)+image[16:16+32768]+chr_data
    (out/'play.nes').write_bytes(image)
    if _read_rom(rom_path)!=rom: raise ValueError('ROM changed during build')
    if Path(manifest_path).read_bytes()!=manifest_raw or any(p.read_bytes()!=raw for p,raw in tracked.items()):
        raise ValueError('Build input changed during build')
    _, after, _ = _source_capture(Path(capture)/'native/scene-005999', _sha(rom))
    if after!=arrays: raise ValueError('Capture changed during build')
    result={'format':'fdisbull-shadowrun-nes-play-browser-1','source_rom_sha256':_sha(rom),
            'program_sha256':_sha(canonical(program)),'output_sha256':_sha(image),
            'capture_ram_sha256':_sha(arrays['ram']), 'intermediate_opening_build':base,
            'presentation': {'type':'symbolic 64x44 captured terrain categories', 'category_legend': {'0':'outside field bounds','1':'raw 0','2':'raw 127','3':'raw 1..126','4':'raw 128..255'}, 'walkability':'unknown'},
            'scope':'prepared scene 2, symbolic terrain, bounded equipment and linked combat against frozen captured NPCs, assisted debug placement',
            'unsupported':['other equipment and actor types','NPC AI and line of sight','original projectile pool lifecycle','scene transitions','audio','dynamic actor collision outside the captured profiles'],
            'executed':False}
    (out/'play-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
