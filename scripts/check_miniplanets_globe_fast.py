#!/usr/bin/env python3
"""Compare actual 6502 renderer hot loops with their preceding C implementation.

Original projection/atlas/map fixtures and all build outputs stay private.
The pinned cc65 sim65 CPU measures instruction cycles, excluding NES mapper,
IRQ and presentation scheduling. Full cartridge behavior is a separate gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sim65.h>
typedef unsigned char u8;
typedef unsigned int u16;
u8 display_plane[256],display_palettes[256],projection_cache[256],world[256];
u8 display_hud[24],display_attributes[16],lives,time_secs,stage_name,keys_left;
unsigned long score;
u8 objects[192],player_x,player_y,player_jump,player_die;u16 render_epoch;
u8 mace_x(u8 slot){return slot;} u8 mace_y(u8 slot){return slot;}
u16 object_projection_pair(u8 x,u8 y,u8 raft){return x+y+raft;}
void banked_call(void){}

u8 render_oam_page,render_oam_index,oam_overflow,globe_source_hi,globe_rowbase,globe_colbase;
u16 globe_atlas_pointer;
const u8 tile_palette[35]={0,2,2,1,3,0,0,2,0,3,3,0,0,0,0,3,2,0,3,2,0,2,2,1,1,1,1,1,1,1,1,1,1,1,1};
void globe_clear(void);
void globe_copy_projection(void);
void globe_paint_terrain(void);
struct Input {
    u8 view[256],atlas[1260],map[256],rowbase,colbase,page,sourcehi,atlas_shift;
};
struct Output {u8 plane[256],palettes[256],cache[256],oam[512];};
static struct Input input;
static struct Output expected;
static u8 atlas[1516];
static unsigned long cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
static void setup(void){
    memset(display_plane,0xa5,256);memset(display_palettes,0x5a,256);
    memset(projection_cache,0x91,256);memset((void*)0x200,0x3c,512);
    render_oam_page=input.page;globe_source_hi=input.sourcehi;
    globe_rowbase=input.rowbase;globe_colbase=input.colbase;
    memcpy(world,input.map,256);memcpy(atlas+input.atlas_shift,input.atlas,1260);
    globe_atlas_pointer=(u16)(atlas+input.atlas_shift);
    memcpy((void*)((u16)globe_source_hi<<8),input.view,256);
}
/* The original C loop bodies, with their already-bound input pointers. */
static void clear_reference(void){
    u16 i;volatile u8 *oam;
    oam=(volatile u8*)((u16)render_oam_page<<8);
    for(i=0;i<256;i=i+1){display_plane[i]=0;display_palettes[i]=0;oam[i]=255;}
}
static void copy_reference(void){
    u16 index;const u8 *view;
    view=(const u8*)((u16)globe_source_hi<<8);
    for(index=0;index<256;index=index+1)projection_cache[index]=view[index];
}
static void paint_reference(void){
    const u8 *view;const u8 *terrain;u16 index,pattern;
    u8 sprite,position,mapoff,mapindex,tile,rowbase,colbase,palette;
    view=projection_cache;terrain=(const u8*)globe_atlas_pointer;
    rowbase=globe_rowbase;colbase=globe_colbase;
    for(sprite=0;sprite<64;sprite=sprite+1){
        index=(u16)(63-sprite)*4;position=view[index];mapoff=view[index+1];
        mapindex=(u8)(((mapoff+rowbase)&240)|((mapoff+colbase)&15));
        tile=world[mapindex];if(tile>=35)tile=0;
        pattern=(u16)tile*36+view[index+2];palette=tile_palette[tile];
        display_plane[position]=terrain[pattern];display_plane[position+1]=terrain[pattern+1];
        display_plane[position+16]=terrain[pattern+2];display_plane[position+17]=terrain[pattern+3];
        display_palettes[position]=palette;display_palettes[position+1]=palette;
        display_palettes[position+16]=palette;display_palettes[position+17]=palette;
    }
}
int main(void){
    u16 i,block,count;int n;unsigned long start,c0,c1,c2,f0,f1,f2;
    unsigned long rc0,rc1,rc2,fc0,fc1,fc2,m0,m1,m2;
    count=block=0;rc0=rc1=rc2=fc0=fc1=fc2=m0=m1=m2=0;
    if(sizeof(input)!=1777)return 5;
    while((n=read(0,&input,sizeof(input)))!=0){
        if(n!=sizeof(input)){printf("short input %d\n",n);return 6;}
        setup();start=cycles();clear_reference();c0=cycles()-start;
        start=cycles();copy_reference();c1=cycles()-start;
        start=cycles();paint_reference();c2=cycles()-start;
        memcpy(expected.plane,display_plane,256);memcpy(expected.palettes,display_palettes,256);
        memcpy(expected.cache,projection_cache,256);memcpy(expected.oam,(void*)0x200,512);
        setup();start=cycles();globe_clear();f0=cycles()-start;
        start=cycles();globe_copy_projection();f1=cycles()-start;
        start=cycles();globe_paint_terrain();f2=cycles()-start;
        if(memcmp(expected.plane,display_plane,256)||memcmp(expected.palettes,display_palettes,256)
           ||memcmp(expected.cache,projection_cache,256)||memcmp(expected.oam,(void*)0x200,512)){
            for(i=0;i<256;i++)if(expected.plane[i]!=display_plane[i]){
                printf("plane mismatch case%u byte%u actual%u expected%u\n",count,i,display_plane[i],expected.plane[i]);return 1;
            }
            printf("palette/cache/OAM mismatch case%u\n",count);return 2;
        }
        if(memcmp(world,input.map,256)||memcmp(atlas+input.atlas_shift,input.atlas,1260)
           ||memcmp((void*)((u16)globe_source_hi<<8),input.view,256)){
            printf("immutable input changed case%u\n",count);return 3;
        }
        rc0+=c0;rc1+=c1;rc2+=c2;fc0+=f0;fc1+=f1;fc2+=f2;
        if(f0>m0)m0=f0;if(f1>m1)m1=f1;if(f2>m2)m2=f2;
        count++;block++;
        if(block==256){
            printf("BLOCK %u %lu %lu %lu %lu %lu %lu %lu %lu %lu\n",block,rc0,rc1,rc2,fc0,fc1,fc2,m0,m1,m2);
            block=0;rc0=rc1=rc2=fc0=fc1=fc2=m0=m1=m2=0;
        }
    }
    if(block)printf("BLOCK %u %lu %lu %lu %lu %lu %lu %lu %lu %lu\n",block,rc0,rc1,rc2,fc0,fc1,fc2,m0,m1,m2);
    printf("PASS %u\n",count);return 0;
}
'''


def verify(rom_path, toolchain, output):
    from fdisbull.udl_miniplanets_full import checked_rom, globe_assets
    rom_path, toolchain, output = map(lambda x: Path(x).resolve(), (rom_path, toolchain, output))
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        raise ValueError('choose a fresh output outside Git')
    output.mkdir(parents=True)
    rom = checked_rom(rom_path.read_bytes())
    source_dir = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources'
    assembly = source_dir / 'nes_globe_fast.s'
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     (assembly, source_dir / 'nes_globe_renderer.c')}
    assets = globe_assets(rom)
    maps = []
    for stage in (0, 19, 46):
        header = 0x655CA + stage * 8
        at = int.from_bytes(rom[header:header + 4], 'big')
        maps.append((f'original-stage-{stage}', rom[at:at + 256]))
    maps.extend((('authored-all35-classes', bytes(i % 35 for i in range(256))),
                 ('authored-invalid-class-clamp', bytes(range(256)))))
    case_path = output / 'cases.bin'
    with case_path.open('wb') as cases:
        for _, world in maps:
            for animation in range(32):
                for view in range(256):
                    cases.write(assets['projection'][view * 256:(view + 1) * 256])
                    cases.write(assets['terrain_frames'][animation])
                    cases.write(world)
                    cases.write(bytes((((view + animation * 3) & 15) * 16,
                                       ((view >> 4) + animation) & 15,
                                       2 + (view & 1), 0xA0 + (view & 31),
                                       (animation * 236) & 255)))
    config = (toolchain / 'cfg/sim6502.cfg').read_text().replace(
        'start = $0200, size = $FFC0 - $0200 - __STACKSIZE__',
        'start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0')
    config = config.replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
    (output / 'sim.cfg').write_text(config)
    (output / 'harness.c').write_text(HARNESS)
    (output / assembly.name).write_bytes(assembly.read_bytes())
    command = [str(toolchain / 'bin/cl65'), '-t', 'sim6502', '-Oirs', '--static-locals',
               '-C', str(output / 'sim.cfg'), '-m', str(output / 'map.txt'), '-Ln', str(output / 'labels.txt'),
               '-o', str(output / 'check'), str(output / assembly.name), str(output / 'harness.c')]
    build = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / 'build.txt').write_text(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError(build.stderr[-3000:])
    with case_path.open('rb') as stream:
        run = subprocess.run([str(toolchain / 'bin/sim65'), '-c', str(output / 'check')],
                             stdin=stream, capture_output=True, text=True, timeout=300)
    (output / 'run.txt').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    rows = [list(map(int, line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('BLOCK ')]
    count = sum(row[0] for row in rows)
    if count != len(maps) * 32 * 256 or f'PASS {count}' not in run.stdout:
        raise RuntimeError('native renderer case count is incomplete')
    totals = [sum(row[i] for row in rows) for i in range(1, 7)]
    maxima = [max(row[i] for row in rows) for i in range(7, 10)]
    receipt = {'format': 'fdisbull-globe-6502-check-1', 'passed': True,
               'cases': count, 'camera_views': 256, 'animation_phases': 32,
               'maps': [{'name': name, 'sha256': hashlib.sha256(world).hexdigest()} for name, world in maps],
               'source_hashes': source_hashes, 'harness_sha256': hashlib.sha256(HARNESS.encode()).hexdigest(),
               'private_fixture_sha256': hashlib.sha256(case_path.read_bytes()).hexdigest(),
               'compiled_program_sha256': hashlib.sha256((output / 'check').read_bytes()).hexdigest(),
               'reference_mean_cycles': dict(zip(('clear', 'copy', 'paint'), (n / count for n in totals[:3]))),
               'fast_mean_cycles': dict(zip(('clear', 'copy', 'paint'), (n / count for n in totals[3:]))),
               'fast_max_cycles': dict(zip(('clear', 'copy', 'paint'), maxima)),
               'claim': 'actual assembled 6502 instructions match the preceding C hot-loop outputs and preserve immutable inputs',
               'limits': ['sim65 CPU procedure boundary; NES mapper, IRQ, full-frame scheduling and visible output require separate checks',
                          'cycle readings include the small C call/counter-read overhead and this harness memory layout',
                          'source data fixtures, maps, atlas bytes and built programs remain private']}
    for path in (assembly, source_dir / 'nes_globe_renderer.c'):
        if hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[path.name]:
            raise RuntimeError('renderer source changed during verification')
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True)
    parser.add_argument('--cc65-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.rom, args.cc65_root, args.output), indent=2))
