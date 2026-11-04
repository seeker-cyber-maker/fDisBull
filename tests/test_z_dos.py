import base64
import hashlib
import struct

import pytest

from fdisbull.z_dos import click_at_dos_mouse_poll, read_linear, write_linear_guarded
from fdisbull.dosbox_rpc import DebuggerError


def digest(data):
    return hashlib.sha256(data).hexdigest()


class MemorySession:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        assert params['address'] == {'space': 'linear', 'offset': '0x0025068E'}
        if method == 'memory.read':
            data = self.data[:params['length']]
            return {'data_base64': base64.b64encode(data).decode(), 'sha256': digest(data)}
        assert method == 'memory.write'
        if params['expected_sha256'] != digest(self.data):
            raise RuntimeError('MEMORY_PRECONDITION_FAILED')
        self.data = base64.b64decode(params['data_base64'], validate=True)
        return {'after_sha256': digest(self.data), 'byte_count': len(self.data)}


def test_linear_helper_preserves_full_bytes_and_guarded_round_trip():
    original = bytes(range(256)) * 2
    session = MemorySession(original)
    before = read_linear(session, 0x25068E, len(original))
    assert base64.b64decode(before['data_base64']) == original
    changed = bytes(reversed(original))
    write_linear_guarded(session, 0x25068E, before['sha256'], changed)
    with pytest.raises(RuntimeError, match='MEMORY_PRECONDITION_FAILED'):
        write_linear_guarded(session, 0x25068E, before['sha256'], original)
    assert session.data == changed
    current = read_linear(session, 0x25068E, len(original))
    write_linear_guarded(session, 0x25068E, current['sha256'], original)
    assert session.data == original


def test_invalid_memory_ranges_refuse_before_dispatch():
    session = MemorySession(b'aa')
    with pytest.raises(ValueError, match='wraps'):
        read_linear(session, 0xFFFFFFFF, 2)
    with pytest.raises(ValueError, match='wraps'):
        write_linear_guarded(session, 0xFFFFFFFF, '0' * 64, b'aa')
    with pytest.raises(ValueError, match='expected_sha256'):
        write_linear_guarded(session, 0x25068E, 'g' * 64, b'aa')
    assert not session.calls


def stopped(trigger, *, breakpoint_id=None, hooks=None):
    return {'stop': {'trigger': trigger}, 'hook_hits': hooks or [],
            'session': {'stop_reason': {'kind': trigger, 'breakpoint_id': breakpoint_id}}}


class MouseSession:
    def __init__(self, *, protected=False, move_stop=None, poll_stop=None, after_stop=None):
        self.protected = protected
        self.move_stop = move_stop
        self.poll_stop = poll_stop
        self.after_stop = after_stop
        self.events = []

    def registers(self):
        return {'cpu_mode': 'protected' if self.protected else 'real',
                'segments': {'cs': '0xC402'}, 'instruction_pointer': '0x00000010'}

    def call(self, method, params):
        self.events.append((method, params))
        if method == 'memory.read':
            return {'data_base64': base64.b64encode(struct.pack('<HH', 0x10, 0xC402)).decode()}
        if method == 'breakpoints.create':
            return {'breakpoint_id': 'owned'}
        return {'accepted': True}

    def run(self, **params):
        self.events.append(('run', params))
        if self.protected:
            return stopped('guest_time')
        if params['guest_ms'] == 250:
            return self.move_stop or stopped('guest_time')
        if params['guest_ms'] == 10:
            return self.poll_stop or stopped('breakpoint', breakpoint_id='owned')
        return self.after_stop or stopped('guest_time')

    def click(self, x, y, **params):
        self.events.append(('click', {'x': x, 'y': y, **params}))
        return {'accepted': True}


def test_mouse_delivery_is_bounded_and_does_not_claim_scene_success():
    session = MouseSession()
    result = click_at_dos_mouse_poll(session, 250, 76, hold_ms=1000)
    assert result['input_delivered'] is True
    assert result['scene_effect'] == 'observe in the calling action'
    clicks = [value for op, value in session.events if op == 'click']
    assert clicks == [{'x': 250, 'y': 76, 'hold_ms': 1000}]
    runs = [value for op, value in session.events if op == 'run']
    assert all(r['guest_ms'] > 0 and r['timeout_ms'] > 0 for r in runs)
    assert all(r.get('stop_on_hook') is True for r in runs)


