"""Authored source/model fixtures; no game bytes or native-execution claims."""
from copy import deepcopy

import pytest

from fdisbull.uil_catalog import (
    build_catalog, canonical_function, from_asm_instruction, from_memory_uil,
    from_scalar_il, function_semantic_id, import_udl, validate_catalog,
)


def addition():
    return {'variables': [{'type': 'u16'}] * 3, 'constants': [],
            'inputs': [0, 1], 'outputs': [2], 'max_steps': 1024,
            'body': [{'op': 'set', 'dst': 2, 'value':
                      {'op': 'add', 'type': 'u16', 'args': [{'var': 0}, {'var': 1}]}}]}


def run(imported, inputs):
    from fdisbull.common_uil import default_value, required_capabilities
    from fdisbull.uil_runtime import execute_program
    function = imported['function']
    program = {'format': 'fdisbull-common-uil-1', 'imports': [],
               'functions': [function], 'entry': 0, 'capabilities': []}
    program['capabilities'] = sorted(required_capabilities(program))
    def present(value, descriptor):
        return str(value) if descriptor['type'][0:1] in ('u', 'i') and '-array' not in descriptor['type'] else value
    initial = [present(default_value(t), t) for t in function['variables']]
    from fdisbull.common_uil import digest
    presentation = {'format': 'fdisbull-uil-presentation-1',
                    'program_sha256': digest(program), 'resources': [],
                    'functions': [{'initial': initial, 'constants': imported['constants']}]}
    return execute_program(program, presentation, inputs=inputs)


def test_alpha_slots_and_transparent_folds_have_one_semantic_identity():
    a = addition()
    b = deepcopy(a)
    b['inputs'], b['outputs'] = [2, 0], [1]
    b['body'] = [{'op': 'group', 'semantic_id': 'semantic:' + '1' * 64,
                  'body': [{'op': 'set', 'dst': 1, 'value':
                            {'op': 'add', 'type': 'u16', 'args': [{'var': 2}, {'var': 0}]}}]}]
    assert canonical_function(a, []) == canonical_function(b, [])
    assert function_semantic_id(a, []) == function_semantic_id(b, [])
    b['body'][0]['body'][0]['value']['op'] = 'sub'
    assert function_semantic_id(a, []) != function_semantic_id(b, [])


def test_constant_slot_order_values_width_and_budget_are_bound():
    a = addition()
    a['constants'] = [{'type': 'u16'}, {'type': 'u16'}]
    a['body'][0]['value']['args'][1] = {'const': 0}
    b = deepcopy(a)
    b['body'][0]['value']['args'][1] = {'const': 1}
    assert function_semantic_id(a, ['1', '2']) == function_semantic_id(b, ['2', '1'])
    assert function_semantic_id(a, ['1', '2']) != function_semantic_id(a, ['2', '1'])
    b = deepcopy(a); b['max_steps'] -= 1
    assert function_semantic_id(a, ['1', '2']) != function_semantic_id(b, ['1', '2'])


def test_catalog_groups_models_not_language_labels_and_is_hash_checked():
    a = addition()
    catalog = build_catalog([
        {'language': 'common', 'origin_language': 'rust', 'function': a, 'constants': [], 'source': {'revision': 'authored-a'}},
        {'language': 'common', 'origin_language': 'fortran', 'function': a, 'constants': [], 'source': {'revision': 'authored-b'}},
        {'language': 'brainfuck', 'source_text': 'unadmitted input'},
    ])
    assert len(catalog['groups']) == 1
    assert len(catalog['groups'][0]['implementations']) == 2
    assert len(catalog['rejected']) == 1
    assert validate_catalog(catalog) is True
    changed = deepcopy(catalog)
    changed['groups'][0]['implementations'][0]['function']['body'][0]['value']['op'] = 'sub'
    with pytest.raises(ValueError): validate_catalog(changed)
    assert all('declaration' in i['assurance'] for i in catalog['groups'][0]['implementations'])


def test_projected_native_c_and_real_masked_python_increment_group():
    specs = [
        {'language': 'x86-16', 'code': '40', 'flags': 'unobserved'},
        {'language': 'c-u16', 'source_text': 'ax += 1;', 'inputs': ['ax'], 'outputs': ['ax']},
        {'language': 'python-u16', 'source_text': 'ax = (ax + 1) & 65535', 'inputs': ['ax'], 'outputs': ['ax']},
    ]
    catalog = build_catalog(specs)
    assert catalog['rejected'] == []
    assert len(catalog['groups']) == 1
    assert len(catalog['groups'][0]['implementations']) == 3
    for spec in specs:
        item = import_udl(spec)
        assert run(item, [65535])['outputs'] == [0]
    with pytest.raises(ValueError):
        import_udl({'language': 'python-u16', 'source_text': 'ax += 1', 'inputs': ['ax'], 'outputs': ['ax']})


