#!/usr/bin/env python3
"""Independent, release-bound Zork UIL comparison against unmodified dfrotz.

This is an independent verification harness, not part of the UIL consumer. Supply
your own story, command list, compiled UIL, and unmodified dfrotz 2.44 executable
built from the pinned reference commit below. No game assets are included here.
The consumer must run without Frotz, DOSBox, a DAT file, or the compiler on its
import path. Reports retain game text and belong outside all Git checkouts.

Text comparison removes dfrotz's generated status lines and the game's trailing
input prompt, then collapses whitespace. All remaining narrative characters are
compared. This intentionally does not assert pixel layout or original line wraps.
The reference route must emit at least one line-start '>' prompt per command; its
known 396-command winning run emits exactly 396. Missing boundaries are failures.

Reference limitation: dfrotz 2.44's dumb_input.c ignores os_read_line's max
argument (the source retains a TODO to enforce it). Differential input cases must
fit the game's input capacity. Overlong-line truncation is checked against the
v3 specification separately; dfrotz is not a valid oracle for that frontend case.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
STORY_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"
FROTZ_COMMIT = "fe66e2ef738354f5e2fe37c7c01b1781ef659acd"
STATUS_LINE = re.compile(
    r"(?m)^[ \t]*(?P<room>[^\n]*?)[ \t]{2,}Score:[ \t]*(?P<score>-?\d+)"
    r"[ \t]+Moves:[ \t]*(?P<moves>\d+)[ \t]*(?:\n|$)"
)
FINAL_SCORE = re.compile(r"Your score is (-?\d+) \(total of (\d+) points\), in (\d+) moves\.")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    text = STATUS_LINE.sub("", text).strip()
    if text.endswith(">"):
        text = text[:-1].rstrip()
    return " ".join(text.split())


def status_from_text(text: str, previous: dict[str, Any]) -> dict[str, Any]:
    result = dict(previous)
    for match in STATUS_LINE.finditer(text):
        result = {
            "status_room": match["room"].strip(),
            "score": int(match["score"]),
            "moves": int(match["moves"]),
        }
    final = FINAL_SCORE.search(text)
    if final:
        result.update(score=int(final[1]), maximum_score=int(final[2]), moves=int(final[3]))
    return result


def oracle(frotz: Path, story: Path, commands: list[str], seed: int, output: Path) -> dict[str, Any]:
    # The appended quit is only a cleanup path for bounded prefixes. A winning
    # full route exits before consuming it. Cleanup output is never compared.
    invocation = [str(frotz), "-m", "-p", "-s", str(seed), "-w", "1000", str(story)]
    started = time.monotonic()
    process = subprocess.run(
        invocation,
        input="\n".join(commands + ["quit", "y"]) + "\n",
        text=True,
        capture_output=True,
        cwd=output,
        timeout=60,
        check=False,
    )
    (output / "frotz-stdout.txt").write_text(process.stdout, encoding="utf-8")
    (output / "frotz-stderr.txt").write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0 or process.stderr:
        raise RuntimeError(f"dfrotz failed: exit={process.returncode}, stderr={process.stderr!r}")
    segments = re.split(r"\n>", process.stdout)
    if len(segments) - 1 < len(commands):
        raise RuntimeError(
            f"Reference ended early or prompt segmentation failed: "
            f"{len(segments)-1} boundaries for {len(commands)} commands"
        )
    initial_status = status_from_text(segments[0], {})
    previous = initial_status
    steps = []
    for index, command in enumerate(commands):
        raw = segments[index + 1]
        previous = status_from_text(raw, previous)
        steps.append({"seq": index + 1, "command": command, "text": raw,
                      "normalized": normalize(raw), "status": previous})
    return {
        "reference": "unmodified dfrotz 2.44",
        "source_commit": FROTZ_COMMIT,
        "executable_sha256": digest(frotz),
        "story_sha256": digest(story),
        "seed": seed,
        "invocation": invocation,
        "input_frontend_limitation": "dfrotz 2.44 dumb_input.c ignores the story's maximum input length; route commands must fit.",
        "maximum_command_characters": max(map(len, commands)),
        "elapsed_seconds": time.monotonic() - started,
        "returncode": process.returncode,
        "prompt_boundaries": len(segments) - 1,
        "initial": {"text": segments[0], "normalized": normalize(segments[0]), "status": initial_status},
        "steps": steps,
        "victory": "Inside the Barrow" in steps[-1]["text"],
        "deaths": process.stdout.count("You have died"),
    }


def first_difference(expected: str, actual: str) -> dict[str, Any] | None:
    if expected == actual:
        return None
    limit = min(len(expected), len(actual))
    position = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    return {"character": position,
            "reference": expected[max(0, position - 100):position + 220],
            "uil": actual[max(0, position - 100):position + 220],
            "reference_length": len(expected), "uil_length": len(actual)}


def fields_equal(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    return {key: {"reference": expected[key], "uil": actual.get(key),
                  "equal": expected[key] == actual.get(key)}
            for key in ("score", "moves") if key in expected}


def byte_ranges(offsets: list[int]) -> list[list[int]]:
    ranges: list[list[int]] = []
    for offset in offsets:
        if ranges and offset == ranges[-1][1] + 1:
            ranges[-1][1] = offset
        else:
            ranges.append([offset, offset])
    return ranges


def check_native(module: Any, program: dict[str, Any], receipt_path: Path,
                 max_steps: int) -> dict[str, Any]:
    """Compare native game memory using its recorded random results, never seed substitution."""
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["identity"]["story_sha256"] != STORY_SHA256:
        raise ValueError("Native oracle is for a different source story")
    tape = [{"range": row["range"], "value": row["value"]} for row in receipt["rng_tape"]]
    runtime = module.Word16Runtime(program, seed=12, random_tape=tape)
    rows = []
    for record in receipt["records"]:
        observed = (runtime.run(max_steps=max_steps) if record["command"] is None
                    else runtime.command(record["command"], max_steps=max_steps))
        ram_path = Path(record["ram_file"])
        if not ram_path.is_absolute():
            ram_path = receipt_path.resolve().parent / ram_path
        native = ram_path.read_bytes()
        if digest(ram_path) != record["ram_sha256"]:
            raise ValueError(f"Native memory receipt no longer matches: {ram_path}")
        end = receipt["static_memory"]
        if len(native) != end or len(runtime.memory) < end:
            raise ValueError("Native and consumer memory extents differ")
        # First64 bytes contain interpreter-specific capability/screen/header
        # state. No bytes outside that documented header are masked out.
        mismatches = [i for i in range(64, end) if native[i] != runtime.memory[i]]
        rows.append({"seq": record["seq"], "command": record["command"],
                     "uil_status": observed["status"], "uil_pc": observed.get("pc"),
                     "native_next_pc": record["next_virtual_pc"],
                     "compared_bytes": end - 64,
                     "mismatch_count": len(mismatches), "mismatch_ranges": byte_ranges(mismatches),
                     "first_mismatches": [{"address": i, "native": native[i], "uil": runtime.memory[i]}
                                          for i in mismatches[:40]],
                     "memory_equal": not mismatches,
                     "boundary_equal": observed["status"] == "input" and observed.get("pc") == record["next_virtual_pc"],
                     "equal": not mismatches and observed["status"] == "input" and observed.get("pc") == record["next_virtual_pc"]})
    actual_tape = [{"range": row["range"], "value": row["value"]}
                   for row in runtime.random_log if row["range"] > 0]
    return {"receipt": str(receipt_path), "identity": receipt["identity"],
            "header_exclusion": [0, 63], "records": rows,
            "all_game_memory_equal": all(row["memory_equal"] for row in rows),
            "all_input_boundaries_equal": all(row["boundary_equal"] for row in rows),
            "expected_rng_events": tape, "uil_rng_events": runtime.random_log,
            "rng_events_equal": actual_tape == tape}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uil", type=Path, required=True, help="Compiled UIL JSON or gzip JSON")
    parser.add_argument("--player-root", type=Path, default=HERE.parent / "player",
                        help="Directory containing fdisbull_player (default: this checkout's player/)")
    parser.add_argument("--story", type=Path, required=True, help="User-owned Zork I release 88, serial 840726 story")
    parser.add_argument("--commands", type=Path, required=True, help="JSON list of command strings")
    parser.add_argument("--frotz", type=Path, required=True, help="Unmodified dfrotz 2.44 executable from the pinned commit")
    parser.add_argument("--output", type=Path, required=True, help="New or empty private report directory outside every Git checkout")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-steps", type=int, default=2_000_000)
    parser.add_argument("--native-receipt", type=Path)
    args = parser.parse_args()
    commands = json.loads(args.commands.read_text(encoding="utf-8"))
    if not isinstance(commands, list) or not commands or any(not isinstance(c, str) or "\n" in c for c in commands):
        raise ValueError("Commands must be a nonempty list of single-line strings")
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("Limit must be positive")
        commands = commands[:args.limit]
    if digest(args.story) != STORY_SHA256:
        raise ValueError("Expected exact GOG Zork I R88 840726 story")
    output = args.output.resolve()
    if output == HERE.parent or HERE.parent in output.parents:
        raise ValueError("Reports retain game text and must be written outside this checkout")
    # Resolve first so symlinked parents cannot hide a checkout. Unlike empty
    # environment placeholders, a .git/HEAD or worktree .git file is a marker.
    for parent in (output, *output.parents):
        marker = parent / ".git"
        if (marker.is_dir() and (marker / "HEAD").is_file()) or marker.is_file():
            raise ValueError("Reports retain game text and must be written outside a Git checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    reference = oracle(args.frotz.resolve(), args.story.resolve(), commands, args.seed, output)
    (output / "reference.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(args.player_root.resolve()))
    module = importlib.import_module("fdisbull_player.word16")
    runtime_source = Path(module.__file__).resolve()
    runtime_sha256 = digest(runtime_source)
    program = module.load_program(args.uil)
    if program["source"]["sha256"] != STORY_SHA256:
        raise ValueError("UIL package has a different story identity")
    runtime = module.Word16Runtime(program, seed=args.seed)
    started = time.monotonic()
    initial = runtime.run(max_steps=args.max_steps)
    initial_difference = first_difference(reference["initial"]["normalized"], normalize(initial["text"]))
    results = []
    error = None
    for expected in reference["steps"]:
        try:
            actual = runtime.command(expected["command"], max_steps=args.max_steps)
        except Exception as exc:
            error = {"seq": expected["seq"], "command": expected["command"],
                     "type": type(exc).__name__, "message": str(exc), "pc": runtime.pc}
            break
        normalized = normalize(actual["text"])
        difference = first_difference(expected["normalized"], normalized)
        fields = fields_equal(expected["status"], actual)
        results.append({"seq": expected["seq"], "command": expected["command"],
                        "reference": expected["text"], "uil": actual["text"],
                        "text_equal": difference is None, "difference": difference,
                        "fields": fields,
                        "fields_equal": all(field["equal"] for field in fields.values()),
                        "uil_status": actual["status"], "uil_pc": actual.get("pc")})
        if expected["seq"] % 50 == 0:
            print(json.dumps({"processed": expected["seq"],
                              "text_mismatches": sum(not r["text_equal"] for r in results),
                              "score": actual.get("score"), "moves": actual.get("moves")}), flush=True)
    summary = {
        "expected_commands": len(commands), "compared_commands": len(results),
        "initial_text_equal": initial_difference is None,
        "matching_text": sum(row["text_equal"] for row in results),
        "mismatching_text": sum(not row["text_equal"] for row in results),
        "matching_fields": sum(row["fields_equal"] for row in results),
        "oracle_victory": reference["victory"], "oracle_final": reference["steps"][-1]["status"],
        "uil_final": {key: actual.get(key) for key in ("status", "score", "moves", "location", "pc")} if results else initial,
        "uil_elapsed_seconds": time.monotonic() - started,
        "executed_distinct_blocks": len(runtime.executed_blocks),
        "rng_events": len(runtime.random_log),
        "error": error,
    }
    summary["all_equal"] = (error is None and len(results) == len(commands)
                            and initial_difference is None
                            and all(r["text_equal"] and r["fields_equal"] for r in results))
    report = {"format": "zork-uil-independent-differential-1", "source_sha256": STORY_SHA256,
              "uil_file_sha256": digest(args.uil),
              "runtime_source_sha256": runtime_sha256,
              "verifier_source_sha256": digest(Path(__file__)),
              "commands_file_sha256": digest(args.commands),
              "seed": args.seed,
              "text_normalization": "Remove generated status lines and terminal prompt; collapse whitespace; retain every other character.",
              "initial_difference": initial_difference, "initial_uil": initial,
              "summary": summary, "steps": results, "random_log": runtime.random_log}
    if args.native_receipt:
        try:
            report["native"] = check_native(module, program, args.native_receipt, args.max_steps)
            summary["native_memory_equal"] = report["native"]["all_game_memory_equal"]
            summary["native_boundaries_equal"] = report["native"]["all_input_boundaries_equal"]
            summary["native_rng_equal"] = report["native"]["rng_events_equal"]
            summary["all_equal"] &= (summary["native_memory_equal"] and summary["native_boundaries_equal"]
                                      and summary["native_rng_equal"])
        except Exception as exc:
            report["native"] = {"error": {"type": type(exc).__name__, "message": str(exc)}}
            summary["all_equal"] = False
    if digest(runtime_source) != runtime_sha256:
        summary["runtime_source_changed_during_verification"] = True
        summary["all_equal"] = False
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["all_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
