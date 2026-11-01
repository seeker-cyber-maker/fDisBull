#!/usr/bin/env python3
"""Compare the native 6502 actor renderer against the retained C body."""
import argparse,hashlib,json,subprocess
from pathlib import Path

PRE=r'''
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;typedef signed char i8;typedef unsigned int u16;
u8 display_plane[256],display_palettes[256],projection_cache[256],world[256];
u8 display_hud[24],display_attributes[16],lives,time_secs,stage_name,keys_left;
u8 render_oam_page,render_oam_index,oam_overflow,globe_source_hi,globe_rowbase,globe_colbase;
u16 globe_atlas_pointer,render_epoch,anim;unsigned long score;
const u8 tile_palette[35]={0};
u8 objects[192],player_x,player_y,player_jump,player_die;
void draw_objects(void);
u16 read_stack(void);
u8 mace_x(u8 slot){return (u8)(objects[slot*4+1]+objects[slot*4+3]);}
u8 mace_y(u8 slot){return (u8)(objects[slot*4+2]-objects[slot*4+3]);}
static u8 component(u8 x,u8 y,u8 raft){return (u8)((x*29u+y*113u+(u16)raft*71u)^((x*y)>>3));}
u16 object_projection_pair(u8 x,u8 y,u8 raft){return (u16)(component(x,y,raft)|((u16)component(y,x,raft)<<8));}
static void reference_sprite(u8 x,u8 y,u8 tile,u8 palette){
 volatile u8 *oam;if(render_oam_index>=252){oam_overflow=1;return;}
 oam=(volatile u8*)((u16)render_oam_page<<8);
 oam[render_oam_index]=y-1;oam[render_oam_index+1]=tile;
 oam[render_oam_index+2]=palette&3;oam[render_oam_index+3]=x;
 render_oam_index=render_oam_index+4;
}
#define draw_sprite reference_sprite
'''
POST=r'''
#undef draw_sprite
static u8 expected[512],saved[512],object_before[192],seen_types[32];
static u16 seed=0x5ac3;
static u8 next(void){seed^=seed<<7;seed^=seed>>9;seed^=seed<<8;return (u8)seed;}
int main(void){
 unsigned long c;u16 i,stack,stack_after;u8 x,y,index,overflow,ei,eo;
 for(c=0;c<CASE_COUNT;c++){
  player_x=next();player_y=next();player_jump=next();player_die=next();render_epoch=(u16)(next()|((u16)next()<<8));
  for(i=0;i<48;i++){
   objects[i*4]=next();if(c&1)objects[i*4]&=31;seen_types[objects[i*4]>>3]|=(u8)(1u<<(objects[i*4]&7));
   objects[i*4+1]=player_x+(i8)((int)(next()%145)-72);
   objects[i*4+2]=player_y+(i8)((int)(next()%145)-72);
   objects[i*4+3]=next();
  }
  memcpy(object_before,objects,192);
  for(i=0;i<512;i++)saved[i]=next();
  memcpy((void*)0x200,saved,512);render_oam_page=2+((c>>8)&1);
  index=next();overflow=next();render_oam_index=index;oam_overflow=overflow;
  reference_draw_objects();memcpy(expected,(void*)0x200,512);ei=render_oam_index;eo=oam_overflow;
  memcpy((void*)0x200,saved,512);render_oam_index=index;oam_overflow=overflow;stack=read_stack();
  x=player_x;y=player_y;draw_objects();stack_after=read_stack();
  if(stack!=stack_after||ei!=render_oam_index||eo!=oam_overflow||memcmp(expected,(void*)0x200,512)||memcmp(object_before,objects,192)||x!=player_x||y!=player_y){
   printf("FAIL %lu index%u expected%u actual%u overflow%u/%u stack%u/%u\n",c,index,ei,render_oam_index,eo,oam_overflow,stack,stack_after);for(i=0;i<512;i++)if(expected[i]!=((u8*)0x200)[i]){printf("OAM %u %u/%u\n",i,expected[i],((u8*)0x200)[i]);break;}return 1;
  }
 }
 for(i=0;i<32;i++)if(seen_types[i]!=255){printf("MISSING TYPES %u\n",i);return 2;}
 printf("PASS %lu\n",c);return 0;
}
'''
STUB='''.setcpu "6502"\n.importzp sp,ptr4\n.export _read_stack,_banked_call\n.segment "CODE"\n_read_stack:\n lda sp\n ldx sp+1\n rts\n_banked_call:\n jmp (ptr4)\n'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc65-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--cases',type=int,default=100000);a=p.parse_args()
 if not 1<=a.cases<=100000:raise ValueError('cases must be between 1 and 100000')
 root=Path(__file__).resolve().parents[1];src=root/'src/fdisbull/game_sources/nes_globe_fast.s';renderer=root/'src/fdisbull/game_sources/nes_globe_renderer.c';data=src.read_bytes();cdata=renderer.read_bytes();c=cdata.decode();start=c.index('void draw_objects(void) {');end=c.index('\nvoid draw_menu(void)',start);body=c[start:end].replace('void draw_objects(void)','void reference_draw_objects(void)',1)
 out=a.output.resolve();cc=a.cc65_root.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh output outside Git')
 out.mkdir(parents=True)
 cfg=(cc/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
 harness=f"#define CASE_COUNT {a.cases}UL\n"+PRE+body+POST
 (out/'sim.cfg').write_text(cfg);(out/'harness.c').write_text(harness);(out/'stub.s').write_text(STUB);(out/src.name).write_bytes(data)
 build=subprocess.run([str(cc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/src.name),str(out/'stub.s'),str(out/'harness.c')],capture_output=True,text=True,timeout=60)
 (out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 run=subprocess.run([str(cc/'bin/sim65'),'-c',str(out/'check')],capture_output=True,text=True,timeout=600);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode or not run.stdout.startswith(f'PASS {a.cases}\n'):raise RuntimeError(run.stdout+run.stderr)
 if src.read_bytes()!=data or renderer.read_bytes()!=cdata:raise RuntimeError('source changed during check')
 sha=lambda b:hashlib.sha256(b).hexdigest()
 receipt={'passed':True,'cases':a.cases,'assembly_sha256':sha(data),'renderer_sha256':sha(cdata),'harness_sha256':sha(harness.encode()),'program_sha256':sha((out/'check').read_bytes()),'coverage':'actual retained C draw_objects vs assembled 6502, 48 slots, relative positions, all 256 actor type bytes, rotated epochs, both OAM pages, OAM and input preservation, stack balance','limits':'synthetic deterministic projection and mace helpers; sim65 does not exercise NES bank switching or actual projection assets; full cartridge integration required'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
