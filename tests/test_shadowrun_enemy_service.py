"""Scheduler boundaries; native source comparisons are in the private receipt."""
import hashlib
from pathlib import Path
import pytest
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_enemy_service import SOURCE, lift_enemy_service
from fdisbull.shadowrun_linked_heading import SOURCE as HEADING

ACTOR = '''
typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u16 shadowrun_ai_x, shadowrun_ai_y, shadowrun_ai_target_heading, shadowrun_ai_kind;
u16 shadowrun_ai_distance, shadowrun_ai_collision_state, shadowrun_ai_animation;
u32 shadowrun_ai_callback;
u8 shadowrun_ai_flags, shadowrun_ai_equipment_flags, shadowrun_ai_event_flags;
u16 shadowrun_ai_combat_global;
'''

def machine():
    rom = bytes(0x16396)
    src = '\n'.join((ACTOR, HEADING.read_text(), SOURCE.read_text()))
    program = author_program(src, [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    m.set_state({'shadowrun_ai_kind': 11, 'shadowrun_ai_flags': 37,
                 'shadowrun_ai_equipment_flags': 32, 'shadowrun_ai_collision_state': 4096,
                 'shadowrun_ai_x': 1000, 'shadowrun_ai_y': 1000,
                 'shadowrun_ai_waypoint_x': 2000, 'shadowrun_ai_waypoint_y': 1100,
                 'shadowrun_ai_target_heading': 99, 'shadowrun_ai_distance': 88,
                 'shadowrun_ai_callback': 0xb574})
    return m

def test_countdown_and_waypoint_refresh():
    m=machine();m.set_state({'shadowrun_ai_service_timer':1})
    m.call('shadowrun_ai_service_tick');s=m.snapshot()
    assert (s['shadowrun_ai_service_supported'], s['shadowrun_ai_service_timer'], s['shadowrun_ai_distance']) == (1,0,88)
    m.call('shadowrun_ai_service_tick');s=m.snapshot()
    assert (s['shadowrun_ai_service_supported'],s['shadowrun_ai_service_timer'],s['shadowrun_ai_distance'],s['shadowrun_ai_service_result']) == (1,20,1050,1)

def test_combat_idle_and_damage_animation_gate():
    m=machine();m.set_state({'shadowrun_ai_combat_global':65535,'shadowrun_ai_animation':32})
    m.call('shadowrun_ai_service_tick');s=m.snapshot()
    assert (s['shadowrun_ai_service_supported'],s['shadowrun_ai_callback'],s['shadowrun_ai_service_timer']) == (1,0xb45c,20)
    m.set_state({'shadowrun_ai_callback':0xb574,'shadowrun_ai_service_timer':0,'shadowrun_ai_animation':124})
    m.call('shadowrun_ai_service_tick');s=m.snapshot()
    assert (s['shadowrun_ai_service_supported'],s['shadowrun_ai_callback'],s['shadowrun_ai_service_result']) == (1,0xb574,3)

@pytest.mark.parametrize('change', [
    {'shadowrun_ai_service_contact':1}, {'shadowrun_ai_waypoint_x':1001,'shadowrun_ai_waypoint_y':1001},
    {'shadowrun_ai_kind':3}, {'shadowrun_ai_service_pause':1}, {'shadowrun_ai_event_flags':2},
])
def test_unmodeled_expiry_refuses_without_actor_mutation(change):
    m=machine();m.set_state(change);m.call('shadowrun_ai_service_tick');s=m.snapshot()
    assert (s['shadowrun_ai_service_supported'],s['shadowrun_ai_service_timer'],s['shadowrun_ai_target_heading'],s['shadowrun_ai_distance'],s['shadowrun_ai_callback']) == (0,0,99,88,0xb574)

def test_source_identity_required():
    with pytest.raises(ValueError): lift_enemy_service(b'')

def test_waypoint_arrival_advances_and_wraps_source_table():
    from fdisbull.shadowrun_enemy_waypoint import SOURCE as WAYPOINT
    rom = bytearray(0x172d88)
    rom[0x172d58:0x172d60] = bytes.fromhex('03e807d00bb80fa0')
    raw = bytes(rom)
    src='\n'.join((ACTOR, HEADING.read_text(), SOURCE.read_text(), WAYPOINT.read_text()))
    m=GameMachine(author_program(src,[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]),{0:raw})
    m.set_state({'shadowrun_ai_kind':11,'shadowrun_ai_flags':37,'shadowrun_ai_equipment_flags':32,
                 'shadowrun_ai_x':1000,'shadowrun_ai_y':2000,
                 'shadowrun_ai_waypoint_x':1000,'shadowrun_ai_waypoint_y':2000,
                 'shadowrun_ai_waypoint_table':0x172d58})
    m.call('shadowrun_ai_waypoint_arrival');s=m.snapshot()
    assert (s['shadowrun_ai_waypoint_supported'],s['shadowrun_ai_waypoint_index'],s['shadowrun_ai_waypoint_x'],s['shadowrun_ai_waypoint_y'],s['shadowrun_ai_callback'],s['shadowrun_ai_event_flags']) == (1,4,3000,4000,0xb45c,4)
    m.set_state({'shadowrun_ai_x':3000,'shadowrun_ai_y':4000,'shadowrun_ai_service_timer':0})
    m.call('shadowrun_ai_waypoint_arrival');s=m.snapshot()
    assert (s['shadowrun_ai_waypoint_supported'],s['shadowrun_ai_waypoint_index'],s['shadowrun_ai_waypoint_x'],s['shadowrun_ai_waypoint_y']) == (1,0,1000,2000)
