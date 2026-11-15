"""Known-answer PE calibration, independent of a compiler or external corpus."""
from __future__ import annotations

import importlib.util
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_bla_curriculum.py'
SPEC = importlib.util.spec_from_file_location('authored_bla_curriculum', SCRIPT)
curriculum = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(curriculum)
MASK = (1 << 64) - 1

# Win64 RCX=x, RDX=limit, R8=out. These independently authored instructions are
# deliberately small enough for the current regional model, with RET as exit.
CORE = bytes.fromhex('4839d1770b4883f15a4883c107498908c3')
MUTATED_CORE = bytes.fromhex('4839d1730b4883f15a4883c107498908c3')


def tiny_dll(tmp_path, *, code=CORE, name='authored.dll', machine=0x8664,
             entry=0, dll=True, imports=False, forward_core=False):
    """Write an actual PE64 DLL containing only our machine-code oracle.

    This is a direct-function fixture. It supplies no Windows startup or imports.
    The separately authored branch/arithmetic bytes are executed by Unicorn.
    """
    pytest.importorskip('pefile')
    raw = bytearray(0x600)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', raw, 0x84, machine, 1, 0, 0, 0, 240,
                     0x22 | (0x2000 if dll else 0))
    opt = 0x98
    struct.pack_into('<H', raw, opt, 0x20b)
    struct.pack_into('<I', raw, opt + 16, entry)
    struct.pack_into('<Q', raw, opt + 24, 0x180000000)
    struct.pack_into('<II', raw, opt + 32, 0x1000, 0x200)
    struct.pack_into('<II', raw, opt + 56, 0x2000, 0x200)
    struct.pack_into('<H', raw, opt + 68, 3)
    struct.pack_into('<I', raw, opt + 108, 16)
    struct.pack_into('<II', raw, opt + 112, 0x1200, 0x100)
    sec = opt + 240
    raw[sec:sec + 8] = b'.text\0\0\0'
    struct.pack_into('<IIII', raw, sec + 8, 0x400, 0x1000, 0x400, 0x200)
    struct.pack_into('<I', raw, sec + 36, 0x60000020)
    assert len(code) <= 0x40
    raw[0x200:0x200 + len(code)] = code
    # bounded_update tail-jumps to bounded_core, exercising a real control edge.
    raw[0x240:0x245] = b'\xe9' + struct.pack('<i', -0x45)
    struct.pack_into('<IIHHIIIIIII', raw, 0x400,
                     0, 0, 0, 0, 0x1290, 1, 2, 2, 0x1240, 0x1248, 0x1250)
    struct.pack_into('<II', raw, 0x440, 0x1280 if forward_core else 0x1000, 0x1040)
    struct.pack_into('<II', raw, 0x448, 0x1260, 0x1270)
    struct.pack_into('<HH', raw, 0x450, 0, 1)
    raw[0x460:0x46d] = b'bounded_core\0'
    raw[0x470:0x47f] = b'bounded_update\0'
    raw[0x490:0x49d] = b'authored.dll\0'
    if forward_core:
        raw[0x480:0x48b] = b'other.func\0'
    if imports:
        struct.pack_into('<II', raw, opt + 120, 0x1300, 0x40)
        struct.pack_into('<IIIII', raw, 0x500, 0x1340, 0, 0, 0x1360, 0x1350)
        struct.pack_into('<Q', raw, 0x540, 0x1380)
        struct.pack_into('<Q', raw, 0x550, 0x1380)
        raw[0x560:0x56d] = b'KERNEL32.dll\0'
        raw[0x580:0x58e] = b'\0\0ExitProcess\0'
    filename = tmp_path / name
    filename.write_bytes(raw)
    return filename


@pytest.mark.parametrize('x,limit,old,expected', [
    (0, 0, 123, 97), (1, 1, 123, 98), (0x5a, 0x5a, 123, 7),
    (0x59, 0x5a, 123, 10), (0x5b, 0x5b, 123, 8),
    (2, 1, 0xabcdef, 0xabcdef), (MASK, MASK - 1, 123, 123),
    (MASK, MASK, 123, MASK - 83), ((MASK - 6) ^ 0x5a, MASK, 123, 0),
])
def test_oracle_known_answers_cover_guard_and_modular_wrap(x, limit, old, expected):
    assert curriculum.oracle(x, limit, old) == expected


@pytest.mark.parametrize('value', [-1, 1 << 64, True, 1.0, '1', None])
@pytest.mark.parametrize('position', range(3))
def test_oracle_rejects_values_outside_unsigned_integer_contract(value, position):
    args = [0, 0, 0]
    args[position] = value
    with pytest.raises(ValueError, match='unsigned 64-bit'):
        curriculum.oracle(*args)


