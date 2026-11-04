"""Bounded live camera integration and source velocity behavior."""
import hashlib
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_snes_camera import source_fragment
from test_shadowrun_snes_target import PRELUDE,put,word


def camera_machine():
    rom=bytearray(1<<20);at=0xc855e
    for i,value in enumerate((0,1000,0,1000,65535)):
        rom[at+i*2:at+i*2+2]=value.to_bytes(2,'little')
    source=PRELUDE+source_fragment()+'''\n u16 camera_test_delta,camera_test_result;
        void camera_test(u8 unused) {camera_test_result=camera_velocity(camera_test_delta);}'''
    return GameMachine(author_program(source,[{'id':0,'length':len(rom),
        'sha256':hashlib.sha256(rom).hexdigest()}]),{0:bytes(rom)})


def test_camera_velocity_negative_rounding_and_limit():
    m=camera_machine()
    for delta,expected in ((0,0),(8,0),(0xfff8,0xfffc),(0xff80,0xffe0),(0xf8,0x20)):
        m.set_state({'camera_test_delta':delta});m.call('camera_test',0)
        assert m.snapshot()['camera_test_result']==expected


def test_camera_updates_source_position_and_fails_on_unknown_bounds():
    m=camera_machine();s=[0]*65536
    for at,value in ((0xcde,0),(0xcf6,0x855d),(0xce0,0x3c0),(0xce2,0x200)):
        put(s,at,value)
    s[0xcf8]=0x99;m.set_state({'task_shared':s});m.call('shadowrun_snes_live_camera',0)
    r=m.snapshot();assert r['camera_status']==1
    assert [word(r['task_shared'],i) for i in (0xce0,0xce2,0xce4,0xce6)]==[0x3d0,0x220,0x10,0x20]
    s[0xcf8]=0x98;m.set_state({'task_shared':s});m.call('shadowrun_snes_live_camera',0)
    assert m.snapshot()['camera_status']==0
