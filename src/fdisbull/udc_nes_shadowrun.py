"""Compile bounded Shadowrun GameIL and observed-scene NES experiments.

The opening build has guarded movement, collision, camera, and an optional
Stoker request with an authored target dialogue projection. It is not a full
game port; byte-retaining output must remain in private storage.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from .game_il import canonical, emit_c
from .udl_shadowrun import (checked_rom, lift_input, project_observed_frame,
                            project_vdp_scene, project_world_atlas, lift_opening_stoker,
                            lift_opening_walk, lift_opening_camera, TABLE_START)

def _authored_stoker_screens(chr_bytes, first_tile):
    """Author readable target labels; no original game text or assets."""
    glyphs = {
        'A':'01110 10001 10001 11111 10001 10001 10001',
        'B':'11110 10001 10001 11110 10001 10001 11110',
        'C':'01111 10000 10000 10000 10000 10000 01111',
        'D':'11110 10001 10001 10001 10001 10001 11110',
        'E':'11111 10000 10000 11110 10000 10000 11111',
        'F':'11111 10000 10000 11110 10000 10000 10000',
        'G':'01111 10000 10000 10111 10001 10001 01111',
        'H':'10001 10001 10001 11111 10001 10001 10001',
        'I':'11111 00100 00100 00100 00100 00100 11111',
        'K':'10001 10010 10100 11000 10100 10010 10001',
        'L':'10000 10000 10000 10000 10000 10000 11111',
        'M':'10001 11011 10101 10101 10001 10001 10001',
        'N':'10001 11001 10101 10011 10001 10001 10001',
        'O':'01110 10001 10001 10001 10001 10001 01110',
        'P':'11110 10001 10001 11110 10000 10000 10000',
        'R':'11110 10001 10001 11110 10100 10010 10001',
        'S':'01111 10000 10000 01110 00001 00001 11110',
        'T':'11111 00100 00100 00100 00100 00100 00100',
        'U':'10001 10001 10001 10001 10001 10001 01110',
        'V':'10001 10001 10001 10001 10001 01010 00100',
        'W':'10001 10001 10001 10101 10101 10101 01010',
        'Y':'10001 10001 01010 00100 00100 00100 00100',
    }
    labels=(('STOKER SIGN','MOTEL ENTRANCE','A CONTINUE'),
            ('MANAGER','B LEAVE','OTHER CHOICES NOT AVAILABLE'),
            ('FAREWELL','A RETURN'),('CHOICE NOT AVAILABLE','RETURNING TO MENU'))
    if first_tile+len(glyphs)>256:raise ValueError('Atlas leaves too few tiles for authored dialogue font')
    data=bytearray(chr_bytes);indices={c:first_tile+i for i,c in enumerate(glyphs)}
    for char,rows in glyphs.items():
        base=indices[char]*16
        for row,bits in enumerate(rows.split()):data[base+row]=int(bits,2)<<2
    screens=bytearray()
    for lines in labels:
        table=bytearray(1024)
        for row,line in enumerate(lines):
            for col,char in enumerate(line):
                if char!=' ':table[(8+row*3)*32+2+col]=indices[char]
        screens.extend(table+bytes((0x0f,0x30,0x10,0x00))*4)
    return bytes(data),bytes(screens)


PLATFORM = r'''
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
extern const u8 shadowrun_scene[1312];
extern u16 shadowrun_pad_held,shadowrun_pad_sample,shadowrun_direction_angle;
extern void shadowrun_input_tick(u8);
extern const u16 shadowrun_direction_table[16];
#define PPUCTRL (*(volatile u8*)0x2000)
#define PPUMASK (*(volatile u8*)0x2001)
#define PPUSTATUS (*(volatile u8*)0x2002)
#define PPUADDR (*(volatile u8*)0x2006)
#define PPUDATA (*(volatile u8*)0x2007)
#define PPUSCROLL (*(volatile u8*)0x2005)
#define PAD (*(volatile u8*)0x4016)
#define OAMADDR (*(volatile u8*)0x2003)
#define OAMDMA (*(volatile u8*)0x4014)
#define OAM ((volatile u8*)0x0200)
#define PUBLICATION ((volatile u8*)0x0700)
u16 rom16(u8 region,u32 offset) {
    if(region!=0 || offset<0x19d2UL || offset>=0x19f2UL || (offset&1)) return 0;
    return shadowrun_direction_table[(u8)((offset-0x19d2UL)>>1)];
}
static void wait_vblank(void) {
    while(PPUSTATUS & 0x80) {}
    while(!(PPUSTATUS & 0x80)) {}
}
static u8 read_pad(void) {
    u8 i,v=0;
    static const u8 bits[8]={0x40,0x10,0x20,0x80,1,2,4,8};
    PAD=1;PAD=0;
    for(i=0;i<8;i++)if(PAD&1)v|=bits[i];
    return v;
}
void main(void) {
    u16 i;
    u8 pad;
    PPUMASK=0;PPUCTRL=0;
    wait_vblank();
    PPUADDR=0x3f;PPUADDR=0;
    for(i=0;i<32;i++)PPUDATA=shadowrun_scene[1024+i];
    PPUADDR=0x20;PPUADDR=0;
    for(i=0;i<1024;i++)PPUDATA=shadowrun_scene[i];
    for(i=0;i<256;i++)OAM[i]=shadowrun_scene[1056+i];
    OAMADDR=0;OAMDMA=2;
    PPUSCROLL=0;PPUSCROLL=0;PPUCTRL=8;PPUMASK=0x1e;
    for(;;) {
        wait_vblank();pad=read_pad();shadowrun_input_tick(pad);
        PUBLICATION[0]=0x53;PUBLICATION[1]=0x52;
        PUBLICATION[2]=(u8)shadowrun_pad_held;PUBLICATION[3]=(u8)(shadowrun_pad_held>>8);
        PUBLICATION[4]=(u8)shadowrun_pad_sample;PUBLICATION[5]=(u8)(shadowrun_pad_sample>>8);
        PUBLICATION[6]=(u8)shadowrun_direction_angle;PUBLICATION[7]=(u8)(shadowrun_direction_angle>>8);
    }
}
'''


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def build_input_scene_probe(rom: bytes, observed_png: bytes, output, *, cc65_root) -> dict:
    """Build a private mapper-0 diagnostic, failing closed on other ROMs."""
    rom = checked_rom(rom)
    projection = project_observed_frame(rom, observed_png)
    return _build_probe(rom, projection, output, cc65_root=cc65_root)


def build_vdp_scene_probe(rom: bytes, scene, output, *, actor_sat_index: int, cc65_root) -> dict:
    """Build a private background-plus-static-actor and input diagnostic."""
    rom = checked_rom(rom)
    projection = project_vdp_scene(rom, scene, actor_sat_index=actor_sat_index)
    return _build_probe(rom, projection, output, cc65_root=cc65_root)


def _build_probe(rom, projection, output, *, cc65_root):
    program = lift_input(rom)
    root = Path(cc65_root).expanduser().resolve()
    tool = root / 'bin' / 'cl65'
    config = root / 'cfg' / 'nes.cfg'
    library = root / 'lib' / 'nes.lib'
    if not all(p.is_file() for p in (tool, config, library)):
        raise ValueError('Expected a prepared cc65 NES toolchain')
    out = Path(output).expanduser().resolve()
    if out.exists() or any((p / '.git').exists() for p in (out, *out.parents)):
        raise ValueError('Choose a new private output outside Git')
    out.mkdir(parents=True)
    sprite_oam = projection.get('sprite_oam', b'')
    scene = (projection['nametable'] + projection['attributes'] + projection['palette'] +
             projection.get('sprite_palette', projection['palette']) + sprite_oam +
             bytes((0xf0, 0, 0, 0)) * (64 - len(sprite_oam)//4))
    if len(scene) != 1312:
        raise ValueError('Invalid projected sprite/OAM length')
    (out / 'scene.bin').write_bytes(scene)
    (out / 'chr.bin').write_bytes(projection['chr'] + projection.get('sprite_chr', bytes(4096)))
    (out / 'game.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n' + emit_c(program))
    values = [int.from_bytes(rom[TABLE_START+i:TABLE_START+i+2], 'big') for i in range(0, 32, 2)]
    (out / 'platform.c').write_text(PLATFORM + '\nconst unsigned int shadowrun_direction_table[16]={' + ','.join(str(v) for v in values) + '};\n')
    (out / 'scene.s').write_text('''\n.segment "RODATA"\n.export _shadowrun_scene\n_shadowrun_scene:\n.incbin "scene.bin"\n''')
    cmd = [str(tool), '-t', 'nes', '-Oirs', '-C', str(config), '--lib-path', str(root/'lib'),
           '-I', str(root/'include'), '-m', 'game.map', '-Ln', 'labels.txt',
           '-o', 'probe.nes', 'game.c', 'platform.c', 'scene.s']
    env = {k:v for k,v in os.environ.items() if not k.startswith(('CC65_', 'LD_', 'DYLD_'))}
    env['LC_ALL'] = 'C'
    run = subprocess.run(cmd, cwd=out, env=env, capture_output=True, text=True, timeout=120)
    (out/'build.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise ValueError('NES probe build failed: ' + run.stderr[-4000:])
    raw = (out/'probe.nes').read_bytes()
    if raw[:4] != b'NES\x1a' or len(raw) != 16 + 32768 + 8192:
        raise ValueError('Unexpected NES probe cartridge format')
    # The standard cc65 NES startup contributes an 8 KiB default CHR segment.
    # Replace just that explicitly located cartridge segment with the private
    # scene projection; no source-game image bytes are included in the repo.
    raw = raw[:16 + 32768] + (out/'chr.bin').read_bytes()
    (out/'probe.nes').write_bytes(raw)
    manifest = {'format':'fdisbull-shadowrun-nes-input-probe-1', 'source_rom_sha256':_sha(rom),
                'program_sha256':_sha(canonical(program)), 'observed_frame':projection['evidence'],
                'output_sha256':_sha(raw), 'cc65_sha256':_sha(tool.read_bytes()),
                'config_sha256':_sha(config.read_bytes()), 'library_sha256':_sha(library.read_bytes()),
                'input_publication':{'address':0x700, 'length':8, 'byte_order':'little',
                    'mapping':'NES A/B/Select/Start to Genesis A/B/C/Start; D-pad unchanged'},
                'scope':'native input-state diagnostic with a static projected background and optional actor',
                'excludes':['movement','collision','interaction','live sprites','audio','whole-game lift',
                            'original NES release','original pixel equivalence','natural scene reachability']}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def build_opening_probe(rom: bytes, scene, raw_ram: bytes, output, *, actor_sat_index: int, cc65_root) -> dict:
    """Build an assisted clear-walk experiment, not a complete opening port.

    The caller supplies one captured Genesis work-RAM snapshot and a separate
    VDP scene from the same intended moment. That association, and the actor
    identity, are caller assumptions. The background/camera and actor pose
    are frozen; actions and nonzero collision outcomes explicitly refuse.
    """
    return _build_opening_probe(rom, scene, raw_ram, output, actor_sat_index=actor_sat_index,
                                cc65_root=cc65_root, atlas=None)


def build_opening_atlas_probe(rom: bytes, scene, raw_ram: bytes, output, *, actor_sat_index: int,
                              cc65_root, atlas_rgb: bytes, atlas_coverage: bytes,
                              atlas_conflicts: bytes, atlas_origin_x: int, atlas_origin_y: int,
                              atlas_row_offset: int, max_pattern_merges: int = 0,
                              enable_stoker: bool = False) -> dict:
    """Build an assisted, source-camera-driven bounded observed-atlas probe."""
    atlas = project_world_atlas(rom, atlas_rgb, atlas_coverage, atlas_conflicts,
                                world_y0=atlas_row_offset, max_pattern_merges=max_pattern_merges)
    return _build_opening_probe(rom, scene, raw_ram, output, actor_sat_index=actor_sat_index,
                                cc65_root=cc65_root, atlas=atlas,
                                atlas_origin_x=atlas_origin_x, atlas_origin_y=atlas_origin_y,
                                enable_stoker=enable_stoker)


def _build_opening_probe(rom, scene, raw_ram, output, *, actor_sat_index, cc65_root,
                         atlas, atlas_origin_x=0, atlas_origin_y=0, enable_stoker=False):
    rom = checked_rom(rom)
    if not isinstance(raw_ram, bytes) or len(raw_ram) != 65536:
        raise ValueError('Expected a full byte-paired Genesis work-RAM capture')
    memory = bytes(raw_ram[i ^ 1] for i in range(len(raw_ram)))
    word = lambda a: int.from_bytes(memory[a:a+2], 'big')
    long = lambda a: int.from_bytes(memory[a:a+4], 'big')
    if (word(0x10e) == 13 or memory[0x110] & 10 != 10 or word(0x10c) == 0 or
            memory[0x19e] & 32 or word(0xdf84) != 0 or memory[0xe168] & 1 or
            long(0xddec) != 0x172daa):
        raise ValueError('Captured state is outside the reviewed opening movement branch')
    xmin, xmax, ymin, ymax = word(0xddd6), word(0xddd2), word(0xddd8), word(0xddd4)
    if (xmin < 12 or ymin < 7 or xmax <= xmin or ymax <= ymin or
            xmax + 11 > 4095 or ymax + 6 > 4095 or
            ((((ymax + 6) << 1) & 0xffc0) + ((xmax + 11) >> 5)) >= 2816):
        raise ValueError('Captured field bounds exceed the supported terrain-map slice')
    if type(enable_stoker) is not bool or (enable_stoker and atlas is None):
        raise ValueError('Stoker projection requires an explicitly enabled atlas probe')
    program = (lift_opening_stoker(rom) if enable_stoker else
               lift_opening_camera(rom) if atlas is not None else lift_opening_walk(rom))
    projection = project_vdp_scene(rom, scene, actor_sat_index=actor_sat_index)
    root = Path(cc65_root).expanduser().resolve()
    tool = root/'bin'/'cl65'
    config = root/'cfg'/'nes.cfg'
    library = root/'lib'/'nes.lib'
    if not all(p.is_file() for p in (tool, config, library)):
        raise ValueError('Expected a prepared cc65 NES toolchain')
    out = Path(output).expanduser().resolve()
    if out.exists() or any((p/'.git').exists() for p in (out, *out.parents)):
        raise ValueError('Choose a new private output outside Git')
    out.mkdir(parents=True)
    oam = projection['sprite_oam']
    background = (b''.join(atlas['nametables']) if atlas is not None else
                  projection['nametable'] + projection['attributes'])
    data = (background + (atlas['palette'] if atlas is not None else projection['palette']) +
            projection['sprite_palette'] + oam + bytes((0xf0,0,0,0))*(64-len(oam)//4))
    if len(data)!=(len(background)+288):
        raise ValueError('Invalid projected scene size')
    (out/'scene.bin').write_bytes(data)
    (out/'chr.bin').write_bytes((atlas['chr'] if atlas is not None else projection['chr'])+projection['sprite_chr'])
    if enable_stoker:
        chr_data,ui_data=_authored_stoker_screens((out/'chr.bin').read_bytes(),atlas['evidence']['target_patterns'])
        (out/'ui-scenes.bin').write_bytes(ui_data)
        (out/'chr.bin').write_bytes(chr_data)
    (out/'map.bin').write_bytes(memory[0x1700:0x2200])
    (out/'input-table.bin').write_bytes(rom[0x19d2:0x19f2])
    (out/'move-table.bin').write_bytes(rom[0xbec2:0xbee2])
    (out/'stand-table.bin').write_bytes(rom[0xc052:0xc062])
    (out/'rectangles.bin').write_bytes(rom[0x172daa:0x172eea])
    if atlas is not None:
        if (type(atlas_origin_x) is not int or type(atlas_origin_y) is not int or
                not 0<=atlas_origin_x<4096 or not 0<=atlas_origin_y<4096):
            raise ValueError('Invalid absolute atlas origin')
        camera_x=(word(0xddc6)>>4)-atlas_origin_x
        camera_y=(word(0xddc8)>>4)-atlas_origin_y
        bit=camera_y*256+camera_x
        if (not 0<=camera_x<256 or not 0<=camera_y<=atlas['evidence']['camera_y_max'] or
                not atlas['camera_valid'][bit//8] & (1<<(bit%8))):
            raise ValueError('Captured camera starts outside observed atlas coverage')
        (out/'camera-table.bin').write_bytes(rom[0x15e16:0x15f56])
        (out/'camera-valid.bin').write_bytes(atlas['camera_valid'])
    (out/'game.c').write_text('unsigned int rom16(unsigned char, unsigned long);\n'+emit_c(program))
    platform_source = Path(__file__).with_name('game_sources')/('shadowrun_nes_atlas.c' if atlas is not None else 'shadowrun_nes_opening.c')
    platform = platform_source.read_bytes()
    (out/'platform.c').write_bytes((b'#define SHADOWRUN_STOKER 1\n' if enable_stoker else b'')+
                                   (b'#define SHADOWRUN_STOKER_VISUAL 1\n' if enable_stoker else b'')+platform)
    fields = {'shadowrun_player_x':word(0x100),'shadowrun_player_y':word(0x104),
              'shadowrun_player_contact':word(0x10c),'shadowrun_player_kind':word(0x10e),
              'shadowrun_player_flags':memory[0x110],'shadowrun_player_heading':word(0x12e),
              'shadowrun_player_target_heading':word(0x134),'shadowrun_player_equipment_flags':memory[0x19e],
              'shadowrun_player_flags_low':memory[0x111],'shadowrun_player_callback':long(0x13a),
              'shadowrun_player_event_flags':memory[0x1b0],'shadowrun_global_special_mode':word(0xdf84),
              'shadowrun_scene_mode':word(0xddc4),'shadowrun_event_mode':word(0xdf40),
              'shadowrun_global_vector_flags':memory[0xe168],'shadowrun_x_min':word(0xddd6),
              'shadowrun_x_max':word(0xddd2),'shadowrun_y_min':word(0xddd8),'shadowrun_y_max':word(0xddd4),
              'shadowrun_rect_base':long(0xddec),'shadowrun_pad_held':word(0xdd20)}
    if atlas is not None:
        fields.update({'shadowrun_camera_x':word(0xddc6),'shadowrun_camera_y':word(0xddc8),
                       'shadowrun_camera_min_x':word(0xddca),'shadowrun_camera_max_x':word(0xddce),
                       'shadowrun_camera_min_y':word(0xddcc),'shadowrun_camera_max_y':word(0xddd0),
                       'shadowrun_camera_scroll_ax':word(0xdd08),'shadowrun_camera_scroll_ay':word(0xdd0a),
                       'shadowrun_camera_scroll_bx':word(0xdd0c),'shadowrun_camera_scroll_by':word(0xdd0e),
                       'shadowrun_camera_stream_x':word(0xdf38),'shadowrun_camera_stream_y':word(0xdf36),
                       'shadowrun_camera_freeze_a':word(0xe100),'shadowrun_camera_freeze_b':word(0xe102),
                       'shadowrun_camera_freeze_c':word(0xdfe8),'shadowrun_camera_mode':memory[0xe186],
                       'shadowrun_camera_previous_x':memory[0xe173],'shadowrun_camera_previous_y':memory[0xe174],
                       'shadowrun_camera_supported':1})
    if enable_stoker:
        fields.update({'shadowrun_interaction_context':memory[0xfbf8],
                       'shadowrun_interaction_phase':memory[0xf0d5],
                       'shadowrun_interaction_reaction_flag':word(0xdf84),
                       'shadowrun_interaction_trigger_busy':word(0xdfe8),
                       'shadowrun_interaction_dispatch_carry':1})
    byte_fields = {'shadowrun_player_flags','shadowrun_player_flags_low','shadowrun_player_equipment_flags',
                   'shadowrun_player_event_flags','shadowrun_global_vector_flags',
                   'shadowrun_camera_mode','shadowrun_camera_previous_x','shadowrun_camera_previous_y',
                   'shadowrun_camera_supported','shadowrun_interaction_context',
                   'shadowrun_interaction_phase','shadowrun_interaction_dispatch_carry'}
    lines = ['typedef unsigned char u8;','typedef unsigned int u16;','typedef unsigned long u32;']
    lines += [f'extern {"u8" if k in byte_fields else "u32" if k in ("shadowrun_rect_base","shadowrun_player_callback") else "u16"} {k};' for k in fields]
    lines += [f'const u16 shadowrun_seed_x={fields["shadowrun_player_x"]}U;',
              f'const u16 shadowrun_seed_y={fields["shadowrun_player_y"]}U;',
              f'const u8 shadowrun_sprite_count={len(oam)//4}U;', 'void shadowrun_seed_scene(void){']
    if atlas is not None:
        lines[-1:-1] = [f'const u16 shadowrun_atlas_origin_x={atlas_origin_x}U;',
                        f'const u16 shadowrun_atlas_origin_y={atlas_origin_y}U;',
                        f'const u16 shadowrun_scene_background_size={len(background)}U;',
                        f'const u8 shadowrun_camera_y_max={atlas["evidence"]["camera_y_max"]}U;',
                        f'const u8 shadowrun_fast_sprite={int(all(130<=oam[i+3]<=154 and 50<=oam[i]<=74 for i in range(0,len(oam),4)))}U;']
    lines += [f'{k}={v}UL;' for k,v in fields.items()]
    lines += ['}']
    (out/'seed.c').write_text('\n'.join(lines)+'\n')
    assembly='''\n.segment "RODATA"\n.export _shadowrun_scene,_shadowrun_initial_map\n.export _shadowrun_table_input,_shadowrun_table_move,_shadowrun_table_stand,_shadowrun_table_rectangles\n_shadowrun_scene: .incbin "scene.bin"\n_shadowrun_initial_map: .incbin "map.bin"\n_shadowrun_table_input: .incbin "input-table.bin"\n_shadowrun_table_move: .incbin "move-table.bin"\n_shadowrun_table_stand: .incbin "stand-table.bin"\n_shadowrun_table_rectangles: .incbin "rectangles.bin"\n'''
    if atlas is not None:
        assembly+='''\n.export _shadowrun_table_camera,_shadowrun_camera_valid\n_shadowrun_table_camera: .incbin "camera-table.bin"\n_shadowrun_camera_valid: .incbin "camera-valid.bin"\n'''
    if enable_stoker:
        assembly+='''\n.export _shadowrun_ui_scenes\n_shadowrun_ui_scenes: .incbin "ui-scenes.bin"\n'''
    (out/'data.s').write_text(assembly)
    cmd=[str(tool),'-t','nes','-Oirs','-C',str(config),'--lib-path',str(root/'lib'),
         '-I',str(root/'include'),'-m','game.map','-Ln','labels.txt','-o','probe.nes',
         'game.c','platform.c','seed.c','data.s']
    env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    run=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'build.log').write_text(run.stdout+run.stderr)
    if run.returncode:raise ValueError('NES opening probe build failed: '+run.stderr[-4000:])
    raw=(out/'probe.nes').read_bytes()
    if raw[:4]!=b'NES\x1a' or len(raw)!=16+32768+8192:
        raise ValueError('Unexpected NES probe cartridge format')
    header=bytearray(raw[:16])
    if atlas is not None and len(atlas['nametables'])==4:header[6]|=8
    raw=bytes(header)+raw[16:16+32768]+(out/'chr.bin').read_bytes();(out/'probe.nes').write_bytes(raw)
    if platform_source.read_bytes()!=platform:
        raise ValueError('NES platform source changed during build')
    manifest={'format':'fdisbull-shadowrun-nes-opening-probe-1','source_rom_sha256':_sha(rom),
              'program_sha256':_sha(canonical(program)),'capture_ram_sha256':_sha(raw_ram),
              'output_sha256':_sha(raw),'cc65_sha256':_sha(tool.read_bytes()),
              'platform_sha256':_sha(platform),'scene':projection['evidence'],
              'scope':('assisted guarded player movement and source-camera observed-atlas experiment' if atlas is not None else
                       'assisted, guarded player movement and static-camera visual experiment'),
              'assumptions':['snapshot and VDP state association supplied by caller',
                             'composition timing follows the observed Right route',
                             'snapshot player flags and bounds remain applicable'],
              'unsupported':['actions and interaction','initial negative collision or unknown player table path',
                             'source terrain streaming','sprite animation','audio',
                             'full scene and original pixel equivalence'],
              'publication':{'address':0x700,'length':26 if atlas is not None else 14,'status_byte':2,'fault_byte':3,
                             'statuses':{'0':'neutral','1':'accepted step','2':'unsupported action',
                                         '3':'unsupported player or initial event path','4':'blocked step',
                                         '5':'camera outside captured coverage or unsupported'}}}
    if atlas is not None:
        manifest['atlas']=atlas['evidence']
        manifest['atlas']['absolute_origin']=[atlas_origin_x,atlas_origin_y]
        manifest['publication']['sequence_byte']=22
        manifest['publication']['completed_tick_byte']=23
        manifest['publication']['reentry_active_byte']=24
        manifest['publication']['reentry_tick_byte']=25
        manifest['publication']['sequence_contract']='odd while copying, even after completed publication; counters wrap modulo 256'
        manifest['unsupported'].append(f'NES lines below the validated {atlas["evidence"]["viewport"][1]}-line viewport')
    if enable_stoker:
        manifest['assumptions'].append('Stoker activity-dispatch carry is set, as observed for one source route')
        manifest['dialogue_projection']={'mode':'authored short labels and font for target-only modal progression',
                                         'reentry':'target-only black transition suppresses input while modeled camera moves to fully observed coverage; fails after 240 ticks'}
        manifest['unsupported'][:2] = ['field action buttons and interactions outside the guarded Stoker request',
                                      'other initial negative collision or unknown player table paths']
        manifest['unsupported'].append('animated or general original dialogue engine')
        manifest['publication']['statuses']['6'] = 'target-projected Stoker modal or exit tick'
        manifest['presentation_timing'] = 'current modeled camera; original raster uses previous camera, allowing a one-tick visual offset'
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
