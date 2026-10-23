"""Evidence boundaries and concrete call-buffer effects, without execution."""
from copy import deepcopy

import pytest

from fdisbull.decoder import decode
from fdisbull.summaries import (builtin_signatures, instantiate_effects,
                               match_signatures, resolve_summary,
                               validate_prototype, validate_signature,
                               validate_summary)


def instructions(data, arch='x86', bits=64, address=0x1000):
    rows, offset = [], 0
    while offset < len(data):
        item = decode(data[offset:], address + offset, arch, bits)
        assert item is not None
        rows.append(item)
        offset += item['size']
    return rows


def contract(name):
    return resolve_summary(name, source={'kind': 'import', 'module': 'test-libc'})


@pytest.mark.parametrize('signature', builtin_signatures(), ids=lambda item: item['id'])
def test_real_helper_bytes_match_whole_bodies_in_explicit_modes(signature):
    rows = instructions(bytes.fromhex(signature['bytes']), signature['arch'], signature['bits'])
    result = match_signatures(rows, arch=signature['arch'], bits=signature['bits'])
    assert len(result) == 1
    match = result[0]
    assert match['signature_id'] == signature['id']
    assert match['whole_supplied_body'] and not match['function_boundary_proven']
    assert match['runtime_observed'] is False
    assert 'authored byte-loop fixture' in match['source']
    assert match['match'] == 'exact_bytes'
    summary = resolve_summary(match['name'], source={'kind': 'exact_signature', 'id': match['signature_id']})
    assert summary['arguments'][0]['index'] == 0
    assert summary['evidence_source'] == 'exact_signature'


def test_signature_catalog_is_not_a_prefix_or_label_heuristic():
    signature = builtin_signatures()[0]
    data = bytes.fromhex(signature['bytes'])
    rows = instructions(data)
    assert match_signatures(rows[:-1]) == []
    assert match_signatures(instructions(data + b'\x90')) == []
    assert match_signatures(rows, arch='x86', bits=32) == []
    rows[1]['address'] += 1
    assert match_signatures(rows) == []
    assert resolve_summary('memcpy') is None
    assert resolve_summary('memcpy', source='annotation') is None
    assert resolve_summary('probably_memcpy', source='import') is None


def test_masked_relocation_requires_explicit_byte_ranges_and_preserves_input():
    # movabs rax, relocated immediate; ret. This custom identity claims no C
    # semantics and is only used to test a full-function relocation mask.
    signature = dict(id='registered.return_pointer', name='return_pointer', arch='x86', bits=64,
                     bytes='48b81122334455667788c3', mask='ffff0000000000000000ff',
                     relocations=[dict(offset=2, size=8, kind='absolute64')], source='user registered relocation')
    rows = instructions(bytes.fromhex('48b8ffeeddccbbaa9988c3'))
    match = match_signatures(rows, [signature], 'x86', 64)[0]
    assert match['masked_offsets'] == list(range(2, 10))
    assert match['input_hex'] == '48b8ffeeddccbbaa9988c3'
    assert match['match'] == 'masked_bytes'
    assert resolve_summary(match['name'], source='exact_signature') is None
    broken = deepcopy(signature)
    broken.pop('relocations')
    with pytest.raises(ValueError, match='declared relocation'):
        validate_signature(broken)
    broken = deepcopy(signature)
    broken['mask'] = '00' * 11
    with pytest.raises(ValueError, match='constrain'):
        validate_signature(broken)


def test_symbol_contracts_have_typed_argument_roles_and_explicit_evidence():
    for name in ('memset', 'memcpy', 'memmove', 'read', 'write', 'fread', 'fwrite'):
        summary = contract(name)
        assert [item['index'] for item in summary['arguments']] == list(range(len(summary['arguments'])))
        assert all(item['type'] and item['role'] for item in summary['arguments'])
        assert summary['confidence'] == 'metadata_identity'
        assert summary['source'] == {'kind': 'import', 'module': 'test-libc'}
    assert contract('read')['effects'][0]['access'] == 'write'
    assert contract('fwrite')['effects'][0]['access'] == 'read'
    assert resolve_summary('memset', source='export', confidence=0)['confidence'] == 0
    with pytest.raises(ValueError, match='confidence'):
        resolve_summary('memset', source='export', confidence=float('nan'))


def test_memset_instantiates_exact_half_open_bytes_and_low_fill_byte():
    result = instantiate_effects(contract('memset'), {'dest': 0x47188, 'value': 0x1234, 'n': 12})
    assert result['valid'] and result['runtime_observed'] is False
    effect, = result['effects']
    assert (effect['access'], effect['address'], effect['size'], effect['end_exclusive']) == ('write', 0x47188, 12, 0x47194)
    assert effect['fill_byte'] == 0x34
    assert effect['extent'] == 'exact' and effect['minimum_size'] == 12
    assert effect['resolved']
    assert result['returns'] == {'op': 'const', 'value': 0x47188}


