"""NPC control preserves source turns and exposes completion to dispatch."""
import hashlib

from fdisbull.game_il import author_program,GameMachine
from fdisbull.shadowrun_snes_npc import SOURCE


def machine():
    raw=bytearray(0x61500)
    raw[0x47a0:0x47a2]=(2).to_bytes(2,'little')
    raw[0x601e0:0x601f0]=bytes((0,1,3,0,5,0,5,24,8,10,12,14,16,18,20,22))
    raw[0x60208:0x60210]=bytes((8,16,24,32,40,48,56,64))
    raw[0x61472:0x61482]=bytes((24,5,2,242,2,242,2,32,0,0,0,0,0,8,0,0))
    program=author_program(SOURCE.read_text(),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    m=GameMachine(program,{0:bytes(raw)})
    m.set_state({'npc_x':100,'npc_y':200,'npc_target_x':200,'npc_target_y':200,
                 'npc_timer':1,'npc_direction':2,'npc_task':65535,'npc_action':1,'npc_anim_kind':3,
                 'npc_anim_table':0x8208,'npc_anim_reload':4,'npc_anim_timer':1,
                 'npc_anim_increment':14,'npc_anim_phase':126,'npc_anim_selector':32})
    return m


def test_target_control_uses_rom_velocity_and_source_countdown():
    m=machine();m.call('shadowrun_snes_npc_control',0)
    s=m.snapshot();assert (s['npc_supported'],s['npc_timer'],s['npc_velocity_x'],s['npc_velocity_y'])==(1,2,2,0)
    m.set_state({'npc_velocity_x':19});m.call('shadowrun_snes_npc_control',0)
    s=m.snapshot();assert (s['npc_timer'],s['npc_velocity_x'])==(1,19)


def test_direction_change_uses_source_table_and_animation_tick():
    m=machine();m.set_state({'npc_target_x':105,'npc_target_y':300})
    m.call('shadowrun_snes_npc_control',0)
    s=m.snapshot()
    assert (s['npc_supported'],s['npc_direction'],s['npc_anim_selector'],s['npc_anim_phase'])==(1,0,16,128)
    m.call('shadowrun_snes_npc_animate')
    s=m.snapshot()
    assert (s['npc_supported'],s['npc_anim_phase'],s['npc_anim_timer'],s['npc_anim_selector'])==(1,14,4,10)


def test_unqualified_direction_follow_and_script_signal_are_refused():
    for changes in ({'npc_direction':0,'npc_anim_reload':0},{'npc_target_x':0}):
        m=machine();m.set_state(changes);m.call('shadowrun_snes_npc_control',0)
        assert m.snapshot()['npc_supported']==0
    m=machine();m.set_state({'npc_target_x':105,'npc_target_y':200,'npc_task':18,'npc_velocity_x':2})
    m.call('shadowrun_snes_npc_control',0);s=m.snapshot()
    assert (s['npc_supported'],s['npc_arrived'],s['npc_completion_pending'],s['npc_completion_task'],s['npc_velocity_x'])==(1,1,1,18,0)
    m=machine();m.set_state({'npc_target_x':105,'npc_target_y':200,'npc_velocity_x':2})
    m.call('shadowrun_snes_npc_control',0);s=m.snapshot()
    assert (s['npc_supported'],s['npc_arrived'],s['npc_velocity_x'],s['npc_velocity_y'])==(1,1,0,0)


def test_action_zero_and_direction_setup_match_observed_record():
    m=machine();m.set_state({'npc_requested_action':0})
    m.call('shadowrun_snes_npc_action',0)
    m.set_state({'npc_requested_direction':6});m.call('shadowrun_snes_npc_direction',0)
    s=m.snapshot()
    assert (s['npc_action'],s['npc_direction'],s['npc_anim_reload'],s['npc_anim_pending'])==(0,6,129,65535)
    m.call('shadowrun_snes_npc_animate');s=m.snapshot()
    assert (s['npc_supported'],s['npc_anim_reload'],s['npc_anim_selector'],s['npc_anim_phase'],s['npc_anim_dy'],s['npc_anim_extra'])==(1,0,22,0,5,24)
    m.set_state({'npc_anim_kind':4,'npc_requested_action':0,'npc_action':1})
    m.call('shadowrun_snes_npc_action',0);assert m.snapshot()['npc_supported']==0


def test_kind_24_one_shot_signals_animation_completion():
    m=machine();m.set_state({'npc_anim_kind':24,'npc_direction':5,
                             'npc_task':8,'npc_requested_action':6})
    m.call('shadowrun_snes_npc_action',0)
    s=m.snapshot()
    assert (s['npc_supported'],s['npc_anim_dx'],s['npc_anim_reload'])==(1,65522,133)
    for _ in range(40):
        m.call('shadowrun_snes_npc_animate');s=m.snapshot()
        assert s['npc_supported']==1
        if s['npc_animation_completion_pending']:break
    else:raise AssertionError('one-shot animation did not finish')
    assert (s['npc_action'],s['npc_anim_increment'],s['npc_anim_timer'])==(0x8006,0,0)
