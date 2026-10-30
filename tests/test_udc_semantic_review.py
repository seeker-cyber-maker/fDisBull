"""Independent regressions for unambiguous module and native-state bindings."""
import pytest

from fdisbull.project import Project
from fdisbull.udc_blueprint import execute_module_uil
from fdisbull.udc_layers import register_contract, register_layer, select_layers
from fdisbull.udc_native16 import execute_native16, NativeBlockError


def test_module_result_aliases_cannot_change_meaning_under_identical_digest(tmp_path):
    source = tmp_path / 'authored.bin'; source.write_bytes(b'\xc3')
    with Project.create(tmp_path / 'authored.fdb', source, arch='x86', bits=16, base=0x1000) as project:
        reference = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': {
            '$a': {'type': 'u8', 'initial': 0}, '$b': {'type': 'u8', 'initial': 0}},
            'resources': {}, 'body': [{'id': 'a', 'op': 'set', 'var': '$a', 'value': 1},
                                     {'id': 'b', 'op': 'set', 'var': '$b', 'value': 2}]}
        contract = register_contract(project, {'format': 'fdisbull-block-contract-1', 'name': 'pair',
            'inputs': {}, 'outputs': {'a': 'u8', 'b': 'u8'}, 'behavior': {'kind': 'uil', 'program': reference}})
        layer = register_layer(project, {'format': 'fdisbull-udl-layer-1', 'name': 'pair', 'contract': contract['id'],
            'implementation': {'backend': 'uil', 'program': reference}})
        selection = select_layers(project, 'pair', {'pair': layer['id']})
        blueprint = {'format': 'fdisbull-module-uil-1', 'role': 'uil', 'variables': {'$x': {'type': 'u8', 'initial': 0}},
            'resources': {}, 'body': [{'id': 'invoke', 'op': 'invoke', 'binding': 'pair', 'contract': contract['id'],
                                     'inputs': {}, 'outputs': {'a': '$x', 'b': '$x'}}]}
        for outputs in ({'a': '$x', 'b': '$x'}, {'b': '$x', 'a': '$x'}):
            blueprint['body'][0]['outputs'] = outputs
            with pytest.raises(ValueError, match='distinct'):
                execute_module_uil(project, blueprint, selection['id'])


def test_contract_input_variable_aliases_are_refused_at_registration(tmp_path):
    source = tmp_path / 'authored.bin'; source.write_bytes(b'\xc3')
    with Project.create(tmp_path / 'authored.fdb', source, arch='x86', bits=16, base=0x1000) as project:
        reference = {'format': 'fdisbull-il-1', 'role': 'uil',
            'variables': {'$x': {'type': 'u8', 'initial': 0}}, 'resources': {}, 'body': []}
        with pytest.raises(ValueError, match='distinct'):
            register_contract(project, {'format': 'fdisbull-block-contract-1', 'name': 'aliased',
                'inputs': {'a': 'u8', 'b': 'u8'}, 'outputs': {},
                'behavior': {'kind': 'uil', 'program': reference, 'inputs': {'a': '$x', 'b': '$x'}}})


def test_adjacent_memory_ports_form_one_permitted_native_access():
    pytest.importorskip('unicorn')
    result = execute_native16(bytes.fromhex('a10000'), {},
        {'inputs': {'lo': {'segment': 'ds', 'offset': 0}, 'hi': {'segment': 'ds', 'offset': 1}},
         'outputs': {'out': {'register': 'ax'}}},
        {'lo': 3, 'hi': 4}, {'lo': 'u8', 'hi': 'u8'}, {'out': 'u16'})
    assert result['outputs'] == {'out': 0x0403}
    result = execute_native16(bytes.fromhex('c70600000304'), {},
        {'inputs': {}, 'outputs': {'lo': {'segment': 'ds', 'offset': 0}, 'hi': {'segment': 'ds', 'offset': 1}}},
        {}, {}, {'lo': 'u8', 'hi': 'u8'})
    assert result['outputs'] == {'lo': 3, 'hi': 4}


def test_adjacent_read_permission_does_not_grant_write_permission():
    pytest.importorskip('unicorn')
    with pytest.raises(NativeBlockError, match='write'):
        execute_native16(bytes.fromhex('c70600000304'), {},
            {'inputs': {'lo': {'segment': 'ds', 'offset': 0}}, 'outputs': {'hi': {'segment': 'ds', 'offset': 1}}},
            {'lo': 3}, {'lo': 'u8'}, {'hi': 'u8'})


