"""Authored ACT programs exercise interpreter contracts without game payloads."""
import hashlib
import json
import struct
from dataclasses import replace

import pytest

from fdisbull.dinopark_animation import (
    AnimationRuntime, ProgramValidationError, RuntimeBudgetExceeded,
    RuntimeStateError, decode_instruction, describe_animation, inspect_animation,
    program,
)
from fdisbull.dinopark_images import decode_act


def actor(programs, sprites=3):
    records = [struct.pack('<8H', 1, 1, 0, 0, 0, 0, 2, 1) + bytes((0x41, 0, i))
               for i in range(sprites)]
    area = b''.join(struct.pack('<H', len(p)) + p for p in programs) + b'\xa7'
    at = 14
    offsets = []
    for record in records:
        offsets.append(at)
        at += len(record)
    return (b'UNC2' + struct.pack('<HIHH', sprites, at + len(area), len(programs), len(area))
            + b''.join(records) + area + struct.pack('<' + 'I' * sprites, *offsets))


@pytest.mark.parametrize('raw,length,args', [
    (b'\x03', 1, ()),
    (b'\x11\xff', 2, (-1,)),
    (b'\x40\xff\xfe', 3, (-2,)),
    (b'\x5d\x03\xfd', 3, (3, -3)),
    (b'\x67\x00\x81\xff', 4, (129, -1)),
    (b'\x80\xff\x00\x81', 4, (-1, 129)),
    (b'\x90\x01\x02\xff', 4, (1, 2, -1)),
    (b'\xb0\xff\xfe\x00\x81', 5, (-2, 129)),
    (b'\xd0\xff\xfe\x00\x81\xff', 6, (-2, 129, -1)),
    (b'\xf3\x02\x04\xff\x03', 4, (2, (4, -1))),
    (b'\xf7\x05\x02\x04\xff', 4, (5, 2, (4, -1))),
    (b'\x66', 1, ()), (b'\xff', 1, ()),
])
def test_operand_classes_preserve_big_endian_signed_widths_and_reader_gaps(raw, length, args):
    token = decode_instruction(raw)
    assert token.length == length and token.operands == args
    for end in range(length):
        with pytest.raises(ValueError):
            decode_instruction(raw[:end])


def test_variable_lookahead_is_required_but_does_not_advance_pc():
    code = b'\xf3\x02\x04\xff\x03'
    decoded = program(code)
    assert [(i.offset, i.opcode) for i in decoded] == [(0, 0xf3), (4, 3)]
    assert decoded[0].scratch == b'\x04\xff\x03'
    with pytest.raises(ValueError, match='lookahead'):
        decode_instruction(code[:-1])
    with pytest.raises(ValueError, match='negative'):
        decode_instruction(b'\xf3\xff')


def test_report_binds_container_offsets_and_hashes_without_retaining_program_data():
    codes = (b'\x12\x01\x03', b'\xf3\x02\x01\xff\x03')
    raw = actor(codes)
    inspected = inspect_animation(raw)
    report = describe_animation(raw)
    assert report['program_count'] == 2 and report['instruction_count'] == 4
    for item, code in zip(inspected.programs, codes):
        assert raw[item.file_offset:item.file_offset+item.length] == code
        assert item.sha256 == hashlib.sha256(code).hexdigest()
    encoded = json.dumps(report)
    assert not any(x in encoded for x in ['scratch', 'hex', 'operands', 'code_bytes'])
    assert report['programs'][1]['instructions'][0]['read_length'] == 5
    with pytest.raises(ValueError, match='instruction budget'):
        describe_animation(raw, max_instructions=3)
    with pytest.raises(ValueError):
        describe_animation(raw, max_instructions=True)
    with pytest.raises(ValueError, match='source byte budget'):
        describe_animation(raw, max_source_bytes=1)


def test_unknown_operand_shape_is_inspectable_but_never_executable():
    raw = actor((b'\x02\x03',))
    report = describe_animation(raw)
    assert report['programs'][0]['unsupported_opcodes'] == [2]
    with pytest.raises(ProgramValidationError, match='outside'):
        AnimationRuntime(decode_act(raw))


def test_ordered_render_then_release_then_schedule_uses_actual_signed_coordinates():
    # Base sprite 1, explicit coordinates (-2,3), visible, wait five ticks;
    # after release select relative frame 1, then yield at terminal.
    code = bytes((0x1b,1,0x1c,1,0x40,0xff,0xfe,0x41,0,3,0x12,1,0x4e,0,5,0x11,1,3))
    runtime = AnimationRuntime(decode_act(actor((code,))))
    assert runtime.tick(0).draws == ()
    assert runtime.tick(1).draws == ((1,3,65534,3,0),)
    released = runtime.tick(5)
    assert released.draws == ((1,3,65534,3,0),)
    assert released.released == (0,) and released.actors[0].frame_offset == 1
    assert runtime.tick(6).draws == ((2,3,65534,3,0),)


