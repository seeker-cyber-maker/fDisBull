"""Frame facts use native instruction IR and generic fixed-point states."""
import json

import pytest

from fdisbull.flowdata import analyze_flow
from fdisbull.frames import ABI_PROFILES, analyze_frame
from fdisbull.semantics import instruction_semantics


def _native(raw, bits=64, arch='x86', abi=None, initial=None):
    raw = bytes.fromhex(raw)
    nodes, semantics, edges = [], {}, []
    offset = 0
    context = f'{arch}:{bits}:little' + (':cs=0100' if bits == 16 else '')
    while offset < len(raw):
        address = 0x1000 + offset
        semantic = instruction_semantics(raw[offset:], address, arch, bits, cs=0x100 if bits == 16 else None)
        assert semantic and semantic['valid']
        identity = f'{context}@{address:#x}'
        nodes.append(dict(id=identity, address=hex(address), context=context, size=semantic['size'],
                          flow=semantic['flow'], mnemonic=semantic['mnemonic']))
        semantics[identity] = semantic
        offset += semantic['size']
    for source, target in zip(nodes, nodes[1:]):
        if source['flow'] in ('next', 'call', 'indirect_call'):
            edges.append(dict(source=source['id'], target=target['id'], kind='fallthrough'))
    snapshot = dict(nodes=nodes, edges=edges, entry=nodes[0]['id'], arch=arch, bits=bits, context=context)
    profile = ABI_PROFILES[abi] if abi else None
    flow = analyze_flow(nodes, edges, snapshot['entry'], semantics, initial=initial, abi=profile)
    assert flow['stable']
    return snapshot, semantics, flow


@pytest.mark.parametrize('argument,opcode,profile,address_size,cleanup', [
    ('04', 'c3', 'x86_16_cdecl_near', 2, 0),
    ('06', 'cb', 'x86_16_cdecl_far', 4, 0),
    ('06', 'ca0400', 'x86_16_cdecl_far', 4, 4),
])
def test_native_dos_near_far_frames_and_cleanup_are_relative_to_entry_sp(argument, opcode, profile, address_size, cleanup):
    # push bp; mov bp,sp; sub sp,8; load first argument; store local;
    # push42; assumed-returning call; addsp2; movax7; leave; near/farret.
    snapshot, semantic, flow = _native('558bec83ec088b46' + argument + '8946fe6a2ae8000083c402b80700c9' + opcode,
                                      bits=16, abi=profile, initial={'ss': 0x2222, 'sp': 0xFFFE})
    result = analyze_frame(snapshot, semantic, flow, profile)
    assert result['status'] == 'candidate' and not result['function_boundary_proven']
    assert any(item['register'] == 'bp' and item['entry_sp_offset'] == -2 for item in result['frame_pointer_relations'])
    slots = {(slot['offset'], slot['width']): slot for slot in result['stack_slots']}
    assert slots[(address_size, 2)]['classification'] == 'incoming_argument_candidate'
    assert slots[(-4, 2)]['classification'] == 'local_or_saved_value_candidate'
    assert any(access['access'] == 'write' for access in slots[(-4, 2)]['accesses'])
    assert result['calls'][0]['argument_values'][0] == {'op': 'const', 'value': 42}
    returned = result['returns'][0]
    assert returned['return_address_size'] == address_size and returned['callee_cleanup'] == cleanup
    assert returned['entry_sp_offset_before_return'] == 0
    assert returned['values'][0]['value'] == {'op': 'const', 'value': 7}
    assert result['callee_cleanup']['matches_selected_abi'] is (cleanup == 0)
    assert result['abi']['profile']['name'] == profile
    json.dumps(result)


def test_native_sysv_register_arguments_and_frame_pointer_relation():
    snapshot, semantic, flow = _native('554889e54883ec10bf2a000000be07000000e800000000b82a000000c9c3',
                                      abi='x86_64_sysv')
    result = analyze_frame(snapshot, semantic, flow, 'sysv_x86_64')
    call = result['calls'][0]
    assert call['arguments'][0]['location'] == {'kind': 'register', 'register': 'rdi'}
    assert call['argument_values'][:2] == [{'op': 'const', 'value': 42}, {'op': 'const', 'value': 7}]
    assert not call['signature_known'] and call['candidate']
    assert any(item['register'] == 'rbp' and item['entry_sp_offset'] == -8 for item in result['frame_pointer_relations'])
    assert result['returns'][0]['values'][0]['value'] == {'op': 'const', 'value': 42}
    assert result['returns'][0]['entry_sp_offset_before_return'] == 0


def test_native_win64_shadow_space_and_stack_argument_are_distinct():
    snapshot, semantic, flow = _native('4883ec28b92a00000048c74424202b000000e8000000004883c428b807000000c3',
                                      abi='x86_64_win64')
    result = analyze_frame(snapshot, semantic, flow, 'win64')
    call = result['calls'][0]
    assert call['shadow_space'] == 32
    assert call['argument_values'][0] == {'op': 'const', 'value': 42}
    assert call['argument_values'][4] == {'op': 'const', 'value': 43}
    stack = next(argument for argument in call['arguments'] if argument['location']['kind'] == 'stack')
    assert stack['location'] == {'kind': 'stack', 'offset': 32, 'entry_sp_offset': -8, 'width': 8}
    assert stack['index'] == 4 and stack['candidate']


