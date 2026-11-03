"""Reproduce one pinned CivD build in a new private directory.

Supply an already prepared/hash-pinned period toolchain. Original targets are
read for comparison and never mounted in DOSBox. The upstream startup correction
operates only on generated files; both raw and corrected output are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source, tools, output, original, dosbox, timeout=180):
    source, tools, output, original = map(lambda p: Path(p).resolve(), (source, tools, output, original))
    if output.exists():
        raise ValueError('build destination must be new')
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    subprocess.run(['git', '-C', str(source), 'diff', '--no-ext-diff', '--quiet', 'HEAD', '--', 'src',
                    'dosbox.conf', 'civ.sha256', 'period-tools.sha256'], check=True)
    tool_checks = []
    for line in (source / 'period-tools.sha256').read_text().splitlines():
        digest, name = line.split()
        actual = sha(tools / name)
        if digest != actual:
            raise ValueError('period tool mismatch: ' + name)
        tool_checks.append(dict(path=name, sha256=actual))
    expected = dict((name, digest) for digest, name in
                    (line.split() for line in (source / 'civ.sha256').read_text().splitlines()))
    original_before = sha(original)
    if expected['CIV.EXE'] != original_before:
        raise ValueError('selected original differs from pinned CIV.EXE checksum')
    output.mkdir(parents=True)
    inputs = []
    paths = subprocess.check_output(['git', '-C', str(source), 'ls-files', 'src'], text=True).splitlines()
    for path in paths:
        src = source / path
        if src.suffix.upper() not in ('.C', '.H', '.ASM', '.INC', '.RSP') and src.name != 'MAKEFILE':
            continue
        raw = src.read_bytes()
        canonical = subprocess.check_output(['git', '-C', str(source), 'show', revision + ':' + path])
        if raw != canonical:
            raise ValueError('source bytes differ from pinned Git object: ' + path)
        shutil.copyfile(src, output / src.name)
        inputs.append(dict(path=path, sha256=sha(src)))
    batch = ('@echo off\r\nset PATH=C:\\BIN;Z:\\\r\nset INCLUDE=C:\\INCLUDE\r\n'
             'make MAKEFILE >MAKE.LOG\r\nif errorlevel 1 goto failed\r\n'
             'echo 0>EXIT.TXT\r\ngoto done\r\n:failed\r\necho 1>EXIT.TXT\r\n:done\r\n')
    (output / 'BUILD.BAT').write_bytes(batch.encode())
    command = [str(dosbox), '-defaultconf', '-defaultmapper', '-conf', str(source / 'dosbox.conf'),
               '-silent', '-fastlaunch', '-nopromptfolder', '-nolog', '-time-limit', str(timeout),
               '-c', f'mount c "{tools}"', '-c', f'mount d "{output}"',
               '-c', 'd:', '-c', 'call BUILD.BAT', '-c', 'exit']
    start = time.monotonic()
    with (output / 'dosbox.log').open('wb') as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy'),
                                 timeout=timeout + 30)
    diagnostics = []
    for log in sorted(output.glob('*.LOG')):
        for line in log.read_text(errors='replace').splitlines():
            if re.search(r'(?:fatal error|error)\s+[A-Z]\d{4}:|There were [1-9]\d* errors detected', line):
                diagnostics.append(dict(log=log.name, text=line))
    checks = [dict(path=name, expected=digest,
                   actual=sha(output / name) if (output / name).is_file() else None)
              for name, digest in expected.items()]
    for check in checks:
        check['match'] = check['actual'] == check['expected']
    success = (process.returncode == 0 and (output / 'EXIT.TXT').is_file()
               and (output / 'EXIT.TXT').read_text().strip() == '0'
               and not diagnostics and all(c['match'] for c in checks))
    raw, final = (output / 'CIVRAW.EXE').read_bytes(), (output / 'CIV.EXE').read_bytes()
    changes = [dict(file_offset=i, raw=a, corrected=b) for i, (a, b) in enumerate(zip(raw, final)) if a != b]
    if len(raw) != len(final) or len(changes) != 4:
        success = False
    toolchain_after = all(sha(tools / x['path']) == x['sha256'] for x in tool_checks)
    original_unchanged = sha(original) == original_before
    artifacts = [p for p in sorted(output.iterdir())
                 if p.suffix.upper() in ('.OBJ', '.COD', '.MAP', '.LOG', '.EXE', '.CVL')]
    receipt = dict(schema='fdisbull-civd-build-1', revision=revision, source_inputs=inputs,
                   toolchain=tool_checks, toolchain_unchanged=toolchain_after,
                   dosbox_sha256=sha(dosbox), config_sha256=sha(source / 'dosbox.conf'),
                   command=command, returncode=process.returncode, seconds=time.monotonic() - start,
                   diagnostics=diagnostics, outputs=checks, startup_correction=changes,
                   original_sha256=original_before, original_unchanged=original_unchanged,
                   artifacts=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in artifacts],
                   verified=success and toolchain_after and original_unchanged,
                   scope='Exact build result with an explicit four-byte generated startup correction; '
                         'no historical symbol-name or native gameplay claim.')
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    if not receipt['verified']:
        raise ValueError('build verification failed; inspect retained build-receipt.json and logs')
    print(json.dumps(dict(output=str(output), revision=revision, seconds=receipt['seconds'],
                          verified=True, changes=changes), indent=2))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'tools', 'output', 'original', 'dosbox'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    build(a.source, a.tools, a.output, a.original, a.dosbox)
