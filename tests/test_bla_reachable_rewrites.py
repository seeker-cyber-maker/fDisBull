"""Development-seed checks for reachable full-width Win64 rewrites.

Compiler tests require an explicitly selected external artifact parent. Artifacts
are retained there; the test does not grant storage admission or download tools.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile

import pytest

from scripts.bla_reachable_rewrites import MAX_LEVEL, VOLATILE_SCRATCH, generate_assembly


ROOT = Path(__file__).resolve().parents[1]
MASK = (1 << 64) - 1
NONVOLATILE = ('rbx', 'rbp', 'rsi', 'rdi', 'r12', 'r13', 'r14', 'r15')


def _program(source):
    instructions, labels = [], {}
    for raw in source.splitlines():
        text = raw.split('#', 1)[0].strip()
        if not text or text.startswith('.') and not text.endswith(':'):
            continue
        if text.endswith(':'):
            labels[text[:-1]] = len(instructions)
        else:
            op, _, operands = text.partition(' ')
            instructions.append((op, [x.strip() for x in operands.split(',')] if operands else []))
    return instructions, labels


def _execute(program, x, limit, old, *, entry='bounded_core', salt=0):
    """Independent integer interpreter for the emitted text, not x86 validation."""
    instructions, labels = program
    regs = {name: (0x123456789abc0000 + salt + i) & MASK for i, name in enumerate(
        (*NONVOLATILE, *VOLATILE_SCRATCH, 'rcx', 'rdx', 'r8', 'rsp'))}
    regs.update(rcx=x, rdx=limit, r8=0x60000008, rsp=0x70008008)
    original = dict(regs)
    value, writes, cf, zf, pc = old, [], False, False, labels[entry]

    def read(operand):
        return regs[operand] if operand in regs else int(operand, 0) & MASK

    for _ in range(1024):
        op, args = instructions[pc]
        pc += 1
        if op == 'ret':
            regs['rsp'] += 8
            return value, writes, regs, original
        if op == 'nop':
            continue
        if op in ('jmp', 'ja', 'jae', 'jb', 'jbe'):
            taken = {'jmp': True, 'ja': not cf and not zf, 'jae': not cf,
                     'jb': cf, 'jbe': cf or zf}[op]
            if taken:
                pc = labels[args[0]]
            continue
        if op == 'mov':
            if args[0] == 'qword ptr [r8]':
                value = read(args[1])
                writes.append((regs['r8'], 8, value))
            else:
                assert args[0] in regs
                regs[args[0]] = read(args[1])
            continue
        assert op in ('xor', 'add', 'sub', 'and', 'or', 'cmp')
        assert args[0] in regs
        a, b = read(args[0]), read(args[1])
        if op in ('sub', 'cmp'):
            result, cf = (a - b) & MASK, a < b
        elif op == 'add':
            result, cf = (a + b) & MASK, a + b > MASK
        elif op == 'xor':
            result, cf = a ^ b, False
        elif op == 'and':
            result, cf = a & b, False
        else:
            result, cf = a | b, False
        zf = result == 0
        if op != 'cmp':
            regs[args[0]] = result
    raise AssertionError('Generated function did not terminate')


def _vectors():
    boundaries = (0, 1, 89, 90, 91, (1 << 32) - 1, 1 << 32,
                  (1 << 63) - 1, 1 << 63, MASK - 1, MASK)
    rows = [(x, limit, 0x0123456789abcdef) for x in boundaries for limit in boundaries]
    rng = random.Random(0x64B1A)
    for _ in range(16):
        x, limit, old = (rng.getrandbits(64) for _ in range(3))
        rows.extend(((x, limit, old), (x, x, old)))
    return rows + [((MASK - 6) ^ 90, MASK, 1), (0, 0, 97)]


@pytest.mark.parametrize('level', range(MAX_LEVEL + 1))
def test_generated_text_matches_unsigned_guard_modular_output_and_abi(level):
    for seed in ('dev-alpha', 'dev-beta', 'dev-\N{GREEK SMALL LETTER DELTA}'):
        program = _program(generate_assembly(seed, level))
        for index, (x, limit, old) in enumerate(_vectors()):
            expected = old if x > limit else ((x ^ 90) + 7) & MASK
            value, writes, regs, original = _execute(program, x, limit, old, salt=index)
            assert value == expected
            assert writes == ([(0x60000008, 8, expected)] if x <= limit else [])
            assert all(regs[name] == original[name] for name in NONVOLATILE)
            assert regs['rsp'] == original['rsp'] + 8
            assert regs['r8'] == original['r8']


@pytest.mark.parametrize('level', (0, 1, 2, 3, MAX_LEVEL))
def test_mutation_changes_only_equality_boundary_and_keeps_required_store_count(level):
    program = _program(generate_assembly('dev-mutation', level, mutation=True))
    equality_witnesses = 0
    for x, limit, old in _vectors():
        value, writes, _, _ = _execute(program, x, limit, old)
        expected = old if x >= limit else ((x ^ 90) + 7) & MASK
        assert value == expected and len(writes) == int(x < limit)
        if x == limit:
            equality_witnesses += 1
            assert writes == []
    assert equality_witnesses


def test_seeded_changes_are_reachable_deterministic_and_do_not_embed_seed_text():
    outputs = [generate_assembly(f'dev-seed-{i}', 2) for i in range(16)]
    assert len(set(outputs)) == 16
    assert outputs[0] == generate_assembly('dev-seed-0', 2)
    assert 'dev-seed-0' not in outputs[0]
    reference = _program(generate_assembly('dev-reference', 0))
    for source in outputs:
        program = _program(source)
        assert program[0] != reference[0]
        # The extra work executes even on the rejected branch.
        assert program[0][0][0] == 'mov' and reference[0][0][0] == 'cmp'


@pytest.mark.parametrize('level', (2, 3, MAX_LEVEL))
def test_higher_levels_replace_the_meaningful_xor_with_or_and_sub(level):
    program, _ = _program(generate_assembly('dev-decomposition', level))
    assert any(op == 'or' and args[1] == '90' for op, args in program)
    assert any(op == 'and' and args[1] == '90' for op, args in program)
    assert not any(op == 'xor' and args[1] == '90' for op, args in program)
    assert len(program) < 128


def test_emitted_profile_has_only_full_width_ports_one_output_store_and_tail_jump():
    source = generate_assembly('dev-syntax', MAX_LEVEL)
    program, labels = _program(source)
    assert '.section .drectve,"yn"' in source
    assert ' /EXPORT:bounded_core /EXPORT:bounded_update' in source
    assert program[labels['bounded_update']] == ('jmp', ['bounded_core'])
    assert sum(bool(args) and args[0] == 'qword ptr [r8]' for _, args in program) == 1
    assert {op for op, _ in program} <= {'mov', 'add', 'sub', 'xor', 'and', 'or', 'cmp',
                                        'nop', 'ret', 'ja', 'jae', 'jb', 'jbe', 'jmp'}
    assert not re.search(r'\b(?:eax|ecx|edx|r8d|r9d|r10d|r11d|esp|ebp|ax|al|push|pop|call|lea)\b', source)
    for _, args in program:
        if len(args) == 2 and args[0] != 'qword ptr [r8]':
            assert args[0] in (*VOLATILE_SCRATCH, 'rcx', 'rdx')


@pytest.mark.parametrize('kwargs', [
    {'seed': None}, {'seed': b'bytes'}, {'seed': 'a' * 4097}, {'seed': '\ud800'},
    {'seed': 'dev', 'level': -1}, {'seed': 'dev', 'level': MAX_LEVEL + 1},
    {'seed': 'dev', 'level': True}, {'seed': 'dev', 'level': 1.0},
    {'seed': 'dev', 'mutation': 1},
])
def test_invalid_generator_inputs_fail_closed(kwargs):
    with pytest.raises(ValueError):
        generate_assembly(**kwargs)


@pytest.fixture(scope='module')
def compiled_development_targets():
    parent = os.environ.get('FDISBULL_REWRITE_TEST_ROOT')
    if not parent:
        pytest.skip('Select an admitted external FDISBULL_REWRITE_TEST_ROOT for compiler checks')
    parent = Path(parent)
    if not parent.is_absolute() or not parent.is_dir():
        pytest.fail('FDISBULL_REWRITE_TEST_ROOT must be an existing absolute artifact parent')
    clang = os.environ.get('FDISBULL_REWRITE_CLANG') or shutil.which('clang')
    linker = os.environ.get('FDISBULL_REWRITE_LINKER') or shutil.which('lld-link')
    if not clang or not linker:
        pytest.skip('An existing Windows-target clang and lld-link are required')
    pytest.importorskip('pefile')
    pytest.importorskip('unicorn')
    directory = Path(tempfile.mkdtemp(prefix='development-', dir=parent))
    environment = os.environ | {'TMPDIR': str(directory)}
    paths = {}
    for name, seed, level, mutation in (
        ('reference', 'dev-compiled-reference', 0, False),
        ('rewrite-one', 'dev-compiled-one', 1, False),
        ('rewrite-two', 'dev-compiled-two', 2, False),
        ('rewrite-three', 'dev-compiled-three', 3, False),
        ('mutation', 'dev-compiled-mutation', 2, True),
    ):
        source, obj, target = (directory / (name + suffix) for suffix in ('.s', '.obj', '.dll'))
        source.write_text(generate_assembly(seed, level, mutation))
        subprocess.run([clang, '--target=x86_64-pc-windows-msvc', '-c', str(source), '-o', str(obj)],
                       check=True, capture_output=True, text=True, timeout=30, env=environment)
        subprocess.run([linker, '/dll', '/noentry', '/nodefaultlib', '/machine:x64', '/fixed',
                        '/opt:noref', '/opt:noicf', '/timestamp:0', '/out:' + str(target), str(obj)],
                       check=True, capture_output=True, text=True, timeout=30, env=environment)
        paths[name] = target
    spec = importlib.util.spec_from_file_location('rewrite_test_curriculum', ROOT / 'scripts/verify_bla_curriculum.py')
    curriculum = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(curriculum)
    return paths, curriculum


def test_compiled_exports_actual_reachable_instructions_and_full_width_operands(compiled_development_targets):
    capstone = pytest.importorskip('capstone')
    paths, curriculum = compiled_development_targets
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    core_bytes = []
    for name, target in paths.items():
        pe, identity = curriculum.inspect_pe(target)
        assert set(identity['exports']) == {'bounded_core', 'bounded_update'}
        start = identity['exports']['bounded_core']
        stop = identity['exports']['bounded_update']
        code = pe.get_data(start, stop - start)
        core_bytes.append(code)
        decoded = list(decoder.disasm(code, identity['image_base'] + start))
        assert sum(ins.size for ins in decoded) == len(code)
        assert decoded[-1].mnemonic == 'ret'
        assert all(ins.mnemonic not in ('lea', 'call', 'push', 'pop') for ins in decoded)
        for ins in decoded:
            for operand in ins.operands:
                if operand.type in (capstone.x86.X86_OP_REG, capstone.x86.X86_OP_MEM):
                    assert operand.size == 8
    assert len(set(core_bytes)) == len(paths)


def test_real_compiled_functions_match_boundary_oracle_abi_and_ordered_writes(compiled_development_targets):
    paths, curriculum = compiled_development_targets
    for name, target in paths.items():
        observed = curriculum.exercise(target, curriculum.case_vectors(), mutation=name == 'mutation')
        assert observed['rejected_output_writes'] == 0
        assert observed['write_counts']['stack'] == 0 and observed['write_counts']['image'] == 0
        if name != 'mutation':
            assert observed['agreement'] == observed['cases']
        else:
            assert observed['mismatches'] and all(row['x'] == row['limit'] for row in observed['mismatches'])


@pytest.mark.parametrize('name', ('rewrite-one', 'rewrite-two', 'rewrite-three', 'mutation'))
def test_actual_reachable_regions_prove_or_replay_deliberate_guard_difference(compiled_development_targets, name):
    pytest.importorskip('z3')
    paths, curriculum = compiled_development_targets
    rows = curriculum.core_comparison(paths['reference'], paths[name], mutation=name == 'mutation')
    assert len(rows) == 2
    if name == 'mutation':
        assert any(row['proof']['status'] == 'different' and row['witness_replay'] for row in rows)
    else:
        assert all(row['proof']['status'] == 'equivalent_under_contract' for row in rows)
        assert all(row['contraction_expansion_verified'] for row in rows)


def test_same_seed_mutation_changes_only_the_two_guard_conditions():
    normal, normal_labels = _program(generate_assembly('dev-isolated-mutation', 2))
    mutated, mutated_labels = _program(generate_assembly('dev-isolated-mutation', 2, mutation=True))
    assert normal_labels == mutated_labels and len(normal) == len(mutated)
    changed = [(a, b) for a, b in zip(normal, mutated, strict=True) if a != b]
    assert len(changed) == 2
    assert all(a[1] == b[1] and (a[0], b[0]) in {('ja', 'jae'), ('jb', 'jbe'), ('jae', 'ja')}
               for a, b in changed)
