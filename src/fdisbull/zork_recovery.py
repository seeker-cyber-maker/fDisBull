"""Recover one source-bound Zork I mailbox action, not a whole game parser.

Only the exact R88 story and the explicitly guarded one-child path are in
scope. RAM is a caller-provided snapshot at action entry, including global 0x86.
"""
from pathlib import Path
from fdisbull.zmachine import inspect_story, decode_v3, decode_ztext
from fdisbull.il_recovery import recover_v3_attributes
from fdisbull.interaction_il import validate_il

STORY_SHA256 = '0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd'


def _word(data, at):
    if at < 0 or at + 2 > len(data): raise ValueError('RAM pointer out of bounds')
    return int.from_bytes(data[at:at + 2], 'big')


def _record(data, number):
    if not 1 <= number <= 255: raise ValueError('invalid object')
    at = _word(data, 10) + 62 + (number - 1) * 9
    if at + 9 > len(data): raise ValueError('object record out of bounds')
    return at


def _attr(data, obj, number):
    at = _record(data, obj)
    return bool(data[at + number // 8] & (128 >> (number % 8)))


def _property(data, obj, number):
    at = _word(data, _record(data, obj) + 7)
    if at >= len(data): raise ValueError('property table out of bounds')
    cursor = at + 1 + 2 * data[at]
    for _ in range(32):
        if cursor >= len(data): raise ValueError('property list out of bounds')
        header = data[cursor]; cursor += 1
        if not header: break
        prop, size = header & 31, (header >> 5) + 1
        if not prop or cursor + size > len(data): raise ValueError('invalid property')
        if prop == number:
            if size == 1: return data[cursor]
            return _word(data, cursor)
        cursor += size
    else:
        raise ValueError('property list exceeds limit')
    return _word(data, _word(data, 10) + 2 * (number - 1))


def _name_key(data, obj):
    at = _word(data, _record(data, obj) + 7)
    if at >= len(data): raise ValueError('name out of bounds')
    length = data[at]
    if length != 3 or at + 1 + 2 * length > len(data):
        raise ValueError('unsupported object short-name layout')
    return int.from_bytes(data[at:at + 1 + 2 * length], 'big')


def state_from_ram(rambytes):
    """Extract investigator-side action-entry fields without mutating a snapshot."""
    if not isinstance(rambytes, bytes) or len(rambytes) < 64 or rambytes[0] != 3:
        raise ValueError('expected v3 RAM bytes')
    mailbox, child = _record(rambytes, 160), _record(rambytes, 161)
    return {'$opened': _attr(rambytes, 160, 11), '$seen': _attr(rambytes, 160, 3),
            '$container': _attr(rambytes, 160, 19), '$transparent': _attr(rambytes, 160, 12),
            '$property10': _property(rambytes, 160, 10), '$property14': _property(rambytes, 161, 14),
            '$object': _word(rambytes, _word(rambytes, 12) + 2 * (0x86 - 0x10)),
            '$child': rambytes[mailbox + 6], '$sibling': rambytes[child + 5],
            '$mailbox_name': _name_key(rambytes, 160), '$child_name': _name_key(rambytes, 161)}


def recover_mailbox(story):
    info = inspect_story(story)
    if info['sha256'] != STORY_SHA256: raise ValueError('unsupported story identity')
    data = Path(story).read_bytes()
    primitive = recover_v3_attributes(data, [0x80a3, 0x80a6], source_file='story', object_variable=0x86, bindings={11: '$opened', 3: '$seen'})
    evidence = primitive['evidence']
    def span(label, start, end, **facts):
        evidence[label] = {'file': 'story', 'sha256': STORY_SHA256, 'range': [start, end], 'bytes': data[start:end].hex(), 'language': 'z-machine-v3', **facts}
        return label
    def ins(label, offset, op):
        instruction = decode_v3(data, offset)
        if instruction['op'] != op: raise ValueError('source instruction mismatch')
        span(label, offset, instruction['end'], instruction=op)
        return instruction
    def text(label, offset, op):
        item = ins(label, offset, op)
        return decode_ztext(data, item['text_offset'])[0]
    def text_dependencies(start, seen=None):
        seen = set() if seen is None else seen
        if start in seen: raise ValueError('cyclic source text')
        seen.add(start)
        at = start; chars = []
        while True:
            w = _word(data, at); at += 2
            chars.extend(((w >> 10) & 31, (w >> 5) & 31, w & 31))
            if w & 0x8000: break
        i = 0
        while i < len(chars):
            code = chars[i]; i += 1
            if code in (1, 2, 3):
                if i >= len(chars): raise ValueError('truncated abbreviation')
                entry = info['abbreviations'] + 2 * (32 * (code - 1) + chars[i]); i += 1
                target = 2 * _word(data, entry)
                span(f'abbr-entry-{entry:x}', entry, entry + 2, source_fact='abbreviation pointer')
                end = decode_ztext(data, target)[1]
                span(f'abbr-text-{target:x}', target, end, source_fact='abbreviation text')
                text_dependencies(target, seen.copy())
            elif code in (4, 5) and i < len(chars):
                # A2/6 consumes two Z-characters as a ZSCII escape.
                if code == 5 and chars[i] == 6:
                    i += 3
                else:
                    i += 1
    # Inline and object names may contain abbreviation references.
    text_starts = [decode_v3(data, n)['text_offset'] for n in (0x80dc, 0x80e7, 0x8e7f, 0x80f4, 0x809a)]
    text_starts += [_word(data, _record(data, n) + 7) + 1 for n in (160, 161)]
    for start in text_starts: text_dependencies(start)
    first = text('prefix', 0x80dc, 'print')
    first += decode_ztext(data, _word(data, _record(data, 160) + 7) + 1)[0]
    first += text('middle', 0x80e7, 'print')
    first += text('article', 0x8e7f, 'print')
    first += decode_ztext(data, _word(data, _record(data, 161) + 7) + 1)[0]
    first += text('suffix', 0x80f4, 'print_ret') + '\n'
    repeat = text('repeat', 0x809a, 'print_ret') + '\n'
    ins('condition', 0x8096, 'test_attr')
    for name, at, op in [('guard-container',0x8089,'test_attr'),('guard-property',0x808e,'get_prop'),('guard-property-branch',0x8092,'jz'),('child-test',0x80a9,'get_child'),('transparent-test',0x80ad,'test_attr'),('child-check',0x80b8,'get_child'),('sibling-check',0x80bc,'get_sibling'),('child-attr',0x80c0,'test_attr'),('child-prop',0x80c4,'get_prop'),('child-prop-branch',0x80c8,'jz'),('print-mailbox',0x80e5,'print_obj'),('list-call',0x80ee,'call'),('list-child',0x8e65,'get_child'),('list-sibling',0x8e69,'get_sibling'),('print-child',0x8e82,'print_obj')]:
        ins(name, at, op)
    span('header', 0, 64, source_fact='object, globals and abbreviation table pointers')
    for name, obj in [('mailbox-record',160),('child-record',161)]:
        at = _record(data, obj); span(name, at, at + 9, object_number=obj)
        table = _word(data, at + 7); end = table + 1 + 2 * data[table]
        span(name + '-name', table, end, object_number=obj, source_fact='short name')
    span('list-control', 0x8e65, 0x8e9d, source_fact='bounded one-child list formatting control')
    span('list-locals', 0x8e58, 0x8e65, source_fact='routine local initial values')
    span('object-defaults', info['objects'], info['objects'] + 62, source_fact='default property values')
    # Bind runtime short names to the exact source values used to compose text.
    names = {'$mailbox_name': _name_key(data, 160), '$child_name': _name_key(data, 161)}
    variables = dict(primitive['variables'])
    variables.update({n: {'type': 'bool', 'initial': False} for n in ('$container', '$transparent')})
    variables.update({n: {'type': 'u16', 'initial': 0} for n in ('$property10', '$property14', '$object')})
    variables.update({n: {'type': 'u8', 'initial': 0} for n in ('$child', '$sibling')})
    variables.update({n: {'type': 'u64', 'initial': 0} for n in names})
    eq = lambda name, value: {'op':'eq', 'left':{'var':name}, 'right':value}
    require = {'op':'and', 'conditions':[eq('$container',True), eq('$transparent',False), {'op':'not','condition':eq('$property10',0)}, eq('$object',160), eq('$child',161), eq('$sibling',0), eq('$property14',0), *[eq(n,v) for n,v in names.items()]]}
    refs = ['header','guard-container','guard-property','guard-property-branch','child-test','transparent-test','child-check','sibling-check','child-attr','child-prop','child-prop-branch','mailbox-record','child-record','mailbox-record-name','child-record-name','object-defaults']
    body = [{'id':'qualified-path','op':'require','condition':require,'evidence':refs},
            {'id':'already-open','op':'if','condition':eq('$opened',True), 'evidence':['condition'],
             'then':[{'id':'repeated-response','op':'text','resource':'repeated','evidence':['repeat'] + [k for k in evidence if k.startswith('abbr-')]}],
             'else':primitive['body'] + [{'id':'first-response','op':'text','resource':'first','evidence':[k for k in evidence if k.startswith('abbr-')] + ['prefix','print-mailbox','mailbox-record-name','middle','list-call','list-locals','list-control','list-child','list-sibling','article','print-child','child-record-name','suffix']}]}]
    doc = {'format':'fdisbull-il-1','role':'udl','variables':variables,'resources':{'first':{'kind':'text','text':first},'repeated':{'kind':'text','text':repeat}},'evidence':evidence,'body':body}
    validate_il(doc)
    return {'il':doc, 'initial_story_state':state_from_ram(data[:info['static_memory']]),
            'requires_action_entry_ram':True,
            'z':{'story_sha256':STORY_SHA256, 'scope':'mailbox open, first or repeated, qualified single-child source path', 'object_variable':0x86, 'object_number':160, 'child_number':161, 'unknown':['parser and object binding','turn loop','global processes','other object and list states']}}
