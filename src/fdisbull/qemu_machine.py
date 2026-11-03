"""One owned offline machine, shared by DOS, PE and boot-debugging profiles."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time
from functools import wraps

from .dosbox_rpc import DebuggerError
from .qemu_control import QemuControl


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class QemuMachine:
    def __init__(self, executable, *, kernel=None, initramfs=None, boot_image=None,
                 paused=False, restore=False, memory_mib=4096, cpus=2, timeout_ms=240000,on_spawn=None):
        self.process=None;self.qmp=None;self.gdb=None;self.machine_stopped=bool(paused)
        self.lock=threading.RLock()
        self.temporary=tempfile.TemporaryDirectory(prefix='fdisbull-vm-')
        root=Path(self.temporary.name);self.log_path=root/'boot.log';self.gdb_path=root/'gdb.sock';self.rpc_path=root/'rpc.sock'
        try:
            if on_spawn is not None and not callable(on_spawn):raise ValueError('Expected an internal process ownership callback')
            if type(memory_mib) is not int or not 16<=memory_mib<=8192 or type(cpus) is not int or not 1<=cpus<=8:
                raise ValueError('Machine memory must be 16..8192 MiB and CPUs 1..8')
            if (boot_image is None)==(kernel is None) or (kernel is None)!=(initramfs is None):
                raise ValueError('Choose a boot image or a kernel/initramfs pair')
            paths={'qemu':Path(executable).expanduser().resolve(strict=True)}
            paths.update({name:Path(path).expanduser().resolve(strict=True) for name,path in [('kernel',kernel),('initramfs',initramfs),('boot_image',boot_image)] if path is not None})
            if any(not p.is_file() for p in paths.values()) or not os.access(paths['qemu'],os.X_OK):raise ValueError('Expected regular QEMU and machine input files')
            version=subprocess.check_output([str(paths['qemu']),'--version'],text=True,stderr=subprocess.STDOUT,timeout=5).splitlines()[0]
            match=re.search(r'QEMU emulator version (\d+)\.(\d+)',version)
            if not match or tuple(map(int,match.groups()))<(9,1):raise DebuggerError('Machine debugging requires QEMU >= 9.1')
            self.inputs={name:dict(path=str(path),sha256=file_hash(path)) for name,path in paths.items()}
            self.inputs['qemu']['version']=version
            command=[str(paths['qemu']),'-accel','tcg,thread=multi','-machine','pc' if boot_image else 'q35','-cpu','max',
                     '-smp',str(cpus),'-m',str(memory_mib)+'M','-nic','none','-display','none','-monitor','none','-no-reboot',
                     '-serial',f'file:{self.log_path}','-serial',f'unix:{self.rpc_path},server=on,wait=off',
                     '-qmp',f'unix:{root/"qmp.sock"},server=on,wait=off',
                     '-chardev',f'socket,path={self.gdb_path},server=on,wait=off,id=fdisbullgdb','-gdb','chardev:fdisbullgdb']
            if boot_image:
                if ',' in str(paths['boot_image']):raise ValueError('Boot image paths cannot contain commas')
                # IDE disks need a writable view. QEMU's temporary snapshot
                # overlay keeps the selected source disk unchanged.
                command+=['-drive',f'file={paths["boot_image"]},format=raw,if=ide,snapshot=on','-boot','order=c']
            else:
                command+=['-kernel',str(paths['kernel']),'-initrd',str(paths['initramfs']),'-append',
                          'console=ttyS0,115200 rdinit=/init rootfstype=ramfs loglevel=4 panic=1 random.trust_cpu=on']
            if paused:command+=['-S']
            if restore:command+=['-incoming','defer']
            self.command=command
            with (root/'qemu.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            if on_spawn is not None:on_spawn(self.process)
            self.qmp=QemuControl(root/'qmp.sock',self.process,time.monotonic()+timeout_ms/1000)
            self.context=MachineContext(self)
        except BaseException as error:
            log=root/'qemu.log';diagnostic=log.read_text(errors='replace')[-4096:] if log.exists() else ''
            self.close()
            if isinstance(error,Exception):raise DebuggerError(str(error)+'\n'+diagnostic) from error
            raise

    def serial(self,deadline):
        stream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            while True:
                try:stream.connect(str(self.rpc_path));return stream
                except (FileNotFoundError,ConnectionRefusedError):
                    if self.process.poll() is not None or time.monotonic()>=deadline:raise DebuggerError('QEMU serial channel did not open')
                    time.sleep(.02)
        except BaseException:stream.close();raise

    def debugger(self):
        if self.gdb is None:
            from .gdb_rpc import GDBRemote
            self.gdb=GDBRemote(self.gdb_path,self.process,time.monotonic()+10)
        return self.gdb

    def close(self):
        if self.gdb is not None:self.gdb.close();self.gdb=None
        if self.qmp is not None:self.qmp.close();self.qmp=None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        if self.temporary is not None:self.temporary.cleanup();self.temporary=None


def machine_operation(function):
    @wraps(function)
    def invoke(self,*args,**kwargs):
        if not self.vm.lock.acquire(timeout=10):raise TimeoutError('Machine context is busy')
        try:
            guard=getattr(self.vm,'operation_guard',None)
            if guard is not None:guard(function.__name__)
            return function(self,*args,**kwargs)
        except BaseException:
            if self.vm.gdb is not None and self.vm.gdb.socket is None:self.vm.close()
            raise
        finally:self.vm.lock.release()
    return invoke


class MachineContext:
    """A machine CPU context, never confused with a process or DOSBox CPU."""
    context_id='machine'

    def __init__(self,vm):
        self.vm=vm;self.breakpoints={};self.next_bp=1;self.project=None;self.run_id=None
        self.capabilities=dict(context='machine',address_spaces=['physical','virtual'],
            execution_breakpoints=True,data_watchpoints=True,register_edit=True,save_states=False,code_layers=False,
            stop_scope='all machine vCPUs',threads='machine vCPUs; not operating-system threads')

    def bind(self,project,run_id):
        self.project=project;self.run_id=run_id;return self

    @machine_operation
    def status(self):
        from .debug_semantics import contract
        state=self.vm.qmp.call('query-status')
        return dict(context='machine',state='running' if state['running'] else 'stopped',native_state=state,capabilities=self.capabilities,
                    semantics=contract('qemu-machine'))

    @machine_operation
    def pause(self):
        self.vm.qmp.call('stop');self.vm.machine_stopped=True
        self.vm.debugger()
        return self.status()

    @machine_operation
    def resume(self):
        if self.breakpoints:raise ValueError('Remove machine breakpoints before resuming guest services; use bounded machine run while they are active')
        if self.vm.gdb is not None:self.vm.gdb.close();self.vm.gdb=None
        self.vm.qmp.call('cont');self.vm.machine_stopped=False
        return self.status()

    def _stopped(self):
        if self.vm.qmp.call('query-status')['running']:
            raise ValueError('Pause the machine context before inspecting or changing CPU state')
        self.vm.machine_stopped=True
        return self.vm.debugger()

    @machine_operation
    def registers(self):
        remote=self._stopped();values=remote.registers()
        text=self.vm.qmp.call('human-monitor-command',{'command-line':'info registers'})
        control={name:hex(int(value,16)) for name,value in re.findall(r'\b(CR0|CR2|CR3|CR4|EFER)=([0-9a-fA-F]+)',text)}
        cs=re.search(r'\bCS\s*=\s*[0-9a-fA-F]+\s+([0-9a-fA-F]+)',text)
        rip=int(values.get('rip',values.get('eip','0x0')),16)
        pc=hex(int(cs.group(1),16)+rip) if cs else None
        mode='unknown'
        if 'CR0' in control:mode='real' if not int(control['CR0'],16)&1 else 'long' if int(control.get('EFER','0'),16)&0x400 else 'protected'
        return dict(context='machine',architecture=remote.architecture,cpu_mode=mode,registers=values,control=control,
                    instruction_pointer=hex(rip),linear_pc=pc,address_context='selected QEMU vCPU; virtual memory uses its page tables')

    @machine_operation
    def memory(self,address,*,length=16,space='physical'):
        value=int(address,0) if isinstance(address,str) else address
        data=self._stopped().memory(value,length,space=space)
        return dict(context='machine',address=hex(value),space=space,hex=data.hex(),length=len(data))

    @machine_operation
    def write_memory(self,address,data_hex,*,expected_hex,space='physical'):
        data=bytes.fromhex(data_hex);expected=bytes.fromhex(expected_hex)
        if not data or len(data)!=len(expected):raise ValueError('Machine edit requires equally sized expected and replacement bytes')
        value=int(address,0) if isinstance(address,str) else address;remote=self._stopped()
        if remote.memory(value,len(data),space=space)!=expected:raise DebuggerError('Machine memory guard differs')
        after=remote.memory(value,len(data),space=space,data=data)
        if after!=data:self.vm.close();raise DebuggerError('Machine memory readback differs')
        return dict(context='machine',address=hex(value),space=space,before_hex=expected_hex,after_hex=after.hex())

    @machine_operation
    def write_registers(self,registers):
        remote=self._stopped();before=remote.registers()
        if not isinstance(registers,dict) or not registers:raise ValueError('Expected guarded machine register edits')
        edits={}
        for name,item in registers.items():
            if not isinstance(item,dict) or set(item)!={'expected','value'} or name not in before:raise ValueError('Invalid guarded machine register edit')
            expected=int(item['expected'],0) if isinstance(item['expected'],str) else item['expected']
            value=int(item['value'],0) if isinstance(item['value'],str) else item['value']
            descriptor=next((r for r in remote.register_description if r['name']==name),None)
            if type(value) is not int or descriptor is None or not 0<=value<1<<(descriptor['size']*8):
                raise ValueError('Invalid machine register value')
            if before[name] is None or int(before[name],16)!=expected:raise DebuggerError('Machine register guard differs')
            edits[name]=value
        try:
            for name,value in edits.items():remote.set_register(name,value)
            after=remote.registers()
            if any(int(after[name],16)!=value for name,value in edits.items()):raise DebuggerError('Machine register readback differs')
        except BaseException:self.vm.close();raise
        return self.registers()

    @machine_operation
    def breakpoint(self,address,*,access='x',length=1):
        value=int(address,0) if isinstance(address,str) else address
        if access not in ('x','r','w','rw') or type(length) is not int or not 1<=length<=65536 or type(value) is not int or not 0<=value<2**64:
            raise ValueError('Invalid machine breakpoint')
        if access=='x' and length!=1:raise ValueError('Machine execution breakpoint length must be one')
        remote=self._stopped();kind={'x':1,'w':2,'r':3,'rw':4}[access]
        if len(self.breakpoints)>=256 or any((r['kind'],r['address'],r['length'])==(kind,value,length) for r in self.breakpoints.values()):
            raise ValueError('Duplicate machine breakpoint or breakpoint budget exceeded')
        if remote.request(f'Z{kind},{value:x},{length:x}')!=b'OK':raise DebuggerError('Machine breakpoint rejected')
        identifier='machine-bp-'+str(self.next_bp);self.next_bp+=1
        self.breakpoints[identifier]=dict(address=value,kind=kind,length=length,access=access)
        return dict(context='machine',breakpoint_id=identifier,address=hex(value),access=access,length=length,
                    address_space='selected-vCPU virtual address',guest_code_modified=False,mechanism='QEMU TCG breakpoint/watchpoint')

    @machine_operation
    def delete_breakpoint(self,breakpoint_id):
        record=self.breakpoints[breakpoint_id];remote=self._stopped()
        if remote.request(f'z{record["kind"]},{record["address"]:x},{record["length"]:x}')!=b'OK':raise DebuggerError('Machine breakpoint removal failed')
        del self.breakpoints[breakpoint_id]
        return dict(deleted=True,context='machine')

    def _execute(self,command,timeout_ms):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine timeout must be 1..600000 ms')
        remote=self._stopped();reply,timed_out=remote.execute(command,timeout_ms)
        if reply[:1] not in (b'T',b'S',b'W',b'X'):self.vm.close();raise DebuggerError('Invalid machine stop reply')
        self.vm.machine_stopped=True;native=reply.decode('ascii')
        regs=self.registers() if reply[:1] in (b'T',b'S') else None
        pc=int(regs['linear_pc'],16) if regs and regs['linear_pc'] else None
        watch=re.search(r'(?:^|;)(?:watch|rwatch|awatch):([0-9a-fA-F]+)',native)
        ids=[key for key,bp in self.breakpoints.items() if bp['access']=='x' and bp['address']==pc or watch and bp['access']!='x' and bp['address']<=int(watch.group(1),16)<bp['address']+bp['length']]
        signal=int(native[1:3],16)
        kind='exited' if reply[:1] in (b'W',b'X') else 'timeout' if timed_out else 'watchpoint' if watch else 'breakpoint' if ids else 'exception' if signal!=5 else 'step' if command=='s' else 'stopped'
        result=dict(context='machine',outcome=kind,timed_out=timed_out,session=dict(state='exited' if kind=='exited' else 'stopped',stop_reason=dict(kind=kind,
                    address=hex(pc) if pc is not None else None,breakpoint_ids=ids,native_reply=native)),registers=regs)
        from .debug_semantics import normalize_stop
        result['stop']=normalize_stop('qemu-machine',result['session']['stop_reason'],outcome=kind)
        if self.project:self._event('machine-'+('step' if command=='s' else 'run'),result)
        return result

    @machine_operation
    def step(self,*,timeout_ms=10000):return self._execute('s',timeout_ms)
    @machine_operation
    def run(self,*,timeout_ms=10000):return self._execute('c',timeout_ms)

    def _event(self,operation,value):
        from .debugger import stamp
        with self.project.transaction(True):
            self.project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                                    (self.run_id,stamp(),operation,json.dumps(value)))

    def _artifact(self,name,kind,data,metadata):
        if self.project is None:raise ValueError('Machine artifact requires a project-bound session')
        return self.project._debug_artifact(self.run_id,name,kind,data,metadata)

    @machine_operation
    def trace(self,name='machine-trace.json',*,count=128,timeout_ms=10000,bits=None):
        from iced_x86 import Decoder
        if type(count) is not int or not 1<=count<=10000:raise ValueError('Machine trace count must be 1..10000')
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine trace timeout must be 1..600000')
        if bits not in (16,32,64):raise ValueError('Machine traces require explicit instruction bitness')
        deadline=time.monotonic()+timeout_ms/1000;events=[];state=None
        while len(events)<count:
            before=self.registers()
            if before['cpu_mode']=='real' and bits!=16 or before['cpu_mode']=='long' and bits!=64:
                raise ValueError('Trace bitness differs from observed machine CPU mode')
            if before['linear_pc'] is None:raise ValueError('Selected machine CPU has no established linear PC')
            pc=int(before['linear_pc'],16);data=bytes.fromhex(self.memory(pc,length=15,space='virtual')['hex'])
            instruction=Decoder(bits,data,ip=pc).decode()
            if instruction.is_invalid:raise DebuggerError('Invalid machine instruction')
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:break
            state=self.step(timeout_ms=remaining)
            if state['outcome']!='step':break
            events.append(dict(address=hex(pc),bytes=data[:instruction.len].hex(),registers=before,phase='before',completion='confirmed native step'))
        if len(events)<count and time.monotonic()>=deadline and (state is None or state['outcome']=='step'):
            state=dict(context='machine',outcome='timeout',timed_out=True,session=dict(state='stopped',stop_reason=dict(kind='timeout',origin='trace-deadline')))
        result=dict(context='machine',events=events,complete=len(events)==count,requested_count=count,session=state,
                    semantics='completed steps on selected vCPU; QEMU default stepping masks IRQs/timers; full machine stopped between calls',bits=bits)
        from .debug_semantics import normalize_trace,contract
        normalize_trace('qemu-machine',events,version=self.version['id'] if hasattr(self,'version') else None)
        result['observation_contract']=contract('qemu-machine')
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),dict(event_count=len(events),complete=result['complete'],context='machine'))

    @machine_operation
    def screenshot(self,name='machine.png',*,grid=False,grid_step=8):
        from PIL import Image
        self._stopped()
        path=Path(self.vm.temporary.name)/'screen.ppm';path.unlink(missing_ok=True)
        self.vm.qmp.call('screendump',{'filename':str(path)})
        with Image.open(path) as image:
            output=io.BytesIO();image.save(output,format='PNG');size=image.size
        data=output.getvalue();artifact=self._artifact(name,'screenshot',data,dict(context='machine',width=size[0],height=size[1],sha256=hashlib.sha256(data).hexdigest(),capture='QEMU stored display surface'))
        return self.project.debug_grid(artifact['artifact'],name=name+'.grid.png',step=grid_step) if grid else artifact


class MachineDebugSession(MachineContext):
    """Project-bound raw boot image using the same saved-artifact interfaces."""
    def __init__(self,project,executable,*,boot_image,version=None,boot_timeout_ms=30000):
        import uuid
        from .debugger import stamp
        selected=project.version(version);image=Path(boot_image).expanduser().resolve(strict=True)
        if project.meta['format']!='raw' or project.meta['arch']!='x86' or selected['parent'] is not None:
            raise ValueError('Machine boot launch requires an original unpatched raw x86 project')
        if not image.is_file() or image.stat().st_size>64*1024*1024 or file_hash(image)!=project.meta['source_sha256']:
            raise ValueError('Boot image differs from the selected raw project')
        vm=QemuMachine(executable,boot_image=image,paused=True,memory_mib=128,cpus=1,timeout_ms=boot_timeout_ms)
        super().__init__(vm)
        self.rpc=vm;vm.context=self;self.closed=False;self.version=selected;self.run_id=uuid.uuid4().hex;self.project=project
        self.metadata=dict(backend='qemu-machine',source_sha256=project.meta['source_sha256'],version_sha256=selected['sha256'],
                           runtime_inputs=vm.inputs,context='machine',address_mapping='explicit physical/selected-vCPU virtual addresses',capabilities=self.capabilities)
        try:
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,selected['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            project._live_debuggers.append(self)
        except BaseException:vm.close();raise

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def contexts(self):return dict(run=self.run_id,selected='machine',contexts=[dict(id='machine',kind='machine',capabilities=self.capabilities)])
    def context(self,name):
        if name!='machine':raise ValueError('This session owns only the machine context')
        return self
    def trace(self,name='machine-trace.json',*,count=128,timeout_ms=10000,bits=None):
        return super().trace(name,count=count,timeout_ms=timeout_ms,bits=self.project.bits if bits is None else bits)
    @property
    def script_operations(self):
        return {'run','registers','memory','breakpoint','delete-breakpoint','trace','screenshot','assert','status','write-memory','write-registers'}
    def script(self,*args,**kwargs):
        from .debugger import DebugSession
        return DebugSession.script(self,*args,**kwargs)
    def status(self):return dict(super().status(),run=self.run_id,version=self.version['id'],mapping=self.metadata)
    def close(self):
        if self.closed:return
        from .debugger import stamp
        self.vm.close();self.closed=True
        with self.project.transaction(True):
            self.project.db.execute('UPDATE debug_runs SET ended=?,state=? WHERE id=?',(stamp(),'exited',self.run_id))
        if self in self.project._live_debuggers:self.project._live_debuggers.remove(self)
