#!/usr/bin/env python3
"""Check captured-heading GameIL flight against an unpatched Genesis run.

The observer's neutrality is not established by its capture alone. The observed
route has no prepared target; target-hit comparison is a separate diagnostic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_field_combat import lift_field_motion, ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',required=True);p.add_argument('--run',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 rom=Path(a.rom).read_bytes();root=Path(a.run).resolve();capture_raw=(root/'capture.json').read_bytes();capture=json.loads(capture_raw)
 receipt_raw=(root/'native/receipt.json').read_bytes();receipt=json.loads(receipt_raw)
 if sha(rom)!=ROM_SHA256 or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or receipt['system']!='genesis':raise ValueError('source identity mismatch')
 if receipt['patches'] or receipt['memory_injection_mode']!='no memory patches' or {'start':6000,'end':6002,'buttons':['A']} not in receipt['inputs']:raise ValueError('input or patch contract mismatch')
 def checked_file(rel):
  raw=(root/rel).read_bytes();declared=capture['files'].get(rel)
  if not declared or declared['sha256']!=sha(raw) or declared['size']!=len(raw):raise ValueError('capture file hash mismatch: '+rel)
  return raw
 def memory(frame):
  b=checked_file(f'native/scene-{frame:06}/ram.bin')
  if len(b)!=65536:raise ValueError('unexpected memory size')
  return bytes(b[i^1] for i in range(len(b)))
 initial=memory(6036);samples={f:memory(f) for f in (6037,6040,6045)}
 actor=initial[0x100:0x200];word=lambda b,i:int.from_bytes(b[i:i+2],'big')
 if (word(actor,0),word(actor,4),word(actor,0x2e),word(actor,0x3e),actor[0x10],actor[0x4e],actor[0x56],actor[0x57])!=(0x3ce0,0x2bca,0x8000,0,15,12,0,2):raise ValueError('captured player mismatch')
 exact={0x4c:10,0x4d:2,0x9c:10,0x78:3,0x7b:2,0x7c:4,0x81:4,0x82:0,0x9a:0,0xb4:0,0xdf:0}
 if any(actor[k]!=v for k,v in exact.items()) or word(actor,0x90)!=4 or actor[0x66:0x76]!=bytes.fromhex('022c0e10000000000000060600000000'):raise ValueError('captured shot profile mismatch')
 terrain=initial[0x1700:0x2200]
 if any(b[0x1700:0x2200]!=terrain for b in samples.values()):raise ValueError('terrain changed across sampled source frames')
 busy=sum(((initial[0xb10+i*0x100]&1)!=0)<<i for i in range(6))
 if busy:raise ValueError('source projectile slots occupied')
 program=lift_field_motion(rom);m=GameMachine(program,{0:rom})
 m.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_path_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':12,'shadowrun_field_slots_busy':busy,'shadowrun_field_target_flags':0,'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,'shadowrun_field_target_hp':50,'shadowrun_field_target_a':5,'shadowrun_field_target_b':5,'shadowrun_field_target_c':5,'shadowrun_field_target_posture':0,'shadowrun_field_rng':word(initial,0xf9f8),'shadowrun_terrain_map':list(terrain),'shadowrun_x_max':word(initial,0xddd2),'shadowrun_y_max':word(initial,0xddd4),'shadowrun_x_min':word(initial,0xddd6),'shadowrun_y_min':word(initial,0xddd8),'shadowrun_rect_base':0x172daa})
 trace_raw=checked_file('native/ram-writes.json');events=json.loads(trace_raw)
 rows=[];m.call('shadowrun_field_captured_launch')
 for frame in range(6037,6045):
  s=m.snapshot();writes=[e for e in events if e['frame']==frame and e['pc']==0x14f72 and e['address'] in (0xff0b04,0xff0b06)]
  hi=[e['value'] for e in writes if e['address']==0xff0b04];lo=[e['value'] for e in writes if e['address']==0xff0b06]
  if not hi or len(hi)!=len(lo):raise AssertionError(('incomplete original position writes',frame))
  original=(hi[-1]<<16)|lo[-1]
  if not s['shadowrun_field_supported'] or s['shadowrun_field_motion_y_fixed']!=original:raise AssertionError(('position mismatch',frame,s['shadowrun_field_motion_y_fixed'],original))
  rows.append({'frame':frame,'y_fixed':original,'steps':s['shadowrun_field_motion_steps'],'lifetime':s['shadowrun_field_motion_lifetime'],'state':s['shadowrun_field_motion_state']})
  if frame<6044:m.call('shadowrun_field_captured_tick')
 if rows[-1]['state']!=3 or not any(e['frame']==6044 and e['address']==0xff0b11 and e['value']&8 for e in events):raise AssertionError('terrain stop mismatch')
 for f,expected_frame in ((6037,6037),(6040,6040),(6045,6044)):
  b=samples[f];row=rows[expected_frame-6037]
  if (int.from_bytes(b[0xb04:0xb08],'big'),b[0xb89],b[0x14e])!=(row['y_fixed'],row['lifetime'],11):raise AssertionError(('RAM mismatch',f))
  if b[0xb9f]!=s['shadowrun_field_source_effect'] or word(b,0xf9f8)!=s['shadowrun_field_rng']:raise AssertionError(('shot RNG mismatch',f))
  if not (b[0xb10]&1) or int.from_bytes(b[0xb3a:0xb3e],'big')!=0x14e0a:raise AssertionError(('projectile identity mismatch',f))
 result={'status':'passed','frames':rows,'rom_sha256':sha(rom),'capture_sha256':sha(capture_raw),'receipt_sha256':sha(receipt_raw),'trace_sha256':sha(trace_raw),'program_sha256':sha(canonical(program)),'terrain_sha256':sha(terrain),'scope':'one unpatched original controller schedule and instrumented captured-source projectile route; observer neutrality and actor-hit reachability unproven'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'frames':len(rows),'scope':result['scope']},indent=2))
if __name__=='__main__':main()
