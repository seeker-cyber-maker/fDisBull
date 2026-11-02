#!/usr/bin/env python3
"""Capture a bounded Genesis presentation trace on the pinned Genesis Plus GX.

A disposable worker forwards the core's VDP data-write handler and samples
its 68000 PC. A separate control runs the same inputs. This is an adapted
presentation check, not original pixel parity or a physical VBlank proof.
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

PINNED_CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'

def sha(data): return hashlib.sha256(data).hexdigest()
def identity(p):
 data=p.read_bytes();return {'sha256':sha(data),'size':len(data)}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--core',required=True,type=Path);p.add_argument('--cartridge',required=True,type=Path);p.add_argument('--manifest',required=True,type=Path);p.add_argument('--labels',required=True,type=Path);p.add_argument('--inputs',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
 p.add_argument('--frames',type=int,default=1200);p.add_argument('--measure-start',type=int,default=260);p.add_argument('--hook-start',type=int,default=100)
 a=p.parse_args();root=Path(__file__).resolve().parents[1];out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 if not 0<=a.hook_start<=a.measure_start<a.frames<=10000:raise ValueError('invalid measurement frame bounds')
 core=a.core.resolve();rom=a.cartridge.resolve();manifest=a.manifest.resolve();labels=a.labels.resolve();inputs=a.inputs.resolve()
 paths={'core':core,'cartridge':rom,'manifest':manifest,'labels':labels,'inputs':inputs,'host':root/'scripts/check_console_udc.py','renderer':root/'src/fdisbull/game_sources/genesis_game_renderer.c','script':Path(__file__).resolve()}
 before={name:identity(path) for name,path in paths.items()}
 if before['core']['sha256']!=PINNED_CORE:raise ValueError('unsupported Genesis core identity')
 meta=json.loads(manifest.read_text())
 if meta.get('format')!='fdisbull-genesis-game-1' or meta.get('rom_sha256')!=before['cartridge']['sha256']:raise ValueError('cartridge does not match Genesis game manifest')
 if meta.get('adapter_sources',{}).get('genesis_game_renderer.c')!=before['renderer']['sha256']:raise ValueError('renderer source differs from cartridge manifest')
 symbols={name:int(address,16) for address,name in re.findall(r'^([0-9a-fA-F]+)\s+\w\s+(\w+)$',labels.read_text(),re.M)}
 names={'genesis_render_epoch':2,'genesis_sprite_count':1,'genesis_sprites':252,'genesis_hud':24,'genesis_palettes':256,'genesis_plane':256}
 if any(n not in symbols for n in names) or 'genesis_present' not in symbols:raise ValueError('renderer symbols missing')
 later=sorted(v for v in symbols.values() if v>symbols['genesis_present'] and v<0x200000)
 if not later:raise ValueError('cannot determine presentation code boundary')
 pc_start,pc_end=symbols['genesis_present'],later[0]
 offsets={name:symbols[name]&0xffff for name in names};base=min(offsets.values())&~1;end=max(offsets[n]+size for n,size in names.items());length=(end-base+1)&~1
 if length>1024:raise ValueError('staging layout exceeds bounded watch')
 watches=[{'name':'staging','memory_id':2,'offset':base,'length':length},{'name':'debug','memory_id':2,'offset':meta['debug']['base'],'length':48}]
 out.mkdir(parents=True);(out/'watches.json').write_text(json.dumps(watches))
 host=paths['host'].read_text();(out/'control-host.py').write_text(host)
 instrumented=host.replace('    frames_ran=0\n','    frames_ran=0\n    vdp_counts=[0]*args.frames\n    vdp_pcs={}\n    vdp_hook_ref=[]\n')
 old='''        lib.retro_run()
        frames_ran=i+1'''
 new=f'''        if i=={a.hook_start}:
            slot=C.c_void_p.in_dll(lib,'vdp_68k_data_w')
            signature=C.CFUNCTYPE(None,C.c_uint)
            original=signature(slot.value)
            lib.m68k_get_reg.argtypes=[C.c_int]
            lib.m68k_get_reg.restype=C.c_uint
            @signature
            def observed_write(value):
                vdp_counts[current[0]]+=1
                pc=lib.m68k_get_reg(16)
                vdp_pcs[pc]=vdp_pcs.get(pc,0)+1
                original(value)
            vdp_hook_ref.extend((slot,original,observed_write))
            slot.value=C.cast(observed_write,C.c_void_p).value
        lib.retro_run()
        if i>={a.hook_start} and slot.value!=C.cast(observed_write,C.c_void_p).value:
            raise RuntimeError('VDP write hook was replaced')
        frames_ran=i+1'''
 if instrumented.count(old)!=1:raise ValueError('host instrument point changed')
 instrumented=instrumented.replace(old,new)
 old='''        if i in selected_frames:
            if frame[0] is None:'''
 new='''        if i in selected_frames:
            for symbol,size in (('vram',65536),('cram',128),('sat',1024),('reg',32)):
                (out/f'{symbol}-{i:06d}.bin').write_bytes(bytes((C.c_ubyte*size).in_dll(lib,symbol)))
            if frame[0] is None:'''
 if instrumented.count(old)!=1:raise ValueError('host snapshot point changed')
 instrumented=instrumented.replace(old,new)
 old='    trace_bytes = (json.dumps('
 if instrumented.count(old)!=1:raise ValueError('host trace point changed')
 instrumented=instrumented.replace(old,"    (out/'vdp-counts.json').write_text(json.dumps(vdp_counts)+'\\n')\n    (out/'vdp-pcs.json').write_text(json.dumps(vdp_pcs)+'\\n')\n"+old)
 (out/'instrumented-host.py').write_text(instrumented)
 frames=sorted({x for x in (100,180,260,420,600,800,1100,a.frames-1) if x<a.frames})
 common=['--core',str(core),'--rom',str(rom),'--system','genesis','--frames',str(a.frames),'--inputs',str(inputs),'--watch',str(out/'watches.json'),'--capture-audio','--frame-images',','.join(map(str,frames)),'--timeout','120']
 for name,script in [('control','control-host.py'),('observed','instrumented-host.py')]:
  run=subprocess.run([sys.executable,str(out/script),*common,'--output',str(out/name)],capture_output=True,text=True,timeout=150)
  (out/f'{name}-run.txt').write_text(run.stdout+run.stderr)
  if run.returncode:raise RuntimeError(f'{name} worker failed: {run.stderr[-1500:]}')
 control=out/'control';obs=out/'observed';observed=json.loads((obs/'receipt.json').read_text());trace=json.loads((obs/'ram_trace.json').read_text());counts=json.loads((obs/'vdp-counts.json').read_text());pcs=json.loads((obs/'vdp-pcs.json').read_text())
 neutral={n:(control/n).read_bytes()==(obs/n).read_bytes() for n in ('state.bin','system_ram.bin','audio.wav','frame.png','ram_trace.json')}
 statea=(control/'state.bin').read_bytes();stateb=(obs/'state.bin').read_bytes();state_diff=sum(x!=y for x,y in zip(statea,stateb)) if len(statea)==len(stateb) else None
 pc_values={int(k):v for k,v in pcs.items()};outside={hex(k):v for k,v in pc_values.items() if not pc_start<=k<pc_end}
 final=a.frames-1;raw=bytes.fromhex(trace['frames'][final]['raw']['staging']);read=lambda addr:raw[(addr-base)^1]
 plane=[read(offsets['genesis_plane']+i) for i in range(256)];pal=[read(offsets['genesis_palettes']+i) for i in range(256)];hud=[read(offsets['genesis_hud']+i) for i in range(24)];sprites=[read(offsets['genesis_sprites']+i) for i in range(252)];count=read(offsets['genesis_sprite_count']);vram=(obs/f'vram-{final:06d}.bin').read_bytes();word=lambda address:(vram[address^1]<<8)|vram[(address+1)^1]
 terrain_diff=sum(word(0xc000+(12+r)*128+(12+c)*2)!=(((pal[((r&254)+1)*16+(c&254)+1]&3)<<13)|plane[r*16+c]) for r in range(16) for c in range(16))
 hud_diff=sum(word(0xc000+8*128+(8+i)*2)!=hud[i] for i in range(24));sat_diff=0
 if count>63:raise ValueError('invalid captured sprite count')
 if count==0:sat_diff=sum(word(0xd000+i*2)!=0 for i in range(4))
 for i in range(count):
  j=i*4;values=(sprites[j+1]+128,i+1 if i+1<count else 0,((sprites[j+3]&3)<<13)|256|sprites[j+2],sprites[j]+160)
  sat_diff+=sum(word(0xd000+i*8+k*2)!=value for k,value in enumerate(values))
 colors=[0,0x0a40,0x0620,0x0eee,0,0x0c40,0x0c86,0x0eee,0,0x00ae,0x06ee,0x0eee,0,0x000c,0x066e,0x0eee]
 expected=[]
 for i in range(64):
  c=colors[(i>>4)*4+(i&3)] if (i&15)<4 else 0
  expected.append(((c&0xe00)>>3)|((c&0xe0)>>2)|((c&0xe)>>1))
 cram=(obs/f'cram-{final:06d}.bin').read_bytes();cram_diff=sum((cram[i*2]|cram[i*2+1]<<8)!=expected[i] for i in range(64))
 selected=counts[a.measure_start:];num296=sum(x==296 for x in selected);fps=observed['fps']
 debugbase=meta['debug']['base']
 def debug_byte(frame,offset):return bytes.fromhex(trace['frames'][frame]['raw']['debug'])[(offset-debugbase)^1]
 epoch=meta['debug']['logic_epoch'];fault=meta['debug']['fault']
 def epoch_at(frame):return (debug_byte(frame,epoch)<<8)|debug_byte(frame,epoch+1)
 epoch_delta=(epoch_at(a.frames-1)-epoch_at(a.measure_start))&0xffff
 faults=[i for i in range(a.measure_start,a.frames) if debug_byte(i,fault)]
 rates={'frames':len(selected),'exact_296_write_batches':num296,'exact_296_batches_per_second':num296/len(selected)*fps,'counts_by_frame':dict(sorted(Counter(selected).items()))}
 if {name:identity(path) for name,path in paths.items()}!=before:raise RuntimeError('input changed during check')
 core_checks=bool(not outside and num296 and not any((terrain_diff,hud_diff,sat_diff,cram_diff)) and all(neutral[n] for n in ('system_ram.bin','audio.wav','frame.png','ram_trace.json')) and not faults)
 assessment=('pass' if all(neutral.values()) else 'partial') if core_checks else 'inconclusive'
 result={'format':'fdisbull-genesis-presentation-check-1','assessment':assessment,'inputs':before,'frames':a.frames,'measurement_start':a.measure_start,'core_fps':fps,'vdp_write_batches':rates,'logic_epoch':{'delta':epoch_delta,'sample_intervals':a.frames-1-a.measure_start,'rate':epoch_delta/(a.frames-1-a.measure_start)*fps if a.frames-1>a.measure_start else None,'fault_frames':faults},'presentation_pc_range':[pc_start,pc_end],'observed_pc_counts':{hex(k):v for k,v in sorted(pc_values.items())},'outside_presentation_pc':outside,'final_snapshot':{'frame':final,'terrain_word_differences':terrain_diff,'hud_word_differences':hud_diff,'sprite_word_differences':sat_diff,'sprite_count':count,'cram_word_differences':cram_diff},'observer_neutrality':neutral,'serialized_state_differing_bytes':state_diff,'audio':observed.get('audio_capture'),'frame_images':observed.get('frame_images'),'limitations':['frame-boundary snapshots may intersect staging or presentation; nonzero differences are not automatically corruption','observed 296-write batches are bounded for this run and sprite count; they are not a universal presentation rate','the complete presentation boundary is inferred from 296 writes, the linked routine and the tested four-sprite view; the return instruction is not hooked',
                 'same captured frame and audio do not establish original Genesis pixel or waveform parity','serialized-state differences require separate diagnosis; no full observer-neutrality claim','no physical Genesis VBlank timing proof']}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
