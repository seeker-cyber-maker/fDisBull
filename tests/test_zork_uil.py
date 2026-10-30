"""Independent bytecode-to-UIL semantics using only authored v3 fixtures.

These programs are deliberately tiny: expected results follow arithmetic and
the public v3 variable/call contract, not the compiler's emitted node structure.
No original game bytes or strings are included.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest

from fdisbull.zmachine import decode_v3
from fdisbull.zork_uil import compile_story, lower_instruction, write_document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))


def story_image(code, *, entry=0x400, size=0x800, patches=()):
    """One empty object, empty dictionary, valid header and real checksum."""
    raw = bytearray(size)
    raw[0] = 3

    def word(at, value):
        raw[at:at + 2] = value.to_bytes(2, "big")

    for at, value in ((2, 1), (4, 0x400), (6, entry), (8, 900),
                      (10, 544), (12, 64), (14, 0x400),
                      (24, 640), (26, size // 2)):
        word(at, value)
    raw[18:24] = b"000001"
    word(613, 615)  # Object 1's empty short-name and property table.
    raw[900:904] = bytes([0, 4, 0, 0])
    raw[entry:entry + len(code)] = bytes(code)
    for at, data in patches:
        raw[at:at + len(data)] = data
    word(28, sum(raw[64:]) & 0xFFFF)
    return raw


def compile_fixture(tmp_path, code, **options):
    path = tmp_path / "authored-story.z3"
    path.write_bytes(story_image(code, **options))
    return compile_story(path)


def runtime(program):
    from fdisbull_player.word16 import Word16Runtime
    return Word16Runtime(program, seed=12)


def global_word(machine, number):
    at = 64 + (number - 16) * 2
    return int.from_bytes(machine.memory[at:at + 2], "big")


def run_to_halt(program):
    machine = runtime(program)
    result = machine.run(max_steps=1000)
    assert result["status"] == "halted", result
    return machine


def test_stack_operands_are_consumed_left_to_right(tmp_path):
    # push100; push13; push3; sub sp sp ->g19; load sp ->g20;
    # pull g21; quit. The subtraction is 3-13, not 13-3.
    code = bytes.fromhex("e87f64 e87f0d e87f03 75000013 9e0014 e97f15 ba")
    program, _ = compile_fixture(tmp_path, code)
    machine = run_to_halt(program)
    assert [global_word(machine, n) for n in (19, 20, 21)] == [65526, 100, 100]


def test_indirect_stack_inc_store_load_and_pull_do_not_push(tmp_path):
    # inc and store replace the existing top. load observes it. pull sp pops
    # the top and replaces the newly exposed top, reducing stack depth by one.
    code = bytes.fromhex("e87f0a e87f14 9500 9e0013 0d0007 9e0014 e97f00 9e0015 e97f16 b9 ba")
    program, _ = compile_fixture(tmp_path, code)
    machine = runtime(program)
    with pytest.raises((ValueError, RuntimeError), match="(?i)stack|underflow"):
        machine.run(max_steps=1000)  # Last pop must underflow after the final pull.
    assert [global_word(machine, n) for n in (19, 20, 21, 22)] == [21, 7, 7, 7]


def test_variable_operand_resolves_an_indirect_stack_reference(tmp_path):
    # A variable-typed operand 0 is first popped to obtain an indirect index;
    # inc [sp] therefore pops index0 and increments the remaining value10.
    code = bytes.fromhex("e87f0a e87f00 a500 9e0013 e97f14 ba")
    program, _ = compile_fixture(tmp_path, code)
    machine = run_to_halt(program)
    assert (global_word(machine, 19), global_word(machine, 20)) == (11, 11)


@pytest.mark.parametrize("instruction,expected", [
    ("d70ffff9000313", 65534),  # -7 / 3 = -2, truncating toward zero.
    ("d80ffff9000313", 65535),  # -7 % 3 = -1, sign of dividend.
    ("d70f0007fffd13", 65534),  # 7 / -3 = -2.
    ("d80f0007fffd13", 1),      # 7 % -3 = 1.
    ("d40fffff000213", 1),      # 65535 + 2 wraps to1.
    ("d50f0000000113", 65535),  # 0 - 1 wraps to65535.
    ("d60f8000000213", 0),      # 32768 * 2 wraps to0.
])
def test_signed_arithmetic_and_word_wrapping(tmp_path, instruction, expected):
    program, _ = compile_fixture(tmp_path, bytes.fromhex(instruction + "ba"))
    machine = run_to_halt(program)
    assert global_word(machine, 19) == expected


@pytest.mark.parametrize("value,branch,expected", [
    (0, 0xC0, 0), (0, 0xC1, 1),
    (1, 0x40, 0), (1, 0x41, 1),
    (1, 0xC1, 99), (0, 0x41, 99),
])
def test_branch_zero_one_return_and_polarity(tmp_path, value, branch, expected):
    caller = bytes.fromhex("e03f028013 ba")
    # Routine: no locals; jz value ?branch; otherwise ret99.
    callee = bytes([0, 0x90, value, branch, 0x9B, 99])
    program, _ = compile_fixture(tmp_path, caller, patches=[(0x500, callee)])
    machine = run_to_halt(program)
    assert global_word(machine, 19) == expected


def test_calls_override_defaults_and_discard_only_callee_stack(tmp_path):
    # The first call supplies local1=9 and retains default local2=4. The second
    # supplies no arguments and gets defaults3,4. A callee temporary255 must not
    # leak into the caller, whose earlier77 must survive both call and return.
    caller = bytes.fromhex("e87f4d e01f02800913 e97f14 e03f028015 ba")
    callee = bytes.fromhex("02 0003 0004 e87fff 74010200 b8")
    program, _ = compile_fixture(tmp_path, caller, patches=[(0x500, callee)])
    machine = run_to_halt(program)
    assert [global_word(machine, n) for n in (19, 20, 21)] == [13, 77, 7]


def test_callee_cannot_pop_the_callers_stack(tmp_path):
    caller = bytes.fromhex("e87f4d e03f028013 ba")
    program, _ = compile_fixture(tmp_path, caller, patches=[(0x500, bytes.fromhex("00 b9 b1"))])
    machine = runtime(program)
    with pytest.raises((ValueError, RuntimeError), match="(?i)stack|underflow"):
        machine.run(max_steps=1000)


def test_zero_routine_call_returns_zero_without_creating_a_frame(tmp_path):
    program, _ = compile_fixture(tmp_path, bytes.fromhex("e87f4d e07f0013 e97f14 ba"))
    machine = run_to_halt(program)
    assert (global_word(machine, 19), global_word(machine, 20)) == (0, 77)


def test_memory_effective_addresses_wrap_at_word_width(tmp_path):
    # storeb65535+901 ->900; storew65535+2*451 ->901.
    code = bytes.fromhex("e207ffff0385ab e103ffff01c3beef d00fffff038513 cf0fffff01c314 ba")
    program, _ = compile_fixture(tmp_path, code)
    machine = run_to_halt(program)
    assert bytes(machine.memory[900:903]) == bytes.fromhex("abbeef")
    assert (global_word(machine, 19), global_word(machine, 20)) == (0xAB, 0xBEEF)


def test_jump_program_counter_is_not_wrapped_to_sixteen_bits(tmp_path):
    # At0xfff0, jump+31 uses end-2 +31 =0x10010.
    program, _ = compile_fixture(tmp_path, bytes.fromhex("8c001f"), entry=0xFFF0,
                                 size=0x10200, patches=[(0x10010, bytes.fromhex("14550513ba"))])
    machine = run_to_halt(program)
    assert global_word(machine, 19) == 90
    assert 0x10010 in machine.executed_blocks


@pytest.mark.parametrize("target,expected", [(0x500, 7), (0x600, 99)])
def test_unobserved_indirect_call_targets_are_retained(tmp_path, target, expected):
    # The target exists only as initial global data, not as an immediate call.
    # Both routine candidates must be retained independent of which is selected.
    program, mapping = compile_fixture(tmp_path, bytes.fromhex("e0bf1314ba"), patches=[
        (70, (target // 2).to_bytes(2, "big")),
        (0x500, bytes.fromhex("009b07")), (0x600, bytes.fromhex("009b63")),
    ])
    assert {"1280", "1536"} <= program["functions"].keys()
    assert "1537" in mapping["instruction_candidates"]
    assert program["qualification"]["candidate_starts_are_reachable_code"] is False
    assert global_word(run_to_halt(program), 20) == expected


def test_changed_instruction_bytes_refuse_execution(tmp_path):
    program, _ = compile_fixture(tmp_path, bytes.fromhex("14020313ba"))
    machine = runtime(program)
    machine.memory[program["entry"]] ^= 1
    with pytest.raises((ValueError, RuntimeError), match="(?i)guard|source|modif|identity"):
        machine.run(max_steps=1000)


def test_invalid_source_checksum_and_unsupported_entry_are_rejected(tmp_path):
    source = tmp_path / "invalid.z3"
    raw = story_image(bytes.fromhex("ba"))
    raw[1000] ^= 1
    source.write_bytes(raw)
    with pytest.raises(ValueError, match="checksum"):
        compile_story(source)
    source.write_bytes(story_image(bytes.fromhex("be")))
    with pytest.raises(ValueError, match="Initial PC"):
        compile_story(source)


def test_illegal_decoded_operand_count_is_not_a_semantic_candidate():
    # Variable-form je with just one operand is syntactically decodable but has
    # no legal v3 semantics and must not become a runtime no-op.
    instruction = decode_v3(bytes.fromhex("c17f01c1"), 0)
    with pytest.raises(ValueError, match="operand count"):
        lower_instruction(instruction)


def test_export_refuses_overwrite_and_git_containment(tmp_path):
    existing = tmp_path / "keep.json"
    existing.write_text("unchanged")
    with pytest.raises(FileExistsError):
        write_document(existing, {"private": "derived"})
    assert existing.read_text() == "unchanged"
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git/HEAD").write_text("ref: refs/heads/main\n")
    target = checkout / "private/derived.json"
    with pytest.raises(ValueError, match="Git checkout"):
        write_document(target, {"private": "derived"})
    assert not target.exists()


def test_compiled_save_continuation_survives_source_free_process_restart(tmp_path):
    # Main calls a routine whose SAVE branches to return1. After the call it
    # draws a random number and waits for input. RESTORE must return to the saved
    # SAVE continuation and reproduce that draw, not take its own return0 branch.
    code = bytes.fromhex("e03f028013 e77f6414 e40f03b60000 b6c0 ba")
    program, _ = compile_fixture(tmp_path, code, patches=[
        (0x500, bytes.fromhex("00 b5c1 b1")), (950, bytes([32])),
    ])
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    consumer = Path(__file__).resolve().parents[1] / "player/fdisbull_player/word16.py"
    shutil.copy2(consumer, isolated / "consumer.py")
    (isolated / "program.json").write_text(json.dumps(program))
    child = r'''
import importlib.util,json,pathlib,sys
spec=importlib.util.spec_from_file_location('consumer',pathlib.Path('consumer.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
machine=module.Word16Runtime(module.load_program('program.json'),seed=12)
if sys.argv[1]=='save':
    result=machine.run()
    machine.save_checkpoint('checkpoint.json')
else:
    machine.load_checkpoint('checkpoint.json')
    result=machine.command('restore')
assert result['status']=='input'
assert machine.snapshot()['game_slot'] is not None
assert not any(name.startswith(('fdisbull','jericho')) for name in sys.modules)
print(json.dumps(machine.snapshot(),sort_keys=True))
'''
    def execute(mode):
        result = subprocess.run([sys.executable, "-I", "-c", child, mode],
                                cwd=isolated, text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    before = execute("save")
    after = execute("restore")
    assert before == after
    assert len(after["random_log"]) == 1
    assert int.from_bytes(bytes.fromhex(after["memory"])[70:72], "big") == 1
