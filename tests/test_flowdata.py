"""Generic IR propagation tests deliberately use no architecture names."""
from fdisbull.flowdata import analyze_flow, evaluate_expression


def c(value):
    return {'op': 'const', 'value': value}


def r(name):
    return {'op': 'reg', 'name': name}


def op(name, a, b):
    return {'op': name, 'args': [a, b]}


def instruction(assignments=(), **more):
    return dict(assignments=[{'register': name, 'value': value, 'bits': bits} for name, value, bits in assignments],
                clobbers=[], memory=[], **more)


def edge(a, b, kind='fallthrough', **more):
    return dict(source=a, target=b, kind=kind, **more)


def test_simultaneous_assignments_wrap_and_unknown_symbols_are_frozen():
    semantics = {
        'a': instruction([('left', r('right'), 8), ('right', r('left'), 8)]),
        'b': instruction([('small', c(0x123), 8), ('saved', r('unknown'), 32)]),
        'c': instruction([('unknown', c(5), 32)]),
    }
    result = analyze_flow(list(semantics), [edge('a', 'b'), edge('b', 'c')], 'a', semantics,
                          initial={'left': 1, 'right': 2})
    final = result['out_states']['c']
    assert final['registers']['left'] == c(2) and final['registers']['right'] == c(1)
    assert final['registers']['small'] == c(0x23)
    saved = evaluate_expression(r('saved'), final)
    assert saved['op'] == 'reg' and saved['name'] == 'unknown' and saved['symbol'] == 'entry:unknown'
    assert result['stable'] and not result['budget_exhausted']


def test_symbolic_stack_preserves_original_numeric_origin_and_saved_values():
    semantics = {
        'push': instruction([('top', op('sub', r('top'), c(2)), 16)], stack_pointer='top', stack_delta=-2),
        'frame': instruction([('frame', r('top'), 16)], stack_pointer='top', frame_pointer='frame'),
        'pop': instruction([('result', {'op': 'load', 'address': r('top'), 'width': 2}, 16),
                            ('top', op('add', r('top'), c(2)), 16)], stack_pointer='top', stack_delta=2),
    }
    semantics['push']['memory'] = [{'address': op('sub', r('top'), c(2)), 'access': 'write', 'width': 2, 'value': c(0x5678)}]
    result = analyze_flow(list(semantics), [edge('push', 'frame'), edge('frame', 'pop')], 'push', semantics, initial={'top': 0x80})
    state = result['in_states']['pop']
    assert state['registers']['top'] == {'op': 'stack', 'base': 'entry_sp', 'offset': -2}
    assert state['registers']['frame'] == state['registers']['top']
    assert state['initial_stack_pointer'] == 0x80
    assert state['memory']['entry_sp:-2:2'] == c(0x5678)
    assert result['out_states']['pop']['registers']['result'] == c(0x5678)
    assert result['out_states']['pop']['registers']['top']['offset'] == 0


def test_unknown_or_overlapping_stores_kill_saved_stack_values():
    start = instruction(stack_pointer='top')
    start['memory'] = [{'address': r('top'), 'access': 'write', 'width': 4, 'value': c(42)}]
    partial = instruction(stack_pointer='top')
    partial['memory'] = [{'address': op('add', r('top'), c(2)), 'access': 'write', 'width': 1, 'value': c(7)}]
    unknown = instruction(stack_pointer='top')
    unknown['memory'] = [{'address': r('pointer'), 'access': 'conditional_write', 'width': 4}]
    semantics = {'a': start, 'b': partial, 'c': unknown}
    result = analyze_flow(list(semantics), [edge('a', 'b'), edge('b', 'c')], 'a', semantics)
    assert 'entry_sp:+0:4' not in result['out_states']['b']['memory']
    assert result['out_states']['c']['memory'] == {}


def test_expression_load_sign_and_callback_bounds_preserve_unresolved_loads():
    calls = []

    def reader(address, width):
        calls.append((address, width))
        return b'\xfc\xff\xff\xff'

    expression = {'op': 'load', 'address': op('add', c(0x1000), c(4)), 'width': 4, 'signed': True}
    assert evaluate_expression(expression, {}, reader) == c(-4)
    assert calls == [(0x1004, 4)]
    unresolved = evaluate_expression({'op': 'load', 'address': r('index'), 'width': 4}, {})
    assert unresolved['op'] == 'load' and unresolved['address']['name'] == 'index'
    assert unresolved['address']['symbol'] == 'entry:index'


