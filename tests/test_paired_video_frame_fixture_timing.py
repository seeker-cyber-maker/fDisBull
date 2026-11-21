"""Source/dataflow contracts for the authored timing witness.

These checks interpret only the small measurement routines' integer operations
and substitute ordered PIT/status/DAC events. They do not assemble code, model
instruction timing, launch a guest, or qualify either native producer. The raw
PIT primitive is checked separately so the event substitution cannot hide a
changed channel, byte order, or clobbered witness register.
"""
from collections import deque

import pytest

from support.paired_video_frame_fixture import ASSEMBLY


# A representative 16-bit address, not an asserted assembled COM offset.
_CALIBRATION_BASE = 0x1000


def _lines(source):
    return [line for raw in source.splitlines()
            if (line := raw.partition(';')[0].strip().lower())]


def _compile(source):
    instructions, labels, scope = [], {}, ''
    for line in _lines(source):
        if line.endswith(':'):
            name = line[:-1]
            if not name.startswith('.'):
                scope = name
            labels[scope + name if name.startswith('.') else name] = len(instructions)
        else:
            instructions.append((scope, line))
    return instructions, labels


def _status_source():
    return 'sample_status:\n' + ASSEMBLY.split('sample_status:\n', 1)[1].split('palette_a:\n', 1)[0]


def _vsync_source():
    return 'new_vsync:\n' + ASSEMBLY.split('new_vsync:\n', 1)[1].split('wait_offset:\n', 1)[0]


def _calibration_source():
    return 'collect_calibration:\n' + ASSEMBLY.split('collect_calibration:\n', 1)[1].split('sample_status:\n', 1)[0]


def _dac_source(color):
    end_marker = f'    mov [{color}_after],ax\n'
    end = ASSEMBLY.index(end_marker) + len(end_marker)
    start_marker = '    call wait_offset\n'
    start = ASSEMBLY.rindex(start_marker, 0, end) + len(start_marker)
    return ASSEMBLY[start:end]


