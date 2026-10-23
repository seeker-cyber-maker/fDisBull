"""Indirect recovery uses normalized evidence, never pointer-looking scans."""
import struct

import pytest

from fdisbull.indirect import recover_indirect


def _const(value):
    return {'op': 'const', 'value': value}


def _reg(name):
    return {'op': 'reg', 'name': name}


def _binary(op, left, right):
    return {'op': op, 'args': [left, right]}


def _load(address, width=8, signed=False):
    return dict(op='load', address=address, width=width, signed=signed)


def _guarded(name='index', high=2, low=0, bits=64, signed=False):
    guard = dict(source='guard', predicate='le_u', taken=True, register=name,
                 symbol='entry:' + name, min=low, max=high, bits=bits, signed=signed)
    bound = dict(min=low, max=high, bits=bits, signed=signed, symbol='entry:' + name, evidence=[guard])
    return dict(registers={}, bounds={name: bound}, guards=[guard])


def _run(target, *, state=None, memory=b'', table=0x3000, executable=None, max_entries=256, target_context=None):
    reads = []

    def reader(address, width):
        reads.append((address, width))
        if table <= address < table + len(memory):
            return memory[address - table:address - table + width]
        return None

    snapshot = dict(nodes=[dict(id='dispatch', address='0x1000', context='normalized', flow='indirect_jump')])
    semantics = {'dispatch': dict(indirect_target=target, target_context=target_context)}
    states = {'in_states': {'dispatch': state if state is not None else {'registers': {}}}}
    result = recover_indirect(snapshot, semantics, states, reader, executable or (lambda address: 0x1000 <= address < 0x3000), max_entries=max_entries)
    return result, reads


def test_register_constants_and_fixed_pointer_slots_need_no_speculative_scan():
    result, reads = _run(_reg('target'), state={'registers': {'target': _const(0x2010)}})
    assert [item['target'] for item in result['candidates']] == [0x2010] and reads == []
    assert result['candidates'][0]['requires_decoder_validation']
    pointer, reads = _run(_load(_const(0x3000)), memory=struct.pack('<Q', 0x2020))
    assert pointer['candidates'][0]['target'] == 0x2020
    assert pointer['candidates'][0]['table_slot'] == 0x3000
    assert pointer['candidates'][0]['entry_width'] == 8 and reads == [(0x3000, 8)]
    assert pointer['candidates'][0]['bound_evidence'] == [{'kind': 'fixed_slot'}]


def test_guarded_absolute_entries_preserve_index_slots_and_bound_evidence():
    address = _binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(8)))
    result, reads = _run(_load(address), state=_guarded(), memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert [item['target'] for item in result['candidates']] == [0x2000, 0x2010, 0x2020]
    assert [item['table_slot'] for item in result['candidates']] == [0x3000, 0x3008, 0x3010]
    assert [item['index'][0]['value'] for item in result['candidates']] == [0, 1, 2]
    assert all(item['bound_evidence'][0]['guards'][0]['source'] == 'guard' for item in result['candidates'])
    assert reads == [(0x3000, 8), (0x3008, 8), (0x3010, 8)]
    assert not result['budget']['partial']


def test_signed_relative_entries_add_base_without_unsigned_wrap():
    slot = _binary('add', _const(0x3000), _binary('shl', _reg('index'), _const(2)))
    target = _binary('add', _const(0x2000), _load(slot, 4, signed=True))
    result, _ = _run(target, state=_guarded(), memory=struct.pack('<3i', -16, 16, 0))
    assert [item['target'] for item in result['candidates']] == [0x1FF0, 0x2010, 0x2000]
    assert result['candidates'][0]['loads'][0]['value'] == -16


@pytest.mark.parametrize('mode', ['unknown', 'nondominating', 'stale_symbol'])
def test_unbounded_or_stale_indices_are_only_proposals_and_do_not_read(mode):
    state = _guarded()
    if mode == 'unknown':
        state['bounds'] = {}
    elif mode == 'nondominating':
        state['guards'] = []
    else:
        state['bounds']['index']['symbol'] = 'old:index'
    expr = _load(_binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(8))))
    result, reads = _run(expr, state=state, memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert not result['candidates'] and result['proposals'] and reads == []


def test_truncated_unmapped_zero_and_nonexecutable_entries_are_not_invented():
    expr = _load(_binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(4))), 4)
    result, reads = _run(expr, state=_guarded(high=4), memory=struct.pack('<3I', 0x2000, 0, 0x5000) + b'\x01\x02')
    assert [item['target'] for item in result['candidates']] == [0x2000]
    assert {item['reason'] for item in result['rejections']} == {'target_not_executable',
                                                             'truncated_or_invalid_table_entry', 'unmapped_table_entry'}
    assert len(reads) == 5


