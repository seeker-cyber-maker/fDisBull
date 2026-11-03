#!/usr/bin/env python3
"""Check the authored 68000 publication copy on the pinned native core.

Uses a private diagnostic cartridge: no production source is modified. It
covers non-overlapping buffers, all four parity pairs and lengths 0..260,
including full destination canaries and an unchanged source.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
import fdisbull.udc_genesis_game as backend
from fdisbull.udl_miniplanets_full import checked_rom

CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
HARNESS='''
extern void genesis_copy_bytes(volatile u8 *,const volatile u8 *,u16);
static u8 probe_src[268] __attribute__((aligned(4)));
static u8 probe_dst[268] __attribute__((aligned(4)));
static void check_copy_native(void) {
  u16 a,b,n,i,cases=0;
  volatile u16 *r=(volatile u16*)0xff1b80UL;
  r[0]=0;r[1]=0;
  for(a=0;a<2;a++)for(b=0;b<2;b++)for(n=0;n<=260;n++){
    for(i=0;i<268;i++){probe_src[i]=(u8)(i*37+19);probe_dst[i]=0x5a;}
    genesis_copy_bytes(probe_dst+2+b,probe_src+2+a,n);
    for(i=0;i<268;i++){
      u8 expected=(i>=2+b && i<2+b+n)?(u8)((i-b+a)*37+19):0x5a;
      if(probe_dst[i]!=expected || probe_src[i]!=(u8)(i*37+19)){r[0]=0xbad0;r[1]=cases;return;}
    }
    cases++;
  }
  r[1]=cases;r[0]=0x600d;
}
'''
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('core','rom','program','m68k-root','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();root=Path(__file__).resolve().parents[1];out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 if sha(a.core.read_bytes())!=CORE:raise ValueError('unsupported core identity')
 rom=checked_rom(a.rom.read_bytes());program=json.loads(a.program.read_text());source=backend.SOURCE_DIR
 captured={n:(source/n).read_bytes() for n in backend.ADAPTERS};out.mkdir(parents=True);adapters=out/'adapters';adapters.mkdir()
 for n,data in captured.items():(adapters/n).write_bytes(data)
 pform=adapters/'genesis_game_platform.c';s=pform.read_text();assert s.count('#include "game_api.h"')==1 and s.count('    hardware_init();')==1
 pform.write_text(s.replace('#include "game_api.h"','#include "game_api.h"'+HARNESS,1).replace('    hardware_init();','    check_copy_native();\n    hardware_init();',1))
 backend.SOURCE_DIR=adapters
 try:manifest=backend.build_genesis_game(program,rom,out/'diagnostic',m68k_root=a.m68k_root)
 finally:backend.SOURCE_DIR=source
 watch=out/'watches.json';watch.write_text(json.dumps([{'name':'copy','offset':0x1b80,'length':4}]))
 cmd=[sys.executable,str(root/'scripts/check_console_udc.py'),'--core',str(a.core),'--rom',str(out/'diagnostic/program.md'),'--system','genesis','--frames','600','--watch',str(watch),'--output',str(out/'run')]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=150)
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
 trace=json.loads((out/'run/ram_trace.json').read_text())['frames'];passes=[x['frame'] for x in trace if x['raw']['copy']=='0d601404']
 if not passes or trace[-1]['raw']['copy']!='0d601404':raise AssertionError('native copy canary check failed or timed out')
 if any((source/n).read_bytes()!=data for n,data in captured.items()):raise RuntimeError('adapter changed during check')
 result={'format':'fdisbull-genesis-copy-check-1','status':'passed','cases':1044,'lengths':'0..260','parities':'all four source/destination combinations','source_sha256':sha(rom),'helper_sha256':sha(captured['genesis_game_copy.s']),'diagnostic_rom_sha256':manifest['rom_sha256'],'core_sha256':CORE,'harness_sha256':sha(HARNESS.encode()),'script_sha256':sha(Path(__file__).read_bytes()),'first_pass_frame':passes[0],'scope':'non-overlapping buffers; compares all destination bytes and unchanged source; not a memmove contract'}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
