"""Execute a bounded AGI source slice against a concrete script-state boundary.

This reference reads original LOGIC bytes directly and does not import an intent
producer, definition, evaluator or adapter. The shared layout checker qualifies
byte boundaries only; the control and effect semantics below are separate.

The supported domain is byte variables, flags, literal-word-group ``said``, ego
left/baseline coordinates, and the listed actor/output requests. Actor requests
are recorded in source order without rendering, cel/loop validation, scheduling,
or native execution. In particular, set.loop before set.view is not reordered.
Ordinary blocking print pauses before its continuation; the caller supplies the
acknowledgement by explicitly resuming at the returned PC. No elapsed time or
animation-completion flag is manufactured.

Conditional opcode zero and high-bit IF displacements are explicitly outside
this reference profile: their shared-layout interpretation does not match the
pinned interpreter's terminator and unsigned-forward-IF semantics. This does
not change the preserved census or broaden the execution qualification.

Semantics references:
https://peterkelly.github.io/agi-re/spec/logic_bytecode.html
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_test.cpp
"""
from copy import deepcopy

from .agi_layout import logic_layout


_ACTIONS = {
    0: 'return', 3: 'assignn', 5: 'addn', 7: 'subn',
    12: 'set', 13: 'reset', 35: 'draw', 36: 'erase',
    38: 'position.v', 39: 'get.posn', 41: 'set.view', 43: 'set.loop',
    47: 'set.cel', 73: 'end.of.loop', 76: 'cycle.time',
    77: 'stop.motion', 78: 'start.motion', 101: 'print',
}
_ACTOR_ACTIONS = frozenset({35, 36, 38, 39, 41, 43, 47, 73, 76, 77, 78})


class AGISliceError(ValueError):
    """Unsupported or invalid reference execution; no caller state is changed."""


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise AGISliceError(f'{label} must be an integer in {minimum}..{maximum}')


def _state(value):
    required = {'variables', 'flags', 'ego', 'words', 'player_control'}
    if (not isinstance(value, dict) or required - set(value)
            or set(value) - required - {'host'}):
        raise AGISliceError('Invalid AGI slice state fields')
    variables, flags = value['variables'], value['flags']
    if not isinstance(variables, list) or len(variables) != 256:
        raise AGISliceError('AGI slice variables must contain exactly 256 bytes')
    for item in variables:
        _integer(item, 0, 255, 'AGI variable')
    if (not isinstance(flags, list) or len(flags) != 256
            or any(type(item) is not bool for item in flags)):
        raise AGISliceError('AGI slice flags must contain exactly 256 booleans')
    ego = value['ego']
    if not isinstance(ego, dict) or set(ego) != {'x', 'y'}:
        raise AGISliceError('AGI slice ego requires x and y coordinates')
    for coordinate in ego.values():
        _integer(coordinate, 0, 255, 'Ego coordinate')
    words = value['words']
    if not isinstance(words, list) or len(words) > 255:
        raise AGISliceError('Parsed words must be a bounded list')
    for word in words:
        _integer(word, 0, 65535, 'Parsed word group')
    if type(value['player_control']) is not bool:
        raise AGISliceError('player_control must be Boolean')
    if 'host' in value and not isinstance(value['host'], dict):
        raise AGISliceError('Optional host state must be a dictionary')
    return deepcopy(value)


def _ego(number):
    if number != 0:
        raise AGISliceError('Only ego screen-object 0 is in this slice state')


def _terms(payload, pc, layout):
    """Retain AND terms and nonnested OR groups without evaluating predicates."""
    terms, group = [], None
    negate = False
    cursor = pc + 1
    while payload[cursor] != 255:
        opcode = payload[cursor]
        if opcode == 252:
            if group is None:
                group = []
            else:
                if not group:
                    raise AGISliceError('Empty AGI OR group')
                terms.append(group)
                group = None
            cursor += 1
        elif opcode == 253:
            negate = True
            cursor += 1
        else:
            if opcode == 0:
                raise AGISliceError('Ambiguous conditional zero is outside this slice profile')
            end = layout['conditions'][cursor]['end']
            term = (opcode, list(payload[cursor + 1:end]), negate)
            (terms if group is None else group).append(term)
            cursor, negate = end, False
    return terms


def _predicate(opcode, operands, state):
    variables, flags = state['variables'], state['flags']
    if opcode in (1, 2, 3, 4, 5, 6):
        left = variables[operands[0]]
        right = variables[operands[1]] if opcode in (2, 4, 6) else operands[1]
        if opcode in (1, 2):
            return left == right
        return left < right if opcode in (3, 4) else left > right
    if opcode == 7:
        return flags[operands[0]]
    if opcode == 8:
        return flags[variables[operands[0]]]
    if opcode == 11:
        _ego(operands[0])
        _, left, top, right, bottom = operands
        return left <= state['ego']['x'] <= right and top <= state['ego']['y'] <= bottom
    if opcode == 14:
        groups = [int.from_bytes(bytes(operands[index:index + 2]), 'little')
                  for index in range(1, len(operands), 2)]
        if any(group in (1, 9999) for group in groups):
            raise AGISliceError('said wildcard groups are outside this slice profile')
        if not flags[2] or flags[4] or not state['words'] or state['words'] != groups:
            return False
        flags[4] = True
        return True
    raise AGISliceError(f'Unsupported AGI slice predicate {opcode:#x}')


