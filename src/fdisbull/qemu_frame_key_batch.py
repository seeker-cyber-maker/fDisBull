"""Bounded stopped keyboard plans and one captured public-operation owner.

Plans are observations, never reservations. Only a complete unchanged typed
refusal may preserve the current owner. An uncertain apply is never replayed.
"""
from copy import deepcopy
from functools import wraps
import hashlib
import inspect
import json
import struct
import time
import uuid

from .dosbox_rpc import DebuggerError
from .operation_budget import request_deadline


PLAN_COMMAND = 'x-fdisbull-plan-frame-key-batch'
APPLY_COMMAND = 'x-fdisbull-apply-frame-key-batch'
BATCH_COMMANDS = frozenset({PLAN_COMMAND, APPLY_COMMAND})
INPUT_RECEIPT_RESERVE = 8192
MAX_RECEIPT_BYTES = INPUT_RECEIPT_RESERVE - 2
REASONS = frozenset({'invalid-edges', 'unsupported-profile', 'unsupported-qcode',
    'device-busy', 'insufficient-space', 'stale-state', 'ownership-conflict',
    'counter-exhausted', 'migration-blocked'})
STATE_FIELDS = (
    'accepted-edges', 'active', 'api-version', 'controller-mode',
    'controller-obdata', 'controller-obsrc', 'controller-pending',
    'controller-status', 'device-path', 'device-type', 'edge-capacity', 'epoch',
    'fifo-command-pointer', 'fifo-count', 'fifo-read-pointer', 'fifo-sha256',
    'fifo-write-pointer', 'foreign-held', 'generation', 'held', 'modifier-mask',
    'repeat-supported', 'scan-enabled', 'scancode-set', 'throttle-deadline-ns',
    'token', 'translated', 'valid', 'write-command')
_BOOLS = frozenset({'active', 'valid', 'repeat-supported', 'scan-enabled', 'translated'})
_STRINGS = frozenset({'device-path', 'device-type', 'fifo-sha256'})
_ARRAYS = frozenset({'held', 'foreign-held'})
_SIGNED = frozenset({'fifo-command-pointer', 'throttle-deadline-ns', 'write-command'})
_MODIFIERS = {'ctrl': 1, 'shift': 2, 'alt': 4, 'ctrl_r': 8, 'shift_r': 16, 'alt_r': 32}
_NATIVE_EXTRA = frozenset({'ctrl_r', 'shift_r', 'alt_r', 'print', 'pause'})


class VerifiedBatchRefusal(ValueError):
    """A fully typed, request-bound no-effect result, with unchanged proof."""
    def __init__(self, reason, proof, stage):
        super().__init__('Native frame key batch refused: ' + reason)
        self.reason, self.proof, self.stage = reason, deepcopy(proof), stage


class InputReceiptBudgetError(ValueError):
    """Host receipt storage refused before intent or apply dispatch."""


def batch_capability(vm):
    from .qemu_frame_keys import FRAME_KEY_COMMANDS
    advertised = BATCH_COMMANDS.intersection(vm.qmp_commands)
    if advertised and (advertised != BATCH_COMMANDS or not FRAME_KEY_COMMANDS <= vm.qmp_commands):
        raise ValueError('Native frame key batch capability is incomplete')
    return bool(advertised)


def _uint(value, maximum=(1 << 64) - 1):
    return type(value) is int and 0 <= value <= maximum


