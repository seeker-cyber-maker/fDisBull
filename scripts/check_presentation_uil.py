#!/usr/bin/env python3
"""Compare executable presentation UIL with the actual assembled 6502 planner.

Uses deterministic authored buffers. This is a procedure-level comparison; it
is not an NES timing, display, audio or original-ROM validation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
from fdisbull.game_il import canonical
from fdisbull.presentation_il import lift_presentation, presentation_machine
from check_miniplanets_globe_fast import HARNESS as TERRAIN_HARNESS

SPANS=[(5,7),(18,12),(34,12),(50,13),(65,14),(81,14),(97,14),(113,14),
       (129,14),(145,14),(161,14),(178,12),(194,12),(212,8)]
HARNESS=r'''
#include <string.h>
#include <unistd.h>
typedef unsigned char u8;
u8 active_nt,display_plane[256],display_hud[24],display_attributes[16];
extern u8 upload_count,upload_cursor,upload_target_nt,upload_lo[22],upload_hi[22],upload_chunk_end[22];
extern u8 upload_shadow0[296],upload_shadow1[296],stub_lo[36],stub_hi[36];
extern u8 upload_terrain_cached,upload_terrain_valid,upload_terrain_overlay,upload_terrain_sparse,upload_sparse_valid;
void prepare_upload(void);
struct Input {u8 active,cached,exact,overlay,sparse,sparse_valid,data[296];};
static struct Input input;
static u8 out[641];
int main(void){
 int n;u8 i,j;unsigned int at;
 if(sizeof(input)!=302)return 9;
 while((n=read(0,&input,sizeof(input)))!=0){
  if(n!=sizeof(input))return 8;
  active_nt=input.active;upload_terrain_cached=input.cached;upload_terrain_valid=input.exact;
  upload_terrain_overlay=input.overlay;upload_terrain_sparse=input.sparse;upload_sparse_valid=input.sparse_valid;
  memcpy(display_plane,input.data,256);memcpy(display_hud,input.data+256,24);memcpy(display_attributes,input.data+280,16);
  memset(upload_chunk_end,0xee,22);prepare_upload();
  out[0]=upload_target_nt;out[1]=upload_count;out[2]=upload_cursor;
  out[3]=upload_terrain_valid;out[4]=upload_sparse_valid;at=5;
  memcpy(out+at,upload_shadow0,296);at+=296;memcpy(out+at,upload_shadow1,296);at+=296;
  memset(out+at,0xff,22);
  for(i=0;i<upload_count;i++){
   for(j=0;j<36;j++)if(upload_lo[i]==stub_lo[j] && upload_hi[i]==stub_hi[j])break;
   if(j==36)return 7;out[at+i]=j;
  }
  at+=22;memcpy(out+at,upload_chunk_end,22);at+=22;
  if(at!=641 || write(1,out,641)!=641)return 6;
 }
 return 0;
}
'''

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc65-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 out=a.output.resolve();cc=a.cc65_root.resolve();root=Path(__file__).resolve().parents[1];src=root/'src/fdisbull/game_sources/nes_display_fast.s';asm=src.read_bytes();program=lift_presentation();uil=canonical(program)
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 out.mkdir(parents=True)
 names=[*(f'upload_row{i}' for i in range(16)),*(f'upload_hud{i}' for i in range(2)),*(f'upload_attr{i}' for i in range(4)),*(f'upload_core{i}' for i in range(14))]
 stub='.setcpu "6502"\n.segment "RENDERFAST"\n'+''.join(f'.export {x}\n{x}: rts\n' for x in names)
 stub+='.export _stub_lo,_stub_hi\n_stub_lo: .byte '+','.join(f'<({x}-1)' for x in names)+'\n_stub_hi: .byte '+','.join(f'>({x}-1)' for x in names)+'\n'
 cfg=(cc/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
 (out/'sim.cfg').write_text(cfg);(out/'harness.c').write_text(HARNESS);(out/'stub.s').write_text(stub);(out/src.name).write_bytes(asm);(out/'program.uil.json').write_bytes(uil+b'\n')
 build=subprocess.run([str(cc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/src.name),str(out/'stub.s'),str(out/'harness.c')],capture_output=True,text=True,timeout=60);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 rng=random.Random(0x6502174);m=presentation_machine(program);fixture=bytearray();expected=[]
 union={i for begin,length in SPANS for i in range(begin,begin+length)}
 def send(staging,cached,sparse,overlay,miss=False):
  state=m.snapshot();exact=0 if miss else state['presentation_terrain_valid'];active=state['presentation_active_nt'];sv=state['presentation_sparse_valid']
  fixture.extend(bytes((active,cached,exact,overlay,sparse,sv))+bytes(staging))
  m.set_state({'presentation_staging':staging,'presentation_terrain_cached':cached,'presentation_terrain_valid':exact,'presentation_overlay':overlay,'presentation_sparse':sparse,'presentation_chunk_end':[238]*22})
  if m.call('presentation_prepare')['result']!=1:raise RuntimeError('model unexpectedly busy')
  state=m.snapshot();ids=state['presentation_jobs'][:state['presentation_count']]+[255]*(22-state['presentation_count'])
  expected.append(bytes((state['presentation_target_nt'],state['presentation_count'],state['presentation_cursor'],state['presentation_terrain_valid'],state['presentation_sparse_valid']))+bytes(state['presentation_shadow0'])+bytes(state['presentation_shadow1'])+bytes(ids)+bytes(state['presentation_chunk_end']))
  while m.snapshot()['presentation_ready']:m.call('presentation_complete')
 for _ in range(40):
  base=[rng.randrange(256) if i in union or i>=256 else 0 for i in range(296)]
  send(base,0,1,0,True)
  for __ in range(3):
   base[256+rng.randrange(24)]=rng.randrange(256);send(base,1,1,0)
  paused=base.copy()
  for i in range(5,11):paused[i]=65+i
  paused[280]^=0x40
  send(paused,1,0,1);send(paused,1,0,1)
  send(base,1,1,0);send(base,1,1,0)
  menu=[rng.randrange(256) for _ in range(296)];send(menu,0,0,0);send(menu,0,0,0)
  send(base,1,1,0);send(base,1,1,0)
 (out/'cases.bin').write_bytes(fixture)
 run=subprocess.run([str(cc/'bin/sim65'),str(out/'check')],input=fixture,capture_output=True,timeout=300)
 (out/'native.bin').write_bytes(run.stdout);(out/'run.txt').write_bytes(run.stderr)
 if run.returncode:raise RuntimeError(f'native exit {run.returncode}: {run.stderr[-1000:]}')
 if len(run.stdout)!=641*len(expected):raise RuntimeError(f'incomplete native output {len(run.stdout)}')
 for i,want in enumerate(expected):
  got=run.stdout[641*i:641*(i+1)]
  if got!=want:
   at=next(j for j in range(641) if got[j]!=want[j]);raise RuntimeError(f'case {i}: byte {at}, native {got[at]} vs UIL {want[at]}')
 terrain_src=root/'src/fdisbull/game_sources/nes_globe_fast.s';terrain_asm=terrain_src.read_bytes()
 terrain_harness=TERRAIN_HARNESS[:TERRAIN_HARNESS.index('int main(void){')]+r"""
