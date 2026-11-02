#!/usr/bin/env python3
"""Assisted collision against an original captured actor, including depletion."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_field_combat import ROM_SHA256
from fdisbull.shadowrun_hostile_received_hit import lift_hostile_received_hit
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for flag in ('rom','core','run','hostile','output'):p.add_argument('--'+flag,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run).resolve();capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);r=json.loads((root/'native/receipt.json').read_text())
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or r['patches'] or r['memory_injection_mode']!='no memory patches':raise ValueError('source identity or patch mismatch')
 raw=(root/'native/scene-006037/ram.bin').read_bytes();entry=cap['files']['native/scene-006037/ram.bin']
 if len(raw)!=65536 or entry['sha256']!=sha(raw):raise ValueError('source capture mismatch')
 b=bytes(raw[i^1] for i in range(65536));w=lambda i:int.from_bytes(b[i:i+2],'big');proj=b[0xb00:0xc00];player=bytearray(b[0x100:0x200]);hostile_path=Path(a.hostile);hostile_raw=hostile_path.read_bytes();hostile_receipt_raw=(hostile_path.parent/'receipt.json').read_bytes();hostile_receipt=json.loads(hostile_receipt_raw);
 if not hostile_receipt['complete'] or not hostile_receipt['inputs_unchanged'] or hostile_receipt['source_sha256']!=ROM_SHA256 or hostile_receipt['core_sha256']!=CORE or sha(hostile_raw)!=hostile_receipt['cases'][0]['ram_before_sha256']:raise ValueError('hostile constructor provenance')
 actor=hostile_raw[0x400:0x500]
 if (int.from_bytes(proj[4:8],'big'),proj[0x89],proj[0x9f],w(0xf9f8))!=(0x2df9fc00,123,4,0x9d2f):raise ValueError('captured projectile mismatch')
 if (int.from_bytes(actor[14:16],'big'),actor[0x10],actor[0x3f],actor[0x4c],actor[0x4d],actor[0x76],actor[0x77],actor[0x78],actor[0x7b],actor[0x7c],actor[0x9b],actor[0x9e])!=(8,0x05,3,10,2,3,5,5,4,3,2,0):raise ValueError('captured actor mismatch')
 cases=[]
 for hp in (1,4,5,10):
  for timer in (0,4):
   for deaths in (7,):
    for override in (0,128):
     for shot in (4,7):
      target=bytearray(actor);target[:2]=(0x3ce0).to_bytes(2,'big');target[4:6]=(0x2e59).to_bytes(2,'big');target[0x4c]=hp;target[0x9a]=override
      globals_=bytearray(b[0xf000:0xfe00]);globals_[0xce]=timer;globals_[0xbfa]=deaths
      p1=bytearray(player);p1[0x8d]=254
      projectile=bytearray(proj);projectile[0x9f]=shot
      cases.append({'name':f'{hp}-{timer}-{deaths}-{override}-{shot}', 'registers':{'A0':0xff0b00},
       'ram':[{'address':0xff0100,'data':p1.hex()},{'address':0xff028d,'data':'ff'},{'address':0xff038d,'data':'00'},
        {'address':0xff0400,'data':target.hex()},{'address':0xff0b00,'data':projectile.hex()},
        {'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe000].hex()},
        {'address':0xffef00,'data':b[0xef00:0xf000].hex()},{'address':0xfff000,'data':globals_.hex()}]})
 contract={'name':'assisted-captured-actor-hit','entry':0x14e0a,
  'code_ranges':[{'start':0x14e0a,'end':0x14edc},{'start':0x14f26,'end':0x14f86},{'start':0x15aba,'end':0x15bb4},{'start':0xe7c8,'end':0xe9cc},{'start':0x55948,'end':0x55b16},{'start':0x55e62,'end':0x55f44},{'start':0x55786,'end':0x55848},{'start':0xd3a,'end':0xdfc}],
  'stop_pcs':[0x14e60,0x14e8a,0x14e30,0x14eda],'stack_scratch_bytes':128,'max_instructions':1500,
  'watch':[{'name':'projectile','address':0xff0b00,'length':256},{'name':'target','address':0xff0400,'length':256},{'name':'global_a','address':0xffdd00,'length':768},{'name':'global_b','address':0xffef00,'length':256},{'name':'global_c','address':0xfff000,'length':3584},{'name':'counter_a','address':0xff018d,'length':1},{'name':'counter_b','address':0xff028d,'length':1},{'name':'counter_c','address':0xff038d,'length':1}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract))
 q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 native=json.loads((out/'native'/'receipt.json').read_text())
 if not native['complete'] or not native['inputs_unchanged'] or len(native['cases'])!=len(cases):raise AssertionError('incomplete native probe')
 program=lift_hostile_received_hit(rom);m=GameMachine(program,{0:rom})
 for inp,case in zip(cases,native['cases']):
  hp,timer,deaths,override,shot=map(int,inp['name'].split('-'))
  if case['registers_after']['PC']!=(0x14e60 if shot == 0 else 0x14e8a):raise AssertionError(('no hit',inp['name']))
  m.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,'shadowrun_field_slots_busy':0,'shadowrun_field_target_flags':0x05,'shadowrun_field_target_flags_b0':0,'shadowrun_field_target_flags_9e':0,'shadowrun_field_target_flags_9a':override,'shadowrun_field_target_type':2,'shadowrun_field_target_defense_bonus':5,'shadowrun_field_death_timer':timer,'shadowrun_field_type13_deaths':deaths,'shadowrun_field_party_counter_a':254,'shadowrun_field_party_counter_b':255,'shadowrun_field_party_counter_c':0,'shadowrun_field_target_x':0x3ce0,'shadowrun_field_target_y':0x2e59,'shadowrun_field_projectile_x':0x3ce0,'shadowrun_field_projectile_y':0x2e59,'shadowrun_hostile_received_profile':1,'shadowrun_hostile_received_kind':8,'shadowrun_hostile_received_armor':3,'shadowrun_field_target_hp':hp,'shadowrun_field_target_a':5,'shadowrun_field_target_b':4,'shadowrun_field_target_c':3,'shadowrun_field_target_posture':2,'shadowrun_field_source_effect':shot,'shadowrun_field_rng':w(0xf9f8)})
  m.call('shadowrun_hostile_received_hit');s=m.snapshot();pr=bytes.fromhex(case['ram_after']['projectile']);tar=bytes.fromhex(case['ram_after']['target']);g=bytes.fromhex(case['ram_after']['global_c'])
  observed=(tar[0x4c],int.from_bytes(g[0x9f8:0x9fa],'big'),g[0xce],g[0xbfa],int(case['ram_after']['counter_a'],16),int(case['ram_after']['counter_b'],16),int(case['ram_after']['counter_c'],16))
  got=tuple(s[k] for k in ('shadowrun_field_target_hp','shadowrun_field_rng','shadowrun_field_death_timer','shadowrun_field_type13_deaths','shadowrun_field_party_counter_a','shadowrun_field_party_counter_b','shadowrun_field_party_counter_c'))
  if not s['shadowrun_hostile_received_supported'] or got!=observed:raise AssertionError((inp['name'],got,observed))

 summary={'status':'passed','cases':len(cases),'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_sha256':sha(capraw),'source_ram_sha256':sha(raw),'hostile_ram_sha256':sha(hostile_raw),'hostile_receipt_sha256':sha(hostile_receipt_raw),'authoring_sha256':sha((ROOT/'src/fdisbull/game_sources/shadowrun_hostile_received_hit.c').read_bytes()),'program_sha256':sha(canonical(program)),'trace_sha256':native['trace_sha256'],'scope':'prepared kind8/type2 actor relocated to captured projectile path; controlled HP/override/globals and positive hit effect; source armor item3, normal reachability excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
