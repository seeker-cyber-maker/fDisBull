"""A small, single-owner dependency queue for retained Z investigations.

Facts are available by presence, including false/zero values. The queue does not
execute operations or infer scientific correctness from evidence references.
Publishing a changed input retires dependent outputs and makes those tasks ready
to be reconsidered. Failed tasks require an explicit retry. There are no workers,
pollers or background processes here.
"""

from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile


_FORMAT = 'fdisbull-dependency-queue-1'
_STATUSES = ('pending', 'running', 'completed', 'failed')
_MAX_TASKS, _MAX_FACTS, _MAX_HISTORY = 256, 1024, 64
_MAX_BYTES = 2 * 1024 * 1024


def _key(value, label='key'):
    if (not isinstance(value, str) or not value.strip() or len(value) > 128
            or any(ord(c) < 32 for c in value)):
        raise ValueError(f'{label} must be a nonempty string of at most 128 characters')
    return value


def _keys(values, label):
    if not isinstance(values, (tuple, list)) or len(values) > 128:
        raise ValueError(f'{label} must be a list of at most 128 fact keys')
    result = [_key(value, label) for value in values]
    if len(set(result)) != len(result):
        raise ValueError(f'{label} contains duplicate fact keys')
    return result


def _json(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)


def _evidence(value):
    if (not isinstance(value, (str, dict)) or not value
            or len(_json(value).encode()) > 16384):
        raise ValueError('evidence must be a nonempty reference string or object of at most 16 KiB')


def _operation(value):
    if value is None:
        return
    if (not isinstance(value, dict) or set(value) - {'verb', 'params'}
            or 'verb' not in value or not isinstance(value.get('params', {}), dict)):
        raise ValueError('operation must contain verb and optional object params')
    _key(value['verb'], 'operation verb')
    _json(value)