def test_diamond_join_keeps_equal_values_and_drops_conflicts():
    semantics = {'entry': instruction(), 'a': instruction([('same', c(1), 32), ('different', c(2), 32)]),
                 'b': instruction([('same', c(1), 32), ('different', c(3), 32)]), 'join': instruction()}
    edges = [edge('entry', 'a'), edge('entry', 'b'), edge('a', 'join'), edge('b', 'join')]
    result = analyze_flow(list(semantics), edges, 'entry', semantics)
    assert result['in_states']['join']['registers']['same'] == c(1)
    assert 'different' not in result['in_states']['join']['registers']


def test_unsigned_guard_bounds_dominate_guarded_dispatch():
    semantics = {'cmp': instruction(comparison={'left': r('index'), 'right': c(3), 'bits': 16}),
                 'branch': instruction(branch_condition={'predicate': 'gt_u', 'source': 'comparison'}),
                 'dispatch': instruction(), 'outside': instruction()}
    edges = [edge('cmp', 'branch'), edge('branch', 'outside', 'conditional'), edge('branch', 'dispatch')]
    result = analyze_flow(list(semantics), edges, 'cmp', semantics)
    state = result['in_states']['dispatch']
    bound = state['bounds']['index']
    assert (bound['min'], bound['max'], bound['bits'], bound['signed']) == (0, 3, 16, False)
    assert bound['symbol'] == 'entry:index'
    assert bound['evidence'][0] in state['guards']
    assert bound['evidence'][0]['source'] == 'branch'
    taken = next(e for e in result['edge_states'] if e['target'] == 'outside')
    assert taken['state']['bounds']['index']['min'] == 4


def test_width_projected_bounds_keep_the_exact_masked_symbol_expression():
    projected = op('and', r('wide_index'), c(0xffffffff))
    semantics = {'cmp': instruction(comparison={'left': projected, 'right': c(3), 'bits': 32}),
                 'branch': instruction(branch_condition={'predicate': 'le_u', 'source': 'comparison'}),
                 'dispatch': instruction()}
    result = analyze_flow(list(semantics), [edge('cmp', 'branch'), edge('branch', 'dispatch', 'conditional')], 'cmp', semantics)
    state = result['in_states']['dispatch']
    bound = state['bounds']['wide_index']
    assert bound['projected'] and (bound['min'], bound['max']) == (0, 3)
    assert bound['projection'] == evaluate_expression(projected, state)
    assert bound['projection']['args'][0]['symbol'] == bound['symbol']
    assert bound['evidence'][0]['projection'] == bound['projection']


def test_nondominating_guard_cannot_expand_a_table_bound_after_join():
    semantics = {'entry': instruction(), 'cmp': instruction(comparison={'left': r('index'), 'right': c(4), 'bits': 32}),
                 'branch': instruction(branch_condition={'predicate': 'lt_u', 'source': 'comparison'}),
                 'unbounded': instruction(), 'join': instruction()}
    edges = [edge('entry', 'cmp'), edge('entry', 'unbounded'), edge('cmp', 'branch'),
             edge('branch', 'join', 'conditional'), edge('unbounded', 'join')]
    result = analyze_flow(list(semantics), edges, 'entry', semantics)
    assert result['in_states']['join']['bounds'] == {}
    assert result['in_states']['join']['guards'] == []


def test_signed_comparison_prunes_impossible_constant_path_and_flags_clobber():
    semantics = {'cmp': instruction(comparison={'left': c(0xff), 'right': c(0), 'bits': 8}),
                 'branch': instruction(branch_condition={'predicate': 'lt_s', 'source': 'comparison'}),
                 'yes': instruction(), 'no': instruction()}
    edges = [edge('cmp', 'branch'), edge('branch', 'yes', 'conditional'), edge('branch', 'no')]
    result = analyze_flow(list(semantics), edges, 'cmp', semantics)
    assert 'yes' in result['in_states'] and 'no' not in result['in_states']
    semantics['branch']['flags_clobbered'] = True
    result = analyze_flow(list(semantics), edges, 'cmp', semantics)
    assert 'yes' in result['in_states'] and 'no' in result['in_states']