def _observe(source, memory, *, status=None, statuses=(), counts=(), calibration=None):
    """Check actual source dataflow; unknown operations require explicit review."""
    instructions, labels = _compile(source)
    registers = {name: 0 for name in ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp')}
    words = {name[1:]: name for name in registers}
    counts, trace, stack = deque(counts), [], []
    assert status is None or not statuses, 'Use one finite status input form'
    status_reads = deque((status,) if status is not None else statuses)
    assert calibration is None or (isinstance(calibration, bytearray) and len(calibration) == 512 * 6)
    pc, zero, above, below, unsigned_comparison = 0, False, False, False, False

    def operand(value):
        return value.removeprefix('byte ').removeprefix('word ').removeprefix('dword ')

    def read(value):
        value = operand(value)
        if value == 'calibration':
            assert calibration is not None, 'The indexed journal requires its bounded byte array'
            return _CALIBRATION_BASE
        if value.startswith('['):
            name = value[1:-1]
            assert name.isidentifier() and name not in registers and name not in words
            return memory[name]
        if value in registers:
            return registers[value]
        if value in words:
            return registers[words[value]] & 65535
        if len(value) == 2 and value[0] in 'abcd' and value[1] in 'lh':
            return (registers['e' + value[0] + 'x'] >> (8 if value[1] == 'h' else 0)) & 255
        return int(value[:-1], 16) if value.endswith('h') else int(value)

    def write(destination, value):
        destination = operand(destination)
        if destination.startswith('['):
            name = destination[1:-1]
            if name in ('di', 'di+2', 'di+4'):
                assert calibration is not None, 'The indexed journal requires its bounded byte array'
                displacement = 0 if name == 'di' else int(name[-1])
                address = read('di') + displacement
                offset = address - _CALIBRATION_BASE
                assert 0 <= offset <= len(calibration) - 2, 'Journal word escaped the 3072-byte region'
                assert 0 <= value <= 65535
                calibration[offset:offset + 2] = value.to_bytes(2, 'little')
                trace.append(('store', address, value))
            else:
                assert name.isidentifier() and name not in registers and name not in words
                memory[name] = value
                trace.append(('store', name, value))
        elif destination in registers:
            registers[destination] = value & 0xffffffff
        elif destination in words:
            parent = words[destination]
            registers[parent] = (registers[parent] & 0xffff0000) | (value & 65535)
        else:
            assert len(destination) == 2 and destination[0] in 'abcd' and destination[1] in 'lh'
            parent, shift = 'e' + destination[0] + 'x', 8 if destination[1] == 'h' else 0
            registers[parent] = (registers[parent] & ~(255 << shift)) | ((value & 255) << shift)

    for _ in range(512):
        if pc == len(instructions):
            break
        scope, line = instructions[pc]
        pc += 1
        operation, _, arguments = line.partition(' ')
        parts = [part.strip() for part in arguments.split(',')]
        if operation == 'latch_pit2':
            count = counts.popleft()
            write('ax', count)
            trace.append(('latch', count))
        elif operation == 'mov':
            if operand(parts[0]) in ('[di]', '[di+2]', '[di+4]'):
                assert parts[0] == operand(parts[0]) and parts[1] in words, 'Indexed journal stores must be words'
            write(parts[0], read(parts[1]))
        elif operation in ('xor', 'and', 'or'):
            left, right = read(parts[0]), read(parts[1])
            value = {'xor': left ^ right, 'and': left & right, 'or': left | right}[operation]
            write(parts[0], value)
            zero = value == 0
            unsigned_comparison = False
        elif operation in ('shl', 'shr'):
            value, shift = read(parts[0]), read(parts[1])
            assert parts[0] in registers and 0 < shift < 32
            write(parts[0], value << shift if operation == 'shl' else value >> shift)
            zero = read(parts[0]) == 0
            unsigned_comparison = False
        elif operation == 'add':
            assert parts[0] in words, 'Only the reviewed word-register ADD is modeled'
            write(parts[0], read(parts[0]) + read(parts[1]))
            zero = read(parts[0]) == 0
            unsigned_comparison = False
        elif operation == 'imul':
            assert len(parts) == 3 and parts[0] in words and parts[1] in words
            value, factor = read(parts[1]), read(parts[2])
            assert -32768 <= factor < 32768
            signed = value - 65536 if value & 0x8000 else value
            write(parts[0], signed * factor)
            unsigned_comparison = False
        elif operation == 'test':
            zero = read(parts[0]) & read(parts[1]) == 0
            unsigned_comparison = False
        elif operation == 'cmp':
            left, right = read(parts[0]), read(parts[1])
            zero, above, below = left == right, left > right, left < right
            unsigned_comparison = True
        elif operation == 'inc':
            bits = 32 if arguments.startswith('dword ') or arguments in registers else 16
            value = (read(arguments) + 1) & ((1 << bits) - 1)
            write(arguments, value)
            zero = value == 0
            unsigned_comparison = False
        elif operation == 'in':
            assert parts == ['al', 'dx'] and read('dx') == 0x3da
            assert status_reads, 'The witness read an undeclared status sample'
            current_status = status_reads.popleft()
            write('al', current_status)
            trace.append(('status', current_status))
        elif operation == 'out':
            assert parts == ['dx', 'al']
            trace.append(('out', read('dx'), read('al')))
        elif operation == 'call':
            assert arguments == 'poll_budget'
            stack.append(pc)
            pc = labels[arguments]
        elif operation in ('je', 'jz', 'jnz', 'ja', 'jb', 'jmp'):
            if operation in ('ja', 'jb'):
                assert unsigned_comparison, 'Unsigned branch requires a current CMP relation'
            take = {'je': zero, 'jz': zero, 'jnz': not zero, 'ja': above, 'jb': below, 'jmp': True}[operation]
            if take:
                if arguments == 'timing_fault':
                    memory['fault'] = 2
                    trace.append(('fault', 2))
                    break
                pc = labels[scope + arguments if arguments.startswith('.') else arguments]
        elif operation == 'ret':
            if not stack:
                break
            pc = stack.pop()
        else:
            raise AssertionError('Unreviewed witness instruction: ' + line)
    else:
        raise AssertionError('Witness source did not finish within its static check bound')
    assert not counts, 'The source did not consume the declared latch events'
    assert not status_reads, 'The source did not consume the declared status events'
    return trace


def _status_memory(previous=0, *, valid=1, generation=3, polls=17):
    return {'current_before': 60000, 'current_after': 59998,
            'previous_before': 60010, 'current_status': previous,
            'previous_status': previous, 'status_valid': valid,
            'vertical_edges': generation, 'poll_count': polls, 'fault': 0}


def test_pit_primitive_keeps_channel_two_latch_byte_order_and_only_ax_clobber():
    primitive = ASSEMBLY.split('%macro latch_pit2 0\n', 1)[1].split('%endmacro', 1)[0]
    assert _lines(primitive) == [
        'mov al,80h', 'out 43h,al', 'in al,42h', 'mov ah,al',
        'in al,42h', 'xchg al,ah',
    ]


@pytest.mark.parametrize('previous,current,upper,vertical', [
    (0, 0, False, 0), (0, 1, True, 0), (0, 8, True, 1), (0, 9, True, 1),
    (1, 0, False, 0), (1, 1, False, 0), (1, 8, True, 1), (1, 9, True, 1),
    (8, 0, False, 0), (8, 1, True, 0), (8, 8, False, 0), (8, 9, True, 0),
    (9, 0, False, 0), (9, 1, False, 0), (9, 8, False, 0), (9, 9, False, 0),
    (0, 0x84, False, 0),  # Other VGA status bits do not demand an upper latch.
])
def test_only_selected_rising_status_bits_take_a_second_latch(previous, current, upper, vertical):
    memory = _status_memory(previous)
    counts = [59980, 59976] if upper else [59980]
    trace = _observe(_status_source(), memory, status=current, counts=counts)
    observations = [event for event in trace if event[0] in ('latch', 'status')]
    assert observations == [('latch', 59980), ('status', current)] + ([('latch', 59976)] if upper else [])
    assert memory['previous_before'] == 60000 and memory['current_before'] == 59980
    assert memory['previous_status'] == previous and memory['current_status'] == current
    assert memory['current_after'] == (59976 if upper else 59998)
    assert memory['vertical_edges'] == 3 + vertical and memory['poll_count'] == 18
    assert memory['fault'] == 0


def test_vertical_journal_brackets_last_low_read_and_first_high_read():
    memory = _status_memory(generation=0)
    _observe(_status_source(), memory, status=0, counts=[59000])
    trace = _observe(_status_source(), memory, status=8, counts=[58980, 58976])
    assert (memory['previous_before'], memory['current_after']) == (59000, 58976)
    assert memory['vertical_edges'] == 1
    upper_index = trace.index(('latch', 58976))
    assert all(index > upper_index for index, event in enumerate(trace)
               if event[0] == 'store' and event[1] != 'poll_count')
    _observe(_status_source(), memory, status=8, counts=[58960])
    assert memory['vertical_edges'] == 1
    _observe(_status_source(), memory, status=0, counts=[58940])
    _observe(_status_source(), memory, status=8, counts=[58920, 58916])
    assert (memory['previous_before'], memory['current_after']) == (58940, 58916)
    assert memory['vertical_edges'] == 2


def test_initial_high_status_does_not_invent_a_vertical_generation():
    memory = _status_memory(valid=0, generation=0)
    _observe(_status_source(), memory, status=9, counts=[59980, 59976])
    assert memory['status_valid'] == 1 and memory['vertical_edges'] == 0
    _observe(_status_source(), memory, status=9, counts=[59960])
    assert memory['vertical_edges'] == 0


@pytest.mark.parametrize('previous,current,valid,upper,vertical', [
    (0, 1, 1, False, 0),   # Bit 0 rises while the vertical bit stays low.
    (8, 9, 1, False, 0),   # Bit 0 rises while the vertical bit stays high.
    (0, 8, 1, True, 1),
    (0, 9, 1, True, 1),    # Simultaneous rises still need one upper latch.
    (1, 9, 0xfe, True, 1), # Preserve the complete nonzero validity byte.
    (9, 8, 1, False, 0),
    (9, 1, 1, False, 0),
    (0, 8, 0, True, 0),    # A first high sample is not a witnessed generation.
    (0, 0x84, 1, False, 0),
])
def test_vertical_waiter_single_sample_fault_snapshot_latches_only_bit_three(previous, current, valid, upper, vertical):
    # The sole admitted sample cannot finish a fresh-low/first-high wait.
    # Its next poll is refused, exposing the complete cached sample at fault.
    memory = _status_memory(previous, valid=valid, polls=199999)
    counts = [59980, 59976] if upper else [59980]
    trace = _observe(_vsync_source(), memory, status=current, counts=counts)
    observations = [event for event in trace if event[0] in ('latch', 'status')]
    assert observations == [('latch', 59980), ('status', current)] + ([('latch', 59976)] if upper else [])
    assert memory['previous_before'] == 60000 and memory['current_before'] == 59980
    assert memory['previous_status'] == previous and memory['current_status'] == current
    assert memory['current_after'] == (59976 if upper else 59998)
    assert memory['vertical_edges'] == 3 + vertical and memory['poll_count'] == 200001
    assert memory['status_valid'] == (valid or 1) and memory['fault'] == 2
    assert trace[-1] == ('fault', 2)


def test_new_vsync_keeps_last_low_first_high_and_ignores_horizontal_rises():
    memory = _status_memory(9)
    trace = _observe(_vsync_source(), memory, statuses=[9, 8, 0, 1, 1, 9],
                     counts=[59980, 59960, 59940, 59920, 59900, 59880, 59876])
    observations = [event for event in trace if event[0] in ('latch', 'status')]
    assert observations == [
        ('latch', 59980), ('status', 9), ('latch', 59960), ('status', 8),
        ('latch', 59940), ('status', 0), ('latch', 59920), ('status', 1),
        ('latch', 59900), ('status', 1), ('latch', 59880), ('status', 9),
        ('latch', 59876),
    ]
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59900, 59880, 59876)
    assert (memory['previous_status'], memory['current_status']) == (1, 9)
    assert memory['vertical_edges'] == 4 and memory['poll_count'] == 23
    assert [event[2] for event in trace if event[:2] == ('store', 'poll_count')] == [23]
    final_upper = trace.index(('latch', 59876))
    assert all(event[0] != 'store' for event in trace[:final_upper])
    assert memory['status_valid'] == 1 and memory['fault'] == 0


