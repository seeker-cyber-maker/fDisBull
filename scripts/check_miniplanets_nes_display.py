#!/usr/bin/env python3
"""Measure FCEUmm NTSC display writes and forwarding-observer neutrality.

This pins the core whose PPU frame scheduling and exported ABI were inspected.
Output is private: events and observations can contain game-derived data.
Writes are dated at instruction completion (DMA writes use core cycle accounting).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from check_miniplanets_native import _private_output

CORE_SHA='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
HERE=Path(__file__).resolve().parent

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--core',required=True);p.add_argument('--rom',required=True);p.add_argument('--output',required=True)
 p.add_argument('--frames',type=int,default=300);p.add_argument('--warmup',type=int,default=40)
 p.add_argument('--patches');p.add_argument('--inputs');p.add_argument('--watch');p.add_argument('--active-nt-offset',type=lambda s:int(s,0))
 p.add_argument('--dmc-evidence',action='store_true',help='Observe pinned-core four-read DMC fetch signatures without changing reads')
 p.add_argument('--require-safe-display',action='store_true',help='Fail on timing/coherence/stack violations or missing observations')
 p.add_argument('--coherence-offsets',nargs=4,type=lambda s:int(s,0),metavar=('PLANE','HUD','ATTRS','OAM_PAGE'),help='SRAM offsets for immutable completed view')
 a=p.parse_args()
 paths={'core':a.core,'rom':a.rom,'checker':__file__,'host':HERE/'check_console_udc.py','observer_source':HERE/'miniplanets_display_observer.c','private_output_helper':HERE/'check_miniplanets_native.py'}
 paths.update({name:value for name,value in [('patches',a.patches),('inputs',a.inputs),('watch',a.watch)] if value})
 if not 0<=a.warmup<a.frames-1: raise ValueError('at least two sampled frames are required after warmup')
 if a.require_safe_display and (a.active_nt_offset is None or not a.coherence_offsets or not a.watch):
  raise ValueError('safe display gate requires active NT offset, coherence offsets, and publication watch')
 out=_private_output(a.output);out.mkdir()
 capture=out/'captured-inputs';capture.mkdir()
 captured={};identity_before={}
 suffixes={'core':'.dylib','rom':'.nes','checker':'.py','host':'.py','observer_source':'.c','private_output_helper':'.py','patches':'.json','inputs':'.json','watch':'.json'}
 for name,path in paths.items():
  source=Path(path).expanduser().resolve();data=source.read_bytes()
  identity_before[name]={'path':str(source),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
  destination=capture/(name+suffixes[name]);destination.write_bytes(data);captured[name]=destination
 if identity_before['core']['sha256']!=CORE_SHA: raise ValueError('core does not match the inspected FCEUmm build')
 dylib=out/'observer.dylib'
 subprocess.run(['cc','-dynamiclib','-O2','-o',str(dylib),str(captured['observer_source'])],check=True)
 s=captured['host'].read_text()
 before='    trace = []\n    patch_trace = []\n'
 injected='''    class DisplayCPU(C.Structure):
        _fields_=[('tcount',C.c_int32),('PC',C.c_uint16),('A',C.c_uint8),('X',C.c_uint8),('Y',C.c_uint8),('S',C.c_uint8),('P',C.c_uint8),('mooPI',C.c_uint8),('jammed',C.c_uint8),('count',C.c_int32),('IRQlow',C.c_uint32),('DB',C.c_uint8)]
    assert C.sizeof(DisplayCPU)==28 and DisplayCPU.count.offset==16
    display_cpu=DisplayCPU.in_dll(lib,'X')
    display_stamp=C.c_uint32.in_dll(lib,'timestamp')
    display_observer=C.CDLL(os.environ['DISPLAY_OBSERVER'])
    display_observer.setup.argtypes=[C.c_void_p]*4
    display_table=(C.c_void_p*65536).in_dll(lib,'BWrite')
    display_observer.setup(C.addressof(display_table),C.addressof(display_stamp),C.addressof((C.c_uint8*4).in_dll(lib,'PPU')),C.addressof(C.c_uint16.in_dll(lib,'RefreshAddr')))
    if os.environ.get('DISPLAY_COHERENCE'):
        cfg=json.loads(os.environ['DISPLAY_COHERENCE'])
        display_observer.coherence.argtypes=[C.c_void_p]*4+[C.c_uint32]*6
        display_observer.coherence(memory_slice(0,0,8192),memory_slice(2,0,2048),C.addressof((C.c_uint8*256).in_dll(lib,'SPRAM')),C.addressof((C.c_void_p*4).in_dll(lib,'vnapage')),*cfg)
    if os.environ.get('DISPLAY_DMC'):
        display_observer.dmc_setup.argtypes=[C.c_void_p]
        display_observer.dmc_setup(C.addressof((C.c_void_p*65536).in_dll(lib,'ARead')))
    display_observer.stack_setup.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32]
    display_observer.stack_setup(C.addressof(C.c_void_p.in_dll(lib,'MapIRQHook')),C.addressof(display_cpu)+DisplayCPU.S.offset,int(os.environ['DISPLAY_WARMUP']))
    display_observer.start_frame.argtypes=[C.c_uint32,C.c_int32]
'''+before
 if s.count(before)!=1 or s.count('        lib.retro_run()\n')!=1 or s.count('    trace_bytes = (json.dumps(')!=1:raise RuntimeError('host instrumentation points changed')
 s=s.replace(before,injected).replace('        lib.retro_run()\n','        display_observer.start_frame(i,display_cpu.count)\n        lib.retro_run()\n')
 s=s.replace('    trace_bytes = (json.dumps(',"""    display_observer.stack_result.argtypes=[C.c_int]
    display_observer.stack_result.restype=C.c_uint32
    (out/'stack.json').write_text(json.dumps([display_observer.stack_result(i) for i in range(3)]))
    if os.environ.get('DISPLAY_COHERENCE'):
        display_observer.coherence_result.argtypes=[C.c_int]
        display_observer.coherence_result.restype=C.c_uint32
        (out/'coherence.json').write_text(json.dumps([display_observer.coherence_result(i) for i in range(7)]))
    if os.environ.get('DISPLAY_DMC'):
        display_observer.dmc_dump.argtypes=[C.c_char_p]
        if display_observer.dmc_dump(os.fsencode(str(out/'dmc-events.bin'))) < 0: raise RuntimeError('DMC observer failed or overflowed')
    display_observer.dump.argtypes=[C.c_char_p]
    if display_observer.dump(os.fsencode(str(out/'ppu-events.bin'))) < 0: raise RuntimeError('display observer failed or overflowed')
    trace_bytes = (json.dumps(""")
 host=out/'instrumented-host.py';host.write_text(s)
 watches=json.loads(captured['watch'].read_text()) if a.watch else []
 if a.active_nt_offset is not None:
  watches.append({'name':'display_active_nt','memory_id':0,'offset':a.active_nt_offset,'length':1})
 wp=out/'watches.json';wp.write_text(json.dumps(watches))
 common=['--core',str(captured['core']),'--rom',str(captured['rom']),'--system','nes','--frames',str(a.frames),'--watch',str(wp),'--capture-audio']
 for flag,name in [('--patches','patches'),('--inputs','inputs')]:
  if name in captured:common += [flag,str(captured[name])]
 env={**os.environ,'DISPLAY_OBSERVER':str(dylib.resolve()),'DISPLAY_WARMUP':str(a.warmup)}
 env.pop('DISPLAY_DMC',None)
 if a.dmc_evidence:env['DISPLAY_DMC']='1'
 if a.coherence_offsets:
  if a.active_nt_offset is None:raise ValueError('coherence requires active NT offset')
  offsets=[*a.coherence_offsets[:3],a.active_nt_offset,a.coherence_offsets[3]]
  if any(o<0 or o+n>8192 for o,n in zip(offsets,[256,24,16,1,1])):raise ValueError('coherence buffers outside SRAM')
  env['DISPLAY_COHERENCE']=json.dumps([*offsets,a.warmup])
 for name,script in [('observed',host),('control',captured['host'])]:
  subprocess.run([sys.executable,str(script),*common,'--output',str(out/name)],env=env,check=True,stdout=subprocess.DEVNULL)
 neutral={n:digest(out/'observed'/n)==digest(out/'control'/n) for n in ['audio.wav','state.bin','save_ram.bin','system_ram.bin','frame.png','ram_trace.json']}
 raw=(out/'observed'/'ppu-events.bin').read_bytes()
 if len(raw)%20:raise RuntimeError('truncated observer event stream')
 stats={};violations=[]
 for f,t,count,address,refresh,value,mask in struct.iter_unpack('<IIiHHBBxx',raw):
  if f<a.warmup or not mask&0x18:continue
  dot=t*3-count/16
  key=f'{address:04x}';v=stats.setdefault(key,{'count':0,'min_dot':dot,'max_dot':dot,'outside':0})
  v['count']+=1;v['min_dot']=min(v['min_dot'],dot);v['max_dot']=max(v['max_dot'],dot)
  # PPU register writes are bounded conservatively to vblank, including DMA OAM writes.
  if not 341<=dot<7161:
   v['outside']+=1
   if len(violations)<20:violations.append({'frame':f,'dot':dot,'address':key,'ppu_address':refresh})
 dmc=None
 if a.dmc_evidence:
  dmcraw=(out/'observed'/'dmc-events.bin').read_bytes()
  if len(dmcraw)%16:raise RuntimeError('truncated DMC event stream')
  ppu_windows={}
  for f,t,count,address,refresh,value,mask in struct.iter_unpack('<IIiHHBBxx',raw):
   if f>=a.warmup and mask&0x18 and address in (0x2006,0x2007):
    item=ppu_windows.setdefault(f,[t,t]);item[0]=min(item[0],t);item[1]=max(item[1],t)
  fetched=[(f,t,count,address) for f,t,count,address in struct.iter_unpack('<IIiI',dmcraw) if f>=a.warmup]
  overlap=[(f,t,address) for f,t,count,address in fetched if f in ppu_windows and ppu_windows[f][0]<=t<=ppu_windows[f][1]]
  dmc={'fetch_signatures':len(fetched),'frames_with_fetches':len({x[0] for x in fetched}),
       'fetches_during_upload_window':len(overlap),'frames_with_upload_overlap':len({x[0] for x in overlap}),
       'first_upload_overlaps':[{'frame':f,'cpu_cycle':t,'address':address} for f,t,address in overlap[:5]],
       'events_sha256':digest(out/'observed'/'dmc-events.bin'),
       'scope':'lower-bound four consecutive same-address reads one CPU cycle apart; pinned FCEUmm DMCDMA signature. Overlap means fetch completion between first PPU address write and last PPU data write in same host frame; instruction-level timing.'}
 trace=json.loads((out/'observed'/'ram_trace.json').read_text())['frames'];swaps=None
 host_receipt=json.loads((out/'observed'/'receipt.json').read_text())
 fps=host_receipt['fps']; measured_intervals=a.frames-a.warmup-1
 publications=None
 if trace and 'publication' in trace[0]['raw']:
  expected=1; measured=0
  for row in trace:
   data=bytes.fromhex(row['raw']['publication'])
   if len(data)<192:raise ValueError('publication watch shorter than four 48-byte records')
   for _ in range(4):
    start=(expected%4)*48; slot=data[start:start+48]
    number=int.from_bytes(slot[2:4],'little')
    if slot[0]&1 or slot[1]!=1 or number!=expected:
     if number>expected and (number-expected)%4==0:raise ValueError('publication ring overrun')
     break
    if row['frame']>a.warmup:measured+=1
    expected+=1
    if expected>65535:raise ValueError('publication epoch wraps; shorten run')
  publications={'completed_logic_updates':measured,'logic_updates_hz':measured*fps/measured_intervals,
                'scope':'consecutively numbered, even version-1 publication slots; epoch wrap is rejected'}
 if a.active_nt_offset is not None:
  values=[bytes.fromhex(x['raw']['display_active_nt'])[0] for x in trace[a.warmup:]]
  swaps=sum(x!=y for x,y in zip(values,values[1:]))
 coherence=None
 if a.coherence_offsets:
  values=json.loads((out/'observed'/'coherence.json').read_text())
  coherence=dict(zip(['checked_flips','plane_mismatches','hud_mismatches','attribute_mismatches','oam_mismatches','control_mismatches','active_nametable_data_writes'],values))
 stack_values=json.loads((out/'observed'/'stack.json').read_text())
 stack=dict(zip(['minimum_s','possible_downward_wraps','instruction_samples'],stack_values))
 stack['scope']='S sampled once per native instruction, including interrupt entry; wrap signal is heuristic and TXS can also change S'
 after={}
 for name,path in paths.items():
  source=Path(path).expanduser().resolve()
  try:
   data=source.read_bytes();after[name]={'path':str(source),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
  except OSError as e:after[name]={'path':str(source),'error':type(e).__name__}
 capture_after={name:{'sha256':digest(path),'size':path.stat().st_size} for name,path in captured.items()}
 immutable=identity_before==after and all(capture_after[name]['sha256']==identity_before[name]['sha256'] and capture_after[name]['size']==identity_before[name]['size'] for name in captured)
 failures=[]
 if a.require_safe_display:
  if not stats or any(stats.get(key,{}).get('count',0)<=0 for key in ['2000','2003','2004','2005','2006','2007','4014']):failures.append('missing required register observations')
  if any(v['outside'] for v in stats.values()):failures.append('register writes outside vblank')
  if swaps is None or swaps<=0:failures.append('no sampled nametable swaps')
  if not publications or publications['completed_logic_updates']<=0:failures.append('no completed logic publications')
  if not coherence or coherence['checked_flips']<=0:failures.append('no checked completed flips')
  elif any(value for key,value in coherence.items() if key!='checked_flips'):failures.append('display coherence mismatch or active nametable write')
  if coherence and swaps is not None and abs(coherence['checked_flips']-swaps)>1:failures.append('checked and sampled flip counts disagree')
  if stack['instruction_samples']<=0 or not 0<stack['minimum_s']<255:failures.append('invalid stack samples')
  if stack['possible_downward_wraps']:failures.append('possible downward stack wrap')
 receipt={'dmc_evidence':dmc,'input_identity_before':identity_before,'input_identity_after':after,'captured_input_identity_after':capture_after,'inputs_unchanged':immutable,'safe_display_required':a.require_safe_display,'safe_display_failures':failures,'generated_host_sha256':digest(host),'compiled_observer_sha256':digest(dylib),'stack':stack,'coherence':coherence,'format':'miniplanets-fceumm-display-1','rom_sha256':identity_before['rom']['sha256'],'core_sha256':CORE_SHA,'frames':a.frames,'warmup':a.warmup,
  'timing':'NTSC PPU dots from FCEUmm frame boundary; instruction-end timestamps and start X.count phase; valid vblank [341,7161); pre-render excluded',
  'scope':'Writes to $2000-$2007 and $4014 while rendering enabled; DMA $2004 writes included. Scanline batching is accounted for; instruction-level accuracy, not bus-cycle exact.',
  'observer_neutrality':neutral,'registers':stats,'first_violations':violations,'sampled_nt_swaps':swaps,
  'sampled_nt_swaps_hz':None if swaps is None else swaps*fps/measured_intervals,'logic':publications,'core_fps':fps,
  'swap_scope':'once per host frame; requires target proof that active_nt changes only on completed view commit; does not imply different pixels',
  'events_sha256':digest(out/'observed'/'ppu-events.bin')}
 (out/'display-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(out/'display-receipt.json')
 if not immutable:raise SystemExit('input identity changed during run')
 if not all(neutral.values()):raise SystemExit('observer neutrality failed')
 if failures:raise SystemExit('safe display gate failed: '+', '.join(failures))
if __name__=='__main__':main()
