"""Invented v3 programs and labeled peers, never a ScummVM qualification."""
from copy import deepcopy
from hashlib import sha256
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player.word16 import Word16Runtime, Word16Error
from fdisbull.zork_uil import compile_story
from fdisbull.zmachine_probe import (StoryBinding, make_word16_probe, compare_prompt_states,
                                     ScummVMZCodePeer, PROTOCOL)


def fixture(tmp_path, code=b'\x14\x02\x03\x10\xba', patches=()):
    raw = bytearray(2048)
    raw[0] = 3
    for at, value in ((2, 1), (4, 1024), (6, 1024), (8, 900), (10, 544),
                      (12, 64), (14, 1024), (24, 640), (26, 1024), (613, 615)):
        raw[at:at+2] = value.to_bytes(2, 'big')
    raw[18:24] = b'000001'
    raw[900:904] = bytes([0, 4, 0, 0])
    raw[1024:1024+len(code)] = code
    for at, value in patches:
        raw[at:at+len(value)] = value
    raw[28:30] = (sum(raw[64:]) & 65535).to_bytes(2, 'big')
    story = bytes(raw)
    path = tmp_path / 'invented.z3'
    path.write_bytes(story)
    program, _ = compile_story(path)
    return program, story


def normalized(result):
    return {k: v for k, v in result.items()
            if k not in ('stop_reason', 'revision', 'host_timeout_scope')}


def test_real_consumer_arithmetic_and_full_state_not_a_mock(tmp_path):
    program, story = fixture(tmp_path)
    baseline = Word16Runtime(program)
    probe = make_word16_probe(program, story)
    assert normalized(probe.run()) == baseline.run()
    assert probe.peek_variable(16) == 5
    assert probe.snapshot() == baseline.snapshot()
    assert probe.observe()['phase'] == 'halted'
    assert probe.observe()['original_x86_executed'] is False


def test_passive_observation_and_stack_peek_do_not_pop(tmp_path):
    program, story = fixture(tmp_path, b'\xe8\x7f\x2a\xba')  # push 42; quit
    probe = make_word16_probe(program, story)
    probe.step()
    before = probe.snapshot()
    assert probe.peek_variable(0) == probe.peek_variable(0) == 42
    assert probe.observe() == probe.observe()
    assert probe.snapshot() == before
    with pytest.raises(ValueError, match='not live'):
        probe.peek_variable(1)


@pytest.mark.parametrize('field', ['sha', 'padding', 'entry', 'layout', 'writable', 'bytes'])
def test_story_and_ir_identity_are_checked(tmp_path, field):
    program, story = fixture(tmp_path)
    if field == 'sha': program['source']['sha256'] = '0' * 64
    elif field == 'padding': story += b'owned-padding'
    elif field == 'entry': program['entry'] += 1
    elif field == 'layout': program['layout']['globals'] += 2
    elif field == 'writable': program['memory']['writable_end'] -= 1
    elif field == 'bytes': program['memory']['initial'] = '00' + program['memory']['initial'][2:]
    with pytest.raises(ValueError): make_word16_probe(program, story)


def test_before_block_breakpoint_resume_step_and_loop_rehit(tmp_path):
    # add 2,3 -> g0; jump back to add (PC 1031 + (-5) - 2 = 1024).
    program, story = fixture(tmp_path, b'\x14\x02\x03\x10\x8c\xff\xfb')
    probe = make_word16_probe(program, story, trace_capacity=1)
    probe.breakpoint(1024)
    assert probe.run()['steps'] == 0
    first = probe.step()
    assert first['steps'] == 1 and probe.peek_variable(16) == 5
    second = probe.run(20)
    assert second['stop_reason'] == 'breakpoint' and second['steps'] == 1
    assert probe.trace()['dropped'] == 1
    assert probe.delete_breakpoint(1024)['removed']
    limited = probe.run(7)
    assert limited['steps'] == 7 and limited['status'] == 'budget_exhausted'
    assert probe.trace()['dropped'] == 8
    with pytest.raises(ValueError): probe.delete_breakpoint(1024)


