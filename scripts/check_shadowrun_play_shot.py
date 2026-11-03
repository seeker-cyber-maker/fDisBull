#!/usr/bin/env python3
"""Compare one bounded NES shot to an instrumented original movement receipt."""
import argparse,hashlib,json
from pathlib import Path
from check_shadowrun_opening_route import captured_file,checked_receipt,NES_CORE_SHA,GENESIS_CORE_SHA,SOURCE_ROM_SHA,indexed_frames

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','source-run','source-comparison','nes','run','output'):p.add_argument('--'+n,required=True,type=Path)
 p.add_argument('--cancel-run',type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=a.nes.read_bytes()
 if sha(rom)!=SOURCE_ROM_SHA:raise ValueError('wrong source ROM')
 cr=(a.source_run/'capture.json').read_bytes();sr=(a.source_run/'native/receipt.json').read_bytes();s=json.loads(sr);checked_receipt(s,system='genesis',core_sha=GENESIS_CORE_SHA,rom_sha=sha(rom))
 comp_raw=a.source_comparison.read_bytes();comp=json.loads(comp_raw)
 if comp.get('status')!='passed' or len(comp.get('frames',[]))!=8 or comp.get('capture_sha256')!=sha(cr) or comp.get('receipt_sha256')!=sha(sr):raise ValueError('wrong original motion comparison')
 rr=(a.run/'receipt.json').read_bytes();r=json.loads(rr);checked_receipt(r,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 if r.get('inputs')!=[{'start':100,'end':102,'buttons':['A']}] or r.get('watches')!=[{'name':'state','offset':1792,'length':55}]:raise ValueError('unexpected target input or watch')
 raw=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(raw,r);observed={}
 for f in range(100,r['frames']):
  b=bytes.fromhex(frames[f]['raw']['state'])
  if len(b)!=55 or b[22]&1 or b[:2]!=b'SW':continue
  if b[43]==1 and b[44] in (1,3):
   key=b[46]
   if key not in observed:observed[key]=(f,b)
 mismatches=[];rows=[]
 for source in comp['frames']:
  n=source['steps']
  if n not in observed:mismatches.append({'source_frame':source['frame'],'field':'missing'});continue
  f,b=observed[n];values={'y_fixed':int.from_bytes(b[47:51],'little'),'lifetime':b[45],'state':b[44],'ammo':b[34],'rng':int.from_bytes(b[51:53],'little')}
  expected={'y_fixed':source['y_fixed'],'lifetime':source['lifetime'],'state':source['state'],'ammo':11,'rng':0x9d2f}
  rows.append({'source_frame':source['frame'],'target_frame':f,'expected':expected,'observed':values})
  if values!=expected:mismatches.append({'source_frame':source['frame'],'observed':values,'expected':expected})
 initial=bytes.fromhex(frames[100]['raw']['state']);launch=observed.get(4,(None,b''))[0]
 if initial[41]!=1 or int.from_bytes(initial[53:55],'little')!=36 or not launch or observed[4][1][23]!=(initial[23]+37)&255:raise ValueError('target delay did not complete 37 logical updates')
 timer_rows=[];capture=json.loads(cr);start_tick=initial[23]
 for sf in (6000,6036,6037,6040,6045):
  tick=(start_tick+sf-6000)&255
  matches=[(f,bytes.fromhex(frames[f]['raw']['state'])) for f in range(100,r['frames']) if bytes.fromhex(frames[f]['raw']['state'])[23]==tick and not bytes.fromhex(frames[f]['raw']['state'])[22]&1]
  if not matches:raise ValueError('missing scheduler publication')
  f,b=matches[0];mem=captured_file(a.source_run,capture,f'native/scene-{sf:06d}/ram.bin');mem=bytes(mem[i^1] for i in range(len(mem)))
  expected=[int.from_bytes(mem[0x1dc:0x1de],'big'),int.from_bytes(mem[0xdfe6:0xdfe8],'big')!=0]
  actual=[int.from_bytes(b[53:55],'little'),bool(b[41])];timer_rows.append({'source_frame':sf,'target_frame':f,'expected':expected,'observed':actual})
  if expected!=actual:mismatches.append({'source_frame':sf,'field':'timer or latch','expected':expected,'observed':actual})
 cancellation=None
 if a.cancel_run:
  crr=(a.cancel_run/'receipt.json').read_bytes();rc=json.loads(crr);checked_receipt(rc,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
  if rc.get('inputs')!=[{'start':100,'end':102,'buttons':['A']},{'start':110,'end':114,'buttons':['START']}] or rc.get('watches')!=[{'name':'state','offset':1792,'length':55}]:raise ValueError('unexpected cancellation inputs')
  ctr=(a.cancel_run/'ram_trace.json').read_bytes();cframes=indexed_frames(ctr,rc)
  pending=bytes.fromhex(cframes[105]['raw']['state']);cancel=bytes.fromhex(cframes[110]['raw']['state'])
  tail=[bytes.fromhex(cframes[f]['raw']['state']) for f in range(111,min(171,rc['frames']))]
  safe=(pending[41]==1 and cancel[2]==2 and cancel[26]==0 and cancel[41]==0 and cancel[34]==12 and all(b[34]==12 and b[42]==0 and b[44]==0 for b in tail))
  cancellation={'passed':safe,'receipt_sha256':sha(crr),'trace_sha256':sha(ctr)}
  if not safe:mismatches.append({'field':'pending shot cancellation'})
 result={'format':'fdisbull-shadowrun-play-shot-check-1','source_capture_sha256':sha(cr),'source_receipt_sha256':sha(sr),'source_comparison_sha256':sha(comp_raw),'nes_sha256':sha(nes),'nes_receipt_sha256':sha(rr),'nes_trace_sha256':sha(raw),'rows':rows,'scheduler':timer_rows,'cancellation':cancellation,'mismatches':mismatches,'scope':'one captured-profile adapted A shot; instrumented source observation, observer neutrality unestablished; no target hit or general firing'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f'{len(rows)} projectile states, {len(mismatches)} mismatches')
 if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
