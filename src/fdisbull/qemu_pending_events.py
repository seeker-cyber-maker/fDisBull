"""One bounded matching-response event batch, before cooperative admission.

The batch says nothing about a quiet stream, discarded history, device-cause
order, or frame/CPU atomicity. Strict ObservationLease remains excluding it.
"""
from copy import deepcopy
from functools import wraps
import json
import re
import time

from .dosbox_rpc import DebuggerError
from .qemu_frame_read import FrameReadOwner


COMMAND = 'x-fdisbull-take-pending-events'
MODEL = 'stopped-pending-qmp-events-v1'
BOUNDARY = 'matching-response-event-batch'
STATES = frozenset(('prelaunch', 'debug', 'paused'))
MAX_EVENTS = 64
MAX_REPLY = 256 * 1024
MAX_WIRE = 512 * 1024
_UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
_RETURN_KEYS = frozenset(('model', 'boundary', 'monitor-id', 'monitor-epoch',
                          'status', 'event-count', 'events'))


def _require(value, message):
    if not value:
        raise DebuggerError('Pending QMP events: ' + message)


def supported(vm):
    return (getattr(vm, 'transport', None) == 'pipe'
            and COMMAND in getattr(vm, 'qmp_commands', ()))


def _binding(callable_value):
    return (getattr(callable_value, '__self__', None),
            getattr(callable_value, '__func__', callable_value))


def _ascii(value, limit, *, nonempty=False):
    _require(type(value) is str and len(value) <= limit and value.isascii()
             and '\0' not in value and (not nonempty or bool(value)), 'invalid ASCII string')
    return len(value)


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=True, separators=(', ', ': ')).encode('ascii'))


class _EventBudget:
    def __init__(self):
        self.nodes = self.strings = 0
        self.containers = set()

    def string(self, value, limit):
        self.strings += _ascii(value, limit)
        _require(self.strings <= 32768, 'decoded string aggregate exceeds 32 KiB')

    def value(self, value, depth, first):
        self.nodes += 1
        _require(depth <= 8 and self.nodes <= 4096 and self.nodes-first <= 256,
                 'event depth or node bound exceeded')
        kind = type(value)
        if kind in (dict, list):
            identity = id(value)
            _require(identity not in self.containers, 'event container alias or cycle')
            self.containers.add(identity)
            _require(len(value) <= (64 if kind is dict else 256), 'event container too large')
            if kind is dict:
                members = []
                for key, child in value.items():
                    self.string(key, 128)
                    members.append((key, self.value(child, depth+1, first)))
                return ('dict', identity, tuple(members))
            return ('list', identity, tuple(self.value(child, depth+1, first) for child in value))
        if kind is str:
            self.string(value, 4096)
        elif kind is int:
            _require(-(1 << 63) <= value < 1 << 64, 'integer outside int64/uint64')
        else:
            _require(value is None or kind is bool, 'unsupported scalar type')
        return (kind.__name__, value)


def validate_events(events):
    """Validate the complete batch before any delegate; retain identities too."""
    _require(type(events) is list and len(events) <= MAX_EVENTS, 'event-list shape or count')
    budget, result = _EventBudget(), []
    for event in events:
        _require(type(event) is dict and 'event' in event
                 and set(event) <= {'event', 'data', 'timestamp'}, 'event envelope shape')
        _ascii(event['event'], 128, nonempty=True)
        _require('data' not in event or type(event['data']) is dict, 'event data is not an object')
        if 'timestamp' in event:
            stamp = event['timestamp']
            _require(type(stamp) is dict and set(stamp) == {'seconds', 'microseconds'}
                     and _integer(stamp['seconds'], 0, (1 << 63)-1)
                     and _integer(stamp['microseconds'], 0, 999999), 'timestamp shape or scalar')
        result.append(budget.value(event, 1, budget.nodes))
        _require(_json_size(event) <= 16384, 'event encoded size exceeds 16 KiB')
    _require(_json_size(events) <= 131072, 'event-list encoded size exceeds 128 KiB')
    return (id(events), tuple(result))