@pytest.mark.parametrize('valid,expected_generation', [(0, 3), (1, 4), (0xfe, 4)])
def test_new_vsync_first_high_waits_for_low_without_losing_observed_rises(valid, expected_generation):
    memory = _status_memory(0, valid=valid, generation=2)
    trace = _observe(_vsync_source(), memory, statuses=[8, 0, 9],
                     counts=[59980, 59976, 59960, 59940, 59936])
    assert [event for event in trace if event[0] == 'status'] == [('status', 8), ('status', 0), ('status', 9)]
    assert [event[1] for event in trace if event[0] == 'latch'] == [59980, 59976, 59960, 59940, 59936]
    assert [event[2] for event in trace if event[:2] == ('store', 'vertical_edges')] == list(range(3, expected_generation + 1))
    assert memory['vertical_edges'] == expected_generation
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59960, 59940, 59936)
    assert (memory['previous_status'], memory['current_status']) == (0, 9)
    assert memory['poll_count'] == 20 and memory['status_valid'] == (valid or 1) and memory['fault'] == 0


def test_new_vsync_poll_cap_precedes_io_and_keeps_last_completed_sample():
    memory = _status_memory(8, polls=199998)
    trace = _observe(_vsync_source(), memory, statuses=[8, 0], counts=[59980, 59960])
    assert [event for event in trace if event[0] in ('latch', 'status')] == [
        ('latch', 59980), ('status', 8), ('latch', 59960), ('status', 0),
    ]
    assert [event[2] for event in trace if event[:2] == ('store', 'poll_count')] == [200001]
    assert trace[-1] == ('fault', 2)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59980, 59960, 59998)
    assert (memory['previous_status'], memory['current_status']) == (8, 0)
    assert memory['vertical_edges'] == 3 and memory['fault'] == 2