class DependencyQueue:
    """Persistent bounded facts/tasks. Mutations save when a path is attached.

    ``load(path)`` creates an empty queue when the path does not exist. Instances
    are for one controller owner; callers must not concurrently edit one file.
    A persisted running task stays running until explicit completion/failure or
    ``retry``; opening a file never repeats an operation.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self._state = {'format': _FORMAT, 'revision': 0, 'facts': {}, 'tasks': {}, 'history': []}

    @classmethod
    def load(cls, path):
        queue = cls(path)
        if queue.path.exists():
            if queue.path.stat().st_size > _MAX_BYTES:
                raise ValueError('queue file exceeds 2 MiB')
            queue._state = json.loads(queue.path.read_text())
            queue._validate()
        return queue

    def snapshot(self):
        """Return a detached raw representation; retained raw data needs no copy ledger."""
        return deepcopy(self._state)

    def _producers(self):
        owners = {}
        for task in self._state['tasks'].values():
            for key in task['produces']:
                if key in owners:
                    raise ValueError(f'fact has more than one producer: {key}')
                owners[key] = task['id']
        return owners

    def _validate(self):
        state = self._state
        if (not isinstance(state, dict) or set(state) != {'format', 'revision', 'facts', 'tasks', 'history'}
                or state['format'] != _FORMAT or type(state['revision']) is not int or state['revision'] < 0
                or not isinstance(state['facts'], dict) or len(state['facts']) > _MAX_FACTS
                or not isinstance(state['tasks'], dict) or len(state['tasks']) > _MAX_TASKS
                or not isinstance(state['history'], list) or len(state['history']) > _MAX_HISTORY):
            raise ValueError('invalid or oversized dependency queue')
        for ident, task in state['tasks'].items():
            if not isinstance(task, dict) or task.get('id') != _key(ident, 'task id'):
                raise ValueError('invalid task identity')
            _keys(task.get('requires'), 'requires')
            _keys(task.get('produces'), 'produces')
            _operation(task.get('operation'))
            if type(task.get('priority')) is not int or task.get('status') not in _STATUSES:
                raise ValueError('invalid task priority or status')
        producers = self._producers()
        edges = {ident: {producers[key] for key in task['requires'] if key in producers}
                 for ident, task in state['tasks'].items()}
        visited, visiting = set(), set()

        def visit(ident):
            if ident in visiting:
                raise ValueError('task dependencies contain a cycle')
            if ident in visited:
                return
            visiting.add(ident)
            for before in edges[ident]:
                visit(before)
            visiting.remove(ident)
            visited.add(ident)
        for ident in edges:
            visit(ident)
        for key, fact in state['facts'].items():
            _key(key)
            if (not isinstance(fact, dict) or set(fact) != {'value', 'evidence', 'revision', 'producer'}
                    or type(fact['revision']) is not int or not 1 <= fact['revision'] <= state['revision']
                    or fact['producer'] != producers.get(key)):
                raise ValueError(f'invalid fact: {key}')
            _evidence(fact['evidence'])
        for task in state['tasks'].values():
            if task['status'] in ('running', 'completed'):
                claimed = task.get('claimed_inputs')
                if (not isinstance(claimed, dict) or set(claimed) != set(task['requires'])
                        or any(type(value) is not int for value in claimed.values())
                        or any(key not in state['facts'] or state['facts'][key]['revision'] != version
                               for key, version in claimed.items())):
                    raise ValueError('running/completed task needs claimed input revisions')
            if task['status'] == 'completed' and any(key not in state['facts'] for key in task['produces']):
                raise ValueError('completed task is missing its declared output')
        if len(_json(state).encode()) > _MAX_BYTES:
            raise ValueError('queue exceeds 2 MiB; keep full results by artifact reference')

    def save(self, path=None):
        destination = Path(path) if path is not None else self.path
        if destination is None:
            raise ValueError('save needs a path')
        self._validate()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=destination.parent,
                                             prefix=destination.name + '.', suffix='.new',
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(_json(self._state) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self.path = destination
        return str(destination)

    def _change(self, action):
        previous = deepcopy(self._state)
        try:
            self._state['revision'] += 1
            result = action()
            self._validate()
            if self.path is not None:
                self.save()
            return deepcopy(result)
        except Exception:
            self._state = previous
            raise

    def _event(self, kind, **fields):
        self._state['history'].append({'revision': self._state['revision'], 'kind': kind, **fields})
        self._state['history'] = self._state['history'][-_MAX_HISTORY:]

    def add_task(self, id, *, requires=(), produces=(), operation=None, priority=0):
        ident = _key(id, 'task id')
        required, produced = _keys(requires, 'requires'), _keys(produces, 'produces')
        _operation(operation)
        if type(priority) is not int:
            raise ValueError('priority must be an integer')
        if ident in self._state['tasks']:
            raise ValueError('task id already exists')
        if any(key in self._state['facts'] for key in produced):
            raise ValueError('cannot assign a new producer to an already published fact')
        task = {'id': ident, 'requires': required, 'produces': produced,
                'operation': deepcopy(operation), 'priority': priority, 'status': 'pending'}
        def add():
            self._state['tasks'][ident] = task
            self._event('task_added', task=ident)
            return task
        return self._change(add)

    def _invalidate(self, changed):
        invalidated, frontier = set(), set(changed)
        while frontier:
            following = set()
            for task in self._state['tasks'].values():
                if task['id'] in invalidated or not frontier.intersection(task['requires']):
                    continue
                invalidated.add(task['id'])
                was_running = task['status'] == 'running'
                if task['status'] != 'failed':
                    task['status'] = 'failed' if was_running else 'pending'
                task['reason'] = 'inputs_changed_during_operation' if was_running else 'inputs_changed'
                task.pop('claimed_inputs', None)
                for key in task['produces']:
                    if key in self._state['facts']:
                        del self._state['facts'][key]
                        following.add(key)
            frontier = following
        if invalidated:
            self._event('inputs_invalidated', tasks=sorted(invalidated))

    def _publish(self, key, value, evidence, producer=None):
        _key(key)
        _evidence(evidence)
        value = json.loads(_json(value))
        owner = self._producers().get(key)
        if producer is not None and producer != owner:
            raise ValueError('producer must be the task declaring this output')
        old = self._state['facts'].get(key)
        same_value = old is not None and _json(old['value']) == _json(value)
        if old is not None and (not same_value or old['producer'] != owner):
            self._invalidate({key})
        revision = old['revision'] if same_value else self._state['revision']
        self._state['facts'][key] = {'value': deepcopy(value), 'evidence': deepcopy(evidence),
                                      'revision': revision, 'producer': owner}
        self._event('fact_published', key=key)
        return self._state['facts'][key]

    def publish(self, key, value, evidence, *, producer=None):
        """Publish a useful partial immediately. Evidence is attribution, not proof.

        A declared output's producer is inferred from its unique task. Replacing
        its value invalidates dependent work; adding another reference to the
        same JSON value preserves the input revision.
        """
        return self._change(lambda: self._publish(key, value, evidence, producer))

    def ready(self):
        facts = self._state['facts']
        return deepcopy(sorted((task for task in self._state['tasks'].values()
                                if task['status'] == 'pending'
                                and all(key in facts for key in task['requires'])),
                               key=lambda task: (-task['priority'], task['id'])))

    def _task(self, id):
        if id not in self._state['tasks']:
            raise ValueError(f'unknown task: {id}')
        return self._state['tasks'][id]

    def claim(self, id):
        def claim():
            task = self._task(id)
            if id not in {t['id'] for t in self.ready()}:
                raise ValueError('task is not ready')
            task['status'] = 'running'
            task.pop('reason', None)
            task['claimed_inputs'] = {key: self._state['facts'][key]['revision'] for key in task['requires']}
            self._event('task_claimed', task=id)
            return task
        return self._change(claim)

    def complete(self, id, outputs=None):
        """Complete a claimed task only when every declared output is published.

        Optional ``outputs`` maps declared keys to ``{value, evidence}``. This
        convenience publication and completion are atomic, including persistence.
        """
        def complete():
            task = self._task(id)
            if task['status'] != 'running':
                raise ValueError('task must be running before completion')
            if outputs is not None:
                if not isinstance(outputs, dict) or set(outputs) - set(task['produces']):
                    raise ValueError('outputs may contain only declared fact keys')
                for key, fact in outputs.items():
                    if not isinstance(fact, dict) or set(fact) != {'value', 'evidence'}:
                        raise ValueError('each output needs value and evidence')
                    self._publish(key, fact['value'], fact['evidence'], id)
            if any(key not in self._state['facts'] for key in task['produces']):
                raise ValueError('required output facts have not been published')
            if task['claimed_inputs'] != {key: self._state['facts'][key]['revision'] for key in task['requires']}:
                raise ValueError('claimed input facts changed')
            task['status'] = 'completed'
            self._event('task_completed', task=id)
            return task
        return self._change(complete)

    def fail(self, id, reason):
        _evidence(reason)
        def fail():
            task = self._task(id)
            if task['status'] != 'running':
                raise ValueError('only a running task can fail')
            task.update(status='failed', reason=deepcopy(reason))
            self._event('task_failed', task=id)
            return task
        return self._change(fail)

    def retry(self, id):
        def retry():
            task = self._task(id)
            if task['status'] not in ('failed', 'running'):
                raise ValueError('retry requires a failed or interrupted running task')
            task['status'] = 'pending'
            task.pop('reason', None)
            task.pop('claimed_inputs', None)
            self._event('task_retried', task=id)
            return task
        return self._change(retry)

    def summary(self):
        ready = {task['id'] for task in self.ready()}
        return {'format': _FORMAT, 'revision': self._state['revision'], 'path': str(self.path) if self.path else None,
                'fact_keys': sorted(self._state['facts']), 'task_counts': dict(Counter(
                    task['status'] for task in self._state['tasks'].values())),
                'ready': [task['id'] for task in self.ready()],
                'tasks': [{'id': task['id'], 'status': task['status'], 'ready': task['id'] in ready,
                           'missing': [key for key in task['requires'] if key not in self._state['facts']],
                           **({'reason': task['reason']} if 'reason' in task else {})}
                          for task in self._state['tasks'].values()]}
