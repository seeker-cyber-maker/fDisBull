#!/usr/bin/env python3
"""Add bounded instruction-entry WRAM checkpoints to the pinned private core.

Run on a fresh private checkout. The ordinary trace adapter establishes the
revision and source anchors first. Checkpoints observe Memory.RAM; they do not
change emulated registers, memory, cycles or instruction dispatch.
"""
from pathlib import Path
import sys

from snes9x_trace_adapter import main as add_trace, replace_once

SOURCE=r'''
static uint8 fdb_checkpoints[8][131072];
static FdbEvent fdb_checkpoint_registers[8];
static uint32 fdb_checkpoint_serials[8];
static uint32 fdb_checkpoint_pc=0, fdb_checkpoint_limit=0, fdb_checkpoint_count=0, fdb_checkpoint_dropped=0, fdb_checkpoint_serial=0;
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_checkpoint_config(uint32 pc,uint32 limit) {
 fdb_checkpoint_pc=pc;fdb_checkpoint_limit=limit<8?limit:8;fdb_checkpoint_count=fdb_checkpoint_dropped=fdb_checkpoint_serial=0;
}
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_checkpoint_clear(void) {fdb_checkpoint_count=fdb_checkpoint_dropped=0;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_checkpoint_count(void) {return fdb_checkpoint_count;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_checkpoint_dropped(void) {return fdb_checkpoint_dropped;}
extern "C" __attribute__((visibility("default"))) const uint8 *fdisbull_snes_checkpoint_ram(uint32 i) {return i<fdb_checkpoint_count?fdb_checkpoints[i]:NULL;}
extern "C" __attribute__((visibility("default"))) const FdbEvent *fdisbull_snes_checkpoint_registers(uint32 i) {return i<fdb_checkpoint_count?&fdb_checkpoint_registers[i]:NULL;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_checkpoint_serial(uint32 i) {return i<fdb_checkpoint_count?fdb_checkpoint_serials[i]:0;}
static void fdb_checkpoint_capture(uint32 pc) {
 if(!fdb_checkpoint_pc || pc!=fdb_checkpoint_pc)return;
 fdb_checkpoint_serial++;
 if(fdb_checkpoint_count>=fdb_checkpoint_limit) {if(fdb_checkpoint_dropped!=0xffffffffU)fdb_checkpoint_dropped++;return;}
 uint32 i=fdb_checkpoint_count++;
 memcpy(fdb_checkpoints[i],Memory.RAM,131072);
 fdb_checkpoint_registers[i]=fdb_entry;fdb_checkpoint_serials[i]=fdb_checkpoint_serial;
}
'''


def main(root):
    add_trace(root)
    path=Path(root).resolve()/'cpuexec.cpp'
    text=path.read_text()
    text=replace_once(text,'static void fdb_instruction(uint32 pc,uint32 opcode) {',
                      SOURCE+'\nstatic void fdb_instruction(uint32 pc,uint32 opcode) {')
    text=replace_once(text,' if (pc>=fdb_pc_lo && pc<fdb_pc_hi) fdb_event(1,pc,opcode);',
                      ' fdb_checkpoint_capture(pc);\n if (pc>=fdb_pc_lo && pc<fdb_pc_hi) fdb_event(1,pc,opcode);')
    path.write_text(text)


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: snes9x_checkpoint_adapter.py FRESH_PRIVATE_CHECKOUT')
    main(sys.argv[1])
