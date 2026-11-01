#!/usr/bin/env python3
"""Compare source capture to the target's completed movement publications."""
import argparse,hashlib,json
from pathlib import Path
from check_shadowrun_opening_route import (FIELDS,NES_CORE_SHA,GENESIS_CORE_SHA,SOURCE_ROM_SHA,
    captured_file,checked_receipt,indexed_frames,scheduled_mask)
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('source-rom','capture','nes','run','output'):p.add_argument('--'+n,required=True,type=Path)
 for n in ('source-start','nes-start','count','input-mask'):p.add_argument('--'+n,required=True,type=int)
 p.add_argument('--allow-blocked',action='store_true',help='include published collision-blocked ticks')
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.source_rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA or not 1<=a.count<=500:raise ValueError('wrong source or count')
 capture_raw=(a.capture/'capture.json').read_bytes();capture=json.loads(capture_raw)
 if (capture.get('format')!='fdisbull-private-genesis-scenes-1' or capture.get('assistance')!='ordinary controller schedule; no memory patches' or capture.get('inputs',{}).get('rom',{}).get('sha256')!=sha(rom) or capture.get('inputs',{}).get('core',{}).get('sha256')!=GENESIS_CORE_SHA):raise ValueError('wrong capture provenance')
 sr=captured_file(a.capture,capture,'native/receipt.json');source=json.loads(sr);checked_receipt(source,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 rr=(a.run/'receipt.json').read_bytes();receipt=json.loads(rr);checked_receipt(receipt,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 if receipt.get('watches')!=[{'name':'state','offset':1792,'length':41}]:raise ValueError('unexpected watch')
 trace=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(trace,receipt);selected=[];previous=None
 for nf in range(a.nes_start,receipt['frames']):
  b=bytes.fromhex(frames[nf]['raw']['state'])
  if len(b)!=41 or b[22]&1:continue
  if previous is not None and b[23]==previous:continue
  if previous is not None and b[23]!=(previous+1)&255:raise ValueError('missed completed tick')
  previous=b[23];selected.append(nf)
  if len(selected)==a.count:break
 if len(selected)!=a.count:raise ValueError('insufficient target ticks')
 bad=[];hashes=[]
 for i,nf in enumerate(selected):
  sf=a.source_start+i;row=frames[nf];b=bytes.fromhex(row['raw']['state'])
  if (b[:2]!=b'SW' or b[3]!=0 or b[2] not in ((1,4) if a.allow_blocked else (1,)) or row['input_mask']!=a.input_mask or scheduled_mask(receipt,nf)!=a.input_mask or scheduled_mask(source,sf)!=a.input_mask):raise ValueError('unexpected status or input schedule')
  mem=captured_file(a.capture,capture,f'native/scene-{sf:06d}/ram.bin');hashes.append(sha(mem))
  for name,to,so in FIELDS:
   got=int.from_bytes(b[to:to+2],'little');want=int.from_bytes(mem[so:so+2],'little')
   if got!=want:bad.append({'source_frame':sf,'target_frame':nf,'field':name,'source':want,'target':got})
 result={'format':'fdisbull-shadowrun-play-route-check-1','count':a.count,'source_start':a.source_start,'target_frames':selected,'input_mask':a.input_mask,'fields':[x[0] for x in FIELDS],'mismatches':bad,'nes_sha256':sha(nes),'nes_trace_sha256':sha(trace),'nes_receipt_sha256':sha(rr),'source_capture_sha256':sha(capture_raw),'source_receipt_sha256':sha(sr),'source_ram_sha256':hashes,'scope':'prepared target, ordinary source and target input, selected completed ticks; published fields only'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f'{a.count} comparisons, {len(bad)} mismatches')
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
