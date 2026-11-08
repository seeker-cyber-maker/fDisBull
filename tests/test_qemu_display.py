"""Native renderer publication contract at the real QMP transport boundary."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_display import DISPLAY_COMMANDS
from test_qemu_audio import AudioWire, audio
from test_qemu_io_deadlines import observation


class DisplayWire(AudioWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.display = {'api-version': 1, 'epoch': 1, 'state': 'idle', 'virtual-ns': 1000,
                        'period-ns': 0, 'updates': 0}
        self.pixels = b'\xff\0\0'
        self.mutate_display = lambda value: value

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in DISPLAY_COMMANDS:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-start-display':
            self.display.update(state='observing', token=args['token'], **{
                'start-ns': self.receipt['virtual-ns'], 'period-ns': args['period-ns']})
        elif command == 'x-fdisbull-stop-display':
            self.display.update(state='stopped', **{'stop-ns': self.receipt['virtual-ns']})
        elif command == 'x-fdisbull-export-display':
            Path(args['filename']).write_bytes(b'P6\n1 1\n255\n' + self.pixels)
        self.display['virtual-ns'] = self.receipt['virtual-ns']
        value = self.mutate_display(deepcopy(self.display))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency

    def publish(self):
        self.display.update(updates=1, width=1, height=1,
                            **{'update-id': 1, 'published-ns': self.receipt['virtual-ns']})


@pytest.fixture
def display(audio):
    o = audio
    wire = DisplayWire(o.clock)
    o.qmp.socket = o.wire = wire
    o.vm.qmp_commands |= DISPLAY_COMMANDS
    o.session.capabilities['renderer_capture'] = True
    return o


def test_start_and_passive_capture_never_refresh_or_run_the_guest(display):
    o = display
    started = o.session.display_start()
    assert started['updates'] == 0 and started['completed_guest_frame'] is None
    with pytest.raises(ValueError, match='No completed renderer'):
        o.session.capture_display()
    o.wire.publish()
    captured = o.session.capture_display(after_update=0)
    assert captured['metadata']['completed_renderer_update'] is True
    assert captured['metadata']['completed_guest_frame'] is None
    assert captured['metadata']['update_id'] == 1
    count = len([call for call in o.wire.calls if call[0] == 'x-fdisbull-export-display'])
    with pytest.raises(ValueError, match='No newer renderer'):
        o.session.capture_display(after_update=1)
    assert len([call for call in o.wire.calls if call[0] == 'x-fdisbull-export-display']) == count
    assert all(command not in ('cont', 'screendump', 'human-monitor-command') for command, _ in o.wire.calls)


@pytest.mark.parametrize('mutation', [
    {'api-version': True}, {'epoch': 2}, {'virtual-ns': 1001}, {'updates': True},
    {'state': 'invalidated'}, {'period-ns': 0}, {'token': 'another-window'},
    {'update-id': 2}, {'published-ns': 999}, {'width': 0}, {'width': 8193},
    {'width': 8192, 'height': 8192},
])
def test_invalid_publication_receipts_close_the_owner(display, mutation):
    o = display
    o.session.display_start()
    o.wire.publish()
    o.wire.mutate_display = lambda value: dict(value, **mutation)
    with pytest.raises(DebuggerError):
        o.session.display_observe()
    assert o.vm.closed


def test_retained_pixels_cannot_change_under_one_update_id(display):
    o = display
    o.session.display_start()
    o.wire.publish()
    o.session.capture_display()
    o.wire.pixels = b'\0\xff\0'
    with pytest.raises(DebuggerError, match='pixels changed'):
        o.session.capture_display()
    assert o.vm.closed and not list(o.directory.glob('display-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 1


def test_unowned_native_window_is_not_adopted(display):
    o = display
    o.wire.display.update(state='observing', token='not-python-owned',
                          **{'start-ns': 1000, 'period-ns': 1000000})
    with pytest.raises(DebuggerError, match='identity'):
        o.session.display_observe()
    assert o.vm.closed


def test_stopped_publication_cannot_keep_growing(display):
    o = display
    o.session.display_start()
    o.wire.publish()
    o.session.display_stop()
    o.wire.display.update(updates=2, **{'update-id': 2})
    with pytest.raises(DebuggerError, match='Stopped native renderer'):
        o.session.display_observe()
    assert o.vm.closed


def test_ppm_length_mismatch_cannot_store_a_publication(display):
    o = display
    o.session.display_start()
    o.wire.publish()
    o.wire.pixels = b'\0'
    with pytest.raises(DebuggerError, match='dimensions'):
        o.session.capture_display()
    assert o.vm.closed and not list(o.directory.glob('display-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('step', [dict(op='display-start', period_ns=0),
                                 dict(op='capture-display', after_update=True)])
def test_whole_script_rejects_invalid_media_before_prior_mutation(display, step):
    o = display
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='keyboard.key-down', key='a'), step])
    with pytest.raises(ValueError):
        validate_script(script, session=o.session)
    assert o.wire.calls == []


def test_renderer_script_uses_one_deadline_through_native_queries(display):
    o = display
    o.wire.latency = .03
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[dict(op='display-start')])
    result = execute_script(o.session, script, timeout_ms=50)
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    assert [command for command, _ in o.wire.calls] == ['query-status', 'query-replay']
    assert o.wire.budgets == pytest.approx([.05, .02])
    assert o.vm.closed


@pytest.mark.parametrize('operation,event', [('audio-start', 'machine-audio-start'),
                                            ('display-start', 'machine-display-start')])
def test_expired_start_receipt_cannot_leave_an_unreported_native_observer(display, operation, event):
    o = display
    original = o.session._event
    def delayed(name, payload):
        original(name, payload)
        if name == event:
            o.clock.now += .1
    o.session._event = delayed
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[dict(op=operation)])
    result = execute_script(o.session, script, timeout_ms=50)
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    assert o.vm.closed and o.wire.socket_closed


def test_renderer_transaction_and_missing_extension_fail_before_native_io(display):
    o = display
    with o.project.transaction(True):
        for operation in (o.session.display_start, o.session.display_observe,
                          o.session.display_stop, o.session.capture_display):
            with pytest.raises(ValueError, match='transaction'):
                operation()
    assert o.wire.calls == []
    o.vm.qmp_commands -= DISPLAY_COMMANDS
    with pytest.raises(ValueError, match='extension'):
        o.session.display_start()
    assert o.wire.calls == []
