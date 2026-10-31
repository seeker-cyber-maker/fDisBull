"""Versioned, bounded procedural UIL for source-bound console game profiles.

C89 is an authoring notation, not an opaque payload in this format.  The
export contains an inspectable syntax tree, typed declarations, procedure
bodies and hash-bound external regions.  Replay walks that tree; native
compilation regenerates C from the same tree.  The integer model deliberately
uses the cc65 ABI (16-bit int, 32-bit long), rather than the host Python/C ABI.

This profile is separate from the small, proved UIL-v1 block contract.
It does not turn an arbitrary C program or cartridge into a recovered game.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable

FORMAT = 'fdisbull-game-il-2'
MAX_NODES = 100_000
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_ARRAY = 65536
MAX_STEPS = 2_000_000
MAX_LOOP = 65536
BUILTINS = {'rom8', 'rom16', 'rom32', 'emit', 'sound_busy', 'hv16'}
NODES = frozenset(('FileAST FuncDef Decl TypeDecl IdentifierType FuncDecl '
    'ParamList ArrayDecl Constant ID BinaryOp UnaryOp Cast Typename Assignment '
    'Compound If For Return FuncCall ExprList EmptyStatement Break Continue '
    'DeclList Enum EnumeratorList Enumerator Typedef InitList ArrayRef').split())
TYPES = {'u8': (8, False), 'i8': (8, True), 'u16': (16, False),
         'i16': (16, True), 'u32': (32, False), 'i32': (32, True),
         'unsigned char': (8, False), 'signed char': (8, True), 'char': (8, False),
         'unsigned short': (16, False), 'short': (16, True),
         'unsigned int': (16, False), 'int': (16, True),
         'unsigned long': (32, False), 'long': (32, True), 'void': (0, False)}


def _parser():
    try:
        from pycparser import c_ast, c_generator, c_parser
    except ImportError as exc:
        raise ValueError('Procedural UIL requires the console extra: fdisbull[console]') from exc
    return c_ast, c_generator, c_parser


def _encode(node):
    if node is None or isinstance(node, (str, int, bool)):
        return node
    if isinstance(node, (list, tuple)):
        return [_encode(x) for x in node]
    name = type(node).__name__
    if name not in NODES:
        raise ValueError(f'Unsupported procedural UIL operation: {name}')
    result = {'node': name}
    for key in node.__slots__:
        if key not in ('coord', '__weakref__'):
            result[key] = _encode(getattr(node, key))
    return result


def _decode(value, depth=0, budget=None):
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0 or depth > 256:
        raise ValueError('Procedural UIL tree exceeds its size/depth limit')
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_decode(x, depth + 1, budget) for x in value]
    if not isinstance(value, dict) or value.get('node') not in NODES:
        raise ValueError('Invalid procedural UIL node')
    c_ast, _, _ = _parser()
    cls = getattr(c_ast, value['node'])
    allowed = set(cls.__slots__) - {'coord', '__weakref__'}
    if set(value) - {'node'} != allowed:
        raise ValueError(f'Invalid fields for {value["node"]}')
    return cls(**{key: _decode(value[key], depth + 1, budget) for key in allowed})


def canonical(program):
    return json.dumps(program, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def author_program(source: str, regions=(), *, evidence=None):
    """Parse the restricted authoring notation into a data-only UIL document."""
    _, _, parser = _parser()
    # pycparser intentionally does not run a preprocessor.  No includes or
    # macros can introduce host-dependent declarations or hidden behavior.
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    tree = parser.CParser().parse(clean)
    result = {'format': FORMAT, 'integer_model': 'cc65-int16-long32',
              'tree': _encode(tree), 'regions': list(regions),
              'evidence': evidence or {}}
    validate_program(result)
    return result


def validate_program(program):
    if not isinstance(program, dict) or program.get('format') != FORMAT:
        raise ValueError('Expected fdisbull-game-il-2')
    if program.get('integer_model') != 'cc65-int16-long32':
        raise ValueError('Unsupported procedural UIL integer model')
    if len(canonical(program)) > MAX_DOCUMENT_BYTES:
        raise ValueError('Procedural UIL document is too large')
    tree = _decode(program.get('tree'))
    if type(tree).__name__ != 'FileAST':
        raise ValueError('Procedural UIL root must be a translation unit')
    seen = set()
    for region in program.get('regions', []):
        if (not isinstance(region, dict) or not isinstance(region.get('id'), int)
                or not 0 <= region['id'] <= 255 or region['id'] in seen
                or not isinstance(region.get('length'), int)
                or not 0 < region['length'] <= 16 * 1024 * 1024
                or not re.fullmatch('[0-9a-f]{64}', region.get('sha256', ''))):
            raise ValueError('Invalid or duplicate immutable region binding')
        seen.add(region['id'])
    funcs = {x.decl.name: x for x in tree.ext if type(x).__name__ == 'FuncDef'}
    if len(funcs) > 512:
        raise ValueError('Too many procedural UIL procedures')
    calls = {name: set() for name in funcs}
    def visit(node, owner=None, block_depth=0):
        kind = type(node).__name__
        if kind == 'Compound': block_depth += 1
        if kind == 'Decl' and owner is not None and block_depth > 1:
            raise ValueError('UIL procedure locals must be declared at the top of the procedure')
        if kind == 'Decl' and owner is not None and block_depth > 0 and {'static', 'extern'}.intersection(node.storage):
            raise ValueError('UIL procedure-local static/extern storage is not supported')
        if kind == 'For' and node.init is not None and type(node.init).__name__ == 'DeclList':
            raise ValueError('UIL loop counters must be declared at procedure scope')
        if kind in ('ID', 'Decl', 'Typedef', 'Enumerator'):
            name = node.name
            if name is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                raise ValueError('Invalid UIL identifier')
        if kind == 'IdentifierType' and any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', x) for x in node.names):
            raise ValueError('Invalid UIL type name')
        if kind == 'Constant':
            if node.type == 'char':
                if not re.fullmatch(r"'(?:[^'\\\n]|\\[0-7]{1,3}|\\x[0-9a-fA-F]{1,2}|\\[\\'\"abfnrtv])'", node.value):
                    raise ValueError('Invalid UIL character literal')
            elif not re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)[uUlL]*', node.value):
                raise ValueError('Invalid UIL integer literal')
        if kind == 'BinaryOp' and node.op not in ('+', '-', '*', '/', '%', '<<', '>>', '<', '<=', '>', '>=', '==', '!=', '&', '|', '^', '&&', '||'):
            raise ValueError('Invalid UIL binary operator')
        if kind == 'Assignment' and node.op not in ('=', '+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^='):
            raise ValueError('Invalid UIL assignment operator')
        if kind in ('Decl', 'Typename', 'TypeDecl', 'ArrayDecl'):
            for field, choices in (('quals', {'const', 'volatile'}), ('dim_quals', set()),
                                   ('storage', {'extern', 'static', 'auto', 'register'}), ('funcspec', set())):
                if any(x not in choices for x in getattr(node, field, [])):
                    raise ValueError('Unsupported UIL declaration qualifier')
        if type(node).__name__ == 'FuncCall':
            if type(node.name).__name__ != 'ID':
                raise ValueError('Indirect calls are not supported')
            name = node.name.name
            if name not in funcs and name not in BUILTINS:
                raise ValueError(f'Unknown procedural UIL call: {name}')
            if owner is not None and name in funcs:
                calls[owner].add(name)
        if type(node).__name__ == 'UnaryOp' and node.op not in ('+', '-', '~', '!', 'p++', 'p--', '++', '--'):
            raise ValueError(f'Unsupported unary operation: {node.op}')
        if type(node).__name__ == 'Decl' and node.bitsize is not None:
            raise ValueError('Bit fields are not supported')
        for _, child in node.children():
            visit(child, owner, block_depth)
    for ext in tree.ext:
        visit(ext, ext.decl.name if type(ext).__name__ == 'FuncDef' else None)
    active, done = set(), set()
    def acyclic(name):
        if name in active:
            raise ValueError('Recursive UIL procedures are not supported')
        if name in done:
            return
        active.add(name)
        for dep in calls[name]:
            acyclic(dep)
        active.remove(name)
        done.add(name)
    for name in funcs:
        acyclic(name)
    # Build storage as part of validation, catching unknown types, duplicate
    # declarations, oversized arrays and invalid initializers before execution.
    GameMachine(program, _validated_tree=tree, _validate_only=True)
    return tree


def emit_c(program):
    tree = validate_program(program)
    _, generator, _ = _parser()
    return generator.CGenerator().visit(tree) + '\n'


@dataclass(frozen=True)
class Value:
    number: int
    bits: int = 16
    signed: bool = True

    def cast(self, typ):
        bits, signed = typ
        if bits == 0:
            return Value(0, 0, False)
        n = self.number & ((1 << bits) - 1)
        if signed and n >= 1 << (bits - 1):
            n -= 1 << bits
        return Value(n, bits, signed)


def _promote(value):
    return value.cast((16, True)) if value.bits < 16 else value


def _common(left, right):
    left, right = _promote(left), _promote(right)
    bits = max(left.bits, right.bits)
    signed = (left.signed and right.signed) if left.bits == right.bits else (
        left.signed if left.bits > right.bits else right.signed)
    # A signed wider type represents every value of a narrower unsigned type.
    typ = (bits, signed)
    return left.cast(typ), right.cast(typ), typ


class _Return(Exception):
    def __init__(self, value): self.value = value
class _Break(Exception): pass
class _Continue(Exception): pass


class GameMachine:
    """Bounded reference executor with checked storage and immutable ROM reads.

    Each public call is transactional, including events and environmental read
    cursors.  Native game adapters additionally expose faults/epochs; the small
    UIL-v1 Z3 proof does not extend to this procedural profile.
    """
    def __init__(self, program, regions=None, *, environment=None,
                 _validated_tree=None, _validate_only=False):
        self.program = program
        tree = _validated_tree if _validated_tree is not None else validate_program(program)
        self.types = dict(TYPES)
        self.constants = {}
        self.globals = {}
        self.global_types = {}
        self.functions = {}
        self.frames = []
        self.events = []
        self.regions = dict(regions or {})
        self.environment = environment or {}
        self.environment_cursor = {}
        self.steps = 0
        self.step_limit = MAX_STEPS
        for node in tree.ext:
            kind = type(node).__name__
            if kind == 'Typedef':
                self.types[node.name] = self._type(node.type)
            elif kind == 'FuncDef':
                self.functions[node.decl.name] = node
            elif kind == 'Decl':
                if type(node.type).__name__ == 'FuncDecl':
                    continue
                if node.name is None:
                    self._enum(node.type)
                else:
                    if node.init is not None:
                        def constant_initializer(item):
                            if type(item).__name__ not in ('Constant', 'InitList', 'BinaryOp', 'UnaryOp', 'Cast', 'Typename', 'TypeDecl', 'IdentifierType', 'ID'):
                                raise ValueError('Global UIL initializers must be constant expressions')
                            for _, child in item.children(): constant_initializer(child)
                        constant_initializer(node.init)
                    self._declare(node, self.globals, self.global_types)
            else:
                raise ValueError(f'Unsupported global declaration: {kind}')
        if not _validate_only:
            for binding in program.get('regions', []):
                raw = self.regions.get(binding['id'])
                if raw is None or len(raw) != binding['length'] or hashlib.sha256(raw).hexdigest() != binding['sha256']:
                    raise ValueError(f'Immutable region {binding["id"]} does not match its UIL binding')

    def _type(self, node):
        kind = type(node).__name__
        if kind in ('TypeDecl', 'Typename'):
            return self._type(node.type)
        if kind == 'IdentifierType':
            name = ' '.join(node.names)
            name = {'signed short': 'short', 'signed int': 'int', 'signed long': 'long', 'short int': 'short', 'long int': 'long', 'unsigned short int': 'unsigned short', 'unsigned long int': 'unsigned long'}.get(name, name)
            if name not in self.types:
                raise ValueError(f'Unknown UIL scalar type: {name}')
            return self.types[name]
        if kind == 'Enum': return (16, True)
        raise ValueError(f'Unsupported UIL storage type: {kind}')

    def _enum(self, node):
        if type(node).__name__ == 'TypeDecl': node = node.type
        if type(node).__name__ != 'Enum' or node.values is None:
            raise ValueError('Expected a scalar declaration or enumeration')
        next_value = 0
        for entry in node.values.enumerators:
            if entry.value is not None: next_value = self._expr(entry.value).number
            self.constants[entry.name] = Value(next_value)
            next_value += 1

    def _declare(self, node, values, types):
        if node.name in values:
            raise ValueError(f'Duplicate UIL declaration: {node.name}')
        if type(node.type).__name__ == 'ArrayDecl':
            element = self._type(node.type.type)
            size = self._expr(node.type.dim).number
            if not 1 <= size <= MAX_ARRAY:
                raise ValueError('UIL array length is outside the permitted range')
            types[node.name] = (element, size)
            values[node.name] = [Value(0).cast(element) for _ in range(size)]
            if node.init is not None:
                if type(node.init).__name__ != 'InitList' or len(node.init.exprs) > size:
                    raise ValueError('Invalid UIL array initializer')
                for i, expr in enumerate(node.init.exprs):
                    values[node.name][i] = self._expr(expr).cast(element)
        else:
            typ = self._type(node.type)
            types[node.name] = typ
            values[node.name] = (self._expr(node.init) if node.init else Value(0)).cast(typ)

    def _storage(self, name):
        if self.frames and name in self.frames[-1][0]: return self.frames[-1]
        if name in self.globals: return self.globals, self.global_types
        raise ValueError(f'Unknown UIL variable: {name}')

    def _tick(self):
        self.steps += 1
        if self.steps > self.step_limit:
            raise ValueError('UIL execution exhausted its operation budget')

    def _ref(self, node):
        if type(node).__name__ == 'ID':
            values, types = self._storage(node.name)
            if isinstance(values[node.name], list): raise ValueError('Array requires an index')
            return values, node.name, types[node.name]
        if type(node).__name__ == 'ArrayRef':
            if type(node.name).__name__ != 'ID': raise ValueError('Only flat arrays are supported')
            values, types = self._storage(node.name.name)
            array = values[node.name.name]
            typ, length = types[node.name.name]
            index = self._expr(node.subscript).number
            if not 0 <= index < length: raise ValueError(f'UIL array index out of bounds: {node.name.name}[{index}]')
            return array, index, typ
        raise ValueError('Invalid UIL assignment target')

    def _expr(self, node):
        self._tick()
        kind = type(node).__name__
        if kind == 'Constant':
            if node.type == 'char':
                import ast
                text = ast.literal_eval(node.value)
                if len(text) != 1: raise ValueError('Multibyte character literals are unsupported')
                return Value(ord(text))
            if node.type not in ('int', 'unsigned int', 'long int', 'unsigned long int'):
                raise ValueError('Only integer literals are supported')
            raw = node.value.lower()
            suffix = re.search('[ul]*$', raw).group()
            body = raw[:-len(suffix)] if suffix else raw
            number = int(body, 16 if body.startswith('0x') else 8 if body.startswith('0') and body != '0' else 10)
            if 'l' in suffix: typ = (32, 'u' not in suffix and number <= 0x7fffffff)
            elif 'u' in suffix: typ = (16 if number <= 65535 else 32, False)
            elif number <= 32767: typ = (16, True)
            elif body.startswith('0') and number <= 65535: typ = (16, False)
            elif number <= 0x7fffffff: typ = (32, True)
            else: typ = (32, False)
            return Value(number).cast(typ)
        if kind == 'ID':
            if node.name in self.constants: return self.constants[node.name]
            values, _ = self._storage(node.name)
            result = values[node.name]
            if not isinstance(result, Value): raise ValueError('Array requires an index')
            return result
        if kind == 'ArrayRef':
            values, key, _ = self._ref(node)
            return values[key]
        if kind == 'Cast': return self._expr(node.expr).cast(self._type(node.to_type))
        if kind == 'FuncCall':
            args = [self._expr(x) for x in node.args.exprs] if node.args else []
            return self._call(node.name.name, args)
        if kind == 'BinaryOp':
            left = self._expr(node.left)
            if node.op == '&&' and not left.number: return Value(0)
            if node.op == '||' and left.number: return Value(1)
            right = self._expr(node.right)
            if node.op in ('<<', '>>'):
                left, right = _promote(left), _promote(right)
                if not 0 <= right.number < left.bits: raise ValueError('Invalid UIL shift count')
                return Value(left.number << right.number if node.op == '<<' else left.number >> right.number).cast((left.bits, left.signed))
            left, right, typ = _common(left, right)
            a, b = left.number, right.number
            if node.op in ('==', '!=', '<', '<=', '>', '>=', '&&', '||'):
                result = {'==': a == b, '!=': a != b, '<': a < b, '<=': a <= b,
                          '>': a > b, '>=': a >= b, '&&': bool(a and b), '||': bool(a or b)}[node.op]
                return Value(int(result))
            if node.op in ('/', '%'):
                if b == 0: raise ValueError('UIL division by zero')
                q = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
                return Value(q if node.op == '/' else a - q * b).cast(typ)
            result = {'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b,
                      '&': lambda: a & b, '|': lambda: a | b, '^': lambda: a ^ b}.get(node.op)
            if result is None: raise ValueError(f'Unsupported UIL binary operation {node.op}')
            return Value(result()).cast(typ)
        if kind == 'UnaryOp':
            if node.op in ('++', '--', 'p++', 'p--'):
                # Resolving an array lvalue may itself have effects (for
                # example data[index++]++).  Resolve it once, then read and
                # update that same cell rather than reevaluating its index.
                values, key, typ = self._ref(node.expr)
                old = values[key]
                values[key] = Value(old.number + (1 if '+' in node.op else -1)).cast(typ)
                return old if node.op.startswith('p') else values[key]
            value = _promote(self._expr(node.expr))
            if node.op == '!': return Value(int(not value.number))
            result = {'+': lambda: value.number, '-': lambda: -value.number, '~': lambda: ~value.number}[node.op]()
            return Value(result).cast((value.bits, value.signed))
        if kind == 'TernaryOp':
            return self._expr(node.iftrue if self._expr(node.cond).number else node.iffalse)
        raise ValueError(f'Unsupported UIL expression: {kind}')

    def _stmt(self, node):
        if node is None: return
        self._tick()
        kind = type(node).__name__
        if kind in ('Compound', 'DeclList'):
            for child in (node.block_items if kind == 'Compound' else node.decls) or []: self._stmt(child)
        elif kind == 'Decl':
            self._declare(node, *self.frames[-1])
        elif kind == 'Assignment':
            values, key, typ = self._ref(node.lvalue)
            value = self._expr(node.rvalue)
            if node.op != '=':
                left, right, common = _common(values[key], value)
                op = node.op[:-1]
                # Evaluate a small equivalent expression using already-frozen values.
                a, b = left.number, right.number
                if op in ('<<', '>>'):
                    if not 0 <= b < left.bits: raise ValueError('Invalid UIL shift count')
                    n = a << b if op == '<<' else a >> b
                elif op in ('/', '%'):
                    if b == 0: raise ValueError('UIL division by zero')
                    q = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
                    n = q if op == '/' else a - q * b
                else:
                    n = {'+': lambda: a+b, '-': lambda: a-b, '*': lambda: a*b,
                         '&': lambda: a&b, '|': lambda: a|b, '^': lambda: a^b}[op]()
                value = Value(n).cast(common)
            values[key] = value.cast(typ)
        elif kind == 'If':
            self._stmt(node.iftrue if self._expr(node.cond).number else node.iffalse)
        elif kind == 'For':
            self._stmt(node.init)
            for _ in range(MAX_LOOP):
                if node.cond is not None and not self._expr(node.cond).number: break
                try: self._stmt(node.stmt)
                except _Continue: pass
                except _Break: break
                self._stmt(node.next)
            else: raise ValueError('UIL loop exhausted its iteration budget')
        elif kind == 'Return':
            raise _Return(self._expr(node.expr) if node.expr else Value(0, 0, False))
        elif kind == 'Break': raise _Break()
        elif kind == 'Continue': raise _Continue()
        elif kind == 'EmptyStatement': pass
        elif kind in ('FuncCall', 'UnaryOp'): self._expr(node)
        elif kind == 'ExprList':
            for child in node.exprs: self._stmt(child)
        else: raise ValueError(f'Unsupported UIL statement: {kind}')

    def _call(self, name, args):
        self._tick()
        if name in BUILTINS:
            nums = [x.number for x in args]
            if name.startswith('rom'):
                if len(nums) != 2: raise ValueError('ROM read expects region and byte offset')
                raw = self.regions.get(nums[0], b'')
                width = int(name[3:]) // 8
                if not 0 <= nums[1] <= len(raw) - width: raise ValueError('UIL immutable region read out of bounds')
                return Value(int.from_bytes(raw[nums[1]:nums[1]+width], 'big')).cast((width*8, False))
            if name == 'emit':
                if len(nums) != 2 or len(self.events) >= 4096: raise ValueError('Invalid or overflowing UIL event queue')
                self.events.append({'kind': nums[0] & 255, 'id': nums[1] & 255})
                return Value(0, 0, False)
            if nums: raise ValueError(f'{name} expects no arguments')
            position = self.environment_cursor.get(name, 0)
            samples = self.environment.get(name, [0])
            if isinstance(samples, Callable):
                raise ValueError('Use serializable environmental samples, not host callbacks')
            if not samples: raise ValueError(f'Missing environmental sample: {name}')
            self.environment_cursor[name] = position + 1
            # A singleton explicitly declares a constant input adapter.  Longer
            # recordings are finite and cannot silently wrap or fabricate reads.
            if len(samples) != 1 and position >= len(samples): raise ValueError(f'Environmental recording exhausted: {name}')
            return Value(samples[0] if len(samples) == 1 else samples[position]).cast((16 if name == 'hv16' else 8, False))
        function = self.functions.get(name)
        if function is None: raise ValueError(f'Unknown UIL procedure: {name}')
        params = function.decl.type.args.params if function.decl.type.args else []
        if len(params) == 1 and type(params[0]).__name__ == 'Typename' and self._type(params[0]) == (0, False): params = []
        if len(params) != len(args): raise ValueError(f'UIL procedure arity mismatch: {name}')
        if len(self.frames) >= 128: raise ValueError('UIL call-depth budget exceeded')
        values, types = {}, {}
        for param, arg in zip(params, args):
            typ = self._type(param.type)
            values[param.name], types[param.name] = arg.cast(typ), typ
        self.frames.append((values, types))
        try:
            try:
                self._stmt(function.body)
                result = Value(0)
            except _Return as done:
                result = done.value
        finally: self.frames.pop()
        return result.cast(self._type(function.decl.type.type))

    def call(self, name, *args, max_steps=MAX_STEPS):
        backup = (copy.deepcopy(self.globals), list(self.events), dict(self.environment_cursor))
        self.steps, self.step_limit = 0, max_steps
        try:
            result = self._call(name, [Value(x, 32, True) for x in args])
        except Exception:
            self.globals, self.events, self.environment_cursor = backup
            raise
        return {'result': result.number, 'steps': self.steps, 'events': list(self.events)}

    def snapshot(self):
        return {name: [x.number for x in value] if isinstance(value, list) else value.number
                for name, value in self.globals.items()}

    def set_state(self, updates):
        for name, value in updates.items():
            if name not in self.globals: raise ValueError(f'Unknown UIL state variable: {name}')
            typ = self.global_types[name]
            if isinstance(self.globals[name], list):
                if not isinstance(value, list) or len(value) != typ[1]: raise ValueError('UIL array state length mismatch')
                self.globals[name] = [Value(x, 32).cast(typ[0]) for x in value]
            else: self.globals[name] = Value(value, 32).cast(typ)
