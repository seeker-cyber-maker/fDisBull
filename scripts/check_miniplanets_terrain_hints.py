#!/usr/bin/env python3
"""Check terrain producer hints against the actual draw_terrain C body."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PRE=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t u16;
static u8 player_x,player_y,projection_cache_valid,projection_cache_phase;
static u16 anim,globe_atlas_pointer;
static u8 globe_source_hi,globe_rowbase,globe_colbase;
static u8 upload_terrain_cached,upload_terrain_valid,hit;
static unsigned clear_count,paint_count,save_count;
static u8 projection_bank(u8 p){return p>>5;}
static void select_data(u8 p){(void)p;}
static void globe_copy_projection(void){}
static u16 terrain_pointer(u8 p){return p;}
static u8 globe_restore_terrain(void){return hit;}
static void globe_clear_terrain(void){clear_count++;}
static void globe_paint_terrain(void){paint_count++;}
static void globe_save_terrain(void){save_count++;}
'''
POST=r'''
static uint32_t state=0x91ab325u;
static u8 next(void){state^=state<<13;state^=state>>17;state^=state<<5;return (u8)state;}
int main(void){
 unsigned n;u8 before;
 for(n=0;n<100000;n++){
  player_x=next();player_y=next();anim=next();hit=next()&1;
  before=next();upload_terrain_valid=before;upload_terrain_cached=0x55;
  clear_count=paint_count=save_count=0;
  draw_terrain();
  if(upload_terrain_cached!=hit || upload_terrain_valid!=(hit?before:0) ||
     clear_count!=(unsigned)!hit || paint_count!=(unsigned)!hit || save_count!=(unsigned)!hit){
   printf("FAIL %u hit=%u cached=%u valid=%u calls=%u/%u/%u\n",n,hit,upload_terrain_cached,upload_terrain_valid,clear_count,paint_count,save_count);return 1;
  }
 }
 puts("PASS 100000");return 0;
}
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 root=Path(__file__).resolve().parents[1];src=root/'src/fdisbull/game_sources/nes_globe_renderer.c';data=src.read_bytes();text=data.decode();start=text.index('void draw_terrain(void) {');end=text.index('\nvoid draw_ending_planet(void)',start);harness=PRE+text[start:end]+POST
 out.mkdir(parents=True);(out/'harness.c').write_text(harness)
 build=subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-o',str(out/'check'),str(out/'harness.c')],capture_output=True,text=True);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 run=subprocess.run([str(out/'check')],capture_output=True,text=True);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode or run.stdout.strip()!='PASS 100000':raise RuntimeError(run.stdout+run.stderr)
 if src.read_bytes()!=data:raise RuntimeError('renderer changed during check')
 sha=lambda b:hashlib.sha256(b).hexdigest();receipt={'passed':True,'cases':100000,'renderer_sha256':sha(data),'harness_sha256':sha(harness.encode()),'program_sha256':sha((out/'check').read_bytes()),'coverage':'cache hit preserves terrain valid bits and skips clear/paint/save; miss clears both validity bits and performs all three operations','limits':'host C producer seam with stubbed restore; real cache correctness, draw_game overlay, planner, mapper and NMI need separate checks'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
