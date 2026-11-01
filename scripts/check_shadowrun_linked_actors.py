#!/usr/bin/env python3
"""Compare captured-actor source-order projectile scans with original core."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_field_combat import ROM_SHA256
from fdisbull.shadowrun_linked_actors import lift_linked_actors
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run).resolve();capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);receipt=json.loads((root/'native/receipt.json').read_text())
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or receipt['patches'] or receipt['memory_injection_mode']!='no memory patches':raise ValueError('source mismatch')
 raw=(root/'native/scene-006037/ram.bin').read_bytes()
 if len(raw)!=65536 or cap['files']['native/scene-006037/ram.bin']['sha256']!=sha(raw):raise ValueError('capture mismatch')
 b=bytes(raw[i^1] for i in range(65536));w=lambda i:int.from_bytes(b[i:i+2],'big');projectile=b[0xb00:0xc00]
 actors=[bytearray(b[0x400+i*0x100:0x500+i*0x100]) for i in range(3)]
 for actor in actors:
  if (int.from_bytes(actor[14:16],'big'),actor[0x10],actor[0x4c],actor[0x4d],actor[0x76],actor[0x77],actor[0x78],actor[0x7b],actor[0x7c],actor[0x9b],actor[0x9e])!=(11,0x25,10,2,0,2,1,2,2,19,0x20):raise ValueError('actor profile mismatch')
 specs=[('first-only',[1,0,0],[0,0,0],[10,10,10],4,0),('second-only',[0,1,0],[0,0,0],[10,10,10],4,1),('third-only',[0,0,1],[0,0,0],[10,10,10],4,2),('ordered',[1,1,1],[0,0,0],[10,10,10],4,0),('skip-ineligible',[1,1,1],[128,0,0],[10,10,10],4,1),('skip-dead',[1,1,1],[0,0,0],[0,10,10],4,1),('no-live',[1,1,1],[0,0,0],[0,0,0],4,255),('zero-success',[1,1,1],[0,0,0],[10,10,10],0,0)]
 cases=[]
 for name,active,blocked,hps,effect,expected_slot in specs:
  records=[]
  for i,base in enumerate(actors):
   x=bytearray(base);x[:2]=(0x3ce0).to_bytes(2,'big');x[4:6]=(0x2e59).to_bytes(2,'big');x[0x10]=(0x25 if active[i] else 0x24);x[0xb0]=blocked[i];x[0x4c]=hps[i];records.append(x)
  pr=bytearray(projectile);pr[0x9f]=effect
  ram=[{'address':0xff0100,'data':b[0x100:0x200].hex()}]+[{'address':0xff0400+i*0x100,'data':x.hex()} for i,x in enumerate(records)]+[{'address':0xff0b00,'data':pr.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe000].hex()},{'address':0xffef00,'data':b[0xef00:0xf000].hex()},{'address':0xfff000,'data':b[0xf000:0xfe00].hex()}]
  cases.append({'name':name,'registers':{'A0':0xff0b00},'ram':ram})
 contract={'name':'ordered-captured-actor-scan','entry':0x14e0a,'code_ranges':[{'start':0x14e0a,'end':0x14edc},{'start':0x14f26,'end':0x14f86},{'start':0x15aba,'end':0x15bb4},{'start':0xe7c8,'end':0xe9cc},{'start':0x55948,'end':0x55b16},{'start':0x55e62,'end':0x55f44},{'start':0x55786,'end':0x55848},{'start':0xd3a,'end':0xdfc}], 'stop_pcs':[0x14e60,0x14e8a,0x14e30,0x14eda],'stack_scratch_bytes':128,'max_instructions':2000,
  'watch':[{'name':'projectile','address':0xff0b00,'length':256}]+[{'name':f'actor{i}','address':0xff0400+i*0x100,'length':256} for i in range(3)]+[{'name':'global_a','address':0xffdd00,'length':768},{'name':'global_b','address':0xffef00,'length':256},{'name':'global_c','address':0xfff000,'length':3584}],'cases':cases}
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged'] or len(r['cases'])!=len(specs):raise AssertionError('incomplete native')
 program=lift_linked_actors(rom);m=GameMachine(program,{0:rom})
 for spec,case in zip(specs,r['cases']):
  name,active,blocked,hps,effect,selected=spec
  m.set_state({'shadowrun_actors_profile':1,'shadowrun_linked_motion_state':1,'shadowrun_linked_motion_steps':4,'shadowrun_linked_motion_lifetime':projectile[0x89],'shadowrun_linked_x_fixed':int.from_bytes(projectile[:4],'big'),'shadowrun_linked_y_fixed':int.from_bytes(projectile[4:8],'big'),'shadowrun_linked_velocity_x':w(0xb4c),'shadowrun_linked_velocity_y':w(0xb4e),'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,'shadowrun_field_source_effect':effect,'shadowrun_field_rng':w(0xf9f8),'shadowrun_field_death_timer':b[0xf0ce],'shadowrun_field_type13_deaths':b[0xfbfa],'shadowrun_target_x':[0x3ce0]*3+[0]*4,'shadowrun_target_y':[0x2e59]*3+[0]*4,'shadowrun_target_flags':[(0x25 if x else 0x24) for x in active]+[0]*4,'shadowrun_target_flags_b0':blocked+[0]*4,'shadowrun_play_actor_hp':hps+[0]*4,'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(0xddd2),'shadowrun_y_max':w(0xddd4),'shadowrun_x_min':w(0xddd6),'shadowrun_y_min':w(0xddd8),'shadowrun_rect_base':0x172daa})
  m.call('shadowrun_actors_tick');s=m.snapshot();pr=bytes.fromhex(case['ram_after']['projectile']);g=bytes.fromhex(case['ram_after']['global_c']);native_hp=[bytes.fromhex(case['ram_after'][f'actor{i}'])[0x4c] for i in range(3)];got=(s['shadowrun_linked_x_fixed'],s['shadowrun_linked_y_fixed'],s['shadowrun_linked_motion_lifetime'],s['shadowrun_field_rng'],s['shadowrun_play_actor_hp'][:3]);observed=(int.from_bytes(pr[:4],'big'),int.from_bytes(pr[4:8],'big'),pr[0x89],int.from_bytes(g[0x9f8:0x9fa],'big'),native_hp)
  if not s['shadowrun_field_supported'] or s['shadowrun_actors_hit_slot']!=selected or got!=observed:raise AssertionError((name,s['shadowrun_actors_hit_slot'],selected,got,observed))
 summary={'status':'passed','cases':len(specs),'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_sha256':sha(capraw),'program_sha256':sha(canonical(program)),'trace_sha256':r['trace_sha256'],'scope':'assisted relocated captured actors; ordered collision scan and original projectile continuation; target AI and ordinary reachability excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
