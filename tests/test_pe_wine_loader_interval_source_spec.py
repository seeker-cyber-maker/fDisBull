"""Independent source rules for two bounded Wine caller fragments.

The success tail restores registers from an explicit saved stack, rather than
claiming they equal the original function-entry registers. The detach prefix
specification admits the captured nonzero-load-count/shutdown branch only.
"""
import hashlib
import json

import pytest

z = pytest.importorskip('z3')
GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
ARITHMETIC = 0x8d5


def _digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _cells(rows):
    result = {}
    for row in rows:
        address, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
        assert raw and address + len(raw) <= 1 << 64
        for k, byte in enumerate(raw):
            assert address + k not in result
            result[address + k] = byte
    return result


def _source_rule(contract, interval):
    role = contract['role']; assert role in ('attach_success_tail', 'detach_selection_prefix')
    addresses = {k: int(v, 16) for k, v in contract['addresses'].items()}
    loader = int(contract['loader_module']['base'], 16)
    wm, teb = addresses['modref'], addresses['teb']
    sp = int(interval['entry']['general']['rsp'], 16)
    raw = _cells(interval['entry_memory'])
    protected = _cells(interval['steps'][0]['protected_before'])
    assert len(protected) == 594
    assert len(interval['steps']) == (21 if role == 'attach_success_tail' else 28)
    assert int.from_bytes(bytes(raw[wm + 0x30 + k] for k in range(8)), 'little') == int(contract['subject_module']['base'], 16)
    initial = {n: z.BitVec('interval_entry_' + n, 64) for n in GPRS}
    flags = z.BitVec('interval_entry_flags', 32)
    generic = set(protected) | set(range(wm + 0x68, wm + 0x6c))
    if role == 'attach_success_tail':
        generic |= set(range(addresses['current_modref'], addresses['current_modref'] + 8))
        generic |= set(range(sp, sp + 0x78))
    else:
        assert contract['walk_nodes'] == [hex(wm + 0x20)]
        generic |= set(range(wm + 0x6c, wm + 0x6e))
        generic |= set(range(addresses['process_detaching'], addresses['process_detaching'] + 4))
    assert generic <= raw.keys()
    ram = {a: z.BitVec(f'interval_entry_ram_{a:x}', 8) if a in generic else z.BitVecVal(b, 8)
           for a, b in raw.items()}
    before = dict(ram)
    word = lambda a, n: z.Concat(*[before[a + k] for k in reversed(range(n))]) if n > 1 else before[a]
    flag_word = word(wm + 0x68, 4)
    registers = dict(initial); accesses = []
    def access(kind, address, width, value):
        accesses.append((kind, z.BitVecVal(address, 64), width, value))
    def store(address, value, width):
        ram.update({address + k: z.Extract(k * 8 + 7, k * 8, value) for k in range(width)})
    assumptions = [initial['rsp'] == sp, flags & 2 == 2]
    if role == 'attach_success_tail':
        assert addresses['current_modref'] == loader + 0x958b8
        assert addresses['debug_channel'] == loader + 0x6d5d0
        assert int.from_bytes(bytes(raw[wm + 0x88 + k] for k in range(8)), 'little') == 0
        assert raw[addresses['debug_channel']] & 8 == 0
        assumptions += [initial['r12'] == wm + 0xa0, z.Extract(31, 0, initial['rax']) == 0]
        intermediate = flag_word | 0x80000
        final_flags = intermediate & 0xffffefff
        access('read', wm + 0x68, 4, flag_word)
        access('write', wm + 0x68, 4, intermediate)
        access('read', wm + 0x88, 8, word(wm + 0x88, 8))
        access('write', addresses['current_modref'], 8, initial['r14'])
        access('read', wm + 0x68, 4, intermediate)
        access('write', wm + 0x68, 4, final_flags)
        access('read', addresses['debug_channel'], 1, word(addresses['debug_channel'], 1))
        store(wm + 0x68, final_flags, 4)
        store(addresses['current_modref'], initial['r14'], 8)
        for index, name in enumerate(('rbx', 'rsi', 'rdi', 'r12', 'r13', 'r14', 'rbp')):
            registers[name] = word(sp + 0x40 + index * 8, 8)
            access('read', sp + 0x40 + index * 8, 8, registers[name])
        access('read', sp + 0x78, 8, word(sp + 0x78, 8))
        registers.update(rax=z.BitVecVal(0, 64), rsp=initial['rsp'] + 0x80)
        a, b = sp, 0x40; value = (a + b) & ((1 << 64) - 1)
        arithmetic = ((1 if a + b >= 1 << 64 else 0)
            | (4 if (value & 255).bit_count() % 2 == 0 else 0)
            | (16 if (a ^ b ^ value) & 16 else 0) | (64 if value == 0 else 0)
            | (128 if value >> 63 else 0) | (2048 if (~(a ^ b) & (a ^ value)) >> 63 & 1 else 0))
        output_flags = (flags & (~ARITHMETIC & 0xffffffff)) | arithmetic
        mask = 0xffffffff
        assert int(interval['exit']['rip'], 16) == int.from_bytes(bytes(raw[sp + 0x78 + k] for k in range(8)), 'little')
        expected_pending = None
        metadata = set(range(wm + 0x68, wm + 0x6c)) | set(range(addresses['current_modref'], addresses['current_modref'] + 8))
    else:
        assert addresses['process_detaching'] == loader + 0x95938
        peb, ldr, head, link = (addresses[k] for k in ('peb', 'ldr', 'init_order_head', 'selected_link'))
        assert head == ldr + 0x30 and link == wm + 0x20 and link != head
        for a, expected in ((teb + 0x30, teb), (teb + 0x60, peb), (peb + 0x18, ldr), (head + 8, link), (link, head)):
            assert int.from_bytes(bytes(raw[a + k] for k in range(8)), 'little') == expected
        state = word(addresses['process_detaching'], 4)
        load_count = word(wm + 0x6c, 2)
        assumptions += [flag_word & 0x80000 != 0, load_count != 0, state != 0]
        for offset, name in ((8, 'rbp'), (0x10, 'rdi'), (0x18, 'rsi'), (0x20, 'rbx')):
            store(sp - offset, initial[name], 8)
            access('write', sp - offset, 8, initial[name])
        for a in (teb + 0x30, teb + 0x60, peb + 0x18, head + 8):
            access('read', a, 8, word(a, 8))
        access('read', addresses['process_detaching'], 4, state)
        access('read', wm + 0x68, 4, flag_word)
        access('read', wm + 0x6c, 2, load_count)
        cleared = flag_word & 0xfff7ffff
        store(wm + 0x68, cleared, 4)
        access('write', wm + 0x68, 4, cleared)
        return_address = loader + 0x31d5b
        store(sp - 0x50, z.BitVecVal(return_address, 64), 8)
        access('write', sp - 0x50, 8, z.BitVecVal(return_address, 64))
        registers.update(rax=z.BitVecVal(link, 64), rbx=z.BitVecVal(wm, 64), rcx=z.BitVecVal(wm, 64),
            rdx=z.BitVecVal(0, 64), rsi=z.BitVecVal(head, 64), rdi=z.BitVecVal(ldr, 64),
            rbp=initial['rsp'] - 0x28, rsp=initial['rsp'] - 0x50, r8=z.ZeroExt(32, state))
        mask = 0xffffffef
        output_flags = ((flags & (~ARITHMETIC & 0xffffffff)) | 0x44) & mask
        target = loader + 0x31600
        assert int(interval['exit']['rip'], 16) == target
        expected_pending = {'target': z.BitVecVal(target, 64), 'return_address': hex(return_address),
            'rsp': initial['rsp'] - 0x50, 'arguments': {'rcx': z.BitVecVal(wm, 64),
            'rdx': z.BitVecVal(0, 64), 'r8': z.ZeroExt(32, state)}}
        metadata = set(range(wm + 0x68, wm + 0x6e)) | set(range(addresses['process_detaching'], addresses['process_detaching'] + 4))
    low, length = int(contract['stack_range']['address'], 16), contract['stack_range']['length']
    stack_cells = set(range(low, low + length))
    assert stack_cells <= raw.keys() and not stack_cells & protected.keys() and not metadata & protected.keys()
    return {'registers': registers, 'flags': output_flags, 'mask': mask, 'before': before, 'ram': ram,
        'protected': set(protected), 'metadata': metadata, 'stack': stack_cells, 'generic': generic,
        'assumptions': assumptions, 'accesses': accesses, 'pending': expected_pending,
        'access_steps': ([3, 3, 4, 5, 8, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20]
                         if role == 'attach_success_tail' else [0, 1, 2, 3, 6, 7, 8, 11, 14, 15, 18, 24, 27])}


