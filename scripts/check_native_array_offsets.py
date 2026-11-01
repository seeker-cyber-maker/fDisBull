#!/usr/bin/env python3
"""Check native small-array lowering on an actual cc65 6502 CPU.

The control accesses use ordinary C indexing in a separate translation unit.
All generated C, binaries, assembly and logs go to a new external directory.
This is an address/arithmetic canary; it does not replace full-game checks.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import re
import subprocess


TYPES = (("u8", 8, False), ("i8", 8, True), ("u16", 16, False),
         ("i16", 16, True), ("u32", 32, False), ("i32", 32, True))
TYPEDEFS = """
typedef unsigned char u8; typedef signed char i8;
typedef unsigned int u16; typedef signed int i16;
typedef unsigned long u32; typedef signed long i32;
"""
INDEXES = ("index", "(i16)index", "(u32)index", "((i16)index-7)+7",
           "((u32)index+65535UL)-65535UL", "index_once(index)")


def _literal(value, bits, signed):
    if signed and value & (1 << (bits - 1)):
        value -= 1 << bits
    if bits == 32:
        if value == -(1 << 31):
            return "(-2147483647L-1L)"
        return str(value) + ("L" if signed else "UL")
    return str(value) + ("U" if not signed and bits == 16 else "")


def sources():
    """Independent authored arrays include every legal final byte offset."""
    rows = []
    unit = [TYPEDEFS, "u16 evaluation_count;",
            "u16 index_once(u16 index){evaluation_count=evaluation_count+1;return index;}"]
    for typ, bits, signed in TYPES:
        for qualifier, suffix in (("", "plain"), ("volatile", "volatile"),
                                  ("const", "const"), ("const volatile", "cv")):
            count = 256 // (bits // 8)
            name = f"array_{typ}_{suffix}"
            values = [((i * 0x9E3779B1) ^ (0x80000000 + i * 19) ^ 0xA55A3CC3)
                      & ((1 << bits) - 1) for i in range(count)]
            # Explicit signed/unsigned minima, maxima and alternating masks.
            values[:6] = [0, (1 << bits) - 1, 1 << (bits - 1),
                          (1 << (bits - 1)) - 1,
                          0x55555555 & ((1 << bits) - 1),
                          0xAAAAAAAA & ((1 << bits) - 1)]
            decl = f"{qualifier} {typ} {name}[{count}]".strip()
            unit.append(decl + "={" + ",".join(_literal(v, bits, signed) for v in values) + "};")
            read = [f"u32 read_{name}(u16 index,u8 mode){{"]
            for mode, expression in enumerate(INDEXES):
                read.append(f"if(mode=={mode})return (u32){name}[{expression}];")
            read.append("return 0;}")
            unit.extend(read)
            unit.append(f"u32 arithmetic_{name}(u16 index,u32 value){{"
                        f"return ((u32){name}[index]+value)^(((u32){name}[index]>>3)|0x12340000UL);}}")
            mutable = "const" not in qualifier
            if mutable:
                unit.append(f"void write_{name}(u16 index,u32 value,u8 mode){{")
                for mode, expression in enumerate(INDEXES):
                    unit.append(f"if(mode=={mode}){{{name}[{expression}]=({typ})value;return;}}")
                unit.append("}")
                unit.append(f"void update_{name}(u16 index,u32 value){{"
                            f"{name}[index]=({typ})((u32){name}[index]+value);"
                            f"{name}[index]^=({typ})0x5A5A5A5AUL;}}")
            rows.append(dict(name=name, typ=typ, bits=bits, signed=signed,
                             count=count, decl=decl, mutable=mutable))
    unit.append("""
