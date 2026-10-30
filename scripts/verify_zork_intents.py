#!/usr/bin/env python3
"""Verify recovered Zork game intents against retained IR and independent oracles.

This checker never treats a semantic label or successful fallback as recovery.
It compares the complete original machine state after every command and every
ordered memory assignment, output fragment and random result. A controlled
mailbox case refuses execution of the replaced handler's IR, except the source
flag deliberately retained as residual. Positive binding and primitive counts
are required. The original word16 runtime and its verifier remain unchanged.

Reports contain game-derived text and state evidence. Write them outside Git.
The original game, dfrotz and native capture receipts are verification inputs;
they are not dependencies of the mixed intent/IR consumer.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

from verify_zork_uil import (
    STORY_SHA256, check_native, digest, first_difference, normalize, oracle,
)


HERE = Path(__file__).resolve().parent
REQUIRED_PRIMITIVES = ("container.open", "turn.count_player_action")
REQUIRED_BINDINGS = ("mailbox_open", "turn_counter")

# These are test inputs for the exact release, not consumer command dispatch.
# Five pronoun paths exercise the parser effects of mentioning the leaflet.
INTERACTION_CASES = {
    "first_repeat_empty": ["open mailbox", "open mailbox", "take leaflet",
                           "close mailbox", "open mailbox"],
    "unavailable_target": ["north", "open mailbox"],
    "unknown_and_meta": ["open asdfgh", "score"],
    "wait_turns": ["wait", "score"],
    "pronoun_read": ["open mailbox", "read it"],
    "pronoun_take": ["open mailbox", "take it", "inventory"],
    "pronoun_close_reopen": ["open mailbox", "close mailbox", "open it"],
    "pronoun_drop": ["open mailbox", "take leaflet", "drop it", "look"],
    "pronoun_put": ["open mailbox", "take leaflet", "put it in mailbox",
                    "close mailbox", "open mailbox"],
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def value_digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class TracedMemory(bytearray):
    """Record physical assignments, including input and memory-stream slices."""

    def __new__(cls, value, owner):
        return super().__new__(cls, value)

    def __init__(self, value, owner):
        super().__init__(value)
        self.owner = owner

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            before = bytes(self[key])
            replacement = bytes(value)
            super().__setitem__(key, replacement)
            self.owner.effects.append({"kind": "memory_write", "start": start,
                "stop": stop, "stride": step, "before": before.hex(),
                "after": replacement.hex()})
        else:
            index = key if key >= 0 else len(self) + key
            before = self[key]
            super().__setitem__(key, value)
            self.owner.effects.append({"kind": "memory_write", "start": index,
                "stop": index + 1, "stride": 1, "before": bytes((before,)).hex(),
                "after": bytes((self[key],)).hex()})


class EffectTrace:
    """Instrumentation only; all production operations delegate unchanged."""

    def __init__(self, *args, **kwargs):
        self.effects = []
        self.ir_blocks = []
        self.forbidden_ir = set()
        super().__init__(*args, **kwargs)

    def _initialize(self, flags2=None):
        previous = bytes(self.memory) if hasattr(self, "memory") else None
        super()._initialize(flags2)
        self.memory = TracedMemory(self.memory, self)
        if previous is not None:
            self.effects.append({"kind": "memory_reset",
                "before_sha256": hashlib.sha256(previous).hexdigest(),
                "after_sha256": hashlib.sha256(self.memory).hexdigest()})

    def restore(self, snapshot):
        previous = bytes(self.memory)
        super().restore(snapshot)
        self.memory = TracedMemory(self.memory, self)
        self.effects.append({"kind": "memory_restore",
            "before_sha256": hashlib.sha256(previous).hexdigest(),
            "after_sha256": hashlib.sha256(self.memory).hexdigest()})

    def _emit(self, value):
        self.effects.append({"kind": "text_fragment", "text": value})
        return super()._emit(value)

    def _random(self, count):
        result = super()._random(count)
        self.effects.append({"kind": "random", "range": count, "value": result})
        return result

    def _record_low_level_block(self, pc, binding=None):
        if pc in self.forbidden_ir:
            raise AssertionError(f"Recovered body executed retained IR at {pc:#x}")
        self.ir_blocks.append({"pc": pc, "binding": binding})
        return super()._record_low_level_block(pc, binding)


def compared_result(result):
    # Implementation work differs when a semantic operation replaces several
    # machine blocks. Every game-facing field remains part of equality.
    return {key: value for key, value in result.items()
            if key not in ("steps", "recovery")}


def state_differences(expected, actual, prefix="", budget=20):
    """Bound diagnostics only; callers compare entire values before reporting."""
    if expected == actual:
        return []
    if budget <= 0:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        rows = []
        for key in sorted(set(expected) | set(actual)):
            path = prefix + "/" + str(key)
            if key not in expected or key not in actual:
                rows.append({"path": path, "expected_present": key in expected,
                             "actual_present": key in actual})
            else:
                rows.extend(state_differences(expected[key], actual[key], path,
                                              budget - len(rows)))
            if len(rows) >= budget:
                break
        return rows
    if prefix.endswith("/memory") and isinstance(expected, str) and isinstance(actual, str):
        old, new = bytes.fromhex(expected), bytes.fromhex(actual)
        differences = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
        return [{"path": prefix, "expected_bytes": len(old), "actual_bytes": len(new),
                 "different_common_bytes": len(differences),
                 "first_offsets": differences[:budget]}]
    if isinstance(expected, list) and isinstance(actual, list):
        rows = []
        if len(expected) != len(actual):
            rows.append({"path": prefix, "expected_length": len(expected),
                         "actual_length": len(actual)})
        for index, (left, right) in enumerate(zip(expected, actual)):
            rows.extend(state_differences(left, right, prefix + "/" + str(index),
                                          budget - len(rows)))
            if len(rows) >= budget:
                break
        return rows
    return [{"path": prefix, "expected": expected, "actual": actual}]


def compare_boundary(baseline, mixed, old_result, new_result, seq, command, reference,
                     before_state=None):
    old_state, new_state = baseline.snapshot(), mixed.low_level_snapshot()
    old_effects, new_effects = baseline.effects, mixed.effects
    row = {
        "seq": seq, "command": command,
        "result_equal": compared_result(old_result) == compared_result(new_result),
        "snapshot_equal": old_state == new_state,
        "ordered_effects_equal": old_effects == new_effects,
        "baseline_snapshot_sha256": value_digest(old_state),
        "mixed_snapshot_sha256": value_digest(new_state),
        "baseline_effects_sha256": value_digest(old_effects),
        "mixed_effects_sha256": value_digest(new_effects),
        "baseline_effect_count": len(old_effects), "mixed_effect_count": len(new_effects),
        "baseline_steps": old_result["steps"], "mixed_steps": new_result["steps"],
        "baseline_result": old_result, "mixed_result": new_result,
        "snapshot_differences": state_differences(old_state, new_state),
        "result_differences": state_differences(compared_result(old_result), compared_result(new_result)),
        "effect_differences": state_differences(old_effects, new_effects),
    }
    if reference is not None:
        difference = first_difference(reference["normalized"], normalize(new_result["text"]))
        expected_status = reference["status"]
        # Missing oracle status fields must not silently make all([]) succeed.
        status_available = all(key in expected_status for key in ("score", "moves"))
        row.update(reference_text_equal=difference is None,
                   reference_difference=difference,
                   reference_status_available=status_available,
                   reference_score_moves_equal=status_available and all(
                       expected_status[key] == new_result[key] for key in ("score", "moves")))
    else:
        row.update(reference_text_equal=True, reference_status_available=True,
                   reference_score_moves_equal=True)
    row["all_equal"] = all(row[key] for key in (
        "result_equal", "snapshot_equal", "ordered_effects_equal",
        "reference_text_equal", "reference_status_available", "reference_score_moves_equal"))
    # Preserve the complete ordered effect sequence for the actual recovered
    # mailbox interaction, not just the aggregate counters used by summaries.
    if new_result.get("recovery", {}).get("binding_hits", {}).get("mailbox_open", 0):
        row["baseline_ordered_effects"] = copy.deepcopy(old_effects)
        row["mixed_ordered_effects"] = copy.deepcopy(new_effects)
        row["complete_input_state_before"] = before_state
        row["complete_baseline_state_after"] = old_state
        row["complete_mixed_state_after"] = new_state
    baseline.effects.clear()
    mixed.effects.clear()
    return row


def positive_recovery(stats, *, required_bindings=REQUIRED_BINDINGS,
                      required_primitives=REQUIRED_PRIMITIVES):
    return (bool(required_bindings) and bool(required_primitives)
            and all(stats.get("binding_hits", {}).get(key, 0) > 0 for key in required_bindings)
            and all(stats.get("primitive_hits", {}).get(key, 0) > 0 for key in required_primitives))


def differential(package, commands, old_class, mixed_class, *, seed, max_steps,
                 reference=None, checkpoint_at=None, checkpoint_path=None,
                 forbid_first_mailbox_ir=False, required_bindings=REQUIRED_BINDINGS,
                 required_primitives=REQUIRED_PRIMITIVES):
    baseline = old_class(package["low_level_ir"], seed=seed)
    mixed = mixed_class(package, seed=seed)
    rows = [compare_boundary(baseline, mixed, baseline.run(max_steps=max_steps),
                             mixed.run(max_steps=max_steps), 0, None,
                             reference["initial"] if reference else None)]
    error = None
    for index, command in enumerate(commands, 1):
        if forbid_first_mailbox_ir and index == 1:
            # The unresolved source flag at0x80a6 is intentionally permitted.
            # These include the handler, list formatter, referent helper and
            # counter. The controlled first interaction uses the referent
            # helper only inside the recovered action, so it can be trapped.
            mixed.forbidden_ir = ((set(range(0x8089, 0x80f5)) - {0x80a6})
                                  | set(range(0x8e65, 0x8eaa))
                                  | set(range(0x9533, 0x953a))
                                  | set(range(0x54ec, 0x54f5)))
        else:
            mixed.forbidden_ir.clear()
        try:
            before_state = baseline.snapshot()
            old = baseline.command(command, max_steps=max_steps)
            new = mixed.command(command, max_steps=max_steps)
            row = compare_boundary(baseline, mixed, old, new, index, command,
                                   reference["steps"][index - 1] if reference else None,
                                   before_state)
            rows.append(row)
            if checkpoint_at == index:
                mixed.save_checkpoint(checkpoint_path)
            if not row["all_equal"]:
                break
        except Exception as exc:
            error = {"seq": index, "command": command,
                     "type": type(exc).__name__, "message": str(exc)}
            break
    stats = copy.deepcopy(mixed.recovery_stats)
    summary = {
        "commands_expected": len(commands), "commands_compared": len(rows) - 1,
        "matching_snapshots": sum(row["snapshot_equal"] for row in rows),
        "matching_ordered_effects": sum(row["ordered_effects_equal"] for row in rows),
        "matching_results": sum(row["result_equal"] for row in rows),
        "matching_reference_narratives": sum(row["reference_text_equal"] for row in rows),
        "matching_reference_score_moves": sum(row["reference_score_moves_equal"] for row in rows),
        "recovery_stats": stats,
        "binding_counts": {key: stats.get("binding_hits", {}).get(key, 0) for key in REQUIRED_BINDINGS},
        "primitive_counts": {key: stats.get("primitive_hits", {}).get(key, 0) for key in REQUIRED_PRIMITIVES},
        "required_recovery": {"bindings": list(required_bindings), "primitives": list(required_primitives)},
        "positive_recovery": positive_recovery(stats, required_bindings=required_bindings,
                                                required_primitives=required_primitives),
        "first_open_replaced_body_trap": forbid_first_mailbox_ir,
        "error": error,
        "final": {key: rows[-1]["mixed_result"].get(key)
                  for key in ("status", "score", "moves", "location", "pc")},
        "all_equal": error is None and len(rows) == len(commands) + 1
                     and all(row["all_equal"] for row in rows),
    }
    return {"summary": summary, "boundaries": rows,
            "final_snapshot_sha256": value_digest(mixed.low_level_snapshot())}


FRESH_PROCESS = r'''
import hashlib, importlib.abc, json, os, pathlib, sys
root=pathlib.Path(sys.argv[1]).resolve()
stdlib=pathlib.Path(sys.base_prefix).resolve()
sys.path.insert(0,str(root))
class RefuseOriginal(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('fdisbull','jericho','frotz'):
            raise RuntimeError('Original/compiler dependency attempted: '+fullname)
sys.meta_path.insert(0,RefuseOriginal())
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        path=pathlib.Path(os.fsdecode(args[0])).resolve()
        if not (path==root or root in path.parents or path==stdlib or stdlib in path.parents):
            raise RuntimeError('External file access refused: '+str(path))
    if event.startswith('socket.') or event=='subprocess.Popen':
        raise RuntimeError('Network/subprocess access refused')
sys.addaudithook(audit)
from fdisbull_player.intent_runtime import IntentRuntime,load_package
r=IntentRuntime(load_package(root/sys.argv[2]),seed=12)
r.load_checkpoint(root/'checkpoint.json')
rows=[]
for command in json.loads((root/'tail.json').read_text()):
    result=r.command(command,max_steps=int(sys.argv[3]))
    result={key:value for key,value in result.items() if key not in ('steps','recovery')}
    rows.append(result)
state=r.low_level_snapshot()
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
print(json.dumps({'results':rows,'final_snapshot_sha256':digest(state),'recovery_stats':r.recovery_stats,
    'original_modules_loaded':any(name.split('.')[0] in ('fdisbull','jericho','frotz') for name in sys.modules)}))
'''


def fresh_process_resume(package_path, checkpoint_path, commands, checkpoint_at,
                         player_root, expected, max_steps=2_000_000):
    with tempfile.TemporaryDirectory(prefix="zork-intent-resume-") as directory:
        root = Path(directory)
        modules = root / "fdisbull_player"
        modules.mkdir()
        (modules / "__init__.py").write_text("")
        for name in ("word16.py", "game_intents.py", "intent_runtime.py"):
            shutil.copyfile(player_root / "fdisbull_player" / name, modules / name)
        package_name = "package.json.gz" if package_path.suffix == ".gz" else "package.json"
        shutil.copyfile(package_path, root / package_name)
        shutil.copyfile(checkpoint_path, root / "checkpoint.json")
        (root / "tail.json").write_text(json.dumps(commands[checkpoint_at:]))
        result = subprocess.run([sys.executable, "-I", "-B", "-c", FRESH_PROCESS,
                                 str(root), package_name, str(max_steps)],
                                cwd=root, capture_output=True, text=True, timeout=300)
        if result.returncode:
            return {"all_equal": False, "returncode": result.returncode,
                    "stderr": result.stderr[-6000:]}
        actual = json.loads(result.stdout)
        wanted = [compared_result(row["mixed_result"])
                  for row in expected["boundaries"][checkpoint_at + 1:]]
        return {"checkpoint_after_commands": checkpoint_at,
                "resumed_commands": len(actual["results"]),
                "all_results_equal": actual["results"] == wanted,
                "complete_final_snapshot_equal": actual["final_snapshot_sha256"] == expected["final_snapshot_sha256"],
                "original_modules_loaded": actual["original_modules_loaded"],
                "recovery_stats": actual["recovery_stats"],
                "isolation": "Fresh Python -I process; only copied package/consumer/checkpoint/tail inputs; workspace reads, network and subprocesses refused.",
                "all_equal": actual["results"] == wanted
                    and actual["final_snapshot_sha256"] == expected["final_snapshot_sha256"]
                    and not actual["original_modules_loaded"]}


def private_output(path):
    path = path.resolve()
    if path == HERE.parent or HERE.parent in path.parents:
        raise ValueError("Game-derived reports must be outside this checkout")
    for parent in (path, *path.parents):
        marker = parent / ".git"
        if marker.is_file() or (marker.is_dir() and (marker / "HEAD").is_file()):
            raise ValueError("Game-derived reports must be outside every Git checkout")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("Report output must be new or empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_commands(path):
    commands = json.loads(path.read_text())
    if (not isinstance(commands, list) or not commands
            or any(not isinstance(value, str) or any(c in value for c in "\r\n\0")
                   for value in commands)):
        raise ValueError("Commands must be a nonempty JSON list of single-line strings")
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--story", required=True, type=Path)
    parser.add_argument("--commands", required=True, type=Path)
    parser.add_argument("--frotz", required=True, type=Path)
    parser.add_argument("--parser-commands", type=Path)
    parser.add_argument("--native-receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--player-root", type=Path, default=HERE.parent / "player")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=2_000_000)
    parser.add_argument("--checkpoint-after", type=int, default=100)
    args = parser.parse_args()
    if digest(args.story) != STORY_SHA256:
        raise ValueError("Expected the exact Zork I R88 story")
    commands = read_commands(args.commands)
    parser_commands = read_commands(args.parser_commands) if args.parser_commands else None
    output = private_output(args.output)
    sys.path.insert(0, str(args.player_root.resolve()))
    old_module = importlib.import_module("fdisbull_player.word16")
    mixed_module = importlib.import_module("fdisbull_player.intent_runtime")
    semantics_module = importlib.import_module("fdisbull_player.game_intents")
    frozen = {str(Path(module.__file__).resolve()): digest(Path(module.__file__))
              for module in (old_module, mixed_module, semantics_module)}
    package_hash = digest(args.package)
    package = mixed_module.load_package(args.package)
    if package["low_level_ir"]["source"]["sha256"] != STORY_SHA256:
        raise ValueError("Intent package has a different source identity")
    old_class = type("TracedRetainedIR", (EffectTrace, old_module.Word16Runtime), {})
    mixed_class = type("TracedGameIntents", (EffectTrace, mixed_module.IntentRuntime), {})
    cases = {"full_route": commands, **INTERACTION_CASES}
    if parser_commands is not None:
        cases["parser_alternatives"] = parser_commands
    report = {"format": "fdisbull-zork-intent-differential-1",
              "source_sha256": STORY_SHA256, "package_sha256": package_hash,
              "runtime_sources": frozen, "checker_sha256": digest(Path(__file__)),
              "command_source_sha256": digest(args.commands), "seed": args.seed,
              "acceptance_requirements": {
                  "full_route": "The unchanged winning route must execute the recovered turn counter. It does not open the mailbox.",
                  "first_repeat_empty": "The complete mailbox interaction must execute both recovered bindings and both state-changing primitives, with the replaced source bodies trapped.",
                  "all_cases": "Every result, complete snapshot and ordered effect must match; unsupported contexts remain explicit IR.",
              },
              "comparison_contract": {
                  "snapshot": "Every field compared; only recursive package identity normalized to retained-IR identity.",
                  "effects": "Every physical memory assignment, output fragment and random range/result in order.",
                  "result": "Every field except implementation steps and intent audit.",
                  "reference_text": "Existing checker normalization: remove status decoration/prompt and collapse whitespace.",
              }, "cases": {}}
    checkpoint_at = min(max(1, args.checkpoint_after), max(1, len(commands) - 1))
    checkpoint_path = output / "resume-checkpoint.json"
    for name, selected in cases.items():
        directory = output / name
        directory.mkdir()
        reference = oracle(args.frotz.resolve(), args.story.resolve(), selected, args.seed, directory)
        (directory / "reference.json").write_text(json.dumps(reference, indent=2) + "\n")
        result = differential(package, selected, old_class, mixed_class, seed=args.seed,
            max_steps=args.max_steps, reference=reference,
            checkpoint_at=checkpoint_at if name == "full_route" else None,
            checkpoint_path=checkpoint_path,
            forbid_first_mailbox_ir=name == "first_repeat_empty",
            required_bindings=("turn_counter",) if name == "full_route" else REQUIRED_BINDINGS,
            required_primitives=("turn.count_player_action",) if name == "full_route" else REQUIRED_PRIMITIVES)
        (directory / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
        report["cases"][name] = {"summary": result["summary"],
                                 "reference_sha256": digest(directory / "reference.json"),
                                 "comparison_sha256": digest(directory / "comparison.json")}
        print(json.dumps({"case": name, **result["summary"]}), flush=True)
        if name == "full_route":
            full_result = result
    if args.native_receipt:
        facade = SimpleNamespace(Word16Runtime=mixed_module.IntentRuntime)
        report["native"] = check_native(facade, package, args.native_receipt, args.max_steps)
        report["native"]["receipt_sha256"] = digest(args.native_receipt)
    if full_result["summary"]["all_equal"] and checkpoint_path.is_file():
        report["fresh_process_resume"] = fresh_process_resume(args.package, checkpoint_path,
            commands, checkpoint_at, args.player_root, full_result, args.max_steps)
    else:
        report["fresh_process_resume"] = {"all_equal": False, "reason": "Full route/checkpoint failed"}
    report["source_files_unchanged"] = (all(digest(Path(path)) == sha for path, sha in frozen.items())
                                        and digest(args.package) == package_hash)
    native = report.get("native")
    report["all_equal"] = (
        all(case["summary"]["all_equal"] for case in report["cases"].values())
        and report["cases"]["full_route"]["summary"]["positive_recovery"]
        and report["cases"]["first_repeat_empty"]["summary"]["positive_recovery"]
        and report["fresh_process_resume"]["all_equal"]
        and report["source_files_unchanged"]
        and (native is None or (bool(native["records"]) and all(native[key] for key in
             ("all_game_memory_equal", "all_input_boundaries_equal", "rng_events_equal")))))
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"all_equal": report["all_equal"], "report": str(output / "verification.json")}), flush=True)
    return 0 if report["all_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
