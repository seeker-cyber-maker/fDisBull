#!/usr/bin/env python3
"""Compare no-overlap predicate against original actor collision scans."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_overlap import SOURCE,lift_enemy_overlap
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);rc=json.loads((root/'native/receipt.json').read_text());author=SOURCE.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or rc['patches'] or rc['memory_injection_mode']!='no memory patches':raise ValueError('identity or capture patches')
 cases=[];groups=[]
 for frame in cap['captures']:
  rel=f'native/scene-{frame:06d}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or cap['files'][rel]['sha256']!=sha(raw):raise ValueError('RAM mismatch')
  b=bytes(raw[i^1] for i in range(65536))
  for overlap in (False,True):
   actors=bytearray(b[0x100:0xb00])
   if overlap:
    actors[0x300:0x302]=(w(actors,0)+10).to_bytes(2,'big');actors[0x304:0x306]=(w(actors,4)+10).to_bytes(2,'big')
   if any((actors[i*256+0x10]&1) and (w(actors,i*256)<256 or w(actors,i*256+4)<256 or w(actors,i*256)>65279 or w(actors,i*256+4)>65279) for i in range(10)):continue
   before=len(cases)
   for i in range(10):
    if not actors[i*256+0x10]&1:continue
    cases.append({'name':f'{frame}-{int(overlap)}-{i}','registers':{'A0':0xff0100+i*256},'ram':[{'address':0xff0100,'data':actors.hex()}]})
   groups.append((frame,overlap,bytes(actors),before,len(cases)))
 contract={'name':'captured-actor-no-overlap','entry':0xeb92,'code_ranges':[{'start':0xeb92,'end':0xec4c},{'start':0xecbc,'end':0xeccc}], 'stop_pcs':[0xeb9c,0xeba8,0xec4a,0xecca], 'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'actors','address':0xff0100,'length':2560}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text());assert r['complete'] and r['inputs_unchanged'] and len(r['cases'])==len(cases)
 prog=lift_enemy_overlap(rom);m=GameMachine(prog,{});clear=blocked=0
 for frame,forced,actors,start,end in groups:
  m.set_state({'shadowrun_ai_overlap_flags':[actors[i*256+0x10] for i in range(10)],'shadowrun_ai_overlap_x':[w(actors,i*256) for i in range(10)],'shadowrun_ai_overlap_y':[w(actors,i*256+4) for i in range(10)],'shadowrun_ai_overlap_target':[l(actors,i*256+0xa2) for i in range(10)],'shadowrun_ai_overlap_attacker':[l(actors,i*256+0xac) for i in range(10)]})
  m.call('shadowrun_ai_overlap_check');s=m.snapshot();native=r['cases'][start:end];pcs=[x['registers_after']['PC'] for x in native]
  if any(pc not in (0xeb9c,0xeba8,0xec4a,0xecca) for pc in pcs):raise AssertionError((frame,pcs))
  hit=0xec4a in pcs
  if bool(s['shadowrun_ai_overlap_supported'])==hit:raise AssertionError((frame,forced,hit,s['shadowrun_ai_overlap_supported']))
  if hit:blocked+=1
  else:clear+=1
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 result={'status':'passed','groups':len(groups),'original_actor_scans':len(cases),'clear_matched':clear,'overlap_refused':blocked,'rom_sha256':sha(rom),'core_sha256':sha(core),'source_capture_sha256':sha(capraw),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'trace_sha256':r['trace_sha256'],'scope':'captured ten-actor source-order scans, plus controlled player/NPC overlap placement; overlap response excluded'}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