def test_call_return_uses_instruction_width_and_generic_abi_clobbers():
    semantics = {'call': instruction(stack_pointer='top', stack_delta=-4, flow='call', return_address_size=4),
                 'next': instruction(stack_pointer='top')}
    result = analyze_flow(list(semantics), [edge('call', 'next')], 'call', semantics,
                          initial={'top': 0x100, 'volatile': 7, 'saved': 8},
                          abi={'caller_clobbers': ['volatile'], 'return_width': 2, 'callee_cleanup': 0})
    state = result['in_states']['next']
    assert state['registers']['top']['offset'] == 0  # actual call pushes4, not ABI2
    assert state['registers']['saved'] == c(8) and 'volatile' not in state['registers']
    assert result['out_states']['call']['registers'] == state['registers']


def test_loop_converges_without_inventing_an_ever_growing_stack_offset():
    semantics = {'entry': instruction(stack_pointer='top'),
                 'loop': instruction([('top', op('sub', r('top'), c(2)), 16)], stack_pointer='top')}
    result = analyze_flow(list(semantics), [edge('entry', 'loop'), edge('loop', 'loop')], 'entry', semantics)
    assert result['stable'] and result['steps'] < 10
    assert 'top' not in result['in_states']['loop']['registers']


def test_budget_stop_is_partial_and_external_edges_remain_explicit():
    semantics = {'a': instruction(), 'b': instruction(), 'c': instruction()}
    result = analyze_flow(list(semantics), [edge('a', 'b'), edge('b', 'c'), edge('a', 'external')],
                          'a', semantics, max_steps=1)
    assert result['budget_exhausted'] and not result['stable']
    assert {u['kind'] for u in result['unresolved']} == {'budget_exhausted', 'external_edge'}


def test_real_dos_ir_stack_cells_and_frame_moves_need_no_solver_architecture_rules():
    from fdisbull.semantics import instruction_semantics
    semantics = {i: instruction_semantics(bytes.fromhex(raw), 0x10000+i*8, 'x86', 16, cs=0x1000)
                 for i, raw in enumerate(('680700', '89e5', '58'))}
    result = analyze_flow(list(semantics), [edge(0, 1), edge(1, 2)], 0, semantics,
                          initial={'sp': 0x80, 'ss': 0x2000})
    assert result['in_states'][2]['memory']['entry_sp:-2:2'] == c(7)
    assert result['out_states'][2]['registers']['ax'] == c(7)
    assert result['out_states'][2]['registers']['bp']['offset'] == -2
    assert result['out_states'][2]['registers']['sp']['offset'] == 0


def test_real_arm_ir_stack_pair_and_load_use_the_same_generic_solver():
    from fdisbull.semantics import instruction_semantics
    # STP X0,X1,[SP,#-16]!; LDP X2,X3,[SP],#16.
    semantics = {0: instruction_semantics(bytes.fromhex('e007bfa9'), 0x1000, 'arm64', 64),
                 1: instruction_semantics(bytes.fromhex('e20fc1a8'), 0x1004, 'arm64', 64)}
    result = analyze_flow(list(semantics), [edge(0, 1)], 0, semantics,
                          initial={'sp': 0x8000, 'x0': 11, 'x1': 22})
    assert result['out_states'][1]['registers']['x2'] == c(11)
    assert result['out_states'][1]['registers']['x3'] == c(22)
    assert result['out_states'][1]['registers']['sp']['offset'] == 0


def test_stored_constants_obey_memory_width_before_unsigned_and_signed_loads():
    store = instruction()
    store['memory'] = [{'address': c(0x2000), 'access': 'write', 'width': 1, 'value': c(-1)}]
    load = instruction([('unsigned', {'op': 'load', 'address': c(0x2000), 'width': 1}, 64),
                        ('signed', {'op': 'load', 'address': c(0x2000), 'width': 1, 'signed': True}, 64)])
    result = analyze_flow(['store', 'load'], [edge('store', 'load')], 'store', {'store': store, 'load': load})
    assert result['out_states']['load']['registers']['unsigned'] == c(255)
    assert result['out_states']['load']['registers']['signed'] == c((1 << 64)-1)


