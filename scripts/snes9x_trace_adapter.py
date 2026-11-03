#!/usr/bin/env python3
"""Add a bounded observational bus-write/instruction hook to one pinned SNES9x checkout.

This changes only a private source checkout. Bus writes record successful direct
memory stores; MMIO, DMA shortcuts and non-CPU writers are outside this hook.
"""
from pathlib import Path
import hashlib
import subprocess
import sys

COMMIT='fae2fea08f74180759ef540ee94259213f503480'
SOURCE_HASHES={'cpuexec.cpp':'ede5212e278afc371000fca0f81d6c8e463b5e0a47a1db8cf9f7004543c977e9',
               'getset.h':'bce5a65828fecaf68db5013ed86da77061ec8b26ca6cb6a1c89c45fddb6efa9b'}
SOURCE=r'''
// fDisBull bounded observational hook; does not modify emulated state.
struct FdbEvent { uint32 kind, pc, address, value, a, x, y, s, d, p, db, opcode; };
static FdbEvent fdb_events[65536], fdb_entry;
static uint32 fdb_count=0, fdb_dropped=0, fdb_limit=0, fdb_pc_lo=0, fdb_pc_hi=0, fdb_wr_lo=0, fdb_wr_hi=0, fdb_pc=0, fdb_opcode=0;
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_trace_config(uint32 pl,uint32 ph,uint32 wl,uint32 wh,uint32 limit) {
 fdb_count=fdb_dropped=0;fdb_pc_lo=pl;fdb_pc_hi=ph;fdb_wr_lo=wl;fdb_wr_hi=wh;fdb_limit=limit<65536?limit:65536;
}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_trace_count(void) { return fdb_count; }
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_trace_dropped(void) { return fdb_dropped; }
extern "C" __attribute__((visibility("default"))) const FdbEvent *fdisbull_snes_trace_events(void) { return fdb_events; }
static void fdb_event(uint32 kind,uint32 address,uint32 value) {
 if (fdb_count>=fdb_limit) { if (fdb_dropped!=0xffffffffU) fdb_dropped++; return; }
 FdbEvent event=fdb_entry;event.kind=kind;event.address=address;event.value=value;
 fdb_events[fdb_count++]=event;
}
extern "C" void fdisbull_snes_trace_write(uint32 address,uint32 value) {
 if (address>=fdb_wr_lo && address<fdb_wr_hi) fdb_event(2,address,value);
}
static void fdb_instruction(uint32 pc,uint32 opcode) {
 fdb_pc=pc;fdb_opcode=opcode;
 uint32 p=(Registers.P.W & ~0xc3U) | ICPU._Carry | ((ICPU._Zero==0)<<1) | (ICPU._Negative&0x80) | (ICPU._Overflow<<6);
 fdb_entry={0,pc,0,0,Registers.A.W,Registers.X.W,Registers.Y.W,Registers.S.W,Registers.D.W,p,Registers.DB,opcode};
 if (pc>=fdb_pc_lo && pc<fdb_pc_hi) fdb_event(1,pc,opcode);
}
'''

def replace_once(text, old, new):
    if text.count(old)!=1: raise ValueError('source anchor mismatch')
    return text.replace(old,new,1)

def main(root):
    root=Path(root).resolve()
    project=Path(__file__).resolve().parents[1]
    if root==project or project in root.parents:
        raise ValueError('instrumentation requires a private external source checkout')
    got=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if got!=COMMIT: raise ValueError('unexpected SNES9x revision')
    cpu=root/'cpuexec.cpp'; mem=root/'getset.h'
    for path in (cpu,mem):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=SOURCE_HASHES[path.name]:
            raise ValueError(f'unexpected source content: {path.name}')
    c=cpu.read_text();h=mem.read_text()
    c=replace_once(c,'static inline void S9xReschedule (void);',SOURCE+'\nstatic inline void S9xReschedule (void);')
    c=replace_once(c,'\t\tRegisters.PCw++;\n\t\t(*Opcodes[Op].S9xOpcode)();','\t\tfdb_instruction(Registers.PBPC & 0xffffffU, Op);\n\t\tRegisters.PCw++;\n\t\t(*Opcodes[Op].S9xOpcode)();')
    h=replace_once(h,'extern uint8\tOpenBus;','extern "C" void fdisbull_snes_trace_write(uint32, uint32);\nextern uint8\tOpenBus;')
    h=replace_once(h,'\t\t*(SetAddress + (Address & 0xffff)) = Byte;','\t\tfdisbull_snes_trace_write(Address & 0xffffffU, Byte);\n\t\t*(SetAddress + (Address & 0xffff)) = Byte;')
    h=replace_once(h,'\t\tWRITE_WORD(SetAddress + (Address & 0xffff), Word);','\t\tif (!o) { fdisbull_snes_trace_write(Address & 0xffffffU, Word & 255U); fdisbull_snes_trace_write((Address+1) & 0xffffffU, Word >> 8); }\n\t\telse { fdisbull_snes_trace_write((Address+1) & 0xffffffU, Word >> 8); fdisbull_snes_trace_write(Address & 0xffffffU, Word & 255U); }\n\t\tWRITE_WORD(SetAddress + (Address & 0xffff), Word);')
    cpu.write_text(c);mem.write_text(h)

if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: snes9x_trace_adapter.py PRIVATE_CHECKOUT')
    main(sys.argv[1])