def _condition(terms, state):
    def test(term):
        opcode, operands, negate = term
        result = _predicate(opcode, operands, state)
        return not result if negate else result

    for term in terms:
        if isinstance(term, list):
            # These cannot be rearranged: a successful said claims input even
            # when a later AND term fails or the successful predicate is NOTed.
            result = any(test(item) for item in term)
        else:
            result = test(term)
        if not result:
            return False
    return True


def run_slice(payload, state, *, entry, stop, max_steps=2000):
    """Run original bytes until stop, return, or an ordinary blocking print.

    ``entry`` is the starting payload PC; ``stop`` is an exclusive upper fence.
    All executed targets must be qualified instruction boundaries. Backward
    branches can revisit earlier LOGIC instructions, including after a resumed
    print. ``executed_offsets`` records that exact execution scope. The step
    budget counts fetched main-stream instructions, including if and goto.

    Effects are ``{operation, operands}`` records for executed source actions;
    operands remain their original bytes. Control instructions are recorded only
    in ``executed_offsets``. Implicit script-state writes, including said's input
    claim, motion's v6 reset and end.of.loop's completion reset, are reflected in
    the returned state. Other engine behavior remains an ordered request.

    State has exactly variables[256], flags[256], ego{x,y}, words and
    player_control, plus an optional host dictionary that is copied untouched.
    Invalid state, unsupported execution, fence escapes and budget exhaustion
    raise AGISliceError. The caller's input state is never modified, including
    on errors; this pure reference performs no external side effects.
    """
    if not isinstance(payload, bytes) or not 2 <= len(payload) <= 65535:
        raise AGISliceError('Invalid AGI slice LOGIC payload')
    _integer(max_steps, 1, 200000, 'max_steps')
    working = _state(state)
    try:
        layout = logic_layout(payload)
    except ValueError as exc:
        raise AGISliceError(str(exc)) from exc
    end = layout['code_end']
    _integer(entry, 2, end, 'entry')
    _integer(stop, entry, end, 'stop')
    starts = layout['instructions']
    boundaries = set(starts) | {end}
    if entry not in boundaries or stop not in boundaries:
        raise AGISliceError('Entry and stop must be instruction boundaries')
    following = dict(zip(starts, starts[1:] + [end]))
    effects, executed = [], []
    variables, flags = working['variables'], working['flags']
    pc = entry

    def result(status):
        return {'state': working, 'effects': effects, 'status': status,
                'pc': pc, 'executed_offsets': executed}

    while pc != stop:
        if pc not in following or pc > stop:
            raise AGISliceError('AGI slice control flow escapes the selected stop boundary')
        if len(executed) >= max_steps:
            raise AGISliceError('AGI slice step budget exhausted before completion')
        executed.append(pc)
        opcode, next_pc = payload[pc], following[pc]
        operands = list(payload[pc + 1:next_pc])
        if opcode == 255:
            delta = int.from_bytes(payload[next_pc - 2:next_pc], 'little')
            if delta >= 32768:
                raise AGISliceError('High-bit conditional displacement is outside this slice profile')
            passed = _condition(_terms(payload, pc, layout), working)
            pc = next_pc if passed else next_pc + delta
            continue
        if opcode == 254:
            pc = next_pc + int.from_bytes(payload[pc + 1:next_pc], 'little', signed=True)
            continue
        if opcode not in _ACTIONS:
            raise AGISliceError(f'Unsupported AGI slice action {opcode:#x}')
        if opcode in _ACTOR_ACTIONS:
            _ego(operands[0])
        if opcode == 101 and (flags[15] or variables[21] != 0):
            raise AGISliceError('Only ordinary blocking print (f15=false, v21=0) is qualified')
        effects.append({'operation': _ACTIONS[opcode], 'operands': operands})
        if opcode == 3:
            variables[operands[0]] = operands[1]
        elif opcode == 5:
            variables[operands[0]] = (variables[operands[0]] + operands[1]) & 255
        elif opcode == 7:
            variables[operands[0]] = (variables[operands[0]] - operands[1]) & 255
        elif opcode in (12, 13):
            flags[operands[0]] = opcode == 12
        elif opcode == 39:
            variables[operands[1]] = working['ego']['x']
            variables[operands[2]] = working['ego']['y']
        elif opcode == 38:
            working['ego'] = {'x': variables[operands[1]], 'y': variables[operands[2]]}
        elif opcode in (77, 78):
            working['player_control'] = opcode == 78
            variables[6] = 0
        elif opcode == 73:
            flags[operands[1]] = False
        pc = next_pc
        if opcode == 101:
            return result('awaiting_ack')
        if opcode == 0:
            return result('complete')
    return result('complete')