@pytest.mark.parametrize('valid', [0, 0xfe])
def test_new_vsync_immediate_poll_fault_keeps_both_distinct_entry_states(valid):
    memory = _status_memory(0, valid=valid, polls=200000)
    memory['previous_status'] = 9
    before = dict(memory)
    trace = _observe(_vsync_source(), memory)
    assert memory == dict(before, poll_count=200001, fault=2)
    assert all(event[0] not in ('latch', 'status') for event in trace)
    assert trace[-1] == ('fault', 2)


@pytest.mark.parametrize('valid,expected_generation', [(0, 3), (1, 4)])
def test_new_vsync_poll_fault_keeps_upper_from_an_earlier_completed_rise(valid, expected_generation):
    memory = _status_memory(0, valid=valid, polls=199998)
    trace = _observe(_vsync_source(), memory, statuses=[8, 0], counts=[59980, 59976, 59960])
    assert [event for event in trace if event[0] in ('latch', 'status')] == [
        ('latch', 59980), ('status', 8), ('latch', 59976),
        ('latch', 59960), ('status', 0),
    ]
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59980, 59960, 59976)
    assert (memory['previous_status'], memory['current_status']) == (8, 0)
    assert memory['poll_count'] == 200001 and memory['vertical_edges'] == expected_generation
    assert memory['status_valid'] == 1 and memory['fault'] == 2 and trace[-1] == ('fault', 2)


@pytest.mark.parametrize('valid,statuses,counts,previous,current,expected_polls', [
    (1, [8], [59980, 59976], 60000, 59980, 18),
    (0, [8, 0, 9], [59980, 59976, 59960, 59940, 59936], 59960, 59940, 20),
])
def test_new_vsync_initial_high_validity_controls_the_thirteenth_rise_fault(valid, statuses, counts, previous, current, expected_polls):
    memory = _status_memory(0, valid=valid, generation=12)
    trace = _observe(_vsync_source(), memory, statuses=statuses, counts=counts)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (previous, current, counts[-1])
    assert memory['current_status'] == statuses[-1] and memory['previous_status'] == 0
    assert memory['vertical_edges'] == 13 and memory['poll_count'] == expected_polls
    assert memory['status_valid'] == 1 and memory['fault'] == 2 and trace[-1] == ('fault', 2)
    assert trace.index(('latch', counts[-1])) < trace.index(('store', 'vertical_edges', 13))


