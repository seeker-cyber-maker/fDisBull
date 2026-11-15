"""Independent intent specification for a complete selected-node Wine attach.

The specification appends one initialization-list member and composes the two
authored source callbacks directly. It does not decode instructions or call the
production transfer implementation. Initial list construction and other DLLs
remain outside this bounded contract.
"""
import hashlib
import json

import pytest

z = pytest.importorskip('z3')
GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
ARITHMETIC = 0x8d5


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _cells(rows):
    result = {}
    for row in rows:
        address, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
        assert raw and address + len(raw) <= 1 << 64
        for k, byte in enumerate(raw):
            assert address + k not in result
            result[address + k] = byte
    return result


def _source_rule(contract, observation):
    addresses = {n: int(v, 16) for n, v in contract['addresses'].items()}
    symbols = {n: int(v, 16) if isinstance(v, str) else v for n, v in contract['subject_symbols'].items()}
    wm, node, teb = (addresses[n] for n in ('modref', 'node', 'teb'))
    head, tail, current, notify = (addresses[n] for n in ('init_order_head', 'old_tail', 'current_modref', 'notification_head'))
    new = wm + 0x20; data = symbols['dll_data_start']; log = symbols['dll_event_log']
    sp = int(observation['entry']['general']['rsp'], 16)
    raw = _cells(observation['entry_memory']); protected = _cells(observation['steps'][0]['protected_before'])
    code_row = contract['entry_code'] if 'entry_code' in contract else contract['module_contract']['entry_code']
    code = _cells([code_row])
    assert len(protected) == 594 and len(code) == 317
    assert set(code) <= protected.keys() and set(range(data, data + 64)) <= protected.keys()
    def concrete(a, width):
        return int.from_bytes(bytes(raw[a + k] for k in range(width)), 'little')
    assert concrete(node, 8) == wm + 0xa0 and concrete(node + 0x28, 8) == 0
    assert concrete(wm + 0x98, 8) == node and concrete(wm + 0x88, 8) == 0
    assert concrete(new, 8) == concrete(new + 8, 8) == 0
    assert concrete(wm + 0x30, 8) == int(contract['subject_module']['base'], 16)
    assert concrete(head + 8, 8) == tail and concrete(tail, 8) == head
    old_nodes = [int(value, 16) for value in contract['init_order_nodes']]
    assert len(set(old_nodes)) == len(old_nodes) and new not in old_nodes and head not in old_nodes
    assert tail == (old_nodes[-1] if old_nodes else head)
    for index, member in enumerate([head, *old_nodes]):
        forward = old_nodes[0] if index == 0 and old_nodes else old_nodes[index] if index < len(old_nodes) else head
        backward = tail if index == 0 else old_nodes[index - 2] if index > 1 else head
        assert concrete(member, 8) == forward and concrete(member + 8, 8) == backward
    assert concrete(notify, 8) == concrete(notify + 8, 8) == notify
    assert concrete(teb + 0x30, 8) == teb
    assert raw[addresses['debug_channel']] & 8 == 0
    assert concrete(symbols['dll_report_constant_immediate'], 4) == 1
    def span(a, width):
        assert 0 <= a < a + width <= 1 << 64
        return set(range(a, a + width))
    head_span, tail_span, new_span = span(head, 16), span(tail, 16), span(new, 16)
    assert not new_span & (head_span | tail_span)
    assert tail == head or not head_span & tail_span
    low, length = int(contract['stack_range']['address'], 16), contract['stack_range']['length']
    stack = span(low, length)
    mutable_groups = [new_span, span(wm + 0x68, 6), span(current, 8), span(tail, 8), span(head + 8, 8)]
    immutable_fields = (span(node, 16) | span(node + 0x28, 8) | span(wm + 0x30, 16)
        | span(wm + 0x88, 8) | span(wm + 0x98, 8) | span(notify, 16)
        | span(teb, 8) | span(teb + 0x30, 8) | span(teb + 0x60, 8)
        | span(addresses['peb'] + 0x18, 8) | span(addresses['debug_channel'], 1))
    for index, group in enumerate(mutable_groups):
        assert not group & (protected.keys() | stack | immutable_fields)
        assert not any(group & earlier for earlier in mutable_groups[:index])
    old_list_groups = [span(a, 16) for a in [head, *old_nodes]]
    for index, group in enumerate(old_list_groups):
        assert not group & (span(wm + 0x68, 6) | span(current, 8) | new_span | immutable_fields | protected.keys() | stack)
        assert not any(group & earlier for earlier in old_list_groups[:index])
    initial = {n: z.BitVec('process_attach_entry_' + n, 64) for n in GPRS}
    flags = z.BitVec('process_attach_entry_flags', 32)
    generic = (set(protected) - set(code)) | span(wm + 0x68, 6) | span(current, 8) | span(teb, 8)
    assert generic <= raw.keys()
    before = {a: z.BitVec(f'process_attach_entry_ram_{a:x}', 8) if a in generic else z.BitVecVal(b, 8)
              for a, b in raw.items()}
    ram = dict(before)
    word = lambda a, width: z.Concat(*[before[a + k] for k in reversed(range(width))]) if width > 1 else before[a]
    count, old_flags = word(data, 4), word(wm + 0x68, 4)
    assumptions = [initial['rsp'] == sp, initial['rcx'] == node, initial['rdx'] != 0,
        flags & 2 == 2, z.ULE(count, 6), old_flags & 0x81000 == 0, old_flags & 0xff000000 == 0]
    def store(address, width, value):
        ram.update({address + k: z.Extract(k * 8 + 7, k * 8, value) for k in range(width)})
    for slot in range(8):
        value = z.If(count == slot, z.BitVecVal(0x11, 32),
                     z.If(count + 1 == slot, z.BitVecVal(0x22, 32), word(log + slot * 4, 4)))
        store(log + slot * 4, 4, value)
    store(data, 4, count + 2); store(data + 4, 4, z.BitVecVal(2, 32)); store(data + 8, 4, z.BitVecVal(1, 32))
    ram[symbols['dll_report_constant_immediate']] = z.BitVecVal(3, 8)
    in_progress = old_flags | 0x1000
    attached = in_progress | 0x80000
    final_flags = attached & 0xffffefff
    store(wm + 0x68, 4, final_flags); store(wm + 0x6c, 2, z.BitVecVal(0xffff, 16))
    pair = z.Concat(z.BitVecVal(tail, 64), z.BitVecVal(head, 64))
    store(new, 16, pair); store(tail, 8, z.BitVecVal(new, 64)); store(head + 8, 8, z.BitVecVal(new, 64))
    registers = dict(initial)
    registers.update(rax=z.BitVecVal(0, 64), rcx=z.BitVecVal(int(contract['subject_module']['base'], 16), 64),
        rdx=z.BitVecVal(1, 64), r8=initial['rdx'], r9=z.BitVecVal(log, 64),
        r10=z.BitVecVal(symbols['dll_entry'], 64), rsp=initial['rsp'] + 8)
    a, b = (sp - 0x78) & ((1 << 64) - 1), 0x40; result = (a + b) & ((1 << 64) - 1)
    arithmetic = ((1 if a + b >= 1 << 64 else 0) | (4 if (result & 255).bit_count() % 2 == 0 else 0)
        | (16 if (a ^ b ^ result) & 16 else 0) | (64 if result == 0 else 0)
        | (128 if result >> 63 else 0) | (2048 if (~(a ^ b) & (a ^ result)) >> 63 & 1 else 0))
    output_flags = (flags & (~ARITHMETIC & 0xffffffff)) | arithmetic
    metadata_writes = [('write', wm + 0x68, 4, in_progress), ('write', wm + 0x6c, 2, z.BitVecVal(0xffff, 16)),
        ('write', new, 16, pair), ('write', tail, 8, z.BitVecVal(new, 64)),
        ('write', head + 8, 8, z.BitVecVal(new, 64)), ('write', current, 8, z.BitVecVal(wm, 64)),
        ('write', wm + 0x68, 4, attached), ('write', current, 8, word(current, 8)),
        ('write', wm + 0x68, 4, final_flags)]
    saved = {}
    for offset, name in ((8, 'rbp'), (0x10, 'r14'), (0x18, 'r13'), (0x20, 'r12'),
                         (0x28, 'rdi'), (0x30, 'rsi'), (0x38, 'rbx')):
        saved.update({sp - offset + k: z.Extract(k * 8 + 7, k * 8, initial[name]) for k in range(8)})
    appended = [*old_nodes, new]; list_bytes = {}
    for index, member in enumerate([head, *appended]):
        forward = appended[0] if index == 0 else appended[index] if index < len(appended) else head
        backward = new if index == 0 else appended[index - 2] if index > 1 else head
        for address, value in ((member, forward), (member + 8, backward)):
            list_bytes.update({address + k: z.BitVecVal((value >> (8 * k)) & 255, 8) for k in range(8)})
    return {'before': before, 'ram': ram, 'registers': registers, 'flags': output_flags, 'generic': generic,
        'protected': set(protected), 'code': set(code), 'stack': stack, 'saved_stack': saved,
        'metadata_required': set().union(*mutable_groups), 'metadata_writes': metadata_writes,
        'vectors': {'xmm0': pair, 'xmm1': z.ZeroExt(64, z.BitVecVal(tail, 64))},
        'teb': span(teb, 8), 'current': span(current, 8), 'assumptions': assumptions, 'list_bytes': list_bytes,
        'list_relation': {'head': head, 'old_tail': tail, 'new_node': new, 'empty_input': tail == head}}


