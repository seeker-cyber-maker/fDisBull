#!/usr/bin/env python3
"""Compare assisted relocated actor hit from captured linked projectile."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_field_combat import ROM_SHA256
from fdisbull.shadowrun_hostile_linked import SOURCE,lift_hostile_linked
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for flag in ('rom','core','run','hostile','output'):p.add_argument('--'+flag,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run).resolve();cr=(root/'capture.json').read_bytes();cap=json.loads(cr);receipt=json.loads((root/'native/receipt.json').read_text())
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or not receipt['patches'] or any(x['frame']!=6000 for x in receipt['patches']):raise ValueError('source or assistance mismatch')
 expected_patches={(256,'004b'),(260,'0032'),(56774,'8042'),(56776,'002b'),(56584,'18ff'),(56586,'9800'),(56588,'18ff'),(56590,'9800'),(57144,'8042'),(57142,'002b')}
 if len(receipt['patches'])!=len(expected_patches) or any(x['memory_id']!=2 for x in receipt['patches']) or {(x['offset'],x['data_hex']) for x in receipt['patches']}!=expected_patches:raise ValueError('unexpected assisted intervention')
 raw=(root/'native/scene-006090/ram.bin').read_bytes();item=cap['files']['native/scene-006090/ram.bin']
 if len(raw)!=65536 or item['sha256']!=sha(raw):raise ValueError('captured source mismatch')
 b=bytes(raw[i^1] for i in range(65536));w=lambda i:int.from_bytes(b[i:i+2],'big');pr=b[0xb00:0xc00];hostile_path=Path(a.hostile);hostile_raw=hostile_path.read_bytes();hostile_receipt_raw=(hostile_path.parent/'receipt.json').read_bytes();hostile_receipt=json.loads(hostile_receipt_raw);
 if not hostile_receipt['complete'] or not hostile_receipt['inputs_unchanged'] or hostile_receipt['source_sha256']!=ROM_SHA256 or hostile_receipt['core_sha256']!=CORE or sha(hostile_raw)!=hostile_receipt['cases'][0]['ram_before_sha256']:raise ValueError('hostile constructor provenance')
 actor=hostile_raw[0x400:0x500]
 if (int.from_bytes(pr[:4],'big'),int.from_bytes(pr[4:8],'big'),pr[0x89],pr[0x9f],w(0xb4c),w(0xb4e),b[0x54c],w(0xf9f8))!=(0x4ea7a800,0x318f5000,119,4,0x5ef5,0xf1ea,10,0x9d2f):raise ValueError('source projectile/actor mismatch')
 target=bytearray(actor);target[:2]=(0x4f06).to_bytes(2,'big');target[4:6]=(0x3181).to_bytes(2,'big')
 contract={'name':'linked-projectile-placed-captured-actor','entry':0x14e0a,
  'code_ranges':[{'start':0x14e0a,'end':0x14edc},{'start':0x14f26,'end':0x14f86},{'start':0x15aba,'end':0x15bb4},{'start':0xe7c8,'end':0xe9cc},{'start':0x55948,'end':0x55b16},{'start':0x55e62,'end':0x55f44},{'start':0x55786,'end':0x55848},{'start':0xd3a,'end':0xdfc}],
  'stop_pcs':[0x14e60,0x14e8a,0x14e30,0x14eda],'stack_scratch_bytes':128,'max_instructions':2000,
  'cases':[] ,
  'watch':[{'name':'counter_a','address':0xff018d,'length':1},{'name':'counter_b','address':0xff028d,'length':1},{'name':'counter_c','address':0xff038d,'length':1},{'name':'projectile','address':0xff0b00,'length':256},{'name':'target','address':0xff0500,'length':256},{'name':'global_a','address':0xffdd00,'length':768},{'name':'global_b','address':0xffef00,'length':256},{'name':'global_c','address':0xfff000,'length':3584}]}
 for hp in (1,4,10):
  for effect in (0,4,7):
   projectile=bytearray(pr);projectile[0x9f]=effect;placed=bytearray(target);placed[0x4c]=hp
   contract['cases'].append({'name':f'{hp}-{effect}','registers':{'A0':0xff0b00},'ram':[{'address':0xff0100,'data':b[0x100:0x200].hex()},{'address':0xff028d,'data':b[0x28d:0x28e].hex()},{'address':0xff038d,'data':b[0x38d:0x38e].hex()},{'address':0xff0500,'data':placed.hex()},{'address':0xff0b00,'data':projectile.hex()},{'address':0xff1700,'data':b[0x1700:0x2200].hex()},{'address':0xffdd00,'data':b[0xdd00:0xe000].hex()},{'address':0xffef00,'data':b[0xef00:0xf000].hex()},{'address':0xfff000,'data':b[0xf000:0xfe00].hex()}]})
 out=_private_directory(a.output);out.mkdir(mode=0o700);cp=out/'contract.json';cp.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(ROOT/'scripts/probe_genesis_function.py'),'--rom',a.rom,'--core',a.core,'--contract',str(cp),'--output',str(out/'native')],capture_output=True,text=True,timeout=180)
 if q.returncode:raise RuntimeError(q.stderr[-4000:])
 r=json.loads((out/'native/receipt.json').read_text())
 if not r['complete'] or not r['inputs_unchanged']:raise AssertionError('native failure')
 program=lift_hostile_linked(rom);m=GameMachine(program,{0:rom})
 for inp,case in zip(contract['cases'],r['cases']):
  hp,effect=map(int,inp['name'].split('-'))
  if case['registers_after']['PC']!=(0x14e60 if effect==0 else 0x14e8a):raise AssertionError(('no hit',inp['name']))
  m.set_state({'shadowrun_hostile_received_profile':1,'shadowrun_hostile_received_kind':8,'shadowrun_hostile_received_armor':3,'shadowrun_linked_profile':1,'shadowrun_linked_motion_state':1,'shadowrun_linked_motion_steps':8,'shadowrun_linked_motion_lifetime':pr[0x89],'shadowrun_linked_x_fixed':int.from_bytes(pr[:4],'big'),'shadowrun_linked_y_fixed':int.from_bytes(pr[4:8],'big'),'shadowrun_linked_velocity_x':w(0xb4c),'shadowrun_linked_velocity_y':w(0xb4e),'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,'shadowrun_field_target_flags':actor[0x10],'shadowrun_field_target_flags_b0':actor[0xb0],'shadowrun_field_target_flags_9e':actor[0x9e],'shadowrun_field_target_flags_9a':actor[0x9a],'shadowrun_field_target_type':actor[0x9b],'shadowrun_field_target_defense_bonus':actor[0x77],'shadowrun_field_target_x':0x4f06,'shadowrun_field_target_y':0x3181,'shadowrun_field_target_hp':hp,'shadowrun_field_target_a':actor[0x78],'shadowrun_field_target_b':actor[0x7b],'shadowrun_field_target_c':actor[0x7c],'shadowrun_field_target_posture':actor[0x4d],'shadowrun_field_source_effect':effect,'shadowrun_field_rng':w(0xf9f8),'shadowrun_field_death_timer':b[0xf0ce],'shadowrun_field_type13_deaths':b[0xfbfa],'shadowrun_field_party_counter_a':b[0x18d],'shadowrun_field_party_counter_b':b[0x28d],'shadowrun_field_party_counter_c':b[0x38d],'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(0xddd2),'shadowrun_y_max':w(0xddd4),'shadowrun_x_min':w(0xddd6),'shadowrun_y_min':w(0xddd8),'shadowrun_rect_base':0x172daa})
  m.call('shadowrun_hostile_linked_tick');s=m.snapshot();npr=bytes.fromhex(case['ram_after']['projectile']);nt=bytes.fromhex(case['ram_after']['target']);ng=bytes.fromhex(case['ram_after']['global_c'])
  observed=(int.from_bytes(npr[:4],'big'),int.from_bytes(npr[4:8],'big'),npr[0x89],nt[0x4c],int.from_bytes(ng[0x9f8:0x9fa],'big'),ng[0xce],int(case['ram_after']['counter_a'],16),int(case['ram_after']['counter_b'],16),int(case['ram_after']['counter_c'],16))
  got=tuple(s[k] for k in ('shadowrun_linked_x_fixed','shadowrun_linked_y_fixed','shadowrun_linked_motion_lifetime','shadowrun_field_target_hp','shadowrun_field_rng','shadowrun_field_death_timer','shadowrun_field_party_counter_a','shadowrun_field_party_counter_b','shadowrun_field_party_counter_c'))
  if not s['shadowrun_field_supported'] or s['shadowrun_linked_motion_state']!=2 or got!=observed:raise AssertionError((got,observed))
 summary={'status':'passed','cases':len(contract['cases']),'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_sha256':sha(cr),'source_ram_sha256':sha(raw),'program_sha256':sha(canonical(program)),'trace_sha256':r['trace_sha256'],'authoring_sha256':sha(SOURCE.read_bytes()),'hostile_receipt_sha256':sha(hostile_receipt_raw),'scope':'assisted linked projectile and constructed hostile relocated to next substep; includes zero effect and source armor; no natural hostile reachability'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
