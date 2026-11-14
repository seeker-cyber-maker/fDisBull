"""Independent source specification for the authored TLS/DllMain/report code.

These expectations use the source record layout, an eight-way event-log update,
and bit-level x86 flag definitions. They do not execute Wine or assume that a
loader invokes a callback. Optional corpus tests read sealed evidence only.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

z = pytest.importorskip('z3')

GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
MARKERS = {'tls-attach': 0x11, 'dll-attach': 0x22, 'report': 0x33,
           'tls-detach': 0x44, 'dll-detach': 0x55}
ARITHMETIC = 0x8d5


def _source_rule(contract):
    """Write the source's transfer independently of any instruction decoder."""
    phase = contract['phase']
    symbols = {name: int(v, 16) if isinstance(v, str) else v for name, v in contract['symbols'].items()}
    stack, caller = (int(contract[n], 16) for n in ('entry_rsp', 'return_address'))
    data, log = symbols['dll_data_start'], symbols['dll_event_log']
    initial = {name: z.BitVec('dll_entry_' + name, 64) for name in GPRS}
    flags = z.BitVec('dll_entry_flags', 32)
    ram = {a: z.BitVec(f'dll_entry_ram_{a:x}', 8) for a in [*range(data, data + 64), *range(stack, stack + 8)]}
    code_start = int(contract['entry_code']['address'], 16)
    code = {code_start + k: z.BitVecVal(b, 8) for k, b in enumerate(bytes.fromhex(contract['entry_code']['hex']))}
    word = lambda a, n: z.Concat(*[ram[a + k] for k in reversed(range(n))])
    count, stage, detach = (word(symbols[n], 4) for n in ('dll_event_count', 'dll_stage', 'dll_detach_flag'))
    assumptions = [initial['rsp'] == stack, (flags & 2) == 2, z.ULE(count, 7)]
    assumptions += [ram[stack + k] == (caller >> (8 * k)) & 255 for k in range(8)]
    if phase != 'report':
        assumptions.append(z.Extract(31, 0, initial['rdx']) == (1 if phase.endswith('attach') else 0))
    output = dict(ram)
    def store(address, value, width=4):
        output.update({address + k: z.Extract(k * 8 + 7, k * 8, value) for k in range(width)})
    # Select a DWORD slot, rather than copying the model's byte-address update.
    for slot in range(8):
        store(log + 4 * slot, z.If(count == slot, z.BitVecVal(MARKERS[phase], 32), word(log + 4 * slot, 4)))
    store(symbols['dll_event_count'], count + 1)
    accesses = []
    def access(kind, address, width, value):
        accesses.append((kind, z.BitVecVal(address, 64) if isinstance(address, int) else address, width, value))
    if phase == 'dll-attach':
        store(symbols['dll_seen_stage'], stage)
        access('read', symbols['dll_stage'], 4, stage)
        access('write', symbols['dll_seen_stage'], 4, stage)
    elif phase == 'report':
        store(symbols['dll_report_stage_seen'], stage)
        store(symbols['dll_report_count_seen'], count)
        access('read', symbols['dll_stage'], 4, stage)
        access('write', symbols['dll_report_stage_seen'], 4, stage)
        access('read', symbols['dll_event_count'], 4, count)
        access('write', symbols['dll_report_count_seen'], 4, count)
    elif phase.endswith('detach'):
        field = symbols['dll_tls_detach_stage_seen' if phase.startswith('tls-') else 'dll_dllmain_detach_stage_seen']
        store(field, stage)
        access('read', symbols['dll_stage'], 4, stage)
        access('write', field, 4, stage)
    access('read', symbols['dll_event_count'], 4, count)
    access('write', z.BitVecVal(log, 64) + z.ZeroExt(32, count) * 4, 4, z.BitVecVal(MARKERS[phase], 32))
    access('write', symbols['dll_event_count'], 4, count + 1)
    next_code = dict(code)
    constant = symbols['dll_report_constant_immediate']
    if phase.endswith('attach'):
        value = 1 if phase.startswith('tls-') else 2
        store(symbols['dll_stage'], z.BitVecVal(value, 32))
        next_code[constant] = z.BitVecVal(value + 1, 8)
        access('write', symbols['dll_stage'], 4, z.BitVecVal(value, 32))
        access('write', constant, 1, z.BitVecVal(value + 1, 8))
    elif phase == 'report':
        store(symbols['dll_stage'], z.BitVecVal(3, 32))
        access('write', symbols['dll_stage'], 4, z.BitVecVal(3, 32))
    else:
        changed = detach | (1 if phase.startswith('tls-') else 2)
        store(symbols['dll_detach_flag'], changed)
        access('read', symbols['dll_detach_flag'], 4, detach)
        access('write', symbols['dll_detach_flag'], 4, changed)
    access('read', stack, 8, z.BitVecVal(caller, 64))
    result = dict(initial)
    result.update(rsp=initial['rsp'] + 8, r9=z.BitVecVal(log, 64))
    result['rax'] = (z.BitVecVal(1, 64) if phase.startswith('dll-') else
                     z.ZeroExt(32, z.Concat(*[code[constant + k] for k in (3, 2, 1, 0)]))
                     if phase == 'report' else z.ZeroExt(32, count + 1))
    logical = phase.endswith('detach')
    value = detach | (1 if phase.startswith('tls-') else 2) if logical else count + 1
    bits = [z.Extract(k, k, value) == 1 for k in range(8)]
    parity = z.Not(z.Xor(*bits[:2]))
    for bit in bits[2:]:
        parity = z.Xor(parity, bit)
    conditions = {0: z.BoolVal(False) if logical else z.ULT(value, count), 2: parity,
                  4: ((count ^ 1 ^ value) & 0x10) != 0,
                  6: value == 0, 7: z.Extract(31, 31, value) == 1,
                  11: z.BoolVal(False) if logical else ((~(count ^ 1) & (count ^ value)) & 0x80000000) != 0}
    final_flags = flags & (~ARITHMETIC & 0xffffffff)
    for bit, condition in conditions.items():
        if logical and bit == 4:
            continue  # Logical OR leaves AF undefined, so it is never compared.
        final_flags |= z.If(condition, z.BitVecVal(1 << bit, 32), z.BitVecVal(0, 32))
    mask = 0xffffffef if logical else 0xffffffff
    return {'registers': result, 'flags': final_flags & mask, 'defined_flags_mask': mask,
            'memory_bytes': output, 'code_bytes': next_code, 'ordered_accesses': accesses,
            'assumptions': assumptions, 'variables': [*initial.values(), flags, *ram.values()]}


