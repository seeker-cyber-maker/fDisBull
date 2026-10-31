import copy
import hashlib
from pathlib import Path

import pytest

from fdisbull.reko_asm_c import render_reko_asm_c
from fdisbull.udl_blocks import lift_asm_block, lift_c_block

BASE = Path('/Volumes/CODEX/Codex_Projects/Civd-intake/decompiler-comparison/reko/official')
REKO = BASE / 'dist/reko.dll'
DOTNET = BASE / 'dotnet-x64/dotnet'


def block(code):
    return lift_asm_block(bytes.fromhex(code), {'ax': '$a', 'bx': '$b'},
                          inputs=['ax', 'bx'], outputs=['ax', 'bx'])


def test_rejects_digest_before_launch():
    lift = block('40')
    lift['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        render_reko_asm_c(lift, executable='/missing')


@pytest.mark.skipif(not REKO.exists() or not DOTNET.exists(), reason='optional Reko installation unavailable')
@pytest.mark.parametrize('code,expected', [
    ('b834124005010048', ['ax = 4660;', 'ax += 1;', 'ax += 1;', 'ax -= 1;']),
    ('2d0200', ['ax -= 2;']),
    ('bbffff434b', ['bx = 65535;', 'bx += 1;', 'bx -= 1;']),
])
def test_real_reko(code, expected):
    lift = block(code)
    before = copy.deepcopy(lift)
    result = render_reko_asm_c(lift, executable=REKO, dotnet=DOTNET)
    assert result['text'].splitlines() == expected
    assert result['source_sha256'] == hashlib.sha256(bytes.fromhex(code)).hexdigest()
    assert result['diagnostics']['covered_bytes'] == len(bytes.fromhex(code))
    assert result['native_c'].strip()
    assert lift_c_block(result['text'], lift['bindings'], inputs=lift['inputs'],
                        outputs=lift['outputs'])['uil']['body'] == lift['uil']['body']
    assert lift == before


def test_incomplete_protocol_fails_closed(monkeypatch):
    def incomplete(cmd, **kwargs):
        out = Path(kwargs['cwd']) / 'block.reko'
        out.mkdir()
        (out / 'block_code.asm').write_text(';;; Segment code (0C00:0100)\n')
        (out / 'block_code.c').write_text('void f() {}')
        return type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    monkeypatch.setattr('fdisbull.reko_asm_c.subprocess.run', incomplete)
    with pytest.raises(ValueError, match='cover'):
        render_reko_asm_c(block('40'), executable='/fake')
