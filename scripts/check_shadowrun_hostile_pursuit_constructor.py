#!/usr/bin/env python3
"""Compare constructor-to-pursuit source chain to assisted full-core frame."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import GameMachine,author_program,canonical
from fdisbull.shadowrun_hostile import lift_hostile
from fdisbull.shadowrun_hostile_pursuit import lift_hostile_pursuit
from fdisbull.shadowrun_hostile_move import lift_hostile_move
from fdisbull.console_udc import _private_directory
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
 if sha(rom)!=ROM_SHA256 or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or len(r['patches'])!=5 or any(x['frame']!=6000 or x['memory_id']!=2 for x in r['patches']) or {(x['offset'],len(x['data_hex'])//2) for x in r['patches']}!=expected:raise ValueError('source or assisted injection mismatch')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=bytearray(frame(5999));after=frame(6000)
 for patch in r['patches']:
  data=bytes.fromhex(patch['data_hex']);offset=patch['offset']
  for i,x in enumerate(data):before[(offset+i)^1]=x
 lift_hostile(rom);lift_hostile_pursuit(rom);lift_hostile_move(rom)
 base=ROOT/'src/fdisbull/game_sources';names=['shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_enemy_move.c','shadowrun_hostile_move.c','shadowrun_hostile_pursuit.c','shadowrun_hostile.c','shadowrun_hostile_pursuit_route.c'];chunks=[(base/n).read_bytes() for n in names]
 source='\n'.join('\n'.join(line for line in c.decode().splitlines() if not line.startswith('extern ')) for c in chunks)
 program=author_program(source,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}]);m=GameMachine(program,{0:rom});b=before;actor=b[0x400:0x500];player=b[0x100:0x200];ww=lambda n:w(actor,n)
 m.set_state({'shadowrun_terrain_map':list(b[0x1700:0x2200]),'shadowrun_x_min':w(b,0xddd6),'shadowrun_x_max':w(b,0xddd2),'shadowrun_y_min':w(b,0xddd8),'shadowrun_y_max':w(b,0xddd4),'shadowrun_rect_base':l(b,0xddec),'shadowrun_probe_corners':list(b[0xef10:0xef14]),
  'shadowrun_hostile_profile':1,'shadowrun_hostile_x':ww(0),'shadowrun_hostile_y':ww(4),'shadowrun_hostile_player_x':w(player,0),'shadowrun_hostile_player_y':w(player,4),'shadowrun_hostile_ammo':actor[0x4e],'shadowrun_hostile_contact':ww(0xc),'shadowrun_hostile_rng':w(b,0xf9f8),'shadowrun_hostile_target_existing':int(bool(l(actor,0xa2))),'shadowrun_hostile_timer':ww(0xb6),'shadowrun_hostile_cooldown':ww(0xdc)})
 m.call('shadowrun_hostile_tick');s=m.snapshot()
 if not s['shadowrun_hostile_supported'] or not s['shadowrun_hostile_pursuit_required']:raise AssertionError('scheduler did not enter pursuit')
 m.set_state({'shadowrun_hostile_pursuit_x':ww(0),'shadowrun_hostile_pursuit_y':ww(4),'shadowrun_hostile_pursuit_player_x':w(player,0),'shadowrun_hostile_pursuit_player_y':w(player,4),'shadowrun_hostile_pursuit_kind':ww(14),'shadowrun_hostile_pursuit_animation':ww(0x16),'shadowrun_hostile_pursuit_collision':ww(0xb8),'shadowrun_hostile_pursuit_path_index':ww(0xba),'shadowrun_hostile_pursuit_global_de':w(b,0xdfde),'shadowrun_hostile_pursuit_global_e0':w(b,0xdfe0),'shadowrun_hostile_pursuit_callback':l(actor,0x3a),'shadowrun_hostile_pursuit_target':0xff0100,'shadowrun_hostile_pursuit_flags':actor[0x10],'shadowrun_hostile_pursuit_item':actor[0x57],'shadowrun_hostile_pursuit_slot':actor[0x56],'shadowrun_hostile_pursuit_ammo':actor[0x4e],'shadowrun_hostile_pursuit_alert':b[0xe186],'shadowrun_hostile_pursuit_event':actor[0xb0],'shadowrun_hostile_pursuit_direction':actor[0xb1],'shadowrun_hostile_pursuit_counter':s['shadowrun_hostile_target_timer']})
 m.call('shadowrun_hostile_pursuit_tick');t=m.snapshot()
 if not t['shadowrun_hostile_pursuit_supported']:raise AssertionError('pursuit refused')
 m.set_state({'shadowrun_ai_x':ww(0),'shadowrun_ai_y':ww(4),'shadowrun_ai_heading':ww(0x2e),'shadowrun_ai_target_heading':t['shadowrun_hostile_pursuit_heading'],'shadowrun_ai_transition_heading':ww(0x36),'shadowrun_ai_kind':ww(14),'shadowrun_ai_distance':t['shadowrun_hostile_pursuit_distance'],'shadowrun_ai_move_state':ww(0x38),'shadowrun_ai_collision_state':ww(0xb8),'shadowrun_ai_speed':ww(0xca),'shadowrun_ai_animation':ww(0x16),'shadowrun_ai_callback':t['shadowrun_hostile_pursuit_callback'],'shadowrun_ai_flags':actor[0x10],'shadowrun_ai_flags_low':actor[0x11],'shadowrun_ai_equipment_flags':actor[0x9e],'shadowrun_ai_event_flags':t['shadowrun_hostile_pursuit_event'],'shadowrun_ai_attribute':actor[0x78],'shadowrun_ai_combat_global':w(b,0xdf84),'shadowrun_ai_corners':list(actor[0xd0:0xd4])})
 m.call('shadowrun_hostile_move_tick');u=m.snapshot();outactor=after[0x400:0x500]
 if not u['shadowrun_hostile_move_supported']:raise AssertionError('movement refused')
 got=(u['shadowrun_ai_x'],u['shadowrun_ai_y'],u['shadowrun_ai_heading'],u['shadowrun_ai_target_heading'],u['shadowrun_ai_distance'],u['shadowrun_ai_callback'],u['shadowrun_ai_event_flags'],u['shadowrun_hostile_pursuit_direction'],u['shadowrun_hostile_pursuit_counter'],u['shadowrun_hostile_pursuit_path0'],u['shadowrun_hostile_pursuit_path1'],u['shadowrun_hostile_pursuit_path2'],u['shadowrun_hostile_timer'],u['shadowrun_hostile_cooldown'],u['shadowrun_hostile_rng'])
 expected=(w(outactor,0),w(outactor,4),w(outactor,0x2e),w(outactor,0x34),w(outactor,0xc8),l(outactor,0x3a),outactor[0xb0],outactor[0xb1],outactor[0xb5],w(outactor,0xbc),w(outactor,0xbe),w(outactor,0xc0),w(outactor,0xb6),w(outactor,0xdc),w(after,0xf9f8))
 if got!=expected:raise AssertionError((got,expected))
 m.set_state({'shadowrun_pursuit_route_sprite_increment':ww(0x18),'shadowrun_pursuit_route_sprite_accumulator':ww(0x1a),'shadowrun_pursuit_route_sprite_threshold':ww(0x1c),'shadowrun_pursuit_route_sprite_index':ww(0x1e)})
 m.call('shadowrun_hostile_pursuit_first_sprite');u=m.snapshot()
 sprite=(u['shadowrun_pursuit_route_sprite_increment'],u['shadowrun_pursuit_route_sprite_accumulator'],u['shadowrun_pursuit_route_sprite_index'])
 if not u['shadowrun_pursuit_route_supported'] or sprite!=(w(outactor,0x18),w(outactor,0x1a),w(outactor,0x1e)):raise AssertionError(('first sprite',sprite))
 result={'status':'passed','matched_cases':1,'source_frame':6000,'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':[sha(c) for c in chunks],'program_sha256':sha(canonical(program)),'scope':'assisted constructor to scheduler, pursuit and clear movement; first actor sprite clock included; original player and sound phases separate'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