@pytest.mark.parametrize('start,expected', [(65535, 65537), (199998, 200000)])
def test_new_vsync_register_poll_count_keeps_word_carry_and_last_admitted_return(start, expected):
    memory = _status_memory(0, polls=start)
    _observe(_vsync_source(), memory, statuses=[0, 8], counts=[59980, 59960, 59956])
    assert memory['poll_count'] == expected and memory['fault'] == 0


def test_source_interpreter_keeps_upper_register_bits_across_byte_and_word_writes():
    memory = {}
    _observe('''mov ebx,12345678h
mov bl,0abh
mov bh,0cdh
mov [after_bytes],ebx
mov bx,1357h
mov [after_word],ebx
mov eax,ebx
shr eax,16
mov [upper_word],ax
''', memory)
    assert memory == {'after_bytes': 0x1234cdab, 'after_word': 0x12341357, 'upper_word': 0x1234}


@pytest.mark.parametrize('generation,expected_fault', [(11, 0), (12, 2)])
def test_new_vsync_keeps_twelfth_rise_and_faults_on_thirteenth_after_bracketing(generation, expected_fault):
    memory = _status_memory(0, generation=generation)
    trace = _observe(_vsync_source(), memory, statuses=[0, 8], counts=[59980, 59960, 59956])
    assert [event for event in trace if event[0] in ('latch', 'status')] == [
        ('latch', 59980), ('status', 0), ('latch', 59960), ('status', 8), ('latch', 59956),
    ]
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59980, 59960, 59956)
    assert (memory['previous_status'], memory['current_status']) == (0, 8)
    assert memory['vertical_edges'] == generation + 1 and memory['poll_count'] == 19
    assert memory['fault'] == expected_fault
    if expected_fault:
        assert trace[-1] == ('fault', 2)
        assert trace.index(('latch', 59956)) < trace.index(('store', 'vertical_edges', 13))


def test_existing_poll_and_retrace_bounds_still_stop_measurement():
    memory = _status_memory(polls=199999)
    _observe(_status_source(), memory, status=0, counts=[59980])
    assert memory['poll_count'] == 200000 and memory['fault'] == 0
    trace = _observe(_status_source(), memory)
    assert memory['poll_count'] == 200001 and memory['fault'] == 2
    assert all(event[0] not in ('latch', 'status') for event in trace)
    memory = _status_memory(generation=11)
    _observe(_status_source(), memory, status=8, counts=[59980, 59976])
    assert memory['vertical_edges'] == 12 and memory['fault'] == 0
    _observe(_status_source(), memory, status=0, counts=[59960])
    _observe(_status_source(), memory, status=8, counts=[59940, 59936])
    assert memory['vertical_edges'] == 13 and memory['fault'] == 2


@pytest.mark.parametrize('color,components', [('b', (42, 21, 1)), ('c', (21, 42, 1))])
def test_complete_dac_triple_is_inside_latches_and_journal_stores_follow(color, components):
    memory = {}
    trace = _observe(_dac_source(color), memory, counts=[12345, 12340])
    assert trace == [
        ('out', 0x3c8, 1), ('latch', 12345),
        *(('out', 0x3c9, value) for value in components),
        ('latch', 12340), ('store', color + '_before', 12345),
        ('store', color + '_after', 12340),
    ]
    assert memory == {color + '_before': 12345, color + '_after': 12340}



def _calibration_memory(previous=0, *, valid=1, generation=3, polls=17, count=0, limited=0):
    memory = _status_memory(previous, valid=valid, generation=generation, polls=polls)
    memory.update(calibration_count=count, calibration_limited=limited)
    return memory, bytearray(512 * 6)


def test_calibration_entry_routes_to_the_dedicated_collector():
    entry = ASSEMBLY.split('%endmacro\n', 1)[1].split('calibration_done:\n', 1)[0]
    calls = [line.removeprefix('call ') for line in _lines(entry) if line.startswith('call ')]
    assert calls == ['setup', 'collect_calibration']
    assert _lines(ASSEMBLY).count('call collect_calibration') == 1
    assert 'call sample_status' not in _lines(ASSEMBLY)


