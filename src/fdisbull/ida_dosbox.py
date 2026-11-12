"""One-client, loopback IDA interface-31 endpoint for an owned DOSBox session.

The emulator's existing CPU hooks implement breakpoints without patch bytes.
Project analysis and observations remain in fDisBull; this is an adapter to the
real emulator, not a replacement CPU or disassembler.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import socket
import threading
import time

from . import ida_wire as w
from .project import Project
from .ida_remote import RemoteDebugger

IOCTL = 39
EXTENSION = 0x01004644
REGISTER_NAMES = ('eax','ebx','ecx','edx','esi','edi','ebp','esp','eip','efl','cs','ds','es','fs','gs','ss')
DESCRIPTION = dict(classes=['General registers','Segment registers'], bits=[], default=1,
    registers=[dict(name=name,flags=2 if name=='eip' else 4 if name=='esp' else 0,
                    register_class=2 if i>=10 else 1,dtype=1 if i>=10 else 2)
               for i,name in enumerate(REGISTER_NAMES)])
# Native breakpoints continue themselves, real-mode segmented registers, safe
# emulation. Data watches stop after access, so LAZY_WATCHPTS is not advertised.
FLAGS = 16 | 128 | 512


class DOSRemoteDebugger(RemoteDebugger):
    def __init__(self, stream):
        super().__init__(stream,debugger_id=10)

    def extension(self, operation, **params):
        data=json.dumps(dict(op=operation,params=params),separators=(',',':'),allow_nan=False).encode()
        if len(data)>65536:raise ValueError('DOS extension request exceeds budget')
        reply=self.request(IOCTL,w.dd(EXTENSION)+w.dd(len(data))+data,timeout=660)
        self._success(reply)
        size=reply.dd()
        if size>w.MAX_PACKET:raise ValueError('DOS extension response exceeds budget')
        document=json.loads(reply.raw(size));reply.finish()
        self.pending=document['event']
        return document['result']


class Session:
    def __init__(self, project, executable, game_dir, **debug_options):
        self.project = project
        self.executable = executable
        self.game_dir = game_dir
        self.debug_options=debug_options
        self.debug = None
        self.pending = None
        self.queued = None
        self.operation = None
        self.mode = 0
        self.breakpoints = {}

    def close(self):
        if self.debug is not None:
            self.debug.close()

    @staticmethod
    def address(value, length=1):
        if not 0 <= value < 0x100000 or not 1 <= length <= 65536 or value+length > 0x100000:
            raise ValueError('DOS endpoint requires unwrapped real-mode memory')
        return dict(space='linear',offset=f'0x{value:08X}')

    def regs(self):
        result = self.debug.registers()
        if result['cpu_mode'] != 'real':
            raise ValueError('DOS endpoint currently requires real mode')
        values = {name:int(value,16) for name,value in result['general'].items()}
        values.update({name:int(value,16) for name,value in result['segments'].items()})
        values.update(eip=int(result['instruction_pointer'],16),efl=int(result['flags'],16))
        return values

    def event(self, kind, native=None):
        registers = self.regs()
        address = registers['cs']*16+registers['eip']
        result = dict(eid=kind,pid=self.debug.rpc.process.pid,tid=1,address=address,handled=True)
        if kind==1:
            result['module'] = dict(name=self.project.meta['filename'],base=self.debug.runtime_base,
                                    size=self.debug.module_size,rebase_to=self.debug.runtime_base)
        elif kind==5:
            result.update(hardware_address=w.MASK64,kernel_address=w.MASK64)
            native_id = (native or {}).get('stop_reason',{}).get('breakpoint_id')
            for value in self.breakpoints.values():
                if native_id in value['ids'] and value['type'] not in (4,8):
                    result['hardware_address'] = value['address']
        self.pending = result
        return result

    def poll(self, timeout_ms):
        if self.queued is not None:
            event, self.queued = self.queued, None
            return event
        if self.operation is None:
            return None
        result = self.debug.call('execution.wait',dict(operation_id=self.operation,timeout_ms=max(1,min(100,timeout_ms))))
        if result.get('running'):
            return None
        self.operation = None
        kind = result.get('stop_reason',{}).get('kind')
        if result.get('state') == 'exited':
            self.pending = dict(eid=2,pid=self.debug.rpc.process.pid,tid=1,address=0,handled=True,exit_code=0)
            return self.pending
        event = self.event(5 if kind=='breakpoint' else 6 if kind=='step' else 13,result)
        self.debug._event('ida-stop',dict(native=result,event=event))
        return event

    def read(self, address, size):
        result = self.debug.call('memory.read',dict(address=self.address(address,size),length=size))
        data = base64.b64decode(result['data_base64'],validate=True)
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=result['sha256']:
            raise ValueError('DOS native memory read failed verification')
        return data

    def dispatch(self, code, reader):
        if code==w.PROCESSES:
            reader.finish()
            data=w.dd(0) if self.debug is None else w.dd(1)+w.dd(self.debug.rpc.process.pid)+w.string(self.project.meta['filename'])
            return w.OK,w.dd(1)+data
        if code==w.INIT:
            reader.dq();reader.dd();reader.string();reader.string()
            if reader.dd()!=10:
                raise ValueError('Expected DOSBox debugger id 10')
            reader.finish()
            return w.OK,w.dd(1)+w.dq(FLAGS)+w.encode_register_set(DESCRIPTION)
        if code in (w.TERM,w.EXIT):
            reader.finish()
            self.close()
            return w.OK,w.dd(1) if code==w.EXIT else b''
        if code==w.START:
            path=reader.string();args=reader.string();directory=reader.string();flags=reader.dd()
            reader.string();reader.dd();reader.byte();env_count=reader.dd()
            if env_count or args or flags&8 or self.debug is not None or Path(path).name!=self.project.meta['filename']:
                raise ValueError('Endpoint launches only its selected original real-mode DOS project')
            reader.finish()
            self.debug=self.project.debugger(self.executable,self.game_dir,version=1,**self.debug_options)
            self.queued=self.event(1)
            return w.OK,w.dd(1)+w.dd(2)+w.string('dosbox')+w.encode_register_set(DESCRIPTION)
        if self.debug is None:
            raise ValueError('No DOS target')
        if code==w.GET_EVENT:
            timeout_ms=reader.dd();reader.finish()
            event=self.poll(timeout_ms)
            return w.OK,w.dd(1)+w.encode_event(event) if event else w.dd(0)
        if code==w.CONTINUE:
            event=w.decode_event(reader);reader.finish()
            if self.pending is None or event['pid']!=self.pending['pid'] or event['tid']!=1 or event['address']!=self.pending['address']:
                raise ValueError('Continuation does not match the stopped event')
            self.pending=None
            if self.mode==1:
                self.debug.call('execution.step',dict(mode='into'))
                self.queued=self.event(6)
            else:
                self.operation=self.debug.call('execution.continue')['operation_id']
            return w.OK,w.dd(1)
        if code==w.PAUSE:
            reader.finish()
            self.operation=self.debug.call('execution.pause')['operation_id']
            return w.OK,w.dd(1)
        if self.pending is None or self.operation is not None:
            raise ValueError('Operation requires a stopped DOS CPU')
        if code==w.STOPPED:
            reader.byte();reader.byte();reader.finish()
            return w.OK,b''
        if code==w.MEMORY_INFO:
            reader.finish()
            # One real-mode conventional-memory region, not inferred symbols.
            return w.OK,w.dd(5)+w.dd(1)+w.ea(0)+w.ea(0)+w.ea(0xa0000)+w.dd(7)+w.string('Conventional RAM')+w.string('')
        if code==33:
            tid,segment=reader.dd(),reader.dd();reader.finish()
            if tid!=1 or not 0<=segment<=0xffff:raise ValueError('Invalid real-mode segment')
            return w.OK,w.dd(1)+w.ea(segment*16)
        if code==48:
            reader.finish()
            return w.OK,w.encode_register_set(DESCRIPTION)
        if code==w.RESUME_MODE:
            tid,mode=reader.dd(),reader.dd();reader.finish()
            if tid!=1 or mode not in (0,1):raise ValueError('Only continue/step-into are supported')
            self.mode=mode
            return w.OK,w.dd(1)
        if code in (w.SUSPEND,w.RESUME):
            if reader.dd()!=1:raise ValueError('DOS has one emulated CPU thread')
            reader.finish()
            return w.OK,w.dd(1)
        if code==w.READ_REGS:
            tid,classes,count=reader.dd(),reader.dd(),reader.dd()
            if tid!=1 or count!=len(REGISTER_NAMES) or classes&~3:raise ValueError('Invalid DOS register request')
            mask=reader.raw((count+7)//8);reader.finish();values=self.regs()
            return w.OK,w.dd(1)+b''.join(w.integer_register(values[name]) for i,name in enumerate(REGISTER_NAMES) if mask[i//8]&(1<<(i%8)))
        if code==w.WRITE_REG:
            tid,index=reader.dd(),reader.dd();value=w.read_integer_register(reader);reader.finish()
            if tid!=1 or index>=len(REGISTER_NAMES):raise ValueError('Invalid register index')
            name=REGISTER_NAMES[index]
            self.debug.call('state.set_register',dict(register='FLAGS' if name=='efl' else name.upper(),value=value))
            if self.regs()[name]!=value:raise ValueError('DOS register edit readback differs')
            self.debug._event('ida-register-edit',dict(register=name,value=hex(value)))
            return w.OK,w.dd(1)
        if code==w.READ:
            address,size=reader.ea(),reader.dd();reader.finish()
            return w.OK,w.dd(size)+self.read(address,size)
        if code==w.WRITE:
            address,size=reader.ea(),reader.dd();self.address(address,size)
            data=reader.raw(size);reader.finish();before=self.read(address,size)
            self.debug.call('memory.write',dict(address=self.address(address,size),data_base64=base64.b64encode(data).decode(),
                                               expected_sha256=hashlib.sha256(before).hexdigest()))
            if self.read(address,size)!=data:raise ValueError('DOS write readback differs')
            self.debug._event('ida-memory-edit',dict(address=hex(address),before_hex=before.hex(),after_hex=data.hex()))
            return w.OK,w.dd(size)
        if code==w.BREAKPOINTS:
            return w.OK,self.update_breakpoints(reader)
        if code==IOCTL:
            function,size=reader.dd(),reader.dd()
            if function!=EXTENSION or size>65536:raise ValueError('Unsupported endpoint extension')
            request=json.loads(reader.raw(size));reader.finish()
            allowed={'screenshot':'screenshot','click-frame':'click_frame','click':'click','trace':'trace',
                     'save-state':'save_state','load-state':'load_state','layers':'layers',
                     'layer-patch':'layer_patch','layer-enable':'layer_enable','run':'run'}
            if request['op'] not in allowed:raise ValueError('Unknown endpoint extension')
            if request['op'] in ('save-state','load-state') and self.breakpoints:
                raise ValueError('Delete wire breakpoints before native state capture/restore')
            result=getattr(self.debug,allowed[request['op']])(**request.get('params',{}))
            event=self.event(13)
            data=json.dumps(dict(result=result,event=event),separators=(',',':'),allow_nan=False).encode()
            return w.OK,w.dd(1)+w.dd(len(data))+data
        return w.UNKNOWN,b''

    def update_breakpoints(self, reader):
        additions,deletions=reader.dd(),reader.dd()
        if additions+deletions>256 or len(self.breakpoints)+additions-deletions>256:
            raise ValueError('Breakpoint budget exceeded')
        results=[];address=0
        for _ in range(additions):
            address=(address+reader.ea())&w.MASK64
            size,kind,pid,tid=reader.dd(),reader.dd(),reader.dd(),reader.dd()
            if kind not in (1,2,3,4,8) or not 1<=size<=256 or kind in (4,8) and size!=1 or address in self.breakpoints:
                raise ValueError('Unsupported DOS breakpoint')
            self.address(address,size)
            original=self.read(address,1) if kind==4 else b''
            access={1:'w',2:'r',3:'rw',4:'execution',8:'execution'}[kind]
            ids=[]
            for i in range(size):
                native_address=self.address(address+i)
                if access=='execution':
                    # Heavy-debug real-mode execution compares physical fetch
                    # addresses. Canonical far pointers also match CS aliases.
                    native_address=dict(space='segmented',segment=f'0x{(address+i)>>4:04X}',offset=f'0x{(address+i)&15:08X}')
                result=self.debug.call('breakpoints.create',dict(kind=access,once=False,address=native_address))
                ids.append(result['breakpoint_id'])
            self.breakpoints[address]=dict(address=address,ids=ids,type=kind)
            results.append(b'\0'+(bytes([len(original)])+original if kind==4 else b''))
        address=0
        for _ in range(deletions):
            address=(address+reader.ea())&w.MASK64
            reader.raw(reader.byte());reader.dd();reader.dd();reader.dd()
            record=self.breakpoints.pop(address)
            for identifier in record['ids']:self.debug.delete_breakpoint(identifier)
            results.append(b'\0')
        reader.finish()
        self.debug._event('ida-breakpoints',dict(addresses=[hex(a) for a in self.breakpoints],guest_code_modified=False))
        return w.dd(1)+w.dd(additions+deletions)+b''.join(results)


class Endpoint:
    """Explicitly started, finite single-client server; disconnect reaps DOSBox."""
    def __init__(self, project, executable, game_dir, *, port=0, idle_timeout=120,
                 backend='dosbox',kernel=None,initramfs=None,files=None,boot_timeout_ms=240000,window=False):
        if type(port) is not int or not 0<=port<=65535 or not 1<=idle_timeout<=3600:
            raise ValueError('Invalid endpoint port/idle deadline')
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        if window and backend != 'dosbox':
            raise ValueError('window is supported only by the native DOSBox backend')
        self.project=Path(project).resolve(strict=True)
        self.executable=Path(executable).resolve(strict=True)
        self.game_dir=Path(game_dir).resolve(strict=True)
        if backend not in ('dosbox','dosbox-qemu'):raise ValueError('Expected a DOS backend')
        self.debug_options=dict(backend=backend,kernel=kernel,initramfs=initramfs,files=files,boot_timeout_ms=boot_timeout_ms,window=window)
        self._closing=threading.Event();self._spawned=None
        self.debug_options['_on_spawn']=self._own_process
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1',port));self.listener.listen(1)
        self.address=self.listener.getsockname()
        self.idle_timeout=idle_timeout
        self.channel=None;self.error=None;self.debug=None
        self.thread=threading.Thread(target=self._serve,name='fdisbull-dos-remote',daemon=False)

    def __enter__(self):
        self.thread.start()
        return self

    def _own_process(self,process):
        self._spawned=process
        if self._closing.is_set() and process.poll() is None:process.terminate()

    def _serve(self):
        session=None
        try:
            self.listener.settimeout(self.idle_timeout)
            stream,_=self.listener.accept()
            self.channel=w.Channel(stream)
            deadline=time.monotonic()+self.idle_timeout
            self.channel.send(w.OPEN,w.dd(w.INTERFACE)+w.dd(10)+w.dd(8),deadline)
            code,data=self.channel.receive(deadline);reader=w.Reader(data)
            if code!=w.OK or reader.dd()!=1 or reader.string()!='':raise ValueError('Invalid endpoint handshake')
            reader.finish();self.channel.send(w.OK,w.dd(1),deadline)
            with Project(self.project) as project:
                session=Session(project,self.executable,self.game_dir,**self.debug_options)
                try:
                    while True:
                        code,data=self.channel.receive(time.monotonic()+self.idle_timeout)
                        answer,payload=session.dispatch(code,w.Reader(data))
                        self.debug=session.debug
                        self.channel.send(answer,payload,time.monotonic()+self.idle_timeout)
                        if code in (w.EXIT,w.TERM):break
                finally:
                    session.close()
        except BaseException as error:
            self.error=error
            if self.channel is not None and self.channel.stream is not None and not isinstance(error,OSError):
                try:self.channel.send(52,w.string(str(error)[:4096]),time.monotonic()+1)
                except (OSError,w.ProtocolError):pass
        finally:
            if self.channel is not None:self.channel.close()
            self.listener.close()

    def close(self):
        self._closing.set()
        if self.debug is None and self._spawned is not None and self._spawned.poll() is None:self._spawned.terminate()
        if self.channel is not None:
            try:self.channel.stream.shutdown(socket.SHUT_RDWR)
            except (OSError,AttributeError):pass
            self.channel.close()
        try:self.listener.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.listener.close()
        self.thread.join(5)
        if self.thread.is_alive() and self.debug is not None:
            # A broken peer must not strand the emulator while its RPC worker
            # is waiting on a native stop. Terminate only this endpoint's child;
            # EOF lets the worker record closure on its own SQLite thread.
            process=self.debug.rpc.process
            if process.poll() is None:process.terminate()
        self.thread.join(15)
        if self.thread.is_alive():raise TimeoutError('DOS endpoint failed to reap its owned session')

    def __exit__(self,*args):
        self.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--executable',required=True)
    parser.add_argument('--game-dir',required=True)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--idle-timeout',type=int,default=120)
    parser.add_argument('--backend',choices=['dosbox','dosbox-qemu'],default='dosbox')
    parser.add_argument('--kernel');parser.add_argument('--initramfs');parser.add_argument('--files',type=json.loads)
    parser.add_argument('--dot-mode','--window',dest='window',action='store_true',help='Request dot-mode: a watch-only native DOSBox window')
    args=parser.parse_args()
    with Endpoint(args.project,args.executable,args.game_dir,port=args.port,idle_timeout=args.idle_timeout,
                  backend=args.backend,kernel=args.kernel,initramfs=args.initramfs,files=args.files,window=args.window) as endpoint:
        print(json.dumps(dict(host=endpoint.address[0],port=endpoint.address[1],interface=w.INTERFACE,debugger_id=10)),flush=True)
        endpoint.thread.join()
        if endpoint.error and not isinstance(endpoint.error,(w.ProtocolError,OSError)):
            raise endpoint.error


if __name__=='__main__':
    main()