def test_vectors_are_repeatable_and_include_actual_output_wrap():
    vectors = curriculum.case_vectors()
    assert vectors == curriculum.case_vectors()
    assert len(vectors) >= 250
    assert any(x == limit == 0 for x, limit, _ in vectors)
    assert any(x == limit == MASK for x, limit, _ in vectors)
    assert any(x == 1 << 32 and x <= limit for x, limit, _ in vectors)
    assert any(x <= limit and (x ^ 0x5a) + 7 == 1 << 64 for x, limit, _ in vectors)
    assert any(x <= limit and old == curriculum.oracle(x, limit, old)
               for x, limit, old in vectors)
    assert len(vectors) > len(set(vectors))  # Retained-image repeated input.


def test_actual_tiny_pe_preserves_guard_output_abi_and_repeated_calls(tmp_path):
    pytest.importorskip('unicorn')
    filename = tiny_dll(tmp_path)
    _, identity = curriculum.inspect_pe(filename)
    assert identity['exports'] == {'bounded_core': 0x1000, 'bounded_update': 0x1040}
    cpu = curriculum.FunctionCPU(filename)
    for x, limit, old, expected in [
        (0, 0, 123, 97), (2, 1, 456, 456),
        ((MASK - 6) ^ 0x5a, MASK, 123, 0), (MASK, MASK, 0, MASK - 83),
        (0, 0, 97, 97), (0, 0, 123, 97),
    ]:
        result = cpu.call(x, limit, old)
        assert result['value'] == expected
        assert result['writes'] == {'output': int(x <= limit), 'stack': 0, 'image': 0}
        assert result['image_write_rvas'] == []
    report = curriculum.exercise(filename, curriculum.case_vectors())
    assert report['agreement'] == report['cases']
    assert report['mismatches'] == []
    assert report['rejected_output_writes'] == 0


@pytest.mark.parametrize('changes', [
    {'machine': 0x14c}, {'entry': 0x1000}, {'dll': False},
    {'imports': True}, {'forward_core': True},
])
def test_pe_boundary_rejects_wrong_arch_startup_imports_or_forwarders(tmp_path, changes):
    filename = tiny_dll(tmp_path, **changes)
    with pytest.raises(ValueError):
        curriculum.inspect_pe(filename)


def test_rejected_idempotent_store_is_an_observable_contract_violation(tmp_path):
    pytest.importorskip('unicorn')
    # Load/store the old value before the guard. Final bytes stay equal on reject.
    filename = tiny_dll(tmp_path, code=bytes.fromhex('498b00498900') + CORE)
    result = curriculum.FunctionCPU(filename).call(2, 1, 456)
    assert result['value'] == 456
    assert result['writes']['output'] == 1
    with pytest.raises(ValueError):
        curriculum.exercise(filename, [(2, 1, 456)])


@pytest.mark.parametrize('prefix,reason', [
    ('4831db', 'nonvolatile'),
    ('49c740f801000000', 'canary'),
    ('49898000010000', 'escaped'),
])
def test_actual_machine_code_cannot_hide_abi_canary_or_footprint_damage(tmp_path, prefix, reason):
    pytest.importorskip('unicorn')
    filename = tiny_dll(tmp_path, code=bytes.fromhex(prefix) + CORE)
    with pytest.raises(ValueError, match=reason):
        curriculum.FunctionCPU(filename).call(0, 0, 123)


def test_instruction_limit_is_failure_not_successful_completion(tmp_path):
    pytest.importorskip('unicorn')
    filename = tiny_dll(tmp_path, code=bytes.fromhex('ebfe'))
    with pytest.raises(ValueError, match='did not return'):
        curriculum.FunctionCPU(filename).call(0, 0, 123)


def test_guard_negative_control_changes_only_equality_boundary(tmp_path):
    pytest.importorskip('unicorn')
    filename = tiny_dll(tmp_path, code=MUTATED_CORE)
    report = curriculum.exercise(filename, curriculum.case_vectors(), mutation=True)
    assert report['mismatches']
    assert all(row['x'] == row['limit'] for row in report['mismatches'])
    assert report['rejected_output_writes'] == 0


def test_broken_everywhere_target_cannot_masquerade_as_guard_mutation(tmp_path):
    pytest.importorskip('unicorn')
    # Returns without updating for every input, including x < limit.
    filename = tiny_dll(tmp_path, code=b'\xc3')
    with pytest.raises(ValueError):
        curriculum.exercise(filename, [(0, 1, 123), (0, 0, 123)], mutation=True)


