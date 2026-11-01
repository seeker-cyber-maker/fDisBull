#!/usr/bin/env python3
"""Measure bounded Genesis batches and compare each to its native staging.

Uses the pinned Genesis Plus GX core in a disposable worker. This checks the
adapted renderer's observed VRAM contents, not physical-hardware deadlines or
original Genesis pixel parity. Inputs and all generated ROMs remain private.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

CORE_SHA='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'

def identity(path):
 data=path.read_bytes()
 return {'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('core','cartridge','manifest','labels','inputs','output'):p.add_argument('--'+name,required=True,type=Path)
 p.add_argument('--renderer',type=Path,help='captured renderer source, defaulting to the current checkout')
 p.add_argument('--patches',type=Path,help='optional finite RAM patches for declared synthetic stress')
 p.add_argument('--watch-state',action='store_true',help='also record native state and publication for assisted seeding checks')
 p.add_argument('--frames',type=int,default=1200);p.add_argument('--measure-start',type=int,default=260)
 a=p.parse_args();root=Path(__file__).resolve().parents[1];out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 if not 1<=a.measure_start<a.frames<=10000:raise ValueError('invalid measurement window')
 paths={n:getattr(a,n).resolve() for n in ('core','cartridge','manifest','labels','inputs')}
 if a.patches:paths['patches']=a.patches.resolve()
 paths.update(host=root/'scripts/check_console_udc.py',renderer=(a.renderer.resolve() if a.renderer else root/'src/fdisbull/game_sources/genesis_game_renderer.c'),script=Path(__file__).resolve())
 ids={k:identity(v) for k,v in paths.items()};meta=json.loads(paths['manifest'].read_text())
 if ids['core']['sha256']!=CORE_SHA:raise ValueError('unsupported core identity')
 if meta.get('format')!='fdisbull-genesis-game-1' or meta.get('rom_sha256')!=ids['cartridge']['sha256']:raise ValueError('manifest/cartridge mismatch')
 if meta['adapter_sources']['genesis_game_renderer.c']!=ids['renderer']['sha256']:raise ValueError('renderer differs from candidate')
 syms={n:int(addr,16) for addr,n in re.findall(r'^([0-9a-fA-F]+)\s+\w\s+(\w+)$',paths['labels'].read_text(),re.M)}
 names={'genesis_plane':256,'genesis_palettes':256,'genesis_hud':24,'genesis_sprites':252,'genesis_sprite_count':1}
 if any(n not in syms for n in names) or 'genesis_present' not in syms:raise ValueError('missing renderer symbols')
 start=syms['genesis_present'];later=sorted(v for v in syms.values() if start<v<0x200000)
 if not later:raise ValueError('missing end of renderer function')
 end=later[0];offsets={n:syms[n]&65535 for n in names}
 out.mkdir(parents=True)
 debug=meta['debug'];debug_base=debug['base']
 if a.watch_state:
  from check_genesis_game import watches_for
  watches,_,_=watches_for(meta)
 else:watches=[{'name':'debug','offset':debug_base,'length':48}]
 (out/'watches.json').write_text(json.dumps(watches))
 host=paths['host'].read_text();old='    frames_ran=0\n';assert host.count(old)==1
 host=host.replace(old,old+'    batch_records=[]\n    current_batch=[None]\n    hook_ref=[]\n')
 old='''        lib.retro_run()
        frames_ran=i+1'''
 injected=f'''        if i=={a.measure_start}:
            slot=C.c_void_p.in_dll(lib,'vdp_68k_data_w')
            sig=C.CFUNCTYPE(None,C.c_uint)
            forward=sig(slot.value)
            lib.m68k_get_reg.argtypes=[C.c_int]
            lib.m68k_get_reg.restype=C.c_uint
            @sig
            def observe(value):
                pc=lib.m68k_get_reg(16)
                line=C.c_ushort.in_dll(lib,'v_counter').value
                if current_batch[0] is None:
                    ram=C.string_at(memory_slice(2,0,65536),65536)
                    current_batch[0]={{'ram':ram,'count':0,'outside':0,'first_line':line,'last_line':line}}
                b=current_batch[0];b['count']+=1;b['last_line']=line
                if not {start}<=pc<{end}:b['outside']+=1
                forward(value)
            hook_ref.extend((slot,forward,observe));slot.value=C.cast(observe,C.c_void_p).value
        current_batch[0]=None
        lib.retro_run()
        if i>={a.measure_start}:
            if slot.value!=C.cast(observe,C.c_void_p).value:raise RuntimeError('VDP hook replaced')
            b=current_batch[0]
            if b is not None:
                ram=b.pop('ram');offsets={offsets!r}
                def byte(name,n):return ram[(offsets[name]+n)^1]
                count=byte('genesis_sprite_count',0)
                expected=280+max(4,4*count)
                b['frame']=i;b['sprite_count']=count;b['expected_words']=expected
                if count>63:raise RuntimeError('invalid sprite count')
                b['min_sprite_y']=min((byte('genesis_sprites',4*n+1) for n in range(count)),default=None)
                vram=(C.c_ubyte*65536).in_dll(lib,'vram')
                def word(addr):return (vram[addr^1]<<8)|vram[(addr+1)^1]
                terrain=0
                for row in range(16):
                    for col in range(16):
                        sample=((row&254)+1)*16+(col&254)+1
                        value=((byte('genesis_palettes',sample)&3)<<13)|byte('genesis_plane',row*16+col)
                        terrain+=word(0xc000+(12+row)*128+(12+col)*2)!=value
                hud=sum(word(0xc000+8*128+(8+x)*2)!=byte('genesis_hud',x) for x in range(24))
                sat=0
                for n in range(max(1,count)):
                    j=n*4
                    vals=(byte('genesis_sprites',j+1)+128,n+1 if n+1<count else 0,((byte('genesis_sprites',j+3)&3)<<13)|256|byte('genesis_sprites',j+2),byte('genesis_sprites',j)+160) if count else (0,0,0,0)
                    sat+=sum(word(0xd000+n*8+k*2)!=v for k,v in enumerate(vals))
                b.update(terrain_differences=terrain,hud_differences=hud,sprite_differences=sat)
                batch_records.append(b)
        frames_ran=i+1'''
 if host.count(old)!=1:raise ValueError('host instrumentation point changed')
 host=host.replace(old,injected)
 old='    trace_bytes = (json.dumps('
 if host.count(old)!=1:raise ValueError('host result point changed')
 host=host.replace(old,"    (out/'batches.json').write_text(json.dumps(batch_records)+'\\n')\n"+old)
 (out/'worker.py').write_text(host)
 cmd=[sys.executable,str(out/'worker.py'),'--core',str(paths['core']),'--rom',str(paths['cartridge']),'--system','genesis','--frames',str(a.frames),'--inputs',str(paths['inputs']),'--watch',str(out/'watches.json'),'--output',str(out/'observed')]
 if a.patches:cmd.extend(('--patches',str(paths['patches'])))
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=150);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError('native worker failed: '+run.stderr[-2000:])
 records=json.loads((out/'observed/batches.json').read_text());receipt=json.loads((out/'observed/receipt.json').read_text())
 trace=json.loads((out/'observed/ram_trace.json').read_text())['frames']
 def debug_byte(frame,offset):
  raw=trace[frame]['raw'];name='debug0' if a.watch_state else 'debug'
  return bytes.fromhex(raw[name])[(offset-debug_base)^1]
 def epoch(frame):return (debug_byte(frame,debug['logic_epoch'])<<8)|debug_byte(frame,debug['logic_epoch']+1)
 epoch_delta=(epoch(a.frames-1)-epoch(a.measure_start))&65535
 faults=[i for i in range(a.measure_start,a.frames) if debug_byte(i,debug['fault'])]
 complete=[r for r in records if r['count']==r['expected_words'] and not r['outside']]
 errors=[r for r in complete if r['terrain_differences'] or r['hud_differences'] or r['sprite_differences']]
 if {k:identity(v) for k,v in paths.items()}!=ids:raise RuntimeError('input changed during run')
 result={'format':'fdisbull-genesis-performance-1','inputs':ids,'frames':a.frames,'measure_start':a.measure_start,'fps':receipt['fps'],'logic_epoch_delta':epoch_delta,'logic_sample_intervals':a.frames-1-a.measure_start,'logic_updates_per_second':epoch_delta/(a.frames-1-a.measure_start)*receipt['fps'],'fault_frames':faults,'frames_with_writes':len(records),'complete_batches':len(complete),'complete_batches_per_second':len(complete)/(a.frames-a.measure_start)*receipt['fps'],'batch_size_distribution':dict(sorted(Counter(r['count'] for r in records).items())),'complete_batch_mismatches':len(errors),'mismatch_examples':errors[:5], 'first_line_distribution':dict(sorted(Counter(r['first_line'] for r in complete).items())),'last_line_distribution':dict(sorted(Counter(r['last_line'] for r in complete).items())),'minimum_staged_sprite_y':min((r['min_sprite_y'] for r in complete if r['min_sprite_y'] is not None),default=None),'limitations':['complete batch means the expected number of data writes within one sampled core frame, not a hooked return instruction','VRAM is compared at the frame boundary to staging captured at the first data write; split batches are recorded but not compared','VDP scanline observations are emulator measurements, not physical-hardware deadline proof','minimum sprite y is a staged coordinate, not evidence of a hardware sprite-fetch deadline','adapted presentation, not original Genesis pixel parity','observer neutrality must be assessed separately']}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if errors or faults:raise RuntimeError('native VRAM mismatch or diagnostic fault')
if __name__=='__main__':main()
