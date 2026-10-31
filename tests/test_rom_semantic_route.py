import pytest
from fdisbull.interaction_il import execute_il
from fdisbull import proofs
from fdisbull.rom_semantics import lift_sh2, lift_ghidra_c, lift_saturn_cpp, compare

C = 'uint authored(uint value) { return value + 1; }'
CPP = '''#include "p_typed_funcs.h"
namespace p_typed {
void f_06010000(SH2Context& c) {
ran[0] = 1;
c.r[0] = c.r[4]; // 06010000 mov r4,r0
c.r[0] += 1; // 06010002 add #1,r0
{ const uint32_t x = c.pr; c.pc = x; return; } // 06010004 rts ; nop
}
} // namespace p_typed
'''

def test_real_shapes_and_wrap():
    a = lift_sh2(bytes.fromhex('60437001000b0009'))
    b, c = lift_ghidra_c(C), lift_saturn_cpp(CPP)
    for lift in (a, b, c):
        result = execute_il(lift['uil'], {'$r0': 12, '$r4': 0xffffffff})
        assert result['state']['$r0'] == 0
    expected = 'equivalent_under_assumptions' if proofs._load_z3() else 'unavailable'
    mutant = 'counterexample' if proofs._load_z3() else 'unavailable'
    assert compare(a, b)['status'] == expected
    assert compare(a, c)['status'] == expected
    assert compare(a, lift_ghidra_c(C.replace('+ 1', '+ 2')))['status'] == mutant

@pytest.mark.parametrize('source', [C.replace('uint', 'int'), C.replace('return', '*p = 0; return'), C.replace('+ 1', '+ 1; goto fail')])
def test_c_refuses_unsupported(source):
    with pytest.raises(ValueError): lift_ghidra_c(source)

def test_sh2_and_cpp_fail_closed():
    with pytest.raises(ValueError): lift_sh2(bytes.fromhex('604370018b000009'))
    with pytest.raises(ValueError): lift_saturn_cpp(CPP.replace('ran[0] = 1;', 'ran[0] = 1; c.r[1] = 4;'))

def test_forged_and_malformed_lifts_are_refused():
    from copy import deepcopy
    original = lift_ghidra_c(C)
    for key, value in [('sha256', '0' * 64), ('source', C.replace('+ 1', '+ 2')), ('uil', {}), ('source_kind', 'other')]:
        forged = deepcopy(original)
        forged[key] = value
        with pytest.raises(ValueError):
            compare(original, forged)

@pytest.mark.parametrize('name', ['if', 'struct', '_Atomic', '__reserved', 'a__reserved'])
def test_c_rejects_reserved_identifiers(name):
    with pytest.raises(ValueError):
        lift_ghidra_c(f'uint authored(uint {name}) {{ return {name} + 1; }}')
