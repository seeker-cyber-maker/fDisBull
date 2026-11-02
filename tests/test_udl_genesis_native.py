"""Authored generic native vectors; no original game bytes are retained here."""
import copy
import hashlib

import pytest

from fdisbull.console_udc import compile_console_rom
from fdisbull.interaction_il import execute_il
from fdisbull.udl_genesis import GenesisLiftError, lift_native


BASE = 0xff1200
LAYOUT = {'$count': {'address': BASE + 6, 'width': 8, 'initial': 3},
          '$active': {'address': BASE + 2, 'width': 8, 'initial': 9}}


def source(code):
    return bytes(0x200) + bytes.fromhex(code)


def lift(code, layout=LAYOUT, registers=None):
    rom = source(code)
    return lift_native(rom, logic_offset=0x200, logic_length=len(rom)-0x200,
                       layout=layout, address_registers={'A2': BASE} if registers is None else registers)


def test_native_countdown_and_conditional_clear():
    # Authored A2+6 / A2+2 vector; neither address nor bytes are a game excerpt.
    code = '532a00066604422a00024e75'
    result = lift(code)
    program = result['program']
    state = None
    for expected in (2, 1, 0, 255, 254):
        executed = execute_il(program, state)
        assert executed['complete']
        state = executed['state']
        assert state['$count'] == expected
        assert state['$active'] == (9 if expected in (2, 1) else 0)
    for target in ('nes', 'genesis'):
        assert compile_console_rom(program, target=target)['manifest']['target'] == target
    p = result['provenance']
    assert p['profile'] == 'm68000-native-memory-1'
    assert p['source_sha256'] == hashlib.sha256(source(code)).hexdigest()
    assert p['logic_sha256'] == hashlib.sha256(bytes.fromhex(code)).hexdigest()
    assert p['address_registers'] == {'A2': BASE}
    # Native bytes, rather than an externally supplied UIL recipe, choose step.
    changed = lift('552a00066604422a00024e75')
    assert execute_il(changed['program'])['state']['$count'] == 1


def test_native_word_test_zero_branch_and_short_absolute_sign_extension():
    layout = {'$word': {'address': 0xff9000, 'width': 16, 'initial': 0},
              '$flag': {'address': 0xff9002, 'width': 8, 'initial': 3}}
    # tst.w $9000.w; beq.s skip; clr.b $9002.w; addq.w #8,$9000.w; rts
    code = '4a789000670442389002507890004e75'
    program = lift(code, layout=layout, registers={})['program']
    assert execute_il(program)['state'] == {'$word': 8, '$flag': 3}
    assert execute_il(program, {'$word': 65535, '$flag': 3})['state'] == {'$word': 7, '$flag': 0}


def test_native_absolute_long_and_word_branch():
    layout = {'$word': {'address': BASE, 'width': 16, 'initial': 1}}
    # subq.w #1,$ff1200.l; bne.w end; addq.w #2,$ff1200.l; rts
    code = '537900ff120066000008547900ff12004e75'
    program = lift(code, layout=layout, registers={})['program']
    assert execute_il(program)['state'] == {'$word': 2}
    assert execute_il(program, {'$word': 0})['state'] == {'$word': 65535}


@pytest.mark.parametrize('code', [
    '66024e754e75',  # incoming CCR is undeclared
    '532a000666fa4e75',  # backward branch/loop
    '532a00066602422a00024e75',  # branch into extension word
    '532a000666204e75',  # branch leaves function
    '532a0006',  # no return
    '4e714e75',  # unsupported opcode
    '532a000660024e754e75',  # unreachable instruction in exact range
    '531a4e75',  # postincrement register side effect
    '53aa00064e75',  # unsupported long width
])
def test_native_refuses_unmodeled_code(code):
    with pytest.raises(GenesisLiftError):
        lift(code)


def test_native_refuses_unbound_register_memory_and_overlapping_layout():
    code = '532a00064e75'
    with pytest.raises(GenesisLiftError, match='unbound address register'):
        lift(code, registers={})
    with pytest.raises(GenesisLiftError, match='unbound native RAM'):
        lift('532a00074e75')
    bad = copy.deepcopy(LAYOUT)
    bad['$overlap'] = dict(bad['$count'])
    with pytest.raises(GenesisLiftError, match='overlapping'):
        lift(code, layout=bad)


def test_native_refuses_shape_register_and_range_budgets():
    code = '532a00064e75'
    for registers in ({'A7': BASE}, {'A0': True}, {'A2': BASE, 'a2': BASE}):
        with pytest.raises(GenesisLiftError, match='register'):
            lift(code, registers=registers)
    with pytest.raises(GenesisLiftError, match='instruction budget'):
        lift('532a0006' * 32 + '4e75')
    with pytest.raises(GenesisLiftError, match='range'):
        lift_native(source(code), logic_offset=0x201, logic_length=8,
                    layout=LAYOUT, address_registers={})
