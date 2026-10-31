#!/usr/bin/env python3
"""Check all audio UIL streams in the actual mapped NES cartridge/core.

Declared debug commands initialize/request/tick the audio engine while normal
audio IRQs and game stepping are disabled. Completed command boundaries are
compared with decoded-event Python state and the portable C renderer. This is
native bank/stream/state conformance, distinct from normal real-time tempo.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.miniplanets_audio import SonaEngine, recover_audio, pitch_value
from check_miniplanets_audio import host_bindings
from capture_miniplanets_audio import GameInfo, SystemInfo, AVInfo

NES_SHA='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'

BYTE_FIELDS={
    **{name:32 for name in ('instrument','attenuation','gate','envelope','pan','duty',
       'attack_ticks','decay_ticks','sustain','release_ticks','envelope_phase','release_peak',
       'psg_level','psg_tl','psg_ar','psg_sl','psg_dr','psg_sr','psg_rr')},
    'owner':16,'current_volume':12,'metadata':476,'pcm_instrument':4,
    'dmc_address':4,'dmc_length':4,'dmc_rate':4,'stream_active':2,
    **{name:1 for name in ('error','bgm_id','sfx_id','sfx_phase','round_robin',
                          'dmc_source','dmc_playing','dmc_slot','dmc_channel')},
}
WORD_FIELDS={
    **{name:32 for name in ('pitch','pulse_period','triangle_period','envelope_counter')},
    'psg_pulse_period':8,'psg_triangle_period':8,'pcm_ticks':4,'pcm_generation':4,'dmc_delivered':4,
    **{name:1 for name in ('tick_count','interrupt_count','command_count','event_crc','note_count',
                          'arpeggio_count','dmc_generation','pcm_dropped','pcm_preempted')},
}


def sha(data):return hashlib.sha256(data).hexdigest()


class LogicalVoices:
    """Typed-event interpretation, independent of the C bytecode reader."""
    def __init__(self):
        self.state={name:[0]*count for name,count in {
            'pitch':32,'instrument':32,'attenuation':32,'gate':32,'pan':32,
            'owner':16,'pcm_generation':4,'pcm_instrument':4}.items()}
        self.reset()

    def reset(self):
        for name in ('attenuation','gate','owner'):self.state[name]=[0]*len(self.state[name])
        self.state['pan']=[192]*32

    def apply(self,event):
        kind=event['kind'];name=event.get('channel')
        if not name:return
        channel={'fm1':0,'fm2':1,'fm3':2,'fm4':4,'fm5':5,'fm6':6,
                 'psg1':8,'psg2':9,'psg3':10,'noise':11,'pcm1':14,'pcm2':15}[name]
        slot=event['slot'];index=slot*16+channel;s=self.state
        owned=bool(s['owner'][channel])==bool(slot)
        if kind=='lock' and slot:
            s['owner'][channel]=1;s['gate'][channel]=0
        elif kind=='instrument':s['instrument'][index]=event['value']
        elif kind in ('note_on','pitch'):
            s['pitch'][index]=(event['pitches'][-1][0] if channel==11 else
                              pitch_value(event['pitches'][-1],s['pitch'][index],psg=channel>=8))
            if kind=='note_on' and owned:s['gate'][index]=1
        elif kind=='note_off' and channel<14:s['gate'][index]=0
        elif kind=='sample_on' and owned:
            at=slot*2+channel-14;s['pcm_generation'][at]=(s['pcm_generation'][at]+1)&65535
            s['pcm_instrument'][at]=event['value']
        elif kind=='volume':
            value=event['value'];old=s['attenuation'][index]
            s['attenuation'][index]=value if value<128 else min(127,old+(value&63)) if value<192 else max(0,old-(value&63))
        elif kind=='pan':s['pan'][index]=event['value']&192

    def free_effect(self):
        for channel in range(16):
            if self.state['owner'][channel]:self.state['gate'][channel]=0
            self.state['gate'][16+channel]=0
        self.state['owner']=[0]*16


def check(args):
    out=Path(args.output).resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh private output outside Git')
    cart=Path(args.cartridge).resolve();rom_path=Path(args.rom).resolve();core=Path(args.core).resolve()
    manifest_path=Path(args.manifest).resolve() if args.manifest else cart.with_name('manifest.json')
    labels_path=cart.parent/'build/labels.txt';audio_path=cart.with_name('audio.uil.json')
    manifest=json.loads(manifest_path.read_text());rom=rom_path.read_bytes();audio=recover_audio(rom)
    if json.loads(audio_path.read_text())!=audio:raise ValueError('retained audio UIL differs from qualified source recovery')
    if sha(cart.read_bytes())!=manifest['rom_sha256'] or sha(core.read_bytes())!=NES_SHA or sha(rom)!=manifest['source_rom_sha256']:
        raise ValueError('cartridge/source/core identity mismatch')
    tools=Path(args.cc65_root).resolve()
    for name,receipt in manifest['toolchain'].items():
        if sha((tools/'bin'/name).read_bytes())!=receipt['sha256']:raise ValueError('toolchain identity mismatch')
    resource_paths=[]
    for name,receipt in manifest.get('runtime_resources',{}).items():
        resource=(cart.parent/receipt['captured_path']).resolve()
        if not resource.is_relative_to(cart.parent) or not resource.is_file():
            raise ValueError('captured runtime resource is outside the cartridge directory')
        raw=resource.read_bytes()
        if len(raw)!=receipt['length'] or sha(raw)!=receipt['sha256']:
            raise ValueError('captured runtime resource identity mismatch: '+name)
        resource_paths.append(resource)
    runtime=ROOT/'src/fdisbull/game_sources/miniplanets_audio_nes.c'
    sources=manifest['adapter_sources']
    if sha(runtime.read_bytes())!=sources[runtime.name]:raise ValueError('live C oracle differs from captured cartridge adapter')
    assembly=ROOT/'src/fdisbull/game_sources/miniplanets_audio_fast.s'
    if sha(assembly.read_bytes())!=sources[assembly.name]:raise ValueError('live assembly differs from captured cartridge adapter')
    labels={}
    for line in labels_path.read_text().splitlines():
        match=re.match(r'al ([0-9A-Fa-f]+) \.(_[A-Za-z0-9_]+)$',line)
        if match:
            name=match[2];address=int(match[1],16)
            if name in labels and labels[name]!=address:raise ValueError('ambiguous native symbol address')
            labels[name]=address
    names=['_audio_'+name for name in (*BYTE_FIELDS,*WORD_FIELDS)]+['_status_busy']
    if any(name not in labels or not 0x6000<=labels[name]<0x8000 for name in names):raise ValueError('audio state is not in declared cartridge RAM')
    host_compiler=Path(shutil.which(args.cc) or args.cc).resolve()
    inputs=[rom_path,cart,core,manifest_path,labels_path,audio_path,runtime,assembly,Path(__file__).resolve(),
            ROOT/'scripts/check_miniplanets_audio.py',ROOT/'scripts/capture_miniplanets_audio.py',
            ROOT/'src/fdisbull/miniplanets_audio.py',host_compiler]
    inputs += [tools/'bin'/name for name in manifest['toolchain']]
    inputs += resource_paths
    before={str(path):sha(path.read_bytes()) for path in inputs}
    out.mkdir(parents=True)
    retained=out/'verification-sources';retained.mkdir()
    for source in (runtime,assembly,Path(__file__).resolve(),ROOT/'scripts/check_miniplanets_audio.py',
                   ROOT/'scripts/capture_miniplanets_audio.py',ROOT/'src/fdisbull/miniplanets_audio.py'):
        (retained/source.name).write_bytes(source.read_bytes())
    (out/'host-bindings.c').write_text(host_bindings(audio))
    host_path=out/('reference.dylib' if sys.platform=='darwin' else 'reference.so')
    build=subprocess.run([args.cc,'-std=c89','-O2','-shared','-fPIC','-DFDISBULL_AUDIO_HOST',str(runtime),str(out/'host-bindings.c'),'-o',str(host_path)],capture_output=True,text=True)
    (out/'host-build.txt').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError(build.stderr[-3000:])
    reference=C.CDLL(str(host_path));reference.audio_request.argtypes=[C.c_ubyte,C.c_ubyte];reference.audio_busy.restype=C.c_ubyte
    host={}
    for name,count in BYTE_FIELDS.items():host[name]=(C.c_ubyte*count).in_dll(reference,'audio_'+name)
    for name,count in WORD_FIELDS.items():host[name]=(C.c_uint*count).in_dll(reference,'audio_'+name)
    lib=C.CDLL(str(core));ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
    VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
    AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16);BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
    POLL=C.CFUNCTYPE(None);STATE=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
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
    def sample(left,right):pass
    @BATCH
    def batch(data,count):return count
    @POLL
    def poll():pass
    @STATE
    def state(port,device,index,button):return 0
    for setter,callback in ((lib.retro_set_environment,environment),(lib.retro_set_video_refresh,video),(lib.retro_set_audio_sample,sample),(lib.retro_set_audio_sample_batch,batch),(lib.retro_set_input_poll,poll),(lib.retro_set_input_state,state)):
        setter.argtypes=[type(callback)];setter(callback)
    lib.retro_init();info=SystemInfo();lib.retro_get_system_info(C.byref(info));payload=cart.read_bytes();buffer=C.create_string_buffer(payload)
    game=GameInfo(os.fsencode(str(cart)),None if info.need_fullpath else C.cast(buffer,C.c_void_p),len(payload),None)
    lib.retro_load_game.argtypes=[C.POINTER(GameInfo)];lib.retro_load_game.restype=C.c_bool
    if not lib.retro_load_game(C.byref(game)):raise RuntimeError('core rejected mapped cartridge')
    lib.retro_get_memory_data.argtypes=[C.c_uint];lib.retro_get_memory_data.restype=C.c_void_p
    lib.retro_get_memory_size.argtypes=[C.c_uint];lib.retro_get_memory_size.restype=C.c_size_t
    system_ptr=lib.retro_get_memory_data(2);save_ptr=lib.retro_get_memory_data(0)
    if lib.retro_get_memory_size(2)!=2048 or lib.retro_get_memory_size(0)!=8192:raise RuntimeError('unexpected NES RAM mapping')
    system=(C.c_ubyte*2048).from_address(system_ptr);save_ram=(C.c_ubyte*8192).from_address(save_ptr)
    frames=0;commands=0;maximum_frames=0;trace=[];start=time.perf_counter()
    def frame(*,guard=True):
        nonlocal frames
        lib.retro_run();frames+=1
        if guard and system[0x7ed]:raise AssertionError(f'native platform fault{system[0x7ed]}')
    def snapshot():
        result={}
        for name,count in BYTE_FIELDS.items():
            offset=labels['_audio_'+name]-0x6000;result[name]=list(save_ram[offset:offset+count])
        for name,count in WORD_FIELDS.items():
            offset=labels['_audio_'+name]-0x6000
            result[name]=[int.from_bytes(bytes(save_ram[offset+i*2:offset+i*2+2]),'little') for i in range(count)]
        result['status_busy']=[save_ram[labels['_status_busy']-0x6000]]
        return result
    def command(procedure,arguments=()):
        nonlocal commands,maximum_frames
        if system[0x7d5]:raise AssertionError('previous native command is unfinished')
        epoch=system[0x7d2]|system[0x7d3]<<8
        raw=b''.join(int(value).to_bytes(4,'little') for value in (*arguments,*([0]*(4-len(arguments)))))
        system[0x7d9:0x7e9]=raw;system[0x7d6]=procedure;system[0x7d5]=1
        for waited in range(1,args.command_frames+1):
            frame()
            if not system[0x7d5]:
                if (system[0x7d2]|system[0x7d3]<<8)!=(epoch+1)&65535:raise AssertionError('native completion epoch differs')
                commands+=1;maximum_frames=max(maximum_frames,waited);return snapshot()
        raise AssertionError(f'native audio command{procedure} exceeded{args.command_frames}frames')
    def compare(actual,engine,shadow):
        expected={name:[value&65535 for value in values] for name,values in host.items()}
        expected['status_busy']=[reference.audio_busy()]
        if actual!=expected:
            differing=next(name for name in expected if actual[name]!=expected[name])
            raise AssertionError(f'native/portable state differs in{differing}: native{actual[differing]} expected{expected[differing]}')
        scalar={'interrupt_count':engine.nes_clock,'tick_count':engine.clock,'command_count':engine.command_count,
                'event_crc':engine.event_crc,'note_count':engine.note_count,'status_busy':int(engine.busy)}
        for name,value in scalar.items():
            if actual[name]!=[value&65535]:raise AssertionError(f'decoded-event {name} mismatch')
        for name,value in shadow.state.items():
            if actual[name]!=value:raise AssertionError(f'independently decoded source voice state differs in{name}')
        if actual['error']!=[0]:raise AssertionError('native source audio decoder fault')
    receipts=[];shadow=LogicalVoices()
    try:
        for _ in range(80):system[0x7d4]=1;frame(guard=False)
        if system[0x7ed]:raise AssertionError('native bootstrap did not reach its fault-free boundary')
        if snapshot()['interrupt_count']!=[0]:raise AssertionError('audio advanced before controlled debug boundary')
        for track in audio['tracks']:
            kind=1 if track['kind']=='bgm' else 2;ident=track['track']+1 if kind==1 else track['track']-12
            engine=SonaEngine(audio);shadow.reset();reference.audio_init();actual=command(250);compare(actual,engine,shadow)
            reference.audio_request(kind,ident);engine.request(kind,ident);actual=command(251,(kind,ident));compare(actual,engine,shadow)
            total=args.interrupts if kind==1 else 512;position=0
            while position<total:
                count=min(args.batch,total-position);cursor=len(engine.events)
                for _ in range(count):reference.audio_tick();engine.nes_tick()
                for event in engine.events[cursor:]:
                    if event['kind']=='stop' and event['slot']==1:shadow.free_effect()
                    else:shadow.apply(event)
                actual=command(252,(count,));compare(actual,engine,shadow);position+=count
                trace.append({'track':track['track'],'interrupts':position,'host_frames':frames,'native':actual})
            coverage={event['offset'] for event in engine.events if event['track']==track['track']}
            if len(coverage)!=len(track['event_program']['events']):raise AssertionError('mapped execution did not cover a whole source iteration')
            receipt={'track':track['track'],'name':track['name'],'interrupts':total,'source_ticks':engine.clock,
                     'commands':engine.command_count,'notes':engine.note_count,'crc':engine.event_crc,
                     'pcm_dropped':actual['pcm_dropped'][0],'pcm_preempted':actual['pcm_preempted'][0],
                     'whole_source_command_coverage':True,'passed':True}
            receipts.append(receipt);print(json.dumps(receipt),flush=True)
        # A composed case exercises ownership, priority rejection and restarts
        # through the same mapped request API, without replacing source state.
        engine=SonaEngine(audio);shadow.reset();reference.audio_init()
        actual=command(250);compare(actual,engine,shadow)
        schedule={0:(1,1),100:(2,1),101:(2,1),105:(2,19),106:(2,3),
                  200:(1,5),250:(3,0),300:(2,18),305:(2,1),
                  600:(1,6),700:(2,10),725:(2,16),730:(2,3),900:(3,0),920:(1,7)}
        position=0
        while position<1024:
            if position in schedule:
                kind,ident=schedule[position];previous=engine.streams[1]
                reference.audio_request(kind,ident);engine.request(kind,ident)
                if kind in (1,3):shadow.reset()
                elif engine.streams[1] is not previous:shadow.free_effect()
                actual=command(251,(kind,ident));compare(actual,engine,shadow)
            next_request=min((at for at in schedule if at>position),default=1024)
            count=min(args.batch,next_request-position,1024-position);cursor=len(engine.events)
            for _ in range(count):reference.audio_tick();engine.nes_tick()
            for event in engine.events[cursor:]:
                if event['kind']=='stop' and event['slot']==1:shadow.free_effect()
                else:shadow.apply(event)
            actual=command(252,(count,));compare(actual,engine,shadow);position+=count
            trace.append({'track':-1,'interrupts':position,'host_frames':frames,'native':actual})
        receipts.append({'track':-1,'name':'mixed-priority-stop-restart','interrupts':1024,'source_ticks':engine.clock,
                         'commands':engine.command_count,'notes':engine.note_count,'crc':engine.event_crc,
                         'pcm_dropped':actual['pcm_dropped'][0],'pcm_preempted':actual['pcm_preempted'][0],
                         'whole_source_command_coverage':'all32 isolated cases qualified separately','passed':True})
    except Exception as error:
        raw=(json.dumps(trace,separators=(',',':'))+'\n').encode();(out/'trace.json').write_bytes(raw)
        failure={'format':'fdisbull-mapped-nes-audio-check-1','passed':False,'error':str(error),
                 'cartridge_sha256':manifest['rom_sha256'],'source_rom_sha256':manifest['source_rom_sha256'],
                 'core_sha256':NES_SHA,'cases':receipts,'completed_commands':commands,'host_frames':frames,
                 'command_pending':bool(system[0x7d5]),'observation_at_failure':snapshot(),
                 'trace_sha256':sha(raw),'input_hashes':before,
                 'claim':'failed controlled native audio check; an observation with a pending command is not completed-call evidence'}
        (out/'receipt.json').write_text(json.dumps(failure,indent=2)+'\n')
        raise
    finally:lib.retro_unload_game();lib.retro_deinit()
    after={str(path):sha(path.read_bytes()) for path in inputs}
    if after!=before:raise AssertionError('source/cartridge/core/compiler/harness changed during mapped audio check')
    raw=(json.dumps(trace,separators=(',',':'))+'\n').encode();(out/'trace.json').write_bytes(raw)
    receipt={'format':'fdisbull-mapped-nes-audio-check-1','passed':True,'cartridge_sha256':manifest['rom_sha256'],
             'source_rom_sha256':manifest['source_rom_sha256'],'core_sha256':NES_SHA,'core_name':info.name.decode(),
             'core_version':info.version.decode(),'toolchain':manifest['toolchain'],
             'runtime_resources':manifest.get('runtime_resources',{}),'adapter_sources':sources,
             'cases':receipts,'interrupts_checked':sum(r['interrupts'] for r in receipts),'completed_commands':commands,
             'maximum_command_host_frames':maximum_frames,'host_frames':frames,'wall_seconds':time.perf_counter()-start,
             'trace_sha256':sha(raw),'inputs_unchanged':True,'input_hashes':before,
             'claim':'completed controlled native banked audio calls match decoded Python source state and portable C; not normal real-time cadence, waveform parity or natural UI coverage'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','cartridge','core','cc65-root','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--manifest');parser.add_argument('--cc',default='cc')
    parser.add_argument('--interrupts',type=int,default=20000);parser.add_argument('--batch',type=int,default=256)
    parser.add_argument('--command-frames',type=int,default=600)
    args=parser.parse_args()
    if not 16000<=args.interrupts<=30000 or not 1<=args.batch<=256 or not 100<=args.command_frames<=1000:parser.error('invalid bounded native audio schedule')
    result=check(args);print(json.dumps({k:v for k,v in result.items() if k not in ('cases','input_hashes')},indent=2))
