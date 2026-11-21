"""Covered control authority at the real QMP/GDB protocol dispatch seams.

The peers below model protocol responses, not QEMU state or native revision
authority. No emulator, project import side effect or native fixture is needed.
"""
import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_observation_authority import ObservationAuthority
from test_qemu_operation_deadlines import Clock, Wire, client, packet


@pytest.fixture
def owned(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock)
    qmp, qwire = client('qmp', clock)
    gdb, gwire = client('gdb', clock)
    gdb.packet_size = 64
    gdb.architecture = 'i386'
    gdb.register_description = [dict(name='eax', number=0, size=4)]
    process = SimpleNamespace(pid=123, poll=lambda: None, stdin=None, stdout=None)
    vm = SimpleNamespace(lock=threading.RLock(), process=process, qmp=qmp, gdb=gdb,
        machine_configuration={'memory_mib': 16, 'cpus': 1}, operation_deadline=None,
        temporary=SimpleNamespace(name=str(tmp_path)), _channels=[], closed=False)
    context = SimpleNamespace(vm=vm, run_id=7, _runtime_epoch='runtime-1', _checkpoint_epoch=0,
        project=object(), version={'id': 1}, metadata={}, _process={'capture_epoch': 'process-1'})
    vm.context = context
    authority = vm.observation_authority = ObservationAuthority(vm)
    authority.bind(qmp=qmp, gdb=gdb)
    value = SimpleNamespace(clock=clock, vm=vm, context=context, authority=authority,
        qmp=qmp, qwire=qwire, gdb=gdb, gwire=gwire, directory=tmp_path)
    yield value
    qmp.close()
    gdb.close()


def observe(o, *, ram_ranges=()):
    return o.authority.observe(o.context, deadline=o.clock.now + 1, ram_ranges=ram_ranges)


