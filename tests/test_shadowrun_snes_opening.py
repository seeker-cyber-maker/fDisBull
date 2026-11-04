"""Opening identity and scene-transition refusal boundaries."""
import hashlib

import pytest

from fdisbull import shadowrun_snes_opening as opening
from fdisbull.game_il import GameMachine, author_program


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def test_opening_rejects_wrong_rom_before_reading_components():
    with pytest.raises(ValueError, match='wrong SNES source'):
        opening.machine_from_title(bytes(1 << 20), bytes(131072), bytes(8192))


def test_opening_rejects_same_size_wrong_title_and_save(monkeypatch):
    rom, title, save = bytes(1 << 20), bytes(131072), bytes(8192)
    monkeypatch.setattr(opening, 'ROM_SHA256', digest(rom))
    monkeypatch.setattr(opening, 'TITLE_SHA256', digest(title))
    monkeypatch.setattr(opening, 'SAVE_SHA256', digest(save))
    changed_title = bytearray(title)
    changed_title[-1] = 1
    with pytest.raises(ValueError, match='wrong source title checkpoint'):
        opening.machine_from_title(rom, bytes(changed_title), save)
    changed_save = bytearray(save)
    changed_save[-1] = 1
    with pytest.raises(ValueError, match='wrong captured save RAM'):
        opening.machine_from_title(rom, title, bytes(changed_save))


PREFIX = '''typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 rom8(u8 region,u32 offset); u8 task_shared[65536]; u8 opening_failure,opening_scene_changed;
u16 requested_entry;
void opening_room_load(u16 entry) {requested_entry=entry;opening_scene_changed=1U;}
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
u16 scene_rom16(u32 at) {return (u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8);}
'''


def gate_machine(*,room=False):
    # One volume in group zero, no entries in group one. Bounds are inclusive.
    rom = bytearray(1 << 20)
    rom[0x100] = 1
    for i, value in enumerate((10, 10, 1, 20, 20, 4)):
        rom[0x101 + 2*i:0x103 + 2*i] = value.to_bytes(2, 'little')
    rom[0x10f] = 0
    if room:
        rom[0x100:0x110]=bytes(16)
        rom[0x101]=1
        for i,value in enumerate((10,10,1,20,20,4,31)):
            rom[0x102+2*i:0x104+2*i]=value.to_bytes(2,'little')
    data = bytes(rom)
    region = {'id': 0, 'length': len(data), 'sha256': digest(data)}
    source = opening.SOURCE.read_text()
    gate = source[source.index('void opening_scene_gate(void) {'):source.index('\n/* $DE5E:')]
    m = GameMachine(author_program(PREFIX + gate, [region]), {0: data})
    shared = bytearray(65536)
    def put(at, value):
        shared[at:at+2] = value.to_bytes(2, 'little')
    put(0x1d05, 0xffff)
    put(0x0cde, 0x42)
    put(0x009d, 0x8100)
    shared[0x009f] = 0x80
    put(0x0e44 + 0x42, 9 * 4)
    put(0x0e9c + 0x42, 15 * 4)
    put(0x0ef4 + 0x42, 4 * 4)
    m.set_state({'task_shared': list(shared)})
    return m


def test_scene_gate_refuses_pending_or_intersecting_room_transition():
    m = gate_machine()
    before = m.snapshot()['task_shared']
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 0
    assert m.snapshot()['task_shared'] == before
    changed = before[:]
    changed[0x0e44 + 0x42:0x0e46 + 0x42] = [40, 0]
    m.set_state({'task_shared': changed})
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 37
    assert m.snapshot()['task_shared'] == changed
    changed[0x1d05:0x1d07] = [0, 0]
    m.set_state({'task_shared': changed, 'opening_failure': 0})
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 37
    assert m.snapshot()['task_shared'] == changed


def test_scene_gate_handles_absent_actor_and_rejects_invalid_mapping():
    m = gate_machine()
    shared = m.snapshot()['task_shared']
    shared[0x0cde:0x0ce0] = [0xff, 0xff]
    shared[0x009d:0x009f] = [0, 0]
    m.set_state({'task_shared': shared})
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 0
    shared[0x0cde:0x0ce0] = [0x41, 0]
    m.set_state({'task_shared': shared, 'opening_failure': 0})
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 12
    shared[0x0cde:0x0ce0] = [0x42, 0]
    m.set_state({'task_shared': shared, 'opening_failure': 0})
    m.call('opening_scene_gate')
    assert m.snapshot()['opening_failure'] == 37


def test_direct_room_volume_dispatches_entry_with_source_coordinate_scaling():
    m=gate_machine(room=True);shared=m.snapshot()['task_shared']
    shared[0x0e44+0x42:0x0e46+0x42]=[40,0]
    m.set_state({'task_shared':shared})
    m.call('opening_scene_gate')
    state=m.snapshot()
    assert state['opening_scene_changed']==1 and state['requested_entry']==31
    assert state['opening_failure']==0 and state['task_shared']==shared
