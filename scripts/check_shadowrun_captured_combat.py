#!/usr/bin/env python3
"""Compare an assisted captured-player shot/effect composition with original CPU.

Uses two independent controlled entries with prepared projectile collision; does
not qualify ordinary input, projectile motion, allocation effects, or NES timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_field_combat import SOURCE, lift_field_combat
CAPTURE='b5872bdca05e98203f81cd5bdfdd4dd82d8a9f516ee694be01a15d1ba0ce0417'
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b): return hashlib.sha256(b).hexdigest()

def main():
 p=argparse.ArgumentParser()
 for flag in ('rom','core','capture-ram','output'): p.add_argument('--'+flag,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();raw=Path(a.capture_ram).read_bytes();author=SOURCE.read_bytes()
 if sha(raw)!=CAPTURE or sha(core)!=CORE: raise ValueError('capture or core identity mismatch')
 actor=bytes(raw[(0x100+i)^1] for i in range(256))
 if (actor[0x3e:0x40],actor[0x10],actor[0x4e],actor[0x56],actor[0x57])!=(b'\x00\x00',15,12,0,2): raise ValueError('capture profile mismatch')
 m=GameMachine(lift_field_combat(rom),{});out=_private_directory(a.output);out.mkdir(mode=0o700)
 def run(name,contract):
  path=out/(name+'-contract.json');path.write_text(json.dumps(contract))
  q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(path),'--output',str(out/name)],capture_output=True,text=True,timeout=180)
  if q.returncode: raise RuntimeError(q.stderr[-4000:])
  r=json.loads((out/name/'receipt.json').read_text())
  if not r['complete'] or not r['inputs_unchanged']:raise AssertionError('incomplete native run')
  return r
 shot_cases=[{'name':str(seed),'registers':{'A0':0xff0100,'A1':0xff0b00},'ram':[{'address':0xff0100,'data':actor.hex()},{'address':0xfff9f8,'data':seed.to_bytes(2,'big').hex()}]} for seed in range(1,41)]
 shot=run('shot',{'name':'captured-player-shot-roll','entry':0x55640,
  'code_ranges':[{'start':0x55640,'end':0x55848},{'start':0x55ed6,'end':0x55f44},{'start':0x12c74,'end':0x12cd6},{'start':0xd3a,'end':0xdfc}],
  'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'source','address':0xff0100,'length':256},{'name':'projectile','address':0xff0b00,'length':256},{'name':'globals','address':0xfff000,'length':4096}],'cases':shot_cases})
 hit_cases=[]
 for index,case in enumerate(shot['cases'],1):
  source=bytearray(0xa0); source[0x57]=2; source[0x9f]=bytes.fromhex(case['ram_after']['projectile'])[0x9f]
  target=bytearray(0xa0);target[0x3f]=3;target[0x4c]=50
  target[0x78]=target[0x7b]=target[0x7c]=5
  glob=bytes.fromhex(case['ram_after']['globals']);rng=glob[0x9f8:0x9fa]
  hit_cases.append({'name':str(index),'registers':{'A0':0xff0100,'A1':0xff0200},'ram':[{'address':0xff0100,'data':source.hex()},{'address':0xff0200,'data':target.hex()},{'address':0xfff9f8,'data':rng.hex()}]})
 hit=run('hit',{'name':'prepared-projectile-hit','entry':0x14e6e,
  'code_ranges':[{'start':0x14e6e,'end':0x14e88},{'start':0x55948,'end':0x55b16},{'start':0x55e62,'end':0x55f44},{'start':0x55786,'end':0x55848},{'start':0xd3a,'end':0xdfc}],
  'stop_pcs':[0x14e88],'stack_scratch_bytes':128,'max_instructions':1000,'watch':[{'name':'source','address':0xff0100,'length':160},{'name':'target','address':0xff0200,'length':160},{'name':'globals','address':0xfff000,'length':4096}],'cases':hit_cases})
 for seed,(shot_case,hit_case) in enumerate(zip(shot['cases'],hit['cases']),1):
  m.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':12,'shadowrun_field_slots_busy':0,'shadowrun_field_projectile_x':512,'shadowrun_field_projectile_y':512,'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,'shadowrun_field_target_flags':1,'shadowrun_field_target_flags_b0':0,'shadowrun_field_target_flags_9e':0,'shadowrun_field_target_hp':50,'shadowrun_field_target_a':5,'shadowrun_field_target_b':5,'shadowrun_field_target_c':5,'shadowrun_field_target_posture':0,'shadowrun_field_rng':seed})
  m.call('shadowrun_field_captured_fire');s=m.snapshot()
  hp=bytes.fromhex(hit_case['ram_after']['target'])[0x4c]
  rng=int.from_bytes(bytes.fromhex(hit_case['ram_after']['globals'])[0x9f8:0x9fa],'big')
  effect=bytes.fromhex(shot_case['ram_after']['projectile'])[0x9f]
  if not s['shadowrun_field_supported'] or (s['shadowrun_field_target_hp'],s['shadowrun_field_rng'],s['shadowrun_field_source_effect'],s['shadowrun_field_ammo'])!=(hp,rng,effect,11):
   raise AssertionError((seed,s['shadowrun_field_target_hp'],hp,s['shadowrun_field_rng'],rng))
 if any((Path(a.rom).read_bytes()!=rom,Path(a.core).read_bytes()!=core,Path(a.capture_ram).read_bytes()!=raw,SOURCE.read_bytes()!=author)):raise ValueError('input changed')
 summary={'status':'passed','cases':len(hit_cases),'capture_sha256':sha(raw),'rom_sha256':sha(rom),'core_sha256':sha(core),'authoring_sha256':sha(author),'shot_trace_sha256':shot['trace_sha256'],'hit_trace_sha256':hit['trace_sha256'],'scope':'assisted captured-source shot plus separately prepared target hit; input dispatch, projectile movement, allocation side effects, HUD and NES runtime excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
