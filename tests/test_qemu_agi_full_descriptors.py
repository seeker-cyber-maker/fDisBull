"""Compile the actual canonical decoder without QEMU and check its catalog.

Width/name expectations are AGI 2.917 format facts, independently transcribed
from the pinned sources documented in native/qemu-agi/OPCODE_COVERAGE.md. The
native pilot's legacy admission set is deliberately a separate expectation.
No game files, reference implementation, QMP process or guest run is needed.
"""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "native/qemu-agi/overlay/target/agi"
ACTION_NAMES = """return increment decrement assignn assignv addn addv subn subv
lindirectv rindirect lindirectn set reset toggle set.v reset.v toggle.v new.room
new.room.v load.logics load.logics.v call call.v load.pic draw.pic show.pic
discard.pic overlay.pic show.pri.screen load.view load.view.v discard.view
animate.obj unanimate.all draw erase position position.v get.posn reposition
set.view set.view.v set.loop set.loop.v fix.loop release.loop set.cel set.cel.v
last.cel current.cel current.loop current.view number.of.loops set.priority
set.priority.v release.priority get.priority stop.update start.update force.update
ignore.horizon observe.horizon set.horizon object.on.water object.on.land
object.on.anything ignore.objs observe.objs distance stop.cycling start.cycling
normal.cycle end.of.loop reverse.cycle reverse.loop cycle.time stop.motion
start.motion step.size step.time move.obj move.obj.v follow.ego wander normal.motion
set.dir get.dir ignore.blocks observe.blocks block unblock get get.v drop put put.v
get.room.v load.sound sound stop.sound print print.v display display.v clear.lines
text.screen graphics set.cursor.char set.text.attribute shake.screen configure.screen
status.line.on status.line.off set.string get.string word.to.string parse get.num
prevent.input accept.input set.key add.to.pic add.to.pic.v status save.game
restore.game init.disk restart.game show.obj random program.control player.control
obj.status.v quit show.mem pause echo.line cancel.line init.joy toggle.monitor
version script.size set.game.id log set.scan.start reset.scan.start reposition.to
reposition.to.v trace.on trace.info print.at print.at.v discard.view.v
clear.text.rect set.upper.left set.menu set.menu.item submit.menu enable.item
disable.item menu.input show.obj.v open.dialogue close.dialogue mul.n mul.v div.n
div.v close.window set.simple push.script pop.script hold.key""".split()
ACTION_WIDTHS = (
    0,1,1,2,2,2,2,2,2,2,2,2,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,
    1,1,0,1,1,3,3,3,3,2,2,2,2,1,1,2,2,2,2,2,2,2,2,2,1,2,1,1,1,1,1,1,
    1,1,1,1,1,3,1,1,1,2,1,2,2,1,1,2,2,5,5,3,1,1,2,2,1,1,4,0,1,1,1,2,
    2,2,1,2,0,1,1,3,3,3,0,0,1,2,1,3,0,0,2,5,2,1,2,0,0,3,7,7,0,0,0,0,
    0,1,3,0,0,1,1,0,0,0,0,0,0,0,1,1,1,0,0,3,3,0,3,4,4,1,5,2,1,2,0,
    1,1,0,1,0,0,2,2,2,2,0,1,0,0,0,
)
PREDICATE_NAMES = (
    "false", "equaln", "equalv", "lessn", "lessv", "greatern", "greaterv",
    "isset", "isset.v", "has", "obj.in.room", "posn", "controller", "have.key",
    "said", "compare.strings", "obj.in.box", "center.posn", "right.posn",
)
PREDICATE_WIDTHS = (0, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 5, 1, 0, None, 2, 5, 5, 5)
SCALAR_NATIVE = set(range(9)) | {12, 13, 14, 37, 38, 39}
BINDING_NATIVE = SCALAR_NATIVE | {30, 31, 33, 41, 42, 43, 44, 47, 48}
INTENT_NATIVE = BINDING_NATIVE | {35, 70, 71}