def test_memcpy_disjoint_overlapping_and_memmove_snapshot_contracts():
    disjoint = instantiate_effects(contract('memcpy'), [0x2000, 0x1000, 8])
    assert disjoint['valid'] and disjoint['overlap']['status'] == 'disjoint'
    assert [(e['access'], e['address'], e['size']) for e in disjoint['effects']] == [('read', 0x1000, 8), ('write', 0x2000, 8)]
    overlap = instantiate_effects(contract('memcpy'), [0x1004, 0x1000, 8])
    assert not overlap['valid'] and overlap['effects'] == []
    assert 'non-overlap precondition' in overlap['diagnostics'][0]
    move = instantiate_effects(contract('memmove'), [0x1004, 0x1000, 8])
    assert move['valid'] and len(move['effects']) == 2
    assert move['overlap'] == {'contract': 'allowed_snapshot', 'status': 'overlap'}
    empty = instantiate_effects(contract('memcpy'), [0x1000, 0x1000, 0])
    assert empty['valid'] and empty['overlap']['status'] == 'disjoint'
    assert all(item['empty'] for item in empty['effects'])


@pytest.mark.parametrize(('name', 'arguments', 'access', 'address', 'size'), [
    ('read', [3, 0x3000, 12], 'write', 0x3000, 12),
    ('write', [3, 0x3000, 12], 'read', 0x3000, 12),
    ('fread', [0x47188, 2, 6, 0x9000], 'write', 0x47188, 12),
    ('fwrite', [0x47188, 2, 6, 0x9000], 'read', 0x47188, 12),
])
def test_io_is_a_possible_range_not_a_completed_transfer(name, arguments, access, address, size):
    effect, = instantiate_effects(contract(name), arguments)['effects']
    assert (effect['access'], effect['address'], effect['size']) == (access, address, size)
    assert effect['extent'] == 'upper_bound' and effect['minimum_size'] == 0
    assert effect['status'] == 'conditional_static_effect'
    assert effect['runtime_observed'] is False


def test_unresolved_expressions_and_frame_values_are_retained():
    frame = dict(argument_values=[{'op': 'reg', 'name': 'rdi'}, {'op': 'const', 'value': 7},
                                  {'op': 'reg', 'name': 'rdx'}], abi='x86_64_sysv', signature_known=False)
    before = deepcopy(frame)
    result = instantiate_effects(contract('memset'), frame, {'registers': {'rdi': {'op': 'const', 'value': 0x8000}}})
    effect, = result['effects']
    assert effect['address'] == 0x8000 and effect['size'] is None
    assert effect['size_expression'] == {'op': 'reg', 'name': 'rdx'}
    assert not effect['resolved'] and frame == before
    records = [{'index': i, 'value': item} for i, item in enumerate(frame['argument_values'])]
    assert instantiate_effects(contract('memset'), {'arguments': records})['effects'][0]['fill_byte'] == 7
    unknown = instantiate_effects(contract('memcpy'), [0x2000])
    assert unknown['valid'] and unknown['overlap']['status'] == 'unknown'
    assert 'do not overlap' in unknown['conditions'][-1]
    assert unknown['effects'][0]['pointer_expression']['op'] == 'unknown'


def test_symbol_matched_flow_bounds_produce_a_range_without_resolving_the_value():
    length = {'op': 'reg', 'name': 'rdx', 'symbol': 'entry:rdx'}
    state = dict(registers={'rdx': {'op': 'const', 'value': 999}}, symbols={'rdx': 'write:later:rdx'},
                 bounds={'rdx': dict(min=1, max=6, symbol='entry:rdx', evidence=[dict(source='guard', predicate='ule')])})
    result = instantiate_effects(contract('fread'), [0x2000, 2, length, 1], state)
    effect, = result['effects']
    assert effect['size'] is None  # frozen rdx is not the later register value
    assert effect['minimum_size'] == 0 and effect['maximum_size'] == 12
    assert effect['size_range']['min'] == 2 and effect['size_range']['max'] == 12
    assert effect['possible_range']['end_exclusive'] == 0x200c
    state['bounds']['rdx']['symbol'] = 'unrelated'
    assert instantiate_effects(contract('fread'), [0x2000, 2, length, 1], state)['effects'][0]['size_range'] is None


@pytest.mark.parametrize('arguments', [[0x1000, 0, -1], [0x1000, 0, 1 << 64]])
def test_invalid_memset_lengths_produce_no_facts(arguments):
    result = instantiate_effects(contract('memset'), arguments)
    assert not result['valid'] and result['effects'] == []
    assert 'byte count' in result['diagnostics'][0]


