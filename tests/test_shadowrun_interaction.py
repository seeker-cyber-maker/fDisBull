from pathlib import Path
import pytest
from fdisbull.game_il import author_program, GameMachine
from fdisbull.shadowrun_interaction import SOURCE, lift_stoker_interaction


def _machine():
    return GameMachine(author_program(SOURCE.read_text()), {})


@pytest.mark.parametrize('phase,address', [(0,0xf4aa0),(1,0xf4af4),(127,0xf4af4),(128,0xf4aec),(255,0xf4aec)])
def test_scene2_stoker_selection(phase,address):
    m=_machine();m.set_state({'shadowrun_interaction_context':2,'shadowrun_interaction_target':2,
                              'shadowrun_interaction_phase':phase});m.call('shadowrun_select_interaction');s=m.snapshot()
    assert (s['shadowrun_interaction_supported'],s['shadowrun_interaction_dialogue_id'],
            s['shadowrun_interaction_prompt_offset'],s['shadowrun_interaction_portrait_offset']) == (1,20,address,0x121fa0)


def test_other_sites_do_not_claim_support():
    m=_machine();m.set_state({'shadowrun_interaction_context':2,'shadowrun_interaction_target':1,
                              'shadowrun_interaction_dialogue_id':0xa5,'shadowrun_interaction_prompt_offset':0x11111111})
    m.call('shadowrun_select_interaction');s=m.snapshot()
    assert s['shadowrun_interaction_supported']==0
    assert s['shadowrun_interaction_dialogue_id']==0xa5 and s['shadowrun_interaction_prompt_offset']==0x11111111


def test_profile_rejects_other_roms():
    with pytest.raises(ValueError,match='exact reviewed'):lift_stoker_interaction(bytes(2097152))


@pytest.mark.parametrize('raw,event', [(0,0),(0x7f,31),(0xff80,0),(0xffc2,2),(0xffff,31),(0xabc2,2)])
def test_collision_event_projection(raw,event):
    m=_machine();m.set_state({'shadowrun_interaction_raw_collision':raw});m.call('shadowrun_decode_collision_event');s=m.snapshot()
    assert s['shadowrun_interaction_actor_collision']==raw
    assert s['shadowrun_interaction_event_index']==event


def test_two_negative_collision_corners_are_needed():
    m=_machine()
    for bits in range(16):
        values=[(0xc2 if bits & (1<<i) else 0x42) for i in range(4)]
        m.set_state({f'shadowrun_interaction_corner{i}':v for i,v in enumerate(values)})
        m.call('shadowrun_check_event_corners');s=m.snapshot()
        assert s['shadowrun_interaction_negative_count']==bits.bit_count()
        assert s['shadowrun_interaction_corner_gate']==(bits.bit_count()>=2)


def test_source_branch_and_carry_transition():
    m=_machine();m.set_state({'shadowrun_interaction_event_index':2,'shadowrun_interaction_event_mode':0,
        'shadowrun_interaction_scene_mode':2,'shadowrun_interaction_reaction_flag':0,'shadowrun_interaction_visited_flag':0})
    m.call('shadowrun_interaction_source_branch');s=m.snapshot()
    assert (s['shadowrun_interaction_source_target'],s['shadowrun_interaction_source_proceeds'])==(2,1)
    m.set_state({'shadowrun_interaction_dispatch_carry':1});m.call('shadowrun_interaction_source_transition');s=m.snapshot()
    assert (s['shadowrun_interaction_transition_flag'],s['shadowrun_interaction_transition_timer'],s['shadowrun_interaction_trigger_busy'])==(65535,16,65535)


def test_stoker_request_guard_and_modal_edge_handling():
    m=_machine();values={'shadowrun_interaction_context':2,'shadowrun_interaction_phase':0,
       'shadowrun_interaction_scene_mode':2,'shadowrun_interaction_event_mode':0,
       'shadowrun_interaction_actor_flags':15,'shadowrun_interaction_dispatch_carry':1,
       'shadowrun_interaction_raw_collision':0xffc2,'shadowrun_interaction_corner0':0xc2,
       'shadowrun_interaction_corner1':0xc2,'shadowrun_interaction_corner2':0,'shadowrun_interaction_corner3':0}
    m.set_state(values);m.call('shadowrun_request_stoker');s=m.snapshot()
    assert s['shadowrun_interaction_requested']==1 and s['shadowrun_interaction_target']==2
    assert s['shadowrun_interaction_prompt_offset']==0xf4aa0 and s['shadowrun_interaction_event_latch']==32
    m.call('shadowrun_stoker_ui_begin',1)
    for pad,mode in [(1,1),(64,2),(64,2),(0,2),(32,2),(0,2),(16,3),(0,3),(64,4),(64,4),(0,0)]:
        m.call('shadowrun_stoker_ui_tick',pad);assert m.snapshot()['shadowrun_stoker_ui_mode']==mode
    m.set_state({'shadowrun_interaction_trigger_busy':0,'shadowrun_interaction_event_latch':0,
                 'shadowrun_interaction_scene_mode':3})
    m.call('shadowrun_request_stoker');assert m.snapshot()['shadowrun_interaction_requested']==0


@pytest.mark.parametrize('override', [
    {'shadowrun_interaction_context':3}, {'shadowrun_interaction_phase':1}, {'shadowrun_interaction_scene_mode':20},
    {'shadowrun_interaction_event_mode':1}, {'shadowrun_interaction_trigger_busy':1},
    {'shadowrun_interaction_event_latch':32}, {'shadowrun_interaction_actor_flags':13},
    {'shadowrun_interaction_actor_flags':31}, {'shadowrun_interaction_actor_flags':79},
    {'shadowrun_interaction_reaction_flag':1}, {'shadowrun_interaction_dispatch_carry':0},
    {'shadowrun_interaction_raw_collision':0xffc3}, {'shadowrun_interaction_corner1':0},
])
def test_request_refuses_unqualified_paths(override):
    m=_machine();values={'shadowrun_interaction_context':2,'shadowrun_interaction_phase':0,
       'shadowrun_interaction_scene_mode':2,'shadowrun_interaction_event_mode':0,
       'shadowrun_interaction_actor_flags':15,'shadowrun_interaction_dispatch_carry':1,
       'shadowrun_interaction_raw_collision':0xffc2,'shadowrun_interaction_corner0':0xc2,
       'shadowrun_interaction_corner1':0xc2,'shadowrun_interaction_corner2':0,'shadowrun_interaction_corner3':0}
    values.update(override);m.set_state(values);m.call('shadowrun_request_stoker')
    assert m.snapshot()['shadowrun_interaction_requested']==0
