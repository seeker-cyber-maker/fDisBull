"""Public prepared-combat domain and state effects; native proof is separate."""
import pytest
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_field_combat import SOURCE, lift_field_combat

@pytest.fixture
def fight():
    m = GameMachine(author_program(SOURCE.read_text()), {})
    m.set_state({'shadowrun_field_actor_index':3,'shadowrun_field_item':1,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':1,'shadowrun_field_ammo':2,'shadowrun_field_slots_busy':0,
      'shadowrun_field_projectile_x':512,'shadowrun_field_projectile_y':512,
      'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,
      'shadowrun_field_target_flags':1,'shadowrun_field_target_hp':50,
      'shadowrun_field_target_a':20,'shadowrun_field_target_b':20,'shadowrun_field_target_c':20,
      'shadowrun_field_target_posture':0,'shadowrun_field_source_effect':30,'shadowrun_field_rng':1})
    return m

def test_prepared_hit_updates_hp_ammo_and_rng(fight):
    fight.call('shadowrun_field_fire')
    s = fight.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_outcome'],s['shadowrun_field_ammo'],
            s['shadowrun_field_slot'],s['shadowrun_field_target_hp'],s['shadowrun_field_rng']) == (1,4,1,9,40,47870)

def test_exhausted_slots_still_consume_ammo(fight):
    fight.set_state({'shadowrun_field_slots_busy':63})
    fight.call('shadowrun_field_fire')
    s=fight.snapshot()
    assert (s['shadowrun_field_outcome'],s['shadowrun_field_ammo'],s['shadowrun_field_target_hp'],s['shadowrun_field_rng']) == (1,1,50,1)

def test_collision_edges_and_empty_ammo(fight):
    fight.set_state({'shadowrun_field_projectile_x':656})
    fight.call('shadowrun_field_fire')
    s=fight.snapshot()
    assert (s['shadowrun_field_outcome'],s['shadowrun_field_target_hp'],s['shadowrun_field_rng']) == (2,50,1)
    fight.set_state({'shadowrun_field_ammo':0,'shadowrun_field_projectile_x':512})
    fight.call('shadowrun_field_fire')
    assert fight.snapshot()['shadowrun_field_outcome'] == 0

def test_unknown_depletion_is_refused_without_mutation(fight):
    fight.set_state({'shadowrun_field_target_hp':10})
    before=fight.snapshot()
    fight.call('shadowrun_field_fire')
    after=fight.snapshot()
    assert after['shadowrun_field_supported'] == 0
    for key in ('shadowrun_field_ammo','shadowrun_field_target_hp','shadowrun_field_rng'):
        assert after[key] == before[key]

def test_exact_source_required():
    with pytest.raises(ValueError):
        lift_field_combat(b'')

def test_captured_profile_composes_shot_and_prepared_hit(fight):
    fight.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_actor_index':0,
      'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,
      'shadowrun_field_ammo':12,'shadowrun_field_target_a':5,'shadowrun_field_target_b':5,
      'shadowrun_field_target_c':5,'shadowrun_field_rng':1})
    fight.call('shadowrun_field_captured_fire')
    s=fight.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_ammo'],s['shadowrun_field_first_slot'],
            s['shadowrun_field_second_slot'],s['shadowrun_field_source_effect'],
            s['shadowrun_field_target_hp'],s['shadowrun_field_rng']) == (1,11,9,10,3,47,14422)

def test_captured_profile_requires_attestation_and_two_slots(fight):
    fight.set_state({'shadowrun_field_captured_profile':0,'shadowrun_field_actor_index':0,
      'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,
      'shadowrun_field_ammo':12,'shadowrun_field_rng':1})
    fight.call('shadowrun_field_captured_fire')
    s=fight.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_ammo'],s['shadowrun_field_rng']) == (0,12,1)
    fight.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_slots_busy':62})
    fight.call('shadowrun_field_captured_fire')
    s=fight.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_ammo'],s['shadowrun_field_outcome'],
            s['shadowrun_field_first_slot'],s['shadowrun_field_source_effect']) == (1,11,1,9,3)
    assert s['shadowrun_field_rng'] != 1

