"""Bounded GDB remote protocol for an owned QEMU system-emulation socket."""
from __future__ import annotations

import socket
import threading
import time
import xml.etree.ElementTree as ET

from .dosbox_rpc import DebuggerError


class GDBRemote:
    limit = 8*1024*1024

    def __init__(self, path, process, deadline):
        self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.lock=threading.RLock();self.console=[];self.register_description=[];self._buffer=b'';self._cursor=0
        try:
            while True:
                try:self.socket.connect(str(path));break
                except (FileNotFoundError,ConnectionRefusedError):
                    if process.poll() is not None or time.monotonic()>=deadline:
                        raise DebuggerError('QEMU GDB socket did not open')
                    time.sleep(.02)
            self.features=self.request('qSupported:qXfer:features:read+;multiprocess+').decode('ascii')
            self._load_registers()
        except BaseException:
            self.close();raise

    def _byte(self,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('GDB response deadline expired')
        self.socket.settimeout(remaining)
        if self._cursor==len(self._buffer):
            self._buffer=self.socket.recv(65536);self._cursor=0
            if not self._buffer:raise DebuggerError('QEMU GDB channel closed')
        value=self._buffer[self._cursor];self._cursor+=1
        return value

    def _packet(self,deadline):
        while True:
            first=self._byte(deadline)
            if first==ord('+'):continue
            if first==ord('-'):raise DebuggerError('GDB rejected packet; request not replayed')
            if first!=ord('$'):raise DebuggerError('Invalid GDB packet prefix')
            raw=bytearray()
            while True:
                value=self._byte(deadline)
                if value==ord('#'):break
                raw.append(value)
                if len(raw)>self.limit:raise DebuggerError('GDB packet exceeds budget')
            try:checksum=int(bytes([self._byte(deadline),self._byte(deadline)]),16)
            except ValueError as error:raise DebuggerError('Invalid GDB checksum') from error
            if sum(raw)%256!=checksum:raise DebuggerError('GDB checksum mismatch; request not replayed')
            self.socket.sendall(b'+')
            result=bytearray();i=0
            while i<len(raw):
                value=raw[i];i+=1
                if value==ord('}'):
                    if i==len(raw):raise DebuggerError('Truncated GDB escape')
                    result.append(raw[i]^0x20);i+=1
                elif value==ord('*'):
                    if not result or i==len(raw) or not 3<=raw[i]-29<=97:
                        raise DebuggerError('Invalid GDB run-length encoding')
                    result.extend(result[-1:]*(raw[i]-29));i+=1
                else:result.append(value)
                if len(result)>self.limit:raise DebuggerError('Expanded GDB packet exceeds budget')
            if result.startswith(b'O') and result!=b'OK':
                try:message=bytes.fromhex(result[1:].decode('ascii'))
                except ValueError as error:raise DebuggerError('Invalid GDB console response') from error
                self.console.append(message.decode(errors='replace'));self.console[:]=self.console[-32:]
                continue
            return bytes(result)

    def _send(self,command,deadline):
        raw=command.encode('ascii') if isinstance(command,str) else command
        if len(raw)>self.limit:raise ValueError('GDB request exceeds budget')
        encoded=bytearray()
        for value in raw:
            if value in b'$#}*':encoded.extend((ord('}'),value^0x20))
            else:encoded.append(value)
        self.socket.settimeout(max(.001,deadline-time.monotonic()))
        self.socket.sendall(b'$'+encoded+b'#'+f'{sum(encoded)%256:02x}'.encode())

    def request(self,command,timeout_ms=10000):
        deadline=time.monotonic()+timeout_ms/1000
        with self.lock:
            try:
                self._send(command,deadline);reply=self._packet(deadline)
                if reply.startswith(b'E'):raise DebuggerError('QEMU GDB operation failed: '+reply.decode(errors='replace'))
                return reply
            except BaseException:self.close();raise

    def execute(self,command,timeout_ms,*,on_continue=None):
        """Continue/step once; interrupt on expiry without replaying execution."""
        if on_continue is not None and not callable(on_continue):
            raise ValueError('Continue observer must be callable')
        deadline=time.monotonic()+timeout_ms/1000
        with self.lock:
            try:
                self._send(command,deadline)
                if on_continue is not None:
                    try:
                        on_continue(deadline)
                    except BaseException as error:
                        # Continue has already been sent. Stop if possible and
                        # quarantine the channel; never resend the instruction.
                        try:
                            self.socket.sendall(b'\x03')
                            self._packet(time.monotonic()+5)
                        except BaseException:
                            pass
                        self.close()
                        if isinstance(error,Exception):
                            raise DebuggerError('Continue observer failed after dispatch; guest stopped or channel quarantined; do not replay: '+str(error)) from error
                        raise
                try:return self._packet(deadline),False
                except (TimeoutError,socket.timeout):
                    self.socket.sendall(b'\x03')
                    return self._packet(time.monotonic()+5),True
            except BaseException:self.close();raise

    def _xml(self,name):
        data=bytearray()
        for _ in range(1024):
            part=self.request(f'qXfer:features:read:{name}:{len(data):x},1000')
            if not part or part[:1] not in (b'm',b'l'):raise DebuggerError('Missing GDB register XML')
            data.extend(part[1:])
            if len(data)>1024*1024:raise DebuggerError('GDB register XML exceeds budget')
            if part[:1]==b'l':
                # QEMU emits GDB's abbreviated xi:include form without an XML
                # namespace declaration. No external DTD/entity is fetched.
                return ET.fromstring(bytes(data).replace(b'xi:include',b'include'))
        raise DebuggerError('GDB register XML pagination exceeded budget')

    def _load_registers(self):
        visited=set();next_number=0
        def visit(name):
            nonlocal next_number
            if name in visited or len(visited)>=32 or '/' in name or '..' in name:
                raise DebuggerError('Invalid or recursive GDB register include')
            visited.add(name);root=self._xml(name)
            def walk(item):
                nonlocal next_number
                tag=item.tag.rsplit('}',1)[-1]
                if tag=='include':visit(item.attrib['href'])
                elif tag=='architecture':self.architecture=item.text
                elif tag=='reg':
                    number=int(item.get('regnum',str(next_number)));bits=int(item.attrib['bitsize'])
                    if not 0<=number<1024 or not 0<bits<=4096 or bits%8:
                        raise DebuggerError('Invalid GDB register description')
                    self.register_description.append(dict(name=item.attrib['name'],number=number,size=bits//8))
                    next_number=number+1
                else:
                    for child in item:walk(child)
            walk(root)
        visit('target.xml')
        if not self.register_description or len({r['name'] for r in self.register_description})!=len(self.register_description):
            raise DebuggerError('Missing or duplicate GDB registers')

    def registers(self):
        raw=self.request('g')
        expected=sum(r['size'] for r in self.register_description)*2
        if len(raw)!=expected:raise DebuggerError('GDB register payload differs from XML layout')
        result={};offset=0
        for item in self.register_description:
            value=raw[offset:offset+item['size']*2];offset+=item['size']*2
            result[item['name']]=None if b'x' in value else hex(int.from_bytes(bytes.fromhex(value.decode()),'little'))
        return result

    def set_register(self,name,value):
        item=next((r for r in self.register_description if r['name']==name),None)
        if item is None or type(value) is not int or not 0<=value<1<<(item['size']*8):
            raise ValueError('Invalid machine register edit')
        data=value.to_bytes(item['size'],'little').hex()
        if self.request(f'P{item["number"]:x}={data}')!=b'OK':raise DebuggerError('GDB register edit rejected')

    def memory(self,address,length,*,space='physical',data=None):
        if space not in ('physical','virtual') or type(address) is not int or not 0<=address<2**64 or type(length) is not int or not 1<=length<=65536 or address+length>2**64:
            raise ValueError('Invalid machine memory address, length or space')
        with self.lock:
            original=self.request('qqemu.PhyMemMode')
            if original not in (b'0',b'1'):raise DebuggerError('QEMU physical-memory mode unavailable')
            mode=b'1' if space=='physical' else b'0'
            try:
                if original!=mode and self.request(b'Qqemu.PhyMemMode:'+mode)!=b'OK':raise DebuggerError('Could not select memory space')
                if data is not None:
                    if len(data)!=length:raise ValueError('Machine write length differs')
                    if self.request(f'M{address:x},{length:x}:{data.hex()}')!=b'OK':raise DebuggerError('Machine memory write rejected')
                raw=self.request(f'm{address:x},{length:x}')
                value=bytes.fromhex(raw.decode('ascii'))
                if len(value)!=length:raise DebuggerError('Incomplete machine memory read')
                return value
            finally:
                if self.socket is not None and original!=mode:
                    if self.request(b'Qqemu.PhyMemMode:'+original)!=b'OK':self.close();raise DebuggerError('Could not restore memory space')

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None
