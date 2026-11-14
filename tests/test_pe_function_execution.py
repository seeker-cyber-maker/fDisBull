"""Independent CPU evidence for a returning function that changes its callee.

The test program mirrors self_modifying_call_wine.S. The expected result below
comes from its source contract, rather than the symbolic instruction model.
"""
from copy import deepcopy
import hashlib

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.wine_arch import register_names


BASE, STACK, OUT = 0x1000, 0x8008, 0x3000
SENTINELS = (0x8877665544332211, 0x1122334455667788)
RBX_SEED = 0xaabbccddeeff0011
MODE = 'single_threaded_calls_smc'


def _program(mutation=2):
    """Assemble only this fixture's declared opcodes and local relocations."""
    code, labels, relocations = bytearray(), {}, []
    def mark(name):
        labels[name] = len(code)
    def emit(hex_bytes):
        code.extend(bytes.fromhex(hex_bytes))
    def relative(opcode, target, width):
        code.extend(bytes.fromhex(opcode))
        relocations.append((len(code), target, width))
        code.extend(bytes(width))
    mark('smc_function')
    emit('4883ec18 48895c2410 4889cb 4883f90a')
    relative('77', 'smc_reject', 1)
    relative('e8', 'smc_value', 4)
    mark('smc_first_return')
    emit('488902')
    relative('e8', 'smc_prepare', 4)
    mark('smc_prepare_return')
    relative('e8', 'smc_value', 4)
    mark('smc_second_return')
    emit('48894208')
    relative('eb', 'smc_epilogue', 1)
    mark('smc_reject')
    emit('48c7c0ffffffff')
    mark('smc_epilogue')
    emit('488b5c2410 4883c418 c3')
    mark('smc_prepare')
    relative('e8', 'smc_writer', 4)
    mark('smc_writer_return')
    emit('c3')
    mark('smc_writer')
    # RIP is after the trailing immediate byte, not just after disp32.
    emit('c605')
    displacement = len(code)
    emit('00000000')
    code.append(mutation)
    mark('smc_after_store')
    emit('c3')
    mark('smc_value')
    mark('smc_constant')
    emit('b8')
    mark('smc_constant_immediate')
    emit('01000000 9090909090 4801c8 c3')
    mark('smc_function_end')
    mark('smc_gate')
    relative('e8', 'smc_function', 4)
    mark('smc_gate_return')
    emit('90c3')
    for position, name, width in relocations:
        code[position:position + width] = (labels[name] - position - width).to_bytes(width, 'little', signed=True)
    code[displacement:displacement + 4] = (labels['smc_constant_immediate'] - displacement - 5).to_bytes(4, 'little', signed=True)
    return bytes(code), {name: BASE + offset for name, offset in labels.items()}


def _contract():
    _, labels = _program()
    return {'entry_registers': {'rsp': hex(STACK), 'rdx': hex(OUT)},
            'memory_model': 'private_ordinary_ram',
            'memory_ranges': [{'address': hex(OUT), 'length': 16},
                              {'address': hex(STACK - 40), 'length': 48}],
            'entry_memory': [{'address': hex(STACK), 'hex': labels['smc_gate_return'].to_bytes(8, 'little').hex()}]}


