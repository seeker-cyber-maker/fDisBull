#!/usr/bin/env python3
"""Rebuild the authored DOS helper asset with GNU binutils (no target inputs)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def build(source, output):
    source = Path(source).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='fdisbull-qpi-build-') as temporary:
        root = Path(temporary)
        obj, elf, binary = (root / name for name in ('probe.o', 'probe.elf', 'probe.com'))
        subprocess.run(['as', '--32', '-o', str(obj), str(source)], check=True, timeout=30)
        subprocess.run(['ld', '-m', 'elf_i386', '-Ttext', '0x100', '-e', '_start',
                        '-o', str(elf), str(obj)], check=True, timeout=30)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(elf), str(binary)],
                       check=True, timeout=30)
        symbols = subprocess.check_output(['nm', '-n', str(elf)], text=True, timeout=30)
        addresses = {row.split()[2]: int(row.split()[0], 16)
                     for row in symbols.splitlines() if len(row.split()) == 3}
        program = binary.read_bytes()
    report_offset, mode_offset = (addresses[name] - 0x100 for name in ('report', 'output_mode'))
    assert program[report_offset:report_offset + 8] == b'FDQPI001'
    assert program[mode_offset] == 0
    assert len(program) == report_offset + 1120 and len(program) < 0xff00
    record = dict(format='fdisbull-qpi-probe-1', source='FdisbullQpiProbe.txt',
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  program_sha256=hashlib.sha256(program).hexdigest(),
                  program_hex=program.hex(), mode_file_offset=mode_offset,
                  report_com_offset=report_offset + 0x100, report_length=1120,
                  ready_com_offset=addresses['report_ready'],
                  release_com_offset=addresses['release_request'])
    Path(output).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / 'src/fdisbull/data'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=root / 'FdisbullQpiProbe.txt')
    parser.add_argument('--output', default=root / 'qpi-probe.json')
    args = parser.parse_args()
    build(args.source, args.output)
