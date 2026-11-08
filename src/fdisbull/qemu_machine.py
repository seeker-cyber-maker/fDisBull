"""One owned offline machine, shared by DOS, PE and boot-debugging profiles."""
from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from functools import wraps

from .dosbox_rpc import DebuggerError
from .qemu_control import QemuControl
from .qemu_transport import PipeChannel, create_fifo_pair, open_fifo_pair
from .memory_search_runtime import MemorySearchSessionMixin
from .memory_rules import MemoryRuleSessionMixin
from .desqview_runtime import DesqviewSessionMixin


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def firmware_identity(directory):
    """Record the explicitly selected QEMU ROM search directory, not an OS."""
    root=Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('QEMU firmware must be a directory')
    files=sorted((item for item in root.iterdir() if item.is_file()),key=lambda item:item.name)
    if not files or len(files)>1024 or sum(item.stat().st_size for item in files)>1024**3:
        raise ValueError('QEMU firmware directory exceeds the bounded identity inventory')
    entries=[dict(name=item.name,sha256=file_hash(item),size=item.stat().st_size) for item in files]
    digest=hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(path=str(root),sha256=digest,files=entries,
                scope='top-level firmware file identities at admission; not guest OS qualification')


class QemuMachine:
    def __init__(self, executable, *, kernel=None, initramfs=None, boot_image=None,
                 paused=False, restore=False, memory_mib=4096, cpus=2, timeout_ms=240000,on_spawn=None,
                 cpu_model='max', boot_image_sha256=None, boot_device='ide', transport='unix', firmware=None):
        self.process=None;self.qmp=None;self.gdb=None;self.machine_stopped=bool(paused)
        self.transport=transport;self._channels=[];self._serial_channel=None
        self.lock=threading.RLock()
        self.temporary=tempfile.TemporaryDirectory(prefix='fdisbull-vm-')
        root=Path(self.temporary.name);self.log_path=root/'boot.log';self.gdb_path=root/'gdb.sock';self.rpc_path=root/'rpc.sock'
        try:
            if on_spawn is not None and not callable(on_spawn):raise ValueError('Expected an internal process ownership callback')
            if transport not in ('unix','pipe'):raise ValueError('QEMU transport must be unix or pipe')
            if transport=='pipe' and os.name!='posix':raise ValueError('QEMU pipe transport requires a POSIX host')
            if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine timeout must be 1..600000 ms')
            if type(memory_mib) is not int or not 16<=memory_mib<=8192 or type(cpus) is not int or not 1<=cpus<=8:
                raise ValueError('Machine memory must be 16..8192 MiB and CPUs 1..8')
            if cpu_model not in ('max', '486'):
                raise ValueError('Unsupported machine CPU profile')
            if boot_device not in ('ide', 'floppy') or boot_device == 'floppy' and boot_image is None:
                raise ValueError('Unsupported machine boot device')
            if boot_image_sha256 is not None and (boot_image is None or not isinstance(boot_image_sha256,str)
                    or re.fullmatch(r'[0-9a-f]{64}',boot_image_sha256) is None):
                raise ValueError('A pinned boot image requires its SHA-256 identity')
            if (boot_image is None)==(kernel is None) or (kernel is None)!=(initramfs is None):
                raise ValueError('Choose a boot image or a kernel/initramfs pair')
            paths={'qemu':Path(executable).expanduser().resolve(strict=True)}
            paths.update({name:Path(path).expanduser().resolve(strict=True) for name,path in [('kernel',kernel),('initramfs',initramfs),('boot_image',boot_image)] if path is not None})
            if any(not p.is_file() for p in paths.values()) or not os.access(paths['qemu'],os.X_OK):raise ValueError('Expected regular QEMU and machine input files')
            # Cold executable startup can be slow under native/translated CI.
            version=subprocess.check_output([str(paths['qemu']),'--version'],text=True,stderr=subprocess.STDOUT,timeout=30).splitlines()[0]
            match=re.search(r'QEMU emulator version (\d+)\.(\d+)',version)
            if not match or tuple(map(int,match.groups()))<(9,1):raise DebuggerError('Machine debugging requires QEMU >= 9.1')
            self.inputs={name:dict(path=str(path),sha256=file_hash(path)) for name,path in paths.items()}
            self.inputs['qemu']['version']=version
            if firmware is not None:self.inputs['firmware']=firmware_identity(firmware)
            self.machine_configuration=dict(cpu=cpu_model,memory_mib=memory_mib,cpus=cpus,network='none',accelerator='tcg',
                                            disk='private-verified-copy-and-snapshot' if boot_image else None,
                                            boot_device=boot_device if boot_image else None,control_transport=transport,
                                            firmware='explicit-directory' if firmware is not None else 'QEMU default search path; not pinned',
                                            hostcalls='not configured; experimental FDB_HOSTCALL_/FDB_LAYER_ selectors removed')
            selected_boot=paths.get('boot_image')
            if boot_image_sha256 is not None:
                if self.inputs['boot_image']['sha256']!=boot_image_sha256:
                    raise ValueError('Boot image changed after guest profile admission')
            if boot_image is not None:
                # A caller may subsequently edit its source image. The owned
                # run uses a private byte-verified copy and a disposable overlay.
                selected_boot=root/'boot-image.raw'
                shutil.copyfile(paths['boot_image'],selected_boot)
                if file_hash(selected_boot)!=self.inputs['boot_image']['sha256']:
                    raise ValueError('Boot image changed while creating its private runtime copy')
            command=[str(paths['qemu']),'-accel','tcg,thread=multi','-machine','pc' if boot_image else 'q35','-cpu',cpu_model,
                     '-smp',str(cpus),'-m',str(memory_mib)+'M','-nic','none','-display','none','-monitor','none','-no-reboot',
                     '-serial',f'file:{self.log_path}']
            if transport=='pipe':
                self.gdb_path=root/'gdb';self.rpc_path=root/'rpc'
                create_fifo_pair(self.gdb_path);create_fifo_pair(self.rpc_path)
                command+=['-serial',f'pipe:{self.rpc_path}','-qmp','stdio',
                          '-chardev',f'pipe,path={self.gdb_path},id=fdisbullgdb','-gdb','chardev:fdisbullgdb']
            else:
                command+=['-serial',f'unix:{self.rpc_path},server=on,wait=off',
                          '-qmp',f'unix:{root/"qmp.sock"},server=on,wait=off',
                          '-chardev',f'socket,path={self.gdb_path},server=on,wait=off,id=fdisbullgdb','-gdb','chardev:fdisbullgdb']
            if firmware is not None:command+=['-L',self.inputs['firmware']['path']]
            if boot_image:
                if ',' in str(selected_boot):raise ValueError('Boot image paths cannot contain commas')
                # DOS disks need a writable view. QEMU's temporary snapshot
                # overlay keeps the selected source disk unchanged.
                command+=['-drive',f'file={selected_boot},format=raw,if={boot_device},snapshot=on',
                          '-boot','order=a' if boot_device=='floppy' else 'order=c']
            else:
                command+=['-kernel',str(paths['kernel']),'-initrd',str(paths['initramfs']),'-append',
                          'console=ttyS0,115200 rdinit=/init rootfstype=ramfs loglevel=4 panic=1 random.trust_cpu=on']
            if paused:command+=['-S']
            if restore:command+=['-incoming','defer']
            self.command=command
            # An earlier local experiment must not silently activate an escape
            # opcode in a custom QEMU build. This profile installs no plugins
            # or hostcalls; those require their own later migration slice.
            environment={key:value for key,value in os.environ.items()
                         if not key.startswith(('FDB_HOSTCALL_','FDB_LAYER_'))}
            deadline=time.monotonic()+timeout_ms/1000
            with (root/'qemu.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=root,stdin=subprocess.PIPE if transport=='pipe' else subprocess.DEVNULL,
                                              stdout=subprocess.PIPE if transport=='pipe' else log,stderr=log,bufsize=0,env=environment)
            if on_spawn is not None:on_spawn(self.process)
            if transport=='pipe':
                channel=PipeChannel(self.process.stdout,self.process.stdin,process=self.process);self._channels.append(channel)
                self.qmp=QemuControl(None,self.process,deadline,channel=channel)
            else:
                self.qmp=QemuControl(root/'qmp.sock',self.process,deadline)
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:raise TimeoutError('QEMU control startup deadline expired')
            self.qmp_commands=frozenset(item['name'] for item in self.qmp.call('query-commands',timeout_ms=remaining))
            self.context=MachineContext(self)
        except BaseException as error:
            log=root/'qemu.log';diagnostic=log.read_text(errors='replace')[-4096:] if log.exists() else ''
            self.close()
            if isinstance(error,Exception):raise DebuggerError(str(error)+'\n'+diagnostic) from error
            raise

    def serial(self,deadline):
        if self.transport=='pipe':
            if time.monotonic()>=deadline:raise TimeoutError('QEMU serial deadline expired')
            if self._serial_channel is None:
                self._serial_channel=open_fifo_pair(self.rpc_path,self.process);self._channels.append(self._serial_channel)
            return self._serial_channel
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
            if self.transport=='pipe':
                channel=open_fifo_pair(self.gdb_path,self.process);self._channels.append(channel)
                self.gdb=GDBRemote(None,self.process,time.monotonic()+10,channel=channel)
            else:self.gdb=GDBRemote(self.gdb_path,self.process,time.monotonic()+10)
        return self.gdb

    def close(self):
        if self.gdb is not None:self.gdb.close();self.gdb=None
        if self.qmp is not None:self.qmp.close();self.qmp=None
        for channel in self._channels:channel.close()
        self._channels.clear()
        if self.process is not None:
            for stream in (self.process.stdin,self.process.stdout):
                if stream is not None:stream.close()
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
            gdb_failed=self.vm.gdb is not None and self.vm.gdb.socket is None
            qmp=getattr(self.vm,'qmp',None)
            qmp_failed=qmp is not None and hasattr(qmp,'socket') and qmp.socket is None
            if gdb_failed or qmp_failed:self.vm.close()
            raise
        finally:self.vm.lock.release()
    return invoke


