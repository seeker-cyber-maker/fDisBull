"""Bracket a stored native frame with state reads, without asserting atomicity."""
from copy import deepcopy
import json
import math
import re

from .native_controller import NativeControlError

_MAX_RECORD_BYTES = 1024 * 1024
_MAX_ATTEMPT_BYTES = 4 * 1024 * 1024
_SHA = re.compile(r'^[0-9a-f]{64}$')


def _json_copy(value):
    """Copy finite JSON without silently converting keys or non-JSON objects."""
    def check(item, stack):
        if item is None or type(item) in (str, bool, int): return
        if type(item) is float:
            if not math.isfinite(item): raise ValueError('non-finite observation')
            return
        if type(item) not in (list, dict) or id(item) in stack:
            raise ValueError('observation is not finite JSON')
        stack.add(id(item))
        if type(item) is dict:
            if any(type(k) is not str for k in item): raise ValueError('invalid observation key')
            for part in item.values(): check(part, stack)
        else:
            for part in item: check(part, stack)
        stack.remove(id(item))
    try:
        check(value, set())
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()) > _MAX_RECORD_BYTES:
            raise ValueError('observation exceeds size limit')
        return deepcopy(value)
    except (RecursionError, UnicodeError, TypeError, OverflowError) as exc:
        raise ValueError('invalid observation') from exc


def _positive(value, name):
    if (type(value) not in (int, float) or type(value) is float and not math.isfinite(value)
            or value <= 0):
        raise ValueError(name+' must be a finite positive number')


def _status_issue(status):
    if type(status) is not dict: return 'status is not an object'
    if status.get('state') != 'stopped': return 'guest is not known to be stopped'
    if type(status.get('session_id')) is not str or not status['session_id']:
        return 'session identity is missing'
    for key in ('state_revision', 'frame_id', 'mode_id'):
        if type(status.get(key)) is not int or status[key] < 0:
            return key+' is missing or invalid'
    return None


def _frame_issue(frame):
    if type(frame) is not dict: return 'frame is not an object'
    if not any(type(frame.get(k)) is str and frame[k] for k in ('path', 'artifact')):
        return 'frame reference is missing'
    if type(frame.get('sha256')) is not str or _SHA.fullmatch(frame['sha256']) is None:
        return 'frame hash is missing or invalid'
    metadata = frame.get('metadata')
    if type(metadata) is not dict or metadata.get('source') != 'last_completed_guest_frame':
        return 'frame source is missing or invalid'
    if type(metadata.get('session_id')) is not str or not metadata['session_id']:
        return 'frame session is missing'
    for key in ('state_revision', 'frame_id', 'mode_id', 'captured_ticks'):
        if type(metadata.get(key)) is not int or metadata[key] < 0:
            return 'frame '+key+' is missing or invalid'
    return None