def _path(x, mutation=2, *, initial_constant=1):
    import unicorn
    from unicorn import x86_const as reg
    code, labels = _program(mutation)
    code = bytearray(code)
    code[labels['smc_constant_immediate'] - BASE] = initial_constant
    code = bytes(code)
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for address in (BASE, OUT, 0x7000, 0x8000):
        cpu.mem_map(address, 4096)
    cpu.mem_write(BASE, code)
    cpu.mem_write(STACK - 40, bytes(range(48)))
    cpu.mem_write(STACK, labels['smc_gate_return'].to_bytes(8, 'little'))
    cpu.mem_write(OUT, b''.join(v.to_bytes(8, 'little') for v in SENTINELS))
    for name, value in {'rax': 0xfedcba9876543210, 'rbx': RBX_SEED, 'rcx': x,
                        'rdx': OUT, 'rsp': STACK}.items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), value)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    def ram():
        return [{'address': row['address'], 'hex': bytes(cpu.mem_read(int(row['address'], 16), row['length'])).hex()}
                for row in _contract()['memory_ranges']]
    def image():
        return [{'address': hex(BASE), 'hex': bytes(cpu.mem_read(BASE, len(code))).hex()}]
    entry, code_entry, events, versions = ram(), image(), [], []
    def version(after_event, raw):
        versions.append({'after_event': after_event, 'address': hex(BASE), 'hex': raw.hex(),
                         'image': [{'address': hex(BASE), 'hex': raw.hex()}],
                         'sha256': hashlib.sha256(raw).hexdigest()})
    version(0, code)
    def before(guest, address, size, _):
        events.append({'address': hex(address), 'project_address': hex(address),
                       'bytes': bytes(guest.mem_read(address, size)).hex(),
                       'registers': {'rip': hex(address),
                         'rflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)), 'thread': 17,
                         'general': {n: hex(guest.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                     for n in register_names(64) - {'rip', 'rflags'}}}})
    def write(guest, access, address, size, value, _):
        if BASE <= address < BASE + len(code):
            raw = bytearray(guest.mem_read(BASE, len(code)))
            raw[address - BASE:address - BASE + size] = value.to_bytes(size, 'little')
            version(len(events), bytes(raw))
    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.hook_add(unicorn.UC_HOOK_MEM_WRITE, write)
    cpu.emu_start(BASE, labels['smc_gate_return'] + 1, count=64)
    assert events[-1]['address'] == hex(labels['smc_gate_return'])
    normalize_trace('wine-qemu', events, version=1)
    result = {'trace': {'mapping': {'backend': 'wine-qemu', 'bits': 64,
               'capture_provider': 'independent-unicorn', 'source_sha256': 'a' * 64,
               'version_sha256': 'b' * 64}, 'version': 1, 'semantics': PE_TRACE_SEMANTICS,
               'complete': True, 'events': events},
              'memory': {'entry': entry, 'exit': ram()},
              'code': {'entry': code_entry, 'exit': image(),
                       'versions': [{'after_event': row['after_event'], 'image': row['image']}
                                    for row in versions]}, 'code_versions': versions}
    _assert_source_sample(result, x, mutation, initial_constant)
    return result


def _assert_source_sample(path, x, mutation, initial_constant=1):
    """Check actual CPU results and surviving writes against source arithmetic."""
    _, labels = _program(mutation)
    last = path['trace']['events'][-1]['registers']['general']
    assert int(last['rsp'], 16) == STACK + 8
    assert int(last['rbx'], 16) == RBX_SEED
    assert int(last['rcx'], 16) == x
    final = {int(row['address'], 16) + k: b for row in path['memory']['exit']
             for k, b in enumerate(bytes.fromhex(row['hex']))}
    word = lambda address: int.from_bytes(bytes(final[address + k] for k in range(8)), 'little')
    assert word(STACK - 8) == RBX_SEED
    assert word(STACK) == labels['smc_gate_return']
    if x <= 10:
        assert int(last['rax'], 16) == x + mutation
        assert [word(OUT), word(OUT + 8)] == [x + initial_constant, x + mutation]
        assert word(STACK - 32) == labels['smc_second_return']
        assert word(STACK - 40) == labels['smc_writer_return']
        constants = [int.from_bytes(bytes.fromhex(e['bytes'])[1:5], 'little') for e in path['trace']['events']
                     if int(e['address'], 16) == labels['smc_constant']]
        assert constants == [initial_constant, mutation]
        assert len(path['code_versions']) == 2
    else:
        assert int(last['rax'], 16) == (1 << 64) - 1
        assert [word(OUT), word(OUT + 8)] == list(SENTINELS)
        assert len(path['code_versions']) == 1
    code = bytes.fromhex(path['code']['exit'][0]['hex'])
    assert code[labels['smc_constant_immediate'] - BASE] == (mutation if x <= 10 else initial_constant)


def _family(mutation=2):
    return [_path(3, mutation), _path(11, mutation)]


def verify_source_spec(recovery, contract, symbols, mutation=2):
    """Prove recovered guarded expressions equal this independently written rule.

    ``symbols`` contains runtime addresses (including the native load delta),
    so the same checker applies to the real PE image and independent CPU input.
    FLAGS are intentionally checked through CPU steps and the instruction model,
    rather than claiming a separate source-level FLAGS derivation here.
    """
    import z3 as z
    address = lambda name: int(symbols[name], 16) if isinstance(symbols[name], str) else symbols[name]
    registers = {n: z.BitVec('entry_' + n, 64) for n in recovery['cases'][0]['registers']}
    cells = {a + k: z.BitVec(f'entry_ram_{a + k:x}', 8)
             for row in contract['memory_ranges'] for a in [int(row['address'], 16)]
             for k in range(row['length'])}
    declarations = {str(v): v for v in [*registers.values(), *cells.values()]}
    declarations['entry_flags'] = z.BitVec('entry_flags', 32)
    assumptions = [registers[n] == int(v, 16) for n, v in contract['entry_registers'].items()]
    for row in contract['entry_memory']:
        start = int(row['address'], 16)
        assumptions += [cells[start + k] == byte for k, byte in enumerate(bytes.fromhex(row['hex']))]
    x = registers['rcx']
    stack, out = (int(contract['entry_registers'][n], 16) for n in ('rsp', 'rdx'))
    accepted = z.ULE(x, 10)
    target = address('smc_gate_return')
    assert int(recovery['call_frame']['return_target'], 16) == target
    assert recovery['call_frame']['stack_pointer_delta'] == 8
    program, local_symbols = _program(mutation)
    for name, local in local_symbols.items():
        if name in symbols:
            assert address(name) - address('smc_function') == local - BASE
    def parse(text, sort):
        value = z.Const('source_spec_result', sort)
        assertion = z.parse_smt2_string('(assert (= source_spec_result ' + text + '))',
                decls=declarations | {'source_spec_result': value})[0]
        return assertion.arg(1)
    def bv64(value):
        return z.BitVecVal(value, 64)
    checked = 0
    for case in recovery['cases']:
        active = len(case['internal_calls']) == 4
        assert len(case['internal_calls']) in (0, 4)
        guard = parse(case['guard'], z.BoolSort())
        deviations = []
        for name, text in case['registers'].items():
            expected = (z.If(accepted, x + mutation, bv64((1 << 64) - 1)) if name == 'rax' else
                        registers[name] + 8 if name == 'rsp' else registers[name])
            deviations.append(parse(text, z.BitVecSort(64)) != expected)
        def byte_of(value, offset):
            return z.Extract(offset * 8 + 7, offset * 8, value)
        for key, text in case['memory_bytes'].items():
            a = int(key, 16)
            if stack - 8 <= a < stack:
                expected = byte_of(registers['rbx'], a - stack + 8)
            else:
                candidate = None
                if out <= a < out + 8:
                    candidate = byte_of(x + 1, a - out)
                elif out + 8 <= a < out + 16:
                    candidate = byte_of(x + mutation, a - out - 8)
                elif stack - 32 <= a < stack - 24:
                    candidate = byte_of(bv64(address('smc_second_return')), a - stack + 32)
                elif stack - 40 <= a < stack - 32:
                    candidate = byte_of(bv64(address('smc_writer_return')), a - stack + 40)
                expected = cells[a] if candidate is None else z.If(accepted, candidate, cells[a])
            deviations.append(parse(text, z.BitVecSort(8)) != expected)
        for key, text in case['code_bytes'].items():
            a = int(key, 16)
            original = program[a - address('smc_function')]
            expected = z.If(accepted, z.BitVecVal(mutation, 8), z.BitVecVal(original, 8)) \
                if a == address('smc_constant_immediate') else z.BitVecVal(original, 8)
            deviations.append(parse(text, z.BitVecSort(8)) != expected)
        accesses = [('write', stack - 8, 8, registers['rbx'])]
        if active:
            first, prepare, second, writer = [bv64(address(n)) for n in
                    ('smc_first_return', 'smc_prepare_return', 'smc_second_return', 'smc_writer_return')]
            accesses += [('write', stack - 32, 8, first), ('read', stack - 32, 8, first),
                         ('write', out, 8, x + 1), ('write', stack - 32, 8, prepare),
                         ('write', stack - 40, 8, writer),
                         ('write', address('smc_constant_immediate'), 1, z.BitVecVal(mutation, 8)),
                         ('read', stack - 40, 8, writer), ('read', stack - 32, 8, prepare),
                         ('write', stack - 32, 8, second), ('read', stack - 32, 8, second),
                         ('write', out + 8, 8, x + mutation)]
        accesses += [('read', stack - 8, 8, registers['rbx']), ('read', stack, 8, bv64(target))]
        for actual, (kind, a, width, value) in zip(case['ordered_accesses'], accesses, strict=True):
            assert actual['kind'] == kind and actual['width'] == width
            deviations += [parse(actual['address'], z.BitVecSort(64)) != a,
                           parse(actual['value'], z.BitVecSort(width * 8)) != value]
        solver = z.Solver()
        solver.set(timeout=5000)
        solver.add(*assumptions, guard != (accepted if active else z.Not(accepted)))
        assert solver.check() == z.unsat
        solver = z.Solver()
        solver.set(timeout=5000)
        solver.add(*assumptions, guard, z.Or(*deviations))
        assert solver.check() == z.unsat
        checked += 1
    return {'status': 'proved_under_entry_contract', 'cases': checked,
            'checked': ['unsigned complete branch domains', 'all selected GPRs and final stack',
                        'output pair and surviving spill/call/return-slot bytes', 'all final code bytes',
                        'ordered RAM and code access addresses, widths and values'],
            'flags': 'Not separately source-derived; checked against CPU steps and retained live in comparison'}


def _compare(a, b, **kwargs):
    from fdisbull.pe_function_recovery import compare_pe_functions
    return compare_pe_functions(a, b, contract=_contract(), execution_mode=MODE, **kwargs)


def test_independent_cpu_executes_the_same_instruction_before_and_after_write():
    for x in (0, 3, 10, 11, (1 << 64) - 1):
        path = _path(x)
        assert len(path['trace']['events']) <= 64


def test_internal_calls_and_reachable_mutation_recover_complete_function():
    a, b = _family(), _family()
    frozen = deepcopy((a, b))
    result = _compare(a, b)
    assert result['status'] == 'equivalent_under_contract', result
    assert all(v['status'] == 'complete' for v in result['coverage'].values())
    assert sorted(len(p['ordered_accesses']) for p in result['baseline_recovery']['cases']) == [3, 14]
    _, symbols = _program()
    for key in ('baseline_recovery', 'layer_recovery'):
        assert verify_source_spec(result[key], _contract(), symbols)['status'] == 'proved_under_entry_contract'
    assert (a, b) == frozen
    from fdisbull.pe_function_recovery import expand_pe_function_contraction
    assert expand_pe_function_contraction(result['contraction'], a, b) == {'baseline': a, 'layer': b}


def test_changed_internal_writer_has_a_concrete_memory_and_return_witness():
    result = _compare(_family(2), _family(3))
    assert result['status'] == 'different', result
    witness = result['counterexample']
    assert int(witness['entry_general']['rcx'], 16) <= 10
    assert witness['differing_live_registers']['rax']
    assert witness['differing_memory_bytes']
    # Independent execution confirms the symbolic witness against source.
    for mutation in (2, 3):
        _path(int(witness['entry_general']['rcx'], 16), mutation)


def test_execution_mode_still_requires_complete_branch_coverage():
    result = _compare(_family()[:1], _family())
    assert result['status'] == 'incomplete_path_coverage', result


def test_identical_byte_store_still_requires_a_separate_preserved_version():
    a, b = _family(1), _family(1)
    assert a[0]['code']['versions'][0]['image'] == a[0]['code']['versions'][1]['image']
    result = _compare(a, b)
    assert result['status'] == 'equivalent_under_contract', result
    active = next(c for c in result['baseline_recovery']['cases'] if c['internal_calls'])
    assert len(active['code_versions']) == 2
    assert len(active['code_writes']) == 1
    a[0]['code']['versions'].pop()
    result = _compare(a, b)
    assert result['status'] == 'unknown', result
    assert 'version' in result['reason'].lower()


def test_forged_prewrite_fetch_or_final_code_fails_closed():
    a = _family()
    _, labels = _program()
    repeat = [e for e in a[0]['trace']['events'] if int(e['address'], 16) == labels['smc_constant']]
    repeat[1]['bytes'] = repeat[0]['bytes']
    result = _compare(a, _family())
    assert result['status'] == 'unknown', result
    b = _family()
    b[0]['code']['exit'] = deepcopy(b[0]['code']['entry'])
    result = _compare(b, _family())
    assert result['status'] == 'unknown', result


def test_unaccounted_initial_code_or_missing_return_slot_stays_unknown():
    a = _family()
    a[0]['code']['entry'][0]['hex'] = a[0]['code']['entry'][0]['hex'][:-2]
    result = _compare(a, _family())
    assert result['status'] == 'unknown', result
    a = _family()
    # The first callee returns through the word just written by CALL.
    _, labels = _program()
    event = next(e for e in a[0]['trace']['events'] if int(e['address'], 16) == labels['smc_first_return'])
    event['registers']['general']['rsp'] = hex(STACK - 16)
    result = _compare(a, _family())
    assert result['status'] == 'unknown', result


def test_stable_leaf_default_does_not_accept_intra_execution_epochs():
    from fdisbull.pe_function_recovery import compare_pe_functions
    result = compare_pe_functions(_family(), _family(), contract=_contract())
    assert result['status'] == 'unknown', result
