#!/usr/bin/env python3
"""Compare source post-launch actor/sprite tail to original first frame."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_attack_first import SOURCE,lift_hostile_attack_first
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
 if sha(trace_raw)!=cap['files']['native/ram-writes.json']['sha256']:raise ValueError('writer trace mismatch')
 events=[x for x in json.loads(trace_raw) if x['frame']==6000]
 sequence=((0xff042e,0xb39e),(0xff014c,0x36b2),(0xff013c,0xb00e),(0xff04dc,0xa912));position=-1
 for address,pc in sequence:
  position=next(i for i in range(position+1,len(events)) if events[i]['address']==address and events[i]['pc']==pc)
 before=frame(5999);after=frame(6000);inj=bytes.fromhex(next(x['data_hex'] for x in r['patches'] if x['offset']==0x400));actor=bytes(inj[i^1] for i in range(256));player=before[0x100:0x200];actual=after[0x400:0x500]
 prog=lift_hostile_attack_first(rom);m=GameMachine(prog,{0:rom});m.set_state({'shadowrun_attack_profile':1,'shadowrun_attack_kind':w(actor,14),'shadowrun_attack_x':w(actor,0),'shadowrun_attack_y':w(actor,4),'shadowrun_attack_heading':0xc000,'shadowrun_attack_animation':w(actor,0x16),'shadowrun_attack_increment':w(actor,0x18),'shadowrun_attack_accumulator':w(actor,0x1a),'shadowrun_attack_threshold':w(actor,0x1c),'shadowrun_attack_index':w(actor,0x1e),'shadowrun_attack_move_state':w(actor,0x38),'shadowrun_attack_action_timer':w(actor,0xdc),'shadowrun_attack_service_timer':20,'shadowrun_attack_gear':w(actor,0x90),'shadowrun_attack_speed':w(actor,0xca),'shadowrun_attack_player_x':w(player,0),'shadowrun_attack_player_y':w(player,4),'shadowrun_attack_global_de':1,'shadowrun_attack_global_e0':w(before,0xdfe0),'shadowrun_attack_callback':l(actor,0x3a),'shadowrun_attack_target':0xff0100,'shadowrun_attack_flags':actor[0x10],'shadowrun_attack_flags_low':actor[0x11],'shadowrun_attack_hp':actor[0x4c],'shadowrun_attack_max_hp':actor[0x9c],'shadowrun_attack_item':actor[0x57],'shadowrun_attack_slot':actor[0x56],'shadowrun_attack_ammo':47,'shadowrun_attack_attr_a':actor[0x78],'shadowrun_attack_attr_b':actor[0x7b],'shadowrun_attack_alert':1,'shadowrun_attack_event':actor[0xb0],'shadowrun_attack_counter':6,'shadowrun_attack_corners':list(actor[0xd0:0xd4]),'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_min':w(before,0xddd6),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_min':w(before,0xddd6+2),'shadowrun_y_max':w(before,0xddd4),'shadowrun_rect_base':l(before,0xddec),'shadowrun_probe_corners':list(before[0xef10:0xef14])})
 m.call('shadowrun_hostile_attack_start');assert m.snapshot()['shadowrun_attack_supported'];m.call('shadowrun_hostile_attack_first_pass');s=m.snapshot()
 got=tuple(s[k] for k in ('shadowrun_attack_x','shadowrun_attack_y','shadowrun_attack_heading','shadowrun_attack_animation','shadowrun_attack_increment','shadowrun_attack_accumulator','shadowrun_attack_index','shadowrun_attack_move_state','shadowrun_attack_action_timer','shadowrun_attack_service_timer','shadowrun_attack_callback','shadowrun_attack_event','shadowrun_attack_counter','shadowrun_attack_corners'))
 exp=(w(actual,0),w(actual,4),w(actual,0x2e),w(actual,0x16),w(actual,0x18),w(actual,0x1a),w(actual,0x1e),w(actual,0x38),w(actual,0xdc),w(actual,0xb6),l(actual,0x3a),actual[0xb0],actual[0xb5],list(actual[0xd0:0xd4]))
 if not s['shadowrun_attack_first_supported'] or got!=exp or s['shadowrun_attack_flags_low']!=(actual[0x11]&239):raise AssertionError((got,exp))
 result={'status':'passed','cases':1,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'writer_trace_sha256':sha(trace_raw),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted constructed hostile source launch, post-scheduler target/counter and extra actor pass attested from source trace; later +11bit4 selection external'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
