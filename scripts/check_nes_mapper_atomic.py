#!/usr/bin/env python3
"""Exercise exact production mapper helpers with real pending 6502 IRQs.

The authored MMC3 cartridges contain two bank sentinels and no game assets.
The core's original write handlers always run; a declared observer asserts the
actual CPU's external IRQ line at one selected store boundary. No instruction
interpreter or simulated mapper replaces the pinned FCEUmm core.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture_miniplanets_audio import GameInfo, SystemInfo

CORE_SHA='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
BOUNDARIES=('selector_shadow','selector_register','bank_shadow','bank_register')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def helper(source,name):
    match=re.search(r'^'+re.escape(name)+r':\n.*?^\s+rts\s*$',source,re.M|re.S)
    if not match:raise ValueError('Could not capture exact helper '+name)
    return match.group(0)+'\n'


def annotate(body,name):
    target='data_bank' if name=='_select_data' else 'code_bank'
    stores={'sta mapper_select':'selector_shadow','sta $8000':'selector_register',
            'sta '+target:'bank_shadow','sta $8001':'bank_register'}
    lines=[]
    for line in body.splitlines():
        if line.strip() in stores:
            label=name+'_'+stores[line.strip()]
            lines.extend(('.export '+label,label+':'))
        lines.append(line)
    return '\n'.join(lines)+'\n'


def cartridge(folder,source,selector,incoming_i,tools):
    bodies={name:helper(source,name) for name in ('_select_data','select_code')}
    selected='_select_data' if selector=='data' else 'select_code'
    init='sei' if incoming_i else 'cli'
    expected=4 if incoming_i else 0
    asm='''
.setcpu "6502"
code_bank=$6000
data_bank=$6001
mapper_select=$6002
irq_count=$6003
mismatches=$6004
done=$6006
flag_errors=$6007
armed=$6008
.segment "B0"
.byte $A5
.res 8191,$EA
.segment "B1"
.byte $5A
.res 8191,$EA
.segment "FIXED"
reset:
 sei
 cld
 ldx #$FF
 txs
 lda #0
 sta $2000
 sta $2001
 sta $4010
 sta $E000
 lda #$40
 sta $4017
 lda #$80
 sta $A001
 ldx #0
 lda #0
clear:
 .repeat 8,page
 sta page*256,x
 .endrepeat
 .repeat 32,page
 sta $6000+page*256,x
 .endrepeat
 inx
 bne clear
 lda #0
 jsr select_code
 lda #0
 jsr _select_data
 lda #1
 sta armed
'''+init+'''
 lda #1
 jsr '''+selected+'''
 php
 pla
 and #4
 cmp #'''+str(expected)+'''
 beq flags_ok
 inc flag_errors
flags_ok:
'''+(''' lda irq_count
 beq still_masked
 inc flag_errors
still_masked:
''' if incoming_i else '')+'''
 cli
 nop
wait_irq:
 lda irq_count
 beq wait_irq
 sei
 lda #1
 sta done
forever:
 jmp forever
irq:
 pha
 txa
 pha
 tya
 pha
 sta $E000
 inc irq_count
 lda code_bank
 beq code_zero
 lda $8000
 cmp #$5A
 jmp check_code
code_zero:
 lda $8000
 cmp #$A5
check_code:
 beq data_check
 inc mismatches
data_check:
 lda data_bank
 beq data_zero
 lda $A000
 cmp #$5A
 jmp check_data
data_zero:
 lda $A000
 cmp #$A5
check_data:
 beq irq_end
 inc mismatches
irq_end:
 pla
 tay
 pla
 tax
 pla
 rti
nmi:
 rti
'''+''.join(annotate(body,name) for name,body in bodies.items())+'''
.segment "VECTORS"
.word nmi,reset,irq
'''
    cfg='''MEMORY {
B0:start=$8000,size=$2000,file=%O,fill=yes;
B1:start=$8000,size=$2000,file=%O,fill=yes;
B2:start=$C000,size=$2000,file=%O,fill=yes;
FIXED:start=$E000,size=$1FFA,file=%O,fill=yes;
VECTORS:start=$FFFA,size=6,file=%O,fill=yes;
}
SEGMENTS {
B0:load=B0,type=ro;B1:load=B1,type=ro;
FIXED:load=FIXED,type=ro;VECTORS:load=VECTORS,type=ro;
}
'''
    folder.mkdir()
    (folder/'probe.s').write_text(asm);(folder/'probe.cfg').write_text(cfg)
    for command in ([tools/'bin/ca65',folder/'probe.s','-o',folder/'probe.o'],
                    [tools/'bin/ld65','-C',folder/'probe.cfg','-Ln',folder/'labels.txt',
                     '-o',folder/'prg.bin',folder/'probe.o']):
        result=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=30)
        if result.returncode:raise RuntimeError(result.stderr)
    prg=(folder/'prg.bin').read_bytes()
    if len(prg)!=32768:raise AssertionError('unexpected authored PRG size')
    image=b'NES\x1A'+bytes((2,0,0x42,0,1,0,0,0,0,0,0,0))+prg
    (folder/'probe.nes').write_bytes(image)
    labels={name:int(address,16) for address,name in re.findall(r'^al ([0-9A-Fa-f]+) \.([^\s]+)$',(folder/'labels.txt').read_text(),re.M)}
    return folder/'probe.nes',{name:sha(raw.encode()) for name,raw in bodies.items()},labels,selected


class CPU(C.Structure):
    # Official FCEUmm ac0d00a x6502struct.h, ARM64 FASTAPASS is empty.
    _fields_=[('tcount',C.c_int32),('PC',C.c_uint16),('A',C.c_uint8),('X',C.c_uint8),
              ('Y',C.c_uint8),('S',C.c_uint8),('P',C.c_uint8),('PI',C.c_uint8),
              ('jammed',C.c_uint8),('count',C.c_int32),('IRQlow',C.c_uint32),('DB',C.c_uint8)]


class Core:
    def __init__(self,path,output):
        self.lib=C.CDLL(str(path));self.keep=[];lib=self.lib
        ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
        VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
        AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
        BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
        POLL=C.CFUNCTYPE(None);STATE=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
        directory=C.create_string_buffer(os.fsencode(output));self.keep.append(directory)
        def environment(command,data):
            if command in (9,31):C.cast(data,C.POINTER(C.c_char_p))[0]=C.cast(directory,C.c_char_p);return True
            if command==10:return C.cast(data,C.POINTER(C.c_int))[0] in (0,1,2)
            if command==3:C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
            return False
        callbacks=[(lib.retro_set_environment,ENV(environment)),
            (lib.retro_set_video_refresh,VIDEO(lambda *x:None)),
            (lib.retro_set_audio_sample,AUDIO(lambda *x:None)),
            (lib.retro_set_audio_sample_batch,BATCH(lambda p,n:n)),
            (lib.retro_set_input_poll,POLL(lambda:None)),
            (lib.retro_set_input_state,STATE(lambda *x:0))]
        for setter,callback in callbacks:setter.argtypes=[type(callback)];setter(callback);self.keep.append(callback)
        lib.retro_init();self.info=SystemInfo();lib.retro_get_system_info(C.byref(self.info))
        lib.retro_load_game.argtypes=[C.POINTER(GameInfo)];lib.retro_load_game.restype=C.c_bool
        lib.retro_get_memory_data.argtypes=[C.c_uint];lib.retro_get_memory_data.restype=C.c_void_p
        lib.retro_get_memory_size.argtypes=[C.c_uint];lib.retro_get_memory_size.restype=C.c_size_t
        lib.retro_serialize_size.restype=C.c_size_t
        for name in ('retro_serialize','retro_unserialize'):
            function=getattr(lib,name);function.argtypes=[C.c_void_p,C.c_size_t];function.restype=C.c_bool
        self.cpu=CPU.in_dll(lib,'X')
        if C.sizeof(CPU)!=28 or CPU.PC.offset!=4:raise AssertionError('unsupported core CPU ABI')

    def serialize(self):
        data=C.create_string_buffer(self.lib.retro_serialize_size())
        if not self.lib.retro_serialize(data,len(data)):raise AssertionError('serialize failed')
        return data.raw

    def restore(self,raw):
        data=C.create_string_buffer(raw)
        if not self.lib.retro_unserialize(data,len(raw)):raise AssertionError('unserialize failed')

    def run(self,image,target):
        raw=image.read_bytes();buffer=C.create_string_buffer(raw)
        game=GameInfo(os.fsencode(image),None if self.info.need_fullpath else C.cast(buffer,C.c_void_p),len(raw),None)
        if not self.lib.retro_load_game(C.byref(game)):raise AssertionError('authored cartridge rejected')
        if self.lib.retro_get_memory_size(0)!=8192:raise AssertionError('authored SRAM mapping differs')
        ram=(C.c_uint8*8192).from_address(self.lib.retro_get_memory_data(0))
        table=(C.c_void_p*65536).in_dll(self.lib,'BWrite')
        WRITE=C.CFUNCTYPE(None,C.c_uint32,C.c_uint8)
        addresses=(0x6000,0x6001,0x6002,0x8000,0x8001)
        pointers={a:table[a] for a in addresses};original={a:WRITE(table[a]) for a in addresses}
        injected=[];trace=[];mode=[False]
        @WRITE
        def observe(address,value):
            original[address](address,value)
            if ram[8]:
                if mode[0] and self.cpu.PC==target and not injected:
                    injected.append({'pc':self.cpu.PC,'address':address,'value':value,'P':self.cpu.P,'S':self.cpu.S})
                    self.cpu.IRQlow|=1
                trace.append({'pc':self.cpu.PC,'address':address,'value':value,'P':self.cpu.P,
                              'code_shadow':ram[0],'data_shadow':ram[1],'irq_count':ram[3]})
        def install():
            for address in addresses:table[address]=C.cast(observe,C.c_void_p).value
        def uninstall():
            for address,pointer in pointers.items():table[address]=pointer
        initial=self.serialize()
        for _ in range(6):self.lib.retro_run()
        control=self.serialize()
        self.restore(initial);install()
        for _ in range(6):self.lib.retro_run()
        forwarding=self.serialize();uninstall()
        neutral=control==forwarding
        self.restore(initial);install();mode[0]=True;trace.clear()
        for frames in range(1,11):
            self.lib.retro_run()
            if ram[6]:break
        result={'completed':ram[6]==1,'irqs':ram[3],'physical_bank_mismatches':ram[4],
                'incoming_I_errors':ram[7],'injected':injected,'forwarding_observer_neutral':neutral,
                'frames':frames,'trace':trace}
        uninstall();self.lib.retro_unload_game()
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-source',required=True);parser.add_argument('--after-source',required=True)
    parser.add_argument('--core',required=True);parser.add_argument('--cc65-root',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output).expanduser().resolve()
    if output.exists() or not output.parent.is_dir() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('Choose a fresh private output outside Git')
    core_path=Path(args.core).resolve();tools=Path(args.cc65_root).resolve()
    sources={name:Path(getattr(args,name+'_source')).resolve() for name in ('before','after')}
    support=Path(__file__).with_name('capture_miniplanets_audio.py').resolve()
    inputs=[core_path,*sources.values(),tools/'bin/ca65',tools/'bin/ld65',Path(__file__).resolve(),support]
    before={str(p):sha(p.read_bytes()) for p in inputs}
    if before[str(core_path)]!=CORE_SHA:raise ValueError('Unqualified FCEUmm binary')
    output.mkdir()
    retained=output/'verification-sources';retained.mkdir()
    for path in (Path(__file__).resolve(),support):(retained/path.name).write_bytes(path.read_bytes())
    core=Core(core_path,output);cases=[]
    for version,path in sources.items():
        raw=path.read_bytes();(output/(version+'-source.s')).write_bytes(raw)
        for selector in ('code','data'):
            for incoming in (0,1):
                folder=output/f'{version}-{selector}-I{incoming}'
                image,hashes,labels,selected=cartridge(folder,raw.decode(),selector,incoming,tools)
                for boundary in BOUNDARIES:
                    result=core.run(image,labels[selected+'_'+boundary])
                    trace=result.pop('trace');(folder/(boundary+'-trace.json')).write_text(json.dumps(trace,indent=2)+'\n')
                    result.update(version=version,selector=selector,incoming_I=incoming,boundary=boundary,
                                  helper_hashes=hashes,cartridge_sha256=sha(image.read_bytes()))
                    result['passed']=(result['completed'] and result['irqs']==1 and result['incoming_I_errors']==0
                        and result['physical_bank_mismatches']==0 and len(result['injected'])==1
                        and result['forwarding_observer_neutral'])
                    cases.append(result)
    core.lib.retro_deinit()
    after_ok=all(x['passed'] for x in cases if x['version']=='after')
    negative=all(not x['passed'] and x['physical_bank_mismatches']>0 for x in cases
                 if x['version']=='before' and x['incoming_I']==0 and x['boundary']=='bank_shadow')
    unchanged=before=={str(p):sha(p.read_bytes()) for p in inputs}
    receipt={'format':'fdisbull-nes-mapper-atomic-check-1','passed':after_ok and negative and unchanged,
        'core_sha256':CORE_SHA,'core_name':core.info.name.decode(),
        'core_version':core.info.version.decode(),
        'cases':cases,'fixed_passed':after_ok,'old_shadow_race_detected_both_selectors':negative,
        'inputs_unchanged':unchanged,'input_hashes':before,
        'claim':'exact helper instructions in authored MMC3 cartridges; actual pending IRQs and native physical-bank sentinels; no original game assets'}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('cases','input_hashes')},indent=2))
    return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