typedef const volatile u16 cv_u16;
cv_u16 alias_qualified[128]={0x1234,0xABCD};
u32 read_alias_qualified(u16 index){return alias_qualified[index];}
u32 nested_read(u16 index){return array_u32_const[(u8)(array_u8_const[index]&63)];}
u8 large_u8[257];u16 large_u16[129];u32 large_u32[65];
u8 shadow[16];u16 type_shadow[8];
u8 pointer_case(u8 *pointer,u16 index){return pointer[index];}
u8 parameter_shadow(u8 *shadow,u16 index){shadow[index]=0xA6;return shadow[43];}
u8 array_parameter_shadow(u8 shadow[16],u16 index){shadow[index]=0xA6;return shadow[43];}
u8 local_shadow(u16 index){u8 shadow[300];shadow[43]=0x19;shadow[index]=0xA6;return shadow[43];}
u8 local_type_shadow(u16 index){u8 type_shadow[256];type_shadow[254]=0x5A;type_shadow[255]=0xA5;return type_shadow[index];}
u16 global_type_shadow(u16 index){return type_shadow[index];}
u32 read_large(u8 kind,u16 index){if(kind==0)return large_u8[index];if(kind==1)return large_u16[index];return large_u32[index];}
void write_large(u8 kind,u16 index,u32 value){if(kind==0)large_u8[index]=(u8)value;else if(kind==1)large_u16[index]=(u16)value;else large_u32[index]=value;}
""")
    control = ["#include <stdio.h>\n#include <string.h>\n#include <sim65.h>", TYPEDEFS,
               "extern u16 evaluation_count;"]
    for row in rows:
        control.append("extern " + row['decl'] + ";")
        name = row['name']
        control.append(f"u32 read_{name}(u16,u8);u32 arithmetic_{name}(u16,u32);")
        if row['mutable']:
            control.append(f"void write_{name}(u16,u32,u8);void update_{name}(u16,u32);")
    control.extend(("""
