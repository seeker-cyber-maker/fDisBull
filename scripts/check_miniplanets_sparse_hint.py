#!/usr/bin/env python3
"""Exercise the real draw_game sparse-hint decision with controlled collaborators."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
PRE=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t u16;
static u8 video_ready,upload_terrain_cached,upload_terrain_sparse,upload_terrain_overlay;
static u8 render_oam_page,render_oam_index,oam_overflow,mode,ending_phase,ingame_status,render_phase;
static u16 render_epoch,epoch_stub;
static u8 hit,captured_sparse,captured_overlay,captured_cached;
static unsigned prepare_count,terrain_count,ending_count,menu_count,pause_count;
static void globe_clear_oam(void){}
static void globe_clear_planes(void){}
static void draw_terrain(void){terrain_count++;upload_terrain_cached=hit;}
static void draw_ending_planet(void){ending_count++;}
static void draw_objects(void){}
static void put_text(u8 x,u8 y,const char *p){(void)x;(void)y;(void)p;pause_count++;}
static void draw_menu(void){menu_count++;}
static void globe_hud_attributes(void){}
static void prepare_upload(void){prepare_count++;captured_sparse=upload_terrain_sparse;captured_overlay=upload_terrain_overlay;captured_cached=upload_terrain_cached;}
'''
POST=r'''
static uint32_t state=0x57a2b9cu;
static u8 next(void){state^=state<<13;state^=state>>17;state^=state<<5;return (u8)state;}
int main(void){
 unsigned n,paused=0,unpaused_hit=0,unpaused_miss=0,menus=0,endings=0,pending=0;u8 ready,sparse,cached,overlay,expected;
 for(n=0;n<100000;n++){
  mode=next()%10;ending_phase=next()%5;ingame_status=next();hit=next()&1;
  ready=(next()&3)==0;video_ready=ready;sparse=next();cached=next();overlay=next();
  upload_terrain_sparse=sparse;upload_terrain_cached=cached;upload_terrain_overlay=overlay;
  prepare_count=terrain_count=ending_count=menu_count=pause_count=0;draw_game();
  if(ready){pending++;if(prepare_count||terrain_count||ending_count||menu_count||pause_count||upload_terrain_sparse!=sparse||upload_terrain_cached!=cached||upload_terrain_overlay!=overlay){printf("FAIL pending %u\n",n);return 1;}continue;}
  expected=(mode==1 && ending_phase!=3 && !(ingame_status&1));
  if(mode==1 && (ingame_status&1))paused++;
  if(expected && hit)unpaused_hit++;
  if(expected && !hit)unpaused_miss++;
  if(mode!=1)menus++;
  if(mode==1 && ending_phase==3)endings++;
  if(prepare_count!=1||video_ready!=1||captured_sparse!=expected||upload_terrain_sparse!=expected||captured_overlay!=(ingame_status&1)||captured_cached!=((mode==1 && ending_phase!=3)?hit:0)||terrain_count!=(unsigned)(mode==1&&ending_phase!=3)||ending_count!=(unsigned)(mode==1&&ending_phase==3)||menu_count!=(unsigned)(mode!=1)||pause_count!=(unsigned)(mode==1&&(ingame_status&1))){
   printf("FAIL %u mode%u end%u pause%u hit%u sparse%u/%u\n",n,mode,ending_phase,ingame_status&1,hit,captured_sparse,expected);return 2;
  }
 }
 if(!paused||!unpaused_hit||!unpaused_miss||!menus||!endings||!pending){puts("MISSING COVERAGE");return 3;}
 printf("PASS 100000 paused=%u hit=%u miss=%u menus=%u endings=%u pending=%u\n",paused,unpaused_hit,unpaused_miss,menus,endings,pending);return 0;
}
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh output outside Git')
 src=Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources/nes_globe_renderer.c';data=src.read_bytes();s=data.decode();start=s.index('void draw_game(void) {');body=s[start:].replace('render_epoch=*(volatile u16*)0x7D2;', 'render_epoch=epoch_stub;');harness=PRE+body+POST
 out.mkdir(parents=True);(out/'harness.c').write_text(harness)
 b=subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-o',str(out/'check'),str(out/'harness.c')],capture_output=True,text=True);(out/'build.txt').write_text(b.stdout+b.stderr)
 if b.returncode:raise RuntimeError(b.stderr)
 r=subprocess.run([str(out/'check')],capture_output=True,text=True);(out/'run.txt').write_text(r.stdout+r.stderr)
 if r.returncode or not r.stdout.startswith('PASS 100000 '):raise RuntimeError(r.stdout+r.stderr)
 if src.read_bytes()!=data:raise RuntimeError('source changed during check')
 sha=lambda b:hashlib.sha256(b).hexdigest();result={'passed':True,'cases':100000,'renderer_sha256':sha(data),'harness_sha256':sha(harness.encode()),'program_sha256':sha((out/'check').read_bytes()),'result':r.stdout.strip(),'coverage':'actual draw_game sparse, cached and pause hints at planner call; terrain, ending, menu, pause, cache-hit/miss and pending ownership','limits':'host with controlled collaborators and native epoch memory read replaced by a local value; native plane contents and planner remain separate checks'}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