@pytest.mark.parametrize('previous,current,valid,upper,vertical', [
    (0, 0, 1, False, 0),
    (0, 1, 1, True, 0),
    (0, 8, 1, True, 1),
    (0, 9, 1, True, 1),
    (8, 9, 1, True, 0),
    (9, 8, 1, False, 0),
    (8, 1, 0xfe, True, 0),
    (0, 9, 0, True, 0),
    (0, 0x84, 1, False, 0),
])
def test_calibration_seed_latches_selected_rises_but_never_becomes_a_record(previous, current, valid, upper, vertical):
    memory, journal = _calibration_memory(previous, valid=valid, polls=199999)
    trace = _observe(_calibration_source(), memory, status=current,
                     counts=[59980, 59976] if upper else [59980], calibration=journal)
    assert [event for event in trace if event[0] in ('latch', 'status')] == [
        ('latch', 59980), ('status', current),
    ] + ([('latch', 59976)] if upper else [])
    assert (memory['previous_before'], memory['current_before']) == (60000, 59980)
    assert (memory['previous_status'], memory['current_status']) == (previous, current)
    assert memory['current_after'] == (59976 if upper else 59998)
    assert memory['vertical_edges'] == 3 + vertical and memory['status_valid'] == (valid or 1)
    assert memory['poll_count'] == 200001 and memory['fault'] == 2
    assert memory['calibration_count'] == 0 and memory['calibration_limited'] == 0
    assert journal == bytes(512 * 6) and trace[-1] == ('fault', 2)


@pytest.mark.parametrize('valid', [0, 0xfe])
def test_calibration_immediate_poll_fault_keeps_both_distinct_entry_states(valid):
    memory, journal = _calibration_memory(0, valid=valid, polls=200000, count=11)
    memory['previous_status'] = 9
    journal[:] = bytes([0xa5]) * len(journal)
    before, before_journal = dict(memory), bytes(journal)
    trace = _observe(_calibration_source(), memory, calibration=journal)
    assert memory == dict(before, poll_count=200001, fault=2)
    assert journal == before_journal
    assert all(event[0] not in ('latch', 'status') for event in trace)
    assert trace[-1] == ('fault', 2)


def test_calibration_records_every_eligible_rise_with_the_last_low_lower_latch():
    memory, journal = _calibration_memory(count=510)
    trace = _observe(_calibration_source(), memory, statuses=[0, 1, 1, 0, 1],
                     counts=[59980, 59960, 59956, 59940, 59920, 59900, 59896], calibration=journal)
    assert [event for event in trace if event[0] in ('latch', 'status')] == [
        ('latch', 59980), ('status', 0),
        ('latch', 59960), ('status', 1), ('latch', 59956),
        ('latch', 59940), ('status', 1),
        ('latch', 59920), ('status', 0),
        ('latch', 59900), ('status', 1), ('latch', 59896),
    ]
    assert journal[:3060] == bytes(3060)
    assert journal[3060:] == b''.join(value.to_bytes(2, 'little')
                                    for value in (59980, 59956, 3, 59920, 59896, 3))
    stores = [event for event in trace if event[0] == 'store' and
              (isinstance(event[1], int) or event[1] == 'calibration_count')]
    assert stores == [
        ('store', _CALIBRATION_BASE + 3060, 59980),
        ('store', _CALIBRATION_BASE + 3062, 59956),
        ('store', _CALIBRATION_BASE + 3064, 3), ('store', 'calibration_count', 511),
        ('store', _CALIBRATION_BASE + 3066, 59920),
        ('store', _CALIBRATION_BASE + 3068, 59896),
        ('store', _CALIBRATION_BASE + 3070, 3), ('store', 'calibration_count', 512),
    ]
    committed = {'current_after', 'previous_before', 'current_before', 'previous_status',
                 'current_status', 'poll_count', 'status_valid'}
    last_upper = trace.index(('latch', 59896))
    assert all(index > last_upper for index, event in enumerate(trace)
               if event[0] == 'store' and event[1] in committed)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59920, 59900, 59896)
    assert (memory['previous_status'], memory['current_status']) == (0, 1)
    assert memory['poll_count'] == 22 and memory['calibration_count'] == 512
    assert memory['calibration_limited'] == 0 and memory['fault'] == 0


@pytest.mark.parametrize('current,upper,recorded', [(0, False, False), (1, True, True),
                                                  (8, False, False), (9, True, False)])
def test_calibration_seed_fourth_retrace_still_takes_and_classifies_the_second_sample(current, upper, recorded):
    memory, journal = _calibration_memory(0, generation=3)
    counts = [59980, 59976, 59960] + ([59956] if upper else [])
    trace = _observe(_calibration_source(), memory, statuses=[8, current], counts=counts, calibration=journal)
    assert [event for event in trace if event[0] == 'status'] == [('status', 8), ('status', current)]
    assert memory['vertical_edges'] == 4 and memory['poll_count'] == 19
    assert (memory['previous_before'], memory['current_before']) == (59980, 59960)
    assert (memory['previous_status'], memory['current_status']) == (8, current)
    assert memory['current_after'] == (59956 if upper else 59976)
    expected = b''.join(value.to_bytes(2, 'little') for value in (59980, 59956, 4)) if recorded else bytes(6)
    assert journal[:6] == expected and journal[6:] == bytes(len(journal) - 6)
    assert memory['calibration_count'] == int(recorded)
    assert memory['calibration_limited'] == 1 and memory['fault'] == 0