def test_zero_deadline_sentinel_and_terminal_entry_context_remain_distinct():
    zero = AnimationRuntime(decode_act(actor((b'\x4e\0\0\x03',))))
    assert zero.tick(0).waiting and zero.tick(100).actors[0].pc == 0
    terminal = AnimationRuntime(decode_act(actor((b'\x03',))))
    result = terminal.tick(0)
    assert not result.waiting and not result.actors[0].blocked
    reached = AnimationRuntime(decode_act(actor((b'\x12\0\x03',))))
    result = reached.tick(0)
    assert result.waiting and result.actors[0].blocked


def test_signal_release_is_next_update_not_same_dispatch_and_exactly_one():
    runtime = AnimationRuntime(decode_act(actor((b'\x1d\0\x16\0\x12\1\x03',))))
    assert runtime.tick(0, signals={0:1}).actors[0].wait_opcode == 0x1d
    assert runtime.tick(1, signals={0:2}).actors[0].pc == 0
    released = runtime.tick(2, signals={0:1})
    assert released.released == (0,) and released.actors[0].visible == 1
    assert runtime.signal_bytes() == bytes(64)


def test_budget_failure_rolls_back_all_actors_signals_and_time():
    # Raw branch 80 means -2, returning to this two-byte instruction.
    runtime = AnimationRuntime(decode_act(actor((b'\x16\0\x17\x80',))), instruction_budget=3)
    before = runtime.snapshot()
    with pytest.raises(RuntimeBudgetExceeded):
        runtime.tick(9, signals={0:1})
    assert runtime.snapshot() == before


@pytest.mark.parametrize('code', [b'\x17\x7f', b'\x17\x81\x03', b'\x12\1', b'\x1b\x03\x03', b'\x1d\xff\x03'])
def test_invalid_continuations_sprite_or_signal_references_refuse_eagerly(code):
    with pytest.raises(ProgramValidationError):
        AnimationRuntime(decode_act(actor((code,))))


def test_unsupported_unreachable_tail_is_refused_and_selection_is_bounded():
    resource = decode_act(actor((b'\x03\x08\x03', b'\x03')))
    with pytest.raises(ProgramValidationError):
        AnimationRuntime(resource)
    assert AnimationRuntime(resource, program_indices=[1]).tick(0).executed_commands == 0
    with pytest.raises(ValueError, match='1..16'):
        AnimationRuntime(resource, program_indices=(1 for _ in range(10**9)))
    with pytest.raises(ValueError):
        AnimationRuntime(resource, program_indices=[True])


def test_custom_hold_stays_bounded_and_bad_last_bank_lookahead_rolls_back():
    code = b'\x12\1\xf3\x03\0\1\xff\x19\x01\x03'
    runtime = AnimationRuntime(decode_act(actor((code,))))
    runtime.tick(0)
    assert runtime.tick(1).draws == ((0,3,0,0,0),)
    assert runtime.tick(2).draws == ((1,3,0,0,0),)
    assert runtime.tick(3).draws == ((1,3,0,0,0),)
    bank = AnimationRuntime(decode_act(actor((code,))), program_indices=[0]*16)
    bank.tick(0)
    before = bank.snapshot()
    with pytest.raises(RuntimeStateError, match='16-record'):
        bank.tick(1)
    assert bank.snapshot() == before


def test_hidden_and_suspended_masks_and_failed_inputs_are_transactional():
    runtime = AnimationRuntime(decode_act(actor((b'\x12\1\x4e\0\1\x03',))))
    runtime.tick(0)
    assert runtime.tick(1,suspended=1).draws == ()
    assert runtime.tick(2,hidden=1).draws == ()
    before = runtime.snapshot()
    with pytest.raises(ValueError):
        runtime.tick(True)
    with pytest.raises(ValueError):
        runtime.tick(3,signals={32:1})
    assert runtime.snapshot() == before


def test_explicit_initialization_and_phase_clocks_do_not_invent_an_update():
    resource = decode_act(actor((b'\x1b\1\x12\1\x4e\0\5\x03',)))
    runtime = AnimationRuntime(resource, display_mode=4, initial_time=17,
                               initial_positions=[(77,4)])
    scheduled = runtime.schedule(20)
    state = scheduled.actors[0]
    assert (state.x, state.y, state.width, state.frame_deadline,
            state.next_motion_tick, state.deadline) == (77,4,4,17,0,25)
    assert scheduled.draws == ()
    update = runtime.update(25)
    assert update.draws == ((1,3,77,4,0),) and update.released == (0,)
    assert update.actors[0].pc == 7 and not update.actors[0].blocked
    # Terminal at phase entry is skipped; scheduler does not synthesize update.
    assert not runtime.schedule(27).waiting
    assert runtime.actors[0].frame_deadline == 25
    report = runtime.snapshot()
    assert report['display_mode'] == 4 and 'frame_table' not in report['actors'][0]
    assert 'frame_table' not in runtime.update(28).to_dict()['actors'][0]
    with pytest.raises(ValueError):
        AnimationRuntime(resource, display_mode=5)
    with pytest.raises(ValueError):
        AnimationRuntime(resource, initial_positions=[(-1,0)])
    with pytest.raises(ValueError):
        AnimationRuntime(resource, initial_positions=[])


