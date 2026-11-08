"""Bounded GDB remote protocol for an owned QEMU system-emulation socket."""
from __future__ import annotations

from contextlib import contextmanager
import socket
import threading
import time
import xml.etree.ElementTree as ET

from .dosbox_rpc import DebuggerError


class GDBRemote:
    limit = 8*1024*1024

    def __init__(self, path, process, deadline, *, channel=None):
        self.socket=channel if channel is not None else socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.lock=threading.RLock();self.console=[];self.register_description=[];self._buffer=b'';self._cursor=0
        self._packet_state=None
        # Initialization shares its caller's budget. The machine owner may set
        # another absolute deadline around later multi-command operations.
        self.operation_deadline=deadline
        try:
            if channel is None:
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('GDB initialization deadline expired')
                    self.socket.settimeout(remaining)
                    try:self.socket.connect(str(path));break
                    except (FileNotFoundError,ConnectionRefusedError):
                        if process.poll() is not None or time.monotonic()>=deadline:
                            raise DebuggerError('QEMU GDB socket did not open')
                        time.sleep(min(.02,max(0,deadline-time.monotonic())))
            self.features=self.request('qSupported:qXfer:features:read+;multiprocess+',
                                       timeout_ms=max(1,int((deadline-time.monotonic())*1000))).decode('ascii')
            sizes=[item.split('=',1)[1] for item in self.features.split(';') if item.startswith('PacketSize=')]
            if len(sizes)>1:raise DebuggerError('Conflicting GDB packet-size limits')
            try:self.packet_size=min(self.limit,int(sizes[0],16)) if sizes else 4096
            except ValueError as error:raise DebuggerError('Invalid GDB packet-size limit') from error
            if self.packet_size<64:raise DebuggerError('GDB packet-size limit is too small')
            self._load_registers(deadline=deadline)
            self.operation_deadline=None
        except BaseException:
            self.close();raise

    def _operation_end(self,timeout_ms):
        deadline=time.monotonic()+timeout_ms/1000
        shared=getattr(self,'operation_deadline',None)
        return deadline if shared is None else min(deadline,shared)

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
        # execute() interrupts on a deadline, then continues reading the same
        # stop reply. Keep framing state across that timeout: a fragment such
        # as "$T05" must not turn its later checksum into a new packet prefix.
        while True:
            state=getattr(self,'_packet_state',None)
            if state is None:
                first=self._byte(deadline)
                if first==ord('+'):continue
                if first==ord('-'):raise DebuggerError('GDB rejected packet; request not replayed')
                if first!=ord('$'):raise DebuggerError('Invalid GDB packet prefix')
                state={'raw':bytearray(),'checksum':bytearray(),'payload':True}
                self._packet_state=state
            raw=state['raw']
            while state['payload']:
                value=self._byte(deadline)
                if value==ord('#'):
                    state['payload']=False
                    break
                raw.append(value)
                if len(raw)>self.limit:raise DebuggerError('GDB packet exceeds budget')
            while len(state['checksum'])<2:
                state['checksum'].append(self._byte(deadline))
            try:checksum=int(state['checksum'],16)
            except ValueError as error:raise DebuggerError('Invalid GDB checksum') from error
            if sum(raw)%256!=checksum:raise DebuggerError('GDB checksum mismatch; request not replayed')
            self.socket.sendall(b'+')
            self._packet_state=None
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
        packet=b'$'+encoded+b'#'+f'{sum(encoded)%256:02x}'.encode()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('GDB operation deadline expired before dispatch')
        self.socket.settimeout(remaining)
        self.socket.sendall(packet)

    @contextmanager
    def _locked(self,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0 or not self.lock.acquire(timeout=remaining):
            raise TimeoutError('GDB operation deadline expired while waiting for the channel')
        try:yield
        finally:self.lock.release()

    def request(self,command,timeout_ms=10000):
        deadline=self._operation_end(timeout_ms)
        with self._locked(deadline):
            try:
                self._send(command,deadline);reply=self._packet(deadline)
                if reply.startswith(b'E'):raise DebuggerError('QEMU GDB operation failed: '+reply.decode(errors='replace'))
                return reply
            except BaseException:self.close();raise

    def execute(self,command,timeout_ms):
        """Continue/step once, with at most five extra seconds to interrupt/stop."""
        deadline=self._operation_end(timeout_ms)
        with self._locked(deadline):
            try:
                self._send(command,deadline)
                try:return self._packet(deadline),False
                except (TimeoutError,socket.timeout):
                    # Execution was dispatched once. Recovery may exceed the
                    # operation budget only to interrupt and observe that same
                    # stop reply; it cannot authorize another execution request.
                    recovery_deadline=time.monotonic()+5
                    self.socket.settimeout(5)
                    self.socket.sendall(b'\x03')
                    return self._packet(recovery_deadline),True
            except BaseException:self.close();raise

    def _xml(self,name,*,deadline=None):
        data=bytearray()
        for _ in range(1024):
            timeout_ms=10000 if deadline is None else int((deadline-time.monotonic())*1000)
            if timeout_ms<=0:raise TimeoutError('GDB register discovery deadline expired')
            amount=min(4096,getattr(self,'packet_size',4096)-4)
            part=self.request(f'qXfer:features:read:{name}:{len(data):x},{amount:x}',timeout_ms=timeout_ms)
            if not part or part[:1] not in (b'm',b'l'):raise DebuggerError('Missing GDB register XML')
            data.extend(part[1:])
            if len(data)>1024*1024:raise DebuggerError('GDB register XML exceeds budget')
            if part[:1]==b'l':
                # QEMU emits GDB's abbreviated xi:include form without an XML
                # namespace declaration. No external DTD/entity is fetched.
                return ET.fromstring(bytes(data).replace(b'xi:include',b'include'))
        raise DebuggerError('GDB register XML pagination exceeded budget')

    def _load_registers(self,*,deadline=None):
        visited=set();next_number=0
        def visit(name):
            nonlocal next_number
            if name in visited or len(visited)>=32 or '/' in name or '..' in name:
                raise DebuggerError('Invalid or recursive GDB register include')
            visited.add(name);root=self._xml(name,deadline=deadline)
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

    def memory(self,address,length,*,space='physical',data=None,timeout_ms=10000):
        if space not in ('physical','virtual') or type(address) is not int or not 0<=address<2**64 or type(length) is not int or not 1<=length<=65536 or address+length>2**64:
            raise ValueError('Invalid machine memory address, length or space')
        if data is not None and len(data)!=length:raise ValueError('Machine write length differs')
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Memory timeout must be 1..600000 ms')
        # Older QEMU stubs advertise a 4-KiB packet budget. A memory byte uses
        # two ASCII characters and write requests also carry an address/length
        # header. The public 64-KiB memory budget therefore spans packets.
        packet_size=getattr(self,'packet_size',4096)
        read_size=(packet_size-4)//2
        write_size=(packet_size-32)//2
        deadline=self._operation_end(timeout_ms)
        def exchange(command):
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:raise TimeoutError('GDB memory-transfer deadline expired')
            return self.request(command,timeout_ms=remaining)
        with self._locked(deadline):
            original=exchange('qqemu.PhyMemMode')
            if original not in (b'0',b'1'):raise DebuggerError('QEMU physical-memory mode unavailable')
            mode=b'1' if space=='physical' else b'0'
            try:
                if original!=mode and exchange(b'Qqemu.PhyMemMode:'+mode)!=b'OK':raise DebuggerError('Could not select memory space')
                if data is not None:
                    for offset in range(0,length,write_size):
                        part=data[offset:offset+write_size]
                        if exchange(f'M{address+offset:x},{len(part):x}:{part.hex()}')!=b'OK':
                            raise DebuggerError('Machine memory write rejected')
                value=bytearray()
                for offset in range(0,length,read_size):
                    amount=min(read_size,length-offset)
                    raw=exchange(f'm{address+offset:x},{amount:x}')
                    part=bytes.fromhex(raw.decode('ascii'))
                    if len(part)!=amount:raise DebuggerError('Incomplete machine memory read')
                    value.extend(part)
                return bytes(value)
            except BaseException:
                # A later write chunk or readback can fail after earlier bytes
                # changed. Poison the channel so the machine owner closes the
                # VM; neither a rollback nor a blind replay is safe here.
                if data is not None:self.close()
                raise
            finally:
                if self.socket is not None and original!=mode:
                    # One bounded recovery exchange restores protocol mode; a
                    # transfer timeout never grants every chunk a fresh budget.
                    # An inherited deadline also bounds this recovery. If it
                    # has expired, close instead of leaving a reusable channel
                    # whose selected address space differs from the caller's.
                    try:
                        if self.request(b'Qqemu.PhyMemMode:'+original,timeout_ms=5000)!=b'OK':
                            raise DebuggerError('Could not restore memory space')
                    except BaseException:self.close();raise

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None