@pytest.mark.parametrize('limited', [0, 0xa5])
def test_calibration_record_512_exit_precedes_the_fourth_retrace_limit(limited):
    memory, journal = _calibration_memory(0, valid=0xfe, generation=3, count=511, limited=limited)
    trace = _observe(_calibration_source(), memory, statuses=[8, 1],
                     counts=[59980, 59976, 59960, 59956], calibration=journal)
    assert journal[:3066] == bytes(3066)
    assert journal[3066:] == b''.join(value.to_bytes(2, 'little') for value in (59980, 59956, 4))
    assert memory['calibration_count'] == 512 and memory['calibration_limited'] == limited
    assert memory['vertical_edges'] == 4 and memory['status_valid'] == 0xfe
    assert memory['current_after'] == 59956 and memory['poll_count'] == 19 and memory['fault'] == 0
    assert all(event[:2] != ('store', 'calibration_limited') for event in trace)


@pytest.mark.parametrize('start,expected', [(65535, 65537), (199998, 200000)])
def test_calibration_register_poll_count_keeps_word_carry_and_last_admitted_record(start, expected):
    memory, journal = _calibration_memory(0, polls=start, count=511)
    _observe(_calibration_source(), memory, statuses=[0, 1],
             counts=[59980, 59960, 59956], calibration=journal)
    assert memory['poll_count'] == expected and memory['calibration_count'] == 512
    assert memory['calibration_limited'] == 0 and memory['fault'] == 0
    assert journal[3066:] == b''.join(value.to_bytes(2, 'little') for value in (59980, 59956, 3))


@pytest.mark.parametrize('valid,statuses,counts,previous,current,upper', [
    (0, [9, 0, 9, 0, 9], [59980, 59976, 59960, 59940, 59936, 59920, 59900, 59896], 59920, 59900, 59896),
    (1, [9, 0, 9], [59980, 59976, 59960, 59940, 59936], 59960, 59940, 59936),
    (0xfe, [9, 0, 9], [59980, 59976, 59960, 59940, 59936], 59960, 59940, 59936),
])
def test_calibration_initial_high_validity_counts_only_witnessed_retraces(valid, statuses, counts, previous, current, upper):
    memory, journal = _calibration_memory(0, valid=valid, generation=2)
    trace = _observe(_calibration_source(), memory, statuses=statuses, counts=counts, calibration=journal)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (previous, current, upper)
    assert (memory['previous_status'], memory['current_status']) == (0, 9)
    assert memory['status_valid'] == (valid or 1) and memory['vertical_edges'] == 4
    assert memory['poll_count'] == 17 + len(statuses)
    assert memory['calibration_count'] == 0 and memory['calibration_limited'] == 1 and memory['fault'] == 0
    assert [event[2] for event in trace if event[:2] == ('store', 'vertical_edges')] == [3, 4]
    assert journal == bytes(len(journal))


@pytest.mark.parametrize('valid,generation,statuses,counts,previous,current,upper,expected_generation,fault', [
    (1, 11, [8, 0], [59980, 59976, 59960], 59980, 59960, 59976, 12, 0),
    (1, 12, [8], [59980, 59976], 60000, 59980, 59976, 13, 2),
    (0xfe, 12, [9], [59980, 59976], 60000, 59980, 59976, 13, 2),
    (0, 12, [0, 9], [59980, 59960, 59956], 59980, 59960, 59956, 13, 2),
])
def test_calibration_global_retrace_fault_precedes_seed_exclusion_and_outer_limit(valid, generation, statuses, counts, previous, current, upper, expected_generation, fault):
    memory, journal = _calibration_memory(0, valid=valid, generation=generation, count=511)
    trace = _observe(_calibration_source(), memory, statuses=statuses, counts=counts, calibration=journal)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (previous, current, upper)
    assert memory['vertical_edges'] == expected_generation and memory['poll_count'] == 17 + len(statuses)
    assert memory['status_valid'] == (valid or 1) and memory['fault'] == fault
    assert memory['calibration_count'] == 511 and memory['calibration_limited'] == int(not fault)
    assert journal == bytes(len(journal))
    if fault:
        assert trace[-1] == ('fault', 2)
        assert trace.index(('latch', upper)) < trace.index(('store', 'vertical_edges', 13))


