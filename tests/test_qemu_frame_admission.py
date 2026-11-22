"""Retained-read admission through real host protocol and publication paths.

Only native sockets/process resources and clock progression are authored
boundaries. These tests do not establish native event timing or frame parity.
"""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_machine import QemuMachine
from fdisbull.qemu_observation_authority import ObservationLease
from test_qemu_frame_contract import prepared
from test_qemu_observation_cleanup import Process, Resource, owner as foreign_owner
from test_qemu_operation_deadlines import client, packet
from test_qemu_video_frame import audio, observation, video


ROUTES = ['probe', 'rgba', 'screenshot', 'capture']
EVENTS = [
    [{'event': 'RTC_CHANGE', 'data': {'offset': 0}}],
    [{'event': 'AUTHORED_UNKNOWN_EVENT', 'data': {'value': 0}}],
    [{'event': 'RTC_CHANGE', 'data': {'offset': 0}},
     {'event': 'RTC_CHANGE', 'data': {'offset': 0}}],
]


class BoundaryLock:
    def __init__(self):
        self.raw = threading.RLock()
        self.depth = self.acquires = self.releases = 0
        self.after_release = None

    def acquire(self, blocking=True, timeout=-1):
        self.acquires += 1
        admitted = self.raw.acquire(blocking, timeout)
        if admitted:
            self.depth += 1
        return admitted

    def release(self):
        self.raw.release()
        self.depth -= 1
        self.releases += 1
        if self.depth == 0 and self.after_release is not None:
            action, self.after_release = self.after_release, None
            action()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class RestoreGDB(GDBRemote):
    after_restore = None

    @property
    def operation_deadline(self):
        return getattr(self, '_authored_deadline', None)

    @operation_deadline.setter
    def operation_deadline(self, value):
        previous = getattr(self, '_authored_deadline', None)
        self._authored_deadline = value
        if value is None and previous is not None and self.after_restore is not None:
            action, self.after_restore = self.after_restore, None
            action()


@pytest.fixture
def retained(video, monkeypatch):
    o = video
    vm = QemuMachine.__new__(QemuMachine)
    vm.__dict__.update(o.vm.__dict__)
    del vm.close  # Exercise the production captured-owner close implementation.
    vm.lock = BoundaryLock()
    vm.process = Process()
    vm.temporary = Resource(str(o.directory))
    vm._qemu_image_proof = Resource('original-proof')
    vm._channels = [Resource('original-extra-channel')]
    vm._admission_guest_pidfd = None
    vm.machine_configuration['memory_mib'] = 16
    callbacks = []
    vm.close_observer = lambda: callbacks.append('original')
    original, gwire = client('gdb', o.clock)
    gdb = RestoreGDB.__new__(RestoreGDB)
    gdb.__dict__.update(original.__dict__)
    gdb.packet_size = 64
    gdb.architecture = 'i386'
    gdb.register_description = [dict(name='eax', number=0, size=4)]
    send = gwire.sendall

    def acknowledge_same_byte_write(data):
        if data.startswith(b'$M'):
            gwire.requests.append(data[1:-3])
            gwire.buffer.extend(packet(b'OK'))
            gwire.pending_delay = 0
            return
        send(data)

    gwire.sendall = acknowledge_same_byte_write
    vm.gdb = gdb
    o.vm, o.gdb, o.gwire = vm, gdb, gwire
    o.process, o.stdin, o.stdout = vm.process, vm.process.stdin, vm.process.stdout
    o.temporary, o.proof, o.extra = vm.temporary, vm._qemu_image_proof, vm._channels[0]
    o.callbacks, o.original_lock = callbacks, vm.lock
    for wire in (o.wire, gwire):
        close = wire.close
        wire.closes = 0
        def counted_close(wire=wire, close=close):
            wire.closes += 1
            close()
        monkeypatch.setattr(wire, 'close', counted_close)
    s = o.session
    s.vm = s.rpc = vm
    s._stopped = lambda: gdb
    s._runtime_epoch, s._checkpoint_epoch = 'frame-runtime', 7
    vm.context = s
    project, run = s.project, s.run_id
    prepared(o)
    o.authority, o.revision = vm.observation_authority, vm.session_revision
    try:
        yield o
    finally:
        # The containing project fixture closes its session after this fixture.
        # Restore only its host reference, after all foreign-isolation oracles.
        s.vm = s.rpc = vm
        s.project, s.run_id = project, run


