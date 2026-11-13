"""C89 segmented-memory realization of the unchanged bounded-memory UIL.

This module emits pure native functions; it does not emulate UIL at runtime or
shrink its logical arena. The owning Win16 runtime supplies paged storage,
transactions, OS services and native execution qualification separately.
"""
from __future__ import annotations

from .udc_web_memory import NAME, digest, validate_memory_uil

TARGET = 'windows-x86-16-memory-1'
PROFILE = 'windows-x86-16-memory-c89-segmented-1'
PAGE_WORDS = 8192
PAGE_BYTES = PAGE_WORDS * 4
_KEYWORDS = set('auto break case char const continue default do double else enum extern float for goto if int long register return short signed sizeof static struct switch typedef union unsigned void volatile while'.split())
WIN16_MEMORY_HEADER = r'''#ifndef FDISBULL_WIN16_MEMORY_ABI_1
#define FDISBULL_WIN16_MEMORY_ABI_1
#include <limits.h>
#if ULONG_MAX == 4294967295UL
typedef unsigned long FdbU32;
#elif UINT_MAX == 4294967295UL
typedef unsigned int FdbU32;
#else
#error No exact unsigned 32-bit carrier is available
#endif
typedef unsigned short FdbU16;
typedef char FdbU16_must_be_two_bytes[(sizeof(FdbU16)==2)?1:-1];
typedef char FdbU32_must_be_four_bytes[(sizeof(FdbU32)==4)?1:-1];
typedef struct Fdb16Arena Fdb16Arena;
typedef struct { FdbU32 status, steps, cut; } FdbBlockResult;
FdbU32 fdb16_word_count(const Fdb16Arena *);
int fdb16_read(const Fdb16Arena *, FdbU32, FdbU32 *);
int fdb16_write(Fdb16Arena *, FdbU32, FdbU32);
Fdb16Arena *fdb16_clone(const Fdb16Arena *);
int fdb16_copy(Fdb16Arena *, const Fdb16Arena *);
void fdb16_release(Fdb16Arena *);
#endif
'''


def segmented_layout(program):
    """Describe storage without reinterpreting native size_t or changing UIL."""
    program = validate_memory_uil(program)
    words = program['memory']['words']
    pages = (words + PAGE_WORDS - 1) // PAGE_WORDS
    return {'format': 'fdisbull-win16-segmented-arena-1',
            'module_uil_sha256': digest(program), 'word_bits': 32,
            'logical_words': words, 'logical_bytes': words * 4,
            'page_words': PAGE_WORDS, 'maximum_page_bytes': PAGE_BYTES,
            'pages': pages, 'last_page_words': words - (pages - 1) * PAGE_WORDS,
            'cross_segment_indexing': 'u32 page/index adapters; no far-pointer linear arithmetic',
            'original_memory_shape_preserved': True}


