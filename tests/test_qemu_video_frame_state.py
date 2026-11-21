"""Selected stopped-state brackets at the real QMP and GDB packet parsers.

The peers provide independent authored CPU/RAM/input/pixel expectations. They
qualify the host contract only, not native cadence, mouse neutrality or native
whole-machine mutation authority. Root owns test and native execution.
"""
from copy import deepcopy
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_observation_authority import ObservationAuthority
from fdisbull.qemu_video_frame_state import (FORMAT, VIDEO_FRAME_STATE_COMMANDS,
    VideoFrameStateRefusal, frozen_video_frame_state_parameters,
    validate_video_frame_state_parameters)
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_operation_deadlines import Wire, packet
from test_qemu_video_frame import VideoWire, video


RANGES = [{'address': 0x7c00, 'length': 4}]
RAM = bytes.fromhex('fa f4 eb fd')
MONITOR = ('EAX=12345678 EIP=00007c00 EFL=00000002\n'
           'CS =0000 00000000 0000ffff 00009b00\n'
           'SS =0000 00000000 0000ffff 00009300\n'
           'CR0=00000010 CR2=00000000 CR3=00000000 CR4=00000000 '
           'EFER=0000000000000000 A20=1\n')


class StateWire(VideoWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.monitor = MONITOR
        self.keyboard = {
            'api-version': 1, 'epoch': 1, 'active': False, 'valid': True,
            'generation': 0, 'held': [], 'edge-capacity': 32,
            'repeat-supported': False, 'accepted-edges': 0,
            'device-path': '/machine/i8042/ps2-kbd', 'device-type': 'ps2-kbd',
            'scan-enabled': True, 'scancode-set': 2, 'translated': True,
            'modifier-mask': 0, 'fifo-count': 0, 'fifo-sha256': 'b' * 64,
            'controller-status': 0, 'controller-mode': 0,
            'controller-pending': 0, 'controller-obsrc': 0, 'controller-obdata': 0,
            'throttle-deadline-ns': -1, 'foreign-held': [],
            'fifo-read-pointer': 11, 'fifo-write-pointer': 11,
            'fifo-command-pointer': -1, 'write-command': -1,
        }
        self.change_input = lambda value: value
        self.change_keyboard = lambda value: value
        self.after_extra = lambda command: None

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in ('x-fdisbull-query-input', 'x-fdisbull-query-frame-keys',
                           'human-monitor-command'):
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-query-input':
            value = self.change_input({'api-version': 1, 'epoch': 1, 'state': 'idle',
                                       'virtual-ns': self.receipt['virtual-ns'], 'event-count': 0})
        elif command == 'x-fdisbull-query-frame-keys':
            value = self.change_keyboard(deepcopy(self.keyboard))
        else:
            assert args == {'command-line': 'info registers'}
            value = self.monitor
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency
        self.after_extra(command)


class StateGDBWire(Wire):
    def __init__(self, clock):
        super().__init__(clock, 'gdb')
        self.commands = self.requests
        self.values = dict(eax=0x12345678, eip=0x7c00, eflags=2, cs=0, ss=0)
        self.memory = {0x7c00 + index: value for index, value in enumerate(RAM)}
        self.after_reply = lambda command: None

    def sendall(self, data):
        if data == b'+' or data == b'\x03':
            return super().sendall(data)
        assert data.startswith(b'$') and data[-3:-2] == b'#'
        command = data[1:-3]
        self.commands.append(command)
        self.budgets.append(self.timeout)
        if command == b'g':
            reply = b''.join(value.to_bytes(4, 'little').hex().encode()
                             for value in self.values.values())
        elif command == b'qqemu.PhyMemMode':
            reply = self.mode
        elif command in (b'Qqemu.PhyMemMode:0', b'Qqemu.PhyMemMode:1'):
            self.mode = command[-1:]
            reply = b'OK'
        elif command.startswith(b'm'):
            address, length = (int(value, 16) for value in command[1:].split(b','))
            reply = bytes(self.memory.get(address + index, 0) for index in range(length)).hex().encode()
        elif command.startswith(b'M'):
            location, encoded = command[1:].split(b':')
            address, length = (int(value, 16) for value in location.split(b','))
            raw = bytes.fromhex(encoded.decode())
            assert len(raw) == length
            self.memory.update({address + index: value for index, value in enumerate(raw)})
            reply = b'OK'
        elif command.startswith(b'P'):
            number, encoded = command[1:].split(b'=')
            name = list(self.values)[int(number, 16)]
            self.values[name] = int.from_bytes(bytes.fromhex(encoded.decode()), 'little')
            reply = b'OK'
        else:
            pytest.fail('Unexpected source-state GDB request: ' + repr(command))
        self.buffer.extend(packet(reply))
        self.pending_delay = self.latency
        self.after_reply(command)


@pytest.fixture
def state_observation(video):
    o = video
    o.wire = StateWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.machine_configuration.update(memory_mib=16, accelerator='tcg', network='none')
    o.vm.qmp_commands |= VIDEO_FRAME_STATE_COMMANDS
    o.session.video_frame_start()
    o.wire.publish()
    wire = StateGDBWire(o.clock)
    remote = GDBRemote.__new__(GDBRemote)
    remote.socket, remote.operation_deadline = wire, None
    remote.lock, remote.console = threading.RLock(), []
    remote._buffer, remote._cursor, remote._packet_state = b'', 0, None
    remote.packet_size, remote.architecture = 4096, 'i386'
    remote.register_description = [dict(name=name, number=index, size=4)
                                   for index, name in enumerate(wire.values)]
    o.vm.gdb, o.gdb, o.gdb_wire = remote, remote, wire
    o.vm.process = SimpleNamespace(poll=lambda: None)
    authority = o.vm.observation_authority = ObservationAuthority(o.vm)
    authority.bind(qmp=o.qmp, gdb=remote)
    o.session.capabilities['video_frame_state_observe'] = True
    original_close = o.vm.close

    def close():
        authority.invalidate('authored owner closed')
        remote.close()
        original_close()

    o.vm.close = close
    o.wire.calls.clear()
    o.wire.budgets.clear()
    return o


def evidence(error):
    extra = getattr(error, 'video_frame_state_evidence', None)
    return extra if extra is not None else error.result


def observe(o, **kwargs):
    return o.session.video_frame_state_observe(ram_ranges=deepcopy(RANGES), **kwargs)


def test_selected_bracket_has_independent_exact_pixels_cpu_ram_and_narrow_claims(state_observation, monkeypatch):
    o = state_observation
    def forbidden(*args, **kwargs):
        pytest.fail('Passive source-state observation must not publish or execute')
    monkeypatch.setattr(o.session, '_event', forbidden)
    monkeypatch.setattr(o.session, '_artifact', forbidden)
    monkeypatch.setattr(o.session, '_stopped', forbidden)
    monkeypatch.setattr(o.gdb, 'execute', forbidden)
    result = observe(o)
    assert result['format'] == FORMAT and result['complete'] is True
    assert result['state_before'] == result['state_after']
    state = result['state_before']
    assert state['registers']['eax'] == '0x12345678'
    assert state['cpu']['cpu_mode'] == 'real' and state['cpu']['linear_pc'] == '0x7c00'
    assert state['ram'] == [dict(address=0x7c00, length=4, space='physical',
                                 data_hex='faf4ebfd', sha256=hashlib.sha256(RAM).hexdigest())]
    assert result['source']['rgb_verified'] and result['source']['rgb_bytes'] == 192000
    expected_pixels = bytes([4, 85, 170]) * 64000
    assert result['source']['pixel_sha256'] == hashlib.sha256(expected_pixels).hexdigest()
    assert result['source']['before'] == result['source']['after'] == result['source']['exported']
    assert result['clocks']['after']['sequence'] > result['clocks']['before']['sequence']
    assert result['clocks']['after']['virtual_ns'] == result['clocks']['before']['virtual_ns']
    assert result['input']['before'] == result['input']['after']
    assert result['input']['before']['keyboard']['throttle-deadline-ns'] == -1
    assert result['input']['before']['keyboard']['fifo-read-pointer'] == 11
    assert result['input']['mouse_state'] is result['input']['all_devices_neutral'] is None
    assert result['input']['guest_consumed'] is None
    assert not result['atomic'] and result['native_mutation_revision'] is None
    assert result['application_frame_complete'] is result['frame_state_equivalence'] is None
    assert result['legacy_phase_equivalence'] is None
    assert result['authority']['complete'] and result['authority']['valid']
    assert (result['authority']['control_generation_before']
            == result['authority']['control_generation_after'])
    assert result['authority']['native_state_revision'] is None
    assert o.session.capabilities['completed_guest_frames'] is False
    assert not hasattr(o.vm, '_physical_input')
    assert o.gdb_wire.mode == b'0'
    assert not list(o.directory.glob('video-frame-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    assert not any(command in ('cont', 'stop', 'screendump', 'input-send-event') for command, _ in o.wire.calls)
    assert not any(command.startswith((b'M', b'P', b'c')) for command in o.gdb_wire.commands)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    result['source']['before']['frame']['rows'][0]['row'] = 199
    assert o.vm._video_frame_last['frame']['rows'][0]['row'] == 0


@pytest.mark.parametrize('field,value', [
    ('foreign-held', ['a']), ('modifier-mask', 1), ('fifo-count', 1),
    ('fifo-command-pointer', 0), ('write-command', 0), ('controller-status', 1),
    ('controller-pending', 1), ('throttle-deadline-ns', 0),
    ('throttle-deadline-ns', 47001), ('scan-enabled', False), ('controller-mode', 0x10),
])
def test_non_neutral_native_keyboard_refuses_without_changing_a_healthy_owner(state_observation, field, value):
    o = state_observation
    o.wire.keyboard[field] = value
    with pytest.raises(VideoFrameStateRefusal) as caught:
        observe(o)
    result = evidence(caught.value)
    assert not result['complete'] and result['stage'] == 'input-before'
    assert result['input']['before']['keyboard'][field] == value
    assert result['state_before'] == {} and not o.vm.closed
    assert not o.gdb_wire.commands
    assert not any(command.startswith('x-fdisbull-export') for command, _ in o.wire.calls)


def test_empty_host_queue_cannot_substitute_for_native_schedule_witness(state_observation):
    o = state_observation
    o.wire.change_input = lambda value: dict(value, state='cancelled', token='prior',
                                             **{'event-count': 1})
    with pytest.raises(VideoFrameStateRefusal) as caught:
        observe(o)
    result = evidence(caught.value)
    assert result['input']['before']['host']['pending'] == []
    assert result['input']['before']['schedule']['state'] == 'cancelled'
    assert result['issues'][0]['code'] == 'native_schedule_not_initial'
    assert not o.vm.closed and not o.gdb_wire.commands


def test_active_native_keyboard_is_a_reusable_precondition_refusal(state_observation):
    o = state_observation
    o.wire.keyboard.update(active=True, token='foreign-owner', generation=1, held=['a'])
    with pytest.raises(VideoFrameStateRefusal) as caught:
        observe(o)
    result = evidence(caught.value)
    assert result['issues'][0]['code'] == 'native_keyboard_owner_active'
    assert result['input']['before']['keyboard']['held'] == ['a']
    assert not o.vm.closed and result['authority']['valid']
    # The peer authors an explicit later released/inactive state. The observer
    # did not detach it, inject a release or alter the received state itself.
    o.wire.keyboard.update(active=False, generation=2, held=[])
    del o.wire.keyboard['token']
    assert observe(o)['complete']


@pytest.mark.parametrize('field,value', [('pending', [{'kind': 'key', 'key': 'a'}]),
                                         ('leases', {'owned': {'kind': 'button'}}),
                                         ('valid', False)])
def test_host_pending_or_invalid_ownership_refuses_without_native_input_mutation(state_observation, field, value):
    o = state_observation
    o.vm._physical_input = dict(session_id='authored', valid=True, invalid_reason=None,
                               sequence=0, pending=[], leases={}, last_delivery=None,
                               invalidated_edges=0, invalidated_leases=0)
    o.vm._physical_input[field] = value
    before = deepcopy(o.vm._physical_input)
    with pytest.raises(VideoFrameStateRefusal) as caught:
        observe(o)
    assert evidence(caught.value)['issues'][0]['code'] == 'host_input_not_neutral'
    assert o.vm._physical_input == before and not o.vm.closed
    assert not any(command == 'x-fdisbull-query-input' for command, _ in o.wire.calls)


@pytest.mark.parametrize('target', ['ram', 'register', 'keyboard', 'clock-status'])
def test_changed_projection_or_witness_with_stable_guest_time_keeps_actual_evidence(state_observation, target):
    o = state_observation
    clock = o.wire.receipt['virtual-ns']
    def mutate():
        if not any(command == 'x-fdisbull-export-video-frame' for command, _ in o.wire.calls):
            return
        if target == 'ram':
            o.gdb_wire.memory[0x7c00] = 0x90
        elif target == 'register':
            o.gdb_wire.values['eax'] = 0x87654321
        elif target == 'keyboard':
            o.wire.keyboard['fifo-sha256'] = 'c' * 64
        else:
            o.wire.receipt['status'] = 'debug'
    o.wire.after_video = mutate
    with pytest.raises(DebuggerError) as caught:
        observe(o)
    result = evidence(caught.value)
    assert not result['complete'] and result['issues'] and result['source']['rgb_verified']
    assert result['clocks']['before']['virtual_ns'] == clock == o.wire.receipt['virtual-ns']
    assert o.vm.closed
    if target in ('ram', 'register'):
        assert result['state_before'] != result['state_after']
    elif target == 'keyboard':
        assert result['input']['before']['keyboard']['fifo-sha256'] == 'b' * 64
        assert result['input']['after']['keyboard']['fifo-sha256'] == 'c' * 64


def test_real_public_write_attempt_is_refused_before_dispatch_despite_stable_clock(state_observation):
    o = state_observation
    seen = []
    def mutate():
        if not any(command == 'x-fdisbull-export-video-frame' for command, _ in o.wire.calls):
            return
        try:
            o.session.write_memory(0x7c00, '90f4ebfd', expected_hex='faf4ebfd')
        except DebuggerError as error:
            seen.append(str(error))
    o.wire.after_video = mutate
    initial = o.wire.receipt['virtual-ns']
    with pytest.raises(DebuggerError) as caught:
        observe(o)
    assert seen and 'reentrant public operation' in seen[0]
    assert o.wire.receipt['virtual-ns'] == initial
    assert not any(command.startswith(b'M') for command in o.gdb_wire.commands)
    assert bytes(o.gdb_wire.memory[0x7c00 + i] for i in range(4)) == RAM
    result = evidence(caught.value)
    assert result['authority']['valid'] is False and not result['complete']
    assert result['state_before']['ram'][0]['data_hex'] == 'faf4ebfd'
    assert o.vm.closed


def test_real_raw_memory_write_and_restore_attempt_cannot_hide_behind_equal_clock_or_bytes(state_observation):
    o = state_observation
    errors = []
    def aba():
        if not any(command == 'x-fdisbull-export-video-frame' for command, _ in o.wire.calls):
            return
        for replacement in (b'\x90\xf4\xeb\xfd', RAM):
            try:
                o.gdb.memory(0x7c00, 4, data=replacement)
            except DebuggerError as error:
                errors.append(str(error))
    o.wire.after_video = aba
    initial = o.wire.receipt['virtual-ns']
    with pytest.raises(DebuggerError) as caught:
        observe(o)
    assert errors and not any(command.startswith(b'M') for command in o.gdb_wire.commands)
    assert bytes(o.gdb_wire.memory[0x7c00 + i] for i in range(4)) == RAM
    assert o.wire.receipt['virtual-ns'] == initial
    assert not evidence(caught.value)['complete'] and o.vm.closed


@pytest.mark.parametrize('range_value', [[], [{'address': True, 'length': 4}],
    [{'address': 0xa0000, 'length': 1}], [{'address': 0x9ffff, 'length': 2}],
    [{'address': 0xc0000000, 'length': 1}], [{'address': 0, 'length': 4097}],
    [{'address': 0, 'length': 4}, {'address': 3, 'length': 1}],
    [{'address': i * 4096, 'length': 4096} for i in range(5)]])
def test_invalid_ranges_refuse_before_any_native_io(state_observation, range_value):
    o = state_observation
    with pytest.raises(ValueError):
        o.session.video_frame_state_observe(ram_ranges=range_value)
    assert not o.wire.calls and not o.gdb_wire.commands and not o.vm.closed


def test_visible_literals_validate_beside_references_and_frozen_parameters_are_owned():
    validate_video_frame_state_parameters(ram_ranges=[{'address': '$address', 'length': 4}],
                                         allow_references=True)
    with pytest.raises(ValueError):
        validate_video_frame_state_parameters(ram_ranges=[{'address': 0xa0000, 'length': '$n'}],
                                             allow_references=True)
    ranges = deepcopy(RANGES)
    frozen = frozen_video_frame_state_parameters(ram_ranges=ranges)
    ranges[0]['address'] = 0xa0000
    assert frozen['ram_ranges'] == RANGES


def test_caller_mutation_during_lock_admission_cannot_change_the_owned_selection(state_observation):
    o = state_observation
    ranges = deepcopy(RANGES)
    original = o.vm.lock
    class AdmissionLock:
        changed = False

        def acquire(self, timeout=-1):
            if not self.changed:
                self.changed = True
                ranges[0]['address'] = 0xa0000
                ranges.append({'address': 0xc0000000, 'length': 1})
            return original.acquire(timeout=timeout)

        def release(self):
            original.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    o.vm.lock = AdmissionLock()
    result = o.session.video_frame_state_observe(ram_ranges=ranges)
    assert result['complete'] and result['selection']['ram_ranges'] == RANGES
    assert result['state_before']['ram'][0]['data_hex'] == 'faf4ebfd'
    assert ranges[0]['address'] == 0xa0000 and len(ranges) == 2


def test_missing_initialized_gdb_and_out_of_ram_selection_refuse_without_reconnecting(state_observation):
    o = state_observation
    remote = o.vm.gdb
    o.vm.gdb = None
    try:
        with pytest.raises(VideoFrameStateRefusal, match='already initialized'):
            observe(o)
        assert not o.wire.calls and not o.vm.closed
    finally:
        o.vm.gdb = remote
    with pytest.raises(VideoFrameStateRefusal, match='configured'):
        o.session.video_frame_state_observe(ram_ranges=[{'address': 16 << 20, 'length': 1}])
    assert not o.wire.calls and not o.gdb_wire.commands and not o.vm.closed


def test_bad_export_retains_before_state_and_closes_only_original_owner(state_observation):
    o = state_observation
    o.wire.bad_export = True
    with pytest.raises(DebuggerError) as caught:
        observe(o)
    result = evidence(caught.value)
    assert result['stage'] == 'source-export' and not result['complete']
    assert result['state_before']['ram'][0]['data_hex'] == 'faf4ebfd'
    assert result['state_after'] == {} and not result['source']['rgb_verified']
    assert o.vm.closed and not list(o.directory.glob('video-frame-*.ppm'))


def test_native_reply_whitespace_counts_against_observation_transport_budget(state_observation):
    o = state_observation
    original = o.wire.sendall
    def padded(data):
        original(data)
        if json.loads(data)['execute'] == 'x-fdisbull-query-frame-keys':
            o.wire.buffer[:0] = b' ' * (128 * 1024)
    o.wire.sendall = padded
    with pytest.raises(DebuggerError, match='budget') as caught:
        observe(o)
    assert evidence(caught.value)['stage'] == 'input-before' and o.vm.closed
    assert not o.gdb_wire.commands


def test_original_deadline_covers_every_query_and_gdb_read(state_observation):
    o = state_observation
    o.vm.operation_deadline = o.clock.now + .05
    o.qmp.operation_deadline = o.clock.now + .04
    o.wire.latency = .003
    with pytest.raises(TimeoutError) as caught:
        observe(o, timeout_ms=1000)
    result = evidence(caught.value)
    assert not result['complete'] and o.vm.closed
    assert max(o.wire.budgets) <= .04 + 1e-8
    assert all(later <= earlier for earlier, later in zip(o.wire.budgets, o.wire.budgets[1:]))
    assert o.qmp.operation_deadline == 100.04


def test_outer_wrapper_expiry_after_successful_lease_returns_incomplete_evidence(state_observation, monkeypatch):
    from fdisbull import qemu_machine
    o = state_observation
    previous = dict(session=o.clock.now + .09, vm=o.clock.now + .08,
                    qmp=o.clock.now + .05, gdb=o.clock.now + .07)
    o.session._deadline = previous['session']
    o.vm.operation_deadline = previous['vm']
    o.qmp.operation_deadline = previous['qmp']
    o.gdb.operation_deadline = previous['gdb']
    native_time = o.wire.receipt['virtual-ns']
    original = qemu_machine._machine_async_guard
    unnamed = []

    def expire_after_method(session, name=None, args=(), kwargs=None):
        original(session, name, args, kwargs)
        if name is None:
            unnamed.append(name)
            if len(unnamed) == 2:
                # Admission is the first unnamed guard. The second is the
                # real wrapper's check after the observer and lease returned.
                assert o.vm.observation_authority._active is None
                assert o.vm.observation_authority._cleanup_owner is None
                assert o.vm.operation_deadline == previous['qmp']
                o.clock.now = previous['qmp'] + .001

    monkeypatch.setattr(qemu_machine, '_machine_async_guard', expire_after_method)
    with pytest.raises(TimeoutError) as caught:
        observe(o, timeout_ms=1000)
    result = caught.value.result
    assert len(unnamed) == 2
    assert result['format'] == FORMAT and result['complete'] is False
    assert result['stage'] == 'outer-deadline'
    assert result['issues'][-1]['code'] == 'outer_deadline'
    assert result['issues'][-1]['stage'] == 'outer-deadline'
    assert result['source']['rgb_verified'] and result['state_before'] == result['state_after']
    assert result['clocks']['before']['virtual_ns'] == result['clocks']['after']['virtual_ns'] == native_time
    assert o.wire.receipt['virtual-ns'] == native_time
    assert o.vm.closed and o.qmp.socket is None and o.gdb.socket is None
    assert o.session._deadline == previous['session']
    assert o.vm.operation_deadline == previous['vm']
    assert o.qmp.operation_deadline == previous['qmp']
    assert o.gdb.operation_deadline == previous['gdb']


def test_lock_replacement_releases_only_the_original_acquired_lock(state_observation):
    o = state_observation
    original = o.vm.lock

    class ReplacementLock:
        acquisitions = 0
        releases = 0

        def acquire(self, **kwargs):
            self.acquisitions += 1
            pytest.fail('Observation must never acquire the replacement lock')

        def release(self):
            self.releases += 1
            pytest.fail('Observation must release its captured original lock')

    replacement = ReplacementLock()
    def replace(command):
        if command == 'x-fdisbull-query-frame-keys':
            o.vm.lock = replacement
    o.wire.after_extra = replace
    try:
        with pytest.raises(DebuggerError) as caught:
            observe(o)
        assert not evidence(caught.value)['complete'] and o.vm.closed
        assert replacement.acquisitions == replacement.releases == 0
        acquired = []

        def probe_original_lock():
            accepted = original.acquire(timeout=.1)
            acquired.append(accepted)
            if accepted:
                original.release()

        thread = threading.Thread(target=probe_original_lock)
        thread.start()
        thread.join(timeout=1)
        assert not thread.is_alive() and acquired == [True]
        assert o.vm.operation_deadline is None
        assert o.qmp.operation_deadline is None and o.gdb.operation_deadline is None
    finally:
        o.vm.lock = original


def test_owner_replacement_during_native_reply_never_reads_or_closes_replacement(state_observation):
    o = state_observation
    replacement = SimpleNamespace(closed=False, qmp=SimpleNamespace(operation_deadline=None))
    def replace(command):
        if command == 'x-fdisbull-query-frame-keys':
            o.session.vm = replacement
    o.wire.after_extra = replace
    try:
        with pytest.raises(DebuggerError) as caught:
            observe(o)
        result = evidence(caught.value)
        assert not result['complete'] and o.vm.closed and not replacement.closed
        assert replacement.qmp.operation_deadline is None
        assert not o.gdb_wire.commands
    finally:
        o.session.vm = o.vm