class Operand(C.Structure):
    _fields_ = [("role", C.c_char_p), ("kind", C.c_int), ("access", C.c_int),
                ("width", C.c_uint32), ("value", C.c_int32)]


class Condition(C.Structure):
    _fields_ = [("kind", C.c_int), ("pc", C.c_uint32), ("opcode", C.c_uint32),
                ("operand_count", C.c_uint32), ("operand_start", C.c_uint32),
                ("mnemonic", C.c_char_p)]


class Successor(C.Structure):
    _fields_ = [("kind", C.c_int), ("pc", C.c_int64), ("in_range", C.c_bool)]


class Instruction(C.Structure):
    _fields_ = [("pc", C.c_uint32), ("opcode", C.c_uint32), ("size", C.c_uint32),
                ("bytes", C.c_uint8 * 1024), ("mnemonic", C.c_char_p),
                ("operation", C.c_char_p), ("effect_class", C.c_int),
                ("execution_support", C.c_int), ("fault", C.c_int),
                ("operand_count", C.c_uint32), ("condition_count", C.c_uint32),
                ("successor_count", C.c_uint32), ("operands", Operand * 7),
                ("conditions", Condition * 256), ("condition_operand_count", C.c_uint32),
                ("condition_operands", Operand * 1024), ("successors", Successor * 2)]


@pytest.fixture(scope="module")
def native_decoder(tmp_path_factory):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("standalone native decoder checks require a C compiler")
    folder = tmp_path_factory.mktemp("agi-descriptor-native")
    wrapper = folder / "wrapper.c"
    wrapper.write_text(r'''
#include <stddef.h>
#include "decode.h"
typedef struct Input {
    const uint8_t *bytes;
    uint32_t length, reads;
    bool outside;
} Input;
static uint8_t checked_read(void *opaque, uint32_t pc) {
    Input *input = opaque;
    if (pc >= input->length) {
        input->outside = true;
        return 0;
    }
    input->reads++;
    return input->bytes[pc];
}
size_t instruction_size(void) { return sizeof(AgiDecodedInstruction); }
bool decode_buffer(const uint8_t *bytes, uint32_t length, uint32_t pc,
                   int profile, int purpose, AgiDecodedInstruction *out,
                   uint32_t *reads, bool *outside) {
    Input input = { .bytes = bytes, .length = length };
    bool ok = agi_decode(checked_read, &input, length, pc, profile, purpose, out);
    *reads = input.reads;
    *outside = input.outside;
    return ok;
}
''', encoding="utf-8")
    library = folder / "libagi-decode.so"
    result = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
         "-I", str(TARGET), str(TARGET / "decode.c"), str(wrapper), "-o", str(library)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    lib = C.CDLL(str(library))
    lib.instruction_size.restype = C.c_size_t
    assert lib.instruction_size() == C.sizeof(Instruction)
    lib.decode_buffer.argtypes = [C.POINTER(C.c_uint8), C.c_uint32, C.c_uint32,
                                  C.c_int, C.c_int, C.POINTER(Instruction),
                                  C.POINTER(C.c_uint32), C.POINTER(C.c_bool)]
    lib.decode_buffer.restype = C.c_bool
    for name in ("agi_operand_kind_name", "agi_operand_access_name",
                 "agi_successor_kind_name", "agi_effect_class_name",
                 "agi_execution_support_name"):
        function = getattr(lib, name)
        function.argtypes, function.restype = [C.c_int], C.c_char_p

    def decode(raw, *, pc=0, profile=2, execution=False):
        buffer = (C.c_uint8 * len(raw)).from_buffer_copy(raw)
        decoded, reads, outside = Instruction(), C.c_uint32(), C.c_bool()
        ok = lib.decode_buffer(buffer, len(raw), pc, profile, not execution,
                               C.byref(decoded), C.byref(reads), C.byref(outside))
        assert not outside.value, "decoder fetched beyond the immutable source"
        return ok, decoded, reads.value

    decode.lib = lib
    return decode


