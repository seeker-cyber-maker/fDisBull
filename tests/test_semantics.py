"""Normalized facts from actual bytes; imported code is never executed."""
import json

import pytest

from fdisbull.flowdata import analyze_flow, evaluate_expression
from fdisbull.semantics import instruction_semantics


def lift(raw, bits=64, arch='x86', address=0x1000, cs=None):
    return instruction_semantics(bytes.fromhex(raw), address, arch, bits, cs=cs)


def evaluate(expr, **registers):
    return evaluate_expression(expr, {'registers': {name: {'op': 'const', 'value': value} for name, value in registers.items()}})


def assigned(semantics, name):
    return next(a for a in semantics['assignments'] if a['register'] == name)


@pytest.mark.parametrize('raw,bits,name,value', [
    ('b83412', 16, 'ax', 0x1234), ('b834120000', 32, 'eax', 0x1234),
    ('48b88877665544332211', 64, 'rax', 0x1122334455667788),
    ('b8ffffffff', 64, 'rax', 0xffffffff),
])
def test_mode_sized_mov_constants_and_zero_extending_eax(raw, bits, name, value):
    ir = lift(raw, bits)
    assert ir['valid'] and assigned(ir, name)['value'] == {'op': 'const', 'value': value}
    assert ir['size'] == len(bytes.fromhex(raw)) and ir['flow'] == 'next'
    assert json.loads(json.dumps(ir)) == ir


def test_partial_and_unsupported_writes_kill_aliases_conservatively():
    partial = lift('66b83412')  # MOV AX in 64-bit mode cannot establish full RAX.
    assert not partial['assignments'] and {'rax', 'eax', 'ax'} <= set(partial['clobbers'])
    cpuid = lift('0fa2')
    assert not cpuid['assignments'] and {'rax', 'rbx', 'rcx', 'rdx'} <= set(cpuid['clobbers'])
    assert lift('b0ff', 16)['assignments'] == []


def test_lea_and_arithmetic_are_generic_expressions():
    lea = lift('488d448b10')
    value = assigned(lea, 'rax')['value']
    assert evaluate(value, rbx=0x2000, rcx=3) == {'op': 'const', 'value': 0x201c}
    assert lea['memory'][0]['access'] == 'address_only'
    subtract = lift('4883ec20')
    assert subtract['stack_delta'] == -32
    assert evaluate(assigned(subtract, 'rsp')['value'], rsp=0x100) == {'op': 'const', 'value': 0xe0}
    shift = lift('c1e020')  # SHL EAX,32 has a masked zero shift count.
    assert evaluate(assigned(shift, 'rax')['value'], rax=7) == {'op': 'const', 'value': 7}


def test_dos_memory_has_explicit_segment_and_separate_stack_coordinates():
    data = lift('8b87886f', 16, address=0x10000, cs=0x1000)
    address = data['memory'][0]['address']
    assert evaluate(address, ds=0x4020, bx=8) == {'op': 'const', 'value': 0x47190}
    assert evaluate_expression(address, {'registers': {}})['op'] == 'add'
    stack = lift('8b46fc', 16, address=0x10000, cs=0x1000)
    memory, = stack['memory']
    assert memory['segment_register'] == 'ss' and memory['width'] == 2
    assert evaluate(memory['stack_address'], bp=0x80) == {'op': 'const', 'value': 0x7c}
    assert evaluate(memory['address'], ss=0x4d04, bp=0x80) == {'op': 'const', 'value': 0x4d0bc}
    assert assigned(stack, 'ax')['value']['stack_address'] == memory['stack_address']


@pytest.mark.parametrize('bits,push,pop,sp,width', [(16, '55', '5d', 'sp', 2), (32, '55', '5d', 'esp', 4), (64, '55', '5d', 'rsp', 8)])
def test_push_pop_and_leave_stack_transfers_are_explicit(bits, push, pop, sp, width):
    pushed = lift(push, bits)
    popped = lift(pop, bits)
    assert pushed['stack_delta'] == -width and popped['stack_delta'] == width
    assert pushed['memory'][0]['width'] == width and pushed['memory'][0]['value']['op'] == 'reg'
    assert assigned(popped, {16: 'bp', 32: 'ebp', 64: 'rbp'}[bits])['value']['op'] == 'load'
    leave = lift('c9', bits)
    assert leave['stack_delta'] is None and assigned(leave, sp)['value']['op'] == 'add'