def verify_dll_source_spec(proof):
    """Prove every generic exported effect equals the independent source rule."""
    assert proof['status'] == 'proved_for_authored_dll_callback'
    rule, transfer = _source_rule(proof['contract']), proof['transfer']
    declarations = {name: z.Bool(name) if bits == 'Bool' else z.BitVec(name, bits)
                    for name, bits in proof['symbols'].items()}
    def parse(text, sort):
        value = z.Const('independent_source_value', sort)
        return z.parse_smt2_string('(assert (= independent_source_value ' + text + '))',
            decls=declarations | {'independent_source_value': value})[0].arg(1)
    assert transfer['defined_flags_mask'] == rule['defined_flags_mask']
    assert set(transfer['registers']) == set(GPRS)
    deviations = [parse(transfer['registers'][n], z.BitVecSort(64)) != expected
                  for n, expected in rule['registers'].items()]
    deviations.append(parse(transfer['flags'], z.BitVecSort(32)) != rule['flags'])
    for category in ('memory_bytes', 'code_bytes'):
        assert {int(a, 16) for a in transfer[category]} == set(rule[category])
        deviations += [parse(transfer[category][hex(a)], z.BitVecSort(8)) != expected
                       for a, expected in rule[category].items()]
    assert len(transfer['ordered_accesses']) == len(rule['ordered_accesses'])
    for actual, (kind, address, width, value) in zip(transfer['ordered_accesses'], rule['ordered_accesses'], strict=True):
        assert actual['kind'] == kind and actual['width'] == width
        deviations += [parse(actual['address'], z.BitVecSort(64)) != address,
                       parse(actual['value'], z.BitVecSort(width * 8)) != value]
    solver = z.Solver()
    solver.set(timeout=5000)
    solver.add(*rule['assumptions'], z.Not(parse(transfer['guard'], z.BoolSort())))
    assert solver.check() == z.unsat
    solver = z.Solver()
    solver.set(timeout=5000)
    solver.add(*rule['assumptions'], z.Or(*deviations))
    assert solver.check() == z.unsat
    return {'status': 'independent_source_transfer_proved', 'phase': proof['contract']['phase'],
            'general_registers': 16, 'defined_flags_mask': rule['defined_flags_mask'],
            'global_and_return_bytes': len(rule['memory_bytes']), 'code_bytes': len(rule['code_bytes']),
            'ordered_accesses': len(rule['ordered_accesses']),
            'scope': 'All callback inputs admitted by the bounded source record/reason/frame contract; '
                     'does not prove loader invocation or hidden process behavior'}


