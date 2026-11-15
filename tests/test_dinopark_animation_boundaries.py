"""Independent authored boundaries for the observed ACT instruction union.

Expected values follow original finite-width stores, phase ordering and branch
arithmetic documented in the read-only source bindings. No original ACT bytes,
private model imports, runtime internals or emulator fixtures are used.
"""
import struct

import pytest

from fdisbull.dinopark_animation import (
    AnimationRuntime, ProgramValidationError, RuntimeStateError,
)
from fdisbull.dinopark_images import decode_act


def resource(*programs, sprites=3):
    """Construct one-pixel authored ACT sprites and length-prefixed programs."""
    records = [struct.pack('<8H', 1, 1, 0, 0, 0, 0, 2, 1)
               + bytes((0x41, 0, index)) for index in range(sprites)]
    sequence_area = b''.join(struct.pack('<H', len(code)) + code for code in programs) + b'\0'
    position = 14
    offsets = []
    for record in records:
        offsets.append(position)
        position += len(record)
    raw = (b'UNC2' + struct.pack('<HIHH', sprites, position + len(sequence_area),
                                len(programs), len(sequence_area))
           + b''.join(records) + sequence_area
           + struct.pack('<' + 'I' * sprites, *offsets))
    return decode_act(raw)


@pytest.mark.parametrize('initial,vx,vy,wait,threshold,expected', [
    ((32767, 127), 1, 128, 0x4A, 0, (32768, 65535)),
    ((65535, 0), 127, 128, 0x4B, 125, (126, 65408)),
])
def test_signed_boundaries_release_after_wrapped_motion_not_during_schedule(
        initial, vx, vy, wait, threshold, expected):
    code = bytes((0x14, vx, 0x15, vy, wait, 0, threshold, 3))
    runtime = AnimationRuntime(resource(code), initial_positions=[initial])
    scheduled = runtime.schedule(0)
    assert (scheduled.actors[0].x, scheduled.actors[0].y) == initial
    moved = runtime.update(0)
    state = moved.actors[0]
    assert (state.x, state.y) == expected
    assert (state.previous_x, state.previous_y) == initial
    assert moved.released == (0,) and not state.blocked and state.pc == 7


def test_low_byte_motion_deadline_distinguishes_7f_from_signed_80():
    runtime = AnimationRuntime(resource(bytes((0x14, 1, 1, 3))))
    runtime.schedule(0)
    assert runtime.update(127).actors[0].x == 1
    # Explicit clocks are not silently normalized: signed byte 7F is later
    # than logical tick126, whereas signed byte80 is earlier than tick0.
    skipped = runtime.update(126).actors[0]
    assert (skipped.x, skipped.previous_x, skipped.next_motion_tick) == (1, 0, 127)
    assert runtime.update(128).actors[0].x == 2
    wrapped = runtime.update(0).actors[0]
    assert (wrapped.x, wrapped.previous_x, wrapped.next_motion_tick) == (3, 2, 0)


def test_positive_frame_cadence_uses_twice_127_and_exact_deadline():
    code = bytes((0x1C, 3, 0x1A, 127, 0x12, 1, 5, 1, 3))
    runtime = AnimationRuntime(resource(code))
    runtime.schedule(0)
    first = runtime.update(100)
    assert first.draws == ((1, 3, 0, 0, 0),)
    assert first.actors[0].frame_deadline == 354
    assert runtime.update(353).draws == ((1, 3, 0, 0, 0),)
    exact = runtime.update(354)
    assert exact.draws == ((2, 3, 0, 0, 0),)
    assert exact.actors[0].frame_deadline == 608


def test_negative_frame_cadence_doubles_as_signed_word_before_clock_add():
    code = bytes((0x1C, 3, 0x1A, 255, 0x12, 1, 5, 1, 3))
    runtime = AnimationRuntime(resource(code))
    runtime.schedule(0)
    first = runtime.update(100)
    assert first.actors[0].frame_cadence == 65535
    assert first.actors[0].frame_deadline == 98
    # No elapsed time is necessary when the new native deadline is in the past.
    assert runtime.update(100).draws == ((2, 3, 0, 0, 0),)


@pytest.mark.parametrize('mode', [5, 6, 7])
def test_single_frame_cycle_endpoint_releases_but_continuation_waits_for_schedule(mode):
    # The continuation changes x. Update may release the wait but must render
    # the old x before scheduling the continuation as a separate phase.
    code = bytes((0x1C, 1, 0x12, 1, mode, 4, 0x40, 0, 9, 3))
    runtime = AnimationRuntime(resource(code))
    runtime.schedule(0)
    released = runtime.update(1)
    assert released.draws == ((0, 3, 0, 0, 0),)
    assert released.released == (0,) and released.actors[0].x == 0
    runtime.schedule(1)
    assert runtime.actors[0].x == 9
    assert runtime.update(2).draws == ((0, 3, 9, 0, 0),)


