#!/usr/bin/env python3
"""Compare native NES sprite emission against the original C routine on sim65."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HARNESS=r'''
#include <stdio.h>
#include <string.h>
#include <sim65.h>
typedef unsigned char u8;
typedef unsigned int u16;
u8 display_plane[256],display_palettes[256],projection_cache[256],world[256];
u8 display_hud[24],display_attributes[16],lives,time_secs,stage_name,keys_left;
u8 render_oam_page,render_oam_index,oam_overflow,globe_source_hi,globe_rowbase,globe_colbase;
u16 globe_atlas_pointer;unsigned long score;
u8 objects[192],player_x,player_y,player_jump,player_die;u16 render_epoch,anim;
u8 mace_x(u8 slot){return slot;} u8 mace_y(u8 slot){return slot;}
u16 object_projection_pair(u8 x,u8 y,u8 raft){return x+y+raft;}
void banked_call(void){}

const u8 tile_palette[35]={0};
void draw_sprite(u8 x,u8 y,u8 tile,u8 palette);
u16 read_stack(void);
static u8 expected[512];
static u16 seed=0x916d;
static u8 next(void){seed^=seed<<7;seed^=seed>>9;seed^=seed<<8;return (u8)seed;}
static unsigned long cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
static void reference(u8 x,u8 y,u8 tile,u8 palette){
 volatile u8 *oam;
 if(render_oam_index>=252){oam_overflow=1;return;}
 oam=(volatile u8*)((u16)render_oam_page<<8);
 oam[render_oam_index]=y-1;oam[render_oam_index+1]=tile;
 oam[render_oam_index+2]=palette & 3;oam[render_oam_index+3]=x;
 render_oam_index=render_oam_index+4;
}
int main(void){
 u16 c,i,sp_before;u8 x,y,t,p,page,index,overflow,expected_index,expected_overflow;
 unsigned long rc=0,fc=0,start;
 for(c=0;c<16384;c++){
  page=2+((c>>8)&1);index=(u8)c;overflow=next();x=next();y=next();t=next();p=next();
  for(i=0;i<512;i++)((u8*)0x200)[i]=next();
  memcpy(expected,(void*)0x200,512);
  render_oam_page=page;render_oam_index=index;oam_overflow=overflow;
  start=cycles();reference(x,y,t,p);rc+=cycles()-start;
  expected_index=render_oam_index;expected_overflow=oam_overflow;
  for(i=0;i<512;i++){u8 v=((u8*)0x200)[i];((u8*)0x200)[i]=expected[i];expected[i]=v;}
  render_oam_index=index;oam_overflow=overflow;sp_before=read_stack();
  start=cycles();draw_sprite(x,y,t,p);fc+=cycles()-start;
  if(read_stack()!=sp_before||render_oam_index!=expected_index||oam_overflow!=expected_overflow||memcmp(expected,(void*)0x200,512)){
   printf("FAIL %u index %u page %u\n",c,index,page);return 1;
  }
 }
 printf("PASS 16384 %lu %lu\n",rc,fc);return 0;
}
'''
STUB='''.setcpu "6502"\n.importzp sp\n.export _read_stack\n.segment "CODE"\n_read_stack:\n lda sp\n ldx sp+1\n rts\n'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc65-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 out=a.output.resolve();cc=a.cc65_root.resolve();src=Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources/nes_globe_fast.s';data=src.read_bytes()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh output outside Git')
 out.mkdir(parents=True)
 cfg=(cc/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
 (out/'sim.cfg').write_text(cfg);(out/'harness.c').write_text(HARNESS);(out/'stub.s').write_text(STUB);(out/src.name).write_bytes(data)
 build=subprocess.run([str(cc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/src.name),str(out/'stub.s'),str(out/'harness.c')],capture_output=True,text=True,timeout=60)
 (out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 run=subprocess.run([str(cc/'bin/sim65'),'-c',str(out/'check')],capture_output=True,text=True,timeout=120);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode or not run.stdout.startswith('PASS 16384 '):raise RuntimeError(run.stdout+run.stderr)
 if src.read_bytes()!=data:raise RuntimeError('source changed during check')
 row=run.stdout.splitlines()[0].split();digest=lambda b:hashlib.sha256(b).hexdigest()
 receipt={'passed':True,'cases':16384,'source_sha256':digest(data),'harness_sha256':digest(HARNESS.encode()),'program_sha256':digest((out/'check').read_bytes()),'reference_mean_cycles':int(row[2])/16384,'native_mean_cycles':int(row[3])/16384,'coverage':'all index bytes, both OAM pages, random complete OAM contents and arguments, overflow flag, stack balance, and all 512 bytes','limits':'sim65 procedure boundary; full cartridge scheduling and integration are separate'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
