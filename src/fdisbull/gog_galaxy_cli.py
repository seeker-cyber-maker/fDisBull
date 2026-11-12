"""Projectless command line for caller-captured GOG Galaxy wrapper rebuilding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .gog_galaxy import rebuild_galaxy_files


def _json_file(path):
    selected = Path(path)
    if not selected.is_file() or selected.stat().st_size > 1024 * 1024:
        raise ValueError("decisions JSON must be a file at most 1 MiB")
    try:
        document = json.loads(selected.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid decisions JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("decisions JSON must be an object")
    return document


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("wrapper", help="owned local Galaxy UPX wrapper")
    command.add_argument("mapped_image", help="caller-captured mapped PE image")
    command.add_argument("capture", help="fdisbull-chimprec-capture-1 JSON receipt")
    command.add_argument("exports", help="captured loaded-module export JSON")
    command.add_argument("output", help="new private output directory")
    command.add_argument("--candidate-slot", dest="candidate_slots", action="append",
                         type=lambda value: int(value, 0),
                         help="repeatable virtual address of an original IAT cell")
    command.add_argument("--decisions", help="JSON thunk-decision object")
    command.add_argument("--max-slots", type=int, default=4096)
    command.add_argument("--gap-limit", type=int, default=10)
    command.add_argument("--keep-relocations", dest="fixed_base", action="store_false",
                         help="retain existing relocation/ASLR metadata")
    command.set_defaults(fixed_base=True)
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        decisions = _json_file(args.decisions) if args.decisions else None
        result = rebuild_galaxy_files(
            args.wrapper, args.mapped_image, args.capture, args.exports, args.output,
            candidate_slots=args.candidate_slots, decisions=decisions,
            max_slots=args.max_slots, gap_limit=args.gap_limit,
            fixed_base=args.fixed_base,
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"complete": False, "status": "refused", "error": str(error)},
                         separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps({"complete": True, "status": "success", **result},
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
