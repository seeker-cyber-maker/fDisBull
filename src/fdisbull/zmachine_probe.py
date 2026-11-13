"""Experimental Z-machine provider probes; no bundled ScummVM engine.

Word16Probe executes the existing independent IR consumer. ScummVMZCodePeer
requires a separately instrumented, owned RPC peer; stock ScummVM will not work.
Observations, memory and checkpoints can contain private game data.
"""
from __future__ import annotations

import copy
from collections import deque
from hashlib import sha256
import json
import time

from .zmachine import inspect_story_bytes

PROTOCOL = 'fdisbull-scummvm-zcode-probe-1'
MAX_TEXT_BYTES = 1024 * 1024
MAX_EVENT_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 65536


def _int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Expected lowercase SHA-256')
    return value



class StoryBinding:
    """Immutable source identity; byte offsets are not DOS addresses."""
    def __init__(self, story):
        self.info = inspect_story_bytes(story)
        self.story = story
        self.image = story[:self.info['declared_bytes']]

    def identity(self):
        return {key: self.info[key] for key in
                ('sha256', 'version', 'release', 'serial_text', 'declared_bytes', 'static_memory', 'globals')}

    def projection(self, memory, *, input_pending, text, command_index):
        """A declared prompt projection, not a complete portable VM snapshot."""
        if not isinstance(memory, bytes) or len(memory) != len(self.image):
            raise ValueError('Expected complete declared story memory')
        if type(input_pending) is not bool or not isinstance(text, str):
            raise ValueError('Expected explicit input readiness and text')
        _int(command_index, 'command_index', 0, 1000000)
        end = self.info['static_memory']
        globals_at = self.info['globals']
        return {'story': self.identity(), 'input_pending': input_pending,
                'command_index': command_index, 'text': text,
                'dynamic_hex': memory[64:end].hex(),
                'dynamic_scope': [64, end], 'header_excluded': [0, 64],
                'globals': [int.from_bytes(memory[i:i+2], 'big')
                            for i in range(globals_at, globals_at + 480, 2)],
                'scope': 'prompt projection; excludes header, stack, RNG and host effects'}


