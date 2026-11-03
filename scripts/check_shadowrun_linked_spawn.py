#!/usr/bin/env python3
"""Compare source projectile spawn vector tables with the original core."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_linked_heading import SPAWN_SOURCE,lift_linked_spawn
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();source=SPAWN_SOURCE.read_bytes()
 if sha(core)!=CORE:raise ValueError('wrong core')
 m=GameMachine(lift_linked_spawn(rom),{0:rom});out=_private_directory(a.output);out.mkdir(mode=0o700)
 cases=[]
 for angle in list(range(0,65536,256))+[0x37ff,0x3fff,0xffff]:
  actor=bytearray(256);actor[:2]=(19200).to_bytes(2,'big');actor[4:6]=(12800).to_bytes(2,'big');actor[0x2e:0x30]=angle.to_bytes(2,'big');actor[0x10]=15
  cases.append({'name':str(angle),'registers':{'A0':0xff0100,'A1':0xff0b00,'D0':9,'D3':0},'ram':[{'address':0xff0100,'data':actor.hex()},{'address':0xffdfd8,'data':'0001'}]})
 c={'name':'spawn-vectors','entry':0x14ff8,'code_ranges':[{'start':0x14ff8,'end':0x1514e}], 'stack_scratch_bytes':128,'max_instructions':500,'watch':[{'name':'projectile','address':0xff0b00,'length':256},{'name':'global','address':0xffdd60,'length':4}],'cases':cases}
 cp=out/'contract.json';cp.write_text(json.dumps(c));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(cases):raise AssertionError('incomplete original probe')
 for original,case in zip(cases,r['cases']):
  angle=int(original['name']);m.set_state({'shadowrun_spawn_source_x':19200,'shadowrun_spawn_source_y':12800,'shadowrun_spawn_heading':angle});m.call('shadowrun_linked_spawn');s=m.snapshot();projectile=bytes.fromhex(case['ram_after']['projectile']);glob=bytes.fromhex(case['ram_after']['global']);w=lambda b,i:int.from_bytes(b[i:i+2],'big')
  got=tuple(s[k] for k in ('shadowrun_spawn_x','shadowrun_spawn_y','shadowrun_spawn_secondary_x','shadowrun_spawn_secondary_y','shadowrun_spawn_velocity_x','shadowrun_spawn_velocity_y'));expected=(w(projectile,0),w(projectile,4),w(glob,0),w(glob,2),w(projectile,0x4c),w(projectile,0x4e))
  if not s['shadowrun_spawn_supported'] or got!=expected:raise AssertionError((original['name'],got,expected))
 if SPAWN_SOURCE.read_bytes()!=source or Path(a.rom).read_bytes()!=rom or Path(a.core).read_bytes()!=core:raise ValueError('input changed')
 summary={'status':'passed','cases':len(cases),'rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(source),'trace_sha256':r['trace_sha256'],'scope':'controlled source spawn position and vector from given heading; allocation, target motion and projectile flight excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
