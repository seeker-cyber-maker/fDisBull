"""Source-byte Genesis lifting: generated cartridge is the source of truth."""
import hashlib

import pytest

from fdisbull.udc_genesis import build
from fdisbull.udl_genesis import GenesisLiftError, lift


LAYOUT = {'$x': {'address': 0xff0000, 'width': 8, 'initial': 250},
          '$ticks': {'address': 0xff0002, 'width': 16, 'initial': 65534},
          '$copy': {'address': 0xff0004, 'width': 16, 'initial': 0}}


def cartridge():
    program = {'body': [
        {'op': 'add', 'var': '$x', 'value': 1},
        {'op': 'add', 'var': '$ticks', 'value': 1},
        {'op': 'set', 'var': '$copy', 'value': {'var': '$ticks'}},
        {'op': 'subtract', 'var': '$copy', 'value': 1},
        {'op': 'add', 'var': '$copy', 'value': {'var': '$ticks'}},
        {'op': 'subtract', 'var': '$copy', 'value': {'var': '$ticks'}},
    ]}
    program.update({'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
                    'variables': {k: {'type': f"u{v['width']}", 'initial': v['initial']} for k, v in LAYOUT.items()}})
    for i, node in enumerate(program['body']):
        node['id'] = f'n{i}'
    result = build(program, LAYOUT)
    start = result['symbols']['logic_tick']
    length = result['symbols']['logic_tick_end'] - start
    return result['rom'], start, length


def test_lifts_actual_rom_and_binds_hashes():
    rom, start, length = cartridge()
    result = lift(rom, logic_offset=start, logic_length=length, layout=LAYOUT)
    body = result['program']['body']
    assert [(n['op'], n['var'], n['value']) for n in body] == [
        ('add', '$x', 1), ('add', '$ticks', 1), ('set', '$copy', {'var': '$ticks'}),
        ('subtract', '$copy', 1), ('add', '$copy', {'var': '$ticks'}),
        ('subtract', '$copy', {'var': '$ticks'})]
    assert result['provenance']['source_sha256'] == hashlib.sha256(rom).hexdigest()
    assert result['provenance']['logic_sha256'] == hashlib.sha256(rom[start:start+length]).hexdigest()
    # Change a real immediate in the source bytes; the lifted value follows it.
    changed = bytearray(rom)
    changed[start + 9] = 7
    revised = lift(bytes(changed), logic_offset=start, logic_length=length, layout=LAYOUT)
    assert revised['program']['body'][0]['value'] == 7
    assert revised['provenance']['source_sha256'] != result['provenance']['source_sha256']


def test_rejects_unknown_code_uncovered_tail_and_missing_binding():
    rom, start, length = cartridge()
    broken = bytearray(rom)
    broken[start:start+2] = b'\x4e\x71'  # NOP is not an authored operation
    with pytest.raises(GenesisLiftError):
        lift(bytes(broken), logic_offset=start, logic_length=length, layout=LAYOUT)
    with pytest.raises(GenesisLiftError):
        lift(rom, logic_offset=start, logic_length=length+2, layout=LAYOUT)
    with pytest.raises(GenesisLiftError):
        lift(rom, logic_offset=start, logic_length=length, layout={'$x': LAYOUT['$x']})


def test_rejects_control_flow():
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': {'$x': {'type': 'u8', 'initial': 250}}, 'resources': {},
               'body': [{'id': 'a', 'op': 'if', 'condition': {'op': 'eq', 'left': 1, 'right': 1}, 'then': [], 'else': []}]}
    result = build(program, {'$x': LAYOUT['$x']})
    start, end = (result['symbols'][k] for k in ('logic_tick', 'logic_tick_end'))
    with pytest.raises(GenesisLiftError):
        lift(result['rom'], logic_offset=start, logic_length=end-start, layout={'$x': LAYOUT['$x']})
