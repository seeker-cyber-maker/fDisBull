#!/usr/bin/env python3
"""Controlled original timer-decrement and pending-input scheduler checks."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_play import lift_play
from fdisbull.shadowrun_inventory import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 rom=a.rom.read_bytes();core=a.core.read_bytes()
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE:raise ValueError('wrong source/core')
 out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 out.mkdir(mode=0o700,parents=True)
 def run(name,c):
  path=out/(name+'.json');path.write_text(json.dumps(c));r=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',str(a.rom),'--core',str(a.core),'--contract',str(path),'--output',str(out/name)],capture_output=True,text=True,timeout=180)
  if r.returncode:raise RuntimeError(r.stderr[-3000:])
  v=json.loads((out/name/'receipt.json').read_text())
  if not v['complete'] or not v['inputs_unchanged']:raise ValueError('incomplete native run')
  return v
 cases=[]
 for timer in (1,2,37,32767):
  for pending in (0,1):
   for pressed in (0,1):cases.append((timer,pending,pressed))
 dec=[];route=[]
 for timer,pending,pressed in cases:
  dec.append({'name':f'{timer}-{pending}-{pressed}','registers':{'A0':0xff0100},'ram':[{'address':0xff01dc,'data':timer.to_bytes(2,'big').hex()}]})
  route.append({'name':f'{timer}-{pending}-{pressed}','registers':{'A0':0xff0100},'ram':[{'address':0xff01dc,'data':(timer-1).to_bytes(2,'big').hex()},{'address':0xffdfe6,'data':('ffff' if pending else '0000')},{'address':0xffdd22,'data':('4000' if pressed else '0000')}]})
 d=run('decrement',{'name':'timer-decrement','entry':0xa906,'code_ranges':[{'start':0xa906,'end':0xa912}],'stop_pcs':[0xa912],'max_instructions':5,'watch':[{'name':'timer','address':0xff01dc,'length':2}],'cases':dec})
 t=run('latch',{'name':'timer-latch','entry':0xad1a,'code_ranges':[{'start':0xad1a,'end':0xad3a}],'stop_pcs':[0xad36,0xae26],'max_instructions':10,'watch':[{'name':'latch','address':0xffdfe6,'length':2}],'cases':route})
 if len(d['cases'])!=len(cases) or len(t['cases'])!=len(cases):raise ValueError('incomplete cases')
 m=GameMachine(lift_play(rom),{0:rom});bad=[]
 for (timer,pending,pressed),dc,tc in zip(cases,d['cases'],t['cases']):
  m.set_state({'shadowrun_play_shot_armed':1,'shadowrun_play_shot_eligible':1,'shadowrun_play_shot_used':0,'shadowrun_play_shot_pending':pending,'shadowrun_play_shot_timer':timer,'shadowrun_field_motion_state':0,'shadowrun_play_refused':0})
  m.call('shadowrun_play_shot_step',64 if pressed else 0,64 if pressed else 0);s=m.snapshot()
  want_timer=int(dc['ram_after']['timer'],16);want_latch=bool(int(tc['ram_after']['latch'],16))
  if (s['shadowrun_play_shot_timer'],bool(s['shadowrun_play_shot_pending']))!=(want_timer,want_latch):bad.append(f'{timer}-{pending}-{pressed}')
 report={'format':'fdisbull-shadowrun-play-scheduler-check-1','cases':len(cases),'mismatches':bad,'rom_sha256':sha(rom),'core_sha256':sha(core),'decrement_trace_sha256':d['trace_sha256'],'latch_trace_sha256':t['trace_sha256'],'scope':'controlled nonnegative timer states and press latch; firing, underflow reset and actor scheduling separate'}
 (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
