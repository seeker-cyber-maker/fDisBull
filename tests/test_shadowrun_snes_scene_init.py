"""New-game scene construction guards and source-derived transitions."""
import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_scene_init import SOURCE


def _machine(rom):
    program=author_program(SOURCE.read_text(), [{'id':0,'length':len(rom),
        'sha256':hashlib.sha256(rom).hexdigest()}])
    return GameMachine(program,{0:bytes(rom)})


def _gamma(value):
    bits=bin(value)[3:]
    return ''.join('0'+bit for bit in bits)+'1'


def test_scene_reset_initializes_source_camera_motion():
    machine=_machine(bytearray(1<<20));shared=[0]*65536
    shared[0x0ce4:0x0ce8]=[0x55]*4
    machine.set_state({'task_shared':shared});machine.call('shadowrun_snes_scene_reset_camera_motion',0)
    assert machine.snapshot()['task_shared'][0x0ce4:0x0ce8]==[0,0,0,0]


def test_world_decoder_handles_source_style_overlapping_backreferences():
    rom=bytearray(1<<20);base=0x5fc42
    rom[base:base+2]=(3515).to_bytes(2,'little')
    rom[base+2:base+4]=(4).to_bytes(2,'little')  # bitstream begins at +6
    rom[base+4]=0xa5;rom[0x1fb7]=1
    bits=_gamma(1)+'0'+_gamma(3513-1)
    bits += '0'*(-len(bits)%16)
    rom[base+6:base+6+len(bits)//8]=int(bits,2).to_bytes(len(bits)//8,'big')
    machine=_machine(rom);machine.call('shadowrun_snes_scene_world',0);state=machine.snapshot()
    assert state['scene_status']==1
    assert state['task_shared'][0x2e00:0x2e00+3515]==[0xa5]*3515


def test_actor_creation_yields_real_task_and_defers_entity_metadata():
    rom=bytearray(1<<20);room=0x1000;entity=0x10;meta=0x6b031+entity
    rom[room+5:room+11]=(100).to_bytes(2,'little')+(200).to_bytes(2,'little')+entity.to_bytes(2,'little')
    rom[meta:meta+7]=bytes((0xc0,0,0,3,0,0x23,1))
    rom[0x66fb4+18:0x66fb6+18]=(0x304).to_bytes(2,'little')
    machine=_machine(rom);shared=[0]*65536
    shared[0x14cc:0x14ce]=[254,255]
    for slot in range(0,88,2):shared[0x3f04+slot:0x3f06+slot]=[255,255]
    machine.set_state({'task_shared':shared,'scene_room_id':3,'scene_room_rom':room,
                       'scene_count':1,'scene_entry':0})
    machine.call('shadowrun_snes_scene_next',0);s=machine.snapshot()
    assert (s['scene_status'],s['scene_pending'],s['scene_actor'],s['scene_task_id'])==(3,1,0x56,0x123)
    assert s['task_shared'][0x1526+0x56:0x1528+0x56]==[255,255]
    assert s['task_shared'][0x0e44+0x56:0x0e46+0x56]==[144,1]
    machine.set_state({'scene_task_result':4});machine.call('shadowrun_snes_scene_task_complete',0);s=machine.snapshot()
    assert (s['scene_status'],s['scene_pending'])==(1,0)
    assert s['task_shared'][0x136c+0x56:0x136e+0x56]==[4,0]
    assert s['task_shared'][0x1526+0x56:0x1528+0x56]==[16,0]
    assert s['task_shared'][0x141c+0x56:0x141e+0x56]==[1,128]
    machine.call('shadowrun_snes_scene_next',0)
    assert machine.snapshot()['scene_status']==2


def test_initial_camera_clamps_source_coordinates_to_room_bounds():
    rom=bytearray(1<<20)
    for i,value in enumerate((409,582,482,481,65535)):
        rom[0xc855e+2*i:0xc8560+2*i]=value.to_bytes(2,'little')
    machine=_machine(rom);shared=[0]*65536
    shared[0x0cf6:0x0cf8]=[0x5d,0x85]
    machine.set_state({'task_shared':shared,'scene_room_id':3,'scene_room_bank':0x99,
                       'scene_initial_x':396,'scene_initial_y':476,'scene_initial_z':64})
    machine.call('shadowrun_snes_scene_camera',0);s=machine.snapshot()
    assert s['scene_status']==1
    assert s['task_shared'][0xce0:0xce4]==[0x20,0x05,0x4c,0x02]


def test_actor_allocation_refuses_when_no_free_slot_exists():
    machine=_machine(bytearray(1<<20))
    machine.set_state({'scene_spawn_kind':3,'scene_task_id':65535})
    before=machine.snapshot()['task_shared']
    machine.call('shadowrun_snes_actor_allocate',0);s=machine.snapshot()
    assert s['scene_status']==0
    assert s['task_shared']==before


def test_party_insertion_rejects_unqualified_kind_without_mutation():
    machine=_machine(bytearray(1<<20));shared=[0]*65536
    shared[0x2de6:0x2de8]=[254,255]
    machine.set_state({'task_shared':shared,'scene_party_kind':10,'scene_party_entity':0x8b2})
    machine.call('shadowrun_snes_party_begin',0);s=machine.snapshot()
    assert (s['scene_status'],s['scene_party_pending'])==(0,0)
    assert s['task_shared']==shared