def test_passive_protocol_bracket_has_limited_authority_and_stable_generation(owned):
    o = owned
    with observe(o, ram_ranges=[(0x2000, 80)]) as lease:
        assert o.qmp.call('query-status') == {'running': False}
        assert o.gdb.registers() == {'eax': '0x0'}
        assert o.gdb.memory(0x2000, 80) == bytes(80)
        assert o.gwire.mode == b'0'
        lease.check()
        assert lease.receipt()['valid'] and not lease.receipt()['complete']
    result = lease.receipt()
    assert result['complete'] and result['valid']
    assert result['control_generation_before'] == result['control_generation_after']
    assert result['atomic'] is False and result['native_state_revision'] is None
    assert result['whole_machine_state_revision'] is None
    assert result['coverage'] == dict(bound_python_protocol_dispatch=True,
        admitted_public_operations=True, raw_handles=False,
        independent_controllers=False, native_device_mutations=False)
    assert o.gwire.requests[0] == b'g'
    assert o.gwire.requests[1:3] == [b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:1']
    assert o.gwire.requests[-1] == b'Qqemu.PhyMemMode:0'
    assert o.authority._cleanup_owner is None


@pytest.mark.parametrize('operation', [
    lambda o: o.qmp.call('cont'),
    lambda o: o.qmp.call('query-unknown'),
    lambda o: o.qmp.call('query-status', {'unexpected': True}),
    lambda o: o.qmp.call('human-monitor-command', {'command-line': 'stop'}),
    lambda o: o.gdb.execute('c', 100),
    lambda o: o.gdb.request('P0=01000000'),
    lambda o: o.gdb.request('Qqemu.PhyMemMode:1'),
    lambda o: o.gdb.request('m2000,1'),
    lambda o: o.gdb.memory(0x2000, 1, data=b'\x90'),
    lambda o: o.gdb.memory(0x2000, 1, space='virtual'),
    lambda o: o.gdb.memory(0x2010, 1),
])
def test_unadmitted_effect_is_refused_before_any_send_and_refusal_is_latched(owned, operation):
    o = owned
    with pytest.raises(DebuggerError, match='invalidated'):
        with observe(o, ram_ranges=[(0x2000, 4)]) as lease:
            with pytest.raises(DebuggerError, match='unadmitted'):
                operation(o)
            assert not o.qwire.requests and not o.gwire.requests
            assert not lease.receipt()['valid']
    assert not lease.receipt()['complete']
    assert o.authority._cleanup_owner is lease.cleanup_owner


@pytest.mark.parametrize('protocol,operation', [
    ('qmp', lambda o: o.qmp.call('cont')),
    ('gdb', lambda o: o.gdb.request('P0=01000000')),
])
def test_generation_advances_before_uncertain_mutation_send(owned, protocol, operation):
    o = owned
    wire = o.qwire if protocol == 'qmp' else o.gwire
    before = o.authority.control_generation
    seen = []

    def failed_send(data):
        seen.append((data, o.authority.control_generation))
        raise OSError('partial outbound transfer')

    wire.sendall = failed_send
    with pytest.raises(OSError, match='partial outbound'):
        operation(o)
    assert len(seen) == 1 and seen[0][1] > before
    assert wire.closed
    assert (o.qmp if protocol == 'qmp' else o.gdb).socket is None


@pytest.mark.parametrize('kind', ['public', 'bind', 'observe'])
def test_reentrant_owner_operation_cannot_be_caught_to_restore_validity(owned, kind):
    o = owned
    with pytest.raises(DebuggerError, match='invalidated'):
        with observe(o) as lease:
            with pytest.raises(DebuggerError):
                if kind == 'public':
                    o.authority.public_operation('write_memory')
                elif kind == 'bind':
                    o.authority.bind(qmp=o.qmp)
                else:
                    with observe(o):
                        pytest.fail('nested observation admitted')
            assert not lease.receipt()['valid']
    assert not o.qwire.requests and not o.gwire.requests


def test_qmp_reentrant_read_is_refused_before_nonreentrant_channel_lock(owned):
    o = owned
    original = o.qwire.sendall

    def peer(data):
        with pytest.raises(DebuggerError, match='reentrant protocol'):
            o.qmp.call('query-status')
        original(data)

    o.qwire.sendall = peer
    with pytest.raises(DebuggerError, match='invalidated'):
        with observe(o):
            o.qmp.call('query-status')
    assert o.qwire.requests == ['query-status']


def test_gdb_ack_callback_cannot_dispatch_another_channel_inside_lease(owned):
    o = owned

    def callback():
        with pytest.raises(DebuggerError, match='reentrant protocol'):
            o.qmp.call('query-status')

    o.gwire.on_ack = callback
    with pytest.raises(DebuggerError, match='invalidated'):
        with observe(o):
            o.gdb.request('g')
    assert o.gwire.requests == [b'g'] and o.qwire.requests == []


def test_qmp_event_is_retained_and_poisoned_during_observation(owned):
    o = owned
    event = {'event': 'RESUME', 'timestamp': {'seconds': 1, 'microseconds': 2}}
    o.qwire.buffer.extend(json.dumps(event).encode() + b'\n')
    with pytest.raises(DebuggerError, match='QMP event') as failure:
        with observe(o) as lease:
            o.qmp.call('query-status')
    assert lease.receipt()['events'] == [event]
    assert failure.value.observation_authority['events'] == [event]
    assert o.qmp.socket is None and o.qwire.closed
    assert o.qwire.requests == ['query-status']


def test_qmp_events_keep_existing_unleased_skip_behavior(owned):
    o = owned
    o.qwire.buffer.extend(b'{"event":"STOP"}\n')
    assert o.qmp.call('query-status') == {'running': False}
    assert o.qmp.socket is o.qwire and not o.qwire.closed


@pytest.mark.parametrize('protocol', ['qmp', 'gdb'])
def test_replaced_socket_is_never_read_written_or_closed_by_failure_cleanup(owned, protocol):
    o = owned
    remote, wire = (o.qmp, o.qwire) if protocol == 'qmp' else (o.gdb, o.gwire)
    foreign = Wire(o.clock, protocol)
    touched = []
    foreign.recv = lambda count: touched.append('recv') or b''
    foreign.sendall = lambda data: touched.append('send')
    original = wire.sendall

    def peer(data):
        original(data)
        remote.socket = foreign

    wire.sendall = peer
    with pytest.raises(DebuggerError, match='changed'):
        with observe(o) as lease:
            if protocol == 'qmp':
                remote.call('query-status')
            else:
                remote.request('g')
    assert touched == [] and not foreign.closed and remote.socket is foreign
    assert wire.closed
    remote.close()
    assert not foreign.closed
    assert o.authority.original_channel(remote) is wire
    assert lease.cleanup_owner[protocol + '_socket'] is wire


def test_same_lock_owner_or_epoch_replacement_is_not_continuity(owned):
    o = owned
    with pytest.raises(DebuggerError, match='lifetime changed'):
        with observe(o) as lease:
            o.context._checkpoint_epoch += 1
            lease.check()
    assert not lease.receipt()['valid']
    assert not o.qwire.requests and not o.gwire.requests


def test_replacement_owner_with_the_same_lock_is_refused_before_dispatch(owned):
    o = owned
    replacement = SimpleNamespace(**vars(o.vm))
    with pytest.raises(DebuggerError, match='machine owner changed'):
        with observe(o):
            o.context.vm = replacement
            o.qmp.call('query-status')
    assert not o.qwire.requests and not o.gwire.requests


def test_changed_lock_during_admission_is_never_treated_as_held(owned):
    o = owned
    released = []

    class ReplacedLock:
        def acquire(self, *, timeout):
            o.vm.lock = threading.RLock()
            return True

        def release(self):
            released.append(True)

    o.vm.lock = ReplacedLock()
    with pytest.raises(DebuggerError, match='lock changed'):
        o.qmp.call('query-status')
    assert released == [True] and not o.qwire.requests


def test_expired_admission_cannot_send_even_memory_mode_query(owned):
    o = owned
    with pytest.raises(TimeoutError, match='deadline'):
        with observe(o, ram_ranges=[(0x2000, 1)]) as lease:
            o.clock.advance(2)
            o.gdb.memory(0x2000, 1)
    assert not o.gwire.requests and not lease.receipt()['valid']


def test_short_reply_deadline_poisons_original_without_retry(owned):
    o = owned
    o.qwire.latency = .2
    with pytest.raises(TimeoutError):
        with observe(o) as lease:
            o.qmp.call('query-status', timeout_ms=50)
    assert o.qwire.requests == ['query-status']
    assert o.qwire.closed and not lease.receipt()['valid']
    assert o.clock.now == pytest.approx(100.05)


@pytest.mark.parametrize('ranges', [[(0xa0000, 1)], [(0xfffff, 2)], [(0x1000000, 1)],
                                   [(0x2000, True)], [(0x2000, 65537)]])
def test_declared_ram_must_be_bounded_ordinary_pc_ram(owned, ranges):
    o = owned
    with pytest.raises(ValueError, match='RAM'):
        with observe(o, ram_ranges=ranges):
            pytest.fail('invalid RAM admitted')
    assert not o.qwire.requests and not o.gwire.requests


def test_exact_single_export_grant_accepts_path_directory_and_consumes_once(owned):
    o = owned
    first = o.directory / ('video-frame-' + 'a' * 32 + '.ppm')
    second = o.directory / ('video-frame-' + 'b' * 32 + '.ppm')
    with pytest.raises(DebuggerError, match='unadmitted'):
        with observe(o) as lease:
            lease.authorize_export('stream', 2, directory=o.directory)
            o.qmp.call('x-fdisbull-export-video-frame',
                       {'token': 'stream', 'frame-id': 2, 'filename': str(first)})
            o.qmp.call('x-fdisbull-export-video-frame',
                       {'token': 'stream', 'frame-id': 2, 'filename': str(second)})
    assert o.qwire.requests == ['x-fdisbull-export-video-frame']


@pytest.mark.parametrize('filename', ['existing', 'outside', 'wrong-name'])
def test_export_grant_cannot_overwrite_or_escape_owned_new_path(owned, filename):
    o = owned
    path = o.directory / ('video-frame-' + 'c' * 32 + '.ppm')
    if filename == 'existing':
        path.write_bytes(b'preserve')
    elif filename == 'outside':
        path = o.directory.parent / path.name
    else:
        path = o.directory / 'not-an-owned-export.ppm'
    with pytest.raises(DebuggerError, match='unadmitted'):
        with observe(o) as lease:
            lease.authorize_export('stream', 2, directory=str(o.directory))
            o.qmp.call('x-fdisbull-export-video-frame',
                       {'token': 'stream', 'frame-id': 2, 'filename': str(path)})
    assert not o.qwire.requests
    if filename == 'existing':
        assert path.read_bytes() == b'preserve'


def test_expected_refusal_requires_healthy_final_bracket_and_allows_later_observation(owned):
    o = owned
    error = ValueError('keyboard is held')
    error.observation_refusal = True
    with pytest.raises(ValueError, match='keyboard'):
        with observe(o) as lease:
            o.qmp.call('query-status')
            raise error
    assert lease.receipt()['valid'] and not lease.receipt()['complete']
    assert o.authority._cleanup_owner is None
    with observe(o) as later:
        later.check()
    assert later.receipt()['complete']


def test_expected_refusal_marker_cannot_hide_prior_mutation_attempt(owned):
    o = owned
    with pytest.raises(DebuggerError, match='invalidated'):
        with observe(o):
            with pytest.raises(DebuggerError):
                o.qmp.call('cont')
            error = ValueError('unsupported input')
            error.observation_refusal = True
            raise error
    assert o.authority._cleanup_owner is not None


def test_missing_gdb_and_unbound_replacement_channel_do_not_reconnect(owned):
    o = owned
    original = o.vm.gdb
    o.vm.gdb = None
    with pytest.raises(DebuggerError, match='existing live'):
        with observe(o):
            pytest.fail('missing debugger admitted')
    o.vm.gdb = original
    o.qmp.socket = Wire(o.clock, 'qmp')
    with pytest.raises(DebuggerError, match='changed'):
        with observe(o):
            pytest.fail('unbound channel admitted')
    assert not o.qwire.requests and not o.gwire.requests


@pytest.mark.parametrize('command', [10**12, object(), ['g'], 'g' * (GDBRemote.limit + 1)],
                         ids=['integer', 'object', 'list', 'oversized-string'])
def test_malformed_gdb_command_is_bounded_before_dispatch(owned, command):
    o = owned
    with pytest.raises(ValueError):
        o.gdb.request(command)
    assert not o.gwire.requests


def test_bound_private_send_requires_an_admitted_protocol_operation(owned):
    o = owned
    with pytest.raises(DebuggerError, match='Raw protocol helper'):
        with observe(o):
            o.gdb._send('P0=01000000', o.clock.now + 1)
    assert not o.gwire.requests


def test_gdb_reply_budget_is_narrowed_without_changing_client_limit(owned):
    o = owned
    o.gwire.buffer.extend(packet(b'0' * (128 * 1024 + 1)))
    with pytest.raises(DebuggerError, match='packet exceeds budget'):
        with observe(o):
            o.gdb.request('g')
    assert o.gdb.limit == 8 * 1024 * 1024
    assert o.gwire.closed


def test_direct_control_on_another_thread_waits_for_observation_owner(owned):
    o = owned
    entered = threading.Event()
    original_lock = threading.RLock()

    class ObservedLock:
        def acquire(self, *, timeout):
            if threading.current_thread() is worker:
                entered.set()
            return original_lock.acquire(timeout=timeout)

        def release(self):
            original_lock.release()

    o.vm.lock = ObservedLock()
    failures = []

    def mutate():
        try:
            o.qmp.call('cont', timeout_ms=1000)
        except BaseException as error:
            failures.append(error)

    worker = threading.Thread(target=mutate)
    with observe(o) as lease:
        worker.start()
        assert entered.wait(1)
        assert o.qwire.requests == []
        lease.check()
    worker.join(2)
    assert not worker.is_alive() and not failures
    assert o.qwire.requests == ['cont']
    historical = lease.receipt()
    assert historical['complete'] and historical['valid']
    assert historical['control_generation_before'] == historical['control_generation_after']


def test_actual_socket_qmp_reply_runs_through_shared_authority(tmp_path):
    left, right = socket.socketpair()
    right.settimeout(2)
    qmp = QemuControl.__new__(QemuControl)
    qmp.socket, qmp.buffer, qmp.sequence = left, bytearray(), 0
    qmp.lock, qmp.operation_deadline = threading.Lock(), None
    gdb, _ = client('gdb', time.monotonic)
    vm = SimpleNamespace(lock=threading.RLock(), process=SimpleNamespace(poll=lambda: None),
        qmp=qmp, gdb=gdb, machine_configuration={'memory_mib': 16},
        temporary=SimpleNamespace(name=str(tmp_path)), operation_deadline=None)
    context = SimpleNamespace(vm=vm)
    authority = ObservationAuthority(vm)
    authority.bind(qmp=qmp, gdb=gdb)
    received, failures = [], []

    def peer():
        try:
            raw = bytearray()
            while b'\n' not in raw:
                raw.extend(right.recv(4096))
            request = json.loads(raw)
            received.append(request['execute'])
            right.sendall(json.dumps({'id': request['id'], 'return': {'running': False}}).encode() + b'\n')
        except BaseException as error:
            failures.append(error)
        finally:
            right.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        with authority.observe(context, deadline=time.monotonic() + 1) as lease:
            assert qmp.call('query-status') == {'running': False}
        assert lease.receipt()['complete']
    finally:
        qmp.close()
        gdb.close()
        worker.join(2)
    assert not worker.is_alive() and not failures and received == ['query-status']
