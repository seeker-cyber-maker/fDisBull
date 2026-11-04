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
    for address, length in ((0x0225, 2), (0x1473, 2), (0x157e, 1),
                            (0x22ff, 2), (0x2adf, 1)):
        assert m.call('task_readable', address, length)['result'] == 0
    for address, length in ((0x0224, 2), (0x146e, 2), (0x21a0, 2), (0x2ae0, 1)):
        assert m.call('task_readable', address, length)['result'] == 1


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
