"""Run named, bounded Zork scene actions with a private JSONL event journal."""
import argparse
import json
from pathlib import Path

from fdisbull.project import Project
from adapter import ZorkScreenAdapter
from scene_harness import ACTIONS, SceneHarness, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    if args.project.exists() or args.journal.exists():
        parser.error("project and journal must be new paths")
    game = args.game_dir.resolve(strict=True)
    ids = {"interpreter_sha256": sha256(game / "_ZORK1.COM"),
           "story_sha256": sha256(game / "DATA" / "ZORK1.DAT"),
           "backend_sha256": sha256(args.backend)}
    with args.journal.open("x", encoding="utf-8") as journal, Project.create(args.project, game / "_ZORK1.COM", image="com") as project:
        with project.debugger(args.backend, game, version=1) as debug:
            adapter = ZorkScreenAdapter(debug)
            first = adapter.wait_prompt()
            harness = SceneHarness(adapter, game, ids, debug.run_id, journal)
            print(json.dumps({"scene": first["status"], "screen": first["text"], "actions": list(ACTIONS)}), flush=True)
            while True:
                try:
                    action = input()
                except EOFError:
                    break
                if action == ":exit":
                    break
                result = harness.act(action)
                print(json.dumps(result, ensure_ascii=True), flush=True)
                if result["kind"] == "indeterminate":
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