@pytest.mark.parametrize('raw,bits,delta,cleanup,return_width,kind', [
    ('c3', 16, 2, 0, 2, 'near'), ('c20800', 32, 12, 8, 4, 'near'),
    ('c20800', 64, 16, 8, 8, 'near'), ('cb', 16, 4, 0, 4, 'far'),
    ('66cb', 16, 8, 0, 8, 'far'),
])
def test_returns_separate_cleanup_and_native_return_slot(raw, bits, delta, cleanup, return_width, kind):
    ir = lift(raw, bits)
    assert (ir['flow'], ir['stack_delta'], ir['return_pop'], ir['return_address_size'], ir['return_kind']) == (
        'return', delta, cleanup, return_width, kind)


def test_operand_size_prefixed_call_uses_native_stack_effect():
    near = lift('66e801000000', 16, address=0x10000, cs=0x1000)
    far = lift('669a100000000020', 16, address=0x10000, cs=0x1000)
    assert near['stack_delta'] == -4 and near['return_address_size'] == 4
    assert far['stack_delta'] == -8 and far['return_address_size'] == 8 and far['far']
    assert near['target_context'] == 'x86:16:little:cs=1000'


def test_comparison_and_branch_conditions_do_not_parse_operand_text():
    comparison = lift('83f903')['comparison']
    assert comparison['bits'] == 32 and comparison['right'] == {'op': 'const', 'value': 3}
    assert evaluate(comparison['left'], rcx=0x100000002) == {'op': 'const', 'value': 2}
    assert lift('7703')['branch_condition'] == {'predicate': 'gt_u', 'source': 'comparison'}
    test = lift('4885c0')
    assert test['comparison']['left']['op'] == 'and' and test['comparison']['right']['value'] == 0
    assert lift('4883c001')['flags_clobbered'] and lift('4883c001')['comparison'] is None


def test_indirect_near_far_and_signed_load_target_expressions():
    near = lift('ff263000', 16, address=0x10000, cs=0x1000)
    assert near['indirect_target']['op'] == 'add' and near['target_context'].endswith('1000')
    far = lift('ff2e3000', 16, address=0x10000, cs=0x1000)
    assert far['indirect_target']['op'] == 'add'
    assert far['target_context']['template'].endswith('{segment:04x}')
    signed = lift('4863048b')  # MOVSXD RAX,dword [RBX+RCX*4]
    value = assigned(signed, 'rax')['value']
    assert value['op'] == 'load' and value['width'] == 4 and value['signed']
    assert evaluate(value['address'], rbx=0x2000, rcx=3)['value'] == 0x200c
    far32 = lift('66ff2e3000', 16, address=0x10000, cs=0x1000)
    assert far32['target_constraints'][0]['max'] == 0xffff
    assert far32['target_constraints'][0]['expression']['width'] == 4


def test_arm_mov_adrp_add_and_zero_register():
    assert assigned(lift('e00301aa', arch='arm64'), 'x0')['value'] == {'op': 'reg', 'name': 'x1'}
    assert assigned(lift('00000090', arch='arm64'), 'x0')['value'] == {'op': 'const', 'value': 0x1000}
    addition = assigned(lift('00040091', arch='arm64'), 'x0')['value']
    assert evaluate(addition, x0=0x2000)['value'] == 0x2001
    assert assigned(lift('e0031faa', arch='arm64'), 'x0')['value'] == {'op': 'const', 'value': 0}


