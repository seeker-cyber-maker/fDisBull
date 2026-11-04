"""Bounded source task notification and wakeup, including failure edges."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_script import SOURCE


def machine():
    return GameMachine(author_program(SOURCE.read_text()), {})


def test_signal_follows_negative_wait_links_and_preserves_other_flags():
    m = machine()
    waits = [0] * 48
    links = [0] * 48
    flags = [0] * 48
    waits[9] = 0xffff
    links[9] = 0x14
    flags[10] = 0x10
    m.set_state({'task_index': 0x12, 'task_wait': waits, 'task_link': links,
                 'task_flags': flags})
    m.call('shadowrun_snes_task_signal', 0)
    s = m.snapshot()
    assert s['task_supported'] == 1
    assert s['task_flags'][10] == 0x14
    assert s['task_flags'][9] == 0
    m.set_state({'task_index': 0x14})
    m.call('shadowrun_snes_task_check', 0)
    assert m.snapshot()['task_ready'] == 1


def test_signal_refuses_invalid_and_cyclic_links_without_mutation():
    for link in (3, 96, 0):
        m = machine()
        waits = [0] * 48
        links = [0] * 48
        waits[0] = 0xffff
        links[0] = link
        m.set_state({'task_index': 0, 'task_wait': waits, 'task_link': links})
        before = m.snapshot()['task_flags']
        m.call('shadowrun_snes_task_signal', 0)
        assert m.snapshot()['task_supported'] == 0
        assert m.snapshot()['task_flags'] == before


def test_timer_and_flag_waits_follow_source_and_only_mark_ready():
    m = machine()
    waits = [0] * 48
    delay = [0] * 48
    flags = [0] * 48
    waits[8], delay[8] = 1, 2
    waits[9], flags[9] = 4, 4
    m.set_state({'task_index': 16, 'task_wait': waits, 'task_delay': delay,
                 'task_flags': flags})
    m.call('shadowrun_snes_task_check', 0)
    assert (m.snapshot()['task_ready'], m.snapshot()['task_delay'][8]) == (0, 1)
    m.call('shadowrun_snes_task_check', 0)
    assert (m.snapshot()['task_ready'], m.snapshot()['task_wait'][8]) == (1, 0)
    m.set_state({'task_index': 18})
    m.call('shadowrun_snes_task_check', 0)
    assert (m.snapshot()['task_ready'], m.snapshot()['task_wait'][9]) == (1, 0)


def test_coordinate_setter_applies_source_scale_and_control_kind():
    m = machine()
    m.set_state({'task_command_kind': 1, 'task_command_arg_x': 500,
                 'task_command_arg_y': 480})
    m.call('shadowrun_snes_task_set_coordinate', 0)
    s = m.snapshot()
    assert (s['task_command_supported'], s['task_command_control'],
            s['task_command_x'], s['task_command_y'], s['task_command_timer']) == (1, 1, 2000, 1920, 1)
    m.set_state({'task_command_kind': 2})
    m.call('shadowrun_snes_task_set_coordinate', 0)
    assert m.snapshot()['task_command_supported'] == 0
    assert m.snapshot()['task_command_x'] == 2000


def test_vm_runs_real_stack_local_callback_and_wait_until_source_yield():
    import hashlib
    rom = bytearray(0x16000)
    rom[:11] = bytes([0xc2, 0x58, 0x3b, 0x14, 0x90, 0x01, 0x00, 0x01,
                      0x58, 0x9e, 0xff])
    rom[0x15895 + 0x3b], rom[0x15895 + 0x9e] = 1, 2
    rom[0x157ba + 0x9e] = 2
    rom = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                   'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    heap = [0] * 1996
    frame, sp = 0x400, 0x500
    def word(address, value):
        heap[address - 0x3f2] = value & 255
        heap[address - 0x3f2 + 1] = value >> 8
    word(frame, 0x8000)
    heap[frame - 0x3f2 + 2] = 0x80
    word(frame + 7, sp)
    heap[frame - 0x3f2 + 19] = 0x44
    frames = [0] * 48
    frames[8] = frame
    shared = [0] * 65536
    shared[0x40bc + 0x44] = 7
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_shared': shared,
                 'task_index': 0x10})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_vm_callback'], s['task_vm_arg0']) == (2, 0x3b, 0x44)
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_shared'][0x40bc + 0x44] == 0
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_vm_pc'], s['task_wait'][8], s['task_delay'][8],
            s['task_callback'][8], s['task_vm_resume'][8]) == (1, 10, 1, 400, 0xf4d2, 1)
    m.set_state({'task_vm_resume_value': 1})
    m.call('shadowrun_snes_task_vm', 0)
    assert m.snapshot()['task_vm_status'] == 0


def test_generic_task_signal_supports_animation_bit_eight():
    m = machine()
    m.set_state({'task_index': 2, 'task_signal_mask': 8})
    m.call('shadowrun_snes_task_signal_mask', 0)
    assert (m.snapshot()['task_supported'], m.snapshot()['task_flags'][1]) == (1, 8)


def test_unknown_callback_resume_value_refuses_unless_discarded():
    import hashlib
    rom = bytes([0x00, 0x2a, 0xff]) + bytes(32765)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                   'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    heap = [0] * 1996
    frame = 0x400
    def word(address, value):
        heap[address - 0x3f2] = value & 255
        heap[address - 0x3f2 + 1] = value >> 8
    word(frame, 0x8000)
    heap[frame - 0x3f2 + 2] = 0x80
    word(frame + 7, 0x500)
    frames, resumes = [0] * 48, [0] * 48
    frames[8], resumes[8] = frame, 1
    m.set_state({'task_heap': heap, 'task_frame': frames,
                 'task_vm_resume': resumes, 'task_index': 0x10})
    m.call('shadowrun_snes_task_vm', 0)
    assert m.snapshot()['task_vm_status'] == 0
    assert m.snapshot()['task_vm_resume'][8] == 1


def test_audio_request_preserves_latches_and_exposes_event():
    import hashlib
    rom = bytearray(32768)
    rom[0x4483 + 0x2e:0x4485 + 0x2e] = (0x18).to_bytes(2, 'little')
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    m.set_state({'task_index': 8, 'task_vm_pending_task': 8, 'task_vm_pending': 1,
                 'task_vm_callback': 0x4c, 'task_vm_arg0': 0x4e,
                 'task_vm_arg1': 0x2e, 'task_vm_arg2': 0xff, 'task_vm_arg3': 3})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert (s['task_native_supported'], s['task_vm_pending'], s['task_audio_count']) == (1, 0, 1)
    assert (s['task_audio_actor'][0], s['task_audio_id'][0], s['task_audio_volume'][0],
            s['task_audio_mode'][0]) == (0x4e, 0x2e, 0xff, 3)
    assert (s['task_shared'][0x1cfe], s['task_shared'][0x1d00]) == (3, 3)


def test_distance_callback_uses_live_actor_positions_and_returns_on_stack():
    m = machine()
    heap, shared, frames = [0] * 1996, [0] * 65536, [0] * 48
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 7] = 0
    heap[0x400 - 0x3f2 + 8] = 5
    def word(address, value):
        shared[address], shared[address + 1] = value & 255, value >> 8
    word(0x0cde, 2)
    word(0x0e44 + 4, 100)
    word(0x0e9c + 4, 300)
    word(0x0e44 + 2, 120)
    word(0x0e9c + 2, 240)
    m.set_state({'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 10, 'task_vm_return': 1, 'task_vm_arg0': 4,
                 'task_heap': heap, 'task_frame': frames, 'task_shared': shared})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    at = 0x4ff - 0x3f2
    assert s['task_native_supported'] == 1
    assert s['task_heap'][at] | s['task_heap'][at + 1] << 8 == 15


def test_task_termination_unlinks_and_releases_validated_heap_block():
    m = machine()
    heap, frames = [0] * 1996, [0] * 48
    links, nexts = [0] * 48, [0] * 48
    frames[8] = 0x410
    heap[0x410 - 0x3f2 - 3] = 0x80
    links[8], nexts[8] = 0xffff, 0x12
    links[9] = 0x10
    m.set_state({'task_index': 0x10, 'task_vm_status': 4, 'task_heap': heap,
                 'task_frame': frames, 'task_link': links, 'task_next': nexts,
                 'task_list_head': 0x10, 'task_list_current': 0x10,
                 'task_list_free': 0xffff, 'task_return_value': 0x1234})
    m.call('shadowrun_snes_task_terminate', 0)
    s = m.snapshot()
    assert (s['task_supported'], s['task_list_head'], s['task_list_current'],
            s['task_list_free']) == (1, 0x12, 0x12, 0x10)
    assert s['task_link'][9] == 0xffff
    assert s['task_heap'][0x410 - 0x3f2 - 3] == 0
    assert s['task_shared'][:2] == [0x34, 0x12]


def test_conversation_tag_callback_updates_only_selected_actor():
    m = machine();shared = [0] * 65536
    m.set_state({'task_shared': shared, 'task_index': 0, 'task_vm_pending_task': 0,
                 'task_vm_pending': 1, 'task_vm_callback': 0xb4, 'task_vm_argc': 2,
                 'task_vm_arg0': 0x42, 'task_vm_arg1': 0x51})
    m.call('shadowrun_snes_task_native', 0);s=m.snapshot()
    assert s['task_native_supported'] == 1
    assert s['task_shared'][0x446e:0x4470] == [0x51, 0]
    assert s['task_shared'][0x446c:0x446e] == [0, 0]
    m.set_state({'task_vm_pending': 1, 'task_vm_arg0': 0x43})
    before=m.snapshot()['task_shared'];m.call('shadowrun_snes_task_native',0);s=m.snapshot()
    assert s['task_native_supported'] == 0 and s['task_shared'] == before


def test_actor_position_callback_stores_raw_coordinates_without_depth_update():
    m = machine()
    shared = [0] * 65536
    shared[0x0f4c + 0x42:0x0f4e + 0x42] = [0x34, 0x12]
    m.set_state({'task_shared': shared, 'task_index': 0, 'task_vm_pending_task': 0,
                 'task_vm_pending': 1, 'task_vm_callback': 0x82, 'task_vm_argc': 4,
                 'task_vm_arg0': 0x42, 'task_vm_arg1': 0x658,
                 'task_vm_arg2': 0x454, 'task_vm_arg3': 0x108})
    m.call('shadowrun_snes_task_native', 0);s=m.snapshot()
    assert s['task_native_supported'] == 1
    assert s['task_shared'][0x0e86:0x0e88] == [0x58, 6]
    assert s['task_shared'][0x0ede:0x0ee0] == [0x54, 4]
    assert s['task_shared'][0x0f36:0x0f38] == [8, 1]
    assert s['task_shared'][0x0f8e:0x0f90] == [0x34, 0x12]
    m.set_state({'task_vm_pending': 1, 'task_vm_arg0': 0x43})
    before=m.snapshot()['task_shared'];m.call('shadowrun_snes_task_native',0);s=m.snapshot()
    assert s['task_native_supported'] == 0 and s['task_shared'] == before


def test_source_addition_wraps_16_bit_stack_words():
    import hashlib
    for left, right, expected in ((5, 3, 8), (0xffff, 1, 0), (0x8000, 0x8000, 0)):
        rom = bytes([0x14, left & 255, left >> 8, 0x14, right & 255, right >> 8, 0x5c, 0x56])
        program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                       'sha256': hashlib.sha256(rom).hexdigest()}])
        m = GameMachine(program, {0: rom})
        heap, frames = [0] * 1996, [0] * 48
        frame, sp = 0x400, 0x500
        heap[frame - 0x3f2:frame - 0x3f2 + 3] = [0, 0x80, 0x80]
        heap[frame - 0x3f2 + 7:frame - 0x3f2 + 9] = [sp & 255, sp >> 8]
        frames[0] = frame
        m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 0})
        m.call('shadowrun_snes_task_vm', 0);s=m.snapshot()
        assert (s['task_vm_status'], s['task_return_value']) == (4, expected)


def test_source_subtract_uses_next_minus_top_with_word_wrap():
    import hashlib
    for left, right, expected in ((5, 3, 2), (3, 5, 0xfffe), (0, 1, 0xffff)):
        rom = bytes([0x14, left, 0, 0x14, right, 0, 0x5e, 0x56])
        program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                       'sha256': hashlib.sha256(rom).hexdigest()}])
        m = GameMachine(program, {0: rom})
        heap, frames = [0] * 1996, [0] * 48
        frame, sp = 0x400, 0x500
        heap[frame - 0x3f2:frame - 0x3f2 + 3] = [0, 0x80, 0x80]
        heap[frame - 0x3f2 + 7:frame - 0x3f2 + 9] = [sp & 255, sp >> 8]
        frames[0] = frame
        m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 0})
        m.call('shadowrun_snes_task_vm', 0);s=m.snapshot()
        assert (s['task_vm_status'], s['task_return_value']) == (4, expected)


def test_source_left_shift_pops_count_and_wraps_the_word():
    import hashlib
    for count, expected in ((0, 0x8001), (1, 2), (15, 0x8000), (16, 0), (0xffff, 0)):
        rom = bytes([0x14, 1, 0x80, 0x14, count & 255, count >> 8, 0x7a, 0x56])
        program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                       'sha256': hashlib.sha256(rom).hexdigest()}])
        m = GameMachine(program, {0: rom})
        heap, frames = [0] * 1996, [0] * 48
        frame, sp = 0x400, 0x500
        heap[frame - 0x3f2:frame - 0x3f2 + 3] = [0, 0x80, 0x80]
        heap[frame - 0x3f2 + 7:frame - 0x3f2 + 9] = [sp & 255, sp >> 8]
        frames[0] = frame
        m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 0})
        m.call('shadowrun_snes_task_vm', 0);s=m.snapshot()
        assert (s['task_vm_status'], s['task_return_value']) == (4, expected)


def test_source_left_shift_refuses_missing_value_without_heap_write():
    import hashlib
    rom = bytes([0x7a])
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                   'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    heap, frames = [0] * 1996, [0] * 48
    frame, sp = 0x400, 3003
    heap[frame - 0x3f2:frame - 0x3f2 + 3] = [0, 0x80, 0x80]
    heap[frame - 0x3f2 + 7:frame - 0x3f2 + 9] = [sp & 255, sp >> 8]
    heap[3004 - 0x3f2] = 1
    frames[0] = frame
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 0})
    m.call('shadowrun_snes_task_vm', 0);s=m.snapshot()
    assert s['task_vm_status'] == 0 and s['task_heap'] == heap


def test_unsigned_less_than_compares_top_against_next_stack_word():
    import hashlib
    for lower, upper, expected in [(20, 10, 0xffff), (10, 20, 0), (10, 10, 0)]:
        rom = bytes([0x14, lower, 0, 0x14, upper, 0, 0x9a, 0x56])
        program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                       'sha256': hashlib.sha256(rom).hexdigest()}])
        m = GameMachine(program, {0: rom})
        heap, frames = [0] * 1996, [0] * 48
        frame, sp = 0x400, 0x500
        heap[frame - 0x3f2:frame - 0x3f2 + 3] = [0, 0x80, 0x80]
        heap[frame - 0x3f2 + 7:frame - 0x3f2 + 9] = [sp & 255, sp >> 8]
        frames[0] = frame
        m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 0})
        m.call('shadowrun_snes_task_vm', 0)
        s = m.snapshot()
        assert (s['task_vm_status'], s['task_return_value']) == (4, expected)


def test_item_record_count_and_reference_callbacks():
    import hashlib
    rom = bytearray(1048576)
    pointer_at = 438322 + 0x395
    rom[pointer_at:pointer_at + 2] = bytes([0xa0, 0x2e])
    rom = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(rom),
                                                   'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    shared = [0] * 65536
    shared[0x2ea2] = 5
    m.set_state({'task_shared': shared, 'task_index': 0, 'task_vm_pending_task': 0,
                 'task_vm_pending': 1, 'task_vm_callback': 0x26, 'task_vm_argc': 2,
                 'task_vm_arg0': 0x395, 'task_vm_arg1': 3})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_shared'][0x2ea2] == 6
    m.set_state({'task_vm_pending': 1, 'task_vm_callback': 0x74, 'task_vm_arg1': 0x8b2})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_shared'][0x2ea3:0x2ea5] == [0xb2, 8]


def test_pickup_owner_uses_live_party_entity_without_changing_count():
    m = machine()
    shared = [0] * 65536
    shared[0x13c4 + 0x3e:0x13c6 + 0x3e] = [0x7d, 0x2e]
    shared[0x2e7f:0x2e82] = [0, 255, 255]
    shared[0x2df0:0x2df2] = [0xb2, 8]
    m.set_state({'task_shared': shared, 'task_index': 0, 'task_vm_pending_task': 0,
                 'task_vm_pending': 1, 'task_vm_callback': 0x6f,
                 'task_vm_argc': 1, 'task_vm_arg0': 0x3e})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1
    assert s['task_shared'][0x2e7f:0x2e82] == [0, 0xb2, 8]
    # Source loads the entire owner word before storing, including alias cases.
    shared = s['task_shared']
    shared[0x13c4 + 0x3e:0x13c6 + 0x3e] = [0xee, 0x2d]
    m.set_state({'task_shared': shared, 'task_vm_pending': 1})
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_shared'][0x2df0:0x2df3] == [0xb2, 0xb2, 8]
    shared = m.snapshot()['task_shared']
    shared[0x13c4 + 0x3e:0x13c6 + 0x3e] = [0xfc, 0xff]
    m.set_state({'task_shared': shared, 'task_vm_pending': 1})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 0 and s['task_vm_pending'] == 1
    assert s['task_shared'] == shared


def test_player_and_actor_x_callbacks_use_live_shared_state():
    m = machine()
    heap, frames, shared = [0] * 1996, [0] * 48, [0] * 65536
    frames[0] = 0x400
    heap[0x400 - 0x3f2 + 7:0x400 - 0x3f2 + 9] = [0, 5]
    shared[0x0cde:0x0ce0] = [0x42, 0]
    shared[0x0e86:0x0e88] = [0x73, 5]
    shared[0x0ede:0x0ee0] = [0x37, 6]
    shared[0x0f36:0x0f38] = [0x5b, 1]
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_shared': shared,
                 'task_index': 0, 'task_vm_pending_task': 0, 'task_vm_pending': 1,
                 'task_vm_return': 1, 'task_vm_callback': 0x28, 'task_vm_argc': 0})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_callback_result'] == 0x42
    m.set_state({'task_vm_pending': 1, 'task_vm_return': 1, 'task_vm_callback': 0x4f,
                 'task_vm_argc': 1, 'task_vm_arg0': 0x42})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_callback_result'] == 0x15c
    for callback, expected in ((0x50, 0x18d), (0x51, 0x56)):
        m.set_state({'task_vm_pending': 1, 'task_vm_return': 1, 'task_vm_callback': callback})
        m.call('shadowrun_snes_task_native', 0)
        s = m.snapshot()
        assert s['task_native_supported'] == 1 and s['task_callback_result'] == expected
    m.set_state({'task_vm_pending': 1, 'task_vm_return': 1, 'task_vm_arg0': 0x43})
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_native_supported'] == 0


def test_distance_callback_preserves_source_ffff_index_wrap():
    m = machine()
    heap, shared, frames = [0] * 1996, [0] * 65536, [0] * 48
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 8] = 5
    def word(address, value):
        shared[address], shared[address + 1] = value & 255, value >> 8
    word(0x0cde, 0xffff)
    word(0x0e43, 20)
    word(0x0e9b, 40)
    word(0x0e44 + 4, 100)
    word(0x0e9c + 4, 80)
    m.set_state({'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 10, 'task_vm_return': 1, 'task_vm_arg0': 4,
                 'task_heap': heap, 'task_frame': frames, 'task_shared': shared})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    at = 0x4ff - 0x3f2
    assert s['task_native_supported'] == 1
    assert s['task_heap'][at] | s['task_heap'][at + 1] << 8 == 20


def test_invalid_frame_and_pending_callback_fail_without_writes():
    m = machine()
    frames = [0] * 48
    frames[8] = 0xffff
    m.set_state({'task_index': 16, 'task_frame': frames})
    before = m.snapshot()['task_heap']
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert s['task_vm_status'] == 0 and s['task_heap'] == before
    shared = s['task_shared']
    m.set_state({'task_vm_pending': 1, 'task_vm_pending_task': 16,
                 'task_vm_callback': 0x3b, 'task_vm_arg0': 3})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 0 and s['task_vm_pending'] == 1
    assert s['task_shared'] == shared
    m.call('shadowrun_snes_task_callback_complete', 0)
    assert m.snapshot()['task_vm_pending'] == 1


def test_invalid_unlink_refuses_without_partial_free():
    m = machine()
    heap, frames, links, nexts = [0] * 1996, [0] * 48, [0] * 48, [0] * 48
    frames[8] = 0x410
    heap[0x410 - 0x3f2 - 3] = 0x80
    links[8], nexts[8] = 0xffff, 0x12
    links[9] = 0x14
    m.set_state({'task_index': 0x10, 'task_vm_status': 4, 'task_heap': heap,
                 'task_frame': frames, 'task_link': links, 'task_next': nexts,
                 'task_list_head': 0x10, 'task_list_free': 0xffff})
    before = m.snapshot()
    m.call('shadowrun_snes_task_terminate', 0)
    after = m.snapshot()
    assert after['task_supported'] == 0
    for name in ('task_heap', 'task_link', 'task_next', 'task_list_head', 'task_list_free'):
        assert after[name] == before[name]


def test_zero_or_negative_wait_refuses_before_installing_wait():
    import hashlib
    for mask in (0, 0x8000):
        rom = bytearray(0x16000)
        rom[:6] = bytes([0xc0, 0x14, mask & 255, mask >> 8, 0x58, 0x9e])
        rom[0x15895 + 0x9e] = 2
        rom[0x157ba + 0x9e] = 2
        rom = bytes(rom)
        region = {'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}
        m = GameMachine(author_program(SOURCE.read_text(), [region]), {0: rom})
        heap, frames = [0] * 1996, [0] * 48
        frames[8] = 0x400
        heap[0x400 - 0x3f2 + 1] = 0x80
        heap[0x400 - 0x3f2 + 2] = 0x80
        heap[0x400 - 0x3f2 + 8] = 5
        m.set_state({'task_index': 16, 'task_frame': frames, 'task_heap': heap})
        m.call('shadowrun_snes_task_vm', 0)
        s = m.snapshot()
        assert s['task_vm_status'] == 0 and s['task_wait'][8] == 0
        assert s['task_callback'][8] == 0


def test_entity_and_actor_flag_callbacks_use_shared_source_state():
    m = machine()
    shared, heap, frames = [0] * 65536, [0] * 1996, [0] * 48
    actor = 0x32
    at = 0x13c4 + actor
    shared[at:at + 2] = [0, 0x30]
    shared[0x3003:0x3005] = [2, 0]
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 8] = 5
    m.set_state({'task_shared': shared, 'task_heap': heap, 'task_frame': frames,
                 'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 0xc5, 'task_vm_return': 1, 'task_vm_arg0': actor})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_callback_result'] == 0xffff
    m.set_state({'task_vm_pending': 1, 'task_vm_callback': 0xc4, 'task_vm_return': 0})
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_shared'][0x3003:0x3005] == [0x38, 0x15]
    m.set_state({'task_vm_pending': 1, 'task_vm_callback': 0xce, 'task_vm_arg1': 0x100})
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_shared'][0x1474 + actor:0x1476 + actor] == [0, 1]
    m.set_state({'task_vm_pending': 1, 'task_vm_callback': 0x2c, 'task_vm_arg1': 0xff})
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_shared'][0x1474 + actor:0x1476 + actor] == [0, 0]
    shared = m.snapshot()['task_shared']
    shared[0x3001] = 0x83
    m.set_state({'task_shared': shared, 'task_vm_pending': 1, 'task_vm_callback': 0x7a,
                 'task_vm_arg1': 0xfffd})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_shared'][0x3001] == 0x81


def test_local_byte_store_and_native_metadata_are_rom_derived():
    import hashlib
    rom = bytearray(0x16000)
    rom[:6] = bytes([0, 0xab, 0x2c, 4, 0x58, 0xe0])
    rom[0x15895 + 0xe0] = 0
    rom[0x157ba + 0xe0] = 2
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    heap, frames = [0] * 1996, [0] * 48
    frame = 0x400
    frames[8] = frame
    heap[frame - 0x3f2 + 1] = 0x80
    heap[frame - 0x3f2 + 2] = 0x80
    heap[frame - 0x3f2 + 8] = 5
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 16})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert s['task_heap'][frame - 0x3f2 + 0x13 + 4] == 0xab
    assert (s['task_vm_status'], s['task_vm_callback'], s['task_vm_argc'],
            s['task_vm_return']) == (2, 0xe0, 0, 1)
    m.call('shadowrun_snes_task_native', 0)
    assert m.snapshot()['task_native_supported'] == 0
    assert m.snapshot()['task_vm_pending'] == 1


def test_source_subroutine_call_and_return_use_frame_return_stack():
    import hashlib
    rom = bytearray(0x16000)
    rom[:12] = bytes([0x4c, 7, 0, 0, 0x11, 0x56, 0xff,
                      0, 0x22, 0x2c, 4, 0x50])
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    heap, frames = [0] * 1996, [0] * 48
    frame = 0x400
    frames[8] = frame
    heap[frame - 0x3f2 + 1] = 0x80
    heap[frame - 0x3f2 + 2] = 0x80
    heap[frame - 0x3f2 + 5] = 0x11
    heap[frame - 0x3f2 + 6] = 0x04
    heap[frame - 0x3f2 + 8] = 5
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 16})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_return_value']) == (4, 0x11)
    assert s['task_heap'][frame - 0x3f2 + 0x13 + 4] == 0x22


def test_source_waypoint_setter_and_placement_use_shared_pointer():
    import hashlib
    rom = bytearray(0x20000)
    rom[0x19001:0x19007] = bytes([0x2c, 1, 0x90, 1, 5, 0])
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    shared = [0] * 65536
    shared[0xf3:0xf6] = [0, 0x90, 0x83]
    m.set_state({'task_shared': shared, 'task_index': 16, 'task_vm_pending_task': 16,
                 'task_vm_pending': 1, 'task_vm_callback': 0x1d,
                 'task_vm_arg0': 0x46, 'task_vm_arg1': 0})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    def word(addr):
        return s['task_shared'][addr] | s['task_shared'][addr + 1] << 8
    assert s['task_native_supported'] == 1
    assert (word(0x4114 + 0x46), word(0x416c + 0x46), word(0x41c4 + 0x46),
            word(0x40bc + 0x46)) == (1, 1200, 1600, 1)
    m.set_state({'task_vm_pending': 1, 'task_vm_callback': 0xb5, 'task_vm_arg0': 0x54})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1
    assert (word(0x0e44 + 0x54), word(0x0e9c + 0x54), word(0x0ef4 + 0x54),
            word(0x40bc + 0x54)) == (1200, 1600, 20, 0)


def test_native_seven_word_call_preserves_source_pop_order_and_scratch():
    import hashlib
    rom = bytearray(0x16000)
    code = bytes([0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0x58, 0xe0])
    rom[:len(code)] = code
    rom[0x15895 + 0xe0] = 7
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    heap, frames = [0] * 1996, [0] * 48
    frame = 0x400
    frames[8] = frame
    heap[frame - 0x3f2 + 1] = 0x80
    heap[frame - 0x3f2 + 2] = 0x80
    heap[frame - 0x3f2 + 8] = 5
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 16})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_vm_argc']) == (2, 7)
    assert [s[f'task_vm_arg{i}'] for i in range(7)] == [7, 6, 5, 4, 3, 2, 1]
    assert s['task_shared'][:14] == [7, 0, 6, 0, 5, 0, 4, 0, 3, 0, 2, 0, 1, 0]


def test_tainted_direct_reads_refuse_including_word_overlap():
    import hashlib
    for address, taints, expect in ((0x1d04, {'task_rng_tainted': 1}, 0),
                                     (0x1d03, {'task_rng_tainted': 1}, 0),
                                     (0x1cff, {'task_audio_tainted': 1}, 0),
                                     (0x1d02, {'task_rng_tainted': 1, 'task_audio_tainted': 1}, 4),
                                     (0x1d05, {'task_rng_tainted': 1}, 4)):
        rom = bytearray(0x16000)
        rom[:4] = bytes([0x18, address & 255, address >> 8, 0x56])
        region = bytes(rom)
        program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                       'sha256': hashlib.sha256(region).hexdigest()}])
        m = GameMachine(program, {0: region})
        heap, frames = [0] * 1996, [0] * 48
        frame = 0x400
        frames[8] = frame
        heap[frame - 0x3f2 + 1] = 0x80
        heap[frame - 0x3f2 + 2] = 0x80
        heap[frame - 0x3f2 + 8] = 5
        m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 16, **taints})
        m.call('shadowrun_snes_task_vm', 0)
        assert m.snapshot()['task_vm_status'] == expect


def test_tainted_audio_callback_refuses_without_latch_or_event_write():
    m = machine()
    m.set_state({'task_index': 8, 'task_vm_pending_task': 8, 'task_vm_pending': 1,
                 'task_vm_callback': 0x4c, 'task_vm_arg0': 0x4e,
                 'task_vm_arg1': 0x2e, 'task_vm_arg2': 0xff, 'task_vm_arg3': 3,
                 'task_audio_tainted': 1})
    before = m.snapshot()
    m.call('shadowrun_snes_task_native', 0)
    after = m.snapshot()
    assert (after['task_native_supported'], after['task_vm_pending']) == (0, 1)
    assert after['task_audio_count'] == before['task_audio_count']
    assert after['task_shared'] == before['task_shared']


def test_native_velocity_setter_updates_three_words_without_moving_actor():
    m = machine()
    shared = [0] * 65536
    shared[0x0e44 + 0x46:0x0e46 + 0x46] = [0x23, 1]
    m.set_state({'task_shared': shared, 'task_index': 16, 'task_vm_pending_task': 16,
                 'task_vm_pending': 1, 'task_vm_callback': 0x79,
                 'task_vm_arg0': 0x46, 'task_vm_arg1': 2,
                 'task_vm_arg2': 0xfffe, 'task_vm_arg3': 0})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1
    assert s['task_shared'][0x0d3c + 0x46:0x0d3e + 0x46] == [2, 0]
    assert s['task_shared'][0x0d94 + 0x46:0x0d96 + 0x46] == [0xfe, 0xff]
    assert s['task_shared'][0x0dec + 0x46:0x0dee + 0x46] == [0, 0]
    assert s['task_shared'][0x0e44 + 0x46:0x0e46 + 0x46] == [0x23, 1]


def test_native_player_control_reset_changes_only_source_words():
    m = machine()
    shared = [0x55] * 65536
    m.set_state({'task_shared': shared, 'task_index': 0, 'task_vm_pending_task': 0,
                 'task_vm_pending': 1, 'task_vm_callback': 0x87})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1
    assert s['task_shared'][0x1d77:0x1d7d] == [255, 255, 0, 0, 0, 0]
    for address in (0x1d81, 0x1d87, 0x1d89):
        assert s['task_shared'][address:address + 2] == [0, 0]
    assert s['task_shared'][0x1d7d] == 0x55


def test_scene_input_reset_preserves_forced_motion_countdown():
    m = machine()
    shared = [0x55] * 65536
    m.set_state({'task_shared': shared})
    m.call('shadowrun_snes_input_reset', 0)
    s = m.snapshot()['task_shared']
    assert s[0x01ec:0x01f8] == [0, 0, 0, 0, 0, 128, 0, 128, 0, 0, 255, 255]
    assert s[0x0204:0x0206] == [0, 0]
    assert s[0x1d81:0x1d83] == [0x55, 0x55]


def test_indexed_source_word_read_returns_on_task_stack():
    m = machine()
    heap, shared, frames = [0] * 1996, [0] * 65536, [0] * 48
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 8] = 5
    shared[0x3bbb + 0x2c:0x3bbd + 0x2c] = [0x34, 0x12]
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_shared': shared,
                 'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 0x57, 'task_vm_return': 1, 'task_vm_arg0': 0x2c})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    at = 0x4ff - 0x3f2
    assert s['task_native_supported'] == 1
    assert (s['task_heap'][at], s['task_heap'][at + 1]) == (0x34, 0x12)


def test_visual_taint_blocks_overlapping_reads_but_not_known_windows():
    m = machine()
    m.set_state({'task_visual_tainted': 1})
    for address, length in ((0x0203, 2), (0x0205, 1), (0x0225, 2), (0x0ce7, 2),
                            (0x0cf3, 1), (0x1473, 2), (0x157e, 1),
                            (0x17ef,2),(0x1801,2),(0x198d,1),(0x1a8d,2),
                            (0x1b8d,1),(0x1c8d,2),(0x3ce3,2),(0x3f03,1),
                            (0x22ff, 2), (0x2adf, 1)):
        assert m.call('task_readable', address, length)['result'] == 0
    for address, length in ((0x0202, 2), (0x0206, 1), (0x0224, 2), (0x0ce6, 2),
                            (0x0cf4, 1), (0x146e, 2), (0x198e,1),(0x1b8e,1),
                            (0x1c92,1),(0x3ce3,1),(0x3f04,1),(0x21a0, 2), (0x2ae0, 1)):
        assert m.call('task_readable', address, length)['result'] == 1


def test_stale_dynamic_collision_words_refuse_until_rebuild():
    m = machine()
    m.set_state({'task_dynamic_stale': 1})
    for address, length in ((0xde87, 2), (0xde88, 1), (0xffff, 1)):
        assert m.call('task_readable', address, length)['result'] == 0
    assert m.call('task_readable', 0xde86, 2)['result'] == 1
    m.set_state({'task_dynamic_stale': 0})
    assert m.call('task_readable', 0xde88, 2)['result'] == 1
    m.set_state({'task_tile_cache_tainted': 1})
    assert m.call('task_readable', 0xde87, 2)['result'] == 0
    assert m.call('task_readable', 0xde86, 2)['result'] == 1
    m.set_state({'task_tile_cache_tainted': 0})
    assert m.call('task_readable', 0xde88, 2)['result'] == 1


def test_dialogue_and_music_taint_refuse_dependent_script_reads():
    m=machine();m.set_state({'task_dialogue_tainted':1,'task_audio_tainted':1})
    for address,length in ((0xda,2),(0xef,1),(0x13f,2),(0x141,1),(0x1cf9,2),(0x1cfa,1)):
        assert m.call('task_readable',address,length)['result']==0
    for address,length in ((0xda,1),(0xf0,1),(0x142,1),(0x1cf9,1),(0x1d01,1)):
        assert m.call('task_readable',address,length)['result']==1


def test_native_entity_byte_two_returns_source_record():
    m = machine()
    heap, shared, frames = [0] * 1996, [0] * 65536, [0] * 48
    actor = 0x42
    shared[0x13c4 + actor:0x13c6 + actor] = [0, 0x30]
    shared[0x3002] = 0xa5
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 8] = 5
    m.set_state({'task_shared': shared, 'task_heap': heap, 'task_frame': frames,
                 'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 8, 'task_vm_return': 1, 'task_vm_arg0': actor})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert s['task_native_supported'] == 1 and s['task_callback_result'] == 0xa5
    assert s['task_heap'][0x4ff - 0x3f2:0x501 - 0x3f2] == [0xa5, 0]


def test_source_equality_opcode_returns_all_bits_set_for_equal_words():
    import hashlib
    rom = bytearray(0x16000)
    rom[:6] = bytes([0, 7, 0, 7, 0xaa, 0x56])
    region = bytes(rom)
    program = author_program(SOURCE.read_text(), [{'id': 0, 'length': len(region),
                                                   'sha256': hashlib.sha256(region).hexdigest()}])
    m = GameMachine(program, {0: region})
    heap, frames = [0] * 1996, [0] * 48
    frame = 0x400
    frames[8] = frame
    heap[frame - 0x3f2 + 1] = 0x80
    heap[frame - 0x3f2 + 2] = 0x80
    heap[frame - 0x3f2 + 8] = 5
    m.set_state({'task_heap': heap, 'task_frame': frames, 'task_index': 16})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_return_value']) == (4, 0xffff)


def test_control_query_reads_two_original_words_without_assuming_zero():
    m = machine()
    heap, shared, frames = [0] * 1996, [0] * 65536, [0] * 48
    frames[8] = 0x400
    heap[0x400 - 0x3f2 + 8] = 5
    shared[0x1da3:0x1da7] = [0, 0, 0xff, 0xff]
    m.set_state({'task_shared': shared, 'task_heap': heap, 'task_frame': frames,
                 'task_index': 16, 'task_vm_pending_task': 16, 'task_vm_pending': 1,
                 'task_vm_callback': 0xc3, 'task_vm_return': 1})
    m.call('shadowrun_snes_task_native', 0)
    s = m.snapshot()
    assert (s['task_native_supported'], s['task_callback_result']) == (1, 0xffff)
