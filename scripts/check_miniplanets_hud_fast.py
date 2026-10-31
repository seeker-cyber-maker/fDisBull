#!/usr/bin/env python3
"""Compare native 6502 HUD/attribute output against the original C expressions."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sim65.h>
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 display_plane[256],display_palettes[256],projection_cache[256],world[256];
u8 display_hud[24],display_attributes[16],lives,time_secs,stage_name,keys_left;
u8 render_oam_page,render_oam_index,oam_overflow,globe_source_hi,globe_rowbase,globe_colbase;
u16 globe_atlas_pointer;
u32 score;
u8 objects[192],player_x,player_y,player_jump,player_die;u16 render_epoch;
u8 mace_x(u8 slot){return slot;} u8 mace_y(u8 slot){return slot;}
u16 object_projection_pair(u8 x,u8 y,u8 raft){return x+y+raft;}
void banked_call(void){}

const u8 tile_palette[35]={0};
void globe_hud_attributes(void);
struct Input {u8 palettes[256],scorebytes[4],lives,time,stage,keys;};
static struct Input input;
static u8 expected_hud[24],expected_attributes[16];
static unsigned long cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
static void reference(void){
 u16 i;u8 x,y,at,value;
 for(i=0;i<24;i=i+1)expected_hud[i]=32;
 for(i=0;i<6;i=i+1)expected_hud[i]=(u8)((score >> ((5-i)*4)) & 15)+48;
 expected_hud[7]=76;expected_hud[8]=(lives>>4)+48;expected_hud[9]=(lives & 15)+48;
 expected_hud[11]=84;expected_hud[12]=(time_secs>>4)+48;expected_hud[13]=(time_secs & 15)+48;
 expected_hud[15]=(stage_name>>4)+48;expected_hud[16]=45;expected_hud[17]=(stage_name & 15)+48;
 expected_hud[19]=75;expected_hud[20]=keys_left+48;
 for(y=0;y<4;y=y+1)for(x=0;x<4;x=x+1){
  at=y*64+x*4;value=display_palettes[at+17];
  value=value | (display_palettes[at+19]<<2);
  value=value | (display_palettes[at+49]<<4);
  value=value | (display_palettes[at+51]<<6);
  expected_attributes[y*4+x]=value;
 }
}
int main(void){
 int n;u16 count=0,block=0;unsigned long start,rc=0,fc=0,r,f;
 while((n=read(0,&input,sizeof(input)))!=0){
  if(n!=sizeof(input))return 2;
  memcpy(display_palettes,input.palettes,256);memcpy(&score,input.scorebytes,4);
  lives=input.lives;time_secs=input.time;stage_name=input.stage;keys_left=input.keys;
  start=cycles();reference();r=cycles()-start;
  start=cycles();globe_hud_attributes();f=cycles()-start;
  if(memcmp(expected_hud,display_hud,24)||memcmp(expected_attributes,display_attributes,16)||memcmp(input.palettes,display_palettes,256)){
   printf("MISMATCH %u\n",count);return 1;
  }
  rc+=r;fc+=f;count++;block++;
  if(block==256){printf("BLOCK %u %lu %lu\n",block,rc,fc);block=0;rc=fc=0;}
 }
 if(block)printf("BLOCK %u %lu %lu\n",block,rc,fc);
 printf("PASS %u\n",count);return 0;
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc65-root',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    assembly=root/'src/fdisbull/game_sources/nes_globe_fast.s'
    renderer=root/'src/fdisbull/game_sources/nes_globe_renderer.c'
    toolchain=Path(args.cc65_root).resolve()
    out=Path(args.output).resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):
        raise ValueError('choose a fresh output outside Git')
    out.mkdir(parents=True)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (assembly,renderer)}
    rng=random.Random(0x6502)
    fixtures=bytearray()
    for case in range(4096):
        palette=bytes(rng.randrange(256 if case&1 else 4) for _ in range(256))
        fields=bytes(rng.randrange(256) for _ in range(8))
        fixtures.extend(palette+fields)
    (out/'cases.bin').write_bytes(fixtures)
    config=(toolchain/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
    (out/'sim.cfg').write_text(config)
    (out/'harness.c').write_text(HARNESS)
    (out/assembly.name).write_bytes(assembly.read_bytes())
    build=subprocess.run([str(toolchain/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/assembly.name),str(out/'harness.c')],capture_output=True,text=True,timeout=60)
    (out/'build.txt').write_text(build.stdout+build.stderr)
    if build.returncode: raise RuntimeError(build.stderr)
    run=subprocess.run([str(toolchain/'bin/sim65'),'-c',str(out/'check')],input=fixtures,capture_output=True,timeout=300)
    output=run.stdout.decode()+run.stderr.decode()
    (out/'run.txt').write_text(output)
    if run.returncode or 'PASS 4096' not in output: raise RuntimeError(output)
    rows=[list(map(int,line.split()[1:])) for line in output.splitlines() if line.startswith('BLOCK ')]
    if sum(r[0] for r in rows)!=4096: raise RuntimeError('incomplete case count')
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[p.name] for p in (assembly,renderer)): raise RuntimeError('sources changed during check')
    receipt={'passed':True,'cases':4096,'source_hashes':hashes,'harness_sha256':hashlib.sha256(HARNESS.encode()).hexdigest(),'fixture_sha256':hashlib.sha256(fixtures).hexdigest(),'program_sha256':hashlib.sha256((out/'check').read_bytes()).hexdigest(),'c_mean_cycles':sum(r[1] for r in rows)/4096,'native_mean_cycles':sum(r[2] for r in rows)/4096,'scope':'sim65 procedure comparison; full NES integration separately required'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__': main()