def verify_loader_module_source_spec(result, symbols):
    """Check the composed module against source, keeping environment assumptions.

    The DLL state is the state after the last authored detach callback. There
    is no claim that memory or registers remain observable after process death.
    """
    assert result['status'] == 'recovered_under_environment_contract'
    recovery = result['whole_module_recovery']
    main = recovery['main']
    runtime = {kind: {name: int(v, 16) if isinstance(v, str) else v for name, v in values.items()}
               for kind, values in symbols.items()}
    es, ds = runtime['exe'], runtime['dll']
    registers = {name: z.BitVec('module_entry_' + name, 64) for name in GPRS}
    flags = z.BitVec('module_entry_flags', 32)
    declarations = {str(v): v for v in [*registers.values(), flags]}
    def parse(text, width):
        target = z.BitVec('module_source_value', width)
        return z.parse_smt2_string('(assert (= module_source_value ' + text + '))',
                    decls=declarations | {'module_source_value': target})[0].arg(1)
    assert set(main['registers_at_exit_api_entry']) == set(GPRS)
    expected = dict(registers)
    expected.update(rax=z.BitVecVal(0x1234, 64), rcx=z.BitVecVal(7, 64),
                    r9=z.BitVecVal(ds['dll_event_log'], 64), rsp=registers['rsp'] - 48)
    differences = [parse(main['registers_at_exit_api_entry'][n], 64) != value for n, value in expected.items()]
    differences.append(parse(main['flags_at_exit_api_entry'], 32) != ((flags & (~ARITHMETIC & 0xffffffff)) | 4))
    solver = z.Solver()
    solver.set(timeout=5000)
    solver.add(registers['rsp'] == int(main['entry_contract']['entry_registers']['rsp'], 16),
               flags & 2 == 2, z.Or(*differences))
    assert solver.check() == z.unsat
    def bytes_at(rows, start, length):
        cells = {}
        for row in rows:
            address, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
            for k, byte in enumerate(raw):
                assert address + k not in cells
                cells[address + k] = byte
        assert set(cells) == set(range(start, start + length))
        return bytes(cells[start + k] for k in range(length))
    def dwords(values):
        return b''.join(v.to_bytes(4, 'little') for v in values)
    assert bytes_at(main['exe_memory'], es['smc_data_start'], 32) == dwords(
        [1, 3, 0x1234, 0, 0, 1, 0xffffffff, 0x1234])
    assert bytes_at(main['dll_report_post_memory'], ds['dll_data_start'], 64) == dwords(
        [3, 3, 1, 0, 2, 2, 0, 0, 0x11, 0x22, 0x33, 0, 0, 0, 0, 0])
    order = recovery['teardown_order']
    assert sorted(order) == ['dll-detach', 'tls-detach']
    tail = [0x44 if phase == 'tls-detach' else 0x55 for phase in order]
    assert bytes_at(recovery['final_dll_memory'], ds['dll_data_start'], 64) == dwords(
        [5, 3, 1, 3, 2, 2, 3, 3, 0x11, 0x22, 0x33, *tail, 0, 0, 0])
    first_code = result['dll_contracts'][0]['contract']['entry_code']
    code_address = int(first_code['address'], 16)
    code = bytearray.fromhex(first_code['hex'])
    offset = ds['dll_report_constant_immediate'] - code_address
    assert code[offset:offset + 4] == bytes.fromhex('01000000')
    code[offset] = 3
    assert recovery['final_dll_code'] == {'address': first_code['address'], 'hex': code.hex()}
    assert main['exit_code'] == recovery['exit_code'] == 7
    return {'status': 'independent_module_source_postconditions_proved',
            'general_registers': 16, 'defined_flags_mask': 0xffffffff,
            'exe_global_bytes': 32, 'dll_report_global_bytes': 64, 'dll_teardown_global_bytes': 64,
            'code_constant_versions': [1, 2, 3], 'teardown_order': order, 'exit_argument_and_receipt': 7,
            'scope': 'Source postconditions under the explicit loader/frame/GS-TEB/ExitProcess contracts; '
                     'DLL final state is after the last authored callback, not postmortem memory'}


