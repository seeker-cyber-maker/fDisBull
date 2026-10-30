"""Bounded structure and instruction facts for raw Z-machine version 3 stories.

This module does not execute a VM. Offsets are story-byte coordinates, never
native interpreter addresses. Unknown opcodes stop decoding explicitly.
"""
from pathlib import Path
import hashlib


MAX_STORY_FILE = 512 * 1024


def inspect_story(path):
    """Recognize a raw v3 image by its structure, independent of its filename."""
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_STORY_FILE + 1)
    return inspect_story_bytes(data)


def inspect_story_bytes(data):
    """Inspect one immutable v3 source snapshot without reopening its file.

    The path-based entry point delegates here so a processor can qualify and
    decode the same bytes, even if the original path later changes.
    """
    if not isinstance(data, bytes):
        raise ValueError('Expected immutable raw Z-machine v3 story bytes')
    if not 64 <= len(data) <= MAX_STORY_FILE or data[0] != 3:
        raise ValueError('Expected a raw Z-machine v3 story of 64..524288 bytes')
    word = lambda n: int.from_bytes(data[n:n + 2], 'big')
    length = word(26) * 2
    if not 64 <= length <= min(len(data), 128 * 1024):
        raise ValueError('v3 story requires a valid declared length')
    static, high, pc = word(14), word(4), word(6)
    if not 64 <= static <= high < length or not 64 <= pc < length:
        raise ValueError('Invalid dynamic/static/high memory or entry bounds')
    objects, globals_, abbreviations, dictionary = (word(n) for n in (10, 12, 24, 8))
    if not (64 <= objects and objects + 62 <= static and 64 <= globals_ and globals_ + 480 <= static):
        raise ValueError('Object defaults or global table exceeds dynamic memory')
    if not 64 <= abbreviations or abbreviations + 192 > min(length, 65536):
        raise ValueError('Abbreviations table exceeds readable memory')
    if not 64 <= dictionary < min(length, 65536):
        raise ValueError('Invalid dictionary address')
    at = dictionary + 1 + data[dictionary]
    if at + 3 > length:
        raise ValueError('Truncated dictionary header')
    entry_size = data[at]
    entries = abs(int.from_bytes(data[at + 1:at + 3], 'big', signed=True))
    if entry_size < 4 or at + 3 + entries * entry_size > length:
        raise ValueError('Dictionary records exceed story length')
    checksum = sum(data[64:length]) & 65535
    if checksum != word(28):
        raise ValueError('Story checksum mismatch')
    return {'format': 'z-machine', 'version': 3, 'release': word(2),
            'serial': data[18:24].hex(), 'serial_text': data[18:24].decode('ascii', errors='replace'),
            'sha256': hashlib.sha256(data).hexdigest(), 'file_bytes': len(data),
            'declared_bytes': length, 'trailing_bytes': len(data) - length,
            'checksum': checksum, 'checksum_status': 'matched', 'initial_pc': pc,
            'static_memory': static, 'high_memory': high, 'objects': objects,
            'globals': globals_, 'dictionary': dictionary, 'abbreviations': abbreviations,
            'scope': 'raw v3 with length/checksum; early v3 without these fields and other versions unsupported'}


_TWO = {1: 'je', 2: 'jl', 3: 'jg', 4: 'dec_chk', 5: 'inc_chk', 6: 'jin',
        7: 'test', 8: 'or', 9: 'and', 10: 'test_attr', 11: 'set_attr',
        12: 'clear_attr', 13: 'store', 14: 'insert_obj', 15: 'loadw',
        16: 'loadb', 17: 'get_prop', 18: 'get_prop_addr', 19: 'get_next_prop',
        20: 'add', 21: 'sub', 22: 'mul', 23: 'div', 24: 'mod'}
_ONE = {0: 'jz', 1: 'get_sibling', 2: 'get_child', 3: 'get_parent',
        4: 'get_prop_len', 5: 'inc', 6: 'dec', 7: 'print_addr', 9: 'remove_obj',
        10: 'print_obj', 11: 'ret', 12: 'jump', 13: 'print_paddr', 14: 'load', 15: 'not'}
_ZERO = {0: 'rtrue', 1: 'rfalse', 2: 'print', 3: 'print_ret', 4: 'nop',
         5: 'save', 6: 'restore', 7: 'restart', 8: 'ret_popped', 9: 'pop',
         10: 'quit', 11: 'new_line', 12: 'show_status', 13: 'verify'}
_VAR = {0: 'call', 1: 'storew', 2: 'storeb', 3: 'put_prop', 4: 'read',
        5: 'print_char', 6: 'print_num', 7: 'random', 8: 'push', 9: 'pull',
        10: 'split_window', 11: 'set_window', 19: 'output_stream',
        20: 'input_stream', 21: 'sound_effect'}