extern u8 large_u8[257],shadow[16];extern u16 large_u16[129],type_shadow[8];extern u32 large_u32[65];
extern const volatile u16 alias_qualified[128];u32 read_alias_qualified(u16);u32 nested_read(u16);
u8 pointer_case(u8*,u16);u8 parameter_shadow(u8*,u16);u8 array_parameter_shadow(u8*,u16);
u8 local_shadow(u16);u8 local_type_shadow(u16);u16 global_type_shadow(u16);
u32 read_large(u8,u16);void write_large(u8,u16,u32);
static u8 scratch[512],expected_bytes[256];
static u32 cases;
static u32 values[6]={0UL,0xFFFFFFFFUL,0x80000000UL,0x7FFFFFFFUL,0x55555555UL,0xAAAAAAAAUL};
static int failure(const char *name,u16 index,u8 mode,u32 got,u32 expected){printf("FAIL %s index%u mode%u actual%lu expected%lu\\n",name,index,mode,got,expected);return 1;}
static void save_bytes(const volatile u8 *source){u16 i;for(i=0;i<256;i=i+1)expected_bytes[i]=source[i];}
static u8 changed_bytes(const volatile u8 *source){u16 i;for(i=0;i<256;i=i+1)if(expected_bytes[i]!=source[i])return 1;return 0;}
static u32 cycles(void){peripherals.counter.latch=0;peripherals.counter.select=0;return peripherals.counter.value32[0];}
int main(int argc,char **argv){
u16 index,k;u8 mode,value_index;u32 actual,expected,prior,start;
if(sizeof(u8)!=1||sizeof(i8)!=1||sizeof(u16)!=2||sizeof(i16)!=2||sizeof(u32)!=4||sizeof(i32)!=4||(char)255!=255)return 90;
if(argc>1){
 actual=*((u16*)((u8*)array_u16_const+1));
 if(actual==(u32)array_u16_const[1])return 91;
 printf("DETECTED_BAD_SCALE index1\\n");
 large_u8[0]=17;large_u8[256]=126;
 if(large_u8[(u8)256]==large_u8[256])return 92;
 printf("DETECTED_BAD_LARGE_WRAP index256\\n");return 1;
}
start=cycles();
""",))
    for row in rows:
        name, typ, size = row['name'], row['typ'], row['bits'] // 8
        control.append(f"for(index=0;index<{row['count']};index=index+1){{")
        control.append(f"expected=(u32){name}[index];")
        control.append(f"for(mode=0;mode<{len(INDEXES)};mode=mode+1){{evaluation_count=0;"
                       f"actual=read_{name}(index,mode);cases=cases+1;"
                       f"if(actual!=expected||evaluation_count!=(mode==5))return failure(\"read_{name}\",index,mode,actual,expected);}}")
        control.append(f"actual=arithmetic_{name}(index,0xF0F01234UL);"
                       "expected=(expected+0xF0F01234UL)^((expected>>3)|0x12340000UL);cases=cases+1;"
                       f"if(actual!=expected)return failure(\"arithmetic_{name}\",index,0,actual,expected);")
        if row['mutable']:
            control.append("for(value_index=0;value_index<6;value_index=value_index+1){")
            control.append(f"for(mode=0;mode<{len(INDEXES)};mode=mode+1){{")
            control.append(f"save_bytes((const volatile u8*)&{name});"
                           f"for(k=0;k<{size};k=k+1)expected_bytes[index*{size}+k]=(u8)(values[value_index]>>(k*8));"
                           f"evaluation_count=0;write_{name}(index,values[value_index],mode);cases=cases+1;"
                           f"if(changed_bytes((const volatile u8*)&{name})||evaluation_count!=(mode==5))"
                           f"return failure(\"write_{name}\",index,mode,(u32){name}[index],(u32)({typ})values[value_index]);}}")
            control.append(f"prior=(u32){name}[index];"
                           f"expected=(u32)({typ})((({typ})(prior+values[value_index]))^({typ})0x5A5A5A5AUL);"
                           f"update_{name}(index,values[value_index]);cases=cases+1;actual=(u32){name}[index];"
                           f"if(actual!=expected)return failure(\"update_{name}\",index,0,actual,expected);")
            control.append("}")
        control.append("}")
    control.append("""
for(index=0;index<256;index=index+1){actual=nested_read(index);expected=array_u32_const[(u8)(array_u8_const[index]&63)];cases=cases+1;if(actual!=expected)return failure("nested",index,0,actual,expected);}
for(index=0;index<128;index=index+1){actual=read_alias_qualified(index);expected=alias_qualified[index];cases=cases+1;if(actual!=expected)return failure("alias_qualified",index,0,actual,expected);}
for(index=0;index<512;index=index+1)scratch[index]=(u8)(index*29U+(index>>8)*71U);
for(index=0;index<512;index=index+1){actual=pointer_case(scratch,index);cases=cases+1;if(actual!=scratch[index])return failure("pointer",index,0,actual,scratch[index]);}
scratch[43]=0x19;scratch[299]=0;
if(parameter_shadow(scratch,299)!=0x19||scratch[299]!=0xA6)return 20;cases=cases+1;
scratch[43]=0x19;scratch[299]=0;
if(array_parameter_shadow(scratch,299)!=0x19||scratch[299]!=0xA6)return 21;cases=cases+1;
if(local_shadow(299)!=0x19)return 22;cases=cases+1;
if(local_type_shadow(255)!=0xA5)return 23;cases=cases+1;
type_shadow[7]=0xA55A;if(global_type_shadow(7)!=0xA55A)return 24;cases=cases+1;
for(index=0;index<257;index=index+1){write_large(0,index,(index*19U)^(index>>8)*71U);cases=cases+1;if(read_large(0,index)!=(u32)large_u8[index])return 25;}
for(index=0;index<129;index=index+1){write_large(1,index,index*0x1234U);cases=cases+1;if(read_large(1,index)!=(u32)large_u16[index])return 26;}
for(index=0;index<65;index=index+1){write_large(2,index,index*0x9E3779B1UL);cases=cases+1;if(read_large(2,index)!=large_u32[index])return 27;}
printf("PASS %lu CYCLES %lu\\n",cases,cycles()-start);return 0;
}
""")
    return "\n".join(unit), "\n".join(control), rows


def verify(toolchain, output):
    from fdisbull.udc_nes_game import _instrument, native_index_generator
    from fdisbull.game_il import _parser
    generator_source = inspect.getsource(native_index_generator)
    toolchain, output = (Path(x).resolve() for x in (toolchain, output))
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        raise ValueError('choose a fresh private output outside Git')
    source, control, rows = sources()
    lowered, segments, _ = _instrument(source, 'R')
    # Check that the candidate optimization was exercised, and that its actual
    # dereferenced element types retain qualifications. This is separate from
    # the CPU behavior checks below, which use an independent control unit.
    _, _, parser = _parser()
    tree = parser.CParser().parse(re.sub(r'^#.*$', '', lowered, flags=re.M))
    functions = {node.decl.name: node for node in tree.ext if type(node).__name__ == 'FuncDef'}
    pointer_qualification_checks = 0
    def dereferenced_types(node):
        if type(node).__name__ == 'UnaryOp' and node.op == '*' and type(node.expr).__name__ == 'Cast':
            pointer = node.expr.to_type.type
            if type(pointer).__name__ == 'PtrDecl':
                addition = node.expr.expr
                if type(addition).__name__ != 'BinaryOp' or addition.op != '+':
                    raise RuntimeError('unexpected lowered byte-address expression')
                byte_cast = addition.left
                if (type(byte_cast).__name__ != 'Cast'
                        or type(byte_cast.expr).__name__ != 'UnaryOp'
                        or byte_cast.expr.op != '&'
                        or type(byte_cast.expr.expr).__name__ != 'ID'):
                    raise RuntimeError('lowered char pointer must refer to the whole array object')
                byte_type = byte_cast.to_type.type.type
                if not set(pointer.type.quals) <= set(byte_type.quals):
                    raise RuntimeError('byte pointer lost element qualification')
                yield pointer.type
        for _, child in node.children():
            yield from dereferenced_types(child)
    for row in rows:
        if row['bits'] == 8:
            if f"{row['name']}[(unsigned char)" not in lowered:
                raise RuntimeError('small byte-array optimization was not exercised')
        else:
            accesses = list(dereferenced_types(functions['read_' + row['name']]))
            expected_quals = set(row['decl'].split()[:-2])
            if len(accesses) != len(INDEXES) or any(not expected_quals <= set(t.quals) for t in accesses):
                raise RuntimeError('lowered access lost const/volatile element qualification')
            pointer_qualification_checks += len(accesses)
    alias_types = list(dereferenced_types(functions['read_alias_qualified']))
    if len(alias_types) != 1 or not {'const', 'volatile'} <= set(alias_types[0].quals):
        raise RuntimeError('lowered access lost typedef-inherited qualifications')
    pointer_qualification_checks += 1
    output.mkdir(parents=True)
    (output / 'source.c').write_text(source)
    (output / 'lowered.c').write_text(lowered)
    (output / 'control.c').write_text(control)
    config = (toolchain / 'cfg/sim6502.cfg').read_text()
    config = config.replace('    BSS:', ''.join(f'    {name}: load = MAIN, type = ro;\n' for name in segments) + '    BSS:')
    (output / 'sim.cfg').write_text(config)
    command = [str(toolchain / 'bin/cl65'), '-t', 'sim6502', '-Oirs', '--static-locals',
               '-C', str(output / 'sim.cfg'), '-m', str(output / 'map.txt'),
               '-Ln', str(output / 'labels.txt'), '-o', str(output / 'check'),
               str(output / 'lowered.c'), str(output / 'control.c')]
    built = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output / 'build.txt').write_text(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError(built.stdout + built.stderr)
    run = subprocess.run([str(toolchain / 'bin/sim65'), '-c', str(output / 'check')],
                         capture_output=True, text=True, timeout=300)
    (output / 'run.txt').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(f'native canary failed ({run.returncode}):\n{run.stdout}{run.stderr}')
    match = re.search(r'^PASS (\d+) CYCLES (\d+)$', run.stdout, re.M)
    expected_count = sum(row['count'] * (len(INDEXES) + 1 + (6 * (len(INDEXES) + 1) if row['mutable'] else 0))
                         for row in rows) + 968 + 256 + 128
    if not match or int(match[1]) != expected_count:
        raise RuntimeError('native case count missing')
    negative = subprocess.run([str(toolchain / 'bin/sim65'), '-c', str(output / 'check'), 'negative'],
                              capture_output=True, text=True, timeout=60)
    (output / 'negative.txt').write_text(negative.stdout + negative.stderr)
    if negative.returncode != 1 or not all(x in negative.stdout for x in ('DETECTED_BAD_SCALE', 'DETECTED_BAD_LARGE_WRAP')):
        raise RuntimeError('canary negative controls did not detect invalid address lowering')
    receipt = {'format': 'fdisbull-native-array-canary-1', 'passed': True,
               'cases': int(match[1]), 'cycles': int(match[2]),
               'arrays': [{k: v for k, v in row.items() if k != 'decl'} for row in rows],
               'index_forms': list(INDEXES),
               'shadow_pointer_large_array_cases': 968,
               'nested_lookup_cases': 256,
               'typedef_inherited_qualification_cases': 128,
               'lowered_element_qualification_checks': pointer_qualification_checks,
               'generator_source_sha256': hashlib.sha256(generator_source.encode()).hexdigest(),
               'negative_controls': ['wrong two-byte element scale', 'illegal truncation of 257-byte array index'],
               'hashes': {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in
                          (output / 'source.c', output / 'lowered.c', output / 'control.c', output / 'check')},
               'limits': ['actual sim65 6502 procedure check, not NES IRQ/mapper/full-game acceptance',
                          'array equality is for valid in-bounds indices; no new bounds or fault behavior is asserted',
                          'cycle count includes control loops and reference checks and is not a speed comparison',
                          'qualified volatile source accesses tested without an interrupting device']}
    if inspect.getsource(native_index_generator) != generator_source:
        raise RuntimeError('native address generator changed during verification')
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc65-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.cc65_root, args.output), indent=2))