def validate_reply(reply, request_id):
    _require(type(reply) is dict and set(reply) == {'id', 'return'}, 'matching result envelope shape')
    _require(_integer(reply['id'], 1, (1 << 64)-1) and reply['id'] == request_id,
             'matching request ID changed or is not an exact positive integer')
    value = reply['return']
    _require(type(value) is dict and set(value) == _RETURN_KEYS, 'retained batch fields differ')
    _require(value['model'] == MODEL and type(value['model']) is str
             and value['boundary'] == BOUNDARY and type(value['boundary']) is str, 'model or boundary differs')
    _require(type(value['monitor-id']) is str and _UUID.fullmatch(value['monitor-id']) is not None
             and _integer(value['monitor-epoch'], 1, (1 << 64)-1), 'native monitor identity differs')
    _require(type(value['status']) is str and value['status'] in STATES, 'native state is not eligible stopped')
    events = value['events']
    _require(_integer(value['event-count'], 0, MAX_EVENTS) and type(events) is list
             and value['event-count'] == len(events), 'declared event count differs')
    fingerprint = validate_events(events)
    _require(_json_size(reply)+1 <= MAX_REPLY, 'normalized matching response too large')
    return (id(reply), tuple(reply), id(value), tuple(value), reply['id'],
            tuple((key, value[key]) for key in value if key != 'events'), fingerprint)


def decode_packet(line):
    """A command-local decoder; unrelated QMP commands retain their policy."""
    _require(0 < len(line) <= MAX_REPLY and line.isascii() and b'\0' not in line,
             'non-ASCII or oversized wire packet')
    # Bound nesting before the standard JSON decoder can allocate containers.
    depth, quoted, escaped = 0, False, False
    for byte in line:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            _require(depth <= 11, 'wire nesting exceeds envelope/event depth')
        elif byte in (93, 125):
            depth -= 1
            _require(depth >= 0, 'unbalanced wire container')
    _require(depth == 0 and not quoted, 'unfinished wire packet')
    def pairs(values):
        _require(len(values) <= 64, 'wire object exceeds member bound')
        result = {}
        for key, value in values:
            _ascii(key, 128)
            _require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def integer(text):
        _require(len(text) <= 20, 'oversized integer token')
        value = int(text)
        _require(-(1 << 63) <= value < 1 << 64, 'integer token outside int64/uint64')
        return value
    def floating(text):
        raise DebuggerError('Pending QMP events: floats and nonfinite values are not admitted')
    value = json.loads(line, object_pairs_hook=pairs, parse_int=integer,
                       parse_float=floating, parse_constant=floating)
    _require(type(value) is dict, 'wire top level is not an object')
    return value


