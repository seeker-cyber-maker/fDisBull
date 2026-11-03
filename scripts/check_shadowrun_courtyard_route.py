#!/usr/bin/env python3
"""Compare a source-only calm courtyard route to existing actor services."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import canonical
from fdisbull.shadowrun_ai_play import actor_service_from_capture
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','snapshot','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or r['patches']:raise ValueError('source identity or unpatched capture mismatch')
 expected=[(6000,6060,'LEFT'),(6080,6101,'UP'),(6120,6180,'RIGHT'),(6200,6260,'DOWN'),(6280,6340,'LEFT'),(6360,6420,'UP')]
 if [(x['start'],x['end'],x['buttons'][0]) for x in r['inputs'] if x['start']>=6000]!=expected:raise ValueError('controller schedule mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 m=actor_service_from_capture(rom,a.snapshot);matched=[];stop=None
 for f in range(6000,6451):
  pad=next(({'LEFT':4,'UP':1,'RIGHT':8,'DOWN':2}[direction] for start,end,direction in expected if start<=f<end),0)
  m.call('shadowrun_ai_frame',pad);s=m.snapshot()
  if s['shadowrun_ai_slot_status'][:3]!=[1,1,1]:stop={'frame':f,'reason':'actor service refused','slot_status':s['shadowrun_ai_slot_status'][:3]};break
  rel=f'native/scene-{f:06}/ram.bin'
  if rel not in cap['files']:continue
  b=frame(f);w=lambda o:int.from_bytes(b[o:o+2],'big');got=(s['shadowrun_player_x'],s['shadowrun_player_y'],*[x for pair in zip(s['shadowrun_target_x'][:3],s['shadowrun_target_y'][:3]) for x in pair]);exp=(w(0x100),w(0x104),*[w(0x400+i*256+j) for i in range(3) for j in (0,4)])
  if got!=exp:stop={'frame':f,'reason':'source position mismatch','actual':got,'expected':exp};break
  matched.append(f)
 result={'status':'bounded' if stop else 'passed','matched_source_checkpoints':len(matched),'last_matched_frame':matched[-1] if matched else None,'first_boundary':stop,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'program_sha256':sha(canonical(m.program)),'scope':'unpatched scene-2 original controller route; player and three actor positions; unobserved frames checked for model refusal but not independently sampled'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
