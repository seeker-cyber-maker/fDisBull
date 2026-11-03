"""Checks of native Genesis cartridge structure and emitted 68000 code."""
import struct

import pytest

from fdisbull.udc_genesis import build, _Assembler


def test_cartridge_vectors_checksum_and_native_logic():
    capstone = pytest.importorskip('capstone')
    program = {'body': [
        {'op': 'if', 'condition': {'op': 'bit_test', 'value': {'var': '$buttons'}, 'bit': 0},
         'then': [{'op': 'add', 'var': '$x', 'value': 1}], 'else': []},
        {'op': 'add', 'var': '$ticks', 'value': 1},
    ]}
    layout = {'$x': {'address': 0xff0000, 'width': 8, 'initial': 8},
              '$buttons': {'address': 0xff0001, 'width': 8, 'initial': 0},
              '$ticks': {'address': 0xff0002, 'width': 16, 'initial': 0}}
    program.update({'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
                    'variables': {k: {'type': f"u{v['width']}", 'initial': v['initial']} for k, v in layout.items()}})
    program['body'][0]['id'] = 'right'
    program['body'][0]['then'][0]['id'] = 'inc'
    program['body'][1]['id'] = 'tick'
    result = build(program, layout, display_variable='$x')
    rom = result['rom']
    stack, reset = struct.unpack_from('>II', rom)
    assert stack == 0xfffffc and reset == result['symbols']['reset'] == 0x200
    assert rom[0x100:0x110] == b'SEGA MEGA DRIVE '
    assert struct.unpack_from('>I', rom, 0x1a4)[0] == len(rom) - 1
    assert struct.unpack_from('>H', rom, 0x18e)[0] == sum(
        struct.unpack_from('>H', rom, i)[0] for i in range(0x200, len(rom), 2)) & 0xffff
    md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)
    start = result['symbols']['logic_tick']
    instructions = list(md.disasm(rom[start:start + 60], start))
    assert any(i.mnemonic == 'btst.b' for i in instructions)
    assert any(i.mnemonic == 'add.b' for i in instructions)
    assert any(i.mnemonic == 'add.w' for i in instructions)
    assert any(i.mnemonic == 'rts' for i in instructions)
    assert result['symbols']['runtime_frame_counter'] == 0xfffff0


def test_invalid_public_inputs_are_refused():
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
               'variables': {'$x': {'type': 'u16', 'initial': 0}}, 'body': []}
    with pytest.raises(ValueError):
        build(program, {'$x': {'address': 0xff0001, 'width': 16, 'initial': 0}})
    with pytest.raises(ValueError):
        build(program, {'$x': {'address': 0xff0000, 'width': 16, 'initial': 0}}, display_variable='$x')
    with pytest.raises(ValueError):
        build({**program, 'resources': {'x': {'kind': 'text', 'text': 'x'}}},
              {'$x': {'address': 0xff0000, 'width': 16, 'initial': 0}})


def test_long_conditional_branch_fails_closed():
    a = _Assembler()
    a.branch(0x6000, 'end')
    a.data.extend(b'\0' * 40000)
    a.label('end')
    with pytest.raises(ValueError, match='branch exceeds'):
        a.resolve()


def test_literal_bit_test_loads_full_word():
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
               'variables': {'$x': {'type': 'u8', 'initial': 0}},
               'body': [{'id': 'cond', 'op': 'if', 'condition': {'op': 'bit_test', 'value': 1, 'bit': 8}, 'then': [], 'else': []}]}
    result = build(program, {'$x': {'address': 0xff0000, 'width': 8, 'initial': 0}})
    start = result['symbols']['logic_tick']
    assert result['rom'][start:start + 4] == bytes.fromhex('303c0001')


def test_genesis_logic_cycle_budget():
    layout = {'$x': {'address': 0xff0000, 'width': 16, 'initial': 0}}
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
               'variables': {'$x': {'type': 'u16', 'initial': 0}},
               'body': [{'id': f'n{i}', 'op': 'add', 'var': '$x', 'value': 1}
                        for i in range(256)]}
    with pytest.raises(ValueError, match='6000-cycle'):
        build(program, layout)
    program['body'] = program['body'][:1]
    profile = build(program, layout)['profile']
    assert profile['logic_cycles_upper_bound'] == 5 * 64
    assert profile['max_logic_cycles'] == 6000
