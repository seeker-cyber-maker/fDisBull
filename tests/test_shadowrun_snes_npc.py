"""A source NPC controller must expose unfinished dispatch and direction edges."""
import hashlib

from fdisbull.game_il import author_program,GameMachine
from fdisbull.shadowrun_snes_npc import SOURCE


def machine():
    raw=bytearray(0x4800)
    raw[0x47a0:0x47a2]=(2).to_bytes(2,'little')
    program=author_program(SOURCE.read_text(),[{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    m=GameMachine(program,{0:bytes(raw)})
    m.set_state({'npc_x':100,'npc_y':200,'npc_target_x':200,'npc_target_y':200,
                 'npc_timer':1,'npc_direction':2,'npc_task':65535})
    return m


def test_target_control_uses_rom_velocity_and_source_countdown():
    m=machine();m.call('shadowrun_snes_npc_control',0)
    s=m.snapshot();assert (s['npc_supported'],s['npc_timer'],s['npc_velocity_x'],s['npc_velocity_y'])==(1,2,2,0)
    m.set_state({'npc_velocity_x':19});m.call('shadowrun_snes_npc_control',0)
    s=m.snapshot();assert (s['npc_timer'],s['npc_velocity_x'])==(1,19)


def test_unqualified_direction_follow_and_script_signal_are_refused():
    for changes in ({'npc_direction':0},{'npc_target_x':0},
                    {'npc_target_x':105,'npc_target_y':200,'npc_task':0}):
        m=machine();m.set_state(changes);m.call('shadowrun_snes_npc_control',0)
        assert m.snapshot()['npc_supported']==0
    m=machine();m.set_state({'npc_target_x':105,'npc_target_y':200,'npc_velocity_x':2})
    m.call('shadowrun_snes_npc_control',0);s=m.snapshot()
    assert (s['npc_supported'],s['npc_arrived'],s['npc_velocity_x'],s['npc_velocity_y'])==(1,1,0,0)
