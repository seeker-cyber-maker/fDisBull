#!/usr/bin/env python3
"""Compare the calm courtyard's actual first near-waypoint transition."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_enemy_waypoint import SOURCE
from fdisbull.shadowrun_enemy_idle import lift_enemy_idle
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(x):return hashlib.sha256(x).hexdigest()
def w(x,n):return int.from_bytes(x[n:n+2],'big')
def l(x,n):return int.from_bytes(x[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','run','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.run);cr=(root/'capture.json').read_bytes();cap=json.loads(cr);rr=(root/'native/receipt.json').read_bytes();r=json.loads(rr)
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or r['patches']:raise ValueError('source identity or unpatched capture mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=frame(6203);after=frame(6204);v=before[0x400:0x500];z=after[0x400:0x500];m=GameMachine(lift_enemy_idle(rom),{0:rom})
 m.set_state({'shadowrun_ai_x':w(v,0),'shadowrun_ai_y':w(v,4),'shadowrun_ai_kind':w(v,14),'shadowrun_ai_target_heading':w(v,0x34),'shadowrun_ai_distance':w(v,0xc8),'shadowrun_ai_collision_state':w(v,0xb8),'shadowrun_ai_animation':w(v,0x16),'shadowrun_ai_callback':l(v,0x3a),'shadowrun_ai_flags':v[0x10],'shadowrun_ai_equipment_flags':v[0x9e],'shadowrun_ai_event_flags':v[0xb0],'shadowrun_ai_combat_global':w(before,0xdf84),'shadowrun_ai_service_timer':w(v,0xb6),'shadowrun_ai_service_contact':w(v,0xc),'shadowrun_ai_waypoint_x':w(v,0x96),'shadowrun_ai_waypoint_y':w(v,0x98),'shadowrun_ai_service_direction':v[0xb1],'shadowrun_ai_service_pause':before[0xe175],'shadowrun_ai_waypoint_table':l(v,0xe0),'shadowrun_ai_waypoint_index':w(v,0xe4),'shadowrun_ai_heading':w(v,0x2e),'shadowrun_ai_transition_heading':w(v,0x36),'shadowrun_ai_move_state':w(v,0x38),'shadowrun_ai_speed':w(v,0xca),'shadowrun_ai_flags_low':v[0x11],'shadowrun_ai_attribute':v[0x78],'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_max':w(before,0xddd4),'shadowrun_x_min':w(before,0xddd6),'shadowrun_y_min':w(before,0xddd8),'shadowrun_rect_base':l(before,0xddec)})
 m.call('shadowrun_ai_waypoint_arrival');s=m.snapshot();keys=('service_timer','target_heading','distance','callback','event_flags','service_direction','waypoint_x','waypoint_y','waypoint_index');got=tuple(s['shadowrun_ai_'+k] for k in keys);exp=(w(z,0xb6),w(z,0x34),w(z,0xc8),l(z,0x3a),z[0xb0],z[0xb1],w(z,0x96),w(z,0x98),w(z,0xe4))
 if not s['shadowrun_ai_waypoint_supported'] or got!=exp or w(before,0xf9f8)!=w(after,0xf9f8):raise AssertionError((got,exp))
 m.call('shadowrun_ai_idle_tick');s=m.snapshot()
 if not s['shadowrun_ai_idle_supported'] or s['shadowrun_ai_animation']!=w(z,0x16) or s['shadowrun_ai_move_state']!=w(z,0x38) or s['shadowrun_ai_corners']!=list(z[0xd0:0xd4]):raise AssertionError(('idle',s['shadowrun_ai_animation'],w(z,0x16),s['shadowrun_ai_corners'],list(z[0xd0:0xd4])))
 result={'status':'passed','source_transition':[6203,6204],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(m.program)),'scope':'unpatched calm scene actor0 near-waypoint source service, waypoint service followed by B45C idle callback; sprite clock separate'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
