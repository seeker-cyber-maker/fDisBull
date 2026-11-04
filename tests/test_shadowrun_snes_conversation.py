import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_conversation import SOURCE as CONVERSATION
from fdisbull.shadowrun_snes_dialogue import SOURCE as DIALOGUE


PRELUDE = '''
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 task_shared[65536],task_audio_tainted;
u8 rom8(u8 region,u32 offset);
u16 scene_read(u16 a) {return (u16)task_shared[a]|((u16)task_shared[a+1U]<<8);}
void scene_write(u16 a,u16 v) {task_shared[a]=(u8)v;task_shared[a+1U]=(u8)(v>>8);}
'''


def machine():
    rom = bytearray(1048576)
    rom[0x147c:0x147e] = bytes([0, 0x81])
    rom[0x147a + 0x4b * 2:0x147c + 0x4b * 2] = bytes([0, 0x82])
    rom[0x68000 + 10:0x68000 + 12] = bytes([1, 0x70])
    record = [0, 0, 0, 0, 0xff, 6, 0x80, 0x34, 0x12, 0x65, 7,
              0xfe, 5, 1, 5, 0x82, 7, 5, 4, 0, 0x34, 0x12,
              0xfd, 4, 0, 0x88, 9, 0xf8]
    rom[0x68100:0x68100 + len(record)] = bytes(record)
    rom = bytes(rom)
    program = author_program(PRELUDE + DIALOGUE.read_text() + CONVERSATION.read_text(),
                             [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    shared = [0] * 65536
    shared[0x3ca3] = 255
    m.set_state({'task_shared': shared, 'conversation_actor': 0x44, 'conversation_tag': 1})
    m.call('shadowrun_snes_conversation_begin', 0)
    return m


def reply(m, request, value=0):
    assert m.snapshot()['conversation_request'] == request
    m.set_state({'conversation_reply_request': request, 'conversation_reply_success': 1,
                 'conversation_value': value})
    m.call('shadowrun_snes_conversation_reply', 0)
    s = m.snapshot()
    assert s['conversation_status'] != 0
    return s


def open_conversation(m):
    for request, value in [(1, 0), (2, 0), (3, 0), (5, 0), (6, 0), (5, 2),
                           (7, 0), (8, 0), (9, 0)]:
        s = reply(m, request, value)
    assert s['conversation_request'] == 16
    s = reply(m, 16)
    assert (s['conversation_request'], s['conversation_text'], s['conversation_script']) == (10, 0x765, 0x1234)
    s = reply(m, 10)
    assert (s['conversation_request'], s['conversation_arg0'], s['conversation_arg1']) == (11, 0x44, 0x1234)
    s = reply(m, 11)
    assert (s['conversation_request'], s['conversation_arg0']) == (12, 61)
    return reply(m, 12)


def test_source_keyword_path_and_cancel_close_order():
    m = machine()
    assert open_conversation(m)['conversation_request'] == 13
    s = reply(m, 13, 1)
    assert s['conversation_request'] == 16
    s = reply(m, 16)
    assert s['conversation_request'] == 10 and s['conversation_text'] == 0x782
    assert s['task_shared'][0x3ca3:0x3ca5] == [5, 255]
    assert reply(m, 10)['conversation_request'] == 13
    s = reply(m, 13, 2)
    assert s['conversation_request'] == 5 and s['conversation_keyword_count'] == 1
    assert s['task_shared'][0x154:0x158] == [1, 0x70, 0, 0]
    s = reply(m, 5, 4)
    assert (s['conversation_request'], s['conversation_arg1'], s['conversation_arg4']) == (13, 1, 1)
    assert reply(m, 13, 0)['conversation_request'] == 14
    assert reply(m, 14)['conversation_request'] == 16
    s = reply(m, 16)
    assert s['conversation_request'] == 10 and s['conversation_text'] == 0x1234
    assert reply(m, 10)['conversation_request'] == 13
    assert reply(m, 13, 0xffff)['conversation_request'] == 15
    assert reply(m, 15, 0)['conversation_request'] == 17
    assert reply(m, 17)['conversation_arg0'] == 2
    assert reply(m, 14)['conversation_arg0'] == 0
    assert reply(m, 14)['conversation_status'] == 2


def test_service_mismatch_refuses_without_advancing():
    m = machine()
    m.set_state({'conversation_reply_request': 2, 'conversation_reply_success': 1})
    m.call('shadowrun_snes_conversation_reply', 0)
    assert m.snapshot()['conversation_status'] == 0


def test_missing_response_repeats_source_clear_before_fallback():
    m = machine()
    open_conversation(m)
    m.set_state({'conversation_selector': 0x33, 'conversation_after_text': 1})
    m.call('conversation_text_request')
    assert m.snapshot()['conversation_request'] == 16
    s = reply(m, 16)
    assert (s['conversation_request'], s['conversation_selector']) == (16, 0xfffd)
    s = reply(m, 16)
    assert (s['conversation_request'], s['conversation_text']) == (10, 0x988)
