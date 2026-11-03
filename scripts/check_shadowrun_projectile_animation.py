#!/usr/bin/env python3
"""Compare bounded projectile descriptor/accumulator animation with original."""
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
 def run(name,c):
  cp=out/(name+'.json');cp.write_text(json.dumps(c));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/(name+'-native'))],capture_output=True,text=True,timeout=180)
  if q.returncode:raise RuntimeError(q.stderr[-4000:])
  r=json.loads((out/(name+'-native')/'receipt.json').read_text())
  if not r['complete'] or not r['inputs_unchanged']:raise AssertionError('incomplete probe')
  return r
 cases=[]
 for frame in (0,1,2):
  for accumulator in (0,14,2048,4095):
   for flags in (0,8):
    actor=bytearray(0x20);actor[0xe:0x10]=bytes.fromhex('0001');actor[0x11]=flags;actor[0x18:0x1a]=bytes.fromhex('0800');actor[0x1a:0x1c]=accumulator.to_bytes(2,'big');actor[0x1c:0x1e]=bytes.fromhex('1000');actor[0x1e:0x20]=frame.to_bytes(2,'big')
    cases.append({'name':f'{frame}-{accumulator}-{flags}','registers':{'A0':0xff0100},'ram':[{'address':0xff0100,'data':actor.hex()}]})
 advance=run('advance',{'name':'projectile-accumulator','entry':0x5fdc,'code_ranges':[{'start':0x5fdc,'end':0x600e}],'max_instructions':25,'watch':[{'name':'actor','address':0xff0100,'length':32},{'name':'scratch','address':0xffdd3c,'length':4}],'cases':cases})
 descriptor_cases=[{'name':c['name'],'registers':{'A0':0xff0100},'ram':[{'address':0xff0100,'data':v['ram_after']['actor']}]} for c,v in zip(cases,advance['cases'])]
 desc=run('descriptor',{'name':'projectile-descriptor','entry':0x600e,'code_ranges':[{'start':0x600e,'end':0x60b0}],'stop_pcs':[0x60ae],'max_instructions':30,'watch':[{'name':'actor','address':0xff0100,'length':32}],'cases':descriptor_cases})
 if len(desc['cases'])!=len(cases) or len(advance['cases'])!=len(cases):raise AssertionError('case count')
 for inp,case in zip(cases,desc['cases']):
  frame,accum,flags=map(int,inp['name'].split('-'));m.set_state({'shadowrun_lifecycle_profile':1,'shadowrun_lifecycle_animation':0,'shadowrun_lifecycle_frame':frame,'shadowrun_lifecycle_accumulator':accum,'shadowrun_lifecycle_flags_low':flags});m.call('shadowrun_lifecycle_animate');s=m.snapshot();x=bytes.fromhex(case['ram_after']['actor']);w=lambda i:int.from_bytes(x[i:i+2],'big');got=(s['shadowrun_lifecycle_animation'],s['shadowrun_lifecycle_frame'],s['shadowrun_lifecycle_accumulator'],s['shadowrun_lifecycle_flags_low']);observed=(w(0x16),w(0x1e),w(0x1a),x[0x11])
  if not s['shadowrun_lifecycle_supported'] or got!=observed:raise AssertionError((inp['name'],got,observed))
 if SOURCE.read_bytes()!=source or Path(a.rom).read_bytes()!=rom or Path(a.core).read_bytes()!=core:raise ValueError('input changed')
 summary={'status':'passed','cases':len(cases),'rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(source),'trace_sha256':[advance['trace_sha256'],desc['trace_sha256']],'scope':'controlled $5FDC accumulator then $600E type1 descriptor boundary; source service scheduling and presentation excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