def test_bad_fread_product_and_address_wrap_are_not_silently_truncated():
    for args in ([0x1000, 1 << 63, 8, 1], [0x1000, 1 << 64, 1, 1], [0x1000, -2, -3, 1]):
        result = instantiate_effects(contract('fread'), args)
        assert not result['valid'] and result['effects'] == []
    wrap = instantiate_effects(contract('memset'), [0xfffe, 0, 4], {'pointer_bits': 16})
    assert not wrap['valid'] and 'address width' in wrap['diagnostics'][0]
    empty = instantiate_effects(contract('fread'), [0, 0, None, 1])
    assert empty['valid'] and empty['effects'][0]['size'] == 0


def test_user_confirmed_prototype_can_define_custom_pointer_effects():
    prototype = dict(arguments=[dict(name='buffer', type='pointer', role='output'), dict(name='length', type='size_t', role='byte_count')])
    summary = dict(effects=[dict(access='write', pointer={'op': 'arg', 'name': 'buffer'}, size={'op': 'arg', 'name': 'length'})])
    custom = resolve_summary('fill_work', source={'kind': 'user_confirmed', 'detail': 'reviewed byte loop'},
                             prototype=prototype, summary=summary)
    result = instantiate_effects(custom, [0x4000, 16])
    assert result['effects'][0]['end_exclusive'] == 0x4010
    with pytest.raises(ValueError, match='user_confirmed'):
        resolve_summary('fill_work', source='import', prototype=prototype, summary=summary)
    # Prototype-only registration supplies no opaque inferred memory behavior.
    typed = resolve_summary('memcpy', source='user_confirmed', prototype=prototype)
    assert typed['effects'] == []
    bad = deepcopy(custom)
    bad['effects'][0]['size']['name'] = 'undeclared'
    with pytest.raises(ValueError, match='undeclared'):
        validate_summary(bad)
    with pytest.raises(ValueError, match='unique'):
        validate_prototype({'arguments': [dict(name='a', type='pointer'), dict(name='a', type='size_t')]})


def test_mutating_resolved_contract_does_not_change_later_resolution():
    first = contract('memset')
    first['arguments'][0]['name'] = 'changed'
    first['effects'].clear()
    assert contract('memset')['arguments'][0]['name'] == 'dest'
    assert len(contract('memset')['effects']) == 1


@pytest.mark.parametrize(('arch', 'abi', 'name', 'raw', 'expected'), [
    ('x86', 'x86_64_sysv', 'memcpy', 'bf00200000be00100000ba08000000e800000000c3', [('read', 0x1000, 8), ('write', 0x2000, 8)]),
    ('x86', 'x86_64_sysv', 'memset', 'bf00200000be34120000ba08000000e800000000c3', [('write', 0x2000, 8)]),
    ('arm64', 'aarch64_aapcs64', 'memcpy', '000084d2010082d2020180d201000094c0035fd6', [('read', 0x1000, 8), ('write', 0x2000, 8)]),
    ('arm64', 'aarch64_aapcs64', 'memset', '000084d2814682d2020180d201000094c0035fd6', [('write', 0x2000, 8)]),
])
def test_actual_call_bytes_flow_through_ir_frames_to_effects(arch, abi, name, raw, expected):
    from fdisbull.flowdata import analyze_flow
    from fdisbull.frames import analyze_frame
    from fdisbull.semantics import instruction_semantics

    rows = instructions(bytes.fromhex(raw), arch=arch)
    context = f'{arch}:64:little'
    for row in rows:
        row.update(id=f'{context}:{row["address"]:016x}', context=context)
    semantics = {row['id']: instruction_semantics(bytes.fromhex(row['bytes']), row['address'], arch, 64) for row in rows}
    edges = [dict(source=left['id'], target=right['id'], kind='fallthrough') for left, right in zip(rows, rows[1:])]
    flow = analyze_flow(rows, edges, rows[0]['id'], semantics)
    snapshot = dict(nodes=rows, entry=rows[0]['id'], context=context, arch=arch, bits=64)
    frame = analyze_frame(snapshot, semantics, flow, abi=abi)
    assert len(frame['calls']) == 1 and frame['calls'][0]['signature_known'] is False
    # The imported identity is supplied separately from the bytes. The actual
    # ABI candidate values come from native decoding, IR propagation and frames.
    result = instantiate_effects(contract(name), frame['calls'][0])
    assert result['valid']
    assert [(item['access'], item['address'], item['size']) for item in result['effects']] == expected
    if name == 'memset':
        assert result['effects'][0]['fill_byte'] == 0x34


@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -1, 2, [], {}, True, ' '])
def test_signature_confidence_is_validated_before_registration(confidence):
    signature = dict(builtin_signatures()[0], confidence=confidence)
    with pytest.raises(ValueError, match='confidence'):
        validate_signature(signature)