def _synthetic_proof(phase):
    """Exercise the independent checker and its failures without native inputs."""
    names = ('dll_event_count', 'dll_stage', 'dll_seen_stage', 'dll_detach_flag', 'dll_report_stage_seen',
             'dll_report_count_seen', 'dll_tls_detach_stage_seen', 'dll_dllmain_detach_stage_seen')
    symbols = {name: 0x3000 + 4 * k for k, name in enumerate(names)}
    symbols.update(dll_data_start=0x3000, dll_event_log=0x3020, dll_report_constant_immediate=0x1001)
    constant = 1 if phase == 'tls-attach' else 2 if phase == 'dll-attach' else 3
    contract = {'phase': phase, 'symbols': symbols, 'entry_rsp': '0x8008', 'return_address': '0x2000',
                'entry_code': {'address': '0x1000', 'hex': 'b8' + constant.to_bytes(4, 'little').hex() + 'c3'}}
    rule = _source_rule(contract)
    sexpr = lambda value: z.simplify(value).sexpr()
    return {'status': 'proved_for_authored_dll_callback', 'contract': contract,
            'symbols': {str(v): v.size() for v in rule['variables']},
            'transfer': {'registers': {n: sexpr(v) for n, v in rule['registers'].items()},
                         'flags': sexpr(rule['flags']), 'defined_flags_mask': rule['defined_flags_mask'],
                         'memory_bytes': {hex(a): sexpr(v) for a, v in rule['memory_bytes'].items()},
                         'code_bytes': {hex(a): sexpr(v) for a, v in rule['code_bytes'].items()},
                         'guard': 'true', 'ordered_accesses': [
                             {'kind': k, 'address': sexpr(a), 'width': w, 'value': sexpr(v)}
                             for k, a, w, v in rule['ordered_accesses']]}}


@pytest.mark.parametrize('phase', list(MARKERS))
def test_source_rule_expresses_all_five_bounded_lifecycle_transfers(phase):
    assert verify_dll_source_spec(_synthetic_proof(phase))['global_and_return_bytes'] == 72


@pytest.mark.parametrize('mutation', ['return-register', 'stack', 'code', 'flags', 'log', 'guard', 'access'])
def test_source_checker_rejects_omitted_or_changed_effects(mutation):
    proof = _synthetic_proof('tls-attach')
    transfer = proof['transfer']
    if mutation == 'return-register':
        transfer['registers']['rax'] = '#x0000000000000000'
    elif mutation == 'stack':
        transfer['registers']['rsp'] = 'dll_entry_rsp'
    elif mutation == 'code':
        transfer['code_bytes']['0x1001'] = '#x01'
    elif mutation == 'flags':
        transfer['defined_flags_mask'] ^= 1
    elif mutation == 'log':
        transfer['memory_bytes']['0x3020'] = 'dll_entry_ram_3020'
    elif mutation == 'guard':
        transfer['guard'] = '(= dll_entry_ram_3000 #x00)'
    else:
        transfer['ordered_accesses'].pop()
    with pytest.raises(AssertionError):
        verify_dll_source_spec(proof)


def _synthetic_module_result(order=('tls-detach', 'dll-detach')):
    initial = {n: z.BitVec('module_entry_' + n, 64) for n in GPRS}
    flags = z.BitVec('module_entry_flags', 32)
    final = dict(initial)
    final.update(rax=z.BitVecVal(0x1234, 64), rcx=z.BitVecVal(7, 64),
                 r9=z.BitVecVal(0x3020, 64), rsp=initial['rsp'] - 48)
    row = lambda start, words: [{'address': hex(start), 'hex': b''.join(v.to_bytes(4, 'little') for v in words).hex()}]
    return {'status': 'recovered_under_environment_contract',
        'dll_contracts': [{'contract': {'entry_code': {'address': '0x1000', 'hex': 'b801000000c3'}}}],
        'whole_module_recovery': {'main': {'registers_at_exit_api_entry': {n: z.simplify(v).sexpr() for n, v in final.items()},
            'flags_at_exit_api_entry': z.simplify((flags & (~ARITHMETIC & 0xffffffff)) | 4).sexpr(),
            'entry_contract': {'entry_registers': {'rsp': '0x8008'}}, 'exit_code': 7,
            'exe_memory': row(0x5000, [1, 3, 0x1234, 0, 0, 1, 0xffffffff, 0x1234]),
            'dll_report_post_memory': row(0x3000, [3, 3, 1, 0, 2, 2, 0, 0, 0x11, 0x22, 0x33, 0, 0, 0, 0, 0])},
            'final_dll_memory': row(0x3000, [5, 3, 1, 3, 2, 2, 3, 3, 0x11, 0x22, 0x33,
                *[0x44 if phase == 'tls-detach' else 0x55 for phase in order], 0, 0, 0]),
            'final_dll_code': {'address': '0x1000', 'hex': 'b803000000c3'},
            'exit_code': 7, 'teardown_order': list(order)}}


