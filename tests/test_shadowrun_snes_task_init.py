"""Source allocator invariants, synthetic ROM tables, and guarded failures."""
import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_task_init import SOURCE, VM_SOURCE


def machine():
    rom = bytearray(1048576)
    for script, size, argc in ((0, (4, 8), 2), (1, (9, 13), 0), (2, (4, 8), 3)):
        rom[0x15970 + script] = 0x83
        code = 0x9000 + script * 0x10
        rom[0x15d18 + script * 2:0x15d1a + script * 2] = code.to_bytes(2, 'little')
        rom[0x16810 + script] = argc
        off = 0x18000 + (code & 0x7fff)
        rom[off:off + 2] = bytes(size)
    rom[0x19002:0x19007] = bytes([0x52, 1, 0, 0xc0, 0x56])
    region = bytes(rom)
    program = author_program(VM_SOURCE.read_text() + '\n' + SOURCE.read_text(),
                             [{'id': 0, 'length': len(region),
                               'sha256': hashlib.sha256(region).hexdigest()}])
    result = GameMachine(program, {0: region})
    result.call('shadowrun_snes_task_reset', 0)
    return result


def word(data, at):
    return data[at] | data[at + 1] << 8


def test_reset_and_source_task_frame_and_list_creation():
    m = machine()
    s = m.snapshot()
    assert (s['task_list_head'], s['task_list_current'], s['task_list_free']) == (0xffff, 0xffff, 0)
    assert s['task_next'] == list(range(2, 96, 2)) + [0xffff]
    assert s['task_heap_first_header'] == [0xcc, 0x07, 0, 0]
    args = [0] * 256
    args[:2] = [0x44, 0x12]
    m.set_state({'task_init_script': 0, 'task_init_args': args})
    m.call('shadowrun_snes_task_create', 0)
    s = m.snapshot()
    assert (s['task_init_supported'], s['task_init_result'], s['task_list_head'],
            s['task_list_free'], s['task_frame'][0]) == (1, 0, 0, 2, 0x3f2)
    assert word(s['task_heap_first_header'], 0) == 0x8023
    assert word(s['task_heap_first_header'], 2) == 39
    assert word(s['task_heap'], 35) == 1957
    assert word(s['task_heap'], 0) == 0x9002
    assert s['task_heap'][2] == 0x83 and word(s['task_heap'], 3) == 0
    assert word(s['task_heap'], 5) == 0x403
    assert word(s['task_heap'], 7) == 0x412
    assert s['task_heap'][33:35] == [0x44, 0x12]
    m.call('shadowrun_snes_task_create', 0)
    s = m.snapshot()
    assert (s['task_init_result'], s['task_list_head'], s['task_list_free']) == (2, 2, 4)
    assert (s['task_next'][1], s['task_link'][0], s['task_link'][1]) == (0, 2, 0xffff)


def test_adjacent_free_blocks_coalesce_before_split():
    m = machine()
    heap = [0] * 1996
    def put(at, value):
        heap[at - 4:at - 2] = [value & 255, value >> 8]
    put(24, 20)
    put(26, 48)
    put(48, 1948)
    put(50, 0)
    m.set_state({'task_heap_first_header': [20, 0, 24, 0], 'task_heap': heap})
    m.call('shadowrun_snes_task_create', 0)
    s = m.snapshot()
    assert s['task_init_supported'] == 1
    assert word(s['task_heap_first_header'], 0) == 0x8023
    assert word(s['task_heap_first_header'], 2) == 39
    assert word(s['task_heap'], 35) == 5
    assert word(s['task_heap'], 37) == 48


def test_invalid_source_inputs_and_corrupt_heap_refuse_without_state_change():
    for changes in ({'task_init_script': 2}, {'task_list_free': 0xffff},
                    {'task_init_script': 936}, {'task_heap_first_header': [10, 0, 2, 0]},
                    {'task_heap_first_header': [0xcc, 0x87, 0, 0]}):
        m = machine()
        m.set_state(changes)
        before = m.snapshot()
        m.call('shadowrun_snes_task_create', 0)
        after = m.snapshot()
        assert after['task_init_supported'] == 0
        for name in ('task_heap', 'task_heap_first_header', 'task_frame', 'task_next',
                     'task_link', 'task_list_head', 'task_list_free'):
            assert after[name] == before[name]


def test_nested_task_inserts_before_parent_and_parent_resumes_after_return():
    m = machine()
    m.call('shadowrun_snes_task_create', 0)
    assert m.snapshot()['task_init_supported'] == 1
    m.set_state({'task_index': 0, 'task_list_current': 0})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_vm_child_id'], s['task_vm_child_argc']) == (5, 1, 0)
    m.call('shadowrun_snes_task_create_child', 0)
    s = m.snapshot()
    assert (s['task_init_supported'], s['task_init_result'], s['task_list_head'],
            s['task_next'][1], s['task_link'][0], s['task_wait'][0],
            s['task_callback'][0], s['task_vm_resume'][0]) == (1, 2, 2, 0, 2, 0xffff, 0xf45e, 3)
    m.set_state({'task_index': 2, 'task_list_current': 2, 'task_vm_status': 4,
                 'task_return_value': 7})
    m.call('shadowrun_snes_task_terminate', 0)
    s = m.snapshot()
    assert (s['task_supported'], s['task_list_head'], s['task_list_current']) == (1, 0, 0)
    waits = s['task_wait']
    waits[0] = 0
    m.set_state({'task_index': 0, 'task_wait': waits})
    m.call('shadowrun_snes_task_vm', 0)
    s = m.snapshot()
    assert (s['task_vm_status'], s['task_return_value'], s['task_vm_resume'][0]) == (4, 0, 0)


def test_first_heap_block_can_be_released_without_losing_header():
    m = machine()
    m.call('shadowrun_snes_task_create', 0)
    assert m.snapshot()['task_frame'][0] == 0x3f2
    m.set_state({'task_index': 0, 'task_list_current': 0, 'task_vm_status': 4})
    m.call('shadowrun_snes_task_terminate', 0)
    s = m.snapshot()
    assert s['task_supported'] == 1
    assert word(s['task_heap_first_header'], 0) == 35
    assert word(s['task_heap_first_header'], 2) == 39
    assert (s['task_list_head'], s['task_list_free']) == (0xffff, 0)
