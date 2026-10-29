"""Independent consumer acceptance with authored UIL, no story or compiler."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys

import pytest

PLAYER = Path(__file__).resolve().parents[1] / "player"
sys.path.insert(0, str(PLAYER))
from fdisbull_player.word16 import FORMAT, Word16Error, Word16Runtime, load_program, main, validate_program


def authored(blocks=None, *, entry=1600, edits=()):
    memory = bytearray(2048)
    memory[0] = 3
    memory[1300] = 40
    memory[1350] = 8
    memory[1400:1404] = bytes((0, 4, 0, 0))
    for address, data in edits:
        memory[address:address + len(data)] = data
    blocks = blocks or {1600: [{"op": "quit"}]}
    return {
        "format": FORMAT, "role": "uil",
        "source": {"sha256": "a" * 64, "version": 3, "release": 1, "serial": "000001"},
        "entry": entry, "memory": {"initial": memory.hex(), "writable_end": 1536},
        "layout": {"globals": 64, "objects": 600, "dictionary": 1400,
                   "abbreviations": 1080, "declared_bytes": len(memory)},
        "blocks": {str(pc): {"guard": memory[pc:pc + 1].hex(), "nodes": nodes, "next": pc + 1}
                   for pc, nodes in blocks.items()}, "functions": {},
    }


def input_node(resume):
    return {"op": "input", "text": 1300, "parse": 1350, "resume": resume}


def test_complete_schema_checks_unselected_branch_and_rejects_vm_escape():
    program = authored({1600: [{"op": "if", "condition": False, "then": [{"op": "execute_story", "path": "game.dat"}]}]})
    with pytest.raises(Word16Error, match="Unsupported node"):
        validate_program(program)
    program = authored()
    program["format"] = "fdisbull-il-1"
    with pytest.raises(Word16Error, match="Unsupported UIL"):
        validate_program(program)


def test_gzip_loader_rejects_duplicate_keys_and_invalid_guards(tmp_path):
    path = tmp_path / "invalid.json.gz"
    path.write_bytes(gzip.compress(b'{"format":"x","format":"y"}'))
    with pytest.raises(Word16Error, match="Duplicate"):
        load_program(path)
    program = authored()
    program["blocks"]["1600"]["guard"] = "01"
    with pytest.raises(Word16Error, match="guard"):
        validate_program(program)


def test_static_write_is_refused_without_hidden_retry():
    runtime = Word16Runtime(authored({1600: [
        {"op": "write_mem", "address": 1000, "width": 8, "value": 42},
        {"op": "write_mem", "address": 1535, "width": 16, "value": 123},
    ]}))
    original = runtime.snapshot()
    with pytest.raises(Word16Error, match="outside dynamic"):
        runtime.run()
    assert runtime.memory[1000] == 42  # The authoritative prefix is retained.
    assert runtime.memory[1535:1537] == b"\0\0"
    with pytest.raises(Word16Error, match="faulted"):
        runtime.run()
    runtime.restore(original)
    assert runtime.memory[1000] == 0
    assert runtime.fault is None


def test_arithmetic_resource_bound_and_header_transcript_alias():
    overflowing = Word16Runtime(authored({1600: [
        {"op": "let", "name": "huge", "value": {"calc": "mul", "args": [2**63, 2**63]}},
        {"op": "quit"},
    ]}))
    with pytest.raises(Word16Error, match="arithmetic intermediate"):
        overflowing.run()
    runtime = Word16Runtime(authored({1600: [
        {"op": "write_mem", "address": 17, "width": 8, "value": 1},
        {"op": "emit", "value": "recorded"}, {"op": "quit"},
    ]}))
    result = runtime.run()
    assert result["events"] == [{"type": "text", "window": 0, "screen": True,
                                 "transcript": True, "text": "recorded"}]


def test_missing_control_target_has_no_bytecode_fallback():
    runtime = Word16Runtime(authored({1600: [{"op": "goto", "target": 1700}]}))
    with pytest.raises(Word16Error, match="Missing lowered control target"):
        runtime.run()


def test_dynamic_code_guard_does_not_prohibit_unexecuted_data_changes():
    runtime = Word16Runtime(authored({
        1600: [{"op": "write_mem", "address": 1290, "width": 8, "value": 99},
               {"op": "goto", "target": 1601}],
        1601: [{"op": "quit"}],
        1290: [{"op": "quit"}],
    }))
    assert runtime.run()["status"] == "halted"
    assert runtime.memory[1290] == 99
    runtime = Word16Runtime(authored({
        1600: [{"op": "write_mem", "address": 1290, "width": 8, "value": 99},
               {"op": "goto", "target": 1290}],
        1290: [{"op": "quit"}],
    }))
    with pytest.raises(Word16Error, match="self-modified code"):
        runtime.run()


def test_budget_stop_preserves_exact_block_continuation():
    program = authored({
        1600: [{"op": "write_mem", "address": 1000, "width": 8, "value": 7}],
        1601: [{"op": "emit", "value": "finished"}, {"op": "quit"}],
    })
    runtime = Word16Runtime(program)
    first = runtime.run(max_steps=1)
    assert (first["status"], first["pc"], runtime.memory[1000]) == ("budget_exhausted", 1601, 7)
    checkpoint = runtime.snapshot()
    fresh = Word16Runtime(program)
    fresh.restore(checkpoint)
    assert fresh.run() == runtime.run()


@pytest.mark.parametrize("change", [
    lambda s: s.update(package_sha256="b" * 64),
    lambda s: s.update(memory=s["memory"][:3200] + "ff" + s["memory"][3202:]),
    lambda s: s["frames"][0].update(base=1),
    lambda s: s["rng"].update(interval=2, counter=2),
    lambda s: s["pending_input"].update(resume=1600),
    lambda s: s["host"]["memory_streams"].append({"table": 1535, "count": 9}),
    lambda s: s.update(tape_index=1),
])
def test_restore_is_transactional_for_invalid_state(change):
    runtime = Word16Runtime(authored({1600: [input_node(1601)], 1601: [{"op": "quit"}]}))
    assert runtime.run()["status"] == "input"
    before = runtime.snapshot()
    bad = copy.deepcopy(before)
    change(bad)
    with pytest.raises(Word16Error):
        runtime.restore(bad)
    assert runtime.snapshot() == before


def test_nested_native_save_slots_cannot_form_recursive_checkpoints():
    runtime = Word16Runtime(authored())
    before = runtime.snapshot()
    bad = copy.deepcopy(before)
    bad["game_slot"] = copy.deepcopy(before)
    bad["game_slot"]["game_slot"] = copy.deepcopy(before)
    with pytest.raises(Word16Error, match="Nested"):
        runtime.restore(bad)
    assert runtime.snapshot() == before


def test_seed_policy_and_tape_preserve_state_and_range_contract():
    nodes = []
    for number in (-3, 10, 10, 10, 10, 0, 100):
        nodes.append({"op": "random", "range": number, "dest": "r"})
    nodes.append({"op": "quit"})
    runtime = Word16Runtime(authored({1600: nodes}), seed=12)
    runtime.run()
    # Small in-story seeds use a rising cycle. Startup/reset seed12 uses the LCG.
    assert [row["value"] for row in runtime.random_log[:5]] == [0, 1, 2, 3, 1]
    accumulator = (12 * 0x015A4E35 + 1) & 0xffffffff
    assert runtime.random_log[-1] == {"range": 100, "value": ((accumulator >> 16) & 32767) % 100 + 1}
    program = authored({1600: [{"op": "random", "range": 10, "dest": "r"}, {"op": "quit"}]})
    taped = Word16Runtime(program, random_tape=[{"range": 10, "value": 7}])
    taped.run()
    assert taped.random_log == [{"range": 10, "value": 7}]
    assert taped.tape_index == 1
    with pytest.raises(Word16Error, match="range mismatch"):
        Word16Runtime(program, random_tape=[{"range": 11, "value": 7}]).run()
    with pytest.raises(Word16Error, match="exhausted"):
        Word16Runtime(program, random_tape=[]).run()


def test_nested_memory_streams_are_authoritative_data_effects():
    program = authored({1600: [
        {"op": "host", "action": "output_stream", "args": [3, 1000]},
        {"op": "emit", "value": "A"},
        {"op": "host", "action": "output_stream", "args": [3, 1100]},
        {"op": "emit", "value": "B\n"},
        {"op": "host", "action": "output_stream", "args": [-3]},
        {"op": "emit", "value": "C"},
        {"op": "host", "action": "output_stream", "args": [-3]},
        {"op": "emit", "value": "visible"}, {"op": "quit"},
    ]})
    runtime = Word16Runtime(program)
    result = runtime.run()
    assert result["text"] == "visible"
    assert runtime.memory[1000:1004] == b"\0\x02AC"
    assert runtime.memory[1100:1104] == b"\0\x02B\r"


def test_indentation_controls_retain_memory_bytes_and_render_as_spaces():
    runtime = Word16Runtime(authored({1600: [
        {"op": "library", "name": "text.character", "args": [9], "dest": "indent"},
        {"op": "library", "name": "text.character", "args": [11], "dest": "gap"},
        {"op": "host", "action": "output_stream", "args": [3, 1000]},
        {"op": "emit", "value": {"tmp": "indent"}},
        {"op": "emit", "value": {"tmp": "gap"}},
        {"op": "host", "action": "output_stream", "args": [-3]},
        {"op": "emit", "value": {"tmp": "indent"}},
        {"op": "emit", "value": {"tmp": "gap"}}, {"op": "quit"},
    ]}))
    assert runtime.run()["text"] == "     "
    assert runtime.memory[1000:1004] == b"\0\x02\x09\x0b"


def test_input_limits_and_token_positions_are_not_a_command_parser():
    program = authored({1600: [input_node(1601)], 1601: [{"op": "quit"}]}, edits=[
        (1300, b"\x09"), (1400, bytes((1, ord(","), 4, 0, 0))),
    ])
    runtime = Word16Runtime(program)
    runtime.run()
    runtime.command("  ABC,D EFG")
    assert runtime.memory[1301:1310] == b"  abc,d \0"
    assert runtime.memory[1351] == 3
    assert runtime.memory[1352:1364] == bytes((0, 0, 3, 3, 0, 0, 1, 6, 0, 0, 1, 7))


def test_real_input_checkpoint_continues_in_an_isolated_fresh_process(tmp_path):
    program = authored({1600: [input_node(1601)], 1601: [
        {"op": "write_var", "index": 17, "value": 123},
        {"op": "emit", "value": "saved continuation"}, {"op": "quit"},
    ]})
    package = tmp_path / "authored.uil.json"
    package.write_text(json.dumps(program))
    state = tmp_path / "state.json"
    runtime = Word16Runtime(program)
    runtime.run()
    runtime.save_checkpoint(state)
    expected = runtime.command("unrecognized command")
    script = """
