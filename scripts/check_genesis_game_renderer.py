#!/usr/bin/env python3
"""Compare Genesis staging C with the existing NES C presentation reference.

The host test uses the checked private original-derived assets. It does not
execute a 68000, a VDP or a complete game. Outputs and derived assets are private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from fdisbull.udl_miniplanets_full import checked_rom,globe_assets

HARNESS=r'''
#include "game_api.h"
#include <stdio.h>
#include <string.h>
extern const u8 genesis_projection[],genesis_terrain[],genesis_object_projection[],genesis_raft_projection[],genesis_ending_projection[],genesis_ending_ids[],genesis_tile_palette[];
extern const u8 genesis_test_maps[14080];
extern u8 genesis_plane[256],genesis_palettes[256],genesis_hud[24],genesis_sprites[252],genesis_sprite_count,genesis_sprite_overflow;
void genesis_render_stage(void);
u8 player_x,player_y,player_jump,player_die,world[256],objects[192];
u8 keys_left,stage_name,lives,time_secs,time_setting,life_setting,ingame_status,ending_phase,ending_timer,sound_test;
u8 mode,title_option,title_show_menu,option_selected,continue_option,password_dial,credits_text[48];
u16 anim;u32 score,stage_bonus,entered_password;volatile u16 genesis_render_epoch;
u8 mace_x(u8 slot){return (u8)(objects[slot*4+1]+objects[slot*4+3]);}
u8 mace_y(u8 slot){return (u8)(objects[slot*4+2]-objects[slot*4+3]);}
static u8 display_plane[256],display_palettes[256],ref_hud[24],ref_sprites[252],render_oam_index,oam_overflow;
#define render_epoch genesis_render_epoch
static u8 ending_ids_value(u8 i){return genesis_ending_ids[i];}
static u8 ending_projection(u16 i){return genesis_ending_projection[i];}
u16 object_projection_pair(u8 x,u8 y,u8 raft){
 const u8 *p=raft?genesis_raft_projection:genesis_object_projection;
 return (u16)(p[(u32)x*256+y] | ((u16)p[(u32)y*256+x]<<8));
}
static void draw_sprite(u8 x,u8 y,u8 tile,u8 palette){
 if(render_oam_index>=252){oam_overflow=1;return;}
 ref_sprites[render_oam_index]=x;ref_sprites[render_oam_index+1]=y;
 ref_sprites[render_oam_index+2]=tile;ref_sprites[render_oam_index+3]=palette&3;
 render_oam_index+=4;
}
static void put_text(u8 x,u8 y,const char *p){u8 at=y*16+x;while(*p && x<16){display_plane[at]=(u8)*p;display_palettes[at]=0;p++;at++;x++;}}
static void hex_digit(u8 x,u8 y,u8 d){display_plane[y*16+x]=(d&15)+48;}
static void ref_terrain(void){
 u8 phase=(u8)((player_y<<4)|(player_x&15)),p,o,t,shape,pal;u16 i;u32 ix,at;
 for(i=0;i<64;i++){
  ix=(u32)phase*256+(u16)(63-i)*4;p=genesis_projection[ix];o=genesis_projection[ix+1];shape=genesis_projection[ix+2];
  t=world[(u8)(((o+(player_y&240))&240)|((o+(player_x>>4))&15))];if(t>=35)t=0;
  at=(u32)(anim&31)*1260+(u16)t*36+shape;pal=genesis_tile_palette[t];
  display_plane[p]=genesis_terrain[at];display_plane[p+1]=genesis_terrain[at+1];display_plane[p+16]=genesis_terrain[at+2];display_plane[p+17]=genesis_terrain[at+3];
  display_palettes[p]=pal;display_palettes[p+1]=pal;display_palettes[p+16]=pal;display_palettes[p+17]=pal;
 }
}
'''
MAIN=r'''
static u8 world_before[256],objects_before[192];
static unsigned int seed=0x47aef6d1u;
static u8 next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return (u8)seed;}
static void reference(void){u16 i;
 memset(display_plane,0,256);memset(display_palettes,0,256);memset(ref_sprites,255,252);render_oam_index=oam_overflow=0;
 if(mode==1){if(ending_phase==3)ref_ending();else ref_terrain();ref_objects();if(ingame_status&1)put_text(5,0,"PAUSED");}else ref_menu();
 for(i=0;i<24;i++)ref_hud[i]=32;
 for(i=0;i<6;i++)ref_hud[i]=(u8)((score>>((5-i)*4))&15)+48;
 ref_hud[7]=76;ref_hud[8]=(lives>>4)+48;ref_hud[9]=(lives&15)+48;
 ref_hud[11]=84;ref_hud[12]=(time_secs>>4)+48;ref_hud[13]=(time_secs&15)+48;
 ref_hud[15]=(stage_name>>4)+48;ref_hud[16]=45;ref_hud[17]=(stage_name&15)+48;
 ref_hud[19]=75;ref_hud[20]=keys_left+48;
}
int main(void){unsigned c,i;
 for(c=0;c<50000;c++){
  player_x=next();player_y=next();player_jump=next();player_die=next();anim=(u16)(next()|((u16)next()<<8));genesis_render_epoch=(u16)(next()|((u16)next()<<8));
  if(c<8192){player_x=(u8)((player_x&0xf0)|(c&15));player_y=(u8)((player_y&0xf0)|((c>>4)&15));anim=(u16)((anim&0xffe0)|((c>>8)&31));}
  mode=(c<40960)?1:(u8)(next()%10);ending_phase=(c<40960)?0:(next()%5);ending_timer=next();ingame_status=next();
  for(i=0;i<256;i++)world[i]=(c%5==0)?next():(next()%35);
  if(c>=8192 && c<22272){
   memcpy(world,genesis_test_maps+(c-8192)/256*256,256);
   player_x=(u8)((player_x&0xf0)|(c&15));player_y=(u8)((player_y&0xf0)|((c>>4)&15));
  }
  for(i=0;i<48;i++){objects[4*i]=next()%32;objects[4*i+1]=player_x+(i8)((int)(next()%145)-72);objects[4*i+2]=player_y+(i8)((int)(next()%145)-72);objects[4*i+3]=next();}
  keys_left=next();stage_name=next();lives=next();time_secs=next();score=((u32)next()<<16)|((u16)next()<<8)|next();stage_bonus=score;entered_password=score;
  title_option=next()%4;title_show_menu=next();option_selected=next()%5;continue_option=next()%2;password_dial=next()%16;time_setting=next();life_setting=next();sound_test=next();
  for(i=0;i<48;i++)credits_text[i]=next();
  reference();memcpy(world_before,world,256);memcpy(objects_before,objects,192);genesis_render_stage();
  if(memcmp(world_before,world,256)||memcmp(objects_before,objects,192)){printf("GAME STATE MUTATED %u\n",c);return 3;}
  if(memcmp(display_plane,genesis_plane,256)||memcmp(display_palettes,genesis_palettes,256)||memcmp(ref_hud,genesis_hud,24)||memcmp(ref_sprites,genesis_sprites,252)||genesis_sprite_count!=render_oam_index/4||genesis_sprite_overflow!=oam_overflow){
   for(i=0;i<256;i++)if(display_plane[i]!=genesis_plane[i]){printf("PLANE %u %u %u/%u mode%u\n",c,i,display_plane[i],genesis_plane[i],mode);return 1;}
   printf("MISMATCH %u mode%u sprites%u/%u overflow%u/%u\n",c,mode,genesis_sprite_count,render_oam_index/4,genesis_sprite_overflow,oam_overflow);return 2;
  }
 }
 puts("PASS 50000");return 0;
}
'''
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True);p.add_argument('--game-api',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 out.mkdir(parents=True);root=Path(__file__).resolve().parents[1];renderer=root/'src/fdisbull/game_sources/genesis_game_renderer.c';reference=root/'src/fdisbull/game_sources/nes_globe_renderer.c';render_bytes=renderer.read_bytes();ref_bytes=reference.read_bytes();text=ref_bytes.decode();rom=checked_rom(a.rom.read_bytes());assets=globe_assets(rom)
 # C reference is the independently retained NES implementation, except for
 # the deliberately target-neutral title label and extracted helper stubs.
 ending=text[text.index('void draw_ending_planet(void) {'):text.index('\nvoid draw_objects(void)')].replace('void draw_ending_planet(void)', 'static void ref_ending(void)').replace('ending_ids[graphic]', 'ending_ids_value(graphic)').replace('ending_ids[graphic+1]', 'ending_ids_value(graphic+1)').replace('ending_ids[graphic+2]', 'ending_ids_value(graphic+2)').replace('ending_ids[graphic+3]', 'ending_ids_value(graphic+3)')
 objects_body=text[text.index('void draw_objects(void) {'):text.index('\nvoid draw_menu(void)')].replace('void draw_objects(void)', 'static void ref_objects(void)')
 menu=text[text.index('void draw_menu(void) {'):text.index('\nvoid draw_game(void)')].replace('void draw_menu(void)', 'static void ref_menu(void)').replace('REMIX / NES','REMIX')
 header=a.game_api.read_text().replace('typedef unsigned long u32;','typedef unsigned int u32;').replace('typedef signed long i32;','typedef signed int i32;')
 (out/'game_api.h').write_text(header);(out/'harness.c').write_text(HARNESS+ending+objects_body+menu+MAIN)
 maps=b''.join(rom[int.from_bytes(rom[0x655ca+i*8:0x655ce+i*8],'big'):][:256] for i in range(55))
 if len(maps)!=55*256:raise ValueError('invalid stage maps')
 arrays={'genesis_test_maps':maps,'genesis_projection':assets['projection'],'genesis_terrain':b''.join(assets['terrain_frames']),'genesis_object_projection':assets['objects'],'genesis_raft_projection':assets['rafts'],'genesis_ending_projection':assets['ending'],'genesis_ending_ids':assets['ending_ids'],'genesis_tile_palette':bytes(1 if i==3 or i>=23 else 3 if i in (4,9,10,15,18,24) else 2 if i in (1,2,7,16,19,21,22) else 0 for i in range(35)),'genesis_chr':assets['chr']}
 (out/'assets.c').write_text('\n'.join('const unsigned char '+name+'['+str(len(data))+']={'+','.join(map(str,data))+'};' for name,data in arrays.items()))
 cmd=['cc','-std=c99','-O2','-Wno-unknown-pragmas','-I',str(out),'-o',str(out/'check'),str(renderer),str(out/'harness.c'),str(out/'assets.c')];build=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 run=subprocess.run([str(out/'check')],capture_output=True,text=True,timeout=120);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode or run.stdout.strip()!='PASS 50000':raise RuntimeError(run.stdout+run.stderr)
 if renderer.read_bytes()!=render_bytes or reference.read_bytes()!=ref_bytes or a.rom.read_bytes()!=rom:raise RuntimeError('inputs changed during check')
 receipt={'passed':True,'cases':50000,'source_rom_sha256':sha(rom),'renderer_sha256':sha(render_bytes),'reference_sha256':sha(ref_bytes),'harness_sha256':sha((HARNESS+ending+objects_body+menu+MAIN).encode()),'program_sha256':sha((out/'check').read_bytes()),'compared':'full plane, per-cell palettes, HUD, ordered sprite staging, count and overflow against NES C bodies and checked source assets; world and objects remain unchanged', 'coverage':'all 256 camera phases crossed with all 32 animation phases; all 55 original stage maps across 256 phases; randomized game/menu/ending states','adaptation':'title says REMIX rather than REMIX / NES','limits':['host C only, deterministic synthetic states and mace helper','not native 68000, VDP timing, Genesis original pixel parity or full-game completion','artifacts and source-derived assets remain private']}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