@pytest.mark.parametrize('code,inputs,expected', [
    ('40', [65535, True], [0, True, True, True, True, False, False]),
    ('050100', [65535], [0, True, True, True, True, False, False]),
    ('150000', [65535, True], [0, True, True, True, True, False, False]),
    ('050100', [32767], [32768, False, True, True, False, True, True]),
    ('0401', [255], [0, True, True, True, True, False, False]),
])
def test_actual_decoder_arithmetic_flag_vectors(code, inputs, expected):
    item = from_asm_instruction(bytes.fromhex(code))
    assert run(item, inputs)['outputs'] == expected
    assert item['source']['outputs'][1:] == ['cf', 'pf', 'af', 'zf', 'sf', 'of']
    assert item['source']['sha256']


def test_adc_carry_is_never_silently_discarded_even_for_projection():
    add = from_asm_instruction(bytes.fromhex('050100'), flags='unobserved')
    adc = from_asm_instruction(bytes.fromhex('150100'), flags='unobserved')
    assert function_semantic_id(add['function'], add['constants']) != function_semantic_id(adc['function'], adc['constants'])
    assert run(adc, [5, False])['outputs'] == [6]
    assert run(adc, [5, True])['outputs'] == [7]


@pytest.mark.parametrize('code', ['90', 'cd21', '4005', '4040', '0100', 'f040'])
def test_native_unknown_memory_prefix_and_multiple_instructions_refuse(code):
    with pytest.raises(ValueError): from_asm_instruction(bytes.fromhex(code))


@pytest.mark.parametrize('bits,code,value', [(16, '89d8', 65535), (32, '89d8', 4294967295),
                                          (64, '4889d8', 18446744073709551615)])
def test_native_mov_preserves_all_declared_flags_and_copy_value(bits, code, value):
    item = from_asm_instruction(bytes.fromhex(code), bits=bits)
    flags = [True, False, True, False, True, False]
    result = run(item, [value, *flags])
    assert result['outputs'] == [value, *flags]
    assert result['steps'] == 1
    assert item['source']['mnemonic'] == 'mov'
    assert item['source']['inputs'][0] == {16: 'bx', 32: 'ebx', 64: 'rbx'}[bits]


def test_native_mov_memory_and_immediate_are_not_guessed():
    for code in ('8b00', 'b80100', '0f20c0', '8cd8'):
        with pytest.raises(ValueError):
            from_asm_instruction(bytes.fromhex(code))


@pytest.mark.parametrize('bits,code', [(16, '89d8'), (32, '89d8'), (64, '4889d8')])
def test_mov_model_agrees_with_actual_instruction_execution(bits, code):
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as r
    mode = {16: unicorn.UC_MODE_16, 32: unicorn.UC_MODE_32, 64: unicorn.UC_MODE_64}[bits]
    dst = {16: r.UC_X86_REG_AX, 32: r.UC_X86_REG_EAX, 64: r.UC_X86_REG_RAX}[bits]
    src = {16: r.UC_X86_REG_BX, 32: r.UC_X86_REG_EBX, 64: r.UC_X86_REG_RBX}[bits]
    positions = [0, 2, 4, 6, 7, 11]
    model = from_asm_instruction(bytes.fromhex(code), bits=bits)
    for value, flags in ((0, [False] * 6), ((1 << bits) - 1, [True] * 6)):
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, mode)
        cpu.mem_map(0x1000, 4096); cpu.mem_write(0x1000, bytes.fromhex(code))
        cpu.reg_write(src, value)
        cpu.reg_write(r.UC_X86_REG_EFLAGS, 0x202 | sum(int(f) << p for f, p in zip(flags, positions)))
        cpu.emu_start(0x1000, 0x1000 + len(bytes.fromhex(code)), count=1)
        status = cpu.reg_read(r.UC_X86_REG_EFLAGS)
        observed = [cpu.reg_read(dst), *[bool(status & (1 << p)) for p in positions]]
        assert run(model, [value, *flags])['outputs'] == observed


def test_scalar_adapter_preserves_nonzero_defaults_and_checked_assignment():
    legacy = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
              'variables': {'$x': {'type': 'u32', 'initial': 9}, '$y': {'type': 'u8', 'initial': 2}},
              'body': [{'id': 'assign', 'op': 'set', 'var': '$y', 'value': {'var': '$x'}}]}
    item = from_scalar_il(legacy, ['$x'], ['$y'])
    assert run(item, [255])['outputs'] == [255]
    assert run(item, [256])['status'] == 'refused'
    initial = deepcopy(legacy); initial['body'] = []
    assert run(from_scalar_il(initial, [], ['$y']), [])['outputs'] == [2]