def verify_process_attach_source_spec(proof, *, contract, observation):
    """Validate complete generic source intent, list append and integer SIMD."""
    assert proof['status'] == 'proved_for_observed_wine_process_attach'
    assert proof['source']['process_attach_sha256'] == _digest(observation)
    assert proof['source']['contract_sha256'] == _digest(contract)
    rule, transfer = _source_rule(contract, observation), proof['transfer']
    declarations = {name: z.Bool(name) if width == 'Bool' else z.BitVec(name, width)
                    for name, width in proof['symbols'].items()}
    for a in rule['generic']: assert proof['symbols'][f'process_attach_entry_ram_{a:x}'] == 8
    for name in ('xmm0', 'xmm1'): assert proof['symbols']['process_attach_entry_' + name] == 128
    def parse(text, width):
        sort = z.BoolSort() if width == 'Bool' else z.BitVecSort(width)
        if text in declarations:
            assert declarations[text].sort() == sort; return declarations[text]
        if width != 'Bool' and text.startswith('#x') and (len(text) - 2) * 4 == width:
            return z.BitVecVal(int(text[2:], 16), width)
        if width == 'Bool' and text in ('true', 'false'): return z.BoolVal(text == 'true')
        value = z.Const('independent_process_attach_value', sort)
        rows = z.parse_smt2_string('(assert (= independent_process_attach_value ' + text + '))',
            decls=declarations | {'independent_process_attach_value': value})
        assert len(rows) == 1
        return rows[0].arg(1)
    def prove(claim, *, entry=True):
        solver = z.Solver(); solver.set(timeout=10000)
        if entry: solver.add(*rule['assumptions'])
        solver.add(z.Not(claim)); assert solver.check() == z.unsat, 'Complete attach differs from independent source intent'
    feasible = z.Solver(); feasible.add(*rule['assumptions']); assert feasible.check() == z.sat
    prove(parse(transfer['entry_guard'], 'Bool') == z.And(*rule['assumptions']), entry=False)
    prove(parse(transfer['guard'], 'Bool'))
    assert set(transfer['registers']) == set(GPRS) and transfer['defined_flags_mask'] == 0xffffffff
    claims = [parse(transfer['registers'][n], 64) == value for n, value in rule['registers'].items()]
    claims.append(parse(transfer['flags'], 32) == rule['flags'])
    assert set(transfer['vectors']) == {'xmm0', 'xmm1'}
    claims += [parse(transfer['vectors'][n], 128) == value for n, value in rule['vectors'].items()]
    assert {int(a, 16) for a in transfer['protected_memory']} == rule['protected']
    claims += [parse(transfer['protected_memory'][hex(a)], 8) == rule['ram'][a] for a in rule['protected']]
    metadata = {int(a, 16) for a in transfer['metadata_memory']}
    assert rule['metadata_required'] <= metadata <= rule['ram'].keys()
    claims += [parse(transfer['metadata_memory'][hex(a)], 8) == rule['ram'][a] for a in metadata]
    assert {int(a, 16) for a in transfer['teb_exception_chain']} == rule['teb']
    claims += [parse(transfer['teb_exception_chain'][hex(a)], 8) == rule['before'][a] for a in rule['teb']]
    assert {int(a, 16) for a in transfer['initialization_list']} == set(rule['list_bytes'])
    claims += [parse(transfer['initialization_list'][hex(a)], 8) == value for a, value in rule['list_bytes'].items()]
    saved = rule['saved_stack']; assert saved.keys() <= {int(a, 16) for a in transfer['stack_memory']}
    claims += [parse(transfer['stack_memory'][hex(a)], 8) == value for a, value in saved.items()]
    sp = int(observation['entry']['general']['rsp'], 16)
    caller = int.from_bytes(bytes(_cells(observation['entry_memory'])[sp + k] for k in range(8)), 'little')
    assert int(observation['exit']['rip'], 16) == caller
    claims += [parse(transfer['stack_memory'][hex(sp + k)], 8) == rule['before'][sp + k] for k in range(8)]
    span = observation['module_span']; first, last = span['first_step'], span['last_step']
    assert 0 < first <= last < len(observation['steps']) - 1
    outer_writes = []
    for row in transfer['ordered_accesses']:
        assert 0 <= row['step'] < len(observation['steps'])
        if row['kind'] != 'write': assert row['kind'] == 'read'; continue
        if first <= row['step'] <= last: continue
        address = parse(row['address'], 64); width = row['width']
        assert type(width) is int and width in (1, 2, 4, 8, 16)
        # Non-stack stores have their exact source-level sequence below.
        simplified = z.simplify(address)
        assert z.is_bv_value(simplified), 'Outer heap/stack pointer should be source-layout fixed'
        a = simplified.as_long()
        if set(range(a, a + width)) <= rule['stack']:
            assert not set(range(a, a + width)) & (rule['protected'] | metadata)
        else:
            outer_writes.append(row)
    assert len(outer_writes) == len(rule['metadata_writes'])
    for row, (kind, address, width, value) in zip(outer_writes, rule['metadata_writes'], strict=True):
        assert row['kind'] == kind and row['width'] == width
        claims += [parse(row['address'], 64) == address, parse(row['value'], width * 8) == value]
    prove(z.And(*claims))
    return {'status': 'independent_process_attach_source_transfer_proved', 'protected_bytes': len(rule['protected']),
        'gprs': len(GPRS), 'defined_flags_mask': '0xffffffff', 'exact_vectors': ['xmm0', 'xmm1'],
        'list_append': rule['list_relation'], 'outer_metadata_writes': len(outer_writes),
        'current_modref': 'Restored to its own arbitrary initial value', 'teb_exception_chain': 'Restored',
        'source_callbacks': ['tls-attach', 'dll-attach'], 'generic_event_count': [0, 6],
        'proof_sha256': proof.get('sha256'), 'contract_sha256': _digest(contract),
        'claim_limit': 'One complete source-bound normal leaf; old-list construction, dependency/notification/activation alternatives, other DLLs, faults, concurrency and remaining whole outer intervals remain conditional'}


