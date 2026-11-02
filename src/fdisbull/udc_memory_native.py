"""Native ARM64 realization of the unchanged bounded-memory UIL profile.

The generator emits ordinary C, using the established macOS compiler identity
probe. No game, graphics, input or RNG operation is part of this lowering.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .udc_macos import DEFAULT_TARGET, _compiler
from .udc_web_memory import NAME, digest, validate_memory_uil

PROFILE = 'macos-arm64-memory-c-1'
TARGET = 'macos-arm64-memory-1'
FORMAT = 'fdisbull-native-memory-block-build-1'
NATIVE_MEMORY_HEADER = r'''#ifndef FDISBULL_NATIVE_MEMORY_ABI_1
#define FDISBULL_NATIVE_MEMORY_ABI_1
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef struct { uint32_t status, steps, cut; } FdbBlockResult;
#endif
'''
_KEYWORDS = set('auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local'.split())


def emit_memory_function(program, function, symbol, *, capture_local=None):
    """Emit one pure N-word function, preserving atomic refusals and charges.

    Expressions use ordered temporaries, so C's unspecified operand/argument
    evaluation order cannot move a trap ahead of an earlier expression. The
    caller owns an N-word mutable arena; a refusal restores that entire arena.
    ``capture_local`` exposes only an explicitly selected successful local.
    """
    program = validate_memory_uil(program)
    if type(function) is not str or function not in program['functions']:
        raise ValueError('unknown native memory function')
    if type(symbol) is not str or not NAME.fullmatch(symbol) or symbol in _KEYWORDS or symbol.startswith('__'):
        raise ValueError('invalid native memory symbol')
    if capture_local is not None and (type(capture_local) is not str or capture_local not in program['variables']):
        raise ValueError('native capture requires a declared local')
    spec = program['functions'][function]
    words = program['memory']['words']
    variables = {name:'fdb_v'+str(index) for index,name in enumerate(sorted(program['variables']))}
    lines = [f'FdbBlockResult {symbol}(uint32_t *fdb_words) {{',
             f'  uint32_t fdb_remaining = {spec["max_steps"]}u;',
             '  uint32_t fdb_failed = 0u;',
             '  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};',
             f'  uint32_t *fdb_saved = (uint32_t *)malloc({words}u * sizeof(uint32_t));',
             '  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};',
             f'  memcpy(fdb_saved,fdb_words,{words}u * sizeof(uint32_t));']
    for name, variable in variables.items():
        lines.append(f'  uint32_t {variable} = {program["variables"][name]["initial"]}u;')
    lines.append('  {')
    counter = 0
    loop_counter = 0

    def line(indent, text):
        lines.append('  '*indent + text)

    def refuse(indent):
        line(indent, 'fdb_failed = 1u; goto fdb_done;')

    def charge(indent):
        line(indent, 'if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }')
        line(indent, '--fdb_remaining;')

    def expression(value, indent):
        nonlocal counter
        if type(value) is int:
            return str(value)+'u'
        if 'var' in value:
            return variables[value['var']]
        if 'load' in value:
            index = expression(value['load'],indent)
            line(indent, f'if ({index} >= {words}u) {{ fdb_failed = 1u; goto fdb_done; }}')
            text = f'fdb_words[{index}]'
        else:
            left = expression(value['left'],indent)
            right = expression(value['right'],indent)
            op = value['op']
            if op in ('div','mod'):
                line(indent, f'if ({right} == 0u) {{ fdb_failed = 1u; goto fdb_done; }}')
            operators={'add':'+','sub':'-','mul':'*','and':'&','or':'|','xor':'^',
                       'div':'/','mod':'%','eq':'==','ne':'!=','lt':'<','le':'<=','gt':'>','ge':'>='}
            if op in ('shl','shr'):
                text=f'({left} {"<<" if op=="shl" else ">>"} ({right} & 31u))'
            else:
                text=f'({left} {operators[op]} {right})'
        temporary='fdb_t'+str(counter);counter+=1
        line(indent,f'uint32_t {temporary} = (uint32_t){text};')
        return temporary

    def body(nodes, indent):
        nonlocal loop_counter
        for node in nodes:
            charge(indent)
            op=node['op']
            if op=='set':
                value=expression(node['value'],indent)
                line(indent,variables[node['var']]+' = '+value+';')
            elif op=='store':
                index=expression(node['index'],indent)
                value=expression(node['value'],indent)
                line(indent,f'if ({index} >= {words}u) {{ fdb_failed = 1u; goto fdb_done; }}')
                line(indent,f'fdb_words[{index}] = {value};')
            elif op=='if':
                condition=expression(node['condition'],indent)
                line(indent,f'if ({condition} != 0u) {{')
                body(node['then'],indent+1)
                line(indent,'} else {')
                body(node['else'],indent+1)
                line(indent,'}')
            elif op=='return':
                line(indent,'goto fdb_done;')
            else:
                loop='fdb_loop'+str(loop_counter);loop_counter+=1
                line(indent,f'for (uint32_t {loop}=0u;;) {{')
                charge(indent+1)
                condition=expression(node['condition'],indent+1)
                line(indent+1,f'if ({condition} == 0u) break;')
                line(indent+1,f'if ({loop} == {node["limit"]}u) {{ fdb_failed = 1u; goto fdb_done; }}')
                line(indent+1,f'++{loop};')
                body(node['body'],indent+1)
                line(indent,'}')

    body(spec['body'],2)
    lines += ['  }','fdb_done:',
              f'  if (fdb_failed) memcpy(fdb_words,fdb_saved,{words}u * sizeof(uint32_t));',
              '  free(fdb_saved);',
              f'  FdbBlockResult fdb_result = {{ fdb_failed, {spec["max_steps"]}u-fdb_remaining, '+
              ('fdb_failed ? 0u : '+variables[capture_local] if capture_local is not None else '0u')+' };',
              '  return fdb_result;','}']
    return '\n'.join(lines)+'\n'


def _probe_source(words):
    return r'''#include <stdio.h>
#include "block.c"
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "The probe ABI requires a little-endian target"
#endif
int main(void) {
  const size_t count = '''+str(words)+r'''u;
  uint32_t *words=(uint32_t *)malloc(count*sizeof(uint32_t));
  if (!words) return 3;
  for (;;) {
    size_t got=fread(words,1,count*sizeof(uint32_t),stdin);
    if (got==0 && feof(stdin)) break;
    if (got!=count*sizeof(uint32_t)) { free(words);return 2; }
    FdbBlockResult result=fdb_block(words);
    uint32_t header[3]={result.status,result.steps,result.cut};
    if (fwrite(header,sizeof(uint32_t),3,stdout)!=3 ||
        fwrite(words,sizeof(uint32_t),count,stdout)!=count || fflush(stdout)!=0) {
      free(words);return 3;
    }
  }
  free(words);return 0;
}
'''


def build_native_memory_block(program, function, destination, *, capture_local=None,
                              c_compiler=None, target=DEFAULT_TARGET):
    """Build an ARM64 dylib and finite streaming probe without executing them."""
    program=validate_memory_uil(program)
    source=NATIVE_MEMORY_HEADER+emit_memory_function(program,function,'fdb_block',capture_local=capture_local)
    if type(target) is not str or not re.fullmatch(r'arm64-apple-macos[0-9]+(?:\.[0-9]+)*',target):
        raise ValueError('native memory target must be arm64-apple-macos*')
    destination=Path(destination).expanduser().absolute()
    if os.path.lexists(destination):raise ValueError('choose a new private native memory output')
    destination=destination.resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('native memory output must be outside Git')
    compiler,compiler_info=_compiler(c_compiler or shutil.which('clang'))
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    (destination/'block.c').write_text(source)
    (destination/'probe.c').write_text(_probe_source(program['memory']['words']))
    common=[str(compiler),'--target='+target,'-std=c11','-O1','-Wall','-Wextra',
            '-Werror','-Wno-unused-variable','-Wno-unused-but-set-variable','-Wno-unused-label']
    commands=[[*common,'-dynamiclib','block.c','-o','block.dylib'],
              [*common,'probe.c','-o','probe']]
    try:
        for command in commands:
            done=subprocess.run(command,cwd=destination,capture_output=True,text=True,timeout=120,check=False)
            if done.returncode:raise ValueError('native memory compilation failed: '+done.stderr[:2000])
    except (OSError,subprocess.TimeoutExpired) as error:
        raise ValueError('native memory compilation failed') from error
    import lief
    for name,file_type in [('block.dylib',lief.MachO.Header.FILE_TYPE.DYLIB),('probe',lief.MachO.Header.FILE_TYPE.EXECUTE)]:
        parsed=lief.MachO.parse(str(destination/name))
        if parsed is None or len(parsed)!=1:raise ValueError('native memory output is not one Mach-O image')
        image=parsed.at(0)
        if image.header.cpu_type!=lief.MachO.Header.CPU_TYPE.ARM64 or image.header.file_type!=file_type:
            raise ValueError('native memory output is not the requested ARM64 image')
    artifacts={name:hashlib.sha256((destination/name).read_bytes()).hexdigest()
               for name in ('block.c','probe.c','block.dylib','probe')}
    receipt={'format':FORMAT,'profile':PROFILE,'target':TARGET,'target_triple':target,
        'function':function,'symbol':'fdb_block','module_uil_sha256':digest(program),
        'abi':{'format':'fdisbull-native-memory-abi-1','memory_words':program['memory']['words'],
            'word':'u32-le','max_steps':program['functions'][function]['max_steps'],
            'capture_local':capture_local,'result':['status','steps','cut'],
            'status':{'complete':0,'refused':1},'atomic_refusal':True},
        'compiler':{**compiler_info,'commands':commands},'artifacts':artifacts,
        'native_execution':False,'source_to_uil':False,
        'linkage':'dyld + libSystem; allocator, arena copy and optional stdio probe',
        'scope':'one bounded-memory function; original fidelity and host adapters qualified separately'}
    (destination/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
