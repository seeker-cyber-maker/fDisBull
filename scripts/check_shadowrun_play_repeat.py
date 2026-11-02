#!/usr/bin/env python3
"""Compare six held-A captured source shots with target logical updates."""
import argparse,hashlib,json
from pathlib import Path
from check_shadowrun_opening_route import (SOURCE_ROM_SHA,NES_CORE_SHA,GENESIS_CORE_SHA,captured_file,checked_receipt,indexed_frames,scheduled_mask)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','capture','nes','run','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA:raise ValueError('wrong source')
 cr=(a.capture/'capture.json').read_bytes();c=json.loads(cr)
 if c.get('assistance')!='ordinary controller schedule; no memory patches' or c.get('inputs',{}).get('rom',{}).get('sha256')!=sha(rom) or c.get('inputs',{}).get('core',{}).get('sha256')!=GENESIS_CORE_SHA:raise ValueError('bad capture')
 sr=captured_file(a.capture,c,'native/receipt.json');source=json.loads(sr);checked_receipt(source,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 rr=(a.run/'receipt.json').read_bytes();r=json.loads(rr);checked_receipt(r,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 if r.get('inputs')!=[{'start':100,'end':600,'buttons':['A']}] or r.get('watches')!=[{'name':'state','offset':1792,'length':75}]:raise ValueError('bad target schedule/watch')
 raw=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(raw,r);shots={}
 for f,row in frames.items():
  b=bytes.fromhex(row['raw']['state']);n=b[42]
  if b[:2]==b'SW' and not b[22]&1 and 1<=n<=6 and n not in shots:shots[n]=(f,b)
 if len(shots)!=6:raise ValueError('six shots were not published')
 rows=[];mismatches=[];prior_tick=None
 for n,sf in enumerate((6037,6089,6141,6193,6245,6297),1):
  f,b=shots[n]
  if scheduled_mask(source,sf)!=2 or scheduled_mask(r,f)!=256:raise ValueError('held A missing')
  m=captured_file(a.capture,c,f'native/scene-{sf:06d}/ram.bin');m=bytes(m[i^1] for i in range(len(m)))
  original=[m[0x14e],int.from_bytes(m[0xf9f8:0xf9fa],'big'),int.from_bytes(m[0x1dc:0x1de],'big'),int.from_bytes(m[0xb04:0xb08],'big'),m[0xb89]]
  target=[b[34],int.from_bytes(b[51:53],'little'),int.from_bytes(b[53:55],'little'),int.from_bytes(b[47:51],'little'),b[45]]
  if original!=target or (prior_tick is not None and (b[23]-prior_tick)&255!=52):mismatches.append({'source_frame':sf,'target_frame':f})
  prior_tick=b[23];rows.append({'source_frame':sf,'target_frame':f,'logical_counter':b[23],'source':original,'target':target})
 result={'format':'fdisbull-shadowrun-play-repeat-check-1','fields':['ammo','rng','cooldown','projectile_y_fixed','lifetime'],'rows':rows,'mismatches':mismatches,'nes_sha256':sha(nes),'source_capture_sha256':sha(cr),'source_receipt_sha256':sha(sr),'nes_receipt_sha256':sha(rr),'nes_trace_sha256':sha(raw),'scope':'six held-A shots from prepared state, observer-instrumented source; target one-projectile lifecycle and physical timing differ'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f'{len(rows)} source/target shots, {len(mismatches)} mismatches')
 if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