def read(o, route):
    if route == 'probe':
        return o.session.frame_probe([[0, 0], [319, 199], [0, 0]])
    if route == 'rgba':
        return o.session.frame_rgba(encoding='png')
    if route == 'screenshot':
        return o.session.call('video.screenshot', {'encoding': 'png-indexed'})
    return o.session.capture_video_frame('admission.png')


def metadata(value, route):
    if route == 'rgba':
        return value.metadata
    return value['metadata'] if route == 'capture' else value


def on_command(o, command, action):
    send = o.wire.sendall
    calls = []
    def boundary(data):
        request = json.loads(data)
        send(data)
        if request['execute'] == command and not calls:
            calls.append(command)
            action()
    o.wire.sendall = boundary
    return calls


def events(o, values):
    o.wire.buffer[:0] = b''.join(json.dumps(value).encode() + b'\n' for value in values)


def observe_admission(o, monkeypatch):
    observed = []
    admit = getattr(o.session, '_frame_contract_admit', None)
    if admit is not None:
        def witness(vm, identity):
            before = list(o.wire.calls)
            value = admit(vm, identity)
            observed.append((deepcopy(value[-1]), o.revision.snapshot(), before, list(o.wire.calls)))
            return value
        monkeypatch.setattr(o.session, '_frame_contract_admit', witness)
    return observed


def assert_original_closed_once(o):
    assert o.process.terminates == o.process.waits == 1 and o.process.kills == 0
    assert o.stdin.closes == o.stdout.closes == 1
    assert o.wire.closes == o.gwire.closes == o.extra.closes == 1
    assert o.temporary.cleanups == o.proof.closes == 1
    assert o.vm.closed and o.original_lock.depth == 0
    o.vm.close()
    o.qmp.close()
    o.gdb.close()
    assert o.process.terminates == o.process.waits == 1
    assert o.wire.closes == o.gwire.closes == 1


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('event_batch', EVENTS)
def test_initial_context_events_enter_exactly_one_admission_without_extra_native_calls(
        retained, monkeypatch, route, event_batch):
    o = retained
    offset = len(o.wire.calls)
    reference = metadata(read(o, route), route)
    expected_commands = [name for name, _ in o.wire.calls[offset:]]
    revision = o.revision.snapshot()
    offset = len(o.wire.calls)
    observed = observe_admission(o, monkeypatch)
    delivered = on_command(o, 'query-status', lambda: events(o, event_batch))
    result = metadata(read(o, route), route)
    assert delivered == ['query-status'] and len(observed) == 1
    admitted, current_at_admission, calls_before, calls_after = observed[0]
    assert admitted == current_at_admission == o.revision.snapshot()
    assert {key: result[key] for key in admitted} == admitted
    assert result['state_revision'] == revision['state_revision'] + len(event_batch)
    assert result['frame_identity'] == reference['frame_identity']
    assert calls_before == calls_after
    assert [name for name, _ in o.wire.calls[offset:]] == expected_commands
    assert not o.process.terminates and not o.vm.closed
    assert getattr(o.vm, '_frame_read_owner', None) is None


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('event_batch', EVENTS)
def test_every_post_admission_event_refuses_without_publication(retained, route, event_batch):
    o = retained
    before = o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    probe_events = o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='frame-probe'").fetchone()[0]
    delivered = on_command(o, 'x-fdisbull-query-video-frame', lambda: events(o, event_batch))
    with pytest.raises(DebuggerError, match='Session control or owner changed') as failure:
        read(o, route)
    assert delivered == ['x-fdisbull-query-video-frame']
    assert failure.value.frame_read['admission'] is not None
    assert failure.value.result['native']['frame']['frame-id'] == o.wire.video['frame']['frame-id']
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='frame-probe'").fetchone()[0] == probe_events
    assert_original_closed_once(o)


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('boundary', ['before', 'after'])
def test_real_bound_same_byte_write_is_baseline_only_before_admission(retained, route, boundary):
    o = retained
    writes = []
    def write():
        before = o.gdb.memory(0x2000, 1, space='physical')
        after = o.gdb.memory(0x2000, 1, space='physical', data=before)
        writes.append((before, after, o.revision.snapshot()))
    command = 'query-status' if boundary == 'before' else 'x-fdisbull-query-video-frame'
    on_command(o, command, write)
    if boundary == 'before':
        result = metadata(read(o, route), route)
        assert {key: result[key] for key in writes[0][2]} == writes[0][2]
        assert not o.vm.closed
    else:
        with pytest.raises(DebuggerError, match='Session control or owner changed'):
            read(o, route)
        assert_original_closed_once(o)
    assert len(writes) == 1 and writes[0][:2] == (b'\0', b'\0')
    assert o.gwire.requests.count(b'M2000,1:00') == 1
    assert o.gwire.mode == b'0'


