"""First-party shared-IL realizations: freestanding C and standalone JavaScript.

No runtime from a surveyed recompiler is required. This deliberately small
profile has no host effects and rejects unsupported statements before emitting.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import ctypes
import json
import subprocess
from .model import Refused, canonical
from fdisbull.interaction_il import validate_il, ILInvalid


def admit(document: dict) -> tuple[str, ...]:
    try:
        validate_il(document)
    except ILInvalid as exc:
        raise Refused('invalid shared IL: '+str(exc)) from exc
    if document['resources']:
        raise Refused('this target does not implement host/resource services')
    variables = document['variables']
    if not variables or len(variables) > 256:
        raise Refused('target requires 1..256 variables')
    if any(d['type'] not in {'u8','u16','bool'} for d in variables.values()):
        raise Refused('target supports u8, u16 and bool only')

    def value(v):
        if isinstance(v,dict): return
        if type(v) is bool: return
        if type(v) is not int or not 0 <= v <= 65535:
            raise Refused('target literal must fit unsigned 16-bit')

    def condition(c):
        if c['op']=='eq': value(c['left']); value(c['right'])
        elif c['op']=='bit_test': value(c['value'])
        elif c['op']=='not': condition(c['condition'])
        elif c['op']=='and':
            for child in c['conditions']: condition(child)
        else: raise Refused('target condition unsupported')

    def walk(body):
        for b in body:
            if b['op'] in {'set','add','subtract'}: value(b['value'])
            elif b['op']=='if':
                condition(b['condition']); walk(b['then']); walk(b['else'])
            else: raise Refused('required operation lacks target implementation: '+b['op'])
    walk(document['body'])
    return tuple(sorted(variables))


def emit_c(document: dict) -> str:
    """Emit C using input/output word arrays; no guest address is emitted."""
    names = admit(document)
    index = {n:i for i,n in enumerate(names)}
    def val(v):
        if isinstance(v,dict): return f's[{index[v["var"]]}]'
        return str(int(v))+'u'
    def cond(c):
        op=c['op']
        if op=='eq': return f'({val(c["left"])} == {val(c["right"])})'
        if op=='bit_test':
            if c['bit']>=16: return '0'
            return f'(({val(c["value"])} >> {c["bit"]}) & 1u)'
        if op=='not': return f'(!{cond(c["condition"])})'
        return '('+' && '.join(cond(x) for x in c['conditions'])+')'
    lines = ['/* First-party generated realization of fdisbull-il-1. */',
             '#include <stdint.h>','#include <stddef.h>',
             'int synth_run(const uint32_t *input, size_t n, uint32_t *output, size_t m) {',
             f'    uint32_t s[{len(names)}];',
             f'    if (!input || !output || n != {len(names)}u || m != {len(names)}u) return 1;']
    for i,n in enumerate(names):
        typ=document['variables'][n]['type']
        cap={'u8':255,'u16':65535,'bool':1}[typ]
        lines += [f'    if (input[{i}] > {cap}u) return 2;', f'    s[{i}] = input[{i}];']
    def block(body,depth):
        pad='    '*depth
        for b in body:
            if b['op']=='if':
                condition = cond(b['condition'])
                if not (condition.startswith('(') and condition.endswith(')')):
                    condition = '(' + condition + ')'
                lines.append(pad+'if '+condition+' {')
                block(b['then'],depth+1)
                lines.append(pad+'} else {')
                block(b['else'],depth+1)
                lines.append(pad+'}')
            else:
                n=b['var']; left=f's[{index[n]}]'; right=val(b['value'])
                expr=right if b['op']=='set' else f'({left} {"+" if b["op"]=="add" else "-"} {right})'
                mask={'u8':255,'u16':65535,'bool':1}[document['variables'][n]['type']]
                if b['op']=='set':
                    lines.append(pad+f'if ({right} > {mask}u) return 3;')
                lines.append(pad+f'{left} = ({expr}) & {mask}u;')
    block(document['body'],1)
    for i in range(len(names)): lines.append(f'    output[{i}] = s[{i}];')
    lines += ['    return 0;','}','']
    return '\n'.join(lines)


def emit_javascript(document: dict) -> str:
    names=admit(document)
    variables=document['variables']
    def val(v): return f's[{json.dumps(v["var"])}]' if isinstance(v,dict) else json.dumps(v)
    def cond(c):
        op=c['op']
        if op=='eq': return f'({val(c["left"])} === {val(c["right"])})'
        if op=='bit_test':
            return 'false' if c['bit']>=16 else f'((({val(c["value"])} >>> {c["bit"]}) & 1) !== 0)'
        if op=='not': return f'(!{cond(c["condition"])})'
        return '('+' && '.join(cond(x) for x in c['conditions'])+')'
    lines=['// First-party generated realization; no native/foreign runtime calls.',
           'export function run(input) {',
           '  if (!input || typeof input !== "object" || Array.isArray(input)) throw new TypeError("state");',
           '  const s = {...input};',
           f'  const keys = {json.dumps(list(names))};',
           '  if (Object.keys(s).length !== keys.length || keys.some(k => !Object.hasOwn(s,k))) throw new TypeError("state keys");']
    for name in names:
        typ=variables[name]['type']; vv=f's[{json.dumps(name)}]'
        check=f'typeof {vv} !== "boolean"' if typ=='bool' else f'!Number.isInteger({vv}) || {vv}<0 || {vv}>{255 if typ=="u8" else 65535}'
        lines.append(f'  if ({check}) throw new TypeError("state value");')
    def block(body,depth):
        pad='  '*depth
        for b in body:
            if b['op']=='if':
                lines.append(pad+'if ('+cond(b['condition'])+') {');block(b['then'],depth+1)
                lines.append(pad+'} else {');block(b['else'],depth+1);lines.append(pad+'}')
            else:
                n=b['var'];left=f's[{json.dumps(n)}]';right=val(b['value'])
                expr=right if b['op']=='set' else f'({left} {"+" if b["op"]=="add" else "-"} {right})'
                typ=variables[n]['type']
                if b['op']=='set' and typ!='bool':
                    lines.append(pad+f'if ({right} > {255 if typ=="u8" else 65535}) throw new RangeError("assignment");')
                lines.append(pad+f'{left} = '+(expr if typ=='bool' else f'({expr}) & {255 if typ=="u8" else 65535}')+';')
    block(document['body'],1)
    lines+=['  return s;','}','']
    return '\n'.join(lines)


@dataclass
class NativeC:
    document: dict
    path: Path
    compiler_command: tuple[str, ...]
    compiler_version: str

    def __post_init__(self):
        self.names=admit(self.document)
        self.semantic_sha256=sha256(canonical(self.document)).hexdigest()
        self.target_profile='host-c-u8-u16-bool-v1'
        self.library=ctypes.CDLL(str(self.path.resolve()))
        self.function=self.library.synth_run
        self.function.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.c_size_t,
                                ctypes.POINTER(ctypes.c_uint32),ctypes.c_size_t]
        self.function.restype=ctypes.c_int

    def run(self,state:dict)->dict:
        if sha256(canonical(self.document)).hexdigest()!=self.semantic_sha256:
            raise Refused('compiled implementation metadata was modified')
        if not isinstance(state,dict) or set(state)!=set(self.names):
            raise Refused('invalid state keys')
        raw=[]
        for name in self.names:
            typ=self.document['variables'][name]['type'];v=state[name]
            valid=(type(v)is bool) if typ=='bool' else (type(v)is int and 0<=v<=({'u8':255,'u16':65535}[typ]))
            if not valid: raise Refused('invalid state value: '+name)
            raw.append(int(v))
        arr=ctypes.c_uint32*len(self.names)
        source=arr(*raw);dest=arr(*([0xdeadbeef]*len(self.names)))
        status=self.function(source,len(source),dest,len(dest))
        if status: raise Refused('native contract rejected inputs: '+str(status))
        return {n:bool(dest[i]) if self.document['variables'][n]['type']=='bool' else int(dest[i])
                for i,n in enumerate(self.names)}


def compile_c(document:dict,directory:Path,compiler:Path,optimization:str='-O2')->NativeC:
    """Explicitly invoke a caller-selected trusted compiler, not a shell command."""
    if optimization not in {'-O0','-O2'}: raise Refused('unsupported compiler policy')
    compiler=Path(compiler)
    if not compiler.is_absolute() or not compiler.is_file():
        raise Refused('compiler must be an explicit existing absolute path')
    text=emit_c(document)  # preflight everything before creating build outputs
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=directory/'module.c';library=directory/'module.so'
    source.write_text(text,encoding='utf-8')
    command=(str(compiler),'-std=c11',optimization,'-Wall','-Wextra','-Werror',
             '-fPIC','-shared',str(source),'-o',str(library))
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise Refused('C build failed: '+result.stderr[-4000:])
    version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=5).stdout.splitlines()[0]
    return NativeC(json.loads(canonical(document)),library,command,version)


def emit_retained(block, document: dict) -> bytes:
    """Return retained source bytes only for the unchanged shared description.

    This is an exact block reconstruction, not an independent behavior proof or
    reconstruction of the containing ROM. Edited UIL needs a new realization.
    """
    normalized=json.loads(canonical(document))
    validate_il(normalized)
    normalized['role']='uil'
    if canonical(normalized)!=block.document_bytes:
        raise Refused('edited UIL has no matching retained implementation')
    return block.backing.code
