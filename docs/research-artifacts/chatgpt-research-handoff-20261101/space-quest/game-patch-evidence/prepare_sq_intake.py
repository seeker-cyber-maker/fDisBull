#!/usr/bin/env python3
"""Prepare the exact SQ1 patch and installer, without requiring Ultima.

Output is private licensed game data; keep it outside Git. Windows code is not
executed. This adapter uses the same extraction functions as the recorded intake.
"""
from pathlib import Path
import argparse
import sys
import tempfile
import bootstrap_intake as b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    b.INPUTS = {k: b.INPUTS[k] for k in ('patch', 'space_quest')}
    with tempfile.TemporaryDirectory(prefix='sq1-inputs-') as temporary:
        stage = Path(temporary)
        for name in b.INPUTS.values():
            source = (args.input_dir / name).resolve(strict=True)
            (stage / name).symlink_to(source)
        sys.argv = [sys.argv[0], '--input-dir', str(stage), '--output-dir', str(root / 'intake')]
        return b.main()


if __name__ == '__main__':
    raise SystemExit(main())