MODULE_SYMBOLS = {'exe': {'smc_data_start': 0x5000},
                  'dll': {'dll_data_start': 0x3000, 'dll_event_log': 0x3020, 'dll_report_constant_immediate': 0x1001}}


@pytest.mark.parametrize('order', [('tls-detach', 'dll-detach'), ('dll-detach', 'tls-detach')])
def test_module_source_postconditions_allow_both_observed_detach_orders(order):
    assert verify_loader_module_source_spec(_synthetic_module_result(order), MODULE_SYMBOLS)['general_registers'] == 16


@pytest.mark.parametrize('mutation', ['register', 'stack', 'flags', 'exe-data', 'dll-data', 'code', 'exit'])
def test_module_source_checker_rejects_changed_effects(mutation):
    result = _synthetic_module_result()
    recovery = result['whole_module_recovery']
    main = recovery['main']
    if mutation == 'register':
        main['registers_at_exit_api_entry']['rdx'] = '#x0000000000000000'
    elif mutation == 'stack':
        main['registers_at_exit_api_entry']['rsp'] = '(bvsub module_entry_rsp #x0000000000000028)'
    elif mutation == 'flags':
        main['flags_at_exit_api_entry'] = 'module_entry_flags'
    elif mutation == 'exe-data':
        main['exe_memory'][0]['hex'] = '00' + main['exe_memory'][0]['hex'][2:]
    elif mutation == 'dll-data':
        recovery['final_dll_memory'][0]['hex'] = '00' + recovery['final_dll_memory'][0]['hex'][2:]
    elif mutation == 'code':
        recovery['final_dll_code']['hex'] = 'b802000000c3'
    else:
        recovery['exit_code'] = 9
    with pytest.raises(AssertionError):
        verify_loader_module_source_spec(result, MODULE_SYMBOLS)


def _sealed_callbacks():
    values = [os.environ.get('FDISBULL_DLL_CALLBACK_' + name) for name in ('REPORT', 'FDB', 'OBJECTS')]
    if not all(values):
        pytest.skip('Select sealed native callback report/FDB/object store for the source proof')
    report_path, fdb_path, objects = map(Path, values)
    report = json.loads(report_path.read_text())
    connection = sqlite3.connect('file:' + str(fdb_path) + '?mode=ro&immutable=1', uri=True)
    try:
        for run in report['runs'].values():
            symbols = run['runtime_symbols']['dll']
            for receipt in run['callbacks']:
                retained, expected = connection.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (receipt['artifact'],)).fetchone()
                if isinstance(retained, str):
                    assert retained.startswith('fdisbull-external-object-1:')
                    reference = json.loads(retained.split(':', 1)[1])
                    raw = (objects / reference['sha256']).read_bytes()
                    assert len(raw) == reference['size']
                else:
                    raw = bytes(retained)
                assert hashlib.sha256(raw).hexdigest() == expected == receipt['sha256']
                observation = json.loads(raw)
                entry = observation['entry']
                start, reason = int(entry['rip'], 16), int(entry['general']['rdx'], 16) & 0xffffffff
                phase = ('report' if start == symbols['dll_report'] else
                         ('tls-' if start == symbols['dll_tls_callback'] else 'dll-') + ('attach' if reason == 1 else 'detach'))
                code, *memory = observation['steps'][0]['memory_before']
                contract = {'phase': phase, 'source_sha256': observation['subject_source_sha256'],
                            'module': observation['subject_module'], 'symbols': symbols,
                            'entry_memory': memory, 'entry_code': code | {'sha256': hashlib.sha256(bytes.fromhex(code['hex'])).hexdigest()},
                            'entry_rsp': entry['general']['rsp'], 'return_address': observation['return_address'],
                            'reason': None if phase == 'report' else reason}
                yield observation, contract
    finally:
        connection.close()


def test_actual_sealed_dll_callbacks_match_the_independent_generic_source_spec():
    from fdisbull.pe_dll_contracts import validate_dll_callback
    phases = []
    for observation, contract in _sealed_callbacks():
        proof = validate_dll_callback(observation, contract=contract, timeout_ms=10000)
        assert proof['status'] == 'proved_for_authored_dll_callback', proof
        verify_dll_source_spec(proof)
        phases.append(contract['phase'])
    assert set(phases) == set(MARKERS)