def _digest(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _text(value, maximum):
    if type(value) is not str or '\0' in value:
        return False
    try:
        return 1 <= len(value.encode('utf-8')) <= maximum
    except UnicodeError:
        return False


def strict_plan_request(arguments):
    """Only this exact bounded schema is a cooperative passive dispatch."""
    if type(arguments) is not dict or set(arguments) != {'edges'}:
        return False
    from .qemu_frame_keys import _CANONICAL
    edges = arguments['edges']
    if type(edges) is not list or not 1 <= len(edges) <= 32:
        return False
    seen = set()
    for edge in edges:
        if (type(edge) is not dict or set(edge) != {'key', 'pressed'}
                or type(edge['key']) is not str or type(edge['pressed']) is not bool
                or edge['key'] not in _CANONICAL.keys() | _NATIVE_EXTRA
                or edge['key'] in seen):
            return False
        seen.add(edge['key'])
    return True


def _proof(raw):
    from .qemu_frame_keys import validate_frame_key_state
    if type(raw) is not dict:
        raise DebuggerError('Invalid frame key batch proof')
    proof = validate_frame_key_state(raw)
    if (not _text(proof['device-path'], 1024) or not _text(proof['device-type'], 128)
            or 'token' in proof and not _text(proof['token'], 128)
            or proof['modifier-mask'] >= 1 << 32
            or any(not _text(key, 64) for key in proof['foreign-held'])):
        raise DebuggerError('Frame key batch proof exceeds its string or scalar bounds')
    return proof


def _string_bytes(value):
    data = value.encode('utf-8')
    return struct.pack('<I', len(data)) + data


def state_payload(proof):
    """Specified binary encoding; callers validate the complete proof first."""
    output = bytearray(b'fdisbull-frame-key-batch-state-v1\0')
    for field in STATE_FIELDS:
        value = proof.get(field)
        if field == 'token':
            output.extend(b'\0' if value is None else b'\1' + _string_bytes(value))
        elif field in _BOOLS:
            output.append(int(value))
        elif field in _STRINGS:
            output.extend(_string_bytes(value))
        elif field in _ARRAYS:
            output.extend(struct.pack('<I', len(value)))
            for key in value:
                output.extend(_string_bytes(key))
        else:
            output.extend(struct.pack('<q' if field in _SIGNED else '<Q', value))
    return bytes(output)


def state_digest(proof):
    return hashlib.sha256(state_payload(proof)).hexdigest()


def batch_payload(state_sha256, edges, encoded, modifiers, prefix):
    output = bytearray(b'fdisbull-frame-key-batch-request-v1\0')
    output.extend(bytes.fromhex(state_sha256))
    output.extend(struct.pack('<I', len(edges)))
    for edge in edges:
        output.extend(_string_bytes(edge['key']))
        output.append(int(edge['pressed']))
    output.extend(struct.pack('<I', len(encoded)))
    output.extend(encoded)
    output.extend(struct.pack('<Q', modifiers))
    output.append(int(prefix))
    return bytes(output)


def batch_digest(state_sha256, edges, encoded, modifiers, prefix):
    return hashlib.sha256(batch_payload(state_sha256, edges, encoded, modifiers, prefix)).hexdigest()


def _echo_edges(raw, expected):
    if not strict_plan_request({'edges': raw}) or raw != expected:
        raise DebuggerError('Frame key batch echoed a different edge request')


def validate_plan(raw, before, edges, expected_held):
    base = {'api-version', 'outcome', 'before', 'edges'}
    ready = {'state-sha256', 'batch-sha256', 'encoded-bytes', 'encoded-byte-count',
        'available-bytes', 'resulting-held', 'resulting-modifier-mask',
        'resulting-translation-prefix'}
    if (type(raw) is not dict or type(raw.get('api-version')) is not int
            or raw['api-version'] != 1 or raw.get('outcome') not in ('ready', 'refused')):
        raise DebuggerError('Invalid native frame key plan outcome')
    allowed = (base | ready,) if raw['outcome'] == 'ready' else (
        base | {'reason'}, base | {'reason', 'required-bytes'})
    if set(raw) not in allowed:
        raise DebuggerError('Unexpected native frame key plan fields')
    actual = _proof(raw['before'])
    if actual != _proof(before):
        raise DebuggerError('Frame key planning changed the captured native proof')
    _echo_edges(raw['edges'], edges)
    if raw['outcome'] == 'refused':
        if type(raw['reason']) is not str or raw['reason'] not in REASONS:
            raise DebuggerError('Unknown frame key planning refusal')
        if 'required-bytes' in raw and (raw['reason'] != 'insufficient-space'
                or not _uint(raw['required-bytes'], 256)
                or not 0 <= actual['fifo-count'] <= 16
                or raw['required-bytes'] <= 16 - actual['fifo-count']):
            raise DebuggerError('Invalid frame key planning capacity refusal')
        raise VerifiedBatchRefusal(raw['reason'], actual, 'plan')
    encoded = raw['encoded-bytes']
    if (type(encoded) is not list or len(encoded) > 16
            or any(not _uint(value, 255) for value in encoded)
            or not _uint(raw['encoded-byte-count'], 16)
            or raw['encoded-byte-count'] != len(encoded)
            or not _uint(raw['available-bytes'], 16)
            or raw['available-bytes'] != 16 - actual['fifo-count']
            or len(encoded) > raw['available-bytes']
            or type(raw['resulting-held']) is not list
            or any(type(key) is not str for key in raw['resulting-held'])
            or raw['resulting-held'] != expected_held
            or not _uint(raw['resulting-modifier-mask'], 63)
            or raw['resulting-modifier-mask'] != sum(_MODIFIERS.get(k, 0) for k in expected_held)
            or raw['resulting-translation-prefix'] is not False):
        raise DebuggerError('Invalid native frame key plan encoding or result')
    for name in ('state-sha256', 'batch-sha256'):
        if not _digest(raw[name]):
            raise DebuggerError('Invalid frame key plan digest')
    if (raw['state-sha256'] != state_digest(actual)
            or raw['batch-sha256'] != batch_digest(raw['state-sha256'], edges,
                encoded, raw['resulting-modifier-mask'], False)):
        raise DebuggerError('Frame key plan digest does not bind its state and encoding')
    return deepcopy(raw)


def validate_apply(raw, request, plan):
    base = {'api-version', 'outcome', 'before', 'after'} | set(request)
    if (type(raw) is not dict or type(raw.get('api-version')) is not int
            or raw['api-version'] != 1 or raw.get('outcome') not in ('accepted', 'refused')):
        raise DebuggerError('Invalid native frame key apply outcome')
    extra = {'encoded-byte-count', 'accepted-edge-count'} if raw['outcome'] == 'accepted' else {'reason'}
    if set(raw) != base | extra:
        raise DebuggerError('Unexpected native frame key apply fields')
    _echo_edges(raw['edges'], request['edges'])
    for key, value in request.items():
        if type(raw[key]) is not type(value) or raw[key] != value:
            raise DebuggerError('Native frame key apply differs from its exact request')
    before, after = _proof(raw['before']), _proof(raw['after'])
    if before != plan['before']:
        raise DebuggerError('Frame key apply lost continuity with its captured plan')
    if raw['outcome'] == 'refused':
        if type(raw['reason']) is not str or raw['reason'] not in REASONS or after != before:
            raise DebuggerError('Frame key refusal lacks an unchanged complete proof')
        raise VerifiedBatchRefusal(raw['reason'], before, 'apply')
    count, encoded = len(request['edges']), plan['encoded-byte-count']
    if (not _uint(raw['encoded-byte-count'], 16) or raw['encoded-byte-count'] != encoded
            or not _uint(raw['accepted-edge-count'], 32) or raw['accepted-edge-count'] != count
            or not after['active'] or after.get('token') != request['token']
            or after['epoch'] != before['epoch'] or after['generation'] != before['generation'] + 1
            or after['accepted-edges'] != before['accepted-edges'] + count
            or after['held'] != plan['resulting-held'] or after['foreign-held']
            or after['modifier-mask'] != plan['resulting-modifier-mask']
            or after['fifo-count'] != before['fifo-count'] + encoded
            or after['fifo-read-pointer'] != before['fifo-read-pointer']
            or after['fifo-write-pointer'] != (before['fifo-write-pointer'] + encoded) % 256
            or after['fifo-command-pointer'] != -1 or after['write-command'] != -1
            or any(after[k] != before[k] for k in ('device-path', 'device-type',
                'scan-enabled', 'scancode-set', 'translated', 'controller-mode',
                'controller-obdata', 'throttle-deadline-ns'))):
        raise DebuggerError('Native frame key batch acceptance differs from intent')
    if encoded:
        if (after['controller-status'] != (before['controller-status'] & ~0x21) | 1
                or after['controller-pending'] != before['controller-pending'] | 0x10
                or after['controller-obsrc'] != 1 or after['edge-capacity'] != 0):
            raise DebuggerError('Native frame key proof is not the actual post-IRQ state')
    elif any(after[k] != before[k] for k in ('controller-status', 'controller-pending',
            'controller-obsrc', 'fifo-sha256', 'edge-capacity')):
        raise DebuggerError('Zero-byte frame key release changed the device queue or IRQ')
    return after


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def compact_receipt(native, edges, plan):
    from .qemu_frame_keys import _CANONICAL
    return dict(native=deepcopy(native), edges=deepcopy(edges),
        held=sorted(_CANONICAL[key] for key in native['held']),
        guest_consumed=None, repeat_supported=False,
        batch=dict(api_version=1, state_sha256=plan['state-sha256'],
            batch_sha256=plan['batch-sha256'], encoded_bytes=plan['encoded-byte-count'],
            accepted_edges=len(edges)))


def reserve_receipt(plan, token, edges):
    """Bound actual compact JSON before either intent or mutating dispatch."""
    after = deepcopy(plan['before'])
    after.update(active=True, token=token, generation=after['generation'] + 1,
        held=list(plan['resulting-held']), **{
        'accepted-edges': after['accepted-edges'] + len(edges),
        'modifier-mask': plan['resulting-modifier-mask'], 'fifo-count': 16,
        'fifo-sha256': 'f' * 64, 'fifo-read-pointer': 255, 'fifo-write-pointer': 255,
        'fifo-command-pointer': -1, 'write-command': -1, 'edge-capacity': 32,
        'controller-status': 255, 'controller-mode': 255, 'controller-pending': 255,
        'controller-obsrc': (1 << 32) - 1, 'controller-obdata': 255,
        'throttle-deadline-ns': (1 << 63) - 1})
    maximum = len(_json_bytes(compact_receipt(after, edges, plan)))
    if maximum > MAX_RECEIPT_BYTES:
        raise InputReceiptBudgetError('Frame key batch receipt exceeds the input journal reservation')
    return maximum


def plan_batch(session, native, edges, expected_held):
    owner = input_owner(session)
    if not edges or not batch_capability(owner.vm):
        return None
    raw = owner.qmp(PLAN_COMMAND, {'edges': deepcopy(edges)})
    plan = validate_plan(raw, native, edges, expected_held)
    owner.check()
    token = native.get('token') or uuid.uuid4().hex
    request = dict(token=token, **{'expected-epoch': native['epoch'],
        'expected-generation': native['generation'],
        'expected-state-sha256': plan['state-sha256'],
        'expected-batch-sha256': plan['batch-sha256'], 'edges': deepcopy(edges)})
    return dict(wire=plan, request=request, receipt_bound=reserve_receipt(plan, token, edges))


def apply_batch(session, native, edges, expected_held, planned):
    from .qemu_frame_keys import adopt_frame_keys
    owner = input_owner(session)
    if planned is None:
        planned = plan_batch(session, native, edges, expected_held)
    if planned is None:
        raise DebuggerError('Frame key batch plan is absent')
    plan, request = planned['wire'], planned['request']
    if plan['before'] != native or request['edges'] != edges or plan['resulting-held'] != expected_held:
        raise DebuggerError('Frame key batch plan belongs to another stopped request')
    owner.call('_event', 'frame-inputs-intent', dict(token=request['token'],
        expected_generation=native['generation'], edges=deepcopy(edges),
        state_sha256=plan['state-sha256'], batch_sha256=plan['batch-sha256']))
    raw = owner.qmp(APPLY_COMMAND, deepcopy(request), mutating=True)
    if type(raw) is dict and raw.get('outcome') == 'accepted':
        owner.accepted_evidence = deepcopy(raw)
    result = validate_apply(raw, request, plan)
    receipt = compact_receipt(result, edges, plan)
    if len(_json_bytes(receipt)) > planned['receipt_bound'] or len(_json_bytes(receipt)) > MAX_RECEIPT_BYTES:
        raise DebuggerError('Native frame key receipt exceeds its pre-dispatch bound')
    owner.adopt(adopt_frame_keys, result, expected_held)
    owner.accepted_evidence = deepcopy(receipt)
    owner.call('_event', 'frame-inputs', receipt)
    return receipt


_CALLBACKS = (
    '_event', '_frame_keys_query', '_frame_keys_prepare', '_frame_keys_apply',
    '_input_schedule_bound', '_input_no_transaction', '_stopped',
    '_history_latest', '_frame_current', '_frame_capability', '_frame_manifest',
    '_frame_delta', '_frame_budget', '_history_admission', '_history_pending',
    '_history_new_revision', '_history_live_fingerprint', '_frame_summary',
    '_frame_execute', '_history_resolve_known_stop', '_frame_bytes_used',
    '_frame_capture_delta', '_history_checkpoint', '_frame_image',
    '_history_validate_node_before_restore', '_timeline_frame_keys',
    '_history_remaining_ms', '_run_with_hooks', 'display_observe',
    'capture_display', 'registers', '_frame_state_bytes',
    '_frame_capture_source', 'video_frame_observe', 'video_frame_advance',
    'capture_video_frame', '_history_state_artifact', '_history_identity')


class FrameInputOwner:
    """Captured resources survive callback replacement and late outer failure.

    This allows intended input/render effects; it is not an ObservationLease
    or a promise that the cooperative revision is constant.
    """
    def __init__(self, session):
        from .qemu_session_revision import session_revision
        from .qemu_video_control import require_no_video_frame_fence
        from .qemu_step_over import require_no_step_over
        from .qemu_input import require_released_machine_input
        from .qemu_instrumented_checkpoint import preflight
        self.session, self.vm = session, session.vm
        vm = self.vm
        self.lock = vm.lock
        self.authority = getattr(vm, 'observation_authority', None)
        self.revision = session_revision(vm)
        self.authority_lifetime = getattr(self.authority, 'lifetime', None)
        self.session_id = self.revision.session_id
        self.project = getattr(session, 'project', None)
        self.context_process = getattr(session, '_process', None)
        self.context = getattr(vm, 'context', None)
        self.serial = getattr(session, '_channel', None)
        self.serial_socket = getattr(self.serial, 'socket', None)
        self.clients = tuple((name, getattr(vm, name, None),
            getattr(getattr(vm, name, None), 'socket', None)) for name in ('qmp', 'gdb'))
        self.qmp_call = getattr(self.clients[0][1], 'call', None)
        self.acquire, self.release = self.lock.acquire, self.lock.release
        self.guards = (getattr(vm, 'operation_guard', None), getattr(vm, 'history_operation_guard', None))
        self.callbacks = {name: getattr(session, name, None) for name in _CALLBACKS}
        self.preflights = (require_no_video_frame_fence, require_no_step_over,
                          require_released_machine_input, preflight)
        self.commands = frozenset(getattr(vm, 'qmp_commands', ()))
        self.expected_owner = getattr(vm, '_frame_key_owner', None)
        self.expected_ledger = deepcopy(self.expected_owner)
        process = getattr(vm, 'process', None)
        self.cleanup_owner = dict(process=process, stdin=getattr(process, 'stdin', None),
            stdout=getattr(process, 'stdout', None), channels=tuple(getattr(vm, '_channels', ())),
            temporary=getattr(vm, 'temporary', None), qemu_image_proof=getattr(vm, '_qemu_image_proof', None),
            admission_guest_pidfd=getattr(vm, '_admission_guest_pidfd', None),
            close_observer=getattr(vm, 'close_observer', None), context=session,
            context_process=self.context_process, frame_read=self, closed=False)
        for name, client, sock in self.clients:
            self.cleanup_owner[name], self.cleanup_owner[name + '_socket'] = client, sock
        self.deadlines = [(vm, 'operation_deadline', getattr(vm, 'operation_deadline', None))]
        self.deadlines.extend((client, 'operation_deadline', getattr(client, 'operation_deadline', None))
                              for _, client, _ in self.clients if client is not None)
        if self.serial is not None:
            self.deadlines.append((self.serial, 'operation_deadline', getattr(self.serial, 'operation_deadline', None)))
        self.saved_session = {name: getattr(session, name, None) for name in ('_deadline', '_rpc_deadline')}
        self.saved_busy = getattr(session, '_history_busy', False)
        self.deadline = None
        self.changed = self.closed = self.mutating = self.intent_written = False
        self.native_dispatch = False
        self.accepted_evidence = None
        self.cleanup_errors, self.closed_resources = [], set()

    def identity_matches(self, *, ledger=True):
        vm, s, old = self.vm, self.session, self.cleanup_owner
        if (s.vm is not vm or getattr(vm, 'lock', None) is not self.lock
                or getattr(s, '_frame_input_owner', None) is not self
                or getattr(s, 'closed', False) or getattr(vm, 'closed', False)
                or getattr(s, 'project', None) is not self.project
                or getattr(s, '_process', None) is not self.context_process
                or getattr(vm, 'context', None) is not self.context
                or getattr(vm, 'observation_authority', None) is not self.authority
                or getattr(vm, 'session_revision', None) is not self.revision
                or getattr(self.authority, 'lifetime', None) != self.authority_lifetime
                or self.revision.session_id != self.session_id
                or getattr(s, '_channel', None) is not self.serial
                or getattr(self.serial, 'socket', None) is not self.serial_socket
                or frozenset(getattr(vm, 'qmp_commands', ())) != self.commands):
            return False
        if ledger and (getattr(vm, '_frame_key_owner', None) is not self.expected_owner
                or self.expected_owner != self.expected_ledger):
            return False
        if any(getattr(vm, name, None) is not client or getattr(client, 'socket', None) is not sock
               for name, client, sock in self.clients):
            return False
        if any(getattr(vm, attr, None) is not old[key] for attr, key in
               (('process', 'process'), ('temporary', 'temporary'), ('_qemu_image_proof', 'qemu_image_proof'),
                ('close_observer', 'close_observer'))):
            return False
        channels = tuple(getattr(vm, '_channels', ()))
        if (len(channels) != len(old['channels'])
                or any(left is not right for left, right in zip(channels, old['channels']))
                or getattr(vm, '_admission_guest_pidfd', None) != old['admission_guest_pidfd']
                or getattr(old['process'], 'stdin', None) is not old['stdin']
                or getattr(old['process'], 'stdout', None) is not old['stdout']):
            return False
        return True

    def check(self, *, deadline=True):
        if self.closed or not self.identity_matches():
            self.changed = True
            raise DebuggerError('Frame input original owner or channels changed')
        if deadline and self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError('QEMU frame input exceeded its outer deadline')
        return self

    def invoke(self, callback, *args, **kwargs):
        self.check()
        try:
            result = callback(*args, **kwargs)
        except BaseException:
            if not self.identity_matches():
                self.changed = True
            raise
        try:
            self.check()
        except BaseException as error:
            if getattr(error, 'result', None) is None:
                error.result = result
            raise
        return result

    def call(self, name, *args, **kwargs):
        callback = self.callbacks[name]
        if callback is None:
            raise DebuggerError('Captured frame input callback is unavailable: ' + name)
        return self.invoke(callback, *args, **kwargs)

    def qmp(self, command, arguments=None, *, mutating=False):
        self.check()
        self.native_dispatch = True
        if mutating:
            self.mutating = True
        try:
            result = self.qmp_call(command, arguments)
        except BaseException:
            if not self.identity_matches():
                self.changed = True
            raise
        if mutating and type(result) is dict and (
                result.get('outcome') == 'accepted'
                or command == 'x-fdisbull-apply-frame-key-edges'):
            # Preserve the received evidence even when the callback replaced
            # the owner before validation/adoption can occur.
            self.accepted_evidence = deepcopy(result)
        try:
            self.check()
        except BaseException as error:
            if getattr(error, 'result', None) is None:
                error.result = result
            raise
        return result

    def adopt(self, callback, native, held):
        self.check()
        callback(self.vm, native, expected_held=held)
        # Only this explicit adoption can replace the expected host ledger.
        if not self.identity_matches(ledger=False):
            self.changed = True
            raise DebuggerError('Frame input owner changed during receipt adoption')
        self.expected_owner = getattr(self.vm, '_frame_key_owner', None)
        self.expected_ledger = deepcopy(self.expected_owner)
        self.check()

    def close_resource(self, resource, method='close'):
        key = id(resource), method
        if resource is None or key in self.closed_resources:
            return
        self.closed_resources.add(key)
        callback = getattr(resource, method, None)
        if callable(callback):
            callback()

    def close_channel(self, name):
        client, sock = self.cleanup_owner[name], self.cleanup_owner[name + '_socket']
        self.close_resource(sock if sock is not None else client)
        if sock is not None and getattr(client, 'socket', None) is sock:
            client.socket = None

    def can_notify(self):
        return (self.session.vm is self.vm
            and getattr(self.session, 'project', None) is self.project
            and getattr(self.session, '_process', None) is self.context_process
            and getattr(self.vm, 'observation_authority', None) is self.authority
            and getattr(self.vm, 'session_revision', None) is self.revision)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.vm._fdisbull_control_quarantine = 'failed frame input original owner'
        actions = [self.revision.effect]
        if self.authority is not None:
            actions.append(lambda: self.authority.invalidate('frame input original owner closed'))
        from .qemu_machine import _close_observation_owner
        actions.extend((lambda: _close_observation_owner(self.vm, self.cleanup_owner),
                        lambda: self.close_resource(self.serial_socket or self.serial)))
        for action in actions:
            try:
                action()
            except BaseException as error:
                self.cleanup_errors.extend(getattr(error, 'machine_cleanup_errors', [type(error).__name__]))
        if self.can_notify():
            self.session.closed = True

    def attach(self, error, result=None):
        if result is not None and getattr(error, 'result', None) is None:
            error.result = result
        error.frame_input_owner = dict(session_id=self.session_id, owner_changed=self.changed,
            mutating_dispatch=self.mutating, intent_written=self.intent_written,
            accepted_evidence=deepcopy(self.accepted_evidence), cleanup_errors=list(self.cleanup_errors))


def input_owner(session):
    owner = getattr(session, '_frame_input_owner', None)
    if not isinstance(owner, FrameInputOwner):
        raise DebuggerError('Frame input requires its captured public-operation owner')
    owner.check()
    return owner


def frame_input_operation(function):
    """Replacement outer wrapper only for frame_inputs and timeline_advance."""
    signature = inspect.signature(function)
    @wraps(function)
    def invoke(session, *args, **kwargs):
        bound = signature.bind(session, *args, **kwargs)
        bound.apply_defaults()
        if getattr(session, '_frame_input_owner', None) is not None:
            raise DebuggerError('A frame input operation is already active')
        owner = FrameInputOwner(session)  # Before guards, callbacks or acquire.
        proposed = request_deadline(session, bound.arguments.get('timeout_ms', 60000))
        limits = [proposed, *owner.saved_session.values(), *(row[2] for row in owner.deadlines)]
        owner.deadline = min(value for value in limits if value is not None)
        session._frame_input_owner = owner
        acquired, result, primary = False, None, None
        try:
            owner.check()
            wait = min(10.0, owner.deadline - time.monotonic())
            if wait <= 0:
                raise TimeoutError('Frame input could not acquire its original machine before deadline')
            acquired = bool(owner.acquire(timeout=wait))
            owner.check()
            if not acquired:
                raise TimeoutError('Frame input could not acquire its original machine before deadline')
            if owner.guards[0] is not None:
                owner.invoke(owner.guards[0], function.__name__)
            session._history_busy = True
            if owner.guards[1] is not None:
                owner.invoke(owner.guards[1], function.__name__, args, kwargs)
            owner.invoke(owner.revision.public_operation, function.__name__, args, kwargs)
            session._rpc_deadline = session._deadline = owner.deadline
            for target, field, _ in owner.deadlines:
                setattr(target, field, owner.deadline)
                owner.check()
            result = function(session, *args, **kwargs)
            owner.check()
        except BaseException as error:
            primary = error
        finally:
            # Write only captured resources. A replacement context owns its
            # own session deadline fields; no replacement channel is touched.
            restores = list(owner.deadlines) if acquired else []
            if acquired and session.vm is owner.vm:
                restores.extend((session, field, old) for field, old in owner.saved_session.items())
                restores.append((session, '_history_busy', owner.saved_busy))
            for target, field, old in restores:
                try:
                    setattr(target, field, old)
                    owner.check(deadline=False)
                except BaseException as error:
                    owner.cleanup_errors.append(type(error).__name__)
                    if primary is None:
                        primary = error
            if acquired:
                try:
                    owner.release()
                    owner.check(deadline=False)
                except BaseException as error:
                    owner.cleanup_errors.append(type(error).__name__)
                    if primary is None:
                        primary = error
            if primary is not None:
                preserving = (isinstance(primary, VerifiedBatchRefusal)
                              and not owner.changed and not owner.cleanup_errors)
                if (acquired or owner.changed) and not preserving and (
                        owner.changed or owner.cleanup_errors or owner.mutating or owner.intent_written
                        or isinstance(primary, DebuggerError) and owner.native_dispatch
                        or not isinstance(primary, ValueError)):
                    owner.close()
                owner.attach(primary, result)
            if getattr(session, '_frame_input_owner', None) is owner:
                session._frame_input_owner = None
        if primary is not None:
            raise primary.with_traceback(primary.__traceback__)
        return result
    return invoke
