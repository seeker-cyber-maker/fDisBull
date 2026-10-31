"""Build the Civ I world snapshot artifacts from a private save pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from civ_world import read_world, render_ascii, render_html, render_svg, summarize


def build(sve: Path, map_file: Path, out_dir: Path, *, edition: str) -> dict:
    world = read_world(sve, map_file, edition=edition)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "world.json").write_text(json.dumps(world, separators=(",", ":")))
    (out_dir / "world.txt").write_text(render_ascii(world))
    (out_dir / "world.html").write_text(render_html(world))
    (out_dir / "world.svg").write_text(render_svg(world))
    summary = summarize(world)
    (out_dir / "world-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-dir", type=Path, help="directory containing CIVIL0.SVE and CIVIL0.MAP"
    )
    parser.add_argument("--sve", type=Path)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--out", type=Path, default=Path("generated"))
    parser.add_argument("--edition", default="unknown")
    args = parser.parse_args()
    sve = args.sve or (args.save_dir / "CIVIL0.SVE" if args.save_dir else None)
    map_file = args.map or (args.save_dir / "CIVIL0.MAP" if args.save_dir else None)
    if sve is None or map_file is None:
        parser.error("provide --save-dir or both --sve and --map")
    summary = build(sve, map_file, args.out, edition=args.edition)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
