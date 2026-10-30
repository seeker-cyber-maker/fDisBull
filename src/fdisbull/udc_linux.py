"""Linux ELF64 shell using the existing private x64 module ABI and lowering.

Builders never execute outputs. The explicit stdout adapter changes presentation
and acknowledgment; it does not assert MessageBox/console effect equivalence.
"""
from copy import deepcopy
from pathlib import Path
import os
import struct

from .udc_shell import (SLOT, _Code, _Lower, _module, _validate, _check,
                        _fields, _json, _sha, _text, _remove_owned_output)

BASE = 0x400000
PROFILE = 'linux-x64-state-arena-1'


def _write(code, *, fd, length, pointer):
    code.emit('b801000000bf');code.emit(struct.pack('<I',fd))
    if pointer=='stack':code.emit('4889e6')
    else:code.relative('488d35',pointer)
    code.emit('ba');code.emit(struct.pack('<I',length));code.emit('0f05')
    code.emit('483d');code.emit(struct.pack('<I',length))


def _provider(code,module,resources):
    end,failed=code.fresh(),code.fresh()
    # Preserve private Win64 nonvolatiles used by Linux's syscall convention.
    code.emit('5756')
    labels={key:code.fresh() for key in sorted(module['messages'],key=int)}
    for key,label in labels.items():
        code.emit('6681fa');code.emit(struct.pack('<H',int(key)));code.relative('0f84',label)
    default=code.fresh();code.relative('e9',default)
    for label,resource in [(labels[k],v) for k,v in sorted(module['messages'].items(),key=lambda pair:int(pair[0]))]+[(default,module['default'])]:
        code.mark(label)
        _write(code,fd=1,length=len(_text(resources[resource]['text']))-1,pointer='resource:'+resource)
        code.relative('0f85',failed)
        code.relative('e9',end)
    code.mark(failed);code.emit('ba03000000');done=code.fresh();code.relative('e9',done)
    code.mark(end);code.emit('31d2');code.mark(done);code.emit('31c05e5fc3')
    # text(resource) entry: RDX is an admitted ASCII resource pointer. Determine
    # its bounded length, then one write; partial/failed writes return status3.
    _check(len(code.data)<=SLOT//2,'Linux notification exceeds its fixed entry slot')
    code.emit(b'\xcc'*(SLOT//2-len(code.data)))
    code.emit('57564889d631d2');loop=code.fresh();ready=code.fresh();bad=code.fresh()
    code.mark(loop);code.emit('803c1600');code.relative('0f84',ready)
    code.emit('48ffc24881fa00100000');code.relative('0f83',bad);code.relative('e9',loop)
    code.mark(ready);code.emit('4989d2b801000000bf010000000f05')
    code.emit('4c39d0');code.relative('0f85',bad);code.emit('31c031d25e5fc3')
    code.mark(bad);code.emit('31c0ba030000005e5fc3')


def _entry(code,plan,state_size,capture_state):
    # Linux process entry has no C caller. Align, then enter a genuine SysV
    # function adapter whose private callee receives RCX=arena, EAX/EDX result.
    code.emit('4883e4f04883ec20')
    startup_fail=code.fresh()
    # rt_sigprocmask(SIG_BLOCK, &SIGPIPE_mask, NULL, 8). A closed pipe must
    # return EPIPE to the bounded write adapter rather than kill this process.
    code.emit('48c7042400100000b80e00000031ff4889e631d241ba080000000f054885c0')
    code.relative('0f85',startup_fail)
    code.relative('488d3d','state')
    code.relative('e8','sysv_adapter');code.emit('4989c6')
    export_fail=code.fresh()
    if capture_state:
        code.emit('c70424554443314c89f048c1e820894424044489742408')
        code.emit('c744240c');code.emit(struct.pack('<I',state_size))
        _write(code,fd=3,length=16,pointer='stack');code.relative('0f85',export_fail)
        _write(code,fd=3,length=state_size,pointer='state');code.relative('0f85',export_fail)
    code.emit('4c89f748c1ef20b83c0000000f050f0b')
    code.mark(export_fail);code.emit('bf04000000b83c0000000f050f0b')
    code.mark(startup_fail);code.emit('bf05000000b83c0000000f050f0b')
    _check(len(code.data)<SLOT//2,'Linux entry exceeds its fixed slot')
    code.emit(b'\xcc'*(SLOT//2-len(code.data)))
    code.mark('sysv_adapter')
    code.emit('41544883ec204989fc4c89e1');code.relative('e8','fn:'+plan['entry'])
    code.emit('89c048c1e2204809d04883c420415cc3')


def build_linux_shell(plan,modules,destination,*,service_adapters=None,capture_state=False,c_compiler=None):
    """Emit static ELF64, retaining the exact common math/function lowering.

    ``service_adapters`` must explicitly bind each notification to
    {backend:linux-stdout, acknowledgment:none}. No GUI equivalence is inferred.
    Optional FD3 observation writes UDC1 + status/u32 + value/u32 + size/u32,
    then sorted word-carrier arena bytes. Export failure exits4; builders don't run.
    """
    plan,modules=deepcopy(plan),deepcopy(modules);_validate(plan,modules)
    _check(type(capture_state) is bool,'capture_state must be boolean')
    services={n for n,m in modules.items() if m['backend'] not in ('uil','c-uil')}
    service_adapters=deepcopy(service_adapters or {})
    _check(isinstance(service_adapters,dict) and set(service_adapters)==services,'Linux needs an explicit adapter for every native notification')
    for adapter in service_adapters.values():
        _check(adapter=={'backend':'linux-stdout','acknowledgment':'none'},'unsupported Linux presentation adapter')
    destination=Path(destination).expanduser().resolve()
    _check(not destination.exists() and not any((p/'.git').exists() for p in (destination,*destination.parents)),'Linux output must be new and outside Git')
    from .udc_c import compile_c
    c_modules={n:compile_c(m,c_compiler) for n,m in modules.items() if m['backend']=='c-uil'}
    functions,bindings,resources=sorted(plan['functions']),sorted(modules),sorted(plan['resources'])
    cells=sorted(plan['state']);offsets={n:2*i for i,n in enumerate(cells)}
    names=['entry']+['fn:'+n for n in functions]+['module:'+n for n in bindings]
    symbols={n:0x1000+i*SLOT for i,n in enumerate(names)}
    symbols['sysv_adapter']=0x1800
    symbols.update({'module:'+n+':text':symbols['module:'+n]+SLOT//2 for n in services})
    text_size=len(names)*SLOT;rdata_rva=0x1000+text_size;rdata_size=(2+len(resources)+len(bindings))*SLOT
    symbols['state']=rdata_rva+rdata_size
    rdata=bytearray(rdata_size)
    for i,n in enumerate(resources):
        at=(1+i)*SLOT;raw=_text(plan['resources'][n]['text']);rdata[at:at+len(raw)]=raw;symbols['resource:'+n]=rdata_rva+at
    codes=[];code=_Code(symbols['entry'],'entry');_entry(code,plan,len(cells)*2,capture_state);codes.append(code)
    for n in functions:
        code=_Code(symbols['fn:'+n],'fn:'+n);end,fail=code.fresh(),code.fresh()
        code.emit('41544881ec');code.emit(struct.pack('<I',96));code.emit('4989cc')
        lower=_Lower(code,plan['state'],offsets,'r12',end,fail);lower.body(plan['functions'][n]['body'],'function.'+n)
        lower.value(plan['functions'][n].get('return',0));code.emit('0fb7c031d2');code.relative('e9',end)
        code.mark(fail);code.emit('ba01000000');code.mark(fail+':status');code.emit('31c0')
        code.mark(end);code.emit('4881c4');code.emit(struct.pack('<I',96));code.emit('415cc3');codes.append(code)
    for n in bindings:
        code=_Code(symbols['module:'+n],'module:'+n)
        if n in services:_provider(code,modules[n],plan['resources'])
        elif n in c_modules:
            from .udc_c import lower_c_module
            lower_c_module(code,modules[n],plan['state'],offsets,c_modules[n])
        else:_module(code,modules[n],plan['state'],offsets)
        codes.append(code)
    text=b''.join(c.resolve(symbols) for c in codes)
    state=b''.join(struct.pack('<H',int(plan['state'][n]['initial'])&65535) for n in cells)
    data=state+bytes(max(4096,((len(state)+4095)//4096)*4096)-len(state))
    header=bytearray(4096);header[:16]=b'\x7fELF\x02\x01\x01'+bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH',header,16,2,62,1,BASE+0x1000,64,0,0,64,56,3,0,0,0)
    for i,(flags,at,payload) in enumerate([(5,0,bytes(header)+text),(4,rdata_rva,bytes(rdata)),(6,symbols['state'],data)]):
        struct.pack_into('<IIQQQQQQ',header,64+i*56,1,flags,at,BASE+at,BASE+at,len(payload),len(payload),4096)
    image=bytes(header)+text+bytes(rdata)+data
    manifest={'format':'fdisbull-native-shell-build-1','profile':PROFILE,'plan_sha256':_sha(_json(plan)),'modules_sha256':_sha(_json(modules)),
      'c_modules':c_modules,'target':{'format':'ELF64','arch':'x86-64','image_base':hex(BASE),'load_profile':'static ET_EXEC; Linux syscalls; no unwind profile','original_binary_wrapped':False},
      'output':{'path':'program','absolute_path':str(destination/'program'),'sha256':_sha(image),'size':len(image)},
      'abi':{'private_arena':'RCX','private_result':'EAX','private_status':'EDX','public_adapter':'SysV RDI=arena, RAX=(status<<32)|u16-result','adapter_rva':0x1800},
      'state':{n:{'rva':symbols['state']+offsets[n],'carrier_bits':16,**plan['state'][n]} for n in cells},
      'slots':{c.prefix:{'rva':c.base,'file_offset':c.base,'size':SLOT,'sha256':_sha(text[c.base-0x1000:c.base-0x1000+SLOT]),'used_bytes':len(c.data),'source_map':c.maps} for c in codes},
      'resources':{n:{'rva':symbols['resource:'+n],'size':SLOT} for n in resources},
      'service_adapters':service_adapters,'observation':{'fd':3 if capture_state else None,'format':'UDC1/status-u32/value-u32/size-u32/arena','capture_failure_exit':4},
      'signals':{'SIGPIPE':'blocked before program entry; write errors return through adapters','startup_failure_exit':5},
      'qualification':{'native_execution':False,'source_to_uil':False,'scope':'authored static Linux shell; explicit stdout presentation lacks acknowledgment; runtime qualification separate'}}
    capsule={'format':'fdisbull-native-shell-capsule-1','plan':plan,'modules':modules,'build':manifest};payload=_json(capsule)+b'\n'
    destination.mkdir(mode=0o700,parents=True,exist_ok=False);owned=destination.stat();files={}
    try:
        for n,raw in [('program',image),('capsule.json',payload)]:
            p=destination/n
            with p.open('xb') as stream:
                st=os.fstat(stream.fileno());files[n]=(st.st_dev,st.st_ino);stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.chmod(p,0o700 if n=='program' else 0o600)
            _check(p.read_bytes()==raw,'Linux output readback mismatch')
    except BaseException:
        _remove_owned_output(destination,(owned.st_dev,owned.st_ino),files);raise
    return {**manifest,'directory':str(destination),'capsule':str(destination/'capsule.json')}


def decode_observation(data,build):
    """Validate a complete FD3 frame; an incomplete export is never a result."""
    _check(isinstance(data,bytes) and 16<=len(data)<=528,'invalid Linux observation length')
    _check(data[:4]==b'UDC1','invalid Linux observation magic')
    status,value,size=struct.unpack_from('<III',data,4)
    fields=sorted(build['state'],key=lambda n:build['state'][n]['rva'])
    _check(status in (0,1,2,3) and value<=65535 and size==2*len(fields) and len(data)==16+size,'incomplete or incompatible Linux observation')
    state={}
    for i,n in enumerate(fields):
        raw=struct.unpack_from('<H',data,16+2*i)[0];typ=build['state'][n]['type']
        _check(typ in ('bool','u8','u16','i16'),'unsupported Linux observation type')
        _check(typ not in ('bool','u8') or raw<=(1 if typ=='bool' else 255),'noncanonical Linux observation value')
        state[n]=bool(raw) if typ=='bool' else raw-65536 if typ=='i16' and raw>=32768 else raw
    return {'status':status,'value':value,'state':state,'complete_frame':True,'scope':'native observation only; caller must bind executable/process identity separately'}