def _operand(decode, value):
    return (value.role.decode(), decode.lib.agi_operand_kind_name(value.kind).decode(),
            value.width, decode.lib.agi_operand_access_name(value.access).decode(), value.value)


def _action(opcode):
    return bytes([opcode, *range(1, ACTION_WIDTHS[opcode] + 1)])


def test_all_fixed_actions_have_semantic_operands_and_unchanged_execution_admission(native_decoder):
    assert len(ACTION_NAMES) == len(ACTION_WIDTHS) == 174
    for profile, native in enumerate((SCALAR_NATIVE, BINDING_NATIVE, INTENT_NATIVE)):
        for opcode, name in enumerate(ACTION_NAMES):
            raw = _action(opcode)
            ok, row, reads = native_decoder(raw, profile=profile)
            assert row.mnemonic.decode() == name
            assert row.operation and row.operation != b"unmodeled", (opcode, name)
            assert row.effect_class != 6, (opcode, name)
            expected = (1 if opcode == 35 else 0) if opcode in native else 2
            assert row.execution_support == expected, (profile, opcode)
            if opcode == 149:
                assert not ok and row.fault == 14 and row.size == 0 and reads == 1
                assert row.successor_count == 0
                continue
            assert ok and row.fault == 0 and row.size == len(raw), (opcode, name)
            assert bytes(row.bytes[:row.size]) == raw and reads == len(raw)
            assert row.operand_count == ACTION_WIDTHS[opcode]
            for index, operand in enumerate(row.operands[:row.operand_count]):
                assert operand.role and not operand.role.startswith(b"arg"), (opcode, index)
                assert operand.value == raw[index + 1]
                assert operand.width in (1, 8)
            executable, legacy, legacy_reads = native_decoder(raw, profile=profile, execution=True)
            # Historically known commands can decode in a disabled profile;
            # execution_support still tells the translator to refuse them.
            assert executable == (opcode in INTENT_NATIVE), (profile, opcode)
            if opcode not in INTENT_NATIVE:
                assert legacy.fault == 1 and legacy.size == 0 and legacy_reads == 1
            else:
                assert legacy.execution_support == expected


def test_fixed_width_actions_reject_every_truncated_prefix_without_extra_reads(native_decoder):
    for opcode in range(174):
        if opcode == 149:
            continue
        raw = _action(opcode)
        for length in range(1, len(raw)):
            ok, row, reads = native_decoder(raw[:length])
            assert not ok and row.fault == 2 and row.size == 0, (opcode, length)
            assert row.successor_count == 0 and reads == 1
            if opcode not in INTENT_NATIVE:
                ok, row, reads = native_decoder(raw[:length], execution=True)
                assert not ok and row.fault == 1 and row.size == 0 and reads == 1


