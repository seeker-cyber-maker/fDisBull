"""Independent source rules for complete normal Wine DLL-dispatch capsules.

This specification composes the authored source's two callbacks directly. It
does not decode loader instructions, use their transfer helpers, or infer a
universal frame from snapshots. Optional sealed-corpus checks consume proofs
that the production verifier has recomputed from original ntdll bytes.
"""
import hashlib
import json

import pytest

z = pytest.importorskip('z3')

GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
ARITHMETIC = 0x8d5


def _cells(rows):
    result = {}
    for row in rows:
        start, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
        assert raw and start + len(raw) <= 1 << 64
        for k, byte in enumerate(raw):
            assert start + k not in result
            result[start + k] = byte
    return result


def _digest(document):
    raw = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _source_rule(contract, capsule):
    phase = contract['phase']
    assert phase in ('attach', 'detach')
    reason = 1 if phase == 'attach' else 0
    symbols = {n: int(v, 16) if isinstance(v, str) else v
               for n, v in contract['subject_symbols'].items()}
    data, log = symbols['dll_data_start'], symbols['dll_event_log']
    stack = int(capsule['entry']['general']['rsp'], 16)
    wm, teb = int(capsule['selection']['modref'], 16), int(capsule['thread_info']['teb'], 16)
    base = int(contract['subject_module']['base'], 16)
    initial = {n: z.BitVec('loader_entry_' + n, 64) for n in GPRS}
    flags = z.BitVec('loader_entry_flags', 32)
    ram = {a: z.BitVec(f'loader_entry_ram_{a:x}', 8)
           for a in [*range(data, data + 64), *range(teb, teb + 8)]}
    word = lambda a: z.Concat(*[ram[a + k] for k in (3, 2, 1, 0)])
    count, stage, detach = word(data), word(data + 4), word(data + 12)
    output = {a: ram[a] for a in range(data, data + 64)}
    def store(address, value):
        output.update({address + k: z.Extract(8 * k + 7, 8 * k, value) for k in range(4)})
    markers = (0x11, 0x22) if phase == 'attach' else (0x44, 0x55)
    # Select whole DWORD slots; the native model instead performs byte-address
    # stores. The two source writes cannot overlap for count 0..6.
    for slot in range(8):
        value = z.If(count == slot, z.BitVecVal(markers[0], 32),
                     z.If(count + 1 == slot, z.BitVecVal(markers[1], 32), word(log + slot * 4)))
        store(log + slot * 4, value)
    store(data, count + 2)
    if phase == 'attach':
        store(data + 4, z.BitVecVal(2, 32))
        store(data + 8, z.BitVecVal(1, 32))
    else:
        store(data + 12, detach | 3)
        store(data + 24, stage)
        store(data + 28, stage)
    protected = _cells(capsule['steps'][0]['protected_before'])
    code = _cells([contract['entry_code']])
    assert set(output) <= protected.keys() and set(code) <= protected.keys()
    if phase == 'attach':
        code[symbols['dll_report_constant_immediate']] = 3
    memory = {a: z.BitVecVal(b, 8) for a, b in protected.items()} | output
    memory.update({a: z.BitVecVal(b, 8) for a, b in code.items()})
    registers = dict(initial)
    registers.update(rax=z.BitVecVal(0, 64), rcx=z.BitVecVal(base, 64),
        rdx=z.BitVecVal(reason, 64), r8=initial['r8'],
        r9=z.BitVecVal(log, 64), r10=z.BitVecVal(symbols['dll_entry'], 64),
        rsp=initial['rsp'] + 8)
    # The final flag-producing operation is the source epilogue's ADD RSP,228h
    # after four PUSHes and SUB RSP,228h. POP/RET preserve its flags.
    a, b = (stack - 0x248) & ((1 << 64) - 1), 0x228
    value = (a + b) & ((1 << 64) - 1)
    arithmetic = ((1 if a + b >= 1 << 64 else 0)
        | (4 if (value & 255).bit_count() % 2 == 0 else 0)
        | (16 if (a ^ b ^ value) & 16 else 0)
        | (64 if value == 0 else 0)
        | (128 if value >> 63 else 0)
        | (2048 if (~(a ^ b) & (a ^ value)) >> 63 & 1 else 0))
    final_flags = (flags & (~ARITHMETIC & 0xffffffff)) | arithmetic
    assumptions = [initial['rsp'] == stack, initial['rcx'] == wm,
        z.Extract(31, 0, initial['rdx']) == reason, flags & 2 == 2, z.ULE(count, 6)]
    return {'registers': registers, 'flags': final_flags, 'memory': memory,
        'globals': output, 'code': code, 'teb': {a: ram[a] for a in range(teb, teb + 8)},
        'assumptions': assumptions, 'initial': initial, 'reason': reason,
        'symbols': symbols, 'stack': stack, 'base': base}


