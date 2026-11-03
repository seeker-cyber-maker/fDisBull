#!/usr/bin/env python3
"""Capture controlled original-CPU Miniplanets audio without changing its ROM.

The ordinary title screen boots first. A declared RAM sound request selects one
track, and the title's attract countdown is held at720 during audition. Chained
core callbacks observe actual chip writes. WAV/trace bytes stay outside Git.
"""
from __future__ import annotations

import argparse
import array
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import wave

from fdisbull.miniplanets_audio import FREQUENCY_RANGES, GENESIS_MASTER_HZ, ROM_SHA256, SonaEngine, pitch_value, recover_audio

CORE_SHA256='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
MASTER_CYCLES_PER_FRAME=896040


def sha(data):return hashlib.sha256(data).hexdigest()


class GameInfo(C.Structure):
    _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]


class SystemInfo(C.Structure):
    _fields_=[('name',C.c_char_p),('version',C.c_char_p),('extensions',C.c_char_p),('need_fullpath',C.c_bool),('block_extract',C.c_bool)]


class Geometry(C.Structure):
    _fields_=[('width',C.c_uint),('height',C.c_uint),('max_width',C.c_uint),('max_height',C.c_uint),('aspect',C.c_float)]


class Timing(C.Structure):
    _fields_=[('fps',C.c_double),('sample_rate',C.c_double)]


class AVInfo(C.Structure):
    _fields_=[('geometry',Geometry),('timing',Timing)]


