"""Terminal player for the qualified DOS text screen via fDisBull 0.20."""
import argparse
from pathlib import Path

from fdisbull.project import Project
from adapter import ObservationError, ZorkScreenAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True, help="new private project path")
    args = parser.parse_args()
    if args.project.exists():
        parser.error("project already exists; choose a new path")
    game = args.game_dir.resolve(strict=True)
    with Project.create(args.project, game / "_ZORK1.COM", image="com") as project:
        with project.debugger(args.backend, game, version=1) as debug:
            adapter = ZorkScreenAdapter(debug)
            try:
                screen = adapter.wait_prompt()
                while True:
                    print("\n" + screen["text"])
                    try:
                        line = input("command (or :exit): ")
                    except EOFError:
                        break
                    if line == ":exit":
                        break
                    try:
                        screen = adapter.command(line)
                    except ValueError as exc:
                        print(exc)
            except ObservationError as exc:
                print("Observation stopped:", exc)
                print("The guest outcome is unknown; do not blindly retry the command.")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