extern u8 terrain_staging_valid;
void globe_clear_terrain(void);
int main(void){
 int n;u8 input[512];
 while((n=read(0,input,512))!=0){
  if(n!=512)return 2;
  memcpy(display_plane,input,256);memcpy(display_palettes,input+256,256);
  terrain_staging_valid=1;globe_clear_terrain();
  if(write(1,display_plane,256)!=256||write(1,display_palettes,256)!=256||write(1,&terrain_staging_valid,1)!=1)return 3;
 }
 return 0;
}
"""
 terrain_cfg=cfg.replace('start = $2000, size = $FFC0 - $2000 - __STACKSIZE__', 'start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0')
 (out/'terrain.cfg').write_text(terrain_cfg);(out/'terrain-harness.c').write_text(terrain_harness);(out/terrain_src.name).write_bytes(terrain_asm)
 build2=subprocess.run([str(cc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'terrain.cfg'),'-o',str(out/'terrain-check'),str(out/terrain_src.name),str(out/'terrain-harness.c')],capture_output=True,text=True,timeout=60)
 (out/'terrain-build.txt').write_text(build2.stdout+build2.stderr)
 if build2.returncode:raise RuntimeError(build2.stderr)
 terrain_input=bytes(rng.randrange(256) for _ in range(512*32))
 run2=subprocess.run([str(cc/'bin/sim65'),str(out/'terrain-check')],input=terrain_input,capture_output=True,timeout=60)
 (out/'terrain-native.bin').write_bytes(run2.stdout)
 if run2.returncode or len(run2.stdout)!=513*32:raise RuntimeError('terrain native check failed')
 for i in range(32):
  m2=presentation_machine(program);chunk=terrain_input[i*512:(i+1)*512]
  m2.set_state({'presentation_plane':list(chunk[:256]),'presentation_palettes':list(chunk[256:]),'presentation_staging_valid':1})
  m2.call('presentation_clear_terrain');state=m2.snapshot()
  want=bytes(state['presentation_plane'])+bytes(state['presentation_palettes'])+bytes([state['presentation_staging_valid']])
  if run2.stdout[i*513:(i+1)*513]!=want:raise RuntimeError(f'terrain clear mismatch case {i}')
 if terrain_src.read_bytes()!=terrain_asm:raise RuntimeError('terrain source changed during check')
 if src.read_bytes()!=asm or canonical(lift_presentation())!=uil:raise RuntimeError('source changed during check')
 receipt={'passed':True,'cases':len(expected),'uil_sha256':sha(uil),'planner_sha256':sha(asm),'harness_sha256':sha(HARNESS.encode()),'fixture_sha256':sha(fixture),'native_program_sha256':sha((out/'check').read_bytes()),'native_output_sha256':sha(run.stdout),'terrain_clear_cases':32,'terrain_assembly_sha256':sha(terrain_asm),'terrain_harness_sha256':sha(terrain_harness.encode()),'terrain_fixture_sha256':sha(terrain_input),'terrain_output_sha256':sha(run2.stdout),'compared':'ordered 6502 routine IDs, chunk starts/ends, both complete 296-byte shadows, target/count/cursor and exact/sparse certificates; sparse terrain clear plane/palette bytes and staging validity','limits':['authored synthetic states and procedure-level sim65; not PPU, IRQ, DMA or original ROM execution','native completion is modeled between calls; staging and plans must remain immutable while pending']}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
