"""Source cursor arithmetic and fail-closed target staging."""
import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_target import source_fragment


PRELUDE = '''
typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 task_shared[65536];
u16 task_wait[48],task_link[48];
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 v) {task_shared[at]=(u8)v;task_shared[at+1U]=(u8)(v>>8);}
'''


def machine():
    rom=bytes(1 << 20)
    return GameMachine(author_program(PRELUDE+source_fragment(),
        [{'id':0,'length':len(rom),'sha256':hashlib.sha256(rom).hexdigest()}]),{0:rom})


def put(shared,at,value):shared[at:at+2]=[value&255,value>>8]
def word(shared,at):return shared[at]|shared[at+1]<<8


def test_source_cursor_begin_and_motion():
    m=machine();s=[0]*65536
    for at,value in ((0xcde,0x42),(0xe44+0x42,0x573),(0xe9c+0x42,0x7e7),
                     (0xef4+0x42,0x100),(0xf4c+0x42,0),(0xce0,0x520),(0xce2,0x24c)):
        put(s,at,value)
    m.set_state({'task_shared':s,'target_globals_known':1});m.call('shadowrun_snes_target_begin',0);r=m.snapshot()
    assert r['target_status']==1 and word(r['task_shared'],0x1f4)==0xffff
    put(r['task_shared'],0x1e6,0x200);put(r['task_shared'],0x1f6,0xffff)
    m.set_state({'task_shared':r['task_shared']})
    m.call('shadowrun_snes_target_cursor',0);r=m.snapshot()
    assert word(r['task_shared'],0x1ec)==0xffd0
    assert r['target_request']==0 and r['target_status']==1


def test_scan_refuses_unknown_geometry_before_hit_detection():
    m=machine();s=[0]*65536
    put(s,0x14cc,0);put(s,0x14ce,0);put(s,0x1f6,0xffff)
    m.set_state({'task_shared':s,'target_globals_known':1})
    m.call('shadowrun_snes_target_scan',0)
    assert m.snapshot()['target_status']==0


def test_cursor_end_requires_name_close_and_preserves_input_and_velocity():
    m=machine();s=[0]*65536
    for at,value in ((0x1f4,0xffff),(0x1f6,3),(0x1ec,0xffd0),(0x1ea,0x8000)):
        put(s,at,value)
    m.set_state({'task_shared':s});m.call('shadowrun_snes_target_end',0)
    assert m.snapshot()['target_status']==0
    put(s,0x1f6,0xffff);m.set_state({'task_shared':s});m.call('shadowrun_snes_target_end',0)
    r=m.snapshot();assert r['target_status']==1
    assert [word(r['task_shared'],i) for i in (0x1f4,0x1ec,0x1ea)]==[0,0xffd0,0x8000]


def test_cursor_facing_requires_known_geometry_and_uses_source_octants():
    m=machine();s=[0]*65536
    m.set_state({'task_shared':s,'target_globals_known':1})
    m.call('shadowrun_snes_target_facing',0);assert m.snapshot()['target_facing_status']==0
    m.set_state({'target_geometry_known':[1]*44});m.call('shadowrun_snes_target_facing',0)
    r=m.snapshot();assert (r['target_facing_status'],r['target_facing_direction'])==(1,4)


def test_target_dispatch_checks_range_and_uses_real_task_wait():
    m=machine();s=[0]*65536;wait=[0]*48
    for at,value in ((0x1f6,3),(0x1fa,0x44),(0x1ea,0x8000),(0xcde,0x42),
                     (0x136c+0x44,0x12),(0xe44+0x44,0xa1)):
        put(s,at,value)
    wait[0x12//2]=0x80
    m.set_state({'task_shared':s,'target_globals_known':1,'target_geometry_known':[1]*44,'task_wait':wait})
    m.call('shadowrun_snes_target_dispatch',0);r=m.snapshot()
    assert (r['target_dispatch_status'],r['target_dispatch_request'])==(2,2)
    put(r['task_shared'],0xe44+0x44,0xa0);m.set_state({'task_shared':r['task_shared']})
    m.call('shadowrun_snes_target_dispatch',0);r=m.snapshot()
    assert (r['target_dispatch_status'],r['target_dispatch_request'])==(2,1)
    assert (r['target_dispatch_actor'],r['target_dispatch_task'],r['target_dispatch_wait'])==(0x44,0x12,0x80)
