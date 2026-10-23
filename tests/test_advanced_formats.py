"""One generic register-indirect rule through actual native file mappings."""
import hashlib
import json
import struct

import pytest

from fdisbull.project import Project
from fixtures_formats import macho_arm64, pe64
from test_dos_loader import mz_file


CASES = ('pe_x86_64', 'elf_x86_64', 'macho_arm64', 'mz_x86_16',
         'raw_x86_64', 'raw_x86_32', 'raw_arm64')


def _body(arch, bits, entry, segmented=False):
    """Set a register to entry+32, jump through it, and return at that target."""
    if arch == 'arm64':
        data = bytearray(bytes.fromhex('1f2003d5') * 16)  # NOP padding
        # ADR X16,entry+32; BR X16. ADR is a native constant-address producer.
        code, end, register = bytes.fromhex('1001001000021fd6'), bytes.fromhex('c0035fd6'), 'x16'
        jump_offset = 4
    else:
        data, end = bytearray(b'\x90' * 64), b'\xc3'
        register = {16: 'ax', 32: 'eax', 64: 'rax'}[bits]
        if bits == 64:
            # LEA RAX,[RIP+25]; JMP RAX, valid at high PE preferred addresses.
            code, jump_offset = bytes.fromhex('488d0519000000ffe0'), 7
        elif bits == 32:
            code, jump_offset = b'\xb8' + struct.pack('<I', entry + 32) + b'\xff\xe0', 5
        else:
            code, jump_offset = b'\xb8' + struct.pack('<H', 32 if segmented else entry + 32) + b'\xff\xe0', 3
    data[:len(code)] = code
    data[32:32 + len(end)] = end
    return bytes(data), entry + jump_offset, register


def _elf64(code):
    """Minimal ELF64 ET_EXEC/PT_LOAD fixture, without an external compiler.

    Like the compiler-built ELF fixtures in test_loading.py this has an x86-64
    executable mapping and an explicit native entry. No symbol/section table
    is needed for loader or recursive-analysis qualification.
    """
    data = bytearray(512)
    data[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 2, 62, 1, 0x400100, 64, 0, 0,
                     64, 56, 1, 64, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0x400000, 0x400000, len(data), len(data), 0x1000)
    data[0x100:0x100 + len(code)] = code
    return bytes(data)


def build_format_case(case):
    """Return actual file bytes, loader arguments and expected target identity."""
    if case == 'pe_x86_64':
        arch, bits, entry, format_ = 'x86', 64, 0x140001000, 'PE'
        code, jump, register = _body(arch, bits, entry)
        data = bytearray(pe64())
        # Remove the unrelated export seed from the base fixture. The target
        # must be admitted by bounded indirect recovery, not export traversal.
        struct.pack_into('<II', data, 0x98 + 112, 0, 0)
        data[0x200:0x200 + len(code)] = code
        options = {}
    elif case == 'elf_x86_64':
        arch, bits, entry, format_ = 'x86', 64, 0x400100, 'ELF'
        code, jump, register = _body(arch, bits, entry)
        data, options = _elf64(code), {}
    elif case == 'macho_arm64':
        arch, bits, entry, format_ = 'arm64', 64, 0x100000100, 'Mach-O'
        code, jump, register = _body(arch, bits, entry)
        data = bytearray(macho_arm64())
        data[0x100:0x100 + len(code)] = code
        options = {}
    elif case == 'mz_x86_16':
        arch, bits, entry, format_ = 'x86', 16, 0x10000, 'MZ'
        code, jump, register = _body(arch, bits, entry, segmented=True)
        data, options = mz_file(code), {}
    elif case in ('raw_x86_64', 'raw_x86_32', 'raw_arm64'):
        arch, bits = ('arm64', 64) if case == 'raw_arm64' else ('x86', int(case.rsplit('_', 1)[1]))
        entry, format_ = 0x1000, 'raw'
        data, jump, register = _body(arch, bits, entry)
        options = dict(arch=arch, bits=bits, base=entry)
    else:
        raise ValueError('unknown qualification case')
    return dict(case=case, data=bytes(data), options=options, format=format_, arch=arch,
                bits=bits, entry=entry, jump=jump, target=entry + 32, register=register)