def expected_frequencies(audio,rom,kind,ident):
    engine=SonaEngine(audio)
    engine.request(1 if kind=='bgm' else 2,ident)
    slot=0 if kind=='bgm' else 1
    for _ in range(50000):
        engine.tick()
        if any(e['slot']==slot and e['kind'] in ('loop','stop') for e in engine.events[-128:]):break
    else:raise RuntimeError('source stream did not finish its first iteration')
    _,offset,length,_=FREQUENCY_RANGES[0]
    data=rom[offset:offset+length]
    lut=[int.from_bytes(data[i:i+2],'little') for i in range(0,length,2)]
    pitches={}
    result=[]
    for event in engine.events:
        if event['slot']!=slot:continue
        if event['kind'] in ('loop','stop'):break
        if event['kind'] not in ('note_on','pitch') or not event['channel'].startswith('fm'):continue
        channel={'fm1':0,'fm2':1,'fm3':2,'fm4':4,'fm5':5,'fm6':6}[event['channel']]
        value=pitch_value(event['pitches'][-1],pitches.get(channel,0))
        pitches[channel]=value
        word=lut[(value%192)//4] | ((value//192)<<11)
        result.append({'channel':channel,'word':word,'clock':event['clock'],'source_offset':event['offset']})
    return result,engine.clock


def worker(args):
    rom_path=Path(args.rom).resolve();core_path=Path(args.core).resolve();out=Path(args.output).resolve()
    rom=rom_path.read_bytes();core_hash=sha(core_path.read_bytes())
    if sha(rom)!=ROM_SHA256 or core_hash!=CORE_SHA256:raise ValueError('unqualified source ROM or core')
    audio=recover_audio(rom)
    expected,source_ticks=expected_frequencies(audio,rom,args.kind,args.id)
    frames=args.frames or math.ceil(source_ticks*451584/MASTER_CYCLES_PER_FRAME)+60
    out.mkdir(parents=True)
    lib=C.CDLL(str(core_path));current=[0];record=[False];pcm=[];fm_events=[];psg_events=[];timer_events=[];status=[]
    ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
    VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
    AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
    BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
    POLL=C.CFUNCTYPE(None)
    STATE=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
    directory=C.create_string_buffer(os.fsencode(str(out)))
    @ENV
    def environment(command,data):
        if command in (9,31):C.cast(data,C.POINTER(C.c_char_p))[0]=C.cast(directory,C.c_char_p);return True
        if command==10:return C.cast(data,C.POINTER(C.c_int))[0] in (0,1,2)
        if command==3:C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
        return False
    @VIDEO
    def video(data,width,height,pitch):pass
    @AUDIO
    def sample(left,right):
        if record[0]:pcm.append(array.array('h',[left,right]).tobytes())
    @BATCH
    def batch(data,count):
        if record[0]:pcm.append(C.string_at(data,count*4))
        return count
    @POLL
    def poll():pass
    @STATE
    def state(port,device,index,button):return 0
    for setter,callback in ((lib.retro_set_environment,environment),(lib.retro_set_video_refresh,video),(lib.retro_set_audio_sample,sample),(lib.retro_set_audio_sample_batch,batch),(lib.retro_set_input_poll,poll),(lib.retro_set_input_state,state)):
        setter.argtypes=[type(callback)];setter(callback)
    lib.retro_init();info=SystemInfo();lib.retro_get_system_info(C.byref(info))
    buffer=C.create_string_buffer(rom)
    game=GameInfo(os.fsencode(str(rom_path)),None if info.need_fullpath else C.cast(buffer,C.c_void_p),len(rom),None)
    lib.retro_load_game.argtypes=[C.POINTER(GameInfo)];lib.retro_load_game.restype=C.c_bool
    if not lib.retro_load_game(C.byref(game)):raise RuntimeError('core rejected source ROM')
    av=AVInfo();lib.retro_get_system_av_info(C.byref(av))
    if abs(av.timing.fps-GENESIS_MASTER_HZ/MASTER_CYCLES_PER_FRAME)>0.000001:raise RuntimeError('unexpected source video clock')
    ram=(C.c_ubyte*65536).in_dll(lib,'work_ram');zram=(C.c_ubyte*8192).in_dll(lib,'zram')
    z80=(C.c_ubyte*88).in_dll(lib,'Z80');z80_cycles=C.c_uint.from_address(C.addressof(z80)+64)
    FM=C.CFUNCTYPE(None,C.c_uint,C.c_uint,C.c_uint)
    fm_pointer=C.c_void_p.in_dll(lib,'fm_write');fm_original=FM(fm_pointer.value);ym_register=[0,0]
    @FM
    def fm(cycles,address,data):
        bank=(address>>1)&1
        if address&1:
            register=ym_register[bank]
            if register in (0x24,0x25,0x26,0x27):timer_events.append([current[0],cycles,register,data])
            if record[0] and register!=0x2a:fm_events.append([current[0]-args.boot-4,cycles,bank,register,data])
        else:ym_register[bank]=data
        fm_original(cycles,address,data)
    WRITE=C.CFUNCTYPE(None,C.c_uint,C.c_ubyte)
    write_pointer=C.c_void_p.in_dll(lib,'z80_writemem');write_original=WRITE(write_pointer.value)
    @WRITE
    def write(address,value):
        if record[0] and address==0x7f11:psg_events.append([current[0]-args.boot-4,z80_cycles.value,value])
        write_original(address,value)
    fm_pointer.value=C.cast(fm,C.c_void_p).value;write_pointer.value=C.cast(write,C.c_void_p).value
    try:
        for frame in range(args.boot+4+frames):
            current[0]=frame
            if frame>=args.boot:
                ram[0x798^1]=2;ram[0x799^1]=208  # Qualified title countdown FF0798=720.
            if frame==args.boot:ram[0x75d^1]=255  # Stop title BGM, then let the command drain.
            if frame==args.boot+4:
                ram[(0x75d if args.kind=='bgm' else 0x75e)^1]=args.id
                record[0]=True
            lib.retro_run()
            if record[0]:status.append([frame-args.boot-4,zram[0x1fc2],ram[0x75f^1]])
    finally:
        fm_pointer.value=C.cast(fm_original,C.c_void_p).value;write_pointer.value=C.cast(write_original,C.c_void_p).value
        lib.retro_unload_game();lib.retro_deinit()
    raw=b''.join(pcm)
    with wave.open(str(out/'original.wav'),'wb') as wav:
        wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(round(av.timing.sample_rate));wav.writeframes(raw)
    samples=array.array('h',raw)
    high=[0,0];actual=[]
    for frame,cycles,bank,register,value in fm_events:
        if 0xa4<=register<=0xa6:high[bank]=value
        if 0xa0<=register<=0xa2:actual.append({'channel':register-0xa0+4*bank,'word':(high[bank]<<8)|value,'cycles':frame*MASTER_CYCLES_PER_FRAME+cycles})
    matching=min(len(expected),len(actual))
    first_mismatch=next((i for i in range(matching) if any(expected[i][key]!=actual[i][key] for key in ('channel','word'))),None)
    complete=len(actual)>=len(expected) and first_mismatch is None
    errors=[]
    if matching and first_mismatch is None:
        errors=[abs((actual[i]['cycles']-actual[0]['cycles'])-(expected[i]['clock']-expected[0]['clock'])*451584)*1000/GENESIS_MASTER_HZ for i in range(matching)]
    acknowledgements=[frame*MASTER_CYCLES_PER_FRAME+cycles for frame,cycles,reg,value in timer_events if reg==0x27 and value==0x2f and frame>100]
    deltas=[b-a for a,b in zip(acknowledgements,acknowledgements[1:])]
    trace={'fm_writes':fm_events,'psg_writes':psg_events,'timer_writes':timer_events,'status':status,'expected_fm_frequencies':expected,'actual_fm_frequencies':actual}
    trace_bytes=(json.dumps(trace,separators=(',', ':'))+'\n').encode();(out/'chip-trace.json').write_bytes(trace_bytes)
    if sha(rom_path.read_bytes())!=ROM_SHA256 or sha(core_path.read_bytes())!=core_hash:raise RuntimeError('source ROM or core changed')
    receipt={'format':'fdisbull-original-audio-capture-1','rom_sha256':ROM_SHA256,'core_sha256':core_hash,
             'script_sha256':sha(Path(__file__).read_bytes()),'core_name':info.name.decode(),'core_version':info.version.decode(),
             'kind':args.kind,'id':args.id,'boot_frames':args.boot,'frames':frames,'sample_rate':av.timing.sample_rate,
             'pcm_frames':len(raw)//4,'pcm_peak':max(map(abs,samples),default=0),
             'pcm_rms':math.sqrt(sum(value*value for value in samples)/max(1,len(samples))),
             'wav_sha256':sha((out/'original.wav').read_bytes()),'trace_sha256':sha(trace_bytes),
             'fm_expected_events':len(expected),'fm_observed_events':len(actual),'fm_first_mismatch':first_mismatch,
             'fm_complete_first_iteration_identity':complete,'fm_max_aligned_timing_error_ms':max(errors,default=None),
             'timer_acknowledgements':len(acknowledgements),'timer_period_mean_master_cycles':statistics.mean(deltas) if deltas else None,
             'timer_period_expected_master_cycles':451584,'source_timer_hz':GENESIS_MASTER_HZ/451584,
             'status_busy_frames':sum(bool(value&32) for _,value,_ in status),
             'interventions':['RAM FF075D=255 once to stop title music','RAM FF075D or FF075E=request ID once','RAM FF0798=720 each audition frame to hold title attract countdown','core fm_write/z80_writemem callback pointers chained; original callbacks always run'],
             'claim':'original CPU and chip output, controlled audition; FM event identity/timing is separate from NES timbre/polyphony adaptation'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core',required=True);parser.add_argument('--rom',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--kind',choices=('bgm','sfx'),required=True);parser.add_argument('--id',type=int,required=True)
    parser.add_argument('--frames',type=int,default=0,help='0 captures one whole source iteration plus one second')
    parser.add_argument('--boot',type=int,default=600);parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 1<=args.id<=(13 if args.kind=='bgm' else 19) or not 0<=args.frames<=20000 or not 600<=args.boot<=650:parser.error('invalid bounded audition parameters')
    out=Path(args.output).resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):parser.error('choose a fresh output outside Git')
    if args.worker:worker(args)
    else:
        result=subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker'],capture_output=True,text=True,timeout=120)
        if result.returncode:raise SystemExit(result.stderr[-4000:])
        print(result.stdout)


if __name__=='__main__':main()
