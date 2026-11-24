"""A cooperative Python control fence, never a native machine-state revision.

Only bound protocol methods and admitted public operations participate. Raw
socket/descriptor use, independent controllers and native/device mutations are
explicitly outside this authority. One observation holds the existing VM lock.
"""
from __future__ import annotations
from .qemu_ram import low_ram_end

from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import Path
import re
import threading
import time
import uuid

from .dosbox_rpc import DebuggerError


_UNSET = object()
_QMP_QUERIES = frozenset({'query-status', 'query-replay', 'x-fdisbull-query-clock',
    'x-fdisbull-query-video-frame', 'x-fdisbull-query-frame-keys',
    'x-fdisbull-query-frame-key-repeat', 'x-fdisbull-query-input'})
_EXPORT_NAME = re.compile(r'video-frame-[0-9a-f]{32}\.ppm\Z')
_REPLY_LIMIT = 128 * 1024


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Observation control deadline expired before dispatch')
    return remaining


def _channel_live(channel):
    if channel is None or getattr(channel, 'closed', False):
        return False
    fileno = getattr(channel, 'fileno', None)
    return fileno is None or fileno() >= 0


def _state(context, vm):
    process = getattr(context, '_process', None) or {}
    metadata = getattr(context, 'metadata', None) or {}
    version = getattr(context, 'version', None) or {}
    return deepcopy(dict(run=getattr(context, 'run_id', None),
        runtime_epoch=getattr(context, '_runtime_epoch', None),
        checkpoint_epoch=getattr(context, '_checkpoint_epoch', None),
        process={key: process.get(key) for key in
                 ('capture_epoch', 'psp_segment', 'state', 'machine_closed')},
        version=version.get('id'),
        source_sha256=metadata.get('source_sha256'),
        version_sha256=metadata.get('version_sha256'),
        gdb_architecture=getattr(getattr(vm, 'gdb', None), 'architecture', None),
        gdb_register_description=getattr(getattr(vm, 'gdb', None), 'register_description', None),
        configuration=getattr(vm, 'machine_configuration', None),
        temporary=getattr(getattr(vm, 'temporary', None), 'name', None)))


def _ranges(vm, values):
    if type(values) not in (tuple, list) or len(values) > 64:
        raise ValueError('Observation RAM ranges must be a bounded sequence')
    ram_end = low_ram_end(getattr(vm, 'machine_configuration', {}))
    result = []
    total = 0
    for value in values:
        if type(value) is dict and set(value) == {'address', 'length'}:
            address, length = value['address'], value['length']
        elif type(value) in (tuple, list) and len(value) == 2:
            address, length = value
        else:
            raise ValueError('Observation RAM range requires address and length')
        if (type(address) is not int or type(length) is not int or not 1 <= length <= 65536
                or not (0 <= address < address + length <= 0xa0000
                        or 0x100000 <= address < address + length <= ram_end)):
            raise ValueError('Observation range must name ordinary conventional or extended PC RAM')
        total += length
        if total > 65536:
            raise ValueError('Observation selected RAM exceeds 65536 bytes')
        result.append((address, length))
    return tuple(result)