def test_new_frame_admission_does_not_rewrite_an_earlier_caller_bracket(retained):
    from fdisbull.frame_coherence import capture_frame_state
    from test_frame_coherence import Fake
    o = retained
    controller = Fake()
    controller.session = o.session
    completed = []
    def capture():
        on_command(o, 'query-status', lambda: events(o, EVENTS[0]))
        result = o.session.capture_video_frame()
        completed.append(result)
        return result
    bracket = capture_frame_state(controller, capture)
    diagnostic = {
        'complete': bracket['complete'], 'issues': bracket['issues'],
        'status_bracket_issues': [item['issues'] for item in bracket['status_brackets']],
    }
    assert len(completed) == 1 and not o.vm.closed, diagnostic
    assert bracket['complete'] is False, diagnostic
    assert bracket['issues'] == ['status state_revision changed', 'frame state_revision differs from bracket']
    assert completed[0]['metadata']['state_revision'] == o.revision.snapshot()['state_revision']
    assert not controller.calls


def foreign(monkeypatch):
    vm, _, callbacks = foreign_owner()
    vm.lock = BoundaryLock()
    vm.operation_deadline = 77
    calls = []
    for target, names in ((vm.session_revision, ('snapshot', 'effect', 'mode')),
                          (vm.observation_authority, ('public_operation', 'invalidate'))):
        for name in names:
            method = getattr(target, name)
            def record(*args, name=name, method=method, **kwargs):
                calls.append(name)
                return method(*args, **kwargs)
            monkeypatch.setattr(target, name, record)
    resources = [vm.qmp.socket, vm.gdb.socket, vm.temporary,
                 vm._qemu_image_proof, *vm._channels, vm.process.stdin, vm.process.stdout]
    return vm, callbacks, calls, resources


def assert_foreign_untouched(value):
    vm, callbacks, calls, resources = value
    assert not calls and not callbacks and not vm.lock.acquires
    assert vm.process.terminates == vm.process.kills == vm.process.waits == 0
    assert all(item.closes == item.cleanups == 0 for item in resources)
    assert vm.operation_deadline == 77
    assert getattr(vm, '_frame_read_owner', None) is None


REPLACEMENTS = ['vm', 'process', 'lock', 'qmp', 'gdb', 'qmp_socket', 'gdb_socket',
    'authority', 'revision', 'qmp_authority', 'gdb_authority', 'project', 'run',
    'configuration', 'runtime', 'checkpoint', 'temporary', 'channels', 'proof',
    'observer', 'stdin', 'stdout', 'session-id', 'authority-lifetime']


def replace(o, kind, value):
    vm = value[0]
    if kind == 'vm': o.session.vm = vm
    elif kind in ('process', 'lock', 'qmp', 'gdb', 'temporary'): setattr(o.vm, kind, getattr(vm, kind))
    elif kind.endswith('_socket'): getattr(o.vm, kind.split('_')[0]).socket = vm.qmp.socket
    elif kind == 'authority': o.vm.observation_authority = vm.observation_authority
    elif kind == 'revision': o.vm.session_revision = vm.session_revision
    elif kind.endswith('_authority'): getattr(o.vm, kind.split('_')[0])._observation_authority = vm.observation_authority
    elif kind == 'project': o.session.project = object()
    elif kind == 'run': o.session.run_id = 'foreign-run'
    elif kind == 'configuration': o.vm.machine_configuration['cpus'] = 2
    elif kind == 'runtime': o.session._runtime_epoch = 'foreign-runtime'
    elif kind == 'checkpoint': o.session._checkpoint_epoch = 'foreign-checkpoint'
    elif kind == 'channels': o.vm._channels = vm._channels
    elif kind == 'proof': o.vm._qemu_image_proof = vm._qemu_image_proof
    elif kind == 'observer': o.vm.close_observer = vm.close_observer
    elif kind in ('stdin', 'stdout'): setattr(o.process, kind, getattr(vm.process, kind))
    elif kind == 'session-id': o.revision.session_id = 'foreign-session'
    else: o.authority.lifetime = 'foreign-lifetime'


