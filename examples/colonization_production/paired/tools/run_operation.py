#!/usr/bin/env python3
"""Execute one delivered semantic operation. Does not run an original game."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from fdisbull.common_uil import digest
from fdisbull.uil_runtime import execute_program

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('input_balance', 'net_production', 'capacity_from_level',
         'stock_available', 'packed_slot_read', 'production_input_pipeline',
         'comparison_suite')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edition', choices=('dos', 'win'), required=True)
    parser.add_argument('--operation', choices=NAMES, required=True)
    parser.add_argument('--inputs', required=True, help='JSON list, in labels.json input order')
    args = parser.parse_args()
    try:
        folder = ROOT / 'representations' / args.edition
        program = json.loads((folder / 'program.uil.json').read_text())
        presentation = json.loads((folder / 'presentation.json').read_text())
        labels = json.loads((folder / 'labels.json').read_text())[args.operation]
        inputs = json.loads(args.inputs)
        program['entry'] = NAMES.index(args.operation)
        presentation['program_sha256'] = digest(program)
        result = execute_program(program, presentation, inputs=inputs)
        print(json.dumps({'edition': args.edition, 'operation': args.operation,
                          'ports': labels, 'result': result}, indent=2))
        return 0 if result['status'] == 'complete' else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'Operation not executed: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
