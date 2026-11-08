"""Repeat a cold structural scan on caller-selected extracted directories.

No target titles, offsets, expected layouts, or private payloads are embedded.
All reports are private; timings measure scanning, not agent investigation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import stat
from fdisbull.structure_discovery import scan_to_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 5:
        parser.error('--repeat must be in 1..5')
    out = args.output
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        parser.error('output must be new with an existing private parent')
    resolved = out.parent.resolve()
    if any((p / '.git').exists() for p in (resolved, *resolved.parents)):
        parser.error('reports must stay outside Git')
    if any(p.is_symlink() for p in (out.parent, *out.parent.parents)):
        parser.error('output parent may not contain symlinks')
    for root in args.inputs:
        r = root.resolve()
        if root.is_symlink() or not root.is_dir() or resolved == r or r in resolved.parents:
            parser.error('inputs must be directories; output cannot be inside an input')
    out.mkdir(mode=0o700)
    rows = []
    for index, root in enumerate(args.inputs):
        receipts = []
        for repeat in range(args.repeat):
            result = scan_to_directory(root, out / f'input-{index + 1}-run-{repeat + 1}')
            receipts.append(result['receipt'])
        identical = len({r['report_sha256'] for r in receipts}) == 1
        rows.append({'input_index': index + 1, 'runs': receipts,
                     'reports_identical': identical, 'runtime_observed': False})
    receipt = out / 'corpus.json'
    receipt.write_text(json.dumps({'inputs': rows}, indent=2) + '\n', encoding='utf-8')
    receipt.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(json.dumps({'receipt': str(receipt), 'all_identical': all(r['reports_identical'] for r in rows)}))
    return 0 if all(r['reports_identical'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
