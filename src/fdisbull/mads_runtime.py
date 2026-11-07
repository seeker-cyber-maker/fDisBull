"""Bounded, source-bound MADS conversation model; not a native game engine.

Arithmetic/commands follow the documented ScummVM core/conv profile. Original
DOS equivalence, native callbacks, live pointer aliases and UI scheduling are
not established. Imports and host-controlled variables require explicit values.
Media decoders never import this module. Checkpoints contain private game state.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json
import time

from .mads_processor import Conversation, MADSConversationProcessor
from .mads_resources import bounded_int, require, read_cnd

PROFILE = 'mads-conversation-model-1'


def signed16(value):
    require(type(value) is int, 'Expected an integer VM value')
    return ((value + 32768) & 65535) - 32768


def evaluate(expression, read):
    """Evaluate signed-16 expressions, preserving operand-read order."""
    code = expression['operation']
    if code == 255:
        return -1
    values = []
    for operand in expression['operands']:
        flag = operand['encoded_flag']
        require(flag in (0, 1, 2), 'Unqualified operand flag')
        value = signed16(read(operand['value']) if flag else operand['value'])
        values.append(int(not value) if flag == 2 else value)
    if code == 0:
        return values[0]
    a, b = values
    if code == 1: result = a + b
    elif code == 2: result = a - b
    elif code == 3: result = a * b
    elif code in (4, 5):
        q = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1) if b else 0
        result = q if code == 4 else a - q*b if b else 0
    elif code == 6: result = int(a >= b)
    elif code == 7: result = int(a <= b)
    elif code == 8: result = int(a > b)
    elif code == 9: result = int(a < b)
    elif code == 10: result = int(a != b)
    elif code == 11: result = int(a == b)
    elif code == 12: result = int(bool(a) and bool(b))
    elif code == 13: result = int(bool(a) or bool(b))
    else: raise ValueError('Unqualified expression operation')
    return signed16(result)


class ConversationRuntime:
    """Single-controller dialog model with transactional dispatch and replay.

    external_values maps VM indices to caller-supplied signed-16 values. It is
    an explicit model input, not a recovered original pointer or host callback.
    random_tape supplies exact inclusive draws, never assumed seed equivalence.
    """
    def __init__(self, cnv, cnd, *, external_values=None, random_tape=(), trace_capacity=256):
        self.conversation = Conversation.read(cnv)
        self.defaults = read_cnd(cnd)
        require(self.defaults['entry_flag_count'] == len(self.conversation.dialogs),
                'CNV/CND dialog count mismatch')
        n = self.defaults['variable_count']
        require(2 <= n <= 65536, 'Conversation needs node/resume variables')
        self.required = set(self.defaults['imports']) | set(range(2, min(23, n)))
        # Serialized pointers and placeholders cannot establish a live binding.
        self.required.update(v['index'] for v in self.defaults['variables']
                             if v['stored_kind'] in (0x564d, 0x4d56, 0xffff))
        self.variables = [v['value'] for v in self.defaults['variables']]
        for i in self.required: self.variables[i] = None
        require(external_values is None or type(external_values) is dict, 'Expected explicit external values')
        for index, value in (external_values or {}).items():
            bounded_int(index, 'external variable index', 0, n-1)
            bounded_int(value, 'external variable value', -32768, 32767)
            self.variables[index] = value
        require(type(random_tape) in (list, tuple) and len(random_tape) <= 65536,
                'RNG tape exceeds limit')
        for value in random_tape: bounded_int(value, 'RNG draw', 1, 65535)
        self.tape = tuple(random_tape)
        self.flags = list(self.defaults['entry_flags'])
        self.rng_position = 0
        self.messages = {'player': [], 'npc': []}
        self.speech = {'player': [], 'npc': []}
        self.dialog = self.pc = None
        self.phase = 'idle'
        self.revision = 0
        self.breakpoints = set()
        self._skip_once = None
        self._processor = None
        self._processors = {}
        bounded_int(trace_capacity, 'trace capacity', 1, 4096)
        self._trace = deque(maxlen=trace_capacity)
        self.trace_dropped = 0
        self.binding = dict(profile=PROFILE,
            cnv_sha256=sha256(self.conversation.pack.source).hexdigest(),
            cnd_sha256=self.defaults['source_sha256'],
            rng_sha256=sha256(json.dumps(self.tape, separators=(',', ':')).encode()).hexdigest())

    def _read(self, index):
        bounded_int(index, 'variable index', 0, len(self.variables)-1)
        value = self.variables[index]
        require(value is not None, f'Unbound external variable {index}')
        return value

    def _write(self, index, value):
        bounded_int(index, 'variable index', 0, len(self.variables)-1)
        require(index not in self.required or self.variables[index] is not None,
                f'Unbound external variable {index}')
        self.variables[index] = signed16(value)

    def _proc(self, index):
        bounded_int(index, 'dialog index', 0, len(self.conversation.dialogs)-1)
        if index not in self._processors:
            self._processors[index] = MADSConversationProcessor(self.conversation, index)
        return self._processors[index]

    def start_dialog(self, index, *, expected_revision=None):
        self._revision(expected_revision)
        require(self.phase != 'paused', 'Finish or restore the active dialog before starting another')
        processor = self._proc(index)
        initial = self._read(1)
        require(self.variables[0] is not None, 'Node variable is unbound')
        self._processor = processor
        self.dialog, self.pc = index, processor.entry_address
        self.variables[0] = initial
        self.messages = {'player': [], 'npc': []}
        self.speech = {'player': [], 'npc': []}
        self.phase = 'paused'; self.revision += 1; self._skip_once = None
        return self.observe()

    def _revision(self, expected):
        require(expected is None or type(expected) is int and expected == self.revision,
                'Stale model revision')

    def observe(self):
        return dict(binding=deepcopy(self.binding), dialog=self.dialog, pc=self.pc,
                    phase=self.phase, revision=self.revision,
                    variables=list(self.variables), entry_flags=list(self.flags),
                    messages=deepcopy(self.messages), speech=deepcopy(self.speech),
                    rng_position=self.rng_position, original_runtime_verified=False,
                    execution_scope='conversation model, not native scene/host execution')

    def breakpoint(self, dialog, offset):
        p = self._proc(dialog)
        require(type(offset) is int and offset in p._rows, 'Not a dialog instruction boundary')
        self.breakpoints.add((dialog, offset))
        return dict(dialog=dialog, offset=offset, binding=deepcopy(self.binding))

    def remove_breakpoint(self, dialog, offset):
        require((dialog, offset) in self.breakpoints, 'Unknown breakpoint')
        self.breakpoints.remove((dialog, offset))

    def _dispatch(self):
        p = self._processor
        row = p._rows[self.pc]
        op, expressions, params = row['opcode'], row['conditions'], row['parameters']
        require(op in (1, 2, 3, 4, 5, 7, 8, 9),
                'Opcode has conflicting historical semantics and is not executable in this model')
        next_pc = self.pc + row['size']
        evaluate_here = lambda item: evaluate(item, self._read)
        condition = evaluate_here(expressions[0])
        stop = False
        if condition:
            if op in (1, 2, 3):
                for index in params['entry_ids']:
                    bounded_int(index, 'entry flag index', 0, len(self.flags)-1)
                    value = self.flags[index]
                    if op == 1: value = (value | 0x4000) & 0x7fff
                    elif op == 2: value &= 0x7fff
                    elif not value & 0x4000: value |= 0x8000
                    self.flags[index] = value
            elif op in (4, 5):
                choices = params['weighted_messages'][:10]
                total = sum(item['weight'] for item in choices)
                require(total > 0, 'Message has no positive selection weight')
                require(self.rng_position < len(self.tape), 'RNG tape exhausted')
                draw = self.tape[self.rng_position]
                require(draw <= total, 'RNG draw outside requested inclusive range')
                self.rng_position += 1
                selected = None
                for i, item in enumerate(choices):
                    draw -= item['weight']
                    if draw <= 0: selected = i; break
                item = choices[selected]
                bounded_int(item['message_id'], 'message index', 0, self.conversation.counts[2]-1)
                side = 'player' if op == 4 else 'npc'
                if len(self.messages[side]) < 10: self.messages[side].append(item['message_id'])
                voices = params['speech_ids'][:10]
                values = voices[selected:selected+1] if len(params['weighted_messages']) > 1 else voices
                self.speech[side].extend(values[:10-len(self.speech[side])])
            elif op == 7:
                target, resume = evaluate_here(expressions[1]), evaluate_here(expressions[2])
                require(target < len(self.conversation.nodes) and resume < len(self.conversation.nodes),
                        'Node target outside conversation')
                self._write(0, target)
                if target >= 0: self._write(1, target)
                elif resume >= 0: self._write(1, resume)
                stop = True
            elif op == 8:
                next_pc = params['target_offset']
                require(next_pc in p._rows, 'Branch escapes selected dialog or targets an operand')
            else:
                self._write(params['variable_index'], evaluate_here(expressions[1]))
        self.pc = next_pc
        if stop:
            self.phase = 'done'
        elif next_pc == p._end:
            self._write(0, -1); self.phase = 'done'
        else:
            require(next_pc in p._rows, 'Execution lost instruction boundary')
        return op

    def step(self, *, expected_revision=None):
        self._revision(expected_revision)
        require(self.phase == 'paused', 'No active paused dialog')
        before = self.snapshot()
        try:
            op = self._dispatch()
        except Exception:
            self._assign(before)
            raise
        self.revision += 1
        self._skip_once = None
        if len(self._trace) == self._trace.maxlen: self.trace_dropped += 1
        self._trace.append(dict(dialog=self.dialog, before_pc=before['pc'], after_pc=self.pc,
                                opcode=op, revision=self.revision))
        return self.observe()

    def run(self, max_steps=10000, *, timeout_ms=1000, expected_revision=None):
        self._revision(expected_revision)
        bounded_int(max_steps, 'instruction budget', 1, 1000000)
        bounded_int(timeout_ms, 'time budget', 1, 60000)
        start = time.monotonic(); count = 0; reason = 'budget'
        while self.phase == 'paused' and count < max_steps:
            if (time.monotonic()-start)*1000 >= timeout_ms:
                reason = 'host_timeout'; break
            key = (self.dialog, self.pc)
            skip = self._skip_once == (self.revision, key)
            self._skip_once = None
            if key in self.breakpoints and not skip:
                self._skip_once = (self.revision, key); reason = 'breakpoint'; break
            self.step(); count += 1
        if self.phase != 'paused': reason = self.phase
        return dict(stop_reason=reason, completed_dispatches=count, state=self.observe())

    def trace(self):
        return dict(events=deepcopy(list(self._trace)), dropped=self.trace_dropped,
                    original_runtime_verified=False)

    def snapshot(self):
        return dict(binding=deepcopy(self.binding), variables=list(self.variables),
                    flags=list(self.flags), dialog=self.dialog, pc=self.pc, phase=self.phase,
                    rng_position=self.rng_position, messages=deepcopy(self.messages), speech=deepcopy(self.speech))

    def _assign(self, state):
        self.variables = list(state['variables']); self.flags = list(state['flags'])
        self.dialog = state['dialog']; self.pc = state['pc']; self.phase = state['phase']
        self.rng_position = state['rng_position']
        self.messages = deepcopy(state['messages']); self.speech = deepcopy(state['speech'])
        self._processor = None if self.dialog is None else self._proc(self.dialog)

    def restore(self, state, *, expected_revision=None):
        self._revision(expected_revision)
        require(type(state) is dict and set(state) == set(self.snapshot()) and state['binding'] == self.binding,
                'Checkpoint schema/source/RNG binding mismatch')
        for field, size, low, high in (('variables', len(self.variables), -32768, 32767),
                                       ('flags', len(self.flags), 0, 65535)):
            values = state[field]
            require(type(values) is list and len(values) == size, 'Checkpoint vector size mismatch')
            for i, value in enumerate(values):
                if field == 'variables' and value is None:
                    require(i in self.required, 'Unexpected unbound ordinary variable')
                else: bounded_int(value, field, low, high)
        require(state['phase'] in ('idle', 'paused', 'done'), 'Invalid checkpoint phase')
        if state['phase'] == 'idle':
            require(state['pc'] is None and state['dialog'] is None, 'Idle checkpoint has a program counter')
        else:
            p = self._proc(state['dialog'])
            require(type(state['pc']) is int and (state['pc'] in p._rows or
                    state['phase'] == 'done' and state['pc'] == p._end), 'Invalid checkpoint program counter')
        bounded_int(state['rng_position'], 'RNG cursor', 0, len(self.tape))
        for field in ('messages', 'speech'):
            require(type(state[field]) is dict and set(state[field]) == {'player', 'npc'}, 'Invalid message queues')
            for values in state[field].values():
                require(type(values) is list and len(values) <= 10, 'Message queue exceeds budget')
                for value in values: bounded_int(value, field, 0,
                    self.conversation.counts[2]-1 if field == 'messages' else 65535)
        self._assign(deepcopy(state))
        self.revision += 1; self._skip_once = None
        self._trace.clear(); self.trace_dropped = 0
        return self.observe()