def test_huge_finite_domain_is_budgeted_without_materializing_or_scanning_it():
    expr = _load(_binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(8))))
    result, reads = _run(expr, state=_guarded(high=(1 << 64) - 1), memory=struct.pack('<2Q', 0x2000, 0x2010), max_entries=2)
    assert len(result['candidates']) == len(reads) == 2
    assert result['budget']['partial'] and result['budget']['entries_examined'] == 2
    assert result['budget']['skipped_entries'] == (1 << 64) - 2


def test_constant_index_and_near_context_are_finite_without_a_guard():
    state = {'registers': {'index': _const(1)}}
    offset = _load(_binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(2))), 2)
    result, reads = _run(_binary('add', _const(0x10000), offset), state=state,
                        memory=struct.pack('<2H', 0x10, 0x20), target_context='x86:16:little:cs=1000', executable=lambda a: a == 0x10020)
    assert result['candidates'][0]['target'] == 0x10020
    assert result['candidates'][0]['target_context'] == 'x86:16:little:cs=1000'
    assert reads == [(0x3002, 2)]


def test_context_template_resolves_segment_selector_without_architecture_logic():
    selector, offset = _load(_const(0x3002), 2), _load(_const(0x3000), 2)
    target = _binary('add', _binary('mul', selector, _const(16)), offset)
    template = dict(template='x86:16:little:cs={segment:04x}', values={'segment': selector})
    result, reads = _run(target, memory=struct.pack('<2H', 0x20, 0x1000), target_context=template, executable=lambda a: a == 0x10020)
    candidate = result['candidates'][0]
    assert candidate['target'] == 0x10020 and candidate['target_context'] == 'x86:16:little:cs=1000'
    assert candidate['table_slot'] == 0x3000 and candidate['entry_width'] == 4
    assert sorted(reads) == [(0x3000, 2), (0x3002, 2)]


@pytest.mark.parametrize('mutation', ['reversed', 'boolean', 'range', 'bad_operation', 'bad_width', 'unknown_target'])
def test_malformed_inputs_stay_rejected_or_proposals_without_memory_scans(mutation):
    state = _guarded()
    target = _load(_binary('add', _const(0x3000), _reg('index')), 4)
    if mutation == 'reversed':
        state['bounds']['index']['min'] = 3
    elif mutation == 'boolean':
        state['bounds']['index']['max'] = True
    elif mutation == 'range':
        state['bounds']['index']['max'] = 1 << 65
    elif mutation == 'bad_operation':
        target = {'op': []}
    elif mutation == 'bad_width':
        target['width'] = 0
    else:
        target = {'op': 'unknown', 'reason': 'unsupported native instruction'}
    result, reads = _run(target, state=state)
    assert not result['candidates'] and (result['proposals'] or result['rejections']) and reads == []


def test_indirect_call_identity_missing_state_and_option_validation():
    graph = {'nodes': [{'id': 'call', 'flow': 'indirect_call', 'address': '0x1000', 'context': 'shared'}]}
    sem = {'call': {'indirect_target': _reg('target')}}
    state = {'in_states': {'call': {'registers': {'target': _const(0x2000)}}}}
    result = recover_indirect(graph, sem, state, lambda a, w: None, lambda a: True)
    assert result['candidates'][0]['flow'] == 'indirect_call' and result['candidates'][0]['source'] == 'call'
    assert result['candidates'][0]['source_context'] == 'shared'
    assert recover_indirect(graph, sem, {}, lambda a, w: None, lambda a: True)['proposals'][0]['reason'] == 'no_reachable_incoming_state'
    for value in (False, 0, 65537):
        with pytest.raises(ValueError):
            recover_indirect(graph, sem, state, lambda a, w: None, lambda a: True, max_entries=value)


def _native(chunks, arch, bits, *, initial=None, edges=None, cs=None, memory=b'', executable=None):
    from fdisbull.flowdata import analyze_flow
    from fdisbull.semantics import instruction_semantics
    nodes, semantics = [], {}
    address = 0x10000 if cs is not None else 0x1000
    for index, chunk in enumerate(chunks):
        raw = bytes.fromhex(chunk)
        semantic = instruction_semantics(raw, address, arch, bits, cs=cs)
        assert semantic['valid'] and semantic['size'] == len(raw)
        identity = f'n{index}'
        semantics[identity] = semantic
        nodes.append(dict(id=identity, address=f'0x{address:x}', context=semantic.get('target_context') or 'native', flow=semantic['flow']))
        address += len(raw)
    if edges is None:
        edges = [dict(source=nodes[i]['id'], target=nodes[i + 1]['id'], kind='fallthrough') for i in range(len(nodes) - 1)]
    flow = analyze_flow(nodes, edges, nodes[0]['id'], semantics, initial=initial)
    reads = []

    def reader(address, width):
        reads.append((address, width))
        return memory[address - 0x3000:address - 0x3000 + width] if 0x3000 <= address < 0x3000 + len(memory) else None

    result = recover_indirect(dict(nodes=nodes, edges=edges), semantics, flow, reader,
                              executable or (lambda a: 0x1F00 <= a < 0x2100))
    return result, reads, flow


