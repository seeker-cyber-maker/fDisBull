#!/usr/bin/env python3
"""Observe Shadowrun's RNG hardware reads in one pinned private SNES9x core.

The journal observes every $80:C530 invocation, including callers outside the
task VM. Counter bytes are captured at their actual separate bus reads; PPU
values are captured after S9xGetPPU returns. No register, memory, cycle count,
input or dispatch path is changed. Raw journal and optional modal RAM stay
private. Seed/result fields are verification metadata, never replay inputs.
"""
from pathlib import Path
import sys

from snes9x_controller_adapter import main as add_controller
from snes9x_trace_adapter import replace_once

SOURCE = r'''
struct FdbHardwareSample {
 uint32 ordinal,serial,boundary,caller,task,return_pc,parent_return,
 seed_before,nmi_low,nmi_high,beam_h,beam_v,latch,result,seed_after,seen;
};
static FdbHardwareSample fdb_hardware_samples[1024],fdb_hardware_active;
static uint32 fdb_hardware_enabled=0,fdb_hardware_modal_enabled=0,
 fdb_hardware_count=0,fdb_hardware_dropped=0,fdb_hardware_ordinal=0,
 fdb_hardware_boundary=0,fdb_hardware_busy=0,fdb_hardware_modal_count=0,
 fdb_hardware_modal_dropped=0;
static uint8 fdb_hardware_modal_ram[32][131072];
struct FdbHardwareModal {uint32 boundary,serial,kind,pc;};
static FdbHardwareModal fdb_hardware_modals[32];
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_hardware_config(uint32 enabled,uint32 modal) {
 fdb_hardware_enabled=enabled;fdb_hardware_modal_enabled=modal;
 fdb_hardware_count=fdb_hardware_dropped=fdb_hardware_ordinal=0;
 fdb_hardware_boundary=fdb_hardware_busy=fdb_hardware_modal_count=fdb_hardware_modal_dropped=0;
}
extern "C" __attribute__((visibility("default"))) void fdisbull_snes_hardware_clear(void) {
 fdb_hardware_count=fdb_hardware_dropped=fdb_hardware_modal_count=fdb_hardware_modal_dropped=0;
}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_hardware_count(void) {return fdb_hardware_count;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_hardware_dropped(void) {return fdb_hardware_dropped;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_hardware_busy(void) {return fdb_hardware_busy;}
extern "C" __attribute__((visibility("default"))) const FdbHardwareSample *fdisbull_snes_hardware_samples(void) {return fdb_hardware_samples;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_hardware_modal_count(void) {return fdb_hardware_modal_count;}
extern "C" __attribute__((visibility("default"))) uint32 fdisbull_snes_hardware_modal_dropped(void) {return fdb_hardware_modal_dropped;}
extern "C" __attribute__((visibility("default"))) const FdbHardwareModal *fdisbull_snes_hardware_modals(void) {return fdb_hardware_modals;}
extern "C" __attribute__((visibility("default"))) const uint8 *fdisbull_snes_hardware_modal_ram(uint32 i) {return i<fdb_hardware_modal_count?fdb_hardware_modal_ram[i]:NULL;}
static void fdb_hardware_controller_capture(uint32 kind,uint32 pc) {
 if(!fdb_hardware_enabled || kind==2U)return;
 ++fdb_hardware_boundary;
 if(kind<3U || !fdb_hardware_modal_enabled)return;
 if(fdb_hardware_modal_count>=32U){++fdb_hardware_modal_dropped;return;}
 uint32 i=fdb_hardware_modal_count++;
 fdb_hardware_modals[i]={fdb_hardware_boundary,fdb_checkpoint_serial,kind,pc};
 memcpy(fdb_hardware_modal_ram[i],Memory.RAM,131072);
}
extern "C" void fdisbull_snes_hardware_read(uint32 address,uint32 value) {
 if(!fdb_hardware_enabled || !fdb_hardware_busy)return;
 if(fdb_pc==0x80c536U && address==0x2137U){fdb_hardware_active.latch=value;fdb_hardware_active.seen|=1U;}
 else if(fdb_pc==0x80c53cU && address==0x7e1c92U){fdb_hardware_active.nmi_low=value;fdb_hardware_active.seen|=2U;}
 else if(fdb_pc==0x80c542U && address==0x213cU){fdb_hardware_active.beam_h=value;fdb_hardware_active.seen|=4U;}
 else if(fdb_pc==0x80c549U && address==0x7e1c93U){fdb_hardware_active.nmi_high=value;fdb_hardware_active.seen|=8U;}
 else if(fdb_pc==0x80c54fU && address==0x213dU){fdb_hardware_active.beam_v=value;fdb_hardware_active.seen|=16U;}
}
static void fdb_hardware_instruction(uint32 pc) {
 if(!fdb_hardware_enabled)return;
 if(pc==0x80c530U) {
  if(fdb_hardware_busy){++fdb_hardware_dropped;return;}
  uint32 sp=Registers.S.W,ret=0,parent=0;
  if(sp<=0x1ffbU){ret=(uint32)Memory.RAM[sp+1U]|((uint32)Memory.RAM[sp+2U]<<8);parent=(uint32)Memory.RAM[sp+3U]|((uint32)Memory.RAM[sp+4U]<<8);}
  uint32 task=(uint32)Memory.RAM[0x26cU]|((uint32)Memory.RAM[0x26dU]<<8);
  uint32 caller=ret==0xff11U?1U:(ret==0xc504U?2U:(ret==0xf4d2U?3U:0U));
  fdb_hardware_active={++fdb_hardware_ordinal,fdb_checkpoint_serial,fdb_hardware_boundary,caller,task,ret,parent,
   Memory.RAM[0x1d04U],0U,0U,0U,0U,0U,0U,0U,0U};
  fdb_hardware_busy=1U;
 } else if(pc==0x80c55cU && fdb_hardware_busy) {
  fdb_hardware_active.result=(uint32)Memory.RAM[0U]|((uint32)Memory.RAM[1U]<<8);
  fdb_hardware_active.seed_after=Memory.RAM[0x1d04U];
  if(fdb_hardware_count>=1024U)++fdb_hardware_dropped;
  else fdb_hardware_samples[fdb_hardware_count++]=fdb_hardware_active;
  fdb_hardware_busy=0U;
 }
}
'''


