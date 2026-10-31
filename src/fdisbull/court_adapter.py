"""UDL realization of the bounded court intent into original AGI requests.

This adapter does not interpret source control flow to select an outcome. The
pure UIL evaluator makes that decision. Its named effects expand to the bound
engine requests and data writes. Original rendering, animation scheduling and
modal time remain host dependencies; no stand-alone game execution is implied.
"""
from __future__ import annotations

import copy
import gzip
import json
import zlib
from pathlib import Path

from .court_intents import canonical_digest, evaluate_event
from .kq1_bow import verify_bow_package


class CourtAdapterError(ValueError):
    pass


def _read_document(path, limit):
    path = Path(path).expanduser()
    opener = gzip.open if path.suffix == '.gz' else open
    try:
        with opener(path, 'rb') as stream:
            raw = stream.read(limit + 1)
    except (EOFError, zlib.error) as exc:
        raise CourtAdapterError('Invalid compressed input document') from exc
    if len(raw) > limit:
        raise CourtAdapterError('Input document exceeds its byte budget')
    return json.loads(raw)


def evaluate_bow(package, *, state=None, state_file=None, event=None, event_file=None):
    """Public private-package API; evaluate rules and requests, without a guest."""
    if (state is None) == (state_file is None):
        raise CourtAdapterError('Supply exactly one of state or state_file')
    if event is not None and event_file is not None:
        raise CourtAdapterError('Supply at most one of event or event_file')
    document = _read_document(package, 32 * 1024 * 1024)
    state = _read_document(state_file, 1024 * 1024) if state_file is not None else state
    event = _read_document(event_file, 64 * 1024) if event_file is not None else event
    result = CourtRuntime(document).step(state, event)
    return {**result, 'execution_scope': 'intent_rules_and_bound_engine_requests',
            'native_execution': False,
            'host_dependencies': document['uil']['host_dependencies']}


def validate_source_state(state):
    required = {'variables', 'flags', 'ego', 'words', 'player_control'}
    if (not isinstance(state, dict) or not required <= set(state) or
            set(state) - required - {'host'}):
        raise CourtAdapterError('Invalid bounded AGI state fields')
    if (not isinstance(state['variables'], list) or len(state['variables']) != 256 or
            any(type(v) is not int or not 0 <= v <= 255 for v in state['variables'])):
        raise CourtAdapterError('Variables must contain 256 bytes')
    if (not isinstance(state['flags'], list) or len(state['flags']) != 256 or
            any(type(v) is not bool for v in state['flags'])):
        raise CourtAdapterError('Flags must contain 256 Booleans')
    if (not isinstance(state['ego'], dict) or set(state['ego']) != {'x', 'y'} or
            any(type(v) is not int or not 0 <= v <= 255 for v in state['ego'].values())):
        raise CourtAdapterError('Invalid actor baseline coordinates')
    if (not isinstance(state['words'], list) or len(state['words']) > 255 or
            any(type(v) is not int or not 0 <= v <= 65535 for v in state['words'])):
        raise CourtAdapterError('Invalid parsed word groups')
    if type(state['player_control']) is not bool or ('host' in state and not isinstance(state['host'], dict)):
        raise CourtAdapterError('Invalid host control state')


