"""Target-only inventory controller behavior, independent of private captures."""
import hashlib
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_play import SOURCE
from fdisbull.shadowrun_inventory import SOURCE as INVENTORY


def machine():
    rom=bytearray(0xd4596);rom[0xd4594]=12;rom=bytes(rom)
    prefix='''typedef unsigned char u8;typedef unsigned int u16;typedef unsigned long u32;
    u16 shadowrun_pad_held,shadowrun_play_shot_timer;u8 shadowrun_opening_status;u8 shadowrun_player_flags;
    u16 shadowrun_player_x,shadowrun_player_y,shadowrun_debug_x,shadowrun_debug_y;
    u8 shadowrun_debug_assisted,shadowrun_debug_recenter,shadowrun_debug_result;
    u8 shadowrun_play_refused,shadowrun_play_weapon_slot,shadowrun_play_weapon_item,shadowrun_play_ammo,shadowrun_play_weapon_aux;
    u8 shadowrun_play_shot_eligible,shadowrun_play_shot_pending,shadowrun_play_shot_armed,shadowrun_field_motion_state,shadowrun_linked_motion_state;
    u8 shadowrun_target_item,shadowrun_target_equipped_slot,shadowrun_target_supported;
    void shadowrun_target_refresh(void){} void shadowrun_target_cycle(void){}
    void shadowrun_play_shot_step(u8 a,u8 b){shadowrun_play_refused=1;}
    void shadowrun_debug_place(void){shadowrun_debug_result=2;}
    
    void shadowrun_opening_frame(u8 pad){shadowrun_opening_status=0;}
    '''
    inventory='\n'.join(x for x in INVENTORY.read_text().splitlines() if not x.startswith('typedef '))
    p=author_program(prefix+inventory+SOURCE.read_text(),[{'id':0,'length':len(rom),'sha256':hashlib.sha256(rom).hexdigest()}])
    m=GameMachine(p,{0:rom})
    m.set_state({'shadowrun_player_flags':1,'shadowrun_inventory_cell0':2,'shadowrun_inventory_cell1':44,
                 'shadowrun_inventory_cell2':14,'shadowrun_inventory_equipped_armor':1,
                 'shadowrun_play_weapon_slot':0,'shadowrun_play_weapon_item':2,'shadowrun_play_ammo':12})
    return m


def press(m, pad):
    m.call('shadowrun_play_frame',0);m.call('shadowrun_play_frame',pad)
    return m.snapshot()


def test_captured_equipment_roundtrips_and_unknown_item_refuses():
    m=machine();press(m,128)
    s=press(m,64);assert (s['shadowrun_play_weapon_slot'],s['shadowrun_play_ammo'])==(127,100)
    s=press(m,64);assert (s['shadowrun_play_weapon_slot'],s['shadowrun_play_ammo'])==(0,12)
    press(m,8);s=press(m,64);assert s['shadowrun_inventory_equipped_armor']==0
    s=press(m,64);assert s['shadowrun_inventory_equipped_armor']==1
    press(m,2);press(m,4);s=press(m,64)
    assert s['shadowrun_play_refused']==1 and s['shadowrun_inventory_equipped_armor']==1


def test_gate_and_invalid_weapon_state_fail_closed():
    m=machine();press(m,128)
    m.set_state({'shadowrun_play_action_gate':1})
    s=press(m,64);assert (s['shadowrun_play_refused'],s['shadowrun_play_ammo'])==(1,12)
    m.set_state({'shadowrun_play_action_gate':0,'shadowrun_play_weapon_slot':3})
    s=press(m,64);assert (s['shadowrun_play_refused'],s['shadowrun_play_weapon_slot'])==(1,3)


def test_other_controls_cancel_pending_shot_before_menu_or_movement():
    m=machine()
    m.set_state({'shadowrun_play_shot_pending':1,'shadowrun_play_shot_armed':1,'shadowrun_play_shot_eligible':1})
    m.call('shadowrun_play_frame',128)
    s=m.snapshot()
    assert (s['shadowrun_play_shot_pending'],s['shadowrun_play_shot_armed'],s['shadowrun_play_shot_eligible'],s['shadowrun_play_menu'])==(0,0,1,0)
    assert s['shadowrun_play_refused']==1