def _claim(*, empty=False):
    loader, subject = 0x6000000000, 0x180000000
    wm, node, teb, peb, ldr, sp = 0x1425f0, 0x142730, 0x700000, 0x710000, 0x720000, 0x120008
    head = ldr + 0x30; tail = head if empty else 0x730000
    data, code, current, notify, debug = subject + 0x2000, subject + 0x4000, loader + 0x958b8, loader + 0x6d4e0, loader + 0x6d5d0
    addresses = {'modref': wm, 'node': node, 'teb': teb, 'peb': peb, 'ldr': ldr,
        'init_order_head': head, 'old_tail': tail, 'current_modref': current,
        'notification_head': notify, 'debug_channel': debug}
    memory = {}
    def put(a, value, width): memory.update({a + k: b for k, b in enumerate(value.to_bytes(width, 'little'))})
    code_raw = bytearray(317); code_raw[128] = 1
    protected = [{'address': hex(data), 'hex': bytes(64).hex()}, {'address': hex(code), 'hex': bytes(code_raw).hex()},
                 {'address': '0x140002000', 'hex': bytes(213).hex()}]
    memory.update(_cells(protected))
    for a, value in ((node, wm + 0xa0), (node + 8, wm + 0xa0), (node + 0x28, 0),
        (wm + 0x98, node), (wm + 0x88, 0), (wm + 0x20, 0), (wm + 0x28, 0),
        (wm + 0x30, subject), (wm + 0x38, code + 64), (head, tail), (head + 8, tail),
        (tail, head), (tail + 8, head), (notify, notify), (notify + 8, notify),
        (teb, 0xabcdef), (teb + 0x30, teb), (teb + 0x60, peb), (peb + 0x18, ldr),
        (current, 0x1234), (sp, loader + 0x40000)):
        put(a, value, 8)
    put(wm + 0x68, 4, 4); put(wm + 0x6c, 1, 2); put(debug, 0, 1)
    for a in range(sp - 4096, sp + 64): memory.setdefault(a, 0)
    symbols = {'dll_data_start': data, 'dll_data_end': data + 64, 'dll_event_log': data + 32,
        'dll_code_start': code, 'dll_code_end': code + 317,
        'dll_report_constant_immediate': code + 128, 'dll_entry': code + 64}
    observation = {'entry': {'general': {'rsp': hex(sp)}}, 'exit': {'rip': hex(loader + 0x40000)},
        'entry_memory': [{'address': hex(a), 'hex': f'{b:02x}'} for a, b in sorted(memory.items())],
        'steps': [{'protected_before': protected} for _ in range(30)],
        'module_span': {'first_step': 10, 'last_step': 19}}
    contract = {'addresses': {n: hex(v) for n, v in addresses.items()},
        'subject_symbols': {n: hex(v) for n, v in symbols.items()},
        'subject_module': {'base': hex(subject)}, 'entry_code': protected[1],
        'stack_range': {'address': hex(sp - 4096), 'length': 4160},
        'init_order_nodes': [] if empty else [hex(tail)]}
    rule = _source_rule(contract, observation)
    transfer = {'registers': {n: v.sexpr() for n, v in rule['registers'].items()},
        'flags': rule['flags'].sexpr(), 'defined_flags_mask': 0xffffffff,
        'guard': 'true', 'entry_guard': z.And(*rule['assumptions']).sexpr(),
        'vectors': {n: v.sexpr() for n, v in rule['vectors'].items()},
        'protected_memory': {hex(a): rule['ram'][a].sexpr() for a in rule['protected']},
        'metadata_memory': {hex(a): rule['ram'][a].sexpr() for a in rule['metadata_required']},
        'teb_exception_chain': {hex(a): rule['before'][a].sexpr() for a in rule['teb']},
        'initialization_list': {hex(a): value.sexpr() for a, value in rule['list_bytes'].items()},
        'stack_memory': {hex(a): v.sexpr() for a, v in rule['saved_stack'].items()},
        'ordered_accesses': []}
    transfer['stack_memory'].update({hex(sp + k): rule['before'][sp + k].sexpr() for k in range(8)})
    for step, (kind, address, width, value) in zip((1, 2, 3, 4, 5, 6, 21, 22, 23), rule['metadata_writes'], strict=True):
        transfer['ordered_accesses'].append({'step': step, 'kind': kind, 'address': z.BitVecVal(address, 64).sexpr(), 'width': width, 'value': value.sexpr()})
    proof = {'status': 'proved_for_observed_wine_process_attach', 'transfer': transfer,
        'symbols': {**{'process_attach_entry_' + n: 64 for n in GPRS}, 'process_attach_entry_flags': 32,
                    'process_attach_entry_xmm0': 128, 'process_attach_entry_xmm1': 128,
                    **{f'process_attach_entry_ram_{a:x}': 8 for a in rule['generic']}},
        'source': {'process_attach_sha256': _digest(observation), 'contract_sha256': _digest(contract)}}
    return proof, contract, observation


