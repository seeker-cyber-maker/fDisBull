#!/usr/bin/env python3
"""Compare baseline and candidate object drawing with identical seeded inputs.

Uses the actual draw_objects bodies compiled on the host, deterministic synthetic
projection values, and complete 256-byte OAM comparison. The mapped NES helper
and NES execution remain separate qualification gates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src/fdisbull/game_sources/nes_globe_renderer.c'

PREAMBLE = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8; typedef int8_t i8; typedef uint16_t u16;
static u8 objects[192],player_x,player_y,player_jump,player_die;
static u8 render_oam_index,oam_overflow,oam[256]; static u16 render_epoch;
static u8 component(u8 x,u8 y,u8 raft) {
    return (u8)((x*29u+y*113u+(unsigned)raft*71u)^((x*y)>>3));
}
static i8 object_projection(u8 x,u8 y,u8 raft){return (i8)component(x,y,raft);}
static u16 object_projection_pair(u8 x,u8 y,u8 raft){
    return (u16)(component(x,y,raft)|((u16)component(y,x,raft)<<8));
}
static u8 mace_x(u8 slot){return (u8)(objects[slot*4+1]+objects[slot*4+3]);}
static u8 mace_y(u8 slot){return (u8)(objects[slot*4+2]-objects[slot*4+3]);}
static void draw_sprite(u8 x,u8 y,u8 tile,u8 palette){
    if(render_oam_index>=252){oam_overflow=1;return;}
    oam[render_oam_index]=y-1;oam[render_oam_index+1]=tile;
    oam[render_oam_index+2]=palette&3;oam[render_oam_index+3]=x;
    render_oam_index+=4;
}
'''
MAIN = r'''
static uint32_t rng=0x71c9406du;
static u8 next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (u8)rng;}
int main(void){
    unsigned c,i; u8 expected[256],expected_index,expected_overflow;
    for(c=0;c<100000;c++){
        player_x=next();player_y=next();player_jump=next();player_die=next()&1;
        render_epoch=(u16)((next()<<8)|next());
        for(i=0;i<48;i++){
            objects[4*i]=next()%32;
            /* Include both hemisphere boundaries and wrapped positions. */
            objects[4*i+1]=(u8)(player_x+(i8)((int)(next()%145)-72));
            objects[4*i+2]=(u8)(player_y+(i8)((int)(next()%145)-72));
            objects[4*i+3]=next();
        }
        memset(oam,255,sizeof(oam));render_oam_index=0;oam_overflow=0;
        baseline_draw_objects();memcpy(expected,oam,sizeof(oam));
        expected_index=render_oam_index;expected_overflow=oam_overflow;
        memset(oam,255,sizeof(oam));render_oam_index=0;oam_overflow=0;
        candidate_draw_objects();
        if(memcmp(expected,oam,sizeof(oam))||expected_index!=render_oam_index||expected_overflow!=oam_overflow){
            printf("mismatch case %u\n",c);return 1;
        }
    }
    printf("PASS 100000\n");return 0;
}
'''

def body(text, name):
    start = text.index('void draw_objects(void) {')
    end = text.index('\nvoid draw_menu(void)', start)
    return text[start:end].replace('void draw_objects(void)', f'void {name}(void)', 1)

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        raise ValueError('choose a fresh output outside Git')
    baseline = args.baseline.resolve().read_bytes(); candidate = CANDIDATE.read_bytes()
    source = PREAMBLE + body(baseline.decode(), 'baseline_draw_objects') + '\n' + body(candidate.decode(), 'candidate_draw_objects') + MAIN
    output.mkdir(parents=True)
    (output / 'harness.c').write_text(source)
    build = subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-o', str(output/'check'), str(output/'harness.c')], capture_output=True, text=True)
    (output/'build.txt').write_text(build.stdout+build.stderr)
    if build.returncode: raise RuntimeError(build.stderr)
    run = subprocess.run([str(output/'check')], capture_output=True, text=True)
    (output/'run.txt').write_text(run.stdout+run.stderr)
    if run.returncode or run.stdout.strip() != 'PASS 100000': raise RuntimeError(run.stdout+run.stderr)
    if CANDIDATE.read_bytes()!=candidate or args.baseline.resolve().read_bytes()!=baseline: raise RuntimeError('source changed during check')
    report={'passed':True,'cases':100000,'baseline_sha256':sha(baseline),'candidate_sha256':sha(candidate),
        'harness_sha256':sha(source.encode()),'check_sha256':sha((output/'check').read_bytes()),
        'compared':'complete OAM bytes, next OAM index, overflow flag',
        'scope':'actual C draw_objects bodies with deterministic synthetic projection and mace functions on host; native helper, mapper, terrain and full cartridge require separate checks'}
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__': main()
