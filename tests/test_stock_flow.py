"""Public authored fixtures; no original game bytes or runtime files."""
import copy

import pytest

from fdisbull.interaction_il import execute_il
from fdisbull.stock_flow import (PORTS, maintenance_contract, maintenance_module,
                                native16_adapter, decode_state, commit_state)
from fdisbull.udc_layers import register_contract, register_layer, select_layers
from fdisbull.udc_blueprint import execute_module_uil
from fdisbull.project import Project


def layout():
    return dict(records=0x2000, stride=28, population_field=7, stock_field=12,
                produced=0x100, supported=0x110, cost_frame_offset=-72,
                record_frame_offset=6, record_count=128)


@pytest.mark.parametrize('population,cost,supported,stock,produced,expected', [
    (3, 1, 2, 10, 9, 11), (3, 2, 2, 10, 9, 9),
    (-128, 2, -32768, 32767, 32767, 254),
    (127, 1, 32767, -32768, -32768, 32515),
])
def test_fixed_word_behavior_and_signed_byte_widening(population, cost, supported, stock, produced, expected):
    program = maintenance_contract()['behavior']['program']
    state = {k: v['initial'] for k, v in program['variables'].items()}
    state.update({'$' + k: v for k, v in dict(population=population, support_cost=cost,
                 supported=supported, stock=stock, produced=produced).items()})
    result = execute_il(program, state=state)
    assert result['status'] == 'complete'
    assert result['state']['$new_stock'] == expected
    assert all(result['state']['$' + k] == state['$' + k] for k in PORTS)


def test_layout_roundtrip_changes_only_one_stock_word():
    l = layout()
    a = native16_adapter(l, record=127, frame=0x8800)
    data, frame = bytearray(b'\xa5' * 65536), bytearray(b'\x5a' * 65536)
    inputs = dict(stock=-3, produced=13, population=-128, supported=2, support_cost=2)
    for name, binding in a['inputs'].items():
        arena = data if binding['segment'] == 'ds' else frame
        offset = binding.get('offset', 0x8800 + binding.get('displacement', 0))
        size = 1 if PORTS[name] == 'i8' else 2
        arena[offset:offset+size] = inputs[name].to_bytes(size, 'little', signed=True)
    argument = a['initializers'][0]
    frame[argument['offset']:argument['offset']+2] = bytes.fromhex(argument['bytes_hex'])
    assert decode_state(l, data, frame, record=127, frame=0x8800) == inputs
    result = commit_state(l, data, 262, record=127)
    offset = a['outputs']['new_stock']['offset']
    assert result[:offset] == data[:offset] and result[offset+2:] == data[offset+2:]
    assert int.from_bytes(result[offset:offset+2], 'little', signed=True) == 262
    frame[argument['offset']] = 0
    with pytest.raises(ValueError, match='record argument'):
        decode_state(l, data, frame, record=127, frame=0x8800)


@pytest.mark.parametrize('change,record,reason', [
    ({}, -1, 'record'), ({}, 128, 'record'), ({'records': 65530}, 0, 'crosses'),
    ({'population_field': 12}, 0, 'overlap'), ({'cost_frame_offset': 6}, 0, 'overlap'),
    ({'stride': 0}, 0, 'stride'), ({'record_count': True}, 0, 'integers'),
])
def test_invalid_layout_refuses(change, record, reason):
    l = layout(); l.update(change)
    with pytest.raises(ValueError, match=reason):
        native16_adapter(l, record=record)


def test_same_module_and_contract_in_two_distinct_binaries_and_restart(tmp_path):
    ids = []
    for index, byte in enumerate((0x90, 0xc3)):
        source = tmp_path / f'{index}.bin'; source.write_bytes(bytes([byte]) * 32)
        path = tmp_path / f'{index}.fdb'
        with Project.create(path, source, arch='x86', bits=16, base=0x1000) as project:
            c = register_contract(project, maintenance_contract())
            layer = register_layer(project, {'format': 'fdisbull-udl-layer-1',
                'name': 'shared-stock', 'contract': c['id'],
                'implementation': {'backend': 'uil', 'program': c['document']['behavior']['program']}})
            module = maintenance_module(c['id'])
            selected = select_layers(project, 'stock', {'food': layer['id']}, program=module)
            ids.append((c['id'], layer['id'], module))
        with Project(path) as project:
            state = {k: v['initial'] for k, v in module['variables'].items()}
            state.update({'$stock': 10, '$produced': 9, '$population': 3,
                          '$supported': 2, '$support_cost': 2})
            result = execute_module_uil(project, module, selected['id'], state=state)
            assert result['status'] == 'complete' and result['state']['$new_stock'] == 9
            bad = copy.deepcopy(state); bad['$support_cost'] = 3
            refused = execute_module_uil(project, module, selected['id'], state=bad)
            assert refused['status'] == 'refused' and refused['state'] == bad
    assert ids[0] == ids[1]
