"""Host admission of an explicit native stopped-control scope.

These packet peers test host contracts, including ABA-shaped evidence. They
do not qualify QEMU dispatch coverage or native execution.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_video_frame_state import VideoFrameStateRefusal
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation
from test_qemu_video_frame import video
from test_qemu_video_frame_state import state_observation, observe, evidence


ARM = 'x-fdisbull-arm-stopped-control'
QUERY = 'x-fdisbull-query-stopped-control'
PROCESS = '12345678-1234-4234-8234-123456789abc'


@pytest.fixture
def native_state(state_observation):
    o = state_observation
    o.session.video_frame_rgba()
    o.vm.qmp_commands |= {ARM, QUERY}
    o.native = dict(**{'api-version': 1, 'model': 'qemu-stopped-control-v1',
                       'process-id': PROCESS}, token='0' * 32, generation=17,
                    epoch=1, state='armed', busy=False)
    o.native_change = lambda value: value
    original = o.wire.sendall

    def send(data):
        request = json.loads(data)
        command, arguments = request['execute'], request.get('arguments', {})
        if command not in (ARM, QUERY):
            return original(data)
        o.wire.calls.append((command, deepcopy(arguments)))
        o.wire.budgets.append(o.wire.timeout)
        assert set(arguments) == {'token'}
        if command == ARM:
            o.native['token'] = arguments['token']
        else:
            assert arguments['token'] == o.native['token']
        value = o.native_change(deepcopy(o.native))
        o.wire.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        o.wire.delay = o.wire.latency

    o.wire.sendall = send
    o.wire.calls.clear()
    return o


def arm(o):
    return o.session.stopped_control_arm(timeout_ms=1000)


def test_explicit_native_scope_uses_cached_rgb_and_passive_brackets(native_state):
    o = native_state
    armed = arm(o)
    assert armed['complete'] is True and armed['native']['process-id'] == PROCESS
    assert armed['token'] == armed['native']['token']
    o.wire.calls.clear()
    result = observe(o, native_control_token=armed['token'])
    assert result['complete'] is True
    assert result['native_mutation_revision'] is None and result['atomic'] is False
    native = result['native_control']
    assert native['scope'] == 'stopped-native-control-admission-v1'
    assert native['complete'] is True and native['before'] == native['after']
    assert native['before']['generation'] == 17
    assert result['source']['rgb_verified'] is True
    assert result['source']['exported'] is None
    assert result['source']['rgb_origin'] == 'previously-verified-immutable-export'
    assert result['state_before'] == result['state_after']
    commands = [name for name, _ in o.wire.calls]
    assert commands[0] == QUERY and commands[-1] == QUERY
    assert commands.count(QUERY) == 2
    assert 'x-fdisbull-export-video-frame' not in commands
    assert not o.vm.closed


def test_native_aba_refuses_equal_final_selected_values(native_state):
    o = native_state
    token = arm(o)['token']
    generations = []

    def intervening_native_edit(command):
        if command == b'g' and not generations:
            before = o.vm.observation_authority.control_generation
            original = o.gdb_wire.memory[0x7c00]
            o.gdb_wire.memory[0x7c00] = 0x5a
            o.native['generation'] += 1
            o.gdb_wire.memory[0x7c00] = original
            o.native['generation'] += 1
            generations.append((before, o.vm.observation_authority.control_generation))

    o.gdb_wire.after_reply = intervening_native_edit
    with pytest.raises(DebuggerError, match='Native stopped-control identity changed') as caught:
        observe(o, native_control_token=token)
    result = evidence(caught.value)
    assert generations and generations[0][0] == generations[0][1]
    assert result['complete'] is False and result['native_control']['complete'] is False
    assert result['state_before'] == result['state_after']
    assert result['native_control']['before']['generation'] == 17
    assert result['native_control']['after']['generation'] == 19
    assert result['native_mutation_revision'] is None and o.vm.closed


@pytest.mark.parametrize('mutation', [
    {'generation': True}, {'generation': -1}, {'generation': 1 << 64},
    {'epoch': True}, {'epoch': 2}, {'busy': 0}, {'busy': True},
    {'api-version': 2}, {'model': 'other'}, {'token': 'f' * 32},
    {'process-id': '12345678123442348234123456789abc'},
    {'process-id': '87654321-4321-4321-8321-cba987654321'},
    {'process-id': PROCESS.upper()}, {'extra': 1},
    {'state': 'retired', 'reason': 'unknown control'},
    {'state': 'armed', 'reason': 'previous retirement'},
])
def test_native_receipt_failure_never_falls_back(native_state, mutation):
    o = native_state
    token = arm(o)['token']
    o.native_change = lambda value: dict(value, **mutation)
    o.wire.calls.clear()
    o.gdb_wire.commands.clear()
    with pytest.raises(DebuggerError) as caught:
        observe(o, native_control_token=token)
    result = evidence(caught.value)
    assert result['complete'] is False
    assert result['native_control']['before'] is not None
    assert result['native_control']['after'] is None
    assert o.gdb_wire.commands == [] and o.vm.closed
    assert [name for name, _ in o.wire.calls] == [QUERY]


@pytest.mark.parametrize('replacement', [None, b'x' * 192000, bytearray(192000)],
                         ids=['missing', 'wrong-bytes', 'mutable'])
def test_arm_requires_a_verified_immutable_rgb_cache(native_state, replacement):
    o = native_state
    o.vm._video_frame_owned_rgb = replacement
    with pytest.raises(VideoFrameStateRefusal, match='cached'):
        arm(o)
    assert ARM not in [name for name, _ in o.wire.calls]
    assert not o.vm.closed


def test_requested_native_scope_requires_its_original_binding(native_state):
    o = native_state
    with pytest.raises(VideoFrameStateRefusal, match='scope'):
        observe(o, native_control_token='a' * 32)
    assert o.wire.calls == [] and not o.vm.closed


def test_scope_cannot_be_rearmed_by_host(native_state):
    o = native_state
    arm(o)
    count = sum(name == ARM for name, _ in o.wire.calls)
    with pytest.raises(VideoFrameStateRefusal, match='already'):
        arm(o)
    assert sum(name == ARM for name, _ in o.wire.calls) == count


@pytest.mark.parametrize('token', ['', 'a' * 31, 'A' * 32, 'g' * 32, True, {}, []])
def test_native_token_is_validated_before_any_dispatch(native_state, token):
    o = native_state
    with pytest.raises(ValueError):
        observe(o, native_control_token=token)
    assert o.wire.calls == []


def test_default_cooperative_observation_still_exports(native_state):
    o = native_state
    result = observe(o)
    assert result['complete'] is True and result.get('native_control') is None
    assert 'x-fdisbull-export-video-frame' in [name for name, _ in o.wire.calls]


@pytest.mark.parametrize('mutation', [
    {'generation': 16}, {'generation': True}, {'generation': 1 << 64},
    {'process-id': '87654321-4321-4321-8321-cba987654321'},
    {'token': 'f' * 32}, {'epoch': 2}, {'busy': True}, {'extra': 1},
    {'state': 'retired', 'reason': 'unsupported command'},
])
def test_after_receipt_is_preserved_before_validation(native_state, mutation):
    o = native_state
    token = arm(o)['token']
    count = []

    def change(value):
        count.append(1)
        return dict(value, **mutation) if len(count) == 2 else value

    o.native_change = change
    with pytest.raises(DebuggerError) as caught:
        observe(o, native_control_token=token)
    result = evidence(caught.value)
    assert result['complete'] is False and result['state_before'] == result['state_after']
    assert result['native_control']['before']['generation'] == 17
    assert all(result['native_control']['after'][key] == value for key, value in mutation.items())
    assert o.vm.closed


def test_uncertain_arm_reply_is_retained_and_original_owner_closed(native_state):
    o = native_state
    o.native_change = lambda value: dict(value, generation=True)
    with pytest.raises(DebuggerError) as caught:
        arm(o)
    assert caught.value.result['native']['generation'] is True
    assert caught.value.result['complete'] is False and o.vm.closed


def test_cached_source_identity_cannot_change_after_arm(native_state):
    o = native_state
    token = arm(o)['token']
    o.wire.publish()
    with pytest.raises((DebuggerError, VideoFrameStateRefusal)) as caught:
        observe(o, native_control_token=token)
    assert evidence(caught.value)['complete'] is False


@pytest.mark.parametrize('field', ['process', 'qmp', 'gdb'])
def test_arm_binding_cannot_follow_replaced_owner(native_state, field):
    o = native_state
    token = arm(o)['token']
    original = getattr(o.vm, field)
    setattr(o.vm, field, object())
    try:
        with pytest.raises(DebuggerError) as caught:
            observe(o, native_control_token=token)
        assert evidence(caught.value)['complete'] is False
        assert QUERY not in [name for name, _ in o.wire.calls]
    finally:
        setattr(o.vm, field, original)


def test_supported_native_write_between_observations_moves_the_accepted_floor(native_state):
    o = native_state
    token = arm(o)['token']
    first = observe(o, native_control_token=token)
    o.native['generation'] = 19
    o.gdb_wire.memory[0x7c00] = 0x5a
    second = observe(o, native_control_token=token)
    assert first['native_control']['before']['generation'] == 17
    assert second['native_control']['before']['generation'] == 19
    assert second['state_before'] == second['state_after']
    assert second['state_before']['ram'][0]['data_hex'].startswith('5a')
    o.native['generation'] = 18
    o.wire.calls.clear()
    with pytest.raises(DebuggerError, match='regressed') as caught:
        observe(o, native_control_token=token)
    assert evidence(caught.value)['native_control']['before']['generation'] == 18
    assert [name for name, _ in o.wire.calls] == [QUERY]


@pytest.mark.parametrize('protocol', ['qmp', 'gdb'])
def test_original_channel_is_closed_without_touching_replacement(native_state, protocol):
    from types import SimpleNamespace
    o = native_state
    token = arm(o)['token']
    client = getattr(o.vm, protocol)
    original = client.socket
    touched, original_closes = [], []
    close = original.close

    def original_close():
        original_closes.append(1)
        close()

    original.close = original_close
    foreign = SimpleNamespace(closed=False, recv=lambda *_: touched.append('recv'),
        sendall=lambda *_: touched.append('send'), close=lambda: touched.append('close'))
    client.socket = foreign
    with pytest.raises(DebuggerError, match='original owner'):
        observe(o, native_control_token=token)
    assert touched == [] and original_closes
    assert client.socket is foreign


def test_native_query_grant_is_exact_and_unavailable_in_a_default_lease(native_state):
    o = native_state
    token = arm(o)['token']
    authority = o.vm.observation_authority
    with pytest.raises(DebuggerError, match='unadmitted protocol'):
        with authority.observe(o.session, deadline=o.clock.now + 1):
            o.qmp.call(QUERY, {'token': token})
    assert QUERY not in [name for name, _ in o.wire.calls]


def test_native_query_cannot_smuggle_extra_arguments(native_state):
    o = native_state
    token = arm(o)['token']
    authority = o.vm.observation_authority
    with pytest.raises(DebuggerError, match='unadmitted protocol'):
        with authority.observe(o.session, deadline=o.clock.now + 1, native_control_token=token):
            o.qmp.call(QUERY, {'token': token, 'repair': True})
    assert QUERY not in [name for name, _ in o.wire.calls]


@pytest.mark.parametrize('moment', ['lock', 'guard', 'failing-guard'])
def test_replacement_during_wrapper_admission_closes_original_with_evidence(native_state, moment):
    from types import SimpleNamespace
    o = native_state
    original_lock = o.vm.lock
    replacement = SimpleNamespace(closed=False, qmp=SimpleNamespace(operation_deadline=None))
    touched = []
    replacement.close = lambda: touched.append('close')

    class AdmissionLock:
        enabled = False
        changed = False

        def acquire(self, timeout=-1):
            acquired = original_lock.acquire(timeout=timeout)
            if self.enabled and not self.changed:
                self.changed = True
                o.session.vm = replacement
            return acquired

        def release(self):
            original_lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    if moment == 'lock':
        # Capture this lock during arm, then enable its waiting callback.
        o.vm.lock = AdmissionLock()
        token = arm(o)['token']
        o.vm.lock.enabled = True
    else:
        token = arm(o)['token']
        def guard(name):
            o.session.vm = replacement
            if moment == 'failing-guard':
                raise RuntimeError('authored admission failure')
        o.vm.operation_guard = guard
    try:
        with pytest.raises(DebuggerError) as caught:
            observe(o, native_control_token=token)
        result = evidence(caught.value)
        assert result['format'] == 'fdisbull-source-raster-state-observation-1'
        assert result['stage'] == 'original-owner-binding' and not result['complete']
        assert o.vm.closed and not touched and replacement.qmp.operation_deadline is None
    finally:
        o.session.vm = o.vm
        o.vm.lock = original_lock


def test_outer_deadline_keeps_primary_receipt_when_original_cleanup_fails(native_state, monkeypatch):
    o = native_state
    token = arm(o)['token']
    from fdisbull import qemu_video_frame_state as module
    original_copy = module._copy
    expired = []

    def copying(value, **kwargs):
        result = original_copy(value, **kwargs)
        if (not expired and type(value) is dict
                and value.get('format') == 'fdisbull-qemu-observation-authority-1'
                and value.get('complete') is True):
            expired.append(1)
            o.clock.now += 2
        return result

    monkeypatch.setattr(module, '_copy', copying)
    binding = o.session._native_stopped_control_binding
    original_close = binding.close_original

    def close():
        original_close()
        raise OSError('authored cleanup failure')

    monkeypatch.setattr(binding, 'close_original', close)
    with pytest.raises(TimeoutError) as caught:
        observe(o, native_control_token=token)
    assert caught.value.result['stage'] == 'outer-deadline'
    assert caught.value.result['complete'] is False
    assert caught.value.result['native_control']['complete'] is False
    assert caught.value.native_stopped_control_cleanup_error == 'OSError'
    assert o.vm.closed


def test_admission_failure_does_not_replace_its_first_cleanup_error(native_state, monkeypatch):
    from types import SimpleNamespace
    o = native_state
    token = arm(o)['token']
    binding = o.session._native_stopped_control_binding
    original_close = binding.close_original
    closes = []

    def close():
        closes.append(1)
        original_close()
        if len(closes) == 1:
            raise OSError('first original-owner cleanup failed')

    def guard(name):
        o.session.vm = SimpleNamespace()

    monkeypatch.setattr(binding, 'close_original', close)
    o.vm.operation_guard = guard
    try:
        with pytest.raises(DebuggerError) as caught:
            observe(o, native_control_token=token)
        assert closes == [1]
        assert caught.value.result['stage'] == 'original-owner-binding'
        assert caught.value.native_stopped_control_cleanup_error == 'OSError'
    finally:
        o.session.vm = o.vm
