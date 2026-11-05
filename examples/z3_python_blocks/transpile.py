#!/usr/bin/env python3
"""Ahead-of-time Z-machine v3 -> Python functions, with media/state containers.

The existing decoder/lowerer is a build-time front end only. No UIL graph,
opcode evaluator, or code generator is loaded by the resulting application.
This is a mechanical, source-bound translation, not recovered game-intent UIL.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'text_asset_pilot'))
from asset_package import Package, canonical, pack, private_output, sha
import pilot
from fdisbull.zork_uil import compile_story
from fdisbull_player import word16

FORMAT = 'fdisbull-z3-python-code-1'
SHARD_BITS = 10


def service_source():
    """Retain support operations, not the reference graph interpreter.

    Extracting exact methods keeps parser/stream/persistence semantics reviewable.
    The resulting file has no reference-runtime import or generic evaluator.
    """
    source = Path(word16.__file__).read_text()
    tree = ast.parse(source)
    selected = []
    keep_functions = {'_integer', '_keys', '_hex', '_u16', '_s16',
                      '_bounded_integer', '_canonical', '_json_load', '_atomic_json'}
    constants = {'CHECKPOINT_FORMAT', 'MAX_CHECKPOINT_BYTES', 'MAX_TEXT',
                 'MAX_STACK', 'MAX_FRAMES', '_ALPHABETS', '_EXTRA'}
    removed = {'__init__', '_expr', '_nodes', '_library', 'run'}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in keep_functions:
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'Word16Error':
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'Word16Runtime':
            node.name = 'StateServices'
            node.body = [m for m in node.body if isinstance(m, ast.FunctionDef) and m.name not in removed]
            selected.append(node)
    class Rename(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == 'Word16Runtime': node.id = 'StateServices'
            return node
    tree = Rename().visit(ast.Module(body=selected, type_ignores=[]))
    ast.fix_missing_locations(tree)
    text = ast.unparse(tree) + '\n'
    assert not any(x in text for x in ('def _nodes(', 'def _expr(', 'def _library(', 'validate_program(', 'fdisbull_player'))
    return ('# Support methods mechanically retained from fDisBull player/word16.py.\n'
            '# Source SHA-256: ' + sha(source.encode()) + '\n'
            '# Parser, object layout, streams and state services remain source-specific.\n'
            + text)


class Emitter:
    """Translate admitted primitive nodes to ordinary Python statements."""
    def __init__(self):
        self.callbacks = 0
        self.temps = set()

    def expr(self, e):
        if type(e) in (int, bool, str): return repr(e)
        if set(e) == {'tmp'}: return 't_' + e['tmp']
        op, args = e['calc'], [self.expr(a) for a in e['args']]
        if op == 'eq': return f'({args[0]} == {args[1]})'
        if op == 'ne': return f'({args[0]} != {args[1]})'
        if op in ('mem8', 'mem16'): return f'm._read({args[0]}, {8 if op == "mem8" else 16})'
        names = {'u16': '_u16', 's16': '_s16', 'not': 'bool_not',
                 'any': 'bool_any', 'all': 'bool_all'}
        return f'{names.get(op, "calc_" + op)}(' + ', '.join(args) + ')'

    def statements(self, nodes, indent=1):
        result = []
        def add(line): result.append('    ' * indent + line)
        for n in nodes:
            op = n['op']
            ex = lambda k: self.expr(n[k])
            args = ', '.join(self.expr(e) for e in n.get('args', []))
            if op == 'let': add('t_' + n['name'] + ' = ' + ex('value'))
            elif op == 'read_var': add(f't_{n["dest"]} = m._read_var({ex("index")}, {n.get("indirect", False)!r})')
            elif op == 'write_var': add(f'm._write_var({ex("index")}, {ex("value")}, {n.get("indirect", False)!r})')
            elif op == 'write_mem': add(f'm._write({ex("address")}, {n["width"]}, {ex("value")})')
            elif op == 'push': add(f'm._push({ex("value")})')
            elif op == 'pop': add(f't_{n["dest"]} = m._pop()')
            elif op == 'if':
                add(f'if require_bool({ex("condition")}):')
                result += self.statements(n['then'], indent + 1) or ['    ' * (indent + 1) + 'pass']
                if n.get('else'):
                    add('else:')
                    result += self.statements(n['else'], indent + 1)
            elif op == 'goto': add(f'm._goto({ex("target")})'); add('return True')
            elif op == 'call':
                add(f'm.call_function({ex("target")}, [{args}], {n["store"]}, {n["resume"]})')
                add('return True')
            elif op == 'return': add(f'm._return({ex("value")})'); add('return True')
            elif op == 'emit': add(f'm._emit({ex("value")})')
            elif op == 'random': add(f't_{n["dest"]} = m._random({ex("range")})')
            elif op == 'library':
                target = n['name'].replace('.', '_')
                invocation = f'm.{target}({args})'
                add(f't_{n["dest"]} = {invocation}' if 'dest' in n else invocation)
            elif op == 'input':
                add(f'm.request_input({ex("text")}, {ex("parse")}, {n["resume"]})')
                add('return True')
            elif op == 'persist':
                name = f'persist_path_{self.callbacks}'
                self.callbacks += 1
                branch = 'success' if n['mode'] == 'save' else 'failure'
                add(f'def {name}():')
                if self.temps:
                    result.append('    ' * (indent + 1) + 'nonlocal ' + ', '.join('t_' + t for t in sorted(self.temps)))
                result += self.statements(n[branch], indent + 1)
                result.append('    ' * (indent + 1) + 'return False')
                add(f'm.{"save_path" if branch == "success" else "restore_path"}({name}, {n["resume"]})')
                add('return True')
            elif op == 'restart': add('m.restart_game()'); add('return True')
            elif op == 'quit': add('m.halted, m.halt_reason = True, "quit"'); add('return True')
            elif op == 'host': add(f'm._host({n["action"]!r}, [{args}])')
            else: raise ValueError('Unsupported node ' + op)
        return result

    def block(self, pc, block):
        self.temps = set()
        def walk(nodes):
            for n in nodes:
                if n['op'] == 'let': self.temps.add(n['name'])
                if 'dest' in n: self.temps.add(n['dest'])
                for key in ('then','else','success','failure'):
                    if key in n: walk(n[key])
        walk(block['nodes'])
        lines = [f'def block_{pc:05x}(m):',
                 f'    """Source-bound continuation 0x{pc:05x}; no opcode fetch."""',
                 f'    m.guard_code({pc}, {len(bytes.fromhex(block["guard"]))})']
        # Assignment establishes closure cells for SAVE/RESTORE branch callbacks.
        if any(n['op'] == 'persist' for n in block['nodes']) and self.temps:
            lines.append('    ' + ' = '.join('t_' + t for t in sorted(self.temps)) + ' = None')
        lines += self.statements(block['nodes'])
        lines += [f'    m._goto({block["next"]})', '    return False', '']
        return '\n'.join(lines)


def build(program, destination, *, source_check=None):
    word16.validate_program(program)
    root = private_output(destination)
    root.mkdir()
    # Reuse the previous text normalizer, not its runtime or IR interpreter.
    old, normalization = pilot.bundle_program(program)
    package = Package(old)
    entries = {}
    for asset, d in package.manifest['assets'].items():
        if d['kind'] == 'text' or asset == 'text.index':
            entries[asset] = (d['kind'], d['media_type'], package.get(asset), d['dependencies'], d['metadata'])
    media = pack({'id':'z3.media','entry':'text.index','requires':{}}, entries,
                 {'profile':'z3-python-media-1','source_sha256':program['source']['sha256']})
    initial = bytes.fromhex(program['memory']['initial'])
    boundary = program['memory']['writable_end']
    schema = {'format':'fdisbull-z3-memory-layout-1', 'source':program['source'],
              'writable_end':boundary, 'layout':program['layout'],
              'global_variables':{'base':program['layout']['globals'],'count':240,'width':16,'endian':'big'},
              'object_flags':{'base':program['layout']['objects']+62,'stride':9,'bits':32,'order':'msb-first'},
              'locals':'per-call-frame u16 list','stack':'u16 list with per-frame base',
              'runtime_fields':['pc','frames','stack','pending_input','rng','host','game_slot'],
              'alias_policy':'one-authoritative-byte-store; typed views, not duplicate copies',
              'readonly_scope':'source-derived read-only data and code identity backing; not instruction dispatch'}
    memory = pack({'id':'z3.memory','entry':'state.layout','requires':{}}, {
        'state.layout':('layout','application/json',canonical(schema),['state.dynamic','state.readonly'],{}),
        'state.dynamic':('state-template','application/octet-stream',initial[:boundary],[],{}),
        'state.readonly':('readonly-data','application/octet-stream',initial[boundary:],[],{})},
        {'profile':'z3-python-memory-1'})
    (root/'media.zip').write_bytes(media)
    (root/'memory.zip').write_bytes(memory)
    (root/'state_services.py').write_text(service_source())
    (root/'asset_package.py').write_bytes((ROOT.parent/'text_asset_pilot/asset_package.py').read_bytes())
    for name in ('runtime.py','primitives.py','play.py'):
        (root/name).write_bytes((ROOT/name).read_bytes())
    generated = root/'game_code'; generated.mkdir()
    (generated/'__init__.py').write_text('# Ahead-of-time generated Python continuations.\n')
    shards = {}
    emitter = Emitter()
    for key, block in sorted(program['blocks'].items(),key=lambda p:int(p[0])):
        pc = int(key)
        shards.setdefault(pc >> SHARD_BITS, []).append((pc, emitter.block(pc,block)))
    for shard, blocks in shards.items():
        name = f'b{shard:03x}.py'
        text = ('# Generated game-derived code. Keep private.\nfrom primitives import *\n\n'
                + '\n'.join(code for pc,code in blocks)
                + '\nBLOCKS = {\n' + ''.join(f'    {pc}: block_{pc:05x},\n' for pc,code in blocks) + '}\n')
        # Validate syntax now, not after the first player reaches a branch.
        compile(text,name,'exec')
        (generated/name).write_text(text)
    functions = {k:{'entry':v['entry'],'locals':v['locals'],'guard_bytes':len(bytes.fromhex(v['guard']))}
                 for k,v in program['functions'].items()}
    spec = {'format':FORMAT,'entry':program['entry'],'source':program['source'],
            'program_sha256':sha(canonical(program)), 'shard_bits':SHARD_BITS,
            'block_ids':sorted(map(int,program['blocks'])), 'functions':functions,
            'media_sha256':sha(media),'memory_sha256':sha(memory),
            'normalization':normalization,
            'translation':'mechanical Python; build-time IR only; game-intent UIL deferred'}
    (root/'program.json').write_bytes(canonical(spec))
    # Lock all shipped code and data. Integrity is not authenticity or equivalence.
    files = {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
    lock = {'format':'fdisbull-z3-python-product-1','files':files}
    (root/'product.json').write_bytes(canonical(lock))
    receipt = {'candidate_blocks':len(program['blocks']),'candidate_functions':len(functions),'python_modules':len(shards),
               'files':len(files),'bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
               'product_sha256':sha(canonical(lock)),'media_sha256':sha(media),'memory_sha256':sha(memory),
               'frontend_source_sha256':source_check,
               'normalization':normalization}
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('story',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    before = sha(args.story.read_bytes())
    program,_ = compile_story(args.story)
    if before != sha(args.story.read_bytes()) or before != program['source']['sha256']:
        raise ValueError('Story changed during build')
    print(json.dumps(build(program,args.output,source_check=before),indent=2))

if __name__ == '__main__': main()
