#!/usr/bin/env python3
"""Export only declared CI evidence from the guest and record source state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

SELECTIONS = ('dist/*', 'artifacts/receipts/*.json', 'artifacts/ordinary/*',
              'artifacts/recovery/*.json',
              '.native/chat/output/*',
              'native-evidence/**/*', '.native/backends/**/*', '.native/offline/output/*',
              '.native/pe/packages/*.whl', '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
              '.native/pe/linux-amd64', '.native/pe/runtime.cpio.gz',
              '.native/pe/oracle.exe', '.native/pe/dos-runtime.cpio.gz')


def export(work, output, expected_sha):
    work = work.resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha):
        raise ValueError('Invalid expected source SHA')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                     cwd=work, text=True)
    postcheck = {'source_commit': head, 'expected_source_commit': expected_sha,
                 'tracked_worktree_dirty': bool(status.strip()), 'export_success': False}
    error = None
    try:
        output.mkdir(parents=True, exist_ok=False)
        for pattern in SELECTIONS:
            for path in work.glob(pattern):
                relative = path.relative_to(work)
                if any((work / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
                    raise ValueError(f'Symlink in selected CI outputs: {relative}')
                if not path.is_file():
                    continue
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(path, target)
                    shutil.copymode(path, target)
        postcheck['export_success'] = True
        if head != expected_sha or status.strip():
            raise ValueError('Guest tracked source changed')
    except (OSError, ValueError) as exc:
        error = exc
    postcheck_path = output.parent / 'source-postcheck.json'
    with postcheck_path.open('x') as stream:
        json.dump(postcheck, stream, indent=2)
        stream.write('\n')
    if error is not None:
        raise error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    export(args.work, args.output, args.source_commit)


if __name__ == '__main__':
    main()