def test_protected_mode_exhaustion_does_not_send_input():
    session = MouseSession(protected=True)
    with pytest.raises(RuntimeError, match='within 2 slices'):
        click_at_dos_mouse_poll(session, 250, 76, max_slices=2)
    assert len(session.events) == 2
    assert all(op == 'run' for op, value in session.events)


def test_foreign_stop_during_move_stops_before_creating_breakpoint_or_click():
    session = MouseSession(move_stop=stopped('breakpoint', breakpoint_id='foreign'))
    with pytest.raises(RuntimeError):
        click_at_dos_mouse_poll(session, 250, 76)
    assert [op for op, value in session.events] == ['input.mouse.move', 'run']


@pytest.mark.parametrize('foreign_stop', [
    stopped('hook', hooks=[{'hook': 'foreign'}]),
    stopped('breakpoint', breakpoint_id='foreign'),
])
def test_foreign_hook_or_breakpoint_at_same_pc_is_not_the_owned_rendezvous(foreign_stop):
    session = MouseSession(poll_stop=foreign_stop)
    with pytest.raises(RuntimeError):
        click_at_dos_mouse_poll(session, 250, 76)
    assert not any(op == 'click' for op, value in session.events)
    assert ('breakpoints.delete', {'breakpoint_id': 'owned'}) in session.events


def test_foreign_stop_after_click_does_not_resume_past_it():
    session = MouseSession(after_stop=stopped('breakpoint', breakpoint_id='foreign'))
    with pytest.raises(RuntimeError):
        click_at_dos_mouse_poll(session, 250, 76)
    assert sum(op == 'click' for op, value in session.events) == 1
    assert sum(op == 'run' and value['guest_ms'] == 2000 for op, value in session.events) == 1


def test_real_mode_sampling_breaks_fast_forward_phase_lock():
    from fdisbull.z_dos import _real_mode
    class Session:
        normal = False
        calls = []
        def registers(self):
            return {'cpu_mode': 'real' if self.normal else 'protected'}
        def run(self, **params):
            self.calls.append(params)
            self.normal = not params['fast_forward']
            return {'stop': {'trigger': 'guest_time'}}
    session = Session()
    assert _real_mode(session, 10) == 8
    assert session.calls[-1]['guest_ms'] == 1
    assert all(row['stop_on_hook'] for row in session.calls)


@pytest.mark.parametrize('foreign_stop,message', [
    (stopped('breakpoint', breakpoint_id='foreign'), 'another breakpoint'),
    (stopped('hook', hooks=[{'hook': 'foreign'}]), 'another hook'),
])
def test_consumed_owned_mouse_breakpoint_cannot_mask_the_foreign_stop(foreign_stop, message):
    session = MouseSession(poll_stop=foreign_stop)
    original = session.call

    def call(method, params):
        if method == 'breakpoints.delete':
            session.events.append((method, params))
            assert params == {'breakpoint_id': 'owned'}
            raise DebuggerError('Breakpoint no longer exists in the debugger (BREAKPOINT_NOT_FOUND)')
        return original(method, params)

    session.call = call
    with pytest.raises(RuntimeError, match=message):
        click_at_dos_mouse_poll(session, 250, 76)
    assert session.events[-1] == ('breakpoints.delete', {'breakpoint_id': 'owned'})
    assert not any(op == 'click' for op, _ in session.events)
    assert sum(op == 'run' for op, _ in session.events) == 2  # Move settle, then the retained stop.


@pytest.mark.parametrize('error', [
    DebuggerError('Backend refused deletion (COMMAND_REJECTED)'),
    RuntimeError('Unrelated failure with misleading text (BREAKPOINT_NOT_FOUND)'),
])
def test_temporary_cleanup_does_not_swallow_unrelated_backend_or_transport_errors(error):
    from fdisbull.z_dos import _delete_owned_temporary_breakpoint

    class Session:
        def call(self, method, params):
            assert method == 'breakpoints.delete' and params == {'breakpoint_id': 'owned'}
            raise error

    with pytest.raises(type(error)) as raised:
        _delete_owned_temporary_breakpoint(Session(), 'owned')
    assert raised.value is error
