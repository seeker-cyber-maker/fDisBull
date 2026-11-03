#!/usr/bin/env python3
"""Compare projectile retirement gate with controlled original core entry."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_projectile_lifecycle import SOURCE,lift_projectile_lifecycle
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();source=SOURCE.read_bytes()
 if sha(core)!=CORE:raise ValueError('wrong core')
 m=GameMachine(lift_projectile_lifecycle(rom),{});out=_private_directory(a.output);out.mkdir(mode=0o700)
 count=0;traces=[]
 for mode in ('primary','secondary'):
  cases=[]
  for animation in (0,1,0x7fff,0x8000,0xffff):
   for flags in (0,1,9,255):
    actor=bytearray(0x42);actor[0x10]=flags;actor[0x16:0x18]=animation.to_bytes(2,'big');actor[0x41]=0
    cases.append({'name':f'{animation}-{flags}','registers':{'A0':0xff0100},'ram':[{'address':0xff0100,'data':actor.hex()}]})
  ranges=([{'start':0x14f1c,'end':0x14f26},{'start':0x14f86,'end':0x14f9a},{'start':0x14ff0,'end':0x14ff8}] if mode=='primary' else [{'start':0xac4e,'end':0xac5e}])
  contract={'name':mode,'entry':0x14f1c if mode=='primary' else 0xac4e,'code_ranges':ranges,'max_instructions':30,'watch':[{'name':'actor','address':0xff0100,'length':66}],'cases':cases}
  cp=out/(mode+'.json');cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/(mode+'-native'))],capture_output=True,text=True,timeout=180)
  if q.returncode:raise RuntimeError(q.stderr[-4000:])
  r=json.loads((out/(mode+'-native')/'receipt.json').read_text())
  if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(cases):raise AssertionError('incomplete probe')
  for inp,case in zip(cases,r['cases']):
   animation,flags=map(int,inp['name'].split('-'));m.set_state({'shadowrun_lifecycle_animation':animation,'shadowrun_lifecycle_flags':flags,'shadowrun_lifecycle_repeat':0});m.call('shadowrun_lifecycle_'+mode);s=m.snapshot();target=bytes.fromhex(case['ram_after']['actor'])
   if not s['shadowrun_lifecycle_supported'] or (s['shadowrun_lifecycle_flags'],s['shadowrun_lifecycle_repeat'])!=(target[0x10],target[0x41]):raise AssertionError((mode,inp['name']))
  count+=len(cases);traces.append(r['trace_sha256'])
 if SOURCE.read_bytes()!=source or Path(a.rom).read_bytes()!=rom or Path(a.core).read_bytes()!=core:raise ValueError('input changed')
 summary={'status':'passed','cases':count,'rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(source),'trace_sha256':traces,'scope':'primary and secondary active-bit retirement given original animation word; animation generation and positive-repeat rearm excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