def test_unknown_semantics_do_not_get_a_semantic_cfg_edge():
    row = describe_animation(actor((b'\x02\x03',)))['programs'][0]['instructions'][0]
    assert row['local_successors'] == [] and row['syntactic_continuation_candidate'] == 1


def test_motion_signed_bytes_wrap_coordinates_and_draw_argument_is_sign_extended():
    code = bytes((0x14,255,0x15,2,0x1f,128,0x12,1,1,3))
    runtime = AnimationRuntime(decode_act(actor((code,))), initial_positions=[(0,65535)])
    runtime.schedule(0)
    result = runtime.update(128)
    assert result.draws == ((0,3,65535,1,0xff80),)
    assert result.actors[0].previous_x == 0 and result.actors[0].previous_y == 65535
    # The next-motion byte 80 is signed -128, so the same logical tick advances.
    again = runtime.update(128)
    assert (again.actors[0].x,again.actors[0].y) == (65534,3)
    assert again.actors[0].wait_opcode == 1 and again.actors[0].blocked


@pytest.mark.parametrize('mode,frames', [(5,[1,2]),(6,[2,1,0]),(7,[1,2,1])])
def test_native_cycle_setup_and_wait_endpoint_order(mode, frames):
    code = bytes((0x1c,3,0x12,1,mode,4,3))
    runtime = AnimationRuntime(decode_act(actor((code,))))
    runtime.schedule(0)
    for time,frame in enumerate(frames,1):
        result = runtime.update(time)
        assert result.draws[0][0] == frame
        assert result.released == ((0,) if time == len(frames) else ())
    assert not runtime.schedule(len(frames)).waiting


def test_pingpong_overflow_refuses_and_rolls_back():
    runtime = AnimationRuntime(decode_act(actor((bytes((0x1c,17,7,1,3)),))))
    before = runtime.snapshot()
    with pytest.raises(RuntimeStateError,match='bounded table'):
        runtime.schedule(0)
    assert runtime.snapshot() == before


def test_custom_forward_loop_restarts_at_marker_without_releasing_block():
    code = b'\x12\1\xf2\3\0\2\xff\x01\x03'
    runtime = AnimationRuntime(decode_act(actor((code,))))
    runtime.schedule(0)
    assert [runtime.update(t).draws[0][0] for t in range(1,6)] == [0,2,0,2,0]
    assert runtime.actors[0].wait_opcode == 1 and runtime.actors[0].blocked


@pytest.mark.parametrize('op,start,velocity,threshold,release',[
    (0x45,0,1,2,2),(0x46,0,1,2,2),(0x4a,0,255,-1,2),
    (0x4b,0,1,1,2),(0x4d,0,1,1,2),
])
def test_signed_coordinate_waits_use_post_motion_state(op,start,velocity,threshold,release):
    vertical = op in (0x46,0x4d)
    code = bytes((0x15 if vertical else 0x14,velocity,op,(threshold>>8)&255,threshold&255,3))
    runtime = AnimationRuntime(decode_act(actor((code,))))
    runtime.schedule(0)
    assert runtime.update(1).released == ()
    assert runtime.update(release).released == (0,)


def test_signal_store_is_word_valued_and_later_actor_branch_uses_exact_one():
    branch = bytes((0x5f,0,3,0x12,0,3,0x12,1,3))
    for value,visible in [(1,1),(2,0),(255,0)]:
        writer = bytes((0x5d,0,value,3))
        runtime = AnimationRuntime(decode_act(actor((writer,branch))))
        result = runtime.schedule(0)
        assert result.actors[1].visible == visible
        assert int.from_bytes(runtime.signal_bytes()[:2],'little') == (value if value<128 else value-256)&65535
    # A signal written by this scheduler does not retroactively release actor0.
    runtime = AnimationRuntime(decode_act(actor((b'\x1d\0\x03',b'\x5d\0\1\x03'))))
    assert runtime.schedule(0).actors[0].wait_opcode == 0x1d
    assert runtime.update(1).released == (0,)


def test_conditional_branch_uses_second_operand_and_preserves_biased_negative_offset():
    # Branch operand B=80 means -2: offset2 + 3 - 2 ==3, which is inside
    # the branch operands, so eager boundary validation must reject it.
    resource = decode_act(actor((b'\x12\0\x5f\0\x80\x03',)))
    with pytest.raises(ProgramValidationError,match='boundary'):
        AnimationRuntime(resource)
    with pytest.raises(ProgramValidationError,match='signal'):
        AnimationRuntime(decode_act(actor((b'\x5d\xff\1\x03',))))