import importlib.abc,json,sys
sys.path.insert(0, sys.argv[1])
class RefuseOriginal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('fdisbull','jericho','frotz'):
            raise RuntimeError('original/compiler dependency attempted')
sys.meta_path.insert(0, RefuseOriginal())
from fdisbull_player.word16 import Word16Runtime,load_program
r=Word16Runtime(load_program(sys.argv[2]))
r.load_checkpoint(sys.argv[3])
print(json.dumps(r.command('unrecognized command')))
"""
    result = subprocess.run([sys.executable, "-I", "-c", script, str(PLAYER), str(package), str(state)],
                            cwd=tmp_path, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == expected


def test_in_game_save_restores_success_continuation_and_preserves_flags2():
    program = authored({
        1600: [{"op": "persist", "mode": "save", "success": [{"op": "goto", "target": 1601}],
                "failure": [{"op": "goto", "target": 1604}], "resume": 1601}],
        1601: [input_node(1602)],
        1602: [{"op": "write_mem", "address": 1000, "width": 8, "value": 99},
               {"op": "write_mem", "address": 16, "width": 16, "value": 3},
               {"op": "persist", "mode": "restore", "success": [],
                "failure": [{"op": "goto", "target": 1604}], "resume": 1603}],
        1603: [{"op": "quit"}], 1604: [{"op": "emit", "value": "failed"}, {"op": "quit"}],
    })
    runtime = Word16Runtime(program)
    assert runtime.run()["status"] == "input"
    result = runtime.command("restore")
    assert result["status"] == "input"
    assert runtime.memory[1000] == 0
    assert runtime.memory[16:18] == b"\0\x03"
    assert {"type": "restore", "success": True} in result["events"]
    resumed = Word16Runtime(program)
    resumed.restore(runtime.snapshot())
    assert resumed.command("restore") == runtime.command("restore")


def test_failed_in_game_restore_executes_failure_branch():
    runtime = Word16Runtime(authored({
        1600: [{"op": "persist", "mode": "restore", "success": [{"op": "goto", "target": 1601}],
                "failure": [{"op": "goto", "target": 1602}], "resume": 1601}],
        1601: [{"op": "emit", "value": "wrong"}, {"op": "quit"}],
        1602: [{"op": "emit", "value": "no save"}, {"op": "quit"}],
    }))
    assert runtime.run()["text"] == "no save"


@pytest.mark.parametrize("output_flag", ["--checkpoint", "--transcript"])
@pytest.mark.parametrize("input_kind", ["package", "commands"])
@pytest.mark.parametrize("alias_kind", ["direct", "symlink", "hardlink"])
def test_cli_refuses_outputs_aliasing_inputs_without_changing_files(
    tmp_path, capsys, output_flag, input_kind, alias_kind,
):
    package = tmp_path / "program.json"
    package.write_text(json.dumps(authored()))
    commands = tmp_path / "commands.json"
    commands.write_text("[]")
    source = package if input_kind == "package" else commands
    output = source
    if alias_kind != "direct":
        output = tmp_path / "alias.json"
        if alias_kind == "symlink":
            output.symlink_to(source)
        else:
            output.hardlink_to(source)
    expected = {path: path.read_bytes() for path in (package, commands, output)}
    with pytest.raises(SystemExit) as stopped:
        main([str(package), "--commands", str(commands), output_flag, str(output)])
    assert stopped.value.code == 2
    assert f"would replace the {input_kind} input" in capsys.readouterr().err
    assert {path: path.read_bytes() for path in expected} == expected


def test_cli_refuses_colliding_outputs_and_transcript_over_resume(tmp_path, capsys):
    package = tmp_path / "program.json"
    package.write_text(json.dumps(authored()))
    commands = tmp_path / "commands.json"
    commands.write_text("[]")
    preserved = tmp_path / "preserved.json"
    preserved.write_text("keep this existing file")
    for options, message in (
        (["--checkpoint", str(preserved), "--transcript", str(preserved)], "must be distinct"),
        (["--resume", str(preserved), "--transcript", str(preserved)], "replace the resume input"),
    ):
        with pytest.raises(SystemExit) as stopped:
            main([str(package), "--commands", str(commands), *options])
        assert stopped.value.code == 2
        assert message in capsys.readouterr().err
        assert preserved.read_text() == "keep this existing file"


@pytest.mark.parametrize("invalid_commands", ["not a list", ["look", 42], ["look", "two\nlines"]])
def test_cli_validates_entire_command_batch_before_initial_output_write(tmp_path, capsys, invalid_commands):
    package = tmp_path / "program.json"
    package.write_text(json.dumps(authored({1600: [input_node(1601)], 1601: [{"op": "quit"}]})))
    commands = tmp_path / "commands.json"
    commands.write_text(json.dumps(invalid_commands))
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("existing checkpoint")
    transcript = tmp_path / "transcript.json"
    transcript.write_text("existing transcript")
    with pytest.raises(SystemExit) as stopped:
        main([str(package), "--commands", str(commands), "--checkpoint", str(checkpoint),
              "--transcript", str(transcript)])
    assert stopped.value.code == 2
    capsys.readouterr()
    assert checkpoint.read_text() == "existing checkpoint"
    assert transcript.read_text() == "existing transcript"


def test_cli_can_resume_and_refresh_same_checkpoint(tmp_path, capsys):
    program = authored({1600: [input_node(1601)],
                        1601: [{"op": "emit", "value": "resumed"}, {"op": "quit"}]})
    package = tmp_path / "program.json"
    package.write_text(json.dumps(program))
    commands = tmp_path / "commands.json"
    commands.write_text('["look"]')
    state = tmp_path / "checkpoint.json"
    runtime = Word16Runtime(program)
    assert runtime.run()["status"] == "input"
    runtime.save_checkpoint(state)
    assert main([str(package), "--commands", str(commands), "--resume", str(state),
                 "--checkpoint", str(state)]) == 0
    assert capsys.readouterr().out == "resumed"
    runtime.load_checkpoint(state)
    assert runtime.halted is True
