#!/usr/bin/env python3
"""Compare 60 captured ordinary RIGHT updates with a prepared NES run."""
import argparse
import hashlib
import json
from pathlib import Path
from check_shadowrun_opening_route import (FIELDS,NES_CORE_SHA,GENESIS_CORE_SHA,SOURCE_ROM_SHA,
    captured_file,checked_receipt,indexed_frames,scheduled_mask)
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('source-rom','capture','nes','run','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 source=a.source_rom.read_bytes();nes=a.nes.read_bytes()
 if sha(source)!=SOURCE_ROM_SHA:raise ValueError('wrong source ROM')
 capture_raw=(a.capture/'capture.json').read_bytes();capture=json.loads(capture_raw)
 if (sha(capture_raw)!='b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c' or capture.get('assistance')!='ordinary controller schedule; no memory patches'):raise ValueError('wrong capture')
 src_receipt_raw=captured_file(a.capture,capture,'native/receipt.json');src_receipt=json.loads(src_receipt_raw)
 checked_receipt(src_receipt,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(source))
 rec_raw=(a.run/'receipt.json').read_bytes();rec=json.loads(rec_raw);checked_receipt(rec,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 if rec.get('watches')!=[{'name':'state','offset':1792,'length':41}]:raise ValueError('unexpected publication watch')
 raw=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(raw,rec);bad=[];hashes=[]
 for i in range(60):
  nf=100+i;sf=6000+i;row=frames[nf];state=bytes.fromhex(row['raw']['state'])
  if (len(state)!=41 or state[:4]!=b'SW\x01\x00' or state[22]&1 or row['input_mask']!=128 or scheduled_mask(rec,nf)!=128 or scheduled_mask(src_receipt,sf)!=128):raise ValueError('invalid stable publication or input')
  memory=captured_file(a.capture,capture,f'native/scene-{sf:06d}/ram.bin');hashes.append(sha(memory))
  for name,to,so in FIELDS:
   got=int.from_bytes(state[to:to+2],'little');want=int.from_bytes(memory[so:so+2],'little')
   if got!=want:bad.append({'frame':nf,'field':name,'source':want,'target':got})
 result={'format':'fdisbull-shadowrun-play-right-check-1','count':60,'fields':[x[0] for x in FIELDS],'mismatches':bad,'nes_sha256':sha(nes),'nes_receipt_sha256':sha(rec_raw),'nes_trace_sha256':sha(raw),'source_capture_sha256':sha(capture_raw),'source_receipt_sha256':sha(src_receipt_raw),'source_ram_sha256':hashes,'scope':'ordinary controller RIGHT, prepared target state, published fields; no full-scene equivalence'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f"60 source/target updates; {len(bad)} mismatches")
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
