#!/usr/bin/env python3
"""Check native staging ownership and partial terrain restoration over sequences."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from check_miniplanets_globe_fast import HARNESS as BASE

MAIN=r'''
extern u8 terrain_staging_valid;
void globe_clear_planes(void);void globe_clear_oam(void);
u8 globe_restore_terrain(void);void globe_save_terrain(void);
int main(void){
 int n;u16 block=0;unsigned long count=0,hits=0,total_hits=0,start,hit_cycles=0,miss_cycles=0,save_cycles=0;
 u8 restored;unsigned long c;
 if(sizeof(input)!=1779)return 5;
 while((n=read(0,&input,sizeof(input)))!=0){
  if(n!=sizeof(input)){printf("SHORT %d\n",n);return 6;}
  player_x=(u8)((input.colbase<<4)|(input.phase&15));
  player_y=(u8)(input.rowbase|(input.phase>>4));anim=input.animation;
  setup();clear_reference();copy_reference();paint_reference();
  memcpy(expected.plane,display_plane,256);memcpy(expected.palettes,display_palettes,256);
  memcpy(expected.cache,projection_cache,256);memcpy(expected.oam,(void*)0x200,512);
  setup();terrain_staging_valid=0;globe_clear_oam();globe_copy_projection();
  start=cycles();restored=globe_restore_terrain();c=cycles()-start;
  if(restored){hits++;hit_cycles+=c;}
  else {miss_cycles+=c;globe_clear_planes();globe_paint_terrain();start=cycles();globe_save_terrain();save_cycles+=cycles()-start;}
  if(memcmp(expected.plane,display_plane,256)||memcmp(expected.palettes,display_palettes,256)||memcmp(expected.cache,projection_cache,256)||memcmp(expected.oam,(void*)0x200,512)||memcmp(world,input.map,256)){
   printf("MISMATCH %lu phase%u anim%u hit%u\n",count,input.phase,input.animation,restored);return 1;
  }
  count++;block++;
  if(block==256){printf("BLOCK %u %lu %lu %lu %lu\n",block,hits,hit_cycles,miss_cycles,save_cycles);total_hits+=hits;block=0;hits=hit_cycles=miss_cycles=save_cycles=0;}
 }
 if(block){printf("BLOCK %u %lu %lu %lu %lu\n",block,hits,hit_cycles,miss_cycles,save_cycles);total_hits+=hits;}
 printf("PASS %lu %lu\n",count,total_hits);return 0;
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',required=True,type=Path);p.add_argument('--cc65-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--negative-control',action='store_true');a=p.parse_args()
 from fdisbull.udl_miniplanets_full import checked_rom,globe_assets
 root=Path(__file__).resolve().parents[1];source=root/'src/fdisbull/game_sources/nes_globe_fast.s';renderer=root/'src/fdisbull/game_sources/nes_globe_renderer.c';source_bytes=source.read_bytes();renderer_bytes=renderer.read_bytes()
 out=a.output.resolve();cc=a.cc65_root.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh output outside Git')
 out.mkdir(parents=True);rom=checked_rom(a.rom.read_bytes());assets=globe_assets(rom)
 maps=[]
 for stage in (0,19,40,43,44,46):
  at=int.from_bytes(rom[0x655ca+stage*8:0x655ce+stage*8],'big');maps.append((f'stage-{stage}',rom[at:at+256]))
 maps.extend((('all-classes',bytes(i%35 for i in range(256))),('invalid-classes',bytes(range(256)))))
 fixture=out/'cases.bin'
 with fixture.open('wb') as f:
  for _,world in maps:
   for view in range(256):
    for frame in range(32):
     mutable=bytearray(world)
     if frame==17:mutable[(view*13)&255]^=0x40
     f.write(assets['projection'][view*256:(view+1)*256]);f.write(assets['terrain_frames'][frame]);f.write(mutable)
     f.write(bytes((((view*3)&15)*16,(view*7)&15,2+(view&1),0xa0+(view&31),(frame*31)&255,view,frame)))
 main=MAIN.replace('int main(void){', 'static u8 staged_plane[256],staged_palettes[256];\nint main(void){')
 main=main.replace('u8 restored;unsigned long c;', 'u8 restored,staging_before;unsigned long c,partial_hits=0,full_hits=0;u16 i;')
 main=main.replace('setup();terrain_staging_valid=0;globe_clear_oam();globe_copy_projection();', 'setup();memcpy(display_plane,staged_plane,256);memcpy(display_palettes,staged_palettes,256);globe_clear_oam();globe_copy_projection();staging_before=terrain_staging_valid;')
 main=main.replace('if(restored){hits++;hit_cycles+=c;}', 'if(restored){hits++;hit_cycles+=c;if(staging_before)partial_hits++;else full_hits++;}')
 inject = r"""
  /* A pause marker can dirty only the first row of a completed terrain. */
  if(count&1)for(i=5;i<11;i++){display_plane[i]=(u8)(0x80+i);display_palettes[i]=0;}
  /* Menu/ending clear and arbitrary diagnostic writes invalidate staging. */
  if((count%37)==3){globe_clear_planes();for(i=0;i<256;i++){display_plane[i]=(u8)(i^0x57);display_palettes[i]=(u8)(i^0xa8);}NEGATIVE}
  if((count%53)==5){terrain_staging_valid=0;for(i=0;i<256;i++){display_plane[i]=(u8)(i^0x23);display_palettes[i]=(u8)(i^0xd4);}}
  memcpy(staged_plane,display_plane,256);memcpy(staged_palettes,display_palettes,256);
 """.replace('NEGATIVE','if(count==3)terrain_staging_valid=1;' if a.negative_control else '')
 main=main.replace('  count++;block++;',inject+'  count++;block++;')
 main=main.replace('printf("PASS %lu %lu\\n",count,total_hits);', 'printf("PASS %lu %lu PARTIAL %lu FULL %lu\\n",count,total_hits,partial_hits,full_hits);')
 harness=BASE[:BASE.index('int main(void){')].replace('page,sourcehi,atlas_shift;','page,sourcehi,atlas_shift,phase,animation;')+main
 cfg=(cc/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FFC0 - $0200 - __STACKSIZE__','start = $2000, size = $FFC0 - $2000 - __STACKSIZE__, bank = 0').replace('    BSS:', '    RENDERFAST: load = MAIN, type = ro;\n    BSS:')
 (out/'sim.cfg').write_text(cfg);(out/'harness.c').write_text(harness);(out/source.name).write_bytes(source_bytes)
 build=subprocess.run([str(cc/'bin/cl65'),'-t','sim6502','-Oirs','--static-locals','-C',str(out/'sim.cfg'),'-o',str(out/'check'),str(out/source.name),str(out/'harness.c')],capture_output=True,text=True,timeout=60);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 with fixture.open('rb') as stream:run=subprocess.run([str(cc/'bin/sim65'),'-c',str(out/'check')],stdin=stream,capture_output=True,text=True,timeout=600)
 (out/'run.txt').write_text(run.stdout+run.stderr)
 if a.negative_control:
  if run.returncode==0 or 'MISMATCH ' not in run.stdout:raise RuntimeError('negative control failed to detect stale staging: '+run.stdout+run.stderr)
  report={'passed':True,'negative_control':True,'observed':run.stdout.strip(),'source_sha256':hashlib.sha256(source_bytes).hexdigest(),'renderer_sha256':hashlib.sha256(renderer_bytes).hexdigest(),'harness_sha256':hashlib.sha256(harness.encode()).hexdigest()}
  (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 rows=[list(map(int,line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('BLOCK ')]
 count=sum(r[0] for r in rows);hits=sum(r[1] for r in rows);misses=count-hits
 if count!=len(maps)*256*32 or not hits or f'PASS {count} {hits} PARTIAL ' not in run.stdout:raise RuntimeError('incomplete cache coverage')
 final=next(line for line in run.stdout.splitlines() if line.startswith('PASS ')).split();partial_hits=int(final[4]);full_hits=int(final[6])
 if not partial_hits or not full_hits:raise RuntimeError('missing restore path coverage')
 if source.read_bytes()!=source_bytes or renderer.read_bytes()!=renderer_bytes:raise RuntimeError('source changed during check')
 sha=lambda b:hashlib.sha256(b).hexdigest()
 receipt={'passed':True,'cases':count,'hits':hits,'partial_hits':partial_hits,'full_hits':full_hits,'misses':misses,'source_sha256':sha(source_bytes),'renderer_sha256':sha(renderer_bytes),'harness_sha256':sha(harness.encode()),'fixture_sha256':sha(fixture.read_bytes()),'program_sha256':sha((out/'check').read_bytes()),'hit_mean_cycles':sum(r[2] for r in rows)/hits,'miss_probe_mean_cycles':sum(r[3] for r in rows)/misses,'miss_save_mean_cycles':sum(r[4] for r in rows)/misses,'coverage':'8 maps, 256 views, 32 animation frames, changed/reverted world, pause row contamination, menu/ending plane clears, arbitrary writes with invalidation, full plane/palette/cache/OAM comparisons','limits':'synthetic sequences in sim65; game frequency, mapper, NMI and complete frame output require cartridge integration'}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