def test_native_aapcs64_pair_slots_arguments_and_link_register_return():
    snapshot, semantic, flow = _native('fd7bbfa9fd030091400580d200000094e00080d2fd7bc1a8c0035fd6',
                                      arch='arm64', abi='aarch64_aapcs64')
    result = analyze_frame(snapshot, semantic, flow, 'aapcs64')
    slots = {(slot['offset'], slot['width']): slot for slot in result['stack_slots']}
    assert (-16, 8) in slots and (-8, 8) in slots
    assert {access['access'] for access in slots[(-16, 8)]['accesses']} == {'read', 'write'}
    assert any(item['register'] == 'x29' and item['entry_sp_offset'] == -16 for item in result['frame_pointer_relations'])
    assert result['calls'][0]['argument_values'][0] == {'op': 'const', 'value': 42}
    assert result['returns'][0]['return_kind'] == 'link_register'
    assert result['returns'][0]['return_address_size'] == 0
    assert result['returns'][0]['values'][0]['value'] == {'op': 'const', 'value': 7}
    assert result['returns'][0]['entry_sp_offset_before_return'] == 0


def test_unspecified_x86_32_convention_preserves_alternatives():
    snapshot, semantic, flow = _native('b92a000000ba07000000ffd0c3', bits=32)
    result = analyze_frame(snapshot, semantic, flow)
    assert result['abi']['selection'] == 'unspecified'
    assert set(result['abi']['alternatives']) == {'x86_32_cdecl', 'x86_32_stdcall', 'x86_32_fastcall', 'x86_32_thiscall'}
    call = result['calls'][0]
    assert call['arguments'] == []
    alternatives = {item['abi']: item for item in call['alternatives']}
    assert alternatives['x86_32_fastcall']['argument_values'] == [{'op': 'const', 'value': 42}, {'op': 'const', 'value': 7}]
    assert alternatives['x86_32_cdecl']['arguments'] == []
    assert all(slot['classification'] == 'unclassified_stack' for slot in result['stack_slots'] if slot['offset'] >= 0)


def test_unknown_and_looping_stack_effects_do_not_invent_slot_offsets():
    snapshot, semantic, flow = _native('4889c4488b1c24c3', abi='x86_64_sysv')
    result = analyze_frame(snapshot, semantic, flow, 'x86_64_sysv')
    assert not result['stack_slots']
    assert any(item['reason'] == 'entry_sp_relation_unknown' for item in result['unresolved'])
    assert result['returns'][0]['entry_sp_offset_before_return'] is None
    node = dict(id='loop', address='0x1000', context='x86:64:little', flow='jump')
    effect = dict(stack_pointer='rsp', frame_pointer='rbp', flow='jump', stack_delta=-8,
                  assignments=[], clobbers=[], memory=[])
    graph = dict(nodes=[node], entry='loop', arch='x86', bits=64)
    loop_flow = analyze_flow([node], [{'source': 'loop', 'target': 'loop', 'kind': 'branch'}], 'loop', {'loop': effect})
    loop_result = analyze_frame(graph, {'loop': effect}, loop_flow, 'x86_64_sysv')
    assert loop_flow['stable'] and loop_result['stack_states'][0]['before_offset'] is None


def test_budget_and_missing_state_are_explicit_and_inputs_are_bounded():
    snapshot, semantic, flow = _native('9090c3', abi='x86_64_sysv')
    limited = analyze_flow(snapshot['nodes'], snapshot['edges'], snapshot['entry'], semantic, max_steps=1)
    result = analyze_frame(snapshot, semantic, limited, 'x86_64_sysv')
    assert result['budget_exhausted'] and not result['complete']
    assert result['coverage']['analyzed_state_count'] < len(snapshot['nodes'])
    assert any(item['kind'] == 'state' for item in result['unresolved'])
    unavailable = analyze_frame(snapshot, semantic, {'unresolved': [{'kind': 'external_edge', 'source': snapshot['entry'], 'target': 'missing'}]}, 'x86_64_sysv')
    assert not unavailable['complete'] and unavailable['coverage']['analyzed_state_count'] == 0
    assert unavailable['flow_unresolved'][0]['kind'] == 'external_edge'
    with pytest.raises(ValueError, match='unknown ABI'):
        analyze_frame(snapshot, semantic, flow, 'invented_abi')
    with pytest.raises(ValueError, match='does not match'):
        analyze_frame(snapshot, semantic, flow, 'x86_16_cdecl_near')
    with pytest.raises(ValueError, match='at most'):
        analyze_frame({'nodes': [{}] * 100001}, {}, {})