class PendingReply:
    """Original admission, handler, response objects and finite receive budget."""
    def __init__(self, client, admission, request_id, deadline):
        self.client, self.admission = client, admission
        self.request_id, self.deadline = request_id, deadline
        self.handler = admission.event
        self.handler_binding = _binding(self.handler)
        self.owner = getattr(client, '_frame_read_owner', None)
        self.authority = admission.authority
        self.vm = getattr(self.authority, 'vm', None)
        self.revision = getattr(self.vm, 'session_revision', None)
        self.authority_lifetime = getattr(self.authority, 'lifetime', None)
        self.channel = admission.channel
        self.lock = client.lock
        self.monitor_binding = getattr(client, '_pending_event_monitor', None)
        self.buffer = client.buffer
        _require(type(self.buffer) is bytearray, 'unexpected receive buffer')
        self.buffer_bytes = bytes(self.buffer)
        self.wire_bytes = len(self.buffer)
        _require(self.wire_bytes <= MAX_WIRE, 'initial buffered wire exceeds 512 KiB')
        self.reply = self.fingerprint = self.snapshot = None
        self.raw_packet = None
        self.received_chunk = None
        self.native_error = False
        self.counts = dict(request_id=request_id, stage='before-dispatch',
            bare_callbacks_started=0, bare_callbacks_returned=0,
            batch_callbacks_started=0, batch_callbacks_returned=0,
            bare_wire_bytes=0, declared_count=None, validated_count=0)
        self.check()

    def check(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Pending QMP events exceeded their original deadline')
        if self.owner is not None:
            self.owner.check_owner()
            _require(getattr(self.client, '_frame_read_owner', None) is self.owner,
                     'captured read owner changed')
        _require(getattr(self.client, '_observation_authority', None) is self.authority,
                 'transport authority changed')
        _require(self.client.lock is self.lock, 'original protocol lock changed')
        if self.authority is not None:
            _require(self.authority.vm is self.vm
                     and self.vm.observation_authority is self.authority
                     and self.vm.session_revision is self.revision
                     and self.authority.lifetime == self.authority_lifetime,
                     'original revision authority changed')
        _require(self.client.socket is self.channel, 'original protocol channel changed')
        _require(all(left is right for left, right in
                     zip(_binding(self.admission.event), self.handler_binding)),
                 'original event handler changed')
        _require(self.client.buffer is self.buffer and bytes(self.buffer) == self.buffer_bytes,
                 'receive buffer changed outside bounded framing')
        _require(getattr(self.client, '_pending_event_monitor', None) is self.monitor_binding,
                 'native monitor binding changed')
        if self.reply is not None:
            _require(self.admission.reply is self.reply
                     and validate_reply(self.reply, self.request_id) == self.fingerprint,
                     'matching response or retained objects changed')

    def read(self):
        from .qemu_observation_authority import check_transport
        self.counts['stage'] = 'receive'
        self.check()
        while b'\n' not in self.buffer:
            remaining = MAX_WIRE-self.wire_bytes
            _require(remaining > 0 and len(self.buffer) < MAX_REPLY, 'incoming wire or line budget exhausted')
            channel = check_transport(self.client)
            self.check()
            channel.settimeout(self.deadline-time.monotonic())
            self.check()
            chunk = channel.recv(min(65536, remaining))
            _require(type(chunk) is bytes and 0 < len(chunk) <= remaining, 'closed or over-budget receive')
            self.wire_bytes += len(chunk)
            # A bounded read may arrive after its deadline or trigger an owner
            # callback. Retain its bytes as evidence without touching a current
            # replacement buffer or delivering an event from that failed read.
            self.received_chunk = chunk
            self.check()
            self.buffer.extend(chunk)
            self.buffer_bytes = bytes(self.buffer)
            self.check()
        line, _, rest = self.buffer.partition(b'\n')
        wire_size = len(line)+1
        _require(wire_size <= MAX_REPLY, 'actual packet line exceeds 256 KiB')
        self.client.buffer = self.buffer = bytearray(rest)
        self.buffer_bytes = bytes(rest)
        self.raw_packet = bytes(line)
        value = decode_packet(bytes(line))
        self.check()
        return value, wire_size

    def bare(self, event, wire_size):
        self.counts['stage'] = 'bare-event'
        _require(self.counts['bare_callbacks_started'] < 64, 'bare-event count exceeds 64')
        self.counts['bare_wire_bytes'] += wire_size
        _require(self.counts['bare_wire_bytes'] <= MAX_REPLY, 'bare-event wire exceeds 256 KiB')
        values = [event]
        fingerprint = validate_events(values)
        self.check()
        self.counts['bare_callbacks_started'] += 1
        self.handler(event)
        self.counts['bare_callbacks_returned'] += 1
        self.check()
        _require(validate_events(values) == fingerprint, 'bare event changed during its callback')

    def deliver(self, reply):
        self.counts['stage'] = 'whole-batch-validation'
        # Set the full response before validation so bounded malformed replies
        # remain transport evidence; do not snapshot an unvalidated structure.
        self.admission.reply = reply
        fingerprint = validate_reply(reply, self.request_id)
        value = reply['return']
        self.counts['declared_count'] = value['event-count']
        self.counts['validated_count'] = len(value['events'])
        binding = (value['monitor-id'], value['monitor-epoch'])
        _require(self.monitor_binding is None or self.monitor_binding == binding,
                 'producer monitor lifetime changed')
        if self.monitor_binding is None:
            self.monitor_binding = binding
            self.client._pending_event_monitor = binding
        self.reply, self.fingerprint = reply, fingerprint
        self.snapshot = deepcopy(reply)
        self.check()
        self.counts['stage'] = 'retained-callbacks'
        for event in value['events']:
            self.check()
            self.counts['batch_callbacks_started'] += 1
            self.handler(event)
            self.counts['batch_callbacks_returned'] += 1
            self.check()
        self.counts['stage'] = 'complete'
        self.check()
        return value

    def error_reply(self, reply):
        _require(set(reply) == {'id', 'error'}
                 and _integer(reply['id'], 1, (1 << 64)-1) and reply['id'] == self.request_id,
                 'native error envelope or ID differs')
        error = reply['error']
        _require(type(error) is dict and set(error) == {'class', 'desc'}, 'native error shape differs')
        _ascii(error['class'], 128, nonempty=True)
        _ascii(error['desc'], 4096)
        self.admission.reply = reply
        self.snapshot = deepcopy(reply)
        self.check()
        self.native_error = True
        raise DebuggerError('QMP '+COMMAND+': '+error['class']+': '+error['desc'])

    def attach(self, error):
        # No access/copy of callback-mutated packet data. Preserve even falsey
        # exception objects and the already-validated bounded pre-callback view.
        try:
            error.pending_events = dict(self.counts, wire_bytes=self.wire_bytes,
                validated_reply=deepcopy(self.snapshot), raw_packet=self.raw_packet,
                last_received_chunk=self.received_chunk)
        except BaseException:
            pass

    def close_original(self):
        if self.owner is not None:
            self.owner.close()
            return
        if self.authority is not None:
            self.authority.invalidate('uncertain pending-event reply')
        if self.revision is not None:
            self.revision.effect()
        try:
            if self.channel is not None:
                self.channel.close()
        finally:
            if self.client.socket is self.channel:
                self.client.socket = None


def take_pending_events(session, vm, *, expected_state=None):
    if not supported(vm):
        return None
    owner = getattr(vm, '_frame_read_owner', None)
    _require(owner is not None and owner.session is session, 'cut lacks its captured original read owner')
    owner.check_owner()
    _require(not getattr(owner, 'pending_cut_started', False), 'one read cannot take a second cut')
    owner.pending_cut_started = True
    value = owner.cleanup_owner['qmp'].call(COMMAND,
        timeout_ms=max(1, min(600000, int((owner.deadline-time.monotonic())*1000))),
        max_reply_bytes=MAX_REPLY)
    owner.check_owner()
    owner.pending_cut = deepcopy(value)
    if expected_state is not None and value['status'] != expected_state:
        error = DebuggerError('Pending QMP events: cut state disagrees with original status')
        error.pending_cut = deepcopy(value)
        try:
            owner.close()
        except BaseException as cleanup:
            error.pending_events_cleanup_error = type(cleanup).__name__
        raise error
    return value


class StatusReadOwner(FrameReadOwner):
    """Status uses the same retained resources, with an explicit DOS transition.

    Only the nonce/serial/memory-verified return path may declare its predicted
    epoch transition. No state is opportunistically rebased after a callback.
    """
    status_scope = True

    def __init__(self, session, vm, deadline, *, dos):
        super().__init__(session, vm, deadline)
        self.dos = dos
        self.base_entered = False
        self.async_context = getattr(session, '_dos_async_pending', None) if dos else None
        self.deferred = (self.async_context is not None and self.async_context['dispatched'])
        self.native = None
        self.return_state = self.closed_state = None
        self.return_complete = False
        self.allow_closed = self.legitimate_closed = False
        self.helper_identity = None
        if self.async_context is not None:
            context = self.async_context
            self.helper_identity = dict(ready=deepcopy(context['ready']),
                ready_bytes=context['ready_bytes'], nonce=context['nonce'],
                helper=context['helper'], serial=context['serial'], run=context['run'])

    def _helper_current(self):
        if self.helper_identity is None:
            return
        value, session = self.helper_identity, self.session
        _require(session._ready == value['ready'] and session._ready_bytes == value['ready_bytes']
                 and session._nonce == value['nonce'] and session._helper == value['helper']
                 and session._channel is value['serial'] and session.run_id == value['run'],
                 'original DOS helper, serial or launch identity changed')

    def state_matches(self):
        from .qemu_observation_authority import _state
        current = _state(self.session, self.vm)
        return current == self.state or self.allow_closed and current == self.closed_state

    def _closed_bindings_match(self):
        vm, saved = self.vm, self.cleanup_owner
        if (self.session.vm is not vm or getattr(vm, 'context', None) is not self.context
                or getattr(self.session, 'project', None) is not self.project
                or getattr(self.session, '_process', None) is not self.context_process
                or getattr(vm, 'observation_authority', None) is not self.authority
                or getattr(vm, 'session_revision', None) is not self.revision
                or self.authority.vm is not vm or self.authority.lifetime != self.lifetime
                or self.revision.session_id != self.session_id or vm.lock is not self.lock
                or getattr(vm, 'process', None) is not saved['process']
                or getattr(self.session, '_frame_read_session_owner', None) is not self
                or getattr(vm, '_frame_read_owner', None) is not self
                or getattr(vm, 'transport', None) != self.transport
                or getattr(vm, 'qmp_commands', None) is not self.commands
                or frozenset(self.commands or ()) != self.command_values):
            return False
        for name, client, channel in self.clients:
            current = getattr(vm, name, None)
            if current is not None and current is not client:
                return False
            if client is not None and (getattr(client, 'socket', None) is not None
                    or getattr(client, '_observation_authority', None) is not self.authority
                    or getattr(client, '_frame_read_owner', None) is not self):
                return False
        for attribute, key in (('temporary', 'temporary'), ('_qemu_image_proof', 'qemu_image_proof'),
                               ('close_observer', 'close_observer')):
            value = getattr(vm, attribute, None)
            if value is not None and value is not saved[key]:
                return False
        return not getattr(vm, '_channels', ()) and getattr(vm, '_admission_guest_pidfd', None) is None

    def check_owner(self):
        self._helper_current()
        if not self.legitimate_closed:
            return super().check_owner()
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Closed DOS status exceeded its original deadline')
        _require(self._closed_bindings_match(), 'closed DOS return replaced an original resource or authority')
        from .qemu_observation_authority import _state
        current = _state(self.session, self.vm)
        omitted = {'gdb_architecture', 'gdb_register_description', 'temporary'}
        _require(all(current[key] == value for key, value in self.closed_state.items()
                     if key not in omitted), 'closed DOS return changed its declared state')
        return self

    def observe_native(self, state):
        self.check_owner()
        _require(type(state) is dict and type(state.get('running')) is bool,
                 'status lacks an exact native running boolean')
        self.native = deepcopy(state)

    def verified_return(self, context, report, raw, serial_bytes):
        self.check_owner()
        _require(self.deferred and context is self.async_context and context.get('reconciling') is True
                 and getattr(self.session, '_dos_async_pending', None) is context
                 and self.return_state is None and raw == serial_bytes
                 and type(raw) is bytes and report.get('type') == 'terminated',
                 'DOS cut lacks the original one-use verified return')
        # The caller has already parsed both complete nonce-bound reports and
        # checked every ready identity, MCB and vector read. Bind that exact
        # transition before the production epoch/classification assignments.
        epoch = getattr(self.session, '_epoch_number', 1)
        _require(type(epoch) is int and epoch >= 1, 'DOS epoch counter shape changed')
        run = self.session.run_id or self.session._runtime_epoch.split(':', 1)[0]
        expected = deepcopy(self.state)
        expected['runtime_epoch'] = run+':process:'+str(epoch+1)
        expected['process']['capture_epoch'] = expected['runtime_epoch']
        expected['process']['state'] = 'resident' if report['dos_result'] >> 8 == 3 else 'exited'
        self.return_state = expected
        self.return_epoch_number = epoch+1

    def accept_return_state(self):
        from .qemu_observation_authority import _state
        _require(self.return_state is not None and _state(self.session, self.vm) == self.return_state,
                 'verified DOS return did not make its exact declared transition')
        self.state = self.return_state
        self.check_owner()

    def permit_closed_return(self):
        self.check_owner()
        _require(self.return_state is not None and not self.allow_closed,
                 'closed return lacks its one-use verified transition')
        expected = deepcopy(self.state)
        run = self.session.run_id or self.session._runtime_epoch.split(':', 1)[0]
        expected['runtime_epoch'] = run+':process:'+str(self.return_epoch_number+1)
        expected['process']['capture_epoch'] = expected['runtime_epoch']
        expected['process']['machine_closed'] = True
        self.closed_state = expected
        self.allow_closed = True

    def complete_return(self, context, result):
        self.check_owner()
        _require(context is self.async_context and self.return_state is not None
                 and result.get('outcome') in ('guest_exit', 'guest_tsr')
                 and not self.return_complete, 'DOS return proof changed or was reused')
        _require((result['session']['state'] == 'closed') == self.legitimate_closed,
                 'DOS closed-return proof differs from actual captured cleanup')
        self.return_complete = True

    def close(self):
        if not self.allow_closed or self.closed:
            return super().close()
        self.check_owner()
        from .qemu_observation_authority import _state
        _require(_state(self.session, self.vm) == self.closed_state,
                 'legitimate DOS close lacks its exact expected state')
        self.state = self.closed_state
        self.closed = self.closing = True
        self.legitimate_closed = True
        try:
            self.authority.invalidate('verified DOS closed return')
            self.revision.effect()
            self.original_close()
            self.close_resources()
        finally:
            self.closing = False
        if self.cleanup_errors:
            raise DebuggerError('Verified DOS return cleanup failed: '+','.join(self.cleanup_errors))

    def finalize(self, result):
        self.check_owner()
        _require(type(result) is dict and self.native is not None, 'status did not retain its original native evidence')
        _require(result.get('native_state') == self.native, 'status native evidence changed during projection')
        if self.legitimate_closed:
            _require(self.return_complete and result.get('state') == 'closed', 'closed status lacks completed return proof')
        elif (not self.native['running'] and self.native.get('status') in STATES
              and (not self.deferred or self.return_complete)):
            take_pending_events(self.session, self.vm, expected_state=self.native['status'])
            self.check_owner()
            result['pending_events'] = {key: value for key, value in self.pending_cut.items() if key != 'events'}
        final_revision = self.admit()
        self.check()
        result.update(final_revision)
        self.check()
        return result


def pending_status_owner(session):
    value = getattr(session, '_frame_read_session_owner', None)
    if isinstance(value, StatusReadOwner):
        value.check_owner()
        return value
    return None


def pending_status_operation(function, *, dos=False):
    @wraps(function)
    def invoke(session, *args, **kwargs):
        from .qemu_frame_read import check_frame_read_session
        check_frame_read_session(session)
        existing = getattr(session, '_frame_read_session_owner', None)
        if existing is not None:
            _require(isinstance(existing, StatusReadOwner) and existing.dos and not dos
                     and not existing.base_entered, 'reentrant status cannot replace its original scope')
            existing.base_entered = True
            return function(session, *args, **kwargs)
        vm = session.vm
        if not supported(vm):
            return function(session, *args, **kwargs)
        limits = [time.monotonic()+30]
        limits.extend(getattr(session, name, None) for name in ('_rpc_deadline', '_deadline'))
        limits.extend(getattr(target, 'operation_deadline', None)
                      for target in (vm, getattr(vm, 'qmp', None), getattr(vm, 'gdb', None)))
        owner = StatusReadOwner(session, vm, min(value for value in limits if value is not None), dos=dos)
        if not owner.install():
            return function(session, *args, **kwargs)
        locked, installed, result = False, [], None
        primary = completion = None
        try:
            remaining = owner.deadline-time.monotonic()
            if remaining <= 0 or not owner.lock.acquire(timeout=min(10, remaining)):
                raise TimeoutError('Pending status deadline expired waiting for its original owner')
            locked = True
            owner.check_owner()
            for target, attribute in [(session, '_deadline'), (vm, 'operation_deadline'),
                    *((client, 'operation_deadline') for _, client, _ in owner.clients if client is not None)]:
                owner.check_owner()
                old = getattr(target, attribute, None)
                installed.append((target, attribute, old))
                setattr(target, attribute, owner.deadline if old is None else min(owner.deadline, old))
                owner.check_owner()
            owner.started = True
            result = function(session, *args, **kwargs)
            owner.check_owner()
            return owner.finalize(result)
        except BaseException as error:
            primary = error
            raise
        finally:
            for target, attribute, previous in installed:
                try:
                    # Only captured resources receive restoration writes. A
                    # replaced authority/client gets no lookup or setter call.
                    if target is session or target is vm or owner.restore_channel(target):
                        setattr(target, attribute, previous)
                    if primary is None and completion is None:
                        owner.check_owner()
                except BaseException as error:
                    if primary is None and completion is None:
                        completion = error
            if locked:
                try:owner.lock.release()
                except BaseException as error:
                    if primary is None and completion is None:completion = error
            owner.finish(primary if primary is not None else completion, result)
            if primary is None and completion is not None:
                raise completion
    return invoke
