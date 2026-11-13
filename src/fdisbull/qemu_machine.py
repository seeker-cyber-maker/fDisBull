"""One owned offline machine, shared by DOS, PE and boot-debugging profiles."""
from __future__ import annotations

import hashlib
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
from .qemu_clock import (MachineClockMixin, machine_clock_configuration, machine_clock_arguments,
                         validate_clock_budget, admit_virtual_clock, VIRTUAL_CLOCK_COMMANDS)
from .qemu_clock_sync import QemuClockSyncMixin
from .qemu_input import QemuPhysicalInputMixin
from .qemu_input_schedule import QemuScheduledInputMixin, INPUT_SCHEDULE_COMMANDS, INPUT_RETRACE_COMMANDS
from .qemu_keyboard_press import KEYBOARD_PRESS_COMMANDS
from .qemu_keyboard_type import KEYBOARD_TYPE_COMMANDS
from .qemu_mouse_click import MOUSE_CLICK_COMMANDS, validate_mouse_click_parameters
from .qemu_mapped_mouse import MAPPED_MOUSE_COMMANDS, validate_mapped_mouse_parameters
from .qemu_layers import LAYER_COMMANDS, QemuLayerSessionMixin
from .qemu_hooks import QemuHookSessionMixin
from .qemu_surface import QemuSurfaceMixin
from .qemu_audio import QemuAudioMixin, machine_audio_configuration, admit_audio
from .qemu_display import (QemuDisplayMixin, DISPLAY_COMMANDS, DISPLAY_PROBE_COMMANDS,
                           validate_display_probe_parameters)
from .qemu_retrace import (QemuRetraceMixin, RETRACE_COMMANDS, machine_retrace_configuration,
                           machine_retrace_arguments, admit_retrace)
from .qemu_vga_configuration import (QemuVgaConfigurationMixin, VGA_CONFIGURATION_COMMANDS,
                                    validate_vga_configuration_parameters)


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


def _tracking(session, operation, reason):
    from .debugger import _tracking_callback
    return _tracking_callback(session, operation, reason)


def _before_machine_execution(session, reason):
    parent = getattr(session, '_automatic_runtime_parent', None)
    if parent is not None:
        _tracking(parent, 'before_execution', 'parent-machine-' + reason)
    _tracking(session, 'before_execution', reason)


class _TrackingDeadline(TimeoutError):
    """No native instruction was dispatched before the tracking budget ended."""


_MAX_INTERNAL_STOPS = 256
_CONTROL_REPAIR_GRACE_MS = 1000