@pytest.mark.parametrize('arch,chunks,initial,memory', [
    ('x86', ['48b81020000000000000', 'ffd0'], None, b''),
    ('arm64', ['e00301aa', '00001fd6'], {'x1': 0x2010}, b''),
    ('arm64', ['200040f9', '00001fd6'], {'x1': 0x3000}, struct.pack('<Q', 0x2010)),
])
def test_actual_x86_and_arm64_constants_and_pointer_loads_share_recovery(arch, chunks, initial, memory):
    result, _, flow = _native(chunks, arch, 64, initial=initial, memory=memory)
    assert flow['stable'] and [item['target'] for item in result['candidates']] == [0x2010]
    assert not result['proposals'] and not result['rejections']


def test_actual_x86_guarded_absolute_jump_table_uses_dominating_branch():
    chunks = ['48b80030000000000000', '4883f902', '7703', 'ff24c8', 'c3']
    edges = [dict(source='n0', target='n1', kind='fallthrough'), dict(source='n1', target='n2', kind='fallthrough'),
             dict(source='n2', target='n4', kind='branch'), dict(source='n2', target='n3', kind='fallthrough')]
    result, reads, _ = _native(chunks, 'x86', 64, edges=edges, memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert [item['target'] for item in result['candidates']] == [0x2000, 0x2010, 0x2020]
    assert all(item['bound_evidence'][0]['guards'][0]['source'] == 'n2' for item in result['candidates'])
    assert reads == [(0x3000, 8), (0x3008, 8), (0x3010, 8)]


def test_actual_arm64_guarded_signed_relative_table_uses_the_same_algorithm():
    # CMP X2,2; B.HI default; LDRSW X0,[X1,X2,LSL2]; ADD X0,X3,X0; BR X0; RET.
    chunks = ['5f0800f1', '88000054', '2078a2b8', '6000008b', '00001fd6', 'c0035fd6']
    edges = [dict(source='n0', target='n1', kind='fallthrough'), dict(source='n1', target='n5', kind='branch'),
             dict(source='n1', target='n2', kind='fallthrough'), dict(source='n2', target='n3', kind='fallthrough'),
             dict(source='n3', target='n4', kind='fallthrough')]
    result, reads, _ = _native(chunks, 'arm64', 64, edges=edges, initial={'x1': 0x3000, 'x3': 0x2000},
                              memory=struct.pack('<3i', -16, 0, 16))
    assert [item['target'] for item in result['candidates']] == [0x1FF0, 0x2000, 0x2010]
    assert reads == [(0x3000, 4), (0x3004, 4), (0x3008, 4)]
    assert all(item['loads'][0]['signed'] for item in result['candidates'])


def test_actual_32bit_guard_cannot_bound_unknown_high_bits_of_64bit_table_index():
    chunks = ['48b80030000000000000', '83f902', '7703', 'ff24c8', 'c3']
    edges = [dict(source='n0', target='n1', kind='fallthrough'), dict(source='n1', target='n2', kind='fallthrough'),
             dict(source='n2', target='n4', kind='branch'), dict(source='n2', target='n3', kind='fallthrough')]
    result, reads, _ = _native(chunks, 'x86', 64, edges=edges, memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert not result['candidates'] and result['proposals'] and reads == []


def test_matching_projected_index_is_bounded_but_unmasked_occurrences_are_not():
    state = _guarded(bits=32)
    frozen = {'op': 'reg', 'name': 'index', 'symbol': 'entry:index'}
    projection = _binary('and', frozen, _const(0xFFFFFFFF))
    state['bounds']['index'].update(projected=True, projection=projection)
    target = _load(_binary('add', _const(0x3000), _binary('mul', _binary('and', _reg('index'), _const(0xFFFFFFFF)), _const(8))))
    result, _ = _run(target, state=state, memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert len(result['candidates']) == 3
    bad, reads = _run(_binary('add', _reg('index'), target), state=state)
    assert not bad['candidates'] and bad['proposals'] and reads == []


def test_actual_dos_near_memory_target_is_canonical_with_selected_cs():
    result, reads, _ = _native(['ff27'], 'x86', 16, cs=0x1000, initial={'ds': 0x300, 'bx': 0},
                              memory=struct.pack('<H', 0x20), executable=lambda a: a == 0x10020)
    assert result['candidates'][0]['target'] == 0x10020
    assert result['candidates'][0]['target_context'] == 'x86:16:little:cs=1000'
    assert reads == [(0x3000, 2)]


@pytest.mark.parametrize('partial', ['flow', 'cfg'])
def test_budget_stopped_states_do_not_admit_targets_before_joins_converge(partial):
    graph = dict(nodes=[dict(id='dispatch', flow='indirect_jump')])
    flow = dict(in_states={'dispatch': {'registers': {'target': _const(0x2000)}}}, stable=True)
    if partial == 'flow':
        flow.update(stable=False, budget_exhausted=True)
    else:
        graph['budget_exhausted'] = True
    reads = []
    result = recover_indirect(graph, {'dispatch': {'indirect_target': _reg('target')}}, flow,
                              lambda a, w: reads.append((a, w)), lambda a: True)
    assert result['budget']['partial'] and result['proposals'] and not result['candidates']
    assert reads == []


@pytest.mark.parametrize('offset,accepted', [(0x20, True), (0x10020, False)])
def test_actual_dos_32bit_far_offset_obeys_adapter_segment_limit_constraint(offset, accepted):
    result, _, _ = _native(['66ff2f'], 'x86', 16, cs=0x1000, initial={'ds': 0x300, 'bx': 0},
                           memory=struct.pack('<IH', offset, 0x1000), executable=lambda a: True)
    assert bool(result['candidates']) is accepted
    if accepted:
        assert result['candidates'][0]['target'] == 0x10020
        assert result['candidates'][0]['target_constraints'][0]['value'] == 0x20
    else:
        assert result['rejections'][0]['reason'] == 'target_constraint_failed'


@pytest.mark.parametrize('mode', ['tainted', 'overlap', 'unknown_alias'])
def test_memory_mutation_policy_is_not_bypassed_by_recovery_snapshot_reads(mode):
    state = {'registers': {}, 'memory_writes': [], 'memory_tainted': False}
    if mode == 'tainted':
        state['memory_tainted'] = True
    elif mode == 'overlap':
        state['memory_writes'] = [{'address': _const(0x3001), 'width': 1}]
    else:
        state['memory_writes'] = [{'address': _reg('unknown_address'), 'width': 8}]
    result, reads = _run(_load(_const(0x3000)), state=state, memory=struct.pack('<Q', 0x2000))
    assert not result['candidates'] and reads == []
    assert result['rejections'][0]['reason'] == 'snapshot_memory_may_be_modified'


def test_known_table_write_blocks_only_overlapping_entry_and_keeps_other_bounds():
    state = _guarded()
    state['memory_writes'] = [{'address': _const(0x3008), 'width': 8}]
    target = _load(_binary('add', _const(0x3000), _binary('mul', _reg('index'), _const(8))))
    result, reads = _run(target, state=state, memory=struct.pack('<3Q', 0x2000, 0x2010, 0x2020))
    assert [item['target'] for item in result['candidates']] == [0x2000, 0x2020]
    assert result['rejections'][0]['reason'] == 'snapshot_memory_may_be_modified'
    assert reads == [(0x3000, 8), (0x3010, 8)]


def test_actual_store_then_indirect_jump_never_reuses_original_file_pointer():
    chunks = ['488905f91f0000', 'ff25f31f0000']  # MOV [3000h],RAX; JMP [3000h].
    result, reads, flow = _native(chunks, 'x86', 64, memory=struct.pack('<Q', 0x2000))
    assert flow['stable'] and not result['candidates'] and reads == []
    assert result['proposals'] or result['rejections']


def test_project_auto_analysis_does_not_retain_legacy_pointer_promotion_after_unknown_write(tmp_path):
    from fdisbull.project import Project
    raw = bytearray(0x50)
    raw[:13] = bytes.fromhex('48890519000000ff2513000000')  # MOV [1020h],RAX; JMP [1020h].
    struct.pack_into('<Q', raw, 0x20, 0x1040)
    raw[0x40] = 0xC3
    source = tmp_path / 'overwritten-pointer.bin'
    source.write_bytes(raw)
    with Project.create(tmp_path / 'overwritten-pointer.fdb', source, arch='x86', base=0x1000) as project:
        project.auto_analyze(max_rounds=4)
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE source='0000000000001007' AND target='0000000000001040' AND kind='resolved_branch'").fetchone()
        result = project.function_analysis(0x1000)['result']['indirect']
        assert not result['candidates'] and (result['proposals'] or result['rejections'])


def test_zero_address_is_a_target_when_explicitly_executable():
    result, reads = _run(_const(0), executable=lambda address: address == 0)
    assert result['candidates'][0]['target'] == 0 and not reads
