#!/usr/bin/env python3
"""Check linked projectile flight against an assisted original B+A run.

The launch-time target Y is a prepared representative yielding the observed
heading, not a captured exact coordinate. Enemy motion is not modeled.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_field_combat import ROM_SHA256
from fdisbull.shadowrun_linked_heading import lift_linked_motion
from fdisbull.shadowrun_linked_actors import lift_linked_actors
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',required=True);p.add_argument('--run',required=True);p.add_argument('--output',required=True);p.add_argument('--actors',action='store_true');a=p.parse_args()
 rom=Path(a.rom).read_bytes();root=Path(a.run).resolve();capraw=(root/'capture.json').read_bytes();cap=json.loads(capraw);receipt=json.loads((root/'native/receipt.json').read_text())
 if sha(rom)!=ROM_SHA256 or receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=CORE or not receipt['patches'] or any(x['frame']!=6000 for x in receipt['patches']):raise ValueError('source or assistance mismatch')
 expected_patches={(256,'004b'),(260,'0032'),(56774,'8042'),(56776,'002b'),(56584,'18ff'),(56586,'9800'),(56588,'18ff'),(56590,'9800'),(57144,'8042'),(57142,'002b')}
 if len(receipt['patches'])!=len(expected_patches) or any(x['memory_id']!=2 for x in receipt['patches']) or {(x['offset'],x['data_hex']) for x in receipt['patches']}!=expected_patches:raise ValueError('unexpected assisted intervention')
 if {'start':6001,'end':6003,'buttons':['B']} not in receipt['inputs'] or {'start':6050,'end':6052,'buttons':['A']} not in receipt['inputs']:raise ValueError('input schedule mismatch')
 def checked(rel):
  b=(root/rel).read_bytes();meta=cap['files'].get(rel)
  if not meta or meta['sha256']!=sha(b) or meta['size']!=len(b):raise ValueError('capture mismatch '+rel)
  return b
 def mem(f):
  b=checked(f'native/scene-{f:06}/ram.bin')
  if len(b)!=65536:raise ValueError('RAM length mismatch')
  return bytes(b[i^1] for i in range(len(b)))
 source_frame=6088 if (root/'native/scene-006088/ram.bin').exists() else 6070
 b=mem(source_frame);later=mem(6090);final=mem(6091 if source_frame==6088 else 6120);w=lambda z,i:int.from_bytes(z[i:i+2],'big')
 target_y=w(b,0x504) if source_frame==6088 else 12480
 if (w(b,0x100),w(b,0x104),int.from_bytes(b[0x1a2:0x1a6],'big'),w(b,0x500),b[0x54c],w(b,0xf9f8))!=(19200,12800,0xff0500,21248,10,0xbf94):raise ValueError('prepared source does not match')
 if b[0x1700:0x2200]!=later[0x1700:0x2200] or b[0x1700:0x2200]!=final[0x1700:0x2200]:raise ValueError('sampled terrain changed')
 if (b[0x510],b[0x54d],b[0x577],b[0x578],b[0x57b],b[0x57c],b[0x59b],b[0x59e])!=(0x25,2,2,1,2,2,0x13,0x21):raise ValueError('target profile mismatch')
 program=(lift_linked_actors(rom) if a.actors else lift_linked_motion(rom));m=GameMachine(program,{0:rom})
 m.set_state({'shadowrun_linked_profile':1,'shadowrun_linked_source_x':19200,'shadowrun_linked_source_y':12800,'shadowrun_field_captured_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':12,'shadowrun_field_slots_busy':0,'shadowrun_field_target_flags':0x25,'shadowrun_field_target_flags_b0':0,'shadowrun_field_target_flags_9e':0x21,'shadowrun_field_target_type':19,'shadowrun_field_target_defense_bonus':2,'shadowrun_field_target_x':21248,'shadowrun_field_target_y':target_y,'shadowrun_field_target_hp':10,'shadowrun_field_target_a':1,'shadowrun_field_target_b':2,'shadowrun_field_target_c':2,'shadowrun_field_target_posture':2,'shadowrun_field_rng':w(b,0xf9f8),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_max':w(b,0xddd4),'shadowrun_x_min':w(b,0xddd6),'shadowrun_y_min':w(b,0xddd8),'shadowrun_rect_base':0x172daa})
 if a.actors:
  if source_frame!=6088:raise ValueError('ordered actors require exact pre-launch capture')
  records=[b[0x400+i*0x100:0x500+i*0x100] for i in range(7)]
  for actor in records[:3]:
   if (actor[0x10],actor[0x4c],actor[0x4d],actor[0x76],actor[0x77],actor[0x78],actor[0x7b],actor[0x7c],actor[0x9b])!=(0x25,10,2,0,2,1,2,2,19):raise ValueError('actor profile mismatch')
  m.set_state({'shadowrun_actors_profile':1,'shadowrun_target_selected':1,
   'shadowrun_target_x':[w(v,0) for v in records], 'shadowrun_target_y':[w(v,4) for v in records],
   'shadowrun_target_flags':[v[0x10] for v in records], 'shadowrun_target_flags_b0':[v[0xb0] for v in records],
   'shadowrun_play_actor_hp':[v[0x4c] for v in records]})
 trace=checked('native/ram-writes.json');events=json.loads(trace);rows=[]
 if source_frame==6088:
  heading_events=[i for i,e in enumerate(events) if e['frame']==6089 and e['address']==0xff0b2e and e['pc']==0x15096 and e['value']==0x3b00]
  target_writes=[i for i,e in enumerate(events) if e['frame']==6089 and e['address'] in (0xff0500,0xff0504)]
  if not heading_events or not target_writes or min(target_writes)<heading_events[0]:raise ValueError('target moved before observed heading write')
 m.call('shadowrun_actors_launch' if a.actors else 'shadowrun_linked_launch')
 for f in (6089,6090,6091):
  s=m.snapshot();xy=[]
  for pc,high,low in ((0x14f6e,0xff0b00,0xff0b02),(0x14f72,0xff0b04,0xff0b06)):
   hi=[e['value'] for e in events if e['frame']==f and e['pc']==pc and e['address']==high];lo=[e['value'] for e in events if e['frame']==f and e['pc']==pc and e['address']==low]
   if not hi or len(hi)!=len(lo):raise AssertionError(('missing trajectory',f))
   xy.append((hi[-1]<<16)|lo[-1])
  got=(s['shadowrun_linked_x_fixed'],s['shadowrun_linked_y_fixed']);
  if not s['shadowrun_field_supported'] or got!=tuple(xy):raise AssertionError((f,got,xy))
  rows.append({'frame':f,'x_fixed':xy[0],'y_fixed':xy[1],'steps':s['shadowrun_linked_motion_steps'],'lifetime':s['shadowrun_linked_motion_lifetime'],'state':s['shadowrun_linked_motion_state']})
  if f<6091:m.call('shadowrun_actors_tick' if a.actors else 'shadowrun_linked_tick')
 if s['shadowrun_linked_heading']!=0x3b00 or s['shadowrun_linked_motion_state']!=3 or not any(e['frame']==6091 and e['address']==0xff0b11 and e['value']&8 for e in events):raise AssertionError('heading or terrain stop mismatch')
 if (int.from_bytes(later[0xb00:0xb04],'big'),int.from_bytes(later[0xb04:0xb08],'big'),later[0xb89],later[0x14e],later[0x54c],final[0x54c],w(later,0xf9f8))!=(rows[1]['x_fixed'],rows[1]['y_fixed'],119,11,10,10,s['shadowrun_field_rng']):raise AssertionError('source RAM mismatch')
 result={'status':'passed','frames':rows,'rom_sha256':sha(rom),'capture_sha256':sha(capraw),'trace_sha256':sha(trace),'program_sha256':sha(canonical(program)),
  'source_frame':source_frame,'target_y':target_y,'ordered_actor_adapter':a.actors,'scope':(('assisted player placement and linked selector; static captured actor adapter; pre-launch snapshot and observed write ordering; original moving target missed' if a.actors else 'assisted player placement and linked selector; pre-launch target snapshot and observed write ordering; original moving target, no actor hit') if source_frame==6088 else 'assisted teleported source and linked selector; representative target y yields observed heading; original moving-target coordinates at launch not observed; collision path contains no actor hit')}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','frames':len(rows),'scope':result['scope']},indent=2))
if __name__=='__main__':main()