@pytest.mark.parametrize('blocked,steps,state', [(True,30,3),(False,32,1)])
def test_captured_motion_uses_shared_terrain(blocked, steps, state):
    from fdisbull.shadowrun_field_combat import MOTION_SOURCE
    source = '\n'.join(p.read_text() for p in (
      SOURCE.with_name('shadowrun_collision.c'), SOURCE.with_name('shadowrun_collision_resolve.c'), SOURCE, MOTION_SOURCE))
    m=GameMachine(author_program(source), {})
    terrain=[0]*2816
    if blocked: terrain[1822]=127
    m.set_state({'shadowrun_field_captured_profile':1,'shadowrun_field_path_profile':1,
      'shadowrun_field_actor_index':0,'shadowrun_field_item':2,'shadowrun_field_equipped_slot':0,
      'shadowrun_field_source_flags':15,'shadowrun_field_ammo':12,'shadowrun_field_slots_busy':0,
      'shadowrun_field_target_flags':0,'shadowrun_field_target_x':512,'shadowrun_field_target_y':512,
      'shadowrun_field_target_hp':50,'shadowrun_field_target_a':5,'shadowrun_field_target_b':5,
      'shadowrun_field_target_c':5,'shadowrun_field_target_posture':0,'shadowrun_field_rng':1,
      'shadowrun_terrain_map':terrain,'shadowrun_x_min':44,'shadowrun_x_max':1876,
      'shadowrun_y_min':44,'shadowrun_y_max':1304,'shadowrun_rect_base':0x172daa})
    m.call('shadowrun_field_captured_launch')
    for _ in range(7): m.call('shadowrun_field_captured_tick')
    s=m.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_motion_steps'],s['shadowrun_field_motion_state']) == (1,steps,state)
    assert s['shadowrun_field_ammo'] == 11

def test_captured_actor_depletion_and_counters(fight):
    fight.set_state({'shadowrun_field_item':2,'shadowrun_field_source_flags':15,
      'shadowrun_field_target_flags':0x25,'shadowrun_field_target_flags_b0':0,
      'shadowrun_field_target_flags_9e':0x20,'shadowrun_field_target_flags_9a':0,
      'shadowrun_field_target_type':19,'shadowrun_field_target_hp':1,
      'shadowrun_field_target_a':1,'shadowrun_field_target_b':2,'shadowrun_field_target_c':2,
      'shadowrun_field_target_posture':2,'shadowrun_field_target_defense_bonus':2,
      'shadowrun_field_source_effect':4,'shadowrun_field_rng':0x9d2f,
      'shadowrun_field_death_timer':0,'shadowrun_field_type13_deaths':7,
      'shadowrun_field_party_counter_a':254,'shadowrun_field_party_counter_b':255,
      'shadowrun_field_party_counter_c':0})
    fight.call('shadowrun_field_fire');s=fight.snapshot()
    assert (s['shadowrun_field_supported'],s['shadowrun_field_target_hp'],s['shadowrun_field_target_depleted'],
      s['shadowrun_field_rng'],s['shadowrun_field_death_timer'],s['shadowrun_field_type13_deaths'],
      s['shadowrun_field_party_counter_a'],s['shadowrun_field_party_counter_b'],s['shadowrun_field_party_counter_c']) == (1,0,1,0x861b,15,8,255,0,1)

def test_zero_success_contact_does_not_roll_or_damage():
    from fdisbull.shadowrun_field_combat import MOTION_SOURCE
    source='\n'.join(p.read_text() for p in (SOURCE.with_name('shadowrun_collision.c'),
      SOURCE.with_name('shadowrun_collision_resolve.c'),SOURCE,MOTION_SOURCE))
    m=GameMachine(author_program(source),{})
    m.set_state({'shadowrun_field_path_profile':1,'shadowrun_field_actor_index':0,'shadowrun_field_item':2,
      'shadowrun_field_equipped_slot':0,'shadowrun_field_source_flags':15,'shadowrun_field_ammo':11,
      'shadowrun_field_target_flags':0x25,'shadowrun_field_target_flags_9e':0x20,
      'shadowrun_field_target_type':19,'shadowrun_field_target_hp':10,'shadowrun_field_target_a':1,
      'shadowrun_field_target_b':2,'shadowrun_field_target_c':2,'shadowrun_field_target_posture':2,
      'shadowrun_field_target_defense_bonus':2,'shadowrun_field_target_x':0x3ce0,'shadowrun_field_target_y':0x2e59,
      'shadowrun_field_source_effect':0,'shadowrun_field_rng':0x9d2f,'shadowrun_field_motion_state':1,
      'shadowrun_field_motion_steps':4,'shadowrun_field_motion_lifetime':123,'shadowrun_field_motion_y_fixed':0x2df9fc00,
      'shadowrun_terrain_map':[0]*2816,'shadowrun_x_min':44,'shadowrun_x_max':1876,
      'shadowrun_y_min':44,'shadowrun_y_max':1304})
    m.call('shadowrun_field_captured_tick');s=m.snapshot()
    assert (s['shadowrun_field_motion_state'],s['shadowrun_field_outcome'],s['shadowrun_field_target_hp'],
            s['shadowrun_field_rng'],s['shadowrun_field_motion_y_fixed'],s['shadowrun_field_motion_lifetime']) == (2,3,10,0x9d2f,0x2e69fb00,122)
