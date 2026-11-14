"""Known-source module execution and explicitly simulated external contracts.

Unicorn executes the authored PE instruction stream, including real CALL stack
writes and self-modification. API actions in this unit fixture are declared
simulations, independently checked against real Wine by the native acceptance
test. They do not constitute execution of the Windows/Wine implementations.
"""
from copy import deepcopy
import hashlib

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.wine_arch import register_names
from test_pe_function_execution import _program as _function_program


BASE, DATA, IAT, STACK = 0x1000, 0x3000, 0x3100, 0x9008
SENTINELS = (0x8877665544332211, 0x1122334455667788)
IMPORTS = ('SetLastError', 'GetLastError', 'ExitProcess')
TARGETS = {name: 0x20000 + i * 16 for i, name in enumerate(IMPORTS)}


def _program(mutation=2, exit_code=7, *, base=BASE, data_address=DATA, import_iat=None):
    """Manually assemble the module fixture, keeping source data/ABI explicit."""
    code, labels, relocations = bytearray(), {}, []
    data_names = ('smc_input', 'smc_output', 'rejected_output', 'accepted_value',
                  'rejected_value', 'observed_last_error')
    slots = import_iat or {n: IAT + i * 8 for i, n in enumerate(IMPORTS)}
    labels.update(zip(data_names, (data_address + k for k in (0, 8, 24, 40, 48, 56))))
    labels.update(smc_data_start=data_address, smc_data_end=data_address + 64)
    def mark(name):
        labels[name] = base + len(code)
    def emit(raw):
        code.extend(bytes.fromhex(raw))
    def relative(opcode, target, suffix=b''):
        emit(opcode)
        relocations.append((len(code), target, len(suffix)))
        code.extend(bytes(4))
        code.extend(suffix)
    mark('smc_module_entry')
    emit('4883ec28 48b8')
    code.extend(SENTINELS[0].to_bytes(8, 'little'))
    relative('488905', 'smc_output')
    relative('488905', 'rejected_output')
    emit('48b8')
    code.extend(SENTINELS[1].to_bytes(8, 'little'))
    relative('488905', data_address + 16)
    relative('488905', data_address + 32)
    for name in ('accepted_value', 'rejected_value', 'observed_last_error'):
        relative('48c705', name, bytes(4))
    relative('488b0d', 'smc_input')
    relative('488d15', 'smc_output')
    relative('e8', 'smc_function')
    mark('smc_module_accepted_return')
    relative('488905', 'accepted_value')
    emit('48c7c10b000000')
    relative('488d15', 'rejected_output')
    relative('e8', 'smc_function')
    mark('smc_module_rejected_return')
    relative('488905', 'rejected_value')
    emit('b934120000')
    mark('smc_set_last_error_call')
    relative('ff15', slots['SetLastError'])
    mark('smc_set_last_error_return')
    mark('smc_get_last_error_call')
    relative('ff15', slots['GetLastError'])
    mark('smc_get_last_error_return')
    relative('8905', 'observed_last_error')
    emit('b9')
    code.extend(exit_code.to_bytes(4, 'little'))
    mark('smc_module_before_exit')
    emit('90')
    mark('smc_exit_process_call')
    relative('ff15', slots['ExitProcess'])
    mark('smc_module_unreachable')
    emit('0f0b')
    function, symbols = _function_program(mutation)
    function_start = base + len(code)
    code.extend(function[:symbols['smc_function_end'] - BASE])
    labels.update({name: function_start + value - BASE for name, value in symbols.items()
                   if name not in ('smc_gate', 'smc_gate_return')})
    mark('smc_module_end')
    for position, target, suffix in relocations:
        value = labels[target] if isinstance(target, str) else target
        code[position:position + 4] = (value - base - position - 4 - suffix).to_bytes(4, 'little', signed=True)
    defaults = (3, 0xaaaaaaaaaaaaaaaa, 0xbbbbbbbbbbbbbbbb,
                0xcccccccccccccccc, 0xdddddddddddddddd,
                0xeeeeeeeeeeeeeeee, 0xffffffffffffffff, 0x5555555555555555)
    return bytes(code), labels, b''.join(v.to_bytes(8, 'little') for v in defaults)


def _contract():
    _, _, data = _program()
    iat = b''.join(TARGETS[n].to_bytes(8, 'little') for n in IMPORTS)
    return {'entry_registers': {'rsp': hex(STACK)},
            'memory_model': 'private_ordinary_ram',
            'memory_ranges': [{'address': hex(DATA), 'length': len(data)},
                              {'address': hex(IAT), 'length': len(iat)},
                              {'address': hex(STACK - 96), 'length': 104}],
            'entry_memory': [{'address': hex(DATA), 'hex': data.hex()},
                             {'address': hex(IAT), 'hex': iat.hex()}],
            'external_stack_ranges': [{'address': hex(STACK - 40), 'length': 32}]}