@pytest.mark.parametrize('empty', [False, True])
def test_source_contract_appends_to_nonempty_and_empty_initialization_lists(empty):
    proof, contract, observation = _claim(empty=empty)
    result = verify_process_attach_source_spec(proof, contract=contract, observation=observation)
    assert result['list_append']['empty_input'] is empty


@pytest.mark.parametrize('mutation', ['pointer-lanes', 'xmm-upper', 'current-modref', 'head-link', 'load-count',
                                    'progress-flag', 'source-code', 'count', 'register', 'status', 'flags', 'extra-store', 'entry-guard'])
def test_independent_full_source_spec_rejects_wrong_generic_effects(mutation):
    proof, contract, observation = _claim(); transfer = proof['transfer']
    a = {n: int(v, 16) for n, v in contract['addresses'].items()}
    data = int(contract['subject_symbols']['dll_data_start'], 16)
    if mutation == 'pointer-lanes':
        transfer['vectors']['xmm0'] = z.Concat(z.BitVecVal(a['init_order_head'], 64), z.BitVecVal(a['old_tail'], 64)).sexpr()
    elif mutation == 'xmm-upper': transfer['vectors']['xmm1'] = 'process_attach_entry_xmm1'
    elif mutation == 'current-modref': transfer['metadata_memory'][hex(a['current_modref'])] = '((_ extract 7 0) process_attach_entry_r14)'
    elif mutation == 'head-link': transfer['metadata_memory'][hex(a['init_order_head'] + 8)] = '#x00'
    elif mutation == 'load-count': transfer['metadata_memory'][hex(a['modref'] + 0x6c)] = '#x01'
    elif mutation == 'progress-flag': transfer['metadata_memory'][hex(a['modref'] + 0x69)] = '#x10'
    elif mutation == 'source-code': transfer['protected_memory'][contract['subject_symbols']['dll_report_constant_immediate']] = '#x02'
    elif mutation == 'count': transfer['protected_memory'][hex(data)] = f'process_attach_entry_ram_{data:x}'
    elif mutation in ('register', 'status'): transfer['registers']['rbx' if mutation == 'register' else 'rax'] = '#x0000000000000001'
    elif mutation == 'flags': transfer['flags'] = 'process_attach_entry_flags'
    elif mutation == 'extra-store': transfer['ordered_accesses'].append({'step': 24, 'kind': 'write', 'address': '#x0000000140002000', 'width': 1, 'value': '#x00'})
    else: transfer['entry_guard'] = '(and ' + transfer['entry_guard'] + ' (= process_attach_entry_r14 #x0000000000000000))'
    with pytest.raises(AssertionError):
        verify_process_attach_source_spec(proof, contract=contract, observation=observation)


