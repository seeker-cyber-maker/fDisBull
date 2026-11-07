#!/usr/bin/env python3
"""Rebuild the authored DESQview companion with GNU binutils, without originals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def build(source, output):
    source = Path(source).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='fdisbull-desqview-build-') as directory:
        root = Path(directory)
        obj, elf, binary = (root / name for name in ('probe.o','probe.elf','probe.com'))
        subprocess.run(['as','--32','-o',str(obj),str(source)], check=True, timeout=30)
        subprocess.run(['ld','-m','elf_i386','-Ttext','0x100','-e','_start','-o',str(elf),str(obj)], check=True, timeout=30)
        subprocess.run(['objcopy','-O','binary','-j','.text',str(elf),str(binary)], check=True, timeout=30)
        symbols = subprocess.check_output(['nm','-n',str(elf)], text=True, timeout=30)
        labels = {row.split()[2]:int(row.split()[0],16) for row in symbols.splitlines() if len(row.split()) == 3}
        program = binary.read_bytes()
    report = labels['report'] - 0x100
    mode = labels['output_mode'] - 0x100
    if (report < 0 or report + 64 != len(program) or program[report:report+8] != b'FDVAPI01'
            or not 0 <= mode < report or program[mode] != 0 or len(program) > 0xff00):
        raise ValueError('Authored probe build has inconsistent extents')
    result = dict(format='fdisbull-desqview-probe-1', source=source.name,
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  program_sha256=hashlib.sha256(program).hexdigest(), program_hex=program.hex(),
                  mode_file_offset=mode, report_com_offset=labels['report'], report_length=64,
                  ready_com_offset=labels['report_ready'], release_com_offset=labels['release_request'])
    Path(output).write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    data = Path(__file__).resolve().parents[1] / 'src/fdisbull/data'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=data/'FdisbullDesqviewProbe.txt')
    parser.add_argument('--output',type=Path,default=data/'desqview-probe.json')
    args = parser.parse_args()
    build(args.source,args.output)