class MachineContext(DesqviewSessionMixin, MemoryRuleSessionMixin, MemorySearchSessionMixin):
    """A machine CPU context, never confused with a process or DOSBox CPU."""
    context_id='machine'

    def __init__(self,vm):
        self.vm=vm;self.breakpoints={};self.next_bp=1;self.project=None;self.run_id=None
        self.capabilities=dict(context='machine',address_spaces=['physical','virtual'],
            execution_breakpoints=True,data_watchpoints=True,register_edit=True,save_states=False,code_layers=False,
            screenshot='screendump' in getattr(vm,'qmp_commands',()),
            memory_translation='observed non-PAE 386 4-KiB pages; paused machine only',
            qemm_observation=False,
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
        # FIFOs do not produce a new GDB connection event when a client opens
        # them again. Keep the completed protocol session alive across QMP
        # continue/stop; there is no outstanding GDB execution request here.
        if self.vm.gdb is not None and getattr(self.vm,'transport','unix')!='pipe':
            self.vm.gdb.close();self.vm.gdb=None
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
        from .dos_memory import machine_address_state
        observed=machine_address_state(values,text)
        observed['address_state']['machine_vcpus']=getattr(self.vm,'machine_configuration',{}).get('cpus')
        return dict(context='machine',architecture=remote.architecture,registers=values,**observed,
                    address_context='selected QEMU vCPU; virtual memory uses its page tables')

    @machine_operation
    def memory_translation(self,address):
        """Observe a linear-to-physical mapping without binding or modifying RAM."""
        from .dos_memory import translate_386_page
        remote=self._stopped()
        registers=self.registers()
        result=translate_386_page(address,registers['address_state'],
                                  lambda location,length:remote.memory(location,length,space='physical'))
        result.update(context='machine',cpu_mode=registers['cpu_mode'],
                      address_state=registers['address_state'])
        if self.project:self._event('machine-memory-translation',result)
        return result

    @machine_operation
    def qemm_observe(self,address,*,length=1120):
        """Retain a QPI helper report already present in stopped guest memory.

        Reading a report does not execute its producer or establish freshness.
        The retained state is explicitly guest-reported, never a qualification
        of QEMM execution or current page ownership.
        """
        from .qpi import parse_qpi_report, REPORT_SIZE
        from .debugger import stamp
        profile=getattr(self,'guest_profile',None)
        if (profile is None or profile.get('memory_manager',{}).get('configured') != 'qemm'
                or self.project is None or not hasattr(self,'metadata')):
            raise ValueError('QEMM observation requires a project-bound QEMM guest profile')
        if type(length) is not int or length!=REPORT_SIZE:
            raise ValueError(f'QPI observation requires exactly {REPORT_SIZE} bytes')
        value=int(address,0) if isinstance(address,str) else address
        if type(value) is not int or not 0<=value<=0x100000000-length:
            raise ValueError('QPI report requires a bounded 32-bit virtual address')
        remote=self._stopped()
        registers=self.registers()
        data=remote.memory(value,length,space='virtual')
        report=parse_qpi_report(data)
        active=report['qemm']['active']
        observed='guest-reported-active' if active is True else 'guest-reported-inactive' if active is False else 'unknown'
        identity=dict(run=self.run_id,boot_image_sha256=profile['boot_image']['sha256'],
                      profile_sha256=profile['profile_sha256'],
                      emulator_sha256=self.vm.inputs['qemu']['sha256'])
        observation=dict(observed=observed,captured_at=stamp(),report_sha256=report['sha256'],
                         complete=report['probe_status']['complete'],probe_status=report['probe_status'],
                         active=active,version=report['qemm']['version'],
                         address=hex(value),space='virtual',length=length,identity=identity,
                         guest_api_called=False,freshness='not_established',
                         native_execution_validation='not_established_by_report',
                         scope='QPI report bytes read at this paused machine stop; producer and report age are unverified')
        artifact=self._artifact('qpi-report.bin','qpi-report',data,
                                deepcopy(dict(observation=observation,registers=registers,report=report)))
        observation['artifact']=artifact['artifact']
        result=dict(context='machine',observation=observation,registers=registers,report=report,
                    artifact={key:item for key,item in artifact.items() if key!='metadata'})
        self._event('qemm-observe',result)
        metadata=deepcopy(self.metadata)
        metadata['qemm_observation']=observation
        manager=metadata['guest_profile']['memory_manager']
        manager.update(observed=observed,report_sha256=report['sha256'],
                       report_complete=report['probe_status']['complete'],
                       observation_scope=observation['scope'])
        with self.project.transaction(True):
            self.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?',(json.dumps(metadata),self.run_id))
        self.metadata=metadata
        self.guest_profile=metadata['guest_profile']
        return result

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
        if bits not in (None,16,32,64):raise ValueError('Machine traces require observed or explicit instruction bitness')
        deadline=time.monotonic()+timeout_ms/1000;events=[];state=None
        while len(events)<count:
            before=self.registers()
            observed_bits=before.get('address_state',{}).get('code_bits')
            decode_bits=observed_bits if bits is None else bits
            if decode_bits not in (16,32,64):raise ValueError('Machine instruction width was not observed; declare bits explicitly')
            if observed_bits is not None and decode_bits!=observed_bits:
                raise ValueError('Trace bitness differs from observed machine code-segment width')
            if observed_bits is None and (before['cpu_mode']=='v86' and decode_bits!=16 or before['cpu_mode']=='real' and decode_bits!=16 or before['cpu_mode']=='long' and decode_bits!=64):
                raise ValueError('Trace bitness differs from observed machine CPU mode')
            if before['linear_pc'] is None:raise ValueError('Selected machine CPU has no established linear PC')
            pc=int(before['linear_pc'],16);data=bytes.fromhex(self.memory(pc,length=15,space='virtual')['hex'])
            instruction=Decoder(decode_bits,data,ip=pc).decode()
            if instruction.is_invalid:raise DebuggerError('Invalid machine instruction')
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:break
            state=self.step(timeout_ms=remaining)
            if state['outcome']!='step':break
            events.append(dict(address=hex(pc),bytes=data[:instruction.len].hex(),registers=before,
                               cpu_mode=before['cpu_mode'],code_bits=decode_bits,
                               phase='before',completion='confirmed native step'))
        if len(events)<count and time.monotonic()>=deadline and (state is None or state['outcome']=='step'):
            state=dict(context='machine',outcome='timeout',timed_out=True,session=dict(state='stopped',stop_reason=dict(kind='timeout',origin='trace-deadline')))
        result=dict(context='machine',events=events,complete=len(events)==count,requested_count=count,session=state,
                    semantics='completed steps on selected vCPU; QEMU default stepping masks IRQs/timers; full machine stopped between calls',
                    bits=bits,bitness_source='observed per instruction' if bits is None else 'explicit and checked against observed width')
        from .debug_semantics import normalize_trace,contract
        normalize_trace('qemu-machine',events,version=self.version['id'] if hasattr(self,'version') else None)
        result['observation_contract']=contract('qemu-machine')
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),dict(event_count=len(events),complete=result['complete'],context='machine'))

    @machine_operation
    def screenshot(self,name='machine.png',*,grid=False,grid_step=8):
        from PIL import Image
        if not self.capabilities['screenshot']:
            raise ValueError('Selected QEMU executable does not provide screendump; use a QEMU build with display-surface support')
        self._stopped()
        path=Path(self.vm.temporary.name)/'screen.ppm';path.unlink(missing_ok=True)
        self.vm.qmp.call('screendump',{'filename':str(path)})
        with Image.open(path) as image:
            output=io.BytesIO();image.save(output,format='PNG');size=image.size
        data=output.getvalue();artifact=self._artifact(name,'screenshot',data,dict(context='machine',width=size[0],height=size[1],sha256=hashlib.sha256(data).hexdigest(),capture='QEMU stored display surface'))
        return self.project.debug_grid(artifact['artifact'],name=name+'.grid.png',step=grid_step) if grid else artifact


