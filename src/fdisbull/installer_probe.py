"""Packer-independent, opt-in DOS installer observation using the owned backend.

Traces instruction fetches, not presumed completed instructions. Changed-code
fetches are unpacking/self-modification candidates, never automatic original-entry
claims. Only explicitly copied files are exposed through the scratch C: drive.
The emulator is not a host security boundary for hostile executable code.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time

from .image_intake import hash_file, file_identity
from .exepack import mz_info
from .dosbox_rpc import DOSBoxRPC


# Names describe the requested interface, not a claim that the program consumes
# the result, supports a specific card, or sends data outside the emulator.
_DOS = {0x19:'default-drive',0x30:'dos-version',0x36:'disk-free-space',
        0x35:'get-interrupt-vector',0x25:'set-interrupt-vector',0x3d:'open-file',
        0x3f:'read-file',0x42:'seek-file',0x40:'write-file',0x43:'file-attributes',0x44:'device-ioctl',
        0x48:'allocate-memory',0x49:'free-memory',0x4a:'resize-memory',
        0x4b:'execute-child',0x4c:'terminate',0x4e:'find-first',0x4f:'find-next',
        0x62:'get-psp'}


def interrupt_request(vector:int, registers:dict) -> dict:
    ax = registers.get('eax',0)&65535; ah=ax>>8
    if vector==0x21:
        name = {0x4408:'drive-removable',0x4409:'drive-remote',0x440d:'generic-block-ioctl'}.get(ax,_DOS.get(ah,'dos-service'))
    elif vector==0x10:
        name = 'video-state' if ah==15 else 'display-combination' if ax==0x1a00 else 'video-service'
    elif vector==0x11: name='bios-equipment-list'
    elif vector==0x12: name='bios-conventional-memory'
    elif vector==0x15: name='bios-system-service'
    elif vector==0x13: name='bios-disk-service'
    elif vector==0x1a: name='bios-clock-or-pci-service'
    elif vector==0x2f: name={0x1500:'mscdex-installation',0x4300:'xms-installation',0x4310:'xms-entry'}.get(ax,'multiplex-service')
    elif vector==0x33: name='mouse-reset-and-detect' if ax==0 else 'mouse-service'
    elif vector==0x67: name='ems-service'
    elif vector==0x16: name='keyboard-service'
    else: name='interrupt-service'
    return {'vector':vector,'ax':ax,'name':name,'inputs':{k:registers.get(k,0) for k in
        ('eax','ebx','ecx','edx','esi','edi','ds','es')},'completion':'not_observed'}


class TraceObserver:
    """Passive accounting over genuine backend fetch records; usable in tests."""
    def __init__(self,baseline:bytes,base:int, *, max_events=10000,max_candidates=128):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_16
        self.decoder=Cs(CS_ARCH_X86,CS_MODE_16)
        self.baseline=baseline; self.base=base; self.registers={}
        self.queries=[];self.candidates=[];self.pages=set();self.pending=[]
        self.count=0;self.max_events=max_events;self.max_candidates=max_candidates
        self.dropped_queries=0;self.dropped_candidates=0;self.decode_failures=0
        self.trace_hash=hashlib.sha256()

    def feed(self,event):
        if event.get('code_bits')!=16 or event.get('cpu_mode')!='real':
            raise ValueError('probe admits only real-mode 16-bit fetches')
        self.count+=1
        self.trace_hash.update(json.dumps(event,sort_keys=True,separators=(',',':')).encode()+b'\n')
        self.registers.update({k:int(v,0) if isinstance(v,str) else v for k,v in event['register_changes'].items()})
        address=event['address'];cs=int(address['segment'],0);ip=int(address['offset'],0)
        linear=cs*16+ip
        code=bytes.fromhex(event['execution_bytes'])
        ins=next(self.decoder.disasm(code,ip,count=1),None)
        if ins is None: self.decode_failures+=1;return
        # Results only when the caller's architectural successor is fetched.
        # Nested calls are separate. A nonreturning service remains unresolved.
        for request in list(self.pending):
            if request['return_cs_ip']==[cs,ip]:
                request.update(completion='caller-successor-observed',return_fetch=self.count,
                    outputs={k:self.registers.get(k,0) for k in
                             ('eax','ebx','ecx','edx','esi','edi','ds','es','flags')})
                self.pending.remove(request)
        relative=linear-self.base
        actual=bytes(ins.bytes)
        if 0<=relative<=len(self.baseline)-len(actual) and self.baseline[relative:relative+len(actual)]!=actual:
            page=linear//4096
            if page not in self.pages:
                self.pages.add(page)
                if len(self.candidates)<self.max_candidates:
                    self.candidates.append({'fetch':self.count,'cs':cs,'ip':ip,'linear':linear,
                        'bytes':len(actual),'current_sha256':hashlib.sha256(actual).hexdigest(),
                        'baseline_sha256':hashlib.sha256(self.baseline[relative:relative+len(actual)]).hexdigest(),
                        'classification':'changed-code-fetch','original_entry_established':False})
                else:self.dropped_candidates+=1
        op=actual[0]
        if op==0xcd and len(actual)==2:
            request=interrupt_request(actual[1],self.registers)
            request.update(kind='interrupt',fetch=self.count,cs=cs,ip=ip,
                           origin='program-arena' if 0<=relative<len(self.baseline) else 'outside-program-arena',
                           return_cs_ip=[cs,(ip+ins.size)&65535])
            if len(self.queries)<self.max_events:
                self.queries.append(request);self.pending.append(request)
            else:self.dropped_queries+=1
        elif op in (0xe4,0xe5,0xec,0xed,0xe6,0xe7,0xee,0xef):
            request={'kind':'port','fetch':self.count,'cs':cs,'ip':ip,
                     'port':actual[1] if op in (0xe4,0xe5,0xe6,0xe7) else self.registers.get('edx',0)&65535,
                     'direction':'read' if op in (0xe4,0xe5,0xec,0xed) else 'write',
                     'width':1 if op in (0xe4,0xec,0xe6,0xee) else 2,
                     'eax':self.registers.get('eax',0),'completion':'fetch_only'}
            if len(self.queries)<self.max_events:self.queries.append(request)
            else:self.dropped_queries+=1
        else:return

    def report(self):
        return {'fetch_records':self.count,'trace_sha256':self.trace_hash.hexdigest(),
                'decode_failures':self.decode_failures,'queries':self.queries,
                'changed_code_candidates':self.candidates,'query_records_dropped':self.dropped_queries,
                'candidate_pages_dropped':self.dropped_candidates,
                'instruction_completion':'only specific caller successors observed; fetch is not completion',
                'uncovered_probes':['memory-mapped BDA/ROM reads','far-call driver interfaces','unreached branches'],
                'generic_unpacking':'changed-code capture, not a universal runnable EXE rebuilder'}


def probe_installer(path,output, *, executable,arguments=(),companions=(),
                    max_fetches=50000,timeout_seconds=60,stop_offset=None,fast_forward=False):
    """Run only the explicit target in a throwaway, bounded emulated environment.

    Output includes private conventional-memory captures. Do not publish them.
    No target-supplied autoexec/config is admitted. Unknown emulator failures are
    not automatically retried. Cancellation closes the owned backend.
    """
    if type(fast_forward) is not bool:
        raise ValueError('fast_forward must be boolean')
    if type(max_fetches) is not int or not 1<=max_fetches<=1000000:
        raise ValueError('invalid instruction-fetch budget')
    if type(timeout_seconds) is not int or not 1<=timeout_seconds<=600:
        raise ValueError('invalid host deadline')
    if (not isinstance(arguments,(list,tuple)) or any(not isinstance(a,str) or
        re.search(r'[\x00-\x1f\x7f]',a) for a in arguments) or len(' '.join(arguments).encode('ascii','strict'))>126):
        raise ValueError('invalid DOS arguments')
    if stop_offset is not None and (type(stop_offset) is not int or not 0<=stop_offset<0xa0000):
        raise ValueError('invalid explicit load-relative stop offset')
    target=Path(path).absolute();exe=Path(executable).absolute();output=Path(output).absolute()
    sources=[target,*map(lambda p:Path(p).absolute(),companions)]
    identities=[];names=set()
    for p in sources:
        ident=file_identity(p)
        if not re.fullmatch(r'[A-Za-z0-9_!$~-]{1,8}(\.[A-Za-z0-9_!$~-]{1,3})?',p.name):
            raise ValueError('probe files require explicit DOS 8.3 names')
        if p.name.casefold() in names or ident['size']>16*1024*1024:
            raise ValueError('duplicate/oversized companion')
        names.add(p.name.casefold());identities.append({'name':p.name,'identity':ident,'sha256':hash_file(p)})
    image=target.read_bytes();m=mz_info(image) if image[:2]==b'MZ' else None
    if m is None and (target.suffix.lower()!='.com' or len(image)>65280):
        raise ValueError('admit DOS MZ or bounded COM only')
    output.mkdir(mode=0o700)
    report={'format':'fdisbull-installer-probe-1','status':'not_started','source_files':identities,
            'backend_sha256':hash_file(exe),'executes_target':True,
            'environment':'owned headless DOSBox, scratch C drive only; emulated hardware, not host inventory',
            'limits':{'max_fetches':max_fetches,'host_seconds':timeout_seconds},'fast_forward_requested':fast_forward,
            'original_entry_established':False,'rebuilt_runnable_executable':False}
    rpc=None;started=time.monotonic();deadline=started+timeout_seconds
    observer=None
    try:
        with tempfile.TemporaryDirectory(prefix='fdisbull-installer-scratch-') as tmp:
            scratch=Path(tmp)
            for p,identity in zip(sources,identities):
                shutil.copyfile(p,scratch/p.name)
                if hash_file(scratch/p.name)!=identity['sha256']:raise ValueError('source changed while copying')
            rpc=DOSBoxRPC(exe,scratch,window=False)
            session=rpc.call('session.start',{'target':{'command':target.name,'arguments':list(arguments)},
                'mounts':[{'drive':'C','host_path':str(scratch)}],'break_at':'entry'})
            sid=session['session_id']
            def call(method,params=None):
                left=max(1,int((deadline-time.monotonic())*1000))
                return rpc.call(method,{'session_id':sid,**(params or {})},timeout_ms=min(left,15000))
            if fast_forward:
                report['timing']=call('execution.timing',{'fast_forward':True})
            regs=call('state.get_registers')
            cs=int(regs['segments']['cs'],0)
            base=(cs-m['cs'])*16 if m else (cs*16+256)
            if not 0<=base<0xa0000:raise ValueError('program is not in conventional RAM')
            length=0xa0000-base
            def memory():
                result=bytearray()
                for at in range(base,base+length,65536):
                    n=min(65536,base+length-at)
                    response=call('memory.read',{'address':{'space':'linear','offset':f'0x{at:08X}'},'length':n})
                    chunk=base64.b64decode(response['data_base64'],validate=True)
                    if len(chunk)!=n:raise ValueError('incomplete native memory read')
                    result.extend(chunk)
                return bytes(result)
            baseline=memory();observer=TraceObserver(baseline,base)
            if stop_offset is not None:
                if stop_offset>=length:raise ValueError('stop offset outside captured arena')
                report['explicit_stop']=call('breakpoints.create',{'kind':'execution','once':True,
                    'address':{'space':'segmented','segment':f'0x{base//16+(stop_offset//65536)*4096:04X}',
                               'offset':f'0x{stop_offset%65536:08X}'}})
                report['requested_stop_offset']=stop_offset
            report.update(status='running',initial_registers=regs,capture_base=base,capture_length=length,
                          baseline_sha256=hashlib.sha256(baseline).hexdigest())
            while observer.count<max_fetches and time.monotonic()<deadline:
                count=min(10000,max_fetches-observer.count)
                call('trace.start',{'detail':'normal','instruction_count':count})
                op=call('execution.continue')
                while True:
                    if time.monotonic()>=deadline:
                        raise TimeoutError('host deadline exceeded')
                    stop=call('execution.wait',{'operation_id':op['operation_id'],'timeout_ms':100})
                    if not stop.get('running'):break
                cursor=None;batch=0
                while True:
                    page=call('trace.read',{'cursor':cursor,'limit':1000})
                    for event in page['events']:observer.feed(event);batch+=1
                    cursor=page.get('next_cursor')
                    if cursor is None:break
                call('trace.stop')
                report['last_stop']=stop
                if stop.get('stop_reason',{}).get('kind')=='guest_exit':
                    report['status']='guest_exit';break
                if stop.get('stop_reason',{}).get('kind')=='breakpoint':
                    report['status']='selected_boundary';break
                if not batch:report['status']='no_trace_progress';break
            else:
                report['status']='fetch_budget' if observer.count>=max_fetches else 'host_deadline'
            # Capture at the actual stopped boundary, not at a past candidate PC.
            if report['status']!='guest_exit':
                capture=memory();report['final_registers']=call('state.get_registers')
                (output/'conventional-memory.bin').write_bytes(capture)
                report['capture_sha256']=hashlib.sha256(capture).hexdigest()
                report['changed_memory_bytes']=sum(a!=b for a,b in zip(baseline,capture))
                report['capture_scope']='stopped-boundary RAM, includes stack/data/unpacker; not an unrelocated EXE'
            report['scratch_files_after']=[{'name':str(p.relative_to(scratch)),'bytes':p.stat().st_size,
                'sha256':hash_file(p)} for p in scratch.rglob('*') if p.is_file() and not p.is_symlink()]
    except (ValueError,OSError,TimeoutError,KeyError) as exc:
        report.update(status='incomplete',error=f'{type(exc).__name__}: {exc}')
    finally:
        if observer is not None:report.update(observer.report())
        if rpc is not None:
            process=rpc.process;rpc.close()
            report['owned_process_reaped']=process.poll() is not None
        report['host_elapsed_seconds']=round(time.monotonic()-started,3)
        report['originals_unchanged']=all(i['identity']==file_identity(p) and i['sha256']==hash_file(p)
            for p,i in zip(sources,identities))
        (output/'probe.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('path');p.add_argument('output');p.add_argument('--executable',required=True)
    p.add_argument('--arguments',default='[]',help='JSON array; no shell')
    p.add_argument('--companion',action='append',default=[])
    p.add_argument('--max-fetches',type=int,default=50000)
    p.add_argument('--fast-forward',action='store_true',help='Explicit faster-than-realtime emulation; timing may differ')
    p.add_argument('--timeout-seconds',type=int,default=60)
    p.add_argument('--stop-offset',type=lambda x:int(x,0),help='Explicit load-image-relative boundary; not auto-detected OEP')
    a=p.parse_args()
    try:
        report=probe_installer(a.path,a.output,executable=a.executable,arguments=json.loads(a.arguments),
            companions=a.companion,max_fetches=a.max_fetches,timeout_seconds=a.timeout_seconds,stop_offset=a.stop_offset,fast_forward=a.fast_forward)
        print(json.dumps(report,allow_nan=False));return 2 if report['status']=='incomplete' else 0
    except (ValueError,OSError) as exc:
        print(json.dumps({'status':'refused','error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
