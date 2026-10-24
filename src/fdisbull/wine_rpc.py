"""Owned offline QEMU VM and bounded private serial RPC for PE64 debugging."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time

from .dosbox_rpc import DebuggerError


class WineQemuRPC:
    limit = 96*1024*1024

    def __init__(self, executable, kernel, initramfs, *, boot_timeout_ms=240000):
        self.process = None;self.socket = None;self.sequence = 0
        self.lock = threading.Lock();self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-pe-',dir='/tmp')
        root=Path(self.temporary.name)
        self.log_path=root/'boot.log'
        try:
            paths=[Path(p).expanduser().resolve(strict=True) for p in (executable,kernel,initramfs)]
            if any(not p.is_file() for p in paths) or not os.access(paths[0],os.X_OK):
                raise ValueError('Expected QEMU executable, Linux kernel and prepared Wine runtime files')
            sock=root/'rpc.sock'
            command=[str(paths[0]),'-accel','tcg,thread=multi','-machine','q35','-cpu','max',
                '-smp','2','-m','4G','-nic','none','-display','none','-monitor','none','-no-reboot',
                '-serial',f'file:{self.log_path}','-serial',f'unix:{sock},server=on,wait=off',
                '-kernel',str(paths[1]),'-initrd',str(paths[2]),'-append',
                'console=ttyS0,115200 rdinit=/init rootfstype=ramfs loglevel=4 panic=1 random.trust_cpu=on']
            self.inputs={name:dict(path=str(p),sha256=self._hash(p)) for name,p in zip(('qemu','kernel','initramfs'),paths)}
            self.command=command
            with (root/'qemu.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            deadline=time.monotonic()+boot_timeout_ms/1000
            self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            while True:
                try:self.socket.connect(str(sock));break
                except (FileNotFoundError,ConnectionRefusedError):
                    if self.process.poll() is not None or time.monotonic()>=deadline:
                        raise DebuggerError('QEMU failed before its serial channel opened')
                    time.sleep(.05)
            hello=self._read(deadline)
            self.hello=hello
            expected=self._hash(Path(__file__).with_name('wine_guest')/'agent.c')
            if hello.get('protocol')!='fdisbull-wine-qemu-1' or hello.get('agent_sha256')!=expected:
                raise DebuggerError('Wine runtime protocol/source mismatch; rebuild the runtime with this package')
            from .wine_runtime import resources
            if hello.get('resources')!={name:self._hash(path) for name,path in resources().items()}:
                raise DebuggerError('Wine runtime resource mismatch; rebuild with the installed package')
            self.capabilities={'backend':'wine-qemu','architecture':'x86-64','execution_breakpoints':True,
                'memory_read':True,'memory_write':True,'instruction_trace':True,'screenshots':True,'mouse':True,
                'save_states':False,'code_layers':False,'data_watchpoints':False,'fast_forward':False}
        except BaseException as error:
            diagnostics=self._diagnostics()
            self.close()
            if isinstance(error,Exception):
                raise DebuggerError(str(error)+diagnostics) from error
            raise

    @staticmethod
    def _hash(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

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

    def call(self, method, params=None, timeout_ms=30000):
        deadline=time.monotonic()+timeout_ms/1000
        if not self.lock.acquire(timeout=timeout_ms/1000):raise TimeoutError('Wine channel is busy')
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
                raise DebuggerError(str(error)+diagnostics) from error
            raise
        finally:self.lock.release()

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        if self.temporary is not None:self.temporary.cleanup();self.temporary=None