def verify_wine_loader_source_spec(proof, *, contract, capsule):
    """Prove exported generic capsule effects equal independent source intent."""
    assert proof['status'] == 'proved_for_observed_wine_loader_capsule'
    assert proof['source']['capsule_sha256'] == _digest(capsule)
    assert proof['source']['contract_sha256'] == _digest(contract)
    rule, transfer = _source_rule(contract, capsule), proof['transfer']
    declarations = {n: z.Bool(n) if bits == 'Bool' else z.BitVec(n, bits)
                    for n, bits in proof['symbols'].items()}
    def parse(expression, width):
        sort = z.BoolSort() if width == 'Bool' else z.BitVecSort(width)
        out = z.Const('independent_loader_value', sort)
        return z.parse_smt2_string('(assert (= independent_loader_value ' + expression + '))',
            decls=declarations | {'independent_loader_value': out})[0].arg(1)
    def universal(claim):
        solver = z.Solver(); solver.set(timeout=10000)
        solver.add(*rule['assumptions'], z.Not(claim))
        assert solver.check() == z.unsat, 'Loader transfer contradicts the independent source specification'
    feasible = z.Solver(); feasible.add(*rule['assumptions'])
    assert feasible.check() == z.sat
    assert set(transfer['registers']) == set(GPRS)
    assert transfer['defined_flags_mask'] == 0xffffffff
    effects = [parse(transfer['registers'][n], 64) == value for n, value in rule['registers'].items()]
    effects.append(parse(transfer['flags'], 32) == rule['flags'])
    for name, expected in (('globals', rule['globals']), ('protected_memory', rule['memory']),
                           ('teb_exception_chain', rule['teb'])):
        assert {int(a, 16) for a in transfer[name]} == set(expected)
        effects.extend(parse(transfer[name][hex(a)], 8) == value for a, value in expected.items())
    assert _cells([transfer['post_code']]) == rule['code']
    universal(z.And(*effects))
    universal(parse(transfer['guard'], 'Bool'))
    callback_targets = [rule['symbols']['dll_tls_callback'], rule['symbols']['dll_entry']]
    calls = [c for c in proof['calls'] if int(c['target'], 16) in callback_targets]
    assert [int(c['target'], 16) for c in calls] == callback_targets
    assert [s['role'] for s in capsule['callback_spans']] == ['tls-' + contract['phase'], 'dll-' + contract['phase']]
    for index, (call, span) in enumerate(zip(calls, capsule['callback_spans'], strict=True)):
        assert call['step'] + 1 == span['first_step']
        expected = {'rcx': z.BitVecVal(rule['base'], 64),
            'rdx': z.BitVecVal(rule['reason'], 64),
            'r8': z.BitVecVal(0, 64) if index == 0 else rule['initial']['r8'],
            'rsp': rule['initial']['rsp'] - (0x440 if index == 0 else 0x290)}
        universal(parse(call['target_expression'], 64) == callback_targets[index])
        universal(z.And(*[parse(call['entry_arguments'][n], 64) == value for n, value in expected.items()]))
    # The inner BOOL return is distinct from outer MODULE_InitDLL's NTSTATUS0.
    inner = proof['callback_contracts'][1]
    inner_declarations = {n: z.Bool(n) if bits == 'Bool' else z.BitVec(n, bits)
                          for n, bits in inner['symbols'].items()}
    return_value = z.BitVec('independent_dllmain_result', 64)
    actual = z.parse_smt2_string('(assert (= independent_dllmain_result ' + inner['transfer']['registers']['rax'] + '))',
        decls=inner_declarations | {'independent_dllmain_result': return_value})[0].arg(1)
    assert z.simplify(actual).as_long() == 1
    protected = sorted(rule['memory'])
    low = int(contract['stack_range']['address'], 16); high = low + contract['stack_range']['length']
    teb = int(capsule['thread_info']['teb'], 16)
    assert not set(protected) & set(range(low, high))
    assert not set(protected) & set(range(teb, teb + 8))
    spans = capsule['callback_spans']
    writes = []
    access_count = sum(len(s['accesses']) for s in capsule['steps'])
    assert len(transfer['ordered_accesses']) == access_count
    for access in transfer['ordered_accesses']:
        assert 0 <= access['step'] < len(capsule['steps'])
        if access['kind'] != 'write':
            assert access['kind'] == 'read'
            continue
        if any(s['first_step'] <= access['step'] <= s['last_step'] for s in spans):
            continue
        pointer, width = parse(access['address'], 64), access['width']
        assert type(width) is int and 1 <= width <= 16
        allowed = z.Or(z.And(z.UGE(pointer, low), z.ULE(pointer, high - width)),
                       z.And(pointer == teb, width == 8))
        noalias = z.And(*[z.Or(z.ULT(a, pointer), z.UGE(a, pointer + width)) for a in protected])
        writes.extend([allowed, z.ULE(pointer, (1 << 64) - width), noalias])
    universal(z.And(*writes))
    return {'status': 'independent_wine_loader_source_transfer_proved', 'phase': contract['phase'],
        'generic_event_count': [0, 6], 'source_callbacks': ['tls-' + contract['phase'], 'dll-' + contract['phase']],
        'final_status': 0, 'inner_dllmain_bool': 1, 'gprs': len(GPRS), 'flags_mask': '0xffffffff',
        'protected_bytes': len(protected), 'teb_exception_chain_bytes': 8,
        'opaque_loader_writes_checked': len(writes) // 3,
        'proof_sha256': proof.get('sha256'), 'contract_sha256': _digest(contract),
        'claim_limit': 'Closed captured normal MODULE_InitDLL capsule; entry selection, uncovered intervals and exceptional paths remain outside this source specification'}


