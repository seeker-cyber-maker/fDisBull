#!/usr/bin/env python3
"""Replay the bounded study in a NEW private workspace with user-owned inputs.

No downloading, package installation, repository writes, or complete game launch.
The generated source-retaining COM files must remain private.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCES = {
    'VICEROY.EXE': 'a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3',
    'COLONIZE.EXE': 'ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650',
}


def sha(path: Path) -> str:
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dos', type=Path, required=True)
    parser.add_argument('--windows', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True,
                        help='Compatible native DOSBox wrapper from the supplied offline kit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.expanduser().resolve()
    try:
        if out.exists():
            raise ValueError('output must not exist; earlier evidence is never overwritten')
        if any((parent / '.git').exists() for parent in (out, *out.parents)):
            raise ValueError('use a private workspace outside a Git checkout')
        version = importlib.metadata.version('fdisbull')
        if version != '0.30.0':
            raise ValueError(f'this replay is pinned to fdisbull 0.30.0, found {version}')
        for package in ('z3-solver', 'capstone'):
            importlib.metadata.version(package)
        for tool in ('as', 'ld', 'node', '/usr/bin/gcc'):
            if not shutil.which(tool):
                raise ValueError(f'required tool not found: {tool}')
        backend = args.backend.expanduser().resolve(strict=True)
        if not backend.is_file() or not os.access(backend, os.X_OK):
            raise ValueError('backend must be an executable file')
        selected = {'VICEROY.EXE': args.dos.expanduser().resolve(strict=True),
                    'COLONIZE.EXE': args.windows.expanduser().resolve(strict=True)}
        for name, path in selected.items():
            if not path.is_file() or sha(path) != SOURCES[name]:
                raise ValueError(f'unsupported source identity: {name}')
        out.mkdir(parents=True, exist_ok=False)
        (out / 'tools').mkdir()
        (out / 'private').mkdir()
        (out / 'deliverable/results').mkdir(parents=True)
        (out / 'logs').mkdir()
        for name, path in selected.items():
            shutil.copy2(path, out / 'private' / name)
        scripts = ('build_uil.py', 'new_native.py', 'check_comparison.py',
                   'prove_models.py', 'check_native_udc.py')
        for script in scripts:
            shutil.copy2(HERE / script, out / 'tools' / script)
        steps = [
            ['new_native.py', '--backend', str(backend)],
            ['build_uil.py'], ['check_comparison.py'],
            ['prove_models.py'], ['check_native_udc.py'],
        ]
        receipt = {'runtime': version, 'source_hashes': SOURCES,
                   'scope': 'isolated x86-16 source closures and corresponding UIL/UDC',
                   'steps': []}
        for step in steps:
            command = [sys.executable, str(out / 'tools' / step[0]), *step[1:]]
            print('Running', step[0], flush=True)
            with (out / 'logs' / (step[0] + '.log')).open('w') as log:
                process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                         timeout=300, cwd=out)
            receipt['steps'].append({'script': step[0], 'returncode': process.returncode})
            (out / 'REPLAY.json').write_text(json.dumps(receipt, indent=2) + '\n')
            if process.returncode:
                raise RuntimeError(f'{step[0]} failed; preserve and inspect {out / "logs"}')
        for name, path in selected.items():
            if sha(path) != SOURCES[name]:
                raise RuntimeError(f'original source changed during replay: {name}')
        receipt['complete'] = True
        (out / 'REPLAY.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print('Completed. Keep source-retaining artifacts in', out / 'private')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            importlib.metadata.PackageNotFoundError) as exc:
        parser.exit(1, f'Replay incomplete: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