@pytest.mark.parametrize('kind', REPLACEMENTS)
@pytest.mark.parametrize('boundary', ['context', 'selection'])
def test_replaced_resources_never_become_the_read_baseline_or_cleanup_target(
        retained, monkeypatch, kind, boundary):
    o = retained
    value = foreign(monkeypatch)
    command = 'query-status' if boundary == 'context' else 'x-fdisbull-query-video-frame'
    changed = on_command(o, command, lambda: replace(o, kind, value))
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_rgba(encoding='png')
    assert changed == [command]
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


@pytest.mark.parametrize('kind', ['authority', 'revision'])
def test_public_guard_replacement_precedes_any_foreign_authority_access(retained, monkeypatch, kind):
    o = retained
    value = foreign(monkeypatch)
    before = list(o.wire.calls)
    o.vm.operation_guard = lambda name: replace(o, kind, value)
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([])
    assert o.wire.calls == before
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


@pytest.mark.parametrize('boundary', ['context', 'selection'])
@pytest.mark.parametrize('active_lease', [False, True])
def test_nested_public_operation_refuses_foreign_authority_before_its_active_lease(
        retained, monkeypatch, boundary, active_lease):
    o = retained
    value = foreign(monkeypatch)
    vm = value[0]
    authority = vm.observation_authority
    lease = ObservationLease(authority, vm.context, 77, ()) if active_lease else None
    authority._active = lease
    generation = authority.control_generation
    native_before = []

    def nested():
        replace(o, 'authority', value)
        native_before.append((len(o.wire.calls), len(o.gwire.requests)))
        o.session.registers()

    command = 'query-status' if boundary == 'context' else 'x-fdisbull-query-video-frame'
    changed = on_command(o, command, nested)
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([[0, 0]])
    assert changed == [command]
    assert native_before == [(len(o.wire.calls), len(o.gwire.requests))]
    assert authority.control_generation == generation and authority._active is lease
    if lease is not None:
        assert lease.reason is None and not lease.ended and not lease.events
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


class ForeignGuardContext:
    """Observe both lookup and invocation on a context outside the read owner."""
    def __init__(self, calls):
        self.calls = calls

    @property
    def _dos_async_operation_guard(self):
        self.calls.append('asynchronous-lookup')
        return lambda *args: self.calls.append('asynchronous-call')

    @property
    def _le_source_operation_guard(self):
        self.calls.append('source-lookup')
        return lambda *args: self.calls.append('source-call')


@pytest.mark.parametrize('boundary', ['context', 'selection'])
def test_nested_public_operation_refuses_foreign_context_before_guard_lookup(retained, boundary):
    o = retained
    calls, native_before = [], []
    context = ForeignGuardContext(calls)

    def nested():
        o.vm.context = context
        native_before.append((len(o.wire.calls), len(o.gwire.requests)))
        o.session.registers()

    command = 'query-status' if boundary == 'context' else 'x-fdisbull-query-video-frame'
    changed = on_command(o, command, nested)
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([[0, 0]])
    assert changed == [command] and not calls
    assert native_before == [(len(o.wire.calls), len(o.gwire.requests))]
    assert_original_closed_once(o)
    assert not calls


@pytest.mark.parametrize('boundary', ['authority', 'asynchronous', 'source', 'operation', 'history'])
def test_each_public_guard_callback_rechecks_owner_before_the_next_guard(
        retained, monkeypatch, boundary):
    o = retained
    phases, foreign_calls = [], []
    replacement = ForeignGuardContext(foreign_calls)
    context = SimpleNamespace()
    o.vm.context = context
    order = ['authority', 'asynchronous', 'source', 'operation', 'history', 'revision']

    def phase(label):
        def callback(*args, **kwargs):
            phases.append(label)
            if label == boundary:
                o.vm.context = replacement
        return callback

    public_operation = o.authority.public_operation
    def original_authority(name):
        public_operation(name)
        phase('authority')(name)
    monkeypatch.setattr(o.authority, 'public_operation', original_authority)
    context._dos_async_operation_guard = phase('asynchronous')
    context._le_source_operation_guard = phase('source')
    o.vm.operation_guard = phase('operation')
    o.vm.history_operation_guard = phase('history')
    revision_operation = o.revision.public_operation
    def original_revision(*args, **kwargs):
        phase('revision')(*args, **kwargs)
        return revision_operation(*args, **kwargs)
    monkeypatch.setattr(o.revision, 'public_operation', original_revision)
    native_before = list(o.wire.calls), list(o.gwire.requests)
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([[0, 0]])
    assert phases == order[:order.index(boundary) + 1]
    assert not foreign_calls
    assert (o.wire.calls, o.gwire.requests) == native_before
    assert_original_closed_once(o)
    assert not foreign_calls


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('kind', ['none', 'authority', 'revision'])
def test_late_outer_timeout_keeps_arrived_frame_and_original_cleanup(retained, monkeypatch, route, kind):
    o = retained
    value = foreign(monkeypatch)
    unnamed = []
    def outer(name=None, *args):
        if name is None:
            unnamed.append(True)
            if len(unnamed) == 2:
                if kind != 'none': replace(o, kind, value)
                o.clock.advance(2)
    o.session._dos_async_operation_guard = outer
    with pytest.raises(TimeoutError) as failure:
        read(o, route)
    result = metadata(failure.value.result, route)
    assert result['frame_id'] == o.wire.video['frame']['frame-id']
    assert result['session_id'] == failure.value.frame_read['session_id']
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


