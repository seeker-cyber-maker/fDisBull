#!/usr/bin/env python3
"""Verify the checked-ROM projection coverage and sparse 6502 terrain clear."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import check_miniplanets_globe_fast as native

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--rom',required=True,type=Path);p.add_argument('--cc65-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 from fdisbull.udl_miniplanets_full import checked_rom,globe_assets
 src=Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources/nes_globe_fast.s'
 data=src.read_bytes();text=data.decode();start=text.index('_globe_clear_terrain:');end=text.index('_globe_clear_oam:',start)
 runs=[(int(x),int(y)) for x,y in re.findall(r'clear_terrain_run\s+(\d+),\s*(\d+)',text[start:end])]
 clear={i for begin,length in runs for i in range(begin,begin+length)}
 if len(clear)!=112 or any(i<0 or i>=256 for i in clear):raise AssertionError('unexpected sparse clear geometry')
 projection=globe_assets(checked_rom(a.rom.read_bytes()))['projection']
 all_covered=set()
 for phase in range(256):
  view=projection[phase*256:(phase+1)*256];covered=set()
  for record in range(0,256,4):
   position=view[record];covered.update(position+d for d in (0,1,16,17) if position+d<256)
  all_covered.update(covered)
  missing=set(range(256))-clear-covered
  if missing:raise AssertionError(f'phase {phase}: uncleared and unwritten cells {sorted(missing)}')
 spans=[(5,7),(18,12),(34,12),(50,13),(65,14),(81,14),(97,14),(113,14),(129,14),(145,14),(161,14),(178,12),(194,12),(212,8)]
 union={i for start,length in spans for i in range(start,start+length)}
 if len(union)!=174 or union!=all_covered:raise AssertionError('sparse upload spans do not match projection union')
 native.HARNESS=native.HARNESS.replace('void globe_clear(void);','void globe_clear(void);\nvoid globe_clear_terrain(void);\nvoid globe_clear_oam(void);').replace('u16 i,block,count;int n;unsigned long start,c0,c1,c2,f0,f1,f2;', 'u16 i,block,count;int n;unsigned long start,c0,c1,c2,f0,f1,f2,fullcycles=0;').replace('setup();start=cycles();globe_clear();f0=cycles()-start;', 'setup();start=cycles();globe_clear();fullcycles+=cycles()-start;setup();start=cycles();globe_clear_terrain();globe_clear_oam();f0=cycles()-start;').replace('BLOCK %u %lu %lu %lu %lu %lu %lu %lu %lu %lu\\n",block,rc0,rc1,rc2,fc0,fc1,fc2,m0,m1,m2)', 'BLOCK %u %lu %lu %lu %lu %lu %lu %lu %lu %lu %lu\\n",block,rc0,rc1,rc2,fc0,fc1,fc2,m0,m1,m2,fullcycles)').replace('block=0;rc0=rc1=rc2=fc0=fc1=fc2=m0=m1=m2=0;', 'block=0;rc0=rc1=rc2=fc0=fc1=fc2=m0=m1=m2=fullcycles=0;')
 union_bytes=','.join('1' if i in union else '0' for i in range(256))
 native.HARNESS=native.HARNESS.replace('int main(void){','static const u8 terrain_union[256]={'+union_bytes+'};\nint main(void){').replace('start=cycles();globe_paint_terrain();f2=cycles()-start;', 'start=cycles();globe_paint_terrain();f2=cycles()-start;for(i=0;i<256;i++)if(!terrain_union[i] && (display_plane[i]||display_palettes[i])){printf("OUTSIDE UNION case%u byte%u\\n",count,i);return 4;}')
 result=native.verify(a.rom,a.cc65_root,a.output)
 if src.read_bytes()!=data:raise RuntimeError('assembly changed during coverage verification')
 rows=[list(map(int,line.split()[1:])) for line in (a.output/'run.txt').read_text().splitlines() if line.startswith('BLOCK ')]
 if not all(len(row)==11 for row in rows):raise RuntimeError('missing matched clear cycle counts')
 result['matched_full_clear_mean_cycles']=sum(row[10] for row in rows)/sum(row[0] for row in rows)
 result['coverage_invariant']={'projection_sha256':hashlib.sha256(projection).hexdigest(),'phases':256,'clear_cells':len(clear),'guaranteed_painted_cells':256-len(clear),'projection_union_cells':len(union),'projection_union_spans':spans,'native_check':'all plane and palette bytes outside union zero after unpaused terrain paint'}
 result['claim']='sparse clear plus actual paint matches original full clear/paint for all cases; coverage separately established for all checked-ROM projection pages'
 (a.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