def qualify_format_case(case, directory):
    """Run the public API and return evidence suitable for a compact receipt."""
    fixture = build_format_case(case)
    binary, database = directory / (case + '.bin'), directory / (case + '.fdb')
    binary.write_bytes(fixture['data'])
    with Project.create(database, binary, **fixture['options']) as project:
        assert (project.meta['format'], project.arch, project.bits, project.meta['entry']) == (
            fixture['format'], fixture['arch'], fixture['bits'], fixture['entry'])
        context = 'x86:16:little:cs=1000' if fixture['format'] == 'MZ' else project.context
        target_key = f'{fixture["target"]:016x}'
        assert not project.db.execute('SELECT 1 FROM instructions WHERE version=1 AND context=? AND address=?',
                                      (context, target_key)).fetchone()
        result = project.auto_analyze(max_instructions=128, max_functions=16, max_steps=1024,
                                      max_entries=16, max_rounds=8)
        assert result['stable'] and not result['budget_exhausted'], result
        # The native entry pass stops at the unknown register jump. The target
        # return is decoded only after the generic pass admits its new edge.
        assert [run['decoded'] for run in result['base_runs']] == [2, 1]
        assert project.db.execute('SELECT 1 FROM instructions WHERE version=1 AND context=? AND address=?',
                                 (context, target_key)).fetchone()
        address = '1000:0000' if fixture['format'] == 'MZ' else fixture['entry']
        function = project.function_analysis(address)
        assert function['state'] == 'done' and not function['stale']
        candidates = [item for item in function['result']['indirect']['candidates']
                      if item['target'] == fixture['target']]
        assert candidates and all(item['admitted'] for item in candidates)
        edge = project.db.execute("SELECT evidence FROM xrefs WHERE version=1 AND context=? AND source=? AND target=? AND kind='resolved_branch'",
                                  (context, f'{fixture["jump"]:016x}', target_key)).fetchone()
        assert edge and json.loads(edge[0])['rule'] == 'bounded_indirect'
        generation = function['generation']
        assert project.auto_analyze(max_instructions=128, max_functions=16, max_steps=1024,
                                    max_entries=16, max_rounds=8)['processed_jobs'] == 0
        assert project.function_analysis(address)['generation'] == generation
        receipt = dict(case=case, format=fixture['format'], arch=fixture['arch'], bits=fixture['bits'],
                       input_sha256=hashlib.sha256(fixture['data']).hexdigest(), input_bytes=len(fixture['data']),
                       entry=hex(fixture['entry']), transfer=hex(fixture['jump']), target=hex(fixture['target']),
                       context=context, register=fixture['register'], stable=result['stable'],
                       rounds=result['rounds'], resolved_rule='bounded_indirect', target_decoded=True,
                       native_pass_decoded=[run['decoded'] for run in result['base_runs']],
                       native_validation=candidates[0]['native_validation'],
                       candidate_expression=candidates[0]['expression'],
                       repeated_jobs=0, runtime_observed=False)
    # A separate Project instance proves that evidence and the target survive
    # reopening without requiring or running the original executable.
    binary.unlink()
    with Project(database) as project:
        assert project.function_analysis(address)['state'] == 'done'
        assert project.advanced_status()['stable']
    receipt['restart_without_source'] = True
    return receipt


@pytest.mark.parametrize('case', CASES)
def test_public_auto_analysis_recovers_same_register_indirect_rule(case, tmp_path):
    receipt = qualify_format_case(case, tmp_path)
    assert receipt['resolved_rule'] == 'bounded_indirect'
    assert receipt['runtime_observed'] is False
