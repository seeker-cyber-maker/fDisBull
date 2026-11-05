#!/usr/bin/env python3
"""Prepare opt-in hooks in one exact, caller-owned ScummVM checkout.

Default: validate and print the unified diff. --apply uses git apply after its
check succeeds. No download, build, network, installation or implicit launch.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess
import sys

UPSTREAM = '750f2373fb100efe08c6444e36b68c01387fc307'
BLOBS = {
    'engines/glk/zcode/mem.cpp': 'd44c235d7afc7cb1f8c42ed1252122542697deb1',
    'engines/glk/zcode/glk_interface.cpp': '6e23f8dbcfb29949c433f3f241736908d00a66f9',
    'engines/glk/zcode/processor_screen.cpp': '8f0af40aa616dd396f655b08b4d99eb3d08f8624',
    'engines/glk/zcode/zcode.cpp': '2df3dc3d3acc4447a12f1c259dc09bcb8d953c19',
}
INCLUDE = '''#if defined(FDISBULL_ZCODE_AGENT)
#define FORBIDDEN_SYMBOL_ALLOW_ALL
#include "glk/zcode/fdisbull_agent.h"
#endif

'''


def one(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f'Expected one exact source anchor: {before[:90]!r}')
    return text.replace(before, after)


def transform(path: str, text: str) -> str:
    if 'FDisBullZCode' in text or 'fdisbull_agent.h' in text:
        raise ValueError('Source is already instrumented')
    # Place system headers before ScummVM forbidden-symbol macros.
    start = text.index('#include ')
    text = text[:start] + INCLUDE + text[start:]
    if path.endswith('/mem.cpp'):
        text = one(text, '\tloadMemory();\n', '''\tloadMemory();
#if defined(FDISBULL_ZCODE_AGENT)
\tFDisBullZCode::agent().loaded(zmp, story_size);
#endif
''')
    elif path.endswith('/processor.cpp'):
        text = one(text, 'void Processor::interpret() {\n\tdo {\n', '''void Processor::interpret() {
\tdo {
#if defined(FDISBULL_ZCODE_AGENT)
\t\tconst FDisBullZCode::Number fdbSpan = FDisBullZCode::agent().before(getPC());
#endif
''')
        text = one(text, '#if defined(DJGPP) && defined(SOUND_SUPPORT)\n', '''#if defined(FDISBULL_ZCODE_AGENT)
\t\tFDisBullZCode::agent().after(fdbSpan, getPC());
#endif
#if defined(DJGPP) && defined(SOUND_SUPPORT)
''')
    elif path.endswith('/glk_interface.cpp'):
        anchor = 'zchar GlkInterface::os_read_line(int max, zchar *buf, int timeout, int width, int continued) {\n'
        text = one(text, anchor, anchor + '''#if defined(FDISBULL_ZCODE_AGENT)
\tif (FDisBullZCode::agent().enabled()) {
\t\tconst std::string input = FDisBullZCode::agent().input("line", max, timeout, continued);
\t\tfor (size_t i = 0; i < input.size(); ++i) buf[i] = static_cast<unsigned char>(input[i]);
\t\tbuf[input.size()] = 0;
\t\treturn ZC_RETURN;
\t}
#endif
''')
        anchor = 'zchar GlkInterface::os_read_key(int timeout, bool show_cursor) {\n'
        text = one(text, anchor, anchor + '''#if defined(FDISBULL_ZCODE_AGENT)
\tif (FDisBullZCode::agent().enabled())
\t\treturn static_cast<unsigned char>(FDisBullZCode::agent().input("char", 1, timeout)[0]);
#endif
''')
    elif path.endswith('/processor_screen.cpp'):
        anchor = 'void Processor::screen_char(zchar c) {\n'
        text = one(text, anchor, anchor + '''#if defined(FDISBULL_ZCODE_AGENT)
\tif (FDisBullZCode::agent().enabled()) {
\t\tFDisBullZCode::agent().character(c, _wp._cwin);
\t\treturn; // Declared text-only host: no pixel/UI equivalence.
\t}
#endif
''')
    elif path.endswith('/zcode.cpp'):
        text = one(text, '\t// Game loop\n\tinterpret();\n', '''\t// Game loop
\tinterpret();
#if defined(FDISBULL_ZCODE_AGENT)
\tif (FDisBullZCode::agent().enabled()) {
\t\tflush_buffer();
\t\tFDisBullZCode::agent().exited(getPC());
\t}
#endif
''')
    else:
        raise ValueError(f'No hook transformation for {path}')
    return text


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def prepare(source: Path) -> str:
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != UPSTREAM:
        raise ValueError(f'Expected upstream {UPSTREAM}, got {head}')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Source checkout must be clean, including untracked files')
    chunks = []
    paths = sorted([*BLOBS, 'engines/glk/zcode/processor.cpp'])
    for path in paths:
        file = source / path
        if file.is_symlink() or not file.is_file():
            raise ValueError(f'Expected regular source file: {path}')
        data = file.read_bytes()
        expected = BLOBS.get(path)
        # Exact upstream Git object guards the processor file as well; a pinned
        # clean tree is required even for files whose blob is not duplicated here.
        committed = subprocess.check_output(['git', '-C', str(source), 'show', f'{UPSTREAM}:{path}'])
        if data != committed or expected and blob(data) != expected:
            raise ValueError(f'Upstream source identity differs: {path}')
        old = data.decode('utf-8')
        new = transform(path, old)
        chunks.append(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                   fromfile='a/'+path, tofile='b/'+path)))
    target = 'engines/glk/zcode/fdisbull_agent.h'
    if (source / target).exists():
        raise ValueError('Agent header already exists')
    header = (Path(__file__).resolve().parent / 'agent.h').read_text()
    chunks.append(''.join(difflib.unified_diff([], header.splitlines(True),
                                               fromfile='/dev/null', tofile='b/'+target)))
    return ''.join(chunks)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    source = args.source.resolve(strict=True)
    patch = prepare(source)
    subprocess.run(['git', '-C', str(source), 'apply', '--check', '-'], input=patch, text=True, check=True)
    if args.apply:
        subprocess.run(['git', '-C', str(source), 'apply', '-'], input=patch, text=True, check=True)
        print('Applied native GLK/ZCode hooks; compile and real-game verification still required.')
    else:
        sys.stdout.write(patch)


if __name__ == '__main__':
    main()
