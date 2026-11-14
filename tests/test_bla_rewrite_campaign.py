"""Freeze boundaries and effect grading, without inspecting a held-out cohort."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_bla_rewrites.py'
SPEC = importlib.util.spec_from_file_location('bla_rewrite_campaign_under_test', SCRIPT)
rewrites = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rewrites)
MASK = (1 << 64) - 1
SMALL_CASES = [(0, 1, 123), (2, 1, 456), ((MASK - 6) ^ 90, MASK, 123),
               (0, 0, 97), (MASK, MASK, 0)]


@pytest.fixture
def authored_protocol_root(tmp_path, monkeypatch):
    source_root = tmp_path / 'authored-source'
    source = source_root / 'fixtures/behavior-curriculum/bounded_update.c'
    source.parent.mkdir(parents=True)
    source.write_text('/* Authored protocol fixture; never compiled. */\n')
    monkeypatch.setattr(rewrites, 'ROOT', source_root)
    output = tmp_path / 'cohort'
    output.mkdir()
    return output, source


def test_protocol_binds_frozen_identity_before_selecting_new_seeds(authored_protocol_root, monkeypatch):
    output, source = authored_protocol_root
    frozen = hashlib.sha256(b'authored frozen generator').hexdigest()
    events = []
    def entropy(length):
        assert length == 32
        # The immutable identity is already supplied when entropy is selected.
        events.append(('entropy', frozen))
        return b'\x42' * 32
    monkeypatch.setattr(rewrites.os, 'urandom', entropy)
    protocol = rewrites.make_protocol(output, frozen, 3)
    assert events == [('entropy', frozen)]
    assert protocol['generator_sha256'] == frozen
    assert protocol['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert protocol['development_seeds'] == ['development-a', 'development-b']
    assert len(protocol['heldout_seeds']) == len(set(protocol['heldout_seeds'])) == 3
    assert set(protocol['heldout_seeds']).isdisjoint(protocol['development_seeds'])
    assert protocol['levels'] == [1, 2, 3]
    raw = (output / 'protocol.json').read_bytes()
    assert json.loads(raw) == protocol
    assert (output / 'protocol.sha256').read_text().strip() == hashlib.sha256(raw).hexdigest()


def test_protocol_replay_keeps_exact_seeds_and_bytes_without_new_entropy(authored_protocol_root, monkeypatch):
    output, _ = authored_protocol_root
    original = rewrites.make_protocol(output, 'a' * 64, 3)
    raw = (output / 'protocol.json').read_bytes()
    replay = output.parent / 'replay'
    replay.mkdir()
    def forbidden(*args):
        raise AssertionError('A replay must not resample held-out seeds')
    monkeypatch.setattr(rewrites.os, 'urandom', forbidden)
    assert rewrites.replay_protocol(replay, output / 'protocol.json', 'a' * 64, 3) == original
    assert (replay / 'protocol.json').read_bytes() == raw


@pytest.mark.parametrize('change', ['generator', 'source', 'seeds', 'count'])
def test_protocol_replay_rejects_changed_identity_or_cohort(authored_protocol_root, change):
    output, source = authored_protocol_root
    protocol = rewrites.make_protocol(output, 'a' * 64, 3)
    frozen = output / 'protocol.json'
    count = 3
    if change == 'generator':
        protocol['generator_sha256'] = 'b' * 64
    elif change == 'source':
        source.write_text('changed source')
    elif change == 'seeds':
        protocol['heldout_seeds'][1] = protocol['heldout_seeds'][0]
    else:
        count = 2
    candidate = output.parent / 'changed.json'
    candidate.write_text(json.dumps(protocol))
    replay = output.parent / 'replay'
    replay.mkdir()
    with pytest.raises(ValueError):
        rewrites.replay_protocol(replay, candidate, 'a' * 64, count)
    assert not (replay / 'protocol.json').exists()
    assert frozen.is_file()


def test_campaign_detects_generator_change_after_entropy_selection_before_any_variant_build(
        tmp_path, monkeypatch):
    source_root = tmp_path / 'authored-source'
    generator = source_root / 'scripts/bla_reachable_rewrites.py'
    generator.parent.mkdir(parents=True)
    generator.write_text('# Authored generator identity, never imported.\n')
    initial_digest = hashlib.sha256(generator.read_bytes()).hexdigest()
    source = source_root / 'fixtures/behavior-curriculum/bounded_update.c'
    source.parent.mkdir(parents=True)
    source.write_text('/* Authored source, never compiled in this test. */\n')
    monkeypatch.setattr(rewrites, 'ROOT', source_root)
    monkeypatch.setattr(rewrites, 'storage_decision', lambda *args: {'mode': 'authored-control'})
    monkeypatch.setenv('FDISBULL_TARGET_STORE', 'restored-after-test')
    def entropy(length):
        assert hashlib.sha256(generator.read_bytes()).hexdigest() == initial_digest
        generator.write_text('# Changed only after the identity was frozen.\n')
        return b'\x43' * length
    monkeypatch.setattr(rewrites.os, 'urandom', entropy)
    commands = []
    monkeypatch.setattr(rewrites.base, 'run_command', lambda argv, root, label: commands.append(label))
    monkeypatch.setattr(rewrites, 'register_observation', lambda *args: [])
    monkeypatch.setattr(rewrites, 'reachable_core_bytes', lambda *args: b'authored-baseline')
    def forbidden(*args, **kwargs):
        raise AssertionError('Changed generator must not build any variant')
    monkeypatch.setattr(rewrites, 'generate_assembly', forbidden)
    output = tmp_path / 'cohort'
    tools = {name: tmp_path / name for name in ('clang', 'lld-link', 'node', 'bla-cli')}
    for file in tools.values():
        file.write_bytes(b'authored tool identity; never executed')
    args = SimpleNamespace(output=output, storage_waiver=None, heldout_count=1,
                           clang=tools['clang'], linker=tools['lld-link'],
                           node=tools['node'], bla_cli=tools['bla-cli'])
    with pytest.raises(ValueError, match='Generator changed'):
        rewrites.campaign(args)
    protocol = json.loads((output / 'protocol.json').read_text())
    assert protocol['generator_sha256'] == initial_digest
    assert commands == ['baseline-compile', 'baseline-link']
    assert not (output / 'verification.json').exists()


@pytest.mark.parametrize('count', [True, False, 0, -1, 9, 1.0, '1', None])
def test_invalid_cohort_count_does_not_select_entropy_or_write_protocol(
        authored_protocol_root, monkeypatch, count):
    output, _ = authored_protocol_root
    def forbidden(length):
        raise AssertionError('Invalid configuration must not select seeds')
    monkeypatch.setattr(rewrites.os, 'urandom', forbidden)
    with pytest.raises(ValueError):
        rewrites.make_protocol(output, 'a' * 64, count)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize('filename', ['protocol.json', 'protocol.sha256'])
def test_existing_freeze_artifacts_are_preserved_before_entropy_selection(
        authored_protocol_root, monkeypatch, filename):
    output, _ = authored_protocol_root
    marker = output / filename
    marker.write_bytes(b'earlier unique protocol evidence')
    def forbidden(length):
        raise AssertionError('An existing protocol must not be replaced')
    monkeypatch.setattr(rewrites.os, 'urandom', forbidden)
    with pytest.raises((ValueError, FileExistsError)):
        rewrites.make_protocol(output, 'a' * 64, 1)
    assert marker.read_bytes() == b'earlier unique protocol evidence'


def test_heldout_case_generation_is_deterministic_full_width_and_has_real_boundaries():
    a = rewrites.heldout_cases('authored-independent-input-seed', count=3)
    assert a == rewrites.heldout_cases('authored-independent-input-seed', count=3)
    assert a != rewrites.heldout_cases('different-authored-input-seed', count=3)
    assert all(type(v) is int and 0 <= v <= MASK for row in a for v in row)
    assert any(x == limit == 0 for x, limit, _ in a)
    assert any(x == limit == MASK for x, limit, _ in a)
    assert any(x > limit for x, limit, _ in a)
    assert any(x < limit for x, limit, _ in a)
    assert any(x <= limit and (x ^ 90) + 7 == 1 << 64 for x, limit, _ in a)
    assert any(x <= limit and old == rewrites.base.oracle(x, limit, old) for x, limit, old in a)


def sample():
    return {'x': 0, 'limit': 1, 'old': 123, 'value': 97,
            'general': {'rax': '0x61', 'rbx': '0x1234'}, 'flags': '0x202',
            'writes': {'output': 1, 'stack': 0, 'image': 0}}


def test_sample_summary_retains_architectural_differences_without_changing_io_claim():
    baseline = sample()
    candidate = deepcopy(baseline)
    candidate['general']['rax'] = '0x99'
    candidate['flags'] = '0x246'
    row, = rewrites.summarize_samples([baseline], [candidate])
    assert row['differing_gprs'] == {'rax': {'baseline': '0x61', 'rewrite': '0x99'}}
    assert row['flags_xor'] == '0x44'
    assert row['output_and_store_equal'] is True
    candidate['writes']['output'] = 0
    assert rewrites.summarize_samples([baseline], [candidate])[0]['output_and_store_equal'] is False


@pytest.mark.parametrize('defect', ['count', 'x', 'limit', 'old', 'extra_register', 'missing_register'])
def test_sample_summary_rejects_unmatched_input_state_or_register_evidence(defect):
    baseline, candidate = sample(), sample()
    if defect == 'count':
        right = []
    else:
        right = [candidate]
        if defect in ('x', 'limit', 'old'):
            candidate[defect] += 1
        elif defect == 'extra_register':
            candidate['general']['r9'] = '0x0'
        else:
            candidate['general'].pop('rax')
    with pytest.raises(ValueError):
        rewrites.summarize_samples([baseline], right)


def test_cli_keeps_linker_driver_symlink_name_for_argv_zero(tmp_path, monkeypatch):
    driver = tmp_path / 'lld'
    driver.write_text('authored placeholder, never executed')
    link = tmp_path / 'lld-link'
    link.symlink_to(driver.name)
    captured = {}
    def campaign(args):
        captured['linker'] = args.linker
        return {'records': [], 'cases_per_target': 1}
    monkeypatch.setattr(rewrites, 'campaign', campaign)
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), 'campaign', '--output', str(tmp_path / 'new'),
        '--clang', str(driver), '--node', str(driver), '--bla-cli', str(driver), '--linker', str(link)])
    assert rewrites.main() == 0
    assert captured['linker'] == link.absolute()
    assert captured['linker'].name == 'lld-link'
    assert captured['linker'] != driver.resolve()


@pytest.mark.parametrize('projection', ['gprs', 'flags', 'ordered_memory'])
def test_contract_override_exposes_real_machine_effects_excluded_from_default_projection(tmp_path, projection):
    pytest.importorskip('unicorn')
    pytest.importorskip('z3')
    from test_bla_curriculum import CORE, tiny_dll
    baseline = tiny_dll(tmp_path, name='baseline.dll')
    if projection == 'gprs':
        # R9 is volatile under the declared caller contract, but observable when live.
        code = bytes.fromhex('49c7c101000000') + CORE
        contract = {'live_registers': ['r9']}
    elif projection == 'flags':
        # Keep output bytes unchanged, but replace the final accepted FLAGS.
        code = CORE[:-1] + bytes.fromhex('4839d1c3')
        contract = {'live_flags': 0xffffffff}
    else:
        # An extra read/idempotent write preserves final RAM, not ordered accesses.
        code = bytes.fromhex('498b00498900') + CORE
        contract = {'memory_observation': 'ordered'}
    variant = tiny_dll(tmp_path, name='different-observer.dll', code=code)
    ordinary = rewrites.base.core_comparison(baseline, variant)
    widened = rewrites.base.core_comparison(baseline, variant, contract=contract)
    assert all(row['proof']['status'] == 'equivalent_under_contract' for row in ordinary)
    assert widened[0]['proof']['status'] == 'different'
    assert widened[0]['proof']['contraction'] is None
    assert widened[0]['proof']['counterexample']
    assert all(row['proof']['semantic_equivalence'] is None for row in ordinary + widened)


def test_unsupported_instruction_cannot_be_laundered_by_matching_sample_outputs(tmp_path):
    pytest.importorskip('unicorn')
    pytest.importorskip('z3')
    from test_bla_curriculum import CORE, tiny_dll
    baseline = tiny_dll(tmp_path, name='baseline.dll')
    variant = tiny_dll(tmp_path, name='unsupported-prefix.dll', code=b'\x66\x90' + CORE)
    reports = rewrites.base.core_comparison(baseline, variant)
    assert all(row['proof']['status'] == 'unknown' for row in reports)
    assert all(row['proof']['contraction'] is None for row in reports)
    assert all(row['contraction_expansion_verified'] is False for row in reports)


@pytest.mark.parametrize('contract', [False, [], 0, {'unknown_field': True}, {'live_flags': True},
                                     {'live_registers': ['r9', 'r9']}])
def test_invalid_override_cannot_silently_select_default_contract(tmp_path, contract):
    pytest.importorskip('unicorn')
    pytest.importorskip('z3')
    from test_bla_curriculum import tiny_dll
    filename = tiny_dll(tmp_path)
    with pytest.raises(ValueError):
        rewrites.base.core_comparison(filename, filename, contract=contract)


def test_existing_grade_workspace_is_preserved_without_executing_solver(tmp_path, monkeypatch):
    solver = tmp_path / 'solver.py'
    solver.write_text('raise SystemExit(99)\n')
    output = tmp_path / 'grade'
    output.mkdir()
    marker = output / 'earlier-evidence'
    marker.write_bytes(b'preserve')
    def forbidden(*args, **kwargs):
        raise AssertionError('An existing grade must not execute a solver')
    monkeypatch.setattr(rewrites.subprocess, 'run', forbidden)
    with pytest.raises(ValueError):
        rewrites.grade_solver(solver, output, 'authored', cases=SMALL_CASES)
    assert marker.read_bytes() == b'preserve'


def test_empty_grade_cases_cannot_pass_vacuously(tmp_path, monkeypatch):
    solver = tmp_path / 'solver.py'
    solver.write_text('pass\n')
    def forbidden(*args, **kwargs):
        raise AssertionError('An empty cohort must fail before solver execution')
    monkeypatch.setattr(rewrites.subprocess, 'run', forbidden)
    with pytest.raises(ValueError):
        rewrites.grade_solver(solver, tmp_path / 'empty-grade', 'authored', cases=[])


@pytest.fixture(scope='module')
def native_sandbox():
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        pytest.skip('Actual macOS sandbox required for grading boundary tests')
    probe = subprocess.run(['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)', '/usr/bin/true'],
                           capture_output=True, timeout=5)
    if probe.returncode:
        pytest.skip('macOS sandbox cannot be applied in this execution environment')


SOLVER = '''import json,sys
MASK=(1<<64)-1
for line in sys.stdin:
 a,b,old=json.loads(line)
 value=old if a>b else ((a^90)+7)&MASK
 writes=int(a<=b)
 row={{'value':value,'writes':writes}}
 {change}
 print(json.dumps(row))
'''


def write_solver(tmp_path, change='pass'):
    path = tmp_path / 'authored-solver.py'
    path.write_text(SOLVER.format(change=change))
    return path


def test_real_sandbox_grades_correct_effects_and_preserves_frozen_source(tmp_path, native_sandbox):
    solver = write_solver(tmp_path)
    frozen = solver.read_bytes()
    output = tmp_path / 'grade'
    report = rewrites.grade_solver(solver, output, 'authored-test-seed', cases=SMALL_CASES)
    assert report['passed'] is True and report['failures'] == []
    assert report['cases'] == len(SMALL_CASES)
    assert report['solver_sha256'] == hashlib.sha256(frozen).hexdigest()
    assert (output / 'solver.py').read_bytes() == frozen
    assert json.loads((output / 'grade.json').read_text()) == report


@pytest.mark.parametrize('change', [
    "row['value']=False if value==0 else value",
    "row['writes']=bool(writes)",
    "row['value']=float(value)",
    "row['writes']=2 if writes else 0",
    "row['writes']=0 if value==old else writes",
    "row['value']=old if a>=b else value",
    "row['extra']=1",
    "row={'value':value}",
    "row=[value,writes]",
])
def test_real_grade_rejects_wrong_json_types_keys_boundary_or_write_effect(tmp_path, native_sandbox, change):
    solver = write_solver(tmp_path, change)
    report = rewrites.grade_solver(solver, tmp_path / 'grade', 'authored-test-seed', cases=SMALL_CASES)
    assert report['passed'] is False
    assert any(row['kind'] == 'recovered_effect_contract_mismatch' for row in report['failures'])


@pytest.mark.parametrize('body', [
    'pass\n',
    'raise SystemExit(7)\n',
    'import sys\nfor line in sys.stdin: print("not-json")\n',
    SOLVER.format(change='pass') + 'print("extra row")\n',
])
def test_real_grade_rejects_missing_extra_invalid_rows_and_nonzero_exit(tmp_path, native_sandbox, body):
    solver = tmp_path / 'authored-solver.py'
    solver.write_text(body)
    report = rewrites.grade_solver(solver, tmp_path / 'grade', 'authored-test-seed', cases=SMALL_CASES)
    assert report['passed'] is False and report['failures']


def test_real_grading_sandbox_denies_oracle_reads_frozen_file_writes_and_network(tmp_path, native_sandbox):
    outside = tmp_path / 'outside-oracle-canary'
    outside.write_bytes(b'authored outside canary, not real oracle data')
    solver = tmp_path / 'authored-solver.py'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        preamble = f'''from pathlib import Path
import socket
blocked=[]
for p in [Path({str(outside)!r})]:
 try: p.read_bytes()
 except PermissionError: blocked.append(True)
 else: blocked.append(False)
try: Path(__file__).write_text('overwrite frozen solver')
except PermissionError: blocked.append(True)
else: blocked.append(False)
try:
 s=socket.create_connection(('127.0.0.1',{port}),timeout=1)
 s.close()
except PermissionError: blocked.append(True)
else: blocked.append(False)
assert blocked==[True,True,True]
'''
        solver.write_text(preamble + SOLVER.format(change='pass'))
        report = rewrites.grade_solver(solver, tmp_path / 'grade', 'authored-test-seed', cases=SMALL_CASES)
    assert report['passed'] is True
    assert outside.read_bytes() == b'authored outside canary, not real oracle data'
