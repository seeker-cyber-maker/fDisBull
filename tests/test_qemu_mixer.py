"""Optional passive native mixer readback through real QMP envelopes.

Peers below supply protocol/admission evidence only; paired-tone rendering and
native passivity remain separate native qualification gates.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_audio import AUDIO_COMMANDS, admit_audio, machine_audio_configuration
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from fdisbull.qemu_cpu_undo_guard import before_operation
from fdisbull.qemu_dos_history import QemuDOSHistoryMixin
from fdisbull.qemu_dos_le_history import LESourceHistoryProvider
from fdisbull.qemu_machine import MachineContext
from test_qemu_audio import AudioWire
from test_qemu_io_deadlines import observation
from test_qemu_opl import OplAdmission


COMMAND = 'x-fdisbull-query-mixer'
SCALE = 1 << 32


def test_mixer_observation_has_direct_json_and_saved_script_routes():
    assert callable(getattr(MachineContext, 'mixer_observe', None))
    assert 'debug-mixer-observe' in METHODS
    assert OPERATIONS.get('mixer-observe') == 'mixer_observe'


def pcm(rate=32000, channels=1, bits=8, signed=False):
    frame = channels * bits // 8
    return {'rate': rate, 'channels': channels, 'bits': bits, 'is-signed': signed,
            'swap-endianness': False, 'bytes-per-frame': frame,
            'bytes-per-second': rate * frame}


def native_reply(profile='sb16-opl'):
    # Authored literal API-1 contract, not a response made by the validator.
    adlib = {'card-id': 'adlib', 'voice-id': 'adlib', 'active': True,
             'hardware-enabled': True, 'hardware-pending-disable': False,
             'software-volume-applied': True, 'format': pcm(bits=16, signed=True),
             'hardware-format': pcm(),
             'gain': {'left': SCALE, 'right': SCALE, 'mute': False}}
    sb = {'card-id': 'sb16', 'voice-id': 'sb16', 'active': True,
          'hardware-enabled': True, 'hardware-pending-disable': False,
          'software-volume-applied': True, 'format': pcm(11025, 2),
          'hardware-format': pcm(),
          'gain': {'left': SCALE // 2, 'right': SCALE // 4, 'mute': False}}
    voices = [adlib, sb] if profile == 'sb16-opl' else [sb]
    return {'api-version': 1, 'gain-scale': SCALE,
            'mono-input': 'duplicate-to-left-right', 'mono-output': 'sum-then-clip',
            'stereo-output': 'clip-left-right', 'audiodevs': [{
                'audiodev-id': 'fdisbull-' + profile, 'driver': 'none',
                'mixing-engine': True, 'cards': ['adlib', 'sb16'] if profile == 'sb16-opl' else ['sb16'],
                'voices': voices, 'captures': []}]}


class MixerWire(AudioWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.mixer = native_reply()
        self.mutate_mixer = lambda value: value
        self.after_mixer = lambda: None

    def sendall(self, data):
        request = json.loads(data)
        if request['execute'] != COMMAND:
            return super().sendall(data)
        assert request.get('arguments', {}) == {}
        self.calls.append((COMMAND, {}))
        self.budgets.append(self.timeout)
        value = self.mutate_mixer(deepcopy(self.mixer))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency
        self.after_mixer()


@pytest.fixture
def mixer(observation):
    o = observation
    o.wire = MixerWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands = AUDIO_COMMANDS | VIRTUAL_CLOCK_COMMANDS | {COMMAND}
    o.vm.machine_configuration.update(clock_profile=machine_clock_configuration('virtual', 1),
        audio_profile=machine_audio_configuration('sb16-opl', 'virtual'))
    o.session.capabilities.update(audio_capture=True, mixer_gain_readback=True, virtual_clock_budget=True)
    return o


def script(*steps):
    return {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': list(steps)}


def event_count(o):
    return o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='machine-mixer-observe'").fetchone()[0]


def test_exact_graph_is_persisted_without_running_or_starting_capture(mixer):
    o = mixer
    before = deepcopy((o.wire.mixer, o.wire.audio, o.wire.receipt, o.wire.counter, o.session.registers()))
    first = o.session.mixer_observe()
    second = o.session.mixer_observe()
    assert first['format'] == 'fdisbull-machine-mixer-1' and first['context'] == 'machine'
    assert first['run'] == o.session.run_id and first['epoch'] == first['clock']['epoch']
    assert first['observed_ns'] == first['clock']['virtual_ns'] == 1000
    assert first['native'] == second['native'] == before[0]
    assert first['clock']['counter'] == first['clocks']['after']['counter']
    assert first['clock']['virtual_ns'] == first['clocks']['after']['virtual_ns']
    assert first['epoch'] == first['clocks']['after']['epoch'] == second['epoch']
    assert before == (o.wire.mixer, o.wire.audio, o.wire.receipt, o.wire.counter, o.session.registers())
    assert o.wire.audio['state'] == 'idle' and o.wire.mixer['audiodevs'][0]['captures'] == []
    allowed = {'query-status', 'query-replay', 'x-fdisbull-query-clock', COMMAND}
    assert all(command in allowed for command, _ in o.wire.calls)
    assert event_count(o) == 2 and not o.vm.closed
    rows = o.project.db.execute("SELECT evidence FROM debug_events WHERE operation='machine-mixer-observe'").fetchall()
    assert [json.loads(r['evidence']) for r in rows] == [first, second]
    first['native']['audiodevs'][0]['voices'][0]['gain']['left'] = 0
    assert o.wire.mixer == before[0]  # Returned metadata cannot mutate the live graph.


@pytest.mark.parametrize('profile', ['sb16', 'sb16-opl'])
def test_initial_registered_cards_need_no_fabricated_voice_or_capture(mixer, profile):
    o = mixer
    o.vm.machine_configuration['audio_profile'] = machine_audio_configuration(profile, 'virtual')
    o.wire.mixer = native_reply(profile)
    o.wire.mixer['audiodevs'][0]['voices'] = [] if profile == 'sb16' else [deepcopy(o.wire.mixer['audiodevs'][0]['voices'][0])]
    for v in o.wire.mixer['audiodevs'][0]['voices']:
        v.update(active=False, **{'hardware-enabled': False})
    result = o.session.mixer_observe()
    assert result['native'] == o.wire.mixer
    assert result['native']['audiodevs'][0]['captures'] == []
    assert not o.vm.closed


def test_attached_capture_format_and_separate_mute_are_retained(mixer):
    o = mixer
    device = o.wire.mixer['audiodevs'][0]
    device['captures'] = [{'format': pcm(), 'enabled': True}]
    device['voices'][1]['gain']['mute'] = True
    result = o.session.mixer_observe()
    assert result['native'] == o.wire.mixer
    gain = result['native']['audiodevs'][0]['voices'][1]['gain']
    assert gain == {'left': SCALE // 2, 'right': SCALE // 4, 'mute': True}
    assert 'master' not in result['native']  # No inferred global gain is manufactured.


@pytest.mark.parametrize('path,value', [
    (('api-version',), True), (('api-version',), 2), (('gain-scale',), float(SCALE)),
    (('mono-output',), 'average'),
    (('audiodevs', 0, 'voices', 0, 'gain', 'left'), -1),
    (('audiodevs', 0, 'voices', 0, 'gain', 'left'), SCALE + 1),
    (('audiodevs', 0, 'voices', 0, 'gain', 'left'), True),
    (('audiodevs', 0, 'voices', 0, 'gain', 'right'), 0.5),
    (('audiodevs', 0, 'voices', 0, 'gain', 'right'), float('nan')),
    (('audiodevs', 0, 'voices', 0, 'gain', 'mute'), 0),
    (('audiodevs', 0, 'voices', 0, 'active'), 1),
    (('audiodevs', 0, 'voices', 0, 'card-id'), 'unregistered'),
    (('audiodevs', 0, 'voices', 0, 'voice-id'), ''),
    (('audiodevs', 0, 'voices', 0, 'voice-id'), 'x' * 129),
    (('audiodevs', 0, 'voices', 0, 'voice-id'), '\ud800'),
    (('audiodevs', 0, 'voices', 0, 'format', 'rate'), 0),
    (('audiodevs', 0, 'voices', 0, 'format', 'bits'), 24),
    (('audiodevs', 0, 'voices', 0, 'format', 'bytes-per-frame'), 1),
    (('audiodevs', 0, 'voices', 0, 'format', 'bytes-per-second'), 1),
    (('audiodevs', 0, 'voices', 0, 'hardware-format', 'is-signed'), 0),
    (('audiodevs', 0, 'audiodev-id'), 'fdisbull-sb16'),
    (('audiodevs', 0, 'driver'), 'coreaudio'),
    (('audiodevs', 0, 'mixing-engine'), False),
])
def test_malformed_gain_format_or_profile_refuses_without_mixer_evidence(mixer, path, value):
    o = mixer
    def mutate(reply):
        node = reply
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return reply
    o.wire.mutate_mixer = mutate
    with pytest.raises(DebuggerError, match='mixer'):
        o.session.mixer_observe()
    assert o.vm.closed and event_count(o) == 0
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('mutation', ['device-duplicate', 'cards-duplicate', 'voice-duplicate',
                                      'voice-unsorted', 'capture-duplicate', 'over-limit'])
def test_ambiguous_or_unbounded_native_graph_refuses(mixer, mutation):
    o = mixer
    def mutate(reply):
        device = reply['audiodevs'][0]
        if mutation == 'device-duplicate':
            reply['audiodevs'].append(deepcopy(device))
        elif mutation == 'cards-duplicate':
            device['cards'].append('sb16')
        elif mutation == 'voice-duplicate':
            device['voices'].append(deepcopy(device['voices'][-1]))
        elif mutation == 'voice-unsorted':
            device['voices'].reverse()
        elif mutation == 'capture-duplicate':
            device['captures'] = [{'format': pcm(), 'enabled': True}, {'format': pcm(), 'enabled': False}]
        else:
            device['voices'] = [dict(deepcopy(device['voices'][0]), **{'voice-id': f'voice{i:02}'}) for i in range(33)]
        return reply
    o.wire.mutate_mixer = mutate
    with pytest.raises(DebuggerError, match='mixer'):
        o.session.mixer_observe()
    assert o.vm.closed and event_count(o) == 0


@pytest.mark.parametrize('drift', ['icount', 'virtual-clock', 'native-epoch'])
def test_changed_native_clock_withdraws_the_readback(mixer, drift):
    o = mixer
    def after():
        if drift == 'icount':
            o.wire.counter += 1
        else:
            o.wire.receipt['virtual-ns' if drift == 'virtual-clock' else 'epoch'] += 1
    o.wire.after_mixer = after
    with pytest.raises(DebuggerError):
        o.session.mixer_observe()
    assert o.vm.closed and event_count(o) == 0


def test_old_native_audio_admission_and_observation_remain_usable(mixer):
    old = OplAdmission()
    assert COMMAND not in old.qmp_commands
    assert admit_audio(old)['state'] == 'idle'
    assert old.calls == ['x-fdisbull-query-sb16', 'x-fdisbull-query-opl', 'x-fdisbull-query-audio']
    o = mixer
    o.vm.qmp_commands -= {COMMAND}
    assert MachineContext(o.vm).capabilities['mixer_gain_readback'] is False
    with pytest.raises(ValueError, match='optional native mixer'):
        o.session.mixer_observe()
    assert o.wire.calls == [] and not o.vm.closed
    assert o.session.audio_observe()['state'] == 'idle' and not o.vm.closed


def test_changed_audio_profile_refuses_before_native_mixer_dispatch(mixer):
    o = mixer
    o.vm.machine_configuration['audio_profile']['capture_format']['rate'] = 48000
    with pytest.raises(DebuggerError, match='profile'):
        o.session.mixer_observe()
    assert o.vm.closed and not o.wire.calls and event_count(o) == 0


def test_transaction_and_missing_capability_preflight_precede_earlier_script_writes(mixer):
    o = mixer
    writes = []
    o.session.write_memory = lambda **kwargs: writes.append(kwargs)
    value = script(dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'),
                   dict(op='mixer-observe'))
    o.session.capabilities['mixer_gain_readback'] = False
    with pytest.raises(ValueError, match='mixer extension'):
        execute_script(o.session, value)
    assert not writes and not o.wire.calls
    o.session.capabilities['mixer_gain_readback'] = True
    with o.project.transaction(True):
        with pytest.raises(ValueError, match='transaction'):
            o.session.mixer_observe()
        with pytest.raises(ValueError, match='transaction'):
            execute_script(o.session, value)
    assert not writes and not o.wire.calls and not o.vm.closed


def test_one_saved_script_deadline_covers_native_query_and_both_clock_brackets(mixer):
    o = mixer
    o.wire.latency = .01
    result = execute_script(o.session, script(dict(op='mixer-observe')), timeout_ms=45)
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    commands = [command for command, _ in o.wire.calls]
    assert COMMAND in commands and not any(command in commands for command in ('cont', 'stop', 'input-send-event'))
    assert o.wire.budgets[0] == pytest.approx(.045)
    assert all(a > b for a, b in zip(o.wire.budgets, o.wire.budgets[1:]))
    assert o.clock.now == pytest.approx(100.045)
    assert o.vm.closed and o.wire.socket_closed and event_count(o) == 0
    assert o.session._rpc_deadline is None


@pytest.mark.parametrize('route', ['json', 'saved-script'])
def test_public_mixer_routing_reaches_the_real_native_envelope(mixer, route):
    o = mixer
    if route == 'json':
        workspace = DebugWorkspace()
        workspace.sessions[o.session.run_id] = o.session
        try:
            response = respond(dict(id=12, method='debug-mixer-observe', params=dict(
                project=str(o.project.path), run=o.session.run_id)), debugger=workspace)
        finally:
            workspace.sessions.clear()
        assert response['ok'], response
        result = response['result']
    else:
        result = execute_script(o.session, script(dict(op='mixer-observe')))
        assert result['ok'], result
        result = result['steps'][0]['result']
    assert result['native'] == o.wire.mixer
    assert event_count(o) == 1 and sum(command == COMMAND for command, _ in o.wire.calls) == 1


def test_readback_preserves_LE_MZ_histories_and_frozen_selected_undo(mixer):
    o, s = mixer, mixer.session
    s._qemu_history_live = {'valid': True, 'cursor': 'mz-node'}
    s._qemu_le_history_live = {'valid': True, 'cursor': 'le-node'}
    s._qemu_cpu_delta_history = {'id': 'selected', 'valid': False, 'frozen': True}
    s._history_busy = False
    s._cpu_delta_before_operation = lambda name, args, kwargs: before_operation(s, name, args, kwargs)
    o.vm.history_operation_guard = lambda name, args, kwargs: QemuDOSHistoryMixin._history_before_operation(s, name, args, kwargs)
    provider = LESourceHistoryProvider(s)
    provider._history_bind()
    original = deepcopy((s._qemu_history_live, s._qemu_le_history_live, s._qemu_cpu_delta_history))
    assert s.mixer_observe()['native'] == o.wire.mixer
    assert (s._qemu_history_live, s._qemu_le_history_live, s._qemu_cpu_delta_history) == original
    assert event_count(o) == 1 and not o.vm.closed
