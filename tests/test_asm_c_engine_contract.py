"""The public ASM-to-C boundary must be interchangeable across engines."""
import os
from pathlib import Path

import pytest

from fdisbull.udl_blocks import asm_to_c, lift_asm_block, qualify_asm_c_view


HEADLESS = Path('/opt/homebrew/Cellar/ghidra/12.2/libexec/support/analyzeHeadless')
JAVA = Path('/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home')
REKO_ROOT = Path('/Volumes/CODEX/Codex_Projects/Civd-intake/decompiler-comparison/reko/official')
DCC = Path('/Volumes/CODEX/Codex_Projects/Civd-intake/decompiler-comparison/dcc/source/dcc_original')


def _lift():
    return lift_asm_block(bytes.fromhex('05c80048'), {'ax': '$result'},
                          inputs=['ax'], outputs=['ax'])


def test_builtin_view_has_public_contract():
    source = _lift()
    view = asm_to_c(source)
    assert view['format'] == 'fdisbull-asm-c-view-2'
    assert view['engine'] == 'builtin'
    assert view['source_sha256'] == source['sha256']
    assert view['bindings'] == source['bindings']
    assert view['inputs'] == source['inputs']
    assert view['outputs'] == source['outputs']
    assert view['native_c'] is None
    assert view['native_c_status'] == 'not_applicable'
    assert view['text'] == 'ax += 200;\nax -= 1;'


def test_builtin_view_preserves_long_admitted_blocks():
    source = lift_asm_block(b'\x40' * 129, {'ax': '$result'},
                            inputs=['ax'], outputs=['ax'])
    view = asm_to_c(source)
    assert len(view['text'].splitlines()) == 129


@pytest.mark.parametrize('engine,tool_path,runtime_path', [
    ('ghidra', HEADLESS, JAVA),
    ('reko', REKO_ROOT / 'dist/reko.dll', REKO_ROOT / 'dotnet-x64/dotnet'),
    ('dcc', DCC, None),
])
def test_real_external_engines_share_public_contract(engine, tool_path, runtime_path):
    pytest.importorskip('z3')
    if not tool_path.is_file() or (runtime_path is not None and not runtime_path.exists()):
        pytest.skip(f'optional {engine} tool unavailable')
    source = _lift()
    view = asm_to_c(source, engine=engine, tool_path=tool_path,
                    runtime_path=runtime_path, require_equivalence=True)
    assert view['format'] == 'fdisbull-asm-c-view-2'
    assert view['engine'] == engine
    assert view['source_sha256'] == source['sha256']
    assert view['bindings'] == source['bindings']
    assert view['inputs'] == source['inputs']
    assert view['outputs'] == source['outputs']
    assert view['text'] == 'ax += 200;\nax -= 1;'
    assert isinstance(view['native_c'], str) and view['native_c'].strip()
    assert view['native_c_status'] == 'diagnostic_unverified'
    assert view['diagnostics']['covered_bytes'] == 4
    assert view['qualification']['status'] == 'equivalent_under_assumptions'
    assert qualify_asm_c_view(source, view)['status'] == 'equivalent_under_assumptions'


def test_qualified_path_rejects_changed_output(monkeypatch):
    pytest.importorskip('z3')
    from fdisbull import dcc_asm_c

    def wrong(lift, *, executable, timeout_s):
        return {'format': 'fdisbull-dcc-asm-c-1',
                'source_sha256': lift['sha256'], 'text': 'ax += 201;\nax -= 1;',
                'native_c': 'void start(void) {}', 'diagnostics': {'covered_bytes': 4}}

    monkeypatch.setattr(dcc_asm_c, 'render_dcc_asm_c', wrong)
    with pytest.raises(RuntimeError, match='not qualified: counterexample'):
        asm_to_c(_lift(), engine='dcc', tool_path='/fake', require_equivalence=True)


@pytest.mark.parametrize('engine,tool_path,runtime_path', [
    ('reko', REKO_ROOT / 'dist/reko.dll', REKO_ROOT / 'dotnet-x64/dotnet'),
    ('dcc', DCC, None),
])
def test_relative_tool_paths_resolve_before_temporary_cwd(engine, tool_path, runtime_path):
    if not tool_path.is_file() or (runtime_path is not None and not runtime_path.is_file()):
        pytest.skip(f'optional {engine} tool unavailable')
    view = asm_to_c(_lift(), engine=engine,
                    tool_path=os.path.relpath(tool_path),
                    runtime_path=os.path.relpath(runtime_path) if runtime_path else None)
    assert view['text'] == 'ax += 200;\nax -= 1;'
