import pytest

from fdisbull.udc_nes import build


def example():
    variables = {'$x': {'type': 'u8', 'initial': 8},
                 '$ticks': {'type': 'u16', 'initial': 0},
                 '$buttons': {'type': 'u8', 'initial': 0}}
    layout = {'$x': {'address': 0x300, 'width': 8, 'initial': 8},
              '$ticks': {'address': 0x301, 'width': 16, 'initial': 0},
              '$buttons': {'address': 0x303, 'width': 8, 'initial': 0}}
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables, 'resources': {},
               'body': [{'id': 'right', 'op': 'if',
                         'condition': {'op': 'bit_test', 'value': {'var': '$buttons'}, 'bit': 0},
                         'then': [{'id': 'inc', 'op': 'add', 'var': '$x', 'value': 1}], 'else': []},
                        {'id': 'tick', 'op': 'add', 'var': '$ticks', 'value': 1}]}
    return program, layout


def test_mapper0_image_and_vectors():
    program, layout = example()
    result = build(program, layout, display_variable='$x')
    rom = result['rom']; symbols = result['symbols']
    assert rom[:16] == b'NES\x1a\x02\x01' + bytes(10)
    assert len(rom) == 16 + 32768 + 8192
    assert int.from_bytes(rom[16 + 0x7ffc:16 + 0x7ffe], 'little') == symbols['reset'] == 0x8000
    assert int.from_bytes(rom[16 + 0x7ffa:16 + 0x7ffc], 'little') == symbols['nmi']
    assert int.from_bytes(rom[16 + 0x7ffe:16 + 0x8000], 'little') == symbols['irq']
    assert rom[16 + 32768:16 + 32768 + 8] == b'\xff' * 8
    assert symbols['runtime_frame_counter'] == 0x7f0
    assert rom[16 + symbols['logic_tick'] - 0x8000] != 0xff


def test_refuses_unsupported_and_reserved_layout():
    program, layout = example()
    program['body'][0]['then'][0]['op'] = 'execute_story'
    with pytest.raises(ValueError, match='unsupported NES statement'):
        build(program, layout)
    program, layout = example()
    layout['$x']['address'] = 0x7f0
    with pytest.raises(ValueError, match='reserved RAM'):
        build(program, layout)


def test_nes_logic_cycle_budget_refuses_large_u16_program():
    program, layout = example()
    program['body'] = [{'id': f'add{i}', 'op': 'add', 'var': '$ticks', 'value': 1}
                       for i in range(256)]
    with pytest.raises(ValueError, match='logic cycle budget'):
        build(program, layout)


def test_nes_logic_bound_covers_both_conditional_branches():
    program, layout = example()
    result = build(program, layout)
    assert result['symbols']['logic_tick_end'] > result['symbols']['logic_tick']
    assert 0 < result['profile']['logic_cycles_upper_bound'] <= result['profile']['max_logic_cycles'] == 1000
    # The bound covers all emitted branches, whether reachable together or not.
    program['body'][0]['else'] = [{'id': 'other', 'op': 'add', 'var': '$x', 'value': 1}]
    larger = build(program, layout)
    assert larger['profile']['logic_cycles_upper_bound'] > result['profile']['logic_cycles_upper_bound']


def test_cycle_scanner_fails_closed_for_unknown_or_truncated_instructions():
    from fdisbull.udc_nes import _logic_cycles
    with pytest.raises(ValueError, match='unknown NES logic opcode'):
        _logic_cycles(bytes([0xea]))
    with pytest.raises(ValueError, match='truncated NES logic opcode'):
        _logic_cycles(bytes([0xad, 0x00]))
