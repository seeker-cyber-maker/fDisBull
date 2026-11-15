"""Source target-close ownership preserves unknown, unselected identities."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_interaction import SOURCE

PREFIX = '''typedef unsigned char u8; typedef unsigned int u16;
u8 task_shared[65536],interaction_status=1,opening_window_status;
u16 interaction_fault,close_calls,closed_slot;
u16 scene_read(u16 at){return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 value){task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
void opening_window_close(u16 slot){close_calls+=1U;closed_slot=slot;opening_window_status=1U;}
'''


def close_machine(kind,actor):
    source=SOURCE.read_text()
    body=source[source.index('void interaction_target_close(void) {'):source.index('void interaction_targets(void) {')]
    m=GameMachine(author_program(PREFIX+body),{})
    data=bytearray(65536)
    for at,value in ((0x1f6,kind),(0x1fa,actor),(0x1f8,4)):
        data[at:at+2]=value.to_bytes(2,'little')
    m.set_state({'task_shared':list(data)})
    return m


def test_empty_target_close_preserves_unselected_identity_and_window_state():
    m=close_machine(0xffff,0x5555);before=m.snapshot()['task_shared']
    m.call('interaction_target_close');after=m.snapshot()
    assert after['task_shared']==before
    assert after['close_calls']==0 and after['interaction_status']==1


def test_selected_target_close_owns_one_window_and_clears_selection():
    m=close_machine(3,0x44);m.call('interaction_target_close');s=m.snapshot();data=s['task_shared']
    assert (s['close_calls'],s['closed_slot'],s['interaction_status'])==(1,4,1)
    assert data[0x1f6:0x1f8]==[255,255] and data[0x1fa:0x1fc]==[255,255]
