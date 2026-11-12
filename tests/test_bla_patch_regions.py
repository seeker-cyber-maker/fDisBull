"""Authored parser/proof fixtures exercise BLA campaign gates without target bytes."""
import gzip
import importlib.util
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_bla_patch_regions.py'
    spec = importlib.util.spec_from_file_location('bla_region_campaign_for_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source():
    return '\n'.join([
        'const runtimeSeedAuthored = arbitraryTime & 0x7fffc | (typeof corpus === "function" && corpus(0) === 4129934667 ? 1 : 0);',
        '(Math.imul(runtimeSeedAuthored ^ 24, runtimeSeedAuthored ^ 24) & 7) === 1;',
        '(Math.imul(runtimeSeedAuthored ^ 28, runtimeSeedAuthored ^ 28) & 7) === 1;',
        '(Math.imul(runtimeSeedAuthored | 21, (runtimeSeedAuthored | 21) + 1) & 1) === 0;',
    ])


def unsigned(value):
    result = bytearray()
    while True:
        byte, value = value & 127, value >> 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def section(kind, body):
    return bytes((kind,)) + unsigned(len(body)) + body


def module_bytes(*, arithmetic=0x6a, extra=b'', invalid_export=False, custom=b''):
    # Pure authored mix(a,b)=a+b and seal(x)=mix(x,3), not BLA instruction bytes.
    types = section(1, bytes.fromhex('0260027f7f017f60017f017f'))
    functions = section(3, b'\x02\x00\x01')
    exports = section(7, b'\x02\x03mix\x00\x00\x04seal\x00' + bytes((2 if invalid_export else 1,)))
    mix = b'\x00\x20\x00\x20\x01' + bytes((arithmetic,)) + b'\x0b'
    seal = bytes.fromhex('002000410310000b')
    code = section(10, b'\x02' + unsigned(len(mix)) + mix + unsigned(len(seal)) + seal)
    return b'\0asm\x01\0\0\0' + types + extra + functions + exports + code + custom


def campaign_root(tmp_path, monkeypatch, runner, *, clean=None, hardened=None):
    clean = module_bytes() if clean is None else clean
    hardened = clean if hardened is None else hardened
    fixtures = {'js': source().encode(), 'clean_js': b'// authored clean fixture\n',
                'clean_wasm': clean, 'hardened_wasm': gzip.compress(hardened), 'license': b'MIT License\n'}
    for key, relative in runner.PATHS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fixtures[key])
    monkeypatch.setattr(runner, 'SUPPORTED_L1', runner.digest(fixtures['js']))
    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if command[0] == 'git':
            if 'rev-parse' in command:
                stdout = runner.SUPPORTED_COMMIT + '\n'
            elif 'config' in command:
                stdout = 'https://github.com/qybaihe/bla.git\n'
            elif 'status' in command:
                stdout = ''
            else:
                raise AssertionError('Unexpected Git operation in authored fixture')
            return subprocess.CompletedProcess(command, 0, stdout, '')
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(runner.subprocess, 'run', run)
    return tmp_path


def test_source_matched_predicates_prove_and_preserve_assumption_negative_case(runner):
    pytest.importorskip('z3')
    rows, vectors = runner.predicates(source())
    assert len(rows) == len(vectors) == 3
    assert [row['counterquery'] for row in rows] == ['unsat'] * 3
    for row, vector in zip(rows, vectors, strict=True):
        start, end = row['source_offsets']
        assert runner.digest(source()[start:end].encode()) == row['source_region_sha256']
        assert 'Standard intrinsic Math.imul and u32 seed input' in row['assumptions']
        assert len(vector['seeds']) == len(vector['expected']) == 264
        if row['operation'] == 'square':
            assert any('seed & 3 == 1' in assumption for assumption in row['assumptions'])
            assert vector['expected'][vector['seeds'].index(0)] is False
            assert all(result is True for seed, result in zip(vector['seeds'], vector['expected'], strict=True)
                       if seed & 3 == 1)
        else:
            assert all(vector['expected'])


@pytest.mark.parametrize('before,after', [
    ('& 0x7fffc |', '& 0x7ffff |'),
    ('corpus(0) === 4129934667', 'other(0) === 4129934667'),
    ('runtimeSeedAuthored ^ 24) &', 'runtimeSeedAuthored ^ 25) &'),
    (' + 1) & 1', ' + 2) & 1'),
])
def test_unreviewed_seed_shape_or_expression_operand_change_is_rejected(runner, before, after):
    pytest.importorskip('z3')
    with pytest.raises(ValueError):
        runner.predicates(source().replace(before, after))