def test_real_region_contraction_expands_with_its_ram_evidence(tmp_path):
    pytest.importorskip('unicorn')
    pytest.importorskip('z3')
    baseline = tiny_dll(tmp_path, name='baseline.dll')
    variant = tiny_dll(tmp_path, name='extra-nop.dll', code=b'\x90' + CORE)
    evidence_dir = tmp_path / 'evidence'
    evidence_dir.mkdir()
    reports = curriculum.core_comparison(baseline, variant, evidence_dir=evidence_dir)
    assert len(reports) == 2
    from fdisbull.pe_region_equivalence import expand_pe_contraction
    for row in reports:
        assert row['proof']['status'] == 'equivalent_under_contract'
        assert row['proof']['semantic_equivalence'] is None
        assert row['contraction_expansion_verified'] is True
        assert 'Unicorn' in row['capture_engine']
        raw = (evidence_dir / row['evidence_file']).read_bytes()
        assert curriculum.sha(raw) == row['evidence_sha256']
        evidence = json.loads(raw)
        assert evidence['capture_engine'] == 'Unicorn'
        expanded = expand_pe_contraction(row['proof']['contraction'], evidence['baseline'], evidence['layer'],
            baseline_memory=evidence['baseline_memory'], layer_memory=evidence['layer_memory'])
        assert expanded == {key: evidence[key] for key in
                            ('baseline', 'layer', 'baseline_memory', 'layer_memory')}
        # Artifact hashes must bind both instructions and the accompanying RAM.
        changed = deepcopy(evidence['baseline_memory'])
        initial = changed['entry'][0]['hex']
        changed['entry'][0]['hex'] = ('00' if initial[:2] != '00' else '01') + initial[2:]
        with pytest.raises(ValueError, match='Expansion evidence differs'):
            expand_pe_contraction(row['proof']['contraction'], evidence['baseline'], evidence['layer'],
                baseline_memory=changed, layer_memory=evidence['layer_memory'])
        changed_trace = deepcopy(evidence['layer'])
        changed_trace['events'][0]['bytes'] = 'cc'
        with pytest.raises(ValueError, match='Expansion evidence differs'):
            expand_pe_contraction(row['proof']['contraction'], evidence['baseline'], changed_trace,
                baseline_memory=evidence['baseline_memory'], layer_memory=evidence['layer_memory'])


def test_guard_solver_witness_replays_on_complete_real_wrapper(tmp_path):
    pytest.importorskip('unicorn')
    pytest.importorskip('z3')
    baseline = tiny_dll(tmp_path, name='baseline.dll')
    mutation = tiny_dll(tmp_path, name='boundary-change.dll', code=MUTATED_CORE)
    reports = curriculum.core_comparison(baseline, mutation, mutation=True)
    assert len(reports) == 2
    for row in reports:
        assert row['proof']['status'] == 'different'
        assert row['proof']['semantic_equivalence'] is None
        assert row['contraction_expansion_verified'] is False
        replay = row['witness_replay']
        assert replay['x'] == replay['limit']
        assert replay['baseline_output_writes'] == 1
        assert replay['mutation_output_writes'] == 0
        assert replay['baseline'] == curriculum.oracle(replay['x'], replay['limit'], replay['old'])
        assert replay['mutation'] == replay['old']


def test_existing_campaign_output_is_preserved_before_tool_or_build_work(tmp_path, monkeypatch):
    output = tmp_path / 'retained'
    output.mkdir()
    marker = output / 'unique-evidence'
    marker.write_bytes(b'retain this')
    def forbidden(*args, **kwargs):
        raise AssertionError('No admission, compiler or protector should run')
    monkeypatch.setattr(curriculum.subprocess, 'run', forbidden)
    with pytest.raises(ValueError, match='new directory'):
        curriculum.campaign(SimpleNamespace(output=output))
    assert marker.read_bytes() == b'retain this'


def test_failed_command_retains_diagnostics_and_exact_argument_receipt(tmp_path):
    (tmp_path / 'tmp').mkdir()
    command = [sys.executable, '-c', 'import sys;print("authored stdout");sys.stderr.write("authored failure\\n");sys.exit(7)']
    with pytest.raises(ValueError, match='retained command logs'):
        curriculum.run_command(command, tmp_path, 'authored-failure')
    assert (tmp_path / 'authored-failure.stdout').read_bytes() == b'authored stdout\n'
    assert (tmp_path / 'authored-failure.stderr').read_bytes() == b'authored failure\n'
    record = json.loads((tmp_path / 'commands.jsonl').read_text())
    assert record['argv'] == command
    assert record['exit'] == 7
    assert record['stderr_sha256'] == curriculum.sha(b'authored failure\n')
