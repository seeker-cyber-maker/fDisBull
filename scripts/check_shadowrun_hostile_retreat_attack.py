#!/usr/bin/env python3
"""Compare second prepared enemy launch pose and following original frames."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_moving_attack_reentry import SOURCE,lift_hostile_moving_attack_reentry
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 expected={(0x400,256),(0xdf84,2),(0xdfd8,2),(0xe186,2),(0xf9f8,2)}
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or len(r['patches'])!=5 or any(x['frame']!=6000 or x['memory_id']!=2 for x in r['patches']) or {(x['offset'],len(x['data_hex'])//2) for x in r['patches']}!=expected:raise ValueError('source or injection mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 trace_raw=(root/'native/ram-writes.json').read_bytes()
 if sha(trace_raw)!=cap['files']['native/ram-writes.json']['sha256']:raise ValueError('trace mismatch')
 events=[x for x in json.loads(trace_raw) if x['frame']==6093];sequence=((0xff04b6,0x13920),(0xff044e,0x38f4),(0xff042e,0xb39e),(0xff041a,0x600c));position=-1
 for address,pc in sequence:position=next(i for i in range(position+1,len(events)) if events[i]['address']==address and events[i]['pc']==pc)
 before=frame(6092);v=before[0x400:0x500];player=frame(6093)[0x100:0x200]
 if (w(v,14),v[0x10],v[0x4e],w(v,0xdc),w(v,0xb6),v[0xb5],l(v,0x3a))!=(8,5,47,65535,0,3,0xb45c):raise ValueError('pre-relaunch mismatch')
 prog=lift_hostile_moving_attack_reentry(rom);m=GameMachine(prog,{0:rom});m.set_state({'shadowrun_attack_profile':1,'shadowrun_attack_kind':w(v,14),'shadowrun_attack_x':w(v,0),'shadowrun_attack_y':w(v,4),'shadowrun_attack_heading':0xcf00,'shadowrun_attack_animation':w(v,0x16),'shadowrun_attack_increment':w(v,0x18),'shadowrun_attack_accumulator':w(v,0x1a),'shadowrun_attack_threshold':w(v,0x1c),'shadowrun_attack_index':w(v,0x1e),'shadowrun_attack_move_state':w(v,0x38),'shadowrun_attack_action_timer':w(v,0xdc),'shadowrun_attack_service_timer':20,'shadowrun_attack_gear':w(v,0x90),'shadowrun_attack_speed':w(v,0xca),'shadowrun_attack_player_x':w(player,0),'shadowrun_attack_player_y':w(player,4),'shadowrun_attack_global_de':1,'shadowrun_attack_global_e0':w(before,0xdfe0),'shadowrun_attack_callback':l(v,0x3a),'shadowrun_attack_target':l(v,0xa2),'shadowrun_attack_flags':v[0x10],'shadowrun_attack_flags_low':v[0x11],'shadowrun_attack_hp':v[0x4c],'shadowrun_attack_max_hp':v[0x9c],'shadowrun_attack_item':v[0x57],'shadowrun_attack_slot':v[0x56],'shadowrun_attack_ammo':46,'shadowrun_attack_attr_a':v[0x78],'shadowrun_attack_attr_b':v[0x7b],'shadowrun_attack_alert':before[0xe186],'shadowrun_attack_event':v[0xb0],'shadowrun_attack_counter':v[0xb5],'shadowrun_attack_corners':list(v[0xd0:0xd4]),'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_min':w(before,0xddd6),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_min':w(before,0xddd8),'shadowrun_y_max':w(before,0xddd4),'shadowrun_rect_base':l(before,0xddec),'shadowrun_probe_corners':list(before[0xef10:0xef14])})
 m.call('shadowrun_hostile_attack_start');assert m.snapshot()['shadowrun_attack_supported'];m.call('shadowrun_hostile_moving_attack_reentry');s=m.snapshot()
 if not s['shadowrun_moving_attack_reentry_supported']:raise AssertionError('relaunch refused')
 for f in range(6093,6094):
  b=frame(f);a1=b[0x400:0x500]
  if b[0x1700:0x2200]!=before[0x1700:0x2200] or (w(a1,0),w(a1,4))!=(w(v,0),w(v,4)):raise ValueError('actor or terrain moved')
  if f>6093:
   m.call('shadowrun_hostile_attack_positive_step');s=m.snapshot()
   if not s['shadowrun_attack_positive_supported']:raise AssertionError(('positive step refused',f))
  got=tuple(s[k] for k in ('shadowrun_attack_x','shadowrun_attack_y','shadowrun_attack_heading','shadowrun_attack_animation','shadowrun_attack_increment','shadowrun_attack_accumulator','shadowrun_attack_index','shadowrun_attack_move_state','shadowrun_attack_action_timer','shadowrun_attack_service_timer','shadowrun_attack_callback','shadowrun_attack_flags_low','shadowrun_attack_event','shadowrun_attack_counter','shadowrun_attack_corners'))
  exp=(w(a1,0),w(a1,4),w(a1,0x2e),w(a1,0x16),w(a1,0x18),w(a1,0x1a),w(a1,0x1e),w(a1,0x38),w(a1,0xdc),w(a1,0xb6),l(a1,0x3a),a1[0x11],a1[0xb0],a1[0xb5],list(a1[0xd0:0xd4]))
  if got!=exp:raise AssertionError((f,got,exp))
 result={'status':'passed','matched_frames':1,'launch_frame':6093,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'writer_trace_sha256':sha(trace_raw),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'prepared moving hostile launch and player-hit actor pose, frame6093; source scheduler/shot and projectile RNG separate'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
