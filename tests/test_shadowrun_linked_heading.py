"""Domain and signed-vector checks; original-core qualification is separate."""
import hashlib
import pytest
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_linked_heading import SOURCE,SPAWN_SOURCE,lift_linked_heading,lift_linked_spawn

def test_heading_refuses_unrepresentable_signed_delta():
    m=GameMachine(author_program(SOURCE.read_text()),{})
    m.set_state({'shadowrun_linked_source_x':0,'shadowrun_linked_source_y':0,
      'shadowrun_linked_target_x':32768,'shadowrun_linked_target_y':0,
      'shadowrun_linked_heading':1234,'shadowrun_linked_metric':5678})
    m.call('shadowrun_linked_measure');s=m.snapshot()
    assert (s['shadowrun_linked_supported'],s['shadowrun_linked_heading'],s['shadowrun_linked_metric']) == (0,1234,5678)

def test_spawn_signed_vector_rounds_toward_negative_infinity():
    region=bytearray(0x16396);region[0x15e56:0x15e58]=bytes.fromhex('ffff');region[0x15e16:0x15e18]=bytes.fromhex('0001')
    raw=bytes(region);program=author_program(SPAWN_SOURCE.read_text(),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    m=GameMachine(program,{0:raw});m.set_state({'shadowrun_spawn_source_x':1000,'shadowrun_spawn_source_y':1000,'shadowrun_spawn_heading':0})
    m.call('shadowrun_linked_spawn');s=m.snapshot()
    assert (s['shadowrun_spawn_supported'],s['shadowrun_spawn_velocity_x'],s['shadowrun_spawn_velocity_y']) == (1,65535,0)

@pytest.mark.parametrize('lift',[lift_linked_heading,lift_linked_spawn])
def test_original_identity_required(lift):
    with pytest.raises(ValueError):lift(b'')

def test_linked_projectile_hits_captured_actor_without_new_shot():
    from fdisbull.shadowrun_field_combat import SOURCE as FIELD
    from fdisbull.shadowrun_linked_heading import LINKED_MOTION_SOURCE
    parts=(FIELD.with_name('shadowrun_collision.c'),FIELD.with_name('shadowrun_collision_resolve.c'),
           FIELD,SOURCE,SPAWN_SOURCE,LINKED_MOTION_SOURCE)
    m=GameMachine(author_program('\n'.join(p.read_text() for p in parts)),{})
    m.set_state({'shadowrun_linked_profile':1,'shadowrun_linked_motion_state':1,
      'shadowrun_linked_motion_steps':8,'shadowrun_linked_motion_lifetime':119,
      'shadowrun_linked_x_fixed':0x4ea7a800,'shadowrun_linked_y_fixed':0x318f5000,
      'shadowrun_linked_velocity_x':0x5ef5,'shadowrun_linked_velocity_y':0xf1ea,
      'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,
      'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,'shadowrun_field_target_flags':0x25,
      'shadowrun_field_target_flags_9e':0x21,'shadowrun_field_target_type':19,
      'shadowrun_field_target_defense_bonus':2,'shadowrun_field_target_x':0x4f06,
      'shadowrun_field_target_y':0x3181,'shadowrun_field_target_hp':10,'shadowrun_field_target_a':1,
      'shadowrun_field_target_b':2,'shadowrun_field_target_c':2,'shadowrun_field_target_posture':2,
      'shadowrun_field_source_effect':4,'shadowrun_field_rng':0x9d2f,
      'shadowrun_terrain_map':[0]*2816,'shadowrun_x_min':44,'shadowrun_x_max':1876,
      'shadowrun_y_min':44,'shadowrun_y_max':1304})
    m.call('shadowrun_linked_tick');s=m.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_linked_motion_state'],s['shadowrun_field_ammo'],
      s['shadowrun_linked_x_fixed'],s['shadowrun_linked_y_fixed'],s['shadowrun_linked_motion_lifetime'],
      s['shadowrun_field_target_hp'],s['shadowrun_field_rng']) == (1,2,11,0x4f069d00,0x31913a00,118,6,0x861b)
