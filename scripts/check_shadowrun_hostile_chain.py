#!/usr/bin/env python3
"""Compare prepared hostile scheduler/pursuit/move composition to CPU chain."""
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
 for k in ('rom','native','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.native);raw=(root/'receipt.json').read_bytes();r=json.loads(raw);before=(root/'ram-before.bin').read_bytes();after=(root/'ram-after.bin').read_bytes();case=r['cases'][0]
 if sha(rom)!=ROM_SHA256 or not r['complete'] or not r['inputs_unchanged'] or r['source_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or sha(before)!=case['ram_before_sha256'] or sha(after)!=case['ram_after_sha256'] or case['registers_after']['PC']!=0xb6e2:raise ValueError('prepared native chain provenance')
 lift_hostile(rom);lift_hostile_pursuit(rom);lift_hostile_move(rom)
 base=ROOT/'src/fdisbull/game_sources';names=['shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_enemy_move.c','shadowrun_hostile_move.c','shadowrun_hostile_pursuit.c','shadowrun_hostile.c'];chunks=[(base/n).read_bytes() for n in names]
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
 result={'status':'passed','cases':1,'rom_sha256':sha(rom),'native_receipt_sha256':sha(raw),'native_trace_sha256':r['trace_sha256'],'authoring_sha256':[sha(c) for c in chunks],'program_sha256':sha(canonical(program)),'scope':'single controlled prepared actor scheduler to pursuit to clear movement; no natural encounter or subsequent frames'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