@pytest.mark.parametrize('boundary', ['restore', 'release'])
@pytest.mark.parametrize('kind', ['raise', 'revision', 'authority', 'expire'])
def test_read_scope_survives_deadline_restoration_and_original_lock_release(
        retained, monkeypatch, boundary, kind):
    o = retained
    value = foreign(monkeypatch)
    fired = []
    def completion():
        fired.append(True)
        if kind == 'raise': raise RuntimeError('authored outer completion failure')
        if kind == 'expire': o.clock.advance(2)
        else: replace(o, kind, value)
    if boundary == 'restore':
        o.gdb.after_restore = completion
    else:
        o.original_lock.after_release = completion
    expected = RuntimeError if kind == 'raise' else TimeoutError if kind == 'expire' else DebuggerError
    with pytest.raises(expected) as failure:
        o.session.frame_probe([[0, 0]])
    assert fired == [True]
    assert failure.value.result['samples'] == [dict(x=0, y=0, rgb=[4, 85, 170])]
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


@pytest.mark.parametrize('boundary', ['context', 'selection'])
def test_falsey_primary_error_survives_replaced_authority_and_cleanup_failure(
        retained, monkeypatch, boundary):
    class Primary(RuntimeError):
        def __bool__(self): return False
    o = retained
    value = foreign(monkeypatch)
    primary = Primary('authored falsey failure')
    def fail():
        replace(o, 'authority', value)
        replace(o, 'revision', value)
        raise primary
    def cleanup_failure():
        o.temporary.cleanups += 1
        raise OSError('authored temporary cleanup failure')
    o.temporary.cleanup = cleanup_failure
    command = 'query-status' if boundary == 'context' else 'x-fdisbull-query-video-frame'
    on_command(o, command, fail)
    with pytest.raises(Primary) as failure:
        o.session.frame_rgba(encoding='png')
    assert failure.value is primary
    assert 'OSError' in primary.frame_read['cleanup_errors']
    assert_original_closed_once(o)
    assert_foreign_untouched(value)


def test_unadvertised_codec_refusal_keeps_healthy_owner_and_issues_no_native_request(retained):
    o = retained
    o.session.capabilities['video']['screenshot_encodings'] = ['png']
    before = list(o.wire.calls)
    with pytest.raises(DebuggerError, match='advertise'):
        o.session.frame_rgba(encoding='png-indexed')
    assert o.wire.calls == before and not o.vm.closed and not o.process.terminates
    assert getattr(o.vm, '_frame_read_owner', None) is None
    assert o.session.frame_rgba(encoding='png').pixel(0, 0) == (4, 85, 170, 255)


def test_retained_read_preserves_an_absent_lazy_debugger_without_connecting(retained):
    o = retained
    o.gdb.close()
    o.vm.gdb = None
    o.authority.bind(gdb=None)
    def forbidden():
        pytest.fail('Retained source reads must not connect an absent debugger')
    o.vm.debugger = o.session._stopped = forbidden
    before = o.revision.snapshot()
    result = o.session.frame_rgba(encoding='png')
    assert result.pixel(0, 0) == (4, 85, 170, 255)
    assert {key: result.metadata[key] for key in before} == before
    assert o.revision.snapshot() == before and o.vm.gdb is None and not o.vm.closed


def test_duplicate_captured_channel_references_receive_one_cleanup_attempt(retained):
    o = retained
    o.vm._channels.extend([o.wire, o.gwire, o.extra])
    on_command(o, 'x-fdisbull-query-video-frame', lambda: events(o, EVENTS[0]))
    with pytest.raises(DebuggerError, match='Session control or owner changed'):
        o.session.frame_probe([[0, 0]])
    assert_original_closed_once(o)
