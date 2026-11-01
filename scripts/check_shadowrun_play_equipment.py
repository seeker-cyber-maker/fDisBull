#!/usr/bin/env python3
"""Compare captured original equipment effects with target-adapted NES UI."""
import argparse
import hashlib
import json
from pathlib import Path
from check_shadowrun_opening_route import (SOURCE_ROM_SHA,NES_CORE_SHA,GENESIS_CORE_SHA,
    captured_file,checked_receipt,indexed_frames,scheduled_mask)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ('source-rom','capture','nes','run','output'):p.add_argument('--'+name,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.source_rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA:raise ValueError('wrong source ROM')
 raw=(a.capture/'capture.json').read_bytes();c=json.loads(raw)
 if c.get('assistance')!='ordinary controller schedule; no memory patches' or c.get('inputs',{}).get('rom',{}).get('sha256')!=sha(rom) or c.get('inputs',{}).get('core',{}).get('sha256')!=GENESIS_CORE_SHA:raise ValueError('wrong source capture')
 sr=captured_file(a.capture,c,'native/receipt.json');src=json.loads(sr);checked_receipt(src,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 for frame,mask in ((6000,8),(6060,128),(6120,2),(6180,2),(6240,128),(6300,2),(6360,2)):
  if scheduled_mask(src,frame)!=mask:raise ValueError('unexpected original input route')
 receipt_raw=(a.run/'receipt.json').read_bytes();rec=json.loads(receipt_raw);checked_receipt(rec,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 if rec.get('inputs') != [{'start':100,'end':112,'buttons':['START']},{'start':130,'end':142,'buttons':['A']},{'start':190,'end':202,'buttons':['RIGHT']},{'start':220,'end':232,'buttons':['A']}]:raise ValueError('unexpected target input route')
 if rec.get('watches')!=[{'name':'state','offset':1792,'length':41}]:raise ValueError('unexpected publication watch')
 trace=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(trace,rec);rows=[];bad=[]
 for sf,nf in ((5999,120),(6210,150),(6390,240)):
  source=captured_file(a.capture,c,f'native/scene-{sf:06d}/ram.bin');target=bytes.fromhex(frames[nf]['raw']['state'])
  if len(source)!=65536 or len(target)!=41 or target[:2]!=b'SW' or target[22]&1:raise ValueError('invalid publication')
  source=bytes(source[i^1] for i in range(len(source)))
  original=[source[0x156],source[0x157],source[0x14e],source[0x176]]
  actual=[target[32],target[33],target[34],target[31]]
  rows.append({'source_frame':sf,'target_frame':nf,'source':original,'target':actual})
  if original!=actual:bad.append({'source_frame':sf,'target_frame':nf})
 result={'format':'fdisbull-shadowrun-play-equipment-check-1','fields':['weapon_slot','weapon_item','ammo','armor'],
   'comparisons':rows,'mismatches':bad,'source_capture_sha256':sha(raw),'source_receipt_sha256':sha(sr),
   'nes_sha256':sha(nes),'nes_receipt_sha256':sha(receipt_raw),'nes_trace_sha256':sha(trace),
   'scope':'original two-confirm equipment route versus target one-confirm adaptation, captured weapon and armor only'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
