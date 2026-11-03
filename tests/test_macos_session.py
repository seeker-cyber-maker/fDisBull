"""Coordinator fault tests; doubles do not qualify native macOS behavior."""
import base64
import copy
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import uuid

import pytest

from fdisbull.macos_session import recover_session, run_session
import fdisbull.macos_session as sessions


def encoded(value):
    return base64.b64encode(plistlib.dumps({'value': value}, fmt=plistlib.FMT_BINARY)).decode()


class NativeDouble:
    def __init__(self):
        self.bundle_id = 'local.fdisbull.fixture.' + uuid.uuid4().hex
        self.pid, self.launch_date, self.open = 777, '2026-10-31T12:00:00Z', False
        self.preferences, self.calls, self.capture_action = {}, [], None

    def __call__(self, operation, **kwargs):
        self.calls.append((operation, copy.deepcopy(kwargs)))
        if operation == 'snapshot':
            return {'target': {'bundle_id': self.bundle_id, 'running': True,
                               'pid': self.pid, 'launch_date': self.launch_date},
                    'menu': {'open': self.open}, 'displays': [{'id': 5, 'bounds': {'x': -2560, 'y': 0}}]}
        if operation == 'prefs_get':
            return {'preferences': {key: {'present': key in self.preferences,
                                          'value_base64': self.preferences.get(key)} for key in kwargs['keys']}}
        if operation in ('prefs_set', 'press_status', 'dismiss_menu'):
            assert kwargs['pid'] == self.pid and kwargs['expected_launch_date'] == self.launch_date
        if operation == 'prefs_set':
            if kwargs['value_base64'] is None:
                self.preferences.pop(kwargs['key'], None)
            else:
                self.preferences[kwargs['key']] = kwargs['value_base64']
        elif operation == 'press_status':
            self.open = not self.open
        elif operation == 'dismiss_menu':
            self.open = False
        elif operation == 'capture':
            if self.capture_action:
                self.capture_action()
            Path(kwargs['output']).write_bytes(b'unit-test-double-not-a-native-screenshot')
            return {'display_id': kwargs['display_id'], 'global_rect': kwargs.get('rect'),
                    'pixel_width': 10, 'pixel_height': 10}
        return {}


def run(native, output, **kwargs):
    return run_session(bundle_id=native.bundle_id, output=output, native=native, **kwargs)


def test_default_session_is_observation_only_and_preserves_global_coordinates(tmp_path):
    native = NativeDouble()
    rect = {'x': -1178, 'y': 3, 'width': 80, 'height': 22}
    receipt = run(native, tmp_path / 'session', display_id=5, rect=rect)
    assert receipt['status'] == receipt['cleanup']['status'] == 'confirmed'
    assert {op for op, _ in native.calls} == {'snapshot', 'capture'}
    assert json.loads((tmp_path / 'session/capture.json').read_text())['global_rect'] == rect
    assert (tmp_path / 'session').stat().st_mode & 0o777 == 0o700


def test_unknown_home_directory_refuses_before_native_actions(tmp_path, monkeypatch):
    native = NativeDouble()
    def missing_home(path):
        raise RuntimeError('unknown user home directory')
    monkeypatch.setattr(sessions.Path, 'expanduser', missing_home)
    with pytest.raises(ValueError, match='cannot expand'):
        run(native, tmp_path / 'session')
    assert native.calls == []


def test_external_menu_open_without_delivery_is_not_owned_or_dismissed(tmp_path):
    class ExternalOpen(NativeDouble):
        def __call__(self, operation, **kwargs):
            if operation == 'press_status':
                self.calls.append((operation, kwargs))
                self.open = True
                return {'status':'confirmed','changed':True,'delivery':{'method':'none','status':'not_needed'}}
            return super().__call__(operation, **kwargs)
    native = ExternalOpen()
    receipt = run(native, tmp_path / 'session', live=True, status_index=0)
    assert receipt['status'] == 'confirmed' and native.open is True
    assert 'dismiss_menu' not in [op for op,_ in native.calls]
    journal = json.loads((tmp_path / 'session/journal.json').read_text())
    assert journal['menu_owned'] is False


