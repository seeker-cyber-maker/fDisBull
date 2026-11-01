#!/usr/bin/env python3
"""Compare prepared hostile shooting pose and full-core stationary frames."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_hostile_idle_service import SOURCE,lift_hostile_idle_service
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','core','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();core=Path(a.core).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr);author=SOURCE.read_bytes()
 expected={(0x400,256),(0xdf84,2),(0xdfd8,2),(0xe186,2),(0xf9f8,2)}
 if sha(rom)!=ROM_SHA256 or sha(core)!=CORE or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or len(r['patches'])!=5 or any(x['frame']!=6000 or x['memory_id']!=2 for x in r['patches']) or {(x['offset'],len(x['data_hex'])//2) for x in r['patches']}!=expected:raise ValueError('source or injection mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 prog=lift_hostile_idle_service(rom);m=GameMachine(prog,{0:rom})
 out=_private_directory(a.output);out.mkdir(mode=0o700)
 b=frame(6021);v=b[0x400:0x500];p1=b[0x100:0x200]
 if (w(v,0),w(v,4),w(v,0x2e),w(v,0x16),l(v,0x3a),w(v,0xb6),w(v,0xdc))!=(16096,11210,0xc000,0x18,0xb45c,20,25):raise ValueError('source stationary seed mismatch')
 m.set_state({'shadowrun_attack_profile':1,'shadowrun_attack_kind':w(v,14),'shadowrun_attack_x':w(v,0),'shadowrun_attack_y':w(v,4),'shadowrun_attack_heading':w(v,0x2e),'shadowrun_attack_animation':w(v,0x16),'shadowrun_attack_increment':w(v,0x18),'shadowrun_attack_accumulator':w(v,0x1a),'shadowrun_attack_threshold':w(v,0x1c),'shadowrun_attack_index':w(v,0x1e),'shadowrun_attack_move_state':w(v,0x38),'shadowrun_attack_action_timer':w(v,0xdc),'shadowrun_attack_service_timer':w(v,0xb6),'shadowrun_attack_gear':w(v,0x90),'shadowrun_attack_speed':w(v,0xca),'shadowrun_attack_player_x':w(p1,0),'shadowrun_attack_player_y':w(p1,4),'shadowrun_attack_global_de':w(b,0xdfde),'shadowrun_attack_global_e0':w(b,0xdfe0),'shadowrun_attack_callback':l(v,0x3a),'shadowrun_attack_target':l(v,0xa2),'shadowrun_attack_flags':v[0x10],'shadowrun_attack_flags_low':v[0x11],'shadowrun_attack_hp':v[0x4c],'shadowrun_attack_max_hp':v[0x9c],'shadowrun_attack_item':v[0x57],'shadowrun_attack_slot':v[0x56],'shadowrun_attack_ammo':v[0x4e],'shadowrun_attack_attr_a':v[0x78],'shadowrun_attack_attr_b':v[0x7b],'shadowrun_attack_alert':b[0xe186],'shadowrun_attack_event':v[0xb0],'shadowrun_attack_counter':v[0xb5],'shadowrun_attack_corners':list(v[0xd0:0xd4]),'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_min':w(b,0xddd6),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_min':w(b,0xddd8),'shadowrun_y_max':w(b,0xddd4),'shadowrun_rect_base':l(b,0xddec),'shadowrun_probe_corners':list(b[0xef10:0xef14])})
 for f in range(6022,6061):
  current=frame(f);v=current[0x400:0x500]
  if current[0x1700:0x2200]!=b[0x1700:0x2200] or (w(v,0),w(v,4))!=(w(b,0x400),w(b,0x404)):raise ValueError('terrain or actor moved')
  if f==6030:
   m.call('shadowrun_hostile_idle_actor_pass');assert m.snapshot()['shadowrun_hostile_idle_supported']
   m.call('shadowrun_hostile_idle_actor_pass');assert m.snapshot()['shadowrun_hostile_idle_supported']
   m.call('shadowrun_hostile_idle_sprite_pass')
  else:m.call('shadowrun_hostile_idle_step')
  s=m.snapshot()
  got=tuple(s[k] for k in ('shadowrun_attack_x','shadowrun_attack_y','shadowrun_attack_heading','shadowrun_attack_animation','shadowrun_attack_increment','shadowrun_attack_accumulator','shadowrun_attack_index','shadowrun_attack_move_state','shadowrun_attack_action_timer','shadowrun_attack_service_timer','shadowrun_attack_callback','shadowrun_attack_flags_low','shadowrun_attack_event','shadowrun_attack_counter','shadowrun_attack_corners'))
  exp=(w(v,0),w(v,4),w(v,0x2e),w(v,0x16),w(v,0x18),w(v,0x1a),w(v,0x1e),w(v,0x38),w(v,0xdc),w(v,0xb6),l(v,0x3a),v[0x11],v[0xb0],v[0xb5],list(v[0xd0:0xd4]))
  if not s['shadowrun_hostile_idle_supported'] or s['shadowrun_hostile_idle_expired']!=(1 if f==6041 else 0) or got!=exp:raise AssertionError((f,got,exp,(s['shadowrun_hostile_idle_supported'],s['shadowrun_hostile_idle_expired'])))
 if SOURCE.read_bytes()!=author:raise ValueError('source changed')
 summary={'status':'passed','matched_idle_frames':39,'expiry_frame':6041,'rom_sha256':sha(rom),'core_sha256':sha(core),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(author),'program_sha256':sha(canonical(prog)),'scope':'prepared hostile idle frames 6022–6060 and DFDE-active service expiry; frame6030 source hit causes an explicit second actor pass; selected B3, independent projectile RNG, audio and graphics excluded'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
