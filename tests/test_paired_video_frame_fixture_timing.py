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


def _dac_source(color):
    end_marker = f'    mov [{color}_after],ax\n'
    end = ASSEMBLY.index(end_marker) + len(end_marker)
    start_marker = '    call wait_offset\n'
    start = ASSEMBLY.rindex(start_marker, 0, end) + len(start_marker)
    return ASSEMBLY[start:end]


def _observe(source, memory, *, status=None, statuses=(), counts=()):
    """Check actual source dataflow; unknown operations require explicit review."""
    instructions, labels = _compile(source)
    registers = {name: 0 for name in ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp')}
    words = {name[1:]: name for name in registers}
    counts, trace, stack = deque(counts), [], []
    assert status is None or not statuses, 'Use one finite status input form'
    status_reads = deque((status,) if status is not None else statuses)
    pc, zero, above = 0, False, False

    def operand(value):
        return value.removeprefix('byte ').removeprefix('word ').removeprefix('dword ')

    def read(value):
        value = operand(value)
        if value.startswith('['):
            return memory[value[1:-1]]
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
            memory[destination[1:-1]] = value
            trace.append(('store', destination[1:-1], value))
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
            write(parts[0], read(parts[1]))
        elif operation in ('xor', 'and', 'or'):
            left, right = read(parts[0]), read(parts[1])
            value = {'xor': left ^ right, 'and': left & right, 'or': left | right}[operation]
            write(parts[0], value)
            zero = value == 0
        elif operation in ('shl', 'shr'):
            value, shift = read(parts[0]), read(parts[1])
            assert parts[0] in registers and 0 < shift < 32
            write(parts[0], value << shift if operation == 'shl' else value >> shift)
            zero = read(parts[0]) == 0
        elif operation == 'test':
            zero = read(parts[0]) & read(parts[1]) == 0
        elif operation == 'cmp':
            zero, above = read(parts[0]) == read(parts[1]), read(parts[0]) > read(parts[1])
        elif operation == 'inc':
            bits = 32 if arguments.startswith('dword ') or arguments in registers else 16
            value = (read(arguments) + 1) & ((1 << bits) - 1)
            write(arguments, value)
            zero = value == 0
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
        elif operation in ('je', 'jz', 'jnz', 'ja', 'jmp'):
            take = {'je': zero, 'jz': zero, 'jnz': not zero, 'ja': above, 'jmp': True}[operation]
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