def test_generic_list_append_allows_only_the_intended_empty_alias():
    head, tail, new, other = z.BitVecs('shape_head shape_tail shape_new shape_other', 64)
    memory = z.Array('shape_before', z.BitVecSort(64), z.BitVecSort(64))
    # Widen endpoints: an object ending exactly at2**64 is valid, while a
    # 64-bit endpoint addition would wrap and incorrectly admit aliases.
    disjoint = lambda a, b: z.Or(z.ULE(z.ZeroExt(1, a) + 16, z.ZeroExt(1, b)),
                               z.ULE(z.ZeroExt(1, b) + 16, z.ZeroExt(1, a)))
    assumptions = [z.ULE(a, (1 << 64) - 16) for a in (head, tail, new)]
    assumptions += [disjoint(new, head), disjoint(new, tail), z.Or(tail == head, disjoint(tail, head))]
    output = z.Store(z.Store(z.Store(z.Store(memory, new, head), new + 8, tail), tail, new), head + 8, new)
    changes = z.Or(output[new] != head, output[new + 8] != tail, output[tail] != new, output[head + 8] != new,
        z.And(other != new, other != new + 8, other != tail, other != head + 8, output[other] != memory[other]))
    for empty in (True, False):
        solver = z.Solver(); solver.add(*assumptions, tail == head if empty else tail != head, changes)
        assert solver.check() == z.unsat
    solver = z.Solver(); solver.add(*assumptions, tail == head + 8)
    assert solver.check() == z.unsat