def capture_frame_state(controller, capture_frame, *, status_reader=None, state_projector=None,
                        require_fresh=False, baseline_frame_id=None, baseline_frame=None,
                        expected_session_id=None, guest_ms=1000, slice_ms=20, max_polls=64):
    """Read a bounded status/state/frame/state/status bracket from one session.

    A matching bracket is not an atomic read and does not establish that the
    frame depicts the exact CPU state, UI readiness, or native authenticity.
    A timeout returns incomplete; exceptions are retained and re-raised without
    replay. The controller owns all execution and stop handling.
    A bare baseline_frame_id is a caller-asserted ordinal in the current pinned
    session and mode; baseline_frame also binds the prior session and mode.
    """
    if (not callable(capture_frame) or status_reader is not None and not callable(status_reader)
            or state_projector is not None and not callable(state_projector)
            or type(require_fresh) is not bool or type(max_polls) is not int
            or not 1 <= max_polls <= 4096
            or baseline_frame_id is not None and (type(baseline_frame_id) is not int or baseline_frame_id < 0)
            or expected_session_id is not None and (type(expected_session_id) is not str or not expected_session_id)
            or baseline_frame is not None and (type(baseline_frame) is not dict or
                set(baseline_frame) != {'session_id', 'mode_id', 'frame_id'} or
                type(baseline_frame['session_id']) is not str or not baseline_frame['session_id'] or
                type(baseline_frame['mode_id']) is not int or baseline_frame['mode_id'] < 0 or
                type(baseline_frame['frame_id']) is not int or baseline_frame['frame_id'] < 0)
            or baseline_frame is not None and baseline_frame_id is not None):
        raise ValueError('Invalid frame-state observation arguments')
    _positive(guest_ms, 'guest_ms'); _positive(slice_ms, 'slice_ms')
    if not isinstance(getattr(controller, 'journal', None), list) or not isinstance(getattr(controller, 'frame_captures', None), list):
        raise ValueError('Controller must expose journal and frame_captures lists')
    session = getattr(controller, 'session', None)
    if status_reader is None and (not callable(getattr(session, 'call', None)) or
                                  not callable(getattr(session, 'frame_probe', None))):
        raise ValueError('Default status adapter requires session.status and frame_probe')
    actual_session = getattr(getattr(controller, 'session', None), 'session_id', None)
    owner_session = actual_session if type(actual_session) is str and actual_session else None
    ownership_issue = ('controller session identity conflicts with expected session'
                       if owner_session is not None and expected_session_id is not None
                       and owner_session != expected_session_id else None)
    owner_session = owner_session or expected_session_id
    if owner_session is None:
        ownership_issue = 'controller session identity is unknown'
    baseline_id = baseline_frame['frame_id'] if baseline_frame is not None else baseline_frame_id
    record = {'format': 'fdisbull-frame-state-observation-1', 'complete': False,
              'atomic': False, 'frame_state_equivalence': None, 'require_fresh': require_fresh,
              'baseline_frame_id': baseline_id, 'baseline_frame': deepcopy(baseline_frame),
              'baseline_source': ('session_bound' if baseline_frame is not None else
                                  'caller_asserted_ordinal' if baseline_frame_id is not None else
                                  'initial_status' if require_fresh else 'not_supplied'),
              'expected_session_id': owner_session, 'freshness': 'unqualified' if require_fresh else 'not_requested',
              'guest_start': controller.guest_elapsed, 'guest_elapsed_ms': 0,
              'polls': 0, 'status_polls': [], 'status_brackets': [], 'issues': [], 'evidence_bytes': 0,
              'scope': ('Bracketed supplied observations; frame state_revision is the capture RPC revision, '
                        'not a render-CPU revision. No atomic frame/CPU equivalence or UI readiness claim.')}
    controller.frame_captures.append(record)
    controller.journal.append({'kind': 'frame-capture', 'record': record})
    end = controller.guest_elapsed + guest_ms

    def check_limits():
        if controller.blocked_reason is not None:
            raise NativeControlError('Controller stopped: '+str(controller.blocked_reason))
        if controller.clock() >= controller.deadline:
            raise NativeControlError('Frame observation wall budget exhausted')
        if controller.guest_elapsed > controller.guest_budget_ms:
            raise NativeControlError('Frame observation exceeded global guest budget')
        if controller.guest_elapsed > end:
            raise NativeControlError('Frame observation exceeded measured guest budget')

    def checked():
        check_limits()
        admission = getattr(controller, 'admission_check', None)
        if admission is not None:
            admission()
            check_limits()

    def take_into(container, key, callback):
        checked()
        raw = callback()
        # Keep the returned value before validation, timing checks or another I/O.
        container[key] = deepcopy(raw)
        copied = _json_copy(raw)
        container[key] = copied
        record['evidence_bytes'] += len(json.dumps(copied, ensure_ascii=False, separators=(',', ':')).encode())
        if record['evidence_bytes'] > _MAX_ATTEMPT_BYTES:
            raise ValueError('frame observation evidence exceeds size limit')
        checked()
        return copied

    def take(key, callback):
        return take_into(record, key, callback)

    def default_status():
        # SDK session.status owns the stopped-state fact; video.probe supplies
        # only frame metadata. Keep each raw response even if a later call fails.
        bracket = {'kind': 'frame-status-probe', 'complete': False, 'issues': []}
        controller.journal.append(bracket)
        record['status_brackets'].append(bracket)
        before = take_into(bracket, 'session_before', lambda: session.call('session.status'))
        probe = take_into(bracket, 'frame_probe', lambda: session.frame_probe([]))
        after = take_into(bracket, 'session_after', lambda: session.call('session.status'))
        for name, value in (('session_before', before), ('session_after', after)):
            if type(value) is not dict or value.get('state') != 'stopped':
                bracket['issues'].append(name+' is not known stopped')
            if (type(value) is not dict or type(value.get('session_id')) is not str or not value['session_id'] or
                    type(value.get('state_revision')) is not int or value['state_revision'] < 0):
                bracket['issues'].append(name+' lacks valid session or revision')
        if (type(probe) is not dict or type(probe.get('session_id')) is not str or not probe['session_id'] or
                any(type(probe.get(k)) is not int or probe[k] < 0
                    for k in ('state_revision', 'frame_id', 'mode_id', 'captured_ticks'))):
            bracket['issues'].append('frame probe lacks valid identity or metadata')
        if not bracket['issues']:
            for key in ('session_id', 'state_revision'):
                if before[key] != probe[key] or before[key] != after[key]:
                    bracket['issues'].append(key+' differs within status probe')
        if bracket['issues']:
            return {'state': None, 'session_id': None, 'state_revision': None,
                    'frame_id': None, 'mode_id': None}
        bracket['complete'] = True
        return {'state': 'stopped', 'session_id': before['session_id'],
                'state_revision': before['state_revision'], 'frame_id': probe['frame_id'],
                'mode_id': probe['mode_id'], 'captured_ticks': probe['captured_ticks']}

    try:
        if ownership_issue is not None:
            record['issues'].append(ownership_issue); return record
        # Admission retains the controller's normal strict budget policy. Once
        # admitted, read-only work is allowed at (but never beyond) the cap.
        controller._active()
        while True:
            status = take('last_status', status_reader or default_status)
            record['status_polls'].append(deepcopy(status)); record['polls'] += 1
            issue = _status_issue(status)
            if issue:
                record['issues'].append(issue); return record
            if status['session_id'] != owner_session:
                record['issues'].append('status session differs from controller session'); return record
            if record.get('session_id') is None:
                record['session_id'], record['mode_id'] = status['session_id'], status['mode_id']
                if baseline_frame is not None and (baseline_frame['session_id'] != status['session_id'] or
                                                   baseline_frame['mode_id'] != status['mode_id']):
                    record['issues'].append('baseline session or mode differs from current status'); return record
                if require_fresh and baseline_id is None:
                    record['baseline_frame_id'] = status['frame_id']
            elif status['session_id'] != record['session_id'] or status['mode_id'] != record['mode_id']:
                record['issues'].append('session or mode changed during freshness wait'); return record
            if len(record['status_polls']) > 1 and status['frame_id'] < record['status_polls'][-2]['frame_id']:
                record['issues'].append('frame id regressed during freshness wait'); return record
            if not require_fresh or status['frame_id'] > record['baseline_frame_id']:
                break
            if (record['polls'] >= max_polls or controller.guest_elapsed >= end
                    or controller.guest_elapsed >= controller.guest_budget_ms):
                record['freshness'] = 'not_observed'
                record['issues'].append('fresh frame not observed within budget')
                return record
            checked()
            previous_elapsed = controller.guest_elapsed
            runner = getattr(controller, 'input_advance', None) or controller.advance
            runner(min(slice_ms, end-controller.guest_elapsed))
            record['guest_elapsed_ms'] = controller.guest_elapsed-record['guest_start']
            if controller.guest_elapsed <= previous_elapsed:
                raise NativeControlError('Frame polling returned no measured guest progress')
            checked()
        record['status_before'] = deepcopy(status)
        before = take('state_before', controller.read_state)
        frame = take('frame', capture_frame)
        after = take('state_after', controller.read_state)
        final = take('status_after', status_reader or default_status)
        identity_matches = True
        issue = _status_issue(final)
        if issue: record['issues'].append(issue)
        else:
            for key in ('session_id', 'state_revision', 'frame_id', 'mode_id'):
                if final[key] != status[key]:
                    identity_matches = False; record['issues'].append('status '+key+' changed')
        issue = _frame_issue(frame)
        if issue: record['issues'].append(issue)
        else:
            metadata = frame['metadata']
            for key in ('session_id', 'state_revision', 'frame_id', 'mode_id'):
                if metadata[key] != status[key]:
                    identity_matches = False; record['issues'].append('frame '+key+' differs from bracket')
        if require_fresh and identity_matches and not _status_issue(final) and not _frame_issue(frame):
            record['freshness'] = 'confirmed'
        if before is None or after is None:
            record['issues'].append('state is missing')
        else:
            left, right = before, after
            if state_projector is not None:
                left = take('projected_before', lambda: state_projector(deepcopy(before)))
                right = take('projected_after', lambda: state_projector(deepcopy(after)))
            if left is None or right is None:
                record['issues'].append('projected state is missing')
            elif json.dumps(left, sort_keys=True, separators=(',', ':'), ensure_ascii=False) != json.dumps(right, sort_keys=True, separators=(',', ':'), ensure_ascii=False):
                record['issues'].append('bracketed state changed')
        checked()
        record['complete'] = not record['issues']
        return record
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        try: controller._block(error)
        except BaseException as secondary:
            record.setdefault('secondary_errors', []).append({'type': type(secondary).__name__, 'message': str(secondary)})
        raise
    finally:
        record['guest_elapsed_ms'] = controller.guest_elapsed-record['guest_start']
