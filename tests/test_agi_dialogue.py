"""Synthetic dialogue protocol tests; these do not establish native parity."""
import pytest

import fdisbull.agi_dos as dos
from test_agi_host import make_host, CS, DS, SS, CODE, FETCH, _u16


def dialogue_fixture(tmp_path, monkeypatch, *, fault=None, two_prints=False):
    host, session, _ = make_host(tmp_path, monkeypatch, [101, 1, 101, 1, 0] if two_prints else [101, 1, 0],
                                 {'$agi_f15': False, '$agi_v21': 0})
    monitor = host.monitor
    session.host = host
    monkeypatch.setattr(dos, 'logic_messages', lambda r: {r.resource_sha256: {'1': 'Fixture message'}})
    session.memory[DS * 16 + 0x5003] = 1
    _u16(session.memory, DS * 16 + 0x5008, 0x5100)
    _u16(session.memory, DS * 16 + 0x5102, 0x20)
    session.memory[DS * 16 + 0x5120:DS * 16 + 0x5120 + 16] = b'Fixture message\0'
    if fault == 'message': session.memory[DS * 16 + 0x5120] = ord('X')
    session.dialogue_runs = 0
    session.keys = []
    original_call = session.call
    bps = {}
    def call(method, params=None):
        result = original_call(method, params)
        if method == 'breakpoints.create':
            bps[result['breakpoint_id']] = int(params['address']['offset'], 16)
        return result
    session.call = call
    def idle():
        return {'keyboard': {'pending_events': 0, 'owned_keys': 0, 'queued_guest_ms': 0}}
    session.keyboard_state = idle
    def press(key, *, hold_ms, gap_ms):
        session.keys.append((key, hold_ms, gap_ms))
        if fault == 'key_transport' or (fault == 'second_key_transport' and len(session.keys) == 2):
            raise TimeoutError('lost key response')
        return {'queued': True}
    session.keyboard_press = press
    def screenshot(name, *, hooks):
        session.screenshot_calls += 1
        if fault == 'missing_frame' and session.screenshot_calls == 2:
            raise OSError('missing frame')
        frame = 1 if fault == 'stale_frame' else session.screenshot_calls
        result = {'artifact': f'frame-{session.screenshot_calls}',
                  'metadata': {'frame_id': frame, 'mode_id': 1}}
        if fault == 'no_artifact' and session.screenshot_calls == 2: result.pop('artifact')
        if fault == 'missing_mode': result['metadata'].pop('mode_id')
        if fault == 'invalid_mode': result['metadata']['mode_id'] = True
        if fault == 'changed_mode' and session.screenshot_calls == 2: result['metadata']['mode_id'] = 2
        return result
    session.screenshot = screenshot
    def run(**kwargs):
        session.dialogue_runs += 1
        n = (session.dialogue_runs - 1) % 4 + 1
        session.state_revision += 1
        if n in (1, 3):
            session.register_state['instruction_pointer'] = hex(dos.DIALOGUE_WAIT)
            session.register_state['general']['esp'] = hex(0x700)
            _u16(session.memory, SS * 16 + 0x706, 0x1d25)
            _u16(session.memory, DS * 16 + 0xd15, 1)
            ids = [ident for ident, addr in bps.items() if addr == dos.DIALOGUE_WAIT]
            ident = ids[-1] if fault != 'foreign_stop' else 'foreign'
            return {'outcome': 'breakpoint', 'guest_elapsed_ms': 1, 'session': {'stop_reason': {'kind': 'breakpoint', 'breakpoint_id': ident}}}
        if n == 2:
            return {'outcome': 'guest_time', 'guest_elapsed_ms': 1 if fault == 'short_preview' else 50}
        if n == 4:
            _u16(session.memory, DS * 16 + 0xd15, 1 if fault == 'window_stays_open' else 0)
            session.register_state['instruction_pointer'] = hex(FETCH)
            session.register_state['general']['esp'] = hex(0x800)
            next_offset = 2 if session.dialogue_runs == 4 else 4
            session.register_state['general']['esi'] = hex(CODE + next_offset)
            session.register_state['general']['eax'] = hex(session.resource.code[next_offset])
            ids = [ident for ident, addr in bps.items() if addr == FETCH]
            return {'outcome': 'breakpoint', 'guest_elapsed_ms': 1, 'session': {'stop_reason': {'kind': 'breakpoint', 'breakpoint_id': ids[0]}}}
        raise AssertionError('unexpected replay')
    session.run = run
    return monitor, session


