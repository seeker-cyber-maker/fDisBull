"""Independent timing and checkpoint oracles for the host typematic contract."""
from copy import deepcopy

import pytest

from fdisbull import qemu_instrumented_checkpoint as checkpoint
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_frame_keys import REPEAT_QUERY, validate_frame_key_repeat

from test_qemu_video_checkpoint import CheckpointPeer, envelope, make_state


def programmed(deadline=500_006_400):
    return {'parameter': 0x27, 'delay-ns': 500_000_000, 'interval-ns': 62_500_000,
            'deadline-ns': deadline, 'key': 'a'}


def state4(repeat):
    state = make_state()
    state['format'] = checkpoint.FRAME_KEY_REPEAT_FORMAT
    state['frame-keys'].update(active=True, held=['a'], generation=1,
                               **{'accepted-edges': 1})
    state['frame-key-repeat'] = repeat
    return state


class RepeatPeer(CheckpointPeer):
    def __init__(self, state):
        super().__init__(state)
        self.qmp_commands.add(REPEAT_QUERY)
        info = self.current['video-frame']['info']
        self.receipt.update(format=checkpoint.FRAME_KEY_REPEAT_FORMAT,
                            **{'video-frame-generation': info['stream-generation'],
                               'video-frame-token': info['token']})
        self.live_repeat = deepcopy(state['frame-key-repeat'])

    def call(self, command, arguments=None, **kwargs):
        if command == REPEAT_QUERY:
            self.calls.append((command, deepcopy(arguments), kwargs))
            return deepcopy(self.live_repeat)
        result = super().call(command, arguments, **kwargs)
        if command == 'x-fdisbull-query-frame-keys':
            result['repeat-supported'] = True
        return result


def test_format4_rebinds_owners_and_proves_due_phase_without_input(monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_retrace.admit_retrace', lambda vm: {'device': '/machine/vga'})
    saved = state4(programmed(deadline=6_401))  # Due before this authored paused cut.
    peer = RepeatPeer(saved)

    result = checkpoint.restore(peer, peer.record)

    assert result['format'] == checkpoint.FRAME_KEY_REPEAT_FORMAT
    assert result['native_epoch'] == 2
    assert result['windows']['video_frame'] == {'old': 'saved-source-owner', 'new': 'fresh-source-owner'}
    assert peer._frame_key_owner['token'] == 'fresh-key-owner'
    assert peer._frame_key_owner['held'] == ['a']
    assert peer._frame_key_owner['accepted_edges'] == 1
    assert peer.live_repeat == saved['frame-key-repeat']
    commands = [command for command, _, _ in peer.calls]
    assert commands.count(REPEAT_QUERY) == 1
    assert not any('apply' in command or 'send-event' in command for command in commands)


def test_restore_refuses_a_restarted_delay_even_with_rebound_keys(monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_retrace.admit_retrace', lambda vm: {'device': '/machine/vga'})
    peer = RepeatPeer(state4(programmed()))
    peer.live_repeat['deadline-ns'] += 62_500_000

    with pytest.raises(DebuggerError, match='repeat readback differs'):
        checkpoint.restore(peer, peer.record)

    assert peer.close_calls == 1
    assert not hasattr(peer, '_frame_key_owner')


@pytest.mark.parametrize('changes', [
    {'key': 'b'}, {'deadline-ns': -1}, {'deadline-ns': True},
    {'parameter': 128}, {'delay-ns': 250_000_000}, {'interval-ns': 62_500_001},
])
def test_rejects_invalid_repeat_checkpoint_before_import(changes):
    peer = RepeatPeer(state4({**programmed(), **changes}))
    with pytest.raises(ValueError, match='repeat proof'):
        checkpoint.restore(peer, peer.record)
    assert peer.calls == []


def test_admits_default_idle_configuration_at_500_ms():
    idle = {'parameter': 0x2B, 'delay-ns': 500_000_000,
            'interval-ns': 91_666_666, 'deadline-ns': -1}
    assert validate_frame_key_repeat(idle, held=[]) == idle


def test_producer_cannot_restore_phase_without_the_readback_command():
    peer = RepeatPeer(state4(programmed()))
    peer.qmp_commands.remove(REPEAT_QUERY)
    with pytest.raises(ValueError, match='native frame key repeat capability'):
        checkpoint.restore(peer, envelope(peer.saved))
    assert peer.calls == []


@pytest.mark.parametrize('parameter, interval', [(0x20, 33_000_000), (0x27, 63_000_000)])
def test_dosbox_millisecond_profile_reports_legacy_cadence(parameter, interval):
    repeat = {'parameter': parameter, 'delay-ns': 500_000_000, 'interval-ns': interval,
              'deadline-ns': -1, 'profile': 'dosbox-millisecond'}
    assert validate_frame_key_repeat(repeat, held=[]) == repeat
    with pytest.raises(DebuggerError, match='timing or ownership'):
        validate_frame_key_repeat({k: v for k, v in repeat.items() if k != 'profile'}, held=[])


def test_checkpoint_repeat_profile_is_pinned_before_import(monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_retrace.admit_retrace', lambda vm: {'device': '/machine/vga'})
    repeat = {**programmed(), 'interval-ns': 63_000_000, 'profile': 'dosbox-millisecond'}
    peer = RepeatPeer(state4(repeat))
    with pytest.raises(ValueError, match='profile differs from launch'):
        checkpoint.restore(peer, peer.record)
    assert peer.calls == []
    peer.machine_configuration['frame_key_repeat_profile'] = 'dosbox-millisecond'
    assert checkpoint.restore(peer, peer.record)['format'] == checkpoint.FRAME_KEY_REPEAT_FORMAT