def test_authored_stateless_wasm_regions_parse_and_interpret_with_u32_wrap(runner):
    parsed = runner.wasm(module_bytes())
    assert parsed['exports'] == {'mix': 0, 'seal': 1}
    assert parsed['export_count'] == 2
    assert runner.interpret(parsed['functions'], 0, (0xffffffff, 1)) == 0
    assert runner.interpret(parsed['functions'], 1, (0xffffffff,)) == 2
    decorated = runner.wasm(module_bytes(custom=section(0, b'\x04noteauthored-metadata')))
    assert parsed['sections'][10] == decorated['sections'][10]
    assert len(decorated['customs']) == 1


@pytest.mark.parametrize('kind', [2, 4, 5, 6, 8, 9, 11])
def test_import_or_mutable_module_state_prevents_pure_region_claim(runner, kind):
    with pytest.raises(ValueError):
        runner.wasm(module_bytes(extra=section(kind, b'\0')))


def test_unadmitted_instruction_and_external_export_are_rejected(runner):
    with pytest.raises(ValueError, match='Instruction outside'):
        runner.wasm(module_bytes(arithmetic=0x6d))  # Division is outside total-i32 profile.
    with pytest.raises(ValueError, match='Export refers outside'):
        runner.wasm(module_bytes(invalid_export=True))


@pytest.mark.parametrize('raw', [b'', b'\x80', b'\xff\xff\xff\xff\x1f', b'\x80' * 6])
def test_wasm_integer_bounds_fail_closed(runner, raw):
    with pytest.raises(ValueError):
        runner.uleb(raw, 0)


def test_signed_integer_and_module_extent_bounds(runner):
    assert runner.sleb(b'\x7f', 0) == (0xffffffff, 1)
    assert runner.sleb(bytes.fromhex('8080808078'), 0) == (0x80000000, 5)
    with pytest.raises(ValueError):
        runner.sleb(b'\x80' * 6, 0)
    with pytest.raises(ValueError):
        runner.wasm(module_bytes()[:-1])
    with pytest.raises(ValueError):
        runner.wasm(b'\0asm\x01\0\0\0' + b'\x01\x7f')


def test_campaign_rejects_changed_allowed_code_before_claiming_identity(runner, tmp_path, monkeypatch):
    pytest.importorskip('z3')
    root = campaign_root(tmp_path, monkeypatch, runner, hardened=module_bytes(arithmetic=0x73))
    with pytest.raises(ValueError, match='code regions differ'):
        runner.campaign(root)


def test_campaign_rejects_gzip_expansion_over_bound(runner, tmp_path, monkeypatch):
    pytest.importorskip('z3')
    root = campaign_root(tmp_path, monkeypatch, runner, hardened=module_bytes() + b'\0' * 200)
    monkeypatch.setattr(runner, 'LIMIT', 128)
    with pytest.raises(ValueError, match='Decoded hardened module exceeds bound'):
        runner.campaign(root)


def test_campaign_rejects_corrupt_compressed_artifact(runner, tmp_path, monkeypatch):
    pytest.importorskip('z3')
    root = campaign_root(tmp_path, monkeypatch, runner)
    (root / runner.PATHS['hardened_wasm']).write_bytes(b'not-a-gzip-file')
    with pytest.raises(OSError):
        runner.campaign(root)


@pytest.mark.parametrize('changed', ['source', 'revision'])
def test_campaign_rejects_unreviewed_provenance(runner, tmp_path, monkeypatch, changed):
    pytest.importorskip('z3')
    root = campaign_root(tmp_path, monkeypatch, runner)
    if changed == 'source':
        monkeypatch.setattr(runner, 'SUPPORTED_L1', '0' * 64)
    else:
        original = runner.subprocess.run

        def changed_revision(command, *args, **kwargs):
            if command[0] == 'git' and 'rev-parse' in command:
                return subprocess.CompletedProcess(command, 0, '0' * 40 + '\n', '')
            return original(command, *args, **kwargs)

        monkeypatch.setattr(runner.subprocess, 'run', changed_revision)
    with pytest.raises(ValueError, match='revision or source differs'):
        runner.campaign(root)