def test_string_controller_and_handler_specific_operand_facts(native_decoder):
    cases = {
        9: [("destination_pointer", "variable", 8, "read", 1),
            ("value", "variable", 8, "read", 2)],
        10: [("destination", "variable", 8, "write", 1),
             ("source_pointer", "variable", 8, "read", 2)],
        82: [("actor", "actor", 8, "reference", 1),
             ("x", "variable", 8, "read", 2), ("y", "variable", 8, "read", 3),
             ("step_size", "variable", 8, "read", 4), ("flag", "flag", 1, "write", 5)],
        95: [("inventory_object", "inventory_object", 8, "reference", 1),
             ("room", "variable", 8, "read", 2)],
        97: [("inventory_object", "variable", 8, "read", 1),
             ("destination", "variable", 8, "write", 2)],
        114: [("destination", "string", 8, "write", 1),
              ("message", "message", 8, "reference", 2)],
        115: [("destination", "string", 8, "write", 1),
              ("message", "message", 8, "reference", 2),
              ("row", "u8", 8, "read", 3), ("column", "u8", 8, "read", 4),
              ("maximum_length", "u8", 8, "read", 5)],
        116: [("destination", "string", 8, "write", 1),
              ("parsed_word_index", "u8", 8, "read", 2)],
        117: [("string", "string", 8, "read", 1)],
        118: [("message", "message", 8, "reference", 1),
              ("destination", "variable", 8, "write", 2)],
        121: [("ascii", "u8", 8, "read", 1), ("scan_code", "u8", 8, "read", 2),
              ("controller", "controller", 8, "write", 3)],
        130: [("minimum", "u8", 8, "read", 1), ("maximum", "u8", 8, "read", 2),
              ("destination", "variable", 8, "write", 3)],
        152: [("message", "variable", 8, "read", 1), ("row", "u8", 8, "read", 2),
              ("column", "u8", 8, "read", 3), ("width", "u8", 8, "read", 4)],
        157: [("message", "message", 8, "reference", 1),
              ("controller", "controller", 8, "reference", 2)],
        170: [("description", "string", 8, "read", 1)],
    }
    for opcode, expected in cases.items():
        ok, row, _ = native_decoder(_action(opcode))
        assert ok
        assert [_operand(native_decoder, item) for item in row.operands[:row.operand_count]] == expected, opcode
    for opcode in range(165, 169):
        ok, row, _ = native_decoder(_action(opcode))
        assert ok and row.effect_class == 0 and row.execution_support == 2
        assert _operand(native_decoder, row.operands[0]) == ("destination", "variable", 8, "read_write", 1)
        assert _operand(native_decoder, row.operands[1]) == ("value", "variable" if opcode % 2 == 0 else "u8", 8, "read", 2)


def test_all_predicates_keep_typed_order_and_legacy_evaluation_boundary(native_decoder):
    for opcode, name in enumerate(PREDICATE_NAMES):
        payload = (bytes([3, 1, 0, 255, 255, 0, 1]) if opcode == 14
                   else bytes(range(1, PREDICATE_WIDTHS[opcode] + 1)))
        raw = bytes([255, opcode]) + payload + bytes([255, 0, 0])
        ok, row, reads = native_decoder(raw)
        assert ok and row.size == len(raw) and reads == len(raw), opcode
        assert row.condition_count == 1
        token = row.conditions[0]
        assert token.kind == 0 and token.pc == 1 and token.opcode == opcode
        assert token.mnemonic.decode() == name
        expected_support = 0 if 1 <= opcode <= 7 else 2
        assert row.execution_support == expected_support
        operands = [_operand(native_decoder, item) for item in row.condition_operands[:row.condition_operand_count]]
        assert all(not item[0].startswith("arg") for item in operands)
        if opcode == 14:
            assert operands == [("word_count", "u8", 8, "read", 3),
                                ("word", "word", 16, "reference", 1),
                                ("word", "word", 16, "reference", 65535),
                                ("word", "word", 16, "reference", 256)]
        elif opcode == 15:
            assert operands == [("left_string", "string", 8, "read", 1),
                                ("right_string", "string", 8, "read", 2)]
        elif opcode == 12:
            assert operands == [("controller", "controller", 8, "read", 1)]
        executable, legacy, _ = native_decoder(raw, execution=True)
        assert executable == (1 <= opcode <= 7)
        if not executable:
            assert legacy.fault == 5 and legacy.size == 0


def test_control_transfer_and_context_boundaries(native_decoder):
    for opcode in (0, 18, 19):
        ok, row, _ = native_decoder(_action(opcode))
        assert ok and row.successor_count == 0
    for opcode in (22, 23):
        ok, row, _ = native_decoder(_action(opcode) + bytes([0]))
        assert ok and row.successor_count == 1
        assert native_decoder.lib.agi_successor_kind_name(row.successors[0].kind) == b"assumed_return"
    for extra in (b"", b"\0", b"\xff\xff\xff"):
        ok, row, reads = native_decoder(bytes([149]) + extra)
        assert not ok and row.fault == 14 and row.size == 0
        assert row.mnemonic == b"trace.on" and row.operation == b"debug.trace_on"
        assert row.successor_count == 0 and reads == 1
        ok, row, reads = native_decoder(bytes([149]) + extra, execution=True)
        assert not ok and row.fault == 1 and row.size == 0 and reads == 1
    for opcode in range(174, 254):
        ok, row, reads = native_decoder(bytes([opcode, 0, 0]))
        assert not ok and row.fault == 1 and row.size == 0 and reads == 1
    for raw, expected in ((bytes([254, 0, 128]), -32765),
                          (bytes([254, 255, 127]), 32770)):
        ok, row, _ = native_decoder(raw)
        assert ok and row.successors[0].pc == expected
        assert not row.successors[0].in_range
    ok, row, _ = native_decoder(bytes([255, 255, 255, 255]))
    assert ok and row.successors[1].pc == 65539