class QemuMachine:
    def __init__(self, executable, *, kernel=None, initramfs=None, boot_image=None,
                 paused=False, restore=False, memory_mib=4096, cpus=2, timeout_ms=240000,on_spawn=None,
                 cpu_model='max', boot_image_sha256=None, boot_device='ide', transport='unix', firmware=None,
                 clock_profile='standard', audio_profile='off', retrace_profile='standard',
                 checkpoint_tool=None, _checkpoint_image=None):
        self.process=None;self.qmp=None;self.gdb=None;self.machine_stopped=bool(paused)
        self.operation_deadline=None;self.close_observer=None
        self.transport=transport;self._channels=[];self._serial_channel=None
        self.lock=threading.RLock()
        self.temporary=tempfile.TemporaryDirectory(prefix='fdisbull-vm-')
        root=Path(self.temporary.name);self.log_path=root/'boot.log';self.gdb_path=root/'gdb.sock';self.rpc_path=root/'rpc.sock'
        try:
            if on_spawn is not None and not callable(on_spawn):raise ValueError('Expected an internal process ownership callback')
            if transport not in ('unix','pipe'):raise ValueError('QEMU transport must be unix or pipe')
            if transport=='pipe' and os.name!='posix':raise ValueError('QEMU pipe transport requires a POSIX host')
            if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine timeout must be 1..600000 ms')
            deadline=time.monotonic()+timeout_ms/1000
            def remaining():
                value=deadline-time.monotonic()
                if value<=0:raise TimeoutError('QEMU control startup deadline expired')
                return value
            if type(memory_mib) is not int or not 16<=memory_mib<=8192 or type(cpus) is not int or not 1<=cpus<=8:
                raise ValueError('Machine memory must be 16..8192 MiB and CPUs 1..8')
            selected_clock=machine_clock_configuration(clock_profile,cpus)
            selected_audio=machine_audio_configuration(audio_profile,clock_profile)
            selected_retrace=machine_retrace_configuration(retrace_profile,clock_profile)
            if retrace_profile!='standard' and (boot_image is None or not paused or restore):
                raise ValueError('Precise retrace observation requires a paused fresh PC boot machine')
            if audio_profile!='off' and (boot_image is None or not paused or restore):
                raise ValueError('Audio capture requires a paused fresh PC boot machine')
            if clock_profile=='virtual' and (not paused or restore):
                raise ValueError('The virtual clock profile requires a paused fresh machine')
            if cpu_model not in ('max', '486'):
                raise ValueError('Unsupported machine CPU profile')
            if boot_device not in ('ide', 'floppy') or boot_device == 'floppy' and boot_image is None:
                raise ValueError('Unsupported machine boot device')
            if boot_image_sha256 is not None and (boot_image is None or not isinstance(boot_image_sha256,str)
                    or re.fullmatch(r'[0-9a-f]{64}',boot_image_sha256) is None):
                raise ValueError('A pinned boot image requires its SHA-256 identity')
            if (boot_image is None)==(kernel is None) or (kernel is None)!=(initramfs is None):
                raise ValueError('Choose a boot image or a kernel/initramfs pair')
            if checkpoint_tool is not None and (boot_image is None or not paused or restore or firmware is None
                    or clock_profile not in ('standard', 'virtual')):
                raise ValueError('Checkpoint mode requires a stopped boot image, pinned firmware and standard or virtual clock')
            if _checkpoint_image is not None and checkpoint_tool is None:
                raise ValueError('Checkpoint image requires an admitted checkpoint tool')
            paths={'qemu':Path(executable).expanduser().resolve(strict=True)}
            if checkpoint_tool is not None:
                paths['checkpoint_tool']=Path(checkpoint_tool).expanduser().resolve(strict=True)
                if not os.access(paths['checkpoint_tool'],os.X_OK):raise ValueError('Checkpoint tool must be executable')
            paths.update({name:Path(path).expanduser().resolve(strict=True) for name,path in [('kernel',kernel),('initramfs',initramfs),('boot_image',boot_image)] if path is not None})
            if any(not p.is_file() for p in paths.values()) or not os.access(paths['qemu'],os.X_OK):raise ValueError('Expected regular QEMU and machine input files')
            # Cold executable startup can be slow under native/translated CI.
            version=subprocess.check_output([str(paths['qemu']),'--version'],text=True,stderr=subprocess.STDOUT,timeout=min(30,remaining())).splitlines()[0]
            match=re.search(r'QEMU emulator version (\d+)\.(\d+)',version)
            if not match or tuple(map(int,match.groups()))<(9,1):raise DebuggerError('Machine debugging requires QEMU >= 9.1')
            self.inputs={name:dict(path=str(path),sha256=file_hash(path)) for name,path in paths.items()}
            self.inputs['qemu']['version']=version
            if firmware is not None:self.inputs['firmware']=firmware_identity(firmware)
            self.machine_configuration=dict(cpu=cpu_model,memory_mib=memory_mib,cpus=cpus,network='none',accelerator='tcg',
                                            disk='private-verified-copy-and-snapshot' if boot_image else None,
                                            boot_device=boot_device if boot_image else None,control_transport=transport,
                                            clock_profile=selected_clock,
                                            audio_profile=selected_audio,
                                            retrace_profile=selected_retrace,
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
            self.checkpoint_disk=None
            if checkpoint_tool is not None:
                from .qemu_checkpoint import validate_qcow_header
                self.checkpoint_disk=root/'checkpoint.qcow2'
                self.checkpoint_virtual_size=selected_boot.stat().st_size
                if _checkpoint_image is None:
                    subprocess.run([str(paths['checkpoint_tool']),'convert','-f','raw','-O','qcow2',
                                    '-o','compat=1.1,lazy_refcounts=off',
                                    str(selected_boot),str(self.checkpoint_disk)],check=True,timeout=remaining(),
                                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                else:
                    with Path(_checkpoint_image).open('rb') as stream:
                        validate_qcow_header(stream.read(104),self.checkpoint_virtual_size)
                    shutil.copyfile(_checkpoint_image,self.checkpoint_disk)
                with self.checkpoint_disk.open('rb') as stream:
                    validate_qcow_header(stream.read(104),self.checkpoint_virtual_size)
                info=json.loads(subprocess.check_output([str(paths['checkpoint_tool']),'info','-f','qcow2','--output=json',
                                                       str(self.checkpoint_disk)],timeout=remaining()))
                if info.get('format')!='qcow2' or info.get('backing-filename') or info.get('full-backing-filename'):
                    raise ValueError('Checkpoint disk must be standalone qcow2')
                self.machine_configuration['disk']='private-standalone-qcow2'
            machine='pc' if boot_image else 'q35'
            if audio_profile=='pc-speaker':machine+=',pcspk-audiodev=fdisbull-pc'
            command=[str(paths['qemu']),*machine_clock_arguments(clock_profile),'-machine',machine,'-cpu',cpu_model,
                     '-smp',str(cpus),'-m',str(memory_mib)+'M','-nic','none','-display','none','-monitor','none','-no-reboot',
                     '-serial',f'file:{self.log_path}']
            command+=machine_retrace_arguments(retrace_profile)
            if audio_profile=='pc-speaker':
                command+=['-audiodev','none,id=fdisbull-pc,timer-period=10000,out.frequency=32000,out.channels=1,out.format=u8']
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
            if self.checkpoint_disk is not None:
                if ',' in str(self.checkpoint_disk):raise ValueError('Checkpoint image paths cannot contain commas')
                command+=['-blockdev',f'driver=file,filename={self.checkpoint_disk},node-name=fdbfile',
                          '-blockdev','driver=qcow2,file=fdbfile,node-name=disk0,lazy-refcounts=off',
                          '-device',('floppy' if boot_device=='floppy' else 'ide-hd')+',drive=disk0',
                          '-boot','order=a' if boot_device=='floppy' else 'order=c']
            elif boot_image:
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
            remaining()
            with (root/'qemu.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=root,stdin=subprocess.PIPE if transport=='pipe' else subprocess.DEVNULL,
                                              stdout=subprocess.PIPE if transport=='pipe' else log,stderr=log,bufsize=0,env=environment)
            if on_spawn is not None:on_spawn(self.process)
            if transport=='pipe':
                channel=PipeChannel(self.process.stdout,self.process.stdin,process=self.process);self._channels.append(channel)
                self.qmp=QemuControl(None,self.process,deadline,channel=channel)
            else:
                self.qmp=QemuControl(root/'qmp.sock',self.process,deadline)
            self.qmp.operation_deadline=deadline
            self.qmp_commands=frozenset(item['name'] for item in self.qmp.call('query-commands',timeout_ms=max(1,int(remaining()*1000))))
            if checkpoint_tool is not None and clock_profile == 'virtual':
                from .qemu_instrumented_checkpoint import require_commands
                require_commands(self)
            if clock_profile=='virtual':
                self.machine_configuration['native_clock_admission']=admit_virtual_clock(self)
            if audio_profile=='pc-speaker':
                self.machine_configuration['native_audio_admission']=admit_audio(self)
            if retrace_profile=='precise':
                self.machine_configuration['native_retrace_admission']=admit_retrace(self)
            self.qmp.operation_deadline=None
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
                try:
                    stream.connect(str(self.rpc_path));self._channels.append(stream);return stream
                except (FileNotFoundError,ConnectionRefusedError):
                    if self.process.poll() is not None or time.monotonic()>=deadline:raise DebuggerError('QEMU serial channel did not open')
                    time.sleep(.02)
        except BaseException:stream.close();raise

    def debugger(self):
        if self.gdb is None:
            from .gdb_rpc import GDBRemote
            deadline=time.monotonic()+10
            if self.operation_deadline is not None:deadline=min(deadline,self.operation_deadline)
            if time.monotonic()>=deadline:raise TimeoutError('QEMU debugger startup deadline expired')
            if self.transport=='pipe':
                channel=open_fifo_pair(self.gdb_path,self.process);self._channels.append(channel)
                self.gdb=GDBRemote(None,self.process,deadline,channel=channel)
            else:self.gdb=GDBRemote(self.gdb_path,self.process,deadline)
            self.gdb.operation_deadline=self.operation_deadline
        return self.gdb

    def close(self):
        try:
            context=getattr(self,'context',None)
            invalidate=getattr(context,'_input_on_close',None)
            if invalidate is not None:invalidate()
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
        finally:
            observer=self.close_observer
            self.close_observer=None
            if observer is not None:
                try:observer()
                except Exception as error:self.close_observer_error=type(error).__name__


def _machine_operation_guard(vm, name, args=(), kwargs=None):
    """Keep legacy guards and parameter-aware history fences independent."""
    if name not in ('close','dos_process_info','tracking_status') and getattr(vm,'_fdisbull_control_quarantine',None):
        raise DebuggerError('Machine controls are quarantined after '+vm._fdisbull_control_quarantine)
    guard = getattr(vm, 'operation_guard', None)
    if guard is not None:
        guard(name)
    history = getattr(vm, 'history_operation_guard', None)
    if history is not None:
        history(name, args, kwargs or {})


def machine_operation(function,*,script_budget=False):
    @wraps(function)
    def invoke(self,*args,**kwargs):
        limit=getattr(self,'_rpc_deadline',None) if script_budget else None
        wait=10 if limit is None else min(10,limit-time.monotonic())
        if wait<=0:raise TimeoutError('Native machine I/O script deadline expired before admission')
        if not self.vm.lock.acquire(timeout=wait):raise TimeoutError('Machine context is busy')
        try:
            _machine_operation_guard(self.vm, function.__name__, args, kwargs)
            return function(self,*args,**kwargs)
        except BaseException:
            gdb_failed=self.vm.gdb is not None and self.vm.gdb.socket is None
            qmp=getattr(self.vm,'qmp',None)
            qmp_failed=qmp is not None and hasattr(qmp,'socket') and qmp.socket is None
            if not getattr(self.vm,'_fdisbull_control_quarantine',None) and (gdb_failed or qmp_failed):self.vm.close()
            raise
        finally:self.vm.lock.release()
    return invoke


def machine_io_operation(function, *, close_on_timeout=False):
    """Carry a saved script's one deadline through composed native I/O.

    These operations do not continue the guest. GDB execution retains its
    separate bounded stop-recovery contract. Restoring each previous bound
    avoids leaking a finished script deadline into the next caller's operation.
    """
    @wraps(function)
    def invoke(self,*args,**kwargs):
        incoming=getattr(self,'_rpc_deadline',None)
        if incoming is None:return function(self,*args,**kwargs)
        if time.monotonic()>=incoming:
            raise TimeoutError('Native machine I/O script deadline expired before admission')
        vm=self.vm
        previous_vm=getattr(vm,'operation_deadline',None)
        bound=incoming if previous_vm is None else min(incoming,previous_vm)
        previous_channels=[]
        for channel in (getattr(vm,'qmp',None),getattr(vm,'gdb',None)):
            if channel is not None:
                previous=getattr(channel,'operation_deadline',None)
                previous_channels.append((channel,previous))
                channel.operation_deadline=bound if previous is None else min(bound,previous)
        vm.operation_deadline=bound
        try:
            result=function(self,*args,**kwargs)
            if time.monotonic()>=bound:
                if close_on_timeout:vm.close()
                raise TimeoutError('Native machine I/O exceeded the saved script deadline')
            return result
        finally:
            vm.operation_deadline=previous_vm
            for channel,previous in previous_channels:channel.operation_deadline=previous
            # A stopped observation may lazily initialize GDB under the bound.
            current=getattr(vm,'gdb',None)
            if current is not None and not any(current is channel for channel,_ in previous_channels):
                current.operation_deadline=previous_vm
    return machine_operation(invoke,script_budget=True)


def machine_clock_operation(function):
    """One host budget includes lock admission, native execution and cleanup.

    GDB retains its existing bounded interrupt recovery. That recovery cannot
    extend this operation's observation budget: an exhausted or uncertain
    native budget closes the machine instead of leaking a timer to a later run.
    """
    @wraps(function)
    def invoke(self,delta_ns,*,timeout_ms=1000):
        validate_clock_budget(delta_ns,timeout_ms)
        from .operation_budget import request_deadline
        bound=request_deadline(self,timeout_ms)
        vm=self.vm
        admission_limits=[bound,getattr(vm,'operation_deadline',None),
                          *[getattr(channel,'operation_deadline',None) for channel in
                            (getattr(vm,'qmp',None),getattr(vm,'gdb',None)) if channel is not None]]
        bound=min(value for value in admission_limits if value is not None)
        wait=min(10,bound-time.monotonic())
        if wait<=0:raise TimeoutError('Native clock host deadline expired before admission')
        if not vm.lock.acquire(timeout=wait):raise TimeoutError('Machine context is busy')
        previous_vm=getattr(vm,'operation_deadline',None)
        previous_channels=[]
        try:
            _machine_operation_guard(vm, function.__name__, (delta_ns,), {'timeout_ms': timeout_ms})
            for channel in (getattr(vm,'qmp',None),getattr(vm,'gdb',None)):
                if channel is not None:
                    previous_channels.append((channel,getattr(channel,'operation_deadline',None)))
            limits=[bound,previous_vm,*[previous for _,previous in previous_channels]]
            bound=min(value for value in limits if value is not None)
            if time.monotonic()>=bound:
                raise TimeoutError('Native clock host deadline expired before dispatch')
            vm.operation_deadline=bound
            for channel,_ in previous_channels:channel.operation_deadline=bound
            result=function(self,delta_ns,timeout_ms=timeout_ms)
            if time.monotonic()>=bound:
                vm.close()
                error=TimeoutError('Native clock execution exceeded its host deadline')
                error.result=result
                raise error
            return result
        except BaseException:
            channels=(getattr(vm,'qmp',None),getattr(vm,'gdb',None))
            if not getattr(vm,'_fdisbull_control_quarantine',None) and any(channel is not None and hasattr(channel,'socket') and channel.socket is None
                   for channel in channels):vm.close()
            raise
        finally:
            vm.operation_deadline=previous_vm
            for channel,previous in previous_channels:channel.operation_deadline=previous
            current=getattr(vm,'gdb',None)
            if current is not None and not any(current is channel for channel,_ in previous_channels):
                current.operation_deadline=previous_vm
            vm.lock.release()
    return invoke


def machine_run_operation(function):
    """Keep scheduled execution and its receipt within one host deadline.

    Ordinary GDB execution keeps its established timeout/interrupt recovery.
    A native input schedule also needs a bounded post-stop QMP reconciliation;
    its deadline starts before lock admission and cannot reset between reads.
    """
    @wraps(function)
    def invoke(self, *, timeout_ms=10000, stop_on_hook=False):
        from .operation_budget import request_deadline
        bound=request_deadline(self,timeout_ms)
        vm=self.vm
        limits=[bound,getattr(vm,'operation_deadline',None),
                *[getattr(channel,'operation_deadline',None) for channel in
                  (getattr(vm,'qmp',None),getattr(vm,'gdb',None)) if channel is not None]]
        bound=min(value for value in limits if value is not None)
        wait=min(10,bound-time.monotonic())
        if wait<=0:raise TimeoutError('Native run host deadline expired before admission')
        if not vm.lock.acquire(timeout=wait):raise TimeoutError('Machine context is busy')
        previous_vm=getattr(vm,'operation_deadline',None)
        previous_channels=[]
        installed=False
        try:
            _machine_operation_guard(vm, function.__name__, (),
                                     {'timeout_ms': timeout_ms, 'stop_on_hook': stop_on_hook})
            # Read ownership under the lock: another caller may have armed a
            # schedule while this request waited for admission.
            from .qemu_save_stop import safe_stop_enabled
            save_stop = safe_stop_enabled(self)
            if not self._input_schedule_bound() and not getattr(self, '_qemu_hooks', None) and not save_stop:
                return function(self,timeout_ms=timeout_ms,stop_on_hook=stop_on_hook)
            for channel in (getattr(vm,'qmp',None),getattr(vm,'gdb',None)):
                if channel is not None:
                    previous_channels.append((channel,getattr(channel,'operation_deadline',None)))
            limits=[bound,previous_vm,*[previous for _,previous in previous_channels]]
            bound=min(value for value in limits if value is not None)
            if time.monotonic()>=bound:
                raise TimeoutError('Native run host deadline expired before dispatch')
            vm.operation_deadline=bound
            for channel,_ in previous_channels:channel.operation_deadline=bound
            installed=True
            if save_stop:
                from .qemu_save_stop import SaveRunScope
                result = None
                try:
                    with SaveRunScope(self) as scope:
                        result=function(self,timeout_ms=timeout_ms,stop_on_hook=stop_on_hook)
                        result=scope.finish(result)
                except BaseException as error:
                    if result is not None and getattr(error,'result',None) is None:
                        error.result=result
                    raise
            else:
                result=function(self,timeout_ms=timeout_ms,stop_on_hook=stop_on_hook)
            if time.monotonic()>=bound:
                vm.close()
                error=TimeoutError('Scheduled or hooked native run exceeded its host deadline')
                error.result=result
                raise error
            return result
        except BaseException:
            channels=(getattr(vm,'qmp',None),getattr(vm,'gdb',None))
            if not getattr(vm,'_fdisbull_control_quarantine',None) and any(channel is not None and hasattr(channel,'socket') and channel.socket is None
                   for channel in channels):vm.close()
            raise
        finally:
            if installed:
                vm.operation_deadline=previous_vm
                for channel,previous in previous_channels:channel.operation_deadline=previous
                current=getattr(vm,'gdb',None)
                if current is not None and not any(current is channel for channel,_ in previous_channels):
                    current.operation_deadline=previous_vm
            vm.lock.release()
    return invoke


def machine_trace_operation(function, *, label='Source trace', default_timeout_ms=None,
                            parameter_validator=None):
    """Bound traces and composed timing operations from lock admission.

    Save each incoming bound separately. The DOS loader's ``_set_deadline``
    intentionally owns all channels during launch; a composed trace must not
    use it to widen an existing script, machine or transport deadline.
    """
    import inspect
    signature=inspect.signature(function)

    @wraps(function)
    def invoke(self,*args,**kwargs):
        from .operation_budget import request_deadline
        arguments=signature.bind(self,*args,**kwargs)
        arguments.apply_defaults()
        if parameter_validator is not None:
            parameter_validator(**{key:value for key,value in arguments.arguments.items() if key!='self'})
        bound=request_deadline(self,arguments.arguments.get('timeout_ms',default_timeout_ms))
        vm=self.vm
        def limits():
            return [bound,getattr(self,'_deadline',None),getattr(vm,'operation_deadline',None),
                    *[getattr(channel,'operation_deadline',None) for channel in
                      (getattr(vm,'qmp',None),getattr(vm,'gdb',None)) if channel is not None]]
        bound=min(value for value in limits() if value is not None)
        wait=min(10,bound-time.monotonic())
        if wait<=0:raise TimeoutError(label+' host deadline expired before admission')
        if not vm.lock.acquire(timeout=wait):raise TimeoutError('Machine context is busy')
        previous_session=getattr(self,'_deadline',None)
        previous_vm=getattr(vm,'operation_deadline',None)
        previous_channels=[]
        installed=False
        try:
            _machine_operation_guard(vm, function.__name__, args, kwargs)
            bound=min(value for value in limits() if value is not None)
            if time.monotonic()>=bound:
                raise TimeoutError(label+' host deadline expired before dispatch')
            for channel in (getattr(vm,'qmp',None),getattr(vm,'gdb',None)):
                if channel is not None:
                    previous_channels.append((channel,getattr(channel,'operation_deadline',None)))
                    channel.operation_deadline=bound
            self._deadline=bound
            vm.operation_deadline=bound
            installed=True
            result=function(self,*args,**kwargs)
            if time.monotonic()>=bound:
                error=TimeoutError(label+' exceeded its host deadline')
                error.result=result
                if function.__name__.startswith('clock_sync_'):
                    # The final check can expire after the method's own check.
                    # Keep a live synchronization mapping from remaining active
                    # after that failure, while retaining its observed receipt.
                    self._clock_sync_outer_expired(result,error)
                elif function.__name__ in ('input_schedule_retrace','keyboard_press','keyboard_type','mouse_button_click','mouse_move_mapped'):
                    # The passive arm may already be accepted and journaled.
                    # An expired return must not leave a usable live timer.
                    self._input_invalidate(label+' arm exceeded its host deadline; input must not be replayed')
                    vm.close()
                elif function.__name__ in ('display_probe', 'vga_configuration_observe'):
                    vm.close()
                raise error
            return result
        except BaseException:
            channels=(getattr(vm,'qmp',None),getattr(vm,'gdb',None))
            if not getattr(vm,'_fdisbull_control_quarantine',None) and any(channel is not None and hasattr(channel,'socket') and channel.socket is None
                   for channel in channels):vm.close()
            raise
        finally:
            if installed:
                self._deadline=previous_session
                vm.operation_deadline=previous_vm
                for channel,previous in previous_channels:channel.operation_deadline=previous
                current=getattr(vm,'gdb',None)
                if current is not None and not any(current is channel for channel,_ in previous_channels):
                    current.operation_deadline=previous_vm
            vm.lock.release()
    return invoke


class MachineContext(QemuPhysicalInputMixin, QemuScheduledInputMixin, MachineClockMixin, QemuClockSyncMixin,
                     QemuSurfaceMixin, QemuAudioMixin, QemuDisplayMixin, QemuRetraceMixin, QemuVgaConfigurationMixin,
                     DesqviewSessionMixin, MemoryRuleSessionMixin, MemorySearchSessionMixin):
    """A machine CPU context, never confused with a process or DOSBox CPU."""
    context_id='machine'

    # The shared machine lock covers complete queue transitions and observation
    # brackets, including callers using the raw context of another backend.
    clock_observe=machine_io_operation(MachineClockMixin.clock_observe)
    clock_advance=machine_clock_operation(MachineClockMixin.clock_advance)
    _clock_advance_with_hooks=machine_clock_operation(MachineClockMixin._clock_advance_with_hooks)
    capture_surface=machine_io_operation(QemuSurfaceMixin.capture_surface)
    audio_start=machine_io_operation(QemuAudioMixin.audio_start,close_on_timeout=True)
    audio_observe=machine_io_operation(QemuAudioMixin.audio_observe)
    audio_stop=machine_io_operation(QemuAudioMixin.audio_stop,close_on_timeout=True)
    capture_audio=machine_io_operation(QemuAudioMixin.capture_audio)
    display_start=machine_io_operation(QemuDisplayMixin.display_start,close_on_timeout=True)
    display_observe=machine_io_operation(QemuDisplayMixin.display_observe)
    display_probe=machine_trace_operation(QemuDisplayMixin.display_probe,
        label='Renderer pixel probe',default_timeout_ms=1000,
        parameter_validator=validate_display_probe_parameters)
    vga_configuration_observe=machine_trace_operation(QemuVgaConfigurationMixin.vga_configuration_observe,
        label='VGA configuration',default_timeout_ms=1000,
        parameter_validator=validate_vga_configuration_parameters)
    display_stop=machine_io_operation(QemuDisplayMixin.display_stop,close_on_timeout=True)
    capture_display=machine_io_operation(QemuDisplayMixin.capture_display)
    retrace_observe=machine_trace_operation(QemuRetraceMixin.retrace_observe,label='Retrace observation')
    retrace_wait=machine_trace_operation(QemuRetraceMixin.retrace_wait,label='Retrace wait')
    clock_sync_start=machine_trace_operation(QemuClockSyncMixin.clock_sync_start,label='Host clock synchronization')
    clock_sync_observe=machine_trace_operation(QemuClockSyncMixin.clock_sync_observe,label='Host clock synchronization')
    clock_sync_step=machine_trace_operation(QemuClockSyncMixin.clock_sync_step,label='Host clock synchronization')
    clock_sync_stop=machine_trace_operation(QemuClockSyncMixin.clock_sync_stop,label='Host clock synchronization')
    keyboard_key_down=machine_io_operation(QemuPhysicalInputMixin.keyboard_key_down)
    keyboard_key_up=machine_io_operation(QemuPhysicalInputMixin.keyboard_key_up)
    keyboard_state=machine_io_operation(QemuPhysicalInputMixin.keyboard_state)
    keyboard_press=machine_trace_operation(QemuPhysicalInputMixin.keyboard_press,
        label='Timed keyboard press',default_timeout_ms=1000)
    keyboard_type=machine_trace_operation(QemuPhysicalInputMixin.keyboard_type,
        label='Timed keyboard text',default_timeout_ms=1000)
    mouse_move_relative=machine_io_operation(QemuPhysicalInputMixin.mouse_move_relative)
    mouse_button_down=machine_io_operation(QemuPhysicalInputMixin.mouse_button_down)
    mouse_button_up=machine_io_operation(QemuPhysicalInputMixin.mouse_button_up)
    mouse_button_click=machine_trace_operation(QemuPhysicalInputMixin.mouse_button_click,
        label='Timed mouse button click',default_timeout_ms=1000,
        parameter_validator=validate_mouse_click_parameters)
    mouse_move_mapped=machine_trace_operation(QemuPhysicalInputMixin.mouse_move_mapped,
        label='Mapped mouse motion',default_timeout_ms=1000,
        parameter_validator=validate_mapped_mouse_parameters)
    input_state=machine_io_operation(QemuPhysicalInputMixin.input_state)
    input_cancel_pending=machine_io_operation(QemuPhysicalInputMixin.input_cancel_pending,close_on_timeout=True)
    input_schedule=machine_io_operation(QemuScheduledInputMixin.input_schedule,close_on_timeout=True)
    input_schedule_observe=machine_io_operation(QemuScheduledInputMixin.input_schedule_observe,close_on_timeout=True)
    input_schedule_retrace=machine_trace_operation(QemuScheduledInputMixin.input_schedule_retrace,label='Retrace input scheduling')

    def __init__(self,vm):
        self.vm=vm;self.breakpoints={};self.next_bp=1;self.project=None;self.run_id=None
        virtual=getattr(vm,'machine_configuration',{}).get('clock_profile',{}).get('profile')=='virtual'
        self.capabilities=dict(context='machine',address_spaces=['physical','virtual'],
            execution_breakpoints=True,data_watchpoints=True,register_edit=True,save_states=False,
            code_layers=(isinstance(self,QemuLayerSessionMixin)
                         and getattr(vm,'machine_configuration',{}).get('cpus')==1
                         and LAYER_COMMANDS <= getattr(vm,'qmp_commands',frozenset())),
            screenshot='screendump' in getattr(vm,'qmp_commands',()),
            surface_capture='screendump' in getattr(vm,'qmp_commands',()),
            completed_guest_frames=False,guest_time_control=False,
            audio_capture=getattr(vm,'machine_configuration',{}).get('audio_profile',{}).get('profile')=='pc-speaker',
            renderer_capture=virtual and DISPLAY_COMMANDS <= getattr(vm,'qmp_commands',frozenset()),
            renderer_probe=(virtual and DISPLAY_COMMANDS | DISPLAY_PROBE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
                            <= getattr(vm,'qmp_commands',frozenset())),
            vga_configuration=(virtual and getattr(vm,'machine_configuration',{}).get('retrace_profile',{}).get('profile')=='precise'
                and VGA_CONFIGURATION_COMMANDS | DISPLAY_COMMANDS | RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
                <= getattr(vm,'qmp_commands',frozenset())),
            retrace_observation=(virtual and getattr(vm,'machine_configuration',{}).get('retrace_profile',{}).get('profile')=='precise'
                                 and RETRACE_COMMANDS <= getattr(vm,'qmp_commands',frozenset())),
            retrace_wait=(virtual and getattr(vm,'machine_configuration',{}).get('retrace_profile',{}).get('profile')=='precise'
                          and RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS <= getattr(vm,'qmp_commands',frozenset())),
            virtual_clock_budget=virtual,
            host_clock_sync=virtual and VIRTUAL_CLOCK_COMMANDS <= getattr(vm,'qmp_commands',frozenset()),
            virtual_input_schedule=virtual and INPUT_SCHEDULE_COMMANDS <= getattr(vm,'qmp_commands',frozenset()),
            virtual_keyboard_press=(virtual and KEYBOARD_PRESS_COMMANDS | INPUT_SCHEDULE_COMMANDS
                | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'} <= getattr(vm,'qmp_commands',frozenset())),
            virtual_keyboard_type=(virtual and KEYBOARD_TYPE_COMMANDS | INPUT_SCHEDULE_COMMANDS
                | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'} <= getattr(vm,'qmp_commands',frozenset())),
            virtual_mouse_click=(virtual and MOUSE_CLICK_COMMANDS | INPUT_SCHEDULE_COMMANDS
                | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'} <= getattr(vm,'qmp_commands',frozenset())),
            mapped_mouse_motion=(virtual
                and getattr(vm,'machine_configuration',{}).get('retrace_profile',{}).get('profile')=='precise'
                and MAPPED_MOUSE_COMMANDS | INPUT_SCHEDULE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
                    | DISPLAY_COMMANDS | RETRACE_COMMANDS | VGA_CONFIGURATION_COMMANDS | {'input-send-event'}
                    <= getattr(vm,'qmp_commands',frozenset())),
            retrace_input_schedule=(virtual
                and getattr(vm,'machine_configuration',{}).get('retrace_profile',{}).get('profile')=='precise'
                and INPUT_RETRACE_COMMANDS | INPUT_SCHEDULE_COMMANDS | RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
                    <= getattr(vm,'qmp_commands',frozenset())),
            clock_observation=('native QEMU virtual nanoseconds and separate instruction count' if virtual else
                               'explicit instruction progress profile; no guest milliseconds'),
            physical_input='input-send-event' in getattr(vm,'qmp_commands',()),
            input_dispatch='one batch during owned GDB continue; guest consumption unverified',
            timed_input=False,absolute_mouse=False,
            memory_translation='observed non-PAE 386 4-KiB pages; paused machine only',
            page_backing_layers='read-only extended RAM backing selection in one stopped VM epoch',
            breakpoint_hooks=isinstance(self, QemuHookSessionMixin),
            qemm_observation=False,
            stop_scope='all machine vCPUs',threads='machine vCPUs; not operating-system threads')

    def bind(self,project,run_id):
        self.project=project;self.run_id=run_id;return self

    @machine_operation
    def status(self):
        from .debug_semantics import contract
        state=self.vm.qmp.call('query-status')
        result=dict(context='machine',state='running' if state['running'] else 'stopped',native_state=state,capabilities=self.capabilities,
                    semantics=contract('qemu-machine'))
        tracker=getattr(self,'_automatic_runtime_tracker',None)
        if tracker is not None:result['automatic_runtime_tracking']=tracker.status()
        return result

    @machine_operation
    def tracking_status(self):
        tracker=getattr(self,'_automatic_runtime_tracker',None)
        return tracker.status() if tracker is not None else dict(enabled=False,state='not-attached')

    @machine_operation
    def pause(self):
        self.vm.qmp.call('stop');self.vm.machine_stopped=True
        self.vm.debugger()
        _tracking(self,'after_stop','machine-pause')
        return self.status()

    @machine_operation
    def resume(self):
        if self._input_pending():raise ValueError('Queued physical input requires a bounded run, not resume')
        # Asynchronous execution cannot retain passive lifecycle coverage.
        # Retire only the tracker-owned controls before the existing user guard.
        _before_machine_execution(self,'machine-resume')
        if self.breakpoints:raise ValueError('Remove machine breakpoints before resuming guest services; use bounded machine run while they are active')
        if getattr(self, '_layer_exec', None) or getattr(self, '_dos_task_monitor', None):self._layer_before_execution()
        # FIFOs do not produce a new GDB connection event when a client opens
        # them again. Keep the completed protocol session alive across QMP
        # continue/stop; there is no outstanding GDB execution request here.
        if self.vm.gdb is not None and getattr(self.vm,'transport','unix')!='pipe':
            self.vm.gdb.close();self.vm.gdb=None
        self._automatic_internal_pending=None
        self.vm.qmp.call('cont');self.vm.machine_stopped=False
        return self.status()

    def _stopped(self):
        if getattr(self.vm,'_fdisbull_control_quarantine',None):
            raise DebuggerError('Machine controls are quarantined after '+self.vm._fdisbull_control_quarantine)
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
    def memory_translation(self,address,*,length=None):
        """Observe a page walk, or read one currently selected RAM backing layer."""
        from .dos_memory import translate_386_page
        if length is not None and (self.project is None or type(length) is not int or not 1<=length<=4096):
            raise ValueError('A backing layer read requires a project and a length of 1..4096')
        remote=self._stopped()
        registers=self.registers()
        if length is not None:
            ram_end=min(self.vm.machine_configuration['memory_mib']<<20,0xc0000000)
        def read_table(location,count):
            if length is not None and not (location+count<=0xa0000 or 0x100000<=location<=ram_end-count):
                raise ValueError('Page table is outside the qualified RAM range')
            return remote.memory(location,count,space='physical')
        def walk(state):
            return translate_386_page(address,state,read_table)
        result=walk(registers['address_state'])
        if length is not None:
            if (result['status']!='mapped' or result['page_size']!=4096
                    or registers['address_state'].get('machine_vcpus')!=1):
                raise ValueError('A backing layer read requires an observed single-vCPU non-PAE 4-KiB page')
            linear=int(result['linear_address'],16)
            physical=int(result['physical_address'],16)
            page_offset=linear & 4095
            backing=physical-page_offset
            if page_offset+length>4096:
                raise ValueError('A backing layer read cannot cross a page boundary')
            # The managed PC profile uses contiguous extended RAM in this
            # conservative region. Do not read firmware or device apertures.
            if backing<0x100000 or backing+4096>ram_end:
                raise ValueError('Backing layer is outside the qualified extended RAM range')
            data=remote.memory(physical,length,space='physical')
            selected=remote.memory(linear,length,space='virtual')
            after=self.registers()
            if (len(data)!=length or data!=selected or after!=registers
                    or walk(after['address_state'])!=result):
                raise ValueError('Stopped page walk and native memory read disagree; no backing layer established')
            epoch=getattr(self,'_runtime_epoch',self.run_id)
            result.update(data_hex=data.hex(),backing_layer=dict(
                id=f'{self.run_id}:{epoch}:{backing:08x}', run=self.run_id, epoch=epoch,
                linear_page=hex(linear-page_offset), physical_page=hex(backing),
                page_offset=page_offset, length=length, bytes_verified=True,
                lifetime='physical backing identity within this VM epoch; allocation lifetime unknown'))
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
        _before_machine_execution(self,'machine-write-memory')
        self._automatic_internal_pending=None
        after=remote.memory(value,len(data),space=space,data=data)
        if after!=data:self.vm.close();raise DebuggerError('Machine memory readback differs')
        _tracking(self,'after_stop','machine-write-memory')
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
            _before_machine_execution(self,'machine-write-registers')
            self._automatic_internal_pending=None
            for name,value in edits.items():remote.set_register(name,value)
            after=remote.registers()
            if any(int(after[name],16)!=value for name,value in edits.items()):raise DebuggerError('Machine register readback differs')
        except BaseException:self.vm.close();raise
        result=self.registers()
        _tracking(self,'after_stop','machine-write-registers')
        return result

    @machine_operation
    def breakpoint(self,address,*,access='x',length=1):
        value=int(address,0) if isinstance(address,str) else address
        if access not in ('x','r','w','rw') or type(length) is not int or not 1<=length<=65536 or type(value) is not int or not 0<=value<2**64:
            raise ValueError('Invalid machine breakpoint')
        if access=='x' and length!=1:raise ValueError('Machine execution breakpoint length must be one')
        remote=self._stopped();kind={'x':1,'w':2,'r':3,'rw':4}[access]
        owner='automatic-runtime-tracking' if getattr(self,'_automatic_tracking_callback_active',False) else 'user'
        aliases=[r for r in self.breakpoints.values() if (r['kind'],r['address'],r['length'])==(kind,value,length)]
        if len(self.breakpoints)>=256 or any(r.get('owner','user')==owner for r in aliases):
            raise ValueError('Duplicate machine breakpoint or breakpoint budget exceeded')
        if not aliases and remote.request(f'Z{kind},{value:x},{length:x}')!=b'OK':raise DebuggerError('Machine breakpoint rejected')
        identifier='machine-bp-'+str(self.next_bp);self.next_bp+=1
        self.breakpoints[identifier]=dict(address=value,kind=kind,length=length,access=access,owner=owner)
        return dict(context='machine',breakpoint_id=identifier,address=hex(value),access=access,length=length,
                    address_space='selected-vCPU virtual address',guest_code_modified=False,mechanism='QEMU TCG breakpoint/watchpoint')

    @machine_operation
    def delete_breakpoint(self,breakpoint_id):
        if breakpoint_id in getattr(self, '_qemu_hooks', {}) and not getattr(self, '_qemu_hook_internal_delete', False):
            raise ValueError('Hook-owned breakpoint must be removed with delete_hook')
        record=self.breakpoints[breakpoint_id];remote=self._stopped()
        aliases=[r for key,r in self.breakpoints.items() if key!=breakpoint_id and
                 (r['kind'],r['address'],r['length'])==(record['kind'],record['address'],record['length'])]
        if not aliases and remote.request(f'z{record["kind"]},{record["address"]:x},{record["length"]:x}')!=b'OK':raise DebuggerError('Machine breakpoint removal failed')
        del self.breakpoints[breakpoint_id]
        return dict(deleted=True,context='machine')

    def _execution_preflight(self,command,timeout_ms):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine timeout must be 1..600000 ms')
        if command!='c' and self._input_pending():
            raise ValueError('Queued physical input requires run() before stepping or tracing')
        if self._input_pending() and self.project is not None and self.project.db.in_transaction:
            raise ValueError('Physical input execution requires a project outside a caller-owned transaction')
        self._input_schedule_preflight()
        if getattr(self, '_layer_exec', None) or getattr(self, '_dos_task_monitor', None):self._layer_before_execution()

    def _execute_once(self,command,timeout_ms):
        self._execution_preflight(command,timeout_ms)
        remote=self._stopped();delivery=None
        scheduled=self._input_schedule_bound()
        if scheduled:
            try:reply,timed_out=remote.execute(command,timeout_ms)
            except BaseException:self.vm.close();raise
        elif self._input_pending():
            def dispatch(deadline):
                nonlocal delivery
                delivery=self._input_after_continue(deadline)
            reply,timed_out=remote.execute(command,timeout_ms,after_send=dispatch)
        else:reply,timed_out=remote.execute(command,timeout_ms)
        if reply[:1] not in (b'T',b'S',b'W',b'X'):self.vm.close();raise DebuggerError('Invalid machine stop reply')
        self.vm.machine_stopped=True;native=reply.decode('ascii')
        # Preserve the original stop even if register observation or native
        # input reconciliation fails. Classification becomes richer only when
        # the corresponding reads complete successfully.
        kind='exited' if reply[:1] in (b'W',b'X') else 'timeout' if timed_out else 'stopped'
        result=dict(context='machine',outcome=kind,timed_out=timed_out,session=dict(state='exited' if kind=='exited' else 'stopped',stop_reason=dict(kind=kind,
                    address=None,breakpoint_ids=[],native_reply=native,classification_complete=False)),registers=None)
        try:
            regs=self.registers() if reply[:1] in (b'T',b'S') else None
            pc=int(regs['linear_pc'],16) if regs and regs['linear_pc'] else None
            watch=re.search(r'(?:^|;)(watch|rwatch|awatch):([0-9a-fA-F]+)',native)
            watch_access = {'watch': 'w', 'rwatch': 'r', 'awatch': 'rw'}[watch.group(1)] if watch else None
            signal=int(native[1:3],16)
            # A native pause/virtual timer uses SIGINT; a matching PC alone cannot
            # turn that interruption into a breakpoint or a DOS parent-return trap.
            ids=[key for key,bp in self.breakpoints.items() if
                 signal==5 and bp['access']=='x' and bp['address']==pc or
                 watch and bp['access'] == watch_access
                 and bp['address'] <= int(watch.group(2), 16) < bp['address'] + bp['length']]
            kind='exited' if reply[:1] in (b'W',b'X') else 'timeout' if timed_out else 'watchpoint' if watch else 'breakpoint' if ids else 'stopped' if signal==2 else 'exception' if signal!=5 else 'step' if command=='s' else 'stopped'
            result=dict(context='machine',outcome=kind,timed_out=timed_out,session=dict(state='exited' if kind=='exited' else 'stopped',stop_reason=dict(kind=kind,
                        address=hex(pc) if pc is not None else None,breakpoint_ids=ids,native_reply=native)),registers=regs)
            if regs is not None and getattr(self, '_layer_exec', None):
                layer_state = self._layer_native_observe()
                if layer_state.get('fault'):
                    kind = 'stopped'
                    result.update(outcome=kind, layer_conflict=layer_state)
                    result['session']['stop_reason'].update(kind=kind, breakpoint_ids=[])
            from .debug_semantics import normalize_stop
            result['stop']=normalize_stop('qemu-machine',result['session']['stop_reason'],outcome=kind)
            if scheduled:delivery=self._input_schedule_after_stop()
            if delivery is not None:result['input_delivery']=delivery
        except BaseException as error:
            # Even an ordinary unscheduled step has already produced a native
            # stop. Later register reads or journal failures must not erase it.
            if getattr(error,'input_schedule_native',None) is not None:
                result['input_schedule_native']=deepcopy(error.input_schedule_native)
            if getattr(error,'input_schedule_retrace_before',None) is not None:
                result['input_schedule_retrace_before']=deepcopy(error.input_schedule_retrace_before)
            if getattr(error,'input_schedule_motion_before',None) is not None:
                result['input_schedule_motion_before']=deepcopy(error.input_schedule_motion_before)
            if getattr(error,'result',None) is None:error.result=result
            if scheduled or delivery is not None:
                self.vm.close()
            raise
        result['breakpoints']=list(result['session']['stop_reason']['breakpoint_ids'])
        return result

    def _tracking_budget_stop(self,result,reason):
        result=deepcopy(result)
        result.update(outcome='tracking-budget',timed_out=reason=='deadline')
        result['session']['stop_reason'].update(kind='tracking-budget',tracking_budget=reason)
        from .debug_semantics import normalize_stop
        result['stop']=normalize_stop('qemu-machine',result['session']['stop_reason'],outcome='tracking-budget')
        return result

    def _native_execute(self,remote,command,deadline):
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<1:raise _TrackingDeadline('Machine execution deadline reached before dispatch')
        _before_machine_execution(self,'machine-gdb-'+('step' if command=='s' else 'run'))
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<1:raise _TrackingDeadline('Machine execution deadline reached during tracking invalidation')
        try:
            return self._execute_once(command,remaining)
        except BaseException as error:
            # An arrived native stop may have escaped classification (for
            # example a register-read failure at a lifecycle hook). Preserve
            # its receipt, but never join task lifetimes across that gap.
            self._automatic_internal_pending=None
            try:_before_machine_execution(self,'machine-restore-unobserved-stop')
            except BaseException as retirement_error:
                error.tracking_retirement_error=type(retirement_error).__name__
                self.vm.close()
            raise

    def _step_over_internal(self,remote,identifiers,deadline):
        suspended=[];attempted=False;result=None;failure=None
        def remaining():
            bounds=[deadline,getattr(self,'_deadline',None),getattr(self,'_rpc_deadline',None),
                    getattr(self.vm,'operation_deadline',None),getattr(remote,'operation_deadline',None)]
            amount=int((min(v for v in bounds if v is not None)-time.monotonic())*1000)
            if amount<1:raise _TrackingDeadline('Internal breakpoint control deadline expired')
            return amount
        try:
            for identifier in identifiers:
                bp=self.breakpoints.get(identifier)
                if bp is None:continue
                key=(bp['kind'],bp['address'],bp['length'])
                if key in suspended:continue
                timeout=remaining();attempted=True
                if remote.request(f'z{bp["kind"]},{bp["address"]:x},{bp["length"]:x}',timeout_ms=timeout)!=b'OK':
                    raise DebuggerError('Internal breakpoint suspension failed')
                suspended.append(key)
            result=self._native_execute(remote,'s',deadline)
        except BaseException as error:
            failure=error
        observed=result or getattr(failure,'result',None) or (getattr(self,'_automatic_internal_pending',None) or {}).get('result')
        reason=(observed or {}).get('session',{}).get('stop_reason',{})
        known_stop=bool((failure is None or isinstance(failure,_TrackingDeadline)) and observed
                       and observed.get('session',{}).get('state')=='stopped'
                       and observed.get('registers') is not None
                       and re.match(r'^[TS][0-9a-fA-F]{2}',reason.get('native_reply',''))
                       and getattr(self.vm,'machine_stopped',False))
        repair_error=None;repair_deadline=None;restored=[]
        prior_remote_deadline=getattr(remote,'operation_deadline',None)
        had_remote_deadline=hasattr(remote,'operation_deadline')
        repair_started=None
        try:
            for kind,address,length in suspended:
                if not any((r['kind'],r['address'],r['length'])==(kind,address,length) for r in self.breakpoints.values()):continue
                if repair_deadline is None:
                    try:timeout=remaining()
                    except _TrackingDeadline:
                        if not known_stop:raise
                        # Repair only the controls removed from this known
                        # stopped interval. One grace covers every Z reply;
                        # it never permits another guest instruction or a
                        # replay after uncertain control I/O.
                        repair_started=time.monotonic()
                        repair_deadline=repair_started+_CONTROL_REPAIR_GRACE_MS/1000
                        remote.operation_deadline=repair_deadline
                        timeout=_CONTROL_REPAIR_GRACE_MS
                else:
                    timeout=int((repair_deadline-time.monotonic())*1000)
                    if timeout<1:raise _TrackingDeadline('Stopped breakpoint repair grace expired')
                if remote.request(f'Z{kind},{address:x},{length:x}',timeout_ms=timeout)!=b'OK':
                    raise DebuggerError('Internal breakpoint restoration failed')
                restored.append(dict(kind=kind,address=address,length=length))
        except BaseException as error:
            repair_error=error
        finally:
            if repair_deadline is not None:
                if had_remote_deadline:remote.operation_deadline=prior_remote_deadline
                else:del remote.operation_deadline
                if observed is not None:
                    observed['tracking_control_repair']=dict(grace_used=True,
                        budget_ms=_CONTROL_REPAIR_GRACE_MS,
                        elapsed_ms=max(0,int((time.monotonic()-repair_started)*1000)),
                        restored=restored,complete=repair_error is None,
                        scope='restore suspended native controls only; no guest execution')
        if failure is not None or repair_error is not None:
            if isinstance(failure,_TrackingDeadline) and repair_error is None:
                # No instruction was dispatched; any removed controls are now
                # repaired, so retain the pending stop for an explicit call.
                raise failure
            error=failure or DebuggerError('Internal breakpoint restoration failed; execution is quarantined')
            if isinstance(error,_TrackingDeadline) and attempted:
                error=DebuggerError('Internal breakpoint control deadline expired; execution is quarantined')
            if getattr(error,'result',None) is None:
                if observed is not None:error.result=observed
            if repair_error is not None:error.tracking_control_repair_error=type(repair_error).__name__
            if attempted:
                self.vm._fdisbull_control_quarantine='uncertain internal breakpoint controls'
                self._automatic_internal_pending=None
                try:_tracking(self,'close','machine-breakpoint-control-failed')
                except BaseException as retirement_error:
                    error.tracking_retirement_error=type(retirement_error).__name__
                try:self.vm.close()
                except BaseException as cleanup_error:
                    error.machine_cleanup_error=type(cleanup_error).__name__
            raise error
        return result

    def _execute(self,command,timeout_ms):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:
            raise ValueError('Machine timeout must be1..600000ms')
        remote=self._stopped()
        bounds=[time.monotonic()+timeout_ms/1000,getattr(self,'_deadline',None),
                getattr(self,'_rpc_deadline',None),getattr(self.vm,'operation_deadline',None),
                getattr(remote,'operation_deadline',None)]
        deadline=min(v for v in bounds if v is not None)
        count=0;result=None
        # A previous budget may have expired after observing the internal event
        # but before executing its native instruction. Never count it twice.
        pending=getattr(self,'_automatic_internal_pending',None)
        if pending:
            now=self.registers()
            if now['registers']==pending['registers'] and now['linear_pc']==pending['pc']:
                at_pc=[key for key,bp in self.breakpoints.items() if bp['access']=='x' and
                       bp['address']==int(now['linear_pc'],16)]
                try:result=self._step_over_internal(remote,at_pc,deadline)
                except _TrackingDeadline:result=self._tracking_budget_stop(pending['result'],'deadline')
                else:self._automatic_internal_pending=None
            else:self._automatic_internal_pending=None
        need_dispatch=result is None
        while True:
            if need_dispatch:
                try:result=self._native_execute(remote,command,deadline)
                except _TrackingDeadline:
                    if result is None:
                        result=dict(context='machine',outcome='timeout',timed_out=True,
                            session=dict(state='stopped',stop_reason=dict(kind='timeout',
                                origin='deadline-before-dispatch')),registers=self.registers(),breakpoints=[])
                    else:result=self._tracking_budget_stop(result,'deadline')
                    break
                need_dispatch=False
            # Every arrived result follows this path, including a result from
            # stepping the prior pending instruction or an internal step-over.
            # Public timeout precedence is unchanged. PC-derived IDs alone
            # (for example after S02) do not prove a delayed native hook trap.
            arrived=(result['outcome']=='breakpoint' or
                     result['outcome']=='timeout' and
                     result['session']['stop_reason'].get('native_reply','')[:3] in ('T05','S05'))
            tracker=getattr(self,'_automatic_runtime_tracker',None)
            internal=set(getattr(tracker,'internal_breakpoints',set()))
            matched=set(result['breakpoints'])
            owned=matched&internal if arrived else set()
            if not owned:
                if command=='c' and result['outcome']=='step':
                    need_dispatch=True;continue
                break
            # Bounded stop cleanup records this already-arrived event before
            # enforcing the running-interval deadline. Never dispatch another
            # guest instruction after expiry; retain the pending original one.
            try:
                hide=_tracking(self,'internal_stop',result)
            except BaseException as error:
                # This stop already arrived, even if its provider read or
                # lifecycle journal failed before pending state was installed.
                # Keep the native receipt and retire the uncertain owner; no
                # step-over or continue may follow this failed observation.
                prior=getattr(error,'result',None)
                if prior is not None and prior is not result:error.tracking_cause_result=prior
                error.result=result
                self._automatic_runtime_stop=result
                self._automatic_internal_pending=None
                self.vm._fdisbull_control_quarantine='failed internal stop publication'
                try:_tracking(self,'close','machine-internal-stop-publication-failed')
                except BaseException as retirement_error:
                    error.tracking_retirement_error=type(retirement_error).__name__
                try:self.vm.close()
                except BaseException as cleanup_error:
                    error.machine_cleanup_error=type(cleanup_error).__name__
                raise
            count+=1
            self._automatic_internal_pending=dict(ids=sorted(matched),
                registers=deepcopy(result['registers']['registers']),
                pc=result['registers']['linear_pc'],result=deepcopy(result))
            result['automatic_breakpoints']=sorted(owned)
            if result['timed_out']:
                result['session']['stop_reason']['automatic_tracking_budget']='deadline'
            user=matched-internal
            if user or not hide:
                if user:
                    result['breakpoints']=sorted(user)
                    result['session']['stop_reason']['breakpoint_ids']=sorted(user)
                break
            if result['timed_out']:break
            if time.monotonic()>=deadline:
                result=self._tracking_budget_stop(result,'deadline');break
            # Pause at the Nth recorded hook BEFORE stepping/resuming, so an
            # N+1th event cannot arrive and then be silently skipped next call.
            if count>=_MAX_INTERNAL_STOPS:
                result=self._tracking_budget_stop(result,'internal-event-count');break
            # One explicit step already reached this stop. Do not execute the
            # newly arrived hook's instruction merely to hide its breakpoint.
            if command=='s':break
            try:result=self._step_over_internal(remote,sorted(matched),deadline)
            except _TrackingDeadline:
                result=self._tracking_budget_stop(self._automatic_internal_pending['result'],'deadline');break
            self._automatic_internal_pending=None
        result['internal_tracking_stops']=count
        self._automatic_runtime_stop=result
        try:
            if result['outcome']=='exited':_tracking(self,'close','native-machine-exit')
            else:_tracking(self,'after_stop','machine-'+result['outcome'])
            if self.project:self._event('machine-'+('step' if command=='s' else 'run'),result)
        except BaseException as error:
            # The native interval already ended. Preserve that observation if
            # tracking or journal publication fails, and retire its uncertain
            # lifetime before closing the owner; never execute it again.
            if getattr(error,'result',None) is None:error.result=result
            self._automatic_internal_pending=None
            self.vm._fdisbull_control_quarantine='failed native stop publication'
            try:_tracking(self,'close','machine-post-stop-publication-failed')
            except BaseException as retirement_error:
                error.tracking_retirement_error=type(retirement_error).__name__
            try:self.vm.close()
            except BaseException as cleanup_error:
                error.machine_cleanup_error=type(cleanup_error).__name__
            raise
        return result

    @machine_operation
    def step(self,*,timeout_ms=10000):return self._execute('s',timeout_ms)
    @machine_run_operation
    def run(self,*,timeout_ms=10000,stop_on_hook=False):
        if type(stop_on_hook) is not bool:raise ValueError('stop_on_hook must be boolean')
        if not getattr(self, '_qemu_hooks', None):return self._execute('c',timeout_ms)
        return self._run_with_hooks(timeout_ms=timeout_ms,stop_on_hook=stop_on_hook)

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
        from .qemu_step_policy import observe_step_policy
        if self._input_pending():raise ValueError('Queued physical input requires run() before stepping or tracing')
        if type(count) is not int or not 1<=count<=10000:raise ValueError('Machine trace count must be 1..10000')
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Machine trace timeout must be 1..600000')
        if bits not in (None,16,32,64):raise ValueError('Machine traces require observed or explicit instruction bitness')
        deadline=time.monotonic()+timeout_ms/1000;events=[];state=None
        step_policy=observe_step_policy(self._stopped(),timeout_ms=min(timeout_ms,1000))
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
            pc=int(before['linear_pc'],16)
            layer_view = self.code(pc, length=15, space='linear') if getattr(self, '_layer_exec', None) else None
            data=bytes.fromhex((layer_view or self.memory(pc,length=15,space='virtual'))['hex'])
            instruction=Decoder(decode_bits,data,ip=pc).decode()
            if instruction.is_invalid:raise DebuggerError('Invalid machine instruction')
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:break
            state=self.step(timeout_ms=remaining)
            if state['outcome']!='step':break
            events.append(dict(address=hex(pc),bytes=data[:instruction.len].hex(),registers=before,
                               cpu_mode=before['cpu_mode'],code_bits=decode_bits,
                               phase='before',completion='native step stop; instruction completion unknown'))
            if getattr(self, '_layer_active', None):
                events[-1]['layer_generation'] = self._layer_generation
                events[-1]['active_layers'] = list(self._layer_active)
        if len(events)<count and time.monotonic()>=deadline and (state is None or state['outcome']=='step'):
            state=dict(context='machine',outcome='timeout',timed_out=True,session=dict(state='stopped',stop_reason=dict(kind='timeout',origin='trace-deadline')))
        result=dict(context='machine',events=events,complete=len(events)==count,requested_count=count,session=state,
                    semantics='before-step registers on selected vCPU; native stops do not certify instruction completion; full machine stopped between calls',
                    single_step_policy=step_policy,
                    bits=bits,bitness_source='observed per instruction' if bits is None else 'explicit and checked against observed width')
        from .debug_semantics import normalize_trace,contract
        normalize_trace('qemu-machine',events,version=self.version['id'] if hasattr(self,'version') else None)
        result['observation_contract']=contract('qemu-machine')
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),dict(event_count=len(events),complete=result['complete'],context='machine'))

    @machine_io_operation
    def screenshot(self,name='machine.png',*,grid=False,grid_step=8):
        from .screenshot_grid import validate_step
        if type(grid) is not bool:raise ValueError('grid must be boolean')
        if grid:validate_step(grid_step)
        artifact=self.capture_surface(name)
        return self.project.debug_grid(artifact['artifact'],name=name+'.grid.png',step=grid_step) if grid else artifact


class MachineDebugSession(QemuHookSessionMixin, QemuLayerSessionMixin, MachineContext):
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
                 transport='unix',firmware=None,clock_profile='standard',audio_profile='off',retrace_profile='standard',
                 checkpoint_tool=None,_on_spawn=None):
        import uuid
        from .debugger import stamp
        selected=project.version(version);image=Path(boot_image).expanduser().resolve(strict=True)
        machine_clock_configuration(clock_profile,1)
        machine_audio_configuration(audio_profile,clock_profile)
        machine_retrace_configuration(retrace_profile,clock_profile)
        if checkpoint_tool is not None and clock_profile != 'standard':
            raise ValueError('Instrumented process checkpoints require an original COM/MZ project; raw checkpoints require standard profiles')
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
                       transport=transport,firmware=firmware,clock_profile=clock_profile,audio_profile=audio_profile,
                       retrace_profile=retrace_profile,checkpoint_tool=checkpoint_tool,on_spawn=_on_spawn,**options)
        super().__init__(vm)
        self._checkpoint_launch=dict(executable=executable,boot_image=image,paused=True,memory_mib=memory_mib,
            cpus=1,timeout_ms=boot_timeout_ms,transport=transport,firmware=firmware,clock_profile=clock_profile,
            audio_profile=audio_profile,retrace_profile=retrace_profile,checkpoint_tool=checkpoint_tool,**options)
        self._checkpoint_epoch=0
        self.rpc=vm;vm.context=self;self.closed=False;self.version=selected;self.run_id=uuid.uuid4().hex;self.project=project
        self.capabilities['save_states']=checkpoint_tool is not None
        self.capabilities['qemm_observation']=self.guest_profile is not None and self.guest_profile['memory_manager']['configured']=='qemm'
        self.capabilities['desqview_observation']=True
        self.capabilities['memory_search']='paused snapshots; explicit task identity and per-range page mappings'
        self.metadata=dict(backend=self.backend_id,source_sha256=project.meta['source_sha256'],version_sha256=selected['sha256'],
                           runtime_inputs=vm.inputs,machine_configuration=vm.machine_configuration,
                           context='machine',address_mapping='explicit physical/selected-vCPU virtual addresses',capabilities=self.capabilities)
        if self.guest_profile is not None:
            self.metadata.update(guest_profile=self.guest_profile,machine_configuration=vm.machine_configuration)
        try:
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,selected['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            from .debugger import _attach_runtime_tracking
            _attach_runtime_tracking(self)
            vm.close_observer=self._on_tracking_machine_closed
            project._live_debuggers.append(self)
        except BaseException:
            try:_tracking(self,'close','machine-launch-failed')
            finally:vm.close()
            raise

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def _on_tracking_machine_closed(self):
        # Raw owners may close through a transport failure rather than close().
        # DOS process owners retain their separate _on_machine_closed observer.
        with self.vm.lock:
            _tracking(self,'close','native-machine-owner-closed')
    def contexts(self):return dict(run=self.run_id,selected='machine',contexts=[dict(id='machine',kind='machine',capabilities=self.capabilities)])
    def context(self,name):
        if name!='machine':raise ValueError('This session owns only the machine context')
        return self

    def _checkpoint_preflight(self):
        from .qemu_input import require_released_machine_input
        if self.closed or self.vm.checkpoint_disk is None or self._checkpoint_launch['checkpoint_tool'] is None:
            raise ValueError('Restricted native machine checkpoints are not enabled')
        if self.project.meta['format'] != 'raw' or hasattr(self, '_process'):
            raise ValueError('Source-bound DOS processes are not eligible for machine checkpoints')
        if self.vm.machine_configuration.get('clock_profile', {}).get('profile') != 'standard':
            raise ValueError('Raw machine checkpoints require standard clock profiles')
        if self.breakpoints:
            raise ValueError('Remove machine breakpoints and watchpoints before checkpointing')
        if getattr(self,'_layer_active',None):
            raise ValueError('Clear native layers before checkpointing')
        if self.project.db.in_transaction:
            raise ValueError('Checkpoint requires a project outside a caller-owned transaction')
        require_released_machine_input(self.vm)

    @machine_operation
    def save_state(self,name='checkpoint.qcow2',*,max_bytes=None):
        import uuid
        from .external_files import _file_name
        from .qemu_checkpoint import snapshot_job, validate_qcow_header
        _file_name(name)
        self._checkpoint_preflight()
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 128*1024*1024):
            raise ValueError('Checkpoint byte budget must be 1..134217728')
        limit=max_bytes or 128*1024*1024
        registers=self.registers()
        tag='fdb-'+uuid.uuid4().hex
        try:
            snapshot_job(self.vm,'save',tag=tag,vmstate='disk0',devices=['disk0'])
            path=self.vm.checkpoint_disk
            if path.stat().st_size>limit:raise ValueError('Checkpoint exceeds its byte budget')
            with path.open('rb') as stream:
                data=stream.read(limit+1)
            if len(data)>limit:raise ValueError('Checkpoint exceeds its byte budget')
            validate_qcow_header(data[:104],self.vm.checkpoint_virtual_size)
            metadata=dict(format='fdisbull-qemu-raw-qcow2-v1',tag=tag,source_sha256=self.metadata['source_sha256'],
                version_sha256=self.metadata['version_sha256'],backend=self.backend_id,
                runtime_inputs=deepcopy(self.vm.inputs),machine_configuration=deepcopy(self.vm.machine_configuration),
                guest_profile=deepcopy(self.guest_profile),registers=registers,
                checkpoint_scope='restricted raw machine; one standalone writable qcow2 disk',
                host_files_restored=False,source_binding_restored=False)
            return self._artifact(name,'state',data,metadata)
        except BaseException:
            self.close()
            raise

    def load_state(self,artifact,*,timeout_ms=60000):
        from .operation_budget import request_deadline
        deadline=request_deadline(self,timeout_ms)
        # The selected VM is replaced after cold restore. Hold and release the
        # original lock, not self.vm.lock after that replacement.
        owner=self.vm
        wait=min(10,deadline-time.monotonic())
        if wait<=0 or not owner.lock.acquire(timeout=wait):
            raise TimeoutError('Checkpoint restore deadline expired waiting for the machine')
        try:
            if self.vm is not owner:
                raise ValueError('Machine owner changed before checkpoint restore admission')
            return self._load_checkpoint_locked(artifact,deadline)
        finally:
            owner.lock.release()

    def _load_checkpoint_locked(self,artifact,deadline):
        from .qemu_checkpoint import snapshot_job
        def remaining():
            value=int((deadline-time.monotonic())*1000)
            if value<=0:raise TimeoutError('Checkpoint restore deadline expired')
            return min(600000,value)
        remaining()
        self._checkpoint_preflight()
        row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                                    (artifact,)).fetchone()
        if row is None or row['kind']!='state' or row['version']!=self.version['id']:
            raise ValueError('State must belong to the selected project version')
        metadata=json.loads(row['metadata']);data=bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Stored checkpoint hash mismatch')
        expected=dict(format='fdisbull-qemu-raw-qcow2-v1',source_sha256=self.metadata['source_sha256'],
                      version_sha256=self.metadata['version_sha256'],backend=self.backend_id,
                      runtime_inputs=self.vm.inputs,machine_configuration=self.vm.machine_configuration,
                      guest_profile=self.guest_profile)
        if any(metadata.get(key)!=value for key,value in expected.items()):
            raise ValueError('Checkpoint source or machine compatibility mismatch')
        remaining()
        old=self.vm;new=None
        try:
            with tempfile.TemporaryDirectory(prefix='fdisbull-checkpoint-') as directory:
                image=Path(directory)/'state.qcow2';image.write_bytes(data)
                launch=dict(self._checkpoint_launch,timeout_ms=remaining())
                new=QemuMachine(**launch,_checkpoint_image=image)
            remaining()
            if new.inputs != old.inputs or new.machine_configuration != old.machine_configuration:
                raise DebuggerError('Fresh checkpoint machine differs from saved identity')
            new.operation_deadline=deadline
            new.qmp.operation_deadline=deadline
            snapshot_job(new,'load',tag=metadata['tag'],vmstate='disk0',devices=['disk0'],timeout_ms=remaining())
            context=MachineContext(new)
            actual=context.registers();saved=metadata['registers']
            remaining()
            for field in ('registers','instruction_pointer','cpu_mode','address_state'):
                if actual.get(field)!=saved.get(field):
                    raise DebuggerError('Restored CPU differs from checkpoint: '+field)
            # Keep the session lock stable across the swap. A caller already
            # queued on the old owner may only see the fully installed epoch.
            new.lock=old.lock
            had_tracker=getattr(self,'_automatic_runtime_tracker',None) is not None
            _tracking(self,'close','machine-checkpoint-restore')
            old.close_observer=None
            old.close();self.vm=new;self.rpc=new;new.context=self
            new.close_observer=self._on_tracking_machine_closed
            self.breakpoints={};self.next_bp=1;self._checkpoint_epoch+=1
            # Memory snapshots, edit plans and rule contexts compare this exact
            # identity; retained artifacts remain readable historical evidence.
            import uuid
            self._runtime_epoch=uuid.uuid4().hex
            self._reset_native_layers()
            self._automatic_internal_pending=None
            if had_tracker:
                self._automatic_runtime_tracker=None
                from .debugger import _attach_runtime_tracking
                _attach_runtime_tracking(self)
            result=dict(artifact=artifact,sha256=row['sha256'],registers=actual,
                checkpoint_epoch=self._checkpoint_epoch,framebuffer='invalidated_until_recaptured',
                source_binding_restored=False,host_files_restored=False)
            remaining()
            self._event('load-state',result)
            remaining()
            new.operation_deadline=None;new.qmp.operation_deadline=None
            if new.gdb is not None:new.gdb.operation_deadline=None
            return result
        except BaseException:
            if new is not None:new.close()
            self.close()
            raise

    def save_anchor_stone(self,name='anchor-stone.qcow2',*,max_bytes=None):
        return self.save_state(name,max_bytes=max_bytes)

    def load_anchor_stone(self,artifact):
        return self.load_state(artifact)
    def trace(self,name='machine-trace.json',*,count=128,timeout_ms=10000,bits=None):
        selected_bits=self.project.bits if bits is None and self.guest_profile is None else bits
        return super().trace(name,count=count,timeout_ms=timeout_ms,bits=selected_bits)
    @property
    def script_operations(self):
        return {'step','run','registers','memory','memory-translation','qemm-observe','desqview-observe',
                'memory-snapshot','memory-apply','memory-rule-tick','memory-rule-run','breakpoint','delete-breakpoint','trace','screenshot',
                'clock-observe','clock-advance','capture-surface','keyboard.key-down','keyboard.key-up','keyboard.state','keyboard.press','keyboard.type',
                'audio-start','audio-observe','audio-stop','capture-audio',
                'display-start','display-observe','display-stop','capture-display','display-probe','vga-configuration',
                'retrace-observe',
                'retrace-wait','clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop',
                'mouse.move-relative','mouse.move-mapped','mouse.button-down','mouse.button-up','mouse.button-click','input-state','input-cancel-pending',
                'input-schedule','input-schedule-observe','input-schedule-retrace',
                'assert','status','write-memory','write-registers','hook','hooks','delete-hook'} | (
                    {'layer-stack','layer-enable','layer-patch','code','capture-code','branch','cave'}
                    if self.capabilities['code_layers'] else set())
    def script(self,*args,**kwargs):
        from .debugger import DebugSession
        return DebugSession.script(self,*args,**kwargs)
    def status(self):return dict(super().status(),run=self.run_id,version=self.version['id'],mapping=self.metadata)
    def close(self):
        if self.closed:return
        from .debugger import stamp
        try:_tracking(self,'close','machine-session-close')
        finally:
            self.vm.close();self.closed=True
            with self.project.transaction(True):
                self.project.db.execute('UPDATE debug_runs SET ended=?,state=? WHERE id=?',(stamp(),'exited',self.run_id))
            if self in self.project._live_debuggers:self.project._live_debuggers.remove(self)
