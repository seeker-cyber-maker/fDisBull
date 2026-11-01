"""Source-bound actor projections and fail-closed dispatch boundaries."""
import hashlib
from pathlib import Path
from fdisbull.game_il import GameMachine, author_program

SOURCES=Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources'
def code(*names):return '\n'.join((SOURCES/n).read_text() for n in names)

def test_selected_projection_preserves_unknown_value():
 m=GameMachine(author_program(code('shadowrun_enemy_outer.c','shadowrun_enemy_projection.c')), {})
 m.set_state({'shadowrun_ai_outer_kind':11,'shadowrun_ai_outer_flags':37,'shadowrun_ai_outer_flags_low':16,
   'shadowrun_ai_outer_hp':10,'shadowrun_ai_outer_max_hp':10,'shadowrun_ai_outer_callback':0xb574,
   'shadowrun_ai_outer_animation':56,'shadowrun_ai_outer_selected_value':123,'shadowrun_ai_outer_d0_valid':0})
 m.call('shadowrun_ai_outer_prepare');assert m.snapshot()['shadowrun_ai_outer_supported']==0
 m.call('shadowrun_ai_outer_movement_projection');s=m.snapshot()
 assert (s['shadowrun_ai_outer_supported'],s['shadowrun_ai_outer_schedule'],s['shadowrun_ai_outer_b3_unknown'],s['shadowrun_ai_outer_selected_value'],s['shadowrun_ai_outer_flags_low'])==(1,1,1,123,16)

def test_overlap_threshold_uses_live_links_and_source_order():
 m=GameMachine(author_program(code('shadowrun_enemy_overlap.c','shadowrun_enemy_overlap_one.c')), {})
 m.set_state({'shadowrun_ai_overlap_flags':[1,1]+[0]*8,'shadowrun_ai_overlap_x':[1000,1100]+[0]*8,
   'shadowrun_ai_overlap_y':[1000,1000]+[0]*8,'shadowrun_ai_overlap_slot':0})
 m.call('shadowrun_ai_overlap_check_one');assert m.snapshot()['shadowrun_ai_overlap_supported']==1
 m.set_state({'shadowrun_ai_overlap_target':[0xff0200]+[0]*9});m.call('shadowrun_ai_overlap_check_one')
 assert m.snapshot()['shadowrun_ai_overlap_supported']==0
 m.set_state({'shadowrun_ai_overlap_slot':1});m.call('shadowrun_ai_overlap_check_one')
 assert m.snapshot()['shadowrun_ai_overlap_supported']==1

def test_clock_expiry_clears_ten_original_records():
 m=GameMachine(author_program(code('shadowrun_enemy_combat_clock.c')), {})
 m.set_state({'shadowrun_ai_clock_combat':65535,'shadowrun_ai_clock_timer':0,'shadowrun_ai_clock_scene':2,
   'shadowrun_ai_clock_target':[1]*10,'shadowrun_ai_clock_attacker':[2]*10,'shadowrun_ai_clock_selected_value':[3]*10,
   'shadowrun_ai_clock_event_flags':[255]*10,'shadowrun_ai_clock_flags_low':[255]*10})
 m.call('shadowrun_ai_clock_tick');s=m.snapshot()
 assert (s['shadowrun_ai_clock_result'],s['shadowrun_ai_clock_combat'],s['shadowrun_ai_clock_timer'])==(2,0,65535)
 assert s['shadowrun_ai_clock_target']==[0]*10 and s['shadowrun_ai_clock_attacker']==[0]*10
 assert s['shadowrun_ai_clock_selected_value']==[0]*10 and s['shadowrun_ai_clock_event_flags']==[191]*10 and s['shadowrun_ai_clock_flags_low']==[239]*10

