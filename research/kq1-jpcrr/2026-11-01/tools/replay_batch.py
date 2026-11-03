"""Run four stock-emulator captures sequentially with explicit private inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


JOBS = (
    ("automatic-first", "KQ1-Robb-Route-63-complete"),
    ("automatic-repeat", "KQ1-Robb-Route-63-complete"),
    ("bow-first", "KQ1-Robb-Route-BOW-66-complete"),
    ("bow-repeat", "KQ1-Robb-Route-BOW-66-complete"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="New private parent directory for all four captures")
    parser.add_argument("--movies-root", type=Path,
                        default=Path(__file__).resolve().parent.parent / "movies")
    parser.add_argument("--stop-ns", type=int, default=35_000_000_000)
    parser.add_argument("--host-timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without creating outputs or starting Java")
    args = parser.parse_args()
    if args.stop_ns <= 0 or args.host_timeout <= 0:
        parser.error("Positive execution bounds are required")
    if args.out.exists():
        parser.error("Output directory must be new; existing evidence is preserved")
    if not args.dry_run:
        args.out.mkdir(parents=True, exist_ok=False)
    for name, movie in JOBS:
        destination = args.out.resolve() / name
        command = [sys.executable, str(Path(__file__).with_name("run_stock_replay.py")),
                   "--jar", str(args.jar.resolve()), "--library", str(args.library.resolve()),
                   "--movie", str(args.movies_root.resolve() / (movie + ".jrsr")),
                   "--out", str(destination), "--stop-ns", str(args.stop_ns),
                   "--host-timeout", str(args.host_timeout)]
        print(json.dumps({"job": name, "event": "dry_run" if args.dry_run else "starting",
                          "command": command}), flush=True)
        if args.dry_run:
            continue
        subprocess.run(command, check=True)
        result = json.loads((destination / "replay-result.json").read_text())
        if not (result["movie_unchanged"] and result["jar_unchanged"] and result["capture"]):
            raise RuntimeError("Replay inputs changed or capture missing")
        print(json.dumps({"job": name, "event": "verified_immutable_inputs",
                          "host_ns": result["elapsed_host_ns"]}), flush=True)


if __name__ == "__main__":
    main()