def _claim(phase):
    data, code, teb, stack = 0x180002000, 0x180004000, 0x700000, 0x120008
    names = ['dll_event_count', 'dll_stage', 'dll_seen_stage', 'dll_detach_flag',
        'dll_report_stage_seen', 'dll_report_count_seen', 'dll_tls_detach_stage_seen', 'dll_dllmain_detach_stage_seen']
    symbols = {n: hex(data + 4 * k) for k, n in enumerate(names)} | {
        'dll_data_start': hex(data), 'dll_data_end': hex(data + 64), 'dll_event_log': hex(data + 32),
        'dll_tls_callback': hex(code), 'dll_entry': hex(code + 32), 'dll_report_constant_immediate': hex(code + 48)}
    rows = [{'address': hex(data), 'hex': bytes(64).hex()}, {'address': hex(code), 'hex': bytes(64).hex()},
            {'address': '0x140002000', 'hex': '01020304'}]
    capsule = {'entry': {'general': {'rsp': hex(stack)}}, 'selection': {'modref': '0x142000'},
        'thread_info': {'teb': hex(teb)}, 'steps': [{'protected_before': rows, 'accesses': []} for _ in range(4)],
        'callback_spans': [{'role': 'tls-' + phase, 'first_step': 1, 'last_step': 1},
                           {'role': 'dll-' + phase, 'first_step': 3, 'last_step': 3}]}
    contract = {'phase': phase, 'subject_symbols': symbols, 'subject_module': {'base': '0x180000000'},
        'entry_code': rows[1], 'stack_range': {'address': hex(stack - 2048), 'length': 4096}}
    rule = _source_rule(contract, capsule)
    initial_ram = {a: z.BitVec(f'loader_entry_ram_{a:x}', 8) for a in [*range(data, data + 64), *range(teb, teb + 8)]}
    proof = {'status': 'proved_for_observed_wine_loader_capsule',
        'symbols': {**{'loader_entry_' + n: 64 for n in GPRS}, 'loader_entry_flags': 32,
                    **{str(v): 8 for v in initial_ram.values()}},
        'callback_contracts': [{}, {'symbols': {}, 'transfer': {'registers': {'rax': '#x0000000000000001'}}}],
        'transfer': {'registers': {n: v.sexpr() for n, v in rule['registers'].items()},
            'flags': rule['flags'].sexpr(), 'defined_flags_mask': 0xffffffff,
            'globals': {hex(a): v.sexpr() for a, v in rule['globals'].items()},
            'protected_memory': {hex(a): v.sexpr() for a, v in rule['memory'].items()},
            'teb_exception_chain': {hex(a): v.sexpr() for a, v in rule['teb'].items()},
            'post_code': {'address': hex(code), 'hex': bytes(rule['code'][a] for a in sorted(rule['code'])).hex()},
            'guard': 'true', 'ordered_accesses': []}, 'calls': []}
    for index, target in enumerate((code, code + 32)):
        args = {'rcx': z.BitVecVal(rule['base'], 64), 'rdx': z.BitVecVal(rule['reason'], 64),
            'r8': z.BitVecVal(0, 64) if index == 0 else rule['initial']['r8'],
            'rsp': rule['initial']['rsp'] - (0x440 if index == 0 else 0x290)}
        proof['calls'].append({'step': index * 2, 'target': hex(target), 'target_expression': z.BitVecVal(target, 64).sexpr(),
            'entry_arguments': {n: v.sexpr() for n, v in args.items()}})
    proof['source'] = {'capsule_sha256': _digest(capsule), 'contract_sha256': _digest(contract)}
    return proof, contract, capsule


