import copy
import hashlib
from pathlib import Path

import pytest

from fdisbull.ghidra_asm_c import render_ghidra_asm_c
from fdisbull.udl_blocks import lift_asm_block, lift_c_block

HEADLESS = Path('/opt/homebrew/Cellar/ghidra/12.2/libexec/support/analyzeHeadless')
JAVA = Path('/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home')


def block(code):
    return lift_asm_block(bytes.fromhex(code), {'ax': '$a', 'bx': '$b'},
                          inputs=['ax', 'bx'], outputs=['ax', 'bx'])


def test_invalid_lift_is_rejected_before_launch():
    lift = block('b8341240')
    lift['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        render_ghidra_asm_c(lift, analyze_headless='/does/not/exist')
    with pytest.raises(ValueError, match='ASM lift'):
        render_ghidra_asm_c({}, analyze_headless='/does/not/exist')


def test_unavailable_backend_fails_without_fallback():
    with pytest.raises(ValueError, match='analyze_headless path'):
        render_ghidra_asm_c(block('40'), analyze_headless=None)
    with pytest.raises(RuntimeError, match='could not start'):
        render_ghidra_asm_c(block('40'), analyze_headless='/does/not/exist')


@pytest.mark.skipif(not HEADLESS.exists() or not JAVA.exists(), reason='optional Ghidra 12.2 installation unavailable')
@pytest.mark.parametrize('code,expected', [
    ('b834124005010048', ['ax = 4660;', 'ax += 1;', 'ax += 1;', 'ax -= 1;']),
    ('2d0200', ['ax -= 2;']),
    ('05c80048', ['ax += 200;', 'ax -= 1;']),
])
def test_real_ghidra_facts_and_c_subset(code, expected):
    lift = block(code)
    before = copy.deepcopy(lift)
    result = render_ghidra_asm_c(lift, analyze_headless=HEADLESS, java_home=JAVA)
    assert result['text'].splitlines() == expected
    assert result['ghidra_version'] == '12.2'
    assert result['diagnostics']['decompile_completed'] is True
    assert 'fdisbull_block' in result['ghidra_c']
    wrapper = result['diagnostics']['synthetic_wrapper']
    assert wrapper['offset'] == len(bytes.fromhex(code))
    assert wrapper['header_format'] == 'DOS MZ'
    assert wrapper['header_size'] == 32
    assert bytes.fromhex(wrapper['header_bytes']).startswith(b'MZ')
    if code == '2d0200':
        assert 'in_AX' in result['ghidra_c']
        assert '-2' in result['ghidra_c']
    assert result['source_sha256'] == hashlib.sha256(bytes.fromhex(code)).hexdigest()
    assert result['diagnostics']['covered_bytes'] == len(bytes.fromhex(code))
    assert sum(item['size'] for item in result['evidence']) == len(bytes.fromhex(code))
    assert lift == before
    c_lift = lift_c_block(result['text'], lift['bindings'], inputs=lift['inputs'], outputs=lift['outputs'])
    assert c_lift['uil']['body'] == lift['uil']['body']


def test_incomplete_ghidra_protocol_fails_closed(monkeypatch):
    def incomplete(cmd, **kwargs):
        Path(cmd[-2]).write_text('VERSION\t12.2\n', encoding='utf-8')
        return type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

    monkeypatch.setattr('fdisbull.ghidra_asm_c.subprocess.run', incomplete)
    with pytest.raises(RuntimeError, match='facts are incomplete'):
        render_ghidra_asm_c(block('2d0200'), analyze_headless='/fake/headless')