def verify_wine_loader_interval_source_spec(proof, *, contract, interval):
    """Check generic source effects and every ordered access without decoding."""
    assert proof['status'] == 'proved_for_observed_wine_loader_interval'
    assert proof['source']['interval_sha256'] == _digest(interval)
    assert proof['source']['contract_sha256'] == _digest(contract)
    rule, transfer = _source_rule(contract, interval), proof['transfer']
    declarations = {n: z.Bool(n) if width == 'Bool' else z.BitVec(n, width) for n, width in proof['symbols'].items()}
    for a in rule['generic']:
        assert proof['symbols'][f'interval_entry_ram_{a:x}'] == 8
    def parse(text, width):
        sort = z.BoolSort() if width == 'Bool' else z.BitVecSort(width)
        if text in declarations:
            assert declarations[text].sort() == sort
            return declarations[text]
        if text.startswith('#x') and width != 'Bool' and (len(text) - 2) * 4 == width:
            return z.BitVecVal(int(text[2:], 16), width)
        if width == 'Bool' and text in ('true', 'false'):
            return z.BoolVal(text == 'true')
        out = z.Const('independent_interval_value', sort)
        rows = z.parse_smt2_string('(assert (= independent_interval_value ' + text + '))',
            decls=declarations | {'independent_interval_value': out})
        assert len(rows) == 1
        return rows[0].arg(1)
    def prove(claim, *, under_entry=True):
        solver = z.Solver(); solver.set(timeout=10000)
        if under_entry: solver.add(*rule['assumptions'])
        solver.add(z.Not(claim))
        assert solver.check() == z.unsat, 'Interval transfer differs from the independent source rule'
    feasible = z.Solver(); feasible.add(*rule['assumptions']); assert feasible.check() == z.sat
    prove(parse(transfer['entry_guard'], 'Bool') == z.And(*rule['assumptions']), under_entry=False)
    prove(parse(transfer['guard'], 'Bool'))
    assert set(transfer['registers']) == set(GPRS) and transfer['defined_flags_mask'] == rule['mask']
    comparisons = [parse(transfer['registers'][n], 64) == value for n, value in rule['registers'].items()]
    comparisons.append(parse(transfer['flags'], 32) == rule['flags'])
    for key, addresses in (('protected_memory', rule['protected']), ('metadata_memory', rule['metadata']), ('stack_memory', rule['stack'])):
        assert {int(a, 16) for a in transfer[key]} == addresses
        comparisons += [parse(transfer[key][hex(a)], 8) == rule['ram'][a] for a in addresses]
    assert len(transfer['ordered_accesses']) == len(rule['accesses'])
    assert [a['step'] for a in transfer['ordered_accesses']] == rule['access_steps']
    for actual, (kind, address, width, value) in zip(transfer['ordered_accesses'], rule['accesses'], strict=True):
        assert actual['kind'] == kind and actual['width'] == width
        comparisons += [parse(actual['address'], 64) == address, parse(actual['value'], width * 8) == value]
    pending = transfer['pending_call']
    if rule['pending'] is None: assert pending is None
    else:
        expected = rule['pending']; assert pending['return_address'] == expected['return_address']
        comparisons += [parse(pending[k], 64) == expected[k] for k in ('target', 'rsp')]
        assert set(pending['arguments']) == set(expected['arguments'])
        comparisons += [parse(pending['arguments'][k], 64) == value for k, value in expected['arguments'].items()]
    assert not any('opaque_fp' in name for name in proof['symbols'])
    prove(z.And(*comparisons))
    return {'status': 'independent_wine_loader_interval_source_transfer_proved', 'role': contract['role'],
        'instructions': len(interval['steps']), 'protected_bytes': len(rule['protected']),
        'ordered_accesses': len(rule['accesses']), 'gprs': len(GPRS), 'defined_flags_mask': hex(rule['mask']),
        'proof_sha256': proof.get('sha256'), 'contract_sha256': _digest(contract),
        'claim_limit': 'Only the source-bound caller fragment; saved-stack values and loader metadata remain explicit entry inputs, and four outer intervals remain conditional'}


