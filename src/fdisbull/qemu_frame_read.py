"""One captured owner and explicit admission for a retained source read.

This is independent of the strict ObservationLease. Cooperating effects before
admission may become the new read's baseline; every effect after it still
invalidates the read. The scope never drains events or issues native requests.
"""
from copy import deepcopy
import time

from .dosbox_rpc import DebuggerError


READ_OPERATIONS = frozenset({'frame_probe', 'frame_rgba', '_frame_screenshot',
                             'capture_video_frame'})


class FrameReadOwner:
    def __init__(self, session, vm, deadline):
        from .qemu_observation_authority import ObservationAuthority, _state
        from .qemu_session_revision import SessionRevision
        self.session, self.vm, self.deadline = session, vm, deadline
        self.authority = getattr(vm, 'observation_authority', None)
        self.revision = getattr(vm, 'session_revision', None)
        if (not isinstance(self.authority, ObservationAuthority)
                or not isinstance(self.revision, SessionRevision)):
            raise ValueError('Retained frame reads require their existing owner authorities')
        self.lifetime = self.authority.lifetime
        self.session_id = self.revision.session_id
        self.lock = vm.lock
        self.project = getattr(session, 'project', None)
        self.context = getattr(vm, 'context', None)
        self.context_process = getattr(session, '_process', None)
        self.state = _state(session, vm)
        self.original_close = vm.close
        process = getattr(vm, 'process', None)
        self.cleanup_owner = dict(process=process,
            stdin=getattr(process, 'stdin', None), stdout=getattr(process, 'stdout', None),
            channels=tuple(getattr(vm, '_channels', ())),
            temporary=getattr(vm, 'temporary', None),
            qemu_image_proof=getattr(vm, '_qemu_image_proof', None),
            admission_guest_pidfd=getattr(vm, '_admission_guest_pidfd', None),
            close_observer=getattr(vm, 'close_observer', None), context=session,
            context_process=self.context_process, frame_read=self, closed=False)
        self.clients = []
        for name in ('qmp', 'gdb'):
            client = getattr(vm, name, None)
            channel = getattr(client, 'socket', None)
            self.cleanup_owner[name] = client
            self.cleanup_owner[name + '_socket'] = channel
            self.clients.append((name, client, channel))
        self.admission = None
        self.started = False
        self.installed = self.closed = self.closing = False
        self.closed_channels = set()
        self.closed_resources = set()
        self.cleanup_errors = []

    def install(self):
        # A strict lease keeps its own admission and cleanup policy. The
        # existing public-operation guard remains responsible for refusing it.
        if self.authority._active is not None or self.authority._cleanup_owner is not None:
            return False
        targets = [self.vm, *(client for _, client, _ in self.clients if client is not None)]
        if any(getattr(target, '_frame_read_owner', None) is not None for target in targets):
            raise DebuggerError('Retained frame owner already has an active or failed read')
        for target in targets:
            target._frame_read_owner = self
        self.installed = True
        self.check_owner()
        return True

    def resources_match(self):
        vm, saved = self.vm, self.cleanup_owner
        if (self.session.vm is not vm or getattr(vm, 'context', None) is not self.context
                or getattr(self.session, 'project', None) is not self.project
                or getattr(self.session, '_process', None) is not self.context_process
                or getattr(vm, 'observation_authority', None) is not self.authority
                or getattr(vm, 'session_revision', None) is not self.revision
                or self.authority.vm is not vm or self.authority.lifetime != self.lifetime
                or self.revision.session_id != self.session_id
                or getattr(vm, 'lock', None) is not self.lock):
            return False
        if self.installed and getattr(vm, '_frame_read_owner', None) is not self:
            return False
        for name, client, channel in self.clients:
            if client is None:
                if (name != 'gdb' or getattr(vm, name, None) is not None
                        or getattr(self.authority, '_' + name) is not None
                        or getattr(self.authority, '_' + name + '_socket') is not None):
                    return False
                continue
            if (channel is None or getattr(vm, name, None) is not client
                    or getattr(client, 'socket', None) is not channel
                    or getattr(client, '_observation_authority', None) is not self.authority
                    or getattr(self.authority, '_' + name) is not client
                    or getattr(self.authority, '_' + name + '_socket') is not channel):
                return False
            if self.installed and getattr(client, '_frame_read_owner', None) is not self:
                return False
        for attribute, key in (('process', 'process'), ('temporary', 'temporary'),
                ('_qemu_image_proof', 'qemu_image_proof'), ('close_observer', 'close_observer')):
            if getattr(vm, attribute, None) is not saved[key]:
                return False
        channels = tuple(getattr(vm, '_channels', ()))
        process = saved['process']
        return (len(channels) == len(saved['channels'])
            and all(left is right for left, right in zip(channels, saved['channels']))
            and getattr(vm, '_admission_guest_pidfd', None) == saved['admission_guest_pidfd']
            and getattr(process, 'stdin', None) is saved['stdin']
            and getattr(process, 'stdout', None) is saved['stdout'])

    def check_owner(self):
        from .qemu_observation_authority import _channel_live, _state
        if self.closed:
            raise DebuggerError('Retained frame original owner was closed')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Retained frame read exceeded its original host deadline')
        if not self.resources_match() or _state(self.session, self.vm) != self.state:
            raise DebuggerError('Session control or owner changed across the retained-frame read')
        process = self.cleanup_owner['process']
        poll = getattr(process, 'poll', None)
        if (getattr(self.vm, 'closed', False) or getattr(self.session, 'closed', False)
                or getattr(self.vm, '_fdisbull_control_quarantine', None)
                or callable(poll) and poll() is not None
                or any(not _channel_live(channel) for _, client, channel in self.clients if client is not None)):
            raise DebuggerError('Retained frame original owner is not live')
        return self

    def admit(self):
        if self.admission is not None:
            raise DebuggerError('Retained frame revision admission may occur only once')
        self.check_owner()
        revision = self.revision.snapshot()
        self.check_owner()
        self.admission = revision
        self.check()
        return deepcopy(revision)

    def check(self):
        self.check_owner()
        if self.admission is not None and self.revision.snapshot() != self.admission:
            raise DebuggerError('Session control or owner changed across the retained-frame read')
        return self

    def can_notify(self):
        """A captured close observer must not use a replacement session binding."""
        from .qemu_observation_authority import _state
        if (self.session.vm is not self.vm
                or getattr(self.vm, 'observation_authority', None) is not self.authority
                or getattr(self.vm, 'session_revision', None) is not self.revision
                or getattr(self.session, 'project', None) is not self.project
                or getattr(self.session, '_process', None) is not self.context_process):
            return False
        # Cleanup has already retired transports and temporary resources.
        current = _state(self.session, self.vm)
        omitted = {'gdb_architecture', 'gdb_register_description', 'temporary'}
        return all(current[key] == value for key, value in self.state.items() if key not in omitted)

    def close_channel(self, name):
        if name in self.closed_channels:
            return
        self.closed_channels.add(name)
        client = self.cleanup_owner[name]
        channel = self.cleanup_owner[name + '_socket']
        try:
            self.close_resource(channel)
        finally:
            if client is not None and getattr(client, 'socket', None) is channel:
                client.socket = None

    def close_resource(self, resource, method='close'):
        key = (id(resource), method)
        if resource is None or key in self.closed_resources:
            return
        self.closed_resources.add(key)
        action = getattr(resource, method, None)
        if callable(action):
            action()

    def close_resources(self):
        from .qemu_machine import _close_observation_owner
        try:
            _close_observation_owner(self.vm, self.cleanup_owner)
        except BaseException as error:
            self.cleanup_errors.extend(getattr(error, 'machine_cleanup_errors', [type(error).__name__]))

    def close(self):
        if self.closed:
            return
        # Compute this before marking the scope closed. Existing fixture/owner
        # close callbacks may run only while all captured bindings still match.
        try:
            from .qemu_observation_authority import _state
            ordinary_close = self.resources_match() and _state(self.session, self.vm) == self.state
        except BaseException:
            ordinary_close = False
        self.closed = self.closing = True
        self.vm._fdisbull_control_quarantine = 'failed retained-frame read'
        for action in (lambda: self.authority.invalidate('retained-frame owner closed'),
                       self.revision.effect):
            try:
                action()
            except BaseException as error:
                self.cleanup_errors.append(type(error).__name__)
        try:
            if ordinary_close:
                try:
                    self.original_close()
                except BaseException as error:
                    self.cleanup_errors.append(type(error).__name__)
            self.close_resources()
        finally:
            self.closing = False
            if hasattr(self.vm, 'closed'):
                self.vm.closed = True

    def attach(self, error, result=None):
        if result is not None and getattr(error, 'result', None) is None:
            error.result = result
        error.frame_read = dict(session_id=self.session_id, admission=deepcopy(self.admission),
            cleanup_attempted=self.closed, cleanup_errors=list(self.cleanup_errors))

    def detach(self):
        for target in [self.vm, *(client for _, client, _ in self.clients if client is not None)]:
            if getattr(target, '_frame_read_owner', None) is self:
                del target._frame_read_owner
        self.installed = False

    def finish(self, error=None, result=None):
        if not self.installed:
            return
        try:
            self.check()
            if error is None and self.admission is None:
                raise DebuggerError('Retained frame read returned without revision admission')
        except BaseException as invalid:
            if error is None:
                self.close()
                self.attach(invalid, result)
                raise
            error.frame_read_integrity_error = type(invalid).__name__
            self.close()
            self.attach(error, result)
            return
        if error is not None and self.started and not isinstance(error, ValueError):
            self.close()
            self.attach(error, result)
        else:
            # Parameter/profile/missing-raster refusals with an intact owner
            # remain reusable, as they were before this scope existed.
            self.detach()

    def restore_channel(self, client):
        return any(client is captured and (getattr(client, 'socket', None) is channel
                                          or getattr(client, 'socket', None) is None)
                   and getattr(client, '_observation_authority', None) is self.authority
                   for _, captured, channel in self.clients)


def capture_frame_read(session, vm, name, deadline):
    if name in READ_OPERATIONS and session.capabilities.get('frame_contract'):
        return FrameReadOwner(session, vm, deadline)
    return None


def check_frame_read_client(client):
    owner = getattr(client, '_frame_read_owner', None)
    if owner is not None:
        # Real same-byte writes still reach the bound transport. The retained
        # read's explicit checks reject their changed revision before success.
        owner.check_owner()


def close_frame_read_owner(vm):
    owner = getattr(vm, '_frame_read_owner', None)
    if owner is None:
        return False
    if owner.closing:
        owner.close_resources()
    else:
        owner.close()
    return True


def close_frame_read_channel(client):
    owner = getattr(client, '_frame_read_owner', None)
    if owner is None:
        return False
    if owner.closing:
        for name, captured, _ in owner.clients:
            if captured is client:
                owner.close_channel(name)
    else:
        owner.close()
    return True
