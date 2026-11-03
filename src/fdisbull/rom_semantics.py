"""Narrow authored SH-2 register experiment; not a general C or SH-2 lifter."""
import hashlib
import re

from .interaction_il import validate_il
from .proofs import arithmetic_model, check_equivalence

_C11_KEYWORDS = frozenset('auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local'.split())

_SCOPE = ('r0 at straight-line arithmetic boundary from r4; user-supplied unsigned 32-bit '
          'ABI binding; return control, other registers, flags, memory, timing, and game behavior excluded')


def _document(n):
    doc = {'format': 'fdisbull-il-1', 'role': 'uil',
           'variables': {'$r0': {'type': 'u32', 'initial': 0}, '$r4': {'type': 'u32', 'initial': 0}},
           'resources': {}, 'body': [
               {'id': 'copy', 'op': 'set', 'var': '$r0', 'value': {'var': '$r4'}},
               {'id': 'add', 'op': 'add', 'var': '$r0', 'value': n}]}
    validate_il(doc)
    return doc


def _result(kind, source, n):
    return {'source_kind': kind, 'sha256': hashlib.sha256(source).hexdigest(),
            'scope': _SCOPE, 'source': source.hex() if kind == 'sh2-authored-block' else source.decode('utf-8'), 'uil': _document(n)}


def lift_sh2(code):
    """Recognize exactly MOV R4,R0; ADD #imm,R0; RTS; NOP, imm 0..127."""
    if not isinstance(code, bytes) or len(code) != 8 or code[:3] != bytes.fromhex('604370') or code[3] > 127 or code[4:] != bytes.fromhex('000b0009'):
        raise ValueError('unsupported SH-2 block')
    return _result('sh2-authored-block', code, code[3])


def lift_ghidra_c(source):
    """Require exact unsigned prototype and single return; uint must mean uint32_t."""
    if not isinstance(source, str) or len(source) > 4096:
        raise ValueError('invalid C source')
    m = re.fullmatch(r'\s*uint\s+authored\s*\(\s*uint\s+([A-Za-z_]\w*)\s*\)\s*\{\s*return\s+\1\s*\+\s*(0|[1-9][0-9]*)\s*;\s*\}\s*', source, re.ASCII)
    if (not m or m.group(1) in _C11_KEYWORDS or m.group(1).startswith('_')
            or '__' in m.group(1) or int(m.group(2)) > 127):
        raise ValueError('unsupported or untyped Ghidra C')
    return _result('ghidra-c-uint32-assumed', source.encode(), int(m.group(2)))


def lift_saturn_cpp(source):
    """Recognize the complete generated wrapper; c.r elements must be uint32_t."""
    if not isinstance(source, str) or len(source) > 4096:
        raise ValueError('invalid C++ source')
    pattern = (r'\s*#include "p_typed_funcs.h"\s*namespace p_typed\s*\{\s*'
               r'void f_06010000\(SH2Context& c\)\s*\{\s*ran\[0\] = 1;\s*'
               r'c\.r\[0\] = c\.r\[4\];\s*// 06010000 mov r4,r0\s*'
               r'c\.r\[0\] \+= (0|[1-9][0-9]*);\s*// 06010002 add #[0-9]+,r0\s*'
               r'\{ const uint32_t x = c\.pr; c\.pc = x; return; \}\s*// 06010004 rts ; nop\s*'
               r'\}\s*\}\s*// namespace p_typed\s*')
    m = re.fullmatch(pattern, source, re.ASCII)
    if not m or int(m.group(1)) > 127:
        raise ValueError('unsupported Saturn C++ wrapper')
    return _result('saturn-cpp-uint32-assumed', source.encode(), int(m.group(1)))


def compare(left, right):
    """Compare validated documents from these lifts, not untrusted claimed source text."""
    def expr(lift):
        if not isinstance(lift, dict):
            raise ValueError('invalid lift')
        try:
            kind, source = lift['source_kind'], lift['source']
            if kind == 'sh2-authored-block':
                rebuilt = lift_sh2(bytes.fromhex(source))
            elif kind == 'ghidra-c-uint32-assumed':
                rebuilt = lift_ghidra_c(source)
            elif kind == 'saturn-cpp-uint32-assumed':
                rebuilt = lift_saturn_cpp(source)
            else:
                raise ValueError('unknown source kind')
            if lift != rebuilt:
                raise ValueError('lift differs from rebuilt source')
            n = rebuilt['uil']['body'][1]['value']
        except (KeyError, TypeError, IndexError, UnicodeError) as exc:
            raise ValueError('invalid lift') from exc
        return {'op': 'add', 'args': [{'var': 'r4'}, {'const': n, 'width': 32}]}
    return check_equivalence(arithmetic_model({'r4': 32}, expr(left), expr(right), scope=_SCOPE))