def test_framing_limits_and_fetch_bounds_remain_explicit(native_decoder):
    for raw in (b"", bytes(65537)):
        ok, row, reads = native_decoder(raw)
        assert not ok and row.fault == 6 and row.size == 0 and reads == 0
    ok, row, reads = native_decoder(b"\0", pc=1)
    assert not ok and row.fault == 6 and reads == 0
    for raw, fault in ((bytes([255, 19, 255, 0, 0]), 5),
                       (bytes([255, 252, 252, 255, 0, 0]), 5),
                       (bytes([255, 253, 253, 7, 0, 255, 0, 0]), 5),
                       (bytes([255, 14, 3, 1, 0]), 2),
                       (bytes([255, *([7, 0] * 65), 255, 0, 0]), 7)):
        ok, row, _ = native_decoder(raw)
        assert not ok and row.fault == fault and row.size == 0
        assert row.successor_count == 0
    # The count byte and 255 little-endian dictionary IDs fit the stopped
    # structural bound; this does not admit said to the legacy evaluator.
    raw = bytes([255, 14, 255]) + b"\xff\xff" * 255 + bytes([255, 0, 0])
    ok, row, reads = native_decoder(raw)
    assert ok and row.size == 516 and reads == 516
    assert row.condition_operand_count == 256 and row.execution_support == 2


def test_explicit_runtime_profile_reuses_full_framing_without_promoting_pilot_support(native_decoder):
    pending = {29, 101, 102, 110, 115, 118, 124, 125, 126, 127, 128, 129,
               133, 134, 135, 136, 139, 141, 144, 151, 152, 161, 162}
    for execution in (False, True):
        for opcode in range(174):
            raw = _action(opcode)
            ok, row, reads = native_decoder(raw, profile=3, execution=execution)
            assert ok and row.fault == 0 and row.size == len(raw), opcode
            assert row.mnemonic.decode() == ACTION_NAMES[opcode]
            assert row.execution_support == (1 if opcode in pending else 0)
            assert reads == len(raw) and bytes(row.bytes[:row.size]) == raw
        for opcode, width in enumerate(PREDICATE_WIDTHS):
            payload = b"\x02\x01\x00\xff\xff" if opcode == 14 else bytes(width)
            raw = bytes([255, opcode]) + payload + bytes([255, 0, 0])
            ok, row, reads = native_decoder(raw, profile=3, execution=execution)
            assert ok and row.size == len(raw) and reads == len(raw)
        raw = bytes([255, *([7, 0] * 64), 255, 0, 0])
        ok, row, reads = native_decoder(raw, profile=3, execution=execution)
        assert ok and row.condition_count == 64 and reads == len(raw)
        assert row.execution_support == 0
        ok, row, reads = native_decoder(bytes([149, 17, 42]), profile=3, execution=execution)
        assert ok and row.size == 1 and reads == 1 and row.mnemonic == b"trace.on"
    # Pilot EXECUTION still rejects a structurally valid ninth predicate.
    raw = bytes([255, *([7, 0] * 9), 255, 0, 0])
    for profile in (0, 1, 2):
        ok, row, _ = native_decoder(raw, profile=profile, execution=True)
        assert not ok and row.fault == 7 and row.size == 0