def _emission(program, function, symbol, *, capture_local=None, atomic=True,
              max_automatic_bytes=16384):
    program = validate_memory_uil(program)
    if type(function) is not str or function not in program['functions']:
        raise ValueError('unknown Win16 memory function')
    if type(symbol) is not str or not NAME.fullmatch(symbol) or symbol in _KEYWORDS or symbol.startswith('__'):
        raise ValueError('invalid Win16 memory symbol')
    if capture_local is not None and (type(capture_local) is not str or capture_local not in program['variables']):
        raise ValueError('Win16 capture requires a declared local')
    if type(atomic) is not bool:
        raise ValueError('Win16 atomic mode must be boolean')
    if type(max_automatic_bytes) is not int or not 64 <= max_automatic_bytes <= 32768:
        raise ValueError('Win16 automatic frame budget outside profile')
    spec = program['functions'][function]
    words = program['memory']['words']
    variables = {name: 'fdb_v'+str(i) for i, name in enumerate(sorted(program['variables']))}
    declarations = ['FdbU32 fdb_remaining;', 'FdbU32 fdb_failed;', 'FdbBlockResult fdb_result;']
    if atomic:
        declarations.append('Fdb16Arena *fdb_saved;')
    declarations += ['FdbU32 '+variable+';' for variable in variables.values()]
    lines = []
    temporaries = loops = 0

    def line(indent, value):
        lines.append('  '*indent+value)

    def charge(indent):
        line(indent, 'if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }')
        line(indent, '--fdb_remaining;')

    def temporary():
        nonlocal temporaries
        name = 'fdb_t'+str(temporaries)
        temporaries += 1
        declarations.append('FdbU32 '+name+';')
        return name

    def expression(value, indent):
        if type(value) is int:
            return str(value)+'UL'
        if 'var' in value:
            return variables[value['var']]
        if 'load' in value:
            index = expression(value['load'], indent)
            result = temporary()
            line(indent, 'if ('+index+' >= '+str(words)+'UL) { fdb_failed = 1UL; goto fdb_done; }')
            line(indent, 'if (fdb16_read(fdb_words,'+index+',&'+result+')) { fdb_failed = 2UL; goto fdb_done; }')
            return result
        left = expression(value['left'], indent)
        right = expression(value['right'], indent)
        op = value['op']
        if op in ('div', 'mod'):
            line(indent, 'if ('+right+' == 0UL) { fdb_failed = 1UL; goto fdb_done; }')
        operators = {'add': '+', 'sub': '-', 'mul': '*', 'and': '&', 'or': '|', 'xor': '^',
                     'div': '/', 'mod': '%', 'eq': '==', 'ne': '!=', 'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>='}
        if op in ('shl', 'shr'):
            text = '('+left+(' << ' if op == 'shl' else ' >> ')+'('+right+' & 31UL))'
        else:
            text = '('+left+' '+operators[op]+' '+right+')'
        result = temporary()
        line(indent, result+' = (FdbU32)'+text+';')
        return result

    def body(nodes, indent):
        nonlocal loops
        for node in nodes:
            charge(indent)
            op = node['op']
            if op == 'set':
                value = expression(node['value'], indent)
                line(indent, variables[node['var']]+' = '+value+';')
            elif op == 'store':
                index = expression(node['index'], indent)
                value = expression(node['value'], indent)
                line(indent, 'if ('+index+' >= '+str(words)+'UL) { fdb_failed = 1UL; goto fdb_done; }')
                line(indent, 'if (fdb16_write(fdb_words,'+index+','+value+')) { fdb_failed = 2UL; goto fdb_done; }')
            elif op == 'if':
                condition = expression(node['condition'], indent)
                line(indent, 'if ('+condition+' != 0UL) {')
                body(node['then'], indent+1)
                line(indent, '} else {')
                body(node['else'], indent+1)
                line(indent, '}')
            elif op == 'return':
                line(indent, 'goto fdb_done;')
            else:
                name = 'fdb_loop'+str(loops)
                loops += 1
                declarations.append('FdbU32 '+name+';')
                line(indent, name+' = 0UL;')
                line(indent, 'for (;;) {')
                charge(indent+1)
                condition = expression(node['condition'], indent+1)
                line(indent+1, 'if ('+condition+' == 0UL) break;')
                line(indent+1, 'if ('+name+' == '+str(node['limit'])+'UL) { fdb_failed = 1UL; goto fdb_done; }')
                line(indent+1, '++'+name+';')
                body(node['body'], indent+1)
                line(indent, '}')

    body(spec['body'], 1)
    # Conservative C-source frame ceiling. Actual compiler stack use and NE
    # code-segment lengths still require checks in the native build receipt.
    automatic = (2+len(variables)+temporaries+loops)*4 + 64
    if automatic > max_automatic_bytes:
        raise ValueError('Win16 automatic frame budget exceeded')
    prelude = [f'FdbBlockResult {symbol}(Fdb16Arena *fdb_words) {{']
    prelude += ['  '+text for text in declarations]
    prelude += ['  fdb_remaining = '+str(spec['max_steps'])+'UL;',
                '  fdb_failed = 0UL;',
                '  fdb_result.status = 1UL; fdb_result.steps = 0UL; fdb_result.cut = 0UL;',
                '  if (!fdb_words || fdb16_word_count(fdb_words) != '+str(words)+'UL) return fdb_result;']
    if atomic:
        prelude += ['  fdb_saved = fdb16_clone(fdb_words);',
                    '  if (!fdb_saved) { fdb_result.status = 2UL; return fdb_result; }']
    for name, variable in variables.items():
        prelude.append('  '+variable+' = '+str(program['variables'][name]['initial'])+'UL;')
    suffix = ['fdb_done:']
    if atomic:
        suffix += ['  if (fdb_failed && fdb16_copy(fdb_words,fdb_saved)) fdb_failed = 2UL;',
                   '  fdb16_release(fdb_saved);']
    suffix += ['  fdb_result.status = fdb_failed;',
               '  fdb_result.steps = '+str(spec['max_steps'])+'UL-fdb_remaining;',
               '  fdb_result.cut = '+('fdb_failed ? 0UL : '+variables[capture_local] if capture_local is not None else '0UL')+';',
               '  return fdb_result;', '}']
    source = '\n'.join(prelude+lines+suffix)+'\n'
    return source, {'format': 'fdisbull-win16-function-emission-1', 'target': TARGET, 'profile': PROFILE,
                    'module_uil_sha256': digest(program), 'function': function, 'symbol': symbol,
                    'logical_words': words, 'atomic': atomic, 'capture_local': capture_local,
                    'temporary_words': temporaries, 'loop_words': loops,
                    'conservative_automatic_bytes': automatic, 'automatic_budget': max_automatic_bytes,
                    'native_execution': False,
                    'status': {'complete': 0, 'uil_refusal': 1, 'carrier_failure': 2},
                    'scope': 'C89 source emission; compiler ABI, code-segment size, stack and Win16 execution qualify separately'}


def emit_win16_memory_function(program, function, symbol, *, capture_local=None,
                               atomic=True, max_automatic_bytes=16384):
    """Emit ordered C89, with u32 page adapters and explicit rollback ownership."""
    return _emission(program, function, symbol, capture_local=capture_local,
                     atomic=atomic, max_automatic_bytes=max_automatic_bytes)[0]


def win16_function_receipt(program, function, symbol, *, capture_local=None,
                           atomic=True, max_automatic_bytes=16384):
    """Return bounded source metadata; never claim native compilation/execution."""
    import hashlib
    source, receipt = _emission(program, function, symbol, capture_local=capture_local,
                                atomic=atomic, max_automatic_bytes=max_automatic_bytes)
    return {**receipt, 'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