def compare_prompt_states(left, right):
    """Compare only explicitly retained prompt data, never unknown as equal.

The caller must pair the same command prefix and declared RNG experiment.
Equality here does not authenticate provenance or qualify an entire engine.
    """
    required = {'story', 'input_pending', 'command_index', 'text', 'dynamic_hex',
                'dynamic_scope', 'header_excluded', 'globals', 'scope'}
    for record in (left, right):
        if not isinstance(record, dict) or not required <= set(record):
            raise ValueError('Incomplete prompt projection')
        story = record['story']
        if not isinstance(story, dict):
            raise ValueError('Missing story identity')
        _sha(story.get('sha256'))
        if type(story.get('version')) is not int or story['version'] != 3:
            raise ValueError('Only qualified version 3 prompt projections are supported')
        _int(story.get('release'), 'release', 0, 65535)
        if not isinstance(story.get('serial_text'), str) or len(story['serial_text']) != 6:
            raise ValueError('Missing six-character story serial')
        declared = _int(story.get('declared_bytes'), 'declared_bytes', 64, 128 * 1024)
        end = _int(story.get('static_memory'), 'static_memory', 64, 65536)
        if (record['input_pending'] is not True or record['dynamic_scope'] != [64, end]
                or record['header_excluded'] != [0, 64]):
            raise ValueError('Comparison requires matching declared prompt boundaries')
        _int(record['command_index'], 'command_index', 0, 1000000)
        if end > declared:
            raise ValueError('Dynamic memory exceeds declared story')
        globals_at = _int(story.get('globals'), 'globals', 64, end - 480)
        raw = record['dynamic_hex']
        if (not isinstance(raw, str) or len(raw) != (end - 64) * 2
                or any(c not in '0123456789abcdef' for c in raw)):
            raise ValueError('Incomplete dynamic memory projection')
        if (not isinstance(record['text'], str) or not isinstance(record['globals'], list)
                or len(record['globals']) != 240):
            raise ValueError('Missing text or globals')
        for value in record['globals']:
            _int(value, 'global', 0, 65535)
        memory = bytes.fromhex(raw)
        observed_globals = [int.from_bytes(memory[i:i+2], 'big')
                            for i in range(globals_at - 64, globals_at - 64 + 480, 2)]
        if record['globals'] != observed_globals:
            raise ValueError('Globals disagree with retained dynamic bytes')
    if left['story'] != right['story'] or left['command_index'] != right['command_index']:
        raise ValueError('Different story identities or command boundaries')
    a, b = bytes.fromhex(left['dynamic_hex']), bytes.fromhex(right['dynamic_hex'])
    differences = [64 + i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    text_equal = ' '.join(left['text'].split()) == ' '.join(right['text'].split())
    return {'matched': not differences and text_equal and left['globals'] == right['globals'],
            'text_equal_whitespace_normalized': text_equal,
            'globals_equal': left['globals'] == right['globals'],
            'dynamic_equal': not differences, 'different_byte_count': len(differences),
            'first_different_offsets': differences[:32],
            'compared_bytes': len(a), 'header_excluded': [0, 64],
            'original_runtime_verified': False, 'whole_engine_equivalence': False}


def make_word16_probe(program, story, *, seed=12, random_tape=None, trace_capacity=256):
    """Construct a probe around the unchanged, optional standalone consumer."""
    from fdisbull_player.word16 import Word16Runtime, Word16Error

    class Word16Probe(Word16Runtime):
        def __init__(self):
            binding = StoryBinding(story)
            if program['source']['sha256'] != binding.info['sha256']:
                raise ValueError('IR belongs to another original story')
            if bytes.fromhex(program['memory']['initial']) != binding.image:
                raise ValueError('IR initial memory differs from bound story')
            if program['entry'] != binding.info['initial_pc']:
                raise ValueError('IR entry differs from bound story')
            if program['memory']['writable_end'] != binding.info['static_memory']:
                raise ValueError('IR writable boundary differs from bound story')
            if any(program['layout'].get(key) != binding.info[key] for key in
                   ('globals', 'objects', 'dictionary', 'abbreviations', 'declared_bytes')):
                raise ValueError('IR layout differs from bound story')
            _int(trace_capacity, 'trace_capacity', 1, 2048)
            super().__init__(program, seed=seed, random_tape=random_tape)
            self.binding = binding
            self.revision = 0
            self.breakpoints = set()
            self._skip_once = None
            self.trace_records = deque(maxlen=trace_capacity)
            self.trace_dropped = 0
            self._active = False

        def observe(self):
            if self._active:
                raise ValueError('Observe only at a stopped probe boundary')
            return {'provider': 'fdisbull-word16', 'execution_unit': 'lowered-source-block',
                    'story': self.binding.identity(), 'package_sha256': self.package_digest,
                    'pc': self.pc, 'address_space': 'story-byte',
                    'phase': 'faulted' if self.fault else 'halted' if self.halted else
                             'input_pending' if self.pending_input is not None else 'before_block',
                    'revision': self.revision, 'stack_depth': len(self.stack),
                    'call_depth': len(self.frames), 'original_x86_executed': False}

        def peek_variable(self, index):
            """Variable zero is a peek, never the source VM's destructive pop."""
            if self._active:
                raise ValueError('Read variables only at a stopped probe boundary')
            _int(index, 'variable', 0, 255)
            if index == 0:
                if len(self.stack) <= self.frames[-1]['base']:
                    raise ValueError('Current routine evaluation stack is empty')
                return self.stack[-1]
            if index < 16:
                if index > len(self.frames[-1]['locals']):
                    raise ValueError('Local variable is not live')
                return self.frames[-1]['locals'][index - 1]
            at = self.layout['globals'] + 2 * (index - 16)
            return int.from_bytes(self.memory[at:at+2], 'big')

        def breakpoint(self, pc):
            if self._active:
                raise ValueError('Set breakpoints only at a stopped probe boundary')
            _int(pc, 'pc', 64, len(self.memory) - 1)
            if pc not in self.blocks:
                raise ValueError('No lowered instruction candidate at breakpoint')
            guard = self._guards[pc]
            if self.memory[pc:pc+len(guard)] != guard:
                raise ValueError('Breakpoint instruction bytes changed')
            self.breakpoints.add(pc)
            return {'pc': pc, 'story_sha256': self.binding.info['sha256'],
                    'boundary': 'before lowered source block', 'reachability': 'not_established'}

        def delete_breakpoint(self, pc):
            if self._active:
                raise ValueError('Delete breakpoints only at a stopped probe boundary')
            _int(pc, 'pc', 64, len(self.memory) - 1)
            if pc not in self.breakpoints:
                raise ValueError('Breakpoint is not owned by this probe')
            self.breakpoints.remove(pc)
            return {'pc': pc, 'removed': True}

        def run(self, max_steps=10000, *, timeout_ms=10000):
            _int(max_steps, 'max_steps', 1, 1000000)
            _int(timeout_ms, 'timeout_ms', 1, 600000)
            if self._active:
                raise ValueError('Probe does not support concurrent execution')
            if self.fault:
                raise ValueError('Execution is faulted; restore a checkpoint')
            self._active = True
            start = time.monotonic()
            output, events, steps = [], [], 0
            reason = 'budget'
            text_bytes, event_bytes = 0, 0

            def collect(text, incoming):
                nonlocal text_bytes, event_bytes
                text_bytes += len(text.encode('utf-8'))
                event_bytes += len(json.dumps(incoming, allow_nan=False).encode('utf-8'))
                if (text_bytes > MAX_TEXT_BYTES or event_bytes > MAX_EVENT_BYTES
                        or len(events) + len(incoming) > MAX_EVENTS):
                    self.fault = 'Debugger run output budget exceeded'
                    raise Word16Error(self.fault)
                output.append(text)
                events.extend(incoming)

            try:
                while not self.halted and self.pending_input is None and steps < max_steps:
                    if (time.monotonic() - start) * 1000 >= timeout_ms:
                        reason = 'host_timeout'
                        break
                    pc = self.pc
                    skip = self._skip_once == (self.revision, pc)
                    self._skip_once = None
                    if pc in self.breakpoints and not skip:
                        self._skip_once = (self.revision, pc)
                        reason = 'breakpoint'
                        break
                    last = super().run(max_steps=1)
                    steps += last['steps']
                    self.revision += last['steps']
                    collect(last['text'], last['events'])
                    if len(self.trace_records) == self.trace_records.maxlen:
                        self.trace_dropped += 1
                    self.trace_records.append({'before_pc': pc, 'after_pc': self.pc,
                                               'revision': self.revision, 'completed_blocks': last['steps']})
                # Input echo or checkpoint-restored output can exist even if a
                # breakpoint stops before the first block. Drain it once, as
                # the baseline consumer does when returning from run().
                collect(''.join(self._text), self._events)
                self._text, self._events, self._text_size = [], [], 0
                if self.halted:
                    reason = 'halted'
                elif self.pending_input is not None:
                    reason = 'input'
                result = {'status': 'halted' if self.halted else 'input' if self.pending_input is not None
                          else 'budget_exhausted' if reason == 'budget' else reason,
                          'text': ''.join(output), 'events': events, 'steps': steps,
                          'pc': self.pc, **self._score(), 'stop_reason': reason,
                          'revision': self.revision, 'host_timeout_scope': 'cooperative block boundaries'}
                if self.halt_reason is not None:
                    result['halt_reason'] = self.halt_reason
                return result
            finally:
                self._active = False

        def step(self, count=1, *, timeout_ms=10000):
            if self._active:
                raise ValueError('Probe does not support concurrent execution')
            _int(timeout_ms, 'timeout_ms', 1, 600000)
            _int(count, 'count', 1, 10000)
            self._skip_once = (self.revision, self.pc)
            return self.run(count, timeout_ms=timeout_ms)

        def command(self, text, max_steps=10000, *, expected_revision=None):
            if self._active:
                raise ValueError('Probe does not support concurrent input')
            if expected_revision is not None and (type(expected_revision) is not int
                                                 or expected_revision != self.revision):
                raise ValueError('Stale input revision; do not replay the command')
            _int(max_steps, 'max_steps', 1, 1000000)
            # Base command dispatches through this run(), so breakpoints remain active.
            result = super().command(text, max_steps=max_steps)
            # Input acceptance is a mutation even when zero blocks executed.
            # Preserve a just-hit breakpoint's one-shot resume identity.
            skipped = self._skip_once
            self.revision += 1
            if skipped is not None:
                self._skip_once = (self.revision, skipped[1])
            result['revision'] = self.revision
            return result

        def restore(self, snapshot):
            if self._active:
                raise ValueError('Cannot restore during execution')
            super().restore(snapshot)
            self.revision += 1
            self._skip_once = None
            self.trace_records.clear()
            self.trace_dropped = 0

        def trace(self):
            return {'events': list(self.trace_records), 'dropped': self.trace_dropped,
                    'unit': 'lowered-source-block', 'whole_run_complete': False}

    return Word16Probe()


class ScummVMZCodePeer:
    """Client for the future patched GLK/Z-code sidecar, not an engine launcher.

The injected peer must provide bounded call(op, params, timeout_ms=...) and close().
The caller owns transport/process identity. No native implementation is bundled.
    """
    def __init__(self, peer, story, *, expected_runtime_sha256):
        self.binding = StoryBinding(story)
        self.peer, self.closed, self.revision = peer, False, -1
        self.expected_runtime_sha256 = _sha(expected_runtime_sha256)
        try:
            hello = self._call('hello')
            expected = {'protocol': PROTOCOL, 'engine': 'glk', 'subengine': 'zcode',
                        'zversion': 3, 'story_sha256': self.binding.info['sha256'],
                        'runtime_sha256': expected_runtime_sha256, 'original_x86_executed': False}
            if any(type(hello.get(k)) is not type(v) or hello.get(k) != v for k, v in expected.items()):
                raise ValueError('Unsupported Z-code peer identity or protocol')
            caps = hello.get('capabilities')
            if (not isinstance(caps, list) or any(not isinstance(v, str) for v in caps)
                    or not {'state.get', 'memory.read', 'step', 'run'} <= set(caps)):
                raise ValueError('Z-code peer lacks required capabilities')
            self.hello = copy.deepcopy(hello)
            self.capabilities = frozenset(caps)
            self.observe()
        except BaseException:
            self.close()
            raise

    def _call(self, op, params=None, *, timeout_ms=10000):
        if self.closed:
            raise ValueError('Z-code peer is closed')
        _int(timeout_ms, 'timeout_ms', 1, 600000)
        try:
            result = self.peer.call(op, params, timeout_ms=timeout_ms)
            if not isinstance(result, dict):
                raise ValueError('Malformed Z-code reply')
            return result
        except BaseException:
            self.close()
            raise

    def observe(self, *, timeout_ms=10000):
        try:
            state = self._call('state.get', timeout_ms=timeout_ms).get('state')
            if (not isinstance(state, dict) or state.get('paused') is not True
                    or state.get('phase') not in ('before_opcode', 'after_opcode', 'input_pending', 'backend_yield')):
                raise ValueError('Z-code state lacks a confirmed stop')
            revision = _int(state.get('revision'), 'revision', 0, 2**53-1)
            _int(state.get('pc'), 'pc', 0, len(self.binding.image)-1)
            if revision < self.revision:
                raise ValueError('Stale Z-code state revision')
            self.revision = revision
            return {**state, 'story': self.binding.identity(), 'provider': 'scummvm-glk-zcode',
                    'original_x86_executed': False}
        except BaseException:
            self.close()
            raise

    def read_memory(self, offset, length):
        _int(offset, 'offset', 0, len(self.binding.image))
        _int(length, 'length', 1, 4096)
        if offset + length > len(self.binding.image):
            raise ValueError('Memory range exceeds story')
        before = self.observe()
        params = {'offset': offset, 'length': length, 'revision': before['revision']}
        reply = self._call('memory.read', params)
        try:
            if any(type(reply.get(k)) is not type(v) or reply.get(k) != v for k, v in params.items()):
                raise ValueError('Memory read changed identity or range')
            data = reply.get('hex')
            if (not isinstance(data, str) or len(data) != 2 * length
                    or any(c not in '0123456789abcdef' for c in data)):
                raise ValueError('Memory read is incomplete')
            return bytes.fromhex(data)
        except BaseException:
            self.close()
            raise

    def run(self, *, max_instructions=10000, timeout_ms=10000):
        _int(max_instructions, 'max_instructions', 1, 1000000)
        _int(timeout_ms, 'timeout_ms', 100, 600000)
        return self._execute('run', max_instructions, timeout_ms)

    def step(self, *, timeout_ms=10000):
        _int(timeout_ms, 'timeout_ms', 100, 600000)
        return self._execute('step', 1, timeout_ms)

    def _execute(self, op, budget, timeout):
        reply = self._call(op, {'max_instructions': budget, 'max_ms': timeout-50}, timeout_ms=timeout)
        try:
            stop = reply.get('stop')
            if (not isinstance(stop, dict) or stop.get('paused') is not True
                    or stop.get('reason') not in ('budget', 'breakpoint', 'input_pending', 'host_timeout', 'quit')
                    or stop.get('phase') not in ('before_opcode', 'after_opcode', 'input_pending', 'backend_yield', 'exited')):
                raise ValueError('Z-code execution lacks a structured stop')
            _int(stop.get('completed_dispatches'), 'completed_dispatches', 0, budget)
            if stop['reason'] == 'quit':
                if stop['phase'] != 'exited':
                    raise ValueError('Quit receipt requires exited phase')
            else:
                _int(stop.get('pc'), 'pc', 0, len(self.binding.image)-1)
            rev = _int(stop.get('revision'), 'revision', 0, 2**53-1)
            if rev < self.revision:
                raise ValueError('Stale Z-code execution receipt')
            self.revision = rev
            return {**stop, 'starting_dispatch_completed': None,
                    'original_x86_executed': False, 'scope': 'dispatch count, not caller completion'}
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.peer.close()
