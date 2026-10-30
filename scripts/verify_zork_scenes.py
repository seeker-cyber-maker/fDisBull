#!/usr/bin/env python3
"""Compare executable scene UIL with preserved IR and the original reference.

This is a verification tool, not a player dependency. The actual story, Frotz,
commands, native captures and detailed output remain private inputs/artifacts.
The older conversion and its verifiers are used unchanged. Recovered selector
instructions are trapped in the complete opening/house-navigation case.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from verify_zork_uil import STORY_SHA256, check_native, digest, normalize, oracle
from verify_zork_intents import EffectTrace, INTERACTION_CASES, private_output, read_commands, state_differences, value_digest


HOUSE_CASE = [
    "open mailbox", "open mailbox", "take leaflet", "close mailbox", "open mailbox",
    "southwest", "east", "north", "east", "in", "open window", "in", "out",
    "south", "west", "open mailbox",
]


def game_result(result):
    return {key: value for key, value in result.items()
            if key not in ("steps", "recovery", "scene_recovery")}


FRESH_PROCESS = r'''
import hashlib, importlib.abc, json, pathlib, sys
root=pathlib.Path(sys.argv[1]).resolve()
allowed=(root,pathlib.Path(sys.base_prefix).resolve())
def audit(event,args):
    if event.startswith(('socket.','subprocess.')) or event=='os.system':
        raise RuntimeError('Original/runtime process access refused')
    if event=='open' and isinstance(args[0],(str,bytes)):
        path=pathlib.Path(args[0]).resolve()
        if not any(path==base or base in path.parents for base in allowed):
            raise RuntimeError('Read outside isolated consumer inputs refused: '+str(path))
class RefuseSource(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='fdisbull' or fullname.startswith(('fdisbull.','jericho','frotz')):
            raise ImportError('Original/compiler module refused')
sys.addaudithook(audit)
sys.meta_path.insert(0,RefuseSource())
sys.path.insert(0,str(root))
from fdisbull_player.scene_runtime import SceneRuntime,load_package
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
runtime=SceneRuntime(load_package(root/'package.json.gz'))
runtime.load_checkpoint(root/'checkpoint.json')
results=[]
for command in json.loads((root/'tail.json').read_text()):
    result=runtime.command(command)
    results.append({k:v for k,v in result.items() if k not in ('steps','recovery','scene_recovery')})
print(json.dumps({'results':results,'snapshot':digest(runtime.low_level_snapshot()),
                  'scene_stats':runtime.scene_stats,'source_modules_loaded':[n for n in sys.modules if n=='fdisbull' or n.startswith('fdisbull.')]}))
'''


def fresh_resume(package_path, checkpoint_path, commands, expected, player_root):
    with tempfile.TemporaryDirectory(prefix="zork-scenes-independent-") as tmp:
        root = Path(tmp)
        modules = root / "fdisbull_player"
        modules.mkdir()
        (modules / "__init__.py").write_text("")
        for name in ("word16", "game_intents", "intent_runtime", "scene_intents", "scene_bindings", "scene_runtime"):
            shutil.copyfile(player_root / "fdisbull_player" / (name + ".py"), modules / (name + ".py"))
        import gzip
        raw = package_path.read_bytes()
        if package_path.suffix != ".gz":
            raw = gzip.compress(raw, mtime=0)
        (root / "package.json.gz").write_bytes(raw)
        shutil.copyfile(checkpoint_path, root / "checkpoint.json")
        (root / "tail.json").write_text(json.dumps(commands))
        process = subprocess.run([sys.executable, "-I", "-B", "-c", FRESH_PROCESS, str(root)],
                                 cwd=root, text=True, capture_output=True, timeout=300)
        if process.returncode:
            return {"all_equal": False, "returncode": process.returncode, "stderr": process.stderr[-6000:]}
        actual = json.loads(process.stdout)
        return {"all_equal": actual["results"] == expected["results"]
                and actual["snapshot"] == expected["snapshot"] and not actual["source_modules_loaded"],
                "results_equal": actual["results"] == expected["results"],
                "complete_snapshot_equal": actual["snapshot"] == expected["snapshot"],
                "commands": len(commands), "scene_stats": actual["scene_stats"],
                "source_modules_loaded": actual["source_modules_loaded"],
                "isolation": "fresh Python -I; only six copied consumer modules, package, checkpoint and commands; external reads, source imports, network and subprocesses refused"}


def run_case(package, commands, *, name, output, story, frotz, seed, max_steps,
             old_class, new_class, checkpoint_after=None):
    directory = output / name
    directory.mkdir()
    reference = oracle(frotz.resolve(), story.resolve(), commands, seed, directory)
    (directory / "reference.json").write_text(json.dumps(reference, indent=2) + "\n")
    old = old_class(package["base_intents"]["low_level_ir"], seed=seed)
    new = new_class(package, seed=seed)
    if name == "house_progression":
        # These are the removed selector mechanisms, not simply the called
        # opening body. A fallback executing any one of them fails this case.
        new.forbidden_ir.update(pc for site in package["udl"]["dispatch"]["sites"] for pc in site["source_pcs"])
        new.forbidden_ir.update(package["udl"]["selection"]["source_operations"].values())
        new.forbidden_ir.update(package["udl"]["movement"]["source_operations"])
    rows, tail_results = [], []
    total_old_effects = total_new_effects = total_old_steps = total_new_steps = 0
    checkpoint = directory / "checkpoint.json"
    for seq, command in enumerate([None, *commands]):
        before = old.snapshot() if name == "house_progression" else None
        baseline = old.run(max_steps) if command is None else old.command(command, max_steps)
        candidate = new.run(max_steps) if command is None else new.command(command, max_steps)
        expected = reference["initial"] if command is None else reference["steps"][seq - 1]
        left, right = old.snapshot(), new.low_level_snapshot()
        row = {"seq": seq, "command": command,
               "result_equal": game_result(baseline) == game_result(candidate),
               "complete_snapshot_equal": left == right,
               "ordered_effects_equal": old.effects == new.effects,
               "reference_text_equal": normalize(candidate["text"]) == expected["normalized"],
               "reference_score_moves_equal": all(k in expected["status"] and candidate[k] == expected["status"][k]
                                                   for k in ("score", "moves")),
               "snapshot_sha256": value_digest(right),
               "effects_sha256": value_digest(new.effects),
               "effect_count": len(new.effects), "baseline_steps": baseline["steps"],
               "candidate_steps": candidate["steps"], "result": game_result(candidate),
               "scene_recovery": copy.deepcopy(new.last_scene_recovery),
               "intent_recovery": copy.deepcopy(new.last_recovery)}
        row["all_equal"] = all(row[k] for k in ("result_equal", "complete_snapshot_equal", "ordered_effects_equal",
                                                "reference_text_equal", "reference_score_moves_equal"))
        if not row["all_equal"]:
            row["state_differences"] = state_differences(left, right)
            row["effect_differences"] = state_differences(old.effects, new.effects)
            row["result_differences"] = state_differences(game_result(baseline), game_result(candidate))
        if name == "house_progression" and command in ("north", "in", "open mailbox"):
            witness = {"before": before, "baseline_after": left, "candidate_after": right,
                       "baseline_ordered_effects": old.effects, "candidate_ordered_effects": new.effects}
            path = directory / f"complete-interaction-{seq}.json"
            path.write_text(json.dumps(witness, indent=2) + "\n")
            row["complete_interaction_receipt"] = {"file": path.name, "sha256": digest(path)}
        rows.append(row)
        total_old_effects += len(old.effects)
        total_new_effects += len(new.effects)
        total_old_steps += baseline["steps"]
        total_new_steps += candidate["steps"]
        old.effects.clear(); new.effects.clear()
        if checkpoint_after is not None and seq == checkpoint_after:
            new.save_checkpoint(checkpoint)
        if checkpoint_after is not None and seq > checkpoint_after:
            tail_results.append(game_result(candidate))
        if not row["all_equal"]:
            break
    path = directory / "boundaries.json"
    path.write_text(json.dumps(rows, indent=2) + "\n")
    summary = {"commands": len(commands), "boundaries": len(rows),
               "all_equal": len(rows) == len(commands) + 1 and all(r["all_equal"] for r in rows),
               "forbidden_original_blocks": len(new.forbidden_ir),
               "scene_stats": new.scene_stats, "intent_stats": new.recovery_stats,
               "baseline_effects": total_old_effects, "candidate_effects": total_new_effects,
               "baseline_steps": total_old_steps, "candidate_steps": total_new_steps,
               "final": {key: candidate.get(key) for key in ("status", "score", "moves", "location", "pc")},
               "final_snapshot_sha256": value_digest(new.low_level_snapshot()),
               "boundaries_sha256": digest(path), "reference_sha256": digest(directory / "reference.json")}
    return summary, checkpoint, {"results": tail_results, "snapshot": summary["final_snapshot_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--commands", type=Path, required=True)
    parser.add_argument("--frotz", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parser-commands", type=Path)
    parser.add_argument("--native-receipt", type=Path)
    parser.add_argument("--player-root", type=Path, default=Path(__file__).resolve().parents[1] / "player")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=2_000_000)
    parser.add_argument("--checkpoint-after", type=int, default=100)
    args = parser.parse_args()
    if digest(args.story) != STORY_SHA256:
        raise ValueError("Expected the exact qualified Zork I R88 story")
    output = private_output(args.output)
    sys.path.insert(0, str(args.player_root.resolve()))
    from fdisbull_player.scene_runtime import SceneRuntime, load_package
    from fdisbull_player.word16 import Word16Runtime
    package = load_package(args.package)
    if package["base_intents"]["low_level_ir"]["source"]["sha256"] != STORY_SHA256:
        raise ValueError("Scene package is for another source")
    sources = {str(args.player_root / "fdisbull_player" / (name + ".py")):
               digest(args.player_root / "fdisbull_player" / (name + ".py"))
               for name in ("word16", "game_intents", "intent_runtime", "scene_intents", "scene_bindings", "scene_runtime")}
    old_class = type("TracedOriginalIR", (EffectTrace, Word16Runtime), {})
    new_class = type("TracedSceneUIL", (EffectTrace, SceneRuntime), {})
    full_commands = read_commands(args.commands)
    cases = {"house_progression": HOUSE_CASE, "full_route": full_commands, **INTERACTION_CASES}
    if args.parser_commands:
        cases["parser_alternatives"] = read_commands(args.parser_commands)
    report = {"format": "fdisbull-zork-scenes-verification-1", "source_sha256": STORY_SHA256,
              "package_sha256": digest(args.package), "runtime_sources": sources,
              "checker_sha256": digest(Path(__file__)), "command_source_sha256": digest(args.commands),
              "seed": args.seed, "comparison_contract": {
                  "state": "every machine snapshot field, normalizing only recursive package identity",
                  "effects": "every ordered physical memory assignment, text fragment and random draw",
                  "game_result": "every result field except implementation dispatch count and recovery audits",
                  "reference": "fresh dfrotz; original checker narrative normalization and score/move fields",
                  "trap": "all recovered dispatch-site instructions, exit selection operations and on-foot movement blocks refused in house progression",
              }, "cases": {}}
    checkpoint_after = min(max(1, args.checkpoint_after), len(full_commands) - 1)
    for name, commands in cases.items():
        summary, checkpoint, expected = run_case(package, commands, name=name, output=output,
            story=args.story, frotz=args.frotz, seed=args.seed, max_steps=args.max_steps,
            old_class=old_class, new_class=new_class,
            checkpoint_after=checkpoint_after if name == "full_route" else None)
        report["cases"][name] = summary
        print(json.dumps({"case": name, "all_equal": summary["all_equal"], "boundaries": summary["boundaries"],
                          "final": summary["final"], "primitive_hits": summary["scene_stats"]["primitive_hits"]}), flush=True)
        if not summary["all_equal"]:
            break
        if name == "full_route":
            report["fresh_process_resume"] = fresh_resume(args.package, checkpoint,
                commands[checkpoint_after:], expected, args.player_root.resolve())
    if args.native_receipt:
        report["native"] = check_native(SimpleNamespace(Word16Runtime=SceneRuntime), package,
                                         args.native_receipt, args.max_steps)
        report["native"]["receipt_sha256"] = digest(args.native_receipt)
    positive = report["cases"]["house_progression"]["scene_stats"]
    native = report.get("native")
    report["source_files_unchanged"] = all(digest(Path(path)) == sha for path, sha in sources.items())
    report["all_equal"] = (len(report["cases"]) == len(cases)
        and all(case["all_equal"] for case in report["cases"].values())
        and all(positive["primitive_hits"].get(name, 0) > 0 for name in ("scene.select_exit", "scene.move_actor"))
        and positive["dispatch_sites"].get("verb_action", 0) > 0
        and report.get("fresh_process_resume", {}).get("all_equal", False)
        and report["source_files_unchanged"]
        and (native is None or all(native[key] for key in ("all_game_memory_equal", "all_input_boundaries_equal", "rng_events_equal"))))
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["all_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
