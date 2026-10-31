import copy
import hashlib
from pathlib import Path

import pytest

from fdisbull.dcc_asm_c import _listing_facts, render_dcc_asm_c
from fdisbull.udl_blocks import lift_asm_block, lift_c_block

DCC = Path('/Volumes/CODEX/Codex_Projects/Civd-intake/decompiler-comparison/dcc/source/dcc_original')


def block(code):
    return lift_asm_block(bytes.fromhex(code), {'ax': '$a', 'bx': '$b'},
                          inputs=['ax', 'bx'], outputs=['ax', 'bx'])


@pytest.mark.skipif(not DCC.is_file(), reason='optional local DCC executable unavailable')
@pytest.mark.parametrize('code,expected', [
    ('b834124005010048', ['ax = 4660;', 'ax += 1;', 'ax += 1;', 'ax -= 1;']),
    ('2d0200', ['ax -= 2;']),
    ('05c80048', ['ax += 200;', 'ax -= 1;']),
    ('bbffff43', ['bx = 65535;', 'bx += 1;']),
])
def test_real_dcc_listing_and_native_c(code, expected):
    lift = block(code)
    before = copy.deepcopy(lift)
    result = render_dcc_asm_c(lift, executable=DCC)
    assert result['text'].splitlines() == expected
    assert result['source_sha256'] == hashlib.sha256(bytes.fromhex(code)).hexdigest()
    assert result['diagnostics']['covered_bytes'] == len(bytes.fromhex(code))
    assert sum(x['size'] for x in result['evidence']) == len(bytes.fromhex(code))
    assert 'void start' in result['native_c']
    assert 'not parsed from native C' in result['diagnostics']['text_provenance']
    assert lift == before
    c = lift_c_block(result['text'], lift['bindings'], inputs=lift['inputs'], outputs=lift['outputs'])
    assert c['uil']['body'] == lift['uil']['body']


def test_dec_comes_from_listing_and_interrupt_is_not_modeled():
    listing = '000 000100 48 DEC ax\n001 000101 C3 RET\n'
    assert _listing_facts(listing, b'\x48')[0] == ['ax -= 1;']
    with pytest.raises(ValueError, match='unsupported DCC instruction'):
        _listing_facts('000 000100 CD21 INT 21h\n001 000102 C3 RET\n', b'\xcd\x21')


@pytest.mark.parametrize('listing', [
    '',
    '000 000100 40 INC ax\n',
    '000 000101 40 INC ax\n001 000102 C3 RET\n',
    '000 000100 41 INC cx\n001 000101 C3 RET\n',
    '000 000100 40 INC ax\n001 000101 90 NOP\n',
    '000 000100 40 INC ax\n001 000101 C3 RET\n002 000102 C3 RET\n',
])
def test_bad_listing_fails_closed(listing):
    with pytest.raises(ValueError):
        _listing_facts(listing, b'\x40')


def test_invalid_lift_and_unavailable_executable():
    lift = block('40')
    lift['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        render_dcc_asm_c(lift, executable='/missing')
    with pytest.raises(ValueError, match='ASM lift'):
        render_dcc_asm_c({}, executable='/missing')
    with pytest.raises(RuntimeError, match='could not start'):
        render_dcc_asm_c(block('40'), executable='/missing')


def test_missing_listing_fails_closed(monkeypatch):
    monkeypatch.setattr('fdisbull.dcc_asm_c.subprocess.run',
                        lambda *a, **k: type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})())
    with pytest.raises(RuntimeError, match='no instruction listing'):
        render_dcc_asm_c(block('40'), executable='/fake')


def test_missing_native_output_fails_closed(monkeypatch):
    def fake_run(args, **kwargs):
        if '-a' in args:
            Path(args[args.index('-o') + 1]).write_text(
                '000 000100 40 INC ax\n001 000101 C3 RET\n', encoding='utf-8')
        return type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    monkeypatch.setattr('fdisbull.dcc_asm_c.subprocess.run', fake_run)
    with pytest.raises(RuntimeError, match='no native C'):
        render_dcc_asm_c(block('40'), executable='/fake')


def test_timeout_fails_closed(monkeypatch):
    import subprocess
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)
    monkeypatch.setattr('fdisbull.dcc_asm_c.subprocess.run', timeout)
    with pytest.raises(RuntimeError, match='timed out'):
        render_dcc_asm_c(block('40'), executable='/fake')
