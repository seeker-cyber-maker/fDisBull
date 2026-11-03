"""Public CHimpREC PE parsing, OEP evidence and reconstruction interface.

The implementation is split into bounded image, import and writer modules.
This facade preserves one public import surface and the ``python -m`` CLI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chimprec_pe_image import find_oep_transfers, map_pe_file, parse_pe
from .chimprec_pe_imports import parse_imports
from .chimprec_pe_writer import rebuild_pe_image

def rebuild_pe_file(source: Path, capture: Path, plan: Path, output: Path, *,
                    entry_rva: int, section_name: str = ".reimp", fixed_base: bool = True) -> dict:
    """Path-based wrapper that refuses overwrites and writes a receipt beside output."""
    source, capture, plan, output = map(Path, (source, capture, plan, output))
    if output.exists():
        raise FileExistsError(output)
    document = json.loads(plan.read_text(encoding="utf-8"))
    rebuilt, receipt = rebuild_pe_image(source.read_bytes(), capture.read_bytes(), document,
                                        entry_rva=entry_rva, section_name=section_name,
                                        fixed_base=fixed_base,
                                        capture_metadata=document.get("capture_metadata"))
    output.write_bytes(rebuilt)
    receipt_path = output.with_suffix(output.suffix + ".chimprec.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "output": str(output), "receipt": str(receipt_path)}


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original packed PE container")
    parser.add_argument("capture", type=Path, help="coherent mapped image bytes, RVA zero at file offset zero")
    parser.add_argument("plan", type=Path, help="reviewed chimprec-import-plan-1 JSON")
    parser.add_argument("output", type=Path, help="new output path; must not exist")
    parser.add_argument("--entry-rva", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--section-name", default=".reimp")
    args = parser.parse_args(argv)
    result = rebuild_pe_file(args.source, args.capture, args.plan, args.output,
                             entry_rva=args.entry_rva, section_name=args.section_name)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