@pytest.mark.parametrize('phase', ['attach', 'detach'])
def test_high_level_capsule_source_spec_admits_both_source_phase_rules(phase):
    proof, contract, capsule = _claim(phase)
    assert verify_wine_loader_source_spec(proof, contract=contract, capsule=capsule)['final_status'] == 0


@pytest.mark.parametrize('corrupt', ['count', 'log', 'nonvolatile', 'status', 'flags', 'protected', 'teb', 'dispatch', 'reserved'])
def test_independent_source_spec_rejects_wrong_generic_capsule_effects(corrupt):
    proof, contract, capsule = _claim('attach')
    transfer = proof['transfer']; data = int(contract['subject_symbols']['dll_data_start'], 16)
    if corrupt in ('count', 'log'):
        transfer['globals'][hex(data + (0 if corrupt == 'count' else 32))] = '#x00'
    elif corrupt in ('nonvolatile', 'status'):
        transfer['registers']['rbx' if corrupt == 'nonvolatile' else 'rax'] = '#x0000000000000001'
    elif corrupt == 'flags': transfer['flags'] = '#x00000002'
    elif corrupt == 'protected': transfer['protected_memory']['0x140002000'] = '#x00'
    elif corrupt == 'teb': transfer['teb_exception_chain']['0x700000'] = '#x00'
    elif corrupt == 'dispatch': proof['calls'].reverse()
    else: proof['calls'][1]['entry_arguments']['r8'] = '#x0000000000000000'
    with pytest.raises(AssertionError):
        verify_wine_loader_source_spec(proof, contract=contract, capsule=capsule)


def test_an_opaque_loader_store_cannot_hide_a_protected_write_and_restore():
    proof, contract, capsule = _claim('detach')
    proof['transfer']['ordered_accesses'] = [
        {'step': 0, 'kind': 'write', 'address': '#x0000000140002000', 'width': 1, 'value': '#x00'},
        {'step': 0, 'kind': 'write', 'address': '#x0000000140002000', 'width': 1, 'value': '#x01'}]
    capsule['steps'][0]['accesses'] = [{}, {}]
    proof['source']['capsule_sha256'] = _digest(capsule)
    with pytest.raises(AssertionError):
        verify_wine_loader_source_spec(proof, contract=contract, capsule=capsule)
