#!/usr/bin/env python3
"""Compare held-A party recovery with a full-core assisted original capture."""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,author_program,canonical
from fdisbull.shadowrun_player_reaction_direction import SOURCE,lift_player_reaction_direction
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
 if not any(x['start']<=6032 and x['end']>6033 and x['buttons']==['LEFT'] for x in r['inputs']):raise ValueError('held LEFT missing')
 def frame(f):
  rel=f'native/scene-{f:06}/ram.bin';raw=(root/rel).read_bytes()
  if len(raw)!=65536 or sha(raw)!=cap['files'][rel]['sha256']:raise ValueError('capture mismatch')
  return bytes(raw[i^1] for i in range(65536))
 before=frame(6032);after=frame(6033);v=before[0x100:0x200];n=after[0x100:0x200]
 if (w(v,14),v[0x10],v[0x4c],l(v,0x3a),w(v,0xdc),w(before,0xdd22),w(before,0xdd04))!=(3,15,5,0xb07e,4,4,0xc000):raise ValueError('source precondition mismatch')
 lift_player_reaction_direction(rom)
 base=ROOT/'src/fdisbull/game_sources';names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_player_reaction.c','shadowrun_player_reaction_step.c','shadowrun_player_reaction_resume.c','shadowrun_player_reaction_direction.c','shadowrun_player_move.c','shadowrun_player_walk.c','shadowrun_player_combat_walk.c','shadowrun_animation.c','shadowrun_party_clock.c')
 chunks=[(base/name).read_bytes() for name in names];prog=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}]);m=GameMachine(prog,{0:rom})
 m.set_state({'shadowrun_reaction_kind':w(v,14),'shadowrun_reaction_x':w(v,0),'shadowrun_reaction_y':w(v,4),'shadowrun_reaction_heading':w(v,0x2e),'shadowrun_reaction_animation':w(v,0x16),'shadowrun_reaction_increment':w(v,0x18),'shadowrun_reaction_accumulator':w(v,0x1a),'shadowrun_reaction_threshold':w(v,0x1c),'shadowrun_reaction_index':w(v,0x1e),'shadowrun_reaction_move_state':w(v,0x38),'shadowrun_reaction_action_timer':w(v,0xdc),'shadowrun_reaction_callback':l(v,0x3a),'shadowrun_reaction_flags':v[0x10],'shadowrun_reaction_flags_low':v[0x11],'shadowrun_reaction_hp':v[0x4c],'shadowrun_reaction_max_hp':v[0x9c],'shadowrun_reaction_counter':v[0xce],'shadowrun_reaction_corners':list(v[0xd0:0xd4]),'shadowrun_terrain_map':list(before[0x1700:0x2200]),'shadowrun_x_max':w(before,0xddd2),'shadowrun_y_max':w(before,0xddd4),'shadowrun_x_min':w(before,0xddd6),'shadowrun_y_min':w(before,0xddd8),'shadowrun_rect_base':l(before,0xddec),'shadowrun_probe_corners':list(before[0xef10:0xef14]),'shadowrun_reaction_cursor':v[0x43],'shadowrun_reaction_attr_a':v[0x78],'shadowrun_reaction_attr_b':v[0x7b],'shadowrun_reaction_gear':w(v,0x90),'shadowrun_reaction_speed':w(v,0xca),'shadowrun_reaction_input_flags':w(before,0xdd22),'shadowrun_reaction_input_heading':w(before,0xdd04),'shadowrun_reaction_global_e6':w(before,0xdfe6),'shadowrun_reaction_global_3a':w(before,0xdf3a),'shadowrun_reaction_global_18a':before[0xe18a],'shadowrun_reaction_global_18b':before[0xe18b]})
 m.call('shadowrun_reaction_step');s=m.snapshot()
 if not s['shadowrun_reaction_step_supported'] or s['shadowrun_reaction_step_result']!=2:raise AssertionError('input admission refused')
 m.call('shadowrun_reaction_resume_direction');s=m.snapshot()
 if not s['shadowrun_reaction_direction_supported']:raise AssertionError('direction admission refused')
 m.set_state({'shadowrun_player_x':w(v,0),'shadowrun_player_y':w(v,4),'shadowrun_player_heading':w(v,0x2e),'shadowrun_player_target_heading':s['shadowrun_reaction_target_heading'],'shadowrun_player_kind':w(v,14),'shadowrun_player_contact':w(v,12),'shadowrun_player_flags':v[0x10],'shadowrun_player_equipment_flags':v[0x9e],'shadowrun_player_event_flags':v[0xb0],'shadowrun_player_combat_attribute':v[0x78],'shadowrun_player_combat_global':w(before,0xdf84),'shadowrun_global_special_mode':0,'shadowrun_global_vector_flags':0})
 m.call('shadowrun_player_combat_walk');t=m.snapshot()
 if not t['shadowrun_player_combat_walk_supported']:raise AssertionError('combat movement refused')
 m.set_state({'shadowrun_party_kind':w(v,14),'shadowrun_party_callback':s['shadowrun_reaction_callback'],'shadowrun_party_heading':t['shadowrun_player_heading'],'shadowrun_party_transition_heading':w(v,0x36),'shadowrun_party_speed':28,'shadowrun_party_flags_low':v[0x11],'shadowrun_anim_increment':w(v,0x18),'shadowrun_anim_accumulator':w(v,0x1a),'shadowrun_anim_threshold':w(v,0x1c),'shadowrun_anim_index':w(v,0x1e)})
 m.call('shadowrun_party_pose_tick');m.call('shadowrun_party_clock_tick');u=m.snapshot()
 got=(t['shadowrun_player_x'],t['shadowrun_player_y'],t['shadowrun_player_heading'],s['shadowrun_reaction_callback'],s['shadowrun_reaction_action_timer'],u['shadowrun_party_pose'],u['shadowrun_anim_increment'],u['shadowrun_anim_accumulator'],u['shadowrun_anim_index'])
 exp=(w(n,0),w(n,4),w(n,0x2e),l(n,0x3a),w(n,0xdc),w(n,0x16),w(n,0x18),w(n,0x1a),w(n,0x1e))
 if not u['shadowrun_party_clock_supported'] or got!=exp:raise AssertionError(('held-direction recovery',got,exp))
 summary={'status':'passed','source_transition':[6032,6033],'rom_sha256':sha(rom),'capture_sha256':sha(cr),'capture_receipt_sha256':sha(rr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(prog)),'scope':'assisted constructed hostile, held LEFT reaction admission and source party movement/sprite clock; walking sprite speed28 supplied from source actor service'}
 out=_private_directory(a.output);out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