class ObservationLease:
    def __init__(self, authority, context, deadline, ram_ranges, native_control_token=None):
        self.authority, self.context = authority, context
        self.vm, self.deadline = authority.vm, deadline
        self.ram_ranges = _ranges(self.vm, ram_ranges)
        self.native_control_token = native_control_token
        self.generation = authority.control_generation
        self.identities = (self.vm.lock, self.vm.process, self.vm.qmp, self.vm.gdb,
                           self.vm.qmp.socket, self.vm.gdb.socket,
                           getattr(context, 'project', None))
        self.state = _state(context, self.vm)
        process = self.vm.process
        self.cleanup_owner = dict(process=process, stdin=getattr(process, 'stdin', None),
            stdout=getattr(process, 'stdout', None), qmp=self.vm.qmp, qmp_socket=self.vm.qmp.socket,
            gdb=self.vm.gdb, gdb_socket=self.vm.gdb.socket,
            channels=tuple(getattr(self.vm, '_channels', ())), temporary=getattr(self.vm, 'temporary', None),
            qemu_image_proof=getattr(self.vm, '_qemu_image_proof', None),
            admission_guest_pidfd=getattr(self.vm, '_admission_guest_pidfd', None),
            close_observer=getattr(self.vm, 'close_observer', None), context=context,
            context_process=getattr(getattr(self.vm, 'context', None), '_process', None), closed=False)
        self.reason = None
        self.events = []
        self.ended = False
        self.completed = False
        self.final_generation = None
        self._export = None
        self._export_granted = False

    def _refuse(self, reason):
        if self.reason is None:
            self.reason = reason[:512]
        self.authority.invalidate(reason)
        raise DebuggerError('Observation authority invalidated: ' + self.reason)

    def check(self):
        if self.reason is not None:
            raise DebuggerError('Observation authority invalidated: ' + self.reason)
        if self.ended or self.authority._active is not self:
            self._refuse('observation lease is no longer active')
        try:
            _remaining(self.deadline)
        except TimeoutError:
            self.authority.invalidate('observation deadline expired')
            raise
        vm = self.vm
        if getattr(self.context, 'vm', None) is not vm:
            self._refuse('machine owner changed')
        current = (getattr(vm, 'lock', None), getattr(vm, 'process', None),
                   getattr(vm, 'qmp', None), getattr(vm, 'gdb', None),
                   getattr(getattr(vm, 'qmp', None), 'socket', None),
                   getattr(getattr(vm, 'gdb', None), 'socket', None),
                   getattr(self.context, 'project', None))
        if any(left is not right for left, right in zip(current, self.identities)):
            self._refuse('machine owner or transport identity changed')
        if (self.authority.control_generation != self.generation
                or self.authority._qmp is not vm.qmp or self.authority._gdb is not vm.gdb
                or self.authority._qmp_socket is not vm.qmp.socket
                or self.authority._gdb_socket is not vm.gdb.socket
                or getattr(vm.qmp, '_observation_authority', None) is not self.authority
                or getattr(vm.gdb, '_observation_authority', None) is not self.authority):
            self._refuse('covered control generation or binding changed')
        if (getattr(self.context, '_closed', False) or getattr(vm, 'closed', False)
                or getattr(vm, '_fdisbull_control_quarantine', None)
                or vm.process.poll() is not None
                or not _channel_live(vm.qmp.socket) or not _channel_live(vm.gdb.socket)):
            self._refuse('machine or transport is closed, exited or quarantined')
        if _state(self.context, vm) != self.state:
            self._refuse('configuration or session lifetime changed')
        return self

    def authorize_export(self, token, frame_id, *, directory):
        self.check()
        if (self._export_granted or type(token) is not str or not token
                or type(frame_id) is not int or frame_id < 1
                or not isinstance(directory, (str, Path))):
            self._refuse('invalid or repeated source export grant')
        target = Path(directory)
        owned = self.state['temporary']
        if (owned is None or not target.is_absolute() or str(target) != str(Path(owned))
                or target.is_symlink() or not target.is_dir()):
            self._refuse('source export directory is not the captured owned directory')
        self._export = (token, frame_id, target)
        self._export_granted = True

    def _export_allowed(self, arguments):
        if (self._export is None or type(arguments) is not dict
                or set(arguments) != {'token', 'frame-id', 'filename'}):
            return False
        token, frame_id, directory = self._export
        filename = arguments['filename']
        if (type(filename) is not str or type(arguments['token']) is not str
                or type(arguments['frame-id']) is not int
                or arguments['token'] != token or arguments['frame-id'] != frame_id):
            return False
        path = Path(filename)
        if (not path.is_absolute() or path.parent != directory
                or not _EXPORT_NAME.fullmatch(path.name) or path.exists() or path.is_symlink()
                or directory.is_symlink() or not directory.is_dir()):
            return False
        self._export = None
        return True

    def receipt(self):
        return dict(format='fdisbull-qemu-observation-authority-1',
            scope='cooperative-owner-control', owner_lifetime=self.authority.lifetime,
            control_generation_before=self.generation,
            control_generation_after=(self.authority.control_generation if self.final_generation is None
                                      else self.final_generation),
            valid=self.reason is None, complete=self.completed and self.reason is None,
            invalidation_reason=self.reason, events=deepcopy(self.events),
            atomic=False, native_state_revision=None, whole_machine_state_revision=None,
            coverage=dict(bound_python_protocol_dispatch=True,
                          admitted_public_operations=True, raw_handles=False,
                          independent_controllers=False, native_device_mutations=False),
            selected_ram=[dict(address=address, length=length) for address, length in self.ram_ranges])


