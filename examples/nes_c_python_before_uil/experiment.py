"""Reproduce the NES C/Python-before-UIL experiment outside the checkout."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import itertools
import json
import re
import subprocess
from pathlib import Path

TICK = bytes.fromhex(
    "a9008503a5002910f016a502d012a5011869038501a9048502a90185034c2980"
    "a502f00538e9018502a503f005a90f8d1540a5018d042060"
)
LENGTH = {
    0xA9: 2, 0xA5: 2, 0x85: 2, 0x8D: 3, 0x29: 2, 0xF0: 2, 0xD0: 2,
    0x18: 1, 0x38: 1, 0x69: 2, 0xE9: 2, 0x4C: 3, 0x60: 1,
}

C_SOURCE = r'''#include <stdint.h>
typedef struct { uint8_t x,cooldown,shot,sound_count,sound_value,draw_count,draw_value; } Result;
Result tick(uint8_t buttons, uint8_t x, uint8_t cooldown) {
    Result out; uint8_t shot=0;
    if ((buttons & 0x10u) != 0u && cooldown == 0u) {
        x=(uint8_t)(x+3u); cooldown=4u; shot=1u;
    } else if (cooldown != 0u) { cooldown=(uint8_t)(cooldown-1u); }
    out.x=x; out.cooldown=cooldown; out.shot=shot;
    out.sound_count=shot?1u:0u; out.sound_value=0x0fu;
    out.draw_count=1u; out.draw_value=x; return out;
}
'''

class Result(ctypes.Structure):
    _fields_=[("x",ctypes.c_uint8),("cooldown",ctypes.c_uint8),("shot",ctypes.c_uint8),
              ("sound_count",ctypes.c_uint8),("sound_value",ctypes.c_uint8),
              ("draw_count",ctypes.c_uint8),("draw_value",ctypes.c_uint8)]


def python_tick(buttons:int,x:int,cooldown:int):
    shot=0
    if buttons & 0x10 and cooldown == 0:
        x=(x+3)&0xff; cooldown=4; shot=1
    elif cooldown: cooldown-=1
    return x,cooldown,shot,((0x0f,) if shot else ()),(x,)


def python_tick_unmasked(buttons:int,x:int,cooldown:int):
    shot=0
    if buttons & 0x10 and cooldown == 0:
        x=x+3; cooldown=4; shot=1
    elif cooldown: cooldown-=1
    return x,cooldown,shot,((0x0f,) if shot else ()),(x,)


def run_6502(buttons:int,x:int,cooldown:int):
    mem=bytearray(65536); mem[0x8000:0x8000+len(TICK)]=TICK
    mem[0],mem[1],mem[2],mem[3]=buttons,x,cooldown,0xaa
    pc=0x8000; a=carry=zero=count=0; sound=[]; draw=[]
    while True:
        count+=1
        if count>100: raise RuntimeError("instruction budget")
        op=mem[pc]
        if op==0xA9: a=mem[pc+1]; zero=int(a==0); pc+=2
        elif op==0xA5: a=mem[mem[pc+1]]; zero=int(a==0); pc+=2
        elif op==0x85: mem[mem[pc+1]]=a; pc+=2
        elif op==0x8D:
            address=mem[pc+1]|mem[pc+2]<<8
            if address==0x4015: sound.append(a)
            elif address==0x2004: draw.append(a)
            else: mem[address]=a
            pc+=3
        elif op==0x29: a&=mem[pc+1]; zero=int(a==0); pc+=2
        elif op in (0xF0,0xD0):
            delta=mem[pc+1]-(256 if mem[pc+1]>=128 else 0)
            take=(zero==1) if op==0xF0 else (zero==0)
            pc=pc+2+delta if take else pc+2
        elif op==0x18: carry=0; pc+=1
        elif op==0x38: carry=1; pc+=1
        elif op==0x69:
            total=a+mem[pc+1]+carry; carry=int(total>0xff); a=total&0xff; zero=int(a==0); pc+=2
        elif op==0xE9:
            total=a-mem[pc+1]-(1-carry); carry=int(total>=0); a=total&0xff; zero=int(a==0); pc+=2
        elif op==0x4C: pc=mem[pc+1]|mem[pc+2]<<8
        elif op==0x60: break
        else: raise RuntimeError(f"unsupported opcode {op:02x}")
    return mem[1],mem[2],mem[3],tuple(sound),tuple(draw),count


def blocks():
    instructions=[]; pc=0x8000
    while pc<0x8000+len(TICK):
        op=TICK[pc-0x8000]; size=LENGTH[op]
        instructions.append((pc,op,size)); pc+=size
    leaders={0x8000}
    for pc,op,size in instructions:
        next_pc=pc+size; off=pc-0x8000
        if op in (0xF0,0xD0):
            delta=TICK[off+1]-(256 if TICK[off+1]>=128 else 0)
            leaders.update((next_pc,next_pc+delta))
        elif op==0x4C: leaders.update((next_pc,TICK[off+1]|TICK[off+2]<<8))
    result=[]; ordered=sorted(leaders)
    for i,start in enumerate(ordered):
        stop=ordered[i+1] if i+1<len(ordered) else 0x10000
        members=[item for item in instructions if start<=item[0]<stop]
        if not members: continue
        pc,op,size=members[-1]; next_pc=pc+size; off=pc-0x8000; successors=[]
        if op in (0xF0,0xD0):
            delta=TICK[off+1]-(256 if TICK[off+1]>=128 else 0); successors=[next_pc,next_pc+delta]
        elif op==0x4C: successors=[TICK[off+1]|TICK[off+2]<<8]
        elif op!=0x60: successors=[next_pc]
        effects=[]
        for at,code,_ in members:
            if code==0x8D:
                o=at-0x8000; target=TICK[o+1]|TICK[o+2]<<8
                if 0x4000<=target<=0x4017: effects.append("apu.write")
                if 0x2000<=target<=0x2007: effects.append("ppu.write")
        result.append({"start":start,"end":pc+size,"instructions":len(members),
                       "successors":successors,"effects":effects})
    return result


def regions(items):
    result=[]; pure=[]
    for item in items:
        if item["effects"]:
            if pure: result.append({"kind":"pure_logic_candidate","blocks":pure}); pure=[]
            result.append({"kind":"effect_boundary","blocks":[item]})
        else: pure.append(item)
    if pure: result.append({"kind":"pure_logic_candidate","blocks":pure})
    return result


def build_rom():
    prg=bytearray([0xea]*0x8000); prg[:len(TICK)]=TICK
    shell=bytes.fromhex("78d8a2ff9aa9008500850185022000804c0d81")
    prg[0x100:0x100+len(shell)]=shell
    for at in (0x7ffa,0x7ffc,0x7ffe): prg[at:at+2]=b"\x00\x81"
    return b"NES\x1a"+bytes([2,0,0,0])+bytes(8)+prg


def llvm_blocks(path:Path):
    text=path.read_text(); match=re.search(r"define\b[^\{]*@tick\([^)]*\)[^\{]*\{(.*?)^\}",text,re.S|re.M)
    body=match.group(1) if match else ""; labels=re.findall(r"^(?:[A-Za-z$._][\w$.-]*|\d+):",body,re.M)
    return (1+len(labels)) if body.strip() else 0


def prepare(path:Path):
    path=path.resolve()
    if path.exists(): raise RuntimeError("output must be new")
    if any((parent/".git").exists() for parent in (path,*path.parents)):
        raise RuntimeError("output must be outside Git")
    path.mkdir(parents=True); return path


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--clang",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); output=prepare(args.output); clang=args.clang.resolve()
    if not clang.is_file(): raise RuntimeError("explicit Clang required")
    cfile=output/"tick.c"; cfile.write_text(C_SOURCE); library=output/"libtick.so"
    subprocess.run([str(clang),"-std=c11","-O2","-shared","-fPIC","-Werror",str(cfile),"-o",str(library)],check=True,timeout=60)
    llvm={}
    for opt in ("O0","O2"):
        path=output/f"tick-{opt}.ll"; subprocess.run([str(clang),f"-{opt}","-S","-emit-llvm",str(cfile),"-o",str(path)],check=True,timeout=60); llvm[opt]=llvm_blocks(path)
    native=ctypes.CDLL(str(library)); native.tick.argtypes=[ctypes.c_uint8]*3; native.tick.restype=Result
    mismatch_c=mismatch_py=mismatch_bad=0; examples=[]; low=999; high=0
    for buttons,x,cooldown in itertools.product((0,0x10),range(256),range(256)):
        original=run_6502(buttons,x,cooldown); low=min(low,original[-1]); high=max(high,original[-1]); expected=original[:-1]
        c=native.tick(buttons,x,cooldown); cvalue=(c.x,c.cooldown,c.shot,((c.sound_value,) if c.sound_count else ()),((c.draw_value,) if c.draw_count else ()))
        mismatch_c+=cvalue!=expected; mismatch_py+=python_tick(buttons,x,cooldown)!=expected
        bad=python_tick_unmasked(buttons,x,cooldown)
        if bad!=expected:
            mismatch_bad+=1
            if len(examples)<8: examples.append({"buttons":buttons,"x":x,"cooldown":cooldown,"original":expected,"unmasked_python":bad})
    rom=build_rom(); (output/"tiny_tick.nes").write_bytes(rom); (output/"tick.bin").write_bytes(TICK)
    graph=blocks(); receipt={
      "toolchain":{"clang_version":subprocess.run([str(clang),"--version"],capture_output=True,text=True,check=True).stdout.splitlines()[0],"clang_sha256":hashlib.sha256(clang.read_bytes()).hexdigest()},
      "fixture":{"rom_sha256":hashlib.sha256(rom).hexdigest(),"rom_bytes":len(rom),"tick_sha256":hashlib.sha256(TICK).hexdigest(),"tick_bytes":len(TICK),"states_tested":131072,"instruction_count_range":[low,high],"emulator_presentation_tested":False},
      "equivalence":{"c_vs_6502_mismatches":mismatch_c,"masked_python_vs_6502_mismatches":mismatch_py,"unmasked_python_vs_6502_mismatches":mismatch_bad,"unmasked_examples":examples},
      "structure":{"6502_instruction_count":28,"6502_basic_blocks":len(graph),"6502_blocks":graph,"deterministic_effect_partition":regions(graph),"llvm_O0_blocks":llvm["O0"],"llvm_O2_blocks":llvm["O2"]},
      "interpretation":{"python_before_uil":"optional executable hypothesis/oracle, not a mandatory IL","typed_c_before_uil":"structured recovery view for pure regions","python_as_udc_provider":"high-level host services, formatting, orchestration and reference providers"}}
    (output/"receipt.json").write_text(json.dumps(receipt,indent=2,default=list)+"\n"); print(json.dumps(receipt["equivalence"],indent=2,default=list))

if __name__=="__main__": main()
