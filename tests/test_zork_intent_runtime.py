"""Mixed intent/IR acceptance with authored, unlicensed source fixtures.

The fixture supplies an independent low-level chest/letter interaction and an
address-free semantic definition. It is not a Zork image or a claim of recovery
from machine code. The private integration checker separately uses the exact
owned story, unmodified Frotz and native memory captures.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "player"))
sys.path.insert(0, str(ROOT / "scripts"))

from fdisbull_player.intent_runtime import (
    FORMAT, UDL_FORMAT, IntentRuntime, load_package, validate_package,
)
from fdisbull_player.word16 import FORMAT as IR_FORMAT, MAX_TEXT, Word16Error, Word16Runtime
from verify_zork_intents import (
    EffectTrace, compared_result, differential, fresh_process_resume,
    positive_recovery, value_digest,
)


CHEST = 662
LETTER = 671
ROOM = 680
OPEN_ENTRY = 1621
UNRESOLVED_EFFECT = 1622
OPEN_TAIL = 1623
TURN_ENTRY = 1662
TURN_ADDRESS = 68


def _name_bytes(text):
    """Encode only the lower-case authored names used by this fixture."""
    codes = [0 if character == " " else ord(character) - ord("a") + 6
             for character in text]
    codes += [5] * (-len(codes) % 3)
    words = [(codes[index] << 10) | (codes[index + 1] << 5) | codes[index + 2]
             for index in range(0, len(codes), 3)]
    words[-1] |= 32768
    return bytes((len(words),)) + b"".join(word.to_bytes(2, "big") for word in words) + b"\0"


def _semantic_definition():
    def emit(resource):
        return {"intent": "narration.emit", "resource": resource}

    opening = [{"intent": "container.open", "entity": "target"},
               {"residual_ir": "post_open_source_flag"}]
    return {
        "format": "fdisbull-game-intent-uil-1", "id": "authored.chest-and-letter",
        "resources": {"repeat": "Already raised.", "empty": "The chest is empty.",
                      "prefix": "Inside ", "middle": " is ", "article": "a ",
                      "period": ".", "newline": "\n"},
        "interaction": {
            "id": "open_chest", "parameters": {"target": "entity"},
            "requires": [{"field": field, "eq": True} for field in (
                "target.is_container", "target.supports_opening",
                "target.opaque", "target.reachable")],
            "outcomes": [
                {"id": "already_open", "when": [{"field": "target.is_open", "eq": True}],
                 "steps": [emit("repeat"), emit("newline")]},
                {"id": "opened_empty", "when": [
                    {"field": "target.is_open", "eq": False},
                    {"field": "target.contents_count", "eq": 0}],
                 "steps": opening + [emit("empty"), emit("newline")]},
                {"id": "opened_contents", "when": [
                    {"field": "target.is_open", "eq": False},
                    {"field": "target.contents_count", "eq": 1},
                    {"field": "first_content.plain_listing", "eq": True}],
                 "steps": opening + [emit("prefix"),
                    {"intent": "narration.name", "entity": "target"},
                    emit("middle"), emit("article"),
                    {"intent": "narration.name", "entity": "first_content"},
                    {"intent": "discourse.remember_mentioned_object",
                     "entity": "first_content", "scene": "current_scene"},
                    emit("period"), emit("newline")]},
            ],
        },
        "turn": {"id": "count_player_action",
                 "requires": [{"field": "turn.count", "range": [0, 999]}],
                 "steps": [{"intent": "turn.count_player_action", "cycle": 1000}]},
    }


def authored_package(*, empty=False, count=0, game_save=False):
    """Author a tiny original IR program, then bind its independent UIL via UDL."""
    memory = bytearray(2048)
    memory[0] = 3
    memory[1300] = 40
    memory[1350] = 8
    memory[1400:1404] = bytes((0, 4, 0, 0))
    for number, value in {16: 3, 18: count, 20: 1, 21: 43, 22: 1, 23: 3}.items():
        address = 64 + 2 * (number - 16)
        memory[address:address + 2] = value.to_bytes(2, "big")
    names = {"oak-chest": (1, CHEST, "oak chest", 800),
             "sealed-letter": (2, LETTER, "letter", 850),
             "attic": (3, ROOM, "attic", 900)}
    for _, (number, record, name, table) in names.items():
        encoded = _name_bytes(name)
        memory[table:table + len(encoded)] = encoded
        memory[record + 7:record + 9] = table.to_bytes(2, "big")
    memory[CHEST] = 64 | 32 | 8  # authored container, opening, opaque flags
    memory[CHEST + 4] = 3
    memory[CHEST + 6] = 0 if empty else 2
    memory[LETTER + 4] = 0 if empty else 1
    memory[ROOM + 6] = 1

    def emit(text):
        return {"op": "emit", "value": text}

    def library(name, args, dest=None):
        return {"op": "library", "name": name, "args": args,
                **({"dest": dest} if dest else {})}

    def read(number, dest):
        return {"op": "read_var", "index": number, "dest": dest}

    def write(number, value):
        return {"op": "write_var", "index": number, "value": value}

    def calc(name, *args):
        return {"calc": name, "args": list(args)}

    input_node = {"op": "input", "text": 1300, "parse": 1350, "resume": 1601}
    source_blocks = {
        1600: [copy.deepcopy(input_node)],
        1601: [{"op": "call", "target": 1620, "args": [], "store": 19, "resume": 1602}],
        1602: [{"op": "call", "target": 1660, "args": [], "store": 24, "resume": 1603}],
        1603: [copy.deepcopy(input_node)],
        OPEN_ENTRY: [
            library("attribute.test", [1, 11], "opened"),
            {"op": "if", "condition": {"tmp": "opened"}, "then": [
                emit("Already raised."), emit("\n"), {"op": "return", "value": 1}]},
            library("attribute.set", [1, 11]),
        ],
        UNRESOLVED_EFFECT: [library("attribute.set", [1, 3])],
        OPEN_TAIL: [
            library("tree.child", [1], "child"),
            {"op": "if", "condition": calc("eq", {"tmp": "child"}, 0), "then": [
                emit("The chest is empty."), emit("\n"), {"op": "return", "value": 1}]},
            emit("Inside "), library("tree.name", [1], "target_name"),
            emit({"tmp": "target_name"}), emit(" is "), emit("a "),
            library("tree.name", [2], "content_name"), emit({"tmp": "content_name"}),
            write(22, 2), write(23, 3), emit("."), emit("\n"), {"op": "return", "value": 1},
        ],
        # An intentionally uninterpreted background operation. It must retain
        # its RNG effect, memory write and frame/control continuation exactly.
        1661: [{"op": "random", "range": 10, "dest": "draw"},
               {"op": "write_mem", "address": 1000, "width": 8, "value": {"tmp": "draw"}}],
        TURN_ENTRY: [
            read(18, "count"), write(18, calc("add", {"tmp": "count"}, 1)),
            read(18, "incremented"),
            {"op": "if", "condition": calc("gt", calc("s16", {"tmp": "incremented"}), 999),
             "then": [write(18, 0)]},
        ],
        1663: [{"op": "return", "value": 0}],
    }
    if game_save:
        source_blocks[1603] = [{"op": "persist", "mode": "save", "success": [],
                                "failure": [], "resume": 1604}]
        source_blocks[1604] = [copy.deepcopy(input_node)]
    # These are authored guard tokens, not borrowed story instructions.
    for address in (*source_blocks, 1620, 1660):
        memory[address] = address % 251 + 1
    functions = {
        "1620": {"guard": memory[1620:1621].hex(), "entry": OPEN_ENTRY, "locals": [0, 0]},
        "1660": {"guard": memory[1660:1661].hex(), "entry": 1661, "locals": [7, 7, 0, 0]},
    }
    source = {"kind": "authored-test-image", "sha256": hashlib.sha256(memory).hexdigest(),
              "version": 3, "release": 0, "serial": "TEST01"}
    ir = {"format": IR_FORMAT, "role": "uil", "source": source, "entry": 1600,
          "memory": {"initial": memory.hex(), "writable_end": 1536},
          "layout": {"globals": 64, "objects": 600, "dictionary": 1400,
                     "abbreviations": 1080, "declared_bytes": len(memory)},
          "blocks": {str(pc): {"guard": memory[pc:pc + 1].hex(), "nodes": nodes, "next": pc + 1}
                     for pc, nodes in source_blocks.items()}, "functions": functions}
    uil = _semantic_definition()

    def witness(start, end):
        data = bytes(memory[start:end])
        return {"start": start, "end": end, "bytes": data.hex(),
                "sha256": hashlib.sha256(data).hexdigest()}

    witnesses = {"action": witness(1620, 1624), "turn": witness(1660, 1664),
                 "dependency": witness(1100, 1101)}
    objects = {}
    for identity, (number, record, name, table) in names.items():
        name_witness = identity + "-name"
        witnesses[name_witness] = witness(table, table + len(_name_bytes(name)))
        objects[identity] = {"number": number, "record": record, "name": name,
                             "name_witness": name_witness}

    def attribute(number):
        return {"kind": "attribute", "object": "oak-chest", "number": number,
                "address": CHEST + number // 8, "mask": 128 >> (number % 8)}

    def global_field(number):
        return {"kind": "global", "number": number, "address": 64 + 2 * (number - 16), "width": 16}

    udl = {"format": UDL_FORMAT, "source": copy.deepcopy(source),
           "low_level_ir_sha256": value_digest(ir), "uil_sha256": value_digest(uil),
           "initial_image_sha256": hashlib.sha256(memory).hexdigest(),
           "witnesses": witnesses, "runtime_guards": list(witnesses), "objects": objects,
           "fields": {
               "target.is_container": attribute(1), "target.supports_opening": attribute(2),
               "target.is_open": attribute(11), "target.opaque": attribute(4),
               "first_content.description": {"kind": "property", "object": "sealed-letter", "number": 17},
               "discourse.object": global_field(22), "discourse.scene": global_field(23),
               "current_scene": global_field(16), "turn.count": global_field(18)},
           "opening": {"entry": OPEN_ENTRY, "function": 1620, "target": "oak-chest",
                       "content": "sealed-letter", "scene": "attic", "scene_object": 3,
                       "direct_object_global": 20, "action_global": 21, "action_value": 43,
                       "locals_initial": [0, 0], "return_pc": 1602, "return_store": 19,
                       "return_value": 1, "return_operations": [OPEN_ENTRY, OPEN_TAIL]},
           "turn": {"entry": TURN_ENTRY, "continue": 1663, "function": 1660,
                    "minimum": 0, "maximum": 999, "cycle": 1000,
                    "locals_count": 4, "return_pc": 1603, "return_store": 24,
                    "cursor_equal": [0, 1], "scheduler_call": 1602},
           "residuals": {"post_open_source_flag": {"kind": "single_block", "entry": UNRESOLVED_EFFECT}},
           }
    for field, operation in (("target.is_open", OPEN_ENTRY),
                             ("discourse.object", OPEN_TAIL),
                             ("discourse.scene", OPEN_TAIL),
                             ("turn.count", TURN_ENTRY)):
        udl["fields"][field]["source_operation"] = operation
    return {"format": FORMAT, "low_level_ir": ir, "uil": uil, "udl": udl}


class TracedIR(EffectTrace, Word16Runtime):
    pass


class TracedIntents(EffectTrace, IntentRuntime):
    pass


def paired(package, **kwargs):
    baseline = TracedIR(package["low_level_ir"], **kwargs)
    mixed = TracedIntents(package, **kwargs)
    assert compared_result(baseline.run()) == compared_result(mixed.run())
    assert baseline.snapshot() == mixed.low_level_snapshot()
    baseline.effects.clear()
    mixed.effects.clear()
    return baseline, mixed


def same_command(baseline, mixed, command="open chest"):
    old = baseline.command(command)
    new = mixed.command(command)
    assert compared_result(old) == compared_result(new)
    assert baseline.snapshot() == mixed.low_level_snapshot()
    assert baseline.effects == mixed.effects
    return old, new


def test_complete_interaction_replaces_body_and_preserves_all_effects_and_control():
    baseline, mixed = paired(authored_package(), random_tape=[{"range": 10, "value": 7}])
    mixed.forbidden_ir = {OPEN_ENTRY, OPEN_TAIL, TURN_ENTRY}
    old, new = same_command(baseline, mixed)
    assert new["text"] == "Inside oak chest is a letter.\n"
    assert new["moves"] == 1
    assert new["steps"] < old["steps"]
    assert mixed.memory[CHEST + 1] & 16
    assert mixed.memory[CHEST] & 16  # known only as the retained source flag
    assert mixed.memory[1000] == 7
    assert mixed.random_log == [{"range": 10, "value": 7}]
    assert int.from_bytes(mixed.memory[76:78], "big") == 2
    assert mixed.frames == [{"locals": [], "base": 0, "resume": None, "store": None}]
    assert mixed.pending_input == {"text": 1300, "parse": 1350, "resume": 1601}
    assert positive_recovery(mixed.recovery_stats)
    assert mixed.last_recovery["mode"] == "mixed_intent_and_ir"
    assert mixed.recovery_stats["residual_bindings"] == {"post_open_source_flag": 1}
    assert [row for row in mixed.ir_blocks if row["binding"]] == [
        {"pc": UNRESOLVED_EFFECT, "binding": "post_open_source_flag"}]
    assert any(row["pc"] == 1661 for row in mixed.ir_blocks)
    assert any(row["mode"] == "low_level_ir" for row in mixed.last_recovery["segments"])


@pytest.mark.parametrize("empty", [False, True])
def test_repeat_and_empty_have_exact_state_output_and_turn_effects(empty):
    baseline, mixed = paired(authored_package(empty=empty))
    _, first = same_command(baseline, mixed)
    assert first["text"] == ("The chest is empty.\n" if empty else "Inside oak chest is a letter.\n")
    assert first["recovery"]["primitive_hits"]["container.open"] == 1
    baseline.effects.clear()
    mixed.effects.clear()
    _, repeated = same_command(baseline, mixed)
    assert repeated["text"] == "Already raised.\n"
    assert repeated["moves"] == 2
    assert "container.open" not in repeated["recovery"]["primitive_hits"]
    assert repeated["recovery"]["primitive_hits"]["turn.count_player_action"] == 1
    assert mixed.recovery_stats["residual_bindings"] == {"post_open_source_flag": 1}
    assert int.from_bytes(mixed.memory[76:78], "big") == (1 if empty else 2)


def test_counter_rollover_preserves_both_source_writes():
    baseline, mixed = paired(authored_package(count=999))
    _, result = same_command(baseline, mixed)
    writes = [event for event in mixed.effects
              if event["kind"] == "memory_write" and event["start"] == TURN_ADDRESS]
    assert [(event["before"], event["after"]) for event in writes] == [
        ("03e7", "03e8"), ("03e8", "0000")]
    assert result["moves"] == 0
    assert result["recovery"]["binding_hits"]["turn_counter"] == 1


@pytest.mark.parametrize("change,reason", [
    (lambda package: package["udl"]["turn"].update(locals_count=5), "turn_frame_not_qualified"),
    (lambda package: package["udl"]["turn"].update(return_store=23), "turn_frame_not_qualified"),
    (lambda package: package["udl"]["turn"].update(cursor_equal=[0, 2]), "turn_scheduler_not_at_end"),
])
def test_unqualified_turn_frame_is_explicit_ir_fallback(change, reason):
    package = authored_package()
    change(package)
    baseline, mixed = paired(package)
    _, result = same_command(baseline, mixed)
    assert result["recovery"]["residual_reasons"][reason] == 1
    assert "turn_counter" not in result["recovery"]["binding_hits"]
    assert "turn.count_player_action" not in result["recovery"]["primitive_hits"]
    assert any(row["pc"] == TURN_ENTRY for row in mixed.ir_blocks)


def test_out_of_range_counter_does_not_claim_modulo_semantics():
    baseline, mixed = paired(authored_package(count=1000))
    _, result = same_command(baseline, mixed)
    assert result["moves"] == 0  # Source writes1001, then0; modulo1000 would yield1.
    assert result["recovery"]["residual_reasons"] == {"turn_counter_outside_qualified_domain": 1}
    assert "turn_counter" not in result["recovery"]["binding_hits"]
    assert "turn.count_player_action" not in result["recovery"]["primitive_hits"]


def test_commit_fault_reports_completed_effects_without_rollback_or_fallback():
    package = authored_package()
    package["low_level_ir"]["blocks"]["1601"]["nodes"].insert(
        0, {"op": "emit", "value": "x" * MAX_TEXT})
    package["udl"]["low_level_ir_sha256"] = value_digest(package["low_level_ir"])
    runtime = IntentRuntime(package)
    runtime.run()
    with pytest.raises(Word16Error, match="output budget"):
        runtime.command("open chest")
    assert runtime.memory[CHEST + 1] & 16
    assert runtime.memory[CHEST] & 16
    receipt = runtime.last_recovery["segments"][-1]
    assert receipt["status"] == "commit_fault"
    assert [effect["type"] for effect in receipt["completed_effects"]] == [
        "container_opened", "residual_ir"]
    assert receipt["interrupted_effect"]["type"] == "narrate"
    assert receipt["interrupted_effect_status"] == "unknown"
    assert runtime.recovery_stats["binding_hits"] == {}
    with pytest.raises(Word16Error, match="faulted"):
        runtime.run()
    assert runtime.last_recovery["segments"][-1] == receipt


def test_preflight_fault_reports_no_semantic_effects():
    runtime = IntentRuntime(authored_package())
    runtime.run()
    runtime._guards[UNRESOLVED_EFFECT] = b"\0"  # injected failure after live admission
    with pytest.raises(Word16Error, match="original bytes changed"):
        runtime.command("open chest")
    assert not runtime.memory[CHEST + 1] & 16
    assert not runtime.memory[CHEST] & 16
    receipt = runtime.last_recovery["segments"][-1]
    assert receipt["status"] == "preflight_fault"
    assert receipt["completed_effects"] == []
    assert receipt["interrupted_effect"] is None


def test_cli_fault_transcript_preserves_last_successful_checkpoint_for_fresh_resume(tmp_path):
    document = authored_package()
    document["low_level_ir"]["blocks"]["1601"]["nodes"].insert(
        0, {"op": "emit", "value": "x" * MAX_TEXT})
    document["udl"]["low_level_ir_sha256"] = value_digest(document["low_level_ir"])
    package, commands = tmp_path / "package.json", tmp_path / "commands.json"
    checkpoint, transcript = tmp_path / "checkpoint.json", tmp_path / "transcript.json"
    package.write_text(json.dumps(document))
    commands.write_text('["open chest"]')
    script = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
              "from fdisbull_player.__main__ import main;raise SystemExit(main())")
    def invoke(*options):
        return subprocess.run([sys.executable, "-I", "-B", "-c", script,
                               str(ROOT / "player"), "--intents", str(package), *options],
                              cwd=tmp_path, text=True, capture_output=True, timeout=15)
    failed = invoke("--commands", str(commands), "--checkpoint", str(checkpoint),
                    "--transcript", str(transcript))
    assert failed.returncode != 0
    fault = json.loads(transcript.read_text())[-1]
    assert fault["status"] == "fault"
    assert fault["recovery"]["segments"][-1]["status"] == "commit_fault"
    saved = json.loads(checkpoint.read_text())
    assert saved["fault"] is None and saved["pending_input"] is not None
    assert not bytes.fromhex(saved["memory"])[CHEST + 1] & 16
    commands.write_text("[]")
    resumed = invoke("--commands", str(commands), "--resume", str(checkpoint))
    assert resumed.returncode == 0, resumed.stderr


@pytest.mark.parametrize("receipt_failure", [False, True])
def test_cli_fault_summary_without_receipt_or_with_receipt_delivery_failure(tmp_path, receipt_failure):
    document = authored_package()
    document["low_level_ir"]["blocks"]["1601"]["nodes"].insert(
        0, {"op": "emit", "value": "x" * MAX_TEXT})
    document["udl"]["low_level_ir_sha256"] = value_digest(document["low_level_ir"])
    package, commands = tmp_path / "package.json", tmp_path / "commands.json"
    checkpoint, transcript = tmp_path / "checkpoint.json", tmp_path / "transcript.json"
    package.write_text(json.dumps(document))
    commands.write_text('["open chest"]')
    script = '''import sys
sys.path.insert(0, sys.argv.pop(1))
import fdisbull_player.intent_runtime as module
if sys.argv.pop(1) == "yes":
    original = module._atomic_json
    def fail_fault_receipt(path, value):
        if isinstance(value, list) and value and value[-1].get("status") == "fault":
            raise OSError("injected receipt delivery failure")
        return original(path, value)
    module._atomic_json = fail_fault_receipt
from fdisbull_player.__main__ import main
raise SystemExit(main())
'''
    argv = [sys.executable, "-I", "-B", "-c", script, str(ROOT / "player"),
            "yes" if receipt_failure else "no", "--intents", str(package),
            "--commands", str(commands), "--checkpoint", str(checkpoint)]
    if receipt_failure:
        argv += ["--transcript", str(transcript)]
    result = subprocess.run(argv, cwd=tmp_path, text=True, capture_output=True, timeout=15)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "Per-run output budget exceeded" in result.stderr
    assert "completed effect calls: 2" in result.stderr
    assert "interrupted effect completion: unknown" in result.stderr
    assert "checkpoint retained: yes" in result.stderr
    assert ("receipt delivery failed" in result.stderr) is receipt_failure
    assert len(result.stderr) < 2048 and "x" * 50 not in result.stderr
    saved = json.loads(checkpoint.read_text())
    assert saved["fault"] is None and saved["pending_input"] is not None
    assert not bytes.fromhex(saved["memory"])[CHEST + 1] & 16


@pytest.mark.parametrize("change,reason", [
    (lambda runtime: runtime._write_var(20, 2), "opening_target_not_qualified"),
    (lambda runtime: runtime._write_var(21, 44), "opening_action_not_qualified"),
    (lambda runtime: runtime._write_var(16, 2), "opening_scene_not_qualified"),
    (lambda runtime: runtime._write(1100, 8, 1), "live_source_dependency_changed:dependency"),
])
def test_unknown_opening_context_retains_ir_without_false_recovery(change, reason):
    baseline, mixed = paired(authored_package())
    change(baseline)
    change(mixed)
    _, result = same_command(baseline, mixed)
    assert result["recovery"]["residual_reasons"][reason] >= 1
    assert "mailbox_open" not in result["recovery"]["binding_hits"]
    assert "container.open" not in result["recovery"]["primitive_hits"]
    assert any(row["pc"] == OPEN_ENTRY for row in mixed.ir_blocks)


def test_live_guards_precede_projection_of_invalid_property_table():
    baseline, mixed = paired(authored_package())
    for runtime in (baseline, mixed):
        runtime._write(LETTER + 7, 16, 65535)
        runtime._write(1100, 8, 1)  # An already invalidated live-source dependency.
    # Stop on the original call boundary, before either opening body executes.
    assert compared_result(baseline.command("open chest", max_steps=1)) == compared_result(
        mixed.command("open chest", max_steps=1))
    assert mixed.pc == OPEN_ENTRY
    # Original IR can execute its first source block without consulting the
    # letter's property table. A speculative semantic projection would fault
    # here; the failed live guard must instead select the original source path.
    old, new = baseline.run(max_steps=1), mixed.run(max_steps=1)
    assert compared_result(old) == compared_result(new)
    assert baseline.snapshot() == mixed.low_level_snapshot()
    assert baseline.effects == mixed.effects
    assert new["status"] == "budget_exhausted"
    assert new["pc"] == UNRESOLVED_EFFECT
    assert new["recovery"]["residual_reasons"] == {
        "live_source_dependency_changed:dependency": 1}
    assert new["recovery"]["binding_hits"] == {}
    assert mixed.fault is None


def test_explicit_low_level_mode_cannot_pass_positive_recovery_gate():
    package = authored_package()
    baseline = TracedIR(package["low_level_ir"])
    mixed = TracedIntents(package, enable_intents=False)
    assert compared_result(baseline.run()) == compared_result(mixed.run())
    _, result = same_command(baseline, mixed)
    assert result["recovery"]["mode"] == "low_level_only"
    assert mixed.recovery_stats["binding_hits"] == {}
    assert mixed.recovery_stats["primitive_hits"] == {}
    assert not positive_recovery(mixed.recovery_stats)


@pytest.mark.parametrize("change,message", [
    (lambda package: package["uil"]["resources"].update(prefix="Changed "), "game-intent definition"),
    (lambda package: package["low_level_ir"]["blocks"]["1600"].update(next=1603), "retained low-level IR"),
    (lambda package: package["udl"]["source"].update(sha256="f" * 64), "source identities"),
    (lambda package: package["udl"].update(initial_image_sha256="f" * 64), "initial-image"),
    (lambda package: package["udl"]["witnesses"]["dependency"].update(bytes="01"), "witness"),
    (lambda package: package["udl"]["fields"]["target.is_open"].update(mask=8), "attribute correspondence"),
])
def test_correspondence_identity_and_source_witness_changes_fail_closed(change, message):
    package = authored_package()
    change(package)
    with pytest.raises(Word16Error, match=message):
        validate_package(package)


@pytest.mark.parametrize("corruption", ["aliased_discourse", "property_as_discourse",
                                        "removed_live_guards", "changed_return"])
def test_bad_udl_remaps_are_rejected_before_any_execution(corruption):
    package = authored_package()
    udl = package["udl"]
    if corruption == "aliased_discourse":
        operation = udl["fields"]["discourse.object"]["source_operation"]
        udl["fields"]["discourse.object"] = copy.deepcopy(udl["fields"]["discourse.scene"])
        udl["fields"]["discourse.object"]["source_operation"] = operation
    elif corruption == "property_as_discourse":
        udl["fields"]["discourse.object"] = {"kind": "property", "object": "sealed-letter",
                                              "number": 17, "source_operation": OPEN_TAIL}
    elif corruption == "removed_live_guards":
        udl["runtime_guards"] = udl["runtime_guards"][:1]
    else:
        udl["opening"]["return_value"] = 0

    class RefuseInitialization(IntentRuntime):
        def _initialize(self, *args, **kwargs):
            pytest.fail("Invalid UDL reached machine initialization")

    with pytest.raises(Word16Error):
        RefuseInitialization(package)


def test_executable_uil_change_is_observed_and_independent_checker_fails_it():
    package = authored_package()
    package["uil"]["resources"]["prefix"] = "You uncover "
    package["udl"]["uil_sha256"] = value_digest(package["uil"])
    result = differential(package, ["open chest"], TracedIR, TracedIntents,
                          seed=12, max_steps=1000)
    boundary = result["boundaries"][1]
    assert boundary["mixed_result"]["text"] == "You uncover oak chest is a letter.\n"
    assert boundary["baseline_result"]["text"] == "Inside oak chest is a letter.\n"
    assert boundary["snapshot_equal"]  # same state is insufficient: output effects differ
    assert not boundary["result_equal"]
    assert not boundary["ordered_effects_equal"]
    assert not result["summary"]["all_equal"]
    assert result["summary"]["positive_recovery"]


def test_checkpoint_binds_full_definition_and_normalizes_nested_game_slot_only():
    package = authored_package(game_save=True)
    baseline, mixed = paired(package)
    same_command(baseline, mixed)
    original = mixed.snapshot()
    assert original["game_slot"] is not None
    assert original["package_sha256"] == original["game_slot"]["package_sha256"]
    assert original["package_sha256"] != baseline.snapshot()["package_sha256"]
    normalized = mixed.low_level_snapshot()
    assert normalized == baseline.snapshot()
    assert mixed.snapshot() == original
    other = copy.deepcopy(package)
    other["uil"]["resources"]["repeat"] = "A different authored rule."
    other["udl"]["uil_sha256"] = value_digest(other["uil"])
    with pytest.raises(Word16Error, match="another program/profile"):
        IntentRuntime(other).restore(original)
    fresh = IntentRuntime(package)
    fresh.restore(original)
    assert fresh.low_level_snapshot() == normalized
    assert compared_result(fresh.command("again")) == compared_result(mixed.command("again"))
    assert fresh.low_level_snapshot() == mixed.low_level_snapshot()


def test_checkpoint_resumes_from_only_package_and_consumer_in_fresh_process(tmp_path):
    package = authored_package()
    package_path = tmp_path / "authored-intents.json"
    package_path.write_text(json.dumps(package))
    assert load_package(package_path) == package
    checkpoint = tmp_path / "checkpoint.json"
    commands = ["open chest", "again", "again"]
    expected = differential(package, commands, TracedIR, TracedIntents, seed=12,
                            max_steps=1000, checkpoint_at=1, checkpoint_path=checkpoint)
    assert expected["summary"]["all_equal"]
    resumed = fresh_process_resume(package_path, checkpoint, commands, 1,
                                    ROOT / "player", expected, max_steps=1000)
    assert resumed["all_equal"], resumed
    assert resumed["resumed_commands"] == 2
    assert resumed["recovery_stats"]["binding_hits"]["mailbox_open"] == 2
    assert resumed["recovery_stats"]["primitive_hits"]["turn.count_player_action"] == 2


def test_player_cli_intents_resume_and_input_output_alias_protection(tmp_path):
    package = tmp_path / "authored-intents.json"
    package.write_text(json.dumps(authored_package()))
    original_package = package.read_bytes()
    commands = tmp_path / "commands.json"
    commands.write_text('["open chest"]')
    checkpoint = tmp_path / "checkpoint.json"
    transcript = tmp_path / "transcript.json"
    script = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
              "from fdisbull_player.__main__ import main;raise SystemExit(main())")

    def invoke(*options):
        return subprocess.run([sys.executable, "-I", "-B", "-c", script,
                               str(ROOT / "player"), "--intents", str(package),
                               "--commands", str(commands), *options],
                              cwd=tmp_path, text=True, capture_output=True, timeout=15)

    started = invoke("--checkpoint", str(checkpoint), "--transcript", str(transcript))
    assert started.returncode == 0, started.stderr
    assert started.stdout == "Inside oak chest is a letter.\n"
    first = json.loads(transcript.read_text())[-1]
    assert first["recovery"]["primitive_hits"]["container.open"] == 1
    resumed = invoke("--resume", str(checkpoint), "--checkpoint", str(checkpoint),
                     "--transcript", str(transcript))
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout == "Already raised.\n"
    assert json.loads(transcript.read_text())[-1]["moves"] == 2
    checkpoint_before = checkpoint.read_bytes()
    rejected = invoke("--checkpoint", str(checkpoint), "--transcript", str(package))
    assert rejected.returncode != 0
    assert "would replace the package input" in rejected.stderr
    assert package.read_bytes() == original_package
    assert checkpoint.read_bytes() == checkpoint_before


def test_independent_checker_detects_unmodeled_machine_state_corruption():
    class CorruptContinuation(TracedIntents):
        def command(self, *args, **kwargs):
            result = super().command(*args, **kwargs)
            self.stack.append(99)
            return result

    result = differential(authored_package(), ["open chest"], TracedIR,
                          CorruptContinuation, seed=12, max_steps=1000)
    boundary = result["boundaries"][1]
    assert boundary["result_equal"]
    assert boundary["ordered_effects_equal"]
    assert not boundary["snapshot_equal"]
    assert boundary["snapshot_differences"] == [
        {"path": "/stack", "expected_length": 0, "actual_length": 1}]
    assert not result["summary"]["all_equal"]