def test_test_opened_menu_and_absent_language_key_are_restored(tmp_path):
    native = NativeDouble()
    receipt = run(native, tmp_path / 'session', live=True, status_index=0, display_id=5,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'confirmed'
    assert native.open is False and 'language' not in native.preferences
    setters = [args for op, args in native.calls if op == 'prefs_set']
    assert [item['value_base64'] for item in setters] == [encoded('ja'), None]
    assert [op for op, _ in native.calls].count('press_status') == 1
    assert [op for op, _ in native.calls].count('dismiss_menu') == 1
    journal = json.loads((tmp_path / 'session/journal.json').read_text())
    assert journal['phase'] == 'complete' and journal['changes'][0]['restored']


def test_existing_menu_and_preference_type_survive(tmp_path):
    native = NativeDouble()
    native.open = True
    native.preferences['enabled'] = encoded(False)
    receipt = run(native, tmp_path / 'session', live=True, status_index=0,
                  keys=['enabled'], preference_changes={'enabled': encoded(1)})
    assert receipt['status'] == 'confirmed' and native.open is True
    assert native.preferences['enabled'] == encoded(False)
    assert not {'press_status', 'dismiss_menu'} & {op for op, _ in native.calls}


def test_capture_failure_still_restores_owned_state(tmp_path):
    native = NativeDouble()
    def fail():
        raise RuntimeError('authored capture fault')
    native.capture_action = fail
    receipt = run(native, tmp_path / 'session', live=True, status_index=0, display_id=5,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'failed' and receipt['cleanup']['status'] == 'confirmed'
    assert native.open is False and native.preferences == {}


def test_external_preference_change_is_not_overwritten(tmp_path):
    native = NativeDouble()
    native.capture_action = lambda: native.preferences.update(language=encoded('user-choice'))
    receipt = run(native, tmp_path / 'session', live=True, display_id=5,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'partial'
    assert native.preferences['language'] == encoded('user-choice')
    assert receipt['cleanup']['outcomes'][0]['status'] == 'conflict'
    assert json.loads((tmp_path / 'session/journal.json').read_text())['phase'] == 'recovery_required'


def test_changed_pid_refuses_cleanup_mutation(tmp_path):
    native = NativeDouble()
    native.capture_action = lambda: setattr(native, 'pid', 778)
    receipt = run(native, tmp_path / 'session', live=True, display_id=5, status_index=0,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'partial' and native.open is True
    assert native.preferences['language'] == encoded('ja')
    assert not any(op == 'dismiss_menu' for op, _ in native.calls)


def test_unknown_menu_state_refuses_live_toggle(tmp_path):
    native = NativeDouble()
    native.open = None
    receipt = run(native, tmp_path / 'session', live=True, status_index=0)
    assert receipt['status'] == 'failed'
    assert not {'press_status', 'dismiss_menu'} & {op for op, _ in native.calls}


def test_one_controller_owns_the_target_across_output_directories(tmp_path):
    native = NativeDouble()
    def competing_controller():
        with pytest.raises(ValueError, match='another controller'):
            run(native, tmp_path / 'second')
        assert not (tmp_path / 'second').exists()
    native.capture_action = competing_controller
    assert run(native, tmp_path / 'first', display_id=5)['status'] == 'confirmed'


def test_forward_budget_does_not_skip_restoration(tmp_path, monkeypatch):
    native = NativeDouble()
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(sessions.time, 'monotonic', lambda: next(ticks))
    receipt = run(native, tmp_path / 'session', live=True, display_id=5, max_seconds=1,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'failed' and receipt['error']['type'] == 'TimeoutError'
    assert native.preferences == {}


def test_keyboard_interrupt_restores_then_propagates(tmp_path):
    native = NativeDouble()
    def stop():
        raise KeyboardInterrupt()
    native.capture_action = stop
    with pytest.raises(KeyboardInterrupt):
        run(native, tmp_path / 'session', live=True, display_id=5, status_index=0,
            keys=['language'], preference_changes={'language': encoded('ja')})
    assert native.preferences == {} and native.open is False
    assert json.loads((tmp_path / 'session/receipt.json').read_text())['cleanup']['status'] == 'confirmed'


def test_failed_journal_update_does_not_prevent_restoration(tmp_path, monkeypatch):
    native = NativeDouble()
    atomic = sessions._atomic_json
    failed = []
    def one_full_disk(path, value):
        if path.name == 'journal.json' and value.get('phase') == 'restoring' and not failed:
            failed.append(True)
            raise OSError('authored full disk')
        return atomic(path, value)
    monkeypatch.setattr(sessions, '_atomic_json', one_full_disk)
    receipt = run(native, tmp_path / 'session', live=True,
                  keys=['language'], preference_changes={'language': encoded('ja')})
    assert receipt['status'] == 'partial' and receipt['cleanup']['status'] == 'confirmed'
    assert native.preferences == {} and receipt['durability_errors']


@pytest.mark.parametrize('options', [
    {'live':False, 'status_index':0}, {'display_id':True},
    {'live':True, 'status_index':64}, {'display_id':1 << 32},
    {'rect':{'x':0,'y':0,'width':10,'height':10}}, {'keys':['x','x']},
    {'keys':['x'], 'preference_changes':{'x':encoded('ja')}},
    {'live':True, 'keys':['x'], 'preference_changes':{'other':encoded('ja')}},
    {'live':True, 'keys':['x'], 'preference_changes':{'x':'not-base64'}},
])
def test_invalid_requests_do_not_create_output_or_touch_native(tmp_path, options):
    native = NativeDouble()
    with pytest.raises(ValueError):
        run(native, tmp_path / 'session', **options)
    assert not native.calls and not (tmp_path / 'session').exists()


def test_private_capture_output_refuses_git_checkout(tmp_path):
    native = NativeDouble()
    (tmp_path / '.git').mkdir()
    with pytest.raises(ValueError, match='outside Git'):
        run(native, tmp_path / 'session')
    assert not (tmp_path / 'session').exists() and not native.calls


def test_recovery_rejects_malformed_completion_flags_before_mutation(tmp_path):
    native = NativeDouble()
    output = tmp_path / 'session'
    run(native, output, live=True, keys=['language'], preference_changes={'language':encoded('ja')})
    journal = json.loads((output / 'journal.json').read_text())
    journal['changes'][0]['restored'] = 1
    (output / 'journal.json').write_text(json.dumps(journal))
    native.calls.clear()
    with pytest.raises(ValueError, match='completion state'):
        recover_session(output, native)
    assert native.calls == []


@pytest.mark.parametrize('interruption', ['sigkill', 'sigterm'])
def test_process_interruption_and_explicit_restart_recovery(tmp_path, interruption):
    """A separate authored controller process exercises real locks and signals."""
    native = NativeDouble()
    state = tmp_path / 'native-double-state.json'
    state.write_text('{}')
    output = tmp_path / 'session'
    source_root = Path(__file__).resolve().parents[1] / 'src'
    code = '''
import json, os, signal, sys
from pathlib import Path
from fdisbull.macos_session import run_session
state, output, bundle, value, interruption = sys.argv[1:]
def native(op, **kwargs):
    prefs=json.loads(Path(state).read_text())
    if op=='snapshot':
        return {'target':{'bundle_id':bundle,'running':True,'pid':777,'launch_date':'2026-10-31T12:00:00Z'},'menu':{'open':False}}
    if op=='prefs_get':
        return {'preferences':{k:{'present':k in prefs,'value_base64':prefs.get(k)} for k in kwargs['keys']}}
    if op=='prefs_set':
        if kwargs['value_base64'] is None: prefs.pop(kwargs['key'],None)
        else: prefs[kwargs['key']]=kwargs['value_base64']
        Path(state).write_text(json.dumps(prefs))
        if kwargs['value_base64'] is not None and interruption=='sigkill': os.kill(os.getpid(),signal.SIGKILL)
    if op=='capture': os.kill(os.getpid(),signal.SIGTERM)
    return {}
run_session(bundle_id=bundle,output=output,native=native,live=True,keys=['language'],preference_changes={'language':value},display_id=5)
'''
    result = subprocess.run([sys.executable, '-c', code, str(state), str(output), native.bundle_id,
                             encoded('ja'), interruption],
                            env={**os.environ, 'PYTHONPATH':str(source_root)},
                            capture_output=True, text=True, timeout=15)
    if interruption == 'sigterm':
        assert result.returncode == 128 + signal.SIGTERM, result.stderr
        assert json.loads(state.read_text()) == {}
        assert json.loads((output / 'receipt.json').read_text())['cleanup']['status'] == 'confirmed'
    else:
        assert result.returncode == -signal.SIGKILL, result.stderr
        native.preferences = json.loads(state.read_text())
        assert native.preferences == {'language':encoded('ja')}
        receipt = recover_session(output, native)
        assert receipt['status'] == 'confirmed' and native.preferences == {}
        assert recover_session(output, native)['status'] == 'confirmed'
