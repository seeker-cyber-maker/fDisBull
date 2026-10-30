"""Durable Z batches with explicit continuations and verified rewind boundaries."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import uuid

from .player import public_observation

LIMIT = 4 * 1024 * 1024


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Invalid batch name')
    return value


def _command(value):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > 4096 or '\n' in value:
        raise ValueError('Invalid batch command')


class BatchSession:
    """One ordered plan, bound to an opaque provider session identity.

    run() sends only pending commands. resume() may send a continuation explicitly
    declared for the current public context, never the original paused command.
    recover() requires a provider-certified rewind before invalidating later
    results. Every dispatch is journaled before execution. Journals are private.
    """
    def __init__(self, player, journal, steps):
        if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
            raise ValueError('Batch requires 1..128 steps')
        seen = set()
        for step in steps:
            if not isinstance(step, dict) or not {'id', 'command'} <= set(step) <= {'id', 'command', 'expect_context', 'continuations'}:
                raise ValueError('Invalid batch step')
            _name(step['id']); _command(step['command'])
            if step['id'] in seen:
                raise ValueError('Duplicate batch step')
            seen.add(step['id'])
            if 'expect_context' in step and (not isinstance(step['expect_context'], str) or not 1 <= len(step['expect_context']) <= 128):
                raise ValueError('Invalid expected context')
            handlers = step.get('continuations', {})
            if not isinstance(handlers, dict) or len(handlers) > 8:
                raise ValueError('Invalid batch continuations')
            for context, command in handlers.items():
                if not isinstance(context, str) or not 1 <= len(context) <= 128:
                    raise ValueError('Invalid continuation context')
                _command(command)
        self.player, self.path, self.plan = player, Path(journal), deepcopy(steps)
        if not self.path.parent.is_dir():
            raise ValueError('Batch journal parent must exist')
        with self._locked():
            if self.path.exists():
                self._read(allow_recovery=True)
            else:
                raw = self.player.backend.observe()
                token = raw.get('session_token') if isinstance(raw, dict) else None
                if public_observation(raw) is None or not isinstance(token, str) or not 1 <= len(token) <= 128:
                    raise ValueError('Batch requires a qualified session-bound provider')
                self.doc = {'format': 'fdisbull-z-batch-1', 'plan': self.plan, 'session_token': token,
                            'steps': [{'id': s['id'], 'state': 'pending', 'attempts': []} for s in steps],
                            'checkpoints': {}, 'history': [], 'recovery': None}
                self._write()

    @contextmanager
    def _locked(self):
        fd = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == 'posix':
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                os.write(fd, b'0'); os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            yield
        finally:
            os.close(fd)

    def _read(self, *, allow_recovery=False):
        if self.path.stat().st_size > LIMIT:
            raise ValueError('Batch journal exceeds budget')
        self.doc = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(self.doc, dict) or self.doc.get('format') != 'fdisbull-z-batch-1' or self.doc.get('plan') != self.plan:
            raise ValueError('Batch plan or journal format changed')
        if len(self.doc.get('steps', [])) != len(self.plan):
            raise ValueError('Invalid batch journal steps')
        for plan, step in zip(self.plan, self.doc['steps']):
            if (not isinstance(step, dict) or step.get('id') != plan['id'] or
                    step.get('state') not in ('pending', 'running', 'completed', 'paused', 'unknown', 'rejected') or
                    not isinstance(step.get('attempts'), list) or len(step['attempts']) > 16):
                raise ValueError('Invalid batch journal step')
        # A process could have stopped anywhere beyond the persisted boundary.
        interrupted = False
        for step in self.doc['steps']:
            if step['state'] == 'running':
                step['state'] = 'unknown'
                interrupted = True
                if step['attempts']:
                    step['attempts'][-1].update(state='unknown', error_type='InterruptedDispatch')
        if self.doc.get('recovery') and not allow_recovery:
            raise ValueError('Prior recovery was interrupted; inspect its private journal')
        if interrupted:
            self._write()

    def _write(self):
        data = (json.dumps(self.doc, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()
        if len(data) > LIMIT:
            raise ValueError('Batch journal exceeds budget')
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name == 'posix':
                directory = os.open(self.path.parent, os.O_RDONLY)
                try: os.fsync(directory)
                finally: os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _observe(self):
        raw = self.player.backend.observe()
        if not isinstance(raw, dict) or raw.get('session_token') != self.doc['session_token']:
            raise ValueError('Batch provider session changed; no command was sent')
        return public_observation(raw)

    def _summary(self):
        pending = next((s for s in self.doc['steps'] if s['state'] != 'completed'), None)
        return {'status': 'recovery-incomplete' if self.doc['recovery'] else pending['state'] if pending else 'completed',
                'complete': pending is None and not self.doc['recovery'],
                'next_step': pending['id'] if pending else None, 'steps': deepcopy(self.doc['steps']),
                'checkpoints': list(self.doc['checkpoints'])}

    def inspect(self):
        with self._locked():
            self._read(allow_recovery=True)
            return self._summary()

    def _attempt(self, index, command, kind):
        step = self.doc['steps'][index]
        if len(step['attempts']) >= 16:
            raise ValueError('Step continuation budget exhausted')
        if self.player.pending is not None:
            raise ValueError('Resolve player clarification before batching')
        if self._observe() is None:
            raise ValueError('Batch scene is unqualified; no command was sent')
        step['state'] = 'running'
        attempt = {'command': command, 'kind': kind, 'state': 'dispatching'}
        step['attempts'].append(attempt)
        self._write()
        try:
            result = self.player.execute_result(command)
            raw = self.player.backend.observe()
            transition = result.get('session_transition', {})
            if raw.get('session_token') != self.doc['session_token']:
                if (result['status'] != 'success' or result['complete'] is not True or
                        transition.get('from') != self.doc['session_token'] or
                        transition.get('to') != raw.get('session_token') or transition.get('reason') != 'native-load'):
                    raise ValueError('Unqualified provider-session transition')
                self.doc['session_token'] = transition['to']
            observation = public_observation(raw)
            context = observation['context']['id'] if observation else None
            attempt.update(state='returned', result=result, context=context)
            if result['complete'] is not True or result['effects'] == 'unknown' or observation is None:
                step['state'] = 'unknown'
            elif result['status'] == 'rejected':
                step['state'] = 'rejected'
            elif result['status'] == 'accepted' or result['effects'] == 'partial':
                step['state'] = 'paused'
            elif self.plan[index].get('expect_context', context) != context:
                step['state'] = 'paused'
            else:
                step['state'] = 'completed'
        except Exception as error:
            step['state'] = 'unknown'
            attempt.update(state='unknown', error_type=type(error).__name__)
        self._write()

    def _drive(self, max_steps):
        if type(max_steps) is not int or not 1 <= max_steps <= 128:
            raise ValueError('Invalid batch execution budget')
        self._observe()
        for _ in range(max_steps):
            index = next((i for i, s in enumerate(self.doc['steps']) if s['state'] != 'completed'), None)
            if index is None or self.doc['steps'][index]['state'] != 'pending':
                break
            self._attempt(index, self.plan[index]['command'], 'intent')
        return self._summary()

    def run(self, *, max_steps=128):
        with self._locked():
            self._read()
            return self._drive(max_steps)

    def resume(self, *, max_steps=128):
        if type(max_steps) is not int or not 1 <= max_steps <= 128:
            raise ValueError('Invalid batch execution budget')
        with self._locked():
            self._read()
            index = next((i for i, s in enumerate(self.doc['steps']) if s['state'] != 'completed'), None)
            if index is not None and self.doc['steps'][index]['state'] == 'paused':
                observation = self._observe()
                if observation is not None:
                    command = self.plan[index].get('continuations', {}).get(observation['context']['id'])
                    already_sent = any(a['kind'] == 'continuation' and a['command'] == command
                                       for a in self.doc['steps'][index]['attempts'])
                    if command is not None and not already_sent:
                        self._attempt(index, command, 'continuation')
            return self._drive(max_steps)

    def checkpoint(self, name):
        _name(name)
        with self._locked():
            self._read()
            if name in self.doc['checkpoints'] or len(self.doc['checkpoints']) >= 32:
                raise ValueError('Checkpoint name exists or budget exhausted')
            if any(s['state'] not in ('completed', 'pending') for s in self.doc['steps']):
                raise ValueError('Checkpoint requires a verified batch boundary')
            observation = self._observe()
            if observation is None:
                raise ValueError('Checkpoint scene is unqualified')
            self.doc['recovery'] = {'operation': 'save', 'name': name}
            self._write()
            result = self.player.backend.save('batch-' + uuid.uuid4().hex)
            self.doc['recovery'] = None
            if not isinstance(result, dict) or result.get('complete') is not True or result.get('status') != 'saved' or result.get('replay_safe') is not True:
                self._write()
                raise ValueError('Provider did not certify a replay-safe checkpoint')
            self.doc['checkpoints'][name] = {'handle': result['checkpoint'], 'context': observation['context']['id'],
                'session_token': self.doc['session_token'],
                'cursor': next((i for i, s in enumerate(self.doc['steps']) if s['state'] != 'completed'), len(self.plan))}
            self._write()
            return {'status': 'saved', 'complete': True, 'checkpoint': name}

    def recover(self, name):
        _name(name)
        with self._locked():
            self._read()
            checkpoint = self.doc['checkpoints'].get(name)
            if checkpoint is None or checkpoint['session_token'] != self.doc['session_token']:
                raise ValueError('Checkpoint is missing or belongs to another native guest')
            if len(self.doc['history']) >= 128:
                raise ValueError('Recovery history budget exhausted')
            self._observe()  # Even an unqualified view must retain its session identity.
            self.doc['recovery'] = {'operation': 'load', 'name': name}
            self._write()
            result = self.player.backend.load(checkpoint['handle'])
            observation = self._observe()
            if (not isinstance(result, dict) or result.get('complete') is not True or result.get('status') != 'restored'
                    or result.get('replay_safe') is not True or observation is None
                    or observation['context']['id'] != checkpoint['context']):
                # Keep the interrupted-recovery latch; a transport/native restore
                # failure must never authorize subsequent dispatch.
                self._write()
                return {'status': 'recovery-incomplete', 'complete': False}
            self.doc['history'].append({'checkpoint': name, 'superseded': deepcopy(self.doc['steps'][checkpoint['cursor']:])})
            for step in self.doc['steps'][checkpoint['cursor']:]:
                step.update(state='pending', attempts=[])
            self.player.pending = None
            self.doc['recovery'] = None
            self._write()
            return {'status': 'restored', 'complete': True, 'checkpoint': name, 'batch': self._summary()}