class _Admission:
    def __init__(self, authority, client, protocol, operation, arguments, deadline):
        self.authority, self.client = authority, client
        self.protocol, self.operation = protocol, operation
        self.arguments, self.deadline = arguments, deadline
        self.channel = getattr(client, 'socket', None)
        self.reply = None
        self.dispatched = False
        self.passive = False
        self.expected = None
        self.max_reply_bytes = _REPLY_LIMIT if authority is not None and authority._active else None

    def dispatch(self):
        from .qemu_frame_read import check_frame_read_client
        check_frame_read_client(self.client)
        _remaining(self.deadline)
        authority = self.authority
        if authority is None:
            return
        authority._current_client(self.client, self.protocol)
        if authority._active is not None:
            authority._active.check()
        elif not self.passive and not self.dispatched:
            authority.invalidate('potential effect: ' + self.protocol + ' ' + str(self.operation)[:96])
        if not self.dispatched:
            from .qemu_session_revision import passive_dispatch, session_revision
            if not passive_dispatch(authority.vm, self, authority._stack):
                session_revision(authority.vm).effect()
        self.dispatched = True

    def event(self, value):
        from .qemu_frame_read import check_frame_read_client
        check_frame_read_client(self.client)
        if self.authority is not None:
            from .qemu_session_revision import session_revision
            session_revision(self.authority.vm).effect()
        if self.authority is not None and self.authority._active is not None:
            lease = self.authority._active
            lease.events.append(deepcopy(value))
            lease._refuse('QMP event during stopped observation')


