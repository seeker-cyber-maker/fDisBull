"""Bounded macOS investigation with a durable, explicitly recoverable journal.

The injected native callable is the real macOS observation/capture adapter.
This coordinator neither launches apps nor guesses a display or menu state.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import signal
import stat
import struct
import tempfile
import threading
import time
import uuid

FORMAT = 'fdisbull-macos-session-1'
_MAX_JOURNAL = 4 * 1024 * 1024
_MAX_KEYS = 64


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
    if len(data) > _MAX_JOURNAL:
        raise ValueError('session JSON exceeds its 4 MiB budget')
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _bundle(value):
    if not isinstance(value, str) or not value or len(value) > 255 or any(c in value for c in '\x00/\\\n\r'):
        raise ValueError('bundle_id must be a nonempty application identifier')
    return value


def _keys(values):
    if not isinstance(values, (list, tuple)) or len(values) > _MAX_KEYS:
        raise ValueError('keys must be a list of at most 64 preference names')
    if any(not isinstance(key, str) or not key or len(key) > 256 or '\x00' in key for key in values):
        raise ValueError('preference names must be nonempty strings of at most 256 characters')
    if len(set(values)) != len(values):
        raise ValueError('preference names must be unique')
    return list(values)


def _value(value):
    if value is None:
        return {'present': False, 'value_base64': None}
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError('preference values must be base64 property lists or null for deletion')
    try:
        raw = base64.b64decode(value, validate=True)
        parsed = plistlib.loads(raw)
    except Exception as exc:
        raise ValueError('invalid preference property list') from exc
    if len(raw) > 49152 or not isinstance(parsed, dict) or set(parsed) != {'value'}:
        raise ValueError('preference property lists must wrap one value in a value dictionary')
    return {'present': True, 'value_base64': value}


def _preference_state(value):
    if not isinstance(value, dict) or type(value.get('present')) is not bool:
        raise ValueError('native preferences must report exact key presence')
    if value['present']:
        return _value(value.get('value_base64')) if value.get('value_base64') is not None else _bad_state()
    if value.get('value_base64') is not None:
        raise ValueError('an absent preference cannot contain a value')
    return {'present': False, 'value_base64': None}


def _bad_state():
    raise ValueError('a present preference must contain an encoded value')


def _same_value(left, right):
    # Binary plist encodings can change ordering; compare their typed payloads.
    if left['present'] != right['present']:
        return False
    if not left['present']:
        return True
    a = plistlib.loads(base64.b64decode(left['value_base64']))['value']
    b = plistlib.loads(base64.b64decode(right['value_base64']))['value']
    return _typed_equal(a, b)


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return struct.pack('>d', left) == struct.pack('>d', right)
    return left == right


def _native(native, operation, **kwargs):
    result = native(operation, **kwargs)
    if not isinstance(result, dict):
        raise ValueError('native adapter returned a non-object result')
    return result


def _snapshot(native, bundle_id):
    result = _native(native, 'snapshot', bundle_id=bundle_id)
    target = result.get('target')
    if not isinstance(target, dict) or type(target.get('running')) is not bool or target.get('bundle_id') != bundle_id:
        raise ValueError('snapshot lacks an exact target identity')
    return result


def _identity(snapshot):
    target = snapshot['target']
    return {name: target.get(name) for name in ('bundle_id', 'running', 'pid', 'launch_date')}


def _menu(snapshot):
    menu = snapshot.get('menu')
    value = menu.get('open') if isinstance(menu, dict) else snapshot.get('menu_open')
    return value if type(value) is bool else None


def _require_identity(native, journal):
    snapshot = _snapshot(native, journal['bundle_id'])
    expected = journal['identity']
    if not expected.get('running') or type(expected.get('pid')) is not int or not expected.get('launch_date'):
        raise ValueError('live actions require a running target with PID and launch date')
    if _identity(snapshot) != expected:
        raise ValueError('target process identity changed; mutation refused')
    return snapshot


def _preferences(native, bundle_id, keys):
    if not keys:
        return {}
    result = _native(native, 'prefs_get', bundle_id=bundle_id, keys=keys)
    values = result.get('preferences')
    if not isinstance(values, dict) or any(key not in values for key in keys):
        raise ValueError('native preference snapshot omitted a requested key')
    return {key: _preference_state(values[key]) for key in keys}


def _private_path(output, *, new):
    path = Path(output).expanduser()
    if path.is_symlink():
        raise ValueError('session output cannot be a symbolic link')
    path = path.resolve()
    if any((parent / '.git').exists() for parent in (path, *path.parents)):
        raise ValueError('private session data must remain outside Git checkouts')
    if new:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('session output must be an owner-only directory')
    return path


@contextmanager
def _file_lock(path):
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError('macOS session locking is unavailable on this host') from exc
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('invalid session controller lock')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another controller owns this application/session') from exc
        os.ftruncate(descriptor, 0)
        os.write(descriptor, json.dumps({'pid': os.getpid(), 'acquired_at': _now()}).encode())
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)


@contextmanager
def _target_lock(bundle_id):
    root = Path(tempfile.gettempdir()).resolve() / ('fdisbull-macos-sessions-' + str(os.getuid()))
    if root.is_symlink():
        raise ValueError('invalid target lock directory')
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('target lock directory must be owner-only')
    name = hashlib.sha256(bundle_id.encode()).hexdigest() + '.lock'
    with _file_lock(root / name):
        yield


@contextmanager
def _interrupt_cleanup():
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _save(path, journal):
    journal['updated_at'] = _now()
    _atomic_json(path / 'journal.json', journal)


def _save_best_effort(path, journal):
    # A full disk must not prevent restoration of an already-journaled effect.
    try:
        _save(path, journal)
    except Exception as exc:
        errors = journal.setdefault('durability_errors', [])
        if len(errors) < 16:
            errors.append({'type': type(exc).__name__, 'message': str(exc)[:1024]})


def _restore(path, journal, native):
    outcomes = []
    for change in reversed(journal['changes']):
        if change.get('restored') is True:
            continue
        key = change['key']
        try:
            _require_identity(native, journal)
            current = _preferences(native, journal['bundle_id'], [key])[key]
            if _same_value(current, change['before']):
                change['restored'] = True
                outcomes.append({'preference': key, 'status': 'already_original'})
            elif not _same_value(current, change['expected']):
                outcomes.append({'preference': key, 'status': 'conflict',
                                 'reason': 'current value differs from both the original and the tool request'})
            else:
                change['restore_intent'] = True
                _save_best_effort(path, journal)
                _native(native, 'prefs_set', bundle_id=journal['bundle_id'], key=key,
                        value_base64=change['before']['value_base64'], pid=journal['identity']['pid'],
                        expected_launch_date=journal['identity']['launch_date'])
                observed = _preferences(native, journal['bundle_id'], [key])[key]
                if not _same_value(observed, change['before']):
                    raise ValueError('restored preference readback differs from the original')
                change['restored'] = True
                outcomes.append({'preference': key, 'status': 'restored'})
        except Exception as exc:
            outcomes.append({'preference': key, 'status': 'unresolved', 'reason': str(exc)[:1024]})
        _save_best_effort(path, journal)
    if journal.get('menu_owned') and not journal.get('menu_restored'):
        try:
            snapshot = _require_identity(native, journal)
            opened = _menu(snapshot)
            if opened is None:
                raise ValueError('menu state is unknown; no dismiss attempted')
            if opened:
                journal['menu_restore_intent'] = True
                _save_best_effort(path, journal)
                journal['menu_close_result'] = _native(native, 'dismiss_menu', bundle_id=journal['bundle_id'],
                        pid=journal['identity']['pid'], index=journal['status_index'],
                        expected_launch_date=journal['identity']['launch_date'])
                snapshot = _require_identity(native, journal)
                if _menu(snapshot) is not False:
                    raise ValueError('test-opened menu closure was not observed')
            journal['menu_restored'] = True
            outcomes.append({'menu': 'status_item', 'status': 'restored_closed'})
        except Exception as exc:
            outcomes.append({'menu': 'status_item', 'status': 'unresolved', 'reason': str(exc)[:1024]})
        _save_best_effort(path, journal)
    unresolved = any(not change.get('restored') for change in journal['changes']) or (
        journal.get('menu_owned') and not journal.get('menu_restored'))
    return {'status': 'partial' if unresolved else 'confirmed', 'outcomes': outcomes}


def _receipt(path, journal, cleanup, error=None, *, operation='run'):
    status = 'partial' if cleanup['status'] != 'confirmed' or journal.get('durability_errors') else ('failed' if error else 'confirmed')
    receipt = {'format': FORMAT, 'operation': operation, 'session_id': journal['session_id'], 'status': status,
               'bundle_id': journal['bundle_id'], 'live': journal['live'],
               'identity': journal.get('identity'), 'cleanup': cleanup,
               'cleanup_scope': 'owned journaled intents only; no app launch/quit or unrelated key restoration',
               'artifacts': {'journal': str(path / 'journal.json')},
               'limitations': [
                   'SIGKILL/power loss cannot run cleanup; recover this durable journal explicitly.',
                   'Concurrent preference writes are checked before restoration, not atomically locked against other apps.',
                   'Preference readback does not prove an already-running app refreshed its cached UI.',
                   'Process identity is bundle/PID/launch date; source binary qualification is separate.',
               ]}
    if (path / 'before.json').exists():
        receipt['artifacts']['before'] = str(path / 'before.json')
    if journal.get('capture') is not None:
        receipt['artifacts'].update(capture=str(path / 'capture.png'), capture_metadata=str(path / 'capture.json'))
    if error:
        receipt['error'] = error
    if journal.get('durability_errors'):
        receipt['durability_errors'] = journal['durability_errors']
    try:
        _atomic_json(path / 'receipt.json', receipt)
    except Exception as exc:
        receipt['status'] = 'partial'
        receipt['receipt_write_error'] = {'type': type(exc).__name__, 'message': str(exc)[:1024]}
    return receipt


def run_session(*, bundle_id, output, native, live=False, status_index=None, display_id=None,
                rect=None, preference_changes=None, keys=(), max_seconds=30):
    """Observe/capture, optionally act explicitly, then restore only owned changes."""
    bundle_id = _bundle(bundle_id)
    keys = _keys(keys)
    if type(live) is not bool:
        raise ValueError('live must be boolean')
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not math.isfinite(max_seconds) or not 0 < max_seconds <= 120:
        raise ValueError('max_seconds must be in 0..120')
    if status_index is not None and (type(status_index) is not int or not 0 <= status_index < 64 or not live):
        raise ValueError('status_index requires live=true and an index in 0..63')
    if display_id is not None and (type(display_id) is not int or not 0 < display_id < 1 << 32):
        raise ValueError('display_id must be a positive uint32 integer')
    if rect is not None and (display_id is None or not isinstance(rect, dict) or set(rect) != {'x', 'y', 'width', 'height'} or
                             any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in rect.values()) or
                             rect['width'] <= 0 or rect['height'] <= 0):
        raise ValueError('rect requires one display and finite global x/y/positive width/height')
    changes = {} if preference_changes is None else preference_changes
    if not isinstance(changes, dict) or any(key not in keys for key in changes) or (changes and not live):
        raise ValueError('preference_changes require live=true and explicitly selected keys')
    expected = {key: _value(value) for key, value in changes.items()}
    with _target_lock(bundle_id):
        path = _private_path(output, new=True)
        with _file_lock(path / '.controller.lock'), _interrupt_cleanup():
            journal = {'format': FORMAT, 'session_id': str(uuid.uuid4()), 'bundle_id': bundle_id,
                       'live': live, 'status_index': status_index, 'created_at': _now(),
                       'phase': 'snapshot', 'changes': [], 'menu_owned': False, 'menu_restored': False}
            if isinstance(getattr(native, 'identity', None), dict):
                journal['native_identity'] = native.identity
            _save(path, journal)
            started = time.monotonic()
            error, interruption = None, None
            def within_budget():
                if time.monotonic() - started > max_seconds:
                    raise TimeoutError('forward session budget expired; restoration still runs')
            try:
                before = _snapshot(native, bundle_id)
                journal['identity'] = _identity(before)
                journal['initial_menu_open'] = _menu(before)
                before['preferences'] = _preferences(native, bundle_id, keys)
                _atomic_json(path / 'before.json', before)
                journal['phase'] = 'prepared'
                _save(path, journal)
                for key, wanted in expected.items():
                    within_budget()
                    _require_identity(native, journal)
                    current = _preferences(native, bundle_id, [key])[key]
                    if not _same_value(current, before['preferences'][key]):
                        raise ValueError('preference changed before the action; no write attempted')
                    change = {'key': key, 'before': before['preferences'][key], 'expected': wanted, 'restored': False}
                    journal['changes'].append(change)
                    journal['phase'] = 'preference_intent'
                    _save(path, journal)
                    if not _same_value(change['before'], wanted):
                        _native(native, 'prefs_set', bundle_id=bundle_id, key=key,
                                value_base64=wanted['value_base64'], pid=journal['identity']['pid'],
                                expected_launch_date=journal['identity']['launch_date'])
                        actual = _preferences(native, bundle_id, [key])[key]
                        if not _same_value(actual, wanted):
                            raise ValueError('preference request readback did not match')
                if status_index is not None:
                    within_budget()
                    current = _require_identity(native, journal)
                    if _menu(current) is None or journal['initial_menu_open'] is None:
                        raise ValueError('live menu action requires known initial/current menu state')
                    if _menu(current) != journal['initial_menu_open']:
                        raise ValueError('menu state changed before the action; no toggle attempted')
                    if not _menu(current):
                        journal['menu_owned'] = True
                        journal['phase'] = 'menu_open_intent'
                        _save(path, journal)
                        journal['menu_open_result'] = _native(native, 'press_status', bundle_id=bundle_id, pid=journal['identity']['pid'],
                                index=status_index, expected_launch_date=journal['identity']['launch_date'])
                        action = journal['menu_open_result']
                        if action.get('delivery', {}).get('method') == 'none':
                            # Another actor opened it between observations; no owned input occurred.
                            journal['menu_owned'] = False
                            _save(path, journal)
                        current = _require_identity(native, journal)
                        if _menu(current) is not True:
                            raise ValueError('requested status menu opening was not observed')
                        _atomic_json(path / 'after-open.json', current)
                if display_id is not None:
                    within_budget()
                    capture_arguments = {'display_id': display_id, 'output': str(path / 'capture.png')}
                    if rect is not None:
                        capture_arguments['rect'] = rect
                    capture = _native(native, 'capture', **capture_arguments)
                    _atomic_json(path / 'capture.json', capture)
                    journal['capture'] = capture
                journal['phase'] = 'restoring'
            except BaseException as exc:
                error = {'type': type(exc).__name__, 'message': str(exc)[:1024]}
                if not isinstance(exc, Exception):
                    interruption = exc
                journal['phase'] = 'restoring_after_failure'
            finally:
                _save_best_effort(path, journal)
                cleanup = _restore(path, journal, native)
                journal['phase'] = 'complete' if cleanup['status'] == 'confirmed' else 'recovery_required'
                _save_best_effort(path, journal)
                receipt = _receipt(path, journal, cleanup, error)
            if interruption is not None:
                raise interruption
            return receipt


def recover_session(output, native):
    """Inspect effects before explicitly restoring a no-longer-owned session."""
    path = _private_path(output, new=False)
    journal = _read_journal(path)
    if not isinstance(journal, dict) or journal.get('format') != FORMAT:
        raise ValueError('unsupported session journal')
    bundle_id = _bundle(journal.get('bundle_id'))
    with _target_lock(bundle_id), _file_lock(path / '.controller.lock'), _interrupt_cleanup():
        # Reload under both locks so another controller cannot update between reads.
        journal = _read_journal(path)
        if not isinstance(journal, dict) or journal.get('format') != FORMAT or journal.get('bundle_id') != bundle_id or type(journal.get('live')) is not bool:
            raise ValueError('invalid recovery journal')
        if not isinstance(journal.get('session_id'), str) or not journal['session_id']:
            raise ValueError('invalid recovery session identity')
        if type(journal.get('menu_owned')) is not bool or type(journal.get('menu_restored')) is not bool:
            raise ValueError('invalid recovery menu state')
        changes = journal.get('changes')
        if not isinstance(changes, list) or len(changes) > _MAX_KEYS or (changes and not journal['live']):
            raise ValueError('invalid recovery preference intents')
        keys = _keys([change.get('key') for change in changes if isinstance(change, dict)])
        if len(keys) != len(changes):
            raise ValueError('invalid recovery preference records')
        for change in changes:
            if type(change.get('restored')) is not bool:
                raise ValueError('invalid recovery completion state')
            change['before'] = _preference_state(change.get('before'))
            change['expected'] = _preference_state(change.get('expected'))
        if changes or journal['menu_owned']:
            identity = journal.get('identity')
            if not isinstance(identity, dict) or identity.get('bundle_id') != bundle_id or identity.get('running') is not True or \
                    type(identity.get('pid')) is not int or identity['pid'] <= 0 or not isinstance(identity.get('launch_date'), str) or not identity['launch_date']:
                raise ValueError('invalid recovery target identity')
        if journal.get('menu_owned') and (not journal['live'] or journal.get('initial_menu_open') is not False or
                                         type(journal.get('status_index')) is not int or not 0 <= journal['status_index'] < 64):
            raise ValueError('invalid recovery menu intent')
        cleanup = _restore(path, journal, native)
        journal['phase'] = 'complete' if cleanup['status'] == 'confirmed' else 'recovery_required'
        _save_best_effort(path, journal)
        return _receipt(path, journal, cleanup, operation='recover')


def _read_journal(path):
    with (path / 'journal.json').open('rb') as stream:
        data = stream.read(_MAX_JOURNAL + 1)
    if len(data) > _MAX_JOURNAL:
        raise ValueError('session journal exceeds 4 MiB')
    def finite(value):
        raise ValueError('session journal must contain finite JSON')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate session journal field')
            result[key] = value
        return result
    return json.loads(data, parse_constant=finite, object_pairs_hook=unique)
