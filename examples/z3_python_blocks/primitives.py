"""Reusable numeric blocks with explicit source-machine numeric semantics."""
from state_services import Word16Error, _integer, _bounded_integer, _u16, _s16


def require_bool(value):
    if type(value) is not bool:
        raise Word16Error('Conditional requires boolean')
    return value


def bool_not(value): return not require_bool(value)
def bool_any(*values): return any([require_bool(v) for v in values])
def bool_all(*values): return all([require_bool(v) for v in values])


def _pair(a, b):
    _bounded_integer(a)
    _bounded_integer(b)


def calc_add(a, b):
    _pair(a,b)
    return _bounded_integer(a+b)


def calc_sub(a, b):
    _pair(a,b)
    return _bounded_integer(a-b)


def calc_mul(a, b):
    _pair(a,b)
    return _bounded_integer(a*b)


def calc_div(a, b):
    _pair(a,b)
    if b == 0: raise Word16Error('Division by zero')
    q = abs(a)//abs(b)
    return -q if (a < 0) != (b < 0) else q


def calc_mod(a, b): return a-calc_div(a,b)*b

def calc_and(a, b):
    _pair(a,b)
    return a & b


def calc_or(a, b):
    _pair(a,b)
    return a | b


def calc_xor(a, b):
    _pair(a,b)
    return a ^ b


def calc_lt(a, b):
    _pair(a,b)
    return a < b


def calc_gt(a, b):
    _pair(a,b)
    return a > b


def calc_le(a, b):
    _pair(a,b)
    return a <= b


def calc_ge(a, b):
    _pair(a,b)
    return a >= b


def calc_shl(a, b):
    _pair(a,b)
    _integer(b,'shift count',0,63)
    return _bounded_integer(a << b)


def calc_shr(a, b):
    _pair(a,b)
    _integer(b,'shift count',0,63)
    return _bounded_integer(a >> b)


__all__ = ['_u16','_s16','require_bool','bool_not','bool_any','bool_all'] + [n for n in globals() if n.startswith('calc_')]