class MachineDebugSession(MachineContext):
    """Project-bound raw boot image using the same saved-artifact interfaces."""
    backend_id='qemu-machine'

    @staticmethod
    def _admit_guest_profile(guest_profile,image):
        from .qemm_runtime import admit_qemm_profile
        from .desqview_runtime import admit_profile as admit_desqview_profile, PROFILE as DESQVIEW_PROFILE
        selected_profile = guest_profile if isinstance(guest_profile,str) else guest_profile.get('profile') if isinstance(guest_profile,dict) else None
        return (admit_desqview_profile(guest_profile,image)
                if selected_profile in ('desqview',DESQVIEW_PROFILE)
                else admit_qemm_profile(guest_profile,image))

    def __init__(self,project,executable,*,boot_image,version=None,boot_timeout_ms=30000,guest_profile=None,
                 transport='unix',firmware=None,_on_spawn=None):
        import uuid
        from .debugger import stamp
        selected=project.version(version);image=Path(boot_image).expanduser().resolve(strict=True)
        if project.meta['format']!='raw' or project.meta['arch']!='x86' or selected['parent'] is not None:
            raise ValueError('Machine boot launch requires an original unpatched raw x86 project')
        if not image.is_file() or image.stat().st_size>64*1024*1024 or file_hash(image)!=project.meta['source_sha256']:
            raise ValueError('Boot image differs from the selected raw project')
        self.guest_profile=None
        # Pin to the project's admitted source, never to a later profile read
        # of a concurrently changed file. QemuMachine checks this again while
        # making its private disk copy, including the unprofiled machine path.
        source_hash=project.meta['source_sha256']
        options=dict(boot_image_sha256=source_hash)
        if guest_profile is not None:
            self.guest_profile = self._admit_guest_profile(guest_profile,image)
            if self.guest_profile['boot_image']['sha256']!=source_hash:
                raise ValueError('Guest profile boot image differs from the admitted project source')
            options.update(cpu_model=self.guest_profile['machine']['cpu'],
                           boot_device=self.guest_profile['machine']['boot_device'])
        memory_mib=self.guest_profile['machine']['memory_mib'] if self.guest_profile else 128
        vm=QemuMachine(executable,boot_image=image,paused=True,memory_mib=memory_mib,cpus=1,timeout_ms=boot_timeout_ms,
                       transport=transport,firmware=firmware,on_spawn=_on_spawn,**options)
        super().__init__(vm)
        self.rpc=vm;vm.context=self;self.closed=False;self.version=selected;self.run_id=uuid.uuid4().hex;self.project=project
        self.capabilities['qemm_observation']=self.guest_profile is not None and self.guest_profile['memory_manager']['configured']=='qemm'
        self.capabilities['desqview_observation']=True
        self.capabilities['memory_search']='paused snapshots; explicit task identity and per-range page mappings'
        self.metadata=dict(backend=self.backend_id,source_sha256=project.meta['source_sha256'],version_sha256=selected['sha256'],
                           runtime_inputs=vm.inputs,context='machine',address_mapping='explicit physical/selected-vCPU virtual addresses',capabilities=self.capabilities)
        if self.guest_profile is not None:
            self.metadata.update(guest_profile=self.guest_profile,machine_configuration=vm.machine_configuration)
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
        selected_bits=self.project.bits if bits is None and self.guest_profile is None else bits
        return super().trace(name,count=count,timeout_ms=timeout_ms,bits=selected_bits)
    @property
    def script_operations(self):
        return {'step','run','registers','memory','memory-translation','qemm-observe','desqview-observe',
                'memory-snapshot','memory-apply','memory-rule-tick','breakpoint','delete-breakpoint','trace','screenshot',
                'assert','status','write-memory','write-registers'}
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
