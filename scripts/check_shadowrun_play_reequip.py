#!/usr/bin/env python3
"""Compare two original re-equipment effects with the adapted NES inventory."""
import argparse,hashlib,json
from pathlib import Path
from check_shadowrun_opening_route import SOURCE_ROM_SHA,NES_CORE_SHA,GENESIS_CORE_SHA,captured_file,checked_receipt,indexed_frames,scheduled_mask
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('source-rom','capture','nes','run','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.source_rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA:raise ValueError('wrong source ROM')
 cr=(a.capture/'capture.json').read_bytes();c=json.loads(cr)
 if c.get('assistance')!='ordinary controller schedule; no memory patches' or c.get('inputs',{}).get('rom',{}).get('sha256')!=sha(rom) or c.get('inputs',{}).get('core',{}).get('sha256')!=GENESIS_CORE_SHA:raise ValueError('wrong capture')
 sr=captured_file(a.capture,c,'native/receipt.json');src=json.loads(sr);checked_receipt(src,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 for f,mask in ((6420,64),(6480,2),(6540,2),(6600,128),(6660,2),(6720,2)):
  if scheduled_mask(src,f)!=mask:raise ValueError('unexpected source schedule')
 rr=(a.run/'receipt.json').read_bytes();r=json.loads(rr);checked_receipt(r,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 target_inputs=[{'start':100,'end':112,'buttons':['START']},{'start':130,'end':142,'buttons':['A']},{'start':190,'end':202,'buttons':['RIGHT']},{'start':220,'end':232,'buttons':['A']},{'start':250,'end':262,'buttons':['LEFT']},{'start':280,'end':292,'buttons':['A']},{'start':310,'end':322,'buttons':['RIGHT']},{'start':340,'end':352,'buttons':['A']}]
 if r.get('inputs')!=target_inputs or r.get('watches')!=[{'name':'state','offset':1792,'length':41}]:raise ValueError('unexpected target schedule')
 trace=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(trace,r);rows=[];bad=[]
 for sf,nf in ((6390,240),(6570,300),(6750,360)):
  source=captured_file(a.capture,c,f'native/scene-{sf:06d}/ram.bin');source=bytes(source[i^1] for i in range(len(source)));target=bytes.fromhex(frames[nf]['raw']['state'])
  if len(source)!=65536 or target[:2]!=b'SW' or target[22]&1:raise ValueError('invalid publication')
  x=[source[0x156],source[0x157],source[0x14e],source[0x176]];y=[target[32],target[33],target[34],target[31]]
  rows.append({'source_frame':sf,'target_frame':nf,'source':x,'target':y})
  if x!=y:bad.append(sf)
 result={'format':'fdisbull-shadowrun-play-reequip-1','fields':['weapon_slot','weapon_item','ammo','armor'],'rows':rows,'mismatches':bad,'source_capture_sha256':sha(cr),'source_receipt_sha256':sha(sr),'nes_sha256':sha(nes),'nes_receipt_sha256':sha(rr),'nes_trace_sha256':sha(trace),'scope':'original two-confirm route vs target one-confirm adapter, captured items only'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