def test_arm_pair_frame_writeback_uses_two_prestate_slots_and_canonical_registers():
    prologue = lift('fd7bbfa9', arch='arm64')
    assert prologue['stack_delta'] == -16 and len(prologue['memory']) == 2
    assert [m['width'] for m in prologue['memory']] == [8, 8]
    assert [m['value'] for m in prologue['memory']] == [{'op': 'reg', 'name': 'x29'}, {'op': 'reg', 'name': 'x30'}]
    assert [evaluate(m['address'], sp=0x100)['value'] for m in prologue['memory']] == [0xf0, 0xf8]
    frame = lift('fd030091', arch='arm64')
    assert assigned(frame, 'x29')['value'] == {'op': 'reg', 'name': 'sp'}
    epilogue = lift('fd7bc1a8', arch='arm64')
    assert epilogue['stack_delta'] == 16 and {'x29', 'x30', 'sp'} <= set(epilogue['clobbers'])
    assert assigned(epilogue, 'x29')['value']['op'] == assigned(epilogue, 'x30')['value']['op'] == 'load'
    assert assigned(epilogue, 'sp')['value']['args'][1]['value'] == 16


def test_arm_comparisons_do_not_clobber_inputs_and_direct_conditions_are_generic():
    cmp = lift('3f0c00f1', arch='arm64')
    assert cmp['comparison']['left'] == {'op': 'reg', 'name': 'x1'} and 'x1' not in cmp['clobbers']
    assert lift('60000054', arch='arm64')['branch_condition'] == {'predicate': 'eq', 'source': 'comparison'}
    cbz = lift('400000b4', arch='arm64')['branch_condition']
    assert cbz['predicate'] == 'eq' and cbz['left'] == {'op': 'reg', 'name': 'x0'}
    assert lift('00001fd6', arch='arm64')['indirect_target'] == {'op': 'reg', 'name': 'x0'}
    returned = lift('c0035fd6', arch='arm64')
    assert returned['indirect_target'] == {'op': 'reg', 'name': 'x30'} and returned['return_pop'] == 0


def test_arm_signed_load_and_indexed_address_preserve_memory_width():
    signed = lift('2068a0b8', arch='arm64')
    value = assigned(signed, 'x0')['value']
    assert value['signed'] and value['width'] == 4
    indexed = lift('207820f8', arch='arm64')
    assert indexed['memory'][0]['access'] == 'write'
    assert evaluate(indexed['memory'][0]['address'], x0=3, x1=0x2000)['value'] == 0x2018


def test_actual_bytes_flow_across_x86_and_arm_frames():
    for arch, payloads, initial, result_register in [
        ('x86', ['6a07', '58'], {}, 'rax'),
        ('arm64', ['fd7bbfa9', 'fd030091', 'fd7bc1a8'], {'x29': 0x1234, 'x30': 0x5678}, 'x29'),
    ]:
        semantics = {str(i): lift(raw, arch=arch) for i, raw in enumerate(payloads)}
        edges = [{'source': str(i), 'target': str(i+1), 'kind': 'fallthrough'} for i in range(len(payloads)-1)]
        result = analyze_flow(list(semantics), edges, '0', semantics, initial=initial)
        assert result['stable']
        value = result['out_states'][str(len(payloads)-1)]['registers'][result_register]
        assert value == {'op': 'const', 'value': 7 if arch == 'x86' else 0x1234}


def test_dos_stack_segment_write_invalidates_old_logical_stack_storage():
    semantics = {str(i): lift(raw, 16, address=0x10000+i*4, cs=0x1000)
                 for i, raw in enumerate(['6a07', '8ed0', '58'])}  # PUSH7; MOVSS,AX; POPAX
    assert semantics['1']['memory_reset']
    result = analyze_flow(list(semantics), [{'source': '0', 'target': '1'}, {'source': '1', 'target': '2'}],
                          '0', semantics, initial={'ss': 0x1000, 'ax': 0x2000})
    value = result['out_states']['2']['registers'].get('ax')
    assert value is None or value.get('op') != 'const'


def test_invalid_bytes_and_parameters_never_get_mock_transfers():
    for ir in (lift('0f'), lift('ffffffff', arch='arm64'), lift('')):
        assert not ir['valid'] and not ir['assignments'] and not ir['memory'] and ir['size'] == 0
    with pytest.raises(ValueError, match='CS'):
        lift('90', cs=0x1000)
    with pytest.raises(ValueError, match='unsigned'):
        lift('90', address=-1)
