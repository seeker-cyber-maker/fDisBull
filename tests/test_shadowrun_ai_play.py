"""Native procedure selection preserves public entry-point dependencies."""
import pytest
import hashlib
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_ai_play import emit_reachable_c, SLOT_SOURCE
from fdisbull.shadowrun_enemy_move import SOURCE as MOVE_SOURCE
from fdisbull.shadowrun_enemy_service import SOURCE as SERVICE_SOURCE
from fdisbull.shadowrun_enemy_outer import SOURCE as OUTER_SOURCE
from fdisbull.shadowrun_enemy_projection import SOURCE as PROJECTION_SOURCE
from fdisbull.shadowrun_enemy_overlap import SOURCE as OVERLAP_SOURCE
from fdisbull.shadowrun_enemy_overlap_one import SOURCE as OVERLAP_ONE_SOURCE
from fdisbull.shadowrun_enemy_visible import SOURCE as VISIBLE_SOURCE


def test_selects_transitive_calls_and_keeps_global_state():
    p=author_program('''typedef unsigned char u8; u8 x;
    void used_leaf(void){x=2;} void entry(void){used_leaf();}
    void unrelated(void){x=7;}''')
    source,receipt=emit_reachable_c(p,roots=['entry'])
    assert receipt['included']==['entry','used_leaf']
    assert receipt['omitted']==['unrelated']
    assert 'unsigned char' in source or 'typedef' in source
    assert 'unrelated(' not in source and 'used_leaf(' in source


def test_rejects_missing_or_empty_roots():
    p=author_program('void entry(void){}')
    for roots in ([],['missing']):
        with pytest.raises(ValueError,match='entry points'):
            emit_reachable_c(p,roots=roots)


def test_actor_service_commits_only_supported_changes():
    rom=bytearray(0xc100)
    rom[0xbe62:0xbe66]=bytes([0, 10, 0, 0])
    prefix='''typedef unsigned char u8; typedef unsigned int u16;
    typedef unsigned long u32; u16 shadowrun_fixed_x,shadowrun_fixed_y;
    u8 shadowrun_probe_flags,shadowrun_probe_corners[4],shadowrun_collision_status;
    u8 collision_refuse; u16 shadowrun_target_x[7],shadowrun_target_y[7];
    u8 shadowrun_target_flags[7],shadowrun_target_flags_low[7],shadowrun_target_flags_b0[7],shadowrun_play_actor_hp[7];
    u8 shadowrun_target_backlink[7],shadowrun_target_selected,shadowrun_player_flags;
    u16 shadowrun_player_x,shadowrun_player_y;
    u8 shadowrun_play_refused,shadowrun_target_supported;
    void shadowrun_opening_frame(u8 pad){} void shadowrun_target_refresh(void){}
    u16 shadowrun_target_contact[7],shadowrun_linked_source_x,shadowrun_linked_source_y;
    u16 shadowrun_linked_target_x,shadowrun_linked_target_y,shadowrun_linked_heading,shadowrun_linked_metric;
    u8 shadowrun_linked_supported;
    void shadowrun_linked_measure(void){shadowrun_linked_supported=0;}
    void shadowrun_collision_check(void){shadowrun_collision_status=collision_refuse;}
    '''
    source='\n'.join(line for line in MOVE_SOURCE.read_text().splitlines()
                     if not line.startswith('typedef '))
    service='\n'.join(line for path in (SERVICE_SOURCE,OUTER_SOURCE,PROJECTION_SOURCE,OVERLAP_SOURCE,OVERLAP_ONE_SOURCE,VISIBLE_SOURCE)
                      for line in path.read_text().splitlines()
                      if not line.startswith('typedef '))
    p=author_program(prefix+source+service+SLOT_SOURCE.read_text(),
                     [{'id':0,'length':len(rom),'sha256':hashlib.sha256(rom).hexdigest()}])
    m=GameMachine(p,{0:bytes(rom)})
    m.set_state({'shadowrun_ai_slot_status':[1,0,0,0,0,0,0],
        'shadowrun_target_x':[100,0,0,0,0,0,0], 'shadowrun_target_y':[200,0,0,0,0,0,0],
        'shadowrun_target_flags':[37,0,0,0,0,0,0],
        'shadowrun_ai_slot_equipment_flags':[32,0,0,0,0,0,0],
        'shadowrun_ai_slot_attribute':[1,0,0,0,0,0,0],
        'shadowrun_ai_slot_kind':[11,0,0,0,0,0,0],
        'shadowrun_ai_slot_callback':[0xb574,0,0,0,0,0,0],
        'shadowrun_ai_slot_distance':[2000,0,0,0,0,0,0]})
    m.call('shadowrun_ai_service_slot',0)
    s=m.snapshot()
    assert (s['shadowrun_target_x'][0],s['shadowrun_target_y'][0],s['shadowrun_ai_slot_status'][0])==(110,200,1)
    m.set_state({'collision_refuse':1})
    m.call('shadowrun_ai_service_slot',0)
    s=m.snapshot()
    assert (s['shadowrun_target_x'][0],s['shadowrun_target_y'][0],s['shadowrun_ai_slot_status'][0])==(110,200,2)
    m.set_state({'collision_refuse':0})
    m.call('shadowrun_ai_service_slot',0)
    assert m.snapshot()['shadowrun_target_x'][0]==110
    m.set_state({'shadowrun_ai_slot_status':[1,1,1,0,0,0,0]})
    m.call('shadowrun_ai_frame',16)
    s=m.snapshot()
    assert s['shadowrun_play_refused']==1 and s['shadowrun_ai_slot_status'][:3]==[2,2,2]
