"""Bounded, live DOS next-fetch history backed by immutable native states.

This is checkpoint-backed navigation, not reverse execution, disk rollback or
proof that an architectural instruction retired between two observed fetches.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import time
import uuid

from .operation_budget import rpc_budget


FORMAT = 'fdisbull-rewind-1'
READ_ONLY = frozenset({'agent.capabilities', 'session.status', 'state.get_registers',
                       'memory.read', 'breakpoints.list', 'trace.read',
                       'input.mouse.state', 'input.keyboard.state',
                       'video.probe', 'video.screenshot', 'state.save'})


def _bounded(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be in {low}..{high}')


def _number(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.startswith(('0x', '0X')):
        return int(value, 16)
    raise ValueError('Rewind requires explicit native hexadecimal addresses')


def _pc(registers):
    if not isinstance(registers, dict) or registers.get('cpu_mode') != 'real':
        raise ValueError('Rewind requires real-mode DOS registers')
    segment = _number(registers['segments']['cs'])
    offset = _number(registers['instruction_pointer'])
    if not 0 <= segment <= 0xffff or not 0 <= offset <= 0xffffffff:
        raise ValueError('Invalid real-mode rewind PC')
    return dict(space='segmented', segment=hex(segment), offset=hex(offset))


def _fetch_pc(event):
    address = event.get('address', {})
    if address.get('space') != 'segmented':
        raise ValueError('Rewind trace requires segmented DOS fetch addresses')
    return _pc(dict(cpu_mode='real', segments={'cs': address.get('segment')},
                    instruction_pointer=address.get('offset')))


class RewindSessionMixin:
    def _rewind_native(self):
        if self.closed:
            raise ValueError('Debugger session is closed')
        backend = getattr(self, 'backend_name', None) or self.metadata.get('backend', 'dosbox')
        if backend != 'dosbox' or not self.rpc.capabilities.get('save_states'):
            raise ValueError('Rewind requires native DOSBox with save_states; other backends are unsupported')

    def _rewind_identity(self):
        return dict(run=self.run_id, version=self.version['id'], **{
            key: self.metadata.get(key) for key in ('source_sha256', 'version_sha256',
            'emulator_sha256', 'runtime_profile', 'runtime_load_segment', 'game_dir')})

    def _rewind_invalidate(self, reason):
        history = getattr(self, '_rewind_history', None)
        if history is not None and history['valid']:
            history['valid'] = False
            history['invalid_reason'] = reason
            self._event('rewind-invalidated', dict(history=history['id'], reason=reason,
                                                 cursor=history['cursor']))

    def _rewind_before_call(self, method):
        """Invalidate before an unrecorded mutation, even if its result is unknown."""
        if not getattr(self, '_rewind_busy', False) and method not in READ_ONLY:
            self._rewind_invalidate('unrecorded RPC: ' + str(method))

    @contextmanager
    def _rewind_owned(self):
        if getattr(self, '_rewind_busy', False):
            raise ValueError('Nested rewind operations are unsupported')
        self._rewind_busy = True
        try:
            yield
        finally:
            self._rewind_busy = False

    def _rewind_require(self):
        self._rewind_native()
        history = getattr(self, '_rewind_history', None)
        if history is None or not history['valid']:
            raise ValueError('No valid rewind history; explicitly start a new history')
        if history['identity'] != self._rewind_identity():
            self._rewind_invalidate('live session identity changed')
            raise ValueError('Rewind history belongs to a different live session identity')
        return history

    def _rewind_stopped(self):
        if self.call('session.status').get('state') != 'stopped':
            raise ValueError('Rewind requires a stopped target')

    def rewind_start(self, max_steps=16, max_bytes=67108864):
        _bounded(max_steps, 'max_steps', 1, 128)
        _bounded(max_bytes, 'max_bytes', 1, 256 * 1024 * 1024)
        self._rewind_native()
        with self._rewind_owned():
            self._rewind_stopped()
            _pc(self.registers())
            self._rewind_history = dict(id=uuid.uuid4().hex, identity=self._rewind_identity(),
                valid=True, invalid_reason=None, cursor=0, entries=[], captures_used=0,
                state_bytes_used=0, max_steps=max_steps, max_bytes=max_bytes, disk_manifest=None)
        result = self.rewind_status()
        self._event('rewind-start', result)
        return result

    def rewind_status(self):
        history = getattr(self, '_rewind_history', None)
        result = dict(format=FORMAT, run=self.run_id, active=history is not None and not self.closed,
                      valid=False, unit='next-fetch interval', instruction_completion='unknown',
                      implementation='immutable native checkpoints; no deterministic replay',
                      disk_restore=False, survives_live_session=False,
                      budget_scope='cumulative checkpoint payloads per explicit history; artifacts retained')
        if history is None:
            return dict(result, history=None, cursor=0, available_back=0, retained_steps=0,
                        captures_used=0, state_bytes_used=0, invalid_reason='not_started')
        return dict(result, history=history['id'], valid=history['valid'] and not self.closed,
                    invalid_reason='session_closed' if self.closed else history['invalid_reason'],
                    cursor=history['cursor'], available_back=history['cursor'] if history['valid'] and not self.closed else 0,
                    retained_steps=len(history['entries']), captures_used=history['captures_used'],
                    state_bytes_used=history['state_bytes_used'], max_steps=history['max_steps'],
                    max_bytes=history['max_bytes'])

    def _rewind_trace(self, artifact, before):
        identifier = artifact.get('artifact')
        row = self.project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (identifier,)).fetchone()
        if row is None or row['kind'] != 'trace' or row['run'] != self.run_id or row['version'] != self.version['id']:
            raise ValueError('Rewind trace must belong to this live run and version')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Rewind trace artifact hash mismatch')
        trace = json.loads(data)
        events = trace.get('events', [])
        run = trace.get('run', {})
        terminal = run.get('session') or {}
        if (trace.get('complete') is not True or trace.get('requested_count') != 2
                or trace.get('version') != self.version['id'] or len(events) != 2
                or run.get('run') != self.run_id or run.get('outcome') != 'pause'
                or run.get('timed_out') is not False or run.get('hook_hits')
                or terminal.get('state') != 'stopped'
                or terminal.get('stop_reason', {}).get('kind') != 'pause'
                or events[-1].get('observation', {}).get('instruction_completed') is not False):
            raise ValueError('Rewind requires exactly two fetches and a clean trace-budget pause')
        first, last = _fetch_pc(events[0]), _fetch_pc(events[1])
        if first != before or _pc(self.registers()) != last:
            raise ValueError('Rewind trace fetches do not match before/after CPU readback')
        return last

    @rpc_budget
    def rewind_record(self, count=1, timeout_ms=10000):
        _bounded(count, 'count', 1, 128)
        history = self._rewind_require()
        if history['captures_used'] + count > history['max_steps']:
            raise ValueError('Rewind capture budget exhausted; earlier checkpoints remain available')
        if history['max_bytes'] - history['state_bytes_used'] < count:
            raise ValueError('Rewind state byte budget exhausted')
        records = []
        started = time.monotonic()
        with self._rewind_owned():
            try:
                self._rewind_stopped()
                for _ in range(count):
                    remaining = history['max_bytes'] - history['state_bytes_used']
                    checkpoint = self.save_state('rewind-before.sav', max_bytes=remaining)
                    size = checkpoint.get('size')
                    if type(size) is not int or not 1 <= size <= remaining:
                        raise ValueError('Rewind checkpoint violated its state byte budget')
                    history['captures_used'] += 1
                    history['state_bytes_used'] += size
                    metadata = checkpoint.get('metadata', {})
                    before = _pc(metadata.get('registers'))
                    manifest = metadata.get('disk_manifest')
                    if history['disk_manifest'] is not None and manifest != history['disk_manifest']:
                        raise ValueError('Mounted game files changed during rewind history')
                    history['disk_manifest'] = deepcopy(manifest)
                    # Starting a new future keeps immutable old artifacts and their cost.
                    history['entries'] = history['entries'][:history['cursor']]
                    deadline = self._rpc_deadline - time.monotonic()
                    if deadline <= 0:
                        raise TimeoutError('Rewind recording host-time budget expired before execution')
                    trace = self.trace('rewind-fetch.json', count=2,
                                       timeout_ms=max(1, int(deadline * 1000)), fast_forward=True)
                    after = self._rewind_trace(trace, before)
                    entry = dict(index=history['cursor'] + 1,
                                 checkpoint={key: checkpoint[key] for key in ('artifact', 'sha256', 'size')},
                                 registers=deepcopy(metadata['registers']), before_pc=before,
                                 after_pc=after, trace_artifact=trace['artifact'])
                    history['entries'].append(entry)
                    history['cursor'] += 1
                    records.append(deepcopy({key: value for key, value in entry.items() if key != 'registers'}))
            except BaseException as error:
                self._rewind_invalidate('record failed: ' + type(error).__name__)
                raise
        result = dict(format=FORMAT, run=self.run_id, requested_count=count, recorded_count=len(records),
                      cursor=history['cursor'], records=records, history=self.rewind_status(),
                      host_elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        self._event('rewind-record', result)
        return result

    def rewind(self, count=1):
        _bounded(count, 'count', 1, 128)
        history = self._rewind_require()
        if count > history['cursor']:
            raise ValueError('Rewind count exceeds the available past')
        target = history['cursor'] - count
        entry = history['entries'][target]
        restored = None
        with self._rewind_owned():
            try:
                self._rewind_stopped()
                restored = self.load_state(entry['checkpoint']['artifact'])
                registers = self.registers()
                if any(registers.get(key) != entry['registers'].get(key)
                       for key in ('general', 'segments', 'instruction_pointer', 'flags')):
                    raise ValueError('Rewind CPU readback differs from the selected checkpoint')
                history['cursor'] = target
            except BaseException as error:
                self._rewind_invalidate('restore failed: ' + type(error).__name__)
                # load_state closes on its own partial failures. If its subsequent
                # independent readback differs, that state must not resume either.
                if restored is not None:
                    try:
                        self.close()
                    except Exception:
                        pass
                raise
        result = dict(format=FORMAT, run=self.run_id, rewound_count=count, cursor=target,
                      target_checkpoint=deepcopy(entry['checkpoint']), restore=restored,
                      history=self.rewind_status())
        self._event('rewind', result)
        return result