class ObservationAuthority:
    def __init__(self, vm):
        from .qemu_session_revision import session_revision
        self.vm = vm
        session_revision(vm)
        self.lifetime = uuid.uuid4().hex
        self.control_generation = 0
        self._qmp = self._gdb = None
        self._qmp_socket = self._gdb_socket = None
        self._active = None
        self._cleanup_owner = None
        self._stack = []
        self._state_lock = threading.RLock()

    def invalidate(self, reason):
        """Cleanup must always be allowed and never replace its primary error."""
        with self._state_lock:
            self.control_generation += 1
            if self._active is not None and self._active.reason is None:
                self._active.reason = reason[:512] if type(reason) is str else 'control invalidated'

    def public_operation(self, name):
        if self._active is not None:
            self._active._refuse('reentrant public operation: ' + str(name)[:96])
        # This is deliberately conservative, including host-only bookkeeping.
        # It is a control admission generation, not a guest mutation count.
        self.invalidate('public operation: ' + str(name)[:96])

    def bind(self, *, qmp=_UNSET, gdb=_UNSET):
        with self.vm.lock:
            if self._active is not None:
                self._active._refuse('transport binding changed during observation')
            for name, client in (('qmp', qmp), ('gdb', gdb)):
                if client is _UNSET:
                    continue
                if client is not None:
                    owner = getattr(client, '_observation_authority', None)
                    if owner is not None and owner is not self:
                        raise DebuggerError('Protocol client belongs to another observation owner')
                    if getattr(self.vm, name, None) is not client:
                        raise DebuggerError('Protocol client is not installed on this machine owner')
                channel = getattr(client, 'socket', None)
                if (getattr(self, '_' + name) is not client
                        or getattr(self, '_' + name + '_socket') is not channel):
                    self.invalidate('transport binding: ' + name)
                    from .qemu_session_revision import session_revision
                    session_revision(self.vm).effect()
                    setattr(self, '_' + name, client)
                    setattr(self, '_' + name + '_socket', channel)
                if client is not None:
                    client._observation_authority = self
        return self

    def original_channel(self, client):
        captured = self._cleanup_owner
        if captured is not None:
            for name in ('qmp', 'gdb'):
                if captured[name] is client:
                    return captured[name + '_socket']
        return getattr(client, 'socket', None)

    def _current_client(self, client, protocol):
        name = 'qmp' if protocol == 'qmp' else 'gdb'
        if (getattr(self, '_' + name) is not client or getattr(self.vm, name, None) is not client
                or getattr(client, '_observation_authority', None) is not self
                or getattr(self, '_' + name + '_socket') is not getattr(client, 'socket', None)
                or not _channel_live(getattr(client, 'socket', None))):
            self.invalidate('bound protocol owner or channel changed')
            raise DebuggerError('Observation protocol owner or channel changed')

    @contextmanager
    def observe(self, context, *, deadline, ram_ranges=(), native_control_token=None):
        from .qemu_stopped_control import validate_native_control_token
        validate_native_control_token(native_control_token)
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError('Observation requires a finite absolute deadline')
        limits = [deadline]
        for owner in (self.vm, self._qmp, self._gdb):
            bound = getattr(owner, 'operation_deadline', None)
            if bound is not None:
                limits.append(bound)
        deadline = min(limits)
        lock = self.vm.lock
        if not lock.acquire(timeout=_remaining(deadline)):
            raise TimeoutError('Observation deadline expired waiting for its owner')
        lease = None
        try:
            if self.vm.lock is not lock:
                self.invalidate('machine lock changed during observation admission')
                raise DebuggerError('Observation machine lock changed during admission')
            if self._active is not None:
                self._active._refuse('reentrant observation')
            if self._cleanup_owner is not None:
                raise DebuggerError('Observation owner retains a failed lease; original-owner cleanup is required')
            if self._stack:
                raise DebuggerError('Observation cannot begin inside a protocol operation')
            vm = self.vm
            if (getattr(context, 'vm', None) is not vm or vm.process is None
                    or self._qmp is None or self._gdb is None
                    or vm.qmp is not self._qmp or vm.gdb is not self._gdb
                    or not _channel_live(getattr(self._qmp, 'socket', None))
                    or not _channel_live(getattr(self._gdb, 'socket', None))):
                raise DebuggerError('Observation requires its original owner and existing live QMP/GDB channels')
            self._current_client(self._qmp, 'qmp')
            self._current_client(self._gdb, 'gdb-request')
            lease = ObservationLease(self, context, deadline, ram_ranges, native_control_token)
            self._active = lease
            self._cleanup_owner = lease.cleanup_owner
            try:
                lease.check()
                yield lease
                lease.check()
                lease.completed = True
                self._cleanup_owner = None
            except BaseException as error:
                expected = getattr(error, 'observation_refusal', False) is True
                if expected:
                    try:
                        lease.check()
                    except BaseException as invalid:
                        invalid.observation_authority = lease.receipt()
                        raise invalid from error
                    # A verified passive bracket may report unsupported input
                    # or profile evidence without poisoning its healthy owner.
                    self._cleanup_owner = None
                elif lease.reason is None:
                    self.invalidate('observation failed: ' + type(error).__name__)
                error.observation_authority = lease.receipt()
                raise
        finally:
            if lease is not None:
                lease.final_generation = self.control_generation
                lease.ended = True
                if self._active is lease:
                    self._active = None
            lock.release()

    def _passive(self, admission):
        protocol, operation, arguments = admission.protocol, admission.operation, admission.arguments
        lease = self._active
        if protocol == 'qmp':
            if type(operation) is not str:
                return False
            if operation in _QMP_QUERIES:
                return arguments is None or type(arguments) is dict and not arguments
            if operation == 'x-fdisbull-query-stopped-control':
                return (lease is not None and lease.native_control_token is not None
                        and type(arguments) is dict and set(arguments) == {'token'}
                        and type(arguments['token']) is str
                        and arguments['token'] == lease.native_control_token)
            if operation == 'human-monitor-command':
                return (type(arguments) is dict and set(arguments) == {'command-line'}
                        and type(arguments['command-line']) is str
                        and arguments['command-line'] == 'info registers')
            return (lease is not None and operation == 'x-fdisbull-export-video-frame'
                    and lease._export_allowed(arguments))
        if protocol == 'gdb-memory':
            if lease is None:
                return False
            address, length, space, write = arguments
            return (not write and space == 'physical'
                    and any(start <= address < address + length <= start + count
                            for start, count in lease.ram_ranges))
        if protocol == 'gdb-request':
            if self._stack and self._stack[-1].protocol == 'gdb-memory':
                parent = self._stack[-1]
                if parent.expected != operation:
                    return False
                if lease is None:
                    return True
                if operation in (b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:0', b'Qqemu.PhyMemMode:1'):
                    return True
                match = re.fullmatch(rb'm([0-9a-f]+),([0-9a-f]+)', operation)
                if match is None:
                    return False
                address, length = (int(value, 16) for value in match.groups())
                start, count, space, write = parent.arguments
                return not write and space == 'physical' and start <= address < address + length <= start + count
            return operation == b'g'
        return False

    @contextmanager
    def protocol(self, client, protocol, operation, arguments, deadline):
        limits = [deadline]
        bound = getattr(self.vm, 'operation_deadline', None)
        if bound is not None:
            limits.append(bound)
        if self._active is not None:
            limits.append(self._active.deadline)
        deadline = min(limits)
        lock = self.vm.lock
        if not lock.acquire(timeout=_remaining(deadline)):
            raise TimeoutError('Observation control deadline expired waiting for its owner')
        admission = None
        try:
            if self.vm.lock is not lock:
                self.invalidate('machine lock changed during protocol admission')
                raise DebuggerError('Observation machine lock changed during protocol admission')
            self._current_client(client, protocol)
            lease = self._active
            if lease is not None:
                lease.check()
                nested_memory = (self._stack and self._stack[-1].protocol == 'gdb-memory'
                    and self._stack[-1].client is client and protocol == 'gdb-request'
                    and self._stack[-1].expected == operation)
                if self._stack and not nested_memory:
                    lease._refuse('reentrant protocol operation')
            elif protocol == 'qmp' and any(item.client is client for item in self._stack):
                self.invalidate('reentrant QMP operation')
                raise DebuggerError('Reentrant QMP operation would deadlock its channel')
            owned = deepcopy(arguments) if protocol == 'qmp' else arguments
            admission = _Admission(self, client, protocol, operation, owned, deadline)
            admission.passive = self._passive(admission)
            if lease is not None and not admission.passive:
                lease._refuse('unadmitted protocol operation: ' + protocol + ' ' + str(operation)[:96])
            self._stack.append(admission)
            try:
                yield admission
                if lease is not None:
                    try:
                        lease.check()
                    except BaseException as error:
                        if admission.reply is not None:
                            error.observation_transport_reply = deepcopy(admission.reply)
                        raise
            except BaseException:
                if lease is not None and lease.reason is None:
                    self.invalidate('admitted protocol operation failed')
                raise
            finally:
                self._stack.pop()
        finally:
            lock.release()

    @contextmanager
    def memory_request(self, client, command):
        if (not self._stack or self._stack[-1].protocol != 'gdb-memory'
                or self._stack[-1].client is not client or self._stack[-1].expected is not None):
            if self._active is not None:
                self._active._refuse('memory exchange outside its admitted operation')
            raise DebuggerError('Memory exchange outside its admitted operation')
        parent = self._stack[-1]
        parent.expected = command.encode('ascii') if isinstance(command, str) else command
        try:
            yield
        finally:
            parent.expected = None

    def check_protocol(self, client):
        """Private framing/receive helpers require an admitted bound operation."""
        if not self._stack or self._stack[-1].client is not client:
            self.invalidate('unadmitted raw protocol helper')
            raise DebuggerError('Raw protocol helper requires an admitted owner operation')
        self._current_client(client, self._stack[-1].protocol)
        if self._active is not None:
            self._active.check()
        if getattr(client, 'socket', None) is not self._stack[-1].channel:
            self.invalidate('protocol channel changed during dispatch')
            raise DebuggerError('Protocol channel changed during dispatch')
        return self._stack[-1].channel


@contextmanager
def transport_operation(client, protocol, operation, arguments, deadline):
    from .qemu_frame_read import check_frame_read_client
    check_frame_read_client(client)
    authority = getattr(client, '_observation_authority', None)
    if authority is None:
        yield _Admission(None, client, protocol, operation, arguments, deadline)
    else:
        with authority.protocol(client, protocol, operation, arguments, deadline) as admission:
            yield admission


@contextmanager
def memory_request(client, command):
    from .qemu_frame_read import check_frame_read_client
    check_frame_read_client(client)
    authority = getattr(client, '_observation_authority', None)
    if authority is None:
        yield
    else:
        with authority.memory_request(client, command):
            yield


def check_transport(client):
    from .qemu_frame_read import check_frame_read_client
    check_frame_read_client(client)
    authority = getattr(client, '_observation_authority', None)
    if authority is not None:
        return authority.check_protocol(client)
    # Unbound protocol parsers may already hold a complete buffered reply.
    # A channel is required only if the parser actually performs I/O.
    return getattr(client, 'socket', None)


def reply_limit(client, limit):
    from .qemu_frame_read import check_frame_read_client
    check_frame_read_client(client)
    authority = getattr(client, '_observation_authority', None)
    return min(limit, _REPLY_LIMIT) if authority is not None and authority._active is not None else limit
