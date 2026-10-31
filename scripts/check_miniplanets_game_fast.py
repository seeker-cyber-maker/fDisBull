#!/usr/bin/env python3
"""Compare known native6502 game intrinsics with compiled C and typed UIL.

All test vectors are authored. Original sine/collision bytes, when --rom is
supplied, are read only from the exact private input and retained only in the
private output directory. This checks local arithmetic/ABI/state effects;
final banked NES integration and real-time behavior require separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
GAME_IL_PATH = ROOT / 'src/fdisbull/game_il.py'
GAME_IL_IMPORTED_SHA256 = hashlib.sha256(GAME_IL_PATH.read_bytes()).hexdigest()
from fdisbull.game_il import GameMachine, author_program
from check_miniplanets_native import _private_output

ROM_SHA256 = 'e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7'
NAMES = ('update_subpixel', 'get_tile', 'get_collision', 'set_tile',
         'collides_player', 'mace_x', 'mace_y')
HEADER = '''typedef unsigned char u8;typedef signed char i8;
typedef unsigned short u16;typedef signed short i16;
typedef unsigned long u32;typedef signed long i32;
u16 anim;u16 subpixel;u8 objects[192];u8 world[256];
u8 player_x;u8 player_y;u8 player_jump;u8 player_die;
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def extract(text, name):
    found = re.search(r'(?:void|u8|u16) ' + name + r'\([^\n]*\)\s*\{.*?^\}', text, re.M | re.S)
    if found is None:
        raise ValueError('reviewed procedure not found: ' + name)
    return found.group()


def array(name, values):
    return 'const u8 ' + name + '[' + str(len(values)) + ']={' + ','.join(map(str, values)) + '};\n'


HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <sim65.h>
typedef unsigned char u8;typedef signed char i8;
typedef unsigned int u16;typedef signed int i16;
typedef unsigned long u32;typedef signed long i32;
u8 before_guard[16];
u16 anim;u16 subpixel;u8 objects[192];u8 world[256];
u8 player_x;u8 player_y;u8 player_jump;u8 player_die;
u8 muteki;u8 player_win;u8 shake_timer;u8 player_action;u8 player_angle;
u8 current_sfx;u8 sfx_to_play;
/* Actor intrinsics are linked but not executed by this primitive suite.
 * Their real handler/effect qualification is a separate actor suite. */
const u8 native_actor_lo[28]={0};
const u8 native_actor_hi[28]={0};
const u8 native_actor_bank[28]={0};
u8 after_guard[16];
u8 reference_world[256];u8 original_objects[192];
u16 stack_pointer(void);
u8 same_stack(u16 original);
void update_subpixel(void);
u8 mace_x(u8 slot);u8 mace_y(u8 slot);
u8 get_tile(u8 x,u8 y);u8 get_collision(u8 x,u8 y);
void set_tile(u8 x,u8 y,u8 tile);
u8 collides_player(u8 x,u8 y,u8 rx,u8 ry);
DATA
u8 rom_fault;
u8 rom8(u8 region,u32 offset) {
    if(region!=0 || offset<0xA514UL || offset>=0xA614UL) {rom_fault=1;return 0;}
    return native_collision[(u16)(offset-0xA514UL)];
}
u16 rom16(u8 region,u32 offset) {
    u16 index;
    if(region!=0 || offset<0x658F8UL || offset>=0x65B87UL) {rom_fault=1;return 0;}
    index=(u16)(offset-0x658F8UL);
    return ((u16)source_sine[index]<<8)|source_sine[index+1];
}
REFERENCE
static u32 cycles(void) {
    peripherals.counter.latch=0;peripherals.counter.select=0;
    return peripherals.counter.value32[0];
}
static u8 guards(void) {
    u16 i;
    for(i=0;i<16;i=i+1) {
        if(before_guard[i]!=(u8)(i*7+1) || after_guard[i]!=(u8)(i*11+3))return 0;
    }
    return 1;
}
static u8 collision_case(u8 x,u8 y,u8 rx,u8 ry) {
    u8 expected,actual,px,py,jump,die;
    u16 sp;
    px=player_x;py=player_y;jump=player_jump;die=player_die;
    sp=stack_pointer();
    expected=reference_collides_player(x,y,rx,ry);
    actual=collides_player(x,y,rx,ry);
    if(expected!=actual || !same_stack(sp) || !guards() || player_x!=px || player_y!=py || player_jump!=jump || player_die!=die) {
        printf("FAIL collision %u %u %u %u player %u %u jump%u die%u expected%u got%u\n",x,y,rx,ry,px,py,jump,die,expected,actual);return 0;
    }
    return 1;
}
int main(void) {
    u16 high,low,i,original,expected,sp,x,y,tile,slot,center,phase,p;
    u16 axis,radius,base,diff,rx,ry,dx,dy,jump,die;
    u8 actual,centers[5],radii[10],edges[16],jumps[6],dies[3];
    u32 start,cost,phase_fast,phase_c,phase_max,mace_fast,mace_c;
    u32 phase_count,mace_count,tile_count,collision_count;
    phase_fast=0;phase_c=0;phase_max=0;mace_fast=0;mace_c=0;
    phase_count=0;mace_count=0;tile_count=0;collision_count=0;
    for(i=0;i<16;i=i+1) {before_guard[i]=(u8)(i*7+1);after_guard[i]=(u8)(i*11+3);}
    for(high=0;high<5;high=high+1) {
        for(low=0;low<256;low=low+1) {
            original=low;
            if(high==1)original=original|0x0100;
            if(high==2)original=original|0x7F00;
            if(high==3)original=original|0x8000;
            if(high==4)original=original|0xFF00;
            anim=original;subpixel=0xFFFF;sp=stack_pointer();
            start=cycles();reference_update_subpixel();cost=cycles()-start;phase_c=phase_c+cost;
            expected=subpixel;anim=original;subpixel=0xFFFF;
            start=cycles();update_subpixel();cost=cycles()-start;phase_fast=phase_fast+cost;
            if(cost>phase_max)phase_max=cost;
            if(anim!=original || subpixel!=expected || !guards() || !same_stack(sp)) {
                printf("FAIL phase %u expected%u got%u anim%u guard%u spok%u\n",original,expected,subpixel,anim,guards(),same_stack(sp));return 1;
            }
            phase_count=phase_count+1;
        }
    }
    if(HAS_ROM) {
        for(slot=0;slot<48;slot=slot+1) {
            p=slot*4;
            for(center=0;center<3;center=center+1) {
                for(i=0;i<192;i=i+1)objects[i]=(u8)(i*13+slot);
                objects[p+1]=(u8)(center*127+center/2);
                objects[p+2]=(u8)(255-objects[p+1]);
                for(phase=0;phase<256;phase=phase+1) {
                    objects[p+3]=(u8)phase;
                    memcpy(original_objects,objects,192);sp=stack_pointer();
                    start=cycles();expected=reference_mace_x((u8)slot);cost=cycles()-start;mace_c=mace_c+cost;
                    start=cycles();actual=mace_x((u8)slot);cost=cycles()-start;mace_fast=mace_fast+cost;
                    if(actual!=expected) {printf("FAIL mace_x %u %u %u expected%u got%u\n",slot,center,phase,expected,actual);return 2;}
                    start=cycles();expected=reference_mace_y((u8)slot);cost=cycles()-start;mace_c=mace_c+cost;
                    start=cycles();actual=mace_y((u8)slot);cost=cycles()-start;mace_fast=mace_fast+cost;
                    if(actual!=expected || memcmp(objects,original_objects,192) || !guards() || !same_stack(sp) || anim!=0xFFFF || subpixel!=255) {
                        printf("FAIL mace_y/state %u %u %u expected%u got%u\n",slot,center,phase,expected,actual);return 3;
                    }
                    mace_count=mace_count+1;
                }
            }
        }
        for(i=0;i<256;i=i+1) {world[i]=(u8)i;reference_world[i]=(u8)i;}
        for(tile=0;tile<256;tile=tile+1) {
            world[0]=(u8)tile;reference_world[0]=(u8)tile;sp=stack_pointer();
            if(get_collision(0,0)!=reference_get_collision(0,0) || !same_stack(sp)) {printf("FAIL collision class%u\n",tile);return 4;}
            tile_count=tile_count+1;
        }
        for(x=0;x<256;x=x+1) {
            for(y=0;y<256;y=y+1) {
                sp=stack_pointer();
                if(get_tile((u8)x,(u8)y)!=reference_get_tile((u8)x,(u8)y) || !same_stack(sp)) {printf("FAIL tile %u %u\n",x,y);return 5;}
                if(get_collision((u8)x,(u8)y)!=reference_get_collision((u8)x,(u8)y) || !same_stack(sp)) {printf("FAIL tile class %u %u\n",x,y);return 6;}
                tile=x^y;
                reference_set_tile((u8)x,(u8)y,(u8)tile);set_tile((u8)x,(u8)y,(u8)tile);
                if(world[(y&240)|(x>>4)]!=reference_world[(y&240)|(x>>4)] || !guards() || !same_stack(sp)) {printf("FAIL set tile %u %u\n",x,y);return 7;}
                tile_count=tile_count+1;
            }
        }
        if(memcmp(world,reference_world,256)) {printf("FAIL world preservation\n");return 8;}
    }
    centers[0]=0;centers[1]=1;centers[2]=127;centers[3]=128;centers[4]=255;
    radii[0]=0;radii[1]=1;radii[2]=7;radii[3]=8;radii[4]=10;
    radii[5]=16;radii[6]=63;radii[7]=127;radii[8]=128;radii[9]=255;
    edges[0]=0;edges[1]=1;edges[2]=7;edges[3]=8;edges[4]=9;edges[5]=16;edges[6]=17;edges[7]=127;
    edges[8]=128;edges[9]=129;edges[10]=239;edges[11]=240;edges[12]=247;edges[13]=248;edges[14]=249;edges[15]=255;
    player_jump=0;player_die=0;
    for(axis=0;axis<2;axis=axis+1) {
        for(radius=0;radius<10;radius=radius+1) {
            for(base=0;base<5;base=base+1) {
                player_x=centers[base];player_y=(u8)(255-centers[base]);
                for(diff=0;diff<256;diff=diff+1) {
                    if(axis==0) {x=(u8)(player_x+diff);y=player_y;rx=radii[radius];ry=8;}
                    else {x=player_x;y=(u8)(player_y+diff);rx=8;ry=radii[radius];}
                    if(!collision_case((u8)x,(u8)y,(u8)rx,(u8)ry))return 9;
                    collision_count=collision_count+1;
                }
            }
        }
    }
    for(base=0;base<3;base=base+1) {
        player_x=centers[base*2];player_y=(u8)(255-player_x);
        for(rx=0;rx<10;rx=rx+1) {
            for(ry=0;ry<10;ry=ry+1) {
                for(dx=0;dx<16;dx=dx+1) {
                    for(dy=0;dy<16;dy=dy+1) {
                        if(!collision_case((u8)(player_x+edges[dx]),(u8)(player_y+edges[dy]),radii[rx],radii[ry]))return 10;
                        collision_count=collision_count+1;
                    }
                }
            }
        }
    }
    jumps[0]=0;jumps[1]=1;jumps[2]=47;jumps[3]=48;jumps[4]=49;jumps[5]=255;
    dies[0]=0;dies[1]=1;dies[2]=255;
    for(jump=0;jump<6;jump=jump+1) {
        for(die=0;die<3;die=die+1) {
            player_jump=jumps[jump];player_die=dies[die];
            for(base=0;base<5;base=base+1) {
                player_x=centers[base];player_y=(u8)(255-player_x);
                for(radius=0;radius<10;radius=radius+1) {
                    if(!collision_case(player_x,player_y,radii[radius],radii[radius]))return 11;
                    collision_count=collision_count+1;
                }
            }
        }
    }
    if(rom_fault || !guards()) {printf("FAIL ROM/canary\n");return 12;}
    printf("PASS %lu %lu %lu %lu %lu %lu %lu %lu %lu\n",phase_count,mace_count,tile_count,collision_count,phase_fast,phase_c,phase_max,mace_fast,mace_c);
    return 0;
}
'''


def check_uil(source_text, rom):
    program = author_program(HEADER + source_text)
    machine = GameMachine(program, {0: rom} if rom else {})
    counts = dict(phase=0, mace=0, tile=0, collision=0)
    for high in (0, 1, 0x7f, 0x80, 0xff):
        for low in range(256):
            value = (high << 8) | low
            machine.set_state({'anim': value, 'subpixel': 65535})
            machine.call('update_subpixel')
            s = machine.snapshot()
            if s['anim'] != value or s['subpixel'] != int(f'{low:08b}'[::-1], 2):
                raise AssertionError('typed UIL phase differs from independent bit-string reversal')
            counts['phase'] += 1
    if rom:
        for slot in (0, 23, 47):
            for center in (0, 127, 255):
                for angle in range(256):
                    objects = [(i * 13 + slot) & 255 for i in range(192)]
                    objects[slot*4+1:slot*4+4] = [center, 255-center, angle]
                    machine.set_state({'objects': objects})
                    sine = int.from_bytes(rom[0x658f8+2*angle:0x658fa+2*angle], 'big', signed=True)
                    cos = int.from_bytes(rom[0x65978+2*angle:0x6597a+2*angle], 'big', signed=True)
                    expected_x = (center + (sine >> 4)) & 255
                    neg_cos = ((-cos + 32768) & 65535) - 32768
                    expected_y = (255-center + (neg_cos >> 4)) & 255
                    if machine.call('mace_x', slot)['result'] != expected_x or machine.call('mace_y', slot)['result'] != expected_y:
                        raise AssertionError('typed UIL mace differs from independently decoded sine words')
                    if machine.snapshot()['objects'] != objects:
                        raise AssertionError('typed UIL mace query wrote objects')
                    counts['mace'] += 1
        world = list(range(256))
        machine.set_state({'world': world})
        for cell in range(256):
            x, y = (cell & 15) * 16 + 15, (cell & 240) + 15
            if machine.call('get_tile', x, y)['result'] != cell or machine.call('get_collision', x, y)['result'] != rom[0xa514+cell]:
                raise AssertionError('typed UIL tile/collision read differs from map/ROM bytes')
            machine.call('set_tile', x, y, 255-cell)
            world[cell] = 255-cell
            if machine.snapshot()['world'] != world:
                raise AssertionError('typed UIL tile write changed an unexpected byte')
            counts['tile'] += 1
    for base in (0, 127, 255):
        for radius in (0, 8, 127, 128, 255):
            for diff in range(256):
                dx = diff if diff < 128 else diff - 256
                signed_r = radius if radius < 128 else radius - 256
                expected = int(-signed_r <= dx <= signed_r)
                machine.set_state({'player_x': base, 'player_y': 255-base, 'player_jump': 0, 'player_die': 0})
                result = machine.call('collides_player', (base+diff)&255, 255-base, radius, 8)['result']
                if result != expected:
                    raise AssertionError('typed UIL collision differs from signed inclusive interval')
                counts['collision'] += 1
    for jump in (0, 1, 47, 48, 49, 255):
        for die in (0, 1, 255):
            machine.set_state({'player_x': 255, 'player_y': 0, 'player_jump': jump, 'player_die': die})
            if machine.call('collides_player', 255, 0, 8, 8)['result'] != int(jump in (0, 48) and die == 0):
                raise AssertionError('typed UIL collision jump/death guard differs')
            counts['collision'] += 1
    return counts, sha(json.dumps(program,sort_keys=True,separators=(',',':')).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc65-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--rom')
    args = parser.parse_args()
    toolchain = Path(args.cc65_root).resolve()
    out = _private_output(args.output)
    out.mkdir()
    full = ROOT / 'src/fdisbull/game_sources/miniplanets_full.c'
    actors = ROOT / 'src/fdisbull/game_sources/miniplanets_actors.c'
    assembly = ROOT / 'src/fdisbull/game_sources/nes_game_fast.s'
    captured = {path: path.read_bytes() for path in (full,actors,assembly,GAME_IL_PATH,Path(__file__))}
    if sha(captured[GAME_IL_PATH]) != GAME_IL_IMPORTED_SHA256:
        raise ValueError('interpreter source changed during module import')
    combined = captured[full].decode() + '\n' + captured[actors].decode()
    source_text = '\n'.join(extract(combined, name) for name in NAMES)
    reference = source_text
    for name in NAMES:
        reference = re.sub(r'\b' + name + r'\b', 'reference_' + name, reference)
    reference = re.sub(r'\bworld\b', 'reference_world', reference)
    rom = Path(args.rom).expanduser().read_bytes() if args.rom else b''
    if rom and (len(rom) != 524288 or sha(rom) != ROM_SHA256):
        raise ValueError('exact reviewed Miniplanets ROM required')
    sine = rom[0x658f8:0x65b88] if rom else bytes(656)
    if rom and sine[512:] != sine[:144]:
        raise ValueError('original sine periodic extension differs')
    collision = rom[0xa514:0xa614] if rom else bytes(256)
    words = [int.from_bytes(sine[i:i+2], 'big') for i in range(0, 512, 2)]
    data = (array('native_sine_lo', [v & 255 for v in words]) +
            array('native_sine_hi', [v >> 8 for v in words]) +
            array('native_collision', collision) + array('source_sine', sine))
    harness = HARNESS.replace('DATA', data).replace('REFERENCE', reference).replace('HAS_ROM', str(int(bool(rom))))
    (out / 'harness.c').write_text(harness)
    (out / 'fast.s').write_bytes(captured[assembly])
    (out / 'probe.s').write_text('.export _stack_pointer, _same_stack, _banked_call\n.importzp c_sp\n.segment "CODE"\n_stack_pointer:\n lda c_sp\n ldx c_sp+1\n rts\n_same_stack:\n cmp c_sp\n bne no\n cpx c_sp+1\n bne no\n lda #1\n ldx #0\n rts\nno:\n lda #0\n ldx #0\n rts\n_banked_call:\n brk ; fail closed if an actor accidentally executes in the primitive suite\n')
    cfg = (toolchain / 'cfg/sim6502.cfg').read_text().replace('    RODATA:', '    GAMEFAST: load = MAIN, type = ro;\n    RODATA:')
    (out / 'sim.cfg').write_text(cfg)
    command = [str(toolchain / 'bin/cl65'), '-t', 'sim6502', '-Oirs', '--static-locals', '-C', str(out / 'sim.cfg'), '-o', str(out / 'check'), str(out / 'harness.c'), str(out / 'fast.s'), str(out / 'probe.s')]
    build = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'build.txt').write_text(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError(build.stderr[-3000:])
    run = subprocess.run([str(toolchain / 'bin/sim65'), '-c', str(out / 'check')], capture_output=True, text=True, timeout=180)
    (out / 'run.txt').write_text(run.stdout + run.stderr)
    found = re.search(r'PASS ' + ' '.join([r'(\d+)'] * 9), run.stdout)
    if run.returncode or found is None:
        raise AssertionError(run.stdout + run.stderr)
    phase, mace, tile, coll, phase_fast, phase_c, phase_max, mace_fast, mace_c = map(int, found.groups())
    counts, program_sha = check_uil(source_text, rom)
    if any(path.read_bytes()!=raw for path,raw in captured.items()):
        raise ValueError('source or verifier changed during qualification')
    report = {
        'format': 'miniplanets-game-intrinsic-sim6502-2', 'status': 'passed',
        'native_cases': {'phase': phase, 'mace_coordinate_pairs': mace, 'tile_read_class_write': tile, 'collision': coll},
        'typed_uil_cases': counts, 'rom_sha256': sha(rom) if rom else None,
        'typed_uil_program_sha256': program_sha,
        'interpreter_sha256': GAME_IL_IMPORTED_SHA256, 'inputs_unchanged': True,
        'private_tables': {'sine': {'offset': 0x658f8, 'length': len(sine), 'sha256': sha(sine)}, 'collision': {'offset': 0xa514, 'length': len(collision), 'sha256': sha(collision)}} if rom else None,
        'game_state_writes': 'Phase writes Subpixel only; SetTile writes the indexed world byte only. Mace/tile/collision queries preserve game state. Software-stack pointer and adjacent canaries checked.',
        'asm_sha256': sha(captured[assembly]),
        'sources': {p.name: sha(captured[p]) for p in (full, actors)},
        'verifier_sha256': sha(captured[Path(__file__)]), 'native_check_sha256': sha((out / 'check').read_bytes()),
        'toolchain': {name: sha((toolchain / 'bin' / name).read_bytes()) for name in ('cl65', 'cc65', 'ca65', 'ld65', 'sim65')},
        'phase': {'asm_cycles_total': phase_fast, 'c_cycles_total': phase_c, 'asm_cycles_mean': phase_fast / phase, 'c_cycles_mean': phase_c / phase, 'asm_cycles_max': phase_max},
        'mace': {'asm_cycles_total': mace_fast, 'c_cycles_total': mace_c, 'asm_cycles_mean_per_coordinate': mace_fast / (mace*2), 'c_cycles_mean_per_coordinate': mace_c / (mace*2)} if mace else None,
        'cycle_scope': 'Includes identical sim65 counter-call measurement overhead; no mapper thunk. Not NES frame-rate evidence.',
        'limit': 'Finite actual sim6502/C/UIL arithmetic/ABI vectors, not exhaustive global-game proof. Final banked NES integration and timing are separate gates.'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
