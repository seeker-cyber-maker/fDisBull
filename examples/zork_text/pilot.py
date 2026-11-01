"""Real, narrow West of House harness experiment against fDisBull 0.20."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from fdisbull.project import Project
from adapter import ZorkScreenAdapter
from scene_harness import SceneHarness


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fresh_response(screen, command):
    marker = ">" + command + "\n"
    if marker not in screen["text"]:
        raise RuntimeError("command echo is missing from observed screen")
    return screen["text"].rsplit(marker, 1)[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True, help="new private .fdb path")
    parser.add_argument("--receipt", type=Path, help="optional new private JSON receipt")
    parser.add_argument("--journal", type=Path, required=True, help="new private JSONL event journal")
    args = parser.parse_args()
    game = args.game_dir.resolve(strict=True)
    binary, story = game / "_ZORK1.COM", game / "DATA" / "ZORK1.DAT"
    if args.project.exists():
        parser.error("project already exists; choose a new path")
    if args.receipt and args.receipt.exists():
        parser.error("receipt already exists; choose a new path")
    if args.journal.exists():
        parser.error("journal already exists; choose a new path")
    identities = {"interpreter_sha256": digest(binary), "story_sha256": digest(story), "backend_sha256": digest(args.backend)}
    t0 = time.perf_counter()
    with args.journal.open("x", encoding="utf-8") as journal, Project.create(args.project, binary, image="com") as project:
        imported = time.perf_counter()
        with project.debugger(args.backend, game, version=1) as debug:
            launched = time.perf_counter()
            adapter = ZorkScreenAdapter(debug)
            opening = adapter.wait_prompt()
            harness = SceneHarness(adapter, game, identities, debug.run_id, journal)
            def action(name):
                event = harness.act(name)
                if event.get("verdict") != "observed_expected_response":
                    raise RuntimeError("scene action not established: " + json.dumps(event))
                return adapter.ready
            first_prompt = time.perf_counter()
            if "West of House" not in opening["status"] or "small mailbox" not in opening["text"]:
                raise RuntimeError("opening scene not recognized")
            opened = action("open_mailbox")
            first_action = time.perf_counter()
            if "Opening the small mailbox reveals a leaflet." not in fresh_response(opened, "open mailbox"):
                raise RuntimeError("open mailbox outcome not observed")
            looked = action("look_west")
            checked = time.perf_counter()
            response = fresh_response(looked, "look")
            if "The small mailbox contains:" not in response or "A leaflet" not in response:
                raise RuntimeError("revisit did not show the leaflet")
            unknown = action("unknown_word")
            response = fresh_response(unknown, "blorb")
            if "don't know" not in response.lower():
                raise RuntimeError("unknown command response not observed")
            north = action("go_north")
            if "North of House" not in fresh_response(north, "north") or "North of House" not in north["status"]:
                raise RuntimeError("north transition not observed")
            blocked = action("try_south")
            if "windows are all boarded" not in fresh_response(blocked, "south").lower() or "North of House" not in blocked["status"]:
                raise RuntimeError("blocked south action not observed")
            returned = action("go_west")
            if "West of House" not in fresh_response(returned, "west") or "West of House" not in returned["status"]:
                raise RuntimeError("return transition not observed")
            revisited = action("look_west")
            if "A leaflet" not in fresh_response(revisited, "look"):
                raise RuntimeError("leaflet state not observed on return")
            finished = time.perf_counter()
            screenshot = debug.screenshot("zork-pilot-look.png")
            record = {"identities": identities, "run": debug.run_id, "project": str(args.project.resolve()), "journal": str(args.journal.resolve()),
                      "timings_seconds": {"project_import": round(imported-t0, 3), "launch": round(launched-imported, 3),
                      "launch_to_first_prompt": round(first_prompt-launched, 3), "prompt_to_verified_action": round(first_action-first_prompt, 3),
                      "start_to_verified_action": round(first_action-t0, 3), "look_and_verify": round(checked-first_action, 3),
                      "invalid_transition_return_revisit": round(finished-checked, 3), "start_to_full_route": round(finished-t0, 3)},
                      "observations": {"opening": opening, "open_mailbox": opened, "look": looked,
                                       "invalid": unknown, "north": north, "blocked_south": blocked, "west": returned, "revisit": revisited},
                      "screenshot": screenshot, "scope": "bounded opening scene, invalid command, transition and revisit; prompt is a display heuristic"}
    result = json.dumps(record, ensure_ascii=True, indent=2) + "\n"
    if args.receipt:
        with args.receipt.open("x", encoding="utf-8") as output:
            output.write(result)
    print(result, end="")


if __name__ == "__main__":
    main()
