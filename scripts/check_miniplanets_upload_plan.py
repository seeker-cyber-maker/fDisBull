#!/usr/bin/env python3
"""Compare the assembled NES dirty-region planner with an independent C model.

This exercises authored staging bytes on sim65. PPU execution, interrupt
ownership and mapper behavior require the separate full-cartridge checks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HARNESS = r'''
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
typedef unsigned int u16;
u8 active_nt,display_plane[256],display_hud[24],display_attributes[16];
extern u8 upload_count,upload_cursor,upload_target_nt,upload_lo[22],upload_hi[22];
extern u8 upload_shadow0[296],upload_shadow1[296],stub_lo[22],stub_hi[22];
extern u8 upload_terrain_cached,upload_terrain_valid,upload_terrain_overlay;
void prepare_upload(void);
static u8 expected_shadow[2][296],expected_valid[2],staging[296],expected_terrain_valid;
static unsigned long calls=0, planned=0;
static unsigned int seed=0x6502;
static u8 random_byte(void){seed^=seed<<7;seed^=seed>>9;seed^=seed<<8;return (u8)seed;}
static u16 offset(u8 r){if(r<16)return (u16)r*16;if(r<18)return 256+(u16)(r-16)*12;return 280+(u16)(r-18)*4;}
static u8 size(u8 r){if(r<16)return 16;if(r<18)return 12;return 4;}
static void check(u8 target){
 u8 r,i,n=0,wanted[22];u16 start;u8 length,dirty;
 u8 cached=upload_terrain_cached,overlay=upload_terrain_overlay;
 active_nt=target^1;
 memcpy(display_plane,staging,256);memcpy(display_hud,staging+256,24);memcpy(display_attributes,staging+280,16);
 for(r=0;r<22;r++){
  start=offset(r);length=size(r);dirty=!expected_valid[target];
  for(i=0;i<length;i++)if(expected_shadow[target][start+i]!=staging[start+i])dirty=1;
  if(dirty){wanted[n++]=r;memcpy(expected_shadow[target]+start,staging+start,length);}
 }
 expected_valid[target]=1;
 if(cached)expected_terrain_valid|=(u8)(1<<target);
 else expected_terrain_valid&=(u8)~(1<<target);
 upload_cursor=0x91;prepare_upload();calls++;planned+=n;
 if(upload_terrain_valid!=expected_terrain_valid || upload_terrain_cached!=cached || upload_terrain_overlay!=overlay){
  printf("HINT call %lu valid %u/%u cached %u overlay %u\n",calls,upload_terrain_valid,expected_terrain_valid,upload_terrain_cached,upload_terrain_overlay);exit(5);
 }
 if(upload_target_nt!=target || upload_count!=n || upload_cursor!=0){
  printf("META call %lu target %u/%u count %u/%u cursor %u\n",calls,upload_target_nt,target,upload_count,n,upload_cursor);exit(1);
 }
 for(i=0;i<n;i++)if(upload_lo[i]!=stub_lo[wanted[i]] || upload_hi[i]!=stub_hi[wanted[i]]){
  printf("PLAN call %lu index %u region %u\n",calls,i,wanted[i]);exit(2);
 }
 if(memcmp(upload_shadow0,expected_shadow[0],296)||memcmp(upload_shadow1,expected_shadow[1],296)){
  printf("SHADOW call %lu\n",calls);exit(3);
 }
 if(memcmp(display_plane,staging,256)||memcmp(display_hud,staging+256,24)||memcmp(display_attributes,staging+280,16)){
  printf("STAGING call %lu\n",calls);exit(4);
 }
 /* Model the ownership contract: only after a plan is consumed may the next
    call prepare another plan. This harness does not execute NMI jobs. */
}
int main(void){
 u16 i,j;u8 target;
 /* First cached-hint call must still force a cold full plan. */
 memset(staging,0,sizeof(staging));upload_terrain_cached=1;check(0);check(1);check(0);check(1);
 upload_terrain_cached=0;
 /* Each of the 296 positions is the sole delta against each NT shadow. */
 for(i=0;i<296;i++){
  staging[i]^=0x5a;check(0);check(1);check(0);check(1);
 }
 /* Arbitrary simultaneous changes, both target orders, and no-op replays. */
 for(j=0;j<256;j++){
  for(i=0;i<296;i++)staging[i]=random_byte();
  target=(u8)(j&1);check(target);check(target^1);check(target);check(target^1);
 }
 /* Producer cache miss: both prior terrain certificates are invalid. */
 upload_terrain_cached=0;upload_terrain_valid=0;expected_terrain_valid=0;
 for(i=0;i<296;i++)staging[i]=(u8)(i*37+19);
 check(0);check(1);
 /* Restored same terrain on both targets: HUD may change independently. */
 upload_terrain_cached=1;upload_terrain_overlay=0;check(0);check(1);
 staging[256]^=0x21;staging[279]^=0x48;check(0);check(1);check(0);check(1);
 /* A changed pause overlay modifies the top row and its attributes. */
 upload_terrain_overlay=1;for(i=0;i<16;i++)staging[i]^=0x7d;
 for(i=280;i<284;i++)staging[i]^=0x35;check(0);check(1);check(0);check(1);
 /* Transition back from pause to unpaused restored terrain. */
 upload_terrain_overlay=0;for(i=0;i<16;i++)staging[i]^=0x7d;
 for(i=280;i<284;i++)staging[i]^=0x35;check(0);check(1);
 /* New terrain cache miss invalidates both even if only one target is drawn. */
 upload_terrain_cached=0;upload_terrain_valid=0;expected_terrain_valid=0;
 for(i=0;i<256;i++)staging[i]^=0xa7;for(i=280;i<296;i++)staging[i]^=0x53;check(0);
 upload_terrain_cached=1;check(0);check(1);check(1);
 /* Menu/ending is not cached: invalidate each target when used. */
 upload_terrain_cached=0;for(i=0;i<296;i++)staging[i]^=0x3c;check(0);check(1);
 /* Restore the cached terrain after a nonterrain view on both targets. */
 upload_terrain_cached=1;for(i=0;i<296;i++)staging[i]^=0x3c;check(0);check(1);check(0);check(1);
 printf("PASS %lu %lu\n",calls,planned);return 0;
}
'''

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc65-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/'src/fdisbull/game_sources/nes_display_fast.s'
    out=args.output.resolve(); toolchain=args.cc65_root.resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):
        raise ValueError('choose a fresh output outside Git')
    out.mkdir(parents=True)
    source_bytes=source.read_bytes()
    names=[*(f'upload_row{i}' for i in range(16)),*(f'upload_hud{i}' for i in range(2)),*(f'upload_attr{i}' for i in range(4))]
    stub='.setcpu "6502"\n.segment "RENDERFAST"\n'+''.join(f'.export {name}\n{name}: rts\n' for name in names)
    stub+='.export _stub_lo, _stub_hi\n_stub_lo: .byte '+','.join(f'<({name}-1)' for name in names)+'\n'
    stub+='_stub_hi: .byte '+','.join(f'>({name}-1)' for name in names)+'\n'
    config=(toolchain/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
    (out/'sim.cfg').write_text(config)
    (out/'harness.c').write_text('#include <stdlib.h>\n'+HARNESS)
    (out/'stubs.s').write_text(stub)
    (out/source.name).write_bytes(source_bytes)
    build=subprocess.run([str(toolchain/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-m',str(out/'map.txt'),'-o',str(out/'check'),str(out/source.name),str(out/'stubs.s'),str(out/'harness.c')],capture_output=True,text=True,timeout=60)
    (out/'build.txt').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError(build.stderr)
    run=subprocess.run([str(toolchain/'bin/sim65'),'-c',str(out/'check')],capture_output=True,text=True,timeout=120)
    (out/'run.txt').write_text(run.stdout+run.stderr)
    if run.returncode or not run.stdout.startswith('PASS 2236 '):raise RuntimeError(run.stdout+run.stderr)
    if source.read_bytes()!=source_bytes:raise RuntimeError('planner changed during check')
    receipt={'passed':True,'calls':2236,'planner_sha256':sha(source_bytes),'harness_sha256':sha(HARNESS.encode()),'stubs_sha256':sha(stub.encode()),'program_sha256':sha((out/'check').read_bytes()),'sim65_output':run.stdout.strip(),'coverage':['cached hint on cold first use still forces both full nametables','cache hits with independent HUD changes, both overlay transitions and unchanged replays','producer cache miss invalidates both targets; menu/ending invalidates each target on use','no-change plans','each of 296 byte positions changed separately on both nametables','256 simultaneous full-buffer changes in alternating target order','exact ordered routine addresses, count, cursor, target, both complete shadows, staging preservation'],'limits':['sim65 planner procedure only; no PPU, mapper, NMI, or scheduler execution','assumes pending plan consumed before the next preparation; enforcement is a separate integration contract','authored deterministic vectors, not original game data']}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