def test_wound_animation_counter_and_negative_selector():
 header='''typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
 u16 rom16(u8 region,u32 offset);u32 rom32(u8 region,u32 offset);
 u16 shadowrun_ai_kind,shadowrun_ai_animation;u32 shadowrun_ai_callback;u8 shadowrun_ai_flags_low;'''
 data=bytearray(0x6500);data[0x62d8:0x62dc]=(0x6300).to_bytes(4,'big');data[0x637c:0x6380]=(0x6400).to_bytes(4,'big');data[0x6400:0x6404]=bytes.fromhex('80020300');raw=bytes(data)
 m=GameMachine(author_program(header+code('shadowrun_enemy_wound_animation.c'),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
 m.set_state({'shadowrun_ai_kind':11,'shadowrun_ai_callback':0xb07e,'shadowrun_ai_animation':0x7c,
   'shadowrun_ai_wound_threshold':4096,'shadowrun_ai_wound_increment':768,'shadowrun_ai_wound_accumulator':4000,'shadowrun_ai_wound_index':1})
 m.call('shadowrun_ai_wound_advance');m.call('shadowrun_ai_wound_select');s=m.snapshot()
 assert (s['shadowrun_ai_wound_anim_supported'],s['shadowrun_ai_animation'],s['shadowrun_ai_wound_accumulator'],s['shadowrun_ai_wound_index'])==(1,0x807c,672,1)

def test_hostile_corridor_pursuit_uses_live_terrain_and_refuses_clear_north():
 data=bytearray(0xd5000);data[0x13e7c:0x13e7e]=(0x1000).to_bytes(2,'big');raw=bytes(data)
 m=GameMachine(author_program(code('shadowrun_collision.c','shadowrun_hostile_pursuit.c'),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
 terrain=[0]*2816;current=0x55f
 for index in (0x51f,0x51e,0x51d):terrain[index]=127
 m.set_state({'shadowrun_terrain_map':terrain,'shadowrun_hostile_pursuit_x':16096,'shadowrun_hostile_pursuit_y':11210,
  'shadowrun_hostile_pursuit_player_x':15584,'shadowrun_hostile_pursuit_player_y':11210,'shadowrun_hostile_pursuit_kind':8,
  'shadowrun_hostile_pursuit_flags':5,'shadowrun_hostile_pursuit_item':10,'shadowrun_hostile_pursuit_target':0xff0100,
  'shadowrun_hostile_pursuit_counter':6})
 m.call('shadowrun_hostile_pursuit_tick');s=m.snapshot()
 assert (s['shadowrun_hostile_pursuit_supported'],s['shadowrun_hostile_pursuit_path0'],s['shadowrun_hostile_pursuit_path1'],s['shadowrun_hostile_pursuit_heading'],s['shadowrun_hostile_pursuit_distance'])==(1,0x55c,0x51c,0xc000,1605)
 terrain[current-64]=0;m.set_state({'shadowrun_terrain_map':terrain,'shadowrun_hostile_pursuit_counter':6,'shadowrun_hostile_pursuit_event':0,'shadowrun_hostile_pursuit_direction':0})
 m.call('shadowrun_hostile_pursuit_tick');assert m.snapshot()['shadowrun_hostile_pursuit_supported']==0

def test_hostile_armor_and_depletion_are_separate_from_dodge():
 data=bytearray(0xd5000);data[0xd4d50+2*48+37]=5;raw=bytes(data)
 m=GameMachine(author_program(code('shadowrun_field_action.c','shadowrun_hostile_received_hit.c'),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
 m.set_state({'shadowrun_hostile_received_profile':1,'shadowrun_hostile_received_kind':8,'shadowrun_hostile_received_armor':3,
  'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,
  'shadowrun_field_target_flags':5,'shadowrun_field_target_type':2,'shadowrun_field_target_defense_bonus':5,
  'shadowrun_field_target_a':5,'shadowrun_field_target_b':4,'shadowrun_field_target_c':3,'shadowrun_field_target_posture':2,
  'shadowrun_field_target_hp':4,'shadowrun_field_target_x':1000,'shadowrun_field_target_y':1000,
  'shadowrun_field_projectile_x':1000,'shadowrun_field_projectile_y':1000,'shadowrun_field_rng':0x9d2f,'shadowrun_field_source_effect':7})
 m.call('shadowrun_hostile_received_hit');s=m.snapshot()
 assert (s['shadowrun_hostile_received_supported'],s['shadowrun_field_target_hp'])==(1,2)

def test_player_wound_readiness_comes_from_source_sprite_counter():
 data=bytearray(0xc082);data[0x62b8:0x62bc]=(0x6300).to_bytes(4,'big');data[0x6360:0x6364]=(0x6400).to_bytes(4,'big');data[0x6400:0x6404]=bytes.fromhex('80020300');data[0xc072:0xc074]=(0x60).to_bytes(2,'big');raw=bytes(data)
 m=GameMachine(author_program(code('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_player_reaction.c'),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
 m.set_state({'shadowrun_reaction_kind':3,'shadowrun_reaction_flags':15,'shadowrun_reaction_hp':10,'shadowrun_reaction_max_hp':10,
  'shadowrun_reaction_heading':0,'shadowrun_reaction_increment':480,'shadowrun_reaction_threshold':4096,'shadowrun_reaction_action_timer':37})
 m.call('shadowrun_reaction_start');m.call('shadowrun_reaction_outer_gate');assert m.snapshot()['shadowrun_reaction_admitted']==0
 for _ in range(12):
  m.call('shadowrun_reaction_advance');assert m.snapshot()['shadowrun_reaction_supported']==1
  m.call('shadowrun_reaction_select');assert m.snapshot()['shadowrun_reaction_supported']==1
 m.call('shadowrun_reaction_outer_gate');s=m.snapshot()
 assert (s['shadowrun_reaction_admitted'],s['shadowrun_reaction_animation'],s['shadowrun_reaction_index'])==(1,0x8060,1)

def test_hostile_item10_self_contact_rolls_then_armor_absorbs():
 data=bytearray(0xd5000);data[0xd4d50+2*48+37]=5;raw=bytes(data)
 m=GameMachine(author_program(code('shadowrun_hostile_self_hit.c'),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
 m.set_state({'shadowrun_selfhit_profile':1,'shadowrun_selfhit_effect':1,'shadowrun_selfhit_hp':10,'shadowrun_selfhit_rng':52645})
 m.call('shadowrun_hostile_self_hit');s=m.snapshot()
 assert (s['shadowrun_selfhit_supported'],s['shadowrun_selfhit_hp'],s['shadowrun_selfhit_rng'])==(1,10,30034)
 m.set_state({'shadowrun_selfhit_effect':0,'shadowrun_selfhit_rng':52645});m.call('shadowrun_hostile_self_hit');s=m.snapshot()
 assert (s['shadowrun_selfhit_hp'],s['shadowrun_selfhit_rng'])==(10,52645)
