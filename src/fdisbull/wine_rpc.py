"""Owned offline QEMU VM and bounded private serial RPC for PE64 debugging."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time

from .dosbox_rpc import DebuggerError


class WineQemuRPC:
    limit = 96*1024*1024
    protocol = 'fdisbull-wine-qemu-1'
    agent_resource = 'opt/fdisbull/agent.c'

    @staticmethod
    def runtime_resources():
        from .wine_runtime import resources
        return resources()

    def __init__(self, executable, kernel, initramfs, *, boot_timeout_ms=240000, restore=None,on_spawn=None,memory_mib=4096):
        self.process = None;self.socket = None;self.sequence = 0
        self.qmp=None;self.vm=None
        self.lock = threading.Lock();self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-pe-')
        root=Path(self.temporary.name)
        self.log_path=root/'boot.log'
        try:
            from .qemu_machine import QemuMachine
            self.temporary.cleanup()
            self.vm=QemuMachine(executable,kernel=kernel,initramfs=initramfs,
                                restore=restore is not None,timeout_ms=boot_timeout_ms,on_spawn=on_spawn,memory_mib=memory_mib)
            self.process=self.vm.process;self.qmp=self.vm.qmp;self.temporary=self.vm.temporary
            self.inputs=self.vm.inputs;self.command=self.vm.command;self.log_path=self.vm.log_path
            self.lock=self.vm.lock
            deadline=time.monotonic()+boot_timeout_ms/1000
            self.socket=self.vm.serial(deadline)
            if restore is None:hello=self._read(deadline)
            else:
                self.qmp.restore(restore,timeout_ms=boot_timeout_ms)
                hello=self.call('identity',timeout_ms=30000)
            self.hello=hello
            expected=self._hash(self.runtime_resources()[self.agent_resource]) if self.agent_resource else None
            if hello.get('protocol')!=self.protocol or self.agent_resource and hello.get('agent_sha256')!=expected:
                raise DebuggerError('Wine runtime protocol/source mismatch; rebuild the runtime with this package')
            if hello.get('resources')!={name:self._hash(path) for name,path in self.runtime_resources().items()}:
                raise DebuggerError('Wine runtime resource mismatch; rebuild with the installed package')
            self.capabilities={'backend':'wine-qemu','architecture':'x86-64','execution_breakpoints':True,
                'memory_read':True,'memory_write':True,'instruction_trace':True,'screenshots':True,'mouse':True,
                'save_states':True,'code_layers':True,'data_watchpoints':True,'register_edit':True,'fast_forward':False}
            self.capabilities.update(watchpoint_access=['r','w','rw'],watchpoint_mechanism='Win32 guard pages with single-step rearming',
                execution_layer_mechanism='guarded relocated instructions; 4 KiB target buffer; host overhead',
                native_state_format='QEMU whole-VM migration; private project sidecar')
            self.capabilities.update(hello.get('capabilities',{}))
        except BaseException as error:
            diagnostics=self._diagnostics()
            self.close()
            if isinstance(error,Exception):
                raise DebuggerError(str(error)+diagnostics) from error
            raise

    @staticmethod
    def _hash(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

    @staticmethod
    def _check_version(version):
        match=re.search(r'QEMU emulator version (\d+)\.(\d+)',version)
        # Older TCG mishandles Wine's user-mode IRET when guest SMAP is enabled.
        if not match or tuple(map(int,match.groups()))<(9,1):
            raise DebuggerError('PE64 requires QEMU >= 9.1 for the TCG user-mode IRET/SMAP fix; found '+version)

    def _diagnostics(self):
        diagnostics=''
        for path in (self.log_path,self.log_path.with_name('qemu.log')):
            if path.exists():
                with path.open('rb') as stream:
                    stream.seek(max(0,path.stat().st_size-4096))
                    diagnostics+='\n'+path.name+':\n'+stream.read(4096).decode(errors='replace')
        return diagnostics

    def _read(self, deadline):
        data=bytearray()
        while b'\n' not in data:
            self.socket.settimeout(max(.001,deadline-time.monotonic()))
            if time.monotonic()>=deadline:raise TimeoutError('Wine RPC deadline expired without replay')
            chunk=self.socket.recv(min(65536,self.limit+1-len(data)))
            if not chunk:raise DebuggerError('Wine guest closed its channel')
            data.extend(chunk)
            if len(data)>self.limit:raise DebuggerError('Wine RPC response exceeds message budget')
        if data.find(b'\n')!=len(data)-1:raise DebuggerError('Unsolicited Wine RPC data')
        result=json.loads(data)
        if not isinstance(result,dict):raise DebuggerError('Invalid Wine RPC object')
        return result

    @property
    def machine(self):
        return self.vm.context

    def call(self, method, params=None, timeout_ms=30000):
        deadline=time.monotonic()+timeout_ms/1000
        if not self.lock.acquire(timeout=timeout_ms/1000):raise TimeoutError('Wine channel is busy')
        # A concurrent pause can win the lock after this call starts. Check
        # under the shared machine lock, outside transport failure cleanup.
        if self.vm is not None and self.vm.machine_stopped:
            self.lock.release()
            raise ValueError('Resume the machine context before calling the guest debugger')
        try:
            if self.socket is None:raise DebuggerError('Wine channel is closed')
            self.sequence+=1
            request={'id':self.sequence,'method':method,'params':params or {}}
            data=json.dumps(request,allow_nan=False,separators=(',',':')).encode()+b'\n'
            if len(data)>self.limit:raise ValueError('Wine request exceeds message budget')
            self.socket.settimeout(max(.001,deadline-time.monotonic()));self.socket.sendall(data)
            reply=self._read(deadline)
            if reply.get('id')!=self.sequence:raise DebuggerError('Invalid Wine response identity')
            if 'error' in reply:
                raise DebuggerError('Wine agent: '+reply['error']+'\n'+reply.get('wine_log_tail',''))
            if not isinstance(reply.get('result'),dict):raise DebuggerError('Invalid Wine result')
            return reply['result']
        except BaseException as error:
            diagnostics=self._diagnostics()
            self.close()
            if isinstance(error,Exception):
                raise DebuggerError(self.protocol+' '+method+': '+str(error)+diagnostics) from error
            raise
        finally:self.lock.release()

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None
        if self.vm is not None:
            self.vm.close();self.qmp=None;self.temporary=None
        else:
            if self.qmp is not None:self.qmp.close();self.qmp=None
            if self.temporary is not None:self.temporary.cleanup();self.temporary=None

    def capture(self,path):
        with self.lock:
            try:return self.qmp.save(path)
            except BaseException:self.close();raise
