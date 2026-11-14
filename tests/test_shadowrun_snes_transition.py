"""Scene transition uses persistent live state and yields source-owned work."""
import hashlib
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_snes_scene_init import SOURCE,COLLISION_SOURCE
from fdisbull.shadowrun_snes_transition import source_fragment


def gamma(value):return ''.join('0'+bit for bit in bin(value)[3:])+'1'


def machine():
    rom=bytearray(1<<20);desc=0x692af+0x1f*9;room=0xd207e
    rom[desc:desc+9]=(0xa07e).to_bytes(2,'little')+bytes([4])+(616).to_bytes(2,'little')+(442).to_bytes(2,'little')+(64).to_bytes(2,'little')
    rom[room:room+5]=bytes([87,7,0xda,0xa0,3]);rom[0xd20da:0xd20e4]=b'\x00\x00\xff\x7f\x00\x00\xff\x7f\xff\xff'
    rom[0x5fb58:0x5fb5b]=bytes([0xd7,0xf8,0x8b])
    zone=bytearray(86);zone[:11]=bytes([0,0,2,1,0x94,0xc6,0x0a,0,8,0,15])
    for i in range(15):zone[11+5*i:13+5*i]=bytes([0,0x60])
    stream=0x5f8d7;rom[stream:stream+4]=(86).to_bytes(2,'little')+(88).to_bytes(2,'little')
    rom[stream+4:stream+90]=zone;bits=gamma(86);bits+='0'*(-len(bits)%16)
    rom[stream+90:stream+90+len(bits)//8]=int(bits,2).to_bytes(len(bits)//8,'big')
    desc1=0x692af+9;room1=0xc812a
    rom[desc1:desc1+9]=(0x012a).to_bytes(2,'little')+bytes([6])+(650).to_bytes(2,'little')+(421).to_bytes(2,'little')+(87).to_bytes(2,'little')
    rom[room1:room1+5]=bytes([9,0,0x0a,0x83,13]);rom[0xc830a:0xc8314]=b'\x00\x00\xff\x7f\x00\x00\xff\x7f\xff\xff'
    rom[0x5fa6e:0x5fa71]=bytes([0x98,0xce,0x8a])
    street=bytearray(1084);street[2]=1;street[3]=9;p=4
    for i in range(9):
        if i<7:street[p+1]=0x80;p+=5
        else:p+=4
    for count in (114,93):
        street[p]=count;p+=1
        for _ in range(count):street[p+1]=0x60;p+=5
    assert p==1084
    stream1=0x54e98;rom[stream1:stream1+4]=(1084).to_bytes(2,'little')+(1086).to_bytes(2,'little')
    rom[stream1+4:stream1+1088]=street;bits=gamma(1084);bits+='0'*(-len(bits)%16)
    rom[stream1+1088:stream1+1088+len(bits)//8]=int(bits,2).to_bytes(len(bits)//8,'big')
    block=0x18000;rom[block:block+4]=(999).to_bytes(2,'little')+(142).to_bytes(2,'little')
    rom[block+4:block+144]=bytes(range(140));bits=gamma(140);bits+='0'*(-len(bits)%16)
    rom[block+144:block+144+len(bits)//8]=int(bits,2).to_bytes(len(bits)//8,'big')
    meta=0x6b031+0x8b2;rom[meta+3:meta+7]=(11).to_bytes(2,'little')+(0x123).to_bytes(2,'little')
    rom[0x1683:0x1685]=(0x8b2).to_bytes(2,'little')
    source=SOURCE.read_text()+'\n'+COLLISION_SOURCE.read_text()+'\n'+source_fragment()
    return GameMachine(author_program(source,[{'id':0,'length':len(rom),'sha256':hashlib.sha256(rom).hexdigest()}]),{0:bytes(rom)})


def put(b,at,value):b[at:at+2]=[value&255,value>>8]


def test_transition_stages_task_yield_without_resetting_persistent_items():
    m=machine();shared=[0]*65536;put(shared,0x2de6,0);put(shared,0x2de8,11)
    put(shared,0x2df0,0x8b2);shared[0x2ea2:0x2ea5]=[1,0xb2,8]
    m.set_state({'task_shared':shared,'transition_scene':0x1f})
    m.call('shadowrun_snes_transition_begin',0);s=m.snapshot()
    assert (s['transition_status'],s['transition_request'])==(2,1)
    for expected in (2,3):
        m.call('shadowrun_snes_transition_resume',0);s=m.snapshot()
        assert (s['transition_status'],s['transition_request'])==(2,expected)
    m.call('shadowrun_snes_transition_resume',0);m.call('shadowrun_snes_transition_next',0);s=m.snapshot()
    assert (s['transition_status'],s['transition_request'],s['scene_actor'],s['scene_task_id'])==(2,4,0x56,0x123)
    m.set_state({'transition_task':2});m.call('shadowrun_snes_transition_resume',0)
    for _ in range(8):
        m.call('shadowrun_snes_transition_next',0);s=m.snapshot()
        if s['transition_status']==2:break
        assert s['transition_status']==3
    assert (s['transition_status'],s['transition_request'])==(2,5)
    assert s['task_shared'][0x2ea2:0x2ea5]==[1,0xb2,8]
    assert s['task_shared'][0x0cde:0x0ce0]==[0x56,0]
    state=s['task_shared'];put(state,0x0ce4,4);put(state,0x0ce6,0xfffc)
    m.set_state({'task_shared':state});m.call('shadowrun_snes_transition_resume',0);s=m.snapshot()
    assert s['transition_status']==1 and s['task_shared'][0x0ce4:0x0ce8]==[0,0,0,0]


def test_transition_rejects_unqualified_scene_before_mutating_shared_state():
    m=machine();shared=[0]*65536;shared[0x2ea2]=7
    m.set_state({'task_shared':shared,'transition_scene':2})
    m.call('shadowrun_snes_transition_begin',0);s=m.snapshot()
    assert s['transition_status']==0 and s['task_shared']==shared


def test_street_zone_decodes_beyond_morgue_group_limit():
    m=machine();shared=[0]*65536;put(shared,0x2de6,0);put(shared,0x2de8,11);put(shared,0x2df0,0x8b2)
    m.set_state({'task_shared':shared,'transition_scene':1});m.call('shadowrun_snes_transition_begin',0)
    for _ in range(3):m.call('shadowrun_snes_transition_resume',0)
    m.call('shadowrun_snes_transition_next',0);m.set_state({'transition_task':2});m.call('shadowrun_snes_transition_resume',0)
    for _ in range(18):
        m.call('shadowrun_snes_transition_next',0);s=m.snapshot()
        if s['transition_status']==2:break
        assert s['transition_status']==3
    assert (s['transition_status'],s['transition_request'],s['scene_static_cursor'])==(2,5,0xde50)


def test_graphics_block_uses_threshold_and_completes_full_literal_run():
    m=machine();m.set_state({'transition_graphics_stream':0x18000,'transition_graphics_target':0x400})
    m.call('shadowrun_snes_transition_graphics_block',0);s=m.snapshot()
    assert (s['transition_graphics_status'],s['transition_graphics_length'])==(1,140)
    assert s['task_shared'][0x400:0x400+140]==list(range(140))


def test_party_direction_uses_live_low_mirror_and_sets_pending_frame():
    m=machine();shared=[0]*65536;slot=0x56
    for at,value in ((0,slot),(4,0x1a5),(6,0x57),(0x1104+slot,4),(0x120c+slot,0x3e)):
        put(shared,at,value)
    m.set_state({'task_shared':shared,'scene_actor':slot,'scene_initial_direction':6,
                 'transition_kind':11,'transition_entity':0x8b2,'transition_party_index':0,
                 'transition_party_pending':1})
    m.call('transition_finish_party');s=m.snapshot();b=s['task_shared']
    assert b[0x11b4+slot:0x11b6+slot]==[6,0]
    assert b[0x120c+slot:0x120e+slot]==[0x3f,0]
    assert b[0x115c+slot:0x115e+slot]==[255,255]
    assert b[0x400c+slot:0x400e+slot]==[128,0]
    assert b[8:12]==[0,0,0x8c,0]
