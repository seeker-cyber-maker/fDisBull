"""Bounded QMP control for one owned offline VM; snapshots use native migration."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import socket
import threading
import time

from .dosbox_rpc import DebuggerError


class QemuControl:
    def __init__(self,path,process,deadline,*,channel=None):
        self.socket=channel if channel is not None else socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.buffer=bytearray();self.sequence=0;self.lock=threading.Lock()
        self.operation_deadline=deadline
        try:
            if channel is None:
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('QMP initialization deadline expired')
                    self.socket.settimeout(remaining)
                    try:self.socket.connect(str(path));break
                    except (FileNotFoundError,ConnectionRefusedError):
                        if process.poll() is not None or time.monotonic()>=deadline:raise DebuggerError('QMP socket did not open')
                        time.sleep(min(.05,max(0,deadline-time.monotonic())))
            self.greeting=self._read(deadline)
            if 'QMP' not in self.greeting:raise DebuggerError('Invalid QMP greeting')
            self.call('qmp_capabilities',timeout_ms=max(1,int((deadline-time.monotonic())*1000)))
            self.operation_deadline=None
        except BaseException:
            self.close();raise

    def _read(self,deadline,max_reply_bytes=8*1024*1024):
        if time.monotonic()>=deadline:raise TimeoutError('QMP deadline expired')
        while b'\n' not in self.buffer:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('QMP deadline expired')
            self.socket.settimeout(remaining)
            chunk=self.socket.recv(65536)
            if not chunk:raise DebuggerError('QMP channel closed')
            self.buffer.extend(chunk)
            first_newline=self.buffer.find(b'\n')
            if (first_newline if first_newline>=0 else len(self.buffer))>max_reply_bytes:
                raise DebuggerError('QMP reply exceeds budget')
        line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
        if len(line)>max_reply_bytes:raise DebuggerError('QMP reply exceeds budget')
        value=json.loads(line)
        if not isinstance(value,dict):raise DebuggerError('Invalid QMP reply')
        return value

    def call(self,method,arguments=None,timeout_ms=30000,*,max_reply_bytes=8*1024*1024):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('QMP timeout must be 1..600000 ms')
        if type(max_reply_bytes) is not int or not 1<=max_reply_bytes<=64*1024*1024:raise ValueError('QMP reply budget must be 1..67108864 bytes')
        deadline=time.monotonic()+timeout_ms/1000
        shared=getattr(self,'operation_deadline',None)
        if shared is not None:deadline=min(deadline,shared)
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('QMP operation deadline expired before dispatch')
        if not self.lock.acquire(timeout=remaining):raise TimeoutError('QMP is busy')
        dispatched=False;completed=False
        try:
            self.sequence+=1;request={'execute':method,'id':self.sequence}
            if arguments is not None:request['arguments']=arguments
            wire=json.dumps(request,separators=(',',':')).encode()+b'\n'
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('QMP operation deadline expired before dispatch')
            self.socket.settimeout(remaining)
            dispatched=True
            self.socket.sendall(wire)
            while True:
                reply=self._read(deadline,max_reply_bytes)
                if 'event' in reply:continue
                if reply.get('id')!=self.sequence:raise DebuggerError('Wrong QMP reply identity')
                if ('error' in reply)==('return' in reply):raise DebuggerError('Invalid QMP result envelope')
                completed=True
                if 'error' in reply:raise DebuggerError('QMP '+method+': '+json.dumps(reply['error']))
                return reply['return']
        except BaseException:
            # A dispatched cont/stop/edit may already have taken effect. Close
            # an uncertain channel, allowing its machine owner to terminate;
            # never retry or consume a late response as another command's reply.
            if dispatched and not completed:self.close()
            raise
        finally:self.lock.release()

    def save(self,path,timeout_ms=240000):
        path=Path(path).resolve()
        if path.exists():raise ValueError('Snapshot output already exists')
        deadline=time.monotonic()+timeout_ms/1000
        self.call('stop')
        if self.call('query-status')['running']:raise DebuggerError('VM did not stop for checkpoint')
        self.call('migrate',{'uri':'exec:/usr/bin/gzip -1 > '+shlex.quote(str(path))})
        while True:
            status=self.call('query-migrate')
            if status.get('status')=='completed':break
            if status.get('status') in ('failed','cancelled') or time.monotonic()>=deadline:
                raise DebuggerError('Native VM checkpoint failed: '+json.dumps(status))
            if path.exists() and path.stat().st_size>2*1024**3:raise DebuggerError('Native checkpoint exceeds 2 GiB')
            time.sleep(.05)
        self.call('cont')
        return {'format':'qemu-native-migration-gzip-1','qmp_status':status}

    def restore(self,path,timeout_ms=240000):
        path=Path(path).resolve(strict=True);deadline=time.monotonic()+timeout_ms/1000
        self.call('migrate-incoming',{'uri':'exec:/usr/bin/gzip -dc '+shlex.quote(str(path))})
        while True:
            status=self.call('query-status')
            if status['status']!='inmigrate':break
            if time.monotonic()>=deadline:raise TimeoutError('Native VM restore deadline expired')
            time.sleep(.05)
        if not status['running']:self.call('cont')
        return status

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None
