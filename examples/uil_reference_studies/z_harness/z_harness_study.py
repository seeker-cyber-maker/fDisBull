"""A bounded Z observation/action envelope over the existing UIL study evaluator.

The calendar state is authoritative. Z projects two of its slots and invokes one
named action. Private checkpoints retain every slot at completed UIL invocation
boundaries. This is not native rewind, instruction tracing, or a whole game.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import uuid

from uil_text_study import run, validate


PROFILE = 'z-uil-binding-study-1'
CLOCK_UNIT = 'UIL invocation'
ACTION = 'advance-calendar-slice'
EXPECTED_TYPES = ['u16', 'i16', 'u8'] + ['u16'] * 8 + ['i16']
REQUIRED_SLOTS = list(range(11))


def _fields(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Unexpected or missing envelope fields')


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 1024:
        raise ValueError('Nonempty bounded text required')


def _identity(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_scene(document):
    """Validate this intentionally small calendar envelope, not a new UIL grammar."""
    _fields(document, ('format', 'scene', 'clock', 'action', 'public_slots',
                       'comparison', 'max_history', 'uil'))
    if document['format'] != PROFILE:
        raise ValueError('Unsupported Z binding study profile')
    _fields(document['scene'], ('id', 'title', 'description'))
    for value in document['scene'].values():
        _text(value)
    _fields(document['clock'], ('unit', 'basis'))
    if document['clock'] != {'unit': CLOCK_UNIT, 'basis': 'successful committed call'}:
        raise ValueError('This harness records only completed UIL invocation boundaries')
    _fields(document['action'], ('id', 'label'))
    _text(document['action']['label'])
    if document['action']['id'] != ACTION:
        raise ValueError('Unsupported study action')
    if type(document['max_history']) is not int or not 1 <= document['max_history'] <= 64:
        raise ValueError('History capacity must be 1..64 snapshots, including initial state')
    _fields(document['public_slots'], ('turn', 'year'))
    if any(type(value) is not int for value in document['public_slots'].values()):
        raise ValueError('Public slots require exact integer indices')
    if document['public_slots'] != {'turn': 0, 'year': 1}:
        raise ValueError('This study exposes only calendar turn and year')
    _fields(document['comparison'], ('required_slots',))
    slots = document['comparison']['required_slots']
    if type(slots) is not list or any(type(slot) is not int for slot in slots) or slots != REQUIRED_SLOTS:
        raise ValueError('Required comparison includes slots0..10, including hidden state')
    validate(document['uil'])
    program = document['uil']['program']
    if [entry['type'] for entry in program['variables']] != EXPECTED_TYPES:
        raise ValueError('Calendar slot declarations differ')
    if program['inputs'] != REQUIRED_SLOTS or program['outputs'] != [0, 1] + list(range(3, 11)):
        raise ValueError('Calendar input/output ports differ')
    return True


@dataclass(frozen=True)
class _Snapshot:
    """Immutable scalar state; parent links preserve discarded future branches."""
    identifier: str
    parent: str | None
    position: int
    state: tuple


class ZHarnessStudy:
    def __init__(self, document):
        validate_scene(document)
        self._document = deepcopy(document)
        self._scene_hash = _identity(self._document)
        self._session = uuid.uuid4().hex
        self._revision = 0
        self._cursor = 'snapshot-0'
        initial = tuple(deepcopy(document['uil']['bindings']['initial']))
        self._snapshots = {'snapshot-0': _Snapshot('snapshot-0', None, 0, initial)}
        self._last_attempt = None

    def _current(self):
        return self._snapshots[self._cursor]

    def _token(self):
        # Revision changes on restore even when the restored values are equal.
        return _identity([self._session, self._scene_hash, self._cursor, self._revision])

    def _public_values(self, state):
        return {label: deepcopy(state[slot]) for label, slot in self._document['public_slots'].items()}

    def observe(self):
        """Public Z view; hidden words and source bindings are deliberately absent."""
        current = self._current()
        return {'format': 'z-observation-study-1', 'scene': deepcopy(self._document['scene']),
                'values': self._public_values(current.state),
                'actions': [deepcopy(self._document['action'])],
                'clock': {'unit': CLOCK_UNIT, 'position': current.position},
                'context_token': self._token()}

    def _evaluate_from(self, uil, state):
        invocation = deepcopy(uil)
        invocation['bindings']['initial'] = list(state)
        inputs = [state[slot] for slot in invocation['program']['inputs']]
        return run(invocation, inputs)

    def act(self, request):
        _fields(request, ('action', 'context_token'))
        _text(request['action'])
        _text(request['context_token'])
        if request['context_token'] != self._token():
            return {'status': 'refused', 'reason': 'stale_context', 'observation': self.observe()}
        if request['action'] != ACTION:
            return {'status': 'refused', 'reason': 'unknown_action', 'observation': self.observe()}
        # Cumulative capacity includes the initial state and every retained branch.
        if len(self._snapshots) >= self._document['max_history']:
            return {'status': 'refused', 'reason': 'history_capacity', 'observation': self.observe()}
        current = self._current()
        outcome = self._evaluate_from(self._document['uil'], current.state)
        self._last_attempt = deepcopy(outcome)
        if outcome['status'] != 'complete':
            # No host adapter is installed. A staged event cannot commit state here.
            return {'status': outcome['status'], 'reason': outcome.get('reason'),
                    'events': deepcopy(outcome['events']), 'host_effects_executed': False,
                    'observation': self.observe()}
        identifier = 'snapshot-' + str(len(self._snapshots))
        self._snapshots[identifier] = _Snapshot(identifier, self._cursor,
                                               current.position + 1, tuple(outcome['state']))
        self._cursor = identifier
        self._revision += 1
        return {'status': 'complete', 'observation': self.observe()}

    def checkpoint(self):
        """A private, session-owned reference to already captured immutable state."""
        return {'format': 'z-checkpoint-study-1', 'session': self._session,
                'scene_sha256': self._scene_hash, 'snapshot': self._cursor}

    def restore(self, checkpoint):
        _fields(checkpoint, ('format', 'session', 'scene_sha256', 'snapshot'))
        if (checkpoint['format'] != 'z-checkpoint-study-1' or
                checkpoint['session'] != self._session or checkpoint['scene_sha256'] != self._scene_hash or
                type(checkpoint['snapshot']) is not str or checkpoint['snapshot'] not in self._snapshots):
            raise ValueError('Checkpoint is not owned by this scene session')
        self._cursor = checkpoint['snapshot']
        self._revision += 1
        self._last_attempt = None
        return {'status': 'restored', 'observation': self.observe()}

    def rewind_one(self):
        parent = self._current().parent
        if parent is None:
            return {'status': 'refused', 'reason': 'no_recorded_parent', 'observation': self.observe()}
        checkpoint = self.checkpoint()
        checkpoint['snapshot'] = parent
        return self.restore(checkpoint)

    def private_state(self):
        return list(self._current().state)

    def private_history(self):
        return {'unit': CLOCK_UNIT, 'cursor': self._cursor,
                'snapshots_used': len(self._snapshots), 'capacity': self._document['max_history'],
                'nodes': [{'snapshot': node.identifier, 'parent': node.parent,
                           'position': node.position, 'state': list(node.state)}
                          for node in self._snapshots.values()]}

    def private_last_attempt(self):
        return deepcopy(self._last_attempt)

    def last_change(self, slot):
        """Find the latest net change on the current branch, never infer causality."""
        if type(slot) is not int or not 0 <= slot < len(EXPECTED_TYPES):
            raise ValueError('Invalid zero-based slot')
        node = self._current()
        result = {'kind': 'net-change-between-invocations', 'slot': slot, 'unit': CLOCK_UNIT,
                  'limitation': 'Same-value writes and transient changes inside an invocation are invisible.'}
        while node.parent is not None:
            parent = self._snapshots[node.parent]
            if node.state[slot] != parent.state[slot]:
                return {**result, 'status': 'found', 'before_snapshot': parent.identifier,
                        'after_snapshot': node.identifier, 'before': parent.state[slot], 'after': node.state[slot]}
            node = parent
        return {**result, 'status': 'not_found'}

    def compare_variant(self, candidate):
        """Private differential check at one entry state and a declared projection."""
        validate(candidate)
        base = self._document['uil']
        for field in ('variables', 'inputs', 'outputs'):
            if candidate['program'][field] != base['program'][field]:
                raise ValueError('Candidate calendar interface differs')
        state = self._current().state
        expected = self._evaluate_from(base, state)
        actual = self._evaluate_from(candidate, state)
        result = {'scope': 'One entry state, two UIL model invocations, required slot projection only.',
                  'original_machine_executed': False, 'reference_status': expected['status'],
                  'candidate_status': actual['status'], 'required_slots': REQUIRED_SLOTS[:],
                  'agreement': False, 'public_equal': None, 'mismatches': []}
        if expected['status'] != 'complete' or actual['status'] != 'complete':
            return result
        result['public_equal'] = self._public_values(expected['state']) == self._public_values(actual['state'])
        result['mismatches'] = [{'slot': slot, 'expected': expected['state'][slot], 'actual': actual['state'][slot]}
                                for slot in REQUIRED_SLOTS if expected['state'][slot] != actual['state'][slot]]
        result['agreement'] = not result['mismatches']
        return result


def _read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def demo(scene_path=None, candidate_path=None):
    root = Path(__file__).resolve().parent / 'examples'
    harness = ZHarnessStudy(_read(scene_path or root / 'calendar_scene.json'))
    start = harness.checkpoint()
    public_before = harness.observe()
    comparison = harness.compare_variant(_read(candidate_path or root / 'faulty_calendar_variant.json'))
    first = harness.act({'action': ACTION, 'context_token': public_before['context_token']})
    first_checkpoint = harness.checkpoint()
    net_change = harness.last_change(4)
    harness.rewind_one()
    restored = harness.observe()
    second = harness.act({'action': ACTION, 'context_token': restored['context_token']})
    return {'profile': PROFILE, 'native_execution': False, 'before': public_before['values'],
            'after': first['observation']['values'], 'restored': restored['values'],
            'clock_unit': CLOCK_UNIT, 'retained_snapshots': harness.private_history()['snapshots_used'],
            'first_branch': first_checkpoint['snapshot'], 'second_branch': harness.checkpoint()['snapshot'],
            'shared_parent': start['snapshot'], 'last_net_change': net_change,
            'faulty_variant_comparison': comparison, 'second_status': second['status']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path)
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    print(json.dumps(demo(args.scene, args.candidate), indent=2))
