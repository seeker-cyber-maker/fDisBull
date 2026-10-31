"""Bounded native Windows x64 orchestration, separate from semantic definitions.

This is an authored PE32+ target, not a DOS/Win16 wrapper. Selected IL
modules lower to native instructions. The plan owns state, calls, bounded loops
and notification bindings. An explicitly selected C backend invokes a compiler; generated programs are
never executed by this builder. It does not qualify source-to-UIL correspondence.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from .interaction_il import validate_il

FORMAT = 'fdisbull-native-shell-1'
PROFILE = 'windows-x64-state-arena-1'
SLOT = 4096
BASE = 0x140000000
TYPES = {'u8', 'u16', 'i16', 'bool'}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _check(ok, message):
    if not ok:
        raise ValueError(message)


def _fields(value, required, optional=()):
    _check(isinstance(value, dict) and set(required) <= value.keys() <= set(required) | set(optional),
           'unsupported native shell fields')


def _ident(value):
    _check(isinstance(value, str) and re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_.$-]{0,95}', value),
           'invalid native shell identity')


def _text(value):
    _check(isinstance(value, str) and '\0' not in value, 'invalid native ASCII text')
    try:
        raw = value.encode('ascii') + b'\0'
    except UnicodeEncodeError as error:
        raise ValueError('MessageBoxA profile supports ASCII text only') from error
    _check(len(raw) <= SLOT, 'native text resource exceeds fixed slot')
    return raw


def _align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def _remove_owned_output(directory, identity, files):
    """Remove only known created inodes; preserve replacements/unknown files."""
    try:
        current = directory.lstat()
        if (current.st_dev, current.st_ino) != identity:
            return
        for name, expected in files.items():
            path = directory / name
            try:
                item = path.lstat()
                if (item.st_dev, item.st_ino) == expected:
                    path.unlink()
            except OSError:
                pass
        current = directory.lstat()
        if (current.st_dev, current.st_ino) == identity:
            directory.rmdir()
    except OSError:
        pass


class _Code:
    def __init__(self, base, prefix):
        self.base, self.prefix = base, prefix
        self.data, self.labels, self.fixups = bytearray(), {}, []
        self.sequence = 0
        self.maps = []

    def emit(self, raw):
        self.data.extend(bytes.fromhex(raw) if isinstance(raw, str) else raw)

    def fresh(self):
        self.sequence += 1
        return self.prefix + ':local:' + str(self.sequence)

    def mark(self, label):
        _check(label not in self.labels, 'duplicate native code label')
        self.labels[label] = self.base + len(self.data)

    def relative(self, opcode, target):
        self.emit(opcode)
        self.fixups.append((len(self.data), target))
        self.emit(bytes(4))

    def resolve(self, symbols):
        symbols = {**symbols, **self.labels}
        for offset, target in self.fixups:
            _check(target in symbols, 'missing native symbol: ' + target)
            displacement = symbols[target] - (self.base + offset + 4)
            _check(-(1 << 31) <= displacement < 1 << 31, 'native relative reference overflow')
            struct.pack_into('<i', self.data, offset, displacement)
        _check(len(self.data) <= SLOT, 'native function exceeds fixed 4096-byte code slot')
        return bytes(self.data) + b'\xcc' * (SLOT - len(self.data))


class _Lower:
    def __init__(self, code, cells, offsets, register, end, fail, *, pure=False, events=None):
        self.c, self.cells, self.offsets, self.register = code, cells, offsets, register
        self.end, self.fail, self.pure = end, fail, pure
        self.events = events

    def value(self, value):
        if isinstance(value, dict):
            _fields(value, ('var',))
            name = value['var']
            _check(name in self.cells, 'unknown native state cell')
            typ = self.cells[name]['type']
            # R12 is the live arena; R13 is an activation-private IL work copy.
            if self.register == 'r12':
                prefix = '490fbf8424' if typ == 'i16' else ('410fb68424' if typ == 'u8' else '410fb78424')
            else:
                prefix = '490fbf85' if typ == 'i16' else ('410fb685' if typ == 'u8' else '410fb785')
            self.c.emit(prefix)
            self.c.emit(struct.pack('<I', self.offsets[name]))
        else:
            _check(type(value) in (int, bool) and -(1 << 63) <= value < 1 << 63,
                   'native literal outside supported signed 64-bit value domain')
            self.c.emit('48b8')
            self.c.emit(struct.pack('<Q', int(value) & ((1 << 64) - 1)))

    def store(self, name, *, checked=False):
        _check(name in self.cells, 'unknown native output cell')
        typ = self.cells[name]['type']
        if checked:
            if typ == 'i16':
                self.c.emit('483d0080ffff')  # CMP RAX,-32768
                self.c.relative('0f8c', self.fail)
                self.c.emit('483dff7f0000')
                self.c.relative('0f8f', self.fail)
            else:
                self.c.emit('483d')
                self.c.emit(struct.pack('<I', {'u8': 255, 'u16': 65535, 'bool': 1}[typ]))
                self.c.relative('0f87', self.fail)
        self.c.emit('25')
        self.c.emit(struct.pack('<I', 255 if typ == 'u8' else (1 if typ == 'bool' else 65535)))
        self.c.emit('6641898424' if self.register == 'r12' else '66418985')
        self.c.emit(struct.pack('<I', self.offsets[name]))

    def condition(self, condition, depth=0):
        _check(depth <= 24 and isinstance(condition, dict), 'native condition depth exceeded')
        op = condition.get('op')
        if op == 'eq':
            _fields(condition, ('op', 'left', 'right'))
            self.value(condition['left']); self.c.emit('50')
            self.value(condition['right']); self.c.emit('4889c1594839c8')
            self.c.emit('0f94c00fb6c0')
        elif op == 'ge':
            _fields(condition, ('op', 'left', 'right'))
            for side in ('left', 'right'):
                item = condition[side]
                if isinstance(item, dict):
                    _check(self.cells.get(item.get('var'), {}).get('type') in ('u8', 'u16'),
                           'native ge compares unsigned cells only')
            self.value(condition['left']); self.c.emit('50')
            self.value(condition['right']); self.c.emit('4889c1594839c1')
            self.c.emit('0f93c00fb6c0')
        elif op == 'bit_test':
            _fields(condition, ('op', 'value', 'bit'))
            _check(type(condition['bit']) is int and 0 <= condition['bit'] < 64, 'unsupported native bit index')
            self.value(condition['value'])
            self.c.emit('480fbae0'); self.c.emit(bytes([condition['bit']]))
            self.c.emit('0f92c00fb6c0')
        elif op == 'not':
            _fields(condition, ('op', 'condition'))
            self.condition(condition['condition'], depth + 1); self.c.emit('83f001')
        elif op == 'and':
            _fields(condition, ('op', 'conditions'))
            _check(isinstance(condition['conditions'], list) and 0 < len(condition['conditions']) <= 64,
                   'invalid native conjunction')
            false, done = self.c.fresh(), self.c.fresh()
            for child in condition['conditions']:
                self.condition(child, depth + 1); self.c.emit('85c0'); self.c.relative('0f84', false)
            self.c.emit('b801000000'); self.c.relative('e9', done)
            self.c.mark(false); self.c.emit('31c0'); self.c.mark(done)
        else:
            raise ValueError('unsupported native condition')

    def body(self, body, path, depth=0):
        _check(isinstance(body, list) and len(body) <= 256 and depth <= 12, 'native body budget exceeded')
        for index, item in enumerate(body):
            _check(isinstance(item, dict), 'invalid native statement')
            start, op = self.c.base + len(self.c.data), item.get('op')
            common = ('id', 'evidence')
            if op in ('set', 'add', 'subtract'):
                _fields(item, ('op', 'var', 'value'), common)
                name = item['var']; _check(name in self.cells, 'unknown native state cell')
                self.value(item['value'])
                if op != 'set':
                    _check(self.cells[name]['type'] != 'bool', 'arithmetic on native bool is unsupported')
                    self.c.emit('4889c1'); self.value({'var': name})
                    self.c.emit('4801c8' if op == 'add' else '4829c8')
                self.store(name, checked=op == 'set')
            elif op == 'if':
                _fields(item, ('op', 'condition', 'then', 'else'), common)
                otherwise, done = self.c.fresh(), self.c.fresh()
                self.condition(item['condition']); self.c.emit('85c0'); self.c.relative('0f84', otherwise)
                self.body(item['then'], path + '.' + str(index) + '.then', depth + 1)
                self.c.relative('e9', done); self.c.mark(otherwise)
                self.body(item['else'], path + '.' + str(index) + '.else', depth + 1); self.c.mark(done)
            elif op == 'require':
                _fields(item, ('op', 'condition'), common)
                self.condition(item['condition']); self.c.emit('85c0'); self.c.relative('0f84', self.fail)
            elif self.pure and op == 'text':
                _fields(item, ('op', 'resource'), common)
                _check(self.events is not None, 'native text requires a notification binding')
                counter, queue = self.events['counter'], self.events['queue']
                self.c.relative('488d05', 'resource:' + item['resource'])
                self.c.emit('8b8c24'); self.c.emit(struct.pack('<I', counter))
                self.c.emit('488984cc'); self.c.emit(struct.pack('<I', queue))
                self.c.emit('ff8424'); self.c.emit(struct.pack('<I', counter))
            elif not self.pure and op == 'call':
                _fields(item, ('op',), ('function', 'binding', 'result', *common))
                _check(('function' in item) != ('binding' in item), 'native call requires exactly one target')
                target = ('fn:' + item['function']) if 'function' in item else ('module:' + item['binding'])
                self.c.emit('4c89e1'); self.c.relative('e8', target)
                self.c.emit('85d2'); self.c.relative('0f85', self.fail + ':status')
                if 'result' in item:
                    self.store(item['result'], checked=True)
            elif not self.pure and op == 'notify':
                _fields(item, ('op', 'binding', 'value'), ('result', *common))
                self.value(item['value']); self.c.emit('0fb7d04c89e1')
                self.c.relative('e8', 'module:' + item['binding'])
                self.c.emit('85d2'); self.c.relative('0f85', self.fail + ':status')
                if 'result' in item:
                    self.store(item['result'], checked=True)
            elif not self.pure and op == 'while':
                _fields(item, ('op', 'condition', 'limit', 'body'), common)
                _check(type(item['limit']) is int and 0 <= item['limit'] <= 65535, 'native loop limit outside 0..65535')
                counter = 32 + 4 * depth
                self.c.emit('c78424'); self.c.emit(struct.pack('<II', counter, item['limit']))
                again, done, available = self.c.fresh(), self.c.fresh(), self.c.fresh()
                self.c.mark(again); self.condition(item['condition']); self.c.emit('85c0'); self.c.relative('0f84', done)
                self.c.emit('83bc24'); self.c.emit(struct.pack('<I', counter)); self.c.emit('00')
                self.c.relative('0f85', available)
                self.c.emit('ba02000000'); self.c.relative('e9', self.fail + ':status')
                self.c.mark(available); self.c.emit('ff8c24'); self.c.emit(struct.pack('<I', counter))
                self.body(item['body'], path + '.' + str(index) + '.body', depth + 1)
                self.c.relative('e9', again); self.c.mark(done)
            elif not self.pure and op == 'return':
                _fields(item, ('op', 'value'), common)
                self.value(item['value']); self.c.emit('0fb7c031d2'); self.c.relative('e9', self.end)
            else:
                raise ValueError('unsupported native statement: ' + str(op))
            self.c.maps.append({'origin': item.get('id', path + '.' + str(index)),
                                'rva': start, 'end_exclusive': self.c.base + len(self.c.data)})


NOTIFICATION_BACKENDS = ('message-box-a', 'debug-string-a')


def _validate(plan, modules, notification_backends=NOTIFICATION_BACKENDS):
    _check(len(_json({'plan': plan, 'modules': modules})) <= 1024 * 1024, 'native build input exceeds 1 MiB')
    _fields(plan, ('format', 'entry', 'state', 'resources', 'functions'), ('evidence',))
    _check(plan['format'] == FORMAT, 'unsupported native shell format')
    _check(isinstance(modules, dict) and 1 <= len(modules) <= 32, 'native shell requires 1..32 bindings')
    _check(all(isinstance(module, dict) for module in modules.values()), 'invalid native module')
    _check(isinstance(plan['state'], dict) and len(plan['state']) <= 128, 'native state exceeds 128 cells')
    _check(isinstance(plan['resources'], dict) and len(plan['resources']) <= 32, 'native resource budget exceeded')
    for name, cell in plan['state'].items():
        _ident(name); _fields(cell, ('type', 'initial'))
        _check(cell['type'] in TYPES, 'unsupported native logical state type')
        value, typ = cell['initial'], cell['type']
        ranges = {'u8': (0, 255), 'u16': (0, 65535), 'i16': (-32768, 32767)}
        _check((type(value) is bool if typ == 'bool' else
                type(value) is int and ranges[typ][0] <= value <= ranges[typ][1]), 'invalid native state initial value')
    for name, resource in plan['resources'].items():
        _ident(name); _fields(resource, ('kind', 'text'))
        _check(resource['kind'] == 'text', 'native shell supports text resources only'); _text(resource['text'])
    _check(isinstance(plan['functions'], dict) and 1 <= len(plan['functions']) <= 16, 'native function budget exceeded')
    _check(plan['entry'] in plan['functions'], 'native entry function is missing')
    calls = {name: set() for name in plan['functions']}
    def references(body, owner, depth=0):
        _check(isinstance(body, list) and depth <= 12, 'invalid native function body')
        for item in body:
            _check(isinstance(item, dict), 'invalid native statement')
            op = item.get('op')
            if op == 'call':
                if 'function' in item:
                    _check(item['function'] in calls, 'unknown native function'); calls[owner].add(item['function'])
                else:
                    _check(item.get('binding') in modules and modules[item['binding']].get('backend') in ('uil','c-uil'),
                           'native call requires an IL binding')
            elif op == 'notify':
                _check(item.get('binding') in modules and modules[item['binding']].get('backend') in notification_backends,
                       'native notify requires an admitted notification provider')
            if op == 'if':
                references(item.get('then'), owner, depth + 1); references(item.get('else'), owner, depth + 1)
            elif op == 'while':
                references(item.get('body'), owner, depth + 1)
    for name, function in plan['functions'].items():
        _ident(name); _fields(function, ('body',), ('return',)); references(function['body'], name)
    def visit(name, ancestors):
        _check(name not in ancestors, 'recursive/reentrant native function graphs are unsupported')
        for child in calls[name]: visit(child, ancestors | {name})
    for name in calls: visit(name, set())
    for name, module in modules.items():
        _ident(name); _check(isinstance(module, dict), 'invalid native module')
        if module.get('backend') in ('uil','c-uil'):
            _fields(module, ('backend', 'program'), ('return', 'notification_binding', 'state_adapter', 'id', 'evidence'))
            validate_il(module['program'])
            adapter = module.get('state_adapter')
            if adapter is not None:
                _fields(adapter, ('inputs', 'outputs'))
                for side in ('inputs', 'outputs'):
                    names = adapter[side]
                    _check(isinstance(names, list) and all(isinstance(name, str) for name in names)
                           and len(names) == len(set(names))
                           and set(names) <= set(module['program']['variables']), 'invalid native state adapter')
            for resource, declaration in module['program']['resources'].items():
                _check(declaration['kind'] == 'text' and plan['resources'].get(resource) == declaration,
                       'native IL text resources require identical declared plan bindings')
            if _event_count(module['program']['body']):
                binding = module.get('notification_binding')
                _check(binding in modules and modules[binding].get('backend') in notification_backends,
                       'native IL text requires an admitted notification_binding')
            for var, declaration in module['program']['variables'].items():
                _check(declaration['type'] in TYPES, 'unsupported native module logical type')
                if adapter is None or var in adapter['inputs'] or var in adapter['outputs']:
                    _check(var in plan['state'] and declaration['type'] == plan['state'][var]['type'],
                           'native module state binding/type mismatch')
            _check(module.get('return') is None or module['return'] in module['program']['variables'],
                   'unknown native module return cell')
        else:
            _fields(module, ('backend', 'title', 'messages', 'default'), ('style', 'id', 'evidence'))
            _check(module['backend'] in notification_backends, 'unsupported native service backend')
            _text(module['title'])
            _check(isinstance(module['messages'], dict) and len(module['messages']) <= 32, 'native message budget exceeded')
            for key, resource in module['messages'].items():
                _check(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,4}', key) and int(key) <= 65535,
                       'notification keys must be canonical u16 decimals')
                _check(resource in plan['resources'], 'unknown native notification resource')
            _check(module['default'] in plan['resources'], 'unknown native default notification resource')
            _check(type(module.get('style', 0)) is int and module.get('style', 0) in (0, 16, 32, 48, 64),
                   'native MessageBoxA style must be MB_OK with an admitted icon')


def _event_count(body):
    return sum((1 if item['op'] == 'text' else 0) +
               (_event_count(item['then']) + _event_count(item['else']) if item['op'] == 'if' else 0)
               for item in body)


def _module(code, module, state, offsets):
    end, fail = code.fresh(), code.fresh()
    if module['backend'] == 'uil':
        variables = module['program']['variables']
        adapter = module.get('state_adapter')
        work = {name: index * 2 for index, name in enumerate(sorted(variables))}
        count = _event_count(module['program']['body'])
        _check(count <= 32, 'native IL text event budget exceeded')
        event_counter = 32 + _align(len(work) * 2, 16)
        event_queue = event_counter + 8
        event_index = event_counter + 4
        frame = _align(len(work) * 2, 16) + 40
        if count:
            frame = _align(_align(len(work) * 2, 16) + 8 + count * 8, 16) + 40
        code.emit('415441554881ec'); code.emit(struct.pack('<I', frame))
        code.emit('4989cc4c8d6c2420')
        if count:
            code.emit('c78424'); code.emit(struct.pack('<II', event_counter, 0))
        for name, offset in work.items():
            if adapter is not None and name not in adapter['inputs']:
                code.emit('b8'); code.emit(struct.pack('<I', int(variables[name]['initial']) & 65535))
            else:
                code.emit('410fb78424'); code.emit(struct.pack('<I', offsets[name]))
            code.emit('66418985'); code.emit(struct.pack('<I', offset))
        lower = _Lower(code, variables, work, 'r13', end, fail, pure=True,
                       events={'counter': event_counter, 'queue': event_queue} if count else None)
        lower.body(module['program']['body'], 'module')
        for name, offset in work.items():
            if adapter is not None and name not in adapter['outputs']:
                continue
            code.emit('410fb785'); code.emit(struct.pack('<I', offset))
            code.emit('6641898424'); code.emit(struct.pack('<I', offsets[name]))
        if count:
            # State and ordered notifications are admitted only after all pure
            # qualification/range checks pass. No notification is emitted on
            # those failures. Service failure after commit is explicit status3.
            again, done = code.fresh(), code.fresh()
            code.emit('c78424'); code.emit(struct.pack('<II', event_index, 0)); code.mark(again)
            code.emit('8b8424'); code.emit(struct.pack('<I', event_index))
            code.emit('3b8424'); code.emit(struct.pack('<I', event_counter)); code.relative('0f83', done)
            code.emit('488b94c4'); code.emit(struct.pack('<I', event_queue))
            code.emit('4c89e1'); code.relative('e8', 'module:' + module['notification_binding'] + ':text')
            code.emit('85d2'); code.relative('0f85', fail + ':status')
            code.emit('ff8424'); code.emit(struct.pack('<I', event_index)); code.relative('e9', again); code.mark(done)
        lower.value({'var': module['return']} if module.get('return') else 0)
        code.emit('0fb7c031d2'); code.relative('e9', end)
        code.mark(fail); code.emit('31c0ba01000000')
        code.mark(fail + ':status')
        code.mark(end); code.emit('4881c4'); code.emit(struct.pack('<I', frame)); code.emit('415d415cc3')
        return
    chosen = code.fresh()
    for key, resource in sorted(module['messages'].items(), key=lambda pair: int(pair[0])):
        following = code.fresh()
        code.emit('81fa'); code.emit(struct.pack('<I', int(key))); code.relative('0f85', following)
        code.relative('488d15', 'resource:' + resource); code.relative('e9', chosen); code.mark(following)
    code.relative('488d15', 'resource:' + module['default']); code.mark(chosen)
    code.relative('e9', code.prefix + ':text')
    _check(len(code.data) <= SLOT // 2, 'native notification selector exceeds fixed entry partition')
    code.emit(b'\xcc' * (SLOT // 2 - len(code.data)))
    code.mark(code.prefix + ':text'); code.emit('4883ec28')
    if module['backend'] == 'message-box-a':
        code.emit('31c9'); code.relative('4c8d05', 'title:' + code.prefix.removeprefix('module:'))
        code.emit('41b9'); code.emit(struct.pack('<I', module.get('style', 0)))
        code.relative('ff15', 'iat:MessageBoxA')
        code.emit('85c00f94c20fb6d28d1452')  # EDX=3 on API failure, else0.
    else:
        code.emit('4889d1'); code.relative('ff15', 'iat:OutputDebugStringA'); code.emit('31c0')
        code.emit('31d2')
    code.emit('4883c428c3')


def _imports(rva):
    """Fixed imports and offsets for every provider selection."""
    blob = bytearray(SLOT)
    lookups, iats, names = {}, {}, {}
    cursor = 64
    groups = [('KERNEL32.dll', ['ExitProcess', 'OutputDebugStringA']), ('USER32.dll', ['MessageBoxA'])]
    for dll, functions in groups:
        lookups[dll] = cursor; cursor += (len(functions) + 1) * 8
    iat_start = cursor
    for dll, functions in groups:
        iats[dll] = cursor; cursor += (len(functions) + 1) * 8
    iat_size = cursor - iat_start
    symbols = {}
    for index, (dll, functions) in enumerate(groups):
        dll_offset = cursor; raw = dll.encode() + b'\0'; blob[cursor:cursor + len(raw)] = raw; cursor += len(raw)
        struct.pack_into('<IIIII', blob, index * 20, rva + lookups[dll], 0, 0, rva + dll_offset, rva + iats[dll])
        for number, name in enumerate(functions):
            cursor = _align(cursor, 2); names[name] = cursor
            raw = b'\0\0' + name.encode() + b'\0'; blob[cursor:cursor + len(raw)] = raw; cursor += len(raw)
            struct.pack_into('<Q', blob, lookups[dll] + number * 8, rva + names[name])
            struct.pack_into('<Q', blob, iats[dll] + number * 8, rva + names[name])
            symbols['iat:' + name] = rva + iats[dll] + number * 8
    return blob, symbols, (rva, 60), (rva + iat_start, iat_size)


def _exports(rva, symbols):
    blob = bytearray(SLOT); entries = sorted(symbols.items()); count = len(entries)
    addresses, names, ordinals = 40, 40 + 4 * count, 40 + 8 * count
    cursor = 40 + 10 * count
    library = cursor; raw = b'udc-shell.exe\0'; blob[cursor:cursor + len(raw)] = raw; cursor += len(raw)
    for index, (name, address) in enumerate(entries):
        raw = name.encode() + b'\0'; _check(cursor + len(raw) <= SLOT, 'native export budget exceeded')
        struct.pack_into('<I', blob, addresses + index * 4, address)
        struct.pack_into('<I', blob, names + index * 4, rva + cursor)
        struct.pack_into('<H', blob, ordinals + index * 2, index)
        blob[cursor:cursor + len(raw)] = raw; cursor += len(raw)
    struct.pack_into('<IIHHIIIIIII', blob, 0, 0, 0, 0, 0, rva + library, 1, count, count,
                     rva + addresses, rva + names, rva + ordinals)
    return blob


def build_windows_shell(plan, modules, destination, *, c_compiler=None):
    """Emit a new private native PE32+ and a content-bound build capsule.

    ``modules`` maps stable logical binding names to selected implementations.
    IL bindings accept existing fdisbull-il-1 programs plus an optional
    return-cell and notification_binding. An explicit state_adapter isolates
    function locals: copy inputs, initialize noninputs, commit outputs only.
    Without an adapter the program is a persistent state block.
    IL text events are queued privately,
    then flushed after qualification; graphics/audio/input events refuse.
    Services are message-box-a or debug-string-a providers.
    Native ABI: RCX=arena, EAX=raw u16 result, EDX=status0/1/2/3. The arena uses
    word carriers for u8/u16/i16/bool; IL work copies make require/set failures
    atomic. Calls are acyclic, loops bounded, notification services synchronous.
    This profile has no exception unwinding, callbacks, recursion or file/media
    services. Changing a provider does not change other fixed code/data slots.
    ``destination`` must be a new directory; originals are never overwritten.
    """
    plan, modules = deepcopy(plan), deepcopy(modules)
    _validate(plan, modules)
    destination = Path(destination).expanduser().resolve()
    _check(not destination.exists(), 'native shell destination must be new')
    _check(not any((parent / '.git').exists() for parent in (destination, *destination.parents)),
           'native shell output must remain outside Git')
    from .udc_c import compile_c
    c_modules={name:compile_c(module,c_compiler) for name,module in modules.items() if module['backend']=='c-uil'}
    functions, bindings, resources = sorted(plan['functions']), sorted(modules), sorted(plan['resources'])
    cells = sorted(plan['state']); offsets = {name: 2 * index for index, name in enumerate(cells)}
    symbols = {'entry': 0x1000}
    slot_names = ['entry'] + ['fn:' + name for name in functions] + ['module:' + name for name in bindings]
    symbols.update({name: 0x1000 + index * SLOT for index, name in enumerate(slot_names)})
    symbols.update({'module:' + name + ':text': symbols['module:' + name] + SLOT // 2
                    for name in bindings if modules[name]['backend'] not in ('uil','c-uil')})
    text_size = len(slot_names) * SLOT
    rdata_rva = 0x1000 + text_size
    rdata_size = (2 + len(resources) + len(bindings)) * SLOT
    state_rva = rdata_rva + rdata_size
    symbols['state'] = state_rva
    imports, import_symbols, import_dir, iat_dir = _imports(rdata_rva); symbols.update(import_symbols)
    rdata = bytearray(rdata_size); rdata[:SLOT] = imports
    for index, name in enumerate(resources):
        offset = (1 + index) * SLOT; raw = _text(plan['resources'][name]['text'])
        rdata[offset:offset + len(raw)] = raw; symbols['resource:' + name] = rdata_rva + offset
    for index, name in enumerate(bindings):
        offset = (1 + len(resources) + index) * SLOT; raw = _text(modules[name].get('title', ''))
        rdata[offset:offset + len(raw)] = raw; symbols['title:' + name] = rdata_rva + offset
    exports = {'shell_entry': symbols['entry'], 'shell_state': state_rva}
    exports.update({'shell_function_' + str(i): symbols['fn:' + name] for i, name in enumerate(functions)})
    exports.update({'shell_binding_' + str(i): symbols['module:' + name] for i, name in enumerate(bindings)})
    export_rva = rdata_rva + rdata_size - SLOT
    rdata[-SLOT:] = _exports(export_rva, exports)
    codes = []
    code = _Code(symbols['entry'], 'entry')
    code.emit('41544883ec20'); code.relative('4c8d25', 'state'); code.emit('4c89e1')
    code.relative('e8', 'fn:' + plan['entry']); code.emit('89d1'); code.relative('ff15', 'iat:ExitProcess'); code.emit('cc')
    codes.append(code)
    for name in functions:
        code = _Code(symbols['fn:' + name], 'fn:' + name)
        end, fail = code.fresh(), code.fresh()
        code.emit('41544881ec'); code.emit(struct.pack('<I', 96)); code.emit('4989cc')
        lower = _Lower(code, plan['state'], offsets, 'r12', end, fail)
        lower.body(plan['functions'][name]['body'], 'function.' + name)
        lower.value(plan['functions'][name].get('return', 0)); code.emit('0fb7c031d2'); code.relative('e9', end)
        code.mark(fail); code.emit('ba01000000'); code.mark(fail + ':status'); code.emit('31c0')
        code.mark(end); code.emit('4881c4'); code.emit(struct.pack('<I', 96)); code.emit('415cc3')
        codes.append(code)
    for name in bindings:
        code = _Code(symbols['module:' + name], 'module:' + name)
        if name in c_modules:
            from .udc_c import lower_c_module
            lower_c_module(code,modules[name],plan['state'],offsets,c_modules[name])
        else:_module(code, modules[name], plan['state'], offsets)
        codes.append(code)
    text = b''.join(code.resolve(symbols) for code in codes)
    state = b''.join(struct.pack('<H', int(plan['state'][name]['initial']) & 65535) for name in cells)
    data = state + bytes(max(512, _align(len(state), 512)) - len(state))
    header = bytearray(512); header[:2] = b'MZ'; struct.pack_into('<I', header, 0x3C, 0x80)
    header[0x80:0x84] = b'PE\0\0'; struct.pack_into('<HHIIIHH', header, 0x84, 0x8664, 3, 0, 0, 0, 240, 0x23)
    opt = 0x98
    struct.pack_into('<HBBIII', header, opt, 0x20B, 1, 0, len(text), len(rdata) + len(data), 0)
    struct.pack_into('<IIQII', header, opt + 16, 0x1000, 0x1000, BASE, 4096, 512)
    struct.pack_into('<HHHHHH', header, opt + 40, 6, 0, 0, 0, 6, 0)
    struct.pack_into('<IIIHH', header, opt + 56, _align(state_rva + len(data), 4096), 512, 0, 2, 0x100)
    struct.pack_into('<QQQQII', header, opt + 72, 1 << 20, 4096, 1 << 20, 4096, 0, 16)
    struct.pack_into('<II', header, opt + 112, export_rva, SLOT)
    struct.pack_into('<II', header, opt + 120, *import_dir)
    struct.pack_into('<II', header, opt + 112 + 12 * 8, *iat_dir)
    file_offset = 512
    for index, (name, payload, rva, flags) in enumerate((
            (b'.text', text, 0x1000, 0x60000020),
            (b'.idata', rdata, rdata_rva, 0xC0000040),
            (b'.data', data, state_rva, 0xC0000040))):
        at = opt + 240 + index * 40; header[at:at + len(name)] = name
        struct.pack_into('<IIII', header, at + 8, len(payload), rva, len(payload), file_offset)
        struct.pack_into('<I', header, at + 36, flags); file_offset += len(payload)
    image = bytes(header) + text + bytes(rdata) + data
    manifest = {'format': 'fdisbull-native-shell-build-1', 'profile': PROFILE,
                'plan_sha256': _sha(_json(plan)), 'modules_sha256': _sha(_json(modules)), 'c_modules': c_modules,
                'target': {'format': 'PE32+', 'arch': 'x86-64', 'image_base': hex(BASE),
                           'load_profile': 'fixed preferred base; no exception-unwind profile',
                           'original_binary_wrapped': False},
                'output': {'path': 'program.exe', 'sha256': _sha(image), 'size': len(image)},
                'abi': {'arena': 'RCX', 'result_u16': 'EAX', 'status': 'EDX',
                        'statuses': {'0': 'success', '1': 'qualification-or-range-failure', '2': 'loop-budget-exhausted',
                                     '3': 'notification-failed-after-state-commit'},
                        'calls': 'Win64 nonvolatile preservation and 32-byte shadow space'},
                'state': {name: {'rva': state_rva + offsets[name], 'carrier_bits': 16, **plan['state'][name]} for name in cells},
                'slots': {code.prefix: {'rva': code.base, 'file_offset': 512 + code.base - 0x1000,
                          'size': SLOT, 'sha256': _sha(text[code.base - 0x1000:code.base - 0x1000 + SLOT]),
                          'used_bytes': len(code.data), 'source_map': code.maps} for code in codes},
                'resources': {name: {'rva': symbols['resource:' + name], 'size': SLOT} for name in resources},
                'provider_data': {name: {'rva': symbols['title:' + name], 'size': SLOT} for name in bindings},
                'bindings': {name: {'backend': modules[name]['backend'], 'entry_rva': symbols['module:' + name],
                                    **({'text_entry_rva': symbols['module:' + name + ':text']}
                                       if modules[name]['backend'] not in ('uil','c-uil') else {})}
                             for name in bindings},
                'exports': exports, 'imports': ['KERNEL32.dll!ExitProcess', 'KERNEL32.dll!OutputDebugStringA', 'USER32.dll!MessageBoxA'],
                'qualification': {'native_execution': False, 'source_to_uil': False,
                                  'scope': 'bounded authored native realization; provider effects explicit; no exception/reentrant/recursive profile'}}
    capsule = {'format': 'fdisbull-native-shell-capsule-1', 'plan': plan, 'modules': modules, 'build': manifest}
    # Validate everything and finish lowering before creating any output.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    owned = destination.stat()
    owned_files = {}
    try:
        for name, payload in [('program.exe', image), ('capsule.json', _json(capsule) + b'\n')]:
            path = destination / name
            with path.open('xb') as stream:
                stat = os.fstat(stream.fileno())
                owned_files[name] = (stat.st_dev, stat.st_ino)
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.chmod(path, 0o600)
    except BaseException:
        _remove_owned_output(destination, (owned.st_dev, owned.st_ino), owned_files)
        raise
    return {**manifest, 'directory': str(destination), 'capsule': str(destination / 'capsule.json')}
