"""A bounded CHIP-8 QEMU CPU session with an optional native device profile.

This is a distinct architecture adapter: no x86 HMP, PC firmware or DOS
contracts apply. The native target and ROM are pinned by SHA-256.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid

from .dosbox_rpc import DebuggerError
from .gdb_rpc import GDBRemote
from .qemu_control import QemuControl
from .debugger import stamp

BACKEND = 'qemu-chip8'
PROFILE = 'chip8-classic-pilot-default-v1'
CPU_SUBSET = 'fdisbull-chip8-cpu-smoke-1'
DEVICE_SUBSET = 'fdisbull-chip8-classic-devices-2'
ENV_MODEL = 'fdisbull-chip8-display-keypad-timers-1'
CLASSIC_SUBSET = 'fdisbull-chip8-classic-complete-3'
CLASSIC_ENV_MODEL = 'fdisbull-chip8-display-keypad-timers-rng-2'
RNG_MODEL = 'fdisbull-lcg32-high8-v1'
DEVICE_MODELS = {DEVICE_SUBSET: ENV_MODEL, CLASSIC_SUBSET: CLASSIC_ENV_MODEL}
STATE_DISK_SIZE = 1024 * 1024
RAM_SIZE = 4096
ROM_BASE = 0x200
REGISTER_NAMES = tuple('v%x' % i for i in range(16)) + ('i','pc','sp') + tuple('stack%d' % i for i in range(16))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _bounded_address(address, length):
    try:
        value = int(address,0) if isinstance(address,str) else address
    except ValueError:
        raise ValueError('Invalid CHIP-8 RAM address') from None
    if (type(value) is not int or type(length) is not int or length < 1
            or value < 0 or value + length > RAM_SIZE):
        raise ValueError('CHIP-8 RAM access must fit within 4 KiB')
    return value


def _remaining(deadline):
    value=int((deadline-time.monotonic())*1000)
    if value < 1: raise TimeoutError('CHIP-8 operation deadline expired')
    return min(value,600000)


def _fault_receipt(qmp, expected_subset=None):
    info=qmp.call('query-chip8-fault')
    if (not isinstance(info,dict) or type(info.get('faulted')) is not bool
            or info.get('profile')!=PROFILE or info.get('cpu-subset') not in (CPU_SUBSET,DEVICE_SUBSET,CLASSIC_SUBSET)
            or expected_subset is not None and info.get('cpu-subset')!=expected_subset):
        raise DebuggerError('Invalid CHIP-8 fault receipt')
    for key in ('fault-code','fault-pc','fault-opcode'):
        if type(info.get(key)) is not int or not 0<=info[key]<=0xffff:
            raise DebuggerError('Invalid CHIP-8 fault receipt')
    if (info['faulted'] and info['fault-code'] not in range(1,7)
            or not info['faulted'] and any(info[key] for key in ('fault-code','fault-pc','fault-opcode'))):
        raise DebuggerError('Inconsistent CHIP-8 fault receipt')
    return info


def _environment_receipt(qmp):
    return _validate_environment(qmp.call('query-chip8-environment'))


def _validate_environment(info):
    if (not isinstance(info,dict) or info.get('profile')!=PROFILE
            or info.get('cpu-subset') not in DEVICE_MODELS
            or info.get('env-model')!=DEVICE_MODELS.get(info.get('cpu-subset'))
            or info.get('width')!=64 or info.get('height')!=32):
        raise DebuggerError('Invalid CHIP-8 environment identity')
    for key in ('key-wait','key-wait-stop-owned','sound-active'):
        if type(info.get(key)) is not bool:raise DebuggerError('Invalid CHIP-8 environment '+key)
    limits={'key-mask':0xffff,'delay-timer':255,'sound-timer':255,'phase-numerator':59,
            **{k:(1<<64)-1 for k in ('frame-generation','virtual-ticks','manual-ticks',
                                      'virtual-now-ns','next-deadline-ns','state-generation')}}
    if info['cpu-subset']==CLASSIC_SUBSET:
        if info.get('rng-model')!=RNG_MODEL:raise DebuggerError('Invalid CHIP-8 RNG model')
        limits.update({'rng-seed':0xffffffff,'rng-state':0xffffffff,'rng-draws':(1<<64)-1})
    for key,maximum in limits.items():
        if type(info.get(key)) is not int or not 0<=info[key]<=maximum:
            raise DebuggerError('Invalid CHIP-8 environment '+key)
    if (info['sound-active']!=(info['sound-timer']>0)
            or info['key-wait-stop-owned'] and not info['key-wait']):
        raise DebuggerError('Inconsistent CHIP-8 environment state')
    encoded=info.get('pixels-hex')
    if not isinstance(encoded,str) or len(encoded)!=4096:
        raise DebuggerError('Invalid CHIP-8 framebuffer length')
    try:pixels=bytes.fromhex(encoded)
    except ValueError:raise DebuggerError('Invalid CHIP-8 framebuffer encoding') from None
    if (len(pixels)!=2048 or any(value not in (0,1) for value in pixels)
            or _sha(pixels)!=info.get('pixels-sha256')):
        raise DebuggerError('CHIP-8 framebuffer identity differs')
    return dict(info)


def _attach_native_diagnostics(error, owner):
    """Preserve bounded private stderr and exit evidence before owner cleanup."""
    try:
        details=owner.diagnostics()
    except BaseException:
        return
    existing=getattr(error,'result',None)
    if isinstance(existing,dict):
        existing.update(details)
    else:
        error.result=dict(previous=existing,**details)


class _Owner:
    def __init__(self, executable, rom_bytes, identity, *, timeout_ms=30000, checkpoint_tool=None, checkpoint_data=None, on_spawn=None):
        self.process=None;self.qmp=None;self.gdb=None;self.lock=threading.RLock();self.closed=False
        self.temporary=tempfile.TemporaryDirectory(prefix='fdisbull-chip8-')
        root=Path(self.temporary.name);self.qmp_path=root/'qmp.sock';self.gdb_path=root/'gdb.sock';self.log_path=root/'qemu.log'
        self.rom_path=root/'rom.ch8';self.rom_path.write_bytes(rom_bytes)
        if _sha(self.rom_path.read_bytes())!=identity['source_sha256']:
            self.close();raise ValueError('Private CHIP-8 ROM copy differs')
        command=[str(executable),'-machine','chip8-test','-accel','tcg','-nodefaults',
                 '-no-user-config','-nic','none','-no-reboot',
                 '-display','none','-monitor','none','-S','-kernel',str(self.rom_path),
                 '-qmp',f'unix:{self.qmp_path},server=on,wait=off',
                 '-gdb',f'unix:{self.gdb_path},server=on,wait=off']
        deadline=time.monotonic()+timeout_ms/1000
        try:
            self.checkpoint_disk=None
            if checkpoint_tool is not None:
                from .qemu_checkpoint import validate_qcow_header
                self.checkpoint_disk=root/'state.qcow2'
                if checkpoint_data is None:
                    subprocess.run([str(checkpoint_tool),'create','-f','qcow2','-o','compat=1.1,lazy_refcounts=off',
                                    str(self.checkpoint_disk),str(STATE_DISK_SIZE)],check=True,
                                   timeout=_remaining(deadline)/1000,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                else:self.checkpoint_disk.write_bytes(checkpoint_data)
                with self.checkpoint_disk.open('rb') as stream:validate_qcow_header(stream.read(104),STATE_DISK_SIZE)
                if ',' in str(self.checkpoint_disk):raise ValueError('CHIP-8 snapshot path cannot contain commas')
                command.extend(('-blockdev',f'driver=file,filename={self.checkpoint_disk},node-name=fdbfile',
                                '-blockdev','driver=qcow2,file=fdbfile,node-name=disk0,lazy-refcounts=off'))
            self.log=self.log_path.open('wb')
            self.process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=self.log)
            if on_spawn is not None:on_spawn(self.process)
            self.qmp=QemuControl(self.qmp_path,self.process,deadline)
            self.gdb=GDBRemote(self.gdb_path,self.process,deadline)
            self.qmp.operation_deadline=None;self.gdb.operation_deadline=None
            if self.gdb.architecture!='chip8':raise DebuggerError('QEMU target did not advertise CHIP-8')
            expected={**{f'v{i:x}':1 for i in range(16)},'i':2,'pc':2,'sp':1,
                      **{f'stack{i}':2 for i in range(16)}}
            actual={item['name']:item['size'] for item in self.gdb.register_description}
            if actual!=expected:raise DebuggerError('QEMU CHIP-8 register description differs from profile')
            if self.qmp.call('query-status',timeout_ms=_remaining(deadline)).get('running'):
                raise DebuggerError('CHIP-8 QEMU did not start stopped')
            self.cpu_subset=_fault_receipt(self.qmp,identity.get('cpu_subset'))['cpu-subset']
            if self.cpu_subset in DEVICE_MODELS:
                commands=self.qmp.call('query-commands',timeout_ms=_remaining(deadline))
                names={item.get('name') for item in commands if isinstance(item,dict)} if isinstance(commands,list) else set()
                if not {'query-chip8-environment','x-chip8-set-keys','x-chip8-debug-ticks'}<=names:
                    raise DebuggerError('CHIP-8 device command set is incomplete')
                if self.cpu_subset==CLASSIC_SUBSET and 'x-chip8-seed-rng' not in names:
                    raise DebuggerError('CHIP-8 RNG command is missing')
                if _environment_receipt(self.qmp)['cpu-subset']!=self.cpu_subset:
                    raise DebuggerError('CHIP-8 environment subset differs')
            self._checkpoint_restored_stopped=True
        except BaseException as error:
            _attach_native_diagnostics(error,self)
            try:self.close()
            except BaseException:pass
            raise

    def diagnostics(self):
        code=None
        if self.process is not None:
            code=self.process.poll()
            if code is None:
                try:code=self.process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:pass
        stderr=''
        if self.log_path.is_file():
            with self.log_path.open('rb') as stream:
                stream.seek(0,os.SEEK_END);size=stream.tell();stream.seek(max(0,size-16384))
                stderr=stream.read(16384).decode('utf-8','replace')
        return dict(native_exit_code=code,native_stderr=stderr)

    def close(self):
        if self.closed:return
        self.closed=True
        for channel in (self.gdb,self.qmp):
            if channel is not None:channel.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=3)
        if getattr(self,'log',None) is not None:self.log.close()
        self.temporary.cleanup()


class Chip8DebugSession:
    """One stopped-at-boundaries CHIP-8 machine bound to one immutable FDB ROM."""
    backend_id=BACKEND
    capabilities={'registers':True,'memory':True,'run':True,'step':True,'breakpoints':True,
                  'save_states':False,'frame':False,'layers':False,'hooks':False,
                  'histories':False,'trials':False,'input':False,'timers':False,
                  'code_layers':False,'rewind':False,'frame_timeline':False,
                  'selected_cpu_ram_undo':False,'comparative_trials':False}

    def __init__(self,project,executable,*,rom,version=None,timeout_ms=30000,checkpoint_tool=None,_on_spawn=None):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 startup timeout')
        deadline=time.monotonic()+timeout_ms/1000
        if checkpoint_tool is not None:
            checkpoint_tool=Path(checkpoint_tool).expanduser().resolve(strict=True)
            if not checkpoint_tool.is_file() or not os.access(checkpoint_tool,os.X_OK):
                raise ValueError('Expected an executable CHIP-8 checkpoint tool')
        selected=project.version(version)
        loader=project.meta.get('loader_metadata')
        descriptor=loader.get('chip8') if isinstance(loader,dict) else None
        if (project.meta.get('arch')!='chip8' or project.meta.get('format')!='raw'
                or project.meta.get('bits')!=16 or project.meta.get('entry')!=ROM_BASE
                or not isinstance(descriptor,dict) or loader.get('chip8_profile')!=PROFILE
                or descriptor.get('profile')!=PROFILE or descriptor.get('memory_size')!=RAM_SIZE
                or descriptor.get('rom_base')!=ROM_BASE or descriptor.get('instruction_bytes')!=2
                or loader.get('instruction_endian')!='big' or selected.get('parent') is not None):
            raise ValueError('CHIP-8 QEMU requires an original unpatched CHIP-8 raw project')
        executable=Path(executable).expanduser().resolve(strict=True)
        source=Path(rom).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable,os.X_OK) or not source.is_file():
            raise ValueError('Expected a QEMU executable and CHIP-8 ROM file')
        data=source.read_bytes()
        if not 2<=len(data)<=RAM_SIZE-ROM_BASE or _sha(data)!=project.meta['source_sha256']:
            raise ValueError('CHIP-8 ROM bytes differ from the selected project')
        version_line=subprocess.check_output([str(executable),'--version'],text=True,stderr=subprocess.STDOUT,timeout=_remaining(deadline)/1000).splitlines()[0]
        binary_sha=_file_sha(executable)
        self.identity=dict(profile=PROFILE,source_sha256=_sha(data),version_sha256=selected['sha256'],
                           cpu_subset=None,qemu_sha256=binary_sha,qemu_version=version_line,
                           checkpoint_tool_sha256=_file_sha(checkpoint_tool) if checkpoint_tool else None,
                           machine='chip8-test',memory=RAM_SIZE)
        self._rom=data;self._executable=executable;self.project=project;self.version=selected
        self._checkpoint_tool=checkpoint_tool;self.capabilities=dict(type(self).capabilities,save_states=checkpoint_tool is not None)
        self.run_id=uuid.uuid4().hex;self.closed=False;self.breakpoints={};self.next_bp=1
        self.metadata=dict(backend=BACKEND,source_sha256=self.identity['source_sha256'],
                           version_sha256=selected['sha256'],identity=self.identity,capabilities=self.capabilities)
        self.vm=_Owner(executable,data,self.identity,timeout_ms=_remaining(deadline),checkpoint_tool=checkpoint_tool,on_spawn=_on_spawn)
        self.rpc=self.vm
        try:
            self.identity['cpu_subset']=getattr(self.vm,'cpu_subset',CPU_SUBSET)
            if self.identity['cpu_subset'] in DEVICE_MODELS:
                self.identity['env_model']=DEVICE_MODELS[self.identity['cpu_subset']]
                self.capabilities.update(frame=True,input=True,timers=True,audio=False)
                if self.identity['cpu_subset']==CLASSIC_SUBSET:self.capabilities['rng']=True
            if _file_sha(executable)!=binary_sha:raise ValueError('QEMU binary changed during startup')
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,selected['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            project._live_debuggers.append(self)
        except BaseException:self.vm.close();raise

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self.closed:return
        self.closed=True
        try:
            self.vm.close()
            with self.project.transaction(True):
                self.project.db.execute('UPDATE debug_runs SET ended=?,state=? WHERE id=?',(stamp(),'exited',self.run_id))
        finally:
            if self in self.project._live_debuggers:self.project._live_debuggers.remove(self)

    def _event(self,operation,value):
        with self.project.transaction(True):
            self.project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                                    (self.run_id,stamp(),operation,json.dumps(value)))

    def _artifact(self,name,kind,data,metadata):
        return self.project._debug_artifact(self.run_id,name,kind,data,metadata)

    def _stopped(self):
        if self.closed or self.vm.process.poll() is not None:raise DebuggerError('CHIP-8 machine is closed')
        if self.vm.qmp.call('query-status').get('running') is not False:
            raise ValueError('CHIP-8 machine must be stopped')
        return self.vm.gdb

    @contextmanager
    def _budget(self,owner,deadline):
        wait=min(10,max(0,deadline-time.monotonic()))
        if not wait or not owner.lock.acquire(timeout=wait):raise TimeoutError('CHIP-8 machine is busy')
        channels=[c for c in (owner.qmp,owner.gdb) if c is not None]
        saved=[getattr(c,'operation_deadline',None) for c in channels]
        try:
            if self.vm is not owner:raise ValueError('CHIP-8 machine owner changed')
            for channel,previous in zip(channels,saved):
                channel.operation_deadline=min(deadline,previous) if previous is not None else deadline
            yield
        finally:
            for channel,previous in zip(channels,saved):channel.operation_deadline=previous
            owner.lock.release()

    def contexts(self):return dict(run=self.run_id,selected='machine',contexts=[dict(id='machine',kind='machine',capabilities=self.capabilities)])
    def context(self,name):
        if name!='machine':raise ValueError('Unknown CHIP-8 machine context')
        return self

    def status(self):
        if self.closed:return dict(context='machine',run=self.run_id,state='exited',capabilities=self.capabilities)
        with self.vm.lock:
            native=self.vm.qmp.call('query-status')
            fault=None if native.get('running') else _fault_receipt(self.vm.qmp,self.identity['cpu_subset'])
            return dict(context='machine',run=self.run_id,version=self.version['id'],
                        state='running' if native.get('running') else 'stopped',native=native,
                        fault=fault,capabilities=self.capabilities,mapping=self.metadata)

    def _require_devices(self):
        if self.identity['cpu_subset'] not in DEVICE_MODELS:
            raise ValueError('This CHIP-8 runtime has no display, keypad or timers')

    def chip8_environment(self,*,timeout_ms=10000):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 environment timeout')
        self._require_devices();deadline=time.monotonic()+timeout_ms/1000;owner=self.vm
        with self._budget(owner,deadline):
            self._stopped()
            return _environment_receipt(owner.qmp)

    def _device_mutation(self,command,arguments,expected,*,timeout_ms):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 device timeout')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 device mutation requires no caller transaction')
        self._require_devices();deadline=time.monotonic()+timeout_ms/1000;owner=self.vm
        with self._budget(owner,deadline):
            self._stopped();before=_environment_receipt(owner.qmp);registers=self.registers()
            if before['state-generation']==(1<<64)-1 or (command=='x-chip8-debug-ticks'
                    and before['manual-ticks']>(1<<64)-1-arguments['count']):
                raise ValueError('CHIP-8 device counter exhausted')
            args=dict(arguments,**{'expected-generation':before['state-generation']})
            after=None
            try:
                after=_validate_environment(owner.qmp.call(command,args,timeout_ms=_remaining(deadline)))
                observed=_environment_receipt(owner.qmp)
                actual_registers=self.registers()
                unchanged=set(before)-set(expected)-{'state-generation','key-wait-stop-owned'}
                if (after!=observed or after['state-generation']!=before['state-generation']+1
                        or after['key-wait-stop-owned'] or actual_registers!=registers
                        or any(after[k]!=before[k] for k in unchanged)
                        or any(after[k]!=(value(before) if callable(value) else value) for k,value in expected.items())):
                    raise DebuggerError('CHIP-8 device mutation readback differs')
                self._event({'x-chip8-set-keys':'chip8-keypad','x-chip8-debug-ticks':'chip8-tick',
                             'x-chip8-seed-rng':'chip8-seed-rng'}[command],
                            dict(before=before,after=after))
                _remaining(deadline)
                return after
            except BaseException as error:
                if getattr(error,'result',None) is None:
                    error.result=dict(before=before,after=after,command=command,arguments=args,
                                      disposition='device mutation uncertain; do not replay')
                _attach_native_diagnostics(error,owner)
                try:self.close()
                except BaseException:pass
                raise

    def chip8_keypad(self,keys,*,timeout_ms=10000):
        if (not isinstance(keys,(list,tuple)) or len(keys)>16
                or any(type(key) is not int or not 0<=key<=15 for key in keys)
                or len(set(keys))!=len(keys)):
            raise ValueError('CHIP-8 keys must be distinct integers from 0 to 15')
        mask=sum(1<<key for key in keys)
        return self._device_mutation('x-chip8-set-keys',{'key-mask':mask},{'key-mask':mask},timeout_ms=timeout_ms)

    def chip8_tick(self,ticks,*,timeout_ms=10000):
        if type(ticks) is not int or not 1<=ticks<=65535:raise ValueError('CHIP-8 ticks must be 1..65535')
        return self._device_mutation('x-chip8-debug-ticks',{'count':ticks},
            {'manual-ticks':lambda old:old['manual-ticks']+ticks,
             'delay-timer':lambda old:max(0,old['delay-timer']-ticks),
             'sound-timer':lambda old:max(0,old['sound-timer']-ticks),
             'sound-active':lambda old:old['sound-timer']>ticks},timeout_ms=timeout_ms)

    def chip8_seed_rng(self,seed,*,timeout_ms=10000):
        if type(seed) is not int or not 0<=seed<=0xffffffff:raise ValueError('CHIP-8 RNG seed must be a uint32')
        if self.identity['cpu_subset']!=CLASSIC_SUBSET:raise ValueError('This CHIP-8 runtime has no deterministic RNG')
        return self._device_mutation('x-chip8-seed-rng',{'seed':seed},
            {'rng-seed':seed,'rng-state':seed,'rng-draws':0},timeout_ms=timeout_ms)

    def frame_rgba(self,*,timeout_ms=10000):
        info=self.chip8_environment(timeout_ms=timeout_ms)
        indices=bytes.fromhex(info['pixels-hex'])
        rgba=b''.join(b'\xff\xff\xff\xff' if value else b'\x00\x00\x00\xff' for value in indices)
        return dict(width=64,height=32,rgba=rgba,sha256=_sha(rgba),format='rgba8888',environment=info)

    def screenshot(self,name='screenshot.png',*,encoding='png',timeout_ms=10000):
        from .external_files import _file_name
        from PIL import Image
        _file_name(name)
        if encoding!='png':raise ValueError('CHIP-8 screenshots support PNG only')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 screenshot requires no caller transaction')
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 screenshot timeout')
        self._require_devices();deadline=time.monotonic()+timeout_ms/1000;owner=self.vm
        with self._budget(owner,deadline):
            frame=self.frame_rgba(timeout_ms=_remaining(deadline))
            image=Image.frombytes('RGBA',(64,32),frame['rgba']);out=io.BytesIO();image.save(out,format='PNG')
            data=out.getvalue();metadata=dict(format='chip8-frame-png-1',width=64,height=32,
                pixel_sha256=frame['sha256'],environment=frame['environment'],identity=self.identity)
            artifact=self._artifact(name,'screenshot',data,metadata)
            if artifact.get('sha256')!=_sha(data):raise DebuggerError('CHIP-8 screenshot artifact differs')
            result=dict(**artifact,width=64,height=32,pixel_sha256=frame['sha256'],
                        format='png',environment=frame['environment'])
            try:_remaining(deadline)
            except BaseException as error:
                error.result=result
                raise
            return result

    def registers(self):
        with self.vm.lock:
            values=self._stopped().registers()
            if set(values)!=set(REGISTER_NAMES) or any(values[k] is None for k in REGISTER_NAMES):
                raise DebuggerError('CHIP-8 register reply is incomplete')
            pc=int(values['pc'],16)
            if pc>0xffff or int(values['i'],16)>0xffff or int(values['sp'],16)>16:
                raise DebuggerError('CHIP-8 register reply is out of range')
            return dict(context='machine',architecture='chip8',registers=values,
                        instruction_pointer=hex(pc),linear_pc=hex(pc),cpu_mode='chip8',
                        address_context='flat 4 KiB CHIP-8 RAM')

    def _memory(self,address,length,data=None):
        address=_bounded_address(address,length);remote=self._stopped()
        packet=max(1,(getattr(remote,'packet_size',4096)-64)//2)
        if data is None:
            value=bytearray()
            for offset in range(0,length,packet):
                size=min(packet,length-offset);result=remote.request(f'm{address+offset:x},{size:x}')
                try:part=bytes.fromhex(result.decode('ascii'))
                except (ValueError,UnicodeDecodeError):raise DebuggerError('Invalid CHIP-8 GDB memory reply') from None
                if len(part)!=size:raise DebuggerError('Incomplete CHIP-8 memory reply')
                value.extend(part)
            return bytes(value)
        if len(data)!=length:raise ValueError('CHIP-8 write length differs')
        for offset in range(0,length,packet):
            part=data[offset:offset+packet]
            if remote.request(f'M{address+offset:x},{len(part):x}:{part.hex()}')!=b'OK':raise DebuggerError('CHIP-8 memory write rejected')
        return self._memory(address,length)

    def memory(self,address,*,length=16,space='physical'):
        if space not in ('physical','virtual'):raise ValueError('CHIP-8 memory space must be physical or virtual')
        value=_bounded_address(address,length)
        with self.vm.lock:data=self._memory(value,length)
        return dict(context='machine',address=hex(value),space=space,hex=data.hex(),length=len(data))

    def write_memory(self,address,data_hex,*,expected_hex,space='physical'):
        if space not in ('physical','virtual'):raise ValueError('CHIP-8 memory space must be physical or virtual')
        try:data=bytes.fromhex(data_hex);expected=bytes.fromhex(expected_hex)
        except (ValueError,TypeError):raise ValueError('Expected hexadecimal CHIP-8 bytes') from None
        value=_bounded_address(address,len(data))
        if len(data)!=len(expected):raise ValueError('CHIP-8 memory edit requires equal-length guard')
        with self.vm.lock:
            if self._memory(value,len(data))!=expected:raise DebuggerError('CHIP-8 memory guard differs')
            try:
                after=self._memory(value,len(data),data)
                if after!=data:raise DebuggerError('CHIP-8 memory readback differs')
            except BaseException as error:
                if getattr(error,'result',None) is None:
                    error.result=dict(address=hex(value),before_hex=expected.hex(),
                                      attempted_hex=data.hex(),disposition='write outcome uncertain; do not replay')
                try:self.close()
                except BaseException:pass
                raise
        return dict(context='machine',address=hex(value),space=space,before_hex=expected.hex(),after_hex=after.hex())

    def write_registers(self,registers):
        if not isinstance(registers,dict) or not registers:raise ValueError('Expected guarded CHIP-8 register edits')
        with self.vm.lock:
            remote=self._stopped();before=remote.registers();edits={}
            if before.get('sp') is None:raise DebuggerError('CHIP-8 stack depth is unavailable')
            for name,item in registers.items():
                if name not in REGISTER_NAMES or not isinstance(item,dict) or set(item)!={'expected','value'}:
                    raise ValueError('Invalid guarded CHIP-8 register edit')
                try:
                    expected=int(item['expected'],0) if isinstance(item['expected'],str) else item['expected']
                    value=int(item['value'],0) if isinstance(item['value'],str) else item['value']
                except ValueError:raise ValueError('Invalid CHIP-8 register value') from None
                maximum=16 if name=='sp' else 255 if name.startswith('v') else 0xffff
                if type(value) is not int or not 0<=value<=maximum or type(expected) is not int:
                    raise ValueError('Invalid CHIP-8 register value')
                if before.get(name) is None or int(before[name],16)!=expected:raise DebuggerError('CHIP-8 register guard differs')
                edits[name]=value
            final_sp=edits.get('sp',int(before['sp'],16))
            if any(name.startswith('stack') and int(name[5:])>=final_sp and value!=0
                   for name,value in edits.items()):
                raise ValueError('Inactive CHIP-8 stack entries must remain zero')
            try:
                # QEMU clears retired slots when depth decreases; establish
                # final depth before applying guarded active-stack edits.
                if 'sp' in edits:remote.set_register('sp',edits['sp'])
                for name,value in edits.items():
                    if name!='sp':remote.set_register(name,value)
                after=remote.registers()
                if any(after.get(name) is None or int(after[name],16)!=value for name,value in edits.items()):
                    raise DebuggerError('CHIP-8 register readback differs')
            except BaseException as error:
                if getattr(error,'result',None) is None:
                    error.result=dict(attempted=edits,disposition='register outcome uncertain; do not replay')
                try:self.close()
                except BaseException:pass
                raise
            return self.registers()

    def breakpoint(self,address,*,access='x',length=1):
        value=_bounded_address(address,length)
        if access!='x' or length!=1:raise ValueError('Only execution breakpoints are supported')
        with self.vm.lock:
            if value in self.breakpoints.values():raise ValueError('A CHIP-8 breakpoint already occupies this address')
            remote=self._stopped()
            try:
                if remote.request(f'Z0,{value:x},1')!=b'OK':raise DebuggerError('CHIP-8 breakpoint rejected')
                ident=self.next_bp;self.next_bp+=1;self.breakpoints[ident]=value
            except BaseException:
                try:self.close()
                except BaseException:pass
                raise
        return dict(context='machine',breakpoint_id=ident,address=hex(value),access='x',length=1)

    def delete_breakpoint(self,breakpoint_id):
        with self.vm.lock:
            address=self.breakpoints[breakpoint_id]
            remote=self._stopped()
            try:
                if remote.request(f'z0,{address:x},1')!=b'OK':raise DebuggerError('CHIP-8 breakpoint removal failed')
                del self.breakpoints[breakpoint_id]
            except BaseException:
                try:self.close()
                except BaseException:pass
                raise
        return dict(deleted=True,context='machine')

    def _execute(self,command,timeout_ms):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 execution timeout')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 execution requires no caller transaction')
        deadline=time.monotonic()+timeout_ms/1000;owner=self.vm
        with self._budget(owner,deadline):
            result=None
            try:
                before_pc=(int(self.registers()['linear_pc'],16)
                           if command=='s' and self.identity['cpu_subset'] in DEVICE_MODELS else None)
                reply,timed_out=self._stopped().execute(command,_remaining(deadline))
                if reply[:1] not in (b'T',b'S',b'W',b'X'):raise DebuggerError('Invalid CHIP-8 stop reply')
                native=reply.decode('ascii');exited=reply[:1] in (b'W',b'X')
                initial='exited' if exited else 'timeout' if timed_out else 'stopped'
                result=dict(context='machine',outcome=initial,
                            timed_out=timed_out,session=dict(state='exited' if exited else 'stopped',
                            stop_reason=dict(kind=initial,address=None,breakpoint_ids=[],native_reply=native,
                                             classification_complete=False)),registers=None)
                if timed_out:
                    result['stop']=dict(trigger='timeout',context='machine')
                    self._event('machine-step' if command=='s' else 'machine-run',result)
                    return result
                regs=None if exited else self.registers()
                fault=None if exited else _fault_receipt(self.vm.qmp,self.identity['cpu_subset'])
                environment=(_environment_receipt(self.vm.qmp)
                             if not exited and self.identity['cpu_subset'] in DEVICE_MODELS else None)
                pc=None if regs is None else int(regs['linear_pc'],16)
                sig=int(native[1:3],16);ids=[key for key,addr in self.breakpoints.items() if sig==5 and addr==pc and not (fault and fault['faulted'])]
                wait=False
                explicit_break=any(field.startswith(('swbreak:','hwbreak:','watch:','rwatch:','awatch:'))
                                   for field in native[3:].split(';'))
                if environment and environment['key-wait-stop-owned'] and not explicit_break and not fault['faulted']:
                    if sig!=5 or environment['key-mask'] or command=='s' and pc!=before_pc:
                        raise DebuggerError('CHIP-8 key-wait stop ownership differs')
                    if pc is None or pc+2>RAM_SIZE:
                        raise DebuggerError('CHIP-8 key-wait PC is outside RAM')
                    word=int.from_bytes(self._memory(pc,2),'big')
                    if word & 0xf0ff != 0xf00a:
                        raise DebuggerError('CHIP-8 key-wait PC does not contain FX0A')
                    wait=True;ids=[]
                outcome=('exited' if exited else 'timeout' if timed_out else 'exception' if fault and fault['faulted'] else 'breakpoint' if ids
                         else 'key_wait' if wait
                         else 'step' if sig==5 and command=='s' else 'stopped' if sig==2 else 'exception')
                reason=dict(kind=outcome,address=hex(pc) if pc is not None else None,breakpoint_ids=ids,native_reply=native)
                result=dict(context='machine',outcome=outcome,timed_out=timed_out,registers=regs,
                            session=dict(state='exited' if exited else 'stopped',stop_reason=reason),
                            stop=dict(trigger=outcome,context='machine'),fault=fault)
                if environment is not None:result['environment']=environment
                self._event('machine-step' if command=='s' else 'machine-run',result)
                return result
            except BaseException as error:
                if result is not None and getattr(error,'result',None) is None:error.result=result
                _attach_native_diagnostics(error,owner)
                try:self.close()
                except BaseException:pass
                raise

    def step(self,*,timeout_ms=10000):return self._execute('s',timeout_ms)
    def run(self,*,timeout_ms=10000,stop_on_hook=False):
        if stop_on_hook is not False:raise ValueError('CHIP-8 hooks are not supported')
        return self._execute('c',timeout_ms)

    def _checkpoint_admit(self):
        if self.closed or self._checkpoint_tool is None or self.vm.checkpoint_disk is None:
            raise ValueError('CHIP-8 native snapshots require a checkpoint tool')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 snapshot requires no caller transaction')
        if self.breakpoints:raise ValueError('Remove CHIP-8 breakpoints before snapshotting')
        if (_file_sha(self._executable)!=self.identity['qemu_sha256']
                or _file_sha(self._checkpoint_tool)!=self.identity['checkpoint_tool_sha256']):
            raise ValueError('CHIP-8 runtime identity changed')
        self._stopped()

    def save_state(self,name='chip8-state.qcow2',*,max_bytes=None,timeout_ms=60000):
        from .external_files import _file_name
        from .qemu_checkpoint import snapshot_job,validate_qcow_header
        _file_name(name)
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 snapshot timeout')
        if max_bytes is not None and (type(max_bytes) is not int or not 1<=max_bytes<=128*1024*1024):
            raise ValueError('Invalid CHIP-8 snapshot byte bound')
        limit=max_bytes or 128*1024*1024;deadline=time.monotonic()+timeout_ms/1000
        owner=self.vm
        with self._budget(owner,deadline):
            self._checkpoint_admit();registers=self.registers();ram=self._memory(0,RAM_SIZE);fault=_fault_receipt(self.vm.qmp,self.identity['cpu_subset'])
            environment=_environment_receipt(self.vm.qmp) if self.identity['cpu_subset'] in DEVICE_MODELS else None
            tag='fdb-'+uuid.uuid4().hex
            artifact=None
            try:
                snapshot_job(self.vm,'save',tag=tag,vmstate='disk0',devices=['disk0'],timeout_ms=_remaining(deadline))
                if environment is not None and _environment_receipt(self.vm.qmp)!=environment:
                    raise DebuggerError('CHIP-8 environment changed during checkpoint')
                path=self.vm.checkpoint_disk
                if path.stat().st_size>limit:raise ValueError('CHIP-8 snapshot exceeds byte bound')
                data=path.read_bytes();validate_qcow_header(data[:104],STATE_DISK_SIZE)
                metadata=dict(format=('fdisbull-qemu-chip8-state-3' if self.identity['cpu_subset']==CLASSIC_SUBSET else
                                      'fdisbull-qemu-chip8-state-2' if environment is not None else 'fdisbull-qemu-chip8-state-1'),tag=tag,identity=self.identity,
                              registers=registers,ram_sha256=_sha(ram),fault=fault,host_files_restored=False)
                if environment is not None:metadata['environment']=environment
                artifact=self.project._debug_artifact(self.run_id,name,'state',data,metadata)
                _remaining(deadline)
                return artifact
            except BaseException as error:
                if artifact is not None and getattr(error,'result',None) is None:error.result=artifact
                try:self.close()
                except BaseException:pass
                raise

    def load_state(self,artifact,*,timeout_ms=60000):
        from .qemu_checkpoint import snapshot_job,validate_qcow_header
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 snapshot timeout')
        deadline=time.monotonic()+timeout_ms/1000;old=self.vm
        with self._budget(old,deadline):
            self._checkpoint_admit()
            row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(artifact,)).fetchone()
            if row is None or row['kind']!='state' or row['version']!=self.version['id']:
                raise ValueError('CHIP-8 snapshot belongs to another project version')
            data=bytes(row['data']);metadata=json.loads(row['metadata'])
            expected_format=('fdisbull-qemu-chip8-state-3' if self.identity['cpu_subset']==CLASSIC_SUBSET else
                             'fdisbull-qemu-chip8-state-2' if self.identity['cpu_subset']==DEVICE_SUBSET else 'fdisbull-qemu-chip8-state-1')
            if (len(data)>128*1024*1024 or _sha(data)!=row['sha256'] or metadata.get('format')!=expected_format
                    or metadata.get('identity')!=self.identity):raise ValueError('CHIP-8 snapshot identity differs')
            if expected_format.endswith(('-2','-3')):
                saved_environment=_validate_environment(metadata.get('environment'))
            validate_qcow_header(data[:104],STATE_DISK_SIZE)
            new=None;result=None;replaced=False;closing_old=False
            try:
                new=_Owner(self._executable,self._rom,self.identity,timeout_ms=_remaining(deadline),
                           checkpoint_tool=self._checkpoint_tool,checkpoint_data=data)
                if (_file_sha(self._executable)!=self.identity['qemu_sha256'] or
                        _file_sha(self._checkpoint_tool)!=self.identity['checkpoint_tool_sha256']):
                    raise ValueError('CHIP-8 runtime changed during restore')
                new.qmp.operation_deadline=deadline;new.gdb.operation_deadline=deadline
                snapshot_job(new,'load',tag=metadata['tag'],vmstate='disk0',devices=['disk0'],timeout_ms=_remaining(deadline))
                # Observe the fresh owner without touching or releasing the original VM.
                new.lock=old.lock
                self.vm=new
                try:
                    registers=self.registers();ram=self._memory(0,RAM_SIZE);fault=_fault_receipt(new.qmp,self.identity['cpu_subset'])
                    environment=_environment_receipt(new.qmp) if expected_format.endswith(('-2','-3')) else None
                finally:self.vm=old
                if registers!=metadata['registers'] or _sha(ram)!=metadata['ram_sha256'] or fault!=metadata.get('fault'):
                    raise DebuggerError('Restored CHIP-8 CPU or RAM differs')
                if environment is not None:
                    saved=dict(saved_environment);actual=dict(environment)
                    # Attribution is tied to the old debugger stop, not guest state.
                    saved.pop('key-wait-stop-owned');actual.pop('key-wait-stop-owned')
                    if saved!=actual or environment['key-wait-stop-owned']:
                        raise DebuggerError('Restored CHIP-8 environment differs')
                _remaining(deadline)
                result=dict(artifact=artifact,sha256=row['sha256'],registers=registers,
                            ram_sha256=_sha(ram),fault=fault,host_files_restored=False)
                if environment is not None:result['environment']=environment
                closing_old=True;old.close();self.vm=self.rpc=new;replaced=True
                new.qmp.operation_deadline=None;new.gdb.operation_deadline=None
                _remaining(deadline)
                return result
            except BaseException as error:
                if new is not None:
                    try:new.close()
                    except BaseException:pass
                if closing_old:
                    if getattr(error,'result',None) is None:
                        error.result=dict(restore=result,owner_replaced=replaced,
                                          disposition='owner transition uncertain; do not replay')
                    try:self.close()
                    except BaseException:pass
                raise
