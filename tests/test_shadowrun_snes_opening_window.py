"""Window state preserves source ownership and exposes omitted producers."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_opening_window import source_fragment

PREFIX = '''typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 task_shared[65536];
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 value) {task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
'''


def new_machine():
    return GameMachine(author_program(PREFIX + source_fragment()), {})


def word(buf, at):
    return buf[at] | (buf[at + 1] << 8)


def test_window_allocation_and_guarded_finish():
    data = bytearray(65536)
    data[0x220:0x222] = b'\xfe\xff'
    data[0x22e:0x230] = b'\x27\x20'
    data[0x232:0x23a] = b'\xff' * 8
    machine = new_machine()
    state = {'task_shared': list(data)}
    state.update({f'opening_window_arg{i}': value for i, value in
                  enumerate((2, 2, 21, 4, 0x400, 0x3b, 240))})
    machine.set_state(state)
    machine.call('opening_window_begin')
    result = machine.snapshot()
    assert (result['opening_window_status'], result['opening_window_phase']) == (1, 1)
    mem = result['task_shared']
    assert [word(mem, p) for p in (0x21e, 0x220, 0x22e, 0x2000, 0x20a0)] == [30, 0, 0x204d, 0x84, 38]
    machine.call('opening_window_finish')
    assert machine.snapshot()['opening_window_status'] == 0
    assert word(machine.snapshot()['task_shared'], 0x238) == 0xffff
    machine.set_state({'opening_window_text_complete': 1, 'opening_window_present_complete': 1,
                       'opening_window_layout_cursor': 0x2045,
                       'opening_window_layout_subpixel': 0})
    machine.call('opening_window_finish')
    result = machine.snapshot()
    assert result['opening_window_status'] == 1
    assert (word(result['task_shared'], 0x238), word(result['task_shared'], 0x240)) == (0, 240)
    assert word(result['task_shared'], 0x20c0) == 0x2045


def test_window_reset_initializes_empty_source_ownership():
    machine = new_machine()
    machine.set_state({'task_shared': [0x55] * 65536})
    machine.call('opening_window_reset')
    result = machine.snapshot()
    assert result['opening_window_status'] == 1
    mem = result['task_shared']
    assert [word(mem, p) for p in (0x210, 0x21e, 0x220, 0x22e, 0x230)] == [0x84, 0, 0xfffe, 0x2027, 0]
    assert all(word(mem, 0x232 + i) == 0xffff for i in range(0, 8, 2))
    assert all(word(mem, 0x242 + i) == 0 for i in range(0, 32, 2))


def test_lifecycle_reports_unknown_rng_and_releases_top_slot():
    data = bytearray(65536)
    data[0x232:0x23a] = b'\xff' * 8
    data[0x238:0x23a] = b'\x00\x00'
    data[0x240:0x242] = b'\x01\x00'
    data[0x242:0x244] = b'\xff\xff'
    data[0x2060:0x2062] = b'\x27\x20'
    data[0x21e:0x220] = b'\x02\x00'
    data[0x1d04] = 0x5a
    machine = new_machine()
    machine.set_state({'task_shared': list(data)})
    machine.call('opening_window_tick')
    state = machine.snapshot()
    assert state['opening_window_status'] == 1
    assert (word(state['task_shared'], 0x220), word(state['task_shared'], 0x22e)) == (0xfffe, 0x2027)
    assert word(state['task_shared'], 0x238) == 0xffff
    assert (word(state['task_shared'], 0x21e), state['task_shared'][0x1d04]) == (1, 0x5a)
    assert state['opening_window_rng_tainted'] == state['opening_window_audio_tainted'] == 1
    assert state['opening_window_display_tainted'] == 1


def test_direct_window_close_preserves_lower_ownership_and_expiry_queue():
    m=new_machine();m.call('opening_window_reset')
    for values in ((2,2,10,3,0),(3,3,11,4,0)):
        m.set_state({f'opening_window_arg{i}':v for i,v in enumerate(values)})
        m.call('opening_window_begin')
        # A direct-window owner completes its own text/presentation producer.
        m.set_state({'opening_window_phase':2})
    before=m.snapshot()['task_shared']
    assert word(before,0x220)==2
    m.call('opening_window_close',2)
    s=m.snapshot();data=s['task_shared']
    assert s['opening_window_status']==1
    assert word(data,0x220)==0 and word(data,0x242)==0xffff and word(data,0x244)==0
    assert data[0x232:0x242]==before[0x232:0x242]
    m.call('opening_window_close',0)
    assert word(m.snapshot()['task_shared'],0x220)==0xfffe
