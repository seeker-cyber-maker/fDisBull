"""Ordered actor adapter boundaries; core comparisons run separately."""
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_field_combat import SOURCE as FIELD
from fdisbull.shadowrun_linked_heading import SOURCE as HEADING,SPAWN_SOURCE,LINKED_MOTION_SOURCE
from fdisbull.shadowrun_linked_actors import SOURCE,SHIM

def machine():
    parts=(FIELD.with_name('shadowrun_collision.c'),FIELD.with_name('shadowrun_collision_resolve.c'),FIELD,HEADING,SPAWN_SOURCE,LINKED_MOTION_SOURCE)
    m=GameMachine(author_program('\n'.join([*(p.read_text() for p in parts),SHIM,SOURCE.read_text()])),{})
    m.set_state({'shadowrun_actors_profile':1,'shadowrun_linked_motion_state':1,'shadowrun_linked_motion_steps':8,
      'shadowrun_linked_motion_lifetime':119,'shadowrun_linked_x_fixed':0x4ea7a800,'shadowrun_linked_y_fixed':0x318f5000,
      'shadowrun_linked_velocity_x':0x5ef5,'shadowrun_linked_velocity_y':0xf1ea,'shadowrun_field_actor_index':0,
      'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,
      'shadowrun_field_ammo':11,'shadowrun_field_source_effect':4,'shadowrun_field_rng':0x9d2f,
      'shadowrun_target_x':[0x4f06]*7,'shadowrun_target_y':[0x3181]*7,'shadowrun_target_flags_b0':[0]*7,
      'shadowrun_terrain_map':[0]*2816,'shadowrun_x_min':44,'shadowrun_x_max':1876,
      'shadowrun_y_min':44,'shadowrun_y_max':1304})
    return m

def test_source_order_chooses_first_eligible_actor():
    m=machine();m.set_state({'shadowrun_target_flags':[0x25,0x25,0,0,0,0,0],'shadowrun_play_actor_hp':[10,10,0,0,0,0,0]})
    m.call('shadowrun_actors_tick');s=m.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_actors_hit_slot'],s['shadowrun_play_actor_hp'][:2]) == (1,0,[6,10])

def test_unqualified_eligible_actor_is_refused_without_damage():
    m=machine();m.set_state({'shadowrun_target_flags':[0,0,0,1,0,0,0],'shadowrun_play_actor_hp':[0,0,0,10,0,0,0]})
    m.call('shadowrun_actors_tick');s=m.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_play_actor_hp'][3],s['shadowrun_field_rng']) == (0,10,0x9d2f)