def test_snapshot_reader_never_resurrects_overwritten_or_unknown_aliased_data():
    calls = []

    def reader(address, width):
        calls.append((address, width))
        return bytes([7]) * width

    for address in (c(0x2000), r('unknown_pointer')):
        store = instruction()
        store['memory'] = [{'address': address, 'access': 'write', 'width': 2}]
        load = instruction([('value', {'op': 'load', 'address': c(0x2001), 'width': 1}, 64)])
        result = analyze_flow(['store', 'load'], [edge('store', 'load')], 'store', {'store': store, 'load': load}, read_memory=reader)
        assert result['out_states']['load']['registers']['value']['op'] == 'load'
    assert calls == []
    store['memory'] = [{'address': c(0x3000), 'access': 'write', 'width': 2}]
    result = analyze_flow(['store', 'load'], [edge('store', 'load')], 'store', {'store': store, 'load': load}, read_memory=reader)
    assert result['out_states']['load']['registers']['value'] == c(7)
    assert calls == [(0x2001, 1)]


def test_repeated_stores_invalidate_bulk_aliases_while_zero_count_touches_nothing():
    save = instruction(stack_pointer='top')
    save['memory'] = [{'address': r('top'), 'access': 'write', 'width': 2, 'value': c(42)}]
    repeated = instruction(stack_pointer='top')
    repeated['memory'] = [{'address': c(0x2000), 'access': 'conditional_write', 'width': 2,
                          'repeat': {'count': None, 'count_register': 'count'}, 'value': c(0)}]
    semantics = {'save': save, 'repeat': repeated}
    result = analyze_flow(list(semantics), [edge('save', 'repeat')], 'save', semantics)
    assert result['out_states']['repeat']['memory'] == {}
    assert result['out_states']['repeat']['memory_tainted']
    result = analyze_flow(list(semantics), [edge('save', 'repeat')], 'save', semantics, initial={'count': 0})
    assert result['out_states']['repeat']['memory']['entry_sp:+0:2'] == c(42)
    assert not result['out_states']['repeat']['memory_tainted']


def test_cyclic_store_history_is_a_set_and_reaches_a_fixed_point():
    pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 0),
             (0, 6), (1, 6), (2, 0), (3, 4), (4, 7), (5, 6), (6, 4), (7, 7)]
    semantics = {i: instruction() for i in range(8)}
    for i, semantic in semantics.items():
        semantic['memory'] = [{'address': c(i*8), 'width': 8, 'access': 'write'}]
    result = analyze_flow(list(semantics), [edge(a, b) for a, b in pairs], 0, semantics, max_steps=100)
    assert result['stable'] and result['steps'] < 50
    for state in result['in_states'].values():
        history = state['memory_writes']
        assert len(history) == 8
        assert history == sorted(history, key=lambda value: __import__('json').dumps(value, sort_keys=True, separators=(',', ':')))


def test_tainted_write_history_stays_at_top_while_exact_new_values_survive():
    from fdisbull.flowdata import memory_read_allowed
    taint, save = instruction(), instruction()
    taint['memory'] = [{'address': r('pointer'), 'width': 1, 'access': 'write'}]
    save['memory'] = [{'address': c(0x2000), 'width': 1, 'access': 'write', 'value': c(42)}]
    result = analyze_flow(['taint', 'save'], [edge('taint', 'save'), edge('save', 'save')], 'taint', {'taint': taint, 'save': save}, max_steps=20)
    state = result['out_states']['save']
    assert result['stable'] and state['memory_tainted'] and state['memory_writes'] == []
    assert state['memory']['absolute:+8192:1'] == c(42)
    assert not memory_read_allowed(0x3000, 1, state)


def test_unknown_callee_cleanup_discards_sp_but_explicit_cleanup_is_applied():
    semantics = {'call': instruction(stack_pointer='top', stack_delta=-4, flow='call', return_address_size=4),
                 'next': instruction(stack_pointer='top')}
    for abi in (None, {'caller_clobbers': [], 'callee_cleanup': None}):
        result = analyze_flow(list(semantics), [edge('call', 'next')], 'call', semantics, abi=abi)
        assert 'top' not in result['in_states']['next']['registers']
        assert any(item['kind'] == 'unknown_call_stack_cleanup' for item in result['unresolved'])
    result = analyze_flow(list(semantics), [edge('call', 'next')], 'call', semantics,
                          abi={'caller_clobbers': [], 'callee_cleanup': 6})
    assert result['in_states']['next']['registers']['top']['offset'] == 6