def test_input_breakpoint_and_revision_resume_without_replaying(tmp_path):
    # read(text=832, parse=864); quit. Buffers are dynamic and distinct.
    program, story = fixture(tmp_path, b'\xe4\x0f\x03\x40\x03\x60\xba',
                             patches=((832, b'\x20'), (864, b'\x04')))
    probe = make_word16_probe(program, story)
    probe.breakpoint(1030)
    assert probe.run()['status'] == 'input'
    initial = probe.snapshot()
    revision = probe.revision
    assert probe.command('invented', expected_revision=revision)['stop_reason'] == 'breakpoint'
    with pytest.raises(ValueError, match='Stale input'):
        probe.command('invented', expected_revision=revision)
    assert probe.run()['status'] == 'halted'  # skip the already hit boundary once
    probe.restore(initial)
    assert probe.observe()['phase'] == 'input_pending' and probe.trace()['events'] == []
    assert probe.revision > revision
    assert probe.snapshot() == initial


def test_cooperative_deadline_and_fault_latching(tmp_path, monkeypatch):
    import fdisbull.zmachine_probe as module
    program, story = fixture(tmp_path)
    probe = make_word16_probe(program, story)
    ticks = iter([10.0, 10.02])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    result = probe.run(timeout_ms=1)
    assert result['stop_reason'] == 'host_timeout' and result['steps'] == 0


def test_aggregate_output_limit_survives_single_block_dispatch(tmp_path, monkeypatch):
    import fdisbull.zmachine_probe as module
    # print_char 'A'; jump to itself. This tests debugger aggregation limits.
    program, story = fixture(tmp_path, b'\xe5\x7f\x41\x8c\xff\xfc')
    probe = make_word16_probe(program, story)
    monkeypatch.setattr(module, 'MAX_TEXT_BYTES', 3)
    before = probe.snapshot()
    with pytest.raises(Word16Error, match='output budget'): probe.run(100)
    with pytest.raises(ValueError, match='faulted'): probe.run()
    probe.restore(before)
    assert probe.fault is None


@pytest.mark.parametrize('value', [True, 0, -1, 1.2])
def test_invalid_execution_budgets_do_not_advance(tmp_path, value):
    program, story = fixture(tmp_path)
    probe = make_word16_probe(program, story)
    before = probe.snapshot()
    with pytest.raises(ValueError): probe.run(value)
    assert probe.snapshot() == before


def projection(story, **changes):
    result = StoryBinding(story).projection(story[:2048], input_pending=True,
                                          text='invented words', command_index=0)
    result.update(changes)
    return result


def test_comparison_is_scoped_and_contains_no_game_bytes(tmp_path):
    _, story = fixture(tmp_path)
    left = projection(story)
    right = projection(story, text='invented\n  words')
    result = compare_prompt_states(left, right)
    assert result['matched'] and result['compared_bytes'] == 960
    assert result['header_excluded'] == [0, 64]
    assert result['whole_engine_equivalence'] is False
    assert not any(k in result for k in ('text', 'dynamic_hex', 'globals'))
    right['text'] = 'a different invented response'
    assert not compare_prompt_states(left, right)['matched']
    # Full dynamic-byte comparison notices a non-global byte change too.
    changed = bytearray(story)
    changed[832] ^= 1
    right = StoryBinding(story).projection(bytes(changed), input_pending=True,
                                           text=left['text'], command_index=0)
    result = compare_prompt_states(left, right)
    assert result['first_different_offsets'] == [832]
    assert not result['dynamic_equal'] and result['globals_equal']


@pytest.mark.parametrize('change', [
    lambda r: r.update(input_pending=False),
    lambda r: r.update(command_index=1),
    lambda r: r.update(dynamic_hex='00'),
    lambda r: r.update(header_excluded=[0, 65]),
    lambda r: r['globals'].__setitem__(0, 123),
    lambda r: r['story'].update(sha256='b' * 64),
    lambda r: r['story'].update(version=True),
])
def test_bad_comparison_records_are_not_success(tmp_path, change):
    _, story = fixture(tmp_path)
    left = projection(story)
    right = deepcopy(left)
    change(right)
    with pytest.raises(ValueError): compare_prompt_states(left, right)


