"""Bounded IDA debugger RPC, interface 31 (IDA 9.4).

Wire layout follows the public Hex-Rays SDK; see docs/IDA_REMOTE.md for the
immutable source reference and attribution. No IDA executable is bundled.
"""
from __future__ import annotations

import socket
import struct
import time


class ProtocolError(ValueError):
    pass


MASK64 = (1 << 64) - 1
OK, UNKNOWN, MEMORY, OPEN, EVENT, EVOK = range(6)
INIT, TERM, PROCESSES, START, EXIT, ATTACH, DETACH = range(10, 17)
GET_EVENT, PAUSE, STOPPED, CONTINUE, SUSPEND, RESUME = range(17, 23)
RESUME_MODE, MEMORY_INFO, READ, WRITE, BREAKPOINTS = range(23, 28)
READ_REGS, WRITE_REG = 31, 32
INTERFACE = 31
MAX_PACKET = 8 * 1024 * 1024


def dd(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ProtocolError('Expected unsigned 32-bit integer')
    if value < 0x80:
        return bytes([value])
    if value < 0x4000:
        return (value | 0x8000).to_bytes(2, 'big')
    if value < 0x20000000:
        return (value | 0xc0000000).to_bytes(4, 'big')
    return b'\xff' + value.to_bytes(4, 'big')


def dq(value):
    if type(value) is not int or not 0 <= value <= MASK64:
        raise ProtocolError('Expected unsigned 64-bit integer')
    return dd(value & 0xffffffff) + dd(value >> 32)


def ea(value):
    if type(value) is not int or not 0 <= value <= MASK64:
        raise ProtocolError('Expected unsigned address')
    return dq((value + 1) & MASK64)


def string(value):
    data = value.encode('utf-8')
    if b'\0' in data or len(data) > 65536:
        raise ProtocolError('Invalid protocol string')
    return data + b'\0'


class Reader:
    def __init__(self, data):
        self.data = bytes(data)
        self.offset = 0

    def raw(self, count):
        if not 0 <= count <= len(self.data) - self.offset:
            raise ProtocolError('Truncated protocol object')
        start = self.offset
        self.offset += count
        return self.data[start:self.offset]

    def byte(self):
        return self.raw(1)[0]

    def dd(self):
        first = self.byte()
        if first < 0x80:
            return first
        if first < 0xc0:
            return ((first & 0x3f) << 8) | self.byte()
        if first < 0xe0:
            return ((first & 0x1f) << 24) | int.from_bytes(self.raw(3), 'big')
        if first == 0xff:
            return int.from_bytes(self.raw(4), 'big')
        raise ProtocolError('Invalid packed integer prefix')

    def dq(self):
        low = self.dd()
        return low | (self.dd() << 32)

    def ea(self):
        return (self.dq() - 1) & MASK64

    def string(self):
        end = self.data.find(b'\0', self.offset, self.offset + 65537)
        if end < 0:
            raise ProtocolError('Unterminated protocol string')
        return self.raw(end - self.offset + 1)[:-1].decode('utf-8', errors='strict')

    def finish(self):
        if self.offset != len(self.data):
            raise ProtocolError('Unexpected trailing protocol bytes')


def encode_event(event):
    kind = event['eid']
    data = dd(kind) + dd(event['pid']) + dd(event['tid']) + ea(event['address']) + dd(int(event.get('handled', False)))
    if kind in (1, 8, 11):
        module = event['module']
        data += string(module['name']) + ea(module['base']) + ea(module['size']) + ea(module.get('rebase_to', MASK64))
    elif kind in (2, 4):
        data += dd(event['exit_code'])
    elif kind == 5:
        data += ea(event.get('hardware_address', MASK64)) + ea(event.get('kernel_address', MASK64))
    elif kind == 7:
        data += dd(event['exception_code']) + dd(int(event['can_continue'])) + ea(event['exception_address']) + string(event['info'])
    elif kind in (3, 9, 10):
        data += string(event.get('info', ''))
    return data


def decode_event(reader):
    event = dict(eid=reader.dd(), pid=reader.dd(), tid=reader.dd(), address=reader.ea(), handled=bool(reader.dd()))
    kind = event['eid']
    if kind in (1, 8, 11):
        event['module'] = dict(name=reader.string(), base=reader.ea(), size=reader.ea(), rebase_to=reader.ea())
    elif kind in (2, 4):
        event['exit_code'] = reader.dd()
    elif kind == 5:
        event.update(hardware_address=reader.ea(), kernel_address=reader.ea())
    elif kind == 7:
        event.update(exception_code=reader.dd(), can_continue=bool(reader.dd()), exception_address=reader.ea(), info=reader.string())
    elif kind in (3, 9, 10):
        event['info'] = reader.string()
    elif kind not in (0, 6, 12, 13):
        raise ProtocolError('Unsupported debug event kind: ' + str(kind))
    return event


def register_set(reader):
    """Read the versioned dynamic register description, never assume indices."""
    if reader.dd() != 0xffffff01:
        raise ProtocolError('Unsupported dynamic register description version')
    def count(limit):
        value = reader.dd()
        if value > limit:
            raise ProtocolError('Register description exceeds budget')
        return value
    classes = [reader.string() for _ in range(count(32))]
    bits = [[reader.string() for _ in range(count(512))] for _ in range(count(512))]
    registers = []
    for _ in range(count(512)):
        item = dict(name=reader.string().lower(), flags=reader.dd(), register_class=reader.dd(),
                    dtype=reader.dd(), bit_strings=reader.dd(), mask=reader.ea())
        if not item['name'] or item['bit_strings'] > len(bits):
            raise ProtocolError('Invalid register description')
        registers.append(item)
    default = reader.dd()
    if len({r['name'] for r in registers}) != len(registers):
        raise ProtocolError('Duplicate register names')
    return dict(classes=classes, bits=bits, registers=registers, default=default)


def encode_register_set(description):
    classes = description['classes']
    registers = description['registers']
    bits = description.get('bits', [])
    data = dd(0xffffff01) + dd(len(classes)) + b''.join(string(c) for c in classes) + dd(len(bits))
    for group in bits:
        data += dd(len(group)) + b''.join(string(value) for value in group)
    data += dd(len(registers))
    for reg in registers:
        data += (string(reg['name'].upper()) + dd(reg['flags']) + dd(reg['register_class']) +
                 dd(reg['dtype']) + dd(reg.get('bit_strings', 0)) + ea(reg.get('mask', 0)))
    return data + dd(description['default'])


def integer_register(value):
    return dd(1) + ea(value)


def read_integer_register(reader):
    if reader.dd() != 1:
        raise ProtocolError('Requested register is not an available integer')
    return reader.ea()


class Channel:
    """One owned stream; any uncertain operation closes it without replay."""
    def __init__(self, stream):
        self.stream = stream

    def close(self):
        stream,self.stream=self.stream,None
        if stream is not None:
            try:stream.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            stream.close()

    def _read(self, count, deadline):
        if self.stream is None:
            raise ProtocolError('IDA RPC stream is closed')
        data = bytearray()
        while len(data) < count:
            stream=self.stream
            if stream is None:
                raise ProtocolError('IDA RPC stream is closed')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('IDA RPC deadline expired')
            # Periodic wakeup also makes cross-thread cancellation deterministic
            # on hosts where close alone does not wake a timed socket receive.
            stream.settimeout(min(.25,remaining))
            try:part = stream.recv(count - len(data))
            except socket.timeout:continue
            if not part:
                raise ProtocolError('IDA RPC stream closed')
            data.extend(part)
        return bytes(data)

    def receive(self, deadline):
        try:
            size, code = struct.unpack('!IB', self._read(5, deadline))
            if size > MAX_PACKET:
                raise ProtocolError('IDA RPC packet exceeds budget')
            return code, self._read(size, deadline)
        except BaseException:
            self.close()
            raise

    def send(self, code, data, deadline):
        try:
            if self.stream is None:
                raise ProtocolError('IDA RPC stream is closed')
            if len(data) > MAX_PACKET:
                raise ProtocolError('IDA RPC packet exceeds budget')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('IDA RPC deadline expired')
            self.stream.settimeout(remaining)
            self.stream.sendall(struct.pack('!IB', len(data), code) + data)
        except BaseException:
            self.close()
            raise


class Client:
    def __init__(self, stream, *, debugger_id=0, password='', timeout=10):
        self.channel = Channel(stream)
        self.events = []
        self.messages = []
        deadline = time.monotonic() + timeout
        try:
            code, data = self.channel.receive(deadline)
            if code != OPEN:
                raise ProtocolError('Expected IDA server greeting')
            greeting = Reader(data)
            self.interface, self.debugger_id, self.address_size = greeting.dd(), greeting.dd(), greeting.dd()
            greeting.finish()
            if self.interface != INTERFACE or self.debugger_id != debugger_id or self.address_size != 8:
                raise ProtocolError('Unsupported IDA interface/debugger/address size: ' + str((self.interface, self.debugger_id, self.address_size)))
            self.channel.send(OK, dd(1) + string(password), deadline)
            code, data = self.channel.receive(deadline)
            answer = Reader(data)
            if code != OK or answer.dd() != 1:
                raise ProtocolError('IDA server authentication failed')
            answer.finish()
        except BaseException:
            self.channel.close()
            raise

    def _notification(self, code, data, deadline):
        if code == EVENT:
            reader = Reader(data)
            self.events.append(decode_event(reader))
            reader.finish()
            if len(self.events) > 1024:
                raise ProtocolError('Unconsumed debugger event budget exceeded')
            self.channel.send(EVOK, b'', deadline)
        elif code in (52, 53, 54):
            reader = Reader(data)
            message = reader.string()
            reader.finish()
            self.messages.append(dict(code=code, message=message))
            self.messages[:] = self.messages[-64:]
            self.channel.send(OK, b'', deadline)
            if code == 52:
                raise ProtocolError('IDA server: ' + message)
        else:
            raise ProtocolError('Unsupported server callback: ' + str(code))

    def request(self, code, data=b'', *, timeout=30):
        deadline = time.monotonic() + timeout
        try:
            self.channel.send(code, data, deadline)
            for _ in range(2048):
                answer, payload = self.channel.receive(deadline)
                if answer == OK:
                    return Reader(payload)
                if answer in (UNKNOWN, MEMORY):
                    raise ProtocolError('IDA server rejected RPC ' + str(code))
                self._notification(answer, payload, deadline)
            raise ProtocolError('IDA callback budget exceeded')
        except BaseException:
            self.channel.close()
            raise

    def close(self):
        self.channel.close()