def test_calibration_late_poll_fault_preserves_completed_record_and_last_upper():
    memory, journal = _calibration_memory(0, polls=199997)
    trace = _observe(_calibration_source(), memory, statuses=[0, 1, 0],
                     counts=[59980, 59960, 59956, 59940], calibration=journal)
    assert journal[:6] == b''.join(value.to_bytes(2, 'little') for value in (59980, 59956, 3))
    assert journal[6:] == bytes(len(journal) - 6)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59960, 59940, 59956)
    assert (memory['previous_status'], memory['current_status']) == (1, 0)
    assert memory['poll_count'] == 200001 and memory['calibration_count'] == 1
    assert memory['calibration_limited'] == 0 and memory['fault'] == 2 and trace[-1] == ('fault', 2)
    assert [event for event in trace if event[0] == 'status'] == [('status', 0), ('status', 1), ('status', 0)]


def test_calibration_from_fresh_observer_state_stops_at_four_retraces():
    memory, journal = _calibration_memory(0, valid=0, generation=0, polls=0)
    for name in ('current_before', 'previous_before', 'current_after'):
        memory[name] = 0
    trace = _observe(_calibration_source(), memory, statuses=[0, 8, 0, 8, 0, 8, 0, 8],
                     counts=[59980, 59960, 59956, 59940, 59920, 59916,
                             59900, 59880, 59876, 59860, 59840, 59836], calibration=journal)
    assert (memory['previous_before'], memory['current_before'], memory['current_after']) == (59860, 59840, 59836)
    assert memory['status_valid'] == 1 and memory['vertical_edges'] == 4 and memory['poll_count'] == 8
    assert memory['calibration_count'] == 0 and memory['calibration_limited'] == 1 and memory['fault'] == 0
    assert [event[2] for event in trace if event[:2] == ('store', 'vertical_edges')] == [1, 2, 3, 4]
    assert journal == bytes(len(journal))


def test_source_interpreter_word_add_wrap_and_signed_imul_preserve_upper_alias_bits():
    memory = {}
    _observe('''mov edi,1234ffffh
add di,2
mov [sum_word],edi
mov eax,5678fffeh
imul di,ax,6
mov [product_word],edi
mov [multiplicand],eax
''', memory)
    assert memory == {'sum_word': 0x12340001, 'product_word': 0x1234fff4, 'multiplicand': 0x5678fffe}


def test_source_interpreter_calibration_words_use_low_di_and_little_endian_bytes():
    memory, journal = {}, bytearray(512 * 6)
    trace = _observe('''mov edi,abcd0000h
mov di,calibration
mov ax,1234h
mov [di],ax
mov dx,0abcdh
mov [di+2],dx
add di,3070
mov [di],ax
mov [address_alias],edi
''', memory, calibration=journal)
    assert journal[:4] == bytes.fromhex('3412cdab') and journal[4:-2] == bytes(len(journal) - 6)
    assert journal[-2:] == bytes.fromhex('3412')
    assert memory == {'address_alias': 0xabcd1bfe}
    assert [event[1] for event in trace if event[0] == 'store' and isinstance(event[1], int)] == [
        _CALIBRATION_BASE, _CALIBRATION_BASE + 2, _CALIBRATION_BASE + 3070,
    ]


@pytest.mark.parametrize('source,message', [
    ('mov di,calibration\nmov al,1\nmov [di],al', 'Indexed journal stores must be words'),
    ('mov di,calibration\nadd di,3072\nmov ax,1\nmov [di],ax', 'Journal word escaped'),
])
def test_source_interpreter_rejects_non_word_or_out_of_journal_stores(source, message):
    with pytest.raises(AssertionError, match=message):
        _observe(source, {}, calibration=bytearray(512 * 6))


@pytest.mark.parametrize('value,expected', [(0, 0), (1, 1), (65535, 2)])
def test_source_interpreter_unsigned_comparison_excludes_equality_from_below(value, expected):
    memory = {}
    _observe(f'''mov ax,{value}
cmp ax,1
jb .lower
ja .higher
mov word [order],1
jmp .done
.lower:
mov word [order],0
jmp .done
.higher:
mov word [order],2
.done:
ret
''', memory)
    assert memory == {'order': expected}


@pytest.mark.parametrize('operation', ['add ax,1', 'and ax,1'])
def test_source_interpreter_refuses_unsigned_branch_on_stale_comparison_flags(operation):
    with pytest.raises(AssertionError, match='Unsigned branch requires a current CMP relation'):
        _observe(f'cmp ax,0\n{operation}\njb .done\n.done:\nret', {})