@pytest.mark.parametrize('key', ['enter', 'escape'])
def test_opt_in_wait_requires_fresh_preview_then_one_key_and_return(tmp_path, monkeypatch, key):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch)
    result = monitor.step(dialogue_key=key)
    assert result['status'] == 'completed' and result['next_offset'] == 2
    phase = result['dialogue']
    assert phase['status'] == 'completed' and phase['window_closed'] and phase['input_settled']
    assert phase['message']['resource_sha256'] == monitor.resource.resource_sha256
    assert phase['waiting_frame']['metadata']['frame_id'] > phase['initial_frame']['metadata']['frame_id']
    assert session.keys == [(key, 1, 1)] and session.dialogue_runs == 4


@pytest.mark.parametrize('fault', ['message', 'foreign_stop', 'missing_frame', 'stale_frame', 'no_artifact',
                                 'missing_mode', 'invalid_mode', 'changed_mode'])
def test_unqualified_preview_or_message_prevents_input_and_replay(tmp_path, monkeypatch, fault):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault=fault)
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped' and not session.keys
    assert not result['dialogue']['input_attempted']
    with pytest.raises(ValueError, match='reconciliation'):
        monitor.step(dialogue_key='enter')


def test_unknown_key_transport_outcome_is_not_replayed(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='key_transport')
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped' and result['dialogue']['input_attempted'] is True
    assert session.keys == [('enter', 1, 1)]
    with pytest.raises(ValueError, match='reconciliation'):
        monitor.step(dialogue_key='enter')
    assert session.keys == [('enter', 1, 1)]


def test_adapter_reports_attempted_key_failure_without_retry(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='key_transport')
    session.host.dialogue_key = 'enter'
    result = session.host.run()
    assert result['status'] == 'incomplete'
    assert result['attempts'][-1]['dialogue']['input_attempted'] is True
    assert result['host_completions'] == []
    assert session.host.run() == result
    assert session.keys == [('enter', 1, 1)]


def test_default_policy_does_not_send_key(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='foreign_stop')
    result = monitor.step()
    assert result['status'] == 'stopped'
    assert 'dialogue' not in result and session.keys == []


def test_pending_keyboard_input_prevents_key(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch)
    session.keyboard_state = lambda: {'keyboard': {'pending_events': 1, 'owned_keys': 0, 'queued_guest_ms': 0}}
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped' and not session.keys
    assert result['dialogue']['input_attempted'] is False


def test_adapter_retains_first_completion_when_second_key_response_is_lost(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='second_key_transport', two_prints=True)
    session.host.dialogue_key = 'enter'
    result = session.host.run()
    assert result['status'] == 'incomplete'
    assert len(result['host_completions']) == 1
    assert result['host_completions'][0]['dialogue']['status'] == 'completed'
    assert result['attempts'][-1]['dialogue']['input_attempted'] is True
    assert session.keys == [('enter', 1, 1), ('enter', 1, 1)]
    assert session.host.run() == result and len(session.keys) == 2


def test_short_preview_interval_cannot_authorize_input(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='short_preview')
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped' and session.keys == []


def test_open_window_after_return_cannot_claim_completion(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch, fault='window_stays_open')
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped'
    assert result['dialogue']['input_attempted'] is True
    assert result['dialogue']['handler_return_observed'] is True
    assert session.keys == [('enter', 1, 1)]


def test_pending_keyboard_after_return_cannot_claim_completion(tmp_path, monkeypatch):
    monitor, session = dialogue_fixture(tmp_path, monkeypatch)
    def state():
        return {'keyboard': {'pending_events': int(bool(session.keys)), 'owned_keys': 0, 'queued_guest_ms': 0}}
    session.keyboard_state = state
    result = monitor.step(dialogue_key='enter')
    assert result['status'] == 'stopped' and result['dialogue']['input_attempted'] is True
    assert result['dialogue']['handler_return_observed'] is True
    assert session.keys == [('enter', 1, 1)]


def test_cleanup_failure_is_retained_after_unknown_key_outcome(tmp_path,monkeypatch):
    monitor,session=dialogue_fixture(tmp_path,monkeypatch,fault='key_transport')
    original=session.call
    def call(method,params=None):
        if method=='breakpoints.delete' and session.keys:raise OSError('cleanup response lost')
        return original(method,params)
    session.call=call
    result=monitor.step(dialogue_key='enter')
    assert result['status']=='stopped' and result['dialogue']['input_attempted']
    assert len(result['cleanup_errors'])==2
    assert all(e['error']=='cleanup response lost' for e in result['cleanup_errors'])
    with pytest.raises(ValueError,match='reconciliation'):monitor.step(dialogue_key='enter')
    assert session.keys==[('enter',1,1)]