class CourtRuntime:
    """A validated package, reused across independent bounded invocations."""
    def __init__(self, package):
        self.package = copy.deepcopy(package)
        self.bindings = verify_bow_package(self.package)
        self.uil = self.package['uil']
        self.package_sha256 = canonical_digest(self.package)

    def _continuation_digest(self, state):
        # Ordinary print waits continue the engine clock. These fields are
        # explicitly outside the suspended interaction's ownership; all other
        # source fields remain bound, and the current clock values survive ack.
        protected = copy.deepcopy(state)
        for number in self.package['udl']['qualification']['modal_host_mutable_variables']:
            protected['variables'][number] = 0
        return canonical_digest(protected)

    @staticmethod
    def project_state(state):
        validate_source_state(state)
        variables, flags = state['variables'], state['flags']
        words = state['words']
        return {
            'actor_x': state['ego']['x'], 'actor_y': state['ego']['y'],
            'score': variables[3], 'direction': variables[6],
            'sequence_countdown': variables[30], 'treasure_count': variables[74],
            'bowed_this_visit': flags[24], 'respect_awarded': flags[168],
            'invisible': flags[79], 'standing_animation': flags[98],
            'bow_complete': flags[22], 'input_ready': flags[2],
            'input_consumed': flags[4], 'player_control': state['player_control'],
            'command': 'bow' if words == [239] else 'bow_to_king' if words == [239, 208] else None,
        }

    @staticmethod
    def _qualification(state):
        v, f = state['variables'], state['flags']
        if v[0] != 53 or f[5] or f[195] or f[194] or v[74] == 3 or f[27]:
            return 'outside_initial_audience'
        if any(v[n] != 0 for n in (30, 70, 71)):
            return 'ending_prefix_not_idle'
        if f[15] or v[21] != 0:
            return 'nonblocking_or_timed_output'
        if f[2] and not f[4] and state['words'] not in ([239], [239, 208]):
            return 'other_parser_command_retained_as_ir'
        if not 0 <= state['ego']['x'] <= 159 or not 0 <= state['ego']['y'] <= 167:
            return 'actor_outside_qualified_screen'
        # The gesture callback is meaningful only for an outstanding bow in
        # this profile. Other flag origins remain original source behavior.
        if f[22] and (not f[24] or not f[98] or not 11 <= state['ego']['x'] <= 79
                      or not 80 <= state['ego']['y'] <= 113):
            return 'unqualified_animation_completion'
        return None

    def step(self, source_state, event=None):
        """Execute the selected room segment or resume its exact pending modal.

        The caller owns the original room/global scheduler and chooses this
        boundary only after its retained prefix. Raw coordinates are preserved,
        including the bow's temporary shift and completion's current-position
        restoration. A finished segment may still have animation outstanding.
        """
        validate_source_state(source_state)
        event = {'kind': 'cycle'} if event is None else event
        if not isinstance(event, dict) or event.get('kind') not in ('cycle', 'ack'):
            raise CourtAdapterError('Invalid adapter event')
        semantic = self.project_state(source_state)
        if event['kind'] == 'ack':
            if set(event) != {'kind', 'continuation'}:
                raise CourtAdapterError('Invalid acknowledgement fields')
            saved = event['continuation']
            if (not isinstance(saved, dict) or set(saved) != {'package_sha256', 'source_state_sha256', 'semantic'}
                    or saved['package_sha256'] != self.package_sha256
                    or saved['source_state_sha256'] != self._continuation_digest(source_state)):
                raise CourtAdapterError('Stale source state or package in modal continuation')
            semantic_event = {'kind': 'ack', 'continuation': saved['semantic']}
        else:
            if set(event) != {'kind'}:
                raise CourtAdapterError('Invalid dispatch fields')
            semantic_event = event
        reason = self._qualification(source_state)
        if reason:
            return {'status': 'unrecovered', 'outcome': 'unrecovered', 'reason': reason,
                    'state': copy.deepcopy(source_state), 'effects': [],
                    'executed_intents': [], 'continuation': None, 'semantic_state': semantic}
        result = evaluate_event(self.uil, semantic, semantic_event)
        if result['status'] == 'unrecovered':
            return {**result, 'state': copy.deepcopy(source_state), 'semantic_state': semantic}
        current = copy.deepcopy(source_state)
        v, f, ego = current['variables'], current['flags'], current['ego']
        actions = []

        def emit(operation, *operands):
            actions.append({'operation': operation, 'operands': list(operands)})

        def flag(number, value):
            emit('set' if value else 'reset', number)
            f[number] = value

        def position_scratch(delta):
            emit('get.posn', 0, 60, 61)
            v[60], v[61] = ego['x'], ego['y']
            emit('subn' if delta < 0 else 'addn', 60, abs(delta))
            v[60] = (v[60] + delta) % 256

        def place():
            emit('position.v', 0, 60, 61)
            ego.update(x=v[60], y=v[61])

        def cycle_time(value):
            emit('assignn', 31, value)
            v[31] = value
            emit('cycle.time', 0, 31)

        for effect in result['effects']:
            if 'residual_ir' in effect:
                # A retained source implementation flag, not a new game intent.
                left, top, right, bottom = self.uil['geometry']['improper_position']
                flag(21, left <= ego['x'] <= right and top <= ego['y'] <= bottom)
                continue
            name = effect['intent']
            if name == 'input.claim':
                # A successful stateful said predicate performs this write.
                # It is not an invented AGI action in the request trace.
                f[4] = True
            elif name == 'court.begin_bow':
                flag(24, True)
                position_scratch(self.uil['gesture']['start_dx'])
                emit('erase', 0)
                emit('stop.motion', 0)
                v[6], current['player_control'] = 0, False
                emit('set.view', 0, 71)
                emit('set.cel', 0, 0)
                place()
                cycle_time(2)
                emit('draw', 0)
                emit('end.of.loop', 0, 22)
                f[22] = False
                flag(98, True)
            elif name == 'court.award_first_respect':
                flag(168, True)
                emit('addn', 3, self.uil['reward']['points'])
                v[3] = (v[3] + self.uil['reward']['points']) % 256
            elif name == 'court.finish_bow':
                flag(22, False)
                flag(98, False)
                position_scratch(self.uil['gesture']['finish_dx'])
                emit('erase', 0)
                # Preserve the original order. Its native result is view0,
                # loop1; a generic renderer's loop clamp is not a substitute.
                emit('set.loop', 0, 1)
                emit('set.view', 0, 0)
                place()
                cycle_time(1)
                emit('draw', 0)
                emit('start.motion', 0)
                v[6], current['player_control'] = 0, True
            elif name == 'narration.modal':
                emit('print', self.package['udl']['resource_bindings'][effect['resource']]['number'])
            else:
                raise CourtAdapterError('Unrealized court primitive')
        if self.project_state(current) != result['state']:
            raise CourtAdapterError('UDL realization disagrees with semantic effects')
        continuation = None
        if result['continuation'] is not None:
            continuation = {'package_sha256': self.package_sha256,
                            'source_state_sha256': self._continuation_digest(current),
                            'semantic': result['continuation']}
        return {**result, 'state': current, 'semantic_state': result['state'],
                'semantic_effects': result['effects'], 'effects': actions,
                'continuation': continuation}
