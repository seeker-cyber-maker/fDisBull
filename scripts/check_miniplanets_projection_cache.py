#!/usr/bin/env python3
"""Compare baseline and cached terrain calls over camera/mode sequences.

Actual draw_terrain C bodies run on the host with deterministic synthetic
immutable projection and terrain data. Native NES behavior is a separate gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src/fdisbull/game_sources/nes_globe_renderer.c'
PREAMBLE = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8; typedef uint16_t u16;
static u8 player_x,player_y,anim,projection_cache[256],display_plane[256],display_palettes[256];
static u8 upload_terrain_cached,upload_terrain_valid;
static u8 projection_cache_valid,projection_cache_phase,globe_source_hi,globe_rowbase,globe_colbase,selected;
static u16 globe_atlas_pointer; static unsigned copies;
static u8 projection_bank(u8 phase){return phase>>5;}
static void select_data(u8 bank){selected=bank;}
static u16 terrain_pointer(u8 phase){return (u16)(0xa000+phase*36u);}
static void globe_copy_projection(void){
    unsigned i;u8 phase=(u8)((selected<<5)|(globe_source_hi-0xa0));copies++;
    for(i=0;i<256;i++)projection_cache[i]=(u8)(phase*73u+i*47u+(phase^i));
}
static u8 globe_restore_terrain(void){return 0;}
static void globe_clear_planes(void){memset(display_plane,0,256);memset(display_palettes,0,256);}
static void globe_clear_terrain(void){globe_clear_planes();}
static void globe_save_terrain(void){}
static void globe_paint_terrain(void){
    unsigned i;for(i=0;i<256;i++){
        display_plane[i]=(u8)(projection_cache[i]+globe_rowbase+globe_colbase+globe_atlas_pointer);
        display_palettes[i]=(u8)((projection_cache[255-i]+(globe_atlas_pointer>>8))&3);
    }
}
'''
MAIN = r'''
typedef struct {u8 cache[256],plane[256],palettes[256],source,row,col,bank,valid,phase;u16 atlas;unsigned copies;} State;
static State baseline,candidate;
static void restore(State *s){
    memcpy(projection_cache,s->cache,256);memcpy(display_plane,s->plane,256);memcpy(display_palettes,s->palettes,256);
    globe_source_hi=s->source;globe_rowbase=s->row;globe_colbase=s->col;selected=s->bank;
    projection_cache_valid=s->valid;projection_cache_phase=s->phase;globe_atlas_pointer=s->atlas;copies=s->copies;
}
static void capture(State *s){
    memcpy(s->cache,projection_cache,256);memcpy(s->plane,display_plane,256);memcpy(s->palettes,display_palettes,256);
    s->source=globe_source_hi;s->row=globe_rowbase;s->col=globe_colbase;s->bank=selected;
    s->valid=projection_cache_valid;s->phase=projection_cache_phase;s->atlas=globe_atlas_pointer;s->copies=copies;
}
static uint32_t rng=0x91abc663u;
static u8 next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (u8)rng;}
int main(void){
    unsigned n,i,draws=0;u8 mode,phase=0;
    for(n=0;n<100000;n++){
        /* First 256 draws cover every phase, including zero after reset. Later
           repeated phases, mode/ending gaps and phase changes are interleaved. */
        if(n<256){mode=1;phase=(u8)n;}else{
            mode=next()%5;
            if((next()&3)==0)phase=next();
        }
        player_x=(u8)((next()&0xf0)|(phase&15));
        player_y=(u8)((next()&0xf0)|(phase>>4));anim=next();
        /* Other modes and the ending do not write the projection cache. */
        if(mode==1){
            for(i=0;i<256;i++){baseline.plane[i]=candidate.plane[i]=0;baseline.palettes[i]=candidate.palettes[i]=0;}
            restore(&baseline);baseline_draw_terrain();capture(&baseline);
            restore(&candidate);candidate_draw_terrain();capture(&candidate);draws++;
        }
        if(memcmp(baseline.cache,candidate.cache,256)||memcmp(baseline.plane,candidate.plane,256)||
           memcmp(baseline.palettes,candidate.palettes,256)||baseline.source!=candidate.source||
           baseline.row!=candidate.row||baseline.col!=candidate.col||baseline.bank!=candidate.bank||baseline.atlas!=candidate.atlas){
            printf("mismatch step %u\n",n);return 1;
        }
    }
    if(baseline.copies!=draws||candidate.copies>=draws){printf("copy coverage failure\n");return 2;}
    printf("PASS steps=100000 draws=%u baseline_copies=%u candidate_copies=%u\n",draws,baseline.copies,candidate.copies);
    return 0;
}
'''

def body(text, name):
    start=text.index('void draw_terrain(void) {')
    end=text.index('\nvoid draw_ending_planet(void)',start)
    return text[start:end].replace('void draw_terrain(void)',f'void {name}(void)',1)

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a fresh output outside Git')
    baseline=args.baseline.resolve().read_bytes();candidate=CANDIDATE.read_bytes()
    source=PREAMBLE+body(baseline.decode(),'baseline_draw_terrain')+'\n'+body(candidate.decode(),'candidate_draw_terrain')+MAIN
    output.mkdir(parents=True);(output/'harness.c').write_text(source)
    build=subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-o',str(output/'check'),str(output/'harness.c')],capture_output=True,text=True)
    (output/'build.txt').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError(build.stderr)
    run=subprocess.run([str(output/'check')],capture_output=True,text=True)
    (output/'run.txt').write_text(run.stdout+run.stderr)
    if run.returncode or not run.stdout.startswith('PASS steps=100000 '):raise RuntimeError(run.stdout+run.stderr)
    if CANDIDATE.read_bytes()!=candidate or args.baseline.resolve().read_bytes()!=baseline:raise RuntimeError('source changed during check')
    report={'passed':True,'result':run.stdout.strip(),'baseline_sha256':sha(baseline),'candidate_sha256':sha(candidate),
            'harness_sha256':sha(source.encode()),'check_sha256':sha((output/'check').read_bytes()),
            'compared':'projection cache, full plane and palette, data bank, source page, atlas pointer and row/column after each step',
            'scope':'actual C draw_terrain bodies on host with synthetic immutable data and forced terrain-cache misses; mode gaps leave projection cache unchanged; actual NES mapper/IRQ/full cartridge require separate checks'}
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