_STORES = {'or', 'and', 'loadw', 'loadb', 'get_prop', 'get_prop_addr',
           'get_next_prop', 'add', 'sub', 'mul', 'div', 'mod', 'get_sibling',
           'get_child', 'get_parent', 'get_prop_len', 'load', 'not', 'call', 'random'}
_BRANCHES = {'je', 'jl', 'jg', 'dec_chk', 'inc_chk', 'jin', 'test',
             'test_attr', 'jz', 'get_sibling', 'get_child', 'save', 'restore', 'verify'}


def decode_v3(data, offset):
    """Decode one v3 instruction, including store, branch and inline text spans."""
    if not isinstance(data, bytes) or type(offset) is not int or not 0 <= offset < len(data):
        raise ValueError('Invalid source bytes or instruction offset')
    start = offset

    def read(size=1):
        nonlocal offset
        if offset + size > len(data):
            raise ValueError('Truncated instruction')
        n = int.from_bytes(data[offset:offset + size], 'big'); offset += size
        return n

    opcode = read()
    if opcode < 128:
        family, number = _TWO, opcode & 31
        kinds = [2 if opcode & 64 else 1, 2 if opcode & 32 else 1]
    elif opcode < 192:
        kind = (opcode >> 4) & 3
        family, number = (_ZERO if kind == 3 else _ONE), opcode & 15
        kinds = [] if kind == 3 else [kind]
    else:
        family, number = (_VAR if opcode & 32 else _TWO), opcode & 31
        types = read(); kinds = []
        ended = False
        for shift in (6, 4, 2, 0):
            kind = (types >> shift) & 3
            if kind == 3: ended = True
            elif ended: raise ValueError('Operand after omitted operand')
            else: kinds.append(kind)
    if number not in family:
        raise ValueError(f'Unsupported v3 opcode at {start:#x}')
    name = family[number]
    operands = [{'kind': ('large', 'small', 'variable')[kind], 'value': read(2 if kind == 0 else 1)} for kind in kinds]
    result = {'offset': start, 'op': name, 'operands': operands}
    if name in _STORES: result['store'] = read()
    if name in _BRANCHES:
        first = read(); displacement = first & 63
        if not first & 64:
            displacement = displacement * 256 + read()
            if displacement & 8192: displacement -= 16384
        result['branch'] = {'when': bool(first & 128), 'offset': displacement,
                            'return': bool(displacement) if displacement in (0, 1) else None,
                            'target': offset + displacement - 2 if displacement not in (0, 1) else None}
    if name in ('print', 'print_ret'):
        result['text_offset'] = offset
        words = 0
        while True:
            word = read(2); words += 1
            if words > 16384: raise ValueError('Inline text budget exceeded')
            if word & 32768: break
    result.update(end=offset, bytes=data[start:offset].hex())
    return result


def decode_ztext(data, offset, *, max_chars=8192, _depth=0, _seen=()):
    """Decode v3 default-alphabet text with bounded abbreviation expansion."""
    if _depth > 8 or offset in _seen or type(offset) is not int or not 0 <= offset < len(data):
        raise ValueError('Invalid or cyclic Z-text')
    chars, at = [], offset
    for _ in range(16384):
        if at + 2 > len(data): raise ValueError('Truncated Z-text')
        w = int.from_bytes(data[at:at + 2], 'big'); at += 2
        chars.extend(((w >> 10) & 31, (w >> 5) & 31, w & 31))
        if w & 32768: break
    else: raise ValueError('Z-text word budget exceeded')
    alphabets = ('abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', ' \n0123456789.,!?_#\'"/\\-:()')
    out, i, alphabet = [], 0, 0
    while i < len(chars):
        c = chars[i]; i += 1
        if c == 0: out.append(' ')
        elif c in (1, 2, 3):
            if i >= len(chars): raise ValueError('Truncated abbreviation')
            index = 32 * (c - 1) + chars[i]; i += 1
            table = int.from_bytes(data[24:26], 'big') + index * 2
            if table + 2 > len(data): raise ValueError('Abbreviation table out of range')
            address = int.from_bytes(data[table:table + 2], 'big') * 2
            out.append(decode_ztext(data, address, max_chars=max_chars, _depth=_depth + 1, _seen=_seen + (offset,))[0])
        elif c in (4, 5):
            alphabet = c - 3
            continue
        elif alphabet == 2 and c == 6:
            if i + 1 >= len(chars): raise ValueError('Truncated ZSCII escape')
            n = chars[i] * 32 + chars[i + 1]; i += 2
            if n == 13: out.append('\n')
            elif 32 <= n <= 126: out.append(chr(n))
            else: raise ValueError('Unsupported ZSCII character')
        else: out.append(alphabets[alphabet][c - 6])
        alphabet = 0
        if sum(map(len, out)) > max_chars: raise ValueError('Z-text character budget exceeded')
    return ''.join(out), at
