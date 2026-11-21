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


def _dac_source(color):
    end_marker = f'    mov [{color}_after],ax\n'
    end = ASSEMBLY.index(end_marker) + len(end_marker)
    start_marker = '    call wait_offset\n'
    start = ASSEMBLY.rindex(start_marker, 0, end) + len(start_marker)
    return ASSEMBLY[start:end]


def _observe(source, memory, *, status=None, counts=()):
    """Check actual source dataflow; unknown operations require explicit review."""
    instructions, labels = _compile(source)
    registers = {name: 0 for name in ('ax', 'bx', 'cx', 'dx', 'si', 'di')}
    counts, trace, stack = deque(counts), [], []
    pc, zero, above = 0, False, False

    def operand(value):
        return value.removeprefix('byte ').removeprefix('word ').removeprefix('dword ')

    def read(value):
        value = operand(value)
        if value.startswith('['):
            return memory[value[1:-1]]
        if value in registers:
            return registers[value]
        if len(value) == 2 and value[0] in 'abcd' and value[1] in 'lh':
            return (registers[value[0] + 'x'] >> (8 if value[1] == 'h' else 0)) & 255
        return int(value[:-1], 16) if value.endswith('h') else int(value)

    def write(destination, value):
        destination = operand(destination)
        if destination.startswith('['):
            memory[destination[1:-1]] = value
            trace.append(('store', destination[1:-1], value))
        elif destination in registers:
            registers[destination] = value & 65535
        else:
            assert len(destination) == 2 and destination[0] in 'abcd' and destination[1] in 'lh'
            parent, shift = destination[0] + 'x', 8 if destination[1] == 'h' else 0
            registers[parent] = (registers[parent] & ~(255 << shift)) | ((value & 255) << shift)

    for _ in range(128):
        if pc == len(instructions):
            break
        scope, line = instructions[pc]
        pc += 1
        operation, _, arguments = line.partition(' ')
        parts = [part.strip() for part in arguments.split(',')]
        if operation == 'latch_pit2':
            count = counts.popleft()
            registers['ax'] = count
            trace.append(('latch', count))
        elif operation == 'mov':
            write(parts[0], read(parts[1]))
        elif operation in ('xor', 'and'):
            value = read(parts[0]) ^ read(parts[1]) if operation == 'xor' else read(parts[0]) & read(parts[1])
            write(parts[0], value)
            zero = value == 0
        elif operation == 'test':
            zero = read(parts[0]) & read(parts[1]) == 0
        elif operation == 'cmp':
            zero, above = read(parts[0]) == read(parts[1]), read(parts[0]) > read(parts[1])
        elif operation == 'inc':
            bits = 32 if arguments.startswith('dword ') else 16
            value = (read(arguments) + 1) & ((1 << bits) - 1)
            write(arguments, value)
            zero = value == 0
        elif operation == 'in':
            assert parts == ['al', 'dx'] and registers['dx'] == 0x3da
            assert status is not None
            write('al', status)
            trace.append(('status', status))
        elif operation == 'out':
            assert parts == ['dx', 'al']
            trace.append(('out', registers['dx'], read('al')))
        elif operation == 'call':
            assert arguments == 'poll_budget'
            stack.append(pc)
            pc = labels[arguments]
        elif operation in ('je', 'jz', 'jnz', 'ja'):
            take = {'je': zero, 'jz': zero, 'jnz': not zero, 'ja': above}[operation]
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
