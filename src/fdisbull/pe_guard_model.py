"""Pure arithmetic FLAGS and direct Jcc predicates for bounded PE analysis."""
from iced_x86 import ConditionCode

FLAG_BITS = {'cf': 0, 'pf': 2, 'af': 4, 'zf': 6, 'sf': 7, 'of': 11}
ARITHMETIC_MASK = sum(1 << bit for bit in FLAG_BITS.values())
READS = {
    'o': ('of',), 'no': ('of',), 'b': ('cf',), 'ae': ('cf',),
    'e': ('zf',), 'ne': ('zf',), 'be': ('cf', 'zf'), 'a': ('cf', 'zf'),
    's': ('sf',), 'ns': ('sf',), 'p': ('pf',), 'np': ('pf',),
    'l': ('sf', 'of'), 'ge': ('sf', 'of'), 'le': ('zf', 'sf', 'of'),
    'g': ('zf', 'sf', 'of'), 'always': (),
}


def condition_name(instruction):
    if instruction.is_jmp_short_or_near:
        return 'always'
    if not instruction.is_jcc_short_or_near:
        raise ValueError('Only direct JMP/Jcc guards are supported')
    return next(name for name in READS if name != 'always'
                and getattr(ConditionCode, name.upper()) == instruction.condition_code)


def decision(condition, flags):
    f = {name: bool(flags & (1 << bit)) for name, bit in FLAG_BITS.items()}
    return {
        'always': True, 'o': f['of'], 'no': not f['of'],
        'b': f['cf'], 'ae': not f['cf'], 'e': f['zf'], 'ne': not f['zf'],
        'be': f['cf'] or f['zf'], 'a': not (f['cf'] or f['zf']),
        's': f['sf'], 'ns': not f['sf'], 'p': f['pf'], 'np': not f['pf'],
        'l': f['sf'] != f['of'], 'ge': f['sf'] == f['of'],
        'le': f['zf'] or f['sf'] != f['of'],
        'g': not f['zf'] and f['sf'] == f['of'],
    }[condition]


def cmp_flags(left, right, bits):
    mask = (1 << bits) - 1
    result = (left - right) & mask
    sign = 1 << (bits - 1)
    values = {'cf': left < right, 'pf': (result & 255).bit_count() % 2 == 0,
              'af': bool((left ^ right ^ result) & 16), 'zf': result == 0,
              'sf': bool(result & sign),
              'of': bool((left ^ right) & (left ^ result) & sign)}
    return sum(int(values[name]) << bit for name, bit in FLAG_BITS.items())
