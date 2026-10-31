"""Shared bounded semantic probes; expected states are authored independently.

The emulator qualification consumes these programs and compares RAM at each
completed logic tick. These tests alone only establish that emitters accept
and package the probes, not that native execution matches the states.
"""
import copy

import pytest

from fdisbull import udc_genesis, udc_nes
from fdisbull.interaction_il import ILInvalid, execute_il, validate_il
from fdisbull.console_udc import compile_console_rom


def semantic_cases():
    return [
        {
            'name': 'alias_wrap',
            'variables': {'$a': {'type': 'u8', 'initial': 255},
                          '$b': {'type': 'u16', 'initial': 0x80ff},
                          '$c': {'type': 'u16', 'initial': 1},
                          '$d': {'type': 'u16', 'initial': 0x100},
                          '$e': {'type': 'u16', 'initial': 0xff}},
            'body': [
                {'id': 'a', 'op': 'add', 'var': '$a', 'value': {'var': '$a'}},
                {'id': 'b', 'op': 'add', 'var': '$b', 'value': {'var': '$b'}},
                {'id': 'c', 'op': 'subtract', 'var': '$c', 'value': 2},
                {'id': 'd', 'op': 'subtract', 'var': '$d', 'value': {'var': '$d'}},
                {'id': 'e', 'op': 'add', 'var': '$e', 'value': 2},
            ],
            'expected': [
                {'$a': 254, '$b': 0x01fe, '$c': 0xffff, '$d': 0, '$e': 0x101},
                {'$a': 252, '$b': 0x03fc, '$c': 0xfffd, '$d': 0, '$e': 0x103},
                {'$a': 248, '$b': 0x07f8, '$c': 0xfffb, '$d': 0, '$e': 0x105},
            ],
        },
        {
            'name': 'nested_conditions',
            'variables': {'$x': {'type': 'u8', 'initial': 8},
                          '$word': {'type': 'u16', 'initial': 0x100}},
            'body': [
                {'id': 'outer', 'op': 'if', 'condition': {'op': 'and', 'conditions': [
                    {'op': 'not', 'condition': {'op': 'eq', 'left': {'var': '$x'}, 'right': 9}},
                    {'op': 'bit_test', 'value': {'var': '$word'}, 'bit': 8},
                    {'op': 'eq', 'left': 0x100, 'right': 0x100},
                ]}, 'then': [{'id': 'yes', 'op': 'set', 'var': '$x', 'value': 9}],
                    'else': [{'id': 'no', 'op': 'subtract', 'var': '$x', 'value': 1}]},
                {'id': 'w', 'op': 'subtract', 'var': '$word', 'value': 1},
            ],
            'expected': [
                {'$x': 9, '$word': 0xff},
                {'$x': 8, '$word': 0xfe},
                {'$x': 7, '$word': 0xfd},
            ],
        },
        {
            'name': 'literal_high_bit',
            'variables': {'$x': {'type': 'u8', 'initial': 0},
                          '$word': {'type': 'u16', 'initial': 0x100}},
            'body': [
                {'id': 'prime', 'op': 'set', 'var': '$word', 'value': 0x100},
                {'id': 'test', 'op': 'if', 'condition': {'op': 'bit_test', 'value': 0, 'bit': 8},
                 'then': [{'id': 'bad', 'op': 'set', 'var': '$x', 'value': 1}],
                 'else': [{'id': 'good', 'op': 'set', 'var': '$x', 'value': 2}]},
            ],
            'expected': [{'$x': 2, '$word': 0x100}] * 3,
        },
    ]


def program(case):
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': case['variables'],
            'resources': {}, 'body': case['body']}


def layout_for(case, start):
    layout = {}
    for name, data in case['variables'].items():
        width = int(data['type'][1:])
        if width == 16 and start & 1 and start >= 0xff0000:
            start += 1
        layout[name] = {'address': start, 'width': width, 'initial': data['initial']}
        start += width // 8
    return layout


def test_both_emitters_package_semantic_cases():
    for case in semantic_cases():
        for backend, start in ((udc_nes, 0x300), (udc_genesis, 0xff0000)):
            result = backend.build(program(case), layout_for(case, start))
            assert isinstance(result['rom'], bytes)
            assert 'logic_tick' in result['symbols']


def test_cases_match_uil_reference_and_hand_checked_states():
    for case in semantic_cases():
        doc = program(case)
        assert validate_il(doc)
        state = None
        for expected in case['expected']:
            result = execute_il(doc, state)
            assert result['complete']
            assert result['state'] == expected
            state = result['state']


def test_sub_alias_is_refused():
    case = semantic_cases()[0]
    doc = copy.deepcopy(program(case))
    doc['body'][2]['op'] = 'sub'
    with pytest.raises(ILInvalid):
        validate_il(doc)
    with pytest.raises(ValueError, match='unsupported NES statement'):
        udc_nes.build(doc, layout_for(case, 0x300))


def test_shared_compiler_accepts_all_validated_cases():
    for case in semantic_cases():
        for target in ('nes', 'genesis'):
            result = compile_console_rom(program(case), target=target)
            assert result['manifest']['target'] == target
            assert result['manifest']['executed'] is False
