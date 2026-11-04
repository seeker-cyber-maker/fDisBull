#!/usr/bin/env python3
"""Add a read-only main-loop controller journal to a pinned private SNES9x core.

The $809D9D entry is accepted only for the main loop's $80963A JSR, whose
native stack return word is $963C. $80DE91 is recorded only for the selected
player. Values and checkpoint serial are observed before each source
instruction; no guest state or input is changed.
"""
from pathlib import Path
import sys

from snes9x_checkpoint_adapter import main as add_checkpoints
from snes9x_trace_adapter import replace_once

SOURCE = r'''
struct FdbControllerSample { uint32 kind, serial, held, previous, edge, actor; };
static FdbControllerSample fdb_controller_samples[32];
static uint32 fdb_controller_enabled=0, fdb_controller_count=0, fdb_controller_dropped=0;
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_controller_config(uint32 enabled) {
 fdb_controller_enabled=enabled;fdb_controller_count=fdb_controller_dropped=0;
}
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_controller_clear(void) {
 fdb_controller_count=fdb_controller_dropped=0;
}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_controller_count(void) {return fdb_controller_count;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_controller_dropped(void) {return fdb_controller_dropped;}
extern "C" __attribute__((visibility("default"))) const FdbControllerSample *fdisbull_snes_controller_samples(void) {return fdb_controller_samples;}
static void fdb_controller_capture(uint32 pc) {
 if(!fdb_controller_enabled || !fdb_checkpoint_serial)return;
 uint32 kind=0, actor=0xffffffffU;
 if(pc==0x809d9dU) {
  uint32 sp=Registers.S.W;
  if(sp>0x1ffdU)return;
  uint32 ret=(uint32)Memory.RAM[sp+1U]|((uint32)Memory.RAM[sp+2U]<<8);
  if(ret!=0x963cU)return;
  kind=1U;
 } else if(pc==0x80de91U) {
  actor=Registers.Y.W;
  uint32 player=(uint32)Memory.RAM[0xcdeU]|((uint32)Memory.RAM[0xcdfU]<<8);
  if(actor!=player || actor>=88U || (actor&1U))return;
  kind=2U;
 } else return;
 if(fdb_controller_count>=32U) {if(fdb_controller_dropped!=0xffffffffU)fdb_controller_dropped++;return;}
 FdbControllerSample sample={kind,fdb_checkpoint_serial,
  (uint32)Memory.RAM[0x1e6U]|((uint32)Memory.RAM[0x1e7U]<<8),
  (uint32)Memory.RAM[0x1e8U]|((uint32)Memory.RAM[0x1e9U]<<8),
  (uint32)Memory.RAM[0x1eaU]|((uint32)Memory.RAM[0x1ebU]<<8),actor};
 fdb_controller_samples[fdb_controller_count++]=sample;
}
'''


def main(root):
    add_checkpoints(root)
    path = Path(root).resolve() / 'cpuexec.cpp'
    text = path.read_text()
    text = replace_once(text, 'static void fdb_instruction(uint32 pc,uint32 opcode) {',
                        SOURCE + '\nstatic void fdb_instruction(uint32 pc,uint32 opcode) {')
    text = replace_once(text, ' fdb_checkpoint_capture(pc);',
                        ' fdb_checkpoint_capture(pc);\n fdb_controller_capture(pc);')
    path.write_text(text)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: snes9x_controller_adapter.py FRESH_PRIVATE_CHECKOUT')
    main(sys.argv[1])