def _claim(role):
    loader, subject, wm, teb, peb, ldr = 0x6000000000, 0x180000000, 0x1425f0, 0x700000, 0x710000, 0x720000
    sp = 0x120000 if role == 'attach_success_tail' else 0x120008
    addresses = {'teb': hex(teb), 'modref': hex(wm), 'current_modref': hex(loader + 0x958b8),
        'process_detaching': hex(loader + 0x95938), 'debug_channel': hex(loader + 0x6d5d0)}
    memory = {}; protected = {'address': '0x140002000', 'hex': bytes(594).hex()}
    def put(a, value, width): memory.update({a + k: b for k, b in enumerate(value.to_bytes(width, 'little'))})
    memory.update(_cells([protected])); put(wm + 0x30, subject, 8)
    put(wm + 0x68, 0x1004 if role == 'attach_success_tail' else 0x80004, 4)
    put(wm + 0x6c, 0xffff, 2)
    if role == 'attach_success_tail':
        low, length = sp, 0x80; put(wm + 0x88, 0, 8)
        put(loader + 0x958b8, 0x1234, 8); put(loader + 0x6d5d0, 0, 1)
        exit_pc = loader + 0x40000; put(sp + 0x78, exit_pc, 8)
        nodes = []
    else:
        low, length = sp - 0x50, 0x58
        addresses.update(peb=hex(peb), ldr=hex(ldr), init_order_head=hex(ldr + 0x30), selected_link=hex(wm + 0x20))
        for a, value in ((teb + 0x30, teb), (teb + 0x60, peb), (peb + 0x18, ldr), (ldr + 0x38, wm + 0x20), (wm + 0x20, ldr + 0x30)):
            put(a, value, 8)
        put(loader + 0x95938, 1, 4); exit_pc = loader + 0x31600; nodes = [hex(wm + 0x20)]
    for a in range(low, low + length): memory.setdefault(a, 0)
    interval = {'entry': {'general': {'rsp': hex(sp)}}, 'exit': {'rip': hex(exit_pc)},
        'entry_memory': [{'address': hex(a), 'hex': f'{b:02x}'} for a, b in sorted(memory.items())],
        'steps': [{'protected_before': [protected]} for _ in range(21 if role == 'attach_success_tail' else 28)]}
    contract = {'role': role, 'addresses': addresses, 'loader_module': {'base': hex(loader)},
        'subject_module': {'base': hex(subject)}, 'walk_nodes': nodes, 'stack_range': {'address': hex(low), 'length': length}}
    rule = _source_rule(contract, interval)
    transfer = {'registers': {n: value.sexpr() for n, value in rule['registers'].items()},
        'flags': rule['flags'].sexpr(), 'defined_flags_mask': rule['mask'],
        'guard': 'true', 'entry_guard': z.And(*rule['assumptions']).sexpr(),
        'pending_call': None, 'ordered_accesses': []}
    for key, selected in (('protected_memory', rule['protected']), ('metadata_memory', rule['metadata']), ('stack_memory', rule['stack'])):
        transfer[key] = {hex(a): rule['ram'][a].sexpr() for a in selected}
    for step, (kind, address, width, value) in zip(rule['access_steps'], rule['accesses'], strict=True):
        transfer['ordered_accesses'].append({'step': step, 'kind': kind, 'address': address.sexpr(), 'width': width, 'value': value.sexpr()})
    if rule['pending'] is not None:
        expected = rule['pending']
        transfer['pending_call'] = {'target': expected['target'].sexpr(), 'rsp': expected['rsp'].sexpr(),
            'return_address': expected['return_address'], 'arguments': {n: v.sexpr() for n, v in expected['arguments'].items()}}
    proof = {'status': 'proved_for_observed_wine_loader_interval', 'transfer': transfer,
        'symbols': {**{'interval_entry_' + n: 64 for n in GPRS}, 'interval_entry_flags': 32,
                    **{f'interval_entry_ram_{a:x}': 8 for a in rule['generic']}},
        'source': {'interval_sha256': _digest(interval), 'contract_sha256': _digest(contract)}}
    return proof, contract, interval