def test_memory_adapter_keeps_u32_comparisons_shifts_and_arena_ownership():
    legacy = {'format': 'fdisbull-memory-uil-1', 'role': 'uil',
              'memory': {'words': 3}, 'variables': {}, 'functions': {'step': {
                  'max_steps': 100, 'body': [
                      {'op': 'store', 'index': 1, 'value': {'op': 'shl', 'left': {'load': 0}, 'right': 33}},
                      {'op': 'store', 'index': 2, 'value': {'op': 'eq', 'left': {'load': 1}, 'right': 2}},
                  ]}}}
    item = from_memory_uil(legacy, 'step')
    words = [1, 0, 0]
    assert run(item, [words])['outputs'] == [[1, 2, 1]]
    assert words == [1, 0, 0]
    bad = deepcopy(legacy)
    bad['functions']['unused'] = {'max_steps': 10, 'body': [{'op': 'mystery'}]}
    with pytest.raises(ValueError): from_memory_uil(bad, 'step')


def test_catalog_rejects_open_function_calls_raw_source_metadata_and_bad_constants():
    a = addition(); a['body'] = [{'op': 'call', 'function': 0, 'inputs': [], 'outputs': []}]
    with pytest.raises(ValueError): function_semantic_id(a, [])
    with pytest.raises(ValueError):
        import_udl({'language': 'common', 'function': addition(), 'constants': [], 'source': {'code_hex': '40'}})
    a = addition(); a['constants'] = [{'type': 'u64'}]
    with pytest.raises(ValueError): function_semantic_id(a, ['01'])


@pytest.mark.parametrize('code,bits,width', [('10c8', 16, 8), ('11c8', 16, 16), ('11c8', 32, 32), ('4811c8', 64, 64)])
def test_register_adc_flags_match_independent_integer_arithmetic(code, bits, width):
    item = from_asm_instruction(bytes.fromhex(code), bits=bits)
    maximum, sign = (1 << width) - 1, 1 << (width - 1)
    values = (0, 1, 15, sign - 1, sign, maximum)
    for a, b in zip(values, reversed(values)):
        for carry in (False, True):
            total = a + b + int(carry); result = total & maximum
            signed_total = (a - (1 << width) if a & sign else a) + (b - (1 << width) if b & sign else b) + int(carry)
            expected = [result, total > maximum, (result & 255).bit_count() % 2 == 0,
                        (a & 15) + (b & 15) + int(carry) > 15, result == 0,
                        bool(result & sign), not -sign <= signed_total < sign]
            assert run(item, [a, b, carry])['outputs'] == expected


def test_inc_preserves_clear_carry_and_add_sign_extended_immediate():
    inc = from_asm_instruction(b'\x40')
    assert run(inc, [65535, False])['outputs'][1] is False
    subtract_one_via_add = from_asm_instruction(bytes.fromhex('83c0ff'))
    assert run(subtract_one_via_add, [1])['outputs'] == [0, True, True, True, True, False, False]


def test_source_evidence_and_inputs_immutable_unknowns_retain_only_metadata():
    source = {'language': 'c-u16', 'source_text': 'ax += 1;', 'inputs': ['ax'], 'outputs': ['ax'],
              'source': {'source_map': {'line': 3}, 'evidence': {'label': 'authored'}}}
    before = deepcopy(source)
    catalog = build_catalog([source, {'language': 'unsupported', 'source_text': 'SECRET_RAW_SOURCE'}])
    assert source == before
    impl = catalog['groups'][0]['implementations'][0]
    assert impl['source']['source_map'] == {'line': 3}
    assert impl['source']['evidence'] == {'label': 'authored'}
    import json
    assert 'SECRET_RAW_SOURCE' not in json.dumps(catalog)
    assert catalog['rejected'][0]['source']['input_sha256']
    legacy = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {}, 'variables': {}, 'body': [],
              'evidence': {'source': {'sha256': 'a' * 64, 'range': [1, 2]}}}
    assert from_scalar_il(legacy, [], [])['source']['evidence'] == legacy['evidence']


@pytest.mark.parametrize('mutation', ['group-id', 'impl-id', 'constant', 'effects', 'source', 'duplicate'])
def test_catalog_corruption_is_refused(mutation):
    catalog = build_catalog([{'language': 'c-u16', 'source_text': 'ax += 1;', 'inputs': ['ax'], 'outputs': ['ax']}])
    group = catalog['groups'][0]; impl = group['implementations'][0]
    if mutation == 'group-id': group['semantic_id'] = 'semantic:' + '0' * 64
    elif mutation == 'impl-id': impl['id'] = 'implementation:' + '0' * 64
    elif mutation == 'constant': impl['constants'][0] = '2'
    elif mutation == 'effects': group['effects'] = ['sound.play']
    elif mutation == 'source': impl['source']['sha256'] = '0' * 64
    else: group['implementations'].append(deepcopy(impl))
    with pytest.raises(ValueError): validate_catalog(catalog)


def test_catalog_preserves_unused_constant_validation_and_non_source_language_refusal():
    function = addition()
    with pytest.raises(ValueError):
        import_udl({'language': 'common', 'function': function, 'constants': ['1']})
    rejected = build_catalog([{'language': [], 'source_text': 'bad'}])
    assert rejected['groups'] == [] and rejected['rejected'][0]['language'] == 'unknown'
    with pytest.raises(ValueError):
        import_udl({'language': 'common', 'function': function, 'constants': [], 'source': {'offset': 1.5}})