def _initialization():
    _, _, data = _program()
    return {'stage': 'pe-entry-after-loader', 'source_sha256': 'a' * 64,
            'entry_address': hex(BASE), 'image_base': '0x0',
            'memory': [{'address': hex(DATA), 'hex': data.hex()},
                       {'address': hex(IAT), 'hex': b''.join(TARGETS[n].to_bytes(8, 'little') for n in IMPORTS).hex()}],
            'tls_callbacks': [], 'clr': False,
            'imports': [{'name': n, 'iat_address': hex(IAT + i * 8), 'target': hex(TARGETS[n])}
                        for i, n in enumerate(IMPORTS)]}


def _path(mutation=2, exit_code=7, api_seed=0x11110000):
    """Execute only authored code; simulate imported actions at their boundaries."""
    import capstone
    import unicorn
    from unicorn import x86_const as reg
    code, labels, data = _program(mutation, exit_code)
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for a in (BASE, DATA, 0x8000, 0x9000, 0x20000):
        cpu.mem_map(a, 4096)
    cpu.mem_write(BASE, code)
    cpu.mem_write(DATA, data)
    cpu.mem_write(IAT, b''.join(TARGETS[n].to_bytes(8, 'little') for n in IMPORTS))
    cpu.mem_write(STACK - 96, bytes(range(104)))
    for name in register_names(64) - {'rip', 'rflags'}:
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()),
                      STACK if name == 'rsp' else 0xaabbccddeeff0011 if name == 'rbx' else 0)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    cpu.reg_write(reg.UC_X86_REG_RIP, BASE)
    disassembler = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    events, external, versions = [], [], []
    def registers():
        rip = cpu.reg_read(reg.UC_X86_REG_RIP)
        return {'rip': hex(rip), 'rflags': hex(cpu.reg_read(reg.UC_X86_REG_EFLAGS)), 'thread': 17,
                'general': {n: hex(cpu.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                            for n in register_names(64) - {'rip', 'rflags'}}}
    def memory():
        return [{'address': row['address'], 'hex': bytes(cpu.mem_read(int(row['address'], 16), row['length'])).hex()}
                for row in _contract()['memory_ranges']]
    def image():
        return [{'address': hex(BASE), 'hex': bytes(cpu.mem_read(BASE, len(code))).hex()}]
    entry, code_entry = memory(), image()
    versions.append({'after_event': 0, 'image': deepcopy(code_entry)})
    last_error = 0x9876
    while len(events) < 128:
        pc = cpu.reg_read(reg.UC_X86_REG_RIP)
        if not BASE <= pc < BASE + len(code):
            raise AssertionError('Unaccounted execution outside authored module')
        instruction = next(disassembler.disasm(bytes(cpu.mem_read(pc, 15)), pc))
        context = registers()
        events.append({'address': hex(pc), 'project_address': hex(pc),
                       'bytes': bytes(instruction.bytes).hex(), 'registers': context})
        cpu.emu_start(pc, BASE + len(code), count=1)
        if pc == labels['smc_writer']:
            versions.append({'after_event': len(events), 'image': image()})
        next_pc = cpu.reg_read(reg.UC_X86_REG_RIP)
        if next_pc not in TARGETS.values():
            continue
        name = next(n for n in IMPORTS if TARGETS[n] == next_pc)
        before, before_ram = registers(), memory()
        call_sp = cpu.reg_read(reg.UC_X86_REG_RSP)
        return_pc = int.from_bytes(cpu.mem_read(call_sp, 8), 'little')
        assert return_pc == pc + instruction.size
        action = {'event_index': len(events) - 1, 'name': name,
                  'iat_address': hex(IAT + IMPORTS.index(name) * 8), 'target': hex(next_pc),
                  'entry_registers': before, 'return_registers': None,
                  'memory': {'entry': before_ram, 'exit': None},
                  'code': {'entry': image(), 'exit': None}}
        if name == 'ExitProcess':
            observed_exit = cpu.reg_read(reg.UC_X86_REG_RCX) & 0xffffffff
            external.append(action)
            events.append({'address': hex(next_pc), 'bytes': 'c3', 'registers': before})
            break
        argument = cpu.reg_read(reg.UC_X86_REG_RCX) & 0xffffffff
        if name == 'SetLastError':
            last_error = argument
        for i, n in enumerate(('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')):
            cpu.reg_write(getattr(reg, 'UC_X86_REG_' + n.upper()), api_seed + 0x100 * len(external) + i)
        if name == 'GetLastError':
            # DWORD return contract leaves the upper half unconstrained.
            cpu.reg_write(reg.UC_X86_REG_RAX, (api_seed << 32) | last_error)
        cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
        cpu.reg_write(reg.UC_X86_REG_RSP, call_sp + 8)
        cpu.reg_write(reg.UC_X86_REG_RIP, return_pc)
        action['return_registers'] = registers()
        action['memory']['exit'] = memory()
        action['code']['exit'] = image()
        external.append(action)
    else:
        raise AssertionError('Module fixture exceeded its finite instruction budget')
    normalize_trace('wine-qemu', events, version=1)
    result = {'trace': {'mapping': {'backend': 'wine-qemu', 'bits': 64,
                 'capture_provider': 'independent-unicorn-with-declared-api-simulation',
                 'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64},
               'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'complete': True, 'events': events},
              'memory': {'entry': entry, 'exit': memory()},
              'code': {'entry': code_entry, 'exit': image(), 'versions': versions},
              'external_calls': external,
              'terminal': {'name': 'ExitProcess', 'exit_code': hex(observed_exit), 'process_exited': True}}
    _assert_source_sample(result, labels, mutation, exit_code)
    return result


def _assert_source_sample(path, symbols, mutation=2, exit_code=7):
    final = {int(row['address'], 16) + k: b for row in path['memory']['exit']
             for k, b in enumerate(bytes.fromhex(row['hex']))}
    word = lambda a: int.from_bytes(bytes(final[a + k] for k in range(8)), 'little')
    assert [word(symbols['smc_output']), word(symbols['smc_output'] + 8)] == [4, 3 + mutation]
    assert [word(symbols['rejected_output']), word(symbols['rejected_output'] + 8)] == list(SENTINELS)
    assert word(symbols['accepted_value']) == 3 + mutation
    assert word(symbols['rejected_value']) == (1 << 64) - 1
    assert word(symbols['observed_last_error']) == 0x1234
    assert [row['name'] for row in path['external_calls']] == list(IMPORTS)
    assert int(path['terminal']['exit_code'], 16) == exit_code
    assert len(path['code']['versions']) == 2
    code = bytes.fromhex(path['code']['exit'][0]['hex'])
    assert code[symbols['smc_constant_immediate'] - BASE] == mutation


def test_independent_cpu_module_initialization_calls_and_exit_observations():
    for mutation, code in ((2, 7), (3, 7), (2, 9)):
        _path(mutation, code)
    _path(api_seed=0x77770000)


def verify_source_spec(recovery, contract, symbols, mutation=2, exit_code=7, import_iat=None):
    """Prove the source-defined module outputs and final authored code bytes.

    External register, FLAGS and declared scratch effects are intentionally
    nondeterministic ABI outputs; they are not invented source expectations.
    This proves API arguments/state/results under the declared contracts; native
    validation must separately establish implementation observations and exit.
    """
    import z3 as z
    number = lambda v: int(v, 16) if isinstance(v, str) else v
    symbols = {n: number(v) for n, v in symbols.items()}
    base, data = symbols['smc_module_entry'], symbols['smc_data_start']
    code, expected_symbols, _ = _program(mutation, exit_code, base=base,
                                        data_address=data, import_iat=import_iat)
    for name, value in expected_symbols.items():
        if name in symbols:
            assert symbols[name] == value
    expected_data = (3, 4, 3 + mutation, *SENTINELS, 3 + mutation, (1 << 64) - 1, 0x1234)
    expected = {data + k: byte for k, byte in enumerate(b''.join(v.to_bytes(8, 'little') for v in expected_data))}
    registers = {n: z.BitVec('entry_' + n, 64) for n in register_names(64) - {'rip', 'rflags'}}
    cells = {a + k: z.BitVec(f'entry_ram_{a + k:x}', 8)
             for row in contract['memory_ranges'] for a in [int(row['address'], 16)]
             for k in range(row['length'])}
    declarations = {str(v): v for v in [*registers.values(), *cells.values()]}
    declarations['entry_flags'] = z.BitVec('entry_flags', 32)
    assumptions = [registers[n] == int(v, 16) for n, v in contract['entry_registers'].items()]
    for row in contract['entry_memory']:
        start = int(row['address'], 16)
        assumptions += [cells[start + k] == byte for k, byte in enumerate(bytes.fromhex(row['hex']))]
    def parse(text, sort):
        value = z.Const('module_source_result', sort)
        assertion = z.parse_smt2_string('(assert (= module_source_result ' + text + '))',
                decls=declarations | {'module_source_result': value})[0]
        return assertion.arg(1)
    checked = 0
    for case in recovery['cases']:
        declarations.update({name: z.BitVec(name, bits) for name, bits in case['external_symbols'].items()})
        guard = parse(case['guard'], z.BoolSort())
        deviations = [parse(case['last_error'], z.BitVecSort(32)) != 0x1234,
                      parse(case['exit_code'], z.BitVecSort(32)) != exit_code]
        assert [effect['name'] for effect in case['external_effects']] == list(IMPORTS)
        effects = case['external_effects']
        deviations += [parse(effects[0]['argument'], z.BitVecSort(32)) != 0x1234,
                       parse(effects[1]['return'], z.BitVecSort(32)) != 0x1234,
                       parse(effects[2]['argument'], z.BitVecSort(32)) != exit_code]
        for a, byte in expected.items():
            deviations.append(parse(case['memory_bytes'][hex(a)], z.BitVecSort(8)) != byte)
        for key, text in case['code_bytes'].items():
            a = int(key, 16)
            byte = mutation if a == symbols['smc_constant_immediate'] else code[a - base]
            deviations.append(parse(text, z.BitVecSort(8)) != byte)
        solver = z.Solver()
        solver.set(timeout=5000)
        solver.add(*assumptions, z.Not(guard))
        assert solver.check() == z.unsat
        solver = z.Solver()
        solver.set(timeout=5000)
        solver.add(*assumptions, guard, z.Or(*deviations))
        assert solver.check() == z.unsat
        checked += 1
    return {'status': 'proved_under_entry_and_external_contracts', 'cases': checked,
            'checked': ['module path guard', 'initialized input', 'accepted and rejected output pairs',
                        'accepted and rejected return records', 'DWORD last-error result', 'all final authored code bytes',
                        'SetLastError/GetLastError state and ExitProcess argument under the declared contracts'],
            'external_effects': 'Imported implementations, ABI effects and actual process termination require native validation'}


def _compare(a, b, *, initialization=None):
    from fdisbull.pe_module_recovery import compare_pe_modules
    return compare_pe_modules(a, b, contract=_contract(),
                              initialization=initialization or _initialization(), timeout_ms=10000)


def test_module_recovery_composes_initialization_internal_calls_and_api_contracts():
    a, b = [_path()], [_path(api_seed=0x77770000)]
    frozen = deepcopy((a, b))
    result = _compare(a, b)
    assert result['status'] == 'equivalent_under_contract', result
    _, symbols, _ = _program()
    for key in ('baseline_recovery', 'layer_recovery'):
        assert verify_source_spec(result[key], _contract(), symbols)['status'] == 'proved_under_entry_and_external_contracts'
    assert (a, b) == frozen


def test_module_writer_change_has_a_source_visible_difference_witness():
    result = _compare([_path(2)], [_path(3)])
    assert result['status'] == 'different', result
    assert result['counterexample']
    assert result['counterexample']['differing_memory_bytes']


def test_module_actual_termination_is_required_and_changed_exit_is_visible():
    a = [_path()]
    a[0]['terminal']['process_exited'] = False
    assert _compare(a, [_path()])['status'] == 'unknown'
    result = _compare([_path(exit_code=7)], [_path(exit_code=9)])
    assert result['status'] == 'different', result
    assert result['counterexample']


def test_module_entry_initialization_and_tls_exclusions_are_explicit():
    initial = _initialization()
    initial['memory'][0]['hex'] = '00' + initial['memory'][0]['hex'][2:]
    assert _compare([_path()], [_path()], initialization=initial)['status'] == 'unknown'
    initial = _initialization()
    initial['tls_callbacks'] = ['0x1000']
    assert _compare([_path()], [_path()], initialization=initial)['status'] == 'unknown'


def test_forged_api_identity_or_result_stays_unknown():
    a = [_path()]
    a[0]['external_calls'][0]['target'] = hex(TARGETS['GetLastError'])
    assert _compare(a, [_path()])['status'] == 'unknown'
    a = [_path()]
    returned = a[0]['external_calls'][1]['return_registers']['general']
    returned['rax'] = hex((int(returned['rax'], 16) & ~0xffffffff) | 0x9999)
    assert _compare(a, [_path()])['status'] == 'unknown'


def test_api_nonvolatile_clobber_or_undeclared_memory_write_stays_unknown():
    a = [_path()]
    a[0]['external_calls'][0]['return_registers']['general']['rbx'] = '0x123456'
    assert _compare(a, [_path()])['status'] == 'unknown'
    a = [_path()]
    memory = a[0]['external_calls'][0]['memory']['exit']
    memory[0]['hex'] = '00' + memory[0]['hex'][2:]
    assert _compare(a, [_path()])['status'] == 'unknown'


def test_module_code_versions_and_external_call_receipts_cannot_be_omitted():
    a = [_path()]
    a[0]['code']['versions'].pop()
    assert _compare(a, [_path()])['status'] == 'unknown'
    a = [_path()]
    a[0]['external_calls'].pop(0)
    assert _compare(a, [_path()])['status'] == 'unknown'