@pytest.mark.parametrize('role', ['attach_success_tail', 'detach_selection_prefix'])
def test_independent_caller_fragment_source_expectations(role):
    proof, contract, interval = _claim(role)
    assert verify_wine_loader_interval_source_spec(proof, contract=contract, interval=interval)['gprs'] == 16


@pytest.mark.parametrize('mutation', ['saved-register', 'current-modref', 'flags', 'protected', 'guard'])
def test_tail_source_rule_rejects_sample_equal_or_incorrect_effects(mutation):
    proof, contract, interval = _claim('attach_success_tail'); transfer = proof['transfer']
    if mutation == 'saved-register': transfer['registers']['rbx'] = 'interval_entry_rbx'
    elif mutation == 'current-modref':
        address = int(contract['addresses']['current_modref'], 16)
        transfer['metadata_memory'][hex(address)] = f'interval_entry_ram_{address:x}'
    elif mutation == 'flags': transfer['flags'] = 'interval_entry_flags'
    elif mutation == 'protected': transfer['protected_memory']['0x140002000'] = '#x00'
    else: transfer['entry_guard'] = '(and ' + transfer['entry_guard'] + ' (= interval_entry_r14 #x0000000000000000))'
    with pytest.raises(AssertionError):
        verify_wine_loader_interval_source_spec(proof, contract=contract, interval=interval)