@pytest.mark.parametrize('custom_mode', [0xF2, 0xF3])
def test_wait_cycle_end_does_not_invent_a_custom_list_completion_condition(custom_mode):
    code = bytes((0x12, 1, custom_mode, 3, 0, 1, 255, 4, 0x40, 0, 9, 3))
    runtime = AnimationRuntime(resource(code))
    runtime.schedule(0)
    states = [runtime.update(t) for t in range(1, 7)]
    assert all(result.released == () for result in states)
    assert all(result.actors[0].wait_opcode == 4 and result.actors[0].blocked
               and result.actors[0].x == 0 for result in states)
    assert states[0].draws == ((0, 3, 0, 0, 0),)
    assert states[1].draws == ((1, 3, 0, 0, 0),)


def conditional_program(displacement):
    if displacement == 127:
        # Branch at0: 0 + length3 + delta127 =130. The untaken arm hides;
        # the taken arm writes a non-Boolean word and becomes visible.
        head = bytes((0x5F, 31, 127, 0x12, 0, 3))
        return head + b'\x03' * 124 + bytes((0x5D, 30, 255, 0x12, 1, 3))
    # Initial branch17 at0 jumps to129 (2+127). Conditional branch there
    # uses FF: 129 + length3 -129 =3. It is not a signed-byte -1 offset.
    head = bytes((0x17, 127, 3, 0x5D, 31, 0, 0x12, 1, 3))
    return head + b'\x03' * 120 + bytes((0x5F, 31, 255, 0x12, 0, 3))


@pytest.mark.parametrize('displacement', [127, 255])
@pytest.mark.parametrize('signal,visible', [(1, 1), (2, 0)])
def test_conditional_extreme_displacements_land_on_independent_valid_targets(
        displacement, signal, visible):
    runtime = AnimationRuntime(resource(conditional_program(displacement)))
    result = runtime.schedule(0, signals={31: signal})
    assert result.actors[0].visible == visible
    words = struct.unpack('<32H', runtime.signal_bytes())
    if displacement == 127:
        assert words[30] == (65535 if signal == 1 else 0)
        assert words[31] == signal
    else:
        assert words[31] == (0 if signal == 1 else 2)


@pytest.mark.parametrize('mode,marker,expected_frame,expected_cursor', [
    (0xF2, 255, 2, 0), (0xF2, 0, 2, 0),
    (0xF3, 255, 1, 255), (0xF3, 0, 2, 0),
])
def test_custom_ff_cursor_observes_adjacent_actor_table_bytes(
        mode, marker, expected_frame, expected_cursor):
    # Actor0's cursorFF probes actor1+C3 and can read actor1+C2, i.e.
    # frame-table positions22 and21. A conceptual -1 table iterator fails F3.
    first = bytes((0x12, 1, mode, 3, 2, 0, 255, 1, 3))
    neighbor_table = [0] * 23
    neighbor_table[1] = 255
    neighbor_table[21] = 1
    neighbor_table[22] = marker
    second = bytes((0xF3, 23, *neighbor_table, 1, 3))
    runtime = AnimationRuntime(resource(first, second))
    runtime.schedule(0)
    result = runtime.update(1)
    assert result.draws == ((expected_frame, 3, 0, 0, 0),)
    assert result.actors[0].cycle_index == expected_cursor


@pytest.mark.parametrize('mode,count', [(5, 0), (5, 33), (6, 0), (6, 33)])
def test_bad_dynamic_cycle_count_rolls_back_earlier_actor_signal_and_clock(mode, count):
    writer = bytes((0x5D, 31, 255, 0x40, 0, 9, 3))
    bad_cycle = bytes((0x1C, count, mode, 1, 3))
    runtime = AnimationRuntime(resource(writer, bad_cycle))
    before = runtime.snapshot()
    with pytest.raises(RuntimeStateError, match='bounded table'):
        runtime.schedule(57, signals={0: 1})
    assert runtime.snapshot() == before
    assert runtime.signal_bytes() == bytes(64)


@pytest.mark.parametrize('code', [
    bytes((0xF2, 33, *([0] * 32), 255, 1, 3)),
    bytes((0xF3, 33, *([0] * 32), 255, 1, 3)),
    bytes((0xF2, 3, 0, 1, 2, 1, 3)),
    bytes((0xF3, 2, 255, 0, 1, 3)),
])
def test_custom_table_overrun_and_missing_or_initial_marker_refuse_eagerly(code):
    with pytest.raises(ProgramValidationError):
        AnimationRuntime(resource(code))


def test_unobserved_motion_cadence_opcode_is_not_silently_enabled_by_new_field():
    with pytest.raises(ProgramValidationError, match='outside'):
        AnimationRuntime(resource(bytes((0x18, 1, 1, 3))))


def test_signed_draw_arguments_survive_multiple_actor_ordering_without_booleanization():
    later = bytes((0x10, 1, 0x1F, 127, 0x12, 1, 1, 3))
    earlier = bytes((0x10, 0, 0x1F, 255, 0x12, 1, 1, 3))
    runtime = AnimationRuntime(resource(later, earlier), initial_positions=[(1, 2), (3, 4)])
    runtime.schedule(0)
    result = runtime.update(1)
    assert result.draws == ((0, 3, 3, 4, 65535), (0, 3, 1, 2, 127))
