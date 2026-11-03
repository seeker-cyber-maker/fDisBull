#!/usr/bin/env python3
"""Source-bound, assisted stale-warp diagnostic in the real combined NES ROM.

This runs the core's original game code. A continuous wall-clip route uses an
assisted level/page checkpoint and large-Mario seed, then controller input.
Separate pipe-level variants use additional placement/control interventions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.mario_minus_world import CORE_SHA256, identify


def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rom',required=True);parser.add_argument('--core',required=True);parser.add_argument('--output',required=True);a=parser.parse_args()
    rom=Path(a.rom).expanduser().resolve();core=Path(a.core).expanduser().resolve()
    raw=rom.read_bytes();source=identify(raw)
    if sha(core.read_bytes())!=CORE_SHA256:raise ValueError('wrong pinned FCEUmm core')
    output=_private_directory(a.output);output.mkdir()
    host=ROOT/'scripts/check_console_udc.py';host_raw=host.read_bytes()
    (output/'source.nes').write_bytes(raw);(output/'core.dylib').write_bytes(core.read_bytes())
    (output/'host.py').write_bytes(host_raw)
    # Paired runs begin from the same boot and state: page-11 checkpoint and
    # player placement are assisted. Only the experimental warp-control seed
    # differs; no run writes the world number or area pointer directly.
    inputs=[{'start':120,'end':125,'buttons':['START']},
            {'start':450,'end':455,'buttons':['START']},
            {'start':700,'end':705,'buttons':['START']},
            {'start':900,'end':1010,'buttons':['DOWN']}]
    base=[(680,0x760,2),(680,0x75c,1),(680,0x75b,11),
          (900,0x86,40),(900,0xce,128)]
    (output/'inputs.json').write_text(json.dumps(inputs))
    watch=[{'name':'low','offset':0,'length':1024},{'name':'high','offset':1024,'length':1024}]
    (output/'watch.json').write_text(json.dumps(watch))
    host_text=host_raw.decode();needle='    trace = []\n'
    if host_text.count(needle)!=1:raise ValueError('host instrumentation point changed')
    observer='''    class CPU(C.Structure):
        _fields_=[('tcount',C.c_int32),('PC',C.c_uint16),('A',C.c_uint8),('X',C.c_uint8),('Y',C.c_uint8),('S',C.c_uint8),('P',C.c_uint8),('PI',C.c_uint8),('jammed',C.c_uint8),('count',C.c_int32),('IRQlow',C.c_uint32),('DB',C.c_uint8)]
    cpu=CPU.in_dll(lib,'X')
    if C.sizeof(CPU)!=28 or CPU.PC.offset!=4:raise RuntimeError('unsupported CPU ABI')
    table=(C.c_void_p*65536).in_dll(lib,'BWrite')
    addresses=(0x075f,0x0750,0x06d6)
    original={a:table[a] for a in addresses}
    WRITE=C.CFUNCTYPE(None,C.c_uint32,C.c_uint8)
    events=[]
    @WRITE
    def observe(address,value):
        if current[0]>=850:
            memory=(C.c_uint8*2048).from_address(lib.retro_get_memory_data(2))
            events.append({'frame':current[0],'address':address,'value':value,'pc':cpu.PC,'a':cpu.A,'x':cpu.X,'y':cpu.Y,'old':memory[address],'warp_control':memory[0x6d6],'player_x':memory[0x86]})
        WRITE(original[address])(address,value)
    for address in addresses:table[address]=C.cast(observe,C.c_void_p).value
    read_table=(C.c_void_p*65536).in_dll(lib,'ARead')
    read_addresses=(0x87f2,0x87f6,0x9cb4,0x9cd7,0x9cef)
    read_original={a:read_table[a] for a in read_addresses}
    READ=C.CFUNCTYPE(C.c_uint8,C.c_uint32)
    @READ
    def observe_read(address):
        value=READ(read_original[address])(address)
        if current[0]>=900:events.append({'frame':current[0],'read_address':address,'value':value,'pc':cpu.PC,'a':cpu.A,'x':cpu.X,'y':cpu.Y})
        return value
    for address in read_addresses:read_table[address]=C.cast(observe_read,C.c_void_p).value
'''
    instrumented=host_text.replace(needle,observer+needle)
    needle="    trace_bytes = (json.dumps("
    if instrumented.count(needle)!=1:raise ValueError('host trace point changed')
    instrumented=instrumented.replace(needle,"    (out/'cpu-events.json').write_text(json.dumps(events,indent=2))\n"+needle)
    (output/'observer-host.py').write_text(instrumented)
    runs={}
    for label,assisted,observed in [('stale',True,True),('normal',False,True),('neutral',True,False)]:
        patches=base+([(900,0x6d6,1)] if assisted else [])
        patchfile=output/(label+'-patches.json')
        patchfile.write_text(json.dumps([{'frame':f,'memory_id':2,'offset':o,'data_hex':bytes([v]).hex()} for f,o,v in patches]))
        cmd=[sys.executable,str(output/('observer-host.py' if observed else 'host.py')),
             '--core',str(output/'core.dylib'),'--rom',str(output/'source.nes'),'--system','nes',
             '--frames','1600','--inputs',str(output/'inputs.json'),'--patches',str(patchfile),
             '--watch',str(output/'watch.json'),'--frame-images','900,1000,1250','--output',str(output/label)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr[-4000:])
        receipt=json.loads((output/label/'receipt.json').read_text())
        runs[label]=receipt
    events=json.loads((output/'stale/cpu-events.json').read_text()); controls=json.loads((output/'normal/cpu-events.json').read_text())
    def has(rows,**expected):return any(all(row.get(k)==v for k,v in expected.items()) for row in rows)
    checks=[has(events,frame=900,pc=0xdf22,read_address=0x87f6,value=0x24,x=4),
            has(events,frame=900,pc=0xdf26,address=0x75f,value=0x23,y=0x23,warp_control=1),
            has(events,frame=900,pc=0xdf29,read_address=0x9cd7,value=0x33,y=0x23),
            has(events,frame=900,pc=0xdf2c,read_address=0x9cef,value=1,x=0x33),
            has(events,frame=900,pc=0xdf2f,address=0x750,value=1),
            has(controls,frame=900,pc=0xdf26,address=0x75f,value=3,x=0,warp_control=4),
            has(controls,frame=900,pc=0xdf2f,address=0x750,value=0x22)]
    if not all(checks):raise AssertionError('actual native warp chain/control differs')
    # Independent earlier checkpoint: ordinary movement produces control=1
    # via the game itself; this path subsequently enters the normal exit pipe.
    natural_inputs=[{'start':120,'end':125,'buttons':['START']},
        {'start':450,'end':455,'buttons':['START']},{'start':700,'end':705,'buttons':['START']},
        {'start':920,'end':1120,'buttons':['RIGHT','B']},{'start':980,'end':1010,'buttons':['A']}]
    natural_patches=[(680,0x760,2),(680,0x75c,1),(680,0x75b,9),
                     (920,0x754,0),(920,0x756,1)]
    (output/'natural-inputs.json').write_text(json.dumps(natural_inputs))
    (output/'natural-patches.json').write_text(json.dumps([
        {'frame':f,'memory_id':2,'offset':o,'data_hex':bytes([v]).hex()}
        for f,o,v in natural_patches]))
    natural_runs={}
    for label,observed in [('natural',True),('natural-neutral',False)]:
        cmd=[sys.executable,str(output/('observer-host.py' if observed else 'host.py')),
             '--core',str(output/'core.dylib'),'--rom',str(output/'source.nes'),'--system','nes',
             '--frames','1120','--inputs',str(output/'natural-inputs.json'),
             '--patches',str(output/'natural-patches.json'),'--watch',str(output/'watch.json'),
             '--frame-images','1000,1025,1054','--output',str(output/label)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr[-4000:])
        natural_runs[label]=json.loads((output/label/'receipt.json').read_text())
    natural_events=json.loads((output/'natural/cpu-events.json').read_text())
    if not has(natural_events,frame=1048,pc=0xb7b2,address=0x6d6,value=1,old=0):
        raise AssertionError('game did not produce stale control from checkpoint')
    for key in ('state_sha256','system_ram_sha256','frame_rgb_sha256','ram_trace_sha256'):
        if natural_runs['natural'][key]!=natural_runs['natural-neutral'][key]:
            raise AssertionError('natural observer changes '+key)
    # Continuous route from the assisted page-9 checkpoint.  Everything after
    # the large-Mario seed is controller input; warp state and position are not
    # patched. This exercises the actual collision crossing and wrong pipe.
    clip_inputs=[{'start':120,'end':125,'buttons':['START']},
        {'start':450,'end':455,'buttons':['START']},{'start':700,'end':705,'buttons':['START']},
        {'start':920,'end':1055,'buttons':['RIGHT','B']},{'start':980,'end':1010,'buttons':['A']},
        {'start':1055,'end':1160,'buttons':['RIGHT']},{'start':1055,'end':1080,'buttons':['A']},
        {'start':1160,'end':1171,'buttons':['LEFT']},{'start':1171,'end':1201,'buttons':['A','DOWN']},
        {'start':1177,'end':1320,'buttons':['RIGHT']},{'start':1201,'end':1222,'buttons':['DOWN']},
        {'start':1320,'end':1550,'buttons':['DOWN']}]
    (output/'clip-inputs.json').write_text(json.dumps(clip_inputs))
    clip_runs={}
    for label,observed in [('clip',True),('clip-neutral',False)]:
        cmd=[sys.executable,str(output/('observer-host.py' if observed else 'host.py')),
             '--core',str(output/'core.dylib'),'--rom',str(output/'source.nes'),'--system','nes',
             '--frames','2100','--inputs',str(output/'clip-inputs.json'),
             '--patches',str(output/'natural-patches.json'),'--watch',str(output/'watch.json'),
             '--frame-images','1159,1200,1230,1300,1390,1421,1500,1900',
             '--output',str(output/label)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr[-4000:])
        clip_runs[label]=json.loads((output/label/'receipt.json').read_text())
    clip_events=json.loads((output/'clip/cpu-events.json').read_text())
    if not all([
        has(clip_events,frame=1048,pc=0xb7b2,address=0x6d6,value=1,old=0),
        has(clip_events,frame=1421,pc=0xdf22,read_address=0x87f6,value=0x24,x=4),
        has(clip_events,frame=1421,pc=0xdf26,address=0x75f,value=0x23,y=0x23,warp_control=1),
        has(clip_events,frame=1421,pc=0xdf29,read_address=0x9cd7,value=0x33,y=0x23),
        has(clip_events,frame=1421,pc=0xdf2c,read_address=0x9cef,value=1,x=0x33),
        has(clip_events,frame=1421,pc=0xdf2f,address=0x750,value=1)]):
        raise AssertionError('connected clip native event chain differs')
    clip_frames={item['frame']:item['rgb_sha256'] for item in clip_runs['clip']['frame_images']}
    expected_frames={1230:'4a29782c0f0a1f61d69b55ebb125a2f923dce7615d83fd836792c453573a6c5e',
        1500:'a41b0159088ccce525680ce1f3591d7509c9326ea278f37843d07cea24e553df',
        1900:'cd0d68938eaa4ed11ec59f3df07e23110e94cceac36bcf8f6ab7b2050694208c'}
    if any(clip_frames.get(k)!=v for k,v in expected_frames.items()):
        raise AssertionError('connected clip display differs from reviewed frames')
    clip_trace=json.loads((output/'clip/ram_trace.json').read_text())['frames']
    def state_at(frame):
        row=clip_trace[frame];lo=bytes.fromhex(row['raw']['low']);hi=bytes.fromhex(row['raw']['high'])
        return lo[0x6d],lo[0x86],lo[0xce],hi[0x2d6],hi[0x35f]
    if state_at(1230)!=(10,132,32,1,0) or state_at(1421)!=(11,39,128,1,35):
        raise AssertionError('connected collision/pipe state differs')
    for key in ('state_sha256','system_ram_sha256','frame_rgb_sha256','ram_trace_sha256'):
        if clip_runs['clip'][key]!=clip_runs['clip-neutral'][key]:
            raise AssertionError('connected clip observer changes '+key)
    # Separate downstream diagnostic: an assisted underwater checkpoint and
    # player position accelerate reaching the end pipe. The original exit code
    # is then responsible for the one observed return to area $01.
    loop_inputs=clip_inputs+[{'start':1900,'end':2300,'buttons':['RIGHT']}]
    loop_patches=natural_patches+[(1471,0x75b,11),(1900,0x86,0xc0),(1900,0xce,0x60)]
    (output/'loop-inputs.json').write_text(json.dumps(loop_inputs))
    (output/'loop-patches.json').write_text(json.dumps([
        {'frame':f,'memory_id':2,'offset':o,'data_hex':bytes([v]).hex()}
        for f,o,v in loop_patches]))
    loop_runs={}
    for label,observed in [('loop',True),('loop-neutral',False)]:
        cmd=[sys.executable,str(output/('observer-host.py' if observed else 'host.py')),
             '--core',str(output/'core.dylib'),'--rom',str(output/'source.nes'),'--system','nes',
             '--frames','2350','--inputs',str(output/'loop-inputs.json'),
             '--patches',str(output/'loop-patches.json'),'--watch',str(output/'watch.json'),
             '--frame-images','1900,1930,1990,2050,2200','--output',str(output/label)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr[-4000:])
        loop_runs[label]=json.loads((output/label/'receipt.json').read_text())
    loop_trace=json.loads((output/'loop/ram_trace.json').read_text())['frames']
    def loop_state(frame):
        row=loop_trace[frame];lo=bytes.fromhex(row['raw']['low']);hi=bytes.fromhex(row['raw']['high'])
        return lo[0x6d],lo[0x0e],hi[0x372],hi[0x35f],hi[0x360],hi[0x350]
    if (loop_state(1919)!=(11,2,3,35,0,1) or loop_state(1971)!=(11,2,0,35,0,1)
            or loop_state(1980)!=(0,0,1,35,0,1) or loop_state(2100)!=(0,8,3,35,0,1)):
        raise AssertionError('assisted underwater exit did not return to same area')
    for key in ('state_sha256','system_ram_sha256','frame_rgb_sha256','ram_trace_sha256'):
        if loop_runs['loop'][key]!=loop_runs['loop-neutral'][key]:
            raise AssertionError('underwater exit observer changes '+key)
    frames={item['frame']:item['rgb_sha256'] for item in runs['stale']['frame_images']}
    if (frames[1000]!='a41b0159088ccce525680ce1f3591d7509c9326ea278f37843d07cea24e553df' or
            frames[1250]!='fd98891bd4e95274ab32548b7fb1dca42b3ba0650adfca6827c163ac959cd1fa'):
        raise AssertionError('observed world/underwater frames differ from reviewed native run')
    for key in ('state_sha256','system_ram_sha256','frame_rgb_sha256','ram_trace_sha256'):
        if runs['stale'][key]!=runs['neutral'][key]:raise AssertionError('observer changes '+key)
    if rom.read_bytes()!=raw or sha(core.read_bytes())!=CORE_SHA256 or host.read_bytes()!=host_raw:
        raise AssertionError('an input changed during diagnostic')
    summary={'format':'fdisbull-mario-minus-world-diagnostic-1','status':'passed',
             'source':source,'core_sha256':CORE_SHA256,'observer_neutral':True,
             'conditions':{'checkpoint':'assisted level/page seed','position':'assisted player placement',
                           'stale_control':'experimental patch to 1','normal_control':'game produced 4',
                           'world_and_area':'not patched'},
             'native':{'stale_world_index':35,'stale_table_value':36,'stale_area_pointer':1,
                       'normal_world_index':3,'normal_area_pointer':34,'frame':900},
             'natural_upstream':{'control_write_pc':0xb7b2,'old':0,'value':1,'frame':1048,'control_patched':False,'outcome':'normal exit pipe; wall clip not demonstrated'},
             'connected_clip':{'assistance':'level/page checkpoint and large-Mario seed only',
                 'no_subsequent_state_patches':True,'control_write_frame':1048,'wall_frame':1230,
                 'pipe_world_write_frame':1421,'world_display_frame':1500,'underwater_frame':1900,
                 'observer_neutral':True},
             'assisted_underwater_return':{'checkpoint_page':11,'extra_player_position_patch':True,
                 'exit_engine_frame':1919,'reinitialize_frame':1971,'world_index':35,
                 'area_number':0,'area_pointer':1,'returned_page':0,'observer_neutral':True,
                 'scope':'one return; not a proof of infinite repetition or unassisted traversal'},
             'observed_frames':{'diagnostic_world_minus_one':1000,'diagnostic_underwater':1250},
             'limitations':['not an unassisted full-game run',
                            'one assisted return observed; infinite repetition not proven']}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(output/'summary.json')


if __name__=='__main__':main()