def test_frame_base_must_be_explicit_and_cannot_also_be_scalar_input():
    pytest.importorskip('unicorn')
    adapter = {'inputs': {'index': {'register': 'bx'}, 'value': {'segment': 'ds', 'base': 'bx', 'displacement': 0}},
               'outputs': {'out': {'register': 'ax'}}}
    for registers in ({}, {'bx': 16}):
        adapter['registers'] = registers
        with pytest.raises(NativeBlockError, match='frame base'):
            execute_native16(bytes.fromhex('8a07'), {}, adapter,
                             {'index': 16, 'value': 7}, {'index': 'u16', 'value': 'u8'}, {'out': 'u8'})
    result = execute_native16(bytes.fromhex('8a4600'), {},
        {'registers': {'bp': 32}, 'inputs': {'value': {'segment': 'ss', 'base': 'bp', 'displacement': 0}},
         'outputs': {'out': {'register': 'ax'}}}, {'value': 7}, {'value': 'u8'}, {'out': 'u8'})
    assert result['outputs'] == {'out': 7}


@pytest.mark.parametrize('locations', [
    {'a': {'register': 'ax'}, 'b': {'register': 'ax'}},
    {'a': {'segment': 'ds', 'offset': 16}, 'b': {'segment': 'ds', 'offset': 17}},
])
def test_native_input_carrier_aliases_are_refused(locations):
    pytest.importorskip('unicorn')
    with pytest.raises(NativeBlockError, match='overlap|distinct'):
        execute_native16(b'\x90', {}, {'inputs': locations, 'outputs': {}},
                         {'a': 1, 'b': 2}, {'a': 'u16', 'b': 'u16'}, {})


@pytest.mark.parametrize('port_kind', ['inputs', 'outputs'])
def test_initializers_cannot_override_contract_ports(port_kind):
    pytest.importorskip('unicorn')
    adapter = {'inputs': {}, 'outputs': {}, 'initializers': [{'segment': 'ds', 'offset': 16, 'bytes_hex': '07'}]}
    adapter[port_kind] = {'value': {'segment': 'ds', 'offset': 16}}
    with pytest.raises(NativeBlockError, match='initializer.*overlap'):
        execute_native16(b'\x90', {}, adapter,
                         {'value': 3} if port_kind == 'inputs' else {},
                         {'value': 'u8'} if port_kind == 'inputs' else {},
                         {'value': 'u8'} if port_kind == 'outputs' else {})


def test_initializers_cannot_overlap_each_other_but_may_initialize_scratch():
    pytest.importorskip('unicorn')
    adapter = {'inputs': {}, 'outputs': {'out': {'register': 'ax'}},
               'initializers': [{'segment': 'ds', 'offset': 16, 'bytes_hex': '0304'},
                                {'segment': 'ds', 'offset': 17, 'bytes_hex': '05'}]}
    with pytest.raises(NativeBlockError, match='initializer.*overlap'):
        execute_native16(bytes.fromhex('a11000'), {}, adapter, {}, {}, {'out': 'u16'})
    adapter['initializers'].pop()
    adapter['scratch'] = [{'segment': 'ds', 'offset': 16, 'size': 2}]
    assert execute_native16(bytes.fromhex('a11000'), {}, adapter, {}, {}, {'out': 'u16'})['outputs'] == {'out': 0x0403}


@pytest.mark.parametrize('code', ['b002', 'c606100002'])
def test_native_boolean_outputs_require_canonical_byte_values(code):
    pytest.importorskip('unicorn')
    binding = {'register': 'ax'} if code.startswith('b0') else {'segment': 'ds', 'offset': 16}
    with pytest.raises(NativeBlockError, match='boolean output'):
        execute_native16(bytes.fromhex(code), {}, {'inputs': {}, 'outputs': {'out': binding}}, {}, {}, {'out': 'bool'})
    assert execute_native16(bytes.fromhex('b001'), {}, {'inputs': {}, 'outputs': {'out': {'register': 'ax'}}},
                            {}, {}, {'out': 'bool'})['outputs'] == {'out': True}


def test_native_segment_relocation_is_not_an_arbitrary_memory_constant_patch():
    pytest.importorskip('unicorn')
    with pytest.raises(NativeBlockError, match='MOV immediate'):
        execute_native16(bytes.fromhex('c7061000ffff'), {},
            {'inputs': {}, 'outputs': {'out': {'segment': 'ds', 'offset': 16}},
             'relocations': [{'offset': 4, 'expected_hex': 'ffff', 'region': 'data'}]}, {}, {}, {'out': 'u16'})


def test_distinct_logical_carry_inputs_cannot_share_one_flag_carrier():
    pytest.importorskip('unicorn')
    with pytest.raises(NativeBlockError, match='distinct'):
        execute_native16(b'\x90', {}, {'inputs': {}, 'flag_inputs': {'a': 0, 'b': 0}, 'outputs': {}},
                         {'a': False, 'b': True}, {'a': 'bool', 'b': 'bool'}, {})
