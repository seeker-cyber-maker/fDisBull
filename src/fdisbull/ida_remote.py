"""Debugger operations over the published IDA interface-31 protocol."""
from __future__ import annotations

import time
from contextlib import contextmanager

from . import ida_wire as w


class RemoteDebugger(w.Client):
    def __init__(self, stream, *, debugger_id=0, password='', execution_mechanism='hardware'):
        if execution_mechanism not in ('hardware','page'):
            raise ValueError('Invalid execution breakpoint mechanism')
        self.execution_mechanism=execution_mechanism
        super().__init__(stream, debugger_id=debugger_id, password=password)
        self.pending = None
        self.pid = None
        self.threads = set()
        self.breakpoints = {}
        self.next_breakpoint = 1
        self.displaced = None
        self.exited = False
        self.last_state = {'state': 'ready'}
        self._step_scope_tid = None
        self._step_scope_held = set()
        try:
            # The client owns software-breakpoint displacement; the server owns
            # the actual process, thread and memory operations.
            reply = self.request(w.INIT, w.dq(1) + w.dd(0) + w.string('fdisbull') + w.string('metapc') + w.dd(debugger_id))
            self._success(reply)
            self.flags = reply.dq()
            self.description = w.register_set(reply)
            reply.finish()
            if debugger_id==0:
                # Page-breakpoint displacement reuses access-violation stops.
                # Its internal single step must consume those debugger-created
                # faults. Genuine target exceptions are reset to unhandled in
                # _stop(), so continuation still reaches the program's SEH.
                policy=w.dd(1)+w.dd(0xc0000005)+w.dd(3)+w.string('ACCESS_VIOLATION')+w.string('Access violation')
                self.request(34,policy).finish()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _success(reply):
        code = reply.dd()
        if code != 1:
            message = reply.string() if reply.offset < len(reply.data) else ''
            raise w.ProtocolError('Debugger operation failed (' + str(code) + '): ' + message)

    def checked(self, code, data=b'', *, timeout=30):
        reply = self.request(code, data, timeout=timeout)
        try:self._success(reply)
        except w.ProtocolError as error:raise w.ProtocolError(f'IDA RPC {code}: {error}') from error
        reply.finish()

    def start(self, path, *, directory='', bits=64, timeout_ms=120000):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:
            raise ValueError('Launch timeout must be 1..600000 ms')
        if self.pid is not None:
            raise ValueError('Remote debugger already owns a target')
        payload = (w.string(path) + w.string('') + w.string(directory) + w.dd(8 if bits == 64 else 0) +
                   w.string(path) + w.dd(0) + b'\1' + w.dd(0))
        reply = self.request(w.START, payload, timeout=timeout_ms/1000)
        self._success(reply)
        self.address_size, self.platform = reply.dd(), reply.string()
        self.description = w.register_set(reply)
        reply.finish()
        event = self.get_event(time.monotonic() + 30)
        if event is None or event['eid'] != 1:
            raise w.ProtocolError('Expected process-start event')
        self.pid = event['pid']
        self.image_base = event['module']['base']
        return event

    def get_event(self, deadline):
        while time.monotonic() < deadline:
            if self.events:
                event = self.events.pop(0)
            else:
                remaining = max(1, min(50, int((deadline - time.monotonic()) * 1000)))
                reply = self.request(w.GET_EVENT, w.dd(remaining), timeout=max(1, deadline - time.monotonic()))
                result = reply.dd()
                if result not in (0, 1, 2):
                    raise w.ProtocolError('Remote event retrieval failed')
                event = w.decode_event(reply) if result else None
                reply.finish()
                if event is None:
                    if self.events:
                        event = self.events.pop(0)
                    else:
                        continue
            self.pending = event
            if event['eid'] in (1, 3, 11):
                self.threads.add(event['tid'])
            if event['eid'] == 4:
                self.threads.discard(event['tid'])
            return event
        return None

    def continue_event(self):
        if self.pending is None:
            raise ValueError('No stopped event to continue')
        event = self.pending
        self.checked(w.CONTINUE, w.encode_event(event))
        self.pending = None

    def registers(self):
        if self.pending is None or self.exited:
            raise ValueError('Registers require a stopped target')
        regs = self.description['registers']
        mask = bytearray((len(regs) + 7) // 8)
        chosen = []
        for i, item in enumerate(regs):
            if item['register_class'] & 3:
                mask[i // 8] |= 1 << (i % 8)
                chosen.append(item)
        reply = self.request(w.READ_REGS, w.dd(self.pending['tid']) + w.dd(3) + w.dd(len(regs)) + mask)
        self._success(reply)
        result = {item['name']: w.read_integer_register(reply) for item in chosen}
        reply.finish()
        return result

    def set_register(self, name, value):
        if self.pending is None or self.exited:
            raise ValueError('Register edits require a stopped target')
        regs = self.description['registers']
        index = next((i for i, item in enumerate(regs) if item['name'] == name), None)
        if index is None:
            raise ValueError('Unknown native register: ' + name)
        self.checked(w.WRITE_REG, w.dd(self.pending['tid']) + w.dd(index) + w.integer_register(value))

    def read(self, address, size, *, logical=True):
        if not 1 <= size <= 65536:
            raise ValueError('Memory read size must be 1..65536')
        reply = self.request(w.READ, w.ea(address) + w.dd(size))
        count = reply.dd()
        if count != size:
            raise w.ProtocolError('Incomplete remote memory read')
        data = bytearray(reply.raw(count))
        reply.finish()
        if logical:
            for record in self.breakpoints.values():
                offset = record['address'] - address
                if record['type'] == 4 and 0 <= offset < size:
                    data[offset:offset+1] = record['original']
        return bytes(data)

    def write(self, address, data):
        if not 1 <= len(data) <= 65536:
            raise ValueError('Memory write size must be 1..65536')
        if any(record['type'] == 4 and address <= record['address'] < address + len(data)
               for record in self.breakpoints.values()):
            raise ValueError('Delete overlapping execution breakpoints before memory editing')
        reply = self.request(w.WRITE, w.ea(address) + w.dd(len(data)) + data)
        if reply.dd() != len(data):
            raise w.ProtocolError('Incomplete remote memory write')
        reply.finish()
        if self.read(address, len(data), logical=False) != data:
            raise w.ProtocolError('Remote memory write readback differs')

    def read_code(self, address):
        """Read up to one x86 instruction, accepting a real short page read."""
        reply = self.request(w.READ, w.ea(address) + w.dd(15))
        count = reply.dd()
        if not 1 <= count <= 15:
            raise w.ProtocolError('Invalid remote instruction read length')
        data = reply.raw(count)
        reply.finish()
        return data

    def breakpoint_boundary(self, observed_pc):
        """Stop before the next owned PC without inventing a native BP event."""
        if self.last_state['stop_reason']['kind'] != 'step':
            return self.last_state
        matched = [identifier for identifier, record in self.breakpoints.items()
                   if record['access'] == 'x' and record['address'] == observed_pc]
        if matched:
            for identifier in matched:
                record = self.breakpoints[identifier]
                if record['armed'] and self.debugger_id == 0:
                    self._remove(record)
                    self.displaced = identifier
            stop = dict(self.last_state['stop_reason'], kind='breakpoint', native_kind='step',
                        address=hex(observed_pc), breakpoint_ids=matched, stop_origin='single-step-boundary')
            self.last_state = dict(self.last_state, stop_reason=stop)
        return self.last_state

    def _hold_step_peer(self, tid):
        if tid != self._step_scope_tid and tid not in self._step_scope_held:
            self.checked(w.SUSPEND, w.dd(tid))
            self._step_scope_held.add(tid)

    @contextmanager
    def step_scope(self):
        """Hold peer threads across a bounded collection, including new peers."""
        if self.pending is None or self.exited:
            raise ValueError('Step requires a stopped target')
        tid = self.pending['tid']
        if self._step_scope_tid is not None:
            if self._step_scope_tid != tid:
                raise w.ProtocolError('Selected thread changed inside trace scope')
            yield
            return
        self._step_scope_tid = tid
        try:
            for other in sorted(self.threads - {tid}):
                self._hold_step_peer(other)
            yield
        finally:
            try:
                if self.channel.stream is not None and not self.exited:
                    for other in sorted(self._step_scope_held & self.threads):
                        self.checked(w.RESUME, w.dd(other))
            except BaseException:
                self.close()
                raise
            finally:
                self._step_scope_tid = None
                self._step_scope_held.clear()

    def _add(self, record):
        reply = self.request(w.BREAKPOINTS, w.dd(1) + w.dd(0) + w.ea(record['address']) +
                             w.dd(record.get('native_length',record['length'])) + w.dd(record['type']) + w.dd(0xffffffff) + w.dd(0))
        self._success(reply)
        count, code = reply.dd(), reply.byte()
        if count != 1 or code not in (0, 10):
            raise w.ProtocolError('Breakpoint rejected: ' + str(code))
        if record['type'] == 4:
            record['original'] = reply.raw(reply.byte())
            if len(record['original']) != 1:
                raise w.ProtocolError('Expected one-byte x86 software breakpoint')
        record['page'] = code == 10
        if record.get('force_page') and not record['page']:
            raise w.ProtocolError('Server did not provide the requested page execution breakpoint')
        record['armed'] = True
        reply.finish()

    def breakpoint(self, address, *, access='x', length=1):
        # Execute watches must not change guest code bytes. IDA selects a debug
        # register or a page breakpoint; INT3 is deliberately never requested.
        kinds = {'x': 8, 'r': 2, 'w': 1, 'rw': 3}
        if access not in kinds or not 1 <= length <= 65536 or access == 'x' and length != 1:
            raise ValueError('Invalid breakpoint access/length')
        if len(self.breakpoints) >= 256 or any(r['address'] == address for r in self.breakpoints.values()):
            raise ValueError('Duplicate breakpoint or breakpoint budget exceeded')
        record = dict(address=address, length=length, type=kinds[access], access=access)
        if access=='x' and self.execution_mechanism=='page':
            # x86 debug registers require execute length=1. IDA deliberately
            # falls back to its page engine for length=2. The extra byte is
            # filtered below; the declared execution stop is one exact PC.
            record.update(native_length=2,force_page=True)
        self._add(record)
        identifier = 'bp-' + str(self.next_breakpoint)
        self.next_breakpoint += 1
        self.breakpoints[identifier] = record
        return identifier

    def _remove(self, record):
        original = record.get('original', b'')
        reply = self.request(w.BREAKPOINTS, w.dd(0) + w.dd(1) + w.ea(record['address']) + bytes([len(original)]) +
                             original + w.dd(record['type']) + w.dd(0xffffffff) + w.dd(0))
        self._success(reply)
        count, code = reply.dd(), reply.byte()
        reply.finish()
        if count != 1 or code != 0:
            raise w.ProtocolError('Breakpoint removal failed')
        record['armed'] = False

    def delete_breakpoint(self, identifier):
        record = self.breakpoints[identifier]
        if record['armed']:
            self._remove(record)
        del self.breakpoints[identifier]

    def _stop(self, event, *, timed_out=False):
        if event['eid']==7:
            event['handled']=False
        kind = {2: 'exited', 4: 'thread-exited', 5: 'breakpoint', 6: 'step', 7: 'exception', 13: 'pause'}.get(event['eid'], 'event')
        matched = []
        for identifier, record in self.breakpoints.items():
            if event['eid'] == 5 and (record['access'] == 'x' and event['address'] == record['address'] or
                record['access'] != 'x' and record['address'] <= event['hardware_address'] < record['address'] + record['length']):
                matched.append(identifier)
                if record['access'] == 'x' and not self.flags & 16:
                    self._remove(record)
                    regs = self.registers()
                    ip_name = 'rip' if 'rip' in regs else 'eip'
                    if regs[ip_name] != event['address']:
                        raise w.ProtocolError('Unexpected PC at execution breakpoint')
                    self.displaced = identifier
                elif record['access'] != 'x':
                    kind = 'watchpoint'
                    if record['page']:
                        self._remove(record)
                        self.displaced = identifier
        self.exited = event['eid'] == 2
        stop = dict(kind='timeout' if timed_out else kind, address=hex(event['address']), thread=event['tid'],
                    breakpoint_ids=matched, native_event=event, before_access=None)
        if kind == 'watchpoint':
            stop['before_access'] = any(self.breakpoints[i]['page'] for i in matched)
        self.last_state = dict(state='exited' if self.exited else 'stopped', stop_reason=stop,
                               exit_code=event.get('exit_code', 0))
        return self.last_state

    def _wait_stop(self, deadline, *, stepping=False):
        for _ in range(16384):
            event = self.get_event(deadline)
            if event is None:
                return None
            if event['eid'] == 3 and self._step_scope_tid is not None:
                self._hold_step_peer(event['tid'])
            if event['eid'] == 4 and event['tid'] == self._step_scope_tid:
                return self._stop(event)
            if event['eid'] in (1, 3, 4, 8, 9, 10):
                self.continue_event()
                continue
            result=self._stop(event)
            if event['eid']==5 and not result['stop_reason']['breakpoint_ids']:
                adjacent=next((identifier for identifier,record in self.breakpoints.items()
                    if record.get('force_page') and record['address']<event['address']<record['address']+record['native_length']),None)
                if adjacent is not None:
                    self._remove(self.breakpoints[adjacent]);self.displaced=adjacent
                    result=self.step(max(1,int((deadline-time.monotonic())*1000)))
                    if result['stop_reason']['kind']=='step':
                        if stepping:return result
                        self.continue_event()
                        continue
            return result
        raise w.ProtocolError('Administrative event budget exceeded')

    def step(self, timeout_ms=10000):
        deadline = time.monotonic() + timeout_ms / 1000
        if self.pending is None or self.exited:
            raise ValueError('Step requires a stopped target')
        tid = self.pending['tid']
        with self.step_scope():
            self.checked(w.RESUME_MODE, w.dd(tid) + w.dd(1))
            displaced = self.displaced
            self.continue_event()
            result = self._wait_stop(deadline, stepping=True)
            if result is None:
                self.close()
                raise TimeoutError('Remote single step did not complete; session cannot resume')
            if result['stop_reason']['kind'] == 'step' and result['stop_reason']['thread'] != tid:
                self.close()
                raise w.ProtocolError('Single-step event belongs to another thread')
            if result['stop_reason']['kind'] == 'step':
                if displaced in self.breakpoints:
                    self._add(self.breakpoints[displaced])
                self.displaced = None
            # The Windows SDK only accepts RESMOD_INTO and clears stepping on
            # its STEP event. Sending RESMOD_NONE there is a failed operation.
            if not self.exited and self.debugger_id!=0:
                self.checked(w.RESUME_MODE, w.dd(tid) + w.dd(0))
            return result

    def run(self, timeout_ms=10000):
        if self.pending is None or self.exited:
            raise ValueError('Run requires a stopped target')
        deadline = time.monotonic() + timeout_ms / 1000
        if self.displaced is not None:
            result = self.step(max(1, int((deadline - time.monotonic()) * 1000)))
            if result['stop_reason']['kind'] != 'step':
                return result
        self.continue_event()
        result = self._wait_stop(deadline)
        if result is not None:
            return result
        self.checked(w.PAUSE)
        result = self._wait_stop(time.monotonic() + 10)
        if result is None:
            raise TimeoutError('Remote pause did not stop target; session cannot resume')
        if result['stop_reason']['kind'] in ('pause', 'exception'):
            result['stop_reason']['native_kind'] = result['stop_reason']['kind']
            result['stop_reason']['kind'] = 'timeout'
        return result
