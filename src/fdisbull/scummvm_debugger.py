"""Source-bound AGI VM debugging through an explicitly patched ScummVM.

ScummVM replaces the original DOS interpreter. All locations here are AGI
logic/resource coordinates; none are presented as original x86 addresses.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import time
import threading
import uuid

from .debugger import DebugSession, bounded, stamp
from .external_files import _file_name
from .keyboard_input import validate_keyboard
from .operation_budget import rpc_budget
from .scummvm_rpc import ScummVMError, ScummVMRPC


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _manifest(game_dir):
    """Bind the entire read-only input set, not just the native project owner."""
    result = []
    size = 0
    for path in sorted(game_dir.rglob('*')):
        if path.is_symlink():
            raise ValueError('ScummVM game inputs cannot contain symbolic links')
        if not path.is_file():
            continue
        if len(result) >= 4096:
            raise ValueError('ScummVM game input count exceeds 4096')
        if size + path.stat().st_size > 256 * 1024 * 1024:
            raise ValueError('ScummVM game inputs exceed 256 MiB')
        with path.open('rb') as stream:
            data = stream.read(256 * 1024 * 1024 - size + 1)
        size += len(data)
        if size > 256 * 1024 * 1024:
            raise ValueError('ScummVM game inputs exceed 256 MiB')
        result.append({'path': str(path.relative_to(game_dir)), 'size': len(data),
                       'sha256': hashlib.sha256(data).hexdigest()})
    return result


def _control_operation(function):
    """Serialize native registration/removal with its wrapper ownership map."""
    @wraps(function)
    def controlled(session, *args, **kwargs):
        with session._control_lock:
            return function(session, *args, **kwargs)
    return controlled


class ScummVMAGISession(DebugSession):
    """One owned replacement-engine VM session with persisted fDisBull evidence."""

    native_hooks_available = False

    @property
    def script_operations(self):
        return {'assert', 'status', 'run', 'trace', 'screenshot', 'frame-probe',
                'scene-check', 'scene-assert', 'scene-click', 'scene-act', 'scene-wait',
                'keyboard.press', 'keyboard.type', 'keyboard.state',
                'keyboard.key-down', 'keyboard.key-up', 'click',
                'click-frame', 'save-state', 'load-state', 'breakpoint',
                'delete-breakpoint', 'engine-state', 'engine-set', 'step',
                'watchpoint', 'delete-watchpoint', 'engine-resource',
                'engine-patch-resource', 'engine-restore-resource', 'engine-cycle'}

    def __init__(self, project, executable, game_dir, *, game_id, version=None,
                 boot_timeout_ms=240000, window=False, _on_spawn=None):
        if window:
            raise ValueError('ScummVM AGI agent currently requires headless mode')
        self.project = project
        self._project_owner_thread = threading.get_ident()
        self.version = project.version(version)
        if self.version['parent'] is not None:
            raise ValueError('ScummVM launch requires original project version 1; patched versions remain separate')
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not self.game_dir.is_dir():
            raise ValueError('Expected an AGI game directory')
        if self.game_dir == project.path.parent or self.game_dir in project.path.parents:
            raise ValueError('Keep the mutable project and private runtime outside the read-only AGI game directory')
        owner = self.game_dir / project.meta['filename']
        if owner.is_symlink() or not owner.is_file() or owner.resolve().parent != self.game_dir:
            raise ValueError('Project source must be an original file directly in the game directory')
        source_sha256 = hashlib.sha256(owner.read_bytes()).hexdigest()
        if source_sha256 != project.meta['source_sha256']:
            raise ValueError('Game source does not match the retained project source')
        self.manifest = _manifest(self.game_dir)
        self.manifest_sha256 = _digest(self.manifest)
        self.run_id = uuid.uuid4().hex
        self.closed = False
        self._guest_exited = False
        self._run_condition = threading.Condition()
        self._run_lock = threading.Lock()
        self._control_lock = threading.RLock()
        self._run_active = False
        self._run_sent = False
        self._run_stop = None
        self._run_error = None
        self._state_revision = 0
        self._last_frame = None
        self._breakpoints = {}
        self._watches = {}
        self._resource_layers = {}
        self._static_logic_cache = {}
        self._queued_keyboard = 0
        self._keyboard_leases = {}
        self._next_save_slot = 1
        self._launch_alias = None
        self.rpc = None
        executable = Path(executable).expanduser().resolve(strict=True)
        self.metadata = {
            'backend': 'scummvm-agi', 'execution_context': 'agi-vm',
            'replacement_engine': True, 'original_x86_executed': False,
            'native_hooks_available': self.native_hooks_available,
            'game_id': game_id, 'fdisbull_version': __import__('fdisbull').__version__,
            'source_sha256': source_sha256, 'version_sha256': self.version['sha256'],
            'resource_manifest_sha256': self.manifest_sha256,
            'resource_manifest': self.manifest,
            'resource_layers_sha256': '0' * 64,
            'resource_count': len(self.manifest), 'executable': str(executable),
            'scummvm_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
            'game_dir': str(self.game_dir), 'runtime_profile': 'scummvm-agi-agent-v1',
            'state_scope': 'ScummVM native save slots are cycle-level, not exact mid-opcode VM checkpoints',
        }
        try:
            self.rpc = ScummVMRPC(executable, self.game_dir, game_id=game_id,
                                  runtime_parent=project.path.parent,
                                  boot_timeout_ms=boot_timeout_ms, on_spawn=_on_spawn)
            self.metadata.update(game_id=self.rpc.game_id, backend_hello=self.rpc.hello,
                                 pid=self.rpc.process.pid)
            initial = self._read_state()
            self.metadata['initial_position'] = self._position(initial)
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                                   (self.run_id, self.version['id'], stamp(), None,
                                    'stopped', json.dumps(self.metadata)))
            self._event('launch', {'state': 'stopped', 'position': self._position(initial),
                                   'backend': 'scummvm-agi',
                                   'resource_manifest_sha256': self.manifest_sha256})
            project._live_debuggers.append(self)
        except BaseException:
            if self.rpc is not None:
                self.rpc.close()
            raise

    def _call(self, op, params=None, *, timeout_ms=15000, on_sent=None):
        from .operation_budget import RpcAdmissionTimeout
        if self.closed or self.rpc is None:
            raise ScummVMError('ScummVM session is closed')
        if self._run_active and op not in ('run', 'run_until_cycle', 'step'):
            raise ScummVMError('AGI execution is active; pause and confirm its stop first')
        deadline = getattr(self, '_rpc_deadline', None)
        if deadline is not None:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0 or remaining < (getattr(self, '_rpc_admission_ms', None) or 0):
                raise RpcAdmissionTimeout('Shared debugger host-time budget expired before AGI RPC dispatch')
            timeout_ms = min(timeout_ms, getattr(self, '_rpc_timeout_cap_ms', None) or 15000,
                             remaining)
        options = {'timeout_ms': timeout_ms}
        if on_sent is not None:
            options['on_sent'] = on_sent
        return self.rpc.call(op, params, **options)

    def _event(self, operation, evidence):
        if threading.get_ident() == self._project_owner_thread:
            return super()._event(operation, evidence)
        # Project's SQLite connection is owner-thread-bound. A concurrent
        # controller thread records its own event through the same file/store
        # contract without sharing that connection across threads.
        from .target_storage import STORAGE, connect
        db = connect(self.project.path, external=self.project.meta.get('storage') == STORAGE,
                     store=getattr(self.project.db, 'store', None))
        try:
            db.execute('BEGIN IMMEDIATE')
            payload = json.dumps(evidence)
            if hasattr(db, 'store'):
                payload = db.store.put(payload)
            db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                       (self.run_id, stamp(), operation, payload))
            state = evidence.get('state') or evidence.get('session', {}).get('state')
            if state:
                db.execute('UPDATE debug_runs SET state=? WHERE id=?', (state, self.run_id))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_run_sent(self):
        with self._run_condition:
            self._run_sent = True
            self._run_condition.notify_all()

    @contextmanager
    def _native_execution(self):
        with self._run_condition:
            if self._run_active:
                raise ScummVMError('An AGI run or step is already active')
            self._run_active = True
            self._run_sent = False
            self._run_stop = None
            self._run_error = None
        try:
            yield
        except BaseException as error:
            with self._run_condition:
                self._run_error = str(error)
            raise
        finally:
            with self._run_condition:
                self._run_active = False
                self._run_condition.notify_all()

    def _verify_manifest(self):
        if _manifest(self.game_dir) != self.manifest:
            self.close()
            raise ScummVMError('Original AGI game resources changed during this ScummVM run')

    @staticmethod
    def _assert_no_layer_conflict(state):
        if state.get('layer_conflict'):
            raise ScummVMError('AGI loaded-logic layer conflict requires a fresh ScummVM session')

    def _require_paused(self):
        with self._run_condition:
            if self._run_active:
                raise ScummVMError('AGI execution is active; pause and confirm its stop first')

    def _read_state(self):
        reply = self._call('state.get')
        state = reply.get('state')
        if not isinstance(state, dict):
            raise ScummVMError('AGI backend omitted VM state')
        if (type(state.get('room')) is not int or type(state.get('logic')) is not int
                or type(state.get('offset')) is not int or
                not isinstance(state.get('vars'), list) or len(state['vars']) != 256 or
                any(type(value) is not int or not 0 <= value <= 255 for value in state['vars']) or
                not isinstance(state.get('flags'), list) or len(state['flags']) != 256 or
                any(type(value) is not bool for value in state['flags'])):
            raise ScummVMError('AGI backend returned an invalid VM state')
        return state

    @staticmethod
    def _position(state):
        return {'space': 'agi-vm', 'logic': state['logic'], 'offset': state['offset'],
                'offset_origin': 'scummvm-loaded-logic-buffer-byte'}

    def contexts(self):
        return {'run': self.run_id, 'selected': 'agi-vm',
                'contexts': [{'id': 'agi-vm', 'kind': 'bytecode-vm',
                              'trace_phase': 'before-AGI-opcode; completion requires step evidence',
                              'source_address': 'logic number + resource byte offset'}]}

    def context(self, name):
        if name != 'agi-vm':
            raise ValueError('ScummVM backend exposes only the agi-vm context')
        return self

    def engine_state(self):
        self._verify_manifest()
        state = self._read_state()
        self._refresh_resource_layers(state)
        return {**state, 'run': self.run_id, 'backend': 'scummvm-agi',
                'position': self._position(state), 'state_revision': self._state_revision,
                'resource_manifest_sha256': self.manifest_sha256,
                'resource_layers_sha256': self._layer_digest(),
                'layer_conflict': state.get('layer_conflict'),
                'offset_origin': 'scummvm-loaded-logic-buffer-byte',
                'state_origin': 'ScummVM replacement AGI engine, not original DOS CPU'}

    def status(self):
        from .debug_semantics import contract
        with self._run_condition:
            active = self._run_active
        if active:
            return {'run': self.run_id, 'version': self.version['id'],
                    'live': not self.closed, 'state': 'running',
                    'backend': 'scummvm-agi', 'mapping': self.metadata,
                    'native_hooks_available': self.native_hooks_available,
                    'position': None, 'position_scope': 'pending native stop',
                    'semantics': contract('scummvm-agi')}
        if self._guest_exited:
            return {'run': self.run_id, 'version': self.version['id'], 'live': not self.closed,
                    'state': 'exited', 'backend': 'scummvm-agi', 'mapping': self.metadata,
                    'native_hooks_available': self.native_hooks_available}
        self._verify_manifest()
        state = self._read_state()
        self._refresh_resource_layers(state)
        return {'run': self.run_id, 'version': self.version['id'], 'live': not self.closed,
                'state': 'stopped', 'backend': 'scummvm-agi',
                'native_hooks_available': self.native_hooks_available,
                'position': self._position(state), 'guest_ms': state.get('guest_ms'),
                'at_cycle': state.get('at_cycle'), 'at_modal': state.get('at_modal'),
                'modal_revision': state.get('modal_revision'),
                'at_backend_yield': state.get('at_backend_yield'),
                'state_revision': self._state_revision, 'mapping': self.metadata,
                'resource_layers_sha256': self._layer_digest(),
                'layer_conflict': state.get('layer_conflict'),
                'capabilities': self.rpc.capabilities,
                'semantics': contract('scummvm-agi')}

    def write_engine_state(self, kind, index, value, *, expected=None):
        self._verify_manifest()
        if kind not in ('var', 'flag', 'object') or type(index) is not int or not 0 <= index <= 255:
            raise ValueError('Expected AGI var, flag or inventory object index 0..255')
        if kind == 'flag':
            if type(value) is not bool:
                raise ValueError('AGI flag value must be boolean')
        elif type(value) is not int or not 0 <= value <= 255:
            raise ValueError('AGI variable/object location must be a byte')
        before = self._read_state()
        self._assert_no_layer_conflict(before)
        if kind == 'var':
            current = before['vars'][index]
        elif kind == 'flag':
            current = before['flags'][index]
        else:
            found = [item for item in before.get('objects', []) if item.get('id') == index]
            if len(found) != 1:
                raise ValueError('AGI inventory object is absent or ambiguous')
            current = found[0]['location']
        if expected is not None and (type(expected) is not type(current) or expected != current):
            raise ValueError('AGI state precondition differs from current engine value')
        result = self._call('state.set', {'kind': kind, 'index': index, 'value': value})
        self._state_revision += 1
        after = self._read_state()
        observed = (after['vars'][index] if kind == 'var' else
                    after['flags'][index] if kind == 'flag' else
                    next((item['location'] for item in after.get('objects', [])
                          if item.get('id') == index), None))
        if type(observed) is not type(value) or observed != value:
            self.close()
            raise ScummVMError('AGI state write was not confirmed at the next pause')
        evidence = {'run': self.run_id, 'kind': kind, 'index': index,
                    'before': current, 'after': observed, 'backend': result,
                    'state_revision': self._state_revision}
        self._event('write-engine-state', evidence)
        return evidence

    engine_set = write_engine_state

    def run(self, *, max_instructions=1000000, timeout_ms=10000, guest_ms=None,
            fast_forward=False, stop_on_hook=False, until_cycle=False):
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another AGI execution is active')
        try:
            return self._run_budgeted(max_instructions=max_instructions, timeout_ms=timeout_ms,
                                      guest_ms=guest_ms, fast_forward=fast_forward,
                                      stop_on_hook=stop_on_hook, until_cycle=until_cycle)
        finally:
            self._run_lock.release()

    @rpc_budget
    def _run_budgeted(self, *, max_instructions=1000000, timeout_ms=10000, guest_ms=None,
                      fast_forward=False, stop_on_hook=False, until_cycle=False):
        self._verify_manifest()
        bounded(max_instructions, 'max_instructions', 1, 1000000)
        bounded(timeout_ms, 'timeout_ms', 1, 600000)
        if guest_ms is not None:
            bounded(guest_ms, 'guest_ms', 1, 3600000)
            if not self.rpc.capabilities.get('virtual_time'):
                raise ScummVMError('Backend does not qualify virtual guest-time runs')
        if any(type(option) is not bool for option in (fast_forward, stop_on_hook, until_cycle)):
            raise ValueError('fast_forward, stop_on_hook and until_cycle must be boolean')
        if stop_on_hook:
            raise ValueError('AGI native DOS hooks are unavailable')
        before = self._read_state()
        self._assert_no_layer_conflict(before)
        started = time.monotonic()
        remaining = int((self._rpc_deadline - time.monotonic()) * 1000)
        remaining = min(remaining, getattr(self, '_rpc_timeout_cap_ms', None) or remaining)
        if remaining < 100:
            raise TimeoutError('AGI run host-time budget expired before dispatch')
        native_host_ms = max(1, remaining - min(500, max(50, remaining // 10)))
        params = {'max_instructions': max_instructions, 'max_ms': native_host_ms}
        if guest_ms is not None:
            params['max_guest_ms'] = guest_ms
        with self._native_execution():
            reply = self._call('run_until_cycle' if until_cycle else 'run', params,
                               timeout_ms=remaining, on_sent=self._mark_run_sent)
            stop = reply.get('stop')
            if not isinstance(stop, dict) or not isinstance(stop.get('reason'), str):
                self.close()
                raise ScummVMError('AGI run ended without a structured stop')
            with self._run_condition:
                self._run_stop = stop
        self._verify_manifest()
        self._state_revision += 1
        self._queued_keyboard = 0
        after = self._read_state() if stop['reason'] != 'quit' else None
        if after is not None:
            self._refresh_resource_layers(after)
        self._guest_exited = stop['reason'] == 'quit'
        guest_elapsed = None
        if after is not None and type(before.get('guest_ms')) is int and type(after.get('guest_ms')) is int:
            guest_elapsed = after['guest_ms'] - before['guest_ms']
            if guest_elapsed < 0:
                self.close()
                raise ScummVMError('AGI virtual clock moved backwards')
        if guest_ms is not None and guest_elapsed is None:
            self.close()
            raise ScummVMError('Backend did not report qualified virtual elapsed time')
        if stop['reason'] == 'guest_budget' and guest_ms is None:
            self.close()
            raise ScummVMError('Backend reported a virtual-time stop without a guest-time request')
        outcome = {'guest_budget': 'guest_time', 'host_timeout': 'timeout',
                   'quit': 'exited'}.get(stop['reason'], stop['reason'])
        evidence = {'run': self.run_id, 'backend': 'scummvm-agi', 'outcome': outcome,
                    'stop': {'context': 'agi-vm', 'trigger': outcome,
                             'position': {'space': 'agi-vm', 'logic': stop.get('logic'),
                                          'offset': stop.get('offset')},
                             'instruction_completed': None},
                    'executed': stop.get('instructions'), 'guest_elapsed_ms': guest_elapsed,
                    'host_elapsed_ms': round((time.monotonic() - started) * 1000, 3),
                    'requested_guest_ms': guest_ms, 'requested_instructions': max_instructions,
                    'requested_cycle_boundary': until_cycle,
                    'fast_forward_requested': fast_forward,
                    'clock_mode': 'deterministic-ScummVM-virtual-clock',
                    'hook_hits': [], 'native_hooks_available': False,
                    'at_modal': stop.get('at_modal'),
                    'modal_revision': stop.get('modal_revision'),
                    'layer_conflict': stop.get('layer_conflict'),
                    'state_revision': self._state_revision, 'native_stop': stop,
                    'state': 'exited' if self._guest_exited else 'stopped'}
        self._event('run', evidence)
        return evidence

    def run_until_cycle(self, *, max_instructions=100000, timeout_ms=10000):
        """Advance explicitly to the next AGI cycle boundary for native saves."""
        return self.run(max_instructions=max_instructions, timeout_ms=timeout_ms,
                        until_cycle=True)

    def pause(self, *, timeout_ms=5000):
        """Request an in-flight AGI run to stop, with explicit ack-only scope."""
        bounded(timeout_ms, 'timeout_ms', 1, 600000)
        deadline = time.monotonic() + timeout_ms / 1000
        with self._run_condition:
            while self._run_active and not self._run_sent:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    break
                self._run_condition.wait(remaining_seconds)
            active = self._run_active
            sent = self._run_sent
            stop = self._run_stop
            error = self._run_error
        if not active:
            if error is not None:
                raise ScummVMError('AGI run ended before pause could confirm a stop: ' + error)
            status = self.status()
            return {'run': self.run_id, 'acknowledged': False,
                    'already_stopped': status['state'] == 'stopped',
                    'confirmed_stopped': status['state'] == 'stopped',
                    'state': status['state'], 'stop': stop}
        if not sent:
            return {'run': self.run_id, 'acknowledged': False,
                    'confirmed_stopped': False, 'state': 'running', 'stop': None,
                    'reason': 'run-request-not-yet-sent'}
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            return {'run': self.run_id, 'acknowledged': False,
                    'confirmed_stopped': False, 'state': 'running', 'stop': None,
                    'reason': 'pause-host-budget-expired'}
        acknowledgement = self.rpc.call('pause', timeout_ms=remaining)
        with self._run_condition:
            while self._run_active:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    break
                self._run_condition.wait(remaining_seconds)
            active = self._run_active
            stop = self._run_stop
            error = self._run_error
        if error is not None:
            raise ScummVMError('AGI run ended without a confirmed stop after pause: ' + error)
        confirmed = not active and isinstance(stop, dict)
        result = {'run': self.run_id, 'acknowledged': True,
                  'native_acknowledgement': acknowledgement,
                  'confirmed_stopped': confirmed,
                  'state': 'running' if active else 'exited' if stop and stop.get('reason') == 'quit' else 'stopped',
                  'stop': stop if confirmed else None}
        self._event('pause', result)
        return result

    def resume(self, *, max_instructions=1000000, timeout_ms=10000, guest_ms=None,
               fast_forward=False):
        """Resume only under a fresh finite instruction, host, and optional guest budget."""
        return self.run(max_instructions=max_instructions, timeout_ms=timeout_ms,
                        guest_ms=guest_ms, fast_forward=fast_forward)

    def step(self, count=1, *, timeout_ms=10000):
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another AGI execution is active')
        try:
            return self._step_budgeted(count=count, timeout_ms=timeout_ms)
        finally:
            self._run_lock.release()

    @rpc_budget
    def _step_budgeted(self, count=1, *, timeout_ms=10000):
        self._verify_manifest()
        bounded(count, 'count', 1, 10000)
        bounded(timeout_ms, 'timeout_ms', 1, 600000)
        records = []
        deadline = time.monotonic() + timeout_ms / 1000
        for _ in range(count):
            before = self._read_state()
            self._assert_no_layer_conflict(before)
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            if remaining <= 1 and time.monotonic() >= deadline:
                break
            shared_deadline = getattr(self, '_rpc_deadline', None)
            if shared_deadline is not None:
                remaining = min(remaining, max(1, int((shared_deadline - time.monotonic()) * 1000)))
            remaining = min(remaining, getattr(self, '_rpc_timeout_cap_ms', None) or remaining)
            if remaining < 100:
                break
            native_host_ms = max(1, remaining - min(500, max(50, remaining // 10)))
            with self._native_execution():
                reply = self._call('step', {'max_ms': native_host_ms}, timeout_ms=remaining,
                                   on_sent=self._mark_run_sent)
                stop = reply.get('stop')
                if not isinstance(stop, dict) or not isinstance(stop.get('reason'), str):
                    self.close()
                    raise ScummVMError('AGI step ended without a structured stop')
                with self._run_condition:
                    self._run_stop = stop
            self._state_revision += 1
            self._queued_keyboard = 0
            records.append({'before': self._position(before), 'stop': stop,
                            'completed_opcode_count': stop.get('instructions'),
                            'some_opcode_completed': stop.get('instructions', 0) > 0,
                            'before_position_instruction_completed': None})
            if stop['reason'] not in ('step', 'budget'):
                if stop['reason'] == 'quit':
                    self._guest_exited = True
                break
        result = {'run': self.run_id, 'backend': 'scummvm-agi', 'steps': records,
                  'completed': len(records) == count and
                               all(record['completed_opcode_count'] == 1 and
                                   record['stop']['reason'] in ('step', 'budget')
                                   for record in records),
                  'position': records[-1]['stop'] if records else self._position(self._read_state()),
                  'state_revision': self._state_revision}
        self._verify_manifest()
        self._event('step', result)
        return result

    def _frame(self):
        self._verify_manifest()
        state = self._read_state()
        if state.get('layer_conflict'):
            raise ScummVMError('AGI loaded-logic layer conflict; frame cannot qualify an existing scene')
        self._refresh_resource_layers(state)
        reply = self._call('frame.get')
        width, height = reply.get('width'), reply.get('height')
        if (type(width) is not int or type(height) is not int or
                not 1 <= width <= 4096 or not 1 <= height <= 4096 or
                width * height > 2_000_000 or reply.get('format') != 'rgb24' or
                type(reply.get('revision')) is not int or reply['revision'] < 0):
            raise ScummVMError('AGI backend returned invalid committed frame metadata')
        try:
            pixels = base64.b64decode(reply['data_base64'], validate=True)
        except (KeyError, ValueError) as error:
            raise ScummVMError('AGI backend returned malformed RGB frame') from error
        if len(pixels) != width * height * 3:
            raise ScummVMError('AGI backend returned incomplete RGB frame')
        self._verify_manifest()
        pixel_sha256 = hashlib.sha256(pixels).hexdigest()
        frame_id = int(_digest([self._state_revision, reply['revision'], pixel_sha256])[:13], 16)
        mode_id = int(_digest([width, height, 'rgb24'])[:13], 16)
        metadata = {'run': self.run_id, 'version': self.version['id'],
                    'backend': 'scummvm-agi',
                    'resource_manifest_sha256': self.manifest_sha256,
                    'resource_layers_sha256': self._layer_digest(),
                    'frame_id': frame_id, 'mode_id': mode_id,
                    'state_revision': self._state_revision,
                    'frame_commit_revision': reply['revision'],
                    'frame_guest_ms': reply.get('guest_ms'),
                    'frame_sha256': pixel_sha256,
                    'width': width, 'height': height, 'source_bpp': 24,
                    'double_width': False, 'double_height': False,
                    'frame_origin': 'last committed ScummVM display at AGI pause'}
        self._last_frame = (metadata, pixels)
        return metadata, pixels

    def frame_probe(self, points):
        if not isinstance(points, list) or len(points) > 4096:
            raise ValueError('Frame probe requires a list of at most 4096 points')
        metadata, pixels = self._frame()
        samples = []
        for point in points:
            if (not isinstance(point, (list, tuple)) or len(point) != 2 or
                    type(point[0]) is not int or type(point[1]) is not int):
                raise ValueError('Expected integer [x,y] frame point')
            x, y = point
            if not 0 <= x < metadata['width'] or not 0 <= y < metadata['height']:
                raise ValueError('Frame point lies outside the committed display')
            index = (y * metadata['width'] + x) * 3
            samples.append({'x': x, 'y': y, 'rgb': list(pixels[index:index+3])})
        result = {**metadata, 'format': 'rgb-samples', 'samples': samples}
        self._event('frame-probe', result)
        return result

    def screenshot(self, name='screenshot.png', *, grid=False, grid_step=32, hooks=True):
        from PIL import Image
        from .screenshot_grid import validate_step
        _file_name(name)
        if type(grid) is not bool or type(hooks) is not bool:
            raise ValueError('grid and hooks must be boolean')
        validate_step(grid_step)
        metadata, pixels = self._frame()
        buffer = io.BytesIO()
        Image.frombytes('RGB', (metadata['width'], metadata['height']), pixels).save(buffer, format='PNG')
        data = buffer.getvalue()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ScummVMError('PNG conversion of AGI display failed')
        metadata = {**metadata, 'sha256': hashlib.sha256(data).hexdigest(),
                    'screenshot_hooks': {'available': False, 'requested': hooks}}
        if not grid:
            return self._artifact(name, 'screenshot', data, metadata)
        original = self._artifact(name[:248] + '.raw.png', 'screenshot', data, metadata)
        return self.project.debug_grid(original['artifact'], name=name, step=grid_step)

    def keyboard_press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(key=key, modifiers=modifiers, hold_ms=hold_ms, gap_ms=gap_ms)
        if modifiers:
            raise ValueError('ScummVM AGI input does not provide key modifiers')
        key = 'escape' if key == 'esc' else key
        timed = 'input.virtual_timing' in self.rpc.capabilities['features']
        if timed:
            params = {'kind': 'key', 'key': key, 'action': 'press',
                      'hold_ms': hold_ms, 'gap_ms': gap_ms}
        elif key in ('enter', 'left', 'right', 'up', 'down', 'escape', 'backspace', 'space'):
            params = {'kind': 'key', 'key': key}
        elif len(key) == 1 and key.isascii() and key.isprintable():
            params = {'kind': 'text', 'text': key}
        else:
            raise ValueError('ScummVM AGI backend cannot queue this physical key')
        reply = self._call('input', params)
        result = self._input_evidence('keyboard.press', params, reply, hold_ms, gap_ms)
        return result

    def keyboard_type(self, text, *, hold_ms=40, gap_ms=40):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(text=text, hold_ms=hold_ms, gap_ms=gap_ms)
        params = {'kind': 'text', 'text': text}
        if 'input.virtual_timing' in self.rpc.capabilities['features']:
            params.update(hold_ms=hold_ms, gap_ms=gap_ms)
        reply = self._call('input', params)
        return self._input_evidence('keyboard.type', params, reply, hold_ms, gap_ms)

    def _input_evidence(self, name, params, reply, hold_ms, gap_ms):
        if type(reply.get('queued')) is not int or reply['queued'] < 1:
            self.close()
            raise ScummVMError('AGI backend did not confirm queued input events')
        self._queued_keyboard += reply['queued']
        self._state_revision += 1
        result = {'run': self.run_id, 'backend': 'scummvm-agi',
                  'input': params, 'queued': reply['queued'], 'consumed': False,
                  'hold_ms_requested': hold_ms, 'gap_ms_requested': gap_ms,
                  'timing_applied': 'input.virtual_timing' in self.rpc.capabilities['features'],
                  'queue_status': {key: reply.get(key) for key in
                                   ('pending','guest_ms','queue_tail_guest_ms','next_due_guest_ms')
                                   if key in reply},
                  'state_revision': self._state_revision}
        self._event(name, result)
        return result

    def keyboard_state(self):
        if 'input.status' in self.rpc.capabilities['features']:
            reply = self._call('input.status')
            if (type(reply.get('pending')) is not int or reply['pending'] < 0 or
                    not isinstance(reply.get('held_keycodes'), list) or
                    not isinstance(reply.get('leases'), list)):
                raise ScummVMError('AGI backend returned invalid input queue status')
            native_ids = {entry.get('lease') for entry in reply['leases']
                          if isinstance(entry, dict)}
            for identifier in list(self._keyboard_leases):
                if identifier not in native_ids:
                    del self._keyboard_leases[identifier]
            return {'run': self.run_id, 'backend': 'scummvm-agi',
                    'keyboard': {'pending_events': reply['pending'],
                                 'owned_keys': [entry['key'] for entry in self._keyboard_leases.values()],
                                 'held_keycodes': reply['held_keycodes'],
                                 'leases': reply['leases'],
                                 'queue_tail_guest_ms': reply.get('queue_tail_guest_ms'),
                                 'next_due_guest_ms': reply.get('next_due_guest_ms'),
                                 'guest_ms': reply.get('guest_ms'),
                                 'dispatch_complete': reply['pending'] == 0,
                                 'game_consumption_verified': False}}
        return {'run': self.run_id, 'keyboard':
                {'queued_events_since_run': self._queued_keyboard,
                 'pending_events': None, 'owned_keys': [],
                 'consumption_verified': False}, 'backend': 'scummvm-agi'}

    def _assert_input_idle(self, operation):
        """Native save files omit the bridge's queued and held input state."""
        if 'input.status' not in self.rpc.capabilities['features']:
            raise ValueError('ScummVM native state requires verified input.status support')
        keyboard = self.keyboard_state()['keyboard']
        if (keyboard['pending_events'] or keyboard['leases'] or
                keyboard['held_keycodes'] or keyboard['owned_keys']):
            raise ValueError(f'ScummVM native {operation} requires an empty input queue and no held keys')
        return keyboard

    def keyboard_key_down(self, key):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(key=key)
        if 'input.key_leases' not in self.rpc.capabilities['features']:
            raise ValueError('ScummVM AGI backend does not expose held-key leases')
        if any(entry['key'] == key for entry in self._keyboard_leases.values()):
            raise ValueError('AGI key already has an owned live lease')
        reply = self._call('input', {'kind':'key','key':key,'action':'down','gap_ms':0})
        lease = reply.get('lease')
        if type(lease) is not int or lease < 1 or reply.get('queued') != 1:
            self.close()
            raise ScummVMError('AGI backend did not confirm owned key-down lease')
        self._keyboard_leases[lease] = {'key':key,'release_scheduled':False}
        self._state_revision += 1
        result = {'run':self.run_id,'key':key,'lease':lease,'queued':1,
                  'down_delivered':False,'state_revision':self._state_revision}
        self._event('keyboard.key-down', result)
        return result

    def keyboard_key_up(self, lease):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        if type(lease) is not int or lease not in self._keyboard_leases or self._keyboard_leases[lease]['release_scheduled']:
            raise ValueError('Unknown or already releasing AGI key lease')
        reply = self._call('input', {'kind':'key','action':'up','lease':lease,'gap_ms':0})
        if reply.get('lease') != lease or reply.get('queued') != 1:
            self.close()
            raise ScummVMError('AGI backend did not confirm owned key-up event')
        self._keyboard_leases[lease]['release_scheduled'] = True
        self._state_revision += 1
        result = {'run':self.run_id,'key':self._keyboard_leases[lease]['key'],
                  'lease':lease,'queued':1,'release_delivered':False,
                  'state_revision':self._state_revision}
        self._event('keyboard.key-up', result)
        return result

    def click(self, x, y, *, button='left', hold_ms=80, mode_id=None, frame_id=None):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        bounded(x, 'x', 0, 4095)
        bounded(y, 'y', 0, 4095)
        bounded(hold_ms, 'hold_ms', 1, 1000)
        if button not in ('left', 'right'):
            raise ValueError('ScummVM AGI backend supports left or right mouse buttons')
        frame, _ = self._frame()
        if x >= frame['width'] or y >= frame['height']:
            raise ValueError('Click is outside the committed frame')
        if mode_id is not None and mode_id != frame['mode_id']:
            raise ValueError('Click mode differs from the current committed frame')
        if frame_id is not None and frame_id != frame['frame_id']:
            raise ValueError('Click frame differs from the current committed frame')
        timed = 'input.virtual_timing' in self.rpc.capabilities['features']
        if timed:
            replies = [self._call('input', {'kind':'mouse','action':'click',
                                            'button':button,'x':x,'y':y,
                                            'hold_ms':hold_ms,'gap_ms':0})]
        else:
            replies = []
            try:
                for action in ('move', 'down', 'up'):
                    params = {'kind': 'mouse', 'action': action, 'button': button, 'x': x, 'y': y}
                    replies.append(self._call('input', params))
            except BaseException:
                # A submitted prefix must not be reissued as a second click.
                if replies:
                    self._event('click-partial', {'run': self.run_id, 'x': x, 'y': y,
                                                   'submitted_actions': ('move', 'down', 'up')[:len(replies)],
                                                   'complete': False})
                    self.close()
                raise
        if any(type(reply.get('queued')) is not int or reply['queued'] < 1 for reply in replies):
            self.close()
            raise ScummVMError('AGI backend did not confirm the complete mouse event sequence')
        self._state_revision += 1
        result = {'run': self.run_id, 'backend': 'scummvm-agi', 'x': x, 'y': y,
                  'button': button, 'queued': sum(reply['queued'] for reply in replies),
                  'consumed': False, 'hold_ms_requested': hold_ms,
                  'timing_applied': timed, 'mode_id': frame['mode_id'],
                  'frame_id': frame['frame_id'], 'state_revision': self._state_revision}
        self._event('click', result)
        return result

    @_control_operation
    def breakpoint(self, address, *, cs=None, access='x', length=1, view='static'):
        if (not isinstance(address, dict) or set(address) != {'logic', 'offset'} or
                type(address['logic']) is not int or not 0 <= address['logic'] <= 255 or
                type(address['offset']) is not int or not 0 <= address['offset'] <= 65535):
            raise ValueError('AGI breakpoint address must be {logic:int, offset:int}')
        if cs is not None or access != 'x' or length != 1 or view not in ('static', 'execute'):
            raise ValueError('AGI breakpoints address one VM opcode; native CPU options do not apply')
        self._call('break.add', address)
        identifier = next((key for key, point in self._breakpoints.items()
                           if point == address), None)
        if identifier is None:
            identifier = uuid.uuid4().hex
            self._breakpoints[identifier] = dict(address)
        result = {'run': self.run_id, 'breakpoint_id': identifier,
                  'address': {'space': 'agi-vm', **address},
                  'verification_view': 'agi-vm', 'bytes_verified': False,
                  'backend': 'scummvm-agi'}
        self._event('breakpoint', result)
        return result

    @_control_operation
    def watchpoint(self, kind, index, *, access='w'):
        if kind not in ('var', 'flag', 'object') or type(index) is not int or not 0 <= index <= 255:
            raise ValueError('AGI watchpoint requires var, flag or object index 0..255')
        if access not in ('r', 'w', 'rw'):
            raise ValueError('AGI watch access must be r, w or rw')
        params = {'kind': kind, 'index': index, 'access': access}
        self._call('watch.add', params)
        identifier = next((key for key, point in self._watches.items()
                           if point == params), None)
        if identifier is None:
            identifier = uuid.uuid4().hex
            self._watches[identifier] = params
        result = {'run': self.run_id, 'watchpoint_id': identifier,
                  'kind': kind, 'index': index, 'access': access, 'backend': 'scummvm-agi',
                  'stop_scope': 'AGI engine mutation safe point'}
        self._event('watchpoint', result)
        return result

    @_control_operation
    def delete_breakpoint(self, breakpoint_id):
        if breakpoint_id in self._breakpoints:
            point = self._breakpoints[breakpoint_id]
            self._call('break.remove', point)
            del self._breakpoints[breakpoint_id]
            kind = 'breakpoint'
        elif breakpoint_id in self._watches:
            point = self._watches[breakpoint_id]
            self._call('watch.remove', point)
            del self._watches[breakpoint_id]
            kind = 'watchpoint'
        else:
            raise ValueError('Unknown AGI breakpoint or watchpoint ID')
        result = {'run': self.run_id, 'deleted': breakpoint_id, 'kind': kind,
                  'backend': 'scummvm-agi'}
        self._event('delete-breakpoint', result)
        return result

    def delete_watchpoint(self, watchpoint_id):
        return self.delete_breakpoint(watchpoint_id)

    def resource_info(self, kind, number):
        self._verify_manifest()
        from .agi_picture import extract_v2_resource
        directories = {'logic': 'LOGDIR', 'picture': 'PICDIR',
                       'view': 'VIEWDIR', 'sound': 'SNDDIR'}
        if kind not in directories or type(number) is not int or not 0 <= number <= 255:
            raise ValueError('Expected AGI v2 resource kind and number 0..255')
        candidates = [path for path in self.game_dir.iterdir()
                      if path.name.lower() == directories[kind].lower()]
        if len(candidates) != 1 or candidates[0].is_symlink():
            raise ValueError('Missing or ambiguous AGI resource directory')
        resource = extract_v2_resource(candidates[0], self.game_dir, number)
        self._verify_manifest()
        return {'kind': kind, 'number': number, 'format': 'agi-v2-resource',
                'volume': resource['volume'], 'volume_offset': resource['offset'],
                'source_file': f"VOL.{resource['volume']}",
                'payload_file_offset': resource['offset'] + 5,
                'length': resource['length'], 'sha256': resource['sha256'],
                'resource_manifest_sha256': self.manifest_sha256,
                'qualification': 'Static original game resource; execution observed separately in ScummVM'}

    def resource(self, logic, offset=0, length=16):
        """Read current loaded VM bytes and their pre-edit baseline."""
        self._verify_manifest()
        bounded(logic, 'logic', 0, 255)
        bounded(offset, 'offset', 0, 65535)
        bounded(length, 'length', 0, 4096)
        reply = self._call('logic.read', {'logic': logic, 'offset': offset, 'length': length})
        if (reply.get('scope') != 'loaded_logic_memory' or
                type(reply.get('generation')) is not int or
                type(reply.get('size')) is not int or
                not isinstance(reply.get('original_hex'), str) or
                not isinstance(reply.get('current_hex'), str) or
                len(reply['original_hex']) != length * 2 or
                len(reply['current_hex']) != length * 2):
            raise ScummVMError('AGI backend returned invalid loaded logic bytes')
        try:
            original = bytes.fromhex(reply['original_hex'])
            current = bytes.fromhex(reply['current_hex'])
        except ValueError as error:
            raise ScummVMError('AGI backend returned nonhex logic bytes') from error
        static = None
        try:
            from .agi_picture import extract_v2_resource
            info = self.resource_info('logic', logic)
            directory = next(path for path in self.game_dir.iterdir() if path.name.lower() == 'logdir')
            payload = extract_v2_resource(directory, self.game_dir, logic)['payload']
            if offset + length <= len(payload) and payload[offset:offset + length] == original:
                static = {'resource': info, 'source_file_offset': info['payload_file_offset'] + offset,
                          'bytes_verified': True}
        except (ValueError, OSError, StopIteration):
            pass
        self._verify_manifest()
        return {**reply, 'backend': 'scummvm-agi', 'run': self.run_id,
                'resource_manifest_sha256': self.manifest_sha256,
                'disk_source': static, 'original_sha256': hashlib.sha256(original).hexdigest(),
                'current_sha256': hashlib.sha256(current).hexdigest(),
                'qualification': 'Paused ScummVM loaded AGI logic memory; disk source is separately verified'}

    def _loaded_logic_hashes(self, logic):
        head = self.resource(logic, 0, 0)
        size = head['size']
        if not 0 < size <= 65536:
            raise ScummVMError('Loaded AGI logic size exceeds bounded resource inspection')
        original = hashlib.sha256()
        current = hashlib.sha256()
        for offset in range(0, size, 4096):
            record = self.resource(logic, offset, min(4096, size - offset))
            if record['size'] != size or record['generation'] != head['generation']:
                raise ScummVMError('Loaded AGI logic changed during paused resource inspection')
            original.update(bytes.fromhex(record['original_hex']))
            current.update(bytes.fromhex(record['current_hex']))
        return {'logic': logic, 'generation': head['generation'],
                'original_sha256': original.hexdigest(), 'current_sha256': current.hexdigest(),
                'size': size}

    def _layer_digest(self):
        return _digest([self._resource_layers[key] for key in sorted(self._resource_layers)]) \
            if self._resource_layers else '0' * 64

    def _refresh_resource_layers(self, state=None):
        if not self._resource_layers:
            return
        if state is None:
            state = self._read_state()
        if state.get('layer_conflict'):
            return
        active = {entry.get('logic') for entry in state.get('logic_patches', [])
                  if isinstance(entry, dict) and entry.get('active', True)}
        before = self._layer_digest()
        for logic in list(self._resource_layers):
            if logic not in active:
                del self._resource_layers[logic]
                continue
            hashes = self._loaded_logic_hashes(logic)
            if hashes['current_sha256'] == hashes['original_sha256']:
                del self._resource_layers[logic]
            else:
                self._resource_layers[logic] = hashes
        if self._layer_digest() != before:
            self._state_revision += 1

    def patch_resource(self, logic, offset, expected_hex, data_hex):
        self._assert_no_layer_conflict(self._read_state())
        bounded(logic, 'logic', 0, 255)
        bounded(offset, 'offset', 0, 65535)
        try:
            expected = bytes.fromhex(expected_hex)
            replacement = bytes.fromhex(data_hex)
        except (TypeError, ValueError) as error:
            raise ValueError('AGI patch expected_hex/data_hex must be even-length hex') from error
        if not 1 <= len(expected) <= 4096 or len(expected) != len(replacement):
            raise ValueError('AGI resource patch requires equal 1..4096-byte sequences')
        if _manifest(self.game_dir) != self.manifest:
            raise ValueError('Game resource manifest changed before loaded-logic patch')
        before = self.resource(logic, offset, len(expected))
        if before['current_hex'].lower() != expected_hex.lower():
            raise ValueError('Loaded AGI resource bytes differ from expected_hex')
        reply = self._call('logic.patch', {'logic': logic, 'offset': offset,
                                           'expected_hex': expected_hex.lower(),
                                           'data_hex': data_hex.lower()})
        after = self.resource(logic, offset, len(replacement))
        if after['current_hex'].lower() != data_hex.lower() or after['generation'] <= before['generation']:
            self.close()
            raise ScummVMError('AGI loaded-logic patch was not confirmed')
        hashes = self._loaded_logic_hashes(logic)
        if hashes['current_sha256'] == hashes['original_sha256']:
            self._resource_layers.pop(logic, None)
        else:
            self._resource_layers[logic] = hashes
        self._state_revision += 1
        if _manifest(self.game_dir) != self.manifest:
            self.close()
            raise ScummVMError('Original game files changed during in-memory logic patch')
        result = {'run': self.run_id, 'logic': logic, 'offset': offset,
                  'before': before, 'after': after, 'native_result': reply,
                  'resource_layers_sha256': self._layer_digest(),
                  'resource_manifest_sha256': self.manifest_sha256,
                  'state_revision': self._state_revision,
                  'scope': 'loaded_logic_memory', 'original_game_files_changed': False,
                  'native_save_persists_patch': False}
        self._event('patch-resource', result)
        return result

    def restore_resource(self, logic, *, expected_fnv1a64=None):
        """Restore all retained original bytes for one still-loaded logic."""
        bounded(logic, 'logic', 0, 255)
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        before = self.resource(logic, 0, 0)
        current = before.get('current_fnv1a64')
        if not isinstance(current, str) or len(current) != 16:
            raise ScummVMError('AGI backend did not provide a full loaded-logic hash')
        if expected_fnv1a64 is not None and expected_fnv1a64 != current:
            raise ValueError('Loaded AGI logic hash differs from expected_fnv1a64')
        reply = self._call('logic.restore', {'logic': logic, 'expected_fnv1a64': current})
        if reply.get('restored') is not True:
            self.close()
            raise ScummVMError('AGI backend did not confirm full loaded-logic restoration')
        hashes = self._loaded_logic_hashes(logic)
        if hashes['current_sha256'] != hashes['original_sha256']:
            self.close()
            raise ScummVMError('AGI loaded logic still differs after full restoration')
        self._resource_layers.pop(logic, None)
        self._state_revision += 1
        self._verify_manifest()
        result = {'run': self.run_id, 'logic': logic, 'before': before,
                  'native_result': reply, 'resource_layers_sha256': self._layer_digest(),
                  'resource_manifest_sha256': self.manifest_sha256,
                  'state_revision': self._state_revision,
                  'scope': 'loaded_logic_memory', 'original_game_files_changed': False}
        self._event('restore-resource', result)
        return result

    def code(self, address, *, cs=None, length=16):
        self._verify_manifest()
        if cs is not None or not isinstance(address, dict) or set(address) != {'logic', 'offset'}:
            raise ValueError('AGI code address must be {logic:int, offset:int}')
        bounded(length, 'length', 1, 65536)
        logic, offset = address['logic'], address['offset']
        info = self.resource_info('logic', logic)
        from .agi_picture import extract_v2_resource
        directory = next(path for path in self.game_dir.iterdir() if path.name.lower() == 'logdir')
        payload = extract_v2_resource(directory, self.game_dir, logic)['payload']
        if len(payload) < 2:
            raise ValueError('AGI logic resource is truncated')
        code_length = int.from_bytes(payload[:2], 'little')
        if code_length > len(payload) - 2 or type(offset) is not int or not 2 <= offset < code_length + 2:
            raise ValueError('AGI code offset lies outside logic bytecode')
        data = payload[offset:min(code_length + 2, offset + length)]
        self._verify_manifest()
        return {'address': {'space': 'agi-resource-code', 'logic': logic, 'offset': offset,
                            'offset_origin': 'scummvm-loaded-logic-buffer-byte'},
                'hex': data.hex(), 'length': len(data), 'logic_resource': info,
                'source_file_offset': info['payload_file_offset'] + offset,
                'decoded': False, 'execution_bytes_verified': False,
                'qualification': 'Original AGI logic bytecode slice, not ScummVM internal code memory'}

    def _static_opcode_source(self, logic, offset, opcode=None):
        try:
            from .agi_picture import extract_v2_resource
            if logic not in self._static_logic_cache:
                info = self.resource_info('logic', logic)
                directory = next(path for path in self.game_dir.iterdir() if path.name.lower() == 'logdir')
                payload = extract_v2_resource(directory, self.game_dir, logic)['payload']
                self._static_logic_cache[logic] = (info, payload)
            info, payload = self._static_logic_cache[logic]
            if not 0 <= offset < len(payload):
                raise ValueError('VM offset outside original logic resource payload')
            original = payload[offset]
            return {'source_file': info['source_file'],
                    'source_file_offset': info['payload_file_offset'] + offset,
                    'resource_sha256': info['sha256'],
                    'original_hex': f'{original:02x}',
                    'opcode_matches_original': None if opcode is None else opcode == original,
                    'scope': 'validated AGI v2 original disk resource'}
        except (ValueError, OSError, StopIteration) as error:
            return {'scope': 'unmapped-original-source', 'reason': str(error)}

    def registers(self):
        raise ValueError('ScummVM AGI VM exposes engine_state, not original x86 registers')

    def memory(self, address, *, cs=None, length=16):
        raise ValueError('ScummVM AGI VM exposes typed state/resources, not original DOS memory')

    def trace(self, name='trace.json', *, count=512, timeout_ms=10000, fast_forward=False):
        self._verify_manifest()
        _file_name(name)
        bounded(count, 'count', 1, 2048)
        bounded(timeout_ms, 'timeout_ms', 1, 600000)
        if type(fast_forward) is not bool:
            raise ValueError('fast_forward must be boolean')
        started = time.monotonic()
        if 'trace.start' in self.rpc.capabilities['features']:
            self._call('trace.clear')
            self._call('trace.start')
            try:
                stop = self.run(max_instructions=count, timeout_ms=timeout_ms,
                                fast_forward=fast_forward)
            finally:
                self._call('trace.stop')
            native = self._call('trace.get')
            if not isinstance(native.get('entries'), list):
                raise ScummVMError('AGI backend returned invalid opcode trace')
            events = []
            for entry in native['entries']:
                if (not isinstance(entry, dict) or
                        any(type(entry.get(key)) is not int for key in ('logic', 'offset', 'opcode', 'guest_ms'))):
                    raise ScummVMError('AGI backend returned malformed opcode trace entry')
                events.append({**entry,
                               'position': {'space': 'agi-vm', 'logic': entry['logic'],
                                            'offset': entry['offset'],
                                            'offset_origin': 'scummvm-loaded-logic-buffer-byte'},
                               'original_source': self._static_opcode_source(
                                   entry['logic'], entry['offset'], entry['opcode']),
                               'execution_origin': 'ScummVM AGI interpreter'})
            # The bridge flags a full ring as truncated at exactly 2048 even
            # when the cleared, bounded run has not dropped an entry.
            complete = (len(events) == count and stop.get('executed') == count and
                        (not native.get('truncated') or count == 2048))
            stop_reason = stop['outcome']
        else:
            result = self.step(count, timeout_ms=timeout_ms)
            events = [{**record, 'original_source': self._static_opcode_source(
                record['before']['logic'], record['before']['offset'])}
                for record in result['steps']]
            complete = result['completed']
            stop_reason = result['steps'][-1]['stop']['reason'] if result['steps'] else 'no-step'
        report = {'run': self.run_id, 'version': self.version['id'],
                  'backend': 'scummvm-agi', 'resource_manifest_sha256': self.manifest_sha256,
                  'resource_layers_sha256': self._layer_digest(),
                  'events': events, 'requested_count': count,
                  'complete': complete, 'stop_reason': stop_reason,
                  'native_trace_capacity_flag': native.get('truncated') if 'native' in locals() else None,
                  'host_elapsed_ms': round((time.monotonic() - started) * 1000, 3),
                  'observation_contract': 'AGI opcode start positions and executed-opcode counts; nested caller completion unknown; no original x86 address'}
        self._verify_manifest()
        return self._artifact(name, 'trace', json.dumps(report, indent=2).encode(),
                              {'backend': 'scummvm-agi', 'event_count': len(report['events']),
                               'complete': report['complete'],
                               'resource_manifest_sha256': self.manifest_sha256})

    def _save_files(self):
        result = {}
        for path in self.rpc.save_dir.iterdir():
            if path.is_symlink() or not path.is_file():
                raise ScummVMError('ScummVM save directory contains an unexpected entry')
            if path.stat().st_size > 128 * 1024 * 1024:
                raise ScummVMError('ScummVM native save exceeds the project artifact budget')
            with path.open('rb') as stream:
                data = stream.read(128 * 1024 * 1024 + 1)
            if len(data) > 128 * 1024 * 1024:
                raise ScummVMError('ScummVM native save exceeds the project artifact budget')
            result[path.name] = {'sha256': hashlib.sha256(data).hexdigest(), 'data': data}
        return result

    def save_state(self, name='checkpoint.sav'):
        self._require_paused()
        _file_name(name)
        state = self._read_state()
        self._refresh_resource_layers(state)
        if state.get('layer_conflict'):
            raise ValueError('ScummVM native save refuses an unresolved loaded-logic conflict')
        if not state.get('at_cycle'):
            raise ValueError('ScummVM native save requires an AGI cycle boundary; call run_until_cycle explicitly')
        if self._resource_layers:
            raise ValueError('Native save cannot include active loaded-logic patches; restore original bytes first')
        self._assert_input_idle('save')
        if self._next_save_slot > 999:
            raise ValueError('ScummVM native save slots 1..999 are exhausted')
        before_manifest = _manifest(self.game_dir)
        if before_manifest != self.manifest:
            raise ValueError('Game resource manifest changed during ScummVM session')
        before_files = self._save_files()
        slot = self._next_save_slot
        self._call('save', {'slot': slot})
        try:
            self._assert_input_idle('save completion')
        except BaseException:
            self.close()
            raise
        after_files = self._save_files()
        changed = [(filename, record) for filename, record in after_files.items()
                   if filename not in before_files or record['sha256'] != before_files[filename]['sha256']]
        if len(changed) != 1:
            raise ScummVMError('Native ScummVM save did not produce one identifiable slot file')
        if _manifest(self.game_dir) != self.manifest:
            raise ScummVMError('Game resource manifest changed while saving ScummVM state')
        filename, record = changed[0]
        self._next_save_slot += 1
        metadata = {**self.metadata, 'format': 'scummvm-agi-native-slot-v1',
                    'slot': slot, 'native_filename': filename,
                    'resource_manifest_sha256': self.manifest_sha256,
                    'exact_vm_checkpoint': False,
                    'restore_scope': 'ScummVM AGI cycle-level native save; opcode continuation not guaranteed',
                    'state_at_save': self.engine_state()}
        result = self._artifact(name, 'state', record['data'], metadata)
        self._event('save-state', {'artifact': result['artifact'], 'slot': slot,
                                   'sha256': result['sha256'], 'exact_vm_checkpoint': False})
        return result

    def load_state(self, artifact):
        self._require_paused()
        state_before = self._read_state()
        self._refresh_resource_layers(state_before)
        if state_before.get('layer_conflict'):
            raise ValueError('ScummVM native load refuses an unresolved loaded-logic conflict')
        if not state_before.get('at_cycle'):
            raise ValueError('ScummVM native load requires an AGI cycle boundary; call run_until_cycle explicitly')
        if self._resource_layers:
            raise ValueError('Restore original loaded-logic bytes before loading a native ScummVM save')
        self._assert_input_idle('load')
        row = self.project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (artifact,)).fetchone()
        if row is None or row['kind'] != 'state' or row['version'] != self.version['id']:
            raise ValueError('State must belong to the selected original AGI project version')
        metadata, data = json.loads(row['metadata']), bytes(row['data'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Stored ScummVM native state hash mismatch')
        for key in ('format', 'game_id', 'source_sha256', 'version_sha256',
                    'scummvm_sha256', 'runtime_profile', 'resource_manifest_sha256'):
            wanted = ('scummvm-agi-native-slot-v1' if key == 'format' else self.metadata[key])
            if metadata.get(key) != wanted:
                raise ValueError('ScummVM native state compatibility mismatch: ' + key)
        if _manifest(self.game_dir) != self.manifest:
            raise ValueError('Game resource manifest changed since ScummVM state was saved')
        slot = metadata.get('slot')
        if type(slot) is not int or not 1 <= slot <= 999:
            raise ValueError('ScummVM native save has invalid slot')
        filename = metadata.get('native_filename')
        if not isinstance(filename, str) or filename != Path(filename).name or not filename:
            raise ValueError('ScummVM native save has invalid filename')
        path = self.rpc.save_dir / filename
        if path.is_symlink():
            raise ValueError('ScummVM private save target is a symbolic link')
        path.write_bytes(data)
        try:
            reply = self._call('load', {'slot': slot})
            self._assert_input_idle('load completion')
            self._state_revision += 1
            self._last_frame = None
            state = self.engine_state()
            if self._resource_layers:
                raise ScummVMError('Native load left active AGI logic patches; continuation refused')
        except BaseException:
            # A native load can have partially changed engine state. Refuse to
            # resume a session whose post-load boundary is not verified.
            self.close()
            raise
        result = {'run': self.run_id, 'artifact': artifact, 'slot': slot,
                  'sha256': row['sha256'], 'backend': 'scummvm-agi',
                  'engine_state': state, 'native_result': reply,
                  'exact_vm_checkpoint': False, 'state_revision': self._state_revision}
        self._event('load-state', result)
        return result

    def close(self):
        if self.closed:
            return
        result = {'state': 'exited' if self._guest_exited else 'interrupted',
                  'backend': 'scummvm-agi'}
        try:
            if self.rpc is not None and self.rpc.sock is not None:
                try:
                    self.rpc.call('quit', timeout_ms=3000)
                except Exception as error:
                    result['quit_error'] = str(error)
        finally:
            if self.rpc is not None:
                self.rpc.close()
                result['process_reaped'] = self.rpc.process.poll() is not None
            self.closed = True
            try:
                self._event('close', result)
                with self.project.transaction(True):
                    self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',
                                            (stamp(), self.run_id))
            finally:
                if self in self.project._live_debuggers:
                    self.project._live_debuggers.remove(self)