class LabeledTestPeer:
    """A protocol test double, not a ScummVM runtime."""
    def __init__(self, story):
        self.story = story
        self.calls, self.closes = [], 0
        self.hello = {'protocol': PROTOCOL, 'engine': 'glk', 'subengine': 'zcode', 'zversion': 3,
                      'story_sha256': sha256(story).hexdigest(), 'runtime_sha256': 'a' * 64,
                      'original_x86_executed': False,
                      'capabilities': ['state.get', 'memory.read', 'run', 'step']}
        self.state = {'paused': True, 'phase': 'before_opcode', 'revision': 1, 'pc': 1024}
        self.stop = {'paused': True, 'reason': 'budget', 'phase': 'after_opcode',
                     'revision': 2, 'pc': 1028, 'completed_dispatches': 1}
        self.alter = None

    def call(self, op, params=None, *, timeout_ms=10000):
        self.calls.append((op, deepcopy(params), timeout_ms))
        if self.alter is not None:
            result = self.alter(op, params)
            if result is not None: return result
        if op == 'hello': return deepcopy(self.hello)
        if op == 'state.get': return {'state': deepcopy(self.state)}
        if op == 'memory.read':
            return {**params, 'hex': self.story[params['offset']:params['offset']+params['length']].hex()}
        if op in ('run', 'step'):
            self.state.update(revision=self.stop['revision'], pc=self.stop.get('pc', 1024))
            return {'stop': deepcopy(self.stop)}
        raise AssertionError(op)

    def close(self): self.closes += 1


def test_native_contract_binds_exact_source_and_expected_runtime(tmp_path):
    _, story = fixture(tmp_path)
    peer = LabeledTestPeer(story)
    session = ScummVMZCodePeer(peer, story, expected_runtime_sha256='a' * 64)
    assert session.read_memory(1024, 4) == story[1024:1028]
    assert session.observe()['provider'] == 'scummvm-glk-zcode'
    result = session.step()
    assert result['completed_dispatches'] == 1
    assert result['starting_dispatch_completed'] is None
    session.close(); session.close()
    assert peer.closes == 1


@pytest.mark.parametrize('change', [
    {'protocol': 'other'}, {'engine': 'zvision'}, {'subengine': 'kyra'}, {'zversion': 5},
    {'zversion': True}, {'story_sha256': 'b'*64}, {'runtime_sha256': 'b'*64},
    {'capabilities': ['run']}, {'original_x86_executed': 0},
])
def test_native_hello_failures_close_owned_peer(tmp_path, change):
    _, story = fixture(tmp_path)
    peer = LabeledTestPeer(story); peer.hello.update(change)
    with pytest.raises(ValueError): ScummVMZCodePeer(peer, story, expected_runtime_sha256='a'*64)
    assert peer.closes == 1


@pytest.mark.parametrize('change', [
    {'paused': False}, {'reason': 'success'}, {'phase': 'unknown'},
    {'completed_dispatches': True}, {'completed_dispatches': 2}, {'revision': 0},
    {'pc': 2048}, {'reason': 'quit', 'phase': 'after_opcode'},
])
def test_native_invalid_stops_never_qualify_execution(tmp_path, change):
    _, story = fixture(tmp_path)
    peer = LabeledTestPeer(story)
    session = ScummVMZCodePeer(peer, story, expected_runtime_sha256='a'*64)
    peer.stop.update(change)
    with pytest.raises(ValueError): session.step()
    assert peer.closes == 1


def test_native_timeout_never_replays_uncertain_request(tmp_path):
    _, story = fixture(tmp_path)
    peer = LabeledTestPeer(story)
    session = ScummVMZCodePeer(peer, story, expected_runtime_sha256='a'*64)
    def fail(op, params):
        if op == 'run': raise TimeoutError('invented peer failure')
    peer.alter = fail
    with pytest.raises(TimeoutError): session.run()
    with pytest.raises(ValueError, match='closed'): session.run()
    assert sum(op == 'run' for op, _, _ in peer.calls) == 1 and peer.closes == 1


@pytest.mark.parametrize('change', [{'revision': 0}, {'offset': 0}, {'hex': 'zz'}, {'hex': ''}])
def test_native_memory_reads_keep_range_and_stopped_revision(tmp_path, change):
    _, story = fixture(tmp_path)
    peer = LabeledTestPeer(story)
    session = ScummVMZCodePeer(peer, story, expected_runtime_sha256='a'*64)
    peer.alter = lambda op, p: {**p, 'hex': '0000', **change} if op == 'memory.read' else None
    with pytest.raises(ValueError): session.read_memory(1024, 2)
    assert peer.closes == 1


def test_stack_peek_cannot_read_a_callers_stack_as_current_routine(tmp_path):
    program, story = fixture(tmp_path, b'\xe8\x7f\x2a\xba')
    probe = make_word16_probe(program, story)
    probe.step()
    # A nested routine starts with no evaluation values of its own.
    probe.frames.append({'locals': [7], 'base': 1, 'resume': 1027, 'store': 16})
    before = probe.snapshot()
    with pytest.raises(ValueError, match='Current routine'): probe.peek_variable(0)
    assert probe.peek_variable(1) == 7 and probe.snapshot() == before
