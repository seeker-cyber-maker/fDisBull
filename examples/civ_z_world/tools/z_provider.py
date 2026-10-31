"""Read-only JSON provider for the Civ I Z world snapshot.

No guest process, input or memory write is involved. The save pair is opened
read-only and the world is a bounded observation, not a playable scene.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from civ_world import read_world, summarize


def observe(
    sve: Path, map_file: Path, *, edition: str, summary_only: bool = False
) -> dict:
    world = read_world(sve, map_file, edition=edition)
    return summarize(world) if summary_only else world


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-dir", type=Path)
    parser.add_argument("--sve", type=Path)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--edition", default="unknown")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sve = args.sve or (args.save_dir / "CIVIL0.SVE" if args.save_dir else None)
    map_file = args.map or (args.save_dir / "CIVIL0.MAP" if args.save_dir else None)
    if sve is None or map_file is None:
        parser.error("provide --save-dir or both --sve and --map")
    result = observe(sve, map_file, edition=args.edition, summary_only=args.summary)
    text = json.dumps(result, separators=(",", ":"))
    if args.out:
        args.out.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
