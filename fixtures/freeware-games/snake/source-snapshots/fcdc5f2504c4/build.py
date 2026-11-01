#!/usr/bin/env python3
"""Build the authored Snake original using an explicit period toolchain.

Output directories must be new. Nothing is installed or written to the tools.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source, tools, emulator, output):
    source, tools, emulator = (Path(p).resolve(strict=True) for p in (source, tools, emulator))
    output = Path(output).resolve()
    pins = {name: sha(tools / 'BIN' / (name + '.EXE')) for name in ('MASM', 'LINK')}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'SNAKE.ASM').write_bytes(source.read_bytes())
    batch = ['@echo off', 'set PATH=C:\\BIN;Z:\\',
             'masm SNAKE.ASM,SNAKE.OBJ,SNAKE.LST; >ASM.LOG',
             'if errorlevel 1 goto failed',
             'link /MAP SNAKE.OBJ,SNAKE.EXE,SNAKE.MAP; >LINK.LOG',
             'if errorlevel 1 goto failed', 'echo 0>EXIT.TXT', 'goto done',
             ':failed', 'echo 1>EXIT.TXT', ':done']
    (output / 'BUILD.BAT').write_bytes(('\r\n'.join(batch) + '\r\n').encode('ascii'))
    (output / 'build.conf').write_text('[sdl]\noutput=surface\n[cpu]\ncore=normal\ncycles=100000\n[mixer]\nnosound=true\n')
    command = [str(emulator), '-defaultconf', '-defaultmapper', '-silent', '-fastlaunch',
               '-conf', str(output / 'build.conf'), '-nopromptfolder', '-nolog',
               '-time-limit', '40', '-c', f'mount c "{tools}"',
               '-c', f'mount d "{output}"', '-c', 'd:', '-c', 'call BUILD.BAT', '-c', 'exit']
    with (output / 'dosbox.log').open('wb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                env=dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy'),
                                timeout=50)
    assert {name: sha(tools / 'BIN' / (name + '.EXE')) for name in pins} == pins, 'Tool bytes changed'
    if result.returncode or not (output / 'EXIT.TXT').exists() or (output / 'EXIT.TXT').read_text().strip() != '0':
        raise RuntimeError(f'Build failed; inspect {output}/ASM.LOG and LINK.LOG')
    assert (output / 'SNAKE.EXE').read_bytes()[:2] == b'MZ'
    receipt = dict(format='fdisbull-authored-fixture-build-1', source_sha256=sha(source),
                   source=str(source), tool_sha256=pins, emulator=str(emulator),
                   emulator_sha256=sha(emulator), command=command, returncode=result.returncode,
                   artifacts={name: dict(bytes=(output / name).stat().st_size, sha256=sha(output / name))
                              for name in ('SNAKE.ASM', 'SNAKE.EXE', 'SNAKE.OBJ', 'SNAKE.LST', 'SNAKE.MAP')})
    (output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path(__file__).with_name('SNAKE.ASM'))
    p.add_argument('--tools', type=Path, required=True, help='Compiler folder containing BIN/MASM.EXE and BIN/LINK.EXE')
    p.add_argument('--dosbox', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.source, a.tools, a.dosbox, a.output)