def main(root):
    add_controller(root)
    root = Path(root).resolve()
    cpu, mem = root / 'cpuexec.cpp', root / 'getset.h'
    c, h = cpu.read_text(), mem.read_text()
    c = replace_once(c, 'struct FdbControllerSample {',
                     'static void fdb_hardware_controller_capture(uint32,uint32);\nstruct FdbControllerSample {')
    c = replace_once(c, ' fdb_controller_samples[fdb_controller_count++]=sample;',
                     ' fdb_controller_samples[fdb_controller_count++]=sample;\n fdb_hardware_controller_capture(kind,pc);')
    c = replace_once(c, 'static void fdb_instruction(uint32 pc,uint32 opcode) {',
                     SOURCE + '\nstatic void fdb_instruction(uint32 pc,uint32 opcode) {')
    c = replace_once(c, ' fdb_controller_capture(pc);',
                     ' fdb_controller_capture(pc);\n fdb_hardware_instruction(pc);')
    h = replace_once(h, 'extern uint8\tOpenBus;',
                     'extern "C" void fdisbull_snes_hardware_read(uint32,uint32);\nextern uint8\tOpenBus;')
    h = replace_once(h, '\t\tbyte = *(GetAddress + (Address & 0xffff));',
                     '\t\tbyte = *(GetAddress + (Address & 0xffff));\n\t\tfdisbull_snes_hardware_read(Address & 0xffffffU,byte);')
    h = replace_once(h, '\t\t\tbyte = S9xGetPPU(Address & 0xffff);',
                     '\t\t\tbyte = S9xGetPPU(Address & 0xffff);\n\t\t\tfdisbull_snes_hardware_read(Address & 0xffff,byte);')
    cpu.write_text(c)
    mem.write_text(h)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: snes9x_hardware_adapter.py FRESH_PRIVATE_CHECKOUT')
    main(sys.argv[1])