@pytest.mark.parametrize('mutation', ['reserved', 'attached-flag', 'return-word', 'flags-mask', 'access-order', 'guard-union', 'opaque-store'])
def test_detach_source_rule_rejects_incorrect_selection_frame_or_effects(mutation):
    proof, contract, interval = _claim('detach_selection_prefix'); transfer = proof['transfer']
    if mutation == 'reserved': transfer['registers']['r8'] = 'interval_entry_r8'
    elif mutation == 'attached-flag':
        address = int(contract['addresses']['modref'], 16) + 0x68 + 2
        transfer['metadata_memory'][hex(address)] = f'interval_entry_ram_{address:x}'
    elif mutation == 'return-word': transfer['pending_call']['return_address'] = '0x1234'
    elif mutation == 'flags-mask': transfer['defined_flags_mask'] = 0xffffffff
    elif mutation == 'access-order': transfer['ordered_accesses'][0], transfer['ordered_accesses'][1] = transfer['ordered_accesses'][1], transfer['ordered_accesses'][0]
    elif mutation == 'guard-union':
        assumptions = _source_rule(contract, interval)['assumptions']
        transfer['entry_guard'] = z.And(*assumptions[:3], z.Or(z.Not(assumptions[3]), assumptions[4])).sexpr()
    else: proof['symbols']['interval_opaque_fp_store_0'] = 128
    with pytest.raises(AssertionError):
        verify_wine_loader_interval_source_spec(proof, contract=contract, interval=interval)
